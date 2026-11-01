"""Download jobs (SPEC §6): fetch and verify every file, then offer one file or one ZIP.

The client creates a job, polls it, and asks for the finished file only when the job is done.
A ZIP is built only when every file is verified; otherwise the job fails with a reason per file
and the client can retry the failed ones.
"""

import asyncio
import secrets
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from app.domain.errors import AppError, ErrorCode
from app.downloads.fetcher import Fetcher, VerifiedFile
from app.downloads.zipper import build_zip
from app.naming.filenames import sanitize_given_name

JOB_TTL_S = 3600.0
MAX_FILES = 100  # 50 announcements, both languages
MAX_ZIP_BYTES = 500 * 1024 * 1024
FILES_PER_JOB = 3


class Mode(StrEnum):
    SINGLE = "single"
    PAIR_ZIP = "pair_zip"
    BULK_ZIP = "bulk_zip"


class ItemState(StrEnum):
    QUEUED = "queued"
    FETCHING = "fetching"
    DONE = "done"
    FAILED = "failed"


class JobState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class JobItem:
    path: str
    filename: str
    state: ItemState = ItemState.QUEUED
    bytes: int = 0
    error: dict[str, object] | None = None
    verified: VerifiedFile | None = field(default=None, repr=False)


@dataclass
class Job:
    id: str
    mode: Mode
    items: list[JobItem]
    zip_name: str
    created: float
    state: JobState = JobState.RUNNING
    error: dict[str, object] | None = None
    result: Path | None = None
    download_name: str = ""
    filename_changed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.id,
            "mode": self.mode.value,
            "state": self.state.value,
            "items": [
                {
                    "path": i.path,
                    "filename": i.filename,
                    "state": i.state.value,
                    "bytes": i.bytes,
                    "error": i.error,
                }
                for i in self.items
            ],
            "error": self.error,
            "download_name": self.download_name if self.state is JobState.DONE else None,
        }


def _zip_name(name: str) -> str:
    clean, _ = sanitize_given_name(name.removesuffix(".zip"))
    return clean.removesuffix(".pdf") + ".zip"


class JobManager:
    def __init__(
        self,
        fetcher: Fetcher,
        *,
        directory: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetcher = fetcher
        self._dir = directory or Path(tempfile.mkdtemp(prefix="hkex-jobs-"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def create(self, mode: Mode, items: list[tuple[str, str]], zip_name: str = "") -> Job:
        """Start a job for `(path, filename)` pairs. Filenames are made safe here, always."""
        self._expire()
        wanted = {Mode.SINGLE: (1, 1), Mode.PAIR_ZIP: (2, 2), Mode.BULK_ZIP: (1, MAX_FILES)}[mode]
        if not wanted[0] <= len(items) <= wanted[1]:
            raise AppError(
                ErrorCode.DOWNLOAD_LIMIT_EXCEEDED,
                f"Choose between {wanted[0]} and {wanted[1]} files for this download.",
            )
        job_items = [JobItem(path, sanitize_given_name(name)[0]) for path, name in items]
        job = Job(
            secrets.token_urlsafe(12),
            mode,
            job_items,
            _zip_name(zip_name or "HKEX-documents"),
            self._clock(),
        )
        self._jobs[job.id] = job
        self._start(job)
        return job

    def get(self, job_id: str) -> Job | None:
        self._expire()
        return self._jobs.get(job_id)

    def retry(self, job_id: str) -> Job | None:
        """Run the failed files again; files that were fetched are not fetched twice."""
        job = self.get(job_id)
        if job is None or job.state is not JobState.FAILED:
            return job
        for item in job.items:
            if item.state is ItemState.FAILED:
                item.state, item.error = ItemState.QUEUED, None
        job.state, job.error = JobState.RUNNING, None
        self._start(job)
        return job

    def _start(self, job: Job) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _expire(self) -> None:
        for job_id, job in list(self._jobs.items()):
            if self._clock() - job.created > JOB_TTL_S:
                if job.result is not None and job.mode is not Mode.SINGLE:
                    job.result.unlink(missing_ok=True)
                del self._jobs[job_id]

    async def _run(self, job: Job) -> None:
        slots = asyncio.Semaphore(FILES_PER_JOB)

        async def one(item: JobItem) -> None:
            if item.state is ItemState.DONE:
                return
            async with slots:
                item.state = ItemState.FETCHING
                try:
                    item.verified = await self._fetcher.fetch(item.path)
                except AppError as exc:
                    item.state, item.error = ItemState.FAILED, exc.to_dict()
                else:
                    item.state, item.bytes = ItemState.DONE, item.verified.size

        await asyncio.gather(*(one(i) for i in job.items))
        self._finish(job)

    def _finish(self, job: Job) -> None:
        failed = [i for i in job.items if i.state is ItemState.FAILED]
        if failed:
            if job.mode is Mode.SINGLE:
                job.error = failed[0].error
            else:
                job.error = AppError(
                    ErrorCode.ZIP_INCOMPLETE,
                    f"The ZIP wasn't created because {len(failed)} of {len(job.items)} files "
                    "failed. Retry the failed files.",
                ).to_dict()
            job.state = JobState.FAILED
            return
        files = [(i.filename, i.verified) for i in job.items if i.verified is not None]
        if job.mode is Mode.SINGLE:
            job.result, job.download_name = files[0][1].file, files[0][0]
        elif sum(v.size for _, v in files) > MAX_ZIP_BYTES:
            job.state = JobState.FAILED
            job.error = AppError(
                ErrorCode.DOWNLOAD_LIMIT_EXCEEDED,
                "These files add up to more than 500 MB. Choose fewer announcements.",
            ).to_dict()
            return
        else:
            target = self._dir / f"{job.id}.zip"
            build_zip(target, files)
            job.result, job.download_name = target, job.zip_name
        job.state = JobState.DONE

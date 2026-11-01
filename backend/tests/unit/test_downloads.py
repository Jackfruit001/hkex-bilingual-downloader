"""Downloads: allowlist, verification, fault injection (SPEC §10.5), cache, jobs and ZIPs."""

import asyncio
import csv
import io
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from app.domain.errors import AppError, ErrorCode
from app.downloads.fetcher import BASE_URL, Fetcher, source_url, verify_pdf
from app.downloads.jobs import ItemState, JobManager, JobState, Mode
from app.downloads.zipper import unique_names
from app.hkex.client import HkexClient
from tests.support import make_pdf

EN = "/listedco/listconews/sehk/2026/1015/2026101500123.pdf"
TC = "/listedco/listconews/sehk/2026/1015/2026101500124_c.pdf"
PDF = make_pdf([["Hello 12,345"]])


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def client() -> AsyncIterator[HkexClient]:
    c = HkexClient(sleep=_no_sleep, jitter=lambda: 0.0, min_interval_s=0.0, max_retries=2)
    yield c
    await c.aclose()


@pytest.fixture
def fetcher(client: HkexClient, tmp_path: Path) -> Fetcher:
    return Fetcher(client, directory=tmp_path / "cache")


def pdf_response(body: bytes = PDF, **headers: str) -> httpx.Response:
    return httpx.Response(200, content=body, headers=headers)


# --- allowlist -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        EN,
        TC,
        "/listedco/listconews/gem/2014/0707/LTN20140707123.PDF",
        "/listedco/listconews/sehk/2026/1015/sub/2026101500123.pdf",
    ],
)
def test_listed_company_pdf_paths_are_accepted(path: str) -> None:
    assert source_url(path) == BASE_URL + path


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/listedco/listconews/sehk/2026/1015/a.pdf",
        "//evil.example/a.pdf",
        "/listedco/listconews/sehk/2026/1015/../../../etc/passwd.pdf",
        "/listedco/listconews/sehk/2026/1015/a.pdf?x=1",
        "/other/path/a.pdf",
        "",
    ],
)
def test_anything_else_is_refused(path: str) -> None:
    with pytest.raises(AppError) as err:
        source_url(path)
    assert err.value.code is ErrorCode.INVALID_DOCUMENT_PATH


def test_web_page_entries_are_not_downloaded() -> None:
    with pytest.raises(AppError) as err:
        source_url("/listedco/listconews/sehk/2026/1015/2026101500123.htm")
    assert err.value.code is ErrorCode.NOT_A_PDF


# --- verification --------------------------------------------------------------------------------


def test_a_real_pdf_gives_its_hash_and_page_count() -> None:
    sha, pages = verify_pdf(make_pdf([["a"], ["b"]]))
    assert pages == 2
    assert len(sha) == 64


@pytest.mark.parametrize("data", [b"", b"<html>Error</html>", b"%PDF-1.4 truncated", b"x" * 500])
def test_anything_that_is_not_a_complete_pdf_fails(data: bytes) -> None:
    with pytest.raises(AppError) as err:
        verify_pdf(data)
    assert err.value.code is ErrorCode.VERIFY_FAILED


# --- fault injection -----------------------------------------------------------------------------


@respx.mock
async def test_a_good_download_is_verified_and_saved(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(return_value=pdf_response(content_length=str(len(PDF))))
    verified = await fetcher.fetch(EN)
    assert verified.file.read_bytes() == PDF  # the original bytes, untouched
    assert verified.pages == 1


@respx.mock
async def test_a_server_error_then_success_is_retried(fetcher: Fetcher) -> None:
    route = respx.get(BASE_URL + EN).mock(side_effect=[httpx.Response(500), pdf_response()])
    assert (await fetcher.fetch(EN)).size == len(PDF)
    assert route.call_count == 2


@respx.mock
async def test_429_with_retry_after_waits_then_succeeds(client: HkexClient, tmp_path: Path) -> None:
    delays: list[float] = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    patched = HkexClient(sleep=record, jitter=lambda: 0.0, min_interval_s=0.0)
    respx.get(BASE_URL + EN).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), pdf_response()]
    )
    await Fetcher(patched, directory=tmp_path).fetch(EN)
    assert 7.0 in delays
    await patched.aclose()


@respx.mock
async def test_a_timeout_that_keeps_happening_is_a_download_failure(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(AppError) as err:
        await fetcher.fetch(EN)
    assert err.value.code is ErrorCode.DOWNLOAD_FAILED


@respx.mock
async def test_a_connection_reset_then_success_is_retried(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(side_effect=[httpx.ReadError("reset"), pdf_response()])
    assert (await fetcher.fetch(EN)).pages == 1


@respx.mock
async def test_a_body_shorter_than_content_length_is_never_accepted(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(return_value=pdf_response(PDF[:50], content_length="9999"))
    with pytest.raises(AppError) as err:
        await fetcher.fetch(EN)
    assert err.value.code is ErrorCode.VERIFY_FAILED


@respx.mock
async def test_an_html_error_page_with_status_200_is_refused(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(return_value=pdf_response(b"<html>Please verify</html>"))
    with pytest.raises(AppError) as err:
        await fetcher.fetch(EN)
    assert err.value.code is ErrorCode.VERIFY_FAILED


@respx.mock
async def test_a_redirect_is_never_followed(fetcher: Fetcher) -> None:
    respx.get(BASE_URL + EN).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/x.pdf"})
    )
    evil = respx.get("https://evil.example/x.pdf").mock(return_value=pdf_response())
    with pytest.raises(AppError) as err:
        await fetcher.fetch(EN)
    assert err.value.code is ErrorCode.DOWNLOAD_FAILED
    assert not evil.called


@respx.mock
async def test_a_404_is_a_download_failure_without_retries(fetcher: Fetcher) -> None:
    route = respx.get(BASE_URL + EN).mock(return_value=httpx.Response(404))
    with pytest.raises(AppError) as err:
        await fetcher.fetch(EN)
    assert err.value.code is ErrorCode.DOWNLOAD_FAILED
    assert route.call_count == 1


# --- cache ---------------------------------------------------------------------------------------


@respx.mock
async def test_the_same_path_is_fetched_once_within_the_hour(fetcher: Fetcher) -> None:
    route = respx.get(BASE_URL + EN).mock(return_value=pdf_response())
    first, second = await fetcher.fetch(EN), await fetcher.fetch(EN)
    assert first == second
    assert route.call_count == 1
    assert fetcher.cache_hits == 1


@respx.mock
async def test_the_cache_expires_after_an_hour(client: HkexClient, tmp_path: Path) -> None:
    now = [0.0]
    fetcher = Fetcher(client, directory=tmp_path, clock=lambda: now[0])
    route = respx.get(BASE_URL + EN).mock(return_value=pdf_response())
    await fetcher.fetch(EN)
    now[0] = 3601.0
    await fetcher.fetch(EN)
    assert route.call_count == 2


# --- jobs and ZIPs -------------------------------------------------------------------------------


@pytest.fixture
def jobs(fetcher: Fetcher, tmp_path: Path) -> JobManager:
    return JobManager(fetcher, directory=tmp_path / "jobs")


async def finished(jobs: JobManager, job_id: str) -> None:
    for _ in range(200):
        job = jobs.get(job_id)
        assert job is not None
        if job.state is not JobState.RUNNING:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


@respx.mock
async def test_a_pair_zip_holds_both_files_unchanged_and_a_source_list(jobs: JobManager) -> None:
    tc_pdf = make_pdf([["你好 12,345"]])
    respx.get(BASE_URL + EN).mock(return_value=pdf_response())
    respx.get(BASE_URL + TC).mock(return_value=pdf_response(tc_pdf))
    job = jobs.create(
        Mode.PAIR_ZIP,
        [(EN, "EN_2026-10-15-00700-Notice.pdf"), (TC, "TC_2026-10-15-00700-通告.pdf")],
        "EN-TC_2026-10-15-00700-Notice.zip",
    )
    await finished(jobs, job.id)
    assert job.state is JobState.DONE
    assert job.result is not None
    with zipfile.ZipFile(job.result) as z:
        assert z.read("EN_2026-10-15-00700-Notice.pdf") == PDF
        assert z.read("TC_2026-10-15-00700-通告.pdf") == tc_pdf
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        raw = z.read("sources.csv")
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert [r["filename"] for r in rows] == [
        "EN_2026-10-15-00700-Notice.pdf",
        "TC_2026-10-15-00700-通告.pdf",
    ]
    assert rows[0]["source_url"] == BASE_URL + EN


@respx.mock
async def test_no_zip_is_offered_when_one_file_fails_and_retry_fixes_it(jobs: JobManager) -> None:
    respx.get(BASE_URL + EN).mock(return_value=pdf_response())
    bad = respx.get(BASE_URL + TC).mock(return_value=pdf_response(b"<html>no</html>"))
    job = jobs.create(Mode.PAIR_ZIP, [(EN, "EN_a.pdf"), (TC, "TC_a.pdf")], "pair.zip")
    await finished(jobs, job.id)
    assert job.state is JobState.FAILED
    assert job.result is None
    assert job.error is not None and job.error["code"] == "ZIP_INCOMPLETE"
    assert [i.state for i in job.items] == [ItemState.DONE, ItemState.FAILED]
    assert job.items[1].error is not None and job.items[1].error["code"] == "VERIFY_FAILED"

    bad.mock(return_value=pdf_response())
    assert jobs.retry(job.id) is job
    await finished(jobs, job.id)
    assert job.state is JobState.DONE and job.result is not None
    assert job.to_dict()["download_name"] == "pair.zip"


@respx.mock
async def test_a_single_download_reports_the_reason_when_it_fails(jobs: JobManager) -> None:
    respx.get(BASE_URL + EN).mock(side_effect=httpx.ConnectTimeout("t"))
    job = jobs.create(Mode.SINGLE, [(EN, "EN_a.pdf")])
    await finished(jobs, job.id)
    assert job.state is JobState.FAILED
    assert job.error is not None and job.error["code"] == "DOWNLOAD_FAILED"


@respx.mock
async def test_a_client_filename_is_made_safe(jobs: JobManager) -> None:
    respx.get(BASE_URL + EN).mock(return_value=pdf_response())
    job = jobs.create(Mode.SINGLE, [(EN, "../../etc/passwd?.pdf")])
    await finished(jobs, job.id)
    assert "/" not in job.items[0].filename and "?" not in job.items[0].filename
    assert job.items[0].filename.endswith(".pdf")


async def test_a_bad_path_is_a_failed_item_not_a_fetch(jobs: JobManager) -> None:
    job = jobs.create(Mode.SINGLE, [("https://evil.example/a.pdf", "a.pdf")])
    await finished(jobs, job.id)
    assert job.error is not None and job.error["code"] == "INVALID_DOCUMENT_PATH"


def test_job_sizes_are_limited(jobs: JobManager) -> None:
    with pytest.raises(AppError) as err:
        jobs.create(Mode.PAIR_ZIP, [(EN, "a.pdf")])
    assert err.value.code is ErrorCode.DOWNLOAD_LIMIT_EXCEEDED
    with pytest.raises(AppError):
        jobs.create(Mode.BULK_ZIP, [(EN, f"{i}.pdf") for i in range(101)])


async def test_jobs_expire_after_an_hour(fetcher: Fetcher, tmp_path: Path) -> None:
    now = [0.0]
    jobs = JobManager(fetcher, directory=tmp_path, clock=lambda: now[0])
    job = jobs.create(Mode.SINGLE, [(EN, "a.pdf")])
    await finished(jobs, job.id)
    now[0] = 3601.0
    assert jobs.get(job.id) is None


def test_duplicate_names_in_a_zip_are_numbered() -> None:
    assert unique_names(["a.pdf", "A.pdf", "b.pdf", "a.pdf"]) == [
        "a.pdf",
        "A-(2).pdf",
        "b.pdf",
        "a-(3).pdf",
    ]

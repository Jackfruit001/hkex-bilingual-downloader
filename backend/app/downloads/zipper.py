"""ZIP files from verified downloads (SPEC §6): stored, UTF-8 names, a `sources.csv` list."""

import csv
import io
import posixpath
import zipfile
from pathlib import Path

from app.downloads.fetcher import VerifiedFile, source_url


def unique_names(names: list[str]) -> list[str]:
    """Two entries never share a name inside a ZIP: the later one gets `-(2)`, `-(3)`."""
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        stem, ext = posixpath.splitext(name)
        candidate, n = name, 1
        while candidate.casefold() in seen:
            n += 1
            candidate = f"{stem}-({n}){ext}"
        seen.add(candidate.casefold())
        out.append(candidate)
    return out


def sources_csv(entries: list[tuple[str, VerifiedFile]]) -> bytes:
    """UTF-8 with a byte order mark so Excel shows Chinese text correctly."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["filename", "source_url", "sha256", "bytes", "pages"])
    for name, verified in entries:
        writer.writerow(
            [name, source_url(verified.path), verified.sha256, verified.size, verified.pages]
        )
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def build_zip(target: Path, files: list[tuple[str, VerifiedFile]]) -> None:
    """Write the ZIP; the caller has already confirmed every file is verified."""
    names = unique_names([name for name, _ in files])
    named = list(zip(names, (v for _, v in files), strict=True))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, verified in named:
            archive.write(verified.file, arcname=name)
        archive.writestr("sources.csv", sources_csv(named))

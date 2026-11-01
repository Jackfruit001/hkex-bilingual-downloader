"""The API end to end in fixture mode: recorded HKEXnews responses, no network (SPEC §10.6)."""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

SEARCH = {"stock_code": "700", "start": "2026-09-30", "end": "2026-10-30"}


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HKEX_MODE", "fixtures")
    with TestClient(app) as client:
        yield client


def search(api: TestClient, **changes: Any) -> Any:
    return api.post("/api/search", json={**SEARCH, **changes})


def test_search_returns_pairs_with_filenames_and_a_summary(api: TestClient) -> None:
    body = search(api).json()
    assert body["company"]["code"] == "00700"
    assert body["summary"]["total"] == len(body["announcements"]) > 0
    assert body["announcements"] == sorted(
        body["announcements"], key=lambda a: a["release_at"], reverse=True
    )
    pair = next(a for a in body["announcements"] if a["status"] == "matched")
    assert pair["en"]["filename"].startswith("EN_2026-")
    assert pair["tc"]["filename"].startswith("TC_2026-")
    assert pair["pair_zip_name"].startswith("EN-TC_2026-")
    assert pair["release_at"].endswith("+08:00")


def test_a_wrong_pairing_is_never_confirmed_without_evidence(api: TestClient) -> None:
    for a in search(api).json()["announcements"]:
        if a["status"] == "matched":
            assert a["evidence"], "a confirmed pair must say why"
            assert a["en"] is not None and a["tc"] is not None
        if a["status"] == "en_only":
            assert a["tc"] is None and a["pair_zip_name"] is None


def test_keyword_filter_applies_after_pairing(api: TestClient) -> None:
    everything = search(api).json()["announcements"]
    word = everything[0]["en"]["title"].split()[0]
    filtered = search(api, keyword=word.upper()).json()["announcements"]
    assert 0 < len(filtered) <= len(everything)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"stock_code": "ABC"}, "INVALID_STOCK_CODE"),
        ({"stock_code": "99999"}, "UNKNOWN_STOCK_CODE"),
        ({"start": "2026-10-30", "end": "2026-09-30"}, "INVALID_DATE_RANGE"),
        ({"end": "2999-01-01"}, "INVALID_DATE_RANGE"),
        ({"start": "30/09/2026"}, "INVALID_DATE_RANGE"),
    ],
)
def test_bad_input_gets_a_code_and_a_message(api: TestClient, changes: dict, code: str) -> None:
    response = search(api, **changes)
    assert response.status_code in (400, 404)
    assert response.json()["code"] == code
    assert response.json()["message"]


def test_a_range_with_no_announcements_says_so(api: TestClient) -> None:
    response = search(api, start="2020-01-01", end="2020-01-02")
    assert response.status_code == 404
    assert response.json()["code"] == "NO_RESULTS"


def test_unknown_fields_are_rejected(api: TestClient) -> None:
    assert search(api, url="https://evil.example").status_code == 422


def test_stock_lookup_by_code_and_name(api: TestClient) -> None:
    by_code = api.get("/api/stocks", params={"q": "700"}).json()
    assert any(s["code"] == "00700" for s in by_code)
    by_name = api.get("/api/stocks", params={"q": "tencent"}).json()
    assert any(s["code"] == "00700" for s in by_name)
    assert api.get("/api/stocks", params={"q": ""}).json() == []


def test_categories_list_has_both_languages(api: TestClient) -> None:
    cats = api.get("/api/categories").json()
    assert cats and {"code", "name_en", "name_tc"} <= cats[0].keys()


def test_every_response_asks_search_engines_not_to_index(api: TestClient) -> None:
    assert "noindex" in api.get("/api/health").headers["x-robots-tag"]


def _wait(api: TestClient, job_id: str) -> Any:
    for _ in range(200):
        job = api.get(f"/api/downloads/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_download_a_pair_zip(api: TestClient) -> None:
    pair = next(a for a in search(api).json()["announcements"] if a["pair_zip_downloadable"])
    created = api.post(
        "/api/downloads",
        json={
            "mode": "pair_zip",
            "items": [
                {"path": pair["en"]["path"], "filename": pair["en"]["filename"]},
                {"path": pair["tc"]["path"], "filename": pair["tc"]["filename"]},
            ],
            "zip_name": pair["pair_zip_name"],
        },
    )
    assert created.status_code == 202
    job = _wait(api, created.json()["job_id"])
    assert job["state"] == "done"
    file = api.get(f"/api/downloads/{job['job_id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in file.headers["content-disposition"]
    assert file.content.startswith(b"PK")


def test_a_file_is_not_offered_before_the_job_is_done_or_when_it_failed(api: TestClient) -> None:
    created = api.post(
        "/api/downloads",
        json={
            "mode": "single",
            "items": [{"path": "/listedco/listconews/sehk/2026/1015/x.htm", "filename": "x.pdf"}],
        },
    )
    job = _wait(api, created.json()["job_id"])
    assert job["state"] == "failed"
    assert job["error"]["code"] == "NOT_A_PDF"
    assert api.get(f"/api/downloads/{job['job_id']}/file").status_code == 409


def test_a_client_cannot_make_the_server_fetch_another_site(api: TestClient) -> None:
    created = api.post(
        "/api/downloads",
        json={
            "mode": "single",
            "items": [{"path": "https://evil.example/a.pdf", "filename": "a.pdf"}],
        },
    )
    job = _wait(api, created.json()["job_id"])
    assert job["error"]["code"] == "INVALID_DOCUMENT_PATH"


def test_an_unknown_job_is_a_clear_404(api: TestClient) -> None:
    response = api.get("/api/downloads/nope")
    assert response.status_code == 404
    assert response.json()["message"]


def test_content_check_says_when_it_cannot_read_the_files(api: TestClient) -> None:
    pair = next(a for a in search(api).json()["announcements"] if a["pair_zip_downloadable"])
    body = api.post(
        "/api/content-check", json={"en_path": pair["en"]["path"], "tc_paths": [pair["tc"]["path"]]}
    ).json()
    assert body["available"] is False  # the fixture PDFs are blank pages
    assert "unavailable" in body["message"]


def test_searching_too_often_from_one_address_is_limited(api: TestClient) -> None:
    from app.api import routes

    routes.search_limit._calls.clear()
    codes = [search(api).status_code for _ in range(routes.search_limit._limit + 1)]
    routes.search_limit._calls.clear()
    assert codes[:-1] == [200] * routes.search_limit._limit
    assert codes[-1] == 503

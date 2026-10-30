from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok_and_hong_kong_time() -> None:
    body = TestClient(app).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["time_hkt"].endswith("+08:00")


def test_probe_route_uses_fixed_targets_and_reports_failures() -> None:
    import httpx
    import respx

    with respx.mock:
        respx.get(url__startswith="https://www1.hkexnews.hk/search/").mock(
            side_effect=httpx.ConnectError("blocked"))
        respx.get(url__startswith="https://www1.hkexnews.hk/listedco/").mock(
            return_value=httpx.Response(
                206, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
            )
        )
        body = TestClient(app).get("/api/probe").json()
    assert body["search"]["error"] == "ConnectError"
    assert body["pdf"]["starts_with_pdf_magic"] is True

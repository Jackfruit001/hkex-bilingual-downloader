from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok_and_hong_kong_time() -> None:
    body = TestClient(app).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["time_hkt"].endswith("+08:00")

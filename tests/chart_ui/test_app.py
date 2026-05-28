"""App 啟動與基本路由 smoke test。"""

from fastapi.testclient import TestClient

from src.chart_ui.app import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_no_store_header():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.headers["cache-control"] == "no-store"


def test_index_served():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "台指期 Chart UI" in r.text

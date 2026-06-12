from fastapi.testclient import TestClient

from src.chart_ui.app import create_app


def test_swing_legs_requires_date():
    client = TestClient(create_app())
    r = client.get("/api/swing-legs")
    assert r.status_code == 422  # 缺 required query


def test_swing_legs_bad_date():
    client = TestClient(create_app())
    r = client.get("/api/swing-legs?date=not-a-date")
    assert r.status_code == 400

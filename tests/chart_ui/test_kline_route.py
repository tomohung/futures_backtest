import src.chart_ui.paths as paths
from fastapi.testclient import TestClient

from src.chart_ui.app import create_app


def _client(test_db_path, monkeypatch):
    monkeypatch.setattr(paths, "DUCKDB_PATH", test_db_path)
    return TestClient(create_app())


def test_kline_center_day(test_db_path, monkeypatch):
    client = _client(test_db_path, monkeypatch)
    r = client.get("/api/kline", params={"center": "2025-06-17", "tf": "1m", "session": "day"})
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) > 0
    assert set(bars[0]) == {"time", "open", "high", "low", "close", "volume"}


def test_kline_daily(test_db_path, monkeypatch):
    client = _client(test_db_path, monkeypatch)
    r = client.get("/api/kline", params={"tf": "1d", "session": "day"})
    assert r.status_code == 200
    assert [b["time"] for b in r.json()] == ["2025-06-16", "2025-06-17"]


def test_kline_bad_tf(test_db_path, monkeypatch):
    client = _client(test_db_path, monkeypatch)
    r = client.get("/api/kline", params={"center": "2025-06-17", "tf": "3m"})
    assert r.status_code == 400


def test_kline_empty_center_400(test_db_path, monkeypatch):
    # 空字串 center 應視同未帶 → 400，而非 date.fromisoformat('') 的 500
    client = _client(test_db_path, monkeypatch)
    r = client.get("/api/kline", params={"center": "", "tf": "1m", "session": "day"})
    assert r.status_code == 400

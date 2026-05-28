import json

import pytest
import src.chart_ui.paths as paths
from fastapi.testclient import TestClient

from src.chart_ui.app import create_app
from src.chart_ui.services.list_index import ALL_DAYS_ID


def _client(test_db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DUCKDB_PATH", test_db_path)
    monkeypatch.setattr(paths, "CHART_LISTS_DIR", tmp_path)
    return TestClient(create_app())


def test_list_index(test_db_path, tmp_path, monkeypatch):
    client = _client(test_db_path, tmp_path, monkeypatch)
    r = client.get("/api/lists")
    assert r.status_code == 200
    assert r.json()[0]["id"] == ALL_DAYS_ID


def test_load_all_days(test_db_path, tmp_path, monkeypatch):
    client = _client(test_db_path, tmp_path, monkeypatch)
    r = client.get(f"/api/lists/{ALL_DAYS_ID}")
    assert r.status_code == 200
    assert r.json()["items"][0]["time"] == "2025-06-17 08:45:00"


def test_load_file_list(test_db_path, tmp_path, monkeypatch):
    (tmp_path / "x.json").write_text(json.dumps({"name": "X", "items": [{"time": "2025-06-17 09:00:00"}]}))
    client = _client(test_db_path, tmp_path, monkeypatch)
    r = client.get("/api/lists/x")
    assert r.status_code == 200
    assert r.json()["name"] == "X"


def test_load_missing_404(test_db_path, tmp_path, monkeypatch):
    client = _client(test_db_path, tmp_path, monkeypatch)
    assert client.get("/api/lists/nope").status_code == 404


def test_load_traversal_blocked(test_db_path, tmp_path, monkeypatch):
    # path traversal 的 list_id 應被拒（404），不可讀到 chart_lists 以外的檔
    from src.chart_ui.services.list_index import load_list
    with pytest.raises(FileNotFoundError):
        load_list(tmp_path, test_db_path, "../secret")

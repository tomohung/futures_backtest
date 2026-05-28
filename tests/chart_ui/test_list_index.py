import json

from src.chart_ui.services.list_index import ALL_DAYS_ID, list_lists, load_list


def test_all_days_present_and_default(test_db_path, tmp_path):
    entries = list_lists(tmp_path, test_db_path)
    ids = [e["id"] for e in entries]
    assert ALL_DAYS_ID in ids
    assert ids[0] == ALL_DAYS_ID  # 永遠排第一（預設）


def test_all_days_items(test_db_path, tmp_path):
    data = load_list(tmp_path, test_db_path, ALL_DAYS_ID)
    times = [it["time"] for it in data["items"]]
    # 新到舊；每筆 08:45 開盤
    assert times == ["2025-06-17 08:45:00", "2025-06-16 08:45:00"]


def test_file_list_enumerated_and_loaded(test_db_path, tmp_path):
    (tmp_path / "esthl.json").write_text(json.dumps({
        "name": "EstHL 測試",
        "items": [{"time": "2025-06-17 09:04:00", "side": "long", "pnl_pts": 10}],
    }))
    entries = list_lists(tmp_path, test_db_path)
    esthl = next(e for e in entries if e["id"] == "esthl")
    assert esthl["name"] == "EstHL 測試"
    assert esthl["count"] == 1

    data = load_list(tmp_path, test_db_path, "esthl")
    assert data["items"][0]["time"] == "2025-06-17 09:04:00"


def test_load_missing_raises(test_db_path, tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_list(tmp_path, test_db_path, "nope")

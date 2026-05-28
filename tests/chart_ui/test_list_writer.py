import json

import pandas as pd

from src.chart_ui.list_writer import (
    write_chart_list, write_chart_list_from_backtesting,
)


def test_write_chart_list_basic(tmp_path):
    path = write_chart_list(
        "esthl-2025",
        items=[{"time": "2025-06-17 09:04:00", "side": "long", "pnl_pts": 10}],
        out_dir=tmp_path,
        name="EstHL 2025",
        strategy="S001-esthl",
    )
    data = json.loads(path.read_text())
    assert data["name"] == "EstHL 2025"
    assert data["strategy"] == "S001-esthl"
    assert data["items"][0]["time"] == "2025-06-17 09:04:00"


def test_from_backtesting_maps_columns(tmp_path):
    df = pd.DataFrame({
        "Size": [1, -1],
        "EntryPrice": [26106.0, 23851.0],
        "ExitPrice": [26048.0, 23904.0],
        "PnL": [-58.0, 53.0],
        "ReturnPct": [-0.0022, 0.0022],
        "EntryTime": ["2025-09-23 09:04:00", "2025-01-07 09:20:00"],
        "ExitTime": ["2025-09-23 09:21:00", "2025-01-07 10:29:00"],
        "Tag": [None, None],
    })
    path = write_chart_list_from_backtesting(df, "orb", out_dir=tmp_path, name="ORB")
    data = json.loads(path.read_text())
    it = data["items"][0]
    assert it["time"] == "2025-09-23 09:04:00"
    assert it["exit_time"] == "2025-09-23 09:21:00"
    assert it["side"] == "long"
    assert it["entry"] == 26106.0
    assert it["pnl_pts"] == -58.0
    assert data["items"][1]["side"] == "short"
    # summary 自動算
    assert data["summary"]["trades"] == 2
    assert data["summary"]["pnl_pts"] == -5.0

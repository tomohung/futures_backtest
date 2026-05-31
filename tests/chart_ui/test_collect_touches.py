import duckdb
from datetime import date
from src.chart_ui.services.daystats import _collect_touches


def test_collect_touches_bull_levels(test_db_path):
    con = duckdb.connect(str(test_db_path), read_only=True)
    out = _collect_touches(con, date(2025, 6, 17), [("L1", 1.0), ("L2", 2.0), ("L3", 3.0)])
    con.close()
    assert "bull" in out and "bear" in out
    labels = [t["level"] for t in out["bull"]]
    assert labels == ["L1", "L2", "L3"]
    assert all("price" in t and "time" in t for t in out["bull"])
    mins = [t["minute"] for t in out["bull"]]
    assert mins == sorted(mins)

from datetime import date
import duckdb
import pytest
from src.chart_ui.services.dci_daily import compute_daily_dci, TOP_WEIGHT_SYMBOLS


def _db(tmp_path):
    p = tmp_path / "dci.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE market_breadth (trade_date DATE, market VARCHAR, "
                "listed_count INT, up_count INT, down_count INT, total_value BIGINT)")
    con.execute("CREATE TABLE stock_day (trade_date DATE, market VARCHAR, symbol VARCHAR, "
                "open DECIMAL(12,4), close DECIMAL(12,4), change DECIMAL(12,4), value BIGINT)")
    con.execute("INSERT INTO market_breadth VALUES "
                "(DATE '2026-05-21','TWSE',1000,700,200,1000000)")
    # 強多日：每檔兩票（close>prev 且 close>open）皆 +1 → W=H=1.0。
    rows = []
    for s in TOP_WEIGHT_SYMBOLS[:5]:
        rows.append(f"(DATE '2026-05-21','TWSE','{s}',100.0,110.0,10.0,9000000000)")
    for i in range(20):
        rows.append(f"(DATE '2026-05-21','TWSE','H{i:03d}',100.0,105.0,5.0,99000000000)")
    con.execute("INSERT INTO stock_day VALUES " + ",".join(rows))
    con.close()
    return p


def test_dci_strong_bull_day(tmp_path):
    con = duckdb.connect(str(_db(tmp_path)), read_only=True)
    r = compute_daily_dci(con, date(2026, 5, 21))
    con.close()
    assert r is not None
    assert r["B"] == pytest.approx(0.5)
    assert r["W"] == pytest.approx(1.0)
    assert r["H"] == pytest.approx(1.0)
    assert r["dci_long"] == pytest.approx(0.40 * 1.0 + 0.35 * 1.0 + 0.25 * 0.5)
    assert r["regime_long"] == "strong"


def test_dci_none_when_no_breadth(tmp_path):
    p = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE market_breadth (trade_date DATE, market VARCHAR, "
                "listed_count INT, up_count INT, down_count INT, total_value BIGINT)")
    con.execute("CREATE TABLE stock_day (trade_date DATE, market VARCHAR, symbol VARCHAR, "
                "open DECIMAL(12,4), close DECIMAL(12,4), change DECIMAL(12,4), value BIGINT)")
    con.close()
    con = duckdb.connect(str(p), read_only=True)
    assert compute_daily_dci(con, date(2026, 5, 21)) is None
    con.close()

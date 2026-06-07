"""Tests for src/etl/download_stock_min.py — 純函式，離線不打 API。"""
import duckdb
import pandas as pd
import pytest
from datetime import date, time

from src.etl import download_stock_min as mod


@pytest.fixture
def conn(tmp_path):
    """每個測試一個獨立可寫 duckdb，含最小 stock_day 樣本。"""
    db = tmp_path / "t.duckdb"
    c = duckdb.connect(str(db))
    c.execute("""
        CREATE TABLE stock_day (
            trade_date DATE, market VARCHAR, symbol VARCHAR, name VARCHAR,
            open DECIMAL(12,4), high DECIMAL(12,4), low DECIMAL(12,4),
            close DECIMAL(12,4), volume BIGINT
        )
    """)
    c.execute("""
        INSERT INTO stock_day
        (trade_date, market, symbol, name, open, high, low, close, volume) VALUES
        ('2025-06-16','TWSE','2330','台積電',1000,1010,995,1005,30000),
        ('2025-06-16','TWSE','2317','鴻海',150,152,149,151,20000),
        ('2025-06-16','TPEX','5483','中美晶',180,183,179,182,5000),
        ('2025-06-17','TWSE','2330','台積電',1005,1015,1000,1012,28000)
    """)
    yield c
    c.close()


def test_ensure_schema_creates_tables(conn):
    mod.ensure_schema(conn)
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert "stock_min" in tables
    assert "stock_min_progress" in tables


def test_stock_min_columns(conn):
    mod.ensure_schema(conn)
    cols = {r[0] for r in conn.execute("DESCRIBE stock_min").fetchall()}
    assert {"trade_date", "stock_id", "minute", "open", "high",
            "low", "close", "volume"}.issubset(cols)


def test_trading_days_range(conn):
    days = mod.trading_days(conn, date(2025, 6, 16), date(2025, 6, 17))
    assert days == [date(2025, 6, 16), date(2025, 6, 17)]


def test_trading_days_filters_range(conn):
    days = mod.trading_days(conn, date(2025, 6, 17), date(2025, 6, 17))
    assert days == [date(2025, 6, 17)]


def test_universe_for_day_both_markets(conn):
    univ = mod.universe_for_day(conn, date(2025, 6, 16))
    assert set(univ) == {"2330", "2317", "5483"}


def test_universe_for_day_market_filter(conn):
    univ = mod.universe_for_day(conn, date(2025, 6, 16), market="TWSE")
    assert set(univ) == {"2330", "2317"}


def test_universe_sorted(conn):
    univ = mod.universe_for_day(conn, date(2025, 6, 16))
    assert univ == sorted(univ)


def test_normalize_kbar_maps_columns():
    raw = pd.DataFrame([
        {"date": "2025-06-16", "minute": "09:00:00", "stock_id": "2330",
         "open": 1000.0, "high": 1010.0, "low": 995.0, "close": 1005.0, "volume": 1100},
        {"date": "2025-06-16", "minute": "09:01:00", "stock_id": "2330",
         "open": 1005.0, "high": 1006.0, "low": 1004.0, "close": 1005.0, "volume": 50},
    ])
    out = mod.normalize_kbar(raw, date(2025, 6, 16))
    assert list(out.columns) == ["trade_date", "stock_id", "minute",
                                 "open", "high", "low", "close", "volume"]
    assert out["trade_date"].iloc[0] == date(2025, 6, 16)
    assert out["minute"].iloc[0] == time(9, 0, 0)
    assert out["stock_id"].iloc[0] == "2330"
    assert len(out) == 2


def test_normalize_kbar_empty():
    out = mod.normalize_kbar(pd.DataFrame(), date(2025, 6, 16))
    assert list(out.columns) == ["trade_date", "stock_id", "minute",
                                 "open", "high", "low", "close", "volume"]
    assert len(out) == 0


def _sample_min_df(d):
    return pd.DataFrame([
        {"date": str(d), "minute": "09:00:00", "stock_id": "2330",
         "open": 1000.0, "high": 1010.0, "low": 995.0, "close": 1005.0, "volume": 1100},
        {"date": str(d), "minute": "09:01:00", "stock_id": "2317",
         "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5, "volume": 800},
    ])


def test_write_day_inserts(conn):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)
    norm = mod.normalize_kbar(_sample_min_df(d), d)
    n = mod.write_day(conn, d, norm)
    assert n == 2
    cnt = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 2


def test_write_day_idempotent(conn):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)
    norm = mod.normalize_kbar(_sample_min_df(d), d)
    mod.write_day(conn, d, norm)
    mod.write_day(conn, d, norm)  # 重跑同日不應重複
    cnt = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 2


def test_write_day_only_deletes_target_day(conn):
    mod.ensure_schema(conn)
    d1, d2 = date(2025, 6, 16), date(2025, 6, 17)
    mod.write_day(conn, d1, mod.normalize_kbar(_sample_min_df(d1), d1))
    mod.write_day(conn, d2, mod.normalize_kbar(_sample_min_df(d2), d2))
    mod.write_day(conn, d2, mod.normalize_kbar(_sample_min_df(d2), d2))  # 重寫 d2
    cnt1 = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d1]).fetchone()[0]
    assert cnt1 == 2  # d1 不受影響

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

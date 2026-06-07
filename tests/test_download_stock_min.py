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


def test_normalize_kbar_dedups_pk():
    # FinMind 舊資料同一分鐘重複 print（OHLC 同、volume 微差）→ 須對 PK 去重，避免 PK 衝突
    raw = pd.DataFrame([
        {"date": "2021-01-04", "minute": "09:00:00", "stock_id": "0050",
         "open": 122.2, "high": 122.2, "low": 122.05, "close": 122.15, "volume": 227},
        {"date": "2021-01-04", "minute": "09:00:00", "stock_id": "0050",
         "open": 122.2, "high": 122.2, "low": 122.05, "close": 122.15, "volume": 229},
        {"date": "2021-01-04", "minute": "09:01:00", "stock_id": "0050",
         "open": 122.2, "high": 122.3, "low": 122.1, "close": 122.25, "volume": 50},
    ])
    out = mod.normalize_kbar(raw, date(2021, 1, 4))
    assert len(out) == 2  # 去重後剩 09:00 + 09:01
    nine = out[out["minute"] == time(9, 0, 0)]
    assert len(nine) == 1
    assert nine["volume"].iloc[0] == 229  # keep="last"


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


def test_record_progress_upsert(conn):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)
    mod.record_progress(conn, d, expected=3, fetched=2, failed=1, n_rows=10, status="partial")
    row = conn.execute(
        "SELECT expected, fetched, failed, n_rows, status FROM stock_min_progress WHERE trade_date=?",
        [d],
    ).fetchone()
    assert row == (3, 2, 1, 10, "partial")
    # 重跑同日覆蓋（upsert）
    mod.record_progress(conn, d, expected=3, fetched=3, failed=0, n_rows=15, status="complete")
    row = conn.execute(
        "SELECT fetched, failed, status FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row == (3, 0, "complete")
    cnt = conn.execute("SELECT COUNT(*) FROM stock_min_progress WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 1  # 不重複


def test_pending_days_skips_complete(conn):
    mod.ensure_schema(conn)
    d1, d2 = date(2025, 6, 16), date(2025, 6, 17)
    mod.record_progress(conn, d1, expected=3, fetched=3, failed=0, n_rows=15, status="complete")
    pend = mod.pending_days(conn, [d1, d2])
    assert pend == [d2]


def test_pending_days_includes_partial(conn):
    mod.ensure_schema(conn)
    d1 = date(2025, 6, 16)
    mod.record_progress(conn, d1, expected=3, fetched=2, failed=1, n_rows=10, status="partial")
    pend = mod.pending_days(conn, [d1])
    assert pend == [d1]  # partial 要重跑


def test_fetch_kbar_day_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_loader_call(stock_id_list, date, use_async):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("rate limit")
        return pd.DataFrame([
            {"date": date, "minute": "09:00:00", "stock_id": "2330",
             "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}
        ])

    monkeypatch.setattr(mod, "_kbar_call", fake_loader_call)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)  # 不真的睡
    df = mod.fetch_kbar_day(["2330"], "2025-06-16", max_retries=3)
    assert calls["n"] == 2
    assert len(df) == 1


def test_fetch_kbar_day_gives_up(monkeypatch):
    def always_fail(stock_id_list, date, use_async):
        raise RuntimeError("down")

    monkeypatch.setattr(mod, "_kbar_call", always_fail)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        mod.fetch_kbar_day(["2330"], "2025-06-16", max_retries=2)


def test_download_day_writes_and_records(conn, monkeypatch):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)

    def fake_fetch(stock_ids, ds, **kw):
        return _sample_min_df(d)  # 回 2330 + 2317 兩檔

    monkeypatch.setattr(mod, "fetch_kbar_day", fake_fetch)
    mod.download_day(conn, d, market="TWSE")

    cnt = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 2
    row = conn.execute(
        "SELECT expected, fetched, status FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row[0] == 2          # TWSE 宇宙 = 2330,2317
    assert row[2] == "complete"


def test_normalize_kbar_none_input():
    out = mod.normalize_kbar(None, date(2025, 6, 16))
    assert list(out.columns) == mod.STOCK_MIN_COLS
    assert len(out) == 0


def test_download_day_records_partial_on_fetch_failure(conn, monkeypatch):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)

    def raise_on_fetch(stock_ids, ds, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(mod, "fetch_kbar_day", raise_on_fetch)
    mod.download_day(conn, d, market="TWSE")

    row = conn.execute(
        "SELECT status, fetched FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row[0] == "partial"
    assert row[1] == 0
    cnt = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 0


def test_download_day_empty_universe_complete(conn, monkeypatch):
    mod.ensure_schema(conn)
    d = date(2099, 1, 1)  # 無 stock_day 資料的未來日期

    fetch_called = {"n": 0}

    def should_not_be_called(stock_ids, ds, **kw):
        fetch_called["n"] += 1
        raise AssertionError("fetch_kbar_day should not be called for empty universe")

    monkeypatch.setattr(mod, "fetch_kbar_day", should_not_be_called)
    mod.download_day(conn, d)

    assert fetch_called["n"] == 0
    row = conn.execute(
        "SELECT status, expected FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row[0] == "complete"
    assert row[1] == 0


def test_download_day_partial_when_fetch_incomplete(conn, monkeypatch):
    # 宇宙 2 檔（2330,2317）但只取得 1 檔 → 不可記 complete（否則靜默資料遺失、不重試）
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)

    def partial_fetch(stock_ids, ds, **kw):
        return pd.DataFrame([
            {"date": str(d), "minute": "09:00:00", "stock_id": "2330",
             "open": 1000.0, "high": 1010.0, "low": 995.0, "close": 1005.0, "volume": 100},
        ])

    monkeypatch.setattr(mod, "fetch_kbar_day", partial_fetch)
    fetched, expected = mod.download_day(conn, d, market="TWSE")
    assert (fetched, expected) == (1, 2)
    row = conn.execute(
        "SELECT status, fetched, failed FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row[0] == "partial"
    assert row[1] == 1 and row[2] == 1
    # partial 日不可被 pending_days 跳過（必須會重抓）
    assert d in mod.pending_days(conn, [d])


def test_download_day_zero_fetch_is_partial(conn, monkeypatch):
    # fetch 回空（撞 rate limit 的樣態）→ partial，不可 complete
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)
    monkeypatch.setattr(mod, "fetch_kbar_day",
                        lambda *a, **k: pd.DataFrame())
    fetched, expected = mod.download_day(conn, d, market="TWSE")
    assert fetched == 0 and expected == 2
    status = conn.execute(
        "SELECT status FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()[0]
    assert status == "partial"

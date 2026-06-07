"""Tests for src/etl/download_stock_min.py + load_stock_min.py — 離線、不打 API。"""
import duckdb
import pandas as pd
import pytest
from datetime import date, time

from src.etl import download_stock_min as mod
from src.etl import load_stock_min as loader


# ---------------------------------------------------------------------------
# normalize_kbar
# ---------------------------------------------------------------------------

def test_normalize_kbar_maps_columns():
    raw = pd.DataFrame([
        {"date": "2025-06-16", "minute": "09:00:00", "stock_id": "2330",
         "open": 1000.0, "high": 1010.0, "low": 995.0, "close": 1005.0, "volume": 1100},
        {"date": "2025-06-16", "minute": "09:01:00", "stock_id": "2330",
         "open": 1005.0, "high": 1006.0, "low": 1004.0, "close": 1005.0, "volume": 50},
    ])
    out = mod.normalize_kbar(raw, date(2025, 6, 16))
    assert list(out.columns) == mod.STOCK_MIN_COLS
    assert out["trade_date"].iloc[0] == date(2025, 6, 16)
    assert out["minute"].iloc[0] == time(9, 0, 0)
    assert out["stock_id"].iloc[0] == "2330"
    assert len(out) == 2


def test_normalize_kbar_empty():
    out = mod.normalize_kbar(pd.DataFrame(), date(2025, 6, 16))
    assert list(out.columns) == mod.STOCK_MIN_COLS
    assert len(out) == 0


def test_normalize_kbar_none_input():
    out = mod.normalize_kbar(None, date(2025, 6, 16))
    assert list(out.columns) == mod.STOCK_MIN_COLS
    assert len(out) == 0


def test_normalize_kbar_dedups_pk():
    # FinMind 舊資料同一分鐘重複 print（OHLC 同、volume 微差）→ 須對 PK 去重
    raw = pd.DataFrame([
        {"date": "2021-01-04", "minute": "09:00:00", "stock_id": "0050",
         "open": 122.2, "high": 122.2, "low": 122.05, "close": 122.15, "volume": 227},
        {"date": "2021-01-04", "minute": "09:00:00", "stock_id": "0050",
         "open": 122.2, "high": 122.2, "low": 122.05, "close": 122.15, "volume": 229},
        {"date": "2021-01-04", "minute": "09:01:00", "stock_id": "0050",
         "open": 122.2, "high": 122.3, "low": 122.1, "close": 122.25, "volume": 50},
    ])
    out = mod.normalize_kbar(raw, date(2021, 1, 4))
    assert len(out) == 2
    nine = out[out["minute"] == time(9, 0, 0)]
    assert len(nine) == 1
    assert nine["volume"].iloc[0] == 229  # keep="last"


# ---------------------------------------------------------------------------
# fetch_kbar_day（monkeypatch 接縫，不打網路）
# ---------------------------------------------------------------------------

def test_fetch_kbar_day_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake(stock_id_list, date, use_async):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("rate limit")
        return pd.DataFrame([
            {"date": date, "minute": "09:00:00", "stock_id": "2330",
             "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}
        ])

    monkeypatch.setattr(mod, "_kbar_call", fake)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    df = mod.fetch_kbar_day(["2330"], "2025-06-16", max_retries=3)
    assert calls["n"] == 2
    assert len(df) == 1


def test_fetch_kbar_day_gives_up(monkeypatch):
    monkeypatch.setattr(mod, "_kbar_call",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        mod.fetch_kbar_day(["2330"], "2025-06-16", max_retries=2)


# ---------------------------------------------------------------------------
# write_day_parquet + download_day（檔案版）
# ---------------------------------------------------------------------------

def _sample_norm(d):
    return mod.normalize_kbar(pd.DataFrame([
        {"date": str(d), "minute": "09:00:00", "stock_id": "2330",
         "open": 1000.0, "high": 1010.0, "low": 995.0, "close": 1005.0, "volume": 100},
        {"date": str(d), "minute": "09:00:00", "stock_id": "2317",
         "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5, "volume": 80},
    ]), d)


def test_write_day_parquet_roundtrip(tmp_path):
    d = date(2025, 6, 16)
    out = mod.write_day_parquet(d, _sample_norm(d), raw_dir=tmp_path)
    assert out.exists()
    assert out.name == "2025-06-16.parquet"
    back = duckdb.connect().execute(f"SELECT * FROM read_parquet('{out}')").df()
    assert len(back) == 2
    assert set(back["stock_id"]) == {"2330", "2317"}


def test_download_day_complete_writes_parquet(tmp_path, monkeypatch):
    d = date(2025, 6, 16)
    monkeypatch.setattr(mod, "fetch_kbar_day",
                        lambda ids, ds, **k: pd.DataFrame([
                            {"date": ds, "minute": "09:00:00", "stock_id": "2330",
                             "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1},
                            {"date": ds, "minute": "09:00:00", "stock_id": "2317",
                             "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0, "volume": 2},
                        ]))
    fetched, expected = mod.download_day(d, ["2330", "2317"], raw_dir=tmp_path)
    assert (fetched, expected) == (2, 2)
    assert mod.day_path(d, tmp_path).exists()


def test_download_day_partial_no_file(tmp_path, monkeypatch):
    # 宇宙 2 檔但只回 1 檔 → 不寫檔（留待重抓）
    d = date(2025, 6, 16)
    monkeypatch.setattr(mod, "fetch_kbar_day",
                        lambda ids, ds, **k: pd.DataFrame([
                            {"date": ds, "minute": "09:00:00", "stock_id": "2330",
                             "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1},
                        ]))
    fetched, expected = mod.download_day(d, ["2330", "2317"], raw_dir=tmp_path)
    assert (fetched, expected) == (1, 2)
    assert not mod.day_path(d, tmp_path).exists()


def test_download_day_empty_fetch_no_file(tmp_path, monkeypatch):
    # fetch 回空（撞 rate limit 樣態）→ 不寫檔
    d = date(2025, 6, 16)
    monkeypatch.setattr(mod, "fetch_kbar_day", lambda *a, **k: pd.DataFrame())
    fetched, expected = mod.download_day(d, ["2330", "2317"], raw_dir=tmp_path)
    assert fetched == 0 and expected == 2
    assert not mod.day_path(d, tmp_path).exists()


def test_download_day_fetch_error_no_file(tmp_path, monkeypatch):
    d = date(2025, 6, 16)
    monkeypatch.setattr(mod, "fetch_kbar_day",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    fetched, expected = mod.download_day(d, ["2330", "2317"], raw_dir=tmp_path)
    assert fetched == 0 and expected == 2
    assert not mod.day_path(d, tmp_path).exists()


# ---------------------------------------------------------------------------
# load_universe_map（一次讀 DB；monkeypatch DB_PATH 指向 tmp 庫）
# ---------------------------------------------------------------------------

@pytest.fixture
def stock_day_db(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    c = duckdb.connect(str(db))
    c.execute("CREATE TABLE stock_day (trade_date DATE, market VARCHAR, symbol VARCHAR)")
    c.execute("""
        INSERT INTO stock_day VALUES
        ('2025-06-16','TWSE','2330'), ('2025-06-16','TWSE','2317'),
        ('2025-06-16','TPEX','5483'), ('2025-06-17','TWSE','2330')
    """)
    c.close()
    monkeypatch.setattr(mod, "DB_PATH", db)
    return db


def test_load_universe_map_all_markets(stock_day_db):
    umap = mod.load_universe_map(date(2025, 6, 16), date(2025, 6, 17))
    assert set(umap[date(2025, 6, 16)]) == {"2330", "2317", "5483"}
    assert umap[date(2025, 6, 17)] == ["2330"]


def test_load_universe_map_market_filter(stock_day_db):
    umap = mod.load_universe_map(date(2025, 6, 16), date(2025, 6, 16), market="TWSE")
    assert set(umap[date(2025, 6, 16)]) == {"2330", "2317"}


# ---------------------------------------------------------------------------
# load_stock_min（phase 2：parquet → DuckDB）
# ---------------------------------------------------------------------------

def test_loader_builds_table(tmp_path):
    raw = tmp_path / "raw"
    for d in (date(2025, 6, 16), date(2025, 6, 17)):
        mod.write_day_parquet(d, _sample_norm(d), raw_dir=raw)
    db = tmp_path / "out.duckdb"
    st = loader.load(db, raw)
    assert st["files"] == 2 and st["days"] == 2 and st["rows"] == 4
    with duckdb.connect(str(db), read_only=True) as c:
        assert c.execute("SELECT COUNT(*) FROM stock_min").fetchone()[0] == 4


def test_wait_for_budget_waits_then_proceeds(monkeypatch):
    # 真實用量先不足、再恢復 → 應先等待再返回
    usages = iter([5900, 5900, 1000])  # 前兩次剩 100<need+margin，第三次充足
    monkeypatch.setattr(mod, "_api_usage", lambda: next(usages))
    slept = {"n": 0}
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.__setitem__("n", slept["n"] + 1))
    mod.wait_for_budget(need=1000, poll_sec=1)
    assert slept["n"] == 2  # 等了兩輪才夠


def test_wait_for_budget_enough_no_wait(monkeypatch):
    monkeypatch.setattr(mod, "_api_usage", lambda: 100)
    monkeypatch.setattr(mod.time, "sleep",
                        lambda s: (_ for _ in ()).throw(AssertionError("不該等待")))
    mod.wait_for_budget(need=1000)  # 100 用量、剩 5900 足夠 → 不等


def test_loader_idempotent(tmp_path):
    raw = tmp_path / "raw"
    mod.write_day_parquet(date(2025, 6, 16), _sample_norm(date(2025, 6, 16)), raw_dir=raw)
    db = tmp_path / "out.duckdb"
    loader.load(db, raw)
    loader.load(db, raw)  # 重跑全量重建，不重複
    with duckdb.connect(str(db), read_only=True) as c:
        assert c.execute("SELECT COUNT(*) FROM stock_min").fetchone()[0] == 2

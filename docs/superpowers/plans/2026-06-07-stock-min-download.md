# 全市場個股分 k 下載 pipeline 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `src/etl/download_stock_min.py`，用 FinMind 官方 SDK 把全市場（上市+上櫃）2021–2026 個股分 k 回補進新表 `stock_min`，逐日冪等、可續傳。

**Architecture:** 純函式（schema/宇宙查詢/normalize/寫入/ledger/續傳）可離線用 fixture DuckDB 做 TDD；唯一的網路抓取層 `fetch_kbar_day()` 包 FinMind SDK + backoff，測試時 monkeypatch。逐交易日 loop：取 `stock_day` 當日宇宙 → SDK async 抓 → 以日為單位 DELETE+INSERT → 寫 `stock_min_progress` ledger。已完成日跳過。

**Tech Stack:** Python 3.12+、DuckDB、pandas、FinMind SDK（新增相依）、pytest。

參考 spec：`docs/superpowers/specs/2026-06-07-stock-min-download-design.md`

---

## File Structure

- **Create** `src/etl/download_stock_min.py` — 下載 pipeline（schema + 純函式 + 抓取層 + main）
- **Modify** `pyproject.toml` — 新增 `FinMind` 相依
- **Create** `tests/test_download_stock_min.py` — 純函式單元測試（離線、不打 API；自帶 tmp_path duckdb fixture，不依賴 conftest）

模組內函式邊界：
- `ensure_schema(conn)` — 建 `stock_min` + `stock_min_progress`
- `trading_days(conn, start, end)` — 區間內 `stock_day` 的 distinct trade_date
- `universe_for_day(conn, d)` — 當日 distinct symbols
- `pending_days(conn, days)` — 濾掉 ledger 已 `complete` 的日
- `normalize_kbar(df, d)` — FinMind df → stock_min 欄位/型別
- `write_day(conn, d, df)` — DELETE WHERE trade_date=d → INSERT，回傳 n_rows
- `record_progress(conn, d, expected, fetched, failed, n_rows, status)` — ledger upsert
- `fetch_kbar_day(stock_ids, d, token)` — 唯一網路層（SDK + backoff）
- `download_day(conn, d, token)` — 串一天
- `main()` — argparse + loop

---

## Task 1: 新增 FinMind 相依

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 加入相依**

Run:
```bash
uv add FinMind
```
Expected: `pyproject.toml` 的 `dependencies` 新增一行 `"finmind>=..."`（或 `FinMind`），`uv.lock` 更新。

- [ ] **Step 2: 驗證可 import**

Run:
```bash
uv run python -c "from FinMind.data import DataLoader; print('ok')"
```
Expected: 印出 `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add FinMind SDK for stock minute download"
```

---

## Task 2: schema 建立

**Files:**
- Create: `src/etl/download_stock_min.py`
- Create: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_download_stock_min.py`：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -q
```
Expected: FAIL — `ModuleNotFoundError` 或 `AttributeError: module has no attribute 'ensure_schema'`

- [ ] **Step 3: 寫最小實作**

建立 `src/etl/download_stock_min.py`：

```python
"""
下載全市場（上市+上櫃）個股分 k（FinMind TaiwanStockKBar）→ DuckDB table `stock_min`。

逐交易日：宇宙取自 stock_day 當日 symbols（含已下市公司，避免 survivorship bias）。
以「日」為冪等單位 DELETE+INSERT；stock_min_progress 記錄完成狀態，可中斷續傳。

dataset TaiwanStockKBar 為 Sponsor 限定，token 取自 env FINMIND_API_KEY。
一個 request = 一檔一天（不接受 end_date）；用官方 SDK use_async 批多檔。

用法：
  uv run python src/etl/download_stock_min.py                       # 預設 2021-01-01 至今
  uv run python src/etl/download_stock_min.py --start 2024-01-01 --end 2024-12-31
  uv run python src/etl/download_stock_min.py --market TWSE          # 只抓上市
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

SCHEMA_STOCK_MIN = """
CREATE TABLE IF NOT EXISTS stock_min (
    trade_date  DATE,
    stock_id    VARCHAR,
    minute      TIME,
    open   DECIMAL(12,4),
    high   DECIMAL(12,4),
    low    DECIMAL(12,4),
    close  DECIMAL(12,4),
    volume BIGINT,
    PRIMARY KEY (trade_date, stock_id, minute)
);
"""

SCHEMA_PROGRESS = """
CREATE TABLE IF NOT EXISTS stock_min_progress (
    trade_date   DATE PRIMARY KEY,
    expected     INTEGER,
    fetched      INTEGER,
    failed       INTEGER,
    n_rows       BIGINT,
    status       VARCHAR,
    fetched_at   TIMESTAMP
);
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_STOCK_MIN)
    conn.execute(SCHEMA_PROGRESS)
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -q
```
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): stock_min schema + ensure_schema"
```

---

## Task 3: 交易日清單 + 當日宇宙查詢

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫失敗測試**

於 `tests/test_download_stock_min.py` 追加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k "trading_days or universe" -q
```
Expected: FAIL — `AttributeError: module has no attribute 'trading_days'`

- [ ] **Step 3: 實作**

於 `src/etl/download_stock_min.py` 的 `ensure_schema` 之後追加：

```python
def trading_days(
    conn: duckdb.DuckDBPyConnection, start: date, end: date
) -> list[date]:
    """區間內 stock_day 出現過的交易日（升冪）。"""
    rows = conn.execute(
        """
        SELECT DISTINCT trade_date
        FROM stock_day
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        [start, end],
    ).fetchall()
    return [r[0] for r in rows]


def universe_for_day(
    conn: duckdb.DuckDBPyConnection, d: date, market: str | None = None
) -> list[str]:
    """當日 stock_day 有成交的 symbols（升冪）。market=None 取全市場。"""
    sql = "SELECT DISTINCT symbol FROM stock_day WHERE trade_date = ?"
    params: list = [d]
    if market:
        sql += " AND market = ?"
        params.append(market)
    sql += " ORDER BY symbol"
    return [r[0] for r in conn.execute(sql, params).fetchall()]
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k "trading_days or universe" -q
```
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): trading_days + universe_for_day queries"
```

---

## Task 4: normalize_kbar（FinMind df → stock_min 欄位/型別）

FinMind 回傳欄位：`date, minute(HH:MM:SS str), stock_id, open, high, low, close, volume`。
轉成 stock_min 欄序與型別（trade_date=DATE、minute=TIME）。

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k normalize -q
```
Expected: FAIL — `AttributeError: ... 'normalize_kbar'`

- [ ] **Step 3: 實作**

追加：

```python
STOCK_MIN_COLS = ["trade_date", "stock_id", "minute",
                  "open", "high", "low", "close", "volume"]


def normalize_kbar(df: pd.DataFrame, d: date) -> pd.DataFrame:
    """FinMind kbar df → stock_min 欄序/型別。空 df 回傳空但欄位齊全。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=STOCK_MIN_COLS)
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["date"]).dt.date
    out["minute"] = pd.to_datetime(out["minute"], format="%H:%M:%S").dt.time
    out["stock_id"] = out["stock_id"].astype(str)
    out["volume"] = out["volume"].fillna(0).astype("int64")
    return out[STOCK_MIN_COLS].reset_index(drop=True)
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k normalize -q
```
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): normalize_kbar transform"
```

---

## Task 5: write_day（日為單位冪等 DELETE+INSERT）

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k write_day -q
```
Expected: FAIL — `AttributeError: ... 'write_day'`

- [ ] **Step 3: 實作**

追加：

```python
def write_day(conn: duckdb.DuckDBPyConnection, d: date, df: pd.DataFrame) -> int:
    """以日為單位刪舊寫新（冪等）。回傳寫入 row 數。"""
    conn.execute("DELETE FROM stock_min WHERE trade_date = ?", [d])
    if len(df):
        conn.register("df_min", df)
        conn.execute(
            f"INSERT INTO stock_min SELECT {', '.join(STOCK_MIN_COLS)} FROM df_min"
        )
        conn.unregister("df_min")
    return len(df)
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k write_day -q
```
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): write_day idempotent per-day write"
```

---

## Task 6: ledger（record_progress + pending_days 續傳）

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k "record_progress or pending" -q
```
Expected: FAIL — `AttributeError: ... 'record_progress'`

- [ ] **Step 3: 實作**

追加：

```python
def record_progress(
    conn: duckdb.DuckDBPyConnection,
    d: date,
    expected: int,
    fetched: int,
    failed: int,
    n_rows: int,
    status: str,
) -> None:
    """ledger upsert（同日覆蓋）。"""
    conn.execute("DELETE FROM stock_min_progress WHERE trade_date = ?", [d])
    conn.execute(
        """
        INSERT INTO stock_min_progress
        (trade_date, expected, fetched, failed, n_rows, status, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, now())
        """,
        [d, expected, fetched, failed, n_rows, status],
    )


def pending_days(
    conn: duckdb.DuckDBPyConnection, days: list[date]
) -> list[date]:
    """過濾掉 ledger 已 status='complete' 的日；其餘（缺/partial）保留。"""
    done = {
        r[0]
        for r in conn.execute(
            "SELECT trade_date FROM stock_min_progress WHERE status = 'complete'"
        ).fetchall()
    }
    return [d for d in days if d not in done]
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k "record_progress or pending" -q
```
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): progress ledger + resume (pending_days)"
```

---

## Task 7: 抓取層 fetch_kbar_day（FinMind SDK + backoff）

唯一的網路層。不寫單元測試打 API（付費）；用 monkeypatch 驗證 backoff 行為。

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫 backoff 行為測試（monkeypatch SDK，不打網路）**

追加：

```python
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
    df = mod.fetch_kbar_day(["2330"], "2025-06-16", token="x", max_retries=3)
    assert calls["n"] == 2
    assert len(df) == 1


def test_fetch_kbar_day_gives_up(monkeypatch):
    def always_fail(stock_id_list, date, use_async):
        raise RuntimeError("down")

    monkeypatch.setattr(mod, "_kbar_call", always_fail)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        mod.fetch_kbar_day(["2330"], "2025-06-16", token="x", max_retries=2)
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k fetch_kbar -q
```
Expected: FAIL — `AttributeError: ... '_kbar_call'` / `'fetch_kbar_day'`

- [ ] **Step 3: 實作**

追加（`_kbar_call` 為薄包 SDK 的接縫，方便 monkeypatch）：

```python
def _kbar_call(stock_id_list: list[str], date: str, use_async: bool) -> pd.DataFrame:
    """薄包 FinMind SDK。隔離成單一接縫供測試 monkeypatch。"""
    from FinMind.data import DataLoader

    token = os.environ["FINMIND_API_KEY"]
    dl = DataLoader()
    dl.login_by_token(api_token=token)
    return dl.taiwan_stock_kbar(
        stock_id_list=stock_id_list, date=date, use_async=use_async
    )


def fetch_kbar_day(
    stock_ids: list[str],
    d: str,
    token: str,
    max_retries: int = 4,
) -> pd.DataFrame:
    """抓單日全宇宙分 k；rate-limit/連線錯誤指數退避重試。最終失敗則 raise。"""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _kbar_call(stock_ids, d, use_async=True)
        except Exception as e:  # noqa: BLE001 — 退避重試所有暫態錯誤
            last_err = e
            time.sleep(2 ** attempt)  # 1,2,4,8...秒
    raise RuntimeError(f"fetch_kbar_day {d} 重試 {max_retries} 次仍失敗: {last_err}")
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k fetch_kbar -q
```
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): fetch_kbar_day with exponential backoff"
```

---

## Task 8: download_day 串接 + main loop

**Files:**
- Modify: `src/etl/download_stock_min.py`
- Modify: `tests/test_download_stock_min.py`

- [ ] **Step 1: 寫 download_day 測試（monkeypatch fetch，不打 API）**

追加：

```python
def test_download_day_writes_and_records(conn, monkeypatch):
    mod.ensure_schema(conn)
    d = date(2025, 6, 16)

    def fake_fetch(stock_ids, ds, token, **kw):
        return _sample_min_df(d)  # 回 2330 + 2317 兩檔

    monkeypatch.setattr(mod, "fetch_kbar_day", fake_fetch)
    mod.download_day(conn, d, token="x", market="TWSE")

    cnt = conn.execute("SELECT COUNT(*) FROM stock_min WHERE trade_date=?", [d]).fetchone()[0]
    assert cnt == 2
    row = conn.execute(
        "SELECT expected, fetched, status FROM stock_min_progress WHERE trade_date=?", [d]
    ).fetchone()
    assert row[0] == 2          # TWSE 宇宙 = 2330,2317
    assert row[2] == "complete"
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -k download_day -q
```
Expected: FAIL — `AttributeError: ... 'download_day'`

- [ ] **Step 3: 實作 download_day + main**

追加：

```python
def download_day(
    conn: duckdb.DuckDBPyConnection,
    d: date,
    token: str,
    market: str | None = None,
) -> None:
    """抓單日 → normalize → 寫入 → 記 ledger。失敗記 partial 不中斷整體。"""
    univ = universe_for_day(conn, d, market)
    expected = len(univ)
    if expected == 0:
        record_progress(conn, d, 0, 0, 0, 0, "complete")
        return
    try:
        raw = fetch_kbar_day(univ, d.isoformat(), token)
    except Exception as e:  # noqa: BLE001
        print(f"  {d} 抓取失敗，記 partial：{e}")
        record_progress(conn, d, expected, 0, expected, 0, "partial")
        return
    norm = normalize_kbar(raw, d)
    n_rows = write_day(conn, d, norm)
    fetched = norm["stock_id"].nunique() if len(norm) else 0
    failed = max(0, expected - fetched)
    record_progress(conn, d, expected, fetched, failed, n_rows, "complete")
    print(f"  {d}: 宇宙{expected} 取得{fetched} rows={n_rows}")


def main() -> None:
    p = argparse.ArgumentParser(description="下載全市場個股分 k（FinMind TaiwanStockKBar）")
    p.add_argument("--start", type=date.fromisoformat, default=date(2021, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    p.add_argument("--market", choices=["TWSE", "TPEX"], default=None,
                   help="預設全市場；指定則只抓單一市場")
    args = p.parse_args()

    token = os.environ.get("FINMIND_API_KEY")
    if not token:
        raise SystemExit("缺 env FINMIND_API_KEY")

    with duckdb.connect(str(DB_PATH)) as conn:
        ensure_schema(conn)
        all_days = trading_days(conn, args.start, args.end)
        todo = pending_days(conn, all_days)
        print(f"交易日 {len(all_days)}，待下載 {len(todo)}（已完成 {len(all_days)-len(todo)} 跳過）")
        for i, d in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {d}")
            download_day(conn, d, token, args.market)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑測試確認通過 + 全測試回歸**

Run:
```bash
uv run pytest tests/test_download_stock_min.py -q && uv run pytest tests/test_etl.py -q
```
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/etl/download_stock_min.py tests/test_download_stock_min.py
git commit -m "feat(etl): download_day orchestration + main loop"
```

---

## Task 9: 真實單日驗收（打 API 一天，人工驗證）

確認端到端對接真實 FinMind 與真實 `data/futures.duckdb`。只跑一天，控制 quota。

**Files:** 無（執行驗證）

- [ ] **Step 1: 選一個近期交易日跑單日下載**

Run:
```bash
uv run python src/etl/download_stock_min.py --start 2026-05-29 --end 2026-05-29
```
Expected: 印出 `交易日 1，待下載 1`，接著 `2026-05-29: 宇宙~2000 取得~1900+ rows=數十萬`

- [ ] **Step 2: 抽樣驗證資料合理**

Run:
```bash
uv run python -c "
import duckdb
c=duckdb.connect('data/futures.duckdb', read_only=True)
print(c.execute('SELECT COUNT(*) rows, COUNT(DISTINCT stock_id) stocks, MIN(minute), MAX(minute) FROM stock_min WHERE trade_date=DATE \'2026-05-29\'').fetchdf().to_string(index=False))
print(c.execute('SELECT * FROM stock_min_progress WHERE trade_date=DATE \'2026-05-29\'').fetchdf().to_string(index=False))
print(c.execute('SELECT * FROM stock_min WHERE trade_date=DATE \'2026-05-29\' AND stock_id=\'2330\' ORDER BY minute LIMIT 3').fetchdf().to_string(index=False))
c.close()
"
```
Expected:
- `stocks` 接近當日 `stock_day` 宇宙數（~2000）
- `minute` 範圍約 09:00–13:30
- `status='complete'`
- 2330 前幾根 OHLCV 數值合理（high≥low）

- [ ] **Step 3: 驗證續傳（重跑同區間應跳過）**

Run:
```bash
uv run python src/etl/download_stock_min.py --start 2026-05-29 --end 2026-05-29
```
Expected: 印出 `待下載 0（已完成 1 跳過）`，不重抓

- [ ] **Step 4: Commit（若無程式改動可略）**

驗收僅執行，無程式變更則不需 commit。若過程中修了 bug，照常 commit。

---

## Task 10: 更新文件（CLAUDE.md schema + 目錄）

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 在 CLAUDE.md「資料庫 Schema」區新增 stock_min 表說明**

於 `ticks_options 表` 區塊之後加入 `stock_min 表`（含 schema、資料來源 FinMind TaiwanStockKBar、ETL 腳本 `src/etl/download_stock_min.py`、上櫃 2021-04-13 起的邊界註記）。

- [ ] **Step 2: 在「目錄結構」的 `src/etl/` 清單加入一行**

```
│   │   ├── download_stock_min.py ← 全市場個股分k下載（FinMind TaiwanStockKBar，DCI 校準用）✅
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document stock_min table + download_stock_min.py"
```

---

## 全量回補（驗收通過後，非本計畫自動步驟）

驗收 OK 後，分段執行全量回補（耗時數十小時，可中斷續傳）：
```bash
# 建議分年跑，過夜執行，可隨時 Ctrl-C 後重跑續傳
uv run python src/etl/download_stock_min.py --start 2021-01-01 --end 2021-12-31
uv run python src/etl/download_stock_min.py --start 2022-01-01 --end 2022-12-31
# ... 2023 / 2024 / 2025 / 2026
```
監看進度：
```bash
uv run python -c "import duckdb; c=duckdb.connect('data/futures.duckdb',read_only=True); print(c.execute(\"SELECT status, COUNT(*), SUM(n_rows) FROM stock_min_progress GROUP BY status\").fetchdf())"
```

---

## 延後項目（後續假設）

- `build_intraday_dci.py`：每分鐘 join 昨收算 W/H/B/DCI_long/DCI_short（H095 研究 Phase）
- DCI 廣度是否納入上櫃、W 權值代理方式 → 看回測
- 每日增量整合進 `daily_update.py`

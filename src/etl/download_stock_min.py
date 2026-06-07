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

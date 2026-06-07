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

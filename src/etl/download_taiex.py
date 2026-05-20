"""
下載 TAIEX 加權指數日線（FinMind TaiwanStockPrice/TAIEX）
                                       → DuckDB table `taiex_day`
                                       → data/external_sources/TAIEX_daily.csv

歷史可追溯：2008-01-02 起（FinMind 涵蓋）。

來源說明：FinMind 公開 endpoint，無需 token，當日收盤後即可取得 T+0 資料。
舊版改用 yfinance ^TWII 常因 T+1 延遲卡住最新交易日 close，2026-05 起改用 FinMind。

冪等：每次重抓覆蓋指定區間。

用法：
  uv run python src/etl/download_taiex.py                      # 預設 2008-01-01 至今
  uv run python src/etl/download_taiex.py --start 2020-01-01
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "external_sources" / "TAIEX_daily.csv"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

SCHEMA_TAIEX = """
CREATE TABLE IF NOT EXISTS taiex_day (
    trade_date   DATE PRIMARY KEY,
    open         DECIMAL(12,2),
    high         DECIMAL(12,2),
    low          DECIMAL(12,2),
    close        DECIMAL(12,2),
    volume       BIGINT
);
"""


def fetch(start: date, end: date) -> pd.DataFrame:
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "TAIEX",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    r = requests.get(FINMIND_URL, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if payload.get("msg") != "success":
        raise RuntimeError(f"FinMind 回傳錯誤：{payload}")
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("FinMind 回傳空資料")
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "date": "trade_date",
        "max": "high",
        "min": "low",
        "Trading_Volume": "volume",
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df[["trade_date", "open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    return df


def write_csv(df: pd.DataFrame) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)


def write_db(df: pd.DataFrame) -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(SCHEMA_TAIEX)
        conn.execute(
            "DELETE FROM taiex_day WHERE trade_date BETWEEN ? AND ?",
            [df["trade_date"].min(), df["trade_date"].max()],
        )
        conn.execute(
            "INSERT INTO taiex_day SELECT * FROM df",
        )
        n = conn.execute("SELECT COUNT(*) FROM taiex_day").fetchone()[0]
        latest = conn.execute(
            "SELECT trade_date, close FROM taiex_day ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
    print(f"DB now has: taiex_day={n}, latest={latest}")


def main() -> None:
    p = argparse.ArgumentParser(description="Download TAIEX daily OHLCV via FinMind")
    p.add_argument("--start", type=date.fromisoformat, default=date(2008, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    print(f"Fetching FinMind TAIEX {args.start} ~ {args.end}")
    df = fetch(args.start, args.end)
    print(f"  Got {len(df)} rows: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    write_csv(df)
    print(f"  CSV → {CSV_PATH}")
    write_db(df)


if __name__ == "__main__":
    main()

"""
下載 TAIEX 加權指數日線（yfinance ^TWII）→ DuckDB table `taiex_day`
                                       → data/external_sources/TAIEX_daily.csv

歷史可追溯：1997 起（yfinance），2008-01 起資料品質穩定。

冪等：每次重抓覆蓋指定區間。

用法：
  uv run python src/etl/download_taiex.py                      # 預設 2008-01-01 至今
  uv run python src/etl/download_taiex.py --start 2020-01-01
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "external_sources" / "TAIEX_daily.csv"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

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
    # yfinance end 是 exclusive，加一天才能拿到最後一天
    raw = yf.download("^TWII", start=start.isoformat(),
                      end=(end + timedelta(days=1)).isoformat(),
                      progress=False, auto_adjust=False)
    if raw.empty:
        raise RuntimeError("yfinance 回傳空資料")
    # MultiIndex columns: ('Open','^TWII') 等 — 攤平
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    df = pd.DataFrame({
        "trade_date": raw.index.date,
        "open": raw["Open"].values,
        "high": raw["High"].values,
        "low": raw["Low"].values,
        "close": raw["Close"].values,
        "volume": raw["Volume"].fillna(0).astype("int64").values,
    })
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def write_csv(df: pd.DataFrame) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)


def write_db(df: pd.DataFrame) -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(SCHEMA_TAIEX)
        # 冪等：先刪指定區間
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
    p = argparse.ArgumentParser(description="Download TAIEX daily OHLCV via yfinance")
    p.add_argument("--start", type=date.fromisoformat, default=date(2008, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    print(f"Fetching ^TWII {args.start} ~ {args.end}")
    df = fetch(args.start, args.end)
    print(f"  Got {len(df)} rows: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    write_csv(df)
    print(f"  CSV → {CSV_PATH}")
    write_db(df)


if __name__ == "__main__":
    main()

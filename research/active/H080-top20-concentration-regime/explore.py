"""H080 Phase 1 Explore — 前 20 權值股集中度的行情分類

從 concentration_index 取 4 個 N 的指標，join TX 日盤 OHLC，跑 1A–1G 各分析。

子假設（GATE 主訊號 = N=20）:
  A) 5 桶 quintile 漲日機率單調且首尾 ≥ 8pp
  B) 5 桶 quintile 平均振幅單調且首尾 ≥ 30%
  C) 27 格中 ≥ 2 格 lift ≥ 80% 且 chi-square p < 0.05
  D) 某 3 桶大跌機率相對 baseline lift ≥ 50%

用法:
  uv run python research/active/H080-top20-concentration-regime/explore.py
  uv run python research/active/H080-top20-concentration-regime/explore.py --start 2018-01-01 --end 2026-05-07
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULT_DIR = Path(__file__).parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

N_VALUES = [1, 5, 10, 20]


DAILY_SQL = """
WITH ci AS (
    SELECT * FROM concentration_index
    WHERE trade_date BETWEEN ? AND ?
),
tx AS (
    SELECT timestamp::DATE AS trade_date,
           FIRST(open  ORDER BY timestamp) AS tx_open,
           LAST(close  ORDER BY timestamp) AS tx_close,
           MAX(high)                       AS tx_high,
           MIN(low)                        AS tx_low
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::DATE BETWEEN ? AND ?
      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
    GROUP BY trade_date
)
SELECT ci.*, tx.tx_open, tx.tx_close, tx.tx_high, tx.tx_low
FROM ci
JOIN tx USING (trade_date)
ORDER BY ci.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end]).fetchdf()
    df["tx_dir"] = (df["tx_close"] - df["tx_open"]) / df["tx_open"]
    df["tx_range"] = (df["tx_high"] - df["tx_low"]) / df["tx_open"]
    df["weekday"] = pd.to_datetime(df["trade_date"]).dt.weekday  # 0=Mon
    return df


# 1A – 1G stub（後續 task 會實作）
def analyze_distribution(df): print("[1A] TODO")
def analyze_quintile_by_N(df): print("[1B] TODO")
def analyze_27grid(df, n=20): print(f"[1C] TODO (N={n})")
def analyze_crash(df, n=20): print(f"[1D] TODO (N={n})")
def analyze_list_changes(df): print("[1E] TODO")
def analyze_correlation_h079(df, s, e): print("[1F] TODO")
def analyze_weekday(df, n=20): print(f"[1G] TODO (N={n})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01", type=date.fromisoformat)
    parser.add_argument("--end", default="2026-05-07", type=date.fromisoformat)
    args = parser.parse_args()

    df = load_daily(args.start, args.end)
    df = df.dropna(subset=["top20_dev_pct"])
    print(f"載入 {len(df)} 個交易日 ({df['trade_date'].min()} ~ {df['trade_date'].max()})")

    df.to_csv(RESULT_DIR / "timeseries.csv", index=False)
    print(f"已輸出: {RESULT_DIR / 'timeseries.csv'}")

    analyze_distribution(df)
    analyze_quintile_by_N(df)
    analyze_27grid(df, n=20)
    analyze_crash(df, n=20)
    analyze_list_changes(df)
    analyze_correlation_h079(df, args.start, args.end)
    analyze_weekday(df, n=20)


if __name__ == "__main__":
    main()

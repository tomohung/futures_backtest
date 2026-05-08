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
import matplotlib.pyplot as plt
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


def analyze_distribution(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1A) 分佈總覽")
    print("=" * 78)
    cols = [f"top{n}_share" for n in N_VALUES] + [f"top{n}_dev_pct" for n in N_VALUES]
    desc = df[cols].describe().T[["mean", "std", "min", "50%", "max"]]
    print(desc.to_string())
    n_changed = df.groupby("list_month")["list_changed"].first().sum()
    n_total = df["list_month"].nunique()
    print(f"\nlist_changed 月份數: {n_changed} / {n_total}")

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    for i, n in enumerate(N_VALUES):
        axes[0, i].hist(df[f"top{n}_share"].dropna(), bins=50, color="steelblue", edgecolor="white")
        axes[0, i].set_title(f"N={n} share %")
        axes[1, i].hist(df[f"top{n}_dev_pct"].dropna(), bins=50, color="darkorange", edgecolor="white")
        axes[1, i].set_title(f"N={n} dev_pct %")
        axes[1, i].axvline(0, color="black", lw=0.5)
    fig.tight_layout()
    fig.savefig(RESULT_DIR / "distribution_overview.png", dpi=120)
    plt.close(fig)
    print(f"已輸出: {RESULT_DIR / 'distribution_overview.png'}")


def analyze_quintile_by_N(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1B) 5 桶 quintile 邊際分析（4 個 N）")
    print("=" * 78)

    rows = []
    for n in N_VALUES:
        sig = df[f"top{n}_dev_pct"]
        df[f"q{n}"] = pd.qcut(sig, 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
        for q in [1, 2, 3, 4, 5]:
            mask = df[f"q{n}"] == q
            sub = df[mask]
            if len(sub) == 0:
                continue
            rows.append({
                "N": n, "quintile": q, "n": len(sub),
                "share_mean": sub[f"top{n}_share"].mean(),
                "dev_pct_mean": sub[f"top{n}_dev_pct"].mean(),
                "tx_dir_mean": sub["tx_dir"].mean(),
                "tx_range_mean": sub["tx_range"].mean(),
                "p_up": (sub["tx_dir"] > 0).mean(),
                "p_down": (sub["tx_dir"] < 0).mean(),
            })
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "A_quintile_by_N.csv", index=False)
    print(res.to_string(index=False))

    print("\n--- GATE 評估 (主訊號 N=20) ---")
    for n in N_VALUES:
        sub = res[res["N"] == n].sort_values("quintile")
        if len(sub) < 5:
            continue
        pp_diff = (sub["p_up"].iloc[-1] - sub["p_up"].iloc[0]) * 100
        range_diff = (sub["tx_range_mean"].iloc[-1] / sub["tx_range_mean"].iloc[0] - 1) * 100
        mono_up = sub["p_up"].is_monotonic_increasing or sub["p_up"].is_monotonic_decreasing
        mono_range = sub["tx_range_mean"].is_monotonic_increasing or sub["tx_range_mean"].is_monotonic_decreasing
        gate1 = abs(pp_diff) >= 8 and mono_up
        gate2 = abs(range_diff) >= 30 and mono_range
        marker = " <- GATE" if n == 20 else ""
        print(f"N={n:>2}: p_up Q5-Q1 = {pp_diff:+6.2f}pp  mono={mono_up}  GATE-1={gate1}{marker}")
        print(f"      range Q5/Q1-1 = {range_diff:+6.1f}%   mono={mono_range}  GATE-2={gate2}{marker}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for n in N_VALUES:
        sub = res[res["N"] == n].sort_values("quintile")
        axes[0].plot(sub["quintile"], sub["p_up"] * 100, marker="o", label=f"N={n}")
        axes[1].plot(sub["quintile"], sub["tx_range_mean"] * 100, marker="o", label=f"N={n}")
    axes[0].set_title("漲日機率 vs quintile (4 個 N)")
    axes[0].set_xlabel("quintile (1=低集中度, 5=高)")
    axes[0].set_ylabel("p_up %")
    axes[0].axhline(50, color="gray", lw=0.5, linestyle="--")
    axes[0].legend()
    axes[1].set_title("平均振幅 vs quintile (4 個 N)")
    axes[1].set_xlabel("quintile")
    axes[1].set_ylabel("range %")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(RESULT_DIR / "A_quintile_by_N.png", dpi=120)
    plt.close(fig)
    print(f"\n已輸出: {RESULT_DIR / 'A_quintile_by_N.png'}")


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

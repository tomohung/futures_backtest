"""H079-B Phase 2 Backtest

Hypothesis (回顧)
------------------
LC-HV（低漲停家數 + 高漲停成交額占比）= 資金集中在大公司，後續 5/10/20 日報酬偏弱
但最大回撤無差異 → 是「停滯訊號」非「崩跌訊號」。

兩個策略
--------
C1: Standalone 隔日做空（純驗證訊號 alpha）
    - LC-HV 日收盤後 → 隔日 08:45 開盤做空 → 13:45 收盤平倉
C3: Long-hold + LC-HV 跳過（停利型 regime filter）
    - Baseline: 每日 08:45 多單 → 13:45 平倉（always-long 日盤）
    - 變體: 前一日為 LC-HV → 當日不進場

成本: 6 點 round-trip (2 手續費 + 1 滑價，雙邊)
績效標準化: 損益% = 損益點數 / 進場價 × 100
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULT_DIR = Path(__file__).parent / "results"

ROUND_TRIP_COST = 6.0  # 點


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

DAILY_SQL = """
WITH b AS (
    SELECT trade_date,
           SUM(up_limit_count) AS up_limit_count,
           SUM(total_value)    AS total_value
    FROM market_breadth
    WHERE trade_date BETWEEN ? AND ?
    GROUP BY trade_date
),
lv AS (
    SELECT trade_date,
           SUM(CASE WHEN is_limit_up THEN value ELSE 0 END) AS lu_value
    FROM stock_day
    WHERE trade_date BETWEEN ? AND ?
    GROUP BY trade_date
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
SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value,
       tx.tx_open, tx.tx_high, tx.tx_low, tx.tx_close
FROM b LEFT JOIN lv USING (trade_date)
       INNER JOIN tx USING (trade_date)
ORDER BY b.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end, start, end]).fetchdf()

    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    cnt_med = df["up_limit_count"].median()
    val_med = df["lu_value_ratio"].median()
    df["is_lc_hv"] = (df["up_limit_count"] < cnt_med) & (df["lu_value_ratio"] >= val_med)
    df["is_hc_hv"] = (df["up_limit_count"] >= cnt_med) & (df["lu_value_ratio"] >= val_med)

    print(f"Threshold: count_median={cnt_med:.0f}, value_ratio_median={val_med:.4f}")
    print(f"Total days: {len(df)}, LC-HV: {df['is_lc_hv'].sum()}, HC-HV: {df['is_hc_hv'].sum()}")
    return df


# ---------------------------------------------------------------------------
# Performance helpers
# ---------------------------------------------------------------------------

def perf_summary(trades: pd.DataFrame, label: str) -> dict:
    """trades 欄位: trade_date, entry_price, exit_price, side ('L' or 'S'), pnl_points, ret_pct"""
    if len(trades) == 0:
        return {"label": label, "n_trades": 0}
    pnl = trades["pnl_points"]
    ret = trades["ret_pct"]
    cum = pnl.cumsum()
    drawdown = cum - cum.cummax()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(252) if ret.std() > 0 else 0
    return {
        "label": label,
        "n_trades": len(trades),
        "win_rate": (pnl > 0).mean(),
        "avg_pnl_pts": pnl.mean(),
        "median_pnl_pts": pnl.median(),
        "total_pnl_pts": pnl.sum(),
        "avg_ret_pct": ret.mean(),
        "total_ret_pct": ret.sum(),
        "sharpe_pct_daily_annualized": sharpe,
        "max_drawdown_pts": drawdown.min(),
        "best_pts": pnl.max(),
        "worst_pts": pnl.min(),
    }


def print_summary(d: dict) -> None:
    print(f"\n--- {d['label']} ---")
    if d.get("n_trades", 0) == 0:
        print("  No trades.")
        return
    print(f"  Trades: {d['n_trades']}")
    print(f"  Win rate: {d['win_rate']:.2%}")
    print(f"  Avg PnL: {d['avg_pnl_pts']:+.2f} pts ({d['avg_ret_pct']:+.4f}%)")
    print(f"  Median PnL: {d['median_pnl_pts']:+.2f} pts")
    print(f"  Total PnL: {d['total_pnl_pts']:+.1f} pts ({d['total_ret_pct']:+.2f}%)")
    print(f"  Sharpe: {d['sharpe_pct_daily_annualized']:.2f}")
    print(f"  Max DD: {d['max_drawdown_pts']:+.1f} pts")
    print(f"  Best/Worst: {d['best_pts']:+.1f} / {d['worst_pts']:+.1f}")


# ---------------------------------------------------------------------------
# C1: Standalone 隔日做空
# ---------------------------------------------------------------------------

def backtest_c1(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """LC-HV 日 → 隔日 08:45 做空 → 13:45 平倉。對照組: HC-HV 同樣方式做空、做多."""
    df = df.sort_values("trade_date").reset_index(drop=True)

    out = {}

    # Strategy: short on day t+1 if day t is LC-HV
    sig = df["is_lc_hv"].shift(1, fill_value=False)
    sub = df[sig].copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "S"
    sub["pnl_points"] = sub["entry_price"] - sub["exit_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["C1_short_after_LCHV"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    # Reference 1: short on day t+1 if day t is HC-HV (應該虧錢，做為 sanity check)
    sig = df["is_hc_hv"].shift(1, fill_value=False)
    sub = df[sig].copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "S"
    sub["pnl_points"] = sub["entry_price"] - sub["exit_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["REF_short_after_HCHV"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    # Reference 2: 全期每日做空
    sub = df.copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "S"
    sub["pnl_points"] = sub["entry_price"] - sub["exit_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["REF_short_every_day"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    return out


# ---------------------------------------------------------------------------
# C3: Long hold + LC-HV 跳過
# ---------------------------------------------------------------------------

def backtest_c3(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Always-long 日盤 baseline vs 前一日 LC-HV 就跳過."""
    df = df.sort_values("trade_date").reset_index(drop=True)
    out = {}

    # Baseline: 每日 long
    sub = df.copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "L"
    sub["pnl_points"] = sub["exit_price"] - sub["entry_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["BASELINE_long_every_day"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    # C3 變體: 前一日 LC-HV 就跳過
    skip = df["is_lc_hv"].shift(1, fill_value=False)
    sub = df[~skip].copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "L"
    sub["pnl_points"] = sub["exit_price"] - sub["entry_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["C3_long_skip_after_LCHV"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    # Sanity check: 只在前一日 LC-HV 進場（純測「被跳過的日子」表現）
    enter = df["is_lc_hv"].shift(1, fill_value=False)
    sub = df[enter].copy()
    sub["entry_price"] = sub["tx_open"]
    sub["exit_price"] = sub["tx_close"]
    sub["side"] = "L"
    sub["pnl_points"] = sub["exit_price"] - sub["entry_price"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_points"] / sub["entry_price"] * 100
    out["DIAG_long_only_after_LCHV"] = sub[
        ["trade_date", "entry_price", "exit_price", "side", "pnl_points", "ret_pct"]
    ]

    return out


# ---------------------------------------------------------------------------
# Walk-forward / OOS split
# ---------------------------------------------------------------------------

def split_is_oos(df: pd.DataFrame, oos_start: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("trade_date")
    oos_ts = pd.Timestamp(oos_start)
    is_df = df[df["trade_date"] < oos_ts].copy()
    oos_df = df[df["trade_date"] >= oos_ts].copy()
    return is_df, oos_df


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_block(df: pd.DataFrame, label: str) -> None:
    print(f"\n{'='*78}")
    print(f"{label}: {df['trade_date'].min()} ~ {df['trade_date'].max()}, n={len(df)}")
    print(f"{'='*78}")

    print("\n----- C1: Standalone 隔日做空 -----")
    c1 = backtest_c1(df)
    for name, trades in c1.items():
        print_summary(perf_summary(trades, name))

    print("\n----- C3: Long-hold + LC-HV 跳過 -----")
    c3 = backtest_c3(df)
    base = perf_summary(c3["BASELINE_long_every_day"], "BASELINE_long_every_day")
    var = perf_summary(c3["C3_long_skip_after_LCHV"], "C3_long_skip_after_LCHV")
    diag = perf_summary(c3["DIAG_long_only_after_LCHV"], "DIAG_long_only_after_LCHV")
    print_summary(base)
    print_summary(var)
    print_summary(diag)

    print("\n  C3 vs Baseline:")
    if base["n_trades"] > 0 and var["n_trades"] > 0:
        skipped_n = base["n_trades"] - var["n_trades"]
        print(f"  Baseline 總損益: {base['total_pnl_pts']:+.1f} pts ({base['n_trades']} 筆)")
        print(f"  C3       總損益: {var['total_pnl_pts']:+.1f} pts ({var['n_trades']} 筆)")
        print(f"  跳過 {skipped_n} 筆，每筆平均: {(base['total_pnl_pts']-var['total_pnl_pts'])/max(skipped_n,1):+.2f} pts")
        print(f"  Baseline Sharpe: {base['sharpe_pct_daily_annualized']:.2f} → C3: {var['sharpe_pct_daily_annualized']:.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 4, 30))
    p.add_argument("--oos-start", type=date.fromisoformat, default=date(2025, 7, 1),
                   help="OOS 起始日（IS = start ~ oos_start-1）")
    p.add_argument("--save", action="store_true")
    args = p.parse_args()

    df = load_daily(args.start, args.end)

    run_block(df, "FULL SAMPLE")
    is_df, oos_df = split_is_oos(df, args.oos_start)
    run_block(is_df, f"IN-SAMPLE (< {args.oos_start})")
    run_block(oos_df, f"OUT-OF-SAMPLE (>= {args.oos_start})")

    if args.save:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        for label, sub in {"full": df, "is": is_df, "oos": oos_df}.items():
            for name, trades in {**backtest_c1(sub), **backtest_c3(sub)}.items():
                trades.to_csv(RESULT_DIR / f"backtest_{label}_{name}.csv", index=False)
        print(f"\nSaved trade CSVs to {RESULT_DIR}")


if __name__ == "__main__":
    main()

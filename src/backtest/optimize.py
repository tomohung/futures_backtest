#!/usr/bin/env python3
"""Grid-search optimization for ORBStrategy.

Base param sweep:
    uv run python src/backtest/optimize.py

Trend filter sensitivity scan:
    uv run python src/backtest/optimize.py --trend-only

Train: 2023-2025  |  OOS test: 2026
Goals: win_rate >= 52%, avg_win/avg_loss >= 1.3, profit_factor >= 1.2
"""
import argparse
import sys
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data
from src.strategies.orb import ORBStrategy

TARGET_WIN_RATE = 52.0
TARGET_WL_RATIO = 1.3
TARGET_PF = 1.2
MIN_TRADES = 10

PARAM_GRID = {
    "range_end_minute":      [30, 45, 60, 75],
    "entry_end_minute":      [60, 75, 90, 105, 120],
    "sl_pct":                [0.003, 0.005, 0.007, 0.010],
    "tp_multiplier":         [1.5, 2.0, 2.5, 3.0],
    "trail_activate_minute": [30, 45, 60, 90],
    "trend_ma_days":         [0, 5, 10, 20, 60],
}

TREND_ONLY_GRID = {
    "trend_ma_days": [0, 5, 10, 20, 60],
}


def build_grid(param_grid: dict) -> list[dict]:
    keys = list(param_grid.keys())
    combos = []
    for vals in product(*param_grid.values()):
        combo = dict(zip(keys, vals))
        rem = combo.get("range_end_minute", 0)
        eem = combo.get("entry_end_minute", rem + 1)
        if eem > rem:
            combos.append(combo)
    return combos


def compute_metrics(stats) -> dict | None:
    trades = stats["_trades"]
    if len(trades) < MIN_TRADES:
        return None
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return None
    win_rate = len(wins) / len(trades) * 100
    avg_wl = wins.mean() / abs(losses.mean())
    pf = wins.sum() / abs(losses.sum())
    return {
        "n_trades":   len(trades),
        "n_long":     int((trades["Size"] > 0).sum()),
        "n_short":    int((trades["Size"] < 0).sum()),
        "win_rate":   round(win_rate, 1),
        "avg_wl":     round(avg_wl, 3),
        "pf":         round(pf, 3),
        "expectancy": round(pnl.mean(), 1),
    }


def run_grid(df: pd.DataFrame, combos: list[dict], label: str = "") -> pd.DataFrame:
    bt = Backtest(df, ORBStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    total = len(combos)
    print(f"{label}: testing {total} combinations...")

    rows = []
    for i, params in enumerate(combos, 1):
        if i % 200 == 0 or i == total:
            print(f"  {i}/{total}", end="\r")
        stats = bt.run(**params)
        m = compute_metrics(stats)
        if m:
            rows.append({**params, **m})
    print()
    return pd.DataFrame(rows)


def print_results(df: pd.DataFrame, label: str, param_cols: list[str], top_n: int = 20) -> pd.DataFrame:
    metric_cols = ["n_trades", "win_rate", "avg_wl", "pf", "expectancy"]
    display_cols = param_cols + metric_cols

    passed = df[
        (df.win_rate >= TARGET_WIN_RATE)
        & (df.avg_wl >= TARGET_WL_RATIO)
        & (df.pf >= TARGET_PF)
    ].sort_values(["pf", "win_rate"], ascending=False).reset_index(drop=True)

    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"  Total valid combos: {len(df)}")
    print(f"  Meet targets (win_rate≥{TARGET_WIN_RATE}%, avg_wl≥{TARGET_WL_RATIO}, pf≥{TARGET_PF}): {len(passed)}")
    print(f"{'='*70}")

    if passed.empty:
        print("  No combo met all targets. Best 10 by profit factor:")
        best = df.nlargest(10, "pf")
        print(best[display_cols].to_string(index=False))
    else:
        show = passed.head(top_n)
        print(f"  Top {len(show)} results:")
        print(show[display_cols].to_string(index=False))

    return passed


def main():
    parser = argparse.ArgumentParser(description="ORB Strategy Parameter Optimization")
    parser.add_argument(
        "--trend-only",
        action="store_true",
        help="Sensitivity scan: fix base params at defaults, sweep trend_ma_days only (5 combos)",
    )
    args = parser.parse_args()

    if args.trend_only:
        param_grid = TREND_ONLY_GRID
        label_suffix = " | trend_ma_days sweep"
        csv_suffix = "_trend_only"
    else:
        param_grid = PARAM_GRID
        label_suffix = ""
        csv_suffix = ""

    param_cols = list(param_grid.keys())

    print("=" * 70)
    print("ORB Strategy — Parameter Optimization")
    print(f"Target: win_rate≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading data...")
    df_train = load_data(start="2023-01-01", end="2025-12-31")
    df_test  = load_data(start="2026-01-01")
    print(f"  Train (2023-2025): {len(df_train):,} bars  "
          f"({df_train.index[0].date()} ~ {df_train.index[-1].date()})")
    print(f"  Test  (2026):      {len(df_test):,} bars  "
          f"({df_test.index[0].date()} ~ {df_test.index[-1].date()})")

    combos = build_grid(param_grid)

    # --- Step 1: train ---
    df_train_results = run_grid(df_train, combos, label=f"Train (2023-2025){label_suffix}")
    good = print_results(df_train_results, label="Training results (2023-2025)", param_cols=param_cols)

    Path("output").mkdir(exist_ok=True)
    train_csv = f"output/optimize_train{csv_suffix}.csv"
    df_train_results.to_csv(train_csv, index=False)
    print(f"\nFull training results saved → {train_csv}")

    if good.empty:
        print("\nNo parameter set met targets on training data. Stopping.")
        return

    # --- Step 2: out-of-sample verify on 2026 ---
    top_combos = good.head(30)[param_cols].to_dict("records")

    print(f"\nVerifying top {len(top_combos)} combos on 2026 data...")
    df_test_results = run_grid(df_test, top_combos, label="Test (2026)")

    train_top = good.head(30)[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades"]].copy()
    train_top.columns = param_cols + ["tr_win_rate", "tr_avg_wl", "tr_pf", "tr_exp", "tr_n"]
    merged = train_top.merge(
        df_test_results[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades"]].rename(
            columns={"win_rate": "te_win_rate", "avg_wl": "te_avg_wl",
                     "pf": "te_pf", "expectancy": "te_exp", "n_trades": "te_n"}
        ),
        on=param_cols,
        how="left",
    )

    print(f"\n{'='*70}")
    print("Out-of-sample verification (2026)")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed_oos = merged[
        (merged.te_win_rate >= 50.0) & (merged.te_pf >= 1.0)
    ]
    print(f"\n{len(passed_oos)}/{len(merged)} combos pass OOS targets (win_rate≥50%, pf≥1.0) on 2026:")
    if not passed_oos.empty:
        print(passed_oos.to_string(index=False))

    verify_csv = f"output/optimize_verify2026{csv_suffix}.csv"
    merged.to_csv(verify_csv, index=False)
    print(f"\nVerification results saved → {verify_csv}")


if __name__ == "__main__":
    main()

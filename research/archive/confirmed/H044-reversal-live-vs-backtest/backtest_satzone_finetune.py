#!/usr/bin/env python3
"""H044: Fine-tune pullback fraction around 0.5.

Test 0.375, 0.5, 0.618, 0.75 to find the sweet spot.
"""
import sys
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy
from backtest_satzone_variants import ReversalSatPullbackReset

PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
)

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

FRACTIONS = [0.375, 0.5, 0.618, 0.75]


def compute_pf(pnl):
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0
    return wins / losses


def run_fraction(df_all, frac):
    params = {**PARAMS, "pullback_fraction": frac}
    year_rows = []
    all_pnl = []

    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ReversalSatPullbackReset, cash=200_000,
                      commission=0.0, trade_on_close=True)
        trades = bt.run(**params)["_trades"]
        if len(trades) == 0:
            year_rows.append({"year": yr, "n": 0, "win": None, "total": 0, "pf": None})
            continue
        pnl = trades["PnL"]
        all_pnl.append(pnl)
        n = len(pnl)
        year_rows.append({
            "year": yr, "n": n,
            "win": round((pnl > 0).sum() / n * 100, 1),
            "total": round(pnl.sum()),
            "pf": round(compute_pf(pnl), 2),
        })

    combined = pd.concat(all_pnl) if all_pnl else pd.Series(dtype=float)
    return year_rows, combined


def main():
    print("Loading data...")
    df_all = load_data_for_reversal()

    # Also run baseline
    print(f"\n{'=' * 72}")
    print("COMPARISON: baseline vs pullback fractions")
    print(f"{'=' * 72}")

    # Baseline
    all_pnl_base = []
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        trades = bt.run(**PARAMS)["_trades"]
        if len(trades) > 0:
            all_pnl_base.append(trades["PnL"])
    base = pd.concat(all_pnl_base)

    print(f"\n  {'Fraction':>10}  {'N':>5}  {'Win%':>7}  {'Avg':>7}  {'Total':>9}  {'PF':>6}")
    print(f"  {'-'*10}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*6}")

    n = len(base)
    print(f"  {'baseline':>10}  {n:>5}  {(base > 0).sum() / n * 100:>6.1f}%  "
          f"{base.mean():>7.1f}  {base.sum():>+9.0f}  {compute_pf(base):>6.2f}")

    results = {}
    for frac in FRACTIONS:
        year_rows, combined = run_fraction(df_all, frac)
        results[frac] = (year_rows, combined)
        n = len(combined)
        if n > 0:
            print(f"  {frac:>10.3f}  {n:>5}  {(combined > 0).sum() / n * 100:>6.1f}%  "
                  f"{combined.mean():>7.1f}  {combined.sum():>+9.0f}  "
                  f"{compute_pf(combined):>6.2f}")

    # Year-by-year detail for top candidates
    for frac in FRACTIONS:
        year_rows, _ = results[frac]
        print(f"\n  pullback_fraction = {frac}")
        print(f"  {'Year':<6}  {'N':>5}  {'Win%':>7}  {'Total':>9}  {'PF':>6}")
        print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*9}  {'-'*6}")
        for r in year_rows:
            w = f"{r['win']:.1f}%" if r['win'] is not None else "—"
            p = f"{r['pf']:.2f}" if r['pf'] is not None else "—"
            print(f"  {r['year']:<6}  {r['n']:>5}  {w:>7}  {r['total']:>+9}  {p:>6}")

    print()


if __name__ == "__main__":
    main()

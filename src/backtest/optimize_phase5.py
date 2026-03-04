#!/usr/bin/env python3
"""Phase 5 optimizer: rolling OR regime filter on top of Phase 4 Hybrid.

Skip new entries when the N-day rolling average of OR width is below a threshold.
This filters out quiet-market regimes (like 2021) where OR breakouts tend to fail.

Fixed: tp_or_multiplier=1.5, sl_pct=0.004  (Phase 4 Hybrid best)
Grid:  min_rolling_or × rolling_or_window   (6 × 2 = 12 combos)
       plus long-only variant for each

Usage:
    uv run python src/backtest/optimize_phase5.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPhase4HybridStrategy, ORBStrategy

PHASE2_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)

# Phase 4 Hybrid best (no regime filter)
PH4H_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
    tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10,
    min_rolling_or=0.0,
)

GRID = {
    "min_rolling_or":    [60, 80, 100, 120, 150],
    "rolling_or_window": [10, 20],
}  # 10 combos

MIN_TRADES = 5

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


def dir_pnl(trades, mask):
    t = trades[mask]["PnL"]
    if len(t) == 0:
        return 0.0, 0, None, None
    w = t[t > 0]
    win = round(len(w) / len(t) * 100, 1)
    exp = round(t.mean(), 1)
    return round(t.sum(), 0), len(t), win, exp


def run_year_sweep(df_all, params, label=""):
    rows = []
    total_long = total_short = total = 0.0
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ORBPhase4HybridStrategy, cash=200_000,
                      commission=0.0, trade_on_close=True)
        trades = bt.run(**params)["_trades"]
        if len(trades) == 0:
            rows.append({"year": yr, "n": 0, "n_long": 0, "n_short": 0,
                         "long_tot": 0, "short_tot": 0, "total": 0,
                         "long_win": None, "short_win": None,
                         "long_exp": None, "short_exp": None})
            continue
        lm = trades["Size"] > 0
        sm = trades["Size"] < 0
        lt, nl, lw, le = dir_pnl(trades, lm)
        st, ns, sw, se = dir_pnl(trades, sm)
        tot = lt + st
        total_long += lt; total_short += st; total += tot
        rows.append({"year": yr, "n": len(trades), "n_long": nl, "n_short": ns,
                     "long_tot": lt, "short_tot": st, "total": tot,
                     "long_win": lw, "short_win": sw,
                     "long_exp": le, "short_exp": se})
    rows.append({"year": "TOTAL", "n": None, "n_long": None, "n_short": None,
                 "long_tot": total_long, "short_tot": total_short, "total": total,
                 "long_win": None, "short_win": None,
                 "long_exp": None, "short_exp": None})
    return pd.DataFrame(rows)


def fv(v, w=7):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.1f}".rjust(w)
    return str(v).rjust(w)


def print_sweep(df, label):
    print(f"\n  {label}")
    print(f"  {'Year':<6}  {'n(L/S)':>10}  {'Long tot':>9}  {'L win%':>7}  {'L exp':>7}"
          f"  {'Sht tot':>9}  {'S win%':>7}  {'S exp':>7}  {'Total':>9}")
    print(f"  {'-'*6}  {'-'*10}  {'-'*9}  {'-'*7}  {'-'*7}"
          f"  {'-'*9}  {'-'*7}  {'-'*7}  {'-'*9}")
    for _, r in df.iterrows():
        ls = f"{r['n_long']}/{r['n_short']}" if r["n_long"] is not None else "—"
        print(f"  {r['year']:<6}  {ls:>10}  {fv(r['long_tot']):>9}  {fv(r['long_win']):>7}"
              f"  {fv(r['long_exp']):>7}  {fv(r['short_tot']):>9}  {fv(r['short_win']):>7}"
              f"  {fv(r['short_exp']):>7}  {fv(r['total']):>9}")


def main():
    print("=" * 72)
    print("Phase 5 — Rolling OR Regime Filter")
    print("  Skip entries when N-day rolling avg OR < min_rolling_or")
    print(f"  Base params: tp_or_multiplier=1.5  sl_pct=0.004  (Ph4 Hybrid best)")
    print("=" * 72)

    # Load data for each rolling_or_window value
    windows = sorted(set(GRID["rolling_or_window"]))
    thresholds = GRID["min_rolling_or"]

    data = {}  # window → df_all
    for w in windows:
        print(f"\nLoading data (rolling_or_window={w})...", flush=True)
        data[w] = load_data_with_night_ma(trend_ma_days=10, rolling_or_window=w)
        print(f"  {len(data[w]):,} bars  {data[w].index[0].date()} ~ {data[w].index[-1].date()}")

    # Baseline: Phase 2 and Ph4 Hybrid (no filter)
    print("\n" + "=" * 72)
    print("BASELINE: Phase 2 vs Ph4 Hybrid (no filter)")
    print("=" * 72)

    df_base = data[windows[0]]
    print("\n  [Phase 2]")
    bt = Backtest(df_base, ORBStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    for yr, start, end in YEARS:
        df_yr = df_base[df_base.index >= start]
        if end: df_yr = df_yr[df_yr.index <= end]
        bt2 = Backtest(df_yr, ORBStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        t = bt2.run(**PHASE2_BASE)["_trades"]
        lm = t["Size"] > 0; sm = t["Size"] < 0
        lt = t[lm]["PnL"]; st = t[sm]["PnL"]
        print(f"    {yr}  n={len(t)}({lm.sum()}/{sm.sum()})  "
              f"L: win={len(lt[lt>0])/len(lt)*100:.0f}% exp={lt.mean():.1f} tot={lt.sum():.0f}  "
              f"S: win={len(st[st>0])/len(st)*100:.0f}% exp={st.mean():.1f} tot={st.sum():.0f}  "
              f"tot={t['PnL'].sum():.0f}" if len(lt) and len(st) else f"    {yr}  n={len(t)}")

    print("\n  [Ph4 Hybrid, no filter]")
    df_p4h = run_year_sweep(df_base, PH4H_BASE)
    print_sweep(df_p4h, "Ph4 Hybrid (min_rolling_or=0)")

    # Grid sweep
    print("\n" + "=" * 72)
    print("GRID SWEEP — year-by-year totals")
    print("=" * 72)

    summary_rows = []
    for w in windows:
        df_all = data[w]
        for thr in thresholds:
            params = {**PH4H_BASE, "min_rolling_or": thr}
            df_sw = run_year_sweep(df_all, params)
            tot_row = df_sw[df_sw["year"] == "TOTAL"].iloc[0]
            yr_totals = {r["year"]: r["total"]
                         for _, r in df_sw[df_sw["year"] != "TOTAL"].iterrows()}
            row = {"window": w, "min_or": thr,
                   "total": tot_row["total"],
                   **{f"y{y}": yr_totals.get(y, 0) for y, *_ in YEARS}}
            summary_rows.append(row)

    df_sum = pd.DataFrame(summary_rows)
    yr_cols = [f"y{y}" for y, *_ in YEARS]

    print(f"\n  {'win':>4}  {'min_or':>6}  " +
          "  ".join(f"{'y'+y:>7}" for y, *_ in YEARS) + f"  {'TOTAL':>8}")
    print(f"  {'-'*4}  {'-'*6}  " + "  ".join(f"{'-'*7}" for _ in YEARS) + f"  {'-'*8}")

    # Also add Ph4H baseline row
    base_yr = {r["year"]: r["total"]
               for _, r in df_p4h[df_p4h["year"] != "TOTAL"].iterrows()}
    base_tot = df_p4h[df_p4h["year"] == "TOTAL"]["total"].iloc[0]
    print(f"  {'—':>4}  {'0 (base)':>8}  " +
          "  ".join(f"{fv(base_yr.get(y,0)):>7}" for y, *_ in YEARS) +
          f"  {fv(base_tot):>8}")

    for _, r in df_sum.iterrows():
        print(f"  {int(r['window']):>4}  {int(r['min_or']):>6}  " +
              "  ".join(f"{fv(r[c]):>7}" for c in yr_cols) +
              f"  {fv(r['total']):>8}")

    # Best combo by total PnL (not making 2021 worse than -200)
    viable = df_sum[df_sum["y2021"] >= -200]
    best = (viable if not viable.empty else df_sum).sort_values("total", ascending=False).iloc[0]
    best_params = {**PH4H_BASE,
                   "min_rolling_or": best["min_or"]}
    best_w = int(best["window"])

    print(f"\n  Best viable combo: window={best_w}  min_rolling_or={int(best['min_or'])}")
    print(f"  (2021≥-200 constraint  →  {len(viable)}/{len(df_sum)} combos viable)")

    # Detailed breakdown for best
    print("\n" + "=" * 72)
    print(f"DETAILED YEAR SWEEP — best: window={best_w}  min_rolling_or={int(best['min_or'])}")
    print("=" * 72)
    df_best = run_year_sweep(data[best_w], best_params)
    print_sweep(df_best, f"Ph4 Hybrid + RollingOR filter (w={best_w}, min={int(best['min_or'])})")

    Path("output").mkdir(exist_ok=True)
    df_sum.to_csv("output/phase5_grid.csv", index=False)
    print("\nGrid results → output/phase5_grid.csv")


if __name__ == "__main__":
    main()

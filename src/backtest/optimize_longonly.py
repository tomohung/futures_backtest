#!/usr/bin/env python3
"""Long-only optimizer: re-optimize tp_or_multiplier × sl_pct for longs only,
then sweep ADX entry filter thresholds on top of the best long-only params.

Step 1 — Long-only grid (24 combos):
    tp_or_multiplier × sl_pct, long_only=1

Step 2 — ADX filter grid (10 combos):
    long_adx_min × adx_period, fixed to Step 1 best params

Usage:
    uv run python src/backtest/optimize_longonly.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPhase4HybridStrategy

# ── Fixed base (Ph4 Hybrid structure) ────────────────────────────────────────
BASE_FIXED = dict(
    range_end_minute=90, entry_end_minute=120,
    or_min_width=20.0, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
    min_rolling_or=0.0, long_only=1,
)

# Ph4 Hybrid best (both directions) — used as reference baseline
PH4H_BOTH = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
    tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10,
    min_rolling_or=0.0,
)

# ── Grids ─────────────────────────────────────────────────────────────────────
GRID1 = {
    "tp_or_multiplier": [1.0, 1.25, 1.5, 2.0, 2.5, 3.0],
    "sl_pct":           [0.003, 0.004, 0.005, 0.006],
}  # 24 combos

GRID2 = {
    "long_adx_min": [20, 22, 25, 28, 30],
    "adx_period":   [10, 14],
}  # 10 combos

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def year_sweep(df_all, params, long_only=True):
    """Run year-by-year sweep, return DataFrame of per-year results."""
    rows = []
    total = 0.0
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ORBPhase4HybridStrategy, cash=200_000,
                      commission=0.0, trade_on_close=True)
        trades = bt.run(**params)["_trades"]
        if len(trades) == 0:
            rows.append({"year": yr, "n": 0, "win": None, "exp": None, "total": 0.0})
            continue
        if long_only:
            trades = trades[trades["Size"] > 0]
        pnl = trades["PnL"]
        n   = len(pnl)
        if n == 0:
            rows.append({"year": yr, "n": 0, "win": None, "exp": None, "total": 0.0})
            continue
        win = round(len(pnl[pnl > 0]) / n * 100, 1)
        exp = round(pnl.mean(), 1)
        tot = round(pnl.sum(), 0)
        total += tot
        rows.append({"year": yr, "n": n, "win": win, "exp": exp, "total": tot})
    rows.append({"year": "TOTAL", "n": None, "win": None, "exp": None, "total": total})
    return pd.DataFrame(rows)


def print_sweep(df, label):
    print(f"\n  {label}")
    print(f"  {'Year':<6}  {'n':>5}  {'win%':>7}  {'exp':>7}  {'Total':>9}")
    print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}")
    for _, r in df.iterrows():
        print(f"  {r['year']:<6}  {fv(r['n'], 5, 0):>5}  "
              f"{fv(r['win']):>7}  {fv(r['exp']):>7}  {fv(r['total'], 9, 0):>9}")


def main():
    t0 = _time.time()
    print("=" * 72)
    print("Long-Only Optimizer")
    print("  Step 1: tp_or_multiplier × sl_pct (24 combos, long_only=1)")
    print("  Step 2: long_adx_min × adx_period (10 combos, ADX entry filter)")
    print("=" * 72)

    # ── Load base data (no ADX yet) ───────────────────────────────────────
    print("\nLoading data (no ADX)...", flush=True)
    df_base = load_data_with_night_ma(trend_ma_days=10)
    print(f"  {len(df_base):,} bars  {df_base.index[0].date()} ~ {df_base.index[-1].date()}")

    # ── Baseline: Ph4 Hybrid both directions ──────────────────────────────
    print("\n" + "=" * 72)
    print("BASELINE: Ph4 Hybrid (both directions, tp_or=1.5, sl=0.004)")
    print("=" * 72)
    df_both = year_sweep(df_base, PH4H_BOTH, long_only=False)
    print_sweep(df_both, "Ph4 Hybrid (both sides)")

    print("\n  [Longs only from Ph4 Hybrid baseline]")
    df_long_base = year_sweep(df_base, PH4H_BOTH, long_only=True)
    print_sweep(df_long_base, "Ph4 Hybrid longs only (params from both-side optim)")

    # ── Step 1: Long-only grid ────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("STEP 1 — LONG-ONLY GRID SWEEP")
    print("=" * 72)

    tp_vals = GRID1["tp_or_multiplier"]
    sl_vals = GRID1["sl_pct"]
    yr_cols = [yr for yr, *_ in YEARS]

    summary = []
    total_combos = len(tp_vals) * len(sl_vals)
    done = 0
    for tp, sl in product(tp_vals, sl_vals):
        params = {**BASE_FIXED, "tp_or_multiplier": tp, "sl_pct": sl, "long_adx_min": 0.0}
        df_sw = year_sweep(df_base, params, long_only=True)
        tot_row  = df_sw[df_sw["year"] == "TOTAL"].iloc[0]
        yr_totals = {r["year"]: r["total"]
                     for _, r in df_sw[df_sw["year"] != "TOTAL"].iterrows()}
        summary.append({
            "tp": tp, "sl": sl,
            "total": tot_row["total"],
            **{f"y{y}": yr_totals.get(y, 0) for y in yr_cols},
        })
        done += 1
        print(f"  [{done:2d}/{total_combos}] tp={tp:.2f} sl={sl:.3f} "
              f"total={tot_row['total']:+.0f}", flush=True)

    df_s1 = pd.DataFrame(summary)
    yr_hdr = "  ".join(f"{'y'+y:>7}" for y in yr_cols)
    print(f"\n  {'tp':>5}  {'sl':>6}  {yr_hdr}  {'TOTAL':>8}")
    print(f"  {'-'*5}  {'-'*6}  " + "  ".join(f"{'-'*7}" for _ in yr_cols) + f"  {'-'*8}")
    for _, r in df_s1.sort_values("total", ascending=False).iterrows():
        yv = "  ".join(f"{fv(r[f'y{y}'], 7, 0):>7}" for y in yr_cols)
        print(f"  {r['tp']:5.2f}  {r['sl']:6.3f}  {yv}  {fv(r['total'], 8, 0):>8}")

    # Best viable combo: 2021 >= -200
    viable = df_s1[df_s1["y2021"] >= -200]
    best1 = (viable if not viable.empty else df_s1).sort_values("total", ascending=False).iloc[0]
    best1_params = {**BASE_FIXED,
                    "tp_or_multiplier": best1["tp"],
                    "sl_pct": best1["sl"],
                    "long_adx_min": 0.0}
    print(f"\n  Best viable (2021≥-200): tp_or={best1['tp']:.2f}  sl={best1['sl']:.3f}"
          f"  total={best1['total']:+.0f}  2021={best1['y2021']:+.0f}")
    print(f"  ({len(viable)}/{len(df_s1)} combos viable)")

    # Detailed year sweep for best Step 1
    print("\n" + "=" * 72)
    print(f"STEP 1 BEST — tp_or={best1['tp']:.2f}  sl={best1['sl']:.3f}")
    print("=" * 72)
    df_best1 = year_sweep(df_base, best1_params, long_only=True)
    print_sweep(df_best1, f"Long-only  tp_or={best1['tp']:.2f}  sl={best1['sl']:.3f}")

    # ── Step 2: ADX filter ────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("STEP 2 — ADX ENTRY FILTER GRID")
    print(f"  Base: tp_or={best1['tp']:.2f}  sl={best1['sl']:.3f}  long_only=1")
    print("=" * 72)

    adx_periods = sorted(set(GRID2["adx_period"]))
    adx_data = {}
    for p in adx_periods:
        print(f"\nLoading data with ADX(period={p})...", flush=True)
        adx_data[p] = load_data_with_night_ma(trend_ma_days=10, adx_period=p)
        print(f"  {len(adx_data[p]):,} bars")

    adx_summary = []
    total_adx = len(GRID2["long_adx_min"]) * len(GRID2["adx_period"])
    done = 0
    for adx_min, adx_p in product(GRID2["long_adx_min"], GRID2["adx_period"]):
        params = {**BASE_FIXED,
                  "tp_or_multiplier": best1["tp"],
                  "sl_pct": best1["sl"],
                  "long_adx_min": float(adx_min),
                  "long_only": 1}
        df_sw = year_sweep(adx_data[adx_p], params, long_only=True)
        tot_row   = df_sw[df_sw["year"] == "TOTAL"].iloc[0]
        yr_totals = {r["year"]: r["total"]
                     for _, r in df_sw[df_sw["year"] != "TOTAL"].iterrows()}
        adx_summary.append({
            "adx_p": adx_p, "adx_min": adx_min,
            "total": tot_row["total"],
            **{f"y{y}": yr_totals.get(y, 0) for y in yr_cols},
        })
        done += 1
        print(f"  [{done:2d}/{total_adx}] adx_p={adx_p}  adx_min={adx_min}"
              f"  total={tot_row['total']:+.0f}  2021={yr_totals.get('2021', 0):+.0f}",
              flush=True)

    df_s2 = pd.DataFrame(adx_summary)
    print(f"\n  {'adx_p':>6}  {'adx_min':>7}  {yr_hdr}  {'TOTAL':>8}")
    print(f"  {'-'*6}  {'-'*7}  " + "  ".join(f"{'-'*7}" for _ in yr_cols) + f"  {'-'*8}")

    # Also show no-filter baseline row
    no_filter_row = df_s1[df_s1.apply(
        lambda r: r["tp"] == best1["tp"] and r["sl"] == best1["sl"], axis=1)].iloc[0]
    yv = "  ".join(f"{fv(no_filter_row[f'y{y}'], 7, 0):>7}" for y in yr_cols)
    print(f"  {'—':>6}  {'0 (base)':>7}  {yv}  {fv(no_filter_row['total'], 8, 0):>8}")

    for _, r in df_s2.sort_values("total", ascending=False).iterrows():
        yv = "  ".join(f"{fv(r[f'y{y}'], 7, 0):>7}" for y in yr_cols)
        print(f"  {int(r['adx_p']):>6}  {int(r['adx_min']):>7}  {yv}  {fv(r['total'], 8, 0):>8}")

    # Best ADX combo: 2021 >= -200
    viable2 = df_s2[df_s2["y2021"] >= -200]
    if not viable2.empty:
        best2 = viable2.sort_values("total", ascending=False).iloc[0]
        print(f"\n  Best ADX viable (2021≥-200): adx_p={int(best2['adx_p'])}"
              f"  adx_min={int(best2['adx_min'])}"
              f"  total={best2['total']:+.0f}  2021={best2['y2021']:+.0f}")
        print(f"  ({len(viable2)}/{len(df_s2)} combos viable)")

        # Detailed year sweep for best ADX combo
        print("\n" + "=" * 72)
        print(f"STEP 2 BEST — adx_p={int(best2['adx_p'])}  adx_min={int(best2['adx_min'])}")
        print("=" * 72)
        best2_params = {**BASE_FIXED,
                        "tp_or_multiplier": best1["tp"],
                        "sl_pct": best1["sl"],
                        "long_adx_min": float(best2["adx_min"]),
                        "long_only": 1}
        df_best2 = year_sweep(adx_data[int(best2["adx_p"])], best2_params, long_only=True)
        print_sweep(df_best2, f"Long-only + ADX≥{int(best2['adx_min'])}(p={int(best2['adx_p'])})")
    else:
        print("\n  No ADX combo meets 2021 ≥ -200 constraint.")

    # Save grids
    Path("output").mkdir(exist_ok=True)
    df_s1.to_csv("output/longonly_grid1.csv", index=False)
    df_s2.to_csv("output/longonly_grid2_adx.csv", index=False)
    print(f"\nGrids → output/longonly_grid1.csv  output/longonly_grid2_adx.csv")
    print(f"Total time: {_time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reversal Strategy optimizer.

Grid: vol_ratio × sl_ema_fraction × tp_ema_fraction  (36 combos)

Usage:
    uv run python src/backtest/optimize_reversal.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

GRID = {
    "vol_ratio":       [1.2, 1.5, 2.0],
    "sl_ema_fraction": [0.25, 0.35, 0.45],
    "tp_ema_fraction": [0.8, 1.0, 1.2, 1.5],
    "tp_mode":         ["ema", "vol_range"],
    "tp_vol_fraction": [0.6, 0.8, 1.0],
}  # 3 × 3 × 4 × 2 × 3 = 216 combos (tp_vol_fraction only used when tp_mode=vol_range)

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


def year_sweep(df_all, params):
    rows = []
    total = 0.0
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ReversalStrategy, cash=200_000,
                      commission=0.0, trade_on_close=True)
        trades = bt.run(**params)["_trades"]
        if len(trades) == 0:
            rows.append({"year": yr, "n": 0, "win": None, "exp": None, "total": 0.0})
            continue
        pnl = trades["PnL"]
        n   = len(pnl)
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
    yr_cols = [yr for yr, *_ in YEARS]
    # Count effective combos: tp_vol_fraction only matters when tp_mode=vol_range
    n_ema = (len(GRID["vol_ratio"]) * len(GRID["sl_ema_fraction"])
             * len(GRID["tp_ema_fraction"]))  # ema mode: tp_vol_fraction irrelevant
    n_vol = (len(GRID["vol_ratio"]) * len(GRID["sl_ema_fraction"])
             * len(GRID["tp_ema_fraction"]) * len(GRID["tp_vol_fraction"]))  # vol_range
    total_combos = n_ema + n_vol

    print("=" * 72)
    print("Reversal Strategy Optimizer")
    print(f"  Grid: vol_ratio × sl_ema_fraction × tp_ema_fraction  ({total_combos} combos)")
    print("=" * 72)

    print("\nLoading data...", flush=True)
    df_all = load_data_for_reversal()
    print(f"  {len(df_all):,} bars  {df_all.index[0].date()} ~ {df_all.index[-1].date()}")

    summary = []
    done = 0
    for vol, sl, tp_ema, tp_mode, tp_vf in product(
        GRID["vol_ratio"], GRID["sl_ema_fraction"], GRID["tp_ema_fraction"],
        GRID["tp_mode"], GRID["tp_vol_fraction"],
    ):
        # Skip redundant combos: tp_vol_fraction doesn't matter for ema mode
        if tp_mode == "ema" and tp_vf != GRID["tp_vol_fraction"][0]:
            continue

        params = dict(vol_ratio=vol, sl_ema_fraction=sl, tp_ema_fraction=tp_ema,
                      tp_mode=tp_mode, tp_vol_fraction=tp_vf)
        df_sw = year_sweep(df_all, params)
        tot_row   = df_sw[df_sw["year"] == "TOTAL"].iloc[0]
        yr_totals = {r["year"]: r["total"]
                     for _, r in df_sw[df_sw["year"] != "TOTAL"].iterrows()}
        summary.append({
            "vol": vol, "sl": sl, "tp_ema": tp_ema,
            "mode": tp_mode, "tp_vf": tp_vf,
            "total": tot_row["total"],
            **{f"y{y}": yr_totals.get(y, 0) for y in yr_cols},
        })
        done += 1
        mode_str = f"mode={tp_mode}"
        vf_str = f" vf={tp_vf:.1f}" if tp_mode == "vol_range" else ""
        print(f"  [{done:3d}/{total_combos}] vol={vol:.1f} sl={sl:.2f} tp={tp_ema:.1f}"
              f" {mode_str}{vf_str}  total={tot_row['total']:+.0f}", flush=True)

    df_s = pd.DataFrame(summary)
    yr_hdr = "  ".join(f"{'y'+y:>7}" for y in yr_cols)
    print(f"\n  {'vol':>5}  {'sl':>5}  {'tp_e':>5}  {'mode':>9}  {'tp_vf':>5}  {yr_hdr}  {'TOTAL':>8}")
    print(f"  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*9}  {'-'*5}  "
          + "  ".join(f"{'-'*7}" for _ in yr_cols) + f"  {'-'*8}")
    for _, r in df_s.sort_values("total", ascending=False).iterrows():
        yv = "  ".join(f"{fv(r[f'y{y}'], 7, 0):>7}" for y in yr_cols)
        vf_str = f"{r['tp_vf']:5.1f}" if r["mode"] == "vol_range" else "    —"
        print(f"  {r['vol']:5.1f}  {r['sl']:5.2f}  {r['tp_ema']:5.1f}  {r['mode']:>9}  {vf_str}  {yv}  "
              f"{fv(r['total'], 8, 0):>8}")

    # Best combo — require no single year worse than -500
    viable = df_s[df_s.apply(
        lambda r: all(r[f"y{y}"] >= -500 for y in yr_cols if f"y{y}" in r), axis=1
    )]
    best = (viable if not viable.empty else df_s).sort_values("total", ascending=False).iloc[0]
    label = (f"vol={best['vol']:.1f} sl={best['sl']:.2f} tp_ema={best['tp_ema']:.1f}"
             f" mode={best['mode']}")
    if best["mode"] == "vol_range":
        label += f" vf={best['tp_vf']:.1f}"
    print(f"\n  Best viable: {label}  total={best['total']:+.0f}")
    print(f"  ({len(viable)}/{len(df_s)} combos viable)")

    best_params = dict(vol_ratio=best["vol"],
                       sl_ema_fraction=best["sl"],
                       tp_ema_fraction=best["tp_ema"],
                       tp_mode=best["mode"],
                       tp_vol_fraction=best["tp_vf"])
    df_best = year_sweep(df_all, best_params)
    print_sweep(df_best, f"Best: {label}")

    Path("output").mkdir(exist_ok=True)
    out = Path("output/reversal_optimize.csv")
    df_s.to_csv(out, index=False)
    print(f"\nGrid → {out}")
    print(f"Total time: {_time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

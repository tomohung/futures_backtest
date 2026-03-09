#!/usr/bin/env python3
"""Entry window sweep for ORBWithEstHLExitStrategy.

Parametrizes OR length (via or_end_min) and entry window end (entry_end_min):
  - OR end: 8:54, 8:55, 8:56, 8:57  (or_end_min = 534, 535, 536, 537)
  - Entry end: 9:05, 9:10, 9:15     (entry_end_min = 545, 550, 555)

Total: 4 × 3 = 12 combos, each run across 2021–2026 YTD.

Usage:
    uv run python src/backtest/explore_entry_window.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

# Dim 1: OR end time (minutes since midnight)
# 8:54=534, 8:55=535, 8:56=536, 8:57=537 (current default)
OR_END_MINS = [534, 535, 536, 537]

# Dim 2: entry window end (minutes since midnight)
# 9:05=545 (current), 9:10=550, 9:15=555
ENTRY_END_MINS = [545, 550, 555]

# Fixed params (best known from prior optimization)
FIXED = dict(sl_ema_fraction=0.25, bigcost_days=2, long_only=True, adx_min=0.0)


def fmt_min(m):
    """Format minutes-since-midnight as HH:MM string."""
    return f"{m // 60}:{m % 60:02d}"


def run_combo(df_all, or_end, entry_end):
    """Run year-by-year sweep for a given (or_end_min, entry_end_min) combo."""
    rows = []
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ORBWithEstHLExitStrategy, cash=200_000,
                      commission=0.0, trade_on_close=True)
        stats = bt.run(**FIXED, or_end_min=or_end, entry_end_min=entry_end)
        trades = stats["_trades"]
        if len(trades) == 0:
            rows.append({"year": yr, "n": 0, "wr": None, "pf": None, "pnl": 0.0})
            continue
        pnl = trades["PnL"]
        n = len(pnl)
        wr = round(len(pnl[pnl > 0]) / n * 100, 1)
        wins = pnl[pnl > 0].sum()
        losses = pnl[pnl < 0].abs().sum()
        pf = round(wins / losses, 2) if losses > 0 else float("inf")
        rows.append({"year": yr, "n": n, "wr": wr, "pf": pf, "pnl": round(pnl.sum(), 0)})
    return rows


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def main():
    t0 = _time.time()
    yr_labels = [yr for yr, *_ in YEARS]
    n_combos = len(OR_END_MINS) * len(ENTRY_END_MINS)

    print("=" * 80)
    print("Entry Window Sweep — ORBWithEstHLExitStrategy")
    print(f"  OR end:    {[fmt_min(m) for m in OR_END_MINS]}")
    print(f"  Entry end: {[fmt_min(m) for m in ENTRY_END_MINS]}")
    print(f"  {n_combos} combos × {len(YEARS)} years")
    print(f"  Fixed: {FIXED}")
    print("=" * 80)

    print("\nLoading data...", flush=True)
    df_all = load_data_for_orb_est_hl()
    print(f"  {len(df_all):,} bars  {df_all.index[0].date()} ~ {df_all.index[-1].date()}")

    all_rows = []
    done = 0
    for or_end, entry_end in product(OR_END_MINS, ENTRY_END_MINS):
        label_or = fmt_min(or_end)
        label_ee = fmt_min(entry_end)
        year_rows = run_combo(df_all, or_end, entry_end)
        total_pnl = sum(r["pnl"] for r in year_rows)
        for r in year_rows:
            all_rows.append({
                "or_end": label_or,
                "entry_end": label_ee,
                "or_end_min": or_end,
                "entry_end_min": entry_end,
                **r,
            })
        done += 1
        yr_pnls = "  ".join(f"{r['pnl']:+.0f}" for r in year_rows)
        print(f"  [{done:2d}/{n_combos}] OR_END={label_or}  ENTRY_END={label_ee}"
              f"  total={total_pnl:+.0f}  [{yr_pnls}]", flush=True)

    df = pd.DataFrame(all_rows)

    # ── Summary pivot: total PnL per combo ───────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY — Total PnL by combo (baseline: OR_END=8:57, ENTRY_END=9:05)")
    print("=" * 80)

    yr_hdr = "  ".join(f"{'y'+y:>7}" for y in yr_labels)
    print(f"\n  {'OR_END':>7}  {'EE':>5}  {yr_hdr}  {'TOTAL':>8}  {'avg_n':>6}  {'avg_wr':>7}")
    print(f"  {'-'*7}  {'-'*5}  " + "  ".join(f"{'-'*7}" for _ in yr_labels)
          + f"  {'-'*8}  {'-'*6}  {'-'*7}")

    combo_summary = []
    for or_end, entry_end in product(OR_END_MINS, ENTRY_END_MINS):
        label_or = fmt_min(or_end)
        label_ee = fmt_min(entry_end)
        subset = df[(df["or_end_min"] == or_end) & (df["entry_end_min"] == entry_end)]
        yr_pnls = {}
        yr_ns = {}
        yr_wrs = {}
        for yr in yr_labels:
            row = subset[subset["year"] == yr].iloc[0]
            yr_pnls[yr] = row["pnl"]
            yr_ns[yr] = row["n"]
            yr_wrs[yr] = row["wr"]
        total = sum(yr_pnls.values())
        avg_n = round(sum(yr_ns.values()) / len(yr_labels), 1)
        valid_wrs = [v for v in yr_wrs.values() if v is not None]
        avg_wr = round(sum(valid_wrs) / len(valid_wrs), 1) if valid_wrs else None
        combo_summary.append({
            "or_end": label_or, "entry_end": label_ee,
            "total": total, "avg_n": avg_n, "avg_wr": avg_wr,
            **{f"y{y}": yr_pnls[y] for y in yr_labels},
        })

    df_summary = pd.DataFrame(combo_summary).sort_values("total", ascending=False)
    for _, r in df_summary.iterrows():
        yv = "  ".join(f"{fv(r[f'y{y}'], 7, 0):>7}" for y in yr_labels)
        baseline_marker = " ◄" if r["or_end"] == "8:57" and r["entry_end"] == "9:05" else ""
        print(f"  {r['or_end']:>7}  {r['entry_end']:>5}  {yv}  "
              f"{fv(r['total'], 8, 0):>8}  {fv(r['avg_n'], 6, 1):>6}  "
              f"{fv(r['avg_wr'], 7, 1):>7}{baseline_marker}")

    # ── Per-year detail for top 3 combos ─────────────────────────────────────
    print("\n" + "=" * 80)
    print("PER-YEAR DETAIL — top 3 combos by total PnL")
    print("=" * 80)
    for _, combo_row in df_summary.head(3).iterrows():
        subset = df[(df["or_end"] == combo_row["or_end"])
                    & (df["entry_end"] == combo_row["entry_end"])]
        print(f"\n  OR_END={combo_row['or_end']}  ENTRY_END={combo_row['entry_end']}"
              f"  total={combo_row['total']:+.0f}")
        print(f"  {'Year':<6}  {'n':>5}  {'WR%':>6}  {'PF':>6}  {'PnL':>9}")
        print(f"  {'-'*6}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*9}")
        for _, r in subset.iterrows():
            print(f"  {r['year']:<6}  {fv(r['n'], 5, 0):>5}  "
                  f"{fv(r['wr'], 6, 1):>6}  {fv(r['pf'], 6, 2):>6}  "
                  f"{fv(r['pnl'], 9, 0):>9}")

    # ── Save CSV ──────────────────────────────────────────────────────────────
    Path("output").mkdir(exist_ok=True)
    out_path = "output/explore_entry_window.csv"
    df.to_csv(out_path, index=False)
    print(f"\nResults → {out_path}")
    print(f"Total time: {_time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Phase 4 Hybrid optimizer: OR-width TP for longs, Phase 2 fixed-pct TP for shorts.

  Longs:  TP = entry + tp_or_multiplier × max(OR_width, or_min_width=20)
  Shorts: TP = entry - sl_pct × tp_multiplier=1.5  (Phase 2 style)
  SL + trailing identical to Phase 2 for both sides.

Grid: tp_or_multiplier × sl_pct  (7 × 3 = 21 combos)

Usage:
    uv run python src/backtest/optimize_phase4_hybrid.py
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

PHASE4_FIXED = dict(
    range_end_minute=90, entry_end_minute=120,
    trail_activate_minute=45, trend_ma_days=10,
    or_min_width=20.0, tp_multiplier=1.5,
)

GRID = {
    "tp_or_multiplier": [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0],
    "sl_pct":           [0.004, 0.005, 0.006],
}  # 21 combos

TARGET_WIN_RATE = 52.0
TARGET_WL_RATIO = 1.3
TARGET_PF       = 1.2
MIN_TRADES      = 10

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


def _dir_metrics(pnl: pd.Series) -> dict:
    if len(pnl) == 0:
        return {"n": 0, "win_rate": None, "avg_wl": None, "pf": None, "expectancy": None}
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "n":          len(pnl),
        "win_rate":   round(len(wins) / len(pnl) * 100, 1),
        "avg_wl":     round(wins.mean() / abs(losses.mean()), 3) if len(wins) and len(losses) else None,
        "pf":         round(wins.sum() / abs(losses.sum()), 3)   if len(losses) and losses.sum() != 0 else None,
        "expectancy": round(pnl.mean(), 1),
    }


def compute_metrics(stats) -> dict | None:
    trades = stats["_trades"]
    if len(trades) < MIN_TRADES:
        return None
    pnl    = trades["PnL"]
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return None

    exit_times = pd.to_datetime(trades["ExitTime"]).dt.time
    force_mask = exit_times >= pd.Timestamp("1900-01-01 13:30:00").time()
    long_mask  = trades["Size"] > 0
    short_mask = trades["Size"] < 0
    tp_mask    = ~force_mask & (pnl > 0)
    sl_mask    = ~force_mask & (pnl <= 0)
    n = len(trades)

    return {
        "n_trades":  n,
        "n_long":    int(long_mask.sum()),
        "n_short":   int(short_mask.sum()),
        "win_rate":  round(len(wins) / n * 100, 1),
        "avg_wl":    round(wins.mean() / abs(losses.mean()), 3),
        "pf":        round(wins.sum() / abs(losses.sum()), 3),
        "expectancy":round(pnl.mean(), 1),
        "total":     round(pnl.sum(), 1),
        "tp_exit":   round(tp_mask.sum() / n * 100, 1),
        "sl_exit":   round(sl_mask.sum() / n * 100, 1),
        "force_pct": round(force_mask.sum() / n * 100, 1),
        "long":      _dir_metrics(trades.loc[long_mask,  "PnL"]),
        "short":     _dir_metrics(trades.loc[short_mask, "PnL"]),
    }


def run_single(df, strategy_cls, params) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    return compute_metrics(bt.run(**params))


def make_combos() -> list[dict]:
    param_cols = list(GRID.keys())
    return [
        {**PHASE4_FIXED, **dict(zip(param_cols, v))}
        for v in product(*GRID.values())
    ]


def run_grid(df, combos: list[dict], label: str) -> pd.DataFrame:
    total = len(combos)
    print(f"{label}: testing {total} combos...", flush=True)
    rows = []
    t0 = _time.time()
    for i, params in enumerate(combos, 1):
        m = run_single(df, ORBPhase4HybridStrategy, params)
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({**params, **flat})
        if i % 5 == 0 or i == total:
            print(f"  {i}/{total}  {_time.time()-t0:.1f}s", flush=True)
    return pd.DataFrame(rows)


def fv(v):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:.1f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def main():
    TRAIN_START, TRAIN_END, TEST_START = "2025-01-01", "2025-12-31", "2026-01-01"
    param_cols = list(GRID.keys())

    print("=" * 70)
    print("Phase 4 Hybrid — OR-width TP (longs) + Phase 2 TP (shorts)")
    print("  Long TP  = entry + tp_or_multiplier × max(OR_width, 20)")
    print("  Short TP = entry - sl_pct × 1.5  (Phase 2 style)")
    print(f"Targets: win≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading data...")
    df_train = load_data_with_night_ma(start=TRAIN_START, end=TRAIN_END, trend_ma_days=10)
    df_test  = load_data_with_night_ma(start=TEST_START,  trend_ma_days=10)
    print(f"  Train: {len(df_train):,} bars  {df_train.index[0].date()} ~ {df_train.index[-1].date()}")
    print(f"  OOS:   {len(df_test):,} bars  {df_test.index[0].date()} ~ {df_test.index[-1].date()}")

    # Baseline
    print("\n" + "─" * 70)
    base_train = run_single(df_train, ORBStrategy, PHASE2_BASE)
    base_test  = run_single(df_test,  ORBStrategy, PHASE2_BASE)
    print("Baseline (Phase 2) computed.")

    combos = make_combos()

    # Train grid
    print("\n" + "─" * 70)
    df_tr = run_grid(df_train, combos, "Train (2025)")

    passed = df_tr[
        (df_tr.win_rate  >= TARGET_WIN_RATE) &
        (df_tr.avg_wl    >= TARGET_WL_RATIO) &
        (df_tr.pf        >= TARGET_PF)
    ].sort_values(["pf", "win_rate"], ascending=False).reset_index(drop=True)

    metric_cols = ["n_trades", "n_long", "n_short", "win_rate", "avg_wl", "pf",
                   "expectancy", "tp_exit", "sl_exit", "force_pct"]
    print(f"\n{'='*70}")
    print(f"Training results (2025)  — {len(passed)}/{len(df_tr)} meet targets")
    print(f"{'='*70}")
    show = passed if not passed.empty else df_tr.sort_values("pf", ascending=False)
    print(show[param_cols + metric_cols].to_string(index=False))

    # OOS
    print("\n" + "─" * 70)
    top_combos = (passed if not passed.empty else df_tr.sort_values("pf", ascending=False)).head(12)
    top_full   = [{**PHASE4_FIXED, **{k: r[k] for k in param_cols}}
                  for _, r in top_combos.iterrows()]
    df_te = run_grid(df_test, top_full, "OOS (2026)")

    tr_top = top_combos[param_cols + ["win_rate", "avg_wl", "pf", "expectancy",
                                       "n_trades", "force_pct", "tp_exit"]].copy()
    tr_top.columns = (param_cols
                      + ["tr_win", "tr_wl", "tr_pf", "tr_exp", "tr_n", "tr_force", "tr_tp"])

    merged = tr_top.merge(
        df_te[param_cols + ["win_rate", "avg_wl", "pf", "expectancy",
                            "n_trades", "force_pct", "tp_exit"]].rename(
            columns={"win_rate": "te_win", "avg_wl": "te_wl", "pf": "te_pf",
                     "expectancy": "te_exp", "n_trades": "te_n",
                     "force_pct": "te_force", "tp_exit": "te_tp"}),
        on=param_cols, how="left",
    )

    print(f"\n{'='*70}")
    print("Phase 4 Hybrid — Train vs OOS")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed_oos = merged[(merged.te_win >= 50) & (merged.te_pf >= 1.0)]
    print(f"\n{len(passed_oos)}/{len(merged)} pass OOS targets (win≥50%, pf≥1.0):")
    if not passed_oos.empty:
        print(passed_oos.to_string(index=False))

    Path("output").mkdir(exist_ok=True)
    merged.to_csv("output/phase4_hybrid_results.csv", index=False)
    print("\nResults → output/phase4_hybrid_results.csv")

    # Best combo
    best_row = (
        passed_oos.sort_values("te_pf", ascending=False).iloc[0]
        if not passed_oos.empty
        else merged.sort_values("te_pf", ascending=False).iloc[0]
    )
    best_params = {**PHASE4_FIXED, **{k: best_row[k] for k in param_cols}}
    best_label  = "  ".join(f"{k}={best_row[k]}" for k in param_cols)

    # ── Historical year sweep ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("HISTORICAL YEAR SWEEP")
    print(f"  Phase 4 Hybrid params: {best_label}")
    print(f"{'='*70}")

    print("\nLoading all-years data...", flush=True)
    df_all = load_data_with_night_ma(trend_ma_days=10)

    total_p2 = total_h = 0.0
    hdr = (f"  {'Year':<6}  {'Ph2 tot':>8}  {'Ph2 exp':>8}"
           f"  {'Hyb tot':>8}  {'Hyb exp':>8}  {'Hyb tp%':>8}  {'Hyb force%':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for yr, start, end in YEARS:
        df_yr = df_all[df_all.index >= start]
        if end:
            df_yr = df_yr[df_yr.index <= end]

        m2 = run_single(df_yr, ORBStrategy,             PHASE2_BASE)
        mh = run_single(df_yr, ORBPhase4HybridStrategy, best_params)

        t2 = (m2["total"] if m2 else 0) or 0
        th = (mh["total"] if mh else 0) or 0
        total_p2 += t2; total_h += th

        print(f"  {yr:<6}  {fv(t2):>8}  {fv(m2.get('expectancy') if m2 else None):>8}"
              f"  {fv(th):>8}  {fv(mh.get('expectancy') if mh else None):>8}"
              f"  {fv(mh.get('tp_exit') if mh else None):>7}%"
              f"  {fv(mh.get('force_pct') if mh else None):>9}%")

    print(f"  {'TOTAL':<6}  {fv(total_p2):>8}  {'':>8}"
          f"  {fv(total_h):>8}")

    # ── Final comparison ───────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("FINAL COMPARISON — Phase 2 | Phase 4 Hybrid")
    print(f"  Hybrid params: {best_label}")
    print(f"{'='*70}")

    for period, df_p in [("Train 2025", df_train), ("OOS 2026", df_test)]:
        m2 = run_single(df_p, ORBStrategy,             PHASE2_BASE) or {}
        mh = run_single(df_p, ORBPhase4HybridStrategy, best_params) or {}

        print(f"\n  Period: {period}")
        print(f"  {'Metric':<22}  {'Phase2':>14}  {'Ph4 Hybrid':>14}")
        print(f"  {'-'*22}  {'-'*14}  {'-'*14}")

        rows_disp = [
            ("n_trades (L/S)",
             f"{m2.get('n_trades','—')}({m2.get('n_long','—')}/{m2.get('n_short','—')})",
             f"{mh.get('n_trades','—')}({mh.get('n_long','—')}/{mh.get('n_short','—')})"),
            ("win_rate",    fv(m2.get("win_rate")),    fv(mh.get("win_rate"))),
            ("avg_wl",      fv(m2.get("avg_wl")),      fv(mh.get("avg_wl"))),
            ("pf",          fv(m2.get("pf")),          fv(mh.get("pf"))),
            ("expectancy",  fv(m2.get("expectancy")),  fv(mh.get("expectancy"))),
            ("total PnL",   fv(m2.get("total")),       fv(mh.get("total"))),
            ("tp_exit %",   fv(m2.get("tp_exit")),     fv(mh.get("tp_exit"))),
            ("sl_exit %",   fv(m2.get("sl_exit")),     fv(mh.get("sl_exit"))),
            ("force_exit %",fv(m2.get("force_pct")),   fv(mh.get("force_pct"))),
        ]
        for lbl, b, hv in rows_disp:
            print(f"  {lbl:<22}  {b:>14}  {hv:>14}")

        for direction in ("long", "short"):
            b  = m2.get(direction) or {}
            hd = mh.get(direction) or {}
            print(f"\n    [{direction.upper()}]")
            print(f"    {'Metric':<20}  {'Phase2':>14}  {'Ph4 Hybrid':>14}")
            print(f"    {'-'*20}  {'-'*14}  {'-'*14}")
            for sub in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                print(f"    {sub:<20}  {fv(b.get(sub)):>14}  {fv(hd.get(sub)):>14}")

    print()


if __name__ == "__main__":
    main()

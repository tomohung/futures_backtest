#!/usr/bin/env python3
"""Phase 3B Hybrid / Long-only optimizer.

Tests two variants:
  1. Long-only  — Phase 3B ST exit, no short entries
  2. Hybrid     — Longs use ST exit; shorts use Phase 2 fixed SL/TP/trailing

Grid: atr_period × atr_multiplier (same as Phase 3B)
Shorts fixed at Phase 2 best: sl_pct=0.005, tp_multiplier=1.5

Usage:
    uv run python src/backtest/optimize_phase3b_hybrid.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPhase3BHybridStrategy, ORBStrategy

PHASE2_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)

# Phase 2 short params held constant in hybrid mode
SHORT_PARAMS = dict(sl_pct=0.005, tp_multiplier=1.5)

ATR_GRID = {
    "atr_period":     [7, 10, 14],
    "atr_multiplier": [2.0, 2.5, 3.0],
}

TARGET_WIN_RATE = 52.0
TARGET_WL_RATIO = 1.3
TARGET_PF = 1.2
MIN_TRADES = 10


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
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return None

    exit_times = pd.to_datetime(trades["ExitTime"]).dt.time
    force_mask = exit_times >= pd.Timestamp("1900-01-01 13:30:00").time()
    long_mask  = trades["Size"] > 0
    short_mask = trades["Size"] < 0

    return {
        "n_trades":   len(trades),
        "n_long":     int(long_mask.sum()),
        "n_short":    int(short_mask.sum()),
        "win_rate":   round(len(wins) / len(trades) * 100, 1),
        "avg_wl":     round(wins.mean() / abs(losses.mean()), 3),
        "pf":         round(wins.sum() / abs(losses.sum()), 3),
        "expectancy": round(pnl.mean(), 1),
        "force_pct":  round(force_mask.sum() / len(trades) * 100, 1),
        "long":       _dir_metrics(trades.loc[long_mask,  "PnL"]),
        "short":      _dir_metrics(trades.loc[short_mask, "PnL"]),
    }


def run_single(df, strategy_cls, params) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    return compute_metrics(bt.run(**params))


def run_grid(df, combos: list[dict], label: str = "") -> pd.DataFrame:
    total = len(combos)
    print(f"{label}: testing {total} combinations...")
    rows = []
    t0 = _time.time()
    for i, params in enumerate(combos, 1):
        bt = Backtest(df, ORBPhase3BHybridStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        m = compute_metrics(bt.run(**params))
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({**params, **flat})
        if i % 3 == 0 or i == total:
            elapsed = _time.time() - t0
            rate = i / elapsed
            eta = (total - i) / rate if i < total else 0
            print(f"  {i}/{total}  {rate:.1f} combo/s  ETA {eta:.0f}s")
    return pd.DataFrame(rows)


def print_grid_results(df: pd.DataFrame, label: str, param_cols: list[str]) -> pd.DataFrame:
    metric_cols = ["n_trades", "n_long", "n_short", "win_rate", "avg_wl", "pf", "expectancy", "force_pct"]
    passed = df[
        (df.win_rate >= TARGET_WIN_RATE) & (df.avg_wl >= TARGET_WL_RATIO) & (df.pf >= TARGET_PF)
    ].sort_values(["pf", "win_rate"], ascending=False).reset_index(drop=True)

    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"  Total: {len(df)}  |  Meet targets: {len(passed)}")
    print(f"{'='*70}")
    show = passed if not passed.empty else df.sort_values("pf", ascending=False)
    print(show[param_cols + metric_cols].to_string(index=False))
    return passed


def print_comparison(label, base_m, p3b_m, param_cols, best_params):
    def fv(v):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        return f"{v:.1f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)

    print(f"\n  [{label}]")
    print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'This variant':>14}")
    print(f"  {'-'*22}  {'-'*14}  {'-'*14}")
    base_m = base_m or {}
    p3b_m  = p3b_m  or {}

    rows = [
        ("n_trades (L/S)",
         f"{base_m.get('n_trades','—')} ({base_m.get('n_long','—')}/{base_m.get('n_short','—')})",
         f"{p3b_m.get('n_trades','—')} ({p3b_m.get('n_long','—')}/{p3b_m.get('n_short','—')})"),
        ("win_rate",     fv(base_m.get("win_rate")),   fv(p3b_m.get("win_rate"))),
        ("avg_wl",       fv(base_m.get("avg_wl")),     fv(p3b_m.get("avg_wl"))),
        ("pf",           fv(base_m.get("pf")),         fv(p3b_m.get("pf"))),
        ("expectancy",   fv(base_m.get("expectancy")), fv(p3b_m.get("expectancy"))),
        ("force_exit %", fv(base_m.get("force_pct")),  fv(p3b_m.get("force_pct"))),
    ]
    for lbl, bvs, pvs in rows:
        print(f"  {lbl:<22}  {bvs:>14}  {pvs:>14}")

    for direction in ("long", "short"):
        bdir = base_m.get(direction) or {}
        pdir = p3b_m.get(direction)  or {}
        print(f"\n    [{direction.upper()}]")
        for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
            print(f"    {m:<20}  {fv(bdir.get(m)):>14}  {fv(pdir.get(m)):>14}")


def main():
    TRAIN_START, TRAIN_END, TEST_START = "2025-01-01", "2025-12-31", "2026-01-01"

    print("=" * 70)
    print("ORB Phase 3B — Long-only & Hybrid variants")
    print(f"Targets: win≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading data...")
    df_train = load_data_with_night_ma(start=TRAIN_START, end=TRAIN_END, trend_ma_days=10)
    df_test  = load_data_with_night_ma(start=TEST_START, trend_ma_days=10)
    print(f"  Train: {len(df_train):,} bars  {df_train.index[0].date()} ~ {df_train.index[-1].date()}")
    print(f"  OOS:   {len(df_test):,} bars  {df_test.index[0].date()} ~ {df_test.index[-1].date()}")

    # Phase 2 baseline
    print("\n" + "─" * 70)
    print("Phase 2 baseline...")
    base_train = run_single(df_train, ORBStrategy, PHASE2_BASE)
    base_test  = run_single(df_test,  ORBStrategy, PHASE2_BASE)

    param_cols = list(ATR_GRID.keys())
    atr_combos = [dict(zip(param_cols, v)) for v in product(*ATR_GRID.values())]

    Path("output").mkdir(exist_ok=True)

    # ── VARIANT 1: Long-only ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    lo_combos = [{**c, **SHORT_PARAMS, "long_only": 1} for c in atr_combos]
    df_lo_train = run_grid(df_train, lo_combos, label="Long-only Train (2025)")
    passed_lo   = print_grid_results(df_lo_train, "Long-only Training results (2025)", param_cols)
    df_lo_train.to_csv("output/phase3b_longonly_train.csv", index=False)

    # OOS for long-only
    top_lo = (passed_lo if not passed_lo.empty else df_lo_train.sort_values("pf", ascending=False)).head(9)
    lo_oos_combos = [{**r, **SHORT_PARAMS, "long_only": 1}
                     for r in top_lo[param_cols].to_dict("records")]
    df_lo_test = run_grid(df_test, lo_oos_combos, label="Long-only Test (2026)")

    # Best long-only by OOS
    lo_merged = top_lo[param_cols + ["win_rate", "pf", "expectancy"]].copy()
    lo_merged.columns = param_cols + ["tr_win", "tr_pf", "tr_exp"]
    lo_merged = lo_merged.merge(
        df_lo_test[param_cols + ["win_rate", "pf", "expectancy"]].rename(
            columns={"win_rate": "te_win", "pf": "te_pf", "expectancy": "te_exp"}),
        on=param_cols, how="left",
    )
    print(f"\n{'='*70}")
    print("Long-only — Train vs OOS")
    print(f"{'='*70}")
    print(lo_merged.to_string(index=False))
    lo_merged.to_csv("output/phase3b_longonly_oos.csv", index=False)

    best_lo_row = (lo_merged[lo_merged.te_win >= 50].sort_values("te_pf", ascending=False)
                   if (lo_merged.te_win >= 50).any()
                   else lo_merged.sort_values("te_pf", ascending=False)).iloc[0]
    best_lo_params = {k: best_lo_row[k] for k in param_cols}
    best_lo_params_full = {**best_lo_params, **SHORT_PARAMS, "long_only": 1}

    # ── VARIANT 2: Hybrid (longs ST, shorts Phase 2) ─────────────────────
    print("\n" + "─" * 70)
    hy_combos = [{**c, **SHORT_PARAMS, "long_only": 0} for c in atr_combos]
    df_hy_train = run_grid(df_train, hy_combos, label="Hybrid Train (2025)")
    passed_hy   = print_grid_results(df_hy_train, "Hybrid Training results (2025)", param_cols)
    df_hy_train.to_csv("output/phase3b_hybrid_train.csv", index=False)

    # OOS for hybrid
    top_hy = (passed_hy if not passed_hy.empty else df_hy_train.sort_values("pf", ascending=False)).head(9)
    hy_oos_combos = [{**r, **SHORT_PARAMS, "long_only": 0}
                     for r in top_hy[param_cols].to_dict("records")]
    df_hy_test = run_grid(df_test, hy_oos_combos, label="Hybrid Test (2026)")

    hy_merged = top_hy[param_cols + ["win_rate", "pf", "expectancy"]].copy()
    hy_merged.columns = param_cols + ["tr_win", "tr_pf", "tr_exp"]
    hy_merged = hy_merged.merge(
        df_hy_test[param_cols + ["win_rate", "pf", "expectancy"]].rename(
            columns={"win_rate": "te_win", "pf": "te_pf", "expectancy": "te_exp"}),
        on=param_cols, how="left",
    )
    print(f"\n{'='*70}")
    print("Hybrid — Train vs OOS")
    print(f"{'='*70}")
    print(hy_merged.to_string(index=False))
    hy_merged.to_csv("output/phase3b_hybrid_oos.csv", index=False)

    best_hy_row = (hy_merged[hy_merged.te_win >= 50].sort_values("te_pf", ascending=False)
                   if (hy_merged.te_win >= 50).any()
                   else hy_merged.sort_values("te_pf", ascending=False)).iloc[0]
    best_hy_params = {k: best_hy_row[k] for k in param_cols}
    best_hy_params_full = {**best_hy_params, **SHORT_PARAMS, "long_only": 0}

    # ── Final comparison ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("FINAL COMPARISON — Phase 2 Base vs Long-only vs Hybrid")

    lo_train_full = run_single(df_train, ORBPhase3BHybridStrategy, best_lo_params_full)
    lo_test_full  = run_single(df_test,  ORBPhase3BHybridStrategy, best_lo_params_full)
    hy_train_full = run_single(df_train, ORBPhase3BHybridStrategy, best_hy_params_full)
    hy_test_full  = run_single(df_test,  ORBPhase3BHybridStrategy, best_hy_params_full)

    for period, bm, lo_m, hy_m in [
        ("Train 2025", base_train, lo_train_full, hy_train_full),
        ("OOS 2026",   base_test,  lo_test_full,  hy_test_full),
    ]:
        print(f"\n{'='*70}")
        print(f"  Period: {period}")
        print(f"{'='*70}")

        def fv(v):
            if v is None or (isinstance(v, float) and v != v):
                return "—"
            return f"{v:.1f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)

        bm = bm or {}
        lo_m = lo_m or {}
        hy_m = hy_m or {}

        print(f"  {'Metric':<22}  {'Phase2 Base':>13}  {'Long-only':>13}  {'Hybrid':>13}")
        print(f"  {'-'*22}  {'-'*13}  {'-'*13}  {'-'*13}")

        for lbl, bk, lok, hyk in [
            ("n_trades (L/S)",
             f"{bm.get('n_trades','—')} ({bm.get('n_long','—')}/{bm.get('n_short','—')})",
             f"{lo_m.get('n_trades','—')} ({lo_m.get('n_long','—')}/{lo_m.get('n_short','—')})",
             f"{hy_m.get('n_trades','—')} ({hy_m.get('n_long','—')}/{hy_m.get('n_short','—')})"),
            ("win_rate",    fv(bm.get("win_rate")),   fv(lo_m.get("win_rate")),   fv(hy_m.get("win_rate"))),
            ("avg_wl",      fv(bm.get("avg_wl")),     fv(lo_m.get("avg_wl")),     fv(hy_m.get("avg_wl"))),
            ("pf",          fv(bm.get("pf")),         fv(lo_m.get("pf")),         fv(hy_m.get("pf"))),
            ("expectancy",  fv(bm.get("expectancy")), fv(lo_m.get("expectancy")), fv(hy_m.get("expectancy"))),
            ("force_pct %", fv(bm.get("force_pct")),  fv(lo_m.get("force_pct")),  fv(hy_m.get("force_pct"))),
        ]:
            print(f"  {lbl:<22}  {bk:>13}  {lok:>13}  {hyk:>13}")

        for direction in ("long", "short"):
            print(f"\n    [{direction.upper()}]")
            print(f"    {'Metric':<20}  {'Phase2 Base':>13}  {'Long-only':>13}  {'Hybrid':>13}")
            print(f"    {'-'*20}  {'-'*13}  {'-'*13}  {'-'*13}")
            bd  = (bm.get(direction)  or {})
            ld  = (lo_m.get(direction) or {})
            hd  = (hy_m.get(direction) or {})
            for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                print(f"    {m:<20}  {fv(bd.get(m)):>13}  {fv(ld.get(m)):>13}  {fv(hd.get(m)):>13}")

    print(f"\n  Long-only best: " + "  ".join(f"{k}={v}" for k, v in best_lo_params.items()))
    print(f"  Hybrid best:    " + "  ".join(f"{k}={v}" for k, v in best_hy_params.items()))
    print()


if __name__ == "__main__":
    main()

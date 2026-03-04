#!/usr/bin/env python3
"""Phase 3A optimizer: OR-based SL/TP with bar-based trailing stop.

Sweeps tp_or_multiplier x trail_bars and compares with Phase 2 base.

Usage:
    uv run python src/backtest/optimize_phase3a.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPhase3AStrategy, ORBStrategy

# Phase 2 best params (baseline)
PHASE2_BASE = dict(
    range_end_minute=90,
    entry_end_minute=120,
    sl_pct=0.005,
    tp_multiplier=1.5,
    trail_activate_minute=45,
    trend_ma_days=10,
)

# Phase 3A grid — fixed structural params inherited from strategy defaults
PHASE3A_GRID = {
    "tp_or_multiplier": [1.5, 2.0, 2.5, 3.0],
    "trail_bars":       [3, 5, 10],
}

TARGET_WIN_RATE = 52.0
TARGET_WL_RATIO = 1.3
TARGET_PF = 1.2
MIN_TRADES = 10


def _dir_metrics(pnl: pd.Series) -> dict:
    """Compute win_rate/avg_wl/pf/expectancy for a subset of trades."""
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

    # Exit type breakdown: force exit at 13:30 vs SL/TP
    exit_times = pd.to_datetime(trades["ExitTime"]).dt.time
    force_mask = exit_times >= pd.Timestamp("1900-01-01 13:30:00").time()
    n_force = force_mask.sum()

    long_mask  = trades["Size"] > 0
    short_mask = trades["Size"] < 0
    long_m  = _dir_metrics(trades.loc[long_mask,  "PnL"])
    short_m = _dir_metrics(trades.loc[short_mask, "PnL"])

    return {
        "n_trades":    len(trades),
        "n_long":      int(long_mask.sum()),
        "n_short":     int(short_mask.sum()),
        "win_rate":    round(len(wins) / len(trades) * 100, 1),
        "avg_wl":      round(wins.mean() / abs(losses.mean()), 3),
        "pf":          round(wins.sum() / abs(losses.sum()), 3),
        "expectancy":  round(pnl.mean(), 1),
        "force_pct":   round(n_force / len(trades) * 100, 1),
        # per-direction
        "long":  long_m,
        "short": short_m,
    }


def run_single(df: pd.DataFrame, strategy_cls, params: dict) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    return compute_metrics(stats)


def run_grid(df: pd.DataFrame, combos: list[dict], label: str = "") -> pd.DataFrame:
    bt = Backtest(df, ORBPhase3AStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    total = len(combos)
    print(f"{label}: testing {total} combinations...")

    rows = []
    t0 = _time.time()
    for i, params in enumerate(combos, 1):
        stats = bt.run(**params)
        m = compute_metrics(stats)
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({**params, **flat})
        if i % 5 == 0 or i == total:
            elapsed = _time.time() - t0
            rate = i / elapsed
            eta = (total - i) / rate if i < total else 0
            print(f"  {i}/{total}  {rate:.1f} combo/s  ETA {eta:.0f}s")
    return pd.DataFrame(rows)


def print_results(df: pd.DataFrame, label: str, param_cols: list[str]) -> pd.DataFrame:
    metric_cols = ["n_trades", "win_rate", "avg_wl", "pf", "expectancy", "force_pct"]
    display_cols = param_cols + metric_cols

    passed = df[
        (df.win_rate >= TARGET_WIN_RATE)
        & (df.avg_wl >= TARGET_WL_RATIO)
        & (df.pf >= TARGET_PF)
    ].sort_values(["pf", "win_rate"], ascending=False).reset_index(drop=True)

    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"  Total valid combos: {len(df)}")
    print(f"  Meet targets (win≥{TARGET_WIN_RATE}%, wl≥{TARGET_WL_RATIO}, pf≥{TARGET_PF}): {len(passed)}")
    print(f"{'='*70}")

    if passed.empty:
        print("  No combo met all targets. Best 10 by profit factor:")
        best = df.nlargest(10, "pf")
        print(best[display_cols].to_string(index=False))
    else:
        print(f"  Top {min(len(passed), 20)} results:")
        print(passed.head(20)[display_cols].to_string(index=False))

    return passed


def print_comparison(base_label: str, base_m: dict, phase3a_row: dict, param_cols: list[str]):
    metric_cols = ["n_trades", "win_rate", "avg_wl", "pf", "expectancy", "force_pct"]
    print(f"\n{'='*70}")
    print("  Comparison: Phase 2 Base vs Phase 3A Best")
    print(f"{'='*70}")

    header = f"  {'Metric':<18}  {'Phase2 Base':>14}  {'Phase3A Best':>14}"
    print(header)
    print(f"  {'-'*18}  {'-'*14}  {'-'*14}")

    def fmt(v):
        if isinstance(v, float):
            return f"{v:.1f}"
        return str(v)

    # Print Phase 3A params
    print(f"\n  Phase 3A params: " + "  ".join(f"{k}={phase3a_row.get(k,'?')}" for k in param_cols))
    print()

    for m in metric_cols:
        bv = base_m.get(m, "—")
        pv = phase3a_row.get(m, "—")
        print(f"  {m:<18}  {fmt(bv):>14}  {fmt(pv):>14}")
    print(f"{'='*70}")


def main():
    TRAIN_START = "2025-01-01"
    TRAIN_END   = "2025-12-31"
    TEST_START  = "2026-01-01"

    print("=" * 70)
    print("ORB Phase 3A — OR-based SL/TP + Bar Trailing Stop")
    print(f"Target: win≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading training data (2025, with night MA)...")
    df_train = load_data_with_night_ma(
        start=TRAIN_START, end=TRAIN_END, trend_ma_days=10
    )
    print(f"  {len(df_train):,} bars  {df_train.index[0].date()} ~ {df_train.index[-1].date()}")

    print("\nLoading OOS data (2026, with night MA)...")
    df_test = load_data_with_night_ma(start=TEST_START, trend_ma_days=10)
    print(f"  {len(df_test):,} bars  {df_test.index[0].date()} ~ {df_test.index[-1].date()}")

    # ── Phase 2 baseline ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("Running Phase 2 baseline (sl_pct=0.005, tp_mult=1.5)...")
    base_train = run_single(df_train, ORBStrategy, PHASE2_BASE)
    base_test  = run_single(df_test,  ORBStrategy, PHASE2_BASE)
    print(f"  [Train] {base_train}")
    print(f"  [OOS]   {base_test}")

    # ── Phase 3A grid search ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    param_cols = list(PHASE3A_GRID.keys())
    combos = [
        dict(zip(param_cols, vals))
        for vals in product(*PHASE3A_GRID.values())
    ]

    df_train_results = run_grid(df_train, combos, label="Train (2025)")
    passed = print_results(df_train_results, label="Phase 3A Training results (2025)", param_cols=param_cols)

    Path("output").mkdir(exist_ok=True)
    df_train_results.to_csv("output/phase3a_train.csv", index=False)
    print(f"\nFull training results → output/phase3a_train.csv")

    if passed.empty:
        print("\nNo Phase 3A combo met targets on training data.")
        best_row = df_train_results.nlargest(1, "pf").iloc[0].to_dict() if len(df_train_results) else {}
    else:
        best_row = passed.iloc[0].to_dict()

    # ── OOS verification ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    top_combos = (passed if not passed.empty else df_train_results.nlargest(12, "pf"))
    top_combos = top_combos.head(12)[param_cols].to_dict("records")
    print(f"Verifying top {len(top_combos)} combos on 2026 OOS data...")

    df_test_results = run_grid(df_test, top_combos, label="Test (2026)")

    # Merge train + test
    train_top = (passed if not passed.empty else df_train_results.nlargest(12, "pf")).head(12)
    train_top = train_top[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].copy()
    train_top.columns = param_cols + ["tr_win", "tr_wl", "tr_pf", "tr_exp", "tr_n", "tr_force_pct"]

    merged = train_top.merge(
        df_test_results[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].rename(
            columns={"win_rate": "te_win", "avg_wl": "te_wl",
                     "pf": "te_pf", "expectancy": "te_exp",
                     "n_trades": "te_n", "force_pct": "te_force_pct"}
        ),
        on=param_cols, how="left",
    )

    print(f"\n{'='*70}")
    print("Phase 3A — Train vs OOS comparison")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed_oos = merged[
        (merged.te_win >= 50.0) & (merged.te_pf >= 1.0)
    ]
    print(f"\n{len(passed_oos)}/{len(merged)} combos pass OOS targets (win≥50%, pf≥1.0):")
    if not passed_oos.empty:
        print(passed_oos.to_string(index=False))

    merged.to_csv("output/phase3a_verify2026.csv", index=False)
    print(f"\nVerification results → output/phase3a_verify2026.csv")

    # ── Final comparison: Phase 2 base vs Phase 3A best ──────────────────
    print("\n" + "─" * 70)
    print("FINAL COMPARISON (Train 2025 + OOS 2026)")

    # Find best Phase 3A OOS combo
    best_oos = (
        passed_oos.sort_values("te_pf", ascending=False).iloc[0]
        if not passed_oos.empty
        else merged.sort_values("te_pf", ascending=False).iloc[0]
        if not merged.empty else None
    )

    # Re-run best combo with full metrics (including per-direction)
    best_p3a_params = {k: best_oos[k] for k in param_cols if k in best_oos} if best_oos is not None else {}
    p3a_train_full = run_single(df_train, ORBPhase3AStrategy, best_p3a_params) if best_p3a_params else {}
    p3a_test_full  = run_single(df_test,  ORBPhase3AStrategy, best_p3a_params) if best_p3a_params else {}

    for period, base_m, p3a_m in [
        ("Train 2025", base_train, p3a_train_full),
        ("OOS 2026",   base_test,  p3a_test_full),
    ]:
        if base_m is None:
            continue
        if p3a_m is None:
            p3a_m = {}

        def fv(v):
            if v is None or v == "—":
                return "—"
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return f"{v:.1f}"
            return str(v)

        print(f"\n  Period: {period}")
        print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'Phase3A Best':>14}")
        print(f"  {'-'*22}  {'-'*14}  {'-'*14}")

        overall_rows = [
            ("n_trades (L/S)",    f"{base_m['n_trades']} ({base_m['n_long']}/{base_m['n_short']})",
                                  f"{p3a_m.get('n_trades','—')} ({p3a_m.get('n_long','—')}/{p3a_m.get('n_short','—')})"),
            ("win_rate",          fv(base_m.get("win_rate")),    fv(p3a_m.get("win_rate"))),
            ("avg_wl",            fv(base_m.get("avg_wl")),      fv(p3a_m.get("avg_wl"))),
            ("pf",                fv(base_m.get("pf")),          fv(p3a_m.get("pf"))),
            ("expectancy",        fv(base_m.get("expectancy")),  fv(p3a_m.get("expectancy"))),
            ("force_exit %",      fv(base_m.get("force_pct")),   fv(p3a_m.get("force_pct"))),
        ]
        for label, bvs, pvs in overall_rows:
            print(f"  {label:<22}  {bvs:>14}  {pvs:>14}")

        # Per-direction breakdown
        for direction in ("long", "short"):
            bdir = base_m.get(direction, {}) or {}
            pdir = p3a_m.get(direction, {}) or {}
            print(f"\n  [{direction.upper()}]")
            print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'Phase3A Best':>14}")
            print(f"  {'-'*22}  {'-'*14}  {'-'*14}")
            for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                bv = bdir.get(m)
                pv = pdir.get(m)
                print(f"  {m:<22}  {fv(bv):>14}  {fv(pv):>14}")

    if best_p3a_params:
        print(f"\n  Phase 3A best params: " + "  ".join(f"{k}={v}" for k, v in best_p3a_params.items()))

    print()


if __name__ == "__main__":
    main()

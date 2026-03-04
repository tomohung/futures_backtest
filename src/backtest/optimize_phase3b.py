#!/usr/bin/env python3
"""Phase 3B optimizer: Super Trend exit, no fixed TP.

Sweeps atr_period x atr_multiplier and compares with Phase 2 base.

Usage:
    uv run python src/backtest/optimize_phase3b.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPhase3BStrategy, ORBStrategy

PHASE2_BASE = dict(
    range_end_minute=90,
    entry_end_minute=120,
    sl_pct=0.005,
    tp_multiplier=1.5,
    trail_activate_minute=45,
    trend_ma_days=10,
)

PHASE3B_GRID = {
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


def run_single(df: pd.DataFrame, strategy_cls, params: dict) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    return compute_metrics(stats)


def run_grid(df: pd.DataFrame, combos: list[dict], label: str = "") -> pd.DataFrame:
    total = len(combos)
    print(f"{label}: testing {total} combinations...")

    rows = []
    t0 = _time.time()
    for i, params in enumerate(combos, 1):
        bt = Backtest(df, ORBPhase3BStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(**params)
        m = compute_metrics(stats)
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({**params, **flat})
        if i % 3 == 0 or i == total:
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
        print("  No combo met all targets. All results by profit factor:")
        print(df.sort_values("pf", ascending=False)[display_cols].to_string(index=False))
    else:
        print(f"  Top {min(len(passed), 20)} results:")
        print(passed.head(20)[display_cols].to_string(index=False))

    return passed


def print_comparison(base_train, base_test, p3b_train, p3b_test, best_params, param_cols):
    def fv(v):
        if v is None or v == "—":
            return "—"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f"{v:.1f}"
        return str(v)

    for period, base_m, p3b_m in [
        ("Train 2025", base_train, p3b_train),
        ("OOS 2026",   base_test,  p3b_test),
    ]:
        if base_m is None:
            continue
        p3b_m = p3b_m or {}

        print(f"\n  Period: {period}")
        print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'Phase3B Best':>14}")
        print(f"  {'-'*22}  {'-'*14}  {'-'*14}")

        rows = [
            ("n_trades (L/S)",
             f"{base_m['n_trades']} ({base_m['n_long']}/{base_m['n_short']})",
             f"{p3b_m.get('n_trades','—')} ({p3b_m.get('n_long','—')}/{p3b_m.get('n_short','—')})"),
            ("win_rate",       fv(base_m.get("win_rate")),   fv(p3b_m.get("win_rate"))),
            ("avg_wl",         fv(base_m.get("avg_wl")),     fv(p3b_m.get("avg_wl"))),
            ("pf",             fv(base_m.get("pf")),         fv(p3b_m.get("pf"))),
            ("expectancy",     fv(base_m.get("expectancy")), fv(p3b_m.get("expectancy"))),
            ("force_exit %",   fv(base_m.get("force_pct")),  fv(p3b_m.get("force_pct"))),
        ]
        for label, bvs, pvs in rows:
            print(f"  {label:<22}  {bvs:>14}  {pvs:>14}")

        for direction in ("long", "short"):
            bdir = base_m.get(direction, {}) or {}
            pdir = p3b_m.get(direction, {}) or {}
            print(f"\n  [{direction.upper()}]")
            print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'Phase3B Best':>14}")
            print(f"  {'-'*22}  {'-'*14}  {'-'*14}")
            for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                print(f"  {m:<22}  {fv(bdir.get(m)):>14}  {fv(pdir.get(m)):>14}")

    if best_params:
        print(f"\n  Phase 3B best params: " + "  ".join(f"{k}={v}" for k, v in best_params.items()))


def main():
    TRAIN_START = "2025-01-01"
    TRAIN_END   = "2025-12-31"
    TEST_START  = "2026-01-01"

    print("=" * 70)
    print("ORB Phase 3B — Super Trend Exit (no fixed TP)")
    print(f"Target: win≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading training data (2025, with night MA)...")
    df_train = load_data_with_night_ma(start=TRAIN_START, end=TRAIN_END, trend_ma_days=10)
    print(f"  {len(df_train):,} bars  {df_train.index[0].date()} ~ {df_train.index[-1].date()}")

    print("\nLoading OOS data (2026, with night MA)...")
    df_test = load_data_with_night_ma(start=TEST_START, trend_ma_days=10)
    print(f"  {len(df_test):,} bars  {df_test.index[0].date()} ~ {df_test.index[-1].date()}")

    # ── Phase 2 baseline ─────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("Running Phase 2 baseline...")
    base_train = run_single(df_train, ORBStrategy, PHASE2_BASE)
    base_test  = run_single(df_test,  ORBStrategy, PHASE2_BASE)

    # ── Phase 3B grid ─────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    param_cols = list(PHASE3B_GRID.keys())
    combos = [dict(zip(param_cols, v)) for v in product(*PHASE3B_GRID.values())]

    df_train_results = run_grid(df_train, combos, label="Train (2025)")
    passed = print_results(df_train_results, "Phase 3B Training results (2025)", param_cols)

    Path("output").mkdir(exist_ok=True)
    df_train_results.to_csv("output/phase3b_train.csv", index=False)
    print(f"\nFull training results → output/phase3b_train.csv")

    # ── OOS verification ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    top_df = passed if not passed.empty else df_train_results.sort_values("pf", ascending=False)
    top_combos = top_df.head(9)[param_cols].to_dict("records")
    print(f"Verifying top {len(top_combos)} combos on 2026 OOS data...")

    df_test_results = run_grid(df_test, top_combos, label="Test (2026)")

    train_top = top_df.head(9)[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].copy()
    train_top.columns = param_cols + ["tr_win", "tr_wl", "tr_pf", "tr_exp", "tr_n", "tr_force_pct"]
    merged = train_top.merge(
        df_test_results[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].rename(
            columns={"win_rate": "te_win", "avg_wl": "te_wl", "pf": "te_pf",
                     "expectancy": "te_exp", "n_trades": "te_n", "force_pct": "te_force_pct"}
        ),
        on=param_cols, how="left",
    )

    print(f"\n{'='*70}")
    print("Phase 3B — Train vs OOS")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed_oos = merged[(merged.te_win >= 50.0) & (merged.te_pf >= 1.0)]
    print(f"\n{len(passed_oos)}/{len(merged)} combos pass OOS targets (win≥50%, pf≥1.0):")
    if not passed_oos.empty:
        print(passed_oos.to_string(index=False))

    merged.to_csv("output/phase3b_verify2026.csv", index=False)
    print(f"\nVerification results → output/phase3b_verify2026.csv")

    # ── Final comparison with long/short breakdown ────────────────────────
    print("\n" + "─" * 70)
    print("FINAL COMPARISON — Phase 2 Base vs Phase 3B Best")

    best_oos = (
        passed_oos.sort_values("te_pf", ascending=False).iloc[0]
        if not passed_oos.empty
        else merged.sort_values("te_pf", ascending=False).iloc[0]
        if not merged.empty else None
    )
    best_params = {k: best_oos[k] for k in param_cols if k in best_oos} if best_oos is not None else {}

    p3b_train_full = run_single(df_train, ORBPhase3BStrategy, best_params) if best_params else None
    p3b_test_full  = run_single(df_test,  ORBPhase3BStrategy, best_params) if best_params else None

    print_comparison(base_train, base_test, p3b_train_full, p3b_test_full, best_params, param_cols)
    print()


if __name__ == "__main__":
    main()

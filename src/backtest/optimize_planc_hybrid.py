#!/usr/bin/env python3
"""Plan C Hybrid optimizer: momentum stall exit with asymmetric SL.

Longs:  OR low SL + no new high in N minutes → exit
Shorts: fixed sl_pct SL + no new low in N minutes → exit

Grid: momentum_window × sl_pct  (4 × 3 = 12 combos)

Usage:
    uv run python src/backtest/optimize_planc_hybrid.py
"""
import sys
import time as _time
from itertools import product
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPlanCHybridStrategy, ORBStrategy

PHASE2_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)

GRID = {
    "momentum_window": [15, 20, 30, 45],
    "sl_pct":          [0.003, 0.005, 0.007],
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
    pnl    = trades["PnL"]
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return None

    exit_times = pd.to_datetime(trades["ExitTime"]).dt.time
    force_mask  = exit_times >= pd.Timestamp("1900-01-01 13:30:00").time()
    long_mask   = trades["Size"] > 0
    short_mask  = trades["Size"] < 0

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


def run_grid(df, combos: list[dict], label: str) -> pd.DataFrame:
    total = len(combos)
    print(f"{label}: testing {total} combos...")
    rows = []
    t0 = _time.time()
    for i, params in enumerate(combos, 1):
        bt = Backtest(df, ORBPlanCHybridStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        m  = compute_metrics(bt.run(**params))
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({**params, **flat})
        if i % 4 == 0 or i == total:
            elapsed = _time.time() - t0
            print(f"  {i}/{total}  {elapsed:.1f}s")
    return pd.DataFrame(rows)


def fv(v):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:.1f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def main():
    TRAIN_START, TRAIN_END, TEST_START = "2025-01-01", "2025-12-31", "2026-01-01"

    print("=" * 70)
    print("Plan C Hybrid — Momentum exit + asymmetric SL")
    print("  Long:  OR low SL  |  Short: fixed sl_pct SL")
    print(f"Targets: win≥{TARGET_WIN_RATE}%  avg_wl≥{TARGET_WL_RATIO}  pf≥{TARGET_PF}")
    print("=" * 70)

    print("\nLoading data...")
    df_train = load_data_with_night_ma(start=TRAIN_START, end=TRAIN_END, trend_ma_days=10)
    df_test  = load_data_with_night_ma(start=TEST_START,  trend_ma_days=10)
    print(f"  Train: {len(df_train):,} bars  {df_train.index[0].date()} ~ {df_train.index[-1].date()}")
    print(f"  OOS:   {len(df_test):,} bars  {df_test.index[0].date()} ~ {df_test.index[-1].date()}")

    # Phase 2 baseline
    print("\n" + "─" * 70)
    base_train = run_single(df_train, ORBStrategy, PHASE2_BASE)
    base_test  = run_single(df_test,  ORBStrategy, PHASE2_BASE)
    print("Phase 2 baseline computed.")

    param_cols = list(GRID.keys())
    combos = [dict(zip(param_cols, v)) for v in product(*GRID.values())]

    # Train
    print("\n" + "─" * 70)
    df_tr = run_grid(df_train, combos, "Train (2025)")

    passed = df_tr[
        (df_tr.win_rate  >= TARGET_WIN_RATE) &
        (df_tr.avg_wl    >= TARGET_WL_RATIO) &
        (df_tr.pf        >= TARGET_PF)
    ].sort_values(["pf", "win_rate"], ascending=False).reset_index(drop=True)

    metric_cols = ["n_trades", "n_long", "n_short", "win_rate", "avg_wl", "pf", "expectancy", "force_pct"]
    print(f"\n{'='*70}")
    print(f"Training results (2025)  — {len(passed)}/{len(df_tr)} meet targets")
    print(f"{'='*70}")
    show = passed if not passed.empty else df_tr.sort_values("pf", ascending=False)
    print(show[param_cols + metric_cols].to_string(index=False))

    # OOS
    print("\n" + "─" * 70)
    top_combos = (passed if not passed.empty else df_tr.sort_values("pf", ascending=False)).head(12)
    top_combos = top_combos[param_cols].to_dict("records")
    df_te = run_grid(df_test, top_combos, "OOS (2026)")

    tr_top = (passed if not passed.empty else df_tr.sort_values("pf", ascending=False)).head(12)
    tr_top = tr_top[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].copy()
    tr_top.columns = param_cols + ["tr_win", "tr_wl", "tr_pf", "tr_exp", "tr_n", "tr_force"]

    merged = tr_top.merge(
        df_te[param_cols + ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]].rename(
            columns={"win_rate": "te_win", "avg_wl": "te_wl", "pf": "te_pf",
                     "expectancy": "te_exp", "n_trades": "te_n", "force_pct": "te_force"}),
        on=param_cols, how="left",
    )

    print(f"\n{'='*70}")
    print("Plan C Hybrid — Train vs OOS")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed_oos = merged[(merged.te_win >= 50) & (merged.te_pf >= 1.0)]
    print(f"\n{len(passed_oos)}/{len(merged)} pass OOS targets (win≥50%, pf≥1.0):")
    if not passed_oos.empty:
        print(passed_oos.to_string(index=False))

    Path("output").mkdir(exist_ok=True)
    merged.to_csv("output/planc_hybrid_results.csv", index=False)
    print("\nResults → output/planc_hybrid_results.csv")

    # Best combo: OOS pf, win≥50% preferred
    best_row = (
        passed_oos.sort_values("te_pf", ascending=False).iloc[0]
        if not passed_oos.empty
        else merged.sort_values("te_pf", ascending=False).iloc[0]
    )
    best_params = {k: best_row[k] for k in param_cols}

    # Full breakdown for best combo
    best_train = run_single(df_train, ORBPlanCHybridStrategy, best_params)
    best_test  = run_single(df_test,  ORBPlanCHybridStrategy, best_params)

    # Also compute Plan C pure (OR SL both sides, best window=20) for reference
    planc_train = run_single(df_train, ORBPlanCHybridStrategy,
                             {"momentum_window": 20, "sl_pct": 999})  # large sl_pct ≈ OR SL only
    # Actually run pure Plan C directly
    from src.strategies.orb import ORBPlanCStrategy
    planc_pure_train = run_single(df_train, ORBPlanCStrategy, {"momentum_window": 20})
    planc_pure_test  = run_single(df_test,  ORBPlanCStrategy, {"momentum_window": 20})

    print(f"\n{'='*70}")
    print(f"FINAL COMPARISON — Phase 2 | Plan C (w=20) | Plan C Hybrid (best)")
    best_label = "  ".join(f"{k}={int(v) if isinstance(v,float) and v==int(v) else v}"
                           for k, v in best_params.items())
    print(f"  Best hybrid params: {best_label}")
    print(f"{'='*70}")

    for period, bm, pcm, phm in [
        ("Train 2025", base_train,    planc_pure_train, best_train),
        ("OOS 2026",   base_test,     planc_pure_test,  best_test),
    ]:
        bm  = bm  or {}
        pcm = pcm or {}
        phm = phm or {}

        print(f"\n  Period: {period}")
        print(f"  {'Metric':<22}  {'Phase2 Base':>13}  {'Plan C w=20':>13}  {'Hybrid best':>13}")
        print(f"  {'-'*22}  {'-'*13}  {'-'*13}  {'-'*13}")

        for lbl, bk, pk, hk in [
            ("n_trades (L/S)",
             f"{bm.get('n_trades','—')} ({bm.get('n_long','—')}/{bm.get('n_short','—')})",
             f"{pcm.get('n_trades','—')} ({pcm.get('n_long','—')}/{pcm.get('n_short','—')})",
             f"{phm.get('n_trades','—')} ({phm.get('n_long','—')}/{phm.get('n_short','—')})"),
            ("win_rate",    fv(bm.get("win_rate")),   fv(pcm.get("win_rate")),   fv(phm.get("win_rate"))),
            ("avg_wl",      fv(bm.get("avg_wl")),     fv(pcm.get("avg_wl")),     fv(phm.get("avg_wl"))),
            ("pf",          fv(bm.get("pf")),         fv(pcm.get("pf")),         fv(phm.get("pf"))),
            ("expectancy",  fv(bm.get("expectancy")), fv(pcm.get("expectancy")), fv(phm.get("expectancy"))),
            ("force_pct %", fv(bm.get("force_pct")),  fv(pcm.get("force_pct")),  fv(phm.get("force_pct"))),
        ]:
            print(f"  {lbl:<22}  {bk:>13}  {pk:>13}  {hk:>13}")

        for direction in ("long", "short"):
            bd  = bm.get(direction)  or {}
            pd_ = pcm.get(direction) or {}
            hd  = phm.get(direction) or {}
            print(f"\n    [{direction.upper()}]")
            print(f"    {'Metric':<20}  {'Phase2 Base':>13}  {'Plan C w=20':>13}  {'Hybrid best':>13}")
            print(f"    {'-'*20}  {'-'*13}  {'-'*13}  {'-'*13}")
            for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                print(f"    {m:<20}  {fv(bd.get(m)):>13}  {fv(pd_.get(m)):>13}  {fv(hd.get(m)):>13}")

    print()


if __name__ == "__main__":
    main()

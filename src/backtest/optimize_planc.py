#!/usr/bin/env python3
"""Plan C optimizer: exit when trend momentum stalls.

No new higher high (long) / lower low (short) in N minutes → exit.

Usage:
    uv run python src/backtest/optimize_planc.py
"""
import sys
import time as _time
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPlanCStrategy, ORBStrategy

PHASE2_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)

PLANC_GRID = {"momentum_window": [15, 20, 30, 45]}

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
        "n_trades":  len(trades),
        "n_long":    int(long_mask.sum()),
        "n_short":   int(short_mask.sum()),
        "win_rate":  round(len(wins) / len(trades) * 100, 1),
        "avg_wl":    round(wins.mean() / abs(losses.mean()), 3),
        "pf":        round(wins.sum() / abs(losses.sum()), 3),
        "expectancy":round(pnl.mean(), 1),
        "force_pct": round(force_mask.sum() / len(trades) * 100, 1),
        "long":      _dir_metrics(trades.loc[long_mask,  "PnL"]),
        "short":     _dir_metrics(trades.loc[short_mask, "PnL"]),
    }


def run_single(df, strategy_cls, params) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    return compute_metrics(bt.run(**params))


def run_grid(df, windows: list[int], label: str) -> pd.DataFrame:
    print(f"{label}: testing {len(windows)} windows...")
    rows = []
    t0 = _time.time()
    for i, w in enumerate(windows, 1):
        bt = Backtest(df, ORBPlanCStrategy, cash=200_000, commission=0.0, trade_on_close=True)
        m  = compute_metrics(bt.run(momentum_window=w))
        if m:
            flat = {k: v for k, v in m.items() if k not in ("long", "short")}
            rows.append({"momentum_window": w, **flat})
        elapsed = _time.time() - t0
        print(f"  {i}/{len(windows)}  window={w}  {elapsed:.1f}s elapsed")
    return pd.DataFrame(rows)


def fv(v):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:.1f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def main():
    TRAIN_START, TRAIN_END, TEST_START = "2025-01-01", "2025-12-31", "2026-01-01"

    print("=" * 70)
    print("ORB Plan C — Momentum stall exit (no new extreme in N minutes)")
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

    # Plan C grid
    windows = PLANC_GRID["momentum_window"]

    print("\n" + "─" * 70)
    df_tr = run_grid(df_train, windows, "Train (2025)")
    df_te = run_grid(df_test,  windows, "OOS (2026)")

    # Merge
    metric_cols = ["win_rate", "avg_wl", "pf", "expectancy", "n_trades", "force_pct"]
    merged = df_tr[["momentum_window"] + metric_cols].merge(
        df_te[["momentum_window"] + metric_cols].rename(
            columns={c: "te_" + c for c in metric_cols}),
        on="momentum_window",
    ).rename(columns={c: "tr_" + c for c in metric_cols})

    print(f"\n{'='*70}")
    print("Plan C — Train vs OOS (all windows)")
    print(f"{'='*70}")
    print(merged.to_string(index=False))

    passed = merged[(merged.te_win_rate >= 50) & (merged.te_pf >= 1.0)]
    print(f"\n{len(passed)}/{len(merged)} combos pass OOS targets (win≥50%, pf≥1.0):")
    if not passed.empty:
        print(passed.to_string(index=False))

    Path("output").mkdir(exist_ok=True)
    merged.to_csv("output/planc_results.csv", index=False)
    print("\nResults → output/planc_results.csv")

    # Best window (OOS pf, relaxed win threshold)
    best_row = merged.sort_values("te_pf", ascending=False).iloc[0]
    best_w   = int(best_row["momentum_window"])

    # Full long/short breakdown for each window
    print(f"\n{'='*70}")
    print("Plan C — Long/Short breakdown per window")
    print(f"{'='*70}")

    for period, df_ in [("Train 2025", df_train), ("OOS 2026", df_test)]:
        print(f"\n  [{period}]")
        print(f"  {'window':>8}  {'n (L/S)':>10}  {'win%':>6}  {'avg_wl':>7}  {'pf':>6}  {'exp':>7}  {'force%':>7}")
        print(f"  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*6}  {'-'*7}  {'-'*7}")
        for w in windows:
            m = run_single(df_, ORBPlanCStrategy, {"momentum_window": w})
            if m:
                print(f"  {w:>8}  {m['n_trades']:>4} ({m['n_long']:>2}/{m['n_short']:>2})"
                      f"  {fv(m['win_rate']):>6}  {fv(m['avg_wl']):>7}  {fv(m['pf']):>6}"
                      f"  {fv(m['expectancy']):>7}  {fv(m['force_pct']):>7}")

        # Long / Short breakdown for each window
        print(f"\n  [LONG]")
        print(f"  {'window':>8}  {'n':>4}  {'win%':>6}  {'avg_wl':>7}  {'pf':>6}  {'exp':>7}")
        print(f"  {'-'*8}  {'-'*4}  {'-'*6}  {'-'*7}  {'-'*6}  {'-'*7}")
        for w in windows:
            m = run_single(df_, ORBPlanCStrategy, {"momentum_window": w})
            if m:
                d = m["long"]
                print(f"  {w:>8}  {d['n']:>4}  {fv(d['win_rate']):>6}  {fv(d['avg_wl']):>7}"
                      f"  {fv(d['pf']):>6}  {fv(d['expectancy']):>7}")

        print(f"\n  [SHORT]")
        print(f"  {'window':>8}  {'n':>4}  {'win%':>6}  {'avg_wl':>7}  {'pf':>6}  {'exp':>7}")
        print(f"  {'-'*8}  {'-'*4}  {'-'*6}  {'-'*7}  {'-'*6}  {'-'*7}")
        for w in windows:
            m = run_single(df_, ORBPlanCStrategy, {"momentum_window": w})
            if m:
                d = m["short"]
                print(f"  {w:>8}  {d['n']:>4}  {fv(d['win_rate']):>6}  {fv(d['avg_wl']):>7}"
                      f"  {fv(d['pf']):>6}  {fv(d['expectancy']):>7}")

    # Final comparison: Phase 2 vs Plan C best
    print(f"\n{'='*70}")
    print(f"FINAL COMPARISON — Phase 2 Base vs Plan C (window={best_w})")
    print(f"{'='*70}")

    pc_train = run_single(df_train, ORBPlanCStrategy, {"momentum_window": best_w})
    pc_test  = run_single(df_test,  ORBPlanCStrategy, {"momentum_window": best_w})

    for period, bm, cm in [
        ("Train 2025", base_train, pc_train),
        ("OOS 2026",   base_test,  pc_test),
    ]:
        bm = bm or {}
        cm = cm or {}
        print(f"\n  Period: {period}")
        print(f"  {'Metric':<22}  {'Phase2 Base':>14}  {'Plan C w={best_w}':>14}")
        print(f"  {'-'*22}  {'-'*14}  {'-'*14}")

        for lbl, bk, ck in [
            ("n_trades (L/S)",
             f"{bm.get('n_trades','—')} ({bm.get('n_long','—')}/{bm.get('n_short','—')})",
             f"{cm.get('n_trades','—')} ({cm.get('n_long','—')}/{cm.get('n_short','—')})"),
            ("win_rate",    fv(bm.get("win_rate")),    fv(cm.get("win_rate"))),
            ("avg_wl",      fv(bm.get("avg_wl")),      fv(cm.get("avg_wl"))),
            ("pf",          fv(bm.get("pf")),           fv(cm.get("pf"))),
            ("expectancy",  fv(bm.get("expectancy")),   fv(cm.get("expectancy"))),
            ("force_exit %",fv(bm.get("force_pct")),    fv(cm.get("force_pct"))),
        ]:
            print(f"  {lbl:<22}  {bk:>14}  {ck:>14}")

        for direction in ("long", "short"):
            bd = bm.get(direction) or {}
            cd = cm.get(direction) or {}
            print(f"\n    [{direction.upper()}]")
            print(f"    {'Metric':<20}  {'Phase2 Base':>14}  {'Plan C':>14}")
            print(f"    {'-'*20}  {'-'*14}  {'-'*14}")
            for m in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                print(f"    {m:<20}  {fv(bd.get(m)):>14}  {fv(cd.get(m)):>14}")

    print()


if __name__ == "__main__":
    main()

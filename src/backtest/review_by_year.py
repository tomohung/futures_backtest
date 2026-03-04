#!/usr/bin/env python3
"""Year-by-year review: Phase 2 vs Plan C vs Plan C Hybrid.

Usage:
    uv run python src/backtest/review_by_year.py
"""
import sys
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBPlanCHybridStrategy, ORBPlanCStrategy, ORBStrategy

PHASE2_PARAMS = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)
PLANC_PARAMS        = dict(momentum_window=20)
PLANC_HYBRID_PARAMS = dict(momentum_window=20, sl_pct=0.007)

PERIODS = [
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
    if len(trades) < 5:
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
        "total_pnl":  round(pnl.sum(), 0),
        "force_pct":  round(force_mask.sum() / len(trades) * 100, 1),
        "long":       _dir_metrics(trades.loc[long_mask,  "PnL"]),
        "short":      _dir_metrics(trades.loc[short_mask, "PnL"]),
    }


def run(df, strategy_cls, params) -> dict | None:
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    return compute_metrics(bt.run(**params))


def fv(v, width=7):
    if v is None or (isinstance(v, float) and v != v):
        s = "—"
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        s = f"{v:.1f}"
    else:
        s = str(v)
    return s.rjust(width)


def main():
    print("=" * 70)
    print("Year-by-year review: Phase 2 | Plan C (w=20) | Plan C Hybrid (w=20, sl=0.7%)")
    print("=" * 70)

    results = {}  # period → {strategy → metrics}

    for label, start, end in PERIODS:
        print(f"\nLoading {label}...", end=" ", flush=True)
        df = load_data_with_night_ma(start=start, end=end, trend_ma_days=10)
        n_days = df.index.normalize().nunique()
        print(f"{len(df):,} bars  ({n_days} trading days)")

        results[label] = {
            "Phase 2":  run(df, ORBStrategy,           PHASE2_PARAMS),
            "Plan C":   run(df, ORBPlanCStrategy,      PLANC_PARAMS),
            "Hybrid":   run(df, ORBPlanCHybridStrategy, PLANC_HYBRID_PARAMS),
        }

    # ── Overall summary table ─────────────────────────────────────────────
    strategies = ["Phase 2", "Plan C", "Hybrid"]
    metrics_overall = [
        ("n (L/S)",    lambda m: f"{m['n_trades']} ({m['n_long']}/{m['n_short']})"),
        ("win%",       lambda m: fv(m["win_rate"])),
        ("avg_wl",     lambda m: fv(m["avg_wl"])),
        ("PF",         lambda m: fv(m["pf"])),
        ("exp/trade",  lambda m: fv(m["expectancy"])),
        ("total PnL",  lambda m: fv(m["total_pnl"], 8)),
        ("force%",     lambda m: fv(m["force_pct"])),
    ]

    print(f"\n{'='*70}")
    print("OVERALL — by year")
    print(f"{'='*70}")
    header = f"  {'Metric':<12}" + "".join(
        f"  {f'{yr} {s}':>14}"
        for yr in ["2024", "2025", "2026"]
        for s in strategies
    )
    print(header)
    print("  " + "-" * (12 + 3 * 3 * 16))

    for metric_label, fn in metrics_overall:
        row = f"  {metric_label:<12}"
        for yr in ["2024", "2025", "2026"]:
            for s in strategies:
                m = results[yr].get(s)
                val = fn(m) if m else "—".rjust(7)
                row += f"  {val:>14}"
        print(row)

    # ── Per-direction detail per year ─────────────────────────────────────
    for yr in ["2024", "2025", "2026"]:
        print(f"\n{'='*70}")
        print(f"  {yr} — Long / Short detail")
        print(f"{'='*70}")

        for direction in ("LONG", "SHORT"):
            key = direction.lower()
            print(f"\n  [{direction}]")
            print(f"  {'Metric':<12}  {'Phase 2':>10}  {'Plan C':>10}  {'Hybrid':>10}")
            print(f"  {'-'*12}  {'-'*10}  {'-'*10}  {'-'*10}")
            for m_label in ["n", "win_rate", "avg_wl", "pf", "expectancy"]:
                row = f"  {m_label:<12}"
                for s in strategies:
                    m = results[yr].get(s)
                    d = m.get(key, {}) if m else {}
                    v = d.get(m_label)
                    row += f"  {fv(v, 10)}"
                print(row)

    # ── Equity curve summary (cumulative PnL per year) ────────────────────
    print(f"\n{'='*70}")
    print("Cumulative PnL summary (points, size=1 contract)")
    print(f"{'='*70}")
    print(f"  {'Year':<6}  {'Phase 2':>10}  {'Plan C':>10}  {'Hybrid':>10}")
    print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*10}")
    running = {"Phase 2": 0, "Plan C": 0, "Hybrid": 0}
    for yr in ["2024", "2025", "2026"]:
        row = f"  {yr:<6}"
        for s in strategies:
            m = results[yr].get(s)
            yr_pnl = m["total_pnl"] if m else 0
            running[s] += yr_pnl
            row += f"  {fv(yr_pnl, 10)}"
        print(row)
    print(f"  {'Total':<6}", end="")
    for s in strategies:
        print(f"  {fv(running[s], 10)}", end="")
    print()


if __name__ == "__main__":
    main()

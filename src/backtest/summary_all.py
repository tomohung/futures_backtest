#!/usr/bin/env python3
"""Comprehensive summary of all strategies across 2024 / 2025 / 2026.

Usage:
    uv run python src/backtest/summary_all.py
"""
import sys
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import (
    ORBLongStrategy,
    ORBStrategy,
)

# ── Strategy definitions ──────────────────────────────────────────────────
STRATEGIES = {
    "Phase2 Base": (
        ORBStrategy,
        dict(range_end_minute=90, entry_end_minute=120, sl_pct=0.005,
             tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10),
        "SL=0.5%  TP=1.5×  trail@9:45"
    ),
    "Ph4 Hybrid": (
        ORBLongStrategy,
        dict(tp_or_multiplier=1.5, sl_pct=0.004),
        "Long TP=1.5×OR_width / Short TP=Phase2  SL=0.4%"
    ),
    "Ph4 Long-only": (
        ORBLongStrategy,
        dict(tp_or_multiplier=1.5, sl_pct=0.004, long_only=1),
        "Long-only  TP=1.5×OR_width  SL=0.4%"
    ),
}

PERIODS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


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

    def dir_m(mask):
        p = trades.loc[mask, "PnL"]
        if len(p) == 0:
            return {}
        w = p[p > 0]; l = p[p < 0]
        return {
            "n":     len(p),
            "win%":  round(len(w) / len(p) * 100, 1),
            "pf":    round(w.sum() / abs(l.sum()), 2) if len(l) and l.sum() != 0 else None,
            "exp":   round(p.mean(), 1),
        }

    return {
        "n":          len(trades),
        "n_long":     int(long_mask.sum()),
        "n_short":    int(short_mask.sum()),
        "win%":       round(len(wins) / len(trades) * 100, 1),
        "avg_wl":     round(wins.mean() / abs(losses.mean()), 2),
        "pf":         round(wins.sum() / abs(losses.sum()), 2),
        "exp":        round(pnl.mean(), 1),
        "total":      round(pnl.sum(), 0),
        "force%":     round(force_mask.sum() / len(trades) * 100, 1),
        "long":       dir_m(long_mask),
        "short":      dir_m(short_mask),
    }


def run(df, cls, params):
    bt = Backtest(df, cls, cash=200_000, commission=0.0, trade_on_close=True)
    return compute_metrics(bt.run(**params))


def fv(v, w=6):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.1f}".rjust(w)
    return str(v).rjust(w)


def main():
    # Load data
    print("Loading data...", flush=True)
    data = {}
    for label, start, end in PERIODS:
        df = load_data_with_night_ma(start=start, end=end, trend_ma_days=10)
        days = df.index.normalize().nunique()
        data[label] = df
        print(f"  {label}: {len(df):,} bars  {df.index[0].date()} ~ {df.index[-1].date()}  ({days} days)")

    # Run all strategies
    print("\nRunning strategies...", flush=True)
    results = {}   # strategy → period → metrics
    for name, (cls, params, _) in STRATEGIES.items():
        results[name] = {}
        for label, _, _ in PERIODS:
            results[name][label] = run(data[label], cls, params)
        print(f"  ✓ {name}")

    # ── Strategy legend ───────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("STRATEGY LEGEND")
    print(f"{'='*72}")
    for name, (_, _, desc) in STRATEGIES.items():
        print(f"  {name:<16}  {desc}")

    # ── Main table ────────────────────────────────────────────────────────
    metric_defs = [
        ("n (L/S)",  lambda m: f"{m['n']}({m['n_long']}/{m['n_short']})"),
        ("win%",     lambda m: fv(m["win%"])),
        ("avg_wl",   lambda m: fv(m["avg_wl"])),
        ("PF",       lambda m: fv(m["pf"])),
        ("exp/trade",lambda m: fv(m["exp"])),
        ("total PnL",lambda m: fv(m["total"], 7)),
        ("force%",   lambda m: fv(m["force%"])),
    ]

    for period_label, _, _ in PERIODS:
        print(f"\n{'='*72}")
        print(f"  {period_label}")
        print(f"{'='*72}")
        print(f"  {'Metric':<12}" + "".join(f"  {s:>14}" for s in STRATEGIES))
        print(f"  {'-'*12}" + "".join(f"  {'-'*14}" for _ in STRATEGIES))

        for m_label, fn in metric_defs:
            row = f"  {m_label:<12}"
            for name in STRATEGIES:
                m = results[name].get(period_label)
                row += f"  {fn(m):>14}" if m else f"  {'—':>14}"
            print(row)

        # Long / Short sub-rows
        for direction in ("long", "short"):
            print(f"\n  [{direction.upper()}]")
            print(f"  {'Metric':<12}" + "".join(f"  {s:>14}" for s in STRATEGIES))
            print(f"  {'-'*12}" + "".join(f"  {'-'*14}" for _ in STRATEGIES))
            for sub in ["n", "win%", "pf", "exp"]:
                row = f"  {sub:<12}"
                for name in STRATEGIES:
                    m = results[name].get(period_label)
                    d = m.get(direction, {}) if m else {}
                    v = d.get(sub)
                    row += f"  {fv(v):>14}"
                print(row)

    # ── Cumulative PnL ────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("CUMULATIVE PnL  (points, 1 contract, no commission)")
    print(f"{'='*72}")
    print(f"  {'Year':<6}" + "".join(f"  {s:>14}" for s in STRATEGIES))
    print(f"  {'-'*6}" + "".join(f"  {'-'*14}" for _ in STRATEGIES))

    totals = {s: 0.0 for s in STRATEGIES}
    for period_label, _, _ in PERIODS:
        row = f"  {period_label:<6}"
        for name in STRATEGIES:
            m = results[name].get(period_label)
            yr_pnl = m["total"] if m else 0
            totals[name] += yr_pnl
            row += f"  {fv(yr_pnl, 7):>14}"
        print(row)

    print(f"  {'Total':<6}" + "".join(f"  {fv(totals[s], 7):>14}" for s in STRATEGIES))

    # ── Quick verdict ─────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    rows = [
        ("2024 profitable?",  lambda s: "✓" if (results[s].get("2024") or {}).get("total", 0) > 0 else "✗"),
        ("2025 profitable?",  lambda s: "✓" if (results[s].get("2025") or {}).get("total", 0) > 0 else "✗"),
        ("2026 profitable?",  lambda s: "✓" if (results[s].get("2026") or {}).get("total", 0) > 0 else "✗"),
        ("All 3 years +?",    lambda s: "✓" if all(
            (results[s].get(yr) or {}).get("total", 0) > 0
            for yr in ["2024", "2025", "2026"]) else "✗"),
        ("OOS PF > 2.0?",     lambda s: "✓" if (results[s].get("2026") or {}).get("pf", 0) > 2.0 else "✗"),
        ("3yr total PnL",     lambda s: fv(totals[s], 7)),
    ]
    print(f"  {'Check':<18}" + "".join(f"  {s:>14}" for s in STRATEGIES))
    print(f"  {'-'*18}" + "".join(f"  {'-'*14}" for _ in STRATEGIES))
    for label, fn in rows:
        print(f"  {label:<18}" + "".join(f"  {fn(s):>14}" for s in STRATEGIES))

    # ── Per-strategy year table ────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("YEAR-BY-YEAR DETAIL — per strategy")
    print(f"{'='*72}")
    HDR = (f"  {'Year':<6}  {'n(L/S)':>9}  {'win%':>6}  {'L win%':>7}  {'S win%':>7}"
           f"  {'exp':>6}  {'L exp':>7}  {'S exp':>7}  {'PF':>5}  {'total':>8}")
    SEP = (f"  {'-'*6}  {'-'*9}  {'-'*6}  {'-'*7}  {'-'*7}"
           f"  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*5}  {'-'*8}")

    def _dv(d, key, w=7):
        v = d.get(key) if d else None
        return fv(v, w)

    for name in STRATEGIES:
        _, _, desc = STRATEGIES[name]
        print(f"\n  [{name}]  {desc}")
        print(HDR)
        print(SEP)
        cum = 0.0
        for period_label, _, _ in PERIODS:
            m = results[name].get(period_label)
            if not m:
                print(f"  {period_label:<6}  {'—':>9}")
                continue
            ls   = f"{m['n_long']}/{m['n_short']}"
            lwin = _dv(m.get("long"),  "win%")
            swin = _dv(m.get("short"), "win%")
            lexp = _dv(m.get("long"),  "exp")
            sexp = _dv(m.get("short"), "exp")
            cum += m["total"]
            print(f"  {period_label:<6}  {ls:>9}  {fv(m['win%'], 6):>6}"
                  f"  {lwin:>7}  {swin:>7}"
                  f"  {fv(m['exp'], 6):>6}  {lexp:>7}  {sexp:>7}"
                  f"  {fv(m['pf'], 5):>5}  {fv(m['total'], 8):>8}")
        print(SEP)
        print(f"  {'TOTAL':<6}  {'':>9}  {'':>6}  {'':>7}  {'':>7}"
              f"  {'':>6}  {'':>7}  {'':>7}  {'':>5}  {fv(cum, 8):>8}")

    print()


if __name__ == "__main__":
    main()

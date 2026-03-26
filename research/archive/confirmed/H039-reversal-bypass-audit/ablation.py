#!/usr/bin/env python3
"""
H039 Phase 2: Ablation backtest — A+B+C+D (current) vs A+D (simplified)

Compares the full Reversal strategy against a version with only
CCD (A) + 2nd BB touch (D), removing Exhaustion (B) and VWAP bypass (C).
"""
import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).parents[3]))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


class ReversalAblation(ReversalStrategy):
    """Reversal with toggleable bypass conditions."""
    use_exhaust: int = 1    # B: exhaustion bypass (int for backtesting.py)
    use_vwap:    int = 1    # C: intraday VWAP bypass

    def next(self):
        # Patch: temporarily disable exhaustion/vwap latches if toggled off
        if not self.use_exhaust:
            self._bull_exhausted = False
            self._bear_exhausted = False
        # For VWAP, we need to intercept the setup logic.
        # Override is done via _sum_vol trick: set to 0 so vwap=None
        self.__orig_sum_vol = self._sum_vol
        if not self.use_vwap:
            self._sum_vol = 0.0

        super().next()

        # Restore
        if not self.use_vwap:
            self._sum_vol = self.__orig_sum_vol


YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

CONFIGS = [
    ("A+B+C+D (current)", {"use_exhaust": 1, "use_vwap": 1}),
    ("A+D (simplified)",  {"use_exhaust": 0, "use_vwap": 0}),
    ("A+B+D (no VWAP)",   {"use_exhaust": 1, "use_vwap": 0}),
    ("A+C+D (no Exhaust)",{"use_exhaust": 0, "use_vwap": 1}),
]


def year_sweep(df_all, params):
    rows = []
    all_trades = []
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, ReversalAblation, cash=200_000,
                      commission=0.0, trade_on_close=True)
        result = bt.run(**params)
        trades = result["_trades"]
        if len(trades) == 0:
            rows.append({"year": yr, "n": 0, "win": None, "exp": None,
                          "total": 0.0, "sharpe": None})
            continue
        pnl = trades["PnL"]
        entry = trades["EntryPrice"]
        pnl_pct = pnl / entry * 100
        n = len(pnl)
        win = round(len(pnl[pnl > 0]) / n * 100, 1)
        exp = round(pnl.mean(), 1)
        tot = round(pnl.sum(), 0)
        sharpe = round(pnl_pct.mean() / pnl_pct.std(), 2) if pnl_pct.std() > 0 else None
        rows.append({"year": yr, "n": n, "win": win, "exp": exp,
                      "total": tot, "sharpe": sharpe})
        all_trades.append(trades)

    total = sum(r["total"] for r in rows)
    rows.append({"year": "TOTAL", "n": sum(r["n"] for r in rows),
                 "win": None, "exp": None, "total": total, "sharpe": None})

    # Overall Sharpe
    if all_trades:
        all_t = pd.concat(all_trades)
        pnl_pct = all_t["PnL"] / all_t["EntryPrice"] * 100
        if pnl_pct.std() > 0:
            rows[-1]["sharpe"] = round(pnl_pct.mean() / pnl_pct.std(), 2)

    return pd.DataFrame(rows)


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def main():
    t0 = _time.time()
    print("=" * 80)
    print("H039 Phase 2: Reversal Bypass Ablation Backtest")
    print("=" * 80)

    print("\nLoading data...", flush=True)
    df_all = load_data_for_reversal()
    print(f"  {len(df_all):,} bars  {df_all.index[0].date()} ~ {df_all.index[-1].date()}")

    results = {}
    for label, params in CONFIGS:
        print(f"\nRunning: {label} ...", flush=True)
        df_sw = year_sweep(df_all, params)
        results[label] = df_sw

    # ── Print results ──────────────────────────────────────────────
    for label, df_sw in results.items():
        print(f"\n{'=' * 80}")
        print(f"  {label}")
        print(f"  {'Year':<6}  {'n':>5}  {'win%':>7}  {'exp':>7}  {'Total':>9}  {'Sharpe':>7}")
        print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*7}")
        for _, r in df_sw.iterrows():
            print(f"  {r['year']:<6}  {fv(r['n'], 5, 0):>5}  "
                  f"{fv(r['win']):>7}  {fv(r['exp']):>7}  "
                  f"{fv(r['total'], 9, 0):>9}  {fv(r['sharpe']):>7}")

    # ── Side-by-side comparison ────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("SIDE-BY-SIDE COMPARISON")
    print(f"{'=' * 80}")

    yr_labels = [yr for yr, *_ in YEARS] + ["TOTAL"]
    header = f"  {'Year':<6}"
    for label, _ in CONFIGS:
        short = label.split(" ")[0]
        header += f"  {'n':>4} {'win%':>5} {'total':>7}"
    print(header)

    for yr in yr_labels:
        line = f"  {yr:<6}"
        for label, _ in CONFIGS:
            df_sw = results[label]
            r = df_sw[df_sw["year"] == yr].iloc[0]
            n = int(r["n"]) if r["n"] and not np.isnan(r["n"]) else 0
            w = f"{r['win']:.0f}%" if r["win"] is not None and not np.isnan(r["win"]) else "—"
            t = f"{r['total']:+.0f}" if r["total"] else "0"
            line += f"  {n:4d} {w:>5} {t:>7}"
        print(line)

    # ── Delta: simplified vs current ───────────────────────────────
    print(f"\n{'=' * 80}")
    print("DELTA: A+D (simplified) vs A+B+C+D (current)")
    print(f"{'=' * 80}")
    curr = results["A+B+C+D (current)"]
    simp = results["A+D (simplified)"]
    print(f"  {'Year':<6}  {'N_curr':>6} {'N_simp':>6} {'ΔN':>4}  "
          f"{'Tot_curr':>8} {'Tot_simp':>8} {'ΔTotal':>8}  "
          f"{'Win_curr':>8} {'Win_simp':>8}")
    for yr in yr_labels:
        rc = curr[curr["year"] == yr].iloc[0]
        rs = simp[simp["year"] == yr].iloc[0]
        nc = int(rc["n"]) if not np.isnan(rc["n"]) else 0
        ns = int(rs["n"]) if not np.isnan(rs["n"]) else 0
        tc = rc["total"] or 0
        ts_ = rs["total"] or 0
        wc = f"{rc['win']:.1f}%" if rc["win"] is not None and not np.isnan(rc["win"]) else "—"
        ws = f"{rs['win']:.1f}%" if rs["win"] is not None and not np.isnan(rs["win"]) else "—"
        dt = ts_ - tc
        print(f"  {yr:<6}  {nc:6d} {ns:6d} {ns-nc:+4d}  "
              f"{tc:+8.0f} {ts_:+8.0f} {dt:+8.0f}  "
              f"{wc:>8} {ws:>8}")

    print(f"\nTotal time: {_time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

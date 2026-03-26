#!/usr/bin/env python3
"""H044 Phase 2: Test BC zone direction variants.

Variant A (baseline): current logic
  - above BC → long only
  - below BC → short only
  - inside BC → follow MA

Variant B: inside BC → both directions
  - above BC → long only
  - below BC → short only
  - inside BC → both allowed

Variant C: inside BC → both, outside follows MA if conflict
  - above BC → long only (but if MA bearish → both)
  - below BC → short only (but if MA bullish → both)
  - inside BC → both
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


class ReversalInsideBoth(ReversalStrategy):
    """Variant B: inside BC zone allows both directions."""

    def next(self):
        cur_ts = self.data.index[-1]
        cur_date = cur_ts.date()

        # Override the BC inside resolution before calling super
        if cur_date != self._prev_date:
            # Let parent handle day rollover first
            pass

        super().next()

    def _reset_daily(self):
        super()._reset_daily()
        self._bc_inside_override = False

    def next(self):
        cur_ts = self.data.index[-1]
        cur_date = cur_ts.date()

        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date
            self._open_price = float(self.data.Open[-1])
            self._day_low = float(self.data.Low[-1])
            self._day_high = float(self.data.High[-1])

            bc1 = float(self.data.VWAP1[-1])
            bc2 = float(self.data.VWAP2[-1])
            if not (np.isnan(bc1) or np.isnan(bc2)):
                bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
                if self._open_price > bc_hi:
                    self._allow_long = True
                elif self._open_price < bc_lo:
                    self._allow_short = True
                else:
                    # VARIANT B: inside → both directions
                    self._allow_long = True
                    self._allow_short = True

        # Skip the parent's next() day-rollover since we handled it
        # Call the rest of parent logic via a direct copy approach
        # Actually, easier: just call the parent but prevent it from re-doing day rollover
        # We already set _prev_date, so parent's day rollover won't trigger again
        super().next()


class ReversalInsideBothMaOverride(ReversalStrategy):
    """Variant C: inside → both, outside → both if MA conflicts."""

    def _reset_daily(self):
        super()._reset_daily()

    def next(self):
        cur_ts = self.data.index[-1]
        cur_date = cur_ts.date()

        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date
            self._open_price = float(self.data.Open[-1])
            self._day_low = float(self.data.Low[-1])
            self._day_high = float(self.data.High[-1])

            bc1 = float(self.data.VWAP1[-1])
            bc2 = float(self.data.VWAP2[-1])

            # Read MA direction
            ma5m = float(self.data.MA5m_120[-1])
            ma5m_prev = float(self.data.MA5m_120_Prev[-1])
            ma_bullish = (not np.isnan(ma5m) and not np.isnan(ma5m_prev)
                          and ma5m > ma5m_prev)

            if not (np.isnan(bc1) or np.isnan(bc2)):
                bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
                if self._open_price > bc_hi:
                    self._allow_long = True
                    # If MA is bearish (conflicts with "above BC → long only"), also allow short
                    if not ma_bullish:
                        self._allow_short = True
                elif self._open_price < bc_lo:
                    self._allow_short = True
                    # If MA is bullish (conflicts with "below BC → short only"), also allow long
                    if ma_bullish:
                        self._allow_long = True
                else:
                    # Inside → both
                    self._allow_long = True
                    self._allow_short = True

        super().next()


PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
)

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and v != v):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def compute_pf(pnl):
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0
    return wins / losses


def run_variant(df_all, strategy_cls, label):
    print(f"\n{'=' * 72}")
    print(f"  {label}")
    print(f"{'=' * 72}")
    print(f"  {'Year':<6}  {'N':>5}  {'Win%':>7}  {'Avg':>7}  {'Total':>9}  {'PF':>6}")
    print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*6}")

    all_pnl = []
    for yr, start, end in YEARS:
        df = df_all[df_all.index >= start]
        if end:
            df = df[df.index <= end]
        bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
        trades = bt.run(**PARAMS)["_trades"]
        if len(trades) == 0:
            print(f"  {yr:<6}  {0:>5}  {'—':>7}  {'—':>7}  {'—':>9}  {'—':>6}")
            continue
        pnl = trades["PnL"]
        all_pnl.append(pnl)
        n = len(pnl)
        win = (pnl > 0).sum() / n * 100
        avg = pnl.mean()
        total = pnl.sum()
        pf = compute_pf(pnl)
        print(f"  {yr:<6}  {n:>5}  {win:>6.1f}%  {avg:>7.1f}  {total:>+9.0f}  {pf:>6.2f}")

    if all_pnl:
        combined = pd.concat(all_pnl)
        n = len(combined)
        win = (combined > 0).sum() / n * 100
        avg = combined.mean()
        total = combined.sum()
        pf = compute_pf(combined)
        print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*6}")
        print(f"  {'ALL':<6}  {n:>5}  {win:>6.1f}%  {avg:>7.1f}  {total:>+9.0f}  {pf:>6.2f}")


def main():
    print("Loading data...")
    df_all = load_data_for_reversal()

    run_variant(df_all, ReversalStrategy, "A (baseline): current BC zone logic")
    run_variant(df_all, ReversalInsideBoth, "B: inside BC → both directions")
    run_variant(df_all, ReversalInsideBothMaOverride,
                "C: inside → both, outside → both if MA conflicts")
    print()


if __name__ == "__main__":
    main()

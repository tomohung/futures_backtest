#!/usr/bin/env python3
"""H044 Phase 2: Test Near-SatZone latch variants for Reversal.

A (baseline): near-SatZone → permanent latch (current)
B: no near-SatZone latch at all
C: near-SatZone latch resets when price pulls back EmaHL * 0.25 from extreme
D: near-SatZone latch resets when price pulls back EmaHL * 0.5 from extreme
"""
import sys
from collections import deque
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy
from src.strategies.estimate_hl_exit import EstimateHLExitMixin

# ── Variant B: No near-SatZone latch ─────────────────────────────────────

class ReversalNoSatLatch(ReversalStrategy):
    """Remove the near-SatZone entry latch entirely."""

    def next(self):
        # Call parent, but override near_sat_latch to always be False
        super().next()

    def _check_near_sat_and_enter(self):
        """Override not possible directly, so we patch in next()."""
        pass

    def next(self):
        cur_ts = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close = float(self.data.Close[-1])

        # Day rollover (copied from parent)
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
                    self._bc_inside = True

        if self._day_low is not None:
            self._day_low = min(self._day_low, float(self.data.Low[-1]))
            self._day_high = max(self._day_high, float(self.data.High[-1]))

        self._record_bar()

        # Exit logic
        if self.position:
            if cur_time >= dtime(13, 40):
                self.position.close()
                return
            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close()
                    return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close()
                    return
            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close()
                    return
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close()
                    return
            if cur_time >= dtime(9, 45):
                if self.position.is_long:
                    self._low_buf.append(float(self.data.Low[-1]))
                    if len(self._low_buf) == 11:
                        lows = list(self._low_buf)
                        if lows[5] == min(lows):
                            if self._trail_stop is None or lows[5] > self._trail_stop:
                                self._trail_stop = lows[5]
                    if self._trail_stop is not None and close < self._trail_stop:
                        self.position.close()
                        return
                elif self.position.is_short:
                    self._high_buf.append(float(self.data.High[-1]))
                    if len(self._high_buf) == 11:
                        highs = list(self._high_buf)
                        if highs[5] == max(highs):
                            if self._trail_stop is None or highs[5] < self._trail_stop:
                                self._trail_stop = highs[5]
                    if self._trail_stop is not None and close > self._trail_stop:
                        self.position.close()
                        return
            return

        if self._entered or self._satzone_reached:
            return

        ema_hl = float(self.data.EmaHL[-1])
        ma5m = float(self.data.MA5m_120[-1])
        ma5m_prev = float(self.data.MA5m_120_Prev[-1])
        bb_upper = float(self.data.BB_Upper[-1])
        bb_lower = float(self.data.BB_Lower[-1])
        vol = float(self.data.Volume[-1])
        vol_ma = float(self.data.VolMA20[-1])
        ccd = float(self.data.CCD_5m[-1])
        ma5 = float(self.data.MA5_1m[-1])

        if any(np.isnan(v) for v in
               [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
            return

        sl = ema_hl * self.sl_ema_fraction
        vol_ok = vol > self.vol_ratio * vol_ma
        bullish = ma5m > ma5m_prev

        if getattr(self, '_bc_inside', False):
            self._bc_inside = False
            if bullish:
                self._allow_long = True
            else:
                self._allow_short = True

        if not (self._allow_long or self._allow_short):
            return

        exhaust_frac = self.exhaust_fraction
        if not self._bull_exhausted and self._day_low is not None:
            if close >= self._day_low + ema_hl * exhaust_frac:
                self._bull_exhausted = True
        if not self._bear_exhausted and self._day_high is not None:
            if close <= self._day_high - ema_hl * exhaust_frac:
                self._bear_exhausted = True

        if self._allow_long and bullish and not self._bb_long_touched:
            if close <= bb_lower and vol_ok:
                self._bb_long_touched = True
                self._bb_long_count += 1
        if self._allow_short and not bullish and not self._bb_short_touched:
            if close >= bb_upper and vol_ok:
                self._bb_short_touched = True
                self._bb_short_count += 1

        if dtime(9, 10) <= cur_time <= dtime(10, 5):
            long_setup = (self._allow_long and bullish and
                          self._bb_long_touched and
                          (ccd > 0 or self._bear_exhausted
                           or self._bb_long_count >= 2))
            short_setup = (self._allow_short and not bullish and
                           self._bb_short_touched and
                           (ccd < 0 or self._bull_exhausted
                            or self._bb_short_count >= 2))

            # NO near-SatZone check — this is the variant
            if long_setup and close > ma5:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.buy(size=1)
                    self._sl_price = close - sl
                    self._entered = True
            elif short_setup and close < ma5:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.sell(size=1)
                    self._sl_price = close + sl
                    self._entered = True

        if close > ma5:
            self._bb_long_touched = False
        if close < ma5:
            self._bb_short_touched = False


# ── Variant C/D: Near-SatZone latch with pullback reset ──────────────────

class ReversalSatPullbackReset(ReversalStrategy):
    """Near-SatZone latch resets when price pulls back from extreme."""

    pullback_fraction: float = 0.25  # reset when pullback >= EmaHL * fraction

    def _reset_daily(self):
        super()._reset_daily()
        self._sat_extreme_high = None  # high when near-sat triggered
        self._sat_extreme_low = None

    def next(self):
        cur_ts = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close = float(self.data.Close[-1])

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
                    self._bc_inside = True

        if self._day_low is not None:
            self._day_low = min(self._day_low, float(self.data.Low[-1]))
            self._day_high = max(self._day_high, float(self.data.High[-1]))

        self._record_bar()

        # Exit logic (same as parent)
        if self.position:
            if cur_time >= dtime(13, 40):
                self.position.close()
                return
            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close()
                    return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close()
                    return
            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close()
                    return
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close()
                    return
            if cur_time >= dtime(9, 45):
                if self.position.is_long:
                    self._low_buf.append(float(self.data.Low[-1]))
                    if len(self._low_buf) == 11:
                        lows = list(self._low_buf)
                        if lows[5] == min(lows):
                            if self._trail_stop is None or lows[5] > self._trail_stop:
                                self._trail_stop = lows[5]
                    if self._trail_stop is not None and close < self._trail_stop:
                        self.position.close()
                        return
                elif self.position.is_short:
                    self._high_buf.append(float(self.data.High[-1]))
                    if len(self._high_buf) == 11:
                        highs = list(self._high_buf)
                        if highs[5] == max(highs):
                            if self._trail_stop is None or highs[5] < self._trail_stop:
                                self._trail_stop = highs[5]
                    if self._trail_stop is not None and close > self._trail_stop:
                        self.position.close()
                        return
            return

        if self._entered or self._satzone_reached:
            return

        ema_hl = float(self.data.EmaHL[-1])
        ma5m = float(self.data.MA5m_120[-1])
        ma5m_prev = float(self.data.MA5m_120_Prev[-1])
        bb_upper = float(self.data.BB_Upper[-1])
        bb_lower = float(self.data.BB_Lower[-1])
        vol = float(self.data.Volume[-1])
        vol_ma = float(self.data.VolMA20[-1])
        ccd = float(self.data.CCD_5m[-1])
        ma5 = float(self.data.MA5_1m[-1])

        if any(np.isnan(v) for v in
               [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
            return

        sl = ema_hl * self.sl_ema_fraction
        vol_ok = vol > self.vol_ratio * vol_ma
        bullish = ma5m > ma5m_prev

        if getattr(self, '_bc_inside', False):
            self._bc_inside = False
            if bullish:
                self._allow_long = True
            else:
                self._allow_short = True

        if not (self._allow_long or self._allow_short):
            return

        exhaust_frac = self.exhaust_fraction
        if not self._bull_exhausted and self._day_low is not None:
            if close >= self._day_low + ema_hl * exhaust_frac:
                self._bull_exhausted = True
        if not self._bear_exhausted and self._day_high is not None:
            if close <= self._day_high - ema_hl * exhaust_frac:
                self._bear_exhausted = True

        if self._allow_long and bullish and not self._bb_long_touched:
            if close <= bb_lower and vol_ok:
                self._bb_long_touched = True
                self._bb_long_count += 1
        if self._allow_short and not bullish and not self._bb_short_touched:
            if close >= bb_upper and vol_ok:
                self._bb_short_touched = True
                self._bb_short_count += 1

        if dtime(9, 10) <= cur_time <= dtime(10, 5):
            long_setup = (self._allow_long and bullish and
                          self._bb_long_touched and
                          (ccd > 0 or self._bear_exhausted
                           or self._bb_long_count >= 2))
            short_setup = (self._allow_short and not bullish and
                           self._bb_short_touched and
                           (ccd < 0 or self._bull_exhausted
                            or self._bb_short_count >= 2))

            # Near-SatZone with pullback reset
            sat_upper = float(self.data.SatZoneUpper[-1])
            sat_lower = float(self.data.SatZoneLower[-1])
            margin = ema_hl / 8

            if not self._near_sat_latch:
                near_sat_up = (not np.isnan(sat_upper) and self._day_high is not None
                               and sat_upper - self._day_high <= margin)
                near_sat_dn = (not np.isnan(sat_lower) and self._day_low is not None
                               and self._day_low - sat_lower <= margin)
                if near_sat_up or near_sat_dn:
                    self._near_sat_latch = True
                    self._sat_extreme_high = self._day_high
                    self._sat_extreme_low = self._day_low

            # Pullback reset: if price has pulled back enough from the extreme
            if self._near_sat_latch and ema_hl > 0:
                pullback_threshold = ema_hl * self.pullback_fraction
                # If high was near upper SatZone, check if price pulled back down
                if (self._sat_extreme_high is not None and
                        self._sat_extreme_high - close >= pullback_threshold):
                    self._near_sat_latch = False
                # If low was near lower SatZone, check if price pulled back up
                if (self._sat_extreme_low is not None and
                        close - self._sat_extreme_low >= pullback_threshold):
                    self._near_sat_latch = False

            if long_setup and close > ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.buy(size=1)
                    self._sl_price = close - sl
                    self._entered = True
            elif short_setup and close < ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.sell(size=1)
                    self._sl_price = close + sl
                    self._entered = True

        if close > ma5:
            self._bb_long_touched = False
        if close < ma5:
            self._bb_short_touched = False


# ── Runner ───────────────────────────────────────────────────────────────

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


def compute_pf(pnl):
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0
    return wins / losses


def run_variant(df_all, strategy_cls, label, extra_params=None):
    params = {**PARAMS, **(extra_params or {})}
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
        trades = bt.run(**params)["_trades"]
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

    run_variant(df_all, ReversalStrategy,
                "A (baseline): near-SatZone permanent latch")
    run_variant(df_all, ReversalNoSatLatch,
                "B: no near-SatZone latch")
    run_variant(df_all, ReversalSatPullbackReset,
                "C: near-SatZone resets on pullback EmaHL*0.25",
                {"pullback_fraction": 0.25})
    run_variant(df_all, ReversalSatPullbackReset,
                "D: near-SatZone resets on pullback EmaHL*0.5",
                {"pullback_fraction": 0.5})
    print()


if __name__ == "__main__":
    main()

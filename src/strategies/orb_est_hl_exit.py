"""
ORB with Estimated H-L Exit Strategy.

Entry: ORB breakout (8:45–8:57 range, 8:58–9:05 window) filtered by
  - 30m 20MA direction (Close30 vs MA30_20)
  - BigCost institutional cost filter (OR breakout must be on correct side)

Exit priority (highest to lowest):
  1. Fixed SL: entry ± 0.25 × EmaHL
  2. SatZone two-phase exit (from EstimateHLExitMixin)
  3. Dow Theory pivot trailing stop (active after 9:45)
  4. Force exit at 13:30
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_OR_START  = dtime(8, 45)
_OR_END    = dtime(8, 57)
_ENTRY_START = dtime(8, 58)
_ENTRY_END   = dtime(9, 5)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)


class ORBWithEstHLExitStrategy(EstimateHLExitMixin, Strategy):
    """ORB entry + SatZone / Dow trailing stop exits."""

    sl_ema_fraction: float = 0.25
    adx_min: float = 0.0    # 0 = disabled; e.g. 20 to require ADX > 20
    long_only: bool = True
    bigcost_days: int = 2   # lookback window for BigCost filter (1–5)

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        self._reset_daily()

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._entered: bool = False
        self._sl_price: float | None = None
        self._low_buf: deque = deque(maxlen=5)
        self._high_buf: deque = deque(maxlen=5)
        self._dow_trail_stop: float | None = None

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])

        # ── Day rollover ───────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date

        # Always record bar for SatZone mixin
        self._record_bar()

        # ── Build Opening Range (8:45–8:57) ───────────────────────────
        if _OR_START <= cur_time <= _OR_END:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low  = min(self._or_low,  float(self.data.Low[-1]))

        # ── Entry window (8:58–9:05), at most once per day ────────────
        if (not self._entered
                and _ENTRY_START <= cur_time <= _ENTRY_END
                and self._or_high != -np.inf):

            ema_hl  = float(self.data.EmaHL[-1])
            if np.isnan(ema_hl):
                pass  # insufficient warmup; skip entry
            else:
                ma30    = float(self.data.MA30_20[-1])
                close30 = float(self.data.Close30[-1])
                bc_vals = [float(getattr(self.data, f"BigCost{i}")[-1])
                           for i in range(1, self.bigcost_days + 1)]
                or_width   = float(self.data.ORWidth[-1])
                rolling_or = float(self.data.RollingOR[-1])
                sl_dist = self.sl_ema_fraction * ema_hl

                trend_nan = np.isnan(ma30) or np.isnan(close30)

                # OR width filter: must be 0.5–1.5× rolling average (skip if no warmup)
                if not np.isnan(rolling_or):
                    if not (0.5 * rolling_or <= or_width <= 1.5 * rolling_or):
                        return

                # ADX filter
                if self.adx_min > 0:
                    adx = float(self.data.DailyADX[-1])
                    if not np.isnan(adx) and adx < self.adx_min:
                        return

                valid_bc = [v for v in bc_vals if not np.isnan(v)]

                if close > self._or_high:
                    trend_ok = trend_nan or (close30 > ma30)
                    cost_ok  = (not valid_bc
                                or self._or_high > max(valid_bc) + 0.5 * sl_dist)
                    if trend_ok and cost_ok:
                        self.buy(size=1)
                        self._sl_price = close - sl_dist
                        self._entered = True

                elif close < self._or_low and not self.long_only:
                    trend_ok = trend_nan or (close30 < ma30)
                    cost_ok  = (not valid_bc
                                or self._or_low < min(valid_bc) - 0.5 * sl_dist)
                    if trend_ok and cost_ok:
                        self.sell(size=1)
                        self._sl_price = close + sl_dist
                        self._entered = True

        # ── Exit logic (only when in a position) ──────────────────────
        if not self.position:
            return

        # 1. Fixed stop-loss
        if self._sl_price is not None:
            if self.position.is_long and close < self._sl_price:
                self.position.close()
                return
            if self.position.is_short and close > self._sl_price:
                self.position.close()
                return

        # 2. SatZone two-phase exit
        if self.position.is_long and self._check_long_exit():
            self.position.close()
            return
        if self.position.is_short and self._check_short_exit():
            self.position.close()
            return

        # 3. Dow Theory trailing stop (active after 9:45)
        if cur_time >= _TRAIL_START:
            if self.position.is_long:
                self._low_buf.append(float(self.data.Low[-1]))
                if len(self._low_buf) == 5:
                    lows = list(self._low_buf)
                    # bar at index 2 (i-2) is confirmed pivot low if it's min of all 5
                    if lows[2] == min(lows):
                        if self._dow_trail_stop is None or lows[2] > self._dow_trail_stop:
                            self._dow_trail_stop = lows[2]
                if self._dow_trail_stop is not None and close < self._dow_trail_stop:
                    self.position.close()
                    return

            elif self.position.is_short:
                self._high_buf.append(float(self.data.High[-1]))
                if len(self._high_buf) == 5:
                    highs = list(self._high_buf)
                    if highs[2] == max(highs):
                        if self._dow_trail_stop is None or highs[2] < self._dow_trail_stop:
                            self._dow_trail_stop = highs[2]
                if self._dow_trail_stop is not None and close > self._dow_trail_stop:
                    self.position.close()
                    return

        # 4. Force exit at 13:30
        if cur_time >= _FORCE_EXIT:
            self.position.close()

"""
ORB with Estimated H-L Split Exit Strategy (H031 Phase 2).

Same entry logic as ORBWithEstHLExitStrategy, but with split exit:
  - Close `satzone_exit_portion` at SatZone (Phase 2 = 5MA confirmation)
  - Trail remaining with `trail_ema_fraction × EmaHL` trailing stop

Parameters (on top of base strategy):
  satzone_exit_portion : float = 1.0   Fraction to close at SatZone (1.0 = baseline)
  trail_ema_fraction   : float = 0.3   Trailing stop = fraction × EmaHL from peak
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_split_exit import EstimateHLSplitExitMixin

_OR_START = dtime(8, 45)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT = dtime(13, 30)


class ORBWithEstHLSplitExitStrategy(EstimateHLSplitExitMixin, Strategy):
    """ORB entry + split SatZone / trailing stop exits."""

    sl_ema_fraction: float = 0.25
    adx_min: float = 0.0
    long_only: bool = True
    vwap_days: int = 2
    or_end_min: int = 537
    entry_end_min: int = 555
    skip_thursday: bool = True
    skip_friday: bool = True
    # Split exit params
    satzone_exit_portion: float = 1.0  # 1.0 = baseline (close all at SatZone)
    trail_ema_fraction: float = 0.3
    entry_size: int = 1  # use >=10 for meaningful partial closes

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        self._or_end = dtime(self.or_end_min // 60, self.or_end_min % 60)
        h, m = divmod(self.or_end_min + 1, 60)
        self._entry_start = dtime(h, m)
        self._entry_end = dtime(self.entry_end_min // 60, self.entry_end_min % 60)
        self._reset_daily()

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._entered: bool = False
        self._sl_price: float | None = None
        self._low_buf: deque = deque(maxlen=11)
        self._high_buf: deque = deque(maxlen=11)
        self._dow_trail_stop: float | None = None

    def next(self):
        cur_ts = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close = float(self.data.Close[-1])

        # Day rollover
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date

        self._record_bar()

        # Build Opening Range
        if _OR_START <= cur_time <= self._or_end:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low = min(self._or_low, float(self.data.Low[-1]))

        # Skip days
        _wd = cur_date.weekday()
        if self.skip_thursday and _wd == 3:
            return
        if self.skip_friday and _wd == 4:
            return

        # Entry window
        if (not self._entered
                and not self._satzone_reached
                and self._entry_start <= cur_time <= self._entry_end
                and self._or_high != -np.inf):

            ema_hl = float(self.data.EmaHL[-1])
            if not np.isnan(ema_hl):
                ma30 = float(self.data.MA30_20[-1])
                close30 = float(self.data.Close30[-1])
                bc_vals = [float(getattr(self.data, f"VWAP{i}")[-1])
                           for i in range(1, self.vwap_days + 1)]
                or_width = float(self.data.ORWidth[-1])
                rolling_or = float(self.data.RollingOR[-1])
                sl_dist = self.sl_ema_fraction * ema_hl

                trend_nan = np.isnan(ma30) or np.isnan(close30)

                if not np.isnan(rolling_or):
                    if not (0.5 * rolling_or <= or_width <= 1.5 * rolling_or):
                        return

                if self.adx_min > 0:
                    adx = float(self.data.DailyADX[-1])
                    if not np.isnan(adx) and adx < self.adx_min:
                        return

                valid_bc = [v for v in bc_vals if not np.isnan(v)]

                if close > self._or_high:
                    trend_ok = trend_nan or (close30 > ma30)
                    cost_ok = (not valid_bc
                               or self._or_high > max(valid_bc) + 0.5 * sl_dist)
                    if trend_ok and cost_ok:
                        self.buy(size=self.entry_size)
                        self._sl_price = close - sl_dist
                        self._entered = True

                elif close < self._or_low and not self.long_only:
                    trend_ok = trend_nan or (close30 < ma30)
                    cost_ok = (not valid_bc
                               or self._or_low < min(valid_bc) - 0.5 * sl_dist)
                    if trend_ok and cost_ok:
                        self.sell(size=self.entry_size)
                        self._sl_price = close + sl_dist
                        self._entered = True

        # Exit logic
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

        # 2. Split SatZone exit
        if self.position.is_long:
            action = self._check_long_split_exit()
            if action == "partial":
                self.position.close(portion=self.satzone_exit_portion)
                # Don't return — remaining position stays open
            elif action == "full":
                self.position.close()
                return
        elif self.position.is_short:
            action = self._check_short_split_exit()
            if action == "partial":
                self.position.close(portion=self.satzone_exit_portion)
            elif action == "full":
                self.position.close()
                return

        # 3. Dow Theory trailing stop (only if partial NOT done yet — once split,
        #    the trailing stop in the mixin handles the remainder)
        if not self._split_partial_done and cur_time >= _TRAIL_START:
            if self.position.is_long:
                self._low_buf.append(float(self.data.Low[-1]))
                if len(self._low_buf) == 11:
                    lows = list(self._low_buf)
                    if lows[5] == min(lows):
                        if self._dow_trail_stop is None or lows[5] > self._dow_trail_stop:
                            self._dow_trail_stop = lows[5]
                if self._dow_trail_stop is not None and close < self._dow_trail_stop:
                    self.position.close()
                    return
            elif self.position.is_short:
                self._high_buf.append(float(self.data.High[-1]))
                if len(self._high_buf) == 11:
                    highs = list(self._high_buf)
                    if highs[5] == max(highs):
                        if self._dow_trail_stop is None or highs[5] < self._dow_trail_stop:
                            self._dow_trail_stop = highs[5]
                if self._dow_trail_stop is not None and close > self._dow_trail_stop:
                    self.position.close()
                    return

        # 4. Force exit at 13:30
        if cur_time >= _FORCE_EXIT:
            self.position.close()

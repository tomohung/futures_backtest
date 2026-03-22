"""
ORB with EstHL Latch + New-High Confirmation Strategy.

Entry: Same filters as ORBWithEstHLExitStrategy, but the breakout signal only
       "arms" a latch.  Actual entry happens when price makes a new session high
       after the latch is armed.

Two confirmation modes:
  Mode 0 (any_bar):    Any 1-min bar's High > session high at latch time → enter.
  Mode 1 (5min_close): Wait for a 5-min candle to close, and its High during that
                        candle > session high at latch time → enter.

Exit priority (identical to ORBWithEstHLExitStrategy):
  1. Fixed SL: entry - sl_ema_fraction × EmaHL
  2. SatZone two-phase exit (from EstimateHLExitMixin)
  3. Dow Theory pivot trailing stop (active after 9:45)
  4. Force exit at 13:30

Parameters:
  confirm_mode        : int   = 0      0=any_bar, 1=5min_close
  latch_entry_end_min : int   = 630    Deadline for confirmed entry (default 10:30)
  sl_ema_fraction     : float = 0.25   SL distance as fraction of EmaHL
  bigcost_days        : int   = 2      Days of BigCost history (1–5)
  long_only           : bool  = True   Disable short trades
  adx_min             : float = 0.0    Min daily ADX14 to trade (0 = disabled)
  or_end_min          : int   = 537    OR end time in minutes (default 8:57)
  entry_end_min       : int   = 555    Latch arm window end in minutes (default 9:15)
  skip_thursday       : bool  = True   Skip Thursdays
  skip_friday         : bool  = True   Skip Fridays
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_OR_START    = dtime(8, 45)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)


class ORBEstHLLatchStrategy(EstimateHLExitMixin, Strategy):
    """ORB latch entry + SatZone / Dow trailing stop exits."""

    sl_ema_fraction: float = 0.25
    adx_min: float = 0.0
    long_only: bool = True
    bigcost_days: int = 2
    or_end_min: int = 537
    entry_end_min: int = 555
    skip_thursday: bool = True
    skip_friday: bool = True
    confirm_mode: int = 0           # 0=any_bar, 1=5min_close
    latch_entry_end_min: int = 630  # 10:30

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        self._or_end = dtime(self.or_end_min // 60, self.or_end_min % 60)
        h, m = divmod(self.or_end_min + 1, 60)
        self._entry_start = dtime(h, m)
        self._entry_end = dtime(self.entry_end_min // 60, self.entry_end_min % 60)
        self._latch_entry_end = dtime(self.latch_entry_end_min // 60,
                                      self.latch_entry_end_min % 60)
        self._reset_daily()

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._entered: bool = False
        self._sl_price: float | None = None
        self._low_buf: deque = deque(maxlen=11)
        self._high_buf: deque = deque(maxlen=11)
        self._dow_trail_stop: float | None = None
        # Latch state
        self._latch_armed: bool = False
        self._session_high: float = -np.inf
        self._session_high_at_latch: float = -np.inf
        self._latch_sl_dist: float | None = None
        # 5-min candle tracking (Mode 1)
        self._5min_slot: int = -1
        self._5min_candle_high: float = -np.inf
        self._prev_5min_candle_high: float = -np.inf  # completed candle's high

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])
        high     = float(self.data.High[-1])

        # ── Day rollover ─────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date

        # Always record bar for SatZone mixin
        self._record_bar()

        # ── Track session high from 8:45 onward ─────────────────────
        if cur_time >= _OR_START:
            self._session_high = max(self._session_high, high)

        # ── Track 5-min candle (Mode 1) ──────────────────────────────
        if self.confirm_mode == 1 and cur_time >= _OR_START:
            cur_slot = (cur_ts.hour * 60 + cur_ts.minute) // 5 * 5
            if cur_slot != self._5min_slot:
                # New 5-min candle started → previous candle is complete
                self._prev_5min_candle_high = self._5min_candle_high
                self._5min_candle_high = high
                self._5min_slot = cur_slot
            else:
                self._5min_candle_high = max(self._5min_candle_high, high)

        # ── Build Opening Range (8:45–or_end) ────────────────────────
        if _OR_START <= cur_time <= self._or_end:
            self._or_high = max(self._or_high, high)
            self._or_low  = min(self._or_low, float(self.data.Low[-1]))

        # ── Weekday skip ─────────────────────────────────────────────
        _wd = cur_date.weekday()
        if self.skip_thursday and _wd == 3:
            return
        if self.skip_friday and _wd == 4:
            return

        # ── Latch arming phase (entry_start – entry_end) ────────────
        if (not self._latch_armed
                and not self._entered
                and not self._satzone_reached
                and self._entry_start <= cur_time <= self._entry_end
                and self._or_high != -np.inf):

            ema_hl = float(self.data.EmaHL[-1])
            if not np.isnan(ema_hl):
                ma30    = float(self.data.MA30_20[-1])
                close30 = float(self.data.Close30[-1])
                bc_vals = [float(getattr(self.data, f"BigCost{i}")[-1])
                           for i in range(1, self.bigcost_days + 1)]
                or_width   = float(self.data.ORWidth[-1])
                rolling_or = float(self.data.RollingOR[-1])
                sl_dist = self.sl_ema_fraction * ema_hl

                trend_nan = np.isnan(ma30) or np.isnan(close30)

                # OR width filter
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
                        # ARM the latch — do not enter yet
                        self._latch_armed = True
                        self._session_high_at_latch = self._session_high
                        self._latch_sl_dist = sl_dist

        # ── Confirmation phase (latch armed, wait for new high) ──────
        if (self._latch_armed
                and not self._entered
                and not self._satzone_reached
                and cur_time <= self._latch_entry_end):

            confirmed = False

            if self.confirm_mode == 0:
                # Mode 0: any bar's High > session high at latch time
                if high > self._session_high_at_latch:
                    confirmed = True
            else:
                # Mode 1: completed 5-min candle's High > session high at latch
                cur_slot = (cur_ts.hour * 60 + cur_ts.minute) // 5 * 5
                if cur_slot != self._5min_slot:
                    # Slot just changed — _prev_5min_candle_high was set above
                    pass  # check below uses _prev_5min_candle_high
                if (self._prev_5min_candle_high > self._session_high_at_latch
                        and self._prev_5min_candle_high != -np.inf):
                    confirmed = True

            if confirmed:
                self.buy(size=1)
                self._sl_price = close - self._latch_sl_dist
                self._entered = True

        # ── Exit logic (only when in a position) ─────────────────────
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

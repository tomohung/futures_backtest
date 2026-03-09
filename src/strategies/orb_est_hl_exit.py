"""
ORB with Estimated H-L Exit Strategy.

Entry: ORB breakout (8:45–8:57 range, 8:58–9:05 window), long-only by default.

Entry filters (all must pass):
  1. Close > or_high (upward breakout)
  2. Close30 > MA30_20 (30m 20MA uptrend, from continuous day+night series)
  3. or_high > max(BigCost1..N) + 0.5 × sl_dist  (breakout above institutional cost)
  4. 0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR (normal opening range width)

Exit priority (highest to lowest):
  1. Fixed SL: entry - sl_ema_fraction × EmaHL  (default 0.25)
  2. SatZone two-phase exit (from EstimateHLExitMixin)
  3. Dow Theory pivot trailing stop (5-bar lookback, 2-bar confirmation, active after 9:45)
  4. Force exit at 13:30

Parameters:
  sl_ema_fraction : float = 0.25   SL distance as fraction of EmaHL
  bigcost_days    : int   = 2      Days of BigCost history to take max of (1–5)
  long_only       : bool  = True   Disable short trades
  adx_min         : float = 0.0   Min daily ADX14 to trade (0 = disabled)
  or_end_min      : int   = 537    OR end time as minutes since midnight (default 8:57)
  entry_end_min   : int   = 545    Entry window end as minutes since midnight (default 9:05)

Backtest results (2021–2026-03, long-only, bigcost_days=2, OR-width filter):
  2021–2024 : 125 trades  WR 58.4%  PF 1.90  EV +15.5 pts/trade
  2025      :  38 trades  WR 50.0%  PF 1.50  EV +16.7 pts/trade  +634 pts
  2026 YTD  :   6 trades  WR 50.0%  PF 2.74  EV +47.2 pts/trade  +283 pts
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_OR_START  = dtime(8, 45)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)


class ORBWithEstHLExitStrategy(EstimateHLExitMixin, Strategy):
    """ORB entry + SatZone / Dow trailing stop exits."""

    sl_ema_fraction: float = 0.25
    adx_min: float = 0.0    # 0 = disabled; e.g. 20 to require ADX > 20
    long_only: bool = True
    bigcost_days: int = 2   # lookback window for BigCost filter (1–5)
    or_end_min: int = 537   # OR end time in minutes since midnight (default 8:57)
    entry_end_min: int = 545  # entry window end in minutes since midnight (default 9:05)

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        # Precompute time objects from integer params
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

        # ── Build Opening Range (8:45–or_end) ─────────────────────────
        if _OR_START <= cur_time <= self._or_end:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low  = min(self._or_low,  float(self.data.Low[-1]))

        # ── Entry window (or_end+1min – entry_end), at most once per day ──
        if (not self._entered
                and self._entry_start <= cur_time <= self._entry_end
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

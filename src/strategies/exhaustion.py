"""
Exhaustion Strategy（趨勢竭盡反轉策略）— S003

Entry premise:
  當趨勢延伸到 Bollinger Band 之外，夜盤又進一步推升創新極值，
  表示多/空方力竭。在日盤 ORB 被反向突破時進場。

Entry conditions:
  多方竭盡做空:
    1. 30m SMA(20) 方向向上 (MA30_20 > MA30_20_Prev)
    2. 30m BB%B(20, open, 2σ) > 1  → column BB30_Above
    3. 夜盤 high > 近二日日盤 high  → column NightNewHigh
    4. ORB(08:45–08:57) 被跌破 (close < ORB_Low)
    5. ORB% >= 0.25%
    6. 非週三、非週四

  空方竭盡做多:
    1. 30m SMA(20) 方向向下 (MA30_20 < MA30_20_Prev)
    2. 30m BB%B(20, open, 2σ) < 0  → column BB30_Below
    3. 夜盤 low < 近二日日盤 low    → column NightNewLow
    4. ORB(08:45–08:57) 被突破 (close > ORB_High)
    5. ORB% >= 0.25%
    6. 非週三、非週四

Exit (same as EstHL):
  1. Fixed SL: entry ± EmaHL × sl_fraction
  2. SatZone two-phase exit (touch → close crosses 5MA)
  3. Dow Theory trailing stop (09:45+)
  4. Force exit at 13:30

Data loader: load_data_for_exhaustion() in src/backtest/runner.py
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_ENTRY_START = dtime(9, 0)   # ORB done at 08:58, entry from 09:00
_ENTRY_END   = dtime(10, 30)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)


class ExhaustionStrategy(EstimateHLExitMixin, Strategy):
    """Trend exhaustion reversal strategy (S003)."""

    sl_fraction:   float = 0.25   # SL = EmaHL × fraction
    min_orb_pct:   float = 0.25   # ORB width / open × 100 minimum
    skip_wed:      bool  = True
    skip_thu:      bool  = True

    def init(self):
        self._prev_date = None
        self._init_estimate_hl_exit()
        self._reset_daily()

    def _reset_daily(self):
        self._entered    = False
        self._or_high    = None
        self._or_low     = None
        self._day_open   = None
        self._or_done    = False
        self._sl_price   = None
        self._trail_stop = None
        self._low_buf    = deque(maxlen=11)   # pivotlow(5,5)
        self._high_buf   = deque(maxlen=11)   # pivothigh(5,5)

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])
        high     = float(self.data.High[-1])
        low      = float(self.data.Low[-1])

        # ── Day rollover ──────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date
            self._day_open  = float(self.data.Open[-1])

        # ── Build Opening Range (08:45–08:58) ─────────────────────────
        if dtime(8, 45) <= cur_time <= dtime(8, 58):
            if self._or_high is None:
                self._or_high = high
                self._or_low  = low
            else:
                self._or_high = max(self._or_high, high)
                self._or_low  = min(self._or_low, low)
        elif cur_time > dtime(8, 58) and not self._or_done:
            self._or_done = True

        # ── SatZone exit mixin: record bar ────────────────────────────
        self._record_bar()

        # ── Exit logic (runs whenever in a position) ──────────────────
        if self.position:
            # 1. Force exit
            if cur_time >= _FORCE_EXIT:
                self.position.close()
                return

            # 2. Fixed SL
            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close()
                    return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close()
                    return

            # 3. SatZone two-phase exit
            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close()
                    return
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close()
                    return

            # 4. Pivot trailing stop (active after 09:45)
            if cur_time >= _TRAIL_START:
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

            return  # in position but no exit triggered

        # ── Already entered today or SatZone reached → skip entry ─────
        if self._entered or self._satzone_reached:
            return

        # ── Pre-conditions: OR must be done, within entry window ──────
        if not self._or_done or not (_ENTRY_START <= cur_time <= _ENTRY_END):
            return

        # ── Read indicators ──────────────────────────────────────────
        ema_hl = float(self.data.EmaHL[-1])
        if np.isnan(ema_hl):
            return

        # Weekday filter (0=Mon, 2=Wed, 3=Thu)
        weekday = cur_date.weekday()
        if self.skip_wed and weekday == 2:
            return
        if self.skip_thu and weekday == 3:
            return

        # ORB% filter
        if self._or_high is None or self._or_low is None or self._day_open is None:
            return
        or_width = self._or_high - self._or_low
        if self._day_open <= 0:
            return
        orb_pct = or_width / self._day_open * 100
        if orb_pct < self.min_orb_pct:
            return

        # 30m MA direction
        ma30     = float(self.data.MA30_20[-1])
        ma30_prev = float(self.data.MA30_20_Prev[-1])
        if np.isnan(ma30) or np.isnan(ma30_prev):
            return
        ma_up   = ma30 > ma30_prev
        ma_down = ma30 < ma30_prev

        # BB%B extremes (pre-computed boolean columns)
        bb_above = bool(self.data.BB30_Above[-1])
        bb_below = bool(self.data.BB30_Below[-1])

        # Night session new extremes (pre-computed boolean columns)
        night_new_high = bool(self.data.NightNewHigh[-1])
        night_new_low  = bool(self.data.NightNewLow[-1])

        sl = ema_hl * self.sl_fraction

        # ── Bull exhaustion → short ───────────────────────────────────
        if ma_up and bb_above and night_new_high:
            if close < self._or_low:
                self.sell(size=1)
                self._sl_price = close + sl
                self._entered  = True
                return

        # ── Bear exhaustion → long ────────────────────────────────────
        if ma_down and bb_below and night_new_low:
            if close > self._or_high:
                self.buy(size=1)
                self._sl_price = close - sl
                self._entered  = True
                return

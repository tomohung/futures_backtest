"""
Reversal Follow Strategy（轉折回歸 — 第二筆跟進策略）

Same setup/trigger logic as ReversalStrategy, but:
  - Skips the 1st trigger, only records entry price and direction
  - On 2nd trigger, checks if the 1st trade's direction is developing
    favorably (current close vs 1st entry price)
  - Only enters if the move is confirmed (1st trade would be profitable now)

This avoids lookahead: we don't need to know the 1st trade's final PnL,
just whether the market has moved in the expected direction since the 1st
signal fired.

Entry condition (on top of ReversalStrategy's setup/trigger):
  Long  : 2nd trigger AND close > 1st_entry_price  (uptrend intact)
  Short : 2nd trigger AND close < 1st_entry_price  (downtrend intact)

All other logic (BC zone gate, direction, exit) identical to ReversalStrategy.

Data loader: load_data_for_reversal() in src/backtest/runner.py
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

_ENTRY_START  = dtime(9, 0)
_ENTRY_END    = dtime(13, 0)
_TRAIL_START  = dtime(9, 45)
_FORCE_EXIT   = dtime(13, 40)


class ReversalFollowStrategy(Strategy):
    """Enter on 2nd reversal signal only if 1st signal's direction confirmed."""

    vol_ratio:       float = 1.5   # volume must exceed vol_ratio × VolMA20
    sl_ema_fraction: float = 0.35  # SL = EmaHL × fraction
    tp_ema_fraction: float = 1.0   # TP = EmaHL × fraction

    def init(self):
        self._prev_date = None
        self._reset_daily()

    def _reset_daily(self):
        self._entered      = False
        self._allow_long   = False
        self._allow_short  = False
        self._open_price   = None
        self._setup_long   = False
        self._setup_short  = False
        self._trigger_count = 0
        self._first_entry_price = None  # price at 1st trigger
        self._first_direction   = None  # 'L' or 'S'
        self._sl_price    = None
        self._tp_price    = None
        self._trail_stop  = None
        self._low_buf     = deque(maxlen=11)
        self._high_buf    = deque(maxlen=11)

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])

        # ── Day rollover ───────────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date  = cur_date
            self._open_price = float(self.data.Open[-1])

            bc1 = float(self.data.BigCost1[-1])
            bc2 = float(self.data.BigCost2[-1])
            if not (np.isnan(bc1) or np.isnan(bc2)):
                bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
                if self._open_price > bc_hi:
                    self._allow_long = True
                elif self._open_price < bc_lo:
                    self._allow_short = True
                else:
                    self._allow_long = True
                    self._allow_short = True

        # ── Exit logic (identical to ReversalStrategy) ────────────────────
        if self.position:
            if cur_time >= _FORCE_EXIT:
                self.position.close()
                return

            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close()
                    return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close()
                    return
            if self._tp_price is not None:
                if self.position.is_long and close >= self._tp_price:
                    self.position.close()
                    return
                if self.position.is_short and close <= self._tp_price:
                    self.position.close()
                    return

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

            return

        # ── Entry gate checks ─────────────────────────────────────────────
        if self._entered or not (self._allow_long or self._allow_short):
            return
        if not (_ENTRY_START <= cur_time <= _ENTRY_END):
            return

        # ── Read indicators ──────────────────────────────────────────────
        ema_hl     = float(self.data.EmaHL[-1])
        ma5m       = float(self.data.MA5m_120[-1])
        ma5m_prev  = float(self.data.MA5m_120_Prev[-1])
        bb_upper   = float(self.data.BB_Upper[-1])
        bb_lower   = float(self.data.BB_Lower[-1])
        vol        = float(self.data.Volume[-1])
        vol_ma     = float(self.data.VolMA20[-1])
        ccd        = float(self.data.CCD_5m[-1])
        ma5        = float(self.data.MA5_1m[-1])

        if any(np.isnan(v) for v in
               [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
            return

        sl     = ema_hl * self.sl_ema_fraction
        tp     = ema_hl * self.tp_ema_fraction
        vol_ok = vol > self.vol_ratio * vol_ma
        bullish = ma5m > ma5m_prev

        # ── Step 1: Latch setup ──────────────────────────────────────────
        if self._allow_long and bullish and not self._setup_long:
            if close <= bb_lower and vol_ok and ccd > 0:
                self._setup_long = True

        if self._allow_short and not bullish and not self._setup_short:
            if close >= bb_upper and vol_ok and ccd < 0:
                self._setup_short = True

        # ── Step 2: Trigger on MA5 cross ─────────────────────────────────
        if self._allow_long and bullish and self._setup_long and close > ma5:
            self._trigger_count += 1

            if self._trigger_count == 1:
                # 1st trigger: record but don't enter
                self._first_entry_price = close
                self._first_direction = 'L'

            elif self._trigger_count == 2:
                # 2nd trigger: enter only if 1st direction confirmed
                if (self._first_direction == 'L'
                        and close > self._first_entry_price):
                    self.buy(size=1)
                    self._sl_price = close - sl
                    self._tp_price = close + tp
                    self._entered  = True

        elif self._allow_short and not bullish and self._setup_short and close < ma5:
            self._trigger_count += 1

            if self._trigger_count == 1:
                self._first_entry_price = close
                self._first_direction = 'S'

            elif self._trigger_count == 2:
                if (self._first_direction == 'S'
                        and close < self._first_entry_price):
                    self.sell(size=1)
                    self._sl_price = close + sl
                    self._tp_price = close - tp
                    self._entered  = True

        # ── Reset setup once MA5 is crossed ──────────────────────────────
        if close > ma5:
            self._setup_long = False
        if close < ma5:
            self._setup_short = False

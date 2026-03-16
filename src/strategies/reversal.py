"""
Reversal Strategy（轉折回歸策略）

Entry premise (BC zone gate):
  BigCost1 = yesterday's institutional VWAP, BigCost2 = day-before.
  - Open between BC1 and BC2 → both long and short allowed
  - Open below BC zone       → short only (price already weak)
  - Open above BC zone       → long only  (price already strong)
  - BC data missing (NaN)    → skip day

Direction: 5m K 120MA 斜率（等同 30m 20MA 時間跨度，但每 5 分鐘更新）
  Bullish day  : MA5m_120 > MA5m_120_Prev  (MA 向上)
  Bearish day  : MA5m_120 < MA5m_120_Prev  (MA 向下)

Two-step entry (sequential):

  Step 1 — Setup (latch flag when ALL of the following are true):
    Long  : close ≤ BB_Lower (1m BB(15,2) oversold) AND volume > vol_ratio × VolMA20
            AND CCD_5m > 0
    Short : close ≥ BB_Upper (1m BB overbought)     AND volume > vol_ratio × VolMA20
            AND CCD_5m < 0

  Step 2 — Trigger (entry on FIRST bar after setup where):
    Long  : close > MA5_1m  (price crosses back above 1m 5-MA)
    Short : close < MA5_1m  (price crosses back below 1m 5-MA)

  The setup flag resets when close crosses MA5 (opportunity passed).
  Once triggered and entered, no further entries are taken that day.

  signal_skip (default 0): number of valid triggers to skip before entering.
    signal_skip=0 → enter on the 1st trigger (original behaviour)
    signal_skip=1 → skip the 1st trigger, enter on the 2nd

Exit priority (highest to lowest):
  1. Fixed SL : entry ∓ EmaHL × sl_ema_fraction
  2. Fixed TP : entry ± EmaHL × tp_ema_fraction
  3. Pivot trailing stop (active after 09:45): pivotlow(5,5) for long,
     pivothigh(5,5) for short — trailing stop ratchets in the favorable direction
  4. Force exit at 13:40

Entry window: 09:00 – 13:00
One entry per day maximum (after skipping signal_skip triggers).

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


class ReversalStrategy(Strategy):
    """Sequential BB-extreme → MA5 cross entry within institutional cost zone."""

    vol_ratio:       float = 1.5   # volume must exceed vol_ratio × VolMA20
    sl_ema_fraction: float = 0.35  # SL = EmaHL × fraction
    tp_ema_fraction: float = 1.0   # TP = EmaHL × fraction
    signal_skip:     int   = 0     # skip first N triggers before entering

    def init(self):
        self._prev_date   = None
        self._reset_daily()

    def _reset_daily(self):
        self._entered      = False
        self._allow_long   = False
        self._allow_short  = False
        self._open_price   = None
        self._setup_long  = False
        self._setup_short = False
        self._trigger_count = 0
        self._sl_price    = None
        self._tp_price    = None
        self._trail_stop  = None
        self._low_buf     = deque(maxlen=11)   # pivotlow(5,5)
        self._high_buf    = deque(maxlen=11)   # pivothigh(5,5)

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
                if self._open_price > bc_hi:       # above zone → long only
                    self._allow_long = True
                elif self._open_price < bc_lo:     # below zone → short only
                    self._allow_short = True
                else:                              # inside zone → both
                    self._allow_long = True
                    self._allow_short = True

        # ── Exit logic (runs whenever in a position) ───────────────────────
        if self.position:
            # 1. Force exit
            if cur_time >= _FORCE_EXIT:
                self.position.close()
                return

            # 2. Fixed SL / TP
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

            # 3. Pivot trailing stop (active after 09:45)
            if cur_time >= _TRAIL_START:
                if self.position.is_long:
                    self._low_buf.append(float(self.data.Low[-1]))
                    if len(self._low_buf) == 11:
                        lows = list(self._low_buf)
                        if lows[5] == min(lows):   # center bar is pivot low
                            if self._trail_stop is None or lows[5] > self._trail_stop:
                                self._trail_stop = lows[5]
                    if self._trail_stop is not None and close < self._trail_stop:
                        self.position.close()
                        return

                elif self.position.is_short:
                    self._high_buf.append(float(self.data.High[-1]))
                    if len(self._high_buf) == 11:
                        highs = list(self._high_buf)
                        if highs[5] == max(highs):  # center bar is pivot high
                            if self._trail_stop is None or highs[5] < self._trail_stop:
                                self._trail_stop = highs[5]
                    if self._trail_stop is not None and close > self._trail_stop:
                        self.position.close()
                        return

            return  # in position but no exit triggered

        # ── Entry gate checks ──────────────────────────────────────────────
        if self._entered or not (self._allow_long or self._allow_short):
            return
        if not (_ENTRY_START <= cur_time <= _ENTRY_END):
            return

        # ── Read indicators ───────────────────────────────────────────────
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
        bullish = ma5m > ma5m_prev   # 5m 120MA 斜率向上

        # ── Step 1: Latch setup ───────────────────────────────────────────
        if self._allow_long and bullish and not self._setup_long:
            if close <= bb_lower and vol_ok and ccd > 0:
                self._setup_long = True

        if self._allow_short and not bullish and not self._setup_short:
            if close >= bb_upper and vol_ok and ccd < 0:
                self._setup_short = True

        # ── Step 2: Trigger on MA5 cross ──────────────────────────────────
        triggered = False
        if self._allow_long and bullish and self._setup_long and close > ma5:
            self._trigger_count += 1
            triggered = True
            if self._trigger_count > self.signal_skip:
                self.buy(size=1)
                self._sl_price = close - sl
                self._tp_price = close + tp
                self._entered  = True

        elif self._allow_short and not bullish and self._setup_short and close < ma5:
            self._trigger_count += 1
            triggered = True
            if self._trigger_count > self.signal_skip:
                self.sell(size=1)
                self._sl_price = close + sl
                self._tp_price = close - tp
                self._entered  = True

        # ── Reset setup once MA5 is crossed (opportunity passed) ─────────
        if close > ma5:
            self._setup_long = False
        if close < ma5:
            self._setup_short = False

"""
Reversal Strategy（轉折回歸策略）

Entry premise (BC zone gate):
  VWAP1 = yesterday's institutional VWAP, VWAP2 = day-before.
  - Open above BC zone       → long only  (price already strong)
  - Open below BC zone       → short only (price already weak)
  - Open inside BC zone      → direction follows MA (bullish → long, bearish → short)
  - BC data missing (NaN)    → skip day

Direction: 5m 120MA direction (same as EstHL Pine Script)
  Bullish  : MA5m_120 > MA5m_120_Prev  (MA trending up)
  Bearish  : MA5m_120 < MA5m_120_Prev  (MA trending down)

Two-step entry (sequential):

  Step 1 — Setup (latch flag when ALL of the following are true):
    Long  : close <= BB_Lower (1m BB(15,2) oversold) AND volume > vol_ratio * VolMA20
    Short : close >= BB_Upper (1m BB overbought)     AND volume > vol_ratio * VolMA20

  Step 2 — Trigger (entry on FIRST bar after setup where):
    CCD gate: CCD_5m > 0 (long) or CCD_5m < 0 (short)
              OR bb_count >= 2 (2nd BB touch bypasses CCD requirement)
    Price:    close > MA5_1m (long) or close < MA5_1m (short)

  The setup flag resets when close crosses MA5 (opportunity passed).
  Once triggered and entered, no further entries are taken that day.

  signal_skip (default 0): number of valid triggers to skip before entering.
    signal_skip=0 → enter on the 1st trigger (original behaviour)
    signal_skip=1 → skip the 1st trigger, enter on the 2nd

  Near-SatZone gate: skip entries if session extreme is within 1/8 EmaHL
    of EITHER SatZone bound (daily range nearly exhausted in any direction).
    The latch resets when price pulls back >= sat_pullback_fraction * EmaHL
    from the extreme that triggered it (H044: pullback allows re-entry after
    confirmed reversal from SatZone extreme).

Exit priority (highest to lowest):
  1. Fixed SL : entry +/- EmaHL * sl_ema_fraction
  2. SatZone two-phase exit (same as EstHL strategy):
       Phase 1: High >= SatZoneUpper (long) or Low <= SatZoneLower (short)
       Phase 2: close < 5MA (long) or close > 5MA (short)
  3. Pivot trailing stop (active after 09:45): pivotlow(5,5) for long,
     pivothigh(5,5) for short — trailing stop ratchets in the favorable direction
  4. Force exit at 13:40

Setup window: session start (08:45) – 10:05 (setup can latch before entry window)
Entry window: 09:10 – 10:05 (trigger/entry must occur within this window)
One entry per day maximum (after skipping signal_skip triggers).

  Exhaustion bypass: if price has already moved >= exhaust_fraction (default 0.5)
    of EstRange from the day extreme, the opposing side is considered spent and
    CCD direction is relaxed.
    Short: bull_exhausted = close >= day_low + EstRange * exhaust_fraction
    Long:  bear_exhausted = close <= day_high - EstRange * exhaust_fraction

H039 audit: removed intraday VWAP bypass (no marginal contribution).
CCD gate: ccd_ok OR exhausted OR bb_count >= 2.

Data loader: load_data_for_reversal() in src/backtest/runner.py
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_ENTRY_START  = dtime(9, 10)
_ENTRY_END    = dtime(10, 5)
_TRAIL_START  = dtime(9, 45)
_FORCE_EXIT   = dtime(13, 40)


class ReversalStrategy(EstimateHLExitMixin, Strategy):
    """Sequential BB-extreme -> MA5 cross entry within institutional cost zone."""

    vol_ratio:        float = 1.2      # volume must exceed vol_ratio * VolMA20
    sl_ema_fraction:  float = 0.25     # SL = EmaHL * fraction
    exhaust_fraction: float = 0.5      # moved >= fraction of EstRange → opposing side exhausted, relax CCD
    signal_skip:      int   = 0        # skip first N triggers before entering
    sat_pullback_fraction: float = 0.5 # near-SatZone latch resets after pullback >= fraction * EmaHL

    def init(self):
        self._prev_date   = None
        self._init_estimate_hl_exit()
        self._reset_daily()

    def _reset_daily(self):
        self._entered      = False
        self._allow_long   = False
        self._allow_short  = False
        self._open_price   = None
        self._bb_long_touched  = False  # latch: BB_Lower + vol_ok
        self._bb_short_touched = False  # latch: BB_Upper + vol_ok
        self._bb_long_count    = 0     # count BB_Lower touches (2nd touch bypasses CCD)
        self._bb_short_count   = 0     # count BB_Upper touches
        self._bull_exhausted   = False  # latch: price reached day_low + EstRange * fraction
        self._bear_exhausted   = False  # latch: price reached day_high - EstRange * fraction
        self._near_sat_latch   = False  # latch: session extreme ever within 1/8 EmaHL of SatZone
        self._sat_extreme_high = None   # day_high when near-sat triggered (for pullback reset)
        self._sat_extreme_low  = None   # day_low when near-sat triggered
        self._trigger_count = 0
        self._day_high    = None
        self._day_low     = None
        self._sl_price    = None
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

            self._day_low  = float(self.data.Low[-1])
            self._day_high = float(self.data.High[-1])

            bc1 = float(self.data.VWAP1[-1])
            bc2 = float(self.data.VWAP2[-1])
            if not (np.isnan(bc1) or np.isnan(bc2)):
                bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
                if self._open_price > bc_hi:       # above zone → long only
                    self._allow_long = True
                elif self._open_price < bc_lo:     # below zone → short only
                    self._allow_short = True
                else:                              # inside zone → follow MA
                    self._bc_inside = True

        # ── Track daily extremes ──────────────────────────────────────
        if self._day_low is not None:
            self._day_low  = min(self._day_low,  float(self.data.Low[-1]))
            self._day_high = max(self._day_high, float(self.data.High[-1]))

        # ── SatZone exit mixin: record bar ────────────────────────────────
        self._record_bar()

        # ── Exit logic (runs whenever in a position) ───────────────────────
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

        # ── Already entered today or SatZone reached → skip entry logic ──
        if self._entered or self._satzone_reached:
            return

        # ── Read indicators (needed for setup + trigger) ─────────────────
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

        sl = ema_hl * self.sl_ema_fraction

        vol_ok = vol > self.vol_ratio * vol_ma

        # Direction: 5m 120MA direction (no slope threshold)
        bullish = ma5m > ma5m_prev

        # Resolve BC inside zone: direction follows MA
        if getattr(self, '_bc_inside', False):
            self._bc_inside = False
            if bullish:
                self._allow_long = True
            else:
                self._allow_short = True

        if not (self._allow_long or self._allow_short):
            return

        # ── Exhaustion latch: once price reaches fraction of EstRange, flag stays on ──
        exhaust_frac = self.exhaust_fraction
        if not self._bull_exhausted and self._day_low is not None:
            if close >= self._day_low + ema_hl * exhaust_frac:
                self._bull_exhausted = True
        if not self._bear_exhausted and self._day_high is not None:
            if close <= self._day_high - ema_hl * exhaust_frac:
                self._bear_exhausted = True

        # ── Step 1: Latch BB touch + vol (must co-occur on same bar) ──────
        if self._allow_long and bullish and not self._bb_long_touched:
            if close <= bb_lower and vol_ok:
                self._bb_long_touched = True
                self._bb_long_count += 1

        if self._allow_short and not bullish and not self._bb_short_touched:
            if close >= bb_upper and vol_ok:
                self._bb_short_touched = True
                self._bb_short_count += 1

        # ── Step 2: Trigger on MA5 cross (must be within entry window) ───
        # Setup = BB_touched AND (CCD_ok OR exhausted OR 2nd BB touch)
        if _ENTRY_START <= cur_time <= _ENTRY_END:
            long_setup = (self._allow_long and bullish and
                          self._bb_long_touched and
                          (ccd > 0 or self._bear_exhausted
                           or self._bb_long_count >= 2))
            short_setup = (self._allow_short and not bullish and
                           self._bb_short_touched and
                           (ccd < 0 or self._bull_exhausted
                            or self._bb_short_count >= 2))

            # Near-SatZone latch: activates when session extreme reaches within
            # 1/8 EmaHL of EITHER SatZone bound.  Resets when price pulls back
            # >= sat_pullback_fraction * EmaHL from the extreme (H044).
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

            # Pullback reset: price pulled back enough from the extreme
            if self._near_sat_latch and ema_hl > 0:
                pb = ema_hl * self.sat_pullback_fraction
                if (self._sat_extreme_high is not None
                        and self._sat_extreme_high - close >= pb):
                    self._near_sat_latch = False
                if (self._sat_extreme_low is not None
                        and close - self._sat_extreme_low >= pb):
                    self._near_sat_latch = False

            if long_setup and close > ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.buy(size=1)
                    self._sl_price = close - sl
                    self._entered  = True

            elif short_setup and close < ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.sell(size=1)
                    self._sl_price = close + sl
                    self._entered  = True

        # ── Reset BB latch on MA5 cross (opportunity passed) ────────────
        if close > ma5:
            self._bb_long_touched = False
        if close < ma5:
            self._bb_short_touched = False

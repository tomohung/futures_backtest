"""
Crossover experiments combining ORBLong and EstHL entry/exit mechanisms.

Direction A: EstHL entry × ORBLong exit
  Entry : strict 08:58–09:05 window, 30m 20MA filter, BigCost filter, OR width filter
  Exit  : fixed % SL + OR-width TP + trailing stop after 09:45 + force 13:30

Direction B: ORBLong entry × EstHL exit
  Entry : 08:45–09:30 OR range, 09:30–11:00 window, TrendMA filter
  Exit  : EmaHL SL + SatZone two-phase + Dow pivot trailing stop + force 13:30

Data: load_data_for_orb_est_hl() — provides all required columns.
"""

from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Strategy

from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_OR_START    = dtime(8, 45)
_OR_END      = dtime(9, 30)   # ORBLong uses 08:45–09:30 opening range
_ENTRY_START = dtime(9, 30)   # entry window starts right after OR closes
_ENTRY_END   = dtime(11, 0)   # entry cutoff
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)


class ORBLongWithEstHLExitStrategy(EstimateHLExitMixin, Strategy):
    """ORBLong entry (09:30–11:00) + EstHL SatZone / Dow trailing stop exits.

    Entry: OR range 08:45–09:30, entry window 09:30–11:00, Close > TrendMA (10-day).
    Exit:  EmaHL SL + SatZone two-phase + Dow pivot trailing stop + force 13:30.

    Backtest result (2021–2026, long-only): worse than both parent strategies in
    most years. SatZone exits are calibrated for early-morning entries; late
    09:30–11:00 entries find zone targets already partially consumed.
    Not recommended for production use.
    """

    sl_ema_fraction: float = 0.25   # SL = fraction × EmaHL
    long_only: bool = True           # disable short trades by default

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        self._reset_daily()

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._or_confirmed: bool = False
        self._entered: bool = False
        self._sl_price: float | None = None
        self._low_buf: deque = deque(maxlen=11)
        self._high_buf: deque = deque(maxlen=11)
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

        # ── Build Opening Range (08:45–09:30) ─────────────────────────
        if _OR_START <= cur_time <= _OR_END:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low  = min(self._or_low,  float(self.data.Low[-1]))
            return  # don't trade during OR formation

        # ── Mark OR as confirmed once we're past 09:30 ────────────────
        if not self._or_confirmed:
            self._or_confirmed = True

        # ── Entry window (09:30–11:00), at most once per day ──────────
        if (not self._entered
                and _ENTRY_START <= cur_time < _ENTRY_END
                and self._or_confirmed
                and self._or_high != -np.inf):

            ema_hl = float(self.data.EmaHL[-1])
            if np.isnan(ema_hl):
                pass  # insufficient warmup; skip
            else:
                trend_ma = float(self.data.TrendMA[-1])
                sl_dist  = self.sl_ema_fraction * ema_hl

                # ── Long entry ────────────────────────────────────────
                if close > self._or_high:
                    trend_ok = np.isnan(trend_ma) or (close > trend_ma)
                    if trend_ok:
                        self.buy(size=1)
                        self._sl_price = close - sl_dist
                        self._entered = True

                # ── Short entry (disabled by default) ─────────────────
                elif close < self._or_low and not self.long_only:
                    trend_ok = np.isnan(trend_ma) or (close < trend_ma)
                    if trend_ok:
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


# ──────────────────────────────────────────────────────────────────────────────
# Direction A: EstHL entry × ORBLong exit
# ──────────────────────────────────────────────────────────────────────────────

_A_OR_START    = dtime(8, 45)
_A_OR_END      = dtime(8, 57)   # EstHL uses 08:45–08:57 opening range
_A_ENTRY_START = dtime(8, 58)
_A_TRAIL_START = dtime(9, 45)
_A_FORCE_EXIT  = dtime(13, 30)


class EstHLEntryORBLongExitStrategy(Strategy):
    """EstHL strict entry (08:58–entry_end_minute) + ORBLong fixed % SL / OR-width TP exits.

    Entry filters (all must pass):
      1. Close > or_high (upward breakout of 08:45–08:57 range)
      2. Close30 > MA30_20 (30m 20MA uptrend)
      3. or_high > max(BigCost1..N) + 0.5 × sl_dist (breakout above institutional cost)
      4. 0.5 × RollingOR <= ORWidth <= 1.5 × RollingOR (normal OR width)

    Exit priority:
      1. Fixed SL:      entry * (1 - sl_pct)                    before 09:45
      2. Fixed TP:      entry + tp_or_multiplier * eff_or_width  before 09:45
      3. Trailing stop: track highest close, exit on sl_pct drawdown  after 09:45
                        also exit if close >= tp_price           after 09:45
      4. Force exit at 13:30

    Parameters:
      sl_pct             : float = 0.004   fixed SL percentage (0.4%)
      tp_or_multiplier   : float = 3.0     TP = entry + N * max(ORWidth, or_min_width)
      or_min_width       : float = 20.0    minimum effective OR width for TP calc
      bigcost_days       : int   = 2       BigCost lookback days (1-5)
      entry_end_minute   : int   = 5       entry window end = 09:HH (minutes past 09:00)
                                           e.g. 5 → 09:05, 15 → 09:15
      long_only          : bool  = True    disable short trades

    Backtest results (2021-2026 YTD, long-only, bigcost_days=2, tp_or_multiplier=3.0,
                      entry_end_minute=15):
      2021 : 53 trades  PF 1.59  +867 pts   (vs ORBLong -498, EstHL +535)
      2022 : 37 trades  PF 1.52  +484 pts   (vs ORBLong +228, EstHL +831)
      2023 : 41 trades  PF 1.37  +389 pts   (vs ORBLong +302, EstHL +542)
      2024 : 39 trades  PF 1.72  +980 pts   (vs ORBLong +1037, EstHL +1153)
      2025 : 48 trades  PF 1.25  +523 pts   (vs ORBLong +1823, EstHL +542)
      2026 : 10 trades  PF 3.30  +978 pts   (vs ORBLong +1723, EstHL +117)
      Total: +4,221 pts — all years positive, no losing year across 2021-2026.
    """

    sl_pct: float = 0.004           # fixed SL percentage (0.4%)
    tp_or_multiplier: float = 3.0   # TP = entry + mult × max(ORWidth, or_min_width)
    or_min_width: float = 20.0      # minimum effective OR width for TP calc
    bigcost_days: int = 2           # BigCost lookback days (1–5)
    entry_end_minute: int = 15      # entry window end = 09:XX (minutes past 09:00)
    long_only: bool = True

    def init(self):
        self._prev_date = None
        self._reset_daily()

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._entered: bool = False
        self._sl_price: float | None = None
        self._tp_price: float | None = None
        self._trail_peak: float | None = None
        self._trail_trough: float | None = None

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])

        # ── Day rollover ───────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date

        # ── Build Opening Range (08:45–08:57) ─────────────────────────
        if _A_OR_START <= cur_time <= _A_OR_END:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low  = min(self._or_low,  float(self.data.Low[-1]))

        # ── Entry window (08:58–09:XX) ─────────────────────────────────
        entry_end = dtime(9, self.entry_end_minute)
        if (not self._entered
                and _A_ENTRY_START <= cur_time <= entry_end
                and self._or_high != -np.inf):

            or_width   = float(self.data.ORWidth[-1])
            rolling_or = float(self.data.RollingOR[-1])

            # OR width filter
            if not np.isnan(rolling_or):
                if not (0.5 * rolling_or <= or_width <= 1.5 * rolling_or):
                    return

            ma30    = float(self.data.MA30_20[-1])
            close30 = float(self.data.Close30[-1])
            trend_nan = np.isnan(ma30) or np.isnan(close30)

            sl_dist = close * self.sl_pct
            eff_or  = max(or_width, self.or_min_width)

            bc_vals   = [float(getattr(self.data, f"BigCost{i}")[-1])
                         for i in range(1, self.bigcost_days + 1)]
            valid_bc  = [v for v in bc_vals if not np.isnan(v)]

            if close > self._or_high:
                trend_ok = trend_nan or (close30 > ma30)
                cost_ok  = (not valid_bc
                            or self._or_high > max(valid_bc) + 0.5 * sl_dist)
                if trend_ok and cost_ok:
                    self.buy(size=1)
                    self._sl_price   = close - sl_dist
                    self._tp_price   = close + self.tp_or_multiplier * eff_or
                    self._trail_peak = close
                    self._entered = True

            elif close < self._or_low and not self.long_only:
                trend_ok = trend_nan or (close30 < ma30)
                cost_ok  = (not valid_bc
                            or self._or_low < min(valid_bc) - 0.5 * sl_dist)
                if trend_ok and cost_ok:
                    self.sell(size=1)
                    self._sl_price     = close + sl_dist
                    self._tp_price     = close - self.tp_or_multiplier * eff_or
                    self._trail_trough = close
                    self._entered = True

        # ── Exit logic ─────────────────────────────────────────────────
        if not self.position:
            return

        # 1. Force exit at 13:30
        if cur_time >= _A_FORCE_EXIT:
            self.position.close()
            return

        if self.position.is_long:
            if cur_time < _A_TRAIL_START:
                # Fixed SL / TP
                if close <= self._sl_price or close >= self._tp_price:
                    self.position.close()
            else:
                # Trailing stop: track highest close, exit on sl_pct drawdown
                self._trail_peak = max(self._trail_peak, close)
                if close <= self._trail_peak * (1 - self.sl_pct):
                    self.position.close()
                elif close >= self._tp_price:
                    self.position.close()

        elif self.position.is_short:
            if cur_time < _A_TRAIL_START:
                if close >= self._sl_price or close <= self._tp_price:
                    self.position.close()
            else:
                self._trail_trough = min(self._trail_trough, close)
                if close >= self._trail_trough * (1 + self.sl_pct):
                    self.position.close()
                elif close <= self._tp_price:
                    self.position.close()

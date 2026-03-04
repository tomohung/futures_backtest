from datetime import time, timedelta

import numpy as np
import pandas as pd
from backtesting import Strategy


class ORBStrategy(Strategy):
    """Opening Range Breakout strategy for Taiwan Futures (TX) day session.

    Parameters
    ----------
    range_end_minute : int
        Minutes from 08:00 when the opening range ends.
        50 = 08:50, 60 = 09:00, 75 = 09:15 (default: 60)
    sl_pct : float
        Stop-loss percentage from entry price (default: 0.005 = 0.5%)
    tp_multiplier : float
        Take-profit as a multiple of the SL distance (default: 2.0)
    trail_activate_minute : int
        Minutes from 09:00 when trailing stop activates (default: 45 = 09:45)
    trend_ma_days : int
        Trend filter – lookback in trading days (0 = disabled).
        Long entries only when close > MA; short entries only when close < MA.
    """

    range_end_minute: int = 60
    entry_end_minute: int = 75      # cutoff for new entries (from 08:00); 75=09:15
    sl_pct: float = 0.005
    tp_multiplier: float = 2.0
    trail_activate_minute: int = 45
    trend_ma_days: int = 0          # trend MA lookback in days (0 = disabled)

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        # Trend MA indicator
        # If a precomputed 'TrendMA' column is present in the data (e.g. from
        # load_data_with_night_ma), use it directly so night-session prices are
        # reflected. Otherwise compute the MA on day-session bars only.
        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        # Precompute OR high/low arrays for chart overlay
        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            date_mask = dates == date
            day_times = times[date_mask]
            in_range = day_times <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[date_mask][in_range].max()
            or_l = lows[date_mask][in_range].min()
            # Draw lines only after the range is confirmed
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.trail_peak = None
        self.trail_trough = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        # A. Detect date change → reset daily state
        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # B. Accumulate opening range
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        # C. Mark range confirmed (first bar past range_end_time)
        if not self.range_confirmed:
            self.range_confirmed = True

        # D. Entry checks (only within entry window)
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            # Resolve trend MA (None = disabled or still in warmup)
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            # Long signal: close breaks above opening range high
            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered = True
                    self.entry_price = close
                    sl_dist = self.entry_price * self.sl_pct
                    self.sl_price = self.entry_price - sl_dist
                    self.tp_price = self.entry_price + sl_dist * self.tp_multiplier
                    self.trail_peak = self.entry_price

            # Short signal: close breaks below opening range low
            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered = True
                    self.entry_price = close
                    sl_dist = self.entry_price * self.sl_pct
                    self.sl_price = self.entry_price + sl_dist
                    self.tp_price = self.entry_price - sl_dist * self.tp_multiplier
                    self.trail_trough = self.entry_price

        # E. Exit checks (only when in position)
        if not self.position:
            return

        # 1. Force exit at 13:30 (highest priority)
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                # Fixed SL/TP
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                # Trailing stop
                self.trail_peak = max(self.trail_peak, close)
                if close <= self.trail_peak * (1 - self.sl_pct):
                    self.position.close()
                elif close >= self.tp_price:
                    self.position.close()

        elif self.position.is_short:
            if bar_time < self._trail_activate_time:
                # Fixed SL/TP
                if close >= self.sl_price or close <= self.tp_price:
                    self.position.close()
            else:
                # Trailing stop
                self.trail_trough = min(self.trail_trough, close)
                if close >= self.trail_trough * (1 + self.sl_pct):
                    self.position.close()
                elif close <= self.tp_price:
                    self.position.close()


class ORBPhase3AStrategy(Strategy):
    """Phase 3A: Opening Range Breakout with OR-based SL/TP and bar-based trailing stop.

    Key differences from ORBStrategy (Phase 2):
    - SL: OR low (long) / OR high (short) — structural, not fixed pct
    - TP: entry ± tp_or_multiplier × OR_width — scales with day's volatility
    - Trailing: exit when close < min-low of last trail_bars bars (long)
                         or close > max-high of last trail_bars bars (short)

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120,
        trail_activate_minute=45, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    trail_activate_minute: int = 45
    trend_ma_days: int = 10
    tp_or_multiplier: float = 2.0   # TP = entry ± N × OR_width
    trail_bars: int = 5             # trailing: look back N bars for low/high

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        # Trend MA
        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        # OR lines for chart overlay
        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            date_mask = dates == date
            day_times = times[date_mask]
            in_range = day_times <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[date_mask][in_range].max()
            or_l = lows[date_mask][in_range].min()
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # Accumulate opening range
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        # Entry (within window)
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            or_width = self.or_high - self.or_low

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered = True
                    self.entry_price = close
                    self.sl_price = self.or_low                          # OR low
                    self.tp_price = self.entry_price + self.tp_or_multiplier * or_width

            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered = True
                    self.entry_price = close
                    self.sl_price = self.or_high                         # OR high
                    self.tp_price = self.entry_price - self.tp_or_multiplier * or_width

        if not self.position:
            return

        # Force exit at 13:30
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                # Bar-based trailing: exit if close breaks below min-low of last N bars
                n = min(int(self.trail_bars), len(self.data.Low) - 1)
                if n > 0:
                    trail_sl = np.min(self.data.Low[-n - 1:-1])
                    if close <= trail_sl:
                        self.position.close()
                        return
                if close >= self.tp_price:
                    self.position.close()

        elif self.position.is_short:
            if bar_time < self._trail_activate_time:
                if close >= self.sl_price or close <= self.tp_price:
                    self.position.close()
            else:
                # Bar-based trailing: exit if close breaks above max-high of last N bars
                n = min(int(self.trail_bars), len(self.data.High) - 1)
                if n > 0:
                    trail_sl = np.max(self.data.High[-n - 1:-1])
                    if close >= trail_sl:
                        self.position.close()
                        return
                if close <= self.tp_price:
                    self.position.close()


class ORBPhase3BStrategy(Strategy):
    """Phase 3B: Super Trend exit — no fixed TP, let trend run to reversal.

    Exit logic:
    - Before trail_activate_minute: SL = OR low (long) / OR high (short)
    - After trail_activate_minute: exit when close crosses Super Trend line
    - Force exit at 13:30

    Super Trend = ATR-based trailing band (lower band for longs, upper for shorts).
    Falls back to OR SL when Super Trend is still in warmup (NaN).

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120,
        trail_activate_minute=45, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    trail_activate_minute: int = 45
    trend_ma_days: int = 10
    atr_period: int = 10
    atr_multiplier: float = 2.0

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        # Trend MA
        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        # Super Trend — precomputed on full bar array
        st_arr, st_dir_arr = _compute_supertrend(
            np.asarray(self.data.High),
            np.asarray(self.data.Low),
            np.asarray(self.data.Close),
            int(self.atr_period),
            float(self.atr_multiplier),
        )
        self._supertrend = self.I(lambda: st_arr, name="SuperTrend", overlay=True,
                                  color="purple", scatter=False)
        self._st_dir = self.I(lambda: st_dir_arr, name="ST Dir", overlay=False)

        # OR lines for chart overlay
        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            date_mask = dates == date
            day_times = times[date_mask]
            in_range = day_times <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[date_mask][in_range].max()
            or_l = lows[date_mask][in_range].min()
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # Accumulate opening range
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        # Entry (within window)
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered = True
                    self.entry_price = close
                    self.sl_price = self.or_low

            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered = True
                    self.entry_price = close
                    self.sl_price = self.or_high

        if not self.position:
            return

        # Force exit at 13:30
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        st_val = self._supertrend[-1]
        st_valid = not np.isnan(st_val)

        if self.position.is_long:
            if bar_time < self._trail_activate_time or not st_valid:
                # Use OR-based SL
                if close <= self.sl_price:
                    self.position.close()
            else:
                # Super Trend exit: close falls below Super Trend support
                if close <= st_val:
                    self.position.close()

        elif self.position.is_short:
            if bar_time < self._trail_activate_time or not st_valid:
                # Use OR-based SL
                if close >= self.sl_price:
                    self.position.close()
            else:
                # Super Trend exit: close rises above Super Trend resistance
                if close >= st_val:
                    self.position.close()


class ORBPhase3BHybridStrategy(Strategy):
    """Phase 3B Hybrid / Long-only variant.

    Longs  → OR-low SL + Super Trend exit (no fixed TP)
    Shorts → Phase 2 fixed sl_pct SL/TP + sl_pct trailing (same as ORBStrategy)
             Disabled entirely when long_only=True.

    Fixed structural params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120,
        trail_activate_minute=45, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    trail_activate_minute: int = 45
    trend_ma_days: int = 10
    # Long exit
    atr_period: int = 10
    atr_multiplier: float = 2.0
    # Short exit (Phase 2 style)
    sl_pct: float = 0.005
    tp_multiplier: float = 1.5
    # Mode
    long_only: int = 0          # 1 = long only, 0 = long + short hybrid

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        st_arr, _ = _compute_supertrend(
            np.asarray(self.data.High),
            np.asarray(self.data.Low),
            np.asarray(self.data.Close),
            int(self.atr_period),
            float(self.atr_multiplier),
        )
        self._supertrend = self.I(lambda: st_arr, name="SuperTrend", overlay=True,
                                  color="purple", scatter=False)

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.trail_peak = None
        self.trail_trough = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # Accumulate opening range
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        # Entry
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered = True
                    self.entry_price = close
                    self.sl_price = self.or_low      # structural SL for longs
                    self.tp_price = None              # no fixed TP
                    self.trail_peak = close

            elif not self.long_only and close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered = True
                    self.entry_price = close
                    sl_dist = self.entry_price * self.sl_pct
                    self.sl_price = self.entry_price + sl_dist    # Phase 2 fixed SL
                    self.tp_price = self.entry_price - sl_dist * self.tp_multiplier
                    self.trail_trough = close

        if not self.position:
            return

        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        st_val = self._supertrend[-1]
        st_valid = not np.isnan(st_val)

        if self.position.is_long:
            if bar_time < self._trail_activate_time or not st_valid:
                if close <= self.sl_price:
                    self.position.close()
            else:
                if close <= st_val:
                    self.position.close()

        elif self.position.is_short:
            # Phase 2 style exit for shorts
            if bar_time < self._trail_activate_time:
                if close >= self.sl_price or close <= self.tp_price:
                    self.position.close()
            else:
                self.trail_trough = min(self.trail_trough, close)
                if close >= self.trail_trough * (1 + self.sl_pct):
                    self.position.close()
                elif close <= self.tp_price:
                    self.position.close()


def _compute_supertrend(high, low, close, period: int, multiplier: float):
    """Compute Super Trend indicator arrays.

    Returns (supertrend, direction) where:
        supertrend: lower band (support) when bullish, upper band (resistance) when bearish
        direction:  +1 = bullish (price above ST), -1 = bearish (price below ST)
    """
    n = len(close)

    # True Range
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low,
         np.maximum(np.abs(high - prev_close),
                    np.abs(low  - prev_close)))

    # ATR via Wilder's smoothing
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    upper = basic_upper.copy()
    lower = basic_lower.copy()
    direction = np.ones(n)
    supertrend = np.full(n, np.nan)

    for i in range(1, n):
        if np.isnan(atr[i]):
            continue

        # Final upper band — reset when previous value was NaN (warmup)
        if np.isnan(upper[i - 1]) or basic_upper[i] < upper[i - 1] or close[i - 1] > upper[i - 1]:
            upper[i] = basic_upper[i]
        else:
            upper[i] = upper[i - 1]
        # Final lower band
        if np.isnan(lower[i - 1]) or basic_lower[i] > lower[i - 1] or close[i - 1] < lower[i - 1]:
            lower[i] = basic_lower[i]
        else:
            lower[i] = lower[i - 1]

        # Direction
        if close[i] > upper[i - 1]:
            direction[i] = 1
        elif close[i] < lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        supertrend[i] = lower[i] if direction[i] == 1 else upper[i]

    return supertrend, direction


class ORBPlanCStrategy(Strategy):
    """Plan C: Exit when trend momentum stalls — no new high/low for N minutes.

    Exit logic:
    - SL: OR low (long) / OR high (short) — structural, same as Phase 3A
    - Momentum exit: if no new higher high (long) / lower low (short) in the
      last `momentum_window` bars, the trend has stalled → exit
    - Force exit at 13:30
    - No fixed TP

    The momentum clock starts at entry and resets whenever a new extreme is made.

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    trend_ma_days: int = 10
    momentum_window: int = 30   # bars (minutes) without new extreme → exit

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows  = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr  = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            mask = dates == date
            in_range = times[mask] <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[mask][in_range].max()
            or_l = lows[mask][in_range].min()
            post = mask & (times > self._range_end_time)
            or_high_arr[post] = or_h
            or_low_arr[post]  = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low  = None
        self.range_confirmed = False
        self.long_entered  = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price    = None
        # momentum tracking
        self.peak_high         = None   # highest high seen since long entry
        self.trough_low        = None   # lowest low seen since short entry
        self.bars_since_peak   = 0      # bars without a new high (long)
        self.bars_since_trough = 0      # bars without a new low (short)

    def next(self):
        bar_ts   = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high  = self.data.High[-1]
        low   = self.data.Low[-1]

        # Accumulate opening range
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low  = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low  = min(self.or_low,  low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        # Entry
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered  = True
                    self.entry_price   = close
                    self.sl_price      = self.or_low
                    self.peak_high     = high
                    self.bars_since_peak = 0

            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered  = True
                    self.entry_price    = close
                    self.sl_price       = self.or_high
                    self.trough_low     = low
                    self.bars_since_trough = 0

        if not self.position:
            return

        # Force exit at 13:30
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        mw = int(self.momentum_window)

        if self.position.is_long:
            # Update momentum tracker
            if high >= self.peak_high:
                self.peak_high     = high
                self.bars_since_peak = 0
            else:
                self.bars_since_peak += 1

            # OR SL
            if close <= self.sl_price:
                self.position.close()
                return
            # Momentum exit
            if self.bars_since_peak >= mw:
                self.position.close()

        elif self.position.is_short:
            # Update momentum tracker
            if low <= self.trough_low:
                self.trough_low     = low
                self.bars_since_trough = 0
            else:
                self.bars_since_trough += 1

            # OR SL
            if close >= self.sl_price:
                self.position.close()
                return
            # Momentum exit
            if self.bars_since_trough >= mw:
                self.position.close()


class ORBPlanCHybridStrategy(Strategy):
    """Plan C Hybrid: momentum stall exit with asymmetric SL.

    Longs  → OR low SL + momentum exit (no new high in N minutes)
    Shorts → fixed sl_pct SL + momentum exit (no new low in N minutes)

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    trend_ma_days: int = 10
    momentum_window: int = 20   # bars without new extreme → exit
    sl_pct: float = 0.005       # short SL only (long uses OR low)

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

    def _reset_daily(self):
        self.or_high = None
        self.or_low  = None
        self.range_confirmed = False
        self.long_entered  = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price    = None
        self.peak_high         = None
        self.trough_low        = None
        self.bars_since_peak   = 0
        self.bars_since_trough = 0

    def next(self):
        bar_ts   = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high  = self.data.High[-1]
        low   = self.data.Low[-1]

        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low  = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low  = min(self.or_low,  low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered    = True
                    self.entry_price     = close
                    self.sl_price        = self.or_low          # structural SL
                    self.peak_high       = high
                    self.bars_since_peak = 0

            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered      = True
                    self.entry_price        = close
                    self.sl_price           = close * (1 + self.sl_pct)  # fixed % SL
                    self.trough_low         = low
                    self.bars_since_trough  = 0

        if not self.position:
            return

        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        mw = int(self.momentum_window)

        if self.position.is_long:
            if high >= self.peak_high:
                self.peak_high       = high
                self.bars_since_peak = 0
            else:
                self.bars_since_peak += 1

            if close <= self.sl_price:
                self.position.close()
                return
            if self.bars_since_peak >= mw:
                self.position.close()

        elif self.position.is_short:
            if low <= self.trough_low:
                self.trough_low         = low
                self.bars_since_trough  = 0
            else:
                self.bars_since_trough += 1

            if close >= self.sl_price:
                self.position.close()
                return
            if self.bars_since_trough >= mw:
                self.position.close()


class ORBPhase4Strategy(Strategy):
    """Phase 4: Adaptive TP using OR width instead of fixed sl_pct multiple.

    TP = entry ± tp_or_multiplier × max(OR_width, or_min_width)

    Key differences from ORBStrategy (Phase 2):
    - TP: OR-width based (adaptive to the day's opening volatility)
    - SL: same fixed sl_pct from entry
    - Trailing: same as Phase 2 (sl_pct trailing after trail_activate_minute)

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120,
        trail_activate_minute=45, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    sl_pct: float = 0.005
    tp_or_multiplier: float = 1.0      # TP = entry ± N × effective_OR_width
    or_min_width: float = 20.0         # floor for OR width on quiet days
    trail_activate_minute: int = 45
    trend_ma_days: int = 10

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            date_mask = dates == date
            day_times = times[date_mask]
            in_range = day_times <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[date_mask][in_range].max()
            or_l = lows[date_mask][in_range].min()
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.trail_peak = None
        self.trail_trough = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            or_width = self.or_high - self.or_low
            eff_or = max(or_width, self.or_min_width)

            if close > self.or_high and not self.long_entered:
                if ma_val is None or close > ma_val:
                    if self.position.is_short:
                        self.position.close()
                    self.buy(size=1)
                    self.long_entered = True
                    self.entry_price = close
                    sl_dist = self.entry_price * self.sl_pct
                    self.sl_price = self.entry_price - sl_dist
                    self.tp_price = self.entry_price + self.tp_or_multiplier * eff_or
                    self.trail_peak = self.entry_price

            elif close < self.or_low and not self.short_entered:
                if ma_val is None or close < ma_val:
                    if self.position.is_long:
                        self.position.close()
                    self.sell(size=1)
                    self.short_entered = True
                    self.entry_price = close
                    sl_dist = self.entry_price * self.sl_pct
                    self.sl_price = self.entry_price + sl_dist
                    self.tp_price = self.entry_price - self.tp_or_multiplier * eff_or
                    self.trail_trough = self.entry_price

        if not self.position:
            return

        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                self.trail_peak = max(self.trail_peak, close)
                if close <= self.trail_peak * (1 - self.sl_pct):
                    self.position.close()
                elif close >= self.tp_price:
                    self.position.close()

        elif self.position.is_short:
            if bar_time < self._trail_activate_time:
                if close >= self.sl_price or close <= self.tp_price:
                    self.position.close()
            else:
                self.trail_trough = min(self.trail_trough, close)
                if close >= self.trail_trough * (1 + self.sl_pct):
                    self.position.close()
                elif close <= self.tp_price:
                    self.position.close()


class ORBPhase4HybridStrategy(Strategy):
    """Phase 4 Hybrid: OR-width TP for longs, Phase 2 fixed-pct TP for shorts.

    Longs:  TP = entry + tp_or_multiplier × max(OR_width, or_min_width)
    Shorts: TP = entry - sl_pct × tp_multiplier  (Phase 2 style)

    SL and trailing stop identical to Phase 2 for both sides.

    Fixed params (Phase 2 best):
        range_end_minute=90, entry_end_minute=120,
        trail_activate_minute=45, trend_ma_days=10
    """

    range_end_minute: int = 90
    entry_end_minute: int = 120
    sl_pct: float = 0.005
    tp_or_multiplier: float = 1.0      # long TP = entry + N × effective_OR_width
    or_min_width: float = 20.0         # floor for OR width on quiet days
    tp_multiplier: float = 1.5         # short TP = entry - sl_pct × tp_multiplier
    trail_activate_minute: int = 45
    trend_ma_days: int = 10
    min_rolling_or: float = 0.0        # skip entry if N-day rolling avg OR < this (0=disabled)
    long_only: int = 0                 # 1 = skip short entries entirely
    long_adx_min: float = 0.0         # skip long entries when daily ADX < this (0=disabled)

    def init(self):
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)
        self._reset_daily()
        self._current_date = None

        if self.trend_ma_days > 0:
            if "TrendMA" in self.data.df.columns:
                trend_ma_arr = self.data.df["TrendMA"].values
                self._trend_ma = self.I(
                    lambda: trend_ma_arr, name="Trend MA (night)", overlay=True,
                )
            else:
                n_bars = self.trend_ma_days * 301
                closes = pd.Series(self.data.Close)
                self._trend_ma = self.I(
                    lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
                    name="Trend MA", overlay=True,
                )

        if self.min_rolling_or > 0 and "RollingOR" in self.data.df.columns:
            rolling_or_arr = self.data.df["RollingOR"].values
            self._rolling_or = self.I(
                lambda: rolling_or_arr, name="Rolling OR Avg", overlay=False,
            )
        else:
            self._rolling_or = None

        if self.long_adx_min > 0 and "DailyADX" in self.data.df.columns:
            adx_arr = self.data.df["DailyADX"].values
            self._daily_adx = self.I(lambda: adx_arr, name="Daily ADX", overlay=False)
        else:
            self._daily_adx = None

        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        idx = pd.DatetimeIndex(self.data.index)
        highs = np.asarray(self.data.High)
        lows = np.asarray(self.data.Low)
        dates = idx.date
        times = idx.time

        or_high_arr = np.full(len(idx), np.nan)
        or_low_arr = np.full(len(idx), np.nan)

        for date in np.unique(dates):
            date_mask = dates == date
            day_times = times[date_mask]
            in_range = day_times <= self._range_end_time
            if not in_range.any():
                continue
            or_h = highs[date_mask][in_range].max()
            or_l = lows[date_mask][in_range].min()
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        self.or_high = None
        self.or_low = None
        self.range_confirmed = False
        self.long_entered = False
        self.short_entered = False
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.trail_peak = None
        self.trail_trough = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        if not self.range_confirmed:
            self.range_confirmed = True

        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            # Rolling OR regime filter — skip new entries in quiet market regimes
            _regime_ok = (
                self._rolling_or is None
                or (not np.isnan(self._rolling_or[-1]) and self._rolling_or[-1] >= self.min_rolling_or)
            )

            if _regime_ok:
                ma_val = None
                if self.trend_ma_days > 0:
                    raw = self._trend_ma[-1]
                    if not np.isnan(raw):
                        ma_val = raw

                or_width = self.or_high - self.or_low
                eff_or = max(or_width, self.or_min_width)
                sl_dist = close * self.sl_pct

                # ADX filter for longs
                _adx_ok = (
                    self._daily_adx is None
                    or (not np.isnan(self._daily_adx[-1])
                        and self._daily_adx[-1] >= self.long_adx_min)
                )

                if close > self.or_high and not self.long_entered and _adx_ok:
                    if ma_val is None or close > ma_val:
                        if self.position.is_short:
                            self.position.close()
                        self.buy(size=1)
                        self.long_entered = True
                        self.entry_price = close
                        self.sl_price = self.entry_price - sl_dist
                        self.tp_price = self.entry_price + self.tp_or_multiplier * eff_or
                        self.trail_peak = self.entry_price

                elif not self.long_only and close < self.or_low and not self.short_entered:
                    if ma_val is None or close < ma_val:
                        if self.position.is_long:
                            self.position.close()
                        self.sell(size=1)
                        self.short_entered = True
                        self.entry_price = close
                        self.sl_price = self.entry_price + sl_dist
                        self.tp_price = self.entry_price - sl_dist * self.tp_multiplier
                        self.trail_trough = self.entry_price

        if not self.position:
            return

        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                self.trail_peak = max(self.trail_peak, close)
                if close <= self.trail_peak * (1 - self.sl_pct):
                    self.position.close()
                elif close >= self.tp_price:
                    self.position.close()

        elif self.position.is_short:
            if bar_time < self._trail_activate_time:
                if close >= self.sl_price or close <= self.tp_price:
                    self.position.close()
            else:
                self.trail_trough = min(self.trail_trough, close)
                if close >= self.trail_trough * (1 + self.sl_pct):
                    self.position.close()
                elif close <= self.tp_price:
                    self.position.close()


def datetime_from_time(t: time):
    """Convert a time object to a datetime for timedelta arithmetic."""
    from datetime import datetime
    return datetime(2000, 1, 1, t.hour, t.minute, t.second)

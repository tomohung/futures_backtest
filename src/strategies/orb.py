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


def datetime_from_time(t: time):
    """Convert a time object to a datetime for timedelta arithmetic."""
    from datetime import datetime
    return datetime(2000, 1, 1, t.hour, t.minute, t.second)

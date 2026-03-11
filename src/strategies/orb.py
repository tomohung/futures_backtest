# 台指期（TX）開盤區間突破策略
# Opening Range Breakout strategies for Taiwan Futures day session (08:45–13:45)

from datetime import time, timedelta

import numpy as np
import pandas as pd
from backtesting import Strategy


class ORBStrategy(Strategy):
    """Phase 2 基準策略：開盤區間突破 + 固定百分比 SL/TP + 趨勢濾網（雙向）

    作為比較基準保留，不用於實盤。
    最佳參數：range_end=90, entry_end=120, sl=0.5%, tp=1.5×, trail@9:45, trend_ma=10日
    """

    range_end_minute: int = 60
    entry_end_minute: int = 75      # 進場截止（距 08:00 的分鐘數）；75 = 09:15
    sl_pct: float = 0.005           # 停損百分比（0.5%）
    tp_multiplier: float = 2.0      # 止盈 = 停損距離 × 乘數
    trail_activate_minute: int = 45 # 啟動移動停損的時間（距 09:00 的分鐘數）；45 = 09:45
    trend_ma_days: int = 0          # 趨勢均線回溯天數（0 = 停用）

    def init(self):
        # ── 計算各關鍵時間點 ────────────────────────────────────────────
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = time(13, 30)  # 13:30 強制出場，不持倉過夜
        self._reset_daily()
        self._current_date = None

        # ── 趨勢均線 ────────────────────────────────────────────────────
        # 優先使用 load_data_with_night_ma 預先計算的夜盤連續均線（TrendMA 欄位），
        # 以確保隔夜價格變動也反映在趨勢判斷中。
        # 若無此欄位則用日盤 bar 計算。
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

        # ── 圖表用：開盤區間高低點水平線 ───────────────────────────────
        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        """預先計算每日開盤區間的高低點陣列，供圖表疊加顯示。"""
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
            # 區間確認後才畫線（避免在區間形成中顯示不完整的高低點）
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        """每日重置所有日內狀態。"""
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

        # A. 偵測換日 → 重置日內狀態
        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # B. 累計開盤區間（區間結束時間前的每根 bar 都更新高低點）
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        # C. 開盤區間確認（第一根超過區間結束時間的 bar）
        if not self.range_confirmed:
            self.range_confirmed = True

        # D. 進場邏輯（僅在進場窗口內）
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:
            ma_val = None
            if self.trend_ma_days > 0:
                raw = self._trend_ma[-1]
                if not np.isnan(raw):
                    ma_val = raw

            # 做多：收盤突破開盤區間高點，且收盤在趨勢均線上方
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

            # 做空：收盤跌破開盤區間低點，且收盤在趨勢均線下方
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

        # E. 出場邏輯（持倉中才檢查）
        if not self.position:
            return

        # 1. 13:30 強制出場（最高優先）
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                # 固定 SL/TP
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                # 移動停損：追蹤最高點，回撤超過 sl_pct 則出場
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


class ORBLongStrategy(Strategy):
    """開盤區間突破 — 順勢只做多策略（Taiwan Futures TX，日盤）

    ════════════════════════════════════════════════════════════
    策略哲學
    ════════════════════════════════════════════════════════════
    台指期的多方走勢（牛市趨勢）比空方走勢更具一致性和可預測性。
    空方的勝率和期望值明顯不如多方，且空方在高波動年（如 2021）
    表現反而拖累整體績效。因此策略只做多，避開空方雜訊。

    進場條件（同時滿足）：
      1. 收盤價突破開盤區間高點（08:45–09:30 的最高價）
      2. 收盤價在 10 日趨勢均線上方（確認多頭方向）
      3. 進場時間在 09:30–11:00 之間（避開太晚的假突破）

    止盈（TP）：
      以開盤區間寬度為基準（波動大的日子目標也大）
      TP = 進場價 + tp_or_multiplier × max(OR寬度, or_min_width)
      最佳參數：tp_or_multiplier=1.5，or_min_width=20 點

    停損（SL）：
      固定百分比停損：SL = 進場價 × (1 - sl_pct)
      最佳參數：sl_pct=0.4%

    移動停損（Trailing Stop）：
      09:45 後啟動，追蹤最高收盤，回撤超過 sl_pct 即出場
      讓盈利部位有機會繼續跑，同時保護已有獲利

    強制出場：
      13:30 強制平倉，不持倉過夜
    ════════════════════════════════════════════════════════════

    最佳參數（2022–2026 回測）：
        tp_or_multiplier = 1.5
        sl_pct           = 0.004  (0.4%)
        or_min_width     = 20.0   點
        trend_ma_days    = 10     日
        range_end        = 09:30  (range_end_minute=90)
        entry_end        = 11:00  (entry_end_minute=120)
        trail_activate   = 09:45  (trail_activate_minute=45)

    年度績效摘要（每口，不含手續費）：
        2022: +228 pts  win=48%  PF=1.3
        2023: +302 pts  win=54%  PF=1.2
        2024: +1037 pts win=56%  PF=1.4
        2025: +1823 pts win=64%  PF=2.5
        2026: +1617 pts win=64%  PF=5.5  （截至 2026-03-04，35 交易日）
    ════════════════════════════════════════════════════════════
    """

    # ── 時間參數 ────────────────────────────────────────────────────────
    range_end_minute: int = 90      # 開盤區間結束（距 08:00 分鐘數）；90 = 09:30
    entry_end_minute: int = 120     # 進場截止（距 08:00 分鐘數）；120 = 11:00
    trail_activate_minute: int = 45 # 啟動移動停損（距 09:00 分鐘數）；45 = 09:45
    force_exit_minute: int = 300    # 強制出場（距 08:00 分鐘數）；300 = 13:00（sweep 最佳）

    # ── 停損／止盈參數 ──────────────────────────────────────────────────
    sl_pct: float = 0.004           # 停損百分比（0.4%）
    tp_or_multiplier: float = 1.5   # 止盈 = 進場價 + N × 開盤區間寬度
    or_min_width: float = 20.0      # 開盤區間寬度下限（安靜日的最低保護）

    # ── 趨勢濾網 ────────────────────────────────────────────────────────
    trend_ma_days: int = 10         # 趨勢均線回溯天數（含夜盤的連續 K 棒均線）

    # ── 實驗性參數（保留供研究用，預設停用）──────────────────────────
    long_only: int = 1              # 1 = 只做多（預設）；0 = 雙向（研究用）
    tp_multiplier: float = 1.5      # 做空止盈乘數（long_only=0 時才生效）
    min_rolling_or: float = 0.0     # 滾動 OR 寬度下限濾網（0 = 停用）
    long_adx_min: float = 0.0       # ADX 進場門檻（0 = 停用；實驗結論：無顯著效益）
    or_pct_min: float = 0.0         # OR% 下限（0 = 停用）；OR% = OR寬度 / 開盤價 × 100
    or_pct_max: float = 0.0         # OR% 上限（0 = 停用）；建議範圍：0.3–1.0%

    def init(self):
        # ── 計算各關鍵時間點 ────────────────────────────────────────────
        self._range_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.range_end_minute)
        ).time()
        self._entry_end_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.entry_end_minute)
        ).time()
        self._trail_activate_time = (
            datetime_from_time(time(9, 0)) + timedelta(minutes=self.trail_activate_minute)
        ).time()
        self._force_exit_time = (
            datetime_from_time(time(8, 0)) + timedelta(minutes=self.force_exit_minute)
        ).time()
        self._reset_daily()
        self._current_date = None

        # ── 趨勢均線（含夜盤連續 K 棒）─────────────────────────────────
        # 使用 load_data_with_night_ma 預先計算的 TrendMA 欄位，
        # 讓隔夜的跳空與夜盤走勢也能反映在趨勢方向判斷上。
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

        # ── 滾動 OR 寬度濾網（實驗性，預設停用）────────────────────────
        # Phase 5 實驗結論：此濾網在移除安靜日空方交易的同時也刪除了獲利多方，
        # 淨效益為負，因此預設停用（min_rolling_or=0）。
        if self.min_rolling_or > 0 and "RollingOR" in self.data.df.columns:
            rolling_or_arr = self.data.df["RollingOR"].values
            self._rolling_or = self.I(
                lambda: rolling_or_arr, name="Rolling OR Avg", overlay=False,
            )
        else:
            self._rolling_or = None

        # ── ADX 進場濾網（實驗性，預設停用）─────────────────────────────
        # Phase 6 實驗結論：ADX 與交易勝負的相關性 |r| < 0.05，
        # 無法有效區分適合進場與不適合進場的日子，因此預設停用。
        if self.long_adx_min > 0 and "DailyADX" in self.data.df.columns:
            adx_arr = self.data.df["DailyADX"].values
            self._daily_adx = self.I(lambda: adx_arr, name="Daily ADX", overlay=False)
        else:
            self._daily_adx = None

        # ── 圖表用：開盤區間高低點水平線 ───────────────────────────────
        or_high_arr, or_low_arr = self._precompute_or_lines()
        self._or_high_line = self.I(
            lambda: or_high_arr, name="OR High", overlay=True, color="lime", scatter=False
        )
        self._or_low_line = self.I(
            lambda: or_low_arr, name="OR Low", overlay=True, color="tomato", scatter=False
        )

    def _precompute_or_lines(self):
        """預先計算每日開盤區間的高低點陣列，供圖表疊加顯示。"""
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
            # 區間確認後才畫線（避免顯示不完整的高低點）
            post_range = date_mask & (times > self._range_end_time)
            or_high_arr[post_range] = or_h
            or_low_arr[post_range] = or_l

        return or_high_arr, or_low_arr

    def _reset_daily(self):
        """每日重置所有日內狀態。"""
        self.or_high = None
        self.or_low = None
        self.day_open = None
        self.range_confirmed = False
        self.or_filter_pass = True  # OR% 濾網：預設通過（未啟用時恆為 True）
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

        # A. 偵測換日 → 重置日內狀態
        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # B. 累計開盤區間（08:45–09:30）
        if bar_time <= self._range_end_time:
            if self.or_high is None:
                self.or_high = high
                self.or_low = low
                self.day_open = self.data.Open[-1]  # 第一根 bar 的開盤價
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)
            return

        # C. 開盤區間確認
        if not self.range_confirmed:
            self.range_confirmed = True
            # OR% 濾網：OR% = OR寬度 / 開盤價 × 100，與指數水位無關
            if (self.or_pct_min > 0 or self.or_pct_max > 0) and self.day_open:
                or_pct = (self.or_high - self.or_low) / self.day_open * 100
                if self.or_pct_min > 0 and or_pct < self.or_pct_min:
                    self.or_filter_pass = False
                if self.or_pct_max > 0 and or_pct > self.or_pct_max:
                    self.or_filter_pass = False

        # D. 進場邏輯（09:30–11:00）
        if self.range_confirmed and self.or_high is not None and bar_time < self._entry_end_time:

            # 滾動 OR 濾網（實驗性）
            _regime_ok = (
                self._rolling_or is None
                or (not np.isnan(self._rolling_or[-1])
                    and self._rolling_or[-1] >= self.min_rolling_or)
            )

            if _regime_ok:
                # 趨勢方向確認（收盤在 10 日均線上方才考慮做多）
                ma_val = None
                if self.trend_ma_days > 0:
                    raw = self._trend_ma[-1]
                    if not np.isnan(raw):
                        ma_val = raw

                # 開盤區間寬度（有效寬度取寬度與下限的最大值，避免安靜日 TP 太近）
                or_width = self.or_high - self.or_low
                eff_or = max(or_width, self.or_min_width)
                sl_dist = close * self.sl_pct

                # ADX 濾網（實驗性）
                _adx_ok = (
                    self._daily_adx is None
                    or (not np.isnan(self._daily_adx[-1])
                        and self._daily_adx[-1] >= self.long_adx_min)
                )

                # ── 做多進場 ────────────────────────────────────────────
                # 條件：突破 OR 高點 + 趨勢向上 + ADX 達標（若啟用）+ OR% 濾網通過
                if close > self.or_high and not self.long_entered and _adx_ok and self.or_filter_pass:
                    if ma_val is None or close > ma_val:
                        if self.position.is_short:
                            self.position.close()
                        self.buy(size=1)
                        self.long_entered = True
                        self.entry_price = close
                        self.sl_price = self.entry_price - sl_dist
                        # 止盈目標 = 進場價 + tp_or_multiplier × 有效 OR 寬度
                        self.tp_price = self.entry_price + self.tp_or_multiplier * eff_or
                        self.trail_peak = self.entry_price

                # ── 做空進場（研究用，預設停用 long_only=1）──────────────
                elif not self.long_only and close < self.or_low and not self.short_entered:
                    if ma_val is None or close < ma_val:
                        if self.position.is_long:
                            self.position.close()
                        self.sell(size=1)
                        self.short_entered = True
                        self.entry_price = close
                        self.sl_price = self.entry_price + sl_dist
                        # 做空使用固定百分比止盈（Phase 2 風格）
                        self.tp_price = self.entry_price - sl_dist * self.tp_multiplier
                        self.trail_trough = self.entry_price

        # E. 出場邏輯（持倉中才檢查）
        if not self.position:
            return

        # 1. 13:30 強制出場（最高優先，不持倉過夜）
        if bar_time >= self._force_exit_time:
            self.position.close()
            return

        if self.position.is_long:
            if bar_time < self._trail_activate_time:
                # 09:45 前：固定 SL/TP
                if close <= self.sl_price or close >= self.tp_price:
                    self.position.close()
            else:
                # 09:45 後：移動停損，追蹤最高收盤，讓獲利奔跑
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
    """將 time 物件轉為 datetime，以便進行 timedelta 加法運算。"""
    from datetime import datetime
    return datetime(2000, 1, 1, t.hour, t.minute, t.second)

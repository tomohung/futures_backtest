"""
H061 - Morning Dip Reversal: Phase 2 Backtest (v2)
Morning dip 反彈做多策略 — BB/KD 超賣 + MA5 確認

策略邏輯（參考 reversal 策略的進場模式）：
1. 超賣 latch：
   - 條件 A：close <= BB Lower (1m BB(15, 2σ))
   - 條件 B：KD_K < kd_threshold（1m Stochastic K(9,3)）
   任一條件成立即 latch
2. 進場確認：latch 後，close > MA5_1m（1 分 K 5MA）時做多
3. 停損：進場價 × (1 - sl_pct%)
4. 停利：進場價 × (1 + tp_pct%)
5. 時間限制：只在 dip_start ~ dip_end 偵測，13:30 強制出場
6. Latch reset：若 close > MA5 但未進場，latch 歸零（機會已過）

所有門檻使用百分比。
"""

from datetime import time

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy


class MorningDipReversalStrategy(Strategy):
    """Morning Dip Reversal v2: BB/KD 超賣 + MA5 確認"""

    # 參數
    bb_period: int = 15              # BB 計算期數
    bb_std: float = 2.0              # BB 標準差倍數
    ma5_period: int = 5              # MA5 期數
    kd_period: int = 9               # KD K 期數
    kd_smooth: int = 3               # KD K 平滑期數
    kd_threshold: float = 20.0       # KD 超賣門檻
    sl_pct: float = 0.3              # 停損 %
    tp_pct: float = 0.6              # 停利 %
    use_bb: bool = True              # 啟用 BB 濾網
    use_kd: bool = False             # 啟用 KD 濾網（預設關閉）
    trend_sma_days: int = 0          # 日線 SMA 天數（0 = 不過濾）
    force_exit_time: time = time(13, 30)

    # latch 窗口
    _W1_START: time = time(9, 15)
    _W1_END: time = time(9, 45)

    def init(self):
        # 預計算指標
        close = pd.Series(self.data.Close, index=self.data.index)

        # BB(15, 2σ)
        bb_ma = close.rolling(self.bb_period).mean()
        bb_std_val = close.rolling(self.bb_period).std(ddof=0)
        self._bb_lower = self.I(lambda: (bb_ma - self.bb_std * bb_std_val).values,
                                name="BB_Lower", overlay=True)
        self._bb_upper = self.I(lambda: (bb_ma + self.bb_std * bb_std_val).values,
                                name="BB_Upper", overlay=True)

        # MA5(1m)
        self._ma5 = self.I(lambda: close.rolling(self.ma5_period).mean().values,
                           name="MA5", overlay=True)

        # Stochastic K(9, 3)
        high_s = pd.Series(self.data.High, index=self.data.index)
        low_s = pd.Series(self.data.Low, index=self.data.index)
        lowest = low_s.rolling(self.kd_period).min()
        highest = high_s.rolling(self.kd_period).max()
        rsv = (close - lowest) / (highest - lowest + 1e-10) * 100
        kd_k = rsv.rolling(self.kd_smooth).mean()
        self._kd_k = self.I(lambda: kd_k.values, name="KD_K")

        # 日線 SMA 趨勢濾網：用前一日收盤價算 SMA，映射回 1 分 K
        if self.trend_sma_days > 0:
            idx = pd.DatetimeIndex(self.data.index)
            daily_close = close.groupby(idx.date).last()
            daily_sma = daily_close.rolling(self.trend_sma_days, min_periods=self.trend_sma_days).mean()
            # shift(1): 用前一日的 SMA，避免 lookahead
            daily_sma = daily_sma.shift(1)
            # 映射回 1 分 K
            date_to_sma = daily_sma.to_dict()
            trend_arr = np.array([date_to_sma.get(d, np.nan) for d in idx.date])
            self._trend_sma = self.I(lambda: trend_arr, name="Trend SMA", overlay=True)
        else:
            self._trend_sma = None

        self._reset_daily()
        self._current_date = None

    def _reset_daily(self):
        self._oversold_latch = False   # BB/KD 超賣 latch
        self._latch_source = None      # 'bb' or 'kd'
        self._entry_done = False
        self._day_done = False         # 超過 W2 就放棄
        self._in_window = 0            # 0=等 W1, 1=W1, 2=W1~W2 間隔, 3=W2
        self._sl_price = None
        self._tp_price = None

    def next(self):
        bar_ts = self.data.index[-1]
        bar_date = bar_ts.date()
        bar_time = bar_ts.time()

        # A. 換日重置
        if bar_date != self._current_date:
            self._current_date = bar_date
            self._reset_daily()

        close = self.data.Close[-1]
        high = self.data.High[-1]
        low = self.data.Low[-1]

        # B. 強制出場
        if bar_time >= self.force_exit_time and self.position:
            self.position.close()
            return

        # C. 持倉管理
        if self.position:
            if low <= self._sl_price:
                self.position.close()
                return
            if high >= self._tp_price:
                self.position.close()
                return
            return

        # D. 當日已進場或已放棄
        if self._entry_done or self._day_done:
            return

        # E. 指標 NaN 檢查
        bb_lower = self._bb_lower[-1]
        ma5 = self._ma5[-1]
        kd_k = self._kd_k[-1]
        if np.isnan(bb_lower) or np.isnan(ma5) or np.isnan(kd_k):
            return

        # F. 時間窗口管理：只看 9:15~9:45
        if bar_time < self._W1_START:
            return
        elif bar_time > self._W1_END:
            self._day_done = True
            return

        # G. Step 1: 超賣 latch
        if not self._oversold_latch:
            if self.use_bb and close <= bb_lower:
                self._oversold_latch = True
                self._latch_source = 'bb'
            elif self.use_kd and kd_k < self.kd_threshold:
                self._oversold_latch = True
                self._latch_source = 'kd'
            return

        # H. Step 2: MA5 確認進場
        if close > ma5:
            # 趨勢濾網：前一日收盤 > SMA 才做多
            if self._trend_sma is not None:
                sma_val = self._trend_sma[-1]
                if np.isnan(sma_val) or close < sma_val:
                    # 趨勢不對，放棄這次 latch
                    self._oversold_latch = False
                    self._latch_source = None
                    return
            self._entry_done = True
            self._sl_price = close * (1 - self.sl_pct / 100)
            self._tp_price = close * (1 + self.tp_pct / 100)
            self.buy()
            return


# ── 資料載入 ──

def load_data(start=None, end=None):
    import duckdb
    with duckdb.connect("data/futures.duckdb", read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()

    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]

    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    return df


def print_summary(stats, label=""):
    trades = stats["_trades"].copy()
    if trades.empty:
        print(f"  {label}: 沒有交易記錄")
        return

    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    max_consec = cur = 0
    for v in (pnl <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    eq = stats["_equity_curve"]["Equity"]
    max_dd_pct = (eq / eq.cummax() - 1).min() * 100

    rows = [
        ("總交易次數",           f"{len(trades)} 筆"),
        ("勝率",                f"{len(wins)/len(trades)*100:.1f}%"),
        ("平均獲利",             f"+{wins.mean():.0f} 點" if len(wins) else "—"),
        ("平均虧損",             f"{losses.mean():.0f} 點" if len(losses) else "—"),
        ("獲利因子 (PF)",        f"{wins.sum() / abs(losses.sum()):.2f}" if len(losses) else "∞"),
        ("最大連續虧損",          f"{max_consec} 筆"),
        ("最大回撤",             f"{max_dd_pct:.2f}%"),
        ("期望值",              f"{pnl.mean():.1f} 點  (NT${pnl.mean()*200:,.0f})"),
        ("總損益",              f"{pnl.sum():.0f} 點  (NT${pnl.sum()*200:,.0f})"),
    ]

    print()
    if label:
        print(f"【{label}】")
    print("=" * 50)
    for lbl, value in rows:
        print(f"  {lbl:<18}  {value}")
    print("=" * 50)


def run_sensitivity(bt, base_params, param_name, values, label):
    """單一參數敏感度分析"""
    print(f"\n── {label} ──")
    for v in values:
        p = {**base_params, param_name: v}
        s = bt.run(**p)
        t = s["_trades"]
        if t.empty:
            print(f"  {param_name}={v}: 無交易")
            continue
        pnl = t["PnL"]
        w = pnl[pnl > 0]
        l = pnl[pnl < 0]
        pf = w.sum() / abs(l.sum()) if len(l) else float('inf')
        print(f"  {param_name}={v}: {len(t):3d} 筆, "
              f"WR {len(w)/len(t)*100:.1f}%, PF {pf:.2f}, "
              f"EV {pnl.mean():.1f} 點")


if __name__ == "__main__":
    print("=" * 60)
    print("H061: Morning Dip Reversal v3 — BB + MA5 + Trend SMA")
    print("=" * 60)

    df_all = load_data()
    print(f"資料: {df_all.index[0]} ~ {df_all.index[-1]}")

    params = dict(
        bb_period=15,
        bb_std=2.0,
        ma5_period=5,
        kd_period=9,
        kd_smooth=3,
        kd_threshold=20.0,
        sl_pct=0.3,
        tp_pct=0.6,
        use_bb=True,
        use_kd=False,
        trend_sma_days=0,
    )

    # ── 1. SMA 天數掃描 (IS 2021~2024) ──
    print("\n" + "=" * 60)
    print("1. Trend SMA 天數掃描 (In-Sample 2021~2024, BB only)")
    print("=" * 60)

    df_is = load_data(start="2021-01-01", end="2024-12-31")
    bt_is = Backtest(df_is, MorningDipReversalStrategy,
                     cash=200_000, commission=0.0, trade_on_close=True)

    print(f"\n{'SMA':>5s}  {'筆數':>5s}  {'勝率':>6s}  {'PF':>6s}  {'EV':>8s}  {'總損益':>10s}")
    print("-" * 50)

    for sma in [0, 5, 10, 20, 40, 60, 120]:
        p = {**params, 'trend_sma_days': sma}
        s = bt_is.run(**p)
        t = s["_trades"]
        if t.empty:
            print(f"  {sma:3d}d   無交易")
            continue
        pnl = t["PnL"]
        w = pnl[pnl > 0]
        l = pnl[pnl < 0]
        pf = w.sum() / abs(l.sum()) if len(l) else float('inf')
        print(f"  {sma:3d}d  {len(t):5d}  {len(w)/len(t)*100:5.1f}%  {pf:5.2f}  "
              f"{pnl.mean():+7.1f}  {pnl.sum():+10.0f}")

    # ── 2. 最佳 SMA 的 IS vs OOS ──
    # 先用 SMA20 作為基準測試
    best_sma_candidates = [10, 20, 40, 60]
    print("\n" + "=" * 60)
    print("2. IS vs OOS 比較 (BB only + 各 SMA)")
    print("=" * 60)

    df_oos = load_data(start="2025-01-01")
    bt_oos = Backtest(df_oos, MorningDipReversalStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)

    print(f"\n{'SMA':>5s}  {'IS筆':>5s} {'IS_WR':>6s} {'IS_PF':>6s} {'IS_EV':>8s}  "
          f"{'OOS筆':>5s} {'OOS_WR':>6s} {'OOS_PF':>6s} {'OOS_EV':>8s}")
    print("-" * 75)

    for sma in best_sma_candidates:
        p = {**params, 'trend_sma_days': sma}

        s_is = bt_is.run(**p)
        t_is = s_is["_trades"]
        s_oos = bt_oos.run(**p)
        t_oos = s_oos["_trades"]

        def _metrics(t):
            if t.empty:
                return 0, 0, 0, 0
            pnl = t["PnL"]
            w = pnl[pnl > 0]
            l = pnl[pnl < 0]
            pf = w.sum() / abs(l.sum()) if len(l) else float('inf')
            return len(t), len(w)/len(t)*100, pf, pnl.mean()

        n1, wr1, pf1, ev1 = _metrics(t_is)
        n2, wr2, pf2, ev2 = _metrics(t_oos)
        print(f"  {sma:3d}d  {n1:5d} {wr1:5.1f}% {pf1:5.2f} {ev1:+7.1f}  "
              f"{n2:5d} {wr2:5.1f}% {pf2:5.2f} {ev2:+7.1f}")

    # ── 3. 最佳組合逐年 ──
    # 選 SMA20 作為預設跑逐年
    best_sma = 20
    params_best = {**params, 'trend_sma_days': best_sma}

    print(f"\n" + "=" * 60)
    print(f"3. 逐年績效 (BB only + SMA{best_sma})")
    print("=" * 60)

    for year in range(2021, 2027):
        df_y = load_data(start=f"{year}-01-01", end=f"{year}-12-31")
        if len(df_y) < 100:
            continue
        bt_y = Backtest(df_y, MorningDipReversalStrategy,
                        cash=200_000, commission=0.0, trade_on_close=True)
        stats_y = bt_y.run(**params_best)
        trades = stats_y["_trades"]
        if trades.empty:
            print(f"  {year}: 無交易")
            continue
        pnl = trades["PnL"]
        w = pnl[pnl > 0]
        l = pnl[pnl < 0]
        pf = w.sum() / abs(l.sum()) if len(l) else float('inf')
        print(f"  {year}: {len(trades):3d} 筆, "
              f"WR {len(w)/len(trades)*100:.1f}%, PF {pf:.2f}, "
              f"EV {pnl.mean():.1f} 點, 總 {pnl.sum():.0f} 點")

    # ── 4. 參數敏感度 (最佳 SMA) ──
    print(f"\n" + "=" * 60)
    print(f"4. 參數敏感度 (IS, BB only + SMA{best_sma})")
    print("=" * 60)

    run_sensitivity(bt_is, params_best, 'sl_pct',
                    [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5], "停損 %")
    run_sensitivity(bt_is, params_best, 'tp_pct',
                    [0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5], "停利 %")

    print("\n=== Phase 2 v3 回測完成 ===")

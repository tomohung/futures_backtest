#!/usr/bin/env python3
"""H050 Phase 0 批次 5-7: 全掃描剩餘候選。

跳過：
  - C 類剩餘（量價指標已證明無效）
  - G4/G5（需個股資料）
  - H 類（太 niche）

測試：
  批次 5（F 類 K 線型態）：F1 長紅後長黑, F2 多頭執帶, F3 多頭母子, F6 黑棒吞噬, F9 抄底長紅
  批次 6（A/B/D 類）：A2 多方維持線, A3 KAMA, A4 Vortex, B1 WaveTrend, B3 QQE, B5 CMO, B7 Ultimate Osc, D2 BBTrend
  批次 7（E 類濾網 + 剩餘）：E3 ADX+Choppy, E4 (done), E5 SZO, B11 CCI超買反轉, A5 Ehlers

Usage:
    uv run python research/active/H050-xq-eddie-pricevol-candidates/explore_batch5_full_scan.py
"""

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"


def load_day_session():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def make_daily(df):
    """合成日線。"""
    daily = df.groupby(df.index.date).agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"),
        Volume=("Volume", "sum"),
    )
    daily.index = pd.to_datetime(daily.index)
    return daily


def make_5m(df):
    return df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()


def stats_line(label, pnls):
    n = len(pnls)
    if n < 5:
        print(f"  {label}: N={n} — 樣本不足")
        return
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = len(wins) / n * 100
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
    marker = "★" if pf > 1.3 and n >= 30 else ""
    print(f"  {label}: N={n} WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt {marker}")


def measure_daily_next(daily, signal_dates, direction=1):
    """測量信號後次日報酬 (close-to-close)。"""
    next_ret = daily["Close"].shift(-1) - daily["Close"]
    ret = next_ret.reindex(signal_dates).dropna() * direction
    return ret


def measure_5m_forward(df5, signal_indices, hold_bars=12, direction=1):
    """5m 信號後持有 N 根。"""
    pnls = []
    for idx in signal_indices:
        idx = pd.Timestamp(idx)
        pos = df5.index.get_loc(idx)
        entry_pos = pos + 1
        exit_pos = entry_pos + hold_bars
        if exit_pos >= len(df5):
            continue
        entry_date = df5.index[entry_pos].date()
        if entry_date != idx.date():
            continue
        exit_date = df5.index[exit_pos].date()
        entry = float(df5.iloc[entry_pos]["Open"])
        if exit_date != entry_date:
            day_end = df5[df5.index.date == entry_date].index[-1]
            exit_p = float(df5.loc[day_end, "Close"])
        else:
            exit_p = float(df5.iloc[exit_pos]["Close"])
        pnls.append((exit_p - entry) * direction)
    return pd.Series(pnls) if pnls else pd.Series(dtype=float)


# ============================================================
# F 類：K 線型態
# ============================================================

def evaluate_f1_long_red_then_black(daily):
    """F1: 長紅後長黑 — 大漲後隔日大跌做空。"""
    print("\n" + "=" * 72)
    print("F1: 長紅後長黑（大漲後做空）")
    print("=" * 72)

    body = daily["Close"] - daily["Open"]
    body_pct = body / daily["Open"] * 100

    for thresh in [1.0, 1.5, 2.0]:
        # 前日長紅 > thresh%
        big_red = body_pct.shift(1) > thresh
        signal_dates = daily[big_red].index
        ret = measure_daily_next(daily, signal_dates, direction=-1)  # 做空
        stats_line(f"前日漲>{thresh}% → 次日做空", ret)

    # 反向：長黑後做多
    print("  --- 反向：長黑後做多 ---")
    for thresh in [1.0, 1.5, 2.0]:
        big_black = body_pct.shift(1) < -thresh
        signal_dates = daily[big_black].index
        ret = measure_daily_next(daily, signal_dates, direction=1)
        stats_line(f"前日跌>{thresh}% → 次日做多", ret)


def evaluate_f2_bullish_belt_hold(daily):
    """F2: 多頭執帶 — 大跌後開在最低收在最高。"""
    print("\n" + "=" * 72)
    print("F2: 多頭執帶（大跌後反轉長紅）")
    print("=" * 72)

    body_pct = (daily["Close"] - daily["Open"]) / daily["Open"] * 100
    day_range = daily["High"] - daily["Low"]

    # 前日大跌
    prev_drop = body_pct.shift(1) < -1.0

    # 當日：開在低點附近 + 收在高點附近（容許 10% 誤差）
    open_near_low = (daily["Open"] - daily["Low"]) < day_range * 0.1
    close_near_high = (daily["High"] - daily["Close"]) < day_range * 0.1
    belt_hold = prev_drop & open_near_low & close_near_high & (body_pct > 0.5)

    signal_dates = daily[belt_hold].index
    ret = measure_daily_next(daily, signal_dates, direction=1)
    stats_line("多頭執帶 → 次日做多", ret)

    # 放寬容許度
    open_near_low2 = (daily["Open"] - daily["Low"]) < day_range * 0.2
    close_near_high2 = (daily["High"] - daily["Close"]) < day_range * 0.2
    belt_hold2 = prev_drop & open_near_low2 & close_near_high2 & (body_pct > 0.5)
    signal_dates2 = daily[belt_hold2].index
    ret2 = measure_daily_next(daily, signal_dates2, direction=1)
    stats_line("多頭執帶(放寬20%) → 次日做多", ret2)


def evaluate_f3_bullish_harami(daily):
    """F3: 多頭母子 — 大跌後前黑K包住後紅K。"""
    print("\n" + "=" * 72)
    print("F3: 多頭母子（前黑包後紅）")
    print("=" * 72)

    prev_body = daily["Close"].shift(1) - daily["Open"].shift(1)
    curr_body = daily["Close"] - daily["Open"]

    # 母：前日黑K（收跌），子：當日紅K（收漲）且在前日實體範圍內
    mother_black = prev_body < 0
    child_red = curr_body > 0
    inside = (daily["Open"] > daily["Close"].shift(1)) & (daily["Close"] < daily["Open"].shift(1))

    # 加上前日大跌的背景
    prev_drop_pct = prev_body / daily["Open"].shift(1) * 100

    for drop_thresh in [0, -0.5, -1.0]:
        if drop_thresh == 0:
            harami = mother_black & child_red & inside
            label = "母子（不限前日跌幅）"
        else:
            harami = mother_black & child_red & inside & (prev_drop_pct < drop_thresh)
            label = f"母子（前日跌>{abs(drop_thresh)}%）"

        signal_dates = daily[harami].index
        ret = measure_daily_next(daily, signal_dates, direction=1)
        stats_line(f"{label} → 次日做多", ret)


def evaluate_f6_bearish_engulfing(daily):
    """F6: 黑棒吞噬紅棒 — 空頭吞噬做空。"""
    print("\n" + "=" * 72)
    print("F6: 黑棒吞噬紅棒（空頭吞噬）")
    print("=" * 72)

    prev_red = daily["Close"].shift(1) > daily["Open"].shift(1)
    curr_black = daily["Close"] < daily["Open"]
    engulf = (daily["Open"] > daily["Close"].shift(1)) & (daily["Close"] < daily["Open"].shift(1))

    bearish_engulf = prev_red & curr_black & engulf
    signal_dates = daily[bearish_engulf].index
    ret = measure_daily_next(daily, signal_dates, direction=-1)
    stats_line("空頭吞噬 → 次日做空", ret)

    # 反向：多頭吞噬
    prev_black = daily["Close"].shift(1) < daily["Open"].shift(1)
    curr_red = daily["Close"] > daily["Open"]
    engulf_bull = (daily["Open"] < daily["Close"].shift(1)) & (daily["Close"] > daily["Open"].shift(1))
    bullish_engulf = prev_black & curr_red & engulf_bull
    signal_dates2 = daily[bullish_engulf].index
    ret2 = measure_daily_next(daily, signal_dates2, direction=1)
    stats_line("多頭吞噬 → 次日做多", ret2)


def evaluate_f9_big_drop_bounce(daily):
    """F9: 大跌後抄底 — 大跌後出現長紅K。"""
    print("\n" + "=" * 72)
    print("F9: 大跌後抄底長紅")
    print("=" * 72)

    body_pct = (daily["Close"] - daily["Open"]) / daily["Open"] * 100
    prev_body_pct = body_pct.shift(1)

    for drop, bounce in [(-1.5, 1.0), (-2.0, 1.0), (-1.5, 1.5), (-2.0, 1.5)]:
        signal = (prev_body_pct < drop) & (body_pct > bounce)
        signal_dates = daily[signal].index
        ret = measure_daily_next(daily, signal_dates, direction=1)
        stats_line(f"前日跌>{abs(drop)}% + 當日漲>{bounce}% → 做多", ret)


# ============================================================
# A 類：趨勢跟隨
# ============================================================

def evaluate_a2_maintenance_line(df5):
    """A2: 多方維持線 — 追蹤前波低點形成支撐。"""
    print("\n" + "=" * 72)
    print("A2: 多方維持線")
    print("=" * 72)

    # 簡化版：rolling min of lows as support, break above = long
    for period in [10, 20]:
        support = df5["Low"].rolling(period).min().shift(1)
        resistance = df5["High"].rolling(period).max().shift(1)

        # 收盤連續 3 根在 support 上方（從下方回到上方）
        above = df5["Close"] > support
        was_below = df5["Close"].shift(3) < support.shift(3)
        signal = above & was_below

        signal = signal[(signal.index.time >= pd.Timestamp("09:00").time()) &
                        (signal.index.time <= pd.Timestamp("12:00").time())]
        first_per_day = signal[signal].groupby(signal[signal].index.date).apply(
            lambda x: x.index[0] if len(x) > 0 else None).dropna()

        pnls = measure_5m_forward(df5, first_per_day.values, 12, 1)
        stats_line(f"Support({period}) 站回 → Long", pnls)


def evaluate_a3_kama(df5):
    """A3: KAMA 考夫曼自適應均線。"""
    print("\n" + "=" * 72)
    print("A3: KAMA 自適應均線")
    print("=" * 72)

    close = df5["Close"]

    for er_period in [10, 20]:
        # Efficiency Ratio
        direction = abs(close - close.shift(er_period))
        volatility = abs(close - close.shift(1)).rolling(er_period).sum()
        er = direction / volatility.replace(0, np.nan)

        # Smoothing constant
        fast_sc = 2 / (2 + 1)
        slow_sc = 2 / (30 + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2

        # KAMA
        kama = pd.Series(index=close.index, dtype=float)
        kama.iloc[:er_period] = np.nan
        kama.iloc[er_period] = close.iloc[er_period]
        for i in range(er_period + 1, len(close)):
            if np.isnan(kama.iloc[i-1]) or np.isnan(sc.iloc[i]):
                kama.iloc[i] = close.iloc[i]
            else:
                kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i-1])

        # Cross signals
        cross_up = (close > kama) & (close.shift(1) <= kama.shift(1))
        cross_dn = (close < kama) & (close.shift(1) >= kama.shift(1))

        for label, cross, direction in [("KAMA Cross Up → Long", cross_up, 1),
                                         ("KAMA Cross Down → Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"KAMA({er_period}) {label}", pnls)


def evaluate_a4_vortex(df5):
    """A4: 漩渦指標 Vortex。"""
    print("\n" + "=" * 72)
    print("A4: Vortex 漩渦指標")
    print("=" * 72)

    for period in [14, 21]:
        vm_plus = abs(df5["High"] - df5["Low"].shift(1))
        vm_minus = abs(df5["Low"] - df5["High"].shift(1))
        tr = np.maximum(df5["High"] - df5["Low"],
                        np.maximum(abs(df5["High"] - df5["Close"].shift(1)),
                                   abs(df5["Low"] - df5["Close"].shift(1))))

        vi_plus = vm_plus.rolling(period).sum() / tr.rolling(period).sum()
        vi_minus = vm_minus.rolling(period).sum() / tr.rolling(period).sum()

        cross_up = (vi_plus > vi_minus) & (vi_plus.shift(1) <= vi_minus.shift(1))
        cross_dn = (vi_plus < vi_minus) & (vi_plus.shift(1) >= vi_minus.shift(1))

        for label, cross, direction in [("VI+ > VI- → Long", cross_up, 1),
                                         ("VI- > VI+ → Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"Vortex({period}) {label}", pnls)


# ============================================================
# B 類：動能/震盪
# ============================================================

def evaluate_b1_wavetrend(df5):
    """B1: WaveTrend Oscillator。"""
    print("\n" + "=" * 72)
    print("B1: WaveTrend Oscillator")
    print("=" * 72)

    hlc3 = (df5["High"] + df5["Low"] + df5["Close"]) / 3

    for ch_period, avg_period in [(10, 21), (9, 12)]:
        esa = hlc3.ewm(span=ch_period).mean()
        d = abs(hlc3 - esa).ewm(span=ch_period).mean()
        ci = (hlc3 - esa) / (0.015 * d).replace(0, np.nan)
        wt1 = ci.ewm(span=avg_period).mean()
        wt2 = wt1.rolling(4).mean()

        # 超買超賣區金叉死叉
        cross_up = (wt1 > wt2) & (wt1.shift(1) <= wt2.shift(1))
        cross_dn = (wt1 < wt2) & (wt1.shift(1) >= wt2.shift(1))

        # 只在超賣區做多、超買區做空
        oversold_cross = cross_up & (wt1 < -60)
        overbought_cross = cross_dn & (wt1 > 60)

        for label, cross, direction in [
            ("超賣金叉 → Long", oversold_cross, 1),
            ("超買死叉 → Short", overbought_cross, -1),
            ("金叉 → Long", cross_up, 1),
            ("死叉 → Short", cross_dn, -1),
        ]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"WT({ch_period},{avg_period}) {label}", pnls)


def evaluate_b3_qqe(df5):
    """B3: QQE — RSI 的平滑版。"""
    print("\n" + "=" * 72)
    print("B3: QQE")
    print("=" * 72)

    for rsi_period, sf in [(14, 5), (6, 3)]:
        delta = df5["Close"].diff()
        gain = delta.where(delta > 0, 0).ewm(span=rsi_period).mean()
        loss = (-delta).where(delta < 0, 0).ewm(span=rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)

        rsi_smooth = rsi.ewm(span=sf).mean()
        dar = abs(rsi_smooth - rsi_smooth.shift(1)).ewm(span=2 * sf).mean() * 4.236

        # Dynamic levels
        long_band = rsi_smooth - dar
        short_band = rsi_smooth + dar

        # Cross
        cross_up = (rsi_smooth > long_band) & (rsi_smooth.shift(1) <= long_band.shift(1))
        cross_dn = (rsi_smooth < short_band) & (rsi_smooth.shift(1) >= short_band.shift(1))

        for label, cross, direction in [("QQE Up → Long", cross_up, 1),
                                         ("QQE Down → Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"QQE({rsi_period},{sf}) {label}", pnls)


def evaluate_b5_cmo(df5):
    """B5: CMO 錢德動量擺盪指標。"""
    print("\n" + "=" * 72)
    print("B5: CMO 錢德動量指標")
    print("=" * 72)

    delta = df5["Close"].diff()
    up = delta.where(delta > 0, 0)
    dn = (-delta).where(delta < 0, 0)

    for period in [9, 14, 20]:
        up_sum = up.rolling(period).sum()
        dn_sum = dn.rolling(period).sum()
        cmo = (up_sum - dn_sum) / (up_sum + dn_sum).replace(0, np.nan) * 100

        cross_up = (cmo > 0) & (cmo.shift(1) <= 0)
        cross_dn = (cmo < 0) & (cmo.shift(1) >= 0)

        for label, cross, direction in [("CMO→0+ Long", cross_up, 1),
                                         ("CMO→0- Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"CMO({period}) {label}", pnls)


def evaluate_b7_ultimate(df5):
    """B7: Ultimate Oscillator。"""
    print("\n" + "=" * 72)
    print("B7: Ultimate Oscillator")
    print("=" * 72)

    bp = df5["Close"] - np.minimum(df5["Low"], df5["Close"].shift(1))
    tr = np.maximum(df5["High"] - df5["Low"],
                    np.maximum(abs(df5["High"] - df5["Close"].shift(1)),
                               abs(df5["Low"] - df5["Close"].shift(1))))

    for p1, p2, p3 in [(7, 14, 28), (5, 10, 20)]:
        avg1 = bp.rolling(p1).sum() / tr.rolling(p1).sum()
        avg2 = bp.rolling(p2).sum() / tr.rolling(p2).sum()
        avg3 = bp.rolling(p3).sum() / tr.rolling(p3).sum()
        uo = (4 * avg1 + 2 * avg2 + avg3) / 7 * 100

        # 超買超賣
        cross_up = (uo > 30) & (uo.shift(1) <= 30)
        cross_dn = (uo < 70) & (uo.shift(1) >= 70)

        for label, cross, direction in [("UO<30→30+ Long", cross_up, 1),
                                         ("UO>70→70- Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"UO({p1}/{p2}/{p3}) {label}", pnls)


def evaluate_b11_cci_reversal(df5):
    """B11: CCI 超買反轉做空。"""
    print("\n" + "=" * 72)
    print("B11: CCI 超買反轉")
    print("=" * 72)

    tp = (df5["High"] + df5["Low"] + df5["Close"]) / 3

    for period in [14, 20]:
        tp_ma = tp.rolling(period).mean()
        md = abs(tp - tp_ma).rolling(period).mean()
        cci = (tp - tp_ma) / (0.015 * md).replace(0, np.nan)

        # 超買反轉做空：CCI 從 +100 以上跌破 +100
        cross_dn = (cci < 100) & (cci.shift(1) >= 100)
        # 超賣反轉做多：CCI 從 -100 以下升破 -100
        cross_up = (cci > -100) & (cci.shift(1) <= -100)

        for label, cross, direction in [("CCI<100 反轉 Short", cross_dn, -1),
                                         ("CCI>-100 反轉 Long", cross_up, 1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"CCI({period}) {label}", pnls)


# ============================================================
# D 類：波動率/通道
# ============================================================

def evaluate_d2_bbtrend(df5):
    """D2: BBTrend — 布林通道衍生趨勢指標。"""
    print("\n" + "=" * 72)
    print("D2: BBTrend")
    print("=" * 72)

    for short_p, long_p in [(20, 50), (10, 30)]:
        sma_s = df5["Close"].rolling(short_p).mean()
        std_s = df5["Close"].rolling(short_p).std()
        upper_s = sma_s + 2 * std_s
        lower_s = sma_s - 2 * std_s
        bw_s = (upper_s - lower_s) / sma_s

        sma_l = df5["Close"].rolling(long_p).mean()
        std_l = df5["Close"].rolling(long_p).std()
        upper_l = sma_l + 2 * std_l
        lower_l = sma_l - 2 * std_l
        bw_l = (upper_l - lower_l) / sma_l

        bbtrend = (bw_s - bw_l) / bw_l.replace(0, np.nan) * 100

        cross_up = (bbtrend > 0) & (bbtrend.shift(1) <= 0)
        cross_dn = (bbtrend < 0) & (bbtrend.shift(1) >= 0)

        for label, cross, direction in [("BBTrend→0+ Long", cross_up, 1),
                                         ("BBTrend→0- Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"BBTrend({short_p}/{long_p}) {label}", pnls)


# ============================================================
# E 類：濾網
# ============================================================

def evaluate_e5_szo(df5):
    """E5: SZO 情緒指數。"""
    print("\n" + "=" * 72)
    print("E5: SZO 情緒指數")
    print("=" * 72)

    sign = np.where(df5["Close"] > df5["Close"].shift(1), 1, -1)
    sign_series = pd.Series(sign, index=df5.index)

    for period in [14, 7]:
        szo = sign_series.rolling(period).sum() / period * 100
        ema_szo = szo.ewm(span=period).mean()

        cross_up = (szo > ema_szo) & (szo.shift(1) <= ema_szo.shift(1))
        cross_dn = (szo < ema_szo) & (szo.shift(1) >= ema_szo.shift(1))

        for label, cross, direction in [("SZO Cross Up Long", cross_up, 1),
                                         ("SZO Cross Dn Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"SZO({period}) {label}", pnls)


def evaluate_a5_ehlers(df5):
    """A5: Ehlers 相關性趨勢指標。"""
    print("\n" + "=" * 72)
    print("A5: Ehlers 相關性趨勢指標")
    print("=" * 72)

    close = df5["Close"]

    for period in [14, 20]:
        # Correlation between price and time index
        x = np.arange(len(close), dtype=float)
        x_series = pd.Series(x, index=close.index)

        corr = close.rolling(period).corr(x_series)

        cross_up = (corr > 0) & (corr.shift(1) <= 0)
        cross_dn = (corr < 0) & (corr.shift(1) >= 0)

        for label, cross, direction in [("Ehlers→0+ Long", cross_up, 1),
                                         ("Ehlers→0- Short", cross_dn, -1)]:
            c = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                      (cross.index.time <= pd.Timestamp("12:00").time())]
            first = c[c].groupby(c[c].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None).dropna()
            pnls = measure_5m_forward(df5, first.values, 12, direction)
            stats_line(f"Ehlers({period}) {label}", pnls)


def main():
    print("=" * 72)
    print("H050 Phase 0 批次 5-7: 全掃描剩餘候選")
    print("=" * 72)

    print("\nLoading day-session 1m data...")
    df = load_day_session()
    df = df[df.index >= "2021-01-01"]
    n_days = len(set(df.index.date))
    print(f"  {len(df):,} bars, {n_days} days")

    daily = make_daily(df)
    print(f"  {len(daily)} daily bars")

    df5 = make_5m(df)
    print(f"  {len(df5):,} 5m bars")

    # F 類：K 線型態（日線）
    evaluate_f1_long_red_then_black(daily)
    evaluate_f2_bullish_belt_hold(daily)
    evaluate_f3_bullish_harami(daily)
    evaluate_f6_bearish_engulfing(daily)
    evaluate_f9_big_drop_bounce(daily)

    # A 類：趨勢跟隨（5m）
    evaluate_a2_maintenance_line(df5)
    evaluate_a3_kama(df5)
    evaluate_a4_vortex(df5)
    evaluate_a5_ehlers(df5)

    # B 類：動能/震盪（5m）
    evaluate_b1_wavetrend(df5)
    evaluate_b3_qqe(df5)
    evaluate_b5_cmo(df5)
    evaluate_b7_ultimate(df5)
    evaluate_b11_cci_reversal(df5)

    # D 類：波動率（5m）
    evaluate_d2_bbtrend(df5)

    # E 類：濾網（5m）
    evaluate_e5_szo(df5)

    print("\n" + "=" * 72)
    print("Done. 標記 ★ 的候選值得進一步研究（PF>1.3 且 N≥30）")
    print("=" * 72)


if __name__ == "__main__":
    main()

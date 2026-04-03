#!/usr/bin/env python3
"""H050 Phase 0 批次 4: 剩餘候選 + 新候選評估。

待測：
  C2 — Weis Wave Volume（波段累積量背離）
  C4 — TSV 時段分割成交量（資金流背離）

新候選：
  B6 — IMI 日內動量指標（專為日內設計）
  C6 — CMF 蔡金資金流量（經典量價）
  E4 — Elder-Ray Index（多空力道）
  B2 — 加速指標（上漲/下跌速度差）

Usage:
    uv run python research/active/H050-xq-eddie-pricevol-candidates/explore_batch4.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

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


def stats_line(label, pnls):
    """印出一行統計。"""
    n = len(pnls)
    if n == 0:
        print(f"  {label}: 0 signals")
        return
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = len(wins) / n * 100
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
    print(f"  {label}: N={n} WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt")


# ============================================================
# C2: Weis Wave Volume
# ============================================================
def evaluate_c2_weis_wave(df):
    """C2: Weis Wave Volume — 波段累積量。

    概念：把價格分成上漲波/下跌波，各自累積成交量。
    信號：下跌波量萎縮 + 上漲波量放大 = 主力進場，做多。

    簡化版：用 5m K，以 close 方向劃分波段。
    """
    print("\n" + "=" * 72)
    print("C2: Weis Wave Volume")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    # 定義波段方向：close > close_prev = up, else down
    df5["direction"] = np.where(df5["Close"] > df5["Close"].shift(1), 1, -1)

    # 計算波段累積量（同方向連續累加，方向變化時重置）
    wave_vol = []
    wave_bars = []
    current_vol = 0
    current_bars = 0
    prev_dir = 0

    for i in range(len(df5)):
        d = df5["direction"].iloc[i]
        v = df5["Volume"].iloc[i]
        if d == prev_dir:
            current_vol += v
            current_bars += 1
        else:
            current_vol = v
            current_bars = 1
            prev_dir = d
        wave_vol.append(current_vol)
        wave_bars.append(current_bars)

    df5["wave_vol"] = wave_vol
    df5["wave_bars"] = wave_bars

    # 信號：前一個下跌波量 < 前前一個上漲波量 × 0.5
    # 且當前轉為上漲 → 做多
    # 需要追蹤波段切換點

    # 改用更簡化的版本：看 rolling 上漲量 vs 下跌量的比率
    up_vol = df5["Volume"].where(df5["direction"] == 1, 0)
    dn_vol = df5["Volume"].where(df5["direction"] == -1, 0)

    for window in [10, 20]:
        up_sum = up_vol.rolling(window).sum()
        dn_sum = dn_vol.rolling(window).sum()
        ratio = up_sum / dn_sum.replace(0, np.nan)
        ratio_prev = ratio.shift(1)

        # 信號：上漲量 > 下跌量 × 1.5（多方放量）+ 前一根 close > open
        for mult in [1.5, 2.0]:
            signal = (ratio_prev > mult) & (df5["Close"].shift(1) > df5["Open"].shift(1))
            signal = signal[(signal.index.time >= pd.Timestamp("09:00").time()) &
                            (signal.index.time <= pd.Timestamp("12:00").time())]

            # 每日第一個信號
            first_per_day = signal[signal].groupby(signal[signal].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None
            ).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append(exit_p - entry)

            stats_line(f"Win{window} UpVol>{mult}x DnVol → Long", pd.Series(pnls))

        # 反向：下跌量 > 上漲量 → 做空
        for mult in [1.5, 2.0]:
            signal_s = (ratio_prev < 1/mult) & (df5["Close"].shift(1) < df5["Open"].shift(1))
            signal_s = signal_s[(signal_s.index.time >= pd.Timestamp("09:00").time()) &
                                (signal_s.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = signal_s[signal_s].groupby(signal_s[signal_s].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None
            ).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append(entry - exit_p)

            stats_line(f"Win{window} DnVol>{mult}x UpVol → Short", pd.Series(pnls))


# ============================================================
# C4: TSV 時段分割成交量
# ============================================================
def evaluate_c4_tsv(df):
    """C4: TSV — Time Segmented Volume。

    TSV = Σ( sign(close - close_prev) × volume ) over N bars
    穿越零軸 = 資金流向翻轉。
    """
    print("\n" + "=" * 72)
    print("C4: TSV 時段分割成交量")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    price_change = df5["Close"] - df5["Close"].shift(1)
    signed_vol = np.sign(price_change) * df5["Volume"]

    for period in [13, 18, 24]:
        tsv = signed_vol.rolling(period).sum()
        tsv_ma = tsv.rolling(7).mean()  # signal line

        # 零軸穿越
        cross_up = (tsv > 0) & (tsv.shift(1) <= 0)
        cross_dn = (tsv < 0) & (tsv.shift(1) >= 0)

        for label, cross, direction in [("TSV Cross Up → Long", cross_up, 1),
                                         ("TSV Cross Down → Short", cross_dn, -1)]:
            cross_filtered = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                                   (cross.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = cross_filtered[cross_filtered].groupby(
                cross_filtered[cross_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"TSV({period}) {label}", pd.Series(pnls))


# ============================================================
# B6: IMI 日內動量指標
# ============================================================
def evaluate_b6_imi(df):
    """B6: Intraday Momentum Index。

    IMI = Σ(gains on up-close bars) / Σ(gains + losses) × 100
    類似 RSI 但只看 K 棒實體（Close vs Open），專為日內設計。
    IMI > 70 超買，IMI < 30 超賣。
    """
    print("\n" + "=" * 72)
    print("B6: IMI 日內動量指標")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    body = df5["Close"] - df5["Open"]
    gains = body.where(body > 0, 0)
    losses = (-body).where(body < 0, 0)

    for period in [14, 20]:
        gain_sum = gains.rolling(period).sum()
        loss_sum = losses.rolling(period).sum()
        imi = gain_sum / (gain_sum + loss_sum).replace(0, np.nan) * 100

        imi_prev = imi.shift(1)

        # 超賣反彈做多：IMI < 30 → 回到 30 以上
        cross_up = (imi > 30) & (imi.shift(1) <= 30)
        # 超買反轉做空：IMI > 70 → 回到 70 以下
        cross_dn = (imi < 70) & (imi.shift(1) >= 70)

        for label, cross, direction in [
            ("IMI<30→30+ 反彈 Long", cross_up, 1),
            ("IMI>70→70- 反轉 Short", cross_dn, -1),
        ]:
            cross_filtered = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                                   (cross.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = cross_filtered[cross_filtered].groupby(
                cross_filtered[cross_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"IMI({period}) {label}", pd.Series(pnls))

        # 順勢策略：IMI > 50 做多、IMI < 50 做空
        for threshold, dir_label, direction in [(60, "IMI>60 Long", 1), (40, "IMI<40 Short", -1)]:
            if direction == 1:
                cross = (imi > threshold) & (imi.shift(1) <= threshold)
            else:
                cross = (imi < threshold) & (imi.shift(1) >= threshold)

            cross_filtered = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                                   (cross.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = cross_filtered[cross_filtered].groupby(
                cross_filtered[cross_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"IMI({period}) {dir_label}", pd.Series(pnls))


# ============================================================
# C6: CMF 蔡金資金流量
# ============================================================
def evaluate_c6_cmf(df):
    """C6: Chaikin Money Flow。

    CLV = ((Close - Low) - (High - Close)) / (High - Low)
    CMF = Σ(CLV × Volume, N) / Σ(Volume, N)
    CMF > 0 = 買壓主導, CMF < 0 = 賣壓主導。
    """
    print("\n" + "=" * 72)
    print("C6: CMF 蔡金資金流量")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    hl_range = (df5["High"] - df5["Low"]).replace(0, np.nan)
    clv = ((df5["Close"] - df5["Low"]) - (df5["High"] - df5["Close"])) / hl_range
    mfv = clv * df5["Volume"]

    for period in [10, 20, 30]:
        cmf = mfv.rolling(period).sum() / df5["Volume"].rolling(period).sum()

        # 零軸穿越
        cross_up = (cmf > 0) & (cmf.shift(1) <= 0)
        cross_dn = (cmf < 0) & (cmf.shift(1) >= 0)

        for label, cross, direction in [
            ("CMF Cross Up → Long", cross_up, 1),
            ("CMF Cross Down → Short", cross_dn, -1),
        ]:
            cross_filtered = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                                   (cross.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = cross_filtered[cross_filtered].groupby(
                cross_filtered[cross_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"CMF({period}) {label}", pd.Series(pnls))


# ============================================================
# E4: Elder-Ray Index
# ============================================================
def evaluate_e4_elder_ray(df):
    """E4: Elder-Ray Index。

    Bull Power = High - EMA(N)
    Bear Power = Low - EMA(N)
    趨勢方向 + Bull/Bear Power 交叉零軸判斷多空。

    信號：EMA 上升 + Bear Power < 0 但回升 → 做多（回檔結束）
    """
    print("\n" + "=" * 72)
    print("E4: Elder-Ray Index")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    for ema_period in [13, 20, 26]:
        ema = df5["Close"].ewm(span=ema_period).mean()
        bull_power = df5["High"] - ema
        bear_power = df5["Low"] - ema

        ema_rising = ema > ema.shift(1)
        ema_falling = ema < ema.shift(1)

        # 做多：EMA 上升 + Bear Power 從負轉正（回檔結束）
        bp_cross_up = (bear_power > 0) & (bear_power.shift(1) <= 0)
        long_signal = ema_rising & bp_cross_up

        # 做空：EMA 下降 + Bull Power 從正轉負（反彈結束）
        bp_cross_dn = (bull_power < 0) & (bull_power.shift(1) >= 0)
        short_signal = ema_falling & bp_cross_dn

        for label, signal, direction in [
            ("EMA↑ + BearPower→0+ Long", long_signal, 1),
            ("EMA↓ + BullPower→0- Short", short_signal, -1),
        ]:
            sig_filtered = signal[(signal.index.time >= pd.Timestamp("09:00").time()) &
                                  (signal.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = sig_filtered[sig_filtered].groupby(
                sig_filtered[sig_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"EMA({ema_period}) {label}", pd.Series(pnls))


# ============================================================
# B2: 加速指標 Acceleration
# ============================================================
def evaluate_b2_acceleration(df):
    """B2: 加速指標。

    AccUp = SMA(max(close - close_prev, 0), 5)
    AccDn = SMA(max(close_prev - close, 0), 5)
    Acc = AccUp - AccDn
    由負轉正 = 多方加速 → 做多。
    """
    print("\n" + "=" * 72)
    print("B2: 加速指標 Acceleration")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    change = df5["Close"] - df5["Close"].shift(1)
    up = change.where(change > 0, 0)
    dn = (-change).where(change < 0, 0)

    for period in [5, 10, 14]:
        acc_up = up.rolling(period).mean()
        acc_dn = dn.rolling(period).mean()
        acc = acc_up - acc_dn

        cross_up = (acc > 0) & (acc.shift(1) <= 0)
        cross_dn = (acc < 0) & (acc.shift(1) >= 0)

        for label, cross, direction in [
            ("Acc→0+ Long", cross_up, 1),
            ("Acc→0- Short", cross_dn, -1),
        ]:
            cross_filtered = cross[(cross.index.time >= pd.Timestamp("09:00").time()) &
                                   (cross.index.time <= pd.Timestamp("12:00").time())]

            first_per_day = cross_filtered[cross_filtered].groupby(
                cross_filtered[cross_filtered].index.date
            ).apply(lambda x: x.index[0] if len(x) > 0 else None).dropna()

            pnls = []
            for ts in first_per_day.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            stats_line(f"Acc({period}) {label}", pd.Series(pnls))


def main():
    print("=" * 72)
    print("H050 Phase 0 批次 4: C2/C4/B6/C6/E4/B2 候選評估")
    print("=" * 72)

    print("\nLoading day-session 1m data...")
    df = load_day_session()
    df = df[df.index >= "2021-01-01"]
    n_days = len(set(df.index.date))
    print(f"  {len(df):,} bars, {n_days} days")

    evaluate_c2_weis_wave(df)
    evaluate_c4_tsv(df)
    evaluate_b6_imi(df)
    evaluate_c6_cmf(df)
    evaluate_e4_elder_ray(df)
    evaluate_b2_acceleration(df)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

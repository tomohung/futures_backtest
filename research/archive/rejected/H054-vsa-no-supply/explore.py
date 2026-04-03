#!/usr/bin/env python3
"""H054 Phase 1: VSA No Supply — 分佈探索研究。

分析項目：
1. No Supply 信號的時段分佈（幾點最多、幾點最有效）
2. IS/OOS 分年度績效（2021-2024 / 2025-2026）
3. Range/Volume 門檻敏感度（0.3x~0.7x 組合）
4. 測試不同 MA 期間（10, 20, 40）和趨勢定義
5. No Demand（反向做空）的獨立分析
6. 每日觸發次數分佈（是否過度交易？）
7. 與 EstHL 的信號日重疊率（概略）

Usage:
    uv run python research/active/H054-vsa-no-supply/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"


def load_day_session():
    """載入日盤 1m OHLCV 資料。"""
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


def build_5m(df):
    """從 1m 合成 5m K 棒。"""
    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    return df5


def add_indicators(df5, ma_period=20):
    """加上 VSA 所需的技術指標。"""
    df5 = df5.copy()
    df5["Range"] = df5["High"] - df5["Low"]
    df5["MA"] = df5["Close"].rolling(ma_period).mean()
    df5["MA_prev"] = df5["MA"].shift(1)
    df5["RangeMA"] = df5["Range"].rolling(ma_period).mean()
    df5["VolMA"] = df5["Volume"].rolling(ma_period).mean()
    df5["trend_up"] = df5["MA"] > df5["MA_prev"]
    df5["trend_dn"] = df5["MA"] < df5["MA_prev"]
    return df5


def find_signals(df5, range_mult, vol_mult, direction="long"):
    """找出 No Supply (long) 或 No Demand (short) 信號。

    Returns: DataFrame with signal bars (index = signal bar timestamp)
    """
    if direction == "long":
        # No Supply: 上升趨勢 + 收跌 + 窄幅 + 低量 + 下一根收漲確認
        signal_bar = (
            df5["trend_up"] &
            (df5["Close"] < df5["Open"]) &
            (df5["Range"] < df5["RangeMA"] * range_mult) &
            (df5["Volume"] < df5["VolMA"] * vol_mult)
        )
        confirm = df5["Close"].shift(-1) > df5["Open"].shift(-1)
    else:
        # No Demand: 下降趨勢 + 收漲 + 窄幅 + 低量 + 下一根收跌確認
        signal_bar = (
            df5["trend_dn"] &
            (df5["Close"] > df5["Open"]) &
            (df5["Range"] < df5["RangeMA"] * range_mult) &
            (df5["Volume"] < df5["VolMA"] * vol_mult)
        )
        confirm = df5["Close"].shift(-1) < df5["Open"].shift(-1)

    signals = df5[signal_bar & confirm].copy()
    return signals


def measure_trades(df5, signals, hold_bars=12, direction="long"):
    """測量信號後的交易績效。

    進場：確認 bar 收盤後的下一根開盤（即 signal + 2 bars）
    出場：持有 hold_bars 根（60min = 12 bars @5m）

    Returns: DataFrame with trade results
    """
    mult = 1 if direction == "long" else -1
    trades = []

    for idx in signals.index:
        pos = df5.index.get_loc(idx)
        # 進場在 signal bar + 2（確認 bar 的下一根）
        entry_pos = pos + 2
        exit_pos = entry_pos + hold_bars

        if exit_pos >= len(df5):
            continue

        # 確保不跨日
        entry_date = df5.index[entry_pos].date()
        exit_date = df5.index[min(exit_pos, len(df5) - 1)].date()
        if entry_date != idx.date():
            continue

        entry_price = float(df5.iloc[entry_pos]["Open"])
        # 如果跨日，用當日最後一根收盤
        if exit_date != entry_date:
            # 找當日最後一根
            day_mask = df5.index.date == entry_date
            day_end = df5[day_mask].index[-1]
            exit_pos_actual = df5.index.get_loc(day_end)
            exit_price = float(df5.iloc[exit_pos_actual]["Close"])
            future = df5.iloc[entry_pos:exit_pos_actual + 1]
        else:
            exit_price = float(df5.iloc[exit_pos]["Close"])
            future = df5.iloc[entry_pos:exit_pos + 1]

        pnl = (exit_price - entry_price) * mult
        mfe = (future["High"].max() - entry_price) * mult if direction == "long" \
            else (entry_price - future["Low"].min())
        mae = (entry_price - future["Low"].min()) if direction == "long" \
            else (future["High"].max() - entry_price)

        trades.append({
            "date": idx.date(),
            "signal_time": idx.strftime("%H:%M"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "mfe": mfe,
            "mae": mae,
            "hour": idx.hour,
        })

    return pd.DataFrame(trades)


def print_stats(trades_df, label=""):
    """印出統計摘要。"""
    if trades_df.empty:
        print(f"  {label}: 0 trades")
        return

    n = len(trades_df)
    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] < 0]
    flat = trades_df[trades_df["pnl"] == 0]
    wr = len(wins) / n * 100
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
    avg_pnl = trades_df["pnl"].mean()
    avg_mfe = trades_df["mfe"].mean()
    avg_mae = trades_df["mae"].mean()

    print(f"  {label}: N={n} WR={wr:.1f}% PF={pf:.2f} "
          f"AvgPnL={avg_pnl:+.1f}pt MFE={avg_mfe:.0f} MAE={avg_mae:.0f}")


# ============================================================
# 分析 1: 時段分佈
# ============================================================
def analyze_time_distribution(df5, range_mult=0.5, vol_mult=0.5):
    """分析信號在不同時段的分佈和有效性。"""
    print("\n" + "=" * 72)
    print("1. No Supply 信號時段分佈")
    print("=" * 72)

    signals = find_signals(df5, range_mult, vol_mult, "long")
    # 限制在 09:00-13:00（給 exit 留空間）
    signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                      (signals.index.time <= pd.Timestamp("13:00").time())]

    trades = measure_trades(df5, signals, hold_bars=12, direction="long")
    if trades.empty:
        print("  No trades found")
        return

    print(f"\n  總信號數: N={len(trades)}")
    print(f"\n  {'時段':<8} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8} {'MFE':>5} {'MAE':>5}")
    print(f"  {'-'*44}")

    for hour in sorted(trades["hour"].unique()):
        subset = trades[trades["hour"] == hour]
        n = len(subset)
        wins = subset[subset["pnl"] > 0]
        losses = subset[subset["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {hour:02d}:00    {n:>5} {wr:>5.1f}% {pf:>6.2f} {subset['pnl'].mean():>+7.1f} "
              f"{subset['mfe'].mean():>5.0f} {subset['mae'].mean():>5.0f}")


# ============================================================
# 分析 2: IS/OOS 分年度績效
# ============================================================
def analyze_is_oos(df5, range_mult=0.5, vol_mult=0.5):
    """IS (2021-2024) vs OOS (2025-2026) 績效比較。"""
    print("\n" + "=" * 72)
    print("2. IS/OOS 分年度績效")
    print("=" * 72)

    signals = find_signals(df5, range_mult, vol_mult, "long")
    signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                      (signals.index.time <= pd.Timestamp("13:00").time())]
    trades = measure_trades(df5, signals, hold_bars=12, direction="long")

    if trades.empty:
        print("  No trades")
        return

    trades["year"] = pd.to_datetime(trades["date"]).dt.year

    print(f"\n  {'年度':<6} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8} {'TotalPnL':>10}")
    print(f"  {'-'*47}")

    for year in sorted(trades["year"].unique()):
        subset = trades[trades["year"] == year]
        n = len(subset)
        wins = subset[subset["pnl"] > 0]
        losses = subset[subset["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        total = subset["pnl"].sum()
        print(f"  {year:<6} {n:>5} {wr:>5.1f}% {pf:>6.2f} {subset['pnl'].mean():>+7.1f} {total:>+9.0f}")

    # IS vs OOS summary
    is_trades = trades[trades["year"] <= 2024]
    oos_trades = trades[trades["year"] >= 2025]
    print(f"\n  --- IS (2021-2024) vs OOS (2025-2026) ---")
    print_stats(is_trades, "IS ")
    print_stats(oos_trades, "OOS")


# ============================================================
# 分析 3: Range/Volume 門檻敏感度
# ============================================================
def analyze_threshold_sensitivity(df5):
    """測試不同 range_mult × vol_mult 組合。"""
    print("\n" + "=" * 72)
    print("3. Range/Volume 門檻敏感度")
    print("=" * 72)

    print(f"\n  {'Range':>6} {'Vol':>5} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'-'*42}")

    for r_mult in [0.3, 0.4, 0.5, 0.6, 0.7]:
        for v_mult in [0.3, 0.4, 0.5, 0.6, 0.7]:
            signals = find_signals(df5, r_mult, v_mult, "long")
            signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                              (signals.index.time <= pd.Timestamp("13:00").time())]
            trades = measure_trades(df5, signals, hold_bars=12, direction="long")
            n = len(trades)
            if n < 10:
                print(f"  {r_mult:>5.1f}x {v_mult:>4.1f}x {n:>5} — 樣本不足")
                continue
            wins = trades[trades["pnl"] > 0]
            losses = trades[trades["pnl"] < 0]
            wr = len(wins) / n * 100
            pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
            print(f"  {r_mult:>5.1f}x {v_mult:>4.1f}x {n:>5} {wr:>5.1f}% {pf:>6.2f} "
                  f"{trades['pnl'].mean():>+7.1f}")


# ============================================================
# 分析 4: 不同 MA 期間和趨勢定義
# ============================================================
def analyze_ma_periods(df5_raw):
    """測試 MA 10, 20, 40 的影響。"""
    print("\n" + "=" * 72)
    print("4. 不同 MA 期間的影響")
    print("=" * 72)

    print(f"\n  {'MA':>4} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'-'*35}")

    for ma_period in [10, 20, 40, 60]:
        df5 = add_indicators(df5_raw, ma_period=ma_period)
        signals = find_signals(df5, 0.5, 0.5, "long")
        signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                          (signals.index.time <= pd.Timestamp("13:00").time())]
        trades = measure_trades(df5, signals, hold_bars=12, direction="long")
        n = len(trades)
        if n < 10:
            print(f"  {ma_period:>4} {n:>5} — 樣本不足")
            continue
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {ma_period:>4} {n:>5} {wr:>5.1f}% {pf:>6.2f} {trades['pnl'].mean():>+7.1f}")

    # 額外測試：MA 斜率而非單純方向
    print("\n  --- 趨勢定義：MA20 連續 N 根上升 ---")
    df5 = add_indicators(df5_raw, ma_period=20)
    for consec in [1, 3, 5]:
        ma_rising = df5["MA"] > df5["MA"].shift(1)
        if consec > 1:
            for i in range(1, consec):
                ma_rising = ma_rising & (df5["MA"].shift(i) > df5["MA"].shift(i + 1))

        df5_temp = df5.copy()
        df5_temp["trend_up"] = ma_rising

        signal_bar = (
            df5_temp["trend_up"] &
            (df5_temp["Close"] < df5_temp["Open"]) &
            (df5_temp["Range"] < df5_temp["RangeMA"] * 0.5) &
            (df5_temp["Volume"] < df5_temp["VolMA"] * 0.5)
        )
        confirm = df5_temp["Close"].shift(-1) > df5_temp["Open"].shift(-1)
        signals = df5_temp[signal_bar & confirm]
        signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                          (signals.index.time <= pd.Timestamp("13:00").time())]
        trades = measure_trades(df5_temp, signals, hold_bars=12, direction="long")
        n = len(trades)
        if n < 10:
            print(f"  連續{consec}根: {n:>5} — 樣本不足")
            continue
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  連續{consec}根: {n:>5} {wr:>5.1f}% {pf:>6.2f} {trades['pnl'].mean():>+7.1f}")


# ============================================================
# 分析 5: No Demand（反向做空）
# ============================================================
def analyze_no_demand(df5):
    """No Demand 獨立分析。"""
    print("\n" + "=" * 72)
    print("5. No Demand（反向做空）獨立分析")
    print("=" * 72)

    print(f"\n  {'Range':>6} {'Vol':>5} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'-'*42}")

    for r_mult, v_mult in [(0.5, 0.5), (0.6, 0.6), (0.5, 0.7), (0.7, 0.5)]:
        signals = find_signals(df5, r_mult, v_mult, "short")
        signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                          (signals.index.time <= pd.Timestamp("13:00").time())]
        trades = measure_trades(df5, signals, hold_bars=12, direction="short")
        n = len(trades)
        if n < 10:
            print(f"  {r_mult:>5.1f}x {v_mult:>4.1f}x {n:>5} — 樣本不足")
            continue
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {r_mult:>5.1f}x {v_mult:>4.1f}x {n:>5} {wr:>5.1f}% {pf:>6.2f} "
              f"{trades['pnl'].mean():>+7.1f}")

    # IS/OOS for best combo
    print("\n  --- No Demand IS/OOS (0.5x/0.5x) ---")
    signals = find_signals(df5, 0.5, 0.5, "short")
    signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                      (signals.index.time <= pd.Timestamp("13:00").time())]
    trades = measure_trades(df5, signals, hold_bars=12, direction="short")
    if not trades.empty:
        trades["year"] = pd.to_datetime(trades["date"]).dt.year
        for year in sorted(trades["year"].unique()):
            subset = trades[trades["year"] == year]
            n = len(subset)
            wins = subset[subset["pnl"] > 0]
            losses = subset[subset["pnl"] < 0]
            wr = len(wins) / n * 100
            pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
            print(f"  {year}: N={n} WR={wr:.1f}% PF={pf:.2f} AvgPnL={subset['pnl'].mean():+.1f}")


# ============================================================
# 分析 6: 每日觸發次數
# ============================================================
def analyze_daily_frequency(df5, range_mult=0.5, vol_mult=0.5):
    """每日觸發次數分佈。"""
    print("\n" + "=" * 72)
    print("6. 每日觸發次數分佈")
    print("=" * 72)

    for direction, label in [("long", "No Supply"), ("short", "No Demand")]:
        signals = find_signals(df5, range_mult, vol_mult, direction)
        signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                          (signals.index.time <= pd.Timestamp("13:00").time())]
        if signals.empty:
            print(f"\n  {label}: 0 signals")
            continue

        daily_counts = signals.groupby(signals.index.date).size()
        total_days = len(set(df5.index.date))
        signal_days = len(daily_counts)

        print(f"\n  {label}:")
        print(f"    交易日總數: {total_days}")
        print(f"    有信號的天數: {signal_days} ({signal_days/total_days*100:.1f}%)")
        print(f"    平均每日觸發: {daily_counts.mean():.1f} (有信號日)")
        print(f"    平均每日觸發: {len(signals)/total_days:.2f} (所有日)")
        print(f"    最多一天: {daily_counts.max()}")

        print(f"    分佈:")
        for count in sorted(daily_counts.unique()):
            n_days = (daily_counts == count).sum()
            print(f"      {count} 次/日: {n_days} 天")


# ============================================================
# 分析 7: 不同持有時間
# ============================================================
def analyze_hold_periods(df5, range_mult=0.5, vol_mult=0.5):
    """測試不同持有期間。"""
    print("\n" + "=" * 72)
    print("7. 不同持有期間（No Supply Long）")
    print("=" * 72)

    signals = find_signals(df5, range_mult, vol_mult, "long")
    signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                      (signals.index.time <= pd.Timestamp("12:00").time())]

    print(f"\n  {'Hold':>8} {'N':>5} {'WR%':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'-'*39}")

    for hold_bars, label in [(6, "30min"), (12, "60min"), (24, "120min"), (0, "收盤")]:
        if hold_bars == 0:
            # 持有到收盤
            trades = measure_trades_to_close(df5, signals, direction="long")
        else:
            trades = measure_trades(df5, signals, hold_bars=hold_bars, direction="long")
        n = len(trades)
        if n < 10:
            print(f"  {label:>8} {n:>5} — 樣本不足")
            continue
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {label:>8} {n:>5} {wr:>5.1f}% {pf:>6.2f} {trades['pnl'].mean():>+7.1f}")


def measure_trades_to_close(df5, signals, direction="long"):
    """持有到當日收盤。"""
    mult = 1 if direction == "long" else -1
    trades = []

    for idx in signals.index:
        pos = df5.index.get_loc(idx)
        entry_pos = pos + 2
        if entry_pos >= len(df5):
            continue

        entry_date = df5.index[entry_pos].date()
        if entry_date != idx.date():
            continue

        entry_price = float(df5.iloc[entry_pos]["Open"])

        # 找當日最後一根
        day_mask = df5.index.date == entry_date
        day_bars = df5[day_mask]
        exit_price = float(day_bars.iloc[-1]["Close"])
        future = day_bars.loc[day_bars.index >= df5.index[entry_pos]]

        pnl = (exit_price - entry_price) * mult
        mfe = (future["High"].max() - entry_price) * mult if direction == "long" \
            else (entry_price - future["Low"].min())
        mae = (entry_price - future["Low"].min()) if direction == "long" \
            else (future["High"].max() - entry_price)

        trades.append({
            "date": idx.date(),
            "signal_time": idx.strftime("%H:%M"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "mfe": mfe,
            "mae": mae,
            "hour": idx.hour,
        })

    return pd.DataFrame(trades)


def main():
    print("=" * 72)
    print("H054 Phase 1: VSA No Supply — 分佈探索研究")
    print("=" * 72)

    print("\nLoading day-session 1m data...")
    df = load_day_session()
    df = df[df.index >= "2021-01-01"]
    n_days = len(set(df.index.date))
    print(f"  {len(df):,} bars, {n_days} days ({df.index.min().date()} ~ {df.index.max().date()})")

    print("\nBuilding 5m bars...")
    df5_raw = build_5m(df)
    print(f"  {len(df5_raw):,} bars")

    # Default indicators with MA20
    df5 = add_indicators(df5_raw, ma_period=20)

    analyze_time_distribution(df5)
    analyze_is_oos(df5)
    analyze_threshold_sensitivity(df5)
    analyze_ma_periods(df5_raw)
    analyze_no_demand(df5)
    analyze_daily_frequency(df5)
    analyze_hold_periods(df5)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

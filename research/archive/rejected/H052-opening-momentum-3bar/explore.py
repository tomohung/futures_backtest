#!/usr/bin/env python3
"""H052 Phase 1: 開盤 3 分鐘連續收紅動能 — 分佈探索。

Tasks:
  1. 確認 N=3 連續收紅的分佈（分年度、分星期）
  2. 測試反向（N=3 連續收綠 → 做空）
  3. 分析信號日的日內走勢特徵（MFE 時間分佈、最大回撤時機）
  4. 比對信號日與 EstHL/Reversal 的重疊率
  5. 測試加入量能條件（3 根都放量 vs 不限量）

Usage:
    uv run python research/active/H052-opening-momentum-3bar/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H052-opening-momentum-3bar/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_BARS = 3  # 前 3 根 1mK


def load_day_session():
    """Load 1m day-session data."""
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


def detect_signals(df, n_bars=N_BARS):
    """Detect consecutive bullish/bearish opening bars.

    Returns:
        long_signals: list of dicts (date, entry, day data) for N consecutive green bars
        short_signals: list of dicts for N consecutive red bars
    """
    daily = df.groupby(df.index.date)
    long_signals = []
    short_signals = []

    for date, day in daily:
        bars = day.head(n_bars)
        if len(bars) < n_bars:
            continue

        after = day.iloc[n_bars:]
        if len(after) == 0:
            continue

        entry = after["Open"].iloc[0]
        exit_close = day["Close"].iloc[-1]
        day_high = day["High"].max()
        day_low = day["Low"].min()

        info = {
            "date": date,
            "year": pd.Timestamp(date).year,
            "weekday": pd.Timestamp(date).weekday(),
            "weekday_name": pd.Timestamp(date).day_name()[:3],
            "entry": entry,
            "exit": exit_close,
            "day_high": day_high,
            "day_low": day_low,
            "day_range": day_high - day_low,
            "open_3bar_vol": bars["Volume"].sum(),
            "open_3bar_avg_vol": bars["Volume"].mean(),
        }

        # Check bullish: all close > open
        all_green = all(bars["Close"] > bars["Open"])
        # Check bearish: all close < open
        all_red = all(bars["Close"] < bars["Open"])

        if all_green:
            pnl_long = exit_close - entry
            mfe_long = after["High"].max() - entry
            mae_long = entry - after["Low"].min()
            # MFE time: when did max favorable occur?
            mfe_idx = after["High"].idxmax()
            mae_idx = after["Low"].idxmin()
            info.update({
                "pnl": pnl_long,
                "mfe": mfe_long,
                "mae": mae_long,
                "mfe_time": mfe_idx.time(),
                "mae_time": mae_idx.time(),
                "mfe_minute": mfe_idx.hour * 60 + mfe_idx.minute,
                "mae_minute": mae_idx.hour * 60 + mae_idx.minute,
            })
            long_signals.append(info)

        if all_red:
            pnl_short = entry - exit_close
            mfe_short = entry - after["Low"].min()
            mae_short = after["High"].max() - entry
            mfe_idx = after["Low"].idxmin()
            mae_idx = after["High"].idxmax()
            info_short = info.copy()
            info_short.update({
                "pnl": pnl_short,
                "mfe": mfe_short,
                "mae": mae_short,
                "mfe_time": mfe_idx.time(),
                "mae_time": mae_idx.time(),
                "mfe_minute": mfe_idx.hour * 60 + mfe_idx.minute,
                "mae_minute": mae_idx.hour * 60 + mae_idx.minute,
            })
            short_signals.append(info_short)

    return long_signals, short_signals


def print_basic_stats(signals, label, n_days):
    """Print basic stats for a signal set."""
    if not signals:
        print(f"\n  {label}: 無信號！")
        return None

    r = pd.DataFrame(signals)
    n = len(r)
    wins = r[r["pnl"] > 0]
    losses = r[r["pnl"] < 0]
    wr = len(wins) / n * 100
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
    avg_pnl = r["pnl"].mean()
    med_pnl = r["pnl"].median()

    print(f"\n  {label}")
    print(f"  {'─' * 50}")
    print(f"  信號日: {n} / {n_days} ({n/n_days*100:.1f}%)")
    print(f"  勝率: {wr:.1f}% (N={n})")
    print(f"  PF: {pf:.2f}")
    print(f"  平均 PnL: {avg_pnl:+.1f}pt, 中位數: {med_pnl:+.1f}pt")
    print(f"  平均 MFE: {r['mfe'].mean():.0f}pt, 平均 MAE: {r['mae'].mean():.0f}pt")
    print(f"  MFE/MAE: {r['mfe'].mean()/r['mae'].mean():.2f}" if r['mae'].mean() > 0 else "")

    return r


def task1_yearly_weekday(long_df, n_days_by_year):
    """Task 1: 分年度、分星期分析。"""
    print("\n" + "=" * 72)
    print("Task 1: N=3 連續收紅 — 分年度、分星期分佈")
    print("=" * 72)

    # By year
    print("\n  --- 分年度 ---")
    print(f"  {'Year':>6} {'N':>5} {'Days':>6} {'Freq%':>6} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'─'*6} {'─'*5} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")

    for year in sorted(long_df["year"].unique()):
        yr = long_df[long_df["year"] == year]
        n = len(yr)
        total = n_days_by_year.get(year, 0)
        wins = yr[yr["pnl"] > 0]
        losses = yr[yr["pnl"] < 0]
        wr = len(wins) / n * 100 if n > 0 else 0
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        freq = n / total * 100 if total > 0 else 0
        print(f"  {year:>6} {n:>5} {total:>6} {freq:>5.1f}% {wr:>5.1f}% {pf:>6.2f} {yr['pnl'].mean():>+7.1f}")

    # By weekday
    print("\n  --- 分星期 ---")
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    print(f"  {'Day':>5} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'─'*5} {'─'*5} {'─'*6} {'─'*6} {'─'*8}")

    for wd in range(5):
        wd_df = long_df[long_df["weekday"] == wd]
        n = len(wd_df)
        if n == 0:
            print(f"  {weekday_names[wd]:>5} {0:>5}")
            continue
        wins = wd_df[wd_df["pnl"] > 0]
        losses = wd_df[wd_df["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {weekday_names[wd]:>5} {n:>5} {wr:>5.1f}% {pf:>6.2f} {wd_df['pnl'].mean():>+7.1f}")


def task3_mfe_mae_timing(long_df, short_df):
    """Task 3: MFE/MAE 時間分佈分析。"""
    print("\n" + "=" * 72)
    print("Task 3: 信號日日內走勢特徵（MFE/MAE 時間分佈）")
    print("=" * 72)

    for label, df in [("做多（3 連紅）", long_df), ("做空（3 連綠）", short_df)]:
        if df is None or len(df) == 0:
            continue
        print(f"\n  {label} (N={len(df)})")
        print(f"  {'─' * 50}")

        # MFE time distribution by hour buckets
        mfe_mins = df["mfe_minute"]
        mae_mins = df["mae_minute"]

        # Time buckets: 08:48-09:30, 09:30-10:30, 10:30-11:30, 11:30-12:30, 12:30-13:45
        buckets = [
            ("08:48-09:30", 528, 570),
            ("09:30-10:30", 570, 630),
            ("10:30-11:30", 630, 690),
            ("11:30-12:30", 690, 750),
            ("12:30-13:45", 750, 825),
        ]

        print(f"\n  MFE 時間分佈（最大有利價格出現時間）:")
        for name, start, end in buckets:
            count = ((mfe_mins >= start) & (mfe_mins < end)).sum()
            pct = count / len(df) * 100
            bar = "█" * int(pct / 2)
            print(f"    {name}: {count:>4} ({pct:>5.1f}%) {bar}")

        print(f"\n  MAE 時間分佈（最大不利價格出現時間）:")
        for name, start, end in buckets:
            count = ((mae_mins >= start) & (mae_mins < end)).sum()
            pct = count / len(df) * 100
            bar = "█" * int(pct / 2)
            print(f"    {name}: {count:>4} ({pct:>5.1f}%) {bar}")

        # MFE before MAE ratio (favorable move comes first)
        mfe_first = (mfe_mins < mae_mins).sum()
        print(f"\n  MFE 先於 MAE: {mfe_first}/{len(df)} ({mfe_first/len(df)*100:.1f}%)")

        # Avg PnL when MFE before/after MAE
        mfe_first_mask = mfe_mins < mae_mins
        if mfe_first_mask.sum() > 0 and (~mfe_first_mask).sum() > 0:
            print(f"    MFE先: avg PnL = {df.loc[mfe_first_mask, 'pnl'].mean():+.1f}pt (N={mfe_first_mask.sum()})")
            print(f"    MAE先: avg PnL = {df.loc[~mfe_first_mask, 'pnl'].mean():+.1f}pt (N={(~mfe_first_mask).sum()})")


def task4_overlap(long_dates, short_dates):
    """Task 4: 比對信號日與 EstHL/Reversal 的重疊率。

    透過跑 S001 和 S002 回測取得交易日。
    """
    print("\n" + "=" * 72)
    print("Task 4: 與 EstHL / Reversal 信號日重疊率")
    print("=" * 72)

    from backtesting import Backtest
    from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
    from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
    from src.strategies.reversal import ReversalStrategy

    # Run S001 EstHL
    print("\n  Running S001 EstHL backtest...")
    df_esthl = load_data_for_orb_est_hl()
    bt1 = Backtest(df_esthl, ORBWithEstHLExitStrategy,
                   cash=200_000, commission=0.0, trade_on_close=True)
    stats1 = bt1.run(
        sl_ema_fraction=0.25, adx_min=0.0, long_only=True,
        vwap_days=2, skip_thursday=True, skip_friday=True,
    )
    esthl_dates = set(pd.to_datetime(stats1["_trades"]["EntryTime"]).dt.date)

    # Run S002 Reversal
    print("  Running S002 Reversal backtest...")
    df_rev = load_data_for_reversal()
    bt2 = Backtest(df_rev, ReversalStrategy,
                   cash=200_000, commission=0.0, trade_on_close=True)
    stats2 = bt2.run(
        vol_ratio=1.2, sl_ema_fraction=0.25,
        exhaust_fraction=0.5, signal_skip=0, sat_pullback_fraction=0.5,
    )
    reversal_dates = set(pd.to_datetime(stats2["_trades"]["EntryTime"]).dt.date)

    print(f"\n  EstHL 交易日數: {len(esthl_dates)}")
    print(f"  Reversal 交易日數: {len(reversal_dates)}")
    print(f"  EstHL ∪ Reversal: {len(esthl_dates | reversal_dates)}")

    # Long signal overlap
    long_set = set(long_dates)
    short_set = set(short_dates)

    overlap_esthl_long = long_set & esthl_dates
    overlap_rev_long = long_set & reversal_dates
    overlap_any_long = long_set & (esthl_dates | reversal_dates)

    print(f"\n  --- 3 連紅做多 (N={len(long_set)}) ---")
    print(f"  與 EstHL 重疊: {len(overlap_esthl_long)} ({len(overlap_esthl_long)/len(long_set)*100:.1f}%)")
    print(f"  與 Reversal 重疊: {len(overlap_rev_long)} ({len(overlap_rev_long)/len(long_set)*100:.1f}%)")
    print(f"  與任一策略重疊: {len(overlap_any_long)} ({len(overlap_any_long)/len(long_set)*100:.1f}%)")
    print(f"  獨立信號（無重疊）: {len(long_set - overlap_any_long)} ({len(long_set - overlap_any_long)/len(long_set)*100:.1f}%)")

    # Overlap-day PnL vs non-overlap
    if len(long_set) > 0:
        long_df_all = pd.DataFrame({"date": long_dates})
        # We'll return the sets for later analysis
        pass

    if short_set:
        overlap_esthl_short = short_set & esthl_dates
        overlap_rev_short = short_set & reversal_dates
        overlap_any_short = short_set & (esthl_dates | reversal_dates)
        print(f"\n  --- 3 連綠做空 (N={len(short_set)}) ---")
        print(f"  與 EstHL 重疊: {len(overlap_esthl_short)} ({len(overlap_esthl_short)/len(short_set)*100:.1f}%)")
        print(f"  與 Reversal 重疊: {len(overlap_rev_short)} ({len(overlap_rev_short)/len(short_set)*100:.1f}%)")
        print(f"  與任一策略重疊: {len(overlap_any_short)} ({len(overlap_any_short)/len(short_set)*100:.1f}%)")


def task5_volume_filter(df, n_bars=N_BARS):
    """Task 5: 測試加入量能條件。"""
    print("\n" + "=" * 72)
    print("Task 5: 量能條件測試（3 根都放量 vs 不限量）")
    print("=" * 72)

    daily = df.groupby(df.index.date)

    # Compute 20-day rolling average of first 3 bars' volume
    first_3_vols = {}
    for date, day in daily:
        bars = day.head(n_bars)
        if len(bars) >= n_bars:
            first_3_vols[date] = bars["Volume"].mean()

    vol_series = pd.Series(first_3_vols).sort_index()
    vol_ma20 = vol_series.rolling(20, min_periods=20).mean()

    # Test different volume ratios
    print(f"\n  基準：前 3 根平均量 vs 20 日同時段均量")
    print(f"\n  {'Filter':>12} {'Long N':>7} {'WR':>6} {'PF':>6} {'AvgPnL':>8} | {'Short N':>8} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'─'*12} {'─'*7} {'─'*6} {'─'*6} {'─'*8}   {'─'*8} {'─'*6} {'─'*6} {'─'*8}")

    for vol_ratio_label, vol_ratio in [("不限量", 0.0), (">0.8x", 0.8), (">1.0x", 1.0), (">1.2x", 1.2), (">1.5x", 1.5)]:
        long_res = []
        short_res = []

        for date, day in daily:
            bars = day.head(n_bars)
            if len(bars) < n_bars:
                continue

            after = day.iloc[n_bars:]
            if len(after) == 0:
                continue

            # Volume filter
            if vol_ratio > 0:
                avg_vol = bars["Volume"].mean()
                threshold = vol_ma20.get(date, np.nan)
                if np.isnan(threshold) or avg_vol < vol_ratio * threshold:
                    continue

            entry = after["Open"].iloc[0]
            exit_close = day["Close"].iloc[-1]

            if all(bars["Close"] > bars["Open"]):
                pnl = exit_close - entry
                long_res.append({"pnl": pnl})

            if all(bars["Close"] < bars["Open"]):
                pnl = entry - exit_close
                short_res.append({"pnl": pnl})

        # Long stats
        ln = len(long_res)
        if ln > 0:
            lr = pd.DataFrame(long_res)
            lw = (lr["pnl"] > 0).sum()
            ll = lr[lr["pnl"] <= 0]
            lwr = lw / ln * 100
            lpf = lr[lr["pnl"] > 0]["pnl"].sum() / abs(ll["pnl"].sum()) if len(ll) > 0 else float("inf")
            lavg = lr["pnl"].mean()
        else:
            lwr = lpf = lavg = 0

        # Short stats
        sn = len(short_res)
        if sn > 0:
            sr = pd.DataFrame(short_res)
            sw = (sr["pnl"] > 0).sum()
            sl = sr[sr["pnl"] <= 0]
            swr = sw / sn * 100
            spf = sr[sr["pnl"] > 0]["pnl"].sum() / abs(sl["pnl"].sum()) if len(sl) > 0 else float("inf")
            savg = sr["pnl"].mean()
        else:
            swr = spf = savg = 0

        print(f"  {vol_ratio_label:>12} {ln:>7} {lwr:>5.1f}% {lpf:>6.2f} {lavg:>+7.1f}   {sn:>8} {swr:>5.1f}% {spf:>6.2f} {savg:>+7.1f}")


def main():
    print("H052 Phase 1: 開盤 3 分鐘連續收紅動能 — 分佈探索")
    print("=" * 72)

    # Load data
    print("\nLoading day-session 1m data...")
    df = load_day_session()
    n_days = len(set(df.index.date))
    print(f"Loaded {len(df):,} bars, {n_days} trading days [{df.index[0].date()} → {df.index[-1].date()}]")

    # Count days by year
    dates = pd.Series(list(set(df.index.date)))
    n_days_by_year = dates.groupby(dates.apply(lambda d: d.year)).count().to_dict()

    # Detect signals
    long_signals, short_signals = detect_signals(df)

    # Task 1 + 2: Basic stats and yearly/weekday breakdown
    print("\n" + "=" * 72)
    print("Task 1 & 2: 基本統計 + 反向測試")
    print("=" * 72)

    long_df = print_basic_stats(long_signals, "做多：N=3 連續收紅", n_days)
    short_df = print_basic_stats(short_signals, "做空：N=3 連續收綠", n_days)

    # Year/weekday breakdown for long
    if long_df is not None:
        task1_yearly_weekday(long_df, n_days_by_year)

    # Year/weekday breakdown for short
    if short_df is not None:
        print("\n  --- 做空分年度 ---")
        print(f"  {'Year':>6} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
        print(f"  {'─'*6} {'─'*5} {'─'*6} {'─'*6} {'─'*8}")
        for year in sorted(short_df["year"].unique()):
            yr = short_df[short_df["year"] == year]
            n = len(yr)
            wins = yr[yr["pnl"] > 0]
            losses = yr[yr["pnl"] < 0]
            wr = len(wins) / n * 100 if n > 0 else 0
            pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
            print(f"  {year:>6} {n:>5} {wr:>5.1f}% {pf:>6.2f} {yr['pnl'].mean():>+7.1f}")

    # Task 3: MFE/MAE timing
    task3_mfe_mae_timing(long_df, short_df)

    # Task 4: Overlap with EstHL/Reversal
    long_dates = [s["date"] for s in long_signals]
    short_dates = [s["date"] for s in short_signals]
    task4_overlap(long_dates, short_dates)

    # Task 5: Volume filter
    task5_volume_filter(df)

    print("\n" + "=" * 72)
    print("Done! Results above.")
    print("=" * 72)


if __name__ == "__main__":
    main()

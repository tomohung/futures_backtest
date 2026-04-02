#!/usr/bin/env python3
"""H052 補充探索：現貨開盤 9:00 那根 5 分 K 確認方向。

信號定義：
  做多：09:00 5mK 收紅（Close > Open）且 High > 08:45~08:59 最高（站上新高）
  做空：09:00 5mK 收黑（Close < Open）且 Low  < 08:45~08:59 最低（跌破新低）

進場：09:05 Open
出場：13:45 Close（naive）

也測試變化：
  - 只要收紅/收黑（不需新高/新低）
  - 只要新高/新低（不限紅黑）
  - 加入量能條件

Usage:
    uv run python research/active/H052-opening-momentum-3bar/explore_cash_open.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"


def load_day_session_1m():
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


def build_5m(df_1m):
    df_5m = df_1m.resample("5min").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
    return df_5m


def compute_stats(results, label, n_days):
    """Compute and print stats for a signal set."""
    if not results:
        print(f"\n  {label}: 無信號！")
        return None

    r = pd.DataFrame(results)
    n = len(r)
    wins = r[r["pnl"] > 0]
    losses = r[r["pnl"] <= 0]
    wr = len(wins) / n * 100
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 and losses["pnl"].sum() != 0 else float("inf")

    print(f"\n  {label}")
    print(f"  {'─' * 60}")
    print(f"  信號日: {n} / {n_days} ({n/n_days*100:.1f}%)")
    print(f"  勝率: {wr:.1f}% (N={n})")
    print(f"  PF: {pf:.2f}")
    print(f"  平均 PnL: {r['pnl'].mean():+.1f}pt, 中位數: {r['pnl'].median():+.1f}pt")
    print(f"  Avg MFE: {r['mfe'].mean():.0f}pt, Avg MAE: {r['mae'].mean():.0f}pt")
    if r["mae"].mean() > 0:
        print(f"  MFE/MAE: {r['mfe'].mean()/r['mae'].mean():.2f}")

    return r


def print_yearly_weekday(r, n_days_by_year):
    """Print year and weekday breakdown."""
    print(f"\n  {'Year':>6} {'N':>4} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'─'*6} {'─'*4} {'─'*6} {'─'*6} {'─'*8}")
    for year in sorted(r["year"].unique()):
        yr = r[r["year"] == year]
        yn = len(yr)
        yw = yr[yr["pnl"] > 0]
        yl = yr[yr["pnl"] <= 0]
        ywr = len(yw) / yn * 100
        ypf = yw["pnl"].sum() / abs(yl["pnl"].sum()) if len(yl) > 0 and yl["pnl"].sum() != 0 else float("inf")
        total = n_days_by_year.get(year, "?")
        print(f"  {year:>6} {yn:>4} {ywr:>5.1f}% {ypf:>6.2f} {yr['pnl'].mean():>+7.1f}")

    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    print(f"\n  {'Day':>5} {'N':>4} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'─'*5} {'─'*4} {'─'*6} {'─'*6} {'─'*8}")
    for wd in range(5):
        wd_df = r[r["weekday"] == wd]
        wn = len(wd_df)
        if wn == 0:
            print(f"  {weekday_names[wd]:>5} {0:>4}")
            continue
        ww = wd_df[wd_df["pnl"] > 0]
        wl = wd_df[wd_df["pnl"] <= 0]
        wwr = len(ww) / wn * 100
        wpf = ww["pnl"].sum() / abs(wl["pnl"].sum()) if len(wl) > 0 and wl["pnl"].sum() != 0 else float("inf")
        print(f"  {weekday_names[wd]:>5} {wn:>4} {wwr:>5.1f}% {wpf:>6.2f} {wd_df['pnl'].mean():>+7.1f}")


def mfe_mae_timing(r, label):
    """Analyze MFE/MAE timing distribution."""
    print(f"\n  {label} MFE/MAE 時間分佈 (N={len(r)})")
    buckets = [
        ("09:05-09:30", 545, 570),
        ("09:30-10:30", 570, 630),
        ("10:30-11:30", 630, 690),
        ("11:30-12:30", 690, 750),
        ("12:30-13:45", 750, 825),
    ]
    print(f"  MFE:")
    for name, start, end in buckets:
        count = ((r["mfe_minute"] >= start) & (r["mfe_minute"] < end)).sum()
        pct = count / len(r) * 100
        bar = "█" * int(pct / 2)
        print(f"    {name}: {count:>3} ({pct:>5.1f}%) {bar}")

    print(f"  MAE:")
    for name, start, end in buckets:
        count = ((r["mae_minute"] >= start) & (r["mae_minute"] < end)).sum()
        pct = count / len(r) * 100
        bar = "█" * int(pct / 2)
        print(f"    {name}: {count:>3} ({pct:>5.1f}%) {bar}")

    mfe_first = (r["mfe_minute"] < r["mae_minute"]).sum()
    mae_first = len(r) - mfe_first
    print(f"\n  MFE 先於 MAE: {mfe_first}/{len(r)} ({mfe_first/len(r)*100:.1f}%)")
    mfe_first_mask = r["mfe_minute"] < r["mae_minute"]
    if mfe_first_mask.sum() > 0 and (~mfe_first_mask).sum() > 0:
        print(f"    MFE先: avg PnL = {r.loc[mfe_first_mask, 'pnl'].mean():+.1f}pt (N={mfe_first_mask.sum()})")
        print(f"    MAE先: avg PnL = {r.loc[~mfe_first_mask, 'pnl'].mean():+.1f}pt (N={(~mfe_first_mask).sum()})")


def main():
    print("H052 補充探索：現貨 9:00 開盤 5mK 確認方向")
    print("=" * 72)

    df_1m = load_day_session_1m()
    df_5m = build_5m(df_1m)
    n_days = len(set(df_1m.index.date))
    print(f"Loaded {n_days} trading days")

    dates_all = pd.Series(list(set(df_1m.index.date)))
    n_days_by_year = dates_all.groupby(dates_all.apply(lambda d: d.year)).count().to_dict()

    daily_1m = df_1m.groupby(df_1m.index.date)
    daily_5m = df_5m.groupby(df_5m.index.date)

    # ────────────────────────────────────────────────────────
    # Signal detection
    # ────────────────────────────────────────────────────────
    # For each day:
    #   pre_market = 08:45~08:59 (3 bars of 5m: 08:45, 08:50, 08:55)
    #   cash_bar   = 09:00~09:04 (the 5m bar at 09:00)
    #   after      = 09:05+ (remaining day)

    long_full = []      # 收紅 + 新高
    short_full = []     # 收黑 + 新低
    long_green_only = []   # 只要收紅
    short_red_only = []    # 只要收黑
    long_newhigh_only = [] # 只要新高
    short_newlow_only = [] # 只要新低

    for date, day_5m in daily_5m:
        day_1m = daily_1m.get_group(date) if date in daily_1m.groups else None
        if day_1m is None:
            continue

        # Pre-market bars (08:45~08:59 in 5m = times < 09:00)
        pre = day_5m[day_5m.index.time < pd.Timestamp("09:00").time()]
        if len(pre) == 0:
            continue

        pre_high = pre["High"].max()
        pre_low = pre["Low"].min()

        # Cash open bar (09:00)
        cash_bars = day_5m[day_5m.index.time == pd.Timestamp("09:00").time()]
        if len(cash_bars) == 0:
            continue
        cash_bar = cash_bars.iloc[0]

        # After bars in 1m (from 09:05)
        after = day_1m[day_1m.index.time >= pd.Timestamp("09:05").time()]
        if len(after) == 0:
            continue

        entry = after["Open"].iloc[0]
        exit_close = day_1m["Close"].iloc[-1]
        day_high = day_1m["High"].max()
        day_low = day_1m["Low"].min()

        is_green = cash_bar["Close"] > cash_bar["Open"]
        is_red = cash_bar["Close"] < cash_bar["Open"]
        is_new_high = cash_bar["High"] > pre_high
        is_new_low = cash_bar["Low"] < pre_low

        base_info = {
            "date": date,
            "year": pd.Timestamp(date).year,
            "weekday": pd.Timestamp(date).weekday(),
            "entry": entry,
            "pre_high": pre_high,
            "pre_low": pre_low,
            "cash_open": cash_bar["Open"],
            "cash_close": cash_bar["Close"],
            "cash_high": cash_bar["High"],
            "cash_low": cash_bar["Low"],
            "cash_vol": cash_bar["Volume"],
            "day_range": day_high - day_low,
        }

        # ── Long signals ──
        if is_green or is_new_high:
            pnl = exit_close - entry
            mfe = after["High"].max() - entry
            mae = entry - after["Low"].min()
            mfe_idx = after["High"].idxmax()
            mae_idx = after["Low"].idxmin()
            info = {**base_info, "pnl": pnl, "mfe": mfe, "mae": mae,
                    "mfe_minute": mfe_idx.hour * 60 + mfe_idx.minute,
                    "mae_minute": mae_idx.hour * 60 + mae_idx.minute}

            if is_green and is_new_high:
                long_full.append(info)
            if is_green:
                long_green_only.append(info)
            if is_new_high:
                long_newhigh_only.append(info)

        # ── Short signals ──
        if is_red or is_new_low:
            pnl = entry - exit_close
            mfe = entry - after["Low"].min()
            mae = after["High"].max() - entry
            mfe_idx = after["Low"].idxmin()
            mae_idx = after["High"].idxmax()
            info = {**base_info, "pnl": pnl, "mfe": mfe, "mae": mae,
                    "mfe_minute": mfe_idx.hour * 60 + mfe_idx.minute,
                    "mae_minute": mae_idx.hour * 60 + mae_idx.minute}

            if is_red and is_new_low:
                short_full.append(info)
            if is_red:
                short_red_only.append(info)
            if is_new_low:
                short_newlow_only.append(info)

    # ────────────────────────────────────────────────────────
    # Results
    # ────────────────────────────────────────────────────────

    print("\n" + "=" * 72)
    print("A. 完整條件：收紅/黑 + 新高/新低")
    print("=" * 72)

    r_long = compute_stats(long_full, "做多：09:00 5mK 收紅 + 站上新高", n_days)
    if r_long is not None:
        print_yearly_weekday(r_long, n_days_by_year)
        mfe_mae_timing(r_long, "做多")

    r_short = compute_stats(short_full, "做空：09:00 5mK 收黑 + 跌破新低", n_days)
    if r_short is not None:
        print_yearly_weekday(r_short, n_days_by_year)
        mfe_mae_timing(r_short, "做空")

    print("\n" + "=" * 72)
    print("B. 拆解條件：單獨看各組合")
    print("=" * 72)

    # Summary table
    configs = [
        ("收紅+新高 → 做多", long_full),
        ("只收紅 → 做多", long_green_only),
        ("只新高 → 做多", long_newhigh_only),
        ("收黑+新低 → 做空", short_full),
        ("只收黑 → 做空", short_red_only),
        ("只新低 → 做空", short_newlow_only),
    ]

    print(f"\n  {'條件':　<20} {'N':>5} {'Freq%':>6} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'MedPnL':>8} {'MFE':>6} {'MAE':>6}")
    print(f"  {'─'*20} {'─'*5} {'─'*6} {'─'*6} {'─'*6} {'─'*8} {'─'*8} {'─'*6} {'─'*6}")

    for label, signals in configs:
        if not signals:
            print(f"  {label:　<20} {0:>5}")
            continue
        r = pd.DataFrame(signals)
        n = len(r)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] <= 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 and losses["pnl"].sum() != 0 else float("inf")
        print(f"  {label:　<20} {n:>5} {n/n_days*100:>5.1f}% {wr:>5.1f}% {pf:>6.2f} "
              f"{r['pnl'].mean():>+7.1f} {r['pnl'].median():>+7.1f} "
              f"{r['mfe'].mean():>5.0f} {r['mae'].mean():>5.0f}")

    # ────────────────────────────────────────────────────────
    # C. Overlap with EstHL/Reversal
    # ────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("C. 與 EstHL / Reversal 重疊率")
    print("=" * 72)

    from backtesting import Backtest
    from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
    from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
    from src.strategies.reversal import ReversalStrategy

    print("  Running S001 EstHL...")
    df_e = load_data_for_orb_est_hl()
    bt1 = Backtest(df_e, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats1 = bt1.run(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                      skip_thursday=True, skip_friday=True)
    esthl_dates = set(pd.to_datetime(stats1["_trades"]["EntryTime"]).dt.date)

    print("  Running S002 Reversal...")
    df_r = load_data_for_reversal()
    bt2 = Backtest(df_r, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats2 = bt2.run(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                      signal_skip=0, sat_pullback_fraction=0.5)
    reversal_dates = set(pd.to_datetime(stats2["_trades"]["EntryTime"]).dt.date)

    any_strat = esthl_dates | reversal_dates

    for label, signals in [("收紅+新高做多", long_full), ("收黑+新低做空", short_full)]:
        if not signals:
            continue
        sig_dates = set(s["date"] for s in signals)
        n_sig = len(sig_dates)
        ov_e = len(sig_dates & esthl_dates)
        ov_r = len(sig_dates & reversal_dates)
        ov_any = len(sig_dates & any_strat)
        indep = n_sig - ov_any
        print(f"\n  {label} (N={n_sig})")
        print(f"    與 EstHL: {ov_e} ({ov_e/n_sig*100:.1f}%)")
        print(f"    與 Reversal: {ov_r} ({ov_r/n_sig*100:.1f}%)")
        print(f"    與任一: {ov_any} ({ov_any/n_sig*100:.1f}%)")
        print(f"    獨立信號: {indep} ({indep/n_sig*100:.1f}%)")

    # ────────────────────────────────────────────────────────
    # D. Volume filter on full condition
    # ────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("D. 量能條件（09:00 那根 5mK 量 vs 20 日同時段均量）")
    print("=" * 72)

    # Compute 20-day rolling avg of 09:00 5m bar volume
    bar_0900_vols = {}
    for date, day_5m in daily_5m:
        cash_bars = day_5m[day_5m.index.time == pd.Timestamp("09:00").time()]
        if len(cash_bars) > 0:
            bar_0900_vols[date] = cash_bars.iloc[0]["Volume"]

    vol_s = pd.Series(bar_0900_vols).sort_index()
    vol_ma20 = vol_s.rolling(20, min_periods=20).mean()

    for label, signals in [("收紅+新高做多", long_full), ("收黑+新低做空", short_full)]:
        if not signals:
            continue

        print(f"\n  {label}")
        print(f"  {'Filter':>10} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
        print(f"  {'─'*10} {'─'*5} {'─'*6} {'─'*6} {'─'*8}")

        for vlabel, vr in [("不限量", 0.0), (">0.8x", 0.8), (">1.0x", 1.0), (">1.2x", 1.2), (">1.5x", 1.5)]:
            filtered = []
            for s in signals:
                if vr > 0:
                    threshold = vol_ma20.get(s["date"], np.nan)
                    if np.isnan(threshold) or s["cash_vol"] < vr * threshold:
                        continue
                filtered.append(s)

            fn = len(filtered)
            if fn == 0:
                print(f"  {vlabel:>10} {0:>5}")
                continue
            fr = pd.DataFrame(filtered)
            fw = fr[fr["pnl"] > 0]
            fl = fr[fr["pnl"] <= 0]
            fwr = len(fw) / fn * 100
            fpf = fw["pnl"].sum() / abs(fl["pnl"].sum()) if len(fl) > 0 and fl["pnl"].sum() != 0 else float("inf")
            print(f"  {vlabel:>10} {fn:>5} {fwr:>5.1f}% {fpf:>6.2f} {fr['pnl'].mean():>+7.1f}")

    print("\n" + "=" * 72)
    print("Done!")
    print("=" * 72)


if __name__ == "__main__":
    main()

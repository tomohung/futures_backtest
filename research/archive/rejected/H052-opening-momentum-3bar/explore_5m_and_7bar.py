#!/usr/bin/env python3
"""H052 補充探索：5 分 K 連三紅/綠 + 1 分 K 連 7 黑做空深度分析。

兩個分析：
  A. 改用 5 分 K，前 3 根連續收紅/收綠 → 做多/做空
  B. 1 分 K 前 7 根全收綠 → 做空（崩跌日捕捉），深入分析個案

Usage:
    uv run python research/active/H052-opening-momentum-3bar/explore_5m_and_7bar.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H052-opening-momentum-3bar/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_day_session_1m():
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


def build_5m(df_1m):
    """Resample 1m to 5m OHLCV."""
    df_5m = df_1m.resample("5min").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
    return df_5m


def analyze_consecutive(df, n_bars, timeframe_label):
    """Analyze consecutive green/red bars for given N."""
    daily = df.groupby(df.index.date)
    n_days = len(set(df.index.date))

    for direction, label, check_fn, pnl_fn in [
        ("long", "連紅做多", lambda bars: all(bars["Close"] > bars["Open"]),
         lambda entry, exit_c: exit_c - entry),
        ("short", "連綠做空", lambda bars: all(bars["Close"] < bars["Open"]),
         lambda entry, exit_c: entry - exit_c),
    ]:
        results = []
        for date, day in daily:
            bars = day.head(n_bars)
            if len(bars) < n_bars:
                continue

            if not check_fn(bars):
                continue

            after = day.iloc[n_bars:]
            if len(after) == 0:
                continue

            entry = after["Open"].iloc[0]
            exit_close = day["Close"].iloc[-1]
            pnl = pnl_fn(entry, exit_close)
            mfe = after["High"].max() - entry if direction == "long" else entry - after["Low"].min()
            mae = entry - after["Low"].min() if direction == "long" else after["High"].max() - entry

            results.append({
                "date": date,
                "year": pd.Timestamp(date).year,
                "weekday": pd.Timestamp(date).weekday(),
                "entry": entry,
                "pnl": pnl,
                "mfe": mfe,
                "mae": mae,
                "day_range": day["High"].max() - day["Low"].min(),
            })

        print(f"\n  {timeframe_label} N={n_bars} {label}")
        print(f"  {'─' * 55}")

        if not results:
            print(f"  無信號！")
            continue

        r = pd.DataFrame(results)
        n = len(r)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] <= 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 and losses["pnl"].sum() != 0 else float("inf")

        print(f"  信號日: {n} / {n_days} ({n/n_days*100:.1f}%)")
        print(f"  勝率: {wr:.1f}% (N={n})")
        print(f"  PF: {pf:.2f}")
        print(f"  平均 PnL: {r['pnl'].mean():+.1f}pt, 中位數: {r['pnl'].median():+.1f}pt")
        print(f"  Avg MFE: {r['mfe'].mean():.0f}pt, Avg MAE: {r['mae'].mean():.0f}pt")
        if r['mae'].mean() > 0:
            print(f"  MFE/MAE: {r['mfe'].mean()/r['mae'].mean():.2f}")

        # Year breakdown
        print(f"\n  {'Year':>6} {'N':>4} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
        print(f"  {'─'*6} {'─'*4} {'─'*6} {'─'*6} {'─'*8}")
        for year in sorted(r["year"].unique()):
            yr = r[r["year"] == year]
            yn = len(yr)
            yw = yr[yr["pnl"] > 0]
            yl = yr[yr["pnl"] <= 0]
            ywr = len(yw) / yn * 100 if yn > 0 else 0
            ypf = yw["pnl"].sum() / abs(yl["pnl"].sum()) if len(yl) > 0 and yl["pnl"].sum() != 0 else float("inf")
            print(f"  {year:>6} {yn:>4} {ywr:>5.1f}% {ypf:>6.2f} {yr['pnl'].mean():>+7.1f}")

        # Weekday breakdown
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

        yield direction, r


def analyze_7bar_short_detail(df_1m):
    """1 分 K 前 7 根全收綠 → 做空：深度個案分析。"""
    print("\n" + "=" * 72)
    print("Part B: 1 分 K 前 7 根連續收綠 → 做空（崩跌日捕捉）")
    print("=" * 72)

    daily = df_1m.groupby(df_1m.index.date)
    n_days = len(set(df_1m.index.date))

    results = []
    for date, day in daily:
        bars = day.head(7)
        if len(bars) < 7:
            continue
        if not all(bars["Close"] < bars["Open"]):
            continue

        after = day.iloc[7:]
        if len(after) == 0:
            continue

        entry = after["Open"].iloc[0]
        exit_close = day["Close"].iloc[-1]
        pnl_short = entry - exit_close
        mfe = entry - after["Low"].min()
        mae = after["High"].max() - entry

        # 開盤跌幅（前 7 根總跌幅）
        open_drop = bars["Open"].iloc[0] - bars["Close"].iloc[-1]

        # 日內最大跌幅（from open）
        day_open = day["Open"].iloc[0]
        max_drop_from_open = day_open - day["Low"].min()

        # MFE 時間
        mfe_idx = after["Low"].idxmin()
        mae_idx = after["High"].idxmax()

        results.append({
            "date": date,
            "year": pd.Timestamp(date).year,
            "weekday_name": pd.Timestamp(date).day_name()[:3],
            "entry": entry,
            "exit": exit_close,
            "pnl": pnl_short,
            "mfe": mfe,
            "mae": mae,
            "open_drop": open_drop,
            "max_drop_from_open": max_drop_from_open,
            "day_range": day["High"].max() - day["Low"].min(),
            "mfe_time": mfe_idx.strftime("%H:%M"),
            "mae_time": mae_idx.strftime("%H:%M"),
            "open_7bar_vol": bars["Volume"].sum(),
        })

    if not results:
        print("  無信號！")
        return

    r = pd.DataFrame(results)
    n = len(r)
    wins = r[r["pnl"] > 0]
    losses = r[r["pnl"] <= 0]
    wr = len(wins) / n * 100
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 and losses["pnl"].sum() != 0 else float("inf")

    print(f"\n  信號日: {n} / {n_days} ({n/n_days*100:.1f}%)")
    print(f"  勝率: {wr:.1f}% (N={n})")
    print(f"  PF: {pf:.2f}")
    print(f"  平均 PnL: {r['pnl'].mean():+.1f}pt, 中位數: {r['pnl'].median():+.1f}pt")
    print(f"  Avg MFE: {r['mfe'].mean():.0f}pt, Avg MAE: {r['mae'].mean():.0f}pt")
    print(f"  平均開盤 7 根跌幅: {r['open_drop'].mean():.0f}pt")
    print(f"  平均日內最大跌幅: {r['max_drop_from_open'].mean():.0f}pt")

    # 個案列表
    print(f"\n  --- 完整個案列表 ---")
    print(f"  {'Date':>12} {'Wk':>3} {'Entry':>7} {'Exit':>7} {'PnL':>7} {'MFE':>6} {'MAE':>6} {'MFE@':>6} {'Range':>6} {'Drop7':>6}")
    print(f"  {'─'*12} {'─'*3} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6}")
    for _, row in r.iterrows():
        marker = "✓" if row["pnl"] > 0 else "✗"
        print(f"  {str(row['date']):>12} {row['weekday_name']:>3} "
              f"{row['entry']:>7.0f} {row['exit']:>7.0f} {row['pnl']:>+6.0f}{marker} "
              f"{row['mfe']:>5.0f} {row['mae']:>5.0f} {row['mfe_time']:>6} "
              f"{row['day_range']:>5.0f} {row['open_drop']:>5.0f}")

    # 也測試 N=5, 6, 8 做空以形成完整梯度
    print(f"\n  --- 1mK 連續收綠做空：N=3~10 梯度 ---")
    print(f"  {'N':>3} {'Signal':>7} {'Freq%':>6} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'MedPnL':>8} {'AvgMFE':>7} {'AvgMAE':>7}")
    print(f"  {'─'*3} {'─'*7} {'─'*6} {'─'*6} {'─'*6} {'─'*8} {'─'*8} {'─'*7} {'─'*7}")

    for n_bars in [3, 4, 5, 6, 7, 8, 9, 10]:
        res = []
        for date, day in daily:
            bars = day.head(n_bars)
            if len(bars) < n_bars:
                continue
            if not all(bars["Close"] < bars["Open"]):
                continue
            after = day.iloc[n_bars:]
            if len(after) == 0:
                continue
            entry = after["Open"].iloc[0]
            exit_close = day["Close"].iloc[-1]
            pnl = entry - exit_close
            mfe = entry - after["Low"].min()
            mae = after["High"].max() - entry
            res.append({"pnl": pnl, "mfe": mfe, "mae": mae})

        if not res:
            print(f"  {n_bars:>3} {0:>7}")
            continue

        rr = pd.DataFrame(res)
        nn = len(rr)
        ww = rr[rr["pnl"] > 0]
        ll = rr[rr["pnl"] <= 0]
        wwr = len(ww) / nn * 100
        ppf = ww["pnl"].sum() / abs(ll["pnl"].sum()) if len(ll) > 0 and ll["pnl"].sum() != 0 else float("inf")
        print(f"  {n_bars:>3} {nn:>7} {nn/n_days*100:>5.1f}% {wwr:>5.1f}% {ppf:>6.2f} {rr['pnl'].mean():>+7.1f} "
              f"{rr['pnl'].median():>+7.1f} {rr['mfe'].mean():>6.0f} {rr['mae'].mean():>6.0f}")

    return r


def main():
    print("H052 補充探索：5 分 K 連三紅/綠 + 1 分 K 連 7 黑")
    print("=" * 72)

    # Load 1m data
    print("\nLoading day-session 1m data...")
    df_1m = load_day_session_1m()
    n_days = len(set(df_1m.index.date))
    print(f"Loaded {len(df_1m):,} bars, {n_days} trading days")

    # Build 5m data
    df_5m = build_5m(df_1m)
    print(f"5m bars: {len(df_5m):,}")

    # ── Part A: 5 分 K 連三紅/綠 ──
    print("\n" + "=" * 72)
    print("Part A: 5 分 K 前 3 根連續收紅/收綠")
    print("=" * 72)

    # N=3 on 5m = 15 minutes (08:45~08:59)
    for direction, r in analyze_consecutive(df_5m, 3, "5mK"):
        pass

    # Also test N=2 on 5m (10 minutes)
    print("\n  --- 也測試 5mK N=2（10 分鐘）---")
    for direction, r in analyze_consecutive(df_5m, 2, "5mK"):
        pass

    # ── Part B: 1 分 K 連 7 黑 ──
    r7 = analyze_7bar_short_detail(df_1m)

    print("\n" + "=" * 72)
    print("Done!")
    print("=" * 72)


if __name__ == "__main__":
    main()

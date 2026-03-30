#!/usr/bin/env python3
"""H050 Phase 0: XQ 發財橘子候選策略快速評估。

批次 1 評估：
  G1 — 開盤五分鐘不回頭（前 5 根 1mK 每根收漲且收最高）
  G3 — 開盤 N 分鐘連續收紅（前 N 根 1mK 都 close > open）
  A1 — SuperTrend（ATR 通道趨勢跟隨）
  C1 — VSA 無供應（窄幅低量回檔 = 賣壓枯竭）
  E1 — CHOP 斬波指標（盤整 vs 趨勢濾網）

Usage:
    uv run python research/active/H050-xq-eddie-pricevol-candidates/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H050-xq-eddie-pricevol-candidates/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


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


def evaluate_g1(df):
    """G1: 開盤五分鐘不回頭。

    條件：前 5 根 1mK（08:45~08:49）每根都：
    - 收漲（Close > Open）
    - 收最高（Close == High）

    測量：信號出現後（08:50 起）到收盤的報酬分佈。
    """
    print("\n" + "=" * 72)
    print("G1: 開盤五分鐘不回頭")
    print("=" * 72)

    daily = df.groupby(df.index.date)
    results = []

    for date, day in daily:
        bars = day.head(5)
        if len(bars) < 5:
            continue

        # 每根都收漲且收最高
        all_up = all(bars["Close"] > bars["Open"])
        all_high = all(bars["Close"] == bars["High"])

        if all_up and all_high:
            day_open = day["Open"].iloc[0]
            day_close = day["Close"].iloc[-1]
            day_high = day["High"].max()
            day_low = day["Low"].min()

            # 08:50 起的報酬
            after = day.iloc[5:]  # bars after first 5
            if len(after) > 0:
                entry = after["Open"].iloc[0]  # 08:50 open
                exit_close = day["Close"].iloc[-1]  # 13:45 close
                pnl = exit_close - entry
                max_fav = after["High"].max() - entry
                max_adv = entry - after["Low"].min()
                results.append({
                    "date": date,
                    "weekday": pd.Timestamp(date).day_name()[:3],
                    "entry": entry,
                    "exit": exit_close,
                    "pnl": pnl,
                    "mfe": max_fav,
                    "mae": max_adv,
                    "day_range": day_high - day_low,
                })

    n_days = len(set(df.index.date))
    n_signal = len(results)
    print(f"  交易日: {n_days}, 信號日: {n_signal} ({n_signal/n_days*100:.1f}%)")

    if n_signal == 0:
        print("  無信號！")
        return

    r = pd.DataFrame(results)
    wins = r[r["pnl"] > 0]
    losses = r[r["pnl"] < 0]
    wr = len(wins) / n_signal * 100
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
    print(f"  勝率: {wr:.1f}% (N={n_signal})")
    print(f"  PF: {pf:.2f}")
    print(f"  平均 PnL: {r['pnl'].mean():+.1f}pt")
    print(f"  平均 MFE: {r['mfe'].mean():.0f}pt, 平均 MAE: {r['mae'].mean():.0f}pt")
    print(f"  MFE/MAE: {r['mfe'].mean()/r['mae'].mean():.2f}")

    # Relax condition: Close > Open only (not necessarily Close == High)
    print("\n  --- 放寬：只要 5 根都收漲（不要求收最高）---")
    results_relaxed = []
    for date, day in daily:
        bars = day.head(5)
        if len(bars) < 5:
            continue
        if all(bars["Close"] > bars["Open"]):
            after = day.iloc[5:]
            if len(after) > 0:
                entry = after["Open"].iloc[0]
                exit_close = day["Close"].iloc[-1]
                pnl = exit_close - entry
                mfe = after["High"].max() - entry
                mae = entry - after["Low"].min()
                results_relaxed.append({"date": date, "pnl": pnl, "mfe": mfe, "mae": mae})

    r2 = pd.DataFrame(results_relaxed)
    n2 = len(r2)
    if n2 > 0:
        w2 = r2[r2["pnl"] > 0]
        l2 = r2[r2["pnl"] < 0]
        pf2 = w2["pnl"].sum() / abs(l2["pnl"].sum()) if len(l2) > 0 else float("inf")
        print(f"  信號日: {n2} ({n2/n_days*100:.1f}%)")
        print(f"  勝率: {len(w2)/n2*100:.1f}%, PF: {pf2:.2f}, avg PnL: {r2['pnl'].mean():+.1f}pt")

    return r


def evaluate_g3(df):
    """G3: 開盤 N 分鐘連續收紅。

    測試 N = 3, 4, 5, 6, 7, 8, 10 分鐘。
    條件：前 N 根 1mK 都 Close > Open（收紅）。
    """
    print("\n" + "=" * 72)
    print("G3: 開盤 N 分鐘連續收紅")
    print("=" * 72)

    daily = df.groupby(df.index.date)
    n_days = len(set(df.index.date))

    print(f"  交易日: {n_days}")
    print(f"\n  {'N':>3} {'Signal':>7} {'%':>6} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'MFE':>6} {'MAE':>6} {'MFE/MAE':>8}")
    print(f"  {'-'*3} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*8} {'-'*6} {'-'*6} {'-'*8}")

    for n_bars in [3, 4, 5, 6, 7, 8, 10]:
        results = []
        for date, day in daily:
            bars = day.head(n_bars)
            if len(bars) < n_bars:
                continue
            if all(bars["Close"] > bars["Open"]):
                after = day.iloc[n_bars:]
                if len(after) > 0:
                    entry = after["Open"].iloc[0]
                    exit_close = day["Close"].iloc[-1]
                    pnl = exit_close - entry
                    mfe = after["High"].max() - entry
                    mae = entry - after["Low"].min()
                    results.append({"pnl": pnl, "mfe": mfe, "mae": mae})

        if len(results) == 0:
            print(f"  {n_bars:>3} {0:>7}")
            continue

        r = pd.DataFrame(results)
        n = len(r)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        mfe_mae = r["mfe"].mean() / r["mae"].mean() if r["mae"].mean() > 0 else 0
        print(f"  {n_bars:>3} {n:>7} {n/n_days*100:>5.1f}% {wr:>5.1f}% {pf:>6.2f} {r['pnl'].mean():>+7.1f} "
              f"{r['mfe'].mean():>5.0f} {r['mae'].mean():>5.0f} {mfe_mae:>8.2f}")

    # Also test short side: N bars all close < open (收綠)
    print(f"\n  --- 反向：前 N 根都收綠 → 做空 ---")
    print(f"  {'N':>3} {'Signal':>7} {'%':>6} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    print(f"  {'-'*3} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*8}")

    for n_bars in [3, 4, 5, 6, 7, 8, 10]:
        results = []
        for date, day in daily:
            bars = day.head(n_bars)
            if len(bars) < n_bars:
                continue
            if all(bars["Close"] < bars["Open"]):
                after = day.iloc[n_bars:]
                if len(after) > 0:
                    entry = after["Open"].iloc[0]
                    exit_close = day["Close"].iloc[-1]
                    pnl = entry - exit_close  # short
                    results.append({"pnl": pnl})

        if len(results) == 0:
            print(f"  {n_bars:>3} {0:>7}")
            continue

        r = pd.DataFrame(results)
        n = len(r)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  {n_bars:>3} {n:>7} {n/n_days*100:>5.1f}% {wr:>5.1f}% {pf:>6.2f} {r['pnl'].mean():>+7.1f}")


def evaluate_a1_supertrend(df):
    """A1: SuperTrend — ATR 通道趨勢跟隨。

    計算日盤 SuperTrend（period=10, multiplier=3），
    統計信號方向的日內延續性。
    """
    print("\n" + "=" * 72)
    print("A1: SuperTrend (ATR channel trend following)")
    print("=" * 72)

    # Compute ATR
    df["TR"] = np.maximum(
        df["High"] - df["Low"],
        np.maximum(abs(df["High"] - df["Close"].shift(1)),
                   abs(df["Low"] - df["Close"].shift(1)))
    )

    for period, mult in [(10, 3), (10, 2), (7, 3), (14, 2)]:
        atr = df["TR"].rolling(period).mean()
        hl2 = (df["High"] + df["Low"]) / 2
        upper_band = hl2 + mult * atr
        lower_band = hl2 - mult * atr

        # SuperTrend calculation
        st = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)  # 1=up, -1=down

        st.iloc[0] = upper_band.iloc[0]
        direction.iloc[0] = 1

        for i in range(1, len(df)):
            if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
                direction.iloc[i] = 1
            elif df["Close"].iloc[i] < lower_band.iloc[i - 1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i - 1]

            if direction.iloc[i] == 1:
                st.iloc[i] = max(lower_band.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == 1 else lower_band.iloc[i]
            else:
                st.iloc[i] = min(upper_band.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == -1 else upper_band.iloc[i]

        # Measure: at start of each day, what is ST direction? Does it predict day direction?
        daily = df.groupby(df.index.date)
        results = []
        for date, day in daily:
            first_idx = day.index[0]
            if first_idx not in direction.index or pd.isna(direction.loc[first_idx]):
                continue
            st_dir = direction.loc[first_idx]
            day_open = day["Open"].iloc[0]
            day_close = day["Close"].iloc[-1]
            day_pnl = (day_close - day_open) * st_dir  # aligned with ST direction
            results.append({"date": date, "st_dir": st_dir, "pnl": day_pnl})

        if len(results) == 0:
            continue

        r = pd.DataFrame(results)
        n = len(r)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        long_n = len(r[r["st_dir"] == 1])
        short_n = len(r[r["st_dir"] == -1])
        print(f"  Period={period} Mult={mult}: N={n} WR={wr:.1f}% PF={pf:.2f} "
              f"AvgPnL={r['pnl'].mean():+.1f} Long={long_n} Short={short_n}")


def evaluate_e1_chop(df):
    """E1: CHOP 斬波指標 — 盤整 vs 趨勢濾網。

    CHOP = 100 * LOG10(SUM(ATR,n) / (Highest-Lowest)) / LOG10(n)
    > 61.8 = 盤整, < 38.2 = 趨勢

    測試：開盤時的 CHOP 值是否預測當日波動性/趨勢性。
    用前一日的 CHOP 值（避免 lookahead）。
    """
    print("\n" + "=" * 72)
    print("E1: CHOP 斬波指標 (盤整 vs 趨勢濾網)")
    print("=" * 72)

    # Daily OHLC
    daily_ohlc = df.groupby(df.index.date).agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"),
    )
    daily_ohlc.index = pd.to_datetime(daily_ohlc.index)

    # ATR (daily)
    tr = np.maximum(
        daily_ohlc["High"] - daily_ohlc["Low"],
        np.maximum(abs(daily_ohlc["High"] - daily_ohlc["Close"].shift(1)),
                   abs(daily_ohlc["Low"] - daily_ohlc["Close"].shift(1)))
    )

    for period in [14, 10, 20]:
        atr_sum = tr.rolling(period).sum()
        highest = daily_ohlc["High"].rolling(period).max()
        lowest = daily_ohlc["Low"].rolling(period).min()
        hl_range = highest - lowest
        chop = 100 * np.log10(atr_sum / hl_range.replace(0, np.nan)) / np.log10(period)

        # Shift by 1 to avoid lookahead
        chop_prev = chop.shift(1)

        # Day range as proxy for "trend day" vs "chop day"
        daily_range = daily_ohlc["High"] - daily_ohlc["Low"]
        daily_oc = abs(daily_ohlc["Close"] - daily_ohlc["Open"])

        valid = chop_prev.dropna()
        valid = valid[valid.index >= "2021-01-01"]

        # Split into CHOP zones
        choppy = valid[valid > 61.8]
        trending = valid[valid < 38.2]
        middle = valid[(valid >= 38.2) & (valid <= 61.8)]

        print(f"\n  Period={period}:")
        print(f"  Total days: {len(valid)}")
        print(f"  Choppy (>61.8): {len(choppy)} ({len(choppy)/len(valid)*100:.1f}%)")
        print(f"  Middle (38.2-61.8): {len(middle)} ({len(middle)/len(valid)*100:.1f}%)")
        print(f"  Trending (<38.2): {len(trending)} ({len(trending)/len(valid)*100:.1f}%)")

        for label, zone in [("Choppy >61.8", choppy), ("Middle", middle), ("Trending <38.2", trending)]:
            if len(zone) == 0:
                continue
            zone_ranges = daily_range.reindex(zone.index).dropna()
            zone_oc = daily_oc.reindex(zone.index).dropna()
            print(f"    {label}: avg_range={zone_ranges.mean():.0f}pt avg_OC={zone_oc.mean():.0f}pt (N={len(zone_ranges)})")


def main():
    print("Loading day-session 1m data...")
    df = load_day_session()
    df = df[df.index >= "2021-01-01"]
    print(f"  {len(df):,} bars, {len(set(df.index.date))} days")

    evaluate_g1(df)
    evaluate_g3(df)
    evaluate_a1_supertrend(df)
    evaluate_e1_chop(df)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

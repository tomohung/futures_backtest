#!/usr/bin/env python3
"""H055 Phase 1: STARC 下軌觸及後反轉做多 — 分佈探索研究。

分析項目：
1. 確認 STARC 下軌觸及的日期與市場背景
2. IS/OOS 分年度反轉率與報酬
3. 參數敏感度（SMA 6/10, ATR 10/14/15, 倍數 1.5/2/2.5）
4. 確認上軌觸及無反轉效果（排除雙向對稱性）
5. 與 S003 Exhaustion 的信號日重疊率
6. 次日盤中的最佳進場時機（開盤做多 vs 等回檔）

Usage:
    uv run python research/active/H055-starc-lower-reversal/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"


def load_daily_ohlcv():
    """從 1m K 棒合成日線 OHLCV。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                CAST(timestamp AS DATE) AS trade_date,
                FIRST(open) AS open,
                MAX(high) AS high,
                MIN(low) AS low,
                LAST(close) AS close,
                SUM(volume) AS volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY CAST(timestamp AS DATE)
            ORDER BY trade_date
        """).df()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def load_intraday_1m():
    """載入日盤 1m OHLCV。"""
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


def compute_starc(daily, sma_period, atr_period, mult):
    """計算 STARC bands。"""
    tr = np.maximum(
        daily["High"] - daily["Low"],
        np.maximum(
            abs(daily["High"] - daily["Close"].shift(1)),
            abs(daily["Low"] - daily["Close"].shift(1))
        )
    )
    sma = daily["Close"].rolling(sma_period).mean()
    atr = tr.rolling(atr_period).mean()
    upper = sma + mult * atr
    lower = sma - mult * atr
    return upper, lower, atr


def load_s003_signals():
    """載入 S003 Exhaustion 做多信號日（Bearish Exhaustion → Long）。

    S003 做多條件（概略版）：
    - 30m SMA(20) 下降
    - BB%B(20, open, 2σ) < 0
    - 夜盤 low < 前 2 日 lowest low
    - ORB 向上突破

    這裡用簡化版：日線連跌 + 大跌後反彈，作為概略代理。
    實際用 BB%B < 0 需要 30m 資料，這裡改用日線 STARC 下軌觸及當作 proxy 比較。
    """
    # 直接從策略回測結果讀取（如果有的話），否則用概略版
    # 這裡採用概略估計：3 日 RSI < 20 作為 proxy
    return None  # 在 analyze_s003_overlap 中直接計算


# ============================================================
# 分析 1: STARC 下軌觸及的基本統計
# ============================================================
def analyze_basic_stats(daily):
    """基本統計：觸及頻率、反轉率、平均報酬。"""
    print("\n" + "=" * 72)
    print("1. STARC 下軌觸及 — 基本統計")
    print("=" * 72)

    upper, lower, atr = compute_starc(daily, 6, 15, 2)

    # 用前一日的 band（避免 lookahead）
    lower_prev = lower.shift(1)
    upper_prev = upper.shift(1)

    touch_lower = daily[daily["Close"] < lower_prev]
    touch_upper = daily[daily["Close"] > upper_prev]

    # 次日報酬
    next_ret = daily["Close"].shift(-1) - daily["Close"]
    next_open_ret = daily["Open"].shift(-1) - daily["Close"]  # gap

    print(f"\n  基準參數: SMA(6) / ATR(15) / ×2")
    print(f"  資料範圍: {daily.index.min().date()} ~ {daily.index.max().date()}")
    print(f"  總交易日: {len(daily)}")

    # 下軌
    n_lower = len(touch_lower)
    if n_lower > 0:
        ret_lower = next_ret.reindex(touch_lower.index).dropna()
        reversal_pct = (ret_lower > 0).sum() / len(ret_lower) * 100
        print(f"\n  下軌觸及: N={n_lower} ({n_lower/len(daily)*100:.1f}%)")
        print(f"    次日反轉率（收漲）: {reversal_pct:.1f}%")
        print(f"    次日平均 PnL: {ret_lower.mean():+.1f}pt")
        print(f"    次日中位數 PnL: {ret_lower.median():+.1f}pt")
        print(f"    次日最大獲利: {ret_lower.max():+.0f}pt")
        print(f"    次日最大虧損: {ret_lower.min():+.0f}pt")
        print(f"    次日標準差: {ret_lower.std():.0f}pt")

        # 列出所有觸及日期
        print(f"\n    觸及日期列表:")
        for date in touch_lower.index:
            ret = next_ret.get(date, np.nan)
            marker = "✓" if ret > 0 else "✗"
            print(f"      {date.strftime('%Y-%m-%d')} Close={daily.loc[date, 'Close']:,.0f} "
                  f"Lower={lower_prev.loc[date]:,.0f} 次日PnL={ret:+.0f} {marker}")

    # 上軌
    n_upper = len(touch_upper)
    if n_upper > 0:
        ret_upper = next_ret.reindex(touch_upper.index).dropna()
        reversal_pct_upper = (ret_upper < 0).sum() / len(ret_upper) * 100
        print(f"\n  上軌觸及: N={n_upper} ({n_upper/len(daily)*100:.1f}%)")
        print(f"    次日反轉率（收跌）: {reversal_pct_upper:.1f}%")
        print(f"    次日平均 PnL: {ret_upper.mean():+.1f}pt（正=繼續漲）")


# ============================================================
# 分析 2: IS/OOS 分年度
# ============================================================
def analyze_is_oos(daily):
    """IS (2021-2024) vs OOS (2025-2026) 分年度績效。"""
    print("\n" + "=" * 72)
    print("2. IS/OOS 分年度反轉率與報酬")
    print("=" * 72)

    upper, lower, atr = compute_starc(daily, 6, 15, 2)
    lower_prev = lower.shift(1)
    touch_lower = daily[daily["Close"] < lower_prev]
    next_ret = daily["Close"].shift(-1) - daily["Close"]

    print(f"\n  {'年度':<6} {'N':>4} {'反轉率%':>8} {'AvgPnL':>8} {'TotalPnL':>10}")
    print(f"  {'-'*40}")

    for year in sorted(touch_lower.index.year.unique()):
        subset = touch_lower[touch_lower.index.year == year]
        n = len(subset)
        ret = next_ret.reindex(subset.index).dropna()
        if len(ret) == 0:
            print(f"  {year:<6} {n:>4}    N/A")
            continue
        reversal = (ret > 0).sum() / len(ret) * 100
        avg = ret.mean()
        total = ret.sum()
        print(f"  {year:<6} {n:>4} {reversal:>7.1f}% {avg:>+7.1f} {total:>+9.0f}")

    # IS/OOS summary
    is_dates = touch_lower[touch_lower.index.year <= 2024]
    oos_dates = touch_lower[touch_lower.index.year >= 2025]
    print(f"\n  --- IS (2021-2024) vs OOS (2025-2026) ---")
    for label, subset in [("IS ", is_dates), ("OOS", oos_dates)]:
        ret = next_ret.reindex(subset.index).dropna()
        n = len(ret)
        if n == 0:
            print(f"  {label}: 0 signals")
            continue
        reversal = (ret > 0).sum() / n * 100
        print(f"  {label}: N={n} 反轉率={reversal:.1f}% AvgPnL={ret.mean():+.1f}pt")


# ============================================================
# 分析 3: 參數敏感度
# ============================================================
def analyze_param_sensitivity(daily):
    """測試不同 SMA/ATR/倍數組合。"""
    print("\n" + "=" * 72)
    print("3. 參數敏感度")
    print("=" * 72)

    next_ret = daily["Close"].shift(-1) - daily["Close"]

    print(f"\n  {'SMA':>4} {'ATR':>4} {'Mult':>5} {'N':>5} {'反轉%':>7} {'AvgPnL':>8} {'Total':>8}")
    print(f"  {'-'*47}")

    for sma_p in [6, 10]:
        for atr_p in [10, 14, 15]:
            for mult in [1.5, 2.0, 2.5]:
                upper, lower, atr = compute_starc(daily, sma_p, atr_p, mult)
                lower_prev = lower.shift(1)
                touch = daily[daily["Close"] < lower_prev]
                n = len(touch)
                if n < 5:
                    print(f"  {sma_p:>4} {atr_p:>4} {mult:>5.1f} {n:>5} — 樣本不足")
                    continue
                ret = next_ret.reindex(touch.index).dropna()
                reversal = (ret > 0).sum() / len(ret) * 100
                print(f"  {sma_p:>4} {atr_p:>4} {mult:>5.1f} {n:>5} {reversal:>6.1f}% "
                      f"{ret.mean():>+7.1f} {ret.sum():>+7.0f}")


# ============================================================
# 分析 4: 上軌觸及（排除雙向對稱性）
# ============================================================
def analyze_upper_band(daily):
    """確認上軌觸及無反轉效果。"""
    print("\n" + "=" * 72)
    print("4. 上軌觸及 — 排除雙向對稱性")
    print("=" * 72)

    next_ret = daily["Close"].shift(-1) - daily["Close"]

    print(f"\n  {'SMA':>4} {'ATR':>4} {'Mult':>5} {'N':>5} {'反轉%':>7} {'AvgPnL':>8}")
    print(f"  {'-'*41}")

    for sma_p, atr_p, mult in [(6, 15, 2), (10, 14, 2), (6, 15, 1.5)]:
        upper, lower, atr = compute_starc(daily, sma_p, atr_p, mult)
        upper_prev = upper.shift(1)
        touch = daily[daily["Close"] > upper_prev]
        n = len(touch)
        if n < 5:
            continue
        ret = next_ret.reindex(touch.index).dropna()
        # 上軌反轉 = 次日收跌
        reversal = (ret < 0).sum() / len(ret) * 100
        print(f"  {sma_p:>4} {atr_p:>4} {mult:>5.1f} {n:>5} {reversal:>6.1f}% "
              f"{ret.mean():>+7.1f}（正=繼續漲）")


# ============================================================
# 分析 5: 與 S003 Exhaustion 的信號日重疊率
# ============================================================
def analyze_s003_overlap(daily):
    """用概略代理比較 STARC 下軌觸及與 S003 的重疊。

    S003 Bearish Exhaustion → Long 需要：
    - 30m SMA 下降 + BB%B < 0 + 夜盤破低 + ORB 突破
    這裡用簡化代理：近 3 日連跌（Close < Close[-3]）+ ATR 放大
    """
    print("\n" + "=" * 72)
    print("5. 與 S003 Exhaustion 信號日重疊率（概略估計）")
    print("=" * 72)

    upper, lower, atr = compute_starc(daily, 6, 15, 2)
    lower_prev = lower.shift(1)
    starc_dates = set(daily[daily["Close"] < lower_prev].index)

    # S003 做多代理：3 日跌幅 > ATR + 當日跌幅大
    daily_ret_3d = daily["Close"] - daily["Close"].shift(3)
    atr_val = atr.shift(1)
    s003_proxy = daily[(daily_ret_3d < -atr_val) & (daily["Close"] < daily["Open"])]
    s003_dates = set(s003_proxy.index)

    overlap = starc_dates & s003_dates
    print(f"\n  STARC 下軌觸及: {len(starc_dates)} 天")
    print(f"  S003 Proxy（3日跌>ATR+當日收跌）: {len(s003_dates)} 天")
    print(f"  重疊: {len(overlap)} 天")
    if len(starc_dates) > 0:
        print(f"  重疊率（STARC 視角）: {len(overlap)/len(starc_dates)*100:.1f}%")
    if len(s003_dates) > 0:
        print(f"  重疊率（S003 視角）: {len(overlap)/len(s003_dates)*100:.1f}%")

    if overlap:
        print(f"\n  重疊日期:")
        for d in sorted(overlap):
            print(f"    {d.strftime('%Y-%m-%d')}")


# ============================================================
# 分析 6: 次日盤中最佳進場時機
# ============================================================
def analyze_entry_timing(daily, intraday):
    """次日盤中的最佳進場時機。"""
    print("\n" + "=" * 72)
    print("6. 次日盤中最佳進場時機")
    print("=" * 72)

    upper, lower, atr = compute_starc(daily, 6, 15, 2)
    lower_prev = lower.shift(1)
    touch_dates = daily[daily["Close"] < lower_prev].index
    # 取次日日期
    all_dates = daily.index
    next_dates = []
    for d in touch_dates:
        pos = all_dates.get_loc(d)
        if pos + 1 < len(all_dates):
            next_dates.append(all_dates[pos + 1])

    if not next_dates:
        print("  No next-day data")
        return

    print(f"\n  觸及下軌後次日（N={len(next_dates)}）的盤中表現:")

    # 測試不同進場時點
    results = {}
    for entry_time_str, entry_label in [
        ("08:45", "開盤 08:45"),
        ("09:00", "09:00"),
        ("09:15", "09:15"),
        ("09:30", "09:30"),
        ("10:00", "10:00"),
    ]:
        entry_time = pd.Timestamp(entry_time_str).time()
        pnls = []

        for next_date in next_dates:
            day_data = intraday[intraday.index.date == next_date.date()]
            if day_data.empty:
                continue

            # 找進場 bar
            entry_bars = day_data[day_data.index.time >= entry_time]
            if entry_bars.empty:
                continue
            entry_price = float(entry_bars.iloc[0]["Open"])

            # 收盤出場
            exit_price = float(day_data.iloc[-1]["Close"])
            pnl = exit_price - entry_price
            pnls.append(pnl)

        if not pnls:
            continue
        pnls = pd.Series(pnls)
        n = len(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        wr = len(wins) / n * 100
        pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
        results[entry_label] = {"n": n, "wr": wr, "pf": pf, "avg": pnls.mean(), "total": pnls.sum()}

    print(f"\n  {'進場時點':<12} {'N':>4} {'WR%':>6} {'PF':>6} {'AvgPnL':>8} {'TotalPnL':>10}")
    print(f"  {'-'*50}")
    for label, r in results.items():
        print(f"  {label:<12} {r['n']:>4} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
              f"{r['avg']:>+7.1f} {r['total']:>+9.0f}")

    # 盤中回檔深度分析
    print(f"\n  --- 次日開盤後的回檔深度 ---")
    drawdowns = []
    for next_date in next_dates:
        day_data = intraday[intraday.index.date == next_date.date()]
        if day_data.empty:
            continue
        day_open = float(day_data.iloc[0]["Open"])
        day_low = float(day_data["Low"].min())
        day_close = float(day_data.iloc[-1]["Close"])
        drawdown = day_open - day_low  # 從開盤到日內最低
        drawdowns.append({
            "date": next_date,
            "open": day_open,
            "low": day_low,
            "close": day_close,
            "drawdown": drawdown,
            "pnl_from_open": day_close - day_open,
        })

    if drawdowns:
        dd_df = pd.DataFrame(drawdowns)
        print(f"    平均開盤後回檔: {dd_df['drawdown'].mean():.0f}pt")
        print(f"    中位數回檔: {dd_df['drawdown'].median():.0f}pt")
        print(f"    最大回檔: {dd_df['drawdown'].max():.0f}pt")
        # 等回檔 N 點再進場
        for wait_pts in [30, 50, 80, 100]:
            triggered = dd_df[dd_df["drawdown"] >= wait_pts]
            if len(triggered) < 3:
                print(f"    等回檔 {wait_pts}pt: N={len(triggered)} — 樣本不足")
                continue
            # 假設回檔到 open - wait_pts 進場，收盤出場
            pnls = triggered["close"] - (triggered["open"] - wait_pts)
            wins = pnls[pnls > 0]
            losses = pnls[pnls < 0]
            wr = len(wins) / len(pnls) * 100
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
            print(f"    等回檔 {wait_pts}pt: N={len(triggered)} WR={wr:.1f}% "
                  f"PF={pf:.2f} AvgPnL={pnls.mean():+.1f}")


def main():
    print("=" * 72)
    print("H055 Phase 1: STARC 下軌觸及後反轉做多 — 分佈探索研究")
    print("=" * 72)

    print("\nLoading daily OHLCV...")
    daily = load_daily_ohlcv()
    daily = daily[daily.index >= "2021-01-01"]
    print(f"  {len(daily)} days ({daily.index.min().date()} ~ {daily.index.max().date()})")

    print("\nLoading intraday 1m data...")
    intraday = load_intraday_1m()
    intraday = intraday[intraday.index >= "2021-01-01"]
    print(f"  {len(intraday):,} bars")

    analyze_basic_stats(daily)
    analyze_is_oos(daily)
    analyze_param_sensitivity(daily)
    analyze_upper_band(daily)
    analyze_s003_overlap(daily)
    analyze_entry_timing(daily, intraday)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

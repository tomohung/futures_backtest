"""
H062 Volume Spike Breakout — Phase 2 深度探索

測試方向：
1. 時段差異（早盤 vs 中盤 vs 尾盤）
2. 最低目標價濾網（振幅佔進場價百分比）
3. 固定點數目標（突破後的反轉掃停損現象）
4. 不同目標倍率（0.5x / 0.618x / 1.0x）+ 不同停損倍率
5. KD 動能濾網
"""

import argparse
from datetime import time as dt_time

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
LOOKBACK = 20
COST = 2


def load_data():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:46:00'
              AND timestamp::TIME <= '13:44:00'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    return df.reset_index(drop=True)


def compute_stoch_k(day_closes, period=9):
    """計算 Stochastic %K（逐 bar）"""
    n = len(day_closes)
    k = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = day_closes[i - period + 1:i + 1]
        lo = window.min()
        hi = window.max()
        if hi > lo:
            k[i] = (day_closes[i] - lo) / (hi - lo) * 100
    return k


def precompute(df, multiplier=3):
    df = df.copy()
    df["vol_ma"] = df.groupby("date")["volume"].transform(
        lambda x: x.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)
    )
    df["is_spike"] = (
        (df["time"] >= dt_time(9, 10))
        & (df["time"] <= dt_time(13, 25))
        & df["vol_ma"].notna()
        & (df["volume"] >= df["vol_ma"] * multiplier)
        & ((df["high"] - df["low"]) >= 3)
    )
    # 預計算 stoch %K
    df["stoch_k"] = df.groupby("date")["close"].transform(
        lambda x: compute_stoch_k(x.values, period=9)
    )
    return df


def run_backtest(df, tp_mult=1.0, sl_mult=1.0, fixed_tp=0, fixed_sl=0,
                 min_range_pct=0, max_signals=0,
                 time_start=dt_time(9, 11), time_end=dt_time(13, 30),
                 kd_long_min=0, kd_short_max=100,
                 min_range_pts=0):
    """
    tp_mult / sl_mult: 凸量 K 振幅的倍率
    fixed_tp / fixed_sl: 固定點數（> 0 時覆蓋 mult）
    min_range_pct: 最低振幅佔進場價的百分比（如 0.1 = 0.1%）
    min_range_pts: 最低振幅點數
    kd_long_min: 做多時 %K 最低要求
    kd_short_max: 做空時 %K 最高要求
    """
    all_trades = []

    for date, idx_range in df.groupby("date").groups.items():
        day_idx = sorted(idx_range)
        n = len(day_idx)
        if n < LOOKBACK + 5:
            continue

        day_times = df.loc[day_idx, "time"].values
        day_opens = df.loc[day_idx, "open"].values.astype(float)
        day_highs = df.loc[day_idx, "high"].values.astype(float)
        day_lows = df.loc[day_idx, "low"].values.astype(float)
        day_closes = df.loc[day_idx, "close"].values.astype(float)
        day_spikes = df.loc[day_idx, "is_spike"].values
        day_kd = df.loc[day_idx, "stoch_k"].values

        spike_list = []
        for i in range(n):
            if day_spikes[i]:
                sp_range = day_highs[i] - day_lows[i]
                spike_list.append((i, day_highs[i], day_lows[i], sp_range, day_times[i]))

        if not spike_list:
            continue

        position = None
        daily_signals = 0
        active_spikes = []

        for i in range(n):
            t = day_times[i]
            bar_high = day_highs[i]
            bar_low = day_lows[i]
            bar_close = day_closes[i]
            bar_kd = day_kd[i]

            while spike_list and spike_list[0][0] == i:
                active_spikes.append(spike_list.pop(0))

            if position and t >= dt_time(13, 44):
                pnl = (bar_close - position["entry"]) * (1 if position["dir"] == "long" else -1)
                pnl -= COST
                all_trades.append({
                    "date": date, "dir": position["dir"],
                    "spike_time": position["spike_time"],
                    "entry_time": position["entry_time"],
                    "entry_price": position["entry"],
                    "exit_time": t, "exit_price": bar_close,
                    "exit_reason": "timeout", "pnl_pts": pnl,
                    "spike_range": position["spike_range"],
                })
                position = None
                continue

            if position:
                if position["dir"] == "long":
                    if bar_low <= position["sl"]:
                        pnl = position["sl"] - position["entry"] - COST
                        exit_p = position["sl"]
                        reason = "sl"
                    elif bar_high >= position["tp"]:
                        pnl = position["tp"] - position["entry"] - COST
                        exit_p = position["tp"]
                        reason = "tp"
                    else:
                        continue
                else:
                    if bar_high >= position["sl"]:
                        pnl = position["entry"] - position["sl"] - COST
                        exit_p = position["sl"]
                        reason = "sl"
                    elif bar_low <= position["tp"]:
                        pnl = position["entry"] - position["tp"] - COST
                        exit_p = position["tp"]
                        reason = "tp"
                    else:
                        continue

                all_trades.append({
                    "date": date, "dir": position["dir"],
                    "spike_time": position["spike_time"],
                    "entry_time": position["entry_time"],
                    "entry_price": position["entry"],
                    "exit_time": t, "exit_price": exit_p,
                    "exit_reason": reason, "pnl_pts": pnl,
                    "spike_range": position["spike_range"],
                })
                position = None
                continue

            if t < time_start or t >= time_end:
                continue
            if max_signals > 0 and daily_signals >= max_signals:
                continue
            if not active_spikes:
                continue

            for sp_idx in range(len(active_spikes) - 1, -1, -1):
                _, sp_high, sp_low, sp_range, sp_time = active_spikes[sp_idx]

                if min_range_pts > 0 and sp_range < min_range_pts:
                    continue
                if min_range_pct > 0 and (sp_range / bar_close * 100) < min_range_pct:
                    continue

                tp_dist = fixed_tp if fixed_tp > 0 else sp_range * tp_mult
                sl_dist = fixed_sl if fixed_sl > 0 else sp_range * sl_mult

                if bar_close > sp_high:
                    if kd_long_min > 0 and (np.isnan(bar_kd) or bar_kd < kd_long_min):
                        continue
                    entry_price = bar_close
                    position = {
                        "dir": "long", "entry": entry_price,
                        "tp": entry_price + tp_dist,
                        "sl": entry_price - sl_dist,
                        "spike_time": sp_time, "entry_time": t,
                        "spike_range": sp_range,
                    }
                    daily_signals += 1
                    active_spikes.clear()
                    break
                elif bar_close < sp_low:
                    if kd_short_max < 100 and (np.isnan(bar_kd) or bar_kd > kd_short_max):
                        continue
                    entry_price = bar_close
                    position = {
                        "dir": "short", "entry": entry_price,
                        "tp": entry_price - tp_dist,
                        "sl": entry_price + sl_dist,
                        "spike_time": sp_time, "entry_time": t,
                        "spike_range": sp_range,
                    }
                    daily_signals += 1
                    active_spikes.clear()
                    break

    return pd.DataFrame(all_trades)


def stats(trades, label=""):
    if trades.empty:
        print(f"  {label}: 無交易")
        return
    n = len(trades)
    w = (trades["pnl_pts"] > 0).sum()
    wr = w / n * 100
    avg = trades["pnl_pts"].mean()
    total = trades["pnl_pts"].sum()
    ws = trades[trades["pnl_pts"] > 0]["pnl_pts"].sum()
    ls = abs(trades[trades["pnl_pts"] <= 0]["pnl_pts"].sum())
    pf = ws / ls if ls > 0 else float("inf")
    pct = trades["pnl_pts"] / trades["entry_price"] * 100
    sharpe = pct.mean() / pct.std() * np.sqrt(252) if pct.std() > 0 else 0
    print(f"  {label:30s} N={n:>5} WR={wr:>5.1f}% PF={pf:>5.2f} Avg={avg:>+6.1f} Total={total:>+8.0f} Sharpe={sharpe:>+5.2f}")


def main():
    print("Loading data...")
    df = load_data()
    df = precompute(df, multiplier=3)
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} days\n")

    # ============================================================
    print("=" * 70)
    print("  TEST 1: 時段差異")
    print("=" * 70)
    for seg, (s, e) in [
        ("09:10-10:30", (dt_time(9, 11), dt_time(10, 30))),
        ("10:30-12:00", (dt_time(10, 30), dt_time(12, 0))),
        ("12:00-13:30", (dt_time(12, 0), dt_time(13, 30))),
        ("09:10-10:30 only", (dt_time(9, 11), dt_time(10, 30))),
    ]:
        t = run_backtest(df, time_start=s, time_end=e)
        stats(t, seg)

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 2: 最低振幅濾網（點數 & 百分比）")
    print("=" * 70)
    print("\n  --- 最低振幅（點數）---")
    for min_pts in [0, 10, 15, 20, 30, 40, 50]:
        t = run_backtest(df, min_range_pts=min_pts)
        stats(t, f"min_range >= {min_pts} pts")

    print("\n  --- 最低振幅佔進場價百分比 ---")
    for pct in [0, 0.05, 0.1, 0.15, 0.2]:
        t = run_backtest(df, min_range_pct=pct)
        stats(t, f"min_range >= {pct}%")

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 3: 固定點數目標（TP=SL）")
    print("=" * 70)
    for pts in [10, 15, 20, 30, 40, 50, 60, 80, 100]:
        t = run_backtest(df, fixed_tp=pts, fixed_sl=pts)
        stats(t, f"Fixed TP=SL={pts} pts")

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 4: 固定點數 + 早盤 only")
    print("=" * 70)
    for pts in [10, 15, 20, 30, 40, 50, 60, 80, 100]:
        t = run_backtest(df, fixed_tp=pts, fixed_sl=pts,
                         time_start=dt_time(9, 11), time_end=dt_time(10, 30))
        stats(t, f"早盤 Fixed TP=SL={pts}")

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 5: 目標倍率 x 停損倍率")
    print("=" * 70)
    for tp_m in [0.5, 0.618, 0.8, 1.0]:
        for sl_m in [0.5, 0.618, 0.8, 1.0, 1.5]:
            t = run_backtest(df, tp_mult=tp_m, sl_mult=sl_m)
            stats(t, f"TP={tp_m}x SL={sl_m}x")
        print()

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 6: KD 動能濾網")
    print("=" * 70)
    print("\n  --- 做多 %K 最低要求 ---")
    for kd_min in [0, 30, 40, 50, 60, 70, 80]:
        t = run_backtest(df, kd_long_min=kd_min, kd_short_max=100)
        stats(t, f"Long only KD>={kd_min}")

    print("\n  --- 做空 %K 最高要求 ---")
    for kd_max in [100, 70, 60, 50, 40, 30, 20]:
        t = run_backtest(df, kd_long_min=0, kd_short_max=kd_max)
        stats(t, f"Short only KD<={kd_max}")

    print("\n  --- 雙向 KD 濾網 ---")
    for kd_val in [0, 30, 40, 50, 60, 70]:
        t = run_backtest(df, kd_long_min=kd_val, kd_short_max=100 - kd_val)
        stats(t, f"Long KD>={kd_val} Short KD<={100-kd_val}")

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 8: Weekday 差異")
    print("=" * 70)
    weekday_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    t_all = run_backtest(df)
    if not t_all.empty:
        t_all["weekday"] = t_all["date"].apply(lambda d: d.weekday())
        for wd in range(5):
            wd_trades = t_all[t_all["weekday"] == wd]
            stats(wd_trades, weekday_names[wd])

    # ============================================================
    print(f"\n{'=' * 70}")
    print("  TEST 7: 組合測試（早盤 + KD + 最低振幅）")
    print("=" * 70)
    for kd_val in [0, 50, 60, 70]:
        for min_pts in [0, 15, 20, 30]:
            t = run_backtest(df,
                             time_start=dt_time(9, 11), time_end=dt_time(10, 30),
                             kd_long_min=kd_val, kd_short_max=100 - kd_val if kd_val > 0 else 100,
                             min_range_pts=min_pts,
                             max_signals=2)
            stats(t, f"早盤 KD{kd_val} min{min_pts}pts max2")


if __name__ == "__main__":
    main()

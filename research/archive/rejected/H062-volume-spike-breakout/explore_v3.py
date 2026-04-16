"""
H062 Volume Spike Breakout — V3 探索

改用掛單邏輯 + 凸量 K 方向濾網：
1. 掛單進場：凸量 K 出現後，掛限價單在高/低點，bar 觸及即成交
2. 方向濾網：凸量 K 本身的方向性
   - 簡單版：close > open = 陽線，只做多
   - RS 版：body_position = (close - low) / (high - low)
     - RS > 0.5 偏多，只做多突破
     - RS < 0.5 偏空，只做空突破
   - Body ratio: body / range，越大表示方向越明確
"""

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
    return df


def run_backtest(df, tp_mult=1.0, sl_mult=1.0, max_signals=0,
                 time_start=dt_time(9, 11), time_end=dt_time(13, 30),
                 entry_mode="limit",  # "limit" = 掛單在高/低點, "close" = 收盤價
                 dir_filter="none",   # "none", "candle", "rs_05", "rs_06", "rs_07"
                 min_range_pts=0,
                 min_body_ratio=0):   # body/range 最低比率
    """
    entry_mode:
      - "limit": 掛單在凸量K高/低點，bar 觸及即成交
      - "close": 收盤突破後用收盤價進場
    dir_filter:
      - "none": 多空都做
      - "candle": 陽線只做多、陰線只做空
      - "rs_05": RS > 0.5 只做多、RS < 0.5 只做空
      - "rs_06": RS > 0.6 只做多、RS < 0.4 只做空
      - "rs_07": RS > 0.7 只做多、RS < 0.3 只做空
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

        spike_list = []
        for i in range(n):
            if day_spikes[i]:
                sp_range = day_highs[i] - day_lows[i]
                if sp_range < max(3, min_range_pts):
                    continue
                sp_body = abs(day_closes[i] - day_opens[i])
                body_ratio = sp_body / sp_range if sp_range > 0 else 0
                if min_body_ratio > 0 and body_ratio < min_body_ratio:
                    continue
                rs = (day_closes[i] - day_lows[i]) / sp_range if sp_range > 0 else 0.5
                is_bullish = day_closes[i] >= day_opens[i]
                spike_list.append((i, day_highs[i], day_lows[i], sp_range,
                                   day_times[i], is_bullish, rs, body_ratio))

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
                    "exit_reason": "timeout", "pnl_pts": pnl,
                })
                position = None
                continue

            if position:
                if position["dir"] == "long":
                    if bar_low <= position["sl"]:
                        pnl = position["sl"] - position["entry"] - COST
                        reason = "sl"
                    elif bar_high >= position["tp"]:
                        pnl = position["tp"] - position["entry"] - COST
                        reason = "tp"
                    else:
                        continue
                else:
                    if bar_high >= position["sl"]:
                        pnl = position["entry"] - position["sl"] - COST
                        reason = "sl"
                    elif bar_low <= position["tp"]:
                        pnl = position["entry"] - position["tp"] - COST
                        reason = "tp"
                    else:
                        continue
                all_trades.append({
                    "date": date, "dir": position["dir"],
                    "spike_time": position["spike_time"],
                    "entry_time": position["entry_time"],
                    "entry_price": position["entry"],
                    "exit_reason": reason, "pnl_pts": pnl,
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
                _, sp_high, sp_low, sp_range, sp_time, is_bull, rs, br = active_spikes[sp_idx]

                tp_dist = sp_range * tp_mult
                sl_dist = sp_range * sl_mult

                # 方向濾網
                def allowed_long():
                    if dir_filter == "none":
                        return True
                    if dir_filter == "candle":
                        return is_bull
                    if dir_filter == "rs_05":
                        return rs > 0.5
                    if dir_filter == "rs_06":
                        return rs > 0.6
                    if dir_filter == "rs_07":
                        return rs > 0.7
                    return True

                def allowed_short():
                    if dir_filter == "none":
                        return True
                    if dir_filter == "candle":
                        return not is_bull
                    if dir_filter == "rs_05":
                        return rs < 0.5
                    if dir_filter == "rs_06":
                        return rs < 0.4
                    if dir_filter == "rs_07":
                        return rs < 0.3
                    return True

                entered = False

                if entry_mode == "limit":
                    if bar_high >= sp_high and allowed_long():
                        entry_price = sp_high
                        position = {
                            "dir": "long", "entry": entry_price,
                            "tp": entry_price + tp_dist,
                            "sl": entry_price - sl_dist,
                            "spike_time": sp_time, "entry_time": t,
                        }
                        entered = True
                    elif bar_low <= sp_low and allowed_short():
                        entry_price = sp_low
                        position = {
                            "dir": "short", "entry": entry_price,
                            "tp": entry_price - tp_dist,
                            "sl": entry_price + sl_dist,
                            "spike_time": sp_time, "entry_time": t,
                        }
                        entered = True
                else:  # close mode
                    if bar_close > sp_high and allowed_long():
                        entry_price = bar_close
                        position = {
                            "dir": "long", "entry": entry_price,
                            "tp": entry_price + tp_dist,
                            "sl": entry_price - sl_dist,
                            "spike_time": sp_time, "entry_time": t,
                        }
                        entered = True
                    elif bar_close < sp_low and allowed_short():
                        entry_price = bar_close
                        position = {
                            "dir": "short", "entry": entry_price,
                            "tp": entry_price - tp_dist,
                            "sl": entry_price + sl_dist,
                            "spike_time": sp_time, "entry_time": t,
                        }
                        entered = True

                if entered:
                    daily_signals += 1
                    active_spikes.clear()
                    break

    return pd.DataFrame(all_trades)


def stats(trades, label=""):
    if trades.empty:
        print(f"  {label:40s} N=    0  --")
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
    print(f"  {label:40s} N={n:>5} WR={wr:>5.1f}% PF={pf:>5.2f} Avg={avg:>+6.1f} Total={total:>+8.0f} Sh={sharpe:>+5.2f}")


def yearly(trades, label=""):
    if trades.empty:
        return
    t = trades.copy()
    t["year"] = t["date"].apply(lambda d: d.year)
    parts = []
    for year, yt in t.groupby("year"):
        n = len(yt)
        total = yt["pnl_pts"].sum()
        parts.append(f"{year}:{total:+.0f}")
    print(f"    {label} yearly: {', '.join(parts)}")


def main():
    print("Loading data...")
    df = load_data()
    df = precompute(df, multiplier=3)
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} days\n")

    # ============================================================
    print("=" * 75)
    print("  A. 掛單 vs 收盤進場（基準比較）")
    print("=" * 75)
    t_limit = run_backtest(df, entry_mode="limit")
    t_close = run_backtest(df, entry_mode="close")
    stats(t_limit, "Limit order (掛單在高/低點)")
    stats(t_close, "Close confirm (收盤價進場)")

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  B. 掛單 + 方向濾網")
    print("=" * 75)
    for filt in ["none", "candle", "rs_05", "rs_06", "rs_07"]:
        t = run_backtest(df, entry_mode="limit", dir_filter=filt)
        stats(t, f"Limit + dir={filt}")

    # 反向：逆凸量K方向做
    print("\n  --- 反向測試（逆凸量K方向）---")
    # 自訂反向邏輯：陽線只做空、陰線只做多
    for filt_name, filt in [("anti_candle", "candle"), ("anti_rs05", "rs_05")]:
        # 透過交換 long/short 的 allowed 來達成反向效果
        # 簡單做法：跑原版再看
        pass

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  C. 掛單 + 方向濾網 + 時段")
    print("=" * 75)
    for filt in ["none", "candle", "rs_05", "rs_06"]:
        for seg, (s, e) in [
            ("早盤", (dt_time(9, 11), dt_time(10, 30))),
            ("中盤", (dt_time(10, 30), dt_time(12, 0))),
            ("尾盤", (dt_time(12, 0), dt_time(13, 30))),
        ]:
            t = run_backtest(df, entry_mode="limit", dir_filter=filt,
                             time_start=s, time_end=e)
            stats(t, f"{seg} dir={filt}")
        print()

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  D. 掛單 + 方向濾網 + TP/SL 倍率")
    print("=" * 75)
    for filt in ["candle", "rs_05"]:
        for tp_m in [0.5, 0.618, 0.8, 1.0]:
            for sl_m in [0.5, 0.618, 0.8, 1.0, 1.5]:
                t = run_backtest(df, entry_mode="limit", dir_filter=filt,
                                 tp_mult=tp_m, sl_mult=sl_m)
                stats(t, f"dir={filt} TP={tp_m}x SL={sl_m}x")
            print()

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  E. 掛單 + 方向 + max signals + min range")
    print("=" * 75)
    for filt in ["candle", "rs_05"]:
        for ms in [0, 1, 2, 3]:
            for min_pts in [0, 15, 20, 30]:
                t = run_backtest(df, entry_mode="limit", dir_filter=filt,
                                 max_signals=ms, min_range_pts=min_pts)
                ms_label = "all" if ms == 0 else str(ms)
                stats(t, f"dir={filt} max={ms_label} min={min_pts}pts")
        print()

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  F. 掛單 + body ratio 濾網（K棒實體佔比）")
    print("=" * 75)
    for br in [0, 0.3, 0.5, 0.6, 0.7, 0.8]:
        t = run_backtest(df, entry_mode="limit", dir_filter="candle",
                         min_body_ratio=br)
        stats(t, f"candle + body_ratio>={br}")

    # ============================================================
    print(f"\n{'=' * 75}")
    print("  G. 最佳組合 IS/OOS 驗證")
    print("=" * 75)
    # 根據上面結果，挑幾個好的組合做 IS/OOS
    combos = [
        ("baseline limit", dict(entry_mode="limit")),
        ("candle filter", dict(entry_mode="limit", dir_filter="candle")),
        ("rs_05 filter", dict(entry_mode="limit", dir_filter="rs_05")),
        ("candle+max2+min20", dict(entry_mode="limit", dir_filter="candle", max_signals=2, min_range_pts=20)),
        ("candle+早盤", dict(entry_mode="limit", dir_filter="candle", time_start=dt_time(9,11), time_end=dt_time(10,30))),
        ("rs05+max2+min20", dict(entry_mode="limit", dir_filter="rs_05", max_signals=2, min_range_pts=20)),
    ]
    split = pd.Timestamp("2024-01-01").date()
    for label, params in combos:
        t = run_backtest(df, **params)
        if t.empty:
            continue
        is_t = t[t["date"] < split]
        oos_t = t[t["date"] >= split]
        print(f"\n  [{label}]")
        stats(is_t, "  IS  (< 2024)")
        stats(oos_t, "  OOS (>= 2024)")
        yearly(t, label)


if __name__ == "__main__":
    main()

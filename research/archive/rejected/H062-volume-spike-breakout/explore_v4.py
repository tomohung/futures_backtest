"""
H062 Volume Spike Breakout — V4 探索

新增：
1. 日+夜盤連續 bars 計算 MA（MA65 在日盤開始就已成熟）
2. MA 方向濾網：只在順 MA 方向突破才進場
3. 凸量延長：被第一次突破後，反向突破仍視為有效（反手訊號）
"""

from datetime import time as dt_time, timedelta

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
LOOKBACK = 20
COST = 2
MA_PERIOD = 65


def load_data_with_ma():
    """載入日+夜盤 bars，計算連續 MA，回傳只保留日盤。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["ma65"] = df["close"].rolling(MA_PERIOD).mean()

    # 只保留日盤
    df["time"] = df["timestamp"].dt.time
    day_mask = (df["time"] >= dt_time(8, 46)) & (df["time"] <= dt_time(13, 44))
    df_day = df[day_mask].copy()
    df_day["date"] = df_day["timestamp"].dt.date
    # 凸量 ma 用日盤計算
    df_day["vol_ma"] = df_day.groupby("date")["volume"].transform(
        lambda x: x.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)
    )
    return df_day.reset_index(drop=True)


def mark_spikes(df, multiplier=3):
    df = df.copy()
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
                 entry_mode="close",  # "close" / "limit"
                 ma_filter="none",    # "none", "trend" (順MA), "anti" (逆MA)
                 ma_buffer=0,         # 進場價與 MA 的距離（點）
                 spike_reusable=False,  # 凸量被一側突破後，反向突破是否仍有效
                 min_range_pts=0):
    all_trades = []

    for date, idx_range in df.groupby("date").groups.items():
        day_idx = sorted(idx_range)
        n = len(day_idx)
        if n < LOOKBACK + 5:
            continue

        day_times = df.loc[day_idx, "time"].values
        day_highs = df.loc[day_idx, "high"].values.astype(float)
        day_lows = df.loc[day_idx, "low"].values.astype(float)
        day_closes = df.loc[day_idx, "close"].values.astype(float)
        day_spikes = df.loc[day_idx, "is_spike"].values
        day_ma = df.loc[day_idx, "ma65"].values

        spike_list = []
        for i in range(n):
            if day_spikes[i]:
                sp_range = day_highs[i] - day_lows[i]
                if sp_range < max(3, min_range_pts):
                    continue
                spike_list.append({
                    "idx": i,
                    "high": day_highs[i],
                    "low": day_lows[i],
                    "range": sp_range,
                    "time": day_times[i],
                    "long_triggered": False,
                    "short_triggered": False,
                })

        if not spike_list:
            continue

        position = None
        daily_signals = 0
        active_spikes = []
        spike_pointer = 0

        for i in range(n):
            t = day_times[i]
            bar_high = day_highs[i]
            bar_low = day_lows[i]
            bar_close = day_closes[i]
            bar_ma = day_ma[i]

            while spike_pointer < len(spike_list) and spike_list[spike_pointer]["idx"] == i:
                active_spikes.append(spike_list[spike_pointer])
                spike_pointer += 1

            # 收盤強平
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

            # MA 濾網
            def allowed_long():
                if ma_filter == "none":
                    return True
                if np.isnan(bar_ma):
                    return False
                if ma_filter == "trend":
                    return bar_close > bar_ma + ma_buffer
                if ma_filter == "anti":
                    return bar_close < bar_ma - ma_buffer
                return True

            def allowed_short():
                if ma_filter == "none":
                    return True
                if np.isnan(bar_ma):
                    return False
                if ma_filter == "trend":
                    return bar_close < bar_ma - ma_buffer
                if ma_filter == "anti":
                    return bar_close > bar_ma + ma_buffer
                return True

            # 檢查 active spikes（最新的先）
            entered = False
            for sp in reversed(active_spikes):
                tp_dist = sp["range"] * tp_mult
                sl_dist = sp["range"] * sl_mult

                # Long 突破
                long_ok = (entry_mode == "close" and bar_close > sp["high"]) or \
                          (entry_mode == "limit" and bar_high >= sp["high"])
                if long_ok and not sp["long_triggered"] and allowed_long():
                    entry_price = bar_close if entry_mode == "close" else sp["high"]
                    position = {
                        "dir": "long", "entry": entry_price,
                        "tp": entry_price + tp_dist,
                        "sl": entry_price - sl_dist,
                        "spike_time": sp["time"], "entry_time": t,
                    }
                    sp["long_triggered"] = True
                    daily_signals += 1
                    entered = True
                    if not spike_reusable:
                        active_spikes.clear()
                    break

                # Short 突破
                short_ok = (entry_mode == "close" and bar_close < sp["low"]) or \
                           (entry_mode == "limit" and bar_low <= sp["low"])
                if short_ok and not sp["short_triggered"] and allowed_short():
                    entry_price = bar_close if entry_mode == "close" else sp["low"]
                    position = {
                        "dir": "short", "entry": entry_price,
                        "tp": entry_price - tp_dist,
                        "sl": entry_price + sl_dist,
                        "spike_time": sp["time"], "entry_time": t,
                    }
                    sp["short_triggered"] = True
                    daily_signals += 1
                    entered = True
                    if not spike_reusable:
                        active_spikes.clear()
                    break

    return pd.DataFrame(all_trades)


def stats(trades, label=""):
    if trades.empty:
        print(f"  {label:42s} N=    0  --")
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
    print(f"  {label:42s} N={n:>5} WR={wr:>5.1f}% PF={pf:>5.2f} Avg={avg:>+6.1f} Total={total:>+8.0f} Sh={sharpe:>+5.2f}")


def main():
    print("Loading data with night session for MA65...")
    df = load_data_with_ma()
    df = mark_spikes(df, multiplier=3)
    print(f"Loaded {len(df):,} day bars, {df['date'].nunique()} days")
    print(f"MA65 available from: {df[df['ma65'].notna()].iloc[0]['timestamp']}\n")

    # ============================================================
    print("=" * 78)
    print("  A. MA 濾網（entry_mode=close, target=range）")
    print("=" * 78)
    for ma_f in ["none", "trend", "anti"]:
        t = run_backtest(df, ma_filter=ma_f)
        stats(t, f"MA filter = {ma_f}")

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  B. MA 濾網 + buffer（避免剛突破就進場）")
    print("=" * 78)
    for buf in [0, 10, 20, 30, 50]:
        t = run_backtest(df, ma_filter="trend", ma_buffer=buf)
        stats(t, f"trend + buffer={buf}pts")

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  C. MA 濾網 + 凸量可重用（反向也可進場）")
    print("=" * 78)
    for ma_f, reuse in [
        ("none", False), ("none", True),
        ("trend", False), ("trend", True),
    ]:
        t = run_backtest(df, ma_filter=ma_f, spike_reusable=reuse)
        stats(t, f"MA={ma_f} reuse={reuse}")

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  D. MA 濾網 + 時段")
    print("=" * 78)
    for ma_f in ["trend"]:
        for seg_name, (s, e) in [
            ("早盤", (dt_time(9, 11), dt_time(10, 30))),
            ("中盤", (dt_time(10, 30), dt_time(12, 0))),
            ("尾盤", (dt_time(12, 0), dt_time(13, 30))),
        ]:
            t = run_backtest(df, ma_filter=ma_f, time_start=s, time_end=e)
            stats(t, f"{seg_name} MA={ma_f}")

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  E. MA 濾網 + min range + 時段")
    print("=" * 78)
    for min_pts in [0, 15, 20, 30]:
        for seg_name, (s, e) in [
            ("早盤", (dt_time(9, 11), dt_time(10, 30))),
            ("全日", (dt_time(9, 11), dt_time(13, 30))),
        ]:
            t = run_backtest(df, ma_filter="trend", min_range_pts=min_pts,
                             time_start=s, time_end=e)
            stats(t, f"{seg_name} trend min={min_pts}pts")
        print()

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  F. MA trend + max signals")
    print("=" * 78)
    for ms in [0, 1, 2, 3]:
        t = run_backtest(df, ma_filter="trend", max_signals=ms)
        label = "all" if ms == 0 else str(ms)
        stats(t, f"MA=trend max_sig={label}")

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  G. MA trend + TP/SL 倍率")
    print("=" * 78)
    for tp_m in [0.5, 0.618, 0.8, 1.0, 1.5]:
        for sl_m in [0.5, 0.618, 0.8, 1.0, 1.5]:
            t = run_backtest(df, ma_filter="trend", tp_mult=tp_m, sl_mult=sl_m)
            stats(t, f"MA=trend TP={tp_m}x SL={sl_m}x")
        print()

    # ============================================================
    print(f"\n{'=' * 78}")
    print("  H. 最佳組合 IS/OOS")
    print("=" * 78)
    combos = [
        ("baseline (no MA)", dict()),
        ("MA trend", dict(ma_filter="trend")),
        ("MA trend + max2", dict(ma_filter="trend", max_signals=2)),
        ("MA trend + min20", dict(ma_filter="trend", min_range_pts=20)),
        ("MA trend + min30", dict(ma_filter="trend", min_range_pts=30)),
        ("MA trend + 早盤", dict(ma_filter="trend",
                                time_start=dt_time(9, 11), time_end=dt_time(10, 30))),
        ("MA trend + reuse", dict(ma_filter="trend", spike_reusable=True)),
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
        # yearly
        t_c = t.copy()
        t_c["year"] = t_c["date"].apply(lambda d: d.year)
        parts = [f"{y}:{yt['pnl_pts'].sum():+.0f}" for y, yt in t_c.groupby("year")]
        print(f"    yearly: {', '.join(parts)}")


if __name__ == "__main__":
    main()

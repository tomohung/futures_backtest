"""
H063 V2 探索：更嚴格的大單定義 + 反向假設

測試方向：
1. 提高單筆大單門檻（5 → 10 → 20 → 50 口）
2. 縮短 burst 窗口（10s → 5s → 3s）
3. 反向假設：無 burst 的突破是否更容易假突破？

核心問題：我們要找的是「足以預測後續走勢」的大單 burst 定義。
"""

from datetime import time as dt_time, datetime, timedelta
import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
LOOKBACK = 20


def load_1m_data():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:45:00'
              AND timestamp::TIME <= '13:44:00'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    return df.reset_index(drop=True)


def find_h018_breakouts(df):
    events = []
    for date, day_df in df.groupby("date"):
        day_df = day_df.reset_index(drop=True)
        or_bars = day_df[(day_df["time"] >= dt_time(8, 45)) & (day_df["time"] <= dt_time(8, 46))]
        if len(or_bars) < 2:
            continue
        or_high = or_bars["high"].max()
        or_low = or_bars["low"].min()
        or_range = or_high - or_low
        if or_range < 3:
            continue
        after = day_df[(day_df["time"] >= dt_time(8, 47)) & (day_df["time"] <= dt_time(13, 30))].reset_index(drop=True)
        for _, bar in after.iterrows():
            if bar["close"] > or_high:
                events.append({
                    "date": date, "scenario": "h018",
                    "breakout_time": bar["time"], "direction": "long",
                    "key_price": or_high, "entry_price": bar["close"],
                    "key_range": or_range, "timestamp": bar["timestamp"],
                })
                break
            elif bar["close"] < or_low:
                events.append({
                    "date": date, "scenario": "h018",
                    "breakout_time": bar["time"], "direction": "short",
                    "key_price": or_low, "entry_price": bar["close"],
                    "key_range": or_range, "timestamp": bar["timestamp"],
                })
                break
    return pd.DataFrame(events)


def find_h062_breakouts(df, multiplier=3):
    df = df.copy()
    df["vol_ma"] = df.groupby("date")["volume"].transform(
        lambda x: x.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)
    )
    events = []
    for date, day_df in df.groupby("date"):
        day_df = day_df.reset_index(drop=True)
        n = len(day_df)
        if n < LOOKBACK + 5:
            continue
        active_spikes = []
        for i in range(n):
            bar = day_df.iloc[i]
            t = bar["time"]
            if (t >= dt_time(9, 10) and t <= dt_time(13, 25)
                    and not pd.isna(bar["vol_ma"])
                    and bar["volume"] >= bar["vol_ma"] * multiplier
                    and (bar["high"] - bar["low"]) >= 3):
                active_spikes.append({
                    "high": bar["high"], "low": bar["low"],
                    "range": bar["high"] - bar["low"], "spike_time": t,
                })
            if t < dt_time(9, 11) or t >= dt_time(13, 30):
                continue
            for sp in reversed(active_spikes):
                if bar["close"] > sp["high"]:
                    events.append({
                        "date": date, "scenario": "h062",
                        "breakout_time": t, "direction": "long",
                        "key_price": sp["high"], "entry_price": bar["close"],
                        "key_range": sp["range"], "timestamp": bar["timestamp"],
                    })
                    active_spikes.clear()
                    break
                elif bar["close"] < sp["low"]:
                    events.append({
                        "date": date, "scenario": "h062",
                        "breakout_time": t, "direction": "short",
                        "key_price": sp["low"], "entry_price": bar["close"],
                        "key_range": sp["range"], "timestamp": bar["timestamp"],
                    })
                    active_spikes.clear()
                    break
    return pd.DataFrame(events)


def detect_burst_per_minute(ticks_df, date, minute_time, lots_threshold,
                             count_threshold, window_sec):
    """對特定日期、特定分鐘，檢查是否有 burst"""
    minute_end = (datetime.combine(date, minute_time) + timedelta(minutes=1)).time()
    mask = (
        (ticks_df["trade_time"] >= minute_time)
        & (ticks_df["trade_time"] < minute_end)
        & (ticks_df["volume"] >= lots_threshold)
    )
    mt = ticks_df[mask]
    if len(mt) < count_threshold:
        return False, 0
    times = mt["dt"].values
    max_in_window = 0
    for i in range(len(times)):
        window_end = times[i] + np.timedelta64(window_sec, "s")
        count = ((times >= times[i]) & (times <= window_end)).sum()
        if count > max_in_window:
            max_in_window = count
    return max_in_window >= count_threshold, max_in_window


def check_burst_configs(events_df, configs, conn):
    """對每個 config（lots, count, window_sec）檢查 burst。
    configs: list of dict {name, lots, count, window}
    """
    # 初始化欄位
    for cfg in configs:
        events_df[f"burst_{cfg['name']}"] = False

    for date, day_events in events_df.groupby("date"):
        # 查這一天所有大單（以最低門檻先撈）
        min_lots = min(cfg["lots"] for cfg in configs)
        ticks = conn.execute(f"""
            SELECT trade_time, volume
            FROM ticks
            WHERE symbol = 'TX'
              AND trade_date = DATE '{date}'
              AND NOT is_auction
              AND volume >= {min_lots}
            ORDER BY trade_time
        """).fetchdf()
        if ticks.empty:
            continue
        ticks["dt"] = pd.to_datetime(
            ticks["trade_time"].astype(str), format="%H:%M:%S", errors="coerce"
        )

        for idx, evt in day_events.iterrows():
            mt = evt["breakout_time"]
            for cfg in configs:
                has_b, _ = detect_burst_per_minute(
                    ticks, date, mt, cfg["lots"], cfg["count"], cfg["window"]
                )
                events_df.at[idx, f"burst_{cfg['name']}"] = has_b

    return events_df


def compute_outcomes(events_df, df_1m):
    df_1m = df_1m.set_index("timestamp")
    outcomes = []
    for _, evt in events_df.iterrows():
        date = evt["date"]
        entry_price = evt["entry_price"]
        direction = evt["direction"]
        key_range = evt["key_range"]
        bo_ts = evt["timestamp"]
        day_bars = df_1m[df_1m.index.date == date]
        after = day_bars[day_bars.index > bo_ts]
        if after.empty:
            outcomes.append({"outcome": "no_data"})
            continue
        highs = after["high"].values
        lows = after["low"].values
        if direction == "long":
            tp = entry_price + key_range
            sl = entry_price - key_range
        else:
            tp = entry_price - key_range
            sl = entry_price + key_range
        outcome = "timeout"
        for i in range(len(after)):
            h, l = highs[i], lows[i]
            if direction == "long":
                if l <= sl:
                    outcome = "sl"
                    break
                if h >= tp:
                    outcome = "tp"
                    break
            else:
                if h >= sl:
                    outcome = "sl"
                    break
                if l <= tp:
                    outcome = "tp"
                    break
        outcomes.append({"outcome": outcome})
    outcome_df = pd.DataFrame(outcomes)
    return pd.concat([events_df.reset_index(drop=True), outcome_df], axis=1)


def summarize(df, label=""):
    if df.empty:
        print(f"  {label:35s} N=    0")
        return None
    n = len(df)
    tp = (df["outcome"] == "tp").sum()
    sl = (df["outcome"] == "sl").sum()
    to = (df["outcome"] == "timeout").sum()
    decided = tp + sl
    wr = tp / decided * 100 if decided > 0 else 0
    print(f"  {label:35s} N={n:>5}  TP={tp:>4} SL={sl:>4}  WR={wr:>5.1f}% (N_dec={decided})")
    return wr


def print_comparison(events_df, cfg_name, scenario_label):
    print(f"\n  [{scenario_label}] config={cfg_name}")
    col = f"burst_{cfg_name}"
    with_b = events_df[events_df[col]]
    no_b = events_df[~events_df[col]]
    total = len(events_df)
    n_with = len(with_b)
    n_no = len(no_b)
    print(f"    trigger rate: {n_with}/{total} = {n_with/total*100:.1f}%")
    wr_with = summarize(with_b, "    WITH burst")
    wr_no = summarize(no_b, "    NO burst")
    if wr_with and wr_no:
        print(f"    delta: {wr_with - wr_no:+.1f}%")


def main():
    print("Loading 1-min data...")
    df = load_1m_data()
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} days\n")

    print("Finding breakout events...")
    h018 = find_h018_breakouts(df)
    h062 = find_h062_breakouts(df)
    print(f"H018: {len(h018):,} | H062: {len(h062):,}\n")

    # 定義要測試的 config
    configs = [
        # (name, lots, count, window_sec)
        {"name": "5_5_10", "lots": 5, "count": 5, "window": 10},      # 原版
        {"name": "10_5_10", "lots": 10, "count": 5, "window": 10},
        {"name": "10_3_10", "lots": 10, "count": 3, "window": 10},
        {"name": "20_3_10", "lots": 20, "count": 3, "window": 10},
        {"name": "20_3_5", "lots": 20, "count": 3, "window": 5},
        {"name": "20_3_3", "lots": 20, "count": 3, "window": 3},
        {"name": "50_2_10", "lots": 50, "count": 2, "window": 10},
        {"name": "50_2_5", "lots": 50, "count": 2, "window": 5},
        {"name": "50_3_10", "lots": 50, "count": 3, "window": 10},
        {"name": "100_1_10", "lots": 100, "count": 1, "window": 10},  # 單筆巨單
        {"name": "100_2_10", "lots": 100, "count": 2, "window": 10},
    ]

    print(f"Testing {len(configs)} burst configs...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        h018 = check_burst_configs(h018, configs, conn)
        h062 = check_burst_configs(h062, configs, conn)

    print("Computing outcomes...")
    h018 = compute_outcomes(h018, df)
    h062 = compute_outcomes(h062, df)

    # ============================================================
    print("\n" + "=" * 80)
    print("  RESULTS：各 config 的 with/no burst 勝率差異")
    print("=" * 80)

    for cfg in configs:
        print_comparison(h018, cfg["name"], "H018")
    print()
    for cfg in configs:
        print_comparison(h062, cfg["name"], "H062")

    # ============================================================
    # 彙整表格：各 config 的 trigger rate + WR 差異
    print("\n" + "=" * 80)
    print("  SUMMARY TABLE")
    print("=" * 80)

    for label, events in [("H018", h018), ("H062", h062)]:
        print(f"\n  [{label}]")
        print(f"  {'Config':<12} {'Trigger%':>10} {'WR_with':>8} {'WR_no':>8} {'Delta':>7} {'N_with':>8} {'N_no':>7}")
        for cfg in configs:
            col = f"burst_{cfg['name']}"
            w = events[events[col]]
            no = events[~events[col]]
            total = len(events)

            def wr(d):
                tp = (d["outcome"] == "tp").sum()
                sl = (d["outcome"] == "sl").sum()
                return tp / (tp + sl) * 100 if (tp + sl) > 0 else 0

            wr_w = wr(w)
            wr_n = wr(no)
            trigger_pct = len(w) / total * 100
            delta = wr_w - wr_n
            print(f"  {cfg['name']:<12} {trigger_pct:>9.1f}% {wr_w:>7.1f}% {wr_n:>7.1f}% "
                  f"{delta:>+6.1f}% {len(w):>7} {len(no):>7}")

    # ============================================================
    # 反向假設：無 burst 是否更容易假突破？
    print("\n" + "=" * 80)
    print("  反向測試：假設「無 burst = 假突破」，做反向交易")
    print("=" * 80)
    print("  邏輯：如果 NO burst 的 WR < 45%，代表反向有正期望值")
    print()

    for label, events in [("H018", h018), ("H062", h062)]:
        print(f"\n  [{label}] 無 burst 群組勝率（越低 → 反向越有 edge）")
        for cfg in configs:
            col = f"burst_{cfg['name']}"
            no = events[~events[col]]
            if len(no) < 30:
                continue
            tp = (no["outcome"] == "tp").sum()
            sl = (no["outcome"] == "sl").sum()
            decided = tp + sl
            wr = tp / decided * 100 if decided > 0 else 0
            reverse_wr = 100 - wr if decided > 0 else 0
            print(f"  {cfg['name']:<12}  N={len(no):>4}  WR={wr:>5.1f}%  反向WR={reverse_wr:>5.1f}%")


if __name__ == "__main__":
    main()

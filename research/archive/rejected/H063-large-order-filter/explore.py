"""
H063 Large Order Filter — Phase 1 Distribution Exploration

策略：
1. 用 ohlcv_1m 先找所有候選突破事件
   - H018 場景：收盤突破開盤二分 K (8:45-8:47) 的 high/low
   - H062 場景：收盤突破凸量 K (過去 20 根均量 × 3) 的 high/low
2. 對每個候選突破，查該分鐘的 ticks 資料
3. 檢查該分鐘是否有「連續大單 burst」（10 秒窗口內 ≥ 5 筆 5 口以上）
4. 比較「有 burst」vs「無 burst」的後續表現（MFE/MAE/勝率）
"""

from datetime import time as dt_time, datetime, timedelta
import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
LOOKBACK = 20

# 大單定義（可調）
BURST_WINDOW_SEC = 10
BURST_MIN_TICKS = 5
BURST_MIN_LOTS = 5


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
    """找開盤二分 K 突破事件（H018 場景）"""
    events = []
    for date, day_df in df.groupby("date"):
        day_df = day_df.reset_index(drop=True)
        # 開盤二分 K: 08:45 + 08:46
        or_bars = day_df[(day_df["time"] >= dt_time(8, 45)) & (day_df["time"] <= dt_time(8, 46))]
        if len(or_bars) < 2:
            continue
        or_high = or_bars["high"].max()
        or_low = or_bars["low"].min()
        or_range = or_high - or_low
        if or_range < 3:
            continue

        # 9:10 之後的 bars
        after = day_df[(day_df["time"] >= dt_time(8, 47)) & (day_df["time"] <= dt_time(13, 30))].reset_index(drop=True)
        broke = None  # 避免一天出太多信號，先只抓「當日第一次突破」
        for _, bar in after.iterrows():
            if bar["close"] > or_high and broke is None:
                events.append({
                    "date": date, "scenario": "h018",
                    "breakout_time": bar["time"],
                    "direction": "long",
                    "key_price": or_high,
                    "entry_price": bar["close"],
                    "key_range": or_range,
                    "timestamp": bar["timestamp"],
                })
                broke = "long"
                break
            elif bar["close"] < or_low and broke is None:
                events.append({
                    "date": date, "scenario": "h018",
                    "breakout_time": bar["time"],
                    "direction": "short",
                    "key_price": or_low,
                    "entry_price": bar["close"],
                    "key_range": or_range,
                    "timestamp": bar["timestamp"],
                })
                broke = "short"
                break
    return pd.DataFrame(events)


def find_h062_breakouts(df, multiplier=3):
    """找凸量 K 突破事件（H062 場景）"""
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

        active_spikes = []  # 尚未被突破的凸量 K
        for i in range(n):
            bar = day_df.iloc[i]
            t = bar["time"]

            # 加入當前凸量 K
            if (t >= dt_time(9, 10) and t <= dt_time(13, 25)
                    and not pd.isna(bar["vol_ma"])
                    and bar["volume"] >= bar["vol_ma"] * multiplier
                    and (bar["high"] - bar["low"]) >= 3):
                active_spikes.append({
                    "high": bar["high"], "low": bar["low"],
                    "range": bar["high"] - bar["low"],
                    "spike_time": t,
                })

            # 檢查突破
            if t < dt_time(9, 11) or t >= dt_time(13, 30):
                continue
            for sp in reversed(active_spikes):
                if bar["close"] > sp["high"]:
                    events.append({
                        "date": date, "scenario": "h062",
                        "breakout_time": t,
                        "direction": "long",
                        "key_price": sp["high"],
                        "entry_price": bar["close"],
                        "key_range": sp["range"],
                        "timestamp": bar["timestamp"],
                        "spike_time": sp["spike_time"],
                    })
                    active_spikes.clear()
                    break
                elif bar["close"] < sp["low"]:
                    events.append({
                        "date": date, "scenario": "h062",
                        "breakout_time": t,
                        "direction": "short",
                        "key_price": sp["low"],
                        "entry_price": bar["close"],
                        "key_range": sp["range"],
                        "timestamp": bar["timestamp"],
                        "spike_time": sp["spike_time"],
                    })
                    active_spikes.clear()
                    break
    return pd.DataFrame(events)


def check_burst_batch(events_df, conn):
    """批次檢查每個事件對應的那一分鐘是否有連續大單 burst。"""
    events_df = events_df.copy()
    events_df["has_burst"] = False
    events_df["max_burst_ticks"] = 0   # 該分鐘最多的 10 秒大單筆數
    events_df["large_tick_count"] = 0  # 該分鐘總共的大單筆數

    # 以日期分組批次查詢
    for date, day_events in events_df.groupby("date"):
        # 這一天所有事件的分鐘都要查
        minutes = day_events["breakout_time"].unique()
        if len(minutes) == 0:
            continue

        # 查這一天所有大單 tick
        ticks = conn.execute(f"""
            SELECT trade_time, volume
            FROM ticks
            WHERE symbol = 'TX'
              AND trade_date = DATE '{date}'
              AND NOT is_auction
              AND volume >= {BURST_MIN_LOTS}
            ORDER BY trade_time
        """).fetchdf()

        if ticks.empty:
            continue

        # 轉為 datetime 以便計算窗口
        ticks["dt"] = pd.to_datetime(
            ticks["trade_time"].astype(str), format="%H:%M:%S", errors="coerce"
        )

        # 對每個事件的分鐘檢查
        for idx, evt in day_events.iterrows():
            mt = evt["breakout_time"]
            # 該分鐘內的大單
            minute_ticks = ticks[
                (ticks["trade_time"] >= mt)
                & (ticks["trade_time"] < (datetime.combine(date, mt) + timedelta(minutes=1)).time())
            ]
            events_df.at[idx, "large_tick_count"] = len(minute_ticks)

            if len(minute_ticks) < BURST_MIN_TICKS:
                continue

            # 找 10 秒窗口內 >= 5 筆的最大數量
            times = minute_ticks["dt"].values
            max_in_window = 0
            for i in range(len(times)):
                window_end = times[i] + np.timedelta64(BURST_WINDOW_SEC, "s")
                count = ((times >= times[i]) & (times <= window_end)).sum()
                if count > max_in_window:
                    max_in_window = count

            events_df.at[idx, "max_burst_ticks"] = max_in_window
            if max_in_window >= BURST_MIN_TICKS:
                events_df.at[idx, "has_burst"] = True

    return events_df


def compute_outcomes(events_df, df_1m):
    """對每個事件計算後續 MFE/MAE 與 RR=1:1 的結果"""
    df_1m = df_1m.set_index("timestamp")

    outcomes = []
    for _, evt in events_df.iterrows():
        date = evt["date"]
        entry_price = evt["entry_price"]
        direction = evt["direction"]
        key_range = evt["key_range"]
        bo_ts = evt["timestamp"]

        # 取突破後當日剩餘 bars
        day_bars = df_1m[df_1m.index.date == date]
        after = day_bars[day_bars.index > bo_ts]
        if after.empty:
            outcomes.append({"mfe": 0, "mae": 0, "mfe_in_range": 0, "mae_in_range": 0, "outcome": "no_data"})
            continue

        highs = after["high"].values
        lows = after["low"].values

        if direction == "long":
            mfe = highs.max() - entry_price
            mae = entry_price - lows.min()
            tp = entry_price + key_range
            sl = entry_price - key_range
        else:
            mfe = entry_price - lows.min()
            mae = highs.max() - entry_price
            tp = entry_price - key_range
            sl = entry_price + key_range

        # 判斷先到 TP 還是 SL
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

        outcomes.append({
            "mfe": mfe, "mae": mae,
            "mfe_in_range": mfe / key_range if key_range > 0 else 0,
            "mae_in_range": mae / key_range if key_range > 0 else 0,
            "outcome": outcome,
        })

    outcome_df = pd.DataFrame(outcomes)
    return pd.concat([events_df.reset_index(drop=True), outcome_df], axis=1)


def summarize(df, label=""):
    if df.empty:
        print(f"  {label}: N=0")
        return
    n = len(df)
    wr_tp = (df["outcome"] == "tp").sum() / max((df["outcome"] != "no_data").sum(), 1) * 100
    tp_ct = (df["outcome"] == "tp").sum()
    sl_ct = (df["outcome"] == "sl").sum()
    to_ct = (df["outcome"] == "timeout").sum()
    decided = tp_ct + sl_ct
    wr_decided = tp_ct / decided * 100 if decided > 0 else 0
    avg_mfe = df["mfe_in_range"].mean()
    avg_mae = df["mae_in_range"].mean()
    print(f"  {label:30s} N={n:>5}  TP={tp_ct:>4} SL={sl_ct:>4} TO={to_ct:>3}  "
          f"WR={wr_decided:>5.1f}%  MFE={avg_mfe:.2f}x  MAE={avg_mae:.2f}x")


def main():
    print("Loading 1-min data...")
    df = load_1m_data()
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} days")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}\n")

    # ============================================================
    print("Finding H018 (opening 2-min K) breakout events...")
    h018 = find_h018_breakouts(df)
    print(f"H018 events: {len(h018):,}")

    print("Finding H062 (volume spike K) breakout events...")
    h062 = find_h062_breakouts(df)
    print(f"H062 events: {len(h062):,}")

    # ============================================================
    print("\nChecking large order bursts (this may take a while)...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        h018 = check_burst_batch(h018, conn)
        h062 = check_burst_batch(h062, conn)

    # ============================================================
    print("\nComputing outcomes (TP/SL with RR=1:1, target=key_range)...")
    h018 = compute_outcomes(h018, df)
    h062 = compute_outcomes(h062, df)

    # ============================================================
    print("\n" + "=" * 75)
    print("  RESULTS: H018 場景（開盤二分 K 突破）")
    print("=" * 75)
    print(f"總事件: {len(h018):,}")
    print(f"有 burst: {h018['has_burst'].sum():,} ({h018['has_burst'].sum()/len(h018)*100:.1f}%)")
    print(f"無 burst: {(~h018['has_burst']).sum():,}")
    print()
    summarize(h018, "ALL")
    summarize(h018[h018["has_burst"]], "WITH burst")
    summarize(h018[~h018["has_burst"]], "NO burst")
    print("\n按方向:")
    summarize(h018[(h018["direction"] == "long") & h018["has_burst"]], "long + burst")
    summarize(h018[(h018["direction"] == "long") & ~h018["has_burst"]], "long no-burst")
    summarize(h018[(h018["direction"] == "short") & h018["has_burst"]], "short + burst")
    summarize(h018[(h018["direction"] == "short") & ~h018["has_burst"]], "short no-burst")

    # ============================================================
    print("\n" + "=" * 75)
    print("  RESULTS: H062 場景（凸量 K 突破）")
    print("=" * 75)
    print(f"總事件: {len(h062):,}")
    print(f"有 burst: {h062['has_burst'].sum():,} ({h062['has_burst'].sum()/len(h062)*100:.1f}%)")
    print(f"無 burst: {(~h062['has_burst']).sum():,}")
    print()
    summarize(h062, "ALL")
    summarize(h062[h062["has_burst"]], "WITH burst")
    summarize(h062[~h062["has_burst"]], "NO burst")
    print("\n按方向:")
    summarize(h062[(h062["direction"] == "long") & h062["has_burst"]], "long + burst")
    summarize(h062[(h062["direction"] == "long") & ~h062["has_burst"]], "long no-burst")
    summarize(h062[(h062["direction"] == "short") & h062["has_burst"]], "short + burst")
    summarize(h062[(h062["direction"] == "short") & ~h062["has_burst"]], "short no-burst")

    # ============================================================
    print("\n" + "=" * 75)
    print("  Burst 強度分佈（max_burst_ticks 分位）")
    print("=" * 75)
    for label, events in [("H018", h018), ("H062", h062)]:
        print(f"\n  [{label}]")
        for thresh in [0, 3, 5, 7, 10, 15]:
            sub = events[events["max_burst_ticks"] >= thresh]
            if len(sub) == 0:
                continue
            summarize(sub, f"burst>={thresh}")

    # Save
    h018.to_csv("research/active/H063-large-order-filter/results_h018.csv", index=False)
    h062.to_csv("research/active/H063-large-order-filter/results_h062.csv", index=False)
    print("\nSaved: results_h018.csv, results_h062.csv")


if __name__ == "__main__":
    main()

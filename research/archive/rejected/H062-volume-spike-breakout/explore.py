"""
H062 Volume Spike Breakout — Phase 1 Distribution Exploration

凸量 K 突破策略探索（向量化版本）
"""

import duckdb
import pandas as pd
import numpy as np
from datetime import time as dt_time

DB_PATH = "data/futures.duckdb"
LOOKBACK_BARS = 20
MULTIPLIERS = [2, 3, 5]

TIME_SEGMENTS = {
    "09:10-10:30": (dt_time(9, 10), dt_time(10, 30)),
    "10:30-12:00": (dt_time(10, 30), dt_time(12, 0)),
    "12:00-13:30": (dt_time(12, 0), dt_time(13, 30)),
}


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
    df["bar_idx"] = range(len(df))
    return df


def find_volume_spikes(df, multiplier):
    df = df.copy()
    df["vol_ma"] = df.groupby("date")["volume"].transform(
        lambda x: x.rolling(LOOKBACK_BARS, min_periods=LOOKBACK_BARS).mean().shift(1)
    )
    mask = (
        (df["time"] >= dt_time(9, 10))
        & (df["time"] <= dt_time(13, 30))
        & (df["vol_ma"].notna())
        & (df["volume"] >= df["vol_ma"] * multiplier)
    )
    spikes = df[mask].copy()
    spikes["range"] = spikes["high"] - spikes["low"]
    spikes["body"] = abs(spikes["close"] - spikes["open"])
    return spikes


def analyze_breakout_vectorized(df, spikes):
    """向量化分析突破：用 groupby + cummax/cummin 避免逐 bar 迴圈"""
    if len(spikes) == 0:
        return pd.DataFrame()

    df_indexed = df.set_index("bar_idx")
    results = []

    # 按日期分組處理
    for date, day_spikes in spikes.groupby("date"):
        day_bars = df[df["date"] == date].copy()
        if len(day_bars) == 0:
            continue

        for _, spike in day_spikes.iterrows():
            spike_range = spike["range"]
            if spike_range < 1:
                continue

            spike_idx = spike["bar_idx"]
            spike_high = spike["high"]
            spike_low = spike["low"]
            spike_body = spike["body"]

            # 後續 bars
            subsequent = day_bars[day_bars["bar_idx"] > spike_idx]
            if len(subsequent) == 0:
                continue

            # 找第一根收盤突破的 bar
            close_above = subsequent["close"] > spike_high
            close_below = subsequent["close"] < spike_low

            first_above_idx = close_above.idxmax() if close_above.any() else None
            first_below_idx = close_below.idxmax() if close_below.any() else None

            if first_above_idx is None and first_below_idx is None:
                continue

            if first_above_idx is not None and first_below_idx is not None:
                if first_above_idx <= first_below_idx:
                    breakout_dir = "long"
                    bo_idx = first_above_idx
                else:
                    breakout_dir = "short"
                    bo_idx = first_below_idx
            elif first_above_idx is not None:
                breakout_dir = "long"
                bo_idx = first_above_idx
            else:
                breakout_dir = "short"
                bo_idx = first_below_idx

            breakout_price = spike_high if breakout_dir == "long" else spike_low
            breakout_time = day_bars.loc[bo_idx, "time"]

            # 突破後的 bars
            after = day_bars[day_bars["bar_idx"] > day_bars.loc[bo_idx, "bar_idx"]]
            if len(after) == 0:
                continue

            after_highs = after["high"].values
            after_lows = after["low"].values

            if breakout_dir == "long":
                max_favorable = float(after_highs.max()) - breakout_price
                max_adverse = breakout_price - float(after_lows.min())
            else:
                max_favorable = breakout_price - float(after_lows.min())
                max_adverse = float(after_highs.max()) - breakout_price

            # 目標價計算
            target_range = spike_range
            target_body = spike_body if spike_body >= 1 else spike_range
            target_half = spike_range / 2 if spike_range / 2 >= 1 else spike_range

            # 判定先到 TP 還是 SL（向量化）
            def determine_outcome_fast(target):
                if breakout_dir == "long":
                    tp = breakout_price + target
                    sl = breakout_price - target
                    hit_tp = after_highs >= tp
                    hit_sl = after_lows <= sl
                else:
                    tp = breakout_price - target
                    sl = breakout_price + target
                    hit_tp = after_lows <= tp
                    hit_sl = after_highs >= sl

                first_tp = np.argmax(hit_tp) if hit_tp.any() else len(after)
                first_sl = np.argmax(hit_sl) if hit_sl.any() else len(after)

                if first_tp == len(after) and first_sl == len(after):
                    return "timeout"
                return "win" if first_tp <= first_sl else "loss"

            outcome_range = determine_outcome_fast(target_range)
            outcome_body = determine_outcome_fast(target_body)
            outcome_half = determine_outcome_fast(target_half)

            segment = "unknown"
            for seg_name, (s_t, e_t) in TIME_SEGMENTS.items():
                if s_t <= spike["time"] < e_t:
                    segment = seg_name
                    break

            results.append({
                "date": date,
                "spike_time": spike["time"],
                "spike_range": spike_range,
                "spike_body": spike_body,
                "spike_volume": spike["volume"],
                "spike_vol_ratio": spike["volume"] / spike["vol_ma"],
                "breakout_dir": breakout_dir,
                "breakout_time": breakout_time,
                "max_favorable": max_favorable,
                "max_adverse": max_adverse,
                "mfe_in_range": max_favorable / spike_range,
                "mae_in_range": max_adverse / spike_range,
                "outcome_range": outcome_range,
                "outcome_body": outcome_body,
                "outcome_half": outcome_half,
                "segment": segment,
            })

    return pd.DataFrame(results)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_results(results, label="ALL"):
    if len(results) == 0:
        print(f"  {label}: no data")
        return

    for target_name in ["range", "body", "half"]:
        col = f"outcome_{target_name}"
        wins = (results[col] == "win").sum()
        losses = (results[col] == "loss").sum()
        timeouts = (results[col] == "timeout").sum()
        total_decided = wins + losses
        wr = wins / total_decided * 100 if total_decided > 0 else 0
        print(f"  Target={target_name:5s}: W={wins} L={losses} T={timeouts} | WR={wr:.1f}% (N={total_decided})")


def main():
    print("Loading data...")
    df = load_data()
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} trading days")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}")

    for mult in MULTIPLIERS:
        print_section(f"Volume Spike >= {mult}x avg (lookback={LOOKBACK_BARS})")

        spikes = find_volume_spikes(df, mult)
        n_spikes = len(spikes)
        n_days = spikes["date"].nunique()
        print(f"\n凸量 K 數量: {n_spikes:,}")
        print(f"涵蓋交易日: {n_days}")
        print(f"平均每日: {n_spikes / n_days:.1f} 根" if n_days > 0 else "")

        print("\n--- 凸量 K 時間分佈 ---")
        for seg_name, (s_t, e_t) in TIME_SEGMENTS.items():
            count = len(spikes[(spikes["time"] >= s_t) & (spikes["time"] < e_t)])
            print(f"  {seg_name}: {count:,} ({count/n_spikes*100:.1f}%)")

        print("\n--- 凸量 K 振幅統計 ---")
        r = spikes["range"]
        print(f"  Mean={r.mean():.1f} Median={r.median():.1f} Std={r.std():.1f} P25={r.quantile(.25):.1f} P75={r.quantile(.75):.1f}")

        print("\nAnalyzing breakouts...")
        results = analyze_breakout_vectorized(df, spikes)
        print(f"有突破事件: {len(results):,} / {n_spikes:,} ({len(results)/n_spikes*100:.1f}%)")

        if len(results) == 0:
            continue

        longs = (results["breakout_dir"] == "long").sum()
        shorts = (results["breakout_dir"] == "short").sum()
        print(f"做多: {longs} ({longs/len(results)*100:.1f}%) | 做空: {shorts} ({shorts/len(results)*100:.1f}%)")

        print(f"\n--- MFE/MAE（以凸量K振幅為單位）---")
        print(f"  MFE mean={results['mfe_in_range'].mean():.2f}x median={results['mfe_in_range'].median():.2f}x")
        print(f"  MAE mean={results['mae_in_range'].mean():.2f}x median={results['mae_in_range'].median():.2f}x")

        print(f"\n--- 整體目標價達成率（RR=1:1）---")
        print_results(results)

        print(f"\n--- 按時段分組 ---")
        for seg_name in TIME_SEGMENTS:
            seg = results[results["segment"] == seg_name]
            print(f"\n  [{seg_name}] N={len(seg)}")
            if len(seg) > 0:
                print_results(seg, seg_name)

        print(f"\n--- 按方向 x 時段（Target=range）---")
        for direction in ["long", "short"]:
            print(f"\n  {direction.upper()}")
            dir_data = results[results["breakout_dir"] == direction]
            for seg_name in TIME_SEGMENTS:
                seg = dir_data[dir_data["segment"] == seg_name]
                if len(seg) == 0:
                    continue
                w = (seg["outcome_range"] == "win").sum()
                l = (seg["outcome_range"] == "loss").sum()
                td = w + l
                wr = w / td * 100 if td > 0 else 0
                print(f"    {seg_name}: W={w} L={l} WR={wr:.1f}% (N={td})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
波動潛力日分析工具

從 ohlcv_1m 找出「值得交易的日子」，分析波動集中時段並分類。

使用方式：
    uv run python src/analysis/volatility_capture.py
    uv run python src/analysis/volatility_capture.py --year 2025
    uv run python src/analysis/volatility_capture.py --recent 30
"""
import argparse
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
OUTPUT_PATH = Path(__file__).parents[2] / "specs" / "strategies" / "volatility_potential_days.csv"
SYMBOL = "TX"

# 四個時段定義
SEGMENTS = [
    ("MorningEarly", dtime(8, 45), dtime(10, 0)),   # ORB/EstHL 進場區
    ("MorningLate",  dtime(10, 0), dtime(11, 0)),    # 趨勢延伸區
    ("Midday",       dtime(11, 0), dtime(12, 0)),    # 通常較沉悶
    ("Afternoon",    dtime(12, 0), dtime(13, 46)),    # 反轉/收盤行情 (含 13:45)
]

# 潛力日分類閾值
CLASSIFY_THRESHOLDS = {
    "EarlyTrend": ("MorningEarly", 0.50),
    "LateTrend":  ("MorningLate", 0.40),
    "Afternoon":  ("Afternoon", 0.40),
}

FIXED_THRESHOLD = 1.0  # 固定門檻 range_pct%（跨年度較穩定，取代 P67 作為主要篩選）


def load_daily_ohlcv() -> pd.DataFrame:
    """載入每日 OHLCV 指標。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute("""
            SELECT
                CAST(timestamp AS DATE) AS trade_date,
                MIN_BY(open, timestamp)  AS day_open,
                MAX(high)                AS day_high,
                MIN(low)                 AS day_low,
                MAX_BY(close, timestamp) AS day_close,
                SUM(volume)              AS volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1
            ORDER BY 1
        """, [SYMBOL]).df()

    df["day_range"] = df["day_high"] - df["day_low"]
    df["range_pct"] = (df["day_range"] / df["day_open"] * 100).round(4)
    df["direction"] = np.where(df["day_close"] >= df["day_open"], "UP", "DOWN")
    df["oc_pct"] = ((df["day_close"] - df["day_open"]) / df["day_open"] * 100).round(4)
    return df


def load_1m_bars() -> pd.DataFrame:
    """載入 1 分 K 用於時段分析。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute("""
            SELECT
                CAST(timestamp AS DATE) AS trade_date,
                CAST(timestamp AS TIME) AS bar_time,
                high, low
            FROM ohlcv_1m
            WHERE symbol = ?
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """, [SYMBOL]).df()
    return df


def compute_segment_marginal(bars_1m: pd.DataFrame) -> pd.DataFrame:
    """計算每日各時段的邊際波幅佔比。

    邊際波幅 = 該時段結束時的累積 range - 該時段開始時的累積 range
    邊際佔比 = 邊際波幅 / 當日總 range
    """
    records = []

    for trade_date, day_bars in bars_1m.groupby("trade_date"):
        day_bars = day_bars.sort_values("bar_time")
        highs = day_bars["high"].values
        lows = day_bars["low"].values
        times = day_bars["bar_time"].values

        day_high = highs.max()
        day_low = lows.min()
        day_range = float(day_high - day_low)

        if day_range == 0:
            continue

        run_high = -np.inf
        run_low = np.inf
        seg_idx = 0
        prev_cum_range = 0.0
        seg_marginals = {}

        for i in range(len(times)):
            t = times[i]
            run_high = max(run_high, float(highs[i]))
            run_low = min(run_low, float(lows[i]))

            # 檢查是否跨越到下一個時段
            while seg_idx < len(SEGMENTS) - 1:
                next_start = SEGMENTS[seg_idx + 1][1]
                # pandas Timedelta / time comparison
                if isinstance(t, dtime):
                    bar_t = t
                else:
                    # numpy timedelta64 → convert
                    total_sec = int(t / np.timedelta64(1, "s"))
                    bar_t = dtime(total_sec // 3600, (total_sec % 3600) // 60, total_sec % 60)

                if bar_t >= next_start:
                    # 記錄當前時段的邊際
                    cur_range = run_high - run_low
                    seg_name = SEGMENTS[seg_idx][0]
                    seg_marginals[seg_name] = cur_range - prev_cum_range
                    prev_cum_range = cur_range
                    seg_idx += 1
                else:
                    break

        # 最後一個時段
        cur_range = run_high - run_low
        seg_name = SEGMENTS[seg_idx][0]
        seg_marginals[seg_name] = cur_range - prev_cum_range

        row = {"trade_date": trade_date, "day_range": day_range}
        for seg_name, _, _ in SEGMENTS:
            marginal = seg_marginals.get(seg_name, 0.0)
            row[f"{seg_name}_marginal"] = round(marginal, 2)
            row[f"{seg_name}_pct"] = round(marginal / day_range, 4) if day_range > 0 else 0.0
        records.append(row)

    return pd.DataFrame(records)


def classify_day(row: pd.Series) -> str:
    """根據時段佔比分類潛力日。"""
    for label, (seg_name, threshold) in CLASSIFY_THRESHOLDS.items():
        if row[f"{seg_name}_pct"] >= threshold:
            return label
    return "Spread"


def build_analysis(year: int | None = None) -> pd.DataFrame:
    """組合完整分析 DataFrame。"""
    daily = load_daily_ohlcv()
    bars = load_1m_bars()
    segments = compute_segment_marginal(bars)

    df = daily.merge(segments, on="trade_date", how="inner", suffixes=("", "_seg"))
    # 移除重複的 day_range
    if "day_range_seg" in df.columns:
        df.drop(columns=["day_range_seg"], inplace=True)

    df["year"] = pd.to_datetime(df["trade_date"]).dt.year
    df["is_potential"] = df["range_pct"] >= FIXED_THRESHOLD

    # 分類（僅對潛力日有意義，但全部都算）
    df["day_type"] = df.apply(classify_day, axis=1)

    if year is not None:
        df = df[df["year"] == year].copy()

    return df


def print_report(df: pd.DataFrame, recent_n: int = 20):
    """輸出終端報表。"""
    # --- 年度摘要 ---
    print("\n" + "=" * 70)
    print("波動潛力日分析")
    print("=" * 70)

    years = sorted(df["year"].unique())

    print(f"\n### 年度摘要（Fixed {FIXED_THRESHOLD}% 門檻）")
    print(f"| 年度 | 交易日 | 潛力日 | 佔比 | 均range% |")
    print(f"|------|-------:|-------:|-----:|--------:|")
    for y in years:
        ydf = df[df["year"] == y]
        n_total = len(ydf)
        n_pot = ydf["is_potential"].sum()
        pct = n_pot / n_total * 100 if n_total > 0 else 0
        avg_range = ydf["range_pct"].mean()
        print(f"| {y} | {n_total:>5} | {n_pot:>5} | {pct:>4.0f}% | {avg_range:>6.2f}% |")

    # --- 潛力日類型分佈 ---
    pot_df = df[df["is_potential"]].copy()
    if len(pot_df) == 0:
        print("\n無潛力日資料")
        return

    print(f"\n### 潛力日類型分佈（Fixed {FIXED_THRESHOLD}%，共 {len(pot_df)} 日）")
    type_counts = pot_df["day_type"].value_counts()
    print(f"| 類型 | 筆數 | 佔比 | 平均range% | 平均方向 |")
    print(f"|------|-----:|-----:|-----------:|---------|")
    for t in ["EarlyTrend", "LateTrend", "Afternoon", "Spread"]:
        if t not in type_counts.index:
            continue
        tdf = pot_df[pot_df["day_type"] == t]
        n = len(tdf)
        pct = n / len(pot_df) * 100
        avg_r = tdf["range_pct"].mean()
        up_pct = (tdf["direction"] == "UP").mean() * 100
        print(f"| {t:<11} | {n:>4} | {pct:>4.0f}% | {avg_r:>9.2f}% | UP {up_pct:.0f}% |")

    # --- 時段平均佔比 ---
    print(f"\n### 潛力日時段波幅佔比（平均）")
    print(f"| 時段 | 佔比 | 平均邊際(pt) |")
    print(f"|------|-----:|------------:|")
    for seg_name, start, end in SEGMENTS:
        avg_pct = pot_df[f"{seg_name}_pct"].mean() * 100
        avg_marginal = pot_df[f"{seg_name}_marginal"].mean()
        print(f"| {seg_name:<13} | {avg_pct:>4.0f}% | {avg_marginal:>10.0f} |")

    # --- 近 N 日明細 ---
    recent = df.tail(recent_n)
    print(f"\n### 近 {recent_n} 日明細")
    print(f"| 日期       | range% | 方向 | 類型        | Early | Late | Mid  | Aft  | 潛力 |")
    print(f"|------------|-------:|------|-------------|------:|-----:|-----:|-----:|------|")
    for _, r in recent.iterrows():
        pot_mark = "●" if r["is_potential"] else ""
        date_str = str(r['trade_date'])[:10]
        print(f"| {date_str} | {r['range_pct']:>5.2f}% | {r['direction']:<4} "
              f"| {r['day_type']:<11} "
              f"| {r['MorningEarly_pct'] * 100:>4.0f}% "
              f"| {r['MorningLate_pct'] * 100:>4.0f}% "
              f"| {r['Midday_pct'] * 100:>4.0f}% "
              f"| {r['Afternoon_pct'] * 100:>4.0f}% "
              f"| {pot_mark:<4} |")


def main():
    parser = argparse.ArgumentParser(description="波動潛力日分析")
    parser.add_argument("--year", type=int, default=None, help="篩選特定年度")
    parser.add_argument("--recent", type=int, default=20, help="近 N 日明細（預設 20）")
    args = parser.parse_args()

    df = build_analysis(year=args.year)

    if df.empty:
        print("無資料")
        return

    print_report(df, recent_n=args.recent)

    # 儲存 CSV
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nCSV 已儲存：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()

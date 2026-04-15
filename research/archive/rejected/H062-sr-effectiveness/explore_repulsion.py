#!/usr/bin/env python3
"""
H062 補充分析：S/R 排斥效應
假設：強 S/R 的效果不是「碰到會彈」，而是「價格不會碰到」。
檢驗：S/R 附近的價格密度是否低於遠離 S/R 的區域？
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.signal import find_peaks
from scipy import stats

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"
LOOKBACK_MONTHS = 6


def calc_sr_as_of(conn, as_of_date, lookback_days=30, bin_size=50,
                  swing_window=3, cluster_dist=100):
    """同 explore.py。"""
    bars = conn.execute("""
        WITH bars_30m AS (
            SELECT
                CASE
                    WHEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                    THEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                    ELSE time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')
                END AS ts,
                MAX(high)::INT AS high,
                MIN(low)::INT  AS low,
                SUM(volume)    AS volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE < ?
              AND timestamp::DATE >= ? - ? * INTERVAL '1 day'
            GROUP BY ts
        )
        SELECT high, low, volume FROM bars_30m ORDER BY ts
    """, [SYMBOL, as_of_date, as_of_date, lookback_days]).fetchall()

    if len(bars) < 20:
        return None

    highs = np.array([r[0] for r in bars], dtype=float)
    lows = np.array([r[1] for r in bars], dtype=float)
    vols = np.array([r[2] for r in bars], dtype=float)
    n = len(bars)

    swing_highs, swing_lows = [], []
    for i in range(swing_window, n - swing_window):
        if highs[i] == max(highs[i - swing_window:i + swing_window + 1]):
            swing_highs.append(float(highs[i]))
        if lows[i] == min(lows[i - swing_window:i + swing_window + 1]):
            swing_lows.append(float(lows[i]))

    def cluster(levels):
        if not levels:
            return []
        levels = sorted(levels)
        groups = [[levels[0]]]
        for lv in levels[1:]:
            if lv - groups[-1][-1] <= cluster_dist:
                groups[-1].append(lv)
            else:
                groups.append([lv])
        return [(round(np.mean(g)), len(g)) for g in groups]

    swing_high_clusters = cluster(swing_highs)
    swing_low_clusters = cluster(swing_lows)

    peaks_idx, props = find_peaks(
        _build_vp(highs, lows, vols, bin_size),
        prominence=0.1, distance=2,
    )
    price_min = int(min(lows) // bin_size * bin_size)
    bins = np.arange(price_min, price_min + 10000, bin_size)
    vp_arr = _build_vp(highs, lows, vols, bin_size)
    peaks_idx2, _ = find_peaks(vp_arr, prominence=vp_arr.max() * 0.1, distance=2)
    vp_levels = [int(price_min + p * bin_size + bin_size / 2) for p in peaks_idx2]

    sr_levels = []
    for price, count in swing_high_clusters:
        sr_levels.append({"price": price, "type": "swing_high", "strength": count})
    for price, count in swing_low_clusters:
        sr_levels.append({"price": price, "type": "swing_low", "strength": count})

    return sr_levels


def _build_vp(highs, lows, vols, bin_size):
    price_min = int(min(lows) // bin_size * bin_size)
    price_max = int(max(highs) // bin_size * bin_size + bin_size)
    bins = np.arange(price_min, price_max + bin_size, bin_size)
    vp = np.zeros(len(bins))
    for i in range(len(highs)):
        lo, hi, vol = lows[i], highs[i], vols[i]
        idx = [j for j, b in enumerate(bins) if b < hi and b + bin_size > lo]
        if idx:
            per = vol / len(idx)
            for j in idx:
                vp[j] += per
    return vp


def main():
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        trading_days = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE >= CURRENT_DATE - ? * INTERVAL '1 month'
            ORDER BY td
        """, [SYMBOL, LOOKBACK_MONTHS]).fetchall()
        trading_days = [r[0] for r in trading_days]

        print(f"分析期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 天)")

        # --- 分析 1：S/R 觸及率 vs strength ---
        # 「強 S/R 是否更不容易被觸及？」
        touch_data = []
        approach_data = []  # 接近但沒碰到

        for td in trading_days:
            sr_levels = calc_sr_as_of(conn, td)
            if sr_levels is None:
                continue

            rows = conn.execute("""
                SELECT high, low, close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY timestamp
            """, [SYMBOL, td]).fetchall()
            if not rows:
                continue

            day_high = max(r[0] for r in rows)
            day_low = min(r[1] for r in rows)
            closes = [float(r[2]) for r in rows]

            for sr in sr_levels:
                p = sr["price"]
                # 只看當日價格範圍內 ±200 的 S/R
                if p < day_low - 200 or p > day_high + 200:
                    continue

                # 計算價格與 S/R 的最近距離
                min_dist = min(
                    min(abs(r[0] - p) for r in rows),  # high
                    min(abs(r[1] - p) for r in rows),  # low
                )
                touched = any(
                    r[1] <= p + 30 and r[0] >= p - 30 for r in rows
                )
                # 接近 = 進入 100 點範圍
                approached = any(
                    r[1] <= p + 100 and r[0] >= p - 100 for r in rows
                )

                touch_data.append({
                    "trade_date": td,
                    "sr_price": p,
                    "sr_type": sr["type"],
                    "strength": sr["strength"],
                    "min_dist": float(min_dist),
                    "touched": touched,
                    "approached": approached,
                    "in_range": day_low - 200 <= p <= day_high + 200,
                })

        df = pd.DataFrame(touch_data)
        print(f"\n觀察的 S/R-日 配對數: {len(df)}")

        # --- 分析：strength vs 觸及率 ---
        print(f"\n{'='*60}")
        print(f"分析 1：S/R strength vs 觸及率")
        print(f"{'='*60}")
        print(f"（假設：強 S/R 越不容易被碰到）\n")

        df["strength_group"] = pd.cut(
            df["strength"], bins=[0, 1, 2, 3, 100],
            labels=["1", "2", "3", "4+"]
        )

        for grp, sub in df.groupby("strength_group", observed=True):
            n = len(sub)
            touch_rate = sub["touched"].mean()
            approach_rate = sub["approached"].mean()
            avg_dist = sub["min_dist"].mean()
            print(f"  strength={grp}: 觸及率={touch_rate:.1%}, "
                  f"接近率(100pt)={approach_rate:.1%}, "
                  f"平均最近距離={avg_dist:.0f}點 (N={n})")

        # 相關性
        corr, p_val = stats.spearmanr(df["strength"], df["min_dist"])
        print(f"\n  Spearman 相關 (strength vs min_dist): r={corr:.3f}, p={p_val:.4f}")

        corr2, p_val2 = stats.pointbiserialr(df["touched"].astype(int), df["strength"])
        print(f"  Point-biserial (touched vs strength): r={corr2:.3f}, p={p_val2:.4f}")

        # --- 分析 2：日內價格走到 S/R 附近的行為 ---
        print(f"\n{'='*60}")
        print(f"分析 2：價格接近 S/R 時的行為")
        print(f"{'='*60}")
        print(f"（只看「接近但沒碰到」的 case，是否轉向？）\n")

        approached_not_touched = df[(df["approached"]) & (~df["touched"])]
        total_approached = df[df["approached"]]
        print(f"  接近(100pt) S/R 的次數: {len(total_approached)}")
        print(f"  接近但沒碰到(30pt)的次數: {len(approached_not_touched)}")
        if len(total_approached) > 0:
            repulsion_rate = len(approached_not_touched) / len(total_approached)
            print(f"  排斥率（接近但沒碰到）: {repulsion_rate:.1%}")

        # 按 strength 分組
        for grp, sub in total_approached.groupby("strength_group", observed=True):
            not_touched = sub[~sub["touched"]]
            rate = len(not_touched) / len(sub) if len(sub) > 0 else 0
            print(f"  strength={grp}: 排斥率={rate:.1%} (N={len(sub)})")

        # --- 分析 3：當日振幅是否受 S/R 限制 ---
        print(f"\n{'='*60}")
        print(f"分析 3：S/R 是否限制當日振幅？")
        print(f"{'='*60}")
        print(f"（比較 S/R 密集區 vs 稀疏區的價格穿越率）\n")

        # 每日計算：最近的上方壓力 & 下方支撐距開盤的距離，vs 實際振幅
        range_data = []
        for td in trading_days:
            sr_levels = calc_sr_as_of(conn, td)
            if sr_levels is None:
                continue

            rows = conn.execute("""
                SELECT
                    FIRST(open ORDER BY timestamp) AS day_open,
                    MAX(high) AS day_high,
                    MIN(low) AS day_low
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            """, [SYMBOL, td]).fetchone()
            if not rows or rows[0] is None:
                continue

            day_open, day_high, day_low = float(rows[0]), float(rows[1]), float(rows[2])

            # 開盤上方最近的壓力
            above = [sr["price"] for sr in sr_levels if sr["price"] > day_open]
            below = [sr["price"] for sr in sr_levels if sr["price"] < day_open]

            nearest_above = min(above) if above else None
            nearest_below = max(below) if below else None

            if nearest_above and nearest_below:
                range_data.append({
                    "trade_date": td,
                    "day_open": day_open,
                    "day_high": day_high,
                    "day_low": day_low,
                    "nearest_res": nearest_above,
                    "nearest_sup": nearest_below,
                    "broke_res": day_high > nearest_above,
                    "broke_sup": day_low < nearest_below,
                    "dist_to_res": nearest_above - day_open,
                    "dist_to_sup": day_open - nearest_below,
                })

        rdf = pd.DataFrame(range_data)
        if not rdf.empty:
            print(f"  有效交易日: {len(rdf)}")
            print(f"  突破上方壓力: {rdf['broke_res'].mean():.1%} ({rdf['broke_res'].sum()}/{len(rdf)})")
            print(f"  跌破下方支撐: {rdf['broke_sup'].mean():.1%} ({rdf['broke_sup'].sum()}/{len(rdf)})")
            print(f"  兩邊都沒破:   {((~rdf['broke_res']) & (~rdf['broke_sup'])).mean():.1%}")
            print(f"  兩邊都破:     {((rdf['broke_res']) & (rdf['broke_sup'])).mean():.1%}")

            # 跟隨機比較：如果 S/R 有效，突破率應低於「距離相同的隨機價位」
            # 簡單估算：用當日振幅 vs S/R 距離
            rdf["actual_range"] = rdf["day_high"] - rdf["day_low"]
            rdf["sr_range"] = rdf["nearest_res"] - rdf["nearest_sup"]
            rdf["contained"] = rdf["actual_range"] <= rdf["sr_range"]
            print(f"\n  S/R 框住振幅（actual_range ≤ sr_range）: "
                  f"{rdf['contained'].mean():.1%} ({rdf['contained'].sum()}/{len(rdf)})")
            print(f"  平均日振幅: {rdf['actual_range'].mean():.0f} 點")
            print(f"  平均 S/R 間距: {rdf['sr_range'].mean():.0f} 點")


if __name__ == "__main__":
    main()

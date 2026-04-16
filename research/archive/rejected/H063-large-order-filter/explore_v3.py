"""
H063 V3 探索：年度動態 P99 + 大單行為研究

研究方向：
1. 用每年的 P99 作動態大單門檻（解決保證金隨指數上調的問題）
2. P99 大單的行為分析：
   - 出現時間分佈
   - 出現時相對當日 high/low 的位置
   - 後續 N 分鐘的價格方向性（報酬分佈）
   - 集中 burst（多筆 P99 tick 連發）後的走勢
3. 作為濾網 vs 作為信號 兩個角度
"""

from datetime import time as dt_time, datetime, timedelta
import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"


def get_yearly_p99():
    """取得每年 P99 門檻"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                EXTRACT(YEAR FROM trade_date)::INT as year,
                quantile_cont(volume, 0.99)::INT as p99,
                quantile_cont(volume, 0.995)::INT as p995,
                quantile_cont(volume, 0.999)::INT as p999
            FROM ticks
            WHERE symbol='TX' AND NOT is_auction
              AND trade_time BETWEEN TIME '08:46:00' AND TIME '13:44:00'
            GROUP BY year
            ORDER BY year
        """).fetchdf()
    return df.set_index("year").to_dict("index")


def load_large_ticks(p99_by_year):
    """撈所有 P99 及以上的 tick"""
    # 用每年的 P99 當動態門檻（取 SQL CASE）
    conditions = []
    for year, v in p99_by_year.items():
        conditions.append(f"(EXTRACT(YEAR FROM trade_date) = {year} AND volume >= {v['p99']})")
    case_clause = " OR ".join(conditions)

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute(f"""
            SELECT trade_date, trade_time, price, volume
            FROM ticks
            WHERE symbol='TX' AND NOT is_auction
              AND trade_time BETWEEN TIME '08:46:00' AND TIME '13:44:00'
              AND ({case_clause})
            ORDER BY trade_date, trade_time
        """).fetchdf()
    df["year"] = pd.to_datetime(df["trade_date"]).dt.year
    return df


def load_1m_for_context():
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
    return df


def analyze_position(large_ticks, df_1m):
    """對每筆 P99 tick，計算：
    - 相對當日 session high/low 的位置（0-1）
    - 相對當日 rolling high/low 的位置
    - 後續 N 分鐘報酬
    """
    print("Computing day session high/low...")
    day_hl = df_1m.groupby("date").agg(
        day_high=("high", "max"), day_low=("low", "min")
    ).reset_index()
    day_hl["date"] = pd.to_datetime(day_hl["date"]).dt.date

    # Rolling high/low: 計算每個時點「到當下為止」的 session high/low
    df_1m_sorted = df_1m.sort_values("timestamp").copy()
    df_1m_sorted["rolling_high"] = df_1m_sorted.groupby("date")["high"].cummax()
    df_1m_sorted["rolling_low"] = df_1m_sorted.groupby("date")["low"].cummin()

    # 對每筆 large tick 找對應的 1 分 K
    large_ticks = large_ticks.copy()
    large_ticks["date"] = pd.to_datetime(large_ticks["trade_date"]).dt.date
    large_ticks["minute"] = large_ticks["trade_time"].apply(
        lambda t: t.replace(second=0)
    )
    large_ticks["timestamp"] = pd.to_datetime(
        large_ticks["date"].astype(str) + " " + large_ticks["minute"].astype(str)
    )

    # Merge with day high/low
    large_ticks = large_ticks.merge(day_hl, on="date", how="left")
    # Position 0-1（0=day low, 1=day high）
    span = large_ticks["day_high"] - large_ticks["day_low"]
    large_ticks["pos_in_day"] = np.where(
        span > 0, (large_ticks["price"] - large_ticks["day_low"]) / span, 0.5
    )

    # Merge with rolling high/low via timestamp
    ctx = df_1m_sorted[["timestamp", "rolling_high", "rolling_low", "close"]]
    large_ticks = large_ticks.merge(ctx, on="timestamp", how="left")
    span_r = large_ticks["rolling_high"] - large_ticks["rolling_low"]
    large_ticks["pos_in_rolling"] = np.where(
        span_r > 0, (large_ticks["price"] - large_ticks["rolling_low"]) / span_r, 0.5
    )

    # 後續 N 分鐘報酬（向量化用 asof merge）
    print("Computing forward returns via vectorized asof merge...")
    forward_minutes = [5, 15, 30, 60]
    bars_for_merge = df_1m_sorted[["timestamp", "close", "date"]].sort_values("timestamp").copy()

    large_ticks = large_ticks.sort_values("timestamp").reset_index(drop=True)
    large_ticks["_row_id"] = np.arange(len(large_ticks))

    for fm in forward_minutes:
        target = large_ticks[["_row_id", "timestamp", "date", "price"]].copy()
        target["target_ts"] = target["timestamp"] + pd.Timedelta(minutes=fm)
        target = target.sort_values("target_ts").reset_index(drop=True)

        merged = pd.merge_asof(
            target, bars_for_merge,
            left_on="target_ts", right_on="timestamp",
            direction="forward", by="date",
            suffixes=("", "_bar"),
        )
        merged[f"fwd_{fm}m"] = merged["close"] - merged["price"]
        # 用 _row_id map 回原順序
        fwd_map = merged.set_index("_row_id")[f"fwd_{fm}m"]
        large_ticks[f"fwd_{fm}m"] = large_ticks["_row_id"].map(fwd_map)

    large_ticks = large_ticks.drop(columns=["_row_id"])
    return large_ticks


def summarize_position(large_ticks, pos_col="pos_in_rolling", label_desc="rolling"):
    """
    pos_col: 'pos_in_rolling' (合法實時資訊) 或 'pos_in_day' (事後資訊，有偷看未來)
    """
    print("\n" + "=" * 75)
    print(f"  P99 大單出現位置分佈（相對 {label_desc} high/low）")
    print("=" * 75)
    print(f"總 P99 tick 數：{len(large_ticks):,}")

    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    bin_labels = ["0-10%", "10-20%", "20-30%", "30-40%", "40-50%", "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"]
    bin_counts = pd.cut(large_ticks[pos_col], bins=bins, labels=bin_labels, include_lowest=True).value_counts().sort_index()

    print(f"\n  {pos_col}（0={label_desc}低點, 1={label_desc}高點）")
    for blabel, count in bin_counts.items():
        pct = count / len(large_ticks) * 100
        bar = "#" * int(pct)
        print(f"    {blabel:8s}: {count:>6} ({pct:>5.1f}%) {bar}")

    print(f"\n  各位置區間的後續 15 分鐘平均報酬（{label_desc}）：")
    large_ticks["_pos_bin"] = pd.cut(large_ticks[pos_col], bins=bins, labels=bin_labels, include_lowest=True)
    for blabel in bin_labels:
        sub = large_ticks[large_ticks["_pos_bin"] == blabel]
        if len(sub) == 0:
            continue
        fwd = sub["fwd_15m"].dropna()
        if len(fwd) == 0:
            continue
        print(f"    {blabel:8s}: N={len(fwd):>5}  mean={fwd.mean():+6.2f}  median={fwd.median():+6.2f}  "
              f"↑%={(fwd > 0).sum() / len(fwd) * 100:>5.1f}%")


def summarize_forward_returns(large_ticks):
    print("\n" + "=" * 75)
    print("  P99 大單出現後的後續報酬分佈")
    print("=" * 75)
    for fm in [5, 15, 30, 60]:
        col = f"fwd_{fm}m"
        fwd = large_ticks[col].dropna()
        if len(fwd) == 0:
            continue
        up = (fwd > 0).sum()
        down = (fwd < 0).sum()
        flat = (fwd == 0).sum()
        print(f"\n  +{fm} 分鐘後 (N={len(fwd):,})")
        print(f"    上漲 {up} ({up/len(fwd)*100:.1f}%) / 下跌 {down} ({down/len(fwd)*100:.1f}%) / 平 {flat}")
        print(f"    mean={fwd.mean():+.2f}  median={fwd.median():+.2f}  std={fwd.std():.2f}")
        print(f"    P10={fwd.quantile(0.1):+.0f}  P90={fwd.quantile(0.9):+.0f}")


def analyze_reversal_zones(large_ticks, pos_col="pos_in_rolling", label_desc="rolling"):
    print("\n" + "=" * 75)
    print(f"  反轉分析：P99 大單出現在極端位置後的走勢（{label_desc}）")
    print("=" * 75)

    zones = [
        ("< 10% (低點區)", (0, 0.10)),
        ("10-20%", (0.10, 0.20)),
        ("20-80% (中段)", (0.20, 0.80)),
        ("80-90%", (0.80, 0.90)),
        ("> 90% (高點區)", (0.90, 1.01)),
    ]

    for zone_label, (lo, hi) in zones:
        sub = large_ticks[(large_ticks[pos_col] >= lo) & (large_ticks[pos_col] < hi)]
        if len(sub) == 0:
            continue
        print(f"\n  {zone_label}  N={len(sub):,}")
        for fm in [5, 15, 30, 60]:
            fwd = sub[f"fwd_{fm}m"].dropna()
            if len(fwd) == 0:
                continue
            up = (fwd > 0).sum() / len(fwd) * 100
            print(f"    +{fm}m: mean={fwd.mean():+6.2f}  median={fwd.median():+6.2f}  ↑%={up:>5.1f}%")


def analyze_cluster_bursts(large_ticks, df_1m):
    """同一分鐘內出現 ≥ N 筆 P99 tick 的事件"""
    print("\n" + "=" * 75)
    print("  Cluster burst：同分鐘多筆 P99 tick 集中出現")
    print("=" * 75)

    # 按 date+minute 分組
    large_ticks["minute_key"] = large_ticks["date"].astype(str) + " " + large_ticks["minute"].astype(str)
    clusters = large_ticks.groupby(["date", "minute", "timestamp"]).size().reset_index(name="count")

    print("\n  每分鐘 P99 tick 筆數分佈：")
    print(clusters["count"].value_counts().sort_index().head(15).to_string())

    # Cluster 事件 (>= 3 筆) 的後續報酬
    print("\n  同分鐘 ≥ N 筆 P99 tick 的後續報酬：")
    df_indexed = df_1m.set_index("timestamp")

    for min_count in [2, 3, 5, 10]:
        evts = clusters[clusters["count"] >= min_count]
        if len(evts) == 0:
            continue
        forward_list = []
        for _, evt in evts.iterrows():
            ts = evt["timestamp"]
            date = evt["date"]
            day_bars = df_indexed[df_indexed.index.date == date]
            if day_bars.empty:
                continue
            base_bar = day_bars.loc[day_bars.index == ts]
            if base_bar.empty:
                continue
            base_price = base_bar.iloc[0]["close"]
            target = ts + pd.Timedelta(minutes=15)
            fut = day_bars[day_bars.index >= target]
            if fut.empty:
                continue
            fut_price = fut.iloc[0]["close"]
            forward_list.append(fut_price - base_price)

        if not forward_list:
            continue
        arr = np.array(forward_list)
        up = (arr > 0).sum()
        print(f"    cluster≥{min_count}:  N={len(arr):>4}  mean={arr.mean():+6.2f}  "
              f"median={np.median(arr):+6.2f}  ↑%={up/len(arr)*100:>5.1f}%")


def main():
    print("=" * 75)
    print("  H063 V3: 年度動態 P99 + 大單行為研究")
    print("=" * 75)

    p99 = get_yearly_p99()
    print("\n各年度門檻：")
    print(f"  {'Year':>6} {'P99':>6} {'P99.5':>7} {'P99.9':>7}")
    for year, v in p99.items():
        print(f"  {year:>6} {v['p99']:>6} {v['p995']:>7} {v['p999']:>7}")

    print("\nLoading P99+ large ticks...")
    large_ticks = load_large_ticks(p99)
    print(f"Total P99+ ticks: {len(large_ticks):,}")
    print(f"By year:")
    print(large_ticks.groupby("year").size().to_string())

    print("\nLoading 1-min context data...")
    df_1m = load_1m_for_context()

    print("\nAnalyzing position and forward returns...")
    large_ticks = analyze_position(large_ticks, df_1m)

    # 加過濾：要求到當下已經累積足夠 bars（例如 9:00 後），rolling 才有意義
    print(f"\nBefore time filter: {len(large_ticks):,}")
    ticks_filtered = large_ticks[large_ticks["timestamp"].dt.time >= dt_time(9, 0)].copy()
    print(f"After time >= 09:00 filter: {len(ticks_filtered):,}")

    # 要求 rolling range 至少 5 點（避免開盤第一分鐘 high=low 造成 pos=0/1 極端值）
    rolling_span = ticks_filtered["rolling_high"] - ticks_filtered["rolling_low"]
    ticks_filtered = ticks_filtered[rolling_span >= 5].copy()
    print(f"After rolling range >= 5 filter: {len(ticks_filtered):,}")

    print("\n" + "#" * 75)
    print("  用 pos_in_rolling（合法實時資訊）")
    print("#" * 75)
    summarize_position(ticks_filtered, pos_col="pos_in_rolling", label_desc="rolling")
    analyze_reversal_zones(ticks_filtered, pos_col="pos_in_rolling", label_desc="rolling")

    print("\n" + "#" * 75)
    print("  用 pos_in_day（事後資訊，有偷看未來，對照用）")
    print("#" * 75)
    summarize_position(ticks_filtered, pos_col="pos_in_day", label_desc="當日")
    analyze_reversal_zones(ticks_filtered, pos_col="pos_in_day", label_desc="當日")

    summarize_forward_returns(ticks_filtered)
    # 跳過 cluster_bursts，那段 loop 太慢
    # analyze_cluster_bursts(large_ticks, df_1m)

    # 存檔
    large_ticks.to_csv("research/active/H063-large-order-filter/p99_ticks_analysis.csv", index=False)
    print("\nSaved: p99_ticks_analysis.csv")


if __name__ == "__main__":
    main()

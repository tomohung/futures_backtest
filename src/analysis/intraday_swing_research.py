"""日內波段交易研究：波動預測與時段分析

回答 7 個核心問題：
  Q1: 波動集中時段（邊際波幅佔比）
  Q2: 當日高低點時間分佈
  Q3: 剩餘波幅分析（目標價設定依據）
  Q4: MAE 分析（停損與部位分配依據）
  Q5: 波動消耗後行為（EstHL 整合）
  Q6: 停損後再進場可行性
  Q7: 加碼分析（新高事件序列）

用法:
    uv run python src/analysis/intraday_swing_research.py
    uv run python src/analysis/intraday_swing_research.py --question 1
    uv run python src/analysis/intraday_swing_research.py --question 1 2 3
"""

import argparse
import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DB_PATH = "data/futures.duckdb"

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

# 30-min time bucket boundaries
BUCKETS_30M = [
    dtime(8, 45), dtime(9, 15), dtime(9, 45), dtime(10, 15),
    dtime(10, 45), dtime(11, 15), dtime(11, 45), dtime(12, 15),
    dtime(12, 45), dtime(13, 15),
]

BUCKET_LABELS = [
    "08:45-09:14", "09:15-09:44", "09:45-10:14", "10:15-10:44",
    "10:45-11:14", "11:15-11:44", "11:45-12:14", "12:15-12:44",
    "12:45-13:14", "13:15-13:45",
]


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def _bucket_idx(t: dtime) -> int:
    for i in range(len(BUCKETS_30M) - 1, -1, -1):
        if t >= BUCKETS_30M[i]:
            return i
    return 0


# ── Data loading ──────────────────────────────────────────────────────────────

def load_minute_bars() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    return df


def load_daily_summary() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MIN_BY(open, timestamp) AS day_open,
                MAX(high) AS day_high,
                MIN(low) AS day_low,
                MAX_BY(close, timestamp) AS day_close,
                SUM(volume) AS day_volume,
                MAX(high) - MIN(low) AS day_range,
                ARG_MAX(timestamp, high)::TIME AS high_time,
                ARG_MIN(timestamp, low)::TIME AS low_time
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            GROUP BY 1
            ORDER BY 1
        """).fetchdf()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["day_range_pct"] = df["day_range"] / df["day_open"] * 100
    df["year"] = df["trade_date"].dt.year
    df["direction"] = np.where(df["day_close"] > df["day_open"], "up", "down")
    return df


# ── Q1: 波動集中時段 ─────────────────────────────────────────────────────────

def analyze_volatility_concentration(df_bars: pd.DataFrame, df_daily: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q1: 波動集中時段 — 各 30 分鐘時段的邊際波幅佔比")
    print("=" * 72)

    dates = sorted(df_bars["date"].unique())
    n_buckets = len(BUCKETS_30M)

    # Per-day, per-bucket: cumulative range at bucket end
    records = []
    for date in dates:
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        run_low = np.inf
        bucket_ranges = []
        prev_range = 0.0

        for bi in range(n_buckets):
            bucket_start = BUCKETS_30M[bi]
            bucket_end = BUCKETS_30M[bi + 1] if bi + 1 < n_buckets else dtime(13, 46)
            mask = (day["time"] >= bucket_start) & (day["time"] < bucket_end)
            bucket_bars = day[mask]

            for _, row in bucket_bars.iterrows():
                run_high = max(run_high, row["high"])
                run_low = min(run_low, row["low"])

            cur_range = run_high - run_low if run_high > -np.inf else 0
            marginal = cur_range - prev_range
            bucket_ranges.append(marginal)
            prev_range = cur_range

        day_range = prev_range
        if day_range <= 0:
            continue

        record = {"date": date}
        for bi in range(n_buckets):
            record[f"marginal_{bi}"] = bucket_ranges[bi]
            record[f"marginal_pct_{bi}"] = bucket_ranges[bi] / day_range * 100
        record["day_range"] = day_range
        records.append(record)

    rdf = pd.DataFrame(records)
    rdf["year"] = pd.to_datetime(rdf["date"]).dt.year

    # Summary table
    print(f"\n  全期 {len(rdf)} 交易日")
    print(f"  {'時段':<14} {'mean%':>7} {'median%':>8} {'std%':>7} {'累積%':>7}")
    print(f"  {'-'*14} {'-'*7} {'-'*8} {'-'*7} {'-'*7}")
    cum = 0.0
    for bi in range(n_buckets):
        col = f"marginal_pct_{bi}"
        m = rdf[col].mean()
        med = rdf[col].median()
        s = rdf[col].std()
        cum += m
        print(f"  {BUCKET_LABELS[bi]:<14} {m:>7.1f} {med:>8.1f} {s:>7.1f} {cum:>7.1f}")

    # Year-by-year: top 3 buckets
    print(f"\n  逐年穩定性（各年度佔比最高的前 3 個時段）")
    print(f"  {'Year':<6}", end="")
    for bi in range(n_buckets):
        print(f" {BUCKET_LABELS[bi][-5:]:>6}", end="")
    print()
    print(f"  {'-'*6}", end="")
    for _ in range(n_buckets):
        print(f" {'-'*6}", end="")
    print()
    for yr, _, _ in YEARS:
        yr_data = rdf[rdf["year"] == int(yr)]
        if yr_data.empty:
            continue
        print(f"  {yr:<6}", end="")
        for bi in range(n_buckets):
            v = yr_data[f"marginal_pct_{bi}"].mean()
            print(f" {v:>5.1f}%", end="")
        print()


# ── Q2: 當日高低點時間分佈 ───────────────────────────────────────────────────

def analyze_hl_timing(df_daily: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q2: 當日高低點時間分佈")
    print("=" * 72)

    df = df_daily.copy()
    df["high_bucket"] = df["high_time"].apply(_bucket_idx)
    df["low_bucket"] = df["low_time"].apply(_bucket_idx)
    df["high_first"] = df["high_time"] < df["low_time"]

    def _print_dist(subset, label):
        n = len(subset)
        print(f"\n  [{label}] n={n}")
        print(f"  {'時段':<14} {'高點n':>6} {'高點%':>7} {'低點n':>6} {'低點%':>7}")
        print(f"  {'-'*14} {'-'*6} {'-'*7} {'-'*6} {'-'*7}")
        for bi in range(len(BUCKETS_30M)):
            h_cnt = (subset["high_bucket"] == bi).sum()
            l_cnt = (subset["low_bucket"] == bi).sum()
            h_pct = h_cnt / n * 100
            l_pct = l_cnt / n * 100
            print(f"  {BUCKET_LABELS[bi]:<14} {h_cnt:>6} {h_pct:>6.1f}% {l_cnt:>6} {l_pct:>6.1f}%")

    _print_dist(df, "全部")
    _print_dist(df[df["direction"] == "up"], "上漲日 (close > open)")
    _print_dist(df[df["direction"] == "down"], "下跌日 (close < open)")

    # High first vs low first
    print(f"\n  高低點先後順序:")
    hf = df["high_first"].sum()
    lf = len(df) - hf
    print(f"  全部:   高點先出現 {hf} ({hf/len(df)*100:.1f}%)  低點先出現 {lf} ({lf/len(df)*100:.1f}%)")
    for dir_label in ["up", "down"]:
        sub = df[df["direction"] == dir_label]
        hf_s = sub["high_first"].sum()
        lf_s = len(sub) - hf_s
        chn = "上漲日" if dir_label == "up" else "下跌日"
        print(f"  {chn}: 高點先出現 {hf_s} ({hf_s/len(sub)*100:.1f}%)  低點先出現 {lf_s} ({lf_s/len(sub)*100:.1f}%)")

    # Year-by-year stability
    print(f"\n  逐年: 高點先出現比例")
    print(f"  {'Year':<6} {'n':>6} {'高先%':>7} {'上漲日高先%':>12} {'下跌日高先%':>12}")
    print(f"  {'-'*6} {'-'*6} {'-'*7} {'-'*12} {'-'*12}")
    for yr, _, _ in YEARS:
        yr_data = df[df["year"] == int(yr)]
        if yr_data.empty:
            continue
        n = len(yr_data)
        hf_all = yr_data["high_first"].mean() * 100
        up_sub = yr_data[yr_data["direction"] == "up"]
        dn_sub = yr_data[yr_data["direction"] == "down"]
        hf_up = up_sub["high_first"].mean() * 100 if len(up_sub) else float("nan")
        hf_dn = dn_sub["high_first"].mean() * 100 if len(dn_sub) else float("nan")
        print(f"  {yr:<6} {n:>6} {hf_all:>6.1f}% {fv(hf_up, 11):>11}% {fv(hf_dn, 11):>11}%")


# ── Q3: 剩餘波幅分析 ─────────────────────────────────────────────────────────

def analyze_remaining_range(df_bars: pd.DataFrame, df_daily: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q3: 剩餘波幅分析 — 各時間點的剩餘上行/下行空間")
    print("=" * 72)

    daily_map = df_daily.set_index("trade_date")[
        ["day_high", "day_low", "day_open", "high_time", "low_time"]
    ].to_dict("index")

    # Checkpoints every 30 min
    checkpoints = BUCKETS_30M

    dates = sorted(df_bars["date"].unique())
    records = []

    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        info = daily_map[td]
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        run_low = np.inf
        cp_idx = 0

        for _, row in day.iterrows():
            run_high = max(run_high, row["high"])
            run_low = min(run_low, row["low"])

            # Check if we've passed a checkpoint
            while cp_idx < len(checkpoints) and row["time"] >= checkpoints[cp_idx]:
                if cp_idx > 0:  # skip 08:45 (no data yet)
                    remaining_up = info["day_high"] - run_high
                    remaining_dn = run_low - info["day_low"]
                    low_is_in = info["low_time"] <= checkpoints[cp_idx]
                    high_is_in = info["high_time"] <= checkpoints[cp_idx]
                    records.append({
                        "date": date,
                        "checkpoint": checkpoints[cp_idx],
                        "cp_idx": cp_idx,
                        "remaining_up": remaining_up,
                        "remaining_dn": remaining_dn,
                        "remaining_up_pct": remaining_up / info["day_open"] * 100,
                        "remaining_dn_pct": remaining_dn / info["day_open"] * 100,
                        "low_is_in": low_is_in,
                        "high_is_in": high_is_in,
                        "day_open": info["day_open"],
                    })
                cp_idx += 1

    rdf = pd.DataFrame(records)

    print(f"\n  全期 {rdf['date'].nunique()} 交易日")
    print(f"\n  {'Checkpoint':<11} {'P(低已出)':>9} {'P(高已出)':>9}"
          f" {'剩餘上行%':>9} {'(p25)':>6} {'(p75)':>6}"
          f" {'剩餘下行%':>9} {'(p25)':>6} {'(p75)':>6}")
    print(f"  {'-'*11} {'-'*9} {'-'*9} {'-'*9} {'-'*6} {'-'*6} {'-'*9} {'-'*6} {'-'*6}")

    for cp_idx in range(1, len(checkpoints)):
        cp = checkpoints[cp_idx]
        sub = rdf[rdf["cp_idx"] == cp_idx]
        if sub.empty:
            continue

        p_low_in = sub["low_is_in"].mean() * 100
        p_high_in = sub["high_is_in"].mean() * 100
        up_mean = sub["remaining_up_pct"].mean()
        up_p25 = sub["remaining_up_pct"].quantile(0.25)
        up_p75 = sub["remaining_up_pct"].quantile(0.75)
        dn_mean = sub["remaining_dn_pct"].mean()
        dn_p25 = sub["remaining_dn_pct"].quantile(0.25)
        dn_p75 = sub["remaining_dn_pct"].quantile(0.75)

        print(f"  {str(cp):<11} {p_low_in:>8.1f}% {p_high_in:>8.1f}%"
              f" {up_mean:>9.3f} {up_p25:>6.3f} {up_p75:>6.3f}"
              f" {dn_mean:>9.3f} {dn_p25:>6.3f} {dn_p75:>6.3f}")

    # Conditional: given low IS already in, remaining upside
    print(f"\n  條件分析：低點已出現時的剩餘上行空間")
    print(f"  {'Checkpoint':<11} {'n(低已出)':>9} {'cond上行%':>9} {'(p25)':>6} {'(p75)':>6}")
    print(f"  {'-'*11} {'-'*9} {'-'*9} {'-'*6} {'-'*6}")
    for cp_idx in range(1, len(checkpoints)):
        cp = checkpoints[cp_idx]
        sub = rdf[(rdf["cp_idx"] == cp_idx) & rdf["low_is_in"]]
        if len(sub) < 10:
            continue
        print(f"  {str(cp):<11} {len(sub):>9}"
              f" {sub['remaining_up_pct'].mean():>9.3f}"
              f" {sub['remaining_up_pct'].quantile(0.25):>6.3f}"
              f" {sub['remaining_up_pct'].quantile(0.75):>6.3f}")


# ── Q4: MAE 分析 ─────────────────────────────────────────────────────────────

def analyze_adverse_excursion(df_bars: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q4: MAE 分析 — 各時間點做多後的最大逆向波動")
    print("=" * 72)

    # Checkpoints for hypothetical entry
    entry_times = [dtime(9, 0), dtime(9, 15), dtime(9, 30), dtime(9, 45),
                   dtime(10, 0), dtime(10, 30), dtime(11, 0), dtime(11, 30),
                   dtime(12, 0)]

    dates = sorted(df_bars["date"].unique())
    records = []

    for date in dates:
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        for et in entry_times:
            entry_bar = day[day["time"] == et]
            if entry_bar.empty:
                continue
            entry_price = entry_bar.iloc[0]["close"]
            after_entry = day[day["time"] > et]
            if after_entry.empty:
                continue

            min_low_after = after_entry["low"].min()
            max_high_after = after_entry["high"].max()
            mae_long = entry_price - min_low_after  # positive = adverse move for long
            mfe_long = max_high_after - entry_price  # positive = favorable move for long

            records.append({
                "date": date,
                "entry_time": et,
                "entry_price": entry_price,
                "mae_long": mae_long,
                "mae_long_pct": mae_long / entry_price * 100,
                "mfe_long": mfe_long,
                "mfe_long_pct": mfe_long / entry_price * 100,
            })

    rdf = pd.DataFrame(records)
    rdf["year"] = pd.to_datetime(rdf["date"]).dt.year

    print(f"\n  做多 MAE（進場後最低點距離進場價）")
    print(f"  {'Entry':>8} {'n':>6} {'mean%':>7} {'p50%':>7} {'p75%':>7} {'p95%':>7}"
          f" {'MFE mean%':>10}")
    print(f"  {'-'*8} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*10}")

    for et in entry_times:
        sub = rdf[rdf["entry_time"] == et]
        if sub.empty:
            continue
        mae = sub["mae_long_pct"]
        mfe = sub["mfe_long_pct"]
        print(f"  {str(et):<8} {len(sub):>6}"
              f" {mae.mean():>7.3f} {mae.median():>7.3f}"
              f" {mae.quantile(0.75):>7.3f} {mae.quantile(0.95):>7.3f}"
              f" {mfe.mean():>10.3f}")

    # MFE/MAE ratio (edge ratio)
    print(f"\n  Edge Ratio = MFE / MAE（>1 表示有利）")
    print(f"  {'Entry':>8} {'mean ratio':>11} {'median ratio':>13}")
    print(f"  {'-'*8} {'-'*11} {'-'*13}")
    for et in entry_times:
        sub = rdf[rdf["entry_time"] == et]
        if sub.empty:
            continue
        ratio = sub["mfe_long"] / (sub["mae_long"] + 0.01)
        print(f"  {str(et):<8} {ratio.mean():>11.2f} {ratio.median():>13.2f}")

    # Year-by-year for 09:15 entry
    print(f"\n  逐年 MAE%（09:15 進場做多）")
    print(f"  {'Year':<6} {'n':>5} {'mean%':>7} {'p50%':>7} {'p75%':>7} {'p95%':>7}")
    print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    sub_0915 = rdf[rdf["entry_time"] == dtime(9, 15)]
    for yr, _, _ in YEARS:
        yr_data = sub_0915[sub_0915["year"] == int(yr)]
        if yr_data.empty:
            continue
        mae = yr_data["mae_long_pct"]
        print(f"  {yr:<6} {len(yr_data):>5}"
              f" {mae.mean():>7.3f} {mae.median():>7.3f}"
              f" {mae.quantile(0.75):>7.3f} {mae.quantile(0.95):>7.3f}")


# ── Q5: 波動消耗後行為 ───────────────────────────────────────────────────────

def analyze_range_consumed(df_bars: pd.DataFrame, df_daily: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q5: 波動消耗後行為 — 當日波幅達預估值後的價格變動")
    print("=" * 72)

    from src.backtest.estimate_hl import compute_estimate_hl_zones

    # Prepare data for EstHL computation
    df_for_hl = df_bars[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df_for_hl = df_for_hl.set_index("timestamp")
    df_for_hl.columns = ["Open", "High", "Low", "Close", "Volume"]
    df_hl = compute_estimate_hl_zones(df_for_hl)

    # Get EmaHL per day (use first non-NaN value each day)
    df_hl["date"] = df_hl.index.date
    ema_hl_daily = df_hl.groupby("date")["EmaHL"].apply(
        lambda x: x.dropna().iloc[0] if x.notna().any() else np.nan
    )

    dates = sorted(df_bars["date"].unique())
    thresholds = [0.8, 1.0, 1.2, 1.5]

    records = []
    for date in dates:
        if date not in ema_hl_daily.index or np.isnan(ema_hl_daily[date]):
            continue
        est_hl = ema_hl_daily[date]
        if est_hl <= 0:
            continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        run_low = np.inf
        day_close = day.iloc[-1]["close"]

        triggered = {t: False for t in thresholds}

        for _, row in day.iterrows():
            run_high = max(run_high, row["high"])
            run_low = min(run_low, row["low"])
            cur_range = run_high - run_low
            consumed_pct = cur_range / est_hl

            for t in thresholds:
                if not triggered[t] and consumed_pct >= t:
                    triggered[t] = True
                    # Direction of consumption
                    open_price = day.iloc[0]["open"]
                    up_move = run_high - open_price
                    dn_move = open_price - run_low
                    direction = "up" if up_move >= dn_move else "down"

                    move_to_close = day_close - row["close"]
                    records.append({
                        "date": date,
                        "threshold": t,
                        "trigger_time": row["time"],
                        "consumed_direction": direction,
                        "price_at_trigger": row["close"],
                        "move_to_close": move_to_close,
                        "move_to_close_pct": move_to_close / row["close"] * 100,
                        "est_hl": est_hl,
                        "cur_range": cur_range,
                        "day_close": day_close,
                    })

    rdf = pd.DataFrame(records)
    total_days = df_daily.shape[0]

    print(f"\n  全期 {total_days} 交易日, EstHL 有效日 {len(ema_hl_daily.dropna())}")
    print(f"\n  {'門檻':>6} {'觸發天數':>8} {'觸發率%':>8} {'avg觸發時間':>12}"
          f" {'觸發後→收盤':>12} {'反轉率%':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*12} {'-'*12} {'-'*8}")

    for t in thresholds:
        sub = rdf[rdf["threshold"] == t]
        if sub.empty:
            print(f"  {t:>5.0%} {'0':>8}")
            continue

        n = len(sub)
        trigger_rate = n / total_days * 100

        # Convert trigger_time to minutes for averaging
        mins = sub["trigger_time"].apply(lambda x: x.hour * 60 + x.minute)
        avg_min = mins.mean()
        avg_time = f"{int(avg_min)//60:02d}:{int(avg_min)%60:02d}"

        avg_move = sub["move_to_close"].mean()

        # Reversal: if consumed upward, reversal = close < trigger price (i.e. move_to_close < 0)
        # if consumed downward, reversal = close > trigger price (move_to_close > 0)
        up_sub = sub[sub["consumed_direction"] == "up"]
        dn_sub = sub[sub["consumed_direction"] == "down"]
        up_rev = (up_sub["move_to_close"] < 0).sum() if len(up_sub) else 0
        dn_rev = (dn_sub["move_to_close"] > 0).sum() if len(dn_sub) else 0
        rev_rate = (up_rev + dn_rev) / n * 100

        print(f"  {t:>5.0%} {n:>8} {trigger_rate:>7.1f}% {avg_time:>12}"
              f" {avg_move:>+11.1f} {rev_rate:>7.1f}%")

    # Breakdown by consumed direction
    print(f"\n  方向分解（消耗方向 × 觸發後行為）")
    print(f"  {'門檻':>6} {'方向':>4} {'n':>5} {'觸發後→收盤':>12} {'反轉率%':>8}")
    print(f"  {'-'*6} {'-'*4} {'-'*5} {'-'*12} {'-'*8}")
    for t in thresholds:
        for d in ["up", "down"]:
            sub = rdf[(rdf["threshold"] == t) & (rdf["consumed_direction"] == d)]
            if len(sub) < 5:
                continue
            avg_move = sub["move_to_close"].mean()
            if d == "up":
                rev = (sub["move_to_close"] < 0).mean() * 100
            else:
                rev = (sub["move_to_close"] > 0).mean() * 100
            print(f"  {t:>5.0%} {d:>4} {len(sub):>5} {avg_move:>+11.1f} {rev:>7.1f}%")


# ── Q6: 停損後再進場 ─────────────────────────────────────────────────────────

def analyze_post_stop(df_bars: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q6: 停損後再進場 — 模擬做多停損後的價格行為")
    print("=" * 72)

    sl_levels = [0.003, 0.005, 0.007]  # 0.3%, 0.5%, 0.7%
    entry_time = dtime(9, 0)
    dates = sorted(df_bars["date"].unique())

    records = []
    for date in dates:
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        entry_bar = day[day["time"] == entry_time]
        if entry_bar.empty:
            continue
        entry_price = entry_bar.iloc[0]["close"]
        day_close = day.iloc[-1]["close"]

        for sl_pct in sl_levels:
            sl_price = entry_price * (1 - sl_pct)
            stopped = False
            stop_time = None
            stop_price = None

            after_entry = day[day["time"] > entry_time]
            for _, row in after_entry.iterrows():
                if row["low"] <= sl_price:
                    stopped = True
                    stop_time = row["time"]
                    stop_price = sl_price
                    break

            if stopped:
                # Measure what happens after stop
                after_stop = day[day["time"] > stop_time]
                if after_stop.empty:
                    continue

                max_high_after = after_stop["high"].max()
                recovery = max_high_after - stop_price
                close_vs_stop = day_close - stop_price
                close_vs_entry = day_close - entry_price

                early_stop = stop_time < dtime(10, 0)

                records.append({
                    "date": date,
                    "sl_pct": sl_pct,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "stop_time": stop_time,
                    "early_stop": early_stop,
                    "max_recovery": recovery,
                    "max_recovery_pct": recovery / entry_price * 100,
                    "close_vs_stop": close_vs_stop,
                    "close_vs_stop_pct": close_vs_stop / entry_price * 100,
                    "close_vs_entry": close_vs_entry,
                    "recovered_above_entry": day_close > entry_price,
                })

    rdf = pd.DataFrame(records)

    print(f"\n  模擬：09:00 做多進場，各 SL 水準的停損後行為")
    print(f"  {'SL%':>5} {'停損次數':>8} {'佔比%':>7}"
          f" {'回升>進場%':>10} {'收盤>停損%':>10}"
          f" {'avg 最大回升%':>13} {'avg 收盤vs停損%':>15}")
    print(f"  {'-'*5} {'-'*8} {'-'*7} {'-'*10} {'-'*10} {'-'*13} {'-'*15}")

    total_days = len(df_bars["date"].unique())
    for sl_pct in sl_levels:
        sub = rdf[rdf["sl_pct"] == sl_pct]
        if sub.empty:
            continue
        n = len(sub)
        pct_of_days = n / total_days * 100
        rec_above_entry = sub["recovered_above_entry"].mean() * 100
        close_above_stop = (sub["close_vs_stop"] > 0).mean() * 100
        avg_recovery = sub["max_recovery_pct"].mean()
        avg_close_vs_stop = sub["close_vs_stop_pct"].mean()

        print(f"  {sl_pct*100:>4.1f}% {n:>8} {pct_of_days:>6.1f}%"
              f" {rec_above_entry:>9.1f}% {close_above_stop:>9.1f}%"
              f" {avg_recovery:>12.3f}% {avg_close_vs_stop:>+14.3f}%")

    # Early vs late stop
    print(f"\n  早盤停損 (<10:00) vs 午盤停損 (>=10:00)")
    print(f"  {'SL%':>5} {'時段':>6} {'n':>5} {'回升>進場%':>10} {'收盤>停損%':>10} {'avg收盤vs停損%':>14}")
    print(f"  {'-'*5} {'-'*6} {'-'*5} {'-'*10} {'-'*10} {'-'*14}")
    for sl_pct in sl_levels:
        for early, label in [(True, "早盤"), (False, "午盤")]:
            sub = rdf[(rdf["sl_pct"] == sl_pct) & (rdf["early_stop"] == early)]
            if len(sub) < 5:
                continue
            rec = sub["recovered_above_entry"].mean() * 100
            close_up = (sub["close_vs_stop"] > 0).mean() * 100
            avg_cs = sub["close_vs_stop_pct"].mean()
            print(f"  {sl_pct*100:>4.1f}% {label:>6} {len(sub):>5}"
                  f" {rec:>9.1f}% {close_up:>9.1f}% {avg_cs:>+13.3f}%")


# ── Q7: 加碼分析 ─────────────────────────────────────────────────────────────

def analyze_sequential_breakouts(df_bars: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Q7: 加碼分析 — 新高事件序列的邊際收益")
    print("=" * 72)

    dates = sorted(df_bars["date"].unique())
    MIN_DELTA = 1.0  # 新高需超過前高至少 1 點

    all_events = []  # (date, event_n, time, price, day_high)

    for date in dates:
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        event_n = 0
        day_high = day["high"].max()
        day_open = day.iloc[0]["open"]
        day_close = day.iloc[-1]["close"]
        prev_event_time = None

        for _, row in day.iterrows():
            if row["high"] > run_high + MIN_DELTA:
                new_high = row["high"]
                event_n += 1

                interval = None
                if prev_event_time is not None:
                    t1 = prev_event_time.hour * 60 + prev_event_time.minute
                    t2 = row["time"].hour * 60 + row["time"].minute
                    interval = t2 - t1

                all_events.append({
                    "date": date,
                    "event_n": event_n,
                    "time": row["time"],
                    "price": new_high,
                    "day_high": day_high,
                    "day_open": day_open,
                    "day_close": day_close,
                    "remaining_up": day_high - new_high,
                    "remaining_up_pct": (day_high - new_high) / day_open * 100,
                    "interval_min": interval,
                })

                run_high = new_high
                prev_event_time = row["time"]
            else:
                run_high = max(run_high, row["high"])

    edf = pd.DataFrame(all_events)
    edf["year"] = pd.to_datetime(edf["date"]).dt.year

    # Distribution of total new-high events per day
    events_per_day = edf.groupby("date").size()
    print(f"\n  每日新高事件次數分佈（>前高至少 {MIN_DELTA} 點）")
    print(f"  mean={events_per_day.mean():.1f}  median={events_per_day.median():.0f}"
          f"  p25={events_per_day.quantile(0.25):.0f}  p75={events_per_day.quantile(0.75):.0f}"
          f"  max={events_per_day.max()}")

    # Marginal gain by event N
    print(f"\n  第 N 次新高後的邊際上行空間")
    print(f"  {'第N次':>6} {'出現天數':>8} {'出現率%':>8}"
          f" {'剩餘上行(pts)':>13} {'剩餘上行%':>10} {'avg間隔(分)':>11}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*13} {'-'*10} {'-'*11}")

    total_days = len(dates)
    for n in range(1, 21):
        sub = edf[edf["event_n"] == n]
        if len(sub) < 10:
            break
        n_days = len(sub)
        rate = n_days / total_days * 100
        rem_pts = sub["remaining_up"].mean()
        rem_pct = sub["remaining_up_pct"].mean()
        avg_interval = sub["interval_min"].dropna().mean() if n > 1 else float("nan")

        int_str = f"{avg_interval:>10.1f}" if not np.isnan(avg_interval) else "—".rjust(10)
        print(f"  {n:>6} {n_days:>8} {rate:>7.1f}%"
              f" {rem_pts:>13.1f} {rem_pct:>9.3f}% {int_str}")

    # Time distribution of new highs
    print(f"\n  新高事件的時段分佈")
    print(f"  {'時段':<14} {'events':>7} {'佔比%':>7} {'avg剩餘上行%':>13}")
    print(f"  {'-'*14} {'-'*7} {'-'*7} {'-'*13}")
    edf["bucket"] = edf["time"].apply(_bucket_idx)
    total_events = len(edf)
    for bi in range(len(BUCKETS_30M)):
        sub = edf[edf["bucket"] == bi]
        if sub.empty:
            continue
        pct = len(sub) / total_events * 100
        rem = sub["remaining_up_pct"].mean()
        print(f"  {BUCKET_LABELS[bi]:<14} {len(sub):>7} {pct:>6.1f}% {rem:>12.3f}%")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="日內波段交易研究")
    parser.add_argument("--question", "-q", nargs="*", type=int,
                        help="只跑指定的問題 (1-7)")
    args = parser.parse_args()

    questions = set(args.question) if args.question else set(range(1, 8))

    print("=" * 72)
    print("日內波段交易研究：波動預測與時段分析")
    print("=" * 72)

    print("\n載入資料中...", flush=True)
    df_bars = load_minute_bars()
    df_daily = load_daily_summary()
    print(f"  1 分 K: {len(df_bars):,} 筆, {df_bars['date'].nunique()} 交易日")
    print(f"  日期範圍: {df_bars['date'].min()} ~ {df_bars['date'].max()}")
    print(f"  日均波幅: {df_daily['day_range'].mean():.0f} pts"
          f" ({df_daily['day_range_pct'].mean():.2f}%)")

    if 1 in questions:
        analyze_volatility_concentration(df_bars, df_daily)
    if 2 in questions:
        analyze_hl_timing(df_daily)
    if 3 in questions:
        analyze_remaining_range(df_bars, df_daily)
    if 4 in questions:
        analyze_adverse_excursion(df_bars)
    if 5 in questions:
        analyze_range_consumed(df_bars, df_daily)
    if 6 in questions:
        analyze_post_stop(df_bars)
    if 7 in questions:
        analyze_sequential_breakouts(df_bars)

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()

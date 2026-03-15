"""EstHL × OR 量比調整研究

Step 0：OR 量比 vs 日波幅的量化關係
Step 1：調整公式測試（5 個候選公式 × 參數）
Step 2：SatZone 連動驗證 + Checkpoint 觸及率

用法:
    uv run python src/analysis/esthl_or_volume_adjust.py
"""

import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DB_PATH = "data/futures.duckdb"

YEARS = [
    ("2021", 2021), ("2022", 2022), ("2023", 2023),
    ("2024", 2024), ("2025", 2025), ("2026", 2026),
]


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_all_data():
    """Load daily OHLCV, OR features, and 1-min bars."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        # Daily summary
        df_daily = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MIN_BY(open, timestamp) AS day_open,
                MAX(high) AS day_high,
                MIN(low) AS day_low,
                MAX_BY(close, timestamp) AS day_close,
                SUM(volume) AS day_volume,
                MAX(high) - MIN(low) AS day_range
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            GROUP BY 1
            ORDER BY 1
        """).fetchdf()

        # OR features (08:45–09:30)
        df_or = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS or_width,
                SUM(volume) AS or_volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '09:30'
            GROUP BY 1
        """).fetchdf()

        # 1-min bars
        df_bars = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            ORDER BY timestamp
        """).fetchdf()

    df_daily["trade_date"] = pd.to_datetime(df_daily["trade_date"])
    df_or["trade_date"] = pd.to_datetime(df_or["trade_date"])

    df_daily = df_daily.set_index("trade_date").sort_index()
    df_or = df_or.set_index("trade_date").sort_index()

    # Merge OR features
    df_daily["or_width"] = df_or["or_width"]
    df_daily["or_volume"] = df_or["or_volume"]

    # OR volume ratio (no lookahead: use 20-day rolling of past OR volumes)
    df_daily["or_vol_20ma"] = df_daily["or_volume"].shift(1).rolling(20, min_periods=10).mean()
    df_daily["or_vol_ratio"] = df_daily["or_volume"] / df_daily["or_vol_20ma"]

    # EmaHL (simplified: EMA(20) of day_range, shift 1)
    alpha = 2.0 / 21
    hl = df_daily["day_range"].values
    n = len(df_daily)
    ema = np.full(n, np.nan)
    for i in range(n):
        if i == 0:
            ema[i] = hl[i]
        else:
            ema[i] = hl[i] * alpha + ema[i - 1] * (1 - alpha)
    df_daily["ema_hl"] = np.roll(ema, 1)
    df_daily.iloc[0, df_daily.columns.get_loc("ema_hl")] = np.nan

    df_daily["year"] = df_daily.index.year

    # 1-min bars
    df_bars["timestamp"] = pd.to_datetime(df_bars["timestamp"])
    df_bars["date"] = df_bars["timestamp"].dt.date
    df_bars["time"] = df_bars["timestamp"].dt.time

    return df_daily, df_bars


# ── Step 0: OR vol ratio vs day range ────────────────────────────────────────

def step0_correlation(df: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Step 0：OR 量比 vs 日波幅的量化關係")
    print("=" * 72)

    valid = df[df["or_vol_ratio"].notna() & df["ema_hl"].notna()].copy()
    print(f"\n  有效交易日：{len(valid)}")

    # Basic correlations
    r_range = valid["or_vol_ratio"].corr(valid["day_range"])
    r_rank = valid["or_vol_ratio"].rank().corr(valid["day_range"].rank())
    print(f"\n  OR 量比 vs 日波幅：")
    print(f"    Pearson  r = {r_range:+.3f}")
    print(f"    Spearman r = {r_rank:+.3f}")

    # vs deviation from EmaHL
    valid["range_ratio"] = valid["day_range"] / valid["ema_hl"]
    r_dev = valid["or_vol_ratio"].corr(valid["range_ratio"])
    r_dev_rank = valid["or_vol_ratio"].rank().corr(valid["range_ratio"].rank())
    print(f"\n  OR 量比 vs (日波幅 / EmaHL)：")
    print(f"    Pearson  r = {r_dev:+.3f}")
    print(f"    Spearman r = {r_dev_rank:+.3f}")

    # Quintile analysis
    valid["q"] = pd.qcut(valid["or_vol_ratio"], 5,
                         labels=["Q1(低)", "Q2", "Q3", "Q4", "Q5(高)"])

    print(f"\n  OR 量比五等分 × 波幅分佈")
    print(f"  {'分位':<8} {'n':>5} {'OR量比':>8} {'avg波幅':>8} {'med波幅':>8}"
          f" {'波幅/EMA':>9} {'EMA觸及%':>9}")
    print(f"  {'-'*8} {'-'*5} {'-'*8} {'-'*8} {'-'*8} {'-'*9} {'-'*9}")

    for q_label, grp in valid.groupby("q", observed=True):
        avg_vr = grp["or_vol_ratio"].mean()
        avg_r = grp["day_range"].mean()
        med_r = grp["day_range"].median()
        avg_ratio = grp["range_ratio"].mean()
        hit_ema = (grp["day_range"] >= grp["ema_hl"]).mean() * 100
        print(f"  {str(q_label):<8} {len(grp):>5} {avg_vr:>8.2f} {avg_r:>8.0f}"
              f" {med_r:>8.0f} {avg_ratio:>9.2f} {hit_ema:>8.1f}%")

    # Year-by-year correlation
    print(f"\n  逐年相關性（OR 量比 vs 日波幅/EmaHL）")
    print(f"  {'Year':<6} {'n':>5} {'Pearson':>9} {'Spearman':>10}")
    print(f"  {'-'*6} {'-'*5} {'-'*9} {'-'*10}")
    for yr_label, yr in YEARS:
        yr_data = valid[valid["year"] == yr]
        if len(yr_data) < 20:
            continue
        rp = yr_data["or_vol_ratio"].corr(yr_data["range_ratio"])
        rs = yr_data["or_vol_ratio"].rank().corr(yr_data["range_ratio"].rank())
        print(f"  {yr_label:<6} {len(yr_data):>5} {rp:>+9.3f} {rs:>+10.3f}")


# ── Step 1: Adjustment formulas ──────────────────────────────────────────────

def step1_formulas(df: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Step 1：調整公式測試")
    print("=" * 72)

    valid = df[df["or_vol_ratio"].notna() & df["ema_hl"].notna()].copy()
    vr = valid["or_vol_ratio"].values
    ema = valid["ema_hl"].values
    actual = valid["day_range"].values

    # Define formulas
    formulas = {}

    # Baseline: no adjustment
    formulas["EmaHL（基準）"] = ema.copy()

    # F1: linear
    formulas["F1: EMA × VR"] = ema * vr

    # F2: sqrt dampening
    formulas["F2: EMA × VR^0.5"] = ema * np.sqrt(vr)

    # F3: clipped linear
    vr_clipped = np.clip(vr, 0.5, 2.0)
    formulas["F3: EMA × clip(VR,0.5,2)"] = ema * vr_clipped

    # F4: blend with different alphas
    for alpha in [0.3, 0.5, 0.7]:
        key = f"F4: EMA×({alpha:.1f}+{1-alpha:.1f}×VR)"
        formulas[key] = ema * (alpha + (1 - alpha) * vr)

    # F5: clipped sqrt
    formulas["F5: EMA × clip(VR^0.5,0.7,1.5)"] = ema * np.clip(np.sqrt(vr), 0.7, 1.5)

    # Evaluate each
    print(f"\n  {'公式':<30} {'觸及率%':>8} {'MAE':>7} {'RMSE':>7}"
          f" {'avg估值':>8} {'偏差%':>7}")
    print(f"  {'-'*30} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*7}")

    results = {}
    for label, est in formulas.items():
        hit = (actual >= est).mean() * 100
        mae = np.abs(actual - est).mean()
        rmse = np.sqrt(((actual - est) ** 2).mean())
        avg_est = est.mean()
        bias = (est.mean() - actual.mean()) / actual.mean() * 100

        results[label] = {
            "hit": hit, "mae": mae, "rmse": rmse,
            "avg_est": avg_est, "bias": bias, "values": est,
        }

        print(f"  {label:<30} {hit:>7.1f}% {mae:>7.0f} {rmse:>7.0f}"
              f" {avg_est:>8.0f} {bias:>+6.1f}%")

    # Year-by-year for top formulas
    top_formulas = ["EmaHL（基準）", "F2: EMA × VR^0.5",
                    "F3: EMA × clip(VR,0.5,2)", "F4: EMA×(0.5+0.5×VR)",
                    "F5: EMA × clip(VR^0.5,0.7,1.5)"]

    print(f"\n  逐年觸及率")
    header = f"  {'Year':<6}"
    for f in top_formulas:
        short = f[:12]
        header += f" {short:>13}"
    print(header)
    print(f"  {'-'*6}" + "".join(f" {'-'*13}" for _ in top_formulas))

    for yr_label, yr in YEARS:
        yr_mask = valid["year"].values == yr
        if yr_mask.sum() < 20:
            continue
        row = f"  {yr_label:<6}"
        for f in top_formulas:
            est = results[f]["values"][yr_mask]
            act = actual[yr_mask]
            hit = (act >= est).mean() * 100
            row += f" {hit:>12.1f}%"
        print(row)

    # Year-by-year MAE
    print(f"\n  逐年 MAE")
    header = f"  {'Year':<6}"
    for f in top_formulas:
        short = f[:12]
        header += f" {short:>13}"
    print(header)
    print(f"  {'-'*6}" + "".join(f" {'-'*13}" for _ in top_formulas))

    for yr_label, yr in YEARS:
        yr_mask = valid["year"].values == yr
        if yr_mask.sum() < 20:
            continue
        row = f"  {yr_label:<6}"
        for f in top_formulas:
            est = results[f]["values"][yr_mask]
            act = actual[yr_mask]
            mae = np.abs(act - est).mean()
            row += f" {mae:>13.0f}"
        print(row)

    return results, valid


# ── Step 2: Checkpoint hit rates + SatZone ───────────────────────────────────

def step2_checkpoint(df: pd.DataFrame, df_bars: pd.DataFrame, results: dict, valid: pd.DataFrame):
    print("\n" + "=" * 72)
    print("Step 2：Checkpoint 觸及率（running_low + 預估值 被碰到的機率）")
    print("=" * 72)

    top_formulas = ["EmaHL（基準）", "F2: EMA × VR^0.5",
                    "F4: EMA×(0.5+0.5×VR)", "F5: EMA × clip(VR^0.5,0.7,1.5)"]

    # Build per-day estimate lookup
    dates_arr = valid.index.values
    est_lookup = {}
    for f in top_formulas:
        vals = results[f]["values"]
        est_lookup[f] = dict(zip(dates_arr, vals))

    checkpoints = [dtime(9, 30), dtime(10, 0), dtime(10, 30), dtime(11, 0)]
    dates = sorted(df_bars["date"].unique())

    records = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in est_lookup[top_formulas[0]]:
            continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        for cp in checkpoints:
            before = day[day["time"] < cp]
            after = day[day["time"] >= cp]
            if before.empty or len(after) < 5:
                continue

            run_low = before["low"].min()
            run_high = before["high"].max()
            max_after = after["high"].max()
            min_after = after["low"].min()

            for f in top_formulas:
                est = est_lookup[f].get(td)
                if est is None or np.isnan(est):
                    continue
                hit_high = max_after >= (run_low + est)
                hit_low = min_after <= (run_high - est)
                records.append({
                    "date": date,
                    "checkpoint": cp,
                    "method": f,
                    "hit_high": hit_high,
                    "hit_low": hit_low,
                })

    rdf = pd.DataFrame(records)

    for cp in checkpoints:
        cp_data = rdf[rdf["checkpoint"] == cp]
        if cp_data.empty:
            continue
        print(f"\n  Checkpoint {cp}")
        print(f"  {'公式':<30} {'n':>5} {'觸及高%':>8} {'觸及低%':>8} {'合計%':>7}")
        print(f"  {'-'*30} {'-'*5} {'-'*8} {'-'*8} {'-'*7}")
        for f in top_formulas:
            sub = cp_data[cp_data["method"] == f]
            if sub.empty:
                continue
            hh = sub["hit_high"].mean() * 100
            hl = sub["hit_low"].mean() * 100
            total = ((sub["hit_high"]) | (sub["hit_low"])).mean() * 100
            print(f"  {f:<30} {len(sub):>5} {hh:>7.1f}% {hl:>7.1f}% {total:>6.1f}%")

    # SatZone analysis
    print("\n" + "-" * 72)
    print("SatZone 調整效果")
    print("-" * 72)
    print("  SatZoneUpper = session_low + EstHL_adj - EmaHL/8")
    print("  定義：SatZone 精準度 = P(day_high 落在 SatZoneUpper ± EmaHL/4 內)")

    sat_records = []
    for f in top_formulas:
        vals = results[f]["values"]
        ema_vals = results["EmaHL（基準）"]["values"]
        actual_high = valid["day_high"].values
        actual_low = valid["day_low"].values

        sat_upper = actual_low + vals - ema_vals / 8
        margin = ema_vals / 4

        within = ((actual_high >= sat_upper - margin) &
                  (actual_high <= sat_upper + margin))
        above = actual_high > sat_upper + margin
        below = actual_high < sat_upper - margin

        sat_records.append({
            "method": f,
            "within_pct": within.mean() * 100,
            "above_pct": above.mean() * 100,
            "below_pct": below.mean() * 100,
            "avg_error": np.abs(actual_high - sat_upper).mean(),
        })

    print(f"\n  {'公式':<30} {'zone內%':>8} {'偏高%':>7} {'偏低%':>7} {'avg誤差':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*7} {'-'*7} {'-'*8}")
    for r in sat_records:
        print(f"  {r['method']:<30} {r['within_pct']:>7.1f}%"
              f" {r['above_pct']:>6.1f}% {r['below_pct']:>6.1f}%"
              f" {r['avg_error']:>8.0f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("EstHL × OR 量比調整研究")
    print("=" * 72)

    print("\n載入資料...", flush=True)
    df_daily, df_bars = load_all_data()
    print(f"  {len(df_daily)} 交易日")
    print(f"  OR 量比有效：{df_daily['or_vol_ratio'].notna().sum()} 天")

    step0_correlation(df_daily)
    results, valid = step1_formulas(df_daily)
    step2_checkpoint(df_daily, df_bars, results, valid)

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()

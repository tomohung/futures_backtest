#!/usr/bin/env python3
"""H059 Phase 1: Night-Day Volatility Correlation — 夜盤日盤振幅相關性探索。

分析夜盤振幅（15:00~05:00）是否能預測隔天日盤振幅（08:45~13:45）。

Usage:
    uv run python research/active/H059-night-day-vol-correlation/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from datetime import time as dt_time, timedelta
from pathlib import Path
from scipy import stats

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H059-night-day-vol-correlation/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Data loading ────────────────────────────────────────────────────────


def load_1m_data():
    """Load all TX 1m data."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ── Session range calculation ───────────────────────────────────────────


def compute_paired_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Compute night and day session H-L ranges, paired by trading date.

    Night session (15:00~04:59) belongs to the NEXT trading day.
    Day session (08:45~13:44) belongs to the same calendar day.
    """
    df["time"] = df["timestamp"].dt.time
    df["cal_date"] = df["timestamp"].dt.date

    # Day session: 08:45 ~ 13:44
    day_mask = (df["time"] >= dt_time(8, 45)) & (df["time"] <= dt_time(13, 44))
    day = df[day_mask].copy()
    day["trade_date"] = day["cal_date"]

    day_ranges = (
        day.groupby("trade_date")
        .agg(day_high=("high", "max"), day_low=("low", "min"),
             day_volume=("volume", "sum"))
        .assign(day_range=lambda x: x["day_high"] - x["day_low"])
    )

    # Night session: 15:00~23:59 → next day, 00:00~04:59 → same day
    night_mask = (df["time"] >= dt_time(15, 0)) | (df["time"] < dt_time(5, 0))
    night = df[night_mask].copy()

    night["trade_date"] = night.apply(
        lambda r: r["cal_date"] + timedelta(days=1) if r["time"] >= dt_time(15, 0) else r["cal_date"],
        axis=1,
    )

    night_ranges = (
        night.groupby("trade_date")
        .agg(night_high=("high", "max"), night_low=("low", "min"),
             night_volume=("volume", "sum"),
             night_bars=("high", "count"))
        .assign(night_range=lambda x: x["night_high"] - x["night_low"])
    )

    # Merge: only keep days with BOTH night and day data
    paired = day_ranges.join(night_ranges, how="inner")

    # Filter out nights with too few bars (< 100 bars = < 2 hours of data)
    paired = paired[paired["night_bars"] >= 100].copy()

    return paired


# ── EMA normalization ──────────────────────────────────────────────────


def add_ema_normalized(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA(20)-normalized range columns."""
    for col in ["day_range", "night_range"]:
        ema_col = f"{col}_ema20"
        norm_col = f"{col}_norm"
        df[ema_col] = df[col].ewm(span=20, adjust=False).mean()
        df[norm_col] = df[col] / df[ema_col]
    return df


# ── Analysis ────────────────────────────────────────────────────────────


def correlation_analysis(df: pd.DataFrame) -> str:
    """Pearson and Spearman correlation between night and day ranges."""
    lines = ["## Correlation Analysis"]

    for suffix, night_col, day_col in [
        ("Raw", "night_range", "day_range"),
        ("EMA-Normalized", "night_range_norm", "day_range_norm"),
    ]:
        lines.append(f"\n### {suffix}")
        x = df[night_col].dropna()
        y = df[day_col].dropna()
        common = x.index.intersection(y.index)
        x, y = x[common], y[common]

        r_p, p_p = stats.pearsonr(x, y)
        r_s, p_s = stats.spearmanr(x, y)

        lines.append(f"  Pearson  r = {r_p:.4f}, p = {p_p:.2e} (N={len(common)})")
        lines.append(f"  Spearman ρ = {r_s:.4f}, p = {p_s:.2e}")

    return "\n".join(lines)


def quartile_analysis(df: pd.DataFrame) -> str:
    """Split night range into quartiles, compare day range distributions."""
    lines = ["## Quartile Analysis"]

    for suffix, night_col, day_col in [
        ("Raw", "night_range", "day_range"),
        ("EMA-Normalized", "night_range_norm", "day_range_norm"),
    ]:
        lines.append(f"\n### {suffix}")
        valid = df[[night_col, day_col]].dropna()
        valid["q"] = pd.qcut(valid[night_col], 4, labels=["Q1", "Q2", "Q3", "Q4"])

        lines.append(f"  {'Quartile':>8} | {'Night Med':>10} | {'Day Med':>10} | {'Day Mean':>10} | {'Day Std':>10} | {'N':>4}")
        lines.append(f"  {'-'*8} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*4}")

        q1_day = None
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            sub = valid[valid["q"] == q]
            n_med = sub[night_col].median()
            d_med = sub[day_col].median()
            d_mean = sub[day_col].mean()
            d_std = sub[day_col].std()
            if q == "Q1":
                q1_day = d_med
            lines.append(
                f"  {q:>8} | {n_med:>10.1f} | {d_med:>10.1f} | {d_mean:>10.1f} | {d_std:>10.1f} | {len(sub):>4}"
            )

        q4_day = valid[valid["q"] == "Q4"][day_col].median()
        if q1_day and q1_day > 0:
            lines.append(f"\n  Q4/Q1 day range ratio: {q4_day / q1_day:.3f}x")

        # Kruskal-Wallis test across quartiles
        groups = [valid[valid["q"] == q][day_col].values for q in ["Q1", "Q2", "Q3", "Q4"]]
        h_stat, p_kw = stats.kruskal(*groups)
        lines.append(f"  Kruskal-Wallis H={h_stat:.2f}, p={p_kw:.4f}")

        # Q1 vs Q4 Mann-Whitney
        u_stat, p_u = stats.mannwhitneyu(
            valid[valid["q"] == "Q4"][day_col],
            valid[valid["q"] == "Q1"][day_col],
            alternative="greater",
        )
        lines.append(f"  Q4 vs Q1 Mann-Whitney (one-sided): p={p_u:.4f}")

    return "\n".join(lines)


def extreme_analysis(df: pd.DataFrame) -> str:
    """Check behavior when night range > 2x EMA(20)."""
    lines = ["## Extreme Night Volatility Analysis"]

    valid = df[["night_range", "night_range_ema20", "day_range", "day_range_norm"]].dropna()

    extreme_mask = valid["night_range"] > 2 * valid["night_range_ema20"]
    normal_mask = ~extreme_mask

    extreme = valid[extreme_mask]
    normal = valid[normal_mask]

    lines.append(f"\n  Extreme nights (range > 2x EMA20): N={len(extreme)}")
    lines.append(f"  Normal nights: N={len(normal)}")

    if len(extreme) < 10:
        lines.append("  樣本不足，跳過極端值分析")
        return "\n".join(lines)

    # Compare day range after extreme vs normal nights
    e_day_med = extreme["day_range"].median()
    n_day_med = normal["day_range"].median()
    ratio = e_day_med / n_day_med if n_day_med > 0 else 0
    _, p = stats.mannwhitneyu(extreme["day_range"], normal["day_range"], alternative="greater")

    lines.append(f"\n  極端夜盤後日盤振幅 median: {e_day_med:.1f}")
    lines.append(f"  正常夜盤後日盤振幅 median: {n_day_med:.1f}")
    lines.append(f"  Ratio: {ratio:.3f}x, p={p:.4f}")

    # Normalized
    e_norm = extreme["day_range_norm"].median()
    n_norm = normal["day_range_norm"].median()
    norm_ratio = e_norm / n_norm if n_norm > 0 else 0
    _, p_n = stats.mannwhitneyu(extreme["day_range_norm"], normal["day_range_norm"], alternative="greater")
    lines.append(f"\n  [Normalized] Ratio: {norm_ratio:.3f}x, p={p_n:.4f}")

    # Check for non-linearity: very extreme (> 3x EMA)
    very_extreme = valid[valid["night_range"] > 3 * valid["night_range_ema20"]]
    if len(very_extreme) >= 5:
        ve_med = very_extreme["day_range"].median()
        lines.append(f"\n  Very extreme (> 3x EMA): N={len(very_extreme)}, day median={ve_med:.1f} (ratio={ve_med/n_day_med:.3f}x)")

    return "\n".join(lines)


def yearly_stability(df: pd.DataFrame) -> str:
    """Check if correlation is stable across years."""
    lines = ["## Yearly Stability"]

    df["year"] = pd.to_datetime(df.index.values).year
    lines.append(f"\n  {'Year':>6} | {'Pearson r':>10} | {'Spearman ρ':>10} | {'N':>4}")
    lines.append(f"  {'-'*6} | {'-'*10} | {'-'*10} | {'-'*4}")

    for year in sorted(df["year"].unique()):
        sub = df[df["year"] == year][["night_range", "day_range"]].dropna()
        if len(sub) < 20:
            lines.append(f"  {year:>6} | N/A (N={len(sub)})")
            continue
        r_p, _ = stats.pearsonr(sub["night_range"], sub["day_range"])
        r_s, _ = stats.spearmanr(sub["night_range"], sub["day_range"])
        lines.append(f"  {year:>6} | {r_p:>10.4f} | {r_s:>10.4f} | {len(sub):>4}")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("Loading 1m data...")
    df_1m = load_1m_data()
    print(f"  {len(df_1m):,} bars loaded")

    print("Computing paired night/day ranges...")
    paired = compute_paired_ranges(df_1m)
    print(f"  {len(paired)} paired trading days")

    print("Computing EMA normalization...")
    paired = add_ema_normalized(paired)
    # Drop warmup
    paired = paired.iloc[20:]

    print(f"\n{'='*72}")
    print("H059: Night-Day Volatility Correlation — Phase 1 Results")
    print(f"{'='*72}")

    print(f"\nData range: {paired.index.min()} ~ {paired.index.max()}")
    print(f"Paired trading days: {len(paired)}")
    print(f"\nBasic stats:")
    for col, label in [("night_range", "Night range"), ("day_range", "Day range")]:
        s = paired[col]
        print(f"  {label}: median={s.median():.1f}, mean={s.mean():.1f}, std={s.std():.1f}")

    # Analysis 1: Correlation
    result1 = correlation_analysis(paired)
    print(f"\n{result1}")

    # Analysis 2: Quartile
    result2 = quartile_analysis(paired)
    print(f"\n{result2}")

    # Analysis 3: Extreme nights
    result3 = extreme_analysis(paired)
    print(f"\n{result3}")

    # Analysis 4: Yearly stability
    result4 = yearly_stability(paired)
    print(f"\n{result4}")

    # Save CSV
    out_csv = OUT_DIR / "night_day_paired.csv"
    paired.to_csv(out_csv)
    print(f"\nResults saved to {out_csv}")


if __name__ == "__main__":
    main()

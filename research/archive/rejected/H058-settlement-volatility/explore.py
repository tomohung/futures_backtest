#!/usr/bin/env python3
"""H058 Phase 1: Settlement Volatility Effect — 結算日振幅分佈探索。

分析結算日（第三個週三或順延）前後的振幅是否顯著大於非結算日。
三個維度：日盤、夜盤、全日盤（前晚夜盤 + 當日日盤）。

Usage:
    uv run python research/active/H058-settlement-volatility/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
from scipy import stats

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H058-settlement-volatility/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Settlement date detection (from runner.py) ──────────────────────────


def settlement_dates(trading_dates: set[date]) -> set[date]:
    """Return actual TX monthly settlement dates."""
    years = {d.year for d in trading_dates}
    result = set()
    for y in sorted(years):
        for m in range(1, 13):
            d = date(y, m, 1)
            wed = d + timedelta(days=(2 - d.weekday()) % 7)
            third_wed = wed + timedelta(weeks=2)
            actual = third_wed
            while actual not in trading_dates:
                actual += timedelta(days=1)
                if (actual - third_wed).days > 10:
                    actual = None
                    break
            if actual is not None:
                result.add(actual)
    return result


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


def compute_session_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Compute day/night/full session H-L ranges per trading date."""

    df["time"] = df["timestamp"].dt.time
    df["cal_date"] = df["timestamp"].dt.date

    # Day session: 08:45 ~ 13:45
    from datetime import time as dt_time

    day_mask = (df["time"] >= dt_time(8, 45)) & (df["time"] <= dt_time(13, 44))
    day = df[day_mask].copy()
    day["trade_date"] = day["cal_date"]

    day_ranges = (
        day.groupby("trade_date")
        .agg(day_high=("high", "max"), day_low=("low", "min"),
             day_open=("open", "first"), day_close=("close", "last"),
             day_volume=("volume", "sum"))
        .assign(day_range=lambda x: x["day_high"] - x["day_low"])
    )

    # Night session: 15:00 ~ 04:59 next day
    # Night session belongs to the NEXT trading day
    night_mask = (df["time"] >= dt_time(15, 0)) | (df["time"] < dt_time(5, 0))
    night = df[night_mask].copy()

    # Assign night session to next trading day:
    # - bars from 15:00~23:59 → next calendar day's trading date
    # - bars from 00:00~04:59 → same calendar day's trading date
    night["trade_date"] = night.apply(
        lambda r: r["cal_date"] + timedelta(days=1) if r["time"] >= dt_time(15, 0) else r["cal_date"],
        axis=1,
    )

    night_ranges = (
        night.groupby("trade_date")
        .agg(night_high=("high", "max"), night_low=("low", "min"),
             night_volume=("volume", "sum"))
        .assign(night_range=lambda x: x["night_high"] - x["night_low"])
    )

    # Full session: night (prev evening) + day session of same trade_date
    merged = day_ranges.join(night_ranges, how="outer")

    # Full session range = max(day_high, night_high) - min(day_low, night_low)
    merged["full_high"] = merged[["day_high", "night_high"]].max(axis=1)
    merged["full_low"] = merged[["day_low", "night_low"]].min(axis=1)
    merged["full_range"] = merged["full_high"] - merged["full_low"]

    return merged


# ── Settlement proximity labeling ───────────────────────────────────────


def label_settlement_proximity(df: pd.DataFrame) -> pd.DataFrame:
    """Add settlement proximity column: -2, -1, 0, +1, or NaN."""
    trading_dates = sorted(df.index)
    settle_days = settlement_dates(set(trading_dates))

    # Build ordered trading date list for offset lookups
    td_list = list(trading_dates)
    td_idx = {d: i for i, d in enumerate(td_list)}

    proximity = {}
    for sd in settle_days:
        if sd not in td_idx:
            continue
        si = td_idx[sd]
        for offset in [-2, -1, 0, 1]:
            idx = si + offset
            if 0 <= idx < len(td_list):
                td = td_list[idx]
                # Closer offset wins (e.g., if +1 of one month == -2 of next)
                if td not in proximity or abs(offset) < abs(proximity[td]):
                    proximity[td] = offset

    df["settle_prox"] = pd.Series(proximity)
    df["is_settlement_week"] = df["settle_prox"].notna()
    return df


# ── EMA normalization ──────────────────────────────────────────────────


def add_ema_normalized(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA(20)-normalized range columns."""
    for col in ["day_range", "night_range", "full_range"]:
        ema_col = f"{col}_ema20"
        norm_col = f"{col}_norm"
        df[ema_col] = df[col].ewm(span=20, adjust=False).mean()
        df[norm_col] = df[col] / df[ema_col]
    return df


# ── Analysis ────────────────────────────────────────────────────────────


def analyze_settlement_vs_non(df: pd.DataFrame) -> str:
    """Compare settlement vs non-settlement ranges."""
    lines = []

    for dim in ["day_range", "night_range", "full_range"]:
        norm_col = f"{dim}_norm"
        lines.append(f"\n### {dim.replace('_', ' ').title()}")

        # Settlement day (prox=0) vs non-settlement
        settle = df[df["settle_prox"] == 0][dim].dropna()
        non_settle = df[df["settle_prox"].isna()][dim].dropna()

        if len(settle) < 5:
            lines.append(f"  結算日樣本不足 (N={len(settle)})")
            continue

        s_med = settle.median()
        ns_med = non_settle.median()
        ratio = s_med / ns_med if ns_med > 0 else float("inf")
        u_stat, p_val = stats.mannwhitneyu(settle, non_settle, alternative="greater")

        lines.append(f"  結算日 median: {s_med:.1f} (N={len(settle)})")
        lines.append(f"  非結算日 median: {ns_med:.1f} (N={len(non_settle)})")
        lines.append(f"  Ratio: {ratio:.3f}x")
        lines.append(f"  Mann-Whitney U (one-sided): p={p_val:.4f}")

        # Normalized version
        settle_n = df[df["settle_prox"] == 0][norm_col].dropna()
        non_settle_n = df[df["settle_prox"].isna()][norm_col].dropna()
        if len(settle_n) > 5:
            sn_med = settle_n.median()
            nsn_med = non_settle_n.median()
            n_ratio = sn_med / nsn_med if nsn_med > 0 else float("inf")
            _, p_n = stats.mannwhitneyu(settle_n, non_settle_n, alternative="greater")
            lines.append(f"  [Normalized] Ratio: {n_ratio:.3f}x, p={p_n:.4f}")

    return "\n".join(lines)


def analyze_proximity_effect(df: pd.DataFrame) -> str:
    """Analyze gradual effect from -2 to +1."""
    lines = ["\n## Proximity Effect (振幅 median by offset)"]

    non_settle = df[df["settle_prox"].isna()]

    for dim in ["day_range", "night_range", "full_range"]:
        norm_col = f"{dim}_norm"
        lines.append(f"\n### {dim.replace('_', ' ').title()}")
        ns_med = non_settle[dim].dropna().median()
        ns_norm_med = non_settle[norm_col].dropna().median()
        lines.append(f"  {'Offset':>8} | {'Median':>8} | {'Ratio':>7} | {'Norm Med':>9} | {'Norm Ratio':>10} | {'N':>4} | {'p-value':>8}")
        lines.append(f"  {'-'*8} | {'-'*8} | {'-'*7} | {'-'*9} | {'-'*10} | {'-'*4} | {'-'*8}")

        for offset in [-2, -1, 0, 1]:
            subset = df[df["settle_prox"] == offset][dim].dropna()
            subset_n = df[df["settle_prox"] == offset][norm_col].dropna()
            if len(subset) < 5:
                lines.append(f"  {offset:>8} | N/A (N={len(subset)})")
                continue
            med = subset.median()
            ratio = med / ns_med if ns_med > 0 else 0
            nmed = subset_n.median()
            nratio = nmed / ns_norm_med if ns_norm_med > 0 else 0
            _, p = stats.mannwhitneyu(subset, non_settle[dim].dropna(), alternative="greater")
            lines.append(
                f"  {offset:>8} | {med:>8.1f} | {ratio:>6.3f}x | {nmed:>9.3f} | {nratio:>9.3f}x | {len(subset):>4} | {p:>8.4f}"
            )

    return "\n".join(lines)


def analyze_weekday_control(df: pd.DataFrame) -> str:
    """Control for weekday effect — compare settlement Wed vs non-settlement Wed."""
    lines = ["\n## Weekday Control: Settlement Wednesday vs Non-Settlement Wednesday"]

    df["weekday"] = pd.to_datetime(df.index.values).weekday  # type: ignore

    settle_wed = df[(df["settle_prox"] == 0) & (df["weekday"] == 2)]
    non_settle_wed = df[(df["settle_prox"].isna()) & (df["weekday"] == 2)]

    for dim in ["day_range", "night_range", "full_range"]:
        norm_col = f"{dim}_norm"
        lines.append(f"\n### {dim.replace('_', ' ').title()}")
        sw = settle_wed[dim].dropna()
        nsw = non_settle_wed[dim].dropna()
        if len(sw) < 5:
            lines.append(f"  結算週三樣本不足 (N={len(sw)})")
            continue
        ratio = sw.median() / nsw.median() if nsw.median() > 0 else 0
        _, p = stats.mannwhitneyu(sw, nsw, alternative="greater")

        sw_n = settle_wed[norm_col].dropna()
        nsw_n = non_settle_wed[norm_col].dropna()
        nratio = sw_n.median() / nsw_n.median() if nsw_n.median() > 0 else 0
        _, p_n = stats.mannwhitneyu(sw_n, nsw_n, alternative="greater")

        lines.append(f"  結算週三 median: {sw.median():.1f} (N={len(sw)})")
        lines.append(f"  非結算週三 median: {nsw.median():.1f} (N={len(nsw)})")
        lines.append(f"  Ratio: {ratio:.3f}x, p={p:.4f}")
        lines.append(f"  [Normalized] Ratio: {nratio:.3f}x, p={p_n:.4f}")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("Loading 1m data...")
    df_1m = load_1m_data()
    print(f"  {len(df_1m):,} bars loaded")

    print("Computing session ranges...")
    ranges = compute_session_ranges(df_1m)
    # Filter to dates with day session data
    ranges = ranges[ranges["day_range"].notna()].copy()
    print(f"  {len(ranges)} trading days")

    print("Labeling settlement proximity...")
    ranges = label_settlement_proximity(ranges)
    n_settle = (ranges["settle_prox"] == 0).sum()
    print(f"  {n_settle} settlement days found")

    print("Computing EMA normalization...")
    ranges = add_ema_normalized(ranges)
    # Drop warmup period
    ranges = ranges.iloc[20:]

    print("\n" + "=" * 72)
    print("H058: Settlement Volatility Effect — Phase 1 Results")
    print("=" * 72)

    # Basic stats
    print(f"\nData range: {ranges.index.min()} ~ {ranges.index.max()}")
    print(f"Trading days: {len(ranges)}")
    print(f"Settlement days (offset=0): {(ranges['settle_prox'] == 0).sum()}")
    for off in [-2, -1, 0, 1]:
        n = (ranges["settle_prox"] == off).sum()
        print(f"  Offset {off:+d}: {n} days")

    # Analysis 1: Settlement vs Non-settlement
    print("\n## Settlement Day vs Non-Settlement Day")
    result1 = analyze_settlement_vs_non(ranges)
    print(result1)

    # Analysis 2: Proximity effect
    result2 = analyze_proximity_effect(ranges)
    print(result2)

    # Analysis 3: Weekday control
    result3 = analyze_weekday_control(ranges)
    print(result3)

    # Summary stats table for markdown
    print("\n\n## Summary Statistics")
    for dim in ["day_range", "night_range", "full_range"]:
        print(f"\n### {dim.replace('_', ' ').title()}")
        for label, mask in [
            ("Settlement (0)", ranges["settle_prox"] == 0),
            ("Pre-1 (-1)", ranges["settle_prox"] == -1),
            ("Pre-2 (-2)", ranges["settle_prox"] == -2),
            ("Post+1 (+1)", ranges["settle_prox"] == 1),
            ("Non-settlement", ranges["settle_prox"].isna()),
        ]:
            subset = ranges[mask][dim].dropna()
            if len(subset) < 3:
                continue
            print(
                f"  {label:>20}: median={subset.median():>7.1f}, "
                f"mean={subset.mean():>7.1f}, std={subset.std():>6.1f}, N={len(subset)}"
            )

    # Save full results to CSV
    out_csv = OUT_DIR / "settlement_ranges.csv"
    ranges.to_csv(out_csv)
    print(f"\nResults saved to {out_csv}")


if __name__ == "__main__":
    main()

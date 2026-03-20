"""
Explore optimal SatZone fraction and settlement day volume multiplier.

Analysis:
  1a. Find vol_mult that makes settlement 100% EstRange either ≈ normal days (38%)
  1b. Est High fraction: for each fraction, measure touch rate and remaining upside
  1c. Est Low fraction: same for short side
  1d. Combined table

Usage:
    uv run python src/backtest/explore_satzone_fraction.py
"""

import sys
from datetime import date, timedelta, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.estimate_hl import compute_vol_estimated_range

DB_PATH = "data/futures.duckdb"
ANALYSIS_START = date(2024, 1, 1)


def _get_settle_dates(trading_dates: set[date]) -> set[date]:
    settle = set()
    min_y = min(d.year for d in trading_dates)
    max_y = max(d.year for d in trading_dates)
    for y in range(min_y, max_y + 1):
        for m in range(1, 13):
            d = date(y, m, 1)
            wed = d + timedelta(days=(2 - d.weekday()) % 7)
            tw = wed + timedelta(weeks=2)
            a = tw
            while a not in trading_dates:
                a += timedelta(days=1)
                if (a - tw).days > 10:
                    a = None
                    break
            if a:
                settle.add(a)
    return settle


def load_raw() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
              AND timestamp >= '2023-01-01'
            ORDER BY timestamp
        """).df()
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def get_trading_dates() -> set[date]:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM ticks WHERE symbol = 'TX'"
        ).fetchall()
    return set(r[0] for r in rows)


def hit_rate_100(df: pd.DataFrame, dates: list[date]) -> tuple[int, int]:
    """Return (either_hits, total) for 100% EstRange."""
    either, n = 0, 0
    for d in dates:
        day = df[df.index.date == d]
        if day.empty:
            continue
        t9 = day[day.index.time >= time(9, 30)]
        if t9.empty:
            continue
        er = t9["EstRange"].dropna()
        if er.empty:
            continue
        er_v = er.iloc[0]
        lo9 = day[day.index.time <= time(9, 30)]["Low"].min()
        hi9 = day[day.index.time <= time(9, 30)]["High"].max()
        sh, sl = day["High"].max(), day["Low"].min()
        if sh >= lo9 + er_v or sl <= hi9 - er_v:
            either += 1
        n += 1
    return either, n


def fraction_analysis(
    df: pd.DataFrame, dates: list[date], fractions: list[float]
) -> pd.DataFrame:
    """For each fraction, compute touch rate and EV for Est High and Est Low."""
    results = []
    for frac in fractions:
        h_touch, l_touch, either = 0, 0, 0
        h_remaining, l_remaining = [], []  # remaining move after touch
        h_profit_at_touch, l_profit_at_touch = [], []  # profit captured at touch
        n = 0

        for d in dates:
            day = df[df.index.date == d]
            if day.empty:
                continue
            t9 = day[day.index.time >= time(9, 30)]
            if t9.empty:
                continue
            er = t9["EstRange"].dropna()
            if er.empty:
                continue
            er_v = er.iloc[0]

            lo9 = day[day.index.time <= time(9, 30)]["Low"].min()
            hi9 = day[day.index.time <= time(9, 30)]["High"].max()
            day_open = day.iloc[0]["Open"]
            sh, sl = day["High"].max(), day["Low"].min()
            n += 1

            # Est High (long exit target)
            est_high = lo9 + er_v * frac
            h_touched = sh >= est_high
            if h_touched:
                h_touch += 1
                # Profit from open to est_high
                h_profit_at_touch.append(est_high - day_open)
                # Remaining upside missed
                h_remaining.append(sh - est_high)

            # Est Low (short exit target)
            est_low = hi9 - er_v * frac
            l_touched = sl <= est_low
            if l_touched:
                l_touch += 1
                # Profit from open to est_low (short: open - est_low)
                l_profit_at_touch.append(day_open - est_low)
                # Remaining downside missed
                l_remaining.append(est_low - sl)

            if h_touched or l_touched:
                either += 1

        results.append({
            "fraction": frac,
            "n": n,
            "H_touch": h_touch,
            "H_rate": h_touch / n if n else 0,
            "H_avg_profit": np.mean(h_profit_at_touch) if h_profit_at_touch else 0,
            "H_avg_remaining": np.mean(h_remaining) if h_remaining else 0,
            "L_touch": l_touch,
            "L_rate": l_touch / n if n else 0,
            "L_avg_profit": np.mean(l_profit_at_touch) if l_profit_at_touch else 0,
            "L_avg_remaining": np.mean(l_remaining) if l_remaining else 0,
            "either": either,
            "either_rate": either / n if n else 0,
        })
    return pd.DataFrame(results)


def main():
    print("Loading data...", flush=True)
    df_raw = load_raw()
    trading_dates = get_trading_dates()
    settle_set = _get_settle_dates(trading_dates)
    settle_list = sorted(d for d in settle_set if d >= ANALYSIS_START)
    non_settle = sorted(
        d for d in set(df_raw.index.date) if d not in settle_set and d >= ANALYSIS_START
    )

    # ================================================================
    # 1a. Settlement vol_mult search
    # ================================================================
    print("\n" + "=" * 70)
    print("1a. 結算日 vol_mult → 100% EstRange either (target ≈ 38%)")
    print("=" * 70)

    # First get normal day baseline
    df_base = compute_vol_estimated_range(df_raw.copy(), lookback=20, use_ema=True)
    e_norm, n_norm = hit_rate_100(df_base, non_settle)
    baseline = e_norm / n_norm
    print(f"一般日 baseline: {e_norm}/{n_norm} = {baseline:.0%}")
    print()

    for vm in [1.5, 1.7, 1.9, 2.1, 2.3, 2.5, 2.7, 3.0, 3.5]:
        df = compute_vol_estimated_range(
            df_raw.copy(), lookback=20, use_ema=True,
            settlement_dates=settle_set, settlement_vol_mult=vm,
        )
        e, n = hit_rate_100(df, settle_list)
        marker = " ←" if abs(e / n - baseline) < 0.05 else ""
        print(f"  ×{vm:.1f}: {e}/{n} = {e/n:.0%}{marker}")

    # ================================================================
    # 1b/1c/1d. Fraction analysis
    # ================================================================
    print("\n" + "=" * 70)
    print("1b/c/d. Fraction analysis — 一般日 (2024-2026)")
    print("=" * 70)

    fracs = [round(0.50 + i * 0.05, 2) for i in range(11)]
    res = fraction_analysis(df_base, non_settle, fracs)

    print(f"\n{'frac':>5s}  {'H_rate':>6s}  {'H_prof':>7s}  {'H_miss':>7s}  "
          f"{'L_rate':>6s}  {'L_prof':>7s}  {'L_miss':>7s}  {'either':>6s}")
    for _, r in res.iterrows():
        print(f"{r.fraction:5.2f}  {r.H_rate:6.0%}  {r.H_avg_profit:7.0f}  "
              f"{r.H_avg_remaining:7.0f}  {r.L_rate:6.0%}  {r.L_avg_profit:7.0f}  "
              f"{r.L_avg_remaining:7.0f}  {r.either_rate:6.0%}")

    # Also show settlement days with ×1.9
    print("\n" + "=" * 70)
    print("Fraction analysis — 結算日 ×1.9 (2024-2026)")
    print("=" * 70)

    df_settle = compute_vol_estimated_range(
        df_raw.copy(), lookback=20, use_ema=True,
        settlement_dates=settle_set, settlement_vol_mult=1.9,
    )
    res_s = fraction_analysis(df_settle, settle_list, fracs)

    print(f"\n{'frac':>5s}  {'H_rate':>6s}  {'H_prof':>7s}  {'H_miss':>7s}  "
          f"{'L_rate':>6s}  {'L_prof':>7s}  {'L_miss':>7s}  {'either':>6s}")
    for _, r in res_s.iterrows():
        print(f"{r.fraction:5.2f}  {r.H_rate:6.0%}  {r.H_avg_profit:7.0f}  "
              f"{r.H_avg_remaining:7.0f}  {r.L_rate:6.0%}  {r.L_avg_profit:7.0f}  "
              f"{r.L_avg_remaining:7.0f}  {r.either_rate:6.0%}")


if __name__ == "__main__":
    main()

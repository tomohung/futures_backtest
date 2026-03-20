"""Compare EstHL strategies: original vs OR volume adjusted.

Runs ORBWithEstHLExitStrategy with both original and OR-volume-adjusted EstHL,
printing side-by-side year-by-year comparison.

Usage:
    uv run python src/backtest/compare_esthl_vol.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.estimate_hl import compute_estimate_hl_zones
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

DB_PATH = "data/futures.duckdb"

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

ESTHL_PARAMS = dict(
    sl_ema_fraction=0.25,
    bigcost_days=2,
    long_only=True,
    skip_thursday=True,
    skip_friday=True,
)


def load_data_for_esthl(or_vol_adjust=False, or_vol_alpha=0.3):
    """Load data with EstHL zones, optionally with OR volume adjustment."""

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_all = conn.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        df_day = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        df_bigcost = conn.execute("""
            WITH vol_ma AS (
                SELECT timestamp::DATE AS date, timestamp, close, volume,
                       AVG(volume) OVER (
                           PARTITION BY timestamp::DATE
                           ORDER BY timestamp
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS vol_20ma
                FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ),
            filtered AS (
                SELECT date, close, volume FROM vol_ma WHERE volume >= vol_20ma
            )
            SELECT date, ROUND(SUM(close * volume) / SUM(volume))::INT AS big_cost
            FROM filtered GROUP BY date ORDER BY date
        """).df()

    df_day.columns = ["Open", "High", "Low", "Close", "Volume"]

    from src.backtest.runner import adjust_settlement_volume
    adjust_settlement_volume(df_day)

    # Estimate H-L zones with optional OR volume adjustment
    df_day = compute_estimate_hl_zones(
        df_day,
        or_vol_adjust=or_vol_adjust,
        or_vol_alpha=or_vol_alpha,
    )

    # 10-day TrendMA
    n_bars = 10 * 301
    trend_ma = df_all["close"].rolling(n_bars, min_periods=n_bars).mean()
    df_day["TrendMA"] = trend_ma.reindex(df_day.index)

    # 30m 20MA
    s30 = df_all["close"].resample("30min").last()
    s30 = s30.dropna()
    ma30_20 = s30.rolling(20, min_periods=20).mean()
    ma30_20_shifted = ma30_20.shift(1)
    close30_shifted = s30.shift(1)
    df_day["MA30_20"] = ma30_20_shifted.reindex(df_day.index, method="ffill")
    df_day["Close30"] = close30_shifted.reindex(df_day.index, method="ffill")

    # BigCost
    df_bigcost["date"] = pd.to_datetime(df_bigcost["date"])
    bc = df_bigcost.set_index("date")["big_cost"]
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    for i in range(1, 6):
        df_day[f"BigCost{i}"] = bc.shift(i).reindex(day_dates).values

    # OR width and RollingOR
    day_date_col = pd.DatetimeIndex(df_day.index).date
    times = pd.DatetimeIndex(df_day.index).time
    from datetime import time as dtime
    or_mask = times <= dtime(8, 57)
    or_highs = df_day.loc[or_mask, "High"].groupby(day_date_col[or_mask]).max()
    or_lows = df_day.loc[or_mask, "Low"].groupby(day_date_col[or_mask]).min()
    or_width = or_highs - or_lows
    rolling_or = or_width.rolling(20, min_periods=5).mean().shift(1)
    df_day["ORWidth"] = or_width.reindex(day_date_col).values
    df_day["RollingOR"] = rolling_or.reindex(day_date_col).values

    # DailyADX (skip for speed — set to NaN, strategy will ignore)
    df_day["DailyADX"] = np.nan

    # Back-fill EmaHL columns within each day
    _hl_cols = ["EmaHL", "EmaVol", "SatZoneUpper", "SatZoneLower",
                "EstHL", "EstHighLevel", "EstLowLevel"]
    date_groups = pd.DatetimeIndex(df_day.index).date
    for col in _hl_cols:
        s = df_day[col].copy()
        s_filled = s.groupby(date_groups).transform(lambda g: g.bfill())
        df_day[col] = s_filled

    return df_day


def run_and_summarize(df, label, params):
    """Run backtest and return summary dict."""
    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    if trades.empty:
        return None

    trades["year"] = pd.to_datetime(trades["EntryTime"]).dt.year
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    pf = wins.sum() / losses.abs().sum() if losses.abs().sum() > 0 else float("inf")

    return {
        "label": label,
        "trades": trades,
        "n": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "avg_pnl": pnl.mean(),
        "total": pnl.sum(),
        "pf": pf,
    }


def print_comparison(results: list[dict]):
    """Print side-by-side comparison."""
    print(f"\n  {'策略':<28} {'n':>4} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*28} {'-'*4} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    for r in results:
        print(f"  {r['label']:<28} {r['n']:>4} {r['win_rate']:>6.1f}%"
              f" {r['avg_pnl']:>+7.1f} {r['total']:>+7.0f} {r['pf']:>7.2f}")

    # Year-by-year
    for r in results:
        trades = r["trades"]
        print(f"\n  逐年（{r['label']}）")
        print(f"  {'Year':<6} {'n':>4} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
        print(f"  {'-'*6} {'-'*4} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
        for yr_label, start, end in YEARS:
            yr = int(yr_label)
            yr_data = trades[trades["year"] == yr]
            if yr_data.empty:
                continue
            pnl = yr_data["PnL"]
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            wr = len(wins) / len(pnl) * 100
            pf = wins.sum() / losses.abs().sum() if losses.abs().sum() > 0 else float("inf")
            print(f"  {yr_label:<6} {len(pnl):>4} {wr:>6.1f}% {pnl.mean():>+7.1f}"
                  f" {pnl.sum():>+7.0f} {pf:>7.2f}")


def main():
    print("=" * 72)
    print("EstHL 策略比較：原始 vs OR 量比調整")
    print("=" * 72)

    # Load both versions
    print("\n載入原始 EstHL 資料...", flush=True)
    df_orig = load_data_for_esthl(or_vol_adjust=False)

    print("載入 OR 量比調整 EstHL (α=0.3)...", flush=True)
    df_adj03 = load_data_for_esthl(or_vol_adjust=True, or_vol_alpha=0.3)

    print("載入 OR 量比調整 EstHL (α=0.5)...", flush=True)
    df_adj05 = load_data_for_esthl(or_vol_adjust=True, or_vol_alpha=0.5)

    # Run backtests
    print("\n執行回測...", flush=True)
    results = []

    r = run_and_summarize(df_orig, "EstHL 原始", ESTHL_PARAMS)
    if r:
        results.append(r)

    r = run_and_summarize(df_adj03, "EstHL + OR量比 (α=0.3)", ESTHL_PARAMS)
    if r:
        results.append(r)

    r = run_and_summarize(df_adj05, "EstHL + OR量比 (α=0.5)", ESTHL_PARAMS)
    if r:
        results.append(r)

    print_comparison(results)

    # Compare EmaHL values between original and adjusted
    print("\n" + "-" * 72)
    print("EstHL 調整幅度統計")
    print("-" * 72)

    orig_hl = df_orig["EstHL"].dropna()
    adj03_hl = df_adj03["EstHL"].dropna()

    # Align by index
    common = orig_hl.index.intersection(adj03_hl.index)
    if len(common) > 0:
        o = orig_hl.loc[common]
        a = adj03_hl.loc[common]
        ratio = a / o
        diff = a - o
        changed = (ratio != 1.0) & ratio.notna()
        changed_ratio = ratio[changed]
        print(f"  比較 bar 數：{len(common):,}")
        print(f"  有調整的 bar：{changed.sum():,} ({changed.mean()*100:.1f}%)")
        if len(changed_ratio) > 0:
            print(f"  調整比例：mean={changed_ratio.mean():.3f}"
                  f"  median={changed_ratio.median():.3f}"
                  f"  min={changed_ratio.min():.3f}"
                  f"  max={changed_ratio.max():.3f}")

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()

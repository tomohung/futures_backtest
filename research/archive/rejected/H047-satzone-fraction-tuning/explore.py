#!/usr/bin/env python3
"""H047 Phase 1: SatZone Fraction 策略別調校 — 分佈探索。

分析三個策略 (S001/S002/S003) 在不同 SatZone fraction 下的：
1. Touch rate（觸及率）
2. Untouched 日損益分佈
3. 觸及後剩餘續行空間
4. 各 fraction 下的 EV% 粗估

Usage:
    uv run python research/active/H047-satzone-fraction-tuning/explore.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    load_data_for_exhaustion,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy
from src.strategies.exhaustion import ExhaustionStrategy

FRACTIONS = [0.80, 0.85, 0.90, 0.95, 1.00]

# Live params for each strategy
S001_PARAMS = dict(
    sl_ema_fraction=0.25, adx_min=0.0, long_only=True,
    vwap_days=2, skip_thursday=True, skip_friday=True,
)
S002_PARAMS = dict(
    vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
    signal_skip=0, sat_pullback_fraction=0.5,
)
S003_PARAMS = dict(
    sl_fraction=0.25, min_orb_pct=0.25, skip_wed=True, skip_thu=True,
)

STRATEGIES = {
    "S001": {
        "loader": load_data_for_orb_est_hl,
        "strategy": ORBWithEstHLExitStrategy,
        "params": S001_PARAMS,
    },
    "S002": {
        "loader": load_data_for_reversal,
        "strategy": ReversalStrategy,
        "params": S002_PARAMS,
    },
    "S003": {
        "loader": load_data_for_exhaustion,
        "strategy": ExhaustionStrategy,
        "params": S003_PARAMS,
    },
}


def run_baseline_backtest(name: str, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run baseline backtest and return (1m_data, trades)."""
    print(f"\n{'='*60}")
    print(f"Loading data for {name}...")
    df = config["loader"]()
    print(f"  {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    print(f"Running baseline backtest for {name}...")
    bt = Backtest(df, config["strategy"],
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**config["params"])
    trades = stats["_trades"].copy()
    print(f"  {len(trades)} trades, WR {(trades['PnL']>0).mean()*100:.1f}%, "
          f"EV {trades['PnL'].mean():.1f} pts")
    return df, trades


def compute_session_extremes(df: pd.DataFrame) -> pd.DataFrame:
    """Add cumulative session_low and session_high columns per day."""
    df = df.copy()
    df["_date"] = df.index.date
    df["SessionLow"] = df.groupby("_date")["Low"].cummin()
    df["SessionHigh"] = df.groupby("_date")["High"].cummax()
    df.drop(columns=["_date"], inplace=True)
    return df


def compute_adjusted_satzone(df: pd.DataFrame, fraction: float) -> pd.DataFrame:
    """Compute fraction-adjusted SatZone targets.

    Formula:
        zone_dist = EstHL - EmaHL/8  (distance from session extreme to SatZone)
        SatZoneUpper_frac = SessionLow + fraction × zone_dist
        SatZoneLower_frac = SessionHigh - fraction × zone_dist
    """
    zone_dist = df["EstHL"] - df["EmaHL"] / 8
    upper = df["SessionLow"] + fraction * zone_dist
    lower = df["SessionHigh"] - fraction * zone_dist
    return upper, lower


def analyze_touch_rates(df: pd.DataFrame, trades: pd.DataFrame,
                        strategy_name: str) -> pd.DataFrame:
    """Analyze touch rates at each fraction for each trade."""
    df = compute_session_extremes(df)
    results = []

    for _, trade in trades.iterrows():
        entry_bar = int(trade["EntryBar"])
        exit_bar = int(trade["ExitBar"])
        is_long = trade["Size"] > 0
        entry_price = trade["EntryPrice"]
        exit_price = trade["ExitPrice"]
        pnl = trade["PnL"]

        # Get trade bars
        trade_df = df.iloc[entry_bar:exit_bar + 1]
        if trade_df.empty:
            continue

        entry_time = trade_df.index[0]
        exit_time = trade_df.index[-1]
        entry_date = entry_time.date()

        # Session extremes during the trade
        if is_long:
            max_favorable = trade_df["High"].max()
            max_excursion = max_favorable - entry_price
        else:
            min_favorable = trade_df["Low"].min()
            max_excursion = entry_price - min_favorable

        for frac in FRACTIONS:
            adj_upper, adj_lower = compute_adjusted_satzone(trade_df, frac)

            if is_long:
                # Check if high ever reached adjusted SatZoneUpper
                touched_mask = trade_df["High"] >= adj_upper
                # Exclude NaN targets
                valid_mask = ~adj_upper.isna()
                has_valid_target = valid_mask.any()
                touched = (touched_mask & valid_mask).any()

                if touched and has_valid_target:
                    first_touch_idx = (touched_mask & valid_mask).idxmax()
                    touch_bar = trade_df.index.get_loc(first_touch_idx)
                    target_at_touch = adj_upper.loc[first_touch_idx]
                    # Remaining continuation after touch
                    post_touch = trade_df.iloc[touch_bar:]
                    remaining = post_touch["High"].max() - target_at_touch
                else:
                    touch_bar = None
                    target_at_touch = None
                    remaining = None
            else:
                touched_mask = trade_df["Low"] <= adj_lower
                valid_mask = ~adj_lower.isna()
                has_valid_target = valid_mask.any()
                touched = (touched_mask & valid_mask).any()

                if touched and has_valid_target:
                    first_touch_idx = (touched_mask & valid_mask).idxmax()
                    touch_bar = trade_df.index.get_loc(first_touch_idx)
                    target_at_touch = adj_lower.loc[first_touch_idx]
                    post_touch = trade_df.iloc[touch_bar:]
                    remaining = target_at_touch - post_touch["Low"].min()
                else:
                    touch_bar = None
                    target_at_touch = None
                    remaining = None

            results.append({
                "strategy": strategy_name,
                "entry_date": entry_date,
                "entry_time": entry_time,
                "direction": "long" if is_long else "short",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl / entry_price * 100,
                "max_excursion": max_excursion,
                "fraction": frac,
                "touched": touched,
                "has_valid_target": has_valid_target,
                "touch_bar_offset": touch_bar,
                "target_at_touch": target_at_touch,
                "remaining_after_touch": remaining,
                "trade_bars": len(trade_df),
                "year": entry_date.year,
            })

    return pd.DataFrame(results)


def print_touch_rate_table(all_results: pd.DataFrame):
    """Print touch rate table: strategy × fraction."""
    print("\n" + "=" * 70)
    print("TOUCH RATE BY STRATEGY × FRACTION")
    print("=" * 70)

    for strat in all_results["strategy"].unique():
        sdf = all_results[all_results["strategy"] == strat]
        n_trades = sdf[sdf["fraction"] == 1.0].shape[0]
        print(f"\n{strat} (N={n_trades} trades)")
        print(f"{'Fraction':<10} {'Touch Rate':>12} {'N Touched':>12} {'Δ vs 1.0':>10}")
        print("-" * 46)
        base_rate = None
        for frac in FRACTIONS:
            fdf = sdf[sdf["fraction"] == frac]
            valid = fdf[fdf["has_valid_target"]]
            if len(valid) == 0:
                continue
            rate = valid["touched"].mean() * 100
            n_touched = valid["touched"].sum()
            if frac == 1.0:
                base_rate = rate
                delta = ""
            else:
                delta = f"+{rate - base_rate:.1f}pp" if base_rate else ""
            print(f"  {frac:<8.2f} {rate:>10.1f}% {n_touched:>10.0f} {delta:>10}")

    # By year breakdown for fraction=1.0 vs 0.90
    print("\n" + "-" * 70)
    print("TOUCH RATE BY YEAR (fraction=1.0 vs 0.90)")
    print("-" * 70)
    for strat in all_results["strategy"].unique():
        sdf = all_results[all_results["strategy"] == strat]
        print(f"\n{strat}")
        print(f"{'Year':<8} {'f=1.0':>10} {'f=0.90':>10} {'f=0.85':>10} {'N':>6}")
        print("-" * 40)
        for year in sorted(sdf["year"].unique()):
            ydf = sdf[sdf["year"] == year]
            rates = {}
            for frac in [1.0, 0.90, 0.85]:
                fdf = ydf[(ydf["fraction"] == frac) & ydf["has_valid_target"]]
                rates[frac] = fdf["touched"].mean() * 100 if len(fdf) > 0 else 0
            n = len(ydf[ydf["fraction"] == 1.0])
            print(f"  {year:<6} {rates[1.0]:>8.1f}% {rates[0.90]:>8.1f}% "
                  f"{rates[0.85]:>8.1f}% {n:>6}")


def print_untouched_pnl(all_results: pd.DataFrame):
    """Print P&L distribution for untouched trades at fraction=1.0."""
    print("\n" + "=" * 70)
    print("UNTOUCHED TRADES P&L (fraction=1.0 baseline)")
    print("=" * 70)

    for strat in all_results["strategy"].unique():
        sdf = all_results[(all_results["strategy"] == strat) &
                          (all_results["fraction"] == 1.0)]
        touched = sdf[sdf["touched"]]
        untouched = sdf[~sdf["touched"]]

        print(f"\n{strat}")
        print(f"  Touched:   N={len(touched)}, "
              f"EV={touched['pnl'].mean():.1f} pts, "
              f"WR={((touched['pnl']>0).mean()*100):.1f}%"
              if len(touched) > 0 else f"  Touched:   N=0")
        print(f"  Untouched: N={len(untouched)}, "
              f"EV={untouched['pnl'].mean():.1f} pts, "
              f"WR={((untouched['pnl']>0).mean()*100):.1f}%"
              if len(untouched) > 0 else f"  Untouched: N=0")

        if len(untouched) > 0:
            pnl = untouched["pnl"]
            print(f"  Untouched P&L分佈:")
            print(f"    Mean: {pnl.mean():.1f}, Median: {pnl.median():.1f}, "
                  f"Std: {pnl.std():.1f}")
            print(f"    Min: {pnl.min():.0f}, Q25: {pnl.quantile(0.25):.0f}, "
                  f"Q75: {pnl.quantile(0.75):.0f}, Max: {pnl.max():.0f}")


def print_remaining_continuation(all_results: pd.DataFrame):
    """Print remaining continuation after SatZone touch."""
    print("\n" + "=" * 70)
    print("REMAINING CONTINUATION AFTER SATZONE TOUCH (pts)")
    print("=" * 70)

    for strat in all_results["strategy"].unique():
        sdf = all_results[all_results["strategy"] == strat]
        print(f"\n{strat}")
        print(f"{'Fraction':<10} {'Mean':>8} {'Median':>8} {'Q25':>8} {'Q75':>8} {'N':>6}")
        print("-" * 50)

        for frac in FRACTIONS:
            fdf = sdf[(sdf["fraction"] == frac) & sdf["touched"]]
            rem = fdf["remaining_after_touch"].dropna()
            if len(rem) == 0:
                continue
            print(f"  {frac:<8.2f} {rem.mean():>7.1f} {rem.median():>7.1f} "
                  f"{rem.quantile(0.25):>7.1f} {rem.quantile(0.75):>7.1f} {len(rem):>6}")


def estimate_ev_by_fraction(all_results: pd.DataFrame):
    """Estimate EV at each fraction by blending touched/untouched outcomes.

    Logic:
    - For trades that NEWLY become touched at lower fraction (vs f=1.0):
      approximate exit near the fraction-adjusted target (conservative: target price)
    - For trades that were already touched at f=1.0: assume same exit
    - For trades still untouched: assume same exit as baseline
    """
    print("\n" + "=" * 70)
    print("ESTIMATED EV BY STRATEGY × FRACTION")
    print("=" * 70)

    for strat in all_results["strategy"].unique():
        sdf = all_results[all_results["strategy"] == strat]
        baseline = sdf[sdf["fraction"] == 1.0].copy()
        n_trades = len(baseline)

        print(f"\n{strat} (N={n_trades})")
        print(f"{'Fraction':<10} {'Est EV (pts)':>14} {'Est EV%':>10} "
              f"{'Touch Rate':>12} {'Δ EV':>8}")
        print("-" * 58)

        base_ev = baseline["pnl"].mean()
        base_ev_pct = baseline["pnl_pct"].mean()

        for frac in FRACTIONS:
            fdf = sdf[sdf["fraction"] == frac]

            # Merge fraction touch info with baseline trade data
            merged = baseline[["entry_date", "direction", "entry_price",
                               "pnl", "pnl_pct", "touched"]].copy()
            merged.columns = ["entry_date", "direction", "entry_price",
                              "base_pnl", "base_pnl_pct", "base_touched"]

            frac_info = fdf[["entry_date", "touched", "target_at_touch"]].copy()
            frac_info.columns = ["entry_date", "frac_touched", "frac_target"]

            merged = merged.merge(frac_info, on="entry_date", how="left")

            est_pnls = []
            for _, row in merged.iterrows():
                if not row["frac_touched"] or pd.isna(row["frac_touched"]):
                    # Still untouched → same as baseline
                    est_pnls.append(row["base_pnl"])
                elif row["base_touched"]:
                    # Already touched at baseline → assume same exit
                    est_pnls.append(row["base_pnl"])
                else:
                    # NEWLY touched at this fraction → estimate exit near target
                    target = row["frac_target"]
                    if pd.isna(target):
                        est_pnls.append(row["base_pnl"])
                    elif row["direction"] == "long":
                        est_pnl = target - row["entry_price"]
                        est_pnls.append(est_pnl)
                    else:
                        est_pnl = row["entry_price"] - target
                        est_pnls.append(est_pnl)

            est_ev = np.mean(est_pnls)
            est_ev_pct = est_ev / baseline["entry_price"].mean() * 100
            valid = fdf[fdf["has_valid_target"]]
            touch_rate = valid["touched"].mean() * 100 if len(valid) > 0 else 0
            delta = est_ev - base_ev

            marker = " ←baseline" if frac == 1.0 else ""
            print(f"  {frac:<8.2f} {est_ev:>12.1f} {est_ev_pct:>9.3f}% "
                  f"{touch_rate:>10.1f}% {delta:>+7.1f}{marker}")

    # By year for key fractions
    print("\n" + "-" * 70)
    print("ESTIMATED EV BY YEAR (selected fractions)")
    print("-" * 70)

    for strat in all_results["strategy"].unique():
        sdf = all_results[all_results["strategy"] == strat]
        baseline_all = sdf[sdf["fraction"] == 1.0]

        print(f"\n{strat}")
        print(f"{'Year':<8} {'f=1.0 EV':>10} {'f=0.90 EV':>10} "
              f"{'f=0.85 EV':>10} {'N':>6}")
        print("-" * 50)

        for year in sorted(baseline_all["year"].unique()):
            baseline = baseline_all[baseline_all["year"] == year]
            n = len(baseline)
            evs = {}
            for frac in [1.0, 0.90, 0.85]:
                fdf = sdf[(sdf["fraction"] == frac) & (sdf["year"] == year)]
                merged = baseline[["entry_date", "direction", "entry_price",
                                   "pnl", "touched"]].copy()
                merged.columns = ["entry_date", "direction", "entry_price",
                                  "base_pnl", "base_touched"]
                frac_info = fdf[["entry_date", "touched", "target_at_touch"]].copy()
                frac_info.columns = ["entry_date", "frac_touched", "frac_target"]
                merged = merged.merge(frac_info, on="entry_date", how="left")

                pnls = []
                for _, row in merged.iterrows():
                    if not row["frac_touched"] or pd.isna(row["frac_touched"]):
                        pnls.append(row["base_pnl"])
                    elif row["base_touched"]:
                        pnls.append(row["base_pnl"])
                    else:
                        target = row["frac_target"]
                        if pd.isna(target):
                            pnls.append(row["base_pnl"])
                        elif row["direction"] == "long":
                            pnls.append(target - row["entry_price"])
                        else:
                            pnls.append(row["entry_price"] - target)
                evs[frac] = np.mean(pnls) if pnls else 0

            print(f"  {year:<6} {evs[1.0]:>+8.1f} {evs[0.90]:>+8.1f} "
                  f"{evs[0.85]:>+8.1f} {n:>6}")


def main():
    all_results = []

    for name, config in STRATEGIES.items():
        df, trades = run_baseline_backtest(name, config)
        if trades.empty:
            print(f"  {name}: no trades, skipping")
            continue
        results = analyze_touch_rates(df, trades, name)
        all_results.append(results)

    if not all_results:
        print("No trades found for any strategy!")
        sys.exit(1)

    combined = pd.concat(all_results, ignore_index=True)

    # Print all analyses
    print_touch_rate_table(combined)
    print_untouched_pnl(combined)
    print_remaining_continuation(combined)
    estimate_ev_by_fraction(combined)

    # Save raw results
    out_dir = Path("research/active/H047-satzone-fraction-tuning/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_dir / "exploration_raw.csv", index=False)
    print(f"\nRaw data saved → {out_dir / 'exploration_raw.csv'}")


if __name__ == "__main__":
    main()

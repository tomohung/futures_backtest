#!/usr/bin/env python3
"""H047 Phase 2: SatZone Fraction 策略別調校 — 回測驗證。

對三個策略分別測試不同 SatZone fraction，比較 IS/OOS 績效。
- IS: 2022-01-01 ~ 2024-12-31
- OOS: 2025-01-01 ~ 2026-12-31
- Fraction 範圍: 0.80 ~ 1.00 (step 0.05)

方法：調整 DataFrame 中的 SatZoneUpper/SatZoneLower 欄位，
使 zone_distance *= fraction，然後跑原始策略回測。

Usage:
    uv run python research/active/H047-satzone-fraction-tuning/backtest.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    load_data_for_exhaustion,
    print_summary,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy
from src.strategies.exhaustion import ExhaustionStrategy

FRACTIONS = [0.80, 0.85, 0.90, 0.95, 1.00]
IS_START, IS_END = "2022-01-01", "2024-12-31"
OOS_START, OOS_END = "2025-01-01", "2026-12-31"

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


def adjust_satzone(df: pd.DataFrame, fraction: float) -> pd.DataFrame:
    """Adjust SatZoneUpper/Lower by fraction.

    zone_dist_upper = SatZoneUpper - SessionLow
    SatZoneUpper_frac = SessionLow + fraction * zone_dist_upper

    zone_dist_lower = SessionHigh - SatZoneLower
    SatZoneLower_frac = SessionHigh - fraction * zone_dist_lower
    """
    if fraction == 1.0:
        return df

    df = df.copy()
    dates = df.index.date
    unique_dates = pd.Series(dates).unique()

    for d in unique_dates:
        mask = dates == d
        day_df = df.loc[mask]

        # Cumulative session extremes
        session_low = day_df["Low"].cummin()
        session_high = day_df["High"].cummax()

        # Adjust upper zone
        sat_upper = df.loc[mask, "SatZoneUpper"]
        zone_dist_upper = sat_upper - session_low
        df.loc[mask, "SatZoneUpper"] = session_low + fraction * zone_dist_upper

        # Adjust lower zone
        sat_lower = df.loc[mask, "SatZoneLower"]
        zone_dist_lower = session_high - sat_lower
        df.loc[mask, "SatZoneLower"] = session_high - fraction * zone_dist_lower

    return df


def run_backtest(df: pd.DataFrame, strategy_cls, params: dict,
                 start: str, end: str) -> dict | None:
    """Run backtest on a date range and return summary stats."""
    period_df = df[(df.index >= start) & (df.index <= end)]
    if period_df.empty:
        return None

    bt = Backtest(period_df, strategy_cls,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"]

    if trades.empty:
        return {
            "n_trades": 0, "wr": 0, "ev_pts": 0, "ev_pct": 0,
            "pf": 0, "total_pts": 0, "trades": trades,
        }

    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    entry_prices = trades["EntryPrice"]

    pnl_pct = pnl / entry_prices * 100

    return {
        "n_trades": len(trades),
        "wr": (pnl > 0).mean() * 100,
        "ev_pts": pnl.mean(),
        "ev_pct": pnl_pct.mean(),
        "pf": wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float("inf"),
        "total_pts": pnl.sum(),
        "trades": trades,
    }


def run_yearly_breakdown(df: pd.DataFrame, strategy_cls, params: dict,
                         years: list[int]) -> dict[int, dict]:
    """Run backtest per year."""
    results = {}
    for year in years:
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        r = run_backtest(df, strategy_cls, params, start, end)
        if r is not None:
            results[year] = r
    return results


def main():
    out_dir = Path("research/active/H047-satzone-fraction-tuning/results")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    for name, config in STRATEGIES.items():
        print(f"\n{'='*70}")
        print(f"STRATEGY: {name}")
        print(f"{'='*70}")

        print("Loading data...")
        df_full = config["loader"]()
        print(f"  {len(df_full):,} bars  [{df_full.index[0]} → {df_full.index[-1]}]")

        for frac in FRACTIONS:
            print(f"\n--- fraction={frac:.2f} ---")
            df_adj = adjust_satzone(df_full, frac)

            # IS
            is_result = run_backtest(df_adj, config["strategy"], config["params"],
                                     IS_START, IS_END)
            # OOS
            oos_result = run_backtest(df_adj, config["strategy"], config["params"],
                                      OOS_START, OOS_END)

            if is_result:
                print(f"  IS  2022-2024: N={is_result['n_trades']}, "
                      f"WR={is_result['wr']:.1f}%, "
                      f"EV={is_result['ev_pts']:+.1f}pts, "
                      f"EV%={is_result['ev_pct']:+.4f}%, "
                      f"PF={is_result['pf']:.2f}")
            if oos_result:
                print(f"  OOS 2025-2026: N={oos_result['n_trades']}, "
                      f"WR={oos_result['wr']:.1f}%, "
                      f"EV={oos_result['ev_pts']:+.1f}pts, "
                      f"EV%={oos_result['ev_pct']:+.4f}%, "
                      f"PF={oos_result['pf']:.2f}")

            # Yearly breakdown
            yearly = run_yearly_breakdown(df_adj, config["strategy"], config["params"],
                                          [2022, 2023, 2024, 2025, 2026])

            for year, yr in yearly.items():
                all_results.append({
                    "strategy": name,
                    "fraction": frac,
                    "period": "IS" if year <= 2024 else "OOS",
                    "year": year,
                    "n_trades": yr["n_trades"],
                    "wr": yr["wr"],
                    "ev_pts": yr["ev_pts"],
                    "ev_pct": yr["ev_pct"],
                    "pf": yr["pf"],
                    "total_pts": yr["total_pts"],
                })

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(out_dir / "backtest_raw.csv", index=False)
    print(f"\nRaw results saved → {out_dir / 'backtest_raw.csv'}")

    # ==========================================
    # Summary tables
    # ==========================================
    print("\n" + "=" * 80)
    print("PHASE 2 BACKTEST SUMMARY")
    print("=" * 80)

    for name in STRATEGIES:
        sdf = results_df[results_df["strategy"] == name]
        baseline = sdf[sdf["fraction"] == 1.0]

        print(f"\n{'─'*70}")
        print(f"  {name}")
        print(f"{'─'*70}")

        # IS summary
        print(f"\n  IS (2022-2024):")
        print(f"  {'Fraction':<10} {'N':>5} {'WR':>8} {'EV(pts)':>10} "
              f"{'EV%':>10} {'PF':>8} {'Total':>10}")
        print(f"  {'-'*56}")
        for frac in FRACTIONS:
            fdf = sdf[(sdf["fraction"] == frac) & (sdf["period"] == "IS")]
            if fdf.empty:
                continue
            n = fdf["n_trades"].sum()
            ev = fdf["ev_pts"].mean()  # average across years
            ev_pct = fdf["ev_pct"].mean()
            # Weighted WR and PF from total trades
            total_pts = fdf["total_pts"].sum()
            # Compute overall WR as weighted average
            wr = (fdf["wr"] * fdf["n_trades"]).sum() / n if n > 0 else 0
            pf_num = fdf[fdf["total_pts"] > 0]["total_pts"].sum()
            pf_den = abs(fdf[fdf["total_pts"] < 0]["total_pts"].sum())
            # Simple: use total_pts / n for EV, then compute PF from yearly
            marker = " ←base" if frac == 1.0 else ""
            print(f"  {frac:<10.2f} {n:>5} {wr:>7.1f}% {ev:>+9.1f} "
                  f"{ev_pct:>+9.4f}% {'-':>8} {total_pts:>+9.0f}{marker}")

        # OOS summary
        print(f"\n  OOS (2025-2026):")
        print(f"  {'Fraction':<10} {'N':>5} {'WR':>8} {'EV(pts)':>10} "
              f"{'EV%':>10} {'Total':>10}")
        print(f"  {'-'*48}")
        for frac in FRACTIONS:
            fdf = sdf[(sdf["fraction"] == frac) & (sdf["period"] == "OOS")]
            if fdf.empty:
                continue
            n = fdf["n_trades"].sum()
            ev = fdf["ev_pts"].mean()
            ev_pct = fdf["ev_pct"].mean()
            total_pts = fdf["total_pts"].sum()
            wr = (fdf["wr"] * fdf["n_trades"]).sum() / n if n > 0 else 0
            marker = " ←base" if frac == 1.0 else ""
            print(f"  {frac:<10.2f} {n:>5} {wr:>7.1f}% {ev:>+9.1f} "
                  f"{ev_pct:>+9.4f}% {total_pts:>+9.0f}{marker}")

        # Year-by-year consistency check (EV% >= baseline each year)
        print(f"\n  Yearly EV (pts) by fraction:")
        print(f"  {'Year':<8}", end="")
        for frac in FRACTIONS:
            print(f" {'f='+str(frac):>10}", end="")
        print(f" {'Pass?':>8}")
        print(f"  {'-'*68}")

        for year in [2022, 2023, 2024, 2025, 2026]:
            ydf = sdf[sdf["year"] == year]
            if ydf.empty:
                continue
            base_ev = ydf[ydf["fraction"] == 1.0]["ev_pts"].values
            base_ev = base_ev[0] if len(base_ev) > 0 else 0

            print(f"  {year:<8}", end="")
            best_frac = None
            best_ev = -np.inf
            for frac in FRACTIONS:
                fev = ydf[ydf["fraction"] == frac]["ev_pts"].values
                ev = fev[0] if len(fev) > 0 else 0
                if frac != 1.0 and ev > best_ev:
                    best_ev = ev
                    best_frac = frac
                marker = "*" if ev > base_ev and frac != 1.0 else " "
                print(f" {ev:>+9.1f}{marker}", end="")

            # Check: does best fraction beat baseline this year?
            passes = best_ev >= base_ev if best_frac else False
            print(f" {'✓' if passes else '✗':>8}")

        print()

    # ==========================================
    # Final comparison: best fraction per strategy
    # ==========================================
    print("\n" + "=" * 80)
    print("BEST FRACTION PER STRATEGY (IS period, 2022-2024)")
    print("=" * 80)

    for name in STRATEGIES:
        sdf = results_df[(results_df["strategy"] == name) & (results_df["period"] == "IS")]

        best_frac = None
        best_ev = -np.inf
        for frac in [f for f in FRACTIONS if f < 1.0]:
            fdf = sdf[sdf["fraction"] == frac]
            # Check yearly consistency: EV >= baseline every year
            consistent = True
            for year in [2022, 2023, 2024]:
                fev = fdf[fdf["year"] == year]["ev_pts"].values
                bev = sdf[(sdf["fraction"] == 1.0) & (sdf["year"] == year)]["ev_pts"].values
                if len(fev) == 0 or len(bev) == 0:
                    continue
                if fev[0] < bev[0]:
                    consistent = False
                    break

            total_ev = fdf["total_pts"].sum()
            if consistent and total_ev > best_ev:
                best_ev = total_ev
                best_frac = frac

        base_total = sdf[sdf["fraction"] == 1.0]["total_pts"].sum()
        print(f"\n  {name}:")
        print(f"    Baseline (f=1.0): {base_total:+.0f} pts total")
        if best_frac:
            print(f"    Best consistent:  f={best_frac:.2f} → {best_ev:+.0f} pts total "
                  f"(Δ={best_ev-base_total:+.0f})")

            # OOS check
            oos_base = results_df[(results_df["strategy"] == name) &
                                  (results_df["fraction"] == 1.0) &
                                  (results_df["period"] == "OOS")]["total_pts"].sum()
            oos_best = results_df[(results_df["strategy"] == name) &
                                  (results_df["fraction"] == best_frac) &
                                  (results_df["period"] == "OOS")]["total_pts"].sum()
            print(f"    OOS base:  {oos_base:+.0f} pts")
            print(f"    OOS best:  {oos_best:+.0f} pts (Δ={oos_best-oos_base:+.0f})")
        else:
            print(f"    No fraction consistently beats baseline across all IS years")


if __name__ == "__main__":
    main()

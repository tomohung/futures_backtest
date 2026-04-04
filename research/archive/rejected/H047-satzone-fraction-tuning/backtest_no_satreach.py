#!/usr/bin/env python3
"""H047 補充測試：取消 _satzone_reached entry-blocking，純測 fraction 對出場的影響。

對比 backtest.py 的結果，隔離 fraction 對出場 vs 進場阻擋的效果。

Usage:
    uv run python research/active/H047-satzone-fraction-tuning/backtest_no_satreach.py
"""

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
from src.strategies.estimate_hl_exit import EstimateHLExitMixin

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


# --- Subclasses that disable _satzone_reached ---

class NoSatReachMixin:
    """Override _record_bar to never set _satzone_reached."""
    def _record_bar(self) -> None:
        cur_date = self.data.index[-1].date()
        if cur_date != self._hl_prev_date:
            self._reset_estimate_hl_exit()
            self._hl_prev_date = cur_date
        # Skip the _satzone_reached logic entirely
        self._close_buffer.append(float(self.data.Close[-1]))


class S001_NoSatReach(NoSatReachMixin, ORBWithEstHLExitStrategy):
    pass

class S002_NoSatReach(NoSatReachMixin, ReversalStrategy):
    pass

class S003_NoSatReach(NoSatReachMixin, ExhaustionStrategy):
    pass


STRATEGIES = {
    "S001": {
        "loader": load_data_for_orb_est_hl,
        "strategy_orig": ORBWithEstHLExitStrategy,
        "strategy_nosr": S001_NoSatReach,
        "params": S001_PARAMS,
    },
    "S002": {
        "loader": load_data_for_reversal,
        "strategy_orig": ReversalStrategy,
        "strategy_nosr": S002_NoSatReach,
        "params": S002_PARAMS,
    },
    "S003": {
        "loader": load_data_for_exhaustion,
        "strategy_orig": ExhaustionStrategy,
        "strategy_nosr": S003_NoSatReach,
        "params": S003_PARAMS,
    },
}


def adjust_satzone(df: pd.DataFrame, fraction: float) -> pd.DataFrame:
    if fraction == 1.0:
        return df
    df = df.copy()
    dates = df.index.date
    unique_dates = pd.Series(dates).unique()
    for d in unique_dates:
        mask = dates == d
        day_df = df.loc[mask]
        session_low = day_df["Low"].cummin()
        session_high = day_df["High"].cummax()
        sat_upper = df.loc[mask, "SatZoneUpper"]
        zone_dist_upper = sat_upper - session_low
        df.loc[mask, "SatZoneUpper"] = session_low + fraction * zone_dist_upper
        sat_lower = df.loc[mask, "SatZoneLower"]
        zone_dist_lower = session_high - sat_lower
        df.loc[mask, "SatZoneLower"] = session_high - fraction * zone_dist_lower
    return df


def run_backtest(df, strategy_cls, params, start, end):
    period_df = df[(df.index >= start) & (df.index <= end)]
    if period_df.empty:
        return None
    bt = Backtest(period_df, strategy_cls,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"]
    if trades.empty:
        return {"n_trades": 0, "wr": 0, "ev_pts": 0, "ev_pct": 0,
                "pf": 0, "total_pts": 0}
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    pnl_pct = pnl / trades["EntryPrice"] * 100
    return {
        "n_trades": len(trades),
        "wr": (pnl > 0).mean() * 100,
        "ev_pts": pnl.mean(),
        "ev_pct": pnl_pct.mean(),
        "pf": wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float("inf"),
        "total_pts": pnl.sum(),
    }


def main():
    out_dir = Path("research/active/H047-satzone-fraction-tuning/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for name, config in STRATEGIES.items():
        print(f"\n{'='*70}")
        print(f"STRATEGY: {name}")
        print(f"{'='*70}")

        df_full = config["loader"]()
        print(f"  {len(df_full):,} bars")

        for mode_label, strat_cls in [("with_satreach", config["strategy_orig"]),
                                       ("no_satreach", config["strategy_nosr"])]:
            print(f"\n  --- {mode_label} ---")
            for frac in FRACTIONS:
                df_adj = adjust_satzone(df_full, frac)

                for period_label, start, end in [("IS", IS_START, IS_END),
                                                  ("OOS", OOS_START, OOS_END)]:
                    r = run_backtest(df_adj, strat_cls, config["params"], start, end)
                    if r:
                        all_rows.append({
                            "strategy": name, "mode": mode_label,
                            "fraction": frac, "period": period_label, **r,
                        })

                # Also per-year
                for year in [2022, 2023, 2024, 2025, 2026]:
                    r = run_backtest(df_adj, strat_cls, config["params"],
                                     f"{year}-01-01", f"{year}-12-31")
                    if r:
                        all_rows.append({
                            "strategy": name, "mode": mode_label,
                            "fraction": frac, "period": str(year), **r,
                        })

    results = pd.DataFrame(all_rows)
    results.to_csv(out_dir / "backtest_no_satreach_raw.csv", index=False)

    # ==========================================
    # Comparison tables
    # ==========================================
    print("\n" + "=" * 80)
    print("COMPARISON: with_satreach vs no_satreach")
    print("=" * 80)

    for name in STRATEGIES:
        sdf = results[results["strategy"] == name]

        print(f"\n{'─'*70}")
        print(f"  {name}")
        print(f"{'─'*70}")

        for period in ["IS", "OOS"]:
            print(f"\n  {period}:")
            print(f"  {'Frac':<6} │ {'with_satreach':^28} │ {'no_satreach':^28} │")
            print(f"  {'':6} │ {'N':>5} {'EV':>8} {'PF':>6} {'Total':>7} │"
                  f" {'N':>5} {'EV':>8} {'PF':>6} {'Total':>7} │")
            print(f"  {'─'*6}─┼{'─'*28}─┼{'─'*28}─┤")

            for frac in FRACTIONS:
                row_w = sdf[(sdf["mode"] == "with_satreach") &
                            (sdf["fraction"] == frac) & (sdf["period"] == period)]
                row_n = sdf[(sdf["mode"] == "no_satreach") &
                            (sdf["fraction"] == frac) & (sdf["period"] == period)]

                def fmt(row):
                    if row.empty:
                        return "     -        -      -       -"
                    r = row.iloc[0]
                    return (f"{r['n_trades']:>5} {r['ev_pts']:>+7.1f} "
                            f"{r['pf']:>5.2f} {r['total_pts']:>+7.0f}")

                marker = " ←" if frac == 1.0 else "  "
                print(f"  {frac:<6.2f}│ {fmt(row_w)} │ {fmt(row_n)} │{marker}")

        # Yearly consistency for no_satreach
        print(f"\n  no_satreach 逐年 EV (pts):")
        print(f"  {'Year':<6}", end="")
        for frac in FRACTIONS:
            print(f" {'f='+str(frac):>10}", end="")
        print(f" {'Pass?':>8}")
        print(f"  {'─'*66}")

        for year in [2022, 2023, 2024, 2025, 2026]:
            ydf = sdf[(sdf["mode"] == "no_satreach") & (sdf["period"] == str(year))]
            if ydf.empty:
                continue
            base_ev = ydf[ydf["fraction"] == 1.0]["ev_pts"].values
            base_ev = base_ev[0] if len(base_ev) > 0 else 0
            print(f"  {year:<6}", end="")
            best_ev = -np.inf
            for frac in FRACTIONS:
                fev = ydf[ydf["fraction"] == frac]["ev_pts"].values
                ev = fev[0] if len(fev) > 0 else 0
                if frac != 1.0 and ev > best_ev:
                    best_ev = ev
                marker = "*" if ev > base_ev and frac != 1.0 else " "
                print(f" {ev:>+9.1f}{marker}", end="")
            passes = best_ev >= base_ev
            print(f" {'✓' if passes else '✗':>8}")

    print(f"\nRaw results saved → {out_dir / 'backtest_no_satreach_raw.csv'}")


if __name__ == "__main__":
    main()

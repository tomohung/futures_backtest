"""
H048 Phase 2: Backtest BB latch start time = 09:05.

- In-sample: 2021-01-01 ~ 2024-12-31
- Out-of-sample: 2025-01-01 ~ 2026-03-26
- Parameter sensitivity: 08:45, 09:00, 09:05, 09:10, 09:15
- Walk-forward: rolling 2-year IS / 1-year OOS
"""

from datetime import time as dtime

import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


def make_gated_strategy(setup_start="09:05"):
    """Create a ReversalStrategy subclass with gated BB latch start."""
    h, m = map(int, setup_start.split(":"))
    gate_time = dtime(h, m)

    class GatedReversal(ReversalStrategy):
        def next(self):
            cur_ts = self.data.index[-1]
            cur_time = cur_ts.time()
            cur_date = cur_ts.date()

            if cur_time < gate_time and not self.position:
                if cur_date != self._prev_date:
                    self._reset_daily()
                    self._prev_date = cur_date
                    self._open_price = float(self.data.Open[-1])
                    self._day_low = float(self.data.Low[-1])
                    self._day_high = float(self.data.High[-1])
                    bc1 = float(self.data.VWAP1[-1])
                    bc2 = float(self.data.VWAP2[-1])
                    if not (np.isnan(bc1) or np.isnan(bc2)):
                        bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
                        if self._open_price > bc_hi:
                            self._allow_long = True
                        elif self._open_price < bc_lo:
                            self._allow_short = True
                        else:
                            self._bc_inside = True
                if self._day_low is not None:
                    self._day_low = min(self._day_low, float(self.data.Low[-1]))
                    self._day_high = max(self._day_high, float(self.data.High[-1]))
                self._record_bar()
                return
            super().next()

    GatedReversal.__name__ = f"Reversal_{setup_start.replace(':', '')}"
    return GatedReversal


def run_bt(df, strategy_cls):
    bt = Backtest(df, strategy_cls, cash=1_000_000, commission=0.00004,
                  exclusive_orders=True, trade_on_close=True)
    return bt.run()


def metrics(stats, label=""):
    trades = stats["_trades"]
    if trades.empty:
        return {"label": label, "n": 0, "win%": "—", "avg_pnl": 0,
                "total": 0, "pf": 0, "avg_pnl_pct": 0, "sharpe_pct": 0}
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    # PnL% = PnL / entry_price * 100
    entry_prices = trades["EntryPrice"]
    pnl_pct = pnl / entry_prices * 100

    sharpe_pct = pnl_pct.mean() / pnl_pct.std() * (252 ** 0.5) if pnl_pct.std() > 0 else 0

    return {
        "label": label,
        "n": len(trades),
        "win%": f"{len(wins)/len(trades)*100:.1f}%",
        "avg_pnl": round(pnl.mean(), 1),
        "total": round(pnl.sum(), 0),
        "pf": round(wins.sum() / abs(losses.sum()), 2) if len(losses) else float("inf"),
        "avg_pnl_pct": round(pnl_pct.mean(), 4),
        "sharpe_pct": round(sharpe_pct, 2),
    }


def print_table(rows, title=""):
    if title:
        print(f"\n{'=' * 90}")
        print(title)
        print('=' * 90)
    headers = ["Label", "Trades", "Win%", "Avg PnL", "Total PnL", "PF", "Avg PnL%", "Sharpe"]
    fmt = "{:<20} {:>6} {:>6} {:>8} {:>10} {:>6} {:>9} {:>7}"
    print(fmt.format(*headers))
    print("-" * 90)
    for r in rows:
        print(fmt.format(
            r["label"], r["n"], r["win%"], r["avg_pnl"], r["total"],
            r["pf"], f"{r['avg_pnl_pct']:.4f}", r["sharpe_pct"]
        ))


def main():
    print("Loading data...")
    df = load_data_for_reversal()
    print(f"  {len(df)} bars, {df.index[0].date()} ~ {df.index[-1].date()}")

    # Split periods
    is_df = df[df.index < "2025-01-01"]
    oos_df = df[df.index >= "2025-01-01"]
    print(f"  IS: {is_df.index[0].date()} ~ {is_df.index[-1].date()}")
    print(f"  OOS: {oos_df.index[0].date()} ~ {oos_df.index[-1].date()}")

    # ── 1. IS/OOS comparison: baseline vs 09:05 ────────────────────────
    print("\n[Phase 2] In-Sample vs Out-of-Sample")

    baseline_cls = ReversalStrategy
    gated_cls = make_gated_strategy("09:05")

    is_results = []
    oos_results = []
    for label, cls in [("08:45 (baseline)", baseline_cls), ("09:05", gated_cls)]:
        is_stats = run_bt(is_df, cls)
        oos_stats = run_bt(oos_df, cls)
        is_results.append(metrics(is_stats, f"{label} IS"))
        oos_results.append(metrics(oos_stats, f"{label} OOS"))

    print_table(is_results + oos_results, "In-Sample (2021-2024) vs Out-of-Sample (2025-2026)")

    # ── 2. Parameter sensitivity: 08:45 ~ 09:15 every 5 min ────────────
    print("\n[Phase 2] Parameter Sensitivity (full period)")

    sensitivity = ["08:45", "09:00", "09:05", "09:10", "09:15"]
    sens_results = []
    for start in sensitivity:
        if start == "08:45":
            cls = ReversalStrategy
        else:
            cls = make_gated_strategy(start)
        stats = run_bt(df, cls)
        sens_results.append(metrics(stats, start))

    print_table(sens_results, f"Sensitivity: BB Latch Start (full period)")

    # IS-only sensitivity
    sens_is = []
    sens_oos = []
    for start in sensitivity:
        if start == "08:45":
            cls = ReversalStrategy
        else:
            cls = make_gated_strategy(start)
        sens_is.append(metrics(run_bt(is_df, cls), f"{start} IS"))
        sens_oos.append(metrics(run_bt(oos_df, cls), f"{start} OOS"))

    print_table(sens_is, "Sensitivity: IS (2021-2024)")
    print_table(sens_oos, "Sensitivity: OOS (2025-2026)")

    # ── 3. Walk-forward: rolling 2yr IS / 1yr OOS ──────────────────────
    print("\n[Phase 2] Walk-Forward (2yr IS → 1yr OOS)")

    wf_windows = [
        ("2021-2022 → 2023", "2021", "2023", "2023", "2024"),
        ("2022-2023 → 2024", "2022", "2024", "2024", "2025"),
        ("2023-2024 → 2025", "2023", "2025", "2025", "2026"),
    ]

    wf_rows = []
    for wf_label, is_start, is_end, oos_start, oos_end in wf_windows:
        wf_is = df[(df.index >= is_start) & (df.index < is_end)]
        wf_oos = df[(df.index >= oos_start) & (df.index < oos_end)]

        for strat_label, cls in [("08:45", ReversalStrategy),
                                  ("09:05", make_gated_strategy("09:05"))]:
            is_m = metrics(run_bt(wf_is, cls), f"{strat_label} IS {wf_label}")
            oos_m = metrics(run_bt(wf_oos, cls), f"{strat_label} OOS {wf_label}")
            wf_rows.append(is_m)
            wf_rows.append(oos_m)

    print_table(wf_rows, "Walk-Forward Results")

    # ── 4. Year-by-year for 08:45 vs 09:05 ─────────────────────────────
    print("\n" + "=" * 90)
    print("Year-by-Year: 08:45 vs 09:05")
    print("=" * 90)

    for strat_label, cls in [("08:45 (baseline)", ReversalStrategy),
                              ("09:05", make_gated_strategy("09:05"))]:
        stats = run_bt(df, cls)
        trades = stats["_trades"].copy()
        trades["year"] = pd.to_datetime(trades["EntryTime"]).dt.year
        trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100

        print(f"\n  [{strat_label}]")
        print(f"  {'Year':<6} {'Trades':>7} {'Win%':>6} {'Avg PnL':>8} {'Total':>8} {'PF':>6} {'Avg%':>8} {'Sharpe':>7}")
        for yr, grp in trades.groupby("year"):
            pnl = grp["PnL"]
            pnl_pct = grp["pnl_pct"]
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            wr = len(wins) / len(pnl) * 100 if len(pnl) else 0
            pf = wins.sum() / abs(losses.sum()) if len(losses) else float("inf")
            sh = pnl_pct.mean() / pnl_pct.std() * (252 ** 0.5) if pnl_pct.std() > 0 else 0
            print(f"  {yr:<6} {len(pnl):>7} {wr:>5.1f}% {pnl.mean():>8.1f} {pnl.sum():>8.0f} {pf:>6.2f} {pnl_pct.mean():>7.4f} {sh:>7.2f}")

    print("\nDone.")


if __name__ == "__main__":
    main()

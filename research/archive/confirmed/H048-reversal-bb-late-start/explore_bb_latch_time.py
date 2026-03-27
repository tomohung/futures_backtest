"""
H048: Explore BB latch timing vs trade outcomes.

Runs the Reversal strategy with different BB latch start times
(08:45, 09:00, 09:05, 09:10) and compares trade quality.

BB(15) on 1m bars needs ~15 bars to reflect today's price action.
08:45 start is contaminated by previous day's close (overnight gap).
09:00 is the mathematical minimum for valid BB values.
"""

from datetime import time as dtime
import numpy as np
import pandas as pd
from backtesting import Backtest
from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


def run_backtest(df, setup_start="08:45", **kwargs):
    """Run reversal backtest with a specific BB latch start time."""
    h, m = map(int, setup_start.split(":"))
    gate_time = dtime(h, m)

    class GatedReversal(ReversalStrategy):
        def next(self):
            cur_ts = self.data.index[-1]
            cur_time = cur_ts.time()
            cur_date = cur_ts.date()

            if cur_time < gate_time and not self.position:
                # Day rollover
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

    bt = Backtest(df, GatedReversal, cash=1_000_000, commission=0.00004,
                  exclusive_orders=True, trade_on_close=True)
    return bt.run(**kwargs)


def run_baseline_with_latch_log(df, **kwargs):
    """Run baseline (08:45) and capture BB latch timing."""
    latch_log = []

    class LoggingReversal(ReversalStrategy):
        def _reset_daily(self):
            super()._reset_daily()
            self._latch_logged_long = False
            self._latch_logged_short = False

        def next(self):
            was_long = self._bb_long_touched
            was_short = self._bb_short_touched

            super().next()

            cur_ts = self.data.index[-1]
            cur_date = cur_ts.date()
            cur_time = cur_ts.time()

            if not was_long and self._bb_long_touched and not self._latch_logged_long:
                latch_log.append({"date": cur_date, "latch_time": cur_time, "direction": "long"})
                self._latch_logged_long = True
            if not was_short and self._bb_short_touched and not self._latch_logged_short:
                latch_log.append({"date": cur_date, "latch_time": cur_time, "direction": "short"})
                self._latch_logged_short = True

    bt = Backtest(df, LoggingReversal, cash=1_000_000, commission=0.00004,
                  exclusive_orders=True, trade_on_close=True)
    stats = bt.run(**kwargs)
    return stats, latch_log


def analyze_trades(stats, label):
    trades = stats["_trades"]
    if trades.empty:
        return {"label": label, "n_trades": 0, "win_rate": "—", "avg_pnl": 0,
                "total_pnl": 0, "pf": 0, "avg_win": 0, "avg_loss": 0,
                "n_long": 0, "n_short": 0}
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "label": label,
        "n_trades": len(trades),
        "n_long": (trades["Size"] > 0).sum(),
        "n_short": (trades["Size"] < 0).sum(),
        "win_rate": f"{len(wins)/len(trades)*100:.1f}%",
        "avg_pnl": round(pnl.mean(), 1),
        "total_pnl": round(pnl.sum(), 0),
        "pf": round(wins.sum() / abs(losses.sum()), 2) if len(losses) else float("inf"),
        "avg_win": round(wins.mean(), 1) if len(wins) else 0,
        "avg_loss": round(losses.mean(), 1) if len(losses) else 0,
    }


def main():
    print("Loading data...")
    df = load_data_for_reversal()
    print(f"  {len(df)} bars, {df.index[0].date()} ~ {df.index[-1].date()}")

    # ── Baseline with latch logging ─────────────────────────────────────
    print("\n[1] Running baseline (08:45) with latch logging...")
    stats_base, latch_log = run_baseline_with_latch_log(df)

    latch_df = pd.DataFrame(latch_log)
    if not latch_df.empty:
        latch_df["latch_minute"] = latch_df["latch_time"].apply(
            lambda t: t.hour * 60 + t.minute
        )
        bins = [
            ("08:45~08:59", 525, 539),
            ("09:00~09:04", 540, 544),
            ("09:05~09:09", 545, 549),
            ("09:10~09:14", 550, 554),
            ("09:15~09:29", 555, 569),
            ("09:30~09:59", 570, 599),
            ("10:00~10:05", 600, 605),
        ]
        print("\n  BB Latch 首次觸發時間分佈：")
        print(f"  {'時段':<16} {'次數':>6} {'占比':>8}")
        print(f"  {'-'*32}")
        for label, lo, hi in bins:
            n = ((latch_df["latch_minute"] >= lo) & (latch_df["latch_minute"] <= hi)).sum()
            pct = n / len(latch_df) * 100
            print(f"  {label:<16} {n:>6} {pct:>7.1f}%")

    # ── Run 4 variants ──────────────────────────────────────────────────
    configs = [
        ("08:45 (baseline)", "08:45"),
        ("09:00", "09:00"),
        ("09:05", "09:05"),
        ("09:10", "09:10"),
    ]

    all_stats = {}
    results = []
    for label, start in configs:
        print(f"\n[Running] setup_start={start}...")
        if start == "08:45":
            stats = stats_base
        else:
            stats = run_backtest(df, setup_start=start)
        all_stats[start] = stats
        results.append(analyze_trades(stats, label))

    # ── Comparison table ────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("BB Latch Start Time 比較")
    print("=" * 85)
    headers = ["Setup Start", "Trades", "Long", "Short", "Win%", "Avg PnL", "Total PnL", "PF", "Avg Win", "Avg Loss"]
    fmt = "{:<18} {:>6} {:>5} {:>5} {:>6} {:>8} {:>10} {:>6} {:>8} {:>9}"
    print(fmt.format(*headers))
    print("-" * 85)
    for r in results:
        print(fmt.format(
            r["label"], r["n_trades"], r["n_long"], r["n_short"],
            r["win_rate"], r["avg_pnl"], r["total_pnl"],
            r["pf"], r["avg_win"], r["avg_loss"]
        ))

    # ── Delta vs baseline ───────────────────────────────────────────────
    base = results[0]
    print(f"\n  vs baseline 差異：")
    for r in results[1:]:
        trade_delta = r["n_trades"] - base["n_trades"]
        pnl_delta = r["total_pnl"] - base["total_pnl"]
        pf_delta = r["pf"] - base["pf"]
        print(f"    {r['label']:<8}  trades {trade_delta:+d} ({trade_delta/base['n_trades']*100:+.1f}%)  "
              f"total_pnl {pnl_delta:+.0f}  PF {pf_delta:+.2f}")

    # ── Early latch trade outcomes (baseline split) ─────────────────────
    trades_base = stats_base["_trades"].copy()
    if not latch_df.empty and not trades_base.empty:
        trades_base["trade_date"] = pd.to_datetime(trades_base["EntryTime"]).dt.date

        time_cuts = [
            ("08:45~09:00", 525, 540),
            ("09:00~09:05", 540, 545),
            ("09:05~09:10", 545, 550),
            ("≥09:10", 550, 999),
        ]

        print("\n" + "=" * 85)
        print("BB Latch 觸發時段 vs 交易結果（Baseline 拆分）")
        print("=" * 85)
        print(f"  {'時段':<16} {'交易數':>6} {'Win%':>6} {'Avg PnL':>8} {'Total':>8} {'PF':>6}")
        print(f"  {'-'*54}")

        for label, lo, hi in time_cuts:
            dates = set(latch_df[(latch_df["latch_minute"] >= lo) &
                                  (latch_df["latch_minute"] < hi)]["date"])
            subset = trades_base[trades_base["trade_date"].isin(dates)]
            if subset.empty:
                print(f"  {label:<16} {'—':>6}")
                continue
            pnl = subset["PnL"]
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            wr = len(wins) / len(pnl) * 100
            pf = wins.sum() / abs(losses.sum()) if len(losses) else float("inf")
            print(f"  {label:<16} {len(pnl):>6} {wr:>5.1f}% {pnl.mean():>8.1f} {pnl.sum():>8.0f} {pf:>6.2f}")

    # ── Year-by-year ────────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("逐年比較")
    print("=" * 85)

    for label, start in configs:
        stats = all_stats[start]
        trades = stats["_trades"].copy()
        if trades.empty:
            continue
        trades["year"] = pd.to_datetime(trades["EntryTime"]).dt.year
        print(f"\n  [{label}]")
        print(f"  {'Year':<6} {'Trades':>7} {'Win%':>6} {'Avg PnL':>8} {'Total':>8} {'PF':>6}")
        for yr, grp in trades.groupby("year"):
            pnl = grp["PnL"]
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            wr = len(wins) / len(pnl) * 100 if len(pnl) else 0
            pf = wins.sum() / abs(losses.sum()) if len(losses) else float("inf")
            print(f"  {yr:<6} {len(pnl):>7} {wr:>5.1f}% {pnl.mean():>8.1f} {pnl.sum():>8.0f} {pf:>6.2f}")

    print("\nDone.")


if __name__ == "__main__":
    main()

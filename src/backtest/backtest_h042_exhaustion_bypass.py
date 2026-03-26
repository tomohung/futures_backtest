#!/usr/bin/env python3
"""H042 Phase 2: Exhaustion Bypass MA Direction — full backtest comparison.

Compares standard Reversal vs Reversal with exhaustion bypass MA.
When the opposing side is exhausted, the MA direction check is bypassed
in both BB latch and setup conditions.

Usage:
    uv run python src/backtest/backtest_h042_exhaustion_bypass.py
"""
import sys
from collections import deque
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.estimate_hl_exit import EstimateHLExitMixin
from src.strategies.reversal import ReversalStrategy

_ENTRY_START = dtime(9, 10)
_ENTRY_END   = dtime(10, 5)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 40)


class ReversalExhaustionBypass(EstimateHLExitMixin, Strategy):
    """Reversal with exhaustion bypass MA direction.

    When opposing side is exhausted, BB latch and setup skip MA direction check.
    BC inside zone also opens the opposing direction when exhausted.
    All other logic identical to ReversalStrategy.
    """
    vol_ratio:        float = 1.2
    sl_ema_fraction:  float = 0.25
    exhaust_fraction: float = 0.5
    signal_skip:      int   = 0
    sat_pullback_fraction: float = 0.5

    def init(self):
        self._prev_date = None
        self._init_estimate_hl_exit()
        self._reset_daily()

    def _reset_daily(self):
        self._entered = False
        self._allow_long  = False
        self._allow_short = False
        self._open_price  = None
        self._bb_long_touched  = False
        self._bb_short_touched = False
        self._bb_long_count    = 0
        self._bb_short_count   = 0
        self._bull_exhausted   = False
        self._bear_exhausted   = False
        self._near_sat_latch   = False
        self._sat_extreme_high = None
        self._sat_extreme_low  = None
        self._trigger_count = 0
        self._day_high    = None
        self._day_low     = None
        self._sl_price    = None
        self._trail_stop  = None
        self._low_buf     = deque(maxlen=11)
        self._high_buf    = deque(maxlen=11)
        self._bc_inside   = False

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])

        # ── Day rollover ─────────────────────────────────────────────
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date  = cur_date
            self._open_price = float(self.data.Open[-1])
            self._day_low  = float(self.data.Low[-1])
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

        # ── Track daily extremes ─────────────────────────────────────
        if self._day_low is not None:
            self._day_low  = min(self._day_low,  float(self.data.Low[-1]))
            self._day_high = max(self._day_high, float(self.data.High[-1]))

        self._record_bar()

        # ── Exit logic (identical to standard) ───────────────────────
        if self.position:
            if cur_time >= _FORCE_EXIT:
                self.position.close(); return
            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close(); return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close(); return
            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close(); return
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close(); return
            if cur_time >= _TRAIL_START:
                if self.position.is_long:
                    self._low_buf.append(float(self.data.Low[-1]))
                    if len(self._low_buf) == 11:
                        lows = list(self._low_buf)
                        if lows[5] == min(lows):
                            if self._trail_stop is None or lows[5] > self._trail_stop:
                                self._trail_stop = lows[5]
                    if self._trail_stop is not None and close < self._trail_stop:
                        self.position.close(); return
                elif self.position.is_short:
                    self._high_buf.append(float(self.data.High[-1]))
                    if len(self._high_buf) == 11:
                        highs = list(self._high_buf)
                        if highs[5] == max(highs):
                            if self._trail_stop is None or highs[5] < self._trail_stop:
                                self._trail_stop = highs[5]
                    if self._trail_stop is not None and close > self._trail_stop:
                        self.position.close(); return
            return

        if self._entered or self._satzone_reached:
            return

        # ── Read indicators ──────────────────────────────────────────
        ema_hl     = float(self.data.EmaHL[-1])
        ma5m       = float(self.data.MA5m_120[-1])
        ma5m_prev  = float(self.data.MA5m_120_Prev[-1])
        bb_upper   = float(self.data.BB_Upper[-1])
        bb_lower   = float(self.data.BB_Lower[-1])
        vol        = float(self.data.Volume[-1])
        vol_ma     = float(self.data.VolMA20[-1])
        ccd        = float(self.data.CCD_5m[-1])
        ma5        = float(self.data.MA5_1m[-1])

        if any(np.isnan(v) for v in
               [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
            return

        sl = ema_hl * self.sl_ema_fraction
        vol_ok = vol > self.vol_ratio * vol_ma
        bullish = ma5m > ma5m_prev

        # ── Resolve BC inside zone ───────────────────────────────────
        # Standard: follow MA direction. But if exhausted, open opposing too.
        if self._bc_inside:
            self._bc_inside = False
            if bullish:
                self._allow_long = True
            else:
                self._allow_short = True

        if not (self._allow_long or self._allow_short):
            return

        # ── Exhaustion latch ─────────────────────────────────────────
        exhaust_frac = self.exhaust_fraction
        if not self._bull_exhausted and self._day_low is not None:
            if close >= self._day_low + ema_hl * exhaust_frac:
                self._bull_exhausted = True
        if not self._bear_exhausted and self._day_high is not None:
            if close <= self._day_high - ema_hl * exhaust_frac:
                self._bear_exhausted = True

        # ── H042: Exhaustion opens opposing direction for BC inside ──
        # If initially resolved to long-only but bull_exhausted → also allow short
        # If initially resolved to short-only but bear_exhausted → also allow long
        # For above/below BC zone, direction is fixed but exhaustion bypasses MA check
        if self._bull_exhausted and not self._allow_short:
            # Don't open short for above-BC (open > bc_hi → long only by structure)
            # Only open if we're in inside zone that was resolved to long
            pass  # handled in latch/setup below via exhaustion bypass
        if self._bear_exhausted and not self._allow_long:
            pass  # same

        # ── Step 1: BB latch + vol ───────────────────────────────────
        # H042 CHANGE: when exhausted, bypass MA direction check
        # Standard: allow_long AND bullish
        # Bypass:   allow_long AND (bullish OR bear_exhausted)
        long_ma_ok = bullish or self._bear_exhausted
        short_ma_ok = (not bullish) or self._bull_exhausted

        if self._allow_long and long_ma_ok and not self._bb_long_touched:
            if close <= bb_lower and vol_ok:
                self._bb_long_touched = True
                self._bb_long_count += 1

        if self._allow_short and short_ma_ok and not self._bb_short_touched:
            if close >= bb_upper and vol_ok:
                self._bb_short_touched = True
                self._bb_short_count += 1

        # ── Step 2: Trigger ──────────────────────────────────────────
        if _ENTRY_START <= cur_time <= _ENTRY_END:
            # H042 CHANGE: setup also uses exhaustion bypass
            long_setup = (self._allow_long and long_ma_ok and
                          self._bb_long_touched and
                          (ccd > 0 or self._bear_exhausted
                           or self._bb_long_count >= 2))
            short_setup = (self._allow_short and short_ma_ok and
                           self._bb_short_touched and
                           (ccd < 0 or self._bull_exhausted
                            or self._bb_short_count >= 2))

            # Near-SatZone gate (identical to standard)
            sat_upper = float(self.data.SatZoneUpper[-1])
            sat_lower = float(self.data.SatZoneLower[-1])
            margin = ema_hl / 8
            if not self._near_sat_latch:
                near_sat_up = (not np.isnan(sat_upper) and self._day_high is not None
                               and sat_upper - self._day_high <= margin)
                near_sat_dn = (not np.isnan(sat_lower) and self._day_low is not None
                               and self._day_low - sat_lower <= margin)
                if near_sat_up or near_sat_dn:
                    self._near_sat_latch = True
                    self._sat_extreme_high = self._day_high
                    self._sat_extreme_low = self._day_low

            if self._near_sat_latch and ema_hl > 0:
                pb = ema_hl * self.sat_pullback_fraction
                if (self._sat_extreme_high is not None
                        and self._sat_extreme_high - close >= pb):
                    self._near_sat_latch = False
                if (self._sat_extreme_low is not None
                        and close - self._sat_extreme_low >= pb):
                    self._near_sat_latch = False

            if long_setup and close > ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.buy(size=1)
                    self._sl_price = close - sl
                    self._entered = True

            elif short_setup and close < ma5 and not self._near_sat_latch:
                self._trigger_count += 1
                if self._trigger_count > self.signal_skip:
                    self.sell(size=1)
                    self._sl_price = close + sl
                    self._entered = True

        # ── Reset BB latch on MA5 cross ──────────────────────────────
        if close > ma5:
            self._bb_long_touched = False
        if close < ma5:
            self._bb_short_touched = False


# ── Formatting ──────────────────────────────────────────────────────────────

def fv(v, width=8, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(width)
    return f"{v:.{dec}f}".rjust(width)


def compute_stats(trades: pd.DataFrame, label: str) -> dict:
    pnl = trades["PnL"]
    n = len(pnl)
    if n == 0:
        return {"label": label, "n": 0}
    winners = pnl[pnl > 0]
    losers = pnl[pnl < 0]
    wr = len(winners) / n * 100
    pf = winners.sum() / abs(losers.sum()) if len(losers) > 0 else float("inf")
    avg = pnl.mean()
    total = pnl.sum()

    # PnL% for Sharpe
    entry_prices = trades["EntryPrice"]
    pnl_pct = pnl / entry_prices * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * (252 ** 0.5) if pnl_pct.std() > 0 else 0

    return {
        "label": label, "n": n, "wr": wr, "pf": pf,
        "avg": avg, "total": total, "sharpe": sharpe,
        "max_dd_pts": pnl.cumsum().min() if pnl.cumsum().min() < 0 else 0,
    }


def print_stats_row(s: dict):
    if s["n"] == 0:
        print(f"  {s['label']:<25}  {'0':>5}")
        return
    print(f"  {s['label']:<25}  {s['n']:>5}  {s['wr']:>5.1f}%  {s['pf']:>5.2f}  "
          f"{fv(s['avg']):>8}  {fv(s['total'], dec=0):>8}  {fv(s['sharpe']):>7}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 78)
    print("H042 Phase 2: Exhaustion Bypass MA — Full Backtest Comparison")
    print("=" * 78)

    # Load full data
    print("\nLoading data...", flush=True)
    df_full = load_data_for_reversal(start="2021-01-01")

    YEARS = [
        ("IS 2021",     "2021-01-01", "2021-12-31"),
        ("IS 2022",     "2022-01-01", "2022-12-31"),
        ("IS 2023",     "2023-01-01", "2023-12-31"),
        ("IS 2024",     "2024-01-01", "2024-12-31"),
        ("OOS 2025",    "2025-01-01", "2025-12-31"),
        ("OOS 2026",    "2026-01-01", None),
        ("IS Total",    "2021-01-01", "2024-12-31"),
        ("OOS Total",   "2025-01-01", None),
        ("ALL",         "2021-01-01", None),
    ]

    header = f"  {'Period':<25}  {'N':>5}  {'WR':>6}  {'PF':>5}  {'Avg PnL':>8}  {'Total':>8}  {'Sharpe':>7}"
    sep    = f"  {'-'*25}  {'-'*5}  {'-'*6}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*7}"

    for strat_cls, strat_name in [(ReversalStrategy, "Standard Reversal"),
                                   (ReversalExhaustionBypass, "Exhaustion Bypass")]:
        print(f"\n{'=' * 78}")
        print(f"  {strat_name}")
        print(f"{'=' * 78}")
        print(header)
        print(sep)

        for label, start, end in YEARS:
            df_slice = df_full[df_full.index >= start]
            if end:
                df_slice = df_slice[df_slice.index <= end]

            if len(df_slice) < 100:
                continue

            bt = Backtest(df_slice, strat_cls, cash=200_000,
                          commission=0.0, trade_on_close=True)
            stats = bt.run()
            trades = stats["_trades"]
            s = compute_stats(trades, label)
            print_stats_row(s)

            if label == "IS Total":
                print(sep)
            if label == "OOS Total":
                print(sep)

    # ── Delta analysis: find the extra trades from bypass ───────────────
    print(f"\n{'=' * 78}")
    print("  Delta Analysis: Extra Trades from Exhaustion Bypass")
    print(f"{'=' * 78}")

    bt_std = Backtest(df_full, ReversalStrategy, cash=200_000,
                      commission=0.0, trade_on_close=True)
    stats_std = bt_std.run()
    trades_std = stats_std["_trades"].copy()
    trades_std["entry_date"] = pd.to_datetime(trades_std["EntryTime"]).dt.date

    bt_byp = Backtest(df_full, ReversalExhaustionBypass, cash=200_000,
                      commission=0.0, trade_on_close=True)
    stats_byp = bt_byp.run()
    trades_byp = stats_byp["_trades"].copy()
    trades_byp["entry_date"] = pd.to_datetime(trades_byp["EntryTime"]).dt.date

    # Find dates that appear in bypass but not in standard
    std_dates = set(trades_std["entry_date"])
    byp_dates = set(trades_byp["entry_date"])

    # Dates with different trades (bypass took a different entry)
    new_dates = byp_dates - std_dates
    common_dates = byp_dates & std_dates

    # For common dates, check if the trade is different
    changed = []
    for d in common_dates:
        t_std = trades_std[trades_std["entry_date"] == d].iloc[0]
        t_byp = trades_byp[trades_byp["entry_date"] == d].iloc[0]
        if abs(t_std["EntryPrice"] - t_byp["EntryPrice"]) > 1:
            changed.append(d)

    extra_trades = trades_byp[trades_byp["entry_date"].isin(new_dates)]
    changed_trades = trades_byp[trades_byp["entry_date"].isin(changed)]

    print(f"\n  Standard trades: {len(trades_std)}")
    print(f"  Bypass trades:   {len(trades_byp)}")
    print(f"  New dates (bypass only):  {len(new_dates)}")
    print(f"  Changed trades (same date, different entry): {len(changed)}")

    if len(extra_trades) > 0:
        print(f"\n  Extra trades (bypass only):")
        print(f"  {'Date':<12} {'Dir':<6} {'Entry':>7} {'PnL':>7} {'Time':<6}")
        print(f"  {'-'*12} {'-'*6} {'-'*7} {'-'*7} {'-'*6}")
        for _, t in extra_trades.sort_values("entry_date").iterrows():
            d = "long" if t["Size"] > 0 else "short"
            tm = pd.to_datetime(t["EntryTime"]).strftime("%H:%M")
            print(f"  {t['entry_date']}  {d:<6} {t['EntryPrice']:>7.0f} {t['PnL']:>7.0f} {tm}")

        pnl = extra_trades["PnL"]
        n = len(pnl)
        wr = (pnl > 0).sum() / n * 100
        print(f"\n  Extra trades summary: N={n}  WR={wr:.1f}%  "
              f"Avg={pnl.mean():.1f}  Total={pnl.sum():.0f}")

    if len(changed_trades) > 0:
        print(f"\n  Changed trades (different entry on same date):")
        print(f"  {'Date':<12} {'Std PnL':>8} {'Byp PnL':>8} {'Delta':>7}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*7}")
        total_delta = 0
        for d in sorted(changed):
            t_s = trades_std[trades_std["entry_date"] == d].iloc[0]
            t_b = trades_byp[trades_byp["entry_date"] == d].iloc[0]
            delta = t_b["PnL"] - t_s["PnL"]
            total_delta += delta
            print(f"  {d}  {t_s['PnL']:>8.0f} {t_b['PnL']:>8.0f} {delta:>7.0f}")
        print(f"  {'':>12}  {'':>8} {'':>8} {total_delta:>7.0f} total delta")

    print(f"\n{'=' * 78}")
    print("Done.")


if __name__ == "__main__":
    main()

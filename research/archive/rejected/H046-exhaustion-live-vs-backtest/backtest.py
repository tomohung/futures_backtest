#!/usr/bin/env python3
"""H046 Phase 2: S003 Exhaustion 策略重新評估 + 變體測試。

測試項目：
  1. Baseline: 現行 S003 參數（close 進場）
  2. 放寬 BB%B 門檻（> 0.85/<0.15, > 0.75/<0.25, > 0.5/<0.5）
  3. 移除夜盤新極值條件
  4. 移除週三四濾網
  5. 組合測試

Usage:
    uv run python research/active/H046-exhaustion-live-vs-backtest/backtest.py
"""

import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_exhaustion, print_summary
from src.strategies.exhaustion import ExhaustionStrategy

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("IS",   "2021-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
    ("OOS",  "2025-01-01", None),
]

# ── Variant: configurable BB%B threshold ─────────────────────────────────

class ExhaustionVariantStrategy(ExhaustionStrategy):
    """Exhaustion with configurable BB%B threshold and night filter toggle."""

    bb_threshold:    float = 1.0   # BB%B > threshold (short) or < 1-threshold (long)
    require_night:   bool  = True  # require night session new high/low

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])
        high     = float(self.data.High[-1])
        low      = float(self.data.Low[-1])
        from datetime import time as dtime

        # ── Day rollover
        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date
            self._day_open  = float(self.data.Open[-1])

        # ── Build Opening Range (08:45–08:57)
        if dtime(8, 45) <= cur_time <= dtime(8, 57):
            if self._or_high is None:
                self._or_high = high
                self._or_low  = low
            else:
                self._or_high = max(self._or_high, high)
                self._or_low  = min(self._or_low, low)
        elif cur_time > dtime(8, 57) and not self._or_done:
            self._or_done = True

        # ── SatZone exit mixin
        self._record_bar()

        # ── Exit logic
        if self.position:
            if cur_time >= dtime(13, 30):
                self.position.close()
                return
            if self._sl_price is not None:
                if self.position.is_long and close <= self._sl_price:
                    self.position.close()
                    return
                if self.position.is_short and close >= self._sl_price:
                    self.position.close()
                    return
            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close()
                    return
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close()
                    return
            if cur_time >= dtime(9, 45):
                if self.position.is_long:
                    self._low_buf.append(float(self.data.Low[-1]))
                    if len(self._low_buf) == 11:
                        lows = list(self._low_buf)
                        if lows[5] == min(lows):
                            if self._trail_stop is None or lows[5] > self._trail_stop:
                                self._trail_stop = lows[5]
                    if self._trail_stop is not None and close < self._trail_stop:
                        self.position.close()
                        return
                elif self.position.is_short:
                    self._high_buf.append(float(self.data.High[-1]))
                    if len(self._high_buf) == 11:
                        highs = list(self._high_buf)
                        if highs[5] == max(highs):
                            if self._trail_stop is None or highs[5] < self._trail_stop:
                                self._trail_stop = highs[5]
                    if self._trail_stop is not None and close > self._trail_stop:
                        self.position.close()
                        return
            return

        if self._entered or self._satzone_reached:
            return
        if not self._or_done or not (dtime(9, 0) <= cur_time <= dtime(10, 30)):
            return

        ema_hl = float(self.data.EmaHL[-1])
        if np.isnan(ema_hl):
            return

        weekday = cur_date.weekday()
        if self.skip_wed and weekday == 2:
            return
        if self.skip_thu and weekday == 3:
            return

        if self._or_high is None or self._or_low is None or self._day_open is None:
            return
        or_width = self._or_high - self._or_low
        if self._day_open <= 0:
            return
        orb_pct = or_width / self._day_open * 100
        if orb_pct < self.min_orb_pct:
            return

        ma30      = float(self.data.MA30_20[-1])
        ma30_prev = float(self.data.MA30_20_Prev[-1])
        if np.isnan(ma30) or np.isnan(ma30_prev):
            return
        ma_up   = ma30 > ma30_prev
        ma_down = ma30 < ma30_prev

        # ── Configurable BB%B threshold ──
        # Read raw BB%B value from data (need to add BB30_PctB column)
        bb_pctb = float(self.data.BB30_PctB[-1])
        if np.isnan(bb_pctb):
            return
        bb_above = bb_pctb > self.bb_threshold
        bb_below = bb_pctb < (1.0 - self.bb_threshold)

        night_new_high = bool(self.data.NightNewHigh[-1])
        night_new_low  = bool(self.data.NightNewLow[-1])

        # Night filter toggle
        if self.require_night:
            night_ok_short = night_new_high
            night_ok_long  = night_new_low
        else:
            night_ok_short = True
            night_ok_long  = True

        sl = ema_hl * self.sl_fraction

        # Bull exhaustion → short
        if ma_up and bb_above and night_ok_short:
            if close < self._or_low:
                self.sell(size=1)
                self._sl_price = close + sl
                self._entered  = True
                return

        # Bear exhaustion → long
        if ma_down and bb_below and night_ok_long:
            if close > self._or_high:
                self.buy(size=1)
                self._sl_price = close - sl
                self._entered  = True
                return


# ── Helpers ──────────────────────────────────────────────────────────────

def year_sweep(df_all, strategy_cls, params):
    rows = []
    for yr, start, end in YEARS:
        sub = df_all[df_all.index >= start]
        if end:
            sub = sub[sub.index <= end]
        if len(sub) < 100:
            rows.append({"year": yr, "n": 0, "wr": None, "pf": None, "ev": None, "total": 0})
            continue
        bt = Backtest(sub, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(**params)
        trades = stats["_trades"]
        n = len(trades)
        if n == 0:
            rows.append({"year": yr, "n": 0, "wr": None, "pf": None, "ev": None, "total": 0})
            continue
        pnl = trades["PnL"]
        wins = pnl[pnl > 0].sum()
        losses = abs(pnl[pnl < 0].sum())
        rows.append({
            "year": yr,
            "n": n,
            "wr": round(len(pnl[pnl > 0]) / n * 100, 1),
            "pf": round(wins / losses, 2) if losses > 0 else float("inf"),
            "ev": round(pnl.mean(), 1),
            "total": round(pnl.sum(), 0),
        })
    return pd.DataFrame(rows)


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float) and v == float("inf"):
        return "∞".rjust(w)
    return f"{v:.{dec}f}".rjust(w)


def print_sweep(label, df_sw):
    print(f"\n  {label}")
    print(f"  {'Year':<6} {'N':>4} {'WR%':>6} {'PF':>6} {'EV':>8} {'Total':>8}")
    print(f"  {'-'*6} {'-'*4} {'-'*6} {'-'*6} {'-'*8} {'-'*8}")
    for _, r in df_sw.iterrows():
        print(f"  {r['year']:<6} {fv(r['n'],4,0):>4} {fv(r['wr'],6):>6} "
              f"{fv(r['pf'],6,2):>6} {fv(r['ev'],8):>8} {fv(r['total'],8,0):>8}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("H046 Phase 2: S003 Exhaustion 策略重新評估")
    print("=" * 72)

    print("\nLoading data...", flush=True)
    df = load_data_for_exhaustion()
    print(f"  {len(df):,} bars  {df.index[0].date()} ~ {df.index[-1].date()}")

    # Need BB30_PctB column for variant strategy
    # Add raw BB%B value to df
    s30_open = df["Open"].resample("30min", offset="15min").first().dropna()
    bb_ma  = s30_open.rolling(20, min_periods=20).mean().shift(1)
    bb_std = s30_open.rolling(20, min_periods=20).std(ddof=1).shift(1)
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    bb_pctb  = (s30_open - bb_lower) / (bb_upper - bb_lower)
    bb_pctb_df = bb_pctb.to_frame("bbpct")
    bb_pctb_df["date"] = bb_pctb_df.index.normalize()
    first_bb = bb_pctb_df.groupby("date")["bbpct"].first()
    import pandas as _pd
    day_dates = _pd.DatetimeIndex(df.index).normalize()
    df["BB30_PctB"] = first_bb.reindex(day_dates).values

    # ── 1. Baseline: S003 current params ─────────────────────────────
    print("\n" + "=" * 72)
    print("[1/5] Baseline: S003 現行參數")
    print("=" * 72)

    baseline_params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                           skip_wed=True, skip_thu=True,
                           bb_threshold=1.0, require_night=True)
    df_base = year_sweep(df, ExhaustionVariantStrategy, baseline_params)
    print_sweep("S003 Baseline (BB>1/<0, 夜盤新極值, 跳週三四)", df_base)

    # ── 2. BB%B threshold variants ───────────────────────────────────
    print("\n" + "=" * 72)
    print("[2/5] BB%B 門檻測試")
    print("=" * 72)

    bb_thresholds = [1.0, 0.85, 0.75, 0.5]
    for bb in bb_thresholds:
        params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                      skip_wed=True, skip_thu=True,
                      bb_threshold=bb, require_night=True)
        df_sw = year_sweep(df, ExhaustionVariantStrategy, params)
        lower = 1.0 - bb
        print_sweep(f"BB > {bb:.2f} / < {lower:.2f}", df_sw)

    # ── 3. Night filter toggle ───────────────────────────────────────
    print("\n" + "=" * 72)
    print("[3/5] 夜盤新極值條件測試")
    print("=" * 72)

    for night in [True, False]:
        params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                      skip_wed=True, skip_thu=True,
                      bb_threshold=1.0, require_night=night)
        df_sw = year_sweep(df, ExhaustionVariantStrategy, params)
        label = "夜盤必要" if night else "不要求夜盤"
        print_sweep(f"BB > 1.0 / < 0.0, {label}", df_sw)

    # ── 4. Weekday filter toggle ─────────────────────────────────────
    print("\n" + "=" * 72)
    print("[4/5] 週三四濾網測試")
    print("=" * 72)

    for skip in [True, False]:
        params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                      skip_wed=skip, skip_thu=skip,
                      bb_threshold=1.0, require_night=True)
        df_sw = year_sweep(df, ExhaustionVariantStrategy, params)
        label = "跳週三四" if skip else "不跳週三四"
        print_sweep(f"BB > 1.0 / < 0.0, {label}", df_sw)

    # ── 5. Best combo search ─────────────────────────────────────────
    print("\n" + "=" * 72)
    print("[5/5] 組合搜尋")
    print("=" * 72)

    combos = []
    for bb, night, skip_wd in product(
        [1.0, 0.85, 0.75],
        [True, False],
        [True, False],
    ):
        params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                      skip_wed=skip_wd, skip_thu=skip_wd,
                      bb_threshold=bb, require_night=night)
        df_sw = year_sweep(df, ExhaustionVariantStrategy, params)
        is_row = df_sw[df_sw["year"] == "IS"].iloc[0]
        oos_row = df_sw[df_sw["year"] == "OOS"].iloc[0]
        lower = 1.0 - bb
        combos.append({
            "bb": f">{bb:.2f}/<{lower:.2f}",
            "night": "Y" if night else "N",
            "skip_wd": "Y" if skip_wd else "N",
            "is_n": is_row["n"], "is_pf": is_row["pf"], "is_total": is_row["total"],
            "oos_n": oos_row["n"], "oos_pf": oos_row["pf"], "oos_total": oos_row["total"],
        })

    df_combos = pd.DataFrame(combos)
    df_combos = df_combos.sort_values("oos_total", ascending=False)

    print(f"\n  {'BB':>12} {'Night':>6} {'Skip':>5} | {'IS_N':>5} {'IS_PF':>6} {'IS_Tot':>7} | "
          f"{'OOS_N':>5} {'OOS_PF':>7} {'OOS_Tot':>8}")
    print(f"  {'-'*12} {'-'*6} {'-'*5} | {'-'*5} {'-'*6} {'-'*7} | {'-'*5} {'-'*7} {'-'*8}")
    for _, r in df_combos.iterrows():
        print(f"  {r['bb']:>12} {r['night']:>6} {r['skip_wd']:>5} | "
              f"{fv(r['is_n'],5,0):>5} {fv(r['is_pf'],6,2):>6} {fv(r['is_total'],7,0):>7} | "
              f"{fv(r['oos_n'],5,0):>5} {fv(r['oos_pf'],7,2):>7} {fv(r['oos_total'],8,0):>8}")

    # Show best combo details
    best = df_combos.iloc[0]
    print(f"\n  Best OOS: BB {best['bb']}, night={best['night']}, skip_wd={best['skip_wd']}")
    print(f"  IS: N={best['is_n']:.0f} PF={best['is_pf']:.2f} Total={best['is_total']:+.0f}")
    print(f"  OOS: N={best['oos_n']:.0f} PF={best['oos_pf']:.2f} Total={best['oos_total']:+.0f}")

    # Print year-by-year for best combo
    bb_val = float(best["bb"].split("/")[0].replace(">", ""))
    best_params = dict(sl_fraction=0.25, min_orb_pct=0.25,
                       skip_wed=best["skip_wd"] == "Y",
                       skip_thu=best["skip_wd"] == "Y",
                       bb_threshold=bb_val,
                       require_night=best["night"] == "Y")
    df_best = year_sweep(df, ExhaustionVariantStrategy, best_params)
    print_sweep("Best combo year-by-year", df_best)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

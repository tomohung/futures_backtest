#!/usr/bin/env python3
"""Explore H042: BB Extreme Bypass MA Direction.

When 30-min BB(20, open) %B > 1 or < 0, the Reversal strategy's MA direction
filter may block valid reversal setups.  This script measures:

  1. 30-min BB%B distribution and extreme frequency
  2. Reversal setups blocked by MA direction during BB%B extreme bars
  3. MFE / MAE of those blocked trades (hypothetical performance)
  4. Comparison: BB%B extreme vs normal Reversal performance

Usage:
    uv run python src/backtest/explore_h042_bb_extreme.py
    uv run python src/backtest/explore_h042_bb_extreme.py --start 2021-01-01
"""
import argparse
import sys
from collections import defaultdict
from datetime import date, time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_reversal

DB_PATH = "data/futures.duckdb"

# Reversal strategy constants (from reversal.py)
_ENTRY_START = dtime(9, 10)
_ENTRY_END   = dtime(10, 5)
VOL_RATIO    = 1.2
EXHAUST_FRAC = 0.5
SAT_PULLBACK = 0.5

# MFE/MAE measurement window (minutes after hypothetical entry)
MFE_MAE_WINDOW = 60  # look 60 bars (minutes) ahead


# ── 30-min BB%B computation ─────────────────────────────────────────────────

def compute_30m_bb_pctb(period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Compute 30-min BB(period, open) %B from day-session only data.

    BB bands and %B both use open prices.  Since open is known at bar start,
    no shift is needed (no lookahead).

    Returns DataFrame with columns: open30, bb_upper, bb_lower, bb_pctb
    indexed by 30-min timestamps.
    """
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_day = conn.execute("""
            SELECT timestamp, open FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df().set_index("timestamp")

    # Resample to 30-min: use open (first) as source for BB and %B
    s30_open = df_day["open"].resample("30min").first().dropna()

    # BB on open prices
    roll = s30_open.rolling(period, min_periods=period)
    bb_mid = roll.mean()
    bb_std = roll.std(ddof=0)
    bb_upper = bb_mid + num_std * bb_std
    bb_lower = bb_mid - num_std * bb_std

    # %B = (open - lower) / (upper - lower)
    bb_width = bb_upper - bb_lower
    bb_pctb = (s30_open - bb_lower) / bb_width.replace(0, np.nan)

    result = pd.DataFrame({
        "open30": s30_open,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_pctb": bb_pctb,
    })

    return result


# ── Reversal entry simulation ───────────────────────────────────────────────

def simulate_reversal_entries(df: pd.DataFrame, bb30: pd.DataFrame) -> pd.DataFrame:
    """Simulate Reversal entry logic day-by-day, tracking MA-blocked setups.

    Returns a DataFrame of all entry events (both taken and blocked),
    with columns: date, direction, entry_price, entry_time, blocked_by_ma,
    bb_pctb_at_entry, mfe, mae, exit_pnl_60m.
    """
    # Map 30-min BB%B to 1-min bars via ffill
    df["bb30_pctb"] = bb30["bb_pctb"].reindex(df.index, method="ffill")

    records = []
    dates = sorted(set(df.index.date))

    for d in dates:
        day = df[df.index.date == d]
        if len(day) < 30:
            continue

        # ── Day-level setup (mirrors reversal.py) ──
        first_bar = day.iloc[0]
        open_price = float(first_bar["Open"])
        bc1 = float(first_bar["VWAP1"])
        bc2 = float(first_bar["VWAP2"])

        if np.isnan(bc1) or np.isnan(bc2):
            continue

        bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
        allow_long = False
        allow_short = False
        bc_inside = False

        if open_price > bc_hi:
            allow_long = True
        elif open_price < bc_lo:
            allow_short = True
        else:
            bc_inside = True

        # Track state
        bb_long_touched = False
        bb_short_touched = False
        bb_long_count = 0
        bb_short_count = 0
        bull_exhausted = False
        bear_exhausted = False
        near_sat_latch = False
        sat_extreme_high = None
        sat_extreme_low = None
        entered = False
        day_high = float(first_bar["High"])
        day_low = float(first_bar["Low"])
        bc_inside_resolved = False
        satzone_reached = False
        bypass_long_latch = False   # persistent: BB touch with MA opposing
        bypass_short_latch = False
        bypass_long_count = 0
        bypass_short_count = 0

        for i in range(len(day)):
            row = day.iloc[i]
            ts = day.index[i]
            cur_time = ts.time()
            close = float(row["Close"])
            high = float(row["High"])
            low = float(row["Low"])

            day_high = max(day_high, high)
            day_low = min(day_low, low)

            # SatZone reached check
            sat_upper = float(row["SatZoneUpper"]) if not np.isnan(row["SatZoneUpper"]) else None
            sat_lower = float(row["SatZoneLower"]) if not np.isnan(row["SatZoneLower"]) else None
            if sat_upper and high >= sat_upper:
                satzone_reached = True
            if sat_lower and low <= sat_lower:
                satzone_reached = True

            if entered or satzone_reached:
                continue

            ema_hl = float(row["EmaHL"])
            ma5m = float(row["MA5m_120"])
            ma5m_prev = float(row["MA5m_120_Prev"])
            bb_upper = float(row["BB_Upper"])
            bb_lower = float(row["BB_Lower"])
            vol = float(row["Volume"])
            vol_ma = float(row["VolMA20"])
            ccd = float(row["CCD_5m"])
            ma5 = float(row["MA5_1m"])
            bb30_pctb = float(row["bb30_pctb"]) if not np.isnan(row.get("bb30_pctb", np.nan)) else np.nan

            if any(np.isnan(v) for v in [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
                continue

            vol_ok = vol > VOL_RATIO * vol_ma
            bullish = ma5m > ma5m_prev

            # Resolve BC inside
            if bc_inside and not bc_inside_resolved:
                bc_inside_resolved = True
                if bullish:
                    allow_long = True
                else:
                    allow_short = True

            if not (allow_long or allow_short):
                continue

            # Exhaustion latch
            if not bull_exhausted:
                if close >= day_low + ema_hl * EXHAUST_FRAC:
                    bull_exhausted = True
            if not bear_exhausted:
                if close <= day_high - ema_hl * EXHAUST_FRAC:
                    bear_exhausted = True

            # ── Step 1: BB latch (with MA direction check = standard behavior) ──
            # Standard: requires `bullish` for long, `not bullish` for short
            # We also track "would have latched" if MA was bypassed

            # Standard latch
            if allow_long and bullish and not bb_long_touched:
                if close <= bb_lower and vol_ok:
                    bb_long_touched = True
                    bb_long_count += 1

            if allow_short and not bullish and not bb_short_touched:
                if close >= bb_upper and vol_ok:
                    bb_short_touched = True
                    bb_short_count += 1

            # Bypass latch (ignoring MA direction check)
            # For long: allow_long but NOT bullish (MA would block it)
            if allow_long and not bullish and not bypass_long_latch:
                if close <= bb_lower and vol_ok:
                    bypass_long_latch = True
                    bypass_long_count += 1

            if allow_short and bullish and not bypass_short_latch:
                if close >= bb_upper and vol_ok:
                    bypass_short_latch = True
                    bypass_short_count += 1

            # ── Step 2: Trigger check ──
            if _ENTRY_START <= cur_time <= _ENTRY_END:
                # Near-SatZone gate
                margin = ema_hl / 8
                if not near_sat_latch:
                    near_up = (sat_upper is not None and sat_upper - day_high <= margin)
                    near_dn = (sat_lower is not None and day_low - sat_lower <= margin)
                    if near_up or near_dn:
                        near_sat_latch = True
                        sat_extreme_high = day_high
                        sat_extreme_low = day_low

                if near_sat_latch and ema_hl > 0:
                    pb = ema_hl * SAT_PULLBACK
                    if sat_extreme_high is not None and sat_extreme_high - close >= pb:
                        near_sat_latch = False
                    if sat_extreme_low is not None and close - sat_extreme_low >= pb:
                        near_sat_latch = False

                if near_sat_latch:
                    continue

                # Standard entry check
                long_setup = (allow_long and bullish and bb_long_touched and
                              (ccd > 0 or bear_exhausted or bb_long_count >= 2))
                short_setup = (allow_short and not bullish and bb_short_touched and
                               (ccd < 0 or bull_exhausted or bb_short_count >= 2))

                if long_setup and close > ma5:
                    # Standard entry taken
                    mfe, mae, pnl_60 = _compute_mfe_mae(day, i, "long")
                    records.append({
                        "date": d, "direction": "long", "entry_price": close,
                        "entry_time": ts, "blocked_by_ma": False,
                        "bb30_pctb": bb30_pctb, "mfe": mfe, "mae": mae,
                        "pnl_60m": pnl_60, "ema_hl": ema_hl,
                    })
                    entered = True
                    continue

                if short_setup and close < ma5:
                    mfe, mae, pnl_60 = _compute_mfe_mae(day, i, "short")
                    records.append({
                        "date": d, "direction": "short", "entry_price": close,
                        "entry_time": ts, "blocked_by_ma": False,
                        "bb30_pctb": bb30_pctb, "mfe": mfe, "mae": mae,
                        "pnl_60m": pnl_60, "ema_hl": ema_hl,
                    })
                    entered = True
                    continue

                # ── Check: would a bypass entry trigger here? ──
                # Only check bypass if standard didn't fire AND MA is opposing
                bypass_long_setup = (allow_long and not bullish and
                                     bypass_long_latch and
                                     (ccd > 0 or bear_exhausted
                                      or bypass_long_count >= 2))
                if bypass_long_setup and close > ma5:
                    mfe, mae, pnl_60 = _compute_mfe_mae(day, i, "long")
                    records.append({
                        "date": d, "direction": "long", "entry_price": close,
                        "entry_time": ts, "blocked_by_ma": True,
                        "bb30_pctb": bb30_pctb, "mfe": mfe, "mae": mae,
                        "pnl_60m": pnl_60, "ema_hl": ema_hl,
                    })
                    entered = True
                    continue

                bypass_short_setup = (allow_short and bullish and
                                      bypass_short_latch and
                                      (ccd < 0 or bull_exhausted
                                       or bypass_short_count >= 2))
                if bypass_short_setup and close < ma5:
                        mfe, mae, pnl_60 = _compute_mfe_mae(day, i, "short")
                        records.append({
                            "date": d, "direction": "short", "entry_price": close,
                            "entry_time": ts, "blocked_by_ma": True,
                            "bb30_pctb": bb30_pctb, "mfe": mfe, "mae": mae,
                            "pnl_60m": pnl_60, "ema_hl": ema_hl,
                        })
                        entered = True
                        continue

            # Reset BB latch on MA5 cross (opportunity passed)
            if close > ma5:
                bb_long_touched = False
                bypass_long_latch = False
            if close < ma5:
                bb_short_touched = False
                bypass_short_latch = False

    return pd.DataFrame(records) if records else pd.DataFrame()


def _compute_mfe_mae(day: pd.DataFrame, entry_idx: int,
                     direction: str) -> tuple[float, float, float]:
    """Compute MFE, MAE, and P&L at 60 minutes after entry."""
    entry_price = float(day.iloc[entry_idx]["Close"])
    remaining = day.iloc[entry_idx + 1: entry_idx + 1 + MFE_MAE_WINDOW]

    if len(remaining) == 0:
        return 0.0, 0.0, 0.0

    if direction == "long":
        mfe = float(remaining["High"].max()) - entry_price
        mae = entry_price - float(remaining["Low"].min())
        pnl = float(remaining.iloc[-1]["Close"]) - entry_price
    else:
        mfe = entry_price - float(remaining["Low"].min())
        mae = float(remaining["High"].max()) - entry_price
        pnl = entry_price - float(remaining.iloc[-1]["Close"])

    return mfe, mae, pnl


# ── Formatting helpers ──────────────────────────────────────────────────────

def fv(v, width=8, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(width)
    return f"{v:.{dec}f}".rjust(width)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="H042: BB Extreme Bypass MA Direction")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    print("=" * 72)
    print("H042: BB Extreme Bypass MA Direction — Phase 1 Distribution Research")
    print("=" * 72)

    # ── Section 1: 30-min BB%B distribution ─────────────────────────────────
    print("\n[1/4] Computing 30-min BB(20, open) %B ...", flush=True)
    bb30 = compute_30m_bb_pctb()
    bb30_valid = bb30["bb_pctb"].dropna()

    # Filter to analysis period
    if args.start:
        bb30_valid = bb30_valid[bb30_valid.index >= args.start]
    if args.end:
        bb30_valid = bb30_valid[bb30_valid.index <= args.end]

    # Day-session only for statistics (08:45~13:45)
    bb30_day = bb30_valid[(bb30_valid.index.time >= dtime(8, 45)) &
                          (bb30_valid.index.time <= dtime(13, 45))]

    total_bars = len(bb30_day)
    extreme_high = (bb30_day > 1).sum()
    extreme_low = (bb30_day < 0).sum()
    extreme_total = extreme_high + extreme_low

    print(f"\n  Total 30-min bars (day session): {total_bars:,}")
    print(f"  BB%B > 1 (overbought extreme) : {extreme_high:,} ({extreme_high/total_bars*100:.1f}%)")
    print(f"  BB%B < 0 (oversold extreme)   : {extreme_low:,} ({extreme_low/total_bars*100:.1f}%)")
    print(f"  Total extreme bars            : {extreme_total:,} ({extreme_total/total_bars*100:.1f}%)")

    # Per-day: how many days have at least one extreme bar
    bb30_day_dates = bb30_day.groupby(bb30_day.index.date)
    days_with_extreme = 0
    days_with_extreme_high = 0
    days_with_extreme_low = 0
    total_days = len(bb30_day_dates)

    for d, grp in bb30_day_dates:
        has_high = (grp > 1).any()
        has_low = (grp < 0).any()
        if has_high or has_low:
            days_with_extreme += 1
        if has_high:
            days_with_extreme_high += 1
        if has_low:
            days_with_extreme_low += 1

    print(f"\n  Total trading days: {total_days}")
    print(f"  Days with any extreme BB%B : {days_with_extreme} ({days_with_extreme/total_days*100:.1f}%)")
    print(f"    - BB%B > 1 days          : {days_with_extreme_high}")
    print(f"    - BB%B < 0 days          : {days_with_extreme_low}")

    # Percentile distribution
    print(f"\n  BB%B percentiles:")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = bb30_day.quantile(pct / 100)
        marker = " ← EXTREME" if val > 1 or val < 0 else ""
        print(f"    P{pct:>2}: {val:>7.3f}{marker}")

    # ── Section 2: Simulate Reversal entries ────────────────────────────────
    print("\n[2/4] Loading Reversal data and simulating entries ...", flush=True)
    df = load_data_for_reversal(start=args.start, end=args.end)
    entries = simulate_reversal_entries(df, bb30)

    if entries.empty:
        print("  No entries found. Aborting.")
        return

    standard = entries[~entries["blocked_by_ma"]]
    blocked = entries[entries["blocked_by_ma"]]

    print(f"\n  Standard Reversal entries (MA-allowed): {len(standard)}")
    print(f"  MA-blocked entries (would bypass)     : {len(blocked)}")

    # ── Section 3: Blocked entries analysis ─────────────────────────────────
    print("\n" + "=" * 72)
    print("[3/4] MA-Blocked Entries — MFE / MAE / Performance")
    print("=" * 72)

    if len(blocked) > 0:
        # BB%B at entry for blocked trades
        bb_extreme_blocked = blocked[
            (blocked["bb30_pctb"] > 1) | (blocked["bb30_pctb"] < 0)
        ]
        bb_normal_blocked = blocked[
            (blocked["bb30_pctb"] >= 0) & (blocked["bb30_pctb"] <= 1)
        ]
        bb_nan_blocked = blocked[blocked["bb30_pctb"].isna()]

        print(f"\n  Blocked entries during BB%B extreme: {len(bb_extreme_blocked)}")
        print(f"  Blocked entries during BB%B normal : {len(bb_normal_blocked)}")
        print(f"  Blocked entries with BB%B NaN      : {len(bb_nan_blocked)}")

        # Detailed stats for all blocked entries
        print(f"\n  {'Category':<25}  {'N':>5}  {'Win%':>6}  {'Avg MFE':>8}  {'Avg MAE':>8}  {'MFE/MAE':>8}  {'Avg PnL':>8}  {'Total':>8}")
        print(f"  {'-'*25}  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

        for label, grp in [("All blocked", blocked),
                           ("BB%B extreme", bb_extreme_blocked),
                           ("BB%B normal", bb_normal_blocked)]:
            if len(grp) == 0:
                print(f"  {label:<25}  {'0':>5}")
                continue
            n = len(grp)
            win = (grp["pnl_60m"] > 0).sum() / n * 100
            avg_mfe = grp["mfe"].mean()
            avg_mae = grp["mae"].mean()
            ratio = avg_mfe / avg_mae if avg_mae > 0 else float("inf")
            avg_pnl = grp["pnl_60m"].mean()
            total = grp["pnl_60m"].sum()
            print(f"  {label:<25}  {n:>5}  {win:>5.1f}%  {fv(avg_mfe):>8}  {fv(avg_mae):>8}  {fv(ratio):>8}  {fv(avg_pnl):>8}  {fv(total, dec=0):>8}")

        # Standard entries comparison
        print(f"\n  {'Standard (MA-allowed)':<25}  ", end="")
        if len(standard) > 0:
            n = len(standard)
            win = (standard["pnl_60m"] > 0).sum() / n * 100
            avg_mfe = standard["mfe"].mean()
            avg_mae = standard["mae"].mean()
            ratio = avg_mfe / avg_mae if avg_mae > 0 else float("inf")
            avg_pnl = standard["pnl_60m"].mean()
            total = standard["pnl_60m"].sum()
            print(f"{n:>5}  {win:>5.1f}%  {fv(avg_mfe):>8}  {fv(avg_mae):>8}  {fv(ratio):>8}  {fv(avg_pnl):>8}  {fv(total, dec=0):>8}")
        else:
            print("0")

        # List individual blocked trades
        print(f"\n  Individual blocked trades:")
        print(f"  {'Date':<12}  {'Dir':<6}  {'Entry':>7}  {'Time':<8}  {'BB%B':>6}  {'MFE':>6}  {'MAE':>6}  {'PnL60':>7}")
        print(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*7}")
        for _, r in blocked.sort_values("date").iterrows():
            bb_str = f"{r['bb30_pctb']:.2f}" if not np.isnan(r["bb30_pctb"]) else "NaN"
            print(f"  {r['date']}  {r['direction']:<6}  {r['entry_price']:>7.0f}  "
                  f"{r['entry_time'].strftime('%H:%M'):<8}  {bb_str:>6}  "
                  f"{r['mfe']:>6.0f}  {r['mae']:>6.0f}  {r['pnl_60m']:>7.0f}")
    else:
        print("\n  No MA-blocked entries found in this period.")

    # ── Section 4: BB%B extreme vs normal — standard entries breakdown ──────
    print("\n" + "=" * 72)
    print("[4/4] Standard Entries: BB%B Extreme vs Normal at Entry")
    print("=" * 72)

    if len(standard) > 0:
        std_extreme = standard[
            (standard["bb30_pctb"] > 1) | (standard["bb30_pctb"] < 0)
        ]
        std_normal = standard[
            (standard["bb30_pctb"] >= 0) & (standard["bb30_pctb"] <= 1)
        ]

        print(f"\n  {'Category':<25}  {'N':>5}  {'Win%':>6}  {'Avg MFE':>8}  {'Avg MAE':>8}  {'MFE/MAE':>8}  {'Avg PnL':>8}  {'Total':>8}")
        print(f"  {'-'*25}  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

        for label, grp in [("BB%B extreme (>1/<0)", std_extreme),
                           ("BB%B normal (0~1)", std_normal),
                           ("ALL standard", standard)]:
            if len(grp) == 0:
                print(f"  {label:<25}  {'0':>5}")
                continue
            n = len(grp)
            win = (grp["pnl_60m"] > 0).sum() / n * 100
            avg_mfe = grp["mfe"].mean()
            avg_mae = grp["mae"].mean()
            ratio = avg_mfe / avg_mae if avg_mae > 0 else float("inf")
            avg_pnl = grp["pnl_60m"].mean()
            total = grp["pnl_60m"].sum()
            print(f"  {label:<25}  {n:>5}  {win:>5.1f}%  {fv(avg_mfe):>8}  {fv(avg_mae):>8}  {fv(ratio):>8}  {fv(avg_pnl):>8}  {fv(total, dec=0):>8}")

    # ── Year-by-year blocked entries ────────────────────────────────────────
    if len(blocked) > 0:
        print(f"\n  Year-by-year blocked entry counts:")
        blocked_years = blocked.groupby(blocked["date"].apply(lambda d: d.year))
        for yr, grp in blocked_years:
            n = len(grp)
            win = (grp["pnl_60m"] > 0).sum()
            print(f"    {yr}: {n} blocked ({win} winners, {n - win} losers)")

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

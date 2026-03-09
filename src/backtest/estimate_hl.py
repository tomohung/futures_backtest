"""
Estimated High-Low Zone computation for TX futures day session.

Algorithm (per the design spec in specs/strategies/estimate-high-low-exit-strategy.md):
  1. Daily EMA(20) of session volume and session H-L range — computed from PRIOR completed
     days and carried forward; unavailable on the very first trading day in the dataset.
  2. Within each day, cumulative volume / cumulative time-factors gives an estimated total
     daily volume at each 15-min slot boundary.
  3. estimated_hl = estimated_volume / ema_volume * ema_hl
  4. Running average of per-slot estimates with a negative_weight=1.414 penalty when the
     new estimate is below the current running average.
  5. SatZoneUpper = session_low + avg - ema_hl/8
     SatZoneLower = session_high - avg + ema_hl/8
  6. Values are delayed by exactly one 15-min slot to prevent lookahead bias; the first
     slot's (08:45–08:59) bars always carry NaN.
"""

from datetime import time

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 15-min time-factor table (fraction of daily volume expected per slot)
# ---------------------------------------------------------------------------
TIME_FACTORS: dict[time, float] = {
    time(8, 45): 0.089,
    time(9, 0): 0.114,
    time(9, 15): 0.077,
    time(9, 30): 0.073,
    time(9, 45): 0.061,
    time(10, 0): 0.055,
    time(10, 15): 0.046,
    time(10, 30): 0.042,
    time(10, 45): 0.038,
    time(11, 0): 0.036,
    time(11, 15): 0.031,
    time(11, 30): 0.030,
    time(11, 45): 0.027,
    time(12, 0): 0.028,
    time(12, 15): 0.026,
    time(12, 30): 0.030,
    time(12, 45): 0.031,
    time(13, 0): 0.040,
    time(13, 15): 0.052,
    time(13, 30): 0.075,
}

_SLOT_TIMES: list[time] = sorted(TIME_FACTORS.keys())


def _get_slot(t: time) -> time | None:
    """Return the 15-min slot start time that contains bar time *t*."""
    slot = None
    for st in _SLOT_TIMES:
        if t >= st:
            slot = st
    return slot


def compute_estimate_hl_zones(df: pd.DataFrame, ema_period: int = 20) -> pd.DataFrame:
    """Compute Estimated H-L satisfaction zones for each 1-min bar.

    Parameters
    ----------
    df : pd.DataFrame
        Day-session 1-min OHLCV with ``DatetimeIndex``.
        Expected columns: ``Open``, ``High``, ``Low``, ``Close``, ``Volume``.
        **Pass the FULL history without date filtering** so that the EMA has
        sufficient warmup data.  Caller should filter by date afterwards.
    ema_period : int
        EMA period for daily volume and H-L range (default 20).

    Returns
    -------
    pd.DataFrame
        Same DataFrame with the following columns appended:

        * ``EmaVol``       – daily EMA of session volume (from prior days)
        * ``EmaHL``        – daily EMA of session H-L range (from prior days)
        * ``EstHL``        – running avg of per-slot estimated H-L for the day
        * ``SatZoneUpper`` – satisfaction zone upper bound (1-slot delayed)
        * ``SatZoneLower`` – satisfaction zone lower bound (1-slot delayed)
        * ``EstHighLevel`` – ``session_low + EstHL``
        * ``EstLowLevel``  – ``session_high - EstHL``
    """
    df = df.copy()
    for col in ("EmaVol", "EmaHL", "EstHL",
                "SatZoneUpper", "SatZoneLower",
                "EstHighLevel", "EstLowLevel"):
        df[col] = np.nan

    alpha = 2.0 / (ema_period + 1)
    ema_vol: float | None = None
    ema_hl: float | None = None

    dates = sorted(df.index.normalize().unique())

    for date in dates:
        mask = df.index.normalize() == date
        idx_list = df.index[mask].tolist()

        # ---- intra-day state ----
        session_high: float = -np.inf
        session_low: float = np.inf
        cum_vol: float = 0.0
        cum_factor: float = 0.0
        est_avg: float | None = None
        est_count: int = 0
        # pending sat_zone to broadcast to the CURRENT slot's bars
        pending: dict | None = None
        prev_slot: time | None = None

        for idx in idx_list:
            t = idx.time()
            slot = _get_slot(t)
            vol = df.at[idx, "Volume"]
            high = df.at[idx, "High"]
            low = df.at[idx, "Low"]

            # ---- slot boundary: finalise previous slot, stage new sat_zone ----
            if slot != prev_slot:
                if prev_slot is None:
                    # Very first bar of the day – initialise cumulative factor
                    cum_factor = TIME_FACTORS.get(slot, 0.0)
                else:
                    # Previous slot completed → compute estimated HL
                    if (ema_vol is not None and ema_hl is not None
                            and ema_vol > 0 and cum_factor > 0):
                        est_vol = cum_vol / cum_factor
                        est_hl = est_vol / ema_vol * ema_hl

                        if est_avg is None:
                            est_avg = est_hl
                            est_count = 1
                        elif est_count == 1:
                            # Second slot: equal weight with first (no penalty yet)
                            est_avg = (est_avg + est_hl) / 2
                            est_count = 2
                        else:
                            adj = (
                                est_hl - (est_avg - est_hl) * 1.414
                                if est_hl < est_avg
                                else est_hl
                            )
                            est_count += 1
                            est_avg = (
                                est_avg * (est_count - 1) + adj
                            ) / est_count

                        pending = {
                            "EmaVol": ema_vol,
                            "EmaHL": ema_hl,
                            "EstHL": est_avg,
                            "SatZoneUpper": session_low + est_avg - ema_hl / 8,
                            "SatZoneLower": session_high - est_avg + ema_hl / 8,
                            "EstHighLevel": session_low + est_avg,
                            "EstLowLevel": session_high - est_avg,
                        }

                    # Advance cumulative factor to include the new slot
                    cum_factor += TIME_FACTORS.get(slot, 0.0)

            # ---- accumulate this bar ----
            cum_vol += vol
            session_high = max(session_high, high)
            session_low = min(session_low, low)

            # ---- broadcast pending sat_zone to this bar ----
            if pending is not None:
                for col, val in pending.items():
                    df.at[idx, col] = val

            prev_slot = slot

        # ---- end of day: update EMA for subsequent days ----
        day_vol = df.loc[mask, "Volume"].sum()
        if session_high == -np.inf or session_low == np.inf:
            continue  # degenerate / empty day
        day_hl = session_high - session_low

        if ema_vol is None:
            ema_vol = float(day_vol)
            ema_hl = float(day_hl)
        else:
            ema_vol = float(day_vol) * alpha + ema_vol * (1 - alpha)
            ema_hl = float(day_hl) * alpha + ema_hl * (1 - alpha)

    return df


# ---------------------------------------------------------------------------
# Debugging helper
# ---------------------------------------------------------------------------

def debug_day(df: pd.DataFrame, date: str) -> None:
    """Print per-slot intermediate values for a given date.

    Parameters
    ----------
    df : pd.DataFrame
        Output of :func:`compute_estimate_hl_zones` (must contain ``EmaVol``
        and ``EmaHL`` columns).
    date : str
        Date string, e.g. ``"2025-03-01"``.
    """
    target = pd.Timestamp(date).normalize()
    mask = df.index.normalize() == target
    day_df = df[mask]

    if day_df.empty:
        print(f"No data for {date}")
        return

    # Retrieve EMA values that were used for this day (from the first bar that has them)
    valid = day_df["EmaVol"].notna()
    if valid.any():
        ema_vol = day_df.loc[valid, "EmaVol"].iloc[0]
        ema_hl = day_df.loc[valid, "EmaHL"].iloc[0]
        ema_str = f"EmaVol={ema_vol:,.0f}  EmaHL={ema_hl:.1f}"
    else:
        ema_vol = ema_hl = None
        ema_str = "EmaVol=N/A  EmaHL=N/A  (insufficient warmup)"

    print(f"\n{'='*78}")
    print(f"  debug_day: {date}   {ema_str}")
    print(f"{'='*78}")
    hdr = (f"  {'Slot':<8} {'CumVol':>10} {'CumFact':>8} {'EstVol':>10} "
           f"{'EstHL':>7} {'AvgHL':>7} {'SatZoneU':>10} {'SatZoneL':>10}")
    print(hdr)
    print(f"  {'-'*76}")

    # Recompute slot-by-slot (mirrors compute_estimate_hl_zones logic)
    session_high = -np.inf
    session_low = np.inf
    cum_vol = 0.0
    cum_factor = 0.0
    est_avg: float | None = None
    est_count = 0
    prev_slot: time | None = None

    def _print_slot(slot_label: time) -> None:
        if ema_vol is None or ema_vol <= 0 or cum_factor <= 0:
            return
        est_v = cum_vol / cum_factor
        est_hl = est_v / ema_vol * ema_hl
        avg = est_avg if est_avg is not None else est_hl
        sat_u = session_low + avg - ema_hl / 8
        sat_l = session_high - avg + ema_hl / 8
        print(
            f"  {str(slot_label):<8} {cum_vol:>10.0f} {cum_factor:>8.3f} "
            f"{est_v:>10.0f} {est_hl:>7.1f} {avg:>7.1f} "
            f"{sat_u:>10.1f} {sat_l:>10.1f}"
        )

    for idx in day_df.index:
        t = idx.time()
        slot = _get_slot(t)
        vol = day_df.at[idx, "Volume"]
        high = day_df.at[idx, "High"]
        low = day_df.at[idx, "Low"]

        if slot != prev_slot:
            if prev_slot is None:
                cum_factor = TIME_FACTORS.get(slot, 0.0)
            else:
                _print_slot(prev_slot)

                # Update running average
                if ema_vol is not None and ema_vol > 0 and cum_factor > 0:
                    est_vol_tmp = cum_vol / cum_factor
                    est_hl_tmp = est_vol_tmp / ema_vol * ema_hl
                    if est_avg is None:
                        est_avg = est_hl_tmp
                        est_count = 1
                    elif est_count == 1:
                        est_avg = (est_avg + est_hl_tmp) / 2
                        est_count = 2
                    else:
                        adj = (
                            est_hl_tmp - (est_avg - est_hl_tmp) * 1.414
                            if est_hl_tmp < est_avg
                            else est_hl_tmp
                        )
                        est_count += 1
                        est_avg = (est_avg * (est_count - 1) + adj) / est_count

                cum_factor += TIME_FACTORS.get(slot, 0.0)

        cum_vol += vol
        session_high = max(session_high, high)
        session_low = min(session_low, low)
        prev_slot = slot

    # Print the last slot
    if prev_slot is not None:
        _print_slot(prev_slot)

    print()

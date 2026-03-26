#!/usr/bin/env python3
"""
H039 Phase 1: Reversal CCD Bypass Conditions Audit

Faithfully replay the Reversal strategy's setup logic bar-by-bar.
For each triggered entry, record which bypass conditions were active,
then analyze the marginal contribution of each condition.

4 conditions in the OR clause:
  A: CCD correct (ccd > 0 for long, ccd < 0 for short)
  B: Exhaustion (bear_exhausted for long, bull_exhausted for short)
  C: Intraday VWAP (above_vwap for long, below_vwap for short) — 09:30+ only
  D: 2nd BB touch (bb_count >= 2)
"""
import sys
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from src.backtest.runner import load_data_for_reversal

ENTRY_START    = dtime(9, 10)
ENTRY_END      = dtime(10, 5)
VOL_RATIO      = 1.2
EXHAUST_FRAC   = 0.5
MFE_WINDOW     = 60   # bars after entry to measure MFE


def simulate(df_day):
    """Replay Reversal setup logic, collecting triggered entries with condition flags."""
    entries = []

    for date, day_df in df_day.groupby(df_day.index.normalize()):
        # ── Day init ──
        first = day_df.iloc[0]
        bc1, bc2 = float(first["VWAP1"]), float(first["VWAP2"])
        open_price = float(first["Open"])

        allow_long = allow_short = False
        bc_inside = False
        if not (np.isnan(bc1) or np.isnan(bc2)):
            bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)
            if open_price > bc_hi:
                allow_long = True
            elif open_price < bc_lo:
                allow_short = True
            else:
                bc_inside = True

        bb_long_touched = bb_short_touched = False
        bb_long_count = bb_short_count = 0
        bull_exhausted = bear_exhausted = False
        entered = False
        day_high = float(first["High"])
        day_low = float(first["Low"])
        sum_cv = 0.0
        sum_vol = 0.0

        for ts, row in day_df.iterrows():
            cur_time = ts.time()
            close = float(row["Close"])
            high = float(row["High"])
            low = float(row["Low"])
            vol = float(row["Volume"])

            day_high = max(day_high, high)
            day_low = min(day_low, low)
            sum_cv += close * vol
            sum_vol += vol

            if entered:
                continue

            ema_hl    = float(row["EmaHL"])
            ma5m      = float(row["MA5m_120"])
            ma5m_prev = float(row["MA5m_120_Prev"])
            bb_upper  = float(row["BB_Upper"])
            bb_lower  = float(row["BB_Lower"])
            vol_ma    = float(row["VolMA20"])
            ccd       = float(row["CCD_5m"])
            ma5       = float(row["MA5_1m"])

            if any(np.isnan(v) for v in
                   [ema_hl, ma5m, ma5m_prev, bb_upper, bb_lower, vol_ma, ma5]):
                continue

            bullish = ma5m > ma5m_prev

            # Resolve BC inside
            if bc_inside:
                bc_inside = False
                if bullish:
                    allow_long = True
                else:
                    allow_short = True

            if not (allow_long or allow_short):
                continue

            vol_ok = vol > VOL_RATIO * vol_ma

            # Exhaustion latch
            if not bull_exhausted and close >= day_low + ema_hl * EXHAUST_FRAC:
                bull_exhausted = True
            if not bear_exhausted and close <= day_high - ema_hl * EXHAUST_FRAC:
                bear_exhausted = True

            # BB touch latch
            if allow_long and bullish and not bb_long_touched:
                if close <= bb_lower and vol_ok:
                    bb_long_touched = True
                    bb_long_count += 1

            if allow_short and not bullish and not bb_short_touched:
                if close >= bb_upper and vol_ok:
                    bb_short_touched = True
                    bb_short_count += 1

            # Step 2: trigger
            if ENTRY_START <= cur_time <= ENTRY_END:
                vwap = sum_cv / sum_vol if sum_vol > 0 else None
                vwap_active = cur_time >= dtime(9, 30)
                above_vwap = vwap_active and vwap is not None and close > vwap
                below_vwap = vwap_active and vwap is not None and close < vwap

                # Condition flags for long
                if allow_long and bullish and bb_long_touched:
                    cond_A = ccd > 0
                    cond_B = bear_exhausted
                    cond_C = above_vwap
                    cond_D = bb_long_count >= 2

                    setup_ok = cond_A or cond_B or cond_C or cond_D

                    if setup_ok and close > ma5:
                        # Measure MFE/MAE
                        after = day_df[day_df.index > ts].head(MFE_WINDOW)
                        mfe = float(after["High"].max() - close) if len(after) > 0 else 0
                        mae = float(close - after["Low"].min()) if len(after) > 0 else 0

                        entries.append({
                            "timestamp": ts, "date": date,
                            "direction": "long", "close": close,
                            "ema_hl": ema_hl,
                            "A_ccd": cond_A, "B_exhaust": cond_B,
                            "C_vwap": cond_C, "D_2nd_bb": cond_D,
                            "mfe": mfe, "mae": mae,
                            "mfe_ratio": mfe / ema_hl if ema_hl > 0 else 0,
                            "profitable": mfe > mae,
                        })
                        entered = True
                        continue

                # Condition flags for short
                if allow_short and not bullish and bb_short_touched:
                    cond_A = ccd < 0
                    cond_B = bull_exhausted
                    cond_C = below_vwap
                    cond_D = bb_short_count >= 2

                    setup_ok = cond_A or cond_B or cond_C or cond_D

                    if setup_ok and close < ma5:
                        after = day_df[day_df.index > ts].head(MFE_WINDOW)
                        mfe = float(close - after["Low"].min()) if len(after) > 0 else 0
                        mae = float(after["High"].max() - close) if len(after) > 0 else 0

                        entries.append({
                            "timestamp": ts, "date": date,
                            "direction": "short", "close": close,
                            "ema_hl": ema_hl,
                            "A_ccd": cond_A, "B_exhaust": cond_B,
                            "C_vwap": cond_C, "D_2nd_bb": cond_D,
                            "mfe": mfe, "mae": mae,
                            "mfe_ratio": mfe / ema_hl if ema_hl > 0 else 0,
                            "profitable": mfe > mae,
                        })
                        entered = True
                        continue

            # Reset BB latch on MA5 cross
            if close > ma5:
                bb_long_touched = False
            if close < ma5:
                bb_short_touched = False

    return pd.DataFrame(entries)


def main():
    print("=" * 70)
    print("H039 Phase 1: Reversal CCD Bypass Conditions Audit")
    print("=" * 70)

    print("\n[1/2] Loading 1m data...")
    df_day = load_data_for_reversal()
    print(f"  {len(df_day):,} bars, {df_day.index[0].date()} ~ {df_day.index[-1].date()}")

    print("\n[2/2] Simulating Reversal setup logic...")
    entries = simulate(df_day)
    print(f"  {len(entries)} triggered entries "
          f"(long: {(entries['direction'] == 'long').sum()}, "
          f"short: {(entries['direction'] == 'short').sum()})")

    CONDS = ["A_ccd", "B_exhaust", "C_vwap", "D_2nd_bb"]
    LABELS = {"A_ccd": "CCD correct", "B_exhaust": "Exhaustion",
              "C_vwap": "VWAP bypass", "D_2nd_bb": "2nd BB touch"}

    # ── 1. Trigger frequency ───────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("1. CONDITION FREQUENCY (how often each condition is True at trigger)")
    print(f"{'=' * 70}")
    n = len(entries)
    for c in CONDS:
        cnt = entries[c].sum()
        print(f"  {LABELS[c]:15s}: {cnt:4d} / {n} ({cnt/n*100:5.1f}%)")

    # ── 2. Co-occurrence matrix ────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("2. CO-OCCURRENCE MATRIX (% of entries where both are True)")
    print(f"{'=' * 70}")
    header = "              " + "".join(f" {LABELS[c]:>13s}" for c in CONDS)
    print(header)
    for c1 in CONDS:
        row = f"  {LABELS[c1]:12s}"
        for c2 in CONDS:
            both = (entries[c1] & entries[c2]).sum()
            row += f" {both/n*100:12.1f}%"
        print(row)

    # ── 3. Exclusive triggers ──────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("3. EXCLUSIVE TRIGGERS (entry would NOT happen without this condition)")
    print(f"{'=' * 70}")
    print(f"{'Condition':>15s} | {'N_excl':>6s} | {'Prof%':>6s} | "
          f"{'AvgMFE':>7s} | {'MFE/HL':>7s} | {'AvgMAE':>7s}")

    for c in CONDS:
        others = [x for x in CONDS if x != c]
        # Exclusive: this condition is True AND all others are False
        # → without this condition, the OR clause would be False
        excl_mask = entries[c].copy()
        for o in others:
            excl_mask = excl_mask & ~entries[o]

        excl = entries[excl_mask]
        ne = len(excl)
        if ne == 0:
            print(f"  {LABELS[c]:13s} | {ne:6d} | (none)")
            continue
        prof = excl["profitable"].mean() * 100
        avg_mfe = excl["mfe"].mean()
        avg_ratio = excl["mfe_ratio"].mean()
        avg_mae = excl["mae"].mean()
        print(f"  {LABELS[c]:13s} | {ne:6d} | {prof:5.1f}% | "
              f"{avg_mfe:6.0f}pt | {avg_ratio:6.3f} | {avg_mae:6.0f}pt")

    # ── 4. Condition-specific profitability ────────────────────────
    print(f"\n{'=' * 70}")
    print("4. CONDITION-SPECIFIC PROFITABILITY (all entries where condition is True)")
    print(f"{'=' * 70}")
    print(f"{'Condition':>15s} | {'N':>5s} | {'Prof%':>6s} | "
          f"{'AvgMFE':>7s} | {'MFE/HL':>7s} | {'AvgMAE':>7s} | {'MFE>MAE%':>8s}")

    # Baseline: all entries
    prof_all = entries["profitable"].mean() * 100
    mfe_all = entries["mfe"].mean()
    ratio_all = entries["mfe_ratio"].mean()
    mae_all = entries["mae"].mean()
    mfe_gt_all = (entries["mfe"] > entries["mae"]).mean() * 100
    print(f"  {'ALL':13s} | {n:5d} | {prof_all:5.1f}% | "
          f"{mfe_all:6.0f}pt | {ratio_all:6.3f} | {mae_all:6.0f}pt | {mfe_gt_all:7.1f}%")

    for c in CONDS:
        sub = entries[entries[c]]
        ns = len(sub)
        if ns == 0:
            continue
        prof = sub["profitable"].mean() * 100
        avg_mfe = sub["mfe"].mean()
        avg_ratio = sub["mfe_ratio"].mean()
        avg_mae = sub["mae"].mean()
        mfe_gt = (sub["mfe"] > sub["mae"]).mean() * 100
        print(f"  {LABELS[c]:13s} | {ns:5d} | {prof:5.1f}% | "
              f"{avg_mfe:6.0f}pt | {avg_ratio:6.3f} | {avg_mae:6.0f}pt | {mfe_gt:7.1f}%")

    # Entries where CCD is WRONG (bypass needed)
    bypass_mask = ~entries["A_ccd"]
    bypass = entries[bypass_mask]
    nb = len(bypass)
    if nb > 0:
        prof_b = bypass["profitable"].mean() * 100
        mfe_b = bypass["mfe"].mean()
        ratio_b = bypass["mfe_ratio"].mean()
        mae_b = bypass["mae"].mean()
        mfe_gt_b = (bypass["mfe"] > bypass["mae"]).mean() * 100
        print(f"  {'CCD wrong':13s} | {nb:5d} | {prof_b:5.1f}% | "
              f"{mfe_b:6.0f}pt | {ratio_b:6.3f} | {mae_b:6.0f}pt | {mfe_gt_b:7.1f}%")

    # ── 5. Ablation: what if we remove each bypass? ────────────────
    print(f"\n{'=' * 70}")
    print("5. ABLATION: ENTRIES LOST IF CONDITION REMOVED")
    print(f"{'=' * 70}")
    print(f"{'Remove':>15s} | {'Lost':>5s} | {'Lost%':>6s} | "
          f"{'Lost_Prof%':>10s} | {'Remain':>6s} | {'Remain_Prof%':>12s}")

    for c in CONDS:
        others = [x for x in CONDS if x != c]
        # Without this condition: entry requires at least one of the others
        would_enter = entries[others].any(axis=1)
        lost = entries[~would_enter]
        remain = entries[would_enter]
        nl, nr = len(lost), len(remain)
        lp = lost["profitable"].mean() * 100 if nl > 0 else 0
        rp = remain["profitable"].mean() * 100 if nr > 0 else 0
        print(f"  {LABELS[c]:13s} | {nl:5d} | {nl/n*100:5.1f}% | "
              f"{lp:9.1f}% | {nr:6d} | {rp:11.1f}%")

    # ── 6. Direction breakdown ─────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("6. BY DIRECTION: EXCLUSIVE TRIGGER PROFITABILITY")
    print(f"{'=' * 70}")
    for direction in ["long", "short"]:
        dir_entries = entries[entries["direction"] == direction]
        nd = len(dir_entries)
        print(f"\n  {direction.upper()} (N={nd}, prof={dir_entries['profitable'].mean()*100:.1f}%)")

        for c in CONDS:
            others = [x for x in CONDS if x != c]
            excl_mask = dir_entries[c].copy()
            for o in others:
                excl_mask = excl_mask & ~dir_entries[o]
            excl = dir_entries[excl_mask]
            ne = len(excl)
            if ne == 0:
                print(f"    {LABELS[c]:13s}: N=0")
                continue
            prof = excl["profitable"].mean() * 100
            print(f"    {LABELS[c]:13s}: N={ne:3d}, prof={prof:5.1f}%")

    # ── 7. Year-by-year: bypass vs CCD-only ────────────────────────
    print(f"\n{'=' * 70}")
    print("7. YEAR-BY-YEAR: CCD-CORRECT vs BYPASS-ONLY ENTRIES")
    print(f"{'=' * 70}")
    entries["year"] = pd.to_datetime(entries["date"]).dt.year
    print(f"{'Year':>5s} | {'N_ccd':>5s} {'Prof%':>6s} | {'N_byp':>5s} {'Prof%':>6s} | {'Delta':>7s}")
    for year in sorted(entries["year"].unique()):
        yr = entries[entries["year"] == year]
        ccd_ok = yr[yr["A_ccd"]]
        bypass_only = yr[~yr["A_ccd"]]
        nc, nb = len(ccd_ok), len(bypass_only)
        pc = ccd_ok["profitable"].mean() * 100 if nc > 0 else 0
        pb = bypass_only["profitable"].mean() * 100 if nb > 0 else 0
        delta = pb - pc
        print(f"  {year} | {nc:5d} {pc:5.1f}% | {nb:5d} {pb:5.1f}% | {delta:+6.1f}%")

    # ── 8. Condition combination patterns ──────────────────────────
    print(f"\n{'=' * 70}")
    print("8. TOP CONDITION COMBINATIONS")
    print(f"{'=' * 70}")
    entries["combo"] = ""
    for c in CONDS:
        entries["combo"] = entries["combo"] + entries[c].map({True: LABELS[c][0], False: "."})

    combo_stats = entries.groupby("combo").agg(
        N=("profitable", "size"),
        prof_pct=("profitable", "mean"),
        avg_mfe=("mfe", "mean"),
    ).sort_values("N", ascending=False)

    combo_stats["prof_pct"] *= 100
    print(f"{'Pattern':>8s} | {'N':>5s} | {'Prof%':>6s} | {'AvgMFE':>7s} | Interpretation")
    print(f"  (C=CCD, E=Exhaust, V=VWAP, 2=2ndBB)")
    for combo, row in combo_stats.head(15).iterrows():
        interp = []
        if combo[0] == "C":
            interp.append("CCD")
        if combo[1] == "E":
            interp.append("Exh")
        if combo[2] == "V":
            interp.append("VWAP")
        if combo[3] == "2":
            interp.append("2nd")
        print(f"  {combo:>6s} | {int(row['N']):5d} | {row['prof_pct']:5.1f}% | "
              f"{row['avg_mfe']:6.0f}pt | {'+'.join(interp)}")


if __name__ == "__main__":
    main()

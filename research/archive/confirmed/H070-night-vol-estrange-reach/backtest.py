#!/usr/bin/env python3
"""H070 Phase 2: Night Vol × SatZone Adjustment.

Step 1: Analyze exit reasons × night_norm
Step 2: Test SatZone scaling
Step 3: R/R threshold
Step 4: Compare all configs

Usage:
    uv run python research/active/H070-night-vol-estrange-reach/backtest.py
"""

import bisect
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

from backtesting import Backtest
from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H070-night-vol-estrange-reach/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END = "2024-12-31"
OOS_START = "2025-01-01"


def compute_night_norm():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS trade_date
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
            ORDER BY trade_date
        """).df()
        day_dates_list = sorted(pd.to_datetime(day_dates_df["trade_date"]).tolist())
        night_raw = conn.execute("""
            SELECT timestamp, high, low
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()

    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    def find_next(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next)
    night_raw = night_raw.dropna(subset=["trade_date"])
    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["night_norm"] = night["night_range"] / night["sma20"]
    return night


def enrich_trades(trades, data_df, night_df):
    """Add exit reason, SatZone distance, R/R ratio, night_norm to trades."""
    trades = trades.copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["ExitTime"] = pd.to_datetime(trades["ExitTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year
    trades["is_long"] = trades["Size"] > 0

    enriched = []
    for _, t in trades.iterrows():
        entry_ts = t["EntryTime"]
        exit_ts = t["ExitTime"]

        # Find entry bar in data
        if entry_ts in data_df.index:
            bar = data_df.loc[entry_ts]
        else:
            idx = data_df.index.get_indexer([entry_ts], method="nearest")[0]
            bar = data_df.iloc[idx]

        ema_hl = float(bar["EmaHL"]) if not np.isnan(bar["EmaHL"]) else None
        sat_upper = float(bar["SatZoneUpper"]) if not np.isnan(bar["SatZoneUpper"]) else None
        sat_lower = float(bar["SatZoneLower"]) if not np.isnan(bar["SatZoneLower"]) else None
        entry_price = float(t["EntryPrice"])

        # SL distance
        sl_dist = ema_hl * 0.25 if ema_hl else None

        # SatZone distance (target)
        if t["is_long"] and sat_upper:
            sat_dist = sat_upper - entry_price
        elif not t["is_long"] and sat_lower:
            sat_dist = entry_price - sat_lower
        else:
            sat_dist = None

        # R/R ratio
        rr = sat_dist / sl_dist if sat_dist and sl_dist and sl_dist > 0 else None

        # Infer exit reason
        exit_time = exit_ts.time()
        pnl = float(t["PnL"])

        if exit_time >= pd.Timestamp("13:30").time():
            exit_reason = "time_stop"
        elif sl_dist and abs(pnl + sl_dist) < sl_dist * 0.15:
            exit_reason = "sl"
        elif pnl > 0:
            exit_reason = "satzone_or_trail"
        else:
            exit_reason = "trail_or_other"

        row = t.to_dict()
        row.update({
            "ema_hl": ema_hl,
            "sat_dist": sat_dist,
            "sl_dist": sl_dist,
            "rr_ratio": rr,
            "exit_reason": exit_reason,
        })
        enriched.append(row)

    result = pd.DataFrame(enriched)

    # Merge night_norm
    result = result.merge(
        night_df[["night_norm"]], left_on="trade_date", right_index=True, how="inner"
    )
    return result


def calc(t):
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg": 0, "total": 0, "sharpe": 0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    pnl_pct = t["PnL"] / t["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean(), "total": t["PnL"].sum(), "sharpe": sharpe}


def fmt(s):
    return (f"N={s['N']:3d}  WR={s['WR']:.1%}  PF={s['PF']:.2f}  "
            f"avg={s['avg']:+.0f}  total={s['total']:+,.0f}  Sharpe={s['sharpe']:.2f}")


def analyze_strategy(name, trades_enriched):
    """Full analysis for one strategy."""
    df = trades_enriched
    print(f"\n{'=' * 70}")
    print(f"  {name}  (N={len(df)})")
    print(f"{'=' * 70}")

    # ── Step 1: Exit reasons × night_norm ──
    print(f"\n── Step 1: 出場原因 × 夜盤波動 ──")

    norm_groups = [
        ("norm < 0.85 (STOP)", df["night_norm"] < 0.85),
        ("norm ≥ 0.85 (GO)", df["night_norm"] >= 0.85),
    ]

    for label, mask in norm_groups:
        sub = df[mask]
        if len(sub) == 0:
            continue
        print(f"\n  {label} (N={len(sub)}):")
        for reason in ["satzone_or_trail", "trail_or_other", "sl", "time_stop"]:
            r_sub = sub[sub["exit_reason"] == reason]
            pct = len(r_sub) / len(sub)
            s = calc(r_sub)
            print(f"    {reason:>20s}: {pct:>5.1%} ({s['N']:>3})  PF={s['PF']:.2f}  avg={s['avg']:+.0f}")

    # ── Step 1b: R/R ratio distribution ──
    print(f"\n── Step 1b: R/R ratio × 夜盤波動 ──")
    valid_rr = df.dropna(subset=["rr_ratio"])
    for label, mask in norm_groups:
        sub = valid_rr[mask[valid_rr.index]]
        if len(sub) == 0:
            continue
        rr = sub["rr_ratio"]
        print(f"  {label}: N={len(sub)}  mean_RR={rr.mean():.2f}  "
              f"median={rr.median():.2f}  RR<1.0={( rr < 1.0).mean():.1%}")

    # ── Step 2: SatZone scaling simulation ──
    print(f"\n── Step 2: SatZone 縮放模擬 ──")
    print("  (用 R/R ratio 近似：scale 後 sat_dist 縮小，PnL 等比縮放)")

    stop_trades = df[df["night_norm"] < 0.85].copy()
    go_trades = df[df["night_norm"] >= 0.85].copy()

    if len(stop_trades) > 0:
        print(f"\n  低夜盤 (STOP) 交易 (N={len(stop_trades)}):")
        print(f"  {'scale':>6}  {'N':>4} {'WR':>5} {'PF':>5} {'avg':>6} {'total':>7} {'vs_不做':>7}")

        baseline_go = calc(go_trades)

        for scale in [0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.00]:
            # Approximate: scale SatZone → profitable trades' PnL scales down,
            # but more trades hit SatZone (fewer time stops)
            # Simple model: multiply sat_dist by scale, cap PnL at scaled target
            simulated = stop_trades.copy()
            if scale < 1.0:
                # For winning trades: cap PnL at scale * original sat_dist
                for idx in simulated.index:
                    sd = simulated.loc[idx, "sat_dist"]
                    pnl = simulated.loc[idx, "PnL"]
                    if pd.notna(sd) and sd > 0 and pnl > 0:
                        scaled_target = sd * scale
                        simulated.loc[idx, "PnL"] = min(pnl, scaled_target)

            s = calc(simulated)
            combined = calc(pd.concat([go_trades, simulated]))
            print(f"  {scale:>6.2f}  {s['N']:>4} {s['WR']:>5.1%} {s['PF']:>5.2f} "
                  f"{s['avg']:>+6.0f} {s['total']:>+7,.0f}  "
                  f"combined PF={combined['PF']:.2f}")

        # vs just not doing (Config A)
        print(f"\n  Config A (不做 STOP): {fmt(baseline_go)}")

    # ── Step 3: R/R threshold ──
    print(f"\n── Step 3: R/R 門檻 ──")
    valid = df.dropna(subset=["rr_ratio"])
    print(f"  {'RR_min':>6}  {'N':>4} {'WR':>5} {'PF':>5} {'avg':>6} {'total':>7}")
    for rr_min in [0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
        sub = valid[valid["rr_ratio"] >= rr_min]
        s = calc(sub)
        print(f"  {rr_min:>6.1f}  {s['N']:>4} {s['WR']:>5.1%} {s['PF']:>5.2f} "
              f"{s['avg']:>+6.0f} {s['total']:>+7,.0f}")

    # ── Step 4: Config comparison (IS/OOS) ──
    print(f"\n── Step 4: Config 比較 (IS/OOS) ──")

    is_t = df[df["trade_date"] <= IS_END]
    oos_t = df[df["trade_date"] >= OOS_START]
    wd_skip_esthl = [3, 4]  # Thu, Fri
    wd_skip_rev = [0, 4]    # Mon, Fri

    wd_skip = wd_skip_esthl if "EstHL" in name else wd_skip_rev

    configs = {
        "A: 現狀 (weekday+NVF)": lambda t: (t["night_norm"] >= 0.85) & (~t["weekday"].isin(wd_skip)),
        "B: NVF only (無星期)": lambda t: t["night_norm"] >= 0.85,
        "C: 全做 + RR≥1.0": lambda t: t["rr_ratio"].fillna(0) >= 1.0,
        "D: NVF + RR≥1.0": lambda t: (t["night_norm"] >= 0.85) & (t["rr_ratio"].fillna(0) >= 1.0),
        "E: night_norm only (無星期無RR)": lambda t: t["night_norm"] >= 0.85,
        "F: 全做 (no filter)": lambda t: pd.Series(True, index=t.index),
    }

    print(f"\n  {'Config':>30}  {'IS_N':>5} {'IS_PF':>6} {'IS_Sh':>6}  "
          f"{'OOS_N':>5} {'OOS_PF':>6} {'OOS_Sh':>6}")
    for cname, filt in configs.items():
        si = calc(is_t[filt(is_t)])
        so = calc(oos_t[filt(oos_t)])
        print(f"  {cname:>30}  {si['N']:>5} {si['PF']:>6.2f} {si['sharpe']:>6.2f}  "
              f"{so['N']:>5} {so['PF']:>6.2f} {so['sharpe']:>6.2f}")


def main():
    night = compute_night_norm()

    # ── EstHL ──
    print("Loading EstHL data...")
    df_esthl = load_data_for_orb_est_hl()
    bt = Backtest(df_esthl, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(sl_ema_fraction=0.25, adx_min=0.0, long_only=True,
                   vwap_days=2, skip_thursday=False, skip_friday=False)
    esthl_trades = enrich_trades(stats["_trades"], df_esthl, night)
    analyze_strategy("EstHL", esthl_trades)

    # ── Reversal ──
    print("\n\nLoading Reversal data...")
    df_rev = load_data_for_reversal()
    bt = Backtest(df_rev, ReversalStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                   signal_skip=0, sat_pullback_fraction=0.5)
    rev_trades = enrich_trades(stats["_trades"], df_rev, night)
    analyze_strategy("Reversal", rev_trades)


if __name__ == "__main__":
    main()

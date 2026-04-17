#!/usr/bin/env python3
"""H069: Strong Night Vol Override on Weak Weekdays.

Usage:
    uv run python research/active/H069-strong-night-override/explore.py
"""

import bisect
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

from backtesting import Backtest
from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H069-strong-night-override/results")
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


def calc(t):
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg": 0, "total": 0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean(), "total": t["PnL"].sum()}


def analyze_combo(merged, weekday, wd_name, strategy_name, thresholds):
    """Deep analysis of one weekday × threshold combo."""
    wd_data = merged[merged["weekday"] == weekday].sort_values("EntryTime")

    print(f"\n{'─' * 70}")
    print(f"  {strategy_name} {wd_name}（全部 N={len(wd_data)}, PF={calc(wd_data)['PF']:.2f}）")
    print(f"{'─' * 70}")

    for thr in thresholds:
        sub = wd_data[wd_data["night_norm"] >= thr].copy()
        s = calc(sub)
        if s["N"] < 3:
            print(f"\n  norm >= {thr:.2f}: N={s['N']}（太少，跳過）")
            continue

        # Robustness: remove best trade
        if s["N"] > 1:
            best_idx = sub["PnL"].idxmax()
            s_no_best = calc(sub.drop(best_idx))
            robust = f"移除最佳後 PF={s_no_best['PF']:.2f}"
        else:
            robust = "—"

        print(f"\n  norm >= {thr:.2f}: N={s['N']}  WR={s['WR']:.1%}  PF={s['PF']:.2f}  "
              f"avg={s['avg']:+.0f}  total={s['total']:+,.0f}  ({robust})")

        # Yearly
        years = sorted(sub["year"].unique())
        n_pos = 0
        print(f"    {'Year':>6} {'N':>3} {'WR':>5} {'PF':>5} {'total':>7}")
        for y in years:
            sy = calc(sub[sub["year"] == y])
            if sy["N"] > 0:
                pos = "✓" if sy["PF"] > 1.0 else "✗"
                if sy["PF"] > 1.0:
                    n_pos += 1
                print(f"    {y:>6} {sy['N']:>3} {sy['WR']:>5.0%} {sy['PF']:>5.2f} {sy['total']:>+7,.0f} {pos}")
        print(f"    consistency: {n_pos}/{len(years)}")

        # IS/OOS
        is_sub = sub[sub["trade_date"] <= IS_END]
        oos_sub = sub[sub["trade_date"] >= OOS_START]
        si = calc(is_sub)
        so = calc(oos_sub)
        print(f"    IS:  N={si['N']:>3}  PF={si['PF']:.2f}  total={si['total']:+,.0f}")
        print(f"    OOS: N={so['N']:>3}  PF={so['PF']:.2f}  total={so['total']:+,.0f}")

        # Trade-by-trade
        print(f"    逐筆交易:")
        for _, row in sub.iterrows():
            d = row["EntryTime"].strftime("%Y-%m-%d")
            nn = row["night_norm"]
            pnl = row["PnL"]
            marker = "✓" if pnl > 0 else "✗"
            print(f"      {d}  norm={nn:.2f}  PnL={pnl:+,.0f}  {marker}")


def main():
    night = compute_night_norm()

    # ── EstHL ──
    print("=" * 70)
    print("EstHL：週四 × 強夜盤")
    print("=" * 70)

    df = load_data_for_orb_est_hl()
    bt = Backtest(df, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                   skip_thursday=False, skip_friday=False)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year
    m_esthl = trades.merge(night[["night_norm"]], left_on="trade_date",
                           right_index=True, how="inner")

    analyze_combo(m_esthl, 3, "Thu", "EstHL", [1.0, 1.15, 1.3])

    # Also confirm Fri is hopeless
    analyze_combo(m_esthl, 4, "Fri", "EstHL", [1.15, 1.3])

    # ── Reversal ──
    print(f"\n\n{'=' * 70}")
    print("Reversal：週五 × 強夜盤")
    print("=" * 70)

    df = load_data_for_reversal()
    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                   signal_skip=0, sat_pullback_fraction=0.5)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year
    m_rev = trades.merge(night[["night_norm"]], left_on="trade_date",
                         right_index=True, how="inner")

    analyze_combo(m_rev, 4, "Fri", "Reversal", [1.0, 1.15, 1.3, 1.5])

    # Also confirm Mon is hopeless
    analyze_combo(m_rev, 0, "Mon", "Reversal", [1.15, 1.3])


if __name__ == "__main__":
    main()

"""
Analyze trade date overlap between EstHL and ORBLong strategies since 2025.

Usage:
    uv run python src/backtest/analyze_overlap.py --start 2025-01-01
"""

import argparse
from pathlib import Path

import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, load_data_with_night_ma
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy


def main():
    parser = argparse.ArgumentParser(description="Overlap analysis: EstHL vs ORBLong")
    parser.add_argument("--start", default="2025-01-01", metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None,          metavar="YYYY-MM-DD")
    args = parser.parse_args()

    print("Loading EstHL data...")
    df_esthl = load_data_for_orb_est_hl(start=args.start, end=args.end)

    print("Loading ORBLong data...")
    df_orb = load_data_with_night_ma(start=args.start, end=args.end, trend_ma_days=10)

    # ── Run EstHL ─────────────────────────────────────────────────────────
    print("Running EstHL strategy...")
    bt_esthl = Backtest(df_esthl, ORBWithEstHLExitStrategy,
                        cash=200_000, commission=0.0, trade_on_close=True)
    stats_esthl = bt_esthl.run(
        sl_ema_fraction=0.25,
        long_only=True,
        vwap_days=2,
        skip_thursday=True,
        skip_friday=True,
    )
    trades_esthl = stats_esthl["_trades"].copy()
    trades_esthl["entry_date"] = pd.to_datetime(trades_esthl["EntryTime"]).dt.date
    trades_esthl["strategy"] = "EstHL"

    # ── Run ORBLong ────────────────────────────────────────────────────────
    print("Running ORBLong strategy...")
    bt_orb = Backtest(df_orb, ORBLongStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
    stats_orb = bt_orb.run(
        sl_pct=0.004,
        tp_or_multiplier=1.5,
        trend_ma_days=10,
        or_pct_min=0.3,
        or_pct_max=1.0,
        force_exit_minute=300,
        thu_or_pct_min=0.7,
    )
    trades_orb = stats_orb["_trades"].copy()
    trades_orb["entry_date"] = pd.to_datetime(trades_orb["EntryTime"]).dt.date
    trades_orb["strategy"] = "ORBLong"

    # ── Find overlapping dates ─────────────────────────────────────────────
    dates_esthl = set(trades_esthl["entry_date"])
    dates_orb   = set(trades_orb["entry_date"])
    overlap_dates = sorted(dates_esthl & dates_orb)

    print(f"\nEstHL total trades  : {len(trades_esthl)}")
    print(f"ORBLong total trades: {len(trades_orb)}")
    print(f"Overlapping days    : {len(overlap_dates)}")
    print(f"Only EstHL days     : {len(dates_esthl - dates_orb)}")
    print(f"Only ORBLong days   : {len(dates_orb - dates_esthl)}")

    if not overlap_dates:
        print("\nNo overlapping trade days found.")
        return

    # ── Build overlap table ────────────────────────────────────────────────
    rows = []
    for d in overlap_dates:
        e = trades_esthl[trades_esthl["entry_date"] == d].iloc[0]
        o = trades_orb  [trades_orb  ["entry_date"] == d].iloc[0]
        rows.append({
            "date":         d,
            "esthl_entry":  e["EntryTime"],
            "esthl_exit":   e["ExitTime"],
            "esthl_pnl":    e["PnL"],
            "orb_entry":    o["EntryTime"],
            "orb_exit":     o["ExitTime"],
            "orb_pnl":      o["PnL"],
            "combined_pnl": e["PnL"] + o["PnL"],
        })

    df_overlap = pd.DataFrame(rows)
    df_overlap["esthl_win"]    = df_overlap["esthl_pnl"] > 0
    df_overlap["orb_win"]      = df_overlap["orb_pnl"]   > 0
    df_overlap["both_win"]     = df_overlap["esthl_win"] & df_overlap["orb_win"]
    df_overlap["both_lose"]    = ~df_overlap["esthl_win"] & ~df_overlap["orb_win"]
    df_overlap["split"]        = df_overlap["esthl_win"] ^ df_overlap["orb_win"]

    # ── Print detail table ─────────────────────────────────────────────────
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.width", 120)

    print("\n── Overlapping Trade Days ─────────────────────────────────────────────")
    print(f"{'Date':<12} {'EstHL Entry':<22} {'EstHL Exit':<22} {'EstHL PnL':>10}"
          f"  {'ORB Entry':<22} {'ORB Exit':<22} {'ORB PnL':>9}  {'Combined':>9}")
    print("-" * 130)
    for _, r in df_overlap.iterrows():
        outcome = "✓✓" if r["both_win"] else ("✗✗" if r["both_lose"] else "±")
        print(f"{str(r['date']):<12} {str(r['esthl_entry']):<22} {str(r['esthl_exit']):<22}"
              f" {r['esthl_pnl']:>10.0f}  {str(r['orb_entry']):<22} {str(r['orb_exit']):<22}"
              f" {r['orb_pnl']:>9.0f}  {r['combined_pnl']:>9.0f}  {outcome}")

    # ── Summary ────────────────────────────────────────────────────────────
    n = len(df_overlap)
    print("\n── Overlap Summary ────────────────────────────────────────────────────")
    print(f"  Both win    : {df_overlap['both_win'].sum():3d}  ({df_overlap['both_win'].mean()*100:.1f}%)")
    print(f"  Both lose   : {df_overlap['both_lose'].sum():3d}  ({df_overlap['both_lose'].mean()*100:.1f}%)")
    print(f"  Split       : {df_overlap['split'].sum():3d}  ({df_overlap['split'].mean()*100:.1f}%)")
    print(f"  EstHL PnL   : {df_overlap['esthl_pnl'].sum():+.0f} pts")
    print(f"  ORBLong PnL : {df_overlap['orb_pnl'].sum():+.0f} pts")
    print(f"  Combined    : {df_overlap['combined_pnl'].sum():+.0f} pts")

    # ── Save ───────────────────────────────────────────────────────────────
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    date_part = args.start.replace("-", "")
    if args.end:
        date_part += f"_{args.end.replace('-', '')}"
    out_path = out_dir / f"overlap_esthl_orb_{date_part}.csv"
    df_overlap.to_csv(out_path, index=False)
    print(f"\nOverlap table saved → {out_path}")


if __name__ == "__main__":
    main()

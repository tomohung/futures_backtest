#!/usr/bin/env python3
"""H044: Compare Reversal live trades vs backtest trades.

Reads live_parsed.csv (strategy=reversal), runs ReversalStrategy backtest
over the same date range, and produces a side-by-side comparison.
"""
import csv
import sys
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

DATA_DIR = Path(__file__).parent / "data"
LIVE_CSV = DATA_DIR / "live_parsed.csv"

REVERSAL_PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
)


def load_live_reversal() -> pd.DataFrame:
    """Load live reversal trades from parsed CSV."""
    rows = []
    with open(LIVE_CSV) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["strategy"] != "reversal":
                continue
            if not r["entry_price"] or not r["exit_price"]:
                continue
            rows.append({
                "date": r["date"],
                "direction": r["direction"],
                "entry_time": r["entry_time"],
                "entry_price": int(r["entry_price"]),
                "exit_strategy": r["exit_strategy"],
                "exit_time": r["exit_time"],
                "exit_price": int(r["exit_price"]),
                "pnl": int(r["pnl"]) if r["pnl"] else None,
            })
    return pd.DataFrame(rows)


def run_backtest_trades(start: str, end: str) -> pd.DataFrame:
    """Run Reversal backtest and extract trades."""
    df = load_data_for_reversal()
    df = df[df.index >= start]
    if end:
        df = df[df.index <= end]
    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**REVERSAL_PARAMS)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["ExitTime"] = pd.to_datetime(trades["ExitTime"])
    trades["date"] = trades["EntryTime"].dt.strftime("%Y-%m-%d")
    trades["direction"] = trades["Size"].apply(lambda x: "B" if x > 0 else "S")
    trades["entry_time"] = trades["EntryTime"].dt.strftime("%H:%M")
    trades["entry_price"] = trades["EntryPrice"].round(0).astype(int)
    trades["exit_time"] = trades["ExitTime"].dt.strftime("%H:%M")
    trades["exit_price"] = trades["ExitPrice"].round(0).astype(int)
    trades["pnl"] = trades["PnL"].round(0).astype(int)
    return trades[["date", "direction", "entry_time", "entry_price",
                    "exit_time", "exit_price", "pnl"]]


def compute_pf(pnl_series):
    wins = pnl_series[pnl_series > 0].sum()
    losses = abs(pnl_series[pnl_series < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0
    return round(wins / losses, 2)


def main():
    live = load_live_reversal()
    print(f"Live reversal trades: {len(live)}")
    print(f"Date range: {live['date'].min()} ~ {live['date'].max()}")

    start = live["date"].min()
    end = live["date"].max()

    print(f"\nRunning backtest {start} ~ {end}...")
    bt_trades = run_backtest_trades(start, end)
    print(f"Backtest trades: {len(bt_trades)}")

    # ── 1. Overall stats comparison ──
    print("\n" + "=" * 72)
    print("1. OVERALL STATISTICS")
    print("=" * 72)
    header = f"  {'':>12}  {'N':>5}  {'Win%':>7}  {'Avg PnL':>8}  {'Total':>9}  {'PF':>6}"
    sep = f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}"
    print(header)
    print(sep)

    for label, df in [("Live", live), ("Backtest", bt_trades)]:
        pnl = df["pnl"].dropna()
        n = len(pnl)
        if n == 0:
            print(f"  {label:>12}  {0:>5}")
            continue
        win_pct = (pnl > 0).sum() / n * 100
        avg = pnl.mean()
        total = pnl.sum()
        pf = compute_pf(pnl)
        print(f"  {label:>12}  {n:>5}  {win_pct:>6.1f}%  {avg:>8.1f}  {total:>9}  {pf:>6.2f}")

    # ── 2. Date-level matching ──
    print("\n" + "=" * 72)
    print("2. DATE-LEVEL MATCHING")
    print("=" * 72)

    live_dates = set(live["date"])
    bt_dates = set(bt_trades["date"])
    both = live_dates & bt_dates
    live_only = live_dates - bt_dates
    bt_only = bt_dates - live_dates

    print(f"  Live trade dates:     {len(live_dates)}")
    print(f"  Backtest trade dates: {len(bt_dates)}")
    print(f"  Both:                 {len(both)}")
    print(f"  Live only:            {len(live_only)}")
    print(f"  Backtest only:        {len(bt_only)}")

    if live_dates:
        overlap_pct = len(both) / len(live_dates) * 100
        print(f"  Overlap rate (vs live): {overlap_pct:.1f}%")

    # ── 3. Direction agreement on shared dates ──
    print("\n" + "=" * 72)
    print("3. DIRECTION AGREEMENT (shared dates)")
    print("=" * 72)

    agree = 0
    disagree = 0
    disagree_list = []
    for d in sorted(both):
        live_row = live[live["date"] == d].iloc[0]
        bt_row = bt_trades[bt_trades["date"] == d].iloc[0]
        if live_row["direction"] == bt_row["direction"]:
            agree += 1
        else:
            disagree += 1
            disagree_list.append((d, live_row["direction"], bt_row["direction"]))

    total_shared = agree + disagree
    if total_shared > 0:
        print(f"  Agree:    {agree} ({agree / total_shared * 100:.1f}%)")
        print(f"  Disagree: {disagree} ({disagree / total_shared * 100:.1f}%)")
    if disagree_list:
        print(f"\n  Direction disagreements:")
        for d, ld, bd in disagree_list:
            print(f"    {d}: Live={ld}, Backtest={bd}")

    # ── 4. PnL comparison on shared dates ──
    print("\n" + "=" * 72)
    print("4. PnL COMPARISON (shared dates, same direction)")
    print("=" * 72)

    pnl_diffs = []
    for d in sorted(both):
        live_row = live[live["date"] == d].iloc[0]
        bt_row = bt_trades[bt_trades["date"] == d].iloc[0]
        if live_row["direction"] != bt_row["direction"]:
            continue
        lp = live_row["pnl"]
        bp = bt_row["pnl"]
        if lp is None or pd.isna(lp):
            continue
        diff = lp - bp
        pnl_diffs.append({
            "date": d,
            "live_dir": live_row["direction"],
            "live_entry": f"{live_row['entry_time']}@{live_row['entry_price']}",
            "bt_entry": f"{bt_row['entry_time']}@{bt_row['entry_price']}",
            "live_exit": f"{live_row.get('exit_time', '')}@{live_row['exit_price']}",
            "bt_exit": f"{bt_row['exit_time']}@{bt_row['exit_price']}",
            "live_pnl": lp,
            "bt_pnl": bp,
            "diff": diff,
        })

    if pnl_diffs:
        df_diff = pd.DataFrame(pnl_diffs)
        print(f"  Matched trades (same date + direction): {len(df_diff)}")
        print(f"  Mean diff (live - bt): {df_diff['diff'].mean():+.1f}")
        print(f"  Median diff:           {df_diff['diff'].median():+.1f}")
        print(f"  Std diff:              {df_diff['diff'].std():.1f}")

        live_better = (df_diff["diff"] > 0).sum()
        bt_better = (df_diff["diff"] < 0).sum()
        same = (df_diff["diff"] == 0).sum()
        print(f"  Live better: {live_better}, Backtest better: {bt_better}, Same: {same}")

        # Top 5 biggest diffs
        print(f"\n  Top 10 biggest discrepancies:")
        print(f"  {'Date':>12}  {'Dir':>3}  {'Live Entry':>14}  {'BT Entry':>14}  "
              f"{'Live PnL':>9}  {'BT PnL':>8}  {'Diff':>7}")
        print(f"  {'-'*12}  {'-'*3}  {'-'*14}  {'-'*14}  {'-'*9}  {'-'*8}  {'-'*7}")
        top = df_diff.reindex(df_diff["diff"].abs().sort_values(ascending=False).index).head(10)
        for _, r in top.iterrows():
            print(f"  {r['date']:>12}  {r['live_dir']:>3}  {r['live_entry']:>14}  "
                  f"{r['bt_entry']:>14}  {r['live_pnl']:>+9}  {r['bt_pnl']:>+8}  "
                  f"{r['diff']:>+7}")

    # ── 5. Live-only trades analysis ──
    print("\n" + "=" * 72)
    print("5. LIVE-ONLY TRADES (no backtest match)")
    print("=" * 72)
    live_only_trades = live[live["date"].isin(live_only)].copy()
    if len(live_only_trades) > 0:
        pnl = live_only_trades["pnl"].dropna()
        wins = (pnl > 0).sum()
        print(f"  Count: {len(live_only_trades)}")
        if len(pnl) > 0:
            print(f"  Win%: {wins / len(pnl) * 100:.1f}%")
            print(f"  Total PnL: {pnl.sum():+d}")
            print(f"  Avg PnL: {pnl.mean():+.1f}")
        print(f"\n  Details:")
        print(f"  {'Date':>12}  {'Dir':>3}  {'Entry':>14}  {'Exit':>14}  {'PnL':>7}  {'Exit Strat'}")
        print(f"  {'-'*12}  {'-'*3}  {'-'*14}  {'-'*14}  {'-'*7}  {'-'*20}")
        for _, r in live_only_trades.iterrows():
            print(f"  {r['date']:>12}  {r['direction']:>3}  "
                  f"{r['entry_time']}@{r['entry_price']:>14}  "
                  f"{r.get('exit_time', '')}@{r['exit_price']:>14}  "
                  f"{r['pnl']:>+7}  {r.get('exit_strategy', '')}")
    else:
        print("  None")

    # ── 6. Backtest-only trades ──
    print("\n" + "=" * 72)
    print("6. BACKTEST-ONLY TRADES (no live match)")
    print("=" * 72)
    bt_only_trades = bt_trades[bt_trades["date"].isin(bt_only)].copy()
    if len(bt_only_trades) > 0:
        pnl = bt_only_trades["pnl"]
        wins = (pnl > 0).sum()
        print(f"  Count: {len(bt_only_trades)}")
        print(f"  Win%: {wins / len(pnl) * 100:.1f}%")
        print(f"  Total PnL: {pnl.sum():+d}")
        print(f"\n  Details:")
        print(f"  {'Date':>12}  {'Dir':>3}  {'Entry':>14}  {'Exit':>14}  {'PnL':>7}")
        print(f"  {'-'*12}  {'-'*3}  {'-'*14}  {'-'*14}  {'-'*7}")
        for _, r in bt_only_trades.iterrows():
            print(f"  {r['date']:>12}  {r['direction']:>3}  "
                  f"{r['entry_time']}@{r['entry_price']:>6}  "
                  f"{r['exit_time']}@{r['exit_price']:>6}  "
                  f"{r['pnl']:>+7}")
    else:
        print("  None")

    # ── 7. Monthly summary ──
    print("\n" + "=" * 72)
    print("7. MONTHLY SUMMARY")
    print("=" * 72)

    live["month"] = live["date"].str[:7]
    bt_trades["month"] = bt_trades["date"].str[:7]
    all_months = sorted(set(live["month"]) | set(bt_trades["month"]))

    print(f"  {'Month':>8}  {'L_N':>4}  {'L_Win%':>7}  {'L_PnL':>8}  "
          f"{'B_N':>4}  {'B_Win%':>7}  {'B_PnL':>8}")
    print(f"  {'-'*8}  {'-'*4}  {'-'*7}  {'-'*8}  {'-'*4}  {'-'*7}  {'-'*8}")

    for m in all_months:
        lm = live[live["month"] == m]
        bm = bt_trades[bt_trades["month"] == m]
        lp = lm["pnl"].dropna()
        bp = bm["pnl"]

        ln = len(lp)
        lw = f"{(lp > 0).sum() / ln * 100:.0f}%" if ln > 0 else "—"
        lt = f"{lp.sum():+d}" if ln > 0 else "—"

        bn = len(bp)
        bw = f"{(bp > 0).sum() / bn * 100:.0f}%" if bn > 0 else "—"
        bt_sum = f"{bp.sum():+d}" if bn > 0 else "—"

        print(f"  {m:>8}  {ln:>4}  {lw:>7}  {lt:>8}  {bn:>4}  {bw:>7}  {bt_sum:>8}")

    print()


if __name__ == "__main__":
    main()

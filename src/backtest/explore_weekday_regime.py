#!/usr/bin/env python3
"""探索：週四/五 + regime 指標交叉分析。

如果 ER > 閾值 且 range% > 閾值 的週四/五，EstHL 能不能做？

Usage:
    uv run python src/backtest/explore_weekday_regime.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl
from src.backtest.strategy_health import compute_daily_regime
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy


def main():
    print("Computing regime metrics...", flush=True)
    regime = compute_daily_regime()

    # Run EstHL WITHOUT skip_thursday/friday to get all trades
    print("\nRunning EstHL (no weekday skip)...", flush=True)
    df = load_data_for_orb_est_hl()
    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    trades = bt.run(
        sl_ema_fraction=0.25,
        long_only=True,
        vwap_days=2,
        skip_thursday=False,
        skip_friday=False,
    )["_trades"].copy()

    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100
    trades["win"] = (trades["PnL"] > 0).astype(int)
    trades["weekday"] = pd.to_datetime(trades["EntryTime"]).dt.weekday
    trades["weekday_name"] = pd.to_datetime(trades["EntryTime"]).dt.day_name()

    # Join with regime
    merged = trades.join(regime[["range_pct", "ema_range_pct_20", "efficiency_ratio",
                                  "ema_er_20", "swing_count"]], on="entry_date")

    print(f"\nTotal trades (no skip): {len(merged)}")

    # ── 1. 各星期基本績效 ──
    print("\n" + "=" * 72)
    print("1. 各星期 EstHL 績效（無 weekday 濾網）")
    print("=" * 72)
    print(f"  {'星期':<8}  {'n':>5}  {'WR':>7}  {'avg%':>8}  {'total%':>9}  {'pts':>8}")
    print(f"  {'-'*8}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*8}")
    wd_names = {0: "週一", 1: "週二", 2: "週三", 3: "週四", 4: "週五"}
    for wd in range(5):
        t = merged[merged["weekday"] == wd]
        if len(t) == 0:
            continue
        wr = t["win"].mean() * 100
        avg_pct = t["pnl_pct"].mean()
        total_pct = t["pnl_pct"].sum()
        pts = t["PnL"].sum()
        print(f"  {wd_names[wd]:<8}  {len(t):>5}  {wr:>6.1f}%  {avg_pct:>+7.3f}%"
              f"  {total_pct:>+8.2f}%  {pts:>+8.0f}")

    # ── 2. 週四/五: regime 好 vs 差 ──
    print("\n" + "=" * 72)
    print("2. 週四/五：regime 好 vs 差")
    print("=" * 72)

    thu_fri = merged[merged["weekday"].isin([3, 4])].copy()
    print(f"\n  週四/五共 {len(thu_fri)} 筆")

    # 用當日 range_pct 和 ER（不是 EMA，因為是事後分析）
    range_thresh = 0.74
    er_thresh = 0.033

    for label, er_t, range_t in [
        ("ER>0.033 且 Range%>0.74%", er_thresh, range_thresh),
        ("ER>0.065 且 Range%>1.0%", 0.065, 1.0),
        ("ER>0.10 且 Range%>1.0%", 0.10, 1.0),
    ]:
        good = thu_fri[
            (thu_fri["efficiency_ratio"] > er_t) &
            (thu_fri["range_pct"] > range_t)
        ]
        bad = thu_fri[
            ~((thu_fri["efficiency_ratio"] > er_t) &
              (thu_fri["range_pct"] > range_t))
        ]
        print(f"\n  [{label}]")
        for name, subset in [("符合", good), ("不符合", bad)]:
            if len(subset) == 0:
                print(f"    {name}: 0 筆")
                continue
            wr = subset["win"].mean() * 100
            avg = subset["pnl_pct"].mean()
            pts = subset["PnL"].sum()
            print(f"    {name}: {len(subset):>3} 筆  WR {wr:>5.1f}%  "
                  f"avg {avg:>+.3f}%  pts {pts:>+.0f}")

    # ── 3. 用前一日 EMA 做濾網（可實際使用，無 lookahead）──
    print("\n" + "=" * 72)
    print("3. 週四/五：用前日 EMA 做濾網（無 lookahead）")
    print("=" * 72)

    # shift regime EMA by 1 day
    regime_shifted = regime[["ema_range_pct_20", "ema_er_20"]].shift(1)
    regime_shifted.columns = ["prev_ema_range", "prev_ema_er"]
    thu_fri2 = thu_fri.join(regime_shifted, on="entry_date")

    for label, er_t, range_t in [
        ("前日 EMA: ER>0.033 且 Range%>0.74%", er_thresh, range_thresh),
        ("前日 EMA: ER>0.050 且 Range%>1.0%", 0.050, 1.0),
        ("前日 EMA: ER>0.065 且 Range%>1.0%", 0.065, 1.0),
    ]:
        good = thu_fri2[
            (thu_fri2["prev_ema_er"] > er_t) &
            (thu_fri2["prev_ema_range"] > range_t)
        ]
        bad = thu_fri2[
            ~((thu_fri2["prev_ema_er"] > er_t) &
              (thu_fri2["prev_ema_range"] > range_t))
        ]
        print(f"\n  [{label}]")
        for name, subset in [("符合", good), ("不符合", bad)]:
            if len(subset) == 0:
                print(f"    {name}: 0 筆")
                continue
            wr = subset["win"].mean() * 100
            avg = subset["pnl_pct"].mean()
            pts = subset["PnL"].sum()
            print(f"    {name}: {len(subset):>3} 筆  WR {wr:>5.1f}%  "
                  f"avg {avg:>+.3f}%  pts {pts:>+.0f}")

    # ── 4. 各星期 × regime 交叉 ──
    print("\n" + "=" * 72)
    print("4. 所有星期 × regime 指標交叉（用前日 EMA，無 lookahead）")
    print("=" * 72)

    all_merged = merged.join(regime_shifted, on="entry_date")

    print(f"\n  [前日 EMA: ER>0.033 且 Range%>0.74%]")
    print(f"  {'星期':<8}  {'n_good':>7}  {'WR_good':>8}  {'avg%_good':>10}  "
          f"{'n_bad':>6}  {'WR_bad':>7}  {'avg%_bad':>9}")
    print(f"  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*9}")

    for wd in range(5):
        t = all_merged[all_merged["weekday"] == wd]
        good = t[(t["prev_ema_er"] > 0.033) & (t["prev_ema_range"] > 0.74)]
        bad = t[~((t["prev_ema_er"] > 0.033) & (t["prev_ema_range"] > 0.74))]
        g_wr = good["win"].mean() * 100 if len(good) > 0 else 0
        g_avg = good["pnl_pct"].mean() if len(good) > 0 else 0
        b_wr = bad["win"].mean() * 100 if len(bad) > 0 else 0
        b_avg = bad["pnl_pct"].mean() if len(bad) > 0 else 0
        print(f"  {wd_names[wd]:<8}  {len(good):>7}  {g_wr:>7.1f}%  {g_avg:>+9.3f}%"
              f"  {len(bad):>6}  {b_wr:>6.1f}%  {b_avg:>+8.3f}%")

    # ── 5. 最終比較：不同方案 ──
    print("\n" + "=" * 72)
    print("5. 方案比較")
    print("=" * 72)

    all_with_ema = merged.join(regime_shifted, on="entry_date")

    scenarios = {
        "A: 現行（skip Thu+Fri）": all_with_ema[~all_with_ema["weekday"].isin([3, 4])],
        "B: 全做（無濾網）": all_with_ema,
        "C: regime 濾（ER>0.033 & Range%>0.74%，全星期）": all_with_ema[
            (all_with_ema["prev_ema_er"] > 0.033) &
            (all_with_ema["prev_ema_range"] > 0.74)
        ],
        "D: skip Thu/Fri + regime 濾": all_with_ema[
            (~all_with_ema["weekday"].isin([3, 4])) &
            (all_with_ema["prev_ema_er"] > 0.033) &
            (all_with_ema["prev_ema_range"] > 0.74)
        ],
        "E: regime 濾 + 只 skip Fri": all_with_ema[
            (~all_with_ema["weekday"].isin([4])) &
            (all_with_ema["prev_ema_er"] > 0.033) &
            (all_with_ema["prev_ema_range"] > 0.74)
        ],
    }

    print(f"\n  {'方案':<45}  {'n':>5}  {'WR':>7}  {'avg%':>8}  {'total%':>9}  {'pts':>8}  {'PF':>6}")
    print(f"  {'-'*45}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*8}  {'-'*6}")
    for name, subset in scenarios.items():
        subset = subset.dropna(subset=["prev_ema_er", "prev_ema_range"])
        if len(subset) == 0:
            print(f"  {name:<45}  {'0':>5}")
            continue
        wr = subset["win"].mean() * 100
        avg = subset["pnl_pct"].mean()
        total = subset["pnl_pct"].sum()
        pts = subset["PnL"].sum()
        wins_pnl = subset.loc[subset["PnL"] > 0, "PnL"].sum()
        losses_pnl = abs(subset.loc[subset["PnL"] < 0, "PnL"].sum())
        pf = wins_pnl / losses_pnl if losses_pnl > 0 else np.inf
        print(f"  {name:<45}  {len(subset):>5}  {wr:>6.1f}%  {avg:>+7.3f}%"
              f"  {total:>+8.2f}%  {pts:>+8.0f}  {pf:>6.2f}")


if __name__ == "__main__":
    main()

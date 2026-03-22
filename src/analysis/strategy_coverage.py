#!/usr/bin/env python3
"""
策略覆蓋分析 — 潛力日 × 現有策略交叉

比較 EstHL / Reversal / ORBLong 對波動潛力日的覆蓋情況，
找出未被捕捉的高波動日及其原因。

使用方式：
    uv run python src/analysis/strategy_coverage.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analysis.volatility_capture import build_analysis
from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    load_data_with_night_ma,
)
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy


def _run_strategy(name, df, cls, params=None):
    """Run a strategy and return trades with standardized columns."""
    bt = Backtest(df, cls, cash=200_000, commission=0.0, trade_on_close=True)
    trades = bt.run(**(params or {}))["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100
    trades["win"] = (trades["PnL"] > 0).astype(int)
    trades["strategy"] = name
    return trades


def load_all_trades() -> dict[str, pd.DataFrame]:
    """Run all three strategies and return {name: trades_df}."""
    print("Loading data & running strategies...", flush=True)

    df_esthl = load_data_for_orb_est_hl()
    esthl = _run_strategy("EstHL", df_esthl, ORBWithEstHLExitStrategy, dict(
        sl_ema_fraction=0.25, long_only=True, bigcost_days=2,
        skip_thursday=True, skip_friday=True,
    ))
    print(f"  EstHL: {len(esthl)} trades")

    df_rev = load_data_for_reversal()
    reversal = _run_strategy("Reversal", df_rev, ReversalStrategy)
    print(f"  Reversal: {len(reversal)} trades")

    df_orb = load_data_with_night_ma(trend_ma_days=10, estimate_hl=True)
    orblong = _run_strategy("ORBLong", df_orb, ORBLongStrategy, dict(
        tp_or_multiplier=1.5, sl_pct=0.004, long_only=1,
    ))
    print(f"  ORBLong: {len(orblong)} trades")

    return {"EstHL": esthl, "Reversal": reversal, "ORBLong": orblong}


def main():
    # 1. Build volatility potential days
    vol_df = build_analysis()
    vol_df["trade_date"] = pd.to_datetime(vol_df["trade_date"]).dt.normalize()
    pot = vol_df[vol_df["is_potential_p67"]].copy()

    # 2. Run strategies
    all_trades = load_all_trades()

    # 3. Build coverage matrix: trade_date × strategy → has_trade / pnl
    trade_dates_by_strat = {}
    pnl_by_strat = {}
    for name, trades in all_trades.items():
        td = trades.groupby("entry_date").agg(
            pnl=("PnL", "sum"),
            pnl_pct=("pnl_pct", "sum"),
            win=("win", "max"),
            n_trades=("PnL", "count"),
        )
        trade_dates_by_strat[name] = set(td.index)
        pnl_by_strat[name] = td

    # 4. Tag potential days with coverage
    strat_names = ["EstHL", "Reversal", "ORBLong"]
    for name in strat_names:
        pot[f"has_{name}"] = pot["trade_date"].isin(trade_dates_by_strat[name])
        pnl_map = pnl_by_strat[name]["pnl"].to_dict()
        pot[f"pnl_{name}"] = pot["trade_date"].map(pnl_map).fillna(0)

    pot["n_strategies"] = sum(pot[f"has_{name}"].astype(int) for name in strat_names)
    pot["any_strategy"] = pot["n_strategies"] > 0

    # ── Reports ──

    print("\n" + "=" * 70)
    print("策略覆蓋分析 × 波動潛力日")
    print("=" * 70)

    # Overall coverage
    n_pot = len(pot)
    n_covered = pot["any_strategy"].sum()
    n_uncovered = n_pot - n_covered
    print(f"\n### 整體覆蓋率")
    print(f"潛力日（P67）: {n_pot} 日")
    print(f"至少一策略進場: {n_covered} 日 ({n_covered/n_pot*100:.0f}%)")
    print(f"完全未覆蓋: {n_uncovered} 日 ({n_uncovered/n_pot*100:.0f}%)")

    # Per-strategy coverage
    print(f"\n### 各策略覆蓋率（對潛力日）")
    print(f"| 策略 | 覆蓋日 | 佔比 | 潛力日勝率 | 潛力日均PnL | 非潛力日均PnL |")
    print(f"|------|-------:|-----:|-----------:|------------|-------------|")
    for name in strat_names:
        covered = pot[pot[f"has_{name}"]]
        n_cov = len(covered)
        pct = n_cov / n_pot * 100

        # 潛力日績效
        pot_trades = all_trades[name][all_trades[name]["entry_date"].isin(pot["trade_date"])]
        non_pot_trades = all_trades[name][~all_trades[name]["entry_date"].isin(pot["trade_date"])]

        pot_wr = pot_trades["win"].mean() * 100 if len(pot_trades) > 0 else 0
        pot_avg = pot_trades["PnL"].mean() if len(pot_trades) > 0 else 0
        non_avg = non_pot_trades["PnL"].mean() if len(non_pot_trades) > 0 else 0

        print(f"| {name:<8} | {n_cov:>5} | {pct:>4.0f}% | {pot_wr:>9.0f}% | {pot_avg:>+10.0f} pts | {non_avg:>+11.0f} pts |")

    # Coverage by day type
    print(f"\n### 日類型 × 覆蓋率")
    print(f"| 類型 | 總數 | 覆蓋 | 覆蓋率 | EstHL | Reversal | ORBLong |")
    print(f"|------|-----:|-----:|-------:|------:|---------:|--------:|")
    for t in ["EarlyTrend", "LateTrend", "Afternoon", "Spread"]:
        tdf = pot[pot["day_type"] == t]
        n = len(tdf)
        if n == 0:
            continue
        n_cov = tdf["any_strategy"].sum()
        e = tdf["has_EstHL"].sum()
        r = tdf["has_Reversal"].sum()
        o = tdf["has_ORBLong"].sum()
        print(f"| {t:<11} | {n:>4} | {n_cov:>4} | {n_cov/n*100:>5.0f}% "
              f"| {e:>5} | {r:>8} | {o:>7} |")

    # Overlap analysis
    print(f"\n### 策略重疊")
    print(f"| 重疊數 | 日數 | 佔比 | 平均range% | 平均總PnL |")
    print(f"|--------|-----:|-----:|-----------:|----------:|")
    for n_s in range(4):
        sub = pot[pot["n_strategies"] == n_s]
        if len(sub) == 0:
            continue
        avg_r = sub["range_pct"].mean()
        total_pnl = sum(sub[f"pnl_{name}"].sum() for name in strat_names)
        avg_pnl = total_pnl / len(sub) if len(sub) > 0 else 0
        label = f"{n_s} 策略" if n_s > 0 else "無策略"
        print(f"| {label} | {len(sub):>4} | {len(sub)/n_pot*100:>4.0f}% | {avg_r:>9.2f}% | {avg_pnl:>+8.0f} |")

    # Uncovered days detail
    uncovered = pot[~pot["any_strategy"]].sort_values("range_pct", ascending=False)
    print(f"\n### 未覆蓋潛力日 TOP 20（依 range% 排序）")
    print(f"| 日期       | range% | 方向 | 類型        | 星期 |")
    print(f"|------------|-------:|------|-------------|------|")
    wd_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    for _, r in uncovered.head(20).iterrows():
        d = str(r["trade_date"])[:10]
        wd = wd_names[pd.Timestamp(r["trade_date"]).dayofweek]
        print(f"| {d} | {r['range_pct']:>5.2f}% | {r['direction']:<4} "
              f"| {r['day_type']:<11} | {wd} |")

    # Year × coverage
    print(f"\n### 年度覆蓋率")
    print(f"| 年度 | 潛力日 | 覆蓋 | 覆蓋率 | 未覆蓋 |")
    print(f"|------|-------:|-----:|-------:|-------:|")
    for y in sorted(pot["year"].unique()):
        ydf = pot[pot["year"] == y]
        n = len(ydf)
        n_c = ydf["any_strategy"].sum()
        print(f"| {y} | {n:>5} | {n_c:>4} | {n_c/n*100:>5.0f}% | {n - n_c:>5} |")

    # Weekday analysis for uncovered
    print(f"\n### 未覆蓋日的星期分佈")
    print(f"| 星期 | 未覆蓋 | 佔未覆蓋% | 主因 |")
    print(f"|------|-------:|----------:|------|")
    uncov_wd = pd.Timestamp("2021-01-01")  # dummy
    uncovered_wds = pd.to_datetime(uncovered["trade_date"]).dt.dayofweek.value_counts().sort_index()
    for wd in range(5):
        n = uncovered_wds.get(wd, 0)
        pct = n / len(uncovered) * 100 if len(uncovered) > 0 else 0
        reason = ""
        if wd in (3, 4):
            reason = "EstHL skip_thu/fri"
        print(f"| {wd_names[wd]} | {n:>5} | {pct:>8.0f}% | {reason} |")


if __name__ == "__main__":
    main()

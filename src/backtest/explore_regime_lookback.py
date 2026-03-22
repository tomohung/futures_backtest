#!/usr/bin/env python3
"""探索：不同 lookback window 對 EstHL 的預警效果

問題：要看過去多少天的 range_pct 分布，才能提前預警 EstHL 績效衰退？

分析維度：
  - Lookback window: 20, 40, 60 天
  - 指標：range_pct 低於閾值的天數比例
  - 閾值候選：0.74%, 0.80%, 0.90%, 1.00%
  - 對照：該區間內 EstHL 交易的勝率、平均損益%

Usage:
    uv run python src/backtest/explore_regime_lookback.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.explore_regime import load_daily_ohlcv
from src.backtest.strategy_health import compute_1m_metrics, run_esthl


def main():
    # ── 1. 準備 regime 資料 ──
    print("=== Regime Lookback 預警探索 ===\n")

    daily = load_daily_ohlcv()
    daily["range_pct"] = (daily["high"] - daily["low"]) / daily["open"] * 100

    metrics_1m = compute_1m_metrics()
    daily = daily.join(metrics_1m)

    # EMA(20) for reference
    daily["ema_range_pct_20"] = daily["range_pct"].ewm(span=20, adjust=False).mean()

    # ── 2. 跑 EstHL 取得交易 ──
    trades = run_esthl()
    trades = trades.set_index("entry_date")

    # ── 3. 分析不同 lookback × threshold 組合 ──
    lookbacks = [20, 40, 60]
    thresholds = [0.74, 0.80, 0.90, 1.00]

    # 預計算每天往前 N 天低於 threshold 的比例
    range_pct_values = daily["range_pct"]

    print("=" * 90)
    print("Section 1: 不同 lookback × threshold 的預警效果")
    print("  「低於比例」= 過去 N 天中 range_pct < threshold 的天數 / N")
    print("  對每筆 EstHL 交易，取進場日的「低於比例」，依 50% 分組看績效差異")
    print("=" * 90)

    for lb in lookbacks:
        print(f"\n### Lookback = {lb} 天")
        print(f"{'threshold':>10} | {'split':>6} | {'trades':>6} | {'WR':>6} | "
              f"{'avg_pnl%':>9} | {'total_pnl%':>10} | {'avg_pts':>8}")
        print("-" * 80)

        for thr in thresholds:
            # 計算每天的 "低於比例"
            below = (range_pct_values < thr).astype(float)
            below_ratio = below.rolling(lb, min_periods=lb).mean()

            # 合併到交易
            merged = trades.join(below_ratio.rename("below_ratio"), how="inner")
            merged = merged.dropna(subset=["below_ratio"])

            if len(merged) < 10:
                print(f"{thr:>10.2f}% | {'N/A':>6} | {len(merged):>6} | — ")
                continue

            # 依 50% 分成高低兩組
            median_ratio = merged["below_ratio"].median()
            low_grp = merged[merged["below_ratio"] <= median_ratio]
            high_grp = merged[merged["below_ratio"] > median_ratio]

            for label, grp in [("low≤", low_grp), ("high>", high_grp)]:
                if len(grp) == 0:
                    continue
                wr = grp["win"].mean() * 100
                avg_pnl = grp["pnl_pct"].mean()
                total_pnl = grp["pnl_pct"].sum()
                avg_pts = grp["PnL"].mean()
                print(f"{thr:>9.2f}% | {label + f'{median_ratio:.0%}':>6} | "
                      f"{len(grp):>6} | {wr:>5.1f}% | {avg_pnl:>+8.3f}% | "
                      f"{total_pnl:>+9.2f}% | {avg_pts:>+7.0f}")
        print()

    # ── 4. 更細緻：不同「低於比例」區間的績效 ──
    print("\n" + "=" * 90)
    print("Section 2: 低於比例分桶（range_pct < 0.90%）× 各 lookback 的績效")
    print("  將「低於比例」切成 4 桶：0-25%, 25-50%, 50-75%, 75-100%")
    print("=" * 90)

    thr_focus = 0.90  # 用 0.90% 為中間閾值
    bins = [0.0, 0.25, 0.50, 0.75, 1.01]
    bin_labels = ["0-25%", "25-50%", "50-75%", "75-100%"]

    for lb in lookbacks:
        below = (range_pct_values < thr_focus).astype(float)
        below_ratio = below.rolling(lb, min_periods=lb).mean()

        merged = trades.join(below_ratio.rename("below_ratio"), how="inner")
        merged = merged.dropna(subset=["below_ratio"])

        merged["bucket"] = pd.cut(merged["below_ratio"], bins=bins, labels=bin_labels,
                                  include_lowest=True)

        print(f"\n### Lookback = {lb} 天, threshold = {thr_focus:.2f}%")
        print(f"{'bucket':>10} | {'trades':>6} | {'WR':>6} | {'avg_pnl%':>9} | "
              f"{'total_pnl%':>10} | {'avg_pts':>8} | {'ratio_range':>15}")
        print("-" * 80)

        for bucket in bin_labels:
            grp = merged[merged["bucket"] == bucket]
            if len(grp) == 0:
                print(f"{bucket:>10} | {0:>6} | — ")
                continue
            wr = grp["win"].mean() * 100
            avg_pnl = grp["pnl_pct"].mean()
            total_pnl = grp["pnl_pct"].sum()
            avg_pts = grp["PnL"].mean()
            r_min = grp["below_ratio"].min()
            r_max = grp["below_ratio"].max()
            print(f"{bucket:>10} | {len(grp):>6} | {wr:>5.1f}% | {avg_pnl:>+8.3f}% | "
                  f"{total_pnl:>+9.2f}% | {avg_pts:>+7.0f} | {r_min:.0%}~{r_max:.0%}")

    # ── 5. 實際過濾模擬：暫停規則的年度績效 ──
    print("\n" + "=" * 90)
    print("Section 3: 暫停規則模擬 — 若「低於比例 > X%」就不做")
    print("  比較不同 lookback × threshold × pause_ratio 的年度績效")
    print("=" * 90)

    # 候選暫停規則
    pause_rules = [
        (20, 0.90, 0.50),   # 過去 20 天，超過 50% 的天 range_pct < 0.90%
        (40, 0.90, 0.50),
        (60, 0.90, 0.50),
        (20, 0.80, 0.50),
        (40, 0.80, 0.50),
        (40, 0.90, 0.40),
        (40, 0.90, 0.60),
        (40, 1.00, 0.60),
    ]

    # Baseline (no filter)
    trades_with_year = trades.copy()
    trades_with_year["year"] = trades_with_year.index.year

    print(f"\n{'rule':>25} | ", end="")
    years = sorted(trades_with_year["year"].unique())
    for y in years:
        print(f" {y} ", end="|")
    print(f" {'TOTAL':>7} | {'trades':>6} | {'filtered':>8}")
    print("-" * 120)

    # Baseline
    print(f"{'baseline (no filter)':>25} | ", end="")
    total_baseline = 0
    for y in years:
        yr_pnl = trades_with_year[trades_with_year["year"] == y]["PnL"].sum()
        total_baseline += yr_pnl
        print(f"{yr_pnl:>+5.0f} ", end="|")
    print(f" {total_baseline:>+7.0f} | {len(trades_with_year):>6} | {'0':>8}")

    for lb, thr, pause_ratio in pause_rules:
        below = (range_pct_values < thr).astype(float)
        below_r = below.rolling(lb, min_periods=lb).mean()

        merged = trades.join(below_r.rename("below_ratio"), how="inner")
        merged = merged.dropna(subset=["below_ratio"])

        # 過濾：只在 below_ratio <= pause_ratio 時交易
        active = merged[merged["below_ratio"] <= pause_ratio]
        filtered_out = merged[merged["below_ratio"] > pause_ratio]

        active["year"] = active.index.year
        filtered_out["year"] = filtered_out.index.year

        rule_str = f"lb{lb}_thr{thr:.2f}_p{pause_ratio:.0%}"
        print(f"{rule_str:>25} | ", end="")
        total = 0
        for y in years:
            yr_pnl = active[active["year"] == y]["PnL"].sum() if y in active.index.year else 0
            total += yr_pnl
            print(f"{yr_pnl:>+5.0f} ", end="|")
        n_filtered = len(filtered_out)
        print(f" {total:>+7.0f} | {len(active):>6} | {n_filtered:>8}")

        # 被過濾掉的交易績效
        if n_filtered > 0:
            f_wr = filtered_out["win"].mean() * 100
            f_avg = filtered_out["PnL"].mean()
            f_total = filtered_out["PnL"].sum()
            print(f"{'  (filtered trades)':>25} | "
                  f"WR={f_wr:.0f}%, avg={f_avg:+.0f}pts, total={f_total:+.0f}pts")

    # ── 6. EMA(20) 連續低於閾值天數 ──
    print("\n" + "=" * 90)
    print("Section 4: EMA(20) 連續低於閾值的天數 vs EstHL 績效")
    print("  計算進場日前 EMA(20) 已連續低於 threshold 多少天")
    print("=" * 90)

    ema_thresholds = [0.74, 0.80, 0.90, 1.00]

    for ema_thr in ema_thresholds:
        # 計算連續低於閾值天數
        below_ema = (daily["ema_range_pct_20"] < ema_thr).astype(int)
        consec = below_ema.copy()
        for i in range(1, len(consec)):
            if consec.iloc[i] == 1:
                consec.iloc[i] = consec.iloc[i-1] + 1

        merged = trades.join(consec.rename("consec_below"), how="inner")
        merged = merged.dropna(subset=["consec_below"])

        # 分桶
        cut_bins = [0, 0.5, 5, 10, 20, 999]
        cut_labels = ["0天", "1-5天", "6-10天", "11-20天", ">20天"]
        merged["consec_bucket"] = pd.cut(merged["consec_below"], bins=cut_bins,
                                         labels=cut_labels, include_lowest=True)

        print(f"\n### EMA(20) range_pct < {ema_thr:.2f}% 連續天數")
        print(f"{'bucket':>10} | {'trades':>6} | {'WR':>6} | {'avg_pnl%':>9} | "
              f"{'avg_pts':>8} | {'total_pts':>9}")
        print("-" * 70)

        for bucket in cut_labels:
            grp = merged[merged["consec_bucket"] == bucket]
            if len(grp) == 0:
                print(f"{bucket:>10} | {0:>6} | — ")
                continue
            wr = grp["win"].mean() * 100
            avg_pnl = grp["pnl_pct"].mean()
            avg_pts = grp["PnL"].mean()
            total_pts = grp["PnL"].sum()
            print(f"{bucket:>10} | {len(grp):>6} | {wr:>5.1f}% | {avg_pnl:>+8.3f}% | "
                  f"{avg_pts:>+7.0f} | {total_pts:>+8.0f}")


if __name__ == "__main__":
    main()

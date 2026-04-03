#!/usr/bin/env python3
"""H056 Phase 1: Night Session 30m MACD + SMA → 日盤前四根 30m K 方向預測.

目標：夜盤收盤時的 MACD 狀態與 SMA 排列，能否預測日盤前四根
30m K（08:45~10:45）的方向與振幅。

Usage:
    uv run python research/active/H056-night-macd-regime/explore.py
"""

import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats as sp_stats

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H056-night-macd-regime/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COLOR_UP = "#d62728"
COLOR_DOWN = "#2ca02c"


# ============================================================
# 1. 資料載入
# ============================================================

def load_1m():
    """載入 TX 全部 1m 資料。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    return df


def assign_trading_date(ts):
    """夜盤 15:00~ 歸下一交易日，凌晨 <06:00 歸當日。"""
    if ts.hour >= 15:
        return (ts + pd.Timedelta(days=1)).date()
    elif ts.hour < 6:
        return ts.date()
    else:
        return ts.date()


# ============================================================
# 2. 建構 30m K + 指標（只在夜盤段計算）
# ============================================================

def build_night_30m_with_indicators(df_1m):
    """建構夜盤 30m K 並計算 MACD/SMA，回傳每個交易日的夜盤最終狀態。"""

    # 只取夜盤 (15:00~05:00) + 日盤 08:45~10:45
    # 先建全部 30m，再篩選
    df_30m = df_1m.resample("30min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    # SMA
    for p in (5, 21, 65):
        df_30m[f"sma{p}"] = df_30m["close"].rolling(p).mean()

    # MACD (12, 26, 9)
    ema12 = df_30m["close"].ewm(span=12, adjust=False).mean()
    ema26 = df_30m["close"].ewm(span=26, adjust=False).mean()
    df_30m["macd"] = ema12 - ema26
    df_30m["macd_signal"] = df_30m["macd"].ewm(span=9, adjust=False).mean()
    df_30m["macd_hist"] = df_30m["macd"] - df_30m["macd_signal"]

    # trading_date
    df_30m["trading_date"] = df_30m.index.map(assign_trading_date)

    # warm-up: 需要 sma65
    df_30m = df_30m.dropna(subset=["sma65"])

    return df_30m


def get_night_snapshot(df_30m):
    """取每個交易日夜盤最後一根 30m bar 的指標快照。

    夜盤結束 = 05:00，所以取 hour < 6 的最後一根。
    """
    # 夜盤 bars: hour >= 15 或 hour < 6
    night = df_30m[(df_30m.index.hour >= 15) | (df_30m.index.hour < 6)].copy()

    snapshots = []
    for td, grp in night.groupby("trading_date"):
        if len(grp) == 0:
            continue
        last = grp.iloc[-1]
        snapshots.append({
            "trading_date": td,
            "night_close": last["close"],
            "macd": last["macd"],
            "macd_signal": last["macd_signal"],
            "macd_hist": last["macd_hist"],
            "sma5": last["sma5"],
            "sma21": last["sma21"],
            "sma65": last["sma65"],
            # 正規化（除以價格水準）
            "macd_pct": last["macd"] / last["close"] * 100,
            "macd_hist_pct": last["macd_hist"] / last["close"] * 100,
            # 簡單特徵
            "macd_above_zero": last["macd"] > 0,
            "macd_hist_positive": last["macd_hist"] > 0,
            "sma5_above_sma21": last["sma5"] > last["sma21"],
            "sma21_above_sma65": last["sma21"] > last["sma65"],
            "price_above_sma21": last["close"] > last["sma21"],
        })

    return pd.DataFrame(snapshots)


# ============================================================
# 3. 日盤前四根 30m K 的目標變量
# ============================================================

def calc_morning_target(df_1m):
    """計算每個交易日 08:45~10:45 的方向與振幅。

    前四根 30m K = 08:45~09:15, 09:15~09:45, 09:45~10:15, 10:15~10:45
    """
    # 篩選日盤前段
    morning = df_1m[(df_1m.index.hour >= 8) & (df_1m.index.hour < 11)].copy()
    morning = morning[~((morning.index.hour == 10) & (morning.index.minute >= 45))]
    morning["date"] = morning.index.date

    results = []
    for date, grp in morning.groupby("date"):
        if len(grp) < 30:  # 至少要有一些 bars
            continue

        # 前 120 分鐘 (08:45 ~ 10:45)
        first_bar = grp.iloc[0]
        morning_open = first_bar["open"]

        # 到 10:44 為止
        bars_2h = grp[grp.index < pd.Timestamp(f"{date} 10:45")]
        if len(bars_2h) < 20:
            continue

        morning_close = bars_2h["close"].iloc[-1]
        morning_high = bars_2h["high"].max()
        morning_low = bars_2h["low"].min()

        move = morning_close - morning_open
        amplitude = morning_high - morning_low
        direction = 1 if move > 0 else (-1 if move < 0 else 0)

        # 最大上漲 / 最大下跌（從 open 算）
        max_up = morning_high - morning_open
        max_down = morning_open - morning_low

        results.append({
            "trading_date": date,
            "morning_open": morning_open,
            "morning_close": morning_close,
            "morning_high": morning_high,
            "morning_low": morning_low,
            "move_pts": move,
            "amplitude": amplitude,
            "direction": direction,
            "max_up": max_up,
            "max_down": max_down,
        })

    return pd.DataFrame(results)


# ============================================================
# 4. 分析
# ============================================================

def analyze(merged):
    """核心分析：各條件對晨盤方向的預測力。"""

    print("\n" + "=" * 72)
    print(f"樣本數: {len(merged)}")
    print(f"時間範圍: {merged['trading_date'].min()} ~ {merged['trading_date'].max()}")
    print(f"晨盤平均振幅: {merged['amplitude'].mean():.1f} pts")
    print(f"晨盤平均 move: {merged['move_pts'].mean():+.1f} pts")
    print(f"晨盤上漲比例: {(merged['direction'] == 1).mean()*100:.1f}%")

    # --- 單因子分析 ---
    factors = {
        "MACD > 0": "macd_above_zero",
        "MACD Hist > 0": "macd_hist_positive",
        "SMA5 > SMA21": "sma5_above_sma21",
        "SMA21 > SMA65": "sma21_above_sma65",
        "Price > SMA21": "price_above_sma21",
    }

    print("\n" + "=" * 72)
    print("單因子分析：各夜盤條件 vs 日盤前四根方向")
    print("=" * 72)
    print(f"{'Factor':<20} {'Cond':>5} {'N':>5} {'Up%':>6} {'Mean':>8} "
          f"{'Median':>8} {'Amp':>6} | {'N':>5} {'Up%':>6} {'Mean':>8}")
    print("-" * 90)

    factor_results = []
    for name, col in factors.items():
        t_grp = merged[merged[col] == True]
        f_grp = merged[merged[col] == False]

        t_up = (t_grp["direction"] == 1).mean() * 100
        f_up = (f_grp["direction"] == 1).mean() * 100

        print(f"{name:<20} {'True':>5} {len(t_grp):>5} {t_up:>5.1f}% {t_grp['move_pts'].mean():>+8.1f} "
              f"{t_grp['move_pts'].median():>+8.1f} {t_grp['amplitude'].mean():>6.0f} "
              f"| {len(f_grp):>5} {f_up:>5.1f}% {f_grp['move_pts'].mean():>+8.1f}")

        # t-test
        t_stat, p_val = sp_stats.ttest_ind(t_grp["move_pts"], f_grp["move_pts"])
        ks_stat, ks_p = sp_stats.ks_2samp(t_grp["move_pts"], f_grp["move_pts"])
        factor_results.append({
            "factor": name,
            "n_true": len(t_grp), "n_false": len(f_grp),
            "up_pct_true": t_up, "up_pct_false": f_up,
            "mean_true": t_grp["move_pts"].mean(),
            "mean_false": f_grp["move_pts"].mean(),
            "t_stat": t_stat, "t_pval": p_val,
            "ks_stat": ks_stat, "ks_pval": ks_p,
        })

    print("\n統計檢定:")
    print(f"{'Factor':<20} {'t-stat':>8} {'t p-val':>9} {'KS stat':>8} {'KS p-val':>9}")
    print("-" * 60)
    for r in factor_results:
        sig = "***" if r["t_pval"] < 0.01 else "**" if r["t_pval"] < 0.05 else "*" if r["t_pval"] < 0.1 else ""
        print(f"{r['factor']:<20} {r['t_stat']:>+8.3f} {r['t_pval']:>9.4f}{sig:>3} "
              f"{r['ks_stat']:>8.4f} {r['ks_pval']:>9.4f}")

    # --- 組合分析：MACD方向 × SMA趨勢 ---
    print("\n" + "=" * 72)
    print("組合分析：MACD方向 × SMA5>21 × SMA21>65")
    print("=" * 72)

    merged["combo"] = (
        merged["macd_above_zero"].map({True: "M+", False: "M-"}) + "_" +
        merged["sma5_above_sma21"].map({True: "5>21", False: "5<21"}) + "_" +
        merged["sma21_above_sma65"].map({True: "21>65", False: "21<65"})
    )

    combo_stats = []
    print(f"\n{'Combo':<25} {'N':>5} {'Up%':>6} {'Mean':>8} {'Median':>8} {'Std':>7} {'Amp':>6}")
    print("-" * 75)

    for combo in sorted(merged["combo"].unique()):
        sub = merged[merged["combo"] == combo]
        up_pct = (sub["direction"] == 1).mean() * 100
        print(f"{combo:<25} {len(sub):>5} {up_pct:>5.1f}% {sub['move_pts'].mean():>+8.1f} "
              f"{sub['move_pts'].median():>+8.1f} {sub['move_pts'].std():>7.1f} "
              f"{sub['amplitude'].mean():>6.0f}")
        combo_stats.append({
            "combo": combo, "n": len(sub), "up_pct": up_pct,
            "mean": sub["move_pts"].mean(), "median": sub["move_pts"].median(),
        })

    # --- MACD% 分桶分析（正規化） ---
    print("\n" + "=" * 72)
    print("MACD% 分桶 → 晨盤方向（已除以價格正規化）")
    print("=" * 72)

    merged["macd_bucket"] = pd.qcut(merged["macd_pct"], q=5, labels=["很空", "偏空", "中性", "偏多", "很多"])
    print(f"\n{'Bucket':<8} {'N':>5} {'MACD% range':>20} {'Up%':>6} {'Mean':>8} {'Median':>8} {'Amp':>6}")
    print("-" * 70)
    for bucket in ["很空", "偏空", "中性", "偏多", "很多"]:
        sub = merged[merged["macd_bucket"] == bucket]
        up_pct = (sub["direction"] == 1).mean() * 100
        lo, hi = sub["macd_pct"].min(), sub["macd_pct"].max()
        print(f"{bucket:<8} {len(sub):>5} {lo:>+8.3f}%~{hi:>+7.3f}% {up_pct:>5.1f}% "
              f"{sub['move_pts'].mean():>+8.1f} {sub['move_pts'].median():>+8.1f} "
              f"{sub['amplitude'].mean():>6.0f}")

    # ANOVA across buckets
    groups = [merged[merged["macd_bucket"] == b]["move_pts"].values
              for b in ["很空", "偏空", "中性", "偏多", "很多"]]
    f_stat, f_pval = sp_stats.f_oneway(*groups)
    print(f"\nANOVA F={f_stat:.3f}, p={f_pval:.4f}")

    # --- MACD Histogram% 分桶 ---
    print("\n" + "=" * 72)
    print("MACD Histogram% 分桶 → 晨盤方向（已正規化）")
    print("=" * 72)

    merged["hist_bucket"] = pd.qcut(merged["macd_hist_pct"], q=5,
                                     labels=["強空", "偏空", "中性", "偏多", "強多"])
    print(f"\n{'Bucket':<8} {'N':>5} {'Hist% range':>20} {'Up%':>6} {'Mean':>8} {'Median':>8}")
    print("-" * 60)
    for bucket in ["強空", "偏空", "中性", "偏多", "強多"]:
        sub = merged[merged["hist_bucket"] == bucket]
        up_pct = (sub["direction"] == 1).mean() * 100
        lo, hi = sub["macd_hist_pct"].min(), sub["macd_hist_pct"].max()
        print(f"{bucket:<8} {len(sub):>5} {lo:>+8.4f}%~{hi:>+7.4f}% {up_pct:>5.1f}% "
              f"{sub['move_pts'].mean():>+8.1f} {sub['move_pts'].median():>+8.1f}")

    groups_h = [merged[merged["hist_bucket"] == b]["move_pts"].values
                for b in ["強空", "偏空", "中性", "偏多", "強多"]]
    f_stat_h, f_pval_h = sp_stats.f_oneway(*groups_h)
    print(f"\nANOVA F={f_stat_h:.3f}, p={f_pval_h:.4f}")

    return pd.DataFrame(factor_results), pd.DataFrame(combo_stats)


# ============================================================
# 5. 圖表
# ============================================================

def plot_single_factor(merged, col, label, fname):
    """單因子：True vs False 的報酬分佈。"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    t_data = merged[merged[col] == True]["move_pts"]
    f_data = merged[merged[col] == False]["move_pts"]

    # 直方圖
    ax = axes[0]
    bins = np.linspace(-300, 300, 31)
    ax.hist(t_data, bins=bins, alpha=0.6, color=COLOR_UP, label=f"True (N={len(t_data)})")
    ax.hist(f_data, bins=bins, alpha=0.6, color=COLOR_DOWN, label=f"False (N={len(f_data)})")
    ax.axvline(0, color="black", ls="--", lw=0.8)
    ax.axvline(t_data.mean(), color=COLOR_UP, ls="-", lw=1.5)
    ax.axvline(f_data.mean(), color=COLOR_DOWN, ls="-", lw=1.5)
    ax.set_title(f"{label}: Move Distribution")
    ax.set_xlabel("Morning Move (pts)")
    ax.legend()

    # Boxplot
    ax = axes[1]
    bp = ax.boxplot([t_data, f_data], tick_labels=["True", "False"],
                     patch_artist=True, showmeans=True)
    bp["boxes"][0].set_facecolor(COLOR_UP)
    bp["boxes"][0].set_alpha(0.5)
    bp["boxes"][1].set_facecolor(COLOR_DOWN)
    bp["boxes"][1].set_alpha(0.5)
    ax.axhline(0, color="black", ls="--", lw=0.8)
    ax.set_title(f"{label}: Boxplot")
    ax.set_ylabel("Morning Move (pts)")

    # 累積分佈
    ax = axes[2]
    t_sorted = np.sort(t_data)
    f_sorted = np.sort(f_data)
    ax.plot(t_sorted, np.linspace(0, 1, len(t_sorted)), color=COLOR_UP, label="True")
    ax.plot(f_sorted, np.linspace(0, 1, len(f_sorted)), color=COLOR_DOWN, label="False")
    ax.axvline(0, color="black", ls="--", lw=0.8)
    ax.set_title(f"{label}: CDF")
    ax.set_xlabel("Morning Move (pts)")
    ax.legend()

    plt.suptitle(f"H056: {label} → Morning 4-bar Move", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(OUT_DIR / fname, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / fname}")


def plot_macd_scatter(merged):
    """MACD 值 vs 晨盤 move 散佈圖。"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]
    colors = [COLOR_UP if d == 1 else COLOR_DOWN if d == -1 else "#999"
              for d in merged["direction"]]
    ax.scatter(merged["macd_pct"], merged["move_pts"], c=colors, s=8, alpha=0.4)
    ax.axhline(0, color="black", ls="--", lw=0.8)
    ax.axvline(0, color="black", ls="--", lw=0.8)
    ax.set_xlabel("Night MACD %")
    merged["move_pct"] = merged["move_pts"] / merged["morning_open"] * 100
    ax.set_ylabel("Morning Move (%)")
    ax.set_title("MACD% vs Morning Move%")

    # 加 rolling mean
    sorted_df = merged.sort_values("macd_pct")
    rolling_mean = sorted_df["move_pct"].rolling(50, center=True).mean()
    ax.plot(sorted_df["macd_pct"], rolling_mean, color="orange", lw=2, label="Rolling mean(50)")
    ax.legend()

    ax = axes[1]
    ax.scatter(merged["macd_hist_pct"], merged["move_pct"], c=colors, s=8, alpha=0.4)
    ax.axhline(0, color="black", ls="--", lw=0.8)
    ax.axvline(0, color="black", ls="--", lw=0.8)
    ax.set_xlabel("Night MACD Histogram %")
    ax.set_ylabel("Morning Move (%)")
    ax.set_title("MACD Hist% vs Morning Move%")

    sorted_df2 = merged.sort_values("macd_hist_pct")
    rolling_mean2 = sorted_df2["move_pct"].rolling(50, center=True).mean()
    ax.plot(sorted_df2["macd_hist_pct"], rolling_mean2, color="orange", lw=2, label="Rolling mean(50)")
    ax.legend()

    plt.suptitle("H056: Night MACD → Morning 4-bar Move", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "macd_scatter.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / 'macd_scatter.png'}")


def plot_combo_bar(combo_stats):
    """組合條件的 bar chart。"""
    df = combo_stats.sort_values("mean")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Mean move
    ax = axes[0]
    colors = [COLOR_UP if m > 0 else COLOR_DOWN for m in df["mean"]]
    ax.barh(range(len(df)), df["mean"], color=colors, alpha=0.7)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels([f"{c} (N={n})" for c, n in zip(df["combo"], df["n"])], fontsize=9)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Mean Morning Move (pts)")
    ax.set_title("Mean Move by Combo")

    # Up%
    ax = axes[1]
    df2 = df.sort_values("up_pct")
    colors2 = [COLOR_UP if u > 50 else COLOR_DOWN for u in df2["up_pct"]]
    ax.barh(range(len(df2)), df2["up_pct"], color=colors2, alpha=0.7)
    ax.set_yticks(range(len(df2)))
    ax.set_yticklabels([f"{c} (N={n})" for c, n in zip(df2["combo"], df2["n"])], fontsize=9)
    ax.axvline(50, color="black", lw=0.8, ls="--")
    ax.set_xlabel("Up %")
    ax.set_title("Up Rate by Combo")

    plt.suptitle("H056: MACD×SMA Combo → Morning Move", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "combo_bar.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / 'combo_bar.png'}")


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 72)
    print("H056: Night 30m MACD+SMA → 日盤前四根 30m K 方向預測")
    print("=" * 72)

    print("\n[1] 載入 1m 資料...")
    df_1m = load_1m()
    print(f"  {len(df_1m):,} rows, {df_1m.index.min()} ~ {df_1m.index.max()}")

    print("[2] 建構夜盤 30m K + 指標...")
    df_30m = build_night_30m_with_indicators(df_1m)
    print(f"  有效 30m bars: {len(df_30m):,}")

    print("[3] 取夜盤快照...")
    snapshots = get_night_snapshot(df_30m)
    print(f"  夜盤快照: {len(snapshots)} 日")

    print("[4] 計算日盤前四根目標...")
    targets = calc_morning_target(df_1m)
    print(f"  晨盤資料: {len(targets)} 日")

    print("[5] 合併...")
    merged = snapshots.merge(targets, on="trading_date", how="inner")
    print(f"  合併: {len(merged)} 日")

    # 分析
    factor_df, combo_df = analyze(merged)

    # 圖表
    print("\n[6] 產出圖表...")
    factors = {
        "MACD > 0": ("macd_above_zero", "factor_macd_zero.png"),
        "MACD Hist > 0": ("macd_hist_positive", "factor_macd_hist.png"),
        "SMA5 > SMA21": ("sma5_above_sma21", "factor_sma5_21.png"),
        "Price > SMA21": ("price_above_sma21", "factor_price_sma21.png"),
    }
    for label, (col, fname) in factors.items():
        plot_single_factor(merged, col, label, fname)

    plot_macd_scatter(merged)
    plot_combo_bar(combo_df)

    # 輸出
    merged.to_csv(OUT_DIR / "regime_daily.csv", index=False)
    print(f"[SAVED] {OUT_DIR / 'regime_daily.csv'}")
    factor_df.to_csv(OUT_DIR / "factor_tests.csv", index=False)
    print(f"[SAVED] {OUT_DIR / 'factor_tests.csv'}")

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

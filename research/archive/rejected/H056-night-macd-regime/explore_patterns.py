#!/usr/bin/env python3
"""H056 Phase 1b: 日盤前四根 30m K 棒組合型態分析.

將每根 30m K 標記為「高」（close > open）或「低」（close < open），
產出 2^4 = 16 種排列，搭配夜盤 MACD 多空方向，看哪些組合有利/不利。

Usage:
    uv run python research/active/H056-night-macd-regime/explore_patterns.py
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


def load_1m():
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
    if ts.hour >= 15:
        return (ts + pd.Timedelta(days=1)).date()
    elif ts.hour < 6:
        return ts.date()
    else:
        return ts.date()


def build_night_indicators(df_1m):
    """夜盤 30m 指標快照。"""
    df_30m = df_1m.resample("30min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    for p in (5, 21, 65):
        df_30m[f"sma{p}"] = df_30m["close"].rolling(p).mean()

    ema12 = df_30m["close"].ewm(span=12, adjust=False).mean()
    ema26 = df_30m["close"].ewm(span=26, adjust=False).mean()
    df_30m["macd"] = ema12 - ema26

    df_30m["trading_date"] = df_30m.index.map(assign_trading_date)
    df_30m = df_30m.dropna(subset=["sma65"])

    night = df_30m[(df_30m.index.hour >= 15) | (df_30m.index.hour < 6)]
    snapshots = []
    for td, grp in night.groupby("trading_date"):
        if len(grp) == 0:
            continue
        last = grp.iloc[-1]
        snapshots.append({
            "trading_date": td,
            "night_close": last["close"],
            "macd": last["macd"],
            "macd_pct": last["macd"] / last["close"] * 100,
            "macd_side": "空" if last["macd"] < 0 else "多",
            "sma5_above_sma21": last["sma5"] > last["sma21"],
        })
    return pd.DataFrame(snapshots)


def build_morning_4bars(df_1m):
    """建構每個交易日的前四根 30m K 並標記型態。

    Bar 1: 08:45~09:14
    Bar 2: 09:15~09:44
    Bar 3: 09:45~10:14
    Bar 4: 10:15~10:44
    """
    morning = df_1m[(df_1m.index.hour >= 8) & (df_1m.index.hour < 11)].copy()
    morning = morning[~((morning.index.hour == 10) & (morning.index.minute >= 45))]

    # Resample to 30m
    bars_30m = morning.resample("30min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    bars_30m["date"] = bars_30m.index.date
    bars_30m["bar_num"] = bars_30m.groupby("date").cumcount() + 1

    # 只取前四根
    bars_30m = bars_30m[bars_30m["bar_num"] <= 4]

    results = []
    for date, grp in bars_30m.groupby("date"):
        if len(grp) < 4:
            continue

        grp = grp.sort_values("bar_num")
        bar_dirs = []
        bar_data = []
        for _, row in grp.iterrows():
            d = "高" if row["close"] >= row["open"] else "低"
            bar_dirs.append(d)
            bar_data.append({
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "body": row["close"] - row["open"],
            })

        pattern = "".join(bar_dirs)

        # 整段 metrics
        morning_open = bar_data[0]["open"]
        morning_close = bar_data[3]["close"]
        morning_high = max(b["high"] for b in bar_data)
        morning_low = min(b["low"] for b in bar_data)
        move = morning_close - morning_open
        amplitude = morning_high - morning_low

        # bar2 開盤相對 bar1（第二根有沒有跳空）
        # 累積方向強度: 連續同方向的根數
        streak = 1
        for i in range(1, 4):
            if bar_dirs[i] == bar_dirs[i-1]:
                streak += 1
            else:
                break

        results.append({
            "trading_date": date,
            "pattern": pattern,
            "morning_open": morning_open,
            "morning_close": morning_close,
            "morning_high": morning_high,
            "morning_low": morning_low,
            "move_pts": move,
            "amplitude": amplitude,
            "direction": 1 if move > 0 else (-1 if move < 0 else 0),
            "bar1_body": bar_data[0]["body"],
            "bar2_body": bar_data[1]["body"],
            "bar3_body": bar_data[2]["body"],
            "bar4_body": bar_data[3]["body"],
            "opening_streak": streak,
            "first_dir": bar_dirs[0],
        })

    return pd.DataFrame(results)


def analyze_patterns(merged):
    """分析 16 種型態。"""

    print("\n" + "=" * 80)
    print(f"總樣本: {len(merged)}")
    print(f"夜盤偏空 (MACD<0): {(merged['macd_side']=='空').sum()}")
    print(f"夜盤偏多 (MACD≥0): {(merged['macd_side']=='多').sum()}")

    # --- 全體 16 型態 ---
    print("\n" + "=" * 80)
    print("全部 16 種四根 K 棒型態")
    print("=" * 80)

    print(f"\n{'Pattern':<8} {'N':>5} {'%':>6} {'Mean':>8} {'Med':>8} {'Up%':>6} {'Amp':>6} {'解讀'}")
    print("-" * 75)

    pattern_stats = []
    for pat in sorted(merged["pattern"].unique()):
        sub = merged[merged["pattern"] == pat]
        n = len(sub)
        pct = n / len(merged) * 100
        mean = sub["move_pts"].mean()
        med = sub["move_pts"].median()
        up = (sub["direction"] == 1).mean() * 100
        amp = sub["amplitude"].mean()

        # 解讀
        up_count = pat.count("高")
        if up_count >= 3:
            interp = "偏多型"
        elif up_count <= 1:
            interp = "偏空型"
        else:
            interp = "混合型"

        print(f"{pat:<8} {n:>5} {pct:>5.1f}% {mean:>+8.1f} {med:>+8.1f} {up:>5.1f}% {amp:>6.0f} {interp}")
        pattern_stats.append({
            "pattern": pat, "n": n, "pct": pct, "mean": mean,
            "median": med, "up_pct": up, "amplitude": amp,
        })

    # --- 搭配 MACD 方向 ---
    print("\n" + "=" * 80)
    print("夜盤 MACD 偏空 → 前四根型態（做多有利？）")
    print("=" * 80)

    bear = merged[merged["macd_side"] == "空"]
    print(f"\nN = {len(bear)}")
    print(f"\n{'Pattern':<8} {'N':>5} {'Mean':>8} {'Med':>8} {'Up%':>6} {'MFE':>8} {'MAE':>8}")
    print("-" * 65)

    for pat in sorted(bear["pattern"].unique()):
        sub = bear[bear["pattern"] == pat]
        if len(sub) < 5:
            continue
        mfe = (sub["morning_high"] - sub["morning_open"]).mean()
        mae = (sub["morning_open"] - sub["morning_low"]).mean()
        print(f"{pat:<8} {len(sub):>5} {sub['move_pts'].mean():>+8.1f} "
              f"{sub['move_pts'].median():>+8.1f} "
              f"{(sub['direction']==1).mean()*100:>5.1f}% "
              f"{mfe:>+8.1f} {mae:>8.1f}")

    print("\n" + "=" * 80)
    print("夜盤 MACD 偏多 → 前四根型態（做空有利？）")
    print("=" * 80)

    bull = merged[merged["macd_side"] == "多"]
    print(f"\nN = {len(bull)}")
    print(f"\n{'Pattern':<8} {'N':>5} {'Mean':>8} {'Med':>8} {'Dn%':>6} {'MFE_S':>8} {'MAE_S':>8}")
    print("-" * 65)

    for pat in sorted(bull["pattern"].unique()):
        sub = bull[bull["pattern"] == pat]
        if len(sub) < 5:
            continue
        # 做空的 MFE = open - low, MAE = high - open
        mfe_s = (sub["morning_open"] - sub["morning_low"]).mean()
        mae_s = (sub["morning_high"] - sub["morning_open"]).mean()
        dn_pct = (sub["direction"] == -1).mean() * 100
        print(f"{pat:<8} {len(sub):>5} {sub['move_pts'].mean():>+8.1f} "
              f"{sub['move_pts'].median():>+8.1f} "
              f"{dn_pct:>5.1f}% "
              f"{mfe_s:>+8.1f} {mae_s:>8.1f}")

    # --- 簡化：前兩根型態 ---
    print("\n" + "=" * 80)
    print("簡化觀察：前兩根型態 × MACD 方向")
    print("=" * 80)

    merged["first2"] = merged["pattern"].str[:2]

    print(f"\n{'MACD':<6} {'Pat2':<6} {'N':>5} {'Mean':>8} {'Med':>8} {'Up%':>6}")
    print("-" * 45)
    for side in ["空", "多"]:
        sub_side = merged[merged["macd_side"] == side]
        for pat2 in sorted(sub_side["first2"].unique()):
            sub = sub_side[sub_side["first2"] == pat2]
            up = (sub["direction"] == 1).mean() * 100
            print(f"{side:<6} {pat2:<6} {len(sub):>5} {sub['move_pts'].mean():>+8.1f} "
                  f"{sub['move_pts'].median():>+8.1f} {up:>5.1f}%")

    # --- 第一根方向的影響 ---
    print("\n" + "=" * 80)
    print("第一根 K 棒方向 × MACD 方向")
    print("=" * 80)

    print(f"\n{'MACD':<6} {'Bar1':<6} {'N':>5} {'Mean':>8} {'Med':>8} {'Up%':>6}")
    print("-" * 45)
    for side in ["空", "多"]:
        for d in ["高", "低"]:
            sub = merged[(merged["macd_side"] == side) & (merged["first_dir"] == d)]
            up = (sub["direction"] == 1).mean() * 100
            print(f"{side:<6} {d:<6} {len(sub):>5} {sub['move_pts'].mean():>+8.1f} "
                  f"{sub['move_pts'].median():>+8.1f} {up:>5.1f}%")

    return pd.DataFrame(pattern_stats)


def plot_patterns(merged, pattern_stats_df):
    """型態視覺化。"""

    # --- 1. 全 16 型態 bar chart ---
    df = pattern_stats_df.sort_values("mean")

    fig, axes = plt.subplots(1, 2, figsize=(14, 8))

    ax = axes[0]
    colors = [COLOR_UP if m > 0 else COLOR_DOWN for m in df["mean"]]
    ax.barh(range(len(df)), df["mean"], color=colors, alpha=0.7)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels([f"{p} (N={n})" for p, n in zip(df["pattern"], df["n"])], fontsize=10)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Mean Morning Move (pts)")
    ax.set_title("Mean Move by Pattern")

    ax = axes[1]
    df2 = df.sort_values("up_pct")
    colors2 = [COLOR_UP if u > 50 else COLOR_DOWN for u in df2["up_pct"]]
    ax.barh(range(len(df2)), df2["up_pct"], color=colors2, alpha=0.7)
    ax.set_yticks(range(len(df2)))
    ax.set_yticklabels([f"{p} (N={n})" for p, n in zip(df2["pattern"], df2["n"])], fontsize=10)
    ax.axvline(50, color="black", lw=0.8, ls="--")
    ax.set_xlabel("Up %")
    ax.set_title("Up Rate by Pattern")

    plt.suptitle("H056: Morning 4-Bar Pattern Analysis", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "patterns_all.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / 'patterns_all.png'}")

    # --- 2. MACD空 × 型態 ---
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    for i, (side, title) in enumerate([("空", "MACD<0 (做多有利?)"), ("多", "MACD≥0 (做空有利?)")]):
        ax = axes[i]
        sub = merged[merged["macd_side"] == side]
        pat_means = sub.groupby("pattern")["move_pts"].agg(["mean", "count"]).reset_index()
        pat_means = pat_means[pat_means["count"] >= 5].sort_values("mean")

        colors = [COLOR_UP if m > 0 else COLOR_DOWN for m in pat_means["mean"]]
        ax.barh(range(len(pat_means)), pat_means["mean"], color=colors, alpha=0.7)
        ax.set_yticks(range(len(pat_means)))
        ax.set_yticklabels([f"{p} (N={n})" for p, n in
                            zip(pat_means["pattern"], pat_means["count"])], fontsize=9)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_xlabel("Mean Move (pts)")
        ax.set_title(f"{title}")

    plt.suptitle("H056: Pattern × MACD Direction", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "patterns_by_macd.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / 'patterns_by_macd.png'}")

    # --- 3. 前兩根 × MACD heatmap ---
    fig, ax = plt.subplots(figsize=(8, 5))
    pivot = merged.pivot_table(index="macd_side", columns="first2",
                                values="move_pts", aggfunc=["mean", "count"])

    means = pivot["mean"]
    counts = pivot["count"]

    im = ax.imshow(means.values, cmap="RdYlGn", aspect="auto", vmin=-40, vmax=40)
    ax.set_xticks(range(len(means.columns)))
    ax.set_xticklabels(means.columns, fontsize=11)
    ax.set_yticks(range(len(means.index)))
    ax.set_yticklabels([f"MACD {s}" for s in means.index], fontsize=11)

    for i in range(len(means.index)):
        for j in range(len(means.columns)):
            v = means.values[i, j]
            n = int(counts.values[i, j])
            ax.text(j, i, f"{v:+.0f}\n(N={n})", ha="center", va="center", fontsize=10,
                    fontweight="bold" if abs(v) > 20 else "normal")

    plt.colorbar(im, ax=ax, label="Mean Move (pts)")
    ax.set_title("H056: First 2 Bars × MACD Direction → Mean Move", fontsize=12)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "first2_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVED] {OUT_DIR / 'first2_heatmap.png'}")


def main():
    print("=" * 80)
    print("H056 Phase 1b: 前四根 30m K 棒型態分析")
    print("=" * 80)

    print("\n[1] 載入資料...")
    df_1m = load_1m()

    print("[2] 夜盤指標...")
    night = build_night_indicators(df_1m)

    print("[3] 前四根 30m K...")
    morning = build_morning_4bars(df_1m)
    print(f"  {len(morning)} 日")

    print("[4] 合併...")
    merged = night.merge(morning, on="trading_date", how="inner")
    print(f"  {len(merged)} 日")

    print("[5] 分析...")
    pat_stats = analyze_patterns(merged)

    print("\n[6] 圖表...")
    plot_patterns(merged, pat_stats)

    merged.to_csv(OUT_DIR / "patterns_daily.csv", index=False)
    print(f"[SAVED] {OUT_DIR / 'patterns_daily.csv'}")

    print("\nDone.")


if __name__ == "__main__":
    main()

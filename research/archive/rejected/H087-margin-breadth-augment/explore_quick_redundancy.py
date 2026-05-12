"""
H087 Option B — 快速冗餘性檢查（不需 ETL backfill）

用 H079 archive 2024-01~2026-04 的廣度資料 + H084 indicators，
計算「廣度衍生指標」與 H084 4 個非冗餘軸的 Pearson r。

目的：在花 16h 跑 ETL backfill 前，先排除「廣度跟 H084 4 軸本來就高度相關」的可能。
若快檢顯示冗餘 → 直接 reject H087；若顯示獨立 → 才值得跑 backfill 做完整 Phase 1。

注意：H079 沒有 new_lows_52w / new_highs_52w（需要個股 OHLC，stock_day 才有），
本檢驗僅針對「漲跌家數家數類」廣度指標。
"""

from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
H079_CSV = PROJECT_ROOT / "research/archive/confirmed/H079-breadth-limitup-thermometer/results/daily_indicators.csv"
H084_CSV = PROJECT_ROOT / "research/active/H084-correction-bottom-survey/results/indicators.csv"
RESULTS_DIR = PROJECT_ROOT / "research/active/H087-margin-breadth-augment/results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

H084_AXES = ["vix_pct", "taiex_dist_125ma_z", "margin_drop_60d_pct", "econ_score"]
REDUNDANT_THRESHOLD = 0.6  # |r| >= 0.6 視為冗餘


def main() -> None:
    print("=" * 78)
    print("H087 Option B — 廣度指標冗餘性快檢（H079 2024+ 資料）")
    print("=" * 78)

    # 載入 H079 廣度資料
    h079 = pd.read_csv(H079_CSV, parse_dates=["trade_date"])
    print(f"\nH079 廣度資料: {len(h079)} rows, {h079['trade_date'].min().date()} ~ {h079['trade_date'].max().date()}")

    # 載入 H084 4 軸
    h084 = pd.read_csv(H084_CSV, parse_dates=["trade_date"])
    print(f"H084 indicators: {len(h084)} rows")

    # ---------------------------------------------------------
    # 候選廣度指標建置（所有 derivable from H079 fields）
    # ---------------------------------------------------------
    b = h079.copy()
    # 漲跌家數比 (high = bullish)
    b["adv_dec_ratio"] = b["up_count"] / b["down_count"].clip(lower=1)
    # 漲家比例 (high = bullish)
    b["up_pct"] = b["up_count"] / (b["up_count"] + b["down_count"]).clip(lower=1)
    # 累積廣度（McClellan-style sum of (up - down)）
    b["adv_dec_cum"] = (b["up_count"] - b["down_count"]).cumsum()
    # 漲停家數
    b["lu_count"] = b["up_limit_count"]
    b["ld_count"] = b["down_limit_count"]
    # 跌停金額占比 (high = panic)
    b["ld_value_ratio"] = b["ld_value_ratio"].fillna(0)
    # 漲停 - 跌停家數差
    b["limit_diff"] = b["up_limit_count"] - b["down_limit_count"]
    # 5d MA of adv_dec_ratio (smoothing)
    b["adv_dec_ratio_5d"] = b["adv_dec_ratio"].rolling(5, min_periods=3).mean()
    # 20d MA of up_pct
    b["up_pct_20d"] = b["up_pct"].rolling(20, min_periods=10).mean()
    # 累積廣度的 20d 變化
    b["adv_dec_cum_20d_chg"] = b["adv_dec_cum"].diff(20)
    # 跌停占比 5d MA
    b["ld_value_ratio_5d"] = b["ld_value_ratio"].rolling(5, min_periods=3).mean()

    breadth_cols = [
        "adv_dec_ratio", "up_pct", "adv_dec_cum",
        "lu_count", "ld_count", "ld_value_ratio", "limit_diff",
        "adv_dec_ratio_5d", "up_pct_20d", "adv_dec_cum_20d_chg",
        "ld_value_ratio_5d",
    ]

    # Merge
    merged = b[["trade_date"] + breadth_cols].merge(
        h084[["trade_date"] + H084_AXES], on="trade_date", how="inner"
    )
    merged = merged.dropna(subset=H084_AXES)
    print(f"\n合併後: {len(merged)} rows, {merged['trade_date'].min().date()} ~ {merged['trade_date'].max().date()}")
    print(f"覆蓋 H084 events 數量檢查：")
    events = pd.read_csv(PROJECT_ROOT / "research/active/H084-correction-bottom-survey/results/trough_mode_state.csv",
                         parse_dates=["trough_date"])
    in_window = events[(events["trough_date"] >= merged["trade_date"].min()) &
                       (events["trough_date"] <= merged["trade_date"].max())]
    print(in_window[["trough_date", "tier", "parent_tier"]].to_string(index=False))

    # ---------------------------------------------------------
    # Pairwise Pearson correlation
    # ---------------------------------------------------------
    print("\n=== Pairwise Pearson r：廣度 × H084 4 軸 ===\n")
    rows = []
    for bc in breadth_cols:
        x = merged[bc]
        nm = x.notna()
        if nm.sum() < 30:
            continue
        row = {"breadth_indicator": bc, "n": int(nm.sum())}
        max_abs_r = 0.0
        for axis in H084_AXES:
            y = merged[axis]
            mask = nm & y.notna()
            if mask.sum() < 30:
                row[f"r_{axis}"] = float("nan")
                continue
            r = np.corrcoef(x[mask], y[mask])[0, 1]
            row[f"r_{axis}"] = float(r)
            max_abs_r = max(max_abs_r, abs(r))
        row["max_abs_r"] = max_abs_r
        row["redundant"] = max_abs_r >= REDUNDANT_THRESHOLD
        rows.append(row)
    corr_df = pd.DataFrame(rows)
    corr_df = corr_df.sort_values("max_abs_r")
    corr_df.to_csv(RESULTS_DIR / "breadth_h084_correlation.csv", index=False)

    pd.set_option("display.float_format", lambda v: f"{v:+.3f}")
    cols = ["breadth_indicator", "n", "r_vix_pct", "r_taiex_dist_125ma_z",
            "r_margin_drop_60d_pct", "r_econ_score", "max_abs_r", "redundant"]
    print(corr_df[cols].to_string(index=False))
    pd.reset_option("display.float_format")

    # ---------------------------------------------------------
    # 統計：多少廣度指標非冗餘（max |r| < 0.6）？
    # ---------------------------------------------------------
    n_total = len(corr_df)
    n_independent = int((~corr_df["redundant"]).sum())
    n_redundant = int(corr_df["redundant"].sum())
    print()
    print(f"總計 {n_total} 個候選廣度指標：")
    print(f"  獨立（max |r| < {REDUNDANT_THRESHOLD}）：{n_independent}")
    print(f"  冗餘（max |r| ≥ {REDUNDANT_THRESHOLD}）：{n_redundant}")
    if n_independent > 0:
        ind_df = corr_df[~corr_df["redundant"]].sort_values("max_abs_r")
        print()
        print("獨立指標清單：")
        print(ind_df[["breadth_indicator", "max_abs_r"]].to_string(index=False))

    # ---------------------------------------------------------
    # 視覺化：correlation heatmap
    # ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 7))
    plot_df = corr_df.set_index("breadth_indicator")[
        ["r_vix_pct", "r_taiex_dist_125ma_z", "r_margin_drop_60d_pct", "r_econ_score"]
    ]
    im = ax.imshow(plot_df.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(plot_df.shape[1]))
    ax.set_xticklabels(["VIX_pct", "z 125MA", "margin_drop_60d", "econ_score"], rotation=30, ha="right")
    ax.set_yticks(range(plot_df.shape[0]))
    ax.set_yticklabels(plot_df.index)
    for i in range(plot_df.shape[0]):
        for j in range(plot_df.shape[1]):
            v = plot_df.values[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                    color="black" if abs(v) < 0.5 else "white", fontsize=9)
    ax.set_title(f"H087 Option B — Breadth × H084 4 axes  (N={len(merged)} days, redundant if |r| >= {REDUNDANT_THRESHOLD})")
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="Pearson r")
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "correlation_heatmap.png", dpi=110)
    plt.close()
    print(f"\nsaved {RESULTS_DIR / 'correlation_heatmap.png'}")

    # ---------------------------------------------------------
    # 額外：兩個 trough event 上廣度指標的「百分位」
    # （N=2 不足以下 hit rate verdict，但展示 sample）
    # ---------------------------------------------------------
    print("\n=== 兩個 trough 事件下，各廣度指標的當日 percentile（窗內排名）===")
    print("（N=2 完全不足以下 hit rate 判斷，僅做展示）")
    for _, ev in in_window.iterrows():
        trough_dt = ev["trough_date"]
        # 取最接近該 trough 的交易日
        near = merged[merged["trade_date"] <= trough_dt].tail(3)
        if near.empty:
            continue
        target_row = merged[merged["trade_date"] == near.iloc[-1]["trade_date"]].iloc[0]
        print(f"\n  {trough_dt.date()} (tier={ev['tier']}, parent={ev['parent_tier']}):")
        for bc in breadth_cols:
            v = target_row[bc]
            if pd.isna(v):
                continue
            pct = (merged[bc].dropna() <= v).mean() * 100
            print(f"    {bc:25s}  value={v:>10.2f}  pct={pct:5.1f}%")

    print("\n=== complete ===")


if __name__ == "__main__":
    main()

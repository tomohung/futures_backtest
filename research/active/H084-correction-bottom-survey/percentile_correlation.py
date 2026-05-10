"""
H084 Step 0.5 + 0.6：百分位命中率 + 相關性矩陣分析。

Step 0.5：對每個事件 trough，計算指標在「全期歷史分佈」下的百分位排名。
  - 識別在多數事件中都呈現極值（百分位 ≥85 或 ≤15）的指標
  - 計算每個指標的「命中率」（在 Tier B/C 事件中達極值的比例）

Step 0.6：指標兩兩 Pearson + Spearman 相關矩陣。
  - 識別冗餘群（|r| ≥ 0.6）

每個指標的「極值方向」：
  - 'low' = 極低值是底部訊號（dist_250ma、z_125ma、econ_score、vol_5_60 取雙向）
  - 'high' = 極高值是底部訊號（vix、vix_pct、blue_streak）
  指標欄位下加 _signal 列出觸發方向。

輸出：
  - results/percentile_table.csv：行=事件、列=指標、值=百分位
  - results/hit_rates.csv：每個指標的命中率
  - results/correlation_matrix.csv
  - results/correlation_heatmap.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"

# 指標配置：(欄名, 極值方向, 顯示名)
# 'low' = 觸發底部訊號的方向是低值；'high' = 高值
INDICATORS = [
    ("taiex_dist_250ma_pct", "low", "dist 250MA"),
    ("taiex_dist_125ma_z", "low", "z 125MA"),
    ("volume_5m_60m", "high", "vol 5/60"),  # 恐慌量增是底部
    ("vix", "high", "VIX"),
    ("vix_pct", "high", "VIX_pct"),
    ("econ_score", "low", "econ_score"),
    ("econ_blue_streak", "high", "blue_streak"),
]

MAIN_TIERS = {"A", "A-sub", "B", "B-sub", "C", "C-sub"}
EXTREME_THRESHOLD = 15  # 百分位 ≤15（low signal）或 ≥85（high signal）算極值


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    indicators = pd.read_csv(RESULTS_DIR / "indicators.csv", parse_dates=["trade_date"])
    indicators["trade_date"] = indicators["trade_date"].dt.date
    events = pd.read_csv(RESULTS_DIR / "tiers.csv",
                         parse_dates=["peak_date", "trough_date", "recovery_date"])
    events["trough_date"] = events["trough_date"].dt.date
    return indicators, events


def compute_percentile(value: float, series: pd.Series) -> float | None:
    """計算 value 在 series 中的百分位（0-100，含 NaN handling）"""
    if pd.isna(value):
        return None
    valid = series.dropna()
    if len(valid) == 0:
        return None
    rank = (valid <= value).sum()
    return rank / len(valid) * 100


def is_extreme(percentile: float | None, direction: str,
               threshold: float = EXTREME_THRESHOLD) -> bool:
    """判定百分位是否屬於該指標的極值方向"""
    if percentile is None:
        return False
    if direction == "low":
        return percentile <= threshold
    return percentile >= (100 - threshold)


def build_percentile_table(indicators: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """每個事件 trough 各指標的百分位"""
    main_events = events[events["tier"].isin(MAIN_TIERS)].copy()
    rows = []
    for _, ev in main_events.iterrows():
        match = indicators.index[indicators["trade_date"] == ev["trough_date"]]
        if len(match) == 0:
            continue
        r = indicators.iloc[match[0]]
        row = {
            "trough_date": ev["trough_date"],
            "tier": ev["tier"],
            "parent_tier": ev["parent_macro_tier"],
            "drawdown_pct": ev["drawdown_pct"],
        }
        for col, _, label in INDICATORS:
            value = r[col]
            pct = compute_percentile(value, indicators[col])
            row[f"{label}_val"] = value
            row[f"{label}_pct"] = round(pct, 1) if pct is not None else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("trough_date").reset_index(drop=True)


def build_hit_rates(percentile_table: pd.DataFrame) -> pd.DataFrame:
    """每個指標在事件中達極值的命中率（按 mode 拆分）"""
    rows = []
    for col, direction, label in INDICATORS:
        pct_col = f"{label}_pct"
        if pct_col not in percentile_table.columns:
            continue
        all_pcts = percentile_table[pct_col]
        valid = all_pcts.notna().sum()
        hits = sum(is_extreme(p, direction) for p in all_pcts if pd.notna(p))
        # By mode
        m1 = percentile_table[percentile_table["parent_tier"] != "A"][pct_col]
        m2 = percentile_table[percentile_table["parent_tier"] == "A"][pct_col]
        m1_valid = m1.notna().sum()
        m2_valid = m2.notna().sum()
        m1_hits = sum(is_extreme(p, direction) for p in m1 if pd.notna(p))
        m2_hits = sum(is_extreme(p, direction) for p in m2 if pd.notna(p))
        rows.append({
            "indicator": label,
            "extreme_dir": direction,
            "events_total": len(all_pcts),
            "events_with_data": valid,
            "hits_total": hits,
            "hit_rate_total": f"{hits}/{valid} ({100*hits/valid:.0f}%)" if valid else "—",
            "hit_rate_mode1": f"{m1_hits}/{m1_valid} ({100*m1_hits/m1_valid:.0f}%)" if m1_valid else "—",
            "hit_rate_mode2": f"{m2_hits}/{m2_valid} ({100*m2_hits/m2_valid:.0f}%)" if m2_valid else "—",
        })
    return pd.DataFrame(rows)


def build_correlation(indicators: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [col for col, _, _ in INDICATORS]
    label_map = {col: label for col, _, label in INDICATORS}
    df = indicators[cols].rename(columns=label_map).dropna()
    pearson = df.corr(method="pearson").round(3)
    spearman = df.corr(method="spearman").round(3)
    return pearson, spearman


def plot_correlation_heatmap(pearson: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(pearson.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pearson.columns)))
    ax.set_xticklabels(pearson.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pearson.index)))
    ax.set_yticklabels(pearson.index)
    # 在每格寫入相關係數
    for i in range(len(pearson.index)):
        for j in range(len(pearson.columns)):
            v = pearson.values[i, j]
            color = "white" if abs(v) > 0.5 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=9)
    ax.set_title("Indicator Pearson correlation (full sample)", fontsize=12)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    indicators, events = load_data()
    print(f"Loaded indicators={indicators.shape}, events={len(events)}")

    # Step 0.5: percentile table
    pct_table = build_percentile_table(indicators, events)
    out_pct = RESULTS_DIR / "percentile_table.csv"
    pct_table.to_csv(out_pct, index=False)
    print(f"Percentile table → {out_pct}")
    print(f"Shape: {pct_table.shape}")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    # 簡化顯示：只看 _pct 欄
    pct_cols = [c for c in pct_table.columns if c.endswith("_pct") or c in
                ("trough_date", "tier", "parent_tier", "drawdown_pct")]
    print("\n=== Percentile at trough ===")
    print(pct_table[pct_cols].to_string(index=False))

    # Hit rates
    hits = build_hit_rates(pct_table)
    out_hits = RESULTS_DIR / "hit_rates.csv"
    hits.to_csv(out_hits, index=False)
    print(f"\nHit rates → {out_hits}")
    print("\n=== Indicator hit rates (extreme = pct ≤15 or ≥85 by direction) ===")
    print(hits.to_string(index=False))

    # Step 0.6: correlation
    pearson, spearman = build_correlation(indicators)
    out_corr = RESULTS_DIR / "correlation_matrix.csv"
    pearson.to_csv(out_corr)
    print(f"\nPearson correlation → {out_corr}")
    print("\n=== Pearson correlation matrix ===")
    print(pearson.to_string())

    # Identify redundant pairs (|r| ≥ 0.6)
    print("\n=== Redundant pairs (|r| ≥ 0.6) ===")
    pairs = []
    for i, c1 in enumerate(pearson.columns):
        for c2 in pearson.columns[i+1:]:
            r = pearson.loc[c1, c2]
            if abs(r) >= 0.6:
                pairs.append((c1, c2, r))
    if pairs:
        for c1, c2, r in sorted(pairs, key=lambda x: -abs(x[2])):
            print(f"  {c1} ~ {c2}: r = {r:+.2f}")
    else:
        print("  (none)")

    out_heatmap = RESULTS_DIR / "correlation_heatmap.png"
    plot_correlation_heatmap(pearson, out_heatmap)
    print(f"\nHeatmap → {out_heatmap}")


if __name__ == "__main__":
    main()

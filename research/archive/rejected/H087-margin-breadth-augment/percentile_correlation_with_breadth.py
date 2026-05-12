"""H087 Phase 1.1 + 1.2: 把廣度指標加進 H084 指標集，重跑百分位 + 相關性。

不修改 H084 檔案，這個腳本：
  1. 載入 H084 indicators.csv + H084 tiers.csv
  2. 合併 H087 breadth_indicators.csv
  3. 計算每個事件 trough 的百分位
  4. 計算每個指標的命中率
  5. 計算 (H084 9 軸 + H087 7 軸) 的相關矩陣

輸出：
  - results/percentile_table_with_breadth.csv
  - results/hit_rates_with_breadth.csv
  - results/correlation_matrix_with_breadth.csv
  - results/correlation_heatmap_with_breadth.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

H084 = Path(__file__).parent.parent / "H084-correction-bottom-survey"
H087 = Path(__file__).parent
RESULTS = H087 / "results"

# H084 原始 9 軸
INDICATORS_H084 = [
    ("taiex_dist_250ma_pct", "low",  "dist 250MA"),
    ("taiex_dist_125ma_z",   "low",  "z 125MA"),
    ("volume_5m_60m",        "high", "vol 5/60"),
    ("vix",                  "high", "VIX"),
    ("vix_pct",              "high", "VIX_pct"),
    ("margin_drop_60d_pct",  "low",  "margin drop 60d"),
    ("margin_amt_pct_1y",    "low",  "margin pct 1y"),
    ("econ_score",           "low",  "econ_score"),
    ("econ_blue_streak",     "high", "blue_streak"),
]

# H087 廣度 7 軸（極值方向是先驗推測，由 hit rate 驗證）
INDICATORS_H087 = [
    ("breadth_adv_dec",           "low",  "adv/dec"),         # 跌家多 → 比值低
    ("breadth_adv_dec_cum",       "low",  "adv-dec cum"),     # McClellan 累積 → 底部低
    ("new_highs_52w",             "low",  "new highs 52w"),   # 底部沒新高
    ("new_lows_52w",              "high", "new lows 52w"),    # 底部新低爆量
    ("new_high_low_diff",         "low",  "high-low diff"),   # 底部新低多 → 負差
    ("value_concentration_top20", "high", "top20 concen"),    # 防禦性資金流向大型股
    ("value_per_stock",           "high", "value/stock"),     # 恐慌量
]

INDICATORS = INDICATORS_H084 + INDICATORS_H087
MAIN_TIERS = {"A", "A-sub", "B", "B-sub", "C", "C-sub"}
EXTREME_THRESHOLD = 15


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    h084 = pd.read_csv(H084 / "results" / "indicators.csv", parse_dates=["trade_date"])
    h087 = pd.read_csv(H087 / "results" / "breadth_indicators.csv", parse_dates=["trade_date"])
    merged = h084.merge(h087, on="trade_date", how="left")
    merged["trade_date"] = merged["trade_date"].dt.date

    events = pd.read_csv(H084 / "results" / "tiers.csv",
                         parse_dates=["peak_date", "trough_date", "recovery_date"])
    events["trough_date"] = events["trough_date"].dt.date
    return merged, events


def compute_percentile(value: float, series: pd.Series) -> float | None:
    if pd.isna(value):
        return None
    valid = series.dropna()
    if len(valid) == 0:
        return None
    return (valid <= value).sum() / len(valid) * 100


def is_extreme(percentile: float | None, direction: str,
               threshold: float = EXTREME_THRESHOLD) -> bool:
    if percentile is None:
        return False
    return percentile <= threshold if direction == "low" else percentile >= (100 - threshold)


def build_percentile_table(indicators: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    main = events[events["tier"].isin(MAIN_TIERS)]
    rows = []
    for _, ev in main.iterrows():
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
            value = r[col] if col in r else None
            pct = compute_percentile(value, indicators[col]) if col in indicators.columns else None
            row[f"{label}_val"] = value
            row[f"{label}_pct"] = round(pct, 1) if pct is not None else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("trough_date").reset_index(drop=True)


def build_hit_rates(pct_table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, direction, label in INDICATORS:
        pc = f"{label}_pct"
        if pc not in pct_table.columns:
            continue
        all_p = pct_table[pc]
        valid = all_p.notna().sum()
        hits = sum(is_extreme(p, direction) for p in all_p if pd.notna(p))
        # by mode (A vs non-A)
        m_nonA = pct_table[pct_table["parent_tier"] != "A"][pc]
        m_A = pct_table[pct_table["parent_tier"] == "A"][pc]
        m1_valid = m_nonA.notna().sum()
        m2_valid = m_A.notna().sum()
        m1_hits = sum(is_extreme(p, direction) for p in m_nonA if pd.notna(p))
        m2_hits = sum(is_extreme(p, direction) for p in m_A if pd.notna(p))
        rows.append({
            "indicator": label,
            "source": "H084" if (col, direction, label) in INDICATORS_H084 else "H087",
            "extreme_dir": direction,
            "events_total": len(all_p),
            "events_with_data": valid,
            "hit_rate_total": f"{hits}/{valid} ({100*hits/valid:.0f}%)" if valid else "—",
            "hit_pct_total":  (100*hits/valid) if valid else None,
            "hit_rate_nonA":  f"{m1_hits}/{m1_valid} ({100*m1_hits/m1_valid:.0f}%)" if m1_valid else "—",
            "hit_rate_A":     f"{m2_hits}/{m2_valid} ({100*m2_hits/m2_valid:.0f}%)" if m2_valid else "—",
        })
    return pd.DataFrame(rows)


def build_correlation(indicators: pd.DataFrame) -> pd.DataFrame:
    cols = [col for col, _, _ in INDICATORS]
    label_map = {col: label for col, _, label in INDICATORS}
    df = indicators[cols].rename(columns=label_map).dropna()
    return df.corr(method="pearson").round(3)


def plot_heatmap(pearson: pd.DataFrame, out_path: Path) -> None:
    n = len(pearson)
    fig, ax = plt.subplots(figsize=(max(8, n*0.65), max(7, n*0.55)))
    im = ax.imshow(pearson.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(n))
    ax.set_xticklabels(pearson.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n))
    ax.set_yticklabels(pearson.index, fontsize=8)
    for i in range(n):
        for j in range(n):
            v = pearson.values[i, j]
            color = "white" if abs(v) > 0.5 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=7)
    # 分隔 H084 vs H087 區塊（前 9 是 H084）
    ax.axhline(8.5, color="black", linewidth=1.5)
    ax.axvline(8.5, color="black", linewidth=1.5)
    ax.set_title("Pearson correlation: H084 9 axes + H087 7 breadth", fontsize=11)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    indicators, events = load_data()
    print(f"Loaded indicators={indicators.shape}, events={len(events)}")

    pct_table = build_percentile_table(indicators, events)
    pct_table.to_csv(RESULTS / "percentile_table_with_breadth.csv", index=False)
    print(f"Percentile table shape={pct_table.shape}")

    pd.set_option("display.width", 280)
    pd.set_option("display.max_columns", None)
    # 只看廣度指標的百分位
    h087_pct_cols = [f"{label}_pct" for _, _, label in INDICATORS_H087]
    base_cols = ["trough_date", "tier", "parent_tier", "drawdown_pct"]
    print("\n=== Trough percentiles — H087 breadth indicators ===")
    print(pct_table[base_cols + h087_pct_cols].to_string(index=False))

    hits = build_hit_rates(pct_table)
    hits.to_csv(RESULTS / "hit_rates_with_breadth.csv", index=False)
    print("\n=== Hit rates (pct ≤15 / ≥85 by direction) ===")
    print(hits.to_string(index=False))

    pearson = build_correlation(indicators)
    pearson.to_csv(RESULTS / "correlation_matrix_with_breadth.csv")
    plot_heatmap(pearson, RESULTS / "correlation_heatmap_with_breadth.png")
    print(f"\nCorrelation matrix saved. Heatmap → results/correlation_heatmap_with_breadth.png")

    # H087 breadth vs H084's 4 confirmed non-redundant axes
    NON_RED_4 = ["VIX_pct", "z 125MA", "margin drop 60d", "econ_score"]
    print("\n=== H087 breadth × H084 4 non-redundant axes ===")
    h087_labels = [label for _, _, label in INDICATORS_H087]
    sub = pearson.loc[h087_labels, NON_RED_4]
    print(sub.to_string())

    print("\n=== Redundant pairs in H087 breadth (|r| ≥ 0.6 to any H084 axis) ===")
    for label in h087_labels:
        worst = sub.loc[label].abs().max()
        worst_col = sub.loc[label].abs().idxmax()
        flag = " ⚠ REDUNDANT" if worst >= 0.6 else ""
        print(f"  {label:20s} max |r| = {worst:.2f}  vs {worst_col:18s}{flag}")


if __name__ == "__main__":
    main()

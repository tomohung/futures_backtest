"""
H084 Step 0.4：事件研究 — 各指標在 Tier B/C trough ±30 trading days 軌跡疊圖

對每個事件（Tier B、C、B-sub、C-sub；Tier A 也畫但用不同樣式作對照）：
  1. 找到 trough_date 在 TAIEX 交易日序列中的索引
  2. 取 ±30 trading days 窗口
  3. X 軸：相對 trough 的交易日數（-30 ~ +30）
  4. Y 軸：指標原始值

每個指標一個 panel，所有事件的軌跡疊在一起。
顏色：parent_macro_tier == 'A' → 紅（Mode 2 結構熊內部），其餘 → 藍（Mode 1 多頭修正）。
中位數軌跡用粗線疊在最上層。

輸出：results/event_study.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"
WINDOW = 30  # ±30 trading days

INDICATORS = [
    ("taiex_dist_250ma_pct", "TAIEX dist 250MA (%)"),
    ("taiex_dist_125ma_z", "TAIEX dist 125MA (z)"),
    ("volume_5m_60m", "Volume 5MA / 60MA"),
    ("vix", "VIX"),
    ("vix_pct", "VIX 1y percentile"),
    ("econ_score", "Econ signal score"),
]

# 主要分析的 tier（不含 D）
MAIN_TIERS = {"A", "A-sub", "B", "B-sub", "C", "C-sub"}


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    indicators = pd.read_csv(RESULTS_DIR / "indicators.csv", parse_dates=["trade_date"])
    indicators["trade_date"] = indicators["trade_date"].dt.date
    events = pd.read_csv(RESULTS_DIR / "tiers.csv",
                         parse_dates=["peak_date", "trough_date", "recovery_date"])
    events["trough_date"] = events["trough_date"].dt.date
    return indicators, events


def extract_window(indicators: pd.DataFrame, trough_date,
                   indicator_col: str, window: int = WINDOW) -> pd.DataFrame | None:
    """從 indicators 中找出 trough_date 對應交易日，取 ±window 窗口
    Returns DataFrame with columns [rel_day, value] or None if trough not found."""
    idx_match = indicators.index[indicators["trade_date"] == trough_date]
    if len(idx_match) == 0:
        return None
    trough_idx = idx_match[0]
    lo = max(0, trough_idx - window)
    hi = min(len(indicators), trough_idx + window + 1)
    seg = indicators.iloc[lo:hi].copy()
    seg["rel_day"] = list(range(lo - trough_idx, hi - trough_idx))
    return seg[["rel_day", indicator_col]].rename(columns={indicator_col: "value"})


def plot_event_study(indicators: pd.DataFrame, events: pd.DataFrame,
                     out_path: Path) -> None:
    main_events = events[events["tier"].isin(MAIN_TIERS)].copy()
    print(f"Plotting {len(main_events)} events")

    n_ind = len(INDICATORS)
    n_cols = 2
    n_rows = (n_ind + 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4 * n_rows), sharex=True)
    axes = axes.flatten()

    for ax, (col, title) in zip(axes, INDICATORS):
        # 收集每個事件的軌跡用於計算中位數
        all_traces: list[pd.DataFrame] = []

        for _, ev in main_events.iterrows():
            seg = extract_window(indicators, ev["trough_date"], col)
            if seg is None or seg["value"].isna().all():
                continue

            mode2 = ev["parent_macro_tier"] == "A"
            color = "#c8102e" if mode2 else "#1f77b4"
            alpha = 0.35
            ax.plot(seg["rel_day"], seg["value"], color=color,
                    alpha=alpha, linewidth=1.0, zorder=2)
            all_traces.append(seg.set_index("rel_day")["value"].rename(ev["trough_date"]))

        # 中位數線
        if all_traces:
            mat = pd.concat(all_traces, axis=1)
            median = mat.median(axis=1)
            ax.plot(median.index, median.values, color="black",
                    linewidth=2.0, zorder=5, label="median")

            # 分別計算 Mode 1 / Mode 2 的中位數
            mode1_keys = [ev["trough_date"] for _, ev in main_events.iterrows()
                          if ev["parent_macro_tier"] != "A"]
            mode2_keys = [ev["trough_date"] for _, ev in main_events.iterrows()
                          if ev["parent_macro_tier"] == "A"]
            m1 = mat[[k for k in mode1_keys if k in mat.columns]].median(axis=1)
            m2 = mat[[k for k in mode2_keys if k in mat.columns]].median(axis=1)
            ax.plot(m1.index, m1.values, color="#1f77b4", linewidth=2.0,
                    linestyle="--", zorder=4, label="Mode 1 median")
            ax.plot(m2.index, m2.values, color="#c8102e", linewidth=2.0,
                    linestyle="--", zorder=4, label="Mode 2 median")

        ax.axvline(x=0, color="gray", linewidth=0.8, linestyle=":", zorder=1)
        ax.axhline(y=0, color="gray", linewidth=0.5, alpha=0.4, zorder=1)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Trading days from trough")
        ax.set_ylabel(col)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)

    # 隱藏多餘 subplot
    for ax in axes[n_ind:]:
        ax.axis("off")

    fig.suptitle(
        f"Event study: indicator trajectories around troughs (±{WINDOW} trading days)\n"
        f"Blue = Mode 1 (bull correction); Red = Mode 2 (within Tier A regime)",
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def summary_at_trough(indicators: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """每個事件 trough day 的指標值，輸出表格"""
    main_events = events[events["tier"].isin(MAIN_TIERS)].copy()
    rows = []
    for _, ev in main_events.iterrows():
        idx_match = indicators.index[indicators["trade_date"] == ev["trough_date"]]
        if len(idx_match) == 0:
            continue
        r = indicators.iloc[idx_match[0]]
        rows.append({
            "trough_date": ev["trough_date"],
            "tier": ev["tier"],
            "parent_tier": ev["parent_macro_tier"],
            "drawdown_pct": ev["drawdown_pct"],
            "dist_250ma": r["taiex_dist_250ma_pct"],
            "z_125ma": r["taiex_dist_125ma_z"],
            "vol_5_60": r["volume_5m_60m"],
            "vix": r["vix"],
            "vix_pct": r["vix_pct"],
            "econ_score": r["econ_score"],
            "econ_color": r["econ_signal_color"],
            "blue_streak": r["econ_blue_streak"],
        })
    df = pd.DataFrame(rows).sort_values("trough_date").reset_index(drop=True)
    return df


def main() -> None:
    indicators, events = load_data()
    print(f"Loaded indicators={indicators.shape}, events={len(events)}")

    out_path = RESULTS_DIR / "event_study.png"
    plot_event_study(indicators, events, out_path)
    print(f"Chart → {out_path}")

    summary = summary_at_trough(indicators, events)
    csv_path = RESULTS_DIR / "trough_indicators.csv"
    summary.to_csv(csv_path, index=False)
    print(f"\nSummary table → {csv_path}")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(summary.to_string(index=False))

    # Mode 1 vs Mode 2 中位數比較
    print("\n=== Mode-wise median at trough ===")
    by_mode = summary.copy()
    by_mode["mode"] = by_mode["parent_tier"].apply(lambda t: "Mode 2 (A)" if t == "A" else "Mode 1 (B/C)")
    cols_num = ["dist_250ma", "z_125ma", "vol_5_60", "vix", "vix_pct", "econ_score", "blue_streak"]
    print(by_mode.groupby("mode")[cols_num].median().to_string())


if __name__ == "__main__":
    main()

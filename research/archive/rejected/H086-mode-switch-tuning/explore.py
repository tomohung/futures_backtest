"""
H086 Phase 1 — Mode 1/2 切換規則 grid search

對每組規則計算：
  - Tier A days 中觸發 Mode 2 的比例（recall）
  - bull days 中觸發 Mode 2 的比例（FPR）
  - Tier B/C/D 內的觸發率（理想：B 比 C 高、C 比 D 高）
  - 規則切換 lag（從 Tier A 進入後首次觸發 Mode 2 的天數）

規則組合：
  - A 條件（cond_A_below_250ma 持續 ≥ N 天）：N ∈ {0, 5, 10, 20, 60}
  - B 條件（econ-related）：
      * blue_streak ≥ {1, 2, 3, 4, 6}
      * econ_score ≤ {16 (藍燈), 22 (黃藍以下)}
      → 共 7 種 B 變體
  - 邏輯：AND, OR

總計 5 × 7 × 2 = 70 rules + 既有 baseline。

IS = 2008-2018，OOS = 2019-2026。
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
warnings.filterwarnings("ignore", category=RuntimeWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
H084_DIR = PROJECT_ROOT / "research" / "active" / "H084-correction-bottom-survey"
H086_DIR = PROJECT_ROOT / "research" / "active" / "H086-mode-switch-tuning"
RESULTS_DIR = H086_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

IS_END = pd.Timestamp("2018-12-31")

A_PERSIST = [0, 5, 10, 20, 60]
B_VARIANTS = [
    ("streak>=1", lambda df: df["econ_blue_streak"] >= 1),
    ("streak>=2", lambda df: df["econ_blue_streak"] >= 2),
    ("streak>=3", lambda df: df["econ_blue_streak"] >= 3),
    ("streak>=4", lambda df: df["econ_blue_streak"] >= 4),
    ("streak>=6", lambda df: df["econ_blue_streak"] >= 6),
    ("score<=16", lambda df: df["econ_score"] <= 16),    # 藍燈
    ("score<=22", lambda df: df["econ_score"] <= 22),    # 黃藍以下
]


def load_data() -> pd.DataFrame:
    fs = pd.read_csv(H084_DIR / "results" / "fuse_state.csv", parse_dates=["trade_date"])
    fs = fs.sort_values("trade_date").reset_index(drop=True)
    return fs


def make_a_persist(fs: pd.DataFrame, n: int) -> pd.Series:
    """cond_A_below_250ma 連續 ≥ N 個交易日為 True"""
    cond = fs["cond_A_below_250ma"].astype(int)
    if n <= 0:
        return cond.astype(bool)
    return (cond.rolling(window=n, min_periods=n).min() == 1)


def confusion(rule_signal: pd.Series, tier: pd.Series) -> dict:
    """對某個 tier，計算 rule=True 的比例"""
    out = {}
    for t in ["A", "B", "C", "D", "bull"]:
        mask = (tier == t)
        n = mask.sum()
        if n == 0:
            out[f"hit_{t}"] = float("nan")
            out[f"n_{t}"] = 0
        else:
            hit = rule_signal[mask].sum()
            out[f"hit_{t}"] = float(hit / n)
            out[f"n_{t}"] = int(n)
    return out


def first_lag_after_tier_A_entry(rule_signal: pd.Series, tier: pd.Series, dates: pd.Series) -> float:
    """每次進入 Tier A 後，到首次觸發 rule=True 的交易日數；回傳中位數"""
    in_A = (tier == "A").values
    sig = rule_signal.values
    lags = []
    i = 0
    n = len(in_A)
    while i < n:
        if not in_A[i]:
            i += 1; continue
        # 找這段 A 區間
        j = i
        while j < n and in_A[j]:
            j += 1
        # 在 [i, j-1] 間找首次 sig=True
        seg = sig[i:j]
        idx_true = np.where(seg)[0]
        if len(idx_true) > 0:
            lags.append(int(idx_true[0]))
        # 否則整段 A 都沒觸發 → 不計
        i = j
    if not lags:
        return float("nan")
    return float(np.median(lags))


def evaluate(fs: pd.DataFrame, rule_signal: pd.Series, name: str, split: str) -> dict:
    cm = confusion(rule_signal, fs["macro_tier"])
    lag = first_lag_after_tier_A_entry(rule_signal, fs["macro_tier"], fs["trade_date"])
    return {
        "rule": name,
        "split": split,
        "recall_A": cm["hit_A"],
        "FPR_bull": cm["hit_bull"],
        "hit_B":    cm["hit_B"],
        "hit_C":    cm["hit_C"],
        "hit_D":    cm["hit_D"],
        "n_A":      cm["n_A"],
        "n_bull":   cm["n_bull"],
        "youden_J": cm["hit_A"] - cm["hit_bull"],
        "median_lag_days": lag,
    }


def main() -> None:
    print("=" * 78)
    print("H086 Phase 1 — Mode 1/2 切換規則 Grid Search")
    print("=" * 78)

    fs = load_data()
    print(f"\nfuse_state: {len(fs)} rows, {fs['trade_date'].min().date()} ~ {fs['trade_date'].max().date()}")
    print(f"macro_tier 分佈: {fs['macro_tier'].value_counts().to_dict()}")

    fs_is  = fs[fs["trade_date"] <= IS_END].reset_index(drop=True)
    fs_oos = fs[fs["trade_date"] >  IS_END].reset_index(drop=True)
    print(f"IS  : {len(fs_is)} rows, A days = {(fs_is['macro_tier']=='A').sum()}, bull days = {(fs_is['macro_tier']=='bull').sum()}")
    print(f"OOS : {len(fs_oos)} rows, A days = {(fs_oos['macro_tier']=='A').sum()}, bull days = {(fs_oos['macro_tier']=='bull').sum()}")

    # ----------------------------------------------------------
    # Baseline (H084 既有)
    # ----------------------------------------------------------
    rows = []
    for split_name, df in [("FULL", fs), ("IS", fs_is), ("OOS", fs_oos)]:
        for col, name in [
            ("cond_A_below_250ma", "BASELINE: cond_A only (TAIEX<250MA)"),
            ("cond_B_blue_streak", "BASELINE: cond_B only (streak>=3)"),
            ("mode2_AND",          "BASELINE: H084 mode2_AND"),
            ("mode2_OR",           "BASELINE: H084 mode2_OR"),
        ]:
            rows.append(evaluate(df, df[col].astype(bool), name, split_name))

    # ----------------------------------------------------------
    # Grid: 5 A-persist × 7 B-variants × 2 logic = 70 rules
    # ----------------------------------------------------------
    for split_name, df in [("FULL", fs), ("IS", fs_is), ("OOS", fs_oos)]:
        for n_a in A_PERSIST:
            a_sig = make_a_persist(df, n_a).fillna(False)
            for b_name, b_fn in B_VARIANTS:
                b_sig = b_fn(df).astype(bool).fillna(False)
                for logic in ["AND", "OR"]:
                    sig = (a_sig & b_sig) if logic == "AND" else (a_sig | b_sig)
                    name = f"A>={n_a}d {logic} B={b_name}"
                    rows.append(evaluate(df, sig, name, split_name))

    grid = pd.DataFrame(rows)
    grid.to_csv(RESULTS_DIR / "rules_grid.csv", index=False)
    print(f"\nGrid 完成：{len(grid)} 列（70 rules + 4 baseline × 3 splits）")

    # ----------------------------------------------------------
    # 顯示 FULL 期間在 target zone 的 rules
    # ----------------------------------------------------------
    full = grid[grid["split"] == "FULL"].copy()
    target = full[(full["recall_A"] >= 0.80) & (full["FPR_bull"] <= 0.10)]
    print(f"\n=== FULL 期間 target zone (recall≥80% AND FPR≤10%) ===")
    print(f"  通過數：{len(target)}")
    if len(target) > 0:
        cols = ["rule", "recall_A", "FPR_bull", "hit_B", "hit_C", "youden_J", "median_lag_days"]
        print(target.sort_values("youden_J", ascending=False)[cols].to_string(index=False))

    # ----------------------------------------------------------
    # 顯示 FULL 期間 Top-15 by Youden J
    # ----------------------------------------------------------
    print(f"\n=== FULL 期間 Top-15 (依 Youden J = recall_A - FPR_bull) ===")
    cols = ["rule", "recall_A", "FPR_bull", "hit_B", "hit_C", "hit_D", "youden_J", "median_lag_days"]
    print(full.sort_values("youden_J", ascending=False).head(15)[cols].to_string(index=False))

    # ----------------------------------------------------------
    # IS/OOS 一致性：top FULL 的 5 個 rule
    # ----------------------------------------------------------
    print(f"\n=== IS vs OOS 一致性檢查（FULL Top-5 by Youden J）===")
    top_rules = full.sort_values("youden_J", ascending=False).head(5)["rule"].tolist()
    cmp_rows = []
    for r in top_rules:
        is_row  = grid[(grid["split"] == "IS")  & (grid["rule"] == r)].iloc[0]
        oos_row = grid[(grid["split"] == "OOS") & (grid["rule"] == r)].iloc[0]
        cmp_rows.append({
            "rule": r,
            "IS_recall": is_row["recall_A"],
            "OOS_recall": oos_row["recall_A"],
            "Δrecall": oos_row["recall_A"] - is_row["recall_A"],
            "IS_FPR": is_row["FPR_bull"],
            "OOS_FPR": oos_row["FPR_bull"],
            "ΔFPR": oos_row["FPR_bull"] - is_row["FPR_bull"],
        })
    cmp_df = pd.DataFrame(cmp_rows)
    print(cmp_df.to_string(index=False))
    cmp_df.to_csv(RESULTS_DIR / "is_oos_consistency.csv", index=False)

    # ----------------------------------------------------------
    # Pareto frontier scatter (FULL)
    # ----------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    for ax, split_name in zip(axes, ["IS", "OOS", "FULL"]):
        sub = grid[grid["split"] == split_name].copy()
        is_baseline = sub["rule"].str.startswith("BASELINE")
        ax.scatter(sub.loc[~is_baseline, "FPR_bull"], sub.loc[~is_baseline, "recall_A"],
                   s=40, c="steelblue", alpha=0.6, label="grid rules")
        ax.scatter(sub.loc[is_baseline, "FPR_bull"], sub.loc[is_baseline, "recall_A"],
                   s=80, c="black", marker="x", label="baseline")
        # target zone
        ax.axhline(0.80, color="red", ls="--", lw=0.7, alpha=0.5)
        ax.axvline(0.10, color="red", ls="--", lw=0.7, alpha=0.5)
        ax.fill_between([0, 0.10], 0.80, 1.0, color="green", alpha=0.08, label="target zone")
        # 標記 target zone 內的 rules
        target_sub = sub[(sub["recall_A"] >= 0.80) & (sub["FPR_bull"] <= 0.10) & (~is_baseline)]
        for _, r in target_sub.iterrows():
            ax.annotate(r["rule"].replace(" ", "\n"), (r["FPR_bull"], r["recall_A"]),
                        fontsize=6, alpha=0.7)
        # baseline 標籤
        for _, r in sub[is_baseline].iterrows():
            ax.annotate(r["rule"].replace("BASELINE: ", ""), (r["FPR_bull"], r["recall_A"]),
                        fontsize=7, color="black", alpha=0.9, xytext=(5, 5), textcoords="offset points")
        ax.set_xlabel("FPR (bull days)")
        if ax is axes[0]:
            ax.set_ylabel("Recall (Tier A days)")
        ax.set_title(f"{split_name} (N={len(sub)} rules)")
        ax.set_xlim(-0.02, 0.6)
        ax.set_ylim(0, 1.05)
        ax.grid(alpha=0.3)
        ax.legend(loc="lower right", fontsize=8)
    plt.suptitle("H086 — Mode 1/2 規則 Pareto frontier (target: recall≥80% & FPR≤10%)")
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "pareto_frontier.png", dpi=110)
    plt.close()
    print(f"\nsaved {RESULTS_DIR / 'pareto_frontier.png'}")

    # ----------------------------------------------------------
    # tier B/C/D ratios for top-5 rules
    # ----------------------------------------------------------
    print("\n=== Top-5 規則的 tier 結構性檢查（理想：A>B>C>D>bull）===")
    cols = ["rule", "recall_A", "hit_B", "hit_C", "hit_D", "FPR_bull"]
    print(full.sort_values("youden_J", ascending=False).head(5)[cols].to_string(index=False))

    print("\n=== complete ===")
    print(f"輸出：{RESULTS_DIR}")


if __name__ == "__main__":
    main()

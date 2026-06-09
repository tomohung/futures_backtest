"""H111 — 核心關係圖：dci_long score × ladder reach（W-50 @09:30，N=181）。

把假設的心臟畫出來：dci_long 分位 → 各關卡(L1–L5)達成率（全日 + forward），
外加連續散點 dci_long vs 擺幅比(up_full/EMA20) 疊關卡線。
用法：uv run python research/active/H111-dci-long-reach-map/dci_score_vs_reach.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PANEL = HERE / "results" / "reach_map_panel.csv"
U, K = "W50", "09:30"
LVL = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}
COL = {"L1": "#9467bd", "L2": "#1f77b4", "L3": "#2ca02c", "L4": "#ff7f0e", "L5": "#d62728"}


def main():
    df = pd.read_csv(PANEL)
    score = df[f"{U}_{K}"]
    df["exc"] = df["up_full"] / df["ema20"]
    df["q"] = pd.qcut(score, 5, labels=["Q1弱", "Q2", "Q3", "Q4", "Q5強"])

    full = {n: (df["up_full"] >= LVL[n] * df["ema20"]).astype(int) for n in LVL}
    fwd = {n: ((df[f"upsw_{K}"] < LVL[n] * df["ema20"]) & (df["up_full"] >= LVL[n] * df["ema20"])).astype(int)
           for n in LVL}

    # ── 表 ──
    print(f"dci_long({U}@{K}) 分位 × 關卡達成率（全日 / forward）  N={len(df)}")
    print(f"{'分位':<6}{'N':>4} | " + "".join(f"{n:>14}" for n in LVL))
    for q in ["Q1弱", "Q2", "Q3", "Q4", "Q5強"]:
        m = df["q"] == q
        cells = "".join(f"{full[n][m].mean():>6.0%}/{fwd[n][m].mean():>5.0%} " for n in LVL)
        print(f"{q:<6}{int(m.sum()):>4} | {cells}")
    print(f"{'base':<6}{len(df):>4} | " + "".join(f"{full[n].mean():>6.0%}/{fwd[n].mean():>5.0%} " for n in LVL))
    print("（格式 全日%/forward%）")

    # ── 圖 ──
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import sys
    sys.path.insert(0, str(HERE.parents[2]))
    try:
        from src.analysis.chart_style import setup_font
        setup_font()
    except Exception:
        pass

    qs = ["Q1弱", "Q2", "Q3", "Q4", "Q5強"]
    x = np.arange(5)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    for n in LVL:
        ax1.plot(x, [full[n][df["q"] == q].mean() for q in qs], "o-", color=COL[n], label=n, lw=1.8)
        ax2.plot(x, [fwd[n][df["q"] == q].mean() for q in qs], "o-", color=COL[n], label=n, lw=1.8)
    for ax, title in ((ax1, "全日達成率"), (ax2, "forward 達成率（t 之後才達）")):
        ax.set_xticks(x); ax.set_xticklabels(qs)
        ax.set_xlabel(f"dci_long ({U} @{K}) 分位"); ax.set_ylabel("達成率")
        ax.set_title(title); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_ylim(0, 1)

    # panel3：連續散點 + 關卡線
    ax3.scatter(score, df["exc"], s=14, alpha=0.5, color="#444")
    for n, c in LVL.items():
        ax3.axhline(c, color=COL[n], ls="--", lw=1, alpha=0.8)
        ax3.text(score.max(), c, f" {n}", color=COL[n], va="center", fontsize=8)
    r = np.corrcoef(score, df["exc"])[0, 1]
    ax3.set_xlabel(f"dci_long ({U} @{K})"); ax3.set_ylabel("上行擺幅 / EMA20")
    ax3.set_title(f"連續：dci vs 擺幅比（corr={r:+.3f}）"); ax3.grid(alpha=0.3)

    fig.suptitle(f"H111 — dci_long score × ladder reach（N={len(df)}，上市-only、forward-guarded）", fontsize=13)
    fig.tight_layout()
    out = HERE / "results" / "dci_score_vs_reach.png"
    fig.savefig(out, dpi=130)
    print(f"\n圖已存：{out}")


if __name__ == "__main__":
    main()

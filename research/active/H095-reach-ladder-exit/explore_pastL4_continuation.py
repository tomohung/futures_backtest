"""Phase 1 探索：碰 L4 之後的續航分佈（依 DCI 分帶）——校準 L4 分批比例。

背景：使用者「L4 照機率等比例出場」要的前瞻量是「**已站上 L4、還會續噴**」的機率，
不是 P(到達 L4)。本腳本定義延伸關卡 L5/L6/L7（沿用既有 c×EMA20 分位邏輯往外推），
算「碰 L4 後續到 L5/L6 的條件機率」與「碰 L4 後最終擺幅分佈」，多空分開、依 DCI 分帶。

關卡定義（與 daystats 同套）：方向性擺動 swing/causal-EMA20 的分位；
  達到率 τ 的關卡係數 c = quantile_{1−τ}(swing/EMA20)，pooled 多空。
  既有 L1–L4 = 90/75/50/25% 達到率；本腳本往外推 L5/L6/L7 = 12.5/6.25/3%。
條件機率：P(碰 L_{k+1} | 已碰 L4) = #(swing≥c_{k+1}) / #(swing≥c_L4)，同帶內（同一條擺動累積，與既有觸及語義一致）。
皆收盤/事後值（hindsight），與 dci_daily 對齊。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dci_reach_distribution_2026 import daily_dci, daily_reach

REACHES = [0.90, 0.75, 0.50, 0.25, 0.125, 0.0625, 0.03]
LABELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]


def build_ladder(reach: pd.DataFrame) -> dict[str, float]:
    """pooled 多空 swing/EMA20 的分位 → 各關卡係數 c。回 {label: c}。"""
    sn = np.concatenate([
        (reach["up_max"] / reach["ema20"]).to_numpy(),
        (reach["dn_max"] / reach["ema20"]).to_numpy(),
    ])
    return {lab: float(np.quantile(sn, 1 - r)) for lab, r in zip(LABELS, REACHES)}


def cond_table(df: pd.DataFrame, ladder: dict, side: str, tag: str):
    """side='short'→下擺/dci_short；'long'→上擺/dci_long。
    印：各 DCI 帶中『已碰 L4』樣本數 + P(續到 L5/L6/L7 | L4) + 碰L4後最終擺幅中位(EMA20倍)。"""
    sw = (df["dn_max"] if side == "short" else df["up_max"]) / df["ema20"]
    score = df["dci_short"] if side == "short" else df["dci_long"]
    cL4, cL5, cL6, cL7 = (ladder[x] for x in ("L4", "L5", "L6", "L7"))
    print(f"\n=== {tag}｜{'空方 dci_short≤−thr / 下擺' if side=='short' else '多方 dci_long≥+thr / 上擺'} ===")
    print(f"  關卡(c×EMA20): L4={cL4:.3f} L5={cL5:.3f} L6={cL6:.3f} L7={cL7:.3f}")
    print(f"  {'band':<10}{'到L4 N':>7}{'P(L5|L4)':>10}{'P(L6|L4)':>10}{'P(L7|L4)':>10}"
          f"{'碰L4後擺幅中位':>15}{'  → take=1−P(L5|L4)':>0}")

    def row(mask, lab):
        g = sw[mask]
        atL4 = g[g >= cL4]
        n = len(atL4)
        if n == 0:
            print(f"  {lab:<10}{0:>7}      —"); return
        p5 = (atL4 >= cL5).mean()
        p6 = (atL4 >= cL6).mean()
        p7 = (atL4 >= cL7).mean()
        med = float(atL4.median())
        take = 1 - p5
        print(f"  {lab:<10}{n:>7}{p5:>10.0%}{p6:>10.0%}{p7:>10.0%}{med:>13.2f}×"
              f"   先出≈{take:.0%}")

    if side == "short":
        row(score <= 999, "全部")
        for thr in (0.2, 0.3, 0.4, 0.5, 0.6):
            row(score <= -thr, f"≤−{thr}")
    else:
        row(score <= 999, "全部")
        for thr in (0.2, 0.3, 0.4, 0.5, 0.6):
            row(score >= thr, f"≥+{thr}")


def seg_table(df: pd.DataFrame, ladder: dict, side: str, tag: str):
    """逐段續航條件機率 P(L3|L2)/P(L4|L3)/P(L5|L4)，依 DCI 分帶。
    驗證多方「二分有效、細分無效」：L3→L4 在 0.2~0.4 vs ≥0.4 是否分離。"""
    sw = (df["dn_max"] if side == "short" else df["up_max"]) / df["ema20"]
    score = df["dci_short"] if side == "short" else df["dci_long"]
    cL2, cL3, cL4, cL5 = (ladder[x] for x in ("L2", "L3", "L4", "L5"))
    sgn = -1 if side == "short" else 1
    print(f"\n--- {tag}｜{'空' if side=='short' else '多'}方 逐段續航（條件機率）---")
    print(f"  {'band':<10}{'碰L2 N':>7}{'P(L3|L2)':>10}{'P(L4|L3)':>10}{'P(L5|L4)':>10}")

    def row(mask, lab):
        g = sw[mask]
        n2 = int((g >= cL2).sum()); n3 = int((g >= cL3).sum()); n4 = int((g >= cL4).sum())
        if not n2:
            print(f"  {lab:<10}{0:>7}      —"); return
        p3 = (g >= cL3).sum() / n2
        p4 = (g >= cL4).sum() / n3 if n3 else float("nan")
        p5 = (g >= cL5).sum() / n4 if n4 else float("nan")
        print(f"  {lab:<10}{n2:>7}{p3:>10.0%}{p4:>10.0%}{p5:>10.0%}  (到L3 {n3}, 到L4 {n4})")

    row(score * sgn >= -999, "全部")
    row((score * sgn >= 0.2) & (score * sgn < 0.4), "0.2~0.4")
    row(score * sgn >= 0.4, "≥0.4")


def main():
    reach = daily_reach()
    ladder = build_ladder(reach)
    print("延伸關卡係數（pooled 多空, 全樣本擬合）達到率→c×EMA20:")
    for lab, r in zip(LABELS, REACHES):
        print(f"  {lab} 達到率{r*100:>5.2f}%  c={ladder[lab]:.3f}")

    flags_cols = pd.DataFrame({"up_max": reach["up_max"], "dn_max": reach["dn_max"],
                               "ema20": reach["ema20"]})
    dci = daily_dci()
    df = flags_cols.join(dci, how="inner").dropna()

    for tag, d in (("全樣本2021-2026", df), ("2026", df[df.index.year == 2026])):
        print("\n" + "=" * 86)
        print(f"  {tag}  N={len(d)}")
        cond_table(d, ladder, "short", tag)
        cond_table(d, ladder, "long", tag)
        seg_table(d, ladder, "long", tag)
        seg_table(d, ladder, "short", tag)


if __name__ == "__main__":
    main()

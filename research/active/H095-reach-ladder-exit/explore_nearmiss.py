"""H095 — 瞄 L2 時的「差一點/回吐」問題量化。

情境：碰 L1（瞄 L2），但行情沒到 L2 就回吐，甚至當日高點差一點碰不到 L2。
先量化兩件事，作為出場規則設計依據：
  (1) P(到 L2 | 碰 L1)，以及沒到的那批「填了 L1→L2 間距的幾成」分佈（near-miss vs 真停滯）。
  (2) 不同 buffer（差 L2 幾點內就算到）下，碰 L1 後「實質達標率」會拉高多少。

關卡 EMA-only：L1=0.385×EMA20, L2=0.497×EMA20（H097）。directional swing, pooled 多空對稱。
注意：此處用全日最大擺動(MFE)，衡量「最遠摸到哪」，非逐 bar 出場模擬。
"""

from __future__ import annotations

import numpy as np
from explore import build_dataset

C_L1, C_L2 = 0.385, 0.497


def main():
    df = build_dataset()
    ema = df["ema"].to_numpy()
    swing = df["swing"].to_numpy()
    L1 = C_L1 * ema
    L2 = C_L2 * ema
    gap = L2 - L1  # L1→L2 間距(點)

    touched_l1 = swing >= L1
    reached_l2 = swing >= L2
    n1 = touched_l1.sum()
    print(f"樣本 {len(df)} (day×dir)，碰 L1 = {n1} ({n1/len(df):.0%})")
    print(f"L1→L2 間距(點)：中位 {np.median(gap[touched_l1]):.0f}，"
          f"p25 {np.percentile(gap[touched_l1],25):.0f}，p75 {np.percentile(gap[touched_l1],75):.0f}\n")

    print(f"P(到 L2 | 碰 L1) = {reached_l2[touched_l1].mean():.0%}")

    # 沒到 L2 的那批：填了 L1→L2 間距的幾成
    miss = touched_l1 & ~reached_l2
    filled = ((swing[miss] - L1[miss]) / gap[miss]).clip(0, 1)
    print(f"\n沒到 L2 的 {miss.sum()} 筆，填了 L1→L2 間距的比例分佈：")
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0)]:
        c = ((filled >= lo) & (filled < hi)).sum() if hi < 1.0 else ((filled >= lo) & (filled <= hi)).sum()
        print(f"  填 {int(lo*100):>3}–{int(hi*100):>3}%：{c:>4} 筆 ({c/miss.sum():.0%})")
    print(f"  中位填補 {np.median(filled):.0%}，其中『摸到 ≥80% 間距』(差一點) 佔 {(filled>=.8).mean():.0%}")

    # buffer：差 L2 幾點內就算「實質達標」
    print(f"\n碰 L1 後『實質達標率』隨 buffer 變化（buffer = L2 往下幾點/或幾成間距）：")
    print(f"{'buffer':>10}{'達標率':>10}  (vs 嚴格到 L2)")
    for frac in [0.0, 0.1, 0.2, 0.3, 0.5]:
        thr = L2 - frac * gap
        rate = (swing[touched_l1] >= thr[touched_l1]).mean()
        med_pts = np.median((frac * gap)[touched_l1])
        print(f"{f'{int(frac*100)}%間距':>10}{rate:>10.0%}  (≈{med_pts:.0f}點)")


if __name__ == "__main__":
    main()

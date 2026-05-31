"""H095 — near-miss / 回吐 量化，L1→L2 與 L2→L3 兩段對照。

對每一段 (起點階, 目標階)：在「已碰起點階」的樣本中，量化
  P(到目標階)、起→目標間距(點)、沒到那批填補比例分佈、加 buffer 後實質達標率。
關卡 EMA-only：L1=0.385 L2=0.497 L3=0.711（×EMA20）。directional swing, pooled 多空對稱。
※ 全日最大擺動(MFE)，非逐 bar 出場模擬。
"""

from __future__ import annotations

import numpy as np
from explore import build_dataset

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}


def analyse(df, start, target):
    ema = df["ema"].to_numpy()
    swing = df["swing"].to_numpy()
    s_dist, t_dist = C[start] * ema, C[target] * ema
    gap = t_dist - s_dist
    at_start = swing >= s_dist
    reached = swing >= t_dist
    n = at_start.sum()
    print(f"\n══════ {start} → {target} ══════")
    print(f"已碰 {start} = {n} 筆；{start}→{target} 間距(點)：中位 {np.median(gap[at_start]):.0f}"
          f"（p25 {np.percentile(gap[at_start],25):.0f} / p75 {np.percentile(gap[at_start],75):.0f}）")
    print(f"P(到 {target} | 碰 {start}) = {reached[at_start].mean():.0%}")

    miss = at_start & ~reached
    filled = ((swing[miss] - s_dist[miss]) / gap[miss]).clip(0, 1)
    print(f"沒到 {target} 的 {miss.sum()} 筆，填補 {start}→{target} 間距比例：", end="")
    parts = []
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0)]:
        c = ((filled >= lo) & ((filled < hi) if hi < 1 else (filled <= hi))).sum()
        parts.append(f"{int(lo*100)}-{int(hi*100)}%:{c/miss.sum():.0%}")
    print("  ".join(parts))
    print(f"  中位填補 {np.median(filled):.0%}；差一點(≥80%) 佔 {(filled>=.8).mean():.0%}")

    print(f"  加 buffer 後實質達標率：", end="")
    segs = []
    for frac in [0.0, 0.2, 0.3, 0.5]:
        thr = t_dist - frac * gap
        rate = (swing[at_start] >= thr[at_start]).mean()
        pts = np.median((frac * gap)[at_start])
        segs.append(f"{int(frac*100)}%間距(≈{pts:.0f}點)={rate:.0%}")
    print("  ".join(segs))


def main():
    df = build_dataset()
    print(f"樣本 {len(df)} (day×dir)，{df['d'].min().date()}~{df['d'].max().date()}")
    analyse(df, "L1", "L2")
    analyse(df, "L2", "L3")


if __name__ == "__main__":
    main()

"""H118 補：強度鑑別度 — 0050期(NYF)/CDF 延伸強弱 → 多 L3/L4/L5 達成率。

回答使用者原始問題：
  「延伸強/弱時，L3/L4/L5 達成率能不能分開？ext_long 的『強=0.16』換成 0050 還成立嗎？」

不做 P&L。純看：強度分桶（五分位 + 固定門檻）→ forward 上行 reach 達成率。
forward reach 嚴格取「讀數時點 t 之後」避免 tautology。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explore import DB, LADDERS, PREOPEN_MIN_TICKS, aux_ext, tx_features

EXT_STRONG_LONG = 0.16   # cash ext_long 的「強」門檻（extension.py）


def reach_rates(ext: pd.Series, tx: pd.DataFrame, T: str) -> None:
    pass


def analyze(p, sym_label, panel, tx, T):
    col = f"ext_{T}"
    if col not in panel.columns:
        p(f"  {sym_label} @{T}: 無此時點"); return
    df = pd.concat([panel[col].rename("e"),
                    tx[f"reach_{T}"].rename("reach")], axis=1).dropna()
    n = len(df)
    p(f"\n--- {sym_label} 延伸@{T}（N={n}）→ forward 上行 reach 達成率 ---")
    # 延伸分佈（讓你知道「強」在哪）
    qs = df["e"].quantile([.1, .25, .5, .75, .9, .95]).round(3)
    p(f"  延伸分佈 q10/25/50/75/90/95 = {list(qs.values)}")

    base = {k: (df['reach'] >= v).mean() for k, v in LADDERS.items()}
    p(f"  base 達成率: L3={base['L3']:.0%} L4={base['L4']:.0%} L5={base['L5']:.0%}")

    # 五分位分桶 → 達成率（看單調分離）
    p(f"  {'五分位':>8} {'N':>4} {'延伸範圍':>16} | {'L3':>6} {'L4':>6} {'L5':>6}")
    # 用 rank 避免重複值（CDF 多 0.0）導致 bin edge 重複
    df["q"] = pd.qcut(df["e"].rank(method="first"), 5,
                      labels=["Q1弱", "Q2", "Q3", "Q4", "Q5強"])
    for q, g in df.groupby("q", observed=True):
        rng = f"[{g['e'].min():+.2f},{g['e'].max():+.2f}]"
        r = {k: (g['reach'] >= v).mean() for k, v in LADDERS.items()}
        p(f"  {q:>8} {len(g):>4} {rng:>16} | {r['L3']:>5.0%} {r['L4']:>5.0%} {r['L5']:>5.0%}")

    # 固定門檻（回答「0.1/0.16 算強嗎」）
    p(f"  -- 固定門檻達成率 vs base --")
    for th in [0.0, 0.05, 0.10, EXT_STRONG_LONG, 0.20, 0.30]:
        g = df[df["e"] >= th]
        if len(g) < 20:
            p(f"   ext≥{th:>4}: N={len(g)} 不足"); continue
        r = {k: (g['reach'] >= v).mean() for k, v in LADDERS.items()}
        lift4 = r['L4'] / base['L4'] if base['L4'] > 0 else np.nan
        p(f"   ext≥{th:>4}: N={len(g):>4} | L3={r['L3']:>4.0%} L4={r['L4']:>4.0%}"
          f"(lift {lift4:.1f}×) L5={r['L5']:>4.0%}")


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        tx = tx_features(conn)
        A = aux_ext(conn, "NYF"); B = aux_ext(conn, "CDF")
        Ag = A[A["preticks"] >= PREOPEN_MIN_TICKS]
        Bg = B[B["preticks"] >= PREOPEN_MIN_TICKS]
        p("=== H118 強度鑑別度：延伸強弱 → 多 L3/L4/L5 達成率 ===")
        p(f"NYF 流動性gate後 N={len(Ag)}；CDF N={len(Bg)}")
        p("（forward reach 取讀數時點之後，避免 tautology）")

        for T in ["08:55", "09:00", "09:15"]:
            p(f"\n############ 時點 T={T} ############")
            analyze(p, "A=NYF(0050期)", Ag, tx, T)
            analyze(p, "B=CDF(台積電)", Bg, tx, T)

    with open("research/active/H118-nyf-preopen-reach/results/strength_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/strength_raw.txt")


if __name__ == "__main__":
    main()

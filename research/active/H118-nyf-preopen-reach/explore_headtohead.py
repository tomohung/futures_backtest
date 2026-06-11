"""H118 補強：三方『同日』head-to-head（釘死 H2/H3，排除樣本差異）。

限定 A=NYF(盤前流動性gate) ∩ B=CDF(gate) ∩ C=cash(W10) ∩ TX 都有值的**同一批日**，
在各時點重算 corr(ext@T, forward L3/L4/L5 reach)。這樣 A/B/C 比在完全相同的日子上。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explore import (DB, LADDERS, PREOPEN_MIN_TICKS, TIMES, aux_ext, cash_ext,
                     corr_lift, tx_features)


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        tx = tx_features(conn)
        A = aux_ext(conn, "NYF"); B = aux_ext(conn, "CDF")
        Ag = A[A["preticks"] >= PREOPEN_MIN_TICKS]
        Bg = B[B["preticks"] >= PREOPEN_MIN_TICKS]
        cash = cash_ext(conn, sorted(set(A.index) & set(tx.index)))

        common = (Ag.index.intersection(Bg.index)
                    .intersection(cash.index).intersection(tx.index))
        common = pd.Index(sorted(common))
        p("=== H118 同日 head-to-head（A=NYF / B=CDF / C=cash W10）===")
        p(f"三方同日有效樣本：N={len(common)}（{common.min()} ~ {common.max()}）")
        p("（限 NYF&CDF 盤前達流動性門檻、cash 有 stock_min、TX 有 reach 的同一批日）")

        for lad, thr in LADDERS.items():
            p(f"\n=== {lad}：同日 corr(ext@T, forward {lad}) ｜ base→top20% lift ===")
            p(f"{'T':>6} | {'A_NYF':>20} | {'B_CDF':>20} | {'C_cash':>20}")
            for T in TIMES:
                row = []
                for panel in (Ag, Bg, cash):
                    col = f"ext_{T}"
                    if col not in panel.columns:
                        row.append(f"{'—(盤前無cash)':>20}"); continue
                    n, c, base, top = corr_lift(
                        panel.loc[common, col], tx.loc[common, f"reach_{T}"], thr)
                    row.append(f"{c:+.3f} {base:.0%}→{top:.0%}" if not np.isnan(c)
                               else f"{'NA':>20}")
                p(f"{T:>6} | {row[0]:>20} | {row[1]:>20} | {row[2]:>20}")

        # 勝者統計：09:00–09:30 每時點 L4 誰 corr 最高
        p("\n=== 09:00–09:30 各時點 L4 corr 勝者（同日）===")
        wins = {"A_NYF": 0, "B_CDF": 0, "C_cash": 0}
        for T in [t for t in TIMES if t >= "09:00"]:
            vals = {}
            for name, panel in [("A_NYF", Ag), ("B_CDF", Bg), ("C_cash", cash)]:
                _, c, _, _ = corr_lift(panel.loc[common, f"ext_{T}"],
                                       tx.loc[common, "reach_" + T], 0.977)
                vals[name] = c
            w = max(vals, key=vals.get)
            wins[w] += 1
            p(f"  {T}: " + "  ".join(f"{k}={v:+.3f}" for k, v in vals.items()) + f"   勝={w}")
        p(f"  → 勝場數：{wins}")

    with open("research/active/H118-nyf-preopen-reach/results/headtohead_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/headtohead_raw.txt")


if __name__ == "__main__":
    main()

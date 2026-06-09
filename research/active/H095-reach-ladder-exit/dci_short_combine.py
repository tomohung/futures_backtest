"""空方訊號合成：寬權值 thrust（帶幅度）+ B 家數（純計數）是否互補（Phase-1）。

讀 dci_universe_panel.csv（同一批 181 天、09:30 快照），不重算。
空方力道（正向=預測下行延伸）：
  s_thr = −(W-100 thrust)   寬權值幅度
  s_B   = −(B 家數)
合成（兩種）：
  z-sum  : z(s_thr)+z(s_B)  等權、不擬合（誠實基準）
  α-grid : α·z(s_thr)+(1−α)·z(s_B) 掃 α，找最佳 r（**in-sample，會高估**）
評估：r(,dn_L4)、AUC（Mann-Whitney）、兩者相關、tercile×tercile 命中格。
用法：uv run python research/active/H095-reach-ladder-exit/dci_short_combine.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).parent / "results"
WIDE = "W-100_09:30"   # 寬權值 thrust 代表（W-50 近似，文末附）


def z(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std()


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def auc(score, y):
    """二元 y 的 AUC = P(score|y=1 > score|y=0)，用 rank（Mann-Whitney）。"""
    score, y = np.asarray(score, float), np.asarray(y, int)
    pos, neg = score[y == 1], score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    r = pd.Series(score).rank().values
    return float((r[y == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def line(name, score, y):
    return f"  {name:<22} r={pb(score, y):+.3f}  AUC={auc(score, y):.3f}"


def main(wide=WIDE):
    df = pd.read_csv(RES / "dci_universe_panel.csv")
    y = df["dn_L4"].values
    base = y.mean()
    s_thr = -df[wide]        # 寬權值幅度（空方力道）
    s_B = -df["B_09:30"]     # 家數（空方力道）

    L = ["=" * 72,
         f"空方合成：{wide}（寬權值幅度）+ B 家數 → dn_L4   N={len(df)}  上市-only",
         f"dn_L4 達標率(base)={base:.1%}　兩力道相關 corr(s_thr,s_B)={pb(s_thr, s_B):+.3f}",
         "-" * 72,
         "單一：",
         line("s_thr (寬權值幅度)", s_thr, y),
         line("s_B   (家數)", s_B, y),
         "合成：",
         line("z-sum 等權(不擬合)", z(s_thr) + z(s_B), y)]

    # α-grid（in-sample，會高估）
    best = (-1, None)
    for a in np.linspace(0, 1, 21):
        sc = a * z(s_thr) + (1 - a) * z(s_B)
        r = pb(sc, y)
        if r > best[0]:
            best = (r, a)
    aopt = best[1]
    L.append(f"  α-grid 最佳 α={aopt:.2f}（s_thr 權重）  r={best[0]:+.3f}  "
             f"AUC={auc(aopt*z(s_thr)+(1-aopt)*z(s_B), y):.3f}  [in-sample，高估]")

    # tercile × tercile 命中格（看互補性）
    L.append("-" * 72)
    L.append("tercile × tercile dn_L4 命中率（列=s_thr 強度↑，欄=s_B 強度↑；[命中率,n]）：")
    tt = pd.DataFrame({"s_thr": s_thr.values, "s_B": s_B.values, "y": y})
    tt["bt"] = pd.qcut(tt["s_thr"], 3, labels=["低", "中", "高"])
    tt["bb"] = pd.qcut(tt["s_B"], 3, labels=["低", "中", "高"])
    grid = tt.groupby(["bt", "bb"], observed=True)["y"].agg(["mean", "count"])
    L.append(f"{'':<8}{'B低':>12}{'B中':>12}{'B高':>12}")
    for bt in ["低", "中", "高"]:
        cells = []
        for bb in ["低", "中", "高"]:
            try:
                m, n = grid.loc[(bt, bb)]
                cells.append(f"[{m:.0%},n{int(n)}]")
            except KeyError:
                cells.append("    -   ")
        L.append(f"thr{bt:<5}" + "".join(f"{c:>12}" for c in cells))
    L.append("  （若『兩者皆高』那格命中率明顯高於各自單高 → 互補；若沿單軸就決定 → 重疊）")

    # 對照：W-50 是否結論一致
    L.append("-" * 72)
    s_thr50 = -df["W-50_09:30"]
    L.append("對照 W-50：" + line("z-sum(W-50)+B", z(s_thr50) + z(s_B), y).strip())

    txt = "\n".join(L)
    print(txt)
    (RES / "dci_short_combine.txt").write_text(txt + "\n")
    print(f"\n存：{RES/'dci_short_combine.txt'}")


if __name__ == "__main__":
    main()

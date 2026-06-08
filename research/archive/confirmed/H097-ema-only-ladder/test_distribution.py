"""H097 後續 — 關卡價分佈比較 + 夜盤校正幅度 vs 關卡間距。

問題：簡化成 EMA-only 後，(1) 每階關卡距離的分佈是否跟雙參數一致？
(2) 夜盤校正的典型幅度，是否小於『跳一個關卡』的間距？若是 → 夜盤只在同一關卡帶內微調，
跳格(換 tier)比夜盤校正更有決策意義，支持簡化。

沿用 explore.py 的資料與擬合。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from explore import TIERS, build_dataset, fit_quantile

pd.set_option("display.width", 200)


def pct(s, qs=(10, 25, 50, 75, 90)):
    return {f"p{q}": round(float(np.percentile(s, q))) for q in qs}


def main():
    df = build_dataset()
    y = df["swing"].to_numpy()
    XA = df[["night", "ema"]].to_numpy()
    XB = df[["ema"]].to_numpy()

    # 擬合兩模型（全樣本，與 explore 一致）
    coefA, coefB = {}, {}
    for lvl, reach, tau in TIERS:
        coefA[lvl] = fit_quantile(y, XA, tau)
        coefB[lvl] = fit_quantile(y, XB, tau)

    night = df["night"].to_numpy()
    ema = df["ema"].to_numpy()

    # 每日每階距離（點數）
    A = {lvl: coefA[lvl][0] * night + coefA[lvl][1] * ema for lvl, _, _ in TIERS}
    B = {lvl: coefB[lvl][0] * ema for lvl, _, _ in TIERS}

    print("=== (1) 每階關卡『距離(點)』分佈：雙參數 A vs EMA-only B ===")
    print(f"{'階':<4}{'模型':<4}{'p10':>6}{'p25':>6}{'p50':>6}{'p75':>6}{'p90':>6}{'mean':>7}")
    for lvl, reach, _ in TIERS:
        for name, D in (("A", A[lvl]), ("B", B[lvl])):
            p = pct(D)
            print(f"{lvl:<4}{name:<4}{p['p10']:>6}{p['p25']:>6}{p['p50']:>6}{p['p75']:>6}"
                  f"{p['p90']:>6}{round(D.mean()):>7}")
        # 兩模型每日距離差的相關 + 中位絕對差
        d = A[lvl] - B[lvl]
        r = np.corrcoef(A[lvl], B[lvl])[0, 1]
        print(f"     A,B 每日距離相關={r:.3f}  中位|A−B|={np.median(np.abs(d)):.0f}點  "
              f"p90|A−B|={np.percentile(np.abs(d),90):.0f}點")
        print()

    print("=== (2) 夜盤校正幅度 vs 關卡間距（核心問題）===")
    # 夜盤校正 = A − B（每日、每階，點數）
    # 關卡間距(EMA-only) = B[next] − B[this]
    order = [t[0] for t in TIERS]
    print(f"{'階':<4}{'中位|夜盤校正|':>12}{'p90|夜盤校正|':>13}  | "
          f"{'到下階間距(中位)':>16}{'校正/間距(中位)':>16}{'校正>間距 比例':>15}")
    for i, lvl in enumerate(order):
        corr = np.abs(A[lvl] - B[lvl])
        med_c, p90_c = np.median(corr), np.percentile(corr, 90)
        if i < len(order) - 1:
            gap = B[order[i + 1]] - B[lvl]          # 跳到下一階的間距(EMA-only)
            med_gap = np.median(gap)
            ratio = np.median(corr / gap)
            frac = np.mean(corr > gap)
            print(f"{lvl:<4}{med_c:>12.0f}{p90_c:>13.0f}  | {med_gap:>16.0f}"
                  f"{ratio:>16.2f}{frac:>14.0%}")
        else:
            print(f"{lvl:<4}{med_c:>12.0f}{p90_c:>13.0f}  | {'(最高階)':>16}")

    print("\n→ 『校正/間距』中位 < 1 且『校正>間距比例』低 = 夜盤校正多半跳不過一個關卡 → 簡化合理。")

    # (3) 幾個具體日子的兩種階梯（從今低往上投射，需當日 low；這裡只比距離與今高/低無關）
    print("\n=== (3) 具體日子：兩模型的關卡『距離(點)』 ===")
    df2 = df.drop_duplicates("d").set_index("d")  # 每日 night/ema（多空同值）
    for ds in ["2025-05-15", "2026-04-24", "2026-05-27"]:
        d = pd.Timestamp(ds)
        if d not in df2.index:
            continue
        nr, e20 = df2.loc[d, "night"], df2.loc[d, "ema"]
        la = [round(coefA[l][0] * nr + coefA[l][1] * e20) for l, _, _ in TIERS]
        lb = [round(coefB[l][0] * e20) for l, _, _ in TIERS]
        print(f"{ds} 夜盤={nr:.0f} EMA20={e20:.0f}")
        print(f"   雙參數 A: L1-4 = {la}")
        print(f"   EMA-only B: L1-4 = {lb}")


if __name__ == "__main__":
    main()

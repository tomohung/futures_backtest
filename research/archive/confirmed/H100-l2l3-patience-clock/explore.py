"""H100 Phase 1 — L2→L3 放棄時鐘（強 DCI 放寬閘的上限）

母體：H095 乾淨 EstHL(long-only)、守初始SL、**碰 L2 且 L2 前未停損** 的單。
對每筆記錄 t2(碰L2)、t3(碰L3)、tstop(觸初始SL)、dci_long。

核心問題（條件存活）：在時刻 T 仍「存活等待」(碰L2、未碰L3、未停損)者，
其最終仍碰到 L3 的條件機率 P(到L3 | 存活@T) 如何隨 T 衰減？強帶是否也有上限 T*？

純探索、無回測。沿用 H095 階梯/進場定義。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "H099-time-axis-exit"))  # noqa
sys.path.insert(0, str(Path(__file__).parent.parent / "H095-reach-ladder-exit"))
from phase2_path_backtest import C, SL_FRAC, build_entries  # noqa: E402
from dci_reach_distribution_2026 import daily_dci  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402

# 放棄時鐘網格（分鐘 of day）；08:45=525 10:45=645 11:30=690 12:20=740 13:45=825
T_GRID = [("10:00", 600), ("10:45", 645), ("11:00", 660), ("11:30", 690),
          ("12:00", 720), ("12:20", 740), ("12:45", 765)]
BANDS = [("強 ≥+0.2", lambda d: d >= 0.2),
         ("中 −0.1~+0.2", lambda d: -0.1 <= d < 0.2),
         ("弱 <−0.1", lambda d: d < -0.1),
         ("全部", lambda d: True)]


def path_marks(day, ei, base, emahl, ema20):
    """守初始SL。回傳 (t2, t3, tstop)；分鐘 of day 或 None。L2 前停損→t2=None(不入母體)。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    L2 = base + C["L2"] * ema20
    L3 = base + C["L3"] * ema20
    entry = c[ei]
    sl = entry - SL_FRAC * emahl
    t2 = t3 = tstop = None
    n = len(h)
    for j in range(ei + 1, n):
        if l[j] <= sl:                       # SL 先檢（與 H095 l3_exit 同慣例）
            tstop = int(mins[j])
            break
        if t2 is None and h[j] >= L2:
            t2 = int(mins[j])
        if h[j] >= L3:
            t3 = int(mins[j])
            break                            # 到 L3 → 這條腿結束
    return t2, t3, tstop


def alive_waiting(r, T):
    """T 時刻：已碰 L2、未碰 L3、未停損 → 存活等待中。"""
    return (r["t2"] is not None and r["t2"] <= T
            and (r["t3"] is None or r["t3"] > T)
            and (r["tstop"] is None or r["tstop"] > T))


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    dci = daily_dci()
    lut = {ts.date(): float(v) for ts, v in dci["dci_long"].items()}

    rows = []
    for e in entries:
        t2, t3, tstop = path_marks(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"])
        if t2 is None:
            continue                         # 沒碰 L2（含 L2 前停損）→ 不入母體
        rows.append({"date": e["date"], "t2": t2, "t3": t3, "tstop": tstop,
                     "dci": lut.get(e["date"], np.nan)})
    print(f"乾淨 EstHL 進場：{len(entries)} 筆")
    print(f"L2-reacher 母體（守初始SL 碰 L2）：{len(rows)} 筆\n")

    def report(pool, tag):
        print(f"================ {tag}　(N={len(pool)}) ================")
        for blab, bf in BANDS:
            band = [r for r in pool if (not np.isnan(r["dci"])) and bf(r["dci"])]
            if not band:
                continue
            reached = sum(r["t3"] is not None for r in band)
            base_p = reached / len(band)
            print(f"\n  [{blab}]  N={len(band)}  無條件 P(到L3|碰L2)={base_p:.0%}  "
                  f"(到L3 {reached}、停損/EOD未到 {len(band)-reached})")
            print(f"    {'存活等待@T':<12} {'存活N':>6} {'之後仍到L3':>10} {'P(到L3|存活)':>12}")
            for tlab, T in T_GRID:
                alive = [r for r in band if alive_waiting(r, T)]
                if not alive:
                    print(f"    {tlab:<12} {0:>6}")
                    continue
                later = sum(r["t3"] is not None for r in alive)  # t3>T 必然
                print(f"    {tlab:<12} {len(alive):>6} {later:>10} {later/len(alive):>11.0%}")

    report(rows, "全期 2021–2026")
    for period, mask in [("OOS train ≤2024", lambda d: d.year <= 2024),
                         ("OOS test ≥2025", lambda d: d.year >= 2025)]:
        report([r for r in rows if mask(r["date"])], period)

    # 圖：強/中帶 P(到L3|存活@T) vs T
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4.5))
        xs = [t for _, t in T_GRID]
        xl = [lab for lab, _ in T_GRID]
        for blab, bf, col in [("strong >=+0.2", lambda d: d >= 0.2, "#c0392b"),
                              ("mid -0.1~+0.2", lambda d: -0.1 <= d < 0.2, "#2980b9"),
                              ("all", lambda d: True, "#7f8c8d")]:
            band = [r for r in rows if (not np.isnan(r["dci"])) and bf(r["dci"])]
            ys, ns = [], []
            for _, T in T_GRID:
                alive = [r for r in band if alive_waiting(r, T)]
                ns.append(len(alive))
                ys.append(sum(r["t3"] is not None for r in alive) / len(alive)
                          if alive else np.nan)
            ax.plot(xs, ys, "o-", color=col, label=blab)
            for x, y, nn in zip(xs, ys, ns):
                if not np.isnan(y):
                    ax.text(x, y + 0.015, f"{nn}", ha="center", fontsize=7, color=col)
        ax.set_xticks(xs)
        ax.set_xticklabels(xl, rotation=15)
        ax.set_ylim(0, 1)
        ax.set_ylabel("P(reach L3 | still waiting at T)")
        ax.set_title("H100: L2->L3 patience clock by DCI (long, 2021-2026; numbers=alive N)")
        ax.legend()
        fig.tight_layout()
        out = Path(__file__).parent / "results" / "patience_clock.png"
        fig.savefig(out, dpi=130)
        print(f"\n圖已存：{out}")
    except Exception as ex:
        print(f"\n[繪圖略過] {ex}")


if __name__ == "__main__":
    main()

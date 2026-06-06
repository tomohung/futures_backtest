"""H095 — 10:45 時間閘敏感度：把 H100 放棄時鐘補上 10:15/10:30 細格。

問題：把時間停損/L2 閘從 10:45 改 10:30，落在「62%→36% 斷崖」的哪裡？
  P(最終到 L3 | 在時刻 T 仍存活等待＝碰 L2、未碰 L3、未停損)。
  此 P 越高 → 在該 T 啟動 trail / 改守 L2 洗掉越多「其實還會到 L3」的單。

母體與定義完全沿用 H100（守初始SL 的 L2-reacher）。純探索、無回測。
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from phase2_path_backtest import C, SL_FRAC, build_entries  # noqa: E402
from dci_reach_distribution_2026 import daily_dci  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402

# 細格：09:30=570 09:45=585 10:00=600 10:15=615 10:30=630 10:45=645 11:00=660 11:30=690
T_GRID = [("09:30", 570), ("09:45", 585), ("10:00", 600), ("10:15", 615),
          ("10:30", 630), ("10:45", 645), ("11:00", 660), ("11:30", 690)]
BANDS = [("全部", lambda d: True),
         ("強 ≥+0.2", lambda d: d >= 0.2),
         ("中 −0.1~+0.2", lambda d: -0.1 <= d < 0.2),
         ("弱 <−0.1", lambda d: d < -0.1)]


def path_marks(day, ei, base, emahl, ema20):
    """守初始SL。回傳 (t2, t3, tstop)；L2 前停損→t2=None。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    L2, L3 = base + C["L2"] * ema20, base + C["L3"] * ema20
    sl = c[ei] - SL_FRAC * emahl
    t2 = t3 = tstop = None
    for j in range(ei + 1, len(h)):
        if l[j] <= sl:
            tstop = int(mins[j]); break
        if t2 is None and h[j] >= L2:
            t2 = int(mins[j])
        if h[j] >= L3:
            t3 = int(mins[j]); break
    return t2, t3, tstop


def alive(r, T):
    return (r["t2"] is not None and r["t2"] <= T
            and (r["t3"] is None or r["t3"] > T)
            and (r["tstop"] is None or r["tstop"] > T))


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    lut = {ts.date(): float(v) for ts, v in daily_dci()["dci_long"].items()}

    rows = []
    for e in entries:
        t2, t3, tstop = path_marks(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"])
        if t2 is None:
            continue
        rows.append({"date": e["date"], "t2": t2, "t3": t3, "tstop": tstop,
                     "dci": lut.get(e["date"], np.nan)})
    print(f"L2-reacher 母體（守初始SL 碰 L2）：{len(rows)} 筆\n")

    for blab, bf in BANDS:
        band = [r for r in rows if (not np.isnan(r["dci"])) and bf(r["dci"])]
        if not band:
            continue
        reached = sum(r["t3"] is not None for r in band)
        print(f"[{blab}]  N={len(band)}  無條件 P(到L3|碰L2)={reached/len(band):.0%}")
        print(f"    {'存活@T':<8}{'存活N':>6}{'仍到L3':>8}{'P(到L3|存活)':>13}   斷崖Δ")
        prev = None
        for tlab, T in T_GRID:
            a = [r for r in band if alive(r, T)]
            if not a:
                print(f"    {tlab:<8}{0:>6}"); continue
            p = sum(r["t3"] is not None for r in a) / len(a)
            delta = f"{(p-prev)*100:+.0f}pp" if prev is not None else "—"
            star = "  ← 10:30(新閘)" if tlab == "10:30" else ("  ← 10:45(舊閘)" if tlab == "10:45" else "")
            print(f"    {tlab:<8}{len(a):>6}{sum(r['t3'] is not None for r in a):>8}{p:>12.0%}   {delta}{star}")
            prev = p
        print()


if __name__ == "__main__":
    main()

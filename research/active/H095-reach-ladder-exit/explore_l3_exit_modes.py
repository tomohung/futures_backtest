"""H095 — 碰 L3 之後的出場模式對決：靜態 vs 5MA-from-L3 vs Dow-from-L3

承 v4 鐵律「碰 L3 前守初始SL 完全不動」。本腳本把 trail 起點改成**碰 L3 才啟動**,
在 L3 這個點直接對打三模式,回答兩問:
  ① 5MA 在 L3 是否被支配?(靜態贏平均 & Dow 贏長尾 → 5MA 兩頭不到岸 = 多餘)
  ② trail-from-L3(Dow)相對靜態的增益,是否全來自 L4 級長尾?(砍 top-3 看翻不翻盤)

關鍵:三模式只在『碰 L3 之後』分歧;沒到 L3 的單三者完全相同(守初始SL 抱到 EOD)。
故 **L3-reachers-only** 區塊是決定性對比;全期區塊的模式差異 = 同一批 L3 單造成。
進場 = phase2_path_backtest 的乾淨 EstHL(long-only)。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from phase2_path_backtest import C, SL_FRAC, build_entries, pivot_low_trail, sma  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402


def l3_exit(day, ei, base, emahl, ema20, entry, mode):
    """守初始SL 抱到 L3,碰 L3 後依 mode 出場。回傳 (pnl, reached_l3, reason)。"""
    h, l, c = day["High"], day["Low"], day["Close"]
    L3 = base + C["L3"] * ema20
    sl = entry - SL_FRAC * emahl
    n = len(h)

    # 守初始SL 找 L3(過程中觸 SL = 該單在 L3 前就死,三模式同)
    j3 = None
    for j in range(ei + 1, n):
        if l[j] <= sl:
            return sl - entry, False, "stop_preL3"
        if h[j] >= L3:
            j3 = j
            break
    if j3 is None:
        return c[n - 1] - entry, False, "eod_preL3"   # 沒到 L3,抱到收盤

    if mode == "static":
        return L3 - entry, True, "static_L3"

    if mode == "5ma":
        ma5 = sma(c)
        for k in range(j3, n):
            if l[k] <= sl:
                return sl - entry, True, "sl"
            if not np.isnan(ma5[k]) and c[k] < ma5[k]:
                return c[k] - entry, True, "5ma"
        return c[n - 1] - entry, True, "eod"

    if mode == "dow":
        pl = pivot_low_trail(l)
        stop = sl
        for k in range(j3, n):
            if pl[k] > stop:
                stop = pl[k]
            if l[k] <= stop:
                return stop - entry, True, "dow"
        return c[n - 1] - entry, True, "eod"

    raise ValueError(mode)


def run(entries, mode, mask=None):
    out = []
    for e in entries:
        if mask and not mask(e["date"]):
            continue
        pnl, r3, reason = l3_exit(e["day"], e["ei"], e["base"], e["emahl"],
                                  e["ema20"], e["entry"], mode)
        out.append({"pnl": pnl, "pnl_pct": pnl / e["entry"] * 100,
                    "r3": r3, "reason": reason})
    return out


def stat_line(rows, label):
    if not rows:
        print(f"  {label}: 無"); return
    pts = np.array([r["pnl"] for r in rows])
    pct = np.array([r["pnl_pct"] for r in rows])
    win = pts > 0
    top3 = np.sort(pts)[-3:].sum()
    print(f"  {label:<18} N={len(pts):>4}  總={pts.sum():>7.0f}  均={pts.mean():>6.1f}  "
          f"均%={pct.mean():>5.2f}  勝率={win.mean():>4.0%}  "
          f"max={pts.max():>5.0f}  砍top3後總={pts.sum()-top3:>7.0f}")


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    print(f"乾淨 EstHL 進場:{len(entries)} 筆 [{entries[0]['date']} ~ {entries[-1]['date']}]\n")

    modes = [("static", "靜態 @L3"), ("5ma", "5MA from L3"), ("dow", "Dow from L3")]

    # 先確認 L3-reach 集合(與 mode 無關,用 static 跑即可標記)
    base_rows = run(entries, "static")
    n_l3 = sum(r["r3"] for r in base_rows)
    print(f"守初始SL 抱到 L3 的單:{n_l3} / {len(entries)} ({n_l3/len(entries):.0%})\n")

    print("=== ① L3-reachers ONLY（決定性對比：只看有到 L3 的單在 L3 後怎麼出）===")
    for m, lab in modes:
        r = run(entries, m)
        stat_line([x for x in r if x["r3"]], lab)

    print("\n=== ② 全期（非L3單三模式相同；差異全來自上面那批 L3 單）===")
    for m, lab in modes:
        stat_line(run(entries, m), lab)

    for period, mask in [("OOS train ≤2024", lambda d: d.year <= 2024),
                         ("OOS test ≥2025", lambda d: d.year >= 2025)]:
        print(f"\n=== {period}（L3-reachers only）===")
        for m, lab in modes:
            r = run(entries, m, mask)
            stat_line([x for x in r if x["r3"]], lab)


if __name__ == "__main__":
    main()

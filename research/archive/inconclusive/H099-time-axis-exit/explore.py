"""H099 Phase 1 — 碰 L3 的時間 → 後續續航衰減（時間維度出場）

母體：H095 乾淨 EstHL(long-only) 進場、守初始SL 抱到 L3 的單（與 explore_l3_exit_modes
的 L3-reacher 一致）。對每筆記錄「碰 L3 的時刻 t3」與「碰 L3 後的價格路徑」：
  - reach_max = (j3 之後最高價 − base) / EMA20        ← 純路徑續航（不受出場影響）
  - 是否續到 L4(0.973) / L5(1.225)
  - 高水位回吐 = reach_max − eod_reach（碰 L3 後最高 → 收盤的侵蝕，×EMA20）

問題：P(L4|L3) 與碰 L3 後中位延伸，是否隨 t3 變晚單調衰減？
控制：固定 DCI band 內時間衰減是否仍在（排除「時間 = DCI 代理」）。

純探索、無回測。沿用 H095 階梯係數與進場/母體定義。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "H095-reach-ladder-exit"))
from phase2_path_backtest import C, SL_FRAC, build_entries  # noqa: E402
from dci_reach_distribution_2026 import daily_dci  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402

# 延伸關卡係數（與 H095 results/pastL4_continuation.txt 一致）
L3C, L4C, L5C = C["L3"], 0.973, 1.225

# 時間桶（分鐘 of day；08:45=525, 09:30=570, 10:45=645, 13:45=825）
BUCKETS = [
    ("≤09:30", 0, 570),
    ("09:30–10:45", 570, 645),
    ("10:45–11:30", 645, 690),
    ("11:30–12:30", 690, 750),
    (">12:30", 750, 826),
]


def l3_path(day, ei, base, emahl, ema20):
    """守初始SL 找 L3。回傳 dict 或 None（None=L3 前觸 SL 或沒到 L3）。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    L3 = base + L3C * ema20
    sl = entry = c[ei]
    sl = entry - SL_FRAC * emahl
    n = len(h)

    j3 = None
    for j in range(ei + 1, n):
        if l[j] <= sl:
            return None                      # L3 前死，不在母體
        if h[j] >= L3:
            j3 = j
            break
    if j3 is None:
        return None                          # 沒到 L3

    post_high = h[j3:].max()
    reach_max = (post_high - base) / ema20
    eod_reach = (c[n - 1] - base) / ema20
    return {
        "t3": int(mins[j3]),
        "reach_max": float(reach_max),
        "l4": reach_max >= L4C,
        "l5": reach_max >= L5C,
        "ext_beyond_l3": float(reach_max - L3C),     # 碰 L3 後又走多遠（×EMA20）
        "giveback": float(reach_max - eod_reach),    # 高水位→收盤回吐（×EMA20）
    }


def bucket_of(t):
    for name, lo, hi in BUCKETS:
        if lo <= t < hi:
            return name
    return ">12:30"


def summarise(rows, title):
    print(f"\n=== {title}　(N={len(rows)}) ===")
    print(f"  {'時間桶':<14} {'N':>4} {'P(L4|L3)':>9} {'P(L5|L4)':>9} "
          f"{'中位reach':>9} {'中位延伸':>9} {'中位回吐':>9}")
    for name, _, _ in BUCKETS:
        b = [r for r in rows if bucket_of(r["t3"]) == name]
        if not b:
            print(f"  {name:<14} {0:>4}")
            continue
        n = len(b)
        l4 = [r for r in b if r["l4"]]
        p_l4 = len(l4) / n
        p_l5 = (np.mean([r["l5"] for r in l4]) if l4 else float("nan"))
        med_reach = np.median([r["reach_max"] for r in b])
        med_ext = np.median([r["ext_beyond_l3"] for r in b])
        med_gb = np.median([r["giveback"] for r in b])
        print(f"  {name:<14} {n:>4} {p_l4:>8.0%} {p_l5:>8.0%} "
              f"{med_reach:>9.2f} {med_ext:>9.2f} {med_gb:>9.2f}")
    # pooled 參考
    n = len(rows)
    l4 = [r for r in rows if r["l4"]]
    print(f"  {'pooled':<14} {n:>4} {len(l4)/n:>8.0%} "
          f"{np.mean([r['l5'] for r in l4]):>8.0%} "
          f"{np.median([r['reach_max'] for r in rows]):>9.2f} "
          f"{np.median([r['ext_beyond_l3'] for r in rows]):>9.2f} "
          f"{np.median([r['giveback'] for r in rows]):>9.2f}")


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    print(f"乾淨 EstHL 進場：{len(entries)} 筆 "
          f"[{entries[0]['date']} ~ {entries[-1]['date']}]")

    rows = []
    for e in entries:
        r = l3_path(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"])
        if r is None:
            continue
        r["date"] = e["date"]
        rows.append(r)
    print(f"守初始SL 抱到 L3 的單（母體）：{len(rows)} 筆")

    # ① 主表：時間桶 × 續航
    summarise(rows, "全期 2021–2026｜碰 L3 時間 × 續航")

    # ② DCI band 控制：固定強度帶內，時間衰減是否仍在
    dci = daily_dci()
    lut = {ts.date(): float(v) for ts, v in dci["dci_long"].items()}
    for r in rows:
        r["dci_long"] = lut.get(r["date"], np.nan)
    have = [r for r in rows if not np.isnan(r["dci_long"])]
    print(f"\n[DCI 對齊] 有 dci_long 的母體：{len(have)}/{len(rows)} 筆")
    for lab, mask in [
        ("強多 dci_long≥+0.2", lambda r: r["dci_long"] >= 0.2),
        ("中 dci_long −0.1~+0.2", lambda r: -0.1 <= r["dci_long"] < 0.2),
        ("弱 dci_long<−0.1", lambda r: r["dci_long"] < -0.1),
    ]:
        sub = [r for r in have if mask(r)]
        if len(sub) >= 8:
            summarise(sub, f"DCI 控制：{lab}")
        else:
            print(f"\n=== DCI 控制：{lab}　(N={len(sub)} 過稀，略) ===")

    # ③ OOS 切分（看時間衰減是否穩定）
    for period, mask in [("train ≤2024", lambda d: d.year <= 2024),
                         ("test ≥2025", lambda d: d.year >= 2025)]:
        sub = [r for r in rows if mask(r["date"])]
        summarise(sub, f"OOS {period}｜碰 L3 時間 × 續航")

    # 圖：P(L4|L3) 與中位延伸 vs 時間桶
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        names = [b[0] for b in BUCKETS]
        p_l4, med_ext, ns = [], [], []
        for name in names:
            b = [r for r in rows if bucket_of(r["t3"]) == name]
            ns.append(len(b))
            p_l4.append(np.mean([r["l4"] for r in b]) if b else np.nan)
            med_ext.append(np.median([r["ext_beyond_l3"] for r in b]) if b else np.nan)

        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        x = range(len(names))
        ax1.bar(x, p_l4, color="#c0392b", alpha=0.65, label="P(L4|L3)")
        ax1.set_ylabel("P(L4|L3)", color="#c0392b")
        ax1.set_ylim(0, 1)
        for i, (p, nn) in enumerate(zip(p_l4, ns)):
            if not np.isnan(p):
                ax1.text(i, p + 0.02, f"{p:.0%}\nN={nn}", ha="center", fontsize=8)
        ax2 = ax1.twinx()
        ax2.plot(x, med_ext, "o-", color="#2c3e50", label="median ext (xEMA20)")
        ax2.set_ylabel("median extension beyond L3 (xEMA20)", color="#2c3e50")
        ax2.axhline(L4C - L3C, ls="--", color="gray", lw=0.8)
        ax2.text(0.02, L4C - L3C + 0.005, "ext needed to reach L4", fontsize=7, color="gray")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(names, rotation=15)
        ax1.set_title("H099: time of L3 touch -> continuation decay (long, 2021-2026)")
        fig.tight_layout()
        out = Path(__file__).parent / "results" / "time_decay.png"
        out.parent.mkdir(exist_ok=True)
        fig.savefig(out, dpi=130)
        print(f"\n圖已存：{out}")
    except Exception as ex:
        print(f"\n[繪圖略過] {ex}")


if __name__ == "__main__":
    main()

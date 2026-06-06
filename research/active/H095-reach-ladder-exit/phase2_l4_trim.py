"""H095 Phase 2 — 多方 L4 trim 驗證：到 L4 的餘量，『全抱 trail』vs『L4 砍半 + 餘量 trail』。

比較對象 = 碰 L3 後被 Dow trail 的那一單位餘量。
  - L3 拆分鎖掉的部分（出½/出⅓）兩政策完全相同 → 從比較中省略（會抵銷），故此處測「餘量 = 1 單位」。
  - 結論對實際餘量比例（≥0.4 路徑 2/3、0.2~0.4 路徑 1/2）等比例成立。
  - L4 trim 是對「不管多少餘量」砍半，與 DCI band 正交 → 本驗證不需盤中 DCI。

規則對齊 exit_scenarios v5.2（多方）：
  - 進場：乾淨 EstHL long（沿用 phase2_path_backtest.build_entries）
  - 初始 SL = 進場價 − 0.25×EmaHL，**守到 L3 完全不動**（無 BE）
  - 10:30 後仍未碰 L3 → 啟「時間停損」Dow trail
  - 碰 L3 → 啟 Dow trail（更高低點 ratchet）
  - 13:30 EOD 全平（保險閘）
  關卡 EMA-only：L1=.385 L2=.497 L3=.711 L4=.977 ×EMA20(日盤振幅, causal prior-day)。

逐筆差 = pnl_trim − pnl_hold = 0.5×(L4 − trail_exit)（僅到 L4 的單子有差）。
  EV 中性 ⇒ mean(diff) ≈ 0；降變異 ⇒ std(TRIM) < std(HOLD)、|maxDD|、最差筆改善。
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from phase2_path_backtest import (  # noqa: E402
    build_entries,
    load_data_for_orb_est_hl,
    pivot_low_trail,
)

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977}
GATE_1030 = 630   # 10:30
EOD_MIN = 810     # 13:30 全平（v5.2 保險閘）
SL_FRAC = 0.25


def simulate_rem(day, ei, base, emahl, ema20):
    """單口、v5.2 多方規則。回傳 (pnl_hold, pnl_trim, reached3, reached4)。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    entry = c[ei]
    L3 = base + C["L3"] * ema20
    L4 = base + C["L4"] * ema20
    stop = entry - SL_FRAC * emahl
    pl = pivot_low_trail(l)
    reached3 = reached4 = trail_on = False

    n = len(h)
    exit_px, _reason = c[n - 1], "eod"
    for j in range(ei + 1, n):
        t = mins[j]
        if t >= EOD_MIN:                       # 13:30 全平
            exit_px, _reason = c[j], "eod"
            break
        if trail_on and pl[j] > stop:          # Dow ratchet
            stop = pl[j]
        if l[j] <= stop:                       # 停損 / trail 觸發（不利方向先檢）
            exit_px = stop
            _reason = "trail" if trail_on else "stop"
            break
        if (not reached3) and (not trail_on) and t >= GATE_1030:
            trail_on = True                    # 10:30 時間停損
            if pl[j] > stop:
                stop = pl[j]
        if not reached3 and h[j] >= L3:        # 碰 L3 → 啟 trail
            reached3 = True
            trail_on = True
            if pl[j] > stop:
                stop = pl[j]
        if reached3 and not reached4 and h[j] >= L4:
            reached4 = True

    pnl_hold = exit_px - entry
    pnl_trim = (0.5 * (L4 - entry) + 0.5 * (exit_px - entry)) if reached4 else pnl_hold
    return pnl_hold, pnl_trim, reached3, reached4


def max_drawdown(pnls):
    """逐筆按時間序的權益曲線最大回撤（點）。"""
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    return float((peak - eq).max()) if len(eq) else 0.0


def describe(pnls, label):
    p = np.asarray(pnls, float)
    if not len(p):
        print(f"  {label}: 無交易"); return
    print(f"  {label:<16} N={len(p):>4}  總={p.sum():>7.0f}  均={p.mean():>6.2f}  "
          f"std={p.std():>6.2f}  最差={p.min():>7.1f}  maxDD={max_drawdown(p):>7.1f}")


def report(entries, mask, period):
    rows = [(simulate_rem(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"]), e["date"])
            for e in entries if (mask is None or mask(e["date"]))]
    hold = np.array([r[0][0] for r in rows])
    trim = np.array([r[0][1] for r in rows])
    r3 = np.array([r[0][2] for r in rows])
    r4 = np.array([r[0][3] for r in rows])

    print(f"=== {period} ===  (N={len(rows)}, 到L3={r3.mean():.0%}, 到L4={r4.mean():.0%})")
    print(" 全樣本（含未到 L4，兩政策僅 L4 單有差）：")
    describe(hold, "HOLD 全抱")
    describe(trim, "TRIM L4砍半")

    if r4.any():
        diff = (trim - hold)[r4]               # = 0.5×(L4 − trail_exit)
        print(f" 到 L4 子集（N={r4.sum()}，唯一有差處）：")
        describe(hold[r4], "HOLD 全抱")
        describe(trim[r4], "TRIM L4砍半")
        print(f"   逐筆差(trim−hold)：均={diff.mean():+.2f}  std={diff.std():.2f}  "
              f"trim較優={np.mean(diff > 0):.0%}  （EV中性⇒均≈0）")
    print()


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    print(f"乾淨 EstHL 進場：{len(entries)} 筆  "
          f"[{entries[0]['date']} ~ {entries[-1]['date']}]\n")

    report(entries, None, "全期")
    report(entries, lambda d: d.year <= 2024, "OOS train ≤2024")
    report(entries, lambda d: d.year >= 2025, "OOS test ≥2025")


if __name__ == "__main__":
    main()

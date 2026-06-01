"""H095 — 「09:30 前碰 L2」的單,後續會怎樣?(回吐分佈)

目的:回答「方向沒確認前(09:30 前)移停損是否過早」。
做法:用同一套 EstHL 進場(phase2_path_backtest.build_entries),對每筆單追蹤
      『首次碰 L2』之後的純價格路徑(不做任何停損移動,只留初始 SL),分類:
        - to_L3        : 碰 L2 後續攻到 L3(high≥L3)
        - roundtrip_SL : 碰 L2 後在到 L3 前先回吐到初始 SL(low≤entry−0.25·EmaHL)
        - held         : 兩者都沒發生,EOD 收在中間
      並量「碰 L2 後最大不利回吐(MAE,L2 以下幾點 / 佔 L2→SL 帶寬幾 %)」。

核心對照:**早碰 L2(<09:30) vs 晚碰 L2(≥09:30)** 的 round-trip 率與回吐深度。
  → 若早碰 round-trip 少、淺  ⇒ 守初始SL 便宜,早收緊只會洗強單(用戶直覺成立)
  → 若早碰 round-trip 多、深  ⇒ 守初始SL 代價高,早期需要某種防護
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from phase2_path_backtest import C, GATE_0930, SL_FRAC, build_entries  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402


def classify(day, ei, base, emahl, ema20, entry):
    """追蹤首次碰 L2 後的路徑。回傳 dict 或 None(沒碰到 L2 / 提早被初始SL停掉)。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    L1 = base + C["L1"] * ema20
    L2 = base + C["L2"] * ema20
    L3 = base + C["L3"] * ema20
    sl = entry - SL_FRAC * emahl
    n = len(h)

    # 1) 找首次碰 L2(過程中若先觸初始SL,該單早死,不入任何 L2 cohort)
    j_l2 = None
    for j in range(ei + 1, n):
        if l[j] <= sl:
            return None                      # 還沒到 L2 就被初始SL停掉
        if h[j] >= L2:
            j_l2 = j
            break
    if j_l2 is None:
        return None                          # 整日沒碰 L2

    t_l2 = mins[j_l2]
    # 2) 碰 L2 後:先到 L3 還是先回初始SL?
    outcome = "held"
    min_after = l[j_l2]
    for k in range(j_l2, n):
        min_after = min(min_after, l[k])
        if h[k] >= L3:
            outcome = "to_L3"
            break
        if l[k] <= sl:
            outcome = "roundtrip_SL"
            break

    band = L2 - sl                            # L2 → 初始SL 的帶寬
    mae_below_l2 = max(0.0, L2 - min_after)   # 碰 L2 後跌破 L2 的最大深度(點)
    l2_minus_l1 = (C["L2"] - C["L1"]) * ema20  # L1 在 L2 下方幾點
    # 若碰 L2 當下把 SL 移到 L1:跌破 L2 深度 ≥ (L2−L1) 就會被 L1 停掉
    washed_at_l1 = mae_below_l2 >= l2_minus_l1
    return {
        "t_l2": t_l2,
        "early": t_l2 < GATE_0930,
        "outcome": outcome,
        "unreal_at_L2": L2 - entry,           # 碰 L2 當下的未實現(點)
        "mae_below_l2": mae_below_l2,
        "mae_frac_band": mae_below_l2 / band if band > 0 else np.nan,
        "l2_minus_l1": l2_minus_l1,
        "washed_at_l1": washed_at_l1,
        "L2_to_L3": L3 - L2,
    }


def summarize(rows, label):
    n = len(rows)
    if n == 0:
        print(f"  {label}: 無樣本")
        return
    out = np.array([r["outcome"] for r in rows])
    p_l3 = np.mean(out == "to_L3")
    p_rt = np.mean(out == "roundtrip_SL")
    p_hold = np.mean(out == "held")
    mae = np.array([r["mae_below_l2"] for r in rows])
    fracb = np.array([r["mae_frac_band"] for r in rows])
    unreal = np.array([r["unreal_at_L2"] for r in rows])
    print(f"  {label:<26} N={n:>4} | 到L3 {p_l3:>4.0%}  回吐到SL {p_rt:>4.0%}  中間守住 {p_hold:>4.0%} "
          f"| 跌破L2深度(點) p50={np.median(mae):>4.0f} p75={np.percentile(mae,75):>4.0f} "
          f"| MAE/帶寬 p50={np.nanmedian(fracb):>4.0%} | 碰L2未實現 p50={np.median(unreal):>4.0f}點")


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    print(f"乾淨 EstHL 進場:{len(entries)} 筆 [{entries[0]['date']} ~ {entries[-1]['date']}]\n")

    rows = []
    for e in entries:
        r = classify(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"], e["entry"])
        if r is not None:
            r["date"] = e["date"]
            rows.append(r)

    n_l2 = len(rows)
    n_early = sum(r["early"] for r in rows)
    print(f"碰到 L2 的單:{n_l2} / {len(entries)}  ({n_l2/len(entries):.0%})  "
          f"其中早碰(<09:30) {n_early}、晚碰(≥09:30) {n_l2-n_early}\n")

    print("=== 全期 ===")
    summarize(rows, "全部碰 L2")
    summarize([r for r in rows if r["early"]], "早碰 L2 (<09:30)")
    summarize([r for r in rows if not r["early"]], "晚碰 L2 (≥09:30)")

    # 決定性問題:碰 L2 移 SL→L1,會洗掉多少『最後有到 L3 的贏單』?
    print("\n=== 若碰 L2 即把 SL 移到 L1:對『到 L3 贏單』的洗單率 ===")
    for lab, sub in [("早碰 L2 (<09:30)", [r for r in rows if r["early"]]),
                     ("晚碰 L2 (≥09:30)", [r for r in rows if not r["early"]])]:
        l3win = [r for r in sub if r["outcome"] == "to_L3"]
        rt = [r for r in sub if r["outcome"] == "roundtrip_SL"]
        washed = sum(r["washed_at_l1"] for r in l3win)
        print(f"  {lab:<20} 到L3贏單 {len(l3win)} 筆,其中到 L3 前先觸 L1 被洗 = "
              f"{washed} ({washed/len(l3win):.0%} 若有)  | 回吐到SL {len(rt)} 筆→改為 L1 止損,"
              f"每筆少賠約 {C['L2'] - C['L1']:.3f}·EMA(≈L2−L1 帶寬的下半段)")

    # OOS sanity:train≤2024 / test≥2025
    for lab, f in [("OOS train ≤2024", lambda d: d.year <= 2024),
                   ("OOS test ≥2025", lambda d: d.year >= 2025)]:
        sub = [r for r in rows if f(r["date"])]
        print(f"\n=== {lab} ===")
        summarize([r for r in sub if r["early"]], "早碰 L2 (<09:30)")
        summarize([r for r in sub if not r["early"]], "晚碰 L2 (≥09:30)")

    # 早碰 L2 再細分觸及時間桶,看 round-trip 率是否隨時間單調
    print("\n=== 早碰 L2 內部:依碰 L2 時間細分 ===")
    buckets = [(525, 549, "08:45–09:09"), (549, 561, "09:09–09:21"), (561, 570, "09:21–09:30")]
    for lo, hi, name in buckets:
        summarize([r for r in rows if lo <= r["t_l2"] < hi], name)


if __name__ == "__main__":
    main()

"""H124 後續 — 測 Pine 指標(swing_levels_tx.pine)的「實際變體 P」是否優於 Python causal A。

動機：Pine 在 2026-06-11 進 09:08，Python(A) 進 08:58 —— 兩者不一致。拆解出 Pine 的進場語意
與 A 不同之處，要決定 chart-ui 主圖指標該對齊哪邊（用數據，不用直覺）。

變體 P＝忠實複刻 Pine（swing_levels_tx.pine:269-313）：
  - peak 用「凍結」值（拉回起點當下的 running 高/低，b_peak/s_peak），算 depth 用它。
  - depth(min_depth 0.25) 是進場 if 的一部分 → 淺站回不進、且【不消耗本段】(不 done)，
    pb_ext 持續往下/上累積，直到第一個「夠深的站回」才進場。每段至多一筆。
  - matured 只在 extend(未拉回前)用 tracked ext 檢查；pullback 中僅靠 overshoot(close-based)。
  - Pine 同根時序：先推 ZigZag 翻轉/開相位，再跑進場邏輯（與 A「延到下一根」不同）。

對照 A＝現行 chart-ui/Python causal：第一個站回(任意深)即記錄+done，depth 事後濾（淺站回消耗本段）。

跑法：uv run python research/archive/rejected/H124-leg-multi-pullback/explore_pine_variant.py
"""
from __future__ import annotations

import importlib.util
from collections import defaultdict
from datetime import date
from pathlib import Path

_p = Path(__file__).with_name("explore.py")
_spec = importlib.util.spec_from_file_location("h124_explore", _p)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

L2C, L3C, L4C, L5C = H.L2C, H.L3C, H.L4C, H.L5C
PB_FLOOR_FRAC, MIN_DEPTH_FRAC, NOON = H.PB_FLOOR_FRAC, H.MIN_DEPTH_FRAC, H.NOON
sma = H.sma


def detect_pine(days, ema):
    """忠實複刻 Pine：凍結 peak + 淺站回不消耗本段 + Pine 同根時序。"""
    out = []
    for d in sorted(ema):
        bars = days[d]
        e = ema[d]
        L2d, L3d = L2C * e, L3C * e
        L4d, L5d = L4C * e, L5C * e
        pb_floor = PB_FLOOR_FRAC * e
        closes = [b[4] for b in bars]
        s5 = sma(closes, 5)
        n = len(bars)

        trend = None
        up_ref = bars[0][3]
        dn_ref = bars[0][2]
        ext = None             # ZigZag running extreme（=Pine ext，當前 trend 的極值）
        phase = None
        anchor = None
        peak_frz = None        # 凍結 peak（=Pine b_peak/s_peak）
        sub = None
        pb_ext = None
        done = False

        def open_phase(dir_up, anc):
            nonlocal phase, anchor, peak_frz, sub, pb_ext, done
            phase = "up" if dir_up else "down"
            anchor = anc
            peak_frz = None
            sub = "extend"
            pb_ext = None
            done = False

        for i in range(n):
            m, o, h, l, c = bars[i]

            # === 1) Pine 順序：先推 ZigZag / 開相位（同根） ===
            if trend is None:
                up_ref = min(up_ref, l)
                dn_ref = max(dn_ref, h)
                if h - up_ref >= L2d:
                    trend = "up"; ext = h; open_phase(True, up_ref)
                elif dn_ref - l >= L2d:
                    trend = "down"; ext = l; open_phase(False, dn_ref)
            elif trend == "up":
                ext = max(ext, h)
                if ext - l >= L2d:
                    pivot = ext; trend = "down"; open_phase(False, pivot); ext = l
            else:
                ext = min(ext, l)
                if h - ext >= L2d:
                    pivot = ext; trend = "up"; open_phase(True, pivot); ext = h

            # === 2) 進場邏輯，用本根已更新的 ext（Pine 同根） ===
            if phase is not None and not done:
                up = phase == "up"
                if sub == "extend":
                    if (ext - anchor if up else anchor - ext) >= L3d:
                        done = True                       # matured（tracked ext，僅 extend）
                    else:
                        dip = (ext - l) if up else (h - ext)
                        if dip >= pb_floor:
                            sub = "pullback"
                            peak_frz = ext                # 凍結
                            pb_ext = l if up else h
                elif sub == "pullback":
                    pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                    cs = s5[i]
                    ps = s5[i - 1] if i > 0 else None
                    pc = bars[i - 1][4] if i > 0 else None
                    if cs is not None and ps is not None and pc is not None:
                        reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                        overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                        depth = (peak_frz - pb_ext) if up else (pb_ext - peak_frz)
                        deep = depth >= MIN_DEPTH_FRAC * L2d
                        if reclaim and not overshoot and deep:
                            out.append({
                                "date": d, "up": up, "side": "bull" if up else "bear",
                                "entry_i": i, "entry_min": m, "entry": c,
                                "anchor": anchor, "pb_low": pb_ext, "ema20": e,
                                "L3d": L3d, "L4d": L4d, "L5d": L5d,
                                "depth_frac": depth / L2d, "peak": peak_frz,
                            })
                            done = True
    return out


def main():
    days = H.load_days()
    ema = H.ema20_map(days)

    A = [t for t in H.detect_causal(days, ema, mode="A")
         if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]
    P = [t for t in detect_pine(days, ema) if t["entry_min"] < NOON]

    print(f"setups（<12:00, depth>=0.25）：  A(現行)={len(A)}   P(Pine)={len(P)}\n")

    for name, S in [("A 現行 chart-ui/Python", A), ("P Pine 實際變體", P)]:
        s_is, s_oos = H.split(S)
        print(f"=== {name} ===")
        print(f"  IS  {H.fmt(H.metrics(H.run(s_is, days)))}")
        print(f"  OOS {H.fmt(H.metrics(H.run(s_oos, days)))}")
        print(f"  ALL {H.fmt(H.metrics(H.run(S, days)))}\n")

    aset = {H.key(t) for t in A}
    pset = {H.key(t) for t in P}
    common = [t for t in P if H.key(t) in aset]
    p_only = [t for t in P if H.key(t) not in aset]
    a_only = [t for t in A if H.key(t) not in pset]
    print("=== P vs A 分解 ===")
    print(f"  兩者相同      {H.fmt(H.metrics(H.run(common, days)))}")
    print(f"  只有 P(Pine)  {H.fmt(H.metrics(H.run(p_only, days)))}")
    print(f"  只有 A(現行)  {H.fmt(H.metrics(H.run(a_only, days)))}")
    print(f"\n  → P 與 A 進場相同的比例：{len(common)}/{len(P)} (P)  {len(common)}/{len(A)} (A)")

    # 逐日：P 與 A 不同的天數
    diff_days = sorted({t["date"] for t in p_only} | {t["date"] for t in a_only})
    print(f"  → P 與 A 結果不同的交易日數：{len(diff_days)}")

    print("\n=== 2026-06-11 sanity ===")
    for name, S in [("A", A), ("P", P)]:
        d11 = [t for t in S if t["date"] == date(2026, 6, 11)]
        for t in H.run(d11, days):
            tc = t["tc"]
            print(f"  {name}: {tc['entry_min']//60:02d}:{tc['entry_min']%60:02d} "
                  f"{'long' if tc['up'] else 'short'} depth={tc['depth_frac']:.2f} "
                  f"{t['outcome']} pnl={t['pnl']:+.1f}")


if __name__ == "__main__":
    main()

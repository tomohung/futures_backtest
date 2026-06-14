"""分析 causal 全量 1260 筆站回：失敗交易有無「進場當下可得」的共同特徵？

對每筆 causal 交易算純 causal 特徵（全部只用截至進場那根 close 的資訊），
再比對勝(overlap 續攻)/負(extra 失敗) 兩組分佈，並測單一濾網的取捨。
目的：判斷能否用 real-time 濾網救回（若兩組分佈重疊→無法事先區分）。

跑法：uv run python research/archive/confirmed/H120-l2-pullback-continuation/analyze_failures.py
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict

import validate_causal as V


def features(t):
    """t = run() 後的交易（含 tc）。回傳純 causal 特徵 dict。"""
    tc = t["tc"]
    up, e = tc["up"], tc["ema20"]
    L2d = 0.497 * e
    anchor, peak, entry, pb = tc["anchor"], tc["peak"], tc["entry"], tc["pb_low"]
    target = anchor + tc["L3d"] if up else anchor - tc["L3d"]
    # 方向正規化：所有距離取「順勢為正」
    ext_peak = (peak - anchor) if up else (anchor - peak)        # 波峰離錨點(確立後最大延伸)
    room = (target - entry) if up else (entry - target)          # 進場到 L3 目標剩餘空間
    gap_peak = (peak - entry) if up else (entry - peak)          # 進場收盤離波峰多遠(站回後仍低於峰多少)
    depth = (peak - pb) if up else (pb - peak)                   # 拉回深度(絕對)
    recovered = (entry - pb) if up else (pb - entry)             # 站回時已從拉回極值回升多少
    return {
        "ext_peak_L2": ext_peak / L2d,        # 1.0=剛確立 L2，越大越接近 L3(更晚/更延伸)
        "room_L2": room / L2d,                # 剩餘空間(÷L2)。越小越接近目標(追高)
        "gap_peak_L2": gap_peak / L2d,        # 進場離峰距離(÷L2)。大=峰已遠(疑似事後反彈)
        "depth_L2": depth / L2d,              # = depth_frac
        "recov_frac": recovered / depth if depth > 0 else 0,  # 回補比例(0=剛站回,1=回到峰)
        "entry_min": tc["entry_min"],
        "risk_pct": (entry - (pb - 0.75 * (pb - anchor))) / entry * 100 if up
                    else ((pb + 0.75 * (anchor - pb)) - entry) / entry * 100,
    }


def dist(vals):
    vals = sorted(vals)
    n = len(vals)
    q = lambda p: vals[min(n - 1, int(p * n))]
    return f"n={n:>4} mean={st.mean(vals):6.2f} med={q(.5):6.2f} p25={q(.25):6.2f} p75={q(.75):6.2f}"


def main():
    days = V.load_days()
    ema = V.ema20_map(days)
    caus = [t for t in V.detect_causal(days, ema)
            if t["depth_frac"] >= V.MIN_DEPTH_FRAC and t["entry_min"] < V.NOON]
    trs = V.run(caus, days)
    for t in trs:
        t["f"] = features(t)
    win = [t for t in trs if t["win"]]
    los = [t for t in trs if not t["win"]]
    print(f"全量 causal: N={len(trs)}  勝={len(win)} ({100*len(win)/len(trs):.0f}%)  負={len(los)}\n")

    keys = ["ext_peak_L2", "room_L2", "gap_peak_L2", "depth_L2", "recov_frac",
            "entry_min", "risk_pct"]
    print("=== 特徵分佈：勝 vs 負（全 causal，進場當下可得）===")
    for k in keys:
        print(f"  {k:>12}")
        print(f"      win  {dist([t['f'][k] for t in win])}")
        print(f"      loss {dist([t['f'][k] for t in los])}")

    # 單一門檻濾網掃描：保留 X 後，勝率/EV/留存比例
    print("\n=== 單濾網掃描（保留滿足條件者；看勝率/EV/留存）===")
    base_ev = st.mean([t["pnl"] for t in trs])
    base_wr = 100 * len(win) / len(trs)
    print(f"  baseline 全留   N={len(trs)} win={base_wr:.1f}% EV={base_ev:.1f}pt")

    def scan(name, keep_fn, grid, fmt="{:.2f}"):
        print(f"  -- {name} --")
        for thr in grid:
            kept = [t for t in trs if keep_fn(t["f"], thr)]
            if len(kept) < 30:
                print(f"     thr={fmt.format(thr)}  n={len(kept)} (太少略)")
                continue
            wr = 100 * sum(t["win"] for t in kept) / len(kept)
            ev = st.mean([t["pnl"] for t in kept])
            tot = sum(t["pct"] for t in kept)
            sd = st.pstdev([t["pct"] for t in kept])
            sh = st.mean([t["pct"] for t in kept]) / sd if sd else 0
            print(f"     thr={fmt.format(thr):>6}  n={len(kept):>4} 留存={100*len(kept)/len(trs):4.0f}%"
                  f"  win={wr:5.1f}% EV={ev:6.1f}pt tot={tot:7.1f}% sharpe={sh:.3f}")

    scan("gap_peak_L2 ≤ thr（進場離峰夠近=新鮮續攻）", lambda f, t: f["gap_peak_L2"] <= t,
         [0.10, 0.20, 0.30, 0.50, 0.75])
    scan("room_L2 ≥ thr（離目標夠遠=還有空間）", lambda f, t: f["room_L2"] >= t,
         [0.30, 0.50, 0.70, 0.90])
    scan("ext_peak_L2 ≤ thr（波峰未過度延伸=早段）", lambda f, t: f["ext_peak_L2"] <= t,
         [1.05, 1.15, 1.25, 1.40])
    scan("recov_frac ≥ thr（站回時已回補多）", lambda f, t: f["recov_frac"] >= t,
         [0.30, 0.50, 0.70])
    scan("entry_min ≤ thr（更早進場）", lambda f, t: f["entry_min"] <= t,
         [570, 600, 630, 660], fmt="{:.0f}")

    # 雙濾網：gap_peak 近 + room 大
    print("\n=== 組合：gap_peak_L2≤0.20 且 room_L2≥0.50 ===")
    kept = [t for t in trs if t["f"]["gap_peak_L2"] <= 0.20 and t["f"]["room_L2"] >= 0.50]
    if kept:
        wr = 100 * sum(t["win"] for t in kept) / len(kept)
        ev = st.mean([t["pnl"] for t in kept])
        tot = sum(t["pct"] for t in kept)
        sd = st.pstdev([t["pct"] for t in kept])
        sh = st.mean([t["pct"] for t in kept]) / sd if sd else 0
        print(f"  n={len(kept)} 留存={100*len(kept)/len(trs):.0f}% win={wr:.1f}% "
              f"EV={ev:.1f}pt tot={tot:.1f}% sharpe={sh:.3f}")


if __name__ == "__main__":
    main()

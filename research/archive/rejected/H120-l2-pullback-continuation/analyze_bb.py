"""H120 衍生濾網：拉回是否打到 BB(15,2) 下/上軌 → 再站回 5MA，勝率/EV 會更高嗎？

定義（使用者選）：確立後的拉回段，期間任一根 low ≤ 下軌(多) / high ≥ 上軌(空)=「打到軌」，
之後收盤站回 5MA 才進場。比較 全部 vs 打到軌 vs 沒打到軌。
重用 backtest.py 的 simulate/metrics（alpha=0.75, mode=L3, cost=3, ≤12:00）。
"""
from __future__ import annotations

import importlib.util
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("bt", str(Path(__file__).parent / "backtest.py"))
bt = importlib.util.module_from_spec(spec)
sys.modules["bt"] = bt
spec.loader.exec_module(bt)

from src.chart_ui.services.swing_legs import zigzag_legs

BB_LEN, BB_K = 15, 2.0
ALPHA, MODE, COST, CUTOFF = 0.75, "L3", 3, 720


def bb_bands(closes):
    """回傳 (lower[], upper[])，causal BB(BB_LEN, BB_K)；不足回 None。"""
    lo, up = [], []
    for i in range(len(closes)):
        if i < BB_LEN - 1:
            lo.append(None); up.append(None); continue
        w = closes[i - BB_LEN + 1:i + 1]
        mid = sum(w) / BB_LEN
        sd = st.pstdev(w)
        lo.append(mid - BB_K * sd); up.append(mid + BB_K * sd)
    return lo, up


def detect_bb(days, ema):
    """同 bt.detect，但記錄拉回是否打到 BB 軌（bb_tag）。"""
    out = []
    for d in sorted(ema):
        bars = days[d]; e = ema[d]
        dist = {k: bt.COEF[k] * e for k in bt.COEF}
        L2d, L3d = dist["L2"], dist["L3"]
        pb_floor = bt.PB_FLOOR_FRAC * e
        closes = [b[4] for b in bars]
        s5 = bt.sma(closes, 5)
        lo, up = bb_bands(closes)
        legs = zigzag_legs([(m, h, l) for m, _, h, l, _ in bars], threshold=L2d)
        for lg in legs:
            if abs(lg["end_price"] - lg["start_price"]) < L2d:
                continue
            up_dir = lg["dir"] == "up"
            sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
            seg_idx = [i for i, b in enumerate(bars) if sm <= b[0] <= em]
            if len(seg_idx) < 3:
                continue
            est_i, ext = None, 0.0
            for i in seg_idx:
                _, _, h, l, _ = bars[i]
                ext = max(ext, (h - anchor) if up_dir else (anchor - l))
                if ext >= L2d:
                    est_i = i; break
            if est_i is None:
                continue
            state, peak, tagged = "extend", None, False
            for i in seg_idx:
                if i < est_i:
                    continue
                m, o, h, l, c = bars[i]
                if peak is None:
                    peak = h if up_dir else l; continue
                if state == "extend":
                    if (h > peak) if up_dir else (l < peak):
                        peak = h if up_dir else l
                    if abs(peak - anchor) >= L3d:
                        break
                    dip = (peak - l) if up_dir else (h - peak)
                    if dip >= pb_floor:
                        state = "pullback"; pb_ext = l if up_dir else h
                        if lo[i] is not None:
                            tagged = (l <= lo[i]) if up_dir else (h >= up[i])
                else:
                    pb_ext = min(pb_ext, l) if up_dir else max(pb_ext, h)
                    if lo[i] is not None and not tagged:
                        tagged = (l <= lo[i]) if up_dir else (h >= up[i])
                    cs, ps, pc = s5[i], s5[i - 1], bars[i - 1][4]
                    if cs is not None and ps is not None:
                        reclaim = (pc < ps and c > cs) if up_dir else (pc > ps and c < cs)
                        overshoot = (c >= anchor + L3d) if up_dir else (c <= anchor - L3d)
                        if reclaim and not overshoot:
                            depth = (peak - pb_ext) if up_dir else (pb_ext - peak)
                            out.append({
                                "date": d, "up": up_dir, "side": "bull" if up_dir else "bear",
                                "entry_i": i, "entry_min": m, "entry": c, "anchor": anchor,
                                "pb_low": pb_ext, "ema20": e, "L3d": L3d,
                                "L4d": dist["L4"], "L5d": dist["L5"], "bb_tag": tagged,
                                "depth_frac": depth / L2d,   # 拉回深度 / L2 距離
                            })
                            break
    return out


def run(tcs, days):
    return [dict(bt.simulate(tc, days[tc["date"]], alpha=ALPHA, mode=MODE, trail_frac=0, cost=COST),
                 bb_tag=tc["bb_tag"], side=tc["side"], year=tc["date"].year,
                 depth_frac=tc["depth_frac"]) for tc in tcs]


def line(label, m, ndays):
    if not m:
        print(f"  {label:<16} N=0"); return
    print(f"  {label:<16} N={m['N']:>4} ({m['N']/ndays:.2f}/日) win={m['win%']:>5}% "
          f"EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% sharpe={m['sharpe']:>6} "
          f"mdd={m['mdd%']:>6}% maxLoss={m['maxLoss']:>2} avgR={m['avgR']}")


def main():
    days = bt.load_all(); ema = bt.ema20_map(days)
    ndays = len(ema)
    tcs = [t for t in detect_bb(days, ema) if t["entry_min"] < CUTOFF]
    trs = run(tcs, days)
    print(f"H120 ≤12:00 trigger A：N={len(trs)}（BB(15,2) 濾網比較）\n")

    print("=== 全部 vs 拉回打到軌 vs 沒打到軌 ===")
    line("全部", bt.metrics(trs), ndays)
    line("打到軌(BB)", bt.metrics([t for t in trs if t["bb_tag"]]), ndays)
    line("沒打到軌", bt.metrics([t for t in trs if not t["bb_tag"]]), ndays)

    print("\n=== 打到軌 × 多空 ===")
    for side in ("bull", "bear"):
        sub = [t for t in trs if t["bb_tag"] and t["side"] == side]
        line("打到軌 " + ("多" if side == "bull" else "空"), bt.metrics(sub), ndays)

    print("\n=== 打到軌 IS/OOS ===")
    bb = [t for t in trs if t["bb_tag"]]
    line("IS<2025", bt.metrics([t for t in bb if t["year"] < 2025]), ndays)
    line("OOS>=2025", bt.metrics([t for t in bb if t["year"] >= 2025]), ndays)
    frac = round(100 * len(bb) / len(trs), 1) if trs else 0
    print(f"打到軌占比：{frac}%（{len(bb)}/{len(trs)}）")

    # ---- (a) 純拉回深度對照：BB 是否只是深拉回的代理？----
    print("\n=== (a) 純拉回深度分桶（depth / L2 距離）===")
    buckets = [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]
    for lo_, hi_ in buckets:
        sub = [t for t in trs if lo_ <= t["depth_frac"] < hi_]
        line(f"depth {lo_:.2f}-{hi_:.2f}", bt.metrics(sub), ndays)

    print("\n=== (a) 深拉回(≥0.5 L2) vs BB打到軌 vs 兩者交集 ===")
    deep = [t for t in trs if t["depth_frac"] >= 0.5]
    line("深拉回≥0.5", bt.metrics(deep), ndays)
    line("BB打到軌", bt.metrics(bb), ndays)
    line("深拉回∩BB", bt.metrics([t for t in trs if t["depth_frac"] >= 0.5 and t["bb_tag"]]), ndays)
    print("\n  控制深度：同在『深拉回≥0.5』內，BB tag 有沒有再加值？")
    line("  深拉回 & BB", bt.metrics([t for t in deep if t["bb_tag"]]), ndays)
    line("  深拉回 & 無BB", bt.metrics([t for t in deep if not t["bb_tag"]]), ndays)
    # BB tag 在深拉回中的占比
    nd = len(deep)
    print(f"  （深拉回中 BB 占比 {round(100*sum(t['bb_tag'] for t in deep)/nd,1) if nd else 0}%）")

    # ---- 加碼倍數：以 avgR 比例為基準 ----
    print("\n=== 加碼倍數建議（以 avgR / 每筆風險調整邊際為基準）===")
    base = bt.metrics(trs)
    for label, sub in (("深拉回≥0.5", deep), ("BB打到軌", bb), ("深拉回∩BB",
                       [t for t in trs if t["depth_frac"] >= 0.5 and t["bb_tag"]])):
        m = bt.metrics(sub)
        if not m:
            continue
        mult_r = m["avgR"] / base["avgR"] if base["avgR"] else 0
        mult_ev = m["EVpt"] / base["EVpt"] if base["EVpt"] else 0
        print(f"  {label:<12} avgR {base['avgR']}→{m['avgR']} (×{mult_r:.1f})  "
              f"EV {base['EVpt']}→{m['EVpt']} (×{mult_ev:.1f})  機會 {m['N']/ndays:.2f}/日")


if __name__ == "__main__":
    main()

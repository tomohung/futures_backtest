"""causal 預備測試：只做單一方向 + 抓長尾（達 L3 改 trail 搏 L4/L5）能否改善？

完全 causal。trail 出場：達 target=L3 後不全出，改 trailing（trail_frac×L3d），
往後逐根上移，被回吐 trail_dist 才出 → 捕捉延伸到 L4/L5 的長尾。
停損優先（保守）。對照 baseline mode=L3（到 L3 全出）。

跑法：uv run python research/archive/confirmed/H120-l2-pullback-continuation/analyze_longtail.py
"""
from __future__ import annotations

import statistics as st

import validate_causal as V


def sim(tc, bars, *, alpha=V.ALPHA, cost=V.COST, mode="L3", trail_frac=0.5):
    up, entry, anchor, pb = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    L3d = tc["L3d"]
    stop = pb - alpha * (pb - anchor) if up else pb + alpha * (anchor - pb)
    target = anchor + L3d if up else anchor - L3d
    risk = (entry - stop) if up else (stop - entry)
    fwd = bars[tc["entry_i"] + 1:]
    trailing = None
    trail_dist = trail_frac * L3d
    hit = False
    outcome, exitp = "open", bars[-1][4]
    for m, o, h, l, c in fwd:
        cur_stop = trailing if trailing is not None else stop
        if (l <= cur_stop) if up else (h >= cur_stop):
            outcome, exitp = ("trail" if trailing is not None else "loss"), cur_stop
            break
        reached = (h >= target) if up else (l <= target)
        if reached and not hit:
            hit = True
            if mode == "L3":
                outcome, exitp = "win", target
                break
            trailing = (target - trail_dist) if up else (target + trail_dist)
        if mode == "trail" and hit:
            newt = (h - trail_dist) if up else (l + trail_dist)
            trailing = max(trailing, newt) if up else min(trailing, newt)
    pnl = ((exitp - entry) if up else (entry - exitp)) - cost
    return {"pnl": pnl, "pct": pnl / entry * 100, "R": (pnl / risk) if risk > 0 else None,
            "win": pnl > 0, "date": tc["date"], "up": tc["up"]}


def stats(trs):
    if not trs:
        return None
    pcts = [t["pct"] for t in trs]
    sd = st.pstdev(pcts) if len(pcts) > 1 else 0
    rs = [t["R"] for t in trs if t["R"] is not None]
    return {"N": len(trs), "win": 100 * sum(t["win"] for t in trs) / len(trs),
            "EV": st.mean([t["pnl"] for t in trs]), "tot": sum(pcts),
            "sh": st.mean(pcts) / sd if sd else 0, "avgR": st.mean(rs) if rs else 0,
            "maxR": max(rs) if rs else 0}


def f(x):
    return (f"N={x['N']:>4} win={x['win']:5.1f}% EV={x['EV']:6.1f} tot={x['tot']:7.1f}% "
            f"sh={x['sh']:6.3f} avgR={x['avgR']:5.2f} maxR={x['maxR']:5.1f}") if x else "N=0"


def show(label, tcs, days, **kw):
    trs = [sim(tc, days[tc["date"]], **kw) for tc in tcs]
    isg = [t for t in trs if t["date"] < V.OOS_START]
    oos = [t for t in trs if t["date"] >= V.OOS_START]
    print(f"  {label:<22} ALL {f(stats(trs))}")
    print(f"  {'':<22} IS  {f(stats(isg))}")
    print(f"  {'':<22} OOS {f(stats(oos))}")


def main():
    days = V.load_days()
    ema = V.ema20_map(days)
    caus = [t for t in V.detect_causal(days, ema)
            if t["depth_frac"] >= V.MIN_DEPTH_FRAC and t["entry_min"] < V.NOON]
    longs = [t for t in caus if t["up"]]
    shorts = [t for t in caus if not t["up"]]
    print(f"causal setups: all={len(caus)} long={len(longs)} short={len(shorts)}\n")

    for name, tcs in (("多空全做", caus), ("只做多", longs), ("只做空", shorts)):
        print(f"=== {name} ===")
        show("L3 全出(baseline)", tcs, days, mode="L3")
        for tf in (0.5, 0.75, 1.0):
            show(f"trail {tf} 抱尾長尾", tcs, days, mode="trail", trail_frac=tf)
        print()


if __name__ == "__main__":
    main()

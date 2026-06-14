"""causal 全量 1260 筆按「方向」「星期」「方向×星期」分類，各看 IS/OOS 是否一致。

目的：是否有某個子群（只做多/只做空、某星期）仍有真 edge？
若某群好但 IS/OOS 不一致 → 挑樣本假象，不採信。

跑法：uv run python research/archive/confirmed/H120-l2-pullback-continuation/analyze_segments.py
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict

import validate_causal as V

WD = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def m(trs):
    if not trs:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    sd = st.pstdev(pcts) if len(pcts) > 1 else 0
    return {"N": len(trs), "win": 100 * wins / len(trs), "EV": st.mean([t["pnl"] for t in trs]),
            "tot": sum(pcts), "sh": st.mean(pcts) / sd if sd else 0}


def line(label, trs):
    a = m(trs)
    if not a:
        print(f"  {label:<16} N=0")
        return
    isg = m([t for t in trs if t["date"] < V.OOS_START])
    oos = m([t for t in trs if t["date"] >= V.OOS_START])
    f = lambda x: f"win={x['win']:5.1f}% EV={x['EV']:6.1f} tot={x['tot']:7.1f}% sh={x['sh']:6.3f}" if x else "N=0"
    print(f"  {label:<16} N={a['N']:>4} | ALL {f(a)}")
    print(f"  {'':<16}        | IS  {f(isg)}")
    print(f"  {'':<16}        | OOS {f(oos)}")


def main():
    days = V.load_days()
    ema = V.ema20_map(days)
    caus = [t for t in V.detect_causal(days, ema)
            if t["depth_frac"] >= V.MIN_DEPTH_FRAC and t["entry_min"] < V.NOON]
    trs = V.run(caus, days)
    for t in trs:
        t["wd"] = t["date"].weekday()

    print(f"全量 causal N={len(trs)}\n")

    print("=== 按方向 ===")
    line("只做多 (long)", [t for t in trs if t["up"]])
    line("只做空 (short)", [t for t in trs if not t["up"]])

    print("\n=== 按星期（全方向）===")
    for w in range(5):
        line(WD[w], [t for t in trs if t["wd"] == w])

    print("\n=== 方向 × 星期 ===")
    for up, tag in ((True, "多"), (False, "空")):
        for w in range(5):
            line(f"{tag} {WD[w]}", [t for t in trs if t["up"] == up and t["wd"] == w])
        print()


if __name__ == "__main__":
    main()

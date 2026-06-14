"""H120 進一步分析：時間桶 / 多空 / 星期 / 多頭空頭 regime 切面.

用 backtest.py 的 detect+simulate（含 overshoot guard），最終參數 alpha=0.75, mode=L3, cost=3。
全樣本 2021–2026。Regime 代理：前一日收盤 vs 20 日日線均線（因果，開盤即知）。
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("bt", str(Path(__file__).parent / "backtest.py"))
bt = importlib.util.module_from_spec(spec)
sys.modules["bt"] = bt
spec.loader.exec_module(bt)

ALPHA, MODE, COST = 0.75, "L3", 3
WD = ["一", "二", "三", "四", "五", "六", "日"]


def regime_map(days):
    """每日 regime：前一日收盤 vs 前 20 日收盤均線。回傳 {date: '多頭'/'空頭'}。"""
    sd = sorted(days)
    close = {d: days[d][-1][4] for d in sd}
    out = {}
    for i, d in enumerate(sd):
        if i < 20:
            continue
        prev = close[sd[i - 1]]
        sma = sum(close[sd[j]] for j in range(i - 20, i)) / 20
        out[d] = "多頭" if prev >= sma else "空頭"
    return out


def tbucket(m):
    if m < 570:
        return "08:45-09:30"
    if m < 630:
        return "09:30-10:30"
    if m < 690:
        return "10:30-11:30"
    return ">11:30"


def line(label, m):
    if not m:
        print(f"  {label:<14} N=0")
        return
    print(f"  {label:<14} N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>5}pt "
          f"tot={m['tot%']:>7}% sharpe={m['sharpe']:>6} mdd={m['mdd%']:>6}% maxLoss={m['maxLoss']:>2} avgR={m['avgR']}")


def main():
    days = bt.load_all()
    ema = bt.ema20_map(days)
    reg = regime_map(days)
    tcs = bt.detect(days, ema)
    trs = []
    for tc in tcs:
        r = bt.simulate(tc, days[tc["date"]], alpha=ALPHA, mode=MODE, trail_frac=0, cost=COST)
        r.update(date=tc["date"], up=tc["up"], side="多" if tc["up"] else "空",
                 tb=tbucket(tc["entry_min"]), wd=tc["date"].weekday(),
                 reg=reg.get(tc["date"]), year=tc["date"].year)
        trs.append(r)
    print(f"全樣本 trigger A：N={len(trs)}（2021-2026, ≤13:45 全時段）\n")

    def grp(key, order=None):
        g = defaultdict(list)
        for t in trs:
            g[key(t)].append(t)
        keys = order or sorted(k for k in g if k is not None)
        return [(k, bt.metrics(g[k])) for k in keys]

    print("=== 1) 進場時間桶 ===")
    for k, m in grp(lambda t: t["tb"], ["08:45-09:30", "09:30-10:30", "10:30-11:30", ">11:30"]):
        line(k, m)

    print("\n=== 2) 多 / 空 ===")
    for k, m in grp(lambda t: t["side"], ["多", "空"]):
        line(k, m)

    print("\n=== 3) 星期 ===")
    for k, m in grp(lambda t: t["wd"], [0, 1, 2, 3, 4]):
        line(f"週{WD[k]}", m)

    print("\n=== 4) Regime 多頭 / 空頭（前日收盤 vs 20日均線）===")
    for k, m in grp(lambda t: t["reg"], ["多頭", "空頭"]):
        line(k, m)

    print("\n=== 5) ★ 交易方向 × Regime（順勢 vs 逆勢）===")
    for side in ("多", "空"):
        for rg in ("多頭", "空頭"):
            sub = [t for t in trs if t["side"] == side and t["reg"] == rg]
            tag = "順勢" if (side, rg) in (("多", "多頭"), ("空", "空頭")) else "逆勢"
            line(f"{side}@{rg}({tag})", bt.metrics(sub))

    print("\n=== 6) 時間桶 × 多空 ===")
    for tb in ("08:45-09:30", "09:30-10:30", "10:30-11:30", ">11:30"):
        for side in ("多", "空"):
            sub = [t for t in trs if t["tb"] == tb and t["side"] == side]
            line(f"{tb} {side}", bt.metrics(sub))


if __name__ == "__main__":
    main()

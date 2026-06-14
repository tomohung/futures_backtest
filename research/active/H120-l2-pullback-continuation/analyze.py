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
    # 使用者指定三段：08:45-10:30 / 10:30-12:00 / 12:00-13:45
    if m < 630:
        return "08:45-10:30"
    if m < 720:
        return "10:30-12:00"
    return "12:00-13:45"


def tbucket30(m):
    """30 分鐘梯度（找更好切法）。"""
    base = 525
    lo = base + ((m - base) // 30) * 30
    return f"{lo // 60:02d}:{lo % 60:02d}"


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
                 tb=tbucket(tc["entry_min"]), entry_min=tc["entry_min"], wd=tc["date"].weekday(),
                 reg=reg.get(tc["date"]), year=tc["date"].year)
        trs.append(r)
    ndays = len({t["date"] for t in trs}) or 1
    ntotaldays = len(ema)
    print(f"全樣本 trigger A：N={len(trs)}（2021-2026, 全時段），有訊號日={ndays}, 交易日={ntotaldays}\n")

    def grp(key, order=None):
        g = defaultdict(list)
        for t in trs:
            g[key(t)].append(t)
        keys = order or sorted(k for k in g if k is not None)
        return [(k, bt.metrics(g[k])) for k in keys]

    def line_freq(label, m):
        """機會(筆/日) + 期望值。"""
        if not m:
            print(f"  {label:<14} N=0")
            return
        per_day = m["N"] / ntotaldays
        print(f"  {label:<14} N={m['N']:>4} ({per_day:.2f}筆/日) win={m['win%']:>5}% "
              f"EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% sharpe={m['sharpe']:>6} avgR={m['avgR']}")

    print("=== 1) 你指定的三段（機會 + 期望值）===")
    for k, m in grp(lambda t: t["tb"], ["08:45-10:30", "10:30-12:00", "12:00-13:45"]):
        line_freq(k, m)

    print("\n=== 1b) 三段 × 多空 ===")
    for tb in ("08:45-10:30", "10:30-12:00", "12:00-13:45"):
        for side in ("多", "空"):
            line_freq(f"{tb} {side}", bt.metrics([t for t in trs if t["tb"] == tb and t["side"] == side]))

    print("\n=== 1c) 30 分鐘梯度（找更好的切法）===")
    g30 = defaultdict(list)
    for t in trs:
        g30[tbucket30(t["entry_min"])].append(t)
    for k in sorted(g30):
        line_freq(k, bt.metrics(g30[k]))

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

    # ---- 日內順序：第一筆 vs 後續，並與「時段」拆開 ----
    by_date = defaultdict(list)
    for t in trs:
        by_date[t["date"]].append(t)
    for d in by_date:
        by_date[d].sort(key=lambda x: x["entry_min"])
        for i, t in enumerate(by_date[d]):
            t["order"] = i + 1
            t["n_in_day"] = len(by_date[d])

    print("\n=== 7) 一天進場筆數分佈 ===")
    from collections import Counter
    cnt = Counter(len(v) for v in by_date.values())
    for k in sorted(cnt):
        print(f"  {k} 筆/日：{cnt[k]} 天")

    print("\n=== 8) ★ 日內第 n 筆（含平均進場時間，看是否=早盤）===")
    def ordkey(t):
        return t["order"] if t["order"] <= 3 else 4
    for o in (1, 2, 3, 4):
        sub = [t for t in trs if ordkey(t) == o]
        if not sub:
            continue
        avg_min = sum(t["entry_min"] for t in sub) / len(sub)
        lbl = f"第{o}筆" if o < 4 else "第4+筆"
        m = bt.metrics(sub)
        print(f"  {lbl:<8} 平均進場={avg_min//60:02.0f}:{avg_min%60:02.0f}  {bt.fmt(m)}")

    print("\n=== 9) ★ 控制時段：同一時段內 第1筆 vs 後續（拆開順序 vs 時段）===")
    for tb in ("08:45-10:30", "10:30-12:00", "12:00-13:45"):
        first = [t for t in trs if t["tb"] == tb and t["order"] == 1]
        rest = [t for t in trs if t["tb"] == tb and t["order"] >= 2]
        print(f"  [{tb}]")
        line("  第1筆", bt.metrics(first))
        line("  第2+筆", bt.metrics(rest))

    print("\n=== 10) ≤12:00 進場上限 IS/OOS（部署設定）===")
    cut = [t for t in trs if t["entry_min"] < 720]
    is_c = [t for t in cut if t["year"] < 2025]
    oos_c = [t for t in cut if t["year"] >= 2025]
    line("全樣本", bt.metrics(cut))
    line("IS<2025", bt.metrics(is_c))
    line("OOS>=2025", bt.metrics(oos_c))


if __name__ == "__main__":
    main()

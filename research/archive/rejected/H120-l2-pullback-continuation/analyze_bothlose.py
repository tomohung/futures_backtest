"""列出 causal 全量中「同一天多、空兩邊都淨賠」的交易日（被雙巴）。

定義：當日 ≥1 多單且 ≥1 空單，且多單合計 pnl<0 且空單合計 pnl<0。
跑法：uv run python research/archive/rejected/H120-l2-pullback-continuation/analyze_bothlose.py
"""
from __future__ import annotations

from collections import defaultdict

import validate_causal as V


def main():
    days = V.load_days()
    ema = V.ema20_map(days)
    caus = [t for t in V.detect_causal(days, ema)
            if t["depth_frac"] >= V.MIN_DEPTH_FRAC and t["entry_min"] < V.NOON]
    trs = V.run(caus, days)

    by_day = defaultdict(list)
    for t in trs:
        by_day[t["date"]].append(t)

    both = []
    for d, ts in by_day.items():
        longs = [t for t in ts if t["up"]]
        shorts = [t for t in ts if not t["up"]]
        if not longs or not shorts:
            continue
        lp = sum(t["pnl"] for t in longs)
        sp = sum(t["pnl"] for t in shorts)
        if lp < 0 and sp < 0:
            both.append((d, lp, sp, longs, shorts))

    both.sort(key=lambda x: x[1] + x[2])   # 最慘（合計虧最多）在前
    tot_days = sum(1 for ts in by_day.values()
                   if any(t["up"] for t in ts) and any(not t["up"] for t in ts))
    print(f"有多空並存的交易日={tot_days}；其中多空都淨賠={len(both)} 天\n")

    def hhmm(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    print("=== 雙巴最慘 5 天 ===")
    for d, lp, sp, longs, shorts in both[:5]:
        print(f"\n【{d} ({['Mon','Tue','Wed','Thu','Fri'][d.weekday()]})】"
              f" 多 {lp:+.1f}pt / 空 {sp:+.1f}pt / 合計 {lp+sp:+.1f}pt")
        for t in sorted(longs + shorts, key=lambda x: x["entry_min"]):
            tc = t["tc"]
            side = "多" if t["up"] else "空"
            print(f"    {hhmm(t['entry_min'])} {side} entry={tc['entry']:.0f} "
                  f"exit={hhmm(t['exit_min'])}@{t['exitp']:.0f} "
                  f"{'WIN ' if t['win'] else 'LOSS'} {t['pnl']:+.1f}pt "
                  f"depth={tc['depth_frac']:.2f}")


if __name__ == "__main__":
    main()

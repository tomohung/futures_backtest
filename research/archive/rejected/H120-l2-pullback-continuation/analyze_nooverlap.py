"""causal 全量套用「單部位」約束：已有部位未出場時，跳過後續訊號（不重疊進場）。

完全 causal（只用進場/出場時間先後，無未來資訊）。比較三種規則：
  - 全進（baseline，可重疊）
  - 單部位（任何方向只要有未平倉就不進）
  - 單部位/同向（只擋同方向重疊，多空可並存）
日內策略：重疊只會發生在同一交易日內（每日 13:45 全平）。

跑法：uv run python research/archive/confirmed/H120-l2-pullback-continuation/analyze_nooverlap.py
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict

import validate_causal as V


def stats(trs):
    if not trs:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    sd = st.pstdev(pcts) if len(pcts) > 1 else 0
    eq = peak = mdd = 0.0
    for t in sorted(trs, key=lambda x: (x["date"], x["entry_min"])):
        eq += t["pct"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"N": len(trs), "win": 100 * wins / len(trs), "EV": st.mean([t["pnl"] for t in trs]),
            "tot": sum(pcts), "sh": st.mean(pcts) / sd if sd else 0, "mdd": mdd}


def f(x):
    return (f"N={x['N']:>4} win={x['win']:5.1f}% EV={x['EV']:6.1f} tot={x['tot']:7.1f}% "
            f"sh={x['sh']:6.3f} mdd={x['mdd']:6.1f}%") if x else "N=0"


def show(label, trs):
    isg = [t for t in trs if t["date"] < V.OOS_START]
    oos = [t for t in trs if t["date"] >= V.OOS_START]
    print(f"  {label}")
    print(f"    ALL {f(stats(trs))}")
    print(f"    IS  {f(stats(isg))}")
    print(f"    OOS {f(stats(oos))}")


def no_overlap(trs, same_dir_only=False):
    """按 (date, entry_min) 排序逐筆掃；持倉中(entry < open_exit)則跳過。"""
    kept = []
    by_day = defaultdict(list)
    for t in trs:
        by_day[t["date"]].append(t)
    for d in sorted(by_day):
        day = sorted(by_day[d], key=lambda x: (x["entry_min"], 0 if x["up"] else 1))
        open_exit = {True: -1, False: -1} if same_dir_only else {"any": -1}
        for t in day:
            k = t["up"] if same_dir_only else "any"
            if t["entry_min"] < open_exit[k]:
                continue                      # 仍持倉 → 跳過此訊號
            kept.append(t)
            open_exit[k] = t["exit_min"]
    return kept


def main():
    days = V.load_days()
    ema = V.ema20_map(days)
    caus = [t for t in V.detect_causal(days, ema)
            if t["depth_frac"] >= V.MIN_DEPTH_FRAC and t["entry_min"] < V.NOON]
    trs = V.run(caus, days)

    base = trs
    single = no_overlap(trs, same_dir_only=False)
    single_dir = no_overlap(trs, same_dir_only=True)

    print(f"全量 causal N={len(base)}；單部位後 N={len(single)}（跳過 {len(base)-len(single)}）；"
          f"單部位/同向後 N={len(single_dir)}\n")

    print("=== baseline（可重疊，全進）===")
    show("all", base)
    print("\n=== 單部位（任何未平倉就不進）===")
    show("all", single)
    print("\n=== 單部位/同向（多空可並存，僅擋同向）===")
    show("all", single_dir)

    # 被跳過的那些訊號本身表現如何？（驗證『後面訊號較差』直覺）
    skipped_keys = {(t["date"], t["entry_min"], t["up"]) for t in single}
    skipped = [t for t in base if (t["date"], t["entry_min"], t["up"]) not in skipped_keys]
    print("\n=== 被跳過的訊號（第二筆以後）本身表現 ===")
    show("skipped", skipped)

    # 單部位 + 只做空（前面分析空方較穩）
    print("\n=== 單部位 ∩ 只做空 ===")
    show("short-only", [t for t in single if not t["up"]])
    print("\n=== 單部位 ∩ 只做多 ===")
    show("long-only", [t for t in single if t["up"]])

    # 逐年（單部位）
    print("\n=== 單部位 逐年 ===")
    by_year = defaultdict(list)
    for t in single:
        by_year[t["date"].year].append(t)
    for y in sorted(by_year):
        print(f"  {y} {f(stats(by_year[y]))}")


if __name__ == "__main__":
    main()

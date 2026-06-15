"""S005 / H120 causal 交易的「日內序列」分析（衍生問題，非可部署 edge）。

問題：一天多筆單時，若「前一筆」已走到 L4/L5，下一筆走到 L3/L4/L5 的機率分佈如何？
      又前一筆是當日第 1/2/3 筆的分佈如何？

注意：S005 已退役（causal 無 edge）。本腳本純做事後序列描述，並附**虛無對照**
（無條件下一筆 reach 分佈、以及把每日序列洗牌的 IID null），避免把邊際分佈誤當自相關。

reach 定義（per trade，causal）：進場後沿續攻方向自 anchor 的「最大順勢 excursion」，
量到「本相位結束」＝價格自續攻方向 running 極值反向 ≥ L2 距離（zigzag 反轉）或日終。
reach bucket：L5(≥L5d) > L4(≥L4d) > L3(≥L3d) > <L3。
與停損無關——衡量的是「這筆單的那段行情實際走多遠」，非策略 L3 封頂出場點。

跑法：uv run python research/archive/rejected/H120-l2-pullback-continuation/analyze_sequence.py
"""
from __future__ import annotations

import importlib.util
import statistics as st
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 從 confirmed 目錄載入 validate_causal（detect_causal / load_days / ema20_map / 常數）
VC_PATH = (HERE.parents[1] / "confirmed/H120-l2-pullback-continuation/validate_causal.py")
if not VC_PATH.exists():
    VC_PATH = HERE / "validate_causal.py"  # fallback
spec = importlib.util.spec_from_file_location("vc", VC_PATH)
vc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vc)

MIN_DEPTH_FRAC = vc.MIN_DEPTH_FRAC
NOON = vc.NOON
OOS_START = vc.OOS_START
BUCKETS = ["<L3", "L3", "L4", "L5"]


def reach_bucket(tc, bars):
    """進場後沿續攻方向自 anchor 的最大 excursion → ladder bucket（相位內，causal）。"""
    up = tc["up"]
    anchor = tc["anchor"]
    L3d, L4d, L5d = tc["L3d"], tc["L4d"], tc["L5d"]
    L2d = L3d / vc.L3C * vc.L2C  # 還原 L2 距離（反轉門檻）
    fwd = bars[tc["entry_i"] + 1:]
    ext = tc["peak"]  # 進場時的續攻方向 running 極值
    max_fav = (ext - anchor) if up else (anchor - ext)
    for m, o, h, l, c in fwd:
        if up:
            if h > ext:
                ext = h
            max_fav = max(max_fav, ext - anchor)
            if ext - l >= L2d:   # 相位反轉（自波峰回 L2）→ 結束
                break
        else:
            if l < ext:
                ext = l
            max_fav = max(max_fav, anchor - ext)
            if h - ext >= L2d:
                break
    if max_fav >= L5d:
        return "L5"
    if max_fav >= L4d:
        return "L4"
    if max_fav >= L3d:
        return "L3"
    return "<L3"


def pct(part, whole):
    return f"{100*part/whole:4.1f}%" if whole else "   - "


def dist_line(counter, total, label):
    cells = "  ".join(f"{b}={counter.get(b,0):>3}({pct(counter.get(b,0),total)})" for b in BUCKETS)
    return f"  {label:<26} N={total:>4}  {cells}"


def reach_ge_L3(b):
    return b in ("L3", "L4", "L5")


def reach_ge_L4(b):
    return b in ("L4", "L5")


def main():
    days = vc.load_days()
    ema = vc.ema20_map(days)
    caus = [t for t in vc.detect_causal(days, ema)
            if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]

    # 標 reach、依日分組、日內按進場時間排序
    for t in caus:
        t["reach"] = reach_bucket(t, days[t["date"]])
    by_day = defaultdict(list)
    for t in caus:
        by_day[t["date"]].append(t)
    for d in by_day:
        by_day[d].sort(key=lambda t: t["entry_min"])
        for k, t in enumerate(by_day[d]):
            t["ord"] = k + 1            # 當日第幾筆
            t["nday"] = len(by_day[d])  # 當日總筆數

    print(f"=== S005 causal 交易總覽（depth>=0.25, 進場<12:00） ===")
    print(f"總筆數 N={len(caus)}   交易日數={len(by_day)}")
    nday_hist = Counter(len(v) for v in by_day.values())
    print("每日筆數分佈：" + "  ".join(f"{k}筆×{nday_hist[k]}日" for k in sorted(nday_hist)))
    multi_days = sum(1 for v in by_day.values() if len(v) >= 2)
    print(f"多筆日（>=2筆）= {multi_days} 日\n")

    # 無條件 reach 分佈（base rate）
    all_reach = Counter(t["reach"] for t in caus)
    print("--- (A) 無條件 reach 分佈（所有交易） ---")
    print(dist_line(all_reach, len(caus), "all trades"))
    base_p3 = sum(all_reach[b] for b in ("L3", "L4", "L5")) / len(caus)
    base_p4 = sum(all_reach[b] for b in ("L4", "L5")) / len(caus)
    print(f"  → 任一筆 reach>=L3 = {base_p3:.1%}   reach>=L4 = {base_p4:.1%}\n")

    # 相鄰對：所有「有前一筆」的下一筆（= 無條件「下一筆」base rate）
    pairs = []  # (prev, nxt)
    for d, v in by_day.items():
        for k in range(1, len(v)):
            pairs.append((v[k - 1], v[k]))
    next_all = Counter(n["reach"] for _, n in pairs)
    print("--- (B) 相鄰對：下一筆 reach 分佈（不分前一筆，base rate of 'next') ---")
    print(dist_line(next_all, len(pairs), "any next"))

    # 條件：前一筆 reach>=L4（L4 or L5）
    cond = [(p, n) for p, n in pairs if reach_ge_L4(p["reach"])]
    cond_next = Counter(n["reach"] for _, n in cond)
    print("\n--- (C) 條件：前一筆走到 L4/L5 → 下一筆 reach 分佈 ---")
    print(dist_line(cond_next, len(cond), "next | prev>=L4"))

    # 對照：前一筆 < L4（沒走到 L4/L5）
    anti = [(p, n) for p, n in pairs if not reach_ge_L4(p["reach"])]
    anti_next = Counter(n["reach"] for _, n in anti)
    print(dist_line(anti_next, len(anti), "next | prev<L4"))

    if cond:
        c3 = sum(cond_next[b] for b in ("L3", "L4", "L5")) / len(cond)
        c4 = sum(cond_next[b] for b in ("L4", "L5")) / len(cond)
        print(f"\n  下一筆 reach>=L3 : 條件={c3:.1%}  vs base(next)="
              f"{sum(next_all[b] for b in ('L3','L4','L5'))/len(pairs):.1%}  vs 全體={base_p3:.1%}")
        print(f"  下一筆 reach>=L4 : 條件={c4:.1%}  vs base(next)="
              f"{sum(next_all[b] for b in ('L4','L5'))/len(pairs):.1%}  vs 全體={base_p4:.1%}")

    # 細分：前一筆 L4 vs L5 分開看
    print("\n--- (C2) 再細分前一筆 = L4 / = L5 ---")
    for lvl in ("L4", "L5"):
        sub = [(p, n) for p, n in pairs if p["reach"] == lvl]
        print(dist_line(Counter(n["reach"] for _, n in sub), len(sub), f"next | prev=={lvl}"))

    # 前一筆（走到 L4/L5 者）是當日第幾筆
    print("\n--- (D) 『前一筆走到 L4/L5』時，那一筆是當日第幾筆？ ---")
    ord_hist = Counter(p["ord"] for p, _ in cond)
    tot = len(cond)
    for o in sorted(ord_hist):
        print(f"  第{o}筆：{ord_hist[o]:>3} ({pct(ord_hist[o], tot)})")
    print(f"  （樣本＝所有『前一筆 reach>=L4 且其後當日還有下一筆』的配對，N={tot}）")

    # 對照：所有「能當前一筆」（即非當日最後一筆）的序位分佈
    print("\n  對照：所有『非當日最後一筆』的序位分佈（誰有資格當 prev）")
    base_ord = Counter(p["ord"] for p, _ in pairs)
    for o in sorted(base_ord):
        print(f"  第{o}筆：{base_ord[o]:>3} ({pct(base_ord[o], len(pairs))})")

    # IID null：每日序列內洗牌 reach，重算條件機率（檢驗序列結構是否非隨機）
    # 用 deterministic 排列（不可呼叫 random）：固定種子式循環移位平均
    print("\n--- (E) IID 對照（日內序列循環移位，破壞順序相依） ---")
    shifts = []
    for s in range(1, 6):
        sc = []  # (prev_reach, next_reach) after cyclic shift of reach labels within day
        for d, v in by_day.items():
            if len(v) < 2:
                continue
            labels = [t["reach"] for t in v]
            rot = labels[s % len(labels):] + labels[:s % len(labels)]
            for k in range(1, len(rot)):
                sc.append((rot[k - 1], rot[k]))
        cN = [(p, n) for p, n in sc if reach_ge_L4(p)]
        if cN:
            g3 = sum(1 for p, n in cN if reach_ge_L3(n)) / len(cN)
            shifts.append(g3)
    if shifts:
        print(f"  下一筆 reach>=L3 | prev>=L4，洗牌後 5 次：" +
              "  ".join(f"{x:.0%}" for x in shifts) +
              f"   均值={st.mean(shifts):.1%}")
        print("  （若觀測值(C)落在洗牌帶內，代表『前一筆走到 L4/L5』不帶額外資訊）")

    # ============ 方向切角 ============
    def opp(p, n):
        return p["side"] != n["side"]

    print("\n--- (F) 方向：前一筆 vs 下一筆（base rate of '反向'） ---")
    # base：所有相鄰對，下一筆反向比例
    base_opp = sum(1 for p, n in pairs if opp(p, n))
    print(f"  任一相鄰對    N={len(pairs):>4}  反向={base_opp}({pct(base_opp,len(pairs))})  "
          f"同向={len(pairs)-base_opp}({pct(len(pairs)-base_opp,len(pairs))})")

    print("\n--- (G) 條件：前一筆走到 L4/L5 → 下一筆方向 ---")
    for lbl, sel in [("next | prev>=L4", reach_ge_L4),
                     ("next | prev==L4", lambda b: b == "L4"),
                     ("next | prev==L5", lambda b: b == "L5"),
                     ("next | prev<L4 ", lambda b: not reach_ge_L4(b))]:
        sub = [(p, n) for p, n in pairs if sel(p["reach"])]
        if not sub:
            continue
        o = sum(1 for p, n in sub if opp(p, n))
        print(f"  {lbl:<16} N={len(sub):>4}  反向={o}({pct(o,len(sub))})  "
              f"同向={len(sub)-o}({pct(len(sub)-o,len(sub))})")

    print("\n--- (H) 條件：前一筆走到 L4/L5 且下一筆『反向』→ 下一筆 reach 分佈 ---")
    cond_opp = [(p, n) for p, n in pairs if reach_ge_L4(p["reach"]) and opp(p, n)]
    cond_same = [(p, n) for p, n in pairs if reach_ge_L4(p["reach"]) and not opp(p, n)]
    print(dist_line(Counter(n["reach"] for _, n in cond_opp), len(cond_opp), "next(反向) | prev>=L4"))
    print(dist_line(Counter(n["reach"] for _, n in cond_same), len(cond_same), "next(同向) | prev>=L4"))
    # 對照：所有反向下一筆的 reach（不分前一筆）
    all_opp = [(p, n) for p, n in pairs if opp(p, n)]
    print(dist_line(Counter(n["reach"] for _, n in all_opp), len(all_opp), "next(反向) | 任一前筆"))
    if cond_opp:
        g3 = sum(1 for _, n in cond_opp if reach_ge_L3(n["reach"])) / len(cond_opp)
        b3 = sum(1 for _, n in all_opp if reach_ge_L3(n["reach"])) / len(all_opp)
        print(f"\n  反向下一筆 reach>=L3 : 條件(prev>=L4)={g3:.1%}  vs base(任一反向)={b3:.1%}")


if __name__ == "__main__":
    main()

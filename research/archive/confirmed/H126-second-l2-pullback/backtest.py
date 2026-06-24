"""H126 Phase 2 backtest — 同向第二次 L2 拉回續攻（2nd+），entry∈[09:30,11:30].

偵測用 **causal** services/l2_pullback.detect_day（與 explore 同源，無前視；H120 的 zigzag_legs 版
有前視已作廢，不沿用）。出場/指標沿用 H120 backtest 的 simulate/metrics（causal）。

驗證重點（H126 distribution「Phase 2 必驗」）：
  (a) 真實停損下 2nd+ ∈[09:30,11:30] 的 EV 是否轉正（母體 H120 近 break-even）
  (b) 目標 L3 vs L4 vs L5 vs trail 的淨賠率（用戶論點：第二次可瞄更遠）
  (c) 對照組「同時段同目標的 1st」量化序數增量
  (d) 11:30 / 12:00 cutoff 敏感度
停損：stop = pb_ext − alpha×(pb_ext − anchor)；成本：每筆扣 cost_pt（round-trip）。
績效用損益%（CLAUDE.md 標準），Sharpe 基於損益%。

用法：uv run python research/active/H126-second-l2-pullback/backtest.py
"""
from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.chart_ui import paths
from src.chart_ui.services.l2_pullback import COEF, detect_day

SYMBOL = "TX"
EMA_SPAN = 20
RESULTS = Path(__file__).parent / "results"
OOS_START = date(2025, 1, 1)        # IS < 2025, OOS >= 2025
WIN_LO, WIN_HI = 570, 690           # 09:30–11:30（H126 edge 窗）
COST = 3.0


# ---------- 資料 ----------
def load_all():
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low, close "
            "FROM ohlcv_1m WHERE symbol=? AND CAST(timestamp AS TIME) "
            "BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp", [SYMBOL]).fetchall()
    days = defaultdict(list)
    for d, t, o, h, l, c in rows:
        days[d].append((t.hour * 60 + t.minute, float(o), float(h), float(l), float(c)))
    return days


def ema20_map(days):
    sd = sorted(days)
    rng = {d: max(h for _, _, h, _, _ in b) - min(l for _, _, _, l, _ in b) for d, b in days.items()}
    out, a = {}, 2.0 / (EMA_SPAN + 1)
    for i, d in enumerate(sd):
        prior = sd[max(0, i - 120):i]
        if len(prior) < EMA_SPAN:
            continue
        e = rng[prior[0]]
        for pd in prior[1:]:
            e = a * rng[pd] + (1 - a) * e
        out[d] = e
    return out


# ---------- 偵測（causal detect_day + 同向序數）----------
def detect(days, ema):
    out = []
    for d in sorted(ema):
        bars = days[d]
        if len(bars) < 5:
            continue
        entries, dist = detect_day(bars, ema[d])
        if not entries:
            continue
        sc = defaultdict(int)
        for e in entries:
            sc[e["side"]] += 1
            up = e["side"] == "long"
            out.append({
                "date": d, "up": up, "ordinal": sc[e["side"]],
                "is_2nd": sc[e["side"]] >= 2,
                "entry_i": e["entry_i"], "entry_min": e["entry_min"], "entry": e["entry"],
                "anchor": e["anchor"], "pb_low": e["pb_ext"],
                "L3d": dist["L3"], "L4d": dist["L4"], "L5d": dist["L5"],
            })
    return out


# ---------- 出場模擬 ----------
def simulate(tc, bars, *, alpha, target, trail_frac, cost):
    """target ∈ {'L3','L4','L5','trail'}；trail = 達 L3 後以 trail_frac×L3d 追蹤博 L4/L5。"""
    up, entry, anchor, pb_low = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    L3d = tc["L3d"]
    tgt_d = {"L3": tc["L3d"], "L4": tc["L4d"], "L5": tc["L5d"], "trail": tc["L3d"]}[target]
    stop = pb_low - alpha * (pb_low - anchor) if up else pb_low + alpha * (anchor - pb_low)
    tgt = anchor + tgt_d if up else anchor - tgt_d
    risk = (entry - stop) if up else (stop - entry)
    fwd = bars[tc["entry_i"] + 1:]
    outcome, exitp, mae = "open", bars[-1][4], 0.0
    trailing, trail_dist, hit = None, trail_frac * L3d, False
    for m, o, h, l, c in fwd:
        mae = max(mae, (entry - l) if up else (h - entry))
        cur_stop = trailing if trailing is not None else stop
        if (l <= cur_stop) if up else (h >= cur_stop):
            outcome, exitp = ("trail_exit" if trailing is not None else "loss"), cur_stop
            break
        reached = (h >= tgt) if up else (l <= tgt)
        if reached and not hit:
            hit = True
            if target != "trail":
                outcome, exitp = "win", tgt
                break
            trailing = (tgt - trail_dist) if up else (tgt + trail_dist)
        if target == "trail" and hit:
            newt = (h - trail_dist) if up else (l + trail_dist)
            trailing = max(trailing, newt) if up else min(trailing, newt)
    pnl = ((exitp - entry) if up else (entry - exitp)) - cost
    return {"outcome": outcome, "pnl": pnl, "pct": pnl / entry * 100, "risk": risk,
            "R": (pnl / risk) if risk > 0 else None, "mae": mae, "win": pnl > 0}


def metrics(trs):
    n = len(trs)
    if not n:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    mean = st.mean(pcts)
    sd = st.pstdev(pcts) if n > 1 else 0
    eq, peak, mdd, cur, mx = 0.0, 0.0, 0.0, 0, 0
    for t in trs:
        eq += t["pct"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        cur = 0 if t["win"] else cur + 1
        mx = max(mx, cur)
    rs = [t["R"] for t in trs if t["R"] is not None]
    return {"N": n, "win%": round(100 * wins / n, 1), "EVpt": round(st.mean([t["pnl"] for t in trs]), 1),
            "tot%": round(sum(pcts), 1), "mean%": round(mean, 4),
            "sharpe": round(mean / sd, 3) if sd else 0, "mdd%": round(mdd, 1),
            "maxLoss": mx, "avgR": round(st.mean(rs), 2) if rs else 0}


def fmt(m):
    if not m:
        return "N=0"
    return (f"N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>6}pt tot={m['tot%']:>8}% "
            f"sharpe={m['sharpe']:>7} mdd={m['mdd%']:>7}% maxLoss={m['maxLoss']:>2} avgR={m['avgR']:>5}")


def run(tcs, days, **kw):
    return [dict(simulate(tc, days[tc["date"]], **kw), date=tc["date"], entry_min=tc["entry_min"])
            for tc in tcs]


def win(tcs, lo=WIN_LO, hi=WIN_HI, only_2nd=None):
    out = [t for t in tcs if lo <= t["entry_min"] < hi]
    if only_2nd is True:
        out = [t for t in out if t["is_2nd"]]
    elif only_2nd is False:
        out = [t for t in out if not t["is_2nd"]]
    return out


def main():
    RESULTS.mkdir(exist_ok=True)
    days = load_all()
    ema = ema20_map(days)
    tcs = detect(days, ema)
    n2 = sum(t["is_2nd"] for t in tcs)
    print(f"setups (causal detect_day): N={len(tcs)}  (2nd+ {n2})")

    T2 = win(tcs, only_2nd=True)      # 2nd+ in 09:30–11:30（主樣本）
    T1 = win(tcs, only_2nd=False)     # 1st  in 09:30–11:30（對照）
    IS2 = [t for t in T2 if t["date"] < OOS_START]
    OOS2 = [t for t in T2 if t["date"] >= OOS_START]
    print(f"主樣本 2nd+∈[09:30,11:30]: N={len(T2)} (IS<2025 {len(IS2)} / OOS≥2025 {len(OOS2)})")
    print(f"對照 1st∈[09:30,11:30]:    N={len(T1)}\n")

    K = dict(trail_frac=0.0, cost=COST)
    # 1) 停損 alpha 敏感度（IS 2nd+, target L3）
    print("=== 1) 停損 alpha 敏感度 (IS 2nd+, target=L3, cost=3) ===")
    best = None
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        m = metrics(run(IS2, days, alpha=alpha, target="L3", **K))
        print(f"  alpha={alpha:<4} {fmt(m)}")
        if best is None or (m and m["sharpe"] > best[1]["sharpe"]):
            best = (alpha, m)
    ba = best[0]
    print(f"  -> IS best Sharpe @ alpha={ba}")

    # 2) 目標 L3/L4/L5/trail（IS 2nd+, best alpha）—— 核心：能否瞄更遠
    print(f"\n=== 2) 目標模式 (IS 2nd+, alpha={ba}, cost=3) — 第二次能否瞄更遠 ===")
    for tg in ("L3", "L4", "L5"):
        print(f"  target={tg:<6} {fmt(metrics(run(IS2, days, alpha=ba, target=tg, **K)))}")
    for tf in (0.5, 0.75, 1.0):
        print(f"  trail {tf:<4}   {fmt(metrics(run(IS2, days, alpha=ba, target='trail', trail_frac=tf, cost=COST)))}")

    # 3) 對照組 2nd+ vs 1st（同窗同目標，全樣本與 IS）—— 序數增量
    print(f"\n=== 3) 序數增量 2nd+ vs 1st (alpha={ba}, 09:30–11:30) ===")
    for tg in ("L3", "L4"):
        print(f"  target={tg}")
        print(f"    2nd+ (all) {fmt(metrics(run(T2, days, alpha=ba, target=tg, **K)))}")
        print(f"    1st  (all) {fmt(metrics(run(T1, days, alpha=ba, target=tg, **K)))}")

    # 4) 成本敏感度（IS 2nd+, best alpha, target L4）
    print(f"\n=== 4) 成本敏感度 (IS 2nd+, alpha={ba}, target=L4) ===")
    for c in (0, 2, 3, 4, 6):
        print(f"  cost={c}pt  {fmt(metrics(run(IS2, days, alpha=ba, target='L4', trail_frac=0.0, cost=c)))}")

    # 5) cutoff 敏感度（11:30 vs 12:00 vs 全日；2nd+, best alpha, L4）
    print(f"\n=== 5) cutoff 敏感度 (2nd+, alpha={ba}, target=L4, cost=3) ===")
    for lo, hi, nm in ((570, 690, "09:30–11:30"), (570, 720, "09:30–12:00"),
                       (570, 826, "09:30–13:45"), (525, 690, "08:45–11:30")):
        print(f"  {nm:<12} {fmt(metrics(run(win(tcs, lo, hi, only_2nd=True), days, alpha=ba, target='L4', **K)))}")

    # 6) ★ IS vs OOS（含 trail 進選擇集；對每個 target 都報 OOS，避免單一選擇誤判）
    print(f"\n=== 6) ★ IS vs OOS (2nd+∈[09:30,11:30], alpha={ba}, cost=3) ===")
    def cfg(tg):
        return dict(alpha=ba, target=("trail" if tg.startswith("trail") else tg),
                    trail_frac=(float(tg.split()[1]) if tg.startswith("trail") else 0.0), cost=COST)
    cands = ["L3", "L4", "L5", "trail 0.5", "trail 1.0"]
    print(f"  {'target':<10} {'IS (N=80)':<78} | OOS (N=40)")
    is_sh = {}
    for tg in cands:
        mi = metrics(run(IS2, days, **cfg(tg)))
        mo = metrics(run(OOS2, days, **cfg(tg)))
        is_sh[tg] = mi["sharpe"]
        print(f"  {tg:<10} IS {fmt(mi)}\n  {'':<10} OOS {fmt(mo)}")
    bt = max(is_sh, key=lambda k: is_sh[k])
    print(f"  -> IS-best target = {bt}（Sharpe {is_sh[bt]}）；上方 OOS 同列即其 holdout 表現")
    print("  ⚠ 記憶 project_oos_equals_highvol_regime：OOS≡高波 regime，與 regime 切換 confounded。")

    # 7) 逐年（2nd+, best alpha, IS-best target + L4 對照）
    print(f"\n=== 7) 逐年 (2nd+∈[09:30,11:30], alpha={ba}, cost=3) ===")
    by_year = defaultdict(list)
    for t in T2:
        by_year[t["date"].year].append(t)
    for tg in (bt, "L4"):
        print(f"  -- target={tg} --")
        for y in sorted(by_year):
            print(f"    {y}  {fmt(metrics(run(by_year[y], days, **cfg(tg))))}")

    # 落地 trades + equity（用 IS-best target）
    trs = run(sorted(T2, key=lambda t: (t["date"], t["entry_min"])), days, **cfg(bt))
    with open(RESULTS / "bt_trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "entry_min", "outcome", "pnl", "pct", "R", "mae", "win"])
        w.writeheader()
        for t in trs:
            w.writerow({k: t[k] for k in ["date", "entry_min", "outcome", "pnl", "pct", "R", "mae", "win"]})
    _equity(trs, ba, bt)
    print(f"\n[saved] results/bt_trades.csv, results/equity_curve.png")


def _equity(trs, alpha, tg):
    eq, xs = 0.0, []
    for t in trs:
        eq += t["pct"]
        xs.append(eq)
    plt.figure(figsize=(11, 5))
    plt.plot(xs, lw=1.2)
    split = sum(1 for t in trs if t["date"] < OOS_START)
    plt.axvline(split, color="r", ls="--", lw=1, label=f"IS/OOS split (n={split})")
    plt.title(f"H126 2nd+ equity (cum PnL%), 09:30-11:30, alpha={alpha}, target={tg}, cost=3pt")
    plt.xlabel("trade #")
    plt.ylabel("cumulative PnL%")
    plt.legend()
    plt.tight_layout()
    plt.savefig(RESULTS / "equity_curve.png", dpi=110)
    plt.close()


if __name__ == "__main__":
    main()

"""H120 Phase 2 backtest — L2 趨勢確立後拉回續攻（trigger A: 5MA 站回）.

Phase 1 結論：trigger A(5MA站回) ≫ N(確立即進) ≫ B(突破)；C 無加值。故固定 A。
本腳本：偵測 → 可掃參數出場模擬（停損 alpha、時間窗、出場模式、成本）→ IS/OOS、
walk-forward、參數敏感度、drawdown/連敗。績效用損益%（CLAUDE.md 標準）。

停損 alpha：stop = pb_low − alpha×(pb_low − anchor)；alpha=0 緊(拉回極值)、alpha=1 寬(錨點)。
出場：mode='L3' 固定 target=錨±L3d；mode='trail' 達 L3 後改 trail（trail_frac×L3d）博 L4/L5。
成本：每筆扣 cost_pts（round-trip，預設 3pt）。

輸出：results/backtest.md 由對話寫；本腳本印表 + results/equity_*.png + bt_trades.csv。
"""
from __future__ import annotations

import csv
import math
import statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.chart_ui import paths
from src.chart_ui.services.swing_legs import zigzag_legs

SYMBOL = "TX"
EMA_SPAN = 20
COEF = {"L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}
RESULTS = Path(__file__).parent / "results"

PB_FLOOR_FRAC = 0.05
MIN_DEPTH_FRAC = 0.25         # 部署最小拉回深度(÷L2)；濾掉淺拉回
OOS_START = date(2025, 1, 1)   # IS < 2025, OOS >= 2025
GATE_0930, GATE_1130 = 570, 690
NOON = 720   # 部署進場上限 12:00（午後尾盤幾乎無 edge，見分時段分析）


# ---------- 資料 ----------
def load_all():
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, "
            "open, high, low, close FROM ohlcv_1m WHERE symbol=? AND CAST(timestamp AS TIME) "
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


def sma(seq, n):
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


# ---------- 偵測（trigger A，每 leg 一筆）----------
def detect(days, ema):
    """回傳 trade-context list（出場政策外掛，不在此固定）。"""
    out = []
    for d in sorted(ema):
        bars = days[d]
        e = ema[d]
        dist = {k: COEF[k] * e for k in COEF}
        L2d, L3d = dist["L2"], dist["L3"]
        pb_floor = PB_FLOOR_FRAC * e
        closes = [b[4] for b in bars]
        s5 = sma(closes, 5)
        legs = zigzag_legs([(m, h, l) for m, _, h, l, _ in bars], threshold=L2d)
        for lg in legs:
            if abs(lg["end_price"] - lg["start_price"]) < L2d:
                continue
            up = lg["dir"] == "up"
            sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
            seg_idx = [i for i, b in enumerate(bars) if sm <= b[0] <= em]
            if len(seg_idx) < 3:
                continue
            # 確立：ext≥L2d
            est_i = None
            ext = 0.0
            for i in seg_idx:
                _, _, h, l, _ = bars[i]
                ext = max(ext, (h - anchor) if up else (anchor - l))
                if ext >= L2d:
                    est_i = i
                    break
            if est_i is None:
                continue
            # 確立後找第一個拉回 + 5MA 站回
            state = "extend"
            peak = None
            for i in seg_idx:
                if i < est_i:
                    continue
                m, o, h, l, c = bars[i]
                if peak is None:
                    peak = h if up else l
                    continue
                if state == "extend":
                    if (h > peak) if up else (l < peak):
                        peak = h if up else l
                    if abs(peak - anchor) >= L3d:   # 已直衝 L3，非可交易
                        break
                    dip = (peak - l) if up else (h - peak)
                    if dip >= pb_floor:
                        state = "pullback"
                        pb_ext = l if up else h
                elif state == "pullback":
                    pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                    cs, ps = s5[i], s5[i - 1]
                    pc = bars[i - 1][4]
                    if cs is not None and ps is not None:
                        reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                        # 進場那根若已爆穿 L3 目標（L2→L3 已走完），非有效 setup，跳過
                        overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                        # 每段一筆：取確立後第一個站回（深度過濾在 main 做，語意=先抓首筆再濾）
                        if reclaim and not overshoot:
                            depth_frac = ((peak - pb_ext) if up else (pb_ext - peak)) / L2d
                            out.append({
                                "date": d, "up": up, "side": "bull" if up else "bear",
                                "entry_i": i, "entry_min": m, "entry": c,
                                "anchor": anchor, "pb_low": pb_ext, "ema20": e,
                                "L3d": L3d, "L4d": dist["L4"], "L5d": dist["L5"],
                                "depth_frac": depth_frac,
                            })
                            break
    return out


# ---------- 出場模擬 ----------
def simulate(tc, bars, *, alpha, mode, trail_frac, cost):
    up, entry, anchor, pb_low = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    L3d = tc["L3d"]
    stop = pb_low - alpha * (pb_low - anchor) if up else pb_low + alpha * (anchor - pb_low)
    target = anchor + L3d if up else anchor - L3d
    risk = (entry - stop) if up else (stop - entry)
    fwd = bars[tc["entry_i"] + 1:]
    outcome, exitp, mae = "open", bars[-1][4], 0.0
    trailing = None
    trail_dist = trail_frac * L3d
    hit_l3 = False
    for m, o, h, l, c in fwd:
        mae = max(mae, (entry - l) if up else (h - entry))
        # 先判停損（保守）
        cur_stop = trailing if trailing is not None else stop
        if (l <= cur_stop) if up else (h >= cur_stop):
            outcome, exitp = ("trail_exit" if trailing is not None else "loss"), cur_stop
            break
        # 達 L3
        reached_t = (h >= target) if up else (l <= target)
        if reached_t and not hit_l3:
            hit_l3 = True
            if mode == "L3":
                outcome, exitp = "win", target
                break
            # trail 模式：啟動 trailing（從 L3 起）
            trailing = (target - trail_dist) if up else (target + trail_dist)
        if mode == "trail" and hit_l3:
            newt = (h - trail_dist) if up else (l + trail_dist)
            trailing = max(trailing, newt) if up else min(trailing, newt)
    pnl = ((exitp - entry) if up else (entry - exitp)) - cost
    pct = pnl / entry * 100
    return {"outcome": outcome, "pnl": pnl, "pct": pct, "risk": risk,
            "R": (pnl / risk) if risk > 0 else None, "mae": mae,
            "win": pnl > 0}


# ---------- 指標 ----------
def metrics(trs):
    n = len(trs)
    if not n:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    mean = st.mean(pcts)
    sd = st.pstdev(pcts) if n > 1 else 0
    # equity & drawdown（損益% 累加）
    eq, peak, mdd, cur_streak, max_streak = 0.0, 0.0, 0.0, 0, 0
    for t in trs:
        eq += t["pct"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if t["win"]:
            cur_streak = 0
        else:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
    rs = [t["R"] for t in trs if t["R"] is not None]
    return {
        "N": n, "win%": round(100 * wins / n, 1),
        "EVpt": round(st.mean([t["pnl"] for t in trs]), 1),
        "tot%": round(sum(pcts), 1), "mean%": round(mean, 4),
        "sharpe": round(mean / sd, 3) if sd else 0,
        "mdd%": round(mdd, 1), "maxLoss": max_streak,
        "avgR": round(st.mean(rs), 2) if rs else 0,
    }


def fmt(m):
    if not m:
        return "N=0"
    return (f"N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% "
            f"sharpe={m['sharpe']:>6} mdd={m['mdd%']:>6}% maxLossStreak={m['maxLoss']:>2} avgR={m['avgR']}")


def run(tcs, days, **kw):
    trs = [dict(simulate(tc, days[tc["date"]], **kw), date=tc["date"],
                bucket=("≤09:30" if tc["entry_min"] < GATE_0930 else
                        "09:30-11:30" if tc["entry_min"] < GATE_1130 else ">11:30"),
                entry_min=tc["entry_min"]) for tc in tcs]
    return trs


def main():
    RESULTS.mkdir(exist_ok=True)
    days = load_all()
    ema = ema20_map(days)
    # 部署過濾：每段首個站回 → 濾掉淺拉回（深度 < 0.25×L2）
    tcs = [t for t in detect(days, ema) if t["depth_frac"] >= MIN_DEPTH_FRAC]
    print(f"setups (trigger A, depth>={MIN_DEPTH_FRAC}): N={len(tcs)}")
    IS = [t for t in tcs if t["date"] < OOS_START]
    OOS = [t for t in tcs if t["date"] >= OOS_START]
    print(f"IS(<2025)={len(IS)}  OOS(>=2025)={len(OOS)}\n")

    COST = 3.0
    # ---- 1) 停損 alpha 敏感度（IS, mode=L3, cost=3）----
    print("=== 1) 停損 alpha 敏感度 (IS, mode=L3, cost=3pt) ===")
    print("alpha=0 緊(拉回極值) → 1 寬(錨點)")
    best = None
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        m = metrics(run(IS, days, alpha=alpha, mode="L3", trail_frac=0, cost=COST))
        print(f"  alpha={alpha:<4} {fmt(m)}")
        if best is None or m["sharpe"] > best[1]["sharpe"]:
            best = (alpha, m)
    best_alpha = best[0]
    print(f"  -> IS best Sharpe @ alpha={best_alpha}")

    # ---- 2) 時間窗（IS, best alpha）----
    print("\n=== 2) 時間窗 (IS, alpha=best, mode=L3, cost=3) ===")
    allt = run(IS, days, alpha=best_alpha, mode="L3", trail_frac=0, cost=COST)
    for b in ("≤09:30", "09:30-11:30", ">11:30"):
        print(f"  {b:<12} {fmt(metrics([t for t in allt if t['bucket']==b]))}")
    early = [t for t in IS if t["entry_min"] < NOON]
    print(f"  ≤12:00 合併    {fmt(metrics(run(early, days, alpha=best_alpha, mode='L3', trail_frac=0, cost=COST)))}")

    # ---- 3) 出場模式 L3 vs trail（IS, best alpha, ≤12:00）----
    print("\n=== 3) 出場模式 (IS, alpha=best, ≤12:00, cost=3) ===")
    print(f"  L3 固定        {fmt(metrics(run(early, days, alpha=best_alpha, mode='L3', trail_frac=0, cost=COST)))}")
    for tf in (0.5, 0.75, 1.0):
        m = metrics(run(early, days, alpha=best_alpha, mode="trail", trail_frac=tf, cost=COST))
        print(f"  trail {tf:<4}     {fmt(m)}")

    # ---- 4) 成本敏感度（IS, best alpha, ≤12:00, L3）----
    print("\n=== 4) 成本敏感度 (IS, alpha=best, ≤12:00, mode=L3) ===")
    for c in (0, 2, 3, 4, 6):
        print(f"  cost={c}pt      {fmt(metrics(run(early, days, alpha=best_alpha, mode='L3', trail_frac=0, cost=c)))}")

    # ---- 5) ★ IS vs OOS（鎖定 alpha=best, ≤12:00, mode=L3, cost=3）----
    print("\n=== 5) ★ IS vs OOS (alpha=best, ≤12:00, mode=L3, cost=3pt) ===")
    is_e = [t for t in IS if t["entry_min"] < NOON]
    oos_e = [t for t in OOS if t["entry_min"] < NOON]
    m_is = metrics(run(is_e, days, alpha=best_alpha, mode="L3", trail_frac=0, cost=COST))
    m_oos = metrics(run(oos_e, days, alpha=best_alpha, mode="L3", trail_frac=0, cost=COST))
    print(f"  IS  {fmt(m_is)}")
    print(f"  OOS {fmt(m_oos)}")

    # ---- 6) 逐年 + walk-forward（每年用「之前所有年」最佳 alpha）----
    print("\n=== 6) 逐年 (≤12:00, mode=L3, cost=3, alpha=best) ===")
    by_year = defaultdict(list)
    for t in tcs:
        if t["entry_min"] < NOON:
            by_year[t["date"].year].append(t)
    for y in sorted(by_year):
        print(f"  {y}  {fmt(metrics(run(by_year[y], days, alpha=best_alpha, mode='L3', trail_frac=0, cost=COST)))}")

    print("\n=== 7) Walk-forward (test 年用 < 該年資料選 alpha) ===")
    wf_trs = []
    years = sorted(by_year)
    for y in years:
        train = [t for t in tcs if t["date"].year < y and t["entry_min"] < NOON]
        if len(train) < 100:
            continue
        ba, bs = None, -9
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
            mm = metrics(run(train, days, alpha=alpha, mode="L3", trail_frac=0, cost=COST))
            if mm["sharpe"] > bs:
                bs, ba = mm["sharpe"], alpha
        tr = run(by_year[y], days, alpha=ba, mode="L3", trail_frac=0, cost=COST)
        wf_trs += tr
        print(f"  {y}  alpha*={ba}  {fmt(metrics(tr))}")
    print(f"  WF stitched  {fmt(metrics(wf_trs))}")

    _equity_plot(run(early, days, alpha=best_alpha, mode="L3", trail_frac=0, cost=COST),
                 m_is, m_oos, best_alpha, is_e, oos_e, days, COST)
    print(f"\n寫出 equity_curve.png")


def _equity_plot(is_trs, m_is, m_oos, alpha, is_e, oos_e, days, cost):
    full = run(sorted(is_e + oos_e, key=lambda t: (t["date"], t["entry_min"])),
               days, alpha=alpha, mode="L3", trail_frac=0, cost=cost)
    eq, xs = 0.0, []
    for t in full:
        eq += t["pct"]
        xs.append(eq)
    plt.figure(figsize=(11, 5))
    plt.plot(xs, lw=1.2)
    split = sum(1 for t in full if t["date"] < OOS_START)
    plt.axvline(split, color="r", ls="--", lw=1, label=f"IS/OOS split (n={split})")
    plt.title(f"H120 equity (cumulative PnL%), trigger A, alpha={alpha}, <=11:30, L3, cost={cost}pt")
    plt.xlabel("trade #")
    plt.ylabel("cumulative PnL%")
    plt.legend()
    plt.tight_layout()
    plt.savefig(RESULTS / "equity_curve.png", dpi=110)
    plt.close()


if __name__ == "__main__":
    main()

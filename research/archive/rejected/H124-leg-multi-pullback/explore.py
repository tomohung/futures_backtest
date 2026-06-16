"""H124 Phase 1 explore — CAUSAL only（H120 前視偏誤教訓：絕不用 leg-bounded detect_day）。

問題：causal detect 對每相位記第一個站回(任意深度)即 done，深度濾網事後才套 →
      淺的第一站回會「燒掉」整個相位，後面更深的站回拿不到訊號（=2026-06-11 9:11 現象）。

三變體（detection 內含深度判定差異；其餘 EMA20/5MA/overshoot/L3 guard/出場 與 validate_causal 完全相同）：
  A baseline：第一站回(任意深)→done；事後濾 depth>=0.25（淺的消失，相位啞掉）
  B 淺不燒名額：站回 depth<0.25 → reset 子狀態續找同相位下一站回；第一個 depth>=0.25 才記錄並 done
  C 同相位全取：所有 depth>=0.25 站回都記錄（可多筆）

比較：A vs B vs C 的 IS/OOS 指標；B/C「多出來(extra)」筆 vs A 重疊筆的 avgR/win；逐日貢獻（防 data snooping）。

跑法：uv run python research/active/H124-leg-multi-pullback/explore.py
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from datetime import date

import duckdb

from src.chart_ui import paths

SYMBOL = "TX"
EMA_SPAN = 20
L2C, L3C, L4C, L5C = 0.497, 0.711, 0.977, 1.225
PB_FLOOR_FRAC = 0.05
MIN_DEPTH_FRAC = 0.25
OOS_START = date(2025, 1, 1)   # 沿用 validate_causal 切分
NOON = 720
COST = 3.0
ALPHA = 0.75


def load_days():
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


def detect_causal(days, ema, *, mode="A"):
    """完全 causal streaming。mode in {'A','B','C'}。回傳 entries（A 為任意深度，過濾在 main）。"""
    out = []
    for d in sorted(ema):
        bars = days[d]
        e = ema[d]
        L2d, L3d = L2C * e, L3C * e
        L4d, L5d = L4C * e, L5C * e
        pb_floor = PB_FLOOR_FRAC * e
        closes = [b[4] for b in bars]
        s5 = sma(closes, 5)
        n = len(bars)

        trend = None
        up_ref = bars[0][3]
        dn_ref = bars[0][2]
        ext = None
        phase = None
        anchor = None
        peak = None
        sub = None
        pb_ext = None
        done = False

        def open_phase(dir_up, anc, cur_h, cur_l):
            nonlocal phase, anchor, peak, sub, pb_ext, done
            phase = "up" if dir_up else "down"
            anchor = anc
            peak = cur_h if dir_up else cur_l
            sub = "extend"
            pb_ext = None
            done = False

        for i in range(n):
            m, o, h, l, c = bars[i]

            if phase is not None and not done:
                up = phase == "up"
                if (h > peak) if up else (l < peak):
                    peak = h if up else l
                if abs(peak - anchor) >= L3d:
                    done = True
                else:
                    if sub == "extend":
                        dip = (peak - l) if up else (h - peak)
                        if dip >= pb_floor:
                            sub = "pullback"
                            pb_ext = l if up else h
                    if sub == "pullback":
                        pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                        cs, ps = s5[i], s5[i - 1] if i > 0 else None
                        pc = bars[i - 1][4] if i > 0 else None
                        if cs is not None and ps is not None and pc is not None:
                            reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                            overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                            if reclaim and not overshoot:
                                dfrac = ((peak - pb_ext) if up else (pb_ext - peak)) / L2d
                                rec = {
                                    "date": d, "up": up, "side": "bull" if up else "bear",
                                    "entry_i": i, "entry_min": m, "entry": c,
                                    "anchor": anchor, "pb_low": pb_ext, "ema20": e,
                                    "L3d": L3d, "L4d": L4d, "L5d": L5d,
                                    "depth_frac": dfrac, "peak": peak,
                                }
                                if mode == "A":
                                    out.append(rec)        # 任意深度 → done（事後濾）
                                    done = True
                                elif mode == "B":
                                    if dfrac >= MIN_DEPTH_FRAC:
                                        out.append(rec)
                                        done = True
                                    else:                  # 淺站回不燒名額：reset 續找
                                        sub = "extend"
                                        peak = h if up else l
                                        pb_ext = None
                                else:  # C：全取合格，不 done
                                    if dfrac >= MIN_DEPTH_FRAC:
                                        out.append(rec)
                                    sub = "extend"
                                    peak = h if up else l
                                    pb_ext = None

            if trend is None:
                if l < up_ref:
                    up_ref = l
                if h > dn_ref:
                    dn_ref = h
                if h - up_ref >= L2d:
                    trend = "up"; ext = h
                    open_phase(True, up_ref, h, l)
                elif dn_ref - l >= L2d:
                    trend = "down"; ext = l
                    open_phase(False, dn_ref, h, l)
            elif trend == "up":
                if h > ext:
                    ext = h
                elif ext - l >= L2d:
                    pivot = ext; trend = "down"; ext = l
                    open_phase(False, pivot, h, l)
            else:
                if l < ext:
                    ext = l
                elif h - ext >= L2d:
                    pivot = ext; trend = "up"; ext = h
                    open_phase(True, pivot, h, l)
    return out


def simulate(tc, bars, *, alpha=ALPHA, cost=COST):
    up, entry, anchor, pb_low = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    L3d = tc["L3d"]
    stop = pb_low - alpha * (pb_low - anchor) if up else pb_low + alpha * (anchor - pb_low)
    target = anchor + L3d if up else anchor - L3d
    risk = (entry - stop) if up else (stop - entry)
    fwd = bars[tc["entry_i"] + 1:]
    outcome, exitp, exit_min = "open", bars[-1][4], bars[-1][0]
    for m, o, h, l, c in fwd:
        if (l <= stop) if up else (h >= stop):
            outcome, exitp, exit_min = "loss", stop, m
            break
        if (h >= target) if up else (l <= target):
            outcome, exitp, exit_min = "win", target, m
            break
    pnl = ((exitp - entry) if up else (entry - exitp)) - cost
    return {"outcome": outcome, "pnl": pnl, "pct": pnl / entry * 100,
            "risk": risk, "R": (pnl / risk) if risk > 0 else None, "win": pnl > 0,
            "exitp": exitp, "exit_min": exit_min}


def metrics(trs):
    n = len(trs)
    if not n:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    mean = st.mean(pcts)
    sd = st.pstdev(pcts) if n > 1 else 0
    eq = peak = mdd = 0.0
    cur = mx = 0
    for t in trs:
        eq += t["pct"]; peak = max(peak, eq); mdd = min(mdd, eq - peak)
        if t["win"]:
            cur = 0
        else:
            cur += 1; mx = max(mx, cur)
    rs = [t["R"] for t in trs if t["R"] is not None]
    return {"N": n, "win%": round(100 * wins / n, 1),
            "EVpt": round(st.mean([t["pnl"] for t in trs]), 1),
            "tot%": round(sum(pcts), 1), "mean%": round(mean, 4),
            "sharpe": round(mean / sd, 3) if sd else 0,
            "mdd%": round(mdd, 1), "maxLoss": mx,
            "avgR": round(st.mean(rs), 2) if rs else 0}


def fmt(m):
    if not m:
        return "N=0"
    return (f"N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% "
            f"sharpe={m['sharpe']:>6} mdd={m['mdd%']:>6}% maxLoss={m['maxLoss']:>2} avgR={m['avgR']}")


def run(tcs, days):
    return [dict(simulate(tc, days[tc["date"]]), date=tc["date"], entry_min=tc["entry_min"],
                up=tc["up"], tc=tc) for tc in tcs]


def key(tc):
    return (tc["date"], tc["up"], tc["entry_min"])


def split(tcs):
    return ([t for t in tcs if t["date"] < OOS_START],
            [t for t in tcs if t["date"] >= OOS_START])


def main():
    days = load_days()
    ema = ema20_map(days)

    A = [t for t in detect_causal(days, ema, mode="A")
         if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]
    B = [t for t in detect_causal(days, ema, mode="B") if t["entry_min"] < NOON]
    C = [t for t in detect_causal(days, ema, mode="C") if t["entry_min"] < NOON]

    print(f"setups（depth>=0.25, <12:00）：  A={len(A)}   B={len(B)}   C={len(C)}\n")

    for name, S in [("A baseline (淺燒名額)", A), ("B 淺不燒名額", B), ("C 同相位全取", C)]:
        s_is, s_oos = split(S)
        print(f"=== {name} ===")
        print(f"  IS  {fmt(metrics(run(s_is, days)))}")
        print(f"  OOS {fmt(metrics(run(s_oos, days)))}")
        print(f"  ALL {fmt(metrics(run(S, days)))}\n")

    aset = {key(t) for t in A}
    for name, S in [("B", B), ("C", C)]:
        extra = [t for t in S if key(t) not in aset]
        common = [t for t in S if key(t) in aset]
        lost = [t for t in A if key(t) not in {key(x) for x in S}]
        print(f"=== {name} 相對 A 分解 ===")
        print(f"  與 A 重疊      {fmt(metrics(run(common, days)))}")
        print(f"  {name} 多出(extra) {fmt(metrics(run(extra, days)))}")
        if lost:
            print(f"  A 有但 {name} 沒(lost) {fmt(metrics(run(lost, days)))}")
        print()

    # extra 逐日貢獻（防 data snooping）：B 多出來的單，集中在少數日？
    extraB = [t for t in B if key(t) not in aset]
    by_day = defaultdict(list)
    for t in run(extraB, days):
        by_day[t["date"]].append(t)
    print(f"=== B extra 逐日（共 {len(extraB)} 筆，分布 {len(by_day)} 天）===")
    tot_days = sorted(by_day, key=lambda d: sum(x["pct"] for x in by_day[d]))
    for d in tot_days[:5] + tot_days[-5:]:
        ts = by_day[d]
        print(f"  {d}  n={len(ts)} tot%={sum(x['pct'] for x in ts):+.2f} "
              f"win={sum(x['win'] for x in ts)}/{len(ts)}")

    # 2026-06-11 sanity：B 是否在該日補進場？
    print("\n=== 2026-06-11 sanity ===")
    for name, S in [("A", A), ("B", B), ("C", C)]:
        d11 = [t for t in S if t["date"] == date(2026, 6, 11)]
        for t in run(d11, days):
            tc = t["tc"]
            print(f"  {name}: {tc['entry_min']//60:02d}:{tc['entry_min']%60:02d} "
                  f"{'long' if tc['up'] else 'short'} depth={tc['depth_frac']:.2f} "
                  f"{t['outcome']} pnl={t['pnl']:+.1f}")
        if not d11:
            print(f"  {name}: (無)")


if __name__ == "__main__":
    main()

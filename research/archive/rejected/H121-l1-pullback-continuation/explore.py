"""H121 Phase 1 探索 — L1 拉回續攻：把「確立門檻」從 L2 放寬到 L1（參數化）。

Fork 自 research/archive/rejected/H120-l2-pullback-continuation/validate_causal.py 的 causal 引擎。
**禁止** 改用帶 `em` 前視 bug 的 strategies/retired/S005-l2-pullback/backtest.py。

與 H120 的唯一差異：detection 的「確立 / 反轉門檻」由參數 EST_C 決定（H120 固定 = L2C=0.497）。
目標仍為 L3（TGT_C=0.711）。其餘（EMA20 / 5MA / pb_floor / depth 濾網 / overshoot / L3 guard /
停損 alpha / 出場模擬 / cost）全部沿用 H120 causal 規格。

注意：EST_C 在 detection 內身兼兩職（與 H120 相同設計，刻意保持耦合）：
  (1) leg 確立 / 反轉的門檻距離；(2) depth_frac 的正規化基準（pullback / est_d）。
  → depth_frac=0.25 在 L1/L2 下語意一致（皆為「拉回佔確立距離的比例」），可 apples-to-apples 比較。

跑法：uv run python research/active/H121-l1-pullback-continuation/explore.py

幾何動機（×EMA20，停損寬 ≈0.75×確立距離）：
  L2→L3 RR≈0.58（H120 死因：目標比停損近、負偏態）；L1→L3 RR≈1.12。
  本腳本檢驗：causal 下 L1 進場是否真的吃得到這個 RR 改善（EV/Sharpe/avgR↑、負偏態收斂），
  還是被「L1→L3 續攻機率 < L2→L3」折損吃光。
"""
from __future__ import annotations

import importlib.util
import statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths

SYMBOL = "TX"
EMA_SPAN = 20
# 階梯倍率（單一真相源：src/chart_ui/services/daystats.py LVL_QUANTILES）
L1C, L2C, L3C, L4C, L5C = 0.385, 0.497, 0.711, 0.977, 1.225
PB_FLOOR_FRAC = 0.05
MIN_DEPTH_FRAC = 0.25
OOS_START = date(2025, 1, 1)
NOON = 720
COST = 3.0
ALPHA = 0.75

# H121 參數：確立門檻（H120=L2C）與目標（H120=L3C）
EST_C_DEFAULT = L2C   # 改成 L1C 即為本假設主場景
TGT_C_DEFAULT = L3C


# ---------- 資料載入（與 H120 validate_causal 相同） ----------
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


# ---------- ★ CAUSAL detection（參數化確立門檻 EST_C；逐根 streaming，無未來 em） ----------
def detect_causal(days, ema, est_c=EST_C_DEFAULT, tgt_c=TGT_C_DEFAULT, phase_log=None):
    """完全 causal。est_c=確立/反轉門檻倍率（H120 固定 L2C）；tgt_c=目標倍率（L3C）。

    phase_log（選填 list）：每開一個確立相位就記一筆 {date, up, anchor, reached_tgt}，
    供「無條件續攻率」虛無對照用（不論是否有拉回站回，這個確立 leg 後續有無摸到目標）。
    """
    out = []
    for d in sorted(ema):
        bars = days[d]
        e = ema[d]
        EST_d = est_c * e            # 確立 / 反轉門檻距離
        TGT_d = tgt_c * e            # 目標（停利 / overshoot / 直衝 guard）
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
        reached_tgt = False          # 本相位是否曾摸到目標（無條件續攻）

        def finalize_phase():
            if phase is not None and phase_log is not None:
                phase_log.append({"date": d, "up": phase == "up",
                                  "anchor": anchor, "reached_tgt": reached_tgt})

        def open_phase(dir_up, anc, cur_h, cur_l):
            nonlocal phase, anchor, peak, sub, pb_ext, done, reached_tgt
            finalize_phase()
            phase = "up" if dir_up else "down"
            anchor = anc
            peak = cur_h if dir_up else cur_l
            sub = "extend"
            pb_ext = None
            done = False
            reached_tgt = abs(peak - anc) >= TGT_d

        for i in range(n):
            m, o, h, l, c = bars[i]

            # === 1) 推進本相位進場邏輯（截至 i，全 causal） ===
            if phase is not None:
                up = phase == "up"
                if (h > peak) if up else (l < peak):
                    peak = h if up else l
                if abs(peak - anchor) >= TGT_d:
                    reached_tgt = True
                if not done:
                    if abs(peak - anchor) >= TGT_d:        # 直衝目標：本相位不交易
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
                                overshoot = (c >= anchor + TGT_d) if up else (c <= anchor - TGT_d)
                                if reclaim and not overshoot:
                                    depth_frac = ((peak - pb_ext) if up else (pb_ext - peak)) / EST_d
                                    out.append({
                                        "date": d, "up": up, "side": "bull" if up else "bear",
                                        "entry_i": i, "entry_min": m, "entry": c,
                                        "anchor": anchor, "pb_low": pb_ext, "ema20": e,
                                        "EST_d": EST_d, "TGTd": TGT_d,
                                        "depth_frac": depth_frac, "peak": peak,
                                        "est_c": est_c, "tgt_c": tgt_c,
                                    })
                                    done = True

            # === 2) 推進 ZigZag streaming（門檻 = EST_d） ===
            if trend is None:
                if l < up_ref:
                    up_ref = l
                if h > dn_ref:
                    dn_ref = h
                if h - up_ref >= EST_d:
                    trend = "up"
                    ext = h
                    open_phase(True, up_ref, h, l)
                elif dn_ref - l >= EST_d:
                    trend = "down"
                    ext = l
                    open_phase(False, dn_ref, h, l)
            elif trend == "up":
                if h > ext:
                    ext = h
                elif ext - l >= EST_d:
                    pivot = ext
                    trend = "down"
                    ext = l
                    open_phase(False, pivot, h, l)
            else:
                if l < ext:
                    ext = l
                elif h - ext >= EST_d:
                    pivot = ext
                    trend = "up"
                    ext = h
                    open_phase(True, pivot, h, l)

        finalize_phase()   # 收日末尾相位
    return out


# ---------- 出場模擬（與 H120 同：停損優先、保守；目標 = TGTd） ----------
def simulate(tc, bars, *, alpha=ALPHA, cost=COST):
    up, entry, anchor, pb_low = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    TGTd = tc["TGTd"]
    stop = pb_low - alpha * (pb_low - anchor) if up else pb_low + alpha * (anchor - pb_low)
    target = anchor + TGTd if up else anchor - TGTd
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
        eq += t["pct"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if t["win"]:
            cur = 0
        else:
            cur += 1
            mx = max(mx, cur)
    rs = [t["R"] for t in trs if t["R"] is not None]
    skew = _skew(pcts)
    return {"N": n, "win%": round(100 * wins / n, 1),
            "EVpt": round(st.mean([t["pnl"] for t in trs]), 1),
            "tot%": round(sum(pcts), 1), "mean%": round(mean, 4),
            "sharpe": round(mean / sd, 3) if sd else 0,
            "mdd%": round(mdd, 1), "maxLoss": mx,
            "avgR": round(st.mean(rs), 2) if rs else 0,
            "skew": round(skew, 2) if skew is not None else None}


def _skew(xs):
    n = len(xs)
    if n < 3:
        return None
    m = st.mean(xs)
    sd = st.pstdev(xs)
    if sd == 0:
        return 0.0
    return sum(((x - m) / sd) ** 3 for x in xs) / n


def fmt(m):
    if not m:
        return "N=0"
    return (f"N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% "
            f"sharpe={m['sharpe']:>6} mdd={m['mdd%']:>6}% maxLoss={m['maxLoss']:>2} "
            f"avgR={m['avgR']:>5} skew={m['skew']}")


def run(tcs, days):
    return [dict(simulate(tc, days[tc["date"]]), date=tc["date"], entry_min=tc["entry_min"],
                up=tc["up"], tc=tc) for tc in tcs]


def key(tc):
    return (tc["date"], tc["up"], tc["entry_min"])


# ---------- cross-check：est=L2 必須完全重現 H120 原始 detect_causal（防 `em` 復發） ----------
def _load_h120_causal():
    p = (Path(__file__).resolve().parents[2]
         / "archive/rejected/H120-l2-pullback-continuation/validate_causal.py")
    spec = importlib.util.spec_from_file_location("h120_causal", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crosscheck(days, ema):
    h120 = _load_h120_causal()
    ref = h120.detect_causal(days, ema)                       # 原始（門檻固定 L2）
    mine = detect_causal(days, ema, est_c=L2C, tgt_c=L3C)     # 我參數化版（est=L2）
    rk = sorted(key(t) for t in ref)
    mk = sorted(key(t) for t in mine)
    same_keys = rk == mk
    # 進一步比對 entry/anchor/pb_low/depth 一致
    rmap = {key(t): t for t in ref}
    maxdiff = 0.0
    for t in mine:
        r = rmap.get(key(t))
        if r:
            for f in ("entry", "anchor", "pb_low", "depth_frac"):
                maxdiff = max(maxdiff, abs(t[f] - r[f]))
    print("[cross-check] 參數化(est=L2) vs H120 原始 detect_causal：")
    print(f"  setups  mine={len(mine)}  ref={len(ref)}  keys_identical={same_keys}  "
          f"field_max_diff={maxdiff:.6f}  (應 keys 全同 & diff≈0)")
    return same_keys and maxdiff < 1e-9


def split(tcs):
    return ([t for t in tcs if t["date"] < OOS_START],
            [t for t in tcs if t["date"] >= OOS_START])


def report_scenario(label, days, ema, est_c, tgt_c):
    phase_log = []
    caus = detect_causal(days, ema, est_c=est_c, tgt_c=tgt_c, phase_log=phase_log)
    flt = [t for t in caus if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]
    c_is, c_oos = split(flt)
    print(f"\n=== {label}  (est_c={est_c}, tgt_c={tgt_c}) ===")
    print(f"  setups(depth>=0.25,<12:00): {len(flt)}   "
          f"(原始確立相位數={len(phase_log)})")
    print(f"  IS  {fmt(metrics(run(c_is, days)))}")
    print(f"  OOS {fmt(metrics(run(c_oos, days)))}")
    print(f"  ALL {fmt(metrics(run(flt, days)))}")

    # 虛無對照 1：無條件續攻率 vs 進場條件勝率
    if phase_log:
        uncond = 100 * sum(p["reached_tgt"] for p in phase_log) / len(phase_log)
        cond_m = metrics(run(flt, days))
        cond = cond_m["win%"] if cond_m else 0
        print(f"  [null-1] 無條件續攻率 P(摸到目標|確立)={uncond:.1f}%  vs  "
              f"進場條件勝率={cond}%  增量={cond - uncond:+.1f}pp")
        print("           （增量≈0 → 站回訊號無資訊量；注意 cond 受 entry 濾網/停損影響，"
              "非純續攻率，正式判定需配 IID 洗牌對照）")

    # 逐年
    by_year = defaultdict(list)
    for t in flt:
        by_year[t["date"].year].append(t)
    print("  逐年:")
    for y in sorted(by_year):
        print(f"    {y}  {fmt(metrics(run(by_year[y], days)))}")
    return flt


def scan_threshold(days, ema):
    print("\n=== 確立門檻掃描 L1→L2（目標固定 L3）===")
    print("  est_c    N   win%   EV   tot%  sharpe  avgR  skew")
    for est_c in [0.385, 0.42, 0.45, 0.47, 0.497]:
        caus = detect_causal(days, ema, est_c=est_c, tgt_c=L3C)
        flt = [t for t in caus if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]
        m = metrics(run(flt, days))
        if m:
            print(f"  {est_c:<6} {m['N']:>4} {m['win%']:>5} {m['EVpt']:>5} "
                  f"{m['tot%']:>6} {m['sharpe']:>6} {m['avgR']:>5} {m['skew']}")


def main():
    days = load_days()
    ema = ema20_map(days)

    ok = crosscheck(days, ema)
    if not ok:
        print("  ⚠️ cross-check 失敗：參數化版在 est=L2 未重現 H120 原始，先修再繼續！")

    report_scenario("H120 baseline（L2 確立）", days, ema, est_c=L2C, tgt_c=L3C)
    report_scenario("H121 主場景（L1 確立 → L3）", days, ema, est_c=L1C, tgt_c=L3C)
    scan_threshold(days, ema)


if __name__ == "__main__":
    main()

"""H120 Phase 1 explore — L2 趨勢確立後拉回續攻（pullback breakout continuation）.

Setup（母體）：用 L2 門檻 ZigZag 切 leg；每 leg ext 自錨點達 L2 距離 = 趨勢確立。
拉回 + trigger：確立後第一個 ≥PB_FLOOR 回檔，記 A(5MA站回)/B(突破前峰)/C(站回+確認)。
交易模擬（全因果，掃到收盤）：target=錨±L3d、stop=拉回極值(主)/錨點(備)，記 MAE/MFE/R/勝負。
baseline：①50% 無條件 ②達 L2 的 leg 中達 L3 比例（≈_CONT_L3_FROM_L2，更嚴）。

輸出：results/setups.csv、results/trades.csv、console 摘要、results/*.png。
腳本必須保留（CLAUDE.md 規則）。
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
from src.chart_ui.services.swing_legs import zigzag_legs

SYMBOL = "TX"
EMA_SPAN = 20
# ladder coef × EMA20振幅（daystats.LVL_QUANTILES）
COEF = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}

RESULTS = Path(__file__).parent / "results"

# ---- 參數（explore 預設；backtest 再掃敏感度）----
PB_FLOOR_FRAC = 0.05      # 最小拉回深度 = PB_FLOOR_FRAC × EMA20（過濾雜訊微回）
BUF_BREAKOUT = 1.0        # 突破前峰 buffer（點）
BUF_STOP = 0.0            # 結構停損 buffer（點，0=正好在拉回極值）

GATE_0930, GATE_1130 = 570, 690  # 分鐘（08:45=525）


def _time_bucket(minute: int) -> str:
    if minute < GATE_0930:
        return "≤09:30"
    if minute < GATE_1130:
        return "09:30-11:30"
    return ">11:30"


def load_all():
    """回傳 {day: [(minute, o, h, l, c)]}（昇冪）與 daily ranges。"""
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, "
            "open, high, low, close FROM ohlcv_1m "
            "WHERE symbol = ? AND CAST(timestamp AS TIME) "
            "BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp",
            [SYMBOL],
        ).fetchall()
    days: dict[date, list] = defaultdict(list)
    for d, t, o, h, l, c in rows:
        days[d].append((t.hour * 60 + t.minute, float(o), float(h), float(l), float(c)))
    return days


def ema20_map(days: dict) -> dict:
    """每日 causal EMA20（前 ≤120 日日盤振幅，昇冪 seed 最舊）。"""
    sorted_days = sorted(days)
    rng = {d: (max(h for _, _, h, _, _ in bars) - min(l for _, _, _, l, _ in bars))
           for d, bars in days.items()}
    out = {}
    alpha = 2.0 / (EMA_SPAN + 1)
    for i, d in enumerate(sorted_days):
        prior = sorted_days[max(0, i - 120):i]
        if len(prior) < EMA_SPAN:
            continue
        ema = rng[prior[0]]
        for pd in prior[1:]:
            ema = alpha * rng[pd] + (1 - alpha) * ema
        out[d] = ema
    return out


def sma(seq, n):
    """causal SMA(n)；不足 n 回 None。回傳與 seq 等長 list。"""
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def process_leg(lg, bars, dist, ema20):
    """單一 leg → (setup dict, [trade dicts])。bars=[(m,o,h,l,c)] 全日。"""
    side = "bull" if lg["dir"] == "up" else "bear"
    sm, em = lg["start_min"], lg["end_min"]
    anchor = lg["start_price"]
    up = side == "bull"

    seg = [b for b in bars if sm <= b[0] <= em]
    if len(seg) < 3:
        return None, []
    L2d, L3d, L4d, L5d = dist["L2"], dist["L3"], dist["L4"], dist["L5"]
    pb_floor = PB_FLOOR_FRAC * ema20

    # leg-level reach（ext 自錨點，phenomenon baseline）
    leg_ext = max((h - anchor) if up else (anchor - l) for _, _, h, l, _ in seg)
    reached = {k: leg_ext >= dist[k] for k in ("L2", "L3", "L4", "L5")}

    # 確立時點：ext 首次 ≥ L2d
    est_min = est_close = None
    ext = 0.0
    for m, _, h, l, c in seg:
        ext = max(ext, (h - anchor) if up else (anchor - l))
        if ext >= L2d:
            est_min, est_close = m, c
            break
    if est_min is None:
        return None, []

    setup = {
        "leg_ext": round(leg_ext), "est_min": est_min, "est_bucket": _time_bucket(est_min),
        "side": side, "anchor": round(anchor), "leg_amp": round(leg_ext),
        "reach_L3": reached["L3"], "reach_L4": reached["L4"], "reach_L5": reached["L5"],
        "had_pullback": False, "pb_depth": None, "pb_min": None,
        "matured_pre_pb": False,
    }

    # 確立後掃拉回 + trigger（用全日 close 算 SMA5，因果）
    closes = [b[4] for b in bars]
    sma5 = sma(closes, 5)
    idx = {b[0]: i for i, b in enumerate(bars)}

    target = anchor + L3d if up else anchor - L3d
    trades = []
    # trigger N（null 對照）：確立當下就進，stop=錨點（無拉回可用）
    if abs((anchor + ext if up else anchor - ext) - anchor) < L3d:
        trades.append(_mk_trade("N", side, est_min, est_close, anchor, anchor,
                                target, dist, bars, idx[est_min], up, ema20, 0.0, setup))
    state = "extend"
    peak = None       # 確立後逐 bar 推進的極值價（peak），首個 bar 取確立極值
    max_depth = 0.0
    for m, o, h, l, c in seg:
        if m < est_min:
            continue
        if peak is None:
            peak = h if up else l
            continue
        i = idx[m]
        cur_sma = sma5[i]
        prev_c = bars[i - 1][4]
        prev_sma = sma5[i - 1]
        if state == "extend":
            if (h > peak) if up else (l < peak):
                peak = h if up else l
            # 已直衝到 L3：L2→L3 這段已走完，非可交易 setup（target 進場前已到）
            if (abs(peak - anchor) >= L3d):
                setup["matured_pre_pb"] = True
                break
            dip = (peak - l) if up else (h - peak)
            if dip >= pb_floor:
                state = "pullback"
                pb_ext = l if up else h
                pb_min = m
                fired = set()
                setup["had_pullback"] = True
        elif state == "pullback":
            pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
            depth = (peak - pb_ext) if up else (pb_ext - peak)
            max_depth = max(max_depth, depth)
            # trigger B：突破前峰
            broke = (h > peak + BUF_BREAKOUT) if up else (l < peak - BUF_BREAKOUT)
            if broke and "B" not in fired:
                entry = peak + BUF_BREAKOUT if up else peak - BUF_BREAKOUT
                trades.append(_mk_trade("B", side, m, entry, pb_ext, anchor,
                                        target, dist, bars, i, up, ema20, depth, setup))
                fired.add("B")
            # trigger A：5MA 站回
            if cur_sma is not None and prev_sma is not None and "A" not in fired:
                reclaim = (prev_c < prev_sma and c > cur_sma) if up else (prev_c > prev_sma and c < cur_sma)
                if reclaim:
                    trades.append(_mk_trade("A", side, m, c, pb_ext, anchor,
                                            target, dist, bars, i, up, ema20, depth, setup))
                    fired.add("A")
                    # trigger C：站回 + 確認（順勢 K：收高於前收 且 紅/綠K）
                    confirm = (c > prev_c and c > o) if up else (c < prev_c and c < o)
                    if confirm and "C" not in fired:
                        trades.append(_mk_trade("C", side, m, c, pb_ext, anchor,
                                                target, dist, bars, i, up, ema20, depth, setup))
                        fired.add("C")
            if {"A", "B", "C"} <= fired:
                break
    if setup["had_pullback"]:
        setup["pb_depth"] = round(max_depth)
        setup["pb_min"] = pb_min
    return setup, trades


def _mk_trade(trig, side, emin, entry, pb_ext, anchor, target, dist, bars, ientry, up, ema20, depth, setup):
    """從進場點向收盤模擬：stop=拉回極值(主)/錨(備)、target=L3。回傳指標。"""
    stop_main = pb_ext - BUF_STOP if up else pb_ext + BUF_STOP
    stop_alt = anchor
    res = {"trig": trig, "side": side, "entry_min": emin, "entry": round(entry),
           "est_bucket": _time_bucket(emin), "depth": round(depth),
           "reach_L3": setup["reach_L3"], "reach_L4": setup["reach_L4"], "reach_L5": setup["reach_L5"]}
    for tag, stop in (("main", stop_main), ("alt", stop_alt)):
        risk = (entry - stop) if up else (stop - entry)
        outcome, exitp, mae, mfe = "open", bars[-1][4], 0.0, 0.0
        for m, o, h, l, c in bars[ientry + 1:]:
            mae = max(mae, (entry - l) if up else (h - entry))
            mfe = max(mfe, (h - entry) if up else (entry - l))
            hit_stop = (l <= stop) if up else (h >= stop)
            hit_tgt = (h >= target) if up else (l <= target)
            if hit_stop:
                outcome, exitp = "loss", stop
                break
            if hit_tgt:
                outcome, exitp = "win", target
                break
        pnl = (exitp - entry) if up else (entry - exitp)
        rr = (pnl / risk) if risk > 0 else None
        res[f"{tag}_risk"] = round(risk, 1)
        res[f"{tag}_outcome"] = outcome
        res[f"{tag}_pnl"] = round(pnl, 1)
        res[f"{tag}_R"] = round(rr, 2) if rr is not None else None
        res[f"{tag}_mae"] = round(mae, 1)
        res[f"{tag}_mfe"] = round(mfe, 1)
    return res


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def main():
    RESULTS.mkdir(exist_ok=True)
    days = load_all()
    ema = ema20_map(days)
    print(f"days total={len(days)}, with EMA20={len(ema)}")

    all_legs = 0
    setups, trades = [], []
    for d in sorted(ema):
        bars = days[d]
        ema20 = ema[d]
        dist = {k: COEF[k] * ema20 for k in COEF}
        legs = zigzag_legs([(m, h, l) for m, _, h, l, _ in bars], threshold=dist["L2"])
        # 只留 start_min < 11:30 的 leg（與 swing_legs 起點閘一致；早盤）
        for lg in legs:
            if abs(lg["end_price"] - lg["start_price"]) < dist["L2"]:
                continue  # tail leg 未達 L2，跳過
            all_legs += 1
            su, tr = process_leg(lg, bars, dist, ema20)
            if su is None:
                continue
            su["date"] = str(d)
            setups.append(su)
            for t in tr:
                t["date"] = str(d)
                trades.append(t)

    # ---- baseline & 分佈 ----
    n_su = len(setups)
    n_pb = sum(s["had_pullback"] for s in setups)
    print(f"\n=== Setup 母體 ===")
    print(f"≥L2 legs (達 L2 確立): N={n_su}")
    print(f"  其中 reach L3: {sum(s['reach_L3'] for s in setups)} ({pct(sum(s['reach_L3'] for s in setups), n_su)}%)  <- 條件 baseline (達L2→L3)")
    print(f"  其中 reach L4: {pct(sum(s['reach_L4'] for s in setups), n_su)}%   reach L5: {pct(sum(s['reach_L5'] for s in setups), n_su)}%")
    print(f"  有拉回 (≥{PB_FLOOR_FRAC}×EMA20) 的 setup: N={n_pb} ({pct(n_pb, n_su)}%)")
    pb = [s for s in setups if s["had_pullback"]]
    print(f"    拉回 setup 中 reach L3: {pct(sum(s['reach_L3'] for s in pb), n_pb)}%  L4: {pct(sum(s['reach_L4'] for s in pb), n_pb)}%  L5: {pct(sum(s['reach_L5'] for s in pb), n_pb)}%")

    # 達 L2→L3 by est_bucket（對照 _CONT_L3_FROM_L2）
    print(f"\n=== 達 L2→L3 by 確立時間桶（對照 daystats _CONT_L3_FROM_L2 早86%→晚46%）===")
    by_b = defaultdict(list)
    for s in setups:
        by_b[s["est_bucket"]].append(s)
    for b in ("≤09:30", "09:30-11:30", ">11:30"):
        ss = by_b[b]
        if ss:
            print(f"  {b}: N={len(ss)}  reach L3={pct(sum(x['reach_L3'] for x in ss), len(ss))}%")

    # 多空不對稱
    print(f"\n=== 多空 ===")
    for side in ("bull", "bear"):
        ss = [s for s in setups if s["side"] == side]
        print(f"  {side}: N={len(ss)}  reach L3={pct(sum(x['reach_L3'] for x in ss), len(ss))}%  有拉回={pct(sum(x['had_pullback'] for x in ss), len(ss))}%")

    # 拉回深度分佈
    depths = [s["pb_depth"] for s in pb if s["pb_depth"] is not None]
    if depths:
        print(f"\n=== 拉回深度（點）N={len(depths)} ===")
        print(f"  median={round(st.median(depths))}  mean={round(st.mean(depths))}  p25={round(_q(depths,.25))}  p75={round(_q(depths,.75))}")

    # ---- trigger 比較 ----
    print(f"\n=== Trigger 比較（stop=main 拉回極值, target=L3）===")
    print(f"{'trig':>4} {'N':>4} {'win%':>5} {'loss%':>6} {'open%':>6} {'EV(pt)':>7} {'avgR':>6} {'MAE_med':>8} {'MAE_p75':>8} {'MFE_med':>8}")
    for trig in ("A", "C", "B"):
        ts = [t for t in trades if t["trig"] == trig]
        _report_trig(trig, ts, "main")
    print(f"\n=== Trigger 比較（stop=alt 錨點, target=L3）+ N(null 確立即進) ===")
    print(f"{'trig':>4} {'N':>4} {'win%':>5} {'loss%':>6} {'open%':>6} {'EV(pt)':>7} {'avgR':>6}")
    for trig in ("A", "C", "B", "N"):
        ts = [t for t in trades if t["trig"] == trig]
        _report_trig(trig, ts, "alt", short=True)

    # trigger × 時間桶（main）
    print(f"\n=== Trigger A × 時間桶（stop=main）===")
    for b in ("≤09:30", "09:30-11:30", ">11:30"):
        ts = [t for t in trades if t["trig"] == "A" and t["est_bucket"] == b]
        _report_trig(b, ts, "main")

    _write_csv(setups, trades)
    _plots(setups, trades)
    print(f"\n寫出: {RESULTS/'setups.csv'}, {RESULTS/'trades.csv'}, *.png")


def _q(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _report_trig(label, ts, tag, short=False):
    n = len(ts)
    if not n:
        print(f"{label:>4} {0:>4}")
        return
    win = sum(t[f"{tag}_outcome"] == "win" for t in ts)
    loss = sum(t[f"{tag}_outcome"] == "loss" for t in ts)
    opn = sum(t[f"{tag}_outcome"] == "open" for t in ts)
    ev = st.mean([t[f"{tag}_pnl"] for t in ts])
    rs = [t[f"{tag}_R"] for t in ts if t[f"{tag}_R"] is not None]
    avgr = st.mean(rs) if rs else 0
    if short:
        print(f"{label:>4} {n:>4} {pct(win,n):>5} {pct(loss,n):>6} {pct(opn,n):>6} {round(ev):>7} {round(avgr,2):>6}")
        return
    maes = [t[f"{tag}_mae"] for t in ts]
    mfes = [t[f"{tag}_mfe"] for t in ts]
    print(f"{label:>4} {n:>4} {pct(win,n):>5} {pct(loss,n):>6} {pct(opn,n):>6} {round(ev):>7} {round(avgr,2):>6} "
          f"{round(st.median(maes)):>8} {round(_q(maes,.75)):>8} {round(st.median(mfes)):>8}")


def _write_csv(setups, trades):
    if setups:
        with open(RESULTS / "setups.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(setups[0].keys()))
            w.writeheader()
            w.writerows(setups)
    if trades:
        with open(RESULTS / "trades.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trades[0].keys()))
            w.writeheader()
            w.writerows(trades)


def _plots(setups, trades):
    # 1) 拉回深度分佈
    depths = [s["pb_depth"] for s in setups if s["pb_depth"] is not None]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    if depths:
        ax[0].hist(depths, bins=40, color="#4477aa")
        ax[0].set_title(f"Pullback depth dist (pt) N={len(depths)}")
        ax[0].set_xlabel("pullback depth")
    # 2) trigger A MAE 分佈（main）
    maesA = [t["main_mae"] for t in trades if t["trig"] == "A"]
    if maesA:
        ax[1].hist(maesA, bins=40, color="#cc6677")
        ax[1].set_title(f"Trigger A MAE dist (main stop) N={len(maesA)}")
        ax[1].set_xlabel("MAE pt")
    plt.tight_layout()
    plt.savefig(RESULTS / "dist_pb_mae.png", dpi=110)
    plt.close()


if __name__ == "__main__":
    main()

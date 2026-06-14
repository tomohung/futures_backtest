"""H120 進場（拉回後站回 5MA 續攻 L2→L3）偵測 — chart-ui 主圖指標 + list 共用真相源。

邏輯與 research/active/H120-l2-pullback-continuation/backtest.py 的 detect()/simulate() 對齊：
  Setup：L2 門檻 zigzag 切 leg → ext 自錨達 L2 確立 → 第一個 ≥PB_FLOOR 拉回 → 收盤站回 5MA 進場。
  guard：直衝 L3 不交易(matured)、進場那根已破 L3 不交易(overshoot)。每 leg 一筆。
  停損：拉回極值往錨點靠 STOP_ALPHA；目標：錨 ± L3 距離。
參數沿用回測 confirmed 值。若回測參數調整，請同步此檔（兩處需一致）。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.swing_legs import zigzag_legs

COEF = {"L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}
PB_FLOOR_FRAC = 0.05
STOP_ALPHA = 0.75
EMA5 = 5
CUTOFF_MIN = 720       # 進場時間上限=12:00（午後尾盤幾乎無 edge）
MIN_DEPTH_FRAC = 0.25  # 進場最小拉回深度(÷L2)；濾掉淺拉回（avgR僅0.08、占46%）


def _sma(seq, n):
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def _min_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def detect_day(bars, ema20):
    """bars=[(minute,o,h,l,c)] 昇冪。回傳 (entries, dist)。

    entry dict：entry_min, side('long'/'short'), entry, anchor, pb_ext, stop, target,
                entry_i（bars 索引，供 simulate）。
    """
    dist = {k: COEF[k] * ema20 for k in COEF}
    L2d, L3d = dist["L2"], dist["L3"]
    pb_floor = PB_FLOOR_FRAC * ema20
    closes = [b[4] for b in bars]
    s5 = _sma(closes, EMA5)
    legs = zigzag_legs([(m, h, l) for m, _, h, l, _ in bars], threshold=L2d)
    out = []
    for lg in legs:
        if abs(lg["end_price"] - lg["start_price"]) < L2d:
            continue
        up = lg["dir"] == "up"
        sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
        seg_idx = [i for i, b in enumerate(bars) if sm <= b[0] <= em]
        if len(seg_idx) < 3:
            continue
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
        state = "extend"
        peak = None
        pb_ext = None
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
                if abs(peak - anchor) >= L3d:
                    break  # 直衝 L3，非可交易
                dip = (peak - l) if up else (h - peak)
                if dip >= pb_floor:
                    state = "pullback"
                    pb_ext = l if up else h
            else:
                pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                cs, ps = s5[i], s5[i - 1]
                pc = bars[i - 1][4]
                if cs is None or ps is None:
                    continue
                reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                if reclaim and not overshoot:
                    stop = pb_ext - STOP_ALPHA * (pb_ext - anchor) if up \
                        else pb_ext + STOP_ALPHA * (anchor - pb_ext)
                    target = anchor + L3d if up else anchor - L3d
                    depth = (peak - pb_ext) if up else (pb_ext - peak)
                    dfrac = depth / L2d
                    out.append({
                        "entry_min": m, "entry_i": i,
                        "side": "long" if up else "short",
                        "entry": round(c, 1), "anchor": round(anchor, 1),
                        "pb_ext": round(pb_ext, 1), "stop": round(stop, 1),
                        "target": round(target, 1),
                        "risk": round(abs(c - stop)),
                        "depth_frac": dfrac, "size": size_mult(dfrac),
                    })
                    break
    return out, dist


def size_mult(dfrac: float) -> float:
    """拉回深度(÷L2) → 加碼倍數（兩階）。<0.25 過濾不交易；0.25~0.5 ×1、≥0.5 ×2。"""
    return 2.0 if dfrac >= 0.5 else 1.0


def simulate(e, bars):
    """從進場掃到收盤：stop / target / 收盤。回傳 exit_min, exit, pnl, result。"""
    up = e["side"] == "long"
    entry, stop, target = e["entry"], e["stop"], e["target"]
    exit_min, exit_px, result = bars[-1][0], bars[-1][4], "Open"
    for m, o, h, l, c in bars[e["entry_i"] + 1:]:
        hit_stop = (l <= stop) if up else (h >= stop)
        hit_tgt = (h >= target) if up else (l <= target)
        if hit_stop:
            exit_min, exit_px, result = m, stop, "Loss"
            break
        if hit_tgt:
            exit_min, exit_px, result = m, target, "Win"
            break
    pnl = (exit_px - entry) if up else (entry - exit_px)
    return exit_min, round(exit_px, 1), round(pnl, 1), result


def _day_bars(conn, sel: date):
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp", [SYMBOL, sel]).fetchall()
    return [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c))
            for t, o, h, l, c in rows]


def compute_h120_entries(*, date_str: str, db_path: Path | None = None) -> dict:
    """單日 H120 進場（主圖指標用）。回傳 {entries:[{time,side,entry,stop,target,risk}], l3_dist, ema20}。"""
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        ema20 = _ema20_range(conn, sel)
        if not ema20:
            return {"entries": [], "l3_dist": None, "ema20": None}
        bars = _day_bars(conn, sel)
    if len(bars) < 5:
        return {"entries": [], "l3_dist": round(COEF["L3"] * ema20, 1), "ema20": round(ema20, 1)}
    entries, dist = detect_day(bars, ema20)
    out = []
    for e in entries:
        if e["entry_min"] >= CUTOFF_MIN:           # 進場時間上限 12:00
            continue
        if e["depth_frac"] < MIN_DEPTH_FRAC:       # 濾掉淺拉回
            continue
        exit_min, exit_px, pnl, result = simulate(e, bars)
        out.append({
            "time": _min_to_hhmm(e["entry_min"]),
            "side": e["side"], "entry": e["entry"], "stop": e["stop"],
            "target": e["target"], "risk": e["risk"],
            "depth_frac": round(e["depth_frac"], 2), "size": e["size"],
            "exit_time": _min_to_hhmm(exit_min), "exit": exit_px,
            "pnl": pnl, "result": result,
        })
    return {"entries": out, "l3_dist": round(dist["L3"], 1), "ema20": round(ema20, 1)}

"""主圖「L3 波段」：當日 11:30 前起點、幅度 ≥ L3 的單向 swing 波段偵測。

兩個門檻刻意解耦（zigzag_legs 為不依賴 DB 的純函式，門檻由呼叫端帶入）：
- 反轉門檻 = L2 距離（≈0.70×L3）：回檔 ≥ L2 即切段，讓接近 L3 的大回檔不被吸收。
- 最小波段幅度 = L3 距離：只顯示淨幅 ≥ L3 的段（l3_mult 也以 L3 為基準）。
compute_swing_legs 包 DB 整合（讀日盤 1 分 K、重用 daystats 的 EMA20 算 L2/L3、篩選起點 < 11:30）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import LVL_QUANTILES, SYMBOL, _ema20_range

NOON_MIN = 690          # 11:30（起點時間閘）
L2_COEF = LVL_QUANTILES[1][2]  # 0.497 × EMA20（反轉門檻）
L3_COEF = LVL_QUANTILES[2][2]  # 0.711 × EMA20（最小波段幅度 / l3_mult 基準）


def zigzag_legs(bars, threshold):
    """ZigZag 波段偵測，反轉門檻 = threshold。

    bars: [(minute, high, low), ...] 已按時間昇冪。threshold: 反轉/幅度門檻。
    回傳 [{start_min, start_price, end_min, end_price, dir}]，dir ∈ {'up','down'}。
    收尾會把最後未確認反轉的極值當暫定 pivot 輸出（幅度篩選由呼叫端負責）。
    """
    if len(bars) < 2:
        return []
    first_min, first_h, first_l = bars[0]
    up_ref_min, up_ref = first_min, first_l   # 上漲基準（running low）
    dn_ref_min, dn_ref = first_min, first_h   # 下跌基準（running high）
    trend = None
    ext_min = ext = None
    pivots = []  # (minute, price, kind) kind ∈ {'L','H'}
    for m, h, l in bars:
        if trend is None:
            if l < up_ref:
                up_ref_min, up_ref = m, l
            if h > dn_ref:
                dn_ref_min, dn_ref = m, h
            if h - up_ref >= threshold:
                trend = "up"
                pivots.append((up_ref_min, up_ref, "L"))
                ext_min, ext = m, h
            elif dn_ref - l >= threshold:
                trend = "down"
                pivots.append((dn_ref_min, dn_ref, "H"))
                ext_min, ext = m, l
        elif trend == "up":
            if h > ext:
                ext_min, ext = m, h
            elif ext - l >= threshold:
                pivots.append((ext_min, ext, "H"))
                trend = "down"
                ext_min, ext = m, l
        else:  # down
            if l < ext:
                ext_min, ext = m, l
            elif h - ext >= threshold:
                pivots.append((ext_min, ext, "L"))
                trend = "up"
                ext_min, ext = m, h
    if trend is not None:
        pivots.append((ext_min, ext, "H" if trend == "up" else "L"))

    legs = []
    for (sm, sp, _sk), (em, ep, _ek) in zip(pivots, pivots[1:]):
        legs.append({
            "start_min": sm, "start_price": sp,
            "end_min": em, "end_price": ep,
            "dir": "up" if ep >= sp else "down",
        })
    return legs


def _min_to_hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _filter_and_format(raw_legs, threshold):
    """篩選 start_min < 11:30 且 abs(amp) ≥ threshold，並格式化輸出。

    amp 帶方向（up 正 / down 負）；l3_mult = round(abs(amp)/threshold, 1)。
    """
    out = []
    for lg in raw_legs:
        if lg["start_min"] >= NOON_MIN:
            continue
        amp_abs = abs(lg["end_price"] - lg["start_price"])
        if amp_abs < threshold:
            continue
        amp = round(lg["end_price"] - lg["start_price"])
        out.append({
            "start_time": _min_to_hhmm(lg["start_min"]),
            "start_price": round(lg["start_price"]),
            "end_time": _min_to_hhmm(lg["end_min"]),
            "end_price": round(lg["end_price"]),
            "dir": lg["dir"],
            "amp": amp,
            "l3_mult": round(amp_abs / threshold, 1),
        })
    return out


def _day_bars(conn, sel: date):
    """當日日盤 1 分 K：[(minute, high, low)]，08:45–13:45，昇冪。"""
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp",
        [SYMBOL, sel],
    ).fetchall()
    return [(t.hour * 60 + t.minute, float(h), float(l)) for t, h, l in rows]


def compute_swing_legs(*, date_str: str, db_path: Path | None = None) -> dict:
    """回傳 {legs:[...], l3_dist, ema20}。ema20 不足 20 日時 legs 為空。"""
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        ema20 = _ema20_range(conn, sel)
        if not ema20:
            return {"legs": [], "l3_dist": None, "ema20": None}
        l2_dist = L2_COEF * ema20   # 反轉門檻：回檔 ≥ L2 即切段
        l3_dist = L3_COEF * ema20   # 顯示門檻：只留淨幅 ≥ L3 的段
        bars = _day_bars(conn, sel)
    raw = zigzag_legs(bars, threshold=l2_dist)
    return {
        "legs": _filter_and_format(raw, threshold=l3_dist),
        "l3_dist": round(l3_dist, 1),
        "ema20": round(ema20, 1),
    }

"""主圖「L3 波段」：當日 11:30 前起點、幅度 ≥ L3 的單向 swing 波段偵測。

zigzag_legs 為不依賴 DB 的純函式（反轉門檻 = L3 距離）；compute_swing_legs 包 DB
整合（讀日盤 1 分 K、重用 daystats 的 EMA20 振幅算 L3、篩選起點 < 11:30 且幅度 ≥ L3）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import LVL_QUANTILES, SYMBOL, _ema20_range

NOON_MIN = 690          # 11:30（起點時間閘）
L3_COEF = LVL_QUANTILES[2][2]  # 0.711 × EMA20


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

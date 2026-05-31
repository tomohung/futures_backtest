"""當日 DCI（方向共識指標）— 收盤/事後值。詳見
research/active/H095-reach-ladder-exit/dci_spec.md。

W 用固定權值清單(無真實市值,以成交值近似權重)、H 用當日成交值前20、B 用漲跌家數。
盤中即時版需另接盤中三序列；此處僅供 chart-ui 覆盤標「事後」。
"""
from __future__ import annotations

from datetime import date

# 台股權值前 ~20 大（截至 2026-05，需偶爾更新）
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
_WL = (0.40, 0.35, 0.25)   # long: W,H,B
_WS = (0.30, 0.30, 0.40)   # short


def _band_long(c: float) -> str:
    return "strong" if c >= 0.30 else "weak" if c <= -0.10 else "mid"


def _band_short(c: float) -> str:
    return "strong" if c <= -0.20 else "weak" if c >= 0.10 else "mid"


def compute_daily_dci(conn, sel: date) -> dict | None:
    """回傳 {W,H,B,dci_long,dci_short,regime_long,regime_short} 或 None（資料不足）。"""
    b = conn.execute(
        "SELECT up_count, down_count, listed_count FROM market_breadth "
        "WHERE market='TWSE' AND trade_date = ?", [sel]
    ).fetchone()
    if not b or not b[2]:
        return None
    B = (b[0] - b[1]) / b[2]

    ph = ",".join(["?"] * len(TOP_WEIGHT_SYMBOLS))
    w = conn.execute(
        f"SELECT SUM(SIGN(change)*value)/NULLIF(SUM(value),0) FROM stock_day "
        f"WHERE market='TWSE' AND trade_date = ? AND symbol IN ({ph}) "
        f"AND change IS NOT NULL AND value IS NOT NULL",
        [sel, *TOP_WEIGHT_SYMBOLS],
    ).fetchone()
    h = conn.execute(
        "SELECT SUM(SIGN(change)*value)/NULLIF(SUM(value),0) FROM ("
        "  SELECT change, value FROM stock_day WHERE market='TWSE' AND trade_date = ? "
        "  AND change IS NOT NULL AND value IS NOT NULL ORDER BY value DESC LIMIT 20)",
        [sel],
    ).fetchone()
    if w is None or w[0] is None or h is None or h[0] is None:
        return None
    W, H = float(w[0]), float(h[0])

    dl = _WL[0] * W + _WL[1] * H + _WL[2] * B
    ds = _WS[0] * W + _WS[1] * H + _WS[2] * B
    return {
        "W": round(W, 3), "H": round(H, 3), "B": round(B, 3),
        "dci_long": round(dl, 3), "dci_short": round(ds, 3),
        "regime_long": _band_long(dl), "regime_short": _band_short(ds),
    }

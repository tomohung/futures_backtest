"""EstRisk 風險/安全價位（移植 close_risk_lines.pine）：全歷史 EMA(20) 日盤(08:45–13:45)
日高低範圍 → risk = ema/4、safe = risk/5。回傳每個交易日對應的 {risk, safe}。

值為 causal：某日的 risk 用「該日之前已完成日」的 EMA（不含當日），與 pine 在當日盤中顯示的值
一致，也與右側欄關卡價的 _ema20_range（同一條 EMA20）一致。
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from cachetools import TTLCache, cached

from src.chart_ui import paths

SYMBOL = "TX"
SPAN = 20

_cache: TTLCache = TTLCache(maxsize=4, ttl=3600)


@cached(_cache)
def compute_risklevels(db_path: Path | None = None) -> dict[str, dict]:
    p = str(db_path or paths.DUCKDB_PATH)
    with duckdb.connect(p, read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, MAX(high) - MIN(low) rng FROM ohlcv_1m "
            "WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "GROUP BY 1 ORDER BY d",
            [SYMBOL],
        ).fetchall()
    alpha = 2.0 / (SPAN + 1)
    ema: float | None = None
    n = 0                                  # 已處理的完成日數
    out: dict[str, dict] = {}
    for d, rng in rows:
        if n >= SPAN:                      # 至少 20 個完成日才有值（與 _ema20_range 一致）
            risk = ema / 4.0
            out[str(d)] = {"risk": round(risk, 1), "safe": round(risk / 5.0, 1)}
        ema = float(rng) if ema is None else alpha * float(rng) + (1 - alpha) * ema
        n += 1
    return out

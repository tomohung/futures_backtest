"""盤前『延伸力·多(0050期)』逐分鐘序列 — NYF（元大台灣50 ETF 期貨）版。

與 services/extension.py（cash W10 版）同質、不同標的：
  cash 版：W10 權值股現貨分K、錨當日現貨 open(09:00)、value-weighted tanh → 廣度延伸
  本檔   ：NYF(0050ETF期)、錨當日期貨 open(08:45)、單一標的 tanh        → 指數延伸

  ext_long_fut(t) = tanh( (NYF_close(t) − NYF_open@08:45) / range_NYF )
  range_NYF = NYF 自身日振幅(high−low) 的 causal EMA20（shift(1) 後 ewm20，不含當日）

優點：個股期 08:45 開盤、現貨 09:00 才開，故盤前 15 分鐘即有讀數，領先估現貨
延伸力多落點，且全日可與 cash 版 overlay 對照。資料源：aux_futures_1m（build_aux_futures.py）。
僅日盤 08:45~13:45。需該日前 ~20 交易日有 NYF 資料才有有效 range，否則回 None。

詳見 docs/superpowers/specs/2026-06-11-preopen-futures-extlong-design.md §9。
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb
import numpy as np
import pandas as pd

from src.chart_ui import paths
from src.chart_ui.services.extension import STRONG_LONG

SYMBOL = "NYF"
ANCHOR_TIME = "08:45:00"


def _causal_ema20_range(conn, sel: date) -> float | None:
    """NYF 日振幅(high−low) 的 causal EMA20（不含 sel 當日）。"""
    df = conn.execute(
        "SELECT CAST(timestamp AS DATE) AS d, MAX(high) - MIN(low) AS rng "
        "FROM aux_futures_1m WHERE symbol = ? AND CAST(timestamp AS DATE) <= ? "
        "GROUP BY d ORDER BY d", [SYMBOL, sel]).df()
    if df.empty or pd.Timestamp(sel) not in set(df["d"]):
        return None
    df["rng"] = df["rng"].astype(float)
    ema = df["rng"].shift(1).ewm(span=20, adjust=False).mean()
    val = ema[df["d"] == pd.Timestamp(sel)]
    if val.empty or not np.isfinite(val.iloc[0]) or val.iloc[0] <= 0:
        return None
    return float(val.iloc[0])


def compute_futures_extension(conn, sel: date) -> dict | None:
    """回傳 {'bars':[{'time':epoch,'ext_long':..}, ...], 'strong_long':..} 或 None。"""
    rng = _causal_ema20_range(conn, sel)
    if rng is None:
        return None
    mn = conn.execute(
        "SELECT CAST(timestamp AS TIME) AS t, open, close FROM aux_futures_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? ORDER BY t",
        [SYMBOL, sel]).df()
    if mn.empty:
        return None
    anchor = mn.loc[mn["t"].astype(str) == ANCHOR_TIME, "open"]
    if anchor.empty:
        return None
    opn = float(anchor.iloc[0])

    ext = np.tanh((mn["close"].astype(float) - opn) / rng)

    def _epoch(t) -> int:
        return int(datetime(sel.year, sel.month, sel.day, t.hour, t.minute,
                            t.second, tzinfo=timezone.utc).timestamp())

    bars = [{"time": _epoch(t), "ext_long": round(float(e), 4)}
            for t, e in zip(mn["t"], ext)]
    return {"bars": bars, "strong_long": STRONG_LONG}


_cache: dict[str, dict | None] = {}


def get_futures_extension(date_str: str) -> dict | None:
    """route 用：開唯讀連線算當日 NYF 延伸序列；逐日結果靜態 → 記憶體快取。"""
    if date_str in _cache:
        return _cache[date_str]
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        res = compute_futures_extension(conn, sel)
    _cache[date_str] = res
    return res

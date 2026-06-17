"""盤中『EstRange 預估振幅』逐分鐘高/低水平線，供 chart-ui 主圖疊線。

移植自 indicators/tradingview/est_range_tx.pine，但改用後端既有的
compute_vol_estimated_range（5 分 slot、EMA(20)、結算量×1.9）計算 est_range，
與 live 策略 S001-esthl 共用同一套 EstRange 邏輯（不另外複寫 Pine 演算法）。

每根 1 分 K：
  est_high  = session_low  + est_range            （預估高 100%，紅）
  est_low   = session_high - est_range            （預估低 100%，綠）

09:00 起顯示（est_range 暖機 + 1 slot 延遲，無 lookahead）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import duckdb
import pandas as pd

from src.chart_ui import paths

SHOW_START_MIN = 540      # 09:00（同 Pine show_start 預設）
_LOOKBACK_DAYS = 90       # 載入天數：EMA(20) 暖機需 ≥20 交易日，多載確保收斂


def _epoch(ts) -> int:
    dt = pd.Timestamp(ts).to_pydatetime()
    return int(dt.replace(tzinfo=timezone.utc).timestamp())   # naive→UTC，對齊 kline_loader


def compute_estrange_series(conn, sel: date) -> dict | None:
    """回傳 {'bars':[{time,est_high,est_low,est_range}, ...]} 或 None（無資料/暖機不足）。"""
    start = sel - timedelta(days=_LOOKBACK_DAYS)
    df = conn.execute(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS DATE) BETWEEN ? AND ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp",
        [start, sel]).df()
    if df.empty:
        return None
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    for c in df.columns:
        df[c] = df[c].astype(float)
    if not (df.index.normalize() == pd.Timestamp(sel)).any():
        return None

    # 與 live 策略共用：結算量校正 + 量加權預估振幅（5 分 slot、EMA20）
    from src.backtest.estimate_hl import compute_vol_estimated_range
    from src.backtest.runner import adjust_settlement_volume
    adjust_settlement_volume(df)
    df = compute_vol_estimated_range(df)

    day = df[df.index.normalize() == pd.Timestamp(sel)].copy()
    if day.empty:
        return None
    sess_high = day["High"].cummax()    # 當日盤中累積高（08:45 起）
    sess_low = day["Low"].cummin()      # 當日盤中累積低

    bars = []
    for ts in day.index:
        tod = ts.hour * 60 + ts.minute
        er = day.at[ts, "EstRange"]
        if tod < SHOW_START_MIN or pd.isna(er):
            continue
        sl = sess_low.loc[ts]
        sh = sess_high.loc[ts]
        bars.append({
            "time": _epoch(ts),
            "est_high": round(float(sl + er), 1),
            "est_low": round(float(sh - er), 1),
            "est_range": round(float(er), 1),
        })
    if not bars:
        return None
    return {"bars": bars}


_cache: dict[str, dict | None] = {}


def get_estrange(date_str: str) -> dict | None:
    """route 用：開唯讀連線算當日 EstRange 高/低序列；逐日結果靜態 → 記憶體快取。"""
    if date_str in _cache:
        return _cache[date_str]
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        res = compute_estrange_series(conn, sel)
    _cache[date_str] = res
    return res

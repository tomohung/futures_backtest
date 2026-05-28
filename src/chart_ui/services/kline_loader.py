"""讀 ohlcv_1m，做 session 過濾、adjust、intraday/daily 聚合。DuckDB 唯讀。"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

import duckdb
import pandas as pd
from cachetools import TTLCache, cached

from src.chart_ui import paths
from src.chart_ui.services.resample import resample_intraday

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
ALLOWED_TF = set(_TF_MINUTES) | {"1d"}
ALLOWED_SESSION = {"day", "full"}
ALLOWED_ADJUST = {"raw", "adj"}

DAY_OPEN = time(8, 45)
DAY_CLOSE = time(13, 45)
NIGHT_OPEN = time(15, 0)
DEFAULT_BUFFER_DAYS = 3

# 各 tf 日盤每日約略 bar 數，用來推算要載入幾個交易日，讓較大 tf 也有足夠 bar。
_BARS_PER_DAY = {"1m": 300, "5m": 60, "15m": 20, "30m": 10, "60m": 5}
_LOAD_TARGET_BARS = 600  # 目標載入量（含平移餘裕）


def _auto_buffer(tf: str) -> int:
    """依 tf 推算 center 兩側要載入的交易日數，使載入 bar 數約達 _LOAD_TARGET_BARS。"""
    bpd = _BARS_PER_DAY.get(tf, 300)
    span = bpd * 2  # center 兩側 → (2*buffer+1) 天
    return max(DEFAULT_BUFFER_DAYS, (_LOAD_TARGET_BARS + span - 1) // span)

# daily 聚合較重，快取（每路徑+session+adjust，TTL 1h）。
_daily_cache: TTLCache = TTLCache(maxsize=32, ttl=3600)


def _to_epoch(ts) -> int:
    dt = pd.Timestamp(ts).to_pydatetime()
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _trading_days(conn) -> list[date]:
    rows = conn.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE) AS d FROM ohlcv_1m "
        "WHERE CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY d"
    ).fetchall()
    return [r[0] for r in rows]


def _select_days(days: list[date], center, frm, to, buffer_days) -> list[date]:
    """選出要載入的交易日。center 模式取最接近 center（>=）那天的 ±buffer_days。
    center 晚於所有資料 → 落在最後一天；早於所有資料 → 落在第一天（不報錯，回傳最近端的視窗）。"""
    if center is not None:
        c = date.fromisoformat(center) if isinstance(center, str) else center
        idx = next((i for i, d in enumerate(days) if d >= c), len(days) - 1)
        lo = max(0, idx - buffer_days)
        hi = min(len(days), idx + buffer_days + 1)
        return days[lo:hi]
    f = date.fromisoformat(str(frm)[:10])
    t = date.fromisoformat(str(to)[:10])
    return [d for d in days if f <= d <= t]


def _ranges(selected: list[date], all_days: list[date], session: str):
    idx_of = {d: i for i, d in enumerate(all_days)}
    out = []
    for d in selected:
        end = datetime.combine(d, DAY_CLOSE)
        if session == "full":
            i = idx_of[d]
            start = datetime.combine(all_days[i - 1], NIGHT_OPEN) if i > 0 else datetime.combine(d, NIGHT_OPEN)
            # i==0 時 start>end → 視窗為空（無前夜資料），符合預期
        else:
            start = datetime.combine(d, DAY_OPEN)
        out.append((start, end))
    return out


def _in_ranges(ts: datetime, ranges) -> bool:
    return any(s <= ts <= e for s, e in ranges)


def load_kline(*, db_path: Path | None = None, center=None, frm=None, to=None,
               tf: str = "1m", session: str = "day", adjust: str = "raw",
               buffer_days: int | None = None) -> list[dict]:
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    if tf == "1d":
        return _load_daily(str(db_path), session, adjust, _db_token(db_path))

    minutes = _TF_MINUTES[tf]
    if buffer_days is None:                 # 未指定 → 依 tf 自動推算載入交易日數
        buffer_days = _auto_buffer(tf)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        all_days = _trading_days(conn)
        if not all_days:
            return []
        selected = _select_days(all_days, center, frm, to, buffer_days)
        if not selected:
            return []
        ranges = _ranges(selected, all_days, session)
        g_start = min(s for s, _ in ranges)
        g_end = max(e for _, e in ranges)
        df = conn.execute(
            "SELECT timestamp, open, high, low, close, volume, adjustment "
            "FROM ohlcv_1m WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp",
            [g_start, g_end],
        ).df()

    if df.empty:
        return []
    mask = df["timestamp"].apply(lambda t: _in_ranges(t.to_pydatetime(), ranges))
    df = df[mask]
    if df.empty:
        return []
    df = df.copy()
    for c in ("open", "high", "low", "close", "volume", "adjustment"):
        df[c] = df[c].astype(float)
    if adjust == "adj":
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] + df["adjustment"]
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    if minutes > 1:
        df = resample_intraday(df, minutes)
    df = df.reset_index()
    return [
        {
            "time": _to_epoch(r.timestamp),
            "open": float(r.open), "high": float(r.high),
            "low": float(r.low), "close": float(r.close),
            "volume": int(r.volume),
        }
        for r in df.itertuples(index=False)
    ]


def _db_token(db_path: Path) -> float:
    """DB 新鮮度 token（.duckdb 與 .wal 的最新 mtime）；放進 daily cache key，
    資料更新後 token 改變→自動失效，不需重啟 server。"""
    mt = db_path.stat().st_mtime if db_path.exists() else 0.0
    wal = db_path.with_name(db_path.name + ".wal")
    if wal.exists():
        mt = max(mt, wal.stat().st_mtime)
    return mt


@cached(_daily_cache, key=lambda db_path, session, adjust, token: (db_path, session, adjust, token))
def _load_daily(db_path: str, session: str, adjust: str, token: float) -> list[dict]:
    with duckdb.connect(db_path, read_only=True) as conn:
        if session == "full":
            sql = """
            WITH td AS (
              SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m
              WHERE CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ),
            night_dates AS (
              SELECT DISTINCT CAST(timestamp AS DATE) nd FROM ohlcv_1m
              WHERE CAST(timestamp AS TIME) >= TIME '15:00:00'
            ),
            night_map AS (
              SELECT nd, (SELECT min(d) FROM td WHERE d > nd) AS session_day FROM night_dates
            ),
            assigned AS (
              SELECT b.timestamp, b.open, b.high, b.low, b.close, b.volume, b.adjustment,
                CASE WHEN CAST(b.timestamp AS TIME) >= TIME '15:00:00'
                     THEN nm.session_day
                     ELSE CAST(b.timestamp AS DATE) END AS session_day
              FROM ohlcv_1m b
              LEFT JOIN night_map nm ON nm.nd = CAST(b.timestamp AS DATE)
              WHERE CAST(b.timestamp AS TIME) >= TIME '15:00:00'
                 OR CAST(b.timestamp AS TIME) <= TIME '05:00:00'
                 OR CAST(b.timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            )
            SELECT session_day AS d,
                   arg_min(open, timestamp) AS open, max(high) AS high,
                   min(low) AS low, arg_max(close, timestamp) AS close,
                   sum(volume) AS volume, arg_max(adjustment, timestamp) AS adjustment
            FROM assigned WHERE session_day IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        else:
            sql = """
            SELECT CAST(timestamp AS DATE) AS d,
                   arg_min(open, timestamp) AS open, max(high) AS high,
                   min(low) AS low, arg_max(close, timestamp) AS close,
                   sum(volume) AS volume, arg_max(adjustment, timestamp) AS adjustment
            FROM ohlcv_1m
            WHERE CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1 ORDER BY 1
            """
        df = conn.execute(sql).df()

    if df.empty:
        return []
    for c in ("open", "high", "low", "close", "adjustment"):
        df[c] = df[c].astype(float)
    if adjust == "adj":
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] + df["adjustment"]
    return [
        {
            "time": str(r.d)[:10],
            "open": float(r.open), "high": float(r.high),
            "low": float(r.low), "close": float(r.close),
            "volume": int(r.volume),
        }
        for r in df.itertuples(index=False)
    ]


def clear_daily_cache() -> None:
    _daily_cache.clear()

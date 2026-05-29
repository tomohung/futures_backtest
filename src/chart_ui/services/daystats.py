"""右側欄每日統計：20日平均振幅(日盤/全日盤)、今日日盤高低振幅、前一日 twnvix、關卡價。

關卡價與今日高低固定以日盤(08:45–13:45)為基準；20日視窗為選定日之前的 20 個交易日(不含當日)。
DuckDB 唯讀。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from src.chart_ui import paths

SYMBOL = "TX"
WINDOW = 20


def _trading_days(conn) -> list[date]:
    rows = conn.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY d",
        [SYMBOL],
    ).fetchall()
    return [r[0] for r in rows]


def _prior_days(days: list[date], sel: date, n: int) -> list[date]:
    """選定日之前的 n 個交易日（不含當日）。"""
    return [d for d in days if d < sel][-n:]


def _day_ranges(conn, day_list: list[date]) -> dict[date, float]:
    """日盤每日振幅 = MAX(high) - MIN(low)，08:45–13:45。"""
    if not day_list:
        return {}
    ph = ",".join(["?"] * len(day_list))
    rows = conn.execute(
        f"SELECT CAST(timestamp AS DATE) d, MAX(high) - MIN(low) rng FROM ohlcv_1m "
        f"WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        f"AND CAST(timestamp AS DATE) IN ({ph}) GROUP BY 1",
        [SYMBOL, *day_list],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _full_ranges(conn, day_list: list[date]) -> dict[date, float]:
    """全日盤每日振幅：前夜 15:00 → 隔日 05:00 + 當日日盤，歸屬到 session_day（同 kline_loader）。"""
    if not day_list:
        return {}
    lo = min(day_list) - timedelta(days=5)
    ph = ",".join(["?"] * len(day_list))
    sql = f"""
    WITH td AS (
      SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    ),
    night_dates AS (
      SELECT DISTINCT CAST(timestamp AS DATE) nd FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) >= TIME '15:00:00'
    ),
    night_map AS (
      SELECT nd, (SELECT min(d) FROM td WHERE d > nd) AS session_day FROM night_dates
    ),
    assigned AS (
      SELECT b.high, b.low,
        CASE WHEN CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             THEN nm.session_day ELSE CAST(b.timestamp AS DATE) END AS session_day
      FROM ohlcv_1m b
      LEFT JOIN night_map nm ON nm.nd = CAST(b.timestamp AS DATE)
      WHERE b.symbol = ?
        AND CAST(b.timestamp AS DATE) >= ?
        AND (CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             OR CAST(b.timestamp AS TIME) <= TIME '05:00:00'
             OR CAST(b.timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00')
    )
    SELECT session_day d, MAX(high) - MIN(low) rng
    FROM assigned WHERE session_day IN ({ph})
    GROUP BY 1
    """
    rows = conn.execute(sql, [SYMBOL, SYMBOL, SYMBOL, lo, *day_list]).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _today_hl(conn, sel: date) -> tuple[float, float] | None:
    row = conn.execute(
        "SELECT MAX(high), MIN(low) FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'",
        [SYMBOL, sel],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0]), float(row[1])


def _prev_vix(conn, sel: date) -> dict | None:
    row = conn.execute(
        "SELECT date, vix FROM vixtwn WHERE date < ? ORDER BY date DESC LIMIT 1", [sel]
    ).fetchone()
    if not row:
        return None
    return {"date": str(row[0]), "vix": float(row[1])}


def _stats(vals: list[float]) -> dict | None:
    if not vals:
        return None
    return {
        "avg": round(sum(vals) / len(vals)),
        "max": round(max(vals)),
        "min": round(min(vals)),
        "n": len(vals),
    }


def compute_daystats(*, date_str: str, db_path: Path | None = None) -> dict:
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        days = _trading_days(conn)
        prior = _prior_days(days, sel, WINDOW)
        day_r = _day_ranges(conn, prior)
        full_r = _full_ranges(conn, prior)
        today = _today_hl(conn, sel)
        prev_vix = _prev_vix(conn, sel)

    day_stats = _stats([day_r[d] for d in prior if d in day_r])
    full_stats = _stats([full_r[d] for d in prior if d in full_r])

    avg_range_20 = {
        "day": day_stats["avg"] if day_stats else None,
        "n_day": day_stats["n"] if day_stats else 0,
        "full": full_stats["avg"] if full_stats else None,
        "n_full": full_stats["n"] if full_stats else 0,
    }

    today_out = None
    if today:
        hi, lo = today
        today_out = {"high": round(hi), "low": round(lo), "range": round(hi - lo)}

    bull = bear = None
    if today and day_stats:
        hi, lo = today
        avg, mx, mn = day_stats["avg"], day_stats["max"], day_stats["min"]
        bull_raw = [
            ("多1 最小振幅", lo + mn),
            ("多2 0.6×均", lo + avg * 0.6),
            ("多3 0.85×均", lo + avg * 0.85),
            ("多4 最大振幅", lo + mx),
        ]
        bear_raw = [
            ("空1 最小振幅", hi - mn),
            ("空2 0.6×均", hi - avg * 0.6),
            ("空3 0.85×均", hi - avg * 0.85),
            ("空4 最大振幅", hi - mx),
        ]
        bull = [{"label": l, "price": round(p)} for l, p in sorted(bull_raw, key=lambda x: -x[1])]
        bear = [{"label": l, "price": round(p)} for l, p in sorted(bear_raw, key=lambda x: -x[1])]

    return {
        "date": date_str,
        "avg_range_20": avg_range_20,
        "today": today_out,
        "prev_vix": prev_vix,
        "range20_day": day_stats,
        "bull": bull,
        "bear": bear,
    }

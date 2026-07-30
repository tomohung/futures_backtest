"""Tests for parse_rpt 日盤缺口自癒偵測（find_day_session_gaps）。"""
from datetime import date

import duckdb
import pytest

from src.etl.parse_rpt import find_day_session_gaps


def _make_conn():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE ticks (
            trade_date DATE, symbol VARCHAR, contract VARCHAR,
            trade_time TIME, price DECIMAL(10,2), volume INT, is_auction BOOLEAN
        )
        """
    )
    return con


def _insert_night(con, d: str, n: int = 2000):
    """插入 n 筆夜盤 tick（15:00 起，逐秒），不含任何日盤。"""
    con.execute(
        """
        INSERT INTO ticks
        SELECT CAST(? AS DATE), 'TX', '202608',
               TIME '15:00:00' + (i * INTERVAL '1 second'),
               40000, 1, false
        FROM range(?) t(i)
        """,
        [d, n],
    )


def _insert_day(con, d: str):
    """插入幾筆日盤 tick（08:45~13:45）。"""
    con.execute(
        """
        INSERT INTO ticks VALUES
        (CAST(? AS DATE), 'TX', '202608', TIME '08:45:00', 40000, 1, true),
        (CAST(? AS DATE), 'TX', '202608', TIME '10:00:00', 40010, 1, false),
        (CAST(? AS DATE), 'TX', '202608', TIME '13:45:00', 40020, 1, true)
        """,
        [d, d, d],
    )


def test_detects_weekday_night_only_gap_confirmed_by_zip():
    """平日、只有夜盤、zip 內有日盤 → 應被標記為缺口。"""
    con = _make_conn()
    gap = date(2026, 7, 29)  # Wednesday
    _insert_night(con, "2026-07-29")

    result = find_day_session_gaps(con, lookback_days=3650, zip_checker=lambda d: d == gap)
    assert result == [gap]


def test_holiday_not_flagged_when_zip_has_no_day_session():
    """平日夜盤-only 但 zip 內無日盤（真休市）→ 不標記。"""
    con = _make_conn()
    _insert_night(con, "2026-01-01")  # New Year (Thursday), night fragment only

    result = find_day_session_gaps(con, lookback_days=3650, zip_checker=lambda d: False)
    assert result == []


def test_complete_day_not_flagged():
    """有日盤的完整交易日 → 不標記（即使 zip_checker 一律 True）。"""
    con = _make_conn()
    _insert_day(con, "2026-07-28")
    _insert_night(con, "2026-07-28")

    result = find_day_session_gaps(con, lookback_days=3650, zip_checker=lambda d: True)
    assert result == []


def test_weekend_night_fragment_excluded():
    """週末落地的跨午夜夜盤碎片 → 因非平日被排除。"""
    con = _make_conn()
    _insert_night(con, "2026-07-25")  # Saturday

    result = find_day_session_gaps(con, lookback_days=3650, zip_checker=lambda d: True)
    assert result == []


def test_lookback_window_limits_scan():
    """超出 lookback 天數的舊缺口不掃（以最新 trade_date 為基準）。"""
    con = _make_conn()
    _insert_night(con, "2026-01-07")   # old gap (Wednesday)
    _insert_day(con, "2026-07-30")     # newest date anchors the window
    _insert_night(con, "2026-07-30")

    # 只回看 30 天 → 2026-01-07 不在窗口內
    result = find_day_session_gaps(con, lookback_days=30, zip_checker=lambda d: True)
    assert result == []

    # 回看夠久 → 抓到
    result = find_day_session_gaps(con, lookback_days=3650, zip_checker=lambda d: d == date(2026, 1, 7))
    assert result == [date(2026, 1, 7)]

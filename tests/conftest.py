"""Shared test fixtures — creates a small in-memory DuckDB with sample data."""
import duckdb
import pytest
from datetime import date, time
from pathlib import Path

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test.duckdb"


def _create_fixture_db():
    """Build a small DuckDB with realistic sample data for testing."""
    FIXTURE_DB.parent.mkdir(exist_ok=True)
    if FIXTURE_DB.exists():
        FIXTURE_DB.unlink()

    con = duckdb.connect(str(FIXTURE_DB))

    con.execute("""
        CREATE TABLE ticks (
            trade_date   DATE,
            symbol       VARCHAR,
            contract     VARCHAR,
            trade_time   TIME,
            price        DECIMAL(10,2),
            volume       INT,
            is_auction   BOOLEAN
        )
    """)

    con.execute("""
        CREATE TABLE ohlcv_1m (
            timestamp       TIMESTAMP,
            symbol          VARCHAR,
            contract        VARCHAR,
            open            DECIMAL(10,2),
            high            DECIMAL(10,2),
            low             DECIMAL(10,2),
            close           DECIMAL(10,2),
            volume          INT,
            tick_count      INT,
            is_rollover     BOOLEAN,
            adjustment      DECIMAL(10,2),
            adj_close       DECIMAL(10,2)
        )
    """)

    con.execute("""
        CREATE TABLE ticks_options (
            trade_date     DATE,
            symbol         VARCHAR,
            strike         DECIMAL(10,2),
            contract       VARCHAR,
            put_call       VARCHAR,
            trade_time     TIME,
            price          DECIMAL(10,2),
            volume         INT,
            is_auction     BOOLEAN
        )
    """)

    con.execute("""
        CREATE TABLE rollover_log (
            rollover_date    DATE,
            symbol           VARCHAR,
            old_contract     VARCHAR,
            new_contract     VARCHAR,
            old_last_price   DECIMAL(10,2),
            new_first_price  DECIMAL(10,2),
            price_gap        DECIMAL(10,2),
            method           VARCHAR
        )
    """)

    # --- Sample ticks ---
    con.execute("""
        INSERT INTO ticks VALUES
        ('2025-06-16', 'TX', '202507', '08:45:00', 21000.00, 10, true),
        ('2025-06-16', 'TX', '202507', '08:46:00', 21010.00, 5,  false),
        ('2025-06-16', 'TX', '202507', '09:00:00', 21050.00, 8,  false),
        ('2025-06-16', 'TX', '202507', '13:45:00', 20980.00, 12, true),
        ('2025-06-17', 'TX', '202507', '08:45:00', 20990.00, 10, true),
        ('2025-06-17', 'TX', '202507', '09:30:00', 21100.00, 6,  false),
        ('2025-06-17', 'TX', '202507', '13:45:00', 21080.00, 15, true)
    """)

    # --- Sample ohlcv_1m: 2 days, day session 08:45~13:45, one bar per 15 min ---
    bars = []
    for d, base in [("2025-06-16", 21000), ("2025-06-17", 21050)]:
        minutes = []
        # Generate 1-min bars from 08:45 to 13:45 (301 bars)
        for h in range(8, 14):
            start_m = 45 if h == 8 else 0
            end_m = 46 if h == 13 else 60
            for m in range(start_m, end_m):
                bar_ts = f"{d} {h:02d}:{m:02d}:00"
                offset = (h - 8) * 60 + m - 45
                o = base + offset * 0.5
                c = o + 2
                hi = max(o, c) + 5
                lo = min(o, c) - 3
                minutes.append((bar_ts, o, hi, lo, c))

        for ts, o, hi, lo, c in minutes:
            bars.append(
                f"('{ts}', 'TX', '202507', {o:.2f}, {hi:.2f}, "
                f"{lo:.2f}, {c:.2f}, 100, 20, false, 0.00, {c:.2f})"
            )

    con.execute(f"INSERT INTO ohlcv_1m VALUES {','.join(bars)}")

    # --- Night session bars for 2025-06-16 (15:00~23:00, 1 bar/hour for simplicity) ---
    night_bars = []
    for h in range(15, 24):
        ts = f"2025-06-16 {h:02d}:00:00"
        o = 20980 + (h - 15) * 10
        c = o + 5
        night_bars.append(
            f"('{ts}', 'TX', '202507', {o:.2f}, {o+8:.2f}, "
            f"{o-3:.2f}, {c:.2f}, 50, 10, false, 0.00, {c:.2f})"
        )
    con.execute(f"INSERT INTO ohlcv_1m VALUES {','.join(night_bars)}")

    # --- Sample options ticks: 2025-06-16, near-month 202507 ---
    opt_rows = []
    strikes = [20500, 20600, 20700, 20800, 20900, 21000, 21100, 21200, 21300, 21400, 21500]
    for s in strikes:
        # Put volume peaks at 20800 (S1 candidate)
        put_vol = 500 if s == 20800 else (300 if s == 20700 else 50)
        # Call volume peaks at 21300
        call_vol = 400 if s == 21300 else (250 if s == 21400 else 30)
        opt_rows.append(
            f"('2025-06-16', 'TXO', {s:.2f}, '202507', 'P', "
            f"'10:00:00', {max(0, 21000-s):.2f}, {put_vol}, false)"
        )
        opt_rows.append(
            f"('2025-06-16', 'TXO', {s:.2f}, '202507', 'C', "
            f"'10:00:00', {max(0, s-21000):.2f}, {call_vol}, false)"
        )
    # Day 2
    for s in strikes:
        put_vol = 600 if s == 20900 else 40
        call_vol = 500 if s == 21200 else 35
        opt_rows.append(
            f"('2025-06-17', 'TXO', {s:.2f}, '202507', 'P', "
            f"'10:00:00', {max(0, 21050-s):.2f}, {put_vol}, false)"
        )
        opt_rows.append(
            f"('2025-06-17', 'TXO', {s:.2f}, '202507', 'C', "
            f"'10:00:00', {max(0, s-21050):.2f}, {call_vol}, false)"
        )

    con.execute(f"INSERT INTO ticks_options VALUES {','.join(opt_rows)}")

    con.close()


# Build once at import time
_create_fixture_db()


@pytest.fixture(scope="session")
def test_db_path():
    """Path to the fixture database."""
    return FIXTURE_DB


@pytest.fixture(scope="session")
def test_conn():
    """Read-only connection to the fixture database."""
    with duckdb.connect(str(FIXTURE_DB), read_only=True) as c:
        yield c

"""Smoke tests for ETL modules — verify DB schema expectations."""
import pytest
import duckdb
from pathlib import Path

DB_PATH = Path("data/futures.duckdb")

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="no database file"
)


@pytest.fixture(scope="module")
def conn():
    with duckdb.connect(str(DB_PATH), read_only=True) as c:
        yield c


class TestTicksTable:
    def test_exists(self, conn):
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        assert "ticks" in tables

    def test_has_expected_columns(self, conn):
        cols = {r[0] for r in conn.execute("DESCRIBE ticks").fetchall()}
        expected = {"trade_date", "symbol", "contract", "trade_time", "price", "volume", "is_auction"}
        assert expected.issubset(cols)

    def test_has_data(self, conn):
        count = conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
        assert count > 0


class TestOhlcv1mTable:
    def test_exists(self, conn):
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        assert "ohlcv_1m" in tables

    def test_has_expected_columns(self, conn):
        cols = {r[0] for r in conn.execute("DESCRIBE ohlcv_1m").fetchall()}
        expected = {"timestamp", "symbol", "contract", "open", "high", "low", "close", "volume"}
        assert expected.issubset(cols)

    def test_ohlc_integrity(self, conn):
        """high >= low, high >= open, high >= close for all rows."""
        bad = conn.execute("""
            SELECT COUNT(*) FROM ohlcv_1m
            WHERE high < low OR high < open OR high < close
               OR low > open OR low > close
        """).fetchone()[0]
        assert bad == 0, f"{bad} rows with invalid OHLC"


class TestTicksOptionsTable:
    def test_exists(self, conn):
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        assert "ticks_options" in tables

    def test_has_expected_columns(self, conn):
        cols = {r[0] for r in conn.execute("DESCRIBE ticks_options").fetchall()}
        expected = {"trade_date", "symbol", "strike", "contract", "put_call", "trade_time", "price", "volume"}
        assert expected.issubset(cols)

    def test_put_call_values(self, conn):
        values = {r[0] for r in conn.execute(
            "SELECT DISTINCT put_call FROM ticks_options"
        ).fetchall()}
        assert values == {"C", "P"}

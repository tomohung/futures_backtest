"""Tests for DB schema — uses fixture database."""
import pytest


class TestTicksTable:
    def test_exists(self, test_conn):
        tables = [r[0] for r in test_conn.execute("SHOW TABLES").fetchall()]
        assert "ticks" in tables

    def test_has_expected_columns(self, test_conn):
        cols = {r[0] for r in test_conn.execute("DESCRIBE ticks").fetchall()}
        expected = {"trade_date", "symbol", "contract", "trade_time", "price", "volume", "is_auction"}
        assert expected.issubset(cols)

    def test_has_data(self, test_conn):
        count = test_conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
        assert count > 0


class TestOhlcv1mTable:
    def test_exists(self, test_conn):
        tables = [r[0] for r in test_conn.execute("SHOW TABLES").fetchall()]
        assert "ohlcv_1m" in tables

    def test_has_expected_columns(self, test_conn):
        cols = {r[0] for r in test_conn.execute("DESCRIBE ohlcv_1m").fetchall()}
        expected = {"timestamp", "symbol", "contract", "open", "high", "low", "close", "volume"}
        assert expected.issubset(cols)

    def test_ohlc_integrity(self, test_conn):
        bad = test_conn.execute("""
            SELECT COUNT(*) FROM ohlcv_1m
            WHERE high < low OR high < open OR high < close
               OR low > open OR low > close
        """).fetchone()[0]
        assert bad == 0, f"{bad} rows with invalid OHLC"

    def test_has_two_days(self, test_conn):
        days = test_conn.execute("""
            SELECT COUNT(DISTINCT timestamp::DATE) FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """).fetchone()[0]
        assert days == 2


class TestTicksOptionsTable:
    def test_exists(self, test_conn):
        tables = [r[0] for r in test_conn.execute("SHOW TABLES").fetchall()]
        assert "ticks_options" in tables

    def test_has_expected_columns(self, test_conn):
        cols = {r[0] for r in test_conn.execute("DESCRIBE ticks_options").fetchall()}
        expected = {"trade_date", "symbol", "strike", "contract", "put_call", "trade_time", "price", "volume"}
        assert expected.issubset(cols)

    def test_put_call_values(self, test_conn):
        values = {r[0] for r in test_conn.execute(
            "SELECT DISTINCT put_call FROM ticks_options"
        ).fetchall()}
        assert values == {"C", "P"}

    def test_has_options_data(self, test_conn):
        count = test_conn.execute("SELECT COUNT(*) FROM ticks_options").fetchone()[0]
        assert count > 0

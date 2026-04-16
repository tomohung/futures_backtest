"""Tests for key_prices.py — the module that broke."""
import pytest
from pathlib import Path

DB_PATH = Path("data/futures.duckdb")

from src.analysis.key_prices import get_key_prices, print_report, _get_put_s1


@pytest.mark.skipif(not DB_PATH.exists(), reason="no database file")
class TestGetKeyPrices:
    @pytest.fixture(scope="class")
    def data(self):
        return get_key_prices()

    def test_returns_dict(self, data):
        assert isinstance(data, dict)

    def test_has_required_keys(self, data):
        required = [
            "last_day", "prev_day", "day", "night", "vwap",
            "ma30_20", "bars_15m_pre10", "weekday_stats", "put_s1",
        ]
        for key in required:
            assert key in data, f"missing key: {key}"

    def test_day_has_hlc(self, data):
        day = data["day"]
        assert "high" in day
        assert "low" in day
        assert "close" in day
        assert day["high"] >= day["low"]

    def test_vwap_is_dict(self, data):
        assert isinstance(data["vwap"], dict)
        assert len(data["vwap"]) >= 1

    def test_put_s1_structure(self, data):
        s1 = data["put_s1"]
        if s1 is not None:
            assert "s1" in s1
            assert "s1_vol" in s1
            assert "contract" in s1
            assert s1["s1"] > 0
            assert s1["s1_vol"] > 0

    def test_print_report_runs(self, data, capsys):
        print_report(data)
        output = capsys.readouterr().out
        assert "關鍵價格參考" in output
        assert "昨日行情" in output
        assert "評估" in output


@pytest.mark.skipif(not DB_PATH.exists(), reason="no database file")
class TestGetPutS1:
    def test_returns_none_for_nonexistent_date(self):
        result = _get_put_s1("1999-01-01", 20000.0)
        assert result is None

    def test_returns_dict_for_valid_date(self):
        import duckdb
        from pathlib import Path
        db = Path("data/futures.duckdb")
        if not db.exists():
            pytest.skip("no database")
        with duckdb.connect(str(db), read_only=True) as conn:
            latest = conn.execute(
                "SELECT MAX(trade_date) FROM ticks_options"
            ).fetchone()[0]
            if latest is None:
                pytest.skip("no options data")
            # Use a realistic ref_price from actual futures data
            fut = conn.execute("""
                SELECT close FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND timestamp::DATE = (SELECT MAX(timestamp::DATE) FROM ohlcv_1m WHERE symbol = 'TX')
                ORDER BY timestamp DESC LIMIT 1
            """).fetchone()
        if fut is None:
            pytest.skip("no futures data")
        ref = float(fut[0])
        result = _get_put_s1(latest, ref)
        assert result is not None
        assert result["s1"] <= ref

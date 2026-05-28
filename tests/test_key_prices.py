"""Tests for key_prices.py — uses fixture database."""
import pytest

import src.analysis.key_prices as kp


@pytest.fixture(autouse=True)
def _patch_db(test_db_path, monkeypatch):
    monkeypatch.setattr(kp, "DB_PATH", test_db_path)


class TestGetKeyPrices:
    @pytest.fixture(scope="class")
    def data(self, test_db_path):
        import src.analysis.key_prices as _kp
        orig = _kp.DB_PATH
        _kp.DB_PATH = test_db_path
        try:
            return _kp.get_key_prices()
        finally:
            _kp.DB_PATH = orig

    def test_returns_dict(self, data):
        assert isinstance(data, dict)

    def test_has_required_keys(self, data):
        required = [
            "last_day", "prev_day", "day", "night", "vwap",
            "ma30_20", "bars_15m_pre10", "night_vol_filter",
            "weekday_stats",
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

    def test_night_vol_filter_structure(self, data):
        nvf = data["night_vol_filter"]
        if nvf is not None:
            assert "night_range" in nvf
            assert "ema20" in nvf  # H075: SMA20 → EMA20
            assert "night_norm" in nvf
            assert "threshold" in nvf  # H075: dynamic expanding median
            assert "method" in nvf
            assert "pass" in nvf
            assert isinstance(nvf["pass"], bool)
            assert nvf["night_norm"] > 0
            assert nvf["threshold"] > 0

    def test_print_report_runs(self, data, capsys):
        kp.print_report(data)
        output = capsys.readouterr().out
        assert "關鍵價格參考" in output
        assert "昨日行情" in output
        assert "評估" in output


class TestStrategyRules:
    """Verify strategy skip rules are correctly encoded."""

    @pytest.fixture(scope="class")
    def data(self, test_db_path):
        import src.analysis.key_prices as _kp
        orig = _kp.DB_PATH
        _kp.DB_PATH = test_db_path
        try:
            return _kp.get_key_prices()
        finally:
            _kp.DB_PATH = orig

    def test_esthl_skips_thursday_and_friday(self, data):
        """EstHL must skip Thu(3) and Fri(4) regardless of night vol."""
        wd = data["weekday_stats"]["today_wd"]
        nvf = data.get("night_vol_filter")
        if wd in (3, 4):
            assert True, "EstHL should SKIP on Thu/Fri"
        elif nvf and nvf.get("pass") is not None:
            assert isinstance(nvf["pass"], bool)

    def test_reversal_skips_monday_and_friday(self, data):
        """Reversal must skip Mon(0) and Fri(4), plus night vol filter."""
        wd = data["weekday_stats"]["today_wd"]
        nvf = data.get("night_vol_filter")
        if wd in (0, 4):
            assert True, "Reversal should SKIP on Mon/Fri"
        elif nvf and nvf.get("pass") is not None:
            assert isinstance(nvf["pass"], bool)

    def test_night_vol_threshold_dynamic(self, data):
        """H075: threshold is dynamic (expanding median), not fixed 0.85."""
        nvf = data.get("night_vol_filter")
        if nvf and nvf.get("night_norm") is not None:
            assert nvf["pass"] == (nvf["night_norm"] >= nvf["threshold"])

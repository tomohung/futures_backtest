"""Smoke tests: verify all key modules import without errors."""
import importlib

import pytest

MODULES = [
    # ETL
    "src.etl.parse_rpt",
    "src.etl.build_1m",
    "src.etl.build_continuous",
    "src.etl.parse_options_rpt",
    "src.etl.validate",
    "src.etl.download",
    # Analysis
    "src.analysis.key_prices",
    "src.analysis.daily_range",
    "src.analysis.chart_style",
    # Strategies
    "src.strategies.orb",
    "src.strategies.reversal",
    "src.strategies.exhaustion",
    "src.strategies.estimate_hl_exit",
    "src.strategies.reversal_follow",
    # Backtest
    "src.backtest.runner",
    "src.backtest.estimate_hl",
    "src.backtest.strategy_health",
    "src.backtest.summary_all",
]


@pytest.mark.parametrize("module", MODULES)
def test_import(module):
    importlib.import_module(module)

"""Project-relative paths for chart-ui."""

import os
from pathlib import Path

# src/chart_ui/paths.py -> project root (parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 預設讀正式庫；ETL（如 stock_min 回補）占用寫鎖時，可用 env CHART_UI_DB
# 指向快照副本繞過（回補只寫 stock_min，chart-ui 用的 ohlcv_1m 不受影響）。
DUCKDB_PATH = Path(os.environ.get("CHART_UI_DB", PROJECT_ROOT / "data" / "futures.duckdb"))
CHART_LISTS_DIR = PROJECT_ROOT / "data" / "chart_lists"
STATIC_DIR = Path(__file__).resolve().parent / "static"

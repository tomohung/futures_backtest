"""Project-relative paths for chart-ui."""

from pathlib import Path

# src/chart_ui/paths.py -> project root (parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
CHART_LISTS_DIR = PROJECT_ROOT / "data" / "chart_lists"
STATIC_DIR = Path(__file__).resolve().parent / "static"

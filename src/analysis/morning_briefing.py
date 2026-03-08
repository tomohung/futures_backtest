#!/usr/bin/env python3
"""
早盤簡報：更新資料 + key_prices + daily_range

使用方式：
    uv run python src/analysis/morning_briefing.py
"""
import subprocess
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).parent
ETL_DIR = Path(__file__).parents[2] / "src" / "etl"


def run(script: Path) -> None:
    subprocess.run([sys.executable, str(script)], check=True)


if __name__ == "__main__":
    run(ETL_DIR / "daily_update.py")
    run(ANALYSIS_DIR / "key_prices.py")
    run(ANALYSIS_DIR / "daily_range.py")

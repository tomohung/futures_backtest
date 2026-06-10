#!/usr/bin/env python3
"""
早盤簡報：更新資料 + key_prices（含 VIX regime + H103）+ daily_range + breadth_thermometer + fg_composite_monitor

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
    run(ANALYSIS_DIR / "key_prices.py")   # 含 VIX regime + H103（已 fold 入,進 clipboard）
    run(ANALYSIS_DIR / "daily_range.py")
    run(ANALYSIS_DIR / "breadth_thermometer.py")
    run(ANALYSIS_DIR / "fg_composite_monitor.py")

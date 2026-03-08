#!/usr/bin/env python3
"""
早盤簡報：一次執行 key_prices + daily_range

使用方式：
    uv run python src/analysis/morning_briefing.py
"""
import subprocess
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).parent


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ANALYSIS_DIR / script)], check=True)


if __name__ == "__main__":
    run("key_prices.py")
    run("daily_range.py")

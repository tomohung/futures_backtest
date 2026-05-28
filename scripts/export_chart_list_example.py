"""把現有回測 CSV 轉成 chart-ui 清單範例。

用法：
    uv run python scripts/export_chart_list_example.py output/s002_reversal_2025-01-01.csv reversal-2025
"""

import sys

import pandas as pd

from src.chart_ui.list_writer import write_chart_list_from_backtesting


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    csv_path, list_id = sys.argv[1], sys.argv[2]
    df = pd.read_csv(csv_path)
    path = write_chart_list_from_backtesting(df, list_id, name=list_id)
    print(f"wrote {path} ({len(df)} trades)")


if __name__ == "__main__":
    main()

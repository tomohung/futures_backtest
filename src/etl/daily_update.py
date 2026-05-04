"""
每日更新 pipeline 整合腳本

執行順序：
  Step 0a: download.py          — 下載期貨最新 zip 檔（可跳過）
  Step 0b: download_options.py  — 下載選擇權最新 zip 檔（可跳過）
  Step 0c: download_stock_market.py — 下載 TWSE/TPEX 廣度資料（可跳過）
  Step 1a: parse_rpt.py         — 期貨 zip → ticks 表
  Step 1b: parse_options_rpt.py — 選擇權 zip → ticks_options 表
  Step 1c: parse_stock_market.py — TWSE/TPEX JSON → market_breadth + stock_day
  Step 2:  build_1m.py          — ticks → ohlcv_1m 表
  Step 3:  build_continuous.py  — 換倉 + Panama adj_close
  Step 4:  validate.py          — 資料驗證（可跳過）

使用 subprocess 呼叫各 step，避免 DuckDB 寫入鎖定衝突。
"""

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
ETL_DIR = Path(__file__).parent


def taiwan_today() -> date:
    return date.today()


def run_step(script: Path, extra_args: list[str] | None = None) -> bool:
    """Run a Python script as a subprocess using the current venv Python.

    Returns True if successful, False otherwise.
    """
    cmd = [sys.executable, str(script)] + (extra_args or [])
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[ERROR] Step failed (return code {result.returncode}): {script.name}")
        return False
    return True


def _parse_args() -> argparse.Namespace:
    today = taiwan_today()

    parser = argparse.ArgumentParser(
        description="每日更新：下載 + ETL pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 完整更新（自動偵測起始，下載到今天，跑全部 ETL）
  uv run python src/etl/daily_update.py

  # 指定日期範圍
  uv run python src/etl/daily_update.py --start 2026-02-01 --end 2026-02-28

  # 跳過下載（已手動放好 zip）
  uv run python src/etl/daily_update.py --skip-download

  # 跳過驗證（加速）
  uv run python src/etl/daily_update.py --skip-validate

  # 只下載，不跑 ETL
  uv run python src/etl/download.py
        """,
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="下載起始日期（預設：磁碟上最新 zip 的隔天）",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        default=(today + timedelta(days=4)).isoformat(),
        help=f"下載結束日期（預設：今天 +4 天 {today + timedelta(days=4)}，涵蓋週末後的下一個交易日）",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳過 Step 0（不下載，直接跑 ETL）",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="跳過 Step 4（驗證）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="下載每筆間隔秒數（預設 1.0）",
    )
    parser.add_argument(
        "--redownload-recent",
        type=int,
        default=2,
        metavar="N",
        help="強制重新下載磁碟上最新 N 個 zip（預設 2）",
    )
    parser.add_argument(
        "--reimport-recent",
        type=int,
        default=2,
        metavar="N",
        help="強制重新匯入最新 N 個 zip 日期的 ticks（預設 2）",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=30,
        metavar="N",
        help="未指定 --start 時，往前掃描 N 天補漏（預設 30）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("台指期每日更新 pipeline")
    print("=" * 60)

    # Step 0: Download
    if not args.skip_download:
        download_args = [
            "--end", args.end,
            "--delay", str(args.delay),
            "--redownload-recent", str(args.redownload_recent),
            "--backfill-days", str(args.backfill_days),
        ]
        if args.start:
            download_args += ["--start", args.start]
        ok = run_step(ETL_DIR / "download.py", download_args)
        if not ok:
            print("\n[ABORT] 期貨下載失敗，停止 pipeline。")
            sys.exit(1)

        # Step 0b: Download options
        options_download_args = [
            "--end", args.end,
            "--delay", str(args.delay),
            "--redownload-recent", str(args.redownload_recent),
        ]
        if args.start:
            options_download_args += ["--start", args.start]
        ok = run_step(ETL_DIR / "download_options.py", options_download_args)
        if not ok:
            print("\n[WARN] 選擇權下載失敗，繼續 pipeline。")

        # Step 0c: Download TWSE/TPEX stock market breadth
        stock_market_args = [
            "--end", args.end,
            "--delay", str(max(args.delay, 3.0)),  # TWSE/TPEX rate limit 較嚴
        ]
        if args.start:
            stock_market_args += ["--start", args.start]
        ok = run_step(ETL_DIR / "download_stock_market.py", stock_market_args)
        if not ok:
            print("\n[WARN] 股市廣度下載失敗，繼續 pipeline。")
    else:
        print("\n[跳過] Step 0: 下載")

    # Step 1a: parse_rpt (futures)
    ok = run_step(ETL_DIR / "parse_rpt.py", ["--reimport-recent", str(args.reimport_recent)])
    if not ok:
        print("\n[ABORT] parse_rpt.py 失敗，停止 pipeline。")
        sys.exit(1)

    # Step 1b: parse_options_rpt
    ok = run_step(ETL_DIR / "parse_options_rpt.py", ["--reimport-recent", str(args.reimport_recent)])
    if not ok:
        print("\n[WARN] parse_options_rpt.py 失敗，選擇權資料未更新。")

    # Step 1c: parse_stock_market（只處理最近 N 天，避免全量重跑）
    parse_start = (taiwan_today() - timedelta(days=args.backfill_days)).isoformat()
    ok = run_step(ETL_DIR / "parse_stock_market.py", ["--start", parse_start])
    if not ok:
        print("\n[WARN] parse_stock_market.py 失敗，股市廣度資料未更新。")

    # Step 2: build_1m
    ok = run_step(ETL_DIR / "build_1m.py")
    if not ok:
        print("\n[ABORT] build_1m.py 失敗，停止 pipeline。")
        sys.exit(1)

    # Step 3: build_continuous
    ok = run_step(ETL_DIR / "build_continuous.py")
    if not ok:
        print("\n[ABORT] build_continuous.py 失敗，停止 pipeline。")
        sys.exit(1)

    # Step 4: validate (optional)
    if not args.skip_validate:
        ok = run_step(ETL_DIR / "validate.py")
        if not ok:
            print("\n[WARN] validate.py 回報錯誤，但 pipeline 已完成。")
    else:
        print("\n[跳過] Step 4: 驗證")

    # Step 5: build_vixtwn (optional, warn-only)
    ok = run_step(ETL_DIR / "build_vixtwn.py")
    if not ok:
        print("\n[WARN] build_vixtwn.py 失敗，VIX 資料未更新。")

    print("\n" + "=" * 60)
    print("Pipeline 完成。")
    print("=" * 60)


if __name__ == "__main__":
    main()

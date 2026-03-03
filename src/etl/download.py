"""
下載期交所每日 zip 檔 → data/raw/<year>/Daily_YYYY_MM_DD.zip

URL 格式：
  https://www.taifex.com.tw/file/taifex/Dailydownload/Dailydownload/Daily_YYYY_MM_DD.zip

非交易日：期交所回傳 HTML（非 zip），magic-byte 檢查後丟棄。
使用 stdlib urllib，無需額外相依。
"""

import argparse
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

BASE_URL = (
    "https://www.taifex.com.tw/file/taifex/Dailydownload/Dailydownload/"
    "Daily_{year}_{month}_{day}.zip"
)

ZIP_MAGIC = b"PK\x03\x04"  # local file header signature for zip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def taiwan_today() -> date:
    """Return current date in Taiwan Standard Time (UTC+8)."""
    tz_tst = timezone(timedelta(hours=8))
    return date.today()  # system clock — assume server runs in TST or caller adjusts


def detect_start_date() -> date:
    """Return the day after the latest zip found on disk, or a sensible default."""
    zips = sorted(RAW_DIR.glob("**/Daily_*.zip"))
    dates: list[date] = []
    for p in zips:
        d = _date_from_filename(p.name)
        if d:
            dates.append(d)
    if dates:
        return max(dates) + timedelta(days=1)
    # fallback: start from yesterday
    return taiwan_today() - timedelta(days=1)


def existing_zip_dates() -> set[date]:
    """Return the set of dates for which a zip already exists on disk."""
    result: set[date] = set()
    for p in RAW_DIR.glob("**/Daily_*.zip"):
        d = _date_from_filename(p.name)
        if d:
            result.add(d)
    return result


def _date_from_filename(name: str) -> date | None:
    m = re.search(r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip", name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _zip_path(target_date: date) -> Path:
    year_dir = RAW_DIR / str(target_date.year)
    return year_dir / f"Daily_{target_date:%Y_%m_%d}.zip"


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------

def download_one(target_date: date, delay: float = 1.0, force: bool = False) -> str:
    """Download zip for target_date.

    Returns:
        'saved'        — zip written to disk (new file)
        'updated'      — zip re-downloaded and overwritten (force=True)
        'skipped'      — file already exists on disk and force=False
        'non_trading'  — server returned non-zip content (HTML)
        'error'        — HTTP error or network failure
    """
    dest = _zip_path(target_date)

    if dest.exists() and not force:
        return "skipped"

    was_existing = dest.exists()

    url = BASE_URL.format(
        year=target_date.strftime("%Y"),
        month=target_date.strftime("%m"),
        day=target_date.strftime("%d"),
    )

    if delay > 0:
        time.sleep(delay)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            content: bytes = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "non_trading"
        print(f"  [error] HTTP {e.code} for {target_date}")
        return "error"
    except Exception as e:
        print(f"  [error] {e} for {target_date}")
        return "error"

    # magic-byte check: real zip starts with PK\x03\x04
    if content[:4] != ZIP_MAGIC:
        return "non_trading"

    # atomic write: .tmp → rename
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.tmp")
    tmp.write_bytes(content)
    tmp.rename(dest)

    return "updated" if was_existing else "saved"


# ---------------------------------------------------------------------------
# Batch download
# ---------------------------------------------------------------------------

def download_range(
    start: date,
    end: date,
    delay: float = 1.0,
    dry_run: bool = False,
    redownload_recent: int = 2,
) -> dict[str, int]:
    """Download all dates in [start, end] (inclusive).

    Also force re-downloads the most recent `redownload_recent` zips already on
    disk, even if they fall before `start` (they may be incomplete partial uploads).

    Returns count dict with keys: saved, updated, skipped, non_trading, error.
    """
    counts: dict[str, int] = {"saved": 0, "updated": 0, "skipped": 0, "non_trading": 0, "error": 0}

    # Determine which dates to force re-download (N most recent zips on disk)
    all_zip_dates = sorted(existing_zip_dates())
    force_dates: set[date] = set(all_zip_dates[-redownload_recent:]) if redownload_recent > 0 else set()
    if force_dates:
        print(f"強制重新下載最近 {len(force_dates)} 個 zip：{sorted(force_dates)}")

    # Union of force_dates and [start, end]
    to_process: dict[date, bool] = {d: True for d in force_dates}
    current = start
    while current <= end:
        if current not in to_process:
            to_process[current] = False
        current += timedelta(days=1)

    for target in sorted(to_process):
        force = to_process[target]
        dest = _zip_path(target)
        if dry_run:
            label = "force" if force else ("skipped" if dest.exists() else "would_download")
            print(f"  [dry-run] {target}  →  {label}")
        else:
            status = download_one(target, delay=delay, force=force)
            print(f"  {target}  →  {status}")
            counts[status] = counts.get(status, 0) + 1

    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    today = taiwan_today()

    parser = argparse.ArgumentParser(
        description="下載期交所每日 zip 檔",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 自動偵測起始日期，下載到今天
  uv run python src/etl/download.py

  # 指定範圍
  uv run python src/etl/download.py --start 2026-02-01 --end 2026-02-28

  # 預覽（不實際下載）
  uv run python src/etl/download.py --dry-run
        """,
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="起始日期（預設：磁碟上最新 zip 的隔天）",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        default=today.isoformat(),
        help=f"結束日期（預設：今天 {today}）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="每次下載間隔秒數（預設 1.0）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出待下載日期，不實際下載",
    )
    parser.add_argument(
        "--redownload-recent",
        type=int,
        default=2,
        metavar="N",
        help="強制重新下載磁碟上最新 N 個 zip（可能是不完整的早期上傳，預設 2）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    end = date.fromisoformat(args.end)
    if args.start:
        start = date.fromisoformat(args.start)
    else:
        start = detect_start_date()

    print(f"下載範圍：{start} ~ {end}")
    if args.dry_run:
        print("（dry-run 模式，不實際下載）")

    if start > end:
        print("起始日期晚於結束日期，無需下載。")
        return

    counts = download_range(
        start, end,
        delay=args.delay,
        dry_run=args.dry_run,
        redownload_recent=args.redownload_recent,
    )

    if not args.dry_run:
        print("\n=== 下載結果 ===")
        print(f"  新增：     {counts['saved']}")
        print(f"  重新下載： {counts['updated']}")
        print(f"  已跳過：   {counts['skipped']}")
        print(f"  非交易日： {counts['non_trading']}")
        print(f"  錯誤：     {counts['error']}")


if __name__ == "__main__":
    main()

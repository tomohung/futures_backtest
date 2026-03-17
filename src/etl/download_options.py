"""
下載期交所每日選擇權 tick zip → data/raw_options/<年份>/OptionsDaily_YYYY_MM_DD.zip

URL 格式：
  https://www.taifex.com.tw/file/taifex/Dailydownload/OptionsDailydownload/OptionsDaily_YYYY_MM_DD.zip

期交所僅保留最近 30 個交易日。
"""

import argparse
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_options"

BASE_URL = (
    "https://www.taifex.com.tw/file/taifex/Dailydownload/OptionsDailydownload/"
    "OptionsDaily_{year}_{month}_{day}.zip"
)

ZIP_MAGIC = b"PK\x03\x04"


def taiwan_today() -> date:
    return date.today()


def detect_start_date(backfill_days: int = 45) -> date:
    return taiwan_today() - timedelta(days=backfill_days)


def existing_zip_dates() -> set[date]:
    dates: set[date] = set()
    for p in RAW_DIR.glob("**/OptionsDaily_*.zip"):
        d = date_from_zip(p)
        if d is not None:
            dates.add(d)
    return dates


def date_from_zip(path: Path) -> date | None:
    m = re.search(r"OptionsDaily_(\d{4})_(\d{2})_(\d{2})\.zip", path.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def download_one(target_date: date, delay: float = 1.0, force: bool = False) -> str:
    if target_date.weekday() >= 5:
        return "weekend"

    year_dir = RAW_DIR / str(target_date.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    fname = f"OptionsDaily_{target_date.year}_{target_date.month:02d}_{target_date.day:02d}.zip"
    fpath = year_dir / fname

    if fpath.exists() and not force:
        return "skipped"

    url = BASE_URL.format(
        year=target_date.year,
        month=f"{target_date.month:02d}",
        day=f"{target_date.day:02d}",
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read()
    except urllib.error.HTTPError:
        return "non_trading"
    except Exception as e:
        print(f"  [ERROR] {target_date}: {e}")
        return "error"

    if data[:4] != ZIP_MAGIC:
        return "non_trading"

    tmp = fpath.with_suffix(".zip.tmp")
    tmp.write_bytes(data)
    tmp.rename(fpath)

    if delay > 0:
        time.sleep(delay)
    return "saved"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下載期交所選擇權每日 tick zip")
    parser.add_argument(
        "--start", type=str, default=None, metavar="YYYY-MM-DD",
        help="起始日期（預設：自動偵測，回掃 45 天）",
    )
    parser.add_argument(
        "--end", type=str, default=None, metavar="YYYY-MM-DD",
        help="結束日期（預設：今天）",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="強制重新下載已存在的 zip",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="每次下載後等待秒數（預設 1.0）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    start = date.fromisoformat(args.start) if args.start else detect_start_date()
    end = date.fromisoformat(args.end) if args.end else taiwan_today()

    print(f"下載選擇權資料：{start} ~ {end}")
    existing = existing_zip_dates()
    print(f"磁碟上已有 {len(existing)} 個 zip")

    saved = skipped = non_trading = 0
    d = start
    while d <= end:
        result = download_one(d, delay=args.delay, force=args.force)
        if result == "saved":
            print(f"  ✓ {d}")
            saved += 1
        elif result == "skipped":
            skipped += 1
        elif result == "non_trading" or result == "weekend":
            non_trading += 1
        d += timedelta(days=1)

    print(f"\n下載完成：新增 {saved}，跳過 {skipped}，非交易日 {non_trading}")
    print(f"磁碟 zip 總數：{len(list(RAW_DIR.glob('**/OptionsDaily_*.zip')))}")


if __name__ == "__main__":
    main()

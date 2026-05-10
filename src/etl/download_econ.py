"""
下載國發會景氣指標與燈號 ZIP → data/raw_econ/eco_indicators_YYYY-MM-DD.zip

來源：政府資料開放平台 dataset 6099 → ws.ndc.gov.tw 上的 ZIP（內含 5 組 CSV + 5 組 schema）

我們關注的檔案：景氣指標與燈號.csv
- 欄位：Date(YYYYMM), 領先指標(綜合/不含趨勢), 同時指標(綜合/不含趨勢), 落後指標(綜合/不含趨勢),
       景氣對策信號綜合分數(int), 景氣對策信號(紅/黃紅/綠/黃藍/藍)
- 歷史：1982-01 至最新（每月底更新前月資料）

ZIP URL 是動態取自 data.gov.tw/dataset/6099 頁面（NDC 偶爾會更新檔案 ID）。
有指定 --url 時直接用該 URL。

用法：
  uv run python src/etl/download_econ.py                  # 抓今天的 snapshot
  uv run python src/etl/download_econ.py --force           # 重抓覆蓋
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_econ"

DATASET_PAGE = "https://data.gov.tw/dataset/6099"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 futures-backtest/1.0"

# 從 dataset 頁面 HTML 抽出 ws.ndc.gov.tw/Download.ashx 連結（完整含 n=、icon= 參數）
NDC_URL_RE = re.compile(
    r'https://ws\.ndc\.gov\.tw/Download\.ashx\?'
    r'u=[A-Za-z0-9%]+'
    r'(?:&(?:amp;)?n=[A-Za-z0-9%]+)?'
    r'(?:&(?:amp;)?icon=[A-Za-z0-9.%]+)?'
)


def _zip_path(snapshot: date) -> Path:
    return RAW_DIR / f"eco_indicators_{snapshot:%Y-%m-%d}.zip"


def discover_zip_url() -> str:
    """從 data.gov.tw dataset 頁面找最新的 ZIP 下載 URL。"""
    req = urllib.request.Request(DATASET_PAGE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = NDC_URL_RE.search(html)
    if not m:
        raise RuntimeError(f"找不到 NDC ZIP 下載 URL，請檢查 {DATASET_PAGE}")
    # 還原 &amp; → &
    return m.group(0).replace("&amp;", "&")


def download(snapshot: date | None = None, url: str | None = None, force: bool = False) -> str:
    snapshot = snapshot or date.today()
    dest = _zip_path(snapshot)
    if dest.exists() and not force:
        return "skipped"

    if url is None:
        url = discover_zip_url()
        print(f"  Resolved ZIP URL: {url[:80]}...")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    if len(raw) < 1000:
        raise RuntimeError(f"ZIP too small ({len(raw)} bytes)，可能下載失敗")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.tmp")
    tmp.write_bytes(raw)
    tmp.rename(dest)
    return "saved"


def main() -> None:
    p = argparse.ArgumentParser(description="Download NDC economic indicator ZIP")
    p.add_argument("--snapshot", help="Snapshot date YYYY-MM-DD (default: today)")
    p.add_argument("--url", help="Override ZIP URL")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    snapshot = date.fromisoformat(args.snapshot) if args.snapshot else date.today()
    result = download(snapshot, url=args.url, force=args.force)
    dest = _zip_path(snapshot)
    if result == "saved":
        print(f"  [saved] {dest} ({dest.stat().st_size:,} bytes)")
    else:
        print(f"  [skipped] {dest} 已存在（用 --force 重抓）")


if __name__ == "__main__":
    main()

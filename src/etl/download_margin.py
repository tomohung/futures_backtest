"""
下載 TWSE 信用交易彙總（每日）→ data/raw_margin/<year>/twse_margin_YYYY-MM-DD.json

來源：MI_MARGN endpoint (selectType=ALL)
  - tables[0]：信用交易統計（融資/融券交易單位、融資金額仟元）← 我們要的核心
  - tables[1]：個股融資融券明細（暫不使用）

歷史可追溯：2010-01-04 確認可用（更早未驗證）。

用法：
  uv run python src/etl/download_margin.py                          # 預設抓最近 30 天
  uv run python src/etl/download_margin.py --start 2010-01-01 --end 2026-05-10

非交易日：API 回傳 stat 非 OK → 建立 .non_trading marker 跳過。
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_margin"

ENDPOINT = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_compact}&selectType=ALL&response=json"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 futures-backtest/1.0"

# TWSE cert 缺 Subject Key Identifier，新版 OpenSSL 嚴格檢查會擋
_RELAXED_CTX = ssl.create_default_context()
_RELAXED_CTX.check_hostname = False
_RELAXED_CTX.verify_mode = ssl.CERT_NONE


def _json_path(target: date) -> Path:
    return RAW_DIR / str(target.year) / f"twse_margin_{target:%Y-%m-%d}.json"


def _marker_path(target: date) -> Path:
    return RAW_DIR / str(target.year) / f"twse_margin_{target:%Y-%m-%d}.non_trading"


def _is_known_non_trading(target: date, trust_marker_days: int = 7) -> bool:
    if target.weekday() >= 5:
        return True
    if not _marker_path(target).exists():
        return False
    cutoff = date.today() - timedelta(days=trust_marker_days)
    return target < cutoff


def _looks_like_data(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    stat = payload.get("stat", "")
    if isinstance(stat, str) and stat != "OK" and "OK" not in stat.upper():
        return False
    tables = payload.get("tables", [])
    if not tables:
        return False
    # 第 0 張表（彙總）至少要有 3 行
    t0 = tables[0]
    if not isinstance(t0, dict):
        return False
    return len(t0.get("data", [])) >= 3


def download_one(target: date, delay: float = 3.0, force: bool = False) -> str:
    dest = _json_path(target)
    if dest.exists() and not force:
        return "skipped"
    if not force and _is_known_non_trading(target):
        return "non_trading"

    url = ENDPOINT.format(date_compact=target.strftime("%Y%m%d"))

    if delay > 0:
        time.sleep(delay)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_RELAXED_CTX) as resp:
            raw: bytes = resp.read()
    except urllib.error.HTTPError as e:
        print(f"  [error] HTTP {e.code} for {target}")
        return "error"
    except Exception as e:
        print(f"  [error] {e} for {target}")
        return "error"

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"  [error] JSON decode failed for {target}: {e}")
        return "error"

    if not _looks_like_data(payload):
        marker = _marker_path(target)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return "non_trading"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    tmp.rename(dest)

    marker = _marker_path(target)
    if marker.exists():
        marker.unlink()
    return "saved"


def download_range(start: date, end: date, delay: float = 3.0) -> dict[str, int]:
    counts = {"saved": 0, "skipped": 0, "non_trading": 0, "error": 0}
    current = start
    while current <= end:
        result = download_one(current, delay=delay)
        counts[result] += 1
        if result == "saved":
            print(f"  [saved] {current}")
        elif result == "error":
            print(f"  [error] {current}")
        current += timedelta(days=1)
    return counts


def parse_date(s: str) -> date:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"date must be YYYY-MM-DD: {s}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def main() -> None:
    p = argparse.ArgumentParser(description="Download TWSE margin trading aggregate")
    p.add_argument("--start", type=parse_date)
    p.add_argument("--end", type=parse_date)
    p.add_argument("--delay", type=float, default=3.0)
    args = p.parse_args()

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=30))

    print(f"Downloading TWSE margin {start} ~ {end}, delay={args.delay}s")
    counts = download_range(start, end, delay=args.delay)
    total = sum(counts.values())
    print(f"\n=== Summary === {counts}  (total {total})")


if __name__ == "__main__":
    main()

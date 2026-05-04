"""
下載 TWSE / TPEX 每日市場資料 → data/raw_market/<source>/<year>/<source>_YYYY-MM-DD.json

來源：
  - TWSE MI_INDEX (type=ALL)：含市場彙總（漲跌家數、總成交額）+ 每日收盤行情（個股 OHLCV）
  - TPEX highlight：上櫃市場彙總（資本額、市值、總成交額等）
  - TPEX dailyQuotes：上櫃個股 OHLCV + 次日漲停跌停價

用法：
  uv run python src/etl/download_stock_market.py                # 預設抓最近 30 天
  uv run python src/etl/download_stock_market.py --start 2024-01-01 --end 2026-04-30

非交易日：API 回傳 stat 非 ok 或 tables 為空，建立 marker file 後續跳過。
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
from typing import Literal

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_market"

Source = Literal["twse_mi_index", "tpex_highlight", "tpex_daily_quotes"]

ENDPOINTS: dict[Source, str] = {
    "twse_mi_index": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_compact}&type=ALL&response=json",
    "tpex_highlight": "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight?date={date_slash}&id=&response=json",
    "tpex_daily_quotes": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={date_slash}&id=&response=json",
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 futures-backtest/1.0"

# TWSE 的 SSL cert 缺 Subject Key Identifier，新版 OpenSSL 嚴格檢查會擋。
# 公開歷史行情資料無敏感性，建一個不驗證 cert 的 context 給 *.twse.com.tw 用。
_RELAXED_SSL_HOSTS = {"www.twse.com.tw", "twse.com.tw", "www.tpex.org.tw", "tpex.org.tw"}
_RELAXED_CTX = ssl.create_default_context()
_RELAXED_CTX.check_hostname = False
_RELAXED_CTX.verify_mode = ssl.CERT_NONE


def _ssl_context_for(url: str) -> ssl.SSLContext | None:
    for host in _RELAXED_SSL_HOSTS:
        if f"//{host}/" in url or url.startswith(f"https://{host}/"):
            return _RELAXED_CTX
    return None


def _json_path(source: Source, target: date) -> Path:
    return RAW_DIR / source / str(target.year) / f"{source}_{target:%Y-%m-%d}.json"


def _marker_path(source: Source, target: date) -> Path:
    return RAW_DIR / source / str(target.year) / f"{source}_{target:%Y-%m-%d}.non_trading"


def _is_known_non_trading(source: Source, target: date, trust_marker_days: int = 7) -> bool:
    """週末 OR 已有 non_trading marker 且該日期早於最近信任期。"""
    if target.weekday() >= 5:
        return True
    if not _marker_path(source, target).exists():
        return False
    cutoff = date.today() - timedelta(days=trust_marker_days)
    return target < cutoff


def _build_url(source: Source, target: date) -> str:
    return ENDPOINTS[source].format(
        date_compact=target.strftime("%Y%m%d"),
        date_slash=target.strftime("%Y/%m/%d"),
    )


def _looks_like_data(payload: dict) -> bool:
    """JSON 是否真的有資料（非交易日 / 異常）。"""
    if not isinstance(payload, dict):
        return False
    stat = payload.get("stat")
    if isinstance(stat, str) and stat != "ok" and "OK" not in stat.upper():
        if "沒有" in stat or "無" in stat or "查無" in stat:
            return False
    tables = payload.get("tables")
    if isinstance(tables, list) and tables:
        for t in tables:
            data = t.get("data") if isinstance(t, dict) else None
            if isinstance(data, list) and len(data) > 0:
                return True
        return False
    if isinstance(payload.get("data"), list) and payload["data"]:
        return True
    return False


def download_one(
    source: Source,
    target: date,
    delay: float = 3.0,
    force: bool = False,
) -> str:
    """Download one (source, date). Returns: saved/skipped/non_trading/error."""
    dest = _json_path(source, target)

    if dest.exists() and not force:
        return "skipped"
    if not force and _is_known_non_trading(source, target):
        return "non_trading"

    url = _build_url(source, target)

    if delay > 0:
        time.sleep(delay)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = _ssl_context_for(url)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw: bytes = resp.read()
    except urllib.error.HTTPError as e:
        print(f"  [error] HTTP {e.code} for {source} {target}")
        return "error"
    except Exception as e:
        print(f"  [error] {e} for {source} {target}")
        return "error"

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"  [error] JSON decode failed for {source} {target}: {e}")
        return "error"

    if not _looks_like_data(payload):
        marker = _marker_path(source, target)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return "non_trading"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    tmp.rename(dest)

    marker = _marker_path(source, target)
    if marker.exists():
        marker.unlink()

    return "saved"


def download_range(
    start: date,
    end: date,
    sources: list[Source],
    delay: float = 3.0,
) -> dict[str, dict[str, int]]:
    """Download (sources × date range). Returns per-source counts."""
    counts: dict[str, dict[str, int]] = {
        s: {"saved": 0, "skipped": 0, "non_trading": 0, "error": 0} for s in sources
    }

    current = start
    while current <= end:
        for source in sources:
            result = download_one(source, current, delay=delay)
            counts[source][result] += 1
            if result == "saved":
                print(f"  [saved] {source} {current}")
            elif result == "error":
                print(f"  [error] {source} {current}")
        current += timedelta(days=1)
    return counts


def parse_date(s: str) -> date:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"date must be YYYY-MM-DD: {s}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def main() -> None:
    p = argparse.ArgumentParser(description="Download TWSE/TPEX daily market data")
    p.add_argument("--start", type=parse_date, help="start date (YYYY-MM-DD); default = today - 30")
    p.add_argument("--end", type=parse_date, help="end date (YYYY-MM-DD); default = today")
    p.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3)")
    p.add_argument(
        "--sources",
        nargs="+",
        default=["twse_mi_index", "tpex_highlight", "tpex_daily_quotes"],
        choices=list(ENDPOINTS.keys()),
    )
    args = p.parse_args()

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=30))

    print(f"Downloading {args.sources} for {start} ~ {end}, delay={args.delay}s")
    counts = download_range(start, end, args.sources, delay=args.delay)

    print("\n=== Summary ===")
    for source, c in counts.items():
        total = sum(c.values())
        print(f"  {source}: {c}  (total {total})")


if __name__ == "__main__":
    main()

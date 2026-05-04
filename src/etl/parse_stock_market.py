"""
Parse TWSE / TPEX 每日 JSON → DuckDB tables `market_breadth`, `stock_day`.

Tables
------
market_breadth (trade_date, market):
    每日大盤廣度（上市/上櫃各一行）

stock_day (trade_date, market, symbol):
    個股 OHLCV，已標記是否漲停/跌停

冪等：重跑會 DELETE 對應日期+市場的舊資料再 INSERT。
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import duckdb

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_market"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

STOCK_SYMBOL_RE = re.compile(r"^\d{4}[A-Z]?$")
SIGN_RE = re.compile(r"color:(red|green)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_BREADTH = """
CREATE TABLE IF NOT EXISTS market_breadth (
    trade_date        DATE,
    market            VARCHAR,
    listed_count      INTEGER,
    up_count          INTEGER,
    up_limit_count    INTEGER,
    down_count        INTEGER,
    down_limit_count  INTEGER,
    unchanged_count   INTEGER,
    no_trade_count    INTEGER,
    total_value       BIGINT,
    PRIMARY KEY (trade_date, market)
);
"""

SCHEMA_STOCK = """
CREATE TABLE IF NOT EXISTS stock_day (
    trade_date     DATE,
    market         VARCHAR,
    symbol         VARCHAR,
    name           VARCHAR,
    open           DECIMAL(12,4),
    high           DECIMAL(12,4),
    low            DECIMAL(12,4),
    close          DECIMAL(12,4),
    change         DECIMAL(12,4),
    volume         BIGINT,
    value          BIGINT,
    trade_count    INTEGER,
    is_limit_up    BOOLEAN,
    is_limit_down  BOOLEAN,
    PRIMARY KEY (trade_date, market, symbol)
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(s: Any) -> int | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).strip().replace(",", "")
    if not s or s in {"--", "-"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _to_float(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", "").replace(" ", "")
    if not s or s in {"--", "-"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date_from_filename(p: Path) -> date | None:
    m = re.search(r"_(\d{4})-(\d{2})-(\d{2})\.json$", p.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _signed_change(magnitude_str: Any, sign_html: Any) -> float | None:
    """TWSE 個股的漲跌價差 = 數字字串 + 符號（藏在 HTML <p color:red/green>）。"""
    m = _to_float(magnitude_str)
    if m is None:
        return None
    if not sign_html:
        return m
    sm = SIGN_RE.search(str(sign_html))
    if sm and sm.group(1).lower() == "green":
        return -m
    return m


def _parse_count_with_limit(cell: str) -> tuple[int | None, int | None]:
    """'5,710(258)' → (5710, 258);  '341' → (341, None)。"""
    if cell is None:
        return None, None
    s = str(cell).replace(",", "").strip()
    m = re.match(r"^(\d+)\s*\((\d+)\)\s*$", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    if s.isdigit():
        return int(s), None
    return None, None


# ---------------------------------------------------------------------------
# TWSE parsing
# ---------------------------------------------------------------------------

def parse_twse(payload: dict, trade_date: date) -> tuple[dict, list[dict]]:
    """Parse TWSE MI_INDEX JSON. Returns (breadth_row, [stock_rows])."""
    tables = payload.get("tables", [])

    breadth: dict = {
        "trade_date": trade_date,
        "market": "TWSE",
        "listed_count": None,
        "up_count": None,
        "up_limit_count": None,
        "down_count": None,
        "down_limit_count": None,
        "unchanged_count": None,
        "no_trade_count": None,
        "total_value": None,
    }

    for t in tables:
        title = t.get("title", "") or ""
        fields = t.get("fields", []) or []
        data = t.get("data", []) or []

        if "漲跌證券數" in title:
            stock_col_idx = fields.index("股票") if "股票" in fields else 2
            for row in data:
                if not row:
                    continue
                cell = row[stock_col_idx] if len(row) > stock_col_idx else None
                kind = (row[0] or "").strip()
                if kind.startswith("上漲"):
                    c, l = _parse_count_with_limit(cell)
                    breadth["up_count"], breadth["up_limit_count"] = c, l
                elif kind.startswith("下跌"):
                    c, l = _parse_count_with_limit(cell)
                    breadth["down_count"], breadth["down_limit_count"] = c, l
                elif kind.startswith("持平"):
                    c, _ = _parse_count_with_limit(cell)
                    breadth["unchanged_count"] = c
                elif kind.startswith("未成交"):
                    c, _ = _parse_count_with_limit(cell)
                    breadth["no_trade_count"] = c

        elif "大盤統計" in title:
            # Row 0 = "1.一般股票", value column = "成交金額(元)"
            for row in data:
                if not row:
                    continue
                kind = str(row[0] or "").strip()
                if kind.startswith("1.") and "一般股票" in kind:
                    breadth["total_value"] = _to_int(row[1])
                    break

    # 推算 listed_count
    parts = [
        breadth.get("up_count") or 0,
        breadth.get("down_count") or 0,
        breadth.get("unchanged_count") or 0,
        breadth.get("no_trade_count") or 0,
    ]
    if any(parts):
        breadth["listed_count"] = sum(parts)

    # Per-stock OHLCV
    stocks: list[dict] = []
    for t in tables:
        title = t.get("title", "") or ""
        if "每日收盤行情" not in title:
            continue
        fields = t.get("fields", []) or []
        idx = {f: i for i, f in enumerate(fields)}
        required = ["證券代號", "證券名稱", "開盤價", "最高價", "最低價", "收盤價",
                    "漲跌(+/-)", "漲跌價差", "成交股數", "成交金額", "成交筆數"]
        if not all(k in idx for k in required):
            continue
        for row in t.get("data", []):
            if not row or len(row) < len(fields):
                continue
            symbol = str(row[idx["證券代號"]]).strip()
            if not STOCK_SYMBOL_RE.match(symbol):
                continue
            close = _to_float(row[idx["收盤價"]])
            high = _to_float(row[idx["最高價"]])
            low = _to_float(row[idx["最低價"]])
            open_ = _to_float(row[idx["開盤價"]])
            change = _signed_change(row[idx["漲跌價差"]], row[idx["漲跌(+/-)"]])
            volume_shares = _to_int(row[idx["成交股數"]])
            value = _to_int(row[idx["成交金額"]])
            trade_count = _to_int(row[idx["成交筆數"]])

            if close is None or volume_shares is None or volume_shares == 0:
                continue
            prev_close = close - change if change is not None else None
            is_limit_up, is_limit_down = _flag_limit(close, high, low, prev_close)

            stocks.append({
                "trade_date": trade_date,
                "market": "TWSE",
                "symbol": symbol,
                "name": str(row[idx["證券名稱"]]).strip(),
                "open": open_, "high": high, "low": low, "close": close,
                "change": change,
                "volume": volume_shares, "value": value, "trade_count": trade_count,
                "is_limit_up": is_limit_up, "is_limit_down": is_limit_down,
            })

    return breadth, stocks


# ---------------------------------------------------------------------------
# TPEX parsing
# ---------------------------------------------------------------------------

def parse_tpex_highlight(payload: dict, trade_date: date) -> dict:
    """TPEX 上櫃當日彙總 → market_breadth row。"""
    breadth: dict = {
        "trade_date": trade_date, "market": "TPEX",
        "listed_count": None, "up_count": None, "up_limit_count": None,
        "down_count": None, "down_limit_count": None,
        "unchanged_count": None, "no_trade_count": None, "total_value": None,
    }
    tables = payload.get("tables", [])
    if not tables:
        return breadth
    t = tables[0]
    fields = t.get("fields", [])
    data = t.get("data", [[]])
    if not data or not data[0]:
        return breadth
    row = data[0]
    idx = {f: i for i, f in enumerate(fields)}

    breadth["listed_count"] = _to_int(row[idx["上櫃家數"]]) if "上櫃家數" in idx else None
    breadth["up_count"] = _to_int(row[idx["上漲家數"]]) if "上漲家數" in idx else None
    breadth["up_limit_count"] = _to_int(row[idx["漲停家數"]]) if "漲停家數" in idx else None
    breadth["down_count"] = _to_int(row[idx["下跌家數"]]) if "下跌家數" in idx else None
    breadth["down_limit_count"] = _to_int(row[idx["跌停家數"]]) if "跌停家數" in idx else None
    breadth["unchanged_count"] = _to_int(row[idx["平盤家數"]]) if "平盤家數" in idx else None
    breadth["no_trade_count"] = (
        _to_int(row[idx["未成交(含暫停交易)家數"]]) if "未成交(含暫停交易)家數" in idx else None
    )
    # 本日總成交值單位是百萬元 → 轉元
    if "本日總成交值(佰萬元)" in idx:
        v = _to_int(row[idx["本日總成交值(佰萬元)"]])
        breadth["total_value"] = v * 1_000_000 if v is not None else None
    return breadth


def parse_tpex_quotes(payload: dict, trade_date: date) -> list[dict]:
    """TPEX dailyQuotes → list of stock_day rows。"""
    stocks: list[dict] = []
    for t in payload.get("tables", []):
        title = t.get("title", "") or ""
        if "上櫃股票行情" not in title:
            continue
        fields = t.get("fields", []) or []
        # TPEX 欄位名有空白如 "次日 漲停價"，這裡正規化做匹配
        norm = {re.sub(r"\s+", "", f): i for i, f in enumerate(fields)}
        required = ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低",
                    "成交股數", "成交金額(元)", "成交筆數",
                    "次日漲停價", "次日跌停價"]
        if not all(k in norm for k in required):
            continue
        for row in t.get("data", []):
            if not row or len(row) < len(fields):
                continue
            symbol = str(row[norm["代號"]]).strip()
            if not STOCK_SYMBOL_RE.match(symbol):
                continue
            close = _to_float(row[norm["收盤"]])
            high = _to_float(row[norm["最高"]])
            low = _to_float(row[norm["最低"]])
            open_ = _to_float(row[norm["開盤"]])
            change = _to_float(row[norm["漲跌"]])  # TPEX 已含正負號
            volume_shares = _to_int(row[norm["成交股數"]])
            value = _to_int(row[norm["成交金額(元)"]])
            trade_count = _to_int(row[norm["成交筆數"]])

            if close is None or volume_shares is None or volume_shares == 0:
                continue
            prev_close = close - change if change is not None else None
            is_limit_up, is_limit_down = _flag_limit(close, high, low, prev_close)

            stocks.append({
                "trade_date": trade_date,
                "market": "TPEX",
                "symbol": symbol,
                "name": str(row[norm["名稱"]]).strip(),
                "open": open_, "high": high, "low": low, "close": close,
                "change": change,
                "volume": volume_shares, "value": value, "trade_count": trade_count,
                "is_limit_up": is_limit_up, "is_limit_down": is_limit_down,
            })
    return stocks


# ---------------------------------------------------------------------------
# Limit-up/down detection
# ---------------------------------------------------------------------------

def _flag_limit(close, high, low, prev_close) -> tuple[bool, bool]:
    """Approximate 收盤=漲停/跌停 判斷。

    台灣漲跌停 = ±10% of prev_close（以最接近 tick 向下取整，故實際 % ≤ 10）。
    判定條件：
      - is_limit_up: close == high AND change_pct >= 9.5%
      - is_limit_down: close == low AND change_pct <= -9.5%

    如果 prev_close 不可得（例如新上市首日），回傳 False/False。
    """
    if close is None or prev_close is None or prev_close <= 0:
        return False, False
    pct = (close - prev_close) / prev_close
    is_up = (high is not None and close == high and pct >= 0.095)
    is_down = (low is not None and close == low and pct <= -0.095)
    return is_up, is_down


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------

def write_breadth(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    if not rows:
        return
    keys = [(r["trade_date"], r["market"]) for r in rows]
    conn.executemany(
        "DELETE FROM market_breadth WHERE trade_date = ? AND market = ?", keys,
    )
    conn.executemany(
        """
        INSERT INTO market_breadth
        (trade_date, market, listed_count, up_count, up_limit_count,
         down_count, down_limit_count, unchanged_count, no_trade_count, total_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(r["trade_date"], r["market"], r["listed_count"], r["up_count"],
          r["up_limit_count"], r["down_count"], r["down_limit_count"],
          r["unchanged_count"], r["no_trade_count"], r["total_value"]) for r in rows],
    )


def write_stocks(conn: duckdb.DuckDBPyConnection, day_market_pairs: set[tuple[date, str]],
                 rows: list[dict]) -> None:
    if not day_market_pairs:
        return
    conn.executemany(
        "DELETE FROM stock_day WHERE trade_date = ? AND market = ?",
        list(day_market_pairs),
    )
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO stock_day
        (trade_date, market, symbol, name, open, high, low, close, change,
         volume, value, trade_count, is_limit_up, is_limit_down)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(r["trade_date"], r["market"], r["symbol"], r["name"],
          r["open"], r["high"], r["low"], r["close"], r["change"],
          r["volume"], r["value"], r["trade_count"],
          r["is_limit_up"], r["is_limit_down"]) for r in rows],
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def iter_files(source: str, start: date | None, end: date | None) -> Iterable[tuple[Path, date]]:
    base = RAW_DIR / source
    if not base.exists():
        return
    for p in sorted(base.glob("**/*.json")):
        d = _date_from_filename(p)
        if d is None:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        yield p, d


def main() -> None:
    p = argparse.ArgumentParser(description="Parse TWSE/TPEX raw JSON into DuckDB")
    p.add_argument("--start", help="YYYY-MM-DD; default = no lower bound")
    p.add_argument("--end", help="YYYY-MM-DD; default = no upper bound")
    args = p.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    breadth_rows: list[dict] = []
    stock_rows: list[dict] = []
    day_market_pairs: set[tuple[date, str]] = set()

    twse_count = tpex_breadth_count = tpex_quote_count = 0

    for path, d in iter_files("twse_mi_index", start, end):
        payload = json.loads(path.read_text())
        breadth, stocks = parse_twse(payload, d)
        breadth_rows.append(breadth)
        stock_rows.extend(stocks)
        day_market_pairs.add((d, "TWSE"))
        twse_count += 1

    for path, d in iter_files("tpex_highlight", start, end):
        payload = json.loads(path.read_text())
        breadth_rows.append(parse_tpex_highlight(payload, d))
        tpex_breadth_count += 1

    for path, d in iter_files("tpex_daily_quotes", start, end):
        payload = json.loads(path.read_text())
        stocks = parse_tpex_quotes(payload, d)
        stock_rows.extend(stocks)
        day_market_pairs.add((d, "TPEX"))
        tpex_quote_count += 1

    print(f"Parsed: TWSE={twse_count}, TPEX-highlight={tpex_breadth_count}, "
          f"TPEX-quotes={tpex_quote_count}")
    print(f"Breadth rows: {len(breadth_rows)}, Stock rows: {len(stock_rows)}")

    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(SCHEMA_BREADTH)
        conn.execute(SCHEMA_STOCK)
        write_breadth(conn, breadth_rows)
        write_stocks(conn, day_market_pairs, stock_rows)
        n_b = conn.execute("SELECT COUNT(*) FROM market_breadth").fetchone()[0]
        n_s = conn.execute("SELECT COUNT(*) FROM stock_day").fetchone()[0]
    print(f"DB now has: market_breadth={n_b}, stock_day={n_s}")


if __name__ == "__main__":
    main()

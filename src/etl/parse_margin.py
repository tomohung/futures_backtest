"""
Parse TWSE 信用交易彙總 JSON → DuckDB table `margin_balance`。

只解析 tables[0]（市場彙總）。tables[1] 是個股明細，目前不存進 DB。

冪等：重跑會 DELETE 對應日期再 INSERT。

用法：
  uv run python src/etl/parse_margin.py                    # parse 所有檔案
  uv run python src/etl/parse_margin.py --start 2026-01-01 # 只 parse 指定日期之後的檔案
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
RAW_DIR = PROJECT_ROOT / "data" / "raw_margin"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

SCHEMA_MARGIN = """
CREATE TABLE IF NOT EXISTS margin_balance (
    trade_date              DATE PRIMARY KEY,
    -- 融資(交易單位)：張為單位
    fin_units_buy           BIGINT,
    fin_units_sell          BIGINT,
    fin_units_cash_repay    BIGINT,
    fin_units_prev_bal      BIGINT,
    fin_units_curr_bal      BIGINT,
    -- 融券(交易單位)：張為單位
    short_units_buy         BIGINT,
    short_units_sell        BIGINT,
    short_units_cash_repay  BIGINT,
    short_units_prev_bal    BIGINT,
    short_units_curr_bal    BIGINT,
    -- 融資金額(仟元)：千元 NTD ← 大盤融資餘額主要指標
    fin_amt_buy             BIGINT,
    fin_amt_sell            BIGINT,
    fin_amt_cash_repay      BIGINT,
    fin_amt_prev_bal        BIGINT,
    fin_amt_curr_bal        BIGINT
);
"""

# Table 0 row order: 融資(交易單位)、融券(交易單位)、融資金額(仟元)
ROW_KIND_MAP = {
    "融資(交易單位)": "fin_units",
    "融券(交易單位)": "short_units",
    "融資金額(仟元)": "fin_amt",
}

# row[1..5] = 買進、賣出、現金償還、前日餘額、今日餘額
COL_SUFFIXES = ["buy", "sell", "cash_repay", "prev_bal", "curr_bal"]


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


def _date_from_filename(p: Path) -> date | None:
    m = re.search(r"_(\d{4})-(\d{2})-(\d{2})\.json$", p.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def parse_one(payload: dict, trade_date: date) -> dict | None:
    """Parse Table 0 (market aggregate). Returns row dict or None if malformed."""
    tables = payload.get("tables", [])
    if not tables:
        return None
    t0 = tables[0]
    data_rows = t0.get("data", [])
    if len(data_rows) < 3:
        return None

    row: dict = {"trade_date": trade_date}
    for data_row in data_rows:
        if not data_row:
            continue
        kind_zh = str(data_row[0]).strip()
        kind_en = ROW_KIND_MAP.get(kind_zh)
        if kind_en is None:
            continue
        for i, suffix in enumerate(COL_SUFFIXES, start=1):
            col = f"{kind_en}_{suffix}"
            row[col] = _to_int(data_row[i]) if i < len(data_row) else None

    # 必要欄位至少要有 fin_amt_curr_bal
    if row.get("fin_amt_curr_bal") is None:
        return None
    return row


def write_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        "DELETE FROM margin_balance WHERE trade_date = ?",
        [(r["trade_date"],) for r in rows],
    )
    cols = (
        ["trade_date"]
        + [f"{k}_{s}" for k in ROW_KIND_MAP.values() for s in COL_SUFFIXES]
    )
    placeholders = ", ".join(["?"] * len(cols))
    conn.executemany(
        f"INSERT INTO margin_balance ({', '.join(cols)}) VALUES ({placeholders})",
        [tuple(r.get(c) for c in cols) for r in rows],
    )


def iter_files(start: date | None, end: date | None) -> Iterable[tuple[Path, date]]:
    if not RAW_DIR.exists():
        return
    for p in sorted(RAW_DIR.glob("**/*.json")):
        d = _date_from_filename(p)
        if d is None:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        yield p, d


def main() -> None:
    p = argparse.ArgumentParser(description="Parse TWSE margin JSON into DuckDB")
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD")
    args = p.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    rows: list[dict] = []
    skipped = 0
    for path, d in iter_files(start, end):
        try:
            payload = json.loads(path.read_text())
        except Exception as e:
            print(f"  [skip] {path.name}: {e}")
            skipped += 1
            continue
        row = parse_one(payload, d)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

    print(f"Parsed: {len(rows)}, skipped: {skipped}")

    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(SCHEMA_MARGIN)
        write_rows(conn, rows)
        n = conn.execute("SELECT COUNT(*) FROM margin_balance").fetchone()[0]
        latest = conn.execute(
            "SELECT trade_date, fin_amt_curr_bal FROM margin_balance ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
    print(f"DB now has: margin_balance={n}, latest={latest}")


if __name__ == "__main__":
    main()

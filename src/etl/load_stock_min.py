"""
Phase 2：把 `data/stock_min_raw/*.parquet`（download_stock_min.py 的落地檔）
載入 DuckDB 的 `stock_min` 表。快、幾分鐘，可隨時做。

預設載入 futures.duckdb；之後若要改用獨立 flushdb，加 --db 指向別的檔即可。
全量重建（DELETE 全表後重灌），parquet 是 single source of truth，故冪等。

用法：
  uv run python src/etl/load_stock_min.py                       # → data/futures.duckdb
  uv run python src/etl/load_stock_min.py --db data/stock_min.duckdb
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RAW_DIR = PROJECT_ROOT / "data" / "stock_min_raw"

SCHEMA_STOCK_MIN = """
CREATE TABLE IF NOT EXISTS stock_min (
    trade_date  DATE,
    stock_id    VARCHAR,
    minute      TIME,
    open   DECIMAL(12,4),
    high   DECIMAL(12,4),
    low    DECIMAL(12,4),
    close  DECIMAL(12,4),
    volume BIGINT,
    PRIMARY KEY (trade_date, stock_id, minute)
);
"""

COLS = "trade_date, stock_id, minute, open, high, low, close, volume"


def load(db_path: Path, raw_dir: Path) -> dict:
    """全量重建 stock_min（DELETE 全表 → INSERT read_parquet）。回傳統計。"""
    files = sorted(raw_dir.glob("*.parquet"))
    if not files:
        raise SystemExit(f"找不到任何 parquet：{raw_dir}")
    glob = str(raw_dir / "*.parquet")
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(SCHEMA_STOCK_MIN)
        conn.execute("DELETE FROM stock_min")
        conn.execute(
            f"INSERT INTO stock_min ({COLS}) "
            f"SELECT {COLS} FROM read_parquet('{glob}')"
        )
        n_rows, n_days, lo, hi = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT trade_date), "
            "MIN(trade_date), MAX(trade_date) FROM stock_min"
        ).fetchone()
    return {"files": len(files), "rows": n_rows, "days": n_days, "lo": lo, "hi": hi}


def main() -> None:
    p = argparse.ArgumentParser(description="載入 stock_min parquet → DuckDB")
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = p.parse_args()

    print(f"載入 {args.raw_dir}/*.parquet → {args.db} 的 stock_min …")
    st = load(args.db, args.raw_dir)
    print(f"完成：{st['files']} 檔 / {st['days']} 交易日 / {st['rows']:,} rows "
          f"（{st['lo']} ~ {st['hi']}）")


if __name__ == "__main__":
    main()

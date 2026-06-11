"""
Phase 2：把 `data/stock_min_raw/*.parquet`（download_stock_min.py 的落地檔）
載入 DuckDB 的 `stock_min` 表。快、幾分鐘，可隨時做。

預設載入 futures.duckdb；之後若要改用獨立 flushdb，加 --db 指向別的檔即可。

**增量 upsert（預設）**：只刪掉「本次要載入的那些 trade_date」再灌，其餘日期不動，
故可逐月（或逐日）載入而不影響已在庫的其他月份。parquet 是 single source of
truth，重跑同一批檔=冪等（先刪該日再灌）。`--rebuild` 才做全表 DELETE 後重灌。

用法：
  uv run python src/etl/load_stock_min.py                            # 增量載入全部落地檔
  uv run python src/etl/load_stock_min.py --start 2025-04-01 --end 2025-04-30  # 只增量載 4 月
  uv run python src/etl/load_stock_min.py --rebuild                  # 全表重建
  uv run python src/etl/load_stock_min.py --db data/stock_min.duckdb
"""

from __future__ import annotations

import argparse
from datetime import date
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


def _file_date(f: Path) -> date | None:
    """從檔名 YYYY-MM-DD.parquet 解析日期；解析不出回 None。"""
    try:
        return date.fromisoformat(f.stem)
    except ValueError:
        return None


def load(
    db_path: Path,
    raw_dir: Path,
    start: date | None = None,
    end: date | None = None,
    rebuild: bool = False,
) -> dict:
    """增量 upsert stock_min。回傳統計。

    預設：只刪掉「本次選到的檔對應的 trade_date」再 INSERT，其餘日期不動
    （逐月載入安全、重跑冪等）。`rebuild=True` 才 DELETE 全表後重灌。
    start/end 皆為 None 時選全部 parquet；有指定則只選檔名日期落在
    [start, end] 區間內的檔（含端點）。
    """
    files = sorted(raw_dir.glob("*.parquet"))
    if start is not None or end is not None:
        files = [
            f for f in files
            if (d := _file_date(f)) is not None
            and (start is None or d >= start)
            and (end is None or d <= end)
        ]
    if not files:
        raise SystemExit(f"找不到符合條件的 parquet：{raw_dir}")
    file_dates = sorted({d for f in files if (d := _file_date(f)) is not None})
    # DuckDB read_parquet 接受檔案路徑 list，避免無法用 glob 表達的日期過濾
    file_list = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(SCHEMA_STOCK_MIN)
        if rebuild:
            conn.execute("DELETE FROM stock_min")
        else:
            # 增量：只清掉本次要載入的那些日期，其餘月份不動
            date_list = "[" + ", ".join(f"DATE '{d}'" for d in file_dates) + "]"
            conn.execute(f"DELETE FROM stock_min WHERE trade_date IN {date_list}")
        conn.execute(
            f"INSERT INTO stock_min ({COLS}) "
            f"SELECT {COLS} FROM read_parquet({file_list})"
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
    p.add_argument("--start", type=date.fromisoformat, default=None,
                   help="只載入 >= 此日期的檔（YYYY-MM-DD）")
    p.add_argument("--end", type=date.fromisoformat, default=None,
                   help="只載入 <= 此日期的檔（YYYY-MM-DD）")
    p.add_argument("--rebuild", action="store_true",
                   help="全表 DELETE 後重灌（預設為只更新本次選到的日期）")
    args = p.parse_args()

    rng = ""
    if args.start or args.end:
        rng = f"（{args.start or '最早'} ~ {args.end or '最晚'}）"
    mode = "全表重建" if args.rebuild else "增量"
    print(f"{mode}載入 {args.raw_dir}/*.parquet{rng} → {args.db} 的 stock_min …")
    st = load(args.db, args.raw_dir, args.start, args.end, args.rebuild)
    print(f"完成：{st['files']} 檔 / {st['days']} 交易日 / {st['rows']:,} rows "
          f"（{st['lo']} ~ {st['hi']}）")


if __name__ == "__main__":
    main()

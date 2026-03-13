#!/usr/bin/env python3
"""
建立並更新 vixtwn 表（台灣 VIX 日資料）

執行順序：
  1. 建表（CREATE TABLE IF NOT EXISTS）
  2. 從 CSV 匯入歷史資料（upsert，冪等）
  3. 從期交所網站抓取最新資料補齊

使用方式：
    uv run python src/etl/build_vixtwn.py
"""
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
CSV_PATH = PROJECT_ROOT / "data" / "external_sources" / "VIXTWN.csv"
VIX_BASE = "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{ym}new.txt"


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vixtwn (
            date  DATE PRIMARY KEY,
            vix   DOUBLE NOT NULL
        )
    """)


def import_csv(conn: duckdb.DuckDBPyConnection) -> int:
    """匯入 CSV 歷史資料，回傳新增/更新筆數。"""
    if not CSV_PATH.exists():
        print(f"  [跳過] CSV 不存在：{CSV_PATH}")
        return 0

    df = pd.read_csv(CSV_PATH, parse_dates=["Date"])
    df = df.rename(columns={"Date": "date", "VIXTWN": "vix"})
    df["date"] = df["date"].dt.date

    before = conn.execute("SELECT COUNT(*) FROM vixtwn").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO vixtwn SELECT date, vix FROM df")
    after = conn.execute("SELECT COUNT(*) FROM vixtwn").fetchone()[0]
    return after - before


def fetch_vix_month(ym: str) -> list[tuple[date, float]]:
    """從期交所下載單月 VIX txt，回傳 [(date, vix), ...]。失敗回傳 []。"""
    url = VIX_BASE.format(ym=ym)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("big5", errors="replace")
    except Exception as e:
        print(f"  [WARN] 下載失敗 {url}: {e}")
        return []

    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        date_str = parts[0].strip()
        if len(date_str) != 8 or not date_str.isdigit():
            continue
        try:
            d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            vix_str = next((p.strip() for p in parts[2:] if p.strip()), "")
            rows.append((d, float(vix_str)))
        except (ValueError, IndexError):
            continue
    return rows


def fetch_and_update(conn: duckdb.DuckDBPyConnection) -> int:
    """從期交所抓取最新資料，只補 DB 最新日期之後的月份，回傳新增筆數。"""
    latest = conn.execute("SELECT MAX(date) FROM vixtwn").fetchone()[0]
    today = date.today()

    # 決定需要抓的月份：從最新日期的當月到今天
    if latest is None:
        start_ym = today.replace(day=1)
    else:
        start_ym = latest.replace(day=1)

    months = []
    cur = start_ym
    while cur <= today.replace(day=1):
        months.append(cur.strftime("%Y%m"))
        # 移到下個月
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    all_rows = []
    for ym in months:
        rows = fetch_vix_month(ym)
        all_rows.extend(rows)

    if not all_rows:
        return 0

    # 只取 latest 之後的資料
    new_rows = [(d, v) for d, v in all_rows if latest is None or d > latest]
    if not new_rows:
        return 0

    df = pd.DataFrame(new_rows, columns=["date", "vix"])
    conn.execute("INSERT OR REPLACE INTO vixtwn SELECT date, vix FROM df")
    return len(new_rows)


def main() -> None:
    print("=" * 50)
    print("build_vixtwn: 建立並更新 vixtwn 表")
    print("=" * 50)

    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)

        # Step 1: CSV 匯入
        print("\n[Step 1] CSV 歷史匯入...")
        added = import_csv(conn)
        total = conn.execute("SELECT COUNT(*) FROM vixtwn").fetchone()[0]
        print(f"  新增/更新：{added} 筆，目前總筆數：{total}")

        # Step 2: HTTP 增量更新
        print("\n[Step 2] 期交所 HTTP 增量更新...")
        new_count = fetch_and_update(conn)
        print(f"  新增：{new_count} 筆")

        # 統計
        row = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM vixtwn"
        ).fetchone()
        print(f"\n  總計 {row[0]} 筆，{row[1]} ~ {row[2]}")

    print("\n完成。")


if __name__ == "__main__":
    main()

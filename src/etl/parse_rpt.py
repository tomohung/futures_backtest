"""
Step 1: 解析 rpt 檔 → ticks 表

掃描 data/raw/ 下各年份子目錄中的 zip 檔，
每個 zip 包含一個同名 .rpt（CSV），
解析後過濾出 TX 台指期資料，寫入 DuckDB ticks 表。

支援增量匯入：已存在的 trade_date 跳過。
"""

import zipfile
import io
import re
from pathlib import Path
from datetime import date

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

COLUMNS = [
    "成交日期", "商品代號", "到期月份(週別)",
    "成交時間", "成交價格", "成交數量(B+S)",
    "近月價格", "遠月價格", "開盤集合競價",
]


def decode_content(content: bytes) -> str:
    for enc in ("utf-8", "big5", "cp950"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("無法解碼檔案內容")


def parse_zip(zip_path: Path) -> pd.DataFrame:
    try:
        zf_ctx = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        # 非交易日：期交所回傳 HTML 而非 zip
        return pd.DataFrame()

    with zf_ctx as zf:
        names = zf.namelist()
        rpt_names = [n for n in names if n.endswith(".rpt")]
        if not rpt_names:
            return pd.DataFrame()
        content = zf.read(rpt_names[0])

    text = decode_content(content)
    df = pd.read_csv(
        io.StringIO(text),
        header=0,
        names=COLUMNS,
        dtype=str,
        skipinitialspace=True,
    )

    # trim 所有字串欄位
    for col in df.columns:
        df[col] = df[col].str.strip()

    # 過濾 TX，排除價差合約（合約代號含 "/"）
    df = df[df["商品代號"] == "TX"].copy()
    df = df[~df["到期月份(週別)"].str.contains("/", na=False)]
    if df.empty:
        return pd.DataFrame()

    # 解析欄位
    df["trade_date"] = pd.to_datetime(df["成交日期"], format="%Y%m%d").dt.date
    df["symbol"] = df["商品代號"]
    df["contract"] = df["到期月份(週別)"]

    # 成交時間：HHMMSS → HH:MM:SS
    df["trade_time"] = df["成交時間"].apply(
        lambda s: f"{s[:2]}:{s[2:4]}:{s[4:6]}" if pd.notna(s) and len(s) == 6 else None
    )

    df["price"] = pd.to_numeric(df["成交價格"], errors="coerce")
    df["volume"] = pd.to_numeric(df["成交數量(B+S)"], errors="coerce").astype("Int64")

    # 開盤集合競價：非空且非 '-' 視為 True
    df["is_auction"] = df["開盤集合競價"].notna() & (df["開盤集合競價"] != "-") & (df["開盤集合競價"] != "")

    result = df[["trade_date", "symbol", "contract", "trade_time", "price", "volume", "is_auction"]].copy()
    result = result.dropna(subset=["price", "trade_time"])
    return result


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            trade_date   DATE,
            symbol       VARCHAR,
            contract     VARCHAR,
            trade_time   TIME,
            price        DECIMAL(10,2),
            volume       INT,
            is_auction   BOOLEAN
        )
    """)


def get_imported_dates(conn: duckdb.DuckDBPyConnection) -> set:
    rows = conn.execute(
        "SELECT DISTINCT trade_date FROM ticks WHERE symbol = 'TX'"
    ).fetchall()
    return {r[0] for r in rows}


def find_all_zips() -> list[Path]:
    zips = sorted(RAW_DIR.glob("**/Daily_*.zip"))
    return zips


def date_from_zip(path: Path) -> date | None:
    m = re.search(r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip", path.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)
        imported_dates = get_imported_dates(conn)

        all_zips = find_all_zips()
        print(f"找到 {len(all_zips)} 個 zip 檔")

        new_rows = 0
        skipped = 0
        processed_dates: list[date] = []

        for zip_path in all_zips:
            file_date = date_from_zip(zip_path)
            if file_date is None:
                continue
            if file_date in imported_dates:
                skipped += 1
                continue

            df = parse_zip(zip_path)
            if df.empty:
                # 非交易日或無 TX 資料，標記已處理（不再重複嘗試）
                # 用一筆 dummy 也不太好，直接跳過即可，下次仍會重試
                continue

            conn.execute("INSERT INTO ticks SELECT * FROM df")
            new_rows += len(df)
            processed_dates.extend(df["trade_date"].unique().tolist())

        # 統計
        stats = conn.execute("""
            SELECT
                SUM(daily_ticks)                 AS total_rows,
                MIN(trade_date)                  AS min_date,
                MAX(trade_date)                  AS max_date,
                COUNT(DISTINCT trade_date)       AS trading_days,
                AVG(daily_ticks)                 AS avg_daily_ticks
            FROM (
                SELECT trade_date, COUNT(*) AS daily_ticks
                FROM ticks
                WHERE symbol = 'TX'
                GROUP BY trade_date
            ) t
        """).fetchone()

        print(f"\n=== ticks 表統計（TX）===")
        print(f"本次新增：{new_rows:,} 筆（跳過 {skipped} 個已匯入日期）")
        print(f"總筆數：  {stats[0]:,}")
        print(f"日期範圍：{stats[1]} ~ {stats[2]}")
        print(f"交易日數：{stats[3]}")
        print(f"每日平均 tick 數：{stats[4]:.0f}")


if __name__ == "__main__":
    main()

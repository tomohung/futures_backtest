"""
Step: 解析選擇權 rpt 檔 → ticks_options 表

掃描 data/raw_options/ 下的 zip 檔，
每個 zip 包含一個同名 .rpt（CSV，Big5 編碼），
解析後過濾出 TXO 台指選擇權資料，寫入 DuckDB ticks_options 表。

支援增量匯入：已存在的 trade_date 跳過。
"""

import argparse
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_options"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

COLUMNS = [
    "成交日期", "商品代號", "履約價格", "到期月份(週別)",
    "買賣權別", "成交時間", "成交價格", "成交數量(B or S)", "開盤集合競價",
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
        return pd.DataFrame()

    with zf_ctx as zf:
        names = zf.namelist()
        rpt_names = [n for n in names if n.endswith(".rpt")]
        if not rpt_names:
            return pd.DataFrame()
        content = zf.read(rpt_names[0])

    text = decode_content(content)

    # Skip separator line (second line with dashes)
    lines = text.split("\n")
    if len(lines) > 1 and lines[1].startswith("---"):
        text = lines[0] + "\n" + "\n".join(lines[2:])

    df = pd.read_csv(
        io.StringIO(text),
        header=0,
        names=COLUMNS,
        dtype=str,
        skipinitialspace=True,
    )

    for col in df.columns:
        df[col] = df[col].str.strip()

    # Filter: TXO only, skip flex contracts (contain "F")
    df = df[df["商品代號"] == "TXO"].copy()
    df = df[~df["到期月份(週別)"].str.contains("F", na=False)]
    if df.empty:
        return pd.DataFrame()

    # Parse columns
    df["trade_date"] = pd.to_datetime(df["成交日期"], format="%Y%m%d").dt.date
    df["symbol"] = "TXO"
    df["strike"] = pd.to_numeric(df["履約價格"], errors="coerce")
    df["contract"] = df["到期月份(週別)"]
    df["put_call"] = df["買賣權別"]

    df["trade_time"] = df["成交時間"].apply(
        lambda s: f"{s[:2]}:{s[2:4]}:{s[4:6]}" if pd.notna(s) and len(s) == 6 else None
    )

    df["price"] = pd.to_numeric(df["成交價格"], errors="coerce")
    df["volume"] = pd.to_numeric(df["成交數量(B or S)"], errors="coerce").astype("Int64")

    df["is_auction"] = (
        df["開盤集合競價"].notna()
        & (df["開盤集合競價"] != "-")
        & (df["開盤集合競價"] != "")
    )

    result = df[[
        "trade_date", "symbol", "strike", "contract", "put_call",
        "trade_time", "price", "volume", "is_auction",
    ]].copy()
    result = result.dropna(subset=["price", "trade_time", "strike"])
    return result


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticks_options (
            trade_date     DATE,
            symbol         VARCHAR,
            strike         DECIMAL(10,2),
            contract       VARCHAR,
            put_call       VARCHAR,
            trade_time     TIME,
            price          DECIMAL(10,2),
            volume         INT,
            is_auction     BOOLEAN
        )
    """)


def get_imported_dates(conn: duckdb.DuckDBPyConnection) -> set:
    rows = conn.execute(
        "SELECT DISTINCT trade_date FROM ticks_options WHERE symbol = 'TXO'"
    ).fetchall()
    return {r[0] for r in rows}


def get_recent_zip_dates(n: int) -> set[date]:
    all_dates = sorted(
        d for p in RAW_DIR.glob("OptionsDaily_*.zip")
        if (d := date_from_zip(p)) is not None
    )
    return set(all_dates[-n:]) if n > 0 and all_dates else set()


def find_all_zips() -> list[Path]:
    return sorted(RAW_DIR.glob("OptionsDaily_*.zip"))


def date_from_zip(path: Path) -> date | None:
    m = re.search(r"OptionsDaily_(\d{4})_(\d{2})_(\d{2})\.zip", path.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="選擇權 zip → ticks_options 表")
    parser.add_argument(
        "--reimport-recent",
        type=int,
        default=2,
        metavar="N",
        help="強制重新匯入磁碟上最新 N 個 zip 日期的資料（先刪後插，預設 2）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)

        # 刪除最近 N 個 zip 日期的 ticks_options，強制重新匯入
        reimport_dates = get_recent_zip_dates(args.reimport_recent)
        if reimport_dates:
            print(f"強制重新匯入最近 {len(reimport_dates)} 個日期：{sorted(reimport_dates)}")
            for d in sorted(reimport_dates):
                count = conn.execute(
                    "SELECT COUNT(*) FROM ticks_options WHERE trade_date = ?", [d]
                ).fetchone()[0]
                if count > 0:
                    conn.execute("DELETE FROM ticks_options WHERE trade_date = ?", [d])
                    print(f"  刪除 {d} 的 {count:,} 筆 ticks_options")

        imported_dates = get_imported_dates(conn)

        all_zips = find_all_zips()
        print(f"找到 {len(all_zips)} 個 options zip 檔")

        new_rows = 0
        skipped = 0

        for zip_path in all_zips:
            file_date = date_from_zip(zip_path)
            if file_date is None:
                continue
            if file_date in imported_dates:
                skipped += 1
                continue

            df = parse_zip(zip_path)
            if df.empty:
                continue

            conn.execute("INSERT INTO ticks_options SELECT * FROM df")
            new_rows += len(df)

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
                FROM ticks_options
                WHERE symbol = 'TXO'
                GROUP BY trade_date
            ) t
        """).fetchone()

        print(f"\n=== ticks_options 表統計（TXO）===")
        print(f"本次新增：{new_rows:,} 筆（跳過 {skipped} 個已匯入日期）")
        if stats[0]:
            print(f"總筆數：  {stats[0]:,}")
            print(f"日期範圍：{stats[1]} ~ {stats[2]}")
            print(f"交易日數：{stats[3]}")
            print(f"每日平均 tick 數：{stats[4]:,.0f}")


if __name__ == "__main__":
    main()

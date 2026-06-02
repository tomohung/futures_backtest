"""
Step 1: 解析 rpt 檔 → ticks 表

掃描 data/raw/ 下各年份子目錄中的 zip 檔，
每個 zip 包含一個同名 .rpt（CSV），
解析後過濾出 TX 台指期資料，寫入 DuckDB ticks 表。

增量匯入以「逐 zip 檔名」追蹤（ingested_zips 表），每個 zip 只處理一次。

為何不以 trade_date 判斷已匯入？
期交所每個 Daily_D.zip 同時含多個 trade_date 的片段，而單一 trade_date 的資料又
拆散在兩個檔：
  - X 的日盤(08:45~13:45) + 凌晨(00:00~05:00) 在 Daily_X
  - X 的晚盤(15:00~23:59) 在 Daily_(X+1)
若以「trade_date 有無資料」判斷跳過，會出兩種錯：
  (1) X 的晚盤先從 Daily_(X+1) 進庫 → X 被視為已匯入 → Daily_X(含日盤)被整個跳過，
      日盤永遠補不到（原始 bug）。
  (2) 颱風假等「有檔但永遠沒日盤」的日期，會被反覆處理 → 夜盤 tick 重複累積。
改以 zip 檔名為單位追蹤，每檔恰好處理一次，可同時避免上述兩者。
只有成功解析出資料的 zip 才記入 ingested_zips；無效/非交易日 stub 不記，
待之後被換成真檔時仍會重試。
"""

import argparse
import zipfile
import io
import re
from pathlib import Path
from datetime import date, timedelta

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingested_zips (
            filename   VARCHAR PRIMARY KEY,
            file_date  DATE,
            n_rows     BIGINT
        )
    """)


def get_ingested_zips(conn: duckdb.DuckDBPyConnection) -> set:
    """回傳已成功匯入的 zip 檔名集合（每個 zip 只處理一次的依據）。"""
    rows = conn.execute("SELECT filename FROM ingested_zips").fetchall()
    return {r[0] for r in rows}


def get_recent_zip_dates(n: int) -> set[date]:
    """Return the N most recent zip dates on disk (candidates for re-import)."""
    all_dates = sorted(
        d for p in RAW_DIR.glob("**/Daily_*.zip")
        if (d := date_from_zip(p)) is not None
    )
    return set(all_dates[-n:]) if n > 0 and all_dates else set()


def find_all_zips() -> list[Path]:
    """回傳所有 zip 路徑，並以「檔名」去重。

    年界檔（如 Daily_2025_12_31.zip）可能同時出現在相鄰兩個年份子目錄，
    內容相同。以檔名去重，確保每個 zip 只被處理一次（避免重複插入 ticks，
    也避免 ingested_zips 的主鍵衝突）。
    """
    seen: dict[str, Path] = {}
    for p in sorted(RAW_DIR.glob("**/Daily_*.zip")):
        seen.setdefault(p.name, p)
    return list(seen.values())


def date_from_zip(path: Path) -> date | None:
    m = re.search(r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip", path.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 1: zip → ticks 表")
    parser.add_argument(
        "--reimport-recent",
        type=int,
        default=2,
        metavar="N",
        help="重新匯入磁碟上最新 N 個 zip 的資料（含跨檔的晚盤，先刪後插，預設 2）",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="清空 ticks 與 ingested_zips，從所有 zip 全量重建（修復歷史重複/缺漏）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)

        if args.rebuild:
            print("全量重建：清空 ticks 與 ingested_zips")
            conn.execute("DELETE FROM ticks")
            conn.execute("DELETE FROM ingested_zips")
        elif args.reimport_recent > 0:
            # 重新匯入最新 N 個 zip。trade_date X 的晚盤(15:00+)落在 Daily_(X+1)，
            # 故除了刪 trade_date >= K，還要刪 K-1 的晚盤（它在 Daily_K 內），
            # 才能在重處理 Daily_K 時乾淨還原、不重複。
            recent = sorted(get_recent_zip_dates(args.reimport_recent))
            if recent:
                k = recent[0]
                ndel = conn.execute(
                    "SELECT COUNT(*) FROM ticks "
                    "WHERE trade_date >= ? OR (trade_date = ? AND trade_time >= TIME '15:00:00')",
                    [k, k - timedelta(days=1)],
                ).fetchone()[0]
                conn.execute(
                    "DELETE FROM ticks "
                    "WHERE trade_date >= ? OR (trade_date = ? AND trade_time >= TIME '15:00:00')",
                    [k, k - timedelta(days=1)],
                )
                conn.execute("DELETE FROM ingested_zips WHERE file_date >= ?", [k])
                print(f"重新匯入最新 {args.reimport_recent} 個 zip：刪除 trade_date >= {k} 的 {ndel:,} 筆")

        ingested = get_ingested_zips(conn)

        all_zips = find_all_zips()
        # 已匯入者（在 ingested）不再 parse，只有待匯入清單會真的開檔解析。
        to_process = [
            p for p in all_zips
            if date_from_zip(p) is not None and p.name not in ingested
        ]
        skipped = len(all_zips) - len(to_process)
        print(
            f"找到 {len(all_zips)} 個 zip 檔，待匯入 {len(to_process)} 個"
            f"（跳過 {skipped} 個已處理）",
            flush=True,
        )

        new_rows = 0
        parsed = 0

        for i, zip_path in enumerate(to_process, 1):
            file_date = date_from_zip(zip_path)
            df = parse_zip(zip_path)
            if df.empty:
                # 無效 zip / 非交易日 stub：不記入 ingested_zips，
                # 之後若被換成真檔仍會重試。
                continue

            conn.execute("INSERT INTO ticks SELECT * FROM df")
            conn.execute(
                "INSERT OR IGNORE INTO ingested_zips VALUES (?, ?, ?)",
                [zip_path.name, file_date, len(df)],
            )
            new_rows += len(df)
            parsed += 1
            # 每 50 檔（或最後一檔）回報一次，避免長時間無輸出像當機；
            # flush 讓 subprocess（morning_briefing）管線下的 stdout 即時顯示。
            if parsed % 50 == 0 or i == len(to_process):
                print(
                    f"  匯入進度 {i}/{len(to_process)}"
                    f"（最新 {file_date}，累計 {new_rows:,} 列）",
                    flush=True,
                )

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
        print(f"本次新增：{new_rows:,} 筆（跳過 {skipped} 個已處理 zip）")
        print(f"總筆數：  {stats[0]:,}")
        print(f"日期範圍：{stats[1]} ~ {stats[2]}")
        print(f"交易日數：{stats[3]}")
        print(f"每日平均 tick 數：{stats[4]:.0f}")


if __name__ == "__main__":
    main()

"""
Parse 國發會景氣指標 ZIP（內含 11 個 CSV）→ DuckDB table `econ_signal`。

只解析「景氣指標與燈號.csv」（CSV 內的 11 個檔案中最關鍵的彙總檔）。

ZIP 內檔名是 big5 編碼（zipfile 預設用 cp437 解析會錯），因此用 raw bytes 對照。

冪等：重跑會覆蓋同月份資料，並更新 snapshot_date。

用法：
  uv run python src/etl/parse_econ.py                      # parse 最新 snapshot
  uv run python src/etl/parse_econ.py --zip path/to/.zip   # parse 指定 zip
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_econ"
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

TARGET_FILENAME_BIG5 = "景氣指標與燈號.csv"

SCHEMA_ECON = """
CREATE TABLE IF NOT EXISTS econ_signal (
    report_month       DATE PRIMARY KEY,    -- YYYY-MM-01
    leading_idx        DECIMAL(12,6),
    leading_idx_nt     DECIMAL(12,6),
    coincident_idx     DECIMAL(12,6),
    coincident_idx_nt  DECIMAL(12,6),
    lagging_idx        DECIMAL(12,6),
    lagging_idx_nt     DECIMAL(12,6),
    score              INTEGER,             -- 1982-2003 早期月份為 NULL
    signal_color       VARCHAR,             -- 紅/黃紅/綠/黃藍/藍 / NULL
    snapshot_date      DATE                 -- 此資料是哪一次 snapshot 取得
);
"""


def _to_float(s: str) -> float | None:
    s = (s or "").strip()
    if not s or s in {"-", "--"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> int | None:
    s = (s or "").strip()
    if not s or s in {"-", "--"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _decode_member_name(info: zipfile.ZipInfo) -> str:
    """處理 ZIP 內檔名編碼。

    ZIP 規範：general purpose flag bit 11 = 1 表示檔名為 UTF-8。
    NDC 新版 ZIP 已啟用此 flag → 直接用 info.filename。
    舊版（未啟用）會走 zipfile 的 cp437 解碼路徑 → 需 cp437→big5 復原。
    """
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("big5")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename


def _date_from_filename(p: Path) -> date | None:
    m = re.search(r"_(\d{4})-(\d{2})-(\d{2})\.zip$", p.name)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def find_latest_zip() -> Path:
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"{RAW_DIR} 不存在，先跑 download_econ.py")
    zips = sorted(RAW_DIR.glob("eco_indicators_*.zip"))
    if not zips:
        raise FileNotFoundError(f"{RAW_DIR} 內無 eco_indicators_*.zip")
    return zips[-1]


def extract_target_csv(zip_path: Path) -> bytes:
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = _decode_member_name(info)
            if name == TARGET_FILENAME_BIG5:
                return z.read(info)
    raise FileNotFoundError(f"{TARGET_FILENAME_BIG5} 不在 {zip_path} 內")


def parse_csv(data: bytes, snapshot_date: date) -> list[dict]:
    """
    CSV 欄位（含 BOM）：
    Date, 領先指標綜合指數, 領先指標不含趨勢指數,
    同時指標綜合指數, 同時指標不含趨勢指數,
    落後指標綜合指數, 落後指標不含趨勢指數,
    景氣對策信號綜合分數, 景氣對策信號

    Date 格式：YYYYMM
    """
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    expected = ["Date", "領先指標綜合指數", "領先指標不含趨勢指數",
                "同時指標綜合指數", "同時指標不含趨勢指數",
                "落後指標綜合指數", "落後指標不含趨勢指數",
                "景氣對策信號綜合分數", "景氣對策信號"]
    if header != expected:
        raise ValueError(f"CSV header 不符預期：{header}")

    rows: list[dict] = []
    for raw in reader:
        if len(raw) != 9:
            continue
        date_str = raw[0].strip()
        if not re.fullmatch(r"\d{6}", date_str):
            continue
        year, month = int(date_str[:4]), int(date_str[4:6])
        report_month = date(year, month, 1)

        rows.append({
            "report_month": report_month,
            "leading_idx": _to_float(raw[1]),
            "leading_idx_nt": _to_float(raw[2]),
            "coincident_idx": _to_float(raw[3]),
            "coincident_idx_nt": _to_float(raw[4]),
            "lagging_idx": _to_float(raw[5]),
            "lagging_idx_nt": _to_float(raw[6]),
            "score": _to_int(raw[7]),
            "signal_color": raw[8].strip() or None,
            "snapshot_date": snapshot_date,
        })
    return rows


def write_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        "DELETE FROM econ_signal WHERE report_month = ?",
        [(r["report_month"],) for r in rows],
    )
    cols = ["report_month", "leading_idx", "leading_idx_nt",
            "coincident_idx", "coincident_idx_nt",
            "lagging_idx", "lagging_idx_nt",
            "score", "signal_color", "snapshot_date"]
    placeholders = ", ".join(["?"] * len(cols))
    conn.executemany(
        f"INSERT INTO econ_signal ({', '.join(cols)}) VALUES ({placeholders})",
        [tuple(r[c] for c in cols) for r in rows],
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Parse NDC econ ZIP into DuckDB")
    p.add_argument("--zip", help="指定 ZIP 路徑（預設用最新 snapshot）")
    args = p.parse_args()

    zip_path = Path(args.zip) if args.zip else find_latest_zip()
    snapshot = _date_from_filename(zip_path) or date.today()
    print(f"Parsing {zip_path.name} (snapshot_date={snapshot})")

    csv_bytes = extract_target_csv(zip_path)
    rows = parse_csv(csv_bytes, snapshot)
    print(f"  {len(rows)} rows from {rows[0]['report_month']} ~ {rows[-1]['report_month']}")

    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(SCHEMA_ECON)
        write_rows(conn, rows)
        n = conn.execute("SELECT COUNT(*) FROM econ_signal").fetchone()[0]
        latest = conn.execute("""
            SELECT report_month, score, signal_color
            FROM econ_signal
            WHERE score IS NOT NULL
            ORDER BY report_month DESC LIMIT 1
        """).fetchone()
    print(f"DB now has: econ_signal={n}, latest with score={latest}")


if __name__ == "__main__":
    main()

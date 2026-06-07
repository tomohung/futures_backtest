"""
下載全市場（上市+上櫃）個股分 k（FinMind TaiwanStockKBar）→ DuckDB table `stock_min`。

逐交易日：宇宙取自 stock_day 當日 symbols（含已下市公司，避免 survivorship bias）。
以「日」為冪等單位 DELETE+INSERT；stock_min_progress 記錄完成狀態，可中斷續傳。

dataset TaiwanStockKBar 為 Sponsor 限定，token 取自 env FINMIND_API_KEY。
一個 request = 一檔一天（不接受 end_date）；用官方 SDK use_async 批多檔。

用法：
  uv run python src/etl/download_stock_min.py                       # 預設 2021-01-01 至今
  uv run python src/etl/download_stock_min.py --start 2024-01-01 --end 2024-12-31
  uv run python src/etl/download_stock_min.py --market TWSE          # 只抓上市
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

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

SCHEMA_PROGRESS = """
CREATE TABLE IF NOT EXISTS stock_min_progress (
    trade_date   DATE PRIMARY KEY,
    expected     INTEGER,
    fetched      INTEGER,
    failed       INTEGER,
    n_rows       BIGINT,
    status       VARCHAR,
    fetched_at   TIMESTAMP
);
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_STOCK_MIN)
    conn.execute(SCHEMA_PROGRESS)


def trading_days(
    conn: duckdb.DuckDBPyConnection, start: date, end: date
) -> list[date]:
    """區間內 stock_day 出現過的交易日（升冪）。"""
    rows = conn.execute(
        """
        SELECT DISTINCT trade_date
        FROM stock_day
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        [start, end],
    ).fetchall()
    return [r[0] for r in rows]


def universe_for_day(
    conn: duckdb.DuckDBPyConnection, d: date, market: str | None = None
) -> list[str]:
    """當日 stock_day 有成交的 symbols（升冪）。market=None 取全市場。"""
    sql = "SELECT DISTINCT symbol FROM stock_day WHERE trade_date = ?"
    params: list = [d]
    if market:
        sql += " AND market = ?"
        params.append(market)
    sql += " ORDER BY symbol"
    return [r[0] for r in conn.execute(sql, params).fetchall()]


STOCK_MIN_COLS = ["trade_date", "stock_id", "minute",
                  "open", "high", "low", "close", "volume"]


def normalize_kbar(df: pd.DataFrame, d: date) -> pd.DataFrame:
    """FinMind kbar df → stock_min 欄序/型別。空 df 回傳空但欄位齊全。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=STOCK_MIN_COLS)
    out = df.copy()
    out["trade_date"] = d
    out["minute"] = pd.to_datetime(out["minute"], format="%H:%M:%S").dt.time
    out["stock_id"] = out["stock_id"].astype(str)
    out["volume"] = out["volume"].fillna(0).astype("int64")
    # FinMind 舊資料（如 2021 的 ETF）偶有同一分鐘重複 print（OHLC 同、volume 微差），
    # 會違反 stock_min 的 PK。對 PK 去重，保留後到的 final print。
    out = out.drop_duplicates(subset=["trade_date", "stock_id", "minute"], keep="last")
    return out[STOCK_MIN_COLS].reset_index(drop=True)


def write_day(conn: duckdb.DuckDBPyConnection, d: date, df: pd.DataFrame) -> int:
    """以日為單位刪舊寫新（冪等）。回傳寫入 row 數。"""
    conn.execute("DELETE FROM stock_min WHERE trade_date = ?", [d])
    if len(df):
        conn.execute(
            f"INSERT INTO stock_min SELECT {', '.join(STOCK_MIN_COLS)} FROM df"
        )
    return len(df)


def record_progress(
    conn: duckdb.DuckDBPyConnection,
    d: date,
    expected: int,
    fetched: int,
    failed: int,
    n_rows: int,
    status: str,
) -> None:
    """ledger upsert（同日覆蓋）。"""
    conn.execute("DELETE FROM stock_min_progress WHERE trade_date = ?", [d])
    conn.execute(
        """
        INSERT INTO stock_min_progress
        (trade_date, expected, fetched, failed, n_rows, status, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, now())
        """,
        [d, expected, fetched, failed, n_rows, status],
    )


def pending_days(
    conn: duckdb.DuckDBPyConnection, days: list[date]
) -> list[date]:
    """過濾掉 ledger 已 status='complete' 的日；其餘（缺/partial）保留。"""
    done = {
        r[0]
        for r in conn.execute(
            "SELECT trade_date FROM stock_min_progress WHERE status = 'complete'"
        ).fetchall()
    }
    return [d for d in days if d not in done]


def _kbar_call(stock_id_list: list[str], date_str: str, use_async: bool) -> pd.DataFrame:
    """薄包 FinMind SDK。隔離成單一接縫供測試 monkeypatch。"""
    from FinMind.data import DataLoader

    token = os.environ["FINMIND_API_KEY"]
    dl = DataLoader()
    dl.login_by_token(api_token=token)
    return dl.taiwan_stock_kbar(
        stock_id_list=stock_id_list, date=date_str, use_async=use_async
    )


def fetch_kbar_day(
    stock_ids: list[str],
    d: str,
    max_retries: int = 4,
) -> pd.DataFrame:
    """抓單日全宇宙分 k；rate-limit/連線錯誤指數退避重試。最終失敗則 raise。"""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _kbar_call(stock_ids, d, use_async=True)
        except Exception as e:  # noqa: BLE001 — 退避重試所有暫態錯誤
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1,2,4,8...秒
    raise RuntimeError(f"fetch_kbar_day {d} 重試 {max_retries} 次仍失敗: {last_err}")


def download_day(
    conn: duckdb.DuckDBPyConnection,
    d: date,
    market: str | None = None,
) -> tuple[int, int]:
    """抓單日 → normalize → 寫入 → 記 ledger。回傳 (fetched, expected)。

    只有「全數取得」才記 complete；fetched<expected 一律記 partial 保留待重抓
    （fetched==0 多半是撞 FinMind rate limit，SDK 會吞錯回空 df 而不 raise）。
    """
    univ = universe_for_day(conn, d, market)
    expected = len(univ)
    if expected == 0:
        record_progress(conn, d, 0, 0, 0, 0, "complete")
        return 0, 0
    try:
        raw = fetch_kbar_day(univ, d.isoformat())
    except Exception as e:  # noqa: BLE001
        print(f"  {d} 抓取失敗，記 partial：{e}", flush=True)
        record_progress(conn, d, expected, 0, expected, 0, "partial")
        return 0, expected
    norm = normalize_kbar(raw, d)
    fetched = norm["stock_id"].nunique() if len(norm) else 0
    n_rows = write_day(conn, d, norm)
    if fetched < expected:
        record_progress(conn, d, expected, fetched, expected - fetched, n_rows, "partial")
        warn = " ⚠ 可能撞 rate limit" if fetched == 0 else ""
        print(f"  {d}: 宇宙{expected} 取得{fetched} rows={n_rows} → partial{warn}", flush=True)
        return fetched, expected
    record_progress(conn, d, expected, fetched, 0, n_rows, "complete")
    print(f"  {d}: 宇宙{expected} 取得{fetched} rows={n_rows}", flush=True)
    return fetched, expected


# FinMind Sponsor 限額 = 6000 requests/小時（一個 request = 一檔一天）。
# 留 margin，自我節流到 RATE_PER_HOUR；超量則等最舊請求滿一小時釋出。
RATE_PER_HOUR = 5500
_window: list[tuple[float, int]] = []  # (timestamp, request_count)


def _throttle(need: int, limit: int = RATE_PER_HOUR) -> None:
    """滑動視窗節流：確保任一小時內發出的 request 數 ≤ limit。"""
    now = time.time()
    while _window and now - _window[0][0] > 3600:
        _window.pop(0)
    used = sum(c for _, c in _window)
    while _window and used + need > limit:
        wait = 3600 - (now - _window[0][0]) + 1
        print(f"  ⏳ rate-limit 保護：本小時已用 {used}/{limit}，本日需 {need}，"
              f"等 {wait/60:.0f} 分鐘釋出…", flush=True)
        time.sleep(min(wait, 300))
        now = time.time()
        while _window and now - _window[0][0] > 3600:
            _window.pop(0)
        used = sum(c for _, c in _window)
    _window.append((now, need))


def _quota_available(market: str | None) -> bool:
    """探一筆已知有資料的 stock-day，確認 FinMind quota 尚未耗盡（非空回傳）。"""
    try:
        df = fetch_kbar_day(["2330"], "2026-05-29")
        return df is not None and len(df) > 0
    except Exception:
        return False


def main() -> None:
    p = argparse.ArgumentParser(description="下載全市場個股分 k（FinMind TaiwanStockKBar）")
    p.add_argument("--start", type=date.fromisoformat, default=date(2021, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    p.add_argument("--market", choices=["TWSE", "TPEX"], default=None,
                   help="預設全市場；指定則只抓單一市場")
    args = p.parse_args()

    token = os.environ.get("FINMIND_API_KEY")
    if not token:
        raise SystemExit("缺 env FINMIND_API_KEY")

    with duckdb.connect(str(DB_PATH)) as conn:
        ensure_schema(conn)
        all_days = trading_days(conn, args.start, args.end)
        todo = pending_days(conn, all_days)
        print(f"交易日 {len(all_days)}，待下載 {len(todo)}（已完成 {len(all_days)-len(todo)} 跳過）",
              flush=True)
        # 啟動 gate：若 quota 仍耗盡（探測秒回空），等到釋出再開跑，避免整批標 partial
        while todo and not _quota_available(args.market):
            print("  ⏳ FinMind quota 目前耗盡（探測回空），等 10 分鐘後重試…", flush=True)
            time.sleep(600)
        for i, d in enumerate(todo, 1):
            need = len(universe_for_day(conn, d, args.market))
            _throttle(need)
            print(f"[{i}/{len(todo)}] {d}", flush=True)
            download_day(conn, d, args.market)


if __name__ == "__main__":
    main()

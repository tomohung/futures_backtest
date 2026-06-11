"""
輔助期貨 1 分 K：從 raw zip 直抽白名單商品（預設 NYF=0050ETF期）→ 日盤 1 分 K
→ 落地 aux_futures_1m 表。供 chart-ui 盤前延伸力多（0050期）副圖復盤用。

為何不讀 ticks 表？
  ticks 只存 TX（parse_rpt.py:82 過濾），NYF/CDF 等被丟掉。故這裡直接解析 raw zip。

範圍：只做**日盤 08:45~13:45**（個股/ETF 期當沖關注日盤；日盤完整落在當日 Daily_X.zip）。
冪等：以 (trade_date, symbol) 為單位，已在 aux_futures_1m 的日期直接跳過。

用法：
  uv run python src/etl/build_aux_futures.py                       # NYF，全部未處理日
  uv run python src/etl/build_aux_futures.py --symbols NYF CDF QFF # 多商品
  uv run python src/etl/build_aux_futures.py --start 2026-01-01    # 限定區間
  uv run python src/etl/build_aux_futures.py --rebuild             # 清表重建
"""

import argparse
import io
import zipfile
from datetime import date

import duckdb
import pandas as pd

from src.etl.build_1m import _aggregate_ticks, build_minute_index
from src.etl.parse_rpt import (
    COLUMNS,
    DB_PATH,
    decode_content,
    date_from_zip,
    find_all_zips,
)

DEFAULT_SYMBOLS = ["NYF"]  # 0050 ETF 期貨（台灣50 指數本體）


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aux_futures_1m (
            timestamp   TIMESTAMP,
            symbol      VARCHAR,
            contract    VARCHAR,
            open        DECIMAL(10,2),
            high        DECIMAL(10,2),
            low         DECIMAL(10,2),
            close       DECIMAL(10,2),
            volume      INT,
            tick_count  INT
        )
    """)


def _done_keys(conn: duckdb.DuckDBPyConnection) -> set[tuple[date, str]]:
    """已落地的 (日期, 商品) 組合 — 冪等跳過依據。"""
    rows = conn.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE), symbol FROM aux_futures_1m"
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def parse_zip_symbols(zip_path, symbols: set[str]) -> pd.DataFrame:
    """解析一個 raw zip，回傳白名單商品的日盤 tick（含 contract）。"""
    try:
        zf_ctx = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        return pd.DataFrame()  # 非交易日 HTML stub
    with zf_ctx as zf:
        rpt_names = [n for n in zf.namelist() if n.endswith((".rpt", ".csv"))]
        if not rpt_names:
            return pd.DataFrame()
        content = zf.read(rpt_names[0])

    df = pd.read_csv(io.StringIO(decode_content(content)), header=0,
                     names=COLUMNS, dtype=str, skipinitialspace=True)
    for col in df.columns:
        df[col] = df[col].str.strip()

    df = df[df["商品代號"].isin(symbols)].copy()
    df = df[~df["到期月份(週別)"].str.contains("/", na=False)]   # 排除價差合約
    if df.empty:
        return pd.DataFrame()

    df["trade_date"] = pd.to_datetime(df["成交日期"], format="%Y%m%d").dt.date
    df["symbol"] = df["商品代號"]
    df["contract"] = df["到期月份(週別)"]
    df["trade_time"] = df["成交時間"].apply(
        lambda s: f"{s[:2]}:{s[2:4]}:{s[4:6]}" if pd.notna(s) and len(s) == 6 else None)
    df["price"] = pd.to_numeric(df["成交價格"], errors="coerce")
    df["volume"] = pd.to_numeric(df["成交數量(B+S)"], errors="coerce")
    df = df.dropna(subset=["price", "trade_time", "volume"])
    # 只留日盤
    df = df[(df["trade_time"] >= "08:45:00") & (df["trade_time"] <= "13:45:00")]
    return df[["trade_date", "symbol", "contract", "trade_time", "price", "volume"]]


def build_symbol_day(day_ticks: pd.DataFrame, trade_date: date, symbol: str) -> pd.DataFrame:
    """單一 (日期, 商品) 的日盤 1 分 K（取當日成交量最大的合約）。"""
    t = day_ticks[day_ticks["symbol"] == symbol]
    if t.empty:
        return pd.DataFrame()
    dominant = t.groupby("contract")["volume"].sum().idxmax()
    t = t[t["contract"] == dominant].copy()
    t["ts"] = pd.to_datetime(
        trade_date.strftime("%Y-%m-%d") + " " + t["trade_time"].astype(str)
    ).dt.floor("1min")

    ohlcv = _aggregate_ticks(t, build_minute_index(trade_date))
    if ohlcv.empty:
        return pd.DataFrame()
    ohlcv = ohlcv.reset_index().rename(columns={"index": "timestamp"})
    ohlcv["symbol"] = symbol
    ohlcv["contract"] = dominant
    ohlcv["volume"] = ohlcv["volume"].astype(int)
    ohlcv["tick_count"] = ohlcv["tick_count"].astype(int)
    return ohlcv[["timestamp", "symbol", "contract", "open", "high", "low",
                  "close", "volume", "tick_count"]]


def main() -> None:
    p = argparse.ArgumentParser(description="raw zip → aux_futures_1m（NYF 等）")
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                   help="商品代號白名單（預設 NYF）")
    p.add_argument("--start", type=date.fromisoformat, default=None)
    p.add_argument("--end", type=date.fromisoformat, default=None)
    p.add_argument("--rebuild", action="store_true", help="清表重建")
    args = p.parse_args()
    symbols = set(args.symbols)

    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)
        if args.rebuild:
            print("清表重建 aux_futures_1m")
            conn.execute("DELETE FROM aux_futures_1m")

        done = set() if args.rebuild else _done_keys(conn)

        zips = []
        for zp in find_all_zips():
            d = date_from_zip(zp)
            if d is None:
                continue
            if args.start and d < args.start:
                continue
            if args.end and d > args.end:
                continue
            # 若所有目標商品該日皆已處理，整個 zip 跳過
            if all((d, s) in done for s in symbols):
                continue
            zips.append((d, zp))
        zips.sort()
        print(f"待處理 {len(zips)} 個 zip（商品 {sorted(symbols)}）")

        new_bars = 0
        for i, (d, zp) in enumerate(zips, 1):
            ticks = parse_zip_symbols(zp, symbols)
            if ticks.empty:
                continue
            for sym in symbols:
                if (d, sym) in done:
                    continue
                day = ticks[ticks["trade_date"] == d]
                bars = build_symbol_day(day, d, sym)
                if bars.empty:
                    continue
                conn.execute("INSERT INTO aux_futures_1m SELECT * FROM bars")
                new_bars += len(bars)
            if i % 50 == 0 or i == len(zips):
                print(f"  進度 {i}/{len(zips)}（最新 {d}，累計 {new_bars:,} 根）", flush=True)

        stats = conn.execute("""
            SELECT symbol, COUNT(DISTINCT CAST(timestamp AS DATE)) AS days,
                   COUNT(*) AS bars, MIN(timestamp) AS lo, MAX(timestamp) AS hi
            FROM aux_futures_1m GROUP BY symbol ORDER BY symbol
        """).fetchall()
        print(f"\n=== aux_futures_1m 統計 ===  本次新增 {new_bars:,} 根")
        for s in stats:
            print(f"  {s[0]}: {s[1]} 交易日 / {s[2]:,} 根 / {s[3]} ~ {s[4]}")


if __name__ == "__main__":
    main()

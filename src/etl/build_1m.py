"""
Step 2: ticks → ohlcv_1m

從 ticks 表合成 1 分 K，包含日盤與夜盤。
- 日盤：08:45~13:45（301 根）
- 夜盤：15:00（前一交易日）~ 次日曆日 05:00（841 根）
- 有成交的分鐘：OHLCV 從 tick 算出
- 無成交的分鐘：用前一分鐘 close 填充 OHLC，volume=0，tick_count=0
- 支援增量：已存在的日期跳過
"""

from pathlib import Path
from datetime import time, timedelta, date, datetime

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

DAY_SESSION_START = time(8, 45)
DAY_SESSION_END = time(13, 45)


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv_1m (
            timestamp       TIMESTAMP,
            symbol          VARCHAR,
            contract        VARCHAR,
            open            DECIMAL(10,2),
            high            DECIMAL(10,2),
            low             DECIMAL(10,2),
            close           DECIMAL(10,2),
            volume          INT,
            tick_count      INT,
            is_rollover     BOOLEAN,
            adjustment      DECIMAL(10,2),
            adj_close       DECIMAL(10,2)
        )
    """)


def get_processed_dates(conn: duckdb.DuckDBPyConnection) -> set:
    """Return dates that already have day session bars (08:45~13:45) in ohlcv_1m."""
    rows = conn.execute("""
        SELECT DISTINCT timestamp::date FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    """).fetchall()
    return {r[0] for r in rows}


def get_processed_night_sessions(conn: duckdb.DuckDBPyConnection) -> set:
    """Return set of dates that already have night session bars (15:00+) in ohlcv_1m."""
    rows = conn.execute("""
        SELECT DISTINCT CAST(timestamp AS DATE)
        FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS TIME) >= TIME '15:00:00'
    """).fetchall()
    return {r[0] for r in rows}


def get_day_contract(conn: duckdb.DuckDBPyConnection, trade_date: date) -> str | None:
    """Get the dominant contract used for the day session of trade_date."""
    r = conn.execute("""
        SELECT contract FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS DATE) = ?
          AND CAST(timestamp AS TIME) = TIME '08:45:00'
        LIMIT 1
    """, [trade_date]).fetchone()
    return r[0] if r else None


def build_minute_index(trade_date: date) -> pd.DatetimeIndex:
    """產生日盤 08:45 ~ 13:45 的每分鐘時間戳（共 301 根）"""
    start = pd.Timestamp(trade_date) + pd.Timedelta(hours=8, minutes=45)
    end   = pd.Timestamp(trade_date) + pd.Timedelta(hours=13, minutes=45)
    return pd.date_range(start, end, freq="1min")


def build_minute_index_night(prev_date: date) -> pd.DatetimeIndex:
    """產生夜盤 15:00（prev_date）~ 次日曆日 05:00 的每分鐘時間戳（共 841 根）"""
    start = pd.Timestamp(prev_date) + pd.Timedelta(hours=15)
    end   = pd.Timestamp(prev_date + timedelta(days=1)) + pd.Timedelta(hours=5)
    return pd.date_range(start, end, freq="1min")


def _aggregate_ticks(ticks: pd.DataFrame, full_idx: pd.DatetimeIndex) -> pd.DataFrame:
    """共用邏輯：tick → 1 分 K，填充空白分鐘。"""
    agg = ticks.groupby("ts").agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("volume", "sum"),
        tick_count=("price", "count"),
    )

    ohlcv = agg.reindex(full_idx)

    real_bars = ohlcv["close"].notna().sum()
    if real_bars == 0:
        return pd.DataFrame()
    if real_bars / len(full_idx) < 0.1:
        return pd.DataFrame()

    ohlcv["close"] = ohlcv["close"].ffill()
    ohlcv["close"] = ohlcv["close"].bfill()

    mask_empty = ohlcv["open"].isna()
    ohlcv.loc[mask_empty, "open"]       = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "high"]       = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "low"]        = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "volume"]     = 0
    ohlcv.loc[mask_empty, "tick_count"] = 0

    return ohlcv


def _finalize(ohlcv: pd.DataFrame, contract: str) -> pd.DataFrame:
    ohlcv = ohlcv.reset_index().rename(columns={"index": "timestamp"})
    ohlcv["symbol"]      = "TX"
    ohlcv["contract"]    = contract
    ohlcv["is_rollover"] = False
    ohlcv["adjustment"]  = 0.0
    ohlcv["adj_close"]   = ohlcv["close"]
    ohlcv["volume"]      = ohlcv["volume"].astype(int)
    ohlcv["tick_count"]  = ohlcv["tick_count"].astype(int)
    cols = [
        "timestamp", "symbol", "contract",
        "open", "high", "low", "close",
        "volume", "tick_count",
        "is_rollover", "adjustment", "adj_close",
    ]
    return ohlcv[cols]


def build_1m_for_date(
    conn: duckdb.DuckDBPyConnection,
    trade_date: date,
) -> pd.DataFrame:
    """日盤 08:45~13:45 的 1 分 K。"""
    ticks = conn.execute("""
        SELECT trade_time, price, volume, contract
        FROM ticks
        WHERE symbol = 'TX'
          AND trade_date = ?
          AND trade_time >= '08:45:00'
          AND trade_time <= '13:45:00'
        ORDER BY contract, trade_time
    """, [trade_date]).df()

    if ticks.empty:
        return pd.DataFrame()

    dominant_contract = ticks.groupby("contract")["volume"].sum().idxmax()
    ticks = ticks[ticks["contract"] == dominant_contract].copy()
    ticks["ts"] = pd.to_datetime(
        trade_date.strftime("%Y-%m-%d") + " " + ticks["trade_time"].astype(str)
    ).dt.floor("1min")

    ohlcv = _aggregate_ticks(ticks, build_minute_index(trade_date))
    if ohlcv.empty:
        return pd.DataFrame()
    return _finalize(ohlcv, dominant_contract)


def build_1m_night_for_session(
    conn: duckdb.DuckDBPyConnection,
    prev_date: date,
    contract: str,
) -> pd.DataFrame:
    """夜盤 1 分 K：prev_date 15:00 ~ (prev_date+1) 05:00。

    夜盤 ticks 分散在兩個 trade_date：
    - prev_date 15:00~23:59 → trade_date = prev_date
    - next calendar day 00:00~05:00 → trade_date = prev_date + 1
    """
    next_cal_date = prev_date + timedelta(days=1)

    ticks_eve = conn.execute("""
        SELECT trade_time, price, volume
        FROM ticks
        WHERE symbol = 'TX' AND trade_date = ? AND contract = ?
          AND trade_time >= '15:00:00'
    """, [prev_date, contract]).df()

    ticks_morn = conn.execute("""
        SELECT trade_time, price, volume
        FROM ticks
        WHERE symbol = 'TX' AND trade_date = ? AND contract = ?
          AND trade_time < '05:00:00'
    """, [next_cal_date, contract]).df()

    if ticks_eve.empty and ticks_morn.empty:
        return pd.DataFrame()

    parts = []
    if not ticks_eve.empty:
        ticks_eve["ts"] = pd.to_datetime(
            str(prev_date) + " " + ticks_eve["trade_time"].astype(str)
        ).dt.floor("1min")
        parts.append(ticks_eve)
    if not ticks_morn.empty:
        ticks_morn["ts"] = pd.to_datetime(
            str(next_cal_date) + " " + ticks_morn["trade_time"].astype(str)
        ).dt.floor("1min")
        parts.append(ticks_morn)

    ticks_all = pd.concat(parts)

    ohlcv = _aggregate_ticks(ticks_all, build_minute_index_night(prev_date))
    if ohlcv.empty:
        return pd.DataFrame()
    return _finalize(ohlcv, contract)


def main() -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)
        processed_dates = get_processed_dates(conn)

        # 只取有日盤 ticks（08:45–13:45）的日期，避免夜盤的跨日後半段
        # （00:00–05:00 的 ticks 其 trade_date 為隔日，若隔日為非交易日
        # 則該日期不應被視為需要建日盤的交易日）
        all_dates = conn.execute("""
            SELECT DISTINCT trade_date FROM ticks
            WHERE symbol = 'TX'
              AND trade_time BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY trade_date
        """).fetchall()
        all_dates = [r[0] for r in all_dates]

        # --- 日盤 ---
        pending_day = [d for d in all_dates if d not in processed_dates]
        print(f"ticks 共 {len(all_dates)} 個日期，日盤待處理 {len(pending_day)} 個")

        new_day_bars = 0
        for trade_date in pending_day:
            df = build_1m_for_date(conn, trade_date)
            if df.empty:
                continue
            conn.execute("INSERT INTO ohlcv_1m SELECT * FROM df")
            new_day_bars += len(df)

        # --- 夜盤 ---
        # 夜盤結束時間：prev_date + 1 日 05:00
        # 若現在已超過該時間，最後一個交易日的夜盤視為完成，納入處理
        day_dates = sorted(get_processed_dates(conn))
        processed_night = get_processed_night_sessions(conn)
        now = datetime.now()

        # 也包含有夜盤 ticks 但沒有日盤的日期（假日夜盤）
        night_tick_dates = {r[0] for r in conn.execute("""
            SELECT DISTINCT trade_date FROM ticks
            WHERE symbol = 'TX' AND trade_time >= '15:00:00'
        """).fetchall()}
        all_night_candidates = sorted(set(day_dates) | night_tick_dates)

        def night_session_ended(d: date) -> bool:
            night_end = datetime(d.year, d.month, d.day) + timedelta(days=1, hours=5)
            return now >= night_end

        pending_night = [
            d for d in all_night_candidates
            if d not in processed_night and night_session_ended(d)
        ]
        print(f"夜盤待處理 {len(pending_night)} 個 session")

        new_night_bars = 0
        for prev_date in pending_night:
            contract = get_day_contract(conn, prev_date)
            if contract is None:
                # 假日無日盤時，從 ticks 找當日夜盤主力合約
                r = conn.execute("""
                    SELECT contract, SUM(volume) AS vol
                    FROM ticks
                    WHERE symbol = 'TX' AND trade_date = ?
                      AND trade_time >= '15:00:00'
                    GROUP BY contract ORDER BY vol DESC LIMIT 1
                """, [prev_date]).fetchone()
                if r is None:
                    continue
                contract = r[0].strip()
            df = build_1m_night_for_session(conn, prev_date, contract)
            if df.empty:
                continue
            conn.execute("INSERT INTO ohlcv_1m SELECT * FROM df")
            new_night_bars += len(df)

        # --- 統計 ---
        stats = conn.execute("""
            SELECT
                MIN(timestamp)   AS min_ts,
                MAX(timestamp)   AS max_ts,
                COUNT(*)         AS total_bars,
                COUNT(*) FILTER (WHERE CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00') AS day_bars,
                COUNT(*) FILTER (WHERE CAST(timestamp AS TIME) >= TIME '15:00:00'
                                    OR CAST(timestamp AS TIME) < TIME '05:00:00') AS night_bars
            FROM ohlcv_1m WHERE symbol = 'TX'
        """).fetchone()

        print(f"\n=== ohlcv_1m 統計（TX）===")
        print(f"本次新增：日盤 {new_day_bars:,} 根，夜盤 {new_night_bars:,} 根")
        print(f"時間範圍：{stats[0]} ~ {stats[1]}")
        print(f"總 bar 數：{stats[2]:,}（日盤 {stats[3]:,}，夜盤 {stats[4]:,}）")


if __name__ == "__main__":
    main()

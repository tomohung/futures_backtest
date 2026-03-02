"""
Step 2: ticks → ohlcv_1m

從 ticks 表合成 1 分 K（日盤 08:45~13:45）。
- 有成交的分鐘：OHLCV 從 tick 算出
- 無成交的分鐘：用前一分鐘 close 填充 OHLC，volume=0，tick_count=0
- 支援增量：已存在的 (timestamp, symbol, contract) 跳過
"""

from pathlib import Path
from datetime import time, timedelta, date

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
    rows = conn.execute("""
        SELECT DISTINCT timestamp::date FROM ohlcv_1m WHERE symbol = 'TX'
    """).fetchall()
    return {r[0] for r in rows}


def build_minute_index(trade_date: date) -> pd.DatetimeIndex:
    """產生日盤 08:45 ~ 13:45 的每分鐘時間戳（共 61 根）"""
    start = pd.Timestamp(trade_date) + pd.Timedelta(hours=8, minutes=45)
    end   = pd.Timestamp(trade_date) + pd.Timedelta(hours=13, minutes=45)
    return pd.date_range(start, end, freq="1min")


def build_1m_for_date(
    conn: duckdb.DuckDBPyConnection,
    trade_date: date,
) -> pd.DataFrame:
    # 拉出當日日盤 ticks（含端點）
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

    # 取當日主力合約（成交量最多的那個）
    dominant_contract = (
        ticks.groupby("contract")["volume"].sum().idxmax()
    )
    ticks = ticks[ticks["contract"] == dominant_contract].copy()

    # 對齊到分鐘（floor）
    ticks["ts"] = pd.to_datetime(
        trade_date.strftime("%Y-%m-%d") + " " + ticks["trade_time"].astype(str)
    ).dt.floor("1min")

    # 合成有成交的分鐘
    agg = ticks.groupby("ts").agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("volume", "sum"),
        tick_count=("price", "count"),
    )

    # 完整分鐘索引（08:45 ~ 13:45）
    full_idx = build_minute_index(trade_date)
    ohlcv = agg.reindex(full_idx)

    # 填充空白分鐘：forward-fill close，volume=0，tick_count=0
    ohlcv["close"] = ohlcv["close"].ffill()
    # 第一根若無成交（極少見），往後再找第一個有效 close
    if ohlcv["close"].isna().all():
        return pd.DataFrame()
    ohlcv["close"] = ohlcv["close"].bfill()

    mask_empty = ohlcv["open"].isna()
    ohlcv.loc[mask_empty, "open"]       = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "high"]       = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "low"]        = ohlcv.loc[mask_empty, "close"]
    ohlcv.loc[mask_empty, "volume"]     = 0
    ohlcv.loc[mask_empty, "tick_count"] = 0

    ohlcv = ohlcv.reset_index().rename(columns={"index": "timestamp"})
    ohlcv["symbol"]      = "TX"
    ohlcv["contract"]    = dominant_contract
    ohlcv["is_rollover"] = False
    ohlcv["adjustment"]  = 0.0
    ohlcv["adj_close"]   = ohlcv["close"]

    ohlcv["volume"]     = ohlcv["volume"].astype(int)
    ohlcv["tick_count"] = ohlcv["tick_count"].astype(int)

    cols = [
        "timestamp", "symbol", "contract",
        "open", "high", "low", "close",
        "volume", "tick_count",
        "is_rollover", "adjustment", "adj_close",
    ]
    return ohlcv[cols]


def main() -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)
        processed_dates = get_processed_dates(conn)

        # 取 ticks 中有 TX 資料的所有日期
        all_dates = conn.execute("""
            SELECT DISTINCT trade_date FROM ticks
            WHERE symbol = 'TX'
            ORDER BY trade_date
        """).fetchall()
        all_dates = [r[0] for r in all_dates]

        pending = [d for d in all_dates if d not in processed_dates]
        print(f"ticks 共 {len(all_dates)} 個交易日，待處理 {len(pending)} 個")

        new_bars = 0
        for trade_date in pending:
            df = build_1m_for_date(conn, trade_date)
            if df.empty:
                continue
            conn.execute("INSERT INTO ohlcv_1m SELECT * FROM df")
            new_bars += len(df)

        # 統計
        stats = conn.execute("""
            SELECT
                MIN(d)           AS min_date,
                MAX(d)           AS max_date,
                SUM(daily_bars)  AS total_bars,
                COUNT(*)         AS trading_days,
                AVG(daily_vol)   AS avg_daily_volume
            FROM (
                SELECT
                    timestamp::date  AS d,
                    COUNT(*)         AS daily_bars,
                    SUM(volume)      AS daily_vol
                FROM ohlcv_1m
                WHERE symbol = 'TX'
                GROUP BY d
            ) t
        """).fetchone()

        print(f"\n=== ohlcv_1m 統計（TX 日盤）===")
        print(f"本次新增：{new_bars:,} 根 K 棒")
        print(f"日期範圍：{stats[0]} ~ {stats[1]}")
        print(f"總 bar 數：{stats[2]:,}")
        print(f"交易日數：{stats[3]}")
        print(f"每日平均成交量：{stats[4]:.0f}")


if __name__ == "__main__":
    main()

"""
Step 3: 換倉處理 + 連續合約

換倉偵測方式：比較連續交易日的主力合約，當合約代號改變時即為換倉。
（build_1m.py 每天只保留主力合約，故每天只有一筆合約記錄）

Panama Method：
  adj_close(t) = close(t) + sum of all price_gaps from rollovers AFTER date t
  即：每次換倉後，往前回填歷史 adjustment。

冪等：重跑前清除 rollover_log 並重置所有 adjustment。
"""

from pathlib import Path
from datetime import date

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rollover_log (
            rollover_date    DATE,
            symbol           VARCHAR,
            old_contract     VARCHAR,
            new_contract     VARCHAR,
            old_last_price   DECIMAL(10,2),
            new_first_price  DECIMAL(10,2),
            price_gap        DECIMAL(10,2),
            method           VARCHAR
        )
    """)


def main() -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        init_db(conn)

        row = conn.execute("""
            SELECT MIN(timestamp::date), MAX(timestamp::date)
            FROM ohlcv_1m WHERE symbol = 'TX'
        """).fetchone()

        if row[0] is None:
            print("ohlcv_1m 無資料，請先執行 build_1m.py")
            return

        min_date, max_date = row[0], row[1]
        print(f"ohlcv_1m 日期範圍：{min_date} ~ {max_date}")

        # 重置（冪等）
        conn.execute("DELETE FROM rollover_log WHERE symbol = 'TX'")
        conn.execute("""
            UPDATE ohlcv_1m
            SET adjustment = 0.0, adj_close = close, is_rollover = FALSE
            WHERE symbol = 'TX'
        """)

        # 每個交易日的主力合約、日盤開盤價（第一根K）、收盤價（最後一根K）
        daily = conn.execute("""
            SELECT
                d                                                          AS trade_date,
                MAX(contract)                                              AS contract,
                MAX(first_close) FILTER (WHERE rn_asc = 1)                AS open_price,
                MAX(last_close)  FILTER (WHERE rn_desc = 1)               AS close_price
            FROM (
                SELECT
                    timestamp::date                                            AS d,
                    contract,
                    close                                                      AS first_close,
                    close                                                      AS last_close,
                    ROW_NUMBER() OVER (PARTITION BY timestamp::date ORDER BY timestamp ASC)  AS rn_asc,
                    ROW_NUMBER() OVER (PARTITION BY timestamp::date ORDER BY timestamp DESC) AS rn_desc
                FROM ohlcv_1m
                WHERE symbol = 'TX'
            ) t
            GROUP BY d
            ORDER BY d
        """).df()

        daily["trade_date"] = pd.to_datetime(daily["trade_date"]).dt.date

        # 偵測合約切換：前一天 contract != 今天 contract
        daily["prev_contract"]    = daily["contract"].shift(1)
        daily["prev_close_price"] = daily["close_price"].shift(1)

        rollovers = daily[
            daily["prev_contract"].notna() &
            (daily["contract"] != daily["prev_contract"])
        ].copy()

        print(f"偵測到 {len(rollovers)} 次換倉")

        rollover_logs = []
        for _, row in rollovers.iterrows():
            rollover_date   = row["trade_date"]
            old_contract    = row["prev_contract"]
            new_contract    = row["contract"]
            old_last_price  = float(row["prev_close_price"])   # 舊合約前一日收盤
            new_first_price = float(row["open_price"])          # 新合約當日開盤
            price_gap       = old_last_price - new_first_price  # Panama 調整量

            rollover_logs.append({
                "rollover_date":   rollover_date,
                "symbol":          "TX",
                "old_contract":    old_contract,
                "new_contract":    new_contract,
                "old_last_price":  old_last_price,
                "new_first_price": new_first_price,
                "price_gap":       price_gap,
                "method":          "panama",
            })

            # 標記換倉日的 K 棒
            conn.execute("""
                UPDATE ohlcv_1m
                SET is_rollover = TRUE
                WHERE symbol = 'TX' AND timestamp::date = ?
            """, [rollover_date])

        if not rollover_logs:
            print("無換倉記錄，結束")
            return

        log_df = pd.DataFrame(rollover_logs).sort_values("rollover_date")
        conn.execute("INSERT INTO rollover_log SELECT * FROM log_df")
        print(f"寫入 {len(rollover_logs)} 筆換倉記錄")

        # Panama backward adjustment：
        # adj = new_first - old_last（正值=新合約比舊合約貴，歷史要往上調）
        # 讓 adj_close(最後一根舊合約) = adj_close(第一根新合約)
        for _, row in log_df.iterrows():
            conn.execute("""
                UPDATE ohlcv_1m
                SET adjustment = adjustment - ?
                WHERE symbol = 'TX' AND timestamp::date < ?
            """, [row["price_gap"], row["rollover_date"]])

        # 最後統一計算 adj_close
        conn.execute("""
            UPDATE ohlcv_1m
            SET adj_close = close + adjustment
            WHERE symbol = 'TX'
        """)

        # 輸出換倉記錄
        gaps = conn.execute("""
            SELECT rollover_date, old_contract, new_contract,
                   ROUND(old_last_price, 0) AS old_close,
                   ROUND(new_first_price, 0) AS new_open,
                   ROUND(price_gap, 0) AS gap
            FROM rollover_log
            WHERE symbol = 'TX'
            ORDER BY rollover_date
        """).df()

        print(f"\n=== 換倉記錄（全部 {len(gaps)} 筆）===")
        print(gaps.to_string(index=False))

        # 驗證：換倉切換點 adj_close 連續性
        # 正確比較：換倉日「前一日最後一根」vs「換倉日第一根」
        continuity = conn.execute("""
            WITH first_bar AS (
                SELECT timestamp::date AS d, MIN(timestamp) AS first_ts
                FROM ohlcv_1m WHERE symbol = 'TX'
                GROUP BY timestamp::date
            ),
            prev_last_bar AS (
                SELECT
                    d,
                    LAG(d) OVER (ORDER BY d) AS prev_d
                FROM first_bar
            ),
            prev_last_ts AS (
                SELECT plb.d, lb2.last_ts
                FROM prev_last_bar plb
                JOIN (
                    SELECT timestamp::date AS d, MAX(timestamp) AS last_ts
                    FROM ohlcv_1m WHERE symbol = 'TX'
                    GROUP BY timestamp::date
                ) lb2 ON lb2.d = plb.prev_d
            ),
            crossover AS (
                SELECT
                    r.rollover_date,
                    o_prev.adj_close  AS prev_last_adj,
                    o_this.adj_close  AS this_first_adj
                FROM rollover_log r
                JOIN prev_last_ts plt ON plt.d = r.rollover_date
                JOIN ohlcv_1m o_prev ON o_prev.timestamp = plt.last_ts AND o_prev.symbol = 'TX'
                JOIN first_bar fb ON fb.d = r.rollover_date
                JOIN ohlcv_1m o_this ON o_this.timestamp = fb.first_ts AND o_this.symbol = 'TX'
                WHERE r.symbol = 'TX'
            )
            SELECT
                rollover_date,
                ROUND(prev_last_adj, 0)                   AS prev_day_last_adj,
                ROUND(this_first_adj, 0)                  AS this_day_first_adj,
                ROUND(this_first_adj - prev_last_adj, 0)  AS gap
            FROM crossover
            ORDER BY rollover_date
        """).df()

        print(f"\n=== 換倉日 adj_close 連續性驗證 ===")
        if continuity.empty:
            print("（無資料）")
        else:
            print(continuity.to_string(index=False))
            large = continuity[continuity["gap"].abs() > 100]
            if large.empty:
                print("\n✓ 所有換倉日跳空均在合理範圍內")
            else:
                print(f"\n⚠ 發現 {len(large)} 筆跳空 > 100 點，請確認：")
                print(large.to_string(index=False))


if __name__ == "__main__":
    main()

"""測試用的合成市場資料產生器。

兩種粒度：
  * `write_ohlcv_db` — 寫出含 ohlcv_1m 的暫存 DuckDB，給需要走 runner.load_data_* 的測試
  * `day_frame`      — 直接組 backtesting.py 吃的日盤 DataFrame，給策略規則測試

⚠️ 價格一律用「震盪 + 緩升」而非單調斜坡。完美趨勢會讓 ADX 飽和在 100，
   讓因果性測試假性通過（見 test_lookahead.py 的踩坑記錄）。
"""
from datetime import date, datetime, time, timedelta

import duckdb
import numpy as np
import pandas as pd

# ohlcv_1m 一個完整交易日的實際 bar 數（用真實 DB 驗證過）
DAY_SESSION_BARS = 301      # 08:45–13:45 含端點
EVENING_BARS = 540          # 15:00–23:59
EARLY_BARS = 301            # 隔日 00:00–05:00
BARS_PER_TRADING_DAY = DAY_SESSION_BARS + EVENING_BARS + EARLY_BARS   # 1142

SESSION_OPEN = time(8, 45)


def weekdays(start: date, n: int) -> list:
    """從 start 起算的 n 個平日（不處理國定假日，測試不需要）。"""
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def bar_times(d: date):
    """單一交易日在 ohlcv_1m 中的所有 timestamp（日盤 + 傍晚 + 隔日凌晨）。"""
    base = datetime.combine(d, SESSION_OPEN)
    for i in range(DAY_SESSION_BARS):
        yield base + timedelta(minutes=i)
    base = datetime.combine(d, time(15, 0))
    for i in range(EVENING_BARS):
        yield base + timedelta(minutes=i)
    base = datetime.combine(d + timedelta(days=1), time(0, 0))
    for i in range(EARLY_BARS):
        yield base + timedelta(minutes=i)


def write_ohlcv_db(path, dates, *, perturb_after=None, perturb_delta=5000.0):
    """建立含 ohlcv_1m 的暫存 DuckDB。

    perturb_after : datetime | None
        若給定，嚴格晚於此時間的所有 bar 價格 +perturb_delta。
        用來檢驗「未來的 bar 有沒有滲進過去的特徵值」。
    """
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE ohlcv_1m (
            timestamp TIMESTAMP, symbol VARCHAR, contract VARCHAR,
            open DECIMAL(10,2), high DECIMAL(10,2), low DECIMAL(10,2),
            close DECIMAL(10,2), volume INT, tick_count INT,
            is_rollover BOOLEAN, adjustment DECIMAL(10,2), adj_close DECIMAL(10,2)
        )
    """)
    rows, i = [], 0
    for d in dates:
        for ts in bar_times(d):
            i += 1
            price = 20000.0 + 300 * np.sin(i / 450.0) + 0.05 * i
            p = price + (perturb_delta if perturb_after and ts > perturb_after else 0.0)
            rows.append(
                f"('{ts:%Y-%m-%d %H:%M:%S}','TX','202601',{p:.2f},{p+5:.2f},"
                f"{p-5:.2f},{p:.2f},100,20,false,0.00,{p:.2f})"
            )
    con.execute(f"INSERT INTO ohlcv_1m VALUES {','.join(rows)}")
    con.close()


def day_frame(d: date, closes, *, wick: float = 1.0, volume: int = 100) -> pd.DataFrame:
    """把一串 close 攤成 08:45 起的日盤 1 分 K，欄位符合 backtesting.py 要求。

    每根 bar：Open = Close = closes[i]，High = +wick，Low = -wick。
    這讓「收盤突破 OR 高點」這類條件可以被精確控制。

    len(closes) 必須 <= DAY_SESSION_BARS（301，即 08:45–13:45）。
    """
    assert len(closes) <= DAY_SESSION_BARS, "超過日盤 bar 數"
    idx = [datetime.combine(d, SESSION_OPEN) + timedelta(minutes=i)
           for i in range(len(closes))]
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"Open": c, "High": c + wick, "Low": c - wick, "Close": c,
         "Volume": np.full(len(c), volume)},
        index=pd.DatetimeIndex(idx),
    )


def minute_of(t: time) -> int:
    """08:45 起算的 bar 索引。day_frame 的第 i 根就是 08:45 + i 分鐘。"""
    return (t.hour * 60 + t.minute) - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)


def multi_day_frame(days: dict) -> pd.DataFrame:
    """把 {date: closes} 串成多日的日盤 DataFrame。

    ⚠️ backtesting.py 會跳過「所有 indicator 都還是 NaN」的前導 bar。
    ORBStrategy 的 OR 高低線在當日 09:30 前必為 NaN，因此**第一個交易日
    的開盤區間永遠不會進 next()**，第一天不可能有交易。
    測試請一律放一天暖身日，斷言從第二天開始（見 test_orb_long_rules.py）。
    """
    return pd.concat([day_frame(d, c) for d, c in sorted(days.items())])

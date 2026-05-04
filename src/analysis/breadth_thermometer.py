"""H079 漲停萎縮溫度計 — 早盤觀察指標

每日輸出今日的「資金溫度計」狀態，作為觀察用 alert（不直接介入策略）。

訊號定義（H079-C 最佳參數）
-----------------------------
- ma = 7 日均
- pct = 0.15 分位門檻
- consec = 3 天連續
- skip_n = 10 天防禦窗
- logic = RATIO only（漲停成交額占比 ma7）

輸出
----
- 今日 raw 漲停占比 + ma7
- 全期門檻
- 距離門檻多遠（接近/跌破）
- 連續跌破天數
- 事件狀態（觸發/防禦中/正常）
- 過去 14 天軌跡

使用方式：
    uv run python src/analysis/breadth_thermometer.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

# H079-C 最佳參數
MA_DAYS = 7
PCT_THRESHOLD = 0.15
CONSEC_DAYS = 3
DEFENSE_WINDOW = 10


def load_breadth_history(end: date | None = None,
                         lookback_years: int = 8) -> pd.DataFrame:
    """Load market_breadth + stock_day → daily indicators."""
    end = end or date.today()
    start = end - timedelta(days=int(lookback_years * 365.25))
    sql = """
    WITH b AS (
        SELECT trade_date,
               SUM(up_limit_count) AS up_limit_count,
               SUM(total_value)    AS total_value
        FROM market_breadth WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    ),
    lv AS (
        SELECT trade_date,
               SUM(CASE WHEN is_limit_up THEN value ELSE 0 END) AS lu_value
        FROM stock_day WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    )
    SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value
    FROM b LEFT JOIN lv USING (trade_date) ORDER BY b.trade_date
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(sql, [start, end, start, end]).fetchdf()
    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    df["lu_ratio_ma"] = df["lu_value_ratio"].rolling(MA_DAYS).mean()
    return df


def compute_status(df: pd.DataFrame) -> dict:
    """Compute today's thermometer status."""
    threshold = df["lu_ratio_ma"].quantile(PCT_THRESHOLD)
    df = df.copy()
    df["below"] = df["lu_ratio_ma"] < threshold
    df["event"] = (df["below"].rolling(CONSEC_DAYS).sum() >= CONSEC_DAYS).fillna(False)
    df["defense"] = df["event"].rolling(DEFENSE_WINDOW, min_periods=1).max().astype(bool)

    if df.empty:
        return {"error": "no data"}

    today = df.iloc[-1]
    today_ma = today["lu_ratio_ma"]
    distance_to_threshold = today_ma - threshold  # 正 = 高於門檻（安全）
    distance_pct = distance_to_threshold / threshold * 100

    # 連續低於門檻天數
    last_below_streak = 0
    for v in reversed(df["below"].tolist()):
        if v:
            last_below_streak += 1
        else:
            break

    # 事件 / 防禦狀態
    in_event = bool(today["event"])
    in_defense = bool(today["defense"])
    if in_defense and not in_event:
        # 算事件結束日 / 還剩幾天
        for i in range(len(df)-1, -1, -1):
            if df.iloc[i]["event"]:
                event_end_idx = i
                break
        days_since_event = len(df) - 1 - event_end_idx
        days_left = max(0, DEFENSE_WINDOW - days_since_event)
    else:
        days_left = DEFENSE_WINDOW if in_event else 0

    # 警示等級
    if in_event:
        level = "🔴 RED 事件觸發"
    elif in_defense:
        level = f"🟠 ORANGE 防禦窗（剩 {days_left} 天）"
    elif today["below"]:
        level = f"🟡 YELLOW 跌破門檻（連續 {last_below_streak} 天）"
    elif distance_pct < 50:
        level = "🟡 YELLOW 接近門檻 (< 50% buffer)"
    else:
        level = "🟢 GREEN 安全"

    return {
        "trade_date": today["trade_date"],
        "today_raw_ratio": today["lu_value_ratio"],
        "today_ma": today_ma,
        "threshold": threshold,
        "distance_pct": distance_pct,
        "below_streak": last_below_streak,
        "in_event": in_event,
        "in_defense": in_defense,
        "days_left_in_defense": days_left,
        "level": level,
        "history_14d": df.tail(14)[
            ["trade_date", "up_limit_count", "lu_value_ratio",
             "lu_ratio_ma", "below", "event", "defense"]
        ],
    }


def print_briefing(status: dict) -> None:
    if "error" in status:
        print(f"[H079 溫度計] {status['error']}")
        return

    print()
    print("=" * 60)
    print("H079 漲停萎縮溫度計 (RATIO ma7, pct=0.15)")
    print("=" * 60)
    print(f"資料日期：{status['trade_date'].strftime('%Y-%m-%d')}")
    print(f"當日漲停成交額占比：{status['today_raw_ratio']*100:.2f}%")
    print(f"7 日均（ma7）：{status['today_ma']*100:.2f}%")
    print(f"全期 15 分位門檻：{status['threshold']*100:.2f}%")
    print(f"距離門檻：{status['distance_pct']:+.0f}% buffer "
          f"({'高於' if status['distance_pct']>0 else '低於'}門檻)")
    if status["below_streak"] > 0:
        print(f"已連續 {status['below_streak']} 天 ma7 < 門檻")
    print()
    print(f"狀態：{status['level']}")
    if status["in_defense"]:
        print(f"  防禦窗剩 {status['days_left_in_defense']} 天 "
              f"(事件成立 → 後續 {DEFENSE_WINDOW} 天回測上會建議暫停做多)")
    print()
    print("過去 14 天軌跡：")
    h = status["history_14d"].copy()
    h["date"] = h["trade_date"].dt.strftime("%m-%d")
    h["raw%"] = (h["lu_value_ratio"] * 100).round(2)
    h["ma7%"] = (h["lu_ratio_ma"] * 100).round(2)
    h["mark"] = h.apply(lambda r:
        ("🔴" if r["event"] else ("🟠" if r["defense"] else
         ("🟡" if r["below"] else "🟢"))), axis=1)
    print(h[["date", "up_limit_count", "raw%", "ma7%", "mark"]].to_string(index=False))
    print()


def main() -> None:
    df = load_breadth_history()
    status = compute_status(df)
    print_briefing(status)


if __name__ == "__main__":
    main()

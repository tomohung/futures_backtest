#!/usr/bin/env python3
"""H103 跳空下方遠做多 — 盤前提醒（觀察用，非自動訊號）。

H103（Inconclusive，傾向正面）：開盤跌破昨/前日 VWAP 成本、且最近成本在
≥1×ema20（日盤振幅）的遠上方 → 開盤做多，目標 +0.7×ema20、停損 −0.5×ema20。
（四象限只有這一格跨體制穩健，詳見 research/active/H103-gapdown-cost-revert/）

盤前 morning_briefing 跑時通常還沒有今日開盤價，故用最近夜盤收盤當「預判開盤」，
並給觸發價 X = min(vwap_last, vwap_prev) − 1.0×ema20：今日開盤落在 X 以下即成立。

使用：uv run python src/analysis/h103_alert.py
"""
import duckdb
import pandas as pd
from datetime import timedelta
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"
CLEAR_THRESH = 1.0   # up_clear_norm 門檻（≥1 個日均振幅）
TARGET_K, STOP_K = 0.7, 0.5


def compute_h103_alert() -> dict | None:
    """回傳盤前提醒所需數據；資料不足回 None。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        last_day = conn.execute("""
            SELECT MAX(timestamp::DATE) FROM ohlcv_1m
            WHERE symbol = ? AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL]).fetchone()[0]
        if last_day is None:
            return None

        # 最近兩個日盤交易日的 VWAP（量加權，對齊 key_prices）
        vwap_rows = conn.execute("""
            SELECT timestamp::DATE AS d,
                   ROUND(SUM(close * volume) / SUM(volume))::INT AS vwap
            FROM ohlcv_1m
            WHERE symbol = ? AND timestamp::DATE <= ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY d ORDER BY d DESC LIMIT 2
        """, [SYMBOL, last_day]).fetchall()
        if len(vwap_rows) < 2:
            return None
        vwap_last, vwap_prev = vwap_rows[0][1], vwap_rows[1][1]

        # causal EMA20(日盤 high−low)，截至 last_day（= 次一交易日的 ema20）
        rng = conn.execute("""
            SELECT timestamp::DATE AS d, (MAX(high) - MIN(low)) AS r
            FROM ohlcv_1m
            WHERE symbol = ? AND timestamp::DATE <= ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY d ORDER BY d
        """, [SYMBOL, last_day]).df()
        if len(rng) < 20:
            return None
        ema20 = float(rng["r"].astype(float).ewm(span=20, adjust=False).mean().iloc[-1])

        # 最近夜盤收盤（last_day 15:00 → 次日 05:00）= 預判次一交易日開盤
        next_day = last_day + timedelta(days=1)
        night_close = conn.execute("""
            WITH night_ticks AS (
                SELECT contract, price,
                       (trade_date::VARCHAR || ' ' || trade_time::VARCHAR)::TIMESTAMP AS ts
                FROM ticks
                WHERE symbol = ?
                  AND ((trade_date = ? AND trade_time >= '15:00:00')
                       OR (trade_date = ? AND trade_time <= '05:00:00'))
            ),
            dominant AS (
                SELECT contract FROM night_ticks
                GROUP BY contract ORDER BY COUNT(*) DESC LIMIT 1
            )
            SELECT arg_max(price, ts)::INT FROM night_ticks
            WHERE contract = (SELECT contract FROM dominant)
        """, [SYMBOL, last_day, next_day]).fetchone()[0]

    cost = min(vwap_last, vwap_prev)
    trigger = cost - CLEAR_THRESH * ema20           # 觸發價 X：開盤 ≤ X 即成立
    ref_open = night_close
    triggered = ref_open is not None and ref_open <= trigger
    return {
        "last_day": last_day, "vwap_last": vwap_last, "vwap_prev": vwap_prev,
        "cost": cost, "ema20": ema20, "trigger": trigger, "ref_open": ref_open,
        "triggered": triggered,
        "target": (ref_open + TARGET_K * ema20) if ref_open is not None else None,
        "stop": (ref_open - STOP_K * ema20) if ref_open is not None else None,
    }


def main():
    a = compute_h103_alert()
    print("=" * 70)
    print("[H103 跳空下方遠做多] 盤前提醒（觀察用・H103 Inconclusive・前推/覆盤）")
    print("=" * 70)
    if a is None:
        print("  資料不足，略過。")
        return
    print(f"  基準日 {a['last_day']}｜成本 vwap_last={a['vwap_last']} "
          f"vwap_prev={a['vwap_prev']}｜ema20={a['ema20']:.0f}")
    print(f"  觸發價 X = min成本({a['cost']}) − 1.0×ema20 = {a['trigger']:.0f}"
          "  （今日開盤 ≤ X 即成立做多）")
    if a["ref_open"] is None:
        print("  夜盤資料未到；待今日開盤確認是否 ≤ X。")
    elif a["triggered"]:
        print(f"  夜收預判開盤 = {a['ref_open']}")
        print(f"  → 🔴 預判觸發：開盤≈{a['ref_open']} 做多｜"
              f"目標 {a['target']:.0f}(+{TARGET_K}×ema)｜"
              f"停損 {a['stop']:.0f}(−{STOP_K}×ema)｜R:R {TARGET_K/STOP_K:.1f}")
    else:
        print(f"  夜收預判開盤 = {a['ref_open']}")
        print(f"  → ⚪ 未觸發：開盤需再低 {a['ref_open'] - a['trigger']:.0f} 點"
              f"（跌破 {a['trigger']:.0f}）才成立")
    print("  註：僅供觀察，非自動訊號；做空/夾中間/跳空上方不適用。")


if __name__ == "__main__":
    main()

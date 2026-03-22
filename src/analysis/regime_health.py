#!/usr/bin/env python3
"""
Regime 健康快報 — 輕量版（不跑策略回測，秒級完成）

輸出近 20 日的 range%、ER、swing count，與歷史比較。
供 morning_briefing.py 呼叫。

使用方式：
    uv run python src/analysis/regime_health.py
"""
import duckdb
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"

# 從 strategy_health.py 校準的 EstHL 閾值
THRESHOLDS = {
    "range_pct": {"watch": 0.74, "danger": 0.55},
    "er":        {"watch": 0.033, "danger": 0.020},
}


def compute_regime(n_recent=20) -> dict:
    """計算 regime 指標，回傳 dict 包含近期與歷史數據。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 每日 OHLCV
        daily = conn.execute("""
            SELECT
                CAST(timestamp AS DATE) AS trade_date,
                MIN_BY(open, timestamp)  AS open,
                MAX(high)               AS high,
                MIN(low)                AS low,
                MAX_BY(close, timestamp) AS close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1
            ORDER BY 1
        """, [SYMBOL]).fetchall()

        # 1m closes for ER & swing count
        bars_1m = conn.execute("""
            SELECT CAST(timestamp AS DATE) AS trade_date, close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """, [SYMBOL]).fetchall()

    # 整理每日 range%
    days = []
    for trade_date, open_p, high, low, close in daily:
        range_pct = float((high - low) / open_p * 100)
        days.append({"date": trade_date, "open": float(open_p),
                     "range_pt": float(high - low), "range_pct": range_pct})

    # 每日 ER & swing count
    from collections import defaultdict
    day_closes = defaultdict(list)
    for trade_date, close in bars_1m:
        day_closes[trade_date].append(float(close))

    for d in days:
        closes = day_closes.get(d["date"], [])
        if len(closes) < 2:
            d["er"] = None
            d["swing_count"] = None
            continue
        arr = np.array(closes)
        net = abs(arr[-1] - arr[0])
        steps = np.abs(np.diff(arr)).sum()
        d["er"] = net / steps if steps > 0 else 0.0

        diffs = np.diff(arr)
        signs = np.sign(diffs)
        signs_nz = signs[signs != 0]
        d["swing_count"] = int(np.sum(np.diff(signs_nz) != 0)) if len(signs_nz) > 1 else 0

    # EMA(20) for range_pct and ER
    alpha = 2 / (20 + 1)
    ema_range = None
    ema_er = None
    for d in days:
        if ema_range is None:
            ema_range = d["range_pct"]
        else:
            ema_range = alpha * d["range_pct"] + (1 - alpha) * ema_range
        d["ema_range_pct"] = ema_range

        if d["er"] is not None:
            if ema_er is None:
                ema_er = d["er"]
            else:
                ema_er = alpha * d["er"] + (1 - alpha) * ema_er
        d["ema_er"] = ema_er

    recent = days[-n_recent:]
    all_range_pct = [d["range_pct"] for d in days]
    all_er = [d["er"] for d in days if d["er"] is not None]

    return {
        "recent": recent,
        "all_mean_range_pct": np.mean(all_range_pct),
        "all_mean_er": np.mean(all_er),
        "n_total": len(days),
    }


def print_report(n_recent=20):
    """輸出 regime 健康快報。"""
    data = compute_regime(n_recent)
    recent = data["recent"]

    if not recent:
        print("[WARN] 無資料")
        return

    cur_ema_range = recent[-1]["ema_range_pct"]
    cur_ema_er = recent[-1]["ema_er"]
    recent_mean_range = np.mean([d["range_pct"] for d in recent])
    recent_mean_er = np.mean([d["er"] for d in recent if d["er"] is not None])
    recent_mean_swing = np.mean([d["swing_count"] for d in recent if d["swing_count"] is not None])

    hist_range = data["all_mean_range_pct"]
    hist_er = data["all_mean_er"]

    # Signal
    range_ok = cur_ema_range >= THRESHOLDS["range_pct"]["watch"]
    er_ok = cur_ema_er >= THRESHOLDS["er"]["watch"]

    if range_ok and er_ok:
        signal = "OK"
    elif not range_ok and not er_ok:
        signal = "DANGER"
    else:
        signal = "WATCH"

    # Output
    print(f"\n### Regime 健康")
    print(f"| 指標 | 近{n_recent}日均 | EMA20 | 歷史均 | 閾值 | 狀態 |")
    print(f"|------|--------:|------:|------:|-----:|------|")

    range_status = "OK" if range_ok else "WATCH"
    er_status = "OK" if er_ok else "WATCH"

    print(f"| 波動% (H-L/Open) | {recent_mean_range:.2f}% | {cur_ema_range:.2f}% "
          f"| {hist_range:.2f}% | {THRESHOLDS['range_pct']['watch']:.2f}% | {range_status} |")
    print(f"| 效率比率 ER | {recent_mean_er:.3f} | {cur_ema_er:.3f} "
          f"| {hist_er:.3f} | {THRESHOLDS['er']['watch']:.3f} | {er_status} |")
    print(f"| 翻轉次數 | {recent_mean_swing:.0f} | — | — | — | — |")

    print(f"\n**綜合信號：{signal}**")

    if signal == "WATCH":
        if not range_ok:
            print(f"  波動% EMA20 ({cur_ema_range:.2f}%) 低於閾值 ({THRESHOLDS['range_pct']['watch']:.2f}%)，日盤振幅縮小")
        if not er_ok:
            print(f"  ER EMA20 ({cur_ema_er:.3f}) 低於閾值 ({THRESHOLDS['er']['watch']:.3f})，盤中走勢碎片化")
    elif signal == "DANGER":
        print(f"  波動% 和 ER 同時低於閾值，策略環境不佳")

    # 近 5 日明細
    print(f"\n| 日期 | 波動(pt) | 波動% | ER | 翻轉 |")
    print(f"|------|--------:|------:|-----:|-----:|")
    for d in recent[-5:]:
        er_str = f"{d['er']:.3f}" if d["er"] is not None else "—"
        sc_str = f"{d['swing_count']}" if d["swing_count"] is not None else "—"
        print(f"| {d['date']} | {d['range_pt']:.0f} | {d['range_pct']:.2f}% | {er_str} | {sc_str} |")


if __name__ == "__main__":
    print_report()

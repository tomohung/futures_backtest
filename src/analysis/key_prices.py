#!/usr/bin/env python3
"""
產生日盤/夜盤關鍵價格參考表

使用方式：
    uv run python src/analysis/key_prices.py
"""
import duckdb
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from src.analysis.chart_style import (
    apply_style, style_axes, style_table,
    BG_FIG, BG_AXES, BG_TABLE_HIGHLIGHT,
    COLOR_UP, COLOR_DOWN,
    COLOR_ACCENT_ORANGE, COLOR_ACCENT_BLUE, COLOR_ACCENT_PURPLE,
    COLOR_ACCENT_GOLD, COLOR_ACCENT_TEAL, COLOR_ACCENT_CORAL,
    COLOR_TEXT, COLOR_TEXT_LIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_WHITE,
    COLOR_GRID, COLOR_BORDER,
)

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"


_NVF_FALLBACK_THRESHOLD = 0.93   # warmup fallback (近 4 年 EMA expanding median ~0.935)
_NVF_MIN_HISTORY_NIGHTS = 60     # warmup 期最少夜盤數

# H092 4-tier classification (cutoffs validated 2021-2026)
_NVF_TIER_CUTS = (0.8, 1.0, 1.2)
_NVF_TIER_LABELS = ("deep STOP", "mid STOP", "mid GO", "strong GO")
_NVF_TIER_ICONS = {
    "deep STOP": "🟦", "mid STOP": "🟨",
    "mid GO": "🟩", "strong GO": "🟧",
}
_NVF_TIER_HINTS = {
    "deep STOP": "窄幅震盪日 — 趨勢/反轉雙弱,S001/S002 已 STOP",
    "mid STOP":  "方向中性 — 標準操作（NVF 門檻邊緣）",
    "mid GO":    "偏多日 — upper bias +9pp,適合 long-trend",
    "strong GO": "高波動 + V 型風險 — 減倉、加大 SL、留意 mean-revert",
}


def _classify_nvf_tier(night_norm: float) -> str:
    """4-tier NVF classification per H092 (cutoffs 0.8 / 1.0 / 1.2)."""
    if night_norm < _NVF_TIER_CUTS[0]:
        return _NVF_TIER_LABELS[0]
    if night_norm < _NVF_TIER_CUTS[1]:
        return _NVF_TIER_LABELS[1]
    if night_norm < _NVF_TIER_CUTS[2]:
        return _NVF_TIER_LABELS[2]
    return _NVF_TIER_LABELS[3]


def _compute_night_vol_filter(last_day, tonight_range):
    """Night vol filter (H075 升級版).

    方法：night_range / EMA20(night_range)，threshold = expanding median of historic norms。
    H066 原評估方法為 EMA + median split，本實作為其 causal 版本。
    Warmup 期（< 60 夜盤值）fallback 到 fixed 0.93。
    """
    import pandas as _pd

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY td
        """, [SYMBOL]).df()
        day_dates_list = sorted(_pd.to_datetime(day_dates_df["td"]).tolist())

        # Load all historical night data (needed for expanding median)
        night_raw = conn.execute("""
            SELECT timestamp, high, low
            FROM ohlcv_1m
            WHERE symbol = ?
              AND (timestamp::TIME >= '15:00:00' OR timestamp::TIME < '05:00:00')
              AND timestamp::DATE <= ?::DATE + INTERVAL '1 day'
            ORDER BY timestamp
        """, [SYMBOL, last_day]).df()

    if night_raw.empty:
        return None

    night_raw["timestamp"] = _pd.to_datetime(night_raw["timestamp"])

    # Vectorised find_next_trade_date (原本逐列 .apply 對全歷史夜盤 1 分 K 太慢)：
    # 夜盤(>=15:00) → 隔日(含)之後第一個交易日；凌晨(<05:00) → 該日(含)之後第一個交易日。
    # np.searchsorted side='left' 等價於 bisect_left，輸出與原版完全一致。
    day_arr = np.array(day_dates_list, dtype="datetime64[ns]")
    ts = night_raw["timestamp"]
    search = ts.dt.normalize().mask(ts.dt.hour >= 15, (ts + _pd.Timedelta(days=1)).dt.normalize())
    idx = np.searchsorted(day_arr, search.values, side="left")
    valid = idx < len(day_arr)
    night_raw["trade_date"] = _pd.Series(
        np.where(valid, day_arr[np.where(valid, idx, 0)], np.datetime64("NaT")),
        index=night_raw.index,
    )
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        n_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["n_bars"] >= 100]
    night = night[night.index <= _pd.Timestamp(last_day)]
    night = night.sort_index()

    if len(night) < 20:
        return None

    # EMA20 of historical night_range (with adjust=False to match H066/H067 explore.py)
    night["ema20"] = night["night_range"].ewm(span=20, adjust=False).mean()
    ema20_today = float(night["ema20"].iloc[-1])
    if ema20_today <= 0:
        return None
    night["norm_ema"] = night["night_range"] / night["ema20"]

    # tonight_norm uses today's EMA20 (the most recent value)
    night_norm = tonight_range / ema20_today

    # Expanding median of historic norms (causal: exclude today implicitly since
    # tonight_range hasn't been added to the EMA series — historic nights only)
    historic_norms = night["norm_ema"].dropna()
    if len(historic_norms) >= _NVF_MIN_HISTORY_NIGHTS:
        threshold = float(historic_norms.median())
        method = "EMA + expanding median"
    else:
        threshold = _NVF_FALLBACK_THRESHOLD
        method = f"EMA + fallback {_NVF_FALLBACK_THRESHOLD} (warmup, only {len(historic_norms)} nights)"

    return {
        "night_range": tonight_range,
        "ema20": round(ema20_today),
        "night_norm": round(night_norm, 3),
        "threshold": round(threshold, 3),
        "pass": night_norm >= threshold,
        "tier": _classify_nvf_tier(night_norm),
        "method": method,
    }


def _ema_series(arr, period):
    """逐點 EMA（adjust=False，種子=首值），回傳同長度 float 陣列。"""
    arr = np.asarray(arr, dtype=float)
    out = np.full_like(arr, np.nan)
    if len(arr) == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def _compute_1h_macd(closes, fast=12, slow=26, signal=9):
    """1H MACD(12,26,9)。回傳最新 macd / signal / hist 與方向（hist>=0 為多）。"""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < slow:
        return None
    macd_line = _ema_series(closes, fast) - _ema_series(closes, slow)
    signal_line = _ema_series(macd_line, signal)
    hist = macd_line - signal_line
    return {
        "macd": float(macd_line[-1]),
        "signal": float(signal_line[-1]),
        "hist": float(hist[-1]),
        "up": bool(hist[-1] >= 0),
    }


def get_key_prices():
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 最新有日盤資料的交易日（= 昨天）
        last_day = conn.execute("""
            SELECT MAX(timestamp::DATE)
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL]).fetchone()[0]

        # 日盤：昨高 / 昨低 / 收盤（from ohlcv_1m）
        day = conn.execute("""
            SELECT
                MAX(high)::INT,
                MIN(low)::INT,
                arg_max(close, timestamp)::INT
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL, last_day]).fetchone()

        # 夜盤：last_day 15:00 ~ (last_day+1) 05:00（from ticks，跨日，主力合約）
        next_day = last_day + timedelta(days=1)
        night = conn.execute("""
            WITH night_ticks AS (
                SELECT
                    contract,
                    price,
                    (trade_date::VARCHAR || ' ' || trade_time::VARCHAR)::TIMESTAMP AS ts
                FROM ticks
                WHERE symbol = ?
                  AND (
                    (trade_date = ? AND trade_time >= '15:00:00')
                    OR
                    (trade_date = ? AND trade_time <= '05:00:00')
                  )
            ),
            dominant AS (
                SELECT contract
                FROM night_ticks
                GROUP BY contract
                ORDER BY COUNT(*) DESC
                LIMIT 1
            )
            SELECT
                MAX(price)::INT,
                MIN(price)::INT,
                arg_max(price, ts)::INT
            FROM night_ticks
            WHERE contract = (SELECT contract FROM dominant)
        """, [SYMBOL, last_day, next_day]).fetchone()

        # 當日與前一日的成本（VWAP = sum(close*volume)/sum(volume)，日盤）
        prev_day = conn.execute("""
            SELECT MAX(timestamp::DATE)
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE < ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL, last_day]).fetchone()[0]

        vwap_rows = conn.execute("""
            SELECT
                timestamp::DATE AS date,
                ROUND(SUM(close * volume) / SUM(volume))::INT AS vwap
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE IN (?, ?)
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY date
            ORDER BY date DESC
        """, [SYMBOL, last_day, prev_day]).fetchall()

        vwap = {row[0]: row[1] for row in vwap_rows}

        # 前天 10點前 15分K 收盤（扣底值，08:45~09:59）
        bars_15m_pre10 = conn.execute("""
            WITH bars_15m AS (
                SELECT
                    time_bucket(INTERVAL '15 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') AS ts,
                    arg_max(close, timestamp)::INT AS close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '09:59:00'
                GROUP BY ts
            )
            SELECT MAX(close), MIN(close), ROUND(AVG(close))::INT
            FROM bars_15m
        """, [SYMBOL, prev_day]).fetchone()

        # 30分K 20MA（所有日盤，bucket 對齊 08:45）
        # 13:45 這根 1分K（日盤真實收盤）合併進 13:15 的 bucket
        ma_row = conn.execute("""
            WITH bars_30m AS (
                SELECT
                    CASE
                        WHEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                        THEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                        ELSE time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')
                    END AS ts,
                    arg_max(close, timestamp) AS close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                GROUP BY ts
            ),
            ma_calc AS (
                SELECT
                    ts,
                    AVG(close) OVER (
                        ORDER BY ts
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS ma20,
                    COUNT(*) OVER (
                        ORDER BY ts
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS window_size,
                    -- 扣底：最新 20MA 窗口中最舊那根 close（下一根 MA 將扣掉它）
                    LAG(close, 19) OVER (ORDER BY ts) AS deduct
                FROM bars_30m
            ),
            with_lag AS (
                SELECT
                    ts,
                    ma20,
                    window_size,
                    deduct,
                    LAG(ma20) OVER (ORDER BY ts) AS prev_ma20
                FROM ma_calc
            )
            SELECT
                ROUND(ma20)::INT AS ma20,
                ma20 > prev_ma20 AS is_up,
                ROUND(deduct)::INT AS deduct
            FROM with_lag
            WHERE window_size = 20
            ORDER BY ts DESC
            LIMIT 1
        """, [SYMBOL]).fetchone()

    has_night = night and night[0] is not None

    night_range = (night[0] - night[1]) if has_night else None

    # 夜盤波動濾網（H066/H067：night_range / SMA20(night_range) >= 0.85）
    # 適用 EstHL + Reversal
    night_vol_filter = None
    if night_range is not None:
        night_vol_filter = _compute_night_vol_filter(last_day, night_range)

    # Weekday 漲跌統計（近 ~40 個交易日 ≈ 2 個月）
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 日盤 + 早盤：from ohlcv_1m
        day_morning_rows = conn.execute("""
            WITH trading_days AS (
                SELECT DISTINCT timestamp::DATE AS td
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY td DESC
                LIMIT 40
            ),
            day_session AS (
                SELECT
                    timestamp::DATE AS td,
                    FIRST(open ORDER BY timestamp) AS day_open,
                    LAST(close ORDER BY timestamp) AS day_close,
                    MAX(high) AS day_high,
                    MIN(low) AS day_low
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (SELECT td FROM trading_days)
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                GROUP BY td
            ),
            morning_session AS (
                SELECT
                    timestamp::DATE AS td,
                    FIRST(open ORDER BY timestamp) AS morn_open,
                    LAST(close ORDER BY timestamp) AS morn_close,
                    MAX(high) AS morn_high,
                    MIN(low) AS morn_low
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (SELECT td FROM trading_days)
                  AND timestamp::TIME BETWEEN '09:00:00' AND '10:30:00'
                GROUP BY td
            )
            SELECT
                d.td,
                DAYOFWEEK(d.td) AS dow,
                d.day_open, d.day_close, d.day_high, d.day_low,
                m.morn_open, m.morn_close, m.morn_high, m.morn_low
            FROM day_session d
            LEFT JOIN morning_session m ON d.td = m.td
            ORDER BY d.td
        """, [SYMBOL, SYMBOL, SYMBOL]).fetchall()

        # 夜盤：15:00~隔日 05:00，以當日日期為基準
        night_rows = conn.execute("""
            WITH trading_days AS (
                SELECT DISTINCT timestamp::DATE AS td
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY td DESC
                LIMIT 40
            )
            SELECT
                td,
                DAYOFWEEK(td) AS dow,
                night_open,
                night_close,
                night_high,
                night_low
            FROM (
                SELECT
                    d.td,
                    FIRST(m.open ORDER BY m.timestamp) AS night_open,
                    LAST(m.close ORDER BY m.timestamp) AS night_close,
                    MAX(m.high) AS night_high,
                    MIN(m.low) AS night_low
                FROM trading_days d
                JOIN ohlcv_1m m ON m.symbol = ?
                  AND (
                    (m.timestamp::DATE = d.td AND m.timestamp::TIME >= '15:00:00')
                    OR
                    (m.timestamp::DATE = d.td + INTERVAL '1 day' AND m.timestamp::TIME <= '05:00:00')
                  )
                GROUP BY d.td
            ) sub
            WHERE night_open IS NOT NULL
            ORDER BY td
        """, [SYMBOL, SYMBOL]).fetchall()

    # 彙整 by weekday（DuckDB DAYOFWEEK: 0=Sun, 1=Mon, ... 6=Sat）
    # 轉成 Python weekday: 0=Mon, ... 4=Fri
    # 每筆紀錄：(close-open, high-low)
    wd_data = defaultdict(lambda: {
        "day": [], "morning": [], "night": []
    })
    for row in day_morning_rows:
        td, dow, day_open, day_close, day_high, day_low, morn_open, morn_close, morn_high, morn_low = row
        py_wd = (dow - 1) % 7  # DuckDB 1=Mon → Python 0=Mon
        if day_open is not None and day_close is not None:
            wd_data[py_wd]["day"].append(
                (float(day_close - day_open), float(day_high - day_low))
            )
        if morn_open is not None and morn_close is not None:
            wd_data[py_wd]["morning"].append(
                (float(morn_close - morn_open), float(morn_high - morn_low))
            )

    for row in night_rows:
        td, dow, night_open, night_close, night_high, night_low = row
        py_wd = (dow - 1) % 7
        if night_open is not None and night_close is not None:
            wd_data[py_wd]["night"].append(
                (float(night_close - night_open), float(night_high - night_low))
            )

    def _agg(items):
        if not items:
            return {"up": 0, "down": 0, "avg_chg": 0.0, "avg_range": 0.0}
        changes = [c for c, _ in items]
        ranges = [r for _, r in items]
        up = sum(1 for c in changes if c > 0)
        down = len(changes) - up
        avg_chg = sum(changes) / len(changes)
        avg_range = sum(ranges) / len(ranges)
        return {"up": up, "down": down,
                "avg_chg": float(round(avg_chg)),
                "avg_range": float(round(avg_range))}

    weekday_stats = {
        "today_wd": next_day.weekday(),  # next_day = 今天的交易日
        "stats": {
            wd: {
                "day": _agg(wd_data[wd]["day"]),
                "morning": _agg(wd_data[wd]["morning"]),
                "night": _agg(wd_data[wd]["night"]),
            }
            for wd in range(5)
        }
    }

    # 1H MACD 方向（因果：get_1h_bars 只到盤前可得的夜盤收盤）
    macd_1h = None
    bars_1h = get_1h_bars(20)
    if bars_1h:
        macd_1h = _compute_1h_macd([r[4] for r in bars_1h])

    result = {
        "last_day": last_day,
        "prev_day": prev_day,
        "day": {"high": day[0], "low": day[1], "close": day[2]},
        "night": {"high": night[0], "low": night[1], "close": night[2]} if has_night else None,
        "vwap": vwap,
        "ma30_20": ma_row[0] if ma_row else None,
        "ma30_20_up": ma_row[1] if ma_row else None,
        "ma30_20_deduct": ma_row[2] if ma_row else None,
        "macd_1h": macd_1h,
        "bars_15m_pre10": bars_15m_pre10,
        "night_vol_filter": night_vol_filter,
        "weekday_stats": weekday_stats,
    }
    return result



def print_report(data):
    d = data
    ld = d["last_day"]
    pd_ = d["prev_day"]
    night = d["night"]
    ma = d["ma30_20"]
    ref = night["close"] if night else None

    # ── helpers ──────────────────────────────────────────
    def n(v):
        return f"{v:,}" if v is not None else "—"

    def ud(price, benchmark):
        if price is None or benchmark is None:
            return "-"
        return "↑ up" if price > benchmark else "↓ down"

    # ── header ───────────────────────────────────────────
    ref_label = f"夜收 {ref:,}" if ref else "（無夜盤）"
    print(f"# 關鍵價格參考｜{ld}（昨）  基準：{ref_label}\n")

    # ── 昨日行情：日盤 vs 夜盤並排 ───────────────────────
    print("### 昨日行情")
    print(f"|      |    日盤 |    夜盤 |")
    print(f"|------|--------:|--------:|")
    print(f"| 高   | {n(d['day']['high'])} | {n(night['high'] if night else None)} |")
    print(f"| 低   | {n(d['day']['low'])}  | {n(night['low']  if night else None)} |")
    print(f"| 收盤 | {n(d['day']['close'])} | {n(night['close'] if night else None)} |")

    # ── 成本：昨 vs 前天並排 ─────────────────────────────
    vwap_last = d["vwap"].get(ld)
    vwap_prev = d["vwap"].get(pd_)

    print()
    print("### 成本")
    print(f"|          | 昨 {ld.strftime('%m/%d')} | 前天 {pd_.strftime('%m/%d')} |")
    print(f"|----------|--------:|----------:|")
    print(f"| VWAP     | {n(vwap_last)} | {n(vwap_prev)} |")

    # ── 趨勢 ─────────────────────────────────────────────
    ma_dir = ud(ref, ma)
    pre10 = d.get("bars_15m_pre10")

    print()
    print("### 趨勢")
    print(f"| 項目              | 數值   | 備註 |")
    print(f"|-------------------|-------:|------|")
    ma_str = n(ma)
    print(f"| 30分K 20MA        | {ma_str} | 方向 {ma_dir}，夜收 {n(ref)} |")
    if pre10 and pre10[0] is not None:
        h, l, avg = pre10
        print(f"| 前天10點前扣底    | {n(h)} / {n(l)} | 均 {n(avg)}（{pd_.strftime('%m/%d')}） |")

    # ── 評估 ─────────────────────────────────────────────
    if ref is not None:
        if ref > d["day"]["high"]:
            two_day = f"新高（昨高 {n(d['day']['high'])}）"
        elif ref < d["day"]["low"]:
            two_day = f"新低（昨低 {n(d['day']['low'])}）"
        else:
            two_day = "-"
    else:
        two_day = "-"

    if ref is not None and ma is not None:
        dist_pct = abs(ref - ma) / ma * 100
        risk = "高" if dist_pct < 0.3 else ("中" if dist_pct < 1.5 else "低")
        reversal_risk = f"{risk}（距 {dist_pct:.1f}%）"
    else:
        reversal_risk = "-"

    # 30分K 20MA 方向：扣抵法（夜收 vs 均線最新窗口扣底 → 預判均線轉向）
    ded = d.get("ma30_20_deduct")
    if ref is not None and ded is not None:
        ma_trend = f"{'↑ up' if ref > ded else '↓ down'}（夜收 {n(ref)} vs 扣底 {n(ded)}）"
    else:
        ma_trend = "-"

    print()
    print(f"### 評估")
    print(f"| 項目                      | 結果 |")
    print(f"|---------------------------|------|")
    print(f"| 夜收 vs 昨成本 {n(vwap_last)} | {ud(ref, vwap_last)} |")
    print(f"| 夜收 vs 前天成本 {n(vwap_prev)} | {ud(ref, vwap_prev)} |")
    print(f"| 二日高低突破              | {two_day} |")
    print(f"| 30分K 20MA 方向           | {ma_trend} |")
    print(f"| 均線轉向風險              | {reversal_risk} |")

    # 夜盤波動 — H092 4-tier 分類 + H075 binary STOP/GO 濾網
    nvf = d.get("night_vol_filter")
    if nvf and nvf.get("night_norm") is not None:
        norm = nvf["night_norm"]
        ema = nvf["ema20"]
        nr = nvf["night_range"]
        tier = nvf.get("tier", "?")
        tier_icon = _NVF_TIER_ICONS.get(tier, "")
        tier_hint = _NVF_TIER_HINTS.get(tier, "")
        print(f"| 夜盤波動 tier (H092)      | {tier_icon} **{tier}** (norm={norm:.2f}) — {tier_hint} |")

    # ── VIX regime（因果：盤前只有昨日 VIX;H117）────────────
    try:
        from src.analysis.vix_regime import get_regime, REACH_EXPECT, regime_note
        vr = get_regime()
        e = REACH_EXPECT[vr["regime"]]
        ex = " 🔥VIX≥35" if vr["extreme"] else ""
        print()
        print(f"### ladder regime（昨日資料 {vr['date']}，套用今日;組合 VIX+已實現）")
        print(f"| 項目 | 值 |")
        print(f"|------|------|")
        print(f"| VIX / MA20 | {vr['vix']} / {vr['ma20']}（{vr['level']}{ex}） |")
        print(f"| 方向 | VIX {vr['vix_dir']} / 已實現 {vr['rv_dir']} → **{vr['regime']}** |")
        print(f"| 深 reach 期望 | 多 L4≈{e['多L4']:.0%}/L5≈{e['多L5']:.0%}、空 L4≈{e['空L4']:.0%}/L5≈{e['空L5']:.0%}（全體~25%/12%） |")
        print(f"| 動作 | {regime_note(vr['regime'], vr['level'], vr['extreme'])} |")
    except Exception:
        pass

    # ── H103 跳空下方遠做多（觀察，H103 Inconclusive）───────
    try:
        from src.analysis.gapdown_revert_alert import compute_gapdown_revert_alert
        a = compute_gapdown_revert_alert()
        if a is not None:
            status = "🔴 預判觸發" if a["triggered"] else "⚪ 未觸發"
            print()
            print(f"### H103 跳空下方遠做多（觀察，非訊號）")
            print(f"| 項目 | 值 |")
            print(f"|------|------|")
            print(f"| 觸發價 X | {a['trigger']:.0f}（min成本 {a['cost']} − 1.0×ema20 {a['ema20']:.0f}） |")
            print(f"| 夜收預判開盤 | {n(a['ref_open'])} → {status} |")
            if a["triggered"]:
                print(f"| 進/目標/停損 | ≈{a['ref_open']} / {a['target']:.0f} / {a['stop']:.0f}（R:R 1.4） |")
            if a["night_ref"] is not None:
                print(f"| T4 參考(夜05:00收) | {n(a['night_ref'])}（開盤站上=較強變體） |")
    except Exception:
        pass

    # Weekday 漲跌統計
    wd_stats = d.get("weekday_stats")
    if wd_stats:
        wd_names = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五"}
        today_wd = wd_stats["today_wd"]

        def _fmt(s):
            total = s["up"] + s["down"]
            if total == 0:
                return "—"
            pct = s["up"] / total * 100
            sign = "+" if s["avg_chg"] >= 0 else ""
            return (f"{s['up']}漲/{s['down']}跌 {pct:.0f}% "
                    f"均{sign}{s['avg_chg']:.0f}pt (振幅{s['avg_range']:.0f})")

        print()
        print("### Weekday 漲跌統計（近 2 個月）")
        print()
        print("|      | 日盤 08:45-13:45 | 早盤 09:00-10:30 | 夜盤 15:00-05:00 |")
        print("|------|------------------|------------------|------------------|")
        for wd in range(5):
            s = wd_stats["stats"][wd]
            marker = " ◀" if wd == today_wd else ""
            label = f"週{wd_names[wd]}{marker}"
            print(f"| {label:4s} | {_fmt(s['day']):16s} | {_fmt(s['morning']):16s} | {_fmt(s['night']):16s} |")

    # ── 方向加分（多空計分）─────────────────────────────
    rows = []  # (label, reading, side)  side ∈ {'long','short','neutral'}

    # 1) 1-hr MACD 方向（hist>=0 為多）
    macd = d.get("macd_1h")
    if macd:
        side = "long" if macd["up"] else "short"
        rows.append(("1-hr MACD 方向",
                     f"{'↑ up' if macd['up'] else '↓ down'}（hist {macd['hist']:+.0f}）", side))

    # 2) 30分K 20MA 方向（夜盤收 vs 均線扣底 → 預判均線轉向）
    ded = d.get("ma30_20_deduct")
    if ref is not None and ded is not None:
        up = ref > ded
        rows.append(("30分K 20MA 方向",
                     f"{'↑ up' if up else '↓ down'}（夜收 {n(ref)} {'>' if up else '<'} 扣底 {n(ded)}）",
                     "long" if up else "short"))

    # 3) 週幾早盤勝率
    ws = d.get("weekday_stats")
    if ws:
        wd_names = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五"}
        twd = ws["today_wd"]
        m = ws["stats"][twd]["morning"]
        tot = m["up"] + m["down"]
        if tot:
            pct = m["up"] / tot * 100
            side = "long" if pct > 50 else ("short" if pct < 50 else "neutral")
            rows.append((f"週{wd_names[twd]} 早盤勝率",
                         f"{m['up']}漲/{m['down']}跌 {pct:.0f}%", side))

    # 4) 夜盤位置 vs 昨/前成本（優先二日突破，其次昨成本）
    if ref is not None:
        dh, dl = d["day"]["high"], d["day"]["low"]
        if ref > dh:
            side, txt = "long", f"創二日新高（>{n(dh)}）"
        elif ref < dl:
            side, txt = "short", f"創二日新低（<{n(dl)}）"
        elif vwap_last is not None and ref > vwap_last:
            side, txt = "long", f"昨成本之上（>{n(vwap_last)}）"
        elif vwap_last is not None and ref < vwap_last:
            side, txt = "short", f"昨成本之下（<{n(vwap_last)}）"
        else:
            side, txt = "neutral", "貼近昨成本"
        rows.append(("夜盤位置 vs 昨/前成本", txt, side))

    if rows:
        longs = sum(1 for _, _, s in rows if s == "long")
        shorts = sum(1 for _, _, s in rows if s == "short")
        if longs > shorts:
            verdict = f"偏多（多 {longs} / 空 {shorts}）"
        elif shorts > longs:
            verdict = f"偏空（空 {shorts} / 多 {longs}）"
        else:
            verdict = f"中性（多 {longs} / 空 {shorts}）"
        print()
        print("### 方向加分（多空計分）")
        print("| 依據 | 多方 | 空方 | 今日讀數 |")
        print("|------|:--:|:--:|------|")
        for label, txt, side in rows:
            lm = "🟥" if side == "long" else ""
            sm = "🟩" if side == "short" else ""
            print(f"| {label} | {lm} | {sm} | {txt} |")
        print(f"\n**合計：{verdict}**")


def get_30m_bars(n_days=20):
    """取近 n_days 個交易日的日盤 30 分K（08:45~13:45，含 MA20 所需歷史）。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        rows = conn.execute("""
            WITH last_day AS (
                SELECT MAX(timestamp::DATE) AS d
                FROM ohlcv_1m WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ),
            bars_30m AS (
                SELECT
                    CASE
                        WHEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                        THEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                        ELSE time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')
                    END AS ts,
                    FIRST(open  ORDER BY timestamp) AS open,
                    MAX(high)                        AS high,
                    MIN(low)                         AS low,
                    LAST(close ORDER BY timestamp)   AS close,
                    SUM(volume)                      AS volume
                FROM ohlcv_1m, last_day
                WHERE symbol = ?
                  AND timestamp::DATE >= (SELECT d FROM last_day) - (? * 2) * INTERVAL '1 day'
                  AND timestamp::DATE <= (SELECT d FROM last_day)
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                GROUP BY ts
            )
            SELECT ts, open, high, low, close, volume
            FROM bars_30m
            ORDER BY ts
        """, [SYMBOL, SYMBOL, n_days]).fetchall()
    return rows


def get_1h_bars(n_days=20):
    """取近 n_days 個交易日的 1 小時 K（日盤 + 夜盤），連續排列（去除無交易空檔）。"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        rows = conn.execute("""
            WITH last_day AS (
                SELECT MAX(timestamp::DATE) AS d
                FROM ohlcv_1m WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ),
            recent AS (
                SELECT timestamp::DATE AS td
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                  AND timestamp::DATE >= (SELECT d FROM last_day) - (? * 2) * INTERVAL '1 day'
                GROUP BY td
                ORDER BY td
            ),
            bounds AS (
                SELECT MIN(td) AS start_d, (SELECT d FROM last_day) AS end_d FROM recent
            ),
            bars AS (
                SELECT
                    time_bucket(INTERVAL '1 hour', timestamp) AS ts,
                    FIRST(open  ORDER BY timestamp) AS open,
                    MAX(high)                        AS high,
                    MIN(low)                         AS low,
                    LAST(close ORDER BY timestamp)   AS close,
                    SUM(volume)                      AS volume
                FROM ohlcv_1m, bounds
                WHERE symbol = ?
                  AND (
                      -- 日盤 + 夜盤前半（當日 15:00~23:59）
                      (timestamp::DATE BETWEEN start_d AND end_d
                       AND (timestamp::TIME BETWEEN '08:00:00' AND '13:59:00'
                            OR timestamp::TIME >= '15:00:00'))
                      OR
                      -- 夜盤後半：隔日 00:00~05:00（timestamp::DATE = end_d + 1）
                      (timestamp::DATE = end_d + INTERVAL '1 day'
                       AND timestamp::TIME < '05:01:00')
                  )
                GROUP BY ts
            )
            SELECT ts, open, high, low, close, volume
            FROM bars
            ORDER BY ts
        """, [SYMBOL, SYMBOL, n_days, SYMBOL]).fetchall()
    return rows  # list of (ts, open, high, low, close, volume)


def _setup_font():
    apply_style()


def plot_sr_chart(data, n_days=20):
    """畫 1 小時 K 線 + 支撐壓力 + Volume Profile，存 PNG 並複製到剪貼簿。"""
    import subprocess

    bars = get_1h_bars(n_days)
    if not bars:
        print("[WARN] 無 K 線資料，跳過圖表")
        return

    ts_list   = [r[0] for r in bars]
    opens     = np.array([float(r[1]) for r in bars])
    highs     = np.array([float(r[2]) for r in bars])
    lows      = np.array([float(r[3]) for r in bars])
    closes    = np.array([float(r[4]) for r in bars])
    volumes   = np.array([float(r[5]) for r in bars])
    n = len(bars)
    x = np.arange(n)

    ref    = (data["night"] or {}).get("close") or data["day"]["close"]

    # ── MACD (12, 26, 9) ─────────────────────────────────
    macd_line = _ema_series(closes, 12) - _ema_series(closes, 26)
    signal_line = _ema_series(macd_line, 9)
    macd_hist = macd_line - signal_line

    _setup_font()
    fig = plt.figure(figsize=(16, 12), layout="constrained")
    gs = fig.add_gridspec(3, 2, height_ratios=[3, 1, 0.9], width_ratios=[5, 1],
                          hspace=0.08)
    ax     = fig.add_subplot(gs[0, 0])
    ax_vp  = fig.add_subplot(gs[0, 1], sharey=ax)
    ax_macd = fig.add_subplot(gs[1, 0], sharex=ax)
    ax_empty = fig.add_subplot(gs[1, 1])
    ax_empty.set_visible(False)
    ax_table = fig.add_subplot(gs[2, :])

    fig.patch.set_facecolor(BG_FIG)
    for a in (ax, ax_vp, ax_macd, ax_table):
        style_axes(a)

    # ── K 線 ──────────────────────────────────────────────
    W = 0.4
    for i in range(n):
        bull = closes[i] >= opens[i]
        color = COLOR_UP if bull else COLOR_DOWN
        body_lo = min(opens[i], closes[i])
        body_hi = max(opens[i], closes[i])
        ax.add_patch(mpatches.Rectangle(
            (i - W, body_lo), 2 * W, max(body_hi - body_lo, 1),
            color=color, zorder=3,
        ))
        ax.plot([i, i], [lows[i], body_lo], color=color, linewidth=0.8, zorder=2)
        ax.plot([i, i], [body_hi, highs[i]], color=color, linewidth=0.8, zorder=2)

    # ── 均線 5/21/65/130/233 ──────────────────────────────
    ma_periods = [5, 21, 65, 130, 233]
    ma_colors  = [COLOR_UP, COLOR_ACCENT_GOLD, COLOR_DOWN, COLOR_ACCENT_BLUE, COLOR_ACCENT_PURPLE]
    for period, mc in zip(ma_periods, ma_colors):
        if n >= period:
            ma = np.full(n, np.nan)
            for i in range(period - 1, n):
                ma[i] = closes[i - period + 1:i + 1].mean()
            valid = ~np.isnan(ma)
            ax.plot(x[valid], ma[valid], color=mc, linewidth=1.0, alpha=0.8,
                    label=f"MA{period}", zorder=4)

    # 現價基準線
    ax.axhline(ref, color=COLOR_TEXT, linewidth=1, linestyle=":", alpha=0.5, zorder=4)
    ax.text(0, ref, f" 基準 {ref:,}", color=COLOR_TEXT, fontsize=8, va="bottom", zorder=5)

    # ── X 軸標籤（每日第一根 08:xx bar 標日期）────────────
    tick_pos, tick_lbl = [], []
    prev_date = None
    for i, ts in enumerate(ts_list):
        d = ts.date()
        if d != prev_date:
            tick_pos.append(i)
            tick_lbl.append(d.strftime("%m/%d"))
            prev_date = d
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8)
    ax.set_xlim(-1, n)
    ax.set_title(
        f"TX 1H K線（近 {n_days} 日，基準 {ref:,}）",
        color=COLOR_TEXT, fontsize=12, pad=8, loc="left",
    )
    ax.legend(loc="upper left", fontsize=7, facecolor=BG_FIG,
              labelcolor=COLOR_TEXT, edgecolor=COLOR_GRID, ncol=5)

    # ── Volume Profile（右側）────────────────────────────
    bin_size = 50
    price_min = int(lows.min() // bin_size * bin_size)
    price_max = int(highs.max() // bin_size * bin_size + bin_size)
    bins = np.arange(price_min, price_max + bin_size, bin_size)
    vp_hist = np.zeros(len(bins))
    for i in range(n):
        lo, hi, vol = lows[i], highs[i], volumes[i]
        idx = [j for j, b in enumerate(bins) if b < hi and b + bin_size > lo]
        if idx:
            per = vol / len(idx)
            for j in idx:
                vp_hist[j] += per

    ax_vp.barh(
        bins + bin_size / 2, vp_hist,
        height=bin_size * 0.9,
        color=COLOR_ACCENT_GOLD, alpha=0.5,
    )
    ax_vp.axhline(ref, color=COLOR_TEXT, linewidth=1, linestyle=":", alpha=0.5)
    ax_vp.set_xlabel("Volume", fontsize=8)
    ax_vp.set_title("VP", fontsize=10)
    ax_vp.xaxis.set_tick_params(labelsize=7)

    # 在所有繪圖完成後才設定 ylim，避免被 barh 自動縮放覆蓋（sharey=True）
    price_range = highs.max() - lows.min()
    ax.set_ylim(lows.min() - price_range * 0.05, highs.max() + price_range * 0.1)

    # ── MACD 子圖 ──────────────────────────────────────
    hist_colors = [COLOR_UP if v >= 0 else COLOR_DOWN for v in macd_hist]
    ax_macd.bar(x, macd_hist, color=hist_colors, width=0.6, alpha=0.7, zorder=2)
    ax_macd.plot(x, macd_line, color=COLOR_ACCENT_BLUE, linewidth=1.2, label="MACD", zorder=3)
    ax_macd.plot(x, signal_line, color=COLOR_ACCENT_ORANGE, linewidth=1.2, label="Signal", zorder=3)
    ax_macd.axhline(0, color=COLOR_TEXT_MUTED, linewidth=0.5, zorder=1)
    ax_macd.set_title("MACD (12, 26, 9)", fontsize=10, pad=4)
    ax_macd.legend(loc="upper left", fontsize=8, facecolor=BG_FIG,
                   labelcolor=COLOR_TEXT, edgecolor=COLOR_GRID)
    ax.tick_params(labelbottom=False)
    ax_macd.set_xticks(tick_pos)
    ax_macd.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8)

    # ── Weekday 統計表格（底部）──────────────────────────
    ax_table.set_xlim(0, 1)
    ax_table.set_ylim(0, 1)
    ax_table.axis("off")

    wd_stats = data.get("weekday_stats")
    if wd_stats:
        wd_names = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五"}
        today_wd = wd_stats["today_wd"]

        def _fmt_cell(s):
            total = s["up"] + s["down"]
            if total == 0:
                return "—", COLOR_TEXT_MUTED
            pct = s["up"] / total * 100
            sign = "+" if s["avg_chg"] >= 0 else ""
            text = (f"{s['up']}漲/{s['down']}跌 {pct:.0f}% "
                    f"均{sign}{s['avg_chg']:.0f}pt (振幅{s['avg_range']:.0f})")
            if pct > 50 and s["avg_chg"] > 0:
                color = COLOR_UP
            elif pct < 50 and s["avg_chg"] < 0:
                color = COLOR_DOWN
            else:
                color = COLOR_TEXT_LIGHT
            return text, color

        col_labels = ["", "日盤 08:45-13:45", "早盤 09:00-10:30", "夜盤 15:00-05:00"]
        cell_text = []
        for wd in range(5):
            s = wd_stats["stats"][wd]
            marker = " ◀" if wd == today_wd else ""
            row_label = f"週{wd_names[wd]}{marker}"
            day_txt, _ = _fmt_cell(s["day"])
            morn_txt, _ = _fmt_cell(s["morning"])
            night_txt, _ = _fmt_cell(s["night"])
            cell_text.append([row_label, day_txt, morn_txt, night_txt])

        table = ax_table.table(
            cellText=cell_text,
            colLabels=col_labels,
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(11)

        # 找出今日高亮列（1-based，header=0）
        highlight_row = today_wd + 1
        style_table(table, 5, highlight_row=highlight_row)

        # 覆寫文字色（根據漲跌方向上色）
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                continue
            if col == 0:
                cell.set_text_props(color=COLOR_TEXT, fontweight="bold")
            else:
                s_key = ["day", "morning", "night"][col - 1]
                s = wd_stats["stats"][row - 1][s_key]
                total = s["up"] + s["down"]
                if total > 0:
                    pct = s["up"] / total * 100
                    if pct > 50 and s["avg_chg"] > 0:
                        clr = COLOR_UP
                    elif pct < 50 and s["avg_chg"] < 0:
                        clr = COLOR_DOWN
                    else:
                        clr = COLOR_TEXT_LIGHT
                else:
                    clr = COLOR_TEXT_MUTED
                cell.set_text_props(color=clr, fontweight="bold")

        table.scale(1, 1.8)
        ax_table.set_title(
            "Weekday 漲跌統計（近 2 個月）",
            color=COLOR_TEXT, fontsize=10, pad=20,
        )

    out_path = Path(__file__).parents[2] / "output" / "sr_chart.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor=BG_FIG)
    print(f"圖表已儲存：{out_path}")

    try:
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{out_path.absolute()}") as «class PNGf»)'],
            check=True, capture_output=True,
        )
        print("已複製到剪貼簿")
    except Exception:
        pass

    plt.show()


def plot_30m_chart(data, n_days=20):
    """畫日盤 30 分K + 20MA + VWAP（昨、前天），存 PNG 並複製到剪貼簿。"""
    import subprocess

    bars = get_30m_bars(n_days)
    if not bars:
        print("[WARN] 無 30 分 K 資料，跳過圖表")
        return

    ts_list = [r[0] for r in bars]
    opens   = np.array([float(r[1]) for r in bars])
    highs   = np.array([float(r[2]) for r in bars])
    lows    = np.array([float(r[3]) for r in bars])
    closes  = np.array([float(r[4]) for r in bars])
    n = len(bars)

    # 20MA
    ma20 = np.full(n, np.nan)
    for i in range(19, n):
        ma20[i] = closes[i-19:i+1].mean()

    # 只顯示最後 n_days 個交易日的 bar（前面的是 MA 預熱期）
    # 找最後 n_days 個不同日期
    dates_seen = []
    for ts in ts_list:
        d = ts.date()
        if not dates_seen or dates_seen[-1] != d:
            dates_seen.append(d)
    cutoff_date = dates_seen[-n_days] if len(dates_seen) >= n_days else dates_seen[0]
    display_mask = [ts.date() >= cutoff_date for ts in ts_list]
    display_idx  = [i for i, m in enumerate(display_mask) if m]

    x_disp = np.arange(len(display_idx))
    opens_d  = opens[display_idx]
    highs_d  = highs[display_idx]
    lows_d   = lows[display_idx]
    closes_d = closes[display_idx]
    ma20_d   = ma20[display_idx]
    ts_disp  = [ts_list[i] for i in display_idx]

    # VWAP
    vwap      = data.get("vwap", {})
    last_day  = data["last_day"]
    prev_day  = data["prev_day"]
    vwap_last = vwap.get(last_day)
    vwap_prev = vwap.get(prev_day)

    _setup_font()
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor(BG_FIG)
    style_axes(ax)

    # K 線
    W = 0.4
    nd = len(display_idx)
    for i in range(nd):
        bull = closes_d[i] >= opens_d[i]
        color = COLOR_UP if bull else COLOR_DOWN
        body_lo = min(opens_d[i], closes_d[i])
        body_hi = max(opens_d[i], closes_d[i])
        ax.add_patch(mpatches.Rectangle(
            (i - W, body_lo), 2 * W, max(body_hi - body_lo, 1),
            color=color, zorder=3,
        ))
        ax.plot([i, i], [lows_d[i], body_lo], color=color, linewidth=0.8, zorder=2)
        ax.plot([i, i], [body_hi, highs_d[i]], color=color, linewidth=0.8, zorder=2)

    # 20MA
    valid = ~np.isnan(ma20_d)
    if valid.any():
        ax.plot(x_disp[valid], ma20_d[valid], color=COLOR_ACCENT_GOLD, linewidth=1.5,
                label="20MA", zorder=4)

    # VWAP 水平線
    if vwap_last is not None:
        ax.axhline(vwap_last, color=COLOR_ACCENT_ORANGE, linewidth=1.5, linestyle="-.", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, vwap_last, f" 昨VWAP {vwap_last:,} ({last_day.strftime('%m/%d')})",
                color=COLOR_ACCENT_ORANGE, fontsize=8, va="bottom", zorder=6)
    if vwap_prev is not None:
        ax.axhline(vwap_prev, color=COLOR_ACCENT_PURPLE, linewidth=1.5, linestyle="-.", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, vwap_prev, f" 前天VWAP {vwap_prev:,} ({prev_day.strftime('%m/%d')})",
                color=COLOR_ACCENT_PURPLE, fontsize=8, va="bottom", zorder=6)

    # 夜盤收盤線
    night = data.get("night")
    night_close = night.get("close") if night else None
    if night_close is not None:
        ax.axhline(night_close, color=COLOR_ACCENT_TEAL, linewidth=1.5, linestyle="--", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, night_close, f" 夜收 {night_close:,}",
                color=COLOR_ACCENT_TEAL, fontsize=8, va="bottom", zorder=6)

    # X 軸：每日第一根標日期
    tick_pos, tick_lbl = [], []
    prev_date = None
    for i, ts in enumerate(ts_disp):
        d = ts.date()
        if d != prev_date:
            tick_pos.append(i)
            tick_lbl.append(d.strftime("%m/%d"))
            prev_date = d
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8)
    ax.set_xlim(-1, nd)
    price_range = highs_d.max() - lows_d.min()
    ax.set_ylim(lows_d.min() - price_range * 0.05, highs_d.max() + price_range * 0.1)
    ax.set_title(
        f"TX 日盤 30 分K + 20MA（近 {n_days} 日）",
        color=COLOR_TEXT, fontsize=12, pad=8,
    )
    ax.legend(loc="upper left", fontsize=9, facecolor=BG_FIG,
              labelcolor=COLOR_TEXT, edgecolor=COLOR_GRID)

    plt.tight_layout()
    out_path = Path(__file__).parents[2] / "output" / "30m_chart.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor=BG_FIG)
    print(f"30 分 K 圖表已儲存：{out_path}")

    try:
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{out_path.absolute()}") as «class PNGf»)'],
            check=True, capture_output=True,
        )
    except Exception:
        pass

    plt.show()


if __name__ == "__main__":
    import io
    import subprocess

    data = get_key_prices()

    # Capture output
    buf = io.StringIO()
    import sys
    _stdout = sys.stdout
    sys.stdout = buf
    print_report(data)
    sys.stdout = _stdout
    output = buf.getvalue()

    print(output, end="")

    # Copy text to clipboard (macOS)
    try:
        subprocess.run(["pbcopy"], input=output.encode(), check=True)
        print("\n已複製到剪貼簿，可直接 Cmd+V 貼上")
    except Exception:
        pass

    plot_sr_chart(data)
    plot_30m_chart(data)

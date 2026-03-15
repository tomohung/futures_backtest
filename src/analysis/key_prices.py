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
from datetime import timedelta
from pathlib import Path
from scipy.signal import find_peaks

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"


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

        # 大戶成本：1分K volume >= 20MA(volume) 的 bar 才計入，再算 VWAP
        big_rows = conn.execute("""
            WITH vol_ma AS (
                SELECT
                    timestamp::DATE AS date,
                    timestamp,
                    close,
                    volume,
                    AVG(volume) OVER (
                        PARTITION BY timestamp::DATE
                        ORDER BY timestamp
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS ma20_vol
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (?, ?)
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ),
            filtered AS (
                SELECT date, close, volume
                FROM vol_ma
                WHERE volume >= ma20_vol
            )
            SELECT
                date,
                ROUND(SUM(close * volume) / SUM(volume))::INT AS big_cost
            FROM filtered
            GROUP BY date
            ORDER BY date DESC
        """, [SYMBOL, last_day, prev_day]).fetchall()

        big_cost = {row[0]: row[1] for row in big_rows}

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
                    ) AS window_size
                FROM bars_30m
            ),
            with_lag AS (
                SELECT
                    ts,
                    ma20,
                    window_size,
                    LAG(ma20) OVER (ORDER BY ts) AS prev_ma20
                FROM ma_calc
            )
            SELECT
                ROUND(ma20)::INT AS ma20,
                ma20 > prev_ma20 AS is_up
            FROM with_lag
            WHERE window_size = 20
            ORDER BY ts DESC
            LIMIT 1
        """, [SYMBOL]).fetchone()

    has_night = night and night[0] is not None
    result = {
        "last_day": last_day,
        "prev_day": prev_day,
        "day": {"high": day[0], "low": day[1], "close": day[2]},
        "night": {"high": night[0], "low": night[1], "close": night[2]} if has_night else None,
        "vwap": vwap,
        "big_cost": big_cost,
        "ma30_20": ma_row[0] if ma_row else None,
        "ma30_20_up": ma_row[1] if ma_row else None,
        "bars_15m_pre10": bars_15m_pre10,
    }
    result["sr"] = _calc_sr(SYMBOL)
    return result


def _calc_sr(symbol, lookback_days=30, bin_size=50, swing_window=3, cluster_dist=100):
    """計算支撐壓力：① Swing High/Low 聚類  ② Volume Profile HVN"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        bars = conn.execute("""
        WITH bars_30m AS (
            SELECT
                CASE
                    WHEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                    THEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                    ELSE time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')
                END AS ts,
                MAX(high)::INT AS high,
                MIN(low)::INT  AS low,
                SUM(volume)    AS volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE >= (SELECT MAX(timestamp::DATE) FROM ohlcv_1m WHERE symbol=?) - ? * INTERVAL '1 day'
            GROUP BY ts
        )
        SELECT high, low, volume FROM bars_30m ORDER BY ts
    """, [symbol, symbol, lookback_days]).fetchall()

    if not bars:
        return {"swing": [], "vp": []}

    highs = np.array([r[0] for r in bars], dtype=float)
    lows  = np.array([r[1] for r in bars], dtype=float)
    vols  = np.array([r[2] for r in bars], dtype=float)
    n = len(bars)

    # ① Swing High/Low 聚類
    swing_highs, swing_lows = [], []
    for i in range(swing_window, n - swing_window):
        if highs[i] == max(highs[i-swing_window:i+swing_window+1]):
            swing_highs.append(float(highs[i]))
        if lows[i] == min(lows[i-swing_window:i+swing_window+1]):
            swing_lows.append(float(lows[i]))

    def cluster(levels):
        if not levels:
            return []
        levels = sorted(levels)
        groups = [[levels[0]]]
        for lv in levels[1:]:
            if lv - groups[-1][-1] <= cluster_dist:
                groups[-1].append(lv)
            else:
                groups.append([lv])
        return [(round(np.mean(g)), len(g)) for g in groups]

    swing_res = {"highs": cluster(swing_highs), "lows": cluster(swing_lows)}

    # ② Volume Profile HVN
    price_min = int(min(lows) // bin_size * bin_size)
    price_max = int(max(highs) // bin_size * bin_size + bin_size)
    bins = np.arange(price_min, price_max + bin_size, bin_size)
    vp = np.zeros(len(bins))

    for i in range(n):
        lo, hi, vol = lows[i], highs[i], vols[i]
        idx = [j for j, b in enumerate(bins) if b < hi and b + bin_size > lo]
        if idx:
            per = vol / len(idx)
            for j in idx:
                vp[j] += per

    peaks, props = find_peaks(vp, prominence=vp.max() * 0.1, distance=2)
    max_v = vp.max() if vp.max() > 0 else 1
    vp_res = sorted(
        [(int(bins[p]), int(bins[p] + bin_size), vp[p], props["prominences"][i])
         for i, p in enumerate(peaks)],
        key=lambda x: -x[2]
    )

    return {"swing": swing_res, "vp": vp_res, "vp_max": max_v}


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
    big_last  = d["big_cost"].get(ld)
    big_prev  = d["big_cost"].get(pd_)

    print()
    print("### 成本")
    print(f"|               | 昨 {ld.strftime('%m/%d')} | 前天 {pd_.strftime('%m/%d')} |")
    print(f"|---------------|--------:|----------:|")
    print(f"| 平均成本 VWAP | {n(vwap_last)} | {n(vwap_prev)} |")
    print(f"| 大戶成本      | {n(big_last)}  | {n(big_prev)}  |")

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

    print()
    print(f"### 評估")
    print(f"| 項目                      | 結果 |")
    print(f"|---------------------------|------|")
    print(f"| 夜收 vs 昨成本 {n(vwap_last)} | {ud(ref, vwap_last)} |")
    print(f"| 夜收 vs 前天成本 {n(vwap_prev)} | {ud(ref, vwap_prev)} |")
    print(f"| 二日高低突破              | {two_day} |")
    print(f"| 30分K 20MA 方向           | {ma_dir} |")
    print(f"| 均線轉向風險              | {reversal_risk} |")

    # 支撐壓力
    sr = d.get("sr", {})
    ref_price = ref if ref is not None else d["day"]["close"]
    RANGE = 1500

    swing_highs = sorted(
        [(p, c) for p, c in sr.get("swing", {}).get("highs", []) if ref_price < p <= ref_price + RANGE],
        key=lambda x: x[0]
    )
    swing_lows = sorted(
        [(p, c) for p, c in sr.get("swing", {}).get("lows", []) if ref_price - RANGE <= p < ref_price],
        key=lambda x: -x[0]
    )
    vp_max = sr.get("vp_max", 1)
    vp_res = sr.get("vp", [])
    vp_above = sorted(
        [(lo, hi, v) for lo, hi, v, _ in vp_res if lo >= ref_price - 25 and lo < ref_price + RANGE],
        key=lambda x: x[0]
    )
    vp_below = sorted(
        [(lo, hi, v) for lo, hi, v, _ in vp_res if hi <= ref_price + 25 and hi > ref_price - RANGE],
        key=lambda x: -x[0]
    )

    def vol_bar(v): return '█' * max(1, int(v / vp_max * 10))

    print()
    print(f"### 支撐壓力（近 30 日，±{RANGE}pt，基準 {ref_price:,}）")

    print()
    print("#### 壓力")
    print("| 價位 | Swing | VP 量 |")
    print("|------|-------|-------|")
    all_res_prices = sorted(set(
        [p for p, _ in swing_highs] +
        [lo + 25 for lo, hi, v in vp_above]  # 用 mid 代表
    ))
    # 合併顯示：以 swing 為主，VP 對照
    for p, cnt in sorted(swing_highs, key=lambda x: x[0]):
        vp_match = next(((lo, hi, v) for lo, hi, v in vp_above if lo <= p <= hi), None)
        vp_str = f"{int(vp_match[2]):,} {vol_bar(vp_match[2])}" if vp_match else "—"
        print(f"| {p:,} | {'★'*cnt} | {vp_str} |")
    # VP only（沒有 swing 對應）
    for lo, hi, v in vp_above:
        if not any(lo <= p <= hi for p, _ in swing_highs):
            print(f"| {lo:,}~{hi:,} | — | {int(v):,} {vol_bar(v)} |")

    print()
    print("#### 支撐")
    print("| 價位 | Swing | VP 量 |")
    print("|------|-------|-------|")
    for p, cnt in sorted(swing_lows, key=lambda x: -x[0]):
        vp_match = next(((lo, hi, v) for lo, hi, v in vp_below if lo <= p <= hi), None)
        vp_str = f"{int(vp_match[2]):,} {vol_bar(vp_match[2])}" if vp_match else "—"
        print(f"| {p:,} | {'★'*cnt} | {vp_str} |")
    for lo, hi, v in vp_below:
        if not any(lo <= p <= hi for p, _ in swing_lows):
            print(f"| {lo:,}~{hi:,} | — | {int(v):,} {vol_bar(v)} |")


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
    for f in [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
    ]:
        if Path(f).exists():
            fp = fm.FontProperties(fname=f)
            plt.rcParams["font.family"] = fp.get_name()
            return


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

    sr     = data.get("sr", {})
    ref    = (data["night"] or {}).get("close") or data["day"]["close"]
    RANGE  = 1500

    swing_highs = [(p, c) for p, c in sr.get("swing", {}).get("highs", [])
                   if ref < p <= ref + RANGE]
    swing_lows  = [(p, c) for p, c in sr.get("swing", {}).get("lows", [])
                   if ref - RANGE <= p < ref]
    vp_res  = sr.get("vp", [])
    vp_max  = sr.get("vp_max", 1) or 1
    vp_above = [(lo, hi, v) for lo, hi, v, _ in vp_res
                if lo < ref + RANGE and hi > ref - 25]
    vp_below = [(lo, hi, v) for lo, hi, v, _ in vp_res
                if hi > ref - RANGE and lo < ref + 25]

    _setup_font()
    fig, (ax, ax_vp) = plt.subplots(
        1, 2, figsize=(16, 8),
        gridspec_kw={"width_ratios": [5, 1]},
        sharey=True,
    )
    fig.patch.set_facecolor("#1a1a2e")
    for a in (ax, ax_vp):
        a.set_facecolor("#16213e")
        a.tick_params(colors="#cccccc")
        for spine in a.spines.values():
            spine.set_edgecolor("#444466")

    # ── K 線 ──────────────────────────────────────────────
    W = 0.4
    for i in range(n):
        bull = closes[i] >= opens[i]
        color = "#ef5350" if bull else "#26a69a"
        body_lo = min(opens[i], closes[i])
        body_hi = max(opens[i], closes[i])
        ax.add_patch(mpatches.Rectangle(
            (i - W, body_lo), 2 * W, max(body_hi - body_lo, 1),
            color=color, zorder=3,
        ))
        ax.plot([i, i], [lows[i], body_lo], color=color, linewidth=0.8, zorder=2)
        ax.plot([i, i], [body_hi, highs[i]], color=color, linewidth=0.8, zorder=2)

    # ── 支撐壓力水平線 ────────────────────────────────────
    for p, cnt in swing_highs:
        lw = 1 + cnt * 0.4
        ax.axhline(p, color="#ff6b6b", linewidth=lw, linestyle="--", alpha=0.8, zorder=4)
        ax.text(n - 0.5, p, f" R {p:,} {'★'*cnt}",
                color="#ff6b6b", fontsize=7, va="bottom", zorder=5)
    for p, cnt in swing_lows:
        lw = 1 + cnt * 0.4
        ax.axhline(p, color="#4ecdc4", linewidth=lw, linestyle="--", alpha=0.8, zorder=4)
        ax.text(n - 0.5, p, f" S {p:,} {'★'*cnt}",
                color="#4ecdc4", fontsize=7, va="top", zorder=5)
    for lo, hi, v, *_ in vp_res:
        mid = (lo + hi) / 2
        if ref - RANGE <= mid <= ref + RANGE:
            alpha = 0.15 + 0.25 * (v / vp_max)
            ax.axhspan(lo, hi, color="#f9ca24", alpha=alpha, zorder=1)

    # 現價基準線
    ax.axhline(ref, color="#ffffff", linewidth=1, linestyle=":", alpha=0.6, zorder=4)
    ax.text(0, ref, f" 基準 {ref:,}", color="#ffffff", fontsize=8, va="bottom", zorder=5)

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
    ax.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8, color="#cccccc")
    ax.set_xlim(-1, n)
    ax.yaxis.set_tick_params(labelcolor="#cccccc")
    ax.set_title(
        f"TX 1H K線 + 支撐壓力（近 {n_days} 日，基準 {ref:,}）",
        color="#eeeeee", fontsize=12, pad=8,
    )
    ax.grid(axis="y", color="#333355", linewidth=0.5, zorder=0)

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
        color="#f9ca24", alpha=0.6,
    )
    ax_vp.axhline(ref, color="#ffffff", linewidth=1, linestyle=":", alpha=0.6)
    ax_vp.set_xlabel("Volume", color="#cccccc", fontsize=8)
    ax_vp.set_title("VP", color="#eeeeee", fontsize=10)
    ax_vp.xaxis.set_tick_params(labelcolor="#cccccc", labelsize=7)

    # 在所有繪圖完成後才設定 ylim，避免被 barh 自動縮放覆蓋（sharey=True）
    price_range = highs.max() - lows.min()
    ax.set_ylim(lows.min() - price_range * 0.05, highs.max() + price_range * 0.1)

    plt.tight_layout()
    out_path = Path(__file__).parents[2] / "output" / "sr_chart.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
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
    """畫日盤 30 分K + 20MA + 大戶成本（昨、前天），存 PNG 並複製到剪貼簿。"""
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

    # 大戶成本
    big_cost  = data.get("big_cost", {})
    last_day  = data["last_day"]
    prev_day  = data["prev_day"]
    big_last  = big_cost.get(last_day)
    big_prev  = big_cost.get(prev_day)

    _setup_font()
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")
    ax.tick_params(colors="#cccccc")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444466")

    # K 線
    W = 0.4
    nd = len(display_idx)
    for i in range(nd):
        bull = closes_d[i] >= opens_d[i]
        color = "#ef5350" if bull else "#26a69a"
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
        ax.plot(x_disp[valid], ma20_d[valid], color="#f9ca24", linewidth=1.5,
                label="20MA", zorder=4)

    # 大戶成本水平線
    if big_last is not None:
        ax.axhline(big_last, color="#ff9f43", linewidth=1.5, linestyle="-.", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, big_last, f" 昨大戶 {big_last:,} ({last_day.strftime('%m/%d')})",
                color="#ff9f43", fontsize=8, va="bottom", zorder=6)
    if big_prev is not None:
        ax.axhline(big_prev, color="#a29bfe", linewidth=1.5, linestyle="-.", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, big_prev, f" 前天大戶 {big_prev:,} ({prev_day.strftime('%m/%d')})",
                color="#a29bfe", fontsize=8, va="bottom", zorder=6)

    # 夜盤收盤線
    night = data.get("night")
    night_close = night.get("close") if night else None
    if night_close is not None:
        ax.axhline(night_close, color="#00cec9", linewidth=1.5, linestyle="--", alpha=0.9, zorder=5)
        ax.text(nd - 0.5, night_close, f" 夜收 {night_close:,}",
                color="#00cec9", fontsize=8, va="bottom", zorder=6)

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
    ax.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8, color="#cccccc")
    ax.set_xlim(-1, nd)
    price_range = highs_d.max() - lows_d.min()
    ax.set_ylim(lows_d.min() - price_range * 0.05, highs_d.max() + price_range * 0.1)
    ax.yaxis.set_tick_params(labelcolor="#cccccc")
    ax.set_title(
        f"TX 日盤 30 分K + 20MA（近 {n_days} 日）",
        color="#eeeeee", fontsize=12, pad=8,
    )
    ax.grid(axis="y", color="#333355", linewidth=0.5, zorder=0)
    ax.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
              labelcolor="#cccccc", edgecolor="#444466")

    plt.tight_layout()
    out_path = Path(__file__).parents[2] / "output" / "30m_chart.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
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

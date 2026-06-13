"""右側欄每日統計：20日平均振幅(日盤/全日盤)、同星期平均振幅、今日日盤高低振幅、
夜盤波動(NVF norm/分級)、加權成交金額(今日 vs 20日均)、前一日 twnvix、關卡價。

關卡價與今日高低固定以日盤(08:45–13:45)為基準；20日視窗為選定日之前的 20 個交易日(不含當日)。
夜盤波動重用 key_prices 的 NVF；成交金額取 market_breadth 的 TWSE total_value。DuckDB 唯讀。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from src.analysis.key_prices import _NVF_TIER_ICONS, _compute_night_vol_filter
from src.chart_ui import paths

SYMBOL = "TX"
WINDOW = 20
_WD_NAMES = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")

# 關卡價 = 達到率百分位階梯（單參數：EMA20 無常數分位迴歸, 全樣本 2021-2026 擬合）。
# 每階振幅 = c×EMA20(日盤振幅)；達到率 = 1−τ。
# H097：夜盤校正中位僅 4~14 點、典型 <一個關卡間距的 1/5（跳格 23~56 點），且 1~2% 的日子
# 才會跨過一格 → 夜盤只在同關卡帶內微調、決策意義低，故簡化為 EMA-only。
# 全樣本實測達到率 90/76/50（碰 L1/L2/L3），幾乎完美對齊名目；舊雙參數(2026擬合)偏寬只 65/41/28。
EMA_SPAN = 20
LVL_QUANTILES = [
    # (序號, 達到率, c_EMA20)
    ("1", "90%", 0.385),
    ("2", "75%", 0.497),
    ("3", "50%", 0.711),
    ("4", "25%", 0.977),
    ("5", "12.5%", 1.225),  # H095 pooled 分位，延伸長尾關卡
]
# 量能整排上調（覆盤用當日實際收盤量, hindsight）：bump = NVOL_W_SURP×(量比−1)×EMA20。
# 僅資訊顯示(整排平移幾十點)，不套用到關卡本身。
NVOL_W_SURP = 0.13

# 碰到 L1 的時間 → 續到 L2 / L3 的機率(%)。方向性擺動分析(多空對稱, pooled, 2021-2026)。
# 在 EMA-only 關卡定義下重算（H097 touch_times.py）。
# L4 不是計畫性目標（早觸亦難預測），故不建表。time = 當日分鐘數(08:45 = 525)。step function。
_CONT_L2 = [(525, 94), (540, 92), (555, 87), (570, 84), (585, 80),
            (600, 80), (615, 66), (630, 78), (645, 61)]
_CONT_L3 = [(525, 76), (540, 67), (555, 56), (570, 55), (585, 46),
            (600, 50), (615, 32), (630, 37), (645, 27)]
_TARGET_MIN = 50  # 該階續航 ≥ 此值才當「可瞄目標」
# L3 額外時間閘：碰 L1 須早於 09:30(=570) 才把 L3 當目標。EMA-only 下 _CONT_L3 於 09:45 才
# 跌破 50%（09:30 那格 55%），此閘比數據更保守，依使用者規則保留。
_L3_CUTOFF_MIN = 570

# 碰 L2 的時間 → 續到 L3 的機率(%)。H096 驗證：以「碰 L2 時間」為條件遠強於「碰 L1 時間」
# (基準 66% vs 55%)，故碰 L2 後再更新一次續 L3 提示。在 EMA-only 關卡下重算(H097)：
# 早盤碰 L2 ~86% 續 L3，遞減到 10:45+ 僅 46%(<門檻→改顯示「守 L2」)。不受 09:30 閘限制。
# step function, 取 ≤ minute 的最後一格。
_CONT_L3_FROM_L2 = [(525, 86), (540, 79), (555, 74), (570, 69), (585, 63),
                    (600, 65), (615, 64), (630, 55), (645, 46)]


def _trading_days(conn) -> list[date]:
    rows = conn.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY d",
        [SYMBOL],
    ).fetchall()
    return [r[0] for r in rows]


def _prior_days(days: list[date], sel: date, n: int) -> list[date]:
    """選定日之前的 n 個交易日（不含當日）。"""
    return [d for d in days if d < sel][-n:]


def _day_ranges(conn, day_list: list[date]) -> dict[date, float]:
    """日盤每日振幅 = MAX(high) - MIN(low)，08:45–13:45。"""
    if not day_list:
        return {}
    ph = ",".join(["?"] * len(day_list))
    rows = conn.execute(
        f"SELECT CAST(timestamp AS DATE) d, MAX(high) - MIN(low) rng FROM ohlcv_1m "
        f"WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        f"AND CAST(timestamp AS DATE) IN ({ph}) GROUP BY 1",
        [SYMBOL, *day_list],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _full_ranges(conn, day_list: list[date]) -> dict[date, float]:
    """全日盤每日振幅：前夜 15:00 → 隔日 05:00 + 當日日盤，歸屬到 session_day（同 kline_loader）。"""
    if not day_list:
        return {}
    lo = min(day_list) - timedelta(days=5)
    ph = ",".join(["?"] * len(day_list))
    sql = f"""
    WITH td AS (
      SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    ),
    night_dates AS (
      SELECT DISTINCT CAST(timestamp AS DATE) nd FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) >= TIME '15:00:00'
    ),
    night_map AS (
      SELECT nd, (SELECT min(d) FROM td WHERE d > nd) AS session_day FROM night_dates
    ),
    assigned AS (
      SELECT b.high, b.low,
        CASE WHEN CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             THEN nm.session_day ELSE CAST(b.timestamp AS DATE) END AS session_day
      FROM ohlcv_1m b
      LEFT JOIN night_map nm ON nm.nd = CAST(b.timestamp AS DATE)
      WHERE b.symbol = ?
        AND CAST(b.timestamp AS DATE) >= ?
        AND (CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             OR CAST(b.timestamp AS TIME) <= TIME '05:00:00'
             OR CAST(b.timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00')
    )
    SELECT session_day d, MAX(high) - MIN(low) rng
    FROM assigned WHERE session_day IN ({ph})
    GROUP BY 1
    """
    rows = conn.execute(sql, [SYMBOL, SYMBOL, SYMBOL, lo, *day_list]).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _today_hl(conn, sel: date) -> tuple[float, float] | None:
    row = conn.execute(
        "SELECT MAX(high), MIN(low) FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'",
        [SYMBOL, sel],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0]), float(row[1])


def _prev_vix(conn, sel: date) -> dict | None:
    """前一交易日(<sel) 組合 regime（VIX 方向 + 已實現振幅方向,因果;H117）+ ladder 達成期望/動作。"""
    try:
        from src.analysis.vix_regime import get_regime, REACH_EXPECT, regime_note
        vr = get_regime(as_of=sel - timedelta(days=1))
    except Exception:
        vr = None
    if vr is None:
        row = conn.execute(
            "SELECT date, vix FROM vixtwn WHERE date < ? ORDER BY date DESC LIMIT 1", [sel]).fetchone()
        return {"date": str(row[0]), "vix": float(row[1])} if row else None
    out = {"date": str(vr["date"]), "vix": vr["vix"], "ma20": vr["ma20"], "regime": vr["regime"],
           "level": vr["level"], "extreme": vr["extreme"], "vix_dir": vr["vix_dir"], "rv_dir": vr["rv_dir"]}
    e = REACH_EXPECT[vr["regime"]]
    out["expect"] = {"uL4": e["多L4"], "uL5": e["多L5"], "dL4": e["空L4"], "dL5": e["空L5"]}
    out["note"] = regime_note(vr["regime"], vr["level"], vr["extreme"])
    return out


def _night_range(conn, sel: date, prev_day: date | None) -> float | None:
    """sel 前一夜（前一交易日 15:00 → sel 05:00）日內振幅，from ohlcv_1m。

    跨假日時 <=05:00 的延續段落（如週六凌晨）歸屬到下一交易日 sel，與
    key_prices._compute_night_vol_filter 的 find_next_trade_date 對齊。
    """
    if prev_day is None:
        return None
    row = conn.execute(
        "SELECT MAX(high) - MIN(low) FROM ohlcv_1m WHERE symbol = ? AND ("
        "  (CAST(timestamp AS TIME) >= TIME '15:00:00' AND CAST(timestamp AS DATE) = ?) "
        "  OR (CAST(timestamp AS TIME) <= TIME '05:00:00' "
        "      AND CAST(timestamp AS DATE) > ? AND CAST(timestamp AS DATE) <= ?))",
        [SYMBOL, prev_day, prev_day, sel],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _turnover(conn, sel: date, prior: list[date]) -> dict | None:
    """加權指數（集中市場 TWSE）成交金額：今日 + 前 20 交易日均，單位億元。"""
    today = conn.execute(
        "SELECT total_value FROM market_breadth WHERE market = 'TWSE' AND trade_date = ?", [sel]
    ).fetchone()
    today_v = float(today[0]) if today and today[0] is not None else None
    avg_v, n = None, 0
    if prior:
        ph = ",".join(["?"] * len(prior))
        rows = conn.execute(
            f"SELECT total_value FROM market_breadth WHERE market = 'TWSE' "
            f"AND trade_date IN ({ph}) AND total_value IS NOT NULL",
            list(prior),
        ).fetchall()
        vals = [float(r[0]) for r in rows]
        if vals:
            avg_v, n = sum(vals) / len(vals), len(vals)
    if today_v is None and avg_v is None:
        return None
    return {
        "today": round(today_v / 1e8) if today_v is not None else None,
        "avg20": round(avg_v / 1e8) if avg_v is not None else None,
        "n": n,
    }


def _weekday_range(conn, sel: date) -> dict | None:
    """同星期、過去 60 日（不含當日）的日盤平均振幅。"""
    wd = sel.weekday()  # 0=Mon
    rows = conn.execute(
        "SELECT MAX(high) - MIN(low) FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) < ? AND CAST(timestamp AS DATE) >= ?::DATE - INTERVAL '60 days' "
        "AND dayofweek(CAST(timestamp AS DATE)) = ? "
        "GROUP BY CAST(timestamp AS DATE)",
        [SYMBOL, sel, sel, (wd + 1) % 7],
    ).fetchall()
    vals = [float(r[0]) for r in rows]
    if not vals:
        return None
    return {"avg": round(sum(vals) / len(vals)), "n": len(vals), "wd": _WD_NAMES[wd]}


def _ema20_range(conn, sel: date, span: int = EMA_SPAN) -> float | None:
    """sel 之前（不含當日）日盤振幅的 EMA(span)，causal。adjust=False，與分析腳本一致。"""
    rows = conn.execute(
        "SELECT rng FROM ("
        "  SELECT CAST(timestamp AS DATE) d, MAX(high) - MIN(low) rng FROM ohlcv_1m "
        "  WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "  AND CAST(timestamp AS DATE) < ? GROUP BY 1 ORDER BY d DESC LIMIT 120"
        ") ORDER BY d",
        [SYMBOL, sel],
    ).fetchall()
    if len(rows) < span:
        return None
    alpha = 2.0 / (span + 1)
    ema = float(rows[0][0])
    for (r,) in rows[1:]:
        ema = alpha * float(r) + (1 - alpha) * ema
    return ema


def _cont_lookup(table, minute: int) -> int:
    """step function：取 table 中 start ≤ minute 的最後一格之值。"""
    c = table[0][1]
    for start, v in table:
        if minute >= start:
            c = v
        else:
            break
    return c


_GATE_0930, _GATE_1030 = 570, 630
_BAND_LABEL = {"strong": "強", "mid": "中", "weak": "弱"}


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _exit_advice(touches: dict, band: str, side: str) -> dict:
    """依觸及時間 + 時間閘產生覆盤出場路線（事後，結構化供前端排版）。

    停損鐵律：碰 L3 前一律守初始 SL（不移 BE、不啟 trail）；時間閘（09:30/10:30）只升「目標」。
    L1/L2 用 EOD regime band 給目標積極度；L3 起列出 DCI 分支提醒（規則速查，覆盤對照實盤用），
    多空不對稱：多方 L3 拆 0.2/0.4、L4 砍½；空方 L3 強空全口切、L4 依強度分批出。
    DCI 分支的實際選擇以盤中即時 DCI 為準（此處 DCI 為收盤事後值，故只列分支不替你選）。
    詳見 research/active/H095-reach-ladder-exit/journal_checklist.md（v5.4）。

    回傳 {band_label, steps:[{t, level, action, branches?, note?}], note?}。
    """
    bl = _BAND_LABEL.get(band, band)
    t1, t2, t3 = touches.get("L1"), touches.get("L2"), touches.get("L3")
    t4, t5 = touches.get("L4"), touches.get("L5")
    if t1 is None:
        return {"band_label": bl, "steps": [], "note": "未碰 L1"}
    is_long = side == "多"
    steps = []
    # L1 閘（09:30）：目標預報，守初 SL
    aim1 = "瞄 L3（守初SL）" if (band == "strong" or t1 < _GATE_0930) else "暫收 L2（守初SL）"
    steps.append({"t": _hhmm(t1), "level": "L1", "action": aim1})
    # L2 閘（10:30）：覆蓋 L1，仍守初 SL
    if t2 is not None:
        if band == "strong":
            act2 = "靜態瞄 L3、標記獵 L4"
            note2 = "晚碰上限 ~11:00–11:30" if t2 >= _GATE_1030 else None
        elif band == "weak":
            act2, note2 = "守 L2／快收", None
        elif t2 < _GATE_1030:
            act2, note2 = "靜態瞄 L3", None
        else:
            act2, note2 = "半收 L2、半瞄 L3", None
        steps.append({"t": _hhmm(t2), "level": "L2", "action": act2, "note": note2})
    # L3：第一個動停損點，依 DCI 拆分（多空不對稱）+ 時間旁註
    if t3 is not None:
        if is_long:
            branches = ["< 0.2　靜態拿 L3", "0.2 ~ 0.4　出 ½、留 ½ 切 Dow", "≥ 0.4　出 ⅓、留 ⅔ 切 Dow"]
        else:
            branches = ["> −0.2　靜態拿 L3", "≤ −0.2　全口切 Dow、延 L4 分批"]
        if t3 < _GATE_0930:
            note3 = "早碰／gap-and-go：偏積極，餘量多留"
        elif t3 >= 690:  # 11:30
            note3 = "晚碰 11:30+：長尾塌，可收乾淨（H099 觀察）"
        else:
            note3 = None
        steps.append({"t": _hhmm(t3), "level": "L3", "action": "依 DCI 拆",
                      "branches": branches, "note": note3})
    # L4：罕見長尾，多方砍½(降變異)/空方依強度分批出(強→出少留多，抱肥尾)
    if t4 is not None:
        if is_long:
            branches = ["≥ 0.4 路徑　出 ⅓、留 ⅓ 切 Dow", "0.2 ~ 0.4 路徑　出 ¼、留 ¼ 切 Dow"]
            act4, note4 = "餘量再砍 ½", "餘量 Dow trail 博瘦尾"
        else:
            branches = ["≤ −0.2　出 ⅓", "≤ −0.4　出 ¼", "≤ −0.6　出 ⅕"]
            act4, note4 = "依強度分批出（強→出少留多）", "餘量 Dow 博 L6／L7"
        steps.append({"t": _hhmm(t4), "level": "L4", "action": act4,
                      "branches": branches, "note": note4})
    # L5：深長尾純收割，逐步收緊（口數不足直接用最緊那道）
    if t5 is not None:
        steps.append({"t": _hhmm(t5), "level": "L5", "action": "逐步收緊",
                      "branches": ["① L5價／15分目標", "② 反向 K 收盤", "③ 5MA 站回 → 清"],
                      "note": "口數不足直接用 ③"})
    return {"band_label": bl, "steps": steps, "note": None}


def _touch_hint(t) -> dict | None:
    """t = datetime.time(L1 首次觸及) → {time, target, cont, action}；未觸及回 None。

    依續航機率決定該瞄到第幾階：碰 L1 早於 09:30 且續L3 ≥50% → 瞄 L3；
    否則續L2 ≥50% → 瞄 L2；否則 拿 L1。
    """
    if t is None:
        return None
    m = t.hour * 60 + t.minute
    c2, c3 = _cont_lookup(_CONT_L2, m), _cont_lookup(_CONT_L3, m)
    if c3 >= _TARGET_MIN and m < _L3_CUTOFF_MIN:
        target, cont, action = "3", c3, "瞄"
    elif c2 >= _TARGET_MIN:
        target, cont, action = "2", c2, "瞄"
    else:
        target, cont, action = "1", c2, "拿"
    return {"time": t.strftime("%H:%M"), "target": target, "cont": cont, "action": action}


def _l2_hint(t) -> dict | None:
    """t = L2 首次觸及 time → {time, contL3, action}；未觸及回 None。

    第二段提示：站在「已碰 L2」更新一次續 L3 機率（H096，比 L1 時間強得多）。
    續 L3 ≥ 門檻 → 瞄 L3；否則守 L2。實務上整日 ≥54%，幾乎恆為瞄 L3。
    """
    if t is None:
        return None
    m = t.hour * 60 + t.minute
    c3 = _cont_lookup(_CONT_L3_FROM_L2, m)
    action = "瞄" if c3 >= _TARGET_MIN else "守"
    return {"time": t.strftime("%H:%M"), "contL3": c3, "action": action}


def _level1_signals(conn, sel: date, r1: float | None, r2: float | None) -> dict | None:
    """當天多/空兩方向首次達到 L1 距離 r1、L2 距離 r2 的時間 + 兩段式續航建議。

    上擺 = 從盤中低點往上的最大移動；下擺 = 從盤中高點往下的最大移動(方向性，與分析一致)。
    每方向回 {"l1": 碰L1提示(_touch_hint), "l2": 碰L2後續L3提示(_l2_hint or None)}。
    """
    if r1 is None or r1 <= 0:
        return None
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp",
        [SYMBOL, sel],
    ).fetchall()
    if not rows:
        return None
    run_lo, run_hi = float("inf"), float("-inf")
    up_max = dn_max = 0.0
    bull_t1 = bear_t1 = bull_t2 = bear_t2 = None
    for t, h, l in rows:
        h, l = float(h), float(l)
        run_lo, run_hi = min(run_lo, l), max(run_hi, h)
        up_max, dn_max = max(up_max, h - run_lo), max(dn_max, run_hi - l)
        if bull_t1 is None and up_max >= r1:
            bull_t1 = t
        if bear_t1 is None and dn_max >= r1:
            bear_t1 = t
        if r2 and bull_t2 is None and up_max >= r2:
            bull_t2 = t
        if r2 and bear_t2 is None and dn_max >= r2:
            bear_t2 = t
    return {
        "bull": {"l1": _touch_hint(bull_t1), "l2": _l2_hint(bull_t2)},
        "bear": {"l1": _touch_hint(bear_t1), "l2": _l2_hint(bear_t2)},
    }


def _running_anchor_touches(bars, levels: list[tuple[str, float]]) -> dict:
    """單一 running 錨點、每階首觸（原行為）。bars=[(minute,high,low)] 昇冪。

    多方從累計低點往上、空方從累計高點往下，距離達到即記首觸。
    price = 多方 run_low+距離 / 空方 run_high−距離（投射價）。
    """
    out = {"bull": [], "bear": []}
    run_lo, run_hi = float("inf"), float("-inf")
    up_max = dn_max = 0.0
    done_b, done_s = set(), set()
    for m, h, l in bars:
        run_lo, run_hi = min(run_lo, l), max(run_hi, h)
        up_max, dn_max = max(up_max, h - run_lo), max(dn_max, run_hi - l)
        for label, dist in levels:
            if label not in done_b and up_max >= dist:
                done_b.add(label)
                out["bull"].append({"level": label, "price": round(run_lo + dist),
                                    "time": _hhmm(m), "minute": m})
            if label not in done_s and dn_max >= dist:
                done_s.add(label)
                out["bear"].append({"level": label, "price": round(run_hi - dist),
                                    "time": _hhmm(m), "minute": m})
    out["bull"].sort(key=lambda x: x["minute"])
    out["bear"].sort(key=lambda x: x["minute"])
    return out


def _rearm_touches(bars, levels: list[tuple[str, float]], l2_dist: float | None) -> dict:
    """每個 ≥L2 反轉波段以波段極值為錨點重新上膛 L1–L5（方案 B）。

    bars=[(minute,high,low)] 昇冪。回傳 {bull:[{level,price,time,minute}], bear:[...]}，
    同一階一天可多筆（不同波段、不同錨價）。無任何 ≥L2 反轉時退回單一 running 錨點。
    用與 L3 波段相同的 zigzag（反轉門檻=l2_dist，不套 L3 最小幅度）取波段轉折。
    """
    out = {"bull": [], "bear": []}
    if not bars:
        return out
    # 延遲 import 避免 daystats ↔ swing_legs 循環依賴
    from src.chart_ui.services.swing_legs import zigzag_legs

    legs = zigzag_legs(bars, threshold=l2_dist) if l2_dist and l2_dist > 0 else []
    if not legs:
        return _running_anchor_touches(bars, levels)

    for lg in legs:
        sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
        side = "bull" if lg["dir"] == "up" else "bear"
        done = set()
        ext = 0.0
        for m, h, l in bars:
            if m < sm or m > em:
                continue
            ext = max(ext, (h - anchor) if side == "bull" else (anchor - l))
            for label, dist in levels:
                if label not in done and ext >= dist:
                    done.add(label)
                    price = round(anchor + dist) if side == "bull" else round(anchor - dist)
                    out[side].append({"level": label, "price": price,
                                      "time": _hhmm(m), "minute": m})
    out["bull"].sort(key=lambda x: x["minute"])
    out["bear"].sort(key=lambda x: x["minute"])
    return out


def _collect_touches(conn, sel, levels: list[tuple[str, float]]) -> dict:
    """各階(label, 距離) 多/空波段觸及。回傳 {bull:[{level,price,time,minute}], bear:[...]}。

    每個 ≥L2 反轉波段重新上膛（方案 B，詳見 _rearm_touches）；反轉門檻取 levels 中 L2 的距離。
    """
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp",
        [SYMBOL, sel],
    ).fetchall()
    bars = [(t.hour * 60 + t.minute, float(h), float(l)) for t, h, l in rows]
    l2_dist = dict(levels).get("L2")
    return _rearm_touches(bars, levels, l2_dist)


def _stats(vals: list[float]) -> dict | None:
    if not vals:
        return None
    return {
        "avg": round(sum(vals) / len(vals)),
        "max": round(max(vals)),
        "min": round(min(vals)),
        "n": len(vals),
    }


def compute_daystats(*, date_str: str, db_path: Path | None = None) -> dict:
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        days = _trading_days(conn)
        prior = _prior_days(days, sel, WINDOW)
        day_r = _day_ranges(conn, prior)
        full_r = _full_ranges(conn, prior)
        today = _today_hl(conn, sel)
        prev_vix = _prev_vix(conn, sel)
        prev_day = prior[-1] if prior else None
        night_range = _night_range(conn, sel, prev_day)
        turnover = _turnover(conn, sel, prior)
        weekday_range = _weekday_range(conn, sel)
        ema20 = _ema20_range(conn, sel)
        level1 = None
        if ema20:
            _r1 = LVL_QUANTILES[0][2] * ema20  # L1 振幅距離
            _r2 = LVL_QUANTILES[1][2] * ema20  # L2 振幅距離
            level1 = _level1_signals(conn, sel, _r1, _r2)

        # 觸及（含 L4/L5）+ DCI(收盤/事後) + 出場路線
        touches = {"bull": [], "bear": []}
        dci = None
        exit_advice = None
        if ema20:
            _lv = [("L1", LVL_QUANTILES[0][2] * ema20),
                   ("L2", LVL_QUANTILES[1][2] * ema20),
                   ("L3", LVL_QUANTILES[2][2] * ema20),
                   ("L4", LVL_QUANTILES[3][2] * ema20),
                   ("L5", LVL_QUANTILES[4][2] * ema20)]  # 顯示每一個關卡的觸及（含 L4/L5）
            touches = _collect_touches(conn, sel, _lv)
            from src.chart_ui.services.dci_daily import compute_daily_dci
            dci = compute_daily_dci(conn, sel)
            if dci:
                dci["hindsight"] = True
                dci["w_proxy"] = True
            # touches 已按 minute 昇冪；同階可能多筆(多波段重新上膛)，exit_advice 取每階最早一次
            _bmin: dict = {}
            for t in touches["bull"]:
                _bmin.setdefault(t["level"], t["minute"])
            _smin: dict = {}
            for t in touches["bear"]:
                _smin.setdefault(t["level"], t["minute"])
            _bl = dci["regime_long"] if dci else "mid"
            _bs = dci["regime_short"] if dci else "mid"
            exit_advice = {"bull": _exit_advice(_bmin, _bl, "多"),
                           "bear": _exit_advice(_smin, _bs, "空")}

    # 夜盤波動分級：重用 morning briefing 的 NVF（norm = 夜振 / EMA20 + 4 級分類）。
    # _compute_night_vol_filter 連自己的預設 DB；chart-ui 一律走預設 DB，故一致。
    night_vol = None
    if night_range is not None and prev_day is not None:
        night_vol = {"range": round(night_range)}
        try:
            nvf = _compute_night_vol_filter(prev_day, night_range)
        except Exception:
            nvf = None
        if nvf and nvf.get("night_norm") is not None:
            night_vol.update({
                "norm": nvf["night_norm"],
                "ema20": nvf["ema20"],
                "tier": nvf["tier"],
                "icon": _NVF_TIER_ICONS.get(nvf["tier"], ""),
                "pass": nvf["pass"],
            })

    day_stats = _stats([day_r[d] for d in prior if d in day_r])
    full_stats = _stats([full_r[d] for d in prior if d in full_r])

    avg_range_20 = {
        "day": day_stats["avg"] if day_stats else None,
        "n_day": day_stats["n"] if day_stats else 0,
        "full": full_stats["avg"] if full_stats else None,
        "n_full": full_stats["n"] if full_stats else 0,
    }

    today_out = None
    if today:
        hi, lo = today
        today_out = {"high": round(hi), "low": round(lo), "range": round(hi - lo)}

    # 關卡價 = 達到率百分位階梯（多1=90%地板 … 多4=25% … 多5=12.5%）。每階振幅 = c×EMA20（單參數, H097；L5 為 H095 pooled 分位）。
    # 多方由今低往上投射(預估高)、空方由今高往下投射(預估低)。
    # 量能上調(事後)：用當日實際收盤量算 bump，整排平移幾十點，僅在副標題顯示、不套用。
    bull = bear = est_range = None
    if today and ema20:
        hi, lo = today
        t20 = turnover.get("avg20") if turnover else None       # 20日均量(億)
        tv_today = turnover.get("today") if turnover else None   # 當日實際量(億, hindsight)
        q = bump = None
        if tv_today is not None and t20:
            q = tv_today / t20
            bump = NVOL_W_SURP * (q - 1.0) * ema20
        floor90 = None
        bull_rows, bear_rows = [], []
        for s, lab, coef in LVL_QUANTILES:
            rng = coef * ema20
            if s == "1":
                floor90 = rng
            bull_rows.append({"label": f"多{s}·{lab}", "price": round(lo + rng)})
            bear_rows.append({"label": f"空{s}·{lab}", "price": round(hi - rng)})
        bull_rows.append({"label": "今高", "price": round(hi), "today": True})
        bear_rows.append({"label": "今低", "price": round(lo), "today": True})
        bull = sorted(bull_rows, key=lambda x: -x["price"])
        bear = sorted(bear_rows, key=lambda x: -x["price"])
        est_range = {"floor90": round(floor90) if floor90 is not None else None,
                     "ema20": round(ema20),
                     "bump": round(bump) if bump is not None else None,
                     "q": round(q, 2) if q is not None else None,
                     "tv_today": round(tv_today) if tv_today is not None else None,
                     "tv20": round(t20) if t20 else None}

    return {
        "date": date_str,
        "avg_range_20": avg_range_20,
        "today": today_out,
        "night_vol": night_vol,
        "turnover": turnover,
        "weekday_range": weekday_range,
        "prev_vix": prev_vix,
        "est_range": est_range,
        "level1": level1,
        "bull": bull,
        "bear": bear,
        "touches": touches,
        "dci": dci,
        "exit_advice": exit_advice,
    }

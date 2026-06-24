"""L2 拉回續攻（拉回後站回 5MA 續攻 L2→L3）偵測 — chart-ui 主圖指標 + list 共用真相源。
（前身為 H120；該假設 causal 後接近 break-even、已 archive/rejected，本檔僅作行情參考指標保留。）

⚠️ 完全 CAUSAL（逐根 streaming，無前視偏誤）。
  舊版用 ZigZag leg 終點 em（反轉後才知的未來資訊）當進場搜尋上界，系統性濾掉失敗站回 →
  灌高勝率/EV（H120/S005 因此於 2026-06-15 作廢）。本檔已改為與
  research/archive/rejected/H120-l2-pullback-continuation/validate_causal.py 的 detect_causal
  對齊：進場相位 = [翻上事件, 下一翻下事件)，anchor=翻轉當下已知的 running 極值(pivot)，不碰未來。

  Setup：價格自 running 極值反轉達 L2 即翻轉確立 → 第一個 ≥PB_FLOOR 拉回 → 收盤站回 5MA 進場。
  guard：直衝 L3 不交易(matured)、進場那根已破 L3 不交易(overshoot)。每相位至多一筆（第一個站回；
         深度濾網於 compute_l2_pullback_entries 事後套——H124 已驗證「淺站回不燒名額/同相位多取」為 -EV，不採用）。
  停損：拉回極值往錨點靠 STOP_ALPHA；目標：錨 ± L3 距離。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range

COEF = {"L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}
PB_FLOOR_FRAC = 0.05
STOP_ALPHA = 0.75
EMA5 = 5
CUTOFF_MIN = 720       # 進場時間上限=12:00（午後尾盤幾乎無 edge）
MIN_DEPTH_FRAC = 0.25  # 進場最小拉回深度(÷L2)；濾掉淺拉回（avgR僅0.08、占46%）

# H126（confirmed）：同向第 2 次（含以上）L2 拉回 + entry∈[09:30,11:30] = 乾淨續攻訊號。
# 停損用 alpha=1.0（=錨點，回測單調最佳），目標瞄 L4（非保守 L3）。詳見
# research/archive/confirmed/H126-second-l2-pullback/。偵測同源 detect_day，僅以 ordinal 切子集。
H126_WIN_LO, H126_WIN_HI = 570, 690   # 09:30–11:30
H126_ALPHA = 1.0
H126_TARGET = "L4"


def _sma(seq, n):
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def _min_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def detect_day(bars, ema20):
    """bars=[(minute,o,h,l,c)] 昇冪。完全 causal streaming，回傳 (entries, dist)。

    與 validate_causal.py 的 detect_causal 對齊（無前視偏誤）：在單一 streaming 迴圈內同時
    維護 ZigZag 翻轉狀態（trend/up_ref/dn_ref/ext）與「本相位」進場狀態。每個翻轉事件當下即
    開新相位（anchor=該翻轉的 running 極值=pivot，過去已知），在下一個反向翻轉前找首個拉回站回。

    entry dict：entry_min, entry_i, side('long'/'short'), entry, anchor, pb_ext, stop, target,
                risk, depth_frac, size。
    """
    dist = {k: COEF[k] * ema20 for k in COEF}
    L2d, L3d = dist["L2"], dist["L3"]
    pb_floor = PB_FLOOR_FRAC * ema20
    closes = [b[4] for b in bars]
    s5 = _sma(closes, EMA5)
    n = len(bars)
    out = []
    ord_count: dict[str, int] = defaultdict(int)   # 同方向序數（H126）

    # ZigZag streaming 狀態
    trend = None
    up_ref = bars[0][3]          # running low（上漲基準）
    dn_ref = bars[0][2]          # running high（下跌基準）
    ext = None                   # 當前相位極值
    # 進場相位狀態
    phase = None                 # None / 'up' / 'down'
    anchor = None
    peak = None                  # 確立後 running 極值（續攻方向）
    sub = None                   # 'extend' / 'pullback'
    pb_ext = None
    done = False                 # 本相位是否已出手或失效（zigzag 仍續跑）

    def open_phase(dir_up, anc, cur_h, cur_l):
        nonlocal phase, anchor, peak, sub, pb_ext, done
        phase = "up" if dir_up else "down"
        anchor = anc
        peak = cur_h if dir_up else cur_l
        sub = "extend"
        pb_ext = None
        done = False

    for i in range(n):
        m, o, h, l, c = bars[i]

        # 1) 先推進本相位進場邏輯（用截至 i 的資訊，全 causal）
        if phase is not None and not done:
            up = phase == "up"
            if (h > peak) if up else (l < peak):
                peak = h if up else l
            if abs(peak - anchor) >= L3d:
                done = True                      # 直衝 L3，非可交易
            else:
                if sub == "extend":
                    dip = (peak - l) if up else (h - peak)
                    if dip >= pb_floor:
                        sub = "pullback"
                        pb_ext = l if up else h
                if sub == "pullback":
                    pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                    cs = s5[i]
                    ps = s5[i - 1] if i > 0 else None
                    pc = bars[i - 1][4] if i > 0 else None
                    if cs is not None and ps is not None and pc is not None:
                        reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                        overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                        if reclaim and not overshoot:
                            stop = pb_ext - STOP_ALPHA * (pb_ext - anchor) if up \
                                else pb_ext + STOP_ALPHA * (anchor - pb_ext)
                            target = anchor + L3d if up else anchor - L3d
                            depth = (peak - pb_ext) if up else (pb_ext - peak)
                            dfrac = depth / L2d
                            side = "long" if up else "short"
                            ord_count[side] += 1
                            out.append({
                                "entry_min": m, "entry_i": i,
                                "side": side, "ordinal": ord_count[side],
                                "entry": round(c, 1), "anchor": round(anchor, 1),
                                "pb_ext": round(pb_ext, 1), "stop": round(stop, 1),
                                "target": round(target, 1),
                                "risk": round(abs(c - stop)),
                                "depth_frac": dfrac, "size": size_mult(dfrac),
                            })
                            done = True

        # 2) 再推進 ZigZag streaming（翻轉事件 → 開新相位）
        if trend is None:
            if l < up_ref:
                up_ref = l
            if h > dn_ref:
                dn_ref = h
            if h - up_ref >= L2d:
                trend = "up"
                ext = h
                open_phase(True, up_ref, h, l)   # 翻上＝確立，anchor=running low
            elif dn_ref - l >= L2d:
                trend = "down"
                ext = l
                open_phase(False, dn_ref, h, l)
        elif trend == "up":
            if h > ext:
                ext = h
            elif ext - l >= L2d:                 # 翻下事件：確認 pivot high = ext
                pivot = ext
                trend = "down"
                ext = l
                open_phase(False, pivot, h, l)    # 下跌相位 anchor = 該波峰
        else:  # trend == "down"
            if l < ext:
                ext = l
            elif h - ext >= L2d:                 # 翻上事件：確認 pivot low = ext
                pivot = ext
                trend = "up"
                ext = h
                open_phase(True, pivot, h, l)     # 上漲相位 anchor = 該波谷
    return out, dist


def size_mult(dfrac: float) -> float:
    """加碼已移除：一律 ×1。

    舊版「深度≥0.5 ×2」來自前視偏誤回測的「深度↑→賠率↑單調」假象。causal 全窗實測
    depth 與賠率非單調（[0.5,0.75) 反而 avgR −0.05、tot −1.9%，只有 [0.75,1.0) avgR 0.27），
    故無可靠的深度→加碼關係，停用加碼。保留函式作介面相容/未來 causal 重驗的掛點。
    """
    return 1.0


def simulate(e, bars):
    """從進場掃到收盤：stop / target / 收盤。回傳 exit_min, exit, pnl, result。"""
    up = e["side"] == "long"
    entry, stop, target = e["entry"], e["stop"], e["target"]
    exit_min, exit_px, result = bars[-1][0], bars[-1][4], "Open"
    for m, o, h, l, c in bars[e["entry_i"] + 1:]:
        hit_stop = (l <= stop) if up else (h >= stop)
        hit_tgt = (h >= target) if up else (l <= target)
        if hit_stop:
            exit_min, exit_px, result = m, stop, "Loss"
            break
        if hit_tgt:
            exit_min, exit_px, result = m, target, "Win"
            break
    pnl = (exit_px - entry) if up else (entry - exit_px)
    return exit_min, round(exit_px, 1), round(pnl, 1), result


def _day_bars(conn, sel: date):
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp", [SYMBOL, sel]).fetchall()
    return [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c))
            for t, o, h, l, c in rows]


def is_h126(e: dict) -> bool:
    """H126 訊號：同向第 2 次（含以上）拉回 + entry∈[09:30,11:30]。"""
    return e["ordinal"] >= 2 and H126_WIN_LO <= e["entry_min"] < H126_WIN_HI


def h126_variant(e: dict, dist: dict) -> dict:
    """把一筆進場改成 H126 出場規格（停損=錨點 alpha=1.0、目標 L4），回傳新 dict（不改原）。"""
    up = e["side"] == "long"
    anchor = e["anchor"]
    tgt_d = dist[H126_TARGET]
    stop = anchor                                  # alpha=1.0 → stop = pb_ext − (pb_ext − anchor) = anchor
    target = anchor + tgt_d if up else anchor - tgt_d
    return {**e, "stop": round(stop, 1), "target": round(target, 1),
            "risk": round(abs(e["entry"] - stop))}


def compute_l2_pullback_entries(*, date_str: str, db_path: Path | None = None) -> dict:
    """單日 L2 拉回續攻進場（主圖指標用）。回傳 {entries:[{time,side,entry,ordinal,is_h126,stop,target,...}], ...}。

    1st（=H120 母體，參考用）：沿用既有濾網（≤12:00、深度≥MIN_DEPTH_FRAC）+ L3/alpha0.75 levels。
    2nd+ 且 09:30–11:30（=H126 confirmed 訊號）：不套深度/時間濾網，改用 H126 levels（停損=錨點、目標 L4）。
    """
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        ema20 = _ema20_range(conn, sel)
        if not ema20:
            return {"entries": [], "l3_dist": None, "ema20": None}
        bars = _day_bars(conn, sel)
    if len(bars) < 5:
        return {"entries": [], "l3_dist": round(COEF["L3"] * ema20, 1), "ema20": round(ema20, 1)}
    entries, dist = detect_day(bars, ema20)
    out = []
    for e in entries:
        h126 = is_h126(e)
        if not h126:                               # 1st 參考：沿用既有濾網
            if e["entry_min"] >= CUTOFF_MIN:
                continue
            if e["depth_frac"] < MIN_DEPTH_FRAC:
                continue
        es = h126_variant(e, dist) if h126 else e
        exit_min, exit_px, pnl, result = simulate(es, bars)
        out.append({
            "time": _min_to_hhmm(e["entry_min"]),
            "side": e["side"], "ordinal": e["ordinal"], "is_h126": h126,
            "entry": es["entry"], "stop": es["stop"], "target": es["target"], "risk": es["risk"],
            "target_label": "L4" if h126 else "L3",
            "depth_frac": round(e["depth_frac"], 2), "size": e["size"],
            "exit_time": _min_to_hhmm(exit_min), "exit": exit_px,
            "pnl": pnl, "result": result,
        })
    return {"entries": out, "l3_dist": round(dist["L3"], 1), "ema20": round(ema20, 1)}

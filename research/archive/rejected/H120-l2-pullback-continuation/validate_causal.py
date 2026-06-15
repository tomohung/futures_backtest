"""H120/S005 獨立前視偏誤驗證 — 完全 causal（逐根 streaming）重寫 detection，與 live 比對。

動機：S005 績效異常好（OOS 勝率 85%、EV 60pt）。懷疑前視偏誤來自 live backtest.py 用
ZigZag 的 leg 終點 em 當進場搜尋上界（seg_idx = bars in [sm, em]）。em 是 leg 反轉後才確認
的未來資訊 → 失敗的站回（站回後隨即反轉）其反轉前高點變成 em，使該筆 i>em 被排除。
亦即 live 只取「事後續創新高」的站回，系統性濾掉失敗站回 → 灌高勝率/EV。

本腳本：
- detect_causal()：逐根 streaming 重寫。ZigZag 的「翻轉事件」本身是 causal（價格反轉 L2 當下
  即知），故沿用；anchor=翻轉當下已知的 running 極值，亦 causal。唯一差異：進場搜尋窗 =
  [翻上事件, 下一個翻下事件)，不使用未來的 em 當上界。其餘（EMA20/5MA/深度/overshoot/L3 guard）
  與 live 完全相同。
- 其餘環節（EMA20、5MA、出場模擬、指標）獨立重寫一份，並 cross-check 與 live 一致。
- 並排比較 live.detect vs detect_causal 的 IS/OOS 指標；分類 causal「多出來」的站回的勝率。

跑法：uv run python research/archive/confirmed/H120-l2-pullback-continuation/validate_causal.py
"""
from __future__ import annotations

import importlib.util
import statistics as st
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths

SYMBOL = "TX"
EMA_SPAN = 20
L2C, L3C, L4C, L5C = 0.497, 0.711, 0.977, 1.225
PB_FLOOR_FRAC = 0.05
MIN_DEPTH_FRAC = 0.25
OOS_START = date(2025, 1, 1)
NOON = 720
COST = 3.0
ALPHA = 0.75   # 部署值


# ---------- 載入 live 模組（做並排對照） ----------
def _load_live():
    p = Path(__file__).resolve().parents[4] / "strategies/retired/S005-l2-pullback/backtest.py"
    spec = importlib.util.spec_from_file_location("s005_live", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- 獨立資料載入（與 live 無關，自己一份） ----------
def load_days():
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, "
            "open, high, low, close FROM ohlcv_1m WHERE symbol=? AND CAST(timestamp AS TIME) "
            "BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp", [SYMBOL]).fetchall()
    days = defaultdict(list)
    for d, t, o, h, l, c in rows:
        days[d].append((t.hour * 60 + t.minute, float(o), float(h), float(l), float(c)))
    return days


def ema20_map(days):
    sd = sorted(days)
    rng = {d: max(h for _, _, h, _, _ in b) - min(l for _, _, _, l, _ in b) for d, b in days.items()}
    out, a = {}, 2.0 / (EMA_SPAN + 1)
    for i, d in enumerate(sd):
        prior = sd[max(0, i - 120):i]
        if len(prior) < EMA_SPAN:
            continue
        e = rng[prior[0]]
        for pd in prior[1:]:
            e = a * rng[pd] + (1 - a) * e
        out[d] = e
    return out


def sma(seq, n):
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


# ---------- ★ CAUSAL detection：逐根 streaming，不碰未來 leg 邊界 ----------
def detect_causal(days, ema):
    """完全 causal 重寫。進場窗 = [翻上事件, 下一翻下事件)，不用未來 em。

    ZigZag 翻轉事件是 causal 的（價格自 running 極值反轉 threshold 當下即偵測到，
    且 anchor=該 running 極值為過去已知）。因此我在同一個 streaming 迴圈裡：
      - 維護 ZigZag 狀態（trend/up_ref/dn_ref/ext）→ 取得每個翻轉事件的 bar 與 anchor。
      - 翻上事件當下＝確立（h-anchor≥L2d）：開始在「本上漲相位」內找拉回→站回，取首筆。
      - 本相位於下一個翻下事件結束（價格自波峰反轉 L2d）；在此之前都可進場（含失敗站回）。
    對稱處理 down。每相位至多一筆。
    """
    out = []
    for d in sorted(ema):
        bars = days[d]
        e = ema[d]
        L2d, L3d = L2C * e, L3C * e
        L4d, L5d = L4C * e, L5C * e
        pb_floor = PB_FLOOR_FRAC * e
        closes = [b[4] for b in bars]
        s5 = sma(closes, 5)
        n = len(bars)

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
        done = False                 # 本相位是否已出手或失效（仍續跑 zigzag）

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

            # === 1) 先推進「本相位」的進場邏輯（用截至 i 的資訊，全 causal） ===
            if phase is not None and not done:
                up = phase == "up"
                # 更新續攻方向 running 極值
                if (h > peak) if up else (l < peak):
                    peak = h if up else l
                if abs(peak - anchor) >= L3d:        # 直衝 L3：本相位不交易
                    done = True
                else:
                    if sub == "extend":
                        dip = (peak - l) if up else (h - peak)
                        if dip >= pb_floor:
                            sub = "pullback"
                            pb_ext = l if up else h
                    if sub == "pullback":
                        pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
                        cs, ps = s5[i], s5[i - 1] if i > 0 else None
                        pc = bars[i - 1][4] if i > 0 else None
                        if cs is not None and ps is not None and pc is not None:
                            reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
                            overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
                            if reclaim and not overshoot:
                                depth_frac = ((peak - pb_ext) if up else (pb_ext - peak)) / L2d
                                out.append({
                                    "date": d, "up": up, "side": "bull" if up else "bear",
                                    "entry_i": i, "entry_min": m, "entry": c,
                                    "anchor": anchor, "pb_low": pb_ext, "ema20": e,
                                    "L3d": L3d, "L4d": L4d, "L5d": L5d,
                                    "depth_frac": depth_frac, "peak": peak,
                                })
                                done = True

            # === 2) 再推進 ZigZag streaming（產生翻轉事件 → 開新相位） ===
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
                elif ext - l >= L2d:                  # 翻下事件：確認 pivot high = ext
                    pivot = ext                       # 剛確認的波峰（causal：running max）
                    trend = "down"
                    ext = l
                    open_phase(False, pivot, h, l)    # 下跌相位 anchor = 該波峰
            else:  # trend == "down"
                if l < ext:
                    ext = l
                elif h - ext >= L2d:                  # 翻上事件：確認 pivot low = ext
                    pivot = ext                       # 剛確認的波谷
                    trend = "up"
                    ext = h
                    open_phase(True, pivot, h, l)     # 上漲相位 anchor = 該波谷
    return out


# ---------- 出場模擬（獨立重寫，與 live 同邏輯：停損優先、保守） ----------
def simulate(tc, bars, *, alpha=ALPHA, cost=COST):
    up, entry, anchor, pb_low = tc["up"], tc["entry"], tc["anchor"], tc["pb_low"]
    L3d = tc["L3d"]
    stop = pb_low - alpha * (pb_low - anchor) if up else pb_low + alpha * (anchor - pb_low)
    target = anchor + L3d if up else anchor - L3d
    risk = (entry - stop) if up else (stop - entry)
    fwd = bars[tc["entry_i"] + 1:]
    outcome, exitp, exit_min = "open", bars[-1][4], bars[-1][0]
    for m, o, h, l, c in fwd:
        if (l <= stop) if up else (h >= stop):
            outcome, exitp, exit_min = "loss", stop, m
            break
        if (h >= target) if up else (l <= target):
            outcome, exitp, exit_min = "win", target, m
            break
    pnl = ((exitp - entry) if up else (entry - exitp)) - cost
    return {"outcome": outcome, "pnl": pnl, "pct": pnl / entry * 100,
            "risk": risk, "R": (pnl / risk) if risk > 0 else None, "win": pnl > 0,
            "exitp": exitp, "exit_min": exit_min}


def metrics(trs):
    n = len(trs)
    if not n:
        return None
    pcts = [t["pct"] for t in trs]
    wins = sum(t["win"] for t in trs)
    mean = st.mean(pcts)
    sd = st.pstdev(pcts) if n > 1 else 0
    eq = peak = mdd = 0.0
    cur = mx = 0
    for t in trs:
        eq += t["pct"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if t["win"]:
            cur = 0
        else:
            cur += 1
            mx = max(mx, cur)
    rs = [t["R"] for t in trs if t["R"] is not None]
    return {"N": n, "win%": round(100 * wins / n, 1),
            "EVpt": round(st.mean([t["pnl"] for t in trs]), 1),
            "tot%": round(sum(pcts), 1), "mean%": round(mean, 4),
            "sharpe": round(mean / sd, 3) if sd else 0,
            "mdd%": round(mdd, 1), "maxLoss": mx,
            "avgR": round(st.mean(rs), 2) if rs else 0}


def fmt(m):
    if not m:
        return "N=0"
    return (f"N={m['N']:>4} win={m['win%']:>5}% EV={m['EVpt']:>5}pt tot={m['tot%']:>7}% "
            f"sharpe={m['sharpe']:>6} mdd={m['mdd%']:>6}% maxLoss={m['maxLoss']:>2} avgR={m['avgR']}")


def run(tcs, days):
    return [dict(simulate(tc, days[tc["date"]]), date=tc["date"], entry_min=tc["entry_min"],
                up=tc["up"], tc=tc) for tc in tcs]


def _hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def write_list(trs, list_id, name):
    """把 run() 的結果寫成 chart-ui 清單。"""
    from src.chart_ui.list_writer import write_chart_list
    items = []
    for t in trs:
        tc = t["tc"]
        d = tc["date"].isoformat()
        items.append({
            "time": f"{d} {_hhmm(tc['entry_min'])}:00",
            "exit_time": f"{d} {_hhmm(t['exit_min'])}:00",
            "side": "long" if t["up"] else "short",
            "entry": round(tc["entry"], 1),
            "exit": round(t["exitp"], 1),
            "pnl_pts": round(t["pnl"], 1),
            "return_pct": round(t["pct"], 3),
            "result": "Win" if t["win"] else "Loss",
            "note": f"depth={tc['depth_frac']:.2f} {t['outcome']}",
        })
    p = write_chart_list(list_id, items, name=name)
    print(f"  寫出清單 {p}  (N={len(items)})")


def key(tc):
    return (tc["date"], tc["up"], tc["entry_min"])


def main():
    days = load_days()
    ema = ema20_map(days)
    live = _load_live()

    # cross-check：EMA20 與我獨立算的一致嗎？
    live_ema = live.ema20_map(live.load_all())
    diffs = [abs(ema[d] - live_ema[d]) for d in ema if d in live_ema]
    print(f"[cross-check] EMA20 max abs diff vs live = {max(diffs):.6f}  (應 ≈ 0)\n")

    # 兩套 detection（同樣套用部署濾網：depth>=0.25, 進場 <12:00）
    orig = [t for t in live.detect(days, ema)
            if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]
    caus = [t for t in detect_causal(days, ema)
            if t["depth_frac"] >= MIN_DEPTH_FRAC and t["entry_min"] < NOON]

    print(f"setups（depth>=0.25, <12:00）：  LIVE={len(orig)}   CAUSAL={len(caus)}")
    print(f"（causal 應 >= live：多出的就是 live 被未來 em 濾掉的失敗站回）\n")

    def split(tcs):
        return ([t for t in tcs if t["date"] < OOS_START],
                [t for t in tcs if t["date"] >= OOS_START])

    o_is, o_oos = split(orig)
    c_is, c_oos = split(caus)

    print("=== LIVE（重現現行 backtest.py detect） ===")
    print(f"  IS  {fmt(metrics(run(o_is, days)))}")
    print(f"  OOS {fmt(metrics(run(o_oos, days)))}")
    print(f"  ALL {fmt(metrics(run(orig, days)))}\n")

    print("=== CAUSAL（逐根 streaming，無未來 em 上界） ===")
    print(f"  IS  {fmt(metrics(run(c_is, days)))}")
    print(f"  OOS {fmt(metrics(run(c_oos, days)))}")
    print(f"  ALL {fmt(metrics(run(caus, days)))}\n")

    # 「多出來」的站回（causal 有、live 沒有）—— 若這些是大賠 → 證明前視偏誤
    oset = {key(t) for t in orig}
    extra = [t for t in caus if key(t) not in oset]
    common = [t for t in caus if key(t) in oset]
    print(f"=== 分解 causal 交易 ===")
    print(f"  與 LIVE 重疊  {fmt(metrics(run(common, days)))}")
    print(f"  LIVE 缺漏(extra) {fmt(metrics(run(extra, days)))}")
    print("\n→ 若 extra 勝率/EV 遠低於重疊組，代表 live 用未來 em 系統性濾掉失敗站回（前視偏誤）。")

    # 逐年 causal
    print("\n=== CAUSAL 逐年 ===")
    by_year = defaultdict(list)
    for t in caus:
        by_year[t["date"].year].append(t)
    for y in sorted(by_year):
        print(f"  {y}  {fmt(metrics(run(by_year[y], days)))}")

    # 輸出 chart-ui 清單供肉眼檢視
    print("\n=== 寫出 chart-ui 清單 ===")
    write_list(run(extra, days), "s005-causal-extra",
               "S005 前視偏誤刪掉的失敗站回(529)")
    write_list(run(caus, days), "s005-causal-all",
               "S005 causal 全量站回(含失敗)")


if __name__ == "__main__":
    main()

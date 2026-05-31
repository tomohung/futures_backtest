"""H095 Phase 2 — 路徑回測：用 EstHL 進場，測我們的關卡出場情境表 + trail 變體。

進場模型（乾淨版 EstHL, long-only）：
  - OR = 08:45–08:57 high/low
  - 進場窗 08:58–09:15，首次 close > OR_high 做多
  - 保留濾網：30分20MA 趨勢(Close30>MA30_20)、VWAP 成本(OR_high > max(VWAP1,2)+0.5×SL)
  - 拿掉：OR 寬度濾網、跳過週四五、NVF（本就未實作）── 疑似過度最佳化
  - 初始停損 = 進場價 − 0.25×EmaHL

出場框架（情境表，多方）：
  - 碰 L1(high≥base+L1d) → 停損移 BE（或 ⅔ 鎖）；早於 09:30 瞄 L3、否則瞄 L2
  - 碰 L2 → 早於 10:45 啟動 ride trail 博 L3；否則守 L2(於 L2 了結)
  - 瞄 L2 / 守 L2：靜態於 target 了結
  - 碰 L3 後：trail 繼續收割延伸（fixed 變體則於 L3 了結）
  - 13:45 EOD 平倉
  base = 進場當下的盤中 running session low（與驗證過的階梯定義一致）。
  關卡 EMA-only：L1=.385 L2=.497 L3=.711 ×EMA20(日盤振幅, causal prior-day)。

變體：trail ∈ {fixed, dow, 5ma, kama}；停損政策 ∈ {be, lock23}。
輸出：每組 N、總點數、平均/筆、勝率、期望值、到 L3 率；全期 + OOS(train≤2024/test≥2025)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from src.backtest.runner import load_data_for_orb_est_hl

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}
GATE_0930, GATE_1045, EOD = 570, 645, 825   # 09:30, 10:45, 13:45 (分鐘)
OR_START, OR_END = 525, 537                 # 08:45, 08:57
ENTRY_START, ENTRY_END = 538, 555           # 08:58, 09:15
SL_FRAC = 0.25
VWAP_DAYS = 2


def kama(close, er_p=10, fast=2, slow=30):
    n = len(close); k = np.full(n, np.nan)
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    if n <= er_p:
        return k
    k[er_p] = close[er_p]
    for i in range(er_p + 1, n):
        change = abs(close[i] - close[i - er_p])
        vol = np.sum(np.abs(np.diff(close[i - er_p:i + 1])))
        er = change / vol if vol else 0.0
        sc = (er * (fsc - ssc) + ssc) ** 2
        k[i] = k[i - 1] + sc * (close[i] - k[i - 1])
    return k


def sma(close, p=5):
    return pd.Series(close).rolling(p).mean().to_numpy()


def pivot_low_trail(low, left=2, right=2):
    """每根的『最近已確認 pivot low』(右側 right 根後才確認)，ratchet 不下降。多方移動停損用。"""
    n = len(low); trail = np.full(n, -np.inf); last = -np.inf
    for j in range(n):
        c = j - right
        if c - left >= 0 and c + right < n:
            if low[c] == np.min(low[c - left:c + right + 1]):
                last = max(last, low[c])
        trail[j] = last
    return trail


def simulate(day, ei, base, emahl, ema20, trail_type, stop_policy):
    """回傳 (exit_price, reason, reached_l3)。多方。"""
    h, l, c, mins = day["High"], day["Low"], day["Close"], day["min"]
    entry = c[ei]
    L1, L2, L3 = base + C["L1"] * ema20, base + C["L2"] * ema20, base + C["L3"] * ema20
    stop = entry - SL_FRAC * emahl
    reached1 = reached2 = False
    aim = None
    trail_on = False
    ma5 = sma(c) if trail_type == "5ma" else None
    km = kama(c) if trail_type == "kama" else None
    pl = pivot_low_trail(l) if trail_type == "dow" else None

    n = len(h)
    for j in range(ei + 1, n):
        t = mins[j]
        # 1) 停損 / trail（先檢查不利方向）
        if l[j] <= stop:
            return stop, "stop", reached1 and L3 <= h[:j + 1].max()
        if trail_on:
            if trail_type == "dow":
                if pl[j] > stop:
                    stop = pl[j]           # ratchet 結構停損
                if l[j] <= stop:
                    return stop, "trail_dow", reached2 and h[:j + 1].max() >= L3
            elif trail_type == "5ma" and not np.isnan(ma5[j]) and c[j] < ma5[j]:
                return c[j], "trail_5ma", h[:j + 1].max() >= L3
            elif trail_type == "kama" and not np.isnan(km[j]) and c[j] < km[j]:
                return c[j], "trail_kama", h[:j + 1].max() >= L3
        # 2) 關卡觸及（有利方向）
        if not reached1 and h[j] >= L1:
            reached1 = True
            stop = entry if stop_policy == "be" else base + (2 / 3) * C["L1"] * ema20
            aim = "L3" if t < GATE_0930 else "L2"
        if reached1 and not reached2 and h[j] >= L2:
            reached2 = True
            if t < GATE_1045:
                aim = "L3"
                if trail_type != "fixed":
                    trail_on = True        # 啟動 ride trail
            else:
                return L2, "hold_L2", False    # 守 L2 靜態了結
        if reached1 and aim == "L2" and h[j] >= L2:
            return L2, "take_L2", False        # 晚碰 L1 → 收 L2
        if aim == "L3" and h[j] >= L3:
            if trail_type == "fixed":
                return L3, "take_L3", True     # 靜態目標於 L3 了結
            # trail 變體：繼續收割，不在此了結
    return c[n - 1], "eod", reached1 and h.max() >= L3


def build_entries(df):
    """乾淨 EstHL 進場掃描。回傳 list of dict(date, ei, base, emahl, ema20, entry, day_slice)。"""
    df = df.copy()
    df["date"] = df.index.date
    df["min"] = df.index.hour * 60 + df.index.minute
    # 每日日盤振幅 → causal prior-day EMA20
    rng = df.groupby("date").apply(lambda g: g["High"].max() - g["Low"].min())
    ema20 = rng.shift(1).ewm(span=20, adjust=False).mean()

    out = []
    for d, g in df.groupby("date"):
        g = g.reset_index(drop=False)
        m = g["min"].to_numpy()
        e20 = ema20.get(d)
        if e20 is None or pd.isna(e20):
            continue
        or_mask = (m >= OR_START) & (m <= OR_END)
        if not or_mask.any():
            continue
        or_high = g["High"].to_numpy()[or_mask].max()
        H, L, Cl = g["High"].to_numpy(), g["Low"].to_numpy(), g["Close"].to_numpy()
        emahl = g["EmaHL"].to_numpy(); ma30 = g["MA30_20"].to_numpy(); c30 = g["Close30"].to_numpy()
        vw = [g[f"VWAP{i}"].to_numpy() for i in range(1, VWAP_DAYS + 1)]
        win = np.where((m >= ENTRY_START) & (m <= ENTRY_END) & (Cl > or_high))[0]
        for ei in win:
            if np.isnan(emahl[ei]):
                continue
            sl_dist = SL_FRAC * emahl[ei]
            trend_ok = np.isnan(ma30[ei]) or np.isnan(c30[ei]) or (c30[ei] > ma30[ei])
            bc = [v[ei] for v in vw if not np.isnan(v[ei])]
            cost_ok = (not bc) or (or_high > max(bc) + 0.5 * sl_dist)
            if not (trend_ok and cost_ok):
                continue
            base = L[:ei + 1].min()      # running session low at entry
            out.append({"date": d, "ei": ei, "base": float(base), "emahl": float(emahl[ei]),
                        "ema20": float(e20), "entry": float(Cl[ei]),
                        "day": {"High": H, "Low": L, "Close": Cl, "min": m}})
            break  # 一天最多一筆
    return out


def stats(trades, label):
    if not trades:
        print(f"  {label}: 無交易"); return
    pts = np.array([t["pnl"] for t in trades])
    pct = np.array([t["pnl_pct"] for t in trades])
    l3 = np.mean([t["l3"] for t in trades])
    win = pts > 0
    aw = pts[win].mean() if win.any() else 0
    al = pts[~win].mean() if (~win).any() else 0
    print(f"  {label:<22} N={len(pts):>4}  總={pts.sum():>7.0f}  均={pts.mean():>6.1f}  "
          f"均%={pct.mean():>5.2f}  勝率={win.mean():>4.0%}  均盈={aw:>6.1f} 均虧={al:>6.1f}  到L3={l3:>4.0%}")


def run(entries, trail_type, stop_policy, mask=None):
    res = []
    for e in entries:
        if mask and not mask(e["date"]):
            continue
        px, reason, l3 = simulate(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"],
                                  trail_type, stop_policy)
        pnl = px - e["entry"]
        res.append({"pnl": pnl, "pnl_pct": pnl / e["entry"] * 100, "l3": l3, "reason": reason})
    return res


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    print(f"乾淨 EstHL 進場：{len(entries)} 筆  "
          f"[{entries[0]['date']} ~ {entries[-1]['date']}]\n")

    configs = [("fixed", "be", "靜態目標 (BE)"), ("dow", "be", "Dow低點 trail (BE)"),
               ("5ma", "be", "5MA trail (BE)"), ("kama", "be", "KAMA trail (BE)"),
               ("5ma", "lock23", "5MA trail (⅔鎖) 對照")]

    for period, mask in [("全期", None),
                         ("OOS train ≤2024", lambda d: d.year <= 2024),
                         ("OOS test ≥2025", lambda d: d.year >= 2025)]:
        print(f"=== {period} ===")
        for tt, sp, lab in configs:
            r = run(entries, tt, sp, mask)
            for x in r:
                x["pnl_pct"] = x["pnl_pct"]
            stats(r, lab)
        print()


if __name__ == "__main__":
    main()

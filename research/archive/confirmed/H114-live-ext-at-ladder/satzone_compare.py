"""H114 Phase 2 對撞 — 時點規則 A vs SatZone-only（無效條件 #2）。

SatZone-only 規則：碰 L3 當下,若價格尚未觸及 EstRange_SatUpper（est_range 量加權,生產同款）
→ 仍有空間,持有 L3→L4 trade;若已觸及 → 滿足收手(不持有)。
對撞：A(早碰才持有) vs SatZone(未滿足才持有) 的 IS/OOS 績效 + 2×2 重疊（是否冗餘/獨立加分）。

注意：未套用結算日量 ×1.9 校正（settlement_dates=None）→ 結算日 est_range 略偏小（少數日,影響有限）。
用法：uv run python research/active/H114-live-ext-at-ladder/satzone_compare.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import sys
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
from src.backtest.estimate_hl import compute_vol_estimated_range   # noqa: E402

DB = str(HERE.parents[2] / "data" / "futures.duckdb")
BT = HERE / "results" / "bt_trades.csv"
CUT = time(10, 30)


def satupper_at_cross():
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp").df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    df = compute_vol_estimated_range(df)
    df["d"] = df.index.date
    df["t"] = df.index.time
    out = {}
    for d, g in df.groupby("d"):
        g = g.sort_index()
        sat = g["EstRange_SatUpper"].ffill()
        runhigh = g["High"].cummax()
        out[d] = (list(g["t"]), sat.values, runhigh.values)
    return out


def stats(p):
    n = len(p)
    if n == 0:
        return dict(N=0, sum=0, mean=0, win=np.nan, sharpe=np.nan, maxDD=0, streak=0)
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(eq)).min()
    s = mx = 0
    for x in p:
        s = s + 1 if x < 0 else 0; mx = max(mx, s)
    return dict(N=n, sum=p.sum(), mean=p.mean(), win=(p > 0).mean(),
                sharpe=(p.mean() / p.std() if p.std() > 0 else np.nan), maxDD=dd, streak=mx)


def ln(lab, s):
    return (f"  {lab:<24} N={s['N']:>3} Σ%={s['sum']:>6.2f} 平均%={s['mean']:>6.3f} "
            f"勝率={s['win']:.0%} Sharpe={s['sharpe']:>5.2f} maxDD={s['maxDD']:>6.2f} 連敗={s['streak']}")


def main():
    bt = pd.read_csv(BT); bt["d"] = pd.to_datetime(bt["d"]).dt.date
    bt["tk"] = pd.to_datetime(bt["tk"], format="%H:%M:%S").dt.time
    sa = satupper_at_cross()

    def satisfied(row):
        d, tk = row["d"], row["tk"]
        if d not in sa:
            return np.nan
        ts, sat, rh = sa[d]
        i = -1
        for j, tt in enumerate(ts):
            if tt <= tk:
                i = j
            else:
                break
        if i < 0 or not np.isfinite(sat[i]):
            return np.nan
        return int(rh[i] >= sat[i])      # 碰 L3 當下,running high 是否已觸及 SatUpper

    bt["sat"] = bt.apply(satisfied, axis=1)
    bt["early"] = bt["tk"].apply(lambda t: t <= CUT)
    n_na = int(bt["sat"].isna().sum())
    bt = bt.dropna(subset=["sat"])
    bt["sat"] = bt["sat"].astype(int)

    L = ["=" * 96,
         f"H114 Phase 2 對撞 — 時點A vs SatZone-only　L3 事件 N={len(bt)}（剔除無 SatZone 暖機 {n_na} 日）",
         "持有=該規則認為還有空間;損益% = bracket trade 點數/進場價×100"]

    for seg in ("IS", "OOS"):
        g = bt[bt["is_seg"] == seg]
        L.append("\n" + "─" * 96)
        L.append(f"【{seg}】N={len(g)}　早碰={int(g['early'].sum())}　SatZone未滿足={int((g['sat']==0).sum())}")
        L.append(ln("規則A 早碰才持有", stats(g.loc[g["early"], "hold_pnl_pct"].values)))
        L.append(ln("SatZone 未滿足才持有", stats(g.loc[g["sat"] == 0, "hold_pnl_pct"].values)))
        L.append(ln("基準 always-hold", stats(g["hold_pnl_pct"].values)))
        # 2×2 重疊：時點 × SatZone（看是否同一回事 or 獨立）
        L.append("    2×2 重疊（平均%／N）：")
        for e, elab in [(True, "早碰"), (False, "晚碰")]:
            cells = []
            for s_, slab in [(0, "未滿足"), (1, "已滿足")]:
                sub = g[(g["early"] == e) & (g["sat"] == s_)]["hold_pnl_pct"]
                cells.append(f"{slab}: {sub.mean():+.3f}(n{len(sub)})" if len(sub) else f"{slab}: -(n0)")
            L.append(f"      {elab}｜" + "　".join(cells))

    # 重疊度
    tab = pd.crosstab(bt["early"], bt["sat"])
    agree = ((bt["early"] & (bt["sat"] == 0)) | (~bt["early"] & (bt["sat"] == 1))).mean()
    L.append("\n" + "─" * 96)
    L.append(f"時點(早碰=持有) 與 SatZone(未滿足=持有) 判定一致率 = {agree:.0%}（高=冗餘,低=獨立）")
    L.append(f"  交叉表 early×sat:\n{tab.to_string()}")

    L.append("\n  ⚠ 無結算量校正;單一窗;無手續費滑價。")
    txt = "\n".join(L)
    print(txt)
    (HERE / "results" / "satzone_raw.txt").write_text(txt + "\n")
    print(f"\n存：{HERE/'results'/'satzone_raw.txt'}")


if __name__ == "__main__":
    main()

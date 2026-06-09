#!/usr/bin/env python3
"""H110 Phase 2 — Reversal 方向濾網改用 09:10 DCI（base/dci/both 三組並排回測）。

唯一變數＝方向來源（dir_mode），其餘 reversal 邏輯與 live (S002) 完全相同。
  base : 5m120MA 斜率（live）
  dci  : 09:10 |dci_long| 落強分位(前40%) → sign(dci_long)（可翻向）；否則退回 base
  both : 強分位且 dci 與 base 同向才進；強分位但不同向 → skip；非強分位退回 base

DCI 注入：把每日 dci_long(09:10)=W-20 thrust 的 方向 + 強分位 bool 廣播成 bar 欄位
  DCI_Dir / DCI_Strong，**僅 09:10 後且窗內日有值，其餘 NaN**（因果 + 退回 base）。
  來源：H110 explore.py 產出的 results/dci_checkpoint_panel.csv（th_09:10）。

窗：load 自 2025-03-01 暖機，**交易只計 2025-06-02~2026-02-26**（DCI 可算窗）。
硬限制：窗內小樣本、**in-sample only**（OOS 待資料擴充）、偏多頭、上市-only。
關鍵考驗：方向命中 edge 是否轉成實際 P&L（reversal 是 fade，方向對≠賺）。

Usage: uv run python research/active/H110-reversal-dci-direction/backtest.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

HERE = Path(__file__).parent
PANEL = HERE / "results" / "dci_checkpoint_panel.csv"
WIN_LO, WIN_HI = date(2025, 6, 2), date(2026, 2, 26)
WARMUP = "2025-03-01"
STRONG_Q = 0.60   # 強分位 = |th_09:10| 前 40%（Q4-5）
CKPT_MIN = 9 * 60 + 10   # 09:10

MODES = ["base", "dci", "both", "dcilong"]
LIVE_PARAMS = dict(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                   signal_skip=0, sat_pullback_fraction=0.5)


def load_with_dci():
    df = load_data_for_reversal(start=WARMUP, end="2026-02-28")
    panel = pd.read_csv(PANEL)
    panel["d"] = pd.to_datetime(panel.iloc[:, 0]).dt.date  # 第一欄為 index 'd'
    th = panel.set_index("d")["th_09:10"]
    cut = th.abs().quantile(STRONG_Q)
    day_dir = np.sign(th)                       # ±1
    day_strong = (th.abs() >= cut).astype(float)  # 1/0

    bar_date = pd.Series(df.index.date, index=df.index)
    bar_min = df.index.hour * 60 + df.index.minute
    causal = (bar_min >= CKPT_MIN)              # 只 09:10 後給值
    dd = bar_date.map(day_dir)                  # 非窗日→NaN
    ds = bar_date.map(day_strong)
    df["DCI_Dir"] = np.where(causal, dd, np.nan)
    df["DCI_Strong"] = np.where(causal, ds, np.nan)
    return df, day_dir, day_strong


def run_mode(df, mode):
    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(dir_mode=mode, **LIVE_PARAMS)
    t = stats["_trades"].copy()
    t["ret_pct"] = t["PnL"] / t["EntryPrice"] * 100.0
    t["d"] = pd.to_datetime(t["EntryTime"]).dt.date
    return t[(t["d"] >= WIN_LO) & (t["d"] <= WIN_HI)].copy()   # 只計窗內


def max_consec_losses(ret):
    mx = cur = 0
    for r in ret:
        cur = cur + 1 if r < 0 else 0
        mx = max(mx, cur)
    return mx


def max_drawdown_pct(ret):
    eq = np.cumsum(ret); peak = np.maximum.accumulate(eq)
    return float((eq - peak).min()) if len(ret) else 0.0


def metrics(t):
    n = len(t)
    if n == 0:
        return dict(n=0, total=0, avg=0, sharpe=0, pf=0, win=0, mcl=0, mdd=0)
    r = t["ret_pct"].values
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=n, total=r.sum(), avg=r.mean(),
                sharpe=(r.mean() / r.std(ddof=1)) if r.std(ddof=1) > 0 else 0,
                pf=(wins / losses) if losses > 0 else float("inf"),
                win=(r > 0).mean() * 100, mcl=max_consec_losses(r),
                mdd=max_drawdown_pct(r))


def fmt(label, m):
    pf = f"{m['pf']:.2f}" if np.isfinite(m["pf"]) else "inf"
    return (f"  {label:<8} n={m['n']:>3}  總損益%={m['total']:>7.2f}  avg={m['avg']:>6.3f}  "
            f"Sharpe={m['sharpe']:>6.3f}  PF={pf:>5}  勝率={m['win']:>5.1f}%  "
            f"最大連敗={m['mcl']:>2}  最大回撤%={m['mdd']:>7.2f}")


def main():
    print("Loading reversal data + injecting 09:10 DCI ...")
    df, day_dir, day_strong = load_with_dci()
    res = {m: run_mode(df, m) for m in MODES}

    L = ["=" * 92,
         f"H110 Phase 2 — Reversal 方向改 09:10 DCI  窗 {WIN_LO}~{WIN_HI}（in-sample only，上市-only，偏多頭）",
         "唯一變數=方向來源；其餘 reversal 邏輯同 live(S002)"]
    L.append("\n" + "─" * 92)
    L.append("全部交易：")
    for m in MODES:
        L.append(fmt(m, metrics(res[m])))
    # 多/空分開（focus：只看多方訊號效果）
    L.append("\n  多方單(Size>0)：")
    for m in MODES:
        L.append(fmt(m, metrics(res[m][res[m]["Size"] > 0])))
    L.append("  空方單(Size<0)：")
    for m in MODES:
        L.append(fmt(m, metrics(res[m][res[m]["Size"] < 0])))

    # ── 逐筆歸因：variant − base 的來源拆解（按日對齊）──
    def attrib(name):
        bd = res["base"].set_index("d"); vd = res[name].set_index("d")
        bret, vret = bd["ret_pct"], vd["ret_pct"]
        bsz, vsz = bd["Size"], vd["Size"]
        shared = set(bd.index) & set(vd.index)
        same = [x for x in shared if np.sign(bsz[x]) == np.sign(vsz[x])]
        flip = [x for x in shared if np.sign(bsz[x]) != np.sign(vsz[x])]
        bonly, vonly = sorted(set(bd.index) - set(vd.index)), sorted(set(vd.index) - set(bd.index))
        out = [f"\n  〔{name} − base〕按進場日對齊：",
               f"    同向 N={len(same)}：相同={bret[same].sum():+.2f}　"
               f"翻向 N={len(flip)}：base={bret[flip].sum():+.2f}→{name}={vret[flip].sum():+.2f}",
               f"    base獨有 N={len(bonly)}：放棄={bret[bonly].sum():+.2f}　"
               f"{name}獨有 N={len(vonly)}：多賺={vret[vonly].sum():+.2f}",
               f"    → {name}−base = {vret.sum() - bret.sum():+.2f}"]
        return out

    L.append("\n" + "─" * 92)
    L.append("逐筆歸因（改善來自哪裡）：")
    for name in ("dci", "dcilong"):
        L += attrib(name)

    L.append("\n  ⚠ in-sample only、N 小、偏多頭、上市-only → 指示性，OOS 待資料擴充。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "backtest_raw.txt").write_text(txt + "\n")
    for m in MODES:
        res[m].to_csv(out / f"trades_{m}.csv", index=False)
    print(f"\n存：{out/'backtest_raw.txt'}")


if __name__ == "__main__":
    main()

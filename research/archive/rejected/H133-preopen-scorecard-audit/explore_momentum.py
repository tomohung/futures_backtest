#!/usr/bin/env python3
"""
H133 Phase 1c — 其它動能指標（比 MACD 直觀）盤前預判早盤方向

檢驗假設：不是 MACD 的問題，而是「動能衝進開盤 → 早盤 mean-revert」的市場性質。
若換直觀動能指標仍同方向 fade，即為 robust 現象。

指標（皆 causal，取到 P 日日盤收；ref=夜盤(P)收當開盤前基準）：
  rsi14      : RSI(14) 日線 > 50 → 多
  roc5       : sign(ref - close[P-5]) → 多/空
  ema20d     : ref > EMA20(日線 close) → 多
  night_mom  : ref - close[P]（隔夜漲跌）> 0 → 多

另做 RSI(14) 五分位 → 早盤(09:00-10:30) mean net 與 P(漲)，看是否單調 fade。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore_momentum.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from explore import (load_data, build_sessions, eval_signal, WINDOWS, COST_RT)


def rsi(close, period=14):
    close = np.asarray(close, dtype=float)
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing
    ag = np.full_like(close, np.nan)
    al = np.full_like(close, np.nan)
    if len(close) <= period:
        return np.full_like(close, 50.0)
    ag[period] = gain[1:period + 1].mean()
    al[period] = loss[1:period + 1].mean()
    for i in range(period + 1, len(close)):
        ag[i] = (ag[i - 1] * (period - 1) + gain[i]) / period
        al[i] = (al[i - 1] * (period - 1) + loss[i]) / period
    rs = ag / np.where(al == 0, np.nan, al)
    out = 100 - 100 / (1 + rs)
    out[al == 0] = 100.0
    return out


def ema(close, period):
    close = np.asarray(close, dtype=float)
    out = np.full_like(close, np.nan)
    a = 2.0 / (period + 1)
    out[0] = close[0]
    for i in range(1, len(close)):
        out[i] = close[i] * a + out[i - 1] * (1 - a)
    return out


VARIANTS = {
    "s_rsi": "RSI(14)日線>50",
    "s_roc5": "ROC(5)日線",
    "s_ema20d": "價>EMA20日線",
    "s_nightmom": "隔夜動能(夜收>昨日盤收)",
}


def build(ds, ns, roll_dates, vix_map):
    ds = ds.sort_values("d").reset_index(drop=True)
    tdays = ds["d"].tolist()
    dclose = ds["day_close"].values.astype(float)
    ds_idx = ds.set_index("d")
    night_close = dict(zip(ns["P"], ns["night_close"]))

    rsi_arr = rsi(dclose, 14)
    ema_arr = ema(dclose, 20)

    rows = []
    for i in range(6, len(tdays)):  # 需 ROC5 + warmup
        D, P = tdays[i], tdays[i - 1]
        if D in roll_dates or P not in night_close:
            continue
        ref = night_close[P]
        if ref is None or np.isnan(ref):
            continue
        rsi_p = rsi_arr[i - 1]          # P 收的 RSI
        ema_p = ema_arr[i - 1]
        close_p = dclose[i - 1]
        close_p5 = dclose[i - 6]

        rec = {"D": D, "year": pd.Timestamp(D).year, "vix": vix_map.get(P, np.nan),
               "rsi": rsi_p}
        rec["s_rsi"] = "long" if rsi_p > 50 else "short"
        rec["s_roc5"] = "long" if ref > close_p5 else "short"
        rec["s_ema20d"] = "long" if ref > ema_p else "short"
        rec["s_nightmom"] = "long" if ref > close_p else "short"
        for name in WINDOWS:
            rec[f"ret_{name}"] = ds_idx.at[D, f"win_{name}_ret"]
        rows.append(rec)
    return pd.DataFrame(rows)


def main():
    bars, roll_dates, vix_map = load_data()
    ds, ns, day = build_sessions(bars)
    df = build(ds, ns, roll_dates, vix_map)
    print(f"N={len(df)}  {df['D'].min()} ~ {df['D'].max()}\n")

    for win in WINDOWS:
        print(f"{'='*72}\n窗口 {win}  base_up={(df[f'ret_{win}']>0).mean():.3f}\n{'='*72}")
        for sig, label in VARIANTS.items():
            r = eval_signal(df, sig, win)
            print(f"  {label} ({sig}) N={r['N']} 多{r['n_long']}/空{r['n_short']}")
            print(f"     hit={r['hit_rate']:.3f} lift(mix)={r['lift_mix']:+.3f} "
                  f"net={r['mean_net']:+.1f} PF={r['pf']} 逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"     逐年net: {yr}")
        print()

    # RSI 五分位 → 早盤 fade 檢驗
    print(f"{'='*72}\nRSI(14) 五分位 vs 早盤 09:00-10:30 報酬（fade 單調性檢驗）\n{'='*72}")
    d = df.dropna(subset=["rsi", "ret_09:00-10:30"]).copy()
    d["q"] = pd.qcut(d["rsi"], 5, labels=["Q1最低","Q2","Q3","Q4","Q5最高"])
    for q, g in d.groupby("q", observed=True):
        ret = g["ret_09:00-10:30"].values
        print(f"  {q}: n={len(g)}  RSI[{g['rsi'].min():.0f}-{g['rsi'].max():.0f}]  "
              f"早盤 mean={ret.mean():+.1f}  median={np.median(ret):+.1f}  P(漲)={ (ret>0).mean():.3f}")
    print("\n  → 若 Q5(高動能) 早盤報酬顯著 < Q1，即『動能衝進開盤→早盤fade』單調成立。")


if __name__ == "__main__":
    main()

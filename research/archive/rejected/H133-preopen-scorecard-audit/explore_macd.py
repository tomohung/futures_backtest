#!/usr/bin/env python3
"""
H133 Phase 1b — 1H MACD hist「動能」變體 vs「位準」

回應提問：hist≥0（位準）已證死，但 hist 遞增 / 黃金交叉（動能）呢？
能否提示日盤早盤上漲？

變體（皆 causal，取 D 日 08:00 前最後一根 1H bar 的 hist_j 與前一根 hist_prev）：
  lvl       : hist_j >= 0                          → 多 / 空
  rise      : hist_j >  hist_prev                  → 多 / 空
  lvl_rise  : hist_j>=0 且遞增 →多; hist_j<0 且遞減 →空; 其餘 neutral
  crossup   : hist 由負翻正(當根)→多; 由正翻負→空; 其餘 neutral

另報「只看多方投票」子集：P(早盤漲 | 喊多) 與 net P&L。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore_macd.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from explore import (load_data, build_sessions, build_1h_macd,
                     eval_signal, WINDOWS, COST_RT)


VARIANTS = {
    "s_lvl": "hist≥0（位準·基準）",
    "s_rise": "hist 遞增（動能）",
    "s_lvl_rise": "hist≥0 且遞增 / <0 且遞減",
    "s_crossup": "黃金/死亡交叉當根",
}


def build_macd_variants(ds, h1, roll_dates, vix_map):
    ds = ds.sort_values("d").reset_index(drop=True)
    tdays = ds["d"].tolist()
    ds_idx = ds.set_index("d")
    h1_ts = h1["h"].values.astype("datetime64[ns]")
    hist = h1["hist"].values

    rows = []
    for i in range(1, len(tdays)):
        D = tdays[i]
        P = tdays[i - 1]
        if D in roll_dates:
            continue
        cut = np.datetime64(pd.Timestamp(D) + pd.Timedelta(hours=8))
        j = np.searchsorted(h1_ts, cut, side="left") - 1
        if j < 27:
            continue
        hj, hp = hist[j], hist[j - 1]

        rec = {"D": D, "year": pd.Timestamp(D).year, "vix": vix_map.get(P, np.nan)}
        rec["s_lvl"] = "long" if hj >= 0 else "short"
        rec["s_rise"] = "long" if hj > hp else "short"
        if hj >= 0 and hj > hp:
            rec["s_lvl_rise"] = "long"
        elif hj < 0 and hj < hp:
            rec["s_lvl_rise"] = "short"
        else:
            rec["s_lvl_rise"] = None
        if hj >= 0 and hp < 0:
            rec["s_crossup"] = "long"
        elif hj < 0 and hp >= 0:
            rec["s_crossup"] = "short"
        else:
            rec["s_crossup"] = None

        for name in WINDOWS:
            rec[f"ret_{name}"] = ds_idx.at[D, f"win_{name}_ret"]
        rows.append(rec)
    return pd.DataFrame(rows)


def long_only(df, sig, win):
    """只看多方投票：P(早盤漲|喊多) 與 net P&L。"""
    rc = f"ret_{win}"
    d = df[df[sig] == "long"].dropna(subset=[rc])
    if len(d) == 0:
        return None
    ret = d[rc].values
    up = (ret > 0).mean()
    net = ret - COST_RT
    yr_pos = 0
    yrs = sorted(d["year"].unique())
    for y in yrs:
        if (d.loc[d["year"] == y, rc].values - COST_RT).mean() > 0:
            yr_pos += 1
    return {"n": len(d), "p_up": round(float(up), 3),
            "mean_net": round(float(net.mean()), 1),
            "yrs_pos": yr_pos, "yrs_tot": len(yrs)}


def main():
    bars, roll_dates, vix_map = load_data()
    ds, ns, day = build_sessions(bars)
    h1 = build_1h_macd(bars)
    df = build_macd_variants(ds, h1, roll_dates, vix_map)
    print(f"N={len(df)}  {df['D'].min()} ~ {df['D'].max()}\n")

    for win in WINDOWS:
        print(f"{'='*72}\n窗口 {win}   base_up={(df[f'ret_{win}']>0).mean():.3f}\n{'='*72}")
        for sig, label in VARIANTS.items():
            r = eval_signal(df, sig, win)
            lo = long_only(df, sig, win)
            if r is None:
                print(f"  {label}: 無樣本")
                continue
            print(f"  {label} ({sig})  N={r['N']} 多{r['n_long']}/空{r['n_short']}")
            print(f"     [雙向] hit={r['hit_rate']:.3f} lift(mix)={r['lift_mix']:+.3f} "
                  f"net={r['mean_net']:+.1f} PF={r['pf']} 逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            if lo:
                print(f"     [只多] P(漲|喊多)={lo['p_up']:.3f} net={lo['mean_net']:+.1f} "
                      f"逐年正={lo['yrs_pos']}/{lo['yrs_tot']} (n={lo['n']})")
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"     逐年net(雙向): {yr}")
        print()


if __name__ == "__main__":
    main()

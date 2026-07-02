#!/usr/bin/env python3
"""
H133 Phase 2 — 開盤後確認訊號（decision 移到 09:15，交易在其後，無 lookahead）

盤前動能已證無 edge。前人唯一找到真 edge 的區域是開盤後（H018：OR 段量比 @09:30）。
本腳本用同一 harness 測開盤後確認訊號。

決策點 09:15（30 分 opening range, OR）；交易窗口 09:15→10:30、09:15→11:30。
另測決策點 09:30（45 分 OR）→ 09:30→11:30。

訊號（皆用 OR 期間資料，決策時點後才交易）：
  ordir      : sign(OR_close - OR_open)  開盤段方向 → 順勢
  orbreak    : OR_close 在 [low,high] 位置 >0.66→多 / <0.33→空 / 其餘 neutral（收在端點=突破續勢）
  ordir_volhi: ordir 但僅當 OR 量比>=1.0（H018 濾網），否則 neutral
  ordir_volhi_skipTF: 再加「跳週四五」（H018 confirmed），否則 neutral

OR 量比 = OR_vol(D) / 近 20 交易日 OR_vol 中位（causal）。
成本 3 點/邊（rt 6）。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore_postopen.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from explore import load_data, build_sessions, eval_signal, COST_RT


# 決策點 → 交易窗口（entry=決策點 close, exit=窗口終點 close）
SETUPS = {
    "OR30": {  # 08:45-09:15 opening range, 決策 09:15
        "or0": "08:45:00", "or1": "09:15:00",
        "trades": {"09:15-10:30": "10:30:00", "09:15-11:30": "11:30:00"},
    },
    "OR45": {  # 08:45-09:30, 決策 09:30
        "or0": "08:45:00", "or1": "09:30:00",
        "trades": {"09:30-11:30": "11:30:00"},
    },
}


def per_day_features(day):
    """每日 OR 聚合 + 各決策點/窗口終點 close。"""
    d = day.copy()
    d["ts"] = d["timestamp"].dt.strftime("%H:%M:%S")
    d["d"] = d["timestamp"].dt.date
    out = {}
    for name, cfg in SETUPS.items():
        m = (d["ts"] >= cfg["or0"]) & (d["ts"] <= cfg["or1"])
        sub = d[m]
        g = sub.groupby("d")
        agg = g.agg(
            or_open=("open", lambda s: s.iloc[0]),
            or_close=("close", lambda s: s.iloc[-1]),
            or_high=("high", "max"),
            or_low=("low", "min"),
            or_vol=("volume", "sum"),
        )
        out[name] = agg
    # 各窗口終點 close（含 09:15/09:30 決策 close 已在 or_close）
    ends = {}
    for name, cfg in SETUPS.items():
        for wname, t1 in cfg["trades"].items():
            mm = d["ts"] <= t1
            gg = d[mm].groupby("d")
            ends[wname] = gg["close"].apply(lambda s: s.iloc[-1])
    return out, ends


def build(day, roll_dates, vix_map):
    feats, ends = per_day_features(day)
    ds_dates = sorted(day["timestamp"].dt.date.unique())

    rows = []
    for name, cfg in SETUPS.items():
        agg = feats[name]
        # OR 量比：近 20 交易日中位（causal）
        agg = agg.reindex(ds_dates)
        or_vol = agg["or_vol"]
        med20 = or_vol.shift(1).rolling(20, min_periods=10).median()
        agg["vol_ratio"] = or_vol / med20

        for D in ds_dates:
            if D in roll_dates or D not in agg.index:
                continue
            r = agg.loc[D]
            if pd.isna(r["or_close"]) or pd.isna(r["or_open"]):
                continue
            rng = r["or_high"] - r["or_low"]
            pos = (r["or_close"] - r["or_low"]) / rng if rng > 0 else 0.5
            wd = pd.Timestamp(D).weekday()

            rec = {"D": D, "setup": name, "year": pd.Timestamp(D).year,
                   "vix": vix_map.get(D, np.nan), "wd": wd,
                   "vol_ratio": r["vol_ratio"]}
            # 方向
            ordir = "long" if r["or_close"] > r["or_open"] else "short"
            rec["s_ordir"] = ordir
            rec["s_orbreak"] = "long" if pos > 0.66 else ("short" if pos < 0.33 else None)
            volhi = (not pd.isna(r["vol_ratio"])) and r["vol_ratio"] >= 1.0
            rec["s_ordir_volhi"] = ordir if volhi else None
            rec["s_ordir_volhi_skipTF"] = ordir if (volhi and wd not in (3, 4)) else None

            for wname, t1 in cfg["trades"].items():
                entry = r["or_close"]
                exit_ = ends[wname].get(D, np.nan)
                rec[f"ret_{wname}"] = (exit_ - entry) if not pd.isna(exit_) else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


SIGNALS = {
    "s_ordir": "開盤段方向（順勢）",
    "s_orbreak": "OR 收盤突破位置",
    "s_ordir_volhi": "開盤方向 + OR量比≥1.0",
    "s_ordir_volhi_skipTF": "方向+量比≥1.0+跳週四五",
}


def main():
    bars, roll_dates, vix_map = load_data()
    ds, ns, day = build_sessions(bars)
    df = build(day, roll_dates, vix_map)

    for setup, cfg in SETUPS.items():
        sub = df[df["setup"] == setup]
        print(f"\n{'#'*72}\nSETUP {setup}  (OR {cfg['or0']}-{cfg['or1']}, 決策後交易)  N={len(sub)}\n{'#'*72}")
        for wname in cfg["trades"]:
            rc = f"ret_{wname}"
            print(f"\n{'='*66}\n交易窗口 {wname}  base_up={(sub[rc]>0).mean():.3f} "
                  f"mean={sub[rc].mean():+.1f}\n{'='*66}")
            for sig, label in SIGNALS.items():
                r = eval_signal(sub, sig, wname)
                if r is None:
                    print(f"  {label}: 無樣本")
                    continue
                print(f"  {label} ({sig}) N={r['N']} 多{r['n_long']}/空{r['n_short']}")
                print(f"     hit={r['hit_rate']:.3f} lift(mix)={r['lift_mix']:+.3f} "
                      f"net={r['mean_net']:+.1f} PF={r['pf']} win={r['win_rate']:.3f} "
                      f"逐年正={r['yrs_pos']}/{r['yrs_tot']}")
                yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
                print(f"     逐年net: {yr}")


if __name__ == "__main__":
    main()

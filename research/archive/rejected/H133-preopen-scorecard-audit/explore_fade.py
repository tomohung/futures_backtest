#!/usr/bin/env python3
"""
H133 追加 — (A) 反向運用「hist≥0 且遞增」確認版  (B) RSI 超買超賣逆勢

動機：
  (A) s_lvl_rise（動能確認版）在順勢方向是反預測（P(漲|多)<base）。能否反過來 fade？
      關鍵：反向毛利要負得夠深打贏 2×成本，且逐年成立（否則是 overfit 反轉）。
  (B) 前面只測 RSI>50 當順勢；沒測 RSI 極端當逆勢（超買→空、超賣→多）。補上。

同一 harness（含 gross/net、逐年）。成本 3 點/邊（rt 6）。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore_fade.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from explore import load_data, build_sessions, build_1h_macd, eval_signal, WINDOWS
from explore_macd import build_macd_variants
from explore_momentum import rsi


def flip(s):
    return {"long": "short", "short": "long"}.get(s, None)


def main():
    bars, roll, vix = load_data()
    ds, ns, day = build_sessions(bars)

    # ── (A) 反向 s_lvl_rise ────────────────────────────────────────
    h1 = build_1h_macd(bars)
    dfm = build_macd_variants(ds, h1, roll, vix)
    dfm["s_lvlrise_fwd"] = dfm["s_lvl_rise"]
    dfm["s_lvlrise_rev"] = dfm["s_lvl_rise"].map(flip)

    print("="*74)
    print("(A) hist≥0且遞增 —— 順勢(fwd) vs 反向(rev)，看 gross 是否負得夠深打贏成本")
    print("="*74)
    for win in ["09:00-10:30", "08:45-11:30"]:
        print(f"\n  窗口 {win}  base_up={(dfm[f'ret_{win}']>0).mean():.3f}")
        for col, lab in [("s_lvlrise_fwd", "順勢"), ("s_lvlrise_rev", "反向fade")]:
            r = eval_signal(dfm, col, win)
            if r is None:
                print(f"    {lab}: 無樣本"); continue
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"    {lab}: N={r['N']} hit={r['hit_rate']:.3f} "
                  f"gross={r['mean_gross']:+.1f} net={r['mean_net']:+.1f} PF={r['pf']} "
                  f"逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            print(f"         逐年net: {yr}")
    print("\n  註：反向 net ≈ −gross_fwd − 成本；只有 gross_fwd 負得遠超 2×rt(=12) 才有戲。")

    # ── (B) RSI 超買超賣逆勢 ──────────────────────────────────────
    ds2 = ds.sort_values("d").reset_index(drop=True)
    dclose = ds2["day_close"].values.astype(float)
    rsi_arr = rsi(dclose, 14)
    tdays = ds2["d"].tolist()
    ds_idx = ds2.set_index("d")
    ns_close = dict(zip(ns["P"], ns["night_close"]))

    rows = []
    for i in range(15, len(tdays)):
        D, P = tdays[i], tdays[i - 1]
        if D in roll or P not in ns_close:
            continue
        rv = rsi_arr[i - 1]
        rec = {"D": D, "year": pd.Timestamp(D).year, "vix": vix.get(P, np.nan), "rsi": rv}
        # 逆勢：超買→空、超賣→多
        rec["mr_70_30"] = "short" if rv > 70 else ("long" if rv < 30 else None)
        rec["mr_80_20"] = "short" if rv > 80 else ("long" if rv < 20 else None)
        rec["mr_75_25"] = "short" if rv > 75 else ("long" if rv < 25 else None)
        for w in WINDOWS:
            rec[f"ret_{w}"] = ds_idx.at[D, f"win_{w}_ret"]
        rows.append(rec)
    dfr = pd.DataFrame(rows)

    print("\n" + "="*74)
    print("(B) RSI(14)日線 超買超賣逆勢（超買→空 / 超賣→多）")
    print("="*74)
    for col, lab in [("mr_70_30", "70/30"), ("mr_75_25", "75/25"), ("mr_80_20", "80/20")]:
        d = dfr[dfr[col].notna()]
        nob = (d[col] == "short").sum()
        nos = (d[col] == "long").sum()
        print(f"\n  門檻 {lab}  觸發天數={len(d)}（超買空{nob}/超賣多{nos}）")
        for win in ["09:00-10:30", "08:45-11:30"]:
            r = eval_signal(dfr, col, win)
            if r is None:
                print(f"    {win}: 無樣本"); continue
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"    {win}: N={r['N']} hit={r['hit_rate']:.3f} lift={r['lift_mix']:+.3f} "
                  f"gross={r['mean_gross']:+.1f} net={r['mean_net']:+.1f} PF={r['pf']} "
                  f"逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            print(f"         逐年net: {yr}")


if __name__ == "__main__":
    main()

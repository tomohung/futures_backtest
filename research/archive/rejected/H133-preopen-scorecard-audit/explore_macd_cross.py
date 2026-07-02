#!/usr/bin/env python3
"""
H133 追加驗證 — 黃金交叉「當根」樣本過少之疑問

背景：explore_macd.py 的 s_crossup 僅 45 筆。原因是「當根」定義要求 MACD 零軸交叉
精準落在盤前最後一根夜盤 1H bar（05:00 那根）→ 每天唯一 anchor bar 中獎機率極低。

本腳本：
  1) 驗證 anchor bar = 夜盤 05:00 那根（前一根 04:00）。
  2) 改用合理定義「近 K 根內曾黃金交叉且目前 hist>=0 → 多」（死叉→空），
     樣本放大到 194~832，重測早盤方向 edge。

結論：K=3/6/12 皆負、逐年 0~2/6 → 原 0.652 為 N=23 小樣本幻覺；黃金交叉（當根或近期）
對早盤方向皆無 edge。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore_macd_cross.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from explore import (load_data, build_sessions, build_1h_macd,
                     eval_signal, WINDOWS)


def main():
    bars, roll, vix = load_data()
    ds, ns, day = build_sessions(bars)
    h1 = build_1h_macd(bars)
    h1_ts = h1["h"].values.astype("datetime64[ns]")
    hist = h1["hist"].values
    tdays = ds.sort_values("d")["d"].tolist()
    ds_idx = ds.sort_values("d").set_index("d")

    print("=== anchor bar（D 08:00 前最後一根 1H）示範 ===")
    for D in tdays[500:505]:
        cut = np.datetime64(pd.Timestamp(D) + pd.Timedelta(hours=8))
        j = np.searchsorted(h1_ts, cut, side="left") - 1
        print(f"  D={D}  anchor={pd.Timestamp(h1_ts[j])}  前一根={pd.Timestamp(h1_ts[j-1])}")

    def build_freshcross(K):
        rows = []
        for i in range(1, len(tdays)):
            D, P = tdays[i], tdays[i - 1]
            if D in roll:
                continue
            cut = np.datetime64(pd.Timestamp(D) + pd.Timedelta(hours=8))
            j = np.searchsorted(h1_ts, cut, side="left") - 1
            if j < 27 + K:
                continue
            gc = any(hist[m] >= 0 and hist[m - 1] < 0 for m in range(j - K + 1, j + 1))
            dc = any(hist[m] < 0 and hist[m - 1] >= 0 for m in range(j - K + 1, j + 1))
            side = None
            if hist[j] >= 0 and gc:
                side = "long"
            elif hist[j] < 0 and dc:
                side = "short"
            rec = {"D": D, "year": pd.Timestamp(D).year, "vix": vix.get(P, np.nan), "s": side}
            for w in WINDOWS:
                rec[f"ret_{w}"] = ds_idx.at[D, f"win_{w}_ret"]
            rows.append(rec)
        return pd.DataFrame(rows)

    print("\n=== 近 K 根內曾黃金交叉且目前 hist>=0 → 多（死叉→空）===")
    for K in (3, 6, 12):
        df = build_freshcross(K)
        n_sig = int(df["s"].notna().sum())
        print(f"\n-- K={K} --  有訊號天數={n_sig}/{len(df)}")
        for w in ["09:00-10:30", "08:45-11:30"]:
            r = eval_signal(df, "s", w)
            if r is None:
                print(f"   {w}: 無樣本")
                continue
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"   {w}: N={r['N']}(多{r['n_long']}/空{r['n_short']}) hit={r['hit_rate']:.3f} "
                  f"lift={r['lift_mix']:+.3f} net={r['mean_net']:+.1f} PF={r['pf']} "
                  f"逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            print(f"       逐年: {yr}")


if __name__ == "__main__":
    main()

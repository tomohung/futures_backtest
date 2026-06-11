"""H118 補：條件接續 — TX 摸到關卡『那一刻』NYF 的強度，能否預測續攻下一關？

P(L4│已達L3) 與 P(L5│已達L4) 是基準接續率（cf. ladder_reach_timing_map）。
問題：在 TX 觸 L3 的當下分鐘，NYF 的延伸強度 ext_NYF(t_L3)，是否鑑別「會不會續到 L4」？
（TX 站 L3 時自身位置固定 ≈0.711，故 NYF 強度是正交額外資訊。）

forward 非 tautology：續攻判斷取「觸關時點之後」的 high。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explore import DB, PREOPEN_MIN_TICKS

L3, L4, L5 = 0.711, 0.977, 1.30


def load_tx_min(conn):
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low
        FROM ohlcv_1m WHERE symbol='TX'
          AND CAST(timestamp AS TIME) BETWEEN TIME '08:45' AND TIME '13:45'
        ORDER BY d, t
    """).df()
    df["t"] = df["t"].astype(str)
    day = df.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    o = df[df["t"] == "08:45:00"][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(o, on="d").sort_values("d").reset_index(drop=True)
    day["ema20"] = (day["hi"] - day["lo"]).shift(1).ewm(span=20, adjust=False).mean()
    return df, day.set_index("d")


def load_nyf_min(conn, symbol):
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low,
               close, tick_count
        FROM aux_futures_1m WHERE symbol=? ORDER BY d, t
    """, [symbol]).df()
    df["t"] = df["t"].astype(str)
    day = df.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    o = df[df["t"] == "08:45:00"][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(o, on="d").sort_values("d").reset_index(drop=True)
    day["ema20"] = (day["hi"] - day["lo"]).shift(1).ewm(span=20, adjust=False).mean()
    pre = df[(df["t"] >= "08:45:00") & (df["t"] <= "08:59:00")]
    day = day.merge(pre.groupby("d")["tick_count"].sum().rename("preticks").reset_index(),
                    on="d", how="left")
    return df, day.set_index("d")


def report(p, label, rows, str_col, cont_col):
    df = pd.DataFrame(rows).dropna(subset=[str_col, cont_col])
    n = len(df)
    base = df[cont_col].mean()
    p(f"\n--- {label}（已達前關 N={n}）base 續攻率={base:.0%} ---")
    if n < 50:
        p("  樣本不足"); return
    p(f"  NYF 觸關當下強度分佈 q25/50/75 = "
      f"{df[str_col].quantile([.25,.5,.75]).round(2).tolist()}")
    p(f"  {'NYF強度五分位':>12} {'N':>4} {'範圍':>14} | 續攻率")
    df["q"] = pd.qcut(df[str_col].rank(method="first"), 5,
                      labels=["Q1弱", "Q2", "Q3", "Q4", "Q5強"])
    for q, g in df.groupby("q", observed=True):
        p(f"  {q:>12} {len(g):>4} [{g[str_col].min():+.2f},{g[str_col].max():+.2f}] "
          f"| {g[cont_col].mean():.0%}")
    p(f"  -- 固定門檻續攻率 vs base {base:.0%} --")
    for th in [-0.1, 0.0, 0.1, 0.2, 0.3]:
        g = df[df[str_col] >= th]
        if len(g) >= 30:
            p(f"   NYF≥{th:>4}: N={len(g):>4} 續攻率={g[cont_col].mean():.0%} "
              f"(lift {g[cont_col].mean()/base:.2f}×)")


def first_touch_idx(highs, level):
    w = np.where(highs >= level)[0]
    return int(w[0]) if len(w) else None


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        tx_min, tx_day = load_tx_min(conn)
        for SYM in ["NYF", "CDF"]:
            fx_min, fx_day = load_nyf_min(conn, SYM)
            tx_by = {d: g for d, g in tx_min.groupby("d")}
            fx_by = {d: g.set_index("t") for d, g in fx_min.groupby("d")}
            rows34, rows45 = [], []
            for d, txg in tx_by.items():
                if d not in tx_day.index or d not in fx_day.index:
                    continue
                o, ema = tx_day.loc[d, "o"], tx_day.loc[d, "ema20"]
                fo, fema, pre = (fx_day.loc[d, "o"], fx_day.loc[d, "ema20"],
                                 fx_day.loc[d, "preticks"])
                if not np.isfinite(ema) or not np.isfinite(fema) or fema <= 0:
                    continue
                if not (pre >= PREOPEN_MIN_TICKS):       # NYF 流動性 gate
                    continue
                lv3, lv4, lv5 = o + L3*ema, o + L4*ema, o + L5*ema
                highs = txg["high"].to_numpy()
                times = txg["t"].to_numpy()
                fxg = fx_by.get(d)
                if fxg is None:
                    continue

                def fx_str_at(tt):
                    if tt in fxg.index:
                        c = fxg.loc[tt, "close"]
                        c = c.iloc[-1] if hasattr(c, "iloc") else c
                        return np.tanh((float(c) - fo) / fema)
                    return np.nan

                i3 = first_touch_idx(highs, lv3)
                if i3 is not None:
                    cont = 1.0 if (highs[i3+1:] >= lv4).any() else 0.0
                    rows34.append({"str": fx_str_at(times[i3]), "cont": cont})
                i4 = first_touch_idx(highs, lv4)
                if i4 is not None:
                    cont = 1.0 if (highs[i4+1:] >= lv5).any() else 0.0
                    rows45.append({"str": fx_str_at(times[i4]), "cont": cont})

            p(f"\n############ 訊號標的 = {SYM} ############")
            report(p, f"{SYM}：L3→L4 接續", rows34, "str", "cont")
            report(p, f"{SYM}：L4→L5 接續", rows45, "str", "cont")

    with open("research/active/H118-nyf-preopen-reach/results/continuation_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/continuation_raw.txt")


if __name__ == "__main__":
    main()

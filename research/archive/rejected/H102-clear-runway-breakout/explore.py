"""H102 淨空開盤裸突破 — Phase 1 分佈探索。

問題：當開盤離昨/前日成本(VWAP)夠遠、某方向無近端成本 S/R 擋路時，
該方向 reach ladder 達標分佈是否顯著優於 baseline？(單邊、方向性)

定義對齊：
- VWAP 成本：日盤 08:45–13:45 量加權 sum(close*vol)/sum(vol)，對齊 key_prices.py。
  vwap_last = 前一交易日 VWAP；vwap_prev = 前兩交易日 VWAP。
- reach ladder：L_i = c_i × causal-EMA20(日盤振幅)，對齊 H095/daystats。
  c = 0.385/0.497/0.711/0.977/1.225 → 名目達到率 90/75/50/25/12.5%。
  方向性擺動 up_max=max(high−running_low)、dn_max=max(running_high−low)。
- open：日盤 08:45 第一根 open。OR=08:45–08:57(對齊 orb_est_hl_exit)。

淨空(單邊)：
  above = open 之上的 cost；below = open 之下的 cost
  up_clear = min(above)−open（上方無 cost→+inf）；dn_clear = open−max(below)
  up_clear_norm = up_clear/ema20；dn_clear_norm = dn_clear/ema20
  上方淨空 = up_clear_norm > 門檻 → 上行；下方淨空 = dn_clear_norm > 門檻 → 下行
  門檻 L4=0.977 / L5=1.225 兩階都跨，當分層變量。
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
LVL = [("L1", 0.385, "90%"), ("L2", 0.497, "75%"), ("L3", 0.711, "50%"),
       ("L4", 0.977, "25%"), ("L5", 1.225, "12.5%")]
L4C, L5C = 0.977, 1.225
OR_END = pd.Timestamp("1900-01-01 08:57:00").time()
ENTRY_END = pd.Timestamp("1900-01-01 09:15:00").time()
EXIT_T = pd.Timestamp("1900-01-01 13:30:00").time()


def load_daily() -> pd.DataFrame:
    """每日聚合：open / OR / up_max / dn_max / rng / vwap / OR 破方向與反咬。"""
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            """
            SELECT CAST(timestamp AS DATE) d, timestamp ts,
                   open, high, low, close, volume
            FROM ohlcv_1m WHERE symbol='TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY ts
            """
        ).df()
    for col in ("open", "high", "low", "close"):
        bars[col] = bars[col].astype(float)
    bars["t"] = pd.to_datetime(bars["ts"]).dt.time

    recs = []
    for d, g in bars.groupby("d"):
        g = g.reset_index(drop=True)
        hi, lo = g["high"].to_numpy(), g["low"].to_numpy()
        run_lo = np.minimum.accumulate(lo)
        run_hi = np.maximum.accumulate(hi)
        up_max = float(np.max(hi - run_lo))
        dn_max = float(np.max(run_hi - lo))
        vwap = float((g["close"] * g["volume"]).sum() / g["volume"].sum())
        day_open = float(g["open"].iloc[0])

        # OR (08:45–08:57)
        orm = g["t"] <= OR_END
        or_high = float(g.loc[orm, "high"].max())
        or_low = float(g.loc[orm, "low"].min())

        # OR 破方向（進場窗 08:58–09:15 首次 close 突破）+ 反咬（進場後是否回觸反向 OR）
        win = g[(g["t"] > OR_END) & (g["t"] <= ENTRY_END)]
        brk_side, brk_i = None, None
        for i, row in win.iterrows():
            if row["close"] > or_high:
                brk_side, brk_i = "up", i
                break
            if row["close"] < or_low:
                brk_side, brk_i = "dn", i
                break
        whip = np.nan
        if brk_side is not None:
            post = g[(g.index >= brk_i) & (g["t"] <= EXIT_T)]
            if brk_side == "up":
                whip = float(post["low"].min() < or_low)   # 破上後回破 OR_low
            else:
                whip = float(post["high"].max() > or_high)

        recs.append(dict(d=pd.Timestamp(d), open=day_open, or_high=or_high,
                         or_low=or_low, rng=float(hi.max() - lo.min()),
                         up_max=up_max, dn_max=dn_max, vwap=vwap,
                         brk_side=brk_side, whip=whip))

    df = pd.DataFrame(recs).set_index("d").sort_index()
    df["ema20"] = df["rng"].shift(1).ewm(span=20, adjust=False).mean()
    df["vwap_last"] = df["vwap"].shift(1)
    df["vwap_prev"] = df["vwap"].shift(2)
    return df.dropna(subset=["ema20", "vwap_last", "vwap_prev"])


def add_clearance(df: pd.DataFrame) -> pd.DataFrame:
    o = df["open"].to_numpy()
    c1, c2 = df["vwap_last"].to_numpy(), df["vwap_prev"].to_numpy()
    costs = np.stack([c1, c2], axis=1)
    up_clear, dn_clear, n_above, n_below = [], [], [], []
    for i in range(len(o)):
        ab = costs[i][costs[i] > o[i]]
        be = costs[i][costs[i] < o[i]]
        up_clear.append(ab.min() - o[i] if ab.size else np.inf)
        dn_clear.append(o[i] - be.max() if be.size else np.inf)
        n_above.append(ab.size)
        n_below.append(be.size)
    df = df.copy()
    df["up_clear"] = up_clear
    df["dn_clear"] = dn_clear
    df["n_above"] = n_above
    df["n_below"] = n_below
    df["up_clear_norm"] = df["up_clear"] / df["ema20"]
    df["dn_clear_norm"] = df["dn_clear"] / df["ema20"]
    # reach 達標旗標
    for lab, coef, _ in LVL:
        df[f"up_{lab}"] = (df["up_max"] >= coef * df["ema20"]).astype(float)
        df[f"dn_{lab}"] = (df["dn_max"] >= coef * df["ema20"]).astype(float)
    return df


def layer(norm: pd.Series) -> pd.Series:
    return pd.cut(norm, [0, L4C, L5C, np.inf], right=False,
                 labels=["<L4", "L4–L5", ">L5"])


def reach_by_layer(df: pd.DataFrame, side: str):
    pre = "up" if side == "up" else "dn"
    norm = df[f"{pre}_clear_norm"]
    lay = layer(norm)
    base = {lab: df[f"{pre}_{lab}"].mean() for lab, _, _ in LVL}
    title = "上方淨空 → 上行 reach" if side == "up" else "下方淨空 → 下行 reach"
    print(f"\n=== {title}  (全樣本 baseline N={len(df)}: "
          + " ".join(f"{lab} {base[lab]:.0%}" for lab, _, _ in LVL) + ") ===")
    print(f"  {'clear 分層':<10}{'N':>4} {'%日':>5}  " +
          "  ".join(f"{lab}({nm})" for lab, _, nm in LVL))
    for lv in ["<L4", "L4–L5", ">L5"]:
        sub = df[lay == lv]
        if len(sub) == 0:
            print(f"  {lv:<10}{0:>4}    —")
            continue
        cells = []
        for L, _, _ in LVL:
            p = sub[f"{pre}_{L}"].mean()
            cells.append(f"{p:4.0%}({p - base[L]:+.0%})")
        print(f"  {lv:<10}{len(sub):>4} {len(sub)/len(df):4.0%}  " + "  ".join(cells))
    # 完全淨空(該側無 cost) 細看
    inf_mask = ~np.isfinite(norm)
    sub = df[inf_mask]
    if len(sub):
        cells = [f"{sub[f'{pre}_{L}'].mean():4.0%}({sub[f'{pre}_{L}'].mean()-base[L]:+.0%})"
                 for L, _, _ in LVL]
        print(f"  {'∞(全淨空)':<10}{len(sub):>4} {len(sub)/len(df):4.0%}  " + "  ".join(cells))


def three_state(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("  開盤三態 × reach 達標 (between=夾兩成本間 / gap=跳空在兩成本之外)")
    print("=" * 70)
    between = (df["n_above"] >= 1) & (df["n_below"] >= 1)
    gap_above = df["n_above"] == 0          # open 在兩成本之上 → 上方全淨空
    gap_below = df["n_below"] == 0          # open 在兩成本之下 → 下方全淨空
    for name, m, pre in [("夾兩成本間(洗盤?)", between, None),
                         ("跳空上方(上全淨空)", gap_above, "up"),
                         ("跳空下方(下全淨空)", gap_below, "dn")]:
        sub = df[m]
        n = len(sub)
        if pre is None:
            up3 = sub["up_L3"].mean()
            dn3 = sub["dn_L3"].mean()
            print(f"  {name:<18} N={n:4d} ({n/len(df):3.0%})  "
                  f"up_L3={up3:.0%} dn_L3={dn3:.0%}  → 兩側")
        else:
            cells = " ".join(f"{L} {sub[f'{pre}_{L}'].mean():.0%}" for L, _, _ in LVL)
            print(f"  {name:<18} N={n:4d} ({n/len(df):3.0%})  {pre}方向: {cells}")


def whipsaw(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("  OR 裸突破 反咬率 (whip=破出後回觸反向 OR；只看與淨空同向的突破)")
    print("=" * 70)
    for side, pre in [("up", "up"), ("dn", "dn")]:
        norm = df[f"{pre}_clear_norm"]
        brk = df[df["brk_side"] == side]
        b_all = brk["whip"].mean()
        clear = brk[norm.loc[brk.index] > L4C]
        nclear = brk[norm.loc[brk.index] <= L4C]
        slab = "上破" if side == "up" else "下破"
        print(f"  {slab}: 全部 N={len(brk):3d} whip={b_all:.0%} | "
              f"同向淨空(>L4) N={len(clear):3d} whip={clear['whip'].mean():.0%} | "
              f"非淨空(≤L4) N={len(nclear):3d} whip={nclear['whip'].mean():.0%}")


def main():
    df = add_clearance(load_daily())
    print("=" * 70)
    print(f"  H102 樣本: N={len(df)}  {df.index.min().date()} ~ {df.index.max().date()}")
    print("=" * 70)
    print(f"  up_clear_norm: median={df['up_clear_norm'].replace(np.inf,np.nan).median():.2f} "
          f"∞日={int((~np.isfinite(df['up_clear_norm'])).sum())}")
    print(f"  dn_clear_norm: median={df['dn_clear_norm'].replace(np.inf,np.nan).median():.2f} "
          f"∞日={int((~np.isfinite(df['dn_clear_norm'])).sum())}")

    reach_by_layer(df, "up")
    reach_by_layer(df, "dn")
    three_state(df)
    whipsaw(df)

    # 旁路：淨空 vs 夜盤波動相關性（用日盤 rng 當當日波動 proxy 先看，NVF 另補）
    df.to_csv(Path(__file__).resolve().parent / "results" / "h102_daily.csv")
    print("\n[saved] results/h102_daily.csv")


if __name__ == "__main__":
    main()

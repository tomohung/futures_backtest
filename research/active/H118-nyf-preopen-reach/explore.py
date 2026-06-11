"""H118 Phase 1：三方盤前延伸 vs TX forward ladder reach 分佈探索。

A=NYF(0050期) / B=CDF(台積電) / C=cash ext_long(W10)。
方法：H111/H114 reach-map。各標的 open-anchor 延伸 tanh((F(t)-F(08:45open))/EMA20_self)，
對打 TX forward 上行 reach（t 之後 session high 相對 open ÷ EMA20_TX）。

硬要求：
- forward-tautology guard：forward reach 嚴格取「t 之後」+ IID 洗牌虛無對照
- 盤前流動性 gate：盤前 08:45–08:59 tick 數不足的標的日剔除
- 每個數字附 N

輸出：results/distribution_raw.txt（給 distribution.md 引用）
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import duckdb

DB = "data/futures.duckdb"
TIMES = ["08:45", "08:50", "08:55", "09:00", "09:05", "09:10",
         "09:15", "09:20", "09:25", "09:30"]
LADDERS = {"L3": 0.711, "L4": 0.977, "L5": 1.30}
PREOPEN_MIN_TICKS = 20          # 盤前流動性 gate（08:45–08:59 tick 數門檻）
ANCHOR = "08:45:00"


# ---------- TX：daily open / causal EMA20 範圍 / 各 T 之後的 forward high ----------
def tx_features(conn) -> pd.DataFrame:
    px = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low
        FROM ohlcv_1m WHERE symbol='TX'
          AND CAST(timestamp AS TIME) BETWEEN TIME '08:45' AND TIME '13:45'
    """).df()
    px["t"] = px["t"].astype(str)
    # 每日 open(08:45)、日振幅
    day = px.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    opn = px[px["t"] == ANCHOR][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(opn, on="d", how="inner")
    day["rng"] = day["hi"] - day["lo"]
    day = day.sort_values("d").reset_index(drop=True)
    day["ema20"] = day["rng"].shift(1).ewm(span=20, adjust=False).mean()

    # 各 T：t 之後（嚴格 > T）的 session high → forward reach
    px = px.sort_values(["d", "t"])
    fwd = {}
    for T in TIMES:
        after = px[px["t"] > T].groupby("d")["high"].max()   # 嚴格 t 之後
        fwd[T] = after
    fwd_df = pd.DataFrame(fwd)   # index=d, cols=T → forward high after T
    out = day.set_index("d")[["o", "ema20"]].join(fwd_df)
    # forward reach @T = (fwd_high_after_T - open)/ema20
    for T in TIMES:
        out[f"reach_{T}"] = (out[T] - out["o"]) / out["ema20"]
    return out[["o", "ema20"] + [f"reach_{T}" for T in TIMES]].dropna(subset=["ema20"])


# ---------- 個股期/ETF期：各 T open-anchor 延伸 + 盤前流動性 ----------
def aux_ext(conn, symbol: str) -> pd.DataFrame:
    px = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low,
               close, tick_count
        FROM aux_futures_1m WHERE symbol=?
    """, [symbol]).df()
    if px.empty:
        return pd.DataFrame()
    px["t"] = px["t"].astype(str)
    day = px.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    opn = px[px["t"] == ANCHOR][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(opn, on="d", how="inner").sort_values("d").reset_index(drop=True)
    day["rng"] = day["hi"] - day["lo"]
    day["ema20"] = day["rng"].shift(1).ewm(span=20, adjust=False).mean()
    # 盤前 08:45–08:59 tick 數
    pre = px[(px["t"] >= "08:45:00") & (px["t"] <= "08:59:00")]
    preticks = pre.groupby("d")["tick_count"].sum().rename("preticks")
    # 各 T 的 close
    cl = px[px["t"].isin([f"{T}:00" for T in TIMES])].pivot_table(
        index="d", columns="t", values="close", aggfunc="last")
    base = day.set_index("d")[["o", "ema20"]].join(preticks)
    ext = {}
    for T in TIMES:
        col = f"{T}:00"
        if col in cl.columns:
            ext[f"ext_{T}"] = np.tanh((cl[col] - base["o"]) / base["ema20"])
    extdf = pd.DataFrame(ext)
    return base.join(extdf).dropna(subset=["ema20"])


# ---------- cash ext_long(W10)：用服務逐日（僅 stock_min 覆蓋日）----------
def cash_ext(conn, days) -> pd.DataFrame:
    from src.chart_ui.services.extension import compute_extension_series
    import datetime as dt
    rows = []
    tset = {f"{T}:00" for T in TIMES}
    for d in days:
        res = compute_extension_series(conn, d)
        if not res:
            continue
        m = {}
        for b in res["bars"]:
            hh = dt.datetime.utcfromtimestamp(b["time"]).strftime("%H:%M:%S")
            if hh in tset:
                m[f"ext_{hh[:5]}"] = b["ext_long"]
        m["d"] = d
        rows.append(m)
    return pd.DataFrame(rows).set_index("d") if rows else pd.DataFrame()


def corr_lift(ext_series: pd.Series, reach: pd.Series, thr: float):
    """corr(ext, reach>=thr) 與 高分位(top20%) lift。回傳 (N, corr, base_rate, top_rate)。"""
    df = pd.concat([ext_series, reach], axis=1, keys=["e", "r"]).dropna()
    n = len(df)
    if n < 20:
        return n, np.nan, np.nan, np.nan
    hit = (df["r"] >= thr).astype(float)
    corr = df["e"].corr(hit)
    base = hit.mean()
    q80 = df["e"].quantile(0.80)
    top = hit[df["e"] >= q80].mean()
    return n, corr, base, top


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        p("=== H118 Phase 1：三方盤前延伸 vs TX forward reach ===")
        tx = tx_features(conn)
        p(f"TX reach panel: N={len(tx)} 日（{tx.index.min()} ~ {tx.index.max()}）")

        panels = {"A_NYF": aux_ext(conn, "NYF"), "B_CDF": aux_ext(conn, "CDF")}
        for k, v in panels.items():
            if v.empty:
                p(f"{k}: 無資料"); continue
            liq = (v["preticks"] >= PREOPEN_MIN_TICKS).sum()
            p(f"{k}: N={len(v)} 日（{v.index.min()}~{v.index.max()}）盤前達流動性門檻 {liq} 日")

        # cash 僅 overlap 日（與 NYF 取交集，省時）
        nyf_days = list(panels["A_NYF"].index) if not panels["A_NYF"].empty else []
        cash = cash_ext(conn, sorted(set(nyf_days) & set(tx.index)))
        p(f"C_cash(W10): N={len(cash)} 日（stock_min 覆蓋 & NYF 重疊）")

        # ---- corr-by-time（L4），三方 + 盤前流動性 gate ----
        for lad, thr in LADDERS.items():
            p(f"\n=== corr(ext@T, forward {lad} reach) ＋ top20% lift ===")
            p(f"{'T':>6} | {'A_NYF corr/N':>16} | {'B_CDF corr/N':>16} | {'C_cash corr/N':>16}")
            for T in TIMES:
                cells = []
                for key, panel in [("A_NYF", panels["A_NYF"]), ("B_CDF", panels["B_CDF"]),
                                   ("C_cash", cash)]:
                    col = f"ext_{T}"
                    if panel.empty or col not in panel.columns:
                        cells.append(f"{'—':>16}"); continue
                    e = panel[col]
                    if "preticks" in panel.columns:   # 流動性 gate
                        e = e[panel["preticks"] >= PREOPEN_MIN_TICKS]
                    n, c, base, top = corr_lift(e, tx[f"reach_{T}"], thr)
                    cells.append(f"{c:+.3f}/{n:>4}" if not np.isnan(c) else f"{'NA':>16}")
                p(f"{T:>6} | {cells[0]:>16} | {cells[1]:>16} | {cells[2]:>16}")

        # ---- forward-tautology guard：IID 洗牌虛無（打亂 ext 與 reach 的配對）----
        p("\n=== forward guard：B_CDF @09:00 L4，真實 vs 洗牌虛無 ===")
        b = panels["B_CDF"]
        bb = b[b["preticks"] >= PREOPEN_MIN_TICKS]
        n, c, base, top = corr_lift(bb["ext_09:00"], tx["reach_09:00"], 0.977)
        p(f"  真實: N={n} corr={c:+.3f} base_L4={base:.2%} top20%_L4={top:.2%}")
        # 洗牌：打散 ext 對 reach
        merged = pd.concat([bb["ext_09:00"], tx["reach_09:00"]], axis=1,
                           keys=["e", "r"]).dropna()
        shuf_corrs = []
        for seed in range(200):
            rng = np.random.default_rng(seed)
            permuted = rng.permutation(merged["e"].values)
            hit = (merged["r"].values >= 0.977).astype(float)
            shuf_corrs.append(np.corrcoef(permuted, hit)[0, 1])
        sc = np.array(shuf_corrs)
        p(f"  洗牌虛無 corr: mean={sc.mean():+.3f} sd={sc.std():.3f} "
          f"95%區間=[{np.percentile(sc,2.5):+.3f},{np.percentile(sc,97.5):+.3f}]")
        p(f"  → 真實 corr {c:+.3f} {'落在虛無外(有訊號)' if abs(c)>np.percentile(np.abs(sc),95) else '落在虛無內(疑似 tautology/無訊號)'}")

        # ---- B_CDF 長歷史跨 regime（按年分段，@09:00 L4 corr）----
        p("\n=== B_CDF 跨年 @09:00 forward L4 corr（多 regime 穩定度）===")
        bb2 = bb.copy(); bb2["yr"] = pd.to_datetime(bb2.index).year
        for yr, g in bb2.groupby("yr"):
            n, c, base, top = corr_lift(g["ext_09:00"], tx["reach_09:00"].reindex(g.index), 0.977)
            p(f"  {yr}: N={n:>4} corr={c:+.3f} base_L4={base:.2%} top20%_L4={top:.2%}"
              if not np.isnan(c) else f"  {yr}: N={n} 不足")

    with open("research/active/H118-nyf-preopen-reach/results/distribution_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/distribution_raw.txt")


if __name__ == "__main__":
    main()

"""H135 條件化探索：VWAP 續攻是否只在「離 VWAP 遠 × VWAP 上彎」的 cell 成立？

回應困惑：binary sign(close−VWAP) 池化歸零，但直覺「站上成本形成趨勢」可能對，
只是 edge 藏在強度/斜率條件裡。這裡把樣本依：
  (a) |離 VWAP 距離|（用當日 open 正規化的 %）tertile
  (b) VWAP 斜率方向（sig 前 15 分鐘 VWAP 變化）是否與 close-VWAP 同向
分層，看續攻分離度是否在「遠 + 斜率同向」的 cell 才出現。

續攻定義：sign(fwd) == sign(dev)，fwd=price(T+H)−price(T)，dev=close(T)−VWAP(T)。
頭條：分離度 = up_rate|dev>0 − up_rate|dev<0（在該 cell 內），+ IID 洗牌 null。
regime 守門沿用 H134/H135：逐年檢視贏家 cell。
"""
import sys
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
SYMBOL = "TX"
HORIZON = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CHECK_TIMES = ["09:00", "09:15", "09:30", "09:45"]
SLOPE_LOOKBACK = 15  # 分鐘


def _t(clock, off):
    return (pd.Timestamp("2000-01-01 " + clock)
            + pd.Timedelta(minutes=off)).strftime("%H:%M")


def load():
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            """
            SELECT timestamp::DATE AS d, timestamp::TIME AS tm,
                   high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol=? AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
            """, [SYMBOL]).fetchdf()
    df["t"] = df["tm"].astype(str).str.slice(0, 5)
    for c2 in ("high", "low", "close", "volume"):
        df[c2] = df[c2].astype(float)
    df["typ"] = (df["high"] + df["low"] + df["close"]) / 3
    g = df.groupby("d", sort=False)
    df["vwap"] = (df["typ"] * df["volume"]).groupby(df["d"]).cumsum() / g["volume"].cumsum()
    return df


def build(df):
    # pivot: 每日每時間的 close / vwap 查表
    cl = df.pivot_table(index="d", columns="t", values="close", aggfunc="last")
    vw = df.pivot_table(index="d", columns="t", values="vwap", aggfunc="last")
    day_open = df[df["t"] == "08:45"].set_index("d")["close"]
    dv = df.groupby("d")["close"].std().rename("dayvol")
    prevvol = dv.sort_index().shift(1)

    rows = []
    for check in CHECK_TIMES:
        sig_t = _t(check, -1)
        out_t = _t(check, HORIZON - 1)
        slp_t = _t(check, -1 - SLOPE_LOOKBACK)
        for cols in (cl, vw):
            for tt in (sig_t, out_t, slp_t):
                if tt not in cols.columns:
                    cols[tt] = np.nan
        m = pd.DataFrame({
            "d": cl.index,
            "px_sig": cl[sig_t].values,
            "px_out": cl[out_t].values,
            "vwap_sig": vw[sig_t].values,
            "vwap_slp": vw[slp_t].values,
        }).dropna(subset=["px_sig", "px_out", "vwap_sig"])
        m["check"] = check
        m["opn"] = m["d"].map(day_open)
        m["prevvol"] = m["d"].map(prevvol)
        m["dev"] = m["px_sig"] - m["vwap_sig"]
        m["dev_pct"] = m["dev"].abs() / m["opn"] * 100
        m["slope"] = m["vwap_sig"] - m["vwap_slp"]      # >0 上彎
        m["aligned"] = np.sign(m["dev"]) == np.sign(m["slope"])
        m["fwd"] = m["px_out"] - m["px_sig"]
        m["year"] = pd.to_datetime(m["d"]).dt.year
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


def sep_stats(s):
    s = s[(np.sign(s["dev"]) != 0) & (s["fwd"] != 0)].copy()
    n = len(s)
    if n < 30:
        return None
    up = (s["fwd"] > 0).to_numpy()
    long_m = (s["dev"] > 0).to_numpy()
    short_m = (s["dev"] < 0).to_numpy()
    if not long_m.any() or not short_m.any():
        return None
    sep = up[long_m].mean() - up[short_m].mean()
    hit = (np.sign(s["fwd"]).to_numpy() == np.sign(s["dev"]).to_numpy()).mean()
    sret = np.sign(s["dev"]).to_numpy() * s["fwd"].to_numpy()
    rng = np.random.default_rng(42)
    lm = long_m
    null = []
    for _ in range(2000):
        perm = rng.permutation(lm)
        null.append(up[perm].mean() - up[~perm].mean())
    null = np.array(null)
    p = (np.abs(null) >= abs(sep)).mean()
    return dict(n=n, long_share=long_m.mean(), sep=sep, hit=hit,
                ev=sret.mean(), p=p)


def prow(k, r):
    if r:
        print(f"{k:>14} | {r['n']:>6} | {r['long_share']*100:>4.0f}% | "
              f"{r['sep']*100:>+5.1f}pp| {r['hit']*100:>4.1f}% | {r['ev']:>+6.1f} | {r['p']:>6.3f}")


def hdr():
    print(f"{'cell':>14} | {'N':>6} | {'多占':>4} | {'分離':>6} | {'命中':>5} | {'EVpts':>6} | {'p洗牌':>6}")
    print("-" * 66)


def main():
    df = load()
    samp = build(df)
    print(f"[HORIZON] {HORIZON}min  slope lookback {SLOPE_LOOKBACK}min  N={len(samp):,}\n")

    print("### A. |離 VWAP 距離| tertile（四時點合併）")
    hdr()
    s = samp.dropna(subset=["dev_pct"]).copy()
    s["devtile"] = pd.qcut(s["dev_pct"], 3, labels=["near", "mid", "far"])
    for v in ["near", "mid", "far"]:
        prow(f"dist={v}", sep_stats(s[s["devtile"] == v]))

    print("\n### B. VWAP 斜率是否與位置同向（四時點合併）")
    hdr()
    for al, lab in [(True, "aligned"), (False, "against")]:
        prow(f"slope={lab}", sep_stats(samp[samp["aligned"] == al]))

    print("\n### C. 交互：距離 × 斜率同向（核心假設 cell = far+aligned）")
    hdr()
    for v in ["near", "mid", "far"]:
        for al, lab in [(True, "aln"), (False, "agn")]:
            cell = s[(s["devtile"] == v) & (s["aligned"] == al)]
            prow(f"{v}+{lab}", sep_stats(cell))

    print("\n### D. 核心 cell（far + aligned）逐年穩健度")
    hdr()
    core = s[(s["devtile"] == "far") & (s["aligned"])]
    for yr in sorted(core["year"].unique()):
        prow(str(yr), sep_stats(core[core["year"] == yr]))

    print("\n### E. 核心 cell（far + aligned）逐時點")
    hdr()
    for check in CHECK_TIMES:
        prow(check, sep_stats(core[core["check"] == check]))


if __name__ == "__main__":
    main()

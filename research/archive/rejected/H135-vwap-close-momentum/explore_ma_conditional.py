"""對照探索：H134 的 5分K 120MA 是否也有「遠離 + 斜率同向 → 續攻」結構？

與 explore_conditional.py（VWAP 版）平行，訊號改回 close vs 5分K 120MA：
- dev = close(T) − ma120(T)；dev_pct = |dev|/open×100
- slope = ma120(T) − ma120(T−15min)（>0 上彎）；aligned = sign(dev)==sign(slope)
- 續攻分離度 = up|dev>0 − up|dev<0，+ IID 洗牌 null；逐年守門。

5分K 定義照 H134：對齊 08:45、日盤 08:45–13:45、跨日連續 rolling 120MA。
"""
import sys
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
SYMBOL = "TX"
HORIZON = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CHECK_TIMES = ["09:00", "09:15", "09:30", "09:45"]
SLOPE_LB = 15  # 分鐘（=3 根 5 分 bar）


def _b(clock, off):
    """檢查時點 clock + off 分鐘 對應的 5 分 bucket start（= 時點-5）。"""
    base = pd.Timestamp("2000-01-01 " + clock) + pd.Timedelta(minutes=off)
    return (base - pd.Timedelta(minutes=5)).strftime("%H:%M")


def load_5m():
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            """
            SELECT timestamp::DATE AS d,
                   time_bucket(INTERVAL '5 minutes', timestamp,
                               TIMESTAMP '2000-01-01 08:45:00') AS ts5,
                   arg_max(close, timestamp) AS close
            FROM ohlcv_1m
            WHERE symbol=? AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY d, ts5 ORDER BY ts5
            """, [SYMBOL]).fetchdf()
    df["t"] = pd.to_datetime(df["ts5"]).dt.strftime("%H:%M")
    df["close"] = df["close"].astype(float)
    df = df.sort_values("ts5").reset_index(drop=True)
    df["ma120"] = df["close"].rolling(120, min_periods=120).mean()
    return df


def build(df):
    cl = df.pivot_table(index="d", columns="t", values="close", aggfunc="last", dropna=False)
    ma = df.pivot_table(index="d", columns="t", values="ma120", aggfunc="last", dropna=False)
    ma = ma.reindex(cl.index)
    day_open = df[df["t"] == "08:45"].set_index("d")["close"]
    rows = []
    for check in CHECK_TIMES:
        sig_t, out_t, slp_t = _b(check, 0), _b(check, HORIZON), _b(check, -SLOPE_LB)
        for cols in (cl, ma):
            for tt in (sig_t, out_t, slp_t):
                if tt not in cols.columns:
                    cols[tt] = np.nan
        m = pd.DataFrame({
            "d": cl.index, "px_sig": cl[sig_t].values, "px_out": cl[out_t].values,
            "ma_sig": ma[sig_t].values, "ma_slp": ma[slp_t].values,
        }).dropna(subset=["px_sig", "px_out", "ma_sig", "ma_slp"])
        m["check"] = check
        m["opn"] = m["d"].map(day_open)
        m["dev"] = m["px_sig"] - m["ma_sig"]
        m["dev_pct"] = m["dev"].abs() / m["opn"] * 100
        m["slope"] = m["ma_sig"] - m["ma_slp"]
        m["aligned"] = np.sign(m["dev"]) == np.sign(m["slope"])
        m["fwd"] = m["px_out"] - m["px_sig"]
        m["year"] = pd.to_datetime(m["d"]).dt.year
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


def sep_stats(s):
    s = s[(np.sign(s["dev"]) != 0) & (s["fwd"] != 0)]
    n = len(s)
    if n < 30:
        return None
    up = (s["fwd"] > 0).to_numpy()
    long_m = (s["dev"] > 0).to_numpy()
    if not long_m.any() or not (~long_m).any():
        return None
    sep = up[long_m].mean() - up[~long_m].mean()
    hit = (np.sign(s["fwd"]).to_numpy() == np.sign(s["dev"]).to_numpy()).mean()
    ev = (np.sign(s["dev"]).to_numpy() * s["fwd"].to_numpy()).mean()
    rng = np.random.default_rng(42)
    null = np.array([up[p].mean() - up[~p].mean()
                     for p in (rng.permutation(long_m) for _ in range(2000))])
    p = (np.abs(null) >= abs(sep)).mean()
    return dict(n=n, long_share=long_m.mean(), sep=sep, hit=hit, ev=ev, p=p)


def prow(k, r):
    if r:
        print(f"{k:>14} | {r['n']:>6} | {r['long_share']*100:>4.0f}% | "
              f"{r['sep']*100:>+5.1f}pp| {r['hit']*100:>4.1f}% | {r['ev']:>+6.1f} | {r['p']:>6.3f}")


def hdr():
    print(f"{'cell':>14} | {'N':>6} | {'多占':>4} | {'分離':>6} | {'命中':>5} | {'EVpts':>6} | {'p洗牌':>6}")
    print("-" * 66)


def main():
    df = load_5m()
    samp = build(df)
    print(f"[MA 版對照] HORIZON {HORIZON}min  N={len(samp):,}\n")

    print("### A. |離 120MA 距離| tertile")
    hdr()
    s = samp.dropna(subset=["dev_pct"]).copy()
    s["devtile"] = pd.qcut(s["dev_pct"], 3, labels=["near", "mid", "far"])
    for v in ["near", "mid", "far"]:
        prow(f"dist={v}", sep_stats(s[s["devtile"] == v]))

    print("\n### C. 距離 × 斜率同向")
    hdr()
    for v in ["near", "mid", "far"]:
        for al, lab in [(True, "aln"), (False, "agn")]:
            prow(f"{v}+{lab}", sep_stats(s[(s["devtile"] == v) & (s["aligned"] == al)]))

    print("\n### D. 核心 cell（far + aligned）逐年")
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

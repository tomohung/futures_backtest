"""H135 Phase 1 探索：close vs 當日 VWAP 在 9:00/9:15/9:30/9:45 對後續 H 分鐘的預測力。

沿用 H134 方法學，訊號改為 sign(close(T) − 當日累積 VWAP(T))。

定義：
- 資料 ohlcv_1m（TX），日盤 08:45–13:45。
- VWAP = 每日累積 sum(typical×volume)/sum(volume)，typical=(H+L+C)/3，08:45 重置。
- 檢查時點 T ∈ {9:00,9:15,9:30,9:45}：signal 取 T−1min 那根 1 分 bar（close、VWAP），
  outcome 取 T+H−1min 那根 bar 的 close。H 由命令列覆寫（預設 30）。
- 頭條 = drift-immune 分離度（多訊號 up-rate − 空訊號 up-rate）+ 2000 次 IID 洗牌 null。
- regime 切分只用「盤前可知（前一日波動）」，禁用當日事後波動（H134 look-ahead 教訓）。
"""
import sys
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
SYMBOL = "TX"

HORIZON = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CHECK_TIMES = ["09:00", "09:15", "09:30", "09:45"]


def _t(clock_str, off):
    return (pd.Timestamp("2000-01-01 " + clock_str)
            + pd.Timedelta(minutes=off)).strftime("%H:%M")


# 檢查時點 -> (signal 1分 bar 時間, outcome 1分 bar 時間)
CHECKS = {c: (_t(c, -1), _t(c, HORIZON - 1)) for c in CHECK_TIMES}


def load_vwap():
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            """
            SELECT timestamp::DATE AS d,
                   timestamp::TIME AS tm,
                   high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).fetchdf()
    df["t"] = df["tm"].astype(str).str.slice(0, 5)
    for col in ("high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["typ"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["pv"] = df["typ"] * df["volume"]
    g = df.groupby("d", sort=False)
    df["vwap"] = g["pv"].cumsum() / g["volume"].cumsum()
    return df


def build_samples(df):
    rows = []
    for check, (sig_t, out_t) in CHECKS.items():
        sig = df[df["t"] == sig_t][["d", "close", "vwap"]].rename(
            columns={"close": "px_sig"})
        out = df[df["t"] == out_t][["d", "close"]].rename(columns={"close": "px_out"})
        m = sig.merge(out, on="d", how="inner").dropna(subset=["vwap"])
        m["check"] = check
        m["fwd"] = m["px_out"] - m["px_sig"]
        m["sig"] = np.sign(m["px_sig"] - m["vwap"]).astype(int)
        m["year"] = pd.to_datetime(m["d"]).dt.year
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


def stats_for(sub):
    s = sub[(sub["sig"] != 0) & (sub["fwd"] != 0)].copy()
    n = len(s)
    if n == 0:
        return None
    up = s["fwd"] > 0
    long_mask = s["sig"] > 0
    short_mask = s["sig"] < 0
    up_long = up[long_mask].mean() if long_mask.any() else np.nan
    up_short = up[short_mask].mean() if short_mask.any() else np.nan
    separation = up_long - up_short
    hit = (np.sign(s["fwd"]).astype(int) == s["sig"]).mean()
    sret = s["sig"] * s["fwd"]
    pct = sret / s["px_sig"] * 100
    rng = np.random.default_rng(42)
    svals = s["sig"].to_numpy()
    upv = up.to_numpy()
    null_sep = []
    for _ in range(2000):
        perm = rng.permutation(svals)
        lm, sm = perm > 0, perm < 0
        if lm.any() and sm.any():
            null_sep.append(upv[lm].mean() - upv[sm].mean())
    null_sep = np.array(null_sep)
    p_val = (np.abs(null_sep) >= abs(separation)).mean()
    return dict(n=n, long_share=long_mask.mean(), base_up=up.mean(),
                up_long=up_long, up_short=up_short, separation=separation,
                hit=hit, ev_pts=sret.mean(), ev_pct=pct.mean(), p_shuffle=p_val)


def fp(x):
    return "n/a" if pd.isna(x) else f"{x*100:.1f}%"


def prow(key, r):
    print(f"{key:>6} | {r['n']:>6} | {fp(r['long_share']):>5} | {fp(r['base_up']):>6} | "
          f"{fp(r['up_long']):>6} | {fp(r['up_short']):>6} | {r['separation']*100:>+5.1f}pp| "
          f"{fp(r['hit']):>5} | {r['ev_pts']:>+6.1f} | {r['ev_pct']:>+5.2f}% | {r['p_shuffle']:>6.3f}")


def hdr():
    print(f"{'key':>6} | {'N':>6} | {'多占':>5} | {'baseUp':>6} | {'up|多':>6} | "
          f"{'up|空':>6} | {'分離':>6} | {'命中':>5} | {'EVpts':>6} | {'EV%':>6} | {'p洗牌':>6}")
    print("-" * 94)


def main():
    df = load_vwap()
    print(f"[HORIZON] 未來 {HORIZON} 分鐘   [CHECKS] {CHECKS}")
    print(f"[1m bars] {len(df):,} rows, {df['d'].nunique()} days, "
          f"{df['d'].min()} ~ {df['d'].max()}")
    samp = build_samples(df)
    print(f"[samples] total {len(samp):,}\n")

    print(f"{'='*80}\n### 逐時點（close vs 當日 VWAP）\n{'='*80}")
    hdr()
    for check in CHECKS:
        r = stats_for(samp[samp["check"] == check])
        if r:
            prow(check, r)

    print(f"\n{'='*80}\n### 逐年（四時點合併）\n{'='*80}")
    hdr()
    for yr in sorted(samp["year"].unique()):
        r = stats_for(samp[samp["year"] == yr])
        if r:
            prow(str(yr), r)

    # 盤前可知波動 tertile（前一日 1分 close 標準差）
    dv = df.groupby("d")["close"].std().rename("dayvol").reset_index().sort_values("d")
    dv["prevvol"] = dv["dayvol"].shift(1)
    s2 = samp.merge(dv, on="d", how="left").dropna(subset=["prevvol"]).copy()
    s2["voltile"] = pd.qcut(s2["prevvol"], 3, labels=["low", "mid", "high"])
    print(f"\n{'='*80}\n### 波動 tertile（盤前可知：前一日波動；四時點合併）\n{'='*80}")
    hdr()
    for v in ["low", "mid", "high"]:
        r = stats_for(s2[s2["voltile"] == v])
        if r:
            prow(v, r)

    print(f"\n{'='*80}\n### 高波桶（盤前可知 top tertile）逐年\n{'='*80}")
    hdr()
    hi = s2[s2["voltile"] == "high"]
    for yr in sorted(hi["year"].unique()):
        r = stats_for(hi[hi["year"] == yr])
        if r:
            prow(str(yr), r)


if __name__ == "__main__":
    main()

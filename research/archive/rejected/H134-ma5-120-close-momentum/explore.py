"""H134 Phase 1 探索：5分K 120MA（均線值/扣抵）vs 收盤價 對後續 30 分鐘的預測力。

定義（照 key_prices 精神，但改 5分K 120MA）：
- 日盤 08:45–13:45，5 分 bar 對齊 08:45（bucket start 標記）。
- 120MA = 該 bar + 前 119 根（跨日連續）的 close 平均；扣抵 = 窗口中最舊那根 close。
- 檢查時點 T ∈ {9:00,9:15,9:30,9:45}：用「已完成」的 5 分 bar，
  其 bucket start = T-5min。price(T)=該 bar close。
- outcome：price(T+30) - price(T)，即 sig bucket=T-5、out bucket=T+25。

訊號：
- ma  法：sign(close(T) - ma120(T))
- ded 法：sign(close(T) - deduct(T))   （close>扣抵 → 均線將上彎 → 多）

守門（見 proposal Notes）：
- 早盤方向漂移 → 頭條指標用「多訊號 up-rate − 空訊號 up-rate」（drift-immune 分離度），
  另附 IID 洗牌 null 分佈與 CI。
- regime confound → 逐年 + 波動 tertile 切分。
"""
import sys
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
SYMBOL = "TX"

# 未來 horizon（分鐘），可由命令列覆寫：python explore.py 15
HORIZON = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CHECK_TIMES = ["09:00", "09:15", "09:30", "09:45"]


def _bucket(clock_str, offset_min):
    """檢查時點 clock 往後 offset 分鐘，對應的 5 分 bucket start（= 時點-5）。"""
    base = pd.Timestamp("2000-01-01 " + clock_str) + pd.Timedelta(minutes=offset_min)
    return (base - pd.Timedelta(minutes=5)).strftime("%H:%M")


# 檢查時點 -> (signal bucket start, outcome bucket start)
CHECKS = {c: (_bucket(c, 0), _bucket(c, HORIZON)) for c in CHECK_TIMES}


def load_5m():
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            """
            SELECT
                timestamp::DATE AS d,
                time_bucket(INTERVAL '5 minutes', timestamp,
                            TIMESTAMP '2000-01-01 08:45:00') AS ts5,
                arg_max(close, timestamp) AS close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY d, ts5
            ORDER BY ts5
            """,
            [SYMBOL],
        ).fetchdf()
    df["t"] = pd.to_datetime(df["ts5"]).dt.strftime("%H:%M")
    df["close"] = df["close"].astype(float)
    # 跨日連續序列上算 rolling 120MA / 扣抵
    df = df.sort_values("ts5").reset_index(drop=True)
    df["ma120"] = df["close"].rolling(120, min_periods=120).mean()
    df["deduct"] = df["close"].shift(119)
    df["nwin"] = df["close"].rolling(120, min_periods=1).count()
    df.loc[df["nwin"] < 120, ["ma120", "deduct"]] = np.nan
    return df


def build_samples(df):
    """每個檢查時點 × 每日，組出 (signal, outcome)。"""
    rows = []
    for check, (sig_t, out_t) in CHECKS.items():
        sig = df[df["t"] == sig_t][["d", "close", "ma120", "deduct"]].rename(
            columns={"close": "px_sig", "ma120": "ma", "deduct": "ded"})
        out = df[df["t"] == out_t][["d", "close"]].rename(columns={"close": "px_out"})
        m = sig.merge(out, on="d", how="inner").dropna(subset=["ma", "ded"])
        m["check"] = check
        m["fwd"] = m["px_out"] - m["px_sig"]          # 未來 30 分點數變動
        m["ma_sig"] = np.sign(m["px_sig"] - m["ma"]).astype(int)
        m["ded_sig"] = np.sign(m["px_sig"] - m["ded"]).astype(int)
        m["year"] = pd.to_datetime(m["d"]).dt.year
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


def stats_for(sub, sig_col):
    """對一個 (check, 訊號法) 子集算方向分離度 / 命中率 / EV。"""
    s = sub[(sub[sig_col] != 0) & (sub["fwd"] != 0)].copy()
    n = len(s)
    if n == 0:
        return None
    up = s["fwd"] > 0
    base_up = up.mean()
    long_mask = s[sig_col] > 0
    short_mask = s[sig_col] < 0
    up_long = up[long_mask].mean() if long_mask.any() else np.nan
    up_short = up[short_mask].mean() if short_mask.any() else np.nan
    separation = up_long - up_short           # drift-immune headline
    hit = (np.sign(s["fwd"]).astype(int) == s[sig_col]).mean()
    # 順訊號報酬
    sret = s[sig_col] * s["fwd"]
    pct = sret / s["px_sig"] * 100
    # IID 洗牌 null（打亂 signal 對 outcome 的配對）分離度分佈
    rng = np.random.default_rng(42)
    svals = s[sig_col].to_numpy()
    upv = up.to_numpy()
    null_sep = []
    for _ in range(2000):
        perm = rng.permutation(svals)
        lm = perm > 0
        sm = perm < 0
        if lm.any() and sm.any():
            null_sep.append(upv[lm].mean() - upv[sm].mean())
    null_sep = np.array(null_sep)
    p_val = (np.abs(null_sep) >= abs(separation)).mean()
    return dict(
        n=n, long_share=long_mask.mean(), base_up=base_up,
        up_long=up_long, up_short=up_short, separation=separation,
        hit=hit, ev_pts=sret.mean(), ev_pct=pct.mean(),
        med_pts=sret.median(), p_shuffle=p_val,
        null_sep_hi=np.quantile(null_sep, 0.975),
    )


def fmt_pct(x):
    return "n/a" if pd.isna(x) else f"{x*100:.1f}%"


def main():
    df = load_5m()
    print(f"[HORIZON] 未來 {HORIZON} 分鐘   [CHECKS] {CHECKS}")
    print(f"[5m bars] {len(df):,} rows, {df['d'].nunique()} days, "
          f"{df['d'].min()} ~ {df['d'].max()}")
    samp = build_samples(df)
    print(f"[samples] total {len(samp):,}\n")

    for sig_col, label in [("ma_sig", "均線值法"), ("ded_sig", "扣抵法")]:
        print(f"\n{'='*78}\n### {label}（close vs {'120MA' if sig_col=='ma_sig' else '扣抵'}）\n{'='*78}")
        print(f"{'check':>6} | {'N':>5} | {'多占':>5} | {'baseUp':>6} | "
              f"{'up|多':>6} | {'up|空':>6} | {'分離':>6} | {'命中':>5} | "
              f"{'EVpts':>6} | {'EV%':>6} | {'p洗牌':>6}")
        print("-" * 92)
        for check in CHECKS:
            r = stats_for(samp[samp["check"] == check], sig_col)
            if r is None:
                continue
            print(f"{check:>6} | {r['n']:>5} | {fmt_pct(r['long_share']):>5} | "
                  f"{fmt_pct(r['base_up']):>6} | {fmt_pct(r['up_long']):>6} | "
                  f"{fmt_pct(r['up_short']):>6} | {r['separation']*100:>+5.1f}pp| "
                  f"{fmt_pct(r['hit']):>5} | {r['ev_pts']:>+6.1f} | "
                  f"{r['ev_pct']:>+5.2f}% | {r['p_shuffle']:>6.3f}")

    # 逐年（合併四時點，扣抵法為主）三關檢查
    print(f"\n{'='*78}\n### 逐年穩健性（扣抵法，四時點合併）\n{'='*78}")
    print(f"{'year':>6} | {'N':>6} | {'分離':>6} | {'命中':>5} | {'EVpts':>7} | {'p洗牌':>6}")
    print("-" * 60)
    for yr in sorted(samp["year"].unique()):
        r = stats_for(samp[samp["year"] == yr], "ded_sig")
        if r:
            print(f"{yr:>6} | {r['n']:>6} | {r['separation']*100:>+5.1f}pp| "
                  f"{fmt_pct(r['hit']):>5} | {r['ev_pts']:>+7.1f} | {r['p_shuffle']:>6.3f}")

    # 波動 tertile — 事後（當日全時段）vs 盤前可知（前一日波動）
    dayvol = df.groupby("d")["close"].std().rename("dayvol").reset_index()
    dayvol = dayvol.sort_values("d").reset_index(drop=True)
    dayvol["prevvol"] = dayvol["dayvol"].shift(1)   # 盤前可知：前一交易日波動
    samp2 = samp.merge(dayvol, on="d", how="left")

    for volcol, tag in [("dayvol", "事後：當日全時段波動"),
                        ("prevvol", "盤前可知：前一日波動")]:
        print(f"\n{'='*78}\n### 波動 tertile（扣抵法，四時點合併；{tag}）\n{'='*78}")
        s2 = samp2.dropna(subset=[volcol]).copy()
        s2["voltile"] = pd.qcut(s2[volcol], 3, labels=["low", "mid", "high"])
        print(f"{'vol':>6} | {'N':>6} | {'分離':>6} | {'命中':>5} | {'EVpts':>7} | {'p洗牌':>6}")
        print("-" * 60)
        for v in ["low", "mid", "high"]:
            r = stats_for(s2[s2["voltile"] == v], "ded_sig")
            if r:
                print(f"{v:>6} | {r['n']:>6} | {r['separation']*100:>+5.1f}pp| "
                      f"{fmt_pct(r['hit']):>5} | {r['ev_pts']:>+7.1f} | {r['p_shuffle']:>6.3f}")

    # 高波桶（盤前可知）逐年穩健度 — 三關的第一關
    print(f"\n{'='*78}\n### 高波桶（前一日波動 top tertile）逐年穩健度（扣抵法）\n{'='*78}")
    s2 = samp2.dropna(subset=["prevvol"]).copy()
    s2["voltile"] = pd.qcut(s2["prevvol"], 3, labels=["low", "mid", "high"])
    hi = s2[s2["voltile"] == "high"]
    print(f"{'year':>6} | {'N':>6} | {'分離':>6} | {'命中':>5} | {'EVpts':>7} | {'p洗牌':>6}")
    print("-" * 60)
    for yr in sorted(hi["year"].unique()):
        r = stats_for(hi[hi["year"] == yr], "ded_sig")
        if r:
            print(f"{yr:>6} | {r['n']:>6} | {r['separation']*100:>+5.1f}pp| "
                  f"{fmt_pct(r['hit']):>5} | {r['ev_pts']:>+7.1f} | {r['p_shuffle']:>6.3f}")

    # 高波桶內逐時點（看是否某時點主導）
    print(f"\n{'='*78}\n### 高波桶（前一日波動 top tertile）逐時點（扣抵法）\n{'='*78}")
    print(f"{'check':>6} | {'N':>6} | {'分離':>6} | {'命中':>5} | {'EVpts':>7} | {'p洗牌':>6}")
    print("-" * 60)
    for check in CHECKS:
        r = stats_for(hi[hi["check"] == check], "ded_sig")
        if r:
            print(f"{check:>6} | {r['n']:>6} | {r['separation']*100:>+5.1f}pp| "
                  f"{fmt_pct(r['hit']):>5} | {r['ev_pts']:>+7.1f} | {r['p_shuffle']:>6.3f}")


if __name__ == "__main__":
    main()

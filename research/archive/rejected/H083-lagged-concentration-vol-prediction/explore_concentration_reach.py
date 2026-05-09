"""快速探索：集中度對 EstRange 觸及率的影響（同時與夜盤 vol 比較）。

EstRange proxy 用 H070 的方法：EMA20 of day_hl, shifted by 1。
reach_1x = day_hl / ema_hl >= 1.0。

問題：
  Q1. 集中度 dev_lag1 高時，是否更常觸及 1× EstRange？
  Q2. 跟夜盤 vol 比，誰預測力強？
  Q3. 兩者互補嗎？(雙重高 vs 雙重低 vs 對沖)
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"

DAY_NIGHT_SQL = """
WITH classified AS (
    SELECT timestamp,
        CASE
            WHEN timestamp::TIME BETWEEN '08:45:00' AND '13:45:00' THEN timestamp::DATE
            WHEN timestamp::TIME >= '15:00:00' THEN (timestamp + INTERVAL 1 DAY)::DATE
            WHEN timestamp::TIME < '05:00:00' THEN timestamp::DATE
        END AS effective_day,
        CASE WHEN timestamp::TIME BETWEEN '08:45:00' AND '13:45:00' THEN 'day' ELSE 'night' END AS session,
        open, high, low, close
    FROM ohlcv_1m WHERE symbol='TX'
      AND (timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
           OR timestamp::TIME >= '15:00:00'
           OR timestamp::TIME < '05:00:00')
), sessions AS (
    SELECT effective_day, session,
           FIRST(open ORDER BY timestamp) AS s_open,
           MAX(high) AS s_high, MIN(low) AS s_low, COUNT(*) AS n_bars
    FROM classified WHERE effective_day IS NOT NULL
    GROUP BY effective_day, session
)
SELECT effective_day AS trade_date,
    MAX(CASE WHEN session='day' THEN s_open END) AS d_open,
    MAX(CASE WHEN session='day' THEN s_high END) AS d_high,
    MAX(CASE WHEN session='day' THEN s_low END) AS d_low,
    MAX(CASE WHEN session='night' THEN s_open END) AS n_open,
    MAX(CASE WHEN session='night' THEN s_high END) AS n_high,
    MAX(CASE WHEN session='night' THEN s_low END) AS n_low,
    MAX(CASE WHEN session='day' THEN n_bars END) AS d_bars,
    MAX(CASE WHEN session='night' THEN n_bars END) AS n_bars
FROM sessions GROUP BY effective_day ORDER BY effective_day
"""


def main() -> None:
    with duckdb.connect(DB, read_only=True) as conn:
        sess = conn.execute(DAY_NIGHT_SQL).fetchdf()
        ci = conn.execute(
            "SELECT trade_date, top20_dev_pct FROM concentration_index"
        ).fetchdf()

    sess["trade_date"] = pd.to_datetime(sess["trade_date"]).dt.date
    ci["trade_date"] = pd.to_datetime(ci["trade_date"]).dt.date
    df = sess.merge(ci, on="trade_date").sort_values("trade_date").reset_index(drop=True)

    # Day H-L (絕對點數，不正規化)
    df["day_hl"] = df["d_high"] - df["d_low"]
    df["night_hl"] = df["n_high"] - df["n_low"]

    # ema_hl = EMA20 of day_hl, shifted by 1（H070 的方法）
    df["ema_hl"] = df["day_hl"].ewm(span=20, adjust=False).mean().shift(1)
    df["hl_ratio"] = df["day_hl"] / df["ema_hl"]

    # night_norm = night_hl / EMA20(night_hl).shift(1)
    df["ema_night"] = df["night_hl"].ewm(span=20, adjust=False).mean().shift(1)
    df["night_norm"] = df["night_hl"] / df["ema_night"]

    # lag-1 集中度
    df["dev_lag1"] = df["top20_dev_pct"].shift(1)

    # 過濾
    df = df.dropna(subset=["hl_ratio", "night_norm", "dev_lag1"])
    df = df[df["n_bars"] >= 200].copy()
    df["weekday"] = pd.to_datetime(df["trade_date"]).dt.weekday

    print(f"樣本: {len(df)} 個交易日")
    print(f"  day_hl mean={df.day_hl.mean():.0f} 點, ema_hl mean={df.ema_hl.mean():.0f} 點")
    print(f"  hl_ratio mean={df.hl_ratio.mean():.3f}, median={df.hl_ratio.median():.3f}")
    print(f"  baseline P(reach >= 1.0) = {(df.hl_ratio >= 1.0).mean()*100:.1f}%")
    print(f"  baseline P(reach >= 0.75) = {(df.hl_ratio >= 0.75).mean()*100:.1f}%")
    print(f"  baseline P(reach >= 1.2) = {(df.hl_ratio >= 1.2).mean()*100:.1f}%")
    print()

    # === Univariate corr ===
    print("=== Univariate corr (vs hl_ratio) ===")
    print(f"  corr(dev_lag1, hl_ratio)   = {df[['dev_lag1','hl_ratio']].corr().iloc[0,1]:+.4f}")
    print(f"  corr(night_norm, hl_ratio) = {df[['night_norm','hl_ratio']].corr().iloc[0,1]:+.4f}")
    print()

    # === 集中度桶 → P(reach) ===
    df["d_q"] = pd.qcut(df["dev_lag1"], 5, labels=["D1", "D2", "D3", "D4", "D5"])
    print("=== 集中度桶 → P(reach 1.0x EstRange) ===")
    g = df.groupby("d_q", observed=True).agg(
        n=("hl_ratio", "count"),
        ratio_mean=("hl_ratio", "mean"),
        p_reach_075=("hl_ratio", lambda s: (s >= 0.75).mean()),
        p_reach_10=("hl_ratio", lambda s: (s >= 1.0).mean()),
        p_reach_12=("hl_ratio", lambda s: (s >= 1.2).mean()),
    )
    g["p_reach_075"] *= 100
    g["p_reach_10"] *= 100
    g["p_reach_12"] *= 100
    print(g.round(3).to_string())
    print()

    # === 夜盤桶 → P(reach) (H070 已知，作為對照) ===
    df["n_q"] = pd.qcut(df["night_norm"], 5, labels=["N1", "N2", "N3", "N4", "N5"])
    print("=== 夜盤桶 → P(reach 1.0x EstRange) ===")
    g = df.groupby("n_q", observed=True).agg(
        n=("hl_ratio", "count"),
        ratio_mean=("hl_ratio", "mean"),
        p_reach_075=("hl_ratio", lambda s: (s >= 0.75).mean()),
        p_reach_10=("hl_ratio", lambda s: (s >= 1.0).mean()),
        p_reach_12=("hl_ratio", lambda s: (s >= 1.2).mean()),
    )
    g["p_reach_075"] *= 100
    g["p_reach_10"] *= 100
    g["p_reach_12"] *= 100
    print(g.round(3).to_string())
    print()

    # === OLS R² 比較 ===
    def ols(y, X):
        X1 = np.column_stack([np.ones(len(X)), X])
        beta = np.linalg.lstsq(X1, y, rcond=None)[0]
        yhat = X1 @ beta
        resid = y - yhat
        n, k = X1.shape
        sigma2 = (resid @ resid) / (n - k)
        cov = sigma2 * np.linalg.inv(X1.T @ X1)
        se = np.sqrt(np.diag(cov))
        t = beta / se
        r2 = 1 - (resid @ resid) / ((y - y.mean()) ** 2).sum()
        return beta, t, r2

    print("=== OLS: hl_ratio ~ ... ===")
    _, t1, r1 = ols(df["hl_ratio"].values, df[["dev_lag1"]].values)
    _, t2, r2 = ols(df["hl_ratio"].values, df[["night_norm"]].values)
    _, t3, r3 = ols(df["hl_ratio"].values, df[["dev_lag1", "night_norm"]].values)
    print(f"  dev_lag1 only:   t={t1[1]:.2f}  R²={r1:.4f}")
    print(f"  night_norm only: t={t2[1]:.2f}  R²={r2:.4f}")
    print(f"  joint:           dev_t={t3[1]:.2f}  night_t={t3[2]:.2f}  R²={r3:.4f}")
    print(f"  dev_lag1 增量 R² = {r3 - r2:.4f}")
    print()

    # === 5x5 P(reach 1x) ===
    print("=== 5x5 P(reach >= 1.0x) % (橫: 夜盤桶, 縱: 集中度桶) ===")
    pivot_reach = df.groupby(["d_q", "n_q"], observed=True).apply(
        lambda g: (g["hl_ratio"] >= 1.0).mean() * 100, include_groups=False
    )
    print(pivot_reach.unstack().round(1).to_string())
    print()
    print("樣本數:")
    n_pivot = df.groupby(["d_q", "n_q"], observed=True).size().unstack(fill_value=0)
    print(n_pivot.to_string())
    print()

    # 對角極端
    print("=== 四個極端格 P(reach >= 1.0x) ===")
    for label, dq, nq in [
        ("雙重高 D5×N5", "D5", "N5"),
        ("雙重低 D1×N1", "D1", "N1"),
        ("集中高夜盤低 D5×N1", "D5", "N1"),
        ("集中低夜盤高 D1×N5", "D1", "N5"),
    ]:
        sub = df[(df["d_q"] == dq) & (df["n_q"] == nq)]
        if len(sub) > 0:
            r = (sub["hl_ratio"] >= 1.0).mean() * 100
            print(f"  {label}: n={len(sub):>3}  P(reach 1x)={r:.1f}%  hl_ratio mean={sub.hl_ratio.mean():.3f}")
    print(f"  baseline: P(reach 1x)={(df.hl_ratio >= 1.0).mean()*100:.1f}%")


if __name__ == "__main__":
    main()

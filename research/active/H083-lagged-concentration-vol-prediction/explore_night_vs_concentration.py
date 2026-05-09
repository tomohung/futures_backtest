"""H083 探索性比較腳本（一次性執行，不入 ETL）。

比較 t-1 集中度 vs t-1 夜盤振幅對 t 日盤振幅的預測力。
結果記錄於 follow_up_note.md。
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"

SQL = """
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
           FIRST(open ORDER BY timestamp) AS s_open, LAST(close ORDER BY timestamp) AS s_close,
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


def ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
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


def main() -> None:
    with duckdb.connect(DB, read_only=True) as conn:
        sess = conn.execute(SQL).fetchdf()
        ci = conn.execute(
            "SELECT trade_date, top20_dev_pct FROM concentration_index"
        ).fetchdf()

    sess["trade_date"] = pd.to_datetime(sess["trade_date"]).dt.date
    ci["trade_date"] = pd.to_datetime(ci["trade_date"]).dt.date
    df = sess.merge(ci, on="trade_date").sort_values("trade_date").reset_index(drop=True)
    df["d_range"] = (df["d_high"] - df["d_low"]) / df["d_open"]
    df["n_range"] = (df["n_high"] - df["n_low"]) / df["n_open"]
    df["dev_lag1"] = df["top20_dev_pct"].shift(1)
    df = df.dropna(subset=["d_range", "n_range", "dev_lag1"])
    df = df[df["n_bars"] >= 200].copy()

    print(f"樣本: {len(df)} 個交易日")

    print("\n=== Univariate corr ===")
    print(f"  corr(dev_lag1, d_range) = {df[['dev_lag1','d_range']].corr().iloc[0,1]:+.4f}")
    print(f"  corr(n_range, d_range)  = {df[['n_range','d_range']].corr().iloc[0,1]:+.4f}")
    print(f"  corr(dev_lag1, n_range) = {df[['dev_lag1','n_range']].corr().iloc[0,1]:+.4f}")

    print("\n=== OLS ===")
    _, t1, r1 = ols(df["d_range"].values, df[["dev_lag1"]].values)
    _, t2, r2 = ols(df["d_range"].values, df[["n_range"]].values)
    _, t3, r3 = ols(df["d_range"].values, df[["dev_lag1", "n_range"]].values)
    print(f"  dev only: t={t1[1]:.2f}  R²={r1:.4f}")
    print(f"  night only: t={t2[1]:.2f}  R²={r2:.4f}")
    print(f"  joint: dev_t={t3[1]:.2f}  night_t={t3[2]:.2f}  R²={r3:.4f}")
    print(f"  dev_lag1 增量 R² = {r3 - r2:.4f}")

    df["n_q"] = pd.qcut(df["n_range"], 5, labels=["N1", "N2", "N3", "N4", "N5"])
    df["d_q"] = pd.qcut(df["dev_lag1"], 5, labels=["D1", "D2", "D3", "D4", "D5"])
    print("\n=== 5x5 d_range mean (%) ===")
    pivot = df.groupby(["d_q", "n_q"], observed=True)["d_range"].mean() * 100
    print(pivot.unstack().round(2).to_string())


if __name__ == "__main__":
    main()

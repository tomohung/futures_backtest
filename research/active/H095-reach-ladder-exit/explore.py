"""H094 — 關卡階梯能否只用 EMA20（單參數）取代現行『夜盤+EMA20』雙參數？

現行 daystats.LVL_QUANTILES：每階距離 rng = a×夜盤振幅 + b×EMA20，無常數分位迴歸
(τ=0.10/0.25/0.50/0.75 ↔ 達到率 90/75/50/25%)。本腳本比較：
  Model A（現行）：rng = a×夜盤 + b×EMA20
  Model B（單參）：rng = c×EMA20
比較指標：pinball loss（越低越好）、達到率覆蓋（實際 ≥ 預測的比例，應 ≈ 目標達到率）。
另做 train(2021-2024)/test(2025-2026) 切分檢驗 OOS 覆蓋。

方法論對齊 daystats / H093：TX 日盤擺動，pooled 多空對稱。
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# 專案根 = 本檔往上 3 層 (research/active/H094-.../explore.py)
DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
SYMBOL = "TX"
# (序號, 達到率, τ)；τ = 1 − 達到率
TIERS = [("L1", "90%", 0.10), ("L2", "75%", 0.25), ("L3", "50%", 0.50), ("L4", "25%", 0.75)]


def build_dataset() -> pd.DataFrame:
    """每筆 = (day, direction)：max 方向擺動、夜盤振幅、causal EMA20(日盤振幅)。"""
    with duckdb.connect(DB, read_only=True) as conn:
        bars = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, high, low FROM ohlcv_1m WHERE symbol = ? "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE) >= DATE '2020-01-01' ORDER BY timestamp",
            [SYMBOL],
        ).df()
        night = conn.execute(
            """
            WITH td AS (SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m
                        WHERE symbol=? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'),
                 nd AS (SELECT DISTINCT CAST(timestamp AS DATE) nd FROM ohlcv_1m
                        WHERE symbol=? AND CAST(timestamp AS TIME) >= TIME '15:00:00'),
                 nm AS (SELECT nd, (SELECT min(d) FROM td WHERE d>nd) sd FROM nd),
                 asg AS (SELECT b.high,b.low,
                           CASE WHEN CAST(b.timestamp AS TIME)>=TIME '15:00:00' THEN nm.sd
                                ELSE CAST(b.timestamp AS DATE) END sd
                         FROM ohlcv_1m b LEFT JOIN nm ON nm.nd=CAST(b.timestamp AS DATE)
                         WHERE b.symbol=? AND (CAST(b.timestamp AS TIME)>=TIME '15:00:00'
                               OR CAST(b.timestamp AS TIME)<=TIME '05:00:00'))
            SELECT sd d, MAX(high)-MIN(low) night FROM asg WHERE sd IS NOT NULL GROUP BY 1
            """,
            [SYMBOL, SYMBOL, SYMBOL],
        ).df()
    bars["d"] = pd.to_datetime(bars["d"])
    bars["high"] = bars["high"].astype(float)
    bars["low"] = bars["low"].astype(float)
    night["d"] = pd.to_datetime(night["d"])
    night = night.set_index("d")["night"].astype(float)

    day_rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = day_rng.shift(1).ewm(span=20, adjust=False).mean()  # causal, 不含當日

    recs = []
    for d, g in bars.groupby("d"):
        nr, e20 = night.get(d), ema20.get(d)
        if nr is None or pd.isna(nr) or e20 is None or pd.isna(e20):
            continue
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        run_lo = np.minimum.accumulate(l)
        run_hi = np.maximum.accumulate(h)
        up = float(np.max(h - run_lo))   # 全日最大上擺
        dn = float(np.max(run_hi - l))   # 全日最大下擺
        recs.append({"d": d, "swing": up, "night": nr, "ema": e20})
        recs.append({"d": d, "swing": dn, "night": nr, "ema": e20})
    return pd.DataFrame(recs)


def pinball(resid: np.ndarray, tau: float) -> float:
    return np.mean(np.maximum(tau * resid, (tau - 1) * resid))


def fit_quantile(y: np.ndarray, X: np.ndarray, tau: float) -> np.ndarray:
    """無常數分位迴歸：min Σ pinball(y − X·β)。X shape (n,k)。"""
    k = X.shape[1]
    # 初值：OLS-ish
    beta0 = np.linalg.lstsq(X, y, rcond=None)[0]
    res = minimize(lambda b: pinball(y - X @ b, tau), beta0, method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-4, "maxiter": 20000})
    return res.x


def coverage(y: np.ndarray, pred: np.ndarray) -> float:
    """實際達到率 = swing ≥ 預測距離 的比例。"""
    return float(np.mean(y >= pred))


def main():
    df = build_dataset()
    df["year"] = df["d"].dt.year
    print(f"樣本 {len(df)} 筆 (day×dir)，{df['d'].min().date()} ~ {df['d'].max().date()}")
    print(f"夜盤 vs EMA20 相關：{np.corrcoef(df['night'], df['ema'])[0,1]:.3f}\n")

    yA = df["swing"].to_numpy()
    XA = df[["night", "ema"]].to_numpy()
    XB = df[["ema"]].to_numpy()

    print(f"{'階':<3}{'達到率':<6}{'τ':<6} | {'A:a夜盤':>8}{'A:b_ema':>9}{'A:pin':>8}{'A:cov':>7} | "
          f"{'B:c_ema':>9}{'B:pin':>8}{'B:cov':>7} | {'pin增幅':>8}")
    print("-" * 96)
    rows = []
    for lvl, reach, tau in TIERS:
        bA = fit_quantile(yA, XA, tau)
        bB = fit_quantile(yA, XB, tau)
        predA, predB = XA @ bA, XB @ bB
        pinA, pinB = pinball(yA - predA, tau), pinball(yA - predB, tau)
        covA, covB = coverage(yA, predA), coverage(yA, predB)
        rows.append((lvl, reach, tau, bA, bB, pinA, pinB, covA, covB))
        print(f"{lvl:<3}{reach:<6}{tau:<6.2f} | {bA[0]:>8.3f}{bA[1]:>9.3f}{pinA:>8.2f}{covA:>7.0%} | "
              f"{bB[0]:>9.3f}{pinB:>8.2f}{covB:>7.0%} | {(pinB/pinA-1):>7.1%}")

    print("\n現行 daystats 係數：L1(.159,.440) L2(.157,.637) L3(.274,.671) L4(.245,1.044)")

    # OOS：train 2021-2024 → test 2025-2026 覆蓋率
    tr = df[df["year"] <= 2024]
    te = df[df["year"] >= 2025]
    print(f"\n=== OOS 覆蓋（train≤2024 n={len(tr)} → test≥2025 n={len(te)}）===")
    print(f"{'階':<3}{'目標':<6} | {'A 覆蓋':>8}{'B 覆蓋':>8}")
    print("-" * 30)
    yTr, yTe = tr["swing"].to_numpy(), te["swing"].to_numpy()
    XAtr, XAte = tr[["night", "ema"]].to_numpy(), te[["night", "ema"]].to_numpy()
    XBtr, XBte = tr[["ema"]].to_numpy(), te[["ema"]].to_numpy()
    for lvl, reach, tau in TIERS:
        bA = fit_quantile(yTr, XAtr, tau)
        bB = fit_quantile(yTr, XBtr, tau)
        covA = coverage(yTe, XAte @ bA)
        covB = coverage(yTe, XBte @ bB)
        print(f"{lvl:<3}{reach:<6} | {covA:>8.0%}{covB:>8.0%}")

    # 夜盤的邊際貢獻：固定 EMA20，比較高/低夜盤日的實際 swing 差異
    print("\n=== 夜盤的邊際資訊（控制 EMA20 後）===")
    df["ema_q"] = pd.qcut(df["ema"], 3, labels=["低EMA", "中EMA", "高EMA"])
    df["night_q"] = pd.qcut(df["night"], 2, labels=["夜盤低", "夜盤高"])
    piv = df.pivot_table(index="ema_q", columns="night_q", values="swing", aggfunc="median", observed=True)
    print("各格 = 中位 swing：")
    print(piv.round(0).to_string())
    print("→ 若同 EMA 列內『夜盤高/低』兩欄差異大，代表夜盤有 EMA 取代不了的資訊。")


if __name__ == "__main__":
    main()

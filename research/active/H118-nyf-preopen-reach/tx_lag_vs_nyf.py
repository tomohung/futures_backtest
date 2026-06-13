"""H118 衍生·決定性測試：NYF 的增量是『0050 獨立資訊』還是只是『慢半拍的 TX』？

前測（tx_vs_nyf_increment.py）發現 NYF 延伸力對 TX 有正的增量 partial corr。但 NYF 成交稀疏
（08:45–09:00 每分 1~2 筆），報價可能 stale → NYF@t ≈ 幾分鐘前的 TX。若如此，NYF 的『增量』
其實被 TX 自身落後路徑(lag)所涵蓋，並非 0050 帶來的獨立資訊。

測法：對每個檢查點 t，比較 outcome 的巢狀 R²：
  M0: out ~ TX@t
  M1: out ~ TX@t + TX@(t-5) + TX@(t-10)            ← 只用 TX 自身近期軌跡
  M2: out ~ TX@t + TX@(t-5) + TX@(t-10) + NYF@t     ← 再加 NYF
  ΔR²(M2−M1) = NYF 在『TX 自身軌跡』之上的真增量。若 ≈0 → NYF = 慢半拍 TX，無獨立價值。
對照組 M1b/M2b：把 NYF@t 換成 TX@(t-5) 再加一階，看『多一個 TX lag』本來能加多少（基準感）。
"""
from __future__ import annotations
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
ANCHOR = "08:45:00"
# 檢查點 → 要用的 TX lag 時刻（t, t-5, t-10）
CPS = {
    "09:00:00": ["09:00:00", "08:55:00", "08:50:00"],
    "09:15:00": ["09:15:00", "09:10:00", "09:05:00"],
    "09:30:00": ["09:30:00", "09:25:00", "09:20:00"],
    "10:00:00": ["10:00:00", "09:55:00", "09:50:00"],
}
ALL_TIMES = sorted({t for v in CPS.values() for t in v})


def causal_ema20(s):
    return s.shift(1).ewm(span=20, adjust=False).mean()


def load(con, table, symbol):
    return con.execute(
        f"SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low, close "
        f"FROM {table} WHERE symbol=? AND CAST(timestamp AS TIME) "
        f"BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d,t", [symbol]).df()


def daily_ema(bars):
    g = bars.groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
    return causal_ema20((g["hi"] - g["lo"]).astype(float))


def ext_at(bars, ema, times):
    """每日在指定 times 的 ext = tanh((close@t − open@08:45)/EMA20)。"""
    out = {}
    for d, g in bars.groupby("d"):
        e = ema.get(d, np.nan)
        if not np.isfinite(e) or e <= 0:
            continue
        gi = g.set_index(g["t"].astype(str))
        if ANCHOR not in gi.index:
            continue
        opn = float(gi.loc[ANCHOR, "open"])
        out[d] = {tm: (np.tanh((float(gi.loc[tm, "close"]) - opn) / e) if tm in gi.index else np.nan)
                  for tm in times}
    return pd.DataFrame.from_dict(out, orient="index")


def outcomes(tx, ema):
    rows = {}
    for d, g in tx.groupby("d"):
        e = ema.get(d, np.nan)
        if not np.isfinite(e) or e <= 0:
            continue
        g = g.sort_values("t").reset_index(drop=True)
        low = g["low"].astype(float).to_numpy()
        high = g["high"].astype(float).to_numpy()
        close = g["close"].astype(float).to_numpy()
        tstr = g["t"].astype(str).to_numpy()
        up_max = np.maximum.accumulate(high - np.minimum.accumulate(low))
        rec = {"A_full": up_max[-1] / e}
        for cp in CPS:
            idx = np.where(tstr == cp)[0]
            if len(idx):
                i = idx[0]
                rec[f"B_fwd@{cp}"] = ((high[i + 1:].max() - close[i]) / e) if i + 1 < len(high) else 0.0
        rows[d] = rec
    return pd.DataFrame.from_dict(rows, orient="index")


def r2(df, ycol, xcols):
    sub = df[[ycol] + xcols].dropna()
    if len(sub) < 50:
        return np.nan, 0
    y = sub[ycol].to_numpy()
    X = np.column_stack([np.ones(len(sub))] + [sub[c].to_numpy() for c in xcols])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_tot = ((y - y.mean()) ** 2).sum()
    return (1 - ((y - pred) ** 2).sum() / ss_tot if ss_tot > 0 else np.nan), len(sub)


def main():
    con = duckdb.connect(DB, read_only=True)
    tx, nyf = load(con, "ohlcv_1m", "TX"), load(con, "aux_futures_1m", "NYF")
    ema_tx, ema_nyf = daily_ema(tx), daily_ema(nyf)
    tx_ext = ext_at(tx, ema_tx, ALL_TIMES).add_prefix("TX@")
    nyf_ext = ext_at(nyf, ema_nyf, list(CPS)).add_prefix("NYF@")
    out = outcomes(tx, ema_tx)
    df = tx_ext.join(nyf_ext, how="inner").join(out, how="inner")
    print(f"N={len(df)}  ({df.index.min().date()} ~ {df.index.max().date()})\n")
    print("巢狀 R²：M0=TX@t | M1=+TX lags(t-5,t-10) | M2=+NYF@t | M2b=+一個額外 TX lag(t-15) 對照\n")

    for cp, lags in CPS.items():
        t, l5, l10 = [f"TX@{x}" for x in lags]
        ncol = f"NYF@{cp}"
        # 額外 TX lag 對照 (t-15)：用 09:xx-15 的 TX 當「再多一個 lag」基準
        hh, mm = int(cp[:2]), int(cp[3:5])
        m15 = mm - 15
        hh2 = hh + (m15 // 60 if m15 < 0 else 0)
        l15 = f"TX@{hh2:02d}:{(m15 % 60):02d}:00"
        for oname, ocol in [("A_full ladder", "A_full"), ("B_fwd 未來上漲", f"B_fwd@{cp}")]:
            m0, _ = r2(df, ocol, [t])
            m1, _ = r2(df, ocol, [t, l5, l10])
            m2, n = r2(df, ocol, [t, l5, l10, ncol])
            d_nyf = m2 - m1
            line = (f"  {cp[:5]} {oname:14s} | R² M0 {m0:.4f} → M1 {m1:.4f} → M2 {m2:.4f}"
                    f" | ΔR²(+NYF over TX軌跡) {d_nyf:+.4f}")
            if l15 in df.columns:
                m2b, _ = r2(df, ocol, [t, l5, l10, l15])
                line += f" | 對照 ΔR²(+1個TX lag) {m2b - m1:+.4f}"
            print(line + f"  n={n}")
        print()

    # 逐年穩健性：09:30 檢查點，NYF 在 TX 軌跡之上的 ΔR²（確認非單一 regime 撐出）
    print("逐年穩健性（09:30，ΔR² = NYF over TX軌跡 t/t-5/t-10）：")
    cp = "09:30:00"
    t, l5, l10 = [f"TX@{x}" for x in CPS[cp]]
    ncol = f"NYF@{cp}"
    yr = df.index.to_series().dt.year
    for y in sorted(yr.unique()):
        sub = df[yr.values == y]
        for oname, ocol in [("A_full", "A_full"), ("B_fwd", f"B_fwd@{cp}")]:
            m1, _ = r2(sub, ocol, [t, l5, l10])
            m2, n = r2(sub, ocol, [t, l5, l10, ncol])
            print(f"  {y} {oname:7s} ΔR²(+NYF) {m2 - m1:+.4f}  (M1 {m1:.4f}→M2 {m2:.4f})  n={n}")
        print()


if __name__ == "__main__":
    main()

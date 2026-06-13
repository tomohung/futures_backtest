"""H118 衍生：NYF(0050期) 延伸力多 相對 TX(台指期) 自身的『增量價值』檢定。

問題：延伸力多現在用 NYF 算。但 NYF 與 TX 都是台灣大型權值指數期、且同樣 08:45 開盤
（彼此無時鐘領先；『領先 15 分』是相對 09:00 才開的現貨）。懷疑 NYF 讀數只是 TX 的影子，
對 L1-L5 ladder 達成沒有 TX 以外的獨立資訊。

設計：每個檢查點 t ∈ {08:50,08:55,09:00,09:15,09:30,10:00}
  predictor: ext(t) = tanh((close@t − open@08:45) / EMA20_range)   兩個標的各自算
  outcome（皆以 TX 定義，因為 ladder 是 TX 驅動）：
    A_full : 全日盤『多方 running-low 最大上擺 / EMA20_TX』（= 系統 ladder reach）
    B_fwd  : t 之後『未來最高 − close@t / EMA20_TX』（乾淨領先測：去除 t 之前的路徑重疊）
    L3/L4  : 全日是否達 0.711 / 0.977 × EMA20（binary）
  比較：
    corr(TX,out) baseline、corr(NYF,out)、corr(TX,NYF) 冗餘度
    partial corr(NYF,out | TX) ← NYF 對 TX 的增量；若≈0 → NYF 無獨立價值
    partial corr(TX,out | NYF) ← 對照（預期 >> NYF 的增量）
    ΔR²：outcome ~ TX 之上再加 NYF 多解釋多少
皆出 Pearson 與 Spearman。
"""
from __future__ import annotations
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
CHECKPOINTS = ["08:50:00", "08:55:00", "09:00:00", "09:15:00", "09:30:00", "10:00:00"]
L3_COEF, L4_COEF = 0.711, 0.977
ANCHOR = "08:45:00"


def causal_ema20(daily_rng: pd.Series) -> pd.Series:
    """日振幅序列 → causal EMA20（shift(1) 後 ewm span=20, adjust=False），index=date。"""
    return daily_rng.shift(1).ewm(span=20, adjust=False).mean()


def load(con, table: str, symbol: str) -> pd.DataFrame:
    return con.execute(
        f"SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, "
        f"open, high, low, close FROM {table} WHERE symbol = ? "
        f"AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        f"ORDER BY d, t", [symbol]).df()


def ext_series(bars: pd.DataFrame, ema: pd.Series) -> pd.DataFrame:
    """每日每檢查點 ext = tanh((close@t − open@08:45)/EMA20)。回 wide: index=date, cols=checkpoints。"""
    out = {}
    for d, g in bars.groupby("d"):
        e = ema.get(d, np.nan)
        if not np.isfinite(e) or e <= 0:
            continue
        g = g.set_index(g["t"].astype(str))
        if ANCHOR not in g.index:
            continue
        opn = float(g.loc[ANCHOR, "open"])
        row = {}
        for cp in CHECKPOINTS:
            if cp in g.index:
                row[cp] = np.tanh((float(g.loc[cp, "close"]) - opn) / e)
        out[d] = row
    return pd.DataFrame.from_dict(out, orient="index")


def outcomes(tx_bars: pd.DataFrame, ema_tx: pd.Series) -> pd.DataFrame:
    """以 TX 算 outcome：A_full(ladder reach) + 每檢查點的 B_fwd + binary L3/L4。"""
    rows = {}
    for d, g in tx_bars.groupby("d"):
        e = ema_tx.get(d, np.nan)
        if not np.isfinite(e) or e <= 0:
            continue
        g = g.sort_values("t").reset_index(drop=True)
        low = g["low"].astype(float).to_numpy()
        high = g["high"].astype(float).to_numpy()
        close = g["close"].astype(float).to_numpy()
        tstr = g["t"].astype(str).to_numpy()
        run_lo = np.minimum.accumulate(low)
        up_max = np.maximum.accumulate(high - run_lo)        # 方向性上擺（running-low 起算）
        full = up_max[-1] / e
        rec = {"A_full": full, "L3": int(up_max[-1] >= L3_COEF * e),
               "L4": int(up_max[-1] >= L4_COEF * e)}
        # 每檢查點 forward 上漲：t 之後最高 − close@t
        for cp in CHECKPOINTS:
            idx = np.where(tstr == cp)[0]
            if len(idx) == 0:
                continue
            i = idx[0]
            if i + 1 < len(high):
                fwd = (high[i + 1:].max() - close[i]) / e
            else:
                fwd = 0.0
            rec[f"B_fwd@{cp}"] = fwd
        rows[d] = rec
    return pd.DataFrame.from_dict(rows, orient="index")


def pcorr(x, y, z, method="pearson"):
    df = pd.DataFrame({"x": x, "y": y, "z": z}).dropna()
    n = len(df)
    if n < 30:
        return np.nan, n
    if method == "spearman":
        df = df.rank()
    rxy = df["x"].corr(df["y"])
    rxz = df["x"].corr(df["z"])
    ryz = df["y"].corr(df["z"])
    denom = np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
    return ((rxy - rxz * ryz) / denom if denom > 0 else np.nan), n


def corr(x, y, method="pearson"):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 30:
        return np.nan
    if method == "spearman":
        df = df.rank()
    return df["x"].corr(df["y"])


def r2(y, cols):
    df = pd.concat([y] + cols, axis=1).dropna()
    if len(df) < 30:
        return np.nan, 0
    yv = df.iloc[:, 0].to_numpy()
    X = np.column_stack([np.ones(len(df))] + [df.iloc[:, i + 1].to_numpy() for i in range(len(cols))])
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    pred = X @ beta
    ss_res = ((yv - pred) ** 2).sum()
    ss_tot = ((yv - yv.mean()) ** 2).sum()
    return (1 - ss_res / ss_tot if ss_tot > 0 else np.nan), len(df)


def main():
    con = duckdb.connect(DB, read_only=True)
    tx = load(con, "ohlcv_1m", "TX")
    nyf = load(con, "aux_futures_1m", "NYF")

    def daily_ema(bars):
        g = bars.groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
        return causal_ema20((g["hi"] - g["lo"]).astype(float))

    ema_tx = daily_ema(tx)
    ema_nyf = daily_ema(nyf)

    ext_tx = ext_series(tx, ema_tx).add_prefix("TX@")
    ext_nyf = ext_series(nyf, ema_nyf).add_prefix("NYF@")
    out = outcomes(tx, ema_tx)

    df = ext_tx.join(ext_nyf, how="inner").join(out, how="inner")
    print(f"共同樣本日數 N = {len(df)}  ({df.index.min()} ~ {df.index.max()})\n")

    for cp in CHECKPOINTS:
        tcol, ncol = f"TX@{cp}", f"NYF@{cp}"
        if tcol not in df or ncol not in df:
            continue
        red_p = corr(df[tcol], df[ncol], "pearson")
        red_s = corr(df[tcol], df[ncol], "spearman")
        print(f"━━━ 檢查點 {cp[:5]} ━━━  冗餘度 corr(TX,NYF): Pearson {red_p:+.3f} / Spearman {red_s:+.3f}")
        for oname, ocol in [("A_full ladder reach", "A_full"),
                            ("B_fwd 未來上漲", f"B_fwd@{cp}"),
                            ("L3 達成(binary)", "L3"),
                            ("L4 達成(binary)", "L4")]:
            if ocol not in df:
                continue
            cT = corr(df[tcol], df[ocol], "pearson")
            cN = corr(df[ncol], df[ocol], "pearson")
            cTs = corr(df[tcol], df[ocol], "spearman")
            cNs = corr(df[ncol], df[ocol], "spearman")
            pN, n = pcorr(df[ncol], df[ocol], df[tcol], "pearson")   # NYF 增量 | TX
            pT, _ = pcorr(df[tcol], df[ocol], df[ncol], "pearson")   # TX 增量 | NYF
            pNs, _ = pcorr(df[ncol], df[ocol], df[tcol], "spearman")
            r2_tx, _ = r2(df[ocol], [df[tcol]])
            r2_both, _ = r2(df[ocol], [df[tcol], df[ncol]])
            d_r2 = r2_both - r2_tx
            print(f"  {oname:20s} | corr TX {cT:+.3f} NYF {cN:+.3f}"
                  f" | 增量 partial NYF|TX {pN:+.3f}(sp {pNs:+.3f}) TX|NYF {pT:+.3f}"
                  f" | ΔR²(+NYF) {d_r2:+.4f}  [Spearman corr TX {cTs:+.3f} NYF {cNs:+.3f}] n={n}")
        print()


if __name__ == "__main__":
    main()

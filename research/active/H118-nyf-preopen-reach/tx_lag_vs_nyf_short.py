"""H118 衍生·空方鏡像：NYF 延伸力對 TX 空方(下擺) ladder 是否也有 TX 以外的獨立增量？

多方版（tx_lag_vs_nyf.py）證明 NYF 對 TX 多方上擺有真增量（非 stale TX）。空方目前系統用現貨
W100+廣度、無 NYF 版。但 NYF 單標的可雙向，故鏡像測之。

predictor：ext(t)=tanh((close@t−open@08:45)/EMA20)（有號；空方時 ext 偏負）。
outcome（TX 定義，空方）：
  A_full_dn：全日盤空方 running-high 最大下擺 / EMA20（系統空方 ladder reach，正數=幅度）。
  B_fwd_dn ：t 之後 close@t − 未來最低 / EMA20（乾淨領先，正數=後續下跌幅度）。
決定性控制（同多方版）：M1=TX@t+TX(t-5)+TX(t-10)；M2=+NYF@t；對照=+額外 TX lag(t-15)。
corr 對空方幅度會是『負相關』（ext 越負→下跌越大），partial/ΔR² 不受符號影響。
"""
from __future__ import annotations
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
ANCHOR = "08:45:00"
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


def outcomes_short(tx, ema):
    """空方下擺 outcome（皆正數=下跌幅度/EMA20）。"""
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
        dn_max = np.maximum.accumulate(np.maximum.accumulate(high) - low)  # running-high 起算最大下擺
        rec = {"A_full_dn": dn_max[-1] / e}
        for cp in CPS:
            idx = np.where(tstr == cp)[0]
            if len(idx):
                i = idx[0]
                rec[f"B_fwd_dn@{cp}"] = ((close[i] - low[i + 1:].min()) / e) if i + 1 < len(low) else 0.0
        rows[d] = rec
    return pd.DataFrame.from_dict(rows, orient="index")


def corr(df, a, b, method="pearson"):
    sub = df[[a, b]].dropna()
    if len(sub) < 30:
        return np.nan
    if method == "spearman":
        sub = sub.rank()
    return sub[a].corr(sub[b])


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
    out = outcomes_short(tx, ema_tx)
    df = tx_ext.join(nyf_ext, how="inner").join(out, how="inner")
    print(f"N={len(df)}  ({df.index.min().date()} ~ {df.index.max().date()})  【空方下擺】\n")
    print("corr 為負屬正常（ext 越負→下跌越大）。巢狀 R²：M1=TX軌跡 → M2=+NYF；對照=+額外TX lag\n")

    for cp, lags in CPS.items():
        t, l5, l10 = [f"TX@{x}" for x in lags]
        ncol = f"NYF@{cp}"
        hh, mm = int(cp[:2]), int(cp[3:5])
        m15 = mm - 15
        l15 = f"TX@{(hh + (m15 // 60 if m15 < 0 else 0)):02d}:{(m15 % 60):02d}:00"
        for oname, ocol in [("A_full_dn ladder", "A_full_dn"), ("B_fwd_dn 未來下跌", f"B_fwd_dn@{cp}")]:
            cT, cN = corr(df, t, ocol), corr(df, ncol, ocol)
            m0, _ = r2(df, ocol, [t])
            m1, _ = r2(df, ocol, [t, l5, l10])
            m2, n = r2(df, ocol, [t, l5, l10, ncol])
            line = (f"  {cp[:5]} {oname:17s} | corr TX {cT:+.3f} NYF {cN:+.3f}"
                    f" | R² M1 {m1:.4f}→M2 {m2:.4f} | ΔR²(+NYF) {m2 - m1:+.4f}")
            if l15 in df.columns:
                m2b, _ = r2(df, ocol, [t, l5, l10, l15])
                line += f" | 對照 ΔR²(+TX lag) {m2b - m1:+.4f}"
            print(line + f"  n={n}")
        print()

    print("逐年穩健性（09:30，ΔR² = NYF over TX軌跡）：")
    cp = "09:30:00"
    t, l5, l10 = [f"TX@{x}" for x in CPS[cp]]
    ncol = f"NYF@{cp}"
    yr = df.index.to_series().dt.year
    for y in sorted(yr.unique()):
        sub = df[yr.values == y]
        for oname, ocol in [("A_full_dn", "A_full_dn"), ("B_fwd_dn", f"B_fwd_dn@{cp}")]:
            m1, _ = r2(sub, ocol, [t, l5, l10])
            m2, n = r2(sub, ocol, [t, l5, l10, ncol])
            print(f"  {y} {oname:10s} ΔR²(+NYF) {m2 - m1:+.4f}  (M1 {m1:.4f}→M2 {m2:.4f})  n={n}")
        print()


if __name__ == "__main__":
    main()

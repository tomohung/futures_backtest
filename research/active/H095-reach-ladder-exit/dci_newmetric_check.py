"""DCI 指標改版影響檢查：W/H 由 value-weighted SIGN(change) → 等權兩票
（sign(close-prev)+sign(close-open)），且強多門檻 +0.30→+0.20。

問題：改版後 DCI 對台指當日 reach 的鑑別力有沒有變差/變好？門檻 ±0.20 是否站得住？
方法（對齊 dci_spec §5，皆同日收盤值 / hindsight）：
  - TX 當日 reach：open-anchor，上方/下方 L3 觸及 = 擺幅 ≥ 0.711×causal EMA20(日盤振幅)。
  - DCI_long ↔ 上方 L3、DCI_short ↔ 下方 L3。
  - 比 old vs new：point-biserial 相關、各 band 的 P(reach)、十分位單調性、門檻定位。
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
_WL = (0.40, 0.35, 0.25)
_WS = (0.30, 0.30, 0.40)
L3 = 0.711  # EMA-only L3 係數


def _sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def strength_new(rows):
    t = n = 0
    for last, prev, op in rows:
        if last is not None and prev is not None:
            t += _sign(last - prev); n += 1
        if last is not None and op is not None:
            t += _sign(last - op); n += 1
    return t / n if n else None


def strength_old(rows):
    """value-weighted SIGN(change)。rows=(change, value)。"""
    num = den = 0.0
    for ch, val in rows:
        if ch is None or val is None:
            continue
        num += _sign(ch) * val; den += val
    return num / den if den else None


def tx_reach() -> pd.DataFrame:
    """TX 每日 up_L3 / dn_L3（open-anchor, causal EMA20）。"""
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            """
            SELECT CAST(timestamp AS DATE) d,
                   arg_min(open, timestamp) AS open,
                   MAX(high) AS high, MIN(low) AS low
            FROM ohlcv_1m WHERE symbol='TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1 ORDER BY 1
            """
        ).df()
    df["d"] = pd.to_datetime(df["d"])
    for col in ["open", "high", "low"]:
        df[col] = df[col].astype(float)
    df = df.set_index("d").sort_index()
    rng = df["high"] - df["low"]
    ema20 = rng.shift(1).ewm(span=20, adjust=False).mean()
    dist = L3 * ema20
    df["up_L3"] = ((df["high"] - df["open"]) >= dist).astype(float)
    df["dn_L3"] = ((df["open"] - df["low"]) >= dist).astype(float)
    return df.dropna(subset=["up_L3"])[["up_L3", "dn_L3"]]


def dci_series() -> pd.DataFrame:
    """每日 old/new 的 dci_long / dci_short。"""
    with duckdb.connect(DB, read_only=True) as c:
        dates = [r[0] for r in c.execute(
            "SELECT DISTINCT trade_date FROM stock_day WHERE market='TWSE' ORDER BY trade_date"
        ).fetchall()]
        ph = ",".join(["?"] * len(TOP_WEIGHT_SYMBOLS))
        recs = []
        for d in dates:
            b = c.execute("SELECT up_count,down_count,listed_count FROM market_breadth "
                          "WHERE market='TWSE' AND trade_date=?", [d]).fetchone()
            if not b or not b[2]:
                continue
            B = (b[0] - b[1]) / b[2]
            # W rows
            wr = c.execute(f"SELECT close,change,open FROM stock_day WHERE market='TWSE' "
                           f"AND trade_date=? AND symbol IN ({ph}) AND close IS NOT NULL",
                           [d, *TOP_WEIGHT_SYMBOLS]).fetchall()
            hr = c.execute("SELECT close,change,open FROM stock_day WHERE market='TWSE' "
                           "AND trade_date=? AND close IS NOT NULL AND value IS NOT NULL "
                           "ORDER BY value DESC LIMIT 20", [d]).fetchall()
            def split_new(rows):
                return [(float(cl), float(cl) - float(ch) if ch is not None else None,
                         float(op) if op is not None else None) for cl, ch, op in rows]
            Wn = strength_new(split_new(wr)); Hn = strength_new(split_new(hr))
            # old needs value-weighted; refetch with value
            wo = c.execute(f"SELECT change,value FROM stock_day WHERE market='TWSE' "
                           f"AND trade_date=? AND symbol IN ({ph}) AND change IS NOT NULL "
                           f"AND value IS NOT NULL", [d, *TOP_WEIGHT_SYMBOLS]).fetchall()
            ho = c.execute("SELECT change,value FROM stock_day WHERE market='TWSE' "
                           "AND trade_date=? AND change IS NOT NULL AND value IS NOT NULL "
                           "ORDER BY value DESC LIMIT 20", [d]).fetchall()
            Wo = strength_old(wo); Ho = strength_old(ho)
            if None in (Wn, Hn, Wo, Ho):
                continue
            recs.append({
                "d": pd.Timestamp(d),
                "long_old": _WL[0]*Wo+_WL[1]*Ho+_WL[2]*B,
                "short_old": _WS[0]*Wo+_WS[1]*Ho+_WS[2]*B,
                "long_new": _WL[0]*Wn+_WL[1]*Hn+_WL[2]*B,
                "short_new": _WS[0]*Wn+_WS[1]*Hn+_WS[2]*B,
            })
    return pd.DataFrame(recs).set_index("d")


def pbcorr(x, y):
    """point-biserial = pearson(連續, 0/1)。"""
    return float(np.corrcoef(x, y)[0, 1])


def band_prob(score, reach, lo=None, hi=None):
    m = np.ones(len(score), bool)
    if lo is not None:
        m &= score >= lo
    if hi is not None:
        m &= score < hi
    return reach[m].mean() if m.any() else float("nan"), int(m.sum())


def main():
    reach = tx_reach()
    dci = dci_series()
    df = dci.join(reach, how="inner").dropna()
    print(f"合併樣本 N={len(df)}  {df.index.min().date()} ~ {df.index.max().date()}")
    up = df["up_L3"].to_numpy(); dn = df["dn_L3"].to_numpy()
    print(f"基準 P(上方L3)={up.mean():.1%}  P(下方L3)={dn.mean():.1%}\n")

    print("=== 1) 鑑別力：point-biserial 相關（|越大|越能分辨 reach）===")
    print(f"  多方  dci_long ↔ 上方L3 :  old {pbcorr(df['long_old'],up):+.3f}   new {pbcorr(df['long_new'],up):+.3f}")
    print(f"  空方  dci_short↔ 下方L3 :  old {pbcorr(df['short_old'],dn):+.3f}   new {pbcorr(df['short_new'],dn):+.3f}")

    print("\n=== 2) 強帶 P(reach)：舊門檻 vs 新門檻 ===")
    p, n = band_prob(df['long_old'].to_numpy(), up, lo=0.30)
    print(f"  多·強 old(≥+0.30): P(上方L3)={p:.1%}  N={n}   (vs 基準 {up.mean():.1%})")
    p, n = band_prob(df['long_new'].to_numpy(), up, lo=0.20)
    print(f"  多·強 new(≥+0.20): P(上方L3)={p:.1%}  N={n}")
    p, n = band_prob(df['short_old'].to_numpy(), dn, hi=-0.20)
    print(f"  空·強 old(≤−0.20): P(下方L3)={p:.1%}  N={n}   (vs 基準 {dn.mean():.1%})")
    p, n = band_prob(df['short_new'].to_numpy(), dn, hi=-0.20)
    print(f"  空·強 new(≤−0.20): P(下方L3)={p:.1%}  N={n}")

    print("\n=== 3) 十分位單調性（new dci_long → 上方L3 reach）===")
    q = pd.qcut(df['long_new'], 10, labels=False, duplicates="drop")
    g = pd.DataFrame({"q": q, "up": up}).groupby("q")["up"].agg(["mean", "count"])
    edges = pd.qcut(df['long_new'], 10, duplicates="drop").cat.categories
    for i, (_, r) in enumerate(g.iterrows()):
        rng = f"[{edges[i].left:+.2f},{edges[i].right:+.2f}]"
        bar = "█" * int(r["mean"] * 40)
        print(f"  D{i} {rng:<16} P(上L3)={r['mean']:.0%} (n={int(r['count'])}) {bar}")

    print("\n=== 4) 新門檻定位：P(上方L3) 隨 dci_long 門檻 ===")
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30):
        p, n = band_prob(df['long_new'].to_numpy(), up, lo=thr)
        print(f"  dci_long ≥ +{thr:.2f}: P(上方L3)={p:.1%}  N={n} ({n/len(df):.0%} of days)")


if __name__ == "__main__":
    main()

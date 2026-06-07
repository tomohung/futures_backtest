"""DCI 投票組合三方對照：W/H 的每檔投票集合改變時，對台指當日 reach 的鑑別力。

背景：W（權值前20）、H（成交值前20）目前每檔投「兩票」：
  sign(close-prev) + sign(close-open)（等權）。
問題（使用者提問）：如果每檔只用「今開→今收」這一票（丟掉昨收票），效果會更好嗎？

三種變體（B=漲跌家數淨值不變、W/H 合成權重不變，只換投票集合）：
  - PREV  : 每檔僅 sign(close-prev)          —— 純隔日（原始想法的等權版）
  - BOTH  : 每檔 sign(close-prev)+sign(close-open) —— 目前線上版
  - OC    : 每檔僅 sign(close-open)           —— 只看當天開收

評估（對齊 dci_spec §5，皆收盤事後值）：
  - TX 當日 reach：open-anchor，上方/下方 L3 = 擺幅 ≥ 0.711×causal EMA20(日盤振幅)。
  - DCI_long ↔ 上方 L3、DCI_short ↔ 下方 L3。
  - 指標：point-biserial 相關、強帶 P(reach)、十分位單調性。
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
_WL = (0.40, 0.35, 0.25)   # long: W,H,B
_WS = (0.30, 0.30, 0.40)   # short
L3 = 0.711

VARIANTS = ("prev", "both", "oc")


def _sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def strength(rows, mode):
    """rows=(last, prev, open)。mode∈{prev,both,oc} 決定每檔投票集合，等權平均。"""
    t = n = 0
    for last, prev, op in rows:
        if mode in ("prev", "both") and last is not None and prev is not None:
            t += _sign(last - prev); n += 1
        if mode in ("oc", "both") and last is not None and op is not None:
            t += _sign(last - op); n += 1
    return t / n if n else None


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
    """每日三變體的 dci_long / dci_short。"""
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
            wr = c.execute(f"SELECT close,change,open FROM stock_day WHERE market='TWSE' "
                           f"AND trade_date=? AND symbol IN ({ph}) AND close IS NOT NULL",
                           [d, *TOP_WEIGHT_SYMBOLS]).fetchall()
            hr = c.execute("SELECT close,change,open FROM stock_day WHERE market='TWSE' "
                           "AND trade_date=? AND close IS NOT NULL AND value IS NOT NULL "
                           "ORDER BY value DESC LIMIT 20", [d]).fetchall()

            def split(rows):
                return [(float(cl), float(cl) - float(ch) if ch is not None else None,
                         float(op) if op is not None else None) for cl, ch, op in rows]

            wr, hr = split(wr), split(hr)
            rec = {"d": pd.Timestamp(d)}
            ok = True
            for m in VARIANTS:
                W = strength(wr, m); H = strength(hr, m)
                if W is None or H is None:
                    ok = False; break
                rec[f"long_{m}"] = _WL[0]*W + _WL[1]*H + _WL[2]*B
                rec[f"short_{m}"] = _WS[0]*W + _WS[1]*H + _WS[2]*B
            if ok:
                recs.append(rec)
    return pd.DataFrame(recs).set_index("d")


def pbcorr(x, y):
    return float(np.corrcoef(x, y)[0, 1])


def band_prob(score, reach, lo=None, hi=None):
    m = np.ones(len(score), bool)
    if lo is not None:
        m &= score >= lo
    if hi is not None:
        m &= score < hi
    return (reach[m].mean() if m.any() else float("nan")), int(m.sum())


def deciles(score, reach, label):
    print(f"\n  十分位單調性（{label}）：")
    q = pd.qcut(score, 10, labels=False, duplicates="drop")
    g = pd.DataFrame({"q": q, "r": reach}).groupby("q")["r"].agg(["mean", "count"])
    edges = pd.qcut(score, 10, duplicates="drop").cat.categories
    for i, (_, r) in enumerate(g.iterrows()):
        rng = f"[{edges[i].left:+.2f},{edges[i].right:+.2f}]"
        bar = "█" * int(r["mean"] * 40)
        print(f"    D{i} {rng:<16} P={r['mean']:.0%} (n={int(r['count'])}) {bar}")


def main():
    reach = tx_reach()
    dci = dci_series()
    df = dci.join(reach, how="inner").dropna()
    up = df["up_L3"].to_numpy(); dn = df["dn_L3"].to_numpy()
    print(f"合併樣本 N={len(df)}  {df.index.min().date()} ~ {df.index.max().date()}")
    print(f"基準 P(上方L3)={up.mean():.1%}  P(下方L3)={dn.mean():.1%}\n")

    names = {"prev": "PREV(只昨收)", "both": "BOTH(目前線上)", "oc": "OC(只開收)"}

    print("=== 1) 鑑別力：point-biserial 相關（|越大|越能分辨 reach）===")
    print(f"  {'變體':<16}{'多 long↔上L3':>14}{'空 short↔下L3':>16}")
    for m in VARIANTS:
        cl = pbcorr(df[f"long_{m}"], up)
        cs = pbcorr(df[f"short_{m}"], dn)
        print(f"  {names[m]:<16}{cl:>+14.3f}{cs:>+16.3f}")

    print("\n=== 2) 強帶 P(reach)（門檻固定 ±0.20，比命中率與覆蓋）===")
    print(f"  {'變體':<16}{'多·強≥+0.20':>22}{'空·強≤−0.20':>22}")
    for m in VARIANTS:
        pl, nl = band_prob(df[f"long_{m}"].to_numpy(), up, lo=0.20)
        ps, ns = band_prob(df[f"short_{m}"].to_numpy(), dn, hi=-0.20)
        print(f"  {names[m]:<16}{f'{pl:.1%} (N={nl})':>22}{f'{ps:.1%} (N={ns})':>22}")
    print(f"  {'基準':<16}{f'{up.mean():.1%}':>22}{f'{dn.mean():.1%}':>22}")

    print("\n=== 3) 十分位單調性（多方 long → 上方L3）===")
    for m in VARIANTS:
        deciles(df[f"long_{m}"], up, names[m])


if __name__ == "__main__":
    main()

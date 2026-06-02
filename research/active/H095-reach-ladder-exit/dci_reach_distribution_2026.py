"""2026 DCI 強度分佈 × 關卡價(L1–L4)達成率。

問題（使用者）：2026 年 DCI 強度怎麼分佈？尤其 |DCI| ≥ 0.2 / 0.3 / 0.4 / 0.5
各 band 對應「關卡價」的達成率分佈為何？

定義（與 chart-ui daystats / dci_daily 完全對齊，皆收盤/事後值 hindsight）：
- DCI：compute_daily_dci()（等權兩票 sign，W=權值20、H=成交值前20、B=漲跌家數）。
  多方看 dci_long、空方看 dci_short（多空不對稱權重，見 dci_spec §5）。
- 關卡價 L1–L4 = c×causal-EMA20(日盤振幅)，c=0.385/0.497/0.711/0.977，名目達到率 90/75/50/25%。
- 達成 = 當日「方向性擺動」達該距離：上擺 up_max=max(high−當下running low)、
  下擺 dn_max=max(當下running high−low)，與 daystats._collect_touches 同義。
- 多方 band（dci_long ≥ +thr）→ 上擺達標；空方 band（dci_short ≤ −thr）→ 下擺達標。
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.chart_ui.services.dci_daily import compute_daily_dci

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
LVL = [("L1", 0.385, "90%"), ("L2", 0.497, "75%"),
       ("L3", 0.711, "50%"), ("L4", 0.977, "25%")]


def daily_reach() -> pd.DataFrame:
    """每日 up_max / dn_max（方向性擺動，點數）+ causal EMA20(日盤振幅)。"""
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            """
            SELECT CAST(timestamp AS DATE) d, timestamp ts, high, low
            FROM ohlcv_1m WHERE symbol='TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY ts
            """
        ).df()
    bars["high"] = bars["high"].astype(float)
    bars["low"] = bars["low"].astype(float)
    recs = []
    for d, g in bars.groupby("d"):
        hi = g["high"].to_numpy()
        lo = g["low"].to_numpy()
        run_lo = np.minimum.accumulate(lo)
        run_hi = np.maximum.accumulate(hi)
        up_max = float(np.max(hi - run_lo))
        dn_max = float(np.max(run_hi - lo))
        recs.append({"d": pd.Timestamp(d), "rng": float(hi.max() - lo.min()),
                     "up_max": up_max, "dn_max": dn_max})
    df = pd.DataFrame(recs).set_index("d").sort_index()
    df["ema20"] = df["rng"].shift(1).ewm(span=20, adjust=False).mean()
    return df.dropna(subset=["ema20"])


def daily_dci() -> pd.DataFrame:
    with duckdb.connect(DB, read_only=True) as c:
        dates = [r[0] for r in c.execute(
            "SELECT DISTINCT trade_date FROM stock_day WHERE market='TWSE' ORDER BY trade_date"
        ).fetchall()]
        recs = []
        for d in dates:
            r = compute_daily_dci(c, d)
            if r:
                recs.append({"d": pd.Timestamp(d), "dci_long": r["dci_long"],
                             "dci_short": r["dci_short"]})
    return pd.DataFrame(recs).set_index("d")


def reach_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for lab, coef, _ in LVL:
        dist = coef * df["ema20"]
        out[f"up_{lab}"] = (df["up_max"] >= dist).astype(float)
        out[f"dn_{lab}"] = (df["dn_max"] >= dist).astype(float)
    return out


def hist(series: pd.Series, label: str):
    edges = [-1, -0.5, -0.4, -0.3, -0.2, -0.1, 0.1, 0.2, 0.3, 0.4, 0.5, 1.01]
    cats = pd.cut(series, edges, right=False)
    g = cats.value_counts().sort_index()
    n = len(series)
    print(f"\n--- {label} 分佈 (N={n}, mean={series.mean():+.3f}, "
          f"median={series.median():+.3f}, sd={series.std():.3f}) ---")
    for iv, cnt in g.items():
        bar = "█" * int(cnt / max(1, n) * 60)
        print(f"  [{iv.left:+.1f},{iv.right:+.1f}) {cnt:3d} ({cnt/n:4.0%}) {bar}")


def band_table(df: pd.DataFrame, side: str):
    """side='long'→多方(dci_long≥thr, 上擺)；'short'→空方(dci_short≤−thr, 下擺)。"""
    pre = "up" if side == "long" else "dn"
    score = df["dci_long"] if side == "long" else df["dci_short"]
    base = {lab: df[f"{pre}_{lab}"].mean() for lab, _, _ in LVL}
    title = "多方 dci_long ≥ +thr → 上擺達標" if side == "long" \
        else "空方 dci_short ≤ −thr → 下擺達標"
    print(f"\n=== {title}  (全樣本基準 N={len(df)}: "
          + " ".join(f"{lab} {base[lab]:.0%}" for lab, _, _ in LVL) + ") ===")
    print(f"  {'band':<14}{'N':>4} {'%日':>5}  " +
          "  ".join(f"{lab}({nm})" for lab, _, nm in LVL))
    for thr in (0.2, 0.3, 0.4, 0.5):
        m = (score >= thr) if side == "long" else (score <= -thr)
        sub = df[m]
        lab = f"{'≥+' if side=='long' else '≤−'}{thr:.1f}"
        if len(sub) == 0:
            print(f"  {lab:<14}{0:>4}    —   (無樣本)")
            continue
        cells = []
        for L, _, _ in LVL:
            p = sub[f"{pre}_{L}"].mean()
            lift = p - base[L]
            cells.append(f"{p:4.0%}({lift:+.0%})")
        print(f"  {lab:<14}{len(sub):>4} {len(sub)/len(df):4.0%}  " + "  ".join(cells))


def run(df: pd.DataFrame, tag: str):
    print("\n" + "=" * 78)
    print(f"  {tag}   N={len(df)}   {df.index.min().date()} ~ {df.index.max().date()}")
    print("=" * 78)
    hist(df["dci_long"], f"{tag} dci_long（多方）")
    hist(df["dci_short"], f"{tag} dci_short（空方）")
    band_table(df, "long")
    band_table(df, "short")


def main():
    reach = daily_reach()
    flags = reach_flags(reach)
    dci = daily_dci()
    df = dci.join(flags, how="inner").dropna()

    full = df
    y26 = df[df.index.year == 2026]
    run(y26, "2026")
    run(full, "全樣本(參考基準)")


if __name__ == "__main__":
    main()

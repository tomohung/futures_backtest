"""H090 Phase 1: 漲停熱絡持續 (lu_value_ratio_ma7) 作為 0050 動量延續訊號 — 分佈探索。

對 lu_value_ratio_ma7 取多個 (threshold × consecutive) 組合作為 trigger，量測：
  - 觸發次數、cluster 數（gap >5d）
  - 與 H085 panic days Jaccard
  - +60/120/250d 0050 含息 forward return vs monthly DCA baseline
  - macro_tier 分佈
  - 拿掉 bull regime 後 lift 是否仍存在

GATE：
  - ≥1 變體 +60d 或 +120d median > DCA + 2%
  - 該變體 cluster 8-30
  - Jaccard vs H085 < 0.3
  - macro_tier != 'bull' 子樣本下仍 lift > +1%
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent.parent
DB = ROOT / "data" / "futures.duckdb"
CACHE_0050 = ROOT / "data" / "external_sources" / "0050_TW_adj.csv"
H084 = ROOT / "research" / "active" / "H084-correction-bottom-survey"
H087 = ROOT / "research" / "active" / "H087-margin-breadth-augment"
H090 = Path(__file__).parent
RESULTS = H090 / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


# H085 4 軸 fear composite，重算 panic days
H085_INDICATORS = [
    ("vix_pct",             +1),
    ("taiex_dist_125ma_z",  -1),
    ("margin_drop_60d_pct", -1),
    ("econ_score",          -1),
]


def cluster_count(dates: pd.Series, gap_days: int = 5) -> int:
    if len(dates) == 0:
        return 0
    td = pd.to_datetime(sorted(dates))
    if len(td) == 1:
        return 1
    gaps = (td[1:] - td[:-1]).days
    return 1 + int((gaps > gap_days).sum())


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def z_score(series: pd.Series, sign: int) -> pd.Series:
    med = series.median()
    iqr = series.quantile(0.75) - series.quantile(0.25)
    if iqr == 0:
        iqr = 1.0
    return sign * (series - med) / iqr


def consec_mask(condition: pd.Series, k: int) -> pd.Series:
    """Returns True on each day where condition has been True for >=k consecutive days."""
    if k <= 1:
        return condition
    # rolling sum 為 k 表示連續 k 天都 True
    return condition.rolling(window=k, min_periods=k).sum() >= k


def load_data() -> pd.DataFrame:
    with duckdb.connect(str(DB), read_only=True) as c:
        lim = c.execute("""
            SELECT trade_date,
                   COUNT(*) FILTER (WHERE is_limit_up) AS lu_count,
                   COALESCE(SUM(value) FILTER (WHERE is_limit_up), 0) AS lu_value,
                   SUM(value) AS total_value
            FROM stock_day GROUP BY trade_date ORDER BY trade_date
        """).fetchdf()
    lim["trade_date"] = pd.to_datetime(lim["trade_date"]).dt.date
    lim["lu_value_ratio"] = lim["lu_value"] / lim["total_value"]
    lim["lu_value_ratio_ma7"] = lim["lu_value_ratio"].rolling(7).mean()

    # 0050
    p = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
    p["trade_date"] = p["trade_date"].dt.date
    p = p.sort_values("trade_date").reset_index(drop=True)
    for n in (60, 120, 250):
        p[f"fwd_{n}d"] = p["adj_close"].shift(-n) / p["adj_close"] - 1.0

    df = lim.merge(p[["trade_date", "adj_close", "fwd_60d", "fwd_120d", "fwd_250d"]],
                   on="trade_date", how="inner")

    # macro_tier
    fuse = pd.read_csv(H084 / "results" / "fuse_state.csv", parse_dates=["trade_date"])
    fuse["trade_date"] = fuse["trade_date"].dt.date
    df = df.merge(fuse[["trade_date", "macro_tier"]], on="trade_date", how="left")

    # H084 indicators 用來算 H085 panic days
    h084_ind = pd.read_csv(H084 / "results" / "indicators.csv", parse_dates=["trade_date"])
    h084_ind["trade_date"] = h084_ind["trade_date"].dt.date
    h084_cols = [c for c, _ in H085_INDICATORS]
    df = df.merge(h084_ind[["trade_date"] + h084_cols], on="trade_date", how="left")
    return df


def compute_h085_triggers(df: pd.DataFrame) -> set:
    cols = [c for c, _ in H085_INDICATORS]
    valid = df.dropna(subset=cols)
    z_sum = sum(z_score(valid[c], s) for c, s in H085_INDICATORS)
    thresh = z_sum.quantile(0.90)
    return set(valid.loc[z_sum >= thresh, "trade_date"])


def monthly_dca_baseline(df: pd.DataFrame) -> dict[int, float]:
    p = df.dropna(subset=["adj_close"]).copy()
    p["yyyymm"] = pd.to_datetime(p["trade_date"]).dt.to_period("M")
    last = p.groupby("yyyymm").tail(1)
    return {n: last[f"fwd_{n}d"].dropna().median() for n in (60, 120, 250)}


def evaluate(df: pd.DataFrame, top_q: float, consec: int,
             h085: set, dca: dict[int, float]) -> dict:
    """top_q = 0.10 表示 lu_value_ratio_ma7 top 10%"""
    valid = df.dropna(subset=["lu_value_ratio_ma7"])
    thresh = valid["lu_value_ratio_ma7"].quantile(1 - top_q)
    cond = valid["lu_value_ratio_ma7"] >= thresh
    mask = consec_mask(cond, consec).fillna(False)
    trig = valid[mask]

    fwd = {}
    for n in (60, 120, 250):
        vals = trig[f"fwd_{n}d"].dropna()
        fwd[n] = {
            "n": len(vals),
            "median": vals.median() if len(vals) else None,
            "mean": vals.mean() if len(vals) else None,
            "lift": (vals.median() - dca[n]) if (len(vals) and dca[n] is not None) else None,
        }

    tier_dist = trig["macro_tier"].fillna("?").value_counts().to_dict()

    # macro_tier != 'bull' 子樣本
    non_bull = trig[trig["macro_tier"] != "bull"]
    fwd_nb = {}
    for n in (60, 120, 250):
        vals = non_bull[f"fwd_{n}d"].dropna()
        fwd_nb[n] = {
            "n": len(vals),
            "median": vals.median() if len(vals) else None,
            "lift": (vals.median() - dca[n]) if (len(vals) and dca[n] is not None) else None,
        }

    trig_dates = set(trig["trade_date"])

    return {
        "top_q": top_q,
        "consec": consec,
        "threshold": float(thresh),
        "n_triggers": len(trig),
        "n_clusters": cluster_count(trig["trade_date"]),
        "jaccard_h085": jaccard(trig_dates, h085),
        "tier_dist": tier_dist,
        "fwd_60d_n": fwd[60]["n"],
        "fwd_60d_med": fwd[60]["median"],
        "fwd_60d_lift": fwd[60]["lift"],
        "fwd_120d_n": fwd[120]["n"],
        "fwd_120d_med": fwd[120]["median"],
        "fwd_120d_lift": fwd[120]["lift"],
        "fwd_250d_n": fwd[250]["n"],
        "fwd_250d_med": fwd[250]["median"],
        "fwd_250d_lift": fwd[250]["lift"],
        # non-bull
        "nb_60d_n": fwd_nb[60]["n"],
        "nb_60d_lift": fwd_nb[60]["lift"],
        "nb_120d_n": fwd_nb[120]["n"],
        "nb_120d_lift": fwd_nb[120]["lift"],
        "nb_250d_n": fwd_nb[250]["n"],
        "nb_250d_lift": fwd_nb[250]["lift"],
    }


def fmt_pct(x):
    if x is None or pd.isna(x):
        return "—"
    return f"{x*100:+.2f}%"


def main() -> None:
    df = load_data()
    print(f"Sample: {df['trade_date'].min()} ~ {df['trade_date'].max()}, N={len(df)}")
    valid_ma7 = df.dropna(subset=["lu_value_ratio_ma7"])
    print(f"  with ma7: N={len(valid_ma7)}")

    dca = monthly_dca_baseline(df)
    print(f"\nDCA baseline (monthly): " + ", ".join(
        f"+{n}d med={fmt_pct(v)}" for n, v in dca.items()))

    h085 = compute_h085_triggers(df)
    print(f"H085 panic days: N={len(h085)}, clusters={cluster_count(pd.Series(list(h085)))}")

    # Grid
    rows = []
    for top_q in (0.05, 0.10, 0.15, 0.20):
        for consec in (1, 3, 5):
            r = evaluate(df, top_q, consec, h085, dca)
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(RESULTS / "trigger_grid.csv", index=False)

    print("\n=== Trigger grid (full sample) ===")
    cols = ["top_q", "consec", "threshold", "n_triggers", "n_clusters", "jaccard_h085",
            "fwd_60d_med", "fwd_60d_lift", "fwd_120d_med", "fwd_120d_lift",
            "fwd_250d_med", "fwd_250d_lift"]
    disp = res[cols].copy()
    disp["top_q"] = (disp["top_q"] * 100).astype(int).astype(str) + "%"
    disp["threshold"] = disp["threshold"].apply(lambda x: f"{x*100:.2f}%")
    disp["jaccard_h085"] = disp["jaccard_h085"].apply(lambda x: f"{x:.2f}")
    for c in ("fwd_60d_med", "fwd_60d_lift", "fwd_120d_med", "fwd_120d_lift",
              "fwd_250d_med", "fwd_250d_lift"):
        disp[c] = disp[c].apply(fmt_pct)
    print(disp.to_string(index=False))

    print("\n=== Non-bull subsample (macro_tier != 'bull') ===")
    cols_nb = ["top_q", "consec", "nb_60d_n", "nb_60d_lift",
               "nb_120d_n", "nb_120d_lift", "nb_250d_n", "nb_250d_lift"]
    disp_nb = res[cols_nb].copy()
    disp_nb["top_q"] = (disp_nb["top_q"] * 100).astype(int).astype(str) + "%"
    for c in ("nb_60d_lift", "nb_120d_lift", "nb_250d_lift"):
        disp_nb[c] = disp_nb[c].apply(fmt_pct)
    print(disp_nb.to_string(index=False))

    print("\n=== Macro tier breakdown per variant ===")
    for _, r in res.iterrows():
        if r["n_triggers"] > 0:
            print(f"  top {int(r['top_q']*100)}% consec={r['consec']}: {r['tier_dist']}")

    # GATE check
    print("\n" + "=" * 60)
    print("GATE check")
    print("=" * 60)
    best = res.loc[res["fwd_120d_lift"].fillna(-1).idxmax()]
    print(f"\nBest +120d lift: top {int(best['top_q']*100)}% consec={best['consec']}")
    print(f"  triggers={best['n_triggers']}, clusters={best['n_clusters']}, jaccard={best['jaccard_h085']:.2f}")
    print(f"  +60d  med={fmt_pct(best['fwd_60d_med'])}, lift={fmt_pct(best['fwd_60d_lift'])}")
    print(f"  +120d med={fmt_pct(best['fwd_120d_med'])}, lift={fmt_pct(best['fwd_120d_lift'])}")
    print(f"  +250d med={fmt_pct(best['fwd_250d_med'])}, lift={fmt_pct(best['fwd_250d_lift'])}")
    print(f"  non-bull +120d N={best['nb_120d_n']}, lift={fmt_pct(best['nb_120d_lift'])}")

    pass_lift = ((best["fwd_60d_lift"] or -1) >= 0.02 or (best["fwd_120d_lift"] or -1) >= 0.02)
    pass_cluster = 8 <= best["n_clusters"] <= 30
    pass_jaccard = best["jaccard_h085"] < 0.3
    pass_nb = (best["nb_120d_n"] >= 6 and (best["nb_120d_lift"] or -1) >= 0.01)

    print(f"\nGATE conditions (best variant):")
    print(f"  [{'✓' if pass_lift else '✗'}] +60d OR +120d lift ≥ +2%")
    print(f"  [{'✓' if pass_cluster else '✗'}] cluster 8-30 ({best['n_clusters']})")
    print(f"  [{'✓' if pass_jaccard else '✗'}] jaccard < 0.3 ({best['jaccard_h085']:.2f})")
    print(f"  [{'✓' if pass_nb else '✗'}] non-bull lift > +1%")


if __name__ == "__main__":
    main()

"""H089 Phase 1: 廣度指標單獨作為 Tier C 進場 trigger — 分佈探索。

對每個廣度指標獨立取 top 5/10% 觸發日，量測：
  - cluster 數（gap > 5d）
  - 與 H085 panic days (comp_z_4 top 10%) 的 Jaccard
  - +60/120/250d 0050 含息 forward return 中位數
  - 對比 monthly DCA baseline
  - 「H085-excluded」變體（只看廣度極值但 H085 未觸發的日子）
  - 命中事件：對應 tiers.csv 中哪幾個 Tier B/C trough

GATE：
  - ≥1 trigger 的 +120d OR +250d median > DCA + 5%
  - cluster 6 ~ 50
  - Jaccard vs H085 < 0.5
  - H085-excluded 變體下仍 N≥6 + median > DCA + 5%
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent.parent
H084 = ROOT / "research" / "active" / "H084-correction-bottom-survey"
H085 = ROOT / "research" / "archive" / "confirmed" / "H085-fg-composite"
H087 = ROOT / "research" / "active" / "H087-margin-breadth-augment"
H089 = Path(__file__).parent
RESULTS = H089 / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

CACHE_0050 = ROOT / "data" / "external_sources" / "0050_TW_adj.csv"

# 廣度指標：(欄名, 極值方向, 顯示名)
# fear-direction: 'low' = 越低越 fear; 'high' = 越高越 fear
BREADTH = [
    ("breadth_adv_dec",   "low",  "adv/dec"),
    ("new_lows_52w",      "high", "new lows 52w"),
    ("new_high_low_diff", "low",  "high-low diff"),
    ("new_highs_52w",     "low",  "new highs 52w"),
]

# H085 4 軸（同 H087 extend_composite）
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


def load_data() -> pd.DataFrame:
    h084_ind = pd.read_csv(H084 / "results" / "indicators.csv", parse_dates=["trade_date"])
    h087_brd = pd.read_csv(H087 / "results" / "breadth_indicators.csv", parse_dates=["trade_date"])
    fuse = pd.read_csv(H084 / "results" / "fuse_state.csv", parse_dates=["trade_date"])
    df = h084_ind.merge(h087_brd, on="trade_date", how="left").merge(
        fuse[["trade_date", "macro_tier"]], on="trade_date", how="left"
    )
    df["trade_date"] = df["trade_date"].dt.date

    # 0050
    p = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
    p["trade_date"] = p["trade_date"].dt.date
    p = p.sort_values("trade_date").reset_index(drop=True)
    for n in (60, 120, 250):
        p[f"fwd_{n}d"] = p["adj_close"].shift(-n) / p["adj_close"] - 1.0
    df = df.merge(p[["trade_date", "adj_close", "fwd_60d", "fwd_120d", "fwd_250d"]],
                  on="trade_date", how="inner")
    return df


def monthly_dca_baseline(df: pd.DataFrame) -> dict[int, float]:
    p = df.copy()
    p["yyyymm"] = pd.to_datetime(p["trade_date"]).dt.to_period("M")
    last = p.groupby("yyyymm").tail(1)
    return {n: last[f"fwd_{n}d"].dropna().median() for n in (60, 120, 250)}


def compute_h085_triggers(df: pd.DataFrame) -> set:
    """H085 comp_z_4 top 10% trigger dates (4-axis fear composite)"""
    valid = df.dropna(subset=[c for c, _ in H085_INDICATORS])
    z_sum = sum(z_score(valid[c], s) for c, s in H085_INDICATORS)
    thresh = z_sum.quantile(0.90)
    return set(valid.loc[z_sum >= thresh, "trade_date"])


def evaluate_single_trigger(df: pd.DataFrame, col: str, direction: str,
                             q: float, h085_dates: set,
                             dca_base: dict[int, float]) -> dict:
    """單一指標 + threshold 變體的所有 metrics."""
    valid = df.dropna(subset=[col])
    if direction == "low":
        # 'top q%' = 最低 q% 的值
        thresh = valid[col].quantile(q)
        mask = valid[col] <= thresh
    else:
        # 'top q%' = 最高 q% 的值
        thresh = valid[col].quantile(1 - q)
        mask = valid[col] >= thresh
    sub = valid[mask]

    trig_dates = set(sub["trade_date"])
    clusters = cluster_count(sub["trade_date"])
    j = jaccard(trig_dates, h085_dates)

    # Forward returns
    fwd = {}
    for n in (60, 120, 250):
        vals = sub[f"fwd_{n}d"].dropna()
        fwd[n] = {
            "n": len(vals),
            "median": vals.median() if len(vals) else None,
            "lift": (vals.median() - dca_base[n]) if (len(vals) and dca_base[n] is not None) else None,
        }

    # Tier breakdown
    tier_dist = sub["macro_tier"].fillna("?").value_counts().to_dict()

    # H085-excluded subset
    excl = sub[~sub["trade_date"].isin(h085_dates)]
    fwd_excl = {}
    for n in (60, 120, 250):
        vals = excl[f"fwd_{n}d"].dropna()
        fwd_excl[n] = {
            "n": len(vals),
            "median": vals.median() if len(vals) else None,
            "lift": (vals.median() - dca_base[n]) if (len(vals) and dca_base[n] is not None) else None,
        }

    return {
        "indicator": col,
        "direction": direction,
        "quantile": f"top {round(q*100)}%",
        "threshold": float(thresh),
        "n_triggers": len(sub),
        "n_clusters": clusters,
        "jaccard_h085": j,
        "tier_dist": tier_dist,
        "fwd_60d_med": fwd[60]["median"],
        "fwd_60d_lift": fwd[60]["lift"],
        "fwd_120d_n": fwd[120]["n"],
        "fwd_120d_med": fwd[120]["median"],
        "fwd_120d_lift": fwd[120]["lift"],
        "fwd_250d_n": fwd[250]["n"],
        "fwd_250d_med": fwd[250]["median"],
        "fwd_250d_lift": fwd[250]["lift"],
        # H085-excluded
        "excl_120d_n": fwd_excl[120]["n"],
        "excl_120d_med": fwd_excl[120]["median"],
        "excl_120d_lift": fwd_excl[120]["lift"],
        "excl_250d_n": fwd_excl[250]["n"],
        "excl_250d_med": fwd_excl[250]["median"],
        "excl_250d_lift": fwd_excl[250]["lift"],
    }


def fmt_pct(x):
    if x is None or pd.isna(x):
        return "—"
    return f"{x*100:+.2f}%"


def main() -> None:
    df = load_data()
    print(f"Sample: {df['trade_date'].min()} ~ {df['trade_date'].max()}, N={len(df)}")

    # DCA baseline
    dca = monthly_dca_baseline(df)
    print(f"\nDCA baseline (monthly): " + ", ".join(
        f"+{n}d med={fmt_pct(v)}" for n, v in dca.items()))

    h085_dates = compute_h085_triggers(df)
    print(f"H085 panic days (comp_z_4 top 10%): N={len(h085_dates)}, "
          f"clusters={cluster_count(pd.Series(list(h085_dates)))}")

    # Evaluate single-indicator triggers
    results = []
    for col, direction, label in BREADTH:
        for q in (0.05, 0.10):
            r = evaluate_single_trigger(df, col, direction, q, h085_dates, dca)
            r["label"] = label
            results.append(r)
    res_df = pd.DataFrame(results)

    # Save raw
    res_df.to_csv(RESULTS / "single_triggers.csv", index=False)

    # Print compact comparison
    print("\n=== Single-indicator triggers (full sample) ===")
    cols_to_show = ["label", "quantile", "n_triggers", "n_clusters", "jaccard_h085",
                    "fwd_120d_n", "fwd_120d_med", "fwd_120d_lift",
                    "fwd_250d_n", "fwd_250d_med", "fwd_250d_lift"]
    display = res_df[cols_to_show].copy()
    for c in ["fwd_120d_med", "fwd_120d_lift", "fwd_250d_med", "fwd_250d_lift", "jaccard_h085"]:
        if c == "jaccard_h085":
            display[c] = display[c].apply(lambda x: f"{x:.2f}")
        else:
            display[c] = display[c].apply(fmt_pct)
    print(display.to_string(index=False))

    print("\n=== H085-EXCLUDED subset (only-breadth events) ===")
    cols_excl = ["label", "quantile", "excl_120d_n", "excl_120d_med", "excl_120d_lift",
                 "excl_250d_n", "excl_250d_med", "excl_250d_lift"]
    display_excl = res_df[cols_excl].copy()
    for c in ["excl_120d_med", "excl_120d_lift", "excl_250d_med", "excl_250d_lift"]:
        display_excl[c] = display_excl[c].apply(fmt_pct)
    print(display_excl.to_string(index=False))

    print("\n=== Macro tier breakdown per trigger (full sample) ===")
    for _, r in res_df.iterrows():
        print(f"  {r['label']:20s} {r['quantile']:8s}: {r['tier_dist']}")

    # GATE check
    print("\n" + "=" * 60)
    print("GATE check")
    print("=" * 60)
    gate_msg = []
    # Find best by lift
    best = res_df.iloc[res_df["fwd_120d_lift"].fillna(-1).idxmax()]
    print(f"\nBest +120d lift: {best['label']} {best['quantile']}")
    print(f"  n_clusters={best['n_clusters']}, jaccard={best['jaccard_h085']:.2f}")
    print(f"  +120d lift vs DCA: {fmt_pct(best['fwd_120d_lift'])} "
          f"(need ≥ +5%)")
    print(f"  +250d lift vs DCA: {fmt_pct(best['fwd_250d_lift'])}")
    print(f"  H085-excluded +120d: N={best['excl_120d_n']}, "
          f"lift={fmt_pct(best['excl_120d_lift'])}")

    pass_120 = (best["fwd_120d_lift"] is not None and best["fwd_120d_lift"] >= 0.05)
    pass_250 = (best["fwd_250d_lift"] is not None and best["fwd_250d_lift"] >= 0.05)
    pass_cluster = 6 <= best["n_clusters"] <= 50
    pass_jaccard = best["jaccard_h085"] < 0.5
    pass_excl = (best["excl_120d_n"] >= 6 and
                 best["excl_120d_lift"] is not None and
                 best["excl_120d_lift"] >= 0.05)

    print(f"\nGATE conditions:")
    print(f"  [{'✓' if (pass_120 or pass_250) else '✗'}] lift ≥ +5% (120d or 250d)")
    print(f"  [{'✓' if pass_cluster else '✗'}] cluster 6 ~ 50 ({best['n_clusters']})")
    print(f"  [{'✓' if pass_jaccard else '✗'}] jaccard < 0.5 ({best['jaccard_h085']:.2f})")
    print(f"  [{'✓' if pass_excl else '✗'}] H085-excluded N≥6 + lift ≥ +5%")


if __name__ == "__main__":
    main()

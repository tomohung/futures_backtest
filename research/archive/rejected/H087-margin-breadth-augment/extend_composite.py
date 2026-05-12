"""H087 Phase 1.3: 把 3 個通過 GATE 的廣度指標加進 H085 composite，比較 forward-return。

對照組：
  - comp_z_4   = H085 原版：vix_pct + (-z 125MA) + (-margin_drop_60d) + (-econ_score)
  - comp_z_4+1 = +adv/dec (low方向)
  - comp_z_4+2 = +adv/dec + new lows 52w
  - comp_z_4+3 = +adv/dec + new lows 52w + high-low diff

forward returns 用 0050 含息 (H085 cache)。

注意：本實驗用 full-sample IQR 標準化（同 H085 explore），有 lookahead bias，
僅用於「廣度補強是否方向正確」的快速 sanity check。
若 sanity check 通過再做 rolling IQR walk-forward。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

H084 = Path(__file__).parent.parent / "H084-correction-bottom-survey"
H085 = Path(__file__).parent.parent.parent / "archive" / "confirmed" / "H085-fg-composite"
H087 = Path(__file__).parent
RESULTS = H087 / "results"

# 通過 GATE 的廣度指標（hit ≥60% + max|r|<0.6 vs H084 4 軸）
BREADTH_TO_ADD = [
    # (col, sign, label)  sign: +1 high→fear, -1 low→fear
    ("breadth_adv_dec",     -1, "adv/dec"),         # low 比值 = 跌家多 = fear
    ("new_lows_52w",        +1, "new lows 52w"),    # high 新低家數 = fear
    ("new_high_low_diff",   -1, "high-low diff"),   # low (negative) = fear
]

H084_4 = [
    ("vix_pct",             +1, "VIX_pct"),
    ("taiex_dist_125ma_z",  -1, "z 125MA"),
    ("margin_drop_60d_pct", -1, "margin_drop_60d"),
    ("econ_score",          -1, "econ_score"),
]


def z_score(series: pd.Series, sign: int) -> pd.Series:
    """sign-aligned (x - median) / IQR；higher = more fear after sign-flip"""
    med = series.median()
    iqr = series.quantile(0.75) - series.quantile(0.25)
    if iqr == 0:
        iqr = 1.0
    return sign * (series - med) / iqr


def load_data() -> pd.DataFrame:
    h084_ind = pd.read_csv(H084 / "results" / "indicators.csv", parse_dates=["trade_date"])
    h087_brd = pd.read_csv(H087 / "results" / "breadth_indicators.csv", parse_dates=["trade_date"])
    df = h084_ind.merge(h087_brd, on="trade_date", how="left")
    df["trade_date"] = df["trade_date"].dt.date

    # 0050 含息（沿用 H085 cache）
    cache = H087.parent.parent.parent / "data" / "external_sources" / "0050_TW_adj.csv"
    p = pd.read_csv(cache, parse_dates=["trade_date"])
    p["trade_date"] = p["trade_date"].dt.date
    p = p.sort_values("trade_date").reset_index(drop=True)
    for n in (60, 120, 250):
        p[f"fwd_{n}d"] = p["adj_close"].shift(-n) / p["adj_close"] - 1.0
    df = df.merge(p[["trade_date", "adj_close", "fwd_60d", "fwd_120d", "fwd_250d"]],
                  on="trade_date", how="inner")
    return df


def build_composites(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    z_h084 = pd.concat([z_score(out[c], s) for c, s, _ in H084_4], axis=1)
    out["comp_z_4"] = z_h084.sum(axis=1)

    z_brd = [z_score(out[c], s) for c, s, _ in BREADTH_TO_ADD]
    out["comp_z_4p1"] = out["comp_z_4"] + z_brd[0]
    out["comp_z_4p2"] = out["comp_z_4"] + z_brd[0] + z_brd[1]
    out["comp_z_4p3"] = out["comp_z_4"] + z_brd[0] + z_brd[1] + z_brd[2]

    # 4 軸齊全且廣度齊全的範圍
    h084_cols = [c for c, _, _ in H084_4]
    brd_cols = [c for c, _, _ in BREADTH_TO_ADD]
    out["all_axes_ok"] = out[h084_cols + brd_cols].notna().all(axis=1)
    return out


def evaluate_composite(df: pd.DataFrame, score_col: str, q_list=(0.80, 0.90, 0.95)) -> pd.DataFrame:
    """Top-q quantile triggers — 算 forward returns 中位數、平均、勝率"""
    valid = df[df["all_axes_ok"] & df["fwd_120d"].notna()]
    baseline_med = {n: valid[f"fwd_{n}d"].median() for n in (60, 120, 250)}
    rows = []
    for q in q_list:
        thresh = valid[score_col].quantile(q)
        sub = valid[valid[score_col] >= thresh]
        for n in (60, 120, 250):
            r = sub[f"fwd_{n}d"].dropna()
            rows.append({
                "score": score_col,
                "quantile": f"top {round((1-q)*100)}%",
                "threshold": round(float(thresh), 2),
                "horizon": f"+{n}d",
                "n": len(r),
                "median": r.median(),
                "mean": r.mean(),
                "win_rate_vs_base": (r > baseline_med[n]).mean() if len(r) else None,
                "lift_vs_base": (r.median() - baseline_med[n]) if len(r) else None,
            })
    return pd.DataFrame(rows)


def cluster_triggers(dates: pd.Series, gap_days: int = 5) -> int:
    if len(dates) == 0:
        return 0
    td = pd.to_datetime(sorted(dates))
    if len(td) == 1:
        return 1
    gaps = (td[1:] - td[:-1]).days
    return 1 + int((gaps > gap_days).sum())


def main() -> None:
    df = load_data()
    df = build_composites(df)
    valid = df[df["all_axes_ok"]]
    print(f"Sample range: {valid['trade_date'].min()} ~ {valid['trade_date'].max()}  N={len(valid)}")
    print(f"  forward-return-evaluable (fwd_120d not null): N={valid['fwd_120d'].notna().sum()}")

    # Evaluate 4 versions
    all_rows = []
    for score in ["comp_z_4", "comp_z_4p1", "comp_z_4p2", "comp_z_4p3"]:
        res = evaluate_composite(df, score)
        all_rows.append(res)
    summary = pd.concat(all_rows, ignore_index=True)
    summary.to_csv(RESULTS / "composite_comparison.csv", index=False)

    # Print top-10% (q=0.90) compactly
    print("\n=== Top 10% trigger forward returns (4-axis vs +breadth) ===")
    top10 = summary[summary["quantile"] == "top 10%"].copy()
    for h in ("+60d", "+120d", "+250d"):
        sub = top10[top10["horizon"] == h].copy()
        for col in ("median", "mean", "win_rate_vs_base", "lift_vs_base"):
            sub[col] = sub[col].apply(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "—")
        print(f"\n--- horizon {h} ---")
        print(sub[["score", "threshold", "n", "median", "mean", "win_rate_vs_base", "lift_vs_base"]]
              .to_string(index=False))

    # Also cluster counts at top 10%
    print("\n=== Trigger clusters at top 10% (gap > 5 trading days) ===")
    for score in ["comp_z_4", "comp_z_4p1", "comp_z_4p2", "comp_z_4p3"]:
        thresh = valid[score].quantile(0.90)
        sub = valid[valid[score] >= thresh]
        n_trigs = len(sub)
        n_clusters = cluster_triggers(sub["trade_date"])
        print(f"  {score}: threshold={thresh:+.2f}, triggers={n_trigs}, clusters={n_clusters}")

    # Same threshold across versions: hold 4-axis threshold (3.97 from H085), see what extended composite returns at the same top-10% trigger DAYS
    print("\n=== H085 panic events: do extra breadth axes ALIGN at those same dates? ===")
    th4 = valid["comp_z_4"].quantile(0.90)
    h085_panic = valid[valid["comp_z_4"] >= th4].sort_values("trade_date")
    cols = ["trade_date", "macro_tier", "comp_z_4", "comp_z_4p1", "comp_z_4p2", "comp_z_4p3",
            "fwd_120d", "fwd_250d"]
    cols = [c for c in cols if c in h085_panic.columns]
    print(h085_panic[cols].to_string(index=False, float_format=lambda x: f"{x:+.2f}"))


if __name__ == "__main__":
    main()

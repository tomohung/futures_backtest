"""H080 Phase 1 Explore — 前 20 權值股集中度的行情分類

從 concentration_index 取 4 個 N 的指標，join TX 日盤 OHLC，跑 1A–1G 各分析。

子假設（GATE 主訊號 = N=20）:
  A) 5 桶 quintile 漲日機率單調且首尾 ≥ 8pp
  B) 5 桶 quintile 平均振幅單調且首尾 ≥ 30%
  C) 27 格中 ≥ 2 格 lift ≥ 80% 且 chi-square p < 0.05
  D) 某 3 桶大跌機率相對 baseline lift ≥ 50%

用法:
  uv run python research/active/H080-top20-concentration-regime/explore.py
  uv run python research/active/H080-top20-concentration-regime/explore.py --start 2018-01-01 --end 2026-05-07
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULT_DIR = Path(__file__).parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

N_VALUES = [1, 5, 10, 20]


DAILY_SQL = """
WITH ci AS (
    SELECT * FROM concentration_index
    WHERE trade_date BETWEEN ? AND ?
),
tx AS (
    SELECT timestamp::DATE AS trade_date,
           FIRST(open  ORDER BY timestamp) AS tx_open,
           LAST(close  ORDER BY timestamp) AS tx_close,
           MAX(high)                       AS tx_high,
           MIN(low)                        AS tx_low
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::DATE BETWEEN ? AND ?
      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
    GROUP BY trade_date
)
SELECT ci.*, tx.tx_open, tx.tx_close, tx.tx_high, tx.tx_low
FROM ci
JOIN tx USING (trade_date)
ORDER BY ci.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end]).fetchdf()
    df["tx_dir"] = (df["tx_close"] - df["tx_open"]) / df["tx_open"]
    df["tx_range"] = (df["tx_high"] - df["tx_low"]) / df["tx_open"]
    df["weekday"] = pd.to_datetime(df["trade_date"]).dt.weekday  # 0=Mon
    return df


def analyze_distribution(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1A) 分佈總覽")
    print("=" * 78)
    cols = [f"top{n}_share" for n in N_VALUES] + [f"top{n}_dev_pct" for n in N_VALUES]
    desc = df[cols].describe().T[["mean", "std", "min", "50%", "max"]]
    print(desc.to_string())
    n_changed = df.groupby("list_month")["list_changed"].first().sum()
    n_total = df["list_month"].nunique()
    print(f"\nlist_changed 月份數: {n_changed} / {n_total}")

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    for i, n in enumerate(N_VALUES):
        axes[0, i].hist(df[f"top{n}_share"].dropna(), bins=50, color="steelblue", edgecolor="white")
        axes[0, i].set_title(f"N={n} share %")
        axes[1, i].hist(df[f"top{n}_dev_pct"].dropna(), bins=50, color="darkorange", edgecolor="white")
        axes[1, i].set_title(f"N={n} dev_pct %")
        axes[1, i].axvline(0, color="black", lw=0.5)
    fig.tight_layout()
    fig.savefig(RESULT_DIR / "distribution_overview.png", dpi=120)
    plt.close(fig)
    print(f"已輸出: {RESULT_DIR / 'distribution_overview.png'}")


def analyze_quintile_by_N(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1B) 5 桶 quintile 邊際分析（4 個 N）")
    print("=" * 78)

    rows = []
    for n in N_VALUES:
        sig = df[f"top{n}_dev_pct"]
        df[f"q{n}"] = pd.qcut(sig, 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
        for q in [1, 2, 3, 4, 5]:
            mask = df[f"q{n}"] == q
            sub = df[mask]
            if len(sub) == 0:
                continue
            rows.append({
                "N": n, "quintile": q, "n": len(sub),
                "share_mean": sub[f"top{n}_share"].mean(),
                "dev_pct_mean": sub[f"top{n}_dev_pct"].mean(),
                "tx_dir_mean": sub["tx_dir"].mean(),
                "tx_range_mean": sub["tx_range"].mean(),
                "p_up": (sub["tx_dir"] > 0).mean(),
                "p_down": (sub["tx_dir"] < 0).mean(),
            })
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "A_quintile_by_N.csv", index=False)
    print(res.to_string(index=False))

    print("\n--- GATE 評估 (主訊號 N=20) ---")
    for n in N_VALUES:
        sub = res[res["N"] == n].sort_values("quintile")
        if len(sub) < 5:
            continue
        pp_diff = (sub["p_up"].iloc[-1] - sub["p_up"].iloc[0]) * 100
        range_diff = (sub["tx_range_mean"].iloc[-1] / sub["tx_range_mean"].iloc[0] - 1) * 100
        mono_up = sub["p_up"].is_monotonic_increasing or sub["p_up"].is_monotonic_decreasing
        mono_range = sub["tx_range_mean"].is_monotonic_increasing or sub["tx_range_mean"].is_monotonic_decreasing
        gate1 = abs(pp_diff) >= 8 and mono_up
        gate2 = abs(range_diff) >= 30 and mono_range
        marker = " <- GATE" if n == 20 else ""
        print(f"N={n:>2}: p_up Q5-Q1 = {pp_diff:+6.2f}pp  mono={mono_up}  GATE-1={gate1}{marker}")
        print(f"      range Q5/Q1-1 = {range_diff:+6.1f}%   mono={mono_range}  GATE-2={gate2}{marker}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for n in N_VALUES:
        sub = res[res["N"] == n].sort_values("quintile")
        axes[0].plot(sub["quintile"], sub["p_up"] * 100, marker="o", label=f"N={n}")
        axes[1].plot(sub["quintile"], sub["tx_range_mean"] * 100, marker="o", label=f"N={n}")
    axes[0].set_title("漲日機率 vs quintile (4 個 N)")
    axes[0].set_xlabel("quintile (1=低集中度, 5=高)")
    axes[0].set_ylabel("p_up %")
    axes[0].axhline(50, color="gray", lw=0.5, linestyle="--")
    axes[0].legend()
    axes[1].set_title("平均振幅 vs quintile (4 個 N)")
    axes[1].set_xlabel("quintile")
    axes[1].set_ylabel("range %")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(RESULT_DIR / "A_quintile_by_N.png", dpi=120)
    plt.close(fig)
    print(f"\n已輸出: {RESULT_DIR / 'A_quintile_by_N.png'}")


def analyze_27grid(df: pd.DataFrame, n: int = 20) -> None:
    print("=" * 78)
    print(f"1C) 27 格主分析 (N={n})")
    print("=" * 78)
    work = df.dropna(subset=[f"top{n}_dev_pct", "tx_dir", "tx_range"]).copy()

    work["c_bucket"] = pd.qcut(work[f"top{n}_dev_pct"], 3, labels=["c_low", "c_mid", "c_high"])
    work["d_bucket"] = pd.cut(
        work["tx_dir"], bins=[-np.inf, -0.003, 0.003, np.inf],
        labels=["dn", "flat", "up"]
    )
    work["r_bucket"] = pd.qcut(work["tx_range"], 3, labels=["sm", "md", "lg"])
    work["regime"] = work["d_bucket"].astype(str) + "_" + work["r_bucket"].astype(str)

    counts = work.groupby(["c_bucket", "regime"], observed=True).size().unstack(fill_value=0)
    baseline = work["regime"].value_counts(normalize=True)
    cond_prob = counts.div(counts.sum(axis=1), axis=0)
    lift = cond_prob.div(baseline, axis=1)

    print("\n樣本數 (橫列：集中度桶, 縱欄：行情格):")
    print(counts.to_string())
    print("\n條件機率 % (橫列：集中度桶):")
    print((cond_prob * 100).round(2).to_string())
    print("\nLift (vs baseline):")
    print(lift.round(2).to_string())
    print(f"\nBaseline (無條件機率):")
    print((baseline * 100).round(2).to_string())

    chi2, p, dof, expected = stats.chi2_contingency(counts.values)
    print(f"\nChi-square: chi2={chi2:.2f}, p={p:.6f}, dof={dof}")

    extreme = []
    for c in lift.index:
        for r in lift.columns:
            if pd.isna(lift.loc[c, r]) or counts.loc[c, r] < 20:
                continue
            if lift.loc[c, r] >= 1.8 or lift.loc[c, r] <= 0.5:
                extreme.append({
                    "c_bucket": c, "regime": r, "n": int(counts.loc[c, r]),
                    "lift": float(lift.loc[c, r]),
                    "p_cond": float(cond_prob.loc[c, r])
                })
    print(f"\n極端格 (lift>=1.8 或 <=0.5, n>=20): {len(extreme)} 格")
    for e in extreme:
        print(f"  c_bucket={e['c_bucket']}  regime={e['regime']:<8} n={e['n']:>3}  lift={e['lift']:.2f}  cond_p={e['p_cond']*100:.1f}%")

    n_high_lift = sum(1 for e in extreme if e["lift"] >= 1.8)
    gate4 = n_high_lift >= 2 and p < 0.05
    print(f"\nGATE-4 (極端格): {n_high_lift} 格 lift>=1.8 + chi2 p={p:.4f} → 通過={gate4}")

    out = lift.stack().reset_index()
    out.columns = ["c_bucket", "regime", "lift"]
    out["count"] = out.apply(lambda r: int(counts.loc[r["c_bucket"], r["regime"]]), axis=1)
    out["cond_prob"] = out.apply(lambda r: float(cond_prob.loc[r["c_bucket"], r["regime"]]), axis=1)
    out.to_csv(RESULT_DIR / f"B_3x9_grid_top{n}.csv", index=False)


def analyze_crash(df: pd.DataFrame, n: int = 20) -> None:
    print("=" * 78)
    print(f"1D) 大跌規避分析 (N={n})")
    print("=" * 78)
    work = df.dropna(subset=[f"top{n}_dev_pct", "tx_dir", "tx_range"]).copy()
    work["c_bucket"] = pd.qcut(work[f"top{n}_dev_pct"], 3, labels=["c_low", "c_mid", "c_high"])
    range_top_tercile = work["tx_range"].quantile(2 / 3)
    work["is_crash"] = (work["tx_dir"] < -0.005) & (work["tx_range"] > range_top_tercile)

    baseline_crash = work["is_crash"].mean()
    by_bucket = work.groupby("c_bucket", observed=True)["is_crash"].agg(["mean", "count"])
    by_bucket["lift"] = by_bucket["mean"] / baseline_crash
    print(f"baseline 大跌機率: {baseline_crash*100:.2f}%  (定義: tx_dir<-0.5% 且 tx_range > 上 1/3 振幅閾值 {range_top_tercile*100:.2f}%)")
    print(by_bucket.round(4).to_string())

    max_lift = by_bucket["lift"].max()
    gate3 = max_lift >= 1.5
    print(f"\nGATE-3 (大跌規避): max lift = {max_lift:.2f} → 通過={gate3}")

    by_bucket.to_csv(RESULT_DIR / "C_crash_by_bucket.csv")
def analyze_list_changes(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1E) 結構性事件：清單進出榜")
    print("=" * 78)

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        symbols_by_month = conn.execute(
            "SELECT list_month, symbol, name, rank FROM top_lists WHERE rank <= 20 ORDER BY list_month, rank"
        ).fetchdf()

    months = sorted(symbols_by_month["list_month"].unique())
    rows = []
    prev_set: set[str] = set()
    prev_name_map: dict[str, str] = {}
    for m in months:
        sub = symbols_by_month[symbols_by_month["list_month"] == m]
        cur_set = set(sub["symbol"])
        cur_name_map = dict(zip(sub["symbol"], sub["name"]))
        if prev_set:
            new_in = cur_set - prev_set
            went_out = prev_set - cur_set
            for s in new_in:
                rows.append({"list_month": m, "event": "進榜", "symbol": s, "name": cur_name_map.get(s, "")})
            for s in went_out:
                rows.append({"list_month": m, "event": "退榜", "symbol": s, "name": prev_name_map.get(s, "")})
        prev_set = cur_set
        prev_name_map = cur_name_map

    diffs = pd.DataFrame(rows)
    diffs.to_csv(RESULT_DIR / "D_list_changes.csv", index=False)
    print(f"進退榜事件總數: {len(diffs)}")
    print(f"涉及月份數: {diffs['list_month'].nunique()} / {len(months)}")
    print(f"\n按事件類型統計:")
    print(diffs["event"].value_counts().to_string())
    print(f"\n進榜次數最多的個股 top 10:")
    print(diffs[diffs["event"]=="進榜"].groupby(["symbol","name"]).size().sort_values(ascending=False).head(10).to_string())

    # 對主訊號 (N=20) 做「移除進退榜當月」robustness 檢查
    change_months = set(diffs["list_month"].tolist())
    df_clean = df[~df["list_month"].isin(change_months)]
    print(f"\n移除有進出榜的月份後樣本: {len(df_clean)} (原 {len(df)})")
    if len(df_clean) > 100:
        df["q20"] = pd.qcut(df["top20_dev_pct"], 5, labels=[1,2,3,4,5], duplicates="drop")
        df_clean = df_clean.copy()
        df_clean["q20"] = pd.qcut(df_clean["top20_dev_pct"], 5, labels=[1,2,3,4,5], duplicates="drop")
        print(f"\nN=20 振幅 mean by quintile:")
        for label, d in [("原始", df), ("移除進出榜月", df_clean)]:
            arr = d.groupby("q20", observed=True)["tx_range"].mean() * 100
            print(f"  {label:<14}: {[f'{v:.2f}' for v in arr.values]}")


def analyze_correlation_h079(df: pd.DataFrame, start: date, end: date) -> None:
    print("=" * 78)
    print("1F) 與 H079 訊號相關性")
    print("=" * 78)
    H079_SQL = """
    WITH b AS (
        SELECT trade_date,
               SUM(up_count)*1.0/(SUM(up_count)+SUM(down_count)+SUM(unchanged_count)) AS up_ratio,
               SUM(total_value) AS mb_total
        FROM market_breadth
        WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    ),
    lv AS (
        SELECT trade_date,
               SUM(CASE WHEN is_limit_up THEN value ELSE 0 END) AS lu_value
        FROM stock_day WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    )
    SELECT b.trade_date, b.up_ratio, lv.lu_value*1.0/NULLIF(b.mb_total,0) AS lu_ratio
    FROM b LEFT JOIN lv USING (trade_date)
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        h079 = conn.execute(H079_SQL, [start, end, start, end]).fetchdf()
    h079["trade_date"] = pd.to_datetime(h079["trade_date"]).dt.date
    df_local = df.copy()
    df_local["trade_date"] = pd.to_datetime(df_local["trade_date"]).dt.date
    merged = df_local.merge(h079, on="trade_date", how="inner")
    rows = []
    for n in N_VALUES:
        for h in ["up_ratio", "lu_ratio"]:
            r = merged[[f"top{n}_dev_pct", h]].corr().iloc[0, 1]
            rows.append({"N": n, "h079_signal": h, "corr": r})
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "E_correlation_with_h079.csv", index=False)
    print(res.to_string(index=False))
    high = res[res["corr"].abs() > 0.7]
    if len(high) > 0:
        print(f"\n⚠️  與 H079 高度相關 (|corr|>0.7): {high.to_dict('records')}")
    else:
        print(f"\n與 H079 訊號獨立性高 (max |corr| = {res['corr'].abs().max():.3f})")


def analyze_quintile_weekday_ev(df: pd.DataFrame, n: int = 20) -> None:
    """5 桶 quintile × 5 weekday = 25 格 的整體期望值 + 大跌規避。"""
    print("=" * 78)
    print(f"1I) Quintile × Weekday EV (N={n})")
    print("=" * 78)
    work = df.dropna(subset=[f"top{n}_dev_pct"]).copy()
    work["q"] = pd.qcut(work[f"top{n}_dev_pct"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")
    wd_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    work["wd"] = work["weekday"].map(wd_map)
    range_top_tercile = work["tx_range"].quantile(2 / 3)
    work["is_crash"] = (work["tx_dir"] < -0.005) & (work["tx_range"] > range_top_tercile)
    baseline_crash = work["is_crash"].mean()

    rows = []
    for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
        for wd in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            sub = work[(work["q"] == q) & (work["wd"] == wd)]
            if len(sub) < 10:
                continue
            rows.append({
                "quintile": q, "weekday": wd, "n": len(sub),
                "p_up_pct": (sub["tx_dir"] > 0).mean() * 100,
                "p_crash_pct": sub["is_crash"].mean() * 100,
                "crash_lift": sub["is_crash"].mean() / baseline_crash,
                "mean_dir_pct": sub["tx_dir"].mean() * 100,
                "range_mean_pct": sub["tx_range"].mean() * 100,
            })
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "H_quintile_weekday.csv", index=False)

    print("\nMean tx_dir % (整體 EV):")
    pivot = res.pivot(index="quintile", columns="weekday", values="mean_dir_pct")
    pivot = pivot[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot.round(3).to_string())

    print(f"\nP(crash) % (baseline = {baseline_crash*100:.2f}%):")
    pivot_p = res.pivot(index="quintile", columns="weekday", values="p_crash_pct")
    pivot_p = pivot_p[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_p.round(2).to_string())

    print(f"\nCrash lift vs baseline:")
    pivot_l = res.pivot(index="quintile", columns="weekday", values="crash_lift")
    pivot_l = pivot_l[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_l.round(2).to_string())

    print("\np_up % (Q5-Q1 行/列差距):")
    pivot_pu = res.pivot(index="quintile", columns="weekday", values="p_up_pct")
    pivot_pu = pivot_pu[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    pivot_pu.loc["Q5-Q1 (pp)"] = pivot_pu.loc["Q5"] - pivot_pu.loc["Q1"]
    print(pivot_pu.round(2).to_string())

    print("\n樣本數 n:")
    pivot_n = res.pivot(index="quintile", columns="weekday", values="n")
    pivot_n = pivot_n[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_n.to_string())

    print("\n顯著 EV 格 (n>=30 且 |mean_dir| >= 0.20%):")
    ev_strong = res[(res["n"] >= 30) & (res["mean_dir_pct"].abs() >= 0.20)]
    if len(ev_strong) > 0:
        print(ev_strong.sort_values("mean_dir_pct", ascending=False).round(3).to_string(index=False))
    else:
        print("  (無符合條件)")

    print("\n極低 / 極高 crash lift 格 (n>=30 且 lift<=0.5 或 lift>=1.5):")
    crash_strong = res[(res["n"] >= 30) & ((res["crash_lift"] <= 0.5) | (res["crash_lift"] >= 1.5))]
    if len(crash_strong) > 0:
        print(crash_strong.sort_values("crash_lift").round(3).to_string(index=False))
    else:
        print("  (無符合條件)")


def analyze_ev_matrix(df: pd.DataFrame, n: int = 20) -> None:
    """細格 (c_bucket × weekday) 的完整機率與期望值。

    回答的問題：
    - 各情況下漲、跌、大跌的機率
    - 漲日的平均漲幅、跌日的平均跌幅
    - 整體期望值 (mean_tx_dir) — 是否有方向 EV
    - 大跌時的平均損失（風險大小）
    """
    print("=" * 78)
    print(f"1H) EV matrix (c_bucket × weekday, N={n})")
    print("=" * 78)
    work = df.dropna(subset=[f"top{n}_dev_pct"]).copy()
    work["c_bucket"] = pd.qcut(work[f"top{n}_dev_pct"], 3, labels=["c_low", "c_mid", "c_high"])
    wd_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    work["wd"] = work["weekday"].map(wd_map)

    range_top_tercile = work["tx_range"].quantile(2 / 3)
    work["is_crash"] = (work["tx_dir"] < -0.005) & (work["tx_range"] > range_top_tercile)
    work["is_rally"] = (work["tx_dir"] > 0.005) & (work["tx_range"] > range_top_tercile)

    rows = []
    for c in ["c_low", "c_mid", "c_high"]:
        for wd in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            sub = work[(work["c_bucket"] == c) & (work["wd"] == wd)]
            if len(sub) < 10:
                continue
            up = sub[sub["tx_dir"] > 0]
            dn = sub[sub["tx_dir"] < 0]
            crash = sub[sub["is_crash"]]
            rally = sub[sub["is_rally"]]
            rows.append({
                "c_bucket": c, "weekday": wd, "n": len(sub),
                "p_up_pct": (sub["tx_dir"] > 0).mean() * 100,
                "p_dn_pct": (sub["tx_dir"] < 0).mean() * 100,
                "p_crash_pct": sub["is_crash"].mean() * 100,
                "p_rally_pct": sub["is_rally"].mean() * 100,
                "mean_dir_pct": sub["tx_dir"].mean() * 100,            # 整體 EV
                "mean_up_pct": up["tx_dir"].mean() * 100 if len(up) else np.nan,
                "mean_dn_pct": dn["tx_dir"].mean() * 100 if len(dn) else np.nan,
                "mean_crash_loss_pct": crash["tx_dir"].mean() * 100 if len(crash) else np.nan,
                "mean_rally_gain_pct": rally["tx_dir"].mean() * 100 if len(rally) else np.nan,
                "range_mean_pct": sub["tx_range"].mean() * 100,
            })
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "G_ev_matrix.csv", index=False)

    # === 整體 EV (mean_tx_dir) ===
    print("\nMean tx_dir % (整體期望值, 越正越偏漲):")
    pivot_ev = res.pivot(index="c_bucket", columns="weekday", values="mean_dir_pct")
    pivot_ev = pivot_ev[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_ev.round(3).to_string())

    # === P(crash) 矩陣 ===
    print("\nP(crash) %:  (定義: tx_dir<-0.5% 且 tx_range > 上 1/3 振幅)")
    pivot_crash = res.pivot(index="c_bucket", columns="weekday", values="p_crash_pct")
    pivot_crash = pivot_crash[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_crash.round(2).to_string())

    # === P(rally) 矩陣 ===
    print("\nP(rally) %:  (定義: tx_dir>+0.5% 且 tx_range > 上 1/3 振幅)")
    pivot_rally = res.pivot(index="c_bucket", columns="weekday", values="p_rally_pct")
    pivot_rally = pivot_rally[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_rally.round(2).to_string())

    # === Crash 條件損失 ===
    print("\nMean loss when crash %:")
    pivot_loss = res.pivot(index="c_bucket", columns="weekday", values="mean_crash_loss_pct")
    pivot_loss = pivot_loss[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_loss.round(3).to_string())

    # === Rally 條件漲幅 ===
    print("\nMean gain when rally %:")
    pivot_gain = res.pivot(index="c_bucket", columns="weekday", values="mean_rally_gain_pct")
    pivot_gain = pivot_gain[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_gain.round(3).to_string())

    # === 樣本數 ===
    print("\n樣本數 n:")
    pivot_n = res.pivot(index="c_bucket", columns="weekday", values="n")
    pivot_n = pivot_n[["Mon", "Tue", "Wed", "Thu", "Fri"]]
    print(pivot_n.to_string())

    # === EV 顯著格 (n>=30 且 |mean_dir| >= 0.15%) ===
    print("\n顯著 EV 格 (n>=30 且 |mean_dir| >= 0.15%):")
    ev_extreme = res[(res["n"] >= 30) & (res["mean_dir_pct"].abs() >= 0.15)]
    if len(ev_extreme) > 0:
        cols = ["c_bucket", "weekday", "n", "mean_dir_pct", "p_up_pct",
                "p_crash_pct", "mean_crash_loss_pct", "p_rally_pct", "mean_rally_gain_pct"]
        print(ev_extreme[cols].sort_values("mean_dir_pct", ascending=False).round(3).to_string(index=False))
    else:
        print("  (無符合條件)")


def analyze_weekday(df: pd.DataFrame, n: int = 20) -> None:
    print("=" * 78)
    print(f"1G) Weekday 子分析 (N={n})")
    print("=" * 78)
    work = df.dropna(subset=[f"top{n}_dev_pct"]).copy()
    work["q"] = pd.qcut(work[f"top{n}_dev_pct"], 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
    wd_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    work["wd"] = work["weekday"].map(wd_map)
    rows = []
    for wd in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        for q in [1, 2, 3, 4, 5]:
            sub = work[(work["wd"] == wd) & (work["q"] == q)]
            if len(sub) < 10:
                continue
            rows.append({
                "weekday": wd, "quintile": q, "n": len(sub),
                "p_up": (sub["tx_dir"] > 0).mean(),
                "range_mean": sub["tx_range"].mean(),
                "dir_mean": sub["tx_dir"].mean(),
            })
    res = pd.DataFrame(rows)
    res.to_csv(RESULT_DIR / "F_weekday_breakdown.csv", index=False)

    print("\nrange_mean (%) by weekday × quintile:")
    pivot_r = res.pivot(index="weekday", columns="quintile", values="range_mean") * 100
    if 1 in pivot_r.columns and 5 in pivot_r.columns:
        pivot_r["Q5/Q1"] = pivot_r[5] / pivot_r[1]
    print(pivot_r.round(2).to_string())

    print("\np_up (%) by weekday × quintile:")
    pivot_p = res.pivot(index="weekday", columns="quintile", values="p_up") * 100
    if 1 in pivot_p.columns and 5 in pivot_p.columns:
        pivot_p["Q5-Q1 (pp)"] = pivot_p[5] - pivot_p[1]
    print(pivot_p.round(2).to_string())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01", type=date.fromisoformat)
    parser.add_argument("--end", default="2026-05-07", type=date.fromisoformat)
    args = parser.parse_args()

    df = load_daily(args.start, args.end)
    df = df.dropna(subset=["top20_dev_pct"])
    print(f"載入 {len(df)} 個交易日 ({df['trade_date'].min()} ~ {df['trade_date'].max()})")

    df.to_csv(RESULT_DIR / "timeseries.csv", index=False)
    print(f"已輸出: {RESULT_DIR / 'timeseries.csv'}")

    analyze_distribution(df)
    analyze_quintile_by_N(df)
    analyze_27grid(df, n=20)
    analyze_crash(df, n=20)
    analyze_list_changes(df)
    analyze_correlation_h079(df, args.start, args.end)
    analyze_weekday(df, n=20)
    analyze_ev_matrix(df, n=20)
    analyze_quintile_weekday_ev(df, n=20)


if __name__ == "__main__":
    main()

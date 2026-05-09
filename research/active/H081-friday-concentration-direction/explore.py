"""H081 Phase 1 Explore — 週五的權值股集中度方向訊號

從 H080 1G 1I 觀察：Q5×Fri p_up=64.71% vs Q1×Fri 48.72% (+15.99pp)，
其他 weekday Q5-Q1 接近零或反向。需嚴謹驗證避免 weekday cherry-picking。

GATE (全部通過才進 Phase 2):
  1. MW p<0.05 (Q5×Fri vs Q1×Fri / 整體 Friday / 整體 baseline)
  2. Permutation percentile >= 95% (不是 cherry-picking)
  3. 樣本穩定 (前後半 Q5×Fri p_up 差距 < 10 pp)

用法:
  uv run python research/active/H081-friday-concentration-direction/explore.py
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


DAILY_SQL = """
WITH ci AS (
    SELECT * FROM concentration_index
    WHERE trade_date BETWEEN ? AND ? AND top20_dev_pct IS NOT NULL
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
SELECT ci.trade_date, ci.top20_dev_pct,
       tx.tx_open, tx.tx_close, tx.tx_high, tx.tx_low
FROM ci JOIN tx USING (trade_date)
ORDER BY ci.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end]).fetchdf()
    df["tx_dir"] = (df["tx_close"] - df["tx_open"]) / df["tx_open"]
    df["tx_range"] = (df["tx_high"] - df["tx_low"]) / df["tx_open"]
    df["weekday"] = pd.to_datetime(df["trade_date"]).dt.weekday
    df["q"] = pd.qcut(df["top20_dev_pct"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")
    return df


# ---------------------------------------------------------------------------
# 1A. 樣本與分佈確認
# ---------------------------------------------------------------------------

def analyze_sample_distribution(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1A) 樣本與分佈確認")
    print("=" * 78)
    fri = df[df["weekday"] == 4]
    print(f"全樣本: {len(df)} 個交易日")
    print(f"週五樣本: {len(fri)} 個 ({len(fri)/len(df)*100:.1f}%)")
    print()

    print("週五 × quintile 分佈:")
    fri_dist = fri.groupby("q", observed=True).size()
    print(fri_dist.to_string())
    print()

    print("週五各桶的 tx_dir 統計 (%):")
    g = fri.groupby("q", observed=True).agg(
        n=("tx_dir", "count"),
        mean=("tx_dir", lambda s: s.mean() * 100),
        median=("tx_dir", lambda s: s.median() * 100),
        std=("tx_dir", lambda s: s.std() * 100),
        p_up=("tx_dir", lambda s: (s > 0).mean() * 100),
    )
    print(g.round(3).to_string())

    # 視覺化：Q5 vs Q1 直方圖
    fig, ax = plt.subplots(1, 1, figsize=(10, 5))
    q1_fri = fri[fri["q"] == "Q1"]["tx_dir"] * 100
    q5_fri = fri[fri["q"] == "Q5"]["tx_dir"] * 100
    bins = np.linspace(min(q1_fri.min(), q5_fri.min()), max(q1_fri.max(), q5_fri.max()), 30)
    ax.hist(q1_fri, bins=bins, alpha=0.55, label=f"Q1 x Fri (n={len(q1_fri)}, p_up={(q1_fri>0).mean()*100:.1f}%)", color="steelblue")
    ax.hist(q5_fri, bins=bins, alpha=0.55, label=f"Q5 x Fri (n={len(q5_fri)}, p_up={(q5_fri>0).mean()*100:.1f}%)", color="darkorange")
    ax.axvline(0, color="black", lw=0.5)
    ax.set_xlabel("tx_dir %")
    ax.set_ylabel("count")
    ax.set_title("H081 1A: tx_dir distribution Q1 vs Q5 within Friday")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULT_DIR / "1A_friday_distribution.png", dpi=120)
    plt.close(fig)
    print(f"\n已輸出: 1A_friday_distribution.png")


# ---------------------------------------------------------------------------
# 1B. Mann-Whitney 統計顯著性
# ---------------------------------------------------------------------------

def analyze_mw_significance(df: pd.DataFrame) -> dict:
    print("=" * 78)
    print("1B) Mann-Whitney U test")
    print("=" * 78)
    fri = df[df["weekday"] == 4]
    q5_fri = fri[fri["q"] == "Q5"]["tx_dir"]
    q1_fri = fri[fri["q"] == "Q1"]["tx_dir"]
    all_fri = fri["tx_dir"]
    all_baseline = df["tx_dir"]

    results = {}

    print(f"\n比較 1: Q5×Fri (n={len(q5_fri)}) vs Q1×Fri (n={len(q1_fri)})")
    u, p_two = stats.mannwhitneyu(q5_fri, q1_fri, alternative="two-sided")
    _, p_greater = stats.mannwhitneyu(q5_fri, q1_fri, alternative="greater")
    print(f"  U={u:.0f}, p (two-sided)={p_two:.4f}, p (Q5>Q1)={p_greater:.4f}")
    print(f"  Q5 median = {q5_fri.median()*100:+.3f}%, Q1 median = {q1_fri.median()*100:+.3f}%")
    results["q5_vs_q1_fri"] = p_greater

    print(f"\n比較 2: Q5×Fri vs 整體 Friday baseline (n={len(all_fri)})")
    _, p_greater_2 = stats.mannwhitneyu(q5_fri, all_fri, alternative="greater")
    print(f"  p (Q5×Fri > all Fri)={p_greater_2:.4f}")
    print(f"  Q5×Fri median = {q5_fri.median()*100:+.3f}%, all Fri median = {all_fri.median()*100:+.3f}%")
    results["q5_fri_vs_all_fri"] = p_greater_2

    print(f"\n比較 3: Q5×Fri vs 整體 baseline (n={len(all_baseline)})")
    _, p_greater_3 = stats.mannwhitneyu(q5_fri, all_baseline, alternative="greater")
    print(f"  p (Q5×Fri > all baseline)={p_greater_3:.4f}")
    print(f"  Q5×Fri median = {q5_fri.median()*100:+.3f}%, baseline median = {all_baseline.median()*100:+.3f}%")
    results["q5_fri_vs_all_baseline"] = p_greater_3

    all_pass = all(p < 0.05 for p in results.values())
    print(f"\nGATE-1 (MW p < 0.05 全通過): {all_pass}")
    return results


# ---------------------------------------------------------------------------
# 1C. Permutation test (核心：避免 weekday cherry-picking)
# ---------------------------------------------------------------------------

def analyze_permutation_test(df: pd.DataFrame, n_sims: int = 1000, rng_seed: int = 42) -> float:
    print("=" * 78)
    print(f"1C) Permutation test (shuffle weekday {n_sims} 次)")
    print("=" * 78)

    rng = np.random.default_rng(rng_seed)
    work = df.dropna(subset=["q"]).copy()

    # 計算實際 Q5-Q1 (pp) by weekday
    actual_q5q1 = {}
    for wd in range(5):
        sub = work[work["weekday"] == wd]
        if len(sub) < 10:
            continue
        q5 = sub[sub["q"] == "Q5"]["tx_dir"]
        q1 = sub[sub["q"] == "Q1"]["tx_dir"]
        if len(q5) > 0 and len(q1) > 0:
            actual_q5q1[wd] = ((q5 > 0).mean() - (q1 > 0).mean()) * 100

    actual_fri = actual_q5q1.get(4, 0.0)
    actual_max = max(abs(v) for v in actual_q5q1.values())
    print(f"實際 Q5-Q1 (pp) by weekday: {[(['Mon','Tue','Wed','Thu','Fri'][k], round(v,2)) for k,v in actual_q5q1.items()]}")
    print(f"實際週五 Q5-Q1 = {actual_fri:+.2f} pp")
    print(f"實際 |max| Q5-Q1 = {actual_max:.2f} pp (across all weekday)")
    print()

    # Shuffle weekday label, 重算
    null_fri = []
    null_max = []
    for _ in range(n_sims):
        shuffled_wd = rng.permutation(work["weekday"].values)
        sim_q5q1 = {}
        for wd in range(5):
            mask = shuffled_wd == wd
            sub_q = work["q"].values[mask]
            sub_d = work["tx_dir"].values[mask]
            q5_mask = sub_q == "Q5"
            q1_mask = sub_q == "Q1"
            if q5_mask.sum() < 10 or q1_mask.sum() < 10:
                continue
            sim_q5q1[wd] = ((sub_d[q5_mask] > 0).mean() - (sub_d[q1_mask] > 0).mean()) * 100
        if 4 in sim_q5q1:
            null_fri.append(sim_q5q1[4])
        if sim_q5q1:
            null_max.append(max(abs(v) for v in sim_q5q1.values()))

    null_fri = np.array(null_fri)
    null_max = np.array(null_max)

    # Test 1: 實際週五 effect 在 「shuffle 後的週五 effect」分佈中的 percentile
    #   (這等於 H₀: 週五沒有特別不同；alternative: Friday Q5-Q1 顯著大)
    pct_fri = (null_fri < actual_fri).mean() * 100
    print(f"Test A: actual Friday Q5-Q1 (+{actual_fri:.2f}) 在 null Friday 分佈中 percentile = {pct_fri:.1f}%")
    print(f"  null Friday Q5-Q1: mean={null_fri.mean():+.2f}, std={null_fri.std():.2f}, 95th pct={np.percentile(null_fri, 95):.2f}")

    # Test 2 (更嚴格): 實際 |max Q5-Q1 across all weekday| 在「shuffle 後 |max| 分佈」中 percentile
    #   (這控制了「從 5 個 weekday 中找最強的格」的多重比較)
    pct_max = (null_max < actual_max).mean() * 100
    print(f"\nTest B (cherry-picking corrected): actual |max| Q5-Q1 ({actual_max:.2f}) 在 null |max| 分佈中 percentile = {pct_max:.1f}%")
    print(f"  null |max| Q5-Q1: mean={null_max.mean():.2f}, std={null_max.std():.2f}, 95th pct={np.percentile(null_max, 95):.2f}")

    print(f"\nGATE-2 通過 (Test B percentile >= 95%): {pct_max >= 95}")
    return pct_max


# ---------------------------------------------------------------------------
# 1D. 早盤訊號相關性 (8:45-9:00 與全日 tx_dir)
# ---------------------------------------------------------------------------

def analyze_early_session_signal(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1D) 早盤訊號相關性")
    print("=" * 78)
    EARLY_SQL = """
    SELECT timestamp::DATE AS trade_date,
           FIRST(open ORDER BY timestamp) AS o_early,
           LAST(close ORDER BY timestamp) AS c_early
    FROM ohlcv_1m
    WHERE symbol = 'TX' AND timestamp::TIME BETWEEN '08:45:00' AND '09:00:00'
    GROUP BY trade_date
    """
    EARLY_30_SQL = EARLY_SQL.replace("'09:00:00'", "'09:15:00'")

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        e15 = conn.execute(EARLY_SQL).fetchdf()
        e30 = conn.execute(EARLY_30_SQL).fetchdf()

    e15["trade_date"] = pd.to_datetime(e15["trade_date"]).dt.date
    e30["trade_date"] = pd.to_datetime(e30["trade_date"]).dt.date
    e15["e15_dir"] = (e15["c_early"] - e15["o_early"]) / e15["o_early"]
    e30["e30_dir"] = (e30["c_early"] - e30["o_early"]) / e30["o_early"]

    work = df.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work.merge(e15[["trade_date", "e15_dir"]], on="trade_date").merge(e30[["trade_date", "e30_dir"]], on="trade_date")
    fri = work[work["weekday"] == 4]
    q5_fri = fri[fri["q"] == "Q5"]
    q1_fri = fri[fri["q"] == "Q1"]

    print("整體樣本:")
    print(f"  corr(8:45-9:00 dir, full day dir) = {work[['e15_dir','tx_dir']].corr().iloc[0,1]:+.3f}")
    print(f"  corr(8:45-9:15 dir, full day dir) = {work[['e30_dir','tx_dir']].corr().iloc[0,1]:+.3f}")
    print()
    print("Q5×Fri 子樣本:")
    if len(q5_fri) > 5:
        print(f"  早盤 15 分 mean dir = {q5_fri['e15_dir'].mean()*100:+.3f}%, 全日 mean dir = {q5_fri['tx_dir'].mean()*100:+.3f}%")
        print(f"  早盤 30 分 mean dir = {q5_fri['e30_dir'].mean()*100:+.3f}%")
        print(f"  P(早盤 15 分上漲) = {(q5_fri['e15_dir']>0).mean()*100:.1f}%, P(全日上漲) = {(q5_fri['tx_dir']>0).mean()*100:.1f}%")
        print(f"  早盤已建立方向的延續率: ", end="")
        same_sign_15 = ((q5_fri["e15_dir"] > 0) == (q5_fri["tx_dir"] > 0)).mean() * 100
        same_sign_30 = ((q5_fri["e30_dir"] > 0) == (q5_fri["tx_dir"] > 0)).mean() * 100
        print(f"15 分→全日 {same_sign_15:.1f}%, 30 分→全日 {same_sign_30:.1f}%")

    print("\nQ1×Fri 子樣本:")
    if len(q1_fri) > 5:
        print(f"  早盤 15 分 mean dir = {q1_fri['e15_dir'].mean()*100:+.3f}%, 全日 mean dir = {q1_fri['tx_dir'].mean()*100:+.3f}%")


# ---------------------------------------------------------------------------
# 1E. 樣本穩定性
# ---------------------------------------------------------------------------

def analyze_stability(df: pd.DataFrame) -> bool:
    print("=" * 78)
    print("1E) 樣本穩定性 (前後半切分)")
    print("=" * 78)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    median_date = df["trade_date"].quantile(0.5)
    h1 = df[df["trade_date"] < median_date]
    h2 = df[df["trade_date"] >= median_date]

    rows = []
    for label, sub in [("H1 (前半)", h1), ("H2 (後半)", h2)]:
        fri = sub[sub["weekday"] == 4]
        q5 = fri[fri["q"] == "Q5"]
        q1 = fri[fri["q"] == "Q1"]
        rows.append({
            "split": label,
            "date_range": f"{sub['trade_date'].min().date()} ~ {sub['trade_date'].max().date()}",
            "fri_n": len(fri),
            "q5_n": len(q5),
            "q1_n": len(q1),
            "q5_p_up": (q5["tx_dir"] > 0).mean() * 100 if len(q5) else np.nan,
            "q1_p_up": (q1["tx_dir"] > 0).mean() * 100 if len(q1) else np.nan,
            "q5_q1_pp": ((q5["tx_dir"] > 0).mean() - (q1["tx_dir"] > 0).mean()) * 100 if len(q5) and len(q1) else np.nan,
        })
    res = pd.DataFrame(rows)
    print(res.to_string(index=False))

    diff = abs(res.iloc[0]["q5_q1_pp"] - res.iloc[1]["q5_q1_pp"])
    stable = diff < 10
    print(f"\n前後半 Q5-Q1 (pp) 差距 = {diff:.2f} pp")
    print(f"GATE-3 通過 (差距 < 10 pp): {stable}")
    return stable


# ---------------------------------------------------------------------------
# 補充：top10 / top5 分桶 vs top20
# ---------------------------------------------------------------------------

def analyze_alternative_buckets(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("補充: 不同 N 的訊號比較 (Q5×Fri p_up)")
    print("=" * 78)
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        ci_full = conn.execute("""
            SELECT trade_date, top1_dev_pct, top5_dev_pct, top10_dev_pct, top20_dev_pct
            FROM concentration_index
            WHERE top20_dev_pct IS NOT NULL
        """).fetchdf()
    ci_full["trade_date"] = pd.to_datetime(ci_full["trade_date"]).dt.date
    work = df.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work.merge(ci_full, on="trade_date", suffixes=("", "_y"))

    rows = []
    for n in [1, 5, 10, 20]:
        col = f"top{n}_dev_pct"
        work[f"q_n{n}"] = pd.qcut(work[col], 5, labels=["Q1","Q2","Q3","Q4","Q5"], duplicates="drop")
        fri = work[work["weekday"] == 4]
        q5 = fri[fri[f"q_n{n}"] == "Q5"]
        q1 = fri[fri[f"q_n{n}"] == "Q1"]
        rows.append({
            "N": n,
            "q5_n": len(q5), "q1_n": len(q1),
            "q5_p_up": (q5["tx_dir"] > 0).mean() * 100 if len(q5) else np.nan,
            "q1_p_up": (q1["tx_dir"] > 0).mean() * 100 if len(q1) else np.nan,
            "q5_q1_pp": ((q5["tx_dir"] > 0).mean() - (q1["tx_dir"] > 0).mean()) * 100 if len(q5) and len(q1) else np.nan,
        })
    res = pd.DataFrame(rows)
    print(res.round(2).to_string(index=False))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01", type=date.fromisoformat)
    parser.add_argument("--end", default="2026-05-07", type=date.fromisoformat)
    args = parser.parse_args()

    df = load_daily(args.start, args.end)
    print(f"載入 {len(df)} 個交易日 ({df['trade_date'].min()} ~ {df['trade_date'].max()})")
    print()

    analyze_sample_distribution(df)
    print()
    mw_results = analyze_mw_significance(df)
    print()
    perm_pct = analyze_permutation_test(df, n_sims=2000)
    print()
    analyze_early_session_signal(df)
    print()
    stable = analyze_stability(df)
    print()
    analyze_alternative_buckets(df)
    print()

    # GATE 摘要
    print("=" * 78)
    print("GATE 總結")
    print("=" * 78)
    gate1 = all(p < 0.05 for p in mw_results.values())
    gate2 = perm_pct >= 95
    gate3 = stable
    print(f"GATE-1 (MW p<0.05 三條全過): {gate1}")
    print(f"GATE-2 (Permutation pct>=95%): {gate2}  (actual: {perm_pct:.1f}%)")
    print(f"GATE-3 (前後半穩定): {gate3}")
    print(f"\n整體通過 (全部): {gate1 and gate2 and gate3}")


if __name__ == "__main__":
    main()

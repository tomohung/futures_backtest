"""H082 Phase 1 Explore — 低集中度 × weekday 安全日訊號

從 H080 1I 觀察：
  - Q1 × Wed (n=43): P(crash) = 0%
  - Q1 × Fri (n=39): P(crash) = 2.56%
  - baseline P(crash) = 13.85%

GATE (全部通過才進 Phase 2):
  1. Wilson CI 上限 < 10% (明顯低於 baseline 13.85%)
  2. Permutation percentile >= 95% (避免 weekday × quintile cherry-picking)
  3. 前後半樣本穩定 (兩段 P(crash) 都 < 10%)
  4. **實戰窗口檢查 (同期 vs t-1 prior 雙版本都通過)**

雙版本：
  Branch A: same-day Q1 (H080 1I 原版，同期相關)
  Branch B: t-1 Q1 (盤前 prior 版，符合實戰窗口要求)

用法:
  uv run python research/active/H082-low-concentration-safe-day/explore.py
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

    # Crash 定義 (與 H080 1D 一致)
    range_top_tercile = df["tx_range"].quantile(2 / 3)
    df["is_crash"] = (df["tx_dir"] < -0.005) & (df["tx_range"] > range_top_tercile)

    # Branch A: same-day quintile
    df["q_same"] = pd.qcut(df["top20_dev_pct"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")

    # Branch B: t-1 quintile (盤前 prior)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["dev_lag1"] = df["top20_dev_pct"].shift(1)
    df["q_lag1"] = pd.qcut(df["dev_lag1"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")

    return df


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    z = stats.norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    halfwidth = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - halfwidth), min(1.0, center + halfwidth)


# ---------------------------------------------------------------------------
# 1A. Branch A vs Branch B 對比 — 樣本與基本機率
# ---------------------------------------------------------------------------

def analyze_basic_probabilities(df: pd.DataFrame) -> dict:
    print("=" * 78)
    print("1A) 同期 (Branch A) vs t-1 prior (Branch B) 機率對比")
    print("=" * 78)

    baseline_crash = df["is_crash"].mean()
    print(f"全樣本 N = {len(df)}")
    print(f"baseline P(crash) = {baseline_crash*100:.2f}% (baseline lift = 1.00)")
    print(f"crash 定義: tx_dir < -0.5% 且 tx_range > 全樣本上 1/3 振幅切點 ({df['tx_range'].quantile(2/3)*100:.2f}%)")
    print()

    wd_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    cells = [("Q1×Wed", "Q1", 2), ("Q1×Fri", "Q1", 4), ("(Q1+Q2)×Fri", "Q12", 4)]

    results = {"baseline_crash": baseline_crash, "branches": {}}

    for branch, q_col in [("A_same", "q_same"), ("B_lag1", "q_lag1")]:
        print(f"--- Branch {branch} ({q_col}) ---")
        sub = df.dropna(subset=[q_col]).copy()
        rows = []
        for label, qsel, wd in cells:
            if qsel == "Q12":
                mask = (sub[q_col].isin(["Q1", "Q2"])) & (sub["weekday"] == wd)
            else:
                mask = (sub[q_col] == qsel) & (sub["weekday"] == wd)
            cell = sub[mask]
            n = len(cell)
            k = cell["is_crash"].sum()
            p = k / n if n > 0 else 0.0
            wlow, whigh = wilson_ci(int(k), n)
            mean_dir = cell["tx_dir"].mean() * 100 if n > 0 else 0
            min_dir = cell["tx_dir"].min() * 100 if n > 0 else 0
            rows.append({
                "cell": label, "n": n, "k_crash": int(k),
                "p_crash%": p * 100,
                "lift": p / baseline_crash if baseline_crash else 0,
                "wilson_lo%": wlow * 100,
                "wilson_hi%": whigh * 100,
                "mean_dir%": mean_dir,
                "max_drop%": min_dir,
            })
        res = pd.DataFrame(rows)
        print(res.round(3).to_string(index=False))
        print()
        results["branches"][branch] = res

    return results


# ---------------------------------------------------------------------------
# 1B. Wilson CI GATE 評估
# ---------------------------------------------------------------------------

def evaluate_wilson_gate(results: dict, threshold: float = 0.10) -> dict:
    print("=" * 78)
    print(f"1B) Wilson CI GATE: 上限 < {threshold*100:.0f}% 才通過")
    print("=" * 78)
    gate_results = {}
    for branch_name, res in results["branches"].items():
        print(f"\n{branch_name}:")
        for _, r in res.iterrows():
            passed = r["wilson_hi%"] / 100 < threshold
            mark = "✅" if passed else "❌"
            print(f"  {mark} {r['cell']:<14} k/n={int(r['k_crash'])}/{int(r['n'])}  P(crash)={r['p_crash%']:.2f}%  Wilson 95% CI=[{r['wilson_lo%']:.2f}%, {r['wilson_hi%']:.2f}%]")
            gate_results[(branch_name, r["cell"])] = passed
    return gate_results


# ---------------------------------------------------------------------------
# 1C. Permutation test (cherry-picking corrected)
# ---------------------------------------------------------------------------

def analyze_permutation(df: pd.DataFrame, q_col: str, branch_name: str, n_sims: int = 2000, rng_seed: int = 42) -> dict:
    print("=" * 78)
    print(f"1C-{branch_name}) Permutation test (shuffle 25 cells, {n_sims} sims)")
    print("=" * 78)
    work = df.dropna(subset=[q_col, "is_crash"]).copy()
    rng = np.random.default_rng(rng_seed)

    # 實際: 計算 25 格 (5 quintile × 5 weekday) 的 P(crash)
    # 找最低的 (越低越「safe」)
    actual_min_p = {}
    for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
        for wd in range(5):
            sub = work[(work[q_col] == q) & (work["weekday"] == wd)]
            if len(sub) >= 30:
                actual_min_p[(q, wd)] = sub["is_crash"].mean()

    actual_q1_wed = work[(work[q_col] == "Q1") & (work["weekday"] == 2)]["is_crash"].mean() if len(work[(work[q_col] == "Q1") & (work["weekday"] == 2)]) > 0 else np.nan
    actual_q1_fri = work[(work[q_col] == "Q1") & (work["weekday"] == 4)]["is_crash"].mean() if len(work[(work[q_col] == "Q1") & (work["weekday"] == 4)]) > 0 else np.nan
    actual_global_min = min(actual_min_p.values()) if actual_min_p else np.nan

    print(f"實際: Q1×Wed P(crash)={actual_q1_wed*100:.2f}%, Q1×Fri P(crash)={actual_q1_fri*100:.2f}%")
    print(f"實際 25 格中最低 P(crash) = {actual_global_min*100:.2f}%")

    # Shuffle (q × weekday) 雙標籤組合
    null_q1_wed = []
    null_q1_fri = []
    null_min = []
    quintile_arr = work[q_col].astype(str).values
    weekday_arr = work["weekday"].values
    crash_arr = work["is_crash"].values

    for _ in range(n_sims):
        # Shuffle crash labels (簡單版，符合 null hypothesis)
        shuffled_crash = rng.permutation(crash_arr)
        sim_min = 1.0
        sim_q1_wed = np.nan
        sim_q1_fri = np.nan
        for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            for wd in range(5):
                mask = (quintile_arr == q) & (weekday_arr == wd)
                if mask.sum() >= 30:
                    p = shuffled_crash[mask].mean()
                    sim_min = min(sim_min, p)
                    if q == "Q1" and wd == 2:
                        sim_q1_wed = p
                    if q == "Q1" and wd == 4:
                        sim_q1_fri = p
        null_min.append(sim_min)
        if not np.isnan(sim_q1_wed):
            null_q1_wed.append(sim_q1_wed)
        if not np.isnan(sim_q1_fri):
            null_q1_fri.append(sim_q1_fri)

    null_min = np.array(null_min)
    null_q1_wed = np.array(null_q1_wed)
    null_q1_fri = np.array(null_q1_fri)

    # Test A: 實際 Q1×Wed vs null Q1×Wed (specific cell)
    pct_q1_wed = (null_q1_wed > actual_q1_wed).mean() * 100 if len(null_q1_wed) > 0 else np.nan
    pct_q1_fri = (null_q1_fri > actual_q1_fri).mean() * 100 if len(null_q1_fri) > 0 else np.nan
    print(f"\nTest A (specific cell):")
    print(f"  Q1×Wed: actual {actual_q1_wed*100:.2f}% < null in {pct_q1_wed:.1f}% of sims (越高越強)")
    print(f"  Q1×Fri: actual {actual_q1_fri*100:.2f}% < null in {pct_q1_fri:.1f}% of sims")

    # Test B: actual_min vs null_min (cherry-picking corrected)
    pct_global = (null_min > actual_global_min).mean() * 100
    print(f"\nTest B (cherry-picking corrected, 在 25 格中找最低):")
    print(f"  null min P(crash) 分佈: mean={null_min.mean()*100:.2f}%, std={null_min.std()*100:.2f}%, 5th pct={np.percentile(null_min, 5)*100:.2f}%")
    print(f"  實際 min ({actual_global_min*100:.2f}%) 比 null min 低 (更 safer) 的次數佔 {pct_global:.1f}%")
    print(f"  → cherry-picking corrected percentile = {pct_global:.1f}%")

    gate2_pass = pct_global >= 95
    print(f"\nGATE-2 通過 (Test B percentile >= 95%): {gate2_pass}")

    return {"q1_wed_pct": pct_q1_wed, "q1_fri_pct": pct_q1_fri, "global_pct": pct_global, "gate2": gate2_pass}


# ---------------------------------------------------------------------------
# 1D. 樣本穩定性 (前後半)
# ---------------------------------------------------------------------------

def analyze_stability(df: pd.DataFrame, q_col: str, branch_name: str) -> dict:
    print("=" * 78)
    print(f"1D-{branch_name}) 樣本穩定性")
    print("=" * 78)
    work = df.dropna(subset=[q_col]).copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"])
    median_date = work["trade_date"].quantile(0.5)
    h1 = work[work["trade_date"] < median_date]
    h2 = work[work["trade_date"] >= median_date]

    rows = []
    for split_label, sub in [("H1 前半", h1), ("H2 後半", h2)]:
        for cell_label, qsel, wd in [("Q1×Wed", "Q1", 2), ("Q1×Fri", "Q1", 4)]:
            mask = (sub[q_col] == qsel) & (sub["weekday"] == wd)
            cell = sub[mask]
            n = len(cell)
            k = cell["is_crash"].sum()
            p = k / n if n > 0 else np.nan
            rows.append({"split": split_label, "cell": cell_label, "n": n, "k": int(k), "p_crash%": (p * 100) if not np.isnan(p) else np.nan})
    res = pd.DataFrame(rows)
    print(res.round(2).to_string(index=False))

    # 評估穩定性
    stability = {}
    for cell_label in ["Q1×Wed", "Q1×Fri"]:
        sub = res[res["cell"] == cell_label]
        if len(sub) == 2:
            both_low = all(sub["p_crash%"] < 10)  # 兩段都 < 10%
            stability[cell_label] = both_low
            print(f"  {cell_label}: 兩段 P(crash) 都 < 10% → {both_low}")
    return stability


# ---------------------------------------------------------------------------
# 1E. 實戰窗口驗證 — Branch B (t-1 prior) 的同期 effect 是否仍 hold
# ---------------------------------------------------------------------------

def compare_branches(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("1E) Branch A (same-day) vs Branch B (t-1 prior) 衰減分析")
    print("=" * 78)
    print("如果 Branch B 比 Branch A 衰減太多 → t-1 prior 不可靠 → 沒實戰窗口")
    print()

    for cell_label, qsel, wd in [("Q1×Wed", "Q1", 2), ("Q1×Fri", "Q1", 4)]:
        print(f"--- {cell_label} ---")
        for branch, q_col in [("A same-day", "q_same"), ("B t-1 prior", "q_lag1")]:
            sub = df.dropna(subset=[q_col])
            mask = (sub[q_col] == qsel) & (sub["weekday"] == wd)
            cell = sub[mask]
            n = len(cell)
            k = cell["is_crash"].sum()
            p_crash = k / n * 100 if n > 0 else 0
            mean_dir = cell["tx_dir"].mean() * 100 if n > 0 else 0
            print(f"  {branch}: n={n}  P(crash)={p_crash:.2f}%  mean_dir={mean_dir:+.3f}%")
        print()


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

    results = analyze_basic_probabilities(df)
    print()
    wilson_gate = evaluate_wilson_gate(results, threshold=0.10)
    print()
    perm_a = analyze_permutation(df, "q_same", "A same-day", n_sims=2000)
    print()
    perm_b = analyze_permutation(df, "q_lag1", "B t-1 prior", n_sims=2000)
    print()
    stab_a = analyze_stability(df, "q_same", "A same-day")
    print()
    stab_b = analyze_stability(df, "q_lag1", "B t-1 prior")
    print()
    compare_branches(df)
    print()

    # GATE 總結
    print("=" * 78)
    print("GATE 總結")
    print("=" * 78)
    print("\nBranch A (same-day):")
    print(f"  GATE-1 Wilson CI < 10%: Q1×Wed={wilson_gate.get(('A_same','Q1×Wed'))}, Q1×Fri={wilson_gate.get(('A_same','Q1×Fri'))}")
    print(f"  GATE-2 Permutation: {perm_a['gate2']} (pct={perm_a['global_pct']:.1f}%)")
    print(f"  GATE-3 Stability: Q1×Wed={stab_a.get('Q1×Wed')}, Q1×Fri={stab_a.get('Q1×Fri')}")

    print("\nBranch B (t-1 prior, 實戰窗口版):")
    print(f"  GATE-1 Wilson CI < 10%: Q1×Wed={wilson_gate.get(('B_lag1','Q1×Wed'))}, Q1×Fri={wilson_gate.get(('B_lag1','Q1×Fri'))}")
    print(f"  GATE-2 Permutation: {perm_b['gate2']} (pct={perm_b['global_pct']:.1f}%)")
    print(f"  GATE-3 Stability: Q1×Wed={stab_b.get('Q1×Wed')}, Q1×Fri={stab_b.get('Q1×Fri')}")


if __name__ == "__main__":
    main()

"""H079 Phase 1 Explore — 廣度 + 漲停成交額溫度計

從 market_breadth + stock_day 計算每日衍生指標，並 join 台指期日盤資料。

子假設：
  A) 廣度背離（加權漲 + 上漲家數比例 < 0.30）→ 隔日 + 未來 5 日累積偏空
  B) 漲停成交額象限 → 後續 5/10/20 日報酬與最大回撤差異
  C) 漲停萎縮事件 → 未來 20 日內 P(單日跌>2%) 與 P(累積跌>5%) 上升
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULT_DIR = Path(__file__).parent / "results"


DAILY_INDICATOR_SQL = """
WITH b AS (
    SELECT trade_date,
           SUM(up_count)         AS up_count,
           SUM(down_count)       AS down_count,
           SUM(unchanged_count)  AS unchanged_count,
           SUM(up_limit_count)   AS up_limit_count,
           SUM(down_limit_count) AS down_limit_count,
           SUM(total_value)      AS total_value
    FROM market_breadth
    WHERE trade_date BETWEEN ? AND ?
    GROUP BY trade_date
),
lv AS (
    SELECT trade_date,
           SUM(CASE WHEN is_limit_up   THEN value ELSE 0 END) AS lu_value,
           SUM(CASE WHEN is_limit_down THEN value ELSE 0 END) AS ld_value
    FROM stock_day
    WHERE trade_date BETWEEN ? AND ?
    GROUP BY trade_date
),
tx AS (
    SELECT timestamp::DATE AS trade_date,
           FIRST(open  ORDER BY timestamp) AS o,
           LAST(close  ORDER BY timestamp) AS c,
           MAX(high)                       AS h,
           MIN(low)                        AS l
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::DATE BETWEEN ? AND ?
      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
    GROUP BY trade_date
)
SELECT b.trade_date, b.up_count, b.down_count, b.unchanged_count,
       b.up_limit_count, b.down_limit_count, b.total_value,
       lv.lu_value, lv.ld_value,
       tx.o AS tx_open, tx.c AS tx_close, tx.h AS tx_high, tx.l AS tx_low
FROM b LEFT JOIN lv USING (trade_date) LEFT JOIN tx USING (trade_date)
ORDER BY b.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_INDICATOR_SQL, [start, end, start, end, start, end]).fetchdf()
    df["up_ratio"] = df["up_count"] / (df["up_count"] + df["down_count"] + df["unchanged_count"])
    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    df["ld_value_ratio"] = df["ld_value"] / df["total_value"]
    df["tx_ret"] = (df["tx_close"] - df["tx_open"]) / df["tx_open"]
    df["daily_close_ret"] = df["tx_close"].pct_change()
    for h in [1, 5, 10, 20]:
        df[f"fwd_ret_{h}d"] = df["tx_close"].shift(-h) / df["tx_close"] - 1
        df[f"fwd_min_{h}d"] = df["tx_low"].rolling(h).min().shift(-h) / df["tx_close"] - 1
    for h in [5, 10, 20]:
        df[f"fwd_worst_daily_{h}d"] = df["daily_close_ret"].shift(-1).rolling(h).min()
    df["lu_cnt_ma7"] = df["up_limit_count"].rolling(7).mean()
    df["lu_ratio_ma7"] = df["lu_value_ratio"].rolling(7).mean()
    return df


# ---------------------------------------------------------------------------
# A: 廣度背離
# ---------------------------------------------------------------------------

def analyze_A(df: pd.DataFrame) -> None:
    print("=" * 78)
    print("A) 廣度背離（加權漲 AND up_ratio < 0.30）")
    print("=" * 78)
    flag = (df["tx_ret"] > 0) & (df["up_ratio"] < 0.30)
    n = flag.sum()
    print(f"背離日: {n} 筆 (佔 {n/len(df)*100:.1f}%)")
    if n < 5:
        print("樣本不足。")
        return

    print(f"\n累積報酬比較（hypothesis: 背離日 < 對照組）:")
    print(f"{'horizon':<10}{'背離 median':<14}{'對照 median':<14}"
          f"{'MW p (兩側)':<14}{'MW p (背離<對照)':<18}")
    for h in [1, 5, 10, 20]:
        a = df.loc[flag, f"fwd_ret_{h}d"].dropna()
        b = df.loc[~flag, f"fwd_ret_{h}d"].dropna()
        if len(a) > 5:
            _, p_two = stats.mannwhitneyu(a, b, alternative="two-sided")
            _, p_less = stats.mannwhitneyu(a, b, alternative="less")
            print(f"{h}d_ret    {a.median():+.4f}      {b.median():+.4f}      "
                  f"{p_two:.3f}         {p_less:.3f}")

    print(f"\n最大回撤比較（hypothesis: 背離日 < 對照組）:")
    print(f"{'horizon':<10}{'背離 median':<14}{'對照 median':<14}{'MW p (背離<對照)':<18}")
    for h in [5, 10, 20]:
        a = df.loc[flag, f"fwd_min_{h}d"].dropna()
        b = df.loc[~flag, f"fwd_min_{h}d"].dropna()
        if len(a) > 5:
            _, p_less = stats.mannwhitneyu(a, b, alternative="less")
            print(f"{h}d_min    {a.median():+.4f}      {b.median():+.4f}      {p_less:.3f}")


# ---------------------------------------------------------------------------
# B: 漲停成交額象限
# ---------------------------------------------------------------------------

def analyze_B(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 78)
    print("B) 漲停成交額象限（HC/LC × HV/LV，門檻 = 全期中位數）")
    print("=" * 78)
    cnt_med = df["up_limit_count"].median()
    val_med = df["lu_value_ratio"].median()
    print(f"門檻: count_median={cnt_med:.0f}, value_ratio_median={val_med:.4f}")

    df = df.copy()
    df["hc"] = df["up_limit_count"] >= cnt_med
    df["hv"] = df["lu_value_ratio"] >= val_med
    df["quad"] = df.apply(
        lambda r: f"{'HC' if r['hc'] else 'LC'}-{'HV' if r['hv'] else 'LV'}", axis=1
    )

    print(f"\n各象限後續報酬中位數:")
    print(f"{'象限':<8}{'n':<6}{'5d_ret':<12}{'10d_ret':<12}{'20d_ret':<12}"
          f"{'5d_min':<12}{'10d_min':<12}{'20d_min':<12}")
    for q in ["HC-HV", "HC-LV", "LC-HV", "LC-LV"]:
        sub = df[df["quad"] == q]
        print(f"{q:<8}{len(sub):<6}"
              f"{sub['fwd_ret_5d'].median():+.4f}     "
              f"{sub['fwd_ret_10d'].median():+.4f}     "
              f"{sub['fwd_ret_20d'].median():+.4f}     "
              f"{sub['fwd_min_5d'].median():+.4f}     "
              f"{sub['fwd_min_10d'].median():+.4f}     "
              f"{sub['fwd_min_20d'].median():+.4f}")

    print(f"\nKruskal-Wallis 檢定（四象限是否有差異）:")
    for col in ["fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d",
                "fwd_min_5d", "fwd_min_10d", "fwd_min_20d"]:
        quads = [df.loc[df["quad"] == q, col].dropna()
                 for q in ["HC-HV", "HC-LV", "LC-HV", "LC-LV"]]
        h, p = stats.kruskal(*quads)
        print(f"  {col}: H={h:.2f}, p={p:.3f}")

    print(f"\n核心對比 LC-HV (集中) vs HC-HV (健康)，單側 Mann-Whitney (LC-HV < HC-HV):")
    for col in ["fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d",
                "fwd_min_5d", "fwd_min_10d", "fwd_min_20d"]:
        a = df.loc[df["quad"] == "LC-HV", col].dropna()
        b = df.loc[df["quad"] == "HC-HV", col].dropna()
        if len(a) > 5 and len(b) > 5:
            _, p = stats.mannwhitneyu(a, b, alternative="less")
            mark = " ✅" if p < 0.05 else (" ⚠️" if p < 0.10 else "")
            print(f"  {col}: p={p:.3f}{mark}")
    return df


# ---------------------------------------------------------------------------
# C: 漲停萎縮事件
# ---------------------------------------------------------------------------

def analyze_C(df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("C) 漲停萎縮事件（lu_cnt_ma7 與 lu_ratio_ma7 同時 < 全期 X 分位，連續 N 天）")
    print("=" * 78)

    base_daily = ((df["fwd_worst_daily_20d"] < -0.02).sum()
                  / df["fwd_worst_daily_20d"].notna().sum())
    base_cum = ((df["fwd_min_20d"] < -0.05).sum() / df["fwd_min_20d"].notna().sum())
    print(f"基準 P(未來20日內 單日跌>2%) = {base_daily:.2%}")
    print(f"基準 P(未來20日內 累積跌>5%) = {base_cum:.2%}")

    print(f"\n{'pct':<6}{'consec':<8}{'事件數':<8}"
          f"{'P(單日>2%)':<13}{'倍數':<7}{'P(累積>5%)':<13}{'倍數':<7}"
          f"{'20d_min med':<14}")
    for pct in [0.10, 0.15, 0.20, 0.30]:
        cnt_th = df["lu_cnt_ma7"].quantile(pct)
        rat_th = df["lu_ratio_ma7"].quantile(pct)
        flag = (df["lu_cnt_ma7"] < cnt_th) & (df["lu_ratio_ma7"] < rat_th)
        for consec in [1, 3, 5]:
            ev = flag.rolling(consec).sum() >= consec
            if ev.sum() < 1:
                continue
            sub_daily = df.loc[ev, "fwd_worst_daily_20d"].dropna()
            sub_cum = df.loc[ev, "fwd_min_20d"].dropna()
            p_daily = (sub_daily < -0.02).sum() / len(sub_daily) if len(sub_daily) else 0
            p_cum = (sub_cum < -0.05).sum() / len(sub_cum) if len(sub_cum) else 0
            print(f"{pct:<6}{consec:<8}{ev.sum():<8}"
                  f"{p_daily:.2%}        {p_daily/base_daily:.2f}x   "
                  f"{p_cum:.2%}        {p_cum/base_cum:.2f}x   "
                  f"{sub_cum.median():+.4f}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="H079 Phase 1 explore")
    p.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 4, 30))
    p.add_argument("--save", action="store_true", help="store CSV outputs to results/")
    args = p.parse_args()

    print(f"Loading {args.start} ~ {args.end} from {DB_PATH}")
    df = load_daily(args.start, args.end)
    print(f"Rows loaded: {len(df)}")
    if df.empty:
        return

    print("\n=== Baseline stats ===")
    print(f"up_ratio        : median={df['up_ratio'].median():.3f}, mean={df['up_ratio'].mean():.3f}")
    print(f"up_limit_count  : median={df['up_limit_count'].median():.0f}, mean={df['up_limit_count'].mean():.1f}")
    print(f"lu_value_ratio  : median={df['lu_value_ratio'].median():.4f}, mean={df['lu_value_ratio'].mean():.4f}")
    print(f"tx_ret (日盤)   : median={df['tx_ret'].median():.4f}, mean={df['tx_ret'].mean():.4f}")

    analyze_A(df)
    df_b = analyze_B(df)
    analyze_C(df)

    if args.save:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(RESULT_DIR / "daily_indicators.csv", index=False)
        df_b[["trade_date", "quad", "up_limit_count", "lu_value_ratio",
              "fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d",
              "fwd_min_5d", "fwd_min_10d", "fwd_min_20d"]].to_csv(
            RESULT_DIR / "B_quadrants.csv", index=False)
        print(f"\nSaved CSVs to {RESULT_DIR}")


if __name__ == "__main__":
    main()

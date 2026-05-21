"""
H094 Phase 1 探索：早盤弱勢（10:30 守低位）→ 當日大長黑 的機率分佈
（H093 的反向對稱版）

觸發定義：pos_1030 = (close_1030 - morning_low) / (morning_high - morning_low) ≤ 門檻
大長黑定義：跌幅 (close_1345-open_0845)/open_0845 ≤ -thr  AND  收盤位於當日全幅下緣 ≤ 0.15
價格序列：連續合約 adj_close
重點：逐年分布，確認偏空 edge 不是單靠 2022 空頭年。
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"

SQL = """
WITH day_bars AS (
    SELECT timestamp::DATE AS d, timestamp::TIME AS t,
           adj_close, high+adjustment AS adj_high, low+adjustment AS adj_low,
           open+adjustment AS adj_open
    FROM ohlcv_1m
    WHERE symbol='TX' AND timestamp::TIME BETWEEN TIME '08:45' AND TIME '13:45'
)
SELECT d,
    arg_min(adj_open, t) AS open_0845,
    max(adj_high) FILTER (WHERE t<=TIME '10:30') AS morning_high,
    min(adj_low)  FILTER (WHERE t<=TIME '10:30') AS morning_low,
    arg_max(adj_close, t) FILTER (WHERE t<=TIME '10:30') AS close_1030,
    max(adj_high) AS day_high, min(adj_low) AS day_low,
    arg_max(adj_close, t) AS close_1345,
    count(*) AS n_bars
FROM day_bars GROUP BY d ORDER BY d
"""

with duckdb.connect(DB, read_only=True) as c:
    df = c.execute(SQL).df()

df = df[(df["n_bars"] >= 250) & (df["morning_high"] > df["morning_low"]) & (df["day_high"] > df["day_low"])].copy()
df["d"] = pd.to_datetime(df["d"])
df["pos_1030"] = (df["close_1030"] - df["morning_low"]) / (df["morning_high"] - df["morning_low"])
df["ret_day"] = (df["close_1345"] - df["open_0845"]) / df["open_0845"] * 100
df["close_pos_day"] = (df["close_1345"] - df["day_low"]) / (df["day_high"] - df["day_low"])

N = len(df)
print(f"=== 樣本 N={N}  範圍 {df['d'].min().date()} ~ {df['d'].max().date()} ===\n")

print("=== 日盤實體跌幅 ret_day(%) 分佈（所有日，左尾） ===")
print(df["ret_day"].describe(percentiles=[.05, .1, .15, .25, .5]).round(3).to_string())
print()

for thr in [0.6, 0.8, 1.0]:
    base = ((df["ret_day"] <= -thr) & (df["close_pos_day"] <= 0.15)).mean()
    print(f"無條件 base rate 大長黑 (ret<=-{thr}% & close_pos<=0.15): {base:.3%}  (N={N})")
print()

def bigblack(d, thr):
    return (d["ret_day"] <= -thr) & (d["close_pos_day"] <= 0.15)

THR = 0.8
df["bb"] = bigblack(df, THR)
base_rate = df["bb"].mean()

print(f"=== pos_1030 分桶 vs 大長黑機率（跌幅門檻={THR}%, 收低位<=0.15）base={base_rate:.3%} ===")
bins = [-0.01, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 1.01]
df["bucket"] = pd.cut(df["pos_1030"], bins)
g = df.groupby("bucket", observed=True).agg(
    n=("bb", "size"), bigblack_rate=("bb", "mean"),
    mean_ret=("ret_day", "mean"), median_ret=("ret_day", "median"))
g["lift_vs_base"] = g["bigblack_rate"] / base_rate
print(g.round(3).to_string())
print()

print("=== pos_1030 門檻掃描（≤門檻 → 大長黑機率, thr=0.8%）===")
rows = []
for p in [0.4, 0.3, 0.25, 0.2, 0.1]:
    sel = df[df["pos_1030"] <= p]
    n = len(sel)
    rate = sel["bb"].mean() if n else np.nan
    收紅 = (sel["ret_day"] > 0).mean() if n else np.nan
    大幅反彈 = (sel["ret_day"] >= 0.5).mean() if n else np.nan
    rows.append((p, n, rate, rate/base_rate if rate==rate else np.nan, sel["ret_day"].mean(), 收紅, 大幅反彈))
scan = pd.DataFrame(rows, columns=["pos<=","N","bigblack_rate","lift","mean_ret%","收紅率","反彈>=0.5%率"])
print(scan.round(3).to_string(index=False))
print()

print("=== 觸發樣本 (pos_1030<=0.25) 的當日 ret_day(%) 分佈 ===")
trig = df[df["pos_1030"] <= 0.25]
print(f"N={len(trig)}")
print(trig["ret_day"].describe(percentiles=[.1,.25,.5,.75,.9]).round(3).to_string())
print()

print("=== 逐年（重點：edge 是否單靠 2022 空頭年） pos<=0.25 ===")
trig = trig.copy(); trig["year"] = trig["d"].dt.year
for y, gy in trig.groupby("year"):
    print(f"  {y}: N={len(gy):3d}  大長黑率={gy['bb'].mean():.1%}  中位ret={gy['ret_day'].median():+.3f}%  "
          f"平均ret={gy['ret_day'].mean():+.3f}%  收紅率={(gy['ret_day']>0).mean():.1%}")
print()

print("=== 不同跌幅門檻下的 lift（pos<=0.25 vs base）===")
for thr in [0.6, 0.8, 1.0]:
    b = bigblack(df, thr).mean(); t = bigblack(trig, thr).mean()
    print(f"thr={thr}%: base={b:.3%}  觸發後={t:.3%}  lift={t/b:.2f}x")

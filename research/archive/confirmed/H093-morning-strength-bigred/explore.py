"""
H093 Phase 1 探索：早盤強勢（10:30 收高位）→ 當日大長紅 的機率分佈

觸發定義：pos_1030 = (close_1030 - morning_low) / (morning_high - morning_low) ≥ 門檻
大長紅定義：漲幅 (close_1345-open_0845)/open_0845 ≥ thr  AND  收盤位於當日全幅上緣 ≥ 0.85
價格序列：連續合約 adj_close（adjustment 為當日常數，intraday 比值不受影響，但仍一致採用）
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"

# 以日盤 1 分K 聚合出每日所需欄位
SQL = """
WITH day_bars AS (
    SELECT
        timestamp::DATE AS d,
        timestamp::TIME AS t,
        adj_close,
        high + adjustment AS adj_high,
        low  + adjustment AS adj_low,
        open + adjustment AS adj_open
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::TIME BETWEEN TIME '08:45' AND TIME '13:45'
)
SELECT
    d,
    -- 開盤
    arg_min(adj_open, t) AS open_0845,
    -- 早盤區間 08:45~10:30
    max(adj_high) FILTER (WHERE t <= TIME '10:30') AS morning_high,
    min(adj_low)  FILTER (WHERE t <= TIME '10:30') AS morning_low,
    -- 10:30 收盤（取 <=10:30 的最後一根）
    arg_max(adj_close, t) FILTER (WHERE t <= TIME '10:30') AS close_1030,
    -- 當日全幅 08:45~13:45
    max(adj_high) AS day_high,
    min(adj_low)  AS day_low,
    -- 13:45 收盤
    arg_max(adj_close, t) AS close_1345,
    count(*) AS n_bars
FROM day_bars
GROUP BY d
ORDER BY d
"""

with duckdb.connect(DB, read_only=True) as c:
    df = c.execute(SQL).df()

# 基本清理：需有完整日盤、區間不退化
df = df[df["n_bars"] >= 250].copy()  # 完整日盤約 301 根
df = df[df["morning_high"] > df["morning_low"]]
df = df[df["day_high"] > df["day_low"]]

# 衍生欄位
df["pos_1030"] = (df["close_1030"] - df["morning_low"]) / (df["morning_high"] - df["morning_low"])
df["ret_day"] = (df["close_1345"] - df["open_0845"]) / df["open_0845"] * 100  # %
df["close_pos_day"] = (df["close_1345"] - df["day_low"]) / (df["day_high"] - df["day_low"])

N = len(df)
print(f"=== 樣本 ===")
print(f"總交易日 N={N}  範圍 {df['d'].min()} ~ {df['d'].max()}")
print()

# --- 先看日盤漲幅分佈，決定「大長紅」漲幅門檻 ---
print("=== 日盤實體漲幅 ret_day(%) 分佈（所有日） ===")
print(df["ret_day"].describe(percentiles=[.5, .75, .85, .9, .95]).round(3).to_string())
print()

# 候選漲幅門檻
for thr in [0.6, 0.8, 1.0]:
    base = ((df["ret_day"] >= thr) & (df["close_pos_day"] >= 0.85)).mean()
    print(f"無條件 base rate 大長紅 (ret>={thr}% & close_pos>=0.85): {base:.3%}  (N={N})")
print()

def bigred(d, thr):
    return (d["ret_day"] >= thr) & (d["close_pos_day"] >= 0.85)

# --- 主分析：pos_1030 分桶 vs 大長紅機率 ---
print("=== pos_1030 分桶 vs 大長紅機率（漲幅門檻=0.8%, 收高位>=0.85） ===")
THR = 0.8
df["br"] = bigred(df, THR)
base_rate = df["br"].mean()
bins = [-np.inf, 0.3, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.01]
df["bucket"] = pd.cut(df["pos_1030"], bins)
g = df.groupby("bucket", observed=True).agg(
    n=("br", "size"),
    bigred_rate=("br", "mean"),
    mean_ret=("ret_day", "mean"),
    median_ret=("ret_day", "median"),
)
g["lift_vs_base"] = g["bigred_rate"] / base_rate
print(f"base rate = {base_rate:.3%}")
print(g.round(3).to_string())
print()

# --- 觸發門檻掃描 ---
print("=== pos_1030 門檻掃描（≥門檻 → 大長紅機率, thr=0.8%） ===")
rows = []
for p in [0.6, 0.7, 0.75, 0.8, 0.85, 0.9]:
    sel = df[df["pos_1030"] >= p]
    n = len(sel)
    rate = sel["br"].mean() if n else np.nan
    # 尾端風險：觸發後收黑 / 大幅回吐
    收黑 = (sel["ret_day"] < 0).mean() if n else np.nan
    大幅回吐 = (sel["ret_day"] <= -0.5).mean() if n else np.nan
    rows.append((p, n, rate, rate / base_rate if rate==rate else np.nan, sel["ret_day"].mean(), 收黑, 大幅回吐))
scan = pd.DataFrame(rows, columns=["pos>=","N","bigred_rate","lift","mean_ret%","收黑率","回吐<=-0.5%率"])
print(scan.round(3).to_string(index=False))
print()

# --- 觸發樣本（pos>=0.75）後的當日報酬分佈 ---
print("=== 觸發樣本 (pos_1030>=0.75) 的當日 ret_day(%) 分佈 ===")
trig = df[df["pos_1030"] >= 0.75]
print(f"N={len(trig)}")
print(trig["ret_day"].describe(percentiles=[.1,.25,.5,.75,.9]).round(3).to_string())
print()

# --- 不同漲幅門檻下的 lift（pos>=0.75 觸發） ---
print("=== 觸發(pos>=0.75) vs base：不同漲幅門檻 ===")
for thr in [0.6, 0.8, 1.0]:
    b = bigred(df, thr).mean()
    t = bigred(trig, thr).mean()
    print(f"thr={thr}%: base={b:.3%}  觸發後={t:.3%}  lift={t/b:.2f}x")

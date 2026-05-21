"""
H094 Phase 2 回測：早盤守低位 → 進空單

進場：10:30 確認 pos_1030 <= 門檻，以 close_1030 放空（無 lookahead）
出場：13:45 收盤回補
方向：short only
績效：損益% = (entry - exit)/entry * 100（做空，跌則賺；跨年度可比）
成本：net 3 點/round-trip（同 H093）
重點：逐年 walk-forward，確認 edge 非單靠 2022 空頭年

IS = 2021-01 ~ 2024-12；OOS = 2025-01 ~ 2026-05
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
COST_PTS = 3.0
IS_END = pd.Timestamp("2024-12-31")
THRESHOLDS = [0.40, 0.30, 0.25, 0.20, 0.10]

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
    arg_max(adj_close, t) AS close_1345,
    count(*) AS n_bars
FROM day_bars GROUP BY d ORDER BY d
"""

with duckdb.connect(DB, read_only=True) as c:
    df = c.execute(SQL).df()

df = df[(df["n_bars"] >= 250) & (df["morning_high"] > df["morning_low"])].copy()
df["d"] = pd.to_datetime(df["d"])
df["pos_1030"] = (df["close_1030"] - df["morning_low"]) / (df["morning_high"] - df["morning_low"])
# 做空損益%（gross）：(entry - exit)/entry。跌 → 正報酬
df["pnl_gross"] = (df["close_1030"] - df["close_1345"]) / df["close_1030"] * 100
df["cost_pct"] = COST_PTS / df["close_1030"] * 100
df["pnl_net"] = df["pnl_gross"] - df["cost_pct"]


def stats(trades, col="pnl_net"):
    r = trades[col].values
    n = len(r)
    if n == 0:
        return dict(N=0)
    eq = np.cumsum(r); mdd = (np.maximum.accumulate(eq) - eq).max()
    gw, gl = r[r > 0].sum(), -r[r < 0].sum()
    sh = r.mean()/r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    span = (trades["d"].max()-trades["d"].min()).days/365.25
    return dict(N=n, win_rate=(r>0).mean(), mean=r.mean(), median=np.median(r),
                total=r.sum(), sharpe=sh,
                sharpe_ann=sh*np.sqrt(n/span) if n > 1 and span > 0 else np.nan,
                max_dd=mdd, pf=gw/gl if gl > 0 else np.inf)


def fmt(s):
    if s.get("N", 0) == 0:
        return "N=0"
    return (f"N={s['N']:4d}  勝率={s['win_rate']:.1%}  平均={s['mean']:+.3f}%  "
            f"中位={s['median']:+.3f}%  總={s['total']:+.1f}%  Sharpe={s['sharpe']:.3f}  "
            f"年化≈{s['sharpe_ann']:.2f}  MDD={s['max_dd']:.1f}%  PF={s['pf']:.2f}")


print(f"=== H094 Phase 2 做空回測（成本={COST_PTS}點/round-trip）===")
print(f"全期 {df['d'].min().date()} ~ {df['d'].max().date()}  全交易日 N={len(df)}")
print(f"IS(<= {IS_END.date()})  OOS(>)\n")

print("=== 門檻掃描（net）：IS / OOS 一致性 ===")
for thr in THRESHOLDS:
    sel = df[df["pos_1030"] <= thr]
    print(f"\npos<={thr:.2f}")
    print(f"  IS : {fmt(stats(sel[sel['d']<=IS_END]))}")
    print(f"  OOS: {fmt(stats(sel[sel['d']>IS_END]))}")

print("\n=== 選定 pos<=0.25：gross vs net（全期）===")
sel = df[df["pos_1030"] <= 0.25]
print(f"  gross: {fmt(stats(sel, 'pnl_gross'))}")
print(f"  net  : {fmt(stats(sel, 'pnl_net'))}")

print("\n=== ★ Walk-forward 逐年（pos<=0.25, net）：edge 是否非單靠 2022 ===")
sel = sel.copy(); sel["year"] = sel["d"].dt.year
for y, g in sel.groupby("year"):
    print(f"  {y}: {fmt(stats(g))}")

print("\n=== 對照：每天都放空 10:30->13:45（net）===")
print(f"  全體: {fmt(stats(df, 'pnl_net'))}")

print("\n=== 極端門檻 pos<=0.10（net）逐年 ===")
sel10 = df[df["pos_1030"] <= 0.10].copy(); sel10["year"] = sel10["d"].dt.year
print(f"  全期: {fmt(stats(sel10))}")
for y, g in sel10.groupby("year"):
    print(f"  {y}: {fmt(stats(g))}")

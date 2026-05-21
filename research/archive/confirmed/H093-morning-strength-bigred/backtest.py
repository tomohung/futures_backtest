"""
H093 Phase 2 回測：早盤守高位 → 進多單

進場：10:30 確認 pos_1030 >= 門檻，以 close_1030 進多單（無 lookahead，10:30 即可決策）
出場：13:45 收盤平倉（最單純版本）
方向：long only
績效：損益% = (exit - entry)/entry * 100（跨年度可比，CLAUDE.md 慣例）
成本：以點數扣除 round-trip（滑價+手續費+稅），TX 約 3 點；同時報 gross / net

IS = 2021-01 ~ 2024-12；OOS = 2025-01 ~ 2026-05
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
COST_PTS = 3.0          # round-trip 成本（點），TX 約 3 點（滑價~2 + 手續費稅~1）
IS_END = "2024-12-31"   # in-sample 結束
THRESHOLDS = [0.60, 0.70, 0.75, 0.80, 0.85, 0.90]

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
# 多單損益%（gross）與 net（扣成本，成本以進場價換算成%）
df["pnl_gross"] = (df["close_1345"] - df["close_1030"]) / df["close_1030"] * 100
df["cost_pct"] = COST_PTS / df["close_1030"] * 100
df["pnl_net"] = df["pnl_gross"] - df["cost_pct"]

is_mask = df["d"] <= IS_END
oos_mask = ~is_mask


def stats(trades, col="pnl_net"):
    r = trades[col].values
    n = len(r)
    if n == 0:
        return dict(N=0)
    wins = r > 0
    gross_win = r[r > 0].sum()
    gross_loss = -r[r < 0].sum()
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    mdd = (peak - eq).max()
    sharpe = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    return dict(
        N=n,
        win_rate=wins.mean(),
        mean=r.mean(),
        median=np.median(r),
        total=r.sum(),
        sharpe=sharpe,                       # per-trade Sharpe（損益%）
        sharpe_ann=sharpe * np.sqrt(n / ((trades["d"].max()-trades["d"].min()).days/365.25)) if n > 1 else np.nan,
        max_dd=mdd,
        pf=gross_win / gross_loss if gross_loss > 0 else np.inf,
    )


def fmt(s):
    if s.get("N", 0) == 0:
        return "N=0"
    return (f"N={s['N']:4d}  勝率={s['win_rate']:.1%}  平均={s['mean']:+.3f}%  "
            f"中位={s['median']:+.3f}%  總計={s['total']:+.1f}%  "
            f"Sharpe(per-trade)={s['sharpe']:.3f}  年化≈{s['sharpe_ann']:.2f}  "
            f"MDD={s['max_dd']:.1f}%  PF={s['pf']:.2f}")


print(f"=== H093 Phase 2 回測（成本={COST_PTS}點/round-trip）===")
print(f"全期 {df['d'].min().date()} ~ {df['d'].max().date()}  全交易日 N={len(df)}")
print(f"IS(<= {IS_END})={is_mask.sum()}天  OOS={oos_mask.sum()}天\n")

# --- 進場門檻掃描（net）：IS vs OOS ---
print("=== 門檻掃描（net 損益%）：IS / OOS 一致性 ===")
for thr in THRESHOLDS:
    sel = df[df["pos_1030"] >= thr]
    s_is = stats(sel[sel["d"] <= IS_END])
    s_oos = stats(sel[sel["d"] > IS_END])
    print(f"\npos>={thr:.2f}")
    print(f"  IS : {fmt(s_is)}")
    print(f"  OOS: {fmt(s_oos)}")

# --- 選定門檻 0.75：gross vs net 全期 ---
print("\n=== 選定 pos>=0.75：gross vs net（全期）===")
sel = df[df["pos_1030"] >= 0.75]
print(f"  gross: {fmt(stats(sel, 'pnl_gross'))}")
print(f"  net  : {fmt(stats(sel, 'pnl_net'))}")

# --- Walk-forward：逐年（pos>=0.75, net）---
print("\n=== Walk-forward 逐年（pos>=0.75, net）===")
sel = sel.copy()
sel["year"] = sel["d"].dt.year
for y, g in sel.groupby("year"):
    print(f"  {y}: {fmt(stats(g))}")

# --- 對照：不交易（全體日的多單 buy&hold 10:30->13:45）---
print("\n=== 對照基準：每天都做多 10:30->13:45（net）===")
print(f"  全體: {fmt(stats(df, 'pnl_net'))}")

"""
H093 衍生：把判斷界線時間從 10:30 提早到 10:00，比較
  (a) Phase 1 機率 lift  (b) Phase 2 多單回測（10:00 進、13:45 出, net 3點）
其餘定義不變。10:00 vs 10:30 並列對照。
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
COST_PTS = 3.0
IS_END = pd.Timestamp("2024-12-31")


def load(cutoff: str):
    sql = f"""
    WITH day_bars AS (
        SELECT timestamp::DATE AS d, timestamp::TIME AS t,
               adj_close, high+adjustment AS adj_high, low+adjustment AS adj_low,
               open+adjustment AS adj_open
        FROM ohlcv_1m
        WHERE symbol='TX' AND timestamp::TIME BETWEEN TIME '08:45' AND TIME '13:45'
    )
    SELECT d,
        arg_min(adj_open, t) AS open_0845,
        max(adj_high) FILTER (WHERE t<=TIME '{cutoff}') AS m_high,
        min(adj_low)  FILTER (WHERE t<=TIME '{cutoff}') AS m_low,
        arg_max(adj_close, t) FILTER (WHERE t<=TIME '{cutoff}') AS close_cut,
        max(adj_high) AS day_high, min(adj_low) AS day_low,
        arg_max(adj_close, t) AS close_1345,
        count(*) AS n_bars
    FROM day_bars GROUP BY d ORDER BY d
    """
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(sql).df()
    df = df[(df["n_bars"] >= 250) & (df["m_high"] > df["m_low"]) & (df["day_high"] > df["day_low"])].copy()
    df["d"] = pd.to_datetime(df["d"])
    df["pos"] = (df["close_cut"] - df["m_low"]) / (df["m_high"] - df["m_low"])
    df["ret_day"] = (df["close_1345"] - df["open_0845"]) / df["open_0845"] * 100
    df["close_pos_day"] = (df["close_1345"] - df["day_low"]) / (df["day_high"] - df["day_low"])
    # 多單損益（進場價=cutoff 收盤）
    df["pnl_gross"] = (df["close_1345"] - df["close_cut"]) / df["close_cut"] * 100
    df["pnl_net"] = df["pnl_gross"] - COST_PTS / df["close_cut"] * 100
    return df


def bt_stats(t, col="pnl_net"):
    r = t[col].values
    n = len(r)
    if n == 0:
        return "N=0"
    eq = np.cumsum(r); mdd = (np.maximum.accumulate(eq) - eq).max()
    gw = r[r > 0].sum(); gl = -r[r < 0].sum()
    sh = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    return (f"N={n:4d} 勝率={(r>0).mean():.1%} 平均={r.mean():+.3f}% 總={r.sum():+.1f}% "
            f"Sharpe={sh:.3f} MDD={mdd:.1f}% PF={gw/gl if gl>0 else np.inf:.2f}")


for cutoff in ["10:00", "10:30"]:
    df = load(cutoff)
    N = len(df)
    print(f"\n{'='*70}\n界線時間 = {cutoff}   全交易日 N={N}   範圍 {df['d'].min().date()}~{df['d'].max().date()}")
    # Phase 1: 大長紅機率 lift（thr=0.8%, close_pos>=0.85）
    THR = 0.8
    df["br"] = (df["ret_day"] >= THR) & (df["close_pos_day"] >= 0.85)
    base = df["br"].mean()
    print(f"-- Phase1 大長紅 base rate = {base:.2%}")
    for p in [0.75, 0.85, 0.90]:
        sel = df[df["pos"] >= p]
        print(f"   pos>={p}: N={len(sel):4d} 大長紅={sel['br'].mean():.2%} lift={sel['br'].mean()/base:.2f}x "
              f"收黑率={(sel['ret_day']<0).mean():.1%}")
    # Phase 2: 多單回測 IS/OOS
    print(f"-- Phase2 多單（{cutoff}進→13:45出, net 3點）IS/OOS")
    for p in [0.70, 0.75, 0.80, 0.85, 0.90]:
        sel = df[df["pos"] >= p]
        print(f"   pos>={p}")
        print(f"      IS : {bt_stats(sel[sel['d']<=IS_END])}")
        print(f"      OOS: {bt_stats(sel[sel['d']>IS_END])}")

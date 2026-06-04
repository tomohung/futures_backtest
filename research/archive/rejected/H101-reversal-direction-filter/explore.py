"""H101 Phase 1 — 方向濾網判定差異與覆蓋率

比較四種 reversal 方向濾網，在進場窗 09:10–10:05 的每日方向判定：
  base : 5m 120MA 斜率（只日盤 08:45–13:45）          ← 現行 live
  A    : 5m 240MA 斜率（=1H 20MA，連續日+夜盤）
  B    : 1H MACD 12/26/9，MACD 線 vs Signal 線（連續日+夜盤）
  C    : A 且 B 同向

方向編碼：+1 bullish, -1 bearish, 0 undefined(NaN)

GATE：新濾網 vs base 歧異率 > 15% 且 C 允許交易天數 ≥ 80。
所有指標皆 shift 避免未來函數（與 runner.py 既有處理一致）。
"""
import duckdb
import numpy as np
import pandas as pd
from datetime import time as dtime

DB = "data/futures.duckdb"
ENTRY_START = dtime(9, 10)
ENTRY_END   = dtime(10, 5)


def load():
    with duckdb.connect(DB, read_only=True) as c:
        df_all = c.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol='TX' ORDER BY timestamp
        """).df().set_index("timestamp")
    return df_all


def main():
    df_all = load()
    # day-session 1m index (08:45–13:45)
    t = df_all.index.time
    day_mask = (t >= dtime(8, 45)) & (t <= dtime(13, 45))
    df_day = df_all.loc[day_mask].copy()

    # ── base: 5m 120MA slope, day-session only (replicates runner.py:521-524)
    s5_day = df_day["close"].resample("5min").last().dropna()
    ma120  = s5_day.rolling(120, min_periods=120).mean()
    base_ma      = ma120.shift(1).reindex(df_day.index, method="ffill")
    base_ma_prev = ma120.shift(2).reindex(df_day.index, method="ffill")
    base_dir = np.sign(base_ma - base_ma_prev)

    # ── A: 5m 240MA slope, continuous day+night
    s5_all = df_all["close"].resample("5min").last().dropna()
    ma240  = s5_all.rolling(240, min_periods=240).mean()
    a_ma      = ma240.shift(1).reindex(df_day.index, method="ffill")
    a_ma_prev = ma240.shift(2).reindex(df_day.index, method="ffill")
    a_dir = np.sign(a_ma - a_ma_prev)

    # ── B: 1H MACD 12/26/9, continuous day+night, MACD line vs Signal line
    s1h = df_all["close"].resample("1h").last().dropna()
    ema12 = s1h.ewm(span=12, adjust=False).mean()
    ema26 = s1h.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_s   = macd.shift(1).reindex(df_day.index, method="ffill")
    signal_s = signal.shift(1).reindex(df_day.index, method="ffill")
    b_dir = np.sign(macd_s - signal_s)

    # ── assemble per-bar frame
    f = pd.DataFrame({
        "base": base_dir, "A": a_dir, "B": b_dir,
    }, index=df_day.index)
    f["date"] = f.index.date
    f["time"] = f.index.time

    # ── sample one direction per trading day at the entry window
    win = f[(f["time"] >= ENTRY_START) & (f["time"] <= ENTRY_END)]
    # take the first bar of the window (09:10) per day
    daily = win.groupby("date").first()

    # also: does direction flip within window? (stability)
    def flips(g):
        return pd.Series({
            "base_flip": g["base"].nunique(dropna=True) > 1,
            "A_flip":    g["A"].nunique(dropna=True) > 1,
            "B_flip":    g["B"].nunique(dropna=True) > 1,
        })
    flip = win.groupby("date").apply(flips, include_groups=False)
    daily = daily.join(flip)

    N = len(daily)
    print(f"=== H101 Phase 1 方向濾網差異 ===")
    print(f"交易日總數 N = {N}  範圍 {daily.index.min()} ~ {daily.index.max()}\n")

    def defined(col):
        return daily[col].notna() & (daily[col] != 0)

    # coverage: each filter yields a usable (non-zero) direction
    print("── 各濾網可用方向覆蓋率（非 NaN/0） ──")
    for col in ["base", "A", "B"]:
        d = defined(col).sum()
        print(f"  {col:>4}: {d:>4}/{N}  ({d/N*100:5.1f}%)")
    print()

    # divergence vs base (only on days where both defined)
    print("── 新濾網 vs base 方向歧異率（兩者皆有方向的交易日上） ──")
    for col in ["A", "B"]:
        both = defined("base") & defined(col)
        nb = both.sum()
        diff = (daily.loc[both, col] != daily.loc[both, "base"]).sum()
        print(f"  base vs {col}: 共同有方向 {nb} 日，歧異 {diff} 日 = {diff/nb*100:5.1f}%")
    print()

    # A vs B agreement → C coverage
    bothAB = defined("A") & defined("B")
    nab = bothAB.sum()
    agree = (daily.loc[bothAB, "A"] == daily.loc[bothAB, "B"]).sum()
    print("── 情境 C：A 與 B 同向 ──")
    print(f"  A、B 皆有方向: {nab} 日")
    print(f"  同向(=C 允許交易): {agree} 日 ({agree/nab*100:5.1f}% of {nab})")
    print(f"  逆向(C 過濾掉): {nab-agree} 日")
    print()

    # C vs base divergence: C's direction (when agree) vs base
    cmask = bothAB & (daily["A"] == daily["B"]) & defined("base")
    nc = cmask.sum()
    cdiff = (daily.loc[cmask, "A"] != daily.loc[cmask, "base"]).sum()
    print(f"  C(同向日) vs base 歧異: {cdiff}/{nc} = {cdiff/nc*100:5.1f}%")
    print()

    # direction balance
    print("── 方向多空比（有方向日中 bullish 占比） ──")
    for col in ["base", "A", "B"]:
        d = daily.loc[defined(col), col]
        print(f"  {col:>4}: bullish {(d>0).sum()}  bearish {(d<0).sum()}  bull%={(d>0).mean()*100:5.1f}%")
    print()

    # within-window flip rate (instability)
    print("── 進場窗內方向翻轉率（09:10–10:05 期間方向改變過） ──")
    for col in ["base", "A", "B"]:
        fr = daily[f"{col}_flip"].mean()
        print(f"  {col:>4}: {daily[f'{col}_flip'].sum()}/{N} = {fr*100:5.1f}%")

    # save per-day table
    out = daily[["base", "A", "B"]].copy()
    out.to_csv("research/active/H101-reversal-direction-filter/results/daily_directions.csv")
    print("\n[saved] results/daily_directions.csv")


if __name__ == "__main__":
    main()

"""H093 — 碰 L2 的時間是否影響後續觸及 L3 的機率？

背景：chart-ui 右側欄『當日觸及』提示目前只用「碰 L1 的時間」查 _CONT_L3 表決定瞄第幾階
（src/chart_ui/services/daystats.py）。L3 必經 L2，「已碰 L2」是比「已碰 L1」更接近 L3 的
狀態，理應更有預測力。本腳本沿用 daystats 的方法論驗證之。

方法論（對齊 daystats）：
- 商品 TX 日盤 08:45–13:45，pooled 2020–2026，多空對稱。
- 關卡距離：rng = a×夜盤振幅 + b×EMA20(日盤振幅)，係數同 LVL_QUANTILES：
    L1=(0.159,0.440) L2=(0.157,0.637) L3=(0.274,0.671)
- 夜盤振幅 night_range(D)：前夜 15:00 → D 05:00 的 max(high)-min(low)（同 _night_range / _full_ranges 歸屬）。
- EMA20：D 之前（不含當日）日盤振幅的 EMA(20)，causal、adjust=False（同 _ema20_range）。
- 擺動定義（同 _level1_signals）：
    上擺(bull) = max(high - running_low)；下擺(bear) = max(running_high - low)，逐分鐘累積。
    首次達到某階距離的分鐘 = 該階觸及時間。
- 條件機率：在「該方向有碰到 L2」的樣本中，依 L2 首觸時間分桶，算後續（同日、L2 之後）也碰到 L3 的比例。
- 對照：現行 _CONT_L3（以 L1 首觸時間為條件）。

輸出：兩張 step-function 表 + 基準率 + L2 時間 vs L1 時間的對照。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
SYMBOL = "TX"
LEVELS = {"L1": (0.159, 0.440), "L2": (0.157, 0.637), "L3": (0.274, 0.671)}
# 與 daystats 一致的時間桶（08:45=525 起，每 15 分鐘一格）
BUCKETS = [525, 540, 555, 570, 585, 600, 615, 630, 645]
BUCKET_LBL = {525: "08:45", 540: "09:00", 555: "09:15", 570: "09:30", 585: "09:45",
              600: "10:00", 615: "10:15", 630: "10:30", 645: "10:45"}


def load_day_bars(conn) -> pd.DataFrame:
    df = conn.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low "
        "FROM ohlcv_1m WHERE symbol = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) >= DATE '2020-01-01' ORDER BY timestamp",
        [SYMBOL],
    ).df()
    df["d"] = pd.to_datetime(df["d"])
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    # 分鐘數（當日 08:45=525）
    tt = pd.to_datetime(df["t"].astype(str))
    df["min"] = tt.dt.hour * 60 + tt.dt.minute
    return df


def night_range_by_session(conn) -> pd.Series:
    """每個 session_day 的前夜振幅，對齊 daystats._full_ranges 的歸屬。"""
    sql = """
    WITH td AS (
      SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    ),
    night_dates AS (
      SELECT DISTINCT CAST(timestamp AS DATE) nd FROM ohlcv_1m
      WHERE symbol = ? AND CAST(timestamp AS TIME) >= TIME '15:00:00'
    ),
    night_map AS (
      SELECT nd, (SELECT min(d) FROM td WHERE d > nd) AS session_day FROM night_dates
    ),
    assigned AS (
      SELECT b.high, b.low,
        CASE WHEN CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             THEN nm.session_day ELSE CAST(b.timestamp AS DATE) END AS session_day
      FROM ohlcv_1m b
      LEFT JOIN night_map nm ON nm.nd = CAST(b.timestamp AS DATE)
      WHERE b.symbol = ?
        AND (CAST(b.timestamp AS TIME) >= TIME '15:00:00'
             OR CAST(b.timestamp AS TIME) <= TIME '05:00:00')
    )
    SELECT session_day d, MAX(high) - MIN(low) night_range
    FROM assigned WHERE session_day IS NOT NULL GROUP BY 1
    """
    df = conn.execute(sql, [SYMBOL, SYMBOL, SYMBOL]).df()
    df["d"] = pd.to_datetime(df["d"])
    return df.set_index("d")["night_range"].astype(float)


def first_touch_minutes(g: pd.DataFrame, dists: dict) -> dict:
    """回傳 {('bull'|'bear', level): 首觸分鐘 or None}。"""
    highs = g["high"].to_numpy()
    lows = g["low"].to_numpy()
    mins = g["min"].to_numpy()
    run_lo = np.minimum.accumulate(lows)
    run_hi = np.maximum.accumulate(highs)
    up = np.maximum.accumulate(highs - run_lo)   # 上擺累積最大
    dn = np.maximum.accumulate(run_hi - lows)    # 下擺累積最大
    out = {}
    for lvl, dist in dists.items():
        iu = np.argmax(up >= dist) if (up >= dist).any() else None
        idd = np.argmax(dn >= dist) if (dn >= dist).any() else None
        out[("bull", lvl)] = int(mins[iu]) if iu is not None else None
        out[("bear", lvl)] = int(mins[idd]) if idd is not None else None
    return out


def bucket_of(minute: int) -> int:
    b = BUCKETS[0]
    for s in BUCKETS:
        if minute >= s:
            b = s
        else:
            break
    return b


def main():
    with duckdb.connect(DB, read_only=True) as conn:
        bars = load_day_bars(conn)
        night = night_range_by_session(conn)

    # 每日日盤振幅 + causal EMA20
    day_rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min())
    day_rng = day_rng.sort_index()
    ema20 = day_rng.shift(1).ewm(span=20, adjust=False).mean()  # 不含當日

    records = []  # 每筆 = 一個 (day, direction)
    for d, g in bars.groupby("d"):
        nr = night.get(d)
        e20 = ema20.get(d)
        if nr is None or pd.isna(nr) or e20 is None or pd.isna(e20):
            continue
        dists = {lvl: a * nr + b * e20 for lvl, (a, b) in LEVELS.items()}
        ft = first_touch_minutes(g, dists)
        for direction in ("bull", "bear"):
            records.append({
                "d": d, "dir": direction,
                "L1": ft[(direction, "L1")],
                "L2": ft[(direction, "L2")],
                "L3": ft[(direction, "L3")],
            })
    R = pd.DataFrame(records)
    n_total = len(R)
    print(f"樣本：{n_total} 個 (交易日 × 方向)，期間 {R['d'].min().date()} ~ {R['d'].max().date()}")
    print(f"  其中碰到 L1：{R['L1'].notna().sum()} ({R['L1'].notna().mean():.0%})")
    print(f"  其中碰到 L2：{R['L2'].notna().sum()} ({R['L2'].notna().mean():.0%})")
    print(f"  其中碰到 L3：{R['L3'].notna().sum()} ({R['L3'].notna().mean():.0%})")

    # 健全性檢查：L3 必經 L2、L2 必經 L1（時間順序）
    touched_l3 = R[R["L3"].notna()]
    viol = ((touched_l3["L2"].isna()) | (touched_l3["L2"] > touched_l3["L3"])).sum()
    print(f"  L3 觸及但 L2 缺/晚於 L3 的筆數（應為 0）：{viol}")

    print("\n=== 基準率 ===")
    base_l3_given_l2 = R[R["L2"].notna()]["L3"].notna().mean()
    base_l3_given_l1 = R[R["L1"].notna()]["L3"].notna().mean()
    print(f"  P(L3 | 已碰 L2) 無條件 = {base_l3_given_l2:.0%}  (n={R['L2'].notna().sum()})")
    print(f"  P(L3 | 已碰 L1) 無條件 = {base_l3_given_l1:.0%}  (n={R['L1'].notna().sum()})")

    def step_table(time_col: str) -> pd.DataFrame:
        sub = R[R[time_col].notna()].copy()
        sub["bkt"] = sub[time_col].apply(bucket_of)
        rows = []
        for b in BUCKETS:
            s = sub[sub["bkt"] == b]
            if len(s) == 0:
                rows.append((b, BUCKET_LBL[b], None, 0))
                continue
            p = s["L3"].notna().mean()
            rows.append((b, BUCKET_LBL[b], round(p * 100), len(s)))
        return pd.DataFrame(rows, columns=["min", "time", "P(L3)%", "n"])

    print("\n=== [新] 以『碰 L2 時間』為條件 → 後續觸及 L3 機率 ===")
    t_l2 = step_table("L2")
    print(t_l2.to_string(index=False))

    print("\n=== [現行對照] 以『碰 L1 時間』為條件 → 觸及 L3 機率（重建 _CONT_L3）===")
    t_l1 = step_table("L1")
    print(t_l1.to_string(index=False))
    print("\n  現行 daystats._CONT_L3 = [(525,69),(540,58),(555,59),(570,56),"
          "(585,41),(600,44),(615,43),(630,39),(645,28)]")

    # 對照：同一桶的 L2-conditioned vs L1-conditioned 提升幅度
    print("\n=== 同時間桶：P(L3|碰L2) − P(L3|碰L1) 提升 ===")
    merged = t_l2.merge(t_l1, on=["min", "time"], suffixes=("_L2", "_L1"))
    merged["lift(pp)"] = merged["P(L3)%_L2"] - merged["P(L3)%_L1"]
    print(merged[["time", "P(L3)%_L2", "n_L2", "P(L3)%_L1", "n_L1", "lift(pp)"]].to_string(index=False))

    # 存 CSV 供覆查
    out = R.copy()
    out["d"] = out["d"].dt.date
    out.to_csv("research/active/H093-l2-touch-time-l3-reach/touches.csv", index=False)
    print("\n明細存 research/active/H093-l2-touch-time-l3-reach/touches.csv")


if __name__ == "__main__":
    main()

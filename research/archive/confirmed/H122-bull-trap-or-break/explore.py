"""
H122 — Bull-Trap OR Break：Phase 1 分佈探索

事件定義
  成本條件(AND)：session_open(08:45 第一根 open) > 昨日日盤VWAP 且 > 前日日盤VWAP
  OR            ：08:45–08:57 high/low
  向下突破事件   ：08:58–09:15 之間存在某根 close < OR low（取首次觸發時間）

Ladder（running-high anchored，往下，沿用 H092 空頭定義）
  錨點 = 當日 running high；達成 = 某時點 low ≤ running_high − m×EmaHL
  等價：max_decline = max_t(running_high(t) − low(t)) ≥ m×EmaHL
  m: L1=0.385 L2=0.497 L3=0.711 L4=0.977 L5=1.30(暫定)
  EmaHL = 前一日為止的 EMA20(日盤 H-L range)，時間窗 08:45–13:45

對照組
  (A) 全體交易日無條件下行 reach（空頭 baseline）
  (B) 早盤破 OR low 但開盤「不在成本之上」的日子（隔離 VWAP 條件增量）
  event = 破 OR low 且 開盤在成本之上

虛無檢定：event 的 Lk 達成率 vs 從「破 OR low 全體日」隨機抽同樣本數的分佈
"""
import duckdb
import numpy as np
import pandas as pd
from datetime import time as dtime

DB = "data/futures.duckdb"
SYM = "TX"
OR_END = dtime(8, 57)      # OR 8:45–8:57
ENTRY_START = dtime(8, 58)  # 進場窗
ENTRY_END = dtime(9, 15)
SESS_START = dtime(8, 45)
SESS_END = dtime(13, 45)
EMA_PERIOD = 20
WARMUP = 20

LADDER = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.30}


def load():
    con = duckdb.connect(DB, read_only=True)
    df = con.execute(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE symbol = ?
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        ORDER BY timestamp
        """,
        [SYM],
    ).df()
    con.close()
    df["date"] = df["timestamp"].dt.date
    df["t"] = df["timestamp"].dt.time
    return df


def per_day(df):
    """逐日特徵。回傳 DataFrame index=date。"""
    rows = []
    for d, g in df.groupby("date"):
        g = g.sort_values("timestamp")
        sess = g[(g["t"] >= SESS_START) & (g["t"] <= SESS_END)]
        if sess.empty:
            continue
        session_open = float(sess.iloc[0]["open"])
        vwap = float((sess["close"] * sess["volume"]).sum() / sess["volume"].sum())
        day_high = float(sess["high"].max())
        day_low = float(sess["low"].min())
        day_range = day_high - day_low

        orbars = sess[sess["t"] <= OR_END]
        or_high = float(orbars["high"].max())
        or_low = float(orbars["low"].min())

        # 向下突破事件：08:58–09:15 任一根 close < OR low
        ent = sess[(sess["t"] >= ENTRY_START) & (sess["t"] <= ENTRY_END)]
        brk = ent[ent["close"] < or_low]
        broke_down = not brk.empty
        brk_time = brk.iloc[0]["t"] if broke_down else None
        brk_close = float(brk.iloc[0]["close"]) if broke_down else np.nan

        # running-high anchored 最大下行回落（全日）
        rhigh = sess["high"].cummax()
        max_decline = float((rhigh - sess["low"]).max())

        rows.append(
            dict(date=d, session_open=session_open, vwap=vwap,
                 day_high=day_high, day_low=day_low, day_range=day_range,
                 or_high=or_high, or_low=or_low,
                 broke_down=broke_down, brk_time=brk_time, brk_close=brk_close,
                 max_decline=max_decline)
        )
    daily = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # EmaHL：前一日為止的 EMA20(day_range)
    alpha = 2.0 / (EMA_PERIOD + 1)
    ema = []
    cur = None
    for r in daily["day_range"]:
        ema.append(cur)               # 前一日為止的值（今天用）
        cur = r if cur is None else (r * alpha + cur * (1 - alpha))
    daily["EmaHL"] = ema

    # 昨日 / 前日 VWAP（按交易日位置）
    daily["vwap_t1"] = daily["vwap"].shift(1)
    daily["vwap_t2"] = daily["vwap"].shift(2)

    # 成本條件 AND
    daily["above_cost"] = (daily["session_open"] > daily["vwap_t1"]) & \
                          (daily["session_open"] > daily["vwap_t2"])

    # ladder 達成
    valid = daily["EmaHL"].notna() & (daily["EmaHL"] > 0)
    for k, m in LADDER.items():
        daily[k] = np.where(valid, daily["max_decline"] >= m * daily["EmaHL"], np.nan)
    daily["reach_ratio"] = np.where(valid, daily["max_decline"] / daily["EmaHL"], np.nan)
    daily["warm"] = valid & (daily.index >= WARMUP)
    return daily


def rate_table(sub, label):
    n = len(sub)
    line = {"group": label, "N": n}
    for k in LADDER:
        line[k] = round(100 * sub[k].mean(), 1) if n else np.nan
    line["median_reach"] = round(sub["reach_ratio"].median(), 3) if n else np.nan
    return line


def main():
    df = load()
    daily = per_day(df)
    d = daily[daily["warm"]].copy()  # 有 EmaHL + 過 warmup

    print(f"全體有效日(warm): N={len(d)}  "
          f"{d['date'].min()} ~ {d['date'].max()}")

    event = d[d["broke_down"] & d["above_cost"]]
    ctrl_b = d[d["broke_down"] & ~d["above_cost"]]
    broke_all = d[d["broke_down"]]
    allday = d

    print("\n=== 樣本數 ===")
    print(f"  全體 warm 日         : {len(allday)}")
    print(f"  早盤破 OR low (全體) : {len(broke_all)}")
    print(f"  event(破底+成本之上) : {len(event)}")
    print(f"  ctrl_b(破底+非成本上): {len(ctrl_b)}")

    tbl = pd.DataFrame([
        rate_table(allday, "A:全體日(baseline)"),
        rate_table(broke_all, "破OR low(全體)"),
        rate_table(event, "EVENT:破底+成本上"),
        rate_table(ctrl_b, "B:破底+非成本上"),
    ])
    print("\n=== Ladder 達成率 % (running-high anchored) ===")
    print(tbl.to_string(index=False))

    # L5 校準參考：reach_ratio 分佈
    print("\n=== reach_ratio (max_decline/EmaHL) 分佈 ===")
    for grp, name in [(allday, "全體"), (event, "EVENT")]:
        q = grp["reach_ratio"].quantile([.1, .25, .5, .75, .9]).round(3)
        print(f"  {name:6s} N={len(grp):4d}  "
              f"p10={q.loc[.1]} p25={q.loc[.25]} p50={q.loc[.5]} "
              f"p75={q.loc[.75]} p90={q.loc[.9]}")

    # 虛無檢定：從「破 OR low 全體日」隨機抽 len(event) 個，看 Lk 達成率分佈
    print("\n=== 虛無檢定：event vs 破OR-low池隨機抽樣 (10000x) ===")
    rng = np.random.default_rng(42)
    ne = len(event)
    pool = broke_all
    for k in LADDER:
        obs = event[k].mean()
        boot = np.array([
            pool[k].sample(ne, replace=False, random_state=int(rng.integers(1e9))).mean()
            for _ in range(2000)
        ])
        pctl = (boot < obs).mean() * 100
        print(f"  {k}: event={obs*100:.1f}%  pool均={pool[k].mean()*100:.1f}%  "
              f"null[p5,p95]=[{np.percentile(boot,5)*100:.1f},"
              f"{np.percentile(boot,95)*100:.1f}]  event位於null第{pctl:.0f}百分位")

    # 條件續走機率（出場規則關鍵數字）
    print("\n=== 條件續走機率 P(L_{k+1}|L_k) ===")
    for grp, name in [(allday, "A:全體"), (event, "EVENT:成本上破底"),
                      (ctrl_b, "B:成本下破底")]:
        L1, L2, L3, L4, L5 = [grp[k].mean() for k in LADDER]
        print(f"  {name:16s} N={len(grp):4d}  "
              f"無條件 L3={L3*100:.0f} L4={L4*100:.0f} L5={L5*100:.0f} | "
              f"P(L4|L3)={L4/L3*100:.0f} P(L5|L4)={L5/L4*100:.0f}")

    # 跨年穩定性：EVENT vs B 的 L3/L4
    print("\n=== 跨年穩定性 EV vs B（L3/L4 達成率 %）===")
    dd = d.copy()
    dd["year"] = pd.to_datetime(dd["date"]).dt.year
    for y, g in dd.groupby("year"):
        ev = g[g["broke_down"] & g["above_cost"]]
        b = g[g["broke_down"] & ~g["above_cost"]]
        if len(ev) < 5 or len(b) < 5:
            continue
        print(f"  {y}  EV_L3={ev.L3.mean()*100:.0f} B_L3={b.L3.mean()*100:.0f} | "
              f"EV_L4={ev.L4.mean()*100:.0f} B_L4={b.L4.mean()*100:.0f}")

    # 年度 / regime 分佈
    print("\n=== EVENT 年度分佈 ===")
    ev = event.copy()
    ev["year"] = pd.to_datetime(ev["date"]).dt.year
    print(ev.groupby("year").size().to_string())

    # 輸出事件日清單
    cols = ["date", "session_open", "vwap_t1", "vwap_t2", "or_high", "or_low",
            "brk_time", "day_low", "max_decline", "EmaHL", "reach_ratio",
            "L2", "L3", "L4", "L5"]
    out = event[cols].copy()
    out.to_csv("research/active/H122-bull-trap-or-break/results/event_days.csv",
               index=False)
    print(f"\n事件日清單已輸出 -> results/event_days.csv (N={len(out)})")

    daily.to_csv("research/active/H122-bull-trap-or-break/results/daily_features.csv",
                 index=False)


if __name__ == "__main__":
    main()

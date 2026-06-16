"""
H123 — Weak-Open OR Break Short：Phase 2 回測

進場   ：嚴格弱勢開局(open<VWAP_t1 且 <VWAP_t2) 且 08:58–09:15 首根 close<OR low → 該根收盤放空
停損   ：sl_mode='orhigh' → OR high；'ema' → entry + sl_mult×EmaHL
停利   ：TP = entry − tp_mult×EmaHL（tp_mult=None → 不設 TP，抱到收盤時間出場）
時間出場：13:45 最後一根收盤
同根模糊：一根內同時觸及 SL 與 TP → 視為先停損（保守）
成本   ：每筆來回扣 cost_pts 點（敏感度 0/1/2/3）
績效   ：損益% = 點數/進場價×100（沿用專案標準），逐筆 Sharpe 基於損益%
"""
import duckdb
import numpy as np
import pandas as pd
from datetime import time as dtime

DB = "data/futures.duckdb"
SYM = "TX"
OR_END = dtime(8, 57)
ENTRY_START, ENTRY_END = dtime(8, 58), dtime(9, 15)
SESS_START, SESS_END = dtime(8, 45), dtime(13, 45)
EMA_PERIOD, WARMUP = 20, 20
LAD = {"L2": 0.497, "L3": 0.711, "L4": 0.977}
ODIR = "research/active/H123-weak-open-break-short/results"


def load():
    con = duckdb.connect(DB, read_only=True)
    df = con.execute(
        """SELECT timestamp, open, high, low, close, volume FROM ohlcv_1m
           WHERE symbol=? AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
           ORDER BY timestamp""", [SYM]).df()
    con.close()
    df["date"] = df["timestamp"].dt.date
    df["t"] = df["timestamp"].dt.time
    return df


def build_events(df):
    """回傳事件日 list[dict]，含 entry/EmaHL/OR + 該日破底後逐根 bars。"""
    daily_range, ema, cur = {}, {}, None
    alpha = 2.0 / (EMA_PERIOD + 1)
    dates = sorted(df["date"].unique())

    # 先算每日 session 特徵
    feat = {}
    for d, g in df.groupby("date"):
        g = g.sort_values("timestamp")
        sess = g[(g.t >= SESS_START) & (g.t <= SESS_END)]
        if sess.empty:
            continue
        feat[d] = dict(
            g=sess,
            session_open=float(sess.iloc[0]["open"]),
            vwap=float((sess.close * sess.volume).sum() / sess.volume.sum()),
            day_range=float(sess.high.max() - sess.low.min()),
            or_high=float(sess[sess.t <= OR_END].high.max()),
            or_low=float(sess[sess.t <= OR_END].low.min()),
        )
    # EmaHL（前一日為止）
    for d in dates:
        if d not in feat:
            continue
        ema[d] = cur
        cur = feat[d]["day_range"] if cur is None else \
            feat[d]["day_range"] * alpha + cur * (1 - alpha)

    events = []
    dlist = [d for d in dates if d in feat]
    for i, d in enumerate(dlist):
        if i < WARMUP or ema[d] is None or ema[d] <= 0:
            continue
        f = feat[d]
        vt1 = feat[dlist[i - 1]]["vwap"]
        vt2 = feat[dlist[i - 2]]["vwap"]
        if not (f["session_open"] < vt1 and f["session_open"] < vt2):
            continue  # 非嚴格弱勢
        sess = f["g"]
        ent = sess[(sess.t >= ENTRY_START) & (sess.t <= ENTRY_END)]
        brk = ent[ent.close < f["or_low"]]
        if brk.empty:
            continue
        brk_ts = brk.iloc[0]["timestamp"]
        entry = float(brk.iloc[0]["close"])
        after = sess[sess.timestamp > brk_ts]
        if after.empty:
            continue
        events.append(dict(date=d, entry=entry, EmaHL=ema[d],
                           or_high=f["or_high"],
                           highs=after.high.to_numpy(),
                           lows=after.low.to_numpy(),
                           last_close=float(after.iloc[-1]["close"])))
    return events


def run(events, tp_mult, sl_mode="orhigh", sl_mult=1.0, cost_pts=2.0):
    recs = []
    for e in events:
        entry, emahl = e["entry"], e["EmaHL"]
        sl = e["or_high"] if sl_mode == "orhigh" else entry + sl_mult * emahl
        tp = entry - tp_mult * emahl if tp_mult is not None else None
        exit_px, reason = None, None
        for hi, lo in zip(e["highs"], e["lows"]):
            if hi >= sl:                       # 先檢查停損（保守）
                exit_px, reason = sl, "SL"
                break
            if tp is not None and lo <= tp:
                exit_px, reason = tp, "TP"
                break
        if exit_px is None:
            exit_px, reason = e["last_close"], "TIME"
        pnl = (entry - exit_px) - cost_pts     # 空單：進場-出場
        recs.append(dict(date=e["date"], entry=entry, exit=exit_px, reason=reason,
                         pnl_pts=pnl, pnl_pct=pnl / entry * 100))
    return pd.DataFrame(recs)


def metrics(r):
    if r.empty:
        return {}
    p = r.pnl_pct
    wins, losses = p[p > 0], p[p <= 0]
    # 最大連敗
    streak = mx = 0
    for v in p:
        streak = streak + 1 if v <= 0 else 0
        mx = max(mx, streak)
    eq = p.cumsum()
    dd = (eq.cummax() - eq).max()
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf
    return dict(N=len(r), win=round(100 * (p > 0).mean(), 1),
                tot_pct=round(p.sum(), 2), avg_pct=round(p.mean(), 4),
                PF=round(pf, 2), sharpe=round(p.mean() / p.std(), 3) if p.std() else 0,
                maxLossStreak=int(mx), maxDD_pct=round(dd, 2))


def main():
    df = load()
    events = build_events(df)
    print(f"事件日總數 N={len(events)}  "
          f"{events[0]['date']}~{events[-1]['date']}\n")

    # ---- 出場階比較（cost=2）----
    print("=== 出場規則比較（SL=OR high, cost=2pt/來回）===")
    rows = []
    configs = [("TP@L2", 0.497), ("TP@L3", 0.711), ("TP@L4", 0.977), ("抱到收盤", None)]
    runs = {}
    for name, tp in configs:
        r = run(events, tp, cost_pts=2.0)
        runs[name] = r
        rows.append({"config": name, **metrics(r)})
    print(pd.DataFrame(rows).to_string(index=False))

    # ---- 成本敏感度（以較佳出場階）----
    print("\n=== 成本敏感度 ===")
    for name, tp in configs:
        line = {"config": name}
        for c in (0, 1, 2, 3):
            line[f"tot%@{c}pt"] = round(run(events, tp, cost_pts=c).pnl_pct.sum(), 1)
        print(line)

    # ---- 停損模式敏感度（TP=L3, cost=2）----
    print("\n=== 停損敏感度（TP@L3, cost=2）===")
    for sm, smu, tag in [("orhigh", 0, "OR high"), ("ema", 0.5, "entry+0.5×EmaHL"),
                         ("ema", 1.0, "entry+1.0×EmaHL"), ("ema", 1.5, "entry+1.5×EmaHL")]:
        r = run(events, 0.711, sl_mode=sm, sl_mult=smu, cost_pts=2.0)
        print({"SL": tag, **metrics(r)})

    # ---- 逐年穩定性（TP@L3, cost=2）----
    print("\n=== 逐年穩定性（TP@L3, cost=2）===")
    r = run(events, 0.711, cost_pts=2.0)
    r["year"] = pd.to_datetime(r.date).dt.year
    yr_rows = []
    for y, g in r.groupby("year"):
        yr_rows.append({"year": int(y), **metrics(g)})
    print(pd.DataFrame(yr_rows).to_string(index=False))

    # ---- IS/OOS（2021-2024 vs 2025-2026）----
    print("\n=== IS(2021-24) vs OOS(2025-26)  TP@L3 cost=2 ===")
    for name, tp in [("TP@L2", 0.497), ("TP@L3", 0.711), ("抱到收盤", None)]:
        rr = run(events, tp, cost_pts=2.0)
        rr["year"] = pd.to_datetime(rr.date).dt.year
        is_ = rr[rr.year <= 2024]; oos = rr[rr.year >= 2025]
        print(f"  {name:8s} IS {metrics(is_)}")
        print(f"  {name:8s} OOS {metrics(oos)}")

    # 輸出最佳組逐筆
    runs["TP@L3"].to_csv(f"{ODIR}/trades_tp_l3.csv", index=False)
    print(f"\n逐筆(TP@L3) -> {ODIR}/trades_tp_l3.csv")


if __name__ == "__main__":
    main()

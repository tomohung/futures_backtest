"""
H123 — Weak-Open OR Break Short：Phase 1 分佈探索

事件（嚴格弱勢開局）
  open(08:45 第一根) < 昨日日盤VWAP 且 < 前日日盤VWAP   （AND，嚴格雙雙在成本下）
  且 08:58–09:15 任一根 close < OR low（取首次觸發 = 進場點）

兩種 reach 並陳
  (1) session-wide running-high anchored（與 H122 可比）：max_t(running_high − low) ≥ m×EmaHL
  (2) **forward-from-break（可交易）**：entry = 破底首根 close；
      fwd_mfe = entry − min(low for bars 在破底之後)；達成 = fwd_mfe ≥ m×EmaHL
  m: L1=.385 L2=.497 L3=.711 L4=.977 L5=1.30；EmaHL=前一日 EMA20(日盤 H-L)

對照：全體 baseline / H122 EVENT(成本上破底) / H122 寬鬆B(非成本上破底)
進場可行性：破底時點 vs 各 ladder 階(forward 基準)首達成時點
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
LADDER = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.30}
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


def per_day(df):
    rows = []
    for d, g in df.groupby("date"):
        g = g.sort_values("timestamp")
        sess = g[(g["t"] >= SESS_START) & (g["t"] <= SESS_END)]
        if sess.empty:
            continue
        session_open = float(sess.iloc[0]["open"])
        vwap = float((sess["close"] * sess["volume"]).sum() / sess["volume"].sum())
        dh, dl = float(sess["high"].max()), float(sess["low"].min())
        orb = sess[sess["t"] <= OR_END]
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())

        ent = sess[(sess["t"] >= ENTRY_START) & (sess["t"] <= ENTRY_END)]
        brk = ent[ent["close"] < or_low]
        broke = not brk.empty
        brk_ts = brk.iloc[0]["timestamp"] if broke else None
        brk_time = brk.iloc[0]["t"] if broke else None
        brk_close = float(brk.iloc[0]["close"]) if broke else np.nan

        # (1) session-wide running-high reach
        rhigh = sess["high"].cummax()
        max_decline = float((rhigh - sess["low"]).max())

        # (2) forward-from-break：破底首根之後的最大下行
        fwd_mfe = np.nan
        if broke:
            after = sess[sess["timestamp"] > brk_ts]
            if not after.empty:
                fwd_mfe = brk_close - float(after["low"].min())
            else:
                fwd_mfe = 0.0

        rows.append(dict(date=d, session_open=session_open, vwap=vwap,
                         day_high=dh, day_low=dl, day_range=dh - dl,
                         or_high=or_high, or_low=or_low, broke_down=broke,
                         brk_time=brk_time, brk_close=brk_close,
                         max_decline=max_decline, fwd_mfe=fwd_mfe))
    daily = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    alpha = 2.0 / (EMA_PERIOD + 1)
    ema, cur = [], None
    for r in daily["day_range"]:
        ema.append(cur)
        cur = r if cur is None else r * alpha + cur * (1 - alpha)
    daily["EmaHL"] = ema
    daily["vwap_t1"] = daily["vwap"].shift(1)
    daily["vwap_t2"] = daily["vwap"].shift(2)

    # 開局分類
    daily["above_cost"] = (daily.session_open > daily.vwap_t1) & (daily.session_open > daily.vwap_t2)
    daily["weak_strict"] = (daily.session_open < daily.vwap_t1) & (daily.session_open < daily.vwap_t2)

    valid = daily.EmaHL.notna() & (daily.EmaHL > 0)
    for k, m in LADDER.items():
        daily[k] = np.where(valid, daily.max_decline >= m * daily.EmaHL, np.nan)       # session-wide
        daily[k + "_f"] = np.where(valid, daily.fwd_mfe >= m * daily.EmaHL, np.nan)     # forward
    daily["reach_sw"] = np.where(valid, daily.max_decline / daily.EmaHL, np.nan)
    daily["reach_fwd"] = np.where(valid, daily.fwd_mfe / daily.EmaHL, np.nan)
    daily["warm"] = valid & (daily.index >= WARMUP)
    return daily


def rates(sub, label, suffix=""):
    n = len(sub)
    line = {"group": label, "N": n}
    for k in LADDER:
        line[k] = round(100 * sub[k + suffix].mean(), 1) if n else np.nan
    return line


def main():
    daily = per_day(load())
    d = daily[daily.warm].copy()
    print(f"全體 warm: N={len(d)}  {d.date.min()}~{d.date.max()}\n")

    base = d
    ev_above = d[d.broke_down & d.above_cost]            # H122 EVENT
    b_loose = d[d.broke_down & ~d.above_cost]            # H122 寬鬆 B
    weak = d[d.broke_down & d.weak_strict]               # H123 嚴格弱勢
    broke_all = d[d.broke_down]

    print("=== 樣本數 ===")
    for nm, s in [("全體 warm", base), ("破OR low(全體)", broke_all),
                  ("H122 EVENT 成本上", ev_above), ("H122 寬鬆B 非成本上", b_loose),
                  ("H123 嚴格弱勢(雙雙成本下)", weak)]:
        print(f"  {nm:24s}: {len(s)}")

    print("\n=== (1) session-wide running-high reach 達成率 % ===")
    print(pd.DataFrame([
        rates(base, "全體 baseline"), rates(ev_above, "H122 成本上"),
        rates(b_loose, "H122 寬鬆B"), rates(weak, "H123 嚴格弱勢"),
    ]).to_string(index=False))

    print("\n=== (2) forward-from-break reach 達成率 %（可交易）===")
    print(pd.DataFrame([
        rates(ev_above, "H122 成本上", "_f"), rates(b_loose, "H122 寬鬆B", "_f"),
        rates(weak, "H123 嚴格弱勢", "_f"),
    ]).to_string(index=False))

    print("\n=== 嚴格弱勢：條件續走（session-wide / forward）===")
    for suf, tag in [("", "session-wide"), ("_f", "forward")]:
        L = [weak[k + suf].mean() for k in LADDER]
        print(f"  {tag:12s} L2={L[1]*100:.0f} L3={L[2]*100:.0f} L4={L[3]*100:.0f} "
              f"L5={L[4]*100:.0f} | P(L4|L3)={L[3]/L[2]*100 if L[1] else 0:.0f}... "
              f"P(L4|L3)={L[3]/L[2]*100:.0f} P(L5|L4)={L[4]/L[3]*100:.0f}")

    # 虛無檢定：weak vs 破OR-low池隨機抽（session-wide 與 forward 都測）
    print("\n=== 虛無檢定：嚴格弱勢 vs 破OR-low池隨機抽 (2000x) ===")
    rng = np.random.default_rng(42)
    nw = len(weak)
    for suf, tag in [("", "SW"), ("_f", "FWD")]:
        for k in ["L3", "L4", "L5"]:
            obs = weak[k + suf].mean()
            boot = np.array([broke_all[k + suf].sample(nw, random_state=int(rng.integers(1e9))).mean()
                             for _ in range(2000)])
            pct = (boot < obs).mean() * 100
            print(f"  [{tag}] {k}: weak={obs*100:.1f}%  pool={broke_all[k+suf].mean()*100:.1f}%  "
                  f"null[p5,p95]=[{np.percentile(boot,5)*100:.1f},{np.percentile(boot,95)*100:.1f}]  "
                  f"第{pct:.0f}百分位")

    # 進場可行性：破底時點分佈
    print("\n=== 進場可行性：破底首次觸發時點分佈（嚴格弱勢）===")
    bt = pd.to_datetime(weak.brk_time.astype(str)).dt.strftime("%H:%M")
    print(bt.value_counts().sort_index().to_string())
    # forward reach > 0 比例（破底後確實還有下行空間，非事後）
    pos = (weak.fwd_mfe > 0).mean() * 100
    big = (weak.reach_fwd >= LADDER["L3"]).mean() * 100
    print(f"  破底後仍有下行空間(fwd_mfe>0): {pos:.0f}%   forward 達 L3: {big:.0f}%")

    # 年度分佈
    print("\n=== 嚴格弱勢 年度分佈 ===")
    w = weak.copy(); w["year"] = pd.to_datetime(w.date).dt.year
    print(w.groupby("year").size().to_string())

    # 輸出
    cols = ["date", "session_open", "vwap_t1", "vwap_t2", "or_low", "brk_time",
            "brk_close", "day_low", "max_decline", "fwd_mfe", "EmaHL",
            "reach_sw", "reach_fwd", "L3", "L4", "L3_f", "L4_f"]
    weak[cols].to_csv(f"{ODIR}/event_days.csv", index=False)
    daily.to_csv(f"{ODIR}/daily_features.csv", index=False)
    print(f"\n事件日清單 -> {ODIR}/event_days.csv (N={len(weak)})")


if __name__ == "__main__":
    main()

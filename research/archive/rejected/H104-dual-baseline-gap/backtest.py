"""H104 雙基準跳空 — Phase 2 回測（錨對照 + 夜盤錨原生尺度）

Phase 1 + 尺度檢查結論：夜盤 05:00 收離開盤僅 3.75h，|gap|/ema20 中位 0.146、僅 2.2%≥1.0，
無法套 H103 的「折價≥1 日均振幅」門檻（literal anchor-swap 零樣本）。故 Phase 2 改測：
  T1  H103 複刻（VWAP 錨反彈做多）            — baseline，驗框架可重現
  T2  DH-16 夜盤錨 fade（中等跳空 → 回夜盤收）— Phase 1 回補率 72–92% 是否可交易
  T3  夜盤錨 momentum（極端跳空 → 續行）      — Phase 1 極端尾端續行
  T4  H104⟂H103 加值（H103 勝組內，夜盤跳空方向/大小是否再分winners）
共同設定：08:45 開盤進場，路徑出場（同根先停損，保守），13:30 未觸發則 13:45 收盤平倉，
成本 3 點/round-trip，績效 損益%=(出場−進場−成本符號)/進場×100。IS=2021–23 / OOS=2024–26。
"""
from __future__ import annotations
from pathlib import Path
import datetime as dt
import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DB = str(ROOT / "data" / "futures.duckdb")
DAILY_CSV = (ROOT / "research" / "archive" / "rejected" /
             "H102-clear-runway-breakout" / "results" / "h102_daily.csv")
EXIT_T = dt.time(13, 30)
COST = 3.0
TRADES_PER_YEAR = 20.0


# ---------------------------------------------------------------- daily table (VWAP + night anchor)
def build_daily():
    daily = pd.read_csv(DAILY_CSV, parse_dates=[0], index_col=0)
    con = duckdb.connect(DB, read_only=True)
    df = con.sql("select timestamp, open, close, adjustment, adj_close, is_rollover "
                 "from ohlcv_1m order by timestamp").df()
    con.close()
    df["t"] = df["timestamp"].dt.time
    T_OPEN = dt.time(8, 45)
    day = df[(df.t >= T_OPEN) & (df.t <= dt.time(13, 45))]
    g = day.groupby(df["timestamp"].dt.normalize())
    daopen = g.apply(lambda x: x.loc[x.t == T_OPEN, "open"].iloc[0]
                     + x.loc[x.t == T_OPEN, "adjustment"].iloc[0], include_groups=False)
    roll = g["is_rollover"].max().astype(bool)
    tdays = daopen.index.to_numpy()
    open_dt = (daopen.index + pd.Timedelta(hours=8, minutes=45)).to_numpy()
    night = df[(df.t >= dt.time(15, 0)) | (df.t <= dt.time(5, 0))].copy()
    idx = np.searchsorted(open_dt, night["timestamp"].to_numpy(), side="left")
    night = night[idx < len(tdays)].copy()
    night["own"] = tdays[idx[idx < len(tdays)]]
    n0500 = night.groupby("own").apply(
        lambda x: (x.loc[x.t == dt.time(5, 0), "adj_close"].iloc[-1] if (x.t == dt.time(5, 0)).any()
                   else x.loc[x.timestamp.idxmax(), "adj_close"]), include_groups=False)
    N = pd.DataFrame({"adj_open": daopen, "night_aclose": n0500, "roll": roll})
    N["ngap"] = N["adj_open"] - N["night_aclose"]          # 夜盤錨跳空（adj，已剔換倉假跳空）
    M = daily.join(N, how="inner")
    M = M[~M["roll"]].copy()
    M["ngap_norm"] = M["ngap"] / M["ema20"]
    M["ngap_pct"] = M["ngap"] / M["open"] * 100
    # night close 在 raw 價座標（出場目標用 raw，和盤中 raw bar 對齊）：night_raw = open_raw - ngap
    M["night_raw"] = M["open"] - M["ngap"]
    return M


def load_intraday(dates):
    dset = ", ".join(f"DATE '{d}'" for d in dates)
    con = duckdb.connect(DB, read_only=True)
    bars = con.execute(
        f"""SELECT CAST(timestamp AS DATE) d, timestamp ts, open, high, low, close
            FROM ohlcv_1m WHERE symbol='TX'
              AND CAST(timestamp AS DATE) IN ({dset})
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY ts""").df()
    con.close()
    for c in ("open", "high", "low", "close"):
        bars[c] = bars[c].astype(float)
    bars["t"] = pd.to_datetime(bars["ts"]).dt.time
    bars["mins"] = (pd.to_datetime(bars["ts"]).dt.hour * 60
                    + pd.to_datetime(bars["ts"]).dt.minute) - (8 * 60 + 45)
    return {pd.Timestamp(d).date(): gg.reset_index(drop=True) for d, gg in bars.groupby("d")}


# ---------------------------------------------------------------- trade engine
def run_trade(g, side, tp_px, sl_px):
    """side=+1 long / -1 short. 路徑出場：同根先停損(保守)。回傳 (pnl_pts_net, pnl_pct_net, hold)."""
    entry = float(g["open"].iloc[0])
    post = g[g["t"] <= EXIT_T]
    exit_px, hold = None, int(post["mins"].iloc[-1])
    for _, b in post.iterrows():
        if side == +1:
            if b["low"] <= sl_px:  exit_px, hold = sl_px, int(b["mins"]); break
            if b["high"] >= tp_px: exit_px, hold = tp_px, int(b["mins"]); break
        else:
            if b["high"] >= sl_px: exit_px, hold = sl_px, int(b["mins"]); break
            if b["low"] <= tp_px:  exit_px, hold = tp_px, int(b["mins"]); break
    if exit_px is None:
        exit_px = float(post["close"].iloc[-1])
    pnl_pts = side * (exit_px - entry) - COST
    return pnl_pts, pnl_pts / entry * 100.0, hold


def stats(p_pct, p_pts):
    p = np.asarray(p_pct); n = len(p)
    if n == 0: return dict(N=0)
    eq = np.cumsum(p); dd = np.maximum.accumulate(eq) - eq
    streak = mx = 0
    for x in p:
        streak = streak + 1 if x <= 0 else 0; mx = max(mx, streak)
    sd = p.std(ddof=1)
    return dict(N=n, win=(p > 0).mean(), avg_pct=p.mean(), sum_pct=p.sum(),
                avg_pts=np.mean(p_pts),
                sharpe=(p.mean() / sd * np.sqrt(TRADES_PER_YEAR)) if sd > 0 else float("nan"),
                maxdd=dd.max(), maxlose=mx,
                pf=(p[p > 0].sum() / -p[p < 0].sum()) if (p < 0).any() else float("inf"))


def line(tag, s):
    if s.get("N", 0) == 0: print(f"  {tag:<22} N=0"); return
    print(f"  {tag:<22} N={s['N']:>3} 勝率={s['win']:>4.0%} PF={s['pf']:>4.2f} "
          f"均{s['avg_pct']:>+6.3f}% 總{s['sum_pct']:>+7.2f}% 年化SR={s['sharpe']:>+5.2f} "
          f"MDD={s['maxdd']:>5.2f}% 連敗={s['maxlose']:>2d} 均{s['avg_pts']:>+5.1f}點")


def report(name, recs):
    tr = pd.DataFrame(recs)
    print(f"\n[{name}]  (IS=21–23 / OOS=24–26)")
    if len(tr) == 0: print("  N=0"); return tr
    IS, OOS = tr[tr.yr <= 2023], tr[tr.yr >= 2024]
    line("全期", stats(tr.pnl_pct, tr.pnl_pts))
    line("In-Sample", stats(IS.pnl_pct, IS.pnl_pts))
    line("Out-of-Sample", stats(OOS.pnl_pct, OOS.pnl_pts))
    return tr


def main():
    M = build_daily()
    intr = load_intraday([d.date() for d in M.index])
    print("=" * 104)
    print(f"  H104 Phase 2  夜盤錨={ '05:00收' }  成本={COST}點/筆  N(no-rollover)={len(M)}")
    print("=" * 104)

    # ---- T1 H103 複刻 (VWAP 錨反彈做多, target0.7/stop0.5 ema20) ----
    recs = []
    q = M[(M.n_above == 2) & (M.up_clear_norm >= 1.0)]
    for d, r in q.iterrows():
        pts, pct, h = run_trade(intr[d.date()], +1, r.open + 0.7 * r.ema20, r.open - 0.5 * r.ema20)
        recs.append(dict(d=d, yr=d.year, pnl_pts=pts, pnl_pct=pct, hold=h))
    report("T1 H103複刻 VWAP錨反彈做多", recs)

    # ---- T2 DH-16 夜盤錨 fade：中等跳空 → 回夜盤收 (target=night, stop=1R=|gap|) ----
    for lo, hi in [(0.10, 0.45), (0.10, 0.30), (0.15, 0.45)]:
        recs = []
        band = M[(M.ngap_norm.abs() >= lo) & (M.ngap_norm.abs() <= hi)]
        for d, r in band.iterrows():
            side = -1 if r.ngap > 0 else +1            # gap up→short回補；gap down→long回補
            gabs = abs(r.ngap)
            tp = r.night_raw                            # 目標=夜盤收
            sl = r.open - side * gabs                   # 1R 反向
            pts, pct, h = run_trade(intr[d.date()], side, tp, sl)
            recs.append(dict(d=d, yr=d.year, pnl_pts=pts, pnl_pct=pct, hold=h))
        report(f"T2 夜盤fade |gap_norm|∈[{lo},{hi}] (target=夜盤收,stop=1R)", recs)

    # ---- T3 夜盤錨 momentum：極端跳空 → 續行 (target0.7/stop0.5 ema20) ----
    for thr in (0.45, 0.55, 0.65):
        recs = []
        ext = M[M.ngap_norm.abs() >= thr]
        for d, r in ext.iterrows():
            side = -1 if r.ngap < 0 else +1            # gap down→short續跌；gap up→long續漲
            pts, pct, h = run_trade(intr[d.date()], side, r.open + side * 0.7 * r.ema20,
                                    r.open - side * 0.5 * r.ema20)
            recs.append(dict(d=d, yr=d.year, pnl_pts=pts, pnl_pct=pct, hold=h, dirn=side))
        tr = report(f"T3 夜盤momentum |gap_norm|≥{thr} (續行,0.7/0.5)", recs)
        if len(tr):  # 拆方向
            for s, nm in [(-1, "  └ 僅gap-down空"), (+1, "  └ 僅gap-up多")]:
                sub = tr[tr.dirn == s]
                line(nm, stats(sub.pnl_pct, sub.pnl_pts))

    # ---- T4 H104⟂H103：H103 勝組內依夜盤跳空方向再分 ----
    print("\n[T4 H104⟂H103 加值] H103勝組(n_above2 & up_clear≥1.0) 依夜盤跳空方向 (反彈做多,0.7/0.5)")
    recs = []
    for d, r in q.iterrows():
        pts, pct, h = run_trade(intr[d.date()], +1, r.open + 0.7 * r.ema20, r.open - 0.5 * r.ema20)
        recs.append(dict(d=d, yr=d.year, pnl_pts=pts, pnl_pct=pct, ngap=r.ngap))
    tr = pd.DataFrame(recs)
    for cond, nm in [(tr.ngap < 0, "夜盤也gap-down(同向折價)"), (tr.ngap > 0, "夜盤gap-up(逆向)")]:
        sub = tr[cond]
        line(nm, stats(sub.pnl_pct, sub.pnl_pts))
        si, so = sub[sub.yr <= 2023], sub[sub.yr >= 2024]
        line(nm + " IS", stats(si.pnl_pct, si.pnl_pts))
        line(nm + " OOS", stats(so.pnl_pct, so.pnl_pts))

    M.to_csv(Path(__file__).resolve().parent / "results" / "h104_daily.csv")
    print("\n[saved] results/h104_daily.csv")


if __name__ == "__main__":
    main()

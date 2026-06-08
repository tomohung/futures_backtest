"""H103 跳空跌破成本→折價回補做多 — Phase 2 回測。

規則（Phase 1 收斂）：
  進場：gap-down 日（open < min(vwap_last,vwap_prev)）且 up_clear_norm≥THRESH(L4=0.977)
        → 08:45 開盤即做多 1 口
  出場：固定目標 T×ema20 / 停損 S×ema20，盤中路徑（同根先停損，保守）；
        13:30 未觸發則收盤平倉
  成本：每筆 round-trip COST 點（手續費+稅~1.5 + 滑價~2 ≈ 3）
績效：損益% = (出場−進場−成本)/進場×100（對齊 CLAUDE.md），Sharpe 基於損益%。
IS=2021–2023、OOS=2024–2026。
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DB = str(ROOT / "data" / "futures.duckdb")
DAILY_CSV = (ROOT / "research" / "archive" / "rejected" /
             "H102-clear-runway-breakout" / "results" / "h102_daily.csv")
L4C, L5C = 0.977, 1.225
EXIT_T = pd.Timestamp("1900-01-01 13:30:00").time()
TRADES_PER_YEAR = 20.0  # ~111/5.4，用於年化 Sharpe


def load_intraday(dates):
    dset = ", ".join(f"DATE '{d}'" for d in dates)
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            f"""SELECT CAST(timestamp AS DATE) d, timestamp ts, open, high, low, close
                FROM ohlcv_1m WHERE symbol='TX'
                  AND CAST(timestamp AS DATE) IN ({dset})
                  AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
                ORDER BY ts""").df()
    for col in ("open", "high", "low", "close"):
        bars[col] = bars[col].astype(float)
    bars["t"] = pd.to_datetime(bars["ts"]).dt.time
    bars["mins"] = (pd.to_datetime(bars["ts"]).dt.hour * 60
                    + pd.to_datetime(bars["ts"]).dt.minute) - (8 * 60 + 45)
    return {pd.Timestamp(d).date(): g.reset_index(drop=True) for d, g in bars.groupby("d")}


def run_trade(g, ema20, T, S, cost):
    """回傳 (pnl_pts_net, pnl_pct_net, hold_min)。"""
    entry = float(g["open"].iloc[0])
    post = g[g["t"] <= EXIT_T]
    tp, sl = entry + T * ema20, entry - S * ema20
    exit_px, hold = None, int(post["mins"].iloc[-1])
    for _, b in post.iterrows():
        if b["low"] <= sl:
            exit_px, hold = sl, int(b["mins"]); break
        if b["high"] >= tp:
            exit_px, hold = tp, int(b["mins"]); break
    if exit_px is None:
        exit_px = float(post["close"].iloc[-1])
    pnl_pts = (exit_px - entry) - cost
    return pnl_pts, pnl_pts / entry * 100.0, hold


def stats(pnls_pct, pnls_pts):
    p = np.asarray(pnls_pct)
    n = len(p)
    if n == 0:
        return dict(N=0)
    eq = np.cumsum(p)
    dd = np.maximum.accumulate(eq) - eq
    # 最長連敗
    streak = mx = 0
    for x in p:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    sharpe_t = p.mean() / p.std(ddof=1) if p.std(ddof=1) > 0 else float("nan")
    return dict(N=n, win=(p > 0).mean(), avg_pct=p.mean(), sum_pct=p.sum(),
                avg_pts=np.mean(pnls_pts), sum_pts=np.sum(pnls_pts),
                sharpe=sharpe_t * np.sqrt(TRADES_PER_YEAR), maxdd=dd.max(),
                pf=(p[p > 0].sum() / -p[p < 0].sum()) if (p < 0).any() else float("inf"),
                maxlose=mx)


def line(tag, s):
    if s.get("N", 0) == 0:
        print(f"  {tag:<18} N=0"); return
    print(f"  {tag:<18} N={s['N']:>3} 勝率={s['win']:>4.0%} "
          f"PF={s['pf']:>4.2f} 均{s['avg_pct']:>+6.3f}% 總{s['sum_pct']:>+6.2f}% "
          f"年化SR={s['sharpe']:>+5.2f} MDD={s['maxdd']:>5.2f}% 連敗={s['maxlose']:>2d} "
          f"均{s['avg_pts']:>+5.1f}點")


def backtest(daily, intr, thresh, T, S, cost, label=""):
    q = daily[(daily["n_above"] == 2) & (daily["up_clear_norm"] >= thresh)].copy()
    recs = []
    for d, r in q.iterrows():
        pts, pct, hold = run_trade(intr[d.date()], r["ema20"], T, S, cost)
        recs.append(dict(d=d, yr=d.year, pnl_pts=pts, pnl_pct=pct, hold=hold))
    return pd.DataFrame(recs)


def main():
    daily = pd.read_csv(DAILY_CSV, parse_dates=[0], index_col=0)
    gd_all = daily[daily["n_above"] == 2]
    intr = load_intraday([d.date() for d in gd_all.index])

    T, S, COST, THRESH = 0.7, 0.5, 3.0, 1.0   # 門檻=1.0（≥1 個日均振幅；平台中央，微優於 L4）
    print("=" * 96)
    print(f"  H103 Phase 2  進場=開盤多｜目標={T}×ema20 停損={S}×ema20｜成本={COST}點/筆｜門檻 up_clear_norm≥{THRESH}")
    print("=" * 96)

    tr = backtest(daily, intr, THRESH, T, S, COST)
    IS = tr[tr["yr"] <= 2023]
    OOS = tr[tr["yr"] >= 2024]
    print("\n[主結果] IS=2021–2023 / OOS=2024–2026")
    line("全期", stats(tr["pnl_pct"], tr["pnl_pts"]))
    line("In-Sample", stats(IS["pnl_pct"], IS["pnl_pts"]))
    line("Out-of-Sample", stats(OOS["pnl_pct"], OOS["pnl_pts"]))

    print("\n[逐年] (walk-forward 視角)")
    for yr, s in tr.groupby("yr"):
        line(str(yr), stats(s["pnl_pct"], s["pnl_pts"]))

    print("\n[敏感度：成本] (門檻L4, 0.7/0.5)")
    for c in (0, 3, 5, 7):
        t2 = backtest(daily, intr, THRESH, T, S, c)
        line(f"成本={c}點", stats(t2["pnl_pct"], t2["pnl_pts"]))

    print("\n[敏感度：門檻] (0.7/0.5, 成本3)")
    for th in (0.8, 0.977, 1.1, 1.225):
        t2 = backtest(daily, intr, th, T, S, COST)
        line(f"門檻≥{th}", stats(t2["pnl_pct"], t2["pnl_pts"]))

    print("\n[敏感度：目標/停損] (門檻L4, 成本3)")
    for tt, ss in [(0.5, 0.5), (0.7, 0.5), (1.0, 0.5), (0.5, 0.4), (0.7, 0.7), (1.0, 0.7)]:
        t2 = backtest(daily, intr, THRESH, tt, ss, COST)
        line(f"T{tt}/S{ss}", stats(t2["pnl_pct"], t2["pnl_pts"]))

    print("\n[對照基準] (同 ≥L4 日，成本3)")
    # baseline 1: 開盤多→收盤平倉（無目標停損）
    base = []
    q = daily[(daily["n_above"] == 2) & (daily["up_clear_norm"] >= THRESH)]
    for d, r in q.iterrows():
        g = intr[d.date()]; e = float(g["open"].iloc[0])
        cl = float(g[g["t"] <= EXIT_T]["close"].iloc[-1])
        base.append(((cl - e - COST) / e * 100, cl - e - COST))
    b = pd.DataFrame(base, columns=["pct", "pts"])
    line("開盤多→收盤", stats(b["pct"], b["pts"]))
    # baseline 2: 控制組 <L4 同規則
    tc = backtest(daily, intr, 0, T, S, COST)
    tc = tc.merge(daily[["up_clear_norm"]], left_on="d", right_index=True)
    line("控制<L4 (T0.7/S0.5)", stats(tc[tc["up_clear_norm"] < L4C]["pnl_pct"],
                                      tc[tc["up_clear_norm"] < L4C]["pnl_pts"]))

    tr.to_csv(Path(__file__).resolve().parent / "results" / "h103_backtest_trades.csv", index=False)
    print("\n[saved] results/h103_backtest_trades.csv")


if __name__ == "__main__":
    main()

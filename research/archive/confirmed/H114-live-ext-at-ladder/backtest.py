"""H114 Phase 2 — 碰觸時點（主軸）出場/加碼規則回測（事件型 bracket trade）。

事件：TX 上行擺幅首觸 L3 的分鐘 t_k → 以當下價 p_L3 進場做多，bracket：
  target = p_L3 + TGT×EMA20（TGT=0.266=L4−L3 擺幅增量）、stop = p_L3 − STOP_R×TGT×EMA20，
  逐分鐘走先到先出，皆未到→收盤平。損益% = 點數 / p_L3 × 100。

規則：
  A（主，時鐘）：t_k ≤ CUT(10:30) 才持有；晚碰→L3 收手（不進此 trade，pnl=0）。
  B：A ∪（晚碰 且 ddpeak<IS中位＝延伸力未滾頭 → 也持有）。
  baseline always：每個 L3 日都持有（不分時點）。
  baseline satisfy：一律 L3 收手（全 0，理論下限）。
對撞：B vs A（ext_long 修正增益）、A vs always（時點規則 vs 無腦持有）。

附帶報告（B 視角）：剩餘分鐘分桶的持有 trade 績效。
IS=≤2026-02-26、OOS=≥2026-03-01。所有數字附 N。
用法：uv run python research/active/H114-live-ext-at-ladder/backtest.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
PANEL = HERE / "results" / "ladder_live_ext_panel.csv"
LO, HI = date(2025, 6, 1), date(2026, 6, 30)
IS_END = date(2026, 2, 26)
L3, L4 = 0.711, 0.977
TGT = L4 - L3                 # 0.266×EMA20 擺幅增量（L3→L4）
STOP_R = 1.0                  # stop = STOP_R × TGT × EMA20（預設 1:1）
CUT = time(10, 30)            # 早/晚碰時鐘切點（Phase 1 平台邊緣）
CLOSE_M = 13 * 60 + 45


def tx_paths():
    """每日：t_k(L3)、p_L3、bracket 結果點數（target/stop/close 先到先出）、剩餘分鐘。"""
    with duckdb.connect(DB, read_only=True) as c:
        rng = c.execute(
            "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
        rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
        ema = rng.set_index("d")["ema20"]
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low, close FROM ohlcv_1m "
            "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
    for col in ("high", "low", "close"):
        bars[col] = bars[col].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        e = float(ema.get(d, np.nan))
        if not (e > 0):
            continue
        g = g.sort_values("t")
        hi, lo, cl = g["high"].values, g["low"].values, g["close"].values
        ts = [t if isinstance(t, time) else pd.Timestamp(t).time() for t in g["t"].values]
        runlow = np.minimum.accumulate(lo)
        up = np.maximum.accumulate(hi - runlow)
        ci = np.argmax(up >= L3 * e) if (up >= L3 * e).any() else -1
        if ci < 0:
            continue
        tk = ts[ci]; p_entry = cl[ci]
        tgt_px = p_entry + TGT * e
        stop_px = p_entry - STOP_R * TGT * e
        # 走 t_k 之後（含當根之後）的路徑，先到先出
        pnl = cl[-1] - p_entry      # 預設收盤平
        for j in range(ci + 1, len(g)):
            if lo[j] <= stop_px:    # 保守：同根先判 stop
                pnl = stop_px - p_entry; break
            if hi[j] >= tgt_px:
                pnl = tgt_px - p_entry; break
        rem = CLOSE_M - (tk.hour * 60 + tk.minute)
        rows.append({"d": pd.Timestamp(d).date(), "ema20": e, "tk": tk, "p_entry": p_entry,
                     "hold_pnl_pts": pnl, "hold_pnl_pct": pnl / p_entry * 100, "rem_min": rem})
    return pd.DataFrame(rows).set_index("d")


def stats(pnls: np.ndarray) -> dict:
    """pnls = 每筆損益%（未持有的日子不計入 trade）。"""
    n = len(pnls)
    if n == 0:
        return {"N": 0, "sum": 0, "mean": 0, "win": np.nan, "sharpe": np.nan, "maxDD": 0, "maxLoseStreak": 0}
    eq = np.cumsum(pnls)
    dd = eq - np.maximum.accumulate(eq)
    streak = mx = 0
    for p in pnls:
        streak = streak + 1 if p < 0 else 0
        mx = max(mx, streak)
    return {"N": n, "sum": pnls.sum(), "mean": pnls.mean(), "win": (pnls > 0).mean(),
            "sharpe": pnls.mean() / pnls.std() if pnls.std() > 0 else np.nan,
            "maxDD": dd.min(), "maxLoseStreak": mx}


def line(lab, s):
    return (f"  {lab:<22} N={s['N']:>3}  Σ損益%={s['sum']:>7.2f}  平均%={s['mean']:>6.3f}  "
            f"勝率={s['win']:.0%}  Sharpe={s['sharpe']:>5.2f}  maxDD={s['maxDD']:>7.2f}  最長連敗={s['maxLoseStreak']}")


def main():
    tx = tx_paths()
    pan = pd.read_csv(PANEL); pan["d"] = pd.to_datetime(pan["d"]).dt.date
    pan = pan[pan["lvl"] == "L3"].set_index("d")
    df = tx.join(pan[["W10_ddpeak", "is_seg"]], how="inner")
    df["early"] = df["tk"].apply(lambda t: t <= CUT)
    ddmed = df.loc[df["is_seg"] == "IS", "W10_ddpeak"].median()    # 晚碰修正門檻（IS 定）
    df["ext_ok"] = df["W10_ddpeak"] <= ddmed                       # 延伸力未滾頭
    df["take_A"] = df["early"]
    df["take_B"] = df["early"] | (~df["early"] & df["ext_ok"])

    L = ["=" * 100,
         f"H114 Phase 2 — 碰觸時點出場規則（bracket: tgt=+{TGT:.3f}×EMA20 / stop=−{STOP_R}R / 收盤平）",
         f"L3 事件 N={len(df)}（IS {int((df['is_seg']=='IS').sum())} / OOS {int((df['is_seg']=='OOS').sum())}）；CUT={CUT}；ddpeak修正門檻(IS中位)={ddmed:.3f}",
         "損益% = 點數/進場價×100；未持有日不計入 trade（=L3 滿足收手，貢獻 0）"]

    for seg in ("IS", "OOS"):
        g = df[df["is_seg"] == seg]
        L.append("\n" + "─" * 100)
        L.append(f"【{seg}】L3 事件={len(g)}　早碰(≤{CUT})={int(g['early'].sum())}　晚碰={int((~g['early']).sum())}")
        L.append(line("規則A 純時點", stats(g.loc[g["take_A"], "hold_pnl_pct"].values)))
        L.append(line("規則B 時點+ext修正", stats(g.loc[g["take_B"], "hold_pnl_pct"].values)))
        L.append(line("基準 always-hold", stats(g["hold_pnl_pct"].values)))
        # 晚碰層拆解（B 增益來源）
        late = g[~g["early"]]
        L.append("    晚碰層拆解：")
        L.append(line("  晚碰全持有", stats(late["hold_pnl_pct"].values)))
        L.append(line("  晚碰∩ext_ok(B取)", stats(late.loc[late["ext_ok"], "hold_pnl_pct"].values)))
        L.append(line("  晚碰∩ext弱(B棄)", stats(late.loc[~late["ext_ok"], "hold_pnl_pct"].values)))

    # 附帶：B 視角（剩餘分鐘分桶，持有 trade 績效）
    L.append("\n" + "═" * 100)
    L.append("附帶報告（B 視角）：持有 trade 績效 by 剩餘分鐘（早碰=剩餘多）")
    bins = [(240, 999, "≥240(早盤)"), (180, 240, "180-240"), (120, 180, "120-180"),
            (60, 120, "60-120"), (0, 60, "<60(收盤前)")]
    for seg in ("IS", "OOS"):
        g = df[df["is_seg"] == seg]
        L.append(f"  [{seg}]")
        for a, b, lab in bins:
            sub = g[(g["rem_min"] >= a) & (g["rem_min"] < b)]
            if len(sub):
                s = stats(sub["hold_pnl_pct"].values)
                L.append(f"     {lab:<12} N={s['N']:>3} 平均%={s['mean']:>6.3f} 勝率={s['win']:.0%} Σ%={s['sum']:>6.2f}")

    L.append("\n  ⚠ 上市-only(ext)、單一窗、無滑價手續費（純訊號驗證）；STOP_R/CUT 敏感度見另跑。SatZone 基準待補。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "backtest_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "bt_trades.csv")
    print(f"\n存：{out/'backtest_raw.txt'}")


if __name__ == "__main__":
    main()

"""H118 Phase 2 回測：CDF(台積電期) 盤前延伸 → 做多 TX，EOD 出場。

策略（long-only）：
  訊號  CDF open-anchor 延伸 @09:00（錨 08:45），盤前流動性 gate
  進場  延伸 ≥ θ → 09:01 open 做多 TX
  出場  13:45 收盤
  績效  損益% = (exit−entry)/entry×100（CLAUDE.md 慣例）

對照：θ=0 = 無條件每日做多（看訊號是否優於 always-long）。
IS=2021–2024 / OOS=2025–2026；逐年 walk-forward；θ 敏感度；成本敏感度。
commission 沿用專案慣例 0（另列扣成本版）。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explore import DB, LADDERS, PREOPEN_MIN_TICKS, aux_ext, tx_features

ENTRY_T = "09:01:00"     # 09:00 訊號 → 下一根 open 進場（避免同根 look-ahead）
EXIT_T = "13:45:00"
TX_POINT_COST = 0.0      # 點/趟（baseline 沿用專案慣例）；敏感度另測


def tx_entry_exit(conn) -> pd.DataFrame:
    """每日 TX 09:01 open（進場）與 13:45 close（出場）。"""
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, close
        FROM ohlcv_1m WHERE symbol='TX'
          AND CAST(timestamp AS TIME) IN (TIME '09:01:00', TIME '13:45:00')
    """).df()
    df["t"] = df["t"].astype(str)
    ent = df[df["t"] == ENTRY_T][["d", "open"]].rename(columns={"open": "entry"})
    ext = df[df["t"] == EXIT_T][["d", "close"]].rename(columns={"close": "exit"})
    return ent.merge(ext, on="d").set_index("d")


def stats(pnl_pct: pd.Series, cost_pct: float = 0.0) -> dict:
    """一組交易的績效。pnl_pct 已是每筆 %。"""
    r = pnl_pct - cost_pct
    n = len(r)
    if n == 0:
        return dict(N=0, win=np.nan, mean=np.nan, total=np.nan, sharpe=np.nan, maxdd=np.nan)
    eq = r.cumsum()
    dd = (eq.cummax() - eq).max()
    return dict(N=n, win=(r > 0).mean(), mean=r.mean(), total=r.sum(),
                sharpe=(r.mean() / r.std() if r.std() > 0 else np.nan), maxdd=dd)


def fmt(s: dict) -> str:
    if s["N"] == 0:
        return "N=0"
    return (f"N={s['N']:>4} 勝率={s['win']:.1%} 均%={s['mean']:+.3f} "
            f"總%={s['total']:+.1f} Sharpe={s['sharpe']:+.2f} maxDD%={s['maxdd']:.1f}")


def tx_path(conn) -> dict:
    """每日 TX 09:01–13:45 的 (high, low, last_close) 路徑，給 target/stop 模擬。"""
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low, close
        FROM ohlcv_1m WHERE symbol='TX'
          AND CAST(timestamp AS TIME) BETWEEN TIME '09:01:00' AND TIME '13:45:00'
        ORDER BY d, t
    """).df()
    return {d: g for d, g in df.groupby("d")}


def target_exit_pnl(row, path: dict, tgt_mult: float, stop_mult: float):
    """單日 target/stop 模擬。回傳 (pnl_pct, outcome) 或 None（跳過）。
    target = open + tgt_mult×EMA20；stop = open − stop_mult×EMA20；否則 EOD 收盤。"""
    d = row.name
    g = path.get(d)
    if g is None or len(g) == 0:
        return None
    o, ema20, entry = row["o"], row["ema20"], row["entry"]
    target = o + tgt_mult * ema20
    stop = o - stop_mult * ema20
    if entry >= target:        # 進場時已過目標 → 無可圖，跳過
        return None
    exit_px = None; outcome = "eod"
    for hi, lo in zip(g["high"].to_numpy(), g["low"].to_numpy()):
        hit_stop = lo <= stop
        hit_tgt = hi >= target
        if hit_stop and hit_tgt:        # 同根兩邊都碰 → 保守算停損先
            exit_px = stop; outcome = "stop"; break
        if hit_stop:
            exit_px = stop; outcome = "stop"; break
        if hit_tgt:
            exit_px = target; outcome = "target"; break
    if exit_px is None:
        exit_px = g["close"].to_numpy()[-1]; outcome = "eod"
    return (exit_px - entry) / entry * 100.0, outcome


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        cdf = aux_ext(conn, "CDF")
        cdf = cdf[cdf["preticks"] >= PREOPEN_MIN_TICKS]    # 盤前流動性 gate
        tx = tx_entry_exit(conn)

        df = cdf[["ext_09:00"]].join(tx, how="inner").dropna()
        df["pnl_pct"] = (df["exit"] - df["entry"]) / df["entry"] * 100.0
        df["yr"] = pd.to_datetime(df.index).year
        p(f"=== H118 Phase 2：CDF 盤前延伸 → 做多 TX (EOD) ===")
        p(f"可交易日（CDF 盤前達流動性 & TX 有進出場價）：N={len(df)}"
          f"（{df.index.min()} ~ {df.index.max()}）")
        p(f"無條件每日做多基準: {fmt(stats(df['pnl_pct']))}")

        # ---- θ 敏感度（全期）----
        p("\n=== θ 門檻敏感度（全期，CDF ext@09:00 ≥ θ 做多）===")
        for th in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]:
            sub = df[df["ext_09:00"] >= th]
            p(f"  θ≥{th:>4}: {fmt(stats(sub['pnl_pct']))}")

        # ---- IS / OOS（θ=0.20）----
        TH = 0.20
        p(f"\n=== IS(2021–2024) / OOS(2025–2026)，θ≥{TH} ===")
        sig = df[df["ext_09:00"] >= TH]
        IS = sig[sig["yr"] <= 2024]; OOS = sig[sig["yr"] >= 2025]
        p(f"  IS : {fmt(stats(IS['pnl_pct']))}")
        p(f"  OOS: {fmt(stats(OOS['pnl_pct']))}")
        # 對照無條件
        bIS = df[df["yr"] <= 2024]; bOOS = df[df["yr"] >= 2025]
        p(f"  (基準 IS  always-long: {fmt(stats(bIS['pnl_pct']))})")
        p(f"  (基準 OOS always-long: {fmt(stats(bOOS['pnl_pct']))})")

        # ---- 逐年 walk-forward（θ=0.20）----
        p(f"\n=== 逐年 walk-forward（θ≥{TH}）vs 該年無條件做多 ===")
        for yr, g in df.groupby("yr"):
            s_sig = stats(g[g["ext_09:00"] >= TH]["pnl_pct"])
            s_all = stats(g["pnl_pct"])
            p(f"  {yr}: 訊號 {fmt(s_sig)}")
            p(f"        基準 {fmt(s_all)}")

        # ---- 成本敏感度（θ=0.20，全期；TX 1點≈進場價的 ~0.005%）----
        p(f"\n=== 成本敏感度（θ≥{TH}，全期；扣每趟 round-trip 成本%）===")
        for c in [0.0, 0.01, 0.02, 0.05]:
            p(f"  成本{c}%/趟: {fmt(stats(sig['pnl_pct'], cost_pct=c))}")

        # ============ TARGET-EXIT：捕捉 Phase 1 預測的「reach」====================
        # EOD 吃不到擺幅 → 改在關卡目標出場。target=L3/L4，stop 用對稱下檔。
        txf = tx_features(conn)[["o", "ema20"]]
        path = tx_path(conn)
        dft = df.join(txf, how="inner").dropna(subset=["o", "ema20"])

        p("\n\n========== TARGET-EXIT（捕捉 reach）==========")
        p(f"進場 09:01 做多；target=open+M×EMA20；stop=open−S×EMA20；否則 EOD。θ≥{TH}")
        sig_t = dft[dft["ext_09:00"] >= TH]
        for tgt_name, M in [("L3", LADDERS["L3"]), ("L4", LADDERS["L4"])]:
            for S in [0.4, 0.6, 0.8]:
                res = sig_t.apply(lambda r: target_exit_pnl(r, path, M, S), axis=1).dropna()
                if len(res) == 0:
                    continue
                pnl = pd.Series([x[0] for x in res], index=res.index)
                outs = pd.Series([x[1] for x in res], index=res.index)
                hit = (outs == "target").mean()
                p(f"  target={tgt_name}({M}) stop={S}: {fmt(stats(pnl))}  目標達成率={hit:.0%}")

        # 最佳組合的 IS/OOS + 逐年（取 target=L3, stop=0.6 為代表，後續可調）
        BM, BS = LADDERS["L3"], 0.6
        p(f"\n=== TARGET-EXIT 代表組（target=L3, stop={BS}）IS/OOS（θ≥{TH}）===")
        def te_stats(sub):
            res = sub.apply(lambda r: target_exit_pnl(r, path, BM, BS), axis=1).dropna()
            if len(res) == 0:
                return stats(pd.Series([], dtype=float))
            return stats(pd.Series([x[0] for x in res]))
        p(f"  IS(≤2024) : {fmt(te_stats(sig_t[sig_t['yr']<=2024]))}")
        p(f"  OOS(≥2025): {fmt(te_stats(sig_t[sig_t['yr']>=2025]))}")
        p(f"\n=== TARGET-EXIT 代表組 逐年 walk-forward ===")
        for yr, g in sig_t.groupby("yr"):
            p(f"  {yr}: {fmt(te_stats(g))}")

    with open("research/active/H118-nyf-preopen-reach/results/backtest_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/backtest_raw.txt")


if __name__ == "__main__":
    main()

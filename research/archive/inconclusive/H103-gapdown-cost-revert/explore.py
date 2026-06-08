"""H103 跳空跌破成本→折價回補做多 — Phase 1 進出場機制探索。

條件樣本（open 跌破兩成本、up_clear_norm≥L4）已由 H102 確認 N≈111。
本階段用盤中 1m 量進出場機制：
- 回補達成率：進場後是否觸及「最近上方成本價」(=min(vwap_last,vwap_prev))，及所需時間
- MFE / MAE（以 ema20 正規化）→ 盈虧比上限、停損位置
- 進場前逆勢熱度（觸及目標前的最大不利）→ 停損能否容納
- up_clear_norm 分層 × 達成率（驗單調）
- 進場時點：開盤即進 vs 等「收復開盤價」確認
- 控制組：全 gap-down 日（含 up_clear<L4 無 edge 那組）對照

依賴：H102 已存的每日表 (archive)。
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
RECLAIM_CUTOFF = pd.Timestamp("1900-01-01 11:00:00").time()
EXIT_T = pd.Timestamp("1900-01-01 13:30:00").time()


def load_intraday(dates) -> dict:
    dset = ", ".join(f"DATE '{d}'" for d in dates)
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            f"""
            SELECT CAST(timestamp AS DATE) d, timestamp ts, open, high, low, close
            FROM ohlcv_1m WHERE symbol='TX'
              AND CAST(timestamp AS DATE) IN ({dset})
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY ts
            """
        ).df()
    for col in ("open", "high", "low", "close"):
        bars[col] = bars[col].astype(float)
    bars["t"] = pd.to_datetime(bars["ts"]).dt.time
    bars["mins"] = (pd.to_datetime(bars["ts"]).dt.hour * 60
                    + pd.to_datetime(bars["ts"]).dt.minute) - (8 * 60 + 45)
    return {pd.Timestamp(d).date(): g.reset_index(drop=True)
            for d, g in bars.groupby("d")}


def trade_at_open(g, target, ema20):
    """進場=08:45 open，做多。回傳回補/MFE/MAE 等。"""
    entry = float(g["open"].iloc[0])
    post = g[g["t"] <= EXIT_T]
    hi, lo = post["high"].to_numpy(), post["low"].to_numpy()
    mins = post["mins"].to_numpy()
    hit_idx = np.where(hi >= target)[0]
    hit = len(hit_idx) > 0
    t_hit = int(mins[hit_idx[0]]) if hit else np.nan
    # 觸及目標前的最大不利（熱度）
    if hit:
        heat = entry - lo[: hit_idx[0] + 1].min()
    else:
        heat = entry - lo.min()
    return dict(entry=entry, hit=float(hit), t_hit=t_hit,
                mfe=float(hi.max() - entry), mae=float(entry - lo.min()),
                heat=float(heat),
                mfe_n=(hi.max() - entry) / ema20,
                mae_n=(entry - lo.min()) / ema20,
                heat_n=heat / ema20)


def trade_reclaim(g, target, ema20):
    """進場=首次收復開盤價（close>open）之收盤；11:00 前未收復則不進場。"""
    open0 = float(g["open"].iloc[0])
    cand = g[(g["mins"] > 0) & (g["t"] <= RECLAIM_CUTOFF) & (g["close"] > open0)]
    if len(cand) == 0:
        return None
    erow = cand.iloc[0]
    entry = float(erow["close"])
    eidx = erow.name
    post = g[(g.index >= eidx) & (g["t"] <= EXIT_T)]
    hi, lo = post["high"].to_numpy(), post["low"].to_numpy()
    hit = bool((hi >= target).any())
    return dict(entry=entry, hit=float(hit), entry_min=int(erow["mins"]),
                mfe_n=(hi.max() - entry) / ema20, mae_n=(entry - lo.min()) / ema20)


def pctl(s, ps=(25, 50, 75, 90)):
    s = pd.Series(s).dropna()
    return "  ".join(f"p{p}={np.percentile(s, p):.2f}" for p in ps) if len(s) else "—"


def main():
    daily = pd.read_csv(DAILY_CSV, parse_dates=[0], index_col=0)
    gd = daily[daily["n_above"] == 2].copy()          # 跳空下方（open 在兩成本之下）
    gd["target"] = gd[["vwap_last", "vwap_prev"]].min(axis=1)   # 最近上方成本

    groups = {
        "主訊號 ≥L4 (L4–L5 + >L5)": gd[gd["up_clear_norm"] >= L4C],
        "  └ L4–L5": gd[(gd["up_clear_norm"] >= L4C) & (gd["up_clear_norm"] < L5C)],
        "  └ >L5": gd[gd["up_clear_norm"] >= L5C],
        "控制組 <L4 (近成本)": gd[gd["up_clear_norm"] < L4C],
    }
    intr = load_intraday([d.date() for d in gd.index])

    print("=" * 78)
    print(f"  H103 進場=開盤即做多  |  目標=最近上方成本  |  gap-down 總 N={len(gd)}")
    print(f"  全 gap-down baseline: 觸成本率(at open) = "
          f"{np.mean([trade_at_open(intr[d.date()], r.target, r.ema20)['hit'] for d,r in gd.iterrows()]):.0%}")
    print("=" * 78)
    print(f"{'分組':<24}{'N':>4} {'觸成本率':>7} {'MAE>MFE率':>9} "
          f"{'熱度n中位':>9} {'到價分(中位)':>11}")
    rows = {}
    for name, sub in groups.items():
        recs = [trade_at_open(intr[d.date()], r.target, r.ema20) for d, r in sub.iterrows()]
        rdf = pd.DataFrame(recs)
        rows[name] = rdf
        bad = (rdf["mae"] > rdf["mfe"]).mean()
        thit = rdf["t_hit"].dropna()
        print(f"{name:<24}{len(sub):>4} {rdf['hit'].mean():>7.0%} {bad:>9.0%} "
              f"{rdf['heat_n'].median():>9.2f} "
              f"{(thit.median() if len(thit) else float('nan')):>9.0f}分")

    main_df = rows["主訊號 ≥L4 (L4–L5 + >L5)"]
    print("\n--- 主訊號組 分佈（正規化 /ema20）---")
    print(f"  MFE_n  : {pctl(main_df['mfe_n'])}")
    print(f"  MAE_n  : {pctl(main_df['mae_n'])}")
    print(f"  熱度_n(觸目標前最大不利): {pctl(main_df['heat_n'])}")
    print(f"  目標距離 up_clear_norm  : {pctl(groups['主訊號 ≥L4 (L4–L5 + >L5)']['up_clear_norm'])}")

    # 停損可行性：觸目標前的熱度 vs 目標距離（盈虧比）
    sub = groups["主訊號 ≥L4 (L4–L5 + >L5)"]
    md = main_df.copy()
    md["clear_n"] = sub["up_clear_norm"].values
    hit = md[md["hit"] == 1]
    print(f"\n--- 停損/盈虧比可行性（主訊號，達成 N={len(hit)}）---")
    print(f"  達成日：觸目標前熱度_n 分佈: {pctl(hit['heat_n'])}")
    print(f"  → 若停損設在 0.4×ema20 之下，達成日中熱度<0.4 比率 = "
          f"{(hit['heat_n'] < 0.4).mean():.0%}（不被洗掉）")
    print(f"  目標距離(clear_n) 中位 = {md['clear_n'].median():.2f}×ema20 "
          f"→ 對 0.4 停損的 R:R ≈ {md['clear_n'].median()/0.4:.1f}")

    # 進場時點對照：reclaim
    print("\n--- 進場時點對照：等『收復開盤價』再進（主訊號組）---")
    rec = [trade_reclaim(intr[d.date()], r.target, r.ema20) for d, r in sub.iterrows()]
    rec_ok = [x for x in rec if x is not None]
    notrade = sum(1 for x in rec if x is None)
    rdf = pd.DataFrame(rec_ok)
    print(f"  可進場 N={len(rec_ok)}（未收復不進 N={notrade}）  "
          f"觸成本率={rdf['hit'].mean():.0%}  "
          f"進場時間中位={rdf['entry_min'].median():.0f}分  "
          f"MAE_n中位={rdf['mae_n'].median():.2f}（vs 開盤即進 {main_df['mae_n'].median():.2f}）")

    # === 修正：目標改固定 reach 距離（非成本），路徑模擬 target×ema20 / stop×ema20 ===
    def sim_ts(g, ema20, T, S):
        entry = float(g["open"].iloc[0])
        post = g[g["t"] <= EXIT_T]
        tp, sl = entry + T * ema20, entry - S * ema20
        for _, b in post.iterrows():
            hit_sl = b["low"] <= sl
            hit_tp = b["high"] >= tp
            if hit_sl:            # 同根先停損（保守）
                return -S
            if hit_tp:
                return T
        return (float(post["close"].iloc[-1]) - entry) / ema20   # 收盤平倉

    print("\n" + "=" * 78)
    print("  固定目標×停損 路徑模擬（進場=開盤即多，單位=×ema20，期望值E=每筆均損益）")
    print("=" * 78)
    sim_groups = {
        "主訊號 ≥L4": groups["主訊號 ≥L4 (L4–L5 + >L5)"],
        "控制 <L4": groups["控制組 <L4 (近成本)"],
        "全 gap-down": gd,
    }
    for T, S in [(0.5, 0.5), (0.7, 0.5), (0.5, 0.4), (0.7, 0.7), (1.0, 0.5)]:
        print(f"\n  目標 {T:.1f} / 停損 {S:.1f}  (R:R={T/S:.1f}):")
        for name, sub in sim_groups.items():
            pnl = np.array([sim_ts(intr[d.date()], r.ema20, T, S) for d, r in sub.iterrows()])
            win = (pnl > 0).mean()
            print(f"    {name:<14} N={len(sub):>4}  勝率={win:>4.0%}  "
                  f"E={pnl.mean():>+6.3f}×ema20  總={pnl.sum():>+7.2f}")

    md.to_csv(Path(__file__).resolve().parent / "results" / "h103_trades.csv")
    print("\n[saved] results/h103_trades.csv")


if __name__ == "__main__":
    main()

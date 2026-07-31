#!/usr/bin/env python3
"""H140 Phase 2 — 相對廣度溫度濾網回測

設計：post-processing（沿用 H079-K 的 h079k_filter.py 模式，不改 S002 原碼）

**關鍵修正 vs Phase 1**
Phase 1 把交易日 D 與 D 當日的 pct1y 對齊，但 stock_day / market_breadth 的 D 日資料
要到 D 收盤後才公布，S002 是日盤盤中進場 → 屬 lookahead。
本階段預設 LAG=1（交易日 D 只能用 D-1 為止的溫度），並保留 LAG=0 對照以量化差距。

規則
----
- baseline      全做
- A_fixed       pct1y < 0.80 全跳過（固定門檻，in-sample 參考用）
- A_wf          門檻由 walk-forward 逐年決定（只用該年之前的資料挑）
- B_scale_k     冷期降強度至 k 倍（k = 0.50 / 0.33）
- C_combo       H140 溫度 + H079 絕對門檻 defense window 併用

前置：
    uv run python strategies/live/S002-reversal/backtest.py --start 2021-01-01
    → output/s002_reversal_2021-01-01.csv

執行：
    MPLBACKEND=Agg uv run python research/active/H140-relative-breadth-temp/backtest.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.analysis.breadth_thermometer import (
    load_breadth_history, annotate, MA_DAYS, PCT_LOOKBACK,
)

HERE = Path(__file__).parent
RESULTS = HERE / "results"
TRADES_CSV = Path("output/s002_reversal_2021-01-01.csv")
DB_PATH = "data/futures.duckdb"

LAG = 1                      # 交易日 D 只能用 D-LAG 為止的溫度
OOS_START = pd.Timestamp("2024-01-01")
THRESHOLD_GRID = [0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
LOOKBACK_GRID = [125, 250, 375]
WF_MIN_PRIOR_YEARS = 2       # walk-forward 至少要幾年歷史才開始挑門檻


# ─────────────────────────── 資料 ───────────────────────────

def rolling_pctile(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=max(60, window // 2)).apply(
        lambda a: (a[:-1] < a[-1]).mean(), raw=True)


def load_daily(lag: int = LAG) -> pd.DataFrame:
    """每日溫度表。pct 欄位已 shift(lag)，可直接與交易日對齊。"""
    df, _ = annotate(load_breadth_history(lookback_years=9))
    df["d"] = pd.to_datetime(df["trade_date"]).astype("datetime64[ns]")
    for w in LOOKBACK_GRID:
        df[f"pct{w}"] = rolling_pctile(df["lu_ratio_ma"], w).shift(lag)
    df["pct1y"] = df[f"pct{PCT_LOOKBACK}"]
    df["in_defense"] = df["defense"].shift(lag).fillna(False).astype(bool)   # H079 絕對門檻
    return df


def load_trades(daily: pd.DataFrame) -> pd.DataFrame:
    t = pd.read_csv(TRADES_CSV, parse_dates=["EntryTime", "ExitTime"])
    t["d"] = t["EntryTime"].dt.normalize().astype("datetime64[ns]")
    t["pts"] = t["PnL"]                       # size=1 → PnL 即點數
    t["ret_pct"] = t["PnL"] / t["EntryPrice"] * 100   # 跨年度可比（CLAUDE.md 規範）
    cols = ["d", "pct1y", "in_defense"] + [f"pct{w}" for w in LOOKBACK_GRID]
    m = t.merge(daily[cols], on="d", how="left")
    m = m.dropna(subset=["pct1y"]).reset_index(drop=True)
    m["yr"] = m.d.dt.year
    return m


# ─────────────────────────── 績效 ───────────────────────────

def max_dd(v: pd.Series) -> float:
    c = v.cumsum()
    return float((c - c.cummax()).min()) if len(v) else 0.0


def max_losing_streak(v: pd.Series) -> int:
    best = cur = 0
    for p in v:
        cur = cur + 1 if p <= 0 else 0
        best = max(best, cur)
    return best


def perf(df: pd.DataFrame, years: float, w: pd.Series | None = None) -> dict:
    """w = 每筆權重（降強度用）。years 用於依實際交易頻率年化 Sharpe。"""
    if len(df) == 0:
        return dict(N=0)
    weight = pd.Series(1.0, index=df.index) if w is None else w
    pts = df["pts"] * weight
    ret = df["ret_pct"] * weight
    active = ret[weight > 0]
    n_active = int((weight > 0).sum())
    trades_per_yr = n_active / years if years > 0 else 0
    sd = ret.std()
    return dict(
        N=n_active,
        exposure=round(float(weight.sum()) / len(df), 2),
        win_pct=round(100 * (active > 0).mean(), 1) if n_active else 0.0,
        avg_pts=round(pts[weight > 0].mean(), 1) if n_active else 0.0,
        avg_ret=round(active.mean(), 3) if n_active else 0.0,
        total_pts=round(pts.sum(), 0),
        total_ret=round(ret.sum(), 1),
        # 依實際交易頻率年化（filter 減少交易數時不會被高估）
        sharpe=round(float(ret.mean() / sd * np.sqrt(trades_per_yr)), 2) if sd and sd > 0 else 0.0,
        # H079-K 的舊慣例（固定 sqrt(252)），僅供對照
        sharpe_252=round(float(ret.mean() / sd * np.sqrt(252)), 2) if sd and sd > 0 else 0.0,
        maxDD_ret=round(max_dd(ret), 2),
        maxDD_pts=round(max_dd(pts), 0),
        streak=max_losing_streak(ret[weight > 0]) if n_active else 0,
    )


def span_years(df: pd.DataFrame) -> float:
    return max((df.d.max() - df.d.min()).days / 365.25, 1e-9) if len(df) else 1.0


# ─────────────────────────── 規則 ───────────────────────────

def weights_for(rule: str, df: pd.DataFrame, wf_thr: pd.Series | None = None) -> pd.Series:
    hot80 = df.pct1y >= 0.80
    if rule == "baseline":
        return pd.Series(1.0, index=df.index)
    if rule == "A_fixed":
        return hot80.astype(float)
    if rule in ("A_wf", "A_wf_sharpe"):
        return (df.pct1y >= wf_thr).astype(float)
    if rule.startswith("B_scale_"):
        k = float(rule.split("_")[-1])
        return np.where(hot80, 1.0, k).astype(float) * pd.Series(1.0, index=df.index)
    if rule == "C_combo":
        return (hot80 & ~df.in_defense).astype(float)
    if rule == "H079_only":
        return (~df.in_defense).astype(float)
    raise ValueError(rule)


def walk_forward_thresholds(df: pd.DataFrame, objective: str = "mean") -> tuple[pd.Series, dict]:
    """逐年用『該年之前的資料』挑最佳門檻。歷史不足則不濾（門檻 0）。

    objective:
      mean   — 平均 ret_pct（會退化：avg_ret 對門檻單調遞增 → 永遠挑最高格）
      sharpe — mean/std × sqrt(交易頻率)，會同時懲罰交易數過少
    """
    thr = pd.Series(0.0, index=df.index)
    chosen = {}
    for y in sorted(df.yr.unique()):
        prior = df[df.yr < y]
        if prior.yr.nunique() < WF_MIN_PRIOR_YEARS:
            chosen[y] = 0.0
            continue
        yrs = span_years(prior)
        best, best_score = 0.0, -np.inf
        for t in THRESHOLD_GRID:
            s = prior[prior.pct1y >= t]["ret_pct"]
            if len(s) < 20 or s.std() == 0:
                continue
            score = s.mean() if objective == "mean" else \
                float(s.mean() / s.std() * np.sqrt(len(s) / yrs))
            if score > best_score:
                best, best_score = t, score
        chosen[y] = best
        thr.loc[df.yr == y] = best
    return thr, chosen


# ─────────────────────────── 主流程 ───────────────────────────

def evaluate(df: pd.DataFrame, wf: dict[str, pd.Series], label: str) -> pd.DataFrame:
    rules = ["baseline", "H079_only", "A_fixed", "A_wf", "A_wf_sharpe",
             "B_scale_0.5", "B_scale_0.33", "C_combo"]
    rows = []
    for split, mask in [("Full", pd.Series(True, index=df.index)),
                        ("IS 2021-2023", df.d < OOS_START),
                        ("OOS 2024-2026", df.d >= OOS_START)]:
        sub = df[mask]
        yrs = span_years(sub)
        for r in rules:
            thr = wf[r][mask] if r in wf else None
            rows.append(dict(scope=label, split=split, rule=r,
                             **perf(sub, yrs, weights_for(r, sub, thr))))
    return pd.DataFrame(rows)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    print(f"{'='*110}\nH140 Phase 2 — S002 Reversal × 相對廣度溫度濾網\n{'='*110}")

    daily = load_daily(LAG)
    df = load_trades(daily)
    print(f"母體 N={len(df)}  {df.d.min().date()} ~ {df.d.max().date()}  "
          f"LAG={LAG}（交易日 D 只用 D-{LAG} 為止的溫度）\n")

    wf_thr, chosen = walk_forward_thresholds(df, "mean")
    wf_shp, chosen_s = walk_forward_thresholds(df, "sharpe")
    wf = {"A_wf": wf_thr, "A_wf_sharpe": wf_shp}
    print("Walk-forward 逐年選定門檻（只用該年之前資料）：")
    for y in chosen:
        nm = len(df[df.yr == y])
        nm_m = int((df[df.yr == y].pct1y >= chosen[y]).sum()) if chosen[y] else nm
        nm_s = int((df[df.yr == y].pct1y >= chosen_s[y]).sum()) if chosen_s[y] else nm
        print(f"  {y}: mean目標 {chosen[y] or '不濾'} ({nm_m}/{nm} 筆)   "
              f"sharpe目標 {chosen_s[y] or '不濾'} ({nm_s}/{nm} 筆)")
    print()

    res = evaluate(df, wf, f"LAG={LAG}")

    show = ["split", "rule", "N", "exposure", "win_pct", "avg_ret", "total_ret",
            "sharpe", "maxDD_ret", "streak", "avg_pts", "total_pts"]
    for split in ["Full", "IS 2021-2023", "OOS 2024-2026"]:
        print(f"=== {split} ===")
        print(res[res.split == split][show].to_string(index=False), "\n")

    # ── LAG 0 對照：量化 Phase 1 的 lookahead 幅度 ──
    df0 = load_trades(load_daily(0))
    res0 = evaluate(df0, {"A_wf": walk_forward_thresholds(df0, "mean")[0],
                          "A_wf_sharpe": walk_forward_thresholds(df0, "sharpe")[0]}, "LAG=0")
    print("=== LAG 敏感度（A_fixed，量化 Phase 1 lookahead 幅度）===")
    cmp = pd.concat([res0[res0.rule.isin(["baseline", "A_fixed"])],
                     res[res.rule.isin(["baseline", "A_fixed"])]])
    print(cmp[["scope", "split", "rule", "N", "avg_ret", "total_ret", "sharpe",
               "maxDD_ret", "streak"]].to_string(index=False), "\n")

    # ── 參數敏感度：門檻 × 回看窗（分 IS / OOS）──
    sens = []
    for w in LOOKBACK_GRID:
        col = f"pct{w}"
        d = df.dropna(subset=[col])
        for t in THRESHOLD_GRID:
            for split, mask in [("IS", d.d < OOS_START), ("OOS", d.d >= OOS_START)]:
                s = d[mask]
                if not len(s):
                    continue
                wt = (s[col] >= t).astype(float)
                p = perf(s, span_years(s), wt)
                sens.append(dict(lookback=w, thr=t, split=split, **p))
    sens_df = pd.DataFrame(sens)
    print("=== 參數敏感度：門檻 × 回看窗（avg_ret %／N）===")
    piv_ret = sens_df.pivot_table(index=["lookback", "thr"], columns="split", values="avg_ret")
    piv_n = sens_df.pivot_table(index=["lookback", "thr"], columns="split", values="N")
    piv = piv_ret.join(piv_n, rsuffix="_N")
    print(piv.round(3).to_string(), "\n")

    # ── 逐年（walk-forward 規則）──
    print("=== 逐年：baseline vs A_wf_sharpe vs B_scale_0.5 ===")
    yr_rows = []
    for y, s in df.groupby("yr"):
        yrs = span_years(s)
        for r in ["baseline", "A_wf_sharpe", "B_scale_0.5"]:
            w = weights_for(r, s, wf_shp[s.index] if r == "A_wf_sharpe" else None)
            yr_rows.append(dict(yr=y, rule=r, **perf(s, yrs, w)))
    yr_df = pd.DataFrame(yr_rows)
    print(yr_df.pivot_table(index="yr", columns="rule",
                            values=["N", "avg_ret", "total_ret"]).round(3).to_string(), "\n")

    res.to_csv(RESULTS / "bt_summary.csv", index=False)
    res0.to_csv(RESULTS / "bt_summary_lag0.csv", index=False)
    sens_df.to_csv(RESULTS / "bt_sensitivity.csv", index=False)
    yr_df.to_csv(RESULTS / "bt_by_year.csv", index=False)
    print(f"CSV → {RESULTS}/")


if __name__ == "__main__":
    main()

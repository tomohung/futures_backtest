#!/usr/bin/env python3
"""H140 Phase 1 — 相對廣度溫度 vs S002 Reversal 分佈探索

主張：
  A  S002 正期望值集中在 pct1y >= 0.80（漲停成交額占比 ma7 的 1 年滾動百分位）
  B  該效果不能被「前 20 日跌勢」或「20 日高波動」完整解釋（增量檢定，關鍵）
  C  若 A+B 成立，改用降強度而非全停

前置：
    uv run python strategies/live/S002-reversal/backtest.py --start 2021-01-01
    → output/s002_reversal_2021-01-01.csv

執行：
    MPLBACKEND=Agg uv run python research/active/H140-relative-breadth-temp/explore.py

產出：results/*.csv + results/h140_distribution.png
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.analysis.breadth_thermometer import load_breadth_history, annotate
from src.analysis.chart_style import (
    apply_style, style_axes,
    COLOR_UP, COLOR_DOWN, COLOR_ACCENT_ORANGE, COLOR_ACCENT_BLUE,
    COLOR_ACCENT_GOLD, COLOR_TEXT, COLOR_GRID, BG_FIG,
)

HERE = Path(__file__).parent
RESULTS = HERE / "results"
TRADES_CSV = Path("output/s002_reversal_2021-01-01.csv")
DB_PATH = "data/futures.duckdb"

LOOKBACK_DEFAULT = 250
HOT_DEFAULT = 0.80
THRESHOLD_SCAN = [0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
LOOKBACK_SCAN = [125, 250, 375]


# ─────────────────────────── 資料 ───────────────────────────

def rolling_pctile(s: pd.Series, window: int) -> pd.Series:
    """當日值在過去 window-1 天中的百分位。只比對過去，無前視。"""
    return s.rolling(window, min_periods=max(60, window // 2)).apply(
        lambda a: (a[:-1] < a[-1]).mean(), raw=True)


def load_temperature() -> pd.DataFrame:
    th, _ = annotate(load_breadth_history(lookback_years=9))
    th["d"] = pd.to_datetime(th["trade_date"]).astype("datetime64[ns]")
    for w in LOOKBACK_SCAN:
        th[f"pct{w}"] = rolling_pctile(th["lu_ratio_ma"], w)
    th["pct1y"] = th[f"pct{LOOKBACK_DEFAULT}"]
    return th


def load_price_context() -> pd.DataFrame:
    """TX 日收盤 → 前 20 日報酬 / 20 日已實現波動，shift(1) 只用到前一日為止。"""
    sql = """SELECT CAST(timestamp AS DATE) d, last(adj_close ORDER BY timestamp) c
             FROM ohlcv_1m GROUP BY 1 ORDER BY 1"""
    with duckdb.connect(DB_PATH, read_only=True) as con:
        px = con.execute(sql).fetchdf()
    px["d"] = pd.to_datetime(px["d"]).astype("datetime64[ns]")
    px["ret20"] = px["c"].pct_change(20)
    px["vol20"] = px["c"].pct_change().rolling(20).std()
    px[["ret20", "vol20"]] = px[["ret20", "vol20"]].shift(1)
    return px


def build_sample() -> pd.DataFrame:
    t = pd.read_csv(TRADES_CSV, parse_dates=["EntryTime"])
    t["d"] = t["EntryTime"].dt.normalize().astype("datetime64[ns]")
    t["pts"] = t["PnL"]                      # size=1 → PnL 即點數
    th, px = load_temperature(), load_price_context()
    cols = ["d", "lu_ratio_ma", "pct1y", "up_limit_count"] + [f"pct{w}" for w in LOOKBACK_SCAN]
    m = (t.merge(th[cols], on="d", how="left")
           .merge(px[["d", "ret20", "vol20"]], on="d", how="left"))
    m = m.dropna(subset=["pct1y", "ret20", "vol20"]).reset_index(drop=True)
    m["yr"] = m.d.dt.year
    m["down"] = m.ret20 < 0
    m["hivol"] = m.vol20 > m.vol20.median()
    return m


# ─────────────────────────── 指標 ───────────────────────────

def max_dd(v: pd.Series) -> float:
    c = v.cumsum()
    return float((c - c.cummax()).min()) if len(v) else 0.0


def max_losing_streak(v: pd.Series) -> int:
    best = cur = 0
    for p in v:
        cur = cur + 1 if p <= 0 else 0
        best = max(best, cur)
    return best


def describe(v: pd.Series) -> dict:
    return dict(N=len(v), mean=round(v.mean(), 1) if len(v) else 0.0,
                total=round(v.sum(), 0), win_pct=round(100 * (v > 0).mean(), 1) if len(v) else 0.0,
                maxDD=round(max_dd(v), 0), max_streak=max_losing_streak(v))


# ─────────────────────────── 各步驟 ───────────────────────────

def step_quintiles(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, label in [("lu_ratio_ma", "ma7 絕對值"), ("pct1y", "pct1y 相對溫度")]:
        x = m.copy()
        x["b"] = pd.qcut(x[col], 5, duplicates="drop")
        for b, s in x.groupby("b", observed=True):
            rows.append(dict(metric=label, bucket=str(b), **describe(s.pts)))
    out = pd.DataFrame(rows)
    print("=== 1. 五分位分佈 ===")
    print(out.to_string(index=False), "\n")
    return out


def step_incremental(m: pd.DataFrame, hot: float = HOT_DEFAULT) -> tuple[pd.DataFrame, pd.DataFrame]:
    x = m.copy()
    x["hot"] = x.pct1y >= hot

    rows = []
    for (h, d), s in x.groupby(["hot", "down"]):
        rows.append(dict(cell=f"{'熱' if h else '冷'}×{'跌勢' if d else '漲勢'}", **describe(s.pts)))
    for (h, v), s in x.groupby(["hot", "hivol"]):
        rows.append(dict(cell=f"{'熱' if h else '冷'}×{'高波' if v else '低波'}", **describe(s.pts)))
    cross = pd.DataFrame(rows)
    print(f"=== 2a. 增量檢定：溫度(>={hot}) × 趨勢 / 波動 交叉 ===")
    print(cross.to_string(index=False), "\n")

    # 子格內的溫度差距（B 的核心數字）
    print("=== 2b. 控制後的溫度增量（同一控制格內 熱 − 冷）===")
    gaps = []
    for ctrl_col, names in [("down", {False: "漲勢", True: "跌勢"}),
                            ("hivol", {False: "低波", True: "高波"})]:
        for val, nm in names.items():
            sub = x[x[ctrl_col] == val]
            h, c = sub[sub.hot].pts, sub[~sub.hot].pts
            if len(h) == 0 or len(c) == 0:
                continue
            tt = stats.ttest_ind(h, c, equal_var=False)
            gaps.append(dict(control=nm, N_hot=len(h), N_cold=len(c),
                             mean_hot=round(h.mean(), 1), mean_cold=round(c.mean(), 1),
                             gap=round(h.mean() - c.mean(), 1),
                             p=round(float(tt.pvalue), 4)))
    gap_df = pd.DataFrame(gaps)
    print(gap_df.to_string(index=False), "\n")

    # 三種濾網比較
    print("=== 2c. 濾網比較（同一母體）===")
    variants = {
        "baseline 全做":     x,
        "只用趨勢 (漲勢才做)": x[~x.down],
        "只用溫度 (熱才做)":   x[x.hot],
        "兩者併用":           x[x.hot & ~x.down],
    }
    comp = pd.DataFrame([dict(rule=k, **describe(v.pts)) for k, v in variants.items()])
    print(comp.to_string(index=False), "\n")
    return cross, pd.concat([gap_df.assign(kind="gap"), comp.assign(kind="filter")], ignore_index=True)


def step_robust(m: pd.DataFrame) -> pd.DataFrame:
    rows = []

    print("=== 3a. 逐年拆解 ===")
    x = m.copy()
    x["hot"] = x.pct1y >= HOT_DEFAULT
    for yr, s in x.groupby("yr"):
        h, c = s[s.hot].pts, s[~s.hot].pts
        rows.append(dict(test="by_year", key=str(yr), N_hot=len(h), N_cold=len(c),
                         mean_hot=round(h.mean(), 1) if len(h) else np.nan,
                         mean_cold=round(c.mean(), 1) if len(c) else np.nan,
                         total_hot=round(h.sum(), 0), total_cold=round(c.sum(), 0)))
    by_year = pd.DataFrame([r for r in rows if r["test"] == "by_year"])
    print(by_year.to_string(index=False), "\n")

    print("=== 3b. Leave-one-year-out（剔除單年後熱桶是否仍為正）===")
    loo = []
    for yr in sorted(x.yr.unique()):
        s = x[x.yr != yr]
        h = s[s.hot].pts
        loo.append(dict(test="LOO", key=f"排除{yr}", N_hot=len(h),
                        mean_hot=round(h.mean(), 1), total_hot=round(h.sum(), 0),
                        mean_cold=round(s[~s.hot].pts.mean(), 1), N_cold=len(s[~s.hot]),
                        total_cold=round(s[~s.hot].pts.sum(), 0)))
    loo_df = pd.DataFrame(loo)
    print(loo_df.to_string(index=False), "\n")

    print("=== 3c. 門檻敏感度（是否單調）===")
    scan = []
    for th_ in THRESHOLD_SCAN:
        h, c = x[x.pct1y >= th_].pts, x[x.pct1y < th_].pts
        scan.append(dict(test="thr_scan", key=f"p{int(th_*100)}",
                         N_hot=len(h), mean_hot=round(h.mean(), 1), total_hot=round(h.sum(), 0),
                         N_cold=len(c), mean_cold=round(c.mean(), 1), total_cold=round(c.sum(), 0),
                         maxDD_hot=round(max_dd(h), 0), streak_hot=max_losing_streak(h)))
    scan_df = pd.DataFrame(scan)
    print(scan_df.to_string(index=False), "\n")

    print("=== 3d. 回看窗敏感度 ===")
    lb = []
    for w in LOOKBACK_SCAN:
        col = f"pct{w}"
        s = m.dropna(subset=[col])
        h, c = s[s[col] >= HOT_DEFAULT].pts, s[s[col] < HOT_DEFAULT].pts
        lb.append(dict(test="lookback", key=f"{w}d", N_hot=len(h), mean_hot=round(h.mean(), 1),
                       total_hot=round(h.sum(), 0), N_cold=len(c), mean_cold=round(c.mean(), 1),
                       total_cold=round(c.sum(), 0)))
    lb_df = pd.DataFrame(lb)
    print(lb_df.to_string(index=False), "\n")

    print("=== 3e. IS / OOS（切點 2024-01-01）===")
    io = []
    for nm, lo, hi in [("IS 2021-2023", "2021-01-01", "2023-12-31"),
                       ("OOS 2024-2026", "2024-01-01", "2026-12-31")]:
        s = x[(x.d >= lo) & (x.d <= hi)]
        h, c = s[s.hot].pts, s[~s.hot].pts
        tt = stats.ttest_1samp(h, 0) if len(h) > 1 else None
        io.append(dict(test="is_oos", key=nm, N_hot=len(h), mean_hot=round(h.mean(), 1),
                       total_hot=round(h.sum(), 0), p_hot=round(float(tt.pvalue), 4) if tt else np.nan,
                       N_cold=len(c), mean_cold=round(c.mean(), 1), total_cold=round(c.sum(), 0)))
    io_df = pd.DataFrame(io)
    print(io_df.to_string(index=False), "\n")

    return pd.concat([by_year, loo_df, scan_df, lb_df, io_df], ignore_index=True)


def step_chart(m: pd.DataFrame, th: pd.DataFrame) -> Path:
    apply_style()
    x = m.copy()
    x["hot"] = x.pct1y >= HOT_DEFAULT
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 11),
                                        gridspec_kw={"height_ratios": [1, 1, 1.1]})
    fig.suptitle("H140 相對廣度溫度 vs S002 Reversal", fontsize=15,
                 fontweight="bold", color=COLOR_TEXT)
    for ax in (ax1, ax2, ax3):
        style_axes(ax)

    # (1) pct1y 時序，冷區塗色
    t = th.dropna(subset=["pct1y"])
    t = t[t.d >= "2021-01-01"]
    ax1.plot(t.d, t.pct1y, color=COLOR_ACCENT_GOLD, linewidth=1.1)
    ax1.axhline(HOT_DEFAULT, color=COLOR_DOWN, linestyle="--", linewidth=1.5,
                label=f"熱門檻 p{int(HOT_DEFAULT*100)}")
    ax1.fill_between(t.d, 0, 1, where=(t.pct1y < HOT_DEFAULT),
                     color=COLOR_ACCENT_BLUE, alpha=0.10, step="mid")
    ax1.set_ylabel("pct1y 相對溫度")
    ax1.set_ylim(0, 1)
    ax1.legend(fontsize=9, facecolor=BG_FIG, edgecolor=COLOR_GRID, loc="lower left")
    ax1.set_title("藍色區 = 相對冷（pct1y < 0.80）", fontsize=11)

    # (2) 累積損益：全做 vs 只在熱時做
    ax2.plot(x.d, x.pts.cumsum(), color=COLOR_TEXT, linewidth=1.6, label="baseline 全做")
    hot = x[x.hot]
    ax2.plot(hot.d, hot.pts.cumsum(), color=COLOR_UP, linewidth=1.8, label="只在熱時做")
    cold = x[~x.hot]
    ax2.plot(cold.d, cold.pts.cumsum(), color=COLOR_ACCENT_BLUE, linewidth=1.4,
             linestyle="--", label="只在冷時做")
    ax2.axhline(0, color=COLOR_GRID, linewidth=1)
    ax2.set_ylabel("累積點數")
    ax2.legend(fontsize=9, facecolor=BG_FIG, edgecolor=COLOR_GRID, loc="upper left")
    ax2.set_title("累積損益（依進場日排序）", fontsize=11)

    # (3) 2026 放大：pct1y + 逐筆損益
    z = t[t.d >= "2026-01-01"]
    ax3.plot(z.d, z.pct1y, color=COLOR_ACCENT_GOLD, linewidth=1.6, label="pct1y")
    ax3.axhline(HOT_DEFAULT, color=COLOR_DOWN, linestyle="--", linewidth=1.5)
    ax3.set_ylabel("pct1y")
    ax3.set_ylim(0, 1.05)
    ax3b = ax3.twinx()
    z26 = x[x.d >= "2026-01-01"]
    ax3b.bar(z26.d, z26.pts, width=2.5,
             color=[COLOR_UP if p > 0 else COLOR_DOWN for p in z26.pts], alpha=0.75)
    ax3b.axhline(0, color=COLOR_GRID, linewidth=0.8)
    ax3b.set_ylabel("S002 單筆點數")
    ax3.set_title("2026 放大：相對溫度 vs S002 逐筆損益（紅=賺 綠=賠）", fontsize=11)
    ax3.legend(fontsize=9, facecolor=BG_FIG, edgecolor=COLOR_GRID, loc="lower left")

    plt.tight_layout()
    out = RESULTS / "h140_distribution.png"
    plt.savefig(out, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    m = build_sample()
    print(f"母體：N={len(m)}  {m.d.min().date()} ~ {m.d.max().date()}  "
          f"期望值={m.pts.mean():+.1f} pts  勝率={100*(m.pts>0).mean():.1f}%\n")

    q = step_quintiles(m)
    cross, inc = step_incremental(m)
    rob = step_robust(m)

    q.to_csv(RESULTS / "quintiles.csv", index=False)
    cross.to_csv(RESULTS / "cross_cells.csv", index=False)
    inc.to_csv(RESULTS / "incremental.csv", index=False)
    rob.to_csv(RESULTS / "robustness.csv", index=False)
    png = step_chart(m, load_temperature())
    print(f"圖表 → {png}")
    print(f"CSV  → {RESULTS}/")


if __name__ == "__main__":
    main()

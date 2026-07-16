#!/usr/bin/env python3
"""H139 Phase 1 — 實現波動「溫度計」預判深reach延續：分佈探索。

執行：uv run python research/active/H139-vol-temperature-forecast/explore.py

產出（research/active/H139-vol-temperature-forecast/results/）：
  - fact_daily.csv      每交易日 zero-strategy 事實表（reach 旗標 + deep-STOP + regime）
  - temp_forecast.png   溫度計時序 + 深reach事件 + 極端桶 forward 分佈
  - 文字報告印到 stdout（並存 distribution_raw.txt）

方法鐵律（snooping 防線，見 tasks.md）：
  步驟1 只看預測變數分佈 → 定桶界；步驟2 只看基準率+自相關 → 定 effective-N 門檻；
  步驟3 才揭露 forward 目標。程式輸出依此順序。
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
DB = str(ROOT / "data" / "futures.duckdb")
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
SYMBOL = "TX"

# ladder 係數（沿用 daystats LVL_QUANTILES；open-anchor、EMA20-relative）
C_L4, C_L5 = 0.977, 1.225
DEEP_STOP_CUT = 0.8          # NVF deep-STOP（沿用 key_prices _NVF_TIER_CUTS[0]）
EMA_SPAN = 20
WS = (5, 10, 20)             # trailing 視窗
HS = (1, 3, 5, 10)           # forward horizon


# ─────────────────────────────────────────────────────────────
# A. zero-strategy 事實表
# ─────────────────────────────────────────────────────────────
def load_day_facts(conn) -> pd.DataFrame:
    """每交易日日盤 open / 累積 high-low（10:30 / 11:30 / 全日）。"""
    df = conn.execute(
        """
        SELECT
            CAST(timestamp AS DATE) AS d,
            arg_min(open, timestamp) AS open,
            MAX(high) AS hi_full, MIN(low) AS lo_full,
            MAX(high) FILTER (WHERE CAST(timestamp AS TIME) <= TIME '10:30:00') AS hi_1030,
            MIN(low)  FILTER (WHERE CAST(timestamp AS TIME) <= TIME '10:30:00') AS lo_1030,
            MAX(high) FILTER (WHERE CAST(timestamp AS TIME) <= TIME '11:30:00') AS hi_1130,
            MIN(low)  FILTER (WHERE CAST(timestamp AS TIME) <= TIME '11:30:00') AS lo_1130
        FROM ohlcv_1m
        WHERE symbol = ? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
        GROUP BY 1 ORDER BY 1
        """,
        [SYMBOL],
    ).df()
    df["d"] = pd.to_datetime(df["d"])
    for col in ("open", "hi_full", "lo_full", "hi_1030", "lo_1030", "hi_1130", "lo_1130"):
        df[col] = df[col].astype(float)
    df["rng"] = df["hi_full"] - df["lo_full"]
    return df


def add_reach_flags(df: pd.DataFrame) -> pd.DataFrame:
    """causal EMA20(range)（不含當日）→ rung 門檻 → open-anchor 方向 reach 旗標。"""
    ema = df["rng"].ewm(span=EMA_SPAN, adjust=False).mean()
    df["ema20"] = ema.shift(1)          # causal：day D 用到 D-1 為止
    thr4 = C_L4 * df["ema20"]
    thr5 = C_L5 * df["ema20"]
    up_ex_full = df["hi_full"] - df["open"]
    dn_ex_full = df["open"] - df["lo_full"]
    up_ex_1130 = df["hi_1130"] - df["open"]
    dn_ex_1130 = df["open"] - df["lo_1130"]
    up_ex_1030 = df["hi_1030"] - df["open"]
    dn_ex_1030 = df["open"] - df["lo_1030"]

    df["up_L4"] = (up_ex_full >= thr4).astype(float)
    df["dn_L4"] = (dn_ex_full >= thr4).astype(float)
    df["up_L5"] = (up_ex_full >= thr5).astype(float)
    df["dn_L5"] = (dn_ex_full >= thr5).astype(float)
    df["anyL4"] = ((df["up_L4"] > 0) | (df["dn_L4"] > 0)).astype(float)
    df["anyL5"] = ((df["up_L5"] > 0) | (df["dn_L5"] > 0)).astype(float)

    df["anyL4_1130"] = ((up_ex_1130 >= thr4) | (dn_ex_1130 >= thr4)).astype(float)
    df["anyL5_1130"] = ((up_ex_1130 >= thr5) | (dn_ex_1130 >= thr5)).astype(float)
    df["anyL4_1030"] = ((up_ex_1030 >= thr4) | (dn_ex_1030 >= thr4)).astype(float)  # early-fireworks

    df.loc[df["ema20"].isna(), ["anyL4", "anyL5", "anyL4_1130", "anyL5_1130", "anyL4_1030"]] = np.nan
    return df


def load_night_deepstop(conn) -> pd.DataFrame:
    """每交易日「前一夜」night_range → causal EMA20 → deep-STOP 旗標（沿用 key_prices NVF）。

    夜盤 grouping 與 key_prices 一致：>=15:00 歸隔日、<05:00 歸當日；再映到該日(含)之後第一個交易日。
    """
    day_dates = conn.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m WHERE symbol=? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d",
        [SYMBOL],
    ).df()
    day_arr = np.array(pd.to_datetime(day_dates["d"]).tolist(), dtype="datetime64[ns]")

    nraw = conn.execute(
        "SELECT timestamp, high, low FROM ohlcv_1m WHERE symbol=? "
        "AND (CAST(timestamp AS TIME) >= TIME '15:00:00' OR CAST(timestamp AS TIME) < TIME '05:00:00') "
        "ORDER BY timestamp",
        [SYMBOL],
    ).df()
    nraw["timestamp"] = pd.to_datetime(nraw["timestamp"])
    ts = nraw["timestamp"]
    search = ts.dt.normalize().mask(ts.dt.hour >= 15, (ts + pd.Timedelta(days=1)).dt.normalize())
    idx = np.searchsorted(day_arr, search.values, side="left")
    valid = idx < len(day_arr)
    nraw["trade_date"] = pd.Series(
        np.where(valid, day_arr[np.where(valid, idx, 0)], np.datetime64("NaT")), index=nraw.index)
    nraw = nraw.dropna(subset=["trade_date"])

    night = nraw.groupby("trade_date").agg(
        nh=("high", "max"), nl=("low", "min"), nb=("high", "count"))
    night["night_range"] = night["nh"] - night["nl"]
    night = night[night["nb"] >= 100].sort_index()
    night["ema20"] = night["night_range"].ewm(span=EMA_SPAN, adjust=False).mean().shift(1)
    night["night_norm"] = night["night_range"] / night["ema20"]
    night["deep_stop"] = (night["night_norm"] < DEEP_STOP_CUT).astype(float)
    night.loc[night["ema20"].isna(), "deep_stop"] = np.nan
    return night.reset_index()[["trade_date", "night_norm", "deep_stop"]].rename(columns={"trade_date": "d"})


def build_facts() -> pd.DataFrame:
    with duckdb.connect(DB, read_only=True) as conn:
        df = add_reach_flags(load_day_facts(conn))
        night = load_night_deepstop(conn)
    df = df.merge(night, on="d", how="left")

    # vix_regime 每日標籤（因果，套用次一交易日）
    try:
        from src.analysis.vix_regime import regime_table
        rg = regime_table(DB)[["date", "regime", "level", "extreme"]].rename(columns={"date": "d"})
        rg["d"] = pd.to_datetime(rg["d"])
        df = df.merge(rg, on="d", how="left")
    except Exception as e:  # noqa
        print(f"[warn] vix_regime 併入失敗：{e}")
        df["regime"] = np.nan
    return df.sort_values("d").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# 溫度計 + forward 目標
# ─────────────────────────────────────────────────────────────
def add_gauges(df: pd.DataFrame) -> pd.DataFrame:
    """trailing 溫度計（days i-W..i-1，純過去）+ forward 目標（days i..i+H-1）。"""
    a = df["anyL4"]
    for W in WS:
        # rolling().mean() 的視窗含當日 → shift(1) 使其只含過去 W 日
        df[f"tempL4_{W}"] = a.rolling(W).mean().shift(1)
        df[f"cntL4_{W}"] = a.rolling(W).sum().shift(1)
        df[f"tempL5_{W}"] = df["anyL5"].rolling(W).mean().shift(1)
        df[f"tempDS_{W}"] = df["deep_stop"].rolling(W).mean().shift(1)
    for H in HS:
        # 未來 H 日（含當日 i）的 anyL4 率：反轉 → rolling → 反轉
        df[f"fwdL4_{H}"] = a[::-1].rolling(H).mean()[::-1]
        df[f"fwdL5_{H}"] = df["anyL5"][::-1].rolling(H).mean()[::-1]
    # 溫度方向：EMA5 vs EMA20 of 日振幅（同 vix_regime rv_dir）
    e5 = df["rng"].ewm(span=5, adjust=False).mean()
    e20 = df["rng"].ewm(span=20, adjust=False).mean()
    df["rv_up"] = (e5 >= e20).astype(float)
    return df


# ─────────────────────────────────────────────────────────────
# 分析輸出
# ─────────────────────────────────────────────────────────────
def acf(x: np.ndarray, lags: int) -> list[float]:
    x = x[~np.isnan(x)]
    x = x - x.mean()
    denom = (x * x).sum()
    return [float((x[:-k] * x[k:]).sum() / denom) if k < len(x) else float("nan")
            for k in range(1, lags + 1)]


def report(df: pd.DataFrame) -> str:
    L = []
    p = L.append
    valid = df.dropna(subset=["anyL4"])
    p("=" * 78)
    p("H139 溫度計預判 深reach延續 — Phase 1 分佈探索")
    p("=" * 78)
    p(f"樣本：N={len(valid)} 交易日  範圍 {valid['d'].min().date()} ~ {valid['d'].max().date()}")
    p("")

    # ── 步驟0：無條件基準率 ──
    p("── [基準率] 無條件 reach（全史，zero-strategy）──")
    for col, lab in [("anyL4", "any L4"), ("anyL5", "any L5"),
                     ("up_L4", "多 L4"), ("dn_L4", "空 L4"),
                     ("up_L5", "多 L5"), ("dn_L5", "空 L5"),
                     ("anyL4_1130", "any L4(≤11:30)"), ("anyL4_1030", "any L4(≤10:30)")]:
        v = df[col].dropna()
        p(f"  {lab:16s} {v.mean():5.1%}  (N={len(v)})")
    ds = df["deep_stop"].dropna()
    p(f"  {'deep-STOP 夜':16s} {ds.mean():5.1%}  (N={len(ds)})")
    p("")

    # ── 步驟2a：自相關（clustering 有多強）──
    p("── [自相關] daily anyL4 的 ACF（clustering 量級；lag=交易日）──")
    ac = acf(valid["anyL4"].values, 20)
    p("  lag  1  2  3  4  5  10  15  20")
    p("  ρ  " + "  ".join(f"{ac[k]:+.2f}" for k in [0, 1, 2, 3, 4, 9, 14, 19]))
    p("  → 若 ρ 快速衰減到 ~0，clustering 短；持續為正代表溫度計必然有『持續性』訊號（虛無①）")
    p("")

    # ── 步驟1：預測變數分佈（先看，不看 forward）→ 定桶 ──
    p("── [步驟1] 預測變數分佈：trailing L4 次數（決定桶界，未看 forward）──")
    for W in WS:
        cnt = df[f"cntL4_{W}"].dropna()
        p(f"  W={W:2d}: trailing L4 次數分佈 "
          f"min={cnt.min():.0f} q25={cnt.quantile(.25):.0f} 中位={cnt.median():.0f} "
          f"q75={cnt.quantile(.75):.0f} max={cnt.max():.0f}；=0(全冷) 佔 {(cnt==0).mean():5.1%}")
    p("  桶界主案：trailing 率 tertile（冷/中/熱，N 均衡）；輔案：L4 次數=0(極冷) vs ≥中位")
    p("")

    # ── 步驟2b：重疊 → effective N ──
    p("── [步驟2] 重疊視窗 → effective sample size（決定 GATE 門檻）──")
    p("  trailing 與 forward 視窗皆重疊 → daily 觀測不獨立。非重疊 block 數 ≈ N/(W 或 H)。")
    for W in WS:
        for H in HS:
            n_ov = len(df.dropna(subset=[f"tempL4_{W}", f"fwdL4_{H}"]))
            n_eff = n_ov / max(W, H)
            p(f"    W={W:2d} H={H:2d}: 重疊觀測 {n_ov:4d}  非重疊≈{n_eff:5.0f}")
    p("  GATE 門檻取『每桶非重疊 block ≥ ~20』→ 反推重疊觀測門檻（下方桶表附非重疊估計）")
    p("")

    # ── 步驟3：桶 → forward（揭露目標）──
    p("── [步驟3] 溫度桶 → 未來 H 日 anyL4 率（揭露 forward）──")
    base = valid["anyL4"].mean()
    p(f"  無條件基準 anyL4 = {base:.1%}（各桶對比此值看 lift）")
    for W in WS:
        for H in HS:
            sub = df.dropna(subset=[f"tempL4_{W}", f"fwdL4_{H}"]).copy()
            try:
                sub["bkt"] = pd.qcut(sub[f"tempL4_{W}"], 3, labels=["冷", "中", "熱"], duplicates="drop")
            except ValueError:
                continue
            g = sub.groupby("bkt", observed=True)[f"fwdL4_{H}"].agg(["mean", "count"])
            if len(g) < 3:
                continue
            cold, hot = g.loc["冷"], g.loc["熱"]
            spread = hot["mean"] - cold["mean"]
            # persistence 對照：冷桶自身溫度 vs 冷桶 forward（>0=續冷但反轉向上/mean-revert）
            cold_temp = sub.loc[sub["bkt"] == "冷", f"tempL4_{W}"].mean()
            hot_temp = sub.loc[sub["bkt"] == "熱", f"tempL4_{W}"].mean()
            p(f"  W={W:2d} H={H:2d}: 冷 {cold['mean']:.0%}(temp {cold_temp:.0%},N{cold['count']:.0f}/eff{cold['count']/max(W,H):.0f})"
              f" | 中 {g.loc['中','mean']:.0%}"
              f" | 熱 {hot['mean']:.0%}(temp {hot_temp:.0%},N{hot['count']:.0f}/eff{hot['count']/max(W,H):.0f})"
              f" | 冷→熱 spread {spread:+.0%}")
    p("")

    # ── 虛無①：IID 洗牌 → spread 的 null band ──
    p("── [虛無①persistence] IID 洗牌 anyL4 序列 → 桶spread 的 null 分佈（destroy clustering）──")
    rng = np.random.default_rng(42)
    for W, H in [(10, 5), (20, 5), (10, 10), (5, 3)]:
        real, nulls = _bucket_spread(df, W, H), []
        if real is None:
            continue
        a = valid["anyL4"].values.copy()
        for _ in range(500):
            sh = a.copy(); rng.shuffle(sh)
            tmp = valid.copy(); tmp["anyL4"] = sh
            tmp[f"tempL4_{W}"] = tmp["anyL4"].rolling(W).mean().shift(1)
            tmp[f"fwdL4_{H}"] = tmp["anyL4"][::-1].rolling(H).mean()[::-1]
            s = _bucket_spread(tmp, W, H)
            if s is not None:
                nulls.append(s)
        nulls = np.array(nulls)
        pctile = (nulls < real).mean() if len(nulls) else float("nan")
        p(f"  W={W:2d} H={H:2d}: 真實 spread {real:+.1%}  vs 洗牌 null "
          f"中位 {np.median(nulls):+.1%} [p5 {np.percentile(nulls,5):+.1%}, p95 {np.percentile(nulls,95):+.1%}]"
          f"  → 真實在 null 的 {pctile:.0%} 分位")
    p("  註：洗牌保留邊際基準率、破壞時間結構。真實 spread 高於 null p95 = clustering 真實存在（不意外）；")
    p("      真正的『額外 edge』要看下面 regime 分層 + 極端桶是否偏離『線性持續』。")
    p("")

    # ── 虛無②：VIX-regime 分層內，溫度是否仍分得開 ──
    p("── [虛無②VIX-regime] 同 regime 內再切 冷/熱溫度 → forward anyL4 是否仍拉開 ──")
    for W, H in [(10, 5), (20, 5), (10, 3)]:
        p(f"  ▸ W={W} H={H}")
        sub = df.dropna(subset=[f"tempL4_{W}", f"fwdL4_{H}", "regime"]).copy()
        for reg in ("升壓", "降壓"):
            s2 = sub[sub["regime"] == reg].copy()
            if len(s2) < 60:
                p(f"    {reg}: N={len(s2)} 不足"); continue
            med = s2[f"tempL4_{W}"].median()
            lo = s2[s2[f"tempL4_{W}"] <= med][f"fwdL4_{H}"]
            hi = s2[s2[f"tempL4_{W}"] > med][f"fwdL4_{H}"]
            base_r = s2[f"fwdL4_{H}"].mean()
            p(f"    {reg}: 基準 {base_r:.0%}(N{len(s2)}) | 低溫 {lo.mean():.0%}(N{len(lo)}) "
              f"高溫 {hi.mean():.0%}(N{len(hi)}) | 增量 {hi.mean()-lo.mean():+.0%}")
    p("  → 若 regime 內『高-低溫』增量≈0，代表溫度資訊已被 VIX regime 吸收（無額外 edge）")
    p("")

    # ── 虛無③：deep-STOP 對 forward 的增量是否 additive over ladder ──
    p("── [虛無③共線性] deep-STOP 夜盤 vs 日盤 ladder 溫度（是否 additive）──")
    W, H = 10, 5
    sub = df.dropna(subset=[f"tempL4_{W}", f"tempDS_{W}", f"fwdL4_{H}"]).copy()
    p(f"  corr(tempL4_{W}, tempDS_{W}) = {sub[f'tempL4_{W}'].corr(sub[f'tempDS_{W}']):+.2f}"
      f"  （高負相關=同因子代理；接近0=可能 additive）")
    # 2x2：ladder 冷/熱 × 夜盤 deep/active
    lad_med = sub[f"tempL4_{W}"].median(); ds_med = sub[f"tempDS_{W}"].median()
    for lad_hot in (False, True):
        for ds_hi in (False, True):
            m = ((sub[f"tempL4_{W}"] > lad_med) == lad_hot) & ((sub[f"tempDS_{W}"] > ds_med) == ds_hi)
            cell = sub[m][f"fwdL4_{H}"]
            p(f"    ladder{'熱' if lad_hot else '冷'}×夜盤{'多STOP' if ds_hi else '少STOP'}: "
              f"fwd {cell.mean():.0%} (N{len(cell)})")
    p("")

    p("=" * 78)
    p("關鍵判讀（給 GATE）：")
    p("  1) clustering（虛無①）必然存在 → 溫度計『有持續性』不算過關。")
    p("  2) 過關要件＝虛無②regime 內仍能拉開 forward 差距，或極端冷桶系統性偏離線性持續。")
    p("  3) 虛無③決定 deep-STOP 是否值得獨立進 tile。")
    p("=" * 78)
    return "\n".join(L)


def _bucket_spread(df: pd.DataFrame, W: int, H: int) -> float | None:
    sub = df.dropna(subset=[f"tempL4_{W}", f"fwdL4_{H}"]).copy()
    if len(sub) < 60:
        return None
    try:
        sub["bkt"] = pd.qcut(sub[f"tempL4_{W}"], 3, labels=["冷", "中", "熱"], duplicates="drop")
    except ValueError:
        return None
    g = sub.groupby("bkt", observed=True)[f"fwdL4_{H}"].mean()
    if "冷" not in g or "熱" not in g:
        return None
    return float(g["熱"] - g["冷"])


def plot(df: pd.DataFrame):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = df.dropna(subset=["anyL4", "tempL4_10"]).copy()
    fig, axes = plt.subplots(3, 1, figsize=(15, 11))

    # 1) 溫度計時序 + L4/L5 事件
    ax = axes[0]
    ax.plot(valid["d"], valid["tempL4_10"], lw=1.0, label="tempL4(W=10)", color="#d9534f")
    ax.plot(valid["d"], valid["tempL4_20"], lw=1.0, label="tempL4(W=20)", color="#c0392b", alpha=0.6)
    ax.axhline(valid["anyL4"].mean(), ls=":", color="gray", label=f"基準 {valid['anyL4'].mean():.0%}")
    l5d = valid[valid["anyL5"] > 0]
    ax.scatter(l5d["d"], [1.02] * len(l5d), s=8, color="purple", marker="v", label="anyL5 日")
    ax.set_title("H139 ladder 溫度計 tempL4 時序（含 L5 事件）")
    ax.legend(fontsize=8, ncol=4); ax.set_ylim(0, 1.08)

    # 2) 溫度 vs 未來 5 日 reach（散點 + 分桶）
    ax = axes[1]
    s = df.dropna(subset=["tempL4_10", "fwdL4_5"])
    ax.scatter(s["tempL4_10"], s["fwdL4_5"], s=5, alpha=0.15, color="#2c7fb8")
    try:
        s2 = s.copy(); s2["bkt"] = pd.qcut(s2["tempL4_10"], 3, labels=["冷", "中", "熱"], duplicates="drop")
        g = s2.groupby("bkt", observed=True).agg(x=("tempL4_10", "mean"), y=("fwdL4_5", "mean"))
        ax.plot(g["x"], g["y"], "o-", color="#d9534f", ms=9, label="tertile 桶均")
    except ValueError:
        pass
    ax.axhline(s["fwdL4_5"].mean(), ls=":", color="gray")
    ax.set_xlabel("tempL4(W=10) 過去10日 L4率"); ax.set_ylabel("未來5日 anyL4率")
    ax.set_title("溫度 → 未來深reach（散點 + tertile 桶）"); ax.legend(fontsize=8)

    # 3) regime 分層：同 regime 內 高/低溫 forward
    ax = axes[2]
    sub = df.dropna(subset=["tempL4_10", "fwdL4_5", "regime"])
    labels, lows, his = [], [], []
    for reg in ("升壓", "降壓"):
        s2 = sub[sub["regime"] == reg]
        if len(s2) < 60:
            continue
        med = s2["tempL4_10"].median()
        labels.append(f"{reg}\n(N{len(s2)})")
        lows.append(s2[s2["tempL4_10"] <= med]["fwdL4_5"].mean())
        his.append(s2[s2["tempL4_10"] > med]["fwdL4_5"].mean())
    x = np.arange(len(labels))
    ax.bar(x - 0.2, lows, 0.4, label="低溫", color="#3182bd")
    ax.bar(x + 0.2, his, 0.4, label="高溫", color="#d9534f")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.axhline(sub["fwdL4_5"].mean(), ls=":", color="gray", label="全體基準")
    ax.set_ylabel("未來5日 anyL4率")
    ax.set_title("虛無②：VIX-regime 分層內，高/低溫 forward 差距（W10 H5）"); ax.legend(fontsize=8)

    fig.tight_layout()
    out = OUT / "temp_forecast.png"
    fig.savefig(out, dpi=130)
    print(f"[圖] {out}")


def main():
    df = build_facts()
    df = add_gauges(df)
    df.to_csv(OUT / "fact_daily.csv", index=False)
    print(f"[表] {OUT / 'fact_daily.csv'}  ({len(df)} 列)")
    txt = report(df)
    print(txt)
    (OUT / "distribution_raw.txt").write_text(txt, encoding="utf-8")
    plot(df)


if __name__ == "__main__":
    main()

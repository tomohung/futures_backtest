"""
H085 Phase 1 Distribution Research
TW Fear & Greed 合成版 forward-return 驗證

從 H084 的 4 個非冗餘指標（vix_pct, taiex_dist_125ma_z, margin_drop_60d_pct, econ_score）
合成 score，找觸發日，量測未來 +60D/+120D/+250D 的 0050 含息報酬，
與 monthly DCA baseline 比較。

資料窗（4 指標皆齊全）：2017-08-31 ~ 2026-04-30（~2094 交易日）
0050 來源：yfinance 0050.TW（auto_adjust=True，含息回填）
"""

from __future__ import annotations

from pathlib import Path
import warnings

import duckdb
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
H084_DIR = PROJECT_ROOT / "research" / "active" / "H084-correction-bottom-survey"
H085_DIR = PROJECT_ROOT / "research" / "active" / "H085-fg-composite"
RESULTS_DIR = H085_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CACHE_0050 = PROJECT_ROOT / "data" / "external_sources" / "0050_TW_adj.csv"

# 4 個非冗餘指標 + 「fear 方向」
# higher composite = more fear = better buy signal
INDICATORS = {
    "vix_pct":             {"sign": +1, "label": "VIX_pct"},
    "taiex_dist_125ma_z":  {"sign": -1, "label": "z 125MA"},
    "margin_drop_60d_pct": {"sign": -1, "label": "margin_drop_60d"},
    "econ_score":          {"sign": -1, "label": "econ_score"},
}


# --------------------------------------------------------------------------
# Step 1.1 — 載入指標、0050、DCA baseline
# --------------------------------------------------------------------------
def load_indicators() -> pd.DataFrame:
    df = pd.read_csv(H084_DIR / "results" / "indicators.csv", parse_dates=["trade_date"])
    df["trade_date"] = df["trade_date"].dt.date
    keep = ["trade_date"] + list(INDICATORS.keys())
    df = df[keep].copy()
    # 只保留 4 指標皆齊全的日子
    df = df.dropna(subset=list(INDICATORS.keys())).reset_index(drop=True)
    return df


def load_macro_tier() -> pd.DataFrame:
    fs = pd.read_csv(H084_DIR / "results" / "fuse_state.csv", parse_dates=["trade_date"])
    fs["trade_date"] = fs["trade_date"].dt.date
    return fs[["trade_date", "macro_tier"]]


def load_0050(start: str = "2009-01-01", end: str = "2026-05-09") -> pd.DataFrame:
    """yfinance auto_adjust=True 含息回填。快取避免重抓。"""
    if CACHE_0050.exists():
        df = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
        df["trade_date"] = df["trade_date"].dt.date
        if df["trade_date"].max().isoformat() >= "2026-04-30":
            return df
    print(f"  fetching 0050.TW {start} ~ {end}...")
    raw = yf.download("0050.TW", start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    df = pd.DataFrame({
        "trade_date": [d.date() for d in raw.index],
        "adj_close": raw["Close"].values.astype(float),
        "volume":    raw["Volume"].fillna(0).astype("int64").values,
    })
    df = df.dropna(subset=["adj_close"]).reset_index(drop=True)
    CACHE_0050.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_0050, index=False)
    return df


def monthly_dca_dates(prices: pd.DataFrame) -> pd.DataFrame:
    """每月最後一個交易日（依 prices 的實際交易日）"""
    p = prices.copy()
    p["yyyymm"] = pd.to_datetime(p["trade_date"]).dt.to_period("M")
    last = p.groupby("yyyymm")["trade_date"].max().reset_index(name="trade_date")
    return last[["trade_date"]]


# --------------------------------------------------------------------------
# Step 1.2 — 合成 score
# --------------------------------------------------------------------------
def compute_composite(df: pd.DataFrame) -> pd.DataFrame:
    """
    回三個合成版本：
      1. comp_pct  : 全樣本 percentile（fear-direction） 平均，0–100
      2. comp_z    : 中位數/IQR 標準化後 sign-aligned 加總
      3. comp_vote : 每指標達 fear 端 ≥85 percentile 算 1 票（0–4）
    Phase 1 用全樣本 percentile，Phase 2 再考慮 expanding/walk-forward。
    """
    out = df.copy()
    pct_arrs, z_arrs, vote_arrs = [], [], []

    for col, meta in INDICATORS.items():
        x = out[col].astype(float)
        sign = meta["sign"]
        # rank 百分位，0–100，higher = more fear after sign-flip
        if sign > 0:
            pct = x.rank(pct=True) * 100
        else:
            pct = (-x).rank(pct=True) * 100
        pct_arrs.append(pct)

        # z-score: (x - median) / IQR（全樣本），sign-flip 使 higher = fear
        med = x.median()
        iqr = x.quantile(0.75) - x.quantile(0.25)
        if iqr == 0:
            iqr = 1.0
        z = sign * (x - med) / iqr
        z_arrs.append(z)

        # vote: 在 fear-direction 的 85+ 百分位 = 1 票
        vote = (pct >= 85).astype(int)
        vote_arrs.append(vote)

    out["comp_pct"]  = pd.concat(pct_arrs, axis=1).mean(axis=1)
    out["comp_z"]    = pd.concat(z_arrs, axis=1).sum(axis=1)
    out["comp_vote"] = pd.concat(vote_arrs, axis=1).sum(axis=1)
    return out


# --------------------------------------------------------------------------
# Step 1.4 — Forward returns
# --------------------------------------------------------------------------
def compute_forward_returns(prices: pd.DataFrame,
                            horizons=(60, 120, 250)) -> pd.DataFrame:
    """以 0050 adj_close 計算 +N 個交易日報酬"""
    p = prices.sort_values("trade_date").reset_index(drop=True).copy()
    for n in horizons:
        p[f"fwd_{n}d"] = p["adj_close"].shift(-n) / p["adj_close"] - 1.0
    return p


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main() -> None:
    print("=" * 70)
    print("H085 Phase 1 — TW F&G Composite Distribution Research")
    print("=" * 70)

    # 1.1 載入
    print("\n[Step 1.1] 載入資料")
    ind = load_indicators()
    print(f"  indicators (4 皆齊全) = {len(ind)} rows, {ind['trade_date'].min()} ~ {ind['trade_date'].max()}")

    tier = load_macro_tier()
    ind = ind.merge(tier, on="trade_date", how="left")
    print(f"  with macro_tier merged: tier dist = {ind['macro_tier'].value_counts().to_dict()}")

    p0050 = load_0050()
    print(f"  0050.TW   = {len(p0050)} rows, {p0050['trade_date'].min()} ~ {p0050['trade_date'].max()}")

    fwd = compute_forward_returns(p0050)
    print(f"  forward returns 計算完成 (60/120/250)")

    dca = monthly_dca_dates(p0050)
    print(f"  monthly DCA dates = {len(dca)}")

    # 1.2 合成 score
    print("\n[Step 1.2] 合成 score")
    ind = compute_composite(ind)
    print(f"  comp_pct  range: [{ind['comp_pct'].min():.1f}, {ind['comp_pct'].max():.1f}]")
    print(f"  comp_z    range: [{ind['comp_z'].min():.2f}, {ind['comp_z'].max():.2f}]")
    print(f"  comp_vote dist: {ind['comp_vote'].value_counts().sort_index().to_dict()}")

    # 比較兩種合成法的相關性
    corr_pz = ind[["comp_pct", "comp_z"]].corr().iloc[0, 1]
    corr_pv = ind[["comp_pct", "comp_vote"]].corr().iloc[0, 1]
    corr_zv = ind[["comp_z",   "comp_vote"]].corr().iloc[0, 1]
    print(f"  corr(comp_pct, comp_z)  = {corr_pz:.3f}")
    print(f"  corr(comp_pct, comp_vote)= {corr_pv:.3f}")
    print(f"  corr(comp_z,   comp_vote)= {corr_zv:.3f}")

    # merge 報酬
    merged = ind.merge(fwd[["trade_date", "adj_close", "fwd_60d", "fwd_120d", "fwd_250d"]],
                       on="trade_date", how="inner")
    print(f"  merged with 0050 = {len(merged)} rows")

    # 1.3 閾值分析
    print("\n[Step 1.3] 閾值分析（top 5/10/20%）")
    threshold_summary = []
    for score_name in ["comp_pct", "comp_z", "comp_vote"]:
        for q in [0.80, 0.90, 0.95]:
            thresh = merged[score_name].quantile(q)
            triggers = merged[merged[score_name] >= thresh]
            n = len(triggers)
            # cluster: 連續觸發日為一群（gap > 5 日視為新 cluster）
            if n > 0:
                td = pd.to_datetime(triggers["trade_date"].sort_values().values)
                gaps = (td[1:] - td[:-1]).days if len(td) > 1 else np.array([])
                n_clusters = 1 + int((gaps > 5).sum()) if len(gaps) > 0 else 1
            else:
                n_clusters = 0
            threshold_summary.append({
                "score": score_name,
                "quantile": f"top {int((1-q)*100)}%",
                "threshold": round(float(thresh), 3),
                "n_triggers": n,
                "n_clusters": n_clusters,
            })
    th_df = pd.DataFrame(threshold_summary)
    print(th_df.to_string(index=False))
    th_df.to_csv(RESULTS_DIR / "threshold_summary.csv", index=False)

    # 1.4 Forward-return 分析（每觸發日的 forward returns）
    print("\n[Step 1.4] Forward-return 分析")
    triggers_records = []
    for score_name in ["comp_pct", "comp_z", "comp_vote"]:
        for q in [0.80, 0.90, 0.95]:
            thresh = merged[score_name].quantile(q)
            sub = merged[merged[score_name] >= thresh].dropna(subset=["fwd_120d"])
            for _, r in sub.iterrows():
                triggers_records.append({
                    "score": score_name,
                    "quantile": f"top {int((1-q)*100)}%",
                    "trade_date": r["trade_date"],
                    "score_val": r[score_name],
                    "macro_tier": r.get("macro_tier"),
                    "fwd_60d":  r["fwd_60d"],
                    "fwd_120d": r["fwd_120d"],
                    "fwd_250d": r["fwd_250d"],
                })
    triggers_df = pd.DataFrame(triggers_records)
    triggers_df.to_csv(RESULTS_DIR / "trigger_returns.csv", index=False)
    print(f"  trigger 記錄 = {len(triggers_df)}")

    # 1.5 分佈對比 + baseline
    print("\n[Step 1.5] 分佈對比 vs baseline")

    # all-day baseline（每天均勻買）
    all_days = merged.dropna(subset=["fwd_120d"])
    baseline_all = {
        n: {
            "median": all_days[f"fwd_{n}d"].median(),
            "mean":   all_days[f"fwd_{n}d"].mean(),
            "n":      all_days[f"fwd_{n}d"].notna().sum(),
        }
        for n in (60, 120, 250)
    }

    # monthly DCA baseline（只取每月最後交易日）
    dca_dates_set = set(dca["trade_date"])
    dca_days = merged[merged["trade_date"].isin(dca_dates_set)].dropna(subset=["fwd_120d"])
    baseline_dca = {
        n: {
            "median": dca_days[f"fwd_{n}d"].median(),
            "mean":   dca_days[f"fwd_{n}d"].mean(),
            "n":      dca_days[f"fwd_{n}d"].notna().sum(),
        }
        for n in (60, 120, 250)
    }

    print("\n  Baseline (all days):")
    for n, s in baseline_all.items():
        print(f"    +{n}d: median={s['median']*100:+.2f}%, mean={s['mean']*100:+.2f}% (N={s['n']})")
    print("\n  Baseline (monthly DCA only):")
    for n, s in baseline_dca.items():
        print(f"    +{n}d: median={s['median']*100:+.2f}%, mean={s['mean']*100:+.2f}% (N={s['n']})")

    # trigger-day stats
    print("\n  Trigger-day forward returns:")
    summary_records = []
    for score_name in ["comp_pct", "comp_z", "comp_vote"]:
        for q in [0.80, 0.90, 0.95]:
            label = f"top {int((1-q)*100)}%"
            sub = triggers_df[(triggers_df["score"] == score_name) & (triggers_df["quantile"] == label)]
            if sub.empty:
                continue
            row = {"score": score_name, "quantile": label, "n": len(sub)}
            for n_h in (60, 120, 250):
                vals = sub[f"fwd_{n_h}d"].dropna()
                if vals.empty:
                    continue
                row[f"med_{n_h}d"]   = vals.median()
                row[f"mean_{n_h}d"]  = vals.mean()
                row[f"win_{n_h}d"]   = (vals > baseline_dca[n_h]["median"]).mean()
                row[f"diff_{n_h}d"]  = vals.median() - baseline_dca[n_h]["median"]
            summary_records.append(row)
    summary_df = pd.DataFrame(summary_records)
    summary_df.to_csv(RESULTS_DIR / "trigger_summary.csv", index=False)
    print(summary_df.to_string(index=False))

    # 單因子 baseline：VIX_pct 單獨表現（top 10%、top 5%）
    print("\n  單因子 baseline (VIX_pct alone):")
    vix_records = []
    for q in [0.80, 0.90, 0.95]:
        label = f"top {int((1-q)*100)}%"
        thresh = merged["vix_pct"].quantile(q)
        sub = merged[merged["vix_pct"] >= thresh].dropna(subset=["fwd_120d"])
        row = {"score": "vix_pct_alone", "quantile": label, "n": len(sub),
               "threshold": round(float(thresh), 1)}
        for n_h in (60, 120, 250):
            vals = sub[f"fwd_{n_h}d"].dropna()
            row[f"med_{n_h}d"]  = vals.median()
            row[f"mean_{n_h}d"] = vals.mean()
            row[f"diff_{n_h}d"] = vals.median() - baseline_dca[n_h]["median"]
        vix_records.append(row)
    vix_df = pd.DataFrame(vix_records)
    vix_df.to_csv(RESULTS_DIR / "vix_pct_baseline.csv", index=False)
    print(vix_df.to_string(index=False))

    # 分 macro_tier 看（comp_pct top 10%）
    print("\n  分 macro_tier（comp_pct top 10%）：")
    thresh = merged["comp_pct"].quantile(0.90)
    top10 = merged[merged["comp_pct"] >= thresh].dropna(subset=["fwd_120d"])
    if "macro_tier" in top10.columns:
        # treat A-sub as A
        top10 = top10.copy()
        top10["tier_simple"] = top10["macro_tier"].astype(str).str.replace("-sub", "", regex=False)
        for tier_v, sub in top10.groupby("tier_simple"):
            if len(sub) < 5:
                continue
            print(f"    tier={tier_v}: N={len(sub)}, "
                  f"med_120d={sub['fwd_120d'].median()*100:+.2f}%, "
                  f"med_250d={sub['fwd_250d'].median()*100:+.2f}%")

    # save merged 全資料給可能的 follow-up
    out_cols = ["trade_date", "macro_tier", "adj_close",
                *INDICATORS.keys(),
                "comp_pct", "comp_z", "comp_vote",
                "fwd_60d", "fwd_120d", "fwd_250d"]
    merged[out_cols].to_csv(RESULTS_DIR / "composite_with_returns.csv", index=False)

    # ----------------------------------------------------------------------
    # 視覺化
    # ----------------------------------------------------------------------
    print("\n[Plots] 生成圖檔")

    # Plot 1: 合成 score 時間序列 + 0050（彩色點 = 觸發日）
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    md = merged.copy()
    md["dt"] = pd.to_datetime(md["trade_date"])
    axes[0].plot(md["dt"], md["adj_close"], color="black", lw=0.8)
    # 標 top 10% comp_pct
    th90 = md["comp_pct"].quantile(0.90)
    th95 = md["comp_pct"].quantile(0.95)
    trig90 = md[md["comp_pct"] >= th90]
    trig95 = md[md["comp_pct"] >= th95]
    axes[0].scatter(trig90["dt"], trig90["adj_close"], s=18, color="orange",
                    alpha=0.5, label=f"top 10% (≥{th90:.1f})", zorder=3)
    axes[0].scatter(trig95["dt"], trig95["adj_close"], s=30, color="red",
                    alpha=0.8, label=f"top 5% (≥{th95:.1f})", zorder=4)
    axes[0].set_ylabel("0050 adj_close")
    axes[0].set_title("0050 含息調整收盤 + composite top-decile triggers")
    axes[0].legend(loc="upper left")
    axes[0].grid(alpha=0.3)

    axes[1].plot(md["dt"], md["comp_pct"], color="steelblue", lw=0.8, label="comp_pct")
    axes[1].axhline(th90, color="orange", lw=0.8, ls="--", label=f"top 10% ({th90:.1f})")
    axes[1].axhline(th95, color="red",    lw=0.8, ls="--", label=f"top 5% ({th95:.1f})")
    axes[1].set_ylabel("composite (percentile-avg)")
    axes[1].set_xlabel("date")
    axes[1].legend(loc="upper left")
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "composite_timeseries.png", dpi=110)
    plt.close()
    print(f"  saved {RESULTS_DIR / 'composite_timeseries.png'}")

    # Plot 2: forward-return 分佈對比（box plot）
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for i, n_h in enumerate((60, 120, 250)):
        boxdata, labels = [], []
        # baseline
        boxdata.append(all_days[f"fwd_{n_h}d"].dropna().values * 100)
        labels.append(f"all-day\n(N={baseline_all[n_h]['n']})")
        boxdata.append(dca_days[f"fwd_{n_h}d"].dropna().values * 100)
        labels.append(f"DCA\n(N={baseline_dca[n_h]['n']})")
        # comp_pct top 10/5
        for q, qlabel in [(0.90, "10%"), (0.95, "5%")]:
            sub = triggers_df[(triggers_df["score"] == "comp_pct") &
                              (triggers_df["quantile"] == f"top {qlabel}")]
            vals = sub[f"fwd_{n_h}d"].dropna().values * 100
            boxdata.append(vals)
            labels.append(f"comp_pct\ntop{qlabel}\n(N={len(vals)})")
        # vix only top 10
        sub = merged[merged["vix_pct"] >= merged["vix_pct"].quantile(0.90)]
        vals = sub[f"fwd_{n_h}d"].dropna().values * 100
        boxdata.append(vals)
        labels.append(f"vix top10\n(N={len(vals)})")

        axes[i].boxplot(boxdata, labels=labels, showmeans=True)
        axes[i].axhline(0, color="grey", lw=0.5)
        axes[i].set_title(f"+{n_h}D 0050 含息報酬")
        axes[i].set_ylabel("return %")
        axes[i].grid(alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "forward_return_dist.png", dpi=110)
    plt.close()
    print(f"  saved {RESULTS_DIR / 'forward_return_dist.png'}")

    print("\n=== Phase 1 exploration complete ===")
    print(f"輸出目錄: {RESULTS_DIR}")


if __name__ == "__main__":
    main()

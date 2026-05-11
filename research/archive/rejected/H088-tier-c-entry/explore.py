"""
H088 Phase 1 — Tier C 標準回檔進場訊號 distribution

目標：補 H085 (Tier B 急速 panic specialist) 的盲點，找一組訊號專抓 Tier C 標準回檔。

資料：
  - H084 indicators.csv (2008-01~2026-04)：z125MA、margin_drop_60d、econ_score、vix_pct
  - 0050.TW adj_close (2009-01+)：forward returns
  - H084 trough_mode_state.csv：21 個 trough 事件 + tier 標記
  - H085 comp_z (rolling 5yr IQR)：用於計算重疊度

候選訊號（per H088 proposal Step 1.2）：
  - 主：z125MA ≤ {-1.5, -2.0}
  - 變體 A：+ econ_score ≥ 17（排除藍燈/結構熊）
  - 變體 B：+ parent_tier != A（用 H084 hindsight tier 排除結構熊內部）
  - 變體 C：+ comp_z < 3.97（不重複 H085 已抓的）
  - 變體 D：margin_drop_60d ≤ -5% but comp_z < 3.97

對每組規則計算：
  1. 觸發日總數 + cluster
  2. 13 個 Tier C 事件的命中率
  3. 與 H085 訊號的 Jaccard 重疊度
  4. forward returns +60d / +120d / +250d vs DCA baseline
  5. 必抓事件覆蓋（2024-08, 2026-03）
"""

from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
H084_DIR = PROJECT_ROOT / "research" / "active" / "H084-correction-bottom-survey"
H088_DIR = PROJECT_ROOT / "research" / "active" / "H088-tier-c-entry"
RESULTS_DIR = H088_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_0050 = PROJECT_ROOT / "data" / "external_sources" / "0050_TW_adj.csv"

# 重用 H085 邏輯
INDICATORS = {
    "vix_pct":             {"sign": +1},
    "taiex_dist_125ma_z":  {"sign": -1},
    "margin_drop_60d_pct": {"sign": -1},
    "econ_score":          {"sign": -1},
}
ROLLING_WIN = 1250
WARMUP = 250


def load_indicators() -> pd.DataFrame:
    df = pd.read_csv(H084_DIR / "results" / "indicators.csv", parse_dates=["trade_date"])
    return df.sort_values("trade_date").reset_index(drop=True)


def load_events() -> pd.DataFrame:
    df = pd.read_csv(H084_DIR / "results" / "trough_mode_state.csv", parse_dates=["trough_date"])
    return df.sort_values("trough_date").reset_index(drop=True)


def load_0050() -> pd.DataFrame:
    df = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
    return df.sort_values("trade_date").reset_index(drop=True)


def compute_h085_comp_z(ind: pd.DataFrame) -> pd.Series:
    """重現 H085 spec 的 comp_z (rolling 5yr IQR)"""
    df = ind.dropna(subset=list(INDICATORS.keys())).copy()
    z_cols = []
    for col, meta in INDICATORS.items():
        sign = meta["sign"]
        x = df[col].astype(float) * sign
        roll = x.rolling(window=ROLLING_WIN, min_periods=WARMUP)
        med = roll.median()
        q25 = roll.quantile(0.25); q75 = roll.quantile(0.75)
        iqr = (q75 - q25).clip(lower=1e-9)
        df[f"z_{col}"] = (x - med) / iqr
        z_cols.append(f"z_{col}")
    df["comp_z"] = df[z_cols].sum(axis=1)
    return df.set_index("trade_date")["comp_z"]


def add_forward_returns(prices: pd.DataFrame, horizons=(60, 120, 250)) -> pd.DataFrame:
    p = prices.sort_values("trade_date").reset_index(drop=True).copy()
    for n in horizons:
        p[f"fwd_{n}d"] = p["adj_close"].shift(-n) / p["adj_close"] - 1.0
    return p


def cluster_count(dates: pd.Series, gap_days: int = 30) -> int:
    if len(dates) <= 1:
        return len(dates)
    sd = pd.to_datetime(dates).sort_values()
    gaps = sd.diff().dt.days.fillna(0)
    return int(1 + (gaps > gap_days).sum())


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def hit_event(triggers: set, event_date: pd.Timestamp, window_days: int = 30) -> int:
    return int(any(abs((t - event_date).days) <= window_days for t in triggers))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main() -> None:
    print("=" * 78)
    print("H088 Phase 1 — Tier C 進場訊號 distribution research")
    print("=" * 78)

    ind = load_indicators()
    ev = load_events()
    pr = add_forward_returns(load_0050())

    print(f"\nIndicators: {len(ind)} rows, {ind['trade_date'].min().date()} ~ {ind['trade_date'].max().date()}")
    print(f"Events:     {len(ev)} 個 trough")
    print(f"0050:       {len(pr)} rows, {pr['trade_date'].min().date()} ~ {pr['trade_date'].max().date()}")

    # H085 comp_z（用於重疊判斷）
    comp_z = compute_h085_comp_z(ind)
    h085_triggers = set(comp_z[comp_z >= 3.97].index)
    print(f"\nH085 comp_z 觸發日：{len(h085_triggers)} 天")

    # Tier C 事件清單
    tier_c_events = ev[ev["tier"].str.startswith("C")].copy()
    print(f"\n所有 Tier C 事件（含 sub）：{len(tier_c_events)} 個")
    print(tier_c_events[["trough_date", "tier", "parent_tier"]].to_string(index=False))

    # 必抓事件
    must_hit = [pd.Timestamp("2024-08-05"), pd.Timestamp("2026-03-31")]
    print(f"\n必抓事件：{[d.date() for d in must_hit]}")

    # ----------------------------------------------------------
    # 候選訊號定義
    # ----------------------------------------------------------
    # 加上 0050 forward returns + comp_z
    df = ind.merge(pr[["trade_date", "adj_close", "fwd_60d", "fwd_120d", "fwd_250d"]],
                   on="trade_date", how="inner")
    df = df.merge(comp_z.rename("comp_z").to_frame(), left_on="trade_date", right_index=True, how="left")
    df = df.dropna(subset=["taiex_dist_125ma_z"])
    df = df.set_index("trade_date").sort_index()

    # 為了用 parent_tier filter，做一個「macro_tier」daily 推算（用 fuse_state.csv）
    fs = pd.read_csv(H084_DIR / "results" / "fuse_state.csv", parse_dates=["trade_date"])
    fs = fs.set_index("trade_date").sort_index()
    df["macro_tier"] = fs["macro_tier"]

    print(f"\n合併後可分析日數: {len(df)}")
    print(f"分析窗：{df.index.min().date()} ~ {df.index.max().date()}")

    # 訊號變體
    SIGNALS = {
        "S1: z125≤-1.5":                     df["taiex_dist_125ma_z"] <= -1.5,
        "S2: z125≤-2.0":                     df["taiex_dist_125ma_z"] <= -2.0,
        "S1+econ≥17":                        (df["taiex_dist_125ma_z"] <= -1.5) & (df["econ_score"] >= 17),
        "S1+notA(parent_tier!=A)":           (df["taiex_dist_125ma_z"] <= -1.5) & (df["macro_tier"] != "A"),
        "S1+nonH085(comp_z<3.97)":           (df["taiex_dist_125ma_z"] <= -1.5) & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
        "S2+nonH085":                        (df["taiex_dist_125ma_z"] <= -2.0) & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
        "S1+econ≥17+nonH085":                (df["taiex_dist_125ma_z"] <= -1.5) & (df["econ_score"] >= 17) & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
        "S1+notA+nonH085":                   (df["taiex_dist_125ma_z"] <= -1.5) & (df["macro_tier"] != "A") & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
        "margin_drop60≤-5+nonH085":          (df["margin_drop_60d_pct"] <= -5.0) & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
        "S1 OR margin≤-5 (nonH085)":         ((df["taiex_dist_125ma_z"] <= -1.5) | (df["margin_drop_60d_pct"] <= -5.0)) & ((df["comp_z"] < 3.97) | df["comp_z"].isna()),
    }

    # ----------------------------------------------------------
    # 對每個訊號計算指標
    # ----------------------------------------------------------
    rows = []
    for name, sig in SIGNALS.items():
        sig = sig.fillna(False).astype(bool)
        triggers = set(df.index[sig])
        n_trig = len(triggers)
        n_clust = cluster_count(pd.Series(sorted(triggers))) if triggers else 0
        # 對所有 Tier C events 的命中率
        hits_all_C = sum(hit_event(triggers, d) for d in tier_c_events["trough_date"])
        hit_rate_C = hits_all_C / len(tier_c_events)
        # 必抓事件
        must_hit_count = sum(hit_event(triggers, d) for d in must_hit)
        # H085 重疊
        jacc_h085 = jaccard(triggers, h085_triggers)
        # forward returns
        sub = df[sig].dropna(subset=["fwd_120d"])
        med_60d  = sub["fwd_60d"].median()  if len(sub) > 0 else np.nan
        med_120d = sub["fwd_120d"].median() if len(sub) > 0 else np.nan
        med_250d = sub["fwd_250d"].median() if len(sub) > 0 else np.nan
        rows.append({
            "signal": name,
            "n_trig": n_trig,
            "n_cluster": n_clust,
            "hit_C_events": f"{hits_all_C}/{len(tier_c_events)}",
            "hit_rate_C": hit_rate_C,
            "must_hit": f"{must_hit_count}/{len(must_hit)}",
            "jaccard_H085": jacc_h085,
            "med_60d_pct": med_60d * 100 if pd.notna(med_60d) else np.nan,
            "med_120d_pct": med_120d * 100 if pd.notna(med_120d) else np.nan,
            "med_250d_pct": med_250d * 100 if pd.notna(med_250d) else np.nan,
        })
    res = pd.DataFrame(rows)
    res.to_csv(RESULTS_DIR / "signal_grid.csv", index=False)

    pd.set_option("display.float_format", lambda v: f"{v:.3f}")
    print("\n=== 訊號變體比較 ===\n")
    print(res.to_string(index=False))
    pd.reset_option("display.float_format")

    # ----------------------------------------------------------
    # baseline 0050 forward returns
    # ----------------------------------------------------------
    valid = df.dropna(subset=["fwd_120d"])
    baseline = {
        "all_day": {
            "med_60d":  valid["fwd_60d"].median()  * 100,
            "med_120d": valid["fwd_120d"].median() * 100,
            "med_250d": valid["fwd_250d"].median() * 100,
            "n":        len(valid),
        }
    }
    # monthly DCA
    dca = valid.copy()
    dca["yyyymm"] = dca.index.to_period("M")
    dca_dates = dca.groupby("yyyymm").apply(lambda g: g.index.max())
    dca_sub = valid.loc[dca_dates.values].dropna(subset=["fwd_120d"])
    baseline["dca_monthly"] = {
        "med_60d":  dca_sub["fwd_60d"].median()  * 100,
        "med_120d": dca_sub["fwd_120d"].median() * 100,
        "med_250d": dca_sub["fwd_250d"].median() * 100,
        "n":        len(dca_sub),
    }
    print("\n=== Baseline ===")
    for k, v in baseline.items():
        print(f"  {k:12s} N={v['n']:4d}  +60d={v['med_60d']:+.2f}%  +120d={v['med_120d']:+.2f}%  +250d={v['med_250d']:+.2f}%")

    # ----------------------------------------------------------
    # Tier C 事件命中明細（最佳訊號）
    # ----------------------------------------------------------
    best_signal_name = res.sort_values("hit_rate_C", ascending=False).iloc[0]["signal"]
    print(f"\n=== {best_signal_name} 對每個 Tier C 事件的命中（窗 ±30 天）===")
    best_sig = SIGNALS[best_signal_name].fillna(False)
    best_triggers = set(df.index[best_sig])
    for _, e in tier_c_events.iterrows():
        d = e["trough_date"]
        win_start = d - pd.Timedelta(days=30)
        win_end   = d + pd.Timedelta(days=30)
        n_in_window = sum(1 for t in best_triggers if win_start <= t <= win_end)
        flag = "✓" if n_in_window > 0 else "✗"
        print(f"  {flag} {d.date()}  tier={e['tier']:<5} parent={e['parent_tier']:<5}  → {n_in_window} 觸發 in ±30d")

    # ----------------------------------------------------------
    # 視覺化：每個訊號 hit_rate vs jaccard 散點
    # ----------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax = axes[0]
    for _, r in res.iterrows():
        ax.scatter(r["jaccard_H085"], r["hit_rate_C"], s=80, alpha=0.7)
        ax.annotate(r["signal"][:30], (r["jaccard_H085"], r["hit_rate_C"]),
                    fontsize=7, alpha=0.8, xytext=(3, 3), textcoords="offset points")
    ax.axvline(0.50, color="red", ls="--", lw=0.7, alpha=0.5, label="重疊上限 50%")
    ax.set_xlabel("Jaccard overlap with H085")
    ax.set_ylabel("Hit rate on Tier C events (N=13)")
    ax.set_title("H088 — 訊號變體：Tier C hit rate vs H085 overlap")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)

    ax = axes[1]
    x = np.arange(len(res))
    ax.bar(x - 0.2, res["med_60d_pct"], width=0.2, label="+60d")
    ax.bar(x,       res["med_120d_pct"], width=0.2, label="+120d")
    ax.bar(x + 0.2, res["med_250d_pct"], width=0.2, label="+250d")
    ax.axhline(baseline["dca_monthly"]["med_120d"], color="grey", ls="--", lw=0.7,
               label=f"DCA +120d baseline ({baseline['dca_monthly']['med_120d']:.1f}%)")
    ax.set_xticks(x)
    ax.set_xticklabels([r[:18] for r in res["signal"]], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("median forward return (%)")
    ax.set_title("Forward returns by signal")
    ax.grid(alpha=0.3, axis="y")
    ax.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "signal_grid.png", dpi=110)
    plt.close()
    print(f"\nsaved {RESULTS_DIR / 'signal_grid.png'}")

    print("\n=== complete ===")


if __name__ == "__main__":
    main()

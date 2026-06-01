"""H098 — Regime 對 L1-L4 觸及率的影響與轉換偵測（Phase 1 分佈探索）。

問題：H095/H097 的 L1-L4 階梯係數（EMA-only：0.385/0.497/0.711/0.977 × causal EMA20
日盤振幅）是「全期 pooled」擬出來的平均。本腳本把交易日依 causal 日線趨勢分類器拆成
多頭 / 盤整 / 空頭，檢查：
  (1) 上方 / 下方 L1-L4 觸及率是否隨 regime 漂移（重點在遠端 L3/L4）；
  (2) 「不對稱度」= 上方觸及率 − 下方觸及率 是否隨 regime 由負→0→正（空→盤整→多）；
  (3) regime 轉換窗口（分類器 flip 前後 ±N 日）不對稱度是否領先 / 同步 / 落後 flip。

方法論對齊 H097：
  - 日盤 08:45–13:45；day_range = high − low；ema20 = day_range.shift(1).ewm(span=20)（causal）。
  - 觸及錨點＝session_open（H098 proposal §Notes，與 H095 directional-from-open 一致）：
      上方 Ln 觸及 = (day_high − open) ≥ coef_n × ema20
      下方 Ln 觸及 = (open − day_low) ≥ coef_n × ema20
  - 趨勢分類器全部 causal（只用到「截至前一交易日收盤」），用 adj_close 避免換倉跳空。

所有觸及率附樣本數 N 與 Wilson 95% CI。輸出圖檔到 results/。
"""

from __future__ import annotations

import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
RESULTS = Path(__file__).resolve().parent / "results"
SYMBOL = "TX"

# H097 EMA-only 係數（距離 = coef × causal EMA20 日盤振幅）
COEFS = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977}
LEVELS = ["L1", "L2", "L3", "L4"]

# 分類器參數（baseline）
MA_N = 20          # 均線天數
BAND_K = 1.0       # baseline band = k × rolling std(close)
SLOPE_M = 5        # MA-slope 回看天數（alt1）
SLOPE_S = 0.010    # MA-slope 門檻（斜率/MA，alt1）
DEV_P = 0.020      # %-deviation band（alt2）：|prev_close/ma − 1| 門檻
EVENT_WIN = 7      # 轉換窗口 ±N 日


# ---------- Wilson CI ----------
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """回 (phat, lo, hi)。n=0 回 (nan,nan,nan)。"""
    if n == 0:
        return (math.nan, math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (p, (c - h) / d, (c + h) / d)


# ---------- 資料 ----------
def build_daily() -> pd.DataFrame:
    """每日一列：open(session) / high / low / close_adj / range / ema20(causal)。"""
    with duckdb.connect(DB, read_only=True) as conn:
        df = conn.execute(
            """
            SELECT CAST(timestamp AS DATE) d,
                   arg_min(open, timestamp)      AS open,
                   MAX(high)                     AS high,
                   MIN(low)                      AS low,
                   arg_max(adj_close, timestamp) AS close_adj
            FROM ohlcv_1m
            WHERE symbol = ?
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1 ORDER BY 1
            """,
            [SYMBOL],
        ).df()
    df["d"] = pd.to_datetime(df["d"])
    for c in ["open", "high", "low", "close_adj"]:
        df[c] = df[c].astype(float)
    df = df.set_index("d").sort_index()
    df["range"] = df["high"] - df["low"]
    df["ema20"] = df["range"].shift(1).ewm(span=20, adjust=False).mean()  # causal
    # 上下擺幅（錨 session open）
    df["up"] = df["high"] - df["open"]
    df["dn"] = df["open"] - df["low"]
    # 觸及旗標（每 level、每方向）
    for lv in LEVELS:
        dist = COEFS[lv] * df["ema20"]
        df[f"up_{lv}"] = (df["up"] >= dist).astype("float")
        df[f"dn_{lv}"] = (df["dn"] >= dist).astype("float")
    return df


# ---------- 三個 causal 分類器 ----------
def add_classifiers(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close_adj"]
    ma = c.rolling(MA_N).mean()
    sd = c.rolling(MA_N).std()
    prev = c.shift(1)               # 前一日收盤
    ma_p = ma.shift(1)              # 截至前一日的 MA
    sd_p = sd.shift(1)

    # baseline: prev_close vs MA ± k×std（皆 causal）
    up_b = ma_p + BAND_K * sd_p
    dn_b = ma_p - BAND_K * sd_p
    reg = pd.Series("range", index=df.index, dtype=object)
    reg[prev > up_b] = "bull"
    reg[prev < dn_b] = "bear"
    reg[ma_p.isna() | sd_p.isna() | prev.isna()] = None
    df["regime"] = reg

    # alt1: MA 斜率
    slope = (ma_p - ma_p.shift(SLOPE_M)) / ma_p
    r1 = pd.Series("range", index=df.index, dtype=object)
    r1[slope > SLOPE_S] = "bull"
    r1[slope < -SLOPE_S] = "bear"
    r1[slope.isna()] = None
    df["regime_slope"] = r1

    # alt2: %-deviation band
    dev = prev / ma_p - 1.0
    r2 = pd.Series("range", index=df.index, dtype=object)
    r2[dev > DEV_P] = "bull"
    r2[dev < -DEV_P] = "bear"
    r2[dev.isna()] = None
    df["regime_dev"] = r2
    return df


# ---------- 觸及率表 ----------
def rate_table(df: pd.DataFrame, reg_col: str) -> pd.DataFrame:
    sub = df.dropna(subset=["ema20", reg_col]).copy()
    rows = []
    for reg in ["bull", "range", "bear"]:
        g = sub[sub[reg_col] == reg]
        n = len(g)
        for lv in LEVELS:
            uk = int(g[f"up_{lv}"].sum()); dk = int(g[f"dn_{lv}"].sum())
            up_p, up_lo, up_hi = wilson(uk, n)
            dn_p, dn_lo, dn_hi = wilson(dk, n)
            rows.append({
                "regime": reg, "level": lv, "N": n,
                "up_rate": up_p, "up_lo": up_lo, "up_hi": up_hi,
                "dn_rate": dn_p, "dn_lo": dn_lo, "dn_hi": dn_hi,
                "asym": (up_p - dn_p) if n else math.nan,
            })
    return pd.DataFrame(rows)


def pooled_baseline(df: pd.DataFrame) -> None:
    """全期 pooled 觸及率（open-anchor），作為對照基準。"""
    sub = df.dropna(subset=["ema20"])
    n = len(sub)
    print(f"\n=== 全期 pooled（open-anchor，N={n}）對照基準 ===")
    print(f"{'level':<6}{'up':>8}{'dn':>8}{'目標達到率':>10}")
    tgt = {"L1": "90%", "L2": "75%", "L3": "50%", "L4": "25%"}
    for lv in LEVELS:
        up = sub[f"up_{lv}"].mean(); dn = sub[f"dn_{lv}"].mean()
        print(f"{lv:<6}{up:>7.0%}{dn:>8.0%}{tgt[lv]:>10}")
    print("（pooled 上下應接近、且 ≈ 名目達到率；regime 拆分後才會分離）")


def print_rate_table(rt: pd.DataFrame, title: str) -> None:
    print(f"\n=== {title} ===")
    for reg in ["bull", "range", "bear"]:
        g = rt[rt["regime"] == reg]
        n = int(g["N"].iloc[0])
        zh = {"bull": "多頭", "range": "盤整", "bear": "空頭"}[reg]
        print(f"\n[{zh} {reg}]  N={n}" + ("  ⚠ <100" if n < 100 else ""))
        print(f"  {'lvl':<4}{'上方(95%CI)':>22}{'下方(95%CI)':>22}{'不對稱度':>10}")
        for _, r in g.iterrows():
            up = f"{r['up_rate']:.0%}[{r['up_lo']:.0%},{r['up_hi']:.0%}]"
            dn = f"{r['dn_rate']:.0%}[{r['dn_lo']:.0%},{r['dn_hi']:.0%}]"
            print(f"  {r['level']:<4}{up:>22}{dn:>22}{r['asym']:>+9.0%}")


def ci_separation(rt: pd.DataFrame) -> None:
    """L3/L4：bull vs bear 的順勢方向觸及率 CI 是否分離 + 不對稱度是否離 0。"""
    print("\n=== Regime 鑑別力檢定（重點 L3/L4）===")
    for lv in ["L3", "L4"]:
        b = rt[(rt.regime == "bull") & (rt.level == lv)].iloc[0]
        r = rt[(rt.regime == "range") & (rt.level == lv)].iloc[0]
        e = rt[(rt.regime == "bear") & (rt.level == lv)].iloc[0]
        # 順勢：多頭看上方、空頭看下方；檢查兩者 CI 是否與盤整對應方向分離
        bull_up_sep = b["up_lo"] > r["up_hi"]      # 多頭上方 > 盤整上方
        bear_dn_sep = e["dn_lo"] > r["dn_hi"]      # 空頭下方 > 盤整下方
        print(f"\n {lv}：")
        print(f"   多頭上方觸及 {b['up_rate']:.0%}[{b['up_lo']:.0%},{b['up_hi']:.0%}]"
              f" vs 盤整上方 {r['up_rate']:.0%}[{r['up_lo']:.0%},{r['up_hi']:.0%}]"
              f"  → {'分離✓' if bull_up_sep else '重疊✗'}")
        print(f"   空頭下方觸及 {e['dn_rate']:.0%}[{e['dn_lo']:.0%},{e['dn_hi']:.0%}]"
              f" vs 盤整下方 {r['dn_rate']:.0%}[{r['dn_lo']:.0%},{r['dn_hi']:.0%}]"
              f"  → {'分離✓' if bear_dn_sep else '重疊✗'}")
        print(f"   不對稱度  多頭{b['asym']:+.0%}  盤整{r['asym']:+.0%}  空頭{e['asym']:+.0%}"
              f"  （預期 多>0、盤整≈0、空<0）")


# ---------- 轉換窗口 event-study ----------
def event_study(df: pd.DataFrame, reg_col: str, level: str = "L3") -> pd.DataFrame:
    """flip 前後 ±EVENT_WIN 日的平均不對稱度（asym = up_touch − dn_touch）。
    分『轉多 flip』『轉空 flip』兩組。回 DataFrame(offset, into_bull, into_bear, n_*)。"""
    sub = df.dropna(subset=["ema20", reg_col]).copy().reset_index()
    reg = sub[reg_col].to_numpy()
    asym = (sub[f"up_{level}"] - sub[f"dn_{level}"]).to_numpy()  # ∈ {-1,0,1}
    flips_bull, flips_bear = [], []
    for i in range(1, len(reg)):
        if reg[i] == "bull" and reg[i - 1] != "bull":
            flips_bull.append(i)
        if reg[i] == "bear" and reg[i - 1] != "bear":
            flips_bear.append(i)
    offs = list(range(-EVENT_WIN, EVENT_WIN + 1))
    out = {"offset": offs}
    for name, flips in [("into_bull", flips_bull), ("into_bear", flips_bear)]:
        means, counts = [], []
        for o in offs:
            vals = [asym[f + o] for f in flips if 0 <= f + o < len(asym)]
            means.append(np.mean(vals) if vals else math.nan)
            counts.append(len(vals))
        out[name] = means
        out[f"n_{name}"] = counts
    print(f"\n=== 轉換窗口 event-study（{reg_col}, {level} 不對稱度，±{EVENT_WIN}日）===")
    print(f"  轉多 flip 數={len(flips_bull)}  轉空 flip 數={len(flips_bear)}")
    print(f"  {'offset':>7}{'轉多asym':>10}{'轉空asym':>10}")
    for j, o in enumerate(offs):
        mark = " ← flip" if o == 0 else ""
        print(f"  {o:>+7}{out['into_bull'][j]:>+10.2f}{out['into_bear'][j]:>+10.2f}{mark}")
    return pd.DataFrame(out)


# ---------- 敏感度 ----------
def sensitivity(df: pd.DataFrame) -> None:
    print("\n=== 分類器敏感度（L3 不對稱度方向是否穩定）===")
    print(f"  {'classifier':<16}{'N多':>6}{'N盤':>6}{'N空':>6}"
          f"{'多asymL3':>9}{'盤asymL3':>9}{'空asymL3':>9}")
    for col, name in [("regime", "MA±std(base)"), ("regime_slope", "MA-slope"),
                      ("regime_dev", "%-dev band")]:
        rt = rate_table(df, col)
        ns = {r: int(rt[(rt.regime == r) & (rt.level == "L3")]["N"].iloc[0])
              for r in ["bull", "range", "bear"]}
        a = {r: rt[(rt.regime == r) & (rt.level == "L3")]["asym"].iloc[0]
             for r in ["bull", "range", "bear"]}
        print(f"  {name:<16}{ns['bull']:>6}{ns['range']:>6}{ns['bear']:>6}"
              f"{a['bull']:>+9.0%}{a['range']:>+9.0%}{a['bear']:>+9.0%}")


# ---------- 視覺化 ----------
def plot_all(df: pd.DataFrame, rt: pd.DataFrame, ev: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Heiti TC", "Arial Unicode MS", "Songti SC"]
    plt.rcParams["axes.unicode_minus"] = False
    RESULTS.mkdir(exist_ok=True)
    zh = {"bull": "多頭", "range": "盤整", "bear": "空頭"}
    col = {"bull": "#d62728", "range": "#7f7f7f", "bear": "#2ca02c"}  # 漲紅跌綠

    # 圖1：三 regime × 上下 × L1-L4 觸及率（含 CI）
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    x = np.arange(len(LEVELS))
    for ax, reg in zip(axes, ["bull", "range", "bear"]):
        g = rt[rt.regime == reg].set_index("level").loc[LEVELS]
        ax.bar(x - 0.2, g["up_rate"], 0.4, label="上方",
               yerr=[g["up_rate"] - g["up_lo"], g["up_hi"] - g["up_rate"]],
               color="#d62728", alpha=.85, capsize=3)
        ax.bar(x + 0.2, g["dn_rate"], 0.4, label="下方",
               yerr=[g["dn_rate"] - g["dn_lo"], g["dn_hi"] - g["dn_rate"]],
               color="#2ca02c", alpha=.85, capsize=3)
        ax.set_title(f"{zh[reg]} (N={int(g['N'].iloc[0])})")
        ax.set_xticks(x); ax.set_xticklabels(LEVELS); ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=.3); ax.legend()
    axes[0].set_ylabel("觸及率")
    fig.suptitle("H098 — 三 regime × 上/下方 L1-L4 觸及率（95% Wilson CI）")
    fig.tight_layout(); fig.savefig(RESULTS / "touch_rates.png", dpi=110); plt.close(fig)

    # 圖2：不對稱度（up−dn）逐 level，分 regime
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.25
    for i, reg in enumerate(["bull", "range", "bear"]):
        g = rt[rt.regime == reg].set_index("level").loc[LEVELS]
        ax.bar(x + (i - 1) * w, g["asym"], w, label=zh[reg], color=col[reg], alpha=.85)
    ax.axhline(0, color="k", lw=.8)
    ax.set_xticks(x); ax.set_xticklabels(LEVELS)
    ax.set_ylabel("不對稱度 = 上方 − 下方觸及率")
    ax.set_title("H098 — 不對稱度逐 level（預期 多>0 / 盤整≈0 / 空<0）")
    ax.grid(axis="y", alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(RESULTS / "asymmetry.png", dpi=110); plt.close(fig)

    # 圖3：轉換窗口 event-study
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(ev["offset"], ev["into_bull"], "-o", color="#d62728", label="轉多 flip")
    ax.plot(ev["offset"], ev["into_bear"], "-o", color="#2ca02c", label="轉空 flip")
    ax.axvline(0, color="k", ls="--", lw=.8); ax.axhline(0, color="k", lw=.6)
    ax.set_xlabel("相對 flip 日 (天)"); ax.set_ylabel("L3 不對稱度 (avg)")
    ax.set_title(f"H098 — 轉換窗口 event-study（±{EVENT_WIN}日）")
    ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(RESULTS / "event_study.png", dpi=110); plt.close(fig)
    print(f"\n圖檔輸出：{RESULTS}/touch_rates.png, asymmetry.png, event_study.png")


def main():
    df = build_daily()
    df = add_classifiers(df)
    valid = df.dropna(subset=["ema20", "regime"])
    print(f"H098 Phase 1 — TX 日盤 {df.index.min().date()} ~ {df.index.max().date()}")
    print(f"有效樣本（含 causal ema20 + regime）：N={len(valid)} 日")

    pooled_baseline(df)
    rt = rate_table(df, "regime")
    print_rate_table(rt, "Baseline 分類器：MA±std  各 regime 觸及率")
    ci_separation(rt)
    ev = event_study(df, "regime", "L3")
    sensitivity(df)
    plot_all(df, rt, ev)
    rt.to_csv(RESULTS / "rate_table.csv", index=False)
    print(f"\n觸及率表 CSV：{RESULTS}/rate_table.csv")


if __name__ == "__main__":
    main()

"""
H085 Phase 2 Backtest
TW Fear & Greed 合成版 — Walk-forward Composite + IS/OOS 驗證

關鍵設計（vs Phase 1 explore.py）：
- 用 expanding rank/IQR 取代全樣本 percentile（消除 look-ahead）
- IS=2018-09 ~ 2022-12（4.3 yr，含 2018/2020/2022 三大 fear 事件）
  OOS=2023-01 ~ 2026-04（3.4 yr，含 2025 關稅事件）
- Threshold 用 IS 期內 top X% quantile，固定後 apply 至 OOS

策略變體：
- single_tranche : 觸發即買 1 單位、N 日後賣，賣出前不再進場（cooldown）
- continuous     : 觸發即買 1 單位、可重疊持倉

無手續費滑價（0050 ETF 流動性高、長持有期，影響微小，後續可加）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
H084_DIR = PROJECT_ROOT / "research" / "active" / "H084-correction-bottom-survey"
H085_DIR = PROJECT_ROOT / "research" / "active" / "H085-fg-composite"
RESULTS_DIR = H085_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_0050 = PROJECT_ROOT / "data" / "external_sources" / "0050_TW_adj.csv"

# fear-direction：sign>0 即原值高 = fear；sign<0 需 negate
INDICATORS = {
    "vix_pct":             {"sign": +1, "label": "VIX_pct"},
    "taiex_dist_125ma_z":  {"sign": -1, "label": "z 125MA"},
    "margin_drop_60d_pct": {"sign": -1, "label": "margin_drop_60d"},
    "econ_score":          {"sign": -1, "label": "econ_score"},
}

IS_START = pd.Timestamp("2017-08-31")
IS_END   = pd.Timestamp("2022-12-31")
OOS_END  = pd.Timestamp("2026-04-30")

WALKFWD_MIN_PERIODS = 250  # 1 年 warmup
TRADING_DAYS_YR = 252


# --------------------------------------------------------------------------
# 載入
# --------------------------------------------------------------------------
def load_indicators() -> pd.DataFrame:
    df = pd.read_csv(H084_DIR / "results" / "indicators.csv", parse_dates=["trade_date"])
    df = df.dropna(subset=list(INDICATORS.keys())).reset_index(drop=True)
    df = df[["trade_date"] + list(INDICATORS.keys())].sort_values("trade_date").reset_index(drop=True)
    return df


def load_0050() -> pd.DataFrame:
    if CACHE_0050.exists():
        df = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
        return df.sort_values("trade_date").reset_index(drop=True)
    raw = yf.download("0050.TW", start="2009-01-01", end="2026-05-09",
                      progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    df = pd.DataFrame({
        "trade_date": [pd.Timestamp(d) for d in raw.index],
        "adj_close":  raw["Close"].values.astype(float),
    })
    CACHE_0050.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_0050, index=False)
    return df


# --------------------------------------------------------------------------
# Walk-forward composite
# --------------------------------------------------------------------------
def compute_composite_walkforward(df: pd.DataFrame,
                                  min_periods: int = WALKFWD_MIN_PERIODS,
                                  rolling_window: int | None = None) -> pd.DataFrame:
    """
    每個指標各自 fear-direction-oriented 後計算百分位、IQR z。
    rolling_window=None → expanding（從頭累積）
    rolling_window=N    → rolling N 日窗（避免歷史極端事件鈍化新訊號）
    NOTE: rank(pct=True) 包含當日，bias=1/N，可忽略。
    """
    out = df.copy()
    pct_cols, z_cols = [], []
    for col, meta in INDICATORS.items():
        sign = meta["sign"]
        x_oriented = out[col].astype(float) * sign
        if rolling_window is None:
            roll = x_oriented.expanding(min_periods=min_periods)
        else:
            roll = x_oriented.rolling(window=rolling_window, min_periods=min_periods)
        out[f"{col}_pct"] = roll.rank(pct=True) * 100
        pct_cols.append(f"{col}_pct")
        med = roll.median()
        q25 = roll.quantile(0.25)
        q75 = roll.quantile(0.75)
        iqr = (q75 - q25).clip(lower=1e-9)
        out[f"{col}_z"] = (x_oriented - med) / iqr
        z_cols.append(f"{col}_z")

    out["comp_pct"] = out[pct_cols].mean(axis=1)
    out["comp_z"]   = out[z_cols].sum(axis=1)
    return out


# --------------------------------------------------------------------------
# Trade engine
# --------------------------------------------------------------------------
@dataclass
class Trade:
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    hold_days: int
    score: float

    @property
    def return_pct(self) -> float:
        return self.exit_price / self.entry_price - 1.0


def run_backtest(signals: pd.DataFrame,
                 prices: pd.DataFrame,
                 score_col: str,
                 threshold: float,
                 hold_days: int,
                 mode: str = "single_tranche") -> list[Trade]:
    """
    signals: 含 trade_date + score_col；只有 score 在 IS 期間 fit 後固定 threshold
    prices : trade_date + adj_close
    mode   : 'single_tranche' 或 'continuous'
    """
    p = prices.set_index("trade_date")["adj_close"].sort_index()
    s = signals.set_index("trade_date")[score_col].sort_index()
    # 對齊：交易日 = prices 的日子
    common_idx = p.index.intersection(s.index)
    p = p.loc[common_idx]
    s = s.loc[common_idx]

    triggers = s[s >= threshold].index
    trades: list[Trade] = []

    if mode == "single_tranche":
        i = 0
        idx_list = list(p.index)
        cooldown_until_idx = -1
        for trig_date in triggers:
            try:
                ti = idx_list.index(trig_date)
            except ValueError:
                continue
            if ti < cooldown_until_idx:
                continue
            entry_idx = ti
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(idx_list):
                break  # 不足持有期則跳過
            entry_date = idx_list[entry_idx]
            exit_date  = idx_list[exit_idx]
            trades.append(Trade(
                entry_date=entry_date,
                entry_price=float(p.iloc[entry_idx]),
                exit_date=exit_date,
                exit_price=float(p.iloc[exit_idx]),
                hold_days=hold_days,
                score=float(s.loc[trig_date]),
            ))
            cooldown_until_idx = exit_idx + 1
    elif mode == "continuous":
        idx_list = list(p.index)
        for trig_date in triggers:
            try:
                ti = idx_list.index(trig_date)
            except ValueError:
                continue
            entry_idx = ti
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(idx_list):
                break
            entry_date = idx_list[entry_idx]
            exit_date  = idx_list[exit_idx]
            trades.append(Trade(
                entry_date=entry_date,
                entry_price=float(p.iloc[entry_idx]),
                exit_date=exit_date,
                exit_price=float(p.iloc[exit_idx]),
                hold_days=hold_days,
                score=float(s.loc[trig_date]),
            ))
    else:
        raise ValueError(f"unknown mode: {mode}")

    return trades


def trades_to_curve(trades: list[Trade], prices: pd.DataFrame) -> pd.DataFrame:
    """
    每筆交易 = 進場時投入 $1。
    日合計：cumulative_invested - cumulative_returned + sum(open_position_mtm)
    輸出 daily 等值序列 (per-$ basis)，可比較 Sharpe / MaxDD。

    為了方便 Sharpe 計算，定義「每日策略報酬率」：
      ret[t] = sum_open(p[t] / p[entry_i] - 1) 的日變化
    這需要追蹤每筆 open position 的 daily P&L。
    """
    if not trades:
        empty = pd.DataFrame({"trade_date": [], "equity": [], "ret": []})
        return empty

    p = prices.set_index("trade_date")["adj_close"].sort_index()

    # 為每筆 trade 在 [entry, exit] 間記錄 daily fraction value
    # daily strategy P&L per $ invested:
    #   for each open trade at day t, pnl_t = (p[t] - p[t-1]) / p[entry]
    #   策略總 daily $ change = sum across open trades
    # 然後等值曲線 = $1 * cum return based on equally-weighted average daily return

    # 用 average return of open positions:
    daily_returns: dict[pd.Timestamp, list[float]] = {}
    for tr in trades:
        # 從 entry day 隔天開始計 daily return 至 exit day
        seg = p.loc[tr.entry_date:tr.exit_date]
        if len(seg) < 2:
            continue
        rets = seg.pct_change().dropna()  # daily returns within trade
        for d, r in rets.items():
            daily_returns.setdefault(d, []).append(float(r))

    if not daily_returns:
        empty = pd.DataFrame({"trade_date": [], "equity": [], "ret": []})
        return empty

    # 每天等權平均 open position 的 daily return
    days = sorted(daily_returns.keys())
    avg_ret = pd.Series(
        [np.mean(daily_returns[d]) for d in days],
        index=days, name="ret"
    )
    equity = (1.0 + avg_ret).cumprod()
    return pd.DataFrame({"trade_date": days, "equity": equity.values, "ret": avg_ret.values})


def compute_metrics(trades: list[Trade],
                    curve: pd.DataFrame,
                    period_years: float) -> dict:
    if not trades:
        return {"n_trades": 0}
    rets = pd.Series([tr.return_pct for tr in trades])
    m = {
        "n_trades":      len(trades),
        "win_rate":      float((rets > 0).mean()),
        "mean_ret":      float(rets.mean()),
        "median_ret":    float(rets.median()),
        "best":          float(rets.max()),
        "worst":         float(rets.min()),
        "total_pnl":     float(rets.sum()),  # sum of per-trade returns ($1 each)
    }
    if not curve.empty:
        eq = curve["equity"].values
        daily_ret = curve["ret"].values
        # Sharpe: assume rf=0
        if daily_ret.std() > 0:
            sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(TRADING_DAYS_YR)
        else:
            sharpe = 0.0
        # MaxDD
        peak = np.maximum.accumulate(eq)
        dd = (eq / peak - 1.0).min()
        # CAGR (based on equity curve length)
        n_yrs = (curve["trade_date"].iloc[-1] - curve["trade_date"].iloc[0]).days / 365.25
        cagr = (eq[-1]) ** (1.0 / max(n_yrs, 1e-9)) - 1.0
        m.update({
            "sharpe":  float(sharpe),
            "maxdd":   float(dd),
            "cagr":    float(cagr),
            "final_equity": float(eq[-1]),
        })
    return m


# --------------------------------------------------------------------------
# Baseline strategies
# --------------------------------------------------------------------------
def monthly_dca_trades(prices: pd.DataFrame, hold_days: int,
                       start: pd.Timestamp, end: pd.Timestamp) -> list[Trade]:
    p = prices[(prices["trade_date"] >= start) & (prices["trade_date"] <= end)].copy()
    p["yyyymm"] = p["trade_date"].dt.to_period("M")
    last = p.groupby("yyyymm")["trade_date"].max().reset_index(name="dt")
    idx_list = list(p["trade_date"])
    trades: list[Trade] = []
    for _, r in last.iterrows():
        try:
            i = idx_list.index(r["dt"])
        except ValueError:
            continue
        if i + hold_days >= len(idx_list):
            break
        entry_date = idx_list[i]
        exit_date  = idx_list[i + hold_days]
        trades.append(Trade(
            entry_date=entry_date,
            entry_price=float(p.set_index("trade_date").loc[entry_date, "adj_close"]),
            exit_date=exit_date,
            exit_price=float(p.set_index("trade_date").loc[exit_date, "adj_close"]),
            hold_days=hold_days,
            score=float("nan"),
        ))
    return trades


def buy_and_hold_metrics(prices: pd.DataFrame,
                         start: pd.Timestamp, end: pd.Timestamp) -> dict:
    p = prices[(prices["trade_date"] >= start) & (prices["trade_date"] <= end)].copy()
    p = p.sort_values("trade_date").reset_index(drop=True)
    eq = (p["adj_close"] / p["adj_close"].iloc[0]).values
    daily_ret = pd.Series(eq).pct_change().dropna().values
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(TRADING_DAYS_YR) if daily_ret.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak - 1.0).min()
    n_yrs = (p["trade_date"].iloc[-1] - p["trade_date"].iloc[0]).days / 365.25
    cagr = eq[-1] ** (1.0 / max(n_yrs, 1e-9)) - 1.0
    return {
        "n_trades":  1,
        "sharpe":    float(sharpe),
        "maxdd":     float(dd),
        "cagr":      float(cagr),
        "total_ret": float(eq[-1] - 1.0),
        "final_equity": float(eq[-1]),
    }


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main() -> None:
    print("=" * 78)
    print("H085 Phase 2 — Walk-forward Backtest")
    print("=" * 78)

    ind = load_indicators()
    print(f"\nIndicators (4 皆齊全): {len(ind)} rows, "
          f"{ind['trade_date'].min().date()} ~ {ind['trade_date'].max().date()}")

    prices = load_0050()
    print(f"0050.TW: {len(prices)} rows, "
          f"{prices['trade_date'].min().date()} ~ {prices['trade_date'].max().date()}")

    # 計算 walk-forward composite — 用 5 年 rolling 取代 expanding
    # 原因：expanding 把 2018/2020/2022 三大事件累積後，2025 新事件相對「沒那麼極端」
    #       導致 comp_pct 在 OOS 鈍化（threshold 永遠達不到）
    #       rolling 5yr (1250 日) 可重置歷史窗，給新事件公平機會
    rolling_win = 1250
    print(f"\nComputing walk-forward composite (rolling={rolling_win}d ≈5yr, min_periods={WALKFWD_MIN_PERIODS})...")
    sig = compute_composite_walkforward(ind, min_periods=WALKFWD_MIN_PERIODS,
                                        rolling_window=rolling_win)
    sig_valid = sig.dropna(subset=["comp_pct", "comp_z"])
    print(f"  valid signals: {len(sig_valid)} rows, "
          f"{sig_valid['trade_date'].min().date()} ~ {sig_valid['trade_date'].max().date()}")

    # IS / OOS 切分
    sig_is = sig_valid[(sig_valid["trade_date"] >= IS_START) &
                       (sig_valid["trade_date"] <= IS_END)]
    sig_oos = sig_valid[(sig_valid["trade_date"] > IS_END) &
                        (sig_valid["trade_date"] <= OOS_END)]
    print(f"  IS  : {len(sig_is)} days, {sig_is['trade_date'].min().date()} ~ {sig_is['trade_date'].max().date()}")
    print(f"  OOS : {len(sig_oos)} days, {sig_oos['trade_date'].min().date()} ~ {sig_oos['trade_date'].max().date()}")

    # 在 IS 期間決定每個 (score_col, top_pct) 的 threshold
    score_cols  = ["comp_pct", "comp_z"]
    top_pcts    = [0.05, 0.10, 0.15, 0.20]
    hold_days_l = [60, 120, 250]
    modes       = ["single_tranche", "continuous"]

    is_thresholds = {}
    for sc in score_cols:
        for tp in top_pcts:
            q = 1.0 - tp
            th = float(sig_is[sc].quantile(q))
            is_thresholds[(sc, tp)] = th

    print("\nIS thresholds:")
    for (sc, tp), th in is_thresholds.items():
        n_trig_is  = int((sig_is[sc] >= th).sum())
        n_trig_oos = int((sig_oos[sc] >= th).sum())
        print(f"  {sc} top {int(tp*100)}%: thresh={th:.3f}  "
              f"#trig IS={n_trig_is}, OOS={n_trig_oos}")

    # ------------------------------------------------------------
    # 大網格回測：score × top_pct × hold × mode × {IS, OOS}
    # ------------------------------------------------------------
    print("\nRunning grid backtest...")
    rows = []
    for sc in score_cols:
        for tp in top_pcts:
            th = is_thresholds[(sc, tp)]
            for hd in hold_days_l:
                for md in modes:
                    for split_name, split_df, split_start, split_end in [
                        ("IS",  sig_is,  IS_START, IS_END),
                        ("OOS", sig_oos, IS_END + pd.Timedelta(days=1), OOS_END),
                    ]:
                        trades = run_backtest(split_df, prices, sc, th, hd, md)
                        # equity curve from trades
                        curve = trades_to_curve(trades, prices)
                        period_yrs = (split_end - split_start).days / 365.25
                        m = compute_metrics(trades, curve, period_yrs)
                        rows.append({
                            "split": split_name,
                            "score": sc,
                            "top_pct": int(tp * 100),
                            "threshold": round(th, 3),
                            "hold_days": hd,
                            "mode": md,
                            **m,
                        })
    grid = pd.DataFrame(rows)
    grid.to_csv(RESULTS_DIR / "backtest_grid.csv", index=False)
    print(f"  grid size = {len(grid)} rows → backtest_grid.csv")

    # ------------------------------------------------------------
    # IS 找最佳：依 Sharpe、CAGR、總損益
    # ------------------------------------------------------------
    print("\nIS 內前 10 名（依 Sharpe）:")
    is_grid = grid[grid["split"] == "IS"].copy()
    is_grid["rank_sharpe"] = is_grid["sharpe"].rank(ascending=False)
    top_is = is_grid.sort_values("sharpe", ascending=False).head(10)
    print(top_is[["score", "top_pct", "hold_days", "mode",
                  "n_trades", "sharpe", "cagr", "maxdd", "total_pnl"]].to_string(index=False))

    # 對應 OOS 結果
    print("\n對應 OOS 結果（同一參數組合）:")
    oos_grid = grid[grid["split"] == "OOS"].copy()
    join_keys = ["score", "top_pct", "hold_days", "mode"]
    oos_top = oos_grid.merge(
        top_is[join_keys].assign(_rank=range(1, len(top_is) + 1)),
        on=join_keys, how="inner"
    ).sort_values("_rank")
    print(oos_top[["score", "top_pct", "hold_days", "mode",
                   "n_trades", "sharpe", "cagr", "maxdd", "total_pnl"]].to_string(index=False))

    # ------------------------------------------------------------
    # Baseline：monthly DCA × 不同 hold_days
    # ------------------------------------------------------------
    print("\nBaselines:")
    baseline_rows = []
    for hd in hold_days_l:
        for split_name, split_start, split_end in [
            ("IS",  IS_START, IS_END),
            ("OOS", IS_END + pd.Timedelta(days=1), OOS_END),
        ]:
            dca_tr = monthly_dca_trades(prices, hd, split_start, split_end)
            dca_curve = trades_to_curve(dca_tr, prices)
            m = compute_metrics(dca_tr, dca_curve, (split_end - split_start).days / 365.25)
            baseline_rows.append({
                "split": split_name, "strategy": f"DCA_{hd}d", **m
            })
    bl = pd.DataFrame(baseline_rows)
    print(bl.to_string(index=False))

    # buy-and-hold
    print("\nBuy-and-hold (0050):")
    bh_is  = buy_and_hold_metrics(prices, IS_START, IS_END)
    bh_oos = buy_and_hold_metrics(prices, IS_END + pd.Timedelta(days=1), OOS_END)
    print(f"  IS  : sharpe={bh_is['sharpe']:.2f}, cagr={bh_is['cagr']*100:.1f}%, maxdd={bh_is['maxdd']*100:.1f}%, total={bh_is['total_ret']*100:.1f}%")
    print(f"  OOS : sharpe={bh_oos['sharpe']:.2f}, cagr={bh_oos['cagr']*100:.1f}%, maxdd={bh_oos['maxdd']*100:.1f}%, total={bh_oos['total_ret']*100:.1f}%")
    bl = pd.concat([bl, pd.DataFrame([
        {"split": "IS",  "strategy": "BuyHold", **bh_is},
        {"split": "OOS", "strategy": "BuyHold", **bh_oos},
    ])], ignore_index=True)
    bl.to_csv(RESULTS_DIR / "baseline_metrics.csv", index=False)

    # ------------------------------------------------------------
    # 視覺化：選 IS Sharpe-best 那組，畫 IS+OOS 連續 equity curve vs DCA & B&H
    # ------------------------------------------------------------
    best = top_is.iloc[0]
    sc, tp, hd, md = best["score"], best["top_pct"], best["hold_days"], best["mode"]
    th = is_thresholds[(sc, tp / 100.0)]
    print(f"\n畫圖 — Best IS combo: {sc} top{tp}% hold {hd}d mode={md} thresh={th:.3f}")

    full_sig = sig_valid[(sig_valid["trade_date"] >= IS_START) &
                         (sig_valid["trade_date"] <= OOS_END)]
    trades_full = run_backtest(full_sig, prices, sc, th, hd, md)
    curve_full  = trades_to_curve(trades_full, prices)

    dca_full = monthly_dca_trades(prices, hd, IS_START, OOS_END)
    dca_curve_full = trades_to_curve(dca_full, prices)

    p_window = prices[(prices["trade_date"] >= IS_START) &
                      (prices["trade_date"] <= OOS_END)].sort_values("trade_date")
    bh_curve = (p_window["adj_close"] / p_window["adj_close"].iloc[0]).values

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    if not curve_full.empty:
        axes[0].plot(curve_full["trade_date"], curve_full["equity"],
                     color="red", lw=1.5, label=f"H085 {sc} top{tp}% hold{hd}d {md}")
    if not dca_curve_full.empty:
        axes[0].plot(dca_curve_full["trade_date"], dca_curve_full["equity"],
                     color="blue", lw=1.0, label=f"DCA {hd}d hold")
    axes[0].plot(p_window["trade_date"], bh_curve,
                 color="grey", lw=1.0, alpha=0.7, label="0050 buy-and-hold")
    axes[0].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5, label="IS / OOS split")
    axes[0].set_ylabel("equity (per-$ basis, 1.0 = entry)")
    axes[0].set_title(f"H085 Phase 2 — Equity Curves (Best IS Combo)")
    axes[0].legend(loc="upper left")
    axes[0].grid(alpha=0.3)
    axes[0].set_yscale("log")

    # signal panel
    ms = sig_valid.set_index("trade_date")
    ms = ms[(ms.index >= IS_START) & (ms.index <= OOS_END)]
    axes[1].plot(ms.index, ms[sc], color="steelblue", lw=0.7, label=sc)
    axes[1].axhline(th, color="red", ls="--", lw=0.7, label=f"thresh={th:.2f}")
    axes[1].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5)
    axes[1].set_ylabel(sc)
    axes[1].set_xlabel("date")
    axes[1].legend(loc="upper left")
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "equity_curves_best.png", dpi=110)
    plt.close()
    print(f"  saved equity_curves_best.png")

    # ------------------------------------------------------------
    # 敏感度 heatmap：sharpe over (top_pct × hold_days)，分 score × mode × split
    # ------------------------------------------------------------
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    panels = [
        ("comp_pct", "single_tranche", "IS"),
        ("comp_pct", "single_tranche", "OOS"),
        ("comp_pct", "continuous",     "IS"),
        ("comp_pct", "continuous",     "OOS"),
        ("comp_z",   "single_tranche", "IS"),
        ("comp_z",   "single_tranche", "OOS"),
        ("comp_z",   "continuous",     "IS"),
        ("comp_z",   "continuous",     "OOS"),
    ]
    for ax, (sc_p, md_p, split_p) in zip(axes.flat, panels):
        sub = grid[(grid["score"] == sc_p) & (grid["mode"] == md_p) &
                   (grid["split"] == split_p)]
        pivot = sub.pivot(index="hold_days", columns="top_pct", values="sharpe")
        im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=-1, vmax=2.5, aspect="auto")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([f"top{c}%" for c in pivot.columns])
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([f"{i}d" for i in pivot.index])
        ax.set_title(f"{sc_p} {md_p} {split_p}", fontsize=9)
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                v = pivot.values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            color="black" if abs(v) < 1.5 else "white", fontsize=8)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    plt.suptitle("Sharpe heatmap (top_pct × hold_days), by score/mode/split", fontsize=11)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "sensitivity_sharpe.png", dpi=110)
    plt.close()
    print(f"  saved sensitivity_sharpe.png")

    print("\n=== Phase 2 backtest complete ===")
    print(f"輸出目錄: {RESULTS_DIR}")


if __name__ == "__main__":
    main()

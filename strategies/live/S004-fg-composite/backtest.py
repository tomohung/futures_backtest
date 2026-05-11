"""
S004-fg-composite — Live Backtest
TW Fear & Greed Composite (H085 confirmed) on 0050.TW

完整可獨立重跑。輸出：交易明細 + IS/OOS/FULL metrics + equity 圖。

使用：
  uv run python strategies/live/S004-fg-composite/backtest.py
  uv run python strategies/live/S004-fg-composite/backtest.py --start 2020-01-01 --end 2026-04-30
"""

from __future__ import annotations

import argparse
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
H084_ARCHIVE = PROJECT_ROOT / "research" / "archive" / "confirmed" / "H084-correction-bottom-survey"
CACHE_0050 = PROJECT_ROOT / "data" / "external_sources" / "0050_TW_adj.csv"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Strategy 規格（鎖定）
SCORE_COL = "comp_z"
THRESHOLD = 3.97
HOLD_DAYS = 250
MAX_OPEN  = 5
COOLDOWN_DAYS = 5
ROLLING_WIN = 1250
WARMUP_MIN_PERIODS = 250
TRADING_DAYS_YR = 252

INDICATORS = {
    "vix_pct":             {"sign": +1},
    "taiex_dist_125ma_z":  {"sign": -1},
    "margin_drop_60d_pct": {"sign": -1},
    "econ_score":          {"sign": -1},
}

IS_START = pd.Timestamp("2018-09-11")
IS_END   = pd.Timestamp("2022-12-30")


# ---------------------------------------------------------
# Data loading
# ---------------------------------------------------------
def find_indicators_csv() -> Path:
    """先找 active，再找 archive。"""
    for d in (H084_DIR, H084_ARCHIVE):
        f = d / "results" / "indicators.csv"
        if f.exists():
            return f
    raise FileNotFoundError("無法找到 H084 indicators.csv，請先執行 H084 build_indicators.py")


def load_indicators() -> pd.DataFrame:
    df = pd.read_csv(find_indicators_csv(), parse_dates=["trade_date"])
    df = df.dropna(subset=list(INDICATORS.keys())).reset_index(drop=True)
    df = df[["trade_date"] + list(INDICATORS.keys())].sort_values("trade_date").reset_index(drop=True)
    return df


def load_0050() -> pd.DataFrame:
    if CACHE_0050.exists():
        df = pd.read_csv(CACHE_0050, parse_dates=["trade_date"])
        return df.sort_values("trade_date").reset_index(drop=True)
    raw = yf.download("0050.TW", start="2009-01-01", end=pd.Timestamp.today().date().isoformat(),
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


# ---------------------------------------------------------
# Composite signal
# ---------------------------------------------------------
def compute_composite(df: pd.DataFrame) -> pd.DataFrame:
    """
    對每指標：fear-direction sign-flip，rolling 5 yr median + IQR 標準化，加總成 comp_z。
    輸出包含：trade_date + 4 個 z + comp_z
    """
    out = df.copy()
    z_cols = []
    for col, meta in INDICATORS.items():
        sign = meta["sign"]
        x_oriented = out[col].astype(float) * sign
        roll = x_oriented.rolling(window=ROLLING_WIN, min_periods=WARMUP_MIN_PERIODS)
        med = roll.median()
        q25 = roll.quantile(0.25)
        q75 = roll.quantile(0.75)
        iqr = (q75 - q25).clip(lower=1e-9)
        out[f"z_{col}"] = (x_oriented - med) / iqr
        z_cols.append(f"z_{col}")
    out["comp_z"] = out[z_cols].sum(axis=1)
    return out


# ---------------------------------------------------------
# Trade engine (V1 cooldown, max_open=5, fixed 250d hold)
# ---------------------------------------------------------
@dataclass
class Trade:
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    score: float

    @property
    def return_pct(self) -> float:
        return self.exit_price / self.entry_price - 1.0

    @property
    def hold_days(self) -> int:
        return (self.exit_date - self.entry_date).days


def run_backtest(signals: pd.DataFrame, prices: pd.DataFrame) -> list[Trade]:
    p = prices.set_index("trade_date")["adj_close"].sort_index()
    s = signals.set_index("trade_date")[SCORE_COL].sort_index()
    common = p.index.intersection(s.index)
    p = p.loc[common]; s = s.loc[common]
    idx_list = list(p.index)
    triggers = s[s >= THRESHOLD].index

    trades: list[Trade] = []
    open_exits: list[int] = []
    last_entry_idx = -10**9

    for trig in triggers:
        ti = idx_list.index(trig)
        open_exits = [ei for ei in open_exits if ei > ti]
        if len(open_exits) >= MAX_OPEN:
            continue
        if ti - last_entry_idx < COOLDOWN_DAYS:
            continue
        exit_idx = ti + HOLD_DAYS
        if exit_idx >= len(idx_list):
            break
        trades.append(Trade(
            entry_date=idx_list[ti],
            entry_price=float(p.iloc[ti]),
            exit_date=idx_list[exit_idx],
            exit_price=float(p.iloc[exit_idx]),
            score=float(s.iloc[ti]),
        ))
        open_exits.append(exit_idx)
        last_entry_idx = ti
    return trades


def trades_to_curve(trades: list[Trade], prices: pd.DataFrame) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame({"trade_date": [], "equity": [], "ret": []})
    p = prices.set_index("trade_date")["adj_close"].sort_index()
    daily_returns: dict[pd.Timestamp, list[float]] = {}
    for tr in trades:
        seg = p.loc[tr.entry_date:tr.exit_date]
        if len(seg) < 2:
            continue
        rets = seg.pct_change().dropna()
        for d, r in rets.items():
            daily_returns.setdefault(d, []).append(float(r))
    if not daily_returns:
        return pd.DataFrame({"trade_date": [], "equity": [], "ret": []})
    days = sorted(daily_returns.keys())
    avg_ret = pd.Series([np.mean(daily_returns[d]) for d in days], index=days)
    eq = (1.0 + avg_ret).cumprod()
    return pd.DataFrame({"trade_date": days, "equity": eq.values, "ret": avg_ret.values})


def compute_metrics(trades: list[Trade], curve: pd.DataFrame) -> dict:
    if not trades:
        return {"n_trades": 0}
    rets = pd.Series([tr.return_pct for tr in trades])
    m = {
        "n_trades":   len(trades),
        "win_rate":   float((rets > 0).mean()),
        "median_ret": float(rets.median()),
        "mean_ret":   float(rets.mean()),
        "best":       float(rets.max()),
        "worst":      float(rets.min()),
        "total_pnl":  float(rets.sum()),
    }
    if not curve.empty:
        eq = curve["equity"].values
        dr = curve["ret"].values
        m["sharpe"] = float((dr.mean() / dr.std()) * np.sqrt(TRADING_DAYS_YR)) if dr.std() > 0 else 0.0
        peak = np.maximum.accumulate(eq)
        m["maxdd"] = float((eq / peak - 1.0).min())
        n_yrs = (curve["trade_date"].iloc[-1] - curve["trade_date"].iloc[0]).days / 365.25
        m["cagr"] = float(eq[-1] ** (1.0 / max(n_yrs, 1e-9)) - 1.0)
        m["final_equity"] = float(eq[-1])
    return m


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description="S004-fg-composite live backtest")
    p.add_argument("--start", type=pd.Timestamp, default=IS_START)
    p.add_argument("--end",   type=pd.Timestamp, default=None)
    args = p.parse_args()

    print("=" * 78)
    print("S004-fg-composite — Live Backtest")
    print("=" * 78)

    ind = load_indicators()
    prices = load_0050()
    end_date = args.end if args.end is not None else min(ind["trade_date"].max(), prices["trade_date"].max())
    print(f"Indicators: {len(ind)} rows, {ind['trade_date'].min().date()} ~ {ind['trade_date'].max().date()}")
    print(f"0050.TW   : {len(prices)} rows, {prices['trade_date'].min().date()} ~ {prices['trade_date'].max().date()}")
    print(f"Backtest window: {args.start.date()} ~ {end_date.date()}")
    print(f"Spec: {SCORE_COL} >= {THRESHOLD}, hold={HOLD_DAYS}td, max_open={MAX_OPEN}, cooldown={COOLDOWN_DAYS}td")

    sig = compute_composite(ind)
    sig_valid = sig.dropna(subset=[SCORE_COL])
    sig_full = sig_valid[(sig_valid["trade_date"] >= args.start) & (sig_valid["trade_date"] <= end_date)]
    sig_is = sig_valid[(sig_valid["trade_date"] >= IS_START)  & (sig_valid["trade_date"] <= IS_END)]
    sig_oos = sig_valid[(sig_valid["trade_date"] >  IS_END)   & (sig_valid["trade_date"] <= end_date)]

    splits = [("IS", sig_is), ("OOS", sig_oos), ("FULL", sig_full)]
    print("\n=== Metrics ===")
    rows = []
    for name, s in splits:
        trades = run_backtest(s, prices)
        curve = trades_to_curve(trades, prices)
        m = compute_metrics(trades, curve)
        rows.append({"split": name, **m})
    res = pd.DataFrame(rows)
    cols = ["split", "n_trades", "win_rate", "median_ret", "mean_ret",
            "sharpe", "maxdd", "cagr", "final_equity", "total_pnl"]
    print(res[cols].to_string(index=False))
    res.to_csv(RESULTS_DIR / "metrics.csv", index=False)

    # FULL trade list
    full_trades = run_backtest(sig_full, prices)
    rows = [{
        "n":           i + 1,
        "entry_date":  tr.entry_date.date().isoformat(),
        "entry_price": round(tr.entry_price, 2),
        "exit_date":   tr.exit_date.date().isoformat(),
        "exit_price":  round(tr.exit_price, 2),
        "return_pct":  round(tr.return_pct * 100, 2),
        "comp_z":      round(tr.score, 2),
    } for i, tr in enumerate(full_trades)]
    trades_df = pd.DataFrame(rows)
    trades_df.to_csv(RESULTS_DIR / "trades.csv", index=False)
    print(f"\n=== FULL trades ({len(full_trades)}) ===")
    print(trades_df.to_string(index=False))

    # Equity curve
    full_curve = trades_to_curve(full_trades, prices)
    if not full_curve.empty:
        p_w = prices[(prices["trade_date"] >= args.start) & (prices["trade_date"] <= end_date)].sort_values("trade_date")
        bh = (p_w["adj_close"] / p_w["adj_close"].iloc[0]).values

        fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1]})
        axes[0].plot(full_curve["trade_date"], full_curve["equity"], color="red", lw=1.5,
                     label=f"S004 (Sharpe={res[res['split']=='FULL']['sharpe'].iloc[0]:.2f})")
        axes[0].plot(p_w["trade_date"], bh, color="grey", lw=0.8, alpha=0.6,
                     label="0050 buy-and-hold")
        axes[0].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5, label="IS / OOS split")
        axes[0].set_yscale("log")
        axes[0].set_ylabel("equity (per $1, log)")
        axes[0].legend(loc="upper left")
        axes[0].grid(alpha=0.3)
        axes[0].set_title("S004-fg-composite — Equity Curve")

        s_full = sig_full.set_index("trade_date")[SCORE_COL]
        axes[1].plot(s_full.index, s_full.values, color="steelblue", lw=0.7)
        axes[1].axhline(THRESHOLD, color="red", ls="--", lw=0.7, label=f"thresh={THRESHOLD}")
        axes[1].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5)
        for tr in full_trades:
            axes[1].scatter([tr.entry_date], [tr.score], s=20, color="red", zorder=3)
        axes[1].set_ylabel("comp_z")
        axes[1].set_xlabel("date")
        axes[1].legend(loc="upper left")
        axes[1].grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(RESULTS_DIR / "equity.png", dpi=110)
        plt.close()
        print(f"\nsaved {RESULTS_DIR / 'equity.png'}")

    print(f"\n輸出目錄：{RESULTS_DIR}")


if __name__ == "__main__":
    main()

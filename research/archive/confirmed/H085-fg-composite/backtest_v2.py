"""
H085 Phase 2.5 — 倉位管理變體比較

對照組與兩個變體（皆用 comp_z, IS-fitted threshold 3.97, 250d 固定出場）：

  B0  : continuous 無上限（現狀，2025 那波 22 倉）
  V1  : continuous + 5 交易日 cooldown + max_open=5
        → 每週至多 1 倉、總計最多 5 倉
  V2  : 訊號開啟 1 倉「金字塔」+ 收盤站上 SMA21/65/133/230 各加 1 倉，max=5
        → pyramid 完成或全部出場前不接受新訊號

目的：驗證使用者直覺
  - 連續 22 天每天買的問題不在 drawdown 而在資金倍數與平均成本被拉高
  - 5 倉上限是否能維持 Sharpe 並大幅降低資金需求
  - 金字塔加碼 vs 純間隔，哪個 total return / Sharpe 更好

EMA → SMA（依使用者偏好）；首次收盤站上即填入該 SMA 槽。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, str(Path(__file__).parent))
from backtest import (
    load_indicators, load_0050, compute_composite_walkforward,
    monthly_dca_trades, buy_and_hold_metrics, trades_to_curve, compute_metrics,
    Trade, INDICATORS, IS_START, IS_END, OOS_END, WALKFWD_MIN_PERIODS,
    TRADING_DAYS_YR, RESULTS_DIR,
)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

SCORE_COL = "comp_z"
THRESHOLD = 3.970     # IS top 10% (from backtest.py)
HOLD_DAYS = 250
MAX_OPEN  = 5
COOLDOWN_DAYS = 5     # ~1 trading week
SMA_PERIODS = [21, 65, 133, 230]


# ---------------------------------------------------------
# SMA helper
# ---------------------------------------------------------
def add_sma(prices: pd.DataFrame, periods=SMA_PERIODS) -> pd.DataFrame:
    p = prices.sort_values("trade_date").reset_index(drop=True).copy()
    for n in periods:
        p[f"sma{n}"] = p["adj_close"].rolling(window=n, min_periods=n).mean()
    return p


# ---------------------------------------------------------
# Backtest engines
# ---------------------------------------------------------
def run_v1_cooldown(signals: pd.DataFrame,
                    prices: pd.DataFrame,
                    threshold: float,
                    hold_days: int = HOLD_DAYS,
                    max_open: int = MAX_OPEN,
                    cooldown_days: int = COOLDOWN_DAYS) -> list[Trade]:
    """
    每觸發日若 (open<max_open) AND (距上次進場 ≥ cooldown_days) → 買 1 倉
    每倉持有 hold_days 後出場
    """
    p = prices.set_index("trade_date")["adj_close"].sort_index()
    s = signals.set_index("trade_date")[SCORE_COL].sort_index()
    common = p.index.intersection(s.index)
    p = p.loc[common]; s = s.loc[common]

    idx_list = list(p.index)
    triggers = s[s >= threshold].index
    trades: list[Trade] = []
    open_exits: list[int] = []  # exit indices of open positions
    last_entry_idx = -10**9

    for trig in triggers:
        try:
            ti = idx_list.index(trig)
        except ValueError:
            continue
        # 清除已出場部位
        open_exits = [ei for ei in open_exits if ei > ti]
        if len(open_exits) >= max_open:
            continue
        if ti - last_entry_idx < cooldown_days:
            continue
        exit_idx = ti + hold_days
        if exit_idx >= len(idx_list):
            break
        trades.append(Trade(
            entry_date=idx_list[ti],
            entry_price=float(p.iloc[ti]),
            exit_date=idx_list[exit_idx],
            exit_price=float(p.iloc[exit_idx]),
            hold_days=hold_days,
            score=float(s.iloc[ti]),
        ))
        open_exits.append(exit_idx)
        last_entry_idx = ti
    return trades


def run_v2_pyramid(signals: pd.DataFrame,
                   prices_with_sma: pd.DataFrame,
                   threshold: float,
                   hold_days: int = HOLD_DAYS,
                   max_open: int = MAX_OPEN,
                   sma_periods=SMA_PERIODS) -> list[Trade]:
    """
    訊號日開啟一個 pyramid：
      seed 倉：訊號當日收盤買 1
      之後每天，對每個尚未填入的 SMA：若 close >= SMA → 買 1，標記該 SMA 已用
    pyramid 同時最多 5 倉（1 seed + 4 SMA）
    pyramid 仍開啟（任一倉未到期）時，新訊號被忽略
    每倉獨立持有 hold_days
    """
    p = prices_with_sma.sort_values("trade_date").reset_index(drop=True)
    sma_cols = [f"sma{n}" for n in sma_periods]
    p_idx = p.set_index("trade_date")
    s = signals.set_index("trade_date")[SCORE_COL].sort_index()

    common = p_idx.index.intersection(s.index)
    p_aligned = p_idx.loc[common].sort_index()
    s_aligned = s.loc[common].sort_index()

    idx_list = list(p_aligned.index)
    closes = p_aligned["adj_close"].values
    sma_vals = {sc: p_aligned[sc].values for sc in sma_cols}

    triggers = s_aligned[s_aligned >= threshold].index
    trig_set = set(triggers)

    trades: list[Trade] = []
    pyramid_active = False
    pyramid_units: list[int] = []   # entry indices in this pyramid
    pyramid_filled: set[str] = set()   # filled SMA cols

    for ti, dt in enumerate(idx_list):
        # 清除 pyramid（若所有 unit 都已到期）
        if pyramid_active:
            still_open = [ei for ei in pyramid_units if ti < ei + hold_days]
            if not still_open:
                pyramid_active = False
                pyramid_units = []
                pyramid_filled = set()

        # 若 pyramid 未開且今日為訊號日 → 開 seed
        if (not pyramid_active) and (dt in trig_set):
            if ti + hold_days >= len(idx_list):
                continue
            pyramid_active = True
            pyramid_units = [ti]
            pyramid_filled = set()
            trades.append(Trade(
                entry_date=dt,
                entry_price=float(closes[ti]),
                exit_date=idx_list[ti + hold_days],
                exit_price=float(closes[ti + hold_days]),
                hold_days=hold_days,
                score=float(s_aligned.iloc[ti]) if dt in s_aligned.index else float("nan"),
            ))
            continue

        # 若 pyramid 開啟且未滿 → 檢查 SMA 加碼
        if pyramid_active and len(pyramid_units) < max_open:
            # ti > seed_idx，避免訊號日當天加碼（保留 seed 抄底特性）
            if ti <= pyramid_units[0]:
                continue
            for sc in sma_cols:
                if sc in pyramid_filled:
                    continue
                sma_v = sma_vals[sc][ti]
                if np.isnan(sma_v):
                    continue
                if closes[ti] >= sma_v:
                    if ti + hold_days >= len(idx_list):
                        continue
                    pyramid_units.append(ti)
                    pyramid_filled.add(sc)
                    trades.append(Trade(
                        entry_date=dt,
                        entry_price=float(closes[ti]),
                        exit_date=idx_list[ti + hold_days],
                        exit_price=float(closes[ti + hold_days]),
                        hold_days=hold_days,
                        score=float(s_aligned.iloc[ti]) if dt in s_aligned.index else float("nan"),
                    ))
                    if len(pyramid_units) >= max_open:
                        break
    return trades


def run_b0_baseline(signals: pd.DataFrame,
                    prices: pd.DataFrame,
                    threshold: float,
                    hold_days: int = HOLD_DAYS) -> list[Trade]:
    """B0 = 現狀 continuous 無上限（每觸發日進場）"""
    p = prices.set_index("trade_date")["adj_close"].sort_index()
    s = signals.set_index("trade_date")[SCORE_COL].sort_index()
    common = p.index.intersection(s.index)
    p = p.loc[common]; s = s.loc[common]
    idx_list = list(p.index)
    triggers = s[s >= threshold].index
    trades: list[Trade] = []
    for trig in triggers:
        try:
            ti = idx_list.index(trig)
        except ValueError:
            continue
        if ti + hold_days >= len(idx_list):
            break
        trades.append(Trade(
            entry_date=idx_list[ti],
            entry_price=float(p.iloc[ti]),
            exit_date=idx_list[ti + hold_days],
            exit_price=float(p.iloc[ti + hold_days]),
            hold_days=hold_days,
            score=float(s.iloc[ti]),
        ))
    return trades


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main() -> None:
    print("=" * 78)
    print("H085 Phase 2.5 — 倉位管理變體 (B0 vs V1 vs V2)")
    print("=" * 78)
    print(f"  score    : {SCORE_COL}")
    print(f"  threshold: {THRESHOLD}")
    print(f"  hold     : {HOLD_DAYS} trading days")
    print(f"  max_open : {MAX_OPEN}")
    print(f"  cooldown : {COOLDOWN_DAYS} trading days (V1)")
    print(f"  SMA      : {SMA_PERIODS} (V2)")

    ind = load_indicators()
    prices = load_0050()
    prices = add_sma(prices)

    sig = compute_composite_walkforward(ind, min_periods=WALKFWD_MIN_PERIODS, rolling_window=1250)
    sig_valid = sig.dropna(subset=["comp_z"])
    sig_is  = sig_valid[(sig_valid["trade_date"] >= IS_START)  & (sig_valid["trade_date"] <= IS_END)]
    sig_oos = sig_valid[(sig_valid["trade_date"] >  IS_END)    & (sig_valid["trade_date"] <= OOS_END)]
    sig_full = pd.concat([sig_is, sig_oos], ignore_index=True)

    rows = []
    splits = [
        ("IS",  sig_is,  IS_START, IS_END),
        ("OOS", sig_oos, IS_END + pd.Timedelta(days=1), OOS_END),
        ("FULL", sig_full, IS_START, OOS_END),
    ]
    for split_name, sig_split, start, end in splits:
        for variant_name, runner in [
            ("B0_continuous", lambda s, p, t: run_b0_baseline(s, p, t, HOLD_DAYS)),
            ("V1_cooldown",   lambda s, p, t: run_v1_cooldown(s, p, t, HOLD_DAYS, MAX_OPEN, COOLDOWN_DAYS)),
            ("V2_pyramid",    lambda s, p, t: run_v2_pyramid(s, p, t, HOLD_DAYS, MAX_OPEN, SMA_PERIODS)),
        ]:
            trades = runner(sig_split, prices, THRESHOLD)
            curve = trades_to_curve(trades, prices)
            m = compute_metrics(trades, curve, (end - start).days / 365.25)
            rows.append({"split": split_name, "variant": variant_name, **m})

    res = pd.DataFrame(rows)
    res.to_csv(RESULTS_DIR / "v1v2_comparison.csv", index=False)
    print("\n=== 結果（依 split / variant）===")
    cols = ["split", "variant", "n_trades", "win_rate", "median_ret", "mean_ret",
            "sharpe", "maxdd", "cagr", "total_pnl", "final_equity"]
    print(res[cols].to_string(index=False))

    # ------------------ 視覺化 ------------------
    full_curves = {}
    full_trades = {}
    for variant_name, runner in [
        ("B0_continuous", lambda s, p, t: run_b0_baseline(s, p, t, HOLD_DAYS)),
        ("V1_cooldown",   lambda s, p, t: run_v1_cooldown(s, p, t, HOLD_DAYS, MAX_OPEN, COOLDOWN_DAYS)),
        ("V2_pyramid",    lambda s, p, t: run_v2_pyramid(s, p, t, HOLD_DAYS, MAX_OPEN, SMA_PERIODS)),
    ]:
        tr = runner(sig_full, prices, THRESHOLD)
        full_trades[variant_name] = tr
        full_curves[variant_name] = trades_to_curve(tr, prices)

    # DCA 250d full window
    dca_tr = monthly_dca_trades(prices, HOLD_DAYS, IS_START, OOS_END)
    dca_curve = trades_to_curve(dca_tr, prices)

    # 圖 1：full equity curve 比較
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    colors = {"B0_continuous": "grey", "V1_cooldown": "blue", "V2_pyramid": "red"}
    for vn, c in full_curves.items():
        if not c.empty:
            axes[0].plot(c["trade_date"], c["equity"], lw=1.3, color=colors[vn], label=vn)
    if not dca_curve.empty:
        axes[0].plot(dca_curve["trade_date"], dca_curve["equity"], lw=1.0, color="green",
                     alpha=0.6, label="DCA 250d")
    p_w = prices[(prices["trade_date"] >= IS_START) & (prices["trade_date"] <= OOS_END)].sort_values("trade_date")
    bh = (p_w["adj_close"] / p_w["adj_close"].iloc[0]).values
    axes[0].plot(p_w["trade_date"], bh, lw=0.8, color="black", alpha=0.5, label="0050 B&H")
    axes[0].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5, label="IS / OOS split")
    axes[0].set_ylabel("equity (per-$ basis, log)")
    axes[0].set_yscale("log")
    axes[0].set_title("H085 Phase 2.5 — B0 / V1 / V2 equity curves")
    axes[0].legend(loc="upper left")
    axes[0].grid(alpha=0.3)

    # signal panel
    s_full = sig_valid.set_index("trade_date")[SCORE_COL]
    s_full = s_full[(s_full.index >= IS_START) & (s_full.index <= OOS_END)]
    axes[1].plot(s_full.index, s_full.values, lw=0.7, color="steelblue")
    axes[1].axhline(THRESHOLD, color="red", ls="--", lw=0.7, label=f"thresh={THRESHOLD}")
    axes[1].axvline(IS_END, color="black", ls="--", lw=1, alpha=0.5)
    axes[1].set_ylabel("comp_z")
    axes[1].legend(loc="upper left")
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "v1v2_equity.png", dpi=110)
    plt.close()
    print(f"\nsaved {RESULTS_DIR / 'v1v2_equity.png'}")

    # 列出每個 variant 在 OOS 的進場明細
    print("\n=== OOS（2025-04~05 那波）每個變體的進場明細 ===")
    for vn in ["B0_continuous", "V1_cooldown", "V2_pyramid"]:
        oos_trades = [tr for tr in full_trades[vn] if tr.entry_date > pd.Timestamp(IS_END)]
        n = len(oos_trades)
        if n == 0:
            print(f"\n{vn}: 0 OOS trades")
            continue
        avg_entry = np.mean([tr.entry_price for tr in oos_trades])
        avg_ret   = np.mean([tr.return_pct for tr in oos_trades])
        print(f"\n{vn}: {n} OOS trades, avg_entry={avg_entry:.2f}, avg_ret={avg_ret*100:+.2f}%")
        for tr in oos_trades:
            print(f"  {tr.entry_date.date()}  ${tr.entry_price:6.2f} → "
                  f"{tr.exit_date.date()} ${tr.exit_price:6.2f}  ({tr.return_pct*100:+.1f}%)")

    print("\n=== complete ===")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""H071 Phase 1: Tuesday Volatility Paradox — 分佈探索。

對 EstHL / Reversal / Exhaustion 三策略，分析「為什麼振幅最大的週二績效不如預期」。

五個任務：
  T1  weekday × strategy 績效（PF/avg/WR）+ 年度穩定性
  T2  雙向甩動假說（efficiency ratio + H/L 出現時間分散度）
  T3  進場後反轉率（MAE/MFE）
  T4  趨勢濾網交叉（weekday × TrendMA 同向/反向 × strategy）
  T5  夜盤波動濾網交叉（套用 H066/H067 NVF 後週二是否被涵蓋）

Usage:
    uv run python research/active/H071-tuesday-vol-paradox/explore.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtesting import Backtest

from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    load_data_for_exhaustion,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy
from src.strategies.exhaustion import ExhaustionStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H071-tuesday-vol-paradox/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 10

# 為了公平比較星期幾，所有 weekday 過濾都解掉。
ESTHL_PARAMS = dict(
    sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
    skip_thursday=False, skip_friday=False,
)
REVERSAL_PARAMS = dict(
    vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
    signal_skip=0, sat_pullback_fraction=0.5,
)
EXHAUSTION_PARAMS = dict(
    skip_wed=False, skip_thu=False,
)

WD_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TUE = 1  # Monday=0


# ─────────────────────────── helpers ────────────────────────────────────

def calc(t: pd.DataFrame) -> dict:
    """Aggregate trade stats."""
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0.0, "PF": 0.0, "avg": 0.0, "total": 0.0, "sharpe": 0.0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    pnl_pct = t["PnL"] / t["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0.0
    return {
        "N": n,
        "WR": (t["PnL"] > 0).sum() / n,
        "PF": w / l if l > 0 else float("inf"),
        "avg": t["PnL"].mean(),
        "total": t["PnL"].sum(),
        "sharpe": sharpe,
    }


def fmt(s: dict) -> str:
    pf = "inf" if s["PF"] == float("inf") else f"{s['PF']:.2f}"
    return (f"N={s['N']:4d}  WR={s['WR']:.1%}  PF={pf:>5}  "
            f"avg={s['avg']:+5.0f}  total={s['total']:+8,.0f}  Sh={s['sharpe']:+.2f}")


def run_strategy(name: str, runner_fn, strategy_cls, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run a backtest, return (trades_df, df_used_for_backtest).

    trades_df 已加入欄位：trade_date, weekday, year, is_long
    """
    print(f"\n[{name}] loading data...")
    df = runner_fn()
    print(f"[{name}] running backtest (params={params})...")
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["ExitTime"]  = pd.to_datetime(trades["ExitTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"]   = trades["EntryTime"].dt.dayofweek
    trades["year"]      = trades["EntryTime"].dt.year
    trades["is_long"]   = trades["Size"] > 0
    print(f"[{name}] trades: {len(trades)}")
    return trades, df


def add_mae_mfe(trades: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Compute MAE/MFE per trade in price points; positive numbers."""
    mae_list, mfe_list = [], []
    for _, t in trades.iterrows():
        slc = df.loc[t["EntryTime"]:t["ExitTime"]]
        if len(slc) == 0:
            mae_list.append(np.nan); mfe_list.append(np.nan); continue
        hi, lo = slc["High"].max(), slc["Low"].min()
        ep = float(t["EntryPrice"])
        if t["is_long"]:
            mae = max(0.0, ep - lo)
            mfe = max(0.0, hi - ep)
        else:
            mae = max(0.0, hi - ep)
            mfe = max(0.0, ep - lo)
        mae_list.append(mae); mfe_list.append(mfe)
    trades["MAE"] = mae_list
    trades["MFE"] = mfe_list
    trades["MAE_MFE_ratio"] = trades.apply(
        lambda r: r["MAE"] / r["MFE"] if r["MFE"] > 0 else np.nan, axis=1
    )
    return trades


def compute_intraday_metrics() -> pd.DataFrame:
    """Per-day intraday metrics from 1m day-session bars.

    Returns DF indexed by trade_date with columns:
      open, close, day_high, day_low, day_range,
      sum_abs_ret  (sum of |1m close-to-close|),
      efficiency   (|close - open| / sum_abs_ret),
      time_high    (minutes from 08:45 to first occurrence of day_high),
      time_low     (minutes from 08:45 to first occurrence of day_low),
      weekday
    """
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        bars = conn.execute("""
            SELECT timestamp, open, high, low, close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    bars["trade_date"] = bars["timestamp"].dt.normalize()

    rows = []
    for d, day in bars.groupby("trade_date"):
        if len(day) < 60:  # skip incomplete days
            continue
        op = float(day["open"].iloc[0])
        cl = float(day["close"].iloc[-1])
        hi = float(day["high"].max())
        lo = float(day["low"].min())
        # Sum of absolute 1m returns (Kaufman ER denominator).
        diffs = day["close"].diff().abs().sum()
        eff = abs(cl - op) / diffs if diffs > 0 else np.nan
        t_hi_idx = day["high"].idxmax()
        t_lo_idx = day["low"].idxmin()
        t0 = day["timestamp"].iloc[0]
        time_hi = (day["timestamp"].loc[t_hi_idx] - t0).total_seconds() / 60.0
        time_lo = (day["timestamp"].loc[t_lo_idx] - t0).total_seconds() / 60.0
        rows.append({
            "trade_date": d, "open": op, "close": cl,
            "day_high": hi, "day_low": lo, "day_range": hi - lo,
            "sum_abs_ret": diffs, "efficiency": eff,
            "time_high": time_hi, "time_low": time_lo,
            "weekday": d.dayofweek,
        })
    out = pd.DataFrame(rows).set_index("trade_date")
    return out


def compute_night_norm() -> pd.DataFrame:
    """Same as H068: night session range / 20D SMA, indexed by next day's trade_date."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS trade_date
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
            ORDER BY trade_date
        """).df()
        day_dates_list = sorted(pd.to_datetime(day_dates_df["trade_date"]).tolist())

        night_raw = conn.execute("""
            SELECT timestamp, high, low
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()

    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    def find_next(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next)
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["night_norm"] = night["night_range"] / night["sma20"]
    return night


def compute_trend_ma() -> pd.Series:
    """10-day TrendMA on continuous (day+night) 1m close, indexed by 1m timestamps."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_all = conn.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df().set_index("timestamp")
    n_bars = 10 * 301
    return df_all["close"].rolling(n_bars, min_periods=n_bars).mean()


def add_trend_regime(trades: pd.DataFrame, trend_ma: pd.Series) -> pd.DataFrame:
    """Per trade: with_trend (long & price>MA) / against_trend / no_data."""
    ma_at_entry = trend_ma.reindex(trades["EntryTime"], method="ffill").values
    above = trades["EntryPrice"].values > ma_at_entry
    is_long = trades["is_long"].values
    regime = np.where(np.isnan(ma_at_entry), "no_data",
              np.where((is_long & above) | (~is_long & ~above), "with_trend", "against_trend"))
    trades["trend_regime"] = regime
    return trades


# ─────────────────────────── analyses ────────────────────────────────────

def task1_weekday_breakdown(strategies: dict) -> pd.DataFrame:
    """T1: per strategy, weekday breakdown + cross-year stability."""
    print("\n" + "=" * 78)
    print("T1: weekday × strategy breakdown")
    print("=" * 78)
    rows = []
    for name, (trades, _df) in strategies.items():
        print(f"\n── {name} ──")
        s_all = calc(trades)
        print(f"  ALL   {fmt(s_all)}")
        for wd in range(5):
            sub = trades[trades["weekday"] == wd]
            s = calc(sub)
            print(f"  {WD_NAMES[wd]:>4}  {fmt(s)}")
            rows.append({"strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd, **s})
        # PF rank within strategy
        wd_pfs = [calc(trades[trades["weekday"] == wd])["PF"] for wd in range(5)]
        rank = sorted(range(5), key=lambda i: wd_pfs[i])  # ascending
        print(f"  Rank (worst→best PF): {[WD_NAMES[i] for i in rank]}")
        print(f"  Tue PF rank: {rank.index(TUE) + 1} / 5")

    print("\n── Cross-year PF (Tue only) ──")
    print(f"  {'Year':>6}", end="")
    for name in strategies:
        print(f"  {name:>10}", end="")
    print()
    years = sorted({y for trades, _ in strategies.values() for y in trades["year"].unique()})
    for y in years:
        print(f"  {y:>6}", end="")
        for name, (trades, _) in strategies.items():
            sub = trades[(trades["year"] == y) & (trades["weekday"] == TUE)]
            s = calc(sub)
            cell = f"{s['PF']:.2f}({s['N']})" if s["N"] > 0 else "—"
            print(f"  {cell:>10}", end="")
        print()

    return pd.DataFrame(rows)


def task2_two_way_swing(intraday: pd.DataFrame) -> dict:
    """T2: efficiency ratio + H/L appearance time stddev by weekday."""
    print("\n" + "=" * 78)
    print("T2: 雙向甩動假說（intraday efficiency + H/L time）")
    print("=" * 78)
    print(f"\n  {'Day':>4}  {'N':>5}  {'eff_mean':>9}  {'eff_med':>8}  "
          f"{'time_hi_std':>11}  {'time_lo_std':>11}  {'range_mean':>10}")
    rows = {}
    for wd in range(5):
        sub = intraday[intraday["weekday"] == wd]
        em = sub["efficiency"].mean()
        ed = sub["efficiency"].median()
        ths = sub["time_high"].std()
        tls = sub["time_low"].std()
        rm = sub["day_range"].mean()
        rows[wd] = {"N": len(sub), "eff_mean": em, "eff_med": ed,
                    "time_hi_std": ths, "time_lo_std": tls, "range_mean": rm}
        print(f"  {WD_NAMES[wd]:>4}  {len(sub):>5}  {em:>9.4f}  {ed:>8.4f}  "
              f"{ths:>11.1f}  {tls:>11.1f}  {rm:>10.1f}")

    # Tue vs others
    tue = intraday[intraday["weekday"] == TUE]
    oth = intraday[intraday["weekday"] != TUE]
    diff = (tue["efficiency"].mean() - oth["efficiency"].mean()) / oth["efficiency"].mean() * 100
    print(f"\n  Tue eff_mean vs others: {tue['efficiency'].mean():.4f} vs {oth['efficiency'].mean():.4f}  "
          f"→ {diff:+.1f}%  (negative = more chop on Tue)")
    return rows


def task3_mae_mfe(strategies: dict) -> pd.DataFrame:
    """T3: MAE/MFE distribution by weekday × strategy."""
    print("\n" + "=" * 78)
    print("T3: 進場後反轉率（MAE/MFE）")
    print("=" * 78)
    rows = []
    for name, (trades, _df) in strategies.items():
        print(f"\n── {name} ──")
        print(f"  {'Day':>4}  {'N':>4}  {'MAE_med':>8}  {'MFE_med':>8}  "
              f"{'MAE/MFE_med':>11}  {'win_MAE':>8}  {'loss_MFE':>8}")
        for wd in range(5):
            sub = trades[(trades["weekday"] == wd) & trades["MAE"].notna()]
            if len(sub) == 0:
                print(f"  {WD_NAMES[wd]:>4}  {'0':>4}  —"); continue
            mae_med = sub["MAE"].median()
            mfe_med = sub["MFE"].median()
            ratio_med = sub["MAE_MFE_ratio"].median()
            wins = sub[sub["PnL"] > 0]
            losses = sub[sub["PnL"] <= 0]
            win_mae = wins["MAE"].mean() if len(wins) else np.nan
            loss_mfe = losses["MFE"].mean() if len(losses) else np.nan
            rows.append({
                "strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd,
                "N": len(sub), "MAE_med": mae_med, "MFE_med": mfe_med,
                "ratio_med": ratio_med, "win_MAE_mean": win_mae,
                "loss_MFE_mean": loss_mfe,
            })
            print(f"  {WD_NAMES[wd]:>4}  {len(sub):>4}  {mae_med:>8.1f}  {mfe_med:>8.1f}  "
                  f"{ratio_med:>11.2f}  {win_mae:>8.1f}  {loss_mfe:>8.1f}")
        # Tue vs other days median ratio
        tue = trades[(trades["weekday"] == TUE) & trades["MAE"].notna()]
        oth = trades[(trades["weekday"] != TUE) & trades["MAE"].notna()]
        if len(tue) > 0 and len(oth) > 0:
            tr = tue["MAE_MFE_ratio"].median()
            otr = oth["MAE_MFE_ratio"].median()
            diff_pct = (tr - otr) / otr * 100 if otr > 0 else np.nan
            print(f"  Tue MAE/MFE_med: {tr:.2f}  vs others: {otr:.2f}  → {diff_pct:+.1f}%")
    return pd.DataFrame(rows)


def task4_trend_cross(strategies: dict) -> pd.DataFrame:
    """T4: weekday × trend regime × strategy."""
    print("\n" + "=" * 78)
    print("T4: 趨勢濾網交叉（weekday × TrendMA regime）")
    print("=" * 78)
    rows = []
    for name, (trades, _df) in strategies.items():
        print(f"\n── {name} ──")
        print(f"  {'Day':>4}   {'with_N':>6} {'with_PF':>7} {'with_WR':>7}   "
              f"{'agst_N':>6} {'agst_PF':>7} {'agst_WR':>7}")
        for wd in range(5):
            sub = trades[trades["weekday"] == wd]
            with_t = calc(sub[sub["trend_regime"] == "with_trend"])
            agst_t = calc(sub[sub["trend_regime"] == "against_trend"])
            rows.append({
                "strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd,
                "with_N": with_t["N"], "with_PF": with_t["PF"], "with_WR": with_t["WR"],
                "agst_N": agst_t["N"], "agst_PF": agst_t["PF"], "agst_WR": agst_t["WR"],
            })
            print(f"  {WD_NAMES[wd]:>4}   {with_t['N']:>6} {with_t['PF']:>7.2f} {with_t['WR']:>7.1%}   "
                  f"{agst_t['N']:>6} {agst_t['PF']:>7.2f} {agst_t['WR']:>7.1%}")
    return pd.DataFrame(rows)


def task5_nvf_cross(strategies: dict, night: pd.DataFrame) -> pd.DataFrame:
    """T5: night vol filter — does it explain Tue weakness?"""
    print("\n" + "=" * 78)
    print("T5: 夜盤波動濾網交叉（NVF threshold = 0.85，與 H067 一致）")
    print("=" * 78)
    rows = []
    for name, (trades, _df) in strategies.items():
        print(f"\n── {name} ──")
        merged = trades.merge(night[["night_norm"]], left_on="trade_date",
                              right_index=True, how="inner")
        # Baseline by weekday
        print(f"  {'Day':>4}   {'base_N':>6} {'base_PF':>7}   {'NVF_N':>6} {'NVF_PF':>7}   "
              f"{'NVF_share':>9}")
        for wd in range(5):
            sub = merged[merged["weekday"] == wd]
            base = calc(sub)
            nvf = calc(sub[sub["night_norm"] >= 0.85])
            share = nvf["N"] / base["N"] if base["N"] > 0 else 0
            rows.append({
                "strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd,
                "base_N": base["N"], "base_PF": base["PF"],
                "nvf_N": nvf["N"], "nvf_PF": nvf["PF"],
                "nvf_share": share,
            })
            print(f"  {WD_NAMES[wd]:>4}   {base['N']:>6} {base['PF']:>7.2f}   "
                  f"{nvf['N']:>6} {nvf['PF']:>7.2f}   {share:>8.1%}")
    return pd.DataFrame(rows)


# ─────────────────────────── plotting ────────────────────────────────────

def plot_overview(t1_rows: pd.DataFrame, t2_rows: dict, t3_rows: pd.DataFrame,
                  t4_rows: pd.DataFrame, t5_rows: pd.DataFrame, intraday: pd.DataFrame):
    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    fig.suptitle("H071: Tuesday Volatility Paradox", fontsize=14)

    # (a) PF by weekday, three strategies
    ax = axes[0, 0]
    strats = t1_rows["strategy"].unique()
    x = np.arange(5)
    width = 0.27
    for i, s in enumerate(strats):
        sub = t1_rows[t1_rows["strategy"] == s].sort_values("wd_idx")
        ax.bar(x + (i - 1) * width, sub["PF"].values, width, label=s)
    ax.set_xticks(x); ax.set_xticklabels(WD_NAMES)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor"); ax.set_title("(a) PF by Weekday × Strategy")
    ax.legend()

    # (b) Intraday efficiency ratio by weekday (boxplot)
    ax = axes[0, 1]
    data = [intraday[intraday["weekday"] == wd]["efficiency"].dropna() for wd in range(5)]
    ax.boxplot(data, labels=WD_NAMES, showfliers=False)
    ax.set_ylabel("Efficiency ratio (|Δ|/Σ|Δ|)")
    ax.set_title("(b) Intraday Efficiency Ratio (lower = choppier)")

    # (c) MAE/MFE median ratio by weekday × strategy
    ax = axes[1, 0]
    for i, s in enumerate(strats):
        sub = t3_rows[t3_rows["strategy"] == s].sort_values("wd_idx")
        ax.plot(sub["wd_idx"].values, sub["ratio_med"].values, marker="o", label=s)
    ax.set_xticks(range(5)); ax.set_xticklabels(WD_NAMES)
    ax.set_ylabel("MAE / MFE  (median)")
    ax.set_title("(c) Reversal Pressure: MAE/MFE Ratio (higher = entries reversed more)")
    ax.legend()

    # (d) H/L appearance time stddev by weekday
    ax = axes[1, 1]
    rows = [t2_rows[wd] for wd in range(5)]
    th = [r["time_hi_std"] for r in rows]
    tl = [r["time_lo_std"] for r in rows]
    x = np.arange(5)
    ax.bar(x - 0.18, th, 0.36, label="time_high std")
    ax.bar(x + 0.18, tl, 0.36, label="time_low std")
    ax.set_xticks(x); ax.set_xticklabels(WD_NAMES)
    ax.set_ylabel("Minutes (std)")
    ax.set_title("(d) H/L Time Dispersion (higher = no consistent peak time)")
    ax.legend()

    # (e) Trend regime PF by weekday — Tue vs avg-of-others (long-trend bars)
    ax = axes[2, 0]
    for i, s in enumerate(strats):
        sub = t4_rows[t4_rows["strategy"] == s].sort_values("wd_idx")
        ax.plot(sub["wd_idx"].values, sub["with_PF"].values, marker="o",
                label=f"{s} (with_trend)")
    ax.set_xticks(range(5)); ax.set_xticklabels(WD_NAMES)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("PF (with-trend trades)")
    ax.set_title("(e) PF by Weekday — With-Trend Trades Only")
    ax.legend(fontsize=9)

    # (f) NVF cross — Tue baseline vs Tue with NVF
    ax = axes[2, 1]
    width = 0.35
    for i, s in enumerate(strats):
        sub = t5_rows[t5_rows["strategy"] == s].sort_values("wd_idx")
        x = np.arange(5) + (i - 1) * 0.27
        # Difference (NVF_PF - base_PF) per weekday
        diff = sub["nvf_PF"].values - sub["base_PF"].values
        ax.bar(x, diff, 0.27, label=s)
    ax.set_xticks(range(5)); ax.set_xticklabels(WD_NAMES)
    ax.axhline(0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("ΔPF (NVF − baseline)")
    ax.set_title("(f) NVF effect by Weekday  (positive = NVF helps)")
    ax.legend(fontsize=9)

    plt.tight_layout()
    fig_path = OUT_DIR / "h071_overview.png"
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved → {fig_path}")
    plt.close()


# ─────────────────────────── main ────────────────────────────────────────

def main():
    print("=" * 78)
    print("H071: Tuesday Volatility Paradox — Phase 1 Distribution Research")
    print("=" * 78)

    # ── Run three strategies (no weekday filters) ─────────────────────
    strategies = {}
    strategies["EstHL"]      = run_strategy("EstHL", load_data_for_orb_est_hl,
                                            ORBWithEstHLExitStrategy, ESTHL_PARAMS)
    strategies["Reversal"]   = run_strategy("Reversal", load_data_for_reversal,
                                            ReversalStrategy, REVERSAL_PARAMS)
    strategies["Exhaustion"] = run_strategy("Exhaustion", load_data_for_exhaustion,
                                            ExhaustionStrategy, EXHAUSTION_PARAMS)

    # ── Add MAE/MFE ───────────────────────────────────────────────────
    print("\nComputing MAE/MFE per trade...")
    for name, (trades, df) in strategies.items():
        strategies[name] = (add_mae_mfe(trades, df), df)

    # ── Add trend regime ──────────────────────────────────────────────
    print("Computing TrendMA & per-trade regime...")
    trend_ma = compute_trend_ma()
    for name, (trades, df) in strategies.items():
        strategies[name] = (add_trend_regime(trades, trend_ma), df)

    # ── Compute intraday + night metrics ─────────────────────────────
    print("Computing intraday metrics...")
    intraday = compute_intraday_metrics()
    print(f"Intraday days: {len(intraday)}")
    print("Computing night vol normalisation...")
    night = compute_night_norm()

    # ── Run analyses ─────────────────────────────────────────────────
    t1 = task1_weekday_breakdown(strategies)
    t2 = task2_two_way_swing(intraday)
    t3 = task3_mae_mfe(strategies)
    t4 = task4_trend_cross(strategies)
    t5 = task5_nvf_cross(strategies, night)

    # ── Save raw CSVs for downstream use ─────────────────────────────
    t1.to_csv(OUT_DIR / "t1_weekday_breakdown.csv", index=False)
    pd.DataFrame(t2).T.to_csv(OUT_DIR / "t2_intraday_summary.csv")
    t3.to_csv(OUT_DIR / "t3_mae_mfe.csv", index=False)
    t4.to_csv(OUT_DIR / "t4_trend_cross.csv", index=False)
    t5.to_csv(OUT_DIR / "t5_nvf_cross.csv", index=False)
    for name, (trades, _) in strategies.items():
        trades.to_csv(OUT_DIR / f"trades_{name.lower()}.csv", index=False)

    # ── Plots ────────────────────────────────────────────────────────
    plot_overview(t1, t2, t3, t4, t5, intraday)


if __name__ == "__main__":
    main()

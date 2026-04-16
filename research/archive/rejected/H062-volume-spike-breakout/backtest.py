"""
H062 Volume Spike Breakout — Phase 2 Backtest (optimized)

策略規則：
- 凸量定義：過去 20 根 1 分 K 均量的 N 倍（預設 3x）
- 進場：9:10 後出現凸量 K，後續 K 收盤突破高/低點
- 目標價：凸量 K 的振幅（high - low）
- 停損：等同目標價（RR = 1:1）
- 手續費：來回 2 點（含稅+滑價）
- 收盤強制平倉：13:44 前未結束的交易以該 bar 收盤平倉

用法：
  uv run python research/active/H062-volume-spike-breakout/backtest.py
  uv run python research/active/H062-volume-spike-breakout/backtest.py --multiplier 5 --max-signals 1
"""

import argparse
from datetime import time as dt_time

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
LOOKBACK = 20
COST_PER_TRADE = 2


def load_data(start=None, end=None):
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:46:00'
              AND timestamp::TIME <= '13:44:00'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    if start:
        df = df[df["date"] >= pd.Timestamp(start).date()]
    if end:
        df = df[df["date"] <= pd.Timestamp(end).date()]
    return df.reset_index(drop=True)


def precompute_spikes(df, multiplier):
    """預計算所有凸量 K，回傳 boolean mask + 相關欄位"""
    df = df.copy()
    df["vol_ma"] = df.groupby("date")["volume"].transform(
        lambda x: x.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)
    )
    df["is_spike"] = (
        (df["time"] >= dt_time(9, 10))
        & (df["time"] <= dt_time(13, 25))
        & df["vol_ma"].notna()
        & (df["volume"] >= df["vol_ma"] * multiplier)
        & ((df["high"] - df["low"]) >= 5)
    )
    return df


def compute_target(row, target_type):
    spike_range = row["high"] - row["low"]
    if target_type == "body":
        body = abs(row["close"] - row["open"])
        return body if body >= 5 else spike_range
    elif target_type == "half":
        half = spike_range / 2
        return half if half >= 5 else spike_range
    return spike_range


def run_backtest(df, multiplier=3, max_signals=0, target_type="range"):
    """事件驅動回測：先標記凸量 K，再逐日模擬"""
    df = precompute_spikes(df, multiplier)
    all_trades = []

    for date, idx_range in df.groupby("date").groups.items():
        day_idx = sorted(idx_range)
        n = len(day_idx)
        if n < LOOKBACK + 5:
            continue

        # 預提取當日 numpy arrays 加速存取
        day_times = df.loc[day_idx, "time"].values
        day_opens = df.loc[day_idx, "open"].values.astype(float)
        day_highs = df.loc[day_idx, "high"].values.astype(float)
        day_lows = df.loc[day_idx, "low"].values.astype(float)
        day_closes = df.loc[day_idx, "close"].values.astype(float)
        day_spikes = df.loc[day_idx, "is_spike"].values

        # 收集當日所有凸量 K 的資訊
        spike_list = []  # (local_idx, high, low, target)
        for i in range(n):
            if day_spikes[i]:
                row_high = day_highs[i]
                row_low = day_lows[i]
                spike_range = row_high - row_low
                if target_type == "body":
                    body = abs(day_closes[i] - day_opens[i])
                    target = body if body >= 5 else spike_range
                elif target_type == "half":
                    half = spike_range / 2
                    target = half if half >= 5 else spike_range
                else:
                    target = spike_range
                spike_list.append((i, row_high, row_low, target, day_times[i]))

        if not spike_list:
            continue

        position = None
        daily_signals = 0
        active_spikes = []  # 尚未被突破的凸量 K

        for i in range(n):
            t = day_times[i]
            bar_high = day_highs[i]
            bar_low = day_lows[i]
            bar_close = day_closes[i]

            # 加入新的凸量 K
            while spike_list and spike_list[0][0] == i:
                active_spikes.append(spike_list.pop(0))

            # 收盤強制平倉
            if position and t >= dt_time(13, 44):
                pnl = (bar_close - position["entry"]) * (1 if position["dir"] == "long" else -1)
                pnl -= COST_PER_TRADE
                all_trades.append({
                    "date": date,
                    "dir": position["dir"],
                    "spike_time": position["spike_time"],
                    "entry_time": position["entry_time"],
                    "entry_price": position["entry"],
                    "exit_time": t,
                    "exit_price": bar_close,
                    "exit_reason": "timeout",
                    "pnl_pts": pnl,
                    "target": position["target_dist"],
                })
                position = None
                continue

            # 有持倉 → 檢查 TP/SL
            if position:
                if position["dir"] == "long":
                    if bar_low <= position["sl"]:
                        pnl = position["sl"] - position["entry"] - COST_PER_TRADE
                        all_trades.append({
                            "date": date, "dir": "long",
                            "spike_time": position["spike_time"],
                            "entry_time": position["entry_time"],
                            "entry_price": position["entry"],
                            "exit_time": t, "exit_price": position["sl"],
                            "exit_reason": "sl", "pnl_pts": pnl,
                            "target": position["target_dist"],
                        })
                        position = None
                    elif bar_high >= position["tp"]:
                        pnl = position["tp"] - position["entry"] - COST_PER_TRADE
                        all_trades.append({
                            "date": date, "dir": "long",
                            "spike_time": position["spike_time"],
                            "entry_time": position["entry_time"],
                            "entry_price": position["entry"],
                            "exit_time": t, "exit_price": position["tp"],
                            "exit_reason": "tp", "pnl_pts": pnl,
                            "target": position["target_dist"],
                        })
                        position = None
                else:
                    if bar_high >= position["sl"]:
                        pnl = position["entry"] - position["sl"] - COST_PER_TRADE
                        all_trades.append({
                            "date": date, "dir": "short",
                            "spike_time": position["spike_time"],
                            "entry_time": position["entry_time"],
                            "entry_price": position["entry"],
                            "exit_time": t, "exit_price": position["sl"],
                            "exit_reason": "sl", "pnl_pts": pnl,
                            "target": position["target_dist"],
                        })
                        position = None
                    elif bar_low <= position["tp"]:
                        pnl = position["entry"] - position["tp"] - COST_PER_TRADE
                        all_trades.append({
                            "date": date, "dir": "short",
                            "spike_time": position["spike_time"],
                            "entry_time": position["entry_time"],
                            "entry_price": position["entry"],
                            "exit_time": t, "exit_price": position["tp"],
                            "exit_reason": "tp", "pnl_pts": pnl,
                            "target": position["target_dist"],
                        })
                        position = None
                continue

            # 無持倉 → 檢查突破
            if t < dt_time(9, 11) or t >= dt_time(13, 30):
                continue
            if max_signals > 0 and daily_signals >= max_signals:
                continue
            if not active_spikes:
                continue

            # 檢查最近的凸量 K（從最新往回）
            for sp_idx in range(len(active_spikes) - 1, -1, -1):
                _, sp_high, sp_low, sp_target, sp_time = active_spikes[sp_idx]

                if bar_close > sp_high:
                    entry_price = bar_close
                    position = {
                        "dir": "long",
                        "entry": entry_price,
                        "tp": entry_price + sp_target,
                        "sl": entry_price - sp_target,
                        "spike_time": sp_time,
                        "entry_time": t,
                        "target_dist": sp_target,
                    }
                    daily_signals += 1
                    active_spikes.clear()
                    break
                elif bar_close < sp_low:
                    entry_price = bar_close
                    position = {
                        "dir": "short",
                        "entry": entry_price,
                        "tp": entry_price - sp_target,
                        "sl": entry_price + sp_target,
                        "spike_time": sp_time,
                        "entry_time": t,
                        "target_dist": sp_target,
                    }
                    daily_signals += 1
                    active_spikes.clear()
                    break

    return pd.DataFrame(all_trades)


def print_summary(trades, label=""):
    if trades.empty:
        print(f"  {label}: 無交易")
        return

    n = len(trades)
    wins = trades[trades["pnl_pts"] > 0]
    losses = trades[trades["pnl_pts"] <= 0]
    total_pnl = trades["pnl_pts"].sum()
    avg_pnl = trades["pnl_pts"].mean()
    wr = len(wins) / n * 100
    pf = wins["pnl_pts"].sum() / abs(losses["pnl_pts"].sum()) if len(losses) > 0 and losses["pnl_pts"].sum() != 0 else float("inf")

    trades_pct = trades["pnl_pts"] / trades["entry_price"] * 100
    sharpe = trades_pct.mean() / trades_pct.std() * np.sqrt(252) if trades_pct.std() > 0 else 0

    cum_pnl = trades["pnl_pts"].cumsum()
    max_dd = (cum_pnl - cum_pnl.cummax()).min()

    max_consec = cur = 0
    for v in (trades["pnl_pts"] <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    exit_counts = trades["exit_reason"].value_counts()
    tp_count = exit_counts.get("tp", 0)
    sl_count = exit_counts.get("sl", 0)
    timeout_count = exit_counts.get("timeout", 0)

    longs = trades[trades["dir"] == "long"]
    shorts = trades[trades["dir"] == "short"]

    print(f"\n{'='*55}")
    if label:
        print(f"  {label}")
        print(f"{'='*55}")
    print(f"  交易筆數          {n}")
    print(f"  做多/做空         {len(longs)} / {len(shorts)}")
    print(f"  勝率              {wr:.1f}%")
    print(f"  獲利因子(PF)      {pf:.2f}")
    print(f"  平均損益          {avg_pnl:.1f} 點 (NT${avg_pnl*200:,.0f})")
    print(f"  總損益            {total_pnl:.0f} 點 (NT${total_pnl*200:,.0f})")
    print(f"  Sharpe            {sharpe:.2f}")
    print(f"  最大回撤          {max_dd:.0f} 點")
    print(f"  最大連續虧損      {max_consec} 筆")
    print(f"  出場: TP={tp_count} SL={sl_count} Timeout={timeout_count}")
    if len(longs) > 0:
        long_wr = len(longs[longs["pnl_pts"] > 0]) / len(longs) * 100
        print(f"  做多勝率          {long_wr:.1f}% (N={len(longs)})")
    if len(shorts) > 0:
        short_wr = len(shorts[shorts["pnl_pts"] > 0]) / len(shorts) * 100
        print(f"  做空勝率          {short_wr:.1f}% (N={len(shorts)})")
    print(f"  平均目標距離      {trades['target'].mean():.1f} 點")
    print(f"{'='*55}")


def yearly_summary(trades):
    if trades.empty:
        return
    trades = trades.copy()
    trades["year"] = trades["date"].apply(lambda d: d.year)
    print(f"\n--- 年度分析 ---")
    print(f"{'Year':>6} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'Total':>8}")
    for year, yt in trades.groupby("year"):
        n = len(yt)
        wr = len(yt[yt["pnl_pts"] > 0]) / n * 100
        ws = yt[yt["pnl_pts"] > 0]["pnl_pts"].sum()
        ls = abs(yt[yt["pnl_pts"] <= 0]["pnl_pts"].sum())
        pf = ws / ls if ls > 0 else float("inf")
        avg = yt["pnl_pts"].mean()
        total = yt["pnl_pts"].sum()
        print(f"  {year:>4} {n:>5} {wr:>5.1f}% {pf:>5.2f} {avg:>7.1f} {total:>7.0f}")


def segment_summary(trades):
    if trades.empty:
        return
    trades = trades.copy()

    def get_segment(t):
        if t < dt_time(10, 30):
            return "09:10-10:30"
        elif t < dt_time(12, 0):
            return "10:30-12:00"
        else:
            return "12:00-13:30"

    trades["segment"] = trades["spike_time"].apply(get_segment)
    print(f"\n--- 時段分析 ---")
    print(f"{'Segment':>14} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8}")
    for seg in ["09:10-10:30", "10:30-12:00", "12:00-13:30"]:
        st = trades[trades["segment"] == seg]
        if len(st) == 0:
            continue
        n = len(st)
        wr = len(st[st["pnl_pts"] > 0]) / n * 100
        ws = st[st["pnl_pts"] > 0]["pnl_pts"].sum()
        ls = abs(st[st["pnl_pts"] <= 0]["pnl_pts"].sum())
        pf = ws / ls if ls > 0 else float("inf")
        avg = st["pnl_pts"].mean()
        print(f"  {seg:>12} {n:>5} {wr:>5.1f}% {pf:>5.2f} {avg:>7.1f}")


def sensitivity_table(df, base_mult, base_max_sig, base_target):
    print(f"\n--- Multiplier 敏感度 ---")
    print(f"{'Mult':>6} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'Total':>8} {'Sharpe':>7}")
    for m in [2, 3, 4, 5]:
        t = run_backtest(df, multiplier=m, max_signals=base_max_sig, target_type=base_target)
        if t.empty:
            continue
        _print_sens_row(f"{m}x", t)

    print(f"\n--- Max Signals 敏感度 ---")
    print(f"{'MaxSig':>7} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'Total':>8}")
    for ms in [0, 1, 2, 3, 5]:
        t = run_backtest(df, multiplier=base_mult, max_signals=ms, target_type=base_target)
        if t.empty:
            continue
        n = len(t)
        wr = len(t[t["pnl_pts"] > 0]) / n * 100
        ws = t[t["pnl_pts"] > 0]["pnl_pts"].sum()
        ls = abs(t[t["pnl_pts"] <= 0]["pnl_pts"].sum())
        pf = ws / ls if ls > 0 else float("inf")
        avg = t["pnl_pts"].mean()
        total = t["pnl_pts"].sum()
        label = "all" if ms == 0 else str(ms)
        print(f"  {label:>5} {n:>5} {wr:>5.1f}% {pf:>5.2f} {avg:>7.1f} {total:>7.0f}")

    print(f"\n--- Target Type 敏感度 ---")
    print(f"{'Target':>7} {'N':>5} {'WR':>6} {'PF':>6} {'AvgPnL':>8} {'Total':>8}")
    for tt in ["range", "body", "half"]:
        t = run_backtest(df, multiplier=base_mult, max_signals=base_max_sig, target_type=tt)
        if t.empty:
            continue
        n = len(t)
        wr = len(t[t["pnl_pts"] > 0]) / n * 100
        ws = t[t["pnl_pts"] > 0]["pnl_pts"].sum()
        ls = abs(t[t["pnl_pts"] <= 0]["pnl_pts"].sum())
        pf = ws / ls if ls > 0 else float("inf")
        avg = t["pnl_pts"].mean()
        total = t["pnl_pts"].sum()
        print(f"  {tt:>5} {n:>5} {wr:>5.1f}% {pf:>5.2f} {avg:>7.1f} {total:>7.0f}")


def _print_sens_row(label, t):
    n = len(t)
    wr = len(t[t["pnl_pts"] > 0]) / n * 100
    ws = t[t["pnl_pts"] > 0]["pnl_pts"].sum()
    ls = abs(t[t["pnl_pts"] <= 0]["pnl_pts"].sum())
    pf = ws / ls if ls > 0 else float("inf")
    avg = t["pnl_pts"].mean()
    total = t["pnl_pts"].sum()
    pct = t["pnl_pts"] / t["entry_price"] * 100
    sharpe = pct.mean() / pct.std() * np.sqrt(252) if pct.std() > 0 else 0
    print(f"  {label:>4} {n:>5} {wr:>5.1f}% {pf:>5.2f} {avg:>7.1f} {total:>7.0f} {sharpe:>6.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--multiplier", type=float, default=3)
    parser.add_argument("--max-signals", type=int, default=0)
    parser.add_argument("--target", default="range", choices=["range", "body", "half"])
    parser.add_argument("--is-split", default="2024-01-01")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data(args.start, args.end)
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} days")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}")
    print(f"Params: mult={args.multiplier}x, target={args.target}, max_signals={args.max_signals or 'all'}")

    trades = run_backtest(df, multiplier=args.multiplier, max_signals=args.max_signals, target_type=args.target)
    print_summary(trades, "Full Period")
    yearly_summary(trades)
    segment_summary(trades)

    if args.is_split and not trades.empty:
        split_date = pd.Timestamp(args.is_split).date()
        is_trades = trades[trades["date"] < split_date]
        oos_trades = trades[trades["date"] >= split_date]

        print(f"\n\n{'#'*55}")
        print(f"  IN-SAMPLE (< {args.is_split})")
        print_summary(is_trades, f"In-Sample")
        yearly_summary(is_trades)

        print(f"\n{'#'*55}")
        print(f"  OUT-OF-SAMPLE (>= {args.is_split})")
        print_summary(oos_trades, f"Out-of-Sample")
        yearly_summary(oos_trades)

    print(f"\n\n{'#'*55}")
    print("  PARAMETER SENSITIVITY")
    print(f"{'#'*55}")
    sensitivity_table(df, args.multiplier, args.max_signals, args.target)


if __name__ == "__main__":
    main()

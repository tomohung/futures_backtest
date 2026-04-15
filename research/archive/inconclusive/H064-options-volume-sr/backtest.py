#!/usr/bin/env python3
"""
H064 Phase 2: Put Volume S1 支撐回測
規則：
  - 每日用前一日近月 Put 成交量最大的履約價（S1）作為支撐
  - 日盤中價格從上方碰到 S1 ± touch_zone 時做多
  - 停損：entry - sl_pct%
  - 停利：entry + tp_pct%
  - 收盤強制平倉（13:44 前最後一根）
  - 每日只做一次

In-sample: 2023-01 ~ 2025-06
Out-of-sample: 2025-07 ~ 2026-04
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

# --- 參數 ---
TOUCH_PCT = 0.15       # 觸及 = S1 ± 0.15%
SL_PCT = 0.20          # 停損 0.20%
TP_PCT = 0.30          # 停利 0.30%
COST_PT = 3.0          # 來回成本（手續費 + 滑價）
ENTRY_START = 30       # 最早進場：開盤後 30 分鐘（09:15）
ENTRY_END = 240        # 最晚進場：開盤後 240 分鐘（12:45），留 1 小時給持倉


def _patch_params(sl, tp):
    global SL_PCT, TP_PCT
    SL_PCT = sl
    TP_PCT = tp


def get_options_sr(conn, trade_date, fut_close):
    """同 explore.py：取前日 Put 成交量最大的履約價。"""
    top_contract = conn.execute("""
        SELECT contract FROM ticks_options
        WHERE trade_date = ?
          AND LENGTH(contract) = 6
        GROUP BY contract
        ORDER BY SUM(volume) DESC LIMIT 1
    """, [trade_date]).fetchone()

    if not top_contract:
        return None

    rows = conn.execute("""
        SELECT strike, SUM(volume) AS vol
        FROM ticks_options
        WHERE trade_date = ?
          AND contract = ?
          AND put_call = 'P'
          AND strike BETWEEN ? - 3000 AND ? + 3000
        GROUP BY strike
        ORDER BY vol DESC
    """, [trade_date, top_contract[0], float(fut_close), float(fut_close)]).fetchall()

    if not rows:
        return None

    # Put volume 最大且在現價下方的
    for strike, vol in rows:
        s = float(strike)
        if s < float(fut_close):
            total_put = sum(v for _, v in rows)
            top3_vol = sum(v for _, v in rows[:3])
            return {
                "s1_price": s,
                "s1_vol": vol,
                "concentration": top3_vol / total_put if total_put > 0 else 0,
            }
    return None


def run_backtest(conn, start_date, end_date, label):
    """對指定期間跑回測。"""
    from datetime import date
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    # 取有選擇權的交易日
    opt_days = [r[0] for r in conn.execute("""
        SELECT DISTINCT trade_date FROM ticks_options
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date
    """, [start_date, end_date]).fetchall()]

    fut_days = [r[0] for r in conn.execute("""
        SELECT DISTINCT timestamp::DATE AS td
        FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
          AND timestamp::DATE >= ? AND timestamp::DATE <= ?
        ORDER BY td
    """, [start_date, end_date]).fetchall()]

    trades = []
    days_with_signal = 0
    days_no_signal = 0

    for opt_date in opt_days:
        # T+1
        next_days = [d for d in fut_days if d > opt_date]
        if not next_days:
            continue
        target_date = next_days[0]
        if target_date > end_date:
            break

        # 前日期貨收盤
        prev_close = conn.execute("""
            SELECT close FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp DESC LIMIT 1
        """, [opt_date]).fetchone()
        if not prev_close:
            prev_close = conn.execute("""
                SELECT close FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND timestamp::DATE < ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY timestamp DESC LIMIT 1
            """, [opt_date]).fetchone()
        if not prev_close:
            continue
        fut_close = float(prev_close[0])

        sr = get_options_sr(conn, opt_date, fut_close)
        if sr is None:
            days_no_signal += 1
            continue

        s1 = sr["s1_price"]
        touch_zone = s1 * TOUCH_PCT / 100
        sl_dist = s1 * SL_PCT / 100
        tp_dist = s1 * TP_PCT / 100

        # 取日盤 1分K
        rows = conn.execute("""
            SELECT timestamp, open, high, low, close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
        """, [target_date]).fetchall()
        if not rows or len(rows) < 30:
            continue

        days_with_signal += 1

        # 模擬交易
        entry_price = None
        entry_idx = None

        for i, (ts, op, hi, lo, cl) in enumerate(rows):
            hi, lo, cl = float(hi), float(lo), float(cl)

            if entry_price is None:
                # 尚未進場
                if i < ENTRY_START or i > ENTRY_END:
                    continue
                # 價格從上方碰到 S1
                if lo <= s1 + touch_zone and hi >= s1 - touch_zone:
                    entry_price = cl
                    entry_idx = i
                    sl_price = entry_price - sl_dist
                    tp_price = entry_price + tp_dist
            else:
                # 已進場，檢查出場
                exit_price = None
                exit_reason = None

                if lo <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL"
                elif hi >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP"
                elif i >= len(rows) - 2:  # 收盤前平倉
                    exit_price = cl
                    exit_reason = "EOD"

                if exit_price is not None:
                    pnl_pt = exit_price - entry_price - COST_PT
                    pnl_pct = pnl_pt / entry_price * 100

                    trades.append({
                        "date": target_date,
                        "s1": s1,
                        "entry": entry_price,
                        "exit": exit_price,
                        "reason": exit_reason,
                        "pnl_pt": pnl_pt,
                        "pnl_pct": pnl_pct,
                        "bars_held": i - entry_idx,
                        "concentration": sr["concentration"],
                    })
                    break

    # --- 統計 ---
    print(f"\n{'='*60}")
    print(f"{label}: {start_date} ~ {end_date}")
    print(f"{'='*60}")
    print(f"有信號天數: {days_with_signal}, 無信號天數: {days_no_signal}")

    if not trades:
        print("無交易")
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    n = len(df)
    wins = df[df["pnl_pt"] > 0]
    losses = df[df["pnl_pt"] <= 0]

    win_rate = len(wins) / n
    avg_win = wins["pnl_pct"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl_pct"].mean() if len(losses) > 0 else 0
    total_pnl = df["pnl_pct"].sum()
    avg_pnl = df["pnl_pct"].mean()

    # Sharpe (日化)
    daily_ret = df.set_index("date")["pnl_pct"]
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0

    # Max drawdown
    cum = df["pnl_pct"].cumsum()
    dd = cum - cum.cummax()
    max_dd = dd.min()

    # 獲利因子
    gross_win = wins["pnl_pct"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_pct"].sum()) if len(losses) > 0 else 0.01
    pf = gross_win / gross_loss

    # 連續虧損
    max_consec = cur = 0
    for v in (df["pnl_pt"] <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    print(f"交易次數: {n}")
    print(f"勝率: {win_rate:.1%}")
    print(f"平均獲利: {avg_win:+.3f}%")
    print(f"平均虧損: {avg_loss:+.3f}%")
    print(f"期望值: {avg_pnl:+.3f}% / 筆")
    print(f"累計損益: {total_pnl:+.2f}%")
    print(f"Sharpe: {sharpe:.2f}")
    print(f"Max DD: {max_dd:.2f}%")
    print(f"獲利因子: {pf:.2f}")
    print(f"最大連續虧損: {max_consec} 筆")
    print(f"平均持倉: {df['bars_held'].mean():.0f} bars")

    # 按出場原因
    print(f"\n出場原因分佈:")
    for reason, sub in df.groupby("reason"):
        print(f"  {reason}: {len(sub)} 筆 ({len(sub)/n:.0%}), "
              f"avg pnl={sub['pnl_pct'].mean():+.3f}%")

    # 按年度
    df["year"] = pd.to_datetime(df["date"]).dt.year
    print(f"\n年度分佈:")
    for yr, sub in df.groupby("year"):
        w = sub[sub["pnl_pt"] > 0]
        print(f"  {yr}: {len(sub)} 筆, 勝率={len(w)/len(sub):.0%}, "
              f"累計={sub['pnl_pct'].sum():+.2f}%, "
              f"avg={sub['pnl_pct'].mean():+.3f}%")

    # 按集中度
    df["conc_grp"] = pd.cut(
        df["concentration"], bins=[0, 0.3, 0.5, 1.0],
        labels=["低(<30%)", "中(30-50%)", "高(>50%)"]
    )
    print(f"\n集中度分組:")
    for grp, sub in df.groupby("conc_grp", observed=True):
        if sub.empty:
            continue
        w = sub[sub["pnl_pt"] > 0]
        print(f"  {grp}: {len(sub)} 筆, 勝率={len(w)/len(sub):.0%}, "
              f"avg={sub['pnl_pct'].mean():+.3f}%")

    return df


def main():
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        print(f"參數: touch={TOUCH_PCT}%, SL={SL_PCT}%, TP={TP_PCT}%, "
              f"cost={COST_PT}pt, entry={ENTRY_START}~{ENTRY_END}min")

        # In-sample
        is_df = run_backtest(conn, "2023-01-01", "2025-06-30", "In-Sample")

        # Out-of-sample
        oos_df = run_backtest(conn, "2025-07-01", "2026-04-30", "Out-of-Sample")

        # 參數敏感度：只跑 IS 期間
        print(f"\n{'='*60}")
        print("參數敏感度分析 (In-Sample)")
        print(f"{'='*60}")

        import itertools
        sl_range = [0.15, 0.20, 0.25, 0.30]
        tp_range = [0.20, 0.30, 0.40, 0.50]

        # 暫存原始參數，用 function default 改寫
        orig_sl, orig_tp = SL_PCT, TP_PCT

        results = []
        for sl, tp in itertools.product(sl_range, tp_range):
            _patch_params(sl, tp)
            import io, contextlib
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                df = run_backtest(conn, "2023-01-01", "2025-06-30", "sens")
            if df.empty:
                continue
            n = len(df)
            wins = df[df["pnl_pt"] > 0]
            wr = len(wins) / n if n > 0 else 0
            avg = df["pnl_pct"].mean()
            total = df["pnl_pct"].sum()
            sharpe = df["pnl_pct"].mean() / df["pnl_pct"].std() * np.sqrt(252) if df["pnl_pct"].std() > 0 else 0
            results.append({
                "SL": sl, "TP": tp, "N": n, "WR": wr,
                "Avg": avg, "Total": total, "Sharpe": sharpe
            })

        _patch_params(orig_sl, orig_tp)

        sens_df = pd.DataFrame(results)
        if not sens_df.empty:
            sens_df = sens_df.sort_values("Total", ascending=False)
            print(f"\n{'SL':>5s} {'TP':>5s} {'N':>4s} {'WR':>5s} {'Avg%':>7s} {'Total%':>8s} {'Sharpe':>7s}")
            for _, r in sens_df.iterrows():
                print(f"{r['SL']:>5.2f} {r['TP']:>5.2f} {int(r['N']):>4d} "
                      f"{r['WR']:>4.0%} {r['Avg']:>+6.3f} {r['Total']:>+7.2f} {r['Sharpe']:>7.2f}")


if __name__ == "__main__":
    main()

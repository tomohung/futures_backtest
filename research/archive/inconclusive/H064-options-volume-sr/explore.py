#!/usr/bin/env python3
"""
H064 Phase 1: 選擇權成交量作為支撐壓力
用前日近月合約 Call/Put 成交量最大的履約價作為壓力/支撐，
檢驗期貨日盤碰到時的反應 vs 隨機。
附帶：PCR 方向預測。
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from collections import defaultdict

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

TOUCH_PCT = 0.15
REACTION_BARS = 10
REACTION_PCT = 0.10
N_RANDOM_TRIALS = 500


def get_options_sr(conn, trade_date, fut_close):
    """
    計算某日的選擇權 volume S/R：
    - 近月合約（月合約中成交量最大的）
    - Call volume 最大的履約價 = R1，第二大 = R2
    - Put volume 最大的履約價 = S1，第二大 = S2
    - 只看 ATM ± 3000 點範圍
    """
    # 找近月月合約（排除週合約 W/F）
    top_contract = conn.execute("""
        SELECT contract
        FROM ticks_options
        WHERE trade_date = ?
          AND LENGTH(contract) = 6  -- 月合約 YYYYMM
        GROUP BY contract
        ORDER BY SUM(volume) DESC
        LIMIT 1
    """, [trade_date]).fetchone()

    if not top_contract:
        return None
    contract = top_contract[0]

    rows = conn.execute("""
        SELECT strike, put_call, SUM(volume) AS vol
        FROM ticks_options
        WHERE trade_date = ?
          AND contract = ?
          AND strike BETWEEN ? - 3000 AND ? + 3000
        GROUP BY strike, put_call
    """, [trade_date, contract, float(fut_close), float(fut_close)]).fetchall()

    if not rows:
        return None

    call_vol = defaultdict(int)
    put_vol = defaultdict(int)
    total_call = 0
    total_put = 0

    for strike, pc, vol in rows:
        s = float(strike)
        if pc == 'C':
            call_vol[s] += vol
            total_call += vol
        else:
            put_vol[s] += vol
            total_put += vol

    if not call_vol or not put_vol:
        return None

    # 排序取 top 3
    call_sorted = sorted(call_vol.items(), key=lambda x: -x[1])
    put_sorted = sorted(put_vol.items(), key=lambda x: -x[1])

    # 壓力：Call volume 最大的履約價中，位於現價上方的
    call_above = [(s, v) for s, v in call_sorted if s > float(fut_close)]
    # 支撐：Put volume 最大的履約價中，位於現價下方的
    put_below = [(s, v) for s, v in put_sorted if s < float(fut_close)]

    if not call_above or not put_below:
        return None

    r1 = call_above[0]
    r2 = call_above[1] if len(call_above) > 1 else None
    s1 = put_below[0]
    s2 = put_below[1] if len(put_below) > 1 else None

    pcr = total_put / total_call if total_call > 0 else None

    # 集中度：top3 占比
    top3_call = sum(v for _, v in call_sorted[:3]) / total_call if total_call > 0 else 0
    top3_put = sum(v for _, v in put_sorted[:3]) / total_put if total_put > 0 else 0

    return {
        "contract": contract,
        "r1": {"price": r1[0], "vol": r1[1]},
        "r2": {"price": r2[0], "vol": r2[1]} if r2 else None,
        "s1": {"price": s1[0], "vol": s1[1]},
        "s2": {"price": s2[0], "vol": s2[1]} if s2 else None,
        "pcr": pcr,
        "total_call": total_call,
        "total_put": total_put,
        "concentration_call": top3_call,
        "concentration_put": top3_put,
    }


def check_touch_reaction(bars_1m, sr_price, touch_pct, reaction_bars, reaction_pct):
    """檢查期貨 1分K 觸及某價位後的反應。"""
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values
    n = len(closes)

    touch_zone = sr_price * touch_pct / 100
    threshold = sr_price * reaction_pct / 100

    events = []
    last_touch = -reaction_bars

    for i in range(n):
        if i - last_touch < reaction_bars:
            continue
        if lows[i] <= sr_price + touch_zone and highs[i] >= sr_price - touch_zone:
            last_touch = i
            entry = closes[i]
            above = closes[max(0, i - 1)] > sr_price

            end_idx = min(i + reaction_bars, n - 1)
            if i >= n - 1:
                continue
            future = closes[i + 1:end_idx + 1]
            if len(future) == 0:
                continue

            if above:
                max_rev = max(future) - entry
            else:
                max_rev = entry - min(future)

            rev_pct = float(max_rev) / entry * 100

            events.append({
                "entry": float(entry),
                "max_reversal_pt": float(max_rev),
                "max_reversal_pct": rev_pct,
                "is_effective": float(max_rev) >= threshold,
            })
    return events


def build_random_baseline(bars_1m, n_trials, touch_pct, reaction_bars, reaction_pct, rng):
    """隨機對照組。"""
    highs = bars_1m["high"].values
    lows = bars_1m["low"].values
    closes = bars_1m["close"].values
    n = len(closes)
    price_min = float(lows.min())
    price_max = float(highs.max())

    events = []
    for _ in range(n_trials):
        rp = rng.uniform(price_min, price_max)
        touch_zone = rp * touch_pct / 100
        threshold = rp * reaction_pct / 100
        last_touch = -reaction_bars

        for i in range(n):
            if i - last_touch < reaction_bars:
                continue
            if lows[i] <= rp + touch_zone and highs[i] >= rp - touch_zone:
                last_touch = i
                entry = closes[i]
                above = closes[max(0, i - 1)] > rp
                end_idx = min(i + reaction_bars, n - 1)
                if i >= n - 1:
                    continue
                future = closes[i + 1:end_idx + 1]
                if len(future) == 0:
                    continue

                if above:
                    max_rev = max(future) - entry
                else:
                    max_rev = entry - min(future)

                rev_pct = float(max_rev) / entry * 100
                events.append({
                    "max_reversal_pct": rev_pct,
                    "is_effective": float(max_rev) >= threshold,
                })
    return events


def main():
    rng = np.random.default_rng(42)

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 找所有有選擇權資料的交易日
        opt_days = conn.execute("""
            SELECT DISTINCT trade_date FROM ticks_options ORDER BY trade_date
        """).fetchall()
        opt_days = [r[0] for r in opt_days]

        # 找所有有期貨日盤資料的交易日
        fut_days = [r[0] for r in conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY td
        """).fetchall()]

        print(f"選擇權資料: {opt_days[0]} ~ {opt_days[-1]} ({len(opt_days)} 天)")

        # --- S/R 觸及分析 ---
        sr_events_r1 = []  # R1 壓力
        sr_events_s1 = []  # S1 支撐
        sr_events_r2 = []
        sr_events_s2 = []
        random_events = []
        pcr_records = []
        days_analyzed = 0

        for i, opt_date in enumerate(opt_days):
            # T+1 交易日（下一個有期貨資料的日子）
            next_fut_days = [d for d in fut_days if d > opt_date]
            if not next_fut_days:
                continue
            target_date = next_fut_days[0]

            # 用前日期貨收盤當 ATM 參考
            prev_close = conn.execute("""
                SELECT LAST(close ORDER BY timestamp)
                FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND timestamp::DATE = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            """, [opt_date]).fetchone()
            if not prev_close or prev_close[0] is None:
                # opt_date 可能不是期貨交易日，用前一日
                prev_close = conn.execute("""
                    SELECT close FROM ohlcv_1m
                    WHERE symbol = 'TX'
                      AND timestamp::DATE < ?
                      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, [opt_date]).fetchone()
            if not prev_close or prev_close[0] is None:
                continue

            fut_close = float(prev_close[0])
            sr = get_options_sr(conn, opt_date, fut_close)
            if sr is None:
                continue

            # 取 target_date 的日盤 1分K
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

            bars = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
            for col in ["open", "high", "low", "close"]:
                bars[col] = bars[col].astype(float)
            days_analyzed += 1

            # 檢查各 S/R 的觸及反應
            for level, bucket in [
                (sr["r1"], sr_events_r1),
                (sr["s1"], sr_events_s1),
            ]:
                evts = check_touch_reaction(
                    bars, level["price"], TOUCH_PCT, REACTION_BARS, REACTION_PCT
                )
                for e in evts:
                    e["sr_price"] = level["price"]
                    e["sr_vol"] = level["vol"]
                    e["trade_date"] = target_date
                    e["concentration"] = sr["concentration_call"] if level == sr["r1"] else sr["concentration_put"]
                bucket.extend(evts)

            if sr["r2"]:
                evts = check_touch_reaction(
                    bars, sr["r2"]["price"], TOUCH_PCT, REACTION_BARS, REACTION_PCT
                )
                for e in evts:
                    e["trade_date"] = target_date
                sr_events_r2.extend(evts)
            if sr["s2"]:
                evts = check_touch_reaction(
                    bars, sr["s2"]["price"], TOUCH_PCT, REACTION_BARS, REACTION_PCT
                )
                for e in evts:
                    e["trade_date"] = target_date
                sr_events_s2.extend(evts)

            # 隨機對照
            rand = build_random_baseline(
                bars, 5, TOUCH_PCT, REACTION_BARS, REACTION_PCT, rng
            )
            random_events.extend(rand)

            # PCR 記錄
            day_open = float(rows[0][1])
            day_close = float(rows[-1][4])
            day_chg_pct = (day_close - day_open) / day_open * 100
            pcr_records.append({
                "opt_date": opt_date,
                "target_date": target_date,
                "pcr": sr["pcr"],
                "day_chg_pct": day_chg_pct,
                "day_up": day_close > day_open,
            })

        print(f"分析天數: {days_analyzed}")

        # === 結果 ===
        print(f"\n{'='*60}")
        print("選擇權 Volume S/R 觸及反應分析")
        print(f"{'='*60}")

        rdf = pd.DataFrame(random_events)
        rand_hit = rdf["is_effective"].mean() if not rdf.empty else 0
        rand_rev = rdf["max_reversal_pct"].mean() if not rdf.empty else 0

        print(f"\n{'隨機基準':14s} 命中率={rand_hit:.1%}, 平均反彈={rand_rev:.3f}% (N={len(rdf)})")

        for label, events in [
            ("R1 壓力", sr_events_r1),
            ("S1 支撐", sr_events_s1),
            ("R2 壓力", sr_events_r2),
            ("S2 支撐", sr_events_s2),
        ]:
            df = pd.DataFrame(events)
            if df.empty:
                print(f"\n{label}: 無觸及事件")
                continue
            hit = df["is_effective"].mean()
            rev = df["max_reversal_pct"].mean()
            print(f"\n--- {label} ---")
            print(f"  命中率={hit:.1%}, 平均反彈={rev:.3f}% (N={len(df)})")

            if not rdf.empty:
                cont = [
                    [int(df["is_effective"].sum()), int((~df["is_effective"]).sum())],
                    [int(rdf["is_effective"].sum()), int((~rdf["is_effective"]).sum())],
                ]
                if all(v > 0 for row in cont for v in row):
                    chi2, p, _, _ = stats.chi2_contingency(cont)
                    direction = "S/R較好" if hit > rand_hit else "S/R較差"
                    print(f"  vs 隨機: χ² p={p:.4f} ({direction}) {'***' if p < 0.05 else ''}")

        # 按集中度分組（R1）
        r1_df = pd.DataFrame(sr_events_r1)
        if not r1_df.empty and "concentration" in r1_df.columns:
            print(f"\n--- R1 壓力：按成交量集中度 ---")
            r1_df["conc_group"] = pd.cut(
                r1_df["concentration"],
                bins=[0, 0.3, 0.5, 1.0],
                labels=["低(<30%)", "中(30-50%)", "高(>50%)"]
            )
            for grp, sub in r1_df.groupby("conc_group", observed=True):
                if sub.empty:
                    continue
                print(f"  {grp}: 命中率={sub['is_effective'].mean():.1%}, "
                      f"反彈={sub['max_reversal_pct'].mean():.3f}% (N={len(sub)})")

        s1_df = pd.DataFrame(sr_events_s1)
        if not s1_df.empty and "concentration" in s1_df.columns:
            print(f"\n--- S1 支撐：按成交量集中度 ---")
            s1_df["conc_group"] = pd.cut(
                s1_df["concentration"],
                bins=[0, 0.3, 0.5, 1.0],
                labels=["低(<30%)", "中(30-50%)", "高(>50%)"]
            )
            for grp, sub in s1_df.groupby("conc_group", observed=True):
                if sub.empty:
                    continue
                print(f"  {grp}: 命中率={sub['is_effective'].mean():.1%}, "
                      f"反彈={sub['max_reversal_pct'].mean():.3f}% (N={len(sub)})")

        # === PCR 分析 ===
        print(f"\n{'='*60}")
        print("PCR 方向預測分析")
        print(f"{'='*60}")

        pcr_df = pd.DataFrame(pcr_records)
        if not pcr_df.empty:
            print(f"\nPCR 統計: mean={pcr_df['pcr'].mean():.2f}, "
                  f"median={pcr_df['pcr'].median():.2f}, "
                  f"std={pcr_df['pcr'].std():.2f}")

            # PCR 分組
            pcr_df["pcr_group"] = pd.cut(
                pcr_df["pcr"],
                bins=[0, 0.8, 1.0, 1.2, 10],
                labels=["<0.8 偏多", "0.8-1.0 中性偏多", "1.0-1.2 中性偏空", ">1.2 偏空"]
            )
            print(f"\n{'PCR 區間':<20s} {'漲日':>4s} {'跌日':>4s} {'漲率':>6s} {'平均漲跌%':>9s} N")
            for grp, sub in pcr_df.groupby("pcr_group", observed=True):
                up = sub["day_up"].sum()
                down = len(sub) - up
                up_rate = up / len(sub)
                avg_chg = sub["day_chg_pct"].mean()
                print(f"  {str(grp):<18s} {up:>4d} {down:>4d} {up_rate:>5.1%} {avg_chg:>+8.3f}% (N={len(sub)})")

            # 反向指標測試：PCR > 1.2 時做多、PCR < 0.8 時做空
            extreme_high = pcr_df[pcr_df["pcr"] > 1.2]
            extreme_low = pcr_df[pcr_df["pcr"] < 0.8]
            if len(extreme_high) > 10:
                print(f"\n  PCR > 1.2 → 做多（反向）: 漲率={extreme_high['day_up'].mean():.1%}, "
                      f"avg chg={extreme_high['day_chg_pct'].mean():+.3f}% (N={len(extreme_high)})")
            if len(extreme_low) > 10:
                print(f"  PCR < 0.8 → 做空（反向）: 跌率={(~extreme_low['day_up']).mean():.1%}, "
                      f"avg chg={extreme_low['day_chg_pct'].mean():+.3f}% (N={len(extreme_low)})")


if __name__ == "__main__":
    main()

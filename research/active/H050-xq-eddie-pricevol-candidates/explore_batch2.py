#!/usr/bin/env python3
"""H050 Phase 0: 批次 1 剩餘 + 批次 2 候選評估。

批次 1 剩餘：
  G2 — 開高破平盤後又站回（開高→跌破平盤→站回，洗盤結束）
  C1 — VSA 無供應（窄幅低量回檔 = 賣壓枯竭）
  C2 — Weis Wave Volume（按波段累積量的背離）

批次 2：
  E2 — Choppy Market Index（盤整 vs 趨勢）
  D1 — STARC 平均波幅通道（ATR 通道，對比 EstRange SatZone）

批次 3 預覽：
  C3 — VWMACD（量加權 MACD）
  C10 — Force Index（每根 K 棒多空力度）

Usage:
    uv run python research/active/H050-xq-eddie-pricevol-candidates/explore_batch2.py
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB_PATH = "data/futures.duckdb"


def load_day_session():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def evaluate_g2(df):
    """G2: 開高破平盤後又站回。

    原始定義（個股）：開高 > 2% → 跌破平盤 → 站回。
    台指期改造：開高 > N 點 → 盤中跌破開盤價 → 站回開盤價上方 → 做多。

    測量：站回後做多至收盤的報酬。
    """
    print("\n" + "=" * 72)
    print("G2: 開高破平盤後又站回")
    print("=" * 72)

    daily = df.groupby(df.index.date)
    n_days = len(set(df.index.date))

    # 先算前一日收盤作為「平盤」
    daily_close = df.groupby(df.index.date)["Close"].last()
    dates = sorted(daily_close.index)

    for gap_min in [30, 50, 80, 100]:
        results = []
        for i in range(1, len(dates)):
            prev_close = daily_close.iloc[i - 1]
            date = dates[i]
            day = daily.get_group(date)
            day_open = day["Open"].iloc[0]

            # 開高條件
            gap = day_open - prev_close
            if gap < gap_min:
                continue

            # 尋找：先跌破 day_open，再站回
            broke_below = False
            stood_back = False
            entry_idx = None

            for j in range(1, len(day)):
                close = day["Close"].iloc[j]
                if not broke_below and close < day_open:
                    broke_below = True
                elif broke_below and not stood_back and close > day_open:
                    stood_back = True
                    entry_idx = j
                    break

            if stood_back and entry_idx is not None:
                entry = day["Close"].iloc[entry_idx]
                exit_close = day["Close"].iloc[-1]
                remaining = day.iloc[entry_idx:]
                pnl = exit_close - entry
                mfe = remaining["High"].max() - entry
                mae = entry - remaining["Low"].min()
                results.append({
                    "date": date,
                    "gap": gap,
                    "entry_time": day.index[entry_idx].strftime("%H:%M"),
                    "pnl": pnl,
                    "mfe": mfe,
                    "mae": mae,
                })

        n = len(results)
        if n == 0:
            print(f"  Gap >= {gap_min}pt: 0 signals")
            continue
        r = pd.DataFrame(results)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  Gap >= {gap_min}pt: N={n} ({n/n_days*100:.1f}%) "
              f"WR={wr:.1f}% PF={pf:.2f} AvgPnL={r['pnl'].mean():+.1f}pt "
              f"MFE={r['mfe'].mean():.0f} MAE={r['mae'].mean():.0f}")

    # Also test short side: gap down → break above open → fall back → short
    print("\n  --- 反向：開低→站回平盤→又跌破 → 做空 ---")
    for gap_min in [30, 50, 80, 100]:
        results = []
        for i in range(1, len(dates)):
            prev_close = daily_close.iloc[i - 1]
            date = dates[i]
            day = daily.get_group(date)
            day_open = day["Open"].iloc[0]

            gap = prev_close - day_open  # gap down
            if gap < gap_min:
                continue

            broke_above = False
            fell_back = False
            entry_idx = None

            for j in range(1, len(day)):
                close = day["Close"].iloc[j]
                if not broke_above and close > day_open:
                    broke_above = True
                elif broke_above and not fell_back and close < day_open:
                    fell_back = True
                    entry_idx = j
                    break

            if fell_back and entry_idx is not None:
                entry = day["Close"].iloc[entry_idx]
                exit_close = day["Close"].iloc[-1]
                pnl = entry - exit_close  # short
                results.append({"date": date, "pnl": pnl})

        n = len(results)
        if n == 0:
            print(f"  Gap >= {gap_min}pt: 0 signals")
            continue
        r = pd.DataFrame(results)
        wins = r[r["pnl"] > 0]
        losses = r[r["pnl"] < 0]
        wr = len(wins) / n * 100
        pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf")
        print(f"  Gap >= {gap_min}pt: N={n} WR={wr:.1f}% PF={pf:.2f} AvgPnL={r['pnl'].mean():+.1f}pt")


def evaluate_c1_vsa(df):
    """C1: VSA 無供應 (No Supply)。

    條件（改造版，用 5m K）：
    - 近 20 根 MA 方向向上（上升趨勢中）
    - 當根：收跌（Close < Open）+ 窄幅（range < MA range × 0.5）+ 低量（vol < MA vol × 0.5）
    - 下一根收漲 → 做多

    測量：進場後 N 根的報酬。
    """
    print("\n" + "=" * 72)
    print("C1: VSA 無供應 (No Supply)")
    print("=" * 72)

    # Use 5m bars for cleaner signals
    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    df5["Range"] = df5["High"] - df5["Low"]
    df5["MA20"] = df5["Close"].rolling(20).mean()
    df5["MA20_prev"] = df5["MA20"].shift(1)
    df5["RangeMA"] = df5["Range"].rolling(20).mean()
    df5["VolMA"] = df5["Volume"].rolling(20).mean()

    # Trend up: MA rising
    df5["trend_up"] = df5["MA20"] > df5["MA20_prev"]

    # No Supply bar: close < open, narrow range, low volume
    for range_mult, vol_mult in [(0.5, 0.5), (0.6, 0.6), (0.7, 0.5), (0.5, 0.7)]:
        df5["no_supply"] = (
            df5["trend_up"] &
            (df5["Close"] < df5["Open"]) &
            (df5["Range"] < df5["RangeMA"] * range_mult) &
            (df5["Volume"] < df5["VolMA"] * vol_mult)
        )

        # Next bar closes up → entry
        df5["next_up"] = df5["Close"].shift(-1) > df5["Open"].shift(-1)
        signals = df5[df5["no_supply"] & df5["next_up"]]

        # Only day session (filter out early/late bars)
        signals = signals[(signals.index.time >= pd.Timestamp("09:00").time()) &
                          (signals.index.time <= pd.Timestamp("12:00").time())]

        n = len(signals)
        if n == 0:
            print(f"  Range<{range_mult}x Vol<{vol_mult}x: 0 signals")
            continue

        # Measure: 12-bar (60min) forward return
        pnls = []
        for idx in signals.index:
            pos = df5.index.get_loc(idx)
            if pos + 13 >= len(df5):
                continue
            entry = float(df5.iloc[pos + 1]["Open"])  # enter on next bar open
            future = df5.iloc[pos + 1:pos + 13]  # 12 bars = 60min
            exit_price = float(future.iloc[-1]["Close"])
            pnls.append(exit_price - entry)

        if len(pnls) == 0:
            print(f"  Range<{range_mult}x Vol<{vol_mult}x: {n} signals but no measurable trades")
            continue

        pnls = pd.Series(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        wr = len(wins) / len(pnls) * 100
        pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
        print(f"  Range<{range_mult}x Vol<{vol_mult}x: N={len(pnls)} "
              f"WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt (60min hold)")

    # Also test No Demand (bearish version)
    print("\n  --- 反向：No Demand（下降趨勢中收漲+窄幅+低量 → 做空）---")
    df5["trend_dn"] = df5["MA20"] < df5["MA20_prev"]
    df5["no_demand"] = (
        df5["trend_dn"] &
        (df5["Close"] > df5["Open"]) &
        (df5["Range"] < df5["RangeMA"] * 0.5) &
        (df5["Volume"] < df5["VolMA"] * 0.5)
    )
    df5["next_dn"] = df5["Close"].shift(-1) < df5["Open"].shift(-1)
    signals_nd = df5[df5["no_demand"] & df5["next_dn"]]
    signals_nd = signals_nd[(signals_nd.index.time >= pd.Timestamp("09:00").time()) &
                            (signals_nd.index.time <= pd.Timestamp("12:00").time())]
    n = len(signals_nd)
    if n > 0:
        pnls = []
        for idx in signals_nd.index:
            pos = df5.index.get_loc(idx)
            if pos + 13 >= len(df5):
                continue
            entry = float(df5.iloc[pos + 1]["Open"])
            future = df5.iloc[pos + 1:pos + 13]
            exit_price = float(future.iloc[-1]["Close"])
            pnls.append(entry - exit_price)  # short
        if len(pnls) > 0:
            pnls = pd.Series(pnls)
            wins = pnls[pnls > 0]
            losses = pnls[pnls < 0]
            wr = len(wins) / len(pnls) * 100
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
            print(f"  No Demand (0.5x/0.5x): N={len(pnls)} WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt")


def evaluate_e2_cmi(df):
    """E2: Choppy Market Index (CMI)。

    CMI = abs(Close - Open[n]) / (Highest - Lowest) × 100
    高 CMI = 趨勢，低 CMI = 盤整。（與 CHOP 相反！）
    """
    print("\n" + "=" * 72)
    print("E2: Choppy Market Index (CMI)")
    print("=" * 72)

    daily = df.groupby(df.index.date).agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"),
    )
    daily.index = pd.to_datetime(daily.index)

    for period in [10, 14, 20, 30]:
        net_move = abs(daily["Close"] - daily["Close"].shift(period))
        total_range = daily["High"].rolling(period).max() - daily["Low"].rolling(period).min()
        cmi = (net_move / total_range.replace(0, np.nan)) * 100
        cmi_prev = cmi.shift(1)  # no lookahead

        valid = cmi_prev.dropna()
        valid = valid[valid.index >= "2021-01-01"]

        # Split into zones
        daily_range = daily["High"] - daily["Low"]
        daily_oc = abs(daily["Close"] - daily["Open"])

        low = valid[valid < 20]    # choppy
        mid = valid[(valid >= 20) & (valid <= 60)]
        high = valid[valid > 60]   # trending

        print(f"\n  Period={period}: (N={len(valid)})")
        for label, zone in [("Choppy <20", low), ("Middle 20-60", mid), ("Trending >60", high)]:
            if len(zone) == 0:
                continue
            r = daily_range.reindex(zone.index).dropna()
            oc = daily_oc.reindex(zone.index).dropna()
            print(f"    {label:>15}: N={len(zone):>4} ({len(zone)/len(valid)*100:>5.1f}%) "
                  f"avg_range={r.mean():>5.0f}pt avg_OC={oc.mean():>4.0f}pt")


def evaluate_d1_starc(df):
    """D1: STARC 平均波幅通道。

    Upper = SMA + mult × ATR
    Lower = SMA - mult × ATR
    觸及上下限 = 超買超賣。

    測試：收盤觸及 STARC band 後次日的反轉傾向。
    """
    print("\n" + "=" * 72)
    print("D1: STARC 平均波幅通道")
    print("=" * 72)

    daily = df.groupby(df.index.date).agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"),
    )
    daily.index = pd.to_datetime(daily.index)

    tr = np.maximum(
        daily["High"] - daily["Low"],
        np.maximum(abs(daily["High"] - daily["Close"].shift(1)),
                   abs(daily["Low"] - daily["Close"].shift(1)))
    )

    for sma_period, atr_period, mult in [(6, 15, 2), (10, 14, 2), (6, 15, 1.5), (10, 10, 2)]:
        sma = daily["Close"].rolling(sma_period).mean()
        atr = tr.rolling(atr_period).mean()
        upper = sma + mult * atr
        lower = sma - mult * atr

        # Previous day values (no lookahead)
        upper_prev = upper.shift(1)
        lower_prev = lower.shift(1)

        valid = daily[upper_prev.notna() & (daily.index >= "2021-01-01")]

        # Touch upper → overbought → expect reversal down
        touch_upper = valid[valid["Close"] > upper_prev.reindex(valid.index)]
        # Touch lower → oversold → expect reversal up
        touch_lower = valid[valid["Close"] < lower_prev.reindex(valid.index)]

        # Next day return
        next_ret = daily["Close"].shift(-1) - daily["Close"]

        n_up = len(touch_upper)
        n_lo = len(touch_lower)

        if n_up > 0:
            ret_after_upper = next_ret.reindex(touch_upper.index).dropna()
            # Expect negative (reversal down)
            avg = ret_after_upper.mean()
            neg_pct = (ret_after_upper < 0).sum() / len(ret_after_upper) * 100
            print(f"  SMA{sma_period}/ATR{atr_period}/×{mult} Touch Upper: N={n_up} "
                  f"next_day_avg={avg:+.1f}pt reversal%={neg_pct:.1f}%")

        if n_lo > 0:
            ret_after_lower = next_ret.reindex(touch_lower.index).dropna()
            avg = ret_after_lower.mean()
            pos_pct = (ret_after_lower > 0).sum() / len(ret_after_lower) * 100
            print(f"  SMA{sma_period}/ATR{atr_period}/×{mult} Touch Lower: N={n_lo} "
                  f"next_day_avg={avg:+.1f}pt reversal%={pos_pct:.1f}%")


def evaluate_c3_vwmacd(df):
    """C3: VWMACD — 量加權 MACD。

    用 VWMA 取代 EMA：VWMA = Σ(Close × Volume) / Σ(Volume)
    VWMACD = VWMA(12) - VWMA(26), Signal = EMA(VWMACD, 9)

    測試：VWMACD 穿越零軸的日內延續性。
    """
    print("\n" + "=" * 72)
    print("C3: VWMACD (量加權 MACD)")
    print("=" * 72)

    # Use 5m bars
    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    cv = df5["Close"] * df5["Volume"]

    for fast, slow, sig in [(12, 26, 9), (8, 21, 5)]:
        vwma_fast = cv.rolling(fast).sum() / df5["Volume"].rolling(fast).sum()
        vwma_slow = cv.rolling(slow).sum() / df5["Volume"].rolling(slow).sum()
        vwmacd = vwma_fast - vwma_slow
        signal = vwmacd.ewm(span=sig).mean()

        # Zero-line cross: VWMACD crosses above 0
        cross_up = (vwmacd > 0) & (vwmacd.shift(1) <= 0)
        cross_dn = (vwmacd < 0) & (vwmacd.shift(1) >= 0)

        # Filter to 09:00-12:00
        cross_up = cross_up[(cross_up.index.time >= pd.Timestamp("09:00").time()) &
                            (cross_up.index.time <= pd.Timestamp("12:00").time())]
        cross_dn = cross_dn[(cross_dn.index.time >= pd.Timestamp("09:00").time()) &
                            (cross_dn.index.time <= pd.Timestamp("12:00").time())]

        # Only first cross per day
        cross_up_first = cross_up[cross_up].groupby(cross_up[cross_up].index.date).apply(
            lambda x: x.index[0] if len(x) > 0 else None
        ).dropna()
        cross_dn_first = cross_dn[cross_dn].groupby(cross_dn[cross_dn].index.date).apply(
            lambda x: x.index[0] if len(x) > 0 else None
        ).dropna()

        # Measure 60min forward
        def measure(cross_times, direction):
            pnls = []
            for ts in cross_times:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnl = (exit_p - entry) * direction
                pnls.append(pnl)
            return pd.Series(pnls) if pnls else pd.Series(dtype=float)

        pnl_up = measure(cross_up_first.values, 1)
        pnl_dn = measure(cross_dn_first.values, -1)

        for label, pnls in [("Cross Up (long)", pnl_up), ("Cross Down (short)", pnl_dn)]:
            if len(pnls) == 0:
                continue
            wins = pnls[pnls > 0]
            losses = pnls[pnls < 0]
            wr = len(wins) / len(pnls) * 100
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
            print(f"  VWMACD({fast},{slow},{sig}) {label}: N={len(pnls)} "
                  f"WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt")


def evaluate_c10_force_index(df):
    """C10: Force Index — 每根 K 棒多空力度。

    Force = (Close - Close_prev) × Volume
    EMA(Force, 13) 穿越零軸 → 趨勢轉向。
    """
    print("\n" + "=" * 72)
    print("C10: Force Index")
    print("=" * 72)

    df5 = df.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    force = (df5["Close"] - df5["Close"].shift(1)) * df5["Volume"]

    for ema_period in [2, 13]:
        fi = force.ewm(span=ema_period).mean()

        cross_up = (fi > 0) & (fi.shift(1) <= 0)
        cross_dn = (fi < 0) & (fi.shift(1) >= 0)

        cross_up = cross_up[(cross_up.index.time >= pd.Timestamp("09:00").time()) &
                            (cross_up.index.time <= pd.Timestamp("12:00").time())]
        cross_dn = cross_dn[(cross_dn.index.time >= pd.Timestamp("09:00").time()) &
                            (cross_dn.index.time <= pd.Timestamp("12:00").time())]

        # First cross per day
        for label, cross, direction in [("Up→Long", cross_up, 1), ("Dn→Short", cross_dn, -1)]:
            first = cross[cross].groupby(cross[cross].index.date).apply(
                lambda x: x.index[0] if len(x) > 0 else None
            ).dropna()

            pnls = []
            for ts in first.values:
                pos = df5.index.get_loc(ts)
                if pos + 13 >= len(df5):
                    continue
                entry = float(df5.iloc[pos + 1]["Open"])
                future = df5.iloc[pos + 1:pos + 13]
                exit_p = float(future.iloc[-1]["Close"])
                pnls.append((exit_p - entry) * direction)

            if len(pnls) == 0:
                continue
            pnls = pd.Series(pnls)
            wins = pnls[pnls > 0]
            losses = pnls[pnls < 0]
            wr = len(wins) / len(pnls) * 100
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float("inf")
            print(f"  EMA({ema_period}) {label}: N={len(pnls)} "
                  f"WR={wr:.1f}% PF={pf:.2f} AvgPnL={pnls.mean():+.1f}pt")


def main():
    print("Loading day-session 1m data...")
    df = load_day_session()
    df = df[df.index >= "2021-01-01"]
    print(f"  {len(df):,} bars, {len(set(df.index.date))} days")

    evaluate_g2(df)
    evaluate_c1_vsa(df)
    evaluate_e2_cmi(df)
    evaluate_d1_starc(df)
    evaluate_c3_vwmacd(df)
    evaluate_c10_force_index(df)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()

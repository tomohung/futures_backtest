"""
H046: Exhaustion 實盤 vs 回測比對

比較實盤主觀 exhaustion 交易 vs S003 程式化信號。
實盤來源：H044/data/live_parsed.csv (strategy=exhaustion)
回測信號：根據 S003 spec + Pine Script 邏輯從 DuckDB 重建。

Pine Script 邏輯要點：
  - 30m SMA(20) 方向：用 [1] vs [2]（前一日最後兩根 30m bar）
  - BB%B(20, open)：bands 用 [1]（排除當前 bar），測試值 = 當前 bar open
  - 夜盤 H/L：extTicker daily [1]（前一交易日含夜盤的 H/L）
  - 近二日 H/L：rawTicker daily [1] vs [2]（前二個交易日的日盤 H/L）
"""

import pandas as pd
import numpy as np
import duckdb
from pathlib import Path

DB_PATH = "data/futures.duckdb"
LIVE_CSV = "research/archive/confirmed/H044-reversal-live-vs-backtest/data/live_parsed.csv"
OUT_DIR = Path("research/active/H046-exhaustion-live-vs-backtest/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 1. Load live exhaustion trades ──────────────────────────────────────

live = pd.read_csv(LIVE_CSV)
live = live[live["strategy"] == "exhaustion"].copy()
live["date"] = pd.to_datetime(live["date"])
live["pnl"] = pd.to_numeric(live["pnl"], errors="coerce")
live["direction"] = live["direction"].map({"B": "long", "S": "short"})
live = live.sort_values("date").reset_index(drop=True)

print(f"=== 實盤 Exhaustion 交易 ===")
print(f"總筆數: {len(live)}")
print(f"有損益: {live['pnl'].notna().sum()}")
print(f"日期範圍: {live['date'].min().date()} ~ {live['date'].max().date()}")
print(f"方向分佈: long={len(live[live['direction']=='long'])}, short={len(live[live['direction']=='short'])}")
print()

# ─── 2. Build S003 signals from DuckDB ──────────────────────────────────

conn = duckdb.connect(DB_PATH, read_only=True)

# 2a. Day session daily OHLC (rawTicker equivalent)
df_daily = conn.execute("""
    SELECT timestamp::DATE AS date,
           FIRST(open ORDER BY timestamp) AS day_open,
           MAX(high) AS day_high,
           MIN(low) AS day_low,
           LAST(close ORDER BY timestamp) AS day_close,
           SUM(volume) AS day_volume
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    GROUP BY 1 ORDER BY 1
""").df()
df_daily["date"] = pd.to_datetime(df_daily["date"])

# 2b. ORB (08:45~08:57)
df_orb = conn.execute("""
    SELECT timestamp::DATE AS date,
           MAX(high) AS orb_high,
           MIN(low) AS orb_low,
           FIRST(open ORDER BY timestamp) AS orb_open
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '08:57:00'
    GROUP BY 1 ORDER BY 1
""").df()
df_orb["date"] = pd.to_datetime(df_orb["date"])
df_orb["orb_width"] = df_orb["orb_high"] - df_orb["orb_low"]
df_orb["orb_pct"] = df_orb["orb_width"] / df_orb["orb_open"] * 100

# 2c. 30m OHLC (day session) for SMA direction + BB%B(open)
# Pine Script 30m bars align to session start: 08:45-09:14, 09:15-09:44, ...
# Use offset resample to match: resample on day-session 1m data with origin at :45
df_1m_day = conn.execute("""
    SELECT timestamp, open, high, low, close, volume
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
    ORDER BY timestamp
""").df()
df_1m_day["timestamp"] = pd.to_datetime(df_1m_day["timestamp"])
df_1m_day = df_1m_day.set_index("timestamp")

# Resample to 30m with offset=15min so bins start at :45/:15
df_30m = df_1m_day.resample("30min", offset="15min").agg({
    "open": "first",
    "close": "last",
}).dropna().reset_index()
df_30m.rename(columns={"open": "open30", "close": "close30"}, inplace=True)
df_30m.rename(columns={"timestamp": "timestamp"}, inplace=True)

# SMA(20) on close — Pine uses ta.sma(close, 20)
df_30m["ma20_close"] = df_30m["close30"].rolling(20, min_periods=20).mean()

# BB bands on open — Pine uses ta.sma(open, 20)[1] and ta.stdev(open, 20)[1]
# [1] means the previous bar's values, so shift(1) to exclude current bar
df_30m["open_ma20"] = df_30m["open30"].rolling(20, min_periods=20).mean().shift(1)
df_30m["open_std20"] = df_30m["open30"].rolling(20, min_periods=20).std(ddof=1).shift(1)  # Pine ta.stdev(open,20,false) = sample stdev
df_30m["bb_upper"] = df_30m["open_ma20"] + 2 * df_30m["open_std20"]
df_30m["bb_lower"] = df_30m["open_ma20"] - 2 * df_30m["open_std20"]
# BB%B: test current bar's open against previous bar's bands
df_30m["bbpct"] = (df_30m["open30"] - df_30m["bb_lower"]) / (df_30m["bb_upper"] - df_30m["bb_lower"])

df_30m["date"] = df_30m["timestamp"].dt.normalize()

# MA direction: Pine uses [1] vs [2] — last completed bar vs one before
# = shift(1) vs shift(2) on 30m series
# For each trading day, we need the values from the LAST two 30m bars
# of the PREVIOUS day (because [1] at 08:45 = yesterday's last bar)
df_30m["ma20_shift1"] = df_30m["ma20_close"].shift(1)  # [1]
df_30m["ma20_shift2"] = df_30m["ma20_close"].shift(2)  # [2]

# Get the FIRST bar of each day — at that point [1] and [2] refer to
# the previous day's last and second-to-last bars
first_bar = df_30m.groupby("date").first().reset_index()
first_bar["ma_up"] = first_bar["ma20_shift1"] > first_bar["ma20_shift2"]
first_bar["ma_down"] = first_bar["ma20_shift1"] < first_bar["ma20_shift2"]

# 2d. Extended session daily H/L (extTicker equivalent)
# Pine: extTicker daily [1] = previous trading day's H/L including night session
# Night session 15:00~05:00 belongs to the same extended day
# So extended daily H/L = min of all bars in that calendar date (day + prev night)
# But in TradingView, extended session daily bar includes all bars for that calendar date.
# For us: extended day D = day session D + night session starting on D
df_ext = conn.execute("""
    WITH bars AS (
        SELECT
            CASE
                WHEN timestamp::TIME >= TIME '08:45:00' AND timestamp::TIME <= TIME '13:45:00'
                    THEN timestamp::DATE
                WHEN timestamp::TIME >= TIME '15:00:00'
                    THEN timestamp::DATE
                WHEN timestamp::TIME < TIME '05:01:00'
                    THEN timestamp::DATE - INTERVAL '1 day'
                ELSE NULL
            END AS ext_date,
            high, low
        FROM ohlcv_1m
        WHERE symbol = 'TX'
    )
    SELECT ext_date::DATE AS date,
           MAX(high) AS ext_high,
           MIN(low) AS ext_low
    FROM bars
    WHERE ext_date IS NOT NULL
    GROUP BY ext_date
    ORDER BY ext_date
""").df()
df_ext["date"] = pd.to_datetime(df_ext["date"])

conn.close()

# ─── 3. Build signal table ───────────────────────────────────────────────

# Merge daily + ORB
sig = df_daily.merge(df_orb[["date", "orb_high", "orb_low", "orb_width", "orb_pct"]], on="date")

# Merge 30m indicators (MA direction + BB%B at first bar of the day)
sig = sig.merge(
    first_bar[["date", "ma_up", "ma_down", "bbpct", "ma20_shift1", "ma20_shift2"]],
    on="date", how="left"
)

# Near 2-day day-session high/low — Pine: rawTicker daily [1] and [2]
# = yesterday's and day-before-yesterday's day-session H/L
sig["recent2_high"] = sig[["day_high"]].shift(1).join(sig[["day_high"]].shift(2), rsuffix="_2").max(axis=1)
sig["recent2_low"] = sig[["day_low"]].shift(1).join(sig[["day_low"]].shift(2), rsuffix="_2").min(axis=1)

# Extended daily [1] = previous extended day's H/L
sig = sig.merge(df_ext, on="date", how="left", suffixes=("", "_ext"))
sig["ext_high_prev"] = sig["ext_high"].shift(1)
sig["ext_low_prev"] = sig["ext_low"].shift(1)

# Night new high/low — Pine: ext_high_d1 > recent2_high
sig["night_new_high"] = sig["ext_high_prev"] > sig["recent2_high"]
sig["night_new_low"] = sig["ext_low_prev"] < sig["recent2_low"]

# Weekday filter
sig["weekday"] = sig["date"].dt.dayofweek  # 0=Mon, 2=Wed, 3=Thu
sig["skip_day"] = sig["weekday"].isin([2, 3])
sig["orb_pct_ok"] = sig["orb_pct"] >= 0.25

# Bull exhaustion → short: MA↑ + BB%B > 1 + night new high
sig["bull_exhaust"] = (
    sig["ma_up"].fillna(False) &
    (sig["bbpct"] > 1) &
    sig["night_new_high"].fillna(False)
)

# Bear exhaustion → long: MA↓ + BB%B < 0 + night new low
sig["bear_exhaust"] = (
    sig["ma_down"].fillna(False) &
    (sig["bbpct"] < 0) &
    sig["night_new_low"].fillna(False)
)

# Full signal (with filters)
sig["signal_short"] = sig["bull_exhaust"] & ~sig["skip_day"] & sig["orb_pct_ok"]
sig["signal_long"] = sig["bear_exhaust"] & ~sig["skip_day"] & sig["orb_pct_ok"]
sig["signal_any"] = sig["signal_short"] | sig["signal_long"]

# Raw signal (without weekday/ORB% filters)
sig["raw_signal_short"] = sig["bull_exhaust"]
sig["raw_signal_long"] = sig["bear_exhaust"]
sig["raw_signal_any"] = sig["raw_signal_short"] | sig["raw_signal_long"]

# Direction column
sig["signal_dir"] = None
sig.loc[sig["signal_long"], "signal_dir"] = "long"
sig.loc[sig["signal_short"], "signal_dir"] = "short"
sig["raw_dir"] = None
sig.loc[sig["raw_signal_long"], "raw_dir"] = "long"
sig.loc[sig["raw_signal_short"], "raw_dir"] = "short"

# ─── 4. Filter to live trading period ────────────────────────────────────

live_start = live["date"].min()
live_end = live["date"].max()
sig_period = sig[(sig["date"] >= live_start) & (sig["date"] <= live_end)].copy()

print(f"=== S003 信號（{live_start.date()} ~ {live_end.date()}）===")
print(f"交易日數: {len(sig_period)}")
print(f"Raw 信號（無濾網）: {sig_period['raw_signal_any'].sum()}")
print(f"  做多: {sig_period['raw_signal_long'].sum()}, 做空: {sig_period['raw_signal_short'].sum()}")
print(f"Filtered 信號（跳週三四 + ORB%>=0.25%）: {sig_period['signal_any'].sum()}")
print(f"  做多: {sig_period['signal_long'].sum()}, 做空: {sig_period['signal_short'].sum()}")
print()

# Sanity check: total signals in full range
sig_full = sig[sig["date"] >= "2021-01-01"]
print(f"=== Sanity check: 全期間 S003 信號 ===")
print(f"交易日: {len(sig_full)}")
print(f"Raw: {sig_full['raw_signal_any'].sum()} (long={sig_full['raw_signal_long'].sum()}, short={sig_full['raw_signal_short'].sum()})")
print(f"Filtered: {sig_full['signal_any'].sum()} (long={sig_full['signal_long'].sum()}, short={sig_full['signal_short'].sum()})")
print(f"（H036 backtest: 91 filtered trades over 2021-2026/3）")
print()

# ─── 5. Cross-match: live vs signals ─────────────────────────────────────

live_dates = set(live["date"].dt.normalize())
signal_dates = set(sig_period[sig_period["signal_any"]]["date"])
raw_signal_dates = set(sig_period[sig_period["raw_signal_any"]]["date"])

overlap_filtered = live_dates & signal_dates
overlap_raw = live_dates & raw_signal_dates
live_only = live_dates - raw_signal_dates
signal_only_filtered = signal_dates - live_dates
raw_only = raw_signal_dates - live_dates

print(f"=== 交叉比對 ===")
print(f"實盤交易日: {len(live_dates)}")
print(f"S003 filtered 信號日: {len(signal_dates)}")
print(f"S003 raw 信號日: {len(raw_signal_dates)}")
print()
print(f"重疊（filtered）: {len(overlap_filtered)} ({len(overlap_filtered)/len(live_dates)*100:.1f}% of live)")
print(f"重疊（raw）: {len(overlap_raw)} ({len(overlap_raw)/len(live_dates)*100:.1f}% of live)")
print(f"實盤獨有（程式無信號）: {len(live_only)} ({len(live_only)/len(live_dates)*100:.1f}%)")
print(f"程式獨有（filtered）: {len(signal_only_filtered)}")
print(f"程式獨有（raw）: {len(raw_only)}")
print()

# ─── 6. Detailed comparison ─────────────────────────────────────────────

print("=" * 80)
print("=== 逐筆比對：實盤 vs S003 信號 ===")
print("=" * 80)

sig_lookup = {}
for _, row in sig_period.iterrows():
    sig_lookup[row["date"]] = row

results = []
for _, trade in live.iterrows():
    d = trade["date"]
    entry = {
        "date": d.date(),
        "weekday": d.strftime("%a"),
        "live_dir": trade["direction"],
        "live_entry_time": trade["entry_time"],
        "live_entry_price": trade["entry_price"],
        "live_exit_strategy": trade["exit_strategy"],
        "live_pnl": trade["pnl"],
    }

    if d in sig_lookup:
        s = sig_lookup[d]
        entry["bbpct"] = f"{s['bbpct']:.3f}" if pd.notna(s["bbpct"]) else "NaN"
        entry["ma_up"] = bool(s["ma_up"]) if pd.notna(s["ma_up"]) else None
        entry["ma_down"] = bool(s["ma_down"]) if pd.notna(s["ma_down"]) else None
        entry["night_new_high"] = bool(s["night_new_high"]) if pd.notna(s["night_new_high"]) else None
        entry["night_new_low"] = bool(s["night_new_low"]) if pd.notna(s["night_new_low"]) else None
        entry["orb_pct"] = f"{s['orb_pct']:.3f}" if pd.notna(s["orb_pct"]) else "NaN"
        entry["skip_day"] = bool(s["skip_day"])
        entry["raw_signal"] = s["raw_dir"] if s["raw_signal_any"] else None
        entry["filtered_signal"] = s["signal_dir"] if s["signal_any"] else None

        # Why no signal?
        reasons = []
        if trade["direction"] == "short":
            # Expected bull_exhaust → short
            if not s["ma_up"]:
                reasons.append("MA not ↑")
            if pd.notna(s["bbpct"]) and s["bbpct"] <= 1:
                reasons.append(f"BB%B={s['bbpct']:.2f}≤1")
            if not s["night_new_high"]:
                reasons.append("no night new H")
        elif trade["direction"] == "long":
            # Expected bear_exhaust → long
            if not s["ma_down"]:
                reasons.append("MA not ↓")
            if pd.notna(s["bbpct"]) and s["bbpct"] >= 0:
                reasons.append(f"BB%B={s['bbpct']:.2f}≥0")
            if not s["night_new_low"]:
                reasons.append("no night new L")
        if s["skip_day"]:
            reasons.append(f"skip_{d.strftime('%a')}")
        if pd.notna(s["orb_pct"]) and s["orb_pct"] < 0.25:
            reasons.append(f"ORB%={s['orb_pct']:.2f}<0.25")
        entry["miss_reasons"] = "; ".join(reasons) if reasons else ""

        if s["signal_any"]:
            dir_match = (s["signal_dir"] == trade["direction"])
            entry["match"] = "MATCH" if dir_match else "DIR_MISMATCH"
        elif s["raw_signal_any"]:
            entry["match"] = "FILTERED_OUT"
        else:
            entry["match"] = "NO_SIGNAL"
    else:
        entry["bbpct"] = "N/A"
        entry["ma_up"] = None
        entry["ma_down"] = None
        entry["night_new_high"] = None
        entry["night_new_low"] = None
        entry["orb_pct"] = "N/A"
        entry["skip_day"] = None
        entry["raw_signal"] = None
        entry["filtered_signal"] = None
        entry["miss_reasons"] = "NO_DATA"
        entry["match"] = "NO_DATA"

    results.append(entry)

df_results = pd.DataFrame(results)

# Print summary by match type
print("\n--- Match Type 分佈 ---")
match_counts = df_results["match"].value_counts()
for mt, cnt in match_counts.items():
    pnl_sub = df_results[df_results["match"] == mt]["live_pnl"]
    avg_pnl = pnl_sub.mean()
    total_pnl = pnl_sub.sum()
    n_with_pnl = pnl_sub.notna().sum()
    avg_str = f"{avg_pnl:+.1f}" if pd.notna(avg_pnl) else "N/A"
    total_str = f"{total_pnl:+.0f}" if pd.notna(total_pnl) else "N/A"
    print(f"  {mt}: {cnt} 筆, 有損益 {n_with_pnl}, avg PnL={avg_str}, total PnL={total_str}")

# ─── 7. Detailed listing ────────────────────────────────────────────────

def fmt_pnl(v):
    return f"{v:+.0f}" if pd.notna(v) else "N/A"

def fmt_dir(v):
    return str(v) if pd.notna(v) else "?"

print("\n--- 實盤獨有（程式無信號）的交易 ---")
no_signal = df_results[df_results["match"] == "NO_SIGNAL"]
if len(no_signal) > 0:
    for _, r in no_signal.iterrows():
        print(f"  {r['date']} ({r['weekday']}) {fmt_dir(r['live_dir']):5s} "
              f"PnL={fmt_pnl(r['live_pnl']):>5s}  "
              f"miss: {r['miss_reasons']}")

print("\n--- 被濾網過濾的交易（有 raw signal 但被 filtered out）---")
filtered_out = df_results[df_results["match"] == "FILTERED_OUT"]
if len(filtered_out) > 0:
    for _, r in filtered_out.iterrows():
        print(f"  {r['date']} ({r['weekday']}) {fmt_dir(r['live_dir']):5s} "
              f"PnL={fmt_pnl(r['live_pnl']):>5s}  raw={r['raw_signal']}  "
              f"miss: {r['miss_reasons']}")

print("\n--- MATCH（方向一致）---")
matched = df_results[df_results["match"] == "MATCH"]
if len(matched) > 0:
    for _, r in matched.iterrows():
        print(f"  {r['date']} ({r['weekday']}) {fmt_dir(r['live_dir']):5s} "
              f"PnL={fmt_pnl(r['live_pnl']):>5s}  BB%B={r['bbpct']}")

print("\n--- 方向不一致 ---")
dir_mm = df_results[df_results["match"] == "DIR_MISMATCH"]
if len(dir_mm) > 0:
    for _, r in dir_mm.iterrows():
        print(f"  {r['date']} ({r['weekday']}) live={r['live_dir']} signal={r['filtered_signal']} "
              f"PnL={fmt_pnl(r['live_pnl'])}")
else:
    print("  （無）")

print("\n--- 程式有信號但實盤沒做 ---")
signal_only = sorted(signal_only_filtered)
for d in signal_only:
    s = sig_lookup.get(d)
    if s is not None:
        d_str = d.strftime("%Y-%m-%d")
        wd = d.strftime("%a")
        sdir = s["signal_dir"]
        print(f"  {d_str} ({wd}) signal={sdir}  BB%B={s['bbpct']:.3f}  ORB%={s['orb_pct']:.3f}")

# ─── 8. Miss reason statistics ──────────────────────────────────────────

print("\n" + "=" * 80)
print("=== NO_SIGNAL 原因統計 ===")
print("=" * 80)

no_sig_with_reasons = df_results[df_results["match"] == "NO_SIGNAL"]
reason_counts = {}
for _, r in no_sig_with_reasons.iterrows():
    for reason in r["miss_reasons"].split("; "):
        if reason:
            key = reason.split("=")[0] if "=" in reason else reason
            reason_counts[key] = reason_counts.get(key, 0) + 1

for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {count}/{len(no_sig_with_reasons)} ({count/len(no_sig_with_reasons)*100:.0f}%)")

# ─── 9. Summary stats comparison ────────────────────────────────────────

print("\n" + "=" * 80)
print("=== 績效比較 ===")
print("=" * 80)

live_with_pnl = live[live["pnl"].notna()]

print(f"\n--- 實盤全部（有損益）---")
print(f"  N={len(live_with_pnl)}, 勝率={len(live_with_pnl[live_with_pnl['pnl']>0])/len(live_with_pnl)*100:.1f}%")
print(f"  平均損益={live_with_pnl['pnl'].mean():+.1f}pt, 總損益={live_with_pnl['pnl'].sum():+.0f}pt")
losers = live_with_pnl[live_with_pnl['pnl'] < 0]['pnl'].sum()
winners = live_with_pnl[live_with_pnl['pnl'] > 0]['pnl'].sum()
print(f"  PF={winners / abs(losers):.2f}" if losers != 0 else "  PF=∞")

for d in ["long", "short"]:
    sub = live_with_pnl[live_with_pnl["direction"] == d]
    if len(sub) > 0:
        wr = len(sub[sub["pnl"] > 0]) / len(sub) * 100
        print(f"  {d}: N={len(sub)}, 勝率={wr:.1f}%, avg={sub['pnl'].mean():+.1f}pt")

print(f"\n--- 只看 MATCH（雙方一致）---")
if len(matched) > 0:
    m_pnl = matched["live_pnl"].dropna()
    if len(m_pnl) > 0:
        print(f"  N={len(m_pnl)}, 勝率={len(m_pnl[m_pnl>0])/len(m_pnl)*100:.1f}%")
        print(f"  平均損益={m_pnl.mean():+.1f}pt, 總損益={m_pnl.sum():+.0f}pt")

print(f"\n--- 只看 NO_SIGNAL（實盤有但程式無信號）---")
if len(no_signal) > 0:
    ns_pnl = no_signal["live_pnl"].dropna()
    if len(ns_pnl) > 0:
        print(f"  N={len(ns_pnl)}, 勝率={len(ns_pnl[ns_pnl>0])/len(ns_pnl)*100:.1f}%")
        print(f"  平均損益={ns_pnl.mean():+.1f}pt, 總損益={ns_pnl.sum():+.0f}pt")

print(f"\n--- 只看 FILTERED_OUT ---")
if len(filtered_out) > 0:
    fo_pnl = filtered_out["live_pnl"].dropna()
    if len(fo_pnl) > 0:
        print(f"  N={len(fo_pnl)}, 勝率={len(fo_pnl[fo_pnl>0])/len(fo_pnl)*100:.1f}%")
        print(f"  平均損益={fo_pnl.mean():+.1f}pt, 總損益={fo_pnl.sum():+.0f}pt")

# ─── 10. Weekday analysis ───────────────────────────────────────────────

print(f"\n--- 實盤交易 weekday 分佈 ---")
live["weekday"] = live["date"].dt.day_name()
wd_stats = live.groupby("weekday").agg(
    N=("pnl", "size"),
    wins=("pnl", lambda x: (x > 0).sum()),
    avg_pnl=("pnl", "mean"),
    total_pnl=("pnl", "sum"),
).reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
for wd, row in wd_stats.iterrows():
    wr = row["wins"] / row["N"] * 100 if row["N"] > 0 else 0
    print(f"  {wd:10s}: N={row['N']:2.0f}, 勝率={wr:5.1f}%, avg={row['avg_pnl']:+6.1f}pt, total={row['total_pnl']:+7.0f}pt")

# ─── 11. Exit strategy comparison ───────────────────────────────────────

print(f"\n--- 實盤出場策略分佈 ---")
exit_stats = live[live["pnl"].notna()].groupby("exit_strategy").agg(
    N=("pnl", "size"),
    avg_pnl=("pnl", "mean"),
    total_pnl=("pnl", "sum"),
)
for es, row in exit_stats.iterrows():
    print(f"  {es}: N={row['N']:.0f}, avg={row['avg_pnl']:+.1f}pt, total={row['total_pnl']:+.0f}pt")

# ─── 12. Save results ───────────────────────────────────────────────────

df_results.to_csv(OUT_DIR / "comparison.csv", index=False)
print(f"\n結果已存至 {OUT_DIR / 'comparison.csv'}")

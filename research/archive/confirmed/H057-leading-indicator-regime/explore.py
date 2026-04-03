"""
H057 Leading Indicator Regime — Phase 1 Distribution Exploration

分析國發會領先指標不含趨勢指數的拐點與 TAIEX 後續報酬的關係。
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

plt.rcParams["font.family"] = ["Arial Unicode MS", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(__file__).parent
OUTPUT = BASE / "results"
OUTPUT.mkdir(exist_ok=True)


# ── 1. Load & Prepare Data ──────────────────────────────────────────────

df = pd.read_csv(BASE / "data" / "leading_indicator.csv")

# Parse date (YYYY/M) → first day of that month
df["date"] = pd.to_datetime(df["date"], format="%Y/%m")
df["pub_date"] = pd.to_datetime(df["last_working_day"], format="%Y/%m/%d")

# Sort ascending by date
df = df.sort_values("date").reset_index(drop=True)

print(f"=== Data Overview ===")
print(f"Range: {df['date'].min():%Y/%m} ~ {df['date'].max():%Y/%m} ({len(df)} months)")
print(f"Leading Index: {df['leading_index'].min():.2f} ~ {df['leading_index'].max():.2f}")
print(f"TAIEX: {df['taiex'].min():.0f} ~ {df['taiex'].max():.0f}")
print()

# ── 2. Identify Turning Points ──────────────────────────────────────────

# Direction: +1 if index rising, -1 if falling, 0 if flat
df["direction"] = np.sign(df["leading_index"].diff())

# Turning point = direction changes
df["prev_direction"] = df["direction"].shift(1)
df["is_turning"] = (df["direction"] != df["prev_direction"]) & df["prev_direction"].notna() & (df["direction"] != 0)
df["turn_type"] = None
df.loc[df["is_turning"] & (df["direction"] > 0), "turn_type"] = "bottom"  # 從下降轉上升 = 底部
df.loc[df["is_turning"] & (df["direction"] < 0), "turn_type"] = "top"     # 從上升轉下降 = 頂部

turns = df[df["is_turning"]].copy()
print(f"=== Turning Points ===")
print(f"Total: {len(turns)} (Top: {(turns['turn_type']=='top').sum()}, Bottom: {(turns['turn_type']=='bottom').sum()})")
print()

for _, row in turns.iterrows():
    print(f"  {row['date']:%Y/%m}  {row['turn_type']:6s}  index={row['leading_index']:.2f}  "
          f"pub={row['pub_date']:%Y/%m/%d}  TAIEX={row['taiex']:.0f}")
print()


# ── 3. Forward Returns After Turning Points ─────────────────────────────

# Calculate forward returns for TAIEX (using publication date prices)
# The publication date is already T+1 month delayed
# "可操作報酬" = from pub_date TAIEX to pub_date+N months TAIEX

def calc_forward_returns(df, turns, months_ahead_list=[1, 3, 6]):
    """Calculate TAIEX forward returns from the publication date of the turning point."""
    results = []
    for idx, turn_row in turns.iterrows():
        pub_idx = df.index.get_loc(idx)
        for n in months_ahead_list:
            fwd_idx = pub_idx + n
            if fwd_idx < len(df):
                fwd_taiex = df.iloc[fwd_idx]["taiex"]
                base_taiex = turn_row["taiex"]  # TAIEX at publication date
                ret_pct = (fwd_taiex - base_taiex) / base_taiex * 100
                results.append({
                    "date": turn_row["date"],
                    "turn_type": turn_row["turn_type"],
                    "pub_date": turn_row["pub_date"],
                    "base_taiex": base_taiex,
                    "fwd_months": n,
                    "fwd_taiex": fwd_taiex,
                    "return_pct": ret_pct,
                })
    return pd.DataFrame(results)

fwd_df = calc_forward_returns(df, turns)

print("=== Forward Returns After Turning Points (from publication date) ===")
print("Note: Returns measured from TAIEX on publication date (already T+1 delayed)")
print()

for turn_type in ["bottom", "top"]:
    print(f"--- {turn_type.upper()} turns ---")
    subset = fwd_df[fwd_df["turn_type"] == turn_type]
    for n in [1, 3, 6]:
        s = subset[subset["fwd_months"] == n]["return_pct"]
        if len(s) > 0:
            expected_dir = "positive" if turn_type == "bottom" else "negative"
            hit_rate = (s > 0).mean() * 100 if turn_type == "bottom" else (s < 0).mean() * 100
            print(f"  +{n}M: mean={s.mean():+.2f}%  median={s.median():+.2f}%  "
                  f"std={s.std():.2f}%  N={len(s)}  "
                  f"hit_rate({expected_dir})={hit_rate:.0f}%")
    print()


# ── 4. Consecutive N Months Confirmation ────────────────────────────────

print("=== Consecutive N Months Confirmation ===")
print("Only count turning point if direction persists for N consecutive months after the turn")
print()

def find_confirmed_turns(df, n_confirm=1):
    """Find turning points where direction persists for N months after."""
    confirmed = []
    for idx in range(1, len(df) - n_confirm):
        row = df.iloc[idx]
        if not row["is_turning"]:
            continue
        direction = row["direction"]
        # Check if next n_confirm months maintain same direction
        persist = True
        for k in range(1, n_confirm + 1):
            if idx + k >= len(df):
                persist = False
                break
            next_dir = df.iloc[idx + k]["direction"]
            if next_dir != direction:
                persist = False
                break
        if persist:
            # The signal is available only after N months of confirmation
            # Signal date = the month when confirmation completes
            confirm_idx = idx + n_confirm
            if confirm_idx < len(df):
                confirmed.append({
                    "turn_date": row["date"],
                    "turn_type": row["turn_type"],
                    "confirm_date": df.iloc[confirm_idx]["date"],
                    "confirm_pub_date": df.iloc[confirm_idx]["pub_date"],
                    "confirm_taiex": df.iloc[confirm_idx]["taiex"],
                    "confirm_idx": confirm_idx,
                })
    return pd.DataFrame(confirmed)

for n in [1, 2, 3]:
    confirmed = find_confirmed_turns(df, n_confirm=n)
    if len(confirmed) == 0:
        print(f"  N={n}: No confirmed turns")
        continue

    print(f"  N={n}: {len(confirmed)} confirmed turns "
          f"(Top: {(confirmed['turn_type']=='top').sum()}, "
          f"Bottom: {(confirmed['turn_type']=='bottom').sum()})")

    # Forward returns from confirmation date
    for turn_type in ["bottom", "top"]:
        sub = confirmed[confirmed["turn_type"] == turn_type]
        for fwd_m in [1, 3, 6]:
            rets = []
            for _, c_row in sub.iterrows():
                fwd_idx = c_row["confirm_idx"] + fwd_m
                if fwd_idx < len(df):
                    fwd_taiex = df.iloc[fwd_idx]["taiex"]
                    ret = (fwd_taiex - c_row["confirm_taiex"]) / c_row["confirm_taiex"] * 100
                    rets.append(ret)
            if rets:
                rets = np.array(rets)
                expected_dir = "pos" if turn_type == "bottom" else "neg"
                hit = np.mean(rets > 0) * 100 if turn_type == "bottom" else np.mean(rets < 0) * 100
                print(f"    {turn_type:6s} +{fwd_m}M: mean={np.mean(rets):+.2f}%  "
                      f"N={len(rets)}  hit({expected_dir})={hit:.0f}%")
    print()


# ── 5. Technical Indicator Filters ──────────────────────────────────────

print("=== Technical Indicator Exploration ===")
print()

# 5a. Monthly SMA crossover
for sma_period in [6, 12]:
    df[f"sma_{sma_period}"] = df["taiex"].rolling(sma_period).mean()

df["above_sma6"] = df["taiex"] > df["sma_6"]
df["above_sma12"] = df["taiex"] > df["sma_12"]

# 5b. Monthly RSI
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

df["rsi_14"] = calc_rsi(df["taiex"], 14)
df["rsi_6"] = calc_rsi(df["taiex"], 6)

# 5c. Monthly MACD
ema12 = df["taiex"].ewm(span=12, adjust=False).mean()
ema26 = df["taiex"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_signal"]

# Analyze: turning point + technical filter
print("--- Bottom Turns + Technical Filters ---")
bottom_turns = turns[turns["turn_type"] == "bottom"]

for filter_name, filter_col, filter_val in [
    ("TAIEX > SMA6", "above_sma6", True),
    ("TAIEX > SMA12", "above_sma12", True),
    ("TAIEX < SMA6 (oversold zone)", "above_sma6", False),
    ("MACD hist > 0", "macd_hist", "positive"),
]:
    matched_indices = []
    for idx, row in bottom_turns.iterrows():
        if filter_col in df.columns:
            val = df.loc[idx, filter_col]
            if filter_val == "positive":
                if val > 0:
                    matched_indices.append(idx)
            elif val == filter_val:
                matched_indices.append(idx)

    if not matched_indices:
        print(f"  {filter_name}: 0 matches")
        continue

    rets_3m = []
    for idx in matched_indices:
        loc = df.index.get_loc(idx)
        if loc + 3 < len(df):
            base = df.loc[idx, "taiex"]
            fwd = df.iloc[loc + 3]["taiex"]
            rets_3m.append((fwd - base) / base * 100)

    if rets_3m:
        rets_3m = np.array(rets_3m)
        print(f"  {filter_name}: N={len(rets_3m)}  mean_3M={np.mean(rets_3m):+.2f}%  "
              f"hit(pos)={np.mean(rets_3m > 0)*100:.0f}%")

print()
print("--- Top Turns + Technical Filters ---")
top_turns = turns[turns["turn_type"] == "top"]

for filter_name, filter_col, filter_val in [
    ("TAIEX < SMA6", "above_sma6", False),
    ("TAIEX < SMA12", "above_sma12", False),
    ("TAIEX > SMA6 (overbought zone)", "above_sma6", True),
    ("MACD hist < 0", "macd_hist", "negative"),
]:
    matched_indices = []
    for idx, row in top_turns.iterrows():
        if filter_col in df.columns:
            val = df.loc[idx, filter_col]
            if filter_val == "negative":
                if val < 0:
                    matched_indices.append(idx)
            elif val == filter_val:
                matched_indices.append(idx)

    if not matched_indices:
        print(f"  {filter_name}: 0 matches")
        continue

    rets_3m = []
    for idx in matched_indices:
        loc = df.index.get_loc(idx)
        if loc + 3 < len(df):
            base = df.loc[idx, "taiex"]
            fwd = df.iloc[loc + 3]["taiex"]
            rets_3m.append((fwd - base) / base * 100)

    if rets_3m:
        rets_3m = np.array(rets_3m)
        print(f"  {filter_name}: N={len(rets_3m)}  mean_3M={np.mean(rets_3m):+.2f}%  "
              f"hit(neg)={np.mean(rets_3m < 0)*100:.0f}%")

print()


# ── 6. Visualization ────────────────────────────────────────────────────

fig, axes = plt.subplots(3, 1, figsize=(14, 12))

# 6a. Leading Index + Turning Points
ax1 = axes[0]
ax1.plot(df["date"], df["leading_index"], "b-", linewidth=1.5, label="Leading Index")
bottoms = turns[turns["turn_type"] == "bottom"]
tops = turns[turns["turn_type"] == "top"]
ax1.scatter(bottoms["date"], bottoms["leading_index"], c="red", marker="^", s=100, zorder=5, label="Bottom turn")
ax1.scatter(tops["date"], tops["leading_index"], c="green", marker="v", s=100, zorder=5, label="Top turn")
ax1.set_ylabel("Leading Index (excl. trend)")
ax1.set_title("H057: Leading Indicator vs TAIEX")
ax1.legend(loc="upper left")
ax1.grid(True, alpha=0.3)

# 6b. TAIEX
ax2 = axes[1]
ax2.plot(df["date"], df["taiex"], "k-", linewidth=1.5, label="TAIEX")
ax2.plot(df["date"], df["sma_6"], "orange", linewidth=1, alpha=0.7, label="SMA6")
ax2.plot(df["date"], df["sma_12"], "purple", linewidth=1, alpha=0.7, label="SMA12")

# Mark turning points on TAIEX
for _, row in bottoms.iterrows():
    ax2.axvline(row["pub_date"], color="red", alpha=0.3, linestyle="--")
for _, row in tops.iterrows():
    ax2.axvline(row["pub_date"], color="green", alpha=0.3, linestyle="--")

ax2.set_ylabel("TAIEX")
ax2.legend(loc="upper left")
ax2.grid(True, alpha=0.3)

# 6c. Forward 3M returns distribution
ax3 = axes[2]
bottom_rets = fwd_df[(fwd_df["turn_type"] == "bottom") & (fwd_df["fwd_months"] == 3)]["return_pct"]
top_rets = fwd_df[(fwd_df["turn_type"] == "top") & (fwd_df["fwd_months"] == 3)]["return_pct"]

bins = np.linspace(-30, 30, 25)
if len(bottom_rets) > 0:
    ax3.hist(bottom_rets, bins=bins, alpha=0.6, color="red", label=f"After Bottom (N={len(bottom_rets)})")
if len(top_rets) > 0:
    ax3.hist(top_rets, bins=bins, alpha=0.6, color="green", label=f"After Top (N={len(top_rets)})")
ax3.axvline(0, color="black", linestyle="--", alpha=0.5)
ax3.set_xlabel("3-Month Forward Return (%)")
ax3.set_ylabel("Count")
ax3.set_title("Forward 3M Return Distribution by Turn Type")
ax3.legend()
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_overview.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {OUTPUT / 'h057_overview.png'}")


# ── 7. Detailed Turn-by-Turn Table ──────────────────────────────────────

print()
print("=== Detailed Turn-by-Turn Analysis ===")
print(f"{'Date':>8s}  {'Type':>6s}  {'Index':>6s}  {'PubDate':>10s}  {'TAIEX':>8s}  "
      f"{'Ret+1M':>7s}  {'Ret+3M':>7s}  {'Ret+6M':>7s}")
print("-" * 80)

for _, turn_row in turns.iterrows():
    rets = {}
    for n in [1, 3, 6]:
        r = fwd_df[(fwd_df["date"] == turn_row["date"]) & (fwd_df["fwd_months"] == n)]
        rets[n] = f"{r['return_pct'].iloc[0]:+.1f}%" if len(r) > 0 else "N/A"

    print(f"{turn_row['date']:%Y/%m}  {turn_row['turn_type']:>6s}  "
          f"{turn_row['leading_index']:6.2f}  {turn_row['pub_date']:%Y/%m/%d}  "
          f"{turn_row['taiex']:8.0f}  {rets[1]:>7s}  {rets[3]:>7s}  {rets[6]:>7s}")

print()
print("=== Summary Statistics ===")
print()
for turn_type in ["bottom", "top"]:
    print(f"--- {turn_type.upper()} ---")
    for n in [1, 3, 6]:
        s = fwd_df[(fwd_df["turn_type"] == turn_type) & (fwd_df["fwd_months"] == n)]["return_pct"]
        if len(s) > 0:
            from scipy import stats
            t_stat, p_val = stats.ttest_1samp(s, 0)
            print(f"  +{n}M: mean={s.mean():+.2f}% median={s.median():+.2f}% "
                  f"std={s.std():.2f}% N={len(s)} t={t_stat:.2f} p={p_val:.3f}")
    print()

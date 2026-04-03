"""
H060 Weekday Volatility Pattern — Phase 1 Distribution Exploration
分析台指期不同星期幾的振幅差異
"""
import duckdb
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.size'] = 11
plt.rcParams['figure.figsize'] = (14, 8)

OUTPUT_DIR = "research/active/H060-weekday-volatility/results"

conn = duckdb.connect("data/futures.duckdb", read_only=True)

# =============================================================================
# 1. 計算每日三種振幅：日盤 H-L、夜盤 H-L、全日盤 H-L
# =============================================================================
print("=" * 60)
print("Step 1: 計算每日振幅")
print("=" * 60)

# 日盤振幅 (08:45 ~ 13:45)
day_range = conn.execute("""
    SELECT
        timestamp::DATE AS trade_date,
        MIN(low) AS day_low,
        MAX(high) AS day_high,
        MAX(high) - MIN(low) AS day_range,
        FIRST(open ORDER BY timestamp) AS day_open,
        LAST(close ORDER BY timestamp) AS day_close
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
    GROUP BY timestamp::DATE
    ORDER BY trade_date
""").df()

# 夜盤振幅 (15:00 ~ 05:00 隔日)
# 夜盤歸屬以下一個日盤交易日為準
# 先建立日盤交易日清單，然後將夜盤 map 到下一個交易日
day_dates = sorted(day_range['trade_date'].unique())
day_dates_set = set(day_dates)

night_raw = conn.execute("""
    SELECT
        timestamp,
        high, low,
        timestamp::DATE AS cal_date,
        timestamp::TIME AS cal_time
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
    ORDER BY timestamp
""").df()

# 計算夜盤所屬交易日：往後找最近的日盤交易日
import bisect
day_dates_list = sorted([pd.Timestamp(d) for d in day_dates])

def find_next_trade_date(ts):
    cal_time = ts.time()
    if cal_time >= pd.Timestamp('15:00').time():
        # 15:00 之後，找隔天起的第一個交易日
        search_date = (ts + pd.Timedelta(days=1)).normalize()
    else:
        # 00:00~05:00，找當天起的第一個交易日
        search_date = ts.normalize()
    idx = bisect.bisect_left(day_dates_list, search_date)
    if idx < len(day_dates_list):
        return day_dates_list[idx]
    return None

night_raw['belongs_to_date'] = night_raw['timestamp'].apply(find_next_trade_date)
night_raw = night_raw.dropna(subset=['belongs_to_date'])

night_range = night_raw.groupby('belongs_to_date').agg(
    night_low=('low', 'min'),
    night_high=('high', 'max'),
).reset_index()
night_range['night_range'] = night_range['night_high'] - night_range['night_low']
night_range = night_range.rename(columns={'belongs_to_date': 'trade_date'})

# 全日盤 = 夜盤 + 日盤
# 用同樣的 find_next_trade_date 邏輯
full_raw = conn.execute("""
    SELECT
        timestamp,
        high, low,
        timestamp::TIME AS cal_time
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '13:45')
    ORDER BY timestamp
""").df()

def assign_trade_date(ts):
    cal_time = ts.time()
    if cal_time >= pd.Timestamp('15:00').time():
        return find_next_trade_date(ts)
    elif cal_time < pd.Timestamp('05:00').time():
        return find_next_trade_date(ts)
    else:
        # 日盤時段 08:45~13:45
        dt = ts.normalize()
        if dt in day_dates_set or pd.Timestamp(dt) in day_dates_set:
            return dt
        return find_next_trade_date(ts)

full_raw['belongs_to_date'] = full_raw['timestamp'].apply(assign_trade_date)
full_raw = full_raw.dropna(subset=['belongs_to_date'])

full_range = full_raw.groupby('belongs_to_date').agg(
    full_low=('low', 'min'),
    full_high=('high', 'max'),
).reset_index()
full_range['full_range'] = full_range['full_high'] - full_range['full_low']
full_range = full_range.rename(columns={'belongs_to_date': 'trade_date'})

# Merge
df = day_range[['trade_date', 'day_range', 'day_close']].merge(
    night_range[['trade_date', 'night_range']], on='trade_date', how='inner'
).merge(
    full_range[['trade_date', 'full_range']], on='trade_date', how='inner'
)

df['trade_date'] = pd.to_datetime(df['trade_date'])
df['weekday'] = df['trade_date'].dt.dayofweek  # 0=Mon
df['weekday_name'] = df['trade_date'].dt.strftime('%a')
df['year'] = df['trade_date'].dt.year

# 計算 EMA(20) 用於標準化
df['day_range_ema20'] = df['day_range'].ewm(span=20).mean()
df['day_range_norm'] = df['day_range'] / df['day_range_ema20']
df['night_range_ema20'] = df['night_range'].ewm(span=20).mean()
df['night_range_norm'] = df['night_range'] / df['night_range_ema20']
df['full_range_ema20'] = df['full_range'].ewm(span=20).mean()
df['full_range_norm'] = df['full_range'] / df['full_range_ema20']

# 結算日偵測（每月第三個週三）
def is_settlement(dt):
    if dt.weekday() != 2:  # Wednesday
        return False
    day = dt.day
    # Third Wednesday: day is between 15 and 21
    return 15 <= day <= 21

df['is_settlement'] = df['trade_date'].apply(is_settlement)

print(f"總樣本數: {len(df)}")
print(f"日期範圍: {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
print(f"結算日數: {df['is_settlement'].sum()}")
print(f"\n每星期樣本數:")
print(df.groupby('weekday_name')['trade_date'].count().reindex(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']))

# =============================================================================
# 2. Box plot 比較
# =============================================================================
print("\n" + "=" * 60)
print("Step 2: Box Plot 比較")
print("=" * 60)

weekday_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

fig, axes = plt.subplots(2, 3, figsize=(18, 10))

for idx, (col, title) in enumerate([
    ('day_range', '日盤振幅 (points)'),
    ('night_range', '夜盤振幅 (points)'),
    ('full_range', '全日盤振幅 (points)'),
    ('day_range_norm', '日盤振幅 / EMA(20)'),
    ('night_range_norm', '夜盤振幅 / EMA(20)'),
    ('full_range_norm', '全日盤振幅 / EMA(20)'),
]):
    ax = axes[idx // 3, idx % 3]
    data = [df[df['weekday_name'] == d][col].dropna().values for d in weekday_order]
    bp = ax.boxplot(data, labels=weekday_order, patch_artist=True)
    colors = ['#ff9999', '#ffcc99', '#99ccff', '#99ff99', '#cc99ff']
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
    medians = [np.median(d) for d in data]
    for i, med in enumerate(medians):
        ax.text(i + 1, med, f'{med:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

plt.suptitle('H060: Weekday Volatility Distribution', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/weekday_boxplot.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved: weekday_boxplot.png")

# =============================================================================
# 3. Kruskal-Wallis 檢定
# =============================================================================
print("\n" + "=" * 60)
print("Step 3: Kruskal-Wallis 檢定")
print("=" * 60)

for col, label in [
    ('day_range', '日盤振幅'),
    ('night_range', '夜盤振幅'),
    ('full_range', '全日盤振幅'),
    ('day_range_norm', '日盤振幅(標準化)'),
    ('night_range_norm', '夜盤振幅(標準化)'),
    ('full_range_norm', '全日盤振幅(標準化)'),
]:
    groups = [df[df['weekday'] == d][col].dropna().values for d in range(5)]
    stat, p = stats.kruskal(*groups)
    print(f"  {label}: H={stat:.2f}, p={p:.4f} {'***' if p < 0.01 else '**' if p < 0.05 else '*' if p < 0.1 else 'ns'}")

# Pairwise Mann-Whitney for significant ones
print("\n--- Pairwise Mann-Whitney U (日盤振幅) ---")
for i in range(5):
    for j in range(i+1, 5):
        g1 = df[df['weekday'] == i]['day_range'].dropna()
        g2 = df[df['weekday'] == j]['day_range'].dropna()
        stat, p = stats.mannwhitneyu(g1, g2, alternative='two-sided')
        if p < 0.05:
            ratio = g1.median() / g2.median()
            print(f"  {weekday_order[i]} vs {weekday_order[j]}: p={p:.4f}, median ratio={ratio:.3f}")

# =============================================================================
# 4. 逐年穩定性分析
# =============================================================================
print("\n" + "=" * 60)
print("Step 4: 逐年穩定性分析")
print("=" * 60)

# Heat map: year × weekday × median range
years = sorted(df['year'].unique())
pivot_raw = df.pivot_table(values='day_range', index='year', columns='weekday_name',
                           aggfunc='median').reindex(columns=weekday_order)
pivot_norm = df.pivot_table(values='day_range_norm', index='year', columns='weekday_name',
                            aggfunc='median').reindex(columns=weekday_order)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

im1 = axes[0].imshow(pivot_raw.values, cmap='YlOrRd', aspect='auto')
axes[0].set_xticks(range(5)); axes[0].set_xticklabels(weekday_order)
axes[0].set_yticks(range(len(years))); axes[0].set_yticklabels(years)
for i in range(len(years)):
    for j in range(5):
        v = pivot_raw.values[i, j]
        axes[0].text(j, i, f'{v:.0f}', ha='center', va='center', fontsize=9)
axes[0].set_title('日盤振幅中位數 (points)')
plt.colorbar(im1, ax=axes[0])

im2 = axes[1].imshow(pivot_norm.values, cmap='YlOrRd', aspect='auto')
axes[1].set_xticks(range(5)); axes[1].set_xticklabels(weekday_order)
axes[1].set_yticks(range(len(years))); axes[1].set_yticklabels(years)
for i in range(len(years)):
    for j in range(5):
        v = pivot_norm.values[i, j]
        axes[1].text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=9)
axes[1].set_title('日盤振幅 / EMA(20) 中位數')
plt.colorbar(im2, ax=axes[1])

plt.suptitle('H060: Yearly Weekday Volatility Stability', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/yearly_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved: yearly_heatmap.png")

# Print yearly stability
print("\n日盤振幅中位數 (points):")
print(pivot_raw.to_string())
print("\n日盤振幅 / EMA(20) 中位數:")
print(pivot_norm.round(3).to_string())

# Check consistency: which weekday is max/min each year
print("\n--- 每年最大/最小振幅的星期 ---")
for year in years:
    row = pivot_norm.loc[year]
    print(f"  {year}: 最大={row.idxmax()} ({row.max():.3f}), 最小={row.idxmin()} ({row.min():.3f})")

# =============================================================================
# 5. 排除結算日後重跑
# =============================================================================
print("\n" + "=" * 60)
print("Step 5: 排除結算日後重跑")
print("=" * 60)

df_nosettl = df[~df['is_settlement']].copy()
print(f"排除結算日後樣本數: {len(df_nosettl)} (移除 {df['is_settlement'].sum()} 筆)")

print("\n--- Kruskal-Wallis (排除結算日) ---")
for col, label in [
    ('day_range', '日盤振幅'),
    ('day_range_norm', '日盤振幅(標準化)'),
    ('night_range_norm', '夜盤振幅(標準化)'),
]:
    groups = [df_nosettl[df_nosettl['weekday'] == d][col].dropna().values for d in range(5)]
    stat, p = stats.kruskal(*groups)
    print(f"  {label}: H={stat:.2f}, p={p:.4f} {'***' if p < 0.01 else '**' if p < 0.05 else '*' if p < 0.1 else 'ns'}")

# Median comparison: all vs no-settlement for Wed
for col, label in [('day_range', '日盤'), ('day_range_norm', '日盤(標準化)')]:
    wed_all = df[df['weekday'] == 2][col].median()
    wed_nosettl = df_nosettl[df_nosettl['weekday'] == 2][col].median()
    print(f"\n  {label} Wed 中位數: 全部={wed_all:.1f}, 排除結算={wed_nosettl:.1f}, 差異={((wed_nosettl/wed_all)-1)*100:.1f}%")

# =============================================================================
# 6. 標準化分析（已在前面計算，這裡做 summary table）
# =============================================================================
print("\n" + "=" * 60)
print("Step 6: 標準化振幅 Summary")
print("=" * 60)

summary = df.groupby('weekday_name').agg(
    N=('day_range', 'count'),
    day_med=('day_range', 'median'),
    day_mean=('day_range', 'mean'),
    day_norm_med=('day_range_norm', 'median'),
    night_norm_med=('night_range_norm', 'median'),
    full_norm_med=('full_range_norm', 'median'),
).reindex(weekday_order)

# Add relative to overall median
overall_day_norm_med = df['day_range_norm'].median()
summary['day_norm_vs_all'] = summary['day_norm_med'] / overall_day_norm_med

print(summary.round(3).to_string())

# Effect size: max/min ratio
max_day = summary['day_norm_med'].max()
min_day = summary['day_norm_med'].min()
print(f"\n日盤標準化振幅: 最大/最小 = {max_day:.3f} / {min_day:.3f} = {max_day/min_day:.3f} ({(max_day/min_day-1)*100:.1f}%)")

max_night = summary['night_norm_med'].max()
min_night = summary['night_norm_med'].min()
print(f"夜盤標準化振幅: 最大/最小 = {max_night:.3f} / {min_night:.3f} = {max_night/min_night:.3f} ({(max_night/min_night-1)*100:.1f}%)")

# =============================================================================
# Summary plot
# =============================================================================
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

for ax, (col, title) in zip(axes, [
    ('day_range_norm', '日盤振幅 / EMA(20)'),
    ('night_range_norm', '夜盤振幅 / EMA(20)'),
    ('full_range_norm', '全日盤振幅 / EMA(20)'),
]):
    medians = df.groupby('weekday_name')[col].median().reindex(weekday_order)
    q25 = df.groupby('weekday_name')[col].quantile(0.25).reindex(weekday_order)
    q75 = df.groupby('weekday_name')[col].quantile(0.75).reindex(weekday_order)

    colors = ['#e74c3c' if m > 1.0 else '#27ae60' for m in medians]
    ax.bar(weekday_order, medians, color=colors, alpha=0.7, edgecolor='black')
    ax.errorbar(weekday_order, medians, yerr=[medians - q25, q75 - medians],
                fmt='none', color='black', capsize=5)
    ax.axhline(1.0, color='gray', linestyle='--', alpha=0.5)
    ax.set_title(title)
    ax.set_ylabel('Normalized Range')
    for i, (d, m) in enumerate(zip(weekday_order, medians)):
        ax.text(i, m + 0.01, f'{m:.3f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

plt.suptitle('H060: Weekday Normalized Volatility', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/weekday_summary.png', dpi=150, bbox_inches='tight')
plt.close()
print("\nSaved: weekday_summary.png")

conn.close()
print("\n✅ Phase 1 exploration complete!")

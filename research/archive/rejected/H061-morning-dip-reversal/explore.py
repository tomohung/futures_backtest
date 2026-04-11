"""
H061 - Morning Dip Reversal: Phase 1 Distribution Research
探索台指期日盤 9:15~10:45 下殺後反彈的模式

分析項目：
1. 日盤低點出現時間分佈（15 分鐘 bin）
2. 9:15~10:45 區間低點佔比
3. 下殺定義與分類（單次 vs 二次探底）
4. 低點後反彈幅度分佈
5. 按盤勢類型分群比較
"""

import duckdb
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = ['Arial Unicode MS', 'Heiti TC']

# ── 載入日盤 1 分 K ──
with duckdb.connect("data/futures.duckdb", read_only=True) as conn:
    df = conn.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND timestamp::TIME >= '08:46'
          AND timestamp::TIME <= '13:45'
        ORDER BY timestamp
    """).fetchdf()

df['date'] = df['timestamp'].dt.date
df['time'] = df['timestamp'].dt.time
print(f"日盤 1 分 K 總筆數: {len(df)}")
print(f"日期範圍: {df['date'].min()} ~ {df['date'].max()}")

# ── 1. 日盤低點時間分佈 ──
print("\n" + "=" * 60)
print("1. 日盤低點出現時間分佈")
print("=" * 60)

daily_stats = []
for date, grp in df.groupby('date'):
    if len(grp) < 200:  # 至少 200 根 1 分 K 才算完整交易日
        continue

    low_idx = grp['low'].idxmin()
    low_row = grp.loc[low_idx]
    high_idx = grp['high'].idxmax()
    high_row = grp.loc[high_idx]

    day_open = grp.iloc[0]['open']
    day_high = grp['high'].max()
    day_low = grp['low'].min()
    day_close = grp.iloc[-1]['close']
    day_range = day_high - day_low

    # 低點出現時間
    low_time = low_row['timestamp']
    low_hour_min = low_time.hour * 60 + low_time.minute

    # 高點出現時間
    high_time = high_row['timestamp']
    high_hour_min = high_time.hour * 60 + high_time.minute

    # 低點後的反彈
    after_low = grp[grp['timestamp'] > low_time]
    rebound_30 = after_low[after_low['timestamp'] <= low_time + pd.Timedelta(minutes=30)]['high'].max() - day_low if len(after_low) > 0 else 0
    rebound_60 = after_low[after_low['timestamp'] <= low_time + pd.Timedelta(minutes=60)]['high'].max() - day_low if len(after_low) > 0 else 0
    rebound_90 = after_low[after_low['timestamp'] <= low_time + pd.Timedelta(minutes=90)]['high'].max() - day_low if len(after_low) > 0 else 0
    rebound_eod = day_close - day_low

    # 盤勢分類：趨勢日 vs 震盪日
    # 用 close 相對 open 的方向和幅度
    direction = 'up' if day_close > day_open else 'down'
    body_ratio = abs(day_close - day_open) / day_range if day_range > 0 else 0
    is_trend_day = body_ratio > 0.5  # 實體超過全距 50% 為趨勢日

    daily_stats.append({
        'date': date,
        'day_open': day_open,
        'day_high': day_high,
        'day_low': day_low,
        'day_close': day_close,
        'day_range': day_range,
        'low_time': low_time,
        'low_hour_min': low_hour_min,
        'high_time': high_time,
        'high_hour_min': high_hour_min,
        'high_before_low': high_hour_min < low_hour_min,
        'rebound_30': rebound_30,
        'rebound_60': rebound_60,
        'rebound_90': rebound_90,
        'rebound_eod': rebound_eod,
        'direction': direction,
        'body_ratio': body_ratio,
        'is_trend_day': is_trend_day,
    })

stats = pd.DataFrame(daily_stats)
total_days = len(stats)
print(f"完整交易日數: {total_days}")

# 低點時間分佈（15 分鐘 bin）
bins_15m = list(range(8 * 60 + 45, 13 * 60 + 46, 15))
bin_labels = [f"{m // 60:02d}:{m % 60:02d}" for m in bins_15m[:-1]]
stats['low_bin'] = pd.cut(stats['low_hour_min'], bins=bins_15m, labels=bin_labels, right=False)

low_dist = stats['low_bin'].value_counts().sort_index()
low_pct = (low_dist / total_days * 100).round(1)

print("\n低點出現時間分佈（15 分鐘 bin）:")
for label, count in low_dist.items():
    pct = low_pct[label]
    bar = '█' * int(pct)
    print(f"  {label}  {count:4d} ({pct:5.1f}%) {bar}")

# ── 2. 9:15~10:45 區間分析 ──
print("\n" + "=" * 60)
print("2. 9:15~10:45 區間低點分析")
print("=" * 60)

morning_window = stats[(stats['low_hour_min'] >= 9 * 60 + 15) & (stats['low_hour_min'] <= 10 * 60 + 45)]
morning_pct = len(morning_window) / total_days * 100

# 更細的時段
early_930 = stats[(stats['low_hour_min'] >= 9 * 60 + 15) & (stats['low_hour_min'] < 9 * 60 + 45)]
mid_1000 = stats[(stats['low_hour_min'] >= 9 * 60 + 45) & (stats['low_hour_min'] < 10 * 60 + 15)]
late_1030 = stats[(stats['low_hour_min'] >= 10 * 60 + 15) & (stats['low_hour_min'] <= 10 * 60 + 45)]

print(f"日盤低點在 9:15~10:45 的天數: {len(morning_window)} / {total_days} ({morning_pct:.1f}%)")
print(f"  9:15~9:45:  {len(early_930):4d} ({len(early_930)/total_days*100:.1f}%)")
print(f"  9:45~10:15: {len(mid_1000):4d} ({len(mid_1000)/total_days*100:.1f}%)")
print(f"  10:15~10:45:{len(late_1030):4d} ({len(late_1030)/total_days*100:.1f}%)")
print(f"  其他時段:   {total_days - len(morning_window):4d} ({(1 - morning_pct/100)*100:.1f}%)")

# 預期值（均勻分佈下，9:15~10:45 = 90 分鐘 / 300 分鐘 ≈ 30%）
expected_pct = 90 / 300 * 100
print(f"\n均勻分佈預期: {expected_pct:.1f}%")
print(f"實際 vs 預期: {morning_pct:.1f}% vs {expected_pct:.1f}% (差異 {morning_pct - expected_pct:+.1f}%)")

# ── 3. 下殺定義與 dip 分類 ──
print("\n" + "=" * 60)
print("3. 下殺模式分類（單次 vs 二次探底）")
print("=" * 60)

# 重新掃描每日的 intraday 走勢，找出 dip 模式
dip_analysis = []

for date, grp in df.groupby('date'):
    if len(grp) < 200:
        continue

    prices = grp[['timestamp', 'high', 'low', 'close', 'volume']].reset_index(drop=True)
    day_low = prices['low'].min()
    day_high = prices['high'].max()
    day_range = day_high - day_low
    if day_range == 0:
        continue

    # 只看 8:46~11:00 的走勢（morning session）
    morning = prices[prices['timestamp'].dt.time <= pd.Timestamp('11:00').time()].copy()
    if len(morning) < 60:
        continue

    morning_low = morning['low'].min()
    morning_low_idx = morning['low'].idxmin()
    morning_low_time = morning.loc[morning_low_idx, 'timestamp']
    morning_low_min = morning_low_time.hour * 60 + morning_low_time.minute

    # 只分析低點在 9:00~11:00 的情況（排除開盤第一根就是低點）
    if morning_low_min < 9 * 60:
        continue

    # 找出開盤到低點之間的最高點（前波高點）
    before_low = morning[morning['timestamp'] < morning_low_time]
    if len(before_low) == 0:
        continue
    pre_high = before_low['high'].max()
    pre_high_idx = before_low['high'].idxmax()
    pre_high_time = before_low.loc[pre_high_idx, 'timestamp']

    # 下殺幅度
    dip_size = pre_high - morning_low

    # 分析是否有二次探底
    # 定義：低點前有一次 >= 50% 深度的 dip，反彈後再跌破或接近
    # 用 rolling min/max 找 swing points
    after_pre_high = morning[morning['timestamp'] > pre_high_time].copy()
    if len(after_pre_high) < 10:
        continue

    # 找第一次 dip（前波高點後的第一個低谷）
    cummin = after_pre_high['low'].cummin()
    # 找到 cummin 停止下降的點（第一次反彈開始）
    first_dip_end = None
    first_dip_low = after_pre_high['low'].iloc[0]
    rebound_started = False

    for i in range(1, len(after_pre_high)):
        curr_low = after_pre_high['low'].iloc[i]
        if curr_low < first_dip_low:
            first_dip_low = curr_low
            first_dip_idx = i
            rebound_started = False
        elif curr_low > first_dip_low + dip_size * 0.15:  # 反彈 > 15% of dip
            if not rebound_started:
                first_dip_end = i
                rebound_started = True

    if first_dip_end is None:
        # 一路跌到底，沒有反彈 → 單純下殺，不是 dip-reversal
        dip_type = 'no_rebound'
        first_rebound_size = 0
        second_dip_low = np.nan
        time_between_dips = 0
    else:
        first_dip_time = after_pre_high['timestamp'].iloc[first_dip_end]

        # 找第一次反彈的高點
        after_first_dip = after_pre_high.iloc[first_dip_end:]
        rebound_high = after_first_dip['high'].iloc[0]
        rebound_high_idx = 0
        for i in range(1, min(len(after_first_dip), 60)):
            if after_first_dip['high'].iloc[i] > rebound_high:
                rebound_high = after_first_dip['high'].iloc[i]
                rebound_high_idx = i
            # 如果從反彈高點又跌了一段，停止找
            if after_first_dip['low'].iloc[i] < rebound_high - dip_size * 0.3:
                break

        first_rebound_size = rebound_high - first_dip_low
        first_rebound_ratio = first_rebound_size / dip_size if dip_size > 0 else 0

        # 檢查反彈後是否有第二次下殺
        after_rebound = after_first_dip.iloc[rebound_high_idx:]
        if len(after_rebound) > 5:
            second_low = after_rebound['low'].min()
            second_low_idx = after_rebound['low'].idxmin()
            second_low_time = after_rebound.loc[second_low_idx, 'timestamp']

            # 二次探底條件：第二次低點接近或低於第一次低點
            if second_low <= first_dip_low + dip_size * 0.1:  # 在第一次低點 ±10% 以內
                dip_type = 'double_dip'
                second_dip_low = second_low
                time_between_dips = (second_low_time - after_pre_high['timestamp'].iloc[first_dip_end]).total_seconds() / 60
            else:
                dip_type = 'single_dip'
                second_dip_low = np.nan
                time_between_dips = 0
        else:
            dip_type = 'single_dip'
            second_dip_low = np.nan
            time_between_dips = 0

    # 低點後反彈（用整日低點）
    after_morning_low = morning[morning['timestamp'] > morning_low_time]
    reb_30 = after_morning_low[after_morning_low['timestamp'] <= morning_low_time + pd.Timedelta(minutes=30)]['high'].max() - morning_low if len(after_morning_low) > 0 else 0
    reb_60 = after_morning_low[after_morning_low['timestamp'] <= morning_low_time + pd.Timedelta(minutes=60)]['high'].max() - morning_low if len(after_morning_low) > 0 else 0

    # 到收盤的反彈
    all_day = df[df['date'] == date]
    eod_close = all_day.iloc[-1]['close']
    reb_eod = eod_close - morning_low

    dip_analysis.append({
        'date': date,
        'morning_low': morning_low,
        'morning_low_min': morning_low_min,
        'pre_high': pre_high,
        'dip_size': dip_size,
        'dip_type': dip_type,
        'first_rebound_size': first_rebound_size,
        'first_rebound_ratio': first_rebound_size / dip_size if dip_size > 0 else 0,
        'second_dip_low': second_dip_low,
        'time_between_dips': time_between_dips,
        'rebound_30': reb_30,
        'rebound_60': reb_60,
        'rebound_eod': reb_eod,
        'day_range': day_range,
        'dip_pct_of_range': dip_size / day_range * 100 if day_range > 0 else 0,
    })

dips = pd.DataFrame(dip_analysis)
print(f"分析天數（低點在 9:00~11:00 且有前波高點）: {len(dips)}")

# Dip 類型分佈
type_counts = dips['dip_type'].value_counts()
print(f"\nDip 類型分佈:")
for t, c in type_counts.items():
    print(f"  {t:15s}: {c:4d} ({c/len(dips)*100:.1f}%)")

# ── 4. 反彈幅度分佈 ──
print("\n" + "=" * 60)
print("4. 低點後反彈幅度分佈")
print("=" * 60)

for dip_type in ['single_dip', 'double_dip']:
    subset = dips[dips['dip_type'] == dip_type]
    if len(subset) == 0:
        continue
    print(f"\n【{dip_type}】(N={len(subset)})")
    for col, label in [('rebound_30', '30 分鐘'), ('rebound_60', '60 分鐘'), ('rebound_eod', '到收盤')]:
        vals = subset[col].dropna()
        if len(vals) == 0:
            continue
        print(f"  {label} 反彈: mean={vals.mean():.0f}, median={vals.median():.0f}, "
              f"std={vals.std():.0f}, win_rate={( vals > 0).mean()*100:.1f}%")

    # 下殺幅度統計
    print(f"  下殺幅度: mean={subset['dip_size'].mean():.0f}, median={subset['dip_size'].median():.0f}")

# ── 5. 二次探底特徵分析 ──
print("\n" + "=" * 60)
print("5. 二次探底（double dip）特徵分析")
print("=" * 60)

double = dips[dips['dip_type'] == 'double_dip']
single = dips[dips['dip_type'] == 'single_dip']

if len(double) > 0:
    print(f"\n二次探底 (N={len(double)}):")
    print(f"  兩次 dip 間隔: mean={double['time_between_dips'].mean():.0f} min, "
          f"median={double['time_between_dips'].median():.0f} min")
    print(f"  第一次反彈比例 (rebound/dip): mean={double['first_rebound_ratio'].mean():.2f}, "
          f"median={double['first_rebound_ratio'].median():.2f}")
    print(f"  下殺幅度: mean={double['dip_size'].mean():.0f}, median={double['dip_size'].median():.0f}")

if len(single) > 0:
    print(f"\n單次探底 (N={len(single)}):")
    print(f"  第一次反彈比例 (rebound/dip): mean={single['first_rebound_ratio'].mean():.2f}, "
          f"median={single['first_rebound_ratio'].median():.2f}")
    print(f"  下殺幅度: mean={single['dip_size'].mean():.0f}, median={single['dip_size'].median():.0f}")

if len(double) > 0 and len(single) > 0:
    print(f"\n【區分特徵比較】")
    print(f"  第一次反彈比例: single={single['first_rebound_ratio'].median():.2f} "
          f"vs double={double['first_rebound_ratio'].median():.2f}")
    print(f"  下殺幅度: single={single['dip_size'].median():.0f} "
          f"vs double={double['dip_size'].median():.0f}")
    print(f"  下殺佔日振幅%: single={single['dip_pct_of_range'].median():.1f}% "
          f"vs double={double['dip_pct_of_range'].median():.1f}%")

# ── 6. 盤勢分群 ──
print("\n" + "=" * 60)
print("6. 按盤勢分群（趨勢日 vs 震盪日）")
print("=" * 60)

# 合併盤勢資訊
dips_merged = dips.merge(stats[['date', 'direction', 'is_trend_day', 'body_ratio']], on='date', how='left')

for trend, label in [(True, '趨勢日'), (False, '震盪日')]:
    sub = dips_merged[dips_merged['is_trend_day'] == trend]
    if len(sub) == 0:
        continue
    print(f"\n【{label}】(N={len(sub)})")
    type_c = sub['dip_type'].value_counts()
    for t, c in type_c.items():
        print(f"  {t}: {c} ({c/len(sub)*100:.1f}%)")
    print(f"  反彈到收盤: mean={sub['rebound_eod'].mean():.0f}, median={sub['rebound_eod'].median():.0f}, "
          f"win_rate={(sub['rebound_eod'] > 0).mean()*100:.1f}%")

# 按方向細分
for direction in ['up', 'down']:
    sub = dips_merged[dips_merged['direction'] == direction]
    print(f"\n【{direction} day】(N={len(sub)})")
    print(f"  反彈到收盤: mean={sub['rebound_eod'].mean():.0f}, median={sub['rebound_eod'].median():.0f}, "
          f"win_rate={(sub['rebound_eod'] > 0).mean()*100:.1f}%")

# ── 7. 低點時間 by dip_type ──
print("\n" + "=" * 60)
print("7. 低點出現時間 by dip type")
print("=" * 60)

for dip_type in ['single_dip', 'double_dip', 'no_rebound']:
    subset = dips[dips['dip_type'] == dip_type]
    if len(subset) == 0:
        continue
    in_window = subset[(subset['morning_low_min'] >= 9*60+15) & (subset['morning_low_min'] <= 10*60+45)]
    print(f"  {dip_type:15s}: 低點在 9:15~10:45 = {len(in_window)}/{len(subset)} ({len(in_window)/len(subset)*100:.1f}%)")

# ── 視覺化 ──
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('H061: Morning Dip Reversal - Phase 1 Distribution', fontsize=14, fontweight='bold')

# 1. 日盤低點時間分佈
ax = axes[0, 0]
low_dist.plot(kind='bar', ax=ax, color='steelblue', alpha=0.8)
ax.set_title('Day Session Low Time Distribution (15min bins)')
ax.set_xlabel('Time')
ax.set_ylabel('Count')
ax.axvspan(1.5, 7.5, alpha=0.15, color='red', label='9:15~10:45')
ax.legend()
ax.tick_params(axis='x', rotation=45)

# 2. 反彈幅度箱形圖
ax = axes[0, 1]
box_data = []
box_labels = []
for dt in ['single_dip', 'double_dip']:
    sub = dips[dips['dip_type'] == dt]['rebound_60'].dropna()
    if len(sub) > 0:
        box_data.append(sub.values)
        box_labels.append(f'{dt}\n(N={len(sub)})')
bp = ax.boxplot(box_data, labels=box_labels, patch_artist=True)
colors = ['#4CAF50', '#FF9800']
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.6)
ax.set_title('60-min Rebound After Low (by dip type)')
ax.set_ylabel('Rebound (points)')
ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

# 3. Dip type 比例
ax = axes[1, 0]
type_counts.plot(kind='bar', ax=ax, color=['#4CAF50', '#FF9800', '#F44336'], alpha=0.8)
ax.set_title('Dip Type Distribution')
ax.set_ylabel('Count')
ax.tick_params(axis='x', rotation=0)

# 4. 反彈到收盤 by direction
ax = axes[1, 1]
for direction, color, label in [('up', '#D32F2F', 'Up Day'), ('down', '#388E3C', 'Down Day')]:
    sub = dips_merged[dips_merged['direction'] == direction]['rebound_eod'].dropna()
    ax.hist(sub, bins=30, alpha=0.5, color=color, label=f'{label} (N={len(sub)})')
ax.set_title('Rebound to EOD (by day direction)')
ax.set_xlabel('Rebound (points)')
ax.set_ylabel('Count')
ax.axvline(x=0, color='gray', linestyle='--', alpha=0.5)
ax.legend()

plt.tight_layout()
plt.savefig('research/active/H061-morning-dip-reversal/distribution_charts.png', dpi=150, bbox_inches='tight')
print("\n圖表已存: research/active/H061-morning-dip-reversal/distribution_charts.png")

# ── 年度趨勢 ──
print("\n" + "=" * 60)
print("8. 年度趨勢")
print("=" * 60)

dips['year'] = pd.to_datetime(dips['date']).dt.year
for year in sorted(dips['year'].unique()):
    sub = dips[dips['year'] == year]
    in_window = sub[(sub['morning_low_min'] >= 9*60+15) & (sub['morning_low_min'] <= 10*60+45)]
    double_cnt = (sub['dip_type'] == 'double_dip').sum()
    print(f"  {year}: N={len(sub):3d}, "
          f"低點在窗口={len(in_window):3d} ({len(in_window)/len(sub)*100:.1f}%), "
          f"double_dip={double_cnt:3d} ({double_cnt/len(sub)*100:.1f}%)")

print("\n=== Phase 1 探索完成 ===")

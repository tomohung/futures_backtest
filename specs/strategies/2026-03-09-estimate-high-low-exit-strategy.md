下面是預估振幅 pinescript 的程式碼
請截取其中的算法，轉成 backtesting.py 之後可以使用的離場策略

策略的精神如下:
1. 每15分鐘生出一個預估振幅
2  每個15分鐘都有一個比重，可以換算成預估當天的可能振幅
3  每15分鐘產生的滿足區價位，取一個最可能達到的價位當作當天的目標價。譬如8:45-8:59 的15分鐘算出來的上方滿足區是31000，9:00-9:14的15分鐘算出來是31100，目前價位是30500，則取31000是滿足區價位
4  進場後，如果行情走到滿足區後，再跌破1分k5ma則出場。
5  以上為做多的舉例，做空則邏輯相反

---

## 演算法說明（Python 實作）

### 每日 EMA 熱身（從歷史資料）
- `ema_volume`：已完成交易日成交量的 EMA(20)，以第一個完成日初始化
- `ema_hl_regular`：已完成交易日（session_high - session_low）的 EMA(20)
- 每日收盤後更新，供**次日**使用；第一個交易日無法計算（欄位為 NaN）

### 15 分鐘時間比重
```python
TIME_FACTORS = {
    time(8,45):0.089, time(9,0):0.114, time(9,15):0.077, time(9,30):0.073,
    time(9,45):0.061, time(10,0):0.055, time(10,15):0.046, time(10,30):0.042,
    time(10,45):0.038, time(11,0):0.036, time(11,15):0.031, time(11,30):0.030,
    time(11,45):0.027, time(12,0):0.028, time(12,15):0.026, time(12,30):0.030,
    time(12,45):0.031, time(13,0):0.040, time(13,15):0.052, time(13,30):0.075,
}
```
各 slot 比重之和 ≈ 1.0，代表當日成交量在各 15 分鐘的典型分佈比例。

### 每個 slot 的預估振幅（在 slot 邊界更新，廣播到下一個 slot）
- `estimated_volume = cum_vol / cum_factor`（截至上一個 slot 結束的累計量）
- `estimated_hl = estimated_volume / ema_volume * ema_hl_regular`
- 加權平均（negative_weight=1.414，低估時懲罰更大）：
  - slot 1（count=1）：avg = est_hl（初始化）
  - slot 2（count=1）：avg = (prev_avg + est_hl) / 2（等權）
  - slot 3+：若 `est_hl < avg`：`adj = est_hl - (avg - est_hl) × 1.414`，否則 `adj = est_hl`
    `avg = (avg × (count-1) + adj) / count`
- **延遲一個 slot**：slot N 結束後的計算結果廣播到 slot N+1 的所有 1 分 K，防止 lookahead

### 滿足區計算
- `sat_zone_upper = session_low + avg - ema_hl / 8`
- `sat_zone_lower = session_high - avg + ema_hl / 8`
- `session_high / session_low`：當日截至上一個 slot 結束的最高/最低價

---

## Python 實作規格

### 元件 1：`src/backtest/estimate_hl.py`（純計算模組）

```python
def compute_estimate_hl_zones(df: pd.DataFrame, ema_period: int = 20) -> pd.DataFrame:
    """
    輸入：完整日盤 1 分 K DataFrame（未過濾日期，確保 EMA 熱身）
    輸出：同 df 加入新欄位：
      EmaVol, EmaHL, EstHL,
      SatZoneUpper, SatZoneLower, EstHighLevel, EstLowLevel
    """

def debug_day(df: pd.DataFrame, date: str) -> None:
    """印出指定日期的逐 slot 中間值，用於驗證"""
```

### 元件 2：`src/backtest/runner.py`（整合）
在 `load_data_with_night_ma()` 加入 `estimate_hl: bool = False` 參數。
在日期過濾**之前**呼叫 `compute_estimate_hl_zones(df_day)`，確保 EMA 熱身不被截斷。

### 元件 3：`src/strategies/estimate_hl_exit.py`（共用離場 Mixin）

```python
class EstimateHLExitMixin:
    def _init_estimate_hl_exit(self): ...      # 在 init() 呼叫
    def _reset_estimate_hl_exit(self): ...     # 在每日 reset 呼叫（由 _record_bar 自動觸發）
    def _record_bar(self): ...                  # 每根 K 棒呼叫一次：記錄收盤、收集 zone 值
    def _update_long_target(self): ...         # 更新多方目標價（未觸及時動態選擇）
    def _update_short_target(self): ...        # 更新空方目標價
    def _check_long_exit(self) -> bool: ...    # Phase 1/2 多方離場判斷
    def _check_short_exit(self) -> bool: ...   # Phase 1/2 空方離場判斷
```

狀態變數：
- `_hl_zone_touched: bool` — 是否已觸及目標區
- `_close_buffer: deque[float]` — 最近 5 根 1 分 K 收盤（maxlen=5）
- `_target_upper / _target_lower: float | None` — 選定目標價
- `_day_sat_zone_uppers / _day_sat_zone_lowers: set[float]` — 當日已出現的所有 zone 值

離場規則：
- **目標選擇（多方）**：當日所有已出現的 SatZoneUpper 中，取最低且高於當前 close 的一個
- **Phase 1（多方）**：等待 High >= target_upper（觸及滿足區）
- **Phase 2（多方）**：觸及後，close < 5MA 則出場
- 做空邏輯相反

---

## 實測統計結果（2021-01 ~ 2026-03，共 1251 個交易日）

### SatZone 觸及率

| 類型 | 天數 | 比例 |
|------|-----:|-----:|
| 觸及上方 SatZoneUpper | 795 | 63% |
| 觸及下方 SatZoneLower | 501 | 40% |
| 至少觸及一邊 | 1037 | 83% |
| **完全未觸及（兩邊都沒到）** | **427** | **34%** |
| **大幅突破（超出 SatZone > 100 點）** | **181** | **14%** |

### 各類型日子的特徵

| 指標 | 完全未觸及 | 正常觸及 | 大幅突破 |
|------|:---------:|:-------:|:-------:|
| HL_ratio 中位數（實際振幅 / EmaHL） | 0.72 | 1.00 | 1.58 |
| Vol_ratio 中位數（成交量 / EmaVol） | 0.94 | 0.96 | 1.13 |
| OR_pct 中位數（開盤區間 / EmaHL）   | 0.30 | 0.27 | 0.31 |

### 關鍵結論

- **完全未觸及** = 縮量盤整日，振幅本來就小，非演算法失準。OR 與量均無法在開盤時預判。
  → 詳見 `specs/strategies/estimate-hl-no-touch-days.md`
- **大幅突破** = 放量趨勢爆發日，EMA(20) 反應慢導致 SatZone 設太近，提早出場損失後段行情。
  → 詳見 `specs/strategies/estimate-hl-breakout-days.md`
- **正常觸及（52%）** = SatZone 演算法表現良好的核心應用場景。

---

## 驗證計劃

### Step A：`estimate_hl.py` 單元驗證 ✅
- `EmaVol` 範圍 143k–384k，`EmaHL` 範圍 108–456 點，符合預期
- `SatZoneUpper` 只在 15 分鐘邊界改變，延遲一個 slot 廣播正確
- `debug_day()` 可列出逐 slot 中間值，便於與 TradingView 比對

### Step B：runner.py 整合驗證 ✅
- `load_data_with_night_ma(estimate_hl=True)` 正常回傳 7 個新欄位
- 日期過濾前執行，EMA 熱身不被截斷

### Step C：Mixin 端對端驗收 ⏳
建立使用 EstimateHLExitMixin 的測試策略，對已知趨勢日回測，確認離場點合理。

---

## 邊界條件
- `EmaVol == 0`：guard 避免除以零，SatZone 維持 NaN
- 無有效目標（所有 zone 已低於當前價）：`_check_long_exit()` 回傳 False，由策略自行強制出場
- 觸及 zone 後不足 5 根 K 棒：`_ma5()` 回傳 None，繼續持倉
- 第一天資料（NaN zones）：zone sets 為空，`_check_*_exit()` 回傳 False

---

## 原始 PineScript（參考）

```pinescript
//@version=6
indicator("Daily Volume from 15min Accumulation with EMA", shorttitle="DV15+EMA", overlay=true)

// Input parameter for EMA period
ema_period = input.int(20, title="EMA Period", minval=1, maxval=200)

// Get 15-minute volume data
fifteen_volume = request.security(syminfo.tickerid, "15", volume)

// Input for custom ticker id (optional)
custom_ticker = input.string("", title="Custom Ticker ID (leave blank for current)")


// Get 15-minute volume data for the selected ticker
fifteen_volume_custom = custom_ticker != "" ? request.security(custom_ticker, "15", volume) : 0.0

// Accumulate 15-minute volumes to build daily totals
var float current_day_volume = 0.0
var float completed_daily_volume = 0.0

// When new session starts, save previous day's total and start fresh
if session.isfirstbar_regular
    completed_daily_volume := current_day_volume  // Save completed day
    current_day_volume := fifteen_volume          // Start new day
else
    current_day_volume += fifteen_volume          // Add to current day

// Calculate EMA of completed daily volumes (built from 15min accumulation)
// Manual EMA calculation that updates only once per day
var float ema_volume = na
var bool ema_initialized = false

// Only update EMA when we have a new day (when completed_daily_volume gets updated)

if session.isfirstbar_regular and not na(completed_daily_volume)
    if not ema_initialized
        ema_volume := completed_daily_volume  // Initialize with first value
        ema_initialized := true
    else
        // EMA formula: EMA = (Close * (2 / (Period + 1))) + (Previous EMA * (1 - (2 / (Period + 1))))
        smoothing_factor = 2.0 / (ema_period + 1)
        ema_volume := (completed_daily_volume * smoothing_factor) + (ema_volume * (1 - smoothing_factor))

// Calculate offset for 1 day shift based on current timeframe
daily_bars = 20

// Plot current day accumulated volume as histogram (長條圖)
// plot(current_day_volume, title="Current Day Volume (Live)", style=plot.style_histogram, color=color.new(color.blue, 20), linewidth=4)

// Plot completed daily volume as histogram (built from 15min accumulation)
// plot(completed_daily_volume, title="Completed Daily Volume", style=plot.style_histogram, color=color.new(color.gray, 50), offset=-daily_bars)

// Plot EMA as line chart (折線圖)
// plot(ema_volume, title="EMA Volume", style=plot.style_line, color=color.red, linewidth=2, offset=-daily_bars)

// Estimated Volume

// Input parameters for time-based amplification factors
factor_0845 = input.float(0.089, title="8:45 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_0900 = input.float(0.114, title="9:00 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_0915 = input.float(0.077, title="9:15 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_0930 = input.float(0.073, title="9:30 Factor", minval=0.001, maxval=2.0, step=0.001)

factor_0945 = input.float(0.061, title="9:45 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1000 = input.float(0.055, title="10:00 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1015 = input.float(0.046, title="10:15 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1030 = input.float(0.042, title="10:30 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1045 = input.float(0.038, title="10:45 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1100 = input.float(0.036, title="11:00 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1115 = input.float(0.031, title="11:15 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1130 = input.float(0.030, title="11:30 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1145 = input.float(0.027, title="11:45 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1200 = input.float(0.028, title="12:00 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1215 = input.float(0.026, title="12:15 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1230 = input.float(0.030, title="12:30 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1245 = input.float(0.031, title="12:45 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1300 = input.float(0.040, title="13:00 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1315 = input.float(0.052, title="13:15 Factor", minval=0.001, maxval=2.0, step=0.001)
factor_1330 = input.float(0.075, title="13:30 Factor", minval=0.001, maxval=2.0, step=0.001)


// Function to get current time factor based on time
getCurrentTimeFactor() =>
    current_time = hour * 100 + minute

    factor = switch
        current_time >= 845 and current_time < 900 => factor_0845
        current_time >= 900 and current_time < 915 => factor_0900
        current_time >= 915 and current_time < 930 => factor_0915
        current_time >= 930 and current_time < 945 => factor_0930
        current_time >= 945 and current_time < 1000 => factor_0945
        current_time >= 1000 and current_time < 1015 => factor_1000
        current_time >= 1015 and current_time < 1030 => factor_1015
        current_time >= 1030 and current_time < 1045 => factor_1030
        current_time >= 1045 and current_time < 1100 => factor_1045
        current_time >= 1100 and current_time < 1115 => factor_1100
        current_time >= 1115 and current_time < 1130 => factor_1115
        current_time >= 1130 and current_time < 1145 => factor_1130
        current_time >= 1145 and current_time < 1200 => factor_1145
        current_time >= 1200 and current_time < 1215 => factor_1200
        current_time >= 1215 and current_time < 1230 => factor_1215
        current_time >= 1230 and current_time < 1245 => factor_1230
        current_time >= 1245 and current_time < 1300 => factor_1245
        current_time >= 1300 and current_time < 1315 => factor_1300
        current_time >= 1315 and current_time < 1330 => factor_1315
        current_time >= 1330 and current_time < 1345 => factor_1330
        => 0.001  // Default for times before 8:45

    factor

// Calculate accumulated volume for the current day (only during 8:45-13:45)
var float accumulated_volume = na
var float accumulated_factors = na

current_factor = getCurrentTimeFactor()

// Reset on new day or when session starts

current_time = hour * 100 + minute
if current_time >= 845 and current_time < 1345
    is_third_wednesday = (dayofweek == dayofweek.wednesday) and (dayofmonth >= 15) and (dayofmonth <= 21)
    accumulated_volume := volume + (is_third_wednesday ? fifteen_volume_custom : 0)
    accumulated_factors := current_factor

// Add current bar's volume and factor only during session
if current_time >=1345
    is_third_wednesday = (dayofweek == dayofweek.wednesday) and (dayofmonth >= 15) and (dayofmonth <= 21)

    accumulated_volume := nz(accumulated_volume, 0.0) + volume + (is_third_wednesday ? fifteen_volume_custom : 0)
    accumulated_factors := nz(accumulated_factors, 0.0) + current_factor


// Calculate estimated volume using accumulated factors
// Logic: sum of factors represents total expected percentage by current time
estimated_volume = accumulated_factors > 0 ? accumulated_volume / accumulated_factors : na

// Plot the results
// plot(estimated_volume, title="Estimated Volume", color=color.orange, linewidth=2, style = plot.style_circles)

// Calculate EMA of daily High-Low range

// Track regular session high and low
var float session_high = na
var float session_low = na
var float completed_daily_high_low = na

// When new session starts, save previous day's range and start fresh
if session.isfirstbar_regular
    if not na(session_high) and not na(session_low)
        completed_daily_high_low := session_high - session_low  // Save completed day's range
    session_high := high          // Start new day
    session_low := low
else
    session_high := math.max(nz(session_high, high), high)    // Track session high
    session_low := math.min(nz(session_low, low), low)        // Track session low

// Calculate EMA of completed daily high-low ranges (regular session only)
var float ema_high_low_regular = na
var bool ema_hl_initialized = false

// Only update EMA when we have a new day (when completed_daily_high_low gets updated)
if session.isfirstbar_regular and not na(completed_daily_high_low)
    if not ema_hl_initialized
        ema_high_low_regular := completed_daily_high_low  // Initialize with first value
        ema_hl_initialized := true
    else
        // EMA formula: EMA = (Close * (2 / (Period + 1))) + (Previous EMA * (1 - (2 / (Period + 1))))
        smoothing_factor = 2.0 / (ema_period + 1)
        ema_high_low_regular := (completed_daily_high_low * smoothing_factor) + (ema_high_low_regular * (1 - smoothing_factor))

// Plot EMA of regular session high-low range
// plot(ema_high_low_regular, title="EMA High-Low Range (Regular Session)", color=color.green, linewidth=2, style=plot.style_line, offset=-daily_bars)

// Plot current session high-low range
current_high_low = not na(session_high) and not na(session_low) ? session_high - session_low : na
// plot(current_high_low, title="Current Session High-Low Range", color=color.purple, linewidth=2, style=plot.style_line)

// Calculate estimated high-low range
estimated_high_low = estimated_volume / ema_volume * ema_high_low_regular

// Plot estimated high-low average

var float estimated_high_low_average = na
var int estimated_high_low_count = 0
var float adjusted_estimated_high_low = na
var negative_weight = 1.414

if session.isfirstbar_regular
    estimated_high_low_average := estimated_high_low
    estimated_high_low_count := 1

if not session.isfirstbar_regular
    if estimated_high_low_count <= 1
        // For the 2nd bar, use raw value so bar 1 and 2 have equal weight
        adjusted_estimated_high_low := estimated_high_low
    else
        if estimated_high_low < estimated_high_low_average
            adjusted_estimated_high_low := estimated_high_low - (estimated_high_low_average - estimated_high_low) * negative_weight
        else
            adjusted_estimated_high_low := estimated_high_low


    estimated_high_low_count := nz(estimated_high_low_count, 0) + 1
    estimated_high_low_average := (estimated_high_low_average * (estimated_high_low_count - 1) + adjusted_estimated_high_low) / estimated_high_low_count


// Plot estimated levels based on current session high/low
estimated_high_level = session_low + estimated_high_low_average
estimated_low_level = session_high - estimated_high_low_average
potential_high_level = session_low + estimated_high_low_average * 0.618
potential_low_level = session_high - estimated_high_low_average * 0.618

// Calculate 滿足區 (satisfaction zone)
satisfaction_zone_upper = estimated_high_level - ema_high_low_regular / 8
satisfaction_zone_lower = estimated_low_level + ema_high_low_regular / 8

plot(estimated_high_level, title="Estimated High (Session Low + Est. Range)", color=color.yellow, linewidth=2, style=plot.style_cross)

plot(satisfaction_zone_upper, title="滿足區 Upper", color=color.gray, linewidth=2, style=plot.style_cross)
plot(potential_high_level, title="Potential High", color=color.new(color.yellow, 50), linewidth=2, style=plot.style_cross)
plot(potential_low_level, title="Potential Low", color=color.new(color.orange, 50), linewidth=2, style=plot.style_circles)
plot(satisfaction_zone_lower, title="滿足區 Lower", color=color.gray, linewidth=2, style=plot.style_circles)
plot(estimated_low_level, title="Estimated Low (Session High - Est. Range)", color=color.orange, linewidth=2, style=plot.style_circles)

// Create table to display values
var table info_table = table.new(position.middle_right, 2, 6, bgcolor=color.new(color.white, 80), border_width=1)

if barstate.islast
    table.cell(info_table, 0, 0, "Estimated High", text_color=color.yellow, bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 0, str.tostring(estimated_high_level[1], "#"), text_color=color.yellow, bgcolor=color.rgb(0, 0, 0, 30))

    table.cell(info_table, 0, 1, "滿足區 Upper", text_color=color.blue, bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 1, str.tostring(satisfaction_zone_upper[1], "#"), text_color=color.gray, bgcolor=color.rgb(0, 0, 0, 30))

    table.cell(info_table, 0, 2, "Potential High", text_color=color.new(color.yellow, 50), bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 2, str.tostring(potential_high_level[1], "#"), text_color=color.new(color.yellow, 50), bgcolor=color.rgb(0, 0, 0, 30))

    table.cell(info_table, 0, 3, "Potential Low", text_color=color.new(color.orange, 50), bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 3, str.tostring(potential_low_level[1], "#"), text_color=color.new(color.orange, 50), bgcolor=color.rgb(0, 0, 0, 30))

    table.cell(info_table, 0, 4, "滿足區 Lower", text_color=color.blue, bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 4, str.tostring(satisfaction_zone_lower[1], "#"), text_color=color.gray, bgcolor=color.rgb(0, 0, 0, 30))

    table.cell(info_table, 0, 5, "Estimated Low", text_color=color.orange, bgcolor=color.rgb(0, 0, 0, 30))
    table.cell(info_table, 1, 5, str.tostring(estimated_low_level[1], "#"), text_color=color.orange, bgcolor=color.rgb(0, 0, 0, 30))


```

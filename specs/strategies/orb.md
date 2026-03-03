# Opening Range Breakout Strategy (`ORBStrategy`)

## 策略概述

開盤區間突破（ORB）策略，用於台指期日盤。以開盤初期的高低點定義區間，區間結束後等待收盤突破，進場做多或做空。

---

## 策略規則

| 規則 | 說明 |
|------|------|
| **交易時段** | 日盤：08:45 ~ 13:45 |
| **開盤區間** | 08:45 ~ `range_end` 的高低點（預設 09:00，可調 08:50~09:15） |
| **多單進場** | 收盤 > 區間高 AND 當日尚未做多 → 買進 |
| **空單進場** | 收盤 < 區間低 AND 當日尚未做空 → 賣出 |
| **每日限制** | 每個方向最多進場一次（多空互斥，後者取代前者） |
| **停損** | 進場價 ± 進場時收盤 × 0.5% |
| **停利** | 停損距離 × `tp_multiplier`（預設 2.0） |
| **追蹤停損** | 09:45 後啟動；以進場後的最高/最低收盤價追蹤；回撤 0.5% 出場 |
| **強制出場** | 13:30 — 有部位一律平倉 |

---

## 參數（可供最佳化）

```python
range_end_minute: int = 60     # 區間結束時間（分鐘，從 08:00 算起）
                                # 50=08:50, 60=09:00, 75=09:15
sl_pct: float = 0.005          # 停損比例（0.5%）
tp_multiplier: float = 2.0     # 停利倍數
trail_activate_minute: int = 45 # 追蹤停損啟動（09:00 後幾分鐘），45=09:45
```

---

## 實作設計

### 檔案

| 檔案 | 說明 |
|------|------|
| `pyproject.toml` | 加入 `backtesting>=0.3.3` |
| `src/strategies/orb.py` | `ORBStrategy` class |
| `src/backtest/runner.py` | 資料載入 + 執行器 |

### 架構決策

- **連續多日回測**：整段資料一次傳入，在 `next()` 內偵測日期切換並重置每日狀態
- **手動管理出場**：不使用 `buy(sl=, tp=)` 參數，統一在 `next()` 處理，方便支援追蹤停損與時間觸發

### 每日狀態（日期切換時重置）

```python
self.or_high = None          # 開盤區間高
self.or_low = None           # 開盤區間低
self.range_confirmed = False # 區間已確認
self.long_entered = False    # 今日已做多
self.short_entered = False   # 今日已做空
# 出場追蹤
self.entry_price = None
self.sl_price = None
self.tp_price = None
self.trail_peak = None       # 做多用：進場後最高收盤
self.trail_trough = None     # 做空用：進場後最低收盤
```

### `next()` 執行流程

```
A. 偵測日期切換 → 重置每日狀態
B. 累積開盤區間（time <= range_end_time）
C. 超過 range_end_time 後標記 range_confirmed
D. 進場檢查（range_confirmed 才執行）：
     多單：收盤 > or_high AND not long_entered
       → 若有空單先平倉，再開多
     空單：收盤 < or_low AND not short_entered
       → 若有多單先平倉，再開空
E. 出場檢查（有部位才執行）：
     time >= 13:30 → 強制平倉（優先）
     time < 09:45：固定停損/停利
     time >= 09:45：追蹤停損（仍可提前達停利）
```

### 多空互斥邏輯

`backtesting.py` 本身只支援單一部位，與本策略的互斥設計相符：

- 做多後出現空單信號 → 平多 + 開空（若空單尚未用過）
- 做空後出現多單信號 → 平空 + 開多（若多單尚未用過）
- 每個方向用過一次後即鎖定，當日不再重複進場

### 資料載入（`runner.py`）

```python
# 從 DuckDB 載入 ohlcv_1m，轉為 backtesting.py 格式
df = conn.execute("""
    SELECT timestamp, open, high, low, close, volume
    FROM ohlcv_1m
    WHERE symbol = 'TX'
    ORDER BY timestamp
""").df()
df = df.set_index("timestamp")
df.columns = ["Open", "High", "Low", "Close", "Volume"]
```

```python
bt = Backtest(
    data,
    ORBStrategy,
    cash=1_000_000,
    commission=50 / 350_000,  # 約 NT$50/口，合約價值約 35萬
    trade_on_close=True,       # 收盤確認後進場
)
```

---

## 驗證方式

```bash
uv sync                                                    # 安裝 backtesting
uv run python src/backtest/runner.py --start 2025-01-01   # 近一年測試
uv run python src/backtest/runner.py                       # 全期回測
```

### 正確性檢查

- 區間期間（08:45~range_end）不應有進場
- 每個交易日最多出現 1 筆進場
- 13:30 後不應有未平倉部位
- 停損距離 = `entry_price × 0.5%`，停利距離 = 停損 × 2

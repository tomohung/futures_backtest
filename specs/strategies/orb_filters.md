# ORB 策略過濾器優化計畫

## 背景與動機

### 基準版結果（2023–2025，3 年）

| 指標 | 數值 | 評估 |
|---|---|---|
| 勝率 | 44.9% | 遠低於目標 55% |
| 平均盈虧比 | 1.24 | 低於目標 1.5 |
| 獲利因子 | 1.02 | 幾乎打平，手續費即可吞噬 |
| 期望值 | +1.0 pts/筆 | 不具實戰意義 |

### 為何不繼續參數最佳化

1,088 組參數組合全掃描後，**無任何組合能同時達到 55% 勝率 ＋ 1.5 盈虧比**。
Pareto 前緣顯示這是策略結構的根本取捨，不是參數問題。

**結論：裸 ORB 的 edge 不足，需要加入訊號品質過濾器，減少低品質進場。**

---

## 目標

| 指標 | 目標 |
|---|---|
| 勝率 | ≥ 52%（放寬至合理範圍） |
| 平均盈虧比 | ≥ 1.3 |
| 獲利因子 | ≥ 1.2 |
| 每年交易次數 | 參考用，非硬門檻（見注意事項） |

---

## 過濾器設計

### Filter 1：開盤區間幅度過濾（OR Range Size）

**假設：** 開盤區間過窄（< 0.X%）時，突破容易是假突破；區間夠大才代表有方向性共識。

**實作：**
```python
min_range_pct: float = 0.003   # 最小區間幅度（佔價格比例）

# 在 range_confirmed 後，進場前檢查：
or_range = (self.or_high - self.or_low) / self.or_low
if or_range < self.min_range_pct:
    return  # 區間太窄，本日不進場
```

**參數掃描：**

| 參數 | 測試值 |
|---|---|
| `min_range_pct` | 0.0, 0.002, 0.003, 0.004, 0.005 |

> `0.0` = 不過濾（等同基準版），用來量化過濾效果。

---

### Filter 2：趨勢方向過濾（Trend Filter）

**假設：** 順大趨勢的 ORB 突破成功率較高；逆勢突破容易被打回。

**實作：** 以過去 N 根日 K 的收盤均線作為趨勢判斷基準。
- 當日開盤價 > MA → 只做多，忽略空單訊號
- 當日開盤價 < MA → 只做空，忽略多單訊號
- 可選：雙向都做，但順勢的停利放大

日 K 均線換算成 1 分 K 資料：`N 日 ≈ N × 301 根 1 分 K`

```python
trend_ma_days: int = 0   # 0 = 不啟用

# init() 中：
if self.trend_ma_days > 0:
    n_bars = self.trend_ma_days * 301
    closes = pd.Series(self.data.Close)
    self._trend_ma = self.I(
        lambda: closes.rolling(n_bars, min_periods=n_bars).mean(),
        name="Trend MA", overlay=True
    )

# next() 進場前：
if self.trend_ma_days > 0:
    ma_val = self._trend_ma[-1]
    if np.isnan(ma_val):
        return
    if close > self.or_high and not self.long_entered:
        if close < ma_val:
            return  # 逆勢多單，跳過
    if close < self.or_low and not self.short_entered:
        if close > ma_val:
            return  # 逆勢空單，跳過
```

**參數掃描：**

| 參數 | 測試值 |
|---|---|
| `trend_ma_days` | 0（不啟用）, 5, 10, 20, 60 |

---

### Filter 3：開盤跳空過濾（Gap Filter）

**假設：** 昨收與今開跳空過大時，行情已提前反應，ORB 的預測力下降；跳空過小則市場無明顯情緒變化。

**兩種跳空情境：**
1. **大跳空**（gap > X%）：行情已過度延伸，突破後容易反轉
2. **小跳空或無跳空**：行情連續性佳，ORB 效果較好

```python
max_gap_pct: float = 0.0   # 0.0 = 不過濾；0.01 = 跳空超過 1% 時跳過

# next() 日期切換時記錄前日收盤，進場前計算：
gap_pct = abs(today_open - prev_close) / prev_close
if self.max_gap_pct > 0 and gap_pct > self.max_gap_pct:
    return  # 跳空過大，本日不進場
```

**實作細節：**
- `prev_close`：前一交易日 13:30 強制出場時的收盤價（在 _reset_daily 前記錄）
- `today_open`：當日第一根 K 棒的 Open

**參數掃描：**

| 參數 | 測試值 |
|---|---|
| `max_gap_pct` | 0.0（不啟用）, 0.005, 0.008, 0.010, 0.015 |

---

## 實作計畫

### Phase 1：逐一加入並獨立驗證（建議順序）

```
Filter 1 (Range Size)  →  最簡單，效果最直覺
Filter 2 (Trend)       →  需要調整 init()，影響較大
Filter 3 (Gap)         →  需要跨日狀態，需小心重置邏輯
```

每個 filter 獨立加入後，**先在 2023–2025 全期跑敏感度掃描，確認方向正確再繼續**。

### Phase 2：組合測試

各 filter 獨立驗證有效後，進行二階組合測試：

```
(Range Size) × (Trend)   →  最有可能組合
(Range Size) × (Gap)
(Trend)      × (Gap)
```

若組合仍有 edge → 三者組合最終測試。

### Phase 3：Out-of-sample 驗證

- Train：2023–2024（2 年）
- Validation：2025（1 年）
- Test（未碰過）：2026

---

## 修改檔案

| 檔案 | 修改內容 |
|---|---|
| `src/strategies/orb.py` | 新增 3 個 filter 參數及對應邏輯 |
| `src/backtest/optimize.py` | 新增 filter 參數到 `PARAM_GRID` |
| `specs/strategies/orb_filters.md` | 本文件 |

### `orb.py` 參數新增（目標）

```python
class ORBStrategy(Strategy):
    # 現有參數
    range_end_minute: int = 65
    entry_end_minute: int = 90
    sl_pct: float = 0.005
    tp_multiplier: float = 2.0
    trail_activate_minute: int = 45

    # 新增 Filter 參數
    min_range_pct: float = 0.0     # Filter 1: 最小區間幅度（0=不過濾）
    trend_ma_days: int = 0         # Filter 2: 趨勢均線天數（0=不過濾）
    max_gap_pct: float = 0.0       # Filter 3: 最大開盤跳空（0=不過濾）
```

所有新參數預設值為「不啟用」（0），確保與現有基準版完全相容。

---

## 測試計畫

### 每個 Filter 的獨立測試格式

```bash
# Filter 1 掃描
uv run python src/backtest/optimize.py --filter range-size

# Filter 2 掃描
uv run python src/backtest/optimize.py --filter trend

# Filter 3 掃描
uv run python src/backtest/optimize.py --filter gap
```

（或直接在 `optimize.py` 裡切換 `PARAM_GRID` 的 filter 欄位）

### 評估指標（每次掃描後記錄）

| 指標 | 說明 |
|---|---|
| 勝率變化 | vs 基準版 44.9% |
| 期望值變化 | vs 基準版 +1.0 pts |
| 獲利因子變化 | vs 基準版 1.02 |
| 交易次數 | 參考用，非硬門檻（見注意事項） |
| 最大回撤 | 不應明顯惡化 |

---

## 成功標準

| 條件 | 門檻 |
|---|---|
| 勝率（2023–2025） | ≥ 52% |
| 平均盈虧比 | ≥ 1.3 |
| 獲利因子 | ≥ 1.2 |
| 年均交易次數 | 參考用，非硬門檻（見注意事項） |
| 2026 OOS 勝率 | ≥ 50%（不退化） |
| 2026 OOS 獲利因子 | ≥ 1.0（不虧損） |

若任何單一 filter 在 train 期間達標，進入 Phase 2 組合測試。
若組合版在 validation（2025）達標，才碰 test（2026）。

---

## 注意事項

- **避免過度最佳化**：每次只測一個維度，保留 2026 資料作為最終驗證
- **記錄每次測試結果**：更新 `output/orb_backtest_report.md`
- **交易次數監控**：交易次數少不代表無效。若年均交易次數 < 30 筆，需勝率顯著高於基準版（例如 > 60%）且獲利因子 ≥ 1.3 才採用；若 < 10 筆，樣本過小，直接排除
- **實作順序**：先讓程式碼可跑通（含單元測試），再跑最佳化，避免 bug 污染結果

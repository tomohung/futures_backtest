# ORB Long-Only：做多專注策略

## 背景與動機

Phase 6 Step 0 探索性分析結論：

1. **機制濾網方向放棄** — ATR%、ADX、實現波動率與 ORB 勝率的相關性均弱（|r| < 0.13），無法建立可靠的機制濾網
2. **2021 指標值與好年份重疊** — 2021 ATR%=1.5 與 2024 相同；2023 ATR% 更低（1.1）但表現良好；指標無法區分「壞機制」與「好機制」年份
3. **做空心理挑戰** — 做空勝率常年低於 50%（2021: 44%, 2022: 42%, 2023: 50%），對當沖交易者造成持續心理壓力

**用戶決策：聚焦做多，放棄做空。**

### 現況數據（Ph4 Hybrid 做多 vs 雙向）

| 年度 | 僅做多 | 雙向（含空） | 差額（空方貢獻） |
|---|---|---|---|
| 2021 | -498 | +10 | +508 |
| 2022 | +228 | +96 | -132 |
| 2023 | +302 | +351 | +49 |
| 2024 | +1,037 | +1,527 | +490 |
| 2025 | +1,823 | +1,845 | +22 |
| 2026 | +1,617 | +1,824 | +207 |
| **總計** | **+4,509** | **+5,653** | **+1,144** |

犧牲空方 → 損失 +1,144 pts，但換取心理穩定性（勝率一致性）。

---

## 問題診斷：2021 做多為何失敗？

從探索分析的做多四分位數據發現：

**ADX 做多分層（最相關）：**

| ADX 四分位 | n | win% | exp | total | ADX 範圍 |
|---|---|---|---|---|---|
| Q1 (低) | 79 | 51.9% | +12.5 | +986 | 6.8~16.8 |
| Q2 | 79 | 45.6% | +6.7 | +530 | 16.8~23.2 |
| Q3 | 79 | 55.7% | +12.0 | +946 | 23.2~32.7 |
| Q4 (高) | 79 | 57.0% | +29.9 | +2,364 | 32.7~61.4 |

2021 平均 ADX = **20.5**（落在 Q2 最差區間），2024 平均 ADX = **27.7**（落在 Q3 良好區間），2026 平均 ADX = **36.5**（Q4 最佳）。

ADX 雖然整體相關性弱（r=+0.092），但高 ADX（>25）確實對應更好的做多表現。

---

## 策略設計

### 做多信號（維持 Ph4 Hybrid 邏輯）

```
進場：收盤突破 OR high，趨勢濾網（TrendMA > close 時不做多）
SL：sl_pct（固定百分比）
TP：tp_or_multiplier × max(OR_width, or_min_width)
Trailing：trail_activate_minute 後啟動
強制出場：13:30
```

### 不變部分

沿用 Ph4 Hybrid 全部固定參數：

```python
range_end_minute=90, entry_end_minute=120,
trail_activate_minute=45, trend_ma_days=10,
or_min_width=20.0, tp_multiplier=1.5  # （僅影響做空，做多不用）
```

### 新增選項：ADX 做多濾網（Step 2）

基於探索結果，ADX > threshold 時才做多：

```python
long_adx_min: float = 0.0   # 0=停用，25=過濾 Q2 以下
```

---

## Step 1：做多基準線確認

### 腳本：`src/backtest/optimize_longonly.py`（新建）

**Grid（重新針對做多最佳化）：**

```python
GRID = {
    "tp_or_multiplier": [1.0, 1.25, 1.5, 2.0, 2.5, 3.0],
    "sl_pct":           [0.003, 0.004, 0.005, 0.006],
}  # 24 組
```

僅使用 `ORBLongOnlyStrategy`（或在 Ph4 Hybrid 加入 `long_only=True` 參數）。

**輸出：**
- 2021–2026 年度 PnL 表（僅做多）
- 最佳參數詳細拆解
- 與 Ph4 Hybrid 雙向基準比較

---

## Step 2：ADX 做多濾網測試

確認 Step 1 最佳參數後，疊加 ADX 濾網：

```python
GRID_ADX = {
    "long_adx_min":    [20, 22, 25, 28, 30],
    "adx_period":      [10, 14],
}  # 10 組
```

ADX 從日線計算，對齊至 1 分線（同 TrendMA 做法）。

**可行性門檻：2021 ≥ -200 且總計不低於 Step 1 基準 -10%。**

---

## 成功標準

| 指標 | 目標 |
|---|---|
| 總計 PnL | ≥ +4,509（至少不低於做多基準） |
| 2021 單年 | ≥ -200（目前 -498，目標大幅改善） |
| 無單年 | < -300 pts |
| 做多勝率（所有年） | ≥ 50% |
| 做多 PF（所有年） | ≥ 1.0 |

---

## 實作順序

| 步驟 | 檔案 | 動作 |
|---|---|---|
| Step 1 | `src/strategies/orb.py` | 修改：`ORBPhase4HybridStrategy` 加入 `long_only: bool = False` 參數，若為 True 跳過空單信號 |
| Step 2 | `src/backtest/optimize_longonly.py` | 新建：做多 Grid 優化 + 年度拆解 |
| Step 3 | `src/strategies/orb.py` | 修改：加入 `long_adx_min` / `adx_period` 參數，ADX 從傳入的 DataFrame 列讀取 |
| Step 4 | `src/backtest/runner.py` | 修改：`load_data_with_night_ma` 加入 `adx_period` 參數，計算日線 ADX 並對齊至 1 分線 |
| Step 5 | `src/backtest/optimize_longonly.py` | 修改：加入 ADX 濾網 Grid |
| Step 6 | `src/backtest/summary_all.py` | 修改：加入 Long-Only 最佳參數 |

### 驗證指令

```bash
# Step 1+2：做多 Grid 優化
uv run python src/backtest/optimize_longonly.py

# 最終總覽
uv run python src/backtest/summary_all.py
```

---

## 備選方案

若 Step 1 做多基準 2021 仍 ≤ -400 且無 ADX 閾值能改善至 ≥ -200：

1. **接受 2021 是統計異常** — 6 年累積仍為正，2021 的損失由後續年份補回
2. **加入月份濾網** — 分析 2021 哪些月份最差，是否有規律
3. **加入趨勢強度（MA 斜率）** — 不只看 MA 方向，也看 MA 是否在加速

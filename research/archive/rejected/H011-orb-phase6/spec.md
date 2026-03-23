# ORB Phase 6：市場機制濾網（Regime Filter）

## Phase 5 結論

Phase 5 嘗試以「N 日滾動 OR 均寬」作為機制濾網，結果如下：

| 組合 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | 總計 |
|---|---|---|---|---|---|---|---|
| Ph4 Hybrid（無濾網） | +10 | +96 | +351 | +1,527 | +1,845 | +1,824 | **+5,653** |
| w=20, min=60（最佳可行） | -189 | +96 | +199 | +1,527 | +1,845 | +1,824 | +5,302 |
| w=10, min=100（2021 轉正） | +278 | -29 | +39 | +1,148 | +1,845 | +1,824 | +5,105 |
| w=10, min=120（過濾太多） | +465 | +316 | 0 | +139 | +1,324 | +1,477 | +3,721 |

**結論：OR 均寬是窄義波動指標，只能局部改善 2021，且一定程度犧牲其他年份。**

根本原因在於：2021 整年的短空方向雖然獲利（+508 pts），濾掉安靜日同時也濾掉了這些有效空單，造成淨損。

---

## 問題根因

ORB 策略的核心假設是「突破後延續趨勢」。這個假設在以下機制（Regime）下成立：

- 市場有明確方向性（trending）
- 日內波動幅度足夠讓 TP 被打到
- 突破後沒有快速回吐

2021 是典型的「震盪/均值回歸」機制：

- 台灣股市 2021 全年緩步上漲，波動小、無急漲急跌
- OR 突破後頻繁回吐，做多成功率僅 39~43%
- 做短固然有效，但這是機制特性，非可穩定預測的優勢

**OR 均寬是症狀，不是病因。需要更廣義的「方向性 / 趨勢強度」指標。**

---

## 機制指標候選

| 指標 | 計算方式 | 選取理由 |
|---|---|---|
| **ADX(14) 日線** | 14 日方向強度指數 | 直接衡量「有無趨勢」；ADX < 20 = 盤整機制 |
| **ATR% (14 日，日線)** | 14 日 ATR ÷ 收盤價 × 100 | 正規化日波動，跨年度可比，比 OR 寬更穩定 |
| **實現波動率（21 日）** | 21 日日收益率的滾動標準差 × √252 | 基於報酬的波動估計，與 VIX 概念一致 |
| **滾動 ORB 勝率** | 最近 N 筆 ORB 訊號的勝率 | 自我適應：策略本身表現變差時自動暫停 |

### 各指標特性比較

**ADX**
- 優點：直接回答「市場有無方向」，與 ORB 核心假設最直接對應
- 缺點：ADX 落後於價格，趨勢已結束才反應；需日線資料
- 適用：當 ADX 持續低於門檻（如 < 20）→ 整體暫停進場

**ATR%（正規化日 ATR）**
- 優點：比 OR 均寬更穩定，覆蓋全日波動而非僅開盤 45 分鐘
- 缺點：仍屬波動代理指標，非直接的方向性指標
- 適用：ATR% 低於門檻 → 市場太安靜 → 跳過

**實現波動率**
- 優點：基於報酬序列，統計性質較好
- 缺點：低波動率也可能出現在趨勢平穩時期，誤殺
- 適用：輔助確認，與 ADX 組合使用

**滾動 ORB 勝率**
- 優點：直接量測策略表現，最具適應性
- 缺點：樣本量少（每日最多 1 筆），N=20 需要 4 週以上暖機；存在前視偏差風險
- 適用：以最近 20 筆進場為基礎，勝率 < 40% → 暫停

---

## Step 0：探索性分析

### 腳本：`src/backtest/explore_regime.py`（新建）

#### 計算項目（每個交易日）

從 `ohlcv_1m` 合成日線 OHLCV，計算：

```
daily_atr_pct     = ATR(14) / close × 100         ← 正規化日 ATR
daily_adx         = ADX(14, 日線)                   ← 方向性強度
realized_vol      = rolling 21 日 std(log_return) × sqrt(252)
rolling_win_rate  = 最近 20 筆 ORB 訊號的勝率（加入 Phase 4 Hybrid 跑出的逐筆交易）
```

#### 分析項目

**1. 年度平均值比較**

各指標各年份平均值，確認 2021 是否在所有指標上都偏低：

| 年度 | avg ATR% | avg ADX | avg RealVol | avg 月報酬% |
|---|---|---|---|---|
| 2021 | | | | |
| 2022 | | | | |
| 2023 | | | | |
| 2024 | | | | |
| 2025 | | | | |
| 2026 | | | | |

**2. 指標四分位分層 × 策略表現**

將每個指標依四分位（Q1=最弱/最低 ~ Q4=最強/最高）分組，
各組統計 Ph4 Hybrid 的 win%、exp/trade、PF、total PnL：

| 指標分組 | n 筆 | win% | exp | total |
|---|---|---|---|---|
| Q1（最低） | | | | |
| Q2 | | | | |
| Q3 | | | | |
| Q4（最高） | | | | |

**3. 相關性：指標 vs 當日 ORB 勝負**

對每筆 Ph4 Hybrid 進場交易，取進場日的指標值，計算與勝負（1/0）的點二列相關：

```
r(ADX,          trade_win)
r(ATR%,         trade_win)
r(realized_vol, trade_win)
r(rolling_win,  trade_win)
```

**4. 可視化（選擇性）**

月度 ATR% 走勢圖，標記每月 ORB win%，確認視覺上的一致性。

#### 決策準則

| 發現 | 後續行動 |
|---|---|
| ADX 與勝率相關最強 | Phase 6 以 ADX 為主指標 |
| ATR% 與勝率相關最強 | Phase 6 以 ATR% 為主指標（概念升級自 Phase 5） |
| 兩者相近 | 測試 ADX + ATR% 組合（AND 條件） |
| 滾動勝率最強 | Phase 6 以滾動 ORB 勝率為主（需注意前視偏差） |
| 無一指標 r > 0.15 | 機制濾網方向放棄，改探索其他方向 |

---

## Step 1：指標設計與資料準備

### `src/backtest/runner.py` 修改

擴充 `load_data_with_night_ma`，新增 `regime_indicator` 參數（或建立獨立函數）：

```python
def load_data_with_night_ma(
    ...,
    regime_type: str = "",   # "", "adx", "atr_pct", "realvol"
    regime_period: int = 14,
):
```

日線 OHLCV 從 1 分線合成後計算指標，以 `forward fill` 方式對齊至 1 分線時間戳（與 TrendMA 相同做法），存為 `RegimeVal` 欄位。

**ADX 計算（純 pandas/numpy 實作，不依賴 ta-lib）：**

```python
def compute_adx(high, low, close, period=14):
    tr  = true_range(high, low, close)
    dm_plus  = directional_movement(high, low, positive=True)
    dm_minus = directional_movement(high, low, positive=False)
    atr  = ewm_or_rolling_mean(tr, period)
    di_plus  = 100 * ewm_or_rolling_mean(dm_plus, period) / atr
    di_minus = 100 * ewm_or_rolling_mean(dm_minus, period) / atr
    dx  = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
    adx = ewm_or_rolling_mean(dx, period)
    return adx
```

---

## Step 2：策略實作

### `src/strategies/orb.py` 修改

在 `ORBPhase4HybridStrategy` 新增機制濾網參數（或建立 `ORBPhase6Strategy` 子類別）：

```python
regime_min: float = 0.0   # 指標低於此值時跳過進場（0=停用）
```

進場邏輯加入：

```python
_regime_ok = (
    self.regime_min == 0.0
    or (not np.isnan(self._regime_val[-1])
        and self._regime_val[-1] >= self.regime_min)
)
if _regime_ok:
    # 原本的多空進場邏輯...
```

---

## Step 3：優化

### 腳本：`src/backtest/optimize_phase6.py`（新建）

**固定參數**（沿用 Ph4 Hybrid 最佳）：

```python
PH4H_BASE = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
    tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10,
)
```

**優化網格**（依 Step 0 選出的最佳指標）：

```python
# 若 ADX 最佳：
GRID = {
    "regime_min":    [15, 18, 20, 22, 25],
    "regime_period": [10, 14, 20],
}  # 15 組

# 若 ATR% 最佳：
GRID = {
    "regime_min":    [0.5, 0.6, 0.7, 0.8, 1.0],
    "regime_period": [10, 14, 20],
}  # 15 組
```

**輸出格式**（同 Phase 5）：

- 各年度長/空 PnL 分解表
- 可行性篩選：2021 ≥ -200（或以 Step 0 發現調整）
- 最佳組合詳細年度拆解

---

## 成功標準

| 指標 | 目標 |
|---|---|
| 總計 PnL | ≥ Ph4 Hybrid +5,653 pts（濾網不應犧牲太多整體獲利） |
| 2021 單年 | ≥ 0（目標轉正） |
| 無單年 | < -200 pts |
| 濾掉交易數 | < 20%（不應大幅降低交易機會） |

---

## 實作順序

| 步驟 | 檔案 | 動作 |
|---|---|---|
| Step 0 | `src/backtest/explore_regime.py` | 新建：計算四個指標，分析年度均值 + 分層表現 + 相關性 |
| Step 1 | `src/backtest/runner.py` | 修改：擴充 `load_data_with_night_ma`，加入 `regime_type` 計算與對齊 |
| Step 2 | `src/strategies/orb.py` | 修改：`ORBPhase4HybridStrategy` 加入 `regime_min` 濾網（或建子類別） |
| Step 3 | `src/backtest/optimize_phase6.py` | 新建：以最佳指標跑門檻網格，年度拆解 |
| Step 4 | `src/backtest/summary_all.py` | 修改：加入 Phase 6 最佳參數 |

### 驗證指令

```bash
# Step 0：確認哪個指標最具區分力
uv run python src/backtest/explore_regime.py

# Step 3：網格優化（指標確定後）
uv run python src/backtest/optimize_phase6.py

# 最終總覽
uv run python src/backtest/summary_all.py
```

---

## 備選方案（若 Step 0 無強信號）

若所有候選指標與 ORB 勝率相關均低（r < 0.10），代表機制濾網方向不適合本策略，可改探索：

1. **時段過濾**：特定月份（如 1~3 月）是否系統性差？
2. **強制做空禁用**：僅做多，避免空單低勝率心理壓力
3. **市場結構**：加入外部資料（如 MSCI 台灣指數 ETF 的 ADX 或 RSI）

但優先走指標路線，因為外部資料引入複雜度高。

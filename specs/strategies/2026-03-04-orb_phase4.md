# ORB Phase 4：自適應 TP 優化

## Phase 3 結論

Phase 3 嘗試了多種 SL 優化方案，結果如下：

| 策略 | 2021~2026 累積 | 問題 |
|---|---|---|
| Phase 2 Base | **+4,632 pts** | 2021/2022 表現弱 |
| Phase 3A (OR SL + OR TP + bar trail) | +655 pts | 做空爛掉，2021/2022 負 |
| Phase 3B (OR SL + Super Trend 出場) | +1,913 pts | 最佳 Phase 3，但仍遜於 Phase 2 |
| Plan C (動量停滯出場) | +1,169 pts | 2021/2022/2024 負 |
| Plan C Hybrid (非對稱 SL + 動量) | +1,362 pts | 同上 |

**結論：換 SL 不是解答。Phase 2 的固定百分比 SL 已是最穩定的。**

---

## 問題診斷

Phase 2 各年度詳細數據：

| 年度 | 筆數 | 勝率 | PF | 期望值 | 強制出場% |
|---|---|---|---|---|---|
| 2021 | 130 | 43.8% | 1.09 | +3.1 | **27.7%** |
| 2022 | 114 | 45.6% | 1.07 | +1.9 | **27.2%** |
| 2023 | 111 | 51.4% | 1.11 | +2.4 | 63.1% |
| 2024 | 114 | 50.9% | 1.22 | +8.8 | 35.1% |
| 2025 | 95  | 56.8% | 1.49 | +16.7 | 45.3% |

**關鍵觀察：**
- 2021/2022 的強制出場率僅 27%，代表 TP（0.75%）根本很少被打到
- 多數交易在 TP 前就被 SL 或 trailing stop 出場，積累小虧損
- 2025 強制出場率 45%，代表更多交易有方向性，帶著獲利撐到收盤

**根本原因：TP 是固定百分比，不考慮當日波動度**

Phase 2 TP = entry ± (sl_pct × tp_multiplier) = entry ± 0.75%，與當日實際波動無關。

---

## 夜盤波動假設（需探索驗證）

台指期夜盤（15:00 ~ 隔日 05:00）反映美股盤後動態。夜盤波動可能影響日盤兩種方式：

**情境 A：正相關（夜盤動 → 日盤也動）**
- 美股跳空 → 台指夜盤大幅震盪 → 日盤延續趨勢
- 應用：夜盤 range 大 → 日盤 TP 應設更遠

**情境 B：負相關（夜盤已消化 → 日盤縮量整理）**
- 夜盤已釋放情緒 → 日盤反而區間震盪
- 應用：夜盤 range 大 → 日盤 TP 應設較近，或進場條件更嚴格

目前日盤 ATR 計算完全不含夜盤，可能低估或高估真實波動度。

**→ 在設計 TP 策略前，必須先做探索性分析確認實際關係。**

---

## Step 0：探索性分析（先跑，再決定策略）

### 腳本：`src/backtest/explore_night_day.py`

#### 計算對象（每個交易日）

```
night_range  = 前夜盤 (15:00 前日 ~ 08:44 當日) 的 high - low
or_range     = 日盤 OR 期間 (08:45 ~ 09:30) 的 high - low
day_range    = 日盤全段 (08:45 ~ 13:45) 的 high - low
open_gap     = 日盤開盤價 - 夜盤收盤價（08:45 open - 前夜 05:00 close）
```

#### 分析項目

**1. 相關性矩陣**
```
night_range  vs  or_range       ← 夜盤是否預測日盤 OR 大小？
night_range  vs  day_range      ← 夜盤是否預測日盤全段波動？
or_range     vs  day_range      ← OR 是否是日盤最好的代理？
open_gap     vs  day_range      ← 跳空大小是否影響日盤波動？
```

**2. 夜盤分層分析**

將 night_range 依四分位分成 4 組（Q1=最窄 ~ Q4=最寬），每組統計：

| 指標 | Q1(最窄) | Q2 | Q3 | Q4(最寬) |
|---|---|---|---|---|
| avg or_range | | | | |
| avg day_range | | | | |
| Phase 2 win% | | | | |
| Phase 2 exp/trade | | | | |
| Phase 2 force_exit% | | | | |

**3. 年度夜盤統計**

各年度 night_range 的平均值與標準差，確認 2021/2022 是否確實夜盤偏窄（對應日盤也安靜）。

#### 決策準則

| 發現 | 對應 TP 設計 |
|---|---|
| night_range 與 day_range **正相關** (r > 0.4) | 將夜盤 range 納入 TP 計算（加權或取最大） |
| night_range 與 day_range **負相關** (r < -0.2) | 夜盤寬時設緊 TP；夜盤窄時設寬 TP（反向） |
| night_range 與 day_range **弱相關** (|r| < 0.2) | 夜盤訊號無效，使用 OR 寬度或日盤 ATR 即可 |
| or_range 是 day_range 最好代理 (r > 0.6) | 優先用 OR 寬度作為 TP 基準 |

---

## Step 1：TP 策略設計（根據探索結果選擇）

### 候選方案

**方案 A：OR 寬度 TP**（夜盤無顯著預測力時）
```
TP = 進場價 ± tp_or_multiplier × OR_width
OR_width = OR_high - OR_low  (08:45 ~ 09:30)
```

**方案 B：含夜盤的 True Range TP**（夜盤與日盤正相關時）
```
overnight_range = max(night_high, day_open) - min(night_low, day_open)
TP = 進場價 ± tp_multiplier × overnight_range
```
實作方式：夜盤高低點可從 `load_data_with_night_ma()` 載入的連續資料中取得，以 `self.I()` 傳入策略。

**方案 C：夜盤條件式 TP**（夜盤有預測力時）
```
if night_range > night_range_ma:   # 夜盤比近期平均寬
    TP = 進場價 ± tp_wide_mult × OR_width
else:                               # 夜盤安靜
    TP = 進場價 ± tp_narrow_mult × OR_width
```
兩個乘數分開優化。

> **預設推進方案 A**，若探索結果顯示夜盤有顯著預測力則改用 B 或 C。

### 共同不變設計

無論採用哪個方案，以下全部沿用 Phase 2：
- SL = 進場價 ± sl_pct（固定百分比）
- Trailing stop：trail_activate_minute 後啟動
- 強制出場：13:30
- 趨勢濾網：TrendMA(10天)
- 進場條件：OR 突破

---

## Step 2：優化

### 共同優化參數

| 參數 | 說明 | 測試值 |
|---|---|---|
| `tp_or_multiplier` | TP = N × 波動基準 | 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0 |
| `sl_pct` | SL 距離（固定百分比） | 0.004, 0.005, 0.006 |

共 **7 × 3 = 21 組**

### 固定參數（沿用 Phase 2 最佳值）

| 參數 | 值 |
|---|---|
| `range_end_minute` | 90 |
| `entry_end_minute` | 120 |
| `trail_activate_minute` | 45 |
| `trend_ma_days` | 10 |

### Train / OOS 分割

- Train：2025-01-01 ~ 2025-12-31
- OOS：2026-01-01 ~

### 成功標準（同 Phase 2/3）

| 指標 | Train 目標 | OOS 門檻 |
|---|---|---|
| 勝率 | ≥ 52% | ≥ 50% |
| 平均盈虧比 | ≥ 1.3 | — |
| 獲利因子 | ≥ 1.2 | ≥ 1.0 |

### 歷史年度驗證（Phase 4 特有）

最佳參數額外回測 2021–2024，目標：

| 指標 | 驗證目標 |
|---|---|
| 2021/2022 期望值 | 明顯高於 Phase 2（目前 +3.1/+1.9 pts） |
| 2021/2022 強制出場% | 高於 27%（代表 TP 被打到更多） |
| 6 年累積 PnL | > Phase 2 +4,632 pts |
| 單年最差 | 不應低於 -200 pts |

### 新增診斷指標

```
tp_exit%    = 盤中獲利出場（TP 或 trailing，非強制）
sl_exit%    = 盤中虧損出場（SL 被打到）
force_exit% = 13:30 強制出場
```

若 Phase 4 假設正確，2021/2022 的 `tp_exit%` 應顯著上升。

---

## 實作順序

### Step 0：`src/backtest/explore_night_day.py`（新建）
探索夜盤 vs 日盤波動關係，決定後續 TP 設計方向。

### Step 1：`src/strategies/orb.py`（修改）
根據探索結果，新增對應的 `ORBPhase4Strategy`。

### Step 2：`src/backtest/optimize_phase4.py`（新建）
複製 `optimize_planc_hybrid.py` 架構，加入歷史年度回測（2021–2024）。

### Step 3：`src/backtest/summary_all.py`（修改）
跑完 optimizer 後，將最佳參數加入 `STRATEGIES` dict。

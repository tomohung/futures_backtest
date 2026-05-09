# Proposal: 時序版集中度預測 — 用 t-1 集中度預測 t 振幅

## ID
H083

## Derived From
H080（confirmed）的 follow-up 發現：原研究是「同期相關性」，因方法論限制不能直接實戰；但 follow-up 顯示集中度有 **lag-1 auto-correlation +0.62**，使「t-1 集中度」成為「t 振幅」的可用 prior。

## Trading Intuition

H080 確認集中度與當日振幅有強同期相關 (Q5/Q1 振幅比 +61%)，但「全日集中度」要收盤才知道，無法盤中決策。

兩個追加觀察解開時序問題：

1. **集中度有強 day-to-day 持續性**：`top20_dev_pct` lag-1 auto-corr = **+0.62**，Q5 → 隔日仍 Q5 機率 55%（隨機 baseline 20%）。
2. **t-1 集中度有實質預測力**：`corr(t-1 dev_pct, t 振幅) = +0.18`，Q5/Q1 振幅比仍 **1.36x**（同期 1.61x，衰減 38% 但顯著）。

→ 把 H080 的「同期 indicator」轉為「**時序 predictor**」，盤前即可決策。

進一步實戰設計（user 提出）：**Bayesian update**
- **盤前 prior**：用 t-1 集中度套 H083 的條件期望表 → 設初始 EstHL 倍數
- **盤中 update**：隨開盤後累積即時 top20 share，逐步從 prior 轉移到「累計到當前的 share 估全日」
- **動態調整**：每隔 N 分鐘重算 posterior 振幅期望，更新倍數

本研究 (Phase 1) 只驗證 prior 的預測力；update 邏輯延到 Phase 1.5/2。

## Hypothesis

### H083-A：純 t-1 集中度的振幅預測力
**陳述**：用 `top20_dev_pct[t-1]` 切 5 桶（quintile），t 日 TX 日盤平均振幅 (high-low)/open 隨集中度桶位呈現**單調趨勢**，Q5/Q1 振幅比 ≥ 1.25。

### H083-B：weekday-conditional 預測力（最重要）
**陳述**：在 weekday ∈ {Tue, Wed} 條件下，Q5/Q1 振幅比 ≥ 1.40。其他 weekday 較弱。

### H083-C：對既有 EMA range 的增量價值
**陳述**：把 `range[t]` 對 `ema_range[t-1]` + `top20_dev_pct[t-1]` 做 OLS regression，dev_pct 係數的 t-stat ≥ 2（p < 0.05），代表它對既有平滑指標有獨立增量。

## Expected Distribution

### Phase 1 預期（in-sample）

已知初步觀察：
- pooled corr +0.18, Q5/Q1 = 1.36x
- Tue 1.57x, Wed 1.49x, Thu 1.39x, Mon 1.29x, Fri 1.04x

Phase 1 會嚴格驗證這些是否在 OOS 仍成立、是否在 permutation null distribution 中極端、是否對 ema_range 有增量。

### 預期通過 GATE 的概率
- H083-A pooled：高（樣本大、效應穩定）
- H083-B weekday：中（n 較小、可能有 cherry-picking）
- H083-C 增量：未知（如果 dev_pct 與 ema_range 高度相關，增量 t-stat 可能不顯著）

## Invalidation Condition

**任一不通過則對應子假設不成立**：

### H083-A
- IS: Q5/Q1 振幅比 < 1.25 或非單調
- **OOS**: 在 25% 留出樣本上 Q5/Q1 < 1.20

### H083-B
- IS: Tue 或 Wed 的 Q5/Q1 < 1.40
- **OOS**: Tue 或 Wed 的 Q5/Q1 在留出樣本 < 1.30
- **Permutation**: 對 (lag1_dev, weekday) 雙標籤 shuffle 1000 次，實際 Tue/Wed 的 Q5/Q1 在 null dist 中 percentile < 95%

### H083-C
- OLS 中 dev_pct 係數 t-stat < 2 或 p > 0.05

## Scope

### 樣本期間
2020-12-31 ~ 2026-05-07（1191 個交易日，受 TX 期貨資料限制）

### IS / OOS 切分
- **IS**：2020-12-31 ~ 2024-08-31（約 899 天，75%）
- **OOS**：2024-09-01 ~ 2026-05-07（約 292 天，25%）
- 切點 2024-09 是有意選的：避開 2024-08-05 黑色週一（極端事件）落在 IS 收尾

### 訊號定義
沿用 H080 的 `top20_dev_pct`（N=20 為主訊號）。

```
signal[t] = top20_dev_pct[t-1]   # 昨日收盤後可知
target[t] = (high - low) / open[t]   # 當日 TX 日盤振幅
```

### 預測標的
TX 日盤振幅（high-low）/open，08:45–13:45。

### 方法論限定
- 解開了 H080 的「同期」限制 — 這是真預測，不是同期相關
- 但仍是 **paper trading** 等級訊號，要套到 S001-esthl 還需要 Phase 2 完整回測（含交易成本、滑點、實單規則）
- 不需要 Phase 1.5 即時資料管線即可完成 Phase 1

### 資料管線
**不需新表** — 直接讀 `concentration_index` + `ohlcv_1m`。

## Notes

### 與已有研究的關係
- **H080**（confirmed）：本研究的母假設，提供同期相關證據
- **H081**（active）：Friday 方向訊號，可考慮也用 t-1 預測來解時序限制
- **H082**（active）：Q1 安全日訊號，同樣可考慮 t-1 預測版本
- **H083**（本）：振幅 GATE-2 的時序版

→ 三個衍生研究都受惠於本研究發現的 lag-1 +0.62 auto-corr。如本研究通過 Phase 1，H081/H082 可重新考量是否改寫為 t-1 預測版本。

### Phase 2 候選方向（GATE 通過後另起 plan）
**主目標：S001-esthl 動態倍數修正**

具體做法：
1. **盤前 prior 倍數**：根據 t-1 集中度桶位 + t weekday 從 H083 期望表查 baseline 倍數修正係數 k_prior
2. **EstHL 倍數 = 原 0.618 × k_prior**
3. **可選 Bayesian update（Phase 2 進階）**：
   - 盤中每 30 分鐘抓即時 top20 share（需即時 API）
   - 計算「累計到目前 → 估全日」的 share posterior
   - 更新 k_realtime
   - 倍數 = 0.618 × (w × k_prior + (1-w) × k_realtime)，w 隨時間衰減
   - **這部分需要 Phase 1.5 即時資料管線，獨立工作**

### 為何單獨成立 H083 而非加進 H080
- H080 已 confirmed 並歸檔；新發現不應改 archive 內容
- 「t-1 預測」與「同期相關」是不同方法論（一個有預測力，一個沒），需要不同的 GATE
- 衍生關係單向：H080 → H083，H083 通過後可餵 H081/H082 升級

### 倍數調整公式（暫定，Phase 2 校準）
```
weekday_strength = {Tue: 1.57, Wed: 1.49, Thu: 1.39, Mon: 1.29, Fri: 1.04}
quintile_offset = {Q1: 0.74, Q2: 0.79, Q3: 0.81, Q4: 0.85, Q5: 1.00}

if weekday in {Tue, Wed} and quintile == Q5:
    k = 1.30   # 振幅放大 ~50%
elif weekday in {Tue, Wed} and quintile == Q1:
    k = 0.85
elif weekday == Fri:
    k = 1.0    # 無預測力
else:
    # 線性插值或查條件期望表
    ...

EstHL_multiplier = 0.618 * k
```
（這只是直覺起點；Phase 2 會用 OLS / GBM 等學最佳對應）

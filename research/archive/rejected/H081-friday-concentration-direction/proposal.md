# Proposal: 週五的權值股集中度方向訊號

## ID
H081

## Derived From
H080 Phase 1（distribution）的 1G + 1I 分析

## Trading Intuition

H080 全樣本（pooled）的 GATE-1 方向訊號失敗（5 桶 quintile p_up 首尾 +2.74 pp，未達 8 pp 門檻），但拆 weekday 後發現：

| weekday | Q1 p_up | Q5 p_up | Q5-Q1 (pp) |
|---|---|---|---|
| Mon | 50.88% | 48.89% | -1.99 |
| Tue | 53.85% | 51.02% | -2.83 |
| Wed | 55.81% | 52.00% | -3.81 |
| Thu | 52.08% | 58.14% | +6.06 |
| **Fri** | **48.72%** | **64.71%** | **+15.99** |

**只有週五**有強烈方向 effect — 高集中度週五的當日漲機率 65%（vs 低集中度週五 49%）。其他週天接近零或反向。

可能的微結構解釋：
- **結算前對沖**：週選週三結算，月選週三結算 → 週五是「結算後重新建倉」
- **週末 risk-off**：法人在週五結帳前避免空頭部位
- **退榜的 mean-reversion**：當週權值股集中度高 = 大型股強，到了週五更可能延續

## Hypothesis

當 t = 週五 且 `top20_dev_pct[t]` 落在 Q5（quintile 5，全樣本最高 20% 集中度），則當日 TX 日盤的 `tx_dir = (close - open) / open` 中位數顯著高於：
- (a) 同樣週五但落在 Q1 的 baseline
- (b) 整體週五的 baseline

且漲日機率（p_up）≥ 60%。

## Expected Distribution

樣本：~241 個週五（2020-12-31 ~ 2026-05-07，5 桶 quintile 各 ~48 天）

預期：
- Q5 × Fri p_up ≈ 60–65%（H080 已觀察 64.71%）
- Q1 × Fri p_up ≈ 45–50%（已觀察 48.72%）
- Q5 - Q1 差距：8–18 pp
- 整體週五 baseline p_up ≈ 51%

## Invalidation Condition

任一條件成立則 H081 不成立：
1. **Mann-Whitney U**：Q5×Fri 的 tx_dir 分佈與 Q1×Fri 沒有顯著差異（p > 0.05，alternative='greater'）
2. **Permutation test**：對 weekday label shuffle 1000 次，Q5-Q1 (pp) 的 95% 信賴區間包含 0（即週五效應可能來自隨機）
3. 樣本數不足以支撐統計檢驗（每桶 < 30 天）

## Scope

### 樣本期間
2020-12-31 ~ 2026-05-07（約 1191 個交易日，~241 個週五）

### 訊號定義
沿用 H080 的 `top20_dev_pct = (top20_share - ma20) / ma20 * 100`，N=20。
分桶用 Q5 quintile（top 20%）vs Q1（bottom 20%）。

### 預測目標
**TX 日盤同期**（08:45 開盤至 13:45 收盤的 close/open - 1）

### 方法論限定（同 H080）
🚨 同期相關性 ≠ 預測力。實戰可用性建立在 H080 提到的「核心假設 A」（早盤集中度 ≈ 全日集中度）之上，需 Phase 1.5 累積即時資料才能驗證。

### 資料管線
**不需新表** — 直接讀 `concentration_index`（已建）+ `ohlcv_1m`（既有）。

## Notes

### 為何單獨成立 H081 而不留在 H080
- H080 主結論是「集中度 = 振幅預測器」（GATE-2 路線，方向中性）
- H081 是「特定 weekday 條件下的方向訊號」，是 conditional 的子訊號
- 樣本邊緣（每桶 ~48 天），需要更嚴謹的統計檢驗

### 與既有研究的關係
- **H068 reversal-weekday-effect**：曾發現 weekday 對 reversal 策略有差異
- **H071 tuesday-vol-paradox**：曾發現週二有特殊 vol pattern
- 本研究發現的「週五 effect」是新方向

### Phase 2 候選方向（GATE 通過後）
- **多單入場濾網**：「週五 + Q5 集中度」當作 long-only 進場條件
- **倉位放大**：Q5×Fri 倉位 ×1.5
- **與 H082 互補**：H082 是「Q1 安全日」（多空都安全），H081 是「Q5×Fri 偏漲」（積極方向）

### 為何不直接做 Phase 2 回測
- Phase 1 GATE 用「Mann-Whitney + permutation」嚴格驗證，避免 data snooping（畢竟這是從 25 格中找最強的格子，需要驗證不是 cherry-picking）
- 通過後再規劃 Phase 2 進出場規則

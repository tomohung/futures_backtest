# Proposal: 低集中度 × 特定 weekday 的「安全日」訊號

## ID
H082

## Derived From
H080 Phase 1（distribution）的 1H + 1I 分析

## Trading Intuition

H080 在 5 桶 quintile × 5 weekday = 25 格的細格分析中發現：
**「集中度極低（Q1）+ 特定 weekday」幾乎不會發生大跌**。

| quintile × weekday | n | P(crash) | crash lift vs baseline |
|---|---|---|---|
| **Q1 × Wed** | 43 | **0.00%** | **0.00**（43 天無一次大跌） |
| Q1 × Fri | 39 | 2.56% | 0.185 |
| Q1 × Tue | 52 | 5.77% | 0.416 |
| Q2 × Fri | 51 | 5.88% | 0.425 |
| Q1 × Thu | 48 | 6.25% | 0.451 |
| baseline | 1191 | 13.85% | 1.00 |

「Q1 × Wed」在 43 天樣本內**零次**大跌，相對 baseline 規避 100%。

可能的微結構解釋：
- **資金分散日 = 風險低**：當資金不集中於少數權值股，意味著市場沒有「大型股獨秀」的 bubble 風險
- **週三平靜效應**：H080 1G 顯示週三平均振幅最小（與 Q5×Wed 1.66% 相比 Q1×Wed 0.88%）
- **週五結帳前風險偏好**：週五接近週末，多數人傾向降低波動

## Hypothesis

當 t 屬於以下「安全日」格子之一時，當日 TX 日盤的「大跌事件」（tx_dir < -0.5% 且 tx_range > top tercile）發生機率顯著低於整體 baseline (13.85%)：

- **H082-A**：Q1 × Wed → P(crash) ≈ 0–3%
- **H082-B**：Q1 × Fri → P(crash) ≈ 0–5%
- **H082-C**：(Q1 + Q2) × Fri 合併 → P(crash) ≈ 3–6%（為了增加樣本）

## Expected Distribution

樣本：
- Q1 × Wed: ~43 天
- Q1 × Fri: ~39 天
- (Q1 + Q2) × Fri: ~90 天

預期：
- Q1 × Wed P(crash) 95% Wilson confidence interval 上限 < 8%
- Q1 × Fri 同樣
- (Q1 + Q2) × Fri 同樣
- 三者中位數 mean_dir 都 ≥ 0（不偏空）

## Invalidation Condition

任一條件成立則對應子假設不成立：
1. **Wilson CI 上限 ≥ 13.85%**（baseline）→ 統計上無法拒絕「P(crash) = baseline」
2. **Permutation test**：對 weekday + quintile 雙標籤 shuffle 1000 次，「Q1×Wed 零大跌」在 shuffle 分佈中 percentile < 95%
3. **樣本穩定性**：切兩半（2020-12 ~ 2023-06 vs 2023-07 ~ 2026-05），任一段 P(crash) > 10%

## Scope

### 樣本期間
2020-12-31 ~ 2026-05-07（約 1191 個交易日）

### 訊號定義
沿用 H080 的 `top20_dev_pct`，N=20。
分桶用 Q1 quintile（bottom 20%）。

### 大跌定義
與 H080 1D 一致：`tx_dir < -0.5%` 且 `tx_range > 全樣本 top tercile (1.24%)`

### 預測目標
**TX 日盤同期**

### 方法論限定（同 H080）
🚨 同期相關性 ≠ 預測力。實戰可用性建立在「核心假設 A」之上，需 Phase 1.5 驗證。

### 資料管線
**不需新表** — 直接讀 `concentration_index` + `ohlcv_1m`。

## Notes

### 為何單獨成立 H082 而不留在 H080
- H080 主結論是「振幅 predictor」，未細看「規避大跌」的條件
- H082 是 H080 主分析以外、用 1I 更細格子發現的條件性結論
- 0% P(crash) 是極端值，需要嚴謹的 confidence interval 驗證

### 與 H081 的關係
- H081（週五方向 +）+ H082（週五安全 +）→ Q5×Fri vs Q1×Fri 是互斥的（quintile 不重疊）
- 可以同時運用：Q5×Fri 積極 long、Q1×Fri 防守 long、其他 Fri 觀望

### Phase 2 候選方向（GATE 通過後）
- **入場濾網**：long-only 策略只在「Q1 × Wed」或「Q1 × Fri」進場 → 預期 max DD 大幅降低
- **量身定做**：H082 是「降風險」而非「找方向」訊號，期望值 ≈ 0 但變異數降低
- **與既有 esthl/orb 等策略疊加**：作為 risk-off 條件

### 樣本邊緣警告
- Q1 × Wed n=43：以 binomial 檢驗，P(crash) = 0/43 的 95% Wilson 上限約 8.4%
- Q1 × Fri n=39：P(crash) = 1/39 = 2.56%，Wilson 上限約 13.4%（**接近 baseline，邊緣可接受**）
- 因此 GATE-A（Wed）較強，GATE-B（Fri）邊緣

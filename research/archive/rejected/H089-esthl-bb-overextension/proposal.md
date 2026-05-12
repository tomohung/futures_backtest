# Proposal: EstHL BB Over-extension Filter

## ID
H089

## Derived From
Origin（從 S001 EstHL live 觀察 + S003 Exhaustion 已使用 `BB30_Above` 訊號的啟發）

## Trading Intuition

S001 EstHL 是早盤 ORB 突破做多策略，核心邏輯是「突破 = 動能延續」。但 S003 Exhaustion
反向使用了同一條件：當 30m BB%B(20, open, 2σ) > 1 時，視為「多方力竭」反而做空。

兩者邏輯邏輯上互斥：
- 若 BB%B > 1 真的代表力竭（Exhaustion 已 confirmed 此觀察），
- 則同一時刻發生的 ORB 突破訊號，本質上是「在過度延伸的位階上追多」，
- 應該有顯著偏高的假突破率（hit fixed SL）。

換言之：S003 用來「進場做空」的條件，可能也是 S001 用來「跳過做多」的好濾網。

## Hypothesis

當 EstHL 訊號（ORB long breakout）發生時，若該訊號當下的 30m K BB%B(20, open, 2σ) > 1，
則該筆交易 hit fixed SL（`entry - EmaHL × 0.25`）的機率，會顯著高於 BB%B ≤ 1 的同類訊號。

**量化定義**：BB%B > 1 桶的 SL hit rate − 全樣本 SL hit rate ≥ 10 個百分點（pp）。

## Expected Distribution

### Pool A — Filtered S001 entries（過完 VWAP + MA20 + OR% + NVF + skip Thu/Fri）
- 樣本總量：2020–2025 約 150–250 筆
- BB%B > 1 佔比預期：15–30%（約 25–75 筆）
- 整體 SL hit rate：~30–40%
- BB%B > 1 桶 SL hit rate：≥ 45%（差距 ≥ 10pp）

### Pool B — Raw ORB long breakout（不過濾網）
- 樣本總量：2020–2025 約 500–800 筆
- BB%B > 1 佔比預期：相近
- 用來驗證效果是否來自 BB 本身，而非與其他濾網的交互作用

### 分桶
BB%B 切四桶：`(-∞, 0]`、`(0, 0.5]`、`(0.5, 1]`、`(1, +∞)`

### 跨年度
若濾網真有效，5 年中至少 3 年應觀察到 BB%B > 1 桶 SL hit rate 高於該年整體平均。

## Invalidation Condition

任一條件成立即視為 Rejected：

1. **樣本不足**：Pool A 中 BB%B > 1 桶 < 20 筆（5 年累計）
2. **效果不顯著**：BB%B > 1 桶 SL hit rate 相對全樣本差距 < 10pp
3. **方向不一致**：5 年中僅 ≤ 2 年方向一致（其餘年份 BB%B > 1 桶反而表現較好或持平）
4. **Pool B 反證**：若 Pool A 顯示效果但 Pool B 無效，代表是濾網交互作用，不是 BB 本身的訊號

## Notes

- BB 參數鎖定 `BB(20, open, 2σ)`，與 S003 Exhaustion 完全一致，直接重用 `runner.py` 的 `BB30_Above` column
- 入場時點的 30m bar：使用「entry timestamp 所屬的 30m bar」的 BB%B（不是上一根 30m bar）
- Phase 1 不做回測，只做 SL hit rate 分桶統計
- Phase 2 若 GATE PASS：在 S001 加入「BB30_Above 為 True 時 skip entry」濾網，回測對比 baseline

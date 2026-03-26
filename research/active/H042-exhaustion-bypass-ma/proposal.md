# Proposal: Exhaustion Bypass MA Direction

## ID
H042

## Derived From
S002-reversal + H042 Phase 1 數據（原 BB%B 極端假設轉向）

## Trading Intuition
Reversal 策略使用 5m 120MA 方向作為進場濾網，避免逆勢交易。但當對手方動能已耗盡（Exhaustion）時，MA 方向仍可能指向原趨勢（因為 MA 反應滯後），導致有效的反轉訊號被過濾掉。

Exhaustion 定義（沿用 Reversal 現有邏輯）：
- bear_exhausted：`close <= day_high - EmaHL × 0.5`（價格從高點下跌 50% EstRange，空方動能耗盡 → 有利做多）
- bull_exhausted：`close >= day_low + EmaHL × 0.5`（價格從低點反彈 50% EstRange，多方動能耗盡 → 有利做空）

例如：開盤急殺後反彈超過 50% EstRange（bull_exhausted），但 MA 方向仍向上，想做空卻被 MA 擋住。實際上多方動能已耗盡，反轉做空的條件成熟。

## Hypothesis
當對手方已 exhausted 時，bypass Reversal 策略的 MA 方向檢查，允許逆 MA 方向進場。在此條件下的 Reversal 交易，其勝率與期望值優於未 exhausted 的逆 MA 交易。

## Expected Distribution（Phase 1 初步數據）
46 筆被 MA 擋掉的交易中：
- Exhausted（36 筆）：WR 55.6%、Avg PnL +17.7、Total +638
- Non-exhausted（10 筆）：WR 40.0%、Avg PnL -17.7、Total -177
- 對照標準 Reversal（558 筆）：WR 45.0%、PF 1.32、Total +3,728

## Invalidation Condition
- Exhaustion bypass 後的完整回測 PF < 1.0
- 加入 bypass 後整體策略 PF 顯著下降（< 1.25）
- 勝率低於 45%（低於標準 Reversal 基線）
- 年度表現不穩定（多數年份虧損）

## Notes
- 進出場邏輯完全沿用 Reversal 策略（BB latch + trigger + SatZone exit）
- 差異：當對手方 exhausted 時，BB latch 和 setup 不檢查 MA 方向
- Exhaustion 機制本已存在於 Reversal 策略中（用於放寬 CCD），此處擴展其用途至放寬 MA 方向
- BC zone inside 的 MA bearish 做多（N=9, WR 44%, MFE/MAE 0.68）是唯一虧損子類型，Phase 2 需特別關注

### Phase 1 假設轉向記錄
原假設為「30 分 K BB%B 極端時 bypass MA」，但修正 BB%B 計算（日盤 only、open-based、不 shift）後，BB%B 極端與 MA blocking 的交叉僅 4 筆，不可行。分析 46 筆被擋交易的特徵後，發現 Exhaustion 狀態才是關鍵區分因子。詳見 `results/distribution.md`。

### H044 實盤比對的相關發現
H044 分析了 Reversal 實盤 vs 回測差異（2024/11~2026/03）：
- 48 筆「實盤有做、回測沒做」的交易中，**12 筆是 DIR_BLOCKED**
- 這 12 筆勝率 83%、Total +1,072 pts
- **驗證基準**：H042 Phase 2 完成後，應比對 H044 的 live-only 清單，確認 exhaustion bypass 能捕捉到多少筆

# Proposal: Tuesday Volatility Paradox

## ID
H071

## Derived From
- H029（confirmed）：weekday-effect 確認 EstHL 週五弱、ORBLong 週四弱，但未深入週二
- H068（confirmed）：reversal-weekday-effect 確認週一/週五弱，週二未被特別處理
- H060（rejected）：weekday-volatility 確認週二日盤振幅最高（標準化 0.999）但效應不足以單獨產生 edge

本假設將上述三者交叉：H060 確認的「週二振幅最大」，與 H029/H068 觀察到的「週二績效不如預期」形成矛盾，需要解釋。

## Trading Intuition
台指期日盤週二的平均振幅最大（H060 已驗證），照理說波動越大、突破/反轉策略越容易賺錢。但實盤觀察 EstHL 與 Reversal 的週二績效並未明顯優於其他平均波動較小的日子，反而相對偏弱。

可能解釋：
1. **雙向甩動假說**：週二的大振幅來自 V 型反轉/假突破，而非單向趨勢，導致突破策略追高殺低、反轉策略過早進場
2. **趨勢逆向假說**：週二在 TrendMA/ADX 同向情境下的勝率特別低（趨勢濾網對週二失效）
3. **時段集中假說**：週二的大振幅集中在特定時段（例如尾盤），策略已出場後才發生，無法捕捉

## Hypothesis
在 2019-01-01 至今（樣本約 6+ 年），台指期日盤週二的策略績效（EstHL、Reversal、Exhaustion）相對於週二以外的交易日，呈現以下其中一種特徵：
- (a) 週二進場後的反轉率（MAE/MFE 比值）顯著高於其他星期
- (b) 週二在 TrendMA 同向情境下的勝率顯著低於其他星期
- (c) 週二日內價格路徑曲折度（高低點觸發時間分佈）顯著高於其他星期

## Expected Distribution
Phase 1 預期觀察到：
- EstHL/Reversal/Exhaustion 三策略中，至少兩個的週二 PF 落於該策略所有日子的後 40%
- 週二進場單的 MAE/MFE 比值顯著高於非週二（差距 > 15%）
- 週二日內 H/L 出現時間分佈比其他日子更分散（標準差更大），代表沒有明確主導趨勢

## Invalidation Condition
若 Phase 1 出現以下任一情況，直接 archive：
- 三個策略的週二 PF 與全週中位數差距均在 ±5% 內（無顯著差異）
- 週二樣本數 < 200（無法做 weekday × strategy × regime 的交叉切片）
- 週二弱勢可被既有的 H066/H067 夜盤波動濾網完全解釋（即扣除 NVF 過濾後的週二樣本，績效已與其他日子相當）

## Notes
- 三個策略一起看：EstHL、Reversal、Exhaustion
- 主要績效指標優先順序：PF → 平均單筆 P&L → 勝率
- 用最新數據重跑（避開 H029 當時的 lookback window）
- Phase 1 不修改任何策略參數，純粹分析現象
- 若 Phase 1 確認「週二大振幅雙向甩動」假說成立，Phase 2 才考慮設計濾網或進場條件調整

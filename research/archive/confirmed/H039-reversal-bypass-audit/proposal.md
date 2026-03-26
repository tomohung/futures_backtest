# Proposal: Reversal CCD Bypass Conditions Audit

## ID
H039

## Derived From
H038 的 distribution 階段（BB touch confluence 無效，觸發對現有條件的反思）

## Trading Intuition
Reversal 策略的進場 setup 需要 BB touch + 「CCD 方向正確」，但隨著開發迭代，
已經累積了 4 種條件可以 bypass CCD 要求：

1. **CCD 本身**：CCD_5m > 0（long）/ < 0（short）— 原始條件
2. **Exhaustion**：price moved >= exhaust_fraction of EstRange → 對手方耗盡
3. **Intraday VWAP**（09:30+）：close > intraday VWAP → 多方仍強
4. **2nd BB touch**：bb_count >= 2 → 第二次觸底/頂，不再要求 CCD

這些條件是逐步加入的，每個都有獨立的邏輯基礎，但從未驗證過它們的**邊際貢獻**。
H038 的經驗提醒我們：直覺合理不代表數據支持。需要確認每個 bypass 是否真的
在讓更多「好訊號」進場，還是只是在放寬條件讓更多 noise 進來。

## Hypothesis
在 Reversal 策略的 BB touch 事件中，4 種 CCD bypass 條件的邊際貢獻不均等：
部分條件確實能篩出高品質的額外進場機會，部分可能只是增加了交易次數但未改善期望值。

具體測試：
- 對每個 BB touch 事件，記錄它滿足了哪些 bypass 條件
- 比較「純 CCD 正確」vs「各 bypass 條件獨立觸發」的勝率與期望值
- 找出是否有條件可以移除而不損失績效

## Expected Distribution
- CCD 本身（原始條件）：勝率應為基準線，最穩定
- 部分 bypass 條件（如 exhaustion）：可能有正貢獻（因有物理意義）
- 部分 bypass 條件：可能勝率與隨機無異（邊際貢獻 ≈ 0）
- 如果所有 bypass 條件都有正貢獻，則策略設計合理，不需簡化

## Invalidation Condition
- 所有 4 種條件的勝率與期望值都在統計誤差範圍內無差異 → 可能需要完全不同的方法論
- 或樣本太少（某條件觸發次數 < 20），無法得出有意義的結論
- 或條件之間高度重疊（同一事件同時滿足多個 bypass），無法區分邊際效果

## Notes
- 這不是要「加新條件」，而是要**審計現有條件**，目標是簡化或確認
- 分析需要回到 bar-level，模擬 strategy 的 setup 邏輯，標記每個 BB touch 滿足了哪些條件
- 如果某條件可以移除，需在 Phase 2 做 ablation 回測確認

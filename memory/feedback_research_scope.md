---
name: research_scope_general_over_strategy_specific
description: Phase 2 偏好「市場現象本身」的描述性研究，而非綁定特定策略的 filter 測試
type: feedback
---

當 Phase 1 揭露市場結構性發現（如夜盤波動 → 日盤方向/振幅關係），Phase 2 預設應該繼續描述這個現象本身（如 day session 方向、極值時點、形態類型），而不是直接套到特定策略（如 S001 EstHL）做 filter 測試。

**Why**: User 偏好先把市場現象完整刻畫清楚，再考慮策略應用。直接做 strategy-specific filter 會：
1. 把研究綁死在特定策略，喪失通用洞察
2. 容易過早 narrow scope，遺漏其他可用維度
3. 與 H070 範式不一致（H070 描述性發現本身即為價值，不強行轉策略）

**How to apply**:
- Phase 2 設計時，預設第一階段做 market structure 描述（夜盤 → 日盤 close-open、極值時點、形態、軌跡）
- 策略應用只在 user 明確要求或市場現象足夠 clean 時才做
- 寫 Phase 2 計畫前先問：「這個 Phase 2 在描述現象，還是在驗證策略?」如果答案是後者但 user 沒明確要求，停下來確認

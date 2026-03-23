# Archive: H021 — 從波動潛力日分析衍生的策略方向

## Status
Confirmed

## Summary
基於 H020 潛力日分析，完成現有策略覆蓋分析（646 潛力日，60% 覆蓋率），識別出最大策略缺口為做空能力不足（EarlyTrend DOWN 238 日中 157 日無策略覆蓋）。提出 5 個候選方向並排定優先級，衍生出 H032（SatZone 三情境）和 H033（缺口日研究）。

## Key Evidence
**覆蓋分析（2026-03-23 更新）**：
- 潛力日 646 日中 40%（260 日）完全未被任何策略覆蓋
- 未覆蓋日幾乎全是 DOWN + 極端波動（含 2021-05-12 range 9.11%、2024-08-05 range 6.60%）
- EstHL 潛力日均 PnL +63 pts vs 非潛力日 +0 pts
- ORBLong 潛力日均 PnL +41 pts vs 非潛力日 -14 pts

**最大缺口 — 做空能力**：
- EarlyTrend DOWN 238 日，Reversal 僅覆蓋 34%（81 日），157 日無策略
- DOWN 日 oc% = -0.76%，方向明確
- 未覆蓋 UP 日（67 日）與已覆蓋 UP 日特徵幾乎相同，非系統性遺漏

**候選策略可行性**：
- E（早盤做空）：最高優先，130+ 日樣本，需全新進場邏輯（E1 缺口竭盡 / E2 BB 轉折）
- A（持倉延伸）：中等，187 日已覆蓋 UP 的邊際改善
- B（午盤反轉）：僅 23 日樣本
- C（LateTrend）：僅 21 日樣本
- D（Spread 區間）：事前無法判定，與趨勢策略衝突

## Why Confirmed
覆蓋分析成功識別了策略組合的結構性缺口（做空能力），並產出可行的研究方向排序。分析框架和數據為後續假設（H032、H033）提供了堅實基礎。

## Derived Hypotheses
- **H032-satzone-scenarios**：SatZone 觸碰後三情境機率統計（策略 F 基礎）
- **H033-gap-day-study**：缺口日研究（策略 E1 基礎）
- 待建立：Reversal DOWN 漏進場原因分析
- 待建立：E1/E2 規則定義與回測（依賴 H033）
- 待建立：策略 A 持倉延伸（優先級最低）

## Links
- Spec：research/archive/confirmed/H021-strategy-candidates-from-volatility/spec.md

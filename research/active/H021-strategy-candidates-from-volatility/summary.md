# Archive: H021 — 從波動潛力日分析衍生的策略方向

## Status
Inconclusive

## Summary
基於 H020 潛力日分析結果，提出 5 個候選策略方向（A: EarlyTrend 持倉延伸、B: 午盤反轉、C: LateTrend 二次進場、D: Spread 區間、E: 早盤做空），並完成 Step 0 覆蓋分析。發現最大缺口是做空能力不足（EarlyTrend DOWN 238 日中僅 81 日被 Reversal 覆蓋），但所有候選方向均停留在概念/探索階段，未進入回測。

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
- E（早盤做空）：最高優先，130+ 日樣本，但需全新進場邏輯（E1 缺口竭盡 / E2 BB 轉折）
- A（持倉延伸）：中等，187 日已覆蓋 UP 的邊際改善
- B（午盤反轉）：僅 23 日樣本
- C（LateTrend）：僅 21 日樣本
- D（Spread 區間）：事前無法判定，與趨勢策略衝突

## Why Inconclusive
所有 5 個候選方向均停留在 Step 0 / 概念階段，未產出可回測的策略規則。最有潛力的做空方向（E1/E2）需要缺口日研究和全新進場邏輯作為前提，尚未開始。其餘方向因樣本不足（B: 23 日、C: 21 日）或事前不可判定（D）而暫緩。

## Derived Hypotheses
- 策略 E1：缺口竭盡反轉（開高破低 A 轉做空 / 開低破高 V 轉做多）
- 策略 E2：BB 轉折（30 分 K BB 極值確認做空/做多）
- 策略 F：SatZone 觸碰後 credit spread（選擇權）
- 缺口日獨立研究（缺口頻率、補缺口率、缺口大小與 range 的關係）

## Links
- Proposal: specs/strategies/2026-03-22-strategy-candidates-from-volatility.md

# Proposal: VSA 無供應 — 趨勢回檔賣壓枯竭進場

## ID
H054

## Derived From
H050 Phase 0 批次 2 評估（C1 候選）

## Trading Intuition
上升趨勢中出現窄幅低量的回檔 K 棒（VSA "No Supply"），代表賣壓已經枯竭，多方準備重新接手。當下一根 K 棒收漲確認時進場做多，搭上趨勢延續。反向的 "No Demand"（下降趨勢中窄幅低量的反彈）同理做空。

這是經典的威科夫（Wyckoff）量價分析概念，原始設計為個股日線，H050 初步測試在台指期 5mK 上表現突出。

## Hypothesis
在 5m K 的 20MA 上升趨勢中，出現窄幅（< RangeMA × 0.5）+ 低量（< VolMA × 0.5）的收跌 bar，且下一根收漲時做多持有 60 分鐘，有正期望值（PF > 1.5）。

## Expected Distribution
- H050 初步結果：PF=2.00（N=412, 0.5x/0.5x）、WR=63.3%
- No Demand 反向做空：PF=2.75（N=298）
- 搭配 EstHL 出場策略後績效可能更好（捕捉趨勢延續到 SatZone）
- 信號頻率高（每日多次觸發），需要篩選最佳進場時機

## Invalidation Condition
- IS/OOS 分裂：IS PF > 1.5 但 OOS PF < 1.0
- 加入交易成本（滑價 + 手續費）後 PF < 1.2
- 信號過於頻繁導致過度交易（每日 > 5 筆有效信號）
- 與現有策略高度重疊（進場時段/方向 > 70% 重疊）

## Notes
- H050 測試用 60 分鐘固定持有，Phase 1 需測試不同出場方式
- 5mK 的 20MA = 100 分鐘 MA，較短期；可測試更長 MA
- Range 和 Volume 的門檻組合需要敏感度分析
- 原始 VSA 概念還有 "Test"、"Stopping Volume" 等延伸型態
- 需確認信號是否集中在某些時段（如開盤後 vs 午盤）

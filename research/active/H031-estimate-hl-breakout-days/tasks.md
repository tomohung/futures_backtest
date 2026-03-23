# Tasks: EstimateHL 趨勢爆發日與未觸及日分析

## Phase 1: Distribution Research

- [x] 統計三類日分佈（大幅突破 181 / 正常觸及 643 / 完全未觸及 427）
- [x] 計算各組 HL_ratio、Vol_ratio、OR_pct 中位數
- [x] 確認 OR 開盤區間無區分力（三組幾乎相同）
- [x] 確認成交量對未觸及日無區分力
- [ ] 放量係數（cum_vol / expected_vol）最佳 slot 分析
- [ ] 趨勢爆發日觸及 SatZone 後繼續走的比例（50/100/200 點）
- [ ] EstHL 何時可靠預測低振幅日

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** [TODO] — 初步分佈已完成，但改善方向的可行性尚待驗證。趨勢爆發日核心問題是 EMA(20) 反應慢導致系統性低估；未觸及日是市場不配合的情境。需先完成基本 SatZone 策略驗收後再回來處理。

---

## Phase 2: Backtest

- [ ] 趨勢爆發日：方向 A（盤中放量偵測 + 動態 SatZone 目標）
- [ ] 趨勢爆發日：方向 B（觸及 SatZone 後 N 根觀察期）
- [ ] 趨勢爆發日：方向 C（EstHL 動態更新作為觸發條件）
- [ ] 趨勢爆發日：方向 D（ATR-based trailing stop）
- [ ] 完全未觸及日：方向 A（早盤 EstHL/EmaHL < 0.75 → 固定時間出場）
- [ ] 完全未觸及日：方向 B（盤中即時 HL_ratio 監控）
- [ ] 完全未觸及日：方向 C（前一日振幅輔助條件）

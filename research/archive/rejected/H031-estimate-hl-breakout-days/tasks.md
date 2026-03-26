# Tasks: EstimateHL 趨勢爆發日與未觸及日分析

## Phase 1: Distribution Research

- [x] 統計三類日分佈（大幅突破 181 / 正常觸及 643 / 完全未觸及 427）
- [x] 計算各組 HL_ratio、Vol_ratio、OR_pct 中位數
- [x] 確認 OR 開盤區間無區分力（三組幾乎相同）
- [x] 確認成交量對未觸及日無區分力
- [x] 放量係數（cum_vol / expected_vol）最佳 slot 分析 → 最佳 slot 13:15（太晚），10:00 前 sep < 0.4
- [x] 趨勢爆發日觸及 SatZone 後繼續走的比例 → 90% >= 100 點，中位數 199 點
- [x] EstHL 何時可靠預測低振幅日 → 無法預測（F1=0.259），untouched 日 EstHL 反而偏高

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** PASS — 爆發日無法事前預判（放量訊號太晚、EstHL 無法預測），但觸及 SatZone 後續行空間顯著（中位數 0.79 × EmaHL，83% >= 0.5 × EmaHL）。收斂為部位分割問題：觸及 SatZone 時分批出場 + trailing stop，透過 EV 優化取代預判。

---

## Phase 2: Backtest — 分批出場 EV 優化

### 設計
- 觸及 SatZone 時出一部分，留一部分用 trailing stop
- Trailing stop 距離：0.3 × EmaHL（固定，不優化）

### 測試組合（僅 3 組，不做連續參數搜尋）
- [x] A：100/0 — baseline ✅
- [x] B：50/50 — IS PASS, OOS FAIL（2025 -0.014%）→ REJECTED
- [x] C：40/60 — IS PASS, OOS FAIL（2025 -0.017%）→ REJECTED

### 判定標準
- 分批出場的 EV（每筆平均損益%）必須在 2022~2025 **每年都 >= baseline**
- 逐年一致才算 confirmed，不靠某一年的大行情拉高整體

### Out-of-sample
- In-sample：2022~2024（決定最佳比例）
- Out-of-sample：2025~2026（驗證，不回頭改）

### 已放棄方向（Phase 1 排除）
- ~~方向 A（盤中放量偵測）~~：separation < 0.4 at 10:00，53% 觸及已發生
- ~~方向 C（EstHL 動態更新）~~：untouched 日 EstHL 反而偏高，無預測力
- ~~未觸及日改善（方向 A/B/C）~~：EstHL 量驅動，無法預測量正常但波動壓縮的日子

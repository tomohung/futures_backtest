# Tasks: STARC 下軌觸及後反轉做多

## Phase 1: Distribution Research

- [x] 確認 STARC 下軌觸及的日期與市場背景
- [x] IS/OOS 分年度反轉率與報酬
- [x] 參數敏感度（SMA 6/10, ATR 10/14/15, 倍數 1.5/2/2.5）
- [x] 確認上軌觸及無反轉效果（排除雙向對稱性）
- [x] 與 S003 Exhaustion 的信號日重疊率
- [x] 次日盤中的最佳進場時機（開盤做多 vs 等回檔）

---
### GATE
**問題：下軌反轉效果是否穩健？**

- IS/OOS 反轉率都 > 60%？
- 上軌反轉率 < 55%（非對稱性確認）？
- 參數穩定（微調不翻轉）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義日盤進出場規則（開盤做多 + SatZone 出場？）
- [ ] IS/OOS 回測
- [ ] 與 S003 Exhaustion 的互補性分析
- [ ] Walk-forward 驗證

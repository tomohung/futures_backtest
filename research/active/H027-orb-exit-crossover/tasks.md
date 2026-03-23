# Tasks: 出場策略交叉實驗

## Phase 1: Distribution Research

- [x] 比較 EstHL 與 ORBLong 的年度績效差異
- [x] 識別差異可能來自出場機制而非進場機制

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。兩策略年度表現互補明顯（EstHL 早年優、ORBLong 近年優），交叉組合有望取長補短。

---

## Phase 2: Backtest

- [x] 方向 A 實作：`EstHLEntryORBLongExitStrategy`
- [x] 方向 A TP 倍數測試（x1.5 / x2.5 / x3.0 / x4.0）— x3.0 六年均無虧損最穩定
- [x] 方向 A 進場窗口測試（09:05 vs 09:15）— 09:15 總計多 +608 點
- [x] 方向 A 最終結果：tp=3.0, entry_end=09:15, 總損益 +4,221
- [x] 方向 B 實作：`ORBLongWithEstHLExitStrategy`
- [x] 方向 B 回測 — 失敗（SatZone 不適用於晚進場）
- [x] 三策略綜合比較（EstHL / 方向A / ORBLong）
- [x] 結論：方向 A 定位在穩定性與絕對報酬之間，適合保守配置

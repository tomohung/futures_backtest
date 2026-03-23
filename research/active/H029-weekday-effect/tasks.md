# Tasks: 星期效應分析與 Weekday Filter

## Phase 1: Distribution Research

- [x] 日盤波動 x 星期統計（平均波動%）
- [x] 各星期市場動態分析（法人行為、結算效應）
- [x] ORBLong 各星期績效分析
- [x] EstHL 各星期績效分析
- [x] OR% x Weekday 交叉分析（ORBLong + EstHL）
- [x] 結算日效應分析（普通週三 vs 月結算週三）
- [x] 週五結算特性分析

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。週四對 ORBLong 是致命傷（PF 0.87），週五對 EstHL 是致命傷（PF 0.97），效果穩定。進入 Filter 方案比較。

---

## Phase 2: Backtest

- [x] ORBLong Filter 方案比較（A/B/C/D/E）
- [x] EstHL Filter 方案比較（A/B/C/D）
- [x] 年度損益比較（方案 A vs C）
- [x] 結論：ORBLong 維持 `thu_or_pct_min=0.7`，EstHL 維持 `skip_thu + skip_fri`
- [x] 已整合至現行策略參數

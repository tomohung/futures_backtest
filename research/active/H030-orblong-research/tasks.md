# Tasks: ORBLong 策略重新研究

## Phase 1: Distribution Research

- [ ] A. Regime 指標交叉分析（range_pct / ER / swing_count / ATR% / ADX 四分位 x ORBLong 勝率）
- [ ] A. Point-biserial correlation（指標 vs win/loss）
- [ ] A. 與 EstHL 的 regime 敏感度比較
- [ ] B. ORBLong x EstHL 重疊分析（overlap rate、損益相關性、互斥日績效）
- [ ] C. Weekday 效應百分比化（pnl_pct）
- [ ] C. 週四 x OR% 交叉、週四/五 x regime 交叉

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** [TODO] — 待完成探索分析後決定

---

## Phase 2: Backtest

- [ ] D. 實作 `ORBLongEstRangeStrategy`（進場 ORBLong + 出場 SatZone）
- [ ] D. 新增 `load_data_for_orblong_estrange()` 合併兩邊資料欄位
- [ ] E. 參數網格回測（sl_ema_fraction x sat_fraction x force_exit_minute x entry_end_minute）
- [ ] E. IS/OOS 切分驗證（避免五維網格過度擬合）
- [ ] 與現行 ORBLong baseline 比較（PF 2.33, +4,970 pts）
- [ ] 與 EstHL 的 daily correlation 檢驗（目標 < 0.3）

# Tasks: L1-reset 同相位再進場

## Phase 1: Distribution Research

- [x] 正式化 causal 偵測器（L1-reset 狀態機）→ explore.py，逐日掃 2021–2026 全部進場，標記每筆
      reentry_idx（同相位第幾次）+ entry_min + 同向序數
- [x] 統計：具 ≥1 次 L1-reset 再進場的交易日數、多/空各別 N、每相位再進場次數分佈
- [x] 「同向再進場」整體拆解：H126 跨相位 vs H130 同相位(L1-reset) 各佔比
- [x] 零策略 forward excursion：第 1 次 vs L1-reset 後再進場，碰 L3/L4/L5 比率 + MFE/MAE
- [x] **虛無對照**：時間配對 / 同為趨勢日第一次 / 條件期望，檢驗增益非純 selection
- [x] **overfit 穩健性**：leave-6/24-out、逐年/單日 P&L 集中度（是否少數天貢獻絕大多數）
- [x] 分時段（09:30/10:30/11:30 閘）看 reach 衰減
- [x] 視覺化關鍵分佈圖

---
### GATE
**問題：分佈結果是否支持進入回測？**

- L1-reset 再進場樣本數是否足夠？（**門檻待 Phase 1 給實際 N 後再定**）
- 第 2 次（L1-reset 後）reach/賠率是否顯著優於第 1 次 / 時間配對基準，且非純 selection？
- 是否 overfit 到 6/24（單日/少數天驅動）？
- data snooping 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 進場規則：L1-reset 後再進場（沿用 detect_day 5MA 站回相位）
- [ ] 停損 / 目標：沿用 H126 結論起手（alpha=1.0 錨點、目標 L3/L4/L5/trail）做敏感度
- [ ] 對照組：同窗「第 1 次」baseline，量化 L1-reset 再進場的增量
- [ ] 設定回測參數（手續費 3pt、滑價）
- [ ] in-sample / out-of-sample / walk-forward / 參數敏感度（PF + 連敗 + drawdown）
- [ ] cutoff / reset 門檻（L1 vs 其他）敏感度

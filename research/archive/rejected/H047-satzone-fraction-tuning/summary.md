# Archive: SatZone Fraction 策略別調校

## Status
Rejected

## Summary
測試將 SatZone 目標距離從固定 1.0 × zone_distance 改為 fraction × zone_distance（0.80~0.95），分別對三個 live 策略（S001-esthl, S002-reversal, S003-exhaustion）調校。Phase 1 分佈探索顯示降低 fraction 提高 touch rate 且估計 EV 改善，但 Phase 2 完整回測未能通過逐年一致性檢驗。

## Key Evidence
- **S001 (f=0.95):** IS 總量 +2,863 vs baseline +2,464（+16%），但 2022 年（-0.7 pts）和 2025 年（-1.0 pts）微幅低於 baseline，未通過嚴格一致性
- **S002:** 降低 fraction 導致 `_satzone_reached` 更早觸發，IS 交易數從 324 驟降至 152（f=0.80）；即使取消 entry-blocking，OOS 仍明確劣化
- **S003:** 樣本不足（N=38-39），各 fraction 差異在噪音範圍，OOS 方向錯誤
- 補充測試取消 `_satzone_reached` 後，S002 交易數恢復但新增交易品質不高，結論不變

## Why Rejected
1. 嚴格一致性檢驗（IS 期間每年 EV >= baseline）未通過，三個策略全部失敗
2. Phase 1 估計過於樂觀：遺漏了 entry-blocking 副作用，且假設出場在 target 附近與實際 5MA cross 出場不符
3. 降低 SatZone 目標本身沒有穩定的邊際效益

## Derived Hypotheses
- H0XX: **S001 Trailing 改用 SatZone Phase 2 啟動** — f=0.95 觸及率提高但 5MA 出場可能太慢，改用更緊的 trailing 可能改善出場精度

## Links
- Proposal: proposal.md
- Distribution: results/distribution.md
- Backtest: results/backtest.md
- Exploration script: explore.py
- Backtest script: backtest.py
- Supplementary script: backtest_no_satreach.py

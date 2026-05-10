# Tasks: 加入廣度指標補強 H084 指標集

## Phase 0: ETL 前置（與 task #11 相同工作）

### Step 0.1：stock_day / market_breadth backfill
- [ ] 確認 src/etl/download_stock_market.py 在 delay=4-5s 下不會被 rate-limit（參考 H084 margin 經驗）
- [ ] 背景執行 backfill 2010-01-01 ~ today（~4000 個交易日 × 3 sources × ~5s delay = 16+ 小時）
- [ ] parse_stock_market.py 全量入庫
- [ ] 驗證 stock_day 涵蓋上市 + 上櫃，2010+ 連續

### Step 0.2：候選廣度指標建置
- [ ] `breadth_adv_dec` = 漲家 / 跌家（market_breadth）
- [ ] `breadth_adv_dec_cum` = 累積（漲家 - 跌家）
- [ ] `new_lows_52w` = 個股當日收盤 ≤ 252日最低 的家數
- [ ] `new_highs_52w` = 個股當日收盤 ≥ 252日最高 的家數
- [ ] `new_high_low_diff` = highs - lows
- [ ] `value_concentration_top20` = top 20 個股成交額 / 全市場（與 H080 重複）
- [ ] 輸出 results/breadth_indicators.csv

---

## Phase 1: 與 H084 指標集合併分析

### Step 1.1：合併 indicators
- [ ] 把 breadth_indicators 加進 H084 的 indicators.csv（或單獨產 H087 版）
- [ ] 重跑 H084 的 percentile_correlation.py 與 event_study.py

### Step 1.2：命中率與相關性檢查
- [ ] 對 21 個 Tier B/C 事件 trough，計算每個廣度指標的百分位
- [ ] 計算與現有 4 軸（VIX_pct、z 125MA、margin_drop_60d、econ_score）的 Pearson r
- [ ] 識別「命中率 ≥ 60% 且最大 |r| < 0.6」的廣度指標

### Step 1.3：合成 score 提升驗證
- [ ] 把通過篩選的廣度指標加進 H085 的合成 score 重跑
- [ ] 比較 forward-return 表現（如果 H085 已完成）

---

### GATE

**問題：廣度指標能否提供 H084 之外的非冗餘軸？**

通過條件（皆需成立）：

- [ ] ≥ 1 個廣度指標命中率 ≥ 60%
- [ ] 該指標與 H084 4 軸所有 |r| < 0.6
- [ ] H085 加入該指標後 forward-return 提升（如已執行）

**決定：**
- [ ] 通過 → 把廣度指標納入 H085 / 後續策略指標集
- [ ] reject → H084 4 軸已足夠，廣度不增加價值

---

## 注意事項

- 本假設**強依賴 stock_day ETL backfill**，如果該背景任務未完成就無法執行
- 如果 ETL 太慢（10+ 小時），可考慮先做 2020+ 的子集驗證概念
- 與 H079（漲停萎縮溫度計）是相鄰研究，可能會發現重疊結論

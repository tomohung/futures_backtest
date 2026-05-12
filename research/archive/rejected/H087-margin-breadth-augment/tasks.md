# Tasks: 加入廣度指標補強 H084 指標集

## Phase 0: ETL 前置（與 task #11 相同工作）

### Step 0.1：stock_day / market_breadth backfill ✅
- [x] delay=1 可以完跑、無 rate-limit（H084 的 4-5s 經驗對這幾個端點過保守）
- [x] backfill 2010-01-01 ~ 2026-05-11，實跑 ~2.5h
- [x] parse_stock_market.py 全量入庫
- [x] 驗證資料完整性：發現並修正 TWSE API canned-data 污染（24 個日期）
  - 12 個 echo 日期 force re-download 拿到真實資料
  - 1 個日期（2017-12-18）TWSE 端點永久壞掉、quarantine 為 `.canned_bad`
  - 2 個公休日（2015-05-01、2017-10-10）正確標記 non_trading
- [x] 最終 coverage：market_breadth TWSE=3989 / TPEX=3990；stock_day=6,511,875 列（2010-2026 每年都齊）

### Step 0.2：候選廣度指標建置 ✅
- [x] `breadth_adv_dec` = 漲家 / 跌家（TWSE+TPEX 合計）
- [x] `breadth_adv_dec_cum` = 累積（漲家 - 跌家）— McClellan-style
- [x] `new_lows_52w` = 個股當日收盤 ≤ 252日最低 的家數
- [x] `new_highs_52w` = 個股當日收盤 ≥ 252日最高 的家數
- [x] `new_high_low_diff` = highs - lows
- [x] `value_concentration_top20` = top 20 個股成交額 / 全市場
- [x] `value_per_stock` = 全市場成交額 / 有成交家數（額外加的分散度指標）
- [x] 輸出 `results/breadth_indicators.csv`（3990 行 × 7 indicators，腳本：`build_breadth_indicators.py`）

---

## Phase 1: 與 H084 指標集合併分析 ✅

### Step 1.1：合併 indicators ✅
- [x] H087 用 `percentile_correlation_with_breadth.py` 合併 H084 9 軸 + H087 7 廣度軸
- [x] 重跑命中率 + Pearson 相關矩陣

### Step 1.2：命中率與相關性檢查 ✅
- [x] 21 個 Tier B/C 事件 trough 的百分位（16 個有廣度資料，5 個 2008-2010 缺）
- [x] 計算與 H084 4 軸 Pearson r
- [x] 找出 4 個通過 GATE 1+2 的指標：adv/dec、new lows 52w、high-low diff、new highs 52w

### Step 1.3：合成 score 提升驗證 ✅
- [x] 用 `extend_composite.py` 把 3 個最強廣度指標加進 H085 comp_z
- [x] 結果：**每加一軸 forward-return 都下降**（+250d median 32.74% → 24.50%, win rate 75% → 57%）

---

### GATE 結果：REJECT

**問題：廣度指標能否提供 H084 之外的非冗餘軸？**

通過條件（皆需成立）：

- [x] ≥ 1 個廣度指標命中率 ≥ 60%（4 個通過）
- [x] 該指標與 H084 4 軸所有 |r| < 0.6（4 個通過）
- [ ] **H085 加入該指標後 forward-return 提升**（❌ 顯著下降）

**決定：**
- [ ] 通過 → 把廣度指標納入 H085 / 後續策略指標集
- [x] **reject → H084 4 軸已足夠，廣度不增加 panic detection 價值**

### Derived Hypothesis: H088

廣度指標在 Tier C 事件 hit rate ~100%（H085 漏接的場景）。
可考慮做「Tier C 專用獨立廣度 trigger」（不和 VIX/margin 混合），補 H085 沒蓋到的標準回檔。
（先決條件：確認 Tier C 進場有正期望，待 H088 研究）

---

## 注意事項

- 本假設**強依賴 stock_day ETL backfill**，如果該背景任務未完成就無法執行
- 如果 ETL 太慢（10+ 小時），可考慮先做 2020+ 的子集驗證概念
- 與 H079（漲停萎縮溫度計）是相鄰研究，可能會發現重疊結論

# Tasks: 廣度 + 漲停成交額作為市場溫度計

## Phase 0: 資料準備（前置作業）

- [ ] 建立 `data/raw_market/` 目錄存放 TWSE/TPEX 原始 JSON
- [ ] 撰寫 `src/etl/download_stock_market.py`：下載 TWSE `MI_INDEX` + TPEX `highlight`（市場彙總），與 `STOCK_DAY_ALL` + `dailyQuotes`（個股日行情，含漲跌停價）
- [ ] 撰寫 `src/etl/parse_stock_market.py`，建立 DuckDB 表：
  - `market_breadth`（trade_date, market, total_count, up_count, down_count, unchanged_count, total_value）
  - `stock_day`（trade_date, market, symbol, open, high, low, close, volume, value, limit_up_price, limit_down_price）
- [ ] 抓取 2024-01-01 ~ 2026-04-30 區間（約 570 個交易日）
- [ ] 驗證資料完整性（缺漏日、零成交額、價格異常）

---

## Phase 1: Distribution Research

### 共同前置
- [ ] 載入台指期日 K（從 `ohlcv_1m` aggregate 到日盤 08:45–13:45）
- [ ] 計算每日衍生指標：
  - `up_ratio` = 上漲家數 / 總家數（兩市合併）
  - `index_return` = 加權當日報酬
  - `limitup_count` = 收盤=漲停價的家數
  - `limitup_value_sum` = 漲停股當日成交額總和
  - `limitup_value_ratio` = limitup_value_sum / total_value
  - 對應跌停指標

### H079-A：廣度背離
- [ ] 定義「強廣度背離日」：`index_return > 0` 且 `up_ratio < 0.30`
- [ ] 統計樣本數、佔比，並列出歷史日期
- [ ] 計算背離日 vs 對照組的隔日／未來 5 日台指期報酬分佈
- [ ] Mann-Whitney U test 檢定中位數差異
- [ ] 視覺化：分佈直方圖、累積報酬曲線

### H079-B：漲停成交額象限
- [ ] 用 `limitup_count` 和 `limitup_value_ratio` 切四象限（用滾動 1 年中位數作門檻）
- [ ] 統計每象限的天數佔比
- [ ] 計算每象限的後續 5/10/20 日台指期報酬分佈（中位數、25/75 分位、最大回撤）
- [ ] Kruskal-Wallis 檢定四象限差異
- [ ] 視覺化：象限熱圖、各象限報酬箱型圖

### H079-C：漲停萎縮事件
- [ ] 計算 `limitup_count_ma7`、`limitup_value_ratio_ma7`
- [ ] 定義「萎縮事件」：兩指標同時 < 滾動 1 年 20 分位數，連續 ≥ 5 個交易日
- [ ] 列出歷史所有萎縮事件（含起訖日）
- [ ] 對每個事件，計算事件後 20 日內的：
  - 最大跌幅
  - 是否出現「單日 < -2%」
  - 累積報酬
- [ ] 計算條件機率 vs 基準機率（無事件期間隨機抽樣）
- [ ] 列舉並對齊前輩提到的 2 個事件（2024/7、2025/3）

---

### GATE
**問題：分佈結果是否支持進入回測？**

逐個子假設判定（任一通過即可進入 Phase 2）：

- [ ] **A**：強背離日 ≥ 30 筆，且隔日報酬中位數 Mann-Whitney p < 0.1
- [ ] **B**：四象限樣本均 ≥ 30 筆，且後續報酬中位數方向符合假設
- [ ] **C**：萎縮事件 ≥ 5 筆，且大跌條件機率 ≥ 基準機率 × 1.5
- [ ] 是否有明顯 data snooping 疑慮（門檻是否過度擬合到 2024/7、2025/4 兩事件）？

**決定：** [ ] 繼續 Phase 2　[ ] 補齊歷史資料後重跑　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過後規劃）

### 共同方向
- [ ] 將通過的子假設轉成台指期進場/濾網規則
- [ ] 候選用法：
  - **A 類**：強背離日後做空台指期（隔日開盤進場、日盤收盤出場）
  - **B 類**：作為既有策略（ESThL、Reversal、ORB）的 regime filter
  - **C 類**：萎縮事件期間降低部位 / 暫停做多
- [ ] 設定回測參數（手續費 2 點、滑價 1 點）
- [ ] 執行 in-sample（2024-01 ~ 2025-06）
- [ ] Out-of-sample 驗證（2025-07 ~ 2026-04）
- [ ] 補齊歷史資料（2018-01 ~ 2023-12）做 walk-forward
- [ ] 參數敏感度（門檻百分位、連續日數）

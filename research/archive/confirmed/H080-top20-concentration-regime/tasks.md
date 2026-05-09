# Tasks: 前 20 權值股成交集中度的行情分類

## Phase 0: 資料管線建置

- [ ] 設計 `top_lists` 表 schema（list_month / rank / symbol / name / monthly_value）
- [ ] 寫 `src/etl/build_top_lists.py`：從 stock_day 算每月個股成交金額加總，取 top 20 → top_lists
- [ ] 設計 `concentration_index` 表 schema（寬表，含 N=1/5/10/20 共 20 欄指標）
- [ ] 寫 `src/etl/build_concentration_index.py`：join stock_day + market_breadth + top_lists → concentration_index（一次算 4 個 N）
- [ ] 驗證 ETL：抽樣 5 個交易日手動核對（含結算日、清單變動日、近期日）
- [ ] 確認 N=1 8 年內幾乎都是 2330（容錯記錄）

## Phase 1: Distribution Research

### 1A. 訊號穩定性檢視
- [ ] 計算每月清單變動數（top 20 的進出榜頻率）並圖示
- [ ] 計算 `top20_share` 全期分佈（min/max/mean/median + 月趨勢，反映台積電權重上升）
- [ ] 計算 `top20_dev_pct` 全期分佈（應為 0 為中心的鐘形，std 約 5–15%）
- [ ] 同步輸出 N=1/5/10 的同類分佈，比較形狀差異

### 1B. 邊際分析（5 桶 quintile，4 個 N 各跑一次）
- [ ] 對每個 `N ∈ {1, 5, 10, 20}` 切 5 桶 → 每桶：漲日機率、平均方向、平均振幅
- [ ] 視覺化：5 桶 vs 漲日機率（4 條線疊在一張圖比較哪個 N 訊號最強）
- [ ] 視覺化：5 桶 vs 平均振幅
- [ ] 計算首尾桶差距，記錄 N=20 是否達 GATE 1 (8pp) / GATE 2 (30%)
- [ ] 標記其他 N 的最佳結果（衍生假設候選）

### 1C. 9 宮格主分析（用 N=20，3 桶 × 9 行情格 = 27 格）
- [ ] 切 3 桶 `top20_dev_pct` + 9 行情格（方向 × 振幅）
- [ ] 對每格計算：發生機率、相對 baseline lift、樣本數
- [ ] Chi-square 檢定（27 格 vs 獨立性虛無假設）
- [ ] 找出 lift ≥ 80% 且 p < 0.05 的格子，記錄是否達 GATE 4
- [ ] 對 N=5/10 重複 27 格分析（可選，若 1B 顯示小 N 訊號更強）

### 1D. 大跌規避分析（H080-D，用 N=20）
- [ ] 定義「大跌日」：方向 < -0.5% 且振幅 > top tercile
- [ ] 計算各集中度桶的大跌日機率，比對 baseline，記錄是否達 GATE 3 (lift ≥ 50%)

### 1E. 結構性事件檢視
- [ ] 標記清單進出榜事件（2018 國巨、2021 長榮、2024 廣達/緯創等），輸出 list_changes.csv
- [ ] 確認 1B/1C 結論在「移除清單變動月份」後是否仍成立（避免單一事件主導）

### 1F. 與既有訊號的相關性
- [ ] 計算 `top20_dev_pct` 與 H079 的 `up_ratio`、`lu_value_ratio` 的相關性
- [ ] 也計算 `top1_dev_pct` 與 H079 訊號的相關性（看獨立性是否更高）
- [ ] 檢查冗餘：若任一 N 與 H079 訊號 corr > 0.7，記錄並評估增量價值

### 1G. Weekday 子分析（條件性，主訊號顯著才做）
**前置條件**：1B 或 1C 主分析已找到 ≥ 1 個顯著訊號
- [ ] 對「最強訊號」（5 桶上的方向或振幅 lift）按 weekday 拆分：每 weekday × 5 桶 = 25 格，每格 ~80 天
- [ ] 比對：主訊號在哪一天最強 / 最弱，是否與 H068 / H071 等既有 weekday 結論呼應或衝突
- [ ] 不對 27 格做 by-weekday（樣本太薄，每格 ~14 天無統計力）
- [ ] 若 weekday 差異顯著，記錄為衍生假設

### 1H. distribution.md 撰寫 + GATE 評估
- [ ] 將 1A–1G 結果整合進 `distribution.md`
- [ ] 顯眼處標記方法論限制（同期相關 ≠ 預測、近似 vs 嚴格 TAIEX 權重）
- [ ] 填寫 GATE 結論
- [ ] 列出衍生假設候選（如 H081 聚焦 top5 / top1）

---
### GATE
**問題：分佈結果是否支持進入 Phase 2 回測？**

主訊號（N=20）任一通過即可進 Phase 2：
1. **方向 lift**：5 桶 quintile 漲日機率單調且首尾差距 ≥ 8pp
2. **振幅 lift**：5 桶 quintile 平均振幅單調且首尾差距 ≥ 30%
3. **大跌規避**：某 3 桶大跌機率相對 baseline lift ≥ 50%
4. **9 宮格極端格**：27 格中存在 ≥ 2 格 lift ≥ 80% 且 chi-square p < 0.05

額外檢查：
- 樣本數 ≥ 1500 個交易日（ma20 暖機後）✓
- 結論不被「清單進出榜事件」主導
- 與 H079 訊號相關性 < 0.7（獨立增量價值）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑　[ ] 衍生 H081（聚焦最佳 N）

---

## Phase 2: Backtest（GATE 通過後規劃）

- [ ] 根據 Phase 1 找到的最強訊號（含最佳 N）定義進出場規則
- [ ] 定義 baseline（無濾網的同方向策略）
- [ ] In-sample 回測（2018-01 ~ 2024-06，約 75% 樣本）
- [ ] Out-of-sample 驗證（2024-07 ~ 2026-05，約 25% 樣本）
- [ ] 參數敏感度分析（quintile 切點、tercile 切點 ±2pp、N 值替換）
- [ ] 與 H079 訊號合併測試（疊加效益是否 > 各自單獨）

## Phase 1.5: 即時集中度驗證（後續延伸，不在本 Phase 範圍）

- [ ] 建立即時集中度日記管線（每天 8 個時點記錄）
- [ ] 累積 60–100 個交易日後分析「早盤各時點 vs 全日集中度」相關性
- [ ] 只有相關性達標（如 corr ≥ 0.85）才允許 Phase 2 結論用於實戰策略

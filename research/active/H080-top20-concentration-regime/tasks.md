# Tasks: 前 20 權值股成交集中度的行情分類

## Phase 0: 資料管線建置

- [ ] 確認 TWSE 月報「市值比重 / 加權指數成份股權重」歷史端點（2018-01 起可回溯）
- [ ] 設計 `top20_lists` 表 schema（list_month / rank / symbol / name / weight_pct）
- [ ] 寫 `src/etl/parse_top20_lists.py`：下載 + 解析月報，2018-01 ~ 2026-05 全期
- [ ] 設計 `top20_concentration` 表 schema
- [ ] 寫 `src/etl/build_top20_concentration.py`：join stock_day + market_breadth + top20_lists → top20_concentration
- [ ] 驗證 ETL：抽樣 5 個交易日手動核對（包含結算日、清單變動日）

## Phase 1: Distribution Research

### 1A. 訊號穩定性檢視
- [ ] 計算每月清單變動數（list_changed events）並圖示
- [ ] 計算 `share_pct` 全期分佈：min / max / mean / median / 變化趨勢（受台積電權重上升影響）
- [ ] 計算 `deviation_pct` 全期分佈：應為 0 為中心的鐘形

### 1B. 邊際分析（5 桶 quintile）
- [ ] 切 5 桶 → 計算每桶：漲日機率、平均方向、平均振幅、std 振幅
- [ ] 視覺化：5 桶 vs 漲日機率（找單調性）
- [ ] 視覺化：5 桶 vs 平均振幅
- [ ] 計算首尾桶差距，記錄是否達 GATE 1 (8pp) / GATE 2 (30%)

### 1C. 9 宮格主分析（3 桶 × 9 行情格）
- [ ] 切 3 桶集中度 + 9 行情格（方向 × 振幅）= 27 格
- [ ] 對每格計算：發生機率、相對 baseline lift、樣本數
- [ ] Chi-square 檢定（27 格 vs 獨立性虛無假設）
- [ ] 找出 lift ≥ 80% 且 p < 0.05 的格子，記錄是否達 GATE 4

### 1D. 大跌規避分析（H080-D）
- [ ] 定義「大跌日」：方向 < -0.5% 且振幅 > top tercile
- [ ] 計算各集中度桶的大跌日機率，比對 baseline，記錄是否達 GATE 3 (lift ≥ 50%)

### 1E. 結構性事件檢視
- [ ] 標記清單進出榜事件（2018 國巨、2021 長榮、2024 廣達/緯創等）
- [ ] 確認結論在「移除清單變動月份」後是否仍成立（避免單一事件主導）

### 1F. 與既有訊號的相關性
- [ ] 計算 `deviation_pct` 與 H079 的 `breadth_up_ratio`、`limitup_value_ratio` 的相關性
- [ ] 檢查是否有冗餘（如果與 H079 訊號 corr > 0.7，本假設增量價值需重新評估）

### 1G. Weekday 子分析（條件性，主訊號顯著才做）
**前置條件**：1B 或 1C 主分析已找到 ≥ 1 個顯著訊號
- [ ] 對「最強訊號」（5 桶 quintile 上的方向或振幅 lift）按 weekday 拆分：每 weekday × 5 桶 = 25 格，每格 ~80 天
- [ ] 比對：主訊號在哪一天最強 / 最弱，是否與既有 H068（reversal weekday）、H071（tuesday vol paradox）的結論呼應或衝突
- [ ] 不對 27 格做 by-weekday（樣本太薄，每格 ~14 天無統計力）
- [ ] 結論若有 weekday 差異性，記錄為衍生假設（不在本研究結案）

---
### GATE
**問題：分佈結果是否支持進入 Phase 2 回測？**

任一通過即可進 Phase 2：
1. **方向 lift**：5 桶 quintile 漲日機率單調且首尾差距 ≥ 8pp
2. **振幅 lift**：5 桶 quintile 平均振幅單調且首尾差距 ≥ 30%
3. **大跌規避**：某 3 桶大跌機率相對 baseline lift ≥ 50%
4. **9 宮格極端格**：27 格中存在 ≥ 2 格 lift ≥ 80% 且 chi-square p < 0.05

額外檢查：
- 樣本數 ≥ 1500 個交易日（ma20 暖機後）✓
- 結論不被「清單進出榜事件」主導（移除事件月後結論仍成立）
- 與 H079 訊號相關性 < 0.7（有獨立增量價值）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過後規劃）

- [ ] 根據 Phase 1 找到的最強訊號定義進出場規則
- [ ] 定義 baseline（無濾網的同方向策略）
- [ ] In-sample 回測（2018-01 ~ 2024-06，約 75% 樣本）
- [ ] Out-of-sample 驗證（2024-07 ~ 2026-05，約 25% 樣本）
- [ ] 參數敏感度分析（quintile 切點、tercile 切點 ±2pp）
- [ ] 與 H079 訊號合併測試（疊加效益是否 > 各自單獨）

## Phase 1.5: 即時集中度驗證（後續延伸，不在本 Phase 範圍）

- [ ] 建立即時集中度日記管線（每天 8 個時點記錄）
- [ ] 累積 60–100 個交易日後分析「早盤各時點 vs 全日集中度」相關性
- [ ] 只有相關性達標（如 corr ≥ 0.85）才允許 Phase 2 結論用於實戰策略

# Proposal: 電子/金融比率趨勢強度作為 trend-vs-chop regime 偵測器

## ID
H131

## Derived From
Origin（原創）。概念相鄰於 H080 concentration_index（leadership 集中度）與 vix_regime（波動環境），本假設探討另一個 leadership 切面：電子 vs 金融的相對強度趨勢。

## Trading Intuition
電子是台股高 beta 攻擊主體、金融是低 beta 防禦主體。觀察：
- **方向面（A）**：電子轉強＝資金偏攻擊（Risk On）；金融轉強＝偏防禦（Risk Off）。
- **持續面（B，主軸）**：當電子/金融比率果斷地往一個方向走（leadership 明確、不洗），市場往往處於「會延續趨勢」的環境；當比率黏在均線附近來回（leadership 不明），市場偏盤整、均值回歸。

用途定位：**不是當沖擇時訊號**，而是日線層級的 **regime 偵測器** —— 描述「現在是不是趨勢環境」。Regime 指標不需要領先性，只要能描述當下環境且夠持續即有價值。

## Hypothesis
電子(TSE23)/金融(TSE28) 對數比率 `r = ln(TSE23/TSE28)` 的**趨勢強度**（trailing Efficiency Ratio），對 TAIEX 未來的「趨勢 vs 盤整」程度（forward ER）有**單調且增量**的預測力：

- **主（B）**：trailing 比率-ER 越高 → 未來 K 日 TAIEX-ER 越高（更乾淨的趨勢）。
- **次（A）**：比率方向 `sign(r − MA_W(r))` 能排序 forward TAIEX 方向報酬。

**增量** 定義（關鍵）：在控制 **TAIEX 自身 trailing ER**（regime 持續性 baseline）後，比率-ER 仍須保有 partial 預測力；且不能只是 concentration_index 或 VIX regime 的換句話說。

### 訊號建構
- 比率：`r_t = ln(TSE23_close / TSE28_close)`（log → 多空對稱）
- 趨勢強度（測 B）：`ratioER_t = |r_t − r_{t−W}| / Σ_{i=t−W+1..t} |r_i − r_{i−1}|`，W 掃 {10, 20}
- 方向（測 A）：`sign(r_t − SMA_W(r_t))`

### 驗證標的（forward ER）
- `fwdER_t(K) = |close_{t+K} − close_t| / Σ_{i=t+1..t+K} |close_i − close_{i−1}|`（TAIEX 日線），K ∈ {5, 10, 20}

## Expected Distribution
- 比率-ER 由低到高分位，對應的 forward TAIEX-ER 中位數**單調遞增**。
- 在 nested/partial 分析中，比率-ER 對 forward ER 的係數於控制 TAIEX-ER 後**仍顯著為正**（增量存在）。
- (A) 方向分組：比率方向為正（電子領先）對應 forward TAIEX 報酬中位數偏正、為負偏負（弱於 B，可接受不顯著）。
- 與 concentration_index / VIX regime 的相關不致高到視為同一指標（|corr| 明顯 < 1）。

## Invalidation Condition
任一即視為主假設不成立（Rejected / Inconclusive）：
1. **無單調**：比率-ER 分位對 forward TAIEX-ER 無單調關係（含倒掛或平坦）。
2. **無增量（最可能的死法）**：控制 TAIEX-ER 後，比率-ER 的 partial 預測力歸零 → 它只是 TAIEX 趨勢度的高 beta 放大版（同步指標，非獨立資訊）。
3. **冗餘**：比率訊號與 concentration_index 或 VIX regime 高度共線（增量相對它們亦為零）。
4. 樣本/穩健性不足以支撐結論（見 GATE）。

## Notes
- 資料缺口：DB 目前無 TSE23/TSE28 類股指數，stock_day 亦無產業分類欄位，**無法自建**。Phase 1 先以一次性 fetch 取得官方日指數（TWSE MI_INDEX 或 FinMind，2010 起對齊 taiex_day），落地 results/ 供探索；若 confirmed 再正式化為 ETL。
- 方法論硬規則（記憶 feedback_excursion_needs_forward_tautology_guard）：所有條件統計必對比正確虛無分佈 —— 此處虛無＝「TAIEX 自身 trailing ER 預測 forward ER」。
- 相鄰結論參考：DCI 被驗為延伸/趨勢訊號而非 fade（project_dci_is_extension_signal）；本假設預期同屬「趨勢/regime 確認」家族。

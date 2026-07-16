# Proposal: 實現波動「溫度計」預判深reach延續

## ID
H139

## Derived From
Origin（原創；緣起於用戶觀察 2026/4/1~4/22 日盤幾乎只到 L3、無 L4/L5 的「冷 streak」）。
方法上承接 [[project_ladder_reach_timing_map]]（ladder 達成地圖）、[[project_vix_regime_ladder_causal]]（VIX regime 因果基準）、
與 [[project_oos_equals_highvol_regime]]（regime confound 警告）。

## Trading Intuition
台指日盤的深 reach（碰到 L4/L5）頻率是重度 regime-dependent 的：擴張期 L4/L5 頻繁、收斂期薄。
2026/4 出現一段連續多日「只到 L3、碰不到 L4/L5」的冷 streak。直覺問題是：
**當下的「行情溫度」（近期實現的深 reach 頻率、夜盤收斂程度）能不能預判接下來幾天是否延續冷/熱？**
若能，就能在盤前調整深關卡的期望（該不該硬等 L4/L5、停損該放寬或收緊）。

現成的 `vix_regime` 已用 VIX + 已實現振幅方向給出 regime 與 reach 期望，但它以 VIX 為主體、
反應相對慢。本假設要問：**直接用「已實現的 ladder 溫度」是否能提供 vix_regime 之外（或之上）的預判力**，
還是只是波動叢聚（volatility clustering）的重述、不具額外可操作資訊。

## Hypothesis
定義兩個 **100% 因果（trailing-only）** 的溫度計：

- **temp_ladder(W)** ＝ trailing W 個日盤 session 中，open-anchor ladder 達成 L4+（方向 excursion from open ≥ 0.977×EMA20(日振幅)）
  與 L5+（≥ 1.225×EMA20）的頻率。多方 / 空方分別統計。主變體＝全日；次變體＝截至 11:30。
  （10:30 因 memory `project_ladder_reach_timing_map` 已知只捕獲全日 L4 的 ~10%，過稀疏，只當 early-fireworks 次要旗標，不當主判據。）
- **temp_night(W)** ＝ trailing W 個夜盤的 deep-STOP 頻率（night_range / EMA20(night_range) < 0.8，沿用 key_prices NVF 定義）。

**待測命題**：存在某組 (W, H)（W∈{5,10,20}, H∈{1,3,5,10}），使得 temp_ladder（和/或 temp_night）
對「未來 H 個 session 的深 reach 率」的預判，**顯著優於下列三個虛無基準**：

1. **Persistence null（核心）**：波動叢聚使「trailing rate ≈ future rate」本就成立。真正有價值的發現是
   **極端值的 mean-reversion / 續冷結構**——例如極冷 streak（近 W 日 0 次 L4）之後，未來 H 日深 reach 率
   是否 **系統性偏離** 無條件基準（顯著低＝續冷可交易；顯著高＝反轉可交易）。單純「高→高、低→低」的
   線性持續性 **不算過關**（那只是重述 clustering）。
2. **VIX-regime null**：以 `vix_regime` 的 regime 標籤（升壓/降壓）預測同一未來 H 日深 reach 率為基準。
   溫度計須證明能 **補強或取代** 它（例如在同一 regime 內再分出高/低溫、且分出的兩組未來 reach 率有實質差距）。
3. **共線性檢查**：temp_night（夜盤 deep-STOP）相對 temp_ladder（日盤深 reach）是否 **additive**，
   還是只是同一潛在波動因子的較噪代理。

## Expected Distribution
- 溫度計對未來深 reach 的原始相關 **必然為正**（clustering），這是預期中、不足為奇的。
- 關鍵看 **極端桶**：把 temp_ladder 分成 quantile 桶（或用「近 W 日 L4 次數 = 0 / 1 / ≥2」），
  檢視各桶「未來 H 日深 reach 率」相對無條件基準（全史 ~L4 25% / L5 12.5%）的 lift，並附每桶 N。
- 預期最冷桶（0 次 L4）未來 reach 率明顯低於基準；最熱桶明顯高於基準。**若關係非單調、或桶間差距在
  剔除 persistence 後消失，則不具額外 edge。**
- VIX-regime 對照：預期在「同 regime、不同溫度」的細分下，若溫度計有料，兩組未來 reach 率應拉開差距；
  若拉不開，代表溫度計資訊已被 VIX regime 吸收。

## Invalidation Condition
以下任一成立即 **不接預測訊號**（Phase 1 GATE 不過；但觀測 tile 仍照建）：

1. 剔除 persistence 後（對比正確虛無：trailing rate 或 IID 洗牌重排 forward window），
   溫度計對未來深 reach 的 edge 不再顯著、或非單調。
2. 在 VIX-regime 分層內，溫度計無法把未來 reach 率拉開實質差距（＝資訊已被 regime 吸收）。
3. 任何看似有效的 (W,H) cell 樣本數不足（見 GATE 門檻）或只由單一 regime 期間（如 2026 單段擴張）撐起，
   跨子期間 / 跨 regime 不穩（承 `project_oos_equals_highvol_regime`、
   `project_elec_fin_ratio_direction_not_trendiness` 的池化 t 三關方法論）。

## Notes
- **必交付（無論 GATE）**：`key_prices.py` 觀測 tile ——（a）近 N 日 L4/L5 達成率（多/空，對比全史基準）、
  （b）deep-STOP 夜盤頻率趨勢、（c）溫度方向箭頭（如 EMA5 vs EMA20 of 日振幅）、（d）與 VIX regime 並列對照。
  這是描述性看盤工具（如現有 NVF tier / breadth thermometer），不宣稱預判力，除非 GATE 過。
- ladder 定義沿用 `src/chart_ui/services/daystats.py` 的 `LVL_QUANTILES`（L4 c=0.977、L5 c=1.225，EMA20-relative，open-anchor）。
- deep-STOP 定義沿用 `src/analysis/key_prices.py` 的 `_NVF_TIER_CUTS`（<0.8）。
- 所有數字結論必附樣本數（專案硬規則）。

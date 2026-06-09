# Proposal: dci_short × 盤中下行關卡觸及 × 各時間點 — 空方關係地圖（strategy-agnostic）

## ID
H112

## Derived From
H111-dci-long-reach-map 的 d2（多方地圖完成後做空方鏡像）。dci_short 公式承 H095 `dci_short_combine`。

## Trading Intuition
H111 證明**多方**：龍頭 thrust(dci_long) 越強 → 當天越會往上延伸到深關卡。**空方不是鏡像對稱**——
H095 已發現「集中龍頭 thrust 對下行 reach 幾乎無效」，**下行延伸要靠廣度**：多少檔在跌（家數 B）、
寬權值整體殺多兇（W-100 帶幅度的廣度）。直覺：**全面性賣壓（廣度）才推得動台指往下擺到深關卡**，
少數龍頭看不出來。把這條件關係量到底，作為空方順勢（放空/突破下殺）族的地基。

## Hypothesis
對 open-anchor **下行**關卡 L1–L5，**P(t 之後才達下行 L_k | dci_short(t) 強度分位)** 隨 dci_short 單調上升；且：
- (a) 深關卡(L3/L4)鑑別力較強；
- (b) 成熟時點 t* **較多方晚（≈09:30）**（H095：空方 09:15 還弱、09:30 才成熟）；
- (c) 強分位達成率顯著高於 base rate。
> dci_short = **z(−thrust(W-100)) + z(−B家數)** 等權（H095 dci_short_combine：r≈+0.24、AUC 0.64、
> 兩成分相關僅 0.23 互補）。各成分（寬權值幅度 / 家數 / 合成）分開看誰主導。forward-guarded。

## Expected Distribution
- 達成率隨 dci_short 五分位單調上升，深關卡(L3/L4)鑑別力較強。
- **整體鑑別力弱於多方**（H095：空 corr exc +0.24 vs 多 +0.35）。
- 成熟曲線：09:15 偏弱、09:30 最佳（與多方 09:15 即成形相反）。
- 合成 > 單一成分（家數與寬權值幅度互補）。
- 下行深關卡達成日**稀少**（此窗多頭偏，dn_full 較小）→ L4/L5 樣本薄。

## Invalidation Condition
任一成立即視為**空方無可用條件結構**：
1. 下行各關卡達成率對 dci_short 分位無單調關係（或只極端分位有、forward-guard 後消失）。
2. forward-guard 後鑑別力歸零（純套套邏輯）。
3. 合成不優於單一成分（互補性不成立），且單一成分也無鑑別。
4. 強分位與 base rate 無顯著差距（樣本內）。
5. 下行深關卡樣本太薄（強分位達成 < ~8 日）無法判斷 → 標 Inconclusive 待資料，而非硬判。

## Notes
- **strategy-agnostic**：純條件機率 P(下行 reach L_k | dci_short bucket)，無進出場、無損益。
- 關卡：open-anchor **下行**擺幅 vs c×EMA20，L1–L5（c=0.385/0.497/0.711/0.977/1.225）+ 連續下行擺幅 dn_full/EMA20。
- **前瞻防護必做**（[[feedback_excursion_needs_forward_tautology_guard]]）；每情境實測附 N（[[feedback_isolate_phenomenon_and_test_each_cell]]）。
- **硬限制（比多方更嚴）**：上市-only、181 日、**此窗輕微多頭偏**（下行擺更遠僅 47%、dn_full 中位 184 vs up 215）
  → 下行深關卡達成日更稀、空方樣本更薄，數字更指示性、**更需 OOS**（待 stock_min 擴充 + 不同 regime）。
- 空方天生較弱是 H095 既有發現，非本案瑕疵；目標是把「弱但存在」的條件結構量清楚。
- 承 [[project_dci_is_extension_signal]]：產出供**空方順勢/突破下殺族**引用，非 fade 族。

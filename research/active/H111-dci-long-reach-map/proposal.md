# Proposal: dci_long × 盤中關卡觸及 × 各時間點 — 多方關係地圖（strategy-agnostic）

## ID
H111

## Derived From
H095 reach-ladder-exit 的 DCI 子線（dci_snapshot_sweep / dci_universe_sweep / dci_calibrate）。
H111 把那些散落的多方發現**系統化、定案化**成一張乾淨的條件地圖，且**完全不綁任何策略**。
也承接 H110 的結論（[[project_dci_is_extension_signal]]：DCI 是延伸訊號）——先把「多方延伸」這塊地基打穩。

## Trading Intuition
盤中 TX 的 **open-anchor 關卡（L1–L5 = c×EMA20 的方向擺幅階梯）** 觸及，不是均勻隨機——
龍頭股越強、越早站上開盤（dci_long 越大），當天台指越可能往上擺得越遠、達到越高的關卡。
這是純現象：**P(當日達 L_k) 應被早盤 dci_long 條件化**。先不談怎麼進出場，先把這關係量到底。

## Hypothesis
對 open-anchor **上行**關卡 L1–L5，**P(該時點之後才達 L_k | dci_long(t) 強度分位)** 隨 dci_long 單調上升；
且：
- (a) 越高的關卡（L4/L5）鑑別力越強（H095 已見 L4 > L3）；
- (b) 存在一個「成熟時點」t*，t* 之後關係穩定可用（早盤太早為噪音，H095 已見 09:01 噪音）；
- (c) 強分位達成率**顯著高於** base rate（無條件達成率），構成可用的條件結構。
> 一句話：強 dci_long(t) 是「當天會往上延伸到高關卡」的可用條件機率訊號（forward-guarded）。

**只做多方（dci_long）。** dci_short（空方廣度）待多方定案後另立假設。

## Expected Distribution
- 達成率隨 dci_long 五分位**單調上升**，最強分位 L4 達成率明顯高於 base rate。
- L1（淺）對 dci_long 幾乎無鑑別（多數日都會碰）；越深（L3/L4/L5）鑑別力越強。
- 時點掃描：09:01–09:05 噪音、~09:10–09:15 起成形、09:30 最成熟但 forward 可用窗縮。
- 對照（防自證）：forward-guard（t 之後才達）後關係仍在，但比「全日達成」弱（後者含 t 前既成擺幅）。

## Invalidation Condition
任一成立即視為**無可用條件結構**：
1. 各關卡達成率對 dci_long 分位**無單調關係**（或只有最極端分位有、forward-guard 後消失）。
2. forward-guard 後鑑別力歸零 → 原關係純為套套邏輯（t 前既成擺幅）。
3. 關係在時點間不穩定、無法定出可用 t*。
4. 強分位達成率與 base rate 無顯著差距（樣本內）。

## Notes
- **strategy-agnostic**：純條件機率 P(reach L_k | dci_long bucket)，無進出場、無損益。
- dci_long 用 H095 最佳定義：**W-20~50（動態 20日均成交值大型股）value-weighted tanh((p@t−open)/range_i)**。
- 關卡：open-anchor 方向擺幅 vs c×EMA20，**L1–L5 全測**（c=0.385/0.497/0.711/0.977/1.225）。
- **前瞻防護必做**（[[feedback_excursion_needs_forward_tautology_guard]]）：reach 用「t 之後才達」，並對照全日達成。
- 每個情境都實測、附樣本數（[[feedback_isolate_phenomenon_and_test_each_cell]]）。
- 硬限制：stock_min 上市 TWSE-only、窗 2025-06~2026-02（181 日）、偏多頭、無 OOS（待資料擴充）。
- 產出是「多方關卡達成條件地圖」，作為日後**順勢/突破族**策略的地基（DCI 的正確歸宿）。

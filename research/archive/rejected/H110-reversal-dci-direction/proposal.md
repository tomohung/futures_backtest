# Proposal: Reversal 方向濾網改用 DCI 盤中廣度訊號

## ID
H110

## Derived From
H095 reach-ladder-exit 的 distribution 階段（DCI-intraday 方向預測發現）。
與 H101-reversal-direction-filter（rejected）對照——H110 補上 H101 未測的「市場內部廣度」訊號源。

## Trading Intuition
Reversal（S002）是均值回歸：`_direction()`（**5m120MA 日盤斜率**，±1）決定當天做多/做空偏向——
MA 向上只 fade 下軌（做多回檔）、向下只 fade 上軌（空反彈）。這個斜率就是策略「找當天方向」的
核心濾網，也是 reversal 的天敵「趨勢日被輾」的主要防線。

實盤直覺：方向判斷只看 TX 自己的價格 MA，等於用「價格的落後平滑」猜方向。盤中**權值龍頭離開
開盤多遠、全市場多少檔在動**（DCI thrust/breadth），是更早、更直接的「今天往哪走」證據。

H095 實測支持：sign(thrust) 對「10:00 前哪邊擺更遠」命中——強 thrust 09:15 達 77%、09:30 達 82%；
多方 thrust 對 reach 排序 r≈+0.35。且 reversal 進場最早 09:10、中位 09:30 → DCI@09:05~09:30
對進場**因果可得**（每筆取 ≤進場 bar 的最近 DCI 檢查點）。

## Hypothesis
把 `reversal.py` 的 `dir_mode` 新增 `'dci'`：方向來自 DCI，但**不是二分 sign**，而是依 `|dci_long|`
**強度分至少強/中/弱三群**（方向 = 群內 sign(dci_long)）於進場前因果檢查點，**取代 5m120MA 斜率**。
強度分群的理由：實測方向命中率隨 |thrust| 單調上升（強 thrust 09:30 對 10:00 前方向 82%、弱 ≈ 噪音），
二分會丟掉這結構。
> H1：base 與 dci 方向**歧異**的 reversal 進場日，DCI 站對邊的優勢**集中在「強」群且隨強度單調遞增**；
> 「弱」群 ≈ CHOP（DCI 無方向資訊）。據此 `dir_mode='dci'`（強群信 DCI、弱群退回 base / 不進）
> 相對 base 在窗內提升 EV/PF、降低連敗與回撤。

強度分群：用 **181 日面板 `|W-20|` 五分位**（強度 5 群，看單調性）定界，**逐檢查點各自定界**（不同時點尺度不同）。
檢查點掃描：09:05/09:10/09:15/09:20/09:25/09:30 全掃，看 edge 何時成熟、及「放寬檢查點」的因果代價
（越晚訊號越強但能合法用的 reversal 進場筆數越少＝只算進場 ≥ t 的單）。
對照組：`base`（5m120MA，現行 live）、`dci`（分群 DCI 方向）、`both`（強群且與 base 同向才進）。
唯一變數為方向來源，其餘 reversal 邏輯（BB latch、力竭、vol、SatZone 出場）完全不動。

## Expected Distribution
- base vs dci 方向在 reversal 進場日的**歧異率**（H101 中 base vs A 僅 20%、vs MACD 54%）。
- **分強/中/弱三群**，各群在歧異日：依 base 方向 vs 依 dci 方向，哪個對應「實際擺更遠/該 fade 成功」的一邊。
- 預期：**強群 DCI 命中率明顯 > base 且隨強度單調**；弱群兩者皆接近擲銅板（CHOP）。
  歧異多發生在強群（趨勢日，thrust 強），正是 base 容易站錯邊處。

## Invalidation Condition
任一成立即視為**不支持**（重演 H101 結局）：
1. base 與 dci 方向歧異率過低（<10%）→ DCI 帶不來新資訊，無從改善。
2. **即使在「強」群**，歧異日 DCI 方向命中率 **未顯著高於** base（或無「強>中>弱」的單調結構）
   → 強度分群沒撐起機制，視同無效。
3. Phase 2：`dci` 與 `both` 在窗內**未優於** base（總損益%、PF、Sharpe、最大連敗、最大回撤綜合看），
   或改善落在樣本雜訊內（窗內 N 小，須標註指示性）。

## Notes
- **硬限制**：DCI 需 stock_min，目前僅 **2025-06~2026-02（181 日，上市 TWSE-only）**。
  → reversal 回測只能在此窗（窗內約 40–60 筆）；樣本小、**OOS 受限**、**區間偏多頭**、breadth 上市-only。
  結論為**指示性**；待主下載到 2026-06 + 回補 + TPEX 後才能正式 OOS / 晉升。
- **因果鐵律**：DCI 一律取「≤進場 bar 的最近檢查點」，禁用未來讀數（EstHL 的教訓）。
- **H101 前車之鑑**：方向濾網非 reversal 主 alpha、base 難打敗；本案賭點在「廣度型外部訊號 ≠ H101 的 TX 同源訊號」。若 DCI 也打不贏 base，結論與 H101 一致並補強之。
- DCI 公式出處（H095 v2 實證骨架）：`research/active/H095-reach-ladder-exit/results/` 的
  `dci_intraday_calibrate.md`、`dci_snapshot_sweep.md`、`dci_formula_compare.md`、
  `dci_universe_sweep.md`、`dci_short_combine.md`、`dci_exit_modulate.md`、`dci_causal_mgmt.md`。
- `dir_mode` 機制由 H101 留下（`_direction()` 可插拔，live 行為不變）。

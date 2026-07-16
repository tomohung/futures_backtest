# Archive: 實現波動「溫度計」預判深reach延續

## Status
Rejected（預測性宣稱）；副產物觀測 tile 已上線 key_prices.py。

## Summary
測試用 trailing W 日已實現的 ladder 達成率（temp_ladder：L4≥0.977×EMA20、L5≥1.225×，open-anchor）
與夜盤 deep-STOP 頻率當「市場溫度計」，能否預判未來 H 日深 reach 是否延續。
結論：**對未來深 reach 沒有 vix_regime 之外的預判力**——溫度資訊已被現有 vix_regime 完全吸收。
N=1339 交易日（2021–2026）。

## Key Evidence
- daily anyL4 幾乎 IID：ACF ρ(lag1)=+0.07，lag3 起≈0 → clustering 極弱，溫度計上限本就低。
- tertile 冷→熱 forward spread 僅 +1~8%，落 IID 洗牌 null 的 75–89 分位（未過 p95）。
- ★ 決定性：同 vix_regime 內再切高/低溫，未來5日 anyL4 增量 **−2%/−2%**（升壓/降壓，N=815/510）全≈0或負。
- 極端冷桶（trailing10日0次L4）forward：次日 −5pp、到 H=5 revert 回基準 24.8%。
- 鐵證：2026/04/21–22 連10日零L4（最冷）→ 04/23 隔日爆 rng=1679、L5 命中（全窗最大 move）。
- deep-STOP 非 additive（corr −0.39、2×2 forward 全 23–27%）。

## Why Rejected
proposal 的無效條件全部命中：剔除 persistence 後 edge 在 IID null 帶內、在 vix_regime 分層內拉不開差距、
極端冷桶 revert 回基準、deep-STOP 不 additive。vix_regime 已是深 reach 前瞻預判的充分統計量。

## Delivered Artifact（非預測，描述性）
`src/analysis/key_prices.py` `_compute_market_temperature()` + print_report「市場溫度（現狀）」段：
近5/10/20日 anyL4(多/空)/anyL5/deep-STOP vs 全史基準 + 振幅 EMA5vsEMA20 方向箭頭 + 與 ladder regime 並列對照。
只進 key_prices 盤前簡報 clipboard。定位＝即時「現狀溫度計」，深 reach 期望仍看 regime tile。

## Derived Hypotheses
- H140（未開）：找 vix_regime **之外** 的盤前變數提升深 reach 前瞻預判——選擇權 IV term、隔夜 gap、
  國際期貨夜間振幅。trailing 已實現頻率已證無增量，方向應轉向 regime 外的獨立資訊源。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 腳本：explore.py（保留）
- 圖：results/temp_forecast.png
- Memory：project_vix_regime_sufficient_for_deep_reach

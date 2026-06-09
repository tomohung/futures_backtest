# Archive: 重權值推力（Heavyweight Thrust）

## Status
Rejected

## Summary
測「前 5~10 大權值、近似指數權重、不 tanh 封頂的重權值推力(HT)」是否為比廣度版 ext_long(W50 tanh)
**更強且 subsume 它**的多方 reach 預測。源於 chart-ui 2026-02-25 案例（窄基重權值拉抬到 L5，ext_long 漏）。
結論：**用戶「HT 更強」假設不成立且方向相反**——ext_long 略強且 subsume HT；HT 更套套邏輯（更像指數鏡子）。

## Key Evidence
N=181（2025-06~2026-02，上市-only、in-sample、偏多頭），目標 forward L4(base 27%)：
- **鑑別力**：ext_long r=+0.224(lift+20%) ≥ HT5/10/15(+0.20~0.21)；等權 HT 近無效(+0.06)→ 權重集中才是 HT 訊號源。
- **subsume（反向）**：控制 ext_long 後 HT partial=+0.044；控制 HT 後 ext_long 仍 +0.114；corr(HT,ext_long)=+0.76。
- **套套邏輯防護**：corr(HT, TX自身09:30擺幅)=+0.59；控制 TX 自身後 HT partial=+0.091 < ext_long +0.132
  → HT 更接近「重算已漲幅度」，ext_long 帶更多真 forward 跨截面資訊。
- **窄基補漏（動機）成立但少**：ext_long 漏的 27 個 L4 日中，HT 乾淨翻強(top20%)只補 **3 天**（01-05/02-10/10-07）；
  2/25 本身 HT 也只微正(+0.14)、未到強。主要漏失型態是「午盤才噴」16 天，任何 09:30 訊號都抓不到。

## Why Rejected
命中 Invalidation #1（HT 不優於 ext_long）+ subsume 反向。HT 不是更強的多方指標，而是
ext_long 的高度相關、更套套邏輯的子集，僅在少數窄基重權值日補到 ext_long 的漏（3 天，價值太薄，OR-合成未採）。

## Derived Hypotheses
- **H113-d2（已驗，移入 H111）**：TX 自身 09:30 擺幅本身 r=+0.214≈ext_long → 個股訊號要證明價值需贏過這條 TX-only 基準；
  控制後 ext_long 仍 +0.132 是它的真增量。ext_long 真實召回/精度/forward 命中分析已補入 H111 backtest.md。

## Links
- Proposal：proposal.md｜Distribution：results/distribution.md｜Scripts：explore.py（HT vs ext_long + 套套邏輯防護）

# Archive: 累積淨多空力道 當 ladder 續攻早碰層修正

## Status
Rejected

## Summary
H115 衍生:用使用者既有指標 `bull_bear_force_volume`（累積淨多空力道 Σ(漲K量−跌K量)/Σ總量）取代無方向 vol_ratio,當早碰層續攻修正。**關鍵:本案 TX-only,不需 stock_min** → 直接拉全 TX 史(2021~2026,含 2022 熊)多 regime 驗,一次驗死。結果早碰層增量**多 regime 符號不穩,否決**。

## Key Evidence
- 全史 666 事件。累積淨力分帶 gap：低/中/高波 +5/+14/+8,但逐年 2021-23 趨 0(+1~2%)、**僅 2025-26 有(+16/+18)**。
- ★ 早碰層增量 by regime：低波 −8% / 中波 +4% / 高波 −5%（**符號翻轉**,2022 熊 +13% 唯一亮點）→ Invalidation #1 觸發。
- H115 的早碰層 IS+9/OOS+26 是近期單一窗假象。

## Why Rejected
累積淨力（即使定向修好了 vol_ratio 的符號問題）當穩定規則,放到多 regime 就垮——早碰層增量符號不穩、僅近兩年有。與全鏈一致:延伸力/量/淨力各形式擴到多 regime 皆不穩。

## 附帶重大產出（回饋 H114）
用全 TX 史驗證:**碰觸時點 gap 跨 5 年所有 regime +23~35% 穩**（666 事件）→ 將 H114 從 Inconclusive 上修為 Confirmed-描述性。方法論:不依賴個股的 ladder 研究應優先全史多 regime 驗,繞過 stock_min 的 2025-06 邊界。

## Derived Hypotheses
- 觀察（不追）：累積淨力 gap 逐年升(2021 +2→2026 +18)、2022 熊早碰層 +13% → 「定向量近年變有訊息/熊市較有用」的微結構假設,證據薄易 snooping,不立案。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（全史多 regime）
- 全史腳本：explore.py;H115 階段腳本：../../rejected/H115-volratio-vs-dci-room/h115_force.py
</content>

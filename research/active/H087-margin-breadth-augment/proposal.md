# Proposal: 加入廣度指標補強 H084 指標集

## ID
H087

## Derived From
H084-correction-bottom-survey 的 distribution.md 後續工作清單

## Trading Intuition

H084 受限於 stock_day / market_breadth ETL 未跑，只有 5 個可用指標。CNN F&G 原版有「漲跌家數比、52週新高新低家數」這類廣度指標，台股應該也能做。

問題：在 H084 的 4 個非冗餘軸（VIX_pct + z 125MA + margin_drop_60d + econ_score）之外，廣度指標能否提供**第 5 個非冗餘軸**？

## Hypothesis

> 從 stock_day / market_breadth 衍生的廣度指標（漲跌家數比、52週新低家數、累積廣度指標）中，**至少有一個指標**：
> 1. 在 Tier B/C trough 達極值的命中率 ≥ 60%
> 2. 與 H084 現有 4 個指標的兩兩 |Pearson r| < 0.6

如成立，加入 H085 合成 score 重跑能進一步提升表現。

## Expected Distribution

Phase 0/1 預期：
- 漲跌家數比累積（McClellan-style）— 與技術指標弱相關，獨立軸
- 52週新低家數 — 在底部（個股廣泛打底）會高，與 z 125MA 相關但程度待測
- 量能廣度（少數股總成交額占比）— 與 H080 集中度研究有關連

## Invalidation Condition

下列任一成立 → reject：

1. **資料不可得**：stock_day ETL 跑不齊（特殊權證 / 停牌 等資料品質問題）
2. **無一個廣度指標** 命中率 ≥ 60%
3. **所有過 60% 的廣度指標** 都與現有 4 軸某一個 |r| ≥ 0.6（即冗餘）
4. 整合後 H085 forward-return 表現未提升

## Notes

- **前置條件**：先跑 download_stock_market.py + parse_stock_market.py 回填 2010+
  - 工作量：~10000+ HTTP 請求，需控制 delay 與分批
- 候選廣度指標清單（建置時要試）：
  - `breadth_adv_dec`：漲家 / 跌家
  - `breadth_adv_dec_cum`：累積漲跌差（McClellan-style）
  - `new_lows_52w`：52w 新低家數
  - `new_highs_minus_lows`：52w 新高 - 新低
  - `volume_concentration`：top 20 個股成交額占比
  - `value_per_stock`：人均成交（分散度）
- 跟 H079 漲停萎縮溫度計與 H080 集中度研究有重疊，要 cross-check

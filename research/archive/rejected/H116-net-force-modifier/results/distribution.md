# Distribution Research Results: 累積淨多空力道 早碰層修正（全史多 regime）

## Date
2026-06-10

## Conditions Tested
- ★ **TX-only**：訊號(累積淨力)+事件(L3碰觸/續攻L4)全用 TX ohlcv_1m,**不需 stock_min**
  → 可拉全 TX 歷史(2021-02~2026-06,含 2022 熊),解掉 H114/H115「OOS≡單一高波 regime」confound（[[project_oos_equals_highvol_regime]]）。
- 碰 L3 日 t_k 取：累積淨力比例 `cum_frac=Σ(漲K量−跌K量)/Σ總量`（當日累積,界 −1~1）、碰觸時點 tod。
- cont = t_k 後續攻 L4。Regime = 全史 ema20(前日EMA20振幅) 三分位（低/中/高波）。
- 腳本 `explore.py`;panel `results/h116_fullhist_panel.csv`。

## Sample
- **L3 事件 N=666**（2021-02~2026-06,5.3 年）;base P(L4|L3)=48%。
- 各 regime base 47-49%（平）;各年 base 44-58%（2024 偏高）。
- 各年事件數：2021(100) 2022(119) 2023(121) 2024(132) 2025(123) 2026(71)。

## Key Findings

### A) 碰觸時點 gap — 跨 regime 全部穩（主軸驗證 ✅）
| regime | 早碰 | 晚碰 | gap |
|---|---|---|---|
| 低波 | 60% | 38% | **+23%** |
| 中波 | 62% | 33% | **+30%** |
| 高波 | 64% | 29% | **+35%** |
- **時點主軸在所有 regime 都大而穩**（+23~35%,666 事件）→ 把 H114 單窗 Inconclusive 的時點發現升級為**多 regime 紮實驗證**。

### B) 累積淨力 gap — 大多是噪音,僅近期有
| regime | gap | | 年 | gap |
|---|---|---|---|---|
| 低波 | +5% | | 2021 | +2% |
| 中波 | +14% | | 2022 | +1% |
| 高波 | +8% | | 2023 | +1% |
| | | | 2024 | +6% |
| | | | **2025** | **+16%** |
| | | | **2026** | **+18%** |
- **H115 的 +34% 幾乎全由 2025-26 撐**;2021-2023 趨近 0（+1~2%）→ 不是穩定訊號,是近期現象（市場微結構/量組成可能變了,觀察）。

### C) ★ 早碰層 累積淨力增量 by regime（Invalidation #1）— 失敗
| regime | 早碰層增量 gap |
|---|---|
| 低波 | **−8%** |
| 中波 | +4% |
| 高波 | **−5%** |
| 〔2022 熊〕 | +13%（唯一亮點,n30）|
- **跨 regime 符號翻轉、繞 0 跳**（−8/+4/−5）→ 早碰層淨力增量**不穩,Invalidation #1 觸發**。
- H115 的早碰層 IS+9/OOS+26 是近期單一窗假象,多 regime 不重現。

## Vs. Expected
- **不符合**：累積淨力的早碰層增量**未能跨 regime 守住**（H115 預期它 regime-stable,實則符號翻轉、僅 2025-26 有）。
- **重大附帶確認**：**碰觸時點跨 5 年/666 事件/所有 regime 穩定 +23~35%** → 主軸地位坐實。

## Gate Decision
**[x] Archive（Rejected）**
- 累積淨力（含定向修正）當 ladder 續攻調節器：**多 regime 否決**——僅近期(2025-26)有、跨 regime 符號不穩。
- 與全鏈一致：延伸力(ext_long)/量(vol_ratio)/淨力,各形式擴到多 regime 皆不穩;**唯「碰觸時點」regime-robust**。
- 正面產出：**時點主軸獲 666 事件多 regime 驗證**（回饋 H114,見下）。

- [ ] 繼續 Phase 2　[x] Archive（Rejected）　[ ] 修改假設

## Derived Hypotheses
- **H116→H114 回饋**：碰觸時點 gap 跨 5 年所有 regime +23~35% 穩 → H114 時點規則應從「Inconclusive(單窗)」**上修**為多 regime 驗證過的 ladder 續攻主軸（仍受「未贏 SatZone P&L」限制,但 separation robustness 已紮實）。
- **觀察（不追）**：累積淨力 gap 逐年升(2021 +2 → 2026 +18) + 2022 熊早碰層 +13% → 「定向量近年變得較有訊息 / 在真有賣壓的熊市較有用」是可能的微結構假設,但目前證據薄、易 snooping,不立案。
- **方法論驗證**：本案示範「TX-only 訊號可直接全史多 regime 驗,繞過 stock_min 的 2025-06 邊界」→ 凡不依賴個股的 ladder 研究都該優先全史驗,別困在單一 regime。
</content>

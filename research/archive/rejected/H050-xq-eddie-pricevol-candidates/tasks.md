# Tasks: XQ 發財橘子純價量策略候選清單

## Phase 0: 候選評估（逐一篩選）

### 批次 1：最高優先（直接適用當沖）
- [x] G1 開盤五分鐘不回頭 → ❌ 淘汰（0 信號，Close==High 太嚴格）
- [x] G2 開高破平盤後又站回 → ⚠️ 做多 PF=1.25 (N=257)，edge 偏弱，暫不建假說
- [x] G3 開盤 N 分鐘連續收紅 → ⚠️ N=3 做多 PF=1.43 (N=134) → **H052**
- [x] A1 SuperTrend → ❌ 淘汰（WR≈50%, PF≈1.10，無 edge）
- [x] C1 VSA 無供應 → ✅ **PF=2.00+ WR=63%** (N=412) → **H054**
- [x] C2 Weis Wave Volume → ❌ 淘汰（PF≈1.0，上漲/下跌波量比無預測力）

### 批次 2：濾網類（疊加現有策略）
- [x] E1 CHOP 斬波指標 → ✅ 趨勢日 range +50% → **H053**
- [x] E2 Choppy Market Index → ❌ 淘汰（各 zone 振幅差異 <5%，無區分度）
- [x] D1 STARC → ⚠️ 下軌反轉率 64-67%, +67~124pt → **H055**

### 批次 3：量價深度分析
- [x] C3 VWMACD → ❌ 淘汰（PF≈1.0，無 edge）
- [x] C4 TSV → ❌ 淘汰（PF≈1.0~1.07，零軸穿越無 edge）
- [x] C10 Force Index → ❌ 淘汰（PF≈1.0，無 edge）

### 批次 4：新候選（量價/動量/濾網）
- [x] B2 加速指標 → ❌ 淘汰（PF≈1.0，零軸穿越無 edge）
- [x] B6 IMI 日內動量指標 → ❌ 淘汰（超買超賣反轉 PF<0.90；順勢 IMI(20)>60 Long PF=1.15 邊緣）
- [x] C6 CMF 蔡金資金流量 → ❌ 淘汰（Long 無 edge；CMF(30) Short PF=1.47 N=452 但方向單一）
- [x] E4 Elder-Ray Index → ❌ 淘汰（Long PF<0.93；Short PF=1.23 N=1106 但偏弱）

### 批次 5：F 類 K 線型態（日線）
- [x] F1 長紅後長黑 → ❌ 做空無 edge；**★ 反向：長黑後做多 PF=1.72~2.04 (N=96/45)**
- [x] F2 多頭執帶 → ❌ 淘汰（台指期信號幾乎不出現，N=1/8）
- [x] F3 多頭母子 → ❌ 淘汰（PF=1.12 但加條件後衰減）
- [x] F6 黑棒吞噬 → ❌ 空頭吞噬無 edge；多頭吞噬 PF=2.47 但 N=25 樣本不足
- [x] F9 大跌後抄底 → ❌ 淘汰（N=9，樣本不足且 PF<0.5）

### 批次 6：A/B/D 類（5m）
- [x] A2 多方維持線 → ❌ 淘汰（PF≈1.0）
- [x] A3 KAMA → ❌ 淘汰（PF≈0.87~1.13，無 edge）
- [x] A4 Vortex → ❌ 淘汰（PF≈1.0~1.24，偏弱）
- [x] A5 Ehlers → ❌ 淘汰（Long PF=0.76~1.0，Short PF=1.05~1.12）
- [x] B1 WaveTrend → ❌ 淘汰（所有組合 PF<1.03）
- [x] B3 QQE → ❌ 淘汰（0 信號，動態 band 太難穿越）
- [x] B5 CMO → ❌ 淘汰（PF≈0.87~1.05）
- [x] B7 Ultimate Oscillator → ❌ 淘汰（PF≈0.84~1.0）
- [x] B11 CCI 超買反轉 → ❌ 淘汰（PF≈0.92~1.0）
- [x] D2 BBTrend → ❌ 淘汰（BBTrend(20/50) Long PF=1.26 邊緣，不夠強）

### 批次 7：E 類濾網
- [x] E5 SZO 情緒指數 → ❌ 淘汰（PF≈0.91~1.06）

### 未測試（跳過）
- C5/C7~C9/C11~C16：C 類量價已證明無效，跳過
- G4/G5：需個股資料，無法測試
- H1~H6：太 niche / 需特殊資料
- A6 KST / A7 DKX / A8 ALF / B4 逆費雪RSI / B8 Chaikin Osc / B9 Coppock / B10 Cybernetic / D3 %B / D4 NW Envelope / D5 Ultimate Smoother / E3 ADX+Choppy / E6 RVI / E7 趨勢強度 / F4 暴量突破 / F5 平台突破 / F7 下影線 / F8 報復性反彈 / F10 狹長突破 / F11 多重MACD：與已測試候選概念重疊或依賴個股特性，不另測

## 評估進度

| 已評估 | 通過 | 淘汰 | 待測 |
|--------|------|------|------|
| 34 | 4+1★ (H052~H055 + F1反向) | 29 | 跳過 ~28 |

### 衍生假說狀態（全部 Rejected）
- H052 開盤動量 → **Rejected**
- H053 CHOP 濾網 → **Rejected**
- H054 VSA 無供應 → **Rejected**
- H055 STARC 下軌 → **Rejected**

## 評估標準

每個候選的快速評估（~30 分鐘）包含：
1. 邏輯是否適用台指期 1m K 線？
2. 計算是否只需 OHLCV？
3. 與現有策略是否互補（非重疊）？
4. 是否有明確可測試的進出場規則？

通過評估者 → 建立獨立 HXXX 假說，走標準 Phase 1 → Phase 2 流程。

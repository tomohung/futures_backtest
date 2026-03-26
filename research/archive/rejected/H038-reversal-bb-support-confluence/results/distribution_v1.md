# Distribution Research Results: BB Touch + Structural Support Confluence

## Date
2026-03-26

## Conditions Tested
- **BB touch 定義**：close <= BB_Lower 或 close >= BB_Upper，且 volume > 1.2 × VolMA20（與 Reversal 策略一致）
- **時間窗口**：08:45 ~ 10:05（setup window）
- **每日每方向只取第一次 touch**
- **S/R 計算**：前 30 日 30m bars 的 swing high/low cluster + VP HVN（lookahead-free）
- **Confluence 定義**：BB touch 價位距離最近 S/R <= threshold × EmaHL
- **反轉成功**：BB touch 後 20 根 bar 內 close 穿越 MA5（trigger），之後 60 根 bar 的 MFE > MAE

## Sample
- 總樣本數：2,341 個 BB touch 事件（long: 1,168 / short: 1,173）
- 時間範圍：2020-12-31 ~ 2026-03-25（約 5.25 年）
- 市場：TX 台指期日盤

## Key Findings

### 1. Trigger rate 幾乎 100%
BB touch 後 20 根 bar 內觸發 MA5 cross 的比例為 99.5%。這表示 **幾乎每次 BB extreme 都會回到 MA5**，trigger 本身不是區分訊號品質的瓶頸。

### 2. Confluence 對勝率無顯著影響

| Threshold | N_conf | N_none | Prof%_conf | Prof%_none | Delta |
|-----------|--------|--------|------------|------------|-------|
| 0.25 EmaHL | 977 | 1,364 | 50.7% | 52.1% | **-1.4%** |
| 0.33 EmaHL | 1,208 | 1,133 | 50.9% | 52.2% | **-1.3%** |
| 0.50 EmaHL | 1,546 | 795 | 51.7% | 51.1% | **+0.6%** |
| 0.67 EmaHL | 1,755 | 586 | 51.5% | 51.5% | **±0.0%** |

在所有閾值下，兩組勝率差距 < 2%，且方向不一致（0.25/0.33 是 confluence 較差，0.5 略好，0.67 持平）。

### 3. MFE 絕對值有差異但 ratio 反轉

| Group | Avg MFE (pt) | MFE / EmaHL |
|-------|-------------|-------------|
| Confluence | 70 pt | 0.313 |
| No confluence | 57 pt | 0.330 |

Confluence 組的絕對 MFE 較高（70 vs 57 pt），但這反映的是 **EmaHL 較大**（高波動日），而非 confluence 本身的效果。MFE/EmaHL ratio 反而是 no-confluence 組略高。

### 4. 年度穩定性不一致

| Year | N_conf | N_none | Prof%_conf | Prof%_none | Delta |
|------|--------|--------|------------|------------|-------|
| 2021 | 304 | 158 | 48.7% | 51.9% | -3.2% |
| 2022 | 298 | 154 | 52.7% | 54.5% | -1.9% |
| 2023 | 233 | 206 | 53.2% | 51.9% | +1.3% |
| 2024 | 312 | 139 | 52.2% | 47.5% | +4.8% |
| 2025 | 325 | 124 | 50.2% | 50.0% | +0.2% |
| 2026 | 74 | 14 | 60.8% | 35.7% | +25.1% |

2021-2022 confluence 反而更差，2023-2024 略好，2025 持平。2026 看似顯著但 N_none=14 太小無意義。

### 5. S/R 距離分佈
- P50 = 0.319 EmaHL（一半的 BB touch 在 1/3 EmaHL 內有 S/R）
- 66% 的事件在 0.5 EmaHL 內有 S/R（1,546 / 2,341）
- 這表示 S/R 密度本身就很高，大多數 BB touch 天然就在 S/R 附近

## Vs. Expected

**完全不符合預期。**

- 預期 confluence 組勝率 > 60% → 實際 51.7%（@ 0.5 EmaHL）
- 預期兩組有顯著差異 → 實際差距 < 2%
- 預期多閾值方向一致 → 實際方向不一致（0.25/0.33 反轉）

根本原因推測：
1. **S/R 密度太高**：66% 的 BB touch 都在 0.5 EmaHL 內有 S/R，分組本身缺乏區辨力
2. **BB touch + vol_ok 已經是強濾網**：能通過這個條件的事件本身就有一定品質，structural S/R 不再提供額外資訊
3. **S/R 的作用可能不在 setup 品質，而在 exit**：支撐壓力更影響反轉後能走多遠，而非是否反轉

## Gate Decision
[x] 直接 Archive（原因：所有閾值下 confluence 對勝率無顯著影響，方向不一致，不滿足 GATE 條件）

## Derived Hypotheses
- **HXXX-reversal-bypass-audit**：回顧 Reversal 策略現有 4 種 CCD bypass 條件的邊際貢獻（使用者已提及要另開）
- **HXXX-sr-exit-enhancement**：structural S/R 可能不影響進場品質，但可能影響 exit 目標（SatZone vs S/R 哪個更好作為停利參考？）

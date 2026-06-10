# Distribution Research Results: vol_ratio vs DCI 當「還有沒有空間」調節器

## Date
2026-06-10

## Conditions Tested
- 事件：碰 L3 日,於 t_k(L3) 當下取三 causal 調節器：
  - **vol_ratio** = EstRange(t_k)/EstRange_Daily(t_k)（量加權,5 分延遲,生產 `compute_vol_estimated_range`）
  - **dci_long** = 盤中 W10 ext_long @t_k（主,`W10_level`）+ W10 @09:15 凍結（對照,`W10_frozen`）
    　※ 註：此「dci_long」即 ext_long（盤中重設計版,同公式）;非 checklist 的 legacy dci_daily（收盤、look-ahead）。
  - **碰觸時點** tk
- 結果 cont = t_k 後是否續攻 L4（forward,取自 H114 panel）。
- 分帶 = IS 三分位(tertile)凍結 → 套 OOS;報強−弱 gap + 單調,IS vs OOS。
- 衍生：使用者既有指標 `bull_bear_force_volume.pine` → **累積/滾動淨多空力道比例**(界 −1~1,抗 regime)取代無方向 vol_ratio。
- 腳本 `explore.py`、`h115_force.py`;panel `results/h115_panel.csv`。

## Sample
- L3 事件 N=149（IS 105 / OOS 44）;base P(L4|L3) IS 50% / OOS 45%。
- 窗 2025-06~2026-06;IS=≤2026-02-26、OOS=≥2026-03-01。上市-only（ext 部分）。

## Key Findings

### 1. vol_ratio 失敗：符號翻轉、regime-dependent（假設否決）
| | IS gap | OOS gap |
|---|---|---|
| vol_ratio 分帶 | **−26%（縮量→續攻多!）** | **+41%** |
- IS 是反直覺的負（縮量續攻更多）、OOS 才正 → **不穩,不可用**。

### 2. ★ 根因 = OOS ≡ 高波 regime（confound,影響整個 IS/OOS 詮釋）
- ema20（前日振幅）中位：**IS 260 → OOS 658（2.5×）**;**OOS 44/44 全落在高波桶**（IS 僅 29/102）。
- → 整個「IS vs OOS」其實 ≡「低波 vs 高波」。所有 OOS 結論都與這**單次 regime 切換**綁死。
- vol_ratio 方向確實隨 regime 變：低波 −18%、高波 ~平（±9%）→ 是 regime 交互,非純噪音（使用者推測正確），但在任一 regime 都不是乾淨正訊號。

### 3. dci_long（=ext_long）也不穩
- 盤中 W10@t_k：IS +26% 單調、**OOS +15% 非單調**（強帶 41% < 中帶 75%）;09:15 凍結同樣 OOS 非單調。重現 H114 的脆。
- 註：ext_long 公式本已 vol-normalize（÷range_i per stock）→ 理論最該抗 regime,卻仍 OOS 退化 → 退化非「缺波動標準化」,是關係在高波真的變了 / 小樣本。

### 4. 碰觸時點完勝且唯一穩定
- IS +38% ↗、**OOS +64% ↗（弱13%/中36%/強78%）,兩段都乾淨單調**。跨低波(IS)/高波(OOS) 都穩 → 唯一 regime-robust 的 room 訊號。

### 5. ★ 多空力道量（使用者指標）修好了 vol_ratio（衍生 H115-d1）
| 訊號 | IS gap | OOS gap | IS 低波/高波 | 控時點增量(早碰層 IS/OOS) |
|---|---|---|---|---|
| **累積淨力比例** | **+34% ↗** | +42% | **+27% / +3~9%（同向）** | **+9% / +26%** |
| 滾動淨力(近20根) | +6% | −2% | flip | — |
- **定向修好了符號**：累積淨力方向直覺（買壓→續攻）且**兩 regime 同向為正**（不像 vol_ratio 翻）→ 使用者「定向 > 無方向」直覺 + `bull_bear_force_volume` 概念**獲驗證**。
- **累積版有用、滾動版噪音**。
- **對時點有真增量但僅早碰層**（IS +9% / OOS +26%;corr(淨力,時點)=−0.43,非純代理）;晚碰層不守。
- 保留：高波 regime 只剩 +3~9%（遠不如時點 +64%）、OOS cell 小（n10~13）、單一 regime → **二級修正,非主軸**。

## Vs. Expected
- **不符合**：vol_ratio 沒贏 DCI、且自身 IS/OOS 符號翻轉（無效條件 #2 觸發）;「放量=還有空間」直覺連 IS 都是反的。
- **意外但重要**：OOS≡高波 的 confound;時點才是唯一 regime-robust 軸;**定向量（使用者指標）能修好 vol_ratio**。

## Gate Decision
**[x] Archive（原始 vol_ratio rejected）+ 衍生 H115-d1（定向量續追）**
- vol_ratio 當「room 調節器」否決（符號不穩、regime-dependent、輸時點）。
- 強結論回收：**checklist 的 room/積極度軸應換成「碰觸時點」,非量、非 DCI**（收斂回 H114）。
- 定向量（累積淨多空力道）升格 H115-d1：當時點主軸的**早碰層二級修正**,值得續追（樣本/regime 補足後複驗）。

- [ ] 繼續 Phase 2　[x] Archive（vol_ratio rejected）+ 衍生 H115-d1　[ ] 修改假設

## Derived Hypotheses
- **H115-d1 → 已升格 H116**（`research/active/H116-net-force-modifier/`）：碰 L3 當下「累積淨多空力道比例」（`bull_bear_force_volume` 概念）當**早碰層續攻二級修正**。Phase 1 已完成(本案 §5);Phase 2 **regime-blocked** 待異質 regime 補足,避免在同一份高波 OOS snooping。
- **H115-d2（方法論,記憶）**：**OOS(2026-03~06) ≡ 高波 regime（44/44）** → DCI 複驗全套 IS/OOS 結論皆與單次低波→高波切換 confounded;「survive OOS」嚴格說是「survive 這次高波」。需異質 regime（2022 結構熊）才能解此 confound。
- **觀察**：延伸力(ext_long)/量(vol_ratio) 各形式 OOS 皆脆,定向量稍好但仍弱;唯「碰觸時點」跨 regime 穩 → ladder 續攻的主軸是時間,不是力道讀數。
</content>

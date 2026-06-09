# Distribution Research Results: 重權值推力 HT vs ext_long

## Date
2026-06-09

## Conditions Tested
HT=前 N 大權值 (p@t−open)/range_i，近似 TAIEX 權重、linear；對打 ext_long(W50 tanh，H111 panel)；
目標 forward 上行 L4；★控制「TX 自身 09:30 上行擺幅」做套套邏輯防護。腳本 `explore.py`。

## Sample
N=181 日（2025-06~2026-02）；上市-only、in-sample、偏多頭；近似權重 hardcode。forward L4 base=27%。

## Key Findings

### ① HT 不比 ext_long 強（用戶假設反了）
| 訊號 @09:30 | r(forward L4) | Q5 lift |
|---|---|---|
| **ext_long(W50 tanh)** | **+0.224** | **+20%** |
| HT5 lin | +0.206 | +17% |
| HT10 lin | +0.199 | +15% |
| HT15 lin | +0.201 | +17% |
| HT10 等權 | +0.061 | +6% |
| TX 自身 09:30 擺幅 | +0.214 | +23% |
- **ext_long 略勝所有 HT 版本。** 等權 HT 幾乎無效(+0.06)→ 確認「權重集中」才是 HT 訊號來源。

### ② ext_long **subsume** HT（方向與用戶假設相反）
- r(HT10, fwdL4)=+0.199 → **控制 ext_long 後 partial=+0.044**（HT 幾乎不再貢獻）。
- r(ext_long, fwdL4)=+0.224 → 控制 HT10 後 partial=**+0.114**（ext_long 仍貢獻）。
- corr(HT10, ext_long)=+0.764（高度相關）。
→ **是 ext_long 涵蓋 HT，不是 HT 涵蓋 ext_long。**

### ③ ★套套邏輯防護：HT 更像「指數的鏡子」
- corr(HT10, TX 自身擺幅)=**+0.591**（HT 大半就是指數動能）。
- 控制 TX 自身擺幅後：HT10 partial=**+0.091**、ext_long partial=**+0.132**。
→ 兩者都掉約一半，但 **ext_long 保留更多真正的 forward(跨截面)資訊；HT 更接近「重算已漲幅度」**。

### ④ 但原始動機（窄基日）成立
- 2026-02-25：ext_long=**−0.128**（漏掉）vs **HT5=+0.181、HT10=+0.135**（翻強），TX 達 L5(1.48×)。
→ **HT 確實抓得到 ext_long 漏掉的窄基重權值日**——只是這類日子是少數，不足以讓 HT 整體更強。

## Vs. Expected
- 用戶「HT 更強、subsume ext_long」：**不支持，且方向相反**（ext_long 更強且 subsume HT）。
- HT 更套套邏輯（corr TX-own +0.59、控制後保留較少）：符合事前防護的擔憂。
- 窄基日 HT 翻強：符合原始動機，但屬少數尾部。

## Gate Decision（待使用者裁決）
命中 **Invalidation #1**（HT 不優於 ext_long）+ subsume 反向。**「HT 更強」不成立。**
但 HT 在窄基重權值日（2/25 類）補到 ext_long 的漏 → **「互補-覆蓋」有殘值**（非更強，是補不同的少數日）。

- [x] **Archive（「HT 更強」否證）— 使用者裁決 2026-06-09**
- [ ] ~~改判互補~~（OR-合成只多抓 3 天乾淨案例，價值太薄，未採）
- [ ] 修改假設

## Derived Hypotheses
- **H113-d1**：OR-合成「ext_long 強 或 HT 強」是否提升「大漲日覆蓋率」（犧牲一點精度換 2/25 類尾部）？
- **H113-d2**：TX 自身 09:30 擺幅 r=+0.214≈ext_long → 「指數自身早盤動能」本身就是個基準預測；
  個股訊號要證明價值，需穩定贏過這條 TX-only 基準（控制後 ext_long +0.132 是它的真正增量）。

# Distribution Research Results: 利潤集中度（Profit Concentration / Pareto）

## Date
2026-06-08

## Conditions Tested
- 診斷 EstHL（趨勢型）、Reversal（均值回歸型）全期 trade log（2021–2026）報酬集中度。
- A. 自身集中度：top-K 佔 gross profit、剔每年 top-N、Gini、最大贏家/均贏、skew。
- B. 對市場大動日依賴：策略 PnL vs 台指 |日盤 move|、剔市場大動日後 edge。
- benchmark：同 N/μ/σ 常態模擬 top5 share（防機械效應）+ 市場 buy-hold 自身集中度。
- 腳本：`explore.py`；trade log：output/s001_esthl_2021-01-01.csv、s002_reversal_2021-01-01.csv

## Sample
- EstHL N=170（淨利 +27.0%、勝率 59%）；Reversal N=508（+10.0%、45%）；市場日報酬 N≈1300；2021–2026。

## Key Findings

### A. 集中度真實且超 benchmark（非機械效應）✅
| | 最大/均贏 | skew | Gini(gross) | top5 佔gross | 剔每年top-5後淨利 | benchmark p(真≥模擬) |
|---|---|---|---|---|---|---|
| EstHL | 4.1x | 0.75 | 0.410 | 16% | **+2.0%（8% of 原）** | 0.99 ✔ |
| Reversal | 7.8x | 1.45 | 0.508 | 12% | **−16.4%（轉負）** | 1.00 ✔ |

- **剔每年 top-5 獲利交易：EstHL 只剩 8% 淨利、Reversal 直接轉負（剔 top-3/年就翻負）** → 兩策略年度淨利都高度集中於少數大贏家，「少數大日 carry 全年」**成立**。
- **benchmark 守門過關**：真實 top5 share（16%/12%）顯著超同 μ/σ 常態模擬（13%/6%），p=0.99/1.00 → 集中度是**真實右尾肥尾**，非「剔贏家必降」的機械廢話。
- **但子假設「趨勢型比均值回歸型更集中」反向錯誤**：Reversal 更集中（Gini 0.508>0.410、skew 1.45>0.75、剔 top-3/年即轉負）。集中度由**勝率/賠率輪廓**決定（Reversal 低勝率 45% 靠少數大贏家），非趨勢 vs 均值回歸。

### B. EstHL 是「波動日收割者」，靜日虧錢 ✅（最可行動）
| 市場\|move\|四分位 | \|move\|中位 | EstHL 均PnL% | EstHL 勝率 | Reversal 均PnL% |
|---|---|---|---|---|
| Q0（靜） | 0.13% | **−0.041%** | 44% | −0.019% |
| Q1 | 0.37% | −0.009% | 48% | −0.014% |
| Q2 | 0.66% | +0.128% | 60% | −0.033% |
| Q3（大動） | 1.15% | **+0.552%** | **86%** | +0.145% |

- **EstHL corr(市場|move|, PnL)=+0.566**：Q3 大動日均 +0.55%/勝率 86%，Q0/Q1 靜日**淨虧**（−0.04%/−0.01%、勝率 <48%）。**EstHL 全部利潤來自活躍日，靜日是淨負擔。**
- Reversal corr +0.186（弱），但 Q0–Q2 也都微負，僅 Q3 為正。
- **但剔「每年市場 |move| top-3/5 極端日」EstHL 仍保 94% 淨利** → 依賴的是**廣義高波動 regime（Q3 ~25% 的日子）**，非少數幾個極端日。穩健於極端事件、脆弱於「靜日空轉」。

### benchmark：市場自身超集中
台指日盤 buy-hold 全期日報酬和 −7.1%（盤中漂移為負，漲幅在夜盤）；剔每年漲幅 top-5 日後 −61.8%。市場本身極端集中——策略在盤中負漂移環境中萃取正報酬。

## Vs. Expected
- 「報酬集中、剔 top-N 大幅衰減、超 benchmark」：**符合**（核心成立）。
- 「趨勢型比均值回歸型更集中」：**反向不符**（Reversal 更集中/更脆弱）。
- 「對市場大動日依賴」：**符合且更精確**——依賴廣義高波動 regime，非少數極端日；EstHL 靜日淨虧。

## Gate Decision
[x] **進入 Phase 2**（出場效率 / 讓獲利奔跑）— 集中度確認且超 benchmark（待使用者確認方向）
[ ] Archive
[ ] 修改假設

> **判斷依據**：集中度真實且超 benchmark（p≥0.99）、剔 top-5/年 edge 崩（EstHL 剩 8%、Reversal 轉負）→ 「讓獲利奔跑」的出場研究有實據。**但本研究揭露的最可行動發現是 B（EstHL 靜日淨虧，Q0/Q1 負期望）**，方向上比「放寬 trail」更直接。兩條都值得，待使用者選 Phase 2 主軸。

## Derived Hypotheses
- **H10X-esthl-vol-filter（強，優先）**：EstHL 在市場 |move| Q0/Q1（靜日）淨虧、Q3 才賺 → 用**盤前波動預測濾掉靜日**可能直接提升 EstHL 期望與 Gini。連到既有 NVF [[feedback_night_vol_as_hard_rule]]（夜盤波動硬規則）——可能 NVF 已部分捕捉，需檢查殘留靜日。**這是本研究最大行動產出。**
- **H10X-let-winners-run（Phase 2 本線）**：top-5/年 carry 92% 淨利 → 量大贏家的 MFE 捕捉率，測「Q3 大動日放寬 trail/提高停利」是否提升年度淨利（含 trail 回吐成本 [[feedback_trail_giveback_is_scaleout_cost]]）。
- **Reversal 脆弱性警告**：剔 top-3/年即轉負、Gini 0.508 → edge 樂透型、依賴極少數事件，過擬合/部位風險需正視；real profitable events 樣本極小。
- **集中度由勝率/賠率輪廓決定非趨勢屬性**：低勝率策略(Reversal)天生更集中——評估任何策略脆弱性應看 Gini/剔top-N 而非策略類型。

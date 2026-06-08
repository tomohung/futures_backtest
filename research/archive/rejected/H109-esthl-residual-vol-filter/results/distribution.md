# Distribution Research Results: EstHL 殘留靜日濾網（Residual Quiet-Day Filter over NVF）

## Date
2026-06-08

## Conditions Tested
- EstHL 全期 trade log（output/s001_esthl_2021-01-01.csv，**已含 NVF/OR%/VWAP 等 live 濾網 = 殘留母體** N=170）。
- 盤前可知預測子 panel：night_norm(既有NVF)、前1/3日日盤range%、OR寬度%(08:45–08:57)、|gap|%、前一日VIX。
- 標的：當日 |day move|%（ex-post label）、EstHL ReturnPct%（實際交易結果）。
- Q1 預測子對 |move| 的增量(去 night_norm 殘差)；Q2 對 EstHL PnL 的分桶分離；Q3 濾網淨效果 + 誤殺檢查。
- 腳本：`explore.py`

## Sample
- 全交易日 N=1282（Q1）；EstHL 進場日 N=170（Q2/Q3）；2021–2026；VIX 自 vixtwn。

## Key Findings

### Q1 ✅ 盤前確實能預測當日|move|，且夜盤以外有增量（gate 前置過關）
| 預測子 | corr(pred, \|move\|) | 增量 corr(去 night_norm 殘差) |
|---|---|---|
| night_norm（既有NVF） | +0.121 | — |
| 前1日日盤range | +0.183 | +0.154 |
| OR寬度 | +0.198 | +0.146 |
| \|gap\| | +0.159 | +0.048 |
| **VIX(前日)** | **+0.253** | **+0.236** |

夜盤 range 其實是**弱**預測子（0.121）；VIX/前日日盤range/OR 都更強且增量 → 「夜≠日」屬實，盤前有額外資訊。

### Q2/Q3 ❌ 但盤前預測子撈不回 EstHL 的「淨負」靜日桶
- 對 EstHL **實際 PnL** 的分離力遠弱於對 |move| 的預測：最佳是 **gap**（spear 0.187、去 night 增量 0.135），VIX 僅 0.063（能測 move ≠ 能測 EstHL 獲利）。
- **連最弱的桶都還是正的**：gap Q0 +0.04%/53%；夜盤&gap 雙低交集(N=41) 平均 **+0.038%**（仍正）。

### 濾網淨效果（決定依據）— 濾不出 edge
| 濾掉 | 保留淨利 | 砍掉日淨 | 砍掉 Q3 贏家日 |
|---|---|---|---|
| gap 底10%(<0.07%) | **102%**（27.0→27.6%） | −0.6%（N=17，雜訊） | 2 |
| gap 底25%(<0.24%) | 94% | **+1.7%（砍掉正報酬）** | 6 |
| gap 底40%(<0.42%) | 86% | +3.7% | 9 |

只有砍最底 10% gap 日小賺 +0.6%/5年（N=17 純雜訊）；再多砍就**砍到淨正交易 + Q3 大贏家**，總淨利下滑。

## Vs. Expected
- 「盤前有夜盤外的增量預測 |move|」：**符合**（VIX 增量 0.236）。
- 「可增量分離 EstHL 殘留靜日虧損」：**不符合**——對 EstHL PnL 分離太弱，無淨負桶可濾。
- **核心領悟**：H108 的「靜日=虧」乾淨單調是 **ex-post**（用實現 |move| 分桶）；**ex-ante 盤前預測子太弱，撈不回淨負桶**。EstHL 既有 NVF+OR%+VWAP 已抽乾可預測的波動成分，殘留靜日是**不可約雜訊**。

## Gate Decision
[ ] 進入 Phase 2
[x] **Archive（Rejected）**——殘留靜日 ex-ante 不可約，無增量濾網（待使用者確認）
[ ] 修改假設

> **判斷依據**：proposal 無效條件「可分離但濾掉的含等量 Q3 贏家 / 無增量於 NVF」成立——盤前預測子能測 |move| 但對 EstHL 獲利分離弱、無淨負桶；任何有感濾除都砍掉淨正交易與 Q3 贏家。**EstHL 既有濾網棧已良好調校，殘留靜日損失是交易此策略的不可約成本。** 此為正面確認（既有 NVF 設計穩當），非可改善項。

## Derived Hypotheses
- **VIX 預測 |move| 優於 night-range，但皆不預測 EstHL 獲利**：VIX corr 0.253 vs night 0.121，惟對 EstHL PnL 皆弱（EstHL 獲利取決於趨勢性非單純振幅）。→ 用 VIX 取代/補強 NVF **不會**改善 EstHL（已測否決方向）；但 VIX 對「日振幅預測」本身可能對**其他需要振幅的策略/EstRange 估計**有用，另立假設。
- **EstHL 獲利 ≠ 振幅**：高 |move| 不必然 EstHL 賺（高 VIX 日可能 choppy）。EstHL 真正需要的是「趨勢性/方向延續」而非振幅 → 衍生「盤前趨勢性(非波動)預測子」假設，但先驗低（本 session pattern）。
- **方法論**：ex-post 乾淨的條件分桶（H108 靜日=虧）≠ ex-ante 可濾；驗證 filter 必用盤前預測子重做、看淨效果與誤殺，勿被 ex-post 圖像誤導。延續 [[feedback_excursion_needs_forward_tautology_guard]]。

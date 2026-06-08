# Proposal: 利潤集中度（Profit Concentration / Pareto）

## ID
H108

## Derived From
`research/angell-backlog.md` 候選 **DH-01**（Angell 心法「大行情日集中利潤、別追求每日固定獲利 → 讓獲利
奔跑」）。**性質與 H104–H107 不同**：這是**報酬分佈結構診斷**，非條件訊號，不涉虛無/前瞻陷阱。

## Trading Intuition
Angell：多數獲利來自少數幾天，別追求每日固定獲利。若台指日內策略的年度淨利高度集中於少數交易/
大動日，則：(1) 出場設計必須「讓獲利奔跑」（不可早砍贏家）；(2) edge 偏「樂透型」、依賴少數事件 →
脆弱性 / 過擬合風險警告。本研究量化 EstHL（趨勢型）、Reversal（均值回歸型）的利潤集中度與對市場
大動日的依賴。

## Hypothesis
**零策略診斷**，兩種「集中」都測，並對比 benchmark（避免「剔贏家必降 PnL」的機械廢話）：

**A. 策略自身報酬集中度**：年度/全期淨利高度集中於少數交易——
- 剔除每年 top-N 獲利交易後，年度淨利顯著衰減，**存在使年度轉負的 N\***（樂透型 edge）。
- 趨勢型(EstHL) 比均值回歸型(Reversal) **更集中**（Gini、top-5% 佔比、最大贏家/均贏比更高）。

**B. 對市場大動日的依賴**：策略淨利集中於台指 |日盤漲跌幅| 最大的少數日——
- 剔除每年市場 |move| top-N 大動日的交易後，策略 edge 顯著衰減 → 策略是「趨勢日收割者」。

**benchmark（防機械廢話）**：集中度需對比 (i) 兩策略互比、(ii) 同 N 同總額的對稱/隨機分佈模擬、
(iii) 市場 buy-hold 日報酬自身集中度——只看「剔 top-N PnL 變低」無意義。

## Expected Distribution
- 集中度高，尤其 EstHL：top-10% 交易貢獻多數 gross profit、Gini 高、最大贏家遠大於均贏。
- 剔每年 top-5 後 EstHL 可能接近兩平/轉負（趨勢策略本質右偏）；Reversal 較分散（勝率高、單筆小）。
- 策略 PnL 對市場 |move| 正相關，集中在高波動日。
- benchmark 對比：策略集中度 > 對稱分佈模擬（確認非機械效應）。

## Invalidation Condition
- 報酬**未集中**：剔 top-N 影響小、Gini 接近對稱分佈 benchmark、趨勢型≈均值回歸型 → 「少數大日
  carry 全年」不成立，edge 廣而穩健（這對 EstHL 反而是穩健性好消息，但證偽 Angell 集中論）。
- 對市場大動日**無依賴**：剔大動日 edge 不變 → 非趨勢日收割者。
- 兩種集中都看不到、或集中只是機械效應（不超 benchmark）。

## Notes
- 資料就緒：trade log 已存（H106 重跑）`output/s001_esthl_2021-01-01.csv`、`output/s002_reversal_2021-01-01.csv`；
  市場日報酬從 `ohlcv_1m` 日盤 close→close（或 open→close）算。零新資料。
- 績效用 損益%（對齊 CLAUDE.md）+ 點數兩版。
- 1 筆/日 → 交易≈日；top-N 以「每年」為單位剔除（避免單一年份主導）。
- **這是診斷非 pass/fail edge**：兩種結果都有行動意涵（集中→出場讓獲利奔跑 + 脆弱性警告；不集中→穩健）。
- 若確認集中，衍生「出場效率（big winner 的 MFE 捕捉率）→ 趨勢日放寬 trail 讓獲利奔跑」為 Phase 2
  （需重跑回測產 MFE，連 [[feedback_trail_giveback_is_scaleout_cost]]）。

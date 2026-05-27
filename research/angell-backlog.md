# George Angell 觀點 → 台指當沖假設 Backlog

> 來源：Obsidian `名人觀點/George Angell`（33 講筆記，整理於 2026-05）
> 建立日期：2026-05-27
> 用途：把 Angell 當沖方法中**可量化、可回測**的觀點，整理成候選假設清單，逐一研究。
> 編號規則：表中用 `GA-XX` 作 backlog 代號；正式啟動某項研究、走 `/new-hypothesis` 時才領 `H095+` 的正式序號（並在「狀態」欄回填）。

---

## 候選假設表

| ID | 假設（可測敘述） | Angell 來源 | 對應/重疊現有研究 | 前置準備 | 資料就緒 | 優先 | 狀態 |
|----|----------------|------------|-----------------|---------|:---:|:---:|------|
| **GA-01** | 極端跳空逆勢：`\|今開−昨收\| > 10日均range` 且開盤突破前4日H/L → 反向，停損 ±50% range | Anatomy of Gaps | H033-gap-day-study（**rejected**，需先看為何被否） | — | ✅ | A | backlog |
| **GA-02** | 一般跳空回補：跳空在前日H/L**之內**且 <閾值 → fade 回前日收，估回補機率 | Trends and Gaps | H033（rejected） | — | ✅ | B | backlog |
| **GA-03** | 一日/四日**廣度動能%**（上漲值÷總值）預測台指隔日方向 | One/Four Day Percent | H079✅、H087（rejected） | **PREP-1** 聚合 advancing/declining value | ⚠️需聚合 | A | backlog |
| **GA-04** | 第一腳→第二腳**等幅(±)等時**投射 + 均衡點進場（第二腳常呈 ×2/÷2 時間關係） | Always Measure Price / Trading the Open / 4 Tips | H017-intraday-swing✅、H093/H094、H034-fib（active） | **PREP-2** 波段分段演算法 | ⚠️需腿偵測 | B | backlog |
| **GA-05** | 第二腳**失敗 → 反轉**：時間&價格雙失敗、退回盤整區/跌破0.618 即反手 | When a Trend Fails | H036-trend-exhaustion✅、H040（active） | PREP-2 | ⚠️ | B | backlog |
| **GA-06** | **三次法則**：第三次測試 S/R，突破則續、失敗則反轉 | Rule of Three | H028-breakout-timing（rejected） | PREP-2 / PREP-3 | ⚠️ | C | backlog |
| **GA-07** | **買賣包絡線**預估隔日 S/R 區間（rally/decline/pivot 三日平均）vs EstRange | Buy/Sell Envelopes | EstRange、key_prices | — | ✅ | C | backlog |
| **GA-08** | 當日**高/低點集中於首尾小時**（08:45–09:45 與 12:45–13:45）分佈驗證 | Trends and Gaps / 4 Tips | H018-early-session✅ | — | ✅ | A | backlog |
| **GA-09** | **尾盤趨勢延續**（don't fade final hour）：尾盤突破續行 vs 早盤突破易反轉 | Trading the Final Hour | H030-orblong（active）、H027✅ | — | ✅ | A | backlog |
| **GA-10** | **V/倒V 對稱**：早盤走幅在午後等量回補（±掃停損 overshoot） | Trends and Gaps / 4 Tips | — | PREP-2 | ⚠️ | C | backlog |
| **GA-11** | **關鍵價位掃停損後反轉**：突破昨高/昨低/早盤H/L 數檔後 fade | Rule of Three / 3 Tips | H062-sr-effectiveness（rejected）、key_prices | **PREP-3** 盤中S/R觸碰偵測 | ⚠️ | B | backlog |
| **GA-12** | **期貨溢價/基差背離 → 反轉**（現貨創新高、基差背離殺） | Trading the Final Hour | （TX 特有，無重疊） | **PREP-4** 盤中現貨 TAIEX（目前缺）；日線版可先測 | ❌盤中／✅日線 | B | backlog |
| **GA-13** | **超買超賣指標** `(H−O+C−L)/(2R)` <30偏多 >70偏空，預測隔日（含泰勒三日週期） | 3 Tips for Futures Day Trader | H029-weekday✅、H018✅ | — | ✅ | C | backlog |

**資料就緒圖例**：✅ 直接可跑｜⚠️ 需先做前置準備｜❌ 缺資料、卡關

---

## 前置準備研究 / 基礎建設

這些是「在研究某些假設之前要先做好的其它研究／基礎建設」，多個假設共用。

| 代號 | 內容 | 解鎖假設 | 備註 |
|------|------|---------|------|
| **PREP-1** | 從 `stock_day` 聚合每日「上漲成交值 / 下跌成交值（及量）」→ 新增廣度動能欄位 | GA-03 | 資料已在（`stock_day` 有 `change`+`value`），純 ETL 聚合 |
| **PREP-2** | **波段分段演算法**：自動偵測腿（leg）、均衡點（連續同價收盤）、0.618 回撤 | GA-04 / GA-05 / GA-06 / GA-10 | 先查 H017-intraday-swing-research 是否已有可重用產出 |
| **PREP-3** | 盤中**關鍵價位觸碰 + 反轉**偵測（建在 `key_prices.py` 之上） | GA-06 / GA-11 | — |
| **PREP-4** | **盤中現貨 TAIEX 資料源**（目前只有 `taiex_day` 日線） | GA-12 盤中版 | 需評估資料來源；卡關項。日線基差可先測 |

---

## 優先序建議

- **A（資料就緒、edge 潛力高、重疊低）**：GA-03（先做 PREP-1）、GA-08、GA-09、GA-01
- **B（就緒但需 leg／SR／基差基礎）**：GA-04、GA-05、GA-11、GA-12（日線版）、GA-02
- **C（meta／弱先驗／高重疊）**：GA-06、GA-07、GA-10、GA-13

---

## 重要 Caveats（套用到台指前先記住）

1. **市場與年代差異**：Angell 素材是 1980–90 年代美股 S&P 場內（floor）交易。掃停損、bid/ask 喊價、溢價背離等論述建立在 pit 微結構上；台指是電子盤，現象**可能存在但強度未必相同**——這正是要用台指 tick 實證、而非照搬結論的理由。
2. **時段壓縮**：Angell 的「早盤趨勢 / 午盤震盪 / 尾盤趨勢」對應美股 6.5 小時盤；台指日盤只有 5 小時（08:45–13:45），時段切點需用台指資料重新校準，不可直接套美東時間窗。
3. **已 rejected 的重疊研究**：GA-01/02 跟 H033（gap，rejected）、GA-11 跟 H062（S/R，rejected）重疊——**啟動前先讀對應 rejected 研究的結論**，確認 Angell 版本的差異（更嚴格濾網、不同進出場）是否足以避免重蹈覆轍。

---

## 純心法（不需回測，直接內化，不列入研究序）

- 大行情日集中利潤：多數獲利來自少數幾天，別追求每日固定獲利 → 影響出場設計（讓獲利奔跑）。
- 每日 1–3 筆，單一時段虧 3 次就收手（search-and-destroy days）。
- 進場時機 > 一切：「等待會讓虧損機率指數成長」，寧可對的時機進場犯錯，也別追價。
- 劇本 A / 劇本 B：進場前設想最可能劇本，不照走立刻切換甚至反手。
- 逆向交易後幾乎不會變好 → 該停損就停損。
- 避開低流動性日（台指對應：結算日、長假前最後交易日）。
- 型態衰減（rule 35）：任何連續 2–3 天有效的固定型態，太好猜就會失效 → 已抽成 GA-10 的反向版精神，也是套用所有 confirmed 策略時的警語。

# Proposal: Bull-Trap OR Break（站穩成本之上卻向下突破開盤區間）

## ID
H122

## Derived From
Origin（原創觀察）。概念上與 orb_est_hl_exit（ORB 進場）、H092（reach 方向對稱性）、
ladder reach 系列（H095 / vix_regime）共用既有的 OR / EmaHL / ladder 定義。

## Trading Intuition
開盤（08:45 第一根 open）站上「昨日與前日的日盤 VWAP（成本）之上」，照理是偏多/強勢的開局。
但若在 08:58–09:15 這段早盤進場窗內，行情反而**向下跌破開盤區間（OR, 08:45–08:57）的低點**，
代表多方在成本之上承接失敗、形成「假強勢 / bull trap」。
觀察這種「站穩成本卻反向破底」的日子，後續往下走的力道有多深——
用 ladder（EmaHL 倍數）量化跌破點之後的下行 reach 達成比例。

## Hypothesis（Phase 1 後改寫為資料支持的方向）

> 原始假設（已被資料否定）：開高走低破底 → 下行 reach 顯著偏深。
> 實測為**反向**，故改寫為下列 Confirmed 版本。

**開高走低型破底**（開盤 > 昨日日盤 VWAP 且 > 前日日盤 VWAP，且 08:58–09:15 收破 OR low）的
下行 reach 有明確上限、**不該期待深跌**：無條件 L3≈48% / L4≈20% / L5≈9%，
且碰 L3 後續走 L4 僅 ~41% → **看到 L3 即了結**。

相對地，**開盤在成本之下的弱勢破底**（破 OR low 但 open 未站上昨+前日 VWAP）reach **顯著更深**：
L3≈62% / L4≈35%，碰 L3 後續走 L4 達 ~57% → **值得抱續跌**。

跨 2021–2026 六年方向一致（成本上破底在 L4 達成率從不深於成本下破底）。

## 定義（本假設採用）

### 篩選條件（事件日）
1. **成本條件（AND）**：`session_open > VWAP(昨日, 日盤)` 且 `session_open > VWAP(前日, 日盤)`
   - session_open = 當日 08:45 第一根 1 分 K 的 open
   - 日盤 VWAP = `SUM(close×volume)/SUM(volume)`，時間窗 08:45–13:45（沿用 key_prices.py 定義）
2. **開盤區間 OR**：08:45–08:57 的 high/low（沿用 orb_est_hl_exit 定義）
3. **向下突破事件**：在 08:58–09:15（進場窗）之間，存在某根 1 分 K **close < OR low**
   - 取第一次觸發的時間/價作為事件錨

### Ladder reach（running-high anchored，往下）
沿用既有 H092 空頭 ladder 標準定義：錨點 = 當日最高點（running high）。
達成判定：`low ≤ running_high − m × EmaHL`（從高點往下回落 m×EmaHL）。

| 階 | m（×EMA20 EmaHL，暫定） | 名目達成率參考 |
|---|---|---|
| L1 | 0.385 | ~90% |
| L2 | 0.497 | ~75% |
| L3 | 0.711 | ~50% |
| L4 | 0.977 | ~25% |
| L5 | ~1.30（暫定，Phase 1 確認） | ~10% |

- EmaHL = 日盤振幅的 EMA20（沿用 estimate_hl.py / runner.py 既有計算）
- reach 統計窗：突破事件發生後 ~ 日盤收盤（13:45）；亦記錄各階首次達成時間（沿用 ladder timing map）

## Expected Distribution
- 事件日樣本：預期數十～百筆等級（成本之上 + 早盤破底是相對少見的組合）
- 若假設成立：事件日的 L3/L4/L5 達成率應**高於**對照基準
  - 基準至少兩種：(a) 全體交易日無條件向下 reach 分佈；(b) 同樣早盤破 OR low、但**開盤不在成本之上**的日子（隔離「站穩成本」這個條件的增量）
- 預期看到右尾較厚（深跌日佔比上升）

## Invalidation Condition
- 事件日 L3/L4/L5 達成率與基準分佈**無顯著差異**（差距落在洗牌/IID 虛無分佈的誤差帶內）
- 或樣本數過少（< 30 筆）以致無法得到穩定結論 → 標記 Inconclusive
- 或「站穩成本」相較「不站穩成本」的破底日**沒有增量**（代表真正起作用的只是破 OR low，VWAP 條件無貢獻）

## Notes
- 對照虛無分佈必做（feedback：條件統計需對比正確 null，否則描述性相關被誤當 edge）。
- regime confound 提醒：OOS(2026-03~06) ≡ 高波 regime，事件日若集中於此需標註。
- L5 倍數待 Phase 1 以實際分佈校準後固定。
- 方向命中（深跌達成）≠ 可交易 P&L；本假設 Phase 1 只描述 reach 分佈，進出場留待 Phase 2。

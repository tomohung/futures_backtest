# Proposal: 淨空開盤裸突破（Clear-Runway Breakout）

## ID
H102

## Derived From
- H095（reach ladder）的 distribution 階段 — 沿用 `L_i = c_i × EMA20(日盤振幅)` 的階梯距離定義當「尺」
- H037（VWAP cost basis）— 昨/前日 VWAP 成本當「明顯支撐壓力」

## Trading Intuition
現行開盤突破策略（S001-esthl / ORB）掛了一整套濾網（NVF 夜盤波動、VWAP 方向、30K 20MA、OR 寬度、週幾排除…）。

觀察：當今天開盤離昨日與前日成本（VWAP）夠遠、**某一個方向上沒有近端的明顯成本 S/R 擋路**時，那個方向就有乾淨的延伸空間（沒有成本磁吸 / 沒有成本壓力帶要穿）。直覺上，這種「淨空跑道」本身就可能是一個夠強的突破條件——也許不需要 EstHL 那整套濾網。

關鍵是**單邊、方向性**的：不是上下都要淨空，只要**有一邊**沒有成本擋路，就有機會往那邊走。

## Hypothesis
以 H095 reach 距離為尺，定義單邊淨空：

```
cost = {vwap_last, vwap_prev}            # 昨日、前日日盤 VWAP（08:45–13:45）
above = open 之上的 cost ；  below = open 之下的 cost
up_clearance  = min(above) − open        （上方無 cost → +∞，完全淨空）
dn_clearance  = open − max(below)         （下方無 cost → +∞）
EMA20         = H095 日盤振幅 EMA20（causal，不含當日）
up_clear_norm = up_clearance / EMA20
dn_clear_norm = dn_clearance / EMA20

上方淨空 = up_clear_norm > 門檻  → 可做「上破」（close > OR_high 進多）
下方淨空 = dn_clear_norm > 門檻  → 可做「下破」（close < OR_low 進空）
```
- `open` 用日盤 08:45 開盤價（盤前 VWAP 已知，08:45 即可判定，不需等 OR 完成）。
- OR 區間沿用現有機制：08:45–08:58。
- 門檻 **L4(0.977) / L5(1.225) 兩階都跨**，當分層變量看單調關係。

**陳述**：在「該方向淨空」的日子，該方向的 reach ladder 達標分佈（up_max / dn_max 走到 L1–L5 的比率）顯著優於 baseline（全日 / 非淨空日），且同向延續更乾淨、反咬率更低——足以支撐「只用淨空一個條件做裸突破」（拿掉 EstHL 濾網堆疊）。

## Expected Distribution
- 淨空程度（clear_norm）越大 → 該方向 reach 達標率（尤其 L3/L4）單調上升。
- 淨空日相對非淨空日：同向延續比率更高、反咬率（破多後反轉去碰下方 L_i）更低。
- 開盤**夾在兩成本之間**（一上一下、兩邊 clearance 都小）→ 多半不符合任一邊 → 預期是洗盤日，reach 達標低。
- 開盤**跳空在兩成本之外**（單邊 clearance = ∞）→ 預期最強的同向延伸。

## Invalidation Condition
符合以下任一即視為（至少在此定義下）不成立：
- 淨空日的該方向 reach 達標率（特別是 L3）相對 baseline 沒有有意義的提升（差距在樣本誤差內）。
- clear_norm 與 reach 達標率之間**沒有單調關係**（淨空程度不帶資訊）。
- 淨空日的反咬率不低於、甚至高於 baseline（淨空≠乾淨，反而更容易假突破）。
- 符合條件的樣本數過少，無法得出有統計意義的結論（見 GATE 門檻）。

## Notes
- **與 NVF hard rule 的張力**：本研究刻意做「裸突破」拿掉 NVF（`feedback_night_vol_as_hard_rule` 記為硬規則）。在研究情境下為了乾淨隔離「淨空」這個變量，這樣做是對的（study 非上線）。Phase 1 會**同時記錄淨空日裡的 NVF 分佈**，檢查淨空是否其實隱含高波動（兩者相關）、或淨空能否放寬 NVF。若日後晉升 live，NVF hard rule 仍適用。
- 評估 filter 效果時依 `feedback_filter_eval_includes_streaks` 同時看連敗長度與 drawdown，不只看 PF。
- 沿用 H095 的 ladder 距離計算（`research/active/H095-reach-ladder-exit/` 內的腳本）保持定義一致。
- VWAP 成本計算對齊 `src/analysis/key_prices.py` 的 vwap_last / vwap_prev（08:45–13:45 成交量加權）。

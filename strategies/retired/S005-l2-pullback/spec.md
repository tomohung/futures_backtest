# Strategy Spec: L2 拉回續攻 — 拉回站回 5MA 續攻 L2→L3

> ## ⛔ RETIRED 2026-06-15 — 前視偏誤
> 原 Confirmed 績效是 ZigZag leg 終點 `em`（未來資訊）造成的假象。causal 重寫後 Sharpe 0.04、
> 無可部署 edge。詳見 performance.md banner 與 H120 causal_validation.md。
> 下方規格僅留存記錄；策略已移至 `strategies/retired/`。

## ID
S005

## Source Hypothesis
H120-l2-pullback-continuation（research/active/，Confirmed 2026-06-14）

## Description
波段達 L2 確立方向後，等一個小回檔、收盤站回 1 分 K 5MA 再進場，吃 L2→L3 的續攻段（有機會延伸 L4/L5）。高勝率、低賠率 profile；賠率靠「拉回深度」放大並據此分級加碼。多空皆做（空方略強）。

## Entry Conditions
1. **階梯單位**：EMA20 = 前 20 日日盤(08:45–13:45)振幅的 causal EMA；L2=0.497×EMA20、L3=0.711×EMA20。
2. **波段偵測**：L2 門檻 ZigZag 切 leg（反轉門檻 = L2 距離）。
3. **趨勢確立**：leg ext 自錨點（起漲低/起跌高）達 L2 距離。
4. **拉回**：確立後出現反向回檔，幅度 ≥ 0.05×EMA20（雜訊地板）且 < L2（≥L2 即翻向作廢）。
5. **進場觸發**：拉回後**第一根收盤站回 1 分 K 5MA**（多：前收<5MA 且 收>5MA；空對稱）→ 該根收盤價進場。每段一筆。
6. **過濾**：
   - 進場時間 **≤ 12:00**（午後尾盤幾乎無 edge）。
   - **拉回深度 ≥ 0.25×L2**（前峰−拉回極值；濾掉淺拉回，avgR 僅 0.08、占 46%）。
   - guard：leg 直衝 L3（確立後未拉回就到 L3）不交易；進場那根已破 L3（overshoot）不交易。

## Exit Conditions
- **停損**（固定，碰 L3 前不移動）：`stop = 拉回極值 − 0.75×(拉回極值 − 錨點)`（多；空對稱）= 偏趨勢起點的寬結構停損。
- **停利**：目標 L3 = 錨點 ± L3 距離，到價全出。
- **抱尾變體（選用）**：達 L3 後改 trail 0.5×L3 博 L4/L5（總點數×1.3、Sharpe 略降）。
- **時間停損**：13:45 收盤平倉。

## Parameters
| Parameter | Value | Sensitivity |
|---|---|---|
| 反轉/確立門檻 L2 | 0.497×EMA20 | — |
| 目標 L3 | 0.711×EMA20 | — |
| 拉回雜訊地板 | 0.05×EMA20 | Low |
| 停損 alpha | 0.75 | Medium（緊停會被巴；0.75~1.0 區間穩） |
| 進場時間上限 | 12:00 | Low |
| 最小拉回深度 | 0.25×L2 | Medium（決定量/質取捨） |
| 成本假設 | 3 pt round-trip | Low（≤6pt 仍正） |

## 加碼（依拉回深度，綁賠率非勝率；兩階）
| 拉回深度(÷L2) | 占留存 | avgR | 倉位 |
|---|---|---|---|
| <0.25 | — | 0.08 | 不交易（已過濾） |
| 0.25–0.5 | 77% | 0.23 | ×1（基準） |
| ≥0.5 | 23% | 0.68–0.90 | ×2 |

> 0.5 是清楚分水嶺（avgR 0.23→0.68 跳一倍多）。不再切 ≥0.75 獨立階（僅 38 筆、屬噪音）。
> 過濾與加碼是兩件事：過濾＝要不要做（≥0.25）；加碼＝做多大（≥0.5 加倍），留存內仍高度不均。

## Universe
- 交易標的：TX 台指期日盤（08:45–13:45）。
- 排除：無（多空皆做）。

## Execution
- 頻率：日內，1 分 K。
- 下單時機：站回 5MA 的那根**收盤確認**才進（非重繪）。
- 倉位大小：基準 1×，依拉回深度加碼至 2~2.5×。

## Constraints
- 單筆最大風險：進場−停損（隨拉回深度，深拉回風險較小）。
- 進場上限 12:00；每段一筆。

## Source Code
- Backtest：`strategies/live/S005-l2-pullback/backtest.py`（= research/active/H120 的回測腳本）
- chart-ui service：`src/chart_ui/services/h120.py`（單一真相源，route /api/h120 + builder 共用）
- chart-ui 指標：主圖 legend「L2拉回續攻」+ 清單 `h120-l2-pullback`
- Pine Script：`indicators/tradingview/swing_levels_tx.pine`（H120 圖層，預設關）

# Proposal: Reversal 方向濾網替換（納入夜盤）

## ID
H101

## Derived From
S002-reversal（live 策略）的方向濾網設計。
Origin：對「方向濾網是否應納入夜盤、是否該用更長/更穩定的趨勢判斷」的探討。

## Trading Intuition
目前 reversal 的方向濾網是 **5m 120MA（只日盤、看斜率方向）**：
- 開盤落在 BC zone（昨/前日法人 VWAP 區間）內時，這條 MA 的斜率是當天做多/做空的唯一依據；
- 開盤在區間外時，方向仍需與斜率一致。

兩個疑慮：
1. **只用日盤**可能讓方向判斷在開盤初期不穩定（日盤剛開、5m 樣本少、易受跳空影響），而夜盤其實已經反映了隔夜趨勢。
2. **120 根 5m（≈2 個日盤交易日）的斜率**是否為最適趨勢尺度？換成更直覺的「1 小時級別」趨勢（5m 240MA = 1H 20MA，或 1H MACD）是否更能濾掉雜訊、抓對方向？

## Hypothesis
把 reversal 的方向濾網從「5m 120MA 日盤斜率」改為下列**納入夜盤連續資料**的判斷，能在不顯著減少交易筆數的前提下，改善損益% / Sharpe，並（或）縮短連敗長度與最大回撤：

- **情境 A**：5m 240MA 斜率（= 1H 20MA），連續日+夜盤。
  - bullish = MA5m_240 > MA5m_240_Prev
- **情境 B**：1H MACD 方向（12/26/9，套在 1 小時 K，連續日+夜盤）。
  - bullish = MACD 線 > Signal 線（最後一次交叉後的狀態）
- **情境 C**：A 與 B **同向**才允許進場（其餘條件與 base 相同；方向不一致則當天不做）。

其餘策略邏輯（BC zone gate、BB 兩段進場、SatZone 出場、pivot trail、時間窗）全部維持與 base 一致，**唯一變數是方向濾網**。

## Expected Distribution
- 三種新濾網與 base 在「每日方向判定」上會有一定比例的歧異（預期 20–40% 交易日方向不同或被過濾）。
- 情境 C（雙濾網同向）會減少交易筆數，但預期單筆品質提升（PF、勝率較高、連敗較短）。
- 納入夜盤後，方向判斷在開盤初期應更穩定（較少因日盤跳空而誤判）。

## Invalidation Condition
任一情境若出現以下情況即視為**不優於 base**：
- 損益% 與 Sharpe **均未**改善（兩者都 ≤ base），或
- 雖然單項指標微幅改善，但**連敗長度或最大回撤明顯惡化**（保護心理資本是方向濾網的核心目的，見 memory `feedback_filter_eval_includes_streaks`），或
- 交易筆數縮減到樣本不足以支撐結論（in-sample < 80 筆即視為不可靠）。

三情境若全部 invalid → 維持 base（5m 120MA 日盤），假設 rejected。

## Comparison Metrics（GATE / Verdict 標準）
1. **損益%**（= 損益點數 / 進場價 × 100）與基於損益% 的 **Sharpe** — 主指標
2. **PF + 勝率**
3. **最大連敗長度 + 最大回撤** — 心理資本保護
4. **總交易筆數** — 樣本量 / 濾網鬆緊度

四個變體（base / A / B / C）並排比較，並做 in-sample vs out-of-sample 分割驗證。

## Notes
- 新濾網的 5m 240MA 與 1H MACD 一律用 `ohlcv_1m` 全時段（日盤+夜盤）連續資料計算，跨夜累積；shift 避免未來函數。
- base 仍為 `load_data_for_reversal()` 內的 5m 120MA（日盤）。
- 實作時新增資料載入欄位（MA5m_240 / MACD_1h / Signal_1h），策略以參數切換方向濾網來源，便於四變體共用同一回測腳本。

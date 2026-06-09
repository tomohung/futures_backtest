# Proposal: 重權值推力（Heavyweight Thrust）— 更強的多方 reach 預測子？

## ID
H113

## Derived From
H111-dci-long-reach-map（多方地圖）+ chart-ui 2026-02-25 案例觀察（ext_long 漏掉窄基重權值大漲日）。

## Trading Intuition
H111 的 ext_long = **value-weighted tanh 於前 50 大型股**（廣度版、tanh 飽和刻意防單股綁架）。
但 2026-02-25 實例：TX 漲到 **L5（1.48×EMA20）**，ext_long 整天弱（峰值 +0.045）——那天是
**窄基重權值/AI 類股拉抬**（鴻海 2317、廣達 2382 猛漲），但多數龍頭在跌（top-50 m_i 中位 −0.14），
tanh 平均被一堆下跌股拉低。**指數（市值集中、台積電 ~30%）漲了，廣度版卻看不到。**

直覺：TX 本質是**市值權重集中**的，少數重權值的動向就決定指數。所以「**忠於指數權重、不被 tanh 封頂的
重權值推力**」可能比廣度 tanh 版更貼近指數 reach——不只是補漏，而是**根本更強的多方指標**。

## Hypothesis
定義 **HT（heavyweight thrust）= 前 5~10 大權值的 (p@t−open)/range_i，用近似指數權重加權、不 tanh 封頂**（linear）。
> H1：HT(09:30) 對上行 **forward L4** reach 的鑑別力 **≥ 廣度 ext_long(W50 tanh)**；
> 且 **HT 大幅 subsume ext_long**（控制 HT 後，ext_long 的邊際貢獻趨近 0）→ 用戶假設「更強、非互補」成立。
> 並能抓到 ext_long 漏掉的窄基重權值大漲日。

**⚠ 必做的套套邏輯防護**：cap-weighted HT 會**逼近「TX 自己的 09:30 上行動能」**（因 TX≈市值權重股價和）。
必須**控制 TX 自身 09:30 已成擺幅**，檢驗 HT 預測的是 **forward(09:30 後)** reach，還是只是把「已經漲的幅度」重算一遍。
若 HT 的優勢在控制 TX-自身動能後消失 → 它只是指數的鏡子、非更強預測，假設**不成立**。

## Expected Distribution
- HT 對 forward L4 的 corr/lift ≥ ext_long（用戶預期更強）。
- HT-vs-ext_long 迴歸：HT 顯著、ext_long 邊際趨近 0（subsume）。
- 2/25 類窄基重權值日：HT 翻強（而 ext_long 弱）。
- **但**控制 TX 自身 09:30 擺幅後，HT 的 forward 增益**部分縮水**（套套邏輯成分）。

## Invalidation Condition
任一成立 → 用戶「HT 更強」假設不支持：
1. HT 對 forward L4 reach 鑑別力**不優於** ext_long。
2. 控制 TX 自身 09:30 上行擺幅後，HT 的 forward 預測力**歸零**（純套套邏輯、只是重算指數）。
3. HT 未 subsume ext_long（兩者實為互補，控制彼此後都仍顯著）→ 則回到「互補」結論（用戶假設被否、但有別的價值）。
4. HT 在窄基日（如 2/25）也沒翻強 → 連原始動機都不成立。

## Notes
- **無真實市值欄**：cap-weight 近似——hardcode 近似 TAIEX 前 ~15-20 權重 list（公開可得，2330~30% 等），
  或測權重來源敏感度（官方近似 vs 成交值近似 vs 等權）。這是關鍵設計變數。
- HT 寬度掃 top-5/10/15；飽和：linear vs tanh（驗證「不封頂」是否真的更好）。
- 沿用 H111：檢查點 09:01-09:30、五分位、**forward-guarded**、附 N、連續擺幅；可重用 `extension.py`/H111 `explore.py`。
- 硬限制：上市-only、181 日、偏多頭、無 OOS。
- 若 HT 確實更強且非套套邏輯 → chart-ui 的「延伸力·多」可改用 HT（或並列），並回頭修 H111 結論。
- 與 [[project_dci_is_extension_signal]] 一致：仍是延伸/順勢訊號族。

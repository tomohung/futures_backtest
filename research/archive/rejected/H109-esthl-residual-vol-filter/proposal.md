# Proposal: EstHL 殘留靜日濾網（Residual Quiet-Day Filter over NVF）

## ID
H109

## Derived From
H108（利潤集中度）的 distribution 階段：EstHL 為波動日收割者，市場 |日move| 靜日(Q0/Q1)淨虧、
大動日(Q3 +0.55%/勝率86%)才賺，corr +0.566。

## Trading Intuition
EstHL **已有重度波動/方向濾網**：夜盤波動 NVF（H066/H075，tonight_range/EMA20≥~0.93）+ 週二 bypass
（H078）+ OR% 寬度(0.3–1.0%) + VWAP + 30m-MA 方向 + 跳過週四五。H108 的「靜日淨虧」是**這些濾網跑完
後的殘留**。既有 NVF 用**夜盤**波動當預測子，但**夜盤活躍 ≠ 日盤活躍**——可能有一批「夜盤夠活躍而
通過 NVF、但日盤實際很靜」的殘留日，EstHL 在其上空轉虧損。

## Hypothesis
**存在盤前可知的波動預測子，能在既有 NVF 之上、增量地分離出 EstHL 虧損的殘留靜日盤，且不誤殺
Q3 大贏家。**

**關鍵 lookahead 防呆**：H108 用的是當日 |day move|（盤後才知），**不可當濾網**。本研究只用**盤前/
進場前可知**的預測子 panel：
- night_norm（既有 NVF 的夜盤 range 正規化）— 當 baseline
- 前 1–N 日「日盤」range / ATR（日盤波動 ≠ 夜盤波動）
- OR 寬度（08:45–08:57，EstHL 已部分用 OR%）
- 開盤 gap 大小
- VIX / TW-VIX（若資料就緒）

**陳述**：上述某預測子（或組合）對「EstHL 進場後是否落在靜日盤虧損」有**增量於 night_norm** 的分離
力；據此加濾網可提升 EstHL 期望/Gini，且剔除日不集中於 Q3 贏家。

## Expected Distribution
- 若日盤波動有「夜盤測不到」的可預測成分（如前日日盤 range、VIX 帶額外資訊）→ 殘留靜日可分離，期望提升。
- 效率市場 / 已過濾先驗：EstHL 已被 NVF+OR%+VWAP 重度過濾，殘留靜日多為**不可預測雜訊** → 無增量預測子（傾向此結果，需誠實面對）。
- 即使可分離，需檢查濾網是否同時砍掉 Q3 贏家（淨效果才算數）。

## Invalidation Condition
- **無預測子在 night_norm 之上帶增量分離力**（殘留靜日虧損對所有盤前預測子皆不可分）→ 殘留靜日為
  不可約雜訊，「再加靜日濾網」無效，H108 的靜日虧損是交易 EstHL 的必要成本。
- 可分離但**濾掉的日子也含等量 Q3 贏家** → 淨期望不升（filter 砍好砍壞各半）。
- 增量效果在 OOS 崩潰 / 僅來自少數年份（對齊本 session 教訓，需 IID/OOS 對照）。

## Notes
- 資料：EstHL trade log（output/s001_esthl_2021-01-01.csv，**已含 NVF 等 live 濾網**，即殘留母體）；
  夜盤/日盤 range、OR、gap 從 ohlcv_1m；VIX 查 daily_range.py 來源是否可取。
- **這題的判斷依據是「增量於既有 NVF」**：不能只看「靜日虧」（H108 已知），要看盤前預測子能否**事前**
  分出來且增量。沿用 [[feedback_excursion_needs_forward_tautology_guard]] 精神：對照正確 baseline（night_norm）。
- 評估 filter 必含連敗/DD（[[feedback_filter_eval_includes_streaks]]）、且 regime 思維為降強度而非全停
  （[[feedback_regime_modulate_not_block]]）。
- 若成立 → Phase 2 把濾網加進 EstHL backtest，OOS/walk-forward；若否 → 確認殘留靜日不可約，回饋 H108。

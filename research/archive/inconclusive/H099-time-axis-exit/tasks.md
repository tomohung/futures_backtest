# Tasks: 時間維度出場（碰 L3 後 Dow trail 的時間閘）

## Phase 1: Distribution Research

- [x] 取 L3-reacher 多單母體（沿用 H095「守初始SL 抱到 L3」清單，全期 2021–2026）→ N=120
- [x] 對每筆記錄：碰 L3 的時刻 t、是否續到 L4/L5、碰 L3 後最大延伸幅度（×EMA20）
- [x] 以 t 分桶（事前登記），算各桶 N、P(L4|L3)、P(L5|L4)、中位延伸 → 中位延伸單調衰減 0.46→0.05
- [x] 控制變數檢查：固定 DCI band 內時間衰減仍存在 → 非 DCI 代理（無效條件 #2 不成立）
- [x] 量「碰 L3 後最高水位回吐」分佈 → 早盤即 ~0.24×EMA20、弱 DCI 達 1.19（見 distribution.md）
- [x] 視覺化：results/time_decay.png（P(L4|L3) bar + 中位延伸 line）

---
### GATE
**問題：時間軸是否有獨立的出場價值，值得進入回測？**

- 各時間桶 N 是否足夠區辨？（最低門檻：**每桶 ≥ 20 筆**，全母體 ≈119 需注意尾桶過稀）
- P(L4|L3) / 中位延伸是否隨時間單調衰減、且幅度超過噪音？
- 控制 DCI band 後，時間衰減是否仍存在（非 DCI 代理）？
- 是否有明顯 data snooping 疑慮（分桶界線是否事後挑選）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義候選規則：(A) 後半場閘 T（t>T 不到 L4 → 降 5MA/靜態）；(B) 結構停滯 N 根無新高 pivot low → 降檔
- [ ] 設定回測參數（手續費、滑價；buffer 沿用 H095）
- [ ] in-sample：比較「純 Dow trail」vs (A) vs (B) vs (A+B) 的平均%、carry-from-L3-high 回吐、尾盤反轉次數、連敗長度、max DD
- [ ] out-of-sample 驗證（train ≤2024 / test ≥2025，沿用 H095 切法）
- [ ] T 與 N 的參數敏感度分析（避免單點過擬合）
- [ ] 結論：時間閘是否在不犧牲長尾的前提下，改善回吐／尾盤反轉／心理軸

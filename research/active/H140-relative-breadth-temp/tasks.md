# Tasks: 相對廣度溫度 —— S002 Reversal 的 regime 閘門

## Phase 1: Distribution Research

- [x] 建 `explore.py`：計算因果版 `pct1y`（rolling 250，僅比對過去），與 S002 trades 對齊
- [x] 母體確認：2021-01-28 ~ 2026-07-30，S002 live 參數，**N=518 筆**（524 扣 6 筆暖機不足）
- [x] `pct1y` 五分位 × 每筆點數 / 勝率 / 累積點數分佈
- [x] **增量檢定（H140-B，本階段核心）**
  - [x] 溫度 × `ret20` 正負 2×2 交叉，看子格內差距
  - [x] 溫度 × 20 日波動高低 2×2 交叉
  - [x] 只用趨勢濾網 vs 只用溫度濾網 vs 兩者併用，三者比較
- [x] **穩健性**
  - [x] 逐年拆解（熱桶 / 冷桶），檢查單年主導程度
  - [x] leave-one-year-out：逐一剔除單年後熱桶期望值是否仍為正
  - [x] 門檻敏感度：p65 / p70 / p75 / p80 / p85 / p90 掃描，看是否單調
  - [x] 回看窗敏感度：125 / 250 / 375 交易日
- [x] 視覺化：pct1y 時序 + S002 逐筆損益疊圖（標出 2026-06/07 斷點）

→ 結果：`results/distribution.md`、`results/*.csv`、`results/h140_distribution.png`

---
### GATE　✅ 2026-07-31 通過
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？→ 熱桶 N=135 ✅；最小引用子格「熱×跌勢」N=33 ✅（勉強）
- 分佈方向是否符合預期？→ pct1y 前四桶全負、最高桶 +21.7 ✅
- **增量是否存在？** → 四個控制格差距 +16.4 ~ +40.4，全部同向 ✅
  且只用溫度（+3055 點 / maxDD −777 / 連敗 5）優於只用趨勢（+2526 / −1319 / 9）
- 是否有明顯的 data snooping 疑慮？→ 門檻 p65~p85 單調成平原；LOO 全部維持正 ✅

**保留**：IS 期不顯著（+7.2，p=0.378）；效果強度集中 2025–2026；p 值因自相關應視為樂觀

**決定：** [x] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] 建 `backtest.py`：post-processing 設計（沿用 H079-K 的 `h079k_filter.py` 模式，不改 S002 原碼）
- [x] **修正 Phase 1 的 lookahead**：改 LAG=1（D 日只用 D−1 為止的溫度），並保留 LAG=0 對照
- [x] **改用 `ret_pct = PnL/EntryPrice×100`** 做跨年度比較（CLAUDE.md 規範）
- [x] 規則 A：`pct1y < 門檻` 全跳過
- [x] 規則 B：`pct1y < 門檻` 減碼（H140-C，0.5x / 0.33x）
- [x] 與 H079 現行絕對門檻 defense filter 併用（C_combo）/ 擇一（H079_only）的比較
- [x] IS（2021–2023）/ OOS（2024–2026）切分驗證
- [x] Walk-forward：逐年滾動決定門檻（mean / sharpe 兩種目標函數）
- [x] 評估指標含 Sharpe（依實際交易頻率年化）、**MaxDD、最大連敗長度**
- [x] 參數敏感度分析（門檻 × 回看窗，36 格）

→ 結果：`results/backtest.md`、`results/bt_*.csv`

**Verdict：Confirmed（僅限 `B_scale` 降強度形式）** —— 待使用者最終確認

關鍵發現：
- 參數敏感度 36/36 格全正；修掉 lookahead 後仍成立（total_ret 9.3% vs baseline 5.6%）
- `B_scale_0.33` IS Sharpe 0.03→0.21、OOS 0.55→1.08、maxDD −6.01%→−2.10%
- A（全停）的 walk-forward 退化到只剩 6~14 筆/年，不可操作
- **對照組警訊**：`H079_only` 在 %-基準 + LAG=1 下 Full total_ret 3.6% < baseline 5.6%，
  與 H079-K 既有 confirmed 結論衝突 → 衍生 H144（高優先，需複驗）

---

## Phase 3: 落地（僅在 Confirmed 後）

- [ ] `breadth_thermometer.py` 增加相對溫度輸出（絕對門檻燈號保留）
- [ ] morning_briefing 同步顯示
- [ ] 決定是否寫入 S002 spec.md（與 H079 觀察期決策合併判斷）

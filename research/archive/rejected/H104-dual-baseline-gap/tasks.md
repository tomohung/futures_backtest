# Tasks: 雙基準跳空（Dual-Baseline Gap）

## Phase 1: Distribution Research（純現象，比兩基準預測力）

### 資料準備
- [x] 逐交易日取出四個錨點：T 日 08:45 開、T 日 13:45 收、T-1 日 13:45 收、T 日凌晨夜盤收（**05:00 整點根** 與 **夜盤實際末筆** 兩種都取）
- [x] 確認夜盤跨日 timestamp 歸屬正確（datetime 窗法：前一日盤開盤後、本日盤開盤前的最後一段夜盤）
- [x] 計算兩種跳空：基準 A = 開 − 夜盤收；基準 B = 開 − 昨日盤收（用 adj_close 剔除換倉假跳空；點數 + 除以前10日range 兩版）

### 兩基準是否真有別
- [x] 比較 A、B 兩跳空值的相關性與差異分佈（A−B = 夜盤段走勢）→ corr 0.557、37% 方向相反、median 83pts
- [x] 分桶後計算「同一天被 A、B 歸入不同桶」的比例 → **69.7%**（前提強烈成立）

### excursion 分佈（對稱情境各自實測）
- [x] 定義 excursion：ret_co(收−開)、up_exc(high−開)、down_exc(開−low)，當日盤內
- [x] **跳空向上日**：分別按基準 A、基準 B 分五分位 + 極端尾端，看 excursion 分佈與偏態
- [x] **跳空向下日**：同上，獨立實測
- [x] 比較兩基準下 excursion 對跳空大小的單調性 / 方向偏態強度 → 五分位皆不顯著；極端尾端 A 勝（gap-down 續跌）
- [x] 比較 05:00 整點 vs 夜盤末筆兩種夜盤收取法 → **等價（corr 1.0000）**，定案用 05:00
- [x] 視覺化：results/h104_distribution.png（跳空十分位 × median ret_co、A vs B 散點、夜盤位移分佈）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠分桶比較？（最低門檻：**每個跳空方向 ≥ 200 個交易日**，極端跳空桶 ≥ 30）
- 兩基準是否真有別？（同一天歸不同桶比例需明顯 > 0，否則命題無意義 → Archive inconclusive）
- 哪個基準的 excursion 條件分佈方向性更乾淨？是否強到值得做進出場？
- 是否有 data snooping 疑慮（分桶數、ATR 視窗 N 的選擇）？

**決定：** [x] **修改假設 → Phase 2**（2026-06-08）：改測單側動能延續版，非 GA-01 對稱反轉。

---

## Phase 2: Backtest（錨對照 + H103 濾網移植）

> 方向修正（見 distribution.md「與 H103 的關係」）：**不當獨立 gap 策略硬上**，改成把 H103 的
> `up_clear`（折價深度 + 上方空間）框架平移到**夜盤收錨**，與 VWAP 錨 head-to-head。
> 目的：(a) 驗證夜盤收錨是否比 VWAP 錨更乾淨/穩、能否救起 H103 薄 OOS（OOS PF 1.24）；
> (b) 用 H104 較大樣本檢查 H103「大 gap-down 必彈」是否被 up_clear 過度樂觀。
> **避免重造 H103**：裸跳空 fade（DH-16）不獨立上，必須帶濾網且與 VWAP 版對照。

### 基礎設定
- [x] 移植 H103 進出場框架（reuse h102_daily.csv 的 ema20/vwap/up_clear/n_above）：做多、目標/停損 ×ema20、成本 3 點
- [x] 排除換倉日（N=1247）；IS(21–23)/OOS(24–26) 對齊 H103

### 錨 head-to-head（核心）→ 尺度檢查改寫
- [x] **尺度檢查**：夜盤 gap |norm| 中位 0.146、僅 2.2%≥1.0 → literal anchor-swap 零樣本，改測原生尺度
- [x] **T1 H103 複刻**（VWAP 錨）：PF 1.66/IS2.55/OOS1.15，重現 H103 ✅
- [x] **T2 夜盤錨 fade**（DH-16）：全面負 PF 0.54–0.60 → Rejected（觸價≠成交）
- [x] **T3 夜盤錨 momentum**（修正版假設）：IS 1.87 → OOS 0.98 崩潰 → Rejected
- [x] 門檻/band 敏感度：一致地差（非刀鋒，真無 edge）

### 反例檢查與守門
- [x] **T4 H104⟂H103 加值**：H103 勝組依夜盤跳空方向分 → 夜盤 gap-up 子集 OOS PF 3.62（N=28，薄）
- [x] Walk-forward：T2/T3 OOS 全崩；唯 T4 跨 IS/OOS 一致但樣本小
- [x] Verdict：夜盤收**非更好的獨立錨**（T2/T3 Rejected），但其**符號是 H103 有效濾網**（T4）→ 衍生 H105；H104 自身判 **Rejected**

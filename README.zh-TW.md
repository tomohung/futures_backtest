# futures-backtest — 台指期假設驅動研究系統

台指期（TX）當沖策略研究工具鏈：從期交所原始 tick 檔 → DuckDB → 策略回測，
外加每日自動 ETL 與早盤簡報 email。支援期貨與選擇權（TXO）資料。

**但系統本身不是重點，研究記錄才是。**

> 測試過 140 個假設。**否決 71 個。** 4 個結論不明。52 個確認。
> 全部都還在這個 repo 裡，包括失敗的那些。

*English version → [README.md](README.md)*

---

## 為什麼「被否決的那些」才是重點

跟 LLM 一起工作時，產出一個看起來合理的結果幾乎是零成本：寫個 prompt，拿到一張圖、
一個支持你原本就相信的數字。研究的瓶頸於是從**產出**移到了**否決**——而否決是完全
沒有多巴胺的那一半。

所以這套流程建立在一條規則上，而且在任何程式跑起來之前就強制執行：

> **Step 1.4 — 無效條件：什麼結果代表假設不成立？（必須在開始前就定義）**
> — [`.claude/skills/new-hypothesis/SKILL.md`](.claude/skills/new-hypothesis/SKILL.md)

先寫下什麼會推翻這個想法，才開始探索。接著是 GATE 判定——而 `/backtest` skill 會
拒絕在沒通過 GATE 的假設上執行。結果就是 `research/archive/rejected/`：71 個在我腦中
很有道理、碰到資料就沒撐過去的想法。

71 否決比 52 確認——這是我希望讀者看的數字。**一份沒有失敗紀錄的研究記錄，不是研究記錄。**

挑三個，看看實際長什麼樣：

- [**H041** — 否決](research/archive/rejected/H041-reversal-skip-after-breakout/summary.md)。
  我很確定這些日子是壞交易的來源，想把它們濾掉。結果它們是**表現比較好**的日子
  （勝率 50% vs 43%）。假設不是被修正，是被反轉。
- [**H083** — 正式研究還沒開始就否決](research/archive/rejected/H083-lagged-concentration-vol-prediction/summary.md)。
  兩支探索腳本就已經提供決定性證據，Phase 1 從未執行。GATE 的作用是**及早停損**，
  不只是事後評分。
- [**H008** — 確認](research/archive/confirmed/H008-estrange-options/summary.md)，
  而且結論裡自己記錄了：修正出場定價之後，PF 從 23.3 降到 1.70。
  **確認不等於蓋章放行。**

## 研究循環

六個 [Claude Code skills](.claude/skills/) 實作整個生命週期。每一步都寫進檔案系統，
所以任何假設的狀態都是一個可以讀、可以 diff、可以 review 的目錄，而不是對話歷史。

```
  /new-hypothesis   →  research/active/HXXX-名稱/
                       proposal.md  ← 交易直覺、可測試陳述、**無效條件**
                       tasks.md
                              │
  /explore          →  Phase 1：歷史資料分佈探索
                       distribution.md + GATE 判定
                              │
                       ┌──────┴──────┐
                    GATE 未過      GATE 通過
                       │              │
                       │       /backtest  →  Phase 2：walk-forward、參數敏感度、
                       │                     drawdown、連敗分析
                       │                     backtest.md + Verdict
                       │              │
  /archive          ←──┴──────────────┘
        │
        ├─ research/archive/confirmed/      (52)  ──/ship──→  strategies/live/  (4)
        ├─ research/archive/rejected/       (71)                     │
        └─ research/archive/inconclusive/    (4)                     ↓
                                                     indicators/tradingview/*.pine (14)
  /status  →  所有進行中假設的總覽
```

skills 強制執行（而非建議）的規則：

- 無效條件必須在 Phase 1 開始前就存在
- 未通過 GATE 不得執行回測
- 所有數字結論必須附上樣本數
- 參數優化後必須做 out-of-sample 驗證才能標記 Confirmed
- 探索與回測腳本必須與結論一起 commit——**跑不出來的結果不算結果**

## 不需要任何市場資料就能跑的部分

市場資料不在版控裡（約 27 GB，且所有權屬於交易所）。測試刻意設計成完全不依賴它：

```bash
asdf install        # Python 3.14.3t + uv，版本鎖在 .tool-versions
uv sync
uv run pytest       # 197 個測試，不需要任何市場資料
```

所有 fixture 由 [`tests/synthetic.py`](tests/synthetic.py) 合成。建議先讀這幾支：

| 檔案 | 釘住什麼 |
|---|---|
| [`tests/test_lookahead.py`](tests/test_lookahead.py) | **前瞻偏誤偵測。** 擾動決策時點**之後**的所有 bar，斷言該時點的特徵值不變。也檢查特徵**語意**——「10 日均線」是不是真的 10 日。 |
| [`tests/test_pipeline_invariants.py`](tests/test_pipeline_invariants.py) | 原本只靠註解維持的契約：指標必須在日期篩選**前**用完整歷史計算、暖身期必須是 `NaN` 不能是 `0`、OHLC 欄位不可位置錯位。 |
| [`tests/test_orb_long_rules.py`](tests/test_orb_long_rules.py) | 用真實引擎跑合成日 K，驗證進出場規則。經突變測試驗證——擾動 8 個策略參數，每一個突變都被抓到。 |
| [`tests/test_runner_pure.py`](tests/test_runner_pure.py) | 結算日推算、Wilder 平滑、結算日量校正。 |

兩個測試標記 `xfail(strict=True)`，斷言的是已知缺陷的**應有行為**；缺陷修好後會變成
`XPASS` 並讓 build 失敗，正好提醒回來拿掉標記。

回測引擎本身是 [backtesting.py](https://github.com/kernc/backtesting.py)（第三方套件）。
這裡測的是本專案自己負責的那一層：餵給它的特徵，以及建構在上面的策略規則。

## 已知缺陷

寫上面那些測試時，抓到兩個已經產出結果好幾個月的真 bug。兩個都屬於「永遠不會報錯，
只會讓數字安靜地變得不一樣」那種：

- **一個濾網讀到的值，取決於當天稍後才會發生的資料。** 該濾網預設停用，
  無 live 策略受影響。
- **一個以「天」命名的參數，實際涵蓋的區間跟名字不符**——而且依資料載入方式不同，
  同一個參數代表兩種東西。

兩個都還沒修，因為修了會改變訊號、讓既有回測失效。目前用 `xfail(strict=True)` 測試
釘住**應有行為**：誰修好了，測試就會開始通過，strict 模式讓 build 失敗，那正是
「回頭更新所有下游」的提醒。完整說明在
[`tests/test_lookahead.py`](tests/test_lookahead.py)。

另外三個，列出來是因為一個宣稱在做誠實研究的 repo 應該對自己也誠實：

- **Python 研究與 Pine Script 執行的等價性未經驗證。** Confirmed 策略會重寫成
  TradingView 指標——那才是實際執行的語言，而它跑不了這套回測，也沒有任何東西
  在檢查兩邊一致。這是本專案最大的未測試面。
- **兩個引擎行為會安靜地縮小結果**：任何回測的第一個交易日都不會產生交易；
  `end` 日期會整天排除該日。兩者現已由測試釘住。
- **測試覆蓋是針對性的，不是全面的**——特徵層與一支策略的規則。其餘策略、
  選擇權回測與探索腳本沒有覆蓋。

## 專案結構

```
src/etl/            期交所 / TWSE / TPEX / FinMind 資料匯入 → DuckDB
                    （下載 → 解析 → 1 分 K → Panama 連續合約 → 驗證）
src/backtest/       資料載入、特徵計算、EstRange、參數優化
src/strategies/     backtesting.py 用的策略類別
src/analysis/       早盤簡報、關鍵價格、VIX regime、廣度溫度計、fg-composite 監控
src/chart_ui/       FastAPI + lightweight-charts 行情瀏覽 app

research/           140 個假設 — active/ 與 archive/{confirmed,rejected,inconclusive}
strategies/live/    4 支由 confirmed 假設晉升的策略
indicators/         14 支 TradingView Pine Script 指標（實際執行面）
tests/              197 個測試，僅用合成 fixture
.claude/skills/     六個研究生命週期 skills
```

## 技術棧

Python 3.14（free-threaded）· uv · DuckDB · backtesting.py · pandas / numpy ·
FastAPI + lightweight-charts · matplotlib · Resend · launchd

資料來源：期交所（期貨與選擇權 tick 檔）、TWSE / TPEX（大盤廣度、個股日線）、
FinMind（指數與個股分 K）、國發會（景氣對策信號）。**本 repo 不轉散布任何資料**，
一律在執行時抓取。

---

# 操作手冊

## 前置需求

- macOS
- [asdf](https://asdf-vm.com/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（需有 Anthropic API 或 Pro/Max 訂閱）

## 安裝

```bash
git clone <your-repo-url>
cd futures_backtest

asdf plugin add python
asdf plugin add uv
asdf install  # 自動讀取 .tool-versions

uv sync
```

`.tool-versions` 鎖定版本：
```
python 3.14.3t
uv 0.10.7
```

## 資料格式

### 期貨（TX）

期交所每日 zip 檔，解壓後為 `.rpt`（CSV 格式）：

```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20251231,TX     ,202601     ,084530,23150,2,-,-,
```

- 每個 zip 對應一個日曆日（含非交易日，非交易日為 HTML 頁面，自動跳過）
- 價差合約（合約代號含 `/`）自動過濾

### 選擇權（TXO）

```
成交日期,商品代號,履約價格,到期月份(週別),買賣權別,成交時間,成交價格,成交數量(B or S),開盤集合競價
20260105,TXO    ,23000,202601     ,P,090703,3.1,1,
```

- 僅匯入 TXO（台指選擇權），過濾 Flex 合約（含 `F`）
- 合約代號：`202601` = 月選，`202601W1` = 週選

## 快速開始

### 1. 下載初始資料

> **注意**：期交所網站只保留最近 **30 個交易日**的資料。超過 30 天的歷史資料可從以下 Google Drive 取得：
>
> - [台指期貨（TX）](https://drive.google.com/drive/folders/1mLvxQdqEQUty9EOeUQ33BoQcqxToM-SE) — 下載後放入 `data/raw/<年份>/`
> - [台指選擇權（TXO）](https://drive.google.com/drive/folders/13IRRQqYpsQ8Au-X0XAjOaPrxgGlKHx0n) — 下載後放入 `data/raw_options/<年份>/`

```bash
# 自動下載（期交所通常於 18:30 前更新當日資料）
uv run python src/etl/download.py

# 或指定範圍
uv run python src/etl/download.py --start 2025-01-01 --end 2025-12-31
```

### 2. 建立資料庫

```bash
# 期貨資料
uv run python src/etl/parse_rpt.py        # zip/rpt → ticks
uv run python src/etl/build_1m.py         # ticks → 1分K
uv run python src/etl/build_continuous.py # Panama 換倉調整
uv run python src/etl/validate.py         # 驗證

# 選擇權資料（需先將 zip 放入 data/raw_options/）
uv run python src/etl/parse_options_rpt.py # zip/rpt → ticks_options
```

### 3. 用 Claude Code 開發策略

```bash
claude

# 範例對話：
# > 幫我寫一個策略：日盤開盤後30分鐘內突破高低點就進場，
# >   用15分鐘K的ATR當停損，收盤前5分鐘強制平倉。
# >   回測近2年的TX資料。
```

## 每日更新資料

`daily_update.py` 是一鍵 pipeline，除期貨 / 選擇權外，也會更新 TWSE/TPEX 廣度、TAIEX、台灣 VIX、融資餘額、景氣信號與 fg-composite 指標（輔助資料源失敗為 warn-only，不中斷）。各 step 對照表見 `CLAUDE.md`。

```bash
# 一鍵更新：自動下載最新 zip + 跑完整 ETL（Step 0–10）
uv run python src/etl/daily_update.py

# 只下載，不跑 ETL
uv run python src/etl/download.py

# 已有 zip，只跑 ETL
uv run python src/etl/daily_update.py --skip-download

# 跳過驗證加速
uv run python src/etl/daily_update.py --skip-validate
```

### 設定自動排程（macOS launchd）

`deploy/` 內含 launchd 排程模板與安裝腳本。金鑰與絕對路徑皆為佔位符，
由 `deploy.sh` 在安裝時以環境變數替換，替換後的複本只寫進
`~/Library/LaunchAgents`，不進版控：

```bash
RESEND_API_KEY=... FINMIND_API_KEY=... bash deploy/deploy.sh
```

## 常用查詢

```python
import duckdb

conn = duckdb.connect("data/futures.duckdb")

# 拉取 1 分 K（含 Panama 調整後的連續合約價格）
df_1m = conn.execute("""
    SELECT timestamp, open, high, low, close, adj_close, volume
    FROM ohlcv_1m
    WHERE symbol = 'TX' AND timestamp >= '2024-01-01'
    ORDER BY timestamp
""").df()

# 合成 15 分 K
df_15m = df_1m.resample('15min', on='timestamp').agg({
    'open': 'first', 'high': 'max',
    'low': 'min', 'close': 'last',
    'adj_close': 'last', 'volume': 'sum'
}).dropna()

# 查換倉紀錄
conn.execute("""
    SELECT * FROM rollover_log WHERE symbol = 'TX' ORDER BY rollover_date
""").df()
```

## 資料表說明

| 表 | 說明 |
|---|---|
| `ticks` | 期貨原始 tick，single source of truth |
| `ohlcv_1m` | 1分K，日盤 08:45~13:45，含 `adj_close` |
| `rollover_log` | 每月換倉記錄，Panama 價差 |
| `ticks_options` | 選擇權原始 tick（TXO），含履約價、買賣權別 |
| `aux_futures_1m` | 輔助期貨 1 分K（NYF=0050ETF期等），chart-ui 盤前延伸力用 |
| `market_breadth` / `stock_day` | TWSE/TPEX 大盤廣度 + 全市場個股日 OHLCV |
| `top_lists` / `concentration_index` | 月度成交前 20 + 集中度寬表（H080） |
| `taiex_day` / `vixtwn` | 加權指數日線 / 台灣 VIX |
| `margin_balance` / `econ_signal` | 融資餘額 / 景氣對策信號 |
| `stock_min` | 全市場個股分K（FinMind，DCI 盤中校準用，獨立兩步 ETL） |

> `taiex_day` / `vixtwn` / `margin_balance` / `econ_signal` 共同支撐 fg-composite（S004）市場情緒綜合指標。

- `adj_close`：Panama backward adjustment，最新合約價格不調整，歷史往前遞增調整
- `adjustment`：累計調整量（`adj_close = close + adjustment`）
- `is_rollover`：換倉日當天的 K 棒標記為 `TRUE`

## 選擇權策略回測

### EstRange Credit Spread

基於 EstRange（Volume-Weighted Estimated Range）的選擇權賣方策略：

- 09:30 計算 EstRange，定出 Est High / Est Low
- 價格碰到一邊後，賣對側 Credit Spread（月選 TXO）
- 跳過週三（雙邊觸及率高）、12:30 收工

```bash
# 回測 2026 年
uv run python src/backtest/backtest_estrange_options.py --start 2026-01-01 --end 2026-03-18

# 自訂參數
uv run python src/backtest/backtest_estrange_options.py \
  --fraction 0.70 --spread-pct 0.50 --exit-time 12:30
```

詳細規格見 `research/archive/confirmed/H008-estrange-options/spec.md`。

## Chart UI（行情瀏覽 app）

```bash
uv run chart-ui            # 啟動，預設 http://127.0.0.1:8888/
```

讀 `data/futures.duckdb` 的 `ohlcv_1m`，可瀏覽每日 1 分K。主圖支援關卡（risk levels）觸及標記與 swing levels 高亮；副圖含延伸力（extension）、NYF（0050期）盤前延伸與 VIX regime 盤前判讀。回測腳本可用 `from src.chart_ui.list_writer import write_chart_list_from_backtesting` 輸出自訂清單。

```bash
./run-chart-ui-tailscale.sh   # 綁 tailscale 對外（自動抓 tailscale ip -4）
```

## 疑難排解

### DuckDB 資料庫損壞或需要重建

```bash
rm data/futures.duckdb
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py
```

### rpt 檔編碼問題

`parse_rpt.py` 會自動嘗試 UTF-8 → Big5 → CP950。

### DuckDB 鎖定錯誤

```
IO Error: Could not set lock on file "futures.duckdb"
```

表示另一個 process 正在使用資料庫。關閉其他連線（如 Jupyter notebook）後重試。

## 授權與免責

MIT。本專案不構成投資建議，回測數字為模擬結果且未計交易成本與滑價。詳見 [LICENSE](LICENSE)。

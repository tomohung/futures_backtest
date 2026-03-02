# 台指期回測系統

台指期（TX）當沖策略回測系統，從期交所原始 tick 資料到策略回測的完整工具鏈。

## 前置需求

- macOS
- [asdf](https://asdf-vm.com/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（需有 Anthropic API 或 Pro/Max 訂閱）

## 安裝

```bash
# 1. Clone 專案
git clone <your-repo-url>
cd futures-backtest

# 2. 安裝 Python（透過 asdf）
asdf plugin add python
asdf install python latest
asdf local python latest

# 3. 安裝 uv
asdf plugin add uv
asdf install uv latest
asdf local uv latest

# 4. 安裝依賴
uv sync
```

## 專案結構

```
futures-backtest/
├── CLAUDE.md              ← Claude Code 的專案說明
├── README.md
├── pyproject.toml
├── .tool-versions         ← asdf 版本鎖定
├── data/
│   ├── raw/               ← 放原始 rpt 檔
│   └── futures.duckdb     ← 自動產生的資料庫
├── src/
│   ├── etl/               ← 資料處理管道
│   ├── strategies/         ← 策略邏輯
│   └── backtest/           ← 回測執行器
├── notebooks/              ← Jupyter 探索分析
└── tests/
```

`.tool-versions` 內容：
```
python 3.12.9
uv 0.6.6
```

## 快速開始

### 1. 準備資料

將期交所 `.rpt` 檔放入 `data/raw/`：

```bash
cp /path/to/your/rpt/files/*.rpt data/raw/
```

### 2. 建立資料庫

```bash
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py
```

### 3. 驗證資料

```bash
uv run python -c "
import duckdb
conn = duckdb.connect('data/futures.duckdb')
print(conn.execute('''
    SELECT
        min(timestamp) as from_date,
        max(timestamp) as to_date,
        count(*) as total_bars,
        count(distinct timestamp::date) as trading_days
    FROM ohlcv_1m
    WHERE symbol = \'TX\'
''').df())
"
```

### 4. 用 Claude Code 開發策略

```bash
claude

# 範例對話：
# > 幫我寫一個策略：日盤開盤後30分鐘內突破高低點就進場，
# >   用15分鐘K的ATR當停損，收盤前5分鐘強制平倉。
# >   回測近2年的TX資料。
```

### 5. 手動跑回測

```bash
uv run python src/backtest/runner.py --strategy my_strategy --from 2024-01-01
```

## 每日更新資料

```bash
cp new_data.rpt data/raw/

# 增量匯入（已存在的日期會跳過）
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py
```

## 常用查詢

```python
import duckdb

conn = duckdb.connect("data/futures.duckdb")

# 拉取 1 分 K
df_1m = conn.execute("""
    SELECT * FROM ohlcv_1m
    WHERE symbol = 'TX' AND timestamp >= '2024-01-01'
    ORDER BY timestamp
""").df()

# 合成 15 分 K
df_15m = df_1m.resample('15min', on='timestamp').agg({
    'open': 'first', 'high': 'max',
    'low': 'min', 'close': 'last',
    'volume': 'sum'
}).dropna()
```

## 疑難排解

### rpt 檔編碼問題
期交所檔案可能是 Big5 編碼，parse_rpt.py 會自動嘗試 UTF-8 → Big5 → CP950。

### TA-Lib 安裝失敗
改用純 Python 替代：
```bash
uv remove ta-lib-bin
uv add pandas-ta
```

### DuckDB 資料庫損壞
刪掉重建，原始 rpt 檔都還在：
```bash
rm data/futures.duckdb
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py
```

# 早盤簡報 Email 化設計

**日期**：2026-07-24
**目標**：把 `morning_briefing.py` 的產出（key_prices 文字報告 + 圖表、daily_range 圖、breadth 文字+圖、fg_composite 文字）轉成 HTML email，平日盤前自動寄到信箱。

## 背景

現況 `src/analysis/morning_briefing.py` 依序跑：
1. `daily_update.py`（ETL）
2. `key_prices.py` — 印 markdown 報告到 stdout + 複製到剪貼簿；另存 `output/sr_chart.png`、`output/30m_chart.png`
3. `daily_range.py` — 存 `output/daily_range.png`
4. `breadth_thermometer.py` — 印文字 alert + 存 `output/breadth_thermometer.png`
5. `fg_composite_monitor.py` — 印文字

問題：這些產出只在終端機/剪貼簿，無法遠端（手機）盤前查看。

參考 `../trading_spirit/scripts/email_alerts.py`：用 stdlib `urllib` 直打 Resend REST API，inline-styled 暗色 HTML，環境變數控制收發件人。

## 使用者決策（brainstorming 確認）

- **內容範圍**：文字報告全包（key_prices + breadth + fg_composite）+ 全部 4 張 PNG 圖表 inline
- **格式**：Markdown → HTML 渲染（非純文字 `<pre>`）
- **觸發**：launchd 自動排程
- **排程時間**：平日（週一～五）盤前 **06:00**
- **非交易日**：不加 guard，照寄（key_prices 用前一交易日資料）
- **morning_briefing.py**：維持現狀（手動、clipboard、跳圖），email 走獨立新腳本

## 架構

兩個新檔，職責分離：

### 1. `src/analysis/md_to_email_html.py` — 純函式 renderer

- 介面：`render(markdown: str) -> str`，回傳 inline-styled HTML 片段。**無 I/O、可獨立單元測試**。
- 只需處理這些腳本實際吐出的 markdown 構造：
  - `# ` → h1、`### ` → h3、`#### ` → h4
  - 表格：`| a | b |` 資料列 + `|---|---|` 分隔列
  - `**粗體**` → `<strong>`
  - `> ` → blockquote
  - `---`（獨立一行）→ `<hr>`
  - `- ` → 清單項
  - 空行 → 分段；其餘 → 段落
- 樣式沿用 `email_alerts.py` 暗色系：`#111` 底 / `#e8e8e8` 文字 / `#d4a574` 琥珀 accent / 等寬表格（`ui-monospace`）/ 表頭 `#d4a574` 底線。
- `↑`/`↓` 箭頭上色：↑ 紅 `#e06666`、↓ 綠 `#57bb8a`（台股漲紅跌綠）。
- HTML escape：`&`/`<`/`>`（沿用 reference 的 `_esc`），但 `**bold**`/箭頭上色在 escape 後套用。
- **為何自寫而非用 Python-Markdown 套件**：email 客戶端剝除 `<style>`/class，必須 inline 樣式；這些腳本 markdown 構造固定規律，自寫 ~120 行完全掌控樣式、零新依賴、貼合 house style（reference 亦刻意 stdlib-only）。

### 2. `src/analysis/email_briefing.py` — orchestrator + 寄信

流程：
1. 跑 `daily_update.py`（`--skip-update` 旗標可略過，供除錯/重寄）。
2. 逐一以 subprocess 跑 4 個分析腳本，**擷取 stdout** 當各段 markdown。
   - 過濾雜訊行：含「圖表已儲存」「已複製到剪貼簿」「已儲存」等的行不進 email。
   - **為何 subprocess 擷取而非 import**：4 個腳本零改動、輸出與終端機一致、PNG 路徑已穩定。
3. 收集 4 張圖（存在才收）：`output/sr_chart.png`、`output/30m_chart.png`、`output/daily_range.png`、`output/breadth_thermometer.png`。
4. 用 `md_to_email_html.render()` 把各段 markdown 轉 HTML，組成完整 HTML doc，每段文字後插入該段的 `<img src="cid:...">`。
5. 用 Resend urllib pattern 送出（複製 reference）：
   - 環境變數：`RESEND_API_KEY`（必填，缺則 warn + exit 0）、`ALERT_EMAIL_TO`（預設 `you@example.com`）、`ALERT_EMAIL_FROM`（預設 `onboarding@resend.dev`）。**複用同一把 Resend key**。
   - 圖以 `content_id` inline attachment 送：`attachments: [{filename, content: <base64>, content_id}]`，HTML 端 `<img src="cid:<content_id>">`。（已查證 Resend 支援：欄位 `content`/`filename`/`content_type`/`content_id`。）
   - Header 帶常規 `User-Agent`（Cloudflare 會擋預設 python-urllib）。
   - 錯誤處理：HTTPError / URLError 印警告回非 0，但不丟例外中斷。

Subject：`[台指早盤] YYYY-MM-DD 關鍵價格簡報`（日期取今天）。

### email 排版順序

1. 標題列 + 日期
2. 關鍵價格文字報告（key_prices stdout）
3. SR 圖（`sr_chart.png`）
4. 30 分 K 圖（`30m_chart.png`）
5. 日盤波動圖（`daily_range.png`）
6. breadth 溫度計文字 + 圖（`breadth_thermometer.png`）
7. fg-composite 文字
8. footer：自動寄出註記

## 資料流

```
launchd 平日 06:00 → run-daily-update.sh
  ├─ daily_update.py                     (ETL，唯一 DuckDB 寫入者)
  └─ (若早上) email_briefing.py --skip-update
       ├─ key_prices.py     → stdout markdown + sr_chart.png, 30m_chart.png
       ├─ daily_range.py    → daily_range.png
       ├─ breadth_...py     → stdout markdown + breadth_thermometer.png
       ├─ fg_composite...py → stdout markdown
       ├─ md_to_email_html.render(每段)  → HTML 片段
       └─ Resend POST (HTML + 4 CID 附件)
```

### 3. 排程整合（沿用現有 launchd，不新增 plist）

現況：`com.tomo.futures-daily` plist 已在**平日 06:00 與 17:00** 跑 `run-daily-update.sh`，
內含 `.daily_update.lock`（mkdir 原子鎖）防兩次 ETL 重疊。

**若另開一個 06:00 email plist 跑自己的 `daily_update.py`，會是第二個寫入者**
（該 Python 呼叫不走 shell 的 `.daily_update.lock`）→ DuckDB 單寫鎖衝突崩潰。

正確做法：**把 email 併入 `run-daily-update.sh` 的早上那次執行**：
- ETL（`daily_update.py`）跑完後，判斷 `$(date +%H) -lt 12`（只早上）→ 跑
  `uv run python src/analysis/email_briefing.py --skip-update`（ETL 剛完成，故 skip）。
- 以 `|| true` 包住，email 失敗不影響 ETL job 退出碼。
- 沿用既有 06:00 平日 launchd 排程與鎖，**不新增 plist**，順序決定性、零 race。
- `RESEND_API_KEY` 需在 launchd 環境可見：加進 `com.tomo.futures-daily.plist` 的
  `EnvironmentVariables`（比照現有 `FINMIND_API_KEY` 作法）。

`email_briefing.py` 本身仍支援獨立手動執行（不帶 `--skip-update` 時會自己先跑 ETL），
供 ad-hoc 重寄；pipeline 走 `--skip-update` 路徑。

## 元件邊界檢查

| 元件 | 做什麼 | 怎麼用 | 依賴 |
|---|---|---|---|
| `md_to_email_html.render` | markdown 段 → inline-styled HTML | `render(md) -> str` | 無（純函式） |
| `email_briefing.py` | 跑分析、收圖、組信、寄信 | `uv run python .../email_briefing.py [--skip-update]` | 4 個分析腳本、renderer、Resend API、env vars |
| `run-daily-update.sh`（改） | ETL 後早上叫 email | 現有 launchd 06:00 觸發 | `email_briefing.py` |

## 測試

- `md_to_email_html.render`：單元測試——餵各 markdown 構造（標題/表格/粗體/blockquote/hr/清單/↑↓），驗證輸出含預期標籤與樣式。
- `email_briefing.py`：以 `--skip-update` + 假的/缺 `RESEND_API_KEY` 跑一次，確認能擷取 4 段、組出 HTML、缺 key 時 warn+exit 0；設好 key 時實際寄一封驗證收件。

## 非目標（YAGNI）

- 不改 `morning_briefing.py`。
- 不加非交易日 guard。
- 不做 email 客戶端相容性矩陣測試（Gmail 為主）。
- 不把 renderer 通用化成完整 markdown 引擎，只覆蓋這些腳本用到的構造。

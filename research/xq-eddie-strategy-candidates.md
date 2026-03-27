# XQ 發財橘子文章 — 純價量策略候選清單

> 來源：https://www.xq.com.tw/xstrader/author/eddie/
> 建立日期：2026-03-27
> 篩選條件：只需 OHLCV（價+量）即可實作，不依賴基本面/籌碼面/個股資料
> 目標：應用於台指期（TX）日盤當沖或波段策略

---

## A. 趨勢跟隨類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| A1 | SuperTrend | [Super trend](https://www.xq.com.tw/xstrader/super-trend/) | ATR 通道 + 階梯修正，突破上軌做多、跌破下軌做空，同時當 trailing stop | HLC | 參數簡單（ATR期間+倍數），可對比 ORB |
| A2 | 多方維持線 | [多方維持線](https://www.xq.com.tw/xstrader/%e5%a4%9a%e7%b6%ad%e6%8c%81%e7%b7%9a/) | 動態追蹤前波低點形成支撐線，收盤連續3天在線上/下確認多空 | HLC | 類似 trailing stop 概念，可做多空切換 |
| A3 | KAMA 考夫曼自適應均線 | [KAMA](https://www.xq.com.tw/xstrader/%e8%80%83%e5%a4%ab%e6%9b%bc%e8%87%aa%e9%81%a9%e6%87%89%e5%9d%87%e7%b7%9a-kama/) | 根據效率比動態調整均線速度，趨勢明確時貼近價格、盤整時遠離 | Close | 自適應特性可減少盤整假訊號 |
| A4 | 漩渦指標 Vortex | [漩渦指標](https://www.xq.com.tw/xstrader/%e6%bc%a9%e6%b8%a6%e6%8c%87%e6%a8%99/) | 比較正向/負向趨勢運動（VI+ vs VI-），交叉判斷趨勢方向 | HLC | 類似 ADX 但更直觀 |
| A5 | Ehlers 相關性趨勢指標 | [Ehlers](https://www.xq.com.tw/xstrader/ehlers-%e7%9b%b8%e9%97%9c%e6%80%a7%e8%b6%a8%e5%8b%a2%e6%8c%87%e6%a8%99/) | 用統計相關性衡量價格與時間的線性關係，高相關=強趨勢 | Close | 數學基礎紮實，適合趨勢確認 |
| A6 | KST 確認指標 | [KST](https://www.xq.com.tw/xstrader/ — page 95) | 多週期 ROC 加權合成，捕捉不同時間框架的趨勢共振 | Close | 多重時間框架概念 |
| A7 | DKX 多空線 | [DKX](https://www.xq.com.tw/xstrader/ — page 95) | 多空判斷趨勢線 | OHLC | — |
| A8 | ALF 亞歷山大過濾指標 | [ALF](https://www.xq.com.tw/xstrader/ — page 95) | 過濾小幅波動，只在價格變動超過門檻時產生訊號 | Close | 濾除雜訊的趨勢追蹤 |

## B. 動能/震盪類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| B1 | WaveTrend Oscillator | [WaveTrend](https://www.xq.com.tw/xstrader/wavetrend-oscillator/) | 雙重 EMA 平滑的 CCI 變體，±60 區域金/死叉進出場 | HLC | 比 KD/RSI 更平滑，減少假訊號 |
| B2 | 加速指標 Acceleration | [加速指標](https://www.xq.com.tw/xstrader/%e5%8a%a0%e9%80%9f%e6%8c%87%e6%a8%99/) | 比較上漲速度 vs 下跌速度的 5 日均值差，由負轉正=多方加速 | Close | 極簡指標，可做動能確認 |
| B3 | QQE | [QQE](https://www.xq.com.tw/xstrader/qqe/) | RSI 的平滑版本，自適應包絡線判斷超買超賣 | Close | RSI 進化版 |
| B4 | 逆費雪轉換 RSI | [逆費雪轉換 RSI](https://www.xq.com.tw/xstrader/%e9%80%86%e8%b2%bb%e9%9b%aa%e8%bd%89%e6%8f%9b-rsi/) | 將 RSI 做逆費雪轉換使極值更明顯 | Close | 放大超買超賣訊號 |
| B5 | CMO 錢德動量擺盪指標 | [CMO](https://www.xq.com.tw/xstrader/ — page 55) | 上漲總和 vs 下跌總和的比率，類似 RSI 但不做平滑 | Close | 對動能變化更敏感 |
| B6 | IMI 日內動量指標 | [IMI](https://www.xq.com.tw/xstrader/ — page 55) | 結合 K 線實體方向與 RSI 概念，專為日內設計 | OC | **專為日內交易設計** |
| B7 | 終極震盪指標 Ultimate Oscillator | [終極震盪指標](https://www.xq.com.tw/xstrader/%e7%b5%82%e6%a5%b5%e9%9c%87%e7%9b%aa%e6%8c%87%e6%a8%99/) | 結合 7/14/28 三個週期，減少單一週期震盪器的假訊號 | HLC | 多重週期概念 |
| B8 | 恰奇震盪指標 Chaikin Oscillator | [恰奇震盪指標](https://www.xq.com.tw/xstrader/%e6%81%b0%e5%a5%87%e9%9c%87%e7%9b%aa%e6%8c%87%e6%a8%99/) | AD 線的 MACD，衡量資金加速流入/流出 | OHLCV | 量價結合的動能指標 |
| B9 | Coppock Indicator 估波指標 | [估波指標](https://www.xq.com.tw/xstrader/%e4%bc%b0%e6%b3%a2%e6%8c%87%e6%a8%99%e3%80%8d%ef%bc%88coppock-indicator%ef%bc%89/) | 長期 ROC 加權平滑，專門抓大底反轉 | Close | 偏長週期，需測試短週期適用性 |
| B10 | Cybernetic Oscillator | [Cybernetic](https://www.xq.com.tw/xstrader/cybernetic-oscillator/) | 控制論概念的震盪指標 | Close | — |
| B11 | CCI 超買反轉 | [CCI超買反轉](https://www.xq.com.tw/xstrader/ — page 60) | CCI 進入超買區後反轉直下的放空策略 | HLC | 超買後反轉做空 |

## C. 量價分析類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| C1 | VSA 無供應 (No Supply) | [VSA無供應](https://www.xq.com.tw/xstrader/25109-2/) | 上升趨勢回檔中「收跌+窄幅+極低量」→ 賣壓枯竭 → 下根收漲進場 | OHLCV | 經典威科夫概念，tick 資料更精準 |
| C2 | Weis Wave Volume | [韋斯波段成交量](https://www.xq.com.tw/xstrader/%e9%9f%8b%e6%96%af%e6%b3%a2%e6%ae%b5%e6%88%90%e4%ba%a4%e9%87%8f-weis-wave-volume/) | 按價格波段累積量，下跌波量萎縮+上漲波量放大=主力進場 | OHLCV | tick 級資料可精確建構 |
| C3 | VWMACD | [VWMACD](https://www.xq.com.tw/xstrader/%e6%88%90%e4%ba%a4%e9%87%8f%e5%8a%a0%e6%ac%8amacd%e6%8c%87%e6%a8%99-vwmacd/) | 用 VWMA 取代 EMA 的 MACD，放量突破更靈敏、縮量盤整減少假訊號 | CV | 直接改良現有 MACD |
| C4 | TSV 時段分割成交量 | [TSV](https://www.xq.com.tw/xstrader/tsv%e6%8c%87%e6%a8%99%e5%8f%8a%e5%85%b6%e6%87%89%e7%94%a8/) | 成交量依價格變動加權，零軸穿越+背離判斷資金轉向 | CV | 偵測「機構腳印」 |
| C5 | VFI 成交量流量指標 | [VFI](https://www.xq.com.tw/xstrader/%e6%88%90%e4%ba%a4%e9%87%8f%e6%b5%81%e9%87%8f%e6%8c%87%e6%a8%99-volume-flow-indicator-vfi-%e3%80%80/) | 三層過濾（量截斷+波動率門檻+長週期），VFI 穿越零軸或背離 | HLCV | 預設 130 天偏長，需測試短週期 |
| C6 | CMF 蔡金資金流量 | [CMF](https://www.xq.com.tw/xstrader/chaikin-money-flow-cmf%e8%94%a1%e9%87%91%e8%b3%87%e9%87%91%e6%b5%81%e9%87%8f%e6%8c%87%e6%a8%99/) | 收盤位置在 HL 區間的相對位置 × 量，判斷買賣壓力 | OHLCV | 經典量價指標 |
| C7 | MFI Money Flow Index | [MFI](https://www.xq.com.tw/xstrader/ — page 55) | 結合量的 RSI，量價版本的超買超賣 | HLCV | 「量能 RSI」 |
| C8 | BW MFI 市場便利指標 | [BW MFI](https://www.xq.com.tw/xstrader/ — page 55) | 價格變動幅度 / 成交量，衡量每單位量推動價格的效率 | HLV | Bill Williams 系列 |
| C9 | EMV Ease of Movement | [EMV](https://www.xq.com.tw/xstrader/ — page 55) | 價格移動的容易程度，高 EMV = 少量即可推動、多方強勢 | HLCV | 獨特的量價效率指標 |
| C10 | Force Index 力度指標 | [Force Index](https://www.xq.com.tw/xstrader/ — page 55) | 價格變動 × 成交量 = 力度，衡量每根K棒的多空力道 | CV | Alexander Elder 系列 |
| C11 | KO 克林格成交量擺動 | [KO](https://www.xq.com.tw/xstrader/ — page 95) | 長短期量能流向差異，穿越零軸判斷趨勢 | HLCV | — |
| C12 | WVAD 威廉變異離散量 | [WVAD](https://www.xq.com.tw/xstrader/ — page 95) | 收盤位置加權的成交量累積指標 | OHLCV | — |
| C13 | Anchored VWAP | [Anchored VWAP](https://www.xq.com.tw/xstrader/anchored-vwap/) | 從特定錨點算 VWAP 做支撐壓力 | HLCV | 適合以開盤/前高低為錨點 |
| C14 | 量比統計 | [量要放大幾倍](https://www.xq.com.tw/xstrader/%e9%87%8f%e8%a6%81%e6%94%be%e5%a4%a7%e5%b9%be%e5%80%8d%e8%82%a1%e5%83%b9%e6%9c%83%e6%bc%b2/) | 放量 5~8 倍時多方動能最強，超過 8 倍反轉 | V | 量能統計觀察，可當濾網 |
| C15 | 價量配合良好 | [價量配合良好](https://www.xq.com.tw/xstrader/ — page 60) | 價漲量增、價跌量縮的經典量價關係確認 | CV | 基本量價原則 |
| C16 | 價量都呈多頭排列 | [價量多頭排列](https://www.xq.com.tw/xstrader/ — page 60) | 價格與成交量均線同時多頭排列 | CV | — |

## D. 波動率/通道類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| D1 | STARC 平均波幅通道 | [STARC](https://www.xq.com.tw/xstrader/%e5%b9%b3%e5%9d%87%e6%b3%a2%e5%b9%85%e9%80%9a%e9%81%93starc/) | SMA + ATR 通道（非標準差），觸及上下限=超買超賣 | HLC | 比布林更貼近實際波動，可對比 EstRange |
| D2 | BBTrend | [BBTrend](https://www.xq.com.tw/xstrader/bbtrend/) | 布林通道衍生的趨勢指標 | Close | — |
| D3 | %B 指標 | [%B](https://www.xq.com.tw/xstrader/ — page 95) | 收盤價在布林通道中的相對位置（0~1） | Close | 布林通道的標準化版本 |
| D4 | 納達拉亞-沃森包絡線 | [NW Envelope](https://www.xq.com.tw/xstrader/%e7%b4%8d%e9%81%94%e6%8b%89%e4%ba%9e-%e6%b2%83%e6%a3%ae%e5%8c%85%e7%b5%a1%e7%b7%9a-nadaraya-watson-envelope/) | 非參數回歸估計的動態包絡線 | Close | 機器學習概念的技術指標 |
| D5 | Ultimate Smoother | [Ultimate Smoother](https://www.xq.com.tw/xstrader/ultimate-smoother-%e6%8c%87%e6%a8%99/) | Ehlers 設計的超平滑濾波器 | Close | 極低延遲的趨勢線 |

## E. 盤整/趨勢判斷濾網類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| E1 | CHOP 斬波指標 | [CHOP](https://www.xq.com.tw/xstrader/%e6%96%ac%e6%b3%a2%e6%8c%87%e6%a8%99choppiness-index-chop/) | > 61.8 盤整勿追、< 38.2 趨勢確立 | HLC | **濾網用**，疊加在現有策略上 |
| E2 | Choppy Market Index | [CMI](https://www.xq.com.tw/xstrader/choppy-market-index/) | 類似 CHOP 的盤整判斷，改良版公式 | HLC | 與 CHOP 互補驗證 |
| E3 | ADX + Choppy 去盤整組合 | [去盤整指標](https://www.xq.com.tw/xstrader/ — page 70) | ADX、CHOP、噪音指標三合一去盤整濾網 | HLC | 多重濾網組合 |
| E4 | Elder-Ray Index | [Elder-Ray](https://www.xq.com.tw/xstrader/elder-ray-index/) | Bull Power / Bear Power 衡量多空力道偏離均線程度 | HLC | Alexander Elder 經典 |
| E5 | SZO 情緒指數 | [SZO](https://www.xq.com.tw/xstrader/szo%e6%83%85%e7%b7%92%e6%8c%87%e6%95%b8/) | 市場情緒極端值判斷 | Close | — |
| E6 | RVI 指標 | [RVI](https://www.xq.com.tw/xstrader/ — page 50) | 相對波動率指標，衡量波動方向 | OHLC | — |
| E7 | 趨勢強度指標 | [趨勢強度](https://www.xq.com.tw/xstrader/%e8%b6%a8%e5%8b%a2%e5%bc%b7%e5%ba%a6%e6%8c%87%e6%a8%99/) | 衡量趨勢強度的複合指標 | HLC | — |

## F. K 線型態 / 價格行為類

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| F1 | 長紅後的長黑（短空反轉） | [長紅後長黑](https://www.xq.com.tw/xstrader/%e9%95%b7%e7%b4%85%e5%be%8c%e7%9a%84%e9%95%b7%e9%bb%91/) | 大漲 > 6% 後隔日大跌 > 6%，散戶套牢短期續跌 | OHLCV | 有完整回測數據 |
| F2 | 大跌後的多頭執帶 | [多頭執帶](https://www.xq.com.tw/xstrader/%e5%a4%a7%e8%b7%8c%e5%be%8c%e7%9a%84%e5%a4%9a%e9%a0%ad%e5%9f%b7%e5%b8%b6/) | 大跌後出現開在最低收在最高的長紅 K，空頭力竭 | OHLC | K 線型態經典 |
| F3 | 大跌後的多頭母子 | [多頭母子](https://www.xq.com.tw/xstrader/%e5%a4%a7%e8%b7%8c%e5%be%8c%e7%9a%84%e5%a4%9a%e9%a0%ad%e6%af%8d%e5%ad%90/) | 大跌後前黑 K 包住後紅 K，賣壓收斂 | OHLC | 回測七年勝率 77% |
| F4 | 暴量脫離區間盤整區 | [暴量突破](https://www.xq.com.tw/xstrader/%e6%9a%b4%e9%87%8f%e8%84%ab%e9%9b%a2%e5%8d%80%e9%96%93%e7%9b%a4%e6%95%b4%e5%8d%80/) | 30 日盤整（振幅 < 10%）+ 爆量突破區間高點 | OHLCV | 與平台突破互補 |
| F5 | 平台整理後突破 | [平台突破](https://www.xq.com.tw/xstrader/%e5%b9%b3%e5%8f%b0%e6%95%b4%e7%90%86%e5%be%8c%e7%aa%81%e7%a0%b4/) | 20 日振幅 ≤ 7% + 四高四低差 ≤ 3% + 放量突破 | OHLCV | 回測 1594 次勝率 60% |
| F6 | 黑棒吞噬紅棒 | [黑棒吞噬](https://www.xq.com.tw/xstrader/ — page 100) | 空頭吞噬型態 | OHLC | 經典反轉型態 |
| F7 | 下影線的應用原則 | [下影線](https://www.xq.com.tw/xstrader/ — page 100) | 長下影線代表下方支撐，應用原則 | OHLC | — |
| F8 | 報復性反彈 | [報復性反彈](https://www.xq.com.tw/xstrader/%e5%a0%b1%e5%be%a9%e6%80%a7%e5%8f%8d%e5%bd%88/) | 月線 RSI ≤ 25 極度超跌後出現日線轉強訊號 | OHLC | 偏波段，需測試日內適用性 |
| F9 | 大跌後抄底系列 | [抄底長紅](https://www.xq.com.tw/xstrader/ — page 30) | 大跌後長黑K隔日長紅K，反轉進場 | OHLCV | — |
| F10 | 狹長整理後的突破 | [狹長突破](https://www.xq.com.tw/xstrader/%e7%8b%b9%e9%95%b7%e6%95%b4%e7%90%86%e5%be%8c%e7%9a%84%e7%aa%81%e7%a0%b4/) | 窄幅盤整後突破 | OHLCV | 類似 F4/F5 |
| F11 | 多重 MACD 交叉 | [江湖傳說(1)](https://www.xq.com.tw/xstrader/%e6%b1%9f%e6%b9%96%e5%82%b3%e8%aa%aa%e8%a7%a3%e5%af%86%e7%b3%bb%e5%88%971/) | 多組 MACD 同時多頭排列進場 | Close | 多重動能共振 |

## G. 盤中 / 開盤策略類（最適合當沖）

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| G1 | 開盤五分鐘不回頭 | [開盤5分鐘](https://www.xq.com.tw/xstrader/%e9%96%8b%e7%9b%a4%e4%ba%94%e5%88%86%e9%90%98%e4%b8%8d%e5%9b%9e%e9%a0%ad/) | 前 5 根 1 分 K 每根都收漲且收最高 → 強力追價買盤 | 1m OHC | **直接適用日盤當沖** |
| G2 | 開高破平盤後又站回 | [開高站回](https://www.xq.com.tw/xstrader/%e9%96%8b%e9%ab%98%e7%a0%b4%e5%b9%b3%e7%9b%a4%e5%be%8c%e5%8f%88%e7%ab%99%e5%9b%9e/) | 開高 > 2% → 盤中跌破平盤 → 站回且連續 5 筆在盤上 → 洗盤結束 | 1m/tick | **行進間換手概念** |
| G3 | 開盤 N 分鐘連續收紅 | [連續收紅](https://www.xq.com.tw/xstrader/%e9%96%8b%e7%9b%a4n%e5%88%86%e9%90%98%e5%85%a7%e6%af%8f%e6%a0%b9bar%e9%83%bd%e6%94%b6%e7%b4%85/) | 開盤起連續 N 根分鐘 K 都收紅，追價動能極強 | 1m OC | 類似 G1 但條件更寬鬆 |
| G4 | 盤中即時多空指標 | [盤中多空](https://www.xq.com.tw/xstrader/%e5%a6%82%e4%bd%95%e6%89%93%e9%80%a0%e7%9b%a4%e4%b8%ad%e5%8d%b3%e6%99%82%e5%a4%9a%e7%a9%ba%e6%8c%87%e6%a8%99/) | 統計前 50 大權值股站上 10 分鐘均線的家數 | 個股 1m | ⚠️ 需個股資料，無法直接用 |
| G5 | 期指盤中領先指標 | [期指領先](https://www.xq.com.tw/xstrader/%e6%9c%9f%e6%8c%87%e7%9b%a4%e4%b8%ad%e9%a0%98%e5%85%88%e6%8c%87%e6%a8%99/) | 50 檔權值股逐分鐘上漲家數趨勢 | 個股 1m | ⚠️ 需個股資料，無法直接用 |

## H. 其他可參考概念

| # | 名稱 | 來源文章 | 核心邏輯 | 資料需求 | 備註 |
|---|------|---------|---------|---------|------|
| H1 | Points and Line Chart | [P&L Chart](https://www.xq.com.tw/xstrader/points-and-line-pl-chart/) | 非時間軸的圖表方式，類似 Renko/P&F | OHLC | 另類視角看價格結構 |
| H2 | 內行人指數 | [內行人指數](https://www.xq.com.tw/xstrader/%e5%85%a7%e8%a1%8c%e4%ba%ba%e6%8c%87%e6%95%b8/) | 用價量推斷聰明錢動向 | OHLCV | — |
| H3 | 外盤成交比例指標 | [外盤比例](https://www.xq.com.tw/xstrader/ — page 100) | 外盤量佔總量比例判斷主動買力 | tick 內外盤 | 需 tick 級買賣方向 |
| H4 | WVIXF | [WVIXF](https://www.xq.com.tw/xstrader/wvixf/) | 波動率相關指標 | — | 需確認是否只需價量 |
| H5 | 雲帶型指標 | [雲帶指標](https://www.xq.com.tw/xstrader/ — page 65) | 製作雲帶型支撐壓力區 | OHLC | — |
| H6 | 轉強天數指標 | [轉強天數](https://www.xq.com.tw/xstrader/ — page 65) | 計算從弱轉強的連續天數 | Close | — |

---

## 統計

- **總計：62 個候選**
- A 趨勢跟隨：8 個
- B 動能/震盪：11 個
- C 量價分析：16 個
- D 波動率/通道：5 個
- E 盤整/趨勢濾網：7 個
- F K 線型態：11 個
- G 盤中/開盤策略：5 個（其中 2 個需個股資料）
- H 其他：6 個

## 下一步

依以下維度排優先順序：
1. **直接可用性**：是否能直接套用在台指期 1m K 線上
2. **與現有策略互補性**：是否補足 EstHL/ORB 的弱點（盤整日、反轉日）
3. **獨立策略 vs 濾網**：獨立策略優先，濾網可疊加
4. **回測數據品質**：原文是否有回測佐證

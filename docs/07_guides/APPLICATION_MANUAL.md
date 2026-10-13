# baldr 完整操作手冊

本手冊提供日常使用順序及常見操作入口。安裝看[快速開始](QUICK_START.md)，既有 owner 搬機看[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)，排程核對看[全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

baldr 是市場資料、個股研究、推薦回放、回測和持倉檢視工具。畫面輸出是研究資訊，不是券商委託或投資保證；目前沒有自動券商交易。Advice、Paper、模型投影、單次回測與排程狀態都不能單獨當成真實交易或自然成熟證據。

## 1. 日常使用旅程

### 1.1 開始前

1. 以你已完成設定的 source GUI 或 portable GUI 開啟 baldr。首次使用先依[首次安裝 Prompt](FIRST_INSTALL_PROMPT.md)、[安裝指南](INSTALL_GUIDE.md)或[可攜版指南](PORTABLE_WINDOWS.md)完成自己的環境設定。
2. 在「數據更新」檢查資料根、行情資料日期、來源狀態、缺件與 warnings。`current`、`expected_wait`、`stale`、`partial`、`failed`、`unknown` 和有效空結果不能互換。
3. 選一項任務：更新資料、查看市場、建立研究候選、讀個股／持倉，或回看已保存結果。先確認本輪決策日、資料日、來源及 scope。
4. 完成後記下 result/run ID、狀態和 warnings。若保存或讀回失敗，保留原錯誤與身份，不手動修改 hash、日期或 artifact。

### 1.2 四種常見情境

| 我想做什麼 | 從哪裡開始 | 主要核對 | 詳細操作 |
|---|---|---|---|
| 更新與檢查行情 | 「數據更新」 | `DATA_ROOT`、來源日、quality、warnings、更新後涵蓋 | [資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md) |
| 查看市場、產業與個股 | 「市場探索」或「個股研究」 | 決策日、行情資料日、來源、coverage、缺件 | [資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md) |
| 研究推薦候選、保存結果或回測 | 「推薦分析」或「Research Lab」 | eligible universe、Profile／策略版本、成本、成交假設、run ID | [推薦與 Research Lab](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) |
| 管理候選清單或檢視持倉 | 「候選池」、「觀察清單」或「Portfolio」 | 選定來源／帳本、資料日期、身份、寫入範圍 | [觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md) |

### 1.3 入口及共通狀態

主要工作區包括 Decision Workbench、Market Explorer、Recommendation、Backtest、Watchlist、Stock Research、Portfolio、Data Update 和 Runtime。不同入口可能讀不同的資料根、來源版本或帳本；以畫面明示的日期、來源、帳戶及狀態為準，不按股票代號或最新檔名猜配。

- `missing` 表示來源或欄位缺失；`unknown` 表示目前無法確認；`degraded`／`partial` 表示結果有可用部分但不完整；`failed` 表示工作失敗；`skipped` 表示本輪條件未執行；0 筆可能是有效空結果，也可能是來源問題，須看 warnings 和查詢狀態。
- `fallback` 是降級結果，不能當作本輪正常產出。Regime、分數、候選排序及 Advice 不是勝率或交易指令。
- 取消工作會停止新工作並等待安全收尾；等待期間畫面可能仍顯示上一個完整結果。確認狀態和本輪 ID 後再決定是否重試。
- UI 刷新只會依該頁契約讀取資料；它不會自動修復行情、重跑策略或啟用排程。

## 2. 數據更新與市場探索

更新前先確認 `DATA_ROOT` 和 `OUTPUT_ROOT` 各自指向預期位置，再檢查來源日期、quality 和 warnings。快速更新適用近期日常補檔，並增量同步 SQLite；安全更新會依選定範圍重建每日合併檔後同步 SQLite。快速更新不等於全量 CSV 重建。

更新完成後再次查狀態，確認同一根目錄、日期涵蓋及 SQLite 狀態。若是部分完成或失敗，保存錯誤、範圍和已完成階段再判斷重試。不要把缺資料填成零、改時間或手動刪除資料庫／WAL／SHM。市場總覽先讀決策日、行情資料日、來源和 warnings，再判斷 Regime、強弱、產業或主力流向。

詳細步驟、參數、狀態解讀與資料修復安全界線見[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md)。

## 3. 推薦、回測、候選與持倉

建立推薦前核對資料日、母體、Profile、門檻及已啟用指標；結果先看 result ID、決策日、資料日、quality、warnings、Why／Why Not 和 screening matrix。保存後只沿同一 result ID 讀回。Research Lab 需確認日期、股票母體、策略版本、成本、滑價、成交假設與 benchmark；最佳化結果是候選，仍需 OOS 或 Walk-forward 等證據。

候選池、Universe、手動交易帳、聲明持倉與 Paper 帳用途不同。保存候選清單或匯入帳本前，核對目前選定資料、預覽、hash 和寫入範圍。所有帳本都不會自動連券商或送委託。詳見[推薦與 Research Lab](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)及[觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md)。

在 Paper 區回看已保存健康評估時，先明確選取 receipt／snapshot，再開啟並核對來源與持倉身份；返回或正常關閉後可沿保存偏好重開同一評估。步驟、分開的時鐘、WATCH／未知與讀取失敗處理見[已保存健康評估與回訪](manuals/WATCHLIST_AND_PORTFOLIO.md#已保存健康評估與回訪)。

## 4. 數據更新

舊連結入口保留；目前更新流程與狀態判讀集中在[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md#檢查與更新資料)。

### 4.2 快速更新與安全更新

<a id="42-快速更新與安全更新"></a>

快速更新適用近期日常補檔；安全更新重建所選範圍的合併檔。兩者的前置條件、資料日核對與取消處理見[更新步驟](manuals/DATA_AND_MARKET_RESEARCH.md#檢查與更新資料)。

### 4.6 市場資料完整性修復（受控 CLI）

<a id="46-市場資料完整性修復受控-cli"></a>

資料修復／availability mapping 有 preview、備份與明確 apply gate，僅由具授權的 owner 依[每日資料更新指南](../03_data/daily_data_update_guide.md)執行。一般使用者不要手動補檔、改 receipt、覆寫 SQLite 或把月營收／財報候選當成已發布資料。

## 6.7 官方市場與技術條件研究

<a id="67-官方市場與技術條件研究"></a>

舊錨點保留；目前入口、來源核驗和條件設定見[官方市場與技術條件研究](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#67-官方市場與技術條件研究)。來源 coverage 不完整、`current_only` 或 available time unknown 時，結果只供當下研究，不能提升為歷史 PIT 證據。

## 8. 每日決策（Daily Decision Desk）

<a id="8-每日決策-daily-decision-desk"></a>

Daily Decision Desk 是已保存來源的唯讀摘要入口。先確認資料日、來源、quality、warnings 和持倉 scope，再讀待判讀項目。空佇列不代表風險為零或 Gate 通過；重新整理不會重跑資料更新或策略。操作見[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md#市場探索)及[觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md#持倉管理)。

## 12. 常見問題

<a id="12-常見問題"></a>

| 狀況 | 先確認 |
|---|---|
| 沒有資料或日期過舊 | 畫面使用的 `DATA_ROOT`、SQLite 路徑、來源日、coverage 和 status；不要沿用別人的 root。 |
| 顯示 0 筆 | 區分有效空結果、來源缺失、查詢失敗和被條件篩除；看狀態列及 warnings。 |
| 更新部分成功或失敗 | 保存日期範圍、錯誤、已完成階段；確認來源、資料庫鎖與磁碟空間，再依失敗階段處理。 |
| 推薦或回測看起來很強 | 核對母體、決策日、資料日、成本、成交假設、驗證期間及 run ID；單次高報酬不是自然或實盤證據。 |
| 保存／讀回不一致 | 保留 result/run ID 和錯誤；不要手工改 hash、複製 artifact 或按最新檔名代替原來源。 |
| Task Ready 或 exit 0 | 這只表示局部排程狀態，不代表產物與 consumer readback 已通過；按[排程唯讀稽核](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)核對同一 run。 |

<details>
<summary>舊手冊書籤與日期化工程補充（按需展開）</summary>

## 舊手冊錨點與日期化工程補充

下列舊章節連結保留，全文已封存；日常操作以本手冊及主題分冊為準。

### 頁面的 i 說明按鈕

<a id="頁面的-i-說明按鈕"></a>

原手冊記錄過在頁面標題旁開啟該頁操作說明的入口，內容涵蓋操作順序、欄位／單位、結果判讀與缺件處理。這是舊版手冊描述，不保證每個現行工作區都有相同按鈕；請以目前畫面及對應操作章節為準。[原始章節](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md#頁面的-i-說明按鈕)

### 2026-10-03 週度研究採集與讀回

<a id="2026-10-03-週度研究採集與讀回"></a>

此日期的 parent／child 收據讀回與各 child 狀態是歷史紀錄；`verified` 不代表來源資格，`formal_credit=false`，也不建立公告可得時間或 historical PIT。完整原文與數值見[原始章節](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md#2026-10-03-週度研究採集與讀回)；目前排程操作依[唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)，目前狀態依 Snapshot 與具名 QA。

### 2026-07-13 系統工程整合判讀

<a id="2026-07-13-系統工程整合判讀"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-04 保存來源當下研究與持倉日期

<a id="2026-10-04-保存來源當下研究與持倉日期"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX04／05 每日研究條件與同源個股

<a id="2026-10-05-ux0405-每日研究條件與同源個股"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX13／18 具名研究母體盤勢與指標排序

<a id="2026-10-05-ux1318-具名研究母體盤勢與指標排序"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX16 唯讀研究來源契約

<a id="2026-10-05-ux16-唯讀研究來源契約"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX18 共用日特徵與個股觀察

<a id="2026-10-05-ux18-共用日特徵與個股觀察"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX19 隔離研究快照生產與讀回

<a id="2026-10-05-ux19-隔離研究快照生產與讀回"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-06 UX21 保存母體 H5／H10／H20 研究結果

<a id="2026-10-06-ux21-保存母體-h5h10h20-研究結果"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 施工版完整保存母體瀏覽

<a id="2026-10-07-施工版完整保存母體瀏覽"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 真人回饋摘要收藏與推薦失敗

<a id="2026-10-07-真人回饋摘要收藏與推薦失敗"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 dev 修正 H20 摘要獨立於一般個股報告

<a id="2026-10-07-dev-修正h20-摘要獨立於一般個股報告"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991E 已保存推薦的個人決定與旅程回看（2026-09-28）

<a id="991e-已保存推薦的個人決定與旅程回看2026-09-28"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991F 個人模型評估摘要讀回唯讀

<a id="991f-個人模型評估摘要讀回唯讀"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991H H20 Gross 每日收據與 BBANDS 上軌保存版別（2026-10-06）

<a id="991h-h20-gross-每日收據與-bbands-上軌保存版別2026-10-06"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

</details>

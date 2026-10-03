# 三階段後續資料鏈路收尾與本機提交

本輪承接11:12 UTC有限工程結案與使用者15:15 UTC的繼續修復／commit授權。原結案的成果與失敗收據保留；本輪以實際程式、資料及逐項驗證更新狀態，不把歷史PIT、自然效果或Windows安全權限混為工程完成。

## 差距與驗收計畫

| 分類 | 差距／對四項用途的影響 | 驗收 |
| --- | --- | --- |
| 已完成 | weekly controller、父子hash binding、canonical acquisition分流、CORE19 fit/cold reload及Legacy/Bank已接受 | 重驗現有收據及程式依賴，不重訓／重複producer |
| 需修工程 | 月營收候選1855列缺正式mapping，又無桌面可操作的現況正規化入口，影響個股現況研究 | raw→Decimal TWD→current-observed完整核對；正式回填維持fail-closed |
| 需修工程 | 六個法人歷史日期的衝突／缺碼只有觀測保存，現況consumer未接修訂view | 舊版本與FAILED不變；新觀測按真實時間供current-restated，歷史日期不能提前看 |
| 待核對 | 季報數值unit／basis／issuer coverage契約與current consumer | 逐來源接受可證明的部分；未知金額unit不猜、公告時間不回填 |
| 需補驗證 | 小視窗及取消／重試未對最終程式取得完整接受 | 最終程式版本新驗，不混用c625前的UI證據 |
| 自然等待 | 未到期來源發布、H5成熟、樣本效果 | 不作工程收尾門檻，不授模型promotion |
| 外部／決策 | Windows Operational logging ACL、無法驗證的歷史公告與正式來源接受 | 不改安全權限；列明真正缺件及安全現況用途 |

## 回滾清單

| 檔案 | 變更類型／摘要 | 回滾方式 | 風險 |
| --- | --- | --- | --- |
| `data_module/current_monthly_revenue_materialization.py`及測試 | 新增受raw綁定的現況正規化／append-only套用 | 保存新增檔，按依賴撤回入口；不刪資料 | 現況更新入口中斷 |
| `app_module/update_service.py`、`ui_qt/views/update_view.py` | 現況研究快照入口 | 用本輪before bytes定向還原，不能用HEAD覆蓋原三階段dirty成果 | 同步撤回UI與service |
| `data_module/institutional_revision_read_model.py`及consumer／測試 | 具觀測時間的修訂view | 還原本輪before bytes，保留舊版與觀測 | current研究恢復舊view |
| Snapshot／Manual／Architecture／QA索引 | 同步真正結果與限制 | 本輪before檔定向還原 | 文件與程式須同步 |

既有189個dirty/untracked檔、完整diff及before bytes已保存於ignored `output/qa/closeout_commit_20261003/`。資料apply前另外做一致SQLite備份與保護表比較。回滾前先確認沒有新writer；不reset、clean或刪原始檔，不以HEAD還原已存在的他人修補。commit前另依owner manifests、dependency與diff逐檔分類；不提交runtime／資料庫／raw／憑證。

## Look-ahead自查

現況數值使用真實驗證／觀測clock，不製造舊公告時間。current-only路徑與正式PIT provider分開，不能作歷史replay／formal training／校準；法人revision僅在其observed_at之後可讀，原歷史available_date不改。金額Decimal或整數量值，展示邊界不反向影響核心推薦計算。


## 2026-10-03 後續資料鏈路與個股研究驗證

本輪保留原三階段成果、失敗收據與原始資料。控制實跑不是自然排程成功；Windows Task 的 LastTaskResult 與資料源實際更新分列。

| 問題／根因 | 修改與實際結果 | 邊界／剩餘 |
| --- | --- | --- |
| 月營收 raw 候選缺 current consumer 正規化入口 | 新增 raw SHA／CSV 全列綁定、Decimal 千元→TWD、備份後 append-only 寫入；1855 列兩市場完成，桌面更新頁增加「更新現況研究資料」 | 不修改原公告日／正式 PIT 表；2026-08 公司完整性未證明 |
| 季報現況 unit／basis 未完整承接 | 六份官方 HTML raw→79903 數值→DB 獨立全列核對；1975 公司，EPS／股數／百分比與金額分單位；weekly controller 完成後接 current writer，cmd／PS1 一致、互斥 writer、600 秒逾時 | 2026-Q2；現金流期間基礎未明示，不作累計彙整；舊 OpenAPI 未證單位數值不供判讀，原始列保留；正式 PIT 仍 2024Q1 |
| 法人歷史修訂未接現況 consumer | 六個日期新增849個 current revision，逐筆 payload/hash/觀測時間驗證，舊列與 checkpoint 不改；個股現況可讀，歷史查詢不能提前讀 | 原失敗／衝突證據保留，不補造歷史資格 |
| 排程 decision_date 與 market cutoff 混用、跨美西／臺北日封存拒絕 | 封存與 consumer 明定臺北決策日、資料截止日；真實控制 producer 保存 rec_65027485839f4da7b662df4c49300e2b，決策10/4、資料10/2，200股15合格185排除 | 不改舊 immutable artifact；週末 no-work 合法 |
| Evidence stdout PIPE 空白而 exit0 | create-only child stdout 檔回讀 SHA／bytes、summary 與 report；缺 summary exit2。舊10/3快照控制重跑報告確實產生，pipeline errors0 | 最新完整來源仍有 watchlist／portfolio／risk quality 缺件，不宣稱全面正常 |
| Rule policy 週末 skipped 被 consumer 判格式失敗 | 驗證 schema、calendar、日期、時戳與所有安全邊界後回 not_published_non_trading_day；20項 provider 測試、真實來源唯讀回讀通過 | 沒有 policy 值、不授正式資格；下次交易日發布須自然核對 |
| 1477 未綁保存來源、整塊 Advice／Rule 內容不可恢復 | 明確同股非未來來源選擇器、指定股票分析入口、獨立 RSI／MACD／ADX／MA20／60 技術觀察及精確篩選排除理由；不可自動套最新或他股來源 | Advice／ML 資格仍依封存來源；正式 calibration 真實根因為2014-01-02起來源修訂隔離，不能用 research 模型替代 |
| 排程驗收提示未包含新契約 | 兩個現有 operational automation 只追加有限唯讀驗收提示，TOML逐欄比對與 SHA回讀 | ACTIVE／RRULE／名稱／目標thread／其他欄位完全不變；沒有重建WP5或提醒 |

### 最新資料源讀取（17:20 UTC）

唯讀 freshness：daily prices 截止20261002；法人 current、信用交易 current，兩市場版本群組齊全，信用2216個最新日期列（TWSE MI_MARGN + TPEx mainboard-margin-openapi.v1）；TDCC20261002、4078列 current。原TPEx HTTP520保留，最新成功不回寫原失敗。TDCC以完成交易週及內部兩後續交易日寬限判讀，不是官方發布deadline。月營收2026-08、季報2026-Q2的現況列已存在，但公司分母／原發布時間不明，維持partial；正式歷史表與current契約分開。

### 測試與原生 UI

新增及相關修正126 passed、1 skipped；Update Workbench強制檢查、validator及mypy在最終版另行回讀。獨立原生 Windows Qt MainWindow使用本輪隔離資料／output副本，不操作使用者既有視窗；1477有5個技術觀察與2個篩選理由、2個可選保存來源，指定1477研究route實際通過。Win32實際視窗寬800、高676（Qt784×637）；取消2330後重試2317由真實service完成。1265個程式檔before/after SHA驗證；截圖只取本輪視窗。QA receipts、raw、SQLite與測試輸出留在ignored output，不提交。

正式推薦概率缺件、歷史PIT公告接受、H5自然成熟、下一次正常來源發布仍須分列；不放寬保護、不交易、不push/merge/deploy、不變更Logging ACL。本輪沒有停用Windows任務，原先raw任務Enabled=true已回讀；不能把未知平台時區欄位補造為已驗證DST設定。


### 最終回讀與提交邊界

週末修正後完整控制Evidence再次實跑：child exit0、22587 stdout bytes、SHA b88dbb3f5ef693ec0924b4f5d30c9d3a10396dc2d152fa2f1c952224e1696911、summary及report皆存在、errors0；wrapper仍exit2／failed，因watchlist_trigger／portfolio_alert／risk_prompt來源品質未ready，持倉轉換為degraded、blockers空。日期fallback涉及週末最新10/2行情與9/30未變持倉，並非新發布日缺資料；人類論點、1418入場身分與正式ML來源隔離仍未授予。此輪receipt不覆蓋原自然05:15 failure，不宣稱自然排程已成功。

最終強制工作台85 passed、validator25 passed／0 failed／4 skipped、mypy754 source files無issue；本輪126 passed／1 skipped，單位契約追加測試所在檔4 passed。承接受影響大套件原repo長路徑run為37 failed／1151 passed／5 skipped；修正QA路徑至短OS TEMP後1187 passed／5 skipped，剩1個小型ML fixture被真實容量保留量拒絕。該fixture單獨沿用既有synthetic_ml_capacity（只提供合成filesystem usage，仍執行preflight，退出後恢復原probe），端到端檔3 passed；另外容量保護25 passed／1 skipped。沒有降低正式容量門檻。初始失敗log保留，不將跨run計數冒充一次全綠總數。所有changed Python語法compile通過；Windows CRLF按cr-at-eol diff檢查，不改動排程時區、安全設定或原始資料。

本輪native資料庫副本已無損gzip封存，3848364032原bytes、1565883435archive bytes，完整解壓SHA為6dbc12a50c3ab84d5021e68c2e5458e3ec129137d8d76b77fafe9f795a8875b2；僅釋放可重建的本輪副本，原始source與apply備份不動。還原方式及身份receipt保存在native_final；本機C容量201GiB、D257GiB為此刻觀測，不作未來producer容量承諾。

逐檔提交清單與before bytes保存在ignored QA。授權範圍內三階段相關code／測試／文件以ML研究、排程資料接線、四用途UI與文檔三組本機提交；不推送。root `paper_event_source_capture.py`是來源未證的重複副本，保留untracked不提交；raw、DB、runtime、automation TOML及工具輸出不stage。automation只改prompt、其他欄位逐一相同。原native task LastTaskResult2仍是原實際自然結果，下一次發布／排程需自然回讀，不能以本輪控制實跑改寫歷史成功。

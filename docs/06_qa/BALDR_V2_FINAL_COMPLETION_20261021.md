# V2 工程補完與整合驗收

本輪依 [Blueprint](../superpowers/specs/BALDR_V2_PRODUCT_UX_BLUEPRINT_CONSOLIDATED_20261020.md) 與 Owner 10/21補完授權，從 `12e7f620`、`codex/baldr-v2-product` 增量完成。本文的 QA001起屬新任務 `output/tasks/baldr-v2-final-completion`；舊QA159／162／164／171屬 `baldr-v2-product-implementation`，兩個命名空間不可混用。角色及原件審查由root負責，三個實際Luna High工作包分別處理月營收、Paper及UI／Main測試；不是更換角色名稱充作獨立複核。

Source及正常Main正向驗證已完成，正在固定唯一Source與集中RC；RC收據完成前不宣告整體交付完成。Native保持`USER_STOPPED_ESCAPE`及`NATIVE_SMOKE_NOT_EXECUTED`，Owner保持`OWNER_UAT_NOT_PERFORMED`。累計額外Credits授權12,500未重置；任務級支出為`USAGE_UNOBSERVABLE`。沒有push、正式資料寫入、實盤、排程變更或替換正式入口。

## 已完成工程與驗證

| 範圍 | 實際結果與界線 |
|---|---|
| 首頁來源日期 | HEAD原`12e7f620`修復保留：排程決策10/21、行情10/20分列，台北實際10/22時仍stale，不用時鐘注入解鎖。 |
| 真Main來源／保存／返回／重開 | 新QA019通過`passed_historical_scoped_main_journal_e2e`。真`main()`、真WorkbenchSourceService及canonical query，原result `rec_e64969b24b2b4784aa02bcb89f2980e4`／1595，真正Journal保存與fresh程序strict read-back、原來源返回、worker／pool排空、四份正式原件SHA保持。只對source reader的shallow-copied config指定正式唯讀output；Main全域output與Journal均CASE隔離，因此不是預設production composition或今日正向候選全旅程。availability未由DTO獨立暴露，保存結果context仍為原10/20、行情日未知，不補日期。 |
| 月營收工程 | 新QA030：177 PASS／1 SKIP；精確雙市場profile、原publisher→file reader→cohort pin→外部SHA binding roundtrip、provider真raw重解析、單位原件proof、Decimal低precision及MOPS不能借JSON profile等守衛通過。 |
| 官方來源有界取得 | 新QA023各一次8秒／2MiB／零重試GET，TWSE HTTP200／607,634 bytes／1,088列，TPEx HTTP200／496,597 bytes／893列，皆2026-09、完整EOF及parser通過。原件與候選保存在`revenue/capture_20261021T235255_729111Z`。單位狀態`unverified_no_twd_conversion`，用途未接受、無正式ingestion、PIT=false。 |
| Paper契約與UI | 新QA035的定向命令100 PASS（整輪因後續probe錯誤FAIL仍保留）；含QA028的96項及研究保存時間、cash seed與未來ledger rows拒絕。真Journal／Timeline、原策略帳戶manifest、唯一seed receipt、外部cash／market／calendar各用途、純預覽、原ledger原子保存／回滾、exact reopen／retry與異動拒絕。UI驗實際首次確認時鐘、跨台北日、重試固定時間、輸入變更、晚到與原entry返回。全部為明示隔離fixture，沒有替Owner建正式帳戶或接受金融來源。 |
| 正常Main正向Paper | 新QA038 `passed_isolated_main_paper_journey`：真`main()`以設定建立原帳戶服務、reader及factory，不在啟動後替換；真Timeline明選→來源重核→1,000股買進純預覽→實際確認→原ledger保存→新repository exact reopen→原entry返回→既有Paper route。fixture事件／現金／行情及Journal時鐘明示取自然當日，seed為此前一日，測試接受原件不授正式用途。來源／Journal pins保持、SQLite sidecars無殘留、Main exit0／worker0／pool0。root已看預覽實圖，費用與模擬後現金可讀。 |
| 必要UI／型別／量化 | 新QA025 Workbench85 PASS，更新頁25 PASS／0 FAIL／4 SKIP；新QA028 mypy1113檔通過。新QA029所有changed Python compile及原量化防線通過；其helper import失敗保留，新QA030修正工具後新增五金融模組靜態防線0違規、packaging合成契約及前置頁11測試通過。靜態檢查不替代數值／來源測試。 |

## 五條旅程分軌判讀

此表重用舊證據時明列版本與切片。五條完整金融旅程仍為PARTIAL，不能把某一欄PASS外推其他欄。

| 旅程 | Code／Contract | Automated Main GUI E2E | Financial Source Qualification | Native Windows | Owner UAT |
|---|---|---|---|---|---|
| 今日總覽→線索→個股→保存→返回 | 日期／canonical身份／保存重開通過 | 新QA019歷史明選結果全鏈通過；今日正向仍PARTIAL_SOURCE_STALE，source-root組裝限制如上 | 原真來源degraded／stale；Paper未升格 | NOT_EXECUTED | NOT_PERFORMED |
| 市場／題材→成分→個股→返回 | 原typed版本、選列及不同來源日守衛保持 | 重用舊QA096／103／162具名樣本及fresh；本輪未改成員流程 | 限原題材／行情樣本，非全市場或PIT | NOT_EXECUTED | NOT_PERFORMED |
| 選股→條件→比較→個股 | 原價格流程保持；具名雙市場月營收reader／binding工程通過 | 重用舊QA159原query／page／row返回；新月營收跨來源Main正向未用正式接受資料驗 | 新OpenData單位與用途接受未成立，Main安全停用 | NOT_EXECUTED | NOT_PERFORMED |
| 個股→Paper→Forward→覆盤 | 新人工確認producer／原ledger／CAS／回滾／retry及因果時間通過；不是只驗前置拒絕 | 新QA038正常Main正向保存／exact reopen／原件返回通過，限明示隔離fixture；Forward原覆盤分支沿既有收據，整旅程PARTIAL | Owner未選正式資金帳戶／同日mark／cash／日曆用途；Forward仍按自然成熟，未造NAV | NOT_EXECUTED | NOT_PERFORMED |
| 策略→回測→保存→Registry比較→返回 | 沿既有保存與比較契約 | 重用舊QA162／164的相容120日／240列、不相容拒絕與返回功能切片；QA164原整輪FAIL不改寫 | 原固定研究範圍，非Alpha／ML promotion資格 | NOT_EXECUTED | NOT_PERFORMED |

## 原始失敗與隔離

舊QA164整輪FAIL保留：urllib3匯入時本機IPv6能力探測被guard攔下。新首頁probe只允許本機`::1:0` bind能力探測，外部connect／解析及CASE外寫入仍拒絕；未改產品網路行為。新QA004鏡像絕對來源根不符、QA011–015工具與未明選修訂的失敗均保留，QA019才完成限定歷史鏈。

新QA003／005／008的producer fixture、QA006／007的Windows測試路徑、QA016／017未定義helper／舊單位assert、QA018 seed identity、QA020原manifest格式與預覽依賴、QA024 market ref與seed日期、QA026型別、QA027超政策fixture及測試API、QA029工具import失敗全部保留原stdout／stderr／receipt。後續通過只接受對應修正後scope。所有已終結owned Job的remaining PIDs為0、限制讀回8GiB／12程序、kill-on-close且`forced_cleanup=false`；不以強殺排空冒作成功。

QA031全文手冊機械檢查遇到HEAD已存在的兩個舊junction trial guide越界引用，原FAIL保留；新增契約／驗收與新章節連結另做精確核對，不宣稱全手冊或全庫通過。QA032 fixture clock簽名、QA033負測對提早拒絕原因的舊assert、QA034新環境清除key未列runner白名單、QA035截圖變數、QA036／037把暫定確認前lineage拿來比落盤原件等工具FAIL保留；QA038以實際最終確認意圖重算完整事件，另核預覽金融值不變，再精確重開。沒有為全綠修改producer或降政策門檻。

## 外部接受與使用限制

OpenData沒有改標MOPS；官方單位原件必須能證明該endpoint／欄位的千元mapping，再由有權接受者固定外部SHA與逐用途接受。下載成功、政府資料開放授權或一般申報簡報都不能單獨補此證明。已準備實際候選、provenance及`approval_request.pending.json`，不是要求Owner自行編JSON或SHA。current-only不另要求完整歷史PIT；用途成立後仍需取得新的完整成功批次，不能倒填舊availability。

Paper正向工程已實作。正式使用仍需Owner明選／批准原帳戶、資金與策略政策，以及可核同日行情、現金與日曆用途；目前只支援原500,000 TWD／八檔契約、整手股數與一帳戶一日operation。非此契約的本金或帳戶形式仍是具名產品限制，不能用隱藏default或放寬policy補足。持久化只寫原ledger，不宣稱已完成獨立NAV投影、Forward成熟或ML資格。完整契約見[增量決策](../01_architecture/BALDR_V2_SOURCE_PAPER_INTEGRATION_20261021.md)，操作見[手冊](../07_guides/APPLICATION_MANUAL.md#保存研究的人工確認-paper-模擬)。

## 版本與候選

舊`eefd2163ad95`後的來源差異包括`b8ed339f`鍵盤／價格返回、`12e7f620`首頁日期修復與本次月營收／Paper工程。舊包及啟動器SHA不改，Source的通過不冒作舊EXE通過。集中新RC只在固定Source後建立一次；source archive、依賴鎖、EXE、同版測試與Launcher各有具名收據，Native未執行、未簽章及發布授權另記。新候選收據尚待完成，正式入口不替換。

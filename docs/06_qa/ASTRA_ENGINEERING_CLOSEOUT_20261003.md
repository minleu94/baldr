# 四用途工程缺口盤點與收尾（2026-10-03）

> 最新有限續接與尚未通過情境見 [2026-10-05 Batch9 清單](MINIMAL_CONTINUATION_HANDOFF_20261005.md)。本文件下列批次保留其原時點與證據，不因新批次工程測試通過而將原 native failure、容量或正式資格阻礙改成成功；本輪未 stage 或 commit。

> **歷史授權界線：** 下方使用者授權、分支與命令只屬於 2026-10-03 至 10-05 的歷史任務，不構成現在重跑、修改或提交的許可；目前狀態與工作入口請回到現行 Snapshot 及具名 QA。

本次承接 `dev`／`13f7a410c2ad850d981ed552ef09515220718ade`。使用者授權現有功能、資料取得、分析、UI、排程、ML 接線與自動累積路徑修復、測試及本機 commit；不授權交易、push、merge、部署、WP5 恢復、憑證或安全 ACL 變更。**目前仍在最終驗收，不能據本文件宣稱全部完成。**

## 最後驗收進度（10/5 01:45 UTC）

目前僅收斂四項，不新增功能或重新訓練：G11 目前研究的法人／信用／集保來源讀取及既有自然更新接線（實作中）；修後同版回歸與原生六情境（待測）；原容量門檻讀回（處理中）；文件與逐檔本機提交（待驗收後）。G1–G10 的 v15 通過證據如下，不能外推為 G11 完成。

集保新官方 HTTP 200 原件已於 01:38 UTC 保存於 `root/g11_current_ownership_capture_20261005/tdcc/run_20261005/`，報告日期 10/2，2,375,465 bytes、raw SHA=`9370ff9c282b951f0edc9288d9cd0787daaa6ee2a125d470c9dcd8b75031e5aa`，4,078 stocks／4,072 shadow-ready／6 quarantine。原 CLI 的 `captured_at_utc` 是 request-start，不能冒稱完成或發布時間；新 reader 必須核驗原件並保留當下觀測／非 PIT 資格。

原生 v19 已展開詳細摘要並驗到 2382 的 10/2 行情 332，但 QA 在 Qt 延遲釋放之後仍持有舊 ML table，因 `QTableView already deleted` 失敗。v20 僅修正事件迴圈後重新取得有效 widget；尚未執行，須連同 G11 在新 sibling 驗證。v19 原始失敗及 25 張實際截圖保留，獨立讀回 SHA=`da5319ec89bce4cf27efcc8cd5055567956c2b23492d93c087aadcf52bcdaf29`，不算六段通過。

最新自然 weekly 已完成，21 tasks 於 01:12 UTC 全部 enabled／Ready 且設定相符。Weekly run=`weekly_2bed8428f52747b8a56a0cabd2ef9a64` 外層 RC0，其後 current-fundamentals 於 01:11:07 UTC 實際 applied 83,606 values／1,976 stocks；這是新批次，不能覆蓋先前受控 79,903／1,975 的記錄。正式 PIT 仍 false，weekly core 保留 pending_human_review。Root 獨立重算 24 件不可變收據／原件雜湊全相符，讀回 SHA=`d90dafefbb60f021ace2489c4ccbd16edf134f75a2dec1bfe1fb7be0c4c765c1`。新 postcutoff PIT 因缺 10/5 verified denominator 回 RC2；其 Paper source-capture 是 waiting_for_frozen_recommendation，與下列成功的 Paper 六持倉快照為不同 lane。

容量處理只對有原封存身份的已結束隔離副本做可逆 NTFS 壓縮：本輪 v3 三檔節省 2,431,811,932 bytes，另七檔節省 12,186,161,152 bytes，完整內容 SHA／長度／mtime 均不變。兩份舊 `run_20260928_02/03` 快照在全批預檢發現 SHA 不符，原失敗保存並排除，沒有改原 pin 或壓縮它們。七檔 root 讀回 SHA=`3da50300805203469e03f4d1e0aa6281651b04946fb503a6f982bb699cf51f58`。卷可用空間另受其他寫入影響，尚未據節省總量宣稱容量 guard 已通過；亦不重播過期自然 ML 以補成功。

01:56 UTC 容量收尾：另五份本輪封存 native 副本已壓縮並逐檔驗完整 SHA／mtime／長度不變，節省 2,721,965,076 bytes，root 讀回 SHA=`e8a6fd5fddad14b83a22d301ea77feb65cb575d30beb23ea24c25c86702348b7`；十五份合計節省 17,339,938,160 bytes。隨後直接呼叫未修改的 `preflight_capacity`：C 自然 ML output free=211,794,477,056、required=215,285,235,712（差 3,490,758,656 bytes，blocked）；D 來源卷通過同 200.5 GiB 預算，但正式 raw output free=281,570,017,280、required=295,279,001,600（差 13,708,984,320 bytes，blocked）。收據 `capacity_probe/post_compression_existing_guards_20261005.json` SHA=`562a94581e5661a3ebfea69a3e194d42c30ce5ad414f05139c8b523524991a2f`。此為唯讀原 guard 檢查，沒有重訓、自然重播或門檻調低；不再擴大清理未知資料。

### 01:08 UTC 已完成驗證與當時觀察

G1–G10 主體修補及額外原生發現的頁首日期、未知得分與舊提示重疊修正已通過 v15；其後發現 G11 候選信用／集保資料未進 current report，正在補齊當下觀測 reader。因此 v15 不能替代 G11 修後驗收。`astra-final-v15` 於 00:55–01:03 UTC 完成七項檢查：114 個測試模組 **1,818 passed／10 skipped／1 warning**，Workbench 85 passed、validator 25 passed／0 failed／4 skipped、完整 mypy 765 檔、補充 35 檔、213 paths 編譯與量化 guard 全部通過。Result SHA=`3a1cf894078f758349183b4ecf7ec3d8ee0fbe79b49cf79885c38886f7c64bf4`；程式 1,294 檔、測試 1,155 檔與 storage config 在七項執行期間保持一致。十個回歸 skip 是 Windows symlink 權限限制；validator 四個 skip 是三項大量真下載及一項合併，並未宣稱驗過。

原生 v17 保留全形冒號的 QA 誤判。Root 從真實失敗截圖另外確認舊 widget 僅 `deleteLater()` 會暫時覆疊新內容，production 現在先隱藏再延遲釋放；新增同 call stack 回歸及原生 v18 截圖均證明修正。v18 又在預設折疊的摘要詳細區要求 label 可見而失敗，屬驗收操作缺步；正在以新的 sibling 展開／定位，原日期、股票、來源及 request identity 斷言不變。v18 原 result SHA=`0d28929e1f67528c8bcfbef43fe30ef44ca933973326a12b004d6303c1112863`，尚不稱原生六段通過。

Freshness producer／更新狀態 consumer 已統一 LA 04:30 發布週期，新收據明示 timezone；legacy 只相容精確既有 task。個股報告另用單一 aware clock、官方交易日、actual／expected／quote period 及合法來源時間核驗，沒有放寬月季或歷史資格。00:35 UTC canonical D 的唯讀狀態讀回 SHA=`99dcc0657dbfae2258ddf983c6bef2b93d84a6ae42ba46ef5a7ec365d2bb86c4`；00:03 UTC 2382 公開報告讀到 10/2、332 元及 fresh，未改原收據。明示來源時間的獨立 reader／Health 負例 SHA=`67082eb9e35e9c4fc13e8813e137fb6e8fde1d2673151387fd7e175fdc3d644b`。

G9 最後 50 檔於 10/4 23:33–23:41 UTC 實跑完成，inner result SHA=`434ce4708229e19446fa0c15ec42f56c800b034b382e120d5139d7bb5342fcef`，獨立讀回 SHA=`fa3cee9a66f4090a8b7a9491b35a00da94c15dec874d85612de6e99021770321`。53 producer pins 相符；1,991 檔中 50 eligible、1,805 degraded、130 excluded、6 missing；特徵分批 16／16／16／2。決策 10/5、行情 10/2、台北 07:40，entry 全為盤前 pending，沒有本批 capture／outcome／fit。歷史 learning 仍 `DailyPriceSourceRevisionError`，現況特徵支線已執行。50 列缺 industry-relative，5013 另缺兩個 60 日欄位，具體影響見下表，不能稱為完整 CORE20 或正式訓練。

10/5 新自然 Paper 已新增六個持倉的盤前市值快照 `paper-main-20261005`，quote date 10/2、ledger transitions 0；terminal SHA=`38f3aa390f578d10214aa5885213aef306a47d20ea0acb30726b696f628d4360`。同時 ML allocation-forward run=`20261005T002504618655Z-11d053ce3700` 被原容量 guard 阻擋（child RC1／外層 RC2、training false），terminal SHA=`7ffcf81e2accf8c0ccd1c72525290e4d4a307aeaf9c621bd90bd29d600cc8666`。C 輸出卷需 215,285,235,712 bytes；01:00 前讀回約 198.31 GB，這是操作容量阻礙，不能歸為歷史資格或只待時間。正在核對可逆壓縮的已結束驗收副本；未降低門檻、不補稱自然成功。

00:34 UTC 清冊的 21 tasks 均 enabled／Ready、設定相符；01:00 到期的 weekly 已自然啟動，正在等待 controller 後續 current-fundamentals 與最外層終端，不能沿用先前「尚未到期」。PIT preopen 先前自然 DNS 失敗與 00:07 受控重試失敗各自保留，statuses SHA 分別為 `deac5e2fbff79df563f969a7d361acb66508ceab1fa36154f3ce089b89bbc961`／`8ca416a36909b057a94a3b2ddfc8c0cd6de0c3bde64865d2421a208b088ad9f5`。單次官方 CSV HTTP 200 不代表全流程恢復。最後 native、容量、自然讀回與明列提交仍進行中，目前沒有本次 commit。

## 歷史：10/4 22:52 UTC 驗收檢查點

G1–G10 的主體修補已完成程式審查；原生 v15 又揭露持倉入口頁首誤用最後交易日，以及盤勢未提供得分時顯示 0 的呈現缺口，正在窄修。最後同版回歸與原生六情境仍待完成，尚未提交。盤勢現在保留請求／判斷生效日，另由截日以內最後有效指數收盤價傳出 `source_data_date`，在市場總覽直接分列判斷日與行情日；不改盤勢分類或歷史轉換。臺北日期邊界、保存來源的實際行情日、無來源恢復及正式／現況來源隔離均保持各自契約。

**G9 最後 50 檔已接受其實際執行範圍。** 22:04:33–22:12:58 UTC 的 run=`20261004T220438614823Z-2a58a758dff8`、result=`rec_fde799bc986843e6b4f74527fa84547e`，評估 1,991 檔、選入 50 檔；四批特徵為 16／16／16／2。4130 以已核驗官方下市證據排除，另外六檔短歷史的具體官方原因見下表。決策日 10/5、行情日 10/2；台北 06:11 尚未收盤，50 個 entry 全部 pending，沒有 input capture、outcomes 或本批 fit。wrapper／learning process RC0 與內部 `failed_dependency` 分開記錄，formal candidate 不存在。獨立摘要 `root/g9_final50_readonly_audit_20261005.json` SHA=`13beab9fa944634947f542f76fa72e6a3cc6a7a326df1d6c4a36f268ae5b6c91`，exact result SHA=`00a44fe9d0c37dc45dd501ff0391743206e689cc778cd5beb1f5fa516f1cb999`。Root 再驗 53 code pins、原 result／wrapper／artifact SHA 皆相符；該批設定 `regime=null`，未執行盤勢，因此後續 Desk 日期 metadata 不影響該批計算。此依賴界線見 `g9_final50_regime_scope_addendum_20261005.json`，SHA=`c919159028028ee821ee4bae9ce7878fd5097100aac954b2844ba87dd204e941`。

**v12 當版七項工程檢查已通過，後續入口修補尚須新版本驗收。** `astra-final-v12` 於 22:39:32–22:46:59 UTC 完成；112 個測試模組為 **1,698 passed／9 skipped／1 warning**，Workbench 85 passed，validator 25 passed／0 failed／4 skipped，完整 mypy 765 files、補充 mypy 33 files、209 個 Python paths 編譯及精度／未來函數 guard 全部成功。九個回歸 skip 是 Windows 無 symlink 建立權限；validator 四個 skip 是三項大量真下載與一項會修改資料的合併測試，均未宣稱驗過。唯一 warning 為全 NaN 測試資料觸發既有 pandas pct_change 的未來版本提示。全部 188 個候選 Python 檔及 91 個變更測試模組都包含於本批，另含整合回歸。v11 原 1 failed／1,674 passed／9 skipped 保留：只修盤前／盤後 fixture 的時間期待，production 與官方到期門檻未放寬。

原生 v15 於 22:47:42–22:48:36 UTC 真正完成正／負來源畫面、盤勢與持倉表；盤勢實值已分列行情 10/2、判斷 10/5。其後 QA 在持倉 tab lazy-render 未穩定前讀表失敗，失敗截圖清楚呈現既有 10/5 持倉讀取日與 10/2 行情日，不能據該斷言稱表格缺欄位。不過 Root 另從同張原生圖確認頁首仍把 7/31 最後交易日當資料日，並從盤勢 DTO 核實 `regime_score=None` 被顯示成 0；兩者列為實際工程缺口。持倉報告與 Portfolio 行情 freshness 不同亦正核對共用來源／QA fixture，尚未歸為自然不足。v15 原失敗及截圖保留，沒有重標為六情境接受。

原生 v14 已真正載入盤勢，以及 1477 的正向與嚴格 PE 未入選保存來源。正向來源為 `rec_255518cd7c044bb6818f20a389f678fb`、負向為 `rec_259228e2d6f34264ad8fa30b284a9e8c`；原失敗收據 SHA=`1b0c166f1d95365fe69306651c6c14edf44d990a54b3b54f77da1a7c3088d0c2`。失敗分別揭露截圖 ROI 在版面重繪前固定，以及 QA 將無來源手動持倉一律期待為「待更新」。2382 真實隔離帳本為 1,000 股、均價 281、行情 332（10/2）、毛未實現損益 51,000，數值已比對；沒有策略來源時 production 正確顯示「來源不足」／WATCH。v15 僅收緊 native geometry／pixel／identity 屏障並按實際 source 欄位區分 QA 預期，保留全部數值與非健康斷言，不改持倉保護。

盤勢原生等待另已定位 QA 的 `QTest.qWait` 造成 Python worker 延遲；改用讓出執行緒的等待後，相同 90 秒上限內取得真 snapshot，診斷 16.766 秒。診斷 `success=false` 及原不完整取樣收據保留，不冒充原生六情境接受。21:38 UTC 的 21 tasks 全部 enabled／Ready、設定相符，原三筆非零 LastResult 不變；兩個 operational prompts V6 磁碟讀回已接受，cache reload 仍 unknown。

以下日期檢查點保留當時狀態；後續接受不回寫舊批次，完整有限缺口表與外部限制表另列於後。

## 10/4 21:36 UTC 原生回歸檢查點（尚未最終接受）

行情日期的 producer／consumer 已凍結並通過獨立審查：新 `market_data_provenance` v1 保存 actual quote date，決策時鐘鏡射 typed Context（formal 可以 null），不新增 `Context.data_snapshot_refs` 或 available_at／PIT 資格。v12 正向結果 `rec_4971df0262df4bf895fa41964577b5db` 在原生保存／重開後顯示決策 10/5、行情 10/2，正負來源選項亦各自保留 exact 日期。來源恢復 7 項、Watchlist 42 項、下市接線四 suites 69 項及分類 24 項聚焦檢查通過，但不替代最後同版整合。

v12 六階段批次在 source-recovery 的盤勢摘要再次超過 90 秒，原失敗收據 SHA=`b7a9974df74b53a7fa9736b903433ab9fcc691e8d67b44a81f6cd5edfd71507a`、batch result SHA=`10a8797c18591654dc53ec3a7b3404b87ae640cc624cd63e080b7ec6900f57f0`。Advice／Rule／History 截圖仍因捲動／重繪屏障不足而重複，不宣稱三個 viewport 都驗證過。Root 21:36 啟動原時限的 30 秒全執行緒診斷；v13 僅補可見區定位與證據，不能延時或改斷言通關。另已定位 Desk、Smart Money、Update 的 host/Taipei 預設日差異，正在窄修並保留明示歷史日期。

官方 current-only gate 最終版本於 21:24 從 canonical D 原件唯讀驗證：4130／5371 為 verified_delisted，1477／3064／6236 非已核驗下市。收據 `root/current_market_status_final_frozen_readback_20261004T212413968158Z.json` SHA=`8fe384977ac745dd7a49d406b9fd63124bf65edf3307e62b9be828eb72a61739`；後續 50 檔整合尚待新實跑。

## 10/4 20:15 UTC Forward 檢查點（歷史）

Forward 的單次 aware 時鐘已接到核心、排程、CLI、Evidence pipeline 及歷史回放；73 項相關測試通過（此輪僅工具輸出，沒有另存 stdout）。Root 審查後於 20:14:40–20:15:06 UTC 執行新的 v3 受控程序，先以唯讀 WAL transaction 固定讀取窗口，**14 項 dry-run 檢查全通過**，再取得 canonical writer lease 更新 172 outcomes、新增 0 筆。43 events 與原自然收據不變。正式 writer 已實際執行，不能再引用 v2 的「尚未 writer」作為目前狀態；v2 原失敗仍保留。

結果為 **52 ready／118 pending／2 missing**；兩筆 missing 為 1538 的 H5 9/17 與 H10 9/24，官方到期日沒有延後，實際收盤價與報酬皆為 null。受控 child 正確回 `external_source_missing`／RC2，不能稱來源已完整或自然排程成功。全部結果使用臺北 10/5 04:14:56 的同一 invocation、盤前 `price_read_cutoff_date=2026-10-04`；該欄是查詢上界，並不表示已有週日行情。精確 report SHA=`47433ebedf8bf40ffc26b907aece608eefaabf332edd7240b08b8e7ce506eb66`，confirmed receipt SHA=`e6aa74fe69b9143ba517d5cd8d0bb76ff620e58250765c3d77cf9f5709fe2ad5`，目錄 `root/forward_outcomes_execute_20261004T201441269566Z/`。完整逐列原值保存於同目錄 `before_cohort.json`；這次 helper 沒有另建完整 DB 備份。

另一位 Luna Max 以新的唯讀 SQLite transaction 重建全部 43／172 列，**24 項獨立檢查全通過**，收據 `root/forward_v3_independent_readback_20261004.json` SHA=`2ebfd97288b3c4aca2a70783ec37d5a3c68ac4403c4487eef6ed5cf08a0422db`。兩筆缺價以外的 170 列只變計算時鐘／日曆診斷；舊 `maturity_status` 保留 legacy row-offset 語義，權威仍是 `outcome_status`、`official_maturity_date` 與 `target_price_state`。WAL 確實因授權寫入改變，不宣稱整庫位元組不變。原自然 12:40 run／status SHA 仍為 `03cdb7b6f9eb8a8aae433164412c248a2af7d19444afd2067d0d0cb53bab3bcd`。

寫入後同一個 G6 terminal 的十股公開讀回於 20:15:45–20:15:49 UTC 再次通過，stdout SHA 仍是 `ecd1c8330202fdb77b8699770c793b3744a583dc90f6731ecd8c09f5988ecfb1`。盤勢窄幅優化的完整 breadth 結果逐欄相同，snapshot 由 28.953 秒降至 16.375 秒，等價收據 SHA=`33b56fe6780b11b3dc1222dc2c8de259999dfca261e7b008245a2dfa6a5ae990`；原生 QA 另補 Qt timer 重入保護，不改 90 秒上限。共用即時推薦的 4130 下市狀態接線、其新實跑、最後原生六情境及完整回歸仍待完成，尚未 commit。

七檔短歷史已完成官方來源查核。近六十個全市場行情日為 7/8–10/2，各股傳入筆數與不可變 G6 DB 逐股相等，沒有 consumer 截掉有效列；初始完整 coverage 收據 `root/snapshot_screening_coverage_readonly_20261004.json` SHA=`05e00f4b7c76241b70775cfb7dc72367058ab15de0528a740541c86205aec9fc`。其中 4130 的現況下市判斷仍是工程待修，不能與另外六檔一起歸為自然不足。

| 股票 | 窗內有效列／官方證據 | 對既有功能的實際影響 |
|---|---|---|
| 7825、2938、7812、7856 | 15／11／7／7 列；官方首次掛牌日依序 9/10、9/16、9/22、9/22，與首筆日價相符 | 二十列技術門檻尚未滿足，保留現況研究內容，待真實有效行情累積，不補歷史 bars |
| 3064、6236 | 11／16 列；全部缺列日期聯集與 controls 共 57 日已核對 TPEx 日期相符的原件。缺少的 49／44 列官方均為股數、筆數、金額 0 且 close=`----`；另 21 筆既有資料數值吻合 | 正式 normalizer 對無可用收盤價的零成交列不產生 bars，未發現官方有效價漏列；不把變更交易方法誤稱停牌，也不補零價格以湊二十列 |
| 4130 | 9 列、最後價 7/21；官方終止上櫃生效日 7/28，G7 於 10/4 實際取得此現況證據 | 10/5 即時選股應以已核驗下市理由排除；正在接共用 service 與可見篩選理由，不把新觀測反向授為 10/2 PIT |

TPEx 完整 Decimal／整數比對收據為 `output/tmp/tpex_daily_missing_audit_continue_20261004T202548Z_5a7cb3df/comparison_decimal_verified.json`，SHA=`5422d2fdfe1f806ab36d94efd230bd6db21c51729c02778f5f1e0d9407d2add7`。它引用兩次取證 run 的 57 個獨立日期原件，不冒充單批原子擷取；首輪 8/3 HTTP 520 只留失敗 metadata、沒有 body，後續成功 body 是另一原件。初版 13 筆字串小數格式差異保留，後版逐件重算原 SHA 並以 Decimal 驗證相等。這只能佐證目前官方回傳的歷史數值，不能建立當時的公告／可取得時間。

## 10/4 19:50 UTC 整合檢查點（歷史）

G9 正常分支修正已實跑三組：原預設 `200/50` 實際 15 檔（19:12–19:13 UTC），明示 QA `400/17` 的 17 檔（19:15–19:17），以及 `2000/50` 的 50 檔（19:23–19:32）。全部 exact snapshot／cohort／stdout／G6／逐列 source contract 驗證通過；17 與 50 檔分別走完整 v2 批次，provider 每批仍至多 16 檔，預設策略與候選範圍未改。50 檔 result=`rec_eff9c6e061824735874ca09329d3f2f9`，stdout SHA=`766bd8368b905daaeffb0e7c3cc7fc4902bd118dbdb57901991ccda7778db070`。三組唯讀摘要 `root/g9_normalbranch_actual_readonly_summary_v2_20261004.json` SHA=`2e86b08312ffb9f6d5cc09a85bf645b762eef3ad3e264c6ebb24bf5b91840c9f`。觀察時為臺北 10/5 03:xx，前日特徵已取得，同日 entry 尚未發布而 pending；不讀未收盤列、不形成自然成熟樣本。learning CLI RC0 與內部正式 `failed_dependency` 同時存在，Formal／PIT／promotion 仍 false。

50 檔執行的 1,991 筆 screening 已逐股核對：1,583 筆未達量比門檻、224 筆無策略訊號，雖沿既有分類為 degraded，均有具名規則／觀測值／門檻且 `missing_data=[]`；127 筆是 top-N 排除、50 筆入選。另 7 筆未達二十列歷史門檻，正在核對官方上市／交易狀態與實際來源範圍，不能直接稱自然新上市。

15 檔特徵的缺值另查原件：產業相對報酬需要已核驗股票成分映射，現有 index CSV 只含指數序列、未發現已配置的治理映射；CORE19 明確排除此欄。1459 的兩項六十日特徵缺值對應 7/23–7/31 無日價，TWSE 官方月報與本機 CSV 一致，8/3 恢復報價另有 TWTAUU 官方減資結果；沒有管線漏抓證據，不補價或授歷史交易資格。唯讀收據 `root/current_feature_missingness_readonly_20261004.json` SHA=`8ebf5755eb087d9ea35a2e0dd025a09873da72a03705697196d103d117c46d14`。

Forward 19:33 受控嘗試在 dry-run 後停止，尚未啟動正式 writer：DB bytes／43 events／172 outcomes 前後相同，但空 WAL 生命期造成 metadata guard 不同。正在以持有唯讀 transaction 的新 QA sibling 固定讀取窗口，保留原嚴格 DB／WAL guard。兩筆實際缺價是 1538 的 H5 9/17 與 H10 9/24，官方列皆 close=NULL；較早 23:03 dry-run 也已是兩筆，不能誤說跨日新增。另核實 date-only 核心對「未來某次到期日恰為今天」有盤前誤判可能，正補 aware invocation／收盤邊界；本次 43×4 horizon 沒有 10/5 到期，因此不是本次兩筆缺價原因。

原生 v9 真實完成 1477 正向保存來源與嚴格 PE 未入選來源讀回，但盤勢 Decision Desk 在 90 秒內仍未完成背景載入，尚未接受。另發現 QA 同名截圖覆寫及 Rule 內容截圖停在 History 捲動底部；v10 將保留唯一原件並分別拍攝 Advice／Rule／History，原失敗與碰撞紀錄保留。`astra-final-v10` 的前四項工程檢查通過，但工具連線在 regression 中斷，沒有完成收據，不能宣稱整套通過。最後完整回歸、native 六情境、Forward 修後受控寫入與 commit 仍待完成。

## 10/4 18:50 UTC 整合檢查點（歷史）

`astra-final-v9` 於 18:18:21–18:26:15 UTC 完成七項檢查：100 個測試模組共 **1,495 passed／9 skipped**、Workbench 85 passed、更新頁 validator 25 passed／0 failed／4 skipped、全範圍 mypy 764 files、補充 mypy 33 files、190 檔 Python 編譯及量化 guard 通過。七批 source／tests／storage inventories 前後與跨批一致。回歸使用 `-q` 未留下九個 skip 的具體原因，因此不推定其原因；validator 的四個略過則為三項大量真下載與一項會修改資料的合併測試。唯讀摘要 `root/astra-final-v9-readonly-review.json` SHA=`67d049d5ee796e8f5fe2034c6d8a8d283013b1c30099d7508acd2704d879b32c`；編譯數量以實際 argv 190 檔為準，修正紀錄 SHA=`bc86f5126adcbe831fbb7b1893563212c56887ac91ecbc43cf8c31780e6ca72c`。此後 G9 又有窄修，不能用 v9 代表最終版。

18:23 的 G9 預設策略真實產生 15 檔，但同一個 G6 DB digest 的裸字串／`sha256:` 表示差異被 consumer 誤拒；原 run 與 SHA 證據保留。修正邊界後，18:40:31 UTC exact G6 loader 真實讀回成功、terminal 原 bytes 不變、current-restated=true／PIT=false，stdout SHA=`cfd8d6240f9ae8372172f748fc4fa73424e711ba6724410ccb3e1a193d85c136`。18:41–18:42 的新 run 又辨識衍生 feature snapshot 的 envelope digest 表示與 provider 入參不一致：獨立重算 15 列，裸值為 0/15 吻合，canonical prefix 為 15/15 吻合。QA 正確拒絕，未修改舊 artifact 或放寬逐列雜湊。該 run=`20261004T184134869586Z-6d0fdf88f5a4`，snapshot result=`rec_e01f496dc18243c68b2c6919c24ce3fc`，stdout SHA=`7f96bf6452513c1ecb43c7961403d593dda4ed3780149f4ef7551bfcbebfdddf`。衍生 feature／entry 正規化與一般 replay 路徑的現觀測累積接線仍在驗收；盤前同日 entry 未發布維持 pending，不能補造價格。

原生 v7 已真實完成 1477 正向分析、保存與 canonical readback，但驗收工具未接受正確保存成功對話框，並在 Rule 延後建立控制前取用下拉選擇器，因此未接受六情境。create-only v8 只補 exact result-id 成功提示與 reportLoaded 後可見 Rule 控制等待，保留同股／同 run／同日期及拒絕條件；尚待同版執行。

18:49:56 UTC 已將審查後的 V6 規則追加到兩個既有 operational prompts，exact SHA CAS 與磁碟讀回成功；只變更 prompt，ACTIVE／排程／target thread 保持不變。morning SHA=`975bae91592fc67b05026e0c4422e76e418438ce690cc223c5f7547eb4f4d02e`，paper SHA=`06772dd7a3186d7f30dc5b07da823408c45ea3b9b6eb02fe0d5826bba8a984d8`；applied receipt SHA=`d00a48e5c680c9d8a94c855368e206ff8fa6f4de821a1ccbf593d9f86ad5c1af`。應用程式快取重載仍未驗證，未新增提醒或 automation。

## 10/4 16:55 UTC 整合檢查點（歷史；跨日實跑發現接線缺口）

17:30 UTC 補驗：pipeline 已把年度日曆與臨時休市的 CLI 路徑傳給 learning child；兩個 argv 測試通過。受限 sandbox 的完整模組測試為 26 passed／8 failed，失敗集中於 Windows no-follow create-only stdout 讀回；正常權限、隔離短 Temp 的同一模組重跑為 **34 passed**，沒有修改保護檢查或 ACL。收據 `root/pipeline_calendar_elevated_20261004/receipt.json` SHA=`7a03bb84a3ed96e62c49dd4fa6ab07d87e782c838c913242cc49b46878828919`，stdout SHA=`e7ded7113c129b05ad23518949b3c5960d813e20445ec84961bfa28a7abec043`。17:17:33 UTC 另重新唯讀核對 21 tasks，均 enabled／Ready、action／schedule／working directory 符合，沒有 missing／unknown；inventory SHA=`42ed04c212df7bb94b484a6c19d141814ba60ef9142a67d96c9cf8622f3748da`，逐項比較見 `root/scheduler_final_inventory_v4/review_v2.json`。G9 完整 cohort 接線仍在實作，不將這兩項局部結果作為整體通過。

新的 G6 完整週期於 16:00:37–16:42:10 UTC 完成，raw run=`raw-pit-20261004T160038845246Z-1772-2c7457bdbf1e404cb519c1285d6acc2e`，terminal SHA=`db9864d91aa64b2da35c980fce6e59e91601abf5d9592e4dd5496dde1f9dcd35`；24 個程式 pins 與儲存設定未變。十股 exact public reader 於 16:43:10 UTC 全部核對通過，registry run=`20261002-ffb8777d33621369a15c3c22`、record SHA=`8a83462073cb0b2d29da8ec827f038c6ab4f67152fe461fc44f574b54f374cf1`，讀回 stdout SHA=`ecd1c8330202fdb77b8699770c793b3744a583dc90f6731ecd8c09f5988ecfb1`。正式 raw bootstrap 仍受容量門檻阻擋。重用未命中只有空 WAL mtime 差異，沒有主 DB、行情或 B 特徵數值改動，未放寬 guard。

G9 使用這筆精確 G6 執行預設策略，實際產生 15 檔 eligible cohort，決策日為臺北 10/5、資料日 10/2，result=`rec_bf7000f4f0b6417590ea5864edcdcedf`。同筆 snapshot／cohort 綁定、正式 DB／WAL、舊收據與 active pointer 前後皆核對不變；learning RC2，尚未接受。真正工程缺口是 live 交易日檢查未接既有官方年曆 cache；另有 QA helper 將 terminal SHA 裸值傳入要求前綴的 CLI，以及把 pending feature stub 當 captured 驗證。前者由 Scheduler 修補，後兩者僅新增 QA sibling，不改舊失敗、不冒充新自然成功。原 stdout SHA=`f752df9e18819353223bec45a967b5e62d1467877375ce682f5ba2e6a373ee82`。

持倉快訊歷史截日、跨股清除舊狀態、月營收同日擷取覆寫及季報 HTTP 失敗原文保存已完成窄修與獨立覆核。月營收仍保留解碼後 HTML 的內容身分，不能宣稱具備原 HTTP wire bytes 的 SHA。`astra-final-v8` 於 16:45:27–16:53:06 UTC 完成，97 個測試模組共 1,441 passed／9 skipped，七項檢查全部通過。Root 曾因非同步 freeze 訊息懷疑 selector 在執行中改動；實際核對七份 before／after inventories，均已是最終 selector SHA `84a6548be034aa7885055d8c144c370691b98b23d7bd57f970f6d6c9d7efaf57`，整批 source inventory SHA 皆為 `1c2ee07dbf867c9d75a7c45b34625130b4d5b70f3fd2bce9749703191d807828`，因此該疑慮不成立。接續的日曆修補仍須另跑最後版本。原生六情境與正式 Forward 受控重算尚待完成。

16:49:51 UTC 容量探針顯示 D 可用 285,741,309,952 bytes。從前次完整週期後至今（含一次完整重建及少量重用產物）實體增加 3,075,492,894 bytes；保守推估二十次同級成長為 61,509,857,880 bytes，另保留下一次啟動預算後餘 1,211,805,096 bytes，不含其他目錄成長。容量收據 SHA=`7b59e04555164504c6e94e10c0acbbcff03a8e32532e7d562d5ec6b08d8d3900`。這不是二十日自然證據，也不解除正式 275 GiB 門檻。

## 10/4 15:45 UTC 整合檢查點（歷史）

`astra-final-v7` 於 15:37:20–15:44:55 UTC 完成：93 個測試模組共 **1,415 passed／8 skipped**；Workbench 85 passed，更新頁 validator 25 passed／0 failed／4 skipped，指定全範圍 mypy 764 files、補充 ML／scripts mypy 31 files、179 檔 Python 編譯及精度／未來函數防禦均通過。七份收據的 source／tests／storage config 前後皆相同。Regression receipt SHA=`4c0d615e5eb83809dc07b1d35390b3cc5c5b476d16b2157e55556cfb85939f43`，stdout SHA=`df34069b5c867d5a37c17e8819f30e05392f1414dc52af2f6319699be94f1eb9`，路徑為 `root/frozen_checks/astra-final-v7-regression_0d7b5546fd534b3abc643f93c9d4c4f6/`。八個環境略過與 validator 四個非破壞性介面略過保留，不視為真下載／合併的驗收。

V5 的 sandbox no-follow 存取失敗與 v6 的八個排程測試失敗均保留原收據。V6 的八個 fixture 實際在臺北 23:00 完成預留截止後啟動，全部被真 guard 以 `heavy_chain_reservation_timeout` 攔住、`writes_evidence_db=false`；並非八項產品故障。修正只凍結測試中的 service／reservation wall clock，仍跑真 wait helper、monotonic deadline 與 OS lease，且既有 23:01 拒絕案例繼續通過。正式程式未因此放寬時限。

G6 同輸入重用的獨立 exact verifier 已於 15:15:24 UTC 通過：新 terminal SHA=`6f1d091d2dab00e172ce615bec02929ea64903f21793cc5370ff73748fafb873`，public verifier 及十股舊 completed 模型讀回一致；stdout SHA=`7291bc40603471f313926ed6d927f2a1b7e2dd335edf0acd23fb60a38b7d037c`。沒有重訓或另發 registry。SHM 僅跨次 mtime 可不同，路徑／bytes／SHA／型別與其他來源 pins 仍逐項核對；registry SHA 前綴只正規化格式，不接受錯誤內容。

G9 的 QA 工具已補齊 Shadow learning receipt 與 canonical 官方行情 custody 的不同根目錄；27 份既有引用、receipt 與 raw bytes/hash 兩次唯讀核對相同。只讀計畫 `root/automatic_cohort_plan_v4_20261004/` 通過，stdout SHA=`eb0ff84d52537e3d28fa2e55c083d751b01babd6537f0f8c7ff2c1d70339db5d`；實際預設策略→同筆 snapshot cohort→current-observed capture 仍待本次執行完成。原有 backfill receipt 保留 `not_proven_by_after_close_capture`，只用來核對舊證據未變，不授 PIT。

原生 v3／v4／v5 的失敗均保留。已確認的驗收工具問題包含 Qt orientation enum、DTO 收據漏股票碼／錯日期欄位，以及在 Rule 頁籤延後建立控制前讀取控制；真實 Windows 視窗與 1477 reportLoaded 事件已取得，但不據此宣稱六情境完成。Forward 的 v2 唯讀診斷十項 predicate 全部通過，正式寫入仍等真實 16:00 UTC 後的合法取得鎖時窗，不改時鐘或縮短預留。

新增官方擷取直接依賴 `urllib3>=2,<3`，Windows constraint 沿用已安裝的 2.6.2；未安裝或升級套件，與 requests 2.32.5 的 GET 520 retry 介面核對通過。未知根目錄 `paper_event_source_capture.py` 仍排除，尚未 stage／commit。

## 10/4 14:55 UTC 整合檢查點（歷史）

G6 v14 於 13:53:33.774563–14:33:55.771317 UTC 完成新完整週期。exact raw run 為 `raw-pit-20261004T135334829192Z-35880-8c0b7165231e4c1998dac57d4a30d592`；terminal `D:/Min/Python/Project/FA_ML_Research/current_stock_cycles/2026-10-02/cf3e95b9be7c5adf6a0b7ece41b47d9c/terminal_receipt.json` 的 SHA 為 `e2f230c79f9563148a9a950b9c2c80e02fc1f3068c4f5c73881e9b13469424ef`，child=`completed`，24 個程式 pins 與儲存設定前後一致。registry run=`20261002-2020580dac3752f3f5c067cc`，record SHA=`634bde8bf02a62ac88e09f5d657f02c9b85ae6e484a2a012fdaa46290633150a`。十股 public reader 的 cycle／run／模型／行情日／價格指紋已逐項重算核對：1225、1256、1465、1477、1560、1714、1721、2382、3207、9935；H5 均 `not_mature`，未產生假機率或正式資格。讀回收據在 `root/g6_v14_exact_ten_stock_readback_v2_20261004/`，stdout SHA=`c656642cc48891b7b153e5267a286fab3a68becd45e12cc4019013c9bb55b513`。第一版 ignored verifier 的 SHA 前綴字串比較失敗另保留。

容量已用本次完整成功週期實測：research root 實體成長 3,070,292,539 bytes、logical 成長 5,191,663,314 bytes；按每日一個同級週期估計二十個交易日成長 61,405,850,780 bytes。扣除下一週期啟動預算及 200 GiB reserve 後，當時仍餘 4,400,477,028 bytes；此預估不包含其他資料夾未來成長，也不是二十日自然成熟證據。after receipt SHA=`b79c3019ff2a7f91b036cd3f9f66bc65f8b0bffe69c513d089e55ee8cd7501df`。正式 raw bootstrap 的 275 GiB 門檻未降低，外層仍 `blocked_insufficient_storage`；研究 child 成功與正式來源建置阻擋必須分列。

Windows 真 OS reservation 已實測 busy 與 release：v14 執行中三秒 probe 逾時，owner PID／nonce／時鐘未變；完成後成功取得並只釋放自身鎖。兩份 receipt SHA 分別為 `4f502008ca893d0520bde11ddadefbe6a1a6f4f5d7ec144df9145519447857e0`、`c918210b6791311be7d9427e24e21394512ee6ec6b40e4066e145a982543a232`。Forward、Capture、手動 CLI 與 Evidence pipeline 已共用 canonical DB reservation，dry-run 使用唯讀 repository；官方到期日缺價不再以更晚行情替代。最終 Data 獨立回歸 100 passed，receipt SHA=`a55320daa27c6c8f92e350419383445e05596c376c3d1ef1eb701a5eac653bc6`。14:53 受控 Forward 在 dry-run 前後一致性檢查停止，尚未正式寫入；原失敗保留待診斷。

第二次真實 cycle 回 `skipped_same_inputs`，新 terminal SHA=`6f1d091d2dab00e172ce615bec02929ea64903f21793cc5370ff73748fafb873`；root 額外 reuse verifier 對 `current_source_observation` 的比較尚待釐清，不能先宣稱額外 verifier 通過。`astra-final-v5` 已於 14:51 UTC 開始最終 91 檔整合回歸／158 檔編譯；同版 native v3 已真正啟動 Windows 視窗，首個來源恢復情境在讀觀察清單欄名時失敗，尚未完成六情境接受。

兩個既有 operational prompts 的 v4 已於 14:30:42 UTC CAS 更新與磁碟讀回，僅追加官方日曆、缺價與共享 writer 規則；未改 ACTIVE、排程或 target thread。morning SHA=`64aae95a53caa8657d1f2384a01dd3e7363873f5c6d353ffa3c1aedd43192c98`，paper SHA=`592128ba7f05a19d9c7fe913b1000feb95720302413235a424b47175bdd1a333`。app 快取重新載入仍未驗證。

### 較早整合檢查點（保留原批次範圍）

v13 的 registry 拒絕已定位為 publisher 使用裸 SHA、controller 使用 `sha256:` 前綴的同值比較錯誤。修補在四個 digest 邊界做嚴格格式正規化，仍逐項核對 cycle／raw run／source date／symbols、完整行情指紋、projection 路徑與 hash、registry index／record hash 及非正式資格。Owner 與另一位 Luna Max 的 54 項回歸、真實 v13 record 唯讀覆核皆通過；這不改變 v13 failed terminal。新 v14 於 13:53:33 UTC 開始，raw run `raw-pit-20261004T135334829192Z-35880-8c0b7165231e4c1998dac57d4a30d592`，14:05:41 UTC 進入 fit，仍待完整接受。

G6 執行期間的真實 Windows OS 競爭 probe 已通過：第二個程序等待三秒後 `timed_out`，原 raw run／G6 child 維持 running，owner PID／nonce hash／建立時鐘前後一致，沒有開啟 DB 或啟動 producer。收據 `root/g6_v14_busy_lock_probe_20261004.json` SHA `4f502008ca893d0520bde11ddadefbe6a1a6f4f5d7ec144df9145519447857e0`。取得後釋放仍需待 v14 結束另驗。

Decision Capture／Scheduled Forward 的共用 reservation 已完成 owner 80 項測試，Data 正獨立覆核。Forward dry-run 與 health reader 都以 `read_only=True` 開啟 repository；取得鎖後日期／期限拒絕時先釋鎖再落終端收據，釋鎖錯誤保留在 receipt。另查明手動 Forward、Evidence pipeline 與歷史 replay 尚未注入日曆，正補齊同一 verified factory；核心未提供日曆時停止結果計算，不能留下 row-offset 旁路。這些最終修補仍須完整同版回歸。

G6 v13 於 13:32:19.472793 UTC 結束；24 個 producer pins 與 storage config 前後一致。fit 與 sidecar 完成，controller 在 registry 回讀拒絕：`immutable ML registry record is not bound to this current-stock cycle`。精確 failed terminal SHA `cdc4b9f477b7c2b114e487c061a49f13d1435f765f3fd0efcd2395a7210b7121`。外層 wrapper RC0 不代表 child 成功；raw 另為 `blocked_insufficient_storage`。本次不接受為完整成功，原模型、registry、terminal 均保留，正逐欄核對 publisher／controller／consumer 身分契約。

v13 容量收據 `root/capacity_probe/controlled_v13_failed_after_20261004.json`（SHA `4a166878c9782f4445f6b7289a63aba76269d053edc31a77a075494b196a8afa`）只記錄失敗批次增長：active research root allocated 增加 3,069,945,242 bytes、logical 增加 5,191,704,948 bytes；未填 `observed_full_cycles`，未將它算成完整成功或二十日容量接受。D 當時高於下一次同級初始預算 51,854,680,064 bytes，正式 raw 的 275 GiB 門檻仍不放寬。

最後實際回歸額外辨識三項有限缺口。保存來源沒有行情日時，公開 DTO 原先以決策日補上，現已保留空行情日並獨立呈現決策日，22 項測試及第二位 Luna Max 覆核通過。05:25 Decision Capture 與 05:40 Forward 是 canonical DB 寫入者，原先未共用 G6 的重型研究鎖；兩個 writer 正接入同一 OS reservation，採有界等待、實際取得後重驗日期／剩餘時間，取得前不啟動 RW DB。共用 helper 已以 22 項測試（含 Windows 真實跨程序競爭）驗證，consumer 尚待凍結。

1538 的舊 H5 到期日衝突也已定位：9/10 決策的第五個官方交易日是 9/17，但舊計算跳過缺價列，直到 10/2 才湊足五筆。9/17 官方 raw custody 的 OHLC 確實為 `--`。修補正改成只查官方到期 session；已到期但缺價應為明確來源缺件及 null 報酬，不能延長 horizon 或標成尚待五日成熟。原 12:40 自然 Forward 的 172 筆 upsert、RC2 及衝突收據保留；新程式尚待同版驗收。

13:00 自然 Paper EOD 的 gate 是合法 `not_trading_day`／Taipei weekend，Task RC0，adapter 未呼叫、沒有新 Paper execution／ledger mutation；收據 SHA `6abe1361607a2d950824206b46ab352427a6287f85712b1c419549d58b68b8dd`。這不構成新的 35 筆 Paper 記錄或三個 capture-ready 結果，亦未宣稱外層 retry runner 的其他配置檔完全零寫入。

下列以本節最新證據為準，較早批次仍保留原失敗。12:49:41 UTC 啟動新的受控 G6 `raw-pit-20261004T124942616685Z-22764-2e7de468752e4af9a2f8eb5643263a09`，全部 producer 程式已凍結。`astra-final-v4` 同步執行 77 個測試檔的完整回歸；Workbench、validator 與兩組 mypy 已通過，尚未用局部結果接受完整 ML／native UI。

`astra-final-v4` 於 12:57:58 UTC 完成且全數通過：77 檔共 1,199 passed／8 skipped（449.91 秒），Workbench 85 passed，validator 25 passed／0 failed／4 skipped，全域 mypy 762 files、scoped mypy 25 files、135 個 Python 編譯及量化 guard 通過。全部檢查前後 source／tests／storage config 不變；回歸 receipt SHA `c9e077fe68dd73e1c6cc664f0ac734236d6398e7aa5644070e403fd80d7ed45a`，stdout SHA `4e15a9db32003ce9422f39b4a35409fc18a4bda5db1f3d2fdd0480e88f737bfc`。若後續 writer 協調新增修補，仍另驗該最終版本，不用 v4 替代。

空 WAL 根因已核實：12:05 run 失敗時主 DB 的 bytes／SHA／mtime 未變，WAL 仍為 0 bytes／空內容 SHA，僅 mtime 從 11:33:01.9803306Z 變成 12:10:07.4714797Z。修補只豁免符合此明確空檔契約的跨次 mtime 差異，同次讀取穩定性及所有其他 pins 維持嚴格。兩位 Luna Max 分別實作／獨立審查，17 項相關測試、mypy 及編譯通過；gate SHA `6e2c5f03232edbd6f6456d6ddc98cd8923c8483d7e6fb6d765f0dd69e9ab74a9`。12:40 之後 WAL 真實新增為 955,872 bytes，舊 snapshot 的 public verifier 正確拒絕，不將它補記為成功。新 run 重新建立來源快照；自然寫入與研究鎖的協調另行查核。

G7 的 520 已加入既有有界 retry 清單，28 項測試通過。新受控 run `20261004T123932996802Z-9a8319f03e` 於 12:40:04.974129Z 結束，15/15 來源、3,140 檔證券成功，partial_failure=false。獨立 public-reader 核對 manifest、snapshot、15 個 final-response raw hashes 與八股內容：2323／2601／3085／4527／5301 listed，2867／5371／8183 delisted，5371 官方終止日 9/3；皆為 current-only、PIT=false。回讀收據 SHA `10b6746e1e1bbe70f07767f444d2a711990a1c3d4fcb6f11919eb5b01dd68bd6`。11:50 自然失敗及 v4／v5 partial 批次各自保留，未拼接為一批成功。

法人未來新增觀測的原子投影、官方值回復 base 及同時鐘全部修訂衝突檢查已完成，61 項回歸通過。現況 reader 僅供目前個股報告法人區塊使用，未擴增推薦排名或 CORE19／20 特徵。既有 849 筆已套用修訂與今日來源數值一致，沒有重複 apply。G9 容量契約也已完成：41 項容量案例、38 項等待案例與 4 項 immutable capture／public verifier 重播案例通過；仍須由完整真實 G6 接受結果。

12:45 自然 G9 `20261004-20261004T124502536699Z-e99b9af94df3` 已於 12:46:15 UTC 以 failed 結束，精確依賴原 12:05 failed G6；Quick 未啟動，official 與 snapshot child 完成，learning 正確 blocked。它在新的受控 G6 啟動前已結束，未誤用後來 latest。自然 receipt SHA `0a2d49cf21bceedfa04be32435da020bef5976410eb9072b36246ff3a7d32bbc`。

12:50 Bank 自然 run `2026-10-04-attempt-001-94af5c511dae` 為合法 `skipped_non_trading_day`／weekend_closed，Task RC0、沒有 child，upstream wait 不適用且 poll_count=0。Receipt SHA `972d0d9953bf8977980804db8f3eb126ca710837b3f5314e5f63220df7e2d18c` 與 status pin 相符；此結果不代表交易日 G9 依賴已通過。

12:05 自然 raw run `raw-pit-20261004T120502848236Z-28832-f7caa53c28bd44e99c92de4a2adc877a` 已於 12:15 終止。研究 child 在 outcome_artifact 拒絕繼續，原因為 `source WAL modification timestamp differs from its receipt pin`；精確 terminal SHA `f828079ac33a33236ad6c95c4e552937376f7d2bcacdc1ac8bf0ce6640ea4466`。唯讀 observer 保留前後 status bytes、Task／PID 時鐘及程式變更；此 run 不能作最終同版成功。正式 G9 等待器釘住相同 run、等待 540.485 秒後正確拒絕，四個 consumer 程式 hash 與 storage config 均未變。原始 WAL 是否只有空檔中繼資料變動正在獨立查核，沒有關閉來源保護。外層正式 raw 仍受 275 GiB headroom 阻擋，與 child 的 WAL 問題分別處理。

11:50 自然 official bundle 的 TPEx 終止上櫃 feed 回傳有效 `tables/fields/data` JSON，原 parser 未支援而失敗。已補嚴格欄位、日期、列長及 totalCount 驗證，25 項測試與獨立覆核通過；source SHA `0555c61e0667d2ca8f07da6995cc0ce47af3a81fa59e5e76d5fdd5ffb0bd5cf2`。12:14 新受控 run `20261004T121420686222Z-8af6a38cf9` 成功 14/15 來源，5371 已有官方終止日 2026-09-03 的實際現況證據；仍失敗的 TPEx disposition feed 為 HTTP 520。這個受控 run 不覆寫或替代 11:50 自然失敗。

月營收與季報的現在觀測自動路徑已由兩位 Luna Max 分別追通：weekly wrapper 在 core 成功後預設呼叫 MOPS HTML updater，追加 canonical current 表，推薦月營收及個股財報 reader 可直接消費。Quick／quarterly OpenAPI 的研究候選是不同來源路徑，單位或 basis 未核實時仍不 apply。本週 weekly 預定 10/4 18:00 Pacific（10/5 01:00 UTC），尚未到期，不能把沒有新收據判為故障。

v11 sidecar 已查明是直接 Python Invocation 保留 `sha256:` 前綴，而 CLI 先移除前綴；八項 hash 的底層值相同。已在 Invocation 建構邊界做嚴格格式正規化，錯誤值仍拒絕，橋接程式 SHA `b64935d04dd6617c65d463bf327b3332b024120fc68addbee6a8a6dc7db0faac`。舊 v11 manifest 釘選舊程式，不能重用或改標成功，待新完整週期。

G9 三項排程修補已凍結並通過另一位 Luna Max 的獨立覆核、64 項測試：逐 child 保留 learning／flush 預算、Quick writer 啟動前有限 OS reservation 交接，以及週末使用已驗證 G6 的 source session。Pipeline SHA 為 `a859dc85c7db50a001b60fabb3f3538c34f9cb314566ecd94441333c019ba7fb`。正式 raw bootstrap 的 275 GiB 門檻不變；新容量隔離只在完整驗證獨立研究 terminal／原始 reuse terminal、自身容量、來源及資格後允許 G9 消費，不把外層 raw status 改成完成。容量證明正在補齊必填預算、實際 terminal 所在研究根目錄的綁定，以及 active D／legacy C 重用讀取，仍待最終同版回歸及實跑。

11:52:42 UTC 的新 inventory 確認 21 個既有 tasks 皆可讀，command、working directory 與 schedule 全符，沒有把讀取失敗當成 missing。11:43:16 UTC 已以 compare-and-swap 同步兩個既有 operational prompts；morning SHA 為 `10c2dca70addf45fbabecaae785c9232a14c8f5e8b1161fbe645ba9bb14fe7b5`、paper SHA 為 `c9b2f9d46a64101ddfb2624e2e680cdad0e6680b10c550eaabbeaf9310381cd0`，其餘欄位未改；實際 app 快取採用仍未驗證。

11:20 自然 Quick `20261004-26372` 於 11:33:22 UTC 完成 core，errors 0、六個 institutional reconciliation warning；技術資料為 10/02，publication receipt SHA `c666dbfdd2dc585593ba2e619e910b462723f36a4c159d58f0f8540bf273344d`。root 唯讀比較六份新 canonical observation 與昨天已接受原件的全部數值／來源欄位，及 599／44／36／38／53／79 共 849 筆修訂，全部一致；沒有重複 apply，也沒有改舊衝突。證據在 `root/natural_quick_20261004/`。後續查明未來新觀測沒有自動進入現況 revision projector，且官方值回復基底值時可能遺留舊修訂；ML owner 正修兩個原子寫入點及現況選版，保留 base、實際觀測時鐘與 FAILED_RETRYABLE checkpoint。這是 G4 自動累積的新增確證子項，不能重列昨日 849 筆為未完成。

v10 的多行 JSON 與大型 fit-audit 讀取契約已修復。v11 在 10:13:53–10:54:50 UTC 完整執行到 sidecar，fit 成功但重新載入模型後出現 `reloaded model source/context/Direct/B pins differ from this invocation`，因此 cycle 仍為 failed；失敗 terminal SHA `4875bde1e3ad3c23aec6aafff90e57746650d410b285c4ffacbeeb0db9ec9731`。精確 run 為 `raw-pit-20261004T101354617035Z-34436-725fbad8cb9245a698c5e51a031cbaa6`。原模型、manifest、失敗 terminal 與 2,432 秒 G9 等待收據全保留；前綴根因已修，不能放寬比對或改寫舊 run 成功。

v11 外層另為 `blocked_insufficient_storage`：正式 raw bootstrap 要求 295,279,001,600 bytes，D 可用 289,279,737,856 bytes；研究 cycle 的 223,165,721,608 bytes 初始預算是另一用途，不能混同。`capacity_probe/v11_failed_after_20261004.json` SHA `20180971c93fe8f5b261ed14561a830adb9a2c3c6e69cfd50c84ab00b2a43473` 只記失敗週期成長量，不作完整成功或二十日容量接受。

自然排程順序亦發現實際缺口：G6 超過 40 分鐘時，05:45 pipeline 在等待 exact G6 前先啟 Quick，雖共同 OS 鎖阻止同時改 DB，卻會留下本可避免的技術更新失敗；自訂 canonical `OUTPUT_ROOT` 另可能使 Quick 的硬編根與 raw 鎖分叉。Scheduler 正窄修為先等待 exact 依賴，再啟 Quick，並統一 canonical root／鎖傳遞。完整新週期、十股讀回、同輸入重用、自動 cohort 與原生 UI 均仍待接受。

G5 最新 SQLite probe v6 exit 0，1477／2382 current PE／YoY 值與篩選結果已核對。Snapshot／personalization 官方基本面 source root 與 artifact root 已分離，獨立 factory／preparer 回歸 28 passed、snapshot wrapper 21 passed。原生 UI 將在新 ML 發布後以最終版本驗收；09:27 的舊 preflight 不作最終證據。

最後一致版本 `astra-final-v3` 於 10:14:50–10:21:20 UTC 全部通過，程式、測試及儲存設定前後未變：Workbench 85 passed；validator 25 passed／0 failed／4 skipped；全域 mypy 761 files、scoped mypy 25 files；70 個相關測試檔共 1,064 passed／8 skipped；126 個 Python 檔案編譯與量化精度／未來函數 guard 通過。完整回歸收據 SHA `b460d4ed599a2cee9fce8bcfe5612bbe437341057d09387cc779294c873e944b`，位於 `root/frozen_checks/astra-final-v3-regression_090301ae0d814bfd992ead9a9b5a47d3/receipt.json`。較早 Windows MAX_PATH 失敗另以同測例短路徑 243 字元通過、長路徑 287 字元失敗對照確認；沒有修改 production 或放寬測試條件。

8 個 skipped 由相同 70 檔的 1,072 個 collected nodeids 與原始進度逐項對齊：BankTaiwan status／receipt 4 個參數案例、current-observed fitter 1 個、ML output boundary 2 個、scheduled projection 1 個，均為 symlink／reparse 負例。另以 `-rs` 定向重探確認目前 Windows 無建立 symlink 權限，BankTaiwan 提升執行後仍為 WinError 1314；未更改 ACL。v3 原始 `-q` 未保存 skip reason，不能把後測例外碼冒充當次例外。原 stdout SHA `713dd4a52c2d7169cb9bb56db9a1a8b3d9c2ed2e009787ea6e84f137dcba16ec`。Validator 的四項跳過是既有接口模式，沒有執行實際大量下載／合併；本輪真實來源擷取與資料讀回另有獨立證據。

### 09:42 UTC 最後回歸與自動 cohort 接線查核

第二輪完整回歸為 989 passed、8 skipped、11 failed；其中十項是 raw-source-scan 測試 adapter 未轉送新增的 `access` 參數，production guard 沒有放寬。修正 fixture 後十項皆通過。另一項是 Windows 長路徑超過 260 字元；QA orchestration 改用授權 Temp 下全新且更短的目錄，保留原失敗收據。Workbench 85 項、validator 25 pass／0 fail／4 skip、全域 mypy 761 files 與 scoped mypy 23 files 已通過，仍須完成最後一致版本回歸。

自動 snapshot 額外查出真實工程缺口：Shadow `--output-root` 同時送進 current-fundamental provider，導致官方 PE reader 從 Shadow/current_valuation 取值，而現有 capture 在 canonical FA_Data/output/current_valuation。這不會回退舊 formal PE，但會漏掉可取得的當日估值。已交 Scheduler Luna Max 修正輸入來源根與結果輸出根、pipeline／Bank forwarding，並加入 public factory／reader 與實際自動 cohort 驗收；完成前 G5／G9 自動估值接線不可結案。手工指定股票的 G5 probe 不能取代此入口的驗收。

補充實際影響：目前 scheduled default strategy 未啟用 PE／YoY 篩選，不能把上述 root 缺口寫成已證實預設 cohort 曾因缺 PE 而錯選。問題影響使用該 factory 的可選基本面條件與個人化配置；修復仍須完成。自動 cohort 驗收保留原策略，分別記錄 snapshot 實際消費的欄位、canonical provider 在同次 cutoff 下可讀的基本面，以及已啟用 PE／YoY 的專門真資料正負篩選證據。

### 09:46 UTC 既有 operational prompts 第二次受控同步

僅更新 morning-report 與 paper 兩個既有 prompt 的內容，增加 active ML storage、同 run 依賴等待、容量假設，以及官方估值／月營收 input root 和 Shadow output root 的分離核對。原始 bytes 與全部非 prompt 欄位以 compare-and-swap 核實，ACTIVE、05:30／06:20 排程和 target thread 皆未變更。落盤後讀回成功；應用程式快取是否重新載入仍未驗證，不能宣稱下一次自然執行已採用。

收據 `root/operational_prompt_update_v2/applied_receipt.json`；morning SHA `01609e36e8984fc9b4de76cbc6a6facaaf4ca185c99cd0cf774653e477b3b40f`，paper SHA `01dd03a653d3262cfdb71cde11892f7fb627acf432559bc208a1d766c663165f`。完整 apply 命令 09:46:09 UTC exit 0，保留原備份與上一版失敗／自然歷史。

### 09:51 UTC v10 真實訓練完成、controller 回傳解析失敗

v10 wrapper 09:24:31–09:51:41 UTC，24 production pins 與 storage 設定前後一致。fit child exit 0，實際訓練 29,927 樣本／40 folds，建立模型、十股 current vectors 與 fit audit；fit stdout 為 10,431 bytes 合法多行 JSON（SHA `e2e4a748f1b5b74437c545dbc87e7a7c6c78ad63f667d42ea29ce6be0c80d85b`）。controller 只按單行解碼而拒絕其完整 receipt，整個 cycle terminal 為 **failed**，SHA `96070270416a60b0064790ede46dab6ffdf4ae073e7270fb9cfc656f5efbc476`，沒有 publish／registry 成功證據。model manifest SHA `f341365de562402d0bd8efa9ec01447af07f0073df3edc5ae72b7a4a4bd0620c`，bundle SHA `8b6a32d5e69dafe42b409cbd562a021da53a38a989740968d4785d0fc020e8cf`；保留此失敗週期及模型，不回寫成功或拿它替完整驗收。

G9 實際從 09:24:51 等到 09:51:42 UTC，共 1,611.469 秒，維持相同 raw run 與 code/config pins，因 exact child failed 而拒絕放行。此收據證明等待與失敗阻擋，**不是成功相依接線證據**。已交 ML Luna Max 修正 bounded JSON framing 並補 CLI 實際多行格式回歸，修後須用新 raw run 再跑完整週期。`capacity_probe/v10_failed_after_20261004.json` 是本次失敗成長量測，未宣稱一次完整成功 cycle，也未以它推稱二十日已成熟。

## 10/4 08:18 UTC 接線與儲存設定讀回

08:14:51 UTC 以 create-only 寫入本機 `output/ml_research_storage.json`（106 bytes，SHA `39198481b876830d195388bfa54930c6e84c28a7ebec358550a6d4c8a3763ccc`），active root 為 `D:/Min/Python/Project/FA_ML_Research`。設定與原 v7 失敗 terminal 均實際讀回；terminal SHA 保持 `35ced633b371ef41a2dbce90ac47787fa50b27ce3d21a9ef6b3dcb6c07a8f35f`。舊研究根、canonical DATA_ROOT、Shadow 的研究寫入嘗試全部被 resolver 拒絕，沒有搬移或刪除檔案。證據在 `root/d_research_storage_activation/receipt.json`；中央模組 SHA `93e9efe69bca81df4f28eafe3ae7f2728c6b6c288823ad4fde1f81f198e38c9b`。

root 在真實 Windows 檔案系統獨立跑 boundary／G9 focused 46 passed、2 skipped（環境不允許建立 symlink）；啟用設定後再跑 producer／registry／projection／dependency／fit 164 passed、1 skipped。各自證據為 `root/storage_root_independent_v1`（08:14:04–08:14:08 UTC，stdout SHA `7b7433a5e72cd80cd74fa56c32f420e63f01dc59dcb91d7f0bfe3bb0263631e4`）與 `root/storage_scheduler_independent_v1`（08:17:43–08:18:03 UTC，stdout SHA `9a2e1ae3b7b8e6d14568bd5bf7d9cb828a9f63c3ce0f7ee8acb47a1848db778d`）。測試只寫隔離 fixture，這些不是完整 v8 成功證據。

08:18:22 UTC 最新 21-task inventory 為 21 available／Enabled／Ready、0 missing／unknown／action／schedule mismatch。Bank task 實際期限 `PT5H`，LastRun／LastTaskResult 仍屬 10/3 自然批次；`root/scheduler_final_inventory_v1/inventory.json` 保存完整查詢。v8 實跑、消費／重用、原生 UI 與最終同版回歸仍待新增實際結果；交叉審查發現的舊比較值 fallback、未來行情日保存 Advice 與三個 research opt-in CLI writer 邊界正做窄修，尚不能結案。

## 10/4 07:42 UTC 進度與新增的有限修復

G5 的自然行情日期、personal 同次 frame、實際診斷列數限額已完成 owner 204 項回歸及獨立 17 項覆核；G4 已補正規化版本、來源／輸出碰撞、觀測時間不得早於 raw capture 的保護，46 項測試及獨立覆核通過。較早不完整／失敗驗收仍保留，不用本段覆寫。最終真實 SQLite probe、同版 native UI 與全路由回歸仍待完成。

G6 v7 因容量保護中止，使原本的「每日新交易日累積」暴露具體工程阻礙：C 剩餘約 204 GiB，其中 200 GiB 為不可降低的 reserve，並非全部可投入資料增長。唯讀盤點 45 份大型 SQLite 的 logical／allocated bytes、sidecars 與收據線索保存於 `capacity_inventory_20261004/sqlite_capacity_inventory.json`，SHA `73ff9548e314c725562c9fb380a0f7569e45053177f8138f219b81fc5cd881cd`。沒有清理未閉合副本、working data 或 WP5 資料。

本輪新增修復限於研究產物儲存接線：ML owner 負責中央 root 設定／邊界及非排程 reader，Scheduler owner 負責 raw／B／cycle、registry／UI 與 G9 consumer 的 root 一致性。預定以 repository 固定、忽略提交的 `output/ml_research_storage.json` 指定新 `D:/Min/Python/Project/FA_ML_Research`；無設定仍採 legacy C，原 C artifacts 與絕對 path／hash 不搬移、不改寫。active root 與原始 DATA_ROOT、formal release、Shadow 學習根保持隔離；invalid config、路徑別名或越界仍拒絕，容量門檻維持 logical 預算與 200 GiB reserve。

07:33:38 UTC root 已對不存在的新研究目錄進行空目錄 NTFS 壓縮設定，並驗證一份新合成 SQLite 的壓縮繼承、4,096 rows 與完整性；logical 5,615,616／allocated 716,800 bytes。收據 `root/d_research_storage_preparation/receipt.json` 明示這不是每日資料壓縮率樣本，也尚未啟用 active-root config。須待程式凍結、獨立邊界回歸、實際新 G6 完整週期、10 股 readback、same-input reuse、G9 exact-pin 消費及增長量實測後，才能判斷容量與自動累積路徑是否就緒。

## 盤點基線與分工

- 23:34:32 UTC 基線保存於 `output/qa/astra_engineering_20261003/baseline_manifest.json`，3,465 個 tracked 檔案 SHA；原有唯一未追蹤檔 `paper_event_source_capture.py` 保留、不提交。
- 六個子代理均以工具明確指定 `model=gpt-6-luna`、`reasoning_effort=max` 啟動並實際回報：Data、UI、Scheduler、ML／Portfolio／Exit、Official Status、Native QA 準備。工具接受此配置；未提供額外模型內部自我檢視資訊，不推測或替換模型。
- 9/29 Graphify 圖譜僅協助定位關係；目前程式與當次資料／收據才是事實來源。較早 06:41 排程診斷不覆蓋後續 11:12 與資料收尾修正。
- CIM 唯讀檢查僅觀察到專案 MCP／formatter，未看到當時的 producer／UI writer；這不能證明其他對話不存在。修改前後仍檢查 working tree；共享程式由單一 owner 編輯，資料庫與 scheduler 操作由 root 串行。

## 有限缺口清單

下表維持本次有限工程範圍，實際接受狀態以文件最上方最後檢查點為準。G1–G10 的程式與有限真資料驗證已有 v15 七項檢查及各自收據；G7 即時下市排除已納入最後 50 檔實跑。G8 最後原生全情境與 G11 新資料讀取／自然保存修後驗收仍待完成。最新原生回歸發現的來源日期漏投影及跨頁預設時區差異均列工程修補，不列為自然成熟。

| ID | 根因／受影響功能 | 判定與修補邊界 | Owner／驗收 |
|---|---|---|---|
| G1 | Watchlist 來源列表忽略股票碼，綁定前未核對同股 run；空推薦結果阻擋保存同次真實篩選紀錄；退化三角形崩潰；已知行情日期又在保存／重開過程遺失 | 工程缺口；exact 股碼／run／日期／完整性列選項並於綁定前重驗；保存未入選原因不冒充推薦；退化擬合不產生訊號；同次 v1 provenance 保存實際行情日，不新增可重播來源引用或 PIT 資格 | UI＋Data；保存重開、取消、異股、錯日期／run、篩選矩陣、formal 空時鐘及 provenance 衝突測試 |
| G2 | MainWindow 未注入個股報告 ML／Exit providers；正常頁固定不可用 | 工程缺口；真正 app 層唯讀 adapter、來源與模型資格驗證、UI 接線；Exit 現況與事後有效性分開 | ML＋UI；真內容讀回、錯股／未來時鐘／錯 run 拒絕，不產生假機率 |
| G3 | 歷史報告借今天持倉；未連結持倉入口以 last_trade_date 標行情日；研究報告把台北前一日 Freshness 收據整份排除，亦未在同日發布截止後重驗或拒絕無效明示來源時鐘 | 工程缺口；歷史持倉需可驗證快照；現況入口按同部位／股票的表格快照傳遞行情日，linked identity 保留；當下日價以單次 aware clock、官方 session、actual／expected／quote period 及合法來源時間核對，月季與歷史不放寬 | ML＋Data；日期／錯股／未來／linked 回歸，40 項報告測試及獨立 source-clock／Health gate 負例；canonical D 2382 跨日讀回為 fresh，真實帳本 Health 另由原生驗收 |
| G4 | current 季報的 basis／aggregate eligibility 未完整通過儲存與 DTO | 工程缺口；真實可觀測數值保留，未知 cash-flow 期間基礎不能用於累計／比率 | Data；逐欄來源單位與 basis 傳遞、舊 schema 相容、正式 PIT 不變 |
| G5 | 既有 SQLite 估值僅 PE 且最後日期為 8/6；個股研究與選股 PE／月營收篩選尚未消費新取得的現況資料 | 工程缺口；新增 current-only 官方擷取與讀回，固定單次 invocation 的 aware UTC 截止時間，保留 raw SHA／實際取得時鐘；explicit cutoff／historical research 維持既有 PIT。月營收 YoY 必須有真實同月去年值；P/S 維持原有 governed external／backfill policy，不另推算 | Data＋ML＋Luna 獨立 reviewer；公開 read_report／推薦入口、未來 capture 拒絕、保存 lineage、歷史路徑不讀 current |
| G6 | 每日 capture／projection 尚缺自然 B adapt／consume 與後續 bounded 研究模型 producer／registry 接線；重型建置另受容量阻擋；長研究週期與同窗 Evidence writer 未共用 reservation | 補全研究鏈、中央儲存根與同 DB writer 串行。Operational receipts 留 D canonical output，新研究 artifacts 寫獨立 active D 根；舊 C artifacts 依原 pin 唯讀。維持 200 GiB reserve、正式來源隔離與所有資格限制 | Scheduler＋ML；同 run／date／hash、實際 fit／registry／十股讀回、同輸入重用、完整週期容量量測及互斥寫入 |
| G7 | 8 檔未出現在 10/2 報價表，不能據缺 row 推論下市／停牌；完整選股另發現已獲官方下市現況證據的 4130 仍被分類為歷史不足 | 官方狀態查核及共用即時推薦接線；僅以決策當下已取得、已驗證的終止狀態排除現況候選並保存理由與 lineage，不反向授歷史 PIT。另逐項核對七檔短歷史，區分新掛牌、下市與來源缺件 | Official＋ML；逐碼來源／日期／影響，手動與排程共用判斷，未知／未來觀測不誤排除 |
| G8 | 舊 native 部分截圖仍在 loading；盤勢新高低重複掃描；QA 捲動未真正將 Advice／Rule 帶入 viewport；Desk／主力流向／Update 日期窗口使用 host date 而與臺北 current scope 不一致；盤勢未另保存實際來源行情日 | 保持數值語義的一次聚合；用 native worker 堆疊區分實際阻斷與 QA 等待行為；各區獨立定位、重繪及可見內容截圖；預設／更新日期沿共用臺北時鐘，明示歷史截止保留；盤勢最後有效行情日經 DTO／lineage 傳到可見 UI，判斷生效日不變。90 秒門檻不變 | Scheduler＋ML＋Native 準備＋root；四用途、1477、保存重開、切股、重複／取消／重試、1.0／1.25 縮放、LA／臺北跨日與營收期別邊界 |
| G9 | 自然推薦學習先執行歷史來源預檢，正式修訂 hold 一旦觸發即 early return；新現況支線又將 Shadow snapshot root 誤作 canonical raw root，且未等待 G6 完成。跨日實跑另確認官方日曆 cache 未傳到底；預設最多 50 檔推薦與 feature provider 單批 16 檔不相容 | 工程控制流程缺口；隔離 historical replay／formal training 與 prospective 累積；分開原推薦 snapshot、G6 source 及 learning output，等待精確 run 後以真時鐘捕獲。日曆 CLI／環境／預設路徑須跨 pipeline、dependency、capture、feature 共用。17–50 檔以明確版本的完整 cohort composition 分批，每批仍至多 16 檔，保留各批原始來源 hashes；缺批不可成為完整 capture。保持原 PIT／promotion 保護，不回填歷史特徵 | ML＋Scheduler＋Data，Scope 獨立審查；精確失敗 run、自然 wrapper argv／root、同 run 等待／超時、完整 cohort／批次邊界與錯誤 pins 負例、實際現在觀測讀回 |
| G10 | Forward 依有效價格列位移選到更晚日期，缺 verified calendar 的 caller 仍可能產生 READY；手動 Evidence writer 與排程互斥不完整；只有日期的截止值可能讀取當日未收盤行情 | 官方 session 決定 exact 目標日，缺價與未到期分列；凍結單次 aware invocation，所有價格讀取受收盤邊界限制，保留明示歷史截止；dry-run 真正唯讀，正式 DB writer 共用 canonical lease | Scope＋Scheduler，ML 協助真實受控 QA；1538 原 9/17／9/24 缺價不能借後日，43 事件／172 outcomes 保留原自然失敗後受控重算，盤前有／無當日列、盤後真缺價、跨日／busy／手動入口負例 |
| G11 | 10/2 法人／信用／集保列已在候選 DB，current 個股報告仍讀正式 DB 的 9/8／9/4；候選隔離未附可用的當下觀測讀取路徑 | 新發現的工程缺口；補 current-only reader；法人／信用驗正規化 observation SHA／同股數值／aware 時鐘並明示 raw 原件未保存，集保重播獨立官方原件與 hash-bound manifest。既有週一 Quick 持續保存獨立 TDCC capture。publication 未知不補值，歷史不借新觀測、候選不升正式，不以 summary 時鐘替代 raw 證明 | ML owner、Data 獨立覆核、root 真資料及同版原生驗收；仍在實作，不能據 v15 宣稱完成 |

UI 現況入口沒有全域漏讀 current 基本面的證據：只有 context 有明確歷史決策日才傳 `as_of_date`，並按既有 PIT 邊界排除 current observations；無綁來源的現況研究保留 current 路徑。對這項增加公開路徑驗證，不移除日期保護。

G5 後續另查出現況基本面 provider 的預設日曆只接 SQLite，未接既有官方快取，會在平日休市後回推時卡在未知。已補 repo-root 年度／臨時休市 custody 路徑，明示路徑優先、不因 OUTPUT_ROOT 或 CWD 漂移，維持離線與原發布截止；39 項 provider／source-root 測試通過。這項改動屬 G9 的 53 個 producer pins，故在 23:33 UTC 另啟最後 50 檔批次，不能只沿用先前 v8 成功。G8 亦補缺少得分／訊號強度顯示未知，真實零值保留。

G8 的更新狀態頁另已統一 Freshness producer／consumer 的 LA 04:30 發布週期。新收據明示時區，legacy 僅相容精確既有 task；跨台北或 LA 午夜但尚未跨發布截止不誤降級。82 項定向測試通過、1 個既有 Windows symlink 權限 skip。00:35 UTC 對 canonical D 原 receipt 使用實際時鐘唯讀驗證，daily／technical 最新均為 10/2，daily current、整體 degraded 原樣投影，資料庫及收據未改；收據 SHA=`99dcc0657dbfae2258ddf983c6bef2b93d84a6ae42ba46ef5a7ec365d2bb86c4`。此讀回只驗狀態投影，不冒充完整 UI。

G9 的自然研究 label 與 G6／Paper H5 分開：G9 使用嚴格 T−1 特徵，同日收盤只作收盤後可驗證的研究基準，沒有可交易 entry／決策資格。合法 capture 後等待 20 個官方交易日，再以後續真實 stock／TAIEX 端點及取得時鐘驗證成熟；不是 H5。週日無同日交易時，feature observation 可留存在同次執行收據，但不產生假 entry 或新自然樣本。程式及 production-shaped fixtures 可證控制流程，不能宣稱尚未發生的下一交易日 capture 或二十日成熟已成功。

最後 G9 的 `DailyPriceSourceRevisionError` 已由獨立 reviewer 逐項映射：100 筆歷史 replay skip 都指向 2014-01-02 起正式 market revision 的歷史可得性保護（`formal_market_revision.py`、`ml_daily_price_revision_gate.py`），不是 run identity 或搬移路徑錯誤。Current-observed 支線仍取得 50 筆特徵；本批沒有 input capture／fit 的直接原因是實際時鐘仍在收盤前，不能稱為該支線被歷史 guard 卡住。G6 CORE19 排除 industry-relative；5013 的另兩個缺值保留為欄位缺件，不阻斷其餘可用觀測。G9 則保存完整 20 槽與 null，訓練矩陣的既有 median imputer 處理缺值；這只是程式契約，本批沒有成熟樣本或真 fit，不能宣稱 50 列均已被模型訓練使用。

## 外部限制與自然累積

以下是來源或成熟度的具體功能邊界。G6 完整週期、G9 三組 cohort 與 Forward 受控修訂已有接受；新即時下市排除已由最後 50 檔實跑接受；最後 native／整合回歸仍列工程驗收，不移入此表。

| 條件 | 目前可用內容 | 被限制的實際用途／下一步 |
|---|---|---|
| 月營收缺完整歷史公告可得映射；較早原列僅有解碼 HTML hash，新 weekly 已另存 response-body 原件 | 2026-08 當前值及同一原件去年基期，以真實 local observed clock 驗證；PE／YoY 現況篩選已有真資料探針 | 不用於歷史可得時間重播或正式 PIT 訓練；需真實歷史公告／逐期 custody，不能猜填日期 |
| Q2 income／balance 有當次 capture clock，cash-flow basis／部分完成時鐘依批次仍受限 | 較早受控批次 79,903 值／1,975 公司，現金流 13,456 值 basis unknown；新 weekly 另 applied 83,606 值／1,976 公司且保留 raw custody，兩批不混算。income 為 YTD，balance 為 period-end | 現金流不作累計／同比／比率；current 季報不混入正式 statement factor 或 ML aggregate；這批 capture 不構成歷史公告 map |
| 官方 10/2 估值中部分公司 PE 缺失 | PE、PB、殖利率依官方實值及真 capture clock 讀取；3207 的 PB 1.55、殖利率 0 保留 | 缺 PE 不能用零、負值或舊正式 PE 充當低估值；有來源的股票仍可正常篩選 |
| P/S 沒有受治理現況來源 | 現有推薦／個股報告使用 PE、PB、殖利率；沒有現行 P/S 篩選控制因此被阻斷 | 既有估值呈現政策仍報外部來源缺件；P/S 不列已接通功能，本輪不新增內部 market-cap／TTM 推算 |
| 官方現況狀態沒有完整歷史資格 | 12:40 完成的獨立受控批次 15/15 來源成功，八股均已有具體現況證據，5371 終止日為 2026-09-03 | 3085／4527／5301 的當期停牌旗標不補造歷史生效日；新擷取仍不具歷史 PIT 資格，原自然及 partial 批次失敗另保留 |
| 10/2 現況 ML／Paper 的 H5、forward、Exit 尚未成熟 | 當下來源、研究預測與等待狀態可展示；普通持倉與 Paper 治理隔離 | 等未來真實交易日／價格／治理條件；報酬、成本與成功結果未成熟保持 null，不造 entry 或 thesis |
| 1538 H5／H10 的官方到期日缺可用 OHLC | 官方八日 OHLC 為 `--`、有量；9/17 H5 與 9/24 H10 已受控修正為 missing，結果價與報酬 null，保留原資料及自然失敗 | 不補值、不延長原 horizon；9/25、9/28 為已驗證休市，9/14 原始 custody 不明仍列來源缺件 |
| 正式 source revision 隔離 | current-restated／current-observed 研究路徑保持可追溯、非正式資格 | 不解除 formal raw／teacher／promotion 保護；新研究成功不覆寫舊正式失敗 |
| 容量與自然排程 | active D 研究根及原 200 GiB reserve 不變；10/5 01:12 UTC 的 21 tasks enabled／Ready、設定相符。新 weekly 與六持倉 Paper 快照自然成功；ML allocation-forward 因容量失敗，PIT preopen／postcutoff 各有獨立阻礙 | 01:56 UTC 原 guard 讀回：C 自然 ML 還差 3,490,758,656 bytes；D 自然 ML 來源卷通過，但正式 raw 275 GiB 還差 13,708,984,320 bytes。已封存副本無損壓縮不代表自然失敗轉成功；不沿用較早剩餘 1.15 GB 的成長預估。受限查詢 unknown 保留，只有成功的原生唯讀清冊證明設定 |


### 歷史容量補驗（10/4 UTC；目前門檻見上表）

已完成修復批次 `formal_technical_repair_receipts/20260923_run02/stage/computed.sqlite` 使用標準 NTFS `compact /C`，不使用 WOF `/EXE`、不搬移、不刪除。壓縮後完整 SHA 仍為 `aef712331735fe58e892a264ec4732003743841d11e58ca2cee2b7528e8449ab`，邏輯長度 25,685,880,832 bytes、mtime 不變、沒有 reparse point，實體占用 7,364,136,960 bytes。原先只記錄邏輯長度，**不能據此推稱釋放了兩者差額的實體容量**；10/4 00:02:53 磁碟 readback 可用 282,182,029,312 bytes，仍低於門檻。

其後對五份已完成修復的 SQLite 備份與兩份衍生 staged CSV 執行同類壓縮；每份前後 SHA、長度、mtime 均一致，收據為 `output/qa/astra_engineering_20261003/capacity_probe/completed_backup_01.json` 至 `07.json`。七份合計 `GetCompressedFileSizeW` 差額 9,826,429,852 bytes；最後 readback D 可用 292,008,308,736 bytes，距門檻仍差 3,270,692,864 bytes。尚未因此接受 heavy builder 或任何模型資格。原始失敗、回滾備份與 formal 資料內容均保留。解壓回復為逐檔 `compact /U <原路徑>`，需先有足夠空間；讀取可能增加 CPU 成本。

第二批精確列明四份 D 槽歷史研究輸入副本與六份 C 槽 QA／回滾快照，亦全部通過前後 SHA／長度／mtime 比對。收據 `additional_snapshot_01.json` 至 `10.json` 記錄逐檔路徑及回復命令；沒有碰正式 DB、原始資料或可續跑的 ML assembly。`capacity_probe/final_readback.json` 於 10/4 00:22:23 UTC 記錄 C 可用 226,977,992,704 bytes、D 可用 298,734,460,928 bytes，D 超過原門檻 3,455,459,328 bytes。**此時解除容量前置阻礙；不代表 heavy builder 已執行或原自然失敗已成功。** 後續每次建置仍須重新走原有真實容量檢查。

## 回滾清單

| 檔案／範圍 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| 本 QA 文件 | 新增 | 保留本檔，撤回其索引連結；不刪歷史證據 | 若程式保留，文件亦需保留相應說明 |
| UI／Data／ML／Scheduler owner 實作 | 修改／新增，精確清單由 owner 在修改前保存 | 從 `output/qa/astra_engineering_20261003/<owner>/before_files/` 逐檔回復前，先比較目前 SHA 與交付 SHA；不使用 reset／clean，不覆蓋後續 writer | 程式、測試與 DTO／caller 需同批回復；正式資料不隨程式回滾刪除 |
| shared state | 修改 | 先保存本輪 before bytes，僅撤回本輪 active 記錄；保留前次交接 | 不把舊 in_progress 狀態當目前 owner |
| 正式資料／Windows tasks | 現況基本面新增版本；Bank task 僅期限由 PT2H 調整 PT5H | G4 回滾備份為 `root/current_append_20261004T012326Z/before.sqlite`；依 receipt 以新受控修訂撤回本批，保留原值追溯，不可用整庫覆蓋丟失後來資料。Task 原 XML／CAS 收據保留，排程與 action 未變 | 不刪原始證據、不改安全 ACL、不做模型 promotion |

## 文檔 Coverage

Must：本 QA、PROJECT_SNAPSHOT、APPLICATION_MANUAL、system_architecture、UI_FEATURES_DOCUMENTATION，以及新增 QA 的 DOCUMENTATION_INDEX／QA README 導覽。PROJECT_NAVIGATION 依新增 adapter 實際位置更新。Roadmap Hub／Product／6M／Legacy／Target Architecture 僅檢查 scoped 一致性，不重寫歷史、不提高成熟度；若本次未改方向或目標架構，不新增平行完成宣告。root 為共享文件 writer；使用者已授權範圍內文件同步。

## 驗收與提交

尚未執行本次最終驗收、尚未建立本次 commit。以最後同版實跑紀錄補入；不得把較早 PASS 或局部測試累加成全系統完成。

### 10/4 第一輪整合檢查（尚未完成）

- 個股來源與保存未入選紀錄的聚焦 UI 測試已交付；最後同版原生測試仍待資料與程式凍結。原生輸入使用隔離複本中的真實七檔觀察清單及三筆使用者持倉；不造持倉、entry 或 thesis。
- 全範圍 mypy 第一輪檢查 759 個檔案，發現本輪三個檔案共 18 個型別錯誤，已分派原 owner 修復；此結果不是驗收通過。
- 現況估值真實擷取：TWSE 2026-10-02 共 1,082 列，實際可取得時鐘為 2026-10-04T00:47:01.782055+00:00。2330 讀回 PE 28.98、PB 10.08、殖利率 0.88%，仍為 current observation、非歷史 PIT。TPEx 同批 HTTP 520，雙市場覆蓋不完整。
- 新一批 MOPS 2026-Q2 擷取僅 TWSE 損益表／資產負債表完成，共 37,111 值；其餘端點 ConnectionReset，整批 blocked，沒有 apply。月營收獨立重試則因官方重新導向目的站憑證過期而失敗，未關閉 TLS 驗證。正評估以既有可核實 raw 重新正規化，保留原始 capture 時鐘，不能用重驗時間冒充來源取得時間。
- TPEx 官網 JavaScript 明定下市資料使用 `/www/zh-tw/company/deListed` POST；精確表單 reason=-1、response=json、offset=0、size=10 的受控呼叫於 00:47:32–00:47:57 read timeout。保留失敗回執，不能將 JS 空表或網路失敗解讀成沒有下市事件。

### G4 受控新增的 root 接受（10/4 01:27:30 UTC）

root 先獨立核對兩市場月營收 CSV／HTML 與六份季報 HTML、原 HTTP request／response URL、參數、原始 bytes SHA 及原捕獲回執，再重新解析完整候選。月營收 1,855 列、季報 79,903 值／1,975 家公司均逐列一致。重解析使用原始 bytes，不能因文字模式換行轉換改變來源 SHA。候選原觀測時間保留；monthly 與 cash-flow 原捕獲完成時鐘缺失仍為 NULL，不以本次重驗時間補填。

單次 `BEGIN IMMEDIATE` 在正式 `D:/Min/Python/Project/FA_Data/sqlite/twstock.db` 新增 81,758 列，current 表由 152,681 增至 234,439。舊 152,681 列原欄位的逐列 SHA 不變；其餘 23 張資料表（包括行情、技術指標、Evidence、正式月營收／季報／估值）逐表完整內容 SHA 均一致，SQLite quick_check 通過。所有候選、原始檔及四個正規化程式的前後 pins 相符。各新列 `aggregate_feature_eligible=false`，不寫正式 PIT 資料。

接受回執：`output/qa/astra_engineering_20261003/root/current_append_20261004T012326Z/receipt.json`，SHA `27924dcc45dcc337f80a4140e75f0977d835b3d68184e6aced3878400e645086`。完整回滾備份、before tables digests、原始及候選 pins 皆在同目錄；`apply_verified_current_fundamentals.py` 是未提交的受控 QA 程序，並非新排程入口。此接受只證資料修訂正確，報告／選股／原生 UI 消費仍另驗。

原生驗收的一致唯讀快照為 `native_final_v1/data/sqlite/twstock.db`，3,974,451,200 bytes、SHA `98edc73cb6b92db9e5e28015d57c945144d03e4edefb6ed5cd2e42475b653740`，來源 DB／WAL 的完整 SHA、大小及 mtime 前後相符。它與 G4 備份在關閉後用標準 NTFS 壓縮，共減少實體占用 3,608,502,272 bytes；兩者邏輯內容、mtime 與 SHA 均不變，逐檔回復命令見 `capacity_probe/current_root_snapshot_01.json`／`02.json`。未碰正式 DB 的壓縮屬性。

### 環境與 task 配置回讀

`root/scheduler_inventory_20261004.json` 於 01:16:28 UTC 記錄 21/21 available、Enabled／Ready，action／schedule／working directory 全符，missing／unknown 為零。仍保存自然 Evidence exit 2、Forward exit 2、calibration learning exit 1；這些是原自然 run，不用本輪受控修補覆蓋。兩次文件編輯因短暫 executor transport 中止而重試，資料庫 apply 與快照程序均正常結束；沒有把通訊事件當作資料成功或遺失。

06:31:11 UTC 另以 Windows COM 唯讀重查 raw、calibration learning、BankTaiwan 三項 task，仍皆 enabled／Ready，trigger 為 05:05／05:45／05:50；原 calibration learning 的 LastTaskResult 仍為 1。前兩者未指定 ExecutionTimeLimit／RestartOnFailure（使用既有預設 72 小時、零自動重試），BankTaiwan 明定兩小時。精確 XML settings／triggers／actions 見 `root/g9_task_dependency_readback_20261004T0632.json`；檔名 0632 不是捕獲時間，應以 receipt 內 UTC 時鐘為準。此讀回確認 G9 必須自行等待具名 G6 run，不能依賴不存在的 task 自動重試。


### 官方估值 canonical 接受（10/4 01:59 UTC）

已凍結的 collector／CLI 實際寫入 canonical `D:/Min/Python/Project/FA_Data/output/current_valuation`，run `astra-valuation-20261004T015930Z`，exit 0、stderr 為空。TWSE 1,082／TPEx 887 個唯一股票，資料日均 10/2；body 完成時鐘分別 10/4 01:59:31.645582Z／01:59:34.708633Z。TPEx 官網 HTTP 520 原始回應與失敗 receipt 保留，再沿官方 Swagger 公布的 `tpex_mainboard_peratio_analysis` OpenAPI 成功，不關閉 TLS。terminal receipt SHA `0f223d49677f351122cb334049f795479e06e1d140df13f8a78113e83c651dd6`；root invocation、stdout 真實 bytes SHA、程式前後 pins 及 provider readback 見 `root/canonical_valuation_20261004/`。

root 獨立讀回 1477 PE 13.11／PB 3.44／殖利率 7.81%，2382 為 14.47／5.25／4.70%，6488 為 57.77／5.88／0.65%；3207 官方 PE 缺值，僅有 PB 1.55 與殖利率 0%，不補零 PE 或猜測原因。原生 seed 為 canonical 檔案的逐檔相同副本，尚未因此宣稱 UI 已驗收。historical/formal PIT flags 仍 false。

### 整合與自然失敗再查（10/4，進行中）

root 獨立 G4／provider 回歸 45 passed，report／source recovery／ML scope 27 passed。第三輪全範圍 mypy 已檢查 760 個檔案、零錯誤；這是該次程式快照的結果，仍需最後凍結版必跑檢查。

自然 Forward run `20261003T124002555383Z` 的唯一 calendar mismatch 是 1538、9/10 事件、H5：官方預定 9/17，symbol 非空收盤價序列第 5 個點卻在 10/2。獨立 raw／CSV／DB 查核確認 9/15–18、9/22–24、9/29 共八日的官方 MI_INDEX OHLC 原值為 `--`，同列仍有正成交股數、筆數與金額；例如 9/17 為 790 股、8 筆、6,271 元。因此不能宣稱零成交或停牌，也不能補價、跳過 mismatch 或延長 H5 冒充原合約成功。9/25、9/28 為已驗證官方休市日；9/14 尚無同等 raw custody，保持未驗。完整 12 個原件／CSV／DB pins 見 `1538_forward_gap_audit/1538_forward_gap_evidence.json`（SHA `0a91602c0a7b82589975236e0e78a25dde66e5f4c1a4d6d03c01e973fa749b53`）。自然 calibration learning attempt `attempt-9923f328161e09638409cf4e` 因 `source_preflight_failed:DailyPriceSourceRevisionError` 保持失敗；其 early return 同時略過獨立前瞻累積是 G9 工程缺口，另行修復，不以缺乏成熟模型概括結案。


### 既有 operational prompts 磁碟回讀（10/4 02:08 UTC）

僅對兩個已授權的既有本機 operational automation 追加逐次查核規則：`baldr-scheduled-evidence-morning-report` 與 `paper`。逐檔 compare-and-swap、原文備份與 TOML 全欄比對後原子替換，非 prompt 欄位全不變，維持 ACTIVE、原 05:30／06:20 排程及原 target thread。收據 `root/operational_prompt_update/applied_receipt.json`；新 SHA 分別 `f9a593ddf62111d01a6338e416203aa10aa47c03a8828a183b130274f83d094b`、`230170537787a32b72ab56d2aeb7cdb2d49ec0df8fdff696cac267eacf648ea8`。只證明設定磁碟回讀成功，未宣稱 app 記憶體快取已重新載入。未新增或恢復已取消提醒。

### 官方三個 child 的同批實測（10/4 02:25–02:27 UTC）

第二次受控 wrapper run `20261004T022506519277Z-2e4864fcbde2` 的不可變 terminal SHA 為 `9f8d1576b640f60a41cbf264310963a27a804c54cbf0c510ffaa5a91dda606e1`。三個 child 的 same-run receipt 都通過獨立驗證：historical events 為 failed／exit 2；current status 為 partial_failure／exit 2；current valuation 為 captured／exit 0。wrapper 整體 exit 1 保留失敗，不把下游可用估值改稱整批成功。逐 child 原始輸出、真實 bytes SHA 及程式前後 pins 見 `root/canonical_official_bundle_v2_20261004/`。

current status snapshot SHA `faf0ae611914015b21d397098bf41abde53ec17c1e2f80e9196ce9ceb38754d1`，reader 可查 2,617 個代號；資料保留 current-only／非 PIT。估值 terminal SHA `1e89be17d7c6445bfe538a48de3dec17138599f294bc010c126dc6dcad1806ce`，TWSE／TPEx 皆為 10/2，capture 時鐘為本次真實 10/4。第一批暴露 CLI 少傳 schema 與 historical-PIT flag 的工程錯誤，已修 CLI 並補實際 main→bundle validator 測試；原失敗 terminal 留存。第二批沒有使用新 receipt 覆寫第一批驗收。

第二批 15 個 current sources 中 12 個成功。失敗精確為 TPEx emerging roster／suspension history 的 HTTP 520，以及 terminated-listing POST 的 read timeout；OTC roster 此次成功讀到 892 列，不能沿用第一批該端點失敗的描述。root 另保存本批八股完整 evidence 於 `root/canonical_official_bundle_v2_20261004/eight_status_exact_snapshot.json`。

| 股票 | 本批可證事實 | 對功能的影響與邊界 |
|---|---|---|
| 2323 中環 | 9/10 臺證上一字第1150018271號；10/1–10/8 停止舊股買賣，10/12 新股上市 | 10/2 缺報價有官方停交易原因；保留 listed 身分，不捏造當日行情 |
| 2601 益航 | 9/9 臺證上一字第1150018275號；9/23–10/3 停止舊股買賣，10/5 新股上市 | 10/2 屬停交易區間；10/4 不延長公告區間或宣稱已發生新股成交 |
| 2867 三商壽 | TWSE terminated-listing 官方表明示 9/1 終止上市 | 現況標為 delisted；歷史是否可交易仍須當時證據，不反填歷史資格 |
| 3085 新零售 | TPEx cmode 1151002 明示 `SuspensionOfTrading=Ｙ` | 可呈現來源日停交易；起迄、公告時鐘未知，不猜填 |
| 4527 方土霖 | 同上，明確同股列 | 同上；保留 listed 與來源日交易限制的區別 |
| 5301 寶得利 | 同上，明確同股列 | 同上，不以缺報價判為下市 |
| 5371 中光電 | 8/4 證櫃監字第11500050581號明示自 8/24 停止買賣；12:14 新批次 TPEx 終止上櫃表明示 115-09-03 | 以新批次官方原件確認現況 delisted；原始 bytes SHA `86b5cf847348056b6220d293b6a569e897939b57b6c3fc9ea5b5d1b6293036a2`。這是新現況證據，不能回填歷史可得時間 |
| 8183 精星 | 9/3 證櫃監字第11500054131號，9/23 停交易、10/1 終止上櫃 | 現況 delisted 且保留原公告；不補 10/2 行情 |

兩份 TWSE 公文及兩份 TPEx 公文列入正式 current collector 的來源 URL 清單；每次重新抓取、解析原文、保留 hash／實際取得時鐘，沒有將股票結論寫死。來源不完整仍顯示 partial failure。root 凍結版官方 status／bundle／valuation 回歸為 **43 passed**，深層 Windows 路徑測試也通過；唯一 warning 是 pytest cache 無寫入權限，未修改 ACL。

### 新暴露的整合錯誤與容量（仍待新批驗收）

第一輪十檔 current research cycle `raw-pit-20261004T021755238344Z-38316-c7f8878f34b844b787e69ad7ac87f9e4` 已完成一致 snapshot，隨後因 `revision_dependencies_verified_at` 晚於 fit freeze 而失敗。外層 raw core 的 exit 0 不代表此 nested cycle 成功；原 snapshot、回執與 blocker 保留。修正需使用驗證完成後的真實時鐘，不能回填來源時間；B feature mapping／registry／數值語意也納入重用判斷，不能只比行情 hash。

G5 真實兩股探針發現 current TWD 與 formal 原始千元 baseline 混用的工程風險。2026-08 同份官方 MOPS raw 已有去年同月比較值，可用相同已驗單位轉換並綁定當期 raw／本地觀測時間；不回填 2025 PIT。1477 當期／去年同期為 3,554,003／3,745,640 千元，2382 為 423,970,932／152,807,846 千元。最終驗收須檢查實際 YoY 數值與 lineage，不能只看 scope 標籤。

另七份已關閉的 9/28 舊 UI QA 快照（精確 m5–m11，非原始資料）完成標準 NTFS 壓縮。每份實體占用由 3,827,728,384 降為 2,101,735,424 bytes，共減少 12,081,950,720 bytes；full SHA、邏輯大小及 mtime 不變，見 `capacity_probe/closed_ui_snapshot_01.json` 至 `07.json`。未碰 WP5、正式 DB 或安全 reserve；後續 producer 仍須重新通過當下容量檢查。

### 第三批官方來源與第二批 research cycle（10/4 03:08 UTC）

第三批官方 wrapper `20261004T030456727648Z-3584d21ccc1b` 的 terminal SHA 為 `1c695222836914e203362602da61d39d82207866ae971a2da8bdcb2629be9a7a`，程式前後 pins 一致。current status 為 14/15 成功、3,142 個代號，唯一失敗是 TPEx terminated-listing 的 RemoteDisconnected；本批 snapshot SHA `4b24edce0f13aa7a689d8837080ca0d139e5f84508e372f1ca9953cc5bf60f12`。新增辨識 TWSE 原始欄位「暫停交易日期」後，原件 383 列均能解析起日；本批 030089 起日為 6/10、恢復日為 6/11。舊快照仍保持原 null，不回寫舊證據。修補起日欄名後，root 另跑 official status／valuation／wrapper 三套獨立回歸 **44 passed**，收據 `root/official_status_independent_v3/`；前述 43 passed 屬較早版本。

本批 valuation terminal SHA `921ed220efbb9a7d648f51d9b3ed258e6e9d299c3e86cec345ce50c47ed44dc7`，兩市場均 captured／exit 0、行情日 10/2。TPEx 官網 connection failure 保留，官方 OpenAPI 備援成功。historical child 對 2014 sprcHis 四次嘗試失敗，保留 10/3 last-known-good 正式發布。wrapper 整體仍 exit 1，不把 current 可用解釋成歷史完成。完整同批 receipts 見 `root/canonical_official_bundle_v3_20261004/`。

第二次 research cycle `raw-pit-20261004T024439704426Z-38664-43e029d60b9d416481913d175476959d` 在 B input 失敗：controller 假定英文 OHLC feature IDs，但真實 adapter 使用中文 registry；另 TPEx 3207 原始數值完整，舊 adapter 卻因欄名空白／別名未辨識而產生七欄 missing。修正共用 feature ID 定義，依市場辨識官方欄名；TPEx 金額只接受明示「元」，歧義或未知單位仍拒絕。舊 B shard、registry 與 cycle terminal SHA `6704cca6e983659a31b4592d2a0ee083c940e1691eb22038147ae2fc6015bdc8` 不改寫。

root 在修補版獨立跑 context／bounded bridge／raw runner／B adapter／Direct adapter／cycle 六套回歸：**102 passed、1 skipped**。skip 是 Windows 無建立 symlink 權限的既有案例，hardlink 拒絕案例通過；未修改安全 ACL。收據 `root/cycle_context_adapter_independent_v4/`。這些測試不代替新批真實 cycle。此前過深的 pytest basetemp 造成六個 MAX_PATH 測試環境失敗，原 log 保留；短且獨立 basetemp 重跑通過，正式 canonical 路徑仍須真實驗證。

G5 comparator 凍結版另由 root 獨立驗證 **62 passed**（`root/g5_comparator_independent_v1/`）。plan-only 候選 3,703 列含 1,855 當期與 1,848 同報表去年同期比較列；候選比較列使用 03:11:41.375211Z 的真實驗證時鐘，正式新增時另記 append 前實際時鐘，不能沿用既有當期列較早的觀測時鐘。尚未因此宣稱正式追加、實際推薦數值或 UI 已完成。

### G5 正式追加與獨立唯讀接受（10/4 03:44 UTC）

03:27–03:30 的 plan-only 完整核對 24 張表、schema、回滾備份與原始候選；plan SHA 為 `2478b1a0e96aa585d2a7123ae29298d99139f02036df617e8935f1034a2ac861`。受控 apply run `20261004T033505Z-6452defbe83e` 已提交 1,848 筆比較列，實際新增觀測時鐘為 **2026-10-04T03:36:45.887790+00:00**；原 1,855 筆當期值及其較早時鐘不變。current 表現為 **236,287** 列。

apply 程序在提交後因唯讀連線關閉過早而回傳 exit 1；保留原 `post_commit_failure_receipt.json` 的 committed=true／rolled_back=false，不重跑寫入、不改原失敗收據。root 另用獨立唯讀程式逐列重解析、核對新列與單位／basis／parent version，驗證原 234,439 列全欄 SHA、其餘 23 張表及 schema 均不變，quick_check 通過；前後 DB／WAL 與備份 pins 穩定。接受收據為 `root/g5_append_independent_readback_v1/receipt.json`，SHA `87f99216450c3fc45026cb2aac448506725a4f3d5080d56678e4b2addc487c6a`。原 apply 失敗與後續資料接受是兩個不同事實。

1477 同期 TWD 比較為 3,554,003,000／3,745,640,000，Decimal YoY 為 -5.116268514859943828024049295%；2382 為 423,970,932,000／152,807,846,000，YoY 為 177.4536406985280062124558709%。七筆原件缺少可用同期值仍保留缺值，不能借用單位未驗的正式 baseline。新增比較列為 current observation，非 2025 歷史 PIT；無任何正式資格提升。

最後原生驗收改用 `native_final_v2`，一致快照 3,976,314,880 bytes、SHA `505964dc2125e0f79d59e190f9a6379dbaa2cf1b36026c8359df8f4a4790640b`，包含 236,287 筆 current 值。沿用逐檔核對的真實七股 watchlist／三筆持倉與唯讀候選資料；官方 seed 24 檔釘住第三批 wrapper 的實際 bytes，原絕對 raw 路徑不改寫。`native_final_v1` 保留，沒有用新版檔案覆蓋前一版證據。此時尚未執行最終原生 UI。

### G9 無模型時的自然累積根因（仍在實作）

實際 shadow active pointer 位於 `D:/Min/Python/Project/FA_Data_Shadow/recommendation_learning/`，狀態為 rule_only，沒有 candidate／model。僅將既有 active-model capture 移到失敗分支仍會形成永遠沒有樣本的死路，因此新增明確 current-observed input capture：保存實際當日輸入、前日以前特徵、同日股票／TAIEX 收盤原值與不可變來源，不生成模型概率。未來由獨立自然結果 lane 驗證真實交易日、原 entry 與後續終點，再供自然樣本專用 shadow fit；歷史 revision 失敗仍保留。10/4 是非交易日，不能把 10/2 收盤改稱 10/4 entry。工程接線完成前不將此項標為僅待自然成熟。

### 10/4 04:08 UTC 整合進度（尚非最終接受）

第三次 G6 cycle `raw-pit-20261004T034826267316Z-28984-9c2b1ebf9dcf411a8a741c6c50e83e3a` 通過十股 B 投影、同版來源 context 及快照，於 raw_publication 的 `core_long_history/manifest.json` 失敗。真實路径 261 字元，年度 shard 266 字元；Windows Python 的 stat／resolve 回 WinError 3。terminal SHA `f39daa40a2bd7f123a6a85778d6634e7b981c34d72d975262043d982f1d6b754`、23 項程式 pins 前後一致。原始外層仍為 blocked_source_revision／exit 0，nested cycle failed；兩者分開記錄，須修工程路徑並重新跑新批，不能解釋成等候樣本。

root 在最新 UI／持倉程式上完成 Workbench **85 passed**、update validator **25 passed／0 failed／4 skipped**，另八套研究報告／來源／UI／持倉整合回歸 **97 passed**。收據依序在 `root/ui_workbench_after_g5_monitor_v1/`、`root/ui_validator_after_g5_monitor_v1/`、`root/research_ui_portfolio_independent_v4/`。validator 的四項 skip 為既有接口測試未下載／合併，不代替真實來源驗證。整合中 mypy 760 檔有四個新 G9 型別／尚未定義 helper 錯誤，已交原 owner；尚未最終通過。

native_v2 第一次 preflight 因參考 manifest 缺少 `user_entries_fabricated=false` 宣告失敗，UI 未啟動。root 再將十個 canonical source 與隔離副本逐檔 SHA／大小核對一致，保存原 manifest 後補正宣告；修正收據 `native_final_v2/reference_manifest_declaration_correction.json`。第二次 preflight 通過，仍只代表輸入就緒、UI 未啟動。父層 log 顯示程序未因環境連線中斷，沒有重複啟動受控流程。

### 10/4 04:32 UTC 獨立審查補件（進行中）

手動月營收 CLI 原本可繞過新正規化路徑，已改為先核對 CSV／原 HTML／單位並呼叫與自然週排程相同的 materializer。root 的 CLI／materializer／snapshot／harvester 四套回歸 **23 passed**，收據 `root/manual_monthly_verified_cli_independent_v1/`；未重新追加已完成的正式資料。保留 200 GiB reserve、備份與 writer lock，apply 不明例外須獨立讀回，不宣稱自動 rollback。CLI 證據檔與來源路徑碰撞保護仍在補驗。

G6 改用保留完整 run ID 的短 hash 儲存目錄，並以 create-only 保存 child 的 stdout／stderr 真實 bytes 與 SHA；root 的 Windows 實際深度路徑／child 失敗證據回歸 **22 passed**，收據 `root/cycle_path_and_child_evidence_independent_v7/`。第四次實際 cycle 已啟動，尚待完成及 registry／重用驗收。相同輸入合法產生 `skipped_same_inputs`，G9 必須驗證新 raw／reuse terminal 與原 completed terminal 的兩層身分，不可把沿用模型改稱新模型或直接借用 latest。

G5 獨立 reviewer 找到兩個待修問題：分析 body 失敗時，空 invocation ID 可能讓 lineage event 二次例外遮蔽原錯誤；同報表比較值缺失時，舊年度已觀測值可能被誤當同比基準。兩者均交原 owner 補拒絕條件與實際負例。原生驗收仍等候這些 production 檔案凍結，沒有把單元測試當成四用途最終接受。

第四次 G6 `raw-pit-20261004T041952605115Z-18352-2c60ad291529453c86dbc4c7f61db4f3` 於 04:31:09 UTC 結束，23 項程式 pins 不變。annual raw 與 outcome child 均 exit 0，controller 卻以 `outcome artifact manifest exceeds the metadata byte limit` 拒絕結果，整體 nested cycle 仍 failed。terminal SHA `151d527a9ad3dab508201190054e759c0c5f8544e7db106ab4a4a653451b4ada`；本次失敗歸為工程讀取契約問題，須依實際 artifact 結構修復，不把保護門檻任意取消或把外層 exit 0 當成功。

`root/quant_guard_integration_v4/` 的 Decimal／浮點邊界與 look-ahead 靜態守門檢查通過；此為當次程式快照的檢查，G9 最後接線仍需重驗。早期對 5371 的查核僅明示 8/24 停買賣與股份轉換日，當時沒有終止上櫃正面原件；外站重取 HTTP 403 保留於原紀錄。12:14 的新官方 JSON 批次才補齊終止日，不能將新證據改標為早期已取得。

### G5 修復接受與 G3 跨入口補驗（10/4 04:54 UTC）

root 的五套 G5／手動 CLI 回歸 **74 passed**，收據 `root/g5_exact_comparator_failure_cli_independent_v2/`；另一位非作者 reviewer 的九個案例亦通過。FAILED body 不再組裝空 invocation lineage；最新當期加舊年度觀測、但缺同報表比較列時，投影與 evaluator 均不產生 YoY。同比要求 parent period、股票、來源、市場、原件 hash、捕獲時鐘、單位與期間基礎一致。手動 CLI 在任何 plan／write 前拒絕 evidence 目的地與輸入 CSV、DB／sidecar 或 raw HTML custody tree 碰撞；測試核對原 bytes 不變。

G3 獨立審查發現報告已有日期 gate，但 `PortfolioConditionMonitor` 的 Portfolio／Alerts caller 仍可能用無日期的 cached price 判斷停損與假設有效。範例為價格 55、成本 50、停損 5%，沒有行情日仍回 valid。此為同一持倉健康工程缺口，正在把唯讀行情日期與既有 MarketSessionCadence proof 接至 monitor、持倉 UI、alerts、使用者持倉研究及報告 caller；不能只改標籤或把合法週末行情全部降級。

G6 確認另有 sidecar 對同一 39,245,761-byte outcome manifest 使用 16 MiB 小型 metadata 上限。修復採用既有完整 artifact loader 已驗證的 context proof，controller 只接 exact SHA 的小型 producer summary，完整 row／array／fold 校驗仍由既有 loader 執行；兩個一般 metadata 上限不任意提高。尚待新實跑接受。

三份已結束 failed cycle 的 SQLite 副本完成標準 NTFS 壓縮，實體占用合計減少 5,489,823,744 bytes；內容 SHA、長度、mtime、terminal 與 snapshot receipts 全不變。逐檔證據及回復命令在 `capacity_probe/closed_failed_cycle_snapshot_01.json` 至 `03.json`；04:37:16 UTC 的 C 可用空間為 227,092,447,232 bytes。未刪原始資料、未降低 200 GiB reserve。

原生 runner 的靜態覆核另修正 125% 縮放時把實體像素錯當邏輯視窗大小的驗收條件，並補快速重複點擊防重的真實控制項操作。這些仍是 QA 準備，不據此宣稱原生畫面通過。


### G3 共用行情證據與 G9 隔離 fitter 的 root 回歸（10/4 05:15–05:16 UTC）

持倉監控、PortfolioService、Alert、PortfolioView、個股報告及使用者宣告研究已傳遞行情日期、來源與 SHA、官方日曆預期日期及 freshness。無日期／過期快取不再使價格 thesis valid 或觸發停損停利；合法週末仍可使用 10/2 行情，價格／成本的 Decimal 損益觀察保留。root 發現缺 InvalidOperation import 的錯值分支後，由原 owner 補正並加入官方 `--` 等負例。root 在短 repo basetemp 獨立跑九個相關 suite，124 passed；收據 `root/g3_final_independent_v1/receipt.json`，stdout SHA `9f79ce105ae5bd19eec22e677fb1ea70e350bb456f40e882e1479abd052887fb`。owner 較早三項失敗保留，root 同版短路徑重跑全過；pytest cache ACL warning 未改安全 ACL。最後原生 UI 仍待驗。

root 獨立執行 `test_current_observed_natural_research_fit.py`，6 passed、1 skipped（Windows 無 symlink 建立權限）；`root/g9_natural_fit_independent_v1/receipt.json` 的 stdout SHA `1435ddd9fc6de9f64bc80f8562cb86293fd405d721bf3791cf2cfd9a125430b4`。成熟合成 fixture 使用真實 DailyRecommendationLearningRunner 建立隔離候選與 verified lineage，active pointer 不建立；receipt verifier 邊界由 fixture 代入，此測試不是整條真實自然資料鏈的驗收。真實捕獲、outcome 及 runner 整合另驗，不宣稱自然模型已成熟。


### G6 第五次受控週期未通過（10/4 05:01–05:21 UTC）

v5 raw run `raw-pit-20261004T050106093970Z-22552-75e1c75e6c44430d8d45e53442b62cbe` 的外層仍為 `blocked_source_revision`，wrapper exit 0 不構成 nested 成功。A 年度 raw、outcome 均已完成，但 fit child 回 `CurrentRestatedResearchError: raw annual shard row count exceeds its bound`，`training_started=false`、`training_performed=false`，cycle terminal 為 failed。23 個程式 pins 前後一致；terminal SHA `7b31a0e1f1a72086a2037669273736d77eaf18591450ad81a80c681757efb20f`，原收據與 child bytes 保留於 `root/current_stock_cycle_controlled_v5_20261004/` 及 `output/ml_research/current_stock_cycles/2026-10-02/891a44f4e8d12c51157fbf9f1ca56111/`。正在核對完整年度原件與 bounded selected-cohort reader 的契約，不能提高上限求通過。

本次實測 snapshot 3,976,314,880 bytes、其餘持久成長 1,157,648,038 bytes；完成時 C 剩餘 221,809,831,936 bytes，低於下一次新輸入 cycle 所需 223,165,721,608 bytes。新市場日不能使用同輸入 reuse；尚未具可持續累積容量，不以舊容量 PASS 結案。正在盤點已關閉 QA 副本的可逆無損壓縮空間，未降低 200 GiB reserve，未刪原件或收據。

G5 實際 probe v2 使用 isolated final-v2 snapshot 與官方估值 seed，當次執行完成但 source fact assertion 未讀到 1477 的唯一 current PE；該 probe 失敗尚未接受。原錯誤為 `1477 has no unique current PE source fact`，正在區分 QA root／日曆接線與 production provider 問題。


### G5 probe v2 的確切拒絕原因（10/4，原失敗保留）

獨立 reviewer 確認正式 Main 與 native harness 均使用 TWStockConfig 預設 `use_sqlite=True`，經 HistoricalRecommendationMarketFrameProvider 的 `mode=ro`／query_only 路徑。只有忽略的 G5 probe 將它改成 False，改讀 CSV 前 500,000 列：1477／2382 各自最近日期為 2015-05-08。PE provider 因行情日不是最近已完成交易日 2026-10-02 而正確拒絕，不能將此歸為正式 UI 無法讀 PE。依原 invocation captured_at 直接讀相同 provider、指定真實 10/2 行情日，可得到 1477 PE 13.11／2382 PE 14.47，calendar 與官方 raw/hash/時鐘均通過。QA helper 改回正式唯讀 SQLite composition 並在 assertion 前保存實際 lineage；仍需新一批完整執行及 persisted readback，舊 v2 失敗不覆寫。


### 下一輪驗收的容量回讀（10/4 05:37:32 UTC）

對已關閉的 native_final_v2 SQLite snapshot 與失敗 v5 source snapshot 執行標準 NTFS compact，先以 exclusive read handle確認無開啟連線，拒 reparse ancestry／非空 WAL／journal，再核前後完整 SHA、長度、mtime 及原 snapshot／terminal receipts。兩份各由 3,976,314,880 實體 bytes 降為 2,146,111,488，合計實測釋放 3,660,406,784 bytes；C 剩餘 225,461,125,120 bytes，暫足下一次新 full-cycle 預檢。收據 `capacity_probe/closed_final_input_01.json`、`02.json` 保留原樣及逐檔 compact /U 回復參數。沒有刪除、搬移或修改正式 DB／原始資料；長期累積的容量限制仍未消失。


### 最終回歸揭露的有限修正（10/4 05:40 UTC 起）

G5 probe v3 已走正式唯讀 SQLite 行情，卻在 production `execute._current_fundamental_lineage_event` 因 `fundamental_input_diagnostics is malformed or unbounded` 拋例外，尚未形成可保存的 execution。root 收據 `root/g5_actual_sqlite_probe_v3/receipt.json` 保存當次 argv／時鐘及 stderr SHA `9794ddac51c0d5cc8696e500741784c7ba68a506342bc8ceaae5e1ecd2d34189`。原 owner 正核對每股多期來源診斷與 event 配額契約；不能刪診斷或只提高上限通關。

另獨立核對發現：自然 PE provider 以 13:30 完成市場日判斷，而 Portfolio／Alert／Exit 沿既定 04:30 Pacific 專案發布截止。在正式收盤至專案截止間，當日 DB 行仍缺獨立發布資格，不能先被 natural Advice 當同等 current。修正維持既有發布截止，在自然行情輸入／技術計算前以同一 invocation clock 及已驗證日曆選定 expected session；market cutoff 與使用者明示歷史 as_of 分開，不能誤切基本面 PIT 路徑。

G9 獨立 reviewer 找到三項需要完成的自動累積邊界：entry snapshot 必須在該日 regular close 後觀測，14:30 的 maturity availability 約定不能冒充 13:30 交易收盤；同日重試的相同語義 capture 須保留全部 receipts 並安全去重，真正 feature／entry／label／cost 衝突仍拒絕；只有舊 rule_only active pointer 而沒有 cost metadata 時，正式 lane 保持 fail closed，不能連帶跳過隔離且具明確 cost scenario 的真實 capture。以上仍屬 G5／G6／G9 原工程缺口範圍，未提高任何正式資格或宣稱自然成熟。

### 真實資料定向回讀與獨立審查（10/4 05:55–06:05 UTC）

G5 owner 以 final-v2 唯讀 SQLite 和本次真實 aware clock 查 1477／2382：兩股當期月營收皆 ready／2026-08；各五筆 revenue 修訂列、兩個月份及一筆同報表比較列，產生九條 exact-str 診斷。原錯誤是數量契約，並非診斷型別錯；七／八月未驗證修訂的保留、被阻期間及被後版取代資訊都不能刪除。來源查詢列數將隨同次 context 傳遞，作為 event 診斷配額依據，整體 16 MiB 上限不變。

G6 v5 的 exact outcome loader 已完整讀回；其後唯讀 QA 曾誤把全部八個 benchmark 欄位當 close，因而被 reader 正確拒絕。改用正式程式的兩個 close ID 後，13 年 raw 全列串流驗證通過：actual／declared 308,194 列、3,111 個 TAIEX 日期、解壓總量 2,034,536,395 bytes、最大壓縮分片 9,802,861 bytes、最大 JSONL 列 23,259 bytes。精確回執 `root/g6_v5_raw_source_reader_readback_20261004.json` SHA `719b3a6b674a9bf0a579fa13e0184db7cb68159ef86b4e93f965f1a565e5fd0d`，仍綁原 failed terminal，不把舊週期改為 completed。工程讀取界線分開為全 raw 1,000,000 列、TAIEX 留存 100,000 列、壓縮分片 32 MiB、單列 1 MiB、全資料解壓 2 GiB；manifest、各年宣告與實讀總數必須全符。這是獨立資源限制，不引用 outcome observation 的上限冒充年度 raw 契約。

root G9 四套回歸於 05:55:57–05:57:12 為 60 passed、1 Windows symlink 權限 skip，stdout SHA `cd7e3b4091a156e4cb1821878590cc3cb7c7a469ad5a10ce963766d009223a9d`（`root/g9_final_three_repairs_independent_v2/`）。隨後 production-shaped 獨立審查仍發現兩項阻斷：語義去重保留了捕獲時鐘衍生 hash／receipt path，實際重試仍衝突；entry calendar proof 只驗自帶欄位與雜湊，未重驗官方 raw／cache。已退回 owner 修補，這 60 項通過不能代表完整 G9 接受。另獨立來源／UI／provider 九套回歸 114 passed，尚未代替同版原生視窗驗證。

### G6 第六次完整執行（10/4 06:12:12–06:39:28 UTC）

root 啟動新 raw run `raw-pit-20261004T061213357045Z-27744-50e0f86fee974fac95cd013f7d9bf29c`，23 個相關程式前後 SHA 完全相同。原始 B、raw publication 與 outcome artifact 均完成，後者含 30,861 個 observations、3,111 個完整日曆日期與 40 folds。fit child return 2：`current-restated fit requires the verified complete 905-session calendar`，其實際 receipt 為 `training_started=true`、`training_performed=true`，但尚無已發布模型／registry。這與第五次尚未開始訓練的失敗不同。

本次 terminal 為 `output/ml_research/current_stock_cycles/2026-10-02/5c7cd442018be2afb7ffcd61c6a44f06/terminal_receipt.json`，SHA `3e35e5d7116d900d96f68f0c1426e9e38146559b8617d931644598fc0c41f2a9`。root 控制回執在 `root/current_stock_cycle_controlled_v6_20261004/`。外層 raw 的 exit 0／`blocked_source_revision` 不能覆蓋此 failed child；必須另以新 run 重驗。根因是研究模型 qualification 的固定 905 總日數與完整來源日曆的契約不一致，正以版本化 qualification 修補；125 個成熟 train dates、63 test dates、60 purge、5 embargo、至少四 fold 及完整 hash／日曆索引驗證均須保留。

### G9 最後獨立覆核摘要（10/4）

Data reviewer 按 runner `f1574a2641628e692ada22453fb7a0ffb8d9750dea2ef93141b3ede678b6f8bf`、evidence `3879c90ade15fb5ad0a03a90935404262087da418ea3793247a4d75476c25148`、capture tests `5044571ff561de21ed565080496f9d2f78e6a436090318a4624cd1571f22b951` 重審：65 passed／1 Windows symlink 權限 skip；另外四項 production-shaped／root 分離重現通過。同一來源、不同 invocation clock 的 feature row 只生成一份語義樣本，全部 capture／outcome receipt refs 仍保留；改 feature 值、source table hash 或成本即拒絕。偽造 calendar path／raw cache 無法產生 entry pin；官方 raw／envelope 的 custody 仍依既有捕獲 producer，不宣稱 TWSE 提供遠端數位簽章。

此 reviewer 沒有另存測試程序的精確起訖 UTC 或 raw stdout／stderr；故僅採其明確標示的 review summary，不冒充 root 完整執行收據。摘要為 `audit_data_g9_independent_20261004_0654/summary.json`，SHA `1ba6b02d27338ccce902fef339a526e097e6f2fc76dcb1636490d9b4608b1765`；完整凍結版的 root 最終回歸及真實 15 股捕獲仍另驗。

### 新一輪容量準備（10/4 06:44–06:46 UTC）

root 對已 failed／關閉的 v6 snapshot、9/28 已完成的 `formal_source_snapshot_v2` QA 副本，以及本輪兩份 native candidate 副本做標準 NTFS 壓縮。逐檔先核原始 snapshot receipt、exclusive read、無 reparse／非空 WAL／journal，再核完整 SHA／長度／mtime／原 receipts 不變；沒有刪除、搬移、重新計算內容或更動正式資料。實測實體節省分別 1,830,203,392、1,725,992,960、456,531,968、456,531,968 bytes；最後 C 可用 224,043,716,608 bytes。逐檔收據及反向 `compact /U` 參數見 `capacity_probe/v6_closed_snapshot_01.json`、`02.json`、`closed_native_candidate_01.json`、`02.json`。此餘額僅暫足下一新週期，不表示長期累積容量已解決。

### 新版日曆資格、容量失敗與實際排程設定（10/4 07:13–07:18 UTC）

G6 qualification v2 綁定完整 verified Direct 日曆的實際筆數、SHA 與 manifest，最低歷史仍為 905 sessions；v1 仍只接受原本 905 sessions。125 mature train／63 test／60 purge／5 embargo／至少四個 folds、標籤終點早於測試期等保護不變，並於 fit 前驗完整日曆。root 獨立測試 37 passed，stdout SHA `e95559024119b2662f228d7f8c4c536544152f22f2f84670ad3d2b6aa721c1d0`（`root/g6_calendar_root_review_v1/receipt.json`）。

v7 受控週期 07:13:53–07:17:56 UTC，raw run `raw-pit-20261004T071354500075Z-44336-33470989325d487a8c19bf556df536d8`，23 個程式 pins 不變。B 完成後，annual raw producer 在 `raw_before_output` 被容量保護阻擋：free 219,042,201,600 bytes、required 219,043,332,096 bytes；尚未進入模型 fit。terminal `output/ml_research/current_stock_cycles/2026-10-02/c7c5bacbf29493df6bcc25f684f8f5a4/terminal_receipt.json` SHA `35ced633b371ef41a2dbce90ac47787fa50b27ce3d21a9ef6b3dcb6c07a8f35f`，完整 root 收據 `root/current_stock_cycle_controlled_v7_20261004/`。沒有將 wrapper exit 0 或舊批次結果冒充成功；保留此失敗並處理持續容量問題。

G9 日期契約拆分為 shared cutoff 下的 G6 source session 與嚴格 T−1 feature session。週一 04:29 Pacific 來源／特徵均為前一交易日；04:31 後來源為當日、特徵仍為前一交易日。等待器釘選同台北決策日的一個 raw run，核 exact terminal path／SHA／run／source date；跨日、pointer 改變、非允許失敗或逾時均阻擋。pipeline 總預算 10,800 秒，先保留 child 3,600 秒與 terminal flush 300 秒；raw root 與 Shadow recommendation／learning root 分開記錄。

root 實際 Windows 檔案回歸：Scheduler／Bank 96 passed、4 skipped，07:15:45–07:15:59 UTC，stdout SHA `d505f5204791baf59f11ee346ec8f4f95d56b51d368531e72df0ca7d4796c879`；G9 capture／日期／自然 fitter／outcome 68 passed、1 skipped，stdout SHA `44a155eb4bc097a05048493fab1ef954878938ea0593925bca17ab7f5344ed22`。收據分別為 `root/g9_scheduler_root_review_v1/receipt.json` 與 `root/g9_final_source_date_root_v1/receipt.json`。較早 sandbox 三項 stdout artifact 失敗未以 mock 掩蓋，而在已授權環境重跑原案例通過。後續只新增缺快取時網路呼叫數為零的測試哨兵，最終凍結版另統一回歸。

07:16:35 UTC 已精確更新既有 Bank task `ExecutionTimeLimit`：`PT2H` → `PT5H`；XML 僅此節點改變，Enabled／Ready、觸發器、帳號、actions、其他設定與 LastRun／LastTaskResult 均保持。before XML SHA `582d3ea72e00f227d337ef0b4ed18944d30e174f093814a7b927bcedef1b8a77`；after SHA `5ec7e602240482909b5c22827d4198a09c3d5bd2c9657bd54362f39aada24920`。備份、CAS 與讀回位於 `root/bank_task_budget_update/20261004T071635589Z-7e7c6cfbc75342288eca8c86a70b69d6/`。這是設定修正，不是新自然成功紀錄。


### v8 真實 D 根的失敗回執（10/4 08:26 UTC）

`root/current_stock_cycle_controlled_v8_20261004` 於 08:26:14.524821–08:26:16.541610 UTC 實跑 raw `raw-pit-20261004T082615571601Z-48092-fc022cafe9934238992414a448714b82`。23 個 code pins 與本機 storage config 前後未變；raw 外層 exit 0／blocked_source_revision 不能算研究成功。projection 已到 D，外層回執的子路徑驗證仍以 repository 為根，拒絕 `projection candidate root allowed root escapes its allowed root`；B 未執行、cycle 未執行、沒有 fit 或 model／terminal 成功。原失敗保留，修補須維持同一 active root 與 no-follow 防線，下一次改用新 run。

容量 helper 的首次失敗是 ignored 工具未把 repository 加入 Python import path，第二次 partial 是 Windows scandir stat 不含 dev／inode，與 Path.stat 混比造成誤判。改用同一 stat API 後，`capacity_probe/v8_before_v3_20261004.json` 實際完整量測：D free 310,503,694,336 bytes、目錄既有 synthetic SQLite logical 5,615,616／allocated 716,800 bytes；對含 reserve 的 total required 223,165,721,608 bytes 尚餘 87,337,972,728 bytes。這份 baseline 與 v8 失敗都不代表新完整 cycle 的每日成長率；首次與 partial 回執不刪除。


### G5 真實 SQLite 同次驗收（10/4 08:53 UTC）

新批 `root/g5_actual_sqlite_probe_v5` 於 08:53:06–08:53:29 UTC 完成，child exit 0。report `g5_current_fundamental/real_source_probe_v5/g5-current-dab277a80d174536b10e600349303a5f/report.json` 的 SHA 為 `3ec25170cc044355aaf835f8bf6bb9182cbd627c2706e75164f3d7dd07f03b6e`；839 個程式輸入 pins、236,287 列 current 值的 QA DB 與 CSV 均前後不變。自然分析使用 10/2 官方 PE：1477 為 13.11，YoY -5.116268514859943828024049295%，按既有 YoY 下限排除；2382 為 14.47，YoY 177.4536406985280062124558709%，按既有條件入選。兩者保留原件與同報表比較身分，current observations 仍非正式 PIT。

v4 的失敗來自 QA helper 無條件要求 aware `decision_at`；實際 explicit today formal PIT 已正常完成，date-only context 的 `decision_at` 原本即為 null。v5 保留 null 並明列 `not_provided_date_only_formal_pit`；formal lane 只使用其 date-bounded `daily_prices.pe` 來源，1477／2382 各為 15.43／15.18、來源日 8/6，均因 PE 上限 15 排除，未使用 current observations。自然 current lane 仍要求真實時鐘、截止及來源 lineage；缺時鐘負例仍拒絕。原 v4 stderr 與失敗 receipt 保留，沒有把它改寫成來源拒絕或執行成功。

另完成 PE 零／負／非有限值的共同拒絕規則與保存 Advice 自身決策日的行情日上界；官方本批兩市場原件沒有零或負 PE，因此負值情況以明示合成回歸驗證，不宣稱來自官方實測。這些驗收不替代最後原生 UI。


### 第九批完整週期的 writer 契約失敗（10/4 09:10 UTC）

v9 `raw-pit-20261004T084239819362Z-14940-b4275cc1b5304420bd4dd47170d10f5f` 於 08:42:38–09:10:11 UTC 執行；24 個 producer 程式 pins 與儲存設定前後一致。原始研究輸出及 outcome 完成，30,861 筆觀測、40 個 fold，outcome manifest SHA `8782240608fe3888ce703ab91e77474390aa59dbe3a1caa2ef4500eef022fd33`。模型 fit 的 caller 先建立 `model` 空目錄，但 create-only writer 自己必須建立不存在的 leaf，因此在發布時拒絕 `research model output already exists`。這是工程呼叫契約錯誤，不能稱樣本不足或模型已可用。外層 raw exit 0／blocked_source_revision 與 nested cycle failed 分列。

原 terminal 為 `D:/Min/Python/Project/FA_ML_Research/current_stock_cycles/2026-10-02/437aa76c88ac050886a9f3a7fd7c6a91/terminal_receipt.json`，SHA `4836cf194ec541af421551276e00ce678f374b525bc60f9a90fd6286333e615e`；輸出與失敗收據保留。修補須由 controller 傳不存在路徑，writer 保持查重與 create-only，並在昂貴計算前拒絕既有目錄，不接受或刪除空目錄來通關。

本批同時暴露 G9 等待用的 running status 回呼漏寫完整 envelope；08:43 的真實等待因 `canonical_raw_status_schema_mismatch` 拒絕，沒有成功等待的證據。修補回呼使用原 `_base_status` 及 raw 真實起始時鐘；consumer 的 schema／run／date／root 保護維持。新批需重驗實際等待與模型 readback。

09:12:12 UTC 唯讀容量盤點顯示 v9 失敗批新增 logical 5,145,408,626／allocated 3,033,739,521 bytes，D 可用 303,454,298,112 bytes。`capacity_probe/v9_failed_after_20261004.json` SHA `41fd2e5ce3c778b6b31582719ccf50edc5234629421fe8326174ba307f1c4078` 明列僅 delta，不將失敗批當完整成功日外推；磁碟整體變化與研究目錄實體占用分開。

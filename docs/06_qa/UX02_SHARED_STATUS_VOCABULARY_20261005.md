# UX02 共用狀態詞彙有限切片（2026-10-05）

基線 `e347caf14a8f731904bcc3d2e3507f885bccaff9`，沿用唯一 `output/plans/baldr_product_experience_plan_20261004.md` 第4節共同語言／UX02，不重做 learner、Library、效能或 Native1477。Root Sol整合兩位既有Luna Max，分別負責盤勢／持倉與選股 presenter／個股／Console，檔案責任分開。沒有使用其他代理。

## 原計畫到實際落點

| UX02 要求／狀態 | 本包實作入口 | 驗證與限制 |
|---|---|---|
| 明確中文映射，保留未知 | `ui_qt/status_vocabulary.py` 的 `status_label`／`status_detail`；data/load/research/qualification/event/validation具名維度 | `test_ux02_status_vocabulary.py`；未知碼保留，completed 不跨維度推論資料或資格。 |
| 資料缺件／品質降級分開，不當股票風險 | DecisionDesk `_quality_label`、`_visibility_quality_label`、`_set_section_quality`；Portfolio 系統健康摘要與 `_paper_status_text` | `test_ux02_market_portfolio_status.py` 及兩個既有 view 模組；可讀區段不被缺件區段整批抹去，HOLD/WATCH/REDUCE/EXIT內容未改。 |
| 載入中／完成與研究完成不同 | Stock `_set_status`／品質詳情；Console pipeline用load、研究摘要用research；Recommendation成功首屏用research | 既有worker與stale callback保護不變；新選股UI測試確認研究完成仍另列ML來源限制。 |
| 未到期與合法休市不作故障 | `waiting_for_time`／`not_due`、實際Paper碼 `skipped_non_trading_day`；Console、Stock到期文字、Portfolio、Workbench | 泛pending只標待確認，泛skipped保留原碼，不猜日曆；Workbench仍顯具名missing/error診斷，休市翻譯不授予證據credit。 |
| 研究完成與正式資格分開 | helper research／qualification；Stock ML資格摘要、Console gate、選股三個中文display欄 | 原machine欄及原nested provenance dict契約保留；不改校準判斷、機率或promotion。 |
| 真實錯誤不美化 | failed/error→執行錯誤；回測保留PASS/WARN/FAIL並加validation白話 | validation FAIL為驗證未通過，非籠統等待；warning顯警告而非全部注意，詳細原因仍保留。 |
| 摘要與技術詳情同義，原碼可追 | 同helper label/detail；盤勢／持倉tooltip及accessible描述、Stock資料稽核、Console表格詳情 | 日期、原始碼、診斷及來源身份沿既有欄位保留；專用領域狀態用既有fallback，不全頁重構。 |
| 當期與歷史日期分開 | Stock研究日／資料日／歷史事件及ML scope既有欄位；Recommendation保存讀回首屏明示歷史保存結果 | `as_of_visible`／`source_recovery`及canonical來源consumer回歸；未修改來源／日期／run／hash拒絕guards。 |

「足夠判讀」是研究可讀性，不是股票安全或正式資格。本包不推論當期缺ML即全報告不可用；也不把歷史保存事件套成今天結論。股票／持倉風險原始診斷保留，資料限制另列。

## 驗證

| 範圍 | 結果 | 證據 |
|---|---|---|
| Root詞彙／Workbench view／回測 presenter | 54 passed | `output/qa/ux02_status_20261005/root_final.xml`；後續實際休市碼與選股首屏另外覆蓋。 |
| 最終關鍵狀態＋選股首屏 | 15 passed | `key_states.xml`，含研究完成／ML限制分列，休市／未知／真正錯誤，waiting不遮具名來源故障。 |
| 整合review後最終詞彙／研究consumer | 41 passed | `final_mapping.xml`；額外修正Console舊fallback會改寫未知碼內的unknown/missing大小寫，現維持原碼完整字串。 |
| 盤勢／持倉新fixture與既有consumer | 67 passed／5.02s | Luna實際tool結果；隔離目錄 `output/qa/product_stage01_20261005/stage1_ux02_status_followup_9d81163a8d4a4e659741f37f3eab0e1c`。 |
| 選股presenter／Console／個股／日期／source recovery | 112 passed | Luna實際tool結果；`output/qa/product_stage01_20261005/stage1_startup_ux02_luna3`，一項pytest cache權限warning，未影響測試。 |
| Root選股execution／保存來源consumer | 最初17 passed／5 failed，五項隔離重驗5 passed | `recommendation.xml`保留失敗；`recommendation_handles.xml`為Windows no-follow祖先handle沙箱限制解除後重驗，未修改保護。 |
| 必跑Workbench | 85 passed | `workbench.xml`。 |
| 必跑update validator | 25 passed／4 skipped | `validator.log`，沿規範命令執行。 |
| 全域型態／語法 | 最終mypy 767 files無issue；15個changed Python compile通過 | `mypy_final.log`、`compile.json`；包含9個產品呈現檔及6個test檔。 |

以上群組有重疊，不加總成不重複測試數。兩位Luna未產生JUnit的組別採其實際tool回報，不能將隔離目錄當成JUnit；root群組有獨立XML。首次盤勢run發現區段不一定有獨立as_of_date，已以snapshot判讀日fallback修正，不冒稱資料觀測日；其餘舊文案assert按新共用詞彙更新。首次研究run發現新增nested provenance label破壞exact dict契約，已移除；未知coverage沿領域fallback並保留原碼詳情。失敗不是自然成熟問題，也沒有調整domain保護。

## 真實唯讀consumer文字確認

使用實際 `TWStockConfig` 正式來源根，關閉config初始化的正式目錄／log寫入，僅呼叫 `StockResearchReportReadService.read_report` 和離屏 `_on_report_loaded`。沒有完整MainWindow、持倉服務、Native或自然producer驗收。

- 2382，研究日與實際行情日皆2026-10-05，收盤331；目前ML scope為 `current_stock_research`，沒有精確相符當期run／event_date／hash，維持空值，沒有借用10/02舊run。
- 首屏badge「部分可用（資料缺件）」、文字「報告部分載入；可讀內容與缺件分開列示」，技術觀察與具名ML來源限制仍可讀。文字由實際QLabel讀回，非受控DTO。
- 主DB與候選DB的device/inode/size/mtime前後一致；這是stat guard，不是全DB內容hash。主DB4,051,714,048 bytes、候選755,363,840 bytes，未拷貝大型DB。
- 首兩次probe寫死10/02且第二次redirect output來源至QA，日期assert失敗已保留；最後改為核對本次實際資料日並沿正式readonly來源，未改產品／日期guards，未造ML降級或資格。
- 最終UTF-8 `readonly_consumer.json`／`report_observation.json`／`labels_observation.json`保留真實身份、文字與兩個呈現檔SHA。離屏PNG使用未初始化中文font的QA QApplication，字型方框已實際檢視；**只採文字確認，不作視覺或Native驗收**。stdout redirect有本機編碼顯示限制，以UTF-8 JSON為準。

## 交付與剩餘界線

Manual、UI功能文件、目前架構、Snapshot、文件索引、兩份交接及原計畫同步。原計畫只追加，修改前bytes副本與prefix核對留在本包output。9個產品檔均屬UI呈現邊界，無核心金融計算、排序／cutoff或未來資料查詢新增。

回退只針對本包commit作revert；原計畫追加可由本包before副本核對還原，保留使用者後續追加。未知根檔 `paper_event_source_capture.py` 與 `C:/ta_iso_1005`隔離／還原映射未讀未動。沒有producer、訓練、策略／模型寫入、全量回歸、效能重跑、Native1477、清理或push。

本包完成UX02指定有限入口；全頁全狀態／訊號變化、證據種類的全面字典、Native閱讀與視覺驗收仍非本包。不能宣告整個stage1／UX17完成：Backtest初始化18.62%未達既有20%門檻、UX16來源availability/warm-up/PIT/universe/benchmark及UX19容量／writer依賴另留。完成本地commit／blob／status核驗後交父層安排下一包，不跳UX18或新增ML。

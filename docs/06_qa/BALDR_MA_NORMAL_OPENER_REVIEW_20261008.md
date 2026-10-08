# 四均線正常來源入口：局部驗證與待完成項目

日期：2026-10-08。此文件記錄 F02 後端整合的局部證據，不代表完整補完計畫、UI 或候選 EXE 已通過。

收藏／比較及觀察清單 service 整合已完成中央回歸：21 passed、618.72 秒。Main／Watchlist 專用路由已接線，工作台與 namespace 回歸 88 passed；最小 Main mount／關閉回歸 10 passed。新 MA view 的完整來源旅程仍未接受，保存排序還原缺口正在修正；新增同來源條件重查回歸 session74431 執行中。以下分段保留各次失敗與接受範圍，不能把局部通過視為完整補完計畫完成。

正常 F17 bundle opener 與 query reopen 使用同一份保存的合成封套。四均線投影掛接於既有逐股驗證迴圈，只有來源驗證成功且 P01 session 發布後才建立 MA session；投影例外不得發布部分狀態。金融數值沿用既有證據計算，沒有新增裸 float 計算。原始窗口、特徵日與可用性註記保留；來源缺少 available_at，歷史 PIT 資格仍為 false。

## 已核對的證據

- Root 原始 row observer 測試：2 passed，10.57 秒。覆蓋原始 row 只消費一次、包含空 segment 的 begin/end，以及例外不發布部分 session。
- 後續新增逐股取消案例：3 passed，8.68 秒，程序 session 93314、exit 0。第二檔投影提出取消後立即停止，begin 有記錄而 end 未完成，built/published session 均為 None。首輪把取消錯誤誤期待為一般 callback 失敗；修正後發現原迴圈要到 16 檔批次結束才停。P01 現於 observer 回傳後檢查取消，保留既有具名錯誤。兩次失敗 QA 目錄保留；source mypy 通過。此變更不影響未掛 observer 的迴圈。
- Root 未掛 observer 的 P01 相容性測試：1 passed，11.80 秒。
- Root F17 原有 canonical page request 與具名取消錯誤正規化：5 passed，0.73 秒。此範圍沒有建立新來源 fixture，不代替完整 F17 旅程。
- Root 後續完整 F17 reader 回歸：27 passed，350.82 秒，session 50744、exit 0。命令為 `.venv/Scripts/python.exe -m pytest tests/test_daily_market_technical_official_disposition_query_reader_v1.py -q -o addopts= --basetemp=output/qa/f02_root_f17_regression_20261008_a`。覆蓋真 257 檔跨段 join／排序／分頁、正常 factory 與雙讀 oracle 一致、來源漂移拒絕、取消不發布、選取 materializer、壞 result/page 拒絕、最終回傳取消門、原 F17 新程序重開。這不等於新的 MA canonical request 已在另一程序驗收。
- 正常入口 attempt03：257 檔納入、1 檔排除、6 頁；兩檔 unknown 子集以股票代碼降序得到 1001、1000，各一頁。從同次 exact P01 session 讀回兩檔 snapshot，重建證據的 state、reason、evidence identity、raw window 與 snapshot identity 均相符。
- 同 session 的條件、排序、兩頁及恢復完整母體，投影計數保持 257；第二次 exact query reopen 後為 514。完整末頁為 1250–1256。兩次 MA index/session identities 相同，跨 segment 的 root 與 plan identity 替換被拒絕。
- Root 已直接閱讀 attempt03 收據；三個整合來源檔 mypy 通過，四個來源／測試檔 py_compile 通過。
- Root 獨立完整 MA query 測試：11 passed，166.75 秒；命令為 `.venv/Scripts/python.exe -m pytest tests/test_daily_market_technical_universe_ma_alignment_query_v1.py -q -o addopts= --basetemp=output/qa/f02_root_ma_pytest_20261008_e`，程序 session 25722、exit 0。涵蓋 60 筆合成原始價格證據的投影與 exact collector，但不足以取代正常 UI 或 EXE 驗證。先前 sandbox 執行為 9 passed、1 failed、1 error，兩個未過案例均在隔離 SQLite 路徑 resolve 受到 WinError 5；改用授權的隔離 QA 執行後全數通過，沒有修改產品來繞過限制。

原始收據：`output/qa/f02_ma_normal_open_reuse_20261008_d/normal_bundle_and_query_reopen_attempt03.receipt.json`，SHA256 `E9CBB3B79F8998DE6F753D2890D73F1F7DC13910B922F3DE12A6014FC4B541E6`。腳本 SHA256 `EB404314EF81C1BDA2DB0D072EC07849D3E81379A13D13A67B8744F72D763CAB`。

測試來源不足 60 個觀測交易時段，因此全部 MA unknown 是合理結果。本次不證明正向多頭排列條件命中，也不證明正式資料完整性或效能門檻。先前 attempt01 計數顯示錯誤、attempt02 測試腳本字串屬性存取錯誤均保留，不能作為通過證據。

## 尚待驗證

1. 全新程序以保存 canonical query 重開，保持 F17、P01 與 MA identities，重做兩股條件及完整母體還原。
2. 至少 60 個觀測交易時段的正向／反向來源證據與決策日界線。
3. 正常 UI 條件、排序、分頁、返回及收藏流程；候選 EXE 必須另驗。
4. 1,000 檔固定來源效能矩陣。上述秒數是個別測試耗時，不能視為 p95。

## 正常查詢接入的審核要求

目前 F17 canonical query 沒有 MA 條件；取得 `ma_alignment_session` 不能證明正常結果或收藏已保存 MA 篩選。接續須有版本化 composite request，綁原 F17 canonical query、同源 P01／MA session 與 index identities，完整保存條件、全域排序、分頁及選取。舊 F17 query／收藏必須沿舊 schema 解讀，不能偷偷補上 MA 條件或改變原 identity。

中央直接檢查 F17 `execute`，現有流程對完整保存事實逐股 join P01，再計數、收集排序鍵、全域排序。MA 必須接入這個已核驗的完整迴圈，不能在已選結果或當頁表格做本地交集。cohort 排除、來源資格、row scope 與明示股票 eligibility 是外層限制；OR 只能作用於明示的規則群組，不能讓 MA 命中繞過母體或資格限制。三值 truth 與實際會員資格分別計數，unknown 不自動變成 match。

接入前需補反例：OR 不納入 excluded／pending、未知條件不冒充命中、改變市場範圍不混來源、同值排序穩定、跨段完整母體先排序後分頁、舊 JSON bytes／identities 保留、未知字段拒絕，以及新收藏在另一程序 exact 重開。這是待實作合約，不是 UI 接入完成證據。

## 新程序完整母體補驗（2026-10-08）

中央直接讀取 `output/qa/f02_ma_fresh_pid_20261008_a/attempts/attempt_20261008T130612_4a7f6073db55/parent_receipt.json` 與 `child-output/child_report.json`，SHA256 分別為 `372b6d9b982184f844043944fd666b50b05d7ae211de43147e993e9d5be92fb9`、`07200b7d7c54cf48be98dc3c0c57535af643c15bcf545b70f9a26f30d6679efe`。兩者 status passed、child exit 0，27.094 秒內完成既定 300 秒期限；parent PID 8888，Windows redirector PID 41184，reporter child PID 40784。

Parent／child 各自從 exact bundle 正常 opener 讀入，MA projection 都為 257 次、分段 `[256,1]`，後續查詢沒有重投影。Unknown 查詢兩股全域降冪為 `1001,1000`、分兩頁；完整查詢 257 股分六頁，末頁 `1250..1256`，兩程序的結果、頁面及證據 identities 相符。原來源 inventory SHA 起訖同為 `a5b500d147700b311ac427c477480a6304272ad26cd901617d512b87969255be`；兩程序的網路、SQLite、越界路徑與未授權程序嘗試均為零。

首次 attempt 的 NUL stdin 防護失敗仍保留；QA 改用 attempt 內零位元組檔案的唯讀 handle，並先以真實 suspended Job 執行固定 Python probe。沒有放寬 NUL 路徑或程序白名單。此補驗證明來源版正常 opener 的新 PID exact 重建；`source_available_at` 仍 null、availability unknown、historical PIT false，尚不證明 MA UI／收藏接入、正式來源資格或候選 EXE 通過。

## 新複合查詢的中央審查（尚未接受完整接線）

新增 MA／F17 複合查詢將完整母體的硬限制、規則群組與 MA 三值判讀分開處理；全域排序後才物化選取頁。可見筆數 `visible_count` 與 predicate match／unknown／not_evaluated 分開，沒有啟用條件不代表每筆均命中規則；pending／excluded 維持 not_evaluated。舊 F17 query 與收藏 schema 不變。

中央獨立小型契約驗證為 16 passed（0.69 秒），命令 `.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_daily_market_technical_official_disposition_ma_query_v1.py -q -o addopts= -p no:cacheprovider --basetemp=output/qa/ma_composite_root_review_20261008_a`。全專案 mypy 通過 914 個來源檔案。這些只證明契約與型別，完整 257 股複合 query／各群組真偽／六頁一致性／新收藏及 UI 仍未接受。

審查另發現兩處取消邊界：多欄排序的 partition／各欄排序前後須檢查取消；public page API 須在全結果錨點重核與 JSON 工作前先驗取消。目前已交回窄修，尚未修完，不得以既有 16 項測試授予這兩項接受。

取消窄修後中央已直接核程式並獨立執行新增契約測試：18 passed，2.89 秒，basetemp `output/qa/ma_composite_cancel_root_20261008_a`。多欄 partition 每 256 筆、股票碼排序及各欄排序前後均檢查取消；public `read_page`／`read_page_request` 在 request／結果錨點作業前先拒絕已取消或無效 callback。這更新上一段的兩項局部待修狀態，完整新增複合查詢接線仍待 257 股驗收。

既有 F17 完整回歸已由中央取得終態：27 passed，352.22 秒，session 26101、exit 0。命令 `.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_daily_market_technical_official_disposition_query_reader_v1.py -q -o addopts= -p no:cacheprovider --basetemp=output/qa/ma_composite_f17_regression_20261008_b`；涵蓋原 257 股 join／排序／分頁、正常 factory、來源漂移、取消與新 PID 重開，不能折抵新增複合群組的完整母體驗收。前一 sandbox attempt 因 extended-path WinError 5 造成 fixture setup 失敗（5 passed、22 errors），保留失敗，沒有修改產品避開路徑驗證。

## 回滾與範圍

本次產品變更限定 projection protocol、P01 builder observer、F17 opener 與 MA query 模組及對應測試；既有 raw QA 封套不修改。回滾應以保存的各檔前像逐一還原本任務變更，先確認沒有其他人後續修改，不執行全工作樹還原。操作手冊須在正常 UI 接入完成時同步入口、條件意義、unknown 與 PIT 限制。

## 收藏、比較與觀察清單整合回歸終態（2026-10-08）

中央 session98850 終態 exit0，直接讀取 `output/qa/watchlist_ma_registration_20261008_a/pytest_full_integration_attempt01.log`：21 passed，618.72 秒。命令為 `.venv/Scripts/python.exe -m pytest tests/test_daily_market_technical_official_disposition_ma_comparison_v1.py tests/test_daily_market_technical_official_disposition_ma_bookmark_v1.py tests/test_watchlist_ma_bookmark_v1.py -q -o addopts= --basetemp C:/t/root-ma-integration-20261008-a`；使用全新隔離測試目錄。

覆蓋跨頁比較、收藏 strict exact 重開、單次 opener／query 的公開 RestoreContext 翻頁、錯查詢／偽造／取消拒絕，以及觀察清單保存、重新載入、移除與恢復原 payload。無效或未知版本仍保留 MA namespace，不落入一般研究解碼。中央另核四個凍結 backend／test 檔案 SHA，均與送測值一致。

此接受限定已測的後端與觀察清單 service；尚未證明新 MA 畫面、Main 接線、收藏重開後同來源改條件、複合 257 股完整矩陣或真人使用流程。接續追加公開 RestoreContext 的完整改條件 API，再整合新畫面並執行 UI 驗收；不以本次 21 項回歸宣告整個補完計畫完成。

## 觀察清單專用路由施工與更新頁驗證（2026-10-08）

觀察清單新增 MA 專用 namespace 辨識、收藏標籤、精確 ID 核對及 typed signal；損壞、缺失或未知版本不能退回一般個股研究。Main 的 signal 接收與 MA 畫面仍施工中，不能以 signal 存在授予完整 UI 接線接受。

必要工作台回歸 85 passed，4.71 秒。更新頁驗證第一次 sandbox 執行為 21 通過、3 失敗、4 跳過；直接核 log 可見 isolated fixture 的 daily_prices 同步遇 WinError 5，後續 daily／technical availability 為 empty。保留該次 log，未修改產品或正式資料；使用腳本相同的全新隔離 fixture 在 native 環境重驗，exit0，25 通過、0 失敗、4 跳過。兩次 log 分別為 `output/qa/ma_watchlist_ui_root_20261008_a/update_validator.log` 與 `update_validator_native.log`。

MA API 修改中的 RowScope 匯入錯誤使新增路由測試無法收集，並使全專案 mypy 在 918 個來源檔案中回報 1 error；已交由該 API owner 修正。此處記錄的是實際失敗，須修正後重新執行路由測試與型別檢查，不提前宣告通過。
RowScope 匯入來源修正後，中央新增 MA 路由測試重驗 exit0：3 passed，覆蓋損壞 v1、未知 v9 及缺 payload 的 MA namespace 維持與精確 ID 拒絕。`watchlist_view.py` 與該測試 py_compile 通過；完整型別與真畫面重開仍須等 API／畫面凍結後驗證。
Main 接線施工後，中央另核收藏 worker 的錯誤與原生終態 callback：主視窗進入關閉時不重新啟用按鈕或發布錯誤到畫面，強引用仍保留到原生終態。Main／Watchlist 語法及局部 mypy 通過；工作台加 MA 路由回歸為 88 passed，5.03 秒（session79613，exit0）。這些尚未涵蓋新 MA view 的真來源收藏重開與全專案最終型別；須待該 view/API 固定後補驗。

## 收藏重開後修改條件的中央靜態審查

中央直接檢視新增 `RestoreContext.execute_query_conditions`：完整 F17 硬條件、技術規則、F17 排序、MA 狀態、群組 AND／OR、unknown 政策及 MA 排序均為明示參數；序列有上限且禁止字串冒充序列。實作由原 exact session 建立 `conditioned` session，再由該 session 建立並執行新 MA query，不能沿原 session 執行而丟失新條件。

回傳前核同來源 pins、MA session／index／source request／方法身分，並執行 result 錨點核驗及最終取消檢查；current-only、未知 official available_at 與 historical PIT false 不變。原收藏 state 未被替換，公開 API 不暴露來源 proof。此為靜態審查結論，新增真來源條件重查測試尚待執行，不能視為完整契約接受。
中央新增最小 Main mount 接線測試，與既有 shutdown coordinator 回歸合跑 exit0；實際測試數以 `output/qa/ma_watchlist_ui_root_20261008_a/main_route_shutdown_attempt01.log` 保存。新測試建立 Qt 主視窗 harness 與真兩個研究 view，確認 MA 為獨立分頁、無來源時不啟 worker／讀取，以及 Main freeze gate 將 MA 設為關閉狀態。這沒有建立完整 MainWindow，也沒有替代真來源收藏旅程。

## MA 畫面條件還原的後續缺口

中央直接檢視新 view 發現 `_read_conditions()` 仍無條件建立 neutral F17 sort，而 `_apply_query_controls()` 未保存原 F17 sort；此外空 MA sort 被控制項的預設 stock_code clause 取代。這會使收藏重開後即使只改另一項條件，仍悄悄改動保存查詢的排序內容與 identity。

已交回 view owner 修正：新來源可明示初始化預設，但還原必須保存完整 typed 排序（包含空 tuple）；在使用者未明示修改排序前，條件重查沿保存值。須補非預設 F17 sort、空排序與改其他條件後排序不變的測試。後端 API 的完整參數契約不能替代畫面實際傳參驗證。

# 四均線正常來源入口：局部驗證與待完成項目

日期：2026-10-08。此文件記錄 F02 後端整合的局部證據，不代表完整補完計畫、UI 或候選 EXE 已通過。

收藏／比較及觀察清單 service 整合已完成中央回歸：21 passed、618.72秒。真MAView旅程、Main／Watchlist實際方法路由，以及完整MainWindow constructor／收藏／重開／shutdown均已通過中央獨立合成隔離複驗。原H20、候選EXE、全母體效能與真人驗收仍未完成。以下分段保留各次失敗及其接受範圍。

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

## 尚待驗證（截至 2026-10-08 原紀錄）

1. 全新程序以保存 canonical query 重開，保持 F17、P01 與 MA identities，重做兩股條件及完整母體還原。
2. 至少 60 個觀測交易時段的正向／反向來源證據與決策日界線。
3. 正常 UI 條件、排序、分頁、返回及收藏流程；候選 EXE 必須另驗。
4. 1,000 檔固定來源效能矩陣。上述秒數是個別測試耗時，不能視為 p95。

2026-10-09 後續收據更新：原清單第 1 項已由 V11 固定合成來源的新程序 Main／Watchlist 收藏重開旅程接受；第 3 項的 Main、排序／分頁與 typed 收藏路由也在同一固定合成旅程中得到接受。這些結果不涵蓋候選 EXE、真人驗收或原始 H20。第 2、4 項仍未解除；精確範圍見本文末的 V11 收據摘要及 [MA V9 child identity Root review](BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)。

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

契約補核更正：F17 codec 明示合法 query 的排序不可為空；MA factory 將空輸入正規化為股票碼升冪。因此上述「保存空 tuple」不能套用於已核合法收藏，亦不應擴充 schema 或製造非法收藏來測試。實際要求是完整保留合法非預設排序；非法空 payload 應拒絕，factory 的既有正規化契約維持。非預設排序還原後不得被 UI neutral 預設取代的缺口仍須修正與驗證。
## 同來源條件重查新增測試失敗（2026-10-08）

中央 session74431 終態 exit1：11 passed、1 failed，259.56 秒；新隔離目錄 `C:/t/root-ma-requery-20261008-c`，log `output/qa/ma_watchlist_ui_root_20261008_a/bookmark_requery_attempt03.log`。直接核 traceback：新增測試要求 `stock_code desc`，被既有 MA `stock_code_tiebreak_invalid` 契約拒絕；股票碼 tie-break 必須升冪。

已交回測試 owner 改為合法非股票欄位降冪及末尾股票碼升冪，另保留非法方向拒絕驗證，不放寬產品排序規則。此失敗尚未證明新重查情境通過，須修正測試後重驗。前兩次 attempt 僅 fixture／plugin 模組載入失敗，未進產品執行；原 log 保留。
## 窄窗幾何通過與 nested F17 排序審查更正

中央直接執行新 UI 定向測試，exit1：2 passed、1 failed，3.54 秒；log `output/qa/ma_watchlist_ui_root_20261008_a/geometry_root_attempt01.log`。460／800 像素寬度的無來源真 view 幾何、控制項完整可見及詳情／稽核末段可達兩項通過；尚未授真來源或真人接受。

第三項在建測試 query 時即被 `nested_f17_sort_or_page_not_neutral` 拒絕，尚未呼叫 view。中央再核 MA codec 的 `_parse_f17_query`：複合查詢明示 nested F17 只用股票碼升冪、技術 neutral order、頁0／size1；有效全域排序位於 MA 外層。因此先前要求「保存非 neutral F17 sort」套用了不適用的 F17 單獨查詢契約，撤回該要求；view 使用 neutral F17 本身符合 MA 契約，不應為該測試擴 schema。

正確驗收改為合法 neutral F17 不變、合法非預設 MA 外層排序在還原及改其他條件後保持完整；非 neutral nested query 應保留拒絕負例。已交回測試 owner 修正，這項失敗不視為產品排序接受或回歸。
更新 UI／API 後，中央全專案 mypy 重新執行 exit0，918 個來源檔案無錯誤，log `output/qa/ma_watchlist_ui_root_20261008_a/mypy_full_attempt02.log`。直接檢視窄窗 detail 截圖尚未看到末段 sentinel，已要求將 inner cursor 位置映到 outer scroll viewport 一併驗證並重拍；不能只以內文編輯器自身的可見範圍授整頁末段視覺接受。
## 正式字型／主題下的窄窗失敗

中央發現早期 offscreen 截圖未套 Main 的 `apply_app_theme`，中文字呈方框。使用既有主題與 Windows 中文字型重驗新 UI 4項（session16437，exit1）：3 passed、460px 1 failed，4.08 秒；460px 水平捲軸 maximum 為6，違反無水平裁切要求。log `output/qa/ma_watchlist_ui_root_20261008_a/themed_geometry_attempt01.log`。

因此無主題幾何通過不能授正式 UI 窄窗接受。已解除 view owner 的 UI leaf 凍結，只修該 view 的響應布局並要求測試使用正式主題，不縮字、不放寬斷言、不修改共用主題。中文字型由既有 `ui_qt.theme.fonts` 載入，不下載或替換產品字型。須修正後以正式字型核控制項、末段與截圖。
## 條件重查第二次定向終態（仍未接受）

中央 session30762 終態 exit1：1 passed、1 failed、11 deselected，232.11 秒，log `output/qa/ma_watchlist_ui_root_20261008_a/bookmark_requery_attempt04.log`。非法股票碼降冪拒絕測試通過；合法重查已完成 conditioned query 執行、來源 pins 不變及新 query／operation identity 的斷言，但可見筆數為0，測試預期1，故完整情境仍失敗。

已要求先對照原已保存 1001 技術規則事實：MA unknown 不等於 MA5／MA20 金叉規則 unknown。須以獨立原規則狀態設定有明確預期的符合／不符兩個重查情境，不直接把預期改0、不弱化 AND 或 unknown 政策。只有原事實與回傳結果都核對後才可接受重查行為。

## 正式主題窄窗修正中央複驗

view owner 僅將頁面左右內距設為5px，保留原上下內距；未縮字、未放寬幾何斷言或修改共用主題。view SHA `eb5a63fe3787782fb469b9658e8f66cd6b2d5bf44bdf764fa42ade64cf425716`、presenter SHA `509bf53b5470f338db9541ca201ba6c85082168eeb0a9073f978128c1a6ae903`、test SHA `647a9ec65abd185fae38bbebd615b2dd99f4eae57eb706b62fc44341560cb7d9`。測試 fixture 使用正式 Main theme；460／800 水平捲軸 maximum 為0，控制項完整可達，inner 文件末段映至 outer viewport 核對。

中央獨立重跑新 view／最小 Main 接線／Watchlist 路由共8 passed（3.53秒），log `output/qa/ma_watchlist_ui_root_20261008_a/themed_geometry_root_attempt02.log`；同時實際檢視 `output/qa/ma_official_view_render_20261008_b/detail_end_same_fixture_460.png`，中文可讀且 `DETAIL-END-SENTINEL` 完整出現在外層 viewport，沒有水平捲軸。460截圖 SHA `753a9f5ccd764a290b98d394d4c88f96c0aedaee78298aad63b30249299dd`。此接受限正式主題下無來源 view 幾何與路由，仍未證明保存來源載入／條件重查／跨頁收藏的完整 UI journey，也不授真人接受。

同版修正後專案強制作業完成：update workbench 85 passed（4.27秒）；隔離 update validator 25通過／0失敗／4跳過；全專案 mypy 918檔案無錯誤；本次 Main／Watchlist／MA view／presenter／service／bookmark／comparison 的 py_compile 通過。新 log 名稱分別為 `workbench_geometry_attempt03.log`、`update_validator_geometry_native_attempt03.log`、`mypy_geometry_attempt03.log`，保存在同一中央 QA 目錄。validator 原生隔離執行沿用已查明的 sandbox WinError5 排除方式，未碰原始資料或正式排程。

## 條件重查保存事實與計數口徑補核

owner 以原保留 bundle exact-open 核1001的五項技術規則皆為 `no_match`，MA狀態為 `unknown`。session55998 終態 exit1（200.47秒），log `output/qa/ma_requery_rule_expectation_20261008_a/requery_attempt02.log`：同來源 no_match 正向查詢為1筆、改要求 match 反向查詢為0筆，query／operation／來源／單次opener斷言已通過；最後將 `ma_truth_counts[unknown]` 預期為1的斷言失敗，實際為257。

中央獨立核 reader:1456–1462：technical／MA／composite 真值分布對完整宣告母體累加，只有 eligible 分布位於 hard-eligible 分支；Counts 的建構核驗同樣要求前三者合計 declared，而 eligible 合計 hard_eligible。故本次為測試口徑錯誤，不應改產品計數。修正測試須同時驗完整MA分布與基準相同、hard_eligible為1，以及正向eligible unknown為1／反向eligible no_match為1、visible為0。修後完整案例仍待新一次終態，不以部分斷言通過授完整重查接受。

## 保存合成來源的重查案例通過

owner 重用 session55998 保留的 sealed bundle，未再產製來源；helper 新 attempt02 handle95482 終態 exit0，31,466ms。固定 bundle identity `b59b1c4703f63d38bdcd93d4bc870f0d37f2f6203896ea9bc2ba98e0d04b80af`，manifest SHA `179d2f4efdace2b33a49c91a0d95d4ccd4766b6a82efbf3fbcff238dbb9e8424`。中央獨立讀 receipt，SHA `088772cb72957160de84f1a227599a97c16d5d2696bc70a094a6dca68cdd12ca`，status passed；七項合成來源根（DB bytes、store、兩parent、market／disposal capture、bundle）的前後inventory相同，SHA `0dc6f5dbe1cd9b505ff318777e1bd7fb82475c904c105f325d1c1a01f0cce274`。helper在同公開 exact opener／query API 執行原修正案例；test SHA `346b542680f700e371dac3bdc18c65f4fe3e75a73144bdeaf2c388162a3e2c00`。

正向／反向保存規則條件、單次restore opener後同session重查、來源pins、新query／operation、hard eligibility與完整母體／eligible計數口徑均通過。producer未呼叫是 helper靜態call-path限定，receipt未冒充runtime觀察計數；SQLite只作來源bytes核驗。第一次helper因手抄manifest pin錯誤在preflight失敗，保存原紀錄並由中央 Get-FileHash核正64碼，未放寬pin。此接受限保存來源的backend重查案例，真UI journey仍待驗，原錯誤oracle與其他失敗封套均保留。
# 實際操作旅程補驗：讀取尚未通過（2026-10-08）

新版旅程測試使用四個明示環境欄位注入已保存的合成 bundle；未注入時使用既有真實 fixture 工廠。operation 事件索引在點擊前保存，清理或來源核驗失敗會使測試失敗，不以 pytest 綠燈遮蓋失敗 receipt。

attempt02（owner handle34433，終態exit1）首次 explicit exact open 呼叫一次。測試180秒等候先逾時，bundle-session factory 約187,531毫秒後拋 `technical_official_query_reader_v1_bundle_exact_read_failed:technical_store_exact_read_failed`。取消後原生 worker 已收尾、view 已關閉，保存 manifest／完整來源樹前後 SHA 相同，fixture producer 未呼叫。記錄在 `output/qa/ma_saved_source_ui_journey_20261008_a/attempt02.log` 及其獨立 attempt 的 `journey_receipt.json`。

現有外層錯誤沒有保存底層 StoreError.code，不能據此判定來源損壞。後續僅針對同保存來源的單次 exact opener 做有界診斷，保留遞迴 cause／cause_code 與取消時間；須區分測試逾時誘發取消和真正讀取錯誤。禁止以延長 timeout、重產來源或重跑完整 UI 旅程替代根因分析。此補驗不授整體操作旅程接受。

中央核讀診斷 attempt03 receipt SHA `118b6e72ac89cbede506c2cfeb7eb6baefd9a8afb1c5a366c769787609c2e663`：同一明示保存來源 native exact opener 成功8,625毫秒，total8,641毫秒，來源樹前後 SHA均 `0dc6f5dbe1cd9b505ff318777e1bd7fb82475c904c105f325d1c1a01f0cce274`。前次 sandbox attempt02 的立即 WinError5另保留，不能與 UI187秒混為同一錯誤。UI測試逾時後 finally 主動取消 worker，187秒外層讀取錯誤在取消後出現；最內錯誤碼仍未直接觀察。下一步比較單次真MAView與同步opener等待方式及背景CPU，查明8秒／187秒差異，不憑此診斷授完整UI操作通過。

單次真MAView診斷 attempt04 已終態exit0，receipt SHA `ecfc93f2915f12ff841745d968b0baae823b86124ad2495ccb4cd66a441d044b`：catalog明示選取後載入成功，整輪14,391毫秒，bundle opener8,890毫秒、view task14,281毫秒，operation成功且workers_terminal=true；23,004次取消callback均未回true，來源manifest／tree前後一致。driver採processEvents加短sleep讓出CPU；純CPU thread對照確有qWait等待拖慢現象，但不能只靠此推定原180秒根因。此證據限單次載入，下一輪完整旅程須保留原180秒門檻並驗選取、返回、比較與還原；不以mini診斷代替完整接受。

完整旅程 session37300 終態exit1（pytest45.40秒），封套 `output/qa/ma_saved_source_ui_journey_20261008_a/attempt_1791501997926071500_53008/journey_receipt.json`。已完成載入、翻頁與比較，fresh restore operation回報完成後，綜合assert失敗；兩view正常關閉、active_worker=false、manifest/tree前後相同。讀碼定位測試只計view的bundle opener，收藏reader走另一公開read-session入口，故未計fresh restore的第二次核驗；產品未因此判定有還原缺口。須統一底層exact-open計數及保存逐項actual／expected後重驗，原失敗不改判通過。

後續封套 `attempt_1791502337207545400_38344` 已逐項驗出fresh restore成功：same query JSON／page index1／page request identity／selected1100／兩筆basket identities／context模式一致，BundleReader實際exact read共2次（normal與restore各1）。仍overall failed：同源條件重查operation回True，產品kind為「沿原保存來源重新全域查詢」，測試誤寫「重新全母體查詢」而拒絕。此為具體oracle文字不一致，須修正後繼續驗重查結果與完整收尾，不能把overall failed改判整體通過。合成1100與原H20的2382驗收互不替代。

修正oracle後，owner完整view旅程exit0、1 passed／62.94秒，receipt SHA `3c12013e76a823241ef01c1653968485681ff08157874f65f1dca822304be5cb`。中央獨立session24403亦exit0、1 passed／65.64秒，receipt `attempt_1791502558711345400_17956/journey_receipt.json` SHA `2e97784a0ee682675720b4c6883cbaa9b615bfde25c3f3350c1c72c3c332281f`，log `root_full_journey.log`。兩輪同固定來源，選列／跨頁／比較／bookmark JSON fresh restore／同來源重查均通過；底層exact read正好2次，同來源重查不重開，兩view已close且無active worker，來源manifest/tree前後一致。測試SHA `c3219bc70910c305e26ff8705c652374de94ed679fd1ef775c59a083dd847b97`。

此接受限真MAView的保存來源流程；bookmark JSON fresh restore並非觀察清單實際持久保存／主視窗signal路由，後者仍需獨立consumer整合驗證。也不授原H20、候選EXE、全母體效能p95或完整M2／補完計畫完成。

## Main／Watchlist收藏持久保存與專用路由複驗

新測試 `tests/test_ui_qt_ma_bookmark_main_route.py` SHA `e03743bfdc7d2490dfb550af0fabf68ac69d5173c4368a749549a1221b4af757`，中央獨立native複驗exit0：1 passed，73.82秒。log為 `output/qa/ma_bookmark_main_route_20261008_a/root_route_review_native.log`，receipt為同目錄 `attempt_1791503191720740100_22232/route_receipt.json`。先前sandbox catalog_root_invalid失敗保留，沒有修改來源或放寬產品核驗。

測試使用固定已保存合成bundle，不重新產製。真MAView準備收藏後，由實際Main方法啟動worker保存到隔離WatchlistService；觀察清單選取真列並按研究按鈕，由MA專用signal呼叫實際Main重開方法。初讀與fresh restore各exact read一次，保存沒有重讀；query/page、股票1100與跨頁比較1000/1100保持一致，沒有generic fallback，來源前後相同且workers終止。

此新增證據補足上一節的consumer路由缺口，但Main以最小QMainWindow shell承載實際方法，尚不代表完整constructor、正式資料、候選EXE或真人流程通過。

中央再清除四個MA固定來源環境變數，使用標準既有合成fixture，獨立一般環境複驗exit0：1 passed，159.65秒（含來源產製）。log `root_route_portable.log`，receipt `attempt_1791503503217397500_45548/route_receipt.json`。此驗證補足測試可攜性；固定來源複驗不產製，一般fixture路徑才建立全新合成來源，兩者均不操作原資料或正式排程。

## 完整MainWindow中央獨立複驗

`tests/test_ui_qt_ma_bookmark_full_mainwindow_startup.py` SHA `409742d640dacd0fb3df3dfb7658ff45be7e49072482dbe573bb4f447c59b73b`。owner的真Main及守衛測試2 passed／49.35秒；中央獨立以同4pins、新OS temp應用根重跑exit0：2 passed／38.37秒。log `output/qa/ma_bookmark_main_startup_20261008_a/root_full_startup.log`，receipt `attempt_1791504241000148100_34728/main_startup_receipt.json`。

測試呼叫真正MainWindow constructor，沒有用shell或替換constructor；設定與SQLite均在明示隔離應用根。推薦研究分頁、準備收藏、真Watchlist持久保存及typed重開、相同query/page／1100選取／1000+1100比較籃與正常shutdown均通過。來源七根inventory及manifest前後一致，initial與fresh restore各exact read一次，無generic fallback，網路／DNS嘗試0，原生workers終止。

前三次測試側失敗分別為應用根應在repo外的矛盾、Windows長路徑解析及tree pin遺漏technical database，收據原樣保留。修正後固定已生成的同一bundle進行重驗，沒有每次重產。此接受是同程序完整合成Main旅程；仍不授新程序／新EXE、原H20、F02複合矩陣、效能p95或整個補完計畫完成。

中央另以一般 pytest 環境、不提供四項固定來源 pins，獨立複驗完整 Main 測試：session 55697 terminal exit 0，2 passed／165.35 秒（包含全新合成來源建立）。收據 `output/qa/ma_bookmark_main_startup_20261008_a/attempt_1791505227381209400_22756/main_startup_receipt.json` SHA `a244d893d41348179374b95a0db6d06b5f1c1f32ba6c7be7c12e6d9a2c01957e`，`source_origin=fresh_unique_bundle_fixture`，Main 旅程耗時 36.453 秒。來源 inventory 前後 SHA 同為 `0370adad1811b3b5ef872ac1671c9fb96981e65e6f8205fd710fdafc81ef3c48`，exact read 2 次，startup/open/save/typed fresh restore 通過、網路嘗試空、正常關閉且原生 workers 終止。這補足完整 Main 測試的一般合成 fixture 路由；不代表正式股票來源、新 EXE 或人工作業接受。

## V11 固定合成來源 Main／新程序收藏重開接受（2026-10-09）

MA V9 Root review 記錄唯一完整旅程 `run_attempt_ffce90498c624514a7f3f1874b89e644`，terminal exit 0。父 Main 以固定合成來源完成 AND／OR／OR-only 三組名單（59／158／97 股，page size 50）並正常關閉；fresh child 再經可見 Watchlist 的實際點選與雙擊，typed capture 恰 1、generic route 為 0，成功重開四均線研究收藏。Child 保留 page 1／50、selected 1000、比較籃 1010／1000 與 query/page identities；Watchlist bytes 與固定九來源前後一致，workers 終止、Job 關閉、launcher/reporter inactive。Root 接受此固定合成 MA 閉環，不再重跑同一旅程。

此後續收據只關閉原待驗清單中固定合成來源的 Main／fresh child 與收藏路由缺口。未取得原始 H20／官方資料資格、候選 EXE 或真人接受；build identity 仍為 unverified／unknown；此結果也不提供 1,000 檔效能 p95 或 60 個自然觀測交易時段的正反向驗證。


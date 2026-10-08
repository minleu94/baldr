# 四均線正常來源入口：局部驗證與待完成項目

日期：2026-10-08。此文件記錄 F02 後端整合的局部證據，不代表完整補完計畫、UI 或候選 EXE 已通過。

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

## 回滾與範圍

本次產品變更限定 projection protocol、P01 builder observer、F17 opener 與 MA query 模組及對應測試；既有 raw QA 封套不修改。回滾應以保存的各檔前像逐一還原本任務變更，先確認沒有其他人後續修改，不執行全工作樹還原。操作手冊須在正常 UI 接入完成時同步入口、條件意義、unknown 與 PIT 限制。

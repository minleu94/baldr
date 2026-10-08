# Baldr 讀取 session 中央審核（2026-10-08）

這份記錄涵蓋 P01 的固定來源索引核心，以及 H20 私有 SQLite 副本的設定與 provider 介面。兩者尚未完成 UI 接線、新候選打包或真人接受；不表示完整補完計畫已完成。

## P01 固定來源索引

中央在原生 Windows 的獨立隔離暫存執行 `tests/test_daily_market_technical_universe_v4_read_session.py`，結果 **7 passed / 46.49 秒**，程序 exit 0。四個 owned 檔案的 mypy 通過。原始輸出保留於 ignored `output/qa/p01_root_review_20261008_b.log`。

同一凍結核心的舊 query、stock 與 bookmark 相鄰回歸另為 **13 passed / 302.31 秒**，程序 exit 0，輸出於 ignored `output/qa/p01_root_neighbors_20261008_a.log`。這是整個測試組耗時，不是單次產品查詢延遲。核心下一輪 selection／materializer 修改必須另行重驗，不能沿用這次凍結版本的通過結果。

測試使用真 public producer、repository 與 store 的合成來源：17 股納入、257 股排除，驗證完整索引的 AND／OR、全域排序與分頁、Decimal／同值／空值排序、選股下鑽、空母體／全排除／partial、來源不符、索引預算、取消、child 篡改，以及 fresh 收藏重驗與新程序 strict 還原。這不是 1000+ 股票或真市場 full-N 的效能證據。

session 固定建立時完成核驗的版本；它不宣稱來源後續仍未變動。頁面與個股會精確重開選取的 child artifact；新收藏重新完整核驗來源，跨來源比較仍各自使用 strict reader。64 MiB 是 canonical serialized index 的預算，不是 Python RSS 限制。

初次中央審核發現 `read_stock_snapshot` 先讀 origin page，再重讀選取的 child artifact，要求保留來源與 origin page 身分驗證的去重方案。後續修正證據列於下一段；原實際來源的下鑽延遲仍待另行驗收。

後續 selection／materializer 增量已完成中央 **14 passed / 52.96 秒**、程序 exit 0，四檔 mypy 通過，雜湊與代理凍結值一致。輸出於 ignored `output/qa/p01_selection_root_20261008_a.log`。新介面先全域篩選排序一次，分頁切固定索引；個股與 fresh 收藏共用同次頁面／snapshot 讀取，避免同操作重讀 artifact。明示空 eligibility 回零筆專屬結果，不把舊 query 的空 filter 解讀為零；包含建立 selection 最後取消 gate、身份篡改、空頁、取消與精確 artifact 核驗。原相鄰 query／stock／bookmark 最新回歸另在執行，尚未宣稱通過；尚未接 UI、官方排序或證明真 N 的效能。

## H20 設定與 provider 介面

中央新測試 `test_personal_h20_sqlite_read_config.py` 與 `test_ml_current_observed_read_copy.py` 共 **10 passed / 1.32 秒**。中央另跑既有 bootstrap、historical provider 與 current-observed capture 回歸，共 **85 passed / 3.89 秒**，程序 exit 0；輸出在 ignored `output/qa/h20_stage1_root_regression_20261008_b.log`。

明示設定 `PERSONAL_H20_SQLITE_READ_ROOT` 為絕對路徑，未設定維持 `None`；設定解析不建立目錄，frozen 模式拒絕程式包內路徑。實際 copy session 負責驗證既有私有根與固定來源的隔離。

provider 的 opt-in session 分支核對原來源路徑與 SHA，重用私有副本既有唯讀交易，保持原 provenance、feature 與 row hash；不另開來源 SQLite 連線、不再雜湊原 DB，也不提交或關閉呼叫端交易。未傳 session 的既有路徑保持相容。測試包含錯誤路徑／SHA、已關閉與取消的 session 拒絕，以及原合成 DB 與 sidecar 起訖 hash／stat 不變。

實際 H20 public verifier、feature replay、entry observation 與 Main 尚待接線。原 4 GB 封存來源的保護、等待提示、2382 下鑽時間、收藏新程序重開與新候選資格均未由這些合成測試證明。

## 真人驗收狀態

### H20 點擊路由增量

中央修改 Main 的已核名單點擊路由，直接以原 cohort／selection／reference 開固定個股 context；由既有 selected reader 完成 manifest、capture、來源及終態 fresh 核驗，不再先重讀完整名單。返回仍沿原來源重新核名單。合成路由測試 **5 passed / 2.28 秒**，驗證沒有另開 cohort worker，以及忙碌／未知列／缺參照／關閉中拒絕下鑽。保存來源 Qt 旅程 **5 passed / 10.33 秒**，包含來源變動、報告失敗仍獨立讀 H20、取消／晚到結果與明示重試；這是隔離 host，不是 Native 或新候選驗收。

本輪 UI 強制 workbench **85 passed / 3.58 秒**，原生更新頁 validator **25 通過、0 失敗、4 跳過**，三個 owned Python 檔 compile／diff-check 通過。先前 sandbox fixture WinError 5、repo 內 fixture 被 activation-root-overlap 拒絕，以及舊旅程 harness 缺收藏 handler 的失敗均保留；以外部 OS TEMP fixture 並同步 harness 的 Main handler 後才通過。full mypy 先碰到另一代理正在實作的 P01 selection 欄位／名稱錯誤；待該核心暫停修改後中央重跑，**894 source files 通過**。P01 最新功能測試與安全副本接線仍另行驗證，不能發布或標整包完成。原始輸出與修改前備份在 ignored `output/qa/h20_direct_drill_root_20261008_a/`。

使用者回報舊 `0f25b8c6ee51` 名單最終出現，但等待很久且不清楚觸發時機；雙擊 2382 後反應慢，未確認能下鑽。此項仍未通過；不要求使用者重測舊版。下一候選完成原件保護與 Main 自動驗證後，才提供精確啟動檔及分開計時的名單／下鑽驗收步驟。

## 2026-10-08 中央後續回歸

P01 最新 query／stock／bookmark 相鄰回歸為 **13 passed / 320.09 秒**；程序 handle 47428 已結束，保留輸出於 ignored `output/qa/p01_selection_root_neighbors_20261008_b.log`。四個核心／測試檔 SHA 與先前 14 項 selection 測試凍結值一致。此時間包含合成來源產製，不代表頁面延遲；UI session 接線與 full-N 效能仍未完成。

H20 stage2a 中央獨立操作測試 **12 passed / 1.06 秒**；再以外部 OS TEMP 合成來源執行 daily、capture、outcome 與 operation 四組回歸，**46 passed / 2.62 秒，exit 0**。目前 public input replay 可透過 resolver 重用私有 copy；outcome 測試中既有 helper 的 input verifier／provider mock 只證明傳遞及同操作重用，不能宣稱完整 outcome source replay 端到端。UI cohort／個股 hooks 尚待接線，原始 4 GB 資料保護及 Native 等待提示、下鑽速度仍未驗收。

F17 新查詢純層中央 **24 passed / 0.69 秒，exit 0**。驗證 canonical criteria、來源 pins、membership／unknown truth、cutoff 與排序契約；尚未接 full-N reader、頁面、收藏或正常更新，不能當作 joined query 或完整產品通過。

中央 stage2a 五檔 compile／diff-check 通過。首次定向 mypy 因 scripts namespace 同檔雙 module name 停止，保留為 invocation failure；改用 `--explicit-package-bases` 後的結果另記，不藉新增 __init__.py 改變產品 package。F17 code review 另發現 pure sort 未核 technical row 決策日、future feature 與 missing-data旗標一致性；已退回 owner 補 guards／反例測試，原 24 passed 不代表此缺口已修復。
中央 `--explicit-package-bases` 五檔 mypy 後續發現匯入既有 `tests/test_current_observed_learning_capture.py` 的 28 個型態錯誤，因此這次五檔檢查未通過，不能沿用代理宣稱的五檔 clean。四個產品 source 的獨立檢查另行執行；不改其他 owner 的測試來掩蓋結果。

中央四個 H20 stage2a 產品 source 使用 `mypy --explicit-package-bases` 結果 **Success: no issues found in 4 source files，exit 0**。UI 的實際入口確認為 `scripts/scheduled/personal_h20_daily_hook.py`：cohort 與 selected reader 目前只有 `PersonalH20ReadSession` 的分組驗證，尚未建立 `PersonalH20SQLiteReadOperation`。因此必須把私有 copy resolver 接入 ports，並在既有 reference/capture/source 終態核驗之後、回傳 UI 結果之前完成 copy/source file-group finish；單接 scheduled daily CLI 不能證明 UI 已保護原始 SQLite。

中央追加 UI call graph 發現收藏重開 `scripts/scheduled/personal_h20_bookmark_read_session.py::_read_ports` 同樣取得未綁 resolver 的來源 verifier，不能漏接；daily hook standalone prediction/manifest reader 及 natural hook／batch ports 也列入漏口盤點。設計必須區分 UI 的安全讀取與既有 scheduled 預設相容路徑，確保 fresh 收藏／新程序重開每次完成自己的私有副本與原來源終態核驗，不以名單或單股測試代替收藏證據。

## F17 列級 guard 補修中央驗證

純排序在接收技術列時，新增 decision_date、feature/previous 日期、cutoff、股票／source scope、snapshot/source-window SHA、rule keys與missing flag一致性檢查；pending／excluded 不得帶 processed technical row。中央對照既有 feature_snapshot_v4 的 lookahead 與 current-only `available_at_unknown` 契約，並獨立重跑 **37 passed / 0.71 秒、exit 0**、兩檔 mypy clean。reader issuer／generation／receipt／artifact exact pins 仍待 full join 層證明，不能由公開 DTO 格式檢查替代。

H20 stage2b 接線設計已經中央讀取，授權受控 UI hook／bookmark／Main 接線；代理先逐檔 dirty/preimage，保存 stage2a transport 差異，不重置其他 owner 檔。natural outcome batch 的逐列 publisher 終態語意仍是後續獨立接線項目，不能由 UI wrapper 通過推論 scheduled 全部安全。

## P01 UI 接線中的中央審核修正

中央讀取尚在實作的 view diff，發現 `load_selected` 的「嚴格核驗來源」傳入先前 `_read_session`；相同 catalog pins 會重用舊索引，不能證明明示重新載入當下來源未變。已要求 owner 將 load/reload 改為 fresh strict session，保留篩選、暖翻頁、同操作下鑽／返回的固定版本 cache。需新增非當頁 child 或 receipt 變動後重新 load 的拒絕反例；失敗時保留舊畫面，但不得發布新成功。此 WIP 尚未凍結或中央驗收。

P01 UI WIP 第二項中央修正：`_apply_query_result` 遇到成功的 empty selection（`page=None`）原先仍保留舊股票頁與cache，會讓新條件零結果和失敗混淆。已要求 owner 用 reader-issued query／selection呈現0列與新條件，清空表格、停用當前列下鑽／收藏，但保留來源session供修改條件重查；不得偽造v4Page。讀取失敗才保留舊可見state。要求真fixture零符合及恢復查詢反例；尚未宣稱補修通過。

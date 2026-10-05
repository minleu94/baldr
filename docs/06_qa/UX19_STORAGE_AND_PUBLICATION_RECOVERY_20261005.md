# UX19 儲存治理與發布復原有限收尾（2026-10-05）

基線 `a466ccedf52946981eefe1eb358b23195497417b`；本批依唯一原計畫延續，不重跑已接受的排名收藏、真實 publisher、效能或 ML 鏈。範圍為有界批次、唯讀參照盤點、發布競態與自身隔離子程序故障復原，以及真實 MainWindow 最小隔離啟動／關閉。儲存與發布不改訊號、公式、排名、日期或既有來源拒絕；未新增未來資料依賴。

## 工程與資料安全

永久刪除停用：所有已發布 manifest、其 artifacts，以及 v1／v2 收藏參照都保留。未提供完整參照來源、未知 schema、缺件或盤點超出預算時，診斷採保守保留；dry-run 候選不能作為刪除授權。沒有 delete／move API、清理排程或自動 retention deletion。

原排名首次發布競態：鎖外讀取 latest 缺件後，鎖內也必須比較「缺件」狀態；不能僅在原指標存在時比較。修正沿用 typed refusal、不可變 artifacts、OS lock 和原子指標替換，方法與分數不變。

## 真實 App 最小隔離收據

`scripts/qa_isolated_app_startup.py` 在 repository `output/` 的獨立新 case 設定 `PROFILE=test`、隔離 DATA_ROOT／OUTPUT_ROOT／Matplotlib cache、cwd、policy 與 runtime registry 根目錄，建立真實 QApplication／MainWindow／九個 workspace，不顯示前景。child Python audit guard 拒絕 case 外寫入與 SQLite、網路及新程序；null 裝置例外只丟棄輸出。Windows 版本偵測改在此 QA child 使用 `sys.getwindowsversion()` 唯讀原生 API，沒有修改產品或啟動 shell。

最終 case `app_startup_1791223626396143900`、PID 23772、exit 0；九頁實際類別：UnifiedDecisionWorkbenchView、QTabWidget、RecommendationView、BacktestView、WatchlistView、StockResearchWorkspace、PortfolioView、UpdateView、RuntimeView。worker 0、background process false、violations 空、5.312 秒。原始收據見 `output/qa/ux19_storage_recovery_20261005/app_startup_process_receipt.json` 與 case `receipt.json`。

前四次失敗保留：外部 Matplotlib／相對 log 路徑、Windows null 裝置及 stdlib OS 版本 shell probe 先後被 guard 拒絕；均記 exit 1，沒有冒充 pass。audit hook 是 Python 事件範圍的防護，並非作業系統級完整寫入監視。最終驗證使用真實服務與空隔離資料，不是 populated 正式資料功能驗收、CLI main() 全流程、Native 鍵鼠或真人驗收。

## 容量政策與工作樹界線

使用者確認 `data_module/ml_storage_capacity.py`、`scripts/capture_evidence_events.py`、`scripts/scheduled/run_scheduled_decision_evidence_capture.py` 由另一對話修改，本批不覆寫、不 stage。中央 reserve 的時點值與 code pin 以本批最終收據為準；不把歷史 200 GiB 宣稱為永遠固定，也不替另一對話制定第二政策。發布仍使用既有中央 capacity preflight 與每批／root hard bounds；診斷不等於 writer 授權。

## 剩餘項目與決策

本批不是整個 UX19、stage 2／3 或第一版所有工程完成。其他原大盤／強弱 consumer 融合、完整 feature／method dictionary、正式合格母體與排程部署、其他 writer 生命周期及長期自然增長量測仍須各自工程收據。Backtest 初始化改善 18.62%／20% 未達保持不變，未重跑或放寬。

來源選項須由使用者定案：保留明示人工研究批次作 current-observed 預設，或另採 TWSE／TPEX 官方當期名冊，明確 as-of／observed 時鐘、納入／排除與 custody；官方歷史 membership／availability／PIT 是另一證據要求。舊 Top／Bottom 完整標籤目前原樣保存並提示非一般前幾％／勝率；若要公開原 numeric score 或更正標籤，須批准明確新 method version，不能反推或改公式。

Native 操作／縮放／跨頁、帶真實資料的完整 App、3–5 位真人驗收，以及來源 availability／PIT／自然 ML 資格分列。沒有正式 DB／registry／真實收藏寫入、全市場 producer、learner、永久刪除、push 或使用者視窗操作；未知 capture 與 C:/ta_iso_1005 還原映射未動。

## 既有來源唯讀核對

17 個既有 feature／rank 檔的 SHA256、原引擎與母體設定 SHA256 均保持前批 pins；DB 與 WAL 大小／mtime、SHM 大小不變，SHM mtime 已變化。基線沿前批已接受收據，不聲稱本批獨占正式 DB，也不把 SHM 變化歸因本批；完整 App audit 拒絕非隔離 SQLite，發布測試僅用小型 fixture DB。比較收據為 `source_before.json`／`source_after.json`／`source_comparison.json`；首次全 stat 相等斷言失敗保留，沒有修改實際來源湊相等。

App harness 因 Windows venv PID 差異補 token／親程序 marker 的自有 child timeout 收尾，必要單次重驗正常流程：case `app_startup_1791224297829135000`，launcher 37592／worker 35820，exit 0、九頁／worker 0／violations 空、6.484 秒；前一成功 case 仍保留。timeout 分支未以正常流程冒充實際故障驗收。

## 實際儲存診斷與中止收據

最終 CLI 使用既有 feature root、rank root 與前批四模式隔離 JSON ledger，未啟任何真實 publisher／learner：scan_complete true，17 檔／29 個 storage entries、33,714 bytes、1 feature manifest＋4 rank manifests、3 feature objects＋4 rank objects、4 v2 收藏／8 refs、temporary 0。未宣稱掌握正式所有清單，故省略 `--watchlist-inventory-complete`，references_complete false、候選 0、原因 `watchlist_inventory_completeness_unasserted`；這是預期保守拒絕，不是來源不合格或工程等待自然成熟。中央時點 reserve 20 GiB、capacity pass；單批 8 MiB＋1 真實 API 拒絕，writer 未啟動。自然 growth samples 不足，7／30／90 日 forecast 不提供。

收據 `output/qa/research_snapshot_storage_governance/ux19-real-existing-final.json`；省略清單來源另有 `ux19-no-watchlist.json`，不產生候選。explicit-completeness guard 加入前的 `ux19-real-existing-initial.json` 保留為初版診斷，不能當最終完整參照驗收。專項安全 fixtures 涵蓋完整 v1/v2、未知／錯 hash、超預算、只讀 SQLite、無全參照與 dry-run 不授權。

Feature／rank 各 objects-after、manifests-after、pointer-before／after 共 8 案，以自有小型 DB 與子程序注入故障。同根持鎖請求 busy；中止 writer 後父程序 reader 讀舊或完整新版本，舊 manifest／pinned artifact 保留，retry 正常或 unchanged。這是跨程序 writer→父 reader，並非另開 fresh reader PID。修後 `-k child_termination` 8 passed／3 deselected（13.27 秒），16 個 worker／launcher PID 均退出，returncode 15；8逐邊界 receipts／log hash／code pins 見 `focused_crash_retest_manifest.json`、`children/*.termination.json`。其餘 3 案及相關 compatibility 由根層驗證。

初輪 marker worker PID 與 Windows venv launcher PID 被 harness 誤判為相同，finally 提早中斷而留下 8 workers／8 launchers；已逐一按本次精確 marker、路徑與啟動時間核對，16 PID 全部退出，未操作其他程序。失敗／清理收據 `focused_tests.txt`、`first_absence_failure.txt`、`orphan_process_cleanup_receipt.json` 保留；不是產品 crash 或全回歸通過紀錄。helper 修正 ownership 與收尾後才接受上述 8 案，未降低產品來源／容量 guard。


## 最終限定驗證與提交基線

根層受影響九檔 `-k not child_termination`：95 passed／8 deselected（12.86 秒），8 故障案例依上列專項收據另列，共 103 個不同案例；storage agent 的 11 pass 已包含於 95，其他局部／首輪結果不加總。全域 mypy 784 source files、7 個 changed Python compile、金融精度／look-ahead guard 通過。產品 UI 未修改，不重跑前批已接受的 Workbench／validator 或全量回歸／效能。

初始基線 a466cced；使用者另一對話已提交 `39cc1ec01cf370ec05107f398979f5722f6989a6`（每日鏈容量／父子鎖／Paper），本批保留該提交及其文檔，不代做修正，不把它計入本批成果。整合測試的工作樹包含外部變動，中央 reserve 20 GiB 取實際介面；本批最終 commit 會以 39cc1ec 為父層，只提交 16 個 owner-confirmed 檔，不是全 repo add。未知 capture 不讀不動，QA raw／原唯一計畫仍 ignored；本地 commit／blob／status 收據另存同 QA 根目錄，未 push。

最終 harness 同版 normal-flow readback：case `app_startup_1791224904723230000`，launcher 33136／worker 33872，exit0、九頁／worker0／violations空、5.437秒；先前失敗與成功cases均保留。最後修改只補timeout錯誤處理後，以此必要readback核對 final script SHA；timeout分支仍未驗，沒有再跑原效能或publisher鏈。

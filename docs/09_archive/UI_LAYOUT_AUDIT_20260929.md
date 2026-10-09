# UI Layout Audit 2026-09-29

## 狀態與接受邊界

本報告記錄 2026-09-29 跨工作區版面修正及驗證。這是 UI presentation work；推薦、回測、金融計算、資料來源、持久化與寫入權限未在本切片改動。最新完整 Qt UI regression 為 567 passed／1 opt-in skipped；最新 MainWindow 整合矩陣六格全數通過，九個工作區皆已走訪，errors=0、coverage gaps=0，六個 child `faulthandler.log` 均為空。此前 per-view QObject controller 曾發生 native access violation；目前 app-owned dispatcher focused 測試及最新六格矩陣均未重現，但不能據此認定歷史 AV 的根因或永久修復已證實。

正式整合矩陣使用三種 logical viewport：預設 1400×800、一般桌面 1366×768，以及最大化可用尺寸模擬 2293×912；每種尺寸分別以 scale factor 1.0 與 1.5 執行。2293×912 來自 root 的唯讀 Windows screen inventory（available geometry 2293×912、DPR 1.5）；offscreen runner 以該 logical 尺寸模擬，不量測 Windows 原生視窗外框或實體螢幕邊界。1920×1080 不屬於這六格整合矩陣；若有該尺寸的 focused probe，僅作為定向補充證據記錄。每個 workspace／子頁／結果分頁要切換成 active 後，以至少六列合成資料、長文字與長警示確認可達；五列量測需檢查實際 viewport row rect、水平捲軸與首五列同時在 viewport 中，並檢查模擬中的 MainWindow frame geometry 不超出 logical available geometry。

## 盤點範圍

| 主工作區 | 巢狀頁面／內容範圍 |
| --- | --- |
| 決策工作台 | 總覽、決策來源、研究證據、持倉追蹤、操作節奏；包含 Decision Desk、Research Console 及 Evidence review 入口。 |
| 市場探索 | 市場總覽、大盤指數、強勢／弱勢個股、強勢／弱勢產業、主力流向；主力流向含個股資金流向與分點進出追蹤。 |
| 推薦分析 | 個人／進階參數、結果摘要、推薦表、個人決定與唯讀個人模型評估。 |
| 策略回測 | 研究模式、結果摘要／表格／診斷分頁，以及批次、最佳化、Walk-forward 與相關動態對話框。 |
| 觀察清單 | 候選列表、分析摘要、下一步與個股／行動表格。 |
| 個股研究 | StockResearchWorkspace、報告摘要與各 lazy report tabs、決策旅程及報告對話框。 |
| 持倉管理 | 交易歷史、覆盤日誌、聲明持倉研究、Paper Portfolio、情境壓力、策略與價格監控、生命週期回顧、籌碼監控。 |
| 數據更新 | 主狀態頁及全部 12 個 content stack source：總覽、每日資料、market、industry、broker branch、technical、monthly revenue、institutional flow、credit transaction、TDCC shareholding、scheduler status、SQLite Inspector。 |
| Runtime | 環境／任務狀態、operations、治理事件流與 session context。 |

QA runner 必須切換實際 active page，而非依 `isVisible()` 跳過隱藏分頁；SQLite Inspector、個股報告與回測的動態頁面亦要顯式覆蓋。新 geometry tests 與 runner 測試登錄於 `qa/full_app_healthcheck/test_inventory.py` 的 `ui-healthcheck-candidate-bridge`，不代表授權為 direct bridge。

## 呈現變更

- 共用 `layout_helpers` 提供可垂直／選配水平捲動的 scroll area、逐 view 計算 table/list 前五列高度的 helper，以及依 available geometry 限制並置中的 MainWindow 初始 geometry。helper 不全域更改 widget size policy，也不改表格模型資料。
- 金融 table style 為 table/list 保留至少五列 viewport；高度會讀取實際字體、row/header/frame 與水平 scrollbar，model／header／resize／show 變更後更新。
- MainWindow 的九個 workspace mapping／identity 保持原有 view widget 契約。個股報告、Runtime、Update、Workbench、Research Console、Evidence review、Decision journey、Watchlist、Portfolio 等頁面由自身可捲動內容承接長頁。
- Portfolio 頁將摘要、警示、動作、Paper health 與進階 tabs 放進一個整頁垂直 scroll area，保留 `portfolio_advanced_scroll` 公開屬性，避免只讓下半部捲動。
- Pandas-backed table cell 與 header 提供完整 formatted tooltip；可用水平 scrollbar 及拖曳欄位邊界查看長欄。Workbench 桌面寬版表格不再禁用水平捲動。
- 個股研究的連續性／個人選擇控制在窄版改直向排列；Runtime、Update 與 Watchlist 的長清單及多行控制保留可達性。

## 已完成的定向驗證

以下為已完成的 focused evidence，不等於完整 MainWindow audit：

| 範圍 | 命令／來源 | 結果 |
| --- | --- | --- |
| shared-layout 改動語法 | 對 shared helpers、MainWindow、相關 views/widgets、models、tests 與 inventory 執行 `py_compile` | 通過。 |
| Shared helper、wrapped lists、Research Console 與 Research Run Compare | `pytest tests/test_ui_qt_layout_helpers.py tests/test_ui_qt_wrapped_list_layout.py tests/test_ui_qt_research_console_view.py tests/test_ui_qt_run_registry_compare.py --basetemp=output/qa/ui_layout_20260929/shared_layout_helper_final_basetemp` | 34 passed。另以 `QT_SCALE_FACTOR=1.5` 重跑 wrapped-list 測試為 1 passed。測試先在空清單安裝 helper、再注入 6 個長項目，靠 model/layout 事件自動重算並以首五筆 `visualItemRect` 確認可見；移除手動 layout refresh 後等待 300ms，確認量測次數已穩定。正式 QSS/font 的 root probe 中，清單 minimum height 642、viewport height 640、第五筆 bottom 637；首個 200ms 量測 3 次、後續 200ms 量測 0 次，首五列完整落在 viewport。 |
| Portfolio presentation 與 lineage identity fixture | `pytest tests/test_ui_qt_portfolio_view.py --basetemp=output/qa/ui_layout_20260929/portfolio_full_basetemp` | 29 passed。測試 fixture 由 legacy DTO writer 建立完整來源 summary/hash，並驗證 hash mismatch 仍 fail closed。 |
| 聲明持倉研究五列表格 viewport | `pytest tests/test_ui_qt_user_declared_holding_research.py --basetemp=output/qa/ui_layout_20260929/userdeclared_basetemp` | 3 passed。自訂 row/header 高度後顯式重算五列最小 viewport。 |
| Decision continuity 與窄版 personal-choice controls | `pytest tests/test_ui_qt_decision_continuity_controls.py` | 4 passed。 |
| Latest full Qt UI regression（本輪來源） | root receipt：`output/qa/ui_layout_20260929/root_tests/ui_dispatcher_final.log`；收集全部 `tests/test_ui_qt_*.py`，不含 runner tests | 568 items：567 passed、1 opt-in skipped，243.53 秒，exit 0。Skip 為 `test_official_scheduled_result_renders_cjk_journey_screenshot_when_available`；`RUN_DECISION_OUTCOME_JOURNEY_REAL_SMOKE` 未啟用，因此沒有正式資料 smoke pass 主張。 |
| Update／Workbench UI regression | root receipt：`output/qa/ui_layout_20260929/root_tests/update_dispatcher_final.log`；`tests/test_ui_qt_update_view_workbench.py` | 85 passed。 |
| Update tab isolated QA | root receipt：`output/qa/ui_layout_20260929/root_tests/update_tab_dispatcher_final.log`；`scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped。Skip 未計為 pass；正式資料 download／merge 等 opt-in 操作未執行。 |
| Repository static checks | root receipts：`mypy_dispatcher_final.log`、45 changed Python files `py_compile` | 739 個 source files mypy 0 issues；45 個變更 Python 檔語法檢查通過。 |
| Visible rows dispatcher/state lifecycle regression（最新來源） | scale 1.0：`pytest tests/test_ui_qt_layout_helpers.py tests/test_ui_qt_wrapped_list_layout.py -q -o addopts= --basetemp=output/qa/ui_layout_20260929/dispatcher_final_scale1`；scale 1.5 同命令，basetemp=`dispatcher_final_scale15` | 各 10 passed。實際量測 table/list 前五列 viewport、CJK 換行長項目、resize/font 重新量測與 idle settle；model A→B 後舊 model 更新不再排程、新 model 更新仍重算；view DeferredDelete 會清掉排程且不回呼；8 個 view × 3 次 model swap 時 app dispatcher `QMetaObject.methodCount()` 固定。 |
| 最新 shared helper 靜態檢查 | `mypy ui_qt/widgets/layout_helpers.py`、helper 與兩個 focused Python tests 的 `py_compile`、`git diff --check` | mypy 1 檔 0 issues；3 個 Python 檔 `py_compile` 通過；無 whitespace errors。pytest 唯一 warning 是本機 `.pytest_cache` 寫入被拒，兩個 scale 的 20 個 focused tests 均通過。 |
| Test inventory machine refresh | `scripts/audit_test_inventory.py --skip-pytest-collection --output-json output/qa/ui_layout_20260929/test_inventory_audit_wrapped_lists_final.json` | overall passed；filesystem／registry 1069/1069、missing／stale 0/0、collection errors 0、documentation count drift 0。未執行 pytest collection，collected count 未知。 |

補充：Portfolio identity 測試最初的舊 fixture 只有 `result_id`、股票代碼與 `profile_id`，無法通過目前既有完整來源驗證。用 `git show HEAD:ui_qt/views/portfolio_view.py` 重建舊 view 的隔離 baseline，該舊 fixture 也失敗；此處同步測試 fixture，未放寬驗證邏輯。

## 最新整合驗收狀態

- 完整 Qt UI regression 的最新來源收據為 **567 passed／1 opt-in skipped**（568 items，243.53 秒，exit 0），涵蓋全部 `tests/test_ui_qt_*.py`；MainWindow runner tests 另以 **46 passed／0 skipped／0 warning** 驗收。Skip 是 `test_official_scheduled_result_renders_cjk_journey_screenshot_when_available`；`RUN_DECISION_OUTCOME_JOURNEY_REAL_SMOKE` 未啟用，沒有正式資料 smoke pass 主張。
- 最新 helper focused tests 在 scale 1.0 與 1.5 各 **10 passed**；更新窄版測試包含前五列實際 viewport rect、CJK 長行、resize/font、model replace 舊來源不再排程／新來源仍重算、DeferredDelete 後 queued work 被清除，以及 app dispatcher method count 穩定。`mypy` 739 個 source files 0 issues，45 個 changed Python files `py_compile` 通過；Update／Workbench 85 passed，isolated Update QA 25 passed／0 failed／4 skipped。
- 最終 MainWindow 整合矩陣收據 `output/qa/ui_layout_20260929/mainwindow_layout_final/summary.json` 為 `complete=true`、`status=passed`：1400×800、1366×768、2293×912 logical viewport × scale 1.0／1.5 共六格；每格都走訪九個 workspace，errors=0、coverage gaps=0。合計 54 次 workspace visits、1,488 次 page visits、1,308 次 table/list checks、834 次 scroll checks；每格涵蓋 248 個頁面／情境走訪（不是 248 個唯一頁面）與 13 個 scenario。六個 child `faulthandler.log` 均為 0 bytes；入口及捲到底截圖位於相同輸出樹的 `scale_1`／`scale_1_5` geometry process `screenshots` 子目錄。runner focused regression `tests/test_qa_validate_ui_layout.py` 為 **46 passed／0 skipped／0 warning**（`runner_layout_final.log`）；45 個 changed Python 檔 `py_compile` 通過。
- 較早的 `mainwindow_dispatcher_final` 曾在每個 scale 各有 22 筆 header／column-width restoration errors 及 3 筆 child-process exit errors；`mainwindow_accepted_complete` 曾有四筆空 Research Console fixture restoration errors。這些是已被後續 runner 修正與 `mainwindow_layout_final` 取代的中間診斷，不列入目前結果。
- 此處量測限於正式 theme 下的 Qt offscreen logical viewport；不代表 Windows 原生外框、OS 游標輸入或實體螢幕邊界。圖表 hover regression 以 `QApplication.sendEvent` 傳送 `QMouseEvent` 到 widget dispatcher。

## 歷史 native 與 runner 診斷（不屬於最新驗收收據）

在 per-view `QObject` controller 仍存在時，runner 曾多次記錄 native access violation：

| 歷史輸出 | 當時事件 |
| --- | --- |
| `mainwindow_final/scale_1` | default、compact 完成後，第三個 MainWindow（actual-max）建立 SmartMoneyTable 時於 `super(QObject)` 記錄 AV。 |
| `mainwindow_verified/scale_1_5` | compact case 在 StockResearch `_render_flows`／table helper 建構途中記錄 AV。 |
| `mainwindow_accepted/scale_1` | compact case 在 StockResearch `_render_price` 建表途中記錄 AV。 |
| `mainwindow_release_final/scale_1_5` | 移除 watchdog 後，compact 的 StockResearch `_render_price` 仍在 controller `QObject.__init__()` 無 parent 處重現 current-thread AV。 |
| `mainwindow_slots_final/scale_1_5` | 加入 explicit `@Slot` overload 後，no-watchdog compact 仍在 StockResearch `_render_price`／controller 建構路徑記錄 current-thread AV；Slot 候選沒有解決該觀察。 |
| `mainwindow_constructor_final/scale_1_5` | default 在 timeout 後有非 current-thread、檔案輸出交錯的 AV；events 已記錄九個 workspace 完成。這與 traceback dump 問題型態相似，但不能據此確診來源。 |

2 秒重複 faulthandler dump 的 A/B 在第九次 stack dump 後重現 native AV／segfault，events 有 472 筆並停在 StockResearch synthetic report 中途；無 watchdog 與 30 秒單次 dump 的 A/B 完成九個 workspace。runner owner 已移除 in-process traceback timer，但其餘 no-watchdog AV 歷史仍需保留。以 constructor ordering、slot registration、GC 時序做過的 probes 都沒有確證 C++ 根因；本機另記錄兩輪 448／669 組 GC start/stop 配對與 30 次 render／close／deleteLater 循環，均未重現問題。

最新 app-owned dispatcher/state focused tests 與 `mainwindow_layout_final` 六格均未再記錄 AV；此結果表示目前驗收範圍內未重現，不證明歷史 native AV 的精確根因，也不構成 Windows 原生視窗環境的永久修復證明。CPython issue [#116008](https://github.com/python/cpython/issues/116008) 與 [#140815](https://github.com/python/cpython/issues/140815) 有 traceback dump 相關 crash 討論，只作診斷參考。

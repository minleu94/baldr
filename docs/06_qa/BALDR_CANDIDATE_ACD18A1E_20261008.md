# 固定 acd18a1e 候選與接受範圍

## Frozen 專項最新狀態（2026-10-08）

QtTest 替代已限定修改本機 QA child，SHA `95244a5f2f2457ce9763fb7cf1988fca5635c704bb50b61a4797bc074d3b3af1`；使用 `QMouseEvent` 與 `QApplication.sendEvent` 投遞 press／release／double-click／release。中央獨立 `--event-self-test` exit 0，真實 QTableWidget 恰收到一次 `(0,0)` 雙擊；代理 compile exit 0，三處 QtTest 引用移除。沒有修改候選、產品 handler 或觸發 signal 代替事件。原失敗與前像／diff／log 保留在 `output/qa/f07_human_acceptance_draft_20261008_a/preimage_event_adapter/`。完整 EXE 旅程暫待 1,000 檔效能獨占窗口結束，這個 source Qt 自測不授 frozen／真人通過。

保留所有失敗封套。`attempt_20261008T195853Z_60d27b03aa6b` 已通過精確 PATH，因 CWD 位於 repo 被拒；新增 `C:/t` 的一次性 CWD 後，`attempt_20261008T200003Z_ea95a6ca2553` 揭示另一個互斥 QA 條件仍要求 CWD 等於 repo 內 runtime。控制器及 child 現改為精確比對本次非 repo CWD 的 device／inode／mode；資料與可寫 runtime 根不變，不授 CWD 寫入權限，保留 QA 目錄。

實際 controller 自測 exit 0，精確五段 PATH、缺段／多段／換序／traversal、repo 內 frozen 根及工作樹模組拒絕、Job ABI 與錯誤來源 pins 共 18 個結果通過；兩個 QA Python compile 通過。接續唯一 attempt `attempt_20261008T200624Z_32ae6e87635d` 通過環境、CWD、407 節點來源與 COW 前置核驗；child PID 41896 在 1.671 秒內 exit 1，錯誤為候選未打包 `PySide6.QtTest`。此錯誤發生於 Main 前，沒有 UI 驗收證據。

中央直接讀 child receipt，SHA `844751c4536d9841fe88c060186d493ff74297168e428d6669441297ad8b3432`；network／SQLite／subprocess／越界寫入計數均零，controller 起訖候選、來源及原 COW pins 一致。下一步只修 QA 的滑鼠事件投遞，以已打包 QtCore／QtGui／QtWidgets 的真實事件取代 QtTest；不得以 signal 或直接 handler 呼叫縮減 UI 旅程。完整 frozen 通過前不交付新版人工啟動入口。

候選由固定 `acd18a1efcc045951defc00b79167035b6ec6f2d` source archive建置，dirty=false；路徑 `dist/candidate_acd18a1efcc0_56943844/baldr/baldr.exe`。中央直接核EXE大小53,722,333 bytes、SHA256 `7249e63836da09e0e9bfb900fd900a8c142fac76dbd8381ddc75815112bb3ded`。

同版Python／EXE隔離probe終態exit0，收據 `output/qa/baldr_same_version_acd18a1efcc0_916a6a3a/same_version_receipt.json`，SHA `1026c3c2d60c46e610a86145491efe9c529f64cbf459e59c821af8a321d4ff77`，中央直接讀status=`passed_isolated_fixture`、正式市場DB未使用、provider網路未允許、真人未驗。launch、原journey／model／H20呈現fixture、Qt入口與無效設定拒絕在此probe範圍；不是原始H20、完整F07或全市場驗收。

source.zip SHA `d5f814add5fddf1eb012fef885e82b0281d89a7a858e665fc989925b47270b6f`，BUILD_INFO SHA `d9c20eefc2a79fbf0327ae178725ff0ecfbb719d1f273ca3b5f36dfccff9c032`；buildlog `output/packaging/build_acd18a1efcc0_56943844/pyinstaller.log`。舊候選及來源檔未覆寫。

包含已保存的來源選股解碼、價格收藏隱藏布局捲動與理由鍵盤閱讀。F07來源版真257 Main／新PID已通過，EXE專項仍待；不得把同版一般probe當F07 frozen旅程通過。不含後續f33c53e0的銷毀警告清理，亦不含施工中的MA全母體query與P01/F17投影接線；已保存MA evidence葉片是工程來源工具，不代表新MA條件已可使用。

下一接受點：固定EXE以保存的同份257來源、exact收藏、比較籃與非零scroll重開，核所有runtime模組origin來自frozen archive，source inventory與關閉收尾，再準備明示設定的ASCII啟動helper及真人驗收步驟。此候選目前不標完整補完完成，不改正式排程、正式資料或安裝位置。

F07 frozen 專項第一次 attempt `output/qa/f07_frozen_exe_bookmark_reopen_20261008_b/attempt_20261008T193732Z_b5e5bc8a3993` 在控制器的 Windows Job 設定失敗，trace 為 preflight 後 0.203 秒 `SetInformationJobObject` Errno 24，沒有 child_started 或應用旅程收據。懸停程序已清理；EXE、保存來源與原 COW pins 起訖相同。中文 stdout 的編碼錯誤是後續輸出問題，不是 EXE 旅程結果。

QA 控制器的 PriorityClass 原誤用指標大小，已依 [Microsoft 結構定義](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) 改為 DWORD。中央獨立 `--self-test` exit 0：Basic 結構 64 bytes、Extended 144 bytes、PriorityClass 4 bytes，空 Job 真實 SetInformation 成功；錯誤 EXE/source/COW pins 與非 frozen 模組來源拒絕測試亦通過。這僅授 QA 控制器修正，不授 frozen 應用旅程通過。後續應採新 attempt 並保留舊失敗，不改原來源。

新 attempt `attempt_20261008T194059Z_2a796d72a20a` 確實啟動 frozen child（PID 22464），child exit 1；中央直接讀 stderr，錯誤為 Main 匯入前的 PATH 環境比對，不是 UI 旅程失敗。該 buildlog 第 858 行包含 `pyi_rth_pyside6.py`；現有固定環境的 PyInstaller runtime hook 第 50–53 行會在 Windows 將 `sys._MEIPASS` 加到 PATH 前方。下一步須以固定 EXE 的有界環境 probe 實測，僅接受精確 frozen prefix 加原系統 PATH 的已證明轉換，不能跳過 PATH 檢查。來源與 COW 保留；此 attempt 不授 F07 通過。

中央靜態審核另找到 origin 檢查的互斥假設：此固定候選位於 repo/dist，正確 `_MEIPASS` 本身亦在 repo 下；不可同時要求模組在 `_MEIPASS` 內且不在整個 repo 內。重試前須以固定 EXE 的精確 `_MEIPASS` 為唯一 frozen 允許根，拒絕其他工作樹模組與 sys.path，不能廣泛允許 dist 或移除來源檢查。需先補「候選在 repo 內仍接受」、「工作樹 ui_qt 被拒絕」及 traversal 反例；此項目前為 QA 修正要求，尚非通過證據。

環境 diagnostic attempt `20261008T194634Z_3152679a2a87` 由代理回報精確五段 PATH 為 `_MEIPASS/PySide6`、`_MEIPASS`、`_MEIPASS/pywin32_system32`、System32、SystemRoot，尚待中央讀原收據。中央已直接檢查固定建置環境來源：`PySide6/__init__.py` 第 74–77 行加入套件目錄；`PyInstaller/hooks/rthooks/pyi_rth_pyside6.py` 第 50–53 行加入 `_MEIPASS`；`PyInstaller/loader/pyimod04_pywin32.py` 第 51–56 行加入 `pywin32_system32`。重試合約應採此精確順序，增加額外路徑、缺段、順序替換的拒絕自測，不廣泛允許任意 frozen 子目錄。環境診斷不代替 Main 收藏旅程。

中央補驗已完成：原收據位於 `output/qa/f07_frozen_exe_path_env_diagnostic_20261008_a/attempt_20261008T194634Z_3152679a2a87/diagnostic_receipt.json`，SHA `F373E1727DAC82679AD23E91ACEFDD23319B5B5F6AFD72571BB083E52486B28C`；status diagnostic_completed、child exit 0、1.203 秒。中央依固定候選路徑重算三個 prefix 字串 SHA，逐項與原 child stdout 相符，兩段系統 tail 亦相符；總數恰為五段。網路／SQLite／子程序／越界寫入計數皆 0，Main 未載入。此證據接受精確環境轉換；原 probe 的單 prefix 布林仍 false，不改寫原收據。origin 與五段 PATH 的正反例通過後才授權新的單次旅程。

中央最新 frozen attempt `20261008T204457Z_39088d9d4967` 已進真正 Main，觀察清單雙擊還原保存的 257 股來源、第 6 頁、S0250、跨頁比較與捲動值 2；SQLite 拒絕為 0，僅三次 case-local runtime 連線。整體仍 exit 1：QA 錯以 producer 模組載入判斷產製器執行，並攔到 urllib3 匯入時的 IPv6 能力探測。原 network 拒絕計數 1 必須保留；不能放行 socket 或清除事件來換通過。候選、原 COW 與合成來源 pins 起訖不變。下一步是審核精確產製入口執行防護與已拒絕依賴探測的分類，不授 frozen 完整接受。

原 H20 摘要接線的來源核對：固定 source.zip 與工作樹的 `ui_qt/main.py`、`stock_research_report_view.py` 位元組一致；`stock_research_workspace.py` 正規化行尾後內容一致，位元組差異僅行尾，未因此改寫來源或 archive。中央新隔離測試 `test_ui_qt_personal_h20_workspace_panel.py` 與 `test_stock_research_product_summary.py` 共 15 passed（2.60 秒），basetemp `output/qa/h20_summary_root_review_20261008_a`。這證明摘要契約及 UI 投影，不證明原來源等待時間、frozen 原 H20 下鑽或真人可讀性；新啟動 helper 的 gate 仍關閉。

窄視窗來源版視覺補驗：`test_ui_qt_recommendation_layout.py` 的完整分數表／文件末段及展開理由兩個案例通過（2 passed、7 deselected，3.02 秒）。中央實際讀取 `output/qa/recommendation_visual_root_20261008_a/recommendation_full_document_end_460x700.png` 與 `recommendation_800x700_personal_history.png`：理由末段可捲至結果 viewport，保存版本／歷史／回退與 DB 選擇控制項各自佔完整列，沒有原回報的垂直擠壓。畫面為合成來源版，仍有整頁捲動；不授 frozen 原資料或真人驗收，不將 offscreen 畫面冒充真人操作結果。

中央整合精確產製入口 wrapper 與 PYZ code 核對：helper SHA `70ceb4d46f32664115ad838084f55624e3fd47643690271fdd02cca63781a8d0`，中央獨立合成自測 36/36 通過。碼身份納入 exception table、stack size、frozenset 等常數；來源 bytes 由固定 source.zip 六個精確成員取得，依賴 bytes 核固定 SHA。urllib3 匯入先探測再發布版本的順序明列為 pending，終態仍要求同一 package/module 身份及版本 2.6.2。socket 拒絕總數不清除。

新 frozen attempt `20261008T213104Z_52b9c71cc78b`（session60817）exit1，child receipt SHA `4de549ccea5af60b3ffe8aefd499bd00597ff2a1864491a3ac6c532fb5da66a8`。真正 Main 再次還原完整 257 股、查詢／第 6 頁／S0250／跨頁 basket／捲動，兩個 from-import alias 已核 wrapper、產製入口嘗試0；8.453 秒完成 Main 關閉且 workers0。network 拒絕仍1，其他三類0；唯一分類缺件為 `dependency_loader_origin_mismatch`，涉及 CArchive bootstrap 的 `pyimod02_importers`，不能套用 PYZ 模組的 spec/file 假設。候選、archive、原 COW、合成來源及 helper/source pins 起訖一致；整體未通過，不交付真人入口。下一步只核實該 bootstrap metadata 並補相應反例，不放行 socket 或改寫來源。

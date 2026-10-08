# 固定 acd18a1e 候選與接受範圍

## Frozen 專項最新狀態（2026-10-08）

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

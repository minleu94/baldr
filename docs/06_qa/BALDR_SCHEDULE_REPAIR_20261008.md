# 2026-10-08 自然排程故障修正與驗證

## 文件 Coverage Pass

| 文件 | 優先級 | 更新內容 |
|---|---|---|
| 本 QA | Must | 原始失敗、實際套用、隔離驗證、未解除阻擋與回復 |
| APPLICATION_MANUAL.md | Must | 維運入口、操作、參數、判讀、安全限制與排錯 |
| scripts/scheduled/README.md | Must | 背景 launcher、套用與重新註冊注意事項 |
| PROJECT_SNAPSHOT.md／DOCUMENTATION_INDEX.md | Must | 有限交付狀態與本 QA 導航 |

Scoped SSOT：本次修復既有排程與來源選取，不改 Roadmap、產品 Gate、架構領域邊界、容量政策、歷史 PIT／formal 資格。原始資料、Paper ledger、舊 receipt 均未覆寫；未手動啟動正式 Task、producer、fit 或 broker action。

## 已確認的自然結果

原始 status 路徑、SHA、mtime 與精簡投影：`output/qa/schedule_repair_20261008_initial.json`（17:10 UTC／10:10 PDT）。06:26 的 heartbeat 等待不是成功；後來 terminal 如下。

- Bank 05:50：`upstream_running_status_mtime_too_late_for_task_start`。G9 running status 會更新 heartbeat，mtime 不應被限制在 Task 起始後 30 秒內。
- G9 05:45：06:41 結束，等待 G6 的有效額度只有 3300 秒；G6 child 06:51 完成，已晚於 06:40 deadline。G6 外層另為 `skipped_locked / direct_chain_maintenance_is_running`，因此只延長等待不能保證 G9 通過。
- G6 同 run 研究 child 已有 completed terminal，但正式 raw 階段未執行；consumer 目前正確拒絕外層 `skipped_locked`。沒有把 child 成功改算 formal 成功，也沒有擴大允許 skipped status。
- Decision Capture：06:53 為 degraded，`snapshot_cli_timeout`、`snapshot_json_invalid`。stderr 停在 watchlist trigger 查詢；原查詢對日期欄位 REPLACE 導致全表掃描。
- Forward：06:53 為 blocked，`outcome_price_missing`；1538 的 H5 2026-09-17 與 H10 2026-09-24 缺價格。這次已越過原共用鎖等待，但缺價未補造。
- Direct 10:00，以及前晚 Paper Portfolio／Sector／ML Allocation：Scheduler 結果為 `0xC000013A`，Paper 缺 terminal。沒有可用 Operational 歷史事件，不能據此斷言是使用者關窗、重開機或同一來源中止。

## 程式修正與實際套用

1. Bank 移除錯誤的 running status mtime 上限。仍核對 Task／日期／root、run_id 起始時間 30 秒綁定、未來時間、stale、no-follow 與重讀穩定性；不是允許任意晚啟動 run。
2. Paper queue 先驗證固定決策來源身份，再以該 `created_at` 選 sector archive。原 10/08 收據的 freeze 是 10/07 12:10:51 UTC，唯讀解析選到 10/06 已保存 archive，避免 EOD 挑到決策後的新 archive。producer 原 hash／clock／coverage 驗證保留。
3. 已 blocked 的 Paper result 不再嘗試綁 fills。對舊收據，僅既有 late-archive 非 retryable 政策、完整 queue/source/candidate 驗證且伴隨精確 `Paper result fills missing` 次生原因時，允許收據離開重試屏障；不補歷史、不寫 fill。原收據 SHA `d80a3d0d21a9de9c765c56552496cff86eafb10f729c3ab62de3f9ac68f90342` 不變。回讀見 `schedule_repair_20261008_readback.json`。
4. G9 CMD 總 timeout 預設從 10800 改為 14400 秒，保留兩個 child 各 3600 秒與 flush／wait cap；擴大可用等待額度。不是 G6 `skipped_locked` 的修復或來源資格放寬。
5. Watchlist 日期讀取先走既有日期索引，支援 compact／ISO／斜線日期，七日內未找到才保留原長區間 fallback。日期始終不超過決策日；公式與金融數值未變。真實唯讀 1955／1961 列查詢約 79ms。
6. 四個既有 Windows Task action 已實際改為既有 pythonw 啟動 `run_scheduled_cmd_hidden.py`，child CMD 使用 CREATE_NO_WINDOW。每次有 stdout／stderr、started／terminal 收據；只記執行結束，不宣稱 pipeline 成功。限定 Direct、Paper Portfolio、Sector、ML Allocation Forward 四個固定入口。

Task 套用備份：`output/qa/schedule_hidden_launcher_20261008T1726139894070Z`。四份 `update.json` 皆確認 OnlyActionChanged、AclPreserved，LastRun 前後相同、TaskManuallyStarted=false；trigger、principal、settings 保留。背景執行減少可見 CMD 被關閉的機會，不能證明過去中止原因，也不能保證 OS 強制終止時寫得出 terminal。

## 驗證

最終證據 SHA 與有限交付狀態：`output/qa/schedule_repair_20261008_final_summary.json`。17:38 UTC 的最終 Task 回讀為四個背景 action、LastRun 保留、Operational disabled。

- 七組主要回歸：**262 passed、4 skipped**，16.56 秒，`output/qa/schedule_repair_20261008_verified_pytest.xml`。
- 背景 launcher／中止收據／watchlist 針對測試：**16 passed**，3.25 秒，`schedule_repair_20261008_launcher_verified_pytest.xml`。與主要回歸有重疊，不相加成唯一測試數。
- Bank、Paper producer／isolated、watchlist、hidden launcher 五個 production Python 檔 mypy 通過；py_compile 與量化 guard 通過。無 UI 變更。
- 完整 Decision CLI 使用真正目前時鐘、`diagnostic_research`、dry-run、不保存，在原設定根約 **38,813ms** 完成、exit 0、sections_missing=[]、watchlist_trigger=3。`schedule_repair_20261008_decision_default_root.json` 明示 saved=false、natural_authority=false、preopen_authority=false、quality=degraded。這是效能與完整輸出驗證，不是重跑 10/08 正式排程。
- 首次 sandbox no-follow fixture WinError 5；首次 host TEMP 選錯位置，另有測試插入位置錯誤造成 NameError，均保留失敗 JUnit。修正測試位置並以短且位於 TEMP 下的隔離 fixture 重驗後得到上述最終數字。
- 首次事件 action DryRun 被自動審查拒絕，理由是尚不能確認無 RegisterTask mutation。新增明示 Apply 防線並保存 static proof 後，同一 DryRun 與正式 Apply 均獲准；沒有繞過審查。

## 尚未通過的項目與必要操作

- Scheduler Operational 仍 disabled。普通 host shell 為 Windows Access denied；其後 RunAs UAC 被取消，沒有管理員成功收據。`scripts/scheduled/enable_scheduler_event_log.ps1` 已完成，只啟用指定日誌、不清除、不改 Task、不觸發工作；須在管理員 PowerShell 執行。未能補回過去不存在的事件。
- 新背景 action 尚待下一次自然 run 驗收；要比對 launcher child exit、內部 terminal、來源／consumer pins，不能只看 Task return 0。
- G6 formal lock blocker、Forward 缺價、原 ML Allocation source revision quarantine／release blocker仍保留。G6 completed child 不等同可供目前 G9 正式消費；需下一 run 避開仍活著的 Direct，或另行受控調整研究 consumer 契約並完整驗證，不以本輪已修好其他缺陷掩蓋。
- 沒有歷史 capture 時，不回填 clock 或 manifest。下一個真實日的 Paper queue／開盤／EOD／consumer 全鏈仍須完成自然驗收。

## 操作與回復

背景 action 核對入口：`update_interrupted_tasks_hidden_launcher.ps1 -Mode DryRun`；`-Mode Apply` 只更新固定四個既有且非 Running Task。若重新執行總註冊器恢復原 CMD action，須再次 DryRun 核對及 Apply。本輪沒有修改總註冊器的所有 action 預設。

回復 Task 必須使用上述各 task 的 before.xml／before.sddl，先確認非 Running，僅 UPDATE 且不觸發 registration trigger，回讀 XML／ACL／LastRun。不要刪除 Task、鎖檔、queue、receipt 或 quarantine。程式修復的預像保存於 `output/qa/schedule_repair_20261008_preimage`；工作區有其他未提交變更，不能用整個 git reset 作回復。事件日誌若日後需停用，同樣需要管理員，只設 `/e:false`，不清除事件。

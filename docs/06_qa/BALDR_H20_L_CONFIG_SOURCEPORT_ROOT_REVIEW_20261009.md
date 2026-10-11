# H20 L 設定入口純測審查

Root 實讀 L `config_sourceport_selftest_01.log`、`config_sourceport_selftest_02_native.log`、actual `_configuration_source_port_selftest` 與固定來源 `_source_port`。01 在模組 resolve 時遭 WinError 5；02 已到真正 `_source_port`，但失敗，不能作為設定契約通過證據。

## 已確認缺陷與修正要求

1. `preverified_terminal_reader` 的 `type(path) is not Path` 在 Windows 必定拒絕真正 `Path(...)` 建立的 WindowsPath。應比較 exact platform Path type 或 exact `type(cycle_path)`，保留固定 terminal path、SHA、來源函式、globals、initial/terminal phase 與一次性限制，不允許子類借資格。
2. 真正 TWStockConfig 的 FileHandler 開啟 config.log 遭 `file_write_outside_exact_allowlist:open` 阻擋，退回 console-only。因此 log handler count 與 exact output-tree postflight 也失敗。需核對真正 `_setup_logging` call chain、open audit args 與私有 log 路徑的精確許可，不能忽略缺件或把 console-only 改判通過。

02 原始結果報 `config_source_port_terminal_read_seam_denied`、`selftest_complete=false`、`status=failed`；SQL connections 為 0、source unchanged 為 true。這表示測試 seam 尚不正確，不能推導原 H20 來源缺件或資料損壞。保留失敗封套，修正後使用新 attempt，仍先證明 actual source-port 初次／終端兩個 config instances、第三次／foreign 拒絕與 logger/environment finally 還原；尚未授權 L 完整 pipeline 或 Main 驗收。

## Attempt 04 有限範圍接受

Root 直接讀取 `config_sourceport_selftest_04_native.log` 與 exit 檔並獨立重算 SHA：exit 0；child SHA256 `9b543016640c849e1899cbf50548ae90e503ca78857dfd17f813318c33943754`，log SHA256 `be284701b3777b2a8a5910e7e088aaf7521cc795b91cf0f845c056d4e5ee290a`。actual `_source_port` 初次／終端各建立不同的 TWStockConfig，24 次既有目錄 noop、一次精確私有 config.log open。Root 讀取 log guard 的完整 caller chain、flags、append mode、absent target 與 phase 條件；沒有允許任意 mkdir 或 log 寫入。

收據包含第三次無 session 呼叫的 12 個目錄拒絕、terminal-reader phase 拒絕、application_state 直接 mkdir 拒絕；source/fixture/H20 group 起訖相同，SQLite/source SQLite 為 0，logger cleanup errors 為空，環境／aliases／Python state 還原，selftest_complete=true。原 hostname 1 次及外部 os.open 3 次拒絕仍保留，未放行或清除。

Root 已允許更新 runner exact child pin、保存 K→L final diff/freeze 及此 pure receipt pins。完整公共 pipeline 仍須核對固定封套與這四個拒絕事件在實際執行 gate 的處置後另行執行；不得以這個 loader 前 sentinel 純測代替 SQLite／cohort pipeline 或 Main 通過。01–03 失敗封套保留。

## L 完整公共 pipeline 失敗

凍結 L 的唯一完整執行已終態失敗，未重跑。Root 直接讀取 `C:/t/h20_h9_public_cohort_pipeline_20261009_l/cohort_diagnostic_receipt.json`：initial 原因為 `os_open_callsite_or_target_denied:os.open`，terminal 為 `personal_h20_source_binding_changed_before_terminal_read`；兩個 cohort 均 unknown，不能宣告 H20 可用。來源、fixture、H20 group、設定目錄與環境起訖一致；SQL 連線為零。五個拒絕事件保留，不能把純測通過解讀成完整流程通過。

固定 `_source_port` 在建立 config 後，以 `read_pinned_json` 開啟固定 cycle terminal JSON；L 的 os.open 許可缺少此角色。原事件沒有 caller/path，因此尚不能將四次 os.open 拒絕逐一歸因。下一個 M 僅準備有界 caller／fixture-role 診斷及精確 terminal JSON 讀取切片純測；不放行泛目錄、不清計數，也尚未授權 M 完整 pipeline 或 Main。

Root 直接補讀 controller 的實際清理欄位：`child_exit_code=1`、`elapsed_seconds=5.516`、`timeout_reached=false`、`job_owned_process_ids_before_cleanup=[3616]`、after 為空、`job_empty_proven=true`、`job_closed=true`、`cleanup_errors=[]`。失敗程序已清理，沒有以其他欄位不存在或程序清單推測終態。

### M 新 slice 測試入口核對

Root 接續讀回 native_05／06／07 原始 stderr。05 與 06 均未通過 context-exit fault 注入；06 的報告顯示 primary_type=None、phase 判定累計 15 次、stream／descriptor 已關且 active_descriptors=0，但預期拒絕未觸發。07 改為逐案標記後，仍只記錄 fixed_capture_reader 標籤，未命中 reader_context_exit，不能宣稱窄 slice 通過。owner 接續改用實際呼叫者 code 身分分辨 enter／read／exit，不依賴第 N 次呼叫。mock phase 資源清理證據仍須與固定 source-port 的實際 initial／terminal 呼叫鏈分開；沒有擴大 public pipeline／Main 的執行範圍。

Root實讀 cycle_terminal_slice_native_01／02 原始logs：01在module Path.resolve遭sandbox Win5；02仍從完整run進舊diagnostic contract，因mockguard缺_cycle_terminal_file而AttributeError，未到新slice。兩者不得視為新的產品讀取失敗或slice驗證。已要求owner建立獨立slice入口與完整guard fixture，避免重跑已接受04或逐欄補mock。新resource cleanup contract明示mockphase、實際fd/stream清理；這只能證明資源清理，實際fixed source-port初讀／終讀呼叫鏈與許可正例仍須分開驗證。仍未授權public pipeline/Main。

## 後續 M7 固定來源 Main 路徑註記（2026-10-10）

其後 M7 另有固定來源 S4 Main receipt 成功，但未把此文件 L attempt 的 pipeline failure 改判通過。M7 receipt 證明一條 bounded Main route；本 L 文件記錄的 `os.open`／terminal-read seam、L 完整 pipeline 失敗與後續 M diagnostic slice 仍按各自 candidate identity 判讀。M7 receipt 未以此 L attempt／診斷封套作接受依據；詳情見 F03 root follow-up M7 段。不得將另一條 Main route 回填成 L candidate 的 caller／許可驗收。

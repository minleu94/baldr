# F02 m 守衛修正：Root 審查與母體執行邊界

Root 已對照 l 的獨立審查、m 原始碼的固定大小上限與 runtime binding 檢查，以及 native guard-only 的完整 stdout/terminal。m 候選 SHA-256 為 `50f425cfc9b597cc9db18c860f2bc93310aa7b2c438a8c1113361678f91428d9`，位於 `output/qa/f02_ma_composite_257_acceptance_20261009_m/`。

## 守衛實際證據

- native guard-only exit 0，41 個 qualification checks 通過。
- supervisor 4/8 MiB 與 bundle writer 64/8/4 MiB 上限改為來源綁定的精確整數常值；註冊前後的上限變更、bool、registration 與 globals 同時變更皆拒絕，finally 後還原。
- 7 個 helper/method/code/globals 身分變更案例拒絕；path-only 案例保留正確 writer local，只改 reader path 引數並被拒絕。
- 16 個直接 reader/context 負例與 9 個固定 writer 至 reader 的注入負例共 25 個預期拒絕，不能計為非預期違規。
- 真 manifest 發布路徑 396 字元，發布後 nlink 2、核驗清理後 nlink 1；fixture fdopen issued/consumed/audit 各 10，pending 0。
- source pins 與本次合成 DB 起訖不變。僅兩次空合成 DB 的唯讀 scope 驗證連線，producer/worker 0；不代表完整母體已通過。

原始 receipt SHA-256 為 `f89b9d6836220bc3dfdefd26b4af5706256fc7afebcff8740462ab69608c60c4`。`py_compile` 通過；整份 QA supervisor 的 mypy **未通過**（163 errors），其中 name-defined/possibly-undefined 為 0。這不是產品完整 mypy gate 通過。

## 完整母體執行前核對

Root 重新計算 `full257_prelaunch_plan.json` 所列十項來源 SHA，全部符合；確認 `C:/t/f02_m_full257_20261009_5d19` 不存在。計畫 SHA-256 為 `11394080cdc22eea993c51ee7decb4497292eedaf33a69ae5fd4abc64ed95be1`。

已授權 owner 在原生隔離環境只執行一次 exact m supervisor `--run`，沿原 1200 秒 deadline、20 秒 cleanup 與 4 MiB log 上限。固定 oracle 的母體為 259 declared、258 included、1 excluded；included 中 1 檔來源缺件必須保持已處理且未知，不能偽造價格或當作尚未處理。

完整 producer、AND/OR 政策、集合、排序與逐頁結果仍須由該次執行證明。這份文件不宣告 1,000 檔效能、完整 UI、EXE、真人或整個補完計畫完成。

## 實際啟動結果與 n 路由修正

m 的完整執行在產製前以 `existing_attempt_requires_manual_review` 終止：固定 target 所在 QA 目錄已有 `attempt_ac55bdc7780b4a26/`。原 attempt 保留，未刪除或繞過拒絕條件。

n 只改 supervisor 的 `TARGET_PATH` 一行，指向同層深度、同 bytes 的全新 target-only 目錄；supervisor SHA 為 `0341bc084476fefab58adbe07388bc23412028c5d5b6572f76eeed513b74ad04`，target SHA 仍為 `ca8663ad43dc3c83e4132ec740ca6d7fad84c38197dfa65a4763c31eda3f485b`。沒有改 guard、producer 或 oracle。n 第一次啟動指定尚不存在的 private parent，在建立 outer attempt 前以 `required_path_component_missing` 終止；失敗封套與原計畫均保留。

Root 直接閱讀 `_new_outer_root`，確認 parent 必須存在，實際工作根由 `os.mkdir` 排他建立 `f02_ma_composite_257_v4_<12hex>` 子目錄。已授權依新 `full257_prelaunch_plan_parent_C_t.json` 使用既存 `C:/t` 作 parent，只執行一次原生隔離測試；此參數不把整個 `C:/t` 開放為產品寫入範圍。新的計畫列出十項來源 pins、parent 身分、target-only inventory 與原 deadline/cleanup 上限。此處仍未宣告完整母體通過，必須另讀實際終態與 oracle 結果。

### n 既存 parent 執行的實際失敗

Root 重算新計畫十項來源 pins 均符合，計畫 SHA 為 `e56bba33bb20816705dfaaf92fb5bc07ea25474aed2b08a5830f5d5949f9a486`。實際 outer attempt 為 `C:/t/f02_ma_composite_257_v4_7814c803bcb2`，owner 同一 handle 46956 終態 exit 1。

Root 實讀 `supervisor_receipt.json` 與 `worker.stderr.log` 的原始 worker marker：status failed，fixture_creation 階段的 `bundle_create_failed`，第一個 guard denial 是 `bundle_link_writer_runtime_binding_changed`（1 次，detail 空）。尚未完成母體 oracle/composite；不得當作 AND/OR、排序或逐頁通過。Job 清理證據為 `empty_before_close`、job closed、zero owned processes proven；supervisor/target 起訖 pins 相等。下一步需定位哪個 runtime binding 在真 writer 路徑被拒絕，保留此失敗封套，不直接移除守衛或重啟原 attempt。

## p 診斷版本的實際母體失敗

Root 實讀 p 固定 writer seam：43 個 qualification checks 全通過，25 項預期拒絕，producer/worker 0，來源起訖一致；helper 失配測試記錄 inner `os_module_identity` 與 outer `path_helper_runtime_binding_matches`，finally 還原後 runtime true。完整母體計畫 SHA 為 `ca805474a1bd4921bd35f12867e09e4b9e9d17f9f9e40ab8ff958d93490318e1`，Root 重算十個來源 pins、確認 target-only 新目錄單檔與隔離 parent 後授權一次執行。

實際 outer root `C:/t/f02_ma_composite_257_v4_c9aa2cc65e05` 的原始 receipt/worker marker 顯示 failed、worker returncode 1、Job empty 且 closed。仍在 fixture_creation，未完成 oracle；具名診斷這次明確指出 `bundle_read_guard.module_registry_identity` 失配，actual/expected 都是 module、identity false，caller 為固定 writer `_publish_objects`。

Root 直接核對 supervisor `_run_fixed_target`：`runpy.run_path(..., run_name="__main__")`；固定 target 尾端以空 argv 呼叫 `_run_case()`。已要求 owner 在新候選以穩定具名 target 模組及核驗後的真正 `_run_case` 入口執行，保持 supervisor registry 與完整來源／code／globals 身分核驗，不修改 target bytes，也不刪除 module identity check。先驗真正 launcher 至 writer 的最小 seam，再核新的完整母體計畫；p 失敗封套保留。
## q 候選清理流程審查與 r 完整矩陣追蹤（2026-10-09）

## r 終態與長路徑診斷

下一切片已授權建立 `query_continuation_only` 新候選，尚未執行：精確重用既有 complete 合成 store 與兩份原 source pointers，以真正 public readers 取得 typed pins、真正 BundleWriter 寫新隔離 bundle，再跑原全母體 Decimal oracle／AND-OR／unknown／排序／分頁。原 DB／store／captures／failed receipt 只讀，新 scope 僅新 attempt 可寫；runner／supervisor 差異、oracle AST 等值、完整 pins、deadline／Job／FD／hardlink 守衛均須先審。此切片不重產、不改原 full status，也不替代 1,000 檔效能驗收。

原生環境對照 002 已 exit 0。Root 實讀收據／原始 stdout：read_exact **success，5.606616 秒**，宣告 259／納入 258／排除 1／處理 258／pending 0／缺資料 1，11 項 unchanged 全 true。副本僅 REPORT_PATH 常值不同（SHA `647abc13...508a14c1`），新 report SHA `06307284...94b19fb`；001 sandbox 失敗完整保留。結果證明相同保存 store 在原生 context 可重開，並不定位原 fixture_creation WinError 3；下一步需具 traceback 的新 QA-only 版本或明示重用 complete 合成 store 的完整矩陣 continuation，保持真 public reader／writer／query／獨立 oracle 與 guard。原 full run 不改稱成功。

證據補全 001 已終態 exit 1。Root 重算凍結 diagnostic／preflight SHA、27 pins 無失配並實讀新收據：public read_exact 在 segment 1 的 extended child manifest 路徑得到 PermissionError／WinError 5，所有 11 項 source／DB／store／segments／原 failed receipt 起訖比較均 true；沒有 producer 或 SQLite connection。此為 sandbox context 的唯讀失敗，不能與較早成功重開合併宣稱穩定產品缺陷。下一步新 native 收據只允許副本改 exclusive REPORT_PATH 常值，先核差異與 pins 再執行；不更動 strict realpath 或來源 guards。原 001 封套保留。

Owner 最新有效 public StoreReader exact 重開成功（5.704 秒）：宣告 259、納入 258、排除 1、處理 258、pending 0、缺資料 1，terminal store receipt 是 complete。此前 raw plan read 與漏掉 research_snapshots/full-technical-store 的 output_root 均屬診斷命令錯誤，不能當產品缺陷。完整重開不重現 WinError 5；仍須實讀新收據與定位原 fixture_creation 的普通 generation path API。保存完整不代表原 full run 或剩餘 AND／OR／排序／逐頁 oracle 已通過。

後續核對更新：Owner 對同一長度 manifest 再驗 extended strict realpath 及 handle final path 均成功，單一 segment parent reader exact 重開亦成功。前述 WinError 5 並非已證明可穩定重現的超長路徑缺陷；必須區分實際 path、guard 與 sandbox/native 執行上下文。Root 已授權一次完整 public StoreReader 唯讀重開以保存真正 traceback／pins，不先修改產品，也不重跑 producer。

同一 session 23324 已終態 exit 1，target receipt 為 failed／fixture_creation，原錯誤是 generation directory 的 WinError 3；尚未跑完 oracle，不能視為母體通過。原 receipt 沒有 traceback。Owner 後續對同份失敗合成 store 做唯讀 public read_exact 重開，另定位 550 字元 batch manifest 在 `_resolve_path` 的 extended `os.path.realpath(..., strict=True)` 遇 WinError 5；這是後續診斷的 callsite，不能冒稱原始失敗的 stack。Store 六檔 inventory 與 synthetic DB 起訖 SHA 一致。

已交 owner 評估保留 strict canonical／reparse 驗證的最小修正與 bounded 原始 callsite 診斷；不得直接降成 strict=False、縮短 QA 路徑掩蓋問題、移除守衛或未經審查再跑完整 producer。此項仍可推進，不需要真人補件。

## r 完整矩陣啟動時核驗（其後已終態）

以下是 owner 啟動完整矩陣時的觀察快照；當時 target receipt 為 `running/fixture_creation`，尚無終態。後續同一 session `23324` 以 exit 1 結束，target receipt 為 failed／fixture_creation，generation directory 發生 WinError 3；該次未完成 oracle，不能視為母體通過。終態與後續唯讀診斷詳見上方「r 終態與長路徑診斷」。外層收據依設計保存在 C:/t，不在 supervisor 原始碼 QA 目錄。

Root 已讀 r 計畫與 source manifest（SHA `1bf21b473deea24e8469f4a0866ff104911c6f4db955951e83dc9fb2ed18c973`），獨立重算 27 筆來源／runtime pins，失配為 0；r target 只有固定 script，C:/t 是普通既有目錄。q→r 只有 TARGET_PATH 目錄字串差異，target bytes 未改。已授權 owner 依固定 argv 執行一次完整矩陣；來源 direct-import pins 需前後獨立比對，終態依原 oracle、原守衛及 Job empty／closed／zero-owned 證據驗收。此段僅是啟動前放行，不代表完整矩陣已通過。

q 後續已修正 target argv 與 supervisor argv 的比較。Root 實讀唯一 native 自測的原 JSON、terminal exit 0 及 SHA `09ad4de8ea71a711f63af3fba0f09de577e44a939b70f0c39d686fecb7e7e0f6`，確認真固定 writer 在 runpy __main__ 路徑以 `bundle_read_guard/module_registry_identity` 拒絕、候選 nlink=1／既有目的檔不變；stable alias 路徑成功 readback、移除自身 alias 並還原 argv／保留 supervisor __main__。primary／foreign alias／argv 漂移負例也通過；producer、SQLite 及 worker 均為 0。凍結 q SHA `9f0d18a2c5de9fc73717a91ad6312a7f4fe769100af9f110872ad13b340a9b7c`，其 p→q 差異已讀取。接受的是 writer/loader seam；完整 257 矩陣仍需新唯一 target routing 計畫及執行證據。

Root 讀取 q 候選的 `_cleanup_named_target_import`，確認它已保存 primary exception、外來 alias 並恢復 argv，但發現正常目標執行刻意設定的 `[TARGET_PATH]` 仍被拿來與原 supervisor argv 比較，會把正常清理誤判成 argv 漂移。已要求 owner 分離「目標執行期間的預期 argv」與「清理後應恢復的 supervisor argv」，並以真正 writer seam 驗證正常路徑及 primary／alias／argv 同時失敗路徑。此處是阻擋紀錄，並非 q 完整產製驗收。


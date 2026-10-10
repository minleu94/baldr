# F03 三路準備：獨立審查後補正

狀態：實作／驗證中，不授共同 reader 資格。承接 `ed8b0506`，完整 F03 query、UI、收藏與跨程序閉環仍未完成。

## 審查結果與實作範圍

獨立 Luna Max 審查發現兩項應在共同 issuer 前補齊的問題：三個 collector 的可變 entries list 沒有保留原 callback entry 參照，跨 lane 相等不足以拒絕三路一起被替換並重算 self hash；group 雜湊前呼叫 MA index `to_dict()` 與 parent `asdict()` 會建立全量複本，不能以後續串流雜湊宣稱整段沒有全量複本。

先在三路 callback 當下保留有界、不可變的 entry 參照與 exact snapshot pin 紀錄，prepare 開始及結束都比對原參照；poison 清除全部紀錄。保存的是 compact entry 參照，不是 raw snapshot 或重新計算金融證據。只使用原 exact snapshot／cutoff，availability unknown、historical PIT false 保持。

後續移除 group 層的全量 MA payload 與 parent ledger 深拷貝。既有 MA index 建構仍有全量 canonical materialization；在真正修改並驗證前，此限制必須保留，不能宣稱完整 streaming／100,000 股記憶體驗收。F12 C3 的 MA source pin 正凍結，不在完整 Main 終態前改動 MA 模組。

## 回滾清單

| 檔案 | 類型 | 變更／回滾 | 風險 |
|---|---|---|---|
| `app_module/daily_market_technical_universe_projection_group_v2.py` | 修改 | 加 callback provenance；僅反向套用本切片 diff | 三路 group observer 受影響；不能覆寫其他改動 |
| `app_module/daily_market_technical_universe_projection_group_prepare_v2.py` | 修改 | 核對原 callback 參照及精確 pins；僅反向套用本切片 diff | 既有 group prepare 測試需重驗 |
| `tests/test_daily_market_technical_projection_group_prepare_v2.py` | 修改 | 原參照、同步替換及晚到替換負例；僅反向套用本切片 diff | 測試須保留首紅證據 |
| 本文件 | 新增 | 移除本文件前確認沒有新增入口依賴 | 不刪除原 QA 收據 |

回滾前核對最新 HEAD／dirty ownership，只撤此切片，重跑相關 group／prepare 測試。原始資料、正式排程、其他 agent 文件與本機 QA 封套不回退或刪除。

## 驗證狀態

待測，不把先前 7／3 項 preparation 通過當作新 tamper contract 已通過。共同 issuer 仍須沿唯一 F17 verified-bundle 發行邊界內部 prepare；不能接受 caller supplied candidate，也不能先發單獨 MA session。

兩個修改的 source module 型態檢查通過。第一次測試命令誤用不存在的 group 測試檔名，exit 4、沒有收集測試；保留 `output/qa/resume_root_validation_20261009_a/three_member_provenance_followup_attempt01.log`。第二次已修正檔名，實際結果待終態，記錄於同目錄 `three_member_provenance_followup_attempt02.log`。

第二次已終態：**13 passed／361.85s，exit 0**。實際正例涵蓋完整 257 included 母體、兩個 parent；query selection 只選最後一股，並未把 preparation 母體縮為一股。舊 MA serializer 與舊 parent `asdict()` canonical bytes 作 oracle，新串流 SHA／byte count 均相同。同步重算三路 transport、自我 hash 有效但 callback entries 被替換、晚到替換等負例均拒絕並 poison。targeted mypy 兩個 source modules 無錯誤；此結果不補授 reader 資格。

獨立審查另指出：provenance list 本身仍是私有可變狀態。這次拒絕模型涵蓋 collector rows 被替換、ledger 保持原 callback 記錄；沒有證明能阻止同一程序直接同時偽造 collector 與私有 ledger，不能稱為不可偽造 seal。唯一 issuer 後續不得接受 caller supplied preparation；正式資格必須由同次內部 verified-bundle 流程授予。新增 refs 僅證明筆數受 stock 上限約束，Python object overhead 尚未量測且不含於 canonical byte budget；完整 100,000 股記憶體驗收仍待辦。

## 並行工作實際狀態

P01 六角色矩陣 C 已執行一次，五個冷啟動與一個暖操作程序均 exit 0、來源與 store 前後一致、清理完成。暖操作每類 30 樣本，原 300 毫秒門檻保持：篩選 p95 618.493 毫秒未過；排序 246.491 毫秒、翻頁 208.060 毫秒。冷啟動至第一頁 p95 25.931 秒。這是隔離候選的量測，不是完整產品效能驗收。封套：`output/qa/p01_1000_component_tuple_memo_candidate_20261009_c/six_role_matrix_aggregate_v1.json`。

F12 C3 完整 Main 首次執行 exit 1，拒絕代碼 `parent_initial_personal_json_not_readonly`；原收據未保存當時的 mode/message，不能直接歸因產品來源錯誤。清理另遇 QA 呼叫不存在的 worker helper；後續 job helper 亦需核對真實 API。首紅封套保持，補正前不宣稱 Main 閉環通過。H20 O 仍只完成靜態檢查，尚未執行真 source-port／SQLite 正例；reader replay 與 storage config 錯 root/hash 負例仍未覆蓋。

root 從暖操作原 `child_result.json` 各 30 筆 elapsed_ns 獨立重算 nearest-rank p95，三類結果與 aggregate 相同，90 筆 status 均 `ok`；六角色 cleanup 沒有 active job PID。F12 另存事後獨立 `readonly_postflight_20261009.json`，13 roots SHA 與原 before 一致、58/58 pins 相符；原 receipt 的 after 仍為 null，沒有冒充補造原當次 after。原 merged stdout 無法從 compacted context 逐字取回，缺口明示保存。

### H20 O 實跑終態（後於上述靜態狀態）

O SHA `409ace8f414edd108059fb13ae852ddc205567d7568d0098307ed7ca439e9d7b`。attempt01 sandbox 匯入固定 N/M helper 遭 strict resolve WinError 5；保留原生 stderr 與 terminal receipt。獲核准的 attempt02 隔離實跑 **exit 1／約 4.67 秒**：已進入原 source callback，在 loader 前置步驟讀取研究根目錄設定，`msvcrt.open_osfhandle` 被原 N guard 以 `windows_open_osfhandle_callsite_or_flags_denied` 拒絕。initial/terminal terminal-file 真讀取與 SQLite 嘗試均為 0，負例未跑；不能宣稱 SQLite 或 source-port 通過。

補正當次 callback 計數判讀：traceback 確實經 `exact_delegate → source_verifier → _source_port`；輸出 `source_callback_delegate_calls=[]` 是失敗路徑沒有更新初始欄位，不能用它宣稱實際 callback 0。原輸出保持；新 P 候選必須在 finally 保存實際完整 ledger。guard 原只認 queries reader 的 code/globals/locals；真正 storage-config reader 來自原 `data_module.ml_research_output_boundary`，其 `O_RDONLY|O_BINARY` 與 no-follow 開啟不因不同 callsite 自動變成無效。新增角色須綁固定 146-byte 設定、exact hash/root/env/file identity 與原 loader 父鏈，不以一般 fixture path 白名單放行。

root 實讀原 `attempt02/stdout.native.txt`：source、fixture、H20 source group、snapshot JSON 起訖一致；cleanup errors 空、aliases／環境恢復、private root 清空、descriptor 0。O 沒有重跑；下一步唯讀對照 config loader 真 callsite 與固定角色授權，先審查最小新候選再執行。原封套：`output/qa/h20_guarded_sourceport_sqlite_slice_20261009_o/attempt01`、`attempt02`。本文件承接 F03 修正 commit `115600d3`，所有首紅與未完成範圍保留。

### F12 D 定向測試與 Main 真狀態

D runner SHA `08f825ed29e612908c8c3318d841e9a4291b5b1443cb168d5047749609862750`；完整 C3→D diff SHA `6979417f80d002d467ffb4d1479c53f619bd364fc4044622a344aac9a56b20c3`。root 實讀完整差異、原 logs 並重算 SHA。D focused 首輪 sandbox 遭 strict resolve WinError 5（3 failed／14 passed／4 subtests）；原紀錄保留。隔離權限 focused 終態三命令 exit 0、無 timeout，**17 passed／4 subtests passed**，58 source pins 起訖一致、候選檔案穩定；真 JobObject child bounded stop、worker API、274-char 路徑與 junction 負例通過。成功收據 `output/qa/f12_main_revenue_new_pid_20261009_d/evidence/20261010T002208Z_38860_c879815b/receipt.json`。

D 唯一完整 Main attempt exit 1；當時 mode/message 已實際保存：`upgrade_available`／「目前沿用原 JSON 觀察清單；可由頁面按一次『升級觀察清單儲存』。」seed 206 bytes、SHA `653bfc9e7844d1c5a5aa8a167a83b7b140b94bcf3ac884347718016b5dc7e555`，路徑相符；嚴格 `personal_source_readonly` gate 保持拒絕。正常 close/drain 成功、cleanup errors 空、post-drain Qt accesses 0、aliases／環境恢復。原 after=null 保持，不據此宣稱來源起訖一致。原生 receipt `run_attempt_6fc40c40c0754c0382ad2c1a14f0cf26/f12_main_revenue_receipt.json`；launcher/raw stdout/stderr 位於 D 的 `evidence/authorized_main_run_20261010T002355Z_a91d0c68`。

root 從目前 QA source 找到具體原因：`_build_private_environment()` 新增兩個個人收藏 env keys，卻把 pinned helper 原有包含這兩 keys 的 unset 清單直接返回；Main 前先 update(env)、再 unset，兩個設定隨即被刪掉，`TWStockConfig` 取得預設 None，factory 選 legacy。後續 E 只調整 QA 明示 opt-in 的兩個 keys 與 unset 衝突，其他敏感／來源移除清單、原 gate 及產品 source 不放寬；尚未實跑 E，不宣稱完整收藏旅程完成。

### P01 正式修補與後續驗證邊界

root 已審查並提交 `76ed1b5e`：只有 strict leaf 已驗證的純 rendering 可預填原 bounded page memo，每次檔案狀態與內容驗證仍照常執行。審查另發現 lone-surrogate 的提前編碼錯誤，已最小修正為預填不新增 entry、保持原 component tuple；真正 strict renderer 仍按原時點拒絕，沒有放寬輸入。原生 **19 passed／27.69s，exit 0**，包含完整頁面 fresh-I/O、selected/unselected mtime restore 竄改、取消及 junction/reparse；targeted mypy、compile 與 whitespace 通過。root 重算 source/test/log SHA 與收據相符。詳見 `BALDR_P01_RENDER_PREFILL_20261009.md`。這次沒有重跑 1,000 股矩陣，不能把機制測試當成原 300ms 門檻已過。

E QA 可更新上述 source 的單一 pin，其他 57 pins、fixed inputs、route 與 deadlines 必須保持；完整 Main 尚待後續終態。D 的獨立 13-root postflight 與 before 相同，原 receipt 的 after=null 不回填。

H20 P 初版仍未實跑。root 靜態審查找到 ownership 時點不相容：原 boundary 在 `open_osfhandle` 成功後把 `owned_handle` 設 False，P 初版卻對後續 fdopen/stream 一律要求 True。已要求保存初版，區分轉移前 True 與轉移後已註冊 descriptor 的 False；不可直接移除 ownership guard。另一位 Luna Max 做獨立差異審查。H20 真 source-port／SQLite 閉環與原 2382 尚未完成，沒有新 EXE 或真人驗收入口。

### E 首輪與 P 父鏈追加審查

E focused 首輪終態 exit 1，原生收據 `output/qa/f12_main_revenue_new_pid_20261009_e/evidence/20261010T003808Z_47028_6ddaade0/receipt.json`；self-test strict resolve 遭 sandbox WinError 5，route exit 0，pytest **4 failed／18 passed／4 subtests passed**。58 pins 與候選檔起訖一致。root 另實讀 stderr 發現真 Config factory 測試曾嘗試開啟正式 D 資料區的 config.log，sandbox 拒絕；因此沒有逕行升權重跑。agent 確認無升權程序或 live handle；下一個候選須在子程序首次 import 前明示 private DATA_ROOT／OUTPUT_ROOT，保留第一個紅測與來源守衛，不刪 factory 測試。這不構成正式資料全面未變的證明。

root 獨立逐欄比對 E/D manifest 的 54 code pins 與 4 guard pins，唯一差異是已核准 P01 source 的 SHA／size；其他 57 完全一致。完整 E Main 尚未執行。

H20 P 的初版 `81f25d62…` 及完整 O→P diff 保留，尚未執行。除 ownership 外，root 實讀原 N `_config_session_phase` 發現 P callback globals 的否定條件方向相反，以及 P 一律要求 `_verify` frame／delegate terminal attribution 與原 `finish` 直接呼叫 verifier 不符。已要求新 P2 和最小追加提案分別核 initial `_verify → verify_source`、terminal `finish` 的 exact code/globals/self/kind；原 N phase authority 不得替換。這些是靜態必拒的原因，不能宣稱執行正例已通過。

E2 終態另存 `evidence/20261010T004430Z_9296_5dc698bb/receipt.json`：候選 self-test、route 均 exit 0，pytest **1 failed／21 passed／4 subtests passed**。唯一失敗為新增 child-env 測試傳入尚不存在的硬編碼 fixture root，原 pinned helper 正確以 strict resolve 拒絕；沒有放寬 helper。原生 stderr 確認 Config 的 DATA_ROOT／OUTPUT_ROOT 已在該 attempt 私有區。58 pins／候選檔起訖一致，E2 原 test/diff 與 receipt 保存。E3 僅把該測試換成真正建立的 fresh private application／f17 目錄，原 child-validator 正反例保留；待終態，不宣稱 Main 完成。

root 和獨立 reviewer 又核對原 frozen loader，修正先前「每 phase 一次 config read」的錯誤要求：真流程為 get-root 一次、兩個 root resolution 各一次、四個 pinned-path resolution 各一次，合計每 phase 七次、initial/terminal 共十四次。新角色只能依這三類 exact caller/code/globals/locals 與固定順序授權；每次 146-byte／SHA、16KiB 上限與新鮮讀取不變，不能快取設定掩蓋真流程，不增加 SQLite cap。P/P2 不執行，先保留靜態材料並重定最小角色方案。獨立審查另發現 descriptor 碰撞及 stream.close 錯誤的清理缺口；修補須關閉已轉移所有權的 CRT descriptor，保留 primary/secondary 錯誤，不把 CloseHandle 當成 os.close。

### E4 定向回歸與完整 Main 待驗（追加）

E3 原生終態為 1 failed／21 passed／4 subtests passed：child-env 測試把 pinned helper 的 unset 清單錯比為固定常數，漏掉原 helper 另加的四個 MA source override keys。E4 只修測試 oracle，從同次真 helper 回傳的完整清單移除兩個明示 personal opt-in keys；四個來源 override keys 仍必須保留，原 child-validator 正反例沒有移除。E1／E2／E3 首紅均保留。

root 獨立讀取 E4 原生 logs、receipt 並重算雜湊：三命令 exit 0，**22 passed／8 subtests passed／7.07s**；58 source pins 起訖匹配、候選檔案穩定。原生 receipt 位於 `output/qa/f12_main_revenue_new_pid_20261009_e/evidence/20261010T005609Z_57816_2c0c04f3/receipt.json`，SHA `48c4ecf7415641088ce935c64506293b4f0d36aa3151d1f2dc0d69070e679836`；pytest stdout SHA `0e29924387ca2e78b3dabb85bffd48aa1d5bbaae3125d74ea61504bd9207b903`。兩個 MainWindow failure receipt 是測試明示注入的建構／清理錯誤，不能誤判為實際 Main 驗收失敗或成功。

root 已閱讀 capture 啟動器並授權唯一一次 E 完整 Main 隔離測試，維持 300／240／180／20 秒期限、來源守衛、真 native PID chain 與來源前後核對。此段落寫入時仍未取得 Main 終態，不宣稱收藏新程序閉環完成，也沒有新 EXE 或真人驗收入口。共享 F17／MA／P01 sources 暫時保持 pin，不因測試通過提前整合 F03。

本機一般 sandbox launcher 曾回報 `CreateProcessSecurityEnvironment HRESULT 0x800705AA`；低負載核准執行可正常讀取及測試，並非所有 Python 已終止。獨立唯讀資源收據 `output/qa/resume_root_validation_20261009_a/system_resource_observation_20261010_a.json` 保存當時 commit limit／使用量、C 槽空間和未確認所有權的程序數；沒有終止未知程序或改系統設定。H20 P3 和 F03 唯一 issuer 提案仍平行做靜態審查；H20 正例與原 2382 待驗，產品完整補完範圍保持。
E 唯一完整 Main 已終態 exit 1／19.015 秒：先前的兩個 personal env keys 衝突已解除，真 mode 為 `personal_source_readonly`。現在拒絕原因為 `f12_full_query_failed:('核驗雙來源並執行全母體查詢', False)`；query 的原始錯誤尚待追查，不能據 UI 終止訊號推斷來源缺件。原 native receipt `run_attempt_77ca0959cb674aa0870dd37e29ccfcd9/f12_main_revenue_receipt.json` 沒有 `source_inventory_after` 欄位，保持原件，不回填；獨立事後 13-root 核對另存。真 wrapper/Popen/native PID 分別 54028／41460／25400，pinned helper 驗證為 `venv_redirector_child`、chain error 空。清理 errors 空、environment／guards restored；nested `parent_finally_window_retirement` 確認 wrapper retired、close finalizing、post-drain Qt accesses 0；沒有啟動 child restore（real Popen 0）。首紅與原 stdout/stderr 位於 `evidence/20261010T010005Z_54028_b7f39cca`，不重跑或把 focused pass 算成 Main pass。

F03 QA 設計初稿已完成，root 審查要求分開完整 included 母體與故意只選一股的 query selection；共同 qualified session 必須保留完整三路母體。getter 必須使用 anchor 綁定的 immutable prepared views，不從發行後仍可變的 live collector 讀值；補發行後替換 collector/ledger 不得改變 sealed view 的驗收。尚未修改正式 issuer 或執行新整合測試。
### E query 拒絕定位與 H20 P3 根審（追加）

root 實讀 E native `guard_events.sqlite`：前三次為 private application state；第四次是同次私有 `operations/f12-revenue-*/monthly_snapshot_operations/<id>/reader/fundamentals.sqlite?mode=ro`、uri=True、classification=unknown。實讀固定 v9 `guarded_connect`，它只認三個舊固定 DB；此新 reader 不在 source allowlist、位於 private application root、uri=True，必走 `unexpected_private_sqlite_uri` 拒絕。此事件與原碼支持守衛拒絕定位；原 worker traceback／status_label 未保存的診斷缺口仍保留。後續 QA 只增精確 snapshot custody 角色與錯誤 capture，不改 pinned v9、不 glob 放行 operations DB，不降低唯讀和來源前後核對。

H20 P3 SHA `640b56483c026eb1dfd9b757bc291665ff8af14da3390ad9ccad9c44a0b2f12a`，P2→P3 diff SHA `3c914ffa243a4a8115a548b22e2f7046788885aaa2be73c49d1e6f68c9fb5787`，未執行。root 分段核 exact 三類 caller、七項順序、原 loader locals、initial／finish、已轉移 descriptor identity，並要求所有 JSON wrong-pin probes 明示 session-gate negative，不冒充原 JSON pin validation。新增碰撞清理還錯要求 original os.close 必須產生 audit_seen；固定 N audit 無此 close 事件。最小追加修正須用 original fstat 的 descriptor 關閉結果核對，保留 primary collision deny 與 secondary cleanup error，不製造虛構 audit missing。P3 保持凍結，待最小差異審查後才跑一輪窄正例。
H20 P4 runner SHA `fdba34621df5c6d309090d946728c3378fb660fc83191e6bd07b9122797a3bef`，最小 diff SHA `e809851b9bb9aaae51214431a7854e0fc5d3aa4e4d81fe7da20029ce3280ae24` 經 root 重算、審查後唯一 attempt01 實跑 exit 1（PID 5616；無 live handle）。原 stdout SHA `d88b4f926be16433317658be0b455ea02ed4b9599f4ee9abc6c174629e58e029`、stderr SHA `699e99c5f7a6738f8f0de988ea40251696835ec5012b7f1c5d6989321e949191`；root 讀原 traceback／ledger：initial 真 delegate 一次，在 frozen capture `read_pinned_json` 的 os.open 被 `cycle_terminal_callsite_or_request_denied` 拒絕，configuration 真讀取／SQLite 均 0。來源、fixture、snapshot JSON 未變；attempt 清理完成、descriptor 0、環境／Python／logger 恢復、cleanup errors 空。負例尚未開始，不能宣稱 P4 reader 或 JSON pin 驗收通過。

root 進一步比對 P4 與原 N：P4 新 `guarded_open → base_open` 多了一個 caller frame；N 只從直接 capture frame 取 `expected`，如今取得的是 P4 wrapper，故 `terminal_pin_argument_matches=false`。不是來源 SHA 已變。P4 fdopen 類似 delegation 亦須完整核對，不能修完第一個 wrapper 再逐次碰第二個。下一步優先取消不必要 os.open wrapper，fdopen 僅為 exact config 角色保留 dispatch；舊 N branches 必須透過具名 exact trampoline 取得原 caller 並原樣執行既有 helper，不能 general ancestor whitelist、不得改 frozen N／source-port 或放寬 pin/cap。P4 首紅不重跑，先審最小接線提案。

### E 獨立來源核對與三路草案審查（追加）

root 已實讀並重算 E anchored 獨立 13-root 收據：`output/qa/f12_main_revenue_new_pid_20261009_e/evidence/e_readonly_13root_reference_20261010_a/receipt.json`，SHA `0b3535a5d7a421059567518fd0d06c1c8310a0e506713dcedbe5be0306b41ce0`。當時 13 roots 與 D、E before 均相同（inventory SHA `2608042da9c70d3e734c5f1dd48902bb12f704c7e77b5dc40071454b6dce856a`）。這是獨立事後核對，沒有新增原 native receipt 的 after。更正前文 D「after=null」的表述：D 與 E 原件實際都缺少 `source_inventory_after` 欄位；欄位缺失與 JSON null 不同，原件保持不動。

F12 F 私有 QA 草案加入真 worker error/status capture 與精確 monthly snapshot reader 角色，目前未跑測試或 Main。root 靜態審查發現草案要求 prime 前後 reader pins 全相同、所有 sidecars 不存在；但原 `fundamental_read_snapshot._prime_reader_copy` 明確允許 SQLite 在隔離 reader 目錄建立 main-only WAL sidecars，正常 `_open_reader_attempt` 會在 prime 後重建 copy binding。已要求沿用原 binding 的來源、reader、容量與完整性政策，不能以錯誤 oracle 阻擋合法私有流程，也不能因此放寬來源資料權限。原 E 首紅及固定 v9 守衛不修改。

F03 私有草案已修正完整母體與單股 selection 混用，核對全部 segment included codes；immutable prepared view 與 live collector 分離，發行後替換 collector 不得改變已封存 view。root 另要求新 group/prepare 模組只在明示 opt-in 分支延遲載入，舊兩個 opener 不因新增入口付出載入成本；正常 opener 的多 segment／257 included、單股 selection 測試仍待執行。正式 F17 source 仍凍結，未提前套用草案。

H20 P5 只獲靜態接線修改授權：取消多餘 os.open wrapper，fdopen 的原分支保留精確單次 caller token，並全面核對 Windows handle fallback；不得改 frozen N 或增加 SQLite cap。尚未實跑 P5。三位 Luna Max 分別處理 H20、F03、F12，由 root 審查；完整補完範圍、未完成真人驗收與效能門檻均不縮減，沒有新 EXE。

### 凍結草案的實際接線缺口（追加）

H20 P5 SHA `221124e9d13c4bc790d05a53409806228494c04551b84688a727d19828907048`，完整 P4→P5 diff SHA `327909a05e524f15b3a4b374345e87fa8452e5c80ba579e314346f6eeb195c3e` 均由 root 重算。root 實讀完整差異，發現 `_p_function_frame_matches` 比對 pinned function 的 code/globals/closure，卻沒有核對傳入的實際 frame code/globals；精確 frame 契約尚不成立，已要求下一個最小靜態 revision 與錯 code/globals 負例。P5 的非 config Windows handle fallback 仍多一層 wrapper，agent 明示 fail-closed／未驗；需先完成原 reader 呼叫鏈與窄 trampoline 審查，未授權 P5 runtime。

F03 A 凍結 draft reader SHA `d494cb0e157f17f1f5ef772af79a9ece9742f668cbb00b6ac6cf56469d1ae689`、group issuer SHA `0d47c6887c3e41f84345fb57f2a4376dc386fe756a467d8c50378129abe856da`。root 已讀完整 issuer、F17 diff、新測試與 test plan；發現測試還從 F17 模組取得已改成 local import 的 issuer 名稱，必須改 hook 真 group-session 模組。fresh child 的 lazy-import 測試亦須明示載入 draft reader，不能測到正式舊版造成假通過。A 原件保留，B 隔離 revision 正在補正及準備只覆蓋兩個 draft modules 的 package-path bootstrap；正式 F17 不修改。test plan 中尚未實作／執行的矩陣不算通過證據，正常 opener 與完整母體實跑仍待驗。

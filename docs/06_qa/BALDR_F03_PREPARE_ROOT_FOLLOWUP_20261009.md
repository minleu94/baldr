# F03 三路準備：獨立審查後補正

狀態：實作／驗證中，不授共同 reader 資格。承接 `ed8b0506`，完整 F03 query、UI、收藏與跨程序閉環仍未完成。

## 最新接續入口（2026-10-10 UTC）

以下為本文件最新工程切片狀態；後文的日期化追加保留原始歷史，不以舊「待測」覆蓋新終態。完整補完仍依原計畫 P00–P14／M1–M3／F01–F23，這三路不代表全部產品範圍。

| 工作 | 已取得的證據 | 接下來與未完成項 |
|---|---|---|
| F03 完整母體共同發行 | C13nodes與F正常node已有原生通過；root已套入正式reader、新group-session與14節點測試，補精確prepared型態後mypy兩source綠、三檔語法綠。 | 正式17節點首輪原生終態：15 passed、2 failed／499.90s；兩紅均為測試仍依賴QA overlay環境變數，已窄修為正式module路徑及tmp_path子程序參數，修正後b封套只重驗兩節點，原生2 passed／179.68s、exit0；首輪15項加修正2項全部取得通過，未重跑其餘15項。composite query／UI／收藏／新程序／EXE待辦，不能以此切片代替全產品完成。 |
| H20 原 source-port 接線 | P9 attempt01 最終中文 stdout 被 CP1252 拒絕，不能取回內部結果；原件保留。byte-identical launcher 的 attempt02 改用 process-tree UTF-8，原生 exit1；逐row PITfalse／hash／日期及12 core negatives通過，來源與fixture不變、cleanup完成。 | 唯一首紅為 QA receipt 的 tuple dictionary key（`('original_n_base_fdopen',)`）；P10唯一attempt01原生exit0／5.04s；真fixed2讀2關、config14讀14關、1private SQLite／0source connection；來源與fixture不變、cleanup完整。negative core通過但完整negative scope仍false；原JSON loader pin、private replay等缺口保留。public cohort、Main、原2382的684bp／圖表／速度、真人仍待驗。 |
| F12 收益與跨程序收藏 | J focused 原生13 passed／0.83s。K 全新隔離 Main 已成功 exact 核來源、完成 bundle 查詢與唯讀月營收 transaction；原生 exit1 止於 f12_initial_query_contract_mismatch，尚未保存各條件實值，不能猜測。 | 下一步只補初始 query／count／scope／page／recipe 明示診斷，保留既有驗收條件。完整收藏／新PID重開尚未完成。歷史封套及原來源保持。 |
| P01 效能 | 正式 render prefill `76ed1b5e` 的定向 19 cases 通過。舊六角色矩陣的篩選 p95 618.493 ms 未達 300 ms，冷啟動 p95 25.931 s。 | 新 prefill 尚未重做完整矩陣，不把定向綠燈當產品速度通過。 |

目前沒有可交真人驗收的新 EXE，不要求使用者重試舊版。三位 Luna Max 分別承接 H20、F03、F12，root 審查；另一 agent 的未提交文件、原始 D 槽資料與正式排程保持。

## 審查結果與實作範圍

### 正式 publication 整合（驗證中）

root 已核候選三檔 SHA、reader／test 與已測 F 相同、新 session 的可執行 AST 僅除 docstring 後相同，才套入正式工作區。首輪 targeted mypy 出現八項 prepared union／object 型態錯誤，已以既有驗證結果的精確 `cast` 補正，沒有 `Any`／ignore 或計算、來源 gate 變更；兩個 source module mypy 通過，三檔語法檢查通過。正式 pytest 首輪15通過、2個QA overlay設定失敗；已修測試路徑、未放寬產品gate，兩節點已原生2 passed／exit0，合計17項覆蓋全數通過；不授產品 query／UI／收藏完成。

| 檔案 | 變更 | 回滾方式 | 風險 |
|---|---|---|---|
| `app_module/daily_market_technical_official_disposition_query_reader_v1.py` | 修改，新增 opt-in group 發行 | 僅反向套用本次 reader 差異；舊 SHA `fc9c3d089c703f2bc815d0ce02310916de49aa1ce35cdfa8336ca7e630dc8045` | 新 opt-in 入口失效；先核沒有後續依賴 |
| `app_module/daily_market_technical_universe_projection_group_session_v2.py` | 新增 opaque issued view | 確認無後續 query／UI 依賴後撤本檔 | 不能保留 reader 對本檔的 opt-in 引用 |
| `tests/test_daily_market_technical_projection_group_publication_v2.py` | 新增14節點回歸 | 隨本次 publication 功能一同撤回 | 不撤既有 prepare／group／reader 測試或原 QA 收據 |

F12 G 原封套保持，正式 F17 SHA 已變；後續 F12 修訂需明示重核來源 pins，不能改寫 G 的歷史 before／after。正式原始資料、排程與其他 agent 文件不變。

### F03 F 正常入口實跑終態（最新追加）

本輪另完成 F12 G 完整修訂、六個 Python 檔相關差異／launchers／preflight／測試審查，獨立核八個 candidate 與 58 個來源 pins 零差。review manifest SHA `14922be3c2945693aa159f72d3e06bee59d19a7cb3ab0c9102cf25c3b9d18514`；diff SHA `699912b6523f3627bf4325d8b01826598e30ac4d5c160db3ae4a8d471a65f222`。focused 封套 `output/qa/f12_main_revenue_new_pid_20261009_g/evidence/20261010T024219Z_56452_2c3c00a9`，receipt SHA `c2fb9c6b65688ac98538871707c70f24d60ac673f2d61220823931419913c4cc`；8 passed／0.88s、stderr空、58 pins起訖相符。只有 helper／finally 定向證據，不授 Main 成功；G 完整 Main 已授單次執行，觀察期限不能冒充終態。

凍結 F launcher 僅跑正常 node 一次，原 pytest **1 passed／173.82s，exit 0**；launcher 收據 elapsed 175.1825018 秒、timeout false、啟動時 commit headroom 9,017,552,896 bytes。root 獨立讀完整 stdout／receipt，核 20 正式 pins、7 候選 pins 與 manifest 起訖相同。獨立 CIM 實測中確認 31764 → 20704 → 50696 → 56960 的四層程序，終態後四 PID 均已不存在。

封套 `output/qa/baldr_f03_group_publication_proposal_20261009_f/attempt01`：receipt SHA `e3d9dbaec07f0d2dadd48c5d5e6c7ae2cbadd58183c83840b2d2611111a403f0`；stdout SHA `708f874ac2b097083a066d1ae41421f533e441d416f341fb9bd0073b119442d1`；stderr 為空。正式來源尚未改動；下一步準備正式整合候選，暫時保持 F12 正在審查的 58 source pins。此結果不授 canonical composite query、正常 UI、收藏、新程序、效能或 EXE 資格。

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

### P6 原生終態及下一步接線（追加）

root 審查並重算 P6 runner SHA `6f735bbaa36a8119603baf9b70e5fc5cdb13ab3defcb1889bc5fdc6df2bc32ff`、P5→P6 diff SHA `25e392a7d675254a443e361f1ca4571185f6fae629a2ff269d9b5fc2a7011b63` 後授權唯一 attempt01。實跑 **exit 1**、無 live session handle；stdout SHA `759d20b8fcb59c63aec4a5f2bf426cc3bb1e928713920117f711f59c9f20d1ad`、stderr SHA `bbfa3d8b88ee956a62da02a8a28b95a01d6200583003a12c51942a066649e1b4` 由 root 重算。SimpleNamespace helper 契約正反例均成功，這不代表原生錯 globals/frame 攻擊路徑已覆蓋。真 initial source delegate 一次，終端 `os.open` 仍被拒；config 真 reader／SQLite 均 0，主負例未開始。source、fixture、H20 source group、snapshot JSON 前後相同；cleanup errors 空、descriptor 0、attempt 移除、aliases／環境／Python／logger 恢復。

本輪原生 diagnostic 的 `terminal_pin_argument_matches=true`，capture frame 直接且 path/flags 吻合，證明前版 os.open wrapper 缺口已解除；不能把同名錯誤當成完全相同原因。root 實讀原 N `_cycle_terminal_phase_with_config_test_fallback`，其開頭核對 `getattr(self, helper).__func__` 必須是原固定函式，P5/P6 新 override 因此必拒，連沒有 fdopen token 的 os.open 也受影響。下一候選須先完整盤點六個 helper 的固定身分／audit 契約，保留 self 上原固定 helper；不得只修改一個檢查逐次撞下一個，也不放寬 terminal pin/cap。P6 首紅保持，不重跑、不算 H20 或個股 UI 通過。

F03 B 已補真 public opener 的 MA/KDJ/volatility 各 begin/consume/end 九個失敗分支、prepare 成功後 issuer envelope 超額拒絕及成功後 poison getter。root 已對照真方法名與清理 API；正式程式未改，隔離 package-path bootstrap 與 before/after source pins 正在完成。下一輪 focused 只跑受影響的 prepare、新 publication 與兩個原 F17 issue/取消 node，不把未修改的完整 BundleReader suite 順手加入。

### F03 B 唯一 focused 執行與 F12 F 靜態審查（追加）

root 已完整審查 B revision diff、package-path bootstrap、launcher 和新增測試，獨立重算 20 個正式 source pins 與 9 個 draft pins，沒有 mismatch。manifest SHA `d8184a26b9f8c634b963c15826322a6393c6616e8427a67fbe965dc417bf0c9f`；revision diff SHA `46bd346e2e0f1d2910cef7512d7bcf13edbfc22b2b1e5d34733eafed3024f3e1`。隔離 bootstrap 在任何 reader import 前掛入僅有兩個候選模組的 overlay，明確核對實際 reader 路徑與 SHA；fresh child lazy-import 檢查亦使用此候選，避免測到正式舊版造成假通過。

授權唯一 B focused attempt，僅跑原 prepare、新 publication 與兩個原 F17 指定 node。此段落寫入時測試仍存活，沒有原生終態或通過宣稱。root 獨立唯讀核對四個 exact PID／建立時間／command chain（31056 → 41796 → 49936 → 35704），觀察收據位於 `output/qa/resume_root_validation_20261009_a/f03_b_live_process_observation_20261010_a.json`。agent 持有原 live handle；root 無法使用該 scoped handle 不代表程序已終止，沒有重啟、重複測試或終止其他 Python。launcher 在原生終態前緩存輸出；正式 F17、MA 與 P01 sources 保持原 pins，尚未整合。

F12 F 仍為未凍結的隔離 QA 草案，未啟動 focused／Main。兩階段角色依原 primer verifier、prime、typed archived binding verifier、selection transaction 順序接線。root 審查要求消除任意 ancestor 搜尋，限定真呼叫鏈並核對 code／globals／thread／task／custody；單次 proof 在所有終態消耗與清理，連線取得後若後置檢查失敗須關閉連線並保留主錯誤與清理錯誤。SQLite 全域 hook 亦須重新核對當下 thread 和 task，不能僅靠函式身分放行。這些是候選審查發現，不能算作已通過負例或產品修復。

三位 Luna Max 維持 H20、F03、F12 分工，root 審查。H20 P7 只獲靜態候選接線授權；原 N helper 身分、來源和 P6 首紅保留。沒有新增 EXE、真人驗收入口或正式排程變更，完整 P00–P14／M1–M3／F01–F23 補完範圍保持。

### F03 B 原生終態與最小 QA 修正（追加）

B 唯一 attempt01 已終態 **exit 1，1 failed／14 passed／13 errors，671.25 秒**；沒有 timeout。root 已實讀原 stdout 與 receipt 並重算：receipt SHA `3d1ec0fd481784e490e325da36c9f4f115390afa95b164fc770dceba368e5fbb`、stdout SHA `157ad7830e396e3659b8b7edac64366fac283fd2ed05fdcead1c9d106cd0e85f`、stderr 為空檔。原生 log 明示載入 B overlay reader 與正確 draft SHA；20 正式 source pins、9 draft pins 與 manifest 起訖相同。root 另用 CIM 核對四個已知 PID 均已不存在；沒有重啟或終止未知程序。

13 個 publication cases 在 setup 階段因 draft tests 只引入 `exact_query`、漏引其依賴的 `exact_p01_session` fixture 而未執行；原正式 fixture 定義已核對。唯一 failed 為 fresh-child legacy stub 把 `builder.verified_session` 設成裸 object，真 bundle opener 需要其 `create_query`，因此 AttributeError。這兩項是 QA 接線首紅，不能當成真 publication 正例／負例執行失敗，也不能因其餘 14 綠燈宣稱 publication 完成。原件全部保留。

C 只獲靜態 QA revision 授權：補真 fixture dependency、修 session stub 契約，先交完整差異與依賴圖。下一輪只覆蓋尚未驗的 publication／lazy child，不重跑來源與候選均未改的已通過 prepare／原 F17 nodes；正式 sources 保持凍結。H20 P7 靜態審查另發現 bridge helper 還讀舊 `base_fdopen` local，新 wrapper 真 closure 名為 `bridged_base_fdopen`，已要求在 freeze 前逐一核對 pins／closure／真 locals，未執行 P7。

### P7 凍結審查及 C 受控收集（追加）

H20 P7 已修正真 wrapper local 名稱並凍結：runner SHA `81fd6773e1036cac82936f5a7ef94c59f9a79367eccf8230823c722ae32b3852`、完整 P6→P7 diff SHA `48d27383d52de6aaafcc574089b14dfbb4bae4d2488823ecab42b285432a01f4` 由 root 重算。root 已完整讀差異、bridge／wrapper／helpers 和靜態收據：六個原 N helpers 不覆寫；QA-only FunctionType clone 保留原 code／closure／defaults，globals 只替 clone 的 sys 提供私有 shim；shim 限真 frame、depth 1、同 thread、單次 token、相鄰 clone→wrapper→原 caller，原守衛後續 admission／audit／caps 不變。N／P6 pins 保持。root 授權唯一 P7 attempt01 窄實測，啟動前須 fresh source pins／至少 2 GiB commit headroom，不能重跑首紅；此段落尚無原生結果。不授 public cohort／Main／原 2382 個股／速度資格。

C 完整 B→C diff SHA `6925630f0721ef4dfd2b4e521604dedf2313ccfcdf4bca5795320768ea79a91a`，manifest SHA `6d09bf5f7238d4bb77bf14e972d8ef9a4dc20503b41c328860e7b47fa1c70eae`。root 已讀完整最小差異、正式 fixture 定義及 opener stub 契約，獨立重算 20 formal／11 draft pins，mismatch 空。批准在 P7 確認終態後唯一 collect01（只有 C publication 檔，預期 14 nodes）；collection 不會 setup fixtures，不能當成 fixture resolution 或功能通過。真 focused 仍待 root 讀收集結果後授權，沒有修改正式 sources。

F12 F 任意 ancestor 搜尋改為精確有限鏈的設計另經實碼核對：query task 經 `_open_from_bundle`、bundle source opener、`_open_and_publish`、monthly index archived opener、snapshot archived opener，再到 `_open_reader_attempt`；目前 bookmark task 實際經 `_restore_bookmark`、recipe reopen、`_open_and_publish`。同檔 `_open_from_recipe` 不是此 bookmark task 的 callsite，root 先前僅由 helper 存在推作 route 的推論已撤回，依 agent 與 root 實讀目前 pinned source 修正。尚未凍結 F 或執行 F。

### P7 真終態與 C focused 放行（追加）

P7 唯一 attempt01 exit 1，Popen elapsed **5.1313974 秒**，120 秒期限未到；launcher PID 26348、Popen PID 15076，並未取得完整 venv redirector／real native Python chain，不能把兩個 PID 當成完整原生程序身分證據。原 launcher receipt SHA `8ced4f6816d090d2b2db04f16af897d4f74c82738577a528128f9c599822a26f`、stdout SHA `89784cdaeb871ebfcd8cfb6ce27ef426049aa73970802b0081a5f9e76e97e7e1`、stderr SHA `7e3531e9a29c3d6c92c0535cbef1f004eb6fd326c78b0b30551b94ee34111a5a` 均由 root 重算。原封套保持。

實際首紅已越過 P6：真 initial terminal receipt 讀取 4046 bytes，原三個 phase helpers 與六個 fdopen helpers setup/final 均匹配。接著初始 source callback 的 config get-root ordinal 1 進入真 Windows reader，open／fdopen／close 各 1，卻在 `_p_storage_fdopen` 的裸 `BoundStorageConfigReader` 名稱處發生 NameError；該類其實是 guard nested class，方法中的裸名不在其 lexical/globals scope。config payload read 0、SQLite 全部 attempts 0、主要負例尚未開始。來源／fixture／snapshot 未變、cleanup errors 空、descriptor 0、aliases／environment／Python/logger 恢復；不宣稱 H20／public cohort／Main 通過。

此 P7 launcher **未執行授權要求的啟動前 commit-memory gate**，agent 把 C: 磁碟餘裕誤作記憶體餘裕。原 `preflight_status=passed` 只涵蓋已實作的來源／磁碟等檢查，不能授予至少 2 GiB CommittedBytes／CommitLimit 資格；不得用事後 counters 補證、回填原件或重跑 P7。P8 只授最小 static revision：修 nested class 的精確 factory／作用域、盤點同類引用，並交完整新 launcher 由 root 審查；memory 與 disk 分欄、觀測失敗即拒跑。

root 已讀 C collect01：恰 14 個 publication／lazy-child nodes，overlay reader SHA 正確；exit 0、elapsed 1.5286749 秒。receipt SHA `f597d29b7c7b7939ddc5dcf8d7f290906348b0f888c87f40c15b45b09799b9e8`、stdout SHA `e435e5fec268f445d010261b96c9aba6b75a3163c692ca9fa932e316a0ee91f1`；fresh commit headroom 4,318,068,736 bytes，sources／drafts／manifest 前後相同。collection 不證 fixture resolution。root CIM 已確認無 P7 runner／launcher 存活 Python，放行唯一 C attempt01 真 focused，仍需新的 pins／memory preflight；本段尚無其測試終態，其他兩路 static-only。

F12 靜態推論再校準：UI helper 只產生未建立的 `parent/f12-revenue-<id>`，source `_new_operation_root` 驗證、mkdir 並回傳同一路徑，並沒有第二層隨機 root；原單層 parent binding 保持。真 callback 的 `effective_cancel` 來自 monthly read-session adapter（不是 selection reader），index opener只轉傳；snapshot reader 的 `session_cancelled` 再包此 callback，需核對兩層閉包與各自 event。這些校準未執行 F，也未放寬來源路徑。

C focused 已開始，agent 持有原 live handle 10589；root 獨立 CIM 核對四程序鏈 52048（venv launcher）→22296（real launcher）→57960（venv pytest）→44804（real pytest），建立時間均為 2026-10-10 02:04:52 UTC、commands 均指 C。唯讀觀察收據 `output/qa/resume_root_validation_20261009_a/f03_c_live_process_observation_20261010_a.json`，SHA `a90d21016ff656a6ae7c4d215c3dcbf68738a9b515fb02bcd5af397dbe1ad87e`。本段尚無 native 終態，不重啟、不並行新 runtime；若超時須另核 exact descendants，不能以 launcher timeout 推定已全止。

### C focused 終態與 D 單正常案例修正（追加）

C 唯一 attempt01 已終態 **exit 1，13 passed／1 failed，296.48 秒**；launcher receipt elapsed 297.7983396 秒、沒有 timeout，fresh commit headroom 4,475,867,136 bytes，formal／draft／manifest 起訖相同。root 已讀完整原 stdout、receipt，重算 receipt SHA `9a278d32472b96c5eadf257ca29707c814e4d88908f3090c02a3a9a152a54752`、stdout SHA `1eeae641706e040a3a0d19987e6b07f1cf69cad5d6f3ed623ceb17770a04eec2`；C 四個已知 PID 經 CIM 確認不存在。首紅封套不改、不重跑。

唯一 failed 是正常正例的 `_one_code_outer_query` 使用 `dataclasses.replace` 更改 outer filter 卻沿用舊 canonical query identity；正式 `__post_init__` 正確拒絕 `technical_official_query_v1_identity_mismatch`，此時還沒呼叫新 opener。D 只獲 static QA revision：沿正式 `DailyMarketTechnicalOfficialDispositionQueryV1.create`，逐欄保留原技術 query、cutoff、bundle／source pins、scopes、market／disposal states 與排序，僅改單股 outer filter，讓原 factory 產生新合法 identity。root 已實讀 factory 及正常 case 全部後續斷言；不得手算 hash、放寬驗證或刪掉完整母體／同次 callback／immutable views／duplicate／poison 等要求。下一實跑僅此正常 1 node，不重跑 C 通過的 13 nodes；D 尚未凍結或授 runtime。

### D 單正常案例放行與 F 凍結審查（追加）

D 已凍結；root 完整讀最小 revision、正常 case API 盤點及 launcher，並獨立核對 20 formal + 7 artifact pins 全匹配。diff SHA `425e38608b7e7ab6c2de6bb6da341474dcf6f8315179a9f71ac535591b99a213`；測試 SHA `888f3d60fe70b588574ca94639d1c31d49c342588feecae863b8b1bcdea598d8`。批准 attempt01 僅正常 opener 1 node 一次，原 CommittedBytes／CommitLimit 至少 2 GiB gate、private roots／環境與 source pins 保留。agent 已回 live handle 8644，本段沒有終態，不重啟或重跑 C 的 13 綠燈。

F 營收候選已靜態凍結，source SHA `c75f4a7bf3036fc640c76d530b44a9999d6bbff8a02a9b66456e7a8bf977042f`，完整 E→F diff SHA `09b4937ed4400b4d9cf3be57d9852a4e1830156c9f574124abc4dff8ef0fc754`。root 正在逐段完整審查，尚未授任何 focused／Main 執行。已找到明確靜態 blocker：transaction context helper 使用 `type(database_path) is Path`；Path 工廠返回 WindowsPath（其他平台 PosixPath），此條件會拒絕正式有效路徑。已要求 agent 對照正式 callsite 與 helper probes，保留凍結 F，先交靜態報告，不以測試執行代替審查，也不放寬 URI／custody／source 驗證。

P8 仍是 H20 static-only 修訂與新 launcher 審查；沒有讀取完成、SQLite／Main 或真人驗收資格。完整產品補完範圍保持 P00–P14／M1–M3／F01–F23，三位 Luna Max 分工與 root 整合不變。
### F 完整靜態差異審查及 P8 launcher 審查（追加）

root 已完整讀 F 的 E→F 全差異、主程式新增 two-stage reader gate／固定十層鏈／proof清理／測試與兩份 launcher；獨立重算 candidate receipt 所列固定檔及 58 source pins，全部相符。F 仍不授 runtime：除 `type(path) is Path` 永遠不接受平台具體 Path 實例外，新增 fixed-chain helper probe 把 reader 排在外層、worker 放內層，再由外層 reader 的 f_back 往 caller 比對 snapshot，呼叫方向相反，正例必拒。兩項由靜態碼證實，未執行 F 確認，凍結原件保留。

F focused driver 只有終態比對 source pins，不在啟動前拒絕 mismatch；candidate 自記 hash 不等於已審查版本約束，且 focused／Main capture 均缺 fresh commit-memory gate。Main capture 外層 process.wait 無上界。原生 `source_inventory_after` 只在成功行程寫入，失敗的 D／E 缺欄位不能藉事後收據轉為 native。已交 agent 靜態盤點及最小新版本修訂提案，尚未授變更或執行；正式查詢／路徑／來源驗證不可放寬。

P8 candidate 全差異及新 launcher 全差異已由 root 實讀，nested reader 沒有剩餘裸 constructor 名稱，工廠使用 pinned class；class與六個方法 code／globals／closure等身分保留。candidate SHA `ca6414cd4226b171cc4409af1536224dedf3169eba01d5b5b39e7db71cf9af99`、launcher SHA `4242f4e549fac4224ee3f7fc5eeb21859f1098bb969a8c7965531b7ac5830ea3` root 重算一致。新 PDH CommittedBytes／CommitLimit 檢查與 disk分開，缺counter／餘裕不足／sample超過5秒都拒Popen；兩次freshness檢查。attempt01目前只有launcher source，沒有runtime收據或logs；等待最後map及D終態，未授P8啟動。

D 已知四程序鏈58044→33888→26884→26716由root CIM独立確認仍存在、建立時間2026-10-10 02:16:46 UTC、全部commands指D，原handle8644不重啟。此追加段落尚沒有D終態，13個C通過案例不重跑。沒有EXE／真人入口／正式排程變更。

### D 正常 opener 終態與 P8 單次實測授權（追加）

D唯一attempt01 exit1，原生 `1 failed in 205.61s`，launcher207.2714872s，無timeout。receipt SHA `096eee8cfa404fba297a194683fe2a37fc84bc6448c678fe7eb9fccac8825d18`、stdout `7e1b9d7ee06e8a85f25f647274c35d8860199243cba0e9fec8ba154bb04b3a9e` root實讀重算；20formal／7draft／manifest前後同，fresh commit headroom6,748,098,560B，rootCIM核4knownPIDs全gone。

正常公開opener成功發行後，258declared／257included+processed／1excluded／0pending、兩parent、單次exactread、三member同snapshot/row、outer單碼不改全母體分母與frozen值斷言均實際越過。唯一failed在test314直接`group._row_provenance=[]`；正式`__setattr__`按設計拒`technical_projection_group_v2_members_immutable`。不得稱整normalnode通過：後續getter穩定／conditions／duplicate／decoder／poison斷言尚未執行。授E static-only：明確驗重綁被拒且原list identity不變，再clear原list內容驗immutablepreparedanchor；不改正式guard，不object.__setattr__繞過，不刪後續斷言。

Root讀P8最後繁中map、完整candidate/launcher diff後授唯一attempt01，D已終態不並行重runtime。fresh frozen source／candidate pins、PDHcommitheadroom至少2GiB與獨立diskgate必須通過；啟動後另以CIM核實native鏈，不能用PopenPID代替。120秒僅觀測期限，同handle等待不重啟。此段尚無P8結果。

F兩個必拒靜態錯誤、失敗原生after缺口與launcher門檻由agent獨立實碼確認；授G static-only最小修訂，保留F、原正式來源與URI/custody條件，完整新diff與launcher受root審查前不跑focused／Qt／Main／producer。全產品範圍保持，無可驗真人新EXE。
### P8 原生讀取進展、QA schema 首紅與 E 正常案例（追加）

P8唯一attempt01 exit1，Popen elapsed5.4003992s，120s期限未到。root已讀原JSONstdout／stderr／launcher receipt／preflight，重算receipt SHA `7af0b26d111227ddb435af56c0dc4bcb4c9b8b9b2133f0ca6a42729f958bc6fe`、stdout `5bba10f1cee9e55219ee19ef2361d26fd3c38a06b2d3e33cf174c3ec784b46ad`、stderr `f5c079f5c245be0635d29ca25294a1ccd322ff4ead0687cc85f659aa23a49b4b`。fresh PDH headroom6,639,513,600B、sample age0.0154108s，memory/disk分開gate通過。源／fixture／H20 source group／snapshot JSON起訖同，cleanup_complete=true、errors=[]、descriptor0、attempt_removed=true、env/Python恢復。

此回真terminal initial/terminal各讀4046bytes，合8092；config initial/terminal各7次，共14次／2044bytes，SHA全符合固定146-byte config。真privateSQLite連線1，原sourceSQLite attempts0；初始與終端sourcecallback均回傳mapping。首紅2236是QA把`historical_pit_eligible`錯查在source_binding schema。root直接讀H9 source_binding SHA `f570beefbab0ae5341e0637b593c7f1790ec369733bd94775de79e53107b55b6`，matchesmanifest；feature date10/02與decision10/06正確，但該schema沒有historical_pit_eligible欄位，.get不是False。原terminal及原source-context另有明確false。不能因missing默認false、改原fixture或刪PIT斷言；交agent盤點真正已驗payload來源與剩餘assert，目前只有static diagnosis，不授P9runtime。後續負例／public cohort／Main／2382原684bp／速度未驗。

P8外部CIM觀察捕捉57400（venv launcher）→45924（real launcher）→44428（venv runner），未捕捉runner的real Python interpreter child，不能宣稱完整native chain。原wrapper把stub當實際launcher而兩項simplifiedidentity=false，原件保持，需另附解釋；root事後CIM確認已知三PID不在且無P8runner／launcher的Python程序。舊map若說P7已讀兩terminal不精確：P7只有initial4046，P8才讀兩次8092；已要求新診斷澄清。

E最小revision已由root完整讀diff／plan／剩餘正常assertions，20formal＋7artifact獨立pins匹配；manifest SHA `151ce51c54c9786c83929fffc89b075982046718b2b262680d7d30fa949d8355`，diff `b43ccbe143e08f4063de4623adba082a8d944c552b523b8ebcce9462feacd05b`。批准唯一Eattempt01同一normalnode，其他13nodes不重跑；原handle22903。root CIM獨立確認12168→17944→59452→57732四程序chain存在、2026-10-10 02:25:00UTC建立且commands指E。此段沒有E終態，不重啟、不並行新增runtime。

P9 schema修訂另由root實碼定位：frozen `_source_port`40–124先用原typed loader驗context PITfalse，feature builder回傳row asdict；H9 pinned binding的每股feature row有明確`historical_pit_eligible:false`、`formal_training_allowed:false`、`research_only:true`，top-level binding無該欄位。授P9 static-only在原逐row/date/rowsha/fingerprint核對中加入真required-row PIT欄位檢查，摘要由已檢全部rows得出，不改fixture／來源／cap或原P8。完整diff／launcher／剩餘assert盤點待root審查。並非正式PIT資格；歷史研究限定仍false。
### E 終態與完整 error-code 靜態盤點（追加）

E唯一attempt01 exit1、`1 failed in 186.88s`，receipt188.6035036s，無timeout，freshcommitheadroom6,809,743,360B。root讀原stdout／receipt並重算receipt SHA `a2ec13b560362f241aae037000019d73a58d0e2771c8fbdafbb7af0e06d142c4`、stdout `f9c96f232d30fef3b2d8dddcc4f1a27fc6b12bcad1b57294b76f727a4bd40152`，20formal／7draft／manifest前後同；已知四PIDrootCIM全gone，原handle22903terminal，不重跑E。

E真ledger probe已越過：257provenance、重綁被既有immutable錯誤拒且原list/content不變、清list與兩parentset後三getter仍同anchor。接著test338錯誤碼literal首紅，少了reader公開前綴；實際拒絕為`technical_official_query_reader_v1_projection_group_session_conditions_require_exact_reopen`。root對照reader `_fail`147–164確實加此前綴；group/session的 `_fail`來自group_v2，不加reader前綴，後續already_issued／poison原expected合理。conditions確實拒絕，但後續duplicate／decoder／poison仍未跑，不稱整normalnode綠燈。

授F03 F static-only最小QA literal修正，需完整核對normalnode全部.code斷言的constructor與_fail、replace init=False與poison/getter行為；不能只盤API名稱。正式與兩draftmodules凍結、E首紅保留，下一次同normalnode唯一實測待rootreview。P8原71359handle已終態wrapperexit0與內部nativeexit1分開；外wrapper成功收尾不是H20切片通過。H20 P9和營收G皆static-only，尚無新真人／EXE驗收。

### 2026-10-10 UTC：正式測試設定修正與 H20 P10 終態

正式首輪封套 `output/qa/f03_formal_publication_validation_20261010_a` 原生 15 passed／2 failed／499.90s，wrapper exit1／501.969s；receipt SHA `11fdeed73667d1316257291df7c087b8de88bfec7721dc1d838d414adaf0b6ce`。兩紅為測試引用舊 QA overlay 環境變數，尚未進入該正常入口／新程序驗證；其餘15項通過。root 僅改這兩項為正式 module 位置及 tmp_path 子程序參數，保留所有產品 gate。新封套 b 僅重驗這兩項，handle26455、pytest5928→23952已實測 live，尚未終態；不得重啟或以目前空 stdout 判失敗。正式三檔語法及差異格式已核；新session SHA `b9767abbaac2f5133c6e6752634feb5ae52da21f0495af1aef4d0317c0126bca`。

H20 P10唯一attempt01已原生exit0／5.041568s。root讀原JSON確認selftest complete、所有completion checks真、真fixed2讀2關與config14讀14關、1private SQLite、source connection false，來源與fixture／group／JSON均不變，環境與Python狀態恢復、無active descriptors、cleanup errors空。stdout SHA `0210aa12373dd3a083d23a81a2c1d60d2a02ad1b1e4643b7c02c00760dac20e9`；stderr為config INFO。原生完整父子PID鏈未觀測，known launcher50396與Popen58796終態後gone。negative core scope通過但完整scope false：private replay、third-phase端到端、nonconfig Windows caller及原JSON loader pin驗證仍缺；不得擴稱public cohort／Main／原684bp完成。子代理接續既有canonical Main controller/child的窄static驗收整合，須先證合法launch inputs，不得改approved_for_launch false為true。

複合篩選正式module與定向tests由Luna Max實作，root尚未授runtime或修改reader接線。F12 H僅static：新增rollback/not_applicable精確transaction角色，保持WAL路徑與57個其他source pins，完整primary／final writer診斷；G原件保留。

正式b封套終態：2 passed／179.68s，wrapper exit0／181.579s；啟動commit headroom 8,737,202,176 bytes。known5928與23952已gone。首輪15項與本次修正2項合計17項全部取得原生通過。只證明publication／舊入口lazy／取消及exact reopen回歸；composite query／UI／收藏／效能／新EXE仍未完成。

### 2026-10-10 UTC：publication提交後的整合審查

共同publication四檔已保存於 `d4d40e24`；其他agent未提交內容保持。root初讀composite query時發現active_groups／active_group_count重parse完整F17 JSON的熱路徑風險，已要求reader預先驗query與active flags、逐股pure evaluation復用，保留canonical起訖驗證；尚未凍結module或授runtime。F12 H新增rollback proof已初讀journal=rollback／wal_state=not_applicable、無prime／typed archived binding、exact task-worker chain與source-capture gates；strict JSON序列化fallback原會丟失primary，已要求保留明示type/message scalar與phase/event。仍待完整G→H差異／pins凍結審查。

H20 `approved_for_launch=false` 是source-only建置流程的內部待驗旗標，不是使用者或auto-review拒絕。使用者已授權隔離QA；不另索批准、不改旗標冒充完成，沿既有builder核實版本與原684 source綁定後產生真正launch inputs。Luna Max正準備最小Main QA候選；沒有啟動Main。

root重新對照原補完計畫，完整P00–P14／M1–M3／F01–F23保持。推薦理由現有detail expand＋可捲文字區及個人模式幾何測試已定位，但來源版測試不能代替同版新EXE與真人；驗收候選仍須能捲到可能影響排名因素／分數拆解末尾，並走原2382來源→摘要→圖表→返回同選取。
### 複合篩選狀態語意審查（實作中，未授runtime）

root逐段讀四組truth helper發現active evaluators對pending/excluded回傳not_evaluated，但global predicate對hard-eligible只接受match/no_match/unknown。既有F17 hard eligibility為outer membership AND P01 stock filter，對這兩種status也可能真，直接套接會使整份query拒絕。Luna Max已採納修訂：保留原hard gates、另分evaluability；active pending/excluded固定not_evaluated／不可進unknown policy或OR入選；全inactive保持舊MA audit browse（hard eligible可見、predicate_match false）。完整declared／included／excluded／pending分母仍核，不以只留下processed掩蓋缺件。Counts須明示evaluability／audit-visible；新增混合status案例，pending目前不由groupissuer發布不等於pure契約可以不測。

另已定位technical helper仍於combine_mode逐股parse query JSON，改復用context.f17_query；reader預先解析query/context與status一次。修訂尚在子代理檔案，root待凍結後完整diff＋型態＋定向QA，不能當已驗證產品結果。
### F12 H完整root審查與單次focused授權

H已凍結；review_manifest SHA `7817d772bf92abbc0d6d38fc40d97c79d122d35029453610189d120a224dcf2b`，source manifest SHA `5ad4ebd50e654d7aed53de2f3c44031fd0c7d98cf153b67d030a3b3be161811b`。root獨立核8artifact大小／SHA全部匹配、54 code＋4 guard共58source全部匹配；唯一G→H source rebase是正式reader d494…ae689，其他57項相同。G fixed_inputs、route、capture launcher、preflight不變，G原封套保留。

root已讀candidate完整539行diff、tests178行diff、focused12行diff及source manifest13行diff；工具截斷的archived verification／transaction gate段另讀實檔1520–1710補齊。rollback新proof只允exact Selection.open呼叫鏈／同次attempt、typed archived binding、task token-worker-thread-cancel-provider/capture/pins，一次原archived verifier成功才發transaction_pending，no-prime與WAL/absent prime分開。transaction仍exact readonly URI／uri=True單次，沒新增generic URI whitelist。strict JSON child/parent原錯誤與writer錯誤另寫stderr；序列化fallback保留明示primary type/message和phase，不用default=str。三個改動Python compile-only通過。

已授Luna Max僅執行凍結H的11節點focused一次（原8＋本3），沿既有fresh commit headroom>=2GiB／58source preflight／隔離runtime。尚未授Main；要先讀focused原生終態，不把helper probes當真SQLite／Main通過。沒有其他root runtime並行。

F12 H focused原生終態：11 passed／24 deselected／0.88s，exit0、未timeout。root讀原stdout／stderr及收據；兩筆stderr是finally測試預期的injected constructor ValueError JSON，非首紅。封套evidence/20261010T030733Z_33044_6e767c81，receipt SHA bdc9d60edf9411708ded2fdfbdc495632ebbaed8510c3c0e56d29d534d0e3bb4；啟動commit headroom 8,595,501,056 bytes、8artifact／58pins起訖0差。已授同凍結H capture launcher完整Main一次，fresh preflight／private副本／新PID收藏流程；尚待實際原生終態，不把helper綠當Main通過。

### F12 H唯一Main原生首紅（不是focused通過的延伸）

H Main封套 `evidence/20261010T030833Z_47616_3d643502`，同exec handle27445原生exit1；root獨立CIM抓到38072→42660（venv capture）→47616（real capture）→46788（venv runner）→48812（real runner），終態後四個known Python PID皆gone。launcher只授單次，未重跑。真正TaskWorker錯誤仍為`unexpected_private_sqlite_uri`，monthly_reader=[]，新transaction-only proof未建立；不能宣稱rollback角色已通過。root另核本次私有snapshot_capture確為rollback/not_applicable，不由G舊模式推測。

H新strict JSON fallback首次保存完整primary stack，並明示final writer錯誤`TypeError: Object of type WindowsPath is not JSON serializable`；native candidate receipt仍running，是未能寫終態的舊內容，不是live證據。root靜態定位 `_serializable_task_diagnostic` 原樣回傳context.operation_parent，而context_for保存expected_parent Path。下一個獨立I候選只轉這個明確path欄位為文字、不用default=str；角色未匹配仍須readonly逐條核 exact caller/locals/gates，先明確首紅條件後才授新runtime。H的after/cleanup終態未保存，不宣稱完整清理成功；既有H/G原件保留。

下一I只加原build_proof與十層exact-chain的first-false固定gate/field/frame ordinal、布林值有界ledger（最多64，overflow不授資格）；維持原短路／exception傳播、不dump locals或callback/frame、不eager、不放寬條件。root已審composite counts完整分母、sort unknown/null置尾與stock tie-break／每256取消及as_tuple Decimal正規化保持精度，尚待全部result/page與定向tests凍結；沒有將pure helpers視為reader/UI資格。

### composite結果／分頁發行審查（未授runtime）

root初讀完整_result issuer／Result／Page anchor與page request段。新結果原接受read_session object，只自驗query.f17_query及group，無actual F17 owner資格；已要求局部import精確正式ReadSession型別、owner.query/source binding及同group reference／既有anchor檢查，page callback改精確typed Protocol。正例不得用stub reader取得資格；private underscore/seal不宣稱同程序惡意竄改不可偽造，仍按正常transport／replace拒絕模型。

另page request反覆呼叫Result.__post_init__時原會重建全ordered_keys payload與hash，100k下O(N)多份複本是明確效能風險；已要求沿immutable typed tuples／same subject anchor評估issue-time cache與page-time精確refs查驗，或明示尚未通過的限制。不得為快而跳source revalidation，不先宣稱100k記憶體或300ms門檻。Luna Max正在補兩個正式檔案及實際reader-issued正例，root待凍結再核全檔＋型態＋原生QA。

H20 sibling Main候選沿既有controller/child，把舊C611固定archive比對改為S3 manifest／BUILD_INFO／bundle／22 pins，真正builder launch_inputs綁Main與六組原來源；原D9 10-symbol／684bp與H9 synthetic1234bp分清。候選補實際report projection/chart/table same capture及Decimal/date/rowhash檢查，不改source-only旗標、不假填source hashes。尚未啟動Main。
### 最新三路審核補充（尚未凍結、未新增 runtime）

使用者再次授權由 root 繼續推進並合理分配 Luna Max；目前三個既有子代理保持 H20、F12、composite 分工，沒有要求真人重驗舊版。

root 另核共同 group-session 的 MA view 直接來自 prepared.ma.index，F17 group 路徑明確不建立 standalone MA ReadSession。已接受 composite source pin schema 移除不存在的 ma_read_session_identity_sha256，改核實際 MA index identity／source request／source clock 與共同 group identity；正式 owner／頁面來源核驗須沿同 schema，不能保留虛構來源標籤。sort key 的各 entry 來源一致性仍須由同一 verified group 與 reader 的 exact join 保證，page 重新核 pinned identities，不准 caller supplied entries 自算 hash 取得資格。

F12 I first-false 診斷候選已初讀：固定 gate／field／frame ordinal、有界64筆、overflow不授資格；path／cancel checks 使用逐項 lazy call 保留短路。原 build_proof 路徑例外的 catch 只記錄型別後 raise；原 exact-chain path helper 原本回 False 的部分維持回 False。完整 H→I diff、凍結 pins 與 focused 終態仍待 root 核驗，不把初讀當 runtime 通過。

H20 sibling controller 初始仍有 C611 舊常數與舊 child 名稱，屬實作中的副本；已要求完成 S3／真 launch_inputs 接線與完整 frozen SHA 才審可執行資格。S3 source-only 旗標不改；builder 產生合法啟動輸入屬已授權 QA 的工程工作，並非新的真人批准事項。

### I 完整初版 diff 審核與兩項實際 schema 錯誤（最新追加）

root 已讀 I 初版完整 H→I diff，SHA `7ecd23da22a02b4812bf754713715fa46431204c54100fc5d2ed0221175cbfa9`；獨立核8 artifacts／58 source pins與6 Python compile-only全匹配。初版review manifest SHA `230f095a55d28f09a851e71c5acb1dc9261e2104847d6b4f883400ecd5822267`，runner SHA `a139038574b4cf0a2ab5217a44f8bf71429fa68cd91fb6d93ef1d3c581841641`。逐項lazy checks維持原判定順序／例外傳播，沒有新增URI允許範圍。初版tests仍與H相同，receipt列的是測試描述而非真正pytest節點；已要求補最小 first-false ordinal、Path JSON、64筆overflow fail-closed真測試再凍結。未啟動I runtime。

H20圖表helper初版把PIT／formal training／research only查在PersonalH20ResearchRow上；root讀S3 dataclass證實該row根本沒有這三欄，必然首紅。已要求在已核原manifest／capture／typed projection的真正欄位驗資格，不用missing默認false，不刪限制；原684bp／10股／日期與hash保持。

composite新版owner pin核驗初版使用MA request.to_dict().get(request_identity_sha256)。root讀真MA契約證實該身分是property計算SHA(to_dict())，序列化body沒有此欄；已要求改用實際property。KD／vol request JSON則確實有該欄，兩者不得混同。Luna Max正補同group原entry object identity核驗與actual owner資格測試，尚未凍結或授runtime。


I 最終新增真測試後再凍結：review manifest `d009ea405b82476e32d2781b53a6c8103d8b44ba3ffff2cb462a184aacdad944`，完整diff `7a291a32a8c5c2ddc4a9d2107ce8f268437802286751393837ede1a308b62842`，static receipt `15c3dc991932840882cf421f67a0d0facd9a0951a8c52f3223d111b3637ea20b`。root另讀新增10-frame首local/code/globals ordinal測試、Path JSON與64容量overflow測試，核有界helper確接實際build_proof；8artifacts／6compile獨立匹配。已授凍結I12節點focused一次，fresh memory／58source gate及隔離runtime，尚未授Main；結果待原生終態。


### I focused通過、Main取得確切首紅與J窄修（最新終態）

I focused唯一封套 `evidence/20261010T032637Z_15592_efbcc676` 原生12 passed／24 deselected／0.83s、exit0。root讀完整stdout8991B／stderr678B並重算SHA，兩個stderr是預期constructor負例；receipt SHA `df2a75b84123d60b86739966752c580778cb07a40951d7a46dbb0c3d76955868`。8artifact／58source起訖匹配，fresh commit headroom8,769,060,864B。

root隨後授凍結I完整Main一次，同handle19474原生exit1且未timeout，沒有重啟。封套 `evidence/20261010T032727Z_17580_b5cd2a12`；root獨立CIM觀測44308→42228→17580→33052→41012，終態後四known Python PID皆gone。launcher receipt SHA `fc5ac9534af5dd1143e37765fce26e43dc9cabd3605a23639962aee21224b019`，native receipt SHA `af5a85df79f4f6ac0b40685cbf9d3057fd298f80fa1a5068dc215e0087d8e603`。本次native終態JSON成功保存failed／17.281s，source_inventory_unchanged=true、after captured matched、cleanup_errors空、環境及runtime guards恢復；不再把舊running收據誤作live。

primary仍unexpected_private_sqlite_uri，但I首次明示唯一proof rejection：frame_chain.local／field f17_query／ordinal4／bundle／token2、overflow false。root對照正式revenue_source_v1.py1112與1120證實route local是f17_query，_open_and_publish直接傳同物件；QA route_specs bundle卻讀舊'f17'而得到None。已授新J sibling static-only最小名稱修正與真source callsite schema回歸，不放寬guard、不改I/H或正式source；待凍結diff／pins／focused後再驗Main。完整收藏／新PID仍未通過。


### J 窄修凍結與 focused 原生通過

root完整讀 I→J 三檔差異，核正式bundle與bookmark的_publish首參數真為f17_query。J review manifest `1e4e79419e7538d499f37477b4a0a4b53e88a866de91b81cd72f8af95fa22180`；diff `68f66380462a6469c0dd211d0d09bbbbbc5b6a44d3f2f33a0aefaa7a5b0a354a`。root8artifacts／58source／6compile獨立通過。J focused唯一封套evidence/20261010T033110Z_48760_4cdebedc，原pytest13 passed／24 deselected／0.83s、exit0（wrapper1.219s）；receipt SHA `4a52c6ed8bc0921f5784452ad0303e67e83299eab01146f5309d327f61b674af`。root完整stdout8992B／stderr678B及before／after source pins已核，預期constructor注入保持。

已授同凍結J完整Main一次，fresh memory gate／8＋58pins／隔離唯讀source-copy，尚待原生終態，不重啟或修改來源。H20合法launch inputs須由非source-only builder新snapshot（S4等）同manifest／Main／root發行，不能與舊S3 manifest混綁；missing market/calendar pins由唯讀實際來源補，不假填或索真人工程批准。


J 唯一Main已終態exit1（launcher約0.3s），尚未進入Main：_parent_main4073拒絕private_application_parent_must_be_new，因J沿用I的頂層private parent而I已存在。8/58pins及fresh memory啟動gate綠，stdout空、stderr842B SHA `ca2c535b44bbe3e22ef0b9f5ead3c7da640e6c22e28735ba7e29dbca4e610042`；native receipt不存在，不能宣稱新query gate通過或正式source有問題。root完整原stderr／launcher讀回，已知26672／58676與J matching Python皆gone，J原件保持。授K static-only只改全新private parent C:/t/f12-main-revenue-newpid-runs-k；root唯讀確認不存在。不刪I舊目錄、不放寬new-parent gate。J13節點已通過不重跑，K需最小diff／8＋58pins／compile／fresh path preflight後單次Main另授。

### K 全新隔離目錄候選已審、唯一 Main 進行中

root 讀完整 J→K diff（07446567c290332407a6af45d6007c9b25ca5344ee1fc60c49fb51880d0e7c53），僅 private parent runs-i→runs-k 與 candidate hash 更新；J 原件保留，其他七檔完全相同。root 獨立核八個 artifact／六檔 compile／新目錄尚不存在；K review manifest b4db5c25a9153b5fd5e769ddf3c89cf03b45ab68185dd3f2f29058e7f3960b17。未重跑已通過的十三節點；授唯一完整 Main。啟動 fresh commit headroom 8,718,974,976 bytes，八 artifact／五十八 source pins 匹配。root 獨立 CIM 觀測 54432→56232→47524→4472→11996；同 handle65577 尚待原生終態，不能先記通過。

複合查詢新增共用 source-pin helper、實際 public group owner 發行 Result 正例、same-result cache 不重序列化 keys 與 replace 拒絕測試，尚未執行。root 初讀發現測試 MA source-clock key 與真 map 拼名不同，已要求依真 schema 修正。H20 舊 market DB/WAL/SHM pins 已漂移，代理只做原來源唯讀雜湊及前後 metadata，不能套舊 pin 或重設歷史 baseline；S4 真 launch template/controller 仍實作中。

### K 原生終態與精確進展

K 唯一 Main 同 handle65577 已完成 exit1，封套 evidence/20261010T033652Z_47524_183ec67a，elapsed20.671s。native receipt SHA bf4f4fc19aad02cda6b862c866b1da4b81b15e5351bcadb850964c8512941dc9；root 核 stdout1811B SHA1316b2fdab04d09fedd8ea0891e834f89f3b8550ba1c7c21af14a01179e1c24a、stderr9985B SHA5f1a482f9adf0abb9e2bbdfaa6d2cc6943769e3a3d530c0c9b2c6e520e6f56ec，native SHA與launcher一致。root獨立確認56232／47524／4472／11996四PID皆gone。

真正 monthly role 本次 status passed：原 archived verifier 通過，rollback/not_applicable不prime，唯讀transaction單次完成、task token2 settled_success=true、proof_rejections空。來源after已捕獲並matches_before=true、source_inventory_unchanged=true；cleanup_errors／role restore errors／capture restore errors皆空，environment／runtime guards restored=true，Qt wrapper退休且post-drain accesses=0。此證據只授初次 bundle query 與月營收讀取；尚未進比較／收藏／fresh PID。

初始contract仍合併檢查query identity、declared/visible258、scope current_only、availability unknown、PIT false、page0/128、recipe非空；native未保存這些各別實值，不能直接改expected或歸因正式source。已要求下一候選明示scalar first-false且維持原gate，未授修改或runtime。舊K首紅保持。

### 複合契約凍結與唯一測試進行中；L診斷候選已審

composite source SHA2375f3703e93c2e26ca6477648e9ed0e679495c393ee7d47069f8b7f847e8a4c、tests SHAbb19032e7c44f98a5309e1f9d626902eafb46b13fb838706510cda5f01b68231。root 已讀結果issuer／same-subject cache／來源map／真group Result正例／replace拒絕測試；兩檔compile及targeted mypy無錯誤。唯一pytest於output/qa/composite_query_focused_20261010_attempt01，handle40490；root獨立觀測43992→52056→31832，fresh commit headroom9,478,979,584B，四個凍結pins匹配。raw stdout已顯示失敗節點，仍在等同handle原生終態，不宣稱通過、不改凍結檔、不重跑。capture改用實際PowerShell直取repo cwd，未執行的draft wrapper已移除，沒有第二次pytest。

L只加九欄初始contract明示scalar診斷與typed fallback；原gate與expected不變，fresh parent runs-l。root完整審K→L diff561185b3ff7f4438c74e681b8bb171eda3330eeab44600c8c63d5dcd7a841510，獨立核8artifact／6compile／新parent不存在；review manifest091adfce128691e8ce2c31cb6845c97d127f36d12999630b2d1ea719618ca65b。L未授runtime，等composite唯一終態後只跑新增一節點，其他十三個unchanged節點不重跑。

H20六role資料重新唯讀核查34個現存named-input與兩個缺席journal，共36路徑整组metadata前後穩定，沒有SQLite connect或source寫入。這仍是builder template/controller準備，不是Main／原684／圖表返回通過；template分組唯一性正在修正，須完整freeze後才授建置。

### 複合契約唯一測試原生終態（首紅保持）

handle40490 原生exit1，pytest121.16s，11 failed／3 passed／2 errors（wrapper123.204s）；receipt SHA9c19e10cc91b066592fc37e9d39b59c448d3d978b83b0bdf31d596b919f47273、stdout29567B SHAa15801c78691ff2ee6dee974dc5972e4c66b37ff0e9c4e349912ab99232b63f2、stderr空。root核完整收據、首錯trace及全部失敗分類；四pins起訖相同，commit headroom終態8,223,539,200B，三已知PID皆gone。

十一項均在測試_p01_query初始化被真query schema767拒絕：receipt_status complete卻pending_count1。兩actual-owner setup error是import exact_query未同時載入其依賴exact_p01_session fixture；尚未執行Result正例。已授test-only修正status partial（保留pending／excluded）與真fixture import，正式composite source2375保持。保留attempt01原件，待新test SHA／靜態檢查凍結後另授下一次，不放寬產品schema。

L等待窗口已結束；現只授新增一節點focused，不重跑原十三項，不授Main。H20完整三十四個named-input與兩missing journal重核收據已落盤，六role path唯一性仍須修正後交root靜態審查；沒有Main/build啟動或新EXE。

### 複合契約16案例分段綠與實際reader整合開始

attempt02 同handle66253原生exit1：15 passed／1 failed／137.74s，wrapper139.729s。root完整stdout1977B已讀，唯一首錯是在測試raises範圍之外先建立非中立F17排序，真契約正確拒絕。只移動該測試的raises範圍、保留float Decimal拒絕，source2375不變。attempt03僅修正節點1 passed／0.51s／exit0，stdout100B SHA8d2febae70ba94a0e3c00ab086bdf3c5fbbd9204b4f068ff9c5e876ced905ea4，receipt7ed705595b51b5017a0e41d1f79641215de864c13b3986b1e44c971f69b69a9。其餘15 unchanged未重跑；16案例是15＋1跨attempt覆蓋綠，不是同次16pass。actual public group full257原entries及真owner Result發行／same-subject快取／replace拒絕已實跑。

最終source2375f3703e93c2e26ca6477648e9ed0e679495c393ee7d47069f8b7f847e8a4c，testf78964823dcd67f62bbcef79c87d779a7af4d3a19a06477cb9555038462654b3；兩檔targeted mypy及compile綠。root新composite_reader_v1執行器開始full-N join／四組全域truth與unknown policy／三tuple來源／exact selected-page重新讀取與排序鍵驗證；尚未接正式reader且未runtime，targeted mypy與compile綠，不授OR/AND閉環、100k記憶體、300ms或UI資格。Luna Max另做唯讀審核；正式reader d494仍保持。

### L 新診斷真測試與唯一 Main 身分差異

L新增唯一node原生1passed／0.61s／exit0、stderr空，receipt84bec115dc12fbc2bbbef31e142405d734b72498cbe799476b49a15a4501ec6e，stdouta22ebc66e97272ea4353a73c92efad3d24bad2f719a7dbada66c03aa855e0c55；8＋58起訖匹配，fresh headroom6,883,696,640B。授單次L Main同handle91839原生exit1，封套evidence/20261010T034918Z_27436_1d3a1648；native6b978def589e42bdecd7f7be4529cb1d01bbef94bb8f7fe3fe454e136c8f2403，17.063s，來源after匹配／cleanup空／環境與guards恢復，receipt鏈27436→47092→29704終態PID皆gone（root未在live窗口觀察完整鏈，僅核receipt與終態）。

九項精確firstfalse只有query identity：expected cccf9aeaef309fc9bf579149390e14e840ae158c72d68e0972fa0e18d2b7410c，actual fa3ca96b56c9f617b2414bf36a5c593ba0a201f36623520de6ae7bd1dffa7368。declared258／visible258／current_only／unknown／PITfalse／page0／128／recipe存在皆匹配。先沿真query canonical來源、UI條件、snapshot路徑與舊oracle查原因，不直接替換expected、不放寬身份；收藏及新PID仍未完成。

### 正式reader API整合待驗與H20模板正規化首錯（最新）

composite契約／tests／本紀錄已提交0bb65fb6，未含新executor。root新executor source SHA f9b39afc2d2e8b201aaabceede839834744c06e0817a638cf291b6a2cce533d0，正式reader d59b32118a6b5cef1dc4a49a282531a907c3b3d4e55af780d379e40cea3b7d28（相對d494僅29行TYPE_CHECKING與兩typed delegate APIs）。兩source targeted mypy綠；未runtime、未提交，Luna Max正唯讀審核及準備full257 OR／AND／unknown／exactpage／cancel／owner負例提案。look-ahead邊界保持同issued group來源、snapshot／feature／cutoff，執行器只join已核事實、不重算金融證據。source availability unknown／current_only／PITfalse保持，不能宣稱100k記憶體或300ms門檻。

F12 L歷史58pins保持，不再以舊d494 pin執行新reader；下一候選須明示rebase／審新reader完整diff。L已清楚firstfalse query identity，原source成功；原因由真canonicalquery／UI條件／原oracle比較查清，不直接換expected。

H20 a靜態封套已回：template a6755493b4675d0720d5763daafb89a78c32a9bf90850c7a6ecedc870ce12d98、36path receipt f5cf3b79c3fecb4bc59258c0600284d9db40c68bfcbe1fd12521c28aa8d5f85e、controller973f369bdbcf63d9b669f49acf69a12142cb9d27d4c2328f1ac3b827697b0658。root讀完整controller差異並補讀截斷的launch綁定段，發現builder將role按字母排序，而原template順序非canonical；controller直接比較template陣列，合法build output必誤拒。尚未build，授b sibling static-only排序正規化與模板pin更新，保留a／36來源member值，不放寬值比對。另要求確認原十股public保存來源／2382廣達684bp→摘要→同capture圖表→返回真Main assertions；2382是股票代碼，不是2382檔母體。現候選的builder dual-copy environment不是完整dual-copy驗收證據。


### S4 真來源快照建置完成；複合取消修正與 F12 oracle 診斷

root 建立 S4 非 source-only approval，SHA4346660f3a9fbdd414978e169a89c6c96a7fd857215894ad1de83050804e2a5e；保留既有22 required pins/profile、九個實際 overlay，逐項 size/SHA 核對。真 builder 單次原生 exit0（handle26313），產製 s4/source 4161 files／77,229,228B。manifest SHA2d259ecb468af0833b1c6638e917f278b1079b8158cb6302795c259f934a6188、launch_inputs SHAb3ca6f3c60a31720cd78dc60d420d4ce66f6227c6eedccfeb8d8c2a3ff00ceeb、source archive SHA25d98adafa4898879f784e18b8cadf0e02e58748e5f4555a61deee61754b536b；root 獨立重新雜湊三檔及確認 approval 正規化 template 完全等於 b。來源 Main SHA813fa8c4c2349cc295e590a2ec867e5ac01d76b84b1c8a6363027f0a8c70f5c9。建置 external_source_groups_opened=0／sqlite_connections_opened=0／main_started=false；內部 approved_for_launch=false 與三驗收 pending 保持，這不是真人批准阻擋或 Main 驗收通過。

b sibling 模板 SHA258da4fa22e0c6bdfd19448a245b2b8545e98ceb87d4330cdfef0262fb53fb65、runner ca3a267f59002bf4a333f4e24eac028ba9339fca9f87d3df9644eb3a64b19eb5、完整 a→b diff4bbfeac495981f488402c42df1213e8c246dd1a7722d769292bd4599ab746576。六 role canonical 順序 activation/calendar/config/h20_db/manifest/market_db，其他值不變；a 保持。child 靜態確認包含真 MainWindow、公用 cohort 十股與2382原684bp／三日期、真表格 signal、同 capture chart/table、返回原 manifest/selection assertions；尚未執行。它直接建 MainWindow，未走正式 main()/startup/preload 或完整 dual-copy supervisor，故不可拿此窄流程授 full Main qualification。

root 修正 composite page 下層 BundleError 的公開例外映射，先 _check_source_error_cancelled，再包 reader page-specific error；不漏出 BundleCancelled。executor 最新 SHAa4abab6737bfd9685ae50784a17a98abb51960c17d20be34d0c3a2173c1cfe0b，formal reader d59b 保持。兩 source targeted mypy 綠；尚未 actual executor runtime。Luna Max 審查 full-N join／OR hard gate 無其他必然阻擋，已轉準備 real full257 integration test 候選；不把靜態審查算 OR/AND／256+1／取消／100k／300ms 通過。

F12 唯讀核對查明 expected cccf 來自舊 attempt04 bookmark，而 L 本次 seed 是206-byte空清單。月營收 read-session identity 包含 snapshot_id 與 reader DB path，真 snapshot 每次 uuid4 新建，因此跨 attempt 固定舊 query hash 不可作同 session oracle。L 沒保存四個實際月營收子身份/canonical body，不能把完整差異推算成已證明。下一 M sibling 保留 L 原件、舊 gate/expected，追加受限 typed canonical fields 的逐欄診斷與明示新 reader source pin rebase；尚未 runtime，不直接替換 expected 或放寬正式身分驗證。


### S4 外部六組來源核對缺口（啟動前補齊）

root 重新讀 b controller source_input_inventory 全文：它核原十股 capture/H20 DB 與相關引用，但沒有遍歷 S4 template 六 role 全部36 named-input，故 JSON template 相等不能證明執行當下 market/calendar/config 全部來源仍匹配。尚未啟動任何 child/Main；要求新 C sibling 在 child前與after以整組 metadata-before/hash/metadata-after核每個template member的existence/size/SHA，保留b原件、不照抄template當實際核驗。不改正式資料。

資源唯讀當下 commit headroom10,040,631,296B、Cfree252,461,826,048B、Efree181,252,952,064B；這不是下一次啟動的fresh gate，啟動仍須現查。S4新增的隔離來源/封套約百餘MB，不是8GB原始DB複本；未搬移其他資料。三Luna Max仍分工準備H20補充guard、真full257 executor integration test與F12受限canonical fields診斷；完整產品與真人驗收資格均保持待完成。


### H20 私有讀取根接線首錯與 C 靜態修案

代理完成對 frozen config/Main 的唯讀核對，b child environment 缺 PERSONAL_H20_SQLITE_READ_ROOT；config 回 None，Main 因此不啟動 cohort worker。這是 QA 候選的私有根接線缺口，未 runtime，不能歸為正式原來源失效。root 授 C sibling static-only：新增 case/research_state/personal_h20_sqlite 私有目錄及明示環境參數、納入 existing_dirs guard；另做六 role/36 member 整組前後metadata與actual hash驗證及負例。保留b／S4原 pins/caps／frozen正式來源，不以補參數放寬讀取器。

正常Main會經真 pinned read session把H20 source 4,054,339,584B複製到私有 reader.sqlite；market 4,061,761,536B只做檔案雜湊且SQLite連線被guard拒絕。這是必要的合法私有讀取副本，不能將S4 builder的零DB複製描述延伸成Main亦零複製。單次copy已有 main_size+8MiB disk gate；controller外層另需fresh commit headroom至少2GiB及足夠磁碟。C不得以JSON輸入清單取代actual source重核，尚未啟動child。


### 複合正式 reader 五項真整合測試進行中

root 完整審閱Luna Max凍結候選461行，SHAea8443f1caba0fbc8a8863e4973de0cfcb6ab71f2cf56c039cbfabceacd3d157，安裝到 tests/test_daily_market_technical_official_disposition_composite_reader_v1.py（原路徑不存在，沒有覆寫）。collection-only原生5 collected／0.51s／exit0。兩owner均由真public projection_group opener建立完整257 included+1 excluded，不stub正例；OR由反向concrete P01狀態與concrete KDJ可接受狀態救回、AND交集拒絕；all-inactive audit母體258驗256+2；MA未知政策include/exclude；execute延後取消及selected-row真委派spy取消不回partial。這五項尚不涵蓋MA具體match、volatility OR、null-tail/tie、page request重開、wrong-owner矩陣或100k/300ms。

唯一runtime封套 output/qa/composite_reader_focused_20261010_attempt01，同handle21297；全新隔離DATA_ROOT/OUTPUT_ROOT/temp，不碰正式D來源。fresh commit headroom11,503,423,488B，五expected source pins匹配：testea844／executora4abab／query2375／readerd59b／groupb976。root獨立live觀測41796→32240→30516→5184，wrapper running receipt32240/30516。尚待同handle原生終態，不能先記通過、不重啟、不改凍結source/tests。另授代理新sibling static補尚缺sort/reopen/owner負例，不共編已啟動的五節點。


### 複合 reader 五項真整合原生通過（169.33s）

唯一handle21297原生exit0，pytest5passed169.33s、wrapper171.485s；stdout112B SHA6368633134aea7607f7665ff20b131a495f055b947a07e415be7b57d590ad009、stderr0、receipt SHAc947b58c3ce558c83861c2be694ee77f4c31d09388a4802366641f1b1c0368ad。root讀完整stdout/receipt，獨立重hash比對及核五pins起訖一致，32240／30516／5184皆gone。真257母體technical no_match由KDJ OR救回、AND拒絕；256+1 processed頁、全inactive258 audit的256+2頁、全域MA未知include/exclude、execute中途及selected-row公開取消皆實跑綠。這是正式typed API/backend資格，不是正常UI／收藏新PID／Native EXE／真人或100k/300ms資格。既有來源availability unknown/current_only/PITfalse保持。

來源executor a4abab、reader d59b 與testea844已凍結。下一葉片只補尚缺sort/null-tail/tie、page request重開、wrongowner/query/group/pin矩陣；原五unchanged不重跑。H20 C預審另抓到members-before與hash交錯（須先整組36metadata再hash），以及負例fixture6present與36/34/2 gate不符（須真34present+2missing）；授靜態修正，不放寬production gate。尚未執行H20 child。


### H20 C 實際小型驗證與唯一自檢首紅；D 接線修案

C 最終freeze receipt3c0548e1a7d6fe40746c83d5852dd3725132cc4097a5a399c738e2e98fd6eabe；controller7447192e2d799c5cb088b7d302b576cdebbcbeb310fa3209e8bb109b5604cb73、testc666995a4ca57a0943ae2104610a3a9bc918007ac5b8cc90383db67db865ee27、diff8ae458898decefca5493617971bbaa7e5f2dc5b08a189995d5a026cb4cb30bf1。root實跑十個focused小檔測例，原生exit0、Ran10／0.871s／9pass1skip（symlink creation unavailable OSError，未宣稱reparse真實檔負例通過），receipt723bd36428f5541295df46edbddaa06dd91f8b30057b497b378f00b7f91ea5d4；七candidate pins起訖相同。前一次舊freeze SHA拒絕在任何子程序/attempt建立前，沒有重跑測試。

root獨立核33個S4 source module size/SHA、candidate七pins、D9 guard/runner及manifest/launch，fresh headroom11,608,776,704B、Cfree252,141,445,120B；唯一C完整controller同handle13930已原生exit1。root live觀測58860→43352→43656→59540；wrapper42.422s，native attempt20261010T041504Z_7e3da4221e03 controller42.329s，guard child0.282s/exit1且未timeout，child_result null。完整trace首錯在baldr_launcher.run_path→child.install_read_only_guards：canonical_probe_private_sqlite_root_required。MainWindow及原十股cohort尚未開始，不能記2382/684bp旅程通過。

root獨立核wrapper receipt059e737e090b4dcf97310d957534f2598127c432ff6f5e6b9e6efb265e83eec0、stderr517B SHA3ce5a73a8415f928bc6ddc7167e62cc2826f6bd4edb8f2e923d8037c173f90ca、stdout空；candidate/source全部起訖不變。native controller SHA5a6a31b50cfef8c4cee19a54f5fd957de81c2f7a3527305e12ecca0b2747162e，六role實際兩輪核驗完成且unchanged=true；已知43352/43656/59540/38636皆gone。guard要求H20_CANONICAL_PRIVATE_SQLITE_ROOT是exact case/private_sqlite_read，C只傳PERSONAL_H20_SQLITE_READ_ROOT且指別處。授D sibling static-only將兩參數指同case/private_sqlite_read及guard existing dirs，保留C與S4、不改guard、不放寬根要求。

### 新六節點測試已凍結並啟動；營收 N 排除 scope 外差異

root完整審edgecase259行與volatility162行，安裝新tests來源（原路徑不存在），edge9b6945c4b6c66cf7dbce6b784f1d1561bee93acacf5034d33f92c089d38ffa19、vol93d4f0e9ff51b6ff842cf18ab9dd4dd04275e97254a983a6048016eb3003e48f。collection原生6collected0.91s。覆蓋null-last、預設asc與明示desc tie、JSON同result page request重開、錯query/session/group/pin拒絕、真Decimal bandwidth min=max救回P01 no_match的OR與AND拒絕；不是bookmark fresh PID。原五已綠unchanged未重跑。

唯一runtimeoutput/qa/composite_reader_focused_20261010_attempt02，同handle4474；fresh headroom11,090,501,632B、七source pins匹配，全新隔離DATA_ROOT/OUTPUT_ROOT/temp。root live36480→15076→56496→42500，尚待同handle原生終態，不重啟、不改凍結source/tests。MA60另授代理新synthetic源在producer前建合法60session，重建全部generation/clock/receipt/bundle，禁止改舊40來源後沿舊pins。

root審M L→M diff發現fixed_inputs cutoff非必要改成local時區字串，雖同instant仍超出授權診斷/rebase範圍且可能改canonical bytes；M未runtime。授N sibling恢復L精確UTC、全新runs-n與自識別hash，保留M/L。N靜態交付receipt e37c841ac226ea40b78b8f4a9e385a8d37d686f153a3825bab822a265cc63bc9、M→N diff595cfafbf283d7e2fb53dec61f58ea7a064326e71841e06be066565e691153e5、L→N diffc420782a61b1be64e636965dae4353a9d806a2e0fafcf121b29b499f58a67574；尚待root完整審查，未focused/Main。原gate與expected cccf保持，不能以session/path變動直接改expected。


### 2026-10-10 原生終態：組合排序測試設定首紅、H20 D 啟動保護與營收 N 診斷

組合 attempt02 同 handle4474 已 exit1：3 passed、3 errors／317.10s，七來源 pins 起訖不變。三個 errors 共用同一 fixture，在 query.create 即拒絕 stock_code desc（stock_code_tiebreak_invalid）；既有契約要求股票代碼作最後升序 tie-break。這是測試設定與既有契約衝突，未取得排序、page-request reopen、wrong-pin 三項資格。KDJ 預設升序 tie、wrong-owner 與真 volatility OR/AND 三項原生通過。保留原 attempt，不放寬正式 sort validator；授代理建立合法排序 sibling 與 desc 拒絕負例，待 root 審查。

H20 D 唯一 controller 已 exit1，wrapper source_pins_unchanged=true。native attempt20261010T042131Z_405ccc9fdad8 完整 trace 首錯是 D9 guard line347 canonical_probe_runtime_log_allowlist_required；仍在保護自檢，不能記 MainWindow／原十股 2382／684bp 下鑽通過。授代理先逐項核對 guard 與啟動環境 contract，再交最小 E sibling，不修改 C/D 或正式 guard。

營收 N 三個 focused 原生3passed、37deselected／0.68s、exit0。root 獨立核 stdout SHA1b2cdd3b4cd85914685ef792b3d9388cf2667e27347eaeb4801c5796528b6206、stderr空、8 candidate與58來源 before/after一致。其後唯一正常主視窗驗證 evidence20261010T042525Z_40736_15b13afd 已 exit1，native receipt run_attempt_7108432794e144dea4ce08c34e7624fe/f12_main_revenue_receipt.json。實際 monthly readonly transaction 核驗通過、source_inventory_unchanged=true；原 query gate 保留而拒絕不同 hash。65項 canonical projection 完整 captured，僅四個 monthly session/index/cohort/source-clock identity 及總 query identity 不同，其餘60相同。actual ecf4a2c19ed73c8ca3509b4f63e6bb619aa65a74d2ffe6fb2495b33610508a03 與歷史 expected cccf9aeaef309fc9bf579149390e14e840ae158c72d68e0972fa0e18d2b7410c 不同；下一步以同 attempt 真正核驗的來源 session 構建獨立 oracle，保留固定條件及來源資格，不能直接採用 actual hash 充作期望。收藏新 PID 尚未抵達。


### 排序最小修案四節點原生通過，MA60 真 match 單節點啟動

使用者暫停後明確恢復。root重新核工作区所有權，其他文檔／排程agent變更保留。edgecase sibling僅改合法 kdj_state desc＋最後 stock_code asc、对应升序断言，新增 desc stock-code 拒絕負例；正式validator未改。新test SHA8c66ff79ffee15a1b4ad7afe5b19163f2c9ccddcb582d20595048e0ba1a6783f。唯一attempt03同handle96431已exit0，4passed、2deselected／153.05s、wrapper158.343s，stdoutSHA02864fe363676759c2dbd036415ed089448c8b409f24f5f5f61edcbff0fee808、stderr空。root獨立核stdout/stderr hashes、七pin before/after一致；實際live11972→33956→19300已皆gone。與attempt02 unchanged已綠三節點合計七項覆蓋，不稱一次七項全跑。相同known KDJ值可證降序選項被接受、null-tail與asc tie，不證多known KDJ值的相對排序。

root完整審MA60原403行與strict sibling diff，獨立核公開MA index屬性。固定遞增close80..139 oracle強化為實際ma_state=match、reason ma_alignment_strictly_descending、warmup60及prefix連續；不動態接受no_match。新formal test tests/test_daily_market_technical_official_disposition_composite_reader_v1_ma60.py SHAaa79e88d21a841ee432a370da2eaf106aa7d4450d41317f9b8340cb26db517e2。唯一attempt04同handle38762啟動，fresh commit headroom42,260,983,808B、七pins匹配，root live18852→9552→27180→32556。完整全新DB／producer兩segment／exact store／新capture／bundle／public group重建。60列只是合成觀測窗，不是官方交易日或crossover；原5357候選保留。尚待原生終態，不能先記pass。正常Composite UI／typed bookmark／新PID／真人／100k/300ms仍未完成。


### MA60 固定真 alignment match 原生通過

attempt04同handle38762原生exit0，唯一node1passed146.40s、wrapper148.312s。root完整讀stdout，獨立hash stdout112B SHA8b5f26cc3670d6a62daddaff2144c751a7a5b14d7e351cd24f612a95e1d1a930、stderr空、receipt SHAd2ce7aece57b4755c1a4d616cce39e03fb3753c77b01df4aa11aac078ccf46a7；七pinsbeforeafter相同，9552/27180/32556皆gone。真全新257+1producer/exact store/bundle/public group鏈，target1000的固定60close80..139得到ma_alignment_strictly_descending match、warmup60/contiguous；technical no_match由MA match OR救回，AND不入選；總母體與來源時鐘不縮減。這補足具體MA match evidence，但不證官方60交易日、真金融來源、crossover、其他256都match、正常UI、freshPID收藏或100k/300ms資格。


### 正常 Composite UI 的來源入口候選（尚未安裝或 runtime）

Root核現有MA view _execute_new_query：bundle_session_v1只綁ma projection，不能先開舊session再重開四群組造成雙次全來源讀取。新增QA-only候選 output/qa/composite_bundle_opener_candidate_20261010，base正式readerd59b不變；候選reader SHAa08d30b084e35dc1eec25c2a9207bdd7a159f8d047d3bb3387e3897bf27e4df9，AST通過。新增explicit open_daily_market_technical_official_disposition_bundle_projection_group_session_v2，與舊bundle opener同kwargs、保留舊函式全文；metadata核pin→單次builder/full bundle exact-read→真bind_projection_group→既有issuer；cutoff從原manifest/source clock，不用latest/現在時鐘，外層hardfilter及P01條件保留，所有post-read失敗與取消均poison群組。尚待獨立review、必要實跑、正式安裝及正常UI接線，不記功能交付。

跨PID identity唯讀追查顯示P01/group/composite canonical identities沒有PID/UUID；新Composite bookmark先採完整source/query/result/page/row strict exact重開，不因月營收ephemeral snapshot案例先略過group/P01 IDs或另造寬鬆stable identity。須真正freshPID資格測試，若不同先拒絕診斷，不自動接納。Luna另交typed presenter候選、H20 E env focused tests、F12 O同attempt source-qualified oracle；正式reader仍d59b，O58pins保持該版本，後續新增需明示rebase不改凍結receipt。

回滾範圍：目前只新增ignored QA候選與本任務QA紀錄，正式reader/UI未改；候選保留原base SHA及完整diff，可停用候選、不動正式來源。其後正式API變更僅由root安裝並另驗，其他agent dirty文件不覆寫。


### Composite 顯示投影真整合與強制 UI 檢查

root已安裝typed presenter（SHA288725c3a14a4bd7a26889b98fef6bbe61ac7da89629f32cc7849753d34f097d）與四項測試（SHAc265d61f151b36e1e58257612d44e81ef08d85fe131aee657b56d7195b0c9a4e）。attempt01因紀錄器沿用舊-k選取而4deselected/exit5，保留原封套；修正紀錄器後唯一attempt02真4passed149.20s、exit0、來源pins起訖不變。驗證真257母體及258 audit、全域counts與頁面筆數分離、四群truth/理由/保存數值與精確Decimal；拒絕未具typed資格輸入。仍未接入可操作View，不宣稱正常UI交付。

強制檢查attempt01：更新工作台85passed4.42s；qa_validate_update_tab exit0；完整8根mypy檢查938來源檔無問題。py_compile在QA長路徑輸出遇Windows路徑限制（exit1），保留原失敗紀錄；attempt02改明示QA短檔名cfile，兩檔皆編譯通過、SHA起訖一致。沒有修改產品程式來迴避檢查。

H20 E guard focused原第一attempt3pass1skip、3QA f-string錯誤及1長路徑失敗；只修正QA literal braces及縮短attempt路徑，四個原失敗節點第二attempt全pass0.421s，合計七pass一skip，未宣稱同一次八項全綠。E完整Main的guard已通過，但0.328s因QA helper ambient import缺失結束，SQLite/訓練/預測計數皆0；原來源及封套pins保持。F sibling只以同目錄普通單鏈檔及SHA載入helper；root已實際抽取執行loader並成功取得callable，不改sys.path/guard/S4。F完整Main唯一attempt已啟動，尚待原生終態，不記2382/684bp通過。

回滾僅限新增presenter及其測試、本任務QA紀錄；尚無其他正式模組依賴該presenter。其他agent文件與正式資料不納入回滾。


### H20 F 真正名單載入仍超時，保留效能缺口

F唯一Main封套原生exit1、wrapper125.563s，所有candidate/S4來源pins起訖不變。guard通過，helper載入缺口已消除；真正Main開始initial_full_cohort。trace在82.953s仍核驗原4,054,339,584B來源，103.032s完成建立4GB安全副本；104.016s開始shutdown，106.141s記canonical_main_stage_timeout:initial_full_cohort。90s stage gate未放寬，worker因shutdown取消，尚未完成十股名單或2382下鑽，不能記原684bp與三日期/同capture圖表通過。下一步需分清全檔核驗、複製、終態重驗及UI progress耗時，提出維持來源資格的修正；不借先前hash、不改90s成綠、不重跑同款失敗。

顯示投影與四測試已保存本機dev提交7131ae29，未push。正常Composite View與typed bookmark候選持續由Luna Max分工，營收O來源qualified同attempt oracle仍待交付。完整產品補完與真人EXE資格保持未完成。


### F 等待成因細分：重複副本建立尚待小檔定因

root逐項讀worker_progress：核驗/複製階段反覆重新從0開始，8次copy、前7次到準備讀取副本，未見任何reader_transaction_ready。正式operation成功後應按canonical(path,SHA)共用session；open_copy失敗未寫入session快取，後續capture可再走複製。F child外層guarded_connect僅接受原來源RO和3個runtime DB，沒有明示委派D9既有private reader.sqlite RO分支；這是待小檔證明的QA guard疑點，不能直接歸為正式產品每檔必複製或未來函數問題。Luna H20改優先核對精確D9契約並交G最小候選/負例，保持S4/guard/90s/原資料不變，不重跑4GB猜測。


### F 反覆複製定因：QA 外層 SQLite guard 誤拒私有 RO

root獨立讀controller_receipt.main_journey.child_result.final_guard_state：private_sqlite_directory_created/removed均8，sqlite_connections/mode_ro/query_only均0；extra sqlite_denied10，8個target IDs均database_not_allowlisted。S4真reader在copy後以reader_path.as_uri()+?mode=ro開啟；F外層只允許原source及3個runtime DB，拒絕合法私有reader，故open_copy失敗後下一capture重建。這證明本輪8次副本/超時包含QA守衛缺口，不是正式產品正常流程耗時證據。G必須只對同case明示私有根/pinned-sqlite-32hex/reader.sqlite普通單link/no-reparse的RO URI委派D9真guard，其餘拒絕；先小檔正負例，再單次完整Main。既有90s/240s、S4 source、D9原guard不變。未到2382下鑽，原人驗資格仍待完成。


### 單次 bundle 四群來源入口候選實跑與 O 審查退回

root以AST移除唯一新增bundle_projection_group_session_v2函式後，核候選reader與正式d59b AST完全相同；專用QA child只將已讀完/已釘選a08d新增函式載入正式reader namespace，保留真DTO/issuer及正式檔案不變。兩項測試封套composite_bundle_opener_focused_20261010_attempt01、handle13432，fresh commit headroom38,075,555,840B，live30360→6028→24060→3308。真257+1 fixture驗單次exact-read/完整group與取消beforemetadata，尚待原生終態；這僅候選function runtime，未授formal安裝或正常UI資格。O58pins仍d59b。

O static freeze bc338d87dbc44560ee9073f3f20f4553c20074af54b9b9ffda99352f2399069d、diff8b7950d580e677bb24c410f89c078eb22fd16605c6a3acf8496ad7c8e1ca0a3e、review manifest b88a65bd8b4b3f6c3a89a1af4469e08ef04c436723e1979d3a9b723817d91e36，root獨立SHA核與8candidate size/hash一致。審閱退回兩個必然阻擋：technical_query_json誤與外層f17_query_json互比；top-level source reference無declared_stock_codes_sha256卻與nested snapshot hash比。root實際讀原90327B bookmark確認top-level hash為None、nested hash98ac5b5278e6e1db5fb25a6a5de4635b499a082559840c8bf1ca671a7a12926f。O沒有runtime；要求P sibling精確修正nested canonical JSON及canonical codes hash，保留原資料/58pins/recipe資格並增真bookmark正反例。


### Bundle 四群來源入口候選兩節點原生通過；收藏契約唯一封套啟動

handle13432原生exit0：2passed143.37s；root獨立核receipt/stdout/stderr及七pins起訖一致、當下formal reader仍d59b。正例真producer/257 included+1 excluded/exact store，全群一次bundle exact-read，三indices皆257、全inactive audit258之256+2頁，頁面後exact-read仍1次；取消beforemetadata正例無來源讀取。新增function透過已驗AST等價的QA child執行，尚未formal安裝，未取得UI/真人/100k/300ms資格。

root逐段審bookmark53KB來源及6節點tests：保存完整37pins/query/group/P01/result/count/request/page/row原身分，fresh PID經真projection_group opener重發、逐一精確一致才接受；真shard bytes變動拒絕且finally只還原本次合成fixture，before-open與first-page後取消不回partial context。candidate SHA df4d44e52ed4cff8e076701486cbdfff3b2e88cbc14d7fbe0d16ae0ca0005fc6、test SHA68aee77b40165b864ca45afa13b38ba1bd506f16fad87dba0ba6ba6d0872535e已root實核。唯一composite_bookmark_focused_20261010_attempt01、handle88069啟動，尚待原生終態；正式模組未改。新View的原comparison basket membership還需依MA既有契約保存，不能因selected去重而自行增刪原籃選取。

### 收藏候選六節點通過；正式模組接入與營收 P 首紅

候選封套同 handle88069 已 exit0：6passed／177.42s、wrapper178.203s；原生stdout SHA b1ae89f90dc573a9be933e11f9f40b86a23264128bb77a0c3e124315d5f3f8cb，stderr空，七個來源 pins 起訖不變。覆蓋真正新 PID 完整身份還原、來源 shard bytes 改動拒絕及兩階段取消；仍不代表正常 UI 或收藏儲存入口已接通。

root 新增正式 `app_module/daily_market_technical_official_disposition_composite_bookmark_v1.py` 與對應六項測試。來源保留候選契約，兩個 factory 改用明示 typed kwargs，immutable anchor 的 slots 補型別宣告；未變更來源開啟器、條件、時鐘或身份核對。首次 mypy 保留 13 項型別錯誤紀錄，修正後單檔 mypy 通過。正式模組 SHA f9112c0cc5455a769ca66d4666548f805c66bc6c58615959f118c665b701c06a、測試 SHA 1ce30c9d87ce7374a40a9f1eac7b947af521d95066fcfbe2f131d284d974bafa；正式六項 runtime 封套 `composite_bookmark_formal_20261010_attempt01` 已啟動，尚待終態。既有 formal reader 保持 d59b，營收58來源 pins 不改。

營收 P 的凍結五節點封套 `f12_main_revenue_new_pid_20261009_p/evidence/20261010T050805Z_16644_8e0d393f` 原生2failed、3passed、38deselected／0.88s、exit1。首紅 `expected_query_recipe_f17_conditions_not_historical`：投影新增內層 technical JSON，但固定 recipe 的條件對照尚未匹配。尚未啟動 P Main。root 獨立 postflight 再核8候選與58來源檔、原生stdout/stderr hash皆匹配，保存 `root_postflight.json`；這只是來源保持證據，不把首紅改記通過。已交 Luna 建 Q sibling，P 原件與失敗封套保留。

H20 G 僅 QA 精確私有 RO 委派候選，最新凍結 child cd782a03e84a9aa8bc898eb8de3fee138733f1e059c6e0850e4db3a24232b523、九項 helper test 0ee1ce39b3ce3a4b18b942aaf13ddf93c06b9f50d3d4f16a9a929de288bd27f2。前一則 subagent 凍結宣告與後續補負例版本不一致，root要求停止修改並重新明示單一版本；尚未執行 G。root 審閱真 D9 callable 委派及 query_only／檔案身份核對，將先小 fixture 與 guard preflight，不直接重跑4GB Main。

#### 本次新增檔案回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
| --- | --- | --- | --- |
| `app_module/daily_market_technical_official_disposition_composite_bookmark_v1.py` | 新增 | 先停用其本次新增呼叫，再移除本次新增模組 | 正常 View 尚未接入；後續接線後須一併回滾依賴 |
| `tests/test_daily_market_technical_official_disposition_composite_bookmark_v1.py` | 新增 | 隨本次模組回滾移除新增測試 | 不影響既有正式來源或其他測試 |
| 本 QA 紀錄 | 修改 | 僅還原本次附加區塊 | 保留其他 agent 文件與先前失敗證據 |

回滾順序為確認檔案所有權、停用本次接線、回滾新增模組與測試、驗證既有來源不變；ignored QA 封套維持留存。沒有新增金融計算或資料日期推論，還原仍限定保存來源與原決策時鐘；不能以最新資料或收藏本身補給資格。正常 View、typed 儲存入口、真人版本與效能門檻仍未完成。

### 正式收藏六節點通過；H20 G 真守衛預檢及營收 Q 進展

正式收藏同 handle8313 已 exit0：6passed／186.47s、stdout SHA 7d0433a3d709a3d4e49cc86465e59b5a65b2b6a7d279420c8e593a371c6e4581、stderr空、七 pins 起訖不變。root 另逐檔核目前 SHA、原生收據及 stdout/stderr，再保存 root_acceptance.json；單檔 mypy 與兩檔指定短 QA cfile 的 py_compile 通過。接受範圍為正式收藏契約及真新 PID 重開，不含正常 View、Watchlist 儲存入口或真人版本。

P 首紅的精確原因補正：原 pinned bookmark 的 F17 decision_cutoff 為 `2026-10-07T16:00:00+08:00`，固定 recipe 原為 `2026-10-07T01:00:00-07:00`；兩者皆與固定月來源 cutoff `2026-10-07T08:00:00+00:00` 同一時刻，但原有 exact spelling gate 拒絕字串差異。Q 只從原 bookmark 修正固定條件字串，未修改月資料 cutoff、精確 equality 或資格限制。Q diff ebf26a946c0eba08ae448675167de15e4432564e1f23c88ff1423c4663dc67c1，review manifest 042791b22e5932772090e934c508b7c49934950509b92ed6ff41a0c27acc5447。五項 focused 原生5passed、38deselected／0.57s；root postflight 獨立核8候選＋58來源皆匹配。

Q 唯一 Main 封套 evidence/20261010T051334Z_4036_d8335313、native run_attempt_fe527c1bda41416b921e14ac1c941e1f 已 exit1。真 native PID38260、parent9036、wrapper4036，原生 chain=venv_redirector_child／無驗證錯誤。全部65項 source-qualified query oracle 精確 matched，來源核驗保持；下一個首紅為 f12_first_page_basket_invalid，未取得收藏新 PID 旅程資格。root 交 Luna 對照實際 basket 操作與正式 UI，R 必須另建 sibling，不能跳過 basket gate 或覆寫 Q。

H20 G 小檔九測試8passed、1 Windows symlink skip／0.52s；guard preflight 原生 exit0／18.188s，真 D9 私有 RO connect/query_only 增量各1，7個非法 request 在 D9 前拒絕，ATTACH／query_only OFF 由 D9 authorizer 拒絕。私有 fixture 目錄建立／移除1／1、沒有 private open failure；原六角色 source groups 完整核兩輪8,119,601,144B，起訖一致。這是 guard 接線資格，不是原 H20 名單已通過。

G 單次完整 Main 封套 `output/qa/run_h20_s4_g_main_capture_20261010.py` SHA 4cf39cbc9c8889ccf09c6e443b51fe00153084ac46cdae7081962f645eac18d8、handle87905 已啟動；重新核G／S4／D9與fresh commit/disk gate，維持原90s／240s及全來源前後核驗，尚待十股名單及2382下鑽終態。Luna H20 轉接 P01 既有 raw profile／memo budget 的只讀診斷；Composite View／獨立儲存 route 由另一位 Luna 持續，正式 reader 仍 d59b。

提交前 whitespace check 指出新測試檔尾多一空白行，僅移除該空行；最終 test SHA bd2b3400e9ad15dc9541ae2b50599fab54809a67abc8389eb3156e8815c337d3，執行時原 SHA 1ce30 及收據保留。沒有改變 AST 或測試斷言，未為此重跑完整產製；staged diff --check 通過。

### H20 名單真正完成：舊 QA 回傳及下鑽契約需要對齊

正式收藏模組與六測試已保存本機 commit 4fb3a3b8，未 push。G 完整 Main 原生 exit1，原來源與 pins 不變，單一 private RO connection、private open failure0、私有目錄建立／移除1／1。root 後續精確讀 trace：cohort worker 在28.125s回傳 `PersonalH20VerifiedCohortView`，worker duration15.453s；QA `_worker_summary` 只解析舊 `(reference,cohort)` tuple，故沒有 row_count，完成 predicate 永遠不成立。G 的90s timeout不能當成正式產品讀取卡住證據。

H sibling 只新增每30s原生執行緒堆疊觀測（child SHA2668157e3296f75c9ba3ca0381da9642f490e6e9491372033cebadaa11d7436c、diff af0479e84a32be24c5718fe4b564b8cc711d7acc3eae14ab156239182c2aa147）。同樣來源、D9與90s／240s不變。唯一attempt 20261010T051901Z_caa69b036f1a 原生exit1，cohort在25.281s完成／duration15.141s；30s stack只剩主執行緒在QA wait_for，沒有仍運行的cohort worker。外部完整來源核兩輪不變。這支持 QA predicate 問題，沒有修改產品或原資料。

I sibling 接真正 `PersonalH20VerifiedCohortView`，先呼叫原 `assert_personal_h20_verified_cohort_view` 核 seal，再從 `value.cohort` 取rows；三處cohort完成gate新增 reader_issued_view_verified 必須為true，沒有接受未核tuple或像型別物件。child f31eb39ef79b55db36aaeed2e29437a6fbf95eb7d69dfc3b376ca32be9a0d398、diff7ef9e2fbd4b86800ece67765241af5bd0b0a492e3a3b4610a14984fd635108ce。小檔測試第一封套1pass1fail：實際public fixture因tests sibling import未定位而未執行；保留該失敗。補明示tests fixture路徑、隔離DATA_ROOT並改fresh短C:/t/h20i2後，原失敗正例1passed4.06s，原negative unchanged；真單股合成public reader seal正例1234bp與tampered seal拒絕皆通過，不能取代原684bp。

I唯一Main 20261010T052245Z_5f5e4b70183c 原生exit1，來源起訖不變。名單真正通過：10 rows／10 available／0 unknown、原manifest a2cad4b3…e76、2382 684bp，三日期10-07／10-06／10-05精確一致，initial_cohort16.547s。真Qt單擊＋雙擊2382已觸發；`PersonalH20SelectedProductProjectionV1` worker在0.156s完成。下一個QA首紅 `double_click_refresh_started` 仍期待新的cohort worker，但S4正常路徑已沿用同次sealed view、只發行selected projection；返回同樣使用專屬 `_personal_h20_return_worker`。需J精確更新 QA 對此真流程的判讀，保留source/reference/selection/chart及684bp/三日期，不再以舊重建cohort作完成條件。完整圖表與返回尚未驗收；不把名單局部通過標成整體H20完成。

### 暫停後續行：營收 R 點擊與 P01 診斷初次實跑

使用者明示繼續；三位 Luna 分別處理營收／H20 QA 契約、複合研究 View 與收藏儲存入口、P01 實際 memo counters。root 保持唯一正式整合及 runtime 執行者。

營收 R review manifest `54db301048287d4bece677c8b78cc2e9d43904ef303ef04cb2d8d7989204a1d9`，完整 Q→R diff `fd9f37ed80732eb4a30fc06b23dcffd8f34e03a6dec3f18870fb6eae862151ef`。root 全讀新可見 viewport QTest mouseClick／精確 typed row／頁碼契約；原 58 pins 不改。第一封套 `20261010T052806Z_30432_e11dd550` 因沙箱 WinError5 阻於 bootstrap，沒有開始測試。受控執行的第二封套 `20261010T052820Z_16756_e9be296b` 原生 exit1：5passed、1failed、38deselected／1.38s，stdout SHA `44a1ce0f8dcea32524491ee0af500575a2988806cb72cdf25120c0ceb6406a79`，stderr 空。新測試真點擊精確選列已通過，但加入比較籃仍為空；需核對產品 handler 與 fixture 的啟用條件，不能跳過籃選驗證或直接跑 Main。R 原封套凍結保留，要求另建 S。

P01 counter probe A script SHA `0778362f07fd5f8637329dc3a90fe6fa18b0b94a5e9b846dcb05d325d747d8b9`，root 已審其 observer 委派、quota-zero 對照、來源及 published page/query/selection pins、操作後清理。首次執行 exit1，失敗在 `_read_candidate_manifest`：controller 仍讀原 manifest `e17582…`，但 probe 期待明示 runtime overlay v3 `f0e639…`；尚未開 verified session、沒有 DB 操作或 page invocation。失敗收據及原始 stdout/stderr 保存在 `output/qa/p01_memo_counter_probe_20261010_a/`，要求 B sibling 精確修正明示 overlay 路由並恢復 controller 狀態；不修改原 runtime、資料或效能門檻。這次沒有任何 300ms 驗收結論。

### 營收真換頁產品缺陷與 P01 cache 診斷證據

S 僅修隔離 Qt fixture 的載入後按鈕狀態，原產品 Main 未手動啟用。review anchor `5f32c0ec84f9ad48771469e8fe5c0deb909dec5ba8e90bfc31c7873c304d1a07`，root 全讀 R→S diff；focused `20261010T053222Z_26672_10177b6c` 原生6passed／38deselected／1.27s，8候選＋58來源獨立 postflight 全匹配。

S 唯一 Main handle45718 原生 exit1，outer `20261010T053230Z_40564_04ac9655`、native PID37748／redirector10124／wrapper40564，鏈資格 `venv_redirector_child` 無錯誤。真首頁 viewport click 成功選中 typed 1000，首頁比較籃 gate 已通過；下一頁按鈕原生 stderr 報 `AttributeError: ... has no attribute '_page_index'`。root 核正式 RevenueView 718／722 的兩個按鈕 lambda 都呼叫該不存在方法，沒有定義；這是產品接線缺陷，不是改寫 QA 可修。Main 收據 timeout `f12_ui_stage_timeout:F12 page 1`／197.094s，source inventory 起訖一致、cleanup errors空。已交最小產品修補候選及實際 next／previous 按鈕回歸，完整旅程仍未通過。

P01 B script `ca9e648b753bbf340f84f083f97dd2652a83097a90506211e7da27a728bc2cc2`，root 審完整 A→B diff及原 metadata 回傳契約後執行，handle80231 exit0，收據 `p01_memo_counter_probe_20261010_b/memo_counter_probe_receipt.json`。candidate manifest e17582 與 overlay f0e639 分開核驗；只在同值、初始已匹配的 route 範圍執行原 reader/verifier，finally 恢復原綁定。單一 verified session、兩個原慢 filter shape、兩種 memo policy 的原 page/query/selection/hash 全一致，來源/store pins 起訖一致，八次操作都 clear一次及零殘留。

實際 baseline component tuples 寫入832,790 UTF-16 bytes，只有12／13次 hits；AND render hits5181、misses5921、byte-budget blocks5789。QA quota-zero component 對照 render hits10521、misses581、blocks0；OR 同方向，由5445／6084變成10927／602。這支持共享1MiB budget 被低重用 component tuples 占用，原「component零hits」假設修正為低hits。AND 儀器計時676.7851／551.8624ms、OR642.791／536.1734ms僅診斷；不得充作正式效能驗收，原300ms gate及完整矩陣失敗狀態保持。

Composite Watchlist 儲存／Qt route 小切片已凍結，root 審 storage c14323、service diff ec0b72、View diff459711、真257測試b64a55；唯一隔離封套 `composite_watchlist_route_20261010_attempt01`、handle27671 啟動。只在 child 記憶體套用 exact baseline 的兩份 diff，正式來源不變；完整257 fixture、JSON duplicate／明示 COW／typed專用重開及一般/latest拒絕尚待原生終態，不能先宣稱通過。

同 handle27671 原生 exit0：1passed／144.49s、wrapper147.125s、13 pins 起訖不變，stdout SHA `080abc1f2b026414eb136a3c38f0cd668c2377cf1eec4053f851062aec86da36`，stderr空。接受範圍為真257 reader owner 的 JSON duplicate、明示 COW、typed 專用 Qt 重開訊號及一般/latest拒絕；測試直接呼叫 Qt route，不授 Main 實際點擊／全View資格。root 另提出未覆蓋身份邊界：同一 strict bookmark 的不同有效比較籃順序／selected membership 會產生不同 envelope identity，但 service 目前按內層 bookmark_id 去重；須明確保存不可變 UI 狀態身份，不能悄悄忽略新籃狀態。此風險尚待專用正反例與候選設計，正式接入保留未完成。

#### 月營收換頁最小修補的事前回滾清單

| 檔案 | 類型 | 修補範圍 | 回滾方式與風險 |
| --- | --- | --- | --- |
| `ui_qt/views/daily_market_technical_official_disposition_revenue_view.py` | 修改 | 補兩個既有頁碼按鈕共用的 `_page_index`，只取目前已核頁碼／無頁時0 | 只移除本次方法；會恢復已確認按鈕例外，不修改來源或其他工作 |
| `tests/test_ui_qt_revenue_page_navigation_buttons.py` | 新增 | 實際 QPushButton 訊號與無頁／首末頁邊界 | 隨修補撤回新增測試；不取代真來源旅程 |
| `docs/07_guides/APPLICATION_MANUAL.md` | 修改 | 補保存來源研究頁碼操作及失敗時保持目前頁的判讀 | 只還原本次操作補充，保留其他 agent 文檔整理 |
| 本 QA 紀錄／Snapshot | 修改 | 同步修補與驗收界線 | 僅還原本次附加段／相應表格列 |

事前未來函數自查：本修補不新增篩選、估計或財務計算，只讀目前已發行頁碼；`navigate_page` 仍核同 source／result／query 並執行既有取消及來源檢查，不使用新資料或當日來源補歷史。正式插入後將執行實際按鈕回歸及 repository 強制 UI 檢查，通過前不提交產品修補。

root 已正式補四行 `_page_index`，RevenueView SHA `a5131b1759ebfa24718c8bef86a149038fa72d3c9011cfde6f353b06aba4d4e4`；Manual 主檔同步來源／頁碼／操作與失敗判讀，歷史附冊未改。強制 checks：工作台85passed／3.47s；update_tab 原生 exit0，25pass／0fail／4skip，使用自身隔離合成資料；mypy939 source files無錯誤；該 View py_compile通過。仍待真按鈕回歸與新版來源 pin 的完整 Main 旅程，尚未 commit 此產品修補。後續 Main 必須明示重建 anchor，不能宣稱與 S 原 c0c50 View 相同；S 所有原失敗收據保留。

root 審 pager sibling 四項單元測試後，以繁中註解新增正式 `test_ui_qt_revenue_page_navigation_buttons.py`；僅按鈕游標 fixture，不冒稱 reader-issued query page。四項實際按鈕回歸原生4passed／0.79s：無頁雙按鈕停用、首頁Next要求1、第二頁Previous要求0、首末頁向外按鈕停用。`navigate_page` 由測試攔截只核訊號接線，沒有來源讀寫；完整來源／新PID旅程仍保留 pending。根另核 S 的 `_detail_selection` 是 MA 私有契約誤套：正式 Revenue 用 typed row／目前 page/query/result/request，bookmark由 `from_issued_result_page` 綁定；後續 QA 須核真 Revenue 契約，不能新增假的 MA 欄位來滿足舊斷言。

產品換頁修補與四測試、Manual／Snapshot／本 QA 已保存本機 commit `963b04ea`，未 push；其他文檔整理 agent 檔案未提交。Composite envelope 去重邊界精確補正：原服務在相同內層 bookmark_id、但 payload 不同時回 `conflict`，不是 `already_present`，所以不會靜默吞掉；仍無法把兩個有效的 UI basket 狀態作為獨立收藏保存。新候選擬以 envelope identity 作 Watchlist source_id／lookup／列核驗，內層 strict bookmark_id 保留原查詢重開，需三種同研究不同籃狀態的真257回歸；此設計尚未正式套用。

#### 四群保存來源 public opener 正式接入的事前回滾清單

| 檔案 | 類型 | 接入範圍 | 回滾方式與風險 |
| --- | --- | --- | --- |
| `app_module/daily_market_technical_official_disposition_query_reader_v1.py` | 修改 | 唯一新增明示 bundle 四群 projection group opener；既有 AST 不變 | 先停本次新呼叫，再移除新增函式；現有 opener 不改 |
| `tests/test_daily_market_technical_official_disposition_bundle_projection_group_entry_v2.py` | 新增 | 真257母體單次 exact-read、完整群組及讀取前取消 | 隨新入口回滾移除本次測試；既有測試保持 |

新增入口候選先前真兩測試143.37s通過，root已審119行完整diff；現準備正式接入並重驗正式版本。來源只允許明示 bundle root／identity／manifest，決策時鐘從原 manifest取得，不讀latest或現在日期；全數原source pins核驗及取消／群組失敗poison仍保留，無新金融計算。不宣稱UI或效能資格。F12下一輪須明示重建新reader anchor（S舊d59b收據保留），不能沿舊58pins執行新來源。

### 正式 bundle 入口通過；H20 K 完整旅程啟動

root 在正式接入前核原reader d59b與候選a08d，AST移除唯一新增函式後完全相同；正式reader現在 `a08d30b084e35dc1eec25c2a9207bdd7a159f8d047d3bb3387e3897bf27e4df9`。單檔 mypy及兩檔py_compile通過。正式封套 `composite_bundle_opener_formal_20261010_attempt01`／handle99842 原生 exit0：2passed／196.38s、wrapper198.438s，六 pins 起訖不變，stdout SHA `290f8852d5ca6c66402e3f02448e850f7caa9f78c05cd9bf8dfbb89436d1fcaa`、stderr空。root 另獨立核當下六 pins及原生輸出／收據，保存 root_acceptance.json。接受真257 included＋1excluded、三indices257、全audit258的256＋2頁、單次exact-read及beforemetadata取消；不授Main、真人或300ms資格。

H20 J 靜態審查退回兩個必紅：summary已雜湊 IDs、return gate卻期待原字串；AST小測試缺hashlib全域。J不執行且原封保存。K只修這兩個 QA 契約並增嚴格 matcher 正反例，child SHA `a0e94a561fcfa99b63fbe747f80b77f6778590beac2b3911019dc8d7c0ddd64d`、test `bc8730443f51203a280927b28ceb3c2935a1fbbaf974e6df2657e3b8d75e6b64`，完整 J→K diff `ba1f160d737fed8dff5136c60e4b87be762092e2211152ca7b92b6f2ec5763e7`。隔離短目錄六focused原生6passed／4.32s，typed容器不冒稱view seal、假chart/假evidence拒絕、返回hash缺欄／錯值／混原ID拒絕；真public reader小fixture仍不取代原684bp。

K唯一完整 Main 封套由root固定K／原33source／S4manifest／launch／D9 guard與runner pins；原來源前後全核及原期限／headroom保持。handle45324啟動，尚待原十股、2382同來源OHLCV及專用return worker終態；正式工作區新API不替換固定S4來源，不混入這次H20資格。

K 原生 handle45324 已終態 exit1；outer封套 `root_main_capture_20261010_01`，native封套 `20261010T054832Z_3bac5cb294b5`，controller elapsed55.89s。失敗明確為同來源 OHLCV QA helper 第187行使用 `Path` 卻未匯入，child elapsed31.563s；不是產品 worker 例外或讀取逾時。起訖來源 pins 不變，原收據保留，不重跑未修改候選。另原 guard 記錄三次 platform 主機資訊查詢開啟 DEVNULL 被拒，後續僅檢視 guard 前 bootstrap 的等價初始化，不放寬寫入規則。新 sibling 須補實際 helper 回歸及精確差異，完整 chart／return 資格仍未取得。

FullView 靜態切片 manifest `8f65016e5bea1f3a01ce9fb4ea9146e4d614a71066533202885d970ee5150043`、receipt `218e8218d7d0c8e18128b886a2f5761e3c1cd0f29116b7a710bb6e66fdd9134c` 已送 root。root 全讀1416行 View、兩份真257測試及 Main 接線提案：候選 constructor 先取尚未建立的 `stock_code_input.setEnabled`，必為 AttributeError，故不啟動昂貴來源測試。新 sibling 須先建立該控件、忙碌結束後恢復代碼固定升冪控件狀態；窄窗回歸須核實際寬度460及操作可達性，不能僅 resize 後冒稱窄窗。原切片保持不變，Main 標題與 storage identity 後續另核；此候選尚未正式接入。

P01 C 凍結 runner `72122bd8dca187de5ccc5e9608cf68813ac8ef79015b80bf692858dc18851a02`、純 component retention 刪除 diff `e86e49c302a515dcaab6179128073afc4f9746cab8116886c30d9cd384235c38`、receipt `6dcf3567f7f71e2bc2af9ef4f6b57c3ec357edaada62cd23447fa3d1802bc279`。root 全讀 diff／runner後，唯一隔離 handle67555 原生 exit0，封套 `p01_quota_zero_capture_root_20261010_attempt01`。一個已核1000母體 session、四暖身排除、兩原慢shape各六組交錯配對；AND median821.6029→605.89ms、OR832.6278→606.23975ms，所有原 page／query／selection 摘要相同，來源／store pins 起訖相同，method／ContextVar／sys.path／helper module均恢復。首次session open21288.0418ms另列，不與頁面計時混合。此結果只診斷舊1f08版本的快取爭用；正式e5ba已有零component retention加render預填，須另核版本差異，不能重複套舊diff或把此結果當300ms門檻通過。

FullView B sibling `composite_view_candidate_20261010_b` 修正建構順序、來源／結果動作兩欄、排序／分頁兩列及busy後固定代碼升冪；View `88bbaa49077865dcf474b6f4a023bc09a0e561de8c83aaa92e1249288c15c727`、完整差異 `d4bb6de356859e8aee72a6e71fb9fdde4f136cfe035d13a3af406516f2d60bbd`。root 審逐行diff後無producer constructor回歸原生1passed／2.95s，15pins不變。唯一完整真257窄窗／條件驗收 handle39677 已啟動；尚待實際460px、文字末行、256＋1返回及四群AND／OR／unknown結果，不提前授予通過或Main資格。

F12 T 已凍結完整差異 `fef850916d44c8b4c5a7526348d14ded37844fef1314fb3939cde5c79c0f9b4a`，僅明示rebase RevenueView與reader兩source pins，其餘56保持；root全讀後發現新增負例使用SimpleNamespace，卻未提供helper所讀四個current properties，會先AttributeError。T不執行且原封保存；新sibling須以四個read-only properties的QA fixture驗真正外來page／request／row，不能放鬆正式Revenue契約。

### 後續終態：窄視窗與月營收仍未驗收

FullView B 的 handle39677 原生終態 exit1：1failed／1passed／1deselected，564.79s，15 pins 不變。真257四群 AND／OR／unknown 條件測試通過，包含完整258宣告、257 included、1 excluded及256＋1頁；窄窗則實際460px但body906大於viewport422，未到文字／返回驗收。C僅改剩餘橫排，root先跑無producer檢查：1failed／1.23s，body428仍大於422，pins不變；不重跑昂貴來源測試、不放寬窄窗門檻。B、C及原失敗均保留；正常View／Main閉環仍待。

F12 T3 原長路徑封套在產生原子收據前超出 Windows 路徑限制，pytest未啟動；root短路徑精確封套才實跑6passed／1failed／1.50s，QA query缺identity。T4補QA query identity及recipe.to_dict後，七項定向測試7passed／1.24s，八候選及58來源pins起訖一致。九個候選／manifest共519,502 bytes完整核驗後複製到同層短路徑 `output/qa/f12t4_main_1010`，不更改來源錨定。

T4唯一完整Main handle3131已終態exit1，native PID33060，封套 `20261010T060750Z_40708_4834ed5c`；native receipt `run_attempt_a6291967851b4a8e8c4a2ab262fbcb74/f12_main_revenue_receipt.json`。原query qualification通過，但 `revenue_result_clicked_row_not_bound_to_issued_page` 阻止後續收藏／新PID重開；不能以七項focused通過宣稱完整旅程成功。候選SHA保持，收據及原始錯誤保留，下一輪先核真Revenue點選列與已發行頁綁定。

Composite storage identity B 尚未正式接入：靜態shadow mypy為10 errors，八項schema字串不足以收窄union、一項generic context誤容Composite、一項removal matches舊union。修正必須維持typed envelope及嚴格decode，不用Any掩蓋。P01下一輪採固定產品commit85bc225b完整tracked source（4666 blobs、81,023,636 bytes）準備新錨定；目前僅靜態盤點，未建立clone、未重建千檔資料、未重跑300ms完整矩陣。

P01固定來源後續已完成：普通Git archive受Windows換行設定影響，與blob bytes不符，A在第一檔核驗停止，沒有runtime。B用固定Git objects原始bytes建立精確zip及新短根 `C:/t/p01src85bc10b`，原生exit0、4666檔全SHA一致、81,023,636 bytes、117相對目錄、0pyc、最長絕對路徑151。archive SHA `5b82641e66e7f7aa0c48de839a7764f8f12777431d57a3fd4ad11cd2af7f8ed8`，materialization receipt SHA `6b2f3570a1bb263efba4334ffd98f8fbf2cd007ba377c1eb007883a259dbda12`。Git/tree canonical inventory `0a90dfc1a6cfdeb524c3f3139d063c232ebf0247323586c24048ab0471381c3d`與既有controller records hash `85d95f8ebeff46927ff01a4a31236a7c5561127c83ac1f12cb38617c4b6612a0`為不同recipe；controller含root目錄數118另列。此只建立程式副本，原千檔source/store未寫入，完整矩陣仍未跑。

窄窗C無來源幾何診斷已定位：官方條件群組長title的minimumSizeHint386，而其layout最低264，外層filter及body邊距將整頁撐至428。下一版須保留外層條件語意並將補充說明折行，不能降低460px驗收。另storage B的複合列無條件停用「查看選中個股研究報告」，所以私有函式路由測試不能代替真按鈕操作；下一版必須有效列可點、損壞列拒絕，驗真QTest點擊與專用typed signal。

H20 L helper新增Path匯入與真分支正負例已由root隔離執行：7passed／4.34s、exit0、六候選pins起訖相同，封套 `h20_l_focused_root_20261010_attempt01`。typed/sealed synthetic fixture實際越過manifest-path比較，移除Path時重現NameError；仍不是原來源Main接受。L完整Main暫不跑，因原platform三拒絕尚未以精確guard前初始化處理；新M需保持D9 guard不變。

root直接核T4正式PageRequest契約後確認首錯：QA以 `request.query is query` 要求物件相同，但 `DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.query` 每次從query_json重建typed query，因此真請求必不相同。後續T5應以canonical JSON、query identity及正式request契約驗等價，page/result原seal身份仍保持；focused必用真Query/PageRequest DTO，不再用同一物件的fixture掩蓋。這是QA判讀錯誤，尚無此首錯造成產品點選失效的證據。

FullView D最小title／折行修正已真跑無來源檢查：body422等於viewport422、實際width460、horizontal scroll maximum0均通過；整項仍1failed／1.27s，因QA對未切入的stack頁使用尚未layout的hidden按鈕預設640px寬。新E應逐頁切換真stack並處理layout後核各頁控件，最後恢復原頁，不能省略某一頁或放寬body門檻。尚不啟動真257窄窗；D原封與收據保留。


### 2026-10-10 接續：窄窗帶來源、P01 靜態核對與收藏路由

- Composite View E 空白構造通過，但真保存來源窄窗測試仍失敗：內容 906 px、viewport 422 px；1 failed / 1 deselected，177.04 秒，候選與正式來源 pins 前後一致。失敗在 opener 前，尚未驗收到末行、返回及來源保留；不能以便宜構造測試通過代表整段完成。已交由 UI subagent 查長來源路徑標籤幾何，另建 F sibling。
- P01 固定 85bc 全樹來源的 controller 靜態 preflight 通過，receipt `output/qa/p01_1000_e5ba_full_matrix_anchor_20261010_a/static_preflight_29e0049cff07.json`；controller SHA bb7a1b652c62175fd41c57110175c59e418d93e15f8e4b537a74541c3b13b0f0、manifest SHA 9bd258ef5ee963551c04e1d2a3d7aded7b7df022ef9376709edb689ec92aef26。SQLite、網路、subprocess 嘗試均 0；此為靜態輸入核對，不是效能驗收。
- 收藏 identity C 已全文審閱服務/View diff 與真 257 Qt 測試。第一輪在合成 DB 的 Windows 沙箱 realpath 檢查遭 PermissionError，4.63 秒 setup error，尚未驗功能；保留 attempt01，於新 attempt02 使用相同候選重新啟動。正式檔案僅在子程序記憶體套候選，原件不改。
- H20 M2 focused 啟動前完成六檔 pins 核對，但建立 C:/t 隔離目錄遭沙箱拒絕，pytest 未啟動。M2 送審後新增 cold-cache fixture 的需求改置 M3；凍結候選不得再覆寫，M/M2 metadata 重建差異如實留痕。

- F12 T5 root 定向回歸結果 7 passed／1 failed／38 deselected，1.75 秒；八候選與 58 來源前後核對通過。真 PageRequest canonical JSON／query identity 比較已通過，但新增 fixture 把 `recipe.sort_clauses` 設為 dict tuple，後續 `.to_dict()` 觸發 AttributeError。此為 QA fixture 型別錯誤，不能外推為產品排序失敗；T6 只改用真 typed sort clauses 並保留所有發行結果 seal 判斷，完整 Main 尚未重跑。


### 2026-10-10 已完成的接續驗證

- Composite storage identity C attempt02 通過：1 passed，224.13 秒／exit 0，10 項 root pins 前後一致。真 full257 發行結果的同一 strict bookmark 保存三種比較籃 membership/order，三個 envelope identity 分別讀回；重複保存與衝突不改 bytes。JSON→明示 private COW readback、可見 Watchlist 按鈕三次專用 typed signal、損壞列停用及 generic/latest signals 0 均通過。這不等同正常 Main 或新 PID 旅程，也尚未正式套用候選。receipt：`output/qa/composite_storage_c_route_20261010_attempt02/receipt.json`。
- F12 T6 eight focused tests 全數通過：8 passed／38 deselected，1.25 秒／exit 0；八候選與58來源 postflight 通過。T5→T6 只修正排序條件 fixture 與私有 run root；PageRequest canonical binding 與原 page/result seals 保留。已建立逐檔 bytes 相同的短路徑 runtime 副本 `output/qa/f12t6_main_1010`，尚未啟動完整 Main。
- Composite View F2 完整 loader 依賴已補齊。root 兩項便宜 Qt 測試通過：2 passed／1 deselected，1.26 秒，12 pins 前後一致；涵蓋空白構造、busy 恢復及長來源路徑的 460px 幾何/精確提示。View SHA d1b116a23999bb250cb8c0b22f5fec2130ae0e65f080a2211801760c1de74b1e；長來源路徑不再放到主標籤撐寬，仍保留原 Path/完整 tooltip/accessibility。真 bundle 全窄窗流程 attempt01 仍執行中，未判為通過。
- H20 M3 focused 為 10 passed／1 failed，5.44 秒，六 pins 不變。強制冷快取測試在已載入 PySide 的 pytest 程序碰到 shiboken import hook 讀取 socket.py，被原嚴格 observer 拒絕；不能因此放寬防護。已交由 subagent 建 M4，在未載入 Qt 的新隔離 Python 子程序驗真冷快取，對齊原 probe 的 prewarm→D9 guard→Qt 順序。M3 Main 未執行。

- Composite F2 真來源窄窗測試終態 exit 1：1 failed／2 deselected，205.54 秒，12 pins unchanged。已通過初始 source label geometry、catalog、全母體 258/257/1、真首頁256列、選取與首股詳情；首紅在 readonly editor 的 QA cursor-position 判斷（0 vs2432）。只讀文字 Ctrl+End 捲動與 caret 不必同時變更；改以 scrollbar及末 document block 可見幾何驗收，G sibling另補 loaded/result/detail/comparison外層viewport檢查。來源指定為本次固定完整 `f17-bundle-v1-synthetic-7jz9y_r9`，不再反覆產製同樣合成來源。F2 原件保留，不能把首股前段通過說成返回流程已通過。

- F12 T6 完整 Main 終態：exit 1，205.656 秒，`f12_ui_stage_timeout:explicit Watchlist COW activation`；cleanup_errors=[]，原來源/候選完整收尾證據留在 `output/qa/f12t6_main_1010/run_attempt_09ca316ef0084a0896571c3836d5cfc7/f12_main_revenue_receipt.json`，launcher PID44592、venv redirector22568、native4708鏈核對通過。新的 canonical PageRequest binding 不再是首紅，但目前失敗沒有記錄啟用前按鈕可見性、Main/View服務身份、modal及status label，不能判定是產品 COW 啟用問題或 QA 點擊/等待錯誤。T7僅補真可見點擊與診斷，保留原私有源/58pins/明示確認。
- 新固定85bc P01六角色矩陣已在無其他 root runtime 的時段啟動，root capture `output/qa/run_p01_85bc_matrix_capture_root_20261010.py`；cold_01 exit0，29.11秒，四個候選pins前後一致，其餘角色尚待。不預判完整矩陣或300ms資格；來源不重建。

### 2026-10-10 六角色終態與後續小範圍驗證

- 固定85bc P01五冷／一暖六角色皆 exit0，四候選 pins 起訖一致，source/store 完整核對 unchanged，所有 Job 子行程完成清理；沿用既有1,000 included／1 excluded保存來源，未重建。root aggregator 報告 `output/qa/p01_1000_e5ba_full_matrix_anchor_20261010_a/root_aggregate_20261010_a.json`：暖啟各30次，nearest-rank p95換頁196.205ms、全域排序191.8186ms，皆低於300ms；篩選523.902ms，仍不達標。冷啟 launch→page0 p95為20.0318602秒，exact-open-start→page0為15.9045568秒。這是完整讀取診斷矩陣，不是正常應用程式1000檔旅程驗收，不能宣告P01完成。
- H20 M5 focused 終態為10 passed／1 failed，4.92秒，六候選 pins不變。隔離cold-cache子行程回報 `platform_machine_architecture_unavailable`；其環境白名單與原控制器Windows架構環境仍須核對，尚不執行Main，也不放寬observer或D9防護。封套 `output/qa/h20_m5_focused_root_20261010_attempt01`。
- Composite G便宜Qt檢查為2 passed／1 failed／1 deselected，1.31秒，12 pins不變。構造／長路徑幾何通過；填滿只讀理由後Ctrl+End加一次PageDown僅到scrollbar19／93。下一版須先讓editor位於外層可見範圍，再以有界實際鍵盤捲動核末行；不得用setValue跳過操作驗收，也不重產製257來源。封套 `output/qa/composite_view_g_constructor_20261010_attempt01`。

- H20 M6只在cold-cache測試child_env加入原controller本來已有的PROCESSOR_ARCHITECTURE，11項定向測試全通過，六pins一致。原S4 Main第二次啟動使用絕對路徑（第一次相對路徑在產品啟動前被拒絕），controller64.281秒／child33.313秒；真2382圖表與返回同manifest／選取已完成，return0.172秒，shutdown0 workers。最後仍exit1：QA把D9已驗證並拒絕的urllib3單次loopback能力探測計入一般network failure；非本機事件0、write/mkdir/prediction/training0，三種來源完整核對unchanged。M6原失敗保留，不能宣稱全旅程通過。
- M7只將最後網路資格判讀呼叫固定D9原有的`network_protocol_v2_passed`，D9檔案SHA、install順序及其拒絕邏輯均不改；不是開放網路。新增定向測試驗精確依賴單次探測、外部事件／多次／錯版本／來源不符拒絕，連同舊11項共12項通過，六pins不變；完整Main重驗待終態。probe SHA cfb3bd6a3a0742e1e6a75614cf43688663b6e51fa8f4306518bdca116a949d17。
- Composite G2/G3便宜Qt原件均保留。G2的固定scrollbar上限未跟隨Qt懶layout增加；G3已修並到末行，但外層QRect.contains(QPointF)型別錯誤，仍2 passed／1 failed。G3候選View九項mypy問題以明確Literal、變數及callback型別、exact envelope narrowing修正，候選型別檢查通過；尚無正式接入或full窄窗通過。

- H20 M7完整原S4 Main已終態exit0：controller61.86秒，child33.219秒；原10檔cohort初次21.031秒，2382真double-click→摘要0.422秒，回到原manifest／原2382選取0.297秒；shutdown complete、0 worker。圖表與表格同一原capture核對120筆2026-04-14至2026-10-05 OHLC，原gross684bp及決策2026-10-07／來源2026-10-06／特徵2026-10-05一致。原兩DB/source archive/template groups全量起訖unchanged，D9原協定精確辨識並拒絕單次套件loopback探測，外部事件0。完整receipt `output/qa/h20_main_s3_chart_candidate_20261010_m7_d9_protocol/attempts/20261010T065528Z_beaf74019975/controller_receipt.json`；這是固定source-port Main旅程，不代表新EXE、真人驗收或初次等待已改善，也不是正式收益/PIT資格。


### 2026-10-10 窄窗 G7、收藏 T8 與 F06 D 實證

- G6 已修結果頁數標籤折行，帶來源的460px外層幾何及詳情末行通過；稽核長文的有界鍵盤步數不足仍失敗。G7 僅增加內文鍵盤操作上限，完整固定258/257/1來源旅程為1 failed／4 deselected，28.12秒：首股理由、稽核、跨頁與比較對話通過，關閉比較後再次進入第二頁詳情時，真滑鼠點擊未取得editor焦點。完整旅程尚未通過；13候選／正式pins與320來源檔SHA前後一致，原失敗保留。封套 `output/qa/composite_view_g7_narrow_20261010_attempt01/receipt.json`。G7 diff原manifest少一個字元，root獨立核驗後記錄實際SHA `0de95f08c29e04cbcb0c2c8c50c6cce413f8af7583805afafe6fbb792012d9e6`，沒有改寫凍結原件。
- F12 T8定向11項通過，但完整Main exit1／199.469秒，仍停在明示Watchlist COW啟用；程序鏈核對與cleanup_errors=[]。啟用前按鈕真可見／可點且Main與View共用同一服務；只記錄到問題視窗Yes點擊，未出現成功／失敗modal，啟用後仍personal_source_readonly。不能據此斷言下一modal已開啟或產品儲存已升級。T9另建新私有root，先以真Qt最小雙modal測試核Yes返回值與timer-before-click，再決定是否重跑Main。T8原收據：`output/qa/f12t8_main_1010/run_attempt_5a0c63f724f84f3b97ae9735d1a66db2/f12_main_revenue_receipt.json`。
- F06 C保存來源測試在正式canonical placeholder page_size檢查被拒（256，契約要求1），未進入formatter；原來源及候選完整起訖一致。D新候選保留正式公式，修QA placeholder為1，composite read_page維持256；root memory-only候選測試兩项皆通過（29.42秒）：已保存observed列與隔離一檔29列OHLC經P02/store/F17公共reader取得的unknown列。BB30明示29／30暖機及warmup_insufficient，ATR14原observed狀態保留；方法、版本、日期窗口與連續性取自reader-issued證據，不補造估計。尚未正式套用presenter或完成使用版驗收。

- F06 D root終態exit0／30.766秒，兩項pytest29.42秒；全部候選與正式程式pins、320個既有來源檔SHA起訖一致。封套 `output/qa/f06_d_formatter_root_20261010_attempt01/receipt.json`。
- F12 T9 root最小真Qt測試為11 passed／1 failed／38 deselected，1.78秒，八候選與58來源postflight通過。真Yes／Ok按鈕released、精確點擊前modal、question返回Yes及information返回Ok均通過；唯一首紅是QA要求自訂clicked slot執行時question仍為activeModal，實際Qt內建handler已關閉question，觀測None。T10另建新候選對齊事件順序；T9 Main未執行，不能以此focused實證宣告T8產品儲存成功。

- Composite G8只修QA可見交集點擊與top-level重新啟用，正式View候選不改。便宜5項1.21秒及完整固定來源窄窗1項35.88秒皆exit0；完整258/257/1、首頁256列與末頁1列、理由／稽核末行、比較對話末行、第二頁詳情及原query／頁／選取／scroll／basket返回均通過。13pins及320來源SHA起訖一致。封套 `output/qa/composite_view_g8_narrow_20261010_attempt01/receipt.json`。這是獨立真來源View驗證，正常Main接線及新程序收藏重開仍待，尚未套入正式產品。

- F12 T10僅改QA對Qt question已關閉後自訂clicked slot觀測順序，12項定向回歸1.69秒全通過／38 deselected，58來源與8候選pre/postflight通過。9檔exact bytes複本 `output/qa/f12t10_main_1010` 已啟動一次完整Main私有COW／新PID重開旅程；終態待核，不預判通過。

- F12 T10 Main終態exit1／208.531秒，仍`explicit Watchlist COW activation`timeout；cleanup_errors=[]，原生／redirector程序鏈無錯。只記錄問題視窗Yes觀測，未出現第二modal，儲存仍readonly。timer-before-click的短訊息定向成功不能外推成完整長訊息確認成功，下一輪先補長訊息真Qt reproducer及保留原question實際return enum的觀測，不再次盲跑完整Main。receipt `output/qa/f12t10_main_1010/run_attempt_a4ff7598389842d69b342861cc1ef50d/f12_main_revenue_receipt.json`。


### F06 顯示層正式整合前回滾與界線

本次先整合已保存證據的呈現函式與可提交回歸測試，沒有正式UI呼叫端使用此presenter；新四群Main入口仍待獨立整合，不能視為使用版已提供新頁。未來函數自查：只讀reader-issued已保存方法／日期／筆數／狀態，不重算指標、改規則、推導未知日期或新增金融float。

| 檔案 | 變更 | 回滾方式 | 風險 |
|---|---|---|---|
| ui_qt/technical_official_composite_research_presenter.py | 顯示方法、窗口、暖機與未知原因 | 依整合收據的preimage還原該檔，先核對沒有後續他人修改 | 回復舊呈現；公式及保存資料不受影響 |
| tests/test_ui_qt_technical_official_composite_research_presenter_volatility.py | 新增真reader-issued observed／29列unknown測試 | 核對新增檔未被後續修改後移出該任務新增測試 | 僅失去此回歸覆蓋；原資料與測試保留 |

F候選正式測試已root隔離memory-only實跑2 passed／205.54秒，exit0；候選／正式pins及320個既有來源SHA起訖一致，封套 `output/qa/f06_f_formal_test_root_20261010_attempt01/receipt.json`。正式套用後執行workbench/update validator/全模組mypy/changed-files compile；未通過前不提交程式，原失敗收據不刪除。


- F06呈現函式與正式耐久測試已套用；git apply保留工作樹換行格式，formal SHA與候選不同但逐檔universal-newline text完全相同，收據 `output/qa/f06_formal_apply_root_20261010/receipt.json`。正式presenter SHA727012144e9ed308dacc2daa216a4e62f7296f3c93659b4e2852537095beed39，新測試SHAa94d77a06b67346e9484064be225b099546a4f11fec19920c9c3807dd58f31bd。
- 強制UI檢查：workbench85 passed／6.20秒、全八模組mypy939檔通過。attempt02 update validator因sandbox路徑WinError5產生3紅、compile因長pycache prefix失敗；原stdout/stderr與Validation Report已保存。只重跑兩紅於新短私有C:/t/f06uicheck1010後，update validator25通過／0失敗及changed-files compile均exit0，正式兩檔pins unchanged。封套 `output/qa/f06_formal_failed_checks_retry_20261010_attempt01/receipt.json`。沒有為通過而改validator、來源、公式或門檻。
- 新presenter目前沒有正式UI呼叫端，故此提交只整合顯示層與回歸覆蓋；新四群Main／Watchlist完整接線候選正在審查，Manual實際入口將與接線一起更新，不能將本函式提交稱為新頁／收藏新PID已接受。


### 複合研究 Main 接線審查（尚未正式套用）

A整合候選包含Main、WatchlistService、WatchlistView及新View／storage五檔；root核正式3 preimage、6 dependencies與patch SHA一致。manifest的Main shadow SHA把dbe誤寫bde，root停止原precheck，另在私有shadow從正式preimages重新套用相同patch。重建3修改檔actual SHA逐位元相同，新2模組因gitapply換行不同但universal-newline text完全相同；沒有覆寫A凍結原件。完整proof `output/qa/composite_install_precheck_root_20261010/input_receipt.json`／`rebuild_receipt.json`。Main actualSHA07913979b4ae3f86b2b4a4c99dbe84d6aa183c964b7d1c0cc92195bb2542865f。正常Main與新PID旅程仍未驗，候選型別檢查不替代正式強制檢查；B將另保存metadata修正與耐久測試。為保留F12原58pin問題重現，正式Main／service／Watchlist暫維持preimage，不在尚待的長確認訊息驗證前更換來源。

### 2026-10-10 恢復：完整長收藏確認視窗 S1

Root 在新私人 `C:/t/f12t11s1focus1010` 執行 S1 唯一長訊息真 Qt 節點，pytest 為 1 failed／2.71 秒；58 個正式來源與 3 個候選檔 SHA 起訖一致。精確長訊息的確認 Yes、巢狀成功 Ok、升級一次、清單重載一次、typed repository 模式及原 question 正常返回均已通過。首紅為 QA observer 記錄 `return_name=None`，不符合要求的 `Yes`；這不是本輪產品升級失敗的證據，仍需 S2 正確記錄 PySide enum 後驗證。不能由 S1 外推 T10 完整 Main 已成功或 F12 Gate 完成。

完整收據：`output/qa/f12_t11_s1_root_attempt01/receipt.json`，原 stdout/stderr 同目錄保留。Root wrapper 在收據落盤後，印出含中文的 pytest stdout 時另遇 cp1252 UnicodeEncodeError；pytest 自身 exit_code=1 已先保存，觀測故障與 UI 結果分開記錄。S1 原件凍結，不覆寫；後續只修 QA 回傳值觀測並建新 sibling。

B 主視窗候選另保存 A 的錯誤 manifest 與修正 metadata，加入真正點擊 catalog／Watchlist 列、保存前非零捲動及關閉後 worker registry 檢查；尚未執行這兩份 durable tests。P01 C 純路徑詞法候選已備妥，尚未 runtime；300 ms 門檻與原篩選 523.902 ms 未通過判定維持。

- S2 只修 QA PySide enum 回傳值編碼，原物件仍原樣交回正式 handler；root 同一長訊息節點 1 passed／4.08 秒，exit 0。58 source 及 3 candidate 起訖 SHA 一致。收據 `output/qa/f12_t11_s2_root_attempt01/receipt.json`；精確 922 字訊息、穩定幾何、實際 Yes／Ok 命中、升級與重載、原始回傳 Yes 都已驗。完整 Main COW 仍需另外診斷與驗證。
- P01 C memory-only 固定 85bc oracle 等價測試 11 passed／0.62 秒，固定來源、正式檔與兩個候選 SHA 起訖一致。`output/qa/p01_c_oracle_root_attempt01/receipt.json`。沒有正式套用候選、效能測量或產製器重跑；不關閉 P01 Gate。

### 主視窗與捲動耐久回歸 D（記憶體候選，未正式套用）

B 產品五檔搭配 D 測試候選：View 五項便宜回歸為 5 passed／1 deselected／2.64 秒，17 pins 起訖一致。D 要求真 Ctrl+Home 從頂端捲動、至少一步 PageDown、末行可見，以及合作式關閉後 native worker 全數終止；Main 點擊則核對祖先裁切、viewport 與 widgetAt 實際命中。收據 `output/qa/composite_d_cheap_root_attempt01/receipt.json`。

Main attempt01 在 pytest 前因 memory loader 未處理 UTF-8 BOM 而 SyntaxError，原輸出保留。attempt02 僅改用 Python 標準 utf-8-sig 解碼，formal canonical __file__ 與來源 bytes 不變；使用全新隔離 synthetic 258／257／1 fixture（不是重用 7jz9 frozen fixture），真 Main 測試 1 failed／125.26 秒，總 128.406 秒，17 pins 起訖一致。首紅在來源清單刷新按鈕：所有祖先／viewport／window containment 通過，但 `QApplication.widgetAt` 的全域中心命中為 None。尚未執行收藏儲存或 Watchlist 重開，不能稱 Main 路由通過。`output/qa/composite_d_main_root_attempt02/receipt.json`。下一步先用無來源 Main geometry smoke 查螢幕／視窗及實際命中，不重建同份 fixture 掩蓋問題。

F12 T11 未執行完整 Main：root 要求追加正式 handler 寫入錯誤的一般 status_label，另建 T12，不覆寫 T11。T12 最小 diff 已 review，13 focused passed／38 deselected／3.24 秒，58來源／8候選 postflight 通過；一般錯誤狀態與儲存狀態分開保留。`output/qa/f12_t12_focused_root_attempt01/receipt.json`。一次完整 Main COW／新程序診斷已啟動，尚待終態，不預判成功。

- T12 完整 Main 終態 exit 1／202.25 秒，cleanup_errors=[]，原生／venv redirector 程序鏈核驗正常。一般 status_label 終於顯示 `personal_watchlist_convert_blocked: stage_validation_failed`；原 question 回傳標準 Yes、released／clicked 命中均已確認，沒有第二 modal 是正式 handler 捕捉升級例外後返回的結果。精確收據 `output/qa/f12t12_main_1010/run_attempt_c6a73637173b4c978978706e971eef73/f12_main_revenue_receipt.json`。
- Root 不安裝 QA guard，僅以 mode=ro／query_only 打開本輪已保留的 failed stage，inventory complete=True、revision_count=1，stage SHA `327e3820d41b68b570054da6bd0811fc8bc7f163994f8c8036e846a3c8505d92` 起訖一致。收據 `output/qa/f12_t12_failed_stage_readonly_inventory_root.json`。沒有再次轉換、啟用或改 stage／來源；這是診斷讀回，不代替整個 COW 驗收。
- 唯讀追查確認 pinned V9 QA guard 將私人 application_root 內 URI 連線一律拒絕；正式 `_validate_stage` 必需以私人 stage 的 mode=ro URI 核驗，因此被 guard 包裝成上述錯誤。正式 converter／來源與 V9 guard 不改；下一候選只補 exact caller／configured target 的 QA 接線，並先驗真 converter 與拒絕案例。後續啟用的 target writer-lock URI 亦須分開核對，不允許任意私人或原來源 URI。

### 2026-10-10 接續：空來源窄窗診斷與 P01 E 等價驗證

- Composite E 空來源真 Main 在隔離目錄執行：1 failed / 1.88 秒，沒有產製資料。Main frame 已落在 800×800 虛擬螢幕內；第一個失敗是「官方市場與技術條件研究」頁籤中心 x=867 落在寬 548 的 scroll viewport 外。左側推薦工作區按鈕真實命中成功。此為窄窗水平裁切證據，不宣稱 Main 旅程通過；後續驗證真實水平捲動與產品可達性。收據：`output/qa/composite_e_geometry_root_attempt02/receipt.json`，完整幾何記錄：同目錄 `stdout.bin`。初次 sandbox 嘗試未能建立 C:/t 私有測試目錄，未執行測試；經隔離測試執行授權後完成上述第二次收據。
- P01 E 改從雜湊固定 baseline 函式原始碼套用唯一候選片段，修正手寫 Windows 字串造成的 SyntaxError，候選建構納入受控錯誤收據。root 在記憶體載入固定 baseline、編譯 E 候選並跑既有 11-case 純詞法 oracle：11 passed / 1.20 秒；固定來源、正式來源、C patch/test 與 E runner pre/post SHA-256 未變。收據：`output/qa/p01_e_oracle_root_attempt01/receipt.json`。此為詞法等價與可編譯性，不是效能 p95 過關。
- 分工續行：T13 精確 SQLite stage-ro / target-ro / activation-lock-rw 測試接線、窄窗可達與既有 qualified fixture 重開、P01 單次 eligible 計數與純詞法配對診斷。正式資料與正式程式未因本段測試改動。

- 窄窗最小 RecommendationView 候選 F 只開啟頁籤捲動按鈕，並在 minimumSizeHint 使用 tabBar.minimumSizeHint，避免整排頁籤寬度撐開 viewport。正式 source SHA `5f0faa96f246c62c7693e1771d538d88b72ae95a6544208d74b14650ed16edd5` 未變；shadow SHA `bccb87917849bd94140023a5ab9ec58f5a3a5429c17ed52c7b0d761af4d5fb63`。F 初輪 2 failed／2.62 秒：640 節點因 QA diagnostic int(ScrollBarPolicy) TypeError；960 節點因虛擬螢幕仍為800×800無法容納。原件／失敗收據保留。
- Root 新 G sibling 僅修 QA enum.value，選640節點，產品shadow不變；1 passed／1.67秒、所有 pre/post pins 一致，Main視窗fit、目標頁籤與refresh真widgetAt命中／QTest點擊、空來源唯讀盤點及native worker關閉通過。收據 `output/qa/composite_g_geometry_root_attempt01/receipt.json`。960未驗；尚未正式套用，尚未完成來源讀取／收藏／新PID。下一步重開既有258列qualified來源，不重新產製。

- F12 T13 stage dispatcher 已由root複製至不可變 focused sibling，helper SHA `88c79359b1e653de08332002646b142cd7ff48fb1ddd5e81ad508fce31c7af4f`、test SHA `60bc412887ea9bc3fd41e881263cacec8e111be1d2a38dd99bb3a2c71bae3817`。真正式JSON converter合成正例及四種拒絕案例為 2 passed／51 deselected／4 subtests passed／1.74秒；58正式來源與T12八候選pre/post驗證通過，兩frozen檔起訖雜湊一致。收據 `output/qa/f12_t13_stage_focused_root_attempt01/receipt.json`。這只驗stage唯讀role，未聲稱完整Main explicit Yes、target RO、activation lock或新PID接受。
- P01 F staticpreflight 32.676秒通過；唯一 warm_01薄診斷終態 `passed_path_precheck_diagnostic_not_qualification`，failures=[]，source/store前後unchanged，cleanup無殘留PID。attempt `C:/t/p01cur_rd_beace32491`，controller SHA `479ee515940c7742af5713f0a492c3db51f90e3e6999bf8991a3308edfae7b96`，manifest SHA `afa1df18b9ff8ed5dbb9201f59f76318431168b6f80f2e2f6bb0b70f8adadc20`。README示例仍誤列舊manifest SHA，root使用實際核驗SHA，另附errata不覆寫原候選。
- 該次reader-issued and_match query/selection/page/rows pins完全命中既有warm_01；observed=629、eligible native absolute Path=629，retain256。9組每側2048次純詞法配對：baseline median57,081,200ns、candidate43,946,100ns；8/9至少快10%，診斷microbenchmark gate通過。此約23%改善僅針對helper，不是整體篩選p95；原523.902ms與300ms門檻未改，P01尚未完成。下一步matched暖A/B全請求量測，不重產資料或污染baseline。

- 固定258來源G Main旅程已由root實跑：1 passed／86.85秒，exit0。真640窄窗→頁籤可見控制→catalog→257全母體查詢→256+1頁→兩筆比較籃→Main typed saver→Watchlist可見按鈕／雙擊fresh reopen通過；query/result/page/selection/basket/非零scroll精確保留，generic/latest旁路0，關閉後native workers為空。`output/qa/composite_g_fixed_main_root_attempt01/receipt.json` 起訖核對正式／候選與既有fixture完整檔案樹一致。公開exact reader先核identity `3cb1b3f9060abafa08ac9c182b36d9c03fa4b65549bd607d56dc639cbeff0d07`、manifest `c651415b93bb12ae06de6a4d28c62ddb8eb3466e647e219310c9a6d9ac1b4a4d`，逐列258/257/1；current_only、partial coverage、PIT=false保留。沒有producer。
- Root wrapper初次因Windows長路徑rglob失敗、第二稿長路徑字串SyntaxError，均在pytest／資料操作前停止且原稿保留；第三稿以標準Windowsextended-path讀取完整樹成功，沒有更改source bytes。這不是放寬qualified reader或縮小來源核驗。
- G仍記憶體候選；正式接線、fresh PID、完整COW及960窗寬未驗。fresh-PID候選接續復用本輪私人收藏，不重產／不覆寫封套。

### 正式六檔接線：執行前回滾清單

| 檔案路徑 | 變更類型 | 變更摘要 | 回滾方式 | 回滾風險 |
|---|---|---|---|---|
| ui_qt/main.py | 修改 | 新研究頁與 typed 收藏/重開/worker 關閉 | 保存後续差異後，只反套本輪 patch 或還原本輪 preimage | 回滾後新增頁入口失效，收藏資料保留 |
| app_module/watchlist_service.py | 修改 | 複合研究 envelope 存取 | 同上，只還原本輪差異 | 回滾後新收藏不能由此入口讀回，不能刪收藏資料 |
| ui_qt/views/watchlist_view.py | 修改 | 精確研究收藏按鈕/雙擊路由 | 同上，只還原本輪差異 | 新收藏路由回退 |
| ui_qt/views/recommendation_view.py | 修改 | 窄窗頁籤左右控制与minimum hint | 同上，只還原本輪差異 | 窄窗頁籤可達性修正回退 |
| ui_qt/views/daily_market_technical_official_disposition_composite_view.py | 新增 | 四群研究條件/比較籃/可捲明細/狀態收藏 | 先回退呼叫端，確認無他人後續依賴，再移除本輪新模組 | 次序不當會導致import失敗 |
| app_module/daily_market_technical_official_disposition_composite_bookmark_storage_v1.py | 新增 | typed envelope/storage | 先回退呼叫端，確認無他人後續依賴，再移除本輪新模組 | 不得連帶移除私人清單與保存資料 |

回滾順序：先逐檔確認所有後續／他人變更並保存；僅撤回本輪差異，不整體checkout共享工作樹；呼叫端與新模組一併回退；保存原資料、QA及收藏；再執行原UI回歸。preimages、安裝patch與逐檔起訖SHA將保存在 `output/qa/composite_formal_integration_root_20261010`。本輪不新增任何策略／績效計算，不改訊號、交易日期或公式；來源日期／current_only／PIT限制與qualified身份維持原typed契約。

### 正式接線文件 Coverage Pass（本輪）

| 優先級 | 文件 | 對應段落與處理 |
|---|---|---|
| Must | docs/07_guides/APPLICATION_MANUAL.md | 推薦分析新增6.7：入口、窄窗頁籤、來源盤點、四群參數、分頁、明細捲動、比較籃、收藏與觀察清單重開；research/PIT/COW限制及排錯 |
| Must | docs/06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md | 固定來源G與新PID K通過／原失敗／正式套用與必需檢查界線；P01仍未達300ms |
| Must | docs/00_core/PROJECT_SNAPSHOT.md | F03正式接線與新PID狀態須依本輪具名QA/commit同步；其他文件agent持有現況整理，不能覆寫其未提交工作 |
| Should | docs/01_architecture/system_architecture.md、PROJECT_NAVIGATION.md | 新View→typed bookmark storage→Watchlist→exact reopen的依賴入口；不改產品方向或領域邊界 |
| Check | Roadmap Hub／6M／Product／Index | 現有補完範圍與未完成Gate不變，無新增版本/正式收益/PIT資格；由具名QA入口追溯，不能稱全產品完成 |

Manual completeness所需資訊已由實際UI／G／K確認，不需新使用者授權。接著只patch本輪相關段落，保留其他agent內容。README與中央索引沒有新增文件路徑，原具名QA入口仍有效。

### 2026-10-10 恢復後核對：正式整合與尚未關閉的 Gate

- 新程序 K 收藏讀回為 1 passed／85.87 秒；Watchlist 按鈕及雙擊均重新核驗既有 qualified 來源並恢復查詢、頁碼、選取、比較籃及 scroll=1731；私人清單起訖一致。收據：`output/qa/composite_k_fresh_main_root_attempt01/receipt.json`。I/J 的 QA 清理、digest 與 canonical path 斷言錯誤保留於原失敗收據，不作產品通過證據。
- 六檔正式接線已套用，逐檔 preimage、patch 與起訖 SHA 保存在 `output/qa/composite_formal_integration_root_20261010/apply_receipt.json`；Manual §6.7 已同步。尚未提交，仍等待正式 import 的耐久旅程測試。
- 正式強制檢查已通過：工作台 85 項、更新頁驗證 exit 0、mypy 941 檔、六檔語法檢查；六檔 pre/post SHA 一致。收據：`output/qa/composite_formal_checks_root_attempt01/receipt.json`。正式耐久測試另記，不把這些檢查當成完整產品驗收。
- P01 無其他 root 重負載的配對 A/B 終態：`C:/t/p01cur_rd_9404ce945b`，baseline p95=623.9202ms、candidate p95=551.0107ms，median=502.56515／490.8013ms，仍未達原 300ms；source/store 不變、failures 空、無殘留 jobs。僅 helper 改善不足，不套用正式 helper、不關閉 P01。先前與 Main 探針並行的一輪保留為負載混雜診斷。
- 恢復開發後維持兩個子代理的靜態平行工作：F12 三種 SQLite URI role 候選及 P01 下一步瓶頸設計；runtime 由 root 審閱後統一安排。其他文件 agent 的未提交文件與 `$null` 均不處理。

- 正式 import 耐久旅程終態：7 passed／382.76 秒（wrapper 388.11 秒）、exit 0；Main 動態 257 檔 fixture 旅程與 View 六節點全部通過，八檔正式 source/test pre/post SHA 一致。收據 `output/qa/composite_formal_durable_root_attempt01/receipt.json`。涵蓋窄窗真頁籤控制、全母體分頁、跨頁比較籃、完整明細捲動、收藏與精確重開及 worker 關閉；合成來源 current_only／partial／PIT=false 限制維持。新程序 K 是另份固定封套證據；960px、新 EXE、真人視覺及完整私人 COW 仍未驗，不能宣稱全產品完成。

### 月營收候選靜態審查與後續工作（未驗收）

- T14 凍結 manifest SHA `9a378845c7f037447addeb317b0226704c7ac810c30296cbe83235005cd1ac22`，58 source pins 與八候選檔核對；歷史失敗 native stdout/stderr 未保存的缺件維持明示，不能當作通過證據。
- Root 與獨立 Luna max 審查確認兩個 QA 正路徑阻擋：post-reload 在沒有 upgrade local 的 View._load_watchlist frame 查 service binding；以及 post-activation lock 模式名稱沒有 post_activation_ 前綴而誤用原 owner matcher。這些是候選守門錯置，沒有放寬正式 COW 或原來源寫入權限。
- Root 保留 T14，建立 T15 靜態 sibling：`output/qa/f12t15_main_1010`，manifest SHA `1a0e9fcb7008bb1c176c048a1e7fff7ae7c0a038937725cb29b436199f90e301`。只修正精確 frame owner、模式名稱與新私人測試根；AST parse 通過，尚未執行 focused／Main，不關閉 F12。
- P01 下一個 I 候選仍僅 QA shadow：fresh manifest bytes 每次重新檢查路徑／link／stat／bounded read／SHA後，才沿用原 reader-issued immutable manifest；所有 artifact 與 layout 核驗維持。具名負例矩陣已交付，尚無可接受 runtime／效能結果，不套用正式來源。
- 架構、PROJECT_NAVIGATION 與 UI_FEATURES 文件覆蓋同步已另提交 `3104b79b`；目前狀態同步 `07ff5694`。其他 agent 的文件整理變更未納入本輪提交。

### F12 focused 終態與接續定位（2026-10-10）

- T15 attempt01 在 sandbox 的嚴格 Path.resolve 發生 WinError5；原 stdout/stderr、receipt 已保存，58+8 pins 一致。attempt02 使用相同凍結候選於全新私人 TEMP：2 passed／6 subtests passed／1 failed／51 deselected；原來源未變，不授完整 Main 通過。
- T16 僅加失敗診斷，T17 修三個 @contextmanager 的 wrapper/generator 精確 code 綁定，T18 補 _history_prefixes 的獨立 schema detection chain；各輪均保存原件與原生 stdout/stderr／receipt。T17/T18 仍 2 passed／6 subtests passed／1 failed，58+8 pins 起訖一致，未改正式程式或資料。
- 最新具體阻擋為 target_read_callsite_invalid：正式 _preview 經 _base_lineage_snapshot → _history_prefixes，先直接 _detect 再 inventory；候選原 receipt_lineage_inventory 缺 _base_lineage_snapshot，schema 與 inventory 兩條都必須列精確鏈。另 under-lock 的直接 _detect 與 _base_lineage_snapshot 嵌套鏈須一併靜態核對。獨立審查持續，不以泛化祖先搜尋／全部私人 URI 放行解決。
- 接續應先完成全部精確 target schema／inventory chains 的靜態核對，再跑三 focused；成功後才執行完整 Main。P01 I 仍是未執行的 QA shadow，300ms Gate 保持未完成。本輪產品有效提交為 8c7fd469，Snapshot 07ff5694，架構／導航／UI Features 3104b79b；無 push、新 EXE或全產品完成宣稱。

### 2026-10-10 真人驗收入口（尚未取得人驗結果）

- 詳細步驟見 [複合研究真人驗收](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)：非全螢幕可達性、完整明細捲動、返回與跨頁比較、收藏即時重開、關閉後重開。使用合成1000–1256，沒有2382/H20；不把此試用外推成真推薦、收益或完整產品驗收。
- 本機啟動檔 `output/qa/composite_human_20261010/start_composite_human.cmd` 與 ASCII PS5.1 腳本六正式SHA核對；`-CheckOnly` exit0且不啟動UI。固定private-trial沿用重啟收藏，不讀正式DATA_ROOT；原碼實際視窗待真人確認，不稱新EXE。
- 三個 Luna max 工作平行：t14_guard_review補完整T19 callchains；f06_evidence補P01 I可執行負例與配對量測候選；resume_perf只讀核真人launcher及控件對照。root負責審閱、runtime及正式整合，真人回覆不阻擋獨立後端工作。

### 2026-10-10 T19／T20 聚焦驗證與真人啟動器覆核

- T19 三項聚焦終態：2 passed／6 subtests passed／1 failed／51 deselected，5.59 秒；58 正式來源及 8 候選檔起訖一致。收據 `output/qa/f12_t19_focused_root_attempt01/receipt.json`。阻擋已定位到 activate_watchlist_sqlite 內再次呼叫 _preview 的精確鏈，不能算完整 COW 通過。
- T20 只在 QA sibling 加三條 activation 初始 preview 的 target-read 鏈及一條 writer-exclusion 鏈；manifest SHA `30ac1bc4089a0296a596b6c6726a4064fd3aa12caec7022c0d62bc51d2803beb`。三項聚焦超過 90 秒，wrapper exit 1、原 stdout/stderr 為空；沒有可用通過結果。補存 `output/qa/f12_t20_focused_root_attempt01/timeout_receipt.json`，66 pins 核對不變，並確認沒有該次測試殘留程序。
- 只讀審查發現 focused modal poll 在成功之後不再輪詢；若 postload 開啟「錯誤」modal，可能卡在巢狀事件迴圈。這是待驗假設，尚未確認根因。T21 僅補測試診斷與有限等待，保留成功斷言、精確守門及正式來源；聚焦成功前不執行完整 Main。
- 真人啟動器已完成獨立靜態覆核：`output/qa/composite_human_20261010/review_receipt_20261010.md`，SHA `e2f1ed56e574cce369238495bc0d6446f34730c4b209ffabb8954d0ad75fe75a`。來源碼入口、六正式 SHA、固定合成 manifest、私人設定及收藏保留範圍均有記錄；CheckOnly 仍會重設私人設定，不能當作完全不寫檔。尚未啟動 UI 或取得真人結果，不能外推成新 EXE 驗收。
- 其他文件 agent 的 Manual／索引／封存整理變更維持原狀；本輪只補具名 QA 記錄。P01 可執行負例與配對效能候選持續平行準備，300ms Gate 未關閉。

### 2026-10-10 T21 成功後重載診斷（未驗收）

- Root 完整讀 T20→T21 diff 並依 manifest SHA `b26e6dc4367a9fb07de39a0634c3fb5f8f6c5563a4f8548f3ea2b9ee5141148f` 凍結；候選正式守門未改，僅 focused 測試增加成功後輪詢、完整意外 modal 診斷及 25 秒 watchdog。Root wrapper 同時補逾時收據與 unbuffered stdout。
- 全新私人合成測試終態 2 passed／6 subtests passed／1 failed／51 deselected，6.25 秒，wrapper 7.078 秒、exit 1、timed_out=false，66 pins 起訖一致。收據 `output/qa/f12_t21_focused_root_attempt01/receipt.json`；原 stdout/stderr 保留。
- 真實成功 modal 之後出現「錯誤」modal，文字與 traceback 為 personal_writer_disabled: sqlite_unavailable；role ledger 的實際拒絕為 activation_lock_callsite_invalid。診斷以標準 OK 關閉意外視窗，使原成功斷言失敗可返回，未把意外 modal 當成功。
- 實際 stack：View._load_watchlist→WatchlistService.get_stocks→personal_load_gate→PersonalWatchlistService._load_watchlist→contextlib.__enter__→PersonalWatchlistService._writer_guard generator→contextlib.__enter__→watchlist_service_writer_guard generator。獨立靜態收據 `output/qa/f12_postload_static_review_20261010/receipt.md`（SHA `15ffe0d295fd47b5163aa1ec006b23133f72d1e3a3dbb3595f37f379977b15fc`）指出四條 postload patterns 的 generator／__enter__ 相鄰順序列反；T21 重現支援此判斷。T22 只修這四條 QA 精確鏈，聚焦通過前不跑完整 Main。
- P01 J 可執行 oracle 已交 root 完整逐段審閱，尚未執行。要求 J2 在每組配對計時之外比對兩側完整 DTO；K controller 另行建立精確 scratch mutation／清理邊界及既有 source／store／native Job 守衛。原 300ms Gate、完整 P00–P14／M1–M3／F01–F23 保持未完成。

### 2026-10-10 T22／T23 收藏背景讀取定位（未通過）

- T22 只修四條 generator／contextlib.__enter__ 順序，manifest SHA `3112bed1044958054cc8b20b14181e203c6c6b4eaa575db2b64c87aecdd4c19c`。聚焦 2 passed／6 subtests passed／1 failed／51 deselected，6.35 秒，wrapper 7.125 秒，66 pins 起訖一致。啟用與主要重載沒有再開 critical modal，但 close_errors 仍因 proof_rejections 非空而失敗；不能宣稱整項通過。收據 `output/qa/f12_t22_focused_root_attempt01/receipt.json`。
- T23 僅增加有限 caller-chain 診斷及原空錯誤清單斷言的 failure payload，沒有修改授權條件。manifest SHA `4f82289dd4fa5541a9e9c70e8a4448582e4b57dbb99e81e8713ca8c95775f7f8`。聚焦 2 passed／6 subtests passed／1 failed／51 deselected，6.58 秒，wrapper 7.5 秒，timed_out=false，66 pins 起訖一致。收據及摘要 `output/qa/f12_t23_focused_root_attempt01/{receipt.json,diagnostic_summary.json}`，原 stdout/stderr 保留。
- 實際兩條拒絕鏈：WatchlistService.get_stocks:1641 → _list_full_n_bookmarks:125 或 _list_price_bookmarks:110 → _invoke_task_with_optional_cancel:50 → TaskWorker.run:222。成功 UI reload 最後刷新收藏控制項，會啟動這兩個 owned workers；它們不符合主執行緒 UI 升級中的單次 personal_load_gate。負向 URI probes 只記 role rejection events，並非本次 proof_rejections 原因。沒有刪除紀錄或弱化成功斷言。
- 下一步先審最小 worker inventory 角色：實際控制項／TaskWorker ownership、callback/code/args 與 service 身分、獨立 thread-local proof、精確 target-read／marker-lock scope，以及 worker drain 後才 close。不能跨執行緒覆用原 question proof、禁用實際控制項或泛化所有私人 URI。獨立設計與競態審查進行中，尚未實作。
- Full Main 另需新 bootstrap 封套：沿既有 G reviewed-set schema、保留精確八候選檔／58 source pins與外部 manifest SHA，綁新的 candidate／fixed_inputs private parent；不改 validator 或回指舊 candidate。T23 已用於診斷，未來 Main sibling 另取新名；聚焦通過前不啟動 full Main。
- P01 J2 的完整配對 DTO 比對 diff 已由 root 讀過，K 精確 scratch controller 尚在靜態準備。未執行新效能樣本或套用 I 正式 patch，300ms Gate 未關閉。

### 2026-10-10 P01 K 實際 oracle 終態與 T24 隔離候選

- Root 完整審閱 K controller diff，固定 manifest SHA `67fcc4f90c15fca1e4f0707f8bac6c61765194c11bc89c5e52026626b70fa9c9`。靜態 preflight exit 0、6.442 秒；收據 `output/qa/p01_filter_parallel_experiment_design_20261010_k/static_preflight_ec5fd3e22c7a.json`。沒有 producer、SQL、子程序或產品模組載入；此項不是效能驗收。
- 實際 warm_01 attempt `C:/t/p01cur_rd_c68a787540` 終態 exit 1。`child_result.json` 保留 `p01_i_oracle_unexpected_error`：固定 runtime 的 `DailyMarketTechnicalUniverseV4ReadSelection` 沒有 `to_dict`，oracle 在建立完整結果比較紀錄時失敗；沒有可接受的新配對樣本。`supervisor_result.json` 記 source/store 起訖 unchanged、native Job 已無活動程序；指定 scratch 已清空並移除。原 K/J2 封套保持不變，新 J3/L 只修 typed serialization 與對應 pins，待審待跑；300ms Gate 未關閉。
- F12 T24 僅在全新 QA sibling 實作。兩位 Luna max 已獨立核對 worker 的精確 ownership、thread-local proof、target RO 與 marker 驗證短 RW lock；主 UI one-shot proof 保持獨立。要求建構與重載 workers 都自然結束並處理 native-finished queued slots，再 shutdown、負向 probes、role close；task-result signal 或非同步 cancel 不算排空。尚未取得 T24 執行結果，完整 Main 仍待。

### 2026-10-10 Worker 身分與排空的獨立審查基準

- Root 已完整讀取獨立靜態收據 `output/qa/f12_worker_scope_review_20261010/review_receipt.md`（繁中修正版 SHA `68581499e129cb349659721a8235aab4aa063bb005c85075f4b063c484ae01af`）。收據以 T23 固定來源、候選及實際 caller 診斷為基準；不是新的 runtime 通過。
- 每個實際收藏 list worker 的 `get_stocks` 有五個 target RO callsite（marker schema、history schema、history inventory、current schema、current inventory），另有一次 target-only writer-exclusion 短 RW lock。四類邏輯區域不能當成只有四次連線；T24 必須全部精確核對，沒有通用 RW 或 activation publish 權限。
- Root 另實讀 PersonalWatchlistService：第 80 行建立同實例 `RLock`，第 283 行先取得此鎖再執行 resolve、marker guard 與資料讀取。兩個控制項使用同一 service 的背景讀取會自然排隊；不把同時啟動 worker 本身判成產品缺陷，也不在 QA 加額外序列化掩蓋正式流程。
- Native finished、queued cleanup、兩控制項無 worker／pending refresh 是撤除守門前的必要證據；result signal 或非同步 cancel 不算排空。T24 仍在隔離候選實作，待完整 diff 與獨立審查後才執行。
- P01 已確認固定 Selection 為 13 個 dataclass fields，SelectionPage wrapper 為 6 個，兩者沒有 to_dict。新 J3/L 修正需明示逐欄與公開 property、reader seal 身分、inner Page／原 Query payload 及每組完整 typed 結果比較，不能退化成只比摘要或股票代碼。尚無新的效能結果。

### 2026-10-10 J3／L 審閱與第二次 oracle 終態

- Root 完整讀 J2→J3 diff、manifest／README，獨立 AST 比對固定 85bc 的九個 dataclass 欄位清單全部一致（Query 27、Selection 13、wrapper 6、inner Page 10 等）；J3 runner SHA `4630f4ac32a3dcbc5c72dcd0f2eca992e90565d6baffb0a93294c60b863cdf46`、manifest SHA `948f15023ce3e0ee69c6a6fe664d7abb6321b492b52822dbe9eb42f77045a3b3`。所有欄位、公開 property、原 payload、reader seal 身分與容器型別均保留完整比較；暖機及 30 組配對比較仍在計時之外。
- Root 完整讀 K→L diff 並核對凍結 manifest SHA `1ec14119afc1d3f1d4304d2fdd41232b63e3255edd0f45680e3ac39d7c6cdbc0`、controller SHA `9e527f7700794872c0c41f1b97ca90e8896c7e5e592ad5e75d3ca721d984e8f0`。靜態 preflight exit 0、7.412 秒，收據 `output/qa/p01_filter_parallel_experiment_design_20261010_l/static_preflight_6580c8feb745.json`。
- 唯一實際 warm attempt `C:/t/p01cur_rd_088d042d9a` 終態 exit 1。`child_events.jsonl` 記 P01 真 opener 已讀 1,000 included，oracle runner 返回 failed、scratch removedempty；沒有新的有效配對速度結果。`supervisor_result.json` 記 source/store unchanged、Job cleanup 完成且活動程序為空。
- 本次 `child_result.json` 未能保存；supervisor 的原 stderr 明確記 `child_result_write_failed / json_output_limit_exceeded`。寫檔錯誤證明輸出超過既有 4 MiB 上限；Root 另實讀 `_io_summary`，確認回傳所有 lstat/open 明細，這是待核的主要容量來源。超限 payload 本身未保存，原 oracle failure 被二次寫檔錯誤遮蔽，不能猜成產品計算失敗。新 J4/M 僅補有界診斷輸出：完整 I/O 次數與全序列 SHA／執行時序列比較不減少，輸出明示 first/last sample 與 omitted count；原錯誤及超限 fallback 收據必須保留，不盲增大小上限。原 L/J3 封套保持不變。

### 2026-10-10 續接靜態覆核：T24 與 J4／M 尚未執行

- Root 與獨立 Luna max 在 T24 草稿辨識並要求修正：current schema detection 誤列為 marker detection、共用 tail 重複 get_stocks、closed-connection verifier 缺 sqlite module 身分，以及未登記 worker 的執行／撤守門缺口。逐項修正仍在候選內，尚未取得凍結封套及 runtime 證據；不宣稱 F12 通過。
- 清理必須同時證明兩個 control idle、全域 worker registry 空、native finished 與 queued cleanup 完成；TLS 還原放在無條件 finally。視窗 constructor 中途失敗與 addCleanup fallback 也必須遵守相同撤守門條件，不能因 view 尚未賦值或忽略 scope close errors 而漏掉存活 worker；私人 fixture 退出前必須完成排空。正式 COW／來源寫入權限未變。
- Root 已完整讀 J4 最後輸出壓縮 diff 與 M controller 草稿 diff：完整 I/O oracle 及配對比較先完成，僅發布時保存五類序列的首尾各最多八筆、完整序列 SHA、總數與省略數；M 保存原 oracle 返回錯誤、payload 大小／SHA、精確 child_result 的有界超限 fallback 及 supervisor readback 身分。尚未凍結或 preflight，不作新速度或負例通過證據。
- 三名 Luna max 分別處理 F12 候選、獨立守門審查及 P01 診斷封套；Root 審核後統一執行隔離測試，避免重負載互相干擾。正式程式、原 D 槽資料、排程及其他文件 agent 的變更不在本段修改範圍。真人驗收入口沿用前述具名文件，尚無新真人結果。

### 2026-10-10 J4／M 實際診斷：原錯誤已保留，Gate 未通過

- Root 完整審閱凍結 J3→J4 與 L→M diff 並逐檔核對 artifact bytes／SHA。J4 manifest SHA `615ba1fc3e7f6270719d7d5b77bd7b3e1e407e4e8d199a2542fc5406a5b2bc7c`、runner SHA `73ce052ff04ab81aca68dd4b854c127a70ee27c366195199e4e728634c2bb260`；M manifest SHA `4e4142c50db0336b9c95da01dc0e67e5f84d24d1c81d3eac2dbe6c4baa47b38c`、controller SHA `38937141f7de97bdb1b36808caa80c860df58909c89b8d3e3ee9259e8534026d`。
- M static preflight exit 0、6.280 秒，收據 `output/qa/p01_filter_parallel_experiment_design_20261010_m/static_preflight_41c8f203cbe6.json`；network／SQLite／subprocess attempts 均為零。唯一 warm runtime `C:/t/p01cur_rd_c41961fe2f` terminal exit 1，原 source／sealed store 起訖 unchanged、native Job 無活動程序、指定 scratch removed_empty_root；未執行第二次同候選。
- 本次 child result 已完整保存 17,957 bytes，沒有再次被 4 MiB 上限遮蔽。Oracle return receipt 同時保留 `io_sequence_output_shape_invalid: bounded_reads` 與原 `p01_i_oracle_unexpected_error / Error`：shutil 建立負例副本時報來源／目的 receipt 路徑 Errno 2。沒有有效的新配對效能樣本，P01 原 300 ms Gate 保持未完成。
- Root 靜態定位摘要錯誤：壓縮後新增的 `io_sequence_samples` 自身也含 bounded_reads key，遞迴投影又將 sample mapping 誤當原始 trace list。下一候選應只辨識完整原 I/O summary、避免再次處理新樣本，不修改內部完整 oracle。第一個報錯的來源 receipt 路徑長 265 字元，host 唯讀檢查檔案存在、2,207 bytes；長路徑複製是待核假設，不把 Errno 2 解讀成原資料遺失。J4／M 原封套及失敗證據保留。

### 2026-10-10 T24 凍結審查與 constructor 清理的剩餘缺口

- T24 manifest SHA `01c3f3eabfac0faed0bf43d72e2830a090f15061850b4dc4b182a7fb1aa933ee`、完整 T23→T24 diff SHA `c81b1401cab15528a038d40dde94ae2cd740adcabf5fdbadf9932d115bc73206`（79,195 bytes）；Root 完整讀差異與 README，八候選檔大小／SHA 核對通過，獨立審查亦核對相同 pins。尚未執行 T24，不宣稱聚焦通過。
- 最終審查發現新的具體清理缺口：constructor 拋錯使 view 尚未賦值時，ensure_view_closed 使用空 controls，all 空集合會讓 controls_idle 為 True；constructor worker 帳本已保存 control，卻未確認其 queued cleanup。native finished／registry 空不能替代此條件。新 T24a 只補 captured control 的直接 idle 核對，T24 原封套保持不變；新封套覆核後才執行三項聚焦測試，完整 Main 仍待。
- P01 唯讀補查兩個訊息中列出的來源 receipt 均存在、265 字元／2,207 bytes，receipt identity 與檔名相符；不推論截斷訊息只代表兩個錯誤。J5／N 僅準備 I/O summary 投影與負例副本複製修正：保留原路徑守門、來源／clone 全樹內容 SHA 與全部負例，不放寬 extended-path 或 scratch 寫入範圍。未取得新 runtime 證據。

### 2026-10-10 T24a 聚焦通過：完整 Main 仍待

- T24a 僅修改 constructor 例外路徑的 captured-control idle 核對；其餘七個 reviewed files 與 T24 逐 byte 相同。Root 完整讀 2,497-byte 差異並核八檔 pins；獨立 Luna max 以相同凍結封套確認可執行 bounded focused。Manifest SHA `cab1f153f9995e6d3aba0a20b2b945d899bb749ae8ec053487ff97ee7a2e20f4`、diff SHA `341c277b5359a8a7a7f31fbef25a62c0129318f96d588b180956017d04100bb4`；T24 原件未改。
- 唯一實際聚焦 attempt：3 passed／6 subtests passed／51 deselected，7.46 秒；wrapper 8.219 秒、exit 0、timed_out=false，58 正式來源＋8候選檔起訖一致。收據 `output/qa/f12_t24a_focused_root_attempt01/receipt.json`，原 stdout／stderr 保留。
- 通過範圍是私人合成清單的真確認／stage／activation／UI reload，以及兩個真收藏 helper 各五 RO＋一次 target-only 短 RW、六連線 closed probe、native finished／全域 registry／queued control cleanup、無 TLS 連線拒絕與原錯誤 mode／callsite／target probes。Price helper 為零筆，逐筆價格收藏讀取未觸發；完整 worker-specific 負例及 timeout／exception 矩陣尚未執行，不能外推成完整 COW／F12 Gate。
- 完整 Main 將另建 T26 bootstrap，依 T24a 基底、原 G reviewed-set schema、58 source pins、精確八檔與外部 manifest SHA，candidate／fixed_inputs 綁同一全新私人 parent。T25 是未執行的舊靜態草稿，不能拿來作通過證據。T26 審閱前不執行 Main；正式程式、原 D 槽資料、新 EXE 與真人狀態不變。

### 2026-10-10 恢復推進：T26 主視窗接線缺件與 N 實際終態

- T26 bootstrap manifest SHA `0ddae92753ec78adc6605cf1f59bcb7406bf87b363165d21a5f3ca35ac083442`、八候選檔與 58 source pins 靜態吻合；但 Root 與獨立 Luna max 確認 worker scope 僅在 focused 測試安裝，完整 Main 沒有安裝、TLS dispatcher 或排空後關閉接線。T26 未執行，不能以 T24a 局部通過代替 Main 通過。T27 先設計實際 Main 接線與失敗清理；成功 COW 不得先 shutdown，後續還需儲存收藏與 fresh child 重開。所有 hook 必須在 native、queued controls 與 registry 安全排空後才撤除，Qt wrapper 刪除前完成。
- Root 完整讀 J4→J5、J5→N 與 M→N 差異。N manifest SHA `a14e27b6f2097e8e74c4c068e4d17b8acb3caac03ad67f667b2a7971def570c8`；靜態 preflight exit 0、6.214 秒，收據 `output/qa/p01_filter_parallel_experiment_design_20261010_n/static_preflight_55635d459943.json`，network／SQLite／subprocess attempts 均為零。候選僅修完整 I/O summary 投影與負例副本的有界串流複製，完整序列 oracle、來源／clone 全樹 SHA、固定 reader 與隔離守門維持。
- 唯一 N warm attempt `C:/t/p01cur_rd_2dbcf2d216` 終態 exit 1；source／store 起訖 unchanged、Job 無活動程序、scratch removed_empty_root。摘要投影錯誤不再出現，原負例副本 Errno 2 仍在；oracle canonical 返回 134,501 bytes、SHA `72029528fb011fb5c68299450be8e0525ae4b11eda8609ee0e4ce6f3a7b7bd4c`，原錯誤與原生輸出保留。尚無有效配對速度結果，不能宣稱長路徑歸因、300 ms Gate 或 P01 資格通過；下一步只讀定位失敗步驟，不盲重跑。
- 本段僅同步本任務 QA 記錄；其他文件 agent 的整理變更與原始資料保持原狀。真人入口沿用具名驗收指南，尚無新真人結果。
- N 正向讀取的完整 DTO（baseline／candidate／strict）相等；三側各 442 次 bounded reads、10,556 次 lstat、26 次 layout scan，候選僅將 26 次 strict manifest parse 改為 26 次 fresh issued-manifest 檢查。這是已保存的正向一致性證據，不抵銷未完成負例或未取得配對計時。
- Root 以相同 `.venv` 的 `-I -B` 唯讀單葉定位：265 字元 plain path 的 open 為 Errno 2、stat 為 WinError 3，沙箱外同結果；PowerShell 與同 Python 的 Windows extended-path 語法均讀得 2,207 bytes、SHA `57b64af7c30f9a8161ba708d6cd136b8578f700bbe19568f1683ab5f186aaa27`。收據 `output/qa/p01_filter_parallel_experiment_design_20261010_n/root_leaf_path_probe_20261010.json`。此檔案的 plain-path 存取限制已證實，但不推論全 copytree 只有此原因，也未放寬 controller 的寫入守門。O 僅建立步驟診斷候選；下一個長路徑方案仍須精確設計及審查。

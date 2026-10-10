# F03 三路準備：獨立審查後補正

狀態：實作／驗證中，不授共同 reader 資格。承接 `ed8b0506`，完整 F03 query、UI、收藏與跨程序閉環仍未完成。

## 最新接續入口（2026-10-10 UTC）

以下為本文件最新工程切片狀態；後文的日期化追加保留原始歷史，不以舊「待測」覆蓋新終態。完整補完仍依原計畫 P00–P14／M1–M3／F01–F23，這三路不代表全部產品範圍。

| 工作 | 已取得的證據 | 接下來與未完成項 |
|---|---|---|
| F03 完整母體共同發行 | C13nodes與F正常node已有原生通過；root已套入正式reader、新group-session與14節點測試，補精確prepared型態後mypy兩source綠、三檔語法綠。 | 正式17節點首輪原生終態：15 passed、2 failed／499.90s；兩紅均為測試仍依賴QA overlay環境變數，已窄修為正式module路徑及tmp_path子程序參數，修正後b封套只重驗兩節點，原生2 passed／179.68s、exit0；首輪15項加修正2項全部取得通過，未重跑其餘15項。composite query／UI／收藏／新程序／EXE待辦，不能以此切片代替全產品完成。 |
| H20 原 source-port 接線 | P9 attempt01 最終中文 stdout 被 CP1252 拒絕，不能取回內部結果；原件保留。byte-identical launcher 的 attempt02 改用 process-tree UTF-8，原生 exit1；逐row PITfalse／hash／日期及12 core negatives通過，來源與fixture不變、cleanup完成。 | 唯一首紅為 QA receipt 的 tuple dictionary key（`('original_n_base_fdopen',)`）；P10唯一attempt01原生exit0／5.04s；真fixed2讀2關、config14讀14關、1private SQLite／0source connection；來源與fixture不變、cleanup完整。negative core通過但完整negative scope仍false；原JSON loader pin、private replay等缺口保留。public cohort、Main、原2382的684bp／圖表／速度、真人仍待驗。 |
| F12 收益與跨程序收藏 | G 完整修訂已 review；8 candidate／58 source pins獨立匹配。G focused 原生exit0，8 passed／26 deselected／0.88s；前後pins零差。G Main 唯一實跑原生exit1，已到真readonly transaction連線guard；四個已知PID皆gone。 | G candidate receipt未更新終態，仍running且after／cleanup缺失；stdout明示queryfailed但錯誤截斷。已定位私有副本走rollback/not_applicable路徑，而QA只授WAL prime路徑；H僅授新增精確rollback transaction角色與完整失敗診斷的static實作，尚未授runtime；真Main／新PID收藏仍未驗完。原G保存，F17正式整合可續推，未來G修訂須明示重核pin。 |
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

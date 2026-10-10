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

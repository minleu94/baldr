# H20 合成 WAL keeper：Root 小測複核

這份紀錄只涵蓋隔離合成行情庫的 WAL 準備與複製，不代表 Main 視窗流程、原 H20 2382、收藏重開或 EXE 已通過。

Root 實讀 `output/qa/h20_wal_keeper_candidate_20261009_a/market_wal_keeper_qa.py` 的開啟邊界與 `selftest_native_attempt05.log`。小測實際為 6 passed、0.97 秒、exit 0；log SHA-256 為 `4d735a80489f961f447d9c0951123c03ca634019f5e8d40d6bd73ff5004218b7`。當時 keeper SHA-256 為 `d3982c5f42555b0fbb207ec2c9414df60824c8e81dc034fc720915a090cdad73`。

先前兩個阻擋項已有具體修正：

- 寫入前要求 caller 傳入 `expected_qa_root`，限定既存 `C:/t/h20dual_*` 的精確 case 子根；manifest、行情庫與 H20 庫都要符合固定來源路徑。目錄祖先、reparse、檔案身分、來源 hash、原有 sidecars 與 DATA_ROOT/OUTPUT_ROOT 重疊在 SQLite 寫入連線前檢查。JSON 的合成標籤本身不構成寫入授權。
- preparer 的 readback 是 dict rows，keeper 按精確鍵與型別解析，再與行情庫實際價格列比較；不再把 dict 誤當 tuple 取索引。合成 schema 補齊既有 bridge 要求的核心表，未放寬 frozen bridge。

Root 另讀六項測試的名稱與斷言：committed WAL 保留、未提交列排除、DELETE journal 拒絕、中途取消清理、manifest 漂移主錯保留、精確 dict schema，以及指向第二個隔離合成根的偽造 manifest 在 SQLite connect 前拒絕。越界負例明確追蹤零 connect calls 並比對另一合成庫起訖檔案 pin。這些小測尚不等同完整視窗流程證據；後續須核 frozen receipt、candidate diff 與 controller 的 keeper finally 生命週期，再執行新 Main case。既有失敗 attempts 保留，正式資料未作為此小測輸入。

## B controller 接線預檢與唯一 Main 執行前核對

Root 實讀 B controller 的生命週期：caller 傳入已核驗的 QA root，keeper 啟動後更新 manifest，child 前後核驗 active source group，最後關閉 keeper，primary 與 cleanup 錯誤分欄。預檢 receipt 位於 `output/qa/h20_wal_keeper_main_candidate_20261009_b/attempts/wal_preflight_20261008_01/controller_receipt.json`，Root 重算 SHA 為 `05dba2acfabb6a82f7c7aa7aee53a6d86b5b657aea8d4a6989321e783b3e35c2`。實際狀態 `preflight_passed_no_main`，Main 未啟動；22 dependency pins、4161 檔來源 inventory 與 archive 起訖不變，preparer exit 0 且 Job tree empty，keeper gate true、start/close error null。非空 WAL 24,752 bytes，checkpoint `[0,0,0]`，未提交 marker 回滾。

下一個唯一 Main 計畫為 B 的 `attempts/main_synthetic_20261008_01/prelaunch_manifest.json`，SHA `1f1c3b1d91f08f60e5ccb402605150e4f5c833142c20c4f885c4279693f971f9`。Root 重算七個 candidate、三個 fixed guard 皆符合，s3 manifest/BUILD_INFO/source_bundle hash 皆符合，確認 `C:/t/h20dual_main_synthetic_20261008_01` 尚不存在，已授權一次原生隔離 Main 測試，prep 120 秒、child 300 秒。測試使用合成 H20 +1234 bp；不取代原 2382 的 +684 bp 驗收，也不宣告新 EXE 就緒。

### B Main 實際失敗與下一步

同一 handle 95974 終態 exit 1。Root 實讀 child stderr：在視窗旅程前匯入 bridge 時，複製後的 `_load_neutral_wal_helper` 用 `__file__.parents[3]` 推導 repo root，實際得到 repository 的 `output/qa`，再附加 `output/qa`，導致 legacy bridge 檔案路徑重複而 `FileNotFoundError`。此失敗未驗證 H20 名單、下鑽或收藏。controller receipt SHA 為 `eff69c9362e205c412b31d139c3b4dab8d0f5fcab10b741ee4848663b53c5e7b`；keeper close 通過，child Job tree empty，固定 source artifact 與 snapshot inventory 起訖不變。

已交 owner 建立新的 C 候選：將 legacy bridge 以同 bytes 的固定副本加入 attempt，loader 只讀同目錄的明確檔案並維持原 SHA 校驗；不得向上搜尋、增加 fallback 或擴大來源 allowlist。先驗實際複製深度的 import 與拒絕案例，再核新的 Main 計畫；B 失敗封套保留。

### C 啟動前 Root 發現的版本綁定缺口

Root 實讀 C loader、差異檔與 plan，重算八個 candidate pins 都符合，case/attempt 尚不存在，plan SHA `0d22da2f81f1664fa0971678bed0446557a7e89961fe96f505c624519171c839`。但 controller 第 55 行 `MARKET_OPERATION_SHA256` 仍是 B bridge 的 `864301...ba27`，實際 C bridge 是 `4f510d40...8083`。舊常值被用於候選檔案核驗與 child 環境，必然在旅程前拒絕；所以沒有授權這版 Main 執行。

已要求 owner 保留這版 C 的前像與 manifest，修正 controller 固定 pin，增加 controller 常值與實際支援檔案的一致性小測，再重新發行 frozen manifest/plan。sibling import 小測本身不覆蓋此 controller 接線錯誤。

# D 候選合成接縫審查（尚未放行 Main）

新 QA-only Main 整合副本位於 `output/qa/h20_main_d_seam_integration_20261009_a/attempts/main_integration_candidate_20261009_a`。Root 已要求維持 frozen guard／legacy 原件，case 與 output 改為兄弟目錄，非空市場 WAL 僅由已核 D operation 私有複製／合併而非直接連來源。Main 預計的 H20 finish／permit release → market finish 順序與已通過小接縫不同，必須另驗正向與 primary failure cleanup，再審完整 Main 計畫。Main workers 必須 native 終態後才釋放 reader。其 s3 固定來源與最新 dev F12／Main 整合不同；此輪即使成功也不能當作最新整合來源或 EXE 同版驗收。

最新 Root 實讀正向 seam001、故障注入003與 runner 清理順序：正向 status passed，market permit 在 typed H20 reader 活躍期間核驗；market finish 在 H20 finish 前完成，來源 main／WAL 起訖相等、來源 SQLite connect attempts 為 0。兩個 SQLite alias 使用同一 frozen wrapper，結束還原；私有目錄建立／清理皆 3，private root 最後為空。故障注入保留 primary row comparison failure，detach、session close、permit release、abort、keeper close 均完成，cleanup_errors 空。這些只接受合成接縫與清理；Main 尚未執行，合成 1234 bp 不取代原保存 684 bp。已交 owner 整合 QA-only Main controller／child 並先提交新的 pins／執行計畫，Root 審查後才執行。

後續 owner 已修正 runner 路徑及匯入、兩個 SQLite alias 指向同一 frozen guarded wrapper，以及 H20 source 與 runtime/output 的測試佈局。seam006 已讀市場與 H20 副本，但在合成 REAL 欄位與字串比對時失敗；失敗後 dispatcher 未 detach 導致 abort 次錯，完整接縫尚未通過。Root 已授權僅 QA row 正規化及先 detach 再 abort／保留主次錯誤修正，要求故障注入與正常清理證據。permit 的內部 inventory 登記並非 H20 資格證明；上層必須核驗真 typed active session、來源副本 pin、query_only、transaction 與實際 guard 建立生命週期，不能只傳入任意 counters。Main 仍未放行。

Root 實際讀取 D helper、merged bridge 與 `run_frozen_guard_market_h20_seam.py`，確認副本和合併快照已改用兩個獨立目錄內的 `reader.sqlite`，目錄身分採凍結 guard 的穩定五欄格式。接縫腳本仍發現兩項前置阻擋：模組級 helper 引用的 `stat` 只在 `main()` 區域匯入，以及候選目錄 `parents[3]` 實際指向 `PythonProjects`；實際 repository 是 `parents[2]`。已通知 owner 修正。

目前 permit 的 root inventory 要求只存在自身兩個目錄，還不能證明與同 root 的合法 H20 session 同時使用。驗收必須包含 H20 session 尚未關閉時的 market reader／verification，且合法 H20 目錄需有凍結 guard 的實際核准證據；不能以任意同名目錄放行。D Main 尚未執行，以上不代表完整研究旅程通過。


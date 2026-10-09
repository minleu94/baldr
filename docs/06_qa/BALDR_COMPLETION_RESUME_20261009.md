# Baldr 補完恢復開發（2026-10-09）

## 授權與分工

使用者在交接 checkpoint `a48a86afd4de0fd9a5f85e2dd09cf370ad42281b` 後，改為由本對話繼續開發，明確要求合理分配 Luna Max subagent。暫停要求已解除；原交接文件的「暫停」保留為該次交接狀態。本輪完整範圍仍為 P00–P14／M1–M3／F01–F23。

- `resume_h20`：真正固定讀取器的 config source-port initial／terminal 窄切片；不替換 reader、不宣告公共 pipeline 或 Main 完成。
- `resume_perf`：P01 真負載 cache 診斷及有證據的新候選；固定 300ms 門檻，不重跑失敗的同一矩陣。
- `resume_revenue`：F12 C1 focused 真 Qt／parent finally／路徑負例與固定封套；完整 Main 須另經 root 審查。
- root：共同契約、F03 prepare／issue 邊界設計、原碼整合與測試審查。

原始資料、正式排程、訓練、實盤、main 及 push 不屬本輪授權。文檔 agent 可繼續整理；本輪先寫獨立 QA 紀錄，不覆寫其權威文件變更。

## 接續基線驗證

| 驗證 | 結果 | 界線 |
|---|---|---|
| 更新工作台 pytest | 85 passed，5.26s，exit 0 | 當前 checkpoint 的既有 UI 回歸 |
| Update validator 初跑 | 21 passed／3 failed／4 skipped，exit 1 | `strict realpath` 檢查隔離 data root 遭 WinError 5；價格同步失敗連帶價格與技指 empty |
| validator workspace-temp 重驗 | 同樣 21／3／4，exit 1 | 只換 TEMP 路徑不足；原失敗保留 |
| validator 受審查沙箱外隔離重驗 | 25 passed／0 failed／4 protected skips，exit 0 | 同一腳本、工作區隔離雙根；沒有降低守衛、正式資料或下載測試 |
| 全域 mypy | 933 source files 無錯誤，exit 0 | 在產品原碼修改前的基線 |
| checkpoint Python 語法 | py_compile 59 files，exit 0 | 不等於功能驗收 |
| 三路 callback group pytest | 沙箱首跑 WinError 5；受審查隔離重驗 1 passed，11.82s | 合成 callback／poison 基線，沒有共同 reader qualification |

root 日誌在 `output/qa/resume_root_validation_20261009_a/`；workbench 原 log 為 `output/qa/resume_20261009_workbench.log`。`validator_initial_failed.md`、workspace-temp 失敗、診斷 traceback 與最後通過分列，不抹去首紅。

## 原碼核對補正

F06 的 Decimal raw evidence leaf 已存在，來源 commit `8816644c`；`daily_market_technical_volatility_evidence_v1.py` 明確定義 BB30 population 2x 與 ATR14 **SMA**。它不等同 TA-Lib Wilder ATR14 或既有 regime window20；`BALDR_F06_VOLATILITY_EVIDENCE_PLAN_20261009.md` 的「未實作」僅可判讀為所述完整接線／收斂規則尚未實作，不能因此重複新增同型 raw leaf。現行 raw leaf、collector 及 query 純契約不授予 F06 收斂、突破或全母體資格。

F03 仍需將 MA 的完整材料核驗／prepare 與 issue 分離，再建立三路共同原子發行。舊 MA-only 路由的 query、index、session identity 必須相容；group member prepare 不能先發 MA seal。新增切片不改金融計算、訊號、cutoff、母體、排序或 hard gate；未來函數邊界沿現有 snapshot／exact reader，不補讀新行情。

## 正在核對的結果

F12 C1 已保留 C 原封套，新 focused pytest 9 passed／1.74s、exit 0；constructor failure 直接進真 `_parent_main()` finally，guard 為明示受控替身，此失敗注入不能當完整正向 guard 驗證。58 pins 前後一致。self-test 首跑 strict source resolve 遭沙箱拒絕，exit 1，不能由 pytest 通過抵銷；正例重驗與完整 Main 尚待 root 審查。

本頁不是發布或真人驗收收據；後續結果依實際終態追加。

## 接續切片與限制

文檔整理已另提交 `6247a177`，本輪原碼改動不混入該提交。MA 私有候選將完整 prepare 與舊 MA-only issue 分開；群組 prepare 仍只取得未授資格的 index。跨兩個 parent、完整 257 檔 included 母體、篩選後單股 selection、晚到取消／poison 與舊 finalizer 拒絕的測試正在執行；目前只完成該原碼 mypy 與兩個 Python 檔 py_compile，不將進行中測試記為通過。

F12 C1 第二次 focused receipt：`output/qa/f12_main_revenue_new_pid_20261009_c1/evidence/20261009T232553Z_26176_0ef2295c/receipt.json`。58 pins 前後一致、9 passed／0.63s；修正 QA hash 字面值少一個 `b` 後，self-test 仍因三個 AST predicates 不符而 exit 1。正在核對實際三個 chooser、Watchlist typed double-click 與明示 COW 確認，尚未允許完整 Main 正例或以 pytest 抵銷 self-test。

P01 單次真 filter trace A 在開來源階段遭 sandbox strict realpath WinError 5，沒有取得 cache observation；失敗 receipt 保留於 `output/qa/p01_true_filter_cache_trace_20261009_a/true_filter_cache_trace.json`。相同 pinned manifest 的受審查沙箱外唯讀單檔檢查成功；B 補逐階段 pins 與 progress 後才執行同一窄測試，沒有改 ACL、正式 store、stat／SHA／守衛或重跑完整效能矩陣。

H20 N 的受限 config seam 真讀取 diff 已由 root 審閱；原 pipeline phase 優先、固定 reader／session／source-port identity 與精確 path／SHA／stat 檢查保留。只核准 initial／terminal 真讀取及負例，不代表公共 pipeline 或 Main 完成；結束時未關閉 FD 應為 0，實際 close 次數另列，不能混為零次關閉。

### MA prepare 切片驗證終態

上述進行中測試於本輪結束：新群組 prepare 測試、既有 MA alignment 與三路 callback group 合計 **17 passed／360.19s，exit 0**，原 log：`output/qa/resume_root_validation_20261009_a/ma_group_prepare_attempt01.log`。新原碼 SHA-256：`e997ad46899edf802f36589c79dd2e936364dfde02b2d3bc325ab786ff46ba95`；F12 原 pin 為 `b5cfdcbf6509657cbd540e70eec15478c3e636dc46fd94328411dae72fe3fa97`。新增私有候選不呼叫 issuer；只保留 group 未授資格材料。既有 MA-only public finalizer 仍走同一驗證、index 與 issuer，測試覆蓋原全母體／篩選排序／重用來源行為。該結果不等於獨立跨程序 byte oracle 或三路共同 qualified session 驗收。

MA 原碼 targeted mypy、原碼與新測試 py_compile、tracked diff whitespace 檢查均通過。下一片為 KDJ／volatility 完整候選、group parent ledger／總 payload 上限及唯一共同 issuer；不得先發 MA 再補驗其他路。

### P01 真 filter trace 終態

`output/qa/p01_true_filter_cache_trace_20261009_b/true_filter_cache_trace.json` 已取得一次真 filter 操作診斷，exit 0，來源／sealed store／DB／query／selection／page pins 前後一致。instrumented wall 1007.45ms／CPU 1000ms，**不是 p95，也未通過 300ms 門檻**。render：11,102 calls、581 unique、5,181 hits、5,921 strict conversions；component：494 calls、446 unique、12 hits。component 暫存 832,790 UTF-16 bytes，占實際 cache 用量約 79.5%；render 另有 5,789 次因 byte cap 不插入。stat／SHA／strict renderer／取消函式 identity 保持原樣。

下一候選只移除 component tuple 的 cache admission，保留原 canonical guard 與相同 root-to-leaf tuple，讓 4096 entries／1 MiB 預算供 render 使用。正式檔仍未修改，須等 F12 固定 pins 測試完成，並同步調整既有 component-cache 測試，使深路徑、精確 spelling、fresh lstat／reparse、取消、render scope／cap 的行為證據維持。候選通過 focused checks、root diff 審閱後才核准一次新效能矩陣。

### 2026-10-09 接續驗證

- H20 N attempt02 窄測試已由 root 實讀收據與負例、獨立重算 N／M／terminal SHA：initial／terminal 各一次 4046-byte 真讀取，open／fdopen／read／close 各 2，最終 descriptors 0；7 負例全拒絕，ledger 60／60、overflow 0，OS／SQLite aliases restore true，SQL connections 0。source／fixture 起訖一致。N SHA `fbc0a4261dafbc861e31590099294c8d295031a335f220c5d714b2bc281d2908`，收據 `output/qa/h20_guarded_fixed_read_slice_20261009_n/attempt_02_runner_receipt.json`。僅 config＋terminal reader；snapshot loader 仍以明示 stop-before-SQL sentinel 隔離，沒有完整 source verifier、公共 cohort、Main、原 2382 或 EXE 驗收。sandbox import失敗及 attempt01 inventory-before-binding／cleanup 失敗原封保留。
- P01 正式窄候選已修改 `personal_data_paths.py` 與原 component memo 測試，source SHA `adf0b776dbced091e0f27b84de76daa87986302548ff635cc6e6e738d92650f2`。agent 定向 16 passed／29.47s、source mypy／兩檔 compile 通過；root 實讀 source／test diff，canonical、fresh I/O、取消守衛及 4096／1MiB 上限保留。尚未完整量測，不宣稱 300ms 通過；正準備固定新 overlay／manifest／runtime inventory。
- F12 C2 已停止測試並解除 paths source freeze：`output/qa/f12_main_revenue_new_pid_20261009_c2/evidence/20261009T234140Z_27472_01d06201/receipt.json`，58 source pins 前後穩定、route contract exit 0、12 focused passed／4 subtests passed；self-test exit 1，固定合成 source root 的 segment000002 parent 不存在（WinError 3）。正唯讀核查 helper 路徑或 artifact 缺失，不能用空目錄、忽略缺件或 latest 替代；未跑 full Main。
- root 新增三路私有 preparation module／測試：核完整母體 order／clock／snapshot／raw-window／source pin、每路及整體 payload 上限、串流雜湊與取消；候選始終 reader-issued false。targeted mypy／compile 已通過，真 257 檔雙 parent 與失敗清除測試正在執行（session 61051）；尚未共同 issuer／qualified query／UI／bookmark 接線。

### 三路 preparation 核驗終態與 F12 長路徑補正

三路私有 preparation 首輪為 **7 passed／281.43s**（`three_member_prepare_attempt01.log`）。其後補齊 canonical payload 的 identity 欄位大小、途中 budget 變動與候選 entry 物件一致性核驗；純雜湊／大小計算測試 **2 passed／0.78s**。最後實際雙 parent 正例、整體 payload 超限及晚到 budget 變動負例為 **3 passed／211.46s，exit 0**，log：`output/qa/resume_root_validation_20261009_a/three_member_prepare_attempt02_boundary.log`。最終 module SHA：`fdfd3602f346335365b3b14d31b1dd58b18ae5ad335509f87a69c379a7e823fa`；targeted mypy、兩檔 py_compile 與 whitespace 檢查通過。候選仍未授 reader 資格，不代表共同 issuer、公開 query 或 UI 已完成。

F12 C2 的「parent 不存在」判斷已補正：實際目錄存在，274 字元普通路徑檢查誤判，extended 路徑讀取成功。C3 僅修正 QA helper，使用原 pinned resolver 的 plain canonical label、fresh ancestry/no-reparse 及原 extended tree signature；實際長路徑正例與同 lexical path junction 負例均通過。root 獨立審閱 C2→C3 diff 與 receipt，接受此窄範圍證據：**14 passed、4 subtests passed**，self-test／route contract exit 0，58 source pins 一致；僅 paths pin 更新為核准的 `adf0b776dbced091e0f27b84de76daa87986302548ff635cc6e6e738d92650f2`。收據：`output/qa/f12_main_revenue_new_pid_20261009_c3/evidence/20261009T235351Z_40512_f619993c/receipt.json`。未重建來源、未執行 full Main；安排在 P01 效能量測後驗證，避免競爭 CPU。

# F02 v4 獨立 oracle 與監督器接續審查

此紀錄承接 v2／v3 的來源計數修正與既有 g 守衛封套，不代表 F02 全流程、Main、EXE 或真人接受。

v4 target `output/qa/f02_ma_composite_257_acceptance_20261009_v4_oracle/run_f02_ma_composite_257_acceptance_v4_oracle.py` SHA 為 `ca8663ad43dc3c83e4132ec740ca6d7fad84c38197dfa65a4763c31eda3f485b`。獨立 Luna Max 已對 raw fixture、MA／量能 Decimal ratio、1257 processed＋missing 身分與 22 組 counts／會員／排序／頁碼提出通過裁決。報告 `output/qa/f02_v4_root_independent_review_20261009_a/oracle_review.md` SHA `347beb95d697d5aae03b6da28957353ae11a3b5a5316930d12cfa4d0d30de433`。

Root 重跑純 oracle 自測 exit 0，日誌 `v4_oracle/root_pure_oracle_review.log`（該相對簡稱指上述 v4 QA 目錄）；ratio、missing 身分／旗標、排序／會員與頁邊界負例拒絕。原料 ratio 的 28 位 Decimal 精度也與既有 factor 邊界核對一致。此模式未執行 producer 或 SQLite，不授 public reader 接受。

新 h supervisor `output/qa/f02_ma_composite_257_acceptance_20261009_h/supervise_f02_ma_composite_257_v4.py` SHA `2769cb4c5bda68dd73062ac889b31aed2a0a20a5b6668a08fed4c263691d19da`。Root 實讀 `g_to_h_supervisor.diff`，差異只為 v4 target path／SHA、QA 根與新外層 attempt prefix；守衛、來源限制、Job、deadline 與 cleanup 未改。g 前像 `939f65fcb13739fad0b4fff5ff8b6a966d54c1bc2747520d08a342d9ef73bd65` 保留。

h guard-only native 自測 exit 0，`guard_selftest_20261009_002/terminal.json` 的 source pins 符合，stdout SHA `dfe0273edd17514ab1809e8b33591068f64559f4dbca53b3c7f01458fecea788`、stderr 空；這輪是一般路徑 guard 自測，不另冒稱再次完成所有 fdopen／hard-link 特例或 manifest publish。初次 sandbox 的 WinError 5 失敗封套保留。

Root 已授權 h 以 `--run --private-parent C:\t` 執行唯一全新隔離合成矩陣。該次執行已終止，未通過完整矩陣；不得以批准紀錄宣稱測試通過，也不得裸跑 target 或更新既有失敗封套。

## h 執行終態與下一候選

Owner 的有界讀回診斷保存在 `output/qa/f02_ma_composite_257_acceptance_20261009_h/full_run_20261009_001/readback_diagnosis.json`。worker 執行固定 target 時仍帶入 supervisor 的 `--worker --outer-attempt` 參數；target 入口只接受 oracle 自測或空參數，因此以 usage 終止，沒有進入 `_run_case()`、producer 或 SQLite，也沒有建立 target attempt。此失敗不能解讀成產製器或篩選計算失敗。

同一封套另記錄外層繁中摘要輸出受到 cp1252 編碼限制而拋出 `UnicodeEncodeError`。Owner 已保存 stdout、stderr、來源起訖、supervisor 收據與清理證據，沒有直接重跑。

已分派 owner 建立全新 i 候選：固定 target 執行前暫存 `sys.argv`、設定為單一 target 路徑並於 finally 還原；啟動命令明確使用 `-X utf8`。先完成入口參數正反驗證與守衛自測，再交 Root 核對 diff 與 SHA。此分派尚未批准下一次完整矩陣執行。

## i 候選實讀審查與執行批准

Root 已直接核對 h→i diff：只新增固定 target 的 argv 隔離 helper，並將 worker 的既有 `runpy.run_path` 呼叫改為該 helper；來源 guards、allowlist、Job 與 deadline 未修改。重新計算 supervisor SHA-256 為 `FFF65A436E48F6EC54778D91E85E87DC2BB571F3E39E891F68EFB3A1D2A4435E`。

入口自測原始碼驗證 target 僅收到固定路徑，成功與 `SystemExit` 均還原 supervisor argv。`entry_selftest_20261009_002/terminal.json` 記錄自測及 compile exit 0；`guard_selftest_20261009_001/terminal.json` 記錄 guard-only exit 0、stderr 空。兩者 source SHA 均符合固定 i 與 v4，沒有啟動 producer。自測使用替代 runpy 呼叫，因此只能證明 helper 契約，不能視為 target 矩陣完成。

已批准 owner 以固定 i supervisor、`-I -B -X utf8 --run --private-parent C:\t` 執行一次全新隔離合成矩陣；保留實際 target 收據、完整 streams、來源起訖與 Job 清理證據。完整矩陣仍待實際終態，未批准原始資料或正式排程操作。

## i 實際終態：保存候選檔讀取拒絕

i 的唯一執行 `full_run_20261009_002` 已 terminal exit 1，完整 stdout 為 820,845 bytes，stderr 空。Root 直接解析 stdout 收據：worker `bundle_create_failed`，target attempt 已建立；Job `empty_before_close`、`job_closed=true`、`zero_owned_processes_proven=true`。因此這次已進到 target，與 h 的入口參數失敗不同。

Owner 讀回 target 失敗收據為 fixture_creation 階段，唯一 guard denial 是 `bundle_link_candidate_read_failed`／`FileNotFoundError`。現有收據沒有精確候選路徑、caller label 或 exception cause chain，不能證明是 Windows 長路徑問題，也不能據此修改 guard 或宣告 producer 正常。

已分派新 j QA 候選補有界診斷及獨立合成長路徑微案例，保留既有 i／target 失敗封套，不放寬拒絕條件。Root 先審 actual raw／extended-path 讀取與呼叫位置證據，再決定修正；尚未批准 j 完整矩陣執行。

## j 診斷與 k 有界修正的接受範圍

j 的真固定 writer 微案例證實：265 字元 candidate 的原 Path.read_bytes 得 errno 2；同檔 extended-path bounded read 的 bytes／SHA 與 lstat／fd 身分吻合。原 guard 仍拒絕，未發布目的檔。獨立 Luna Max 審查只支持窄幅修正與有界自測，未支持完整 F02 已通過。

k supervisor SHA `bea3e66aa22dbb9d4a041c7ef670f11fef2614e6ce5d55aa9b13375565e41355`，摘要 `output/qa/f02_ma_composite_257_acceptance_20261009_k/k_review_summary.json`。真長路徑自測 `_004` 已經固定 `_publish_objects` 發布 274 字元目的檔，核發布後 nlink=2、候選清理後目的 nlink=1；來源 pins 不變。固定 writer negatives 與 generic negatives 另有 exit 0 收據，早期兩次失敗保留。沒有完整 producer 終態。

Root 實讀 j→k diff 後另派 Luna Max 唯讀審查；目前發現新 bounded-read helper 的四個實際呼叫點受原 token 與 4／8 MiB 上限控制，未增加 link／unlink 能力，但 helper 本身未固定 caller／budget，且既有 negatives 未注入 fd 身分、mtime、讀取超界競態。此缺口不由 generic 15 個案例折抵。完整矩陣尚未批准；需在新 immutable 候選補 helper 自身硬界與相應拒絕案例，保留 k 原證據。

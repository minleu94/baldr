# 2026-10-07 排程故障修正與有限驗證

## 文件 Coverage Pass

| 文件 | 優先級 | 更新範圍 |
|---|---|---|
| 本 QA | Must | 原始失敗、程式修正、隔離驗證及未完成的自然驗收 |
| scripts/scheduled/README.md | Must | 每日 Direct 有限 cycle、Paper 開盤重試與排錯 |
| APPLICATION_MANUAL.md | Must | 入口、步驟、參數、結果與安全限制 |
| PROJECT_SNAPSHOT.md | Must | 本次有限工程交付及尚存阻擋 |
| DOCUMENTATION_INDEX.md | Must | 本 QA 導航 |

Scoped SSOT 核對：本次不改產品 Gate、6M 優先序、架構邊界或來源授權，Roadmap／Architecture 無需修改。Manual 六項完整性由以下維運段落補齊。無待使用者補充的修正參數。

## 修正與原始證據

- Codex 原失敗為 sandbox setup refresh，node_repl executable 被占用。重新啟動後本 chat 的唯讀 shell 已恢復；不能回填早晨 heartbeat 為成功。
- Forward 原 run `20261007T124002333067Z` 等待共用 heavy-chain reservation 至 08:00 PDT，結果 `heavy_chain_reservation_timeout`、exit 2。Direct maintainer 原長駐 watcher 在完成／無新輸入時仍持鎖；每日 wrapper 已取消 `--watch-formal-inputs` 並限制 `--max-restarts 1`，由現有 finally 釋鎖。人工 watcher 介面保留。此修正不保證耗時的有效訓練可在 Forward deadline 前完成，也不跳過互斥鎖。
- Paper EOD 的原 receipt 是 `output/paper_execution_eod_replay/receipts/paper_execution_2026-10-07_30429f03efb3791f_20261007T130007470295Z.json`。唯讀 SQL 確認 `paper-main` ledger 有 8 筆 2026-09-08 記錄。原 policy context 用本次 decision_date 宣告 history start，誤拒舊列；現改以同 portfolio 非未來 ledger 日期與 snapshot 日期最早值，並要求官方日曆覆蓋整段。全部舊列留給原 adapter 驗證，不刪列、不把它們授予歷史 PIT 資格。範圍超過 3660 日或日期不合法仍拒絕。
- 10/07 原開盤 raw response 的 SHA 為 `sha256:48ab4c954d9fc1d6d705c2842496b7678dd32b1377bdedabec03f1988b1cc31d`。原 request 有 8 檔；多檔尚未成交列是 08:59:55～59、open/last `-`、volume `0`，另有一列空 symbol。現只將 capture 在 09:00～09:02、同日最後一分鐘且未成交的盤前列分類為 `session_open_not_ready`，讓既有最多 3 次／間隔 30 秒重取。回傳列仍不接受；重取若仍有空 symbol、identity、hash、日期或價格錯誤，仍 blocked。所有 rejected raw 診斷保存；未製造當日 durable manifest。
- Paper Portfolio 在等待 cutoff 時受中止，原 heartbeat stale、缺 terminal。wrapper 現於可捕捉 `KeyboardInterrupt`／`SystemExit` 寫失敗 terminal 後重拋；原 Exception 路徑保留。OS 強制終止仍無法保證 Python terminal，此時以 stale heartbeat＋Scheduler 結果判讀；不改寫舊 heartbeat。

## 驗證

- 最終 affected suite：**191 passed、1 skipped**，23.19 秒。JUnit：`output/qa/schedule_repair_20261007_pytest.xml`。六組覆蓋 Paper daily producer、formal source chain、scheduled Direct、Paper Portfolio、Direct maintainer 與 Forward。
- 五個變更 production Python 檔：mypy 與 py_compile 通過；`scripts/quant_guard_linter.py` 通過。
- 原始開盤 raw bytes／SHA 不變；修正 parser 的唯讀回放得到 `session_open_not_ready`、接受列數 0。保存於 `output/qa/schedule_repair_20261007_saved_raw_readback.json`。
- 測試需 immutable receipt hard-link。sandbox 的 WinError 5 曾造成大批 fixture 失敗；改於 host 執行隔離 TEMP fixtures 才完成回歸。這些先前失敗不是綠燈；最終結果與環境限制分列。
- 唯讀時鐘／資料自查：history helper 僅使用 `event_date <= decision_date`；開盤重試不接受盤前價格，不覆寫決策日／capture 時鐘。金融核心無新增裸 float。

## 首輪尚未恢復的自然證據（延伸驗證見下）

原二次驗收：`output/qa/paper_heartbeat_20261007_recheck_20261007T170400Z/audit_summary.json`。Decision snapshot public reader 的 ID、hash、context pins 通過，仍 research-only。

G6 正式 raw source revision hold（`DailyPriceSourceRevisionError`）仍存在；B adapter 與 current-stock research cycle 未具備同次成功。G9 已保存 `technical_source_refresh_blocked`／`pinned_raw_run_cycle_is_not_same_run_date_success`，不是可直接假定的 race。Bank lane 亦受 source revision guard 阻擋；未做 source rebuild／migration。

Sector 最後可讀 status 為 10/05 23:00 UTC 的 DNS／verified denominator blocked，不能代表 10/07 中止 run。ML Allocation 最後完整 status 為 10/06 00:30 UTC `blocked_missing_release`，也不能替代 10/07 結果。Scheduler Operational log disabled，三個 task 的 0xC000013A 不足以證明同一個終止原因。

首輪只修改程式、測試、文件及 repo QA；當時沒有手動啟動正式 Task、producer、訓練，也沒有寫正式／Paper DB、刪鎖或補 historical capture。使用者後續要求全部處理，延伸實際執行如下；兩輪證據不可混為自然排程成功。

## 延伸修正與實際恢復

- Direct 既有 Windows 任務由美西 05:30 移至 10:00；預設註冊參數同步。COM readback 確認僅 StartBoundary 改變，ACL、principal、action、settings、enabled 皆保留，未手動 Run Task。備份及結果：`output/qa/schedule_recovery_20261007_direct_task_before_update.xml`、`schedule_recovery_20261007_direct_task_update.json`。有限 cycle 加窗口調整減少晨間競爭，仍不宣稱長耗時訓練保證避開每個未來窗口。
- 原 10/07 TPEx 股票 6129 漲跌欄為「除權」，projection 曾拒絕而使 B／current-stock cycle 未執行。現與「除息」一樣保存 source annotation，數值為 missing，未知文字仍拒收。CLI output-root 改由既有 research storage 設定解析，未改 storage 設定。真實同日資料 1,967 列（TWSE 1,094／TPEx 873）projection 與 B adapter 已通過、原 raw／正式 status 保留。
- 原 Paper capture 把 1569（上櫃）送往 `tse`，回傳空 symbol；producer 現從決策日已驗證行情 custody 解析 `tse`／`otc`，每列 exchange 必須與 request 相符。真實唯讀對照 1303／1714 為 tse、1569 為 otc；兩市場 receipt／raw pins 已核對。此證據不是新的開盤 manifest。
- 原 10/07 缺 durable manifest 收據已宣告不可補歷史、非 retryable、無 ledger／formal credit。現只讓同類已過當日 15:00 且候選與來源身份完整的 rejected 收據離開重試屏障；實際原收據唯讀驗證通過、bytes 不變。沒有刪 ledger、queue 或寫 fill；新日是否完成仍須自然執行。
- TPEx 官方 HTTP 曾回 520 或 HTML；相容 User-Agent／Cache-Control 已取得合法 JSON。新的 Sector capture 於臺北 10/08 02:46 完成 1,988 列 custody、archive 與 consumer，狀態仍 degraded，因官方 CSV 主機 DNS NXDOMAIN。receipt：`output/formal_daily_publications/scheduler/pit_preopen_capture/recovery_verified_20261007/latest_status.json`。這是 10/08 實際前瞻採集，不回填 10/07。
- 官方資料集 [18419](https://data.gov.tw/dataset/18419)／[25036](https://data.gov.tw/dataset/25036) 仍列 `mopsfin.twse.com.tw` CSV；本機及 1.1.1.1 曾回 name does not exist。後續實際 HTTP 重新可讀，使用相容 Accept header 後完整分母 1,988 檔、CSV／JSON／metadata／Swagger／license 皆驗證通過；收據 `output/qa/schedule_recovery_20261007_sector_full.json`，分母 file SHA `sha256:29c4b68ef21fb864c05b3ce1e003a5fcd7e98683b4edeba0325636e0c9eaa2a3`。完整 cross-source／授權契約保留，未合成 CSV 或冒用舊分母。
- 獨立 Python 恢復呼叫第一次略過正式 CMD wrapper 的 Rule prepublication，導致 taxonomy 缺同日 parent，並非正式 wrapper 缺少該步驟。已按 wrapper 的既有順序、真實 10/08 盤前時鐘補建 `clock-20261008-machine-v2-e4cbe23dccd2-85d50c270d9a` candidate；唯讀 DB、create-only repo bundle，結果 `output/qa/schedule_recovery_20261007_rule_parent.json`。完整 Sector taxonomy 正在重驗；不改寫舊日證據。
- ML Allocation 原「缺 release」實為 `DailyPriceSourceRevisionError`：既有模型 artifact 已隔離。現獨立輸出 `blocked_source_revision_release` 與具名原因；原阻擋證據保留。已唯讀驗證另一修訂研究 release `restated-repair-4db92a237e3ad10a`（identity `sha256:34ae38b0e733ee5dfd7ea10c1dfc2ec2b95f70c0cecb3a5634f15c8d5e109708`），62 欄契約相容，但現有正式 raw exporter 仍受 revision guard；單改 release 路徑不能完成正式 Forward，不進行此種假修復。

## 延伸驗證記錄

- 七組 affected 回歸 **218 passed、1 skipped**：`output/qa/schedule_repair_20261007_full_recovery_pytest.xml`。
- HTTP／分母／Paper source 後續回歸 **54 passed、1 skipped**：`output/qa/schedule_repair_20261007_source_final_pytest.xml`。
- Allocation **28 passed**：`output/qa/schedule_repair_20261007_allocation_final_pytest.xml`。首次 27 passed／1 failed 因舊測試固定 200 GiB 與 HEAD 已有 20 GiB 容量 SSOT 不一致，現測試引用共用政策常數；容量政策未改。其他 fixture 曾遇 sandbox hard-link／Windows 長路徑，已使用短 TEMP host 隔離驗證，失敗記錄不作通過。
- 新變更 production 檔 mypy、全部變更 Python py_compile、量化精度與 look-ahead guard 通過。
- 已實際完成新的 current-stock 研究恢復鏈，run `recovery-raw-20261007T182844996044Z`，非自然排程、非正式訓練、無原始／Paper DB 寫入。研究產物不可變保存，研究 registry／reuse index 依既有 producer 追加；正式 pointer 未改。完整來源／snapshot／B／outcome pins 在 `output/qa/schedule_recovery_20261007_research.json`。已完成 snapshot、raw publication、30,891 observation／49 feature outcome；fit 於 19:01:51 UTC 完成，29,957 samples／40 verified folds、`verified_base_outcome_only`。Legacy sidecar、十檔 registry 與 reuse index 於 19:20:26 UTC 完成，terminal SHA `sha256:89cdd2e750d9b188a0b029e34e9daa7928c64a7906de40a62e7d0a7f130f4c68`。`formal_training_eligible=false`，full allocation teacher 仍未提供。
- Bank 於 19:38:20 UTC 完成 `verified_research_sidecar`，receipt SHA `640e109c4b2356fe99d75e77aa540528a7dfc2d81fbb5c8867803059acf26642`。實際 reader 核對 Legacy／Bank binding、sample cohort 與十檔 CORE19 numeric vector hashes 全部一致；Bank 仍使用既有 1,000 股估計費率情境、Legacy 為原固定 50 bp。沒有模型重訓、formal calibration 或 broker action；Bank 成功是此新研究鏈的消費成功，不能回寫舊 G9／Bank 自然失敗 run。
- cycle 結束後實際短暫 acquire／finally release 既有 OS heavy-chain lock 成功：`output/qa/schedule_recovery_20261007_lock_readback.json`。沒有刪鎖或憑 PID 回收鎖，可確認當次恢復作業已釋放 Forward 的共用鎖。
- 原官方 ISIN 全市場 HTML 有 35,434,238 bytes，第一次真實 HTTP download 約 8 分鐘，之後 parse／驗證亦需時間。新增 `read1` 分塊與單調時鐘總門檻，避免只有 socket inactivity timeout 而無總界線；每次 socket 30 秒、整份回應 15 分鐘門檻，若最後一個 socket read 跨過門檻則回讀後拒收。最初 60 秒門檻曾誤拒此正常大型來源，已依實測校正，失敗 attempt 保留。分類 producer mypy／compile／量化 guard 通過，分類四組 fixture **60 passed／1 skipped**，總時限校正後四項串流界線測試另重驗通過。
- taxonomy blocker 是設定內的 8183 終止上櫃 overlay 已不在當日完整官方分母，原 strict validator 正確拒絕。已保存原設定並以獨立 QA 設定移除當日不適用的 overlay 重驗，完整 live 成功後同步正式 caller；未放寬 validator、未刪歷史 termination proof。`output/qa/schedule_recovery_20261007_sector_scope_complete.json` 為 `machine_verified_candidate`、exit 0、blockers 空；taxonomy coverage complete、rule scope compatible false，仍為候選／研究分類，不授予 formal 資格。
- 首次正式設定重用曾被 `late source config proof is missing` 擋住，原因是 proof 設定只接受 10/01 特定保存路徑。現額外只接受既有 canonical live 設定 `scripts/scheduled/pit_taxonomy_source_config.json`；必須與原 attempt 的 canonical config hash 相同、完整重驗 bundle／descriptor／receipt／completion linkage，且全部產製／回讀在同日 08:30 前完成。新 capture 自動保存 proof；重用只允許缺失 proof 的同日補產製，partial cache、hash 錯誤或 custom path 一律保留 blocked。原 bundle／attempt bytes 不改、historical availability／PIT／formal credit 仍 false。
- 最終正式 caller 回讀：`output/qa/schedule_recovery_20261007_sector_production_final.json`，`machine_verified_candidate`、exit 0、blockers 空、`capture_mode=reused_existing_split_candidate`、taxonomy `verified_reused_existing_split_candidate`，沒有 HTTP refetch 或新 capture attempt。來源 proof 自動流程五組回歸 **70 passed／1 skipped**：`output/qa/schedule_repair_20261007_taxonomy_reuse_final_pytest.xml`；兩個 production 檔 mypy、py_compile、量化 guard 通過。
- 全部 12 個變更 production Python 檔的最終合併 mypy 檢查通過，使用 `--explicit-package-bases` 避免 CLI 路徑與 `scripts.*` import 被視為重複模組；沒有為型別檢查修改 runtime package 結構。最終證據彙整：`output/qa/schedule_recovery_20261007_final_summary.json`。

## 最終邊界與待驗事項

這輪已完成確認的程式／設定故障修復、實際研究鏈與 Sector 來源／重用驗證；原始與 Paper DB 保留，沒有手動 Run Windows Task、broker action 或正式模型／資料 pointer 切換。復原產物使用新 run／收據，不回寫原自然失敗。

1. 10/07 遺失的開盤 capture 無法補為當時 durable manifest；原失敗保留並可按非 retryable 逾期規則結案，下一自然日才驗新 capture／EOD。
2. 舊 ML Allocation route 的模型 source-revision quarantine 與正式 historical raw qualification guard 仍有效。另有已驗證的修訂研究 release，但只改 path 不會修復 input contract；新的 current-stock／Legacy／Bank 研究成功不等於替換舊 Allocation release、具備 full allocation teacher 或取得正式歷史 PIT 資格。
3. 修正後的 Windows Task 真正自然 trigger、Paper durable manifest／terminal／ledger 與原 G6／G9／Bank 自然同 run 消費仍待驗；既有 Codex heartbeat 只讀證據，不把手動研究恢復當成自然成功。

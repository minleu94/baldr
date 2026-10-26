# Gate 2 working-copy 接線與 Gate 3 現況觀測可見性 QA

> 日期：2026-10-26。此收據記錄原始碼與合成測試範圍，不代表實際 Owner 核准、來源接受、Gate closeout 或 ML 資格。

## 變更摘要

- Evidence Review「覆盤歷史」新增 working-copy DB 選擇與還原預設。自訂來源限定既有一般檔案、`LEGACY_COMPAT` 路由及非 production-like 路徑；history dashboard 與 Owner approval hash 重查共用同一 DB。兩者均唯讀；缺檔／缺表不建立 DB 或 schema。正式 DB、PERSONAL／LEGACY_READ_ONLY 的自訂 DB 選擇會被拒絕。Owner approval 仍只追加至獨立 JSON projection。
- Decision Desk 將 `fundamental_current_observations` 的 SQL 彙總呈現於「資料可見性與擴充因子」：市場／種類／來源版本／期間基準分布、basis verification、aggregate-feature 標記及 available-at 已知／缺漏筆數。查詢依 `as_of_date <= cutoff`，不讀金融數值，且 summary 明示僅供研究、歷史 PIT 未驗證。
- 所有計數只是本機表欄位的描述性摘要；時間戳語意、時區、來源授權、修訂歷史、issuer coverage、PIT、formal acceptance、Gate 與 ML 資格仍未驗證。

## 驗證

| 項目 | 結果 |
|---|---|
| 聚焦 weekly history／approval／source guard／Evidence Review wiring／Decision Desk／visibility tests | 150 passed |
| `tests/test_ui_qt_update_view_workbench.py` | 93 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped |
| 全量 mypy | 1,147 個來源檔，無錯誤 |
| 15 個修改 Python 檔 `py_compile` | 通過 |
| `git diff --check` | 通過；僅有既有 LF／CRLF 提醒 |
| Feature Map targeted check | 通過；新增 DTO 與代表測試已加入 market-explore change patterns |
| Architecture／Weekly Review Runbook targeted checks | 通過 |
| Application Manual link check | 未通過：既有兩個 `output/trial/.../TRIAL_GUIDE.md` 連結因 `output` junction 回報 WinError 5，與本次新增段落無關 |
| 原生 GUI／實際 Owner UAT | 未執行 |

隔離收據位於本機任務 scratch：

- `weekly-history-visibility-final-v2.log`
- `required-workbench-weekly-visibility-v2.log`
- `required-validator-weekly-visibility-v2.log` 及該次 validator 報告
- `required-mypy-weekly-visibility-v2.log`
- `required-pycompile-weekly-visibility-final-v2.log`

驗證僅使用合成／隔離測試 DB；沒有讀寫正式 DB、建立真實核准 projection、接受來源、啟用 scheduler 或變更 Gate／ML credit。下一步需用實際既有 working-copy 由 Owner 覆核，再逐項補足三個真實週期、三個操作日、backup／rollback／recovery 與 scheduler approval；Gate 3 還需來源條款、欄位契約、PIT 與市場 coverage 證據。

## 2026-10-26 weekly collection 索引掃描修復與隔離重跑

Task Scheduler 的 2026-10-25 weekly collection 上次因 core process timeout 失敗，沒有產生週報。追查發現 `_read_weekly_source_coverage` 將 `日期` 欄包在 `REPLACE(TRIM(CAST(...)))` 內做 WHERE，SQLite 對正式 `daily_prices` 日期索引只能 full scan。collector 現改用原始 `日期` 欄的 compact `YYYYMMDD` 與 ISO `YYYY-MM-DD` 雙範圍 predicate 做篩選，保留標準化日期作分組；合成測試核對索引可用與 ISO 日期仍會納入。Focused collector tests **7 passed**，兩個修改 Python 檔 `py_compile` 通過。

修復後從正式行情 DB 以 SQLite `mode=ro` 執行同期間候選採集；候選 sidecar／輸出都在隔離 scratch，正式 DB 未寫入。實際報告 `v2_2_weekly_collection_20261025.json` 的 SHA-256 為 `4BDFC5BEFCB1D0DC925F0D8057EB36D0209FA8258C14085725BA767F274C7471`，run record `ewc_58409a20689d74be`：2026-10-19..25 觀察到 7,859 列、1,987 個股票、4 個交易日、0 重複列；16 列 OHLC 缺值均有同日 TWSE custody receipt 證明官方值為 `--`，未驗證原因 0 列。coverage 仍為 `degraded`、collection／Gate credit 為 `pending_human_review`；母體未知，未宣稱全市場覆蓋。`write_intent=false`、`source_write_allowed=false`、`human_approval_required=true`；沒有 append 正式 sidecar、修補 OHLC、接受來源或授 Gate credit。隔離 scratch 報告：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-candidate-rerun-20261026-10f453771a23\output\scheduled\v2_2_weekly_collection\v2_2_weekly_collection_20261025.json`。

正式 `twstock.db` 的 `mode=ro` query-plan 複核回報 `MULTI-INDEX OR`，compact 與 ISO 兩個分支都 `SEARCH daily_prices USING COVERING INDEX idx_daily_prices_date (日期>? AND 日期<?)`；只有分組用 `TEMP B-TREE`。這證實 WHERE 不再全掃日期索引。正式 DB 僅供此 query plan 開啟，未讀行情列或執行寫入。

後續以核准的唯讀權限重跑 PROJECT_SNAPSHOT 單檔 document-control check：**12 features／1 link source／0 errors**。先前 27 個 `output/` junction `WinError 5` 是 sandbox 存取限制，並非失效連結；此檢查不修改文件或外部產物。

## 2026-10-26 Gate 2 weekly candidate review packet

Root 從目前隔離候選的 `evidence_scheduler.db` 只讀 sidecar 為 `ewc_58409a20689d74be` 產生具名覆核輸入包。候選報告 SHA-256 `4bdfc5befcb1d0dc925f0d8057eb36d0209fa8258c14085725ba767f274c7471`；來源 SQLite fingerprint `sha256:4c2066b6169ec366080466f6fec3d591ddb01643fef62234e0300cf5fb301721`；sidecar SHA-256 `4c495eb6ede0daf95b574ab2b74bebe04f52b3d6d571fa4a9f69a03f7184064b`。候選期間 2026-10-19..25，觀察 7,859 列／1,987 檔／4 個交易日／0 重複列；16 列 OHLC 空值均有同日官方 TWSE `--` receipt，預期市場母體仍未知。

覆核包位於 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-review-packet-20261026-ewc_58409a20689d74be\approval-input.md`，機器輸入 `approval-input.json` SHA-256 `0d541e50941bd774deee7235b302bc0bbb52ecd44ee2be85c569a853f6c61e44`。狀態 `needs_named_owner_reviewer`、1 筆 pending；owner／reviewer 欄位與 review decision 都空白；`formal_credit_authorized=false`、`production_scheduler_allowed=false`、`write_performed=false`，source sidecar hash 讀回不變。此包是供人檢視的候選輸入，不是 review history、approval projection、live recovery rehearsal 或 Gate credit；Gate 2 仍需具名 Owner／Reviewer 審核、三個真實週期、三個操作日與 working-copy backup／rollback／recovery 證據。

## 2026-10-26 隔離 Gate 2 recovery rehearsal 工具

新增 `scripts/rehearse_weekly_review_recovery.py`，供人工以既有非正式 weekly-review working-copy DB 與 approval projection 執行可重複的備份／還原演練。它拒絕正式 `twstock.db` 路徑、來源檔 reparse point、非空 WAL／rollback journal、正式／輸出根底下或與來源重疊的 scratch、無效 projection schema，以及 `formal_credit_authorized=true`。只有全新 scratch 根目錄可寫入；source DB、WAL、journal 與 projection 都做前後 hash 讀回。實際 Scheduler 不會被呼叫或停用，disable-first 僅在 scratch 模擬。故障注入後工具把備份還原成新檔，保留故障副本，核對 SQLite `quick_check`、週報 ID／hash／期間摘要及 projection bytes／record count。

本輪對合成 weekly history DB 與 `formal_credit_authorized=false` 空 projection 執行 focused tests **3 passed**；包含成功還原、正式 DB 路徑拒絕、非空 WAL／journal 拒絕與禁止 formal credit。新工具 mypy **1 source file clean**、兩個修改 Python 檔 `py_compile` 通過；Feature Map／QA／Runbook scoped document-control **12 features／5 link sources／0 errors**。PROJECT_SNAPSHOT 單檔核對仍列出 **27** 條既有 `output/` trial/task 外部連結越界，均非本次新增連結。這只證明 utility 的 scratch recovery 機制；未用實際 working-copy／Owner projection 做 live rehearsal，未操作 Task Scheduler，不算 backup／rollback Gate 完成，也不授 Gate credit。Windows sandbox 拒絕 scratch 內 `os.replace`，實作改為將備份還原至新的 scratch 檔，保留故障注入副本，避免覆寫任何來源。

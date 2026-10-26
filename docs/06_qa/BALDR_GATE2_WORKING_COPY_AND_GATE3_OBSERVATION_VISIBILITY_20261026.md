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

## 2026-10-26 隔離 Gate 2 recovery rehearsal 工具

新增 `scripts/rehearse_weekly_review_recovery.py`，供人工以既有非正式 weekly-review working-copy DB 與 approval projection 執行可重複的備份／還原演練。它拒絕正式 `twstock.db` 路徑、來源檔 reparse point、非空 WAL／rollback journal、正式／輸出根底下或與來源重疊的 scratch、無效 projection schema，以及 `formal_credit_authorized=true`。只有全新 scratch 根目錄可寫入；source DB、WAL、journal 與 projection 都做前後 hash 讀回。實際 Scheduler 不會被呼叫或停用，disable-first 僅在 scratch 模擬。故障注入後工具把備份還原成新檔，保留故障副本，核對 SQLite `quick_check`、週報 ID／hash／期間摘要及 projection bytes／record count。

本輪對合成 weekly history DB 與 `formal_credit_authorized=false` 空 projection 執行 focused tests **3 passed**；包含成功還原、正式 DB 路徑拒絕、非空 WAL／journal 拒絕與禁止 formal credit。新工具 mypy **1 source file clean**、兩個修改 Python 檔 `py_compile` 通過；Feature Map／QA／Runbook scoped document-control **12 features／5 link sources／0 errors**。PROJECT_SNAPSHOT 單檔核對仍列出 **27** 條既有 `output/` trial/task 外部連結越界，均非本次新增連結。這只證明 utility 的 scratch recovery 機制；未用實際 working-copy／Owner projection 做 live rehearsal，未操作 Task Scheduler，不算 backup／rollback Gate 完成，也不授 Gate credit。Windows sandbox 拒絕 scratch 內 `os.replace`，實作改為將備份還原至新的 scratch 檔，保留故障注入副本，避免覆寫任何來源。

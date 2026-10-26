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

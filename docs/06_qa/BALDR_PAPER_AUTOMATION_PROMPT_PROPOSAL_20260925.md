# BALDR Paper heartbeat prompt 修訂提案（2026-09-25）

## 狀態與來源

**等待 root 審查；尚未套用。** 唯讀檢查現有 `automation.toml`，未直接修改 TOML，也未呼叫 Codex automation 管理工具。

- automation：`paper`，`ACTIVE`，heartbeat，目標 thread `01a0b393-181a-7ef3-9ad7-2af05bc09f8b`。
- 現有日程：`FREQ=DAILY;BYHOUR=6;BYMINUTE=20;BYSECOND=0`，依 automation 的本地時間每日 06:20 執行，目前對應台北 21:20。提案保留日程、thread、名稱、狀態、model 欄位與通知設定；DST 後以實際觸發時間為準。
- TOML SHA-256：`604D336B2037246A8938034EA21B1BA194B8848A9032BB36CE2181D46D1D152E`。
- 原 prompt SHA-256：`E373D98EF075A7C11FC4B681ACCECD1524227AE7A2E4DA23B8B9EA18DF9F7081`。
- 提案 prompt 的 SHA-256 見同目錄 update request JSON，以其中精確 UTF-8 prompt bytes 為準。

原 prompt、建議 prompt、管理工具 request 與完整 rollback request 保存在 [BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json](BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json)。48 個 automation 的唯讀來源快照在 [BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json](BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json)。

## 唯一建議修改

| 原 prompt 權限 | 提案調整 |
|---|---|
| 真實失敗時可由 `gpt-5.6-luna`、`reasoning_effort=max` 的 subagent 做 bounded 診斷、最小程式修正、隔離測試及文件修改；root 審核計畫與結果後受控執行，並可分批 commit。 | 保留同一 bounded 診斷、最小相容修正、隔離測試與相關文件更新用途；明訂實作 subagent 使用 `gpt-6-luna/max` 並優先重用既有 agent，root 先審查計畫與結果；移除 stage／commit／push。prompt 不授權新增或觸發正式資料 writer、正式 evidence producer、scheduler/automation 變更、ML rebuild 或 promotion，這些仍需另行明確授權。 |

## 建議 heartbeat prompt

以下區塊是 request JSON 中 `request.prompt` 的完整內容：

```text
在本對話 thread 內，依現有 automation 本地時間每日 06:20 執行（目前對應台北時間 21:20），在 Legacy 20:45、BankTaiwan 20:50、Paper 21:00 應有工作結束後，做一次唯讀驗收：檢查實際 Windows Task Scheduler state、last result、next run、最新 terminal receipt/status、binding/capture receipt、source/output roots 與當日 timestamps。週末先依官方交易日 calendar 與 receipt 判定，不把尚未到期或休市視為失敗；只有真正 failure、blocked、missing/stale receipt、new terminal/binding/capture 或有意義 drift 才通知，狀態未變且沒有待處理 blocker 時保持安靜。

沿用本對話最新進度，先讀 repository AGENTS.md 並保護所有未提交 dirty。用同一 run 的 producer run_id、decision date、時間及 receipt hash，對照 canonical typed result ID/hash 與 consumer readback；Task Scheduler exit 0 或單看 latest pointer 不代表 readback 通過。若 run_id、日期或 receipt bytes 無法對上，記為 stale/missing blocker，不得當作正常等待；只有官方 calendar 與實際 trigger 證明該日沒有到期工作時，才按非執行日處理。

Paper preopen 驗收分別核對 root schema_version=`paper-portfolio-daily-status.v1`、獨立 isolated_scope_schema_version=`paper-portfolio-daily-isolated-scope.v1`、nested preopen_coverage.schema_version=`paper-preopen-coverage.v1`。未治理的 root/scope/coverage 或不同層 schema 混用均為 blocker；舊格式只在明確治理的 bounded compatibility contract、指定 producer、candidate-only 與完整 no-credit/隔離安全旗標全部成立時接受。保留既有 decision date、path、hash、snapshot、state、status、calendar、no-credit/no-broker 與 receipt-race gates。

目前已用隔離 synthetic tests 修正 2026-09-22 Paper receipt 的 reader/schema handoff，並驗證新 observation 的 emitted_at 取實際 append clock；這不等同新一次 Windows Scheduler producer run 或 live same-run consumer readback。最新 live receipt 若仍是 9/22 舊 run，應明確報告 post-fix operational readback 尚未建立，不得用舊 receipt 宣稱當前通過，也不得把 stale 當正常等待。

正式 producer/writer 不自動重播舊日；不碰交易、帳務或正式資料，不補 future clock，不追認 credit。若發現真實失敗，可在既有授權範圍內做 bounded 診斷、最小相容程式修正、隔離 synthetic tests 與必要文件更新；先整理 before/after、最小重現與風險供 root review，再按已授權範圍驗證。優先重用目前既有的 Luna Max agent，不另生平行 agent；不 stage、commit 或 push。

本 heartbeat 不授權新增／重跑正式資料 writer 或 evidence producer、ML full-market rebuild、promotion、刷新正式 config、或修改／觸發 Windows Task Scheduler task 與 Codex automation；這些需要另行明確授權。若執行 bounded 工程修正，實作 subagent 使用 `gpt-6-luna`、`reasoning_effort=max`，優先重用既有 agent；root 先審查修正計畫與結果，再依既有授權受控執行。所有目前 PAUSED 的 refactor、milestone、activation automations 與 Tasks 維持 PAUSED，不恢復，也不手動觸發。新 capture 不等於 matured，也不等於正式 credit。

保留既有名稱、ACTIVE 狀態、target thread、model 設定、通知設定與 local RRULE。不要因 DST 改寫排程；遇 DST 或實際執行時間疑義時讀回 automation 的實際 trigger/timezone 與 next run，不假稱全年固定台北 21:20。保持既有 TPEX heartbeat 與晨報不變；只有完成同次 terminal、binding、capture 及 consumer readback 核驗後才能宣告成功；失敗、具名 blocker、需使用者動作或有意義 drift 即通知，狀態不變時不重複通知。
```

## 保留欄位與隔離驗證

建議管理請求只變更 prompt；保留原名稱、ACTIVE 狀態、local RRULE、target thread、model 欄位和 notification policy。45 個 PAUSED automations、morning report 與 Moomoo automation 均不在此次變更範圍。

root 審查後可按 request JSON 呼叫 `automation_update`。之後以唯讀 readback 確認 `id/status/rrule/targetThreadId/name/model/prompt hash`：僅在狀態、時間表、thread、原 model 設定與 prompt hash 均符合時接受；不手動觸發 automation 驗證。若 readback 有非預期漂移，JSON `rollbackRequest` 用原 prompt 與原 schedule/status 還原；不直接編輯 TOML。

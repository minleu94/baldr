# BALDR 產品整合與排程接續驗收（2026-09-25）

## 裁決狀態

**截至 21:08 PDT 的唯讀盤點已完成；截至 2026-09-26，Paper bounded 修補已獨立接受、prompt 已套用並讀回，daily technical parse/partial-failure slice 已通過隔離回歸。** 本文件前段仍是盤點 baseline，不代表正式 production acceptance、writer 授權、ML promotion 或 scheduler gate 通過；後續工程/驗證進度見文末 current 狀態區。

本輪沿用 [R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 的工程狀態：C1 歷史 gate 已接受；C2 接受但保留具名 QA teardown baseline；C4 接受但保留 shadow-boundary baseline；R027/R028 與其他風險仍按原 owner/status 列管。沒有重跑 C1–C4。

## HEAD、dirty 與 C4 bytes 基線

- `HEAD=bec423eef1d9e9d4a32410dac96cd233304489aa`，本輪驗收期間未切換 HEAD。
- 20:41 PDT 初始 machine inventory 記錄 7,297 個 dirty/untracked entries（50 tracked、7,247 untracked）。原始路徑清冊與完整 C4 input hashes 保存於 [baseline JSON](../06_qa/BALDR_PRODUCT_INTEGRATION_BASELINE_20260925.json)。
- 最終 21:08 PDT machine inventory 有 7,305 entries（50 tracked dirty、7,255 untracked）；相對初始清冊新增 8 個路徑、0 個移除。新增路徑包括其他 owner 的 `BALDR_PRODUCT_USABILITY_20260925.md` 與本輪 7 個清冊／提案文件；其他既有 dirty paths 保留原樣，沒有清理。
- `active_task.yaml` 與 `handoff_log.md` 是初始清冊已存在的 tracked dirty paths；本輪只在確認 hash 與既有 owner 後分別 append 一筆，不覆寫其他 owner/歷史內容。
- C4 manifest `docs/06_qa/C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json` SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`；234 tests + 237 sources 共 471 inputs。於 20:58 與 21:08 PDT 逐一重驗 bytes 與 SHA-256：兩次都是 471 matched、0 drift、0 missing。
- 本輪沒有修改 471 個 C4 source/test input，沒有 stage、commit 或 push。完整 status path list 保存在 baseline JSON，而非只依賴長篇 `git status` console output。

## 截至 21:08 PDT 的 Scheduler 與 artifact readback（歷史盤點快照）

完整 21-task action/account/trigger/timezone/workdir/env/parameters/timeout/retry/overlap/state/last/next/result、task XML hashes、wrapper hashes及 25 個 artifact readback 皆在 [Scheduler 清冊](BALDR_SCHEDULER_RECONCILIATION_20260925.md) 與 [Scheduler JSON](BALDR_SCHEDULER_RECONCILIATION_20260925.json)。該收據只讀匯出，沒有啟動 task。

主要因果讀回：quick-update 04:20 的 scheduler result 是 exit 1；同名最新 status 在 05:45 被 recommendation-learning 子流程重寫，因此 run id/timestamp 不同，不能拿該 latest pointer冒充 04:20 receipt。Evidence dry-run 05:15 exit 2 且 `dry_run=true`、`writes_evidence_db=false`；Paper EOD dependency gate 06:00 blocked、query-only、沒有 source DB/file writes。Forward outcomes 是目前排程中一個既有 evidence DB writer，但本輪只讀 status/progress receipt，沒有執行 task或查詢 DB。

Formal/PIT 狀態現為過期 runtime config 的 fail-closed receipts；Direct chain blocked on capacity；ML promotion authority readback 顯示沒有建立 authorization、formal OOS=false、alpha=0。Paper portfolio 與 ML forward 的 9/25 task 結果為 `0xC000013A`，其 latest receipts 是 9/22 舊資料，沒有同次 readback。這些事項在排程報告中逐項保留，沒有手動觸發、重播、刷新 config、重訓或 promotion。

## Codex automation 現況與處置

48 個 `automation.toml` 的只讀快照見 [automation inventory JSON](../06_qa/BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json)：3 個 ACTIVE、45 個 PAUSED。沒有讀其他 Codex 設定或 secret config，沒有直接編輯 TOML。

| automation | 本輪處置 |
|---|---|
| `baldr-scheduled-evidence-morning-report` | 保留原唯讀提示、05:30 America/Los_Angeles 日程與 target thread；不改。 |
| `moomoo-200-risk-lab` | 獨立工作，本範圍外；不改。 |
| `paper`（21:08 PDT 快照） | 當時保留原 EOD 驗收目的與 bounded 診斷、最小相容修正、隔離測試及文件更新權限；提出移除 stage／commit／push、改用既有 `gpt-6-luna/max` agents 並補 same-run/schema 判讀。該快照記錄提案尚未套用；目前狀態見文末 2026-09-26 更新。 |

完整 before/after 及回復方法在 [prompt proposal](BALDR_PAPER_AUTOMATION_PROMPT_PROPOSAL_20260925.md)；完整 `automation_update` request 與原 prompt rollback request 在 [request JSON](BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json)。

## 最小 before/after 與隔離驗證

**Before：** `paper` prompt 在真實失敗時允許 `gpt-5.6-luna/max` subagent 執行 bounded 程式修正、隔離測試及文件更新，並提及分批 commit。

**After 提案：** 保留 bounded 診斷、最小相容程式修正、隔離測試與文件更新；使用 `gpt-6-luna/max` 並優先重用既有 agent，先由 root 審查計畫及結果；移除 stage／commit／push。明列 formal writer/evidence producer、ML rebuild/promotion 與 scheduler/automation 變更需另行授權。保留原名稱、ACTIVE 狀態、`FREQ=DAILY;BYHOUR=6;BYMINUTE=20;BYSECOND=0`、target thread、交易日判讀和 TPEX/morning reporter 要求。

截至 21:08 PDT 的提案快照：原 TOML SHA `604D336B2037246A8938034EA21B1BA194B8848A9032BB36CE2181D46D1D152E`、原 prompt SHA `E373D98EF075A7C11FC4B681ACCECD1524227AE7A2E4DA23B8B9EA18DF9F7081`、提案 prompt SHA `86BB652A882031D2A72517579DC00395F43F23CAB7683E0C2FD0DB71A19A7DE3`。當時尚未透過管理工具更新；後續實際套用與 readback 在 2026-09-26 current 狀態區記錄。

Windows Scheduler 21 個 action、principal、日程與重疊/retry設定沒有找到可證明需要調整的最小修復，本輪不提出 action/settings patch。已啟用的 Direct、promotion、Formal 與 Forward outcomes task 維持原狀；其 fail-closed/stale/readback 條件不能推導出新的 rebuild、writer 或 promotion 授權。

## 重現命令與產物

```powershell
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
Get-FileHash -Algorithm SHA256 docs/06_qa/C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json
Get-ScheduledTask | Where-Object { $_.TaskName -like 'baldr-*' }
Get-ScheduledTaskInfo -TaskPath '\' -TaskName 'baldr-data-update-quick-daily'
Export-ScheduledTask -TaskPath '\' -TaskName 'baldr-data-update-quick-daily'
Get-FileHash -Algorithm SHA256 <named-status-or-wrapper-path>
```

C4 471 項 input 的 path/expected bytes/hash/current matched state，Scheduler 的 21 份 XML/每個 wrapper/action/receipt，以及 automation 的 48 個完整 prompt/source hashes，都有 machine-readable 收據連結可重驗。非 Windows Task Scheduler 的 Codex automation 只從 `C:\Users\archi\.codex\automations\*\automation.toml` 讀取。截至 21:08 PDT inventory checkpoint，沒有資料庫查詢、正式 writer、交易、資料更新、UI 啟動或測試重跑；後續隔離 P1 pytest 與 static 結果列在文末，不改寫當時盤點邊界。

## 本輪檔案與接手狀態

- 新增驗收報告、Scheduler reconciliation 報告及 JSON、automation inventory JSON、baseline JSON、prompt proposal 與 update request JSON。
- `docs/agents/shared_state/active_task.yaml` 以獨立 `baldr_product_integration_reconciliation_20260925` 項目追加此 lane；`handoff_log.md` 追加本輪收據，未覆寫既有 owner/歷史段落。
- Paper schema/clock 切片修改兩個 production modules、兩個相關測試與原樣 frozen fixture；隔離驗證未讀寫正式資料或 DB。21:08 inventory 當時 Windows Task Scheduler 設定與 automation TOML 都未改；後續只有 `paper` prompt 經管理工具更新，見 current 狀態區。未 stage、commit、push。
- 截至 21:08 PDT，下一步為 root 審查 prompt proposal/management request；該句是盤點當下的歷史狀態，後續 bounded code/test 工作已另列如下。

## 後續工程與驗證續接（2026-09-25）

這些工作發生於前述 21:08 PDT inventory snapshot 之後。它們不代表 live Scheduler post-fix readback，也不觸發 Windows task、Codex automation、formal writer、Paper DB、ML rebuild 或 promotion。

### Paper preopen/schema 與自然 append clock

- Owner：`/root/c1_final_qa`。修正 Paper receipt reader 與 derived-shadow consumer gate 的 root schema / isolated scope schema 分層驗證；`paper-portfolio-daily-status.v1`、`paper-portfolio-daily-isolated-scope.v1` 和 nested `paper-preopen-coverage.v1` 獨立驗證。bounded legacy reader 另拒絕 scope 欄位混入；直接 reader negative test 覆蓋該案例。
- `record_and_mature` 對新 observation 捕獲實際 append `emitted_at`；重跑保留舊 row/hash/clock，不回填歷史時間、不追認 credit，forward late rejection 保持原狀。
- 原 2026-09-22 receipt fixture 維持精確 5822 bytes/hash，未修改來源或讀取其 DB。兩個受影響 suites 最新合併結果 `63 passed in 2.62s`，log SHA-256 `D1EF07B8D61587C03D95D1C52BE193EAFA1F220AC5AEF8B0CB4DE890A7EC7E4A`，路徑見 Scheduler reconciliation report。這是隔離程式契約證據；post-fix 同次 live producer/consumer readback 仍待既有排程自然產生。
- 截至本次 21:08 inventory 時，`paper` automation prompt proposal 已更新為保留既有 bounded 修復、測試、文件用途，只去除 stage／commit／push，並加強 same-run receipt / typed-result readback 和 schema gates；當時 request 尚待 root 管理工具套用。後續 readback 結果見 2026-09-26 current 狀態區；TOML 由管理工具更新，未由本 agent 直接編輯。

### 平行 owner 與 root integration/native

| Slice | Owner | 本輪狀態 |
|---|---|---|
| Paper schema／clock／排程清冊 | `/root/c1_final_qa` | 兩 suite 63 passed；cross/root 已獨立接受 bounded contract slice；prompt 已套用並讀回。自然排程 same-run receipt 尚待。 |
| IndustryMapper 與 native fixture | `/root/c1_capture` | 平行實作／驗收進行中；本報告不替代其專屬證據。 |
| Calibration learner | `/root/c1_cross_boundary_review` | 平行切片進行中；本報告不替代其專屬證據。 |
| 整合與 native readback | `/root` | 彙整三切片、審查工程計畫與結果、處理 automation 管理請求；不得由本報告推定已完成。 |

本續接只依賴隔離 TEMP／synthetic 驗證。Windows Scheduler action/settings 與正式資料保持未改；`paper` automation prompt 僅由管理工具按核准 request 更新並讀回。未 stage、commit、push。

## 截至 2026-09-26 的狀態更新（歷史記錄）

### Paper 修補與 automation readback

- Paper root/scope/nested coverage schema 與 append-clock slice 已完成獨立複審，無 P1/P2；兩個受影響 suites `63 passed / 2.54s`。cross/root 接受的是隔離程式契約，不是下一次 Paper 排程的 live pass。原 2026-09-22 fixture 保持 5822 bytes，SHA-256 `8972FC031F95A0FBD3D52052C3047D68DB93210DA3C846A7E4B9A0F7E29C740C`。
- Root 使用 Codex automation 管理工具套用 `paper` prompt，並完成唯讀 readback。狀態 `APPLIED_AND_READBACK_VERIFIED`；prompt SHA-256 `86BB652A882031D2A72517579DC00395F43F23CAB7683E0C2FD0DB71A19A7DE3`，TOML after SHA-256 `9D7CADB0A63D9B87264A2BAD11B85C86321E329456CB6FB1EB2C5300AD468DF9`。驗證只改 `prompt` 與 `updated_at`，ACTIVE、原 RRULE、target thread、notification null 保留；尚未有套用後的正常 automation run。套用前 TOML 備份位於 TEMP，SHA-256 `604D336B2037246A8938034EA21B1BA194B8848A9032BB36CE2181D46D1D152E`。
- Scheduler task/XML/settings 未修改或觸發。Paper 下一次有效 run 仍須依 prompt 同次 typed result、root/scope/nested schemas、date/path/hash/snapshot/state/no-credit gates 完整 readback，方可宣告成功。

### Daily technical parse 與 partial-failure diagnosis

- Owner `/root/c1_final_qa`；細節與完整重跑命令見 [technical parse QA 報告](BALDR_DAILY_TECHNICAL_PARSE_DIAGNOSTIC_QA_20260925.md)。SQLite synthetic integration 證明逗號格式買賣價在既有 alias guard 前先經 canonical Decimal parser；stale/nonfinite 輸入被拒絕且不讀 CSV fallback。quick runner 對部分成功保留成功數、完整失敗代號與分段錯誤碼，不再把部分成功誤報為零更新。
- 四受影響 suites `141 passed / 9.10s / exit 0`；pytest log `C:\Users\archi\AppData\Local\Temp\tp_final_f7f67a47\pytest.log` SHA-256 `0CBD09AA54F3BE715914B557AA7C21FA2BCF0E33EB009B6AD2771D832BC0C0E1`。changed Python 五檔 `py_compile` exit 0；兩個 production files scoped mypy `2 files / 0 issues`；`git diff --check` exit 0。隔離測試未執行 quick-update Scheduler 或正式 DB writer。
- 該切片驗證的是來源轉換與 runner 分類契約，不代表當日全市場資料完整、正式資料已更新，亦不構成排程自然 readback。

### Backtest Decimal 保存獨立複審

- 正在唯讀追蹤 capture 的 Decimal serializer 修補。已確認 UI portfolio save 會把 execution result 的 `equity_curve`／`trades` 直接交 `ResearchRunService.save_run`，再由 `DataFrame.to_parquet` 寫 staging bytes；`ResearchRunRepository._transition_portfolio_result_state` 約第 561 行與 `mark_portfolio_result_failed` 約第 663 行另以 `canonical_json(expected_data_manifest)` 建 CAS predicate。serializer normalization 已在 `_dto_to_row`，但仍須核實傳入 CAS 的 expected manifest 是否也正規化。
- 本項發現已回報 owner；不由此文檔 owner 修改 serializer/repository。完整 UI save/readback、Decimal finite、重試 bytes 相同、舊讀回的驗收仍待 capture 收口與獨立複審。

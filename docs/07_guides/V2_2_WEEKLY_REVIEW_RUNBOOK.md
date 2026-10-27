# V2.2 每週 Evidence Review Runbook

> 日期：2026-07-12
> 用途：以真實時間建立 V2.2 的三週人工 weekly review history；本文件不是 scheduler 核准，也不授權對正式 DB 寫入。

## 1. 開始前的安全邊界

- 本文件是 2026-07-12 的操作程序，不是目前進度權威。當日較早的[工程 readiness 快照](../09_archive/V2_2_ENGINEERING_READINESS_2026_07_12.md)記錄 weekly `0/3`；較晚的 [Week 1 QA](../09_archive/V2_2_WEEK1_REVIEW_2026_07_12.md) 已保存 `1/3 waiting_for_time`。兩份歷史證據保留各自時點，本指南不沿用舊進度數字。最新 Windows weekly collection 回讀見 [10/09 排程修正 QA](../06_qa/BALDR_SCHEDULE_REMEDIATION_20261009.md)：10/04 core 為 `pending_human_review`；這是待人工判讀的 collection，不等同三週人工 review history 或 formal closeout。
- 未取得對應週期的 append-only review receipt 前，不推算 Week 2／Week 3 或目前累積數；`production_scheduler_allowed=false` 與 formal closeout 條件仍須依 Snapshot 及具名最新 QA 判讀。
- 此流程不產生交易建議、不串 broker、不自動交易、不自動套用 lifecycle action。
- `--save-history` 與 `--confirm-action-items` 只能在明確選定、可回溯且核准作為工作副本的 working-copy DB 使用；這裡的副本核准是環境／路徑核可，不代表本週 weekly history 已經 Owner approval。CLI 會 canonicalize 實際 `--db-path`，並同時比對 configured、環境 `DATA_ROOT` 與預設正式 root；因此 `--data-root` 不能使正式 DB 變成可接受路徑。production-like DB 一律拒絕，沒有 `--allow-production-like-db` 繞過旗標；正式 DB、production-like DB 與 scheduler write-mode 均不在本 runbook 的授權範圍。
- replay、fixture、單次 smoke、raw scheduled report 或手動補表不計入三週 Gate。每列只記錄該週實際取得的證據。

## 2. 週日 Sidecar Collection（不屬於人工 weekly review）

- Windows Task Scheduler 的 `baldr-v2-2-weekly-collection` 於每週日 18:00 執行 `run_v2_2_weekly_collection.cmd`。它只執行 collection CLI，將來源的週期資料保存為 sidecar record，結果只能是 `pending_human_review` 或 `collection_failed`。
- `pending_human_review` 只代表資料已收集、等待人工判讀；它**不是** manual review、不代表 Gate 通過、不會確認 action item，也不會寫入或補造 weekly history。此 task 不帶 `--save-history` 或 `--confirm-action-items`。
- 此 task 不改正式 source DB、不啟用 production scheduler，且 `production_scheduler_allowed=false` 維持不變。真實三週人工 review 與 append-only history 仍必須依本 runbook 的後續章節，由人工在隔離的 working-copy DB 完成。
- 註冊前可執行 `scripts\scheduled\register_baldr_scheduled_tasks.cmd dryrun` 檢視排程；`weekly-register` 只建立或取代此週日 task，不建立、取代或啟用任何既有每日 task。查核使用 `schtasks /Query /TN baldr-v2-2-weekly-collection /V /FO LIST`。
- 回復此收集 task 時，只能在 Windows Task Scheduler 停用，或執行 `scripts\scheduled\unregister_baldr_scheduled_tasks.cmd weekly-unregister`。禁止自動刪除 sidecar SQLite table；既有 record 與錯誤記錄保留供人工診斷。

歷史補充：`register-all` 對應當時 12 個每日 task 與週日 collection task 的 aggregate 模板，不是目前排程全集；不得依這段舊程序重建全部 task。若只需建立或更新週日 collection task，先依[排程操作指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)核對現行清單及既有設定，再使用上述 `weekly-register` 受控流程。註冊模式會先做 wrapper-file preflight，缺檔時不會呼叫 schtasks。

## 3. 每週固定操作順序

1. 確認本週觀察期間、reviewer、正式 source DB 路徑與 working-copy DB 路徑。先用既有 working-copy smoke 的 copy/guard 建立隔離副本；它會拒絕 source 與 copy 為同一檔案、拒絕 production DB 作為 copy target，且只在副本執行 confirm smoke：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_evidence_pipeline_working_copy.py --source-db-path <approved-source-db> --working-copy-db-path <working-copy-db> --decision-date <YYYY-MM-DD> --repeat 2 --keep-working-copy --json-output
```

若 working-copy 已存在，工具不覆蓋它；先記錄既有副本來源與 hash，再交由人工決定是否另建新的隔離副本。此步驟不啟用 scheduler，也不對 source DB 寫入。
2. 讀取當週 freshness、source coverage、scheduled dry-run / manual dry-run 與 Evidence Review dashboard。記錄 warning、blocking gap、degraded reason 與資料品質。

若要在隔離工作區檢查既有正式推薦快照，可用受控 replay 將來源與輸出根分開。`--recommendation-source-root` 只讀取 canonical recommendation、freshness 與相關來源；`--output-root` 和 `--status-path` 必須指向與來源根完全分離的 scratch。`--db-path` 使用上述 working-copy DB，`--data-root` 使用 working-copy 資料根。受控 replay 不會改寫來源，也不構成人工 review、scheduler approval 或 Gate credit：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_scheduled_evidence_pipeline_dry_run.py --dry-run --bind-scheduled-recommendation --validation-decision-date <YYYY-MM-DD> --recommendation-source-root <canonical-output-root> --output-root <isolated-scratch-root> --status-path <isolated-scratch-root>\scheduled-replay\latest_status.json --data-root <working-copy-data-root> --db-path <working-copy-db>
```

來源與輸出根重疊時工具會拒絕受控 replay。不要複製或編輯 `latest_status.json` 來改變 `output_root` 身分；需保留來源原 bytes、status hash 及 replay 收據。

受控 replay 不會把 scratch 中找不到 Paper snapshot/status 解讀為正式 Paper 帳戶缺件。若已有明確綁定、唯讀的 Paper state，另傳 `--paper-evidence-source-root <paper-source-root>`；state/status 由該根讀取，replay 產物仍留在 scratch。若未提供，收據會標成 `not_configured_for_controlled_replay`，代表本次沒有檢查 Paper 輸入，不代表 Gate 通過。不得用複製到 scratch 的資料冒充已綁定來源。
3. 先產生唯讀週報；不得帶 `--save-history` 或 `--confirm-action-items`：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --db-path <working-copy-db> --plan-action-items --json-output
```

4. 檢查輸出：`write_performed=false`、`production_scheduler_allowed=false`，以及每個 manual lifecycle candidate 的 `apply_action=false`。不符合任一條件時，停止並在本週紀錄填入 follow-up；不寫 history。
5. 若本週有可覆核的 collection candidate，先在 Update 的 weekly collection 複核流程中逐筆作出 `reviewed`／`dismissed`／`follow_up` 處置，產生新的 candidate-only decision artifact。記錄 artifact 路徑與 SHA-256；姓名與角色由處置者自我聲明，處置只表示候選已被判讀，不是 weekly history approval、Gate 接受或 scheduler 授權。若沒有合格 candidate artifact，記錄原因並依本週紀錄格式繼續，不得捏造決定。
6. 將 weekly review 僅保存至明選的非正式 working-copy DB；此步只保存待核准 history，不執行 Owner approval 或確認 action items。若有 candidate artifact，可在產品 Evidence Review →「覆盤歷史」選取同一 working-copy DB，填入本週開始／結束日，按「保存候選決定至週報 history…」，並選擇 candidate artifact 與它綁定的 sidecar。確認視窗會列出所有路徑與週期；保存前會重建報告、再次驗證 artifact／sidecar／manifest binding，保存後回報並讀回 `review_id`／`review_hash`。再重新整理列表並核對同一 hash。若使用 CLI，candidate bridge 命令如下：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --db-path <working-copy-db> --save-history --json-output
```

若不用 UI，可另明確指定產生它的 sidecar；當 artifact 綁定 runbook manifest 時，也要指定已核可的 receipt root：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --db-path <working-copy-db> --save-history --candidate-review-artifact <candidate-artifact.json> --candidate-review-sidecar-path <source-sidecar.sqlite> --json-output
```

若 artifact 綁定 runbook manifest，另加 `--candidate-review-authorized-receipt-root <trusted-receipt-root>`；沒有 manifest binding 時省略該參數。若 candidate artifact 的 sidecar SHA、collection ID／狀態、期間、source hash、runbook manifest binding 或報表期間已變動／不相符，工具必須在寫入前拒絕。沒有 candidate artifact 時不得虛構；記錄沒有合格候選的原因，並省略所有 `--candidate-review-*` 參數。History payload 需保留原 candidate-only 安全旗標；保存 history 不會將候選處置升格為 Gate credit、Owner approval 或 scheduler permission。Candidate bridge 不能與 `--confirm-action-items` 同次執行。

7. 以唯讀方式讀回並記錄該筆 `review_id`／`review_hash`／status；確認 candidate SHA、collection、決定、自我聲明的 Owner／Reviewer 身分與理由均對應本週處置。若有 candidate 卻找不到唯一且相符的 saved history，停止，不核准。`--list-history` 在 config 初始化前只以 `--db-path` 或 `--data-root` 做純路徑解析；對缺 DB 或缺 history table 只輸出 diagnostics，不建立 DB parent、log directory、schema 或 index：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --db-path <working-copy-db> --list-history --json-output
```

8. 在產品 Evidence Review 的「覆盤歷史」選取同一份 working-copy DB，核對相同 `review_id`／`review_hash` 與 candidate disposition，再由具名 Owner 對**這一筆已保存的 hash**作 append-only approval。核准紀錄須另外讀回並記錄；candidate artifact 自身的 `candidate_only=true`、`formal_credit_authorized=false` 與 `production_scheduler_allowed=false` 不得改寫。Owner approval 不代表 Gate 2／正式排程已通過。

9. Owner approval 讀回成功後，才依本週判讀安排 Action Items。需要確認時，以相同 working-copy DB 執行下列命令；不要同時重新保存另一個週期 history hash：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --db-path <working-copy-db> --confirm-action-items --action-owner <owner> --json-output
```

處置歷程另依下方「Action Item lifecycle」流程追加到獨立投影，並記錄 `reviewed`／`dismissed`／`follow_up` 與下一步。結論只描述 evidence、quality、warning、來源與後續工作，不得寫成買賣、倉位或 lifecycle 指令。

若在產品 Evidence Review 內核對，於「覆盤歷史」按「選擇 working-copy DB…」並選同一個既有副本；UI 會唯讀載入 history，Owner 覆核時也對同檔重新核對 ID／hash。PERSONAL／LEGACY_READ_ONLY 路由不接受自訂 DB；Owner projection 仍須獨立設定，核准不寫回 working-copy。

在「覆盤歷史」頁可另處理 Action Item lifecycle：先按「選擇 working-copy DB…」明選同一份既有、非正式副本，再選「Action Item 投影檔」的新／既有 JSON 路徑；僅兩者都通過路徑與來源檢查後，「檢視／更新 Action Items…」才會啟用。來源 DB 必須已 checkpoint；若存在非空 WAL／rollback journal，先由原工作流程安全 checkpoint 後再選取，且操作期間不得有其他程序寫入該副本。畫面讀出該副本的 Action Items、來源 Item／review ID、review hash、期間及完整處置歷程，可追加 `open → reviewed / dismissed / follow_up`、`reviewed / dismissed → follow_up`，以及 `follow_up → reviewed / dismissed`。每次須填寫處置者姓名、角色與說明；姓名／角色為自我聲明。事件以 hash chain 追加在獨立投影中，來源 SQLite 保持唯讀，且不可與 Owner approval projection 共用。換回預設資料來源會停用此操作；要續用，需重新明選 working-copy 與同一個投影檔。投影只記錄人工追蹤，不核准週報、不改 Gate／排程或策略，`formal_credit_authorized=false`、`downstream_eligibility=none`。若來源 Action Item 已變更或事件鏈損毀，操作會拒絕並要求以正確 working-copy／投影檔核對，不可手工改 hash。

10. 記錄下一步與本週 backup / rollback / recovery 演練狀態。三週都完成後，仍須人工彙整 scheduler approval package；不可自動進入 formal closeout。

### 隔離 recovery rehearsal（工程演練，不計 weekly Gate）

若已具備一份既有、非正式且 checkpoint 完整的 weekly-review working-copy DB 與核准 projection，可用以下工具在一個全新 scratch 目錄演練備份、故障注入與還原：

```powershell
.\.venv\Scripts\python.exe scripts\rehearse_weekly_review_recovery.py --source-db-path <existing-working-copy-db> --source-projection-path <existing-approval-projection.json> --scratch-root <new-scratch-run-directory>
```

工具只讀取兩個來源檔；若 DB 有非空 WAL／rollback journal、來源不是一般檔案、projection schema／`formal_credit_authorized` 不合約，或來源 DB 是正式 `twstock.db`，會 fail closed。Scratch 必須是新路徑，且位於設定的 `DATA_ROOT`／`OUTPUT_ROOT` 之外。工具會先在 scratch 寫入模擬停用標記，再建立 DB／projection 備份、在各自 scratch working copy 注入故障、將備份還原為新檔，並核對 SHA-256、SQLite `quick_check`、weekly history IDs/hashes 與 projection record count；故障副本保留供稽核。它不呼叫 Task Scheduler、不改 scheduler task、不覆寫來源或舊 scratch。

收據的 `passed=true` 只代表這次隔離副本的備份／還原與來源前後 hash 檢查通過。`disable_first.verified_in_scratch_simulation` 是 scratch 模擬，不代表正式 task 已停用；它也不代表真實 Owner review、三週 history、三操作日、production disable／rollback 或 scheduler approval 已通過，不能給 Gate 2 credit。若要測正式的停用優先操作，另依排程操作指南取得對應人工核准並由操作人員在 Task Scheduler 實際執行。

## 4. 固定三週人工紀錄格式

下表必須完整填寫三列。`待執行` 不是通過；若未保存 history，`--save-history` 欄必須填入拒絕原因而非虛構 review ID。

| 週次 | 週期日期 / review timestamp | 資料 freshness 與 quality | dry-run 狀態 | warnings / blocking gaps | reviewed / dismissed / follow-up | action owner | working-copy DB path 與隔離確認 | `--save-history` 結果 | backup / rollback / recovery | 下一步 |
|---|---|---|---|---|---|---|---|---|---|---|
| Week 1 | `<YYYY-MM-DD>.. <YYYY-MM-DD> / <timestamp>` | `<fresh / degraded / reason>` | `<dry_run / confirm / scheduler_allowed=false>` | `<逐項列出或 none>` | `<人工結論>` | `<姓名或角色>` | `<path>; 與正式 DB 不同=true>` | `<review_id/hash/status 或未保存原因>` | `<狀態與證據>` | `<可驗證下一步>` |
| Week 2 | `<YYYY-MM-DD>.. <YYYY-MM-DD> / <timestamp>` | `<fresh / degraded / reason>` | `<dry_run / confirm / scheduler_allowed=false>` | `<逐項列出或 none>` | `<人工結論>` | `<姓名或角色>` | `<path>; 與正式 DB 不同=true>` | `<review_id/hash/status 或未保存原因>` | `<狀態與證據>` | `<可驗證下一步>` |
| Week 3 | `<YYYY-MM-DD>.. <YYYY-MM-DD> / <timestamp>` | `<fresh / degraded / reason>` | `<dry_run / confirm / scheduler_allowed=false>` | `<逐項列出或 none>` | `<人工結論>` | `<姓名或角色>` | `<path>; 與正式 DB 不同=true>` | `<review_id/hash/status 或未保存原因>` | `<狀態與證據>` | `<可驗證下一步>` |

## 5. 三週完成後的判讀

只有三週都具備真實時間、人工 review 與 append-only history 時，weekly history 才能從 `0/3 waiting_for_time` 進入人工審查。即使三週齊備，下列項目未完成前仍不能建立 formal closeout：

- scheduler approval 未由授權 owner 明確核准；
- backup、rollback、recovery 演練未完成或無可追溯記錄；
- 任一週缺 owner、`--save-history` 結果、warnings 判讀或下一步；
- 將 raw report、replay、fixture 或人工補表當作真實週期。

在所有條件完成並獲人工核准前，維持 `production_scheduler_allowed=false`；production scheduler 若日後獲准，也只能保存 evidence，不得自動交易或套用 lifecycle action。

## 6. 排錯與停止條件

| 情況 | 必須動作 |
|---|---|
| `--help` 沒有顯示 `--save-history`、`--list-history`、`--action-owner`、`--candidate-review-artifact`、`--candidate-review-sidecar-path` 或 `--candidate-review-authorized-receipt-root` | 停止，不執行保存；確認目前程式碼與虛擬環境。 |
| working-copy DB 路徑等於或指向正式 DB | 停止，不使用 `--save-history` / `--confirm-action-items`；建立經核准的隔離副本後重做唯讀檢查。 |
| 測試 production-like guard | 僅在 QA 暫存根目錄執行 `--data-root <qa-root> --db-path <qa-root>/sqlite/twstock.db --save-history`，預期 exit code `2` 且不建立 DB；不得以實際正式 DB 或任何 allow 旗標測試。 |
| dry-run 輸出出現 `write_performed=true`、scheduler allowed 或 lifecycle `apply_action=true` | 停止，保留輸出作診斷；不得把該週列為通過。 |
| freshness / source coverage 有 blocking gap | 填入 follow-up 與 owner；不得以手動編輯或舊 report 補足。 |
| 無法寫入或 list history 找不到剛保存的記錄 | 填入未保存原因與 recovery follow-up；此週不計入三週 Gate。 |
| weekly sidecar collection 失敗或需停止 | 保留 sidecar error record 與 task/log 證據；停用或 `weekly-unregister` task。不得自動 drop sidecar table，亦不得把既有 `pending_human_review` 當成已完成 review。 |

## 更新記錄

- 2026-07-12：建立 V2.2 固定三週人工記錄格式與 working-copy weekly review 操作順序；明確保留 scheduler 未核准與不可 formal closeout 邊界。
- 2026-07-12：補上 working-copy copy/guard、production-like 強制拒絕與 combined confirm/history snapshot trace；`--list-history` 缺 DB / table 時只回 diagnostics，不建立 SQLite 物件。re-review 補強 `--data-root` 不可繞過 canonical production DB guard。
- 2026-07-12：新增週日 sidecar collection 的操作與 rollback 邊界；collection 僅保存 `pending_human_review`，不屬於人工 review、不寫 weekly history，且不改 `production_scheduler_allowed=false`。
- 2026-10-27：修正 candidate disposition、working-copy history 與 Owner approval 的先後順序；先綁定並保存待核准 history，再核准讀回的精確 review hash，最後處理 Action Items。保留 candidate-only、Gate 與 production scheduler 安全旗標；三週真實 cadence 條件不變。

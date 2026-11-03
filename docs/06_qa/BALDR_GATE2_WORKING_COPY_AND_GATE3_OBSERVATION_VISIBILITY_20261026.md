# Gate 2 working-copy 接線與 Gate 3 現況觀測可見性 QA

## 2026-11-02 Gate 2 三個操作日 evidence event 唯讀盤點

以 evidence-only read-only access 分別查詢 `decision_date` 2026-10-29、2026-10-30、2026-11-02 的 `recommendation_included`。查詢均回傳 `writes_allowed=false`、`outcomes_count=0`、無 diagnostics。三個不同操作日各有真實 EOD research event，`event_date`／`decision_date`／`available_date` 同日、`data_quality=observed`、`temporal_status=verified`、`source_availability_preserved=true`；皆為 `research_only=true`、`natural_authority=false`，且 event 的 `source_trace.run_id` 為空。

| 操作日 | 收錄事件 | result／source snapshot identity | Event IDs（symbol） |
|---|---:|---|---|
| 2026-10-29 | 1 | `rec_8b6ec436d61241209445c2fe6148b59a` | `evt_de4016a796e04713aad06b2aee0721d0`（1201） |
| 2026-10-30 | 2 | `rec_3eac8902caae4328bd88ec5f7e8fd1dd` | `evt_08ef7a0d729f41bebe2442ebe32b5191`（1526）；`evt_9b41ab21096e4957b3ee39b1e2f88658`（1201） |
| 2026-11-02 | 5 | `rec_ab35aaa1276841879f706f9d4e10486a` | `evt_4a965fd662fc436c97eb18051b32db59`（1456）；`evt_5b89d73e8bc84519b5b1778e11bf1a4b`（1235）；`evt_af58f9e595be49bf966a5092ee7dae46`（1416）；`evt_c283300c9c7347e58b9e5b17b5e248f6`（1232）；`evt_f05733a6b7e241eda73326ecf0b9c6fb`（1528） |

**Gate 2 判讀：**三個操作日的實際 evidence event 已可定位；這只確認事件存在，不等於 Gate 2 的操作日證據包已完成。因 `run_id` 為空，排程 run identity 尚未由這些 event rows 綁定；也沒有 forward outcome。仍須依 Runbook 補齊每日期所需的 freshness、coverage、scheduled／manual dry-run、weekly report、write-safety、warning／blocking、具名覆核及 recovery 等材料，並由 Owner 審閱。上述事件為 research-only，不授正式來源、PIT、financial 或 Gate credit。

## 2026-10-27 Action Item lifecycle append-only 投影

Evidence Review「覆盤歷史」新增 Action Item 人工追蹤流程。操作者必須先明選通過路徑守衛的非正式 working-copy DB，再選獨立 JSON 投影檔；兩個條件缺一時，操作按鈕維持停用。服務僅接受 checkpoint 完成且無非空 WAL／rollback journal 的 DB，以 SQLite `mode=ro`／`query_only` 讀取 action row 與 review hash／期間，並比較讀取前後主檔與 WAL／journal 狀態以拒絕讀取期間的變動；操作時不得另有工作程序寫入該副本。狀態事件綁定 working-copy path identity 及完整 action payload hash；事件由跨程序鎖序列化，重讀來源並驗證轉態與 hash chain 後，以原子替換追加。來源列改變／消失、投影損毀、來源 DB 不同、無時區時間或不允許轉態會 fail closed。來源 DB、週報 history、Owner approval projection、正式資料與 scheduler 均不由此流程寫入。

最終受控驗證結果（已包含 SQLite 讀取期間 WAL／journal 競態檢查及回歸測試）：

| 檢查 | 結果 |
|---|---|
| Action Item lifecycle 與 Evidence Review 狀態投影 focused tests | 15 passed |
| 必要 Update UI regression | 97 passed |
| Update validator | 25 passed／0 failed／4 skipped |
| 全域 mypy | 1,157 source files，無錯誤 |
| 6 個修改 Python 檔 `py_compile` | 通過 |
| scoped document-control（Feature Map、架構、資料 runtime、Gate 2 QA、Runbook） | 12 features／5 link sources／0 errors |
| APPLICATION_MANUAL scoped document-control | 2 條既有 `../../output/trial/.../TRIAL_GUIDE.md` 引用因 output junction WinError 5 無法讀取；本次 Action Item 章節連結為 Runbook 內部連結 |
| Windows Job | exit 0；8 GiB memory／12-process／kill-on-close 限制讀回；啟動前可用 RAM 26.3 GiB；Job 自然歸零、剩餘 PID 0、handles 與 mutex 關閉、無強制清理 |

獨立 Luna 靜態複核發現 SQLite sidecar 可能在讀取期間變動；已加入讀前／讀後 stamp 比對與 regression test，最終 focused 組含新測試共 15 passed。Windows sandbox 預設 pytest temp 會拒絕 `os.replace`，故使用工作區 `.tmp` 下的唯一短路徑；Update validator 日誌以 `BALDR_UPDATE_TAB_QA_LOG_DIR` 導向任務隔離 scratch，未寫入 repo `output/` junction。最終批次只在一個有界 Job 內序列執行。

最終受控 Job receipt：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\industry-theme-qa\owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433\single_owned_qa_8314137f6ace4b2e973a6def5ec7eee5\receipt.json`；SHA-256 `303c00e5a2b3933bbd32b4e4e21987219924b26dbbbc4778c66daedca7eac871`。原始測試、validator、mypy、compile 與 document-control 輸出在同目錄的 `action_item_final_validation\20261026T201521Z\`。

此工程只讓 Action Item 的人工後續狀態可追蹤；本輪沒有對真實週報 Action Item 寫入事件，未執行 Owner 原生 GUI UAT，也未完成真實三週／三操作日 cadence。`formal_credit_authorized=false`、`production_scheduler_allowed=false`；Gate 2、Gate 3、Gate 7／ML 資格不變。Owner 姓名／角色只作自我聲明，投影不驗登入身份。QA 屬合成 working-copy fixture，不算真實週期 Gate evidence。

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

### 2026-10-26 Gate 2 具名週收集覆核決定artifact

更新頁在唯讀週 collection 明細中新增「記錄具名覆核決定…」。操作者選一筆仍待審且可覆核的候選，填入實際 Owner／Reviewer 姓名、角色、決定（`reviewed`／`dismissed`／`follow_up`）及理由；視窗同時展示 coverage 數字、品質發現、最多五個完整性例子與尚未核驗的收據 hash。若要檢查收據內容，先取消覆核視窗，回明細核驗／預覽，再重新開啟覆核。寫入前重新建立 packet 並比對 sidecar SHA 與完整候選內容；候選已變動、已非 pending、不可覆核、已有決定或輸出檔存在都 fail closed。artifact 明示 candidate-only、`gate_credit_status=pending_human_review` 及所有正式寫入／授權旗標為 false；exclusive create 不覆寫現有檔案。

這是實際可保存的人工處置，不是登入認證或 Gate approval。它只寫新 JSON artifact，不寫 sidecar、weekly history、approval projection、正式 DB 或 scheduler。`reviewed` 只表示操作者檢視該筆候選；品質缺口不會因這個標記消失。既有 Evidence Operations history approval 是不同輸入與 writer。以下為本次新增實作與驗收收據；未執行 Owner UI UAT 時，不宣稱真實 Owner 已完成覆核。

| 驗證 | 結果 |
|---|---|
| `tests/test_evidence_weekly_review_decision.py` | 13 passed |
| 必要 `tests/test_ui_qt_update_view_workbench.py` | 96 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped；報告寫至隔離 `.tmp_weekly_review_decision_20261026/update_tab_qa/` |
| 全域 mypy | 1,154 source files clean |
| 修改 Python 檔 `py_compile` | 4 個檔案通過 |
| Feature Map／scoped document-control | 12 features／5 link sources／0 errors |
| `git diff --check` | 通過 |

受控 Windows Job receipt SHA-256：`aaf1be2916754bac6b1064f6f63a7da5cab90a524bc1bbc70a8809264a672392`；exit 0、kill-on-close 與 8 GiB／12-process 上限讀回成功、剩餘 PID 0、無強制清理。另一次將 Snapshot 與 Manual 納入的廣域 document check 受到既有 `output/` junction 外部 trial/task 連結的 sandbox `WinError 5` 阻擋；上述本次功能文件 scoped check 通過。此次未執行原生 GUI 或真實 Owner UAT，故沒有實際人工決定 artifact，也不授 Gate 2 credit。

### 週 collection 候選從更新頁匯出

更新頁「檢視週收集明細（唯讀）」現可將目前待審候選匯出成 JSON，供 Owner／Reviewer 檢視。匯出前會重新唯讀 sidecar；寫檔使用新檔建立，不覆寫既有封包或來源 sidecar。packet 仍是 `candidate_only`，未填人工決定，不寫 weekly history／approval projection，也不授 Gate credit。第一次受控 UI 驗證發現匯出按鈕缺少 `QFileDialog` import，修正後通過；後續新增正式旗標 fail-closed 契約時，UI 測試 fixture 一度缺 `approved_projection_emitted=false`，補齊 fixture 後以最後一輪完整收據驗收。

| 驗證 | 結果 |
|---|---|
| `tests/test_evidence_weekly_approval_input.py` | 8 passed |
| 必要 `tests/test_ui_qt_update_view_workbench.py` | 95 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped |
| 全域 mypy | 1,153 source files clean |
| 修改 Python 檔 `py_compile` | 4 個檔案通過 |
| Feature Map／QA 文件 scoped document check | 12 features；Gate 2 QA 文件與 QA README 連結無錯 |
| Owned Windows Job | exit 0；kill-on-close、8 GiB／12-process 上限讀回成功；剩餘 PID 0；無強制清理 |

最後一輪受控驗證 receipt SHA-256：`41713c786e9ce5862ff68f7b798306123e8743312c3b0eb9dbb43063348344a8`。Gate 2 QA 文件與 QA README scoped document-control check：12 features／2 link sources／0 errors，receipt SHA-256 `c45a8cdd84bf60a98c7ccd44021fb82e24d19cae0d3aa45a41e03532ddff5a36`。另一次將 Snapshot／Manual 一併納入的廣域 link check 被既有 `output/` junction 29 個 `WinError 5` 外部連結限制擋下；錯誤只落在舊 trial／task 連結，Gate 2 QA 文件及 README 本身連結無錯。`git diff --check` 通過。另驗證 sidecar 在預覽後若已無待審候選，UI 不匯出過期 packet。這只改善候選封包交接，尚未建立人工 review writer 或跨入 Owner approval/history；原 Gate 2 待辦及資格邊界不變。

## 2026-10-26 Gate 2 Runbook evidence checklist

每筆週收集候選新增 11 個 Runbook evidence roles：working-copy smoke、freshness、coverage、scheduled／manual dry-run、Evidence Review dashboard、weekly report、write-safety assertions、warnings／blocking gaps、review identity/history、backup／rollback／recovery。Packet 與 Update 明細將其分為 `missing`、`partial`、`unverified`、`verified`；collection sidecar 的 coverage 不會被當成已核驗附件，已有 quality findings 也只算部分資訊。`runbook_evidence.status` 與舊 `packet_status` 分開：`ready_for_human_review` 仍只表示候選可開始人工檢視，明確不等同 Runbook completeness 或 Gate 2 readiness。

`scripts/build_weekly_runbook_manifest.py` 可為同一 collection／期間的收據建立獨立 manifest，附相對路徑與 SHA-256；只允許受支援的附件角色，拒絕目錄外路徑、`..` traversal、symlink／reparse、重複角色、非 JSON、超過 4 MiB 的附件及覆寫既有 manifest。Update 明細可載入 manifest，逐項檢查 schema、角色、collection／期間、內容 hash 及 smoke／weekly report 共用工作副本 fingerprint。decision writer 在保存前會重讀 sidecar 與 manifest；具名決定 JSON 會保存 manifest 路徑／SHA 及角色附件 hash。覆核視窗也列出 manifest digest、附件角色、狀態與 hash。

合成 sidecar 加入有效 smoke、weekly report 及 dashboard 附件時，fixture 核得 4 個角色 `verified`，review identity 保持 `partial`，backup／rollback／recovery 保持 `missing`；coverage／freshness、scheduled／manual receipt 與人工 review 仍有獨立缺件或資格限制。無附件的 sidecar 仍顯示 0 verified。這些是合成 fixture 結果，不是實際週封包盤點。尚未用真實 Owner GUI UAT 核對，也沒有寫正式 sidecar／weekly history、產生真實 backup／recovery evidence 或授 Gate credit。

| 驗證 | 結果 |
|---|---|
| weekly approval input、manifest builder、working-copy smoke、weekly review CLI、dashboard snapshot、Update UI focused tests | 147 passed／1 skipped |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped |
| 全域 mypy | 1,155 source files clean |
| 8 個變更 Python 模組 `py_compile` | 通過 |
| `git diff --check` | 通過 |
| scoped document-control（Gate 2 QA 文件＋Feature Map） | 12 features／2 link sources／0 errors |
| APPLICATION_MANUAL scoped check | 找到 2 條既有 `output/trial` Junction 引用 WinError 5；本次新增操作說明沒有新增 Markdown 外部連結 |
| 整合 bounded QA | 全項成功；receipt SHA-256 `8cee31e6a3ea8b4bbb5dfe421730dec8953032e39746bf438ab455d1a731201b` |

最終 bounded Windows Job receipt 位於 task workspace `owned-validation/weekly-runbook-manifest-final9-20261026/receipt.json`；exit 0、kill-on-close／8 GiB／12-process 限制 readback 通過、剩餘 PID 0、無強制清理。Focused tests 使用合成 sidecar；Update validator 只用隔離 fixture。正式資料、sidecar、scheduler 與 Gate 狀態未變。

## 2026-10-26 隔離 Gate 2 recovery rehearsal 工具

新增 `scripts/rehearse_weekly_review_recovery.py`，供人工以既有非正式 weekly-review working-copy DB 與 approval projection 執行可重複的備份／還原演練。它拒絕正式 `twstock.db` 路徑、來源檔 reparse point、非空 WAL／rollback journal、正式／輸出根底下或與來源重疊的 scratch、無效 projection schema，以及 `formal_credit_authorized=true`。只有全新 scratch 根目錄可寫入；source DB、WAL、journal 與 projection 都做前後 hash 讀回。實際 Scheduler 不會被呼叫或停用，disable-first 僅在 scratch 模擬。故障注入後工具把備份還原成新檔，保留故障副本，核對 SQLite `quick_check`、週報 ID／hash／期間摘要及 projection bytes／record count。

本輪對合成 weekly history DB 與 `formal_credit_authorized=false` 空 projection 執行 focused tests **3 passed**；包含成功還原、正式 DB 路徑拒絕、非空 WAL／journal 拒絕與禁止 formal credit。新工具 mypy **1 source file clean**、兩個修改 Python 檔 `py_compile` 通過；Feature Map／QA／Runbook scoped document-control **12 features／5 link sources／0 errors**。PROJECT_SNAPSHOT 單檔核對仍列出 **27** 條既有 `output/` trial/task 外部連結越界，均非本次新增連結。這只證明 utility 的 scratch recovery 機制；未用實際 working-copy／Owner projection 做 live rehearsal，未操作 Task Scheduler，不算 backup／rollback Gate 完成，也不授 Gate credit。Windows sandbox 拒絕 scratch 內 `os.replace`，實作改為將備份還原至新的 scratch 檔，保留故障注入副本，避免覆寫任何來源。

### 2026-10-26 既有 working-copy／Owner projection recovery rehearsal

以現有 `v2_2_week1_20260706_20260712.db`（3,308,916,736 bytes；檔案時間 2026-07-21）及 `C:\Temp\external-evidence-shadow\approved-weekly-history-projection.json`（1,269 bytes；檔案時間 2026-07-28）執行同一 recovery 工具。兩個來源均唯讀；只在全新 visualization scratch 複製、故障注入與還原。資料庫備份／還原 SHA-256 完全相同，SQLite `quick_check` 前後皆 `ok`，一筆 weekly-review identity count／digest 前後一致；Owner projection 備份／還原 hash 相同，讀回 3 筆紀錄並維持 `formal_credit_authorized=false`。兩來源 DB／projection 的前後 hash 相同，`source_files_unchanged=true`。

Recovery receipt SHA-256 `b30676591bfd2ce3bb9d7db795a713f517dd834675e7bf0d1602e08f2e03c90a`；bounded Job receipt SHA-256 `ba3de2c5cb65c616acd27e40c20ece24b16027d402cd98165bd5e115be838eab`。Job exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 自然歸零及 handles 關閉。這是**既有歷史副本**的 recovery 證據，不是目前週期／三週操作日證據；disable-first 僅在 scratch 模擬，沒有查詢或操作實際 Task Scheduler。`owner_review_performed=false`、`formal_credit_authorized=false`；因此它補強了真實工作副本與投影的可恢復性證據，仍不等於當前 Runbook role 完整、Owner UAT 或 Gate 2 通過。原始收據與 scratch 留於 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\gate2-recovery-live-20261026\`。

## 2026-10-27 candidate disposition 綁定週報 history

修正 Gate 2 週流程的順序斷點：舊 Runbook 要求取得已保存週報的 Owner approval 後才建立 history，但 approval service 必須核對已存在的 `review_id`／`review_hash`，照舊步驟會形成循環。weekly CLI 現可接受 `--candidate-review-artifact`，並要求明選原始 sidecar；若 decision artifact 綁定 runbook manifest，還必須指定可信 receipt root。保存前讀取原始 artifact bytes 並計 SHA-256，核對 schema、安全旗標、期別、單一 collection、pending/reviewable 狀態、來源 hash、sidecar SHA 與 manifest binding；保存前再次驗證。候選內容以 `candidate_review_decision` 巢狀欄位加入 weekly history payload，因此 history hash 會綁定該決定及 artifact hash。此 bridge 不寫 sidecar／正式 DB／approval projection，也不授予 Gate credit 或 scheduler 權限；與 `--confirm-action-items` 同次執行會拒絕，避免 partial writes。

Evidence Review「覆盤歷史」明細及 Owner approval confirmation 現會顯示候選決定、Owner／Reviewer 自我聲明身份、理由、collection ID、source hash 與決定 artifact SHA。舊 weekly history 沒有 disposition 欄位時仍相容。Runbook 現改為 candidate disposition → working-copy history save → 唯讀核對同一 review ID/hash → Owner append-only approval → Action Items；三週真實週期、三個操作日、backup／rollback／recovery 的 Gate 條件不變。

| 驗證 | 結果 |
|---|---|
| decision bridge、decision writer、weekly history CLI、history UI focused tests | 48 passed |
| 修改 Python 檔 `py_compile` | 8 個檔案通過 |
| 必要 `tests/test_ui_qt_update_view_workbench.py` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped；報告與 log 位於隔離 visualization scratch `qa_gate2_update_tab_20261027/` |
| 全域 mypy | 1,158 source files clean |
| Feature Map／scoped document-control（QA、QA README、Runbook） | 12 features／3 link sources／0 errors；receipt SHA-256 `c2257c42da188a20bd6331c635fd99d2ce160226c9cca19b762467dc21e64864` |
| APPLICATION_MANUAL scoped check | 2 條既有 `output/trial` 引用因 junction WinError 5 未能核對；本次新增段落沒有新增外部 Markdown 連結 |
| 受控驗證 receipts | 測試／compile／UI Job `e17f5c7ad11ee58b700a7d369b01cf30a2623f82c4614ab19a6998f33ecacb2b`；validator／mypy Job `3f9f94a02402c32e2143523491e17cb607db54b0833fa1faea63542306afd61a` |

兩個 root-owned Windows Jobs 均讀回 kill-on-close、8 GiB／12-process 限制，並自然歸零、無強制清理。第一個 Job 的 validator 日誌預設寫到既有 `output/` junction 時被 sandbox 拒絕；將 log 重導至隔離 scratch 後，validator 通過。測試使用合成 sidecar 與獨立 working-copy SQLite，沒有真實 Owner 決定或原生 GUI UAT；這只修通候選資訊綁定及操作順序，不代表本週已完成覆核、三週 cadence 或 Gate 2 通過。

## 2026-10-27 Evidence Review 內保存候選處置與 SQLite WAL 防競態

Evidence Review「覆盤歷史」現在可在明選既有非正式 working-copy DB 後，依明確開始／結束日，選取 candidate decision JSON 與其 sidecar，將已重驗的候選處置附加至重建週報，再保存到該 working-copy。保存前會重算週報、重驗 artifact／sidecar／collection／期間／manifest，保存後讀回相同 `review_id`、`review_hash` 與 payload。保存作業執行期間會鎖定來源切換、日期篩選、重新整理、Owner 覆核及 Action Item 操作；來源切換與報表載入入口也有程式層守衛，成功／失敗後恢復各控制項。歷史列表仍唯讀；此操作不確認 Action Items、不建立 Owner approval、不寫 sidecar／正式資料、不啟用 scheduler 或授 Gate credit。Owner 仍須重新整理、核對 ID/hash，再另行 append-only 核准。

獨立複核發現舊 bridge 只核對 SQLite 主檔 SHA，可能漏掉 WAL 變更。本次 bridge 改為比對 sidecar 完整 SQLite file-set fingerprint，拒絕非空 WAL／rollback journal，並在重建 approval packet 前後及驗證結尾再次比對；weekly-history save service 對工作副本亦採相同 checkpoint／fingerprint 守衛，若報告讀取期間或寫入前檔案組已變動即拒絕。側車資料與週報 working-copy 不在同一交易中；仍以 hash 與兩次重驗保守 fail closed。

| 驗證 | 結果 |
|---|---|
| save service、candidate bridge（含非空 WAL 與讀取期間 WAL 變動）、Evidence Review UI、history CLI／dashboard focused suite（含來源鎖定） | **111 passed** |
| Evidence Review UI 狀態／控制項（含來源鎖定及成功／失敗 callback 恢復） | **11 passed** |
| 必要 Workbench UI suite | **97 passed** |
| `scripts/qa_validate_update_tab.py` | **25 passed／0 failed／4 skipped**；log/report 在隔離 visualization scratch `owned-validation/weekly-history-ui-20261027-update-logs/` |
| 全域 mypy | **1,159 source files clean** |
| 本輪修改 Python 檔 `py_compile` | **view、test 2 個檔案通過**；先前 service／bridge 整合 8 檔結果見下方既有 QA |
| Owned Windows Job | focused／Workbench／validator／mypy／compile 各自使用 root-owned Job；8 GiB／12-process／kill-on-close 限制讀回，exit 0，程序自然歸零、handles 關閉。Focused 原始輸出與 receipt 位於 `owned-validation/weekly-history-ui-20261027-final-focused/`；其他同名前綴資料夾分別留存各項收據。 |
| 檔案／資料邊界 | 測試使用合成 sidecar 及 mock working-copy；未修改真實 sidecar、正式 DB、Owner projection 或排程。 |

本次競態修正後的完整 focused suite 為 **111 passed**；新增控制項與 callback 恢復案例另以目前完整 UI 測試檔驗證 **11 passed**。WorkBench／validator／mypy／compile 結果如表。第一次重跑 validator 因預設 `output/qa/update_tab/RUN_LOG.txt` 的既有 junction 權限失敗；將其 log/report 導向隔離 scratch 後，25 passed／0 failed／4 skipped，原始失敗保留。尚未進行原生 GUI／Owner UAT，也沒有實際保存或覆核本週真實候選；三週真實週期、三個操作日及 Gate 2 recovery／scheduler approval 條件仍未完成。

## 2026-11-02 排程週報可讀性與容量唯讀盤點

- Collector Markdown 輸出已在程式碼中調整為人工覆核摘要優先；逐列缺值及收據雜湊收在可展開段落，完整證據仍由同週 JSON 保留。若舊收據沒有來源覆蓋摘要，新的說明將其標為覆蓋／品質未知或降級並要求 follow-up；這限制可下的品質結論，不抹除自然採集事實或自動否定 capture-time PIT。舊週報不重寫，格式修正待後續執行採用。
- `F:\Min\Python\Project\FA_Data\output\scheduled\v2_2_weekly_collection` 目前 75 個檔案合計 574,428 bytes（約 0.55 MiB）；10/04、10/18 的收據時間分別為當地週日 18:00:03、18:00:22，對應自然排程；兩筆均為 `pending_human_review`，保存 period、source DB 路徑與當時整庫 source hash，但舊 payload 沒有 `source_coverage`。因此它們是有效的自然排程採集輸入，可由 Owner 延後審查並將品質／覆蓋記為未知及 follow-up，不是已完成的 review history；缺欄位不等同 PIT 失效。
- 10/19–25 的週日排程嘗試逾時；隔離補採提供 Collection ID `ewc_58409a20689d74be`／`ewc_6d44f2be666d127a` 兩份相同 7,859 列候選，均涵蓋週內 10/19、10/20、10/21、10/22 四個交易日，最後交易日為 10/22。該週候選可作內容／缺值覆核輸入；須把自然排程逾時與後續補採分別記錄，不得把補採標成原排程成功。這兩份重複補採只選一份作該週來源，不能重複算兩週。11/01 自然週收集 Markdown 7,358 bytes／JSON 38,049 bytes。上述材料都不是大量空間占用來源。
- F 槽唯讀觀測起始值：已用 860.4 GiB、可用 93.5 GiB。`GetCompressedFileSizeW` 對以下目錄逐檔讀取且 errors=0；當時 logical／allocated bytes 相同：`formal_technical_repair_receipts` 39.38 GiB、`formal_technical_raw_alias_repair_receipts` 9.88 GiB、`technical_indicator_repair_receipts` 7.04 GiB、`excluded_daily_price_repair_receipts` 3.38 GiB、`historical_session_repair_receipts` 3.38 GiB、`formal_market_repair_receipts` 3.37 GiB、`daily_price_repair_receipts` 3.35 GiB。這些目錄最新檔案時間落在 2026-09-22 至 2026-09-29。`ml_allocation_copilot` 為 2.78 GiB，其中 raw PIT publication 2.44 GiB、shadow evidence 0.33 GiB；其目錄於 2026-11-02 05:20 有新檔，shadow evidence SQLite 本體最後修改為 2026-10-31。
- 已接受的 `accepted_daily_price_relocation_20261020.json` 與 `accepted_revision_custody_20261022.json` 引用部分 repair receipt 路徑及雜湊；未確認可恢復性及依賴前，不把這些產物當垃圾刪除或搬移。每週 collection 輸出僅佔約 0.55 MiB，不能藉清它們解決 F 槽容量。
- Task Scheduler 精確 task 讀回在本環境失敗：`Get-ScheduledTask` 回報 CIM access unavailable，`schtasks /Query` 回報 network address invalid。Elevated GUI 畫面可見每日 task 清單及 LastRun／NextRun，但 helper 因 integrity level 不同無法選取 task 或讀 Properties，週日 task action／environment 仍未核實。因此只確認 repo wrapper 預設 DATA_ROOT／OUTPUT_ROOT 為 F 槽與 11/01 實際報告來源路徑為 F 槽；沒有改註冊 task。
- 本次未改正式資料、sidecar、既有排程 task 或歷史週報；未刪除／移動任何輸出。此程式碼變更尚未執行測試或自然排程驗證。Gate 2 狀態不變。

### 2026-11-02 安全壓縮與當日排程寫入補查

- 唯一執行的正式輸出容量變更是 NTFS 壓縮單一已具既有 QA 壓縮證明的快照：`formal_technical_repair_receipts/20260923_run02/stage/computed.sqlite`。壓縮前 SHA-256 `AEF712331735FE58E892A264EC4732003743841D11E58CA2CEE2B7528E8449AB`、長度 25,685,880,832 bytes、mtime 2026-09-23 16:44:20；壓縮後重讀 SHA-256、長度及 mtime 完全相同，NTFS allocated size 從 25,685,880,832 降至 7,364,136,960 bytes，回收 18,321,743,872 bytes（約 17.06 GiB）。讀取 errors=0。此目錄因此目前約 logical 39.38 GiB／allocated 22.32 GiB。沒有刪除或搬移任何檔案。
- 壓縮後 F 槽讀回約已用 867.33 GiB／可用 86.53 GiB；相較起始觀測，可用空間淨減約 6.97 GiB，與單檔回收量不一致。當日 `output/scheduled` 內可見新／更新檔合計不足 20 MiB；其中 `ml_allocation_copilot` 當日 7 個檔案約 0.15 MiB，不能解釋差額。另唯讀掃描資料根目錄找到當日寫入目標：`sqlite/twstock.db` 約 3.90 GiB；`technical_analysis/*_indicators.csv` 約 2.11 GiB（1,949 個檔案）。它們是正式行情 DB 與個股技術指標快取，非週報或可隨意清除的排程垃圾。沒有更新前逐檔大小快照，故僅能確認當日更新規模，不能將這些邏輯檔案大小當作 volume 增量，也不能精確解釋 6.97 GiB 淨變化。
- `v2_2_weekly_collection` 75 個檔案僅約 0.55 MiB；因此三份週收集材料不是大量空間來源。`ml_allocation_copilot` 的 2.44 GiB raw PIT publication 與 0.33 GiB shadow evidence 仍是有明確研究／證據用途的資產，且已有保留及可裁定性限制；本次不刪除它們。
- 這次 NTFS 壓縮不改內容雜湊、長度或時間戳；它是對單一已核准可壓縮快照做容量處理，不會讓 Gate 2 證據成熟。Gate 2 未解除；週報格式程式變更尚未測試，Task Scheduler 的實際 action／執行環境也未驗證。

### 2026-11-02 Owner 週期決定保存與每日 outcome manifest 容量修正

- Owner Archie 明確接受 9/28–10/04、10/12–10/18、10/19–10/25 三份週期材料作為 review 輸入；前兩期的 `source_coverage` 未採集，覆蓋／品質維持未知，第三期保留原週日排程逾時及隔離補採的區別，且僅按 10/19–22 已觀察交易列判讀。三筆 append-only weekly history 已保存並讀回：`eor_7250d4397141a813`（`sha256:7250d4397141a813182d7353fd2e726428f28e5d59f1328179a75e2d99eb6756`）、`eor_806e64e336c5c670`（`sha256:806e64e336c5c670ecb901c528bff6549cc8f4d4fd085603d8fe6a80cbed15d4`）、`eor_fd3be048288f822b`（`sha256:fd3be048288f822b1527580623cce433bc95038fee2548ffb614a0f34e596f8f`）。Owner approval projection 對應追加三筆 Archie／Owner 記錄並以各 review hash 綁定；投影仍明確 `formal_credit_authorized=false`，這些人工決定不會虛構缺少的來源覆蓋或排程成功。
- 10/29、10/30、11/02 三個操作日的推薦 snapshot 與 event identities 可由 result ID 對應，但排程 forward-outcome 收據皆因 `source_observation_manifest_too_large` 在 evidence DB 寫入前 blocked，故目前沒有 outcome rows。根因是 `ForwardSourceObservationRecorder` 的 manifest 限 512 KiB，低於 producer 已支援的 2,500 events × 4 windows 所需容量；不是來源缺資料。已將單一 manifest 上限調為 16 MiB，readback 使用相同上限，整次 observation 仍受 64 MiB `MAX_RUN_BYTES`、64 MiB readback 及既有 rows/chunks/retention 限制。這是程式修正；本次未執行測試或真實排程重跑，故尚未證明修正後 receipt 成功，也未補寫任何 outcome。
- 三份週期 history／Owner review 已完成保存。當時每日 outcome producer 修正仍待排程收據確認；三操作日附件包、working-copy recovery 與 scheduler approval 尚未核證。後續核對結果見本文 2026-11-03 各節；績效視窗自然成熟不作 Gate 2 等待條件。沒有啟用或修改正式排程，也沒有授予 formal credit。

### 2026-11-03 排程 outcome 觀察包真實資料 dry-run 與核實更正

- 初次把 manifest 上限調至 16 MiB 後，對正式 DB 的唯讀 dry-run 仍以 `source_observation_run_byte_limit` 失敗。繼續追查發現：來源 bundle 未捕獲時，service 仍建立逐列 binder，讀取並重複保存所有歷史價格投影，再為每列寫入「資格未知」binding。現修正為只有 `source_bundle.status=captured` 才建立 binder；bundle 未捕獲時，只取 forward 計算實際使用的日期／收盤價兩欄，並由 run receipt 明確保留 `daily_price_source_bundle.status=unknown`。有 captured bundle 時，完整投影、逐列 binding 與資格守衛不變。來源 unknown 不會因此被提升為 PIT 或正式可用。
- 修正後以正式 `F:\Min\Python\Project\FA_Data\sqlite\twstock.db` 作唯讀來源，照實際排程參數（120 天、最多 2,500 個 recommendation events、四個 windows、require cohort identity）執行 dry-run。結果 `status=dry_run`、exit 0、`writes_evidence_db=false`、`source_db_changed=false`；64 個合格 events 掃描、215 個不完整 identity events 跳過，256 筆候選 outcomes（84 created／172 updated）只在 dry-run summary 計算，未寫入 DB。Observation `run_id=20261102T235210188546Z`，864 queries／121,032 rows／864 chunks；完整 manifest/chunk readback 回傳 `status=verified`，manifest SHA-256 `sha256:1b534e9ededfefea72b28110ee0c7d5720557faa0f369afa1ea9c232990e83c6`。收據及 chunks 僅在隔離 scratch `C:\Users\archi\.codex\visualizations\2026\10\31\01a193b0-7972-7dd3-b07f-4589e33735fb\forward-outcome-capacity-dryrun-fixed-20261103\`。
- 此 dry-run 仍如實保留 health blockers `outcome_price_missing`（1538 之 5／10 日官方預定交易日缺價）及 `official_maturity_calendar_unavailable`；106 筆尚未到期、21 筆時間契約需人工／來源確認，來源 bundle 仍 unknown。它證明觀察包容量修正與逐列 readback 成功，不證明來源合格、outcomes 已寫回或 production scheduler 可啟用。
- 對三操作日 evidence 的 `run_id` 判讀更正：`recommendation_result` importer 把推薦 `result_id` 寫入 `source_id` 與 `source_snapshot_id`，不把它偽裝成 Research Run `run_id`。因此 10/29、10/30、11/02 的真實操作日事件可由各自成功排程 snapshot log、精確 result ID 與 event IDs 對應；三個日期的 evidence event 計數已具備，空 `run_id` 本身不否定此對應。它仍不補足各日 Runbook evidence 附件。
- 目前三筆 weekly history 的狀態仍為 `coverage_only`、`scheduler_readiness=not_ready`；每週各有六項 warnings（working-copy smoke 未提供、liquidity-gate payload 缺漏、scheduler approval 缺漏、recommendation persistence 缺漏、screening matrix 缺漏、why-not payload 缺漏），三週決策品質 review／Action Item 均為 0。這些 Owner review／approval 是真實、append-only 且 hash 綁定的人工決定，但不能把 coverage-only 報告改標為完整、不能替代 action-item 節奏，也沒有設定 `production_scheduler_allowed=true`。接續 Gate 2 工程工作由 Codex 負責，不要求 Owner 重審三份週報。
- 目前 Owner working-copy／projection 的 backup、故障注入與 restore rehearsal 已通過，見前一節。至此已完成三週具名 history／Owner review、三操作日事件與隔離 recovery；Gate 2／production evidence scheduler 仍不可標為全部通過，除非剩餘 working-copy writer／idempotency smoke、Action Item lifecycle、Runbook 包及正式 approval 有真實證據滿足。未來 outcome 自然成熟不是 Gate 2 解鎖前提。未修改正式 evidence DB、Task Scheduler 或 Owner projection。

### 2026-11-03 三操作日 outcome dry-run 與未發布年度行事曆分類修正

- 對正式 `twstock.db` 以唯讀模式重跑 2026-10-29..2026-11-02 的三操作日範圍，沿用正式排程設定（`recommendation_included`、四個視窗、最多 2,500 events、要求 cohort identity），輸出只寫入隔離 scratch `C:\Users\archi\.codex\visualizations\2026\10\31\01a193b0-7972-7dd3-b07f-4589e33735fb\forward-outcome-three-operation-days-dryrun-calendar-fix-20261103\`。收據 `run_id=20261102T235910015204Z`、SHA-256 `sha256:9ca885cb15840abef888cfc7e0585fbf637788d5131ae54a59ccdab0d002ed72`；8／8 events identity 完整，dry-run 產生 32 筆明確 `insufficient_future_data` 候選結果，`health_classification=waiting_for_natural_maturity`、blockers 為空。正式 DB 前後 size／mtime 相同、`source_db_changed=false`、`confirm=false`、`writes_evidence_db=false`。
- 此次發現先前將未來年度官方行事曆尚未發布列為時間契約 blocker。修正後，當缺少的年度均晚於官方日曆 cache 的 as-of 年度，結果改標 `waiting_for_natural_calendar`／`future_official_calendar_not_yet_published`，保留為尚未成熟的 missing-quality／`insufficient_future_data`；其他 calendar 缺漏仍 fail closed。三操作日結果警告分布為 8 筆未來官方行事曆尚未發布、24 筆未來價格尚未成熟，時間契約 blocker、outcome 缺價及 run blockers 均為 0。這不將未發布日曆推測為交易日，也不把任何結果當成熟或正式 evidence outcome。
- Observation manifest／7 個 chunks 完整唯讀讀回為 `verified`（7 queries、21,801 rows、7 chunks；manifest SHA-256 `sha256:0e07a2d3f99c618584deae862485dadd6b46411a2d5a9d0bf705c7b74dbcb8ce`）。收據明示來源 bundle `unknown`、`pit_qualified=false`、`training_eligible=false`、跨查詢 snapshot consistency `not_guaranteed`；所以這只驗證容量、序列化及 readback，不構成 PIT／source qualification、自然排程寫入或 Gate 2 通過。Gate 2 後續工程項目是隔離 working-copy 的 confirmed writer／idempotency smoke、逐操作日 Runbook evidence package、真實 Action Item lifecycle 與明確 scheduler approval；5／10／20／60 日績效自然成熟只影響結果判讀，不是等待解除 Gate 2 的前提。Owner 已接受的三份週報不需重讀。
- 對三個已保存週期以唯讀 `--plan-action-items` 重建 weekly review，三期都因沒有 Decision Quality review／items 而規劃出 **0** 個 action item；沒有為了湊 Gate 而手造項目。唯讀查詢 `Get-ScheduledTask` 未返回 task，`schtasks /Query /TN baldr-forward-outcomes-daily /V /FO LIST` 回 `ERROR: The network address is invalid.`；此環境無法證實該 Task Scheduler task 當前 State、Action、Last／NextRun 或 enabled 狀態。這不是停用證據，也沒有修改 task。真實 Action Item lifecycle、Task Scheduler 核實及獨立 approval artifact 仍是 Gate 2 待辦。

### 2026-11-02 目前 Owner working-copy／projection recovery rehearsal

- 以目前含三筆新週期 history 的 working-copy `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-review-working-copy-20261025\sqlite\twstock.db` 及 Owner projection `C:\Temp\external-evidence-shadow\approved-weekly-history-projection.json` 執行隔離 recovery rehearsal；唯一輸出寫在新的 scratch `C:\Users\archi\.codex\visualizations\2026\10\31\01a193b0-7972-7dd3-b07f-4589e33735fb\gate2-current-working-copy-recovery-20261102\`，收據檔為該目錄下的 `recovery-rehearsal.json`。
- `passed=true`、`source_files_unchanged=true`；DB source SHA 前後相同（`sha256:acbe8db103c7eb99f6c84661faecac8ea62895c7bc011e023dfdae19181a6c5e`），SQLite `quick_check` 還原前後皆 `ok`，weekly history identity 為 3 筆且前後 digest 相同（`sha256:c9c44f7b8c0ce9bbb49f73654de713a603c3c432b61a9c0843891b6635f80828`）。Projection 還原 SHA 前後相同（`sha256:52f4d03774fccc8bceaf1f4c1a6858d07caed9173da1a82ff795f593249050b1`），核對 6 筆 approval projection entries，`formal_credit_authorized=false`。WAL／journal 未變更。
- 這完成目前工作副本及投影的隔離 backup／fault-injection／restore 證據；`disable_first` 只在 scratch 模擬，收據明載 `actual_scheduler_touched=false`、`task_scheduler_api_called=false`，沒有觸碰正式排程。這不是三個操作日收據，也不代替 outcome manifest 修正後的實際排程收據、Runbook 附件包或 scheduler approval；Gate 2 仍未解除。

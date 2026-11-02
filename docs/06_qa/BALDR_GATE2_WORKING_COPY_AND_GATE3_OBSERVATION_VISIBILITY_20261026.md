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

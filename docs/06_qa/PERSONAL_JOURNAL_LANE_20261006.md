# Personal Journal lane：明示路徑與唯讀 projections

日期：2026-10-06。lane：`C:/Projects/PythonProjects/technical_analysis_personal_store_lane`，branch `lane/personal-store-separation-20261005`。本包基準 `5efb3f13a989667c97ddac619cf51c58cd212b18`，承接原 path/COW 兩提交；不用 rebase/merge 吸收 UI 主線。

開始及交付前唯讀比對 dev `1ad0d53db71eef1ab69fef26b23be637c0e40e28`：JournalService、continuity_review_projection、workbench_source_service、personalization_read_service、portfolio_store 相對原基準 `631d6ad189e490dc75e964ee4abafc69df7ce114` 沒有 committed 差異，且無 shared dirty ownership。整合前主 owner 仍須重查。

## Ownership 與結果

只新增 `app_module/personal_journal_paths.py`、`tests/test_personal_journal_storage.py` 與本 QA 文件；只修改 `app_module/journal_service.py`、`continuity_review_projection.py`、`workbench_source_service.py`、`personalization_read_service.py`。PortfolioJsonlStore、UI main、config、全域 plan／Manual、Portfolio／Ledger／Paper 演算法／文件均未改。未新增代理、未建正式 store、未讀真實 notes／持倉／帳本，沒有 migration、分享、push 或 dev cherry-pick。

PersonalJournalPaths 包裝既有 PersonalDataPaths，`resolve_personal_journal_paths` 明示 market、personal、legacy output roots，不看 watchlist source／activation；不建立 watchlist DB 或目錄，不全域改 OUTPUT_ROOT，也不把 notes 存入 watchlist DB。

| 用途 | 位置 |
|---|---|
| personal notes JSONL | `P/research_notes/journal_entries.jsonl` |
| sibling OS lock | `P/research_notes/.journal_entries.jsonl.lock` |
| legacy 唯讀來源 | `O/portfolio/journal_entries.jsonl` |
| 備份保留契約（未有 producer） | `P/backups/research_notes/` |
| audit 保留契約（未有 producer） | `P/research_notes/audit/` |

P 推薦仍為 `%LOCALAPPDATA%/baldr/personal`，這只是路徑提案，未建立或正式啟用。source JSONL、全部歷史、revision／ACK／tombstone／CAS 語意不改；個人模式拒絕未知 record_type、交易與 overwrite API。繼承既有 append／project 實作，不複製金融計算。PersonalJournalJsonlStore 不呼叫父類建構子的 legacy mkdir；首次 writer 操作才建立 personal notes／lock。writer 的 load 仍沿用 OS lock；唯讀 projections 與 legacy adapter 不建鎖。

同時驗證 root 互斥、reparse/junction/symlink、hardlink 與 regular file type；每次 reader（含 cache hit）與 writer 操作重新檢查。legacy adapter 對 source 只讀，用 read 前後 stat 拒絕讀取期間變動，不對來源加寫鎖。個人 root 必須由 caller 控制 writer custody；本 path guard 不是抵抗惡意程序在檢查與開檔間換 junction 的 handle-based IO。唯讀 projections 沿用原有直接 JSONL 讀取／上層 fingerprint 契約，不聲稱交易式快照。

`cancel_check` 在 writer 操作開始檢查，取消尚未開始的 append 不產生 notes 或 rollback 寫入；成功 append 不倒寫／刪除歷史。readonly personal readers 接既有 cooperative_read_cancellation；未知 type 和 unsafe path fail-closed，可由 caller 顯示診斷。沒有真 migration，故不存在資料回復／自動搬備份流程；backup／audit 目前只保留受守衛的目錄契約，沒有新檔生成，也不呼叫 config.create_backup。

## 主 owner 最小接線（本 lane 未修改 UI/config）

```python
from app_module.personal_journal_paths import resolve_personal_journal_paths

notes = resolve_personal_journal_paths(
    config.data_root,
    personal_root=approved_notes_personal_root,
    legacy_output_root=config.output_root,
)
journal = JournalService(config, journal_paths=notes)
continuity = ContinuityReviewProjectionService.from_personal_paths(notes)
workbench = WorkbenchSourceService(config, journal_paths=notes)
personalization = PersonalizationReadService.from_paths(
    output_root=config.output_root,
    journal_paths=notes,
    evidence_db_path=existing_explicit_evidence_path,
)
```

root 選擇需要新增獨立 notes selector；目前 config 的 personal root／watchlist source 成對約束不應迫使 notes 啟用 watchlist。可由 composition 顯式傳入 approved notes root，延後 global config 變更。

明示讀 legacy：`JournalService(config, journal_paths=notes, legacy_read_only=True)`、`ContinuityReviewProjectionService.from_personal_paths(notes, legacy_read_only=True)`；Workbench／Personalization factory 用 `legacy_journal_read_only=True`。這是 caller 明示模式，不以 personal file 缺失自動 fallback。legacy 原始路徑固定 O/portfolio/journal_entries.jsonl，不掃描 glob 或猜其他舊檔。

`journal_paths` 與原 `journal_path`／Workbench 自訂 continuity adapter 不可同時傳入，避免 reader/writer 意外分流。原未傳新 selector 的 APIs 保持 legacy 行為（包括既有 legacy writer），因此本包不是全域禁寫來源；主 owner 必須切換所有 journal caller 後才可啟用個人模式。尤其 ui_qt/main.py 的 JournalService、journal readonly path、personalization 路由，以及 controller/workbench 使用同一 notes 選擇，不能只接一個 writer。個人 reader 可明示 legacy 相容，但不混讀 personal＋legacy streams。

Portfolio/trades readonly path、其他 Portfolio／Ledger／Paper owner 留原責任。DecisionQuality／Desk／Evidence fallback 到市場 twstock.db 的 custody 風險仍在，不擴本包為 DB migration；市場 export 仍僅 CSV 白名單 metadata plan，SQLite 市場分享仍無表級契約。

## Synthetic 驗證與既有 blockers

最終驗證：**139 passed、2 deselected**，其中專屬 personal journal 27、既有 path 68、Journal/continuity/Workbench/personalization 回歸 44；沒有 skip。新 root 無副作用 discovery、legacy readonly 無來源 lock／mkdir、JSONL notes/revision/tombstone/ACK/CAS、未知type、取消後恢復操作、雙新 process OS lock（16 append）、CAS 同 token 只有一人成功、cached reader 硬連結拒絕、真 Windows junction swap 與 hardlink 負例均實際通過。來源 synthetic bytes／mtime 與檔案清單保持不變。

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_personal_journal_storage.py tests/test_personal_data_paths.py tests/test_decision_continuity_write_path.py tests/test_continuity_review_workbench_r1.py tests/test_continuity_review_workbench_r1_integration.py tests/test_personalization_read_service.py tests/test_workbench_source_service.py tests/test_workbench_read_only_boundary.py -q -o addopts= -k "not test_watchlist_repository_history_conflict_tombstone_and_legacy_baseline and not test_producer_backed_workbench_to_shared_report_journey_and_readback" --basetemp=C:/Users/archi/AppData/Local/Temp/ta_journal_final_1006_a
```

未排除初次回歸：44 passed、2 failed。兩個失敗均以專屬 Temp sitecustomize 唯讀載入未修改 `5efb3f13` 四個介面模組、傳給父／子process後重現相同錯誤，不覆寫 tracked files：

1. `test_decision_continuity_write_path.py::test_watchlist_repository_history_conflict_tombstone_and_legacy_baseline` 仍期待 WatchlistRepository 原地升級舊 schema，現 COW 規則拋 `watchlist_schema_requires_copy_on_write`。原測試 owner 承接。
2. `test_continuity_review_workbench_r1_integration.py::test_producer_backed_workbench_to_shared_report_journey_and_readback` 先完成資料 readback，後 busy-close helper 失敗。modified 與 baseline receipt 均為 `report worker did not reach busy barrier`、`close_requested_while_busy=false`。UI owner 承接，不宣稱 busy-close gate 通過。

baseline bootstrap 與兩次 synthetic receipts 位於 Temp `ta_journal_baseline_modules_1006`、`ta_journal_baseline_failures_1006`，不 stage。五個 production 模組 mypy（`--follow-imports=skip`、專屬 Temp cache）通過；六 Python 檔 py_compile、git diff --check 通過。初次 mypy 用預設 cache 內部錯誤，專屬 writable Temp cache 正常，未安裝依賴。

沒有 UI 修改，不將本包驗證冒稱主 owner 的 UI／正式資料驗收。整合前重查所有 exclusive 檔 ownership，再 cherry-pick 本 lane 第三包（前兩包已整合）。正式 journal migration 另需批准 source、target、backup、停寫、校驗、切 writer 與回復方案；不能把 watchlist 已批准／整合當成 notes／portfolio 搬移批准。

回滾：尚未正式啟用時可受控 revert 本包，保留前兩包個人 path/COW 契約。本 lane 未執行 revert。已寫入 personal notes 後不能只退程式就重新啟用 legacy writer；先停用 caller 並保留兩個 streams 待人工審查，不自動覆寫或合併歷史。

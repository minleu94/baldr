# BALDR B10 Notes Backup / Restore Adapter QA

## 回復清單（實作前）

本任務只會新增下列三個檔案。若本輪需回復，僅移除這三個 B10 新增檔；不得還原、覆寫或清理其他工作目錄中的既有檔案或資料：

- `app_module/personal_notes_backup.py`
- `tests/test_personal_notes_backup.py`
- `docs/06_qa/BALDR_B10_NOTES_BACKUP_20261006.md`

不建立真實使用者備份、不做 restore/migration、不啟用正式 caller，也不清除任何部分產物或 Temp 證據。路由是有限位元組的原始 notes JSONL 備份，不新增行情、策略、回測、未來資訊或金融績效計算；Look-ahead 檢查結果為本功能沒有新增任何計算或訊號資料流。

## 實作與驗證狀態

`PersonalNotesBackupAdapter(journal_paths, *, store_identity, max_bytes)` 只備份 `PersonalJournalPaths.journal_file` 原始 JSONL 位元組。identity 必須是非空、無首尾空白的 caller-provided 字串；`max_bytes` 必須是正整數。`backup(snapshot_path, receipt_path, confirmed=False, cancel_check=None)` 和 `restore_into(target_journal_paths, receipt_path, expected_receipt_sha256=..., confirmed=False, cancel_check=None)` 預設均為 dry-run，輸入與產物會先做有界讀取／驗證，dry-run 不建立目錄或輸出。只有 `confirmed=True` 才建立輸出，且使用 exclusive create，拒絕覆寫既有檔案。

兩個備份輸出必須是原 `journal_paths.backup_root` 的直接子檔。Receipt 使用 `personal-notes-backup.v1`，記錄 identity、notes source canonical path／size／SHA-256，以及 snapshot canonical path／size／SHA-256；回傳 frozen receipt 帶 receipt bytes 的 SHA-256。Restore 先比對 caller pin，再驗 schema、identity、來源引用、snapshot 路徑／size／hash，最後只以 create-only 寫入 target selector 的 `journal_file`。來源、輸出及 target 透過 `assert_personal_store_path` 檢查 containment、canonical path、link／hardlink，作業系統 I/O 使用 `to_internal_io_path`。

已新增合成測試，涵蓋 dry-run 與 preflight cancel 不建輸出、notes bytes/hash 不變、backup→另一個 synthetic personal root restore→新 Python process 的 `JournalService` 精確讀回，以及 byte budget、超長 identity 造成 manifest overflow、pin、receipt schema／JSON／path／size／readback、snapshot hash、既有目標、create-only、source hardlink 與 snapshot／receipt 間 cancel。失敗後不刪除本 adapter 已建立的部分 snapshot／receipt；已建立 backup root 或 snapshot 後才收到的 cancellation 會保留當時產物。SYMLINK 用例因 Windows 環境回報 WinError 1314（缺少建立 symlink 權限）而 skip，未改動環境權限。

驗證結果：

- `python -m pytest -p no:cacheprovider tests/test_personal_notes_backup.py -q -o addopts= -rs`：14 passed，1 skipped。新程序測試是直接啟動 Python 載入 JournalService；不啟動 pytest。主測試使用 `-p no:cacheprovider`，無 pytest cache warning。
- `python -m mypy app_module/personal_notes_backup.py tests/test_personal_notes_backup.py`：通過，2 source files。
- `python -m py_compile app_module/personal_notes_backup.py tests/test_personal_notes_backup.py`：通過。
- Look-ahead 自查：本功能只複製同一 notes JSONL 位元組，不新增行情輸入、預測、交易、策略或績效計算。

所有測試均使用 pytest 合成暫存目錄；沒有讀寫真實資料庫，也沒有執行正式個人路由啟用或遷移。文件與 adapter 不代表正式備份操作已獲批准。普通 fstat 前後指紋用於發現可觀察到的檔案變化，不保證防範惡意競態；caller 必須控制個人根目錄及其父目錄的寫入權限。late cancellation 或寫入失敗若已建立 backup root、snapshot 或 receipt，會依契約保留，不做自動清理。

回復本任務只移除上述三個 B10 新增檔；不還原中央 service/config 或其他 lane 檔案，也不刪除任何測試證據或 Temp 資料。

中央同版覆盤／notes 聯集：`.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_personal_notes_backup.py tests/test_baldr_b10_private_review.py tests/test_decision_quality_service.py tests/test_decision_quality_repository.py tests/test_personal_store_selection.py tests/test_decision_quality_dashboard_service.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/b10_notes_review_union_20261006.xml`：42 passed／1 symlink 權限 skip，8.74s。JUnit SHA256 `0754da2a795f91ea2563f5735fac0247dd53287419635c205d9b9868e7592466`，raw 不提交。Manual 已同步工程入口、參數、dry-run／create-only 步驟、判讀、取消與排錯；caller 接線及正式啟用資格未提升。

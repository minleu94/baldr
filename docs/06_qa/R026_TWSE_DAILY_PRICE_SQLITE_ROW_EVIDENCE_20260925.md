# R026 TWSE 前瞻日價列證據（2026-09-25）

## 範圍與資料語意

此有界切片新增前瞻式 TWSE 每日價格列證據。`DataLoader` 對本次回應建立 projection manifest；排程更新流程只把本次成功取得的診斷傳給既有 SQLite sync；sync 成功後才嘗試 create-only 發布 SQLite 列證據。讀取器驗證 custody、manifest、CSV 投影與 SQLite 指定欄位的讀回值。證據失敗回報 UNKNOWN，不撤銷既有 CSV／SQLite 更新，也不改既有消費者行為。

`source_date` 是既有的 requested/ingested date key；目前未驗證 MI_INDEX 回應或每列日期能證明交易所資料期，因此不得解讀為 payload 日期或 PIT 可得時間。`source_published_at` 固定 UNKNOWN。`first_observed_at` 是本機取得回應的觀察時間；`written_at` 是 SQLite sync 成功後進入 evidence publisher 的時間，不是 commit 或讀回完成時間。

`sqlite_projection_row_sha256` 只摘要 manifest `projection_columns` 指定欄位，以 SQLite `typeof()` 與實際讀回值驗證；不代表 `daily_prices` 的所有動態欄位或完整來源身分。每個候選列分別讀回，使用各自的唯讀 transaction，沒有跨列一致 snapshot。

## UNKNOWN 邊界

- 缺少本次 custody／projection、舊 CSV 或既有檔案 skip、無資料、缺檔、解析或驗證錯誤，都不會推導 EMPTY 或沿用舊 receipt。
- TWSE/TPEX 同鍵碰撞（即使值相同）、TWSE 重複鍵、未觀察到的既有 SQLite 列、後續 CSV／SQLite 漂移及 sidecar 發布失敗，均不得取得列證據。既有 upsert 可保留未出現在本次輸入的舊列；它們仍為 UNKNOWN。
- SQLite、CSV 與 sidecar 間沒有共同 transaction。硬連結 create-only 發布失敗時只令證據 UNKNOWN；短 TEMP 測試不證明正式長路徑 OUTPUT_ROOT 可用。
- 本切片只處理可逐列追溯的本次 TWSE 觀察，不證明來源完整性、整日 snapshot、歷史可得時間或跨來源 PIT，也不回填舊列。

## 合成驗證

新增測試 `tests/test_twse_daily_price_sqlite_publication.py`，涵蓋 DataLoader／`UpdateService.update_daily()`／scheduled sync handoff、SQLite typed readback、partial upsert、同鍵碰撞／重複、舊檔與 skip、CSV/raw payload 被替換、no-data、發布失敗及後續 drift。R015 probe 確認專用 `daily_price_files` 路徑保留合併後重複鍵；publisher 以 key multiplicity 拒絕證據。因此撤回先前對完整同值列的疑慮，並新增永久負例：以完整 16 欄 TWSE CSV 原樣複製為 TPEX CSV，確認跨來源同鍵仍為 UNKNOWN。未修改 production code。測試 inventory 僅新增該測試的一筆 `service-oracle-data-market` entry。

Final fresh TEMP route 使用 `PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT` 與短 TEMP：8 個檔案，86 passed，exit 0（pytest 自報 5.69s）。Log：`C:\t\twsefin_5d044c\pytest.log`，SHA-256 `8FDC73EC0F9061198F9EA348C25797D0AC3C8E83415B40AA2DCAA1C0788977CF`。完整同值跨來源負例在獨立短 TEMP 亦通過，1 passed。

PowerShell 路由（`$r` 指向本次唯一短 TEMP 根目錄）：

```powershell
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $r 'data'
$env:OUTPUT_ROOT = Join-Path $r 'output'
.\.venv\Scripts\python.exe -m pytest tests/test_twse_daily_price_sqlite_publication.py tests/test_core/test_data_loader.py tests/test_daily_price_source_guard.py tests/test_daily_price_revision_write_guard.py tests/test_update_daily_output.py tests/test_scheduled_data_update_runner.py tests/test_task_loop_01_contract.py tests/test_update_service_import_contract.py -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $r 'p')
```

更早的 provenance red case `test_csv_rewritten_after_download_cannot_be_bound_to_original_raw_receipt` 在修補前曾錯誤得到 `captured`，預期是 UNKNOWN；該次未保留可核對的 pytest log，不列作帶雜湊收據。修補後同一負例、`Response.content` 與 `.json()` 不一致負例、完整同值 TWSE/TPEX collision 負例及上述 final route 均通過。

Final source 靜態檢查：四個 production 檔及測試 `py_compile` 通過；scoped mypy（`--follow-imports=silent`）四個 source files、0 issues；量化精度／look-ahead guard 通過。`git diff --check` exit 0，whitespace scan 無尾端空白。

## 獨立複核與 bounded 接受

R015 以同一 8-file fresh TEMP route 獨立重跑 **86 passed／0 failed**；log `C:\t\r015_236df3ae\pytest.log` SHA-256 `CC58E88EFC65A456AD2D170344614DE4D69BE49016A74287448718AB59DCCC05`。R015 確認 source/test/inventory SHA 相符，scoped mypy、compile、quant/look-ahead guard 通過，未發現 P1/P2。Root 對本前瞻 row-evidence producer slice 裁定 bounded `ACCEPTED_SCOPE`。較早測試 SHA `ACF43DE688AC4D114B2811CE3829BCB422F3FCDEF2BA66541A88057DF9DC3830` 是加入完整同值 TWSE/TPEX 負例前的歷史 bytes，不是 final test receipt。

Final SHA-256 manifest：helper `data_module/twse_daily_price_publication.py` `466CC7C1E22F37C2D83E516BA3F9D3E6A3C4BCA3B37DB72EF3363636F7F40EDD`；DataLoader `data_module/data_loader.py` `A270A87AF4A37FB8152446A75BAE38EF3076684974BF55B1D90602A3648F0B05`；UpdateService `app_module/update_service.py` `5D94EB7601BB7E9D53CCD22EFF05A2F8124EF449B7A11B50E73120240E421717`；scheduled runner `scripts/scheduled/run_daily_data_update_quick.py` `B799C1BDF0FE894533F5E1DC55A362AB72037847B71D9FB11B23CB6EDE78886B`；test `tests/test_twse_daily_price_sqlite_publication.py` `FAF30E398227F6772DF646CBD27AC744A6E8973B92797AD957CB1545A29DF6A3`；inventory `qa/full_app_healthcheck/test_inventory.py` `B69E7FE019CA27B5593E76E2FA5C040D4D794562A711DF6EAD0CB16EBFEAEEAC`。

接受只涵蓋上述合成、前瞻逐列 evidence 路徑。`row_evidence` 是內部 sync JSON，不新增 UI／Manual 語意；R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`，未證明歷史 PIT、完整資料來源、跨資源原子性或正式長路徑支援。
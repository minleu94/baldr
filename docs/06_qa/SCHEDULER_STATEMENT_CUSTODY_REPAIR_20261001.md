# 每週 MOPS 公告候選 custody 與來源讀回 QA（2026-10-01）

## 結果

每週 V2.2 wrapper 現可在既有 core collection 成功後，另外啟動固定六筆查詢的 MOPS research capture。已驗證新路徑只保存公告查詢的原始 HTTP entity、來源 metadata、legacy artifact hash 與唯讀 readback；沒有財報數值、feature、label、模型輸入或 Formal/OOS credit。既有 V2.2 `pending_human_review`、SQLite sidecar 與 exit code 契約不變。

成功 HTTP response custody 是 opt-in。一般 CLI 維持舊輸出；排程 wrapper 預設開啟，明確設定 `BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 可關閉。core collection 非 0 時不呼叫研究 collector；研究 collector 失敗會留下每次執行自己的狀態與錯誤輸出，wrapper 最終仍回傳 core exit code。Collector 不初始化 `TWStockConfig`，只從 `DATA_ROOT`／預設值純解析 protected paths；避免其初始化建立 DROOT 資料、log 或 research-run 目錄。

`--last-complete-taipei-7-days` 是封閉 preset：以真實台北時鐘選取昨天往前七個完整曆日，固定 `sii`、`otc` × `F26`、`F27`、`F28`，一個七日日期窗、30 秒 timeout、0 retries，恰好六個 POST。此 preset 拒絕明示日期、範圍、查詢項目、輸出名稱／root、timeout、retry、window 或其他 custody flag 覆寫。固定輸出為 repository `output/research/mops_statement_availability/run_<UTC timestamp>/`，run directory 及各收據均 create-only。

每個成功或官方 no-data HTTP response 保存完整 encoded entity bytes（每份最多 8 MiB），保留 HTTP 狀態、請求與完成時間、嘗試 lineage、查詢 market/item/window、entity SHA-256 與 legacy canonical JSON SHA-256。失敗回應沿用最多 64 KiB prefix；成功 entity 與失敗 prefix 合計每 run 不超過 128 MiB，metadata 每檔不超過 64 KiB、總量不超過 4 MiB，寫入前保留 16 MiB 磁碟空間。讀回會以 bounded single-link regular-file reader 重算 entity／metadata／artifact hash、解碼 response 並重算 canonical JSON hash，再寫入 create-only `source_readback.json`。每 run 的 `weekly_research_status.json` 記錄真實選取日期、六筆查詢數、開始／artifact capture／完成時間、artifact SHA 與來源讀回狀態。

固定 preset 將六筆有效 `status=fail` 官方 no-data 回覆標記為 `official_no_data`，以 exit 0 結束並保留六份 response custody；成功觀測標記為 `captured_research`。任何 transport/schema/query 或 invalid-event failure 會標記 `partial_failure` 並回傳非 0。這些狀態均為 research observation，不等同 Formal ready 或 credit。

`production_scheduler_allowed=false` 是 legacy artifact 的**消費者資格旗標**：表示該 artifact 不可直接餵給正式 production downstream／training／Formal consumer；它不表示來源查詢排程停用。`run_v2_2_weekly_collection.cmd` 在原 core 成功後預設啟動此 research acquisition，且可用 `BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` opt-out；排程採集狀態另寫入 `weekly_research_status.json`。保留 artifact 既有旗標，不以改旗標表示允許 Formal 使用。

## 隔離驗證

Focused route：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mops_ezsearch_statement_availability.py tests\test_mops_success_response_custody.py tests\test_scheduled_mops_statement_custody.py -q -o addopts=
```

結果：52 passed。涵蓋 gzip／identity encoded entity、官方 no-data、原始失敗 prefix + retry lineage、hash／artifact／metadata tamper、容量限制、固定七日日期、preset 覆寫拒絕、mock 驗證恰好六筆固定 POST、六筆 no-data 正常結束、一筆 HTTP 503 轉 partial failure，以及以假 Python child 執行 weekly wrapper，驗證 core failure 短路、研究 child 失敗不覆蓋 core success、env opt-out 與預設啟用。覆寫負測把 `requests.Session` 設為立即失敗、把 output-root validator 設為立即失敗，再確認 parser 在它們之前報錯且不建立 root；preset capture 測試另以未存在的 `DATA_ROOT` 驗證沒有初始化或建立該路徑。每個測試案例都明確使用 mock session 或 deny-network stub；本測試模組沒有 autouse 的全域網路封鎖 fixture。

語法檢查：

```powershell
.\.venv\Scripts\python.exe -m py_compile data_module\mops_ezsearch_statement_availability.py data_module\mops_success_response_custody.py scripts\fetch_mops_statement_availability.py tests\test_mops_success_response_custody.py tests\test_scheduled_mops_statement_custody.py
```

結果：成功。型態檢查：

```powershell
.\.venv\Scripts\python.exe -m mypy --config-file mypy.ini data_module\mops_ezsearch_statement_availability.py data_module\mops_success_response_custody.py scripts\fetch_mops_statement_availability.py
```

結果：`Success: no issues found in 3 source files`。可核對輸出：

- `output/qa/mops_statement_custody_tests_20261001.log`
- `output/qa/mops_statement_custody_pycompile_20261001.log`
- `output/qa/mops_statement_custody_mypy_20261001.log`

pytest 僅有既有 `.pytest_cache` 權限警告，52 項測試均通過。第一次 override 負測曾因 Python 中 `0 == False` 被錯誤當成未指定，意外進入 CLI 並嘗試六筆網路請求；sandbox 以 WinError 10013 在取得任何 HTTP response 或 body 前拒絕。該次產生的失敗 run 已刪除，未將其重造為 HTTP 收據。比較式已改成明確 `is None`／`is True`，覆寫測試另以 deny-network stub 防護；之後完整 route 使用 mock，沒有再觸網。

## 實際六筆 research capture 驗收

```powershell
.\.venv\Scripts\python.exe scripts\fetch_mops_statement_availability.py --last-complete-taipei-7-days
```

Root 審核唯一命令及當下日期窗後，於台北時間 2026-10-01 執行一次；程序實際選取 2026-09-24 至 2026-09-30。新 run 位於 `output/research/mops_statement_availability/run_20260930T221808809646Z/`，保存 6/6 個 HTTP 200 完整 encoded entity 與 sidecar。唯讀 readback 重驗 raw、metadata、artifact 與 readback receipt hash；artifact SHA-256 為 `sha256:7a50834e63d9429ef23b3716c38cd69d75b6881df1309a25a20fd574fa70f57d`。六筆 query 為 `sii`／`otc` × `F26`／`F27`／`F28`，36 個 event/projection，duplicate、future、invalid、failed、official-no-data 數皆為 0。Capture UTC 為 `2026-09-30T22:18:15.084953+00:00`，早於本次驗收觀測時間；全部輸出維持 `research_only=true`、`formal_oos_allowed=false`、`formal_credit_authorized=false`、`production_scheduler_allowed=false`、alpha 0。逐筆 raw/hash、HTTP metadata、時間窗、品質計數與 readback 驗收記錄在 `output/qa/mops_statement_live_capture_readback_20261001.log`。

該命令此次恰好執行六個 POST。沒有新增／修改 Windows Task，亦未觸碰 Quick 路徑、D 資料根、正式 DB、訓練或 Formal publisher。先前 override 負測曾誤入 CLI，六次連線嘗試均在 WinError 10013 時被 sandbox 阻擋，未取得任何 HTTP response/body；該次診斷 run 已刪除，未重造為原始收據。該事件與本次獲核准且成功保存的六筆 capture 分開記錄。

## 每週接線設計

沿用既有 `baldr-v2-2-weekly-collection`（週日 18:00）呼叫的 `scripts/scheduled/run_v2_2_weekly_collection.cmd`。原 core collector 先跑並保留其 exit result；成功後才依 `BALDR_ENABLE_MOPS_STATEMENT_CUSTODY` 預設執行固定 preset，失敗時只輸出研究 collector exit code，不覆蓋 core 結果。沒有建立或修改 Task，也沒有加入 Quick critical path。正式宣告低頻自然證據仍需按來源政策與 maturity cutoff 另行驗收；本研究 capture 不生成財報數值或成熟度 credit。

# R026 direct daily-price typed receipt evidence QA

- 日期：2026-09-25
- 範圍：`collect_daily_price_repair_receipt_evidence()` 的 direct daily-price receipt namespace；獨立複核既有實作，不改 source、tests 或 inventory。
- 裁定：本 bounded slice 為 `ACCEPTED_SCOPE`。這不代表 R026、其他 revision namespace 或 TMP-ML-01 已完成。

## Frozen source 與測試

| 檔案 | SHA-256 |
|---|---|
| `data_module/ml_daily_price_revision_gate.py` | `A535B11766259B9ED3DE8CD711E04458FF342C51FC9452848C5493E42C27CCFA` |
| `tests/test_r026_daily_price_receipt_same_bytes.py` | `F0397D336866096C20C4C9D0AF23FF11D4DDC7482A9401E94E2A5B307BDC3886` |

複核涵蓋 direct collector 的 `EMPTY`／`PRESENT`、同次 bytes hash/parse、explicit/automatic role identity、cutoff、pending receipt、無效候選不回傳部分 evidence，以及 legacy public guard 相容性。`check_daily_price_source_revision()` 原有 `dict | None` ABI 與 market → session → excluded → direct-receipt guard 順序仍在；typed collector 僅收集 direct receipt namespace，不代替其他 guard。

## 隔離與驗證收據

- 環境：Windows、Python 3.11.9、`sys.platform=win32`；`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest `tmp_path` 均為隔離 TEMP。未讀寫正式資料。
- Fresh TEMP 根目錄：`C:\t\r026_receipt_typed_review_f3b932f5d909`。
- 六檔路由：
  - `tests/test_r026_daily_price_receipt_link_characterization.py`
  - `tests/test_r026_daily_price_receipt_same_bytes.py`
  - `tests/test_r026_source_revision_evidence_contract.py`
  - `tests/test_r026_excluded_daily_price_namespace_red.py`
  - `tests/test_r026_session_revision_evidence.py`
  - `tests/test_ml_pit_year_shard_exporter.py`
- 結果：**89 passed、0 failed、0 skipped**，11.24 秒。pytest log：`C:\t\r026_receipt_typed_review_f3b932f5d909\pytest.log`；SHA-256 `5F9B587172F65FA79AFBE62F98865BF4093820E7E4AC89B1F3B885314C6528A6`。
- Scoped mypy（source 與兩個 direct-receipt 測試檔）：3 files、0 issues；三檔 `py_compile` 通過。
- Root 對本 bounded slice 的 gate 裁定為 `ACCEPTED_SCOPE`，89 passed，未發現 P1/P2。

## 相容性與 evidence 語意

- Legacy public checker 保留原摘要與 `dict | None` 回傳。typed collector 以同一候選掃描／receipt inspector 取得驗證結果：無 receipt 時回 direct namespace 的 `EMPTY`；有效候選時回 `PRESENT` 與有序 evidence files。任一候選驗證失敗時整次呼叫 fail closed，不回傳已累積的部分 evidence。
- Receipt 內容只讀一次 `receipt_bytes`，同一 buffer 用於 JSON parse 與 SHA-256；atomic replace regression 驗證回傳摘要與 evidence hash 仍對應被解析的原始 bytes。Evidence file 的 digest 使用裸 64 字元 hex SHA-256。
- Automatic role 由資料根下 canonical relative path 產生 URL-safe Base64 token；explicit role 由 canonical resolved path 的 SHA-256 產生。Automatic candidates 維持資料根 containment、resolved alias 去重與讀取前後路徑 identity 檢查。這些 role 是 evidence identity，不是來源完整性或跨 namespace 的證明。
- Explicit malformed-slot 行為刻意與 legacy 相異：當 explicit directory 的 `receipt.json` slot 存在但不是 regular file（測試使用同名目錄）時，legacy checker 因 `is_file()` 過濾而回 `None`；typed collector 以 strict slot mode 拋 `DailyPriceSourceRevisionError`，避免把不完整 explicit slot 當成驗證後的空集合。若 slot 是無效 JSON，legacy 與 typed 路徑都 fail closed。
- PIT cutoff 與 pending receipt 測試固定：cutoff 前可回 `PRESENT` evidence；receipt 的 source date 到達決策 cutoff 時拋出 block error。`PRESENT` 表示掃描到並驗證了 receipt evidence，不等同該 receipt 已可用於特定決策，也不取代其他 namespace 的驗證。

## 限制與未宣稱事項

- 兩次 path resolution 可偵測穩定的 target retarget，但不能排除 retarget 後再還原的 ABA；此 slice 不提供檔案系統／SQLite 跨資源原子交易。
- Windows 檔案 symlink 因 `WinError 1314` 無法建立，未計入測試覆蓋；本機實際測的是目錄 junction。Explicit caller-supplied path 的授權政策亦未在本 slice 擴張。
- 沒有測量其他 revision namespace 的完整互相綁定、完整 ML preparation 或模型載入 ABI。R026 與 TMP-ML-01 維持開啟。

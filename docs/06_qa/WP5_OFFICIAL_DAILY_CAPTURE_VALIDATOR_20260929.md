# WP5 官方日行情 capture 唯讀驗收（2026-09-29）

## 範圍

新增獨立唯讀 validator、stdout JSON CLI 與合成負控測試。CLI 只讀取指定的 QA capture、caller 提供的 receipt／manifest SHA-256 pins、決策日與 cutoff；不寫 receipt、QA capture、SQLite 或正式 D，也沒有接入 preflight、pipeline、updater、scheduler 或 learning child。

本驗收使用既有 capture：
`output/qa/wp5_official_daily_capture_20260929_20260929T151827Z_ae0845d9/`。
Receipt SHA-256=`a336af12b89fd9d768a892229105fb30dfcf98528543502b14a61d8d99a43877`；manifest SHA-256=`56c04c0955ee5fcbc3bdff822678a98552a553e5385b42191e091e157f79bf37`。Validator 重新讀回 receipt、manifest 和兩份 raw bytes，核對 hash／長度／readback 欄位、QA path containment、reparse 與單一 hardlink，並檢查來源 URL、HTTP 200、capture chronology、caller cutoff、日期、table schema、列形狀、代碼唯一性及必要代碼的正成交股數。

Caller SHA pins 只保護本機 receipt、manifest 與 raw bytes 的內容一致性；receipt／manifest 的來源 URL、HTTP status、content type 與 capture 時間是未簽章 metadata，不是獨立網路來源或官方發布時間證明。Media type 需精確為 `application/json`，允許合法單一 `charset` 參數，拒絕 `application/jsonp`。程式檢查路徑元件後再開檔，identity 前後核對仍無法消除兩步之間遭並行 rename／junction 置換的 TOCTOU 殘餘；目前未使用 no-follow directory handle 開啟整條目錄鏈。

## 可重跑命令

在 repo root 執行：

```powershell
.\.venv\Scripts\python.exe scripts\qa_validate_wp5_official_daily_capture.py --capture-dir output\qa\wp5_official_daily_capture_20260929_20260929T151827Z_ae0845d9 --expected-receipt-sha256 a336af12b89fd9d768a892229105fb30dfcf98528543502b14a61d8d99a43877 --expected-manifest-sha256 56c04c0955ee5fcbc3bdff822678a98552a553e5385b42191e091e157f79bf37 --decision-date 2026-09-29 --cutoff-utc 2026-09-29T15:30:00Z
```

## 結果

CLI exit `0`、stdout JSON `status=validated`。TWSE `tables[8]` 有 35,673 列、35,673 個唯一代碼，必要代碼 2330 收盤 2,475.00、成交 26,893,348 股；TPEx `tables[0]` 有 11,730 列、11,730 個唯一代碼且 `totalCount=11730`，必要代碼 6488 收盤 945.00、成交 9,157,413 股。Receipt 內 TPEx body 結束時間為兩市場較晚者，因此輸出 `available_at_utc=2026-09-29T15:18:31.0739265+00:00`，早於 caller cutoff `2026-09-29T15:30:00Z`；成功 JSON 亦直接輸出 `cutoff_utc=2026-09-29T15:30:00Z`。Validator 要求每個市場 capture start 與 end 換算台北日期皆等於 caller `decision_date`，另有跨日 capture start/end 負控。

輸出刻意保留 `official_published_at_utc=unknown`、`temporary_closure_negative_coverage=false`、`closure_gate_passed=false`、`formal_pit=false`。這只證明兩個官方全市場回應包含該日正向交易資料列；本地 body read-complete 時間是保守可得時間上界，不是官方發布時間，也不證明完整臨時休市 negative coverage、正常日 runner readiness 或正常交易日真鏈已完成。

## 驗證

- `pytest tests/test_wp5_official_daily_capture_validator.py -q -o addopts=`：22 passed、1 skipped。Skip 是 Windows 權限不允許的實體 symlink 建立測試；另有 monkeypatch reparse 負控通過。
- `.venv\Scripts\python.exe -m mypy data_module\wp5_official_daily_capture_validator.py scripts\qa_validate_wp5_official_daily_capture.py --show-error-codes`：2 source files、0 errors。
- 三個新增 Python 檔 `py_compile` 通過。
- `git diff --check` 通過；Git 提示另一份 WP5 主診斷文件的既有 LF／CRLF 工作樹轉換警告，本報告與本包新增檔案 whitespace check clean。
- pytest 顯示既有 `.pytest_cache` 寫入權限 warning；不影響測試結果。

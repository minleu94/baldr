# WP5 個人同日已觀測行情資格（唯讀 QA）

## 範圍與判讀

`data_module/wp5_daily_chain_preflight.py::run_personal_current_observed_activity` 是獨立的個人研究資格分支。CLI 必須明確指定 `--mode personal_current_observed_activity`；未指定時仍執行原本 strict daily-chain preflight。此模式只讀 seed／隔離證據、年度 TWSE 日曆、可選的官方臨時休市事件，以及由 caller 以 SHA-256 固定的 TWSE／TPEx 官方同日 raw capture；只把 JSON 寫到 stdout，不建立狀態檔、receipt、目錄或 SQLite sidecar，也不呼叫 updater、pipeline、scheduler、recommendation 或 learning child。

年曆必須由既有 verifier 判定有效且 `planned_open=true`，並由 caller 提供年度 cache 檔案 SHA-256。兩市 capture 必須同屬 caller `decision_date`、body-read completion 不晚於實際 `cutoff_utc`，並提供 receipt／manifest SHA-256 pins；validator 會回報兩市 raw body SHA-256、資料列／唯一代碼數與必要代碼 2330／6488 正成交量。Caller cutoff 必須依既有 preflight 的即時鐘檢查：不超前目前 UTC 時鐘 30 秒、距現在不超過 5 分鐘，且台北日期等於 `decision_date`。輸出 `observed_at_utc` 是兩市最晚 body-read completion，`decision_at_utc`／`cutoff_utc` 是 caller 的實際資格判定 cutoff。

輸出頂層狀態只會是 `eligible_personal_research` 或 `blocked`；成功仍固定 `research_only=true`、`formal_pit=false`、`official_published_at=unknown`（同時輸出 `_utc` 別名）、`temporary_closure_negative_coverage=false`、`runner_executed=false`。原始 `day_execution_readiness` 結果原樣保留；缺 closure coverage 或官方 source-time receipt 時仍維持 `blocked`。個人研究 eligibility 不代表 `normal-full-day`、一般 runner ready、正式 PIT、交易授權或真鏈完成。

缺少臨時休市事件 sidecar 時，個人分支將 coverage 標為 `unknown`；若提供且驗證為其他日期的單一事件，也不推論目標日沒有休市。若提供的 sidecar 驗證出目標日休市，個人資格阻擋；無效 sidecar 同樣 fail closed。即使年曆排定開市且兩市場有當日交易列，仍不代表臨時休市 negative coverage 已成立。capture 的 `available_at_utc` 僅採本機 body-read completion 上界，不是官方發布時間，也不構成 Formal PIT。

Bootstrap 與日行情 validator 保留既有 path/reparse/hardlink、hash／readback 與 SQLite `mode=ro`／`query_only` 檢查；新分支另要求年度 cache 與可選 closure sidecar 為單一 hardlink，並比較讀取前後檔案 identity。Path/reparse 檢查與後續開檔之間仍有並行 rename／junction TOCTOU 殘餘；本命令不授權之後的 runner 使用，也不作為完整子程序路徑隔離證明。

## 命令格式

在 repo root 使用一個全新的、已建立完成的 QA root；環境需符合該 root 的 `PROFILE=prod`、`DATA_ROOT`、`OUTPUT_ROOT`、`DB_PATH` 與 recommendation-learning output root。以下 placeholder 必須由本次 QA 輸入的實際路徑／hash 取代，不能沿用其他日期 capture 的 receipt／manifest pins：

```powershell
$env:PROFILE = 'prod'
$env:DATA_ROOT = '<QA_ROOT>\data'
$env:OUTPUT_ROOT = '<QA_ROOT>\output'
$env:DB_PATH = '<QA_ROOT>\data\sqlite\twstock.db'
$env:RECOMMENDATION_LEARNING_OUTPUT_ROOT = '<QA_ROOT>\output'

.\.venv\Scripts\python.exe scripts\qa_wp5_daily_chain_preflight.py `
  --mode personal_current_observed_activity `
  --qa-root '<QA_ROOT>' `
  --decision-date '<當前台北日期>' `
  --observed-at-utc '<實際 UTC cutoff，ISO-8601 且含時區>' `
  --expected-bootstrap-receipt-sha256 '<bootstrap receipt SHA-256>' `
  --expected-working-db-sha256 '<QA working DB SHA-256>' `
  --expected-snapshot-receipt-sha256 '<upstream QA snapshot receipt SHA-256>' `
  --skip-candidate-update `
  --calendar-cache-path '<QA 目錄中的有效 TWSE 年度 cache>' `
  --expected-calendar-cache-sha256 '<年度 cache 檔案 SHA-256>' `
  --capture-dir '<output\qa 中的同日官方 capture 直接子目錄>' `
  --expected-capture-receipt-sha256 '<同日 capture receipt SHA-256>' `
  --expected-capture-manifest-sha256 '<同日 capture manifest SHA-256>'
```

若有可驗臨時休市 event sidecar，可加 `--temporary-closure-path '<QA event sidecar>'`。沒有 sidecar 時不得合成空事件收據。Exit `0` 只代表個人同日已觀測行情分支符合其窄範圍條件；Exit `2` 或 JSON `status=blocked` 表示至少一項條件未滿足。此 CLI 是檢查命令，不會建立持久 preflight receipt。

固定 2026-09-29 capture 可由 `scripts/qa_validate_wp5_official_daily_capture.py` 以其既定 pins 與 `2026-09-29T15:30:00Z` cutoff 做回溯 raw readback；這不等於該日仍是 caller 的「當前台北日」，不能把舊 capture 當成後續日期的個人 current qualification。個人模式每次都要求 cutoff 對應當前台北日期，並以該 caller cutoff 驗證 capture body-read 完成時間。

## 負控與驗證

合成測試覆蓋年度日曆 closed／expired、同日 closure、缺事件及異日事件、跨日／錯日 capture、超 cutoff、future/stale observed time、缺少 caller pin、hash mismatch、HTTP 非 200、缺市場、錯 schema、空表、必要代碼零成交與假 `published_at` metadata。個人分支成功時仍斷言 strict `day_execution_readiness=blocked`，且沒有通用 `ready`／`runner_ready` 欄位。

本包為 QA-only eligibility 判定，未修改排程器或接入任何執行路徑；沒有執行 updater、runner、scheduler、learning child，沒有讀寫正式 D。測試合成 bytes 僅在 pytest `tmp_path` 中使用；沒有新增實際行情、捏造未來行情、研究固定成本績效或自然績效結論。

## 本包驗證

- `pytest tests/test_wp5_personal_current_observed_activity.py tests/test_wp5_daily_chain_preflight.py tests/test_wp5_official_daily_capture_validator.py -q -o addopts= -p no:cacheprovider`：**57 passed、1 skipped**。Skip 是 Windows 環境不允許的實體 symlink 建立測試；reparse 負控另有 monkeypatch case。
- `.venv\Scripts\python.exe -m mypy data_module\wp5_daily_chain_preflight.py data_module\wp5_official_daily_capture_validator.py scripts\qa_wp5_daily_chain_preflight.py --show-error-codes`：3 source files、0 errors。
- 上述 5 個變更 Python 檔 `py_compile` 通過；`git diff --check` 通過。
- 固定 9/29 capture 以 dedicated validator、固定 receipt／manifest pins 與 15:30Z cutoff 回溯讀回 exit `0`／`status=validated`；available time `15:18:31.0739265Z`。此為 capture validator regression check，非 current-day 個人資格或 runner 驗收。

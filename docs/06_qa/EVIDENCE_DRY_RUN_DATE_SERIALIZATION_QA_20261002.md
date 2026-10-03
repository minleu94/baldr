# Evidence dry-run 日期序列化 QA（2026-10-02）

## 範圍與結論

修復 Evidence recommendation event hashing 遇到 typed `date` 的例外。變更限於 legacy recommendation importer 的兩個具名 metadata 欄位與對應回歸測試；未修改共用 canonical JSON serializer、Evidence DB、正式資料或排程設定。

## 執行證據

- 2026-10-01 05:15 PDT 的 `evidence_pipeline_dry_run` log 以 `TypeError: Object of type date is not JSON serializable` 結束。Traceback 經過 `EvidenceCaptureService._sample_event`、`EvidenceEventService.build_event_hash`，最後落在 `research_run_dtos.canonical_json` 的 `json.dumps`。
- 最新自然 dry-run 仍是 2026-10-02 05:15 PDT：`pipeline_exit_code=0`、`pipeline_summary_available=true`、`events_seen=1749`，並已產生 `20261002_evidence_pipeline_dry_run.md`。整體狀態仍為 `degraded`、有 8 個 warnings。此筆成功表示該次資料沒有觸發例外，不代表 legacy typed-date 路徑已安全。
- `RecommendationEvidenceImporter._consumer_result` 在 legacy read model 路徑直接傳回 `legacy_result`；payload builder 曾原樣把 `rec.eligible_universe_date` 放入 `metadata`。該欄位的決策型別是 `date | None`。Canonical execution 投影路徑已有 `isoformat()`，所以兩條來源路徑的差異可解釋 10/02 通過、舊 legacy payload 仍可觸發錯誤。
- 最小鏈路回歸透過 legacy importer 建立 typed `date` 與 timezone-aware `datetime`，再交給 `EvidenceCaptureService.capture()` 計算 sample event hash。測試同時以 ISO 字串建立對照，兩者 hash 完全相同；`datetime` 的 `+08:00` offset 原樣保留。未知 `object` 仍由原 serializer 拒絕，沒有加入通用字串 fallback。

## 修正與契約

- `metadata.eligible_universe_date`：只對 exact `date` 呼叫 `date.isoformat()`；`datetime` 不會被當作日期截斷。既有字串保持原樣。
- `metadata.source_created_at`：只對 exact `datetime` 呼叫 `datetime.isoformat()`，保存輸入時區 offset；不轉成 UTC，也不改動既有字串。
- 其他值不作通用轉字串。原 JSON encoder 仍負責拒絕不支援的型別。
- 因為既有合法字串輸入的 payload bytes 不變，既有 event hash 保持不變；回歸測試直接比較 typed 欄位與原 ISO 字串欄位的 hash。

## 驗證

- `pytest tests/test_recommendation_evidence_importer.py tests/test_evidence_capture_service.py -q -o addopts=`：24 passed。pytest cache 寫入警告為本機 `.pytest_cache` 權限問題，不影響測試結果。
- `py_compile app_module/evidence_event_importers.py tests/test_recommendation_evidence_importer.py`：通過。
- `mypy app_module/evidence_event_importers.py`：通過，1 個來源檔無型態錯誤。
- `git diff --check`：通過。

## 備份與待驗

修改前原始 bytes 保存在忽略的 `output/qa/integration_20261002/evidence_before/`：

- `evidence_event_importers.py.before` — SHA-256 `4c4b5ff7bd77a97e30469c7614ebedac713560bd339c9f6b680ea0e277f21092`
- `test_recommendation_evidence_importer.py.before` — SHA-256 `a0116ca3fae0f50e5f3f9e9d8ba5904162bfe34a66a17f099b5d11fd425f2a9a`

本次只執行隔離 pytest、型態與語法檢查，沒有啟動 producer、Task Scheduler task 或寫入正式 Evidence DB。修補後的受控 dry-run、report／summary 及下游讀回仍待 root owner 執行與驗收；10/02 自然 run 是修補前證據。

# Security Lifecycle Contract QA — 2026-09-15

## 結論

PASS（受控新增 helper/schema 的 bounded QA）。本次只驗證 `data_module/security_lifecycle_contract.py` 的解析、狀態投影、create-only 寫入與 readback；尚未接入 L 的 PIT source producer/reader、正式 rule source、scheduler、Manual 或評分管線，也不會因此產生正式信用、carry 或自然日交易日判定。

## 變更範圍

- 新增 `data_module/security_lifecycle_contract.py`：MOPS 原始回應的 typed contract、fail-closed parser、as-of state projector、create-only writer/readback。
- 新增 `tests/test_security_lifecycle_contract.py`：16 個單元測試。
- 新增 `tests/fixtures/security_lifecycle/`：縮減後的測試 fixture；不是官方原始檔的逐位複製。fixture 限制另見該目錄的 `README.md`。

Contract 明確分離：

- `source_available_at`：MOPS response 內的 server timestamp。
- `available_at`：client 可用時間，不早於 client capture 與所有 raw reference capture time。
- `captured_at`：client 完成捕獲的時間。
- `historical_research_replay` 與 `prospective_capture` scope。
- lifecycle phase、market tradability、history warmup、score readiness。

`observed_sessions` 若只提供 date/string window，不視為 caller 已驗證的官方交易日；要標記 warmup 完整，必須由 caller 提供 successor 自身價格 lineage、官方交易日確認與去重後的 typed evidence。helper 不建立交易日曆，也不實作 T-1/features。

## 官方 MOPS 原始回應驗證

來源為官方 MOPS endpoint：

- list：<https://mops.twse.com.tw/mops/api/t05st01>
- detail：<https://mops.twse.com.tw/mops/api/t05st01_detail>
- browser page：<https://mops.twse.com.tw/mops/#/web/t05st01>

實際使用的原始檔保留於本機 Temp，未複製為 repo fixture：

| 類型 | 原始檔 | server timestamp（UTC） | SHA-256 |
|---|---|---|---|
| list | `mops_api_t05st01_5371_115.json` | `2026-09-15T18:05:49Z` | `sha256:9744c8826b616c1eb115c454ed3a70d0716dcef2e697857a7f11b6a31c7db203` |
| detail page 1 | `mops_api_t05st01_detail_5371_1150729_1.json` | `2026-09-15T18:06:18Z` | `sha256:4c41e149e5ab84e63bd7578d46e2a77512634668cce1183c739b66e89241202a` |
| detail page 2 | `mops_api_t05st01_detail_5371_1150729_2.json` | `2026-09-15T18:06:46Z` | `sha256:28e9eef83a23bf8b6e9c57fa20550d83a8085a91fd90a8dc28fecd0b1f27aa48` |

Temp 目錄：
`C:\Users\archi\AppData\Local\Temp\twse-5371-event-verification-20260915\`

以 `historical_research_replay` scope 執行 parser → create-only contract → readback：

- client capture：`2026-09-15T18:34:33.265060Z`
- `source_available_at`：`2026-09-15T18:06:46Z`
- `available_at`：`2026-09-15T18:34:33.265060Z`
- contract：`security_lifecycle_contract_research_replay.json`
- contract hash：`sha256:4762595b5454f7d0b196783453eb45aa6b727f1a2ec43542a9fbf5b199887444`
- event hash：`sha256:2fa33cbc331f7b26795a01210a59730eee19506cf1cfabb7c3985b6d45e74686`
- readback：`True`

解析結果與官方事件一致：5371 → 3718、predecessor→successor ratio `1:1`、換發普通股 `390,981,110` 股；last trade `2026-08-21`、halt `2026-08-24`、termination/conversion/listing `2026-09-03`。parser 從原始 response 推導 identity、ratio 與日期，不依賴上述事件的 production constants。

## 負向與安全邊界

已覆蓋：

- predecessor/successor symbol tamper。
- 明確 predecessor→successor ratio tamper 與 declaration conflict。
- conversion/listing date mismatch reject。
- future announcement、capture earlier than source availability、future effective date。
- duplicate observed session、pre-listing/out-of-window session、future session。
- bare date-only window 不宣稱 warmup 已驗證。
- required warmup 參數不得使用 float。
- contract raw response hash tamper 與 create-only conflict。
- 尚未達 successor listing date 時，不會提前回報 successor active。
- successor listing 後，market tradability、history warmup 與 score readiness 仍分開；即使 caller evidence 足夠，也只回報 `HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER`，不直接產生可評分結論。

## 驗證命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_security_lifecycle_contract.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy data_module\security_lifecycle_contract.py tests\test_security_lifecycle_contract.py
.\.venv\Scripts\python.exe -m py_compile data_module\security_lifecycle_contract.py
```

結果：`16 passed`、`mypy Success: no issues found`、`py_compile` 成功。pytest 僅有既有 `.pytest_cache` 權限 warning，不影響測試結果。

## 後續交接邊界

L 線若要接續，應由既有 OfficialTradingCalendar、T-1/features 與正式 PIT source contract caller 產生 `SuccessorSessionEvidence`，再決定是否將 contract 納入其既有 reader/consumer；在本次 QA 驗證期間，本線未修改那些檔案。本段不宣告後續版本控制狀態。

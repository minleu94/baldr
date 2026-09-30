# 排程基本面 bootstrap 與研究候選驗收（2026-09-30）

## 結論

已從保存的 TWSE／TPEx 2026-08 官方回應重建完整 1,978 列研究 candidate，並以正式既有資料做唯讀 no-apply preview。Candidate 的 row/key/schema/Decimal/source hashes 與 capture-bound availability 均通過；較早的 1,841 列 candidate 少掉 137 個 API-only keys，原因是舊候選只取舊 frozen baseline 的 key 交集。新 candidate 保留完整雙市場 scope，未改 1,841 列來源、正式 availability mapping 或 SQLite。

這次 `ready_for_apply=true` 只表示機械 preview 可解析、合併無衝突，不能作為正式 writer 的授權。TWSE／TPEx OpenAPI 的欄位頁未明示 API 金額單位；目前沒有 hash-bound 的來源與單位接受證據，因此 `owner_acceptance=false`、`formal_apply_authorized=false`，研究 candidate 不可正式套用。已修復兩層 apply 路徑，research-only candidate 在建立備份、開啟正式 DB、修改 mapping、寫 journal/evidence 前即被拒絕；合法 legacy MOPS route 維持原有 apply 路徑。

## 保存的官方來源與完整 scope

唯讀 source/candidate/preview 材料位於：

`C:\Projects\PythonProjects\technical_analysis\.tmp_fundamental_full1978_20261001_lineage02\`

來源原件由既有 2026-09-30 capture 複製，未重新連網：

| 檔案 | 列數／bytes | SHA-256 |
|---|---:|---|
| `source/twse.json` | 1,086 rows / 606,355 bytes | `83480ff80b337e936821b45e2cef1c2a48ba92f112fb3e31027501810e8bccf5` |
| `source/tpex.json` | 892 rows / 496,547 bytes | `f00e3fdd7060db0db943b79dc53d732df940d038ef208a1b075363e06660bd92` |
| `twse_tpex_openapi_monthly_revenue_2026-08_full_1978.csv` | 1,978 rows / 616,793 bytes | `3903194a0409d62b9288d86e54b11410b2d4fead37b1fdd746d97f4cc6726df7` |
| `availability_capture_bound_full_1978.csv` | 1,978 rows / 516,426 bytes | `165bb200427667573c60e1cfccf70ff51c0e0b9fcacbbde4bfaad5d9960ea915` |
| `full_source_scope_manifest.json` | 2,807 bytes | `94a525a370941736751a840cf0ba37c3f8042931590403c726f7f6d485fcdd90` |
| `candidate_manifest.json` | 10,105 bytes | `a53254a8f27a03da737bf2d19973092d5025425f28dba45fc6d29ba7fd9164fa` |
| `baseline_scope_diff_137.json` | 84,723 bytes | `96b14a7f9f0c4719e9d2c19a893eb761537b8029b2a1b83826a078c9854c311b` |

TWSE response completion 為 `2026-09-30T08:56:44.077872Z`，TPEx 為 `2026-09-30T08:56:51.265713Z`，即台北時間 2026-09-30 16:56:44／16:56:51。候選產生並完成 readback 的時間是 `2026-09-30T21:33:55.065722Z`（台北 2026-10-01 05:33:55）。Availability 的 date-only 規則使用 source capture 的台北日期再加一天；candidate completion time 另行記錄。資料沒有被回填到 2026-08 的可用日或舊 baseline cutoff。

137 個 API-only key 全都存在於保存的官方 TWSE+TPEx response；它們只因舊候選的 baseline-key intersection 被漏列，並非股票 eligibility 排除。新完整 scope 為 TWSE 1,086 + TPEx 892、合計 1,978；venue/natural keys 唯一、period 全為 2026-08。此 composite 是 manifest 明確允許的雙 venue scope；未知來源或同 key/venue 的衝突仍必須 fail closed。

Decimal QA 保留來源數值字串，沒有轉換或四捨五入。五個金額欄位各有 1,978 個有限 Decimal、沒有空值或非有限值；三個百分比欄位有 9／6／3 個空值，非空值均有限。API schema 本身未清楚聲明金額單位。官方資料集與 API 入口列於 [TWSE 月營收資料集](https://data.gov.tw/dataset/18420)、[TPEx 月營收資料集](https://data.gov.tw/dataset/56510) 和 [TWSE OpenAPI](https://openapi.twse.com.tw/)；欄位旁證不足以取代 API unit contract 與來源 owner acceptance。

## No-apply 與正式適用界線

唯讀 preview receipt：

`C:\Projects\PythonProjects\technical_analysis\.tmp_fundamental_full1978_20261001_lineage02\recovery_noapply.json`

Preview 顯示完整 scope、接受 1,978 列、availability 新增 1,978 列、舊 mapping 1,832 列、合併後 3,810 列、衝突 0；backfill 正規化 1,978 列，duplicate、unmatched、invalid 都是 0。正式 mapping 的 preview 前後 SHA 均為 `ea6c0c5651e94f605dc10ac8f4cc36803193e8d3aad0db63a7b9f31d72728f7e`。Preview 沒有套用 mapping、資料庫、backup、journal 或 evidence。`recovery_noapply.json` SHA-256 為 `43605475ddce56060aea4b227da78fc66dcb2ac993de6ee968a2dddc0da74e1e`。

Source contract reader 只接受 manifest root 下的安全相對路徑；讀 manifest/raw 前檢查 root 與祖先不得為 symlink/junction、單一 hard link、一般檔、16 MiB 上限，使用 max+1 bounded read 並比對前後 file identity/size/mtime/link count。Source contract 驗證 TWSE 與 TPEx 原始 response、capture receipt、candidate snapshot、venue row counts、natural keys 和 hash lineage。

正式 apply 需要分開看兩個狀態：

- `ready_for_apply=true`：mechanical preview 通過，可供 review。
- `formal_apply_eligible=true`：來源 lane 已經有 writer 接受的正式資格；本次 OpenAPI research candidate 為 `false`。

目前沒有可核准執行的正式 apply command。Recovery orchestrator 在任何 backup reservation、mapping merge、DB open/write、journal/evidence 前擋下機械 ready 但 formal-ineligible 的 OpenAPI research candidate，CLI `--apply` 會以非零狀態結束。Direct SQLite writer 同樣在建立 backup 或 connect DB 前檢查 eligibility。Legacy MOPS 靜態 snapshot 的既有測試路徑仍可套用。之後若要接受 OpenAPI source，需先建立獨立、hash-bound 的 source/unit acceptance artifact 與 validator；一般 `--confirm` 字串不構成該證據。

## MOPS statement availability 診斷

既有保存診斷位於：

`C:\Projects\PythonProjects\technical_analysis\output\qa\mops_fundamental_retry_20261001_run01\`

範圍為 SII F26/F27/F28、2026-08-01 至 2026-08-31、7-day date windows，15 個 query 全部成功，產生 3,150 events；duplicate/future/invalid/failed query 都是 0，最大單窗 703 rows。實際每 query 僅一次 attempt；CLI 上限 `--query-retries 1` 表示最多額外一次、即最多兩次 attempt/query 與 30 個 POST。保存 capture time `2026-09-30T21:29:42.203937Z` 等於台北 2026-10-01 05:29:42。

這份既存 legacy artifact 的 query manifest 維持舊 ABI：保存 canonical response JSON SHA，但沒有每次成功 HTTP response 的原始 entity bytes、HTTP headers、實際完成時間與 per-window raw lineage。它可作 parsed research event evidence，不能描述成完整 raw custody；舊 `invalid_response` 缺少 body，不能倒推舊失敗必定由 response cap 引起。新的成功 body sidecar 工作由另一個受控變更負責，未回填此舊 artifact。

## 日常 candidate-only producer

Quick daily runner 的 opt-in collector 僅在所有 core phases、technical publication receipt、terminal history/status 完成後才釋放 heavy-chain reservation，再啟動較低優先序研究 child。研究結果寫入 run-id 專屬 create-only receipt，不重寫可能已被另一個 Quick run 更新的 `latest_status.json`；child failure 不改 core status。`.cmd` 預設啟用，設 `BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE=0` 可停用；Python caller 的新參數仍預設關閉。

Collector 固定對官方 TWSE/TPEx endpoint 各發一次 GET，timeout 30 秒、每 venue 最多 8 MiB、整體 response 最多 16 MiB；repo candidate root 初次需有 16 MiB input budget + 16 MiB reserve，每次 artifact write 都再以實際 incoming bytes檢查 reserve，並以 32 MiB total output、CSV/metadata per-file caps、create-only 與 no-linked-parent 限制保護輸出。候選 snapshot/availability/source receipts 僅寫 `output/fundamental_research_candidates/<unique-run-id>/`，不寫正式 CSV、正式 DB 或 Task Scheduler。Date-only availability 不早於 source capture 的下一個台北日，candidate build/readback completion 另行記錄；units/source acceptance 預設 false。

CLI 命令為：

```powershell
.\.venv\Scripts\python.exe scripts\capture_monthly_revenue_research_candidate.py
```

依 reviewer 核准，daily candidate CLI 共執行兩次。第一次 sandbox 執行時，TWSE、TPEx 連線均被 Windows `WinError 10013` 拒絕，沒有 response body；失敗 receipt 保留在 `output/fundamental_research_candidates/20260930T221723106457Z-3a03ee312d754d0a94cdf300740718d4/`，status 為 `failed`，兩個 request attempt 分別記錄 `2026-09-30T22:17:23.330103Z` 與 `2026-09-30T22:17:23.697568Z`。該次 Python 子程序的原始 stdout／returncode 未留存，故不把工具層執行回報稱為 CLI exit code；目前 CLI `main()` 對非 `captured` 結果明確回傳 2。依 reviewer 對同一精確 CLI 的核准升權後，第二次執行成功 exit 0；新 run 使用另一個唯一路徑，前次失敗資料沒有覆寫。

成功 run 位於 `output/fundamental_research_candidates/20260930T221743808050Z-4148c176e04b4b958b305ed9e971b987/`。TWSE HTTP 200，1,086 rows／606,355 bytes，SHA-256 `83480ff80b337e936821b45e2cef1c2a48ba92f112fb3e31027501810e8bccf5`，source response completion `2026-09-30T22:17:45.393277Z`；TPEx HTTP 200，892 rows／496,547 bytes，SHA-256 `f00e3fdd7060db0db943b79dc53d732df940d038ef208a1b075363e06660bd92`，completion `2026-09-30T22:17:48.275856Z`。兩邊 period 都是 11508（2026-08），response encoding 為 identity；candidate snapshot 與 availability 各 1,978 rows。Candidate manifest 在兩份 raw readback 與完整 snapshot/availability/scope readback 成功後才寫成 success；capture status 與 candidate manifest hash 一致。

該次 snapshot SHA-256 為 `147d1695f0e9241d9ca6a2fc47ca7535a8280671dd16356facf248fb1540ce63`；availability 為 `dece4ac90dcfc2ef516a812f8164b6d5f47aa3e8d2771afc7542ac1aed4d50db`；scope manifest 為 `7b3aadf6eb2d152e4ffc6781415c9a822b0cb106d75bc27438d0878506893605`；capture receipt 為 `fdc3903102c42dd0b89e1fe9a4d43902886831ee0280861cf8eb2f062a2f3be8`；candidate manifest 為 `3db932cbacd6ea3a7c03b1c957cf1cf97c72efca3e536f07491f57ecfadd7a77`。Candidate完成時間為 `2026-09-30T22:17:48.394676Z`（台北 2026-10-01 06:17:48）。Source capture 當日是台北 2026-10-01，因此 date-only availability 為次日 `2026-10-02`，沒有用機器時區或公告月份回填。

對該 live candidate 做唯讀 backfill plan read：1,978 normalized records、diagnostics 0、`ready_for_apply=true`、`formal_apply_eligible=false`。`owner_acceptance`、`formal_apply_authorized`、`formal_unit_contract_accepted`、`historical_pit_credit` 均為 false；數值轉換為 none。所有 raw/manifest/snapshot/availability/status 檔皆一般檔、link count 1，candidate status 的 manifest SHA 與實際 manifest bytes 相符；執行 plan 前後 source bytes SHA 無變。執行後唯讀檢查正式 availability mapping `D:\Min\Python\Project\FA_Data\meta_data\monthly_revenue_availability.csv` 仍為先前 no-apply hash `ea6c0c5651e94f605dc10ac8f4cc36803193e8d3aad0db63a7b9f31d72728f7e`。日常候選命令不開啟正式 DB，也不寫 D 槽。

這個命令不接受 apply/交易參數，不會觸發 Quick 主資料工作、Task Scheduler、模型訓練或 formal apply。Actual run 的 source receipt/status、candidate manifest、raw bytes 與 generated CSV 都留在上述 repo output path，可用 saved SHA 與 CLI stdout 核對。

## 驗證與限制

Focused route：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_monthly_revenue_backfill.py tests\test_monthly_revenue_recovery.py tests\test_monthly_revenue_research_candidate.py tests\test_scheduled_data_update_runner.py tests\test_scheduled_cmd_scripts_no_confirm.py -q -o addopts= --basetemp .tmp_monthly_daily_collector_route_qa_v4
```

結果：`86 passed, 2 skipped`。兩個 skip 是 Windows 建立 directory symlink 的權限不可用；程式仍有 linked-path 檢查，以及 bounded read/fingerprint 的負向測試。Pytest 另有 `.pytest_cache` 寫入權限 warning；測試結果仍完整。對六個變更 source modules/scripts 執行 `py_compile` 與 `mypy`：成功，`Success: no issues found in 6 source files`。

Direct daily collector 的實際 network capture 已完成並通過 raw／manifest／snapshot／availability readback；仍待下一次自然 Quick wrapper run 驗收同一次 core execution 後產生的 nested child receipt。OpenAPI candidate 未 apply 到正式資料。研究資料品質、readiness 與正式來源接受是三個不同判定，不可互相替代。

## 實作定位

- `data_module/monthly_revenue_backfill.py`：source contract reader／validation 與 direct apply eligibility gate（約 391、928、1123 行起）。
- `data_module/monthly_revenue_recovery.py`：recovery plan 分列 mechanical/formal eligibility；OpenAPI research apply 在任何寫入前拒絕（約 53、158、197 行起）。
- `data_module/monthly_revenue_research_candidate.py`：雙 venue candidate、capture-bound availability、per-write reserve/output caps、manifest readback-success gate（約 125、343、900、914 行起）。
- `scripts/scheduled/run_daily_data_update_quick.py`：terminal core publication 完成後才 release 並跑研究 child，child receipt create-only（約 1420、1506、1526 行起）。

# ML raw PIT 來源修訂與前瞻候選 QA（2026-09-30）

## 結論

9/30 05:05 的 `ml_raw_pit_refresh` 失敗不是容量等待：既有正式修訂鏈為 `applied`，歷史 PIT guard 拒絕來源時間倒填；child 回傳 exit 2，舊 wrapper 把它歸成 `raw_pit_builder_failed:2`。原始 D 收據保留在 `D:\Min\Python\Project\FA_Data\output\scheduled\ml_raw_pit_refresh\latest_status.json`，本次未重跑 Task 或正式 builder。現在 wrapper 會將同一 guard 的拒絕明確標成 `blocked_source_revision`，保留 exact error 和原 revision 收據；舊 status 不回寫。

驗證的來源修訂為 `20260923_run01`，DB `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`，日期範圍 `2014-01-02..2026-09-23`；`revision.json` SHA-256 `801375e37a6f3c387d80178c775bfa73a1bf21ec914e73f7a014233078c700d2`，完整鏈摘要 `7dc35af66b3ca033f47d172ff52cdea9d21b95a1a94c2ed57fb649624a508bc4`。`inspect_market_revision_state()` 不接受 cutoff，只驗證 DB identity、鏈結、bytes hashes、狀態及日期範圍；原 `collect_market_revision_evidence()` 仍按實際 cutoff 阻擋歷史 PIT（`data_module/formal_market_revision.py:198-343`）。

## 前瞻證據與排程接線

合法生產端是每日 Quick updater：`scripts/scheduled/run_daily_data_update_quick.py:963-993` 更新 TWSE/TPEx；TWSE 原始回應與 custody 由 `data_module/data_loader.py:627-643` 保存，TPEx 由 `data_module/tpex_daily_price_source.py:117-187` 保存。新增 collector 只讀這些正式 custody，檢查 raw/receipt bytes hashes、API 日期、實際 price rows/schema/count、兩市場完整性與 `available_at <= 真實 observed_at`，再 create-only 複製到隔離 candidate；不呼叫網路、不寫 D DB/正式 pointer，也不產 features、labels 或 model input（`data_module/ml_prospective_daily_price_capture.py:155-238,343-479,824-1075`）。

9/30 no-apply preview 驗得 TWSE 1,095 rows、TPEx 877 rows，兩者 `available_at` 分別為 `2026-09-30T08:07:47Z`、`08:07:51Z`。raw SHA 分別為 `5f4bb47a32d90d7f6ded896bac70174bb3267148f53f5bb016f72d1ebd393689`、`ee80854bd773c12237953e3a700fc762b4b88c52de09f9ffa6027ee67a16a311`。候選 `089c28f7c037af83c41e99e28bc6c5ccb85ecf215cb52cb65ae7fd7c889f5d81` 的真實 `candidate_available_at=2026-09-30T20:45:36.956214Z`，重讀為 `already_captured`；manifest SHA `226f222c7ed32ed3df75f5918f449874354c60d3d8cb400e2d2126c275ff9b49`，capture receipt SHA `677d45d40b0c7c573c7196ed4904fe17fd05db2b0a69ed6b51c3f20b2dd23123`。此次驗收候選在 repo `output/qa/ml_prospective_daily_price_candidates/2026-09-30/<candidate_id>`；正式 runner 固定使用 `output/ml_prospective_daily_price_candidates`，兩者皆位於 repo 的 ignored `output/` 下。容量上限 128 MiB、保留 16 MiB；本候選輸入 5,141,016 bytes、估算 7,238,168 bytes。候選的 `historical_pit_eligible`、`formal_source_contract_eligible`、`formal_oos_allowed`、`formal_credit` 皆為 false。

`run_ml_raw_pit_refresh.py` 在 fresh core proof 後、`skipped_current` 或來源修訂 block 前執行 collector（`scripts/scheduled/run_ml_raw_pit_refresh.py:224,1410-1509`）；失敗會寫 status/log，但不能略過既有 guard。Python CLI 預設不改舊呼叫 ABI；排程 `.cmd` 預設開啟，僅 `BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE=0` 關閉（`scripts/scheduled/run_ml_raw_pit_refresh.cmd:15-16`）。程式已接線，仍待下一次合法 scheduled runner 執行確認正式候選根每日累積；本 QA 沒有觸發該 Task。自然排程觸發也不等同正式自然 authority：D 上 decision capture 最新狀態為 `eod_research/research_only=true/preopen_authority=false/natural_authority=false`。

## 時間界線與後續正式 gate

9/30 08:30 台北 cutoff 是 `00:30Z`，晚於此 cutoff 才可得的當日 raw 不可回填；本次 raw `available_at` 已是 `08:07Z`，candidate 到 `20:45Z` 才完成，因此不符合 9/30 cutoff。10/1 08:30 台北（`00:30Z`）僅是後續 consumer eligibility 計畫：候選 timestamp 早於它，但尚未做 cutoff 驗收，也沒有 owner source-contract acceptance 或正式 credit。

最小後續順序：①維持 `.cmd` 前瞻候選接線，只累積每次真實 custody；②由 source owner 接受明確的來源契約（venue、日期、receipt/bytes hashes、available-at 與 DB revision 綁定），再以 `20260923_run01` revision/hash 驗證完整歷史重建輸入；③完成 revision-aware dataset/rebuild 與 source-quality、pointer readback QA 後，才可重跑 `scripts/scheduled/run_ml_raw_pit_refresh.cmd`；目前舊 raw builder 仍會被 revision guard 阻擋，不可只靠改 status 宣稱解決。正式 D 重建前，需 capacity 預檢：至少保留 200 GiB，scheduled persistent 上限 35 GiB、temporary peak 40 GiB，持有共用 `.ml_heavy_chain.lock` 並確認 Direct/OOC 不競爭（`data_module/ml_storage_capacity.py:37-58`）；本次沒有進入此重建。

前瞻 candidate 只是 accumulator，不等於 mature。shadow gate 要求 5/10/20/60 trading-day horizons、至少 20 個 shadow days，且每 horizon 至少 20 筆已成熟觀測（`data_module/prospective_shadow_maturity.py:36-38,288-321`）；各筆必須先跨過對應 horizon 並通過 source/cutoff 驗證，之後才另行 owner review formal/OOS eligibility。

## 驗證

53 項基線（inspector、collector、raw guard）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ml_prospective_daily_price_capture.py tests\test_r026_market_revision_evidence.py tests\test_scheduled_ml_raw_pit_refresh.py -q -o addopts= -p no:cacheprovider
```

排程接線整合共 73 項（含後續 peer-review 修補）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ml_prospective_daily_price_capture.py tests\test_r026_market_revision_evidence.py tests\test_scheduled_ml_raw_pit_refresh.py tests\test_scheduled_cmd_scripts_no_confirm.py -q -o addopts= -p no:cacheprovider
```

只讀 peer review 發現 candidate root 若是受保護 source/DB root 的祖先會漏擋；collector 現在會拒絕 ancestor 與 descendant 兩向重疊，保留預設 candidate path，並新增 ancestor-root 負測。修補後 focused ML/revision/raw route 為 58 passed，接線整合路由為 73 passed。獨立接線測試為 raw runner 4 passed、cmd 1 passed。四檔 `py_compile` 與 `mypy` 均通過（mypy：`Success: no issues found in 4 source files`）：

```powershell
.\.venv\Scripts\python.exe -m py_compile data_module\formal_market_revision.py data_module\ml_prospective_daily_price_capture.py scripts\capture_ml_prospective_daily_prices.py scripts\scheduled\run_ml_raw_pit_refresh.py
.\.venv\Scripts\python.exe -m mypy data_module\formal_market_revision.py data_module\ml_prospective_daily_price_capture.py scripts\capture_ml_prospective_daily_prices.py scripts\scheduled\run_ml_raw_pit_refresh.py
```

可核對紀錄位於 `output/qa/scheduler_ml_raw_repair_20260930/`：`pytest.txt`、`pytest-integrated-peer-review-fix.txt`、`pytest-ml-peer-review-fix.txt`、`pytest-schedule-integration.txt`、`pytest-cmd-integration.txt`、`py_compile-integrated.txt`、`py_compile-peer-review-fix.txt`、`mypy-integrated.txt`、`mypy-peer-review-fix.txt`、`source_preview.json`、`candidate_readback.json`。本次只有 D 唯讀 preview 與隔離 repo candidate 寫入，沒有正式 D 寫入、raw rebuild、Direct/OOC、訓練或 Task 執行。

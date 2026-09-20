# Natural Shadow Weekly Evidence Audit（2026-09-20）

本次查核區分 V2.2 weekly collection 與 ML natural shadow evidence。兩者不是同一份週報，也沒有把研究觀測誤當成自然成熟績效。

## 實際排程與產物

- 查核時鐘：UTC `2026-09-20 05:07`；Pacific 為 `2026-09-19 22:07`；台北為 `2026-09-20 13:07`。
- `\baldr-v2-2-weekly-collection` 為 enabled/Ready；上次 `2026-09-13 18:00` Pacific，結果 `0`；下次 `2026-09-20 18:00` Pacific，即台北 `2026-09-21 09:00`。它是 V2.2 review sidecar，不是 natural learning weekly gate。
- V2.2 最近產物在 `D:\Min\Python\Project\FA_Data\output\scheduled\v2_2_weekly_collection`，涵蓋 `2026-09-07` 至 `2026-09-13`，狀態為 `pending_human_review`、`human_approval_required=true`、`write_intent=false`；這不是本週自然成熟報告。
- `\baldr-ml-allocation-copilot-daily` 每日執行；最近一筆自然 shadow 狀態位於 `D:\Min\Python\Project\FA_Data\output\scheduled\ml_allocation_copilot\natural_shadow_pruning_evidence\weekly\2026-W38\asof_2026-09-18_evidence_dc6ac6b7a21c24f8.json`。W38 有 `29` 筆 pending、成熟 `0` 筆，all-horizon gate 的 h5/h10/h20/h60 都是 `0`。
- `\baldr-ml-allocation-forward-daily` 的 sidecar 位於 `C:\Projects\PythonProjects\technical_analysis\output\v4_ml_daily_derived_shadow_real_v2\scheduled\ml_allocation_copilot\shadow_evidence_collector\shadow_evidence.sqlite`；實體讀回只有 `1` 筆 observation、`2` 筆 outcome，尚無合法自然 credit。

## 原因與判讀

W38 的 29 筆不是單純「週末沒有交易所以尚未產生」。現有 producer 在 `app_module/ml_allocation_shadow_evidence.py` 以 research-only T-1 paper ledger 產生 observation，明確寫入 `promotion_day_credit_allowed=false`，並保留 `formal_rule_champion_weight_snapshot_missing` 與 `formal_sector_thesis_health_context_missing`。一般 daily caller `scripts/run_daily_ml_allocation_orchestration.py` 也沒有為這個 research lane 產生自然可用的 observation availability clock，因此 collector 會保留 `observation_available_at_missing`。

Outcome maturity 仍要求 h5、h10、h20、h60 全部完成；已有 partial h5/h10/h20 只能供觀測，不能計入 matured。h60 尚未完整屬於時間／資料成熟缺口，但 credit false、availability 缺件與 formal custody 缺件是工程／契約阻擋，不能標成正常等待。

Forward lane 雖已由排程產生 sidecar，實體 observation 同樣標為 `research_only=true`、`promotion_day_credit_allowed=false`，且沒有 promotion reference/authority。因此它現在只作 weekly diagnostic companion，不能補進 primary cohort 或改變 eligibility。

## 本輪修補邊界

- `ml_module/natural_shadow_pruning_evidence.py` 現在輸出 observation classification：`time_wait_only`、`contract_blocked`、`blocked_unknown`、availability `missing/future/unknown`，並在 identity cohort 混合時重新計算分類，避免成熟樣本搬入 pending 後殘留 `matured` 標記。
- `scripts/natural_shadow_pruning_evidence_runner.py` 將 `pending_is_normal_wait` 限定為全 cohort 已知且純 time-wait；缺 sidecar、空 cohort、契約缺件、未知原因都 fail-closed。forward companion 固定標示 `diagnostic_only=true`、`promotion_authority=false`、`eligibility_contribution=none`，並保留 sidecar hash、size 與 as-of read cutoff。
- `scripts/run_daily_ml_allocation_orchestration.py` 從既有 `ML_FORWARD_OUTPUT_ROOT` 選取 forward sidecar；`scripts/scheduled/run_ml_allocation_copilot.cmd` 只補上既有 forward output root 的環境設定。這條接線只讀 companion，不寫正式 DB、不授予 natural credit、不放寬 all-horizon gate。

驗證：

```text
.\.venv\Scripts\python.exe -m py_compile ml_module\natural_shadow_pruning_evidence.py scripts\natural_shadow_pruning_evidence_runner.py scripts\run_daily_ml_allocation_orchestration.py
.\.venv\Scripts\python.exe -m pytest tests\test_ml_natural_shadow_pruning_evidence.py tests\test_natural_shadow_pruning_evidence_runner.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases ml_module\natural_shadow_pruning_evidence.py scripts\natural_shadow_pruning_evidence_runner.py scripts\run_daily_ml_allocation_orchestration.py
```

結果為 `24 passed`、targeted mypy `Success: no issues found in 3 source files`；pytest 僅有既有 `.pytest_cache` 權限 warning。測試使用 temporary SQLite fixture，沒有觸發 scheduler、沒有執行 production writer，也沒有修改 D 槽舊 raw/artifact。

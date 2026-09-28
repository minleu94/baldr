# WP4 個人模型唯讀評估投影 v1（2026-09-28）

## 結論

`PersonalizationReadService.read_personal_model_assessment(...)` 已提供單一已保存推薦、其個人 capture 與明確指定 Stage C summary 的唯讀 assessment projection。它從現有封存資料重驗 identity 並投影狀態，不改 Stage C writer 或 producer schema，不掃描 `latest`/glob，也不產生全域 evidence 或 promotion credit。

真實 m11 readback 為 `insufficient_data` / `pending`：19 列模型有效、0 列 rule-only fallback、0 列成熟、19 列待觀察，model coverage 為 10000 bp。Stage C 原摘要的 reason 是 `personal_outcome_source_or_cost_incomplete`。固定 50% null benchmark 為 5000 bp；pending 時 model/null Brier 與 calibration gap 全為 `null`。After-cost 狀態為 `unavailable`，所有 after-cost 指標為 `null`。這是資料尚未成熟／完整的狀態，不是模型失敗或自然績效判斷。

該 projection 只表示決策日收盤至官方 20-session endpoint 收盤的事後 close-to-close 標籤；`is_execution_pnl=false`。即使未來單筆 outcome 成熟，本 v1 仍固定回報 `insufficient_data`，不從單一 capture 給出繼續、停用或替換建議、不比較 `rule_score`、不自動切換。要得出效果建議仍需要明確版本化的同 scope 評估政策與足夠成熟樣本。

## 成熟列讀回邊界

成熟 Stage C outcome 讀回會逐列要求 `label_kind=stock_close_return_positive.v1`、`stock_return_bp` 為整數基點（拒絕 bool），且 `label == int(stock_return_bp > 0)`。讀回再以同一個 V2 user-declared SQLite 中的決策日與 endpoint 收盤價重算 close-to-close 基點；查詢使用唯讀／query-only 連線、明確兩個 compact 日期與 symbol/date 索引，並比對來源檔身分及 Stage C evaluation 前後 stat。若來源有未被摘要 pin 的 `-wal`/`-shm`、索引或列不唯一、資料缺漏、雜湊／日期／價格不符，成熟 outcome 不會被接受。這是指定來源目前 bytes 的一致性驗證；self-hash 不是不可偽造簽章，不代表官方 publication time 或完整歷史 PIT。

成熟 outcome 的價格交叉讀回只適用於穩定、已 checkpoint、沒有 `-wal`／`-shm` sidecar 的隔離 SQLite 副本；讀回器目前在檔案 stat 與 SQLite open 間沒有同一 handle 的原子綁定，因此不可對正在被替換或寫入的資料庫做成熟判定。若正式來源旁有 WAL/SHM，請勿為了通過檢查而 checkpoint 或改寫正式資料庫；改用核准的 SQLite backup 流程建立隔離副本，確認副本穩定且無 sidecar 後再明確指定。拒絕只表示此來源形狀目前無法安全重驗，不代表模型無效。m11 的 19 筆 pending 原因仍是 Stage C 摘要中的 source/cost evidence incomplete，不能歸因為 sidecar。

After-cost 結果目前明確投影為 `unassessed`，after-cost Brier、null benchmark 與 sample count 保持 `null`。Stage C 原始 after-cost 狀態只保留在診斷欄位；本讀回器尚未獨立重算 after-cost 指標，因此不會把 `matured_with_after_cost_probability` 直接顯示為已評估。

## 呼叫介面

```python
from app_module.personalization_read_service import (
    PersonalModelAssessmentV1,
    PersonalizationReadService,
)

assessment: PersonalModelAssessmentV1 = service.read_personal_model_assessment(
    result_id,
    capture_path,
    personal_capture_root,
    daily_summary_path,
)
```

呼叫者必須提供 exact `result_id`、canonical output 中已保存的 capture 路徑、其 `personal_prediction` 根目錄，以及 Stage C summary 的明確路徑。Stage C 目前沒有 result→summary 索引；禁止以掃目錄、glob 或 latest 猜路徑。缺 summary 時，UI 應顯示「尚未執行評估」及下一步，不得拿當前政策補註舊結果。

DTO 的主要欄位是 `assessment_status`、`evidence_status`、`recommendation`、`reason`、`identity`、`scope`、成熟／待觀察數、整數 bp `metrics`、`after_cost`、`missing_evidence`、`next_steps` 與 `diagnostics`。v1 的 `recommendation` 固定為 `insufficient_data`、`read_only=true`、`writes_allowed=false`、`auto_switch=false`。所有不可計算或尚未成熟的數值以 `null` 表示，不把未知當 0。

`identity` 綁定 canonical payload/raw artifact、V2 policy revision/hash、完整候選 pins、user-declared source trust、market source 檔案身分、receipt/projection/cost hashes、capture/result、決策時間，以及 summary/outcome hashes。`scope` 顯示決策日、回報起訖、close-to-close 標籤、20-session horizon、成本情境、交付列/模型有效列/fallback 列與 coverage。個人來源固定標為 research-only，`official_historical_pit_verified=false`；這不會轉成官方 PIT 或 publication-time 證明。

## m11 真實收據

唯讀重投影使用已存在的 m11 canonical result、capture 和 Stage C summary；沒有修改原資料：

| 證據 | 路徑與 SHA-256 |
|---|---|
| Canonical result | `result_id=rec_03ae4c2c3e0344a7ae26d8646107c851`，由 read service 進行 exact canonical readback |
| Personal capture | `output/qa/personal_daily_product_20261006/personal_research_ui/m11/output/_test/personal_prediction/captures/ad981904a1717affda64c1a787aa95c7602156344a67a6521dd0ff3c23b8ac28.json`；raw SHA `sha256:9bb49cb8e0f461231710dfd7d8113d15383674094eb208d332315bf43dbf2f46` |
| Stage C summary | `output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json`；payload SHA `sha256:6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667`；raw SHA `sha256:2355562e24d6e9e3398810835e43ac315ce84a61ae89bb55b6652abbea4dbdea` |
| Assessment readback receipt | `output/qa/personal_daily_product_20261006/wp4_personal_model_assessment_v1_m11_20260928/readback.json`；SHA `sha256:96418342a45940f4725d18e0d0b8167d2d37abe4cd8ff8dc593b9d24487951ff` |

Candidate `rec-cal-3f8b2c276ef316e28de3806d`、policy revision 1。決策日由封存 identity 投影為 `2026-09-29`。結果為 19 active / 0 fallback / 10000 bp coverage，0 matured / 19 pending。這只驗證 m11 的 sealed result/capture/summary 能被 read service 精確連結及投影；不是新訓練、自然成熟結果或額外 UI 操作證據。Source trust 仍是 `user_declared_source_time`、research-only、非官方 PIT。

m11 仍是本次唯一真實 Native model run 的 pending readback；下述成熟正例是另外建構的隔離合成 canonical/capture/Stage C contract fixture，不能與 m11 pending 混為一談。

## 驗證

- 隔離成熟正例使用 synthetic SQLite 價格與 calendar、canonical execution/readback、V2 policy event、V3 capture 與既有 Stage C writer。它驗證的範圍只有 Stage C sealed rows 到 user-declared source endpoint 價格的唯讀讀回契約，不代表真實 V2 policy 被採用、歷史自然表現已驗證或 official PIT。
- 負例重算 outcome 與 summary hashes 後，仍會拒絕：（1）return 與 label 一起改寫但與來源價格相反；（2）錯誤 `label_kind`；（3）label 與 `stock_return_bp` 符號不一致。另將 after-cost 狀態偽改成 mature，readback 仍保持 `unassessed` 並讓指標為 `null`。
- 最終短路徑命令：`$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests/test_personal_model_full_stack_integration.py tests/test_ui_qt_personal_model_assessment.py -q -o addopts= --basetemp .tmp_5`；6 passed，37.47 秒。pytest cache 權限警告不影響測試 exit 0。單獨 integration module 在 `.tmp_w3` 為 4 passed，31.02 秒。
- 首次較深 basetemp `.tmp_wp4_mature_full_01` 為 3 passed / 1 failed；失敗在既有 Windows create-only receipt 發布的 `os.link`，回報 `WinError 3`。改用 repo ignored 短 basetemp `.tmp_w3` 後整個 integration module 4 passed；將此首輪失敗保留為測試路徑／Windows 檔案操作限制，不據此宣稱產品回歸。
- `py_compile`：`app_module/personalization_read_service.py`、`tests/test_personal_model_full_stack_integration.py` 通過。
- `mypy app_module/personalization_read_service.py`：0 issues。
- `git diff --check`：本次兩個 Python 檔通過（只有 Git 的 LF/CRLF 工作副本提示）。

本次 final source/test/report SHA-256 於交付回報列出；m11 canonical、capture、summary 與其既有 readback receipt 均只讀，沒有重寫或替換原 artifacts。

測試正例使用隔離 fixture；m11 readback 使用既有 QA 收據唯讀重投影。兩者都不寫正式 D: 資料、不改個人 policy/global pointer。WP3 已接上使用者明確選擇 summary path 的唯讀 UI 路徑；本報告不代表 native OS foreground 操作或新的 WP3 end-to-end 驗收。真實 m11 的 19 pending 仍待有效 session/calendar 與來源成本證據補齊後，以新的隔離 assessment 輸出評估。

# V5 日常操作與可讀性工程：驗收報告

> **文件狀態：FROZEN QA EVIDENCE／整合 route 已完成實測。**
>
> 本文件記錄 V5 日常操作與可讀性工程的實測證據與限制。它不宣告正式 V4／V5 gate，不宣告 V6 真實個人化成熟，也不把 fixture、replay 或工程接線解讀成 learning 有效。

## 1. 目的與判讀邊界

本輪改善目標是讓既有決策工作台更容易開始、逐區知道重點與下一步，並讓進階研究、資料日期、來源 identity、錯誤恢復與按需圖表有清楚入口。呈現層可整理既有 DTO 與 read-only source；推薦保存、personalization delivery ACK、journal/readback、continuity write path、scheduled evidence capture 與每日資料累積契約必須維持原有 call chain。

本輪不授予新的資料寫入權限、不觸發正式 collector／scheduler、不改正式 SQLite 或 learning producer，不改推薦／回測的數值、切換參數與 cutoff／缺件拒絕規則。工程完成的判定以本文件的實測命令、隔離 fixture、source diff 與受控測試為準。

## 2. 目前狀態

| 項目 | 狀態 |
|---|---|
| A 工作台／市場首屏 | root 已完成 1280×800 與 900×700 視覺審查；mandatory QA 已完成 |
| B 候選池／研究／來源 | focused 75 tests 與末輪 44 tests；watchlist CTA／下排按鈕重疊修正後由 root 核對可達與可見 |
| D 推薦／回測／導覽 | focused 86 tests；root 已核對推薦策略／執行首屏、navigation groups、回測實際停損／停利摘要 |
| baseline core integrity | final tracked non-UI core 1,142→1,142、changed=0、missing=0、unexpected=0；protected paths 193 |
| `ui_qt/main.py` | baseline before／current patch SHA-256 相同；原有 50 insertions／40 deletions dirty 保留 |
| 效能 | before／after 均完成 2 samples；after 附 lazy price tab probe |
| 本文件 | frozen QA evidence；整合 route 已由同一組命令重跑並全綠 |

## 3. 基線與隔離證據

基線產物位於 `output/qa/v5_readability_20260921/`：

- `git_head.txt`、`git_status_before.txt`、`git_diff_before.patch`、`git_diff_stat_before.txt`：保存 branch／HEAD／完整 dirty diff。
- `dirty_backup/` 與 `dirty_backup_manifest.json`：基線 dirty 15/15 檔案備份及 hash 對帳。
- `tracked_non_ui_core_manifest_final.json`：排除 UI／tests／docs／QA output 的 tracked non-UI manifest。
- `protected_contract_paths.txt`：scripts/scheduled、daily capture／forward learning／recommendation、identity、journal、repository 保護路徑。
- `core_integrity_report_final.json`：baseline 1,142、current 1,142、changed 0、unexpected 0。
- `ui_qt_main_before.patch`、`ui_qt_main_final.patch`：確認 `ui_qt/main.py` 仍是基線 dirty，未混入本輪 assurance 變更。

效能 before 位於 `perf_before_runs/run_20260921T214919Z/before.json`。環境為 Python 3.11.9、PySide6 6.10.1、Windows 10 build 26200、Qt `offscreen`；fixture 的隔離 SQLite 有 `daily_prices=30`、股票 `2330`、資料日 `2026-08-30`，重複 2 次。repeat 0 是 cold-in-process（不含 process／import startup），repeat 1 是 warm；沒有 `QApplication.exec`、collector 或 scheduler。

已量得的 before 數字：

| 指標 | cold repeat 0 | warm repeat 1 |
|---|---:|---:|
| MainWindow construct | 2,147.966 ms | 1,064.375 ms |
| MainWindow show | 50.437 ms | 39.667 ms |
| MainWindow workspace count | 8 | 8 |
| Stock report construct | 5.700 ms | 5.881 ms |
| Stock report show＋load | 49.555 ms | 52.016 ms |
| Stock report rows | 30 | 30 |

RSS／tracemalloc 同樣保存於 JSON；before 僅有 2 samples，不足以代表 production dataset 的速度或記憶體分布。

## 4. R1–R10 驗收矩陣

| ID | 驗收要求 | 主要程式入口 | 測試／證據 | 狀態 |
|---|---|---|---|---|
| R1 | 首頁優先呈現每日重點、日期、資料日期與下一步；三秒是設計目標，不以本輪自動化量測宣稱真人理解時間 | `ui_qt/views/workbench_view.py` | `test_ui_qt_v5_workbench_guided.py`、final perf、A screenshots | bounded evidence verified |
| R2 | 各 section 有重點、原因、下一步或明確缺件 | guided workbench、`v5_research_summary.py`、candidate／report／portfolio views | v5 workbench/research tests、B/D screenshots | bounded evidence verified |
| R3 | 日常、進階研究、系統維護分層；deep link 仍可達 | `ui_qt/widgets/left_navigation.py` | `test_ui_qt_v5_guided_readability.py`、left navigation／main integration、D screenshot | verified |
| R4 | candidate／report／portfolio 保留 exact context、result identity、data date | watchlist／stock report／portfolio／continuity | `test_continuity_review_workbench_r1_integration.py`、research tests、B screenshots | verified |
| R5 | 推薦與回測提供 guided summary／進階切換；數值、參數、save→ACK→journal/readback 不變 | recommendation／backtest config/result | D route、v5 guided tests、`test_personalization_save_integration.py`、save coordinator | verified |
| R6 | 價格圖按需 render；OHLC 完整用 candle／volume，缺件 fallback close | stock research report view | research views、report screenshots、after lazy probe | verified |
| R7 | 錯誤用白話說明原因、恢復步驟；保留 last good data | report／portfolio／recommendation errors、continuity controls | research tests、continuity controls、affected error tests | verified |
| R8 | before／after 量測建構 8 個工作區、執行 7 次指定切換（`workbench`→`recommendation`→`backtest`→`watchlist`→`portfolio`→`runtime`→`workbench`）、report、記憶體；lazy first price／revisit／call counts 分開記 | `run_ui_perf_baseline.py` | before JSON＋after JSON | bounded evidence verified |
| R9 | 不破壞 collector／scheduler／identity／persistence／learning safety；缺件與 cutoff 仍 fail closed | protected contract paths、UI save／continuity／scheduled evidence | personalization save、continuity write/controller、scheduled evidence、main integration、source service | verified |
| R10 | Manual、UI Features、Snapshot、Product／6M／Version／Hub／Index 維持 scoped SSOT 一致 | docs owned by this task | 本文件、coverage pass、final doc readback | updated；pending wording retained |

## 5. Final QA route（frozen worktree 實測）

所有命令都在 repository root 執行，使用 `.venv/Scripts/python.exe`。測試先確認 `tmp_path`／隔離 config，不接受只做 import 或 source grep 的替代結果。

### 5.1 精選整合路由

以下測試合併於一次 pytest invocation，避免重跑重疊測試：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_personalization_save_integration.py `
  tests/test_continuity_review_workbench_r1_integration.py `
  tests/test_ui_qt_decision_continuity_controls.py `
  tests/test_decision_continuity_write_path.py `
  tests/test_decision_continuity_controller.py `
  tests/test_recommendation_save_coordinator.py `
  tests/test_scheduled_decision_evidence_capture.py `
  tests/test_workbench_source_service.py `
  tests/test_ui_qt_decision_desk_main_integration.py `
  tests/test_ui_qt_v5_guided_readability.py `
  tests/test_ui_qt_v5_research_views.py `
  tests/test_ui_qt_v5_workbench_guided.py `
  tests/test_ui_qt_left_navigation.py `
  tests/test_ui_qt_recommendation_profiles.py `
  tests/test_ui_qt_recommendation_metadata.py `
  tests/test_ui_qt_recommendation_next_steps_copy_text.py `
  tests/test_ui_qt_recommendation_portfolio_results.py `
  tests/test_ui_qt_research_workflow.py `
  tests/test_ui_qt_research_lab_mode_driven_ui.py `
  tests/test_cross_page_decision_journey_mainwindow.py `
  tests/test_full_app_healthcheck_mainwindow_smoke_plan.py `
  tests/test_ui_qt_watchlist_layout.py `
  tests/test_ui_qt_watchlist_candidate_pool_copy_text.py `
  tests/test_ui_qt_watchlist_storage_wiring_increment_b.py `
  tests/test_ui_qt_stock_research_navigation.py `
  tests/test_ui_qt_stock_research_report.py `
  tests/test_ui_qt_portfolio_view.py `
  tests/test_ui_qt_decision_desk_view.py `
  tests/test_ui_qt_workbench_view.py `
  tests/test_workbench_read_only_composer.py `
  -q -o addopts=
```

若 A／B／D owner 另有新增 affected tests，加入同一 invocation；不要把 focused owner count 與 final combined count 相加。輸出保存到本 QA 目錄並記錄 pytest cache `PermissionWarning`；warning 不得偽裝成 pass，真實 failure 必須回 owner 修正。

Frozen worktree 修正後實際結果：**299 passed、1 warning、44.64s**。`test_workbench_source_service_reads_real_read_only_sources` 已改為核對 seeded 2330 portfolio alert 的 reason、source trace、drill-down、action 與 `write_intent=false`，同時保留 background evidence feed 的完整 item set；這是對既有 composer 分類的精準契約對齊，不放寬 fail-closed。原始 pytest log 位於 `output/qa/v5_readability_20260921/focused_integration_route_final_20260921.log`。

### 5.2 Mandatory QA

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
.venv\Scripts\python.exe scripts/qa_validate_update_tab.py
.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

再以 frozen worktree 的實際 Python 變更清單執行 `py_compile`，不把 baseline dirty 的 `main.py` 排除在語法檢查外。命令與完整輸出保存至 QA output。

Frozen 結果：update workbench pytest **84 passed、1 pytest cache warning、2.30s**；`scripts/qa_validate_update_tab.py` **exit 0，passed 25、failed 0、skipped 4**；全域 mypy **Success: no issues found in 638 source files**；changed Python 與隔離 perf harness `py_compile` 均通過。

### 5.3 UI evidence

沿用 root 已完成視覺審查的 A／B／D screenshot fixture，視窗包含 1280×800 與 900×700；research screenshot 使用正式 Midnight Analyst theme，必要時在 process 明確載入 `C:/Windows/Fonts/msjh.ttc`。final readback 檢查首屏 CTA／下排按鈕不重疊、無方框字型、錯誤與資料日期可讀；本輪沒有真人理解時間測試。

## 6. After performance route

使用相同隔離 fixture 形狀（30 rows、2330、2026-08-30）與 before 的重複邊界（2 samples）。改進只增加 `phase`／output path 與獨立 lazy report probe，不改基本量測動作：

```powershell
.venv\Scripts\python.exe output\qa\v5_readability_20260921\run_ui_perf_baseline.py `
  --phase after --repeats 2 --lazy-report-probe `
  --work-root output\qa\v5_readability_20260921\perf_after_runs
```

after JSON 必須同時保存 cold-in-process、warm constructor/show、建構 8 個工作區與 7 次指定切換、stock report construct/show＋load、RSS/tracemalloc。`lazy_report_probe` 另保存：首次切到價格 tab 時間、重訪價格 tab 時間、首次／重訪 render call count、tab 變更後的 `read_report` call count。這些額外欄位不得與 before 的基本 report load 時間直接混比。

After 實證在 `perf_after_runs/run_20260921T225247Z/after.json`：cold／warm MainWindow construct 為 2056.184／1117.590 ms（before 2147.966／1064.375），show 為 26.087／20.972 ms（before 50.437／39.667）；stock report construct 為 7.672／7.755 ms（before 5.700／5.881），show＋load 為 38.471／38.525 ms（before 49.555／52.016）。兩個 sample 的 lazy first price tab 為 17.247／16.927 ms，revisit 為 6.004／4.391 ms，tab 變更後 `read_report` 新呼叫為 0、重訪 render call count 保持 1。這是小型 fixture、兩次 in-process sample 的 bounded comparison，不代表 production dataset 效能。

如相同邊界出現超過 15–20% 回退，先確認 fixture、Qt、process 與 owner 變更，再回報 root；不在 QA 階段擴大 main 架構。

## 7. 文件同步與 final wording

已完成並互相核對：

- `docs/02_features/UI_FEATURES_DOCUMENTATION.md`：首頁 guided、分層導覽、候選／報告／持倉摘要、按需圖表與 fallback。
- `docs/07_guides/APPLICATION_MANUAL.md`：預設／進階入口、操作、參數、結果判讀、data date／identity source 用途、失敗恢復、完整功能位置。
- `docs/00_core/PROJECT_SNAPSHOT.md`：目前工作模式與 bounded V5 engineering status。
- `docs/00_core/DEVELOPMENT_ROADMAP.md`：Roadmap Hub current／next 入口（若適用）。
- `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`、`ROADMAP_6M_ENGINEERING.md`、`VERSION_ROADMAP_V2_1_TO_V4_0.md`：依 scoped authority 補工程進度，保留 formal／natural／V6 pending。
- `docs/00_core/DOCUMENTATION_INDEX.md`：本驗收文件入口。

最終只能使用「V5日常操作與可讀性工程已完成／已由指定測試與隔離 evidence 驗證」這類 bounded wording。仍須保留：正式 V4 evidence gate、正式 V5 gate、V6 user-level personalization maturity、自然 learning 效果與 production data readiness 的 pending 語意。

## 8. Final sign-off checklist

- [x] root 已宣告 code frozen；B/D 最後 layout／summary 修正已納入。
- [x] final manifest 與 `ui_qt/main.py` baseline exact comparison 已重產。
- [x] 精選整合 pytest 以真實結果保存：299 passed、1 pytest cache warning；source contract assertion 已核對 2330 portfolio alert 與完整 background feed。
- [x] mandatory pytest／QA validator／mypy／changed py_compile 已保存。
- [x] after perf 與 before 用同一 fixture／repeats，lazy probe 額外指標已分開。
- [x] screenshots 使用正式 theme、字型可讀、CTA／按鈕不重疊。
- [x] R1–R10 每項都有路徑與 evidence；限制與 pending 清楚保留。
- [x] Manual、UI Features、Snapshot、Scoped SSOT、Index 已同步；本文件保留 formal／natural／V6 pending 邊界。

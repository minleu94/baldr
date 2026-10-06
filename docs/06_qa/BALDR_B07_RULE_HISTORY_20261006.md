# BALDR B07 規則卡與研究歷史查找驗證（2026-10-06）

## 範圍與整合邊界

獨立 lane：`lane/baldr-b07-rule-history-20261006`；固定 base：`11a56284f871e0098f30be869b3419dad74f9a4f`。worktree：`output/worktrees/baldr-b07-rule-history`。本次需求依據為原 `baldr_product_experience_plan_20261004.md`、Astra completion inventory 與 Sol completion review 的 B07；不新增計畫來源、不改原 plan。

本 lane 補齊 B07 的固定來源唯讀查找，以及至少一條既有 typed single_backtest 執行後保存完整規則來源的路徑。這不是整份 Stage 6 或投資有效性驗收。沒有 B09 依賴，沒有規避 B09 拒絕。

僅修改排他清單中的規則卡 reader、saved reader、backtest UI／metadata 與兩個既有測試；新增 `research_history_lookup.py`、B07 focused 測試與本文件。`research_run_legacy_adapter.py` 沿用未修改。ResearchRunService、原 repositories、Comparison、shared DTO、main、config、完整 Manual 與金融 core 維持唯讀。沒有真實資料庫操作、交易、Native／Task／ACL、資料清理、訓練或 push。

## 固定來源與 API

`ResearchHistoryLookup.list_entries(limit=200)` 回傳每來源最多 200 筆的 immutable entry 與逐來源 diagnostics；API 接受 1–1000 筆。`resolve(entry)` 核對 source_kind、run_type、run_id、metadata hash、股票與 context，回傳原保存 payload／ResearchRunData；來源改動、缺件或種類不支援就拒絕。

| 原來源 | 查找 kind／run_type | 開啟路徑 |
|---|---|---|
| BacktestRunRepository | legacy_backtest | 原歷史摘要／交易明細 |
| RecommendationPortfolioRunRepository | legacy_recommendation_portfolio | 原推薦回放 DTO 結果 |
| Registry | single_backtest | 原保存摘要／交易明細與 saved rule card |
| Registry | batch_backtest_stock | 原保存個股摘要／交易明細與 saved rule card |
| Registry | fixed_basket_stock | 原保存個股摘要／交易明細與 saved rule card |
| Registry | recommendation_portfolio | 既有嚴格 recommendation reader 與原回放畫面 |
| Registry | research_forward | metadata-only；research_forward_metadata_only |
| Registry | 其他 unknown run_type | metadata-only；unknown_run_type_metadata_only |

不新增 rule-only decision／journal 來源，不將 legacy backfill 成 Registry。既有比較 eligibility 邏輯保持原樣。

查找不建目錄、不遷移、不取得 SQLite lock、不寫入。SQLite 使用 `mode=ro&immutable=1` 與 `query_only`；Registry 的 schema／row decoder／artifact verifier 沿用原契約。存在 `-wal`、`-shm` 或 `-journal` 時明示 `active_sqlite_sidecar_unsupported`，避免 immutable 讀到未合併 snapshot；查找不自行 checkpoint 或移除 sidecar。Legacy artifact 前後 hash 重新核對；registry 由原 artifact verifier 核對。

## 真實既有 typed execution → 保存 → 新程序規則卡

single producer 在原 `BacktestExecutionRequest.execute` 邊界封存 `single-backtest-rule-execution.v1`。支援既有 baseline_score_threshold 1.0、fixed threshold 與 next_open；其他模式沿原 execution 並保留缺件狀態。原行情 loader 載入一次，原 StrategyRegistry／BaselineScoreExecutor、BacktestService、BrokerSimulator 執行同一份輸入。封存實際 executor 參數、BrokerConfig、資料 bytes fingerprint、程式來源 hash、執行期間、股票、features、benchmark 與原資格聲明；不新增核心計算。

測試只替換行情 I/O，使用隔離的合成 OHLCV；確實經過原 typed executor／broker，產生進出場交易與 equity，再走原 `save_run` artifact 保存與實際 UI save 邊界。不是手填合格 report fixture。新 Python interpreter 從保存 metadata／parquet 讀回完整欄位規則卡，且禁止呼叫今天的 registry metadata 或 executor。與原 request execution 的 equity／trades 完全相同。

完整欄位表示本次執行的 entry、exit、成本與來源能被識別；`historical_pit_eligible=false`、`performance_evaluable=false`，saved 結果仍 `source_ref_only`／`not_evaluable`。Unknown／source-only 不補成可評。現有 typed recommendation portfolio reader 沿用，沒有創造新 typed portfolio producer。

Look-ahead 自查：不新增訊號、標準化、benchmark 計算或停損停利計算；原 executor／next-open 撮合保留。producer 拒絕超出本次請求期間的輸入。資料 fingerprint 只證明本次輸入 bytes，不證明歷史 PIT。

## UI 操作與中央 Manual 同步素材

入口：研究實驗室結果面板上方，展開「研究歷史查找（legacy／Registry／推薦回放）」；各研究模式共用同一查找。

1. 點「查找既有歷史」，按需讀取；預設每來源上限 200，不在畫面建構時掃描。
2. 用搜尋欄過濾已載入名稱、股票、來源、種類、run ID；清單標示 legacy／Registry 與種類。
3. 選一筆後「開啟原結果」，重新核對 exact 來源再返回既有摘要／推薦回放。歷史回測缺少的績效顯示「未知」，保存／升級動作不可用。
4. Registry 支援結果可「查看保存規則」；完整來源已綁定的卡仍提示績效與正式資格不可評。legacy 不冒充 typed 規則卡。
5. 「查看保存 metadata 與原因」可讀保存 snapshot 與 hashes；forward／unknown 僅開 metadata，並顯示不支援理由。
6. 取消、切換選取、關閉或新執行 generation 會忽略舊 callback；背景讀取不套用過期結果。

排錯：`source_missing` 表示既有來源未配置或檔案不存在，查找不自動建庫；`selected_source_changed`／artifact hash 錯誤需重新查找及核對原保存來源；`active_sqlite_sidecar_unsupported` 需由原來源 owner 處理後再查找，本入口不修復資料。部分來源缺件顯示 diagnostics，其他可讀來源仍可列出。

完整 `APPLICATION_MANUAL.md` 由中央 owner 同步本節入口、步驟、參數、判讀、限制與排錯；本 lane 遵守 Manual readonly 排他界線。

## 驗證與證據

Focused regression 涵蓋 B07 lookup、saved card、UI callback、metadata、Decimal save、原 execution coordinator、實際 UI save、Comparison、legacy adapter、原 rule reader／dialog、研究模式 UI。測試全部使用隔離 tmp，沒有讀寫正式 DB。正負測試涵蓋固定來源、同 run_id 異 kind、exact 六項身份變動、artifact 改動、snapshot entry／exit／cost／來源變動、缺 DB、active sidecar、取消／關閉／generation 過期、原結果返回與 fresh process。

來源 immutable 斷言包含所有來源檔 bytes、size、mtime；legacy 查找前後 Registry run 數相同。連線 spy 拒絕 writer constructor／schema，並要求 immutable read URI。

最終 focused pytest：**154 passed in 51.37s**（`.tmp_b07_final5`）。執行命令：

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_baldr_b07_research_history.py tests/test_saved_strategy_rule_card.py tests/test_ui_qt_saved_strategy_rule_card.py tests/test_backtest_research_run_metadata.py tests/test_backtest_research_run_decimal_save.py tests/test_backtest_execution_coordinator.py tests/test_ui_qt_research_run_save.py tests/test_research_run_comparison_service.py tests/test_research_run_legacy_adapter.py tests/test_strategy_rule_card_readmodel.py tests/test_ui_qt_strategy_rule_card.py tests/test_ui_qt_research_lab_mode_driven_ui.py -q -o addopts= --basetemp=.tmp_b07_final5
```

六個修改 production 檔以 `mypy --follow-imports=silent` 檢查通過；九個修改 Python 檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 的金融 float 邊界及 Look-ahead 檢查通過；`git diff --check` 通過。早期失敗曾是測試資料未出場、child config 產生日誌、spy 參數與 `uri=True` 重名、UI 建構漏參數，以及 UI optional 保存按鈕缺件；皆已修正並重跑，不刪 raw QA 輸出。

依委派，重 UI union 只由中央在整合結果執行一次：`tests/test_ui_qt_update_view_workbench.py`、`scripts/qa_validate_update_tab.py` 與 `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`。本 lane 的 focused 結果不取代這三項整合門檻。

Rollback：中央如需撤回，對本 lane 的單一提交執行 `git revert <B07 commit>`；只撤回這十個程式／測試／QA 檔的功能，不刪除已保存研究 artifact 或原資料。本 lane 保留 worktree，等待中央整合，不自行 dev cherry-pick。

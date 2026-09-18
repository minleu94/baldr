# Graphify 程式碼引用查核收尾（2026-09-17）

## 範圍與結論

以 `fb31f7c0` 工作樹為查核起點，先查既有 Graphify 圖，再對 Git 追蹤的 Python、JSON、TOML、YAML、PowerShell 與 batch 檔案做符號文字查核，並閱讀候選實作、直接 caller 與相關契約。本輪不執行候選函式、不連線、不啟動排程、不碰正式資料。

「repo 內未找到外部引用」是靜態查核結果，不能證明外部使用者、動態匯入或部署入口不存在。無 caller 的相容介面保留；未啟用 producer 不自動接線。這次沒有刪除 production 程式碼，完成的是候選分類及失準文件修正，不是宣告整個專案沒有死碼。

## 候選逐項處置

| 候選 | 查核證據與目前狀態 | 本輪處置 |
|---|---|---|
| `app_module/position_service.py::PositionService` | 符號只出現在自身定義與 logging；`V4_POSITION_HEALTH_TRANSITION_EVALUATOR_CONTRACT_2026_09_08.md` 明示為 legacy JSON PositionDTO 路徑，與 V4 position snapshot 不同 | 保留 legacy 相容介面，不接入 V4；退役須另確認外部 JSON 使用者與資料遷移 |
| `app_module/strategy_executor_adapter.py::SimpleStrategyExecutor` | 檔案已 deprecated，註明以 `BaselineScoreExecutor` 替代；repo 內未找到 caller | 保留向後相容邊界；不把無 caller 當作可移除公開匯入的證據 |
| `app_module/financial_units.py` | 明確以 `__all__` re-export `financial_module.units` 七個函式；未找到舊模組的 repo 內匯入 | 保留舊匯入相容 wrapper，新增程式使用正式 financial module |
| `data_module/prospective_technical_shadow_producer.py::run_prospective_technical_shadow` | 只有定義及 `__all__`；函式會複製 daily prices 並執行技術指標計算 | 保留未接線候選；不能為消除無 caller 而啟動資料重算 |
| `DecisionQualityDiagnostic`、`DecisionQualityMetricSet` | `decision_quality_dtos.py` 中只有定義；同檔仍有其他使用中的 DTO；MetricSet 包含 bp 邊界正規化 | 保留 DTO 候選，不刪整個 DTO 模組；本輪未證明可由其他 DTO 等價替代 |
| `NoSlippageModel`、`FixedBPSlippageModel` | 無外部符號引用；同模組的 `TaiwanStockTickSlippageModel` 被 Paper daily execution 與 portfolio execution trace 使用 | 保留替代模型，沒有為它們接上 runtime；不同成本模型不能視作重複語意 |
| `ExitEffectivenessProducer` | 類別只有 wrapper／export；實際 `produce_exit_effectiveness()` 被 `scripts/run_exit_effectiveness_daily.py:18,41` 及 `tests/test_exit_effectiveness_producer.py` 呼叫 | 保留 wrapper 與正在使用的模組；已修正架構文件的實際 caller 名稱 |
| `should_accept_daily_price_session()` | 符號只有定義；`market_data_integrity.py` 的其他工具被 update service 與 repair script 使用 | 保留未接線 helper；不可整檔刪除，亦不擅自改變行情接受規則 |
| `is_human_review_classification()` | `machine_status_classification.py` 中只有定義；不等於整個 machine status 契約未使用 | 保留 helper；本輪不改 classification 契約 |
| `export_mops_readiness_package()` | 無 caller；同模組的 `build_mops_readiness_package()` 有專屬測試；export 另包含 output 路徑檢查、staging 與發布 | 保留未接線匯出介面；不可將 builder 測試視作 export 已受驗證 |
| `TalibCompatibility`、`MockTalib` | 模組內 MockTalib 會呼叫 TalibCompatibility，且 fallback 分支會建立 MockTalib；repo 外部未找到接線。主 `technical_analyzer.py` 與 `technical_indicators.py` 均直接 `import talib` | 保留相容實作；修正 `system_flow_end_to_end.md`，不再暗示主流程自動 fallback 已接通 |
| MCP server、runtime validator、`ui_app/main.py` | 外部或 CLI 入口不需要有 repo 內 importer 才能被執行 | 不因圖中無 inbound 刪除；本輪不對所有入口做運行驗收 |

## 圖的更新與限制

- 使用本機安裝版本的 `graphify update .`，只做 AST 程式碼更新，不呼叫 LLM。此 CLI 對整個 code corpus 重新抽取並利用快取，不能將它描述為只抽取 Git 差異檔案。
- 更新後獨立讀取 `graph.json` 核算：**42,264 nodes、115,862 edges、1,459 communities；缺端點 0、自迴圈 0**。Git 追蹤且仍存在的 **1,983 個 Python 檔全部具有 source_file 節點**；此指標不等於每個符號或每條引用都被抽取。圖的 `built_at_commit` 為 `fb31f7c0`，對應本輪文件修改前的程式碼基準。
- 本輪工具顯示 361 個未命中快取的檔案完成抽取、43 個輸入檔（提示例為 JSON）產生零節點。所有圖節點標記 `_origin=ast`；report 仍含 8,685 條 `INFERRED` 邊，因此不能把整張圖視為純精確 import/call 證據。工具已備份舊圖；因超過 5,000 節點，自動略過 HTML 生成，舊 HTML 不代表本輪結果。
- 先前報告的 33,831 nodes／103,885 edges／798 communities 是前一張圖的數值，其 `built_at_commit` 為 `639a7789`，不能直接當作目前 HEAD 的驗證。
- 文件語意層本輪未重建。先前「273 份文件必須有 LLM key 才能更新」不精確：skill 允許 host agent 做語意抽取；這次不啟用該流程，不能聲稱文件引用完整或最新。
- `scripts/sqlite_explorer_local.py` 是個人筆記且被 `.gitignore` 明確排除，缺席不構成受追蹤程式碼漏掃；不執行該檔。
- AST 工具將部分 JSON 視為輸入但產生零節點，不能以 Python 覆蓋率推論所有支援格式均已成功抽取。
- 節點／邊結構健康只能確認圖結構，不是 API 使用、執行路徑、測試覆蓋或功能退役的證明。

## 驗證與回滾

查核方法為既有 graph query、Git tracked 檔案的文字引用搜尋、候選與 caller 原文核對、圖端點／自迴圈／Python 檔案覆蓋核算，以及 `git diff --check`。本輪只有文件變更，未執行正式資料 producer，也未宣稱 runtime 測試通過。

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `docs/01_architecture/system_architecture.md` | 修改 | Exit 成效的函式及 CLI 接線 | 對本批文件 commit 執行 `git revert <commit>` | 僅撤回文件修正 |
| `docs/01_architecture/system_flow_end_to_end.md` | 修改 | TA-Lib fallback 尚未接線 | 同上 | 僅撤回文件修正 |
| 本文件 | 新增 | 候選證據與圖限制 | 同上 | 移除本輪查核紀錄 |

回滾前先用 `git status --short` 確認工作樹，檢視 `git show <commit>` 的範圍，再 revert；不可覆盖其他 agent 的未提交內容。`graphify-out/` 與 `output/qa/` 均保留本機，不納入 Git；圖可由原始碼重新抽取。

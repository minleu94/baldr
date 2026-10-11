# BALDR B07 規則卡與研究歷史查找驗證（2026-10-06）

> **後續狀態導覽（2026-10-11）：** 本文的 154／54／11 項數字是各自 lane 的測試結果；後續中央整合另記錄 caller 採用 64 MiB 單檔／256 MiB 每輪預算、中央 caller 五項測試通過及 Manual 同步完成。這些有限收據不代表 Native、真人、正式資料或投資有效性驗收。細節見[第二波中央整合收據](BALDR_SECOND_WAVE_INTEGRATION_20261006.md)。

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

## 中央 review 最小 followup（ce8c8fad 之後）

本次閉合兩個精確 finding：legacy artifact 的無界 `read_bytes`／hash 後再次開路徑 decode，以及 parent shutdown 查錯 child 屬性。僅修改 owned lookup、backtest_view、兩個 owned 測試與本文件；原共享 service／repository／金融 core 不改。

新增 `ResearchHistoryReadBudget(max_artifact_bytes=..., max_total_bytes=...)`：兩欄必須由工程 caller 明示正整數 serialized byte 上限。原 legacy 保存入口與 ResearchRunService 沒有可直接沿用的單檔／aggregate 保存容量上限，因此本 lane 不制定新的正式容量政策。constructor 可注入 `read_budget`；`list_entries`／`resolve` 可用同名 optional keyword 覆蓋，並有向後相容的 `check_cancel: Callable[[], bool] | None = None`。沒有 budget 時 legacy 查找回 diagnostic、resolve 回 unavailable：`legacy_read_budget_required`，不能聲稱預設 legacy 路徑完整可用。Registry metadata／原 reader 契約維持原樣；本 budget 僅覆蓋 owned legacy artifact I/O。

中央 caller 最小接線素材（數值由中央依實際工程情境評估，以下不設正式 threshold）：

```python
from app_module.research_history_lookup import ResearchHistoryReadBudget

budget = ResearchHistoryReadBudget(
    max_artifact_bytes=caller_artifact_bytes,
    max_total_bytes=caller_round_bytes,
)
# 注入 result_panel 建立 ResearchHistoryLookup 的 read_budget=budget，
# 或工程 caller 直接呼叫：
page = lookup.list_entries(read_budget=budget, check_cancel=check_cancel)
result = lookup.resolve(selected, read_budget=budget, check_cancel=check_cancel)
```

每次 list／resolve 另起一輪 aggregate；跨 row、跨兩個 legacy source 共用，不以 200／1000 筆 row limit 冒充 bytes limit。讀前 stat 超單檔或剩餘 aggregate 就拒絕且不開 artifact；每次 read 最多 64 KiB，分塊檢查取消。list 只保留 digest；resolve 留住同份 raw bytes，算 SHA 重建 entry/context 並核對 selected pin 後才 decode，不 hash 一份、再從路徑讀另一份放行。stat／fstat 的 size、mtime_ns、dev、inode 在開啟前、讀中／後與 decode 後核對；來源變動回 `artifact_source_changed`，超限回 `artifact_byte_budget_exceeded`／`aggregate_byte_budget_exceeded`，取消回 `read_cancelled`。

這是 serialized bytes 與一般來源變動檢查，不是解壓後記憶體容量政策，也不宣稱能防惡意 race、timestamp 偽造或 ABA。Registry 共享 reader 的既有 decode／sidecar 行為不在本次最小 legacy 補件的保證範圍。source-only／rule／performance／PIT 資格均未提升。

`BacktestView.request_cooperative_shutdown` 現沿 `self.result_panel.research_history_lookup` 設 `_closed`、`cancel_pending`，將 child worker 納入等待判定。真正 parent `closeEvent` 的晚到 worker 測試驗證不開結果，沒有只測 widget 自己 close。

新增 stat 超限不 open、兩 artifact／跨 source aggregate、分塊大小／cancel、同 raw pin 後 decode、同 size／mtime inode source swap、讀後來源消失，以及實際 parent close 負例。只跑 related subset，不重跑前次 154 或中央重 UI union。

Followup 驗證：`test_baldr_b07_research_history.py`＋`test_ui_qt_saved_strategy_rule_card.py`：**54 passed in 50.22s**（`.tmp_b07_followup2`）；最後補上 unavailable wrapper／來源消失後，重跑新增 budget／chunk／swap／missing 負例：**11 passed, 28 deselected in 1.90s**（`.tmp_b07_followup3`）。兩個修改 production 檔 targeted mypy、四個修改 Python 檔 compile、quant guard 與 diff check 均通過。測試初次失敗為 stat guard 攔到測試自己的 inventory 與真實 collapsed group 尚未啟用；已修測試接線並重跑，不清理輸出。

```powershell
python -m pytest tests/test_baldr_b07_research_history.py tests/test_ui_qt_saved_strategy_rule_card.py -q -o addopts= --basetemp=.tmp_b07_followup2
python -m pytest tests/test_baldr_b07_research_history.py -k 'legacy_budget or legacy_one_round or legacy_aggregate or legacy_read_chunks or legacy_selected_same or legacy_source_swap or legacy_source_missing' -q -o addopts= --basetemp=.tmp_b07_followup3
```

執行 interpreter 仍為原 workspace `.venv/Scripts/python.exe`。新增提交只包含上述五個 owned 檔案；中央整合需保留前次 ce8c8fad 並接續此 followup，caller budget 接線、完整 Manual 與一次重 UI union 尚由中央處理。

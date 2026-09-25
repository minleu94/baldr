# R022 實作報告：Regime policy／state transition 與 I/O 分離

**IMPLEMENTATION_STATUS: ACCEPTED_SCOPE**

**TASK:** R022

**IMPLEMENTER MODEL:** LUNA_MAX

**START HEAD:** `e16f92928980a025d24bd5b023eeadf9d6a31daa`
**END HEAD:** `e16f92928980a025d24bd5b023eeadf9d6a31daa`（本輪未 stage／commit）

Root 已就 pure regime policy／state boundary、多日與 cooldown parity、CAS fail-closed、execution-time save 與 P2 closure 授予 R022 bounded `ACCEPTED_SCOPE`。此狀態不代表 Wave 7–14 完成；相關 waves 仍 `BLOCKED`。共享工作樹在本輪開始時已包含其他 Wave 7 slices 的未提交變更；下列檔案表只認領 R022 對應 hunk，不認領同檔其他 owner 的變更。未讀取或寫入正式資料。

## 權威與前置依賴

- 已依 repo 規定閱讀 `AGENTS.md`、`docs/agents/README.md`、`shared_context.md`、`git_exclusions.md`、專案 snapshot／roadmap、現況與目標架構、skills registry、APPLICATION_MANUAL，以及 R022 指定文件。
- R022 authority：`FINAL_TARGET_ARCHITECTURE.md` §5.2、`FINAL_MIGRATION_SEQUENCE.md` Block 4、`FINAL_ARCHITECTURE_INVARIANTS.md` INV-03／05／07／10／13／16。
- 前置：R003、R012、R015 已具備本切片所需的現有 detector、execution-time regime 保存與 personal save caller closure；R022 不重開其 wire／save contract。

## 起始 characterization

在改碼前，以 `PROFILE=test`、獨立 TEMP data/output roots 跑下列既有路由，結果 **42 passed**：

```powershell
python -m pytest tests/test_market_regime_kernels.py tests/test_market_regime_detector_details.py tests/test_market_regime_data_provider.py tests/test_walkforward_service.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_use_case.py tests/test_ui_qt_recommendation_execution.py -q -o addopts=
```

起始 TEMP root：`C:\Users\archi\AppData\Local\Temp\r022_baseline_a78f12ef81a547a4bf5f463fcfc21fc3`；另以 synthetic sequence fixture 保存基準於 `C:\Users\archi\AppData\Local\Temp\r022_state_baseline_9fa8dc0943b84ba08985c5b23768d52c\baseline.py`。舊行為：8/3 Trend 初始寫入；8/4 Breakout 候選仍輸出 Trend 並保存候選；8/5 第二日確認後輸出／保存 Breakout；8/6、8/7 cooldown 對 Trend 候選持續輸出 Breakout 且不寫入。8/4 同日重跑只參考更早日期並替換該日紀錄。Persistent mode 使用 `regime_history.json`；isolated mode 從空記憶體狀態開始，不讀寫 history file。

## 實作與相容性

| 範圍 | R022 變更 |
|---|---|
| `decision_module/market_regime_policy.py` | 新增純 `RegimeTransition`／`RegimeAssessment` contract 與 transition function。沿用兩日確認、三日 cooldown、只看目標日前 history、同日重跑及原 candidate/effective regime 語意。 |
| `decision_module/market_regime_detector.py` | Detector 改成接收明示 DataFrame 與 prior history，回傳 regime／transition；移除 provider、檔案、history load/save 與 SQLite/CSV I/O。公式、threshold、label、confidence 與分類條件未改。舊 constructor 的 inert `config` 相容參數仍是暫時入口，列入 TMP-RGM-01。 |
| `app_module/regime_history_store.py`、`app_module/regime_service.py` | 新增 app-side persistent／isolated state adapter。保存既有 `regime_history.json` 路徑與 `{date: {"regime", "timestamp"}}` wire shape；用 raw-byte SHA fingerprint、同路徑 thread lock + OS sidecar lock 包住 compare/write、同一鎖區間下 atomic `os.replace`。競爭者 fingerprint 已改變時明確拒絕提交；不使用 fallback write 覆蓋較新的 state。 |
| Composition 與推薦 facade | `decision_service_composition.py` 建立單一 RegimeService，並將同一 object 注入 RecommendationService；組合測試鎖住 object identity。RecommendationService constructor 與尾端 regime wrappers 改委派到 app-side service；保留舊 custom `regime_detector`／未注入 constructor 相容 adapter，列入 TMP-RGM-01。 |
| Caller 接線 | `ui_app/main.py` 將 RegimeService 共用於 UI 與 RecommendationService；personalization／scheduled CLI、walk-forward script 及 QA producer 以明示 service 接線。walk-forward 使用 isolated history。 |
| UI DTO 回歸 | Legacy Tk UI 的兩個 call site 改讀 `RegimeResultDTO` attributes；新增「策略分析」及「手動市場狀態檢測」呼叫測試。 |
| Update Tab QA cleanup | 僅 QA sandbox teardown：確認 cleanup 目標等於位於系統 TEMP 下的 TemporaryDirectory，再對 Windows `WinError 32` 做最多 5 秒的遞增延遲 `TemporaryDirectory.cleanup()` 重試；每次 sharing violation 都記錄，其他錯誤立即重拋，期限耗盡仍失敗。未修改 UpdateService 業務邏輯。 |

本表涉及的 `recommendation_service.py`、`decision_service_composition.py`、`ui_app/main.py`、personalization／scheduled scripts 也包含其他 slice 的共享 dirty hunks；R022 僅認領上述 regime 注入／delegate hunks。測試 custom/fake detector callers 保留相容注入，不代表新增第二個 production detector owner。

### 主要行為保證

- History entry 更新時間仍在成功 transition candidate 發佈時由 app 產生 `datetime.now().isoformat()`；JSON 仍採 `ensure_ascii=False, indent=2`。同日記錄在評估時排除，提交時以該日 key 取代。目標日期後的 history 永遠不參與計算。
- cooldown suppression 不寫 history，並在 persistent mode 檢查評估 fingerprint 是否變化；candidate pending 按原規則保存候選。isolated mode 只更新 service 內記憶體，不建立檔案或 lock sidecar。
- source provider 讀取例外回傳舊有 `Trend`／`0.5`／`details.error` degraded 結果，不讀取或發佈 history；CSV `pd.read_csv` 失敗 regression 驗證 error 原字串。History decode、CAS conflict、atomic publish 錯誤不會落入 source fallback：直接 service call 明確失敗；DTO route 為 `quality=degraded, regime=None` 並保留 error warning/details，不能偽裝成成功 Trend。
- Detector 僅以目標日當天與之前的市場資料計算；transition policy 僅接收日期 `< target_date` 的 history。look-ahead 檢查通過，沒有改 indicator 公式、數值精度、regime label／confidence、recommendation ranking 或 backtest 統計；未新增金融核心裸 `float` 算術。
- 保存仍採已完成 execution 的 regime snapshot。既有 execution A→source/regime B→save A 測試以 spy 證明保存時不呼叫 `detect_regime`；不填 `DecisionBatch.state_transition`，避免改 sealed payload/hash。
- persistent history concurrency test 同步兩個 service 先讀相同 absent fingerprint，讓第一個 writer 在 atomic replace 中停住；驗證第二個 writer 無法進入 replace、最後只有一個 replace，另一方收到 `RegimeHistoryConflict` 且不能覆寫勝者。

## Service owner 與相容入口盤點

| Caller | R022 接線／狀態 |
|---|---|
| `app_module/decision_service_composition.py` | 單一 RegimeService 注入 RecommendationService；composition test 以 `is` assertion 驗證同一物件。 |
| `ui_app/main.py` | 建立一個 persistent RegimeService，同一物件供 legacy UI 檢測與 RecommendationService；兩個 dict-style DTO call site 已修為 attribute access。APPLICATION_MANUAL §2.3 明確標示此 Tk UI 為 legacy、主入口是 `ui_qt/main.py`。 |
| `scripts/run_personalization_recommendation.py`、`scripts/scheduled/run_scheduled_recommendation_snapshot.py` | 各自明示建構 persistent RegimeService 並注入 RecommendationService；同 process 不再有隱式第二個 persistent writer。 |
| `scripts/run_walk_forward_comparison.py` | 明示建構 isolated RegimeService；cache 遇到 degraded details.error 時跳過該日，符合舊 detector fallback 行為。 |
| QA scripts | 同一流程同時使用 RegimeService 與 RecommendationService 時共用同一實例；離線 loop 的 fake detector 僅為測試 seam。 |
| RecommendationService compatibility default | 尚保留 constructor 未注入時自建 persistent RegimeService、`regime_detector` 相容參數及尾端 wrappers。它們不是新的 domain writer，但未來外部／遺留 caller 仍可能未明示共享 service，列入 TMP-RGM-01。 |

APPLICATION_MANUAL §5.1 已同步：source read failure 的 Trend／0.5／`details.error` 是降級結果，不是新訊號；history 損壞或 CAS conflict 時本輪狀態不可用，勿把上一輪結果當成本輪成功，先查來源與同時寫入並保留 `regime_history.json` 原狀。這是因 R022 的 source degraded 與 history fail-closed 會影響結果判讀及排錯；手冊未承諾特定 UI 文案，也未新增參數或操作入口。

## 驗證結果

所有測試使用新 TEMP roots、`PROFILE=test`；Qt 路由設 `QT_QPA_PLATFORM=offscreen`。完整受影響 route：

```powershell
python -m pytest tests/test_r022_regime_state_separation.py tests/test_ui_app_regime_result_dto.py tests/test_market_regime_data_provider.py tests/test_market_regime_detector_details.py tests/test_market_regime_kernels.py tests/test_walkforward_service.py tests/test_decision_service_composition.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_use_case.py tests/test_ui_qt_recommendation_execution.py tests/test_task_loop_02_contract.py tests/test_task_loop_03_contract.py tests/test_pit_industry_callers.py tests/test_recommendation_input_preparation.py tests/test_recommendation_input_read_order_characterization.py tests/test_recommendation_refactor_characterization.py tests/test_recommendation_service_calibration_integration.py -q -o addopts=
```

結果 **129 passed、2 warnings**（既有 `decision_module/scoring_engine.py:437` pandas dtype `FutureWarning`）；TEMP root `C:\Users\archi\AppData\Local\Temp\r022_full_c38354b57014453abf853c5e0b050dd8`。

| Gate | 結果 |
|---|---|
| Reviewer P2 closure | Reviewer 針對 source CSV failure fallback、history conflict 與兩個 UI DTO caller 的合併回歸 **26 passed**；可核對模組：`tests/test_r022_regime_state_separation.py`、`tests/test_ui_app_regime_result_dto.py`、`tests/test_market_regime_data_provider.py`、`tests/test_walkforward_service.py`。Reviewer 未提供精確 CLI flags 或 TEMP basename，故不補寫未核實資料。 |
| 新 cleanup regression：transient sharing violation 後成功、5 秒期限內耗盡仍重拋、sandbox 路徑越界拒絕 | `\.venv\Scripts\python.exe -m pytest tests\test_qa_validate_update_tab_cleanup.py -q -o addopts=`：**3 passed**。 |
| 強制 Update Workbench UI suite | `\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=`：**84 passed**；TEMP root `C:\Users\archi\AppData\Local\Temp\r022_ui_workbench_426b70a00e00455f8402ad9026fca28d`。 |
| 強制 Update Tab QA | `\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py` 在 deadline 版本下由 implementer 以三個獨立 TEMP roots 連續執行，均為 **25 passed / 0 failed / 4 skipped，exit 0**：`r022_updateqa_1_cd0e4576017c45d7b54bdadffcf7ce08`、`r022_updateqa_2_8a9e441a370b4e489702af24a47d4fe7`、`r022_updateqa_3_bf0b9382cb424f8885d3b02fd24ea798`；root 另以新 TEMP 執行一次亦為 **25/0/4、exit 0**。每次皆將 `TEMP`／`TMP` 指向新唯一 root；4 個 skip 為腳本既有下載／破壞性操作 skip。較早的 5-attempt 單次綠燈不列作 gate 證據：root 後續獨立重跑曾再現 WinError32，因此改成 5 秒 elapsed-time deadline，再以 persistent-lock test 與上述四次 fresh TEMP run 驗證。13 次隔離診斷重跑成功且未找到持續持有者；`with sqlite3.connect(...)` 只管理 transaction、不會自動關閉 connection，可能是後續維護硬化點，但未證實為原事故來源。本次 cleanup retry 僅改善暫時 sharing violation 的恢復能力，不宣稱根因已定位或修復。 |
| Targeted mypy | Regime policy/store/service、detector、composition、RecommendationService：**6 files / 0 issues**。 |
| Broad mypy | Root 在更新後共享工作樹獨立執行：**697 source files / 0 issues**。本地較早的並行快照曾見 R019 `decision_module/recommendation/evaluate.py` 12 errors；該 owner 修復後由 root 最新 gate 清零。 |
| `py_compile` | R022 改動的 service／policy／store／composition／UI／CLI／QA scripts／tests 全部成功。 |

Root 另做 focused verification：在 `PROFILE=test`、`DATA_ROOT=$r/data`、`OUTPUT_ROOT=$r/output` 的新 TEMP root 下，下列命令 **34 passed**；root 未列出實際隨機 TEMP basename。

```powershell
python -B -m pytest tests/test_r022_regime_state_separation.py tests/test_market_regime_data_provider.py tests/test_market_regime_detector_details.py tests/test_market_regime_kernels.py tests/test_walkforward_service.py tests/test_decision_service_composition.py tests/test_pit_industry_callers.py -q -o addopts= -p no:cacheprovider
```

R022 source failure 與 conflict 新增測試分別證明：CSV parse exception 保留 error details 且無 history write；history commit conflict 直接拋出，DTO route 顯示 degraded、`regime=None` 與原 error，不回傳成功 fallback。save A test 確認 A snapshot 保存期間 `detect_regime` spy 未被呼叫。

## Acceptance criteria 自評

| Criteria | 自評 |
|---|---|
| Decision detector 無 file／DB／CSV I/O；state 在 app adapter | 完成；資料 provider 位於 application layer，pure detector 收 explicit frame／prior state。 |
| 多日確認、cooldown、同日 rerun、日期 cutoff、persistent／isolated 行為 parity | 完成 synthetic sequence 與 provider/detector/walk-forward regression；冷卻期間不寫入及舊 history wire/path 均覆蓋。 |
| state compare/write 原子且競爭明示失敗 | 完成 deterministic 兩 service test；OS path lock 包含 fingerprint compare 與 atomic replacement。 |
| execution-time regime 保存，save 不 redetect | 完成 R012/R015 caller regression 與 A→B→save-A spy test。 |
| production producer 使用單一 RegimeService | 已知 UI、composition、personalization、scheduled callers 明示共用／注入；RecommendationService constructor fallback 與舊 `regime_detector` source compatibility 尚保留，故 TMP-RGM-01 ACTIVE。 |

## Temporary component、風險與 rollback

`TMP-RGM-01` ACTIVE：由 R022 引入，owner 為 Regime／application composition；具體殘留為 `RecommendationService.__init__` 的無注入 default、`regime_detector` 相容 adapter、`detect_regime`／`get_strategy_config_for_regime` wrappers，以及測試／QA fake detector calls。R029／Block 5 的 caller inventory 完成、所有支援中的來源 caller 明示注入 RegimeService，外部支援期結束，且單一 object identity test 維持通過後，才能移除相容參數與 fallback。此為 source compatibility，不宣稱 serialized artifact alias。

已知既有殘差：cooldown suppression 若候選持續與剛切換 regime 不同，沿原行為可能持續不寫入；本輪刻意保留。JSON 檔案損壞或 concurrent state change 現採 fail-closed，需依 error details 排查，不自動清空／覆寫歷史。Update QA 的間歇 WinError32 尚未確認根因；13 次隔離重跑未觀察到持續 handle holder，SQLite context manager 未自動 close connection 是可能的後續硬化點，需另行驗證，不列入 R022 已修復根因。

Rollback 只回退 R022 hunk：移除新 pure policy/store，恢復原 detector 的 provider/history adapter，恢復各 R022 caller 注入與 DTO attribute 修正；同檔 R015/R018/R021/R025/R023/R024 hunks 不得整檔還原。保留既有 `regime_history.json` bytes；本任務未做 schema migration 或正式檔案寫入。QA cleanup retry 可獨立回退；回退後既有 transient WinError32 可能再次令 validator exit 1。

`TMP-RGM-01` 的 ledger row 已窄幅加入 `FINAL_MIGRATION_SEQUENCE.md`；未改 R015 `TMP-REC-03` row。Root 最終 gate 授予本切片 bounded `ACCEPTED_SCOPE`；`TMP-RGM-01` 仍 ACTIVE，Wave 7–14 仍 BLOCKED。

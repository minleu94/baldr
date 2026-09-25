# Gemini 獨立審查：R005 replay／portfolio replay characterization

## ROLE／TASK ID／PURPOSE

你是 R005 的獨立 Gemini reviewer。只做唯讀正式審查，依目前 repository 實際 source、test、diff 與下面完整 task spec／Luna report 判斷。SOL 初審不是 PASS。請在 `C:\Projects\PythonProjects\technical_analysis` 工作；不要改檔、開始其他 R-task 或重新設計 architecture。

## CURRENT SYSTEM CONTEXT／COMPLETED DEPENDENCIES

HEAD 基線 `391b057c92037ec7a19cab2bf951d6029d29b020`。R001、R002、R004、R007 已 PASS；R005 的 R001 依賴已完成。Wave 1 的 R003、R005、R006 正式 Gemini 審查仍待完成，Wave 2 blocked。工作樹有既存且並行的未提交變更；只對本任務歸屬兩檔提出變更建議。Gemini 先前的 `WAVE1_PARALLEL_ANALYSIS` 是唯讀分析，`ANALYSIS_STATUS: COMPLETE` 不是本次正式 review PASS；SOL 對照記錄在 `REFACTOR_REPORTS/WAVE1_GEMINI_PARALLEL_ANALYSIS_INTAKE.md`。

**R001 清冊勘誤（R005 報告撰寫後）：**下方內嵌的 R005 implementation report 將 R001 的 replay/provider source path mismatch 列為當時的追溯 gap；該 gap 已由 Luna 在 R001 清冊修正，並經 SOL 重審 PASS（`REFACTOR_REPORTS/R001_SOL_ERRATUM_REVIEW.md`）。目前正確定義為 `app_module/recommendation_replay_service.py::RecommendationReplayService.run_snapshot -> RecommendationSnapshotDTO` 與 `app_module/recommendation_dataframe_provider.py::RecommendationDataFrameProvider.__call__ -> List[Dict[str, Any]]`。TMP-REC-04 canonical bridge 尚未建立，由 R017 建立、R020 移除。R005 受審測試／報告本身的凍結 SHA 沒有改動；請按目前 repository source 評估，不把已收口的歷史追溯 gap 當作新的 R005 failure。

## AUTHORITATIVE ARCHITECTURE／RELEVANT INVARIANTS

`FINAL_TARGET_ARCHITECTURE.md`、`FINAL_DATA_FLOW.md`、`FINAL_ARCHITECTURE_INVARIANTS.md`、`FINAL_MIGRATION_SEQUENCE.md`、`REFACTOR_EXECUTION_ORDER.md` 與原始 R005 spec 是權威。本 task 只 characterization 現行系統；若發現與目標架構有差異，報告 gap／後續 owner，不在 R005 修改 production。下列為 `FINAL_ARCHITECTURE_INVARIANTS.md` 相關原文：

| invariant | 要求 | 驗證 |
|---|---|---|
| INV-05 | 訊號、特徵、母體、標準化與 benchmark 只用 decision-time 可得資料；unknown availability 不當已知。 | cutoff／PIT／未來資料注入反例。 |
| INV-06 | 新金融核心計算使用 Decimal 或具單位整數；不得在重構中偷改原 precision、rounding、tie-break 或 ML matrix ABI。 | 獨立數值 oracle、精確比較；具名 legacy 例外退休帳。 |
| INV-13 | 歷史顯示只讀原結果；歷史重算建立新 result_id 並保留 parent/版本；兩模式 policy 差異不得被共用 engine 偷改。 | 無 live lookup readback、日期/母體/策略差異 fixtures。 |

## CHANGED-FILE／DIFF SCOPE／FROZEN BYTES

Luna 本輪只變更：
- `tests/test_recommendation_replay_characterization.py`，SHA-256 `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`。
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`，SHA-256 `14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F`。

請先用 SHA-256 核對實際 bytes；若已 drift，停止審查並請 SOL 重凍結。兩檔是原先未追蹤檔，不能只用 `git diff` 判定內容；直接讀實際檔案並對照下面完整報告與 source。不要觸碰其他 existing modifications、正式資料、artifact、模型或 repository store。

## REVIEW FOCUS／TESTS ALREADY EXECUTED

SOL 獨立執行：
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py tests/test_historical_evidence_replay.py tests/test_recommendation_historical_replay.py tests/test_recommendation_portfolio_backtest.py tests/test_backtest_timeline_contract.py -q -o addopts= -p no:cacheprovider
```
結果：`66 passed, 24 warnings in 2.56s`，exit 0。Luna 亦獨立執行專用測試與 `py_compile`，詳見實作報告。這些綠燈不取代你的 oracle／source 檢查。

查同 mode full snapshot 與 future append 的獨立 expected、數字 YYYYMMDD、as-of/available_date 逐列 cutoff 和排除計數、universe、lookback 80、自訂 lookback、max stocks 200、20-row minimum、volume_ratio_min、price_change_min／price_change_max 精確邊界、score fallback、stable tie/top-N、個股例外、portfolio factor manifest/date/config/refs。特別不要把未來 available_date 列排除誤解成整股 veto：先前仍有 20 個有效列時可使用較早資料。查 annotation、parent reference、exception diagnostics 的證據限制與 downstream owner，不要求跨 interactive/replay mode 相等。

逐項檢查 acceptance criteria、現行行為保存、numerical semantics、architecture compliance、dependency direction、persistence／replay／ML compatibility、hidden state、duplicated ownership、scope creep 與測試是否充分。若有 finding，指出檔案/行號、可重現證據與對 R005 原 scope 的具體修正；若現況 gap 本來屬後續任務，標明 owner，不以這點要求 R005 偷改 production。勿在 review 中修改程式碼。

## ORIGINAL R005 TASK SPECIFICATION（完整）

# R005 — replay／portfolio replay characterization

## TASK CONTEXT

RecommendationDataFrameProvider使用自己的lookback、max stocks、fast filters、exception skip與簡化dict；RecommendationReplayService再包SnapshotDTO。它不是互動推薦只換日期。

## WHY THIS TASK EXISTS

R017/R020要先bridge再共用evaluator；沒有mode-specific oracle會把既有差異誤判成應消除的重複。

## AUTHORITATIVE ARCHITECTURE REFERENCES

- [FINAL_DATA_FLOW §4](../FINAL_DATA_FLOW.md)
- [FINAL_TARGET_ARCHITECTURE §7](../FINAL_TARGET_ARCHITECTURE.md)
- [FINAL_ARCHITECTURE_INVARIANTS INV-05、13](../FINAL_ARCHITECTURE_INVARIANTS.md)

## DEPENDENCIES

R001。

## ALLOWED SCOPE

新增replay characterization與小型DataFrame fixtures；只讀portfolio backtest integration。

## OUT OF SCOPE

共用evaluator、改policy、改backtest撮合/成本、持久化新execution。

## CURRENT BEHAVIOR TO PRESERVE

numeric YYYYMMDD、future-row cut、available_date、lookback 80、max stocks 200、min rows、volume/price fast filters、score fallback、sort/top_n、per-stock exception skip及factor manifest。

## IMPLEMENTATION OBJECTIVE

建立interactive/replay差異表與replay own golden cases；每個snapshot的profile/config/date/rows及portfolio refs均可驗。

## ARCHITECTURAL INVARIANTS

INV-05、06、13。

## ML COMPATIBILITY REQUIREMENTS

無ML schema變更；若fixture帶annotation，只驗不被replay重算。

## PERSISTENCE COMPATIBILITY REQUIREMENTS

歷史manifest只在tmp_path；不寫RecommendationRepository。

## TEST REQUIREMENTS

新增專用test；跑historical replay、portfolio backtest中replay/date/factor manifest、timeline contract。

## ACCEPTANCE CRITERIA

同mode結果穩定；future append不改舊snapshot；空/缺資料/例外語意有斷言；跨mode不硬性相等。

## EXPECTED DELIVERABLES

replay oracle、mode差異表、policy候選清冊（只描述、不設計新政策）。

## POST-TASK REPORT REQUIREMENTS

列出已固定與未知差異、測試命令、將由R017/R020處理的mapping。

## ROLLBACK / FAILURE CONDITIONS

若只能依賴正式資料，改用最小DataFrame。回滾移除新增tests。

## LUNA R005 IMPLEMENTATION REPORT（完整）

# R005 實作報告

- TASK：R005 replay／portfolio replay characterization
- IMPLEMENTER：Codex Luna
- HEAD：起始與結束皆為 `391b057c92037ec7a19cab2bf951d6029d29b020`
- 狀態：待 SOL review

## 基線與 dirty state

開始前確認 HEAD 為 `391b057c`。指定檔案當時均為未追蹤檔，且與 rework packet 的交付基線雜湊一致：

| 檔案 | 起始 SHA-256 |
|---|---|
| `tests/test_recommendation_replay_characterization.py` | `4FE16FC67B72FDD4E48FF47BA3A206542C938400F0315539CE7DBB59A6511312` |
| `REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md` | `DC71C444F19AB8ADA27F72B065AE07B51BED5F8430DA08E0F37E0CB4F2BA06E9` |

起始 dirty baseline：

- 已修改：`data_module/__init__.py`、`docs/00_core/DOCUMENTATION_INDEX.md`、`docs/01_architecture/README.md`、`docs/01_architecture/target_system_architecture.md`、`tests/test_task_loop_03_contract.py`。
- 未追蹤：`=`、`data_module/contracts/`、`docs/01_architecture/target_architecture_2026_09_22/`、`docs/06_qa/REFACTOR_BASELINE_R001_20260922.md`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md`、`tests/test_data_market_contracts.py`、`tests/test_r004_recommendation_persistence_characterization.py`、`tests/test_recommendation_execution_state_characterization.py`、`tests/test_recommendation_refactor_characterization.py`、`tests/test_recommendation_replay_characterization.py`、`tests/test_refactor_ml_compatibility_baseline.py`。
- 只修改本報告與 `tests/test_recommendation_replay_characterization.py`；其餘 baseline paths 未改。HEAD 未變，未 stage／commit／push。

## 實作與責任邊界

測試使用合成 DataFrame，沒有讀正式資料，也沒有寫 RecommendationRepository。新增 oracle 固定同 mode full snapshot/future append、數字 `YYYYMMDD`、決策日與 availability cutoff、空／缺日期、universe、預設及可配置 lookback 與股票上限、20 列最低門檻、價量 fast filters、score fallback 順序、stable tie/top-N、個股例外及 portfolio factor manifest。

| Owner | 本次觀察到的行為 | oracle 邊界 |
|---|---|---|
| 一般互動推薦 `RecommendationService.run_recommendation` | 由 `DefaultRecommendationMarketDataProvider` 供應資料並回傳 RecommendationDTO，具有自己的 PIT/cutoff、universe 與 calibration 路徑。 | R005 不以 DataFrame provider 代替其 interactive oracle，也未固定互動結果。 |
| Portfolio/replay legacy evaluator `RecommendationDataFrameProvider` | `ui_qt/views/backtest_view.py` 的 portfolio backtest 建立此 provider。lookback 預設 80 個日曆日、上限預設 200 個首次出現代碼、少於 20 列跳過；價量 fast filters（含 `price_change_min` 下界與 `price_change_max` 上界）；分數依 `FinalScore`、`TotalScore`、`綜合評分`、0 順序取值；按分數穩定遞減排序後取 `top_n`；個股例外被靜默略過。 | 合成輸入鎖定門檻、正反例、輸出字典與候選順序。這是 provider policy，不是一般互動模式的 policy。 |
| Replay wrapper `RecommendationReplayService.run_snapshot` | 先解析並限制 `日期 <= as_of_date`；若存在 `available_date` 欄，缺值或晚於決策日的列會排除並計數；universe 是代碼 membership filter；複製 config、限制 top-N，封裝日期、profile、regime、recommendations、diagnostics。 | 精確比對 provider 實收 rows 與完整 snapshot 欄位；欄位不存在時不套用 availability cutoff。 |
| Portfolio backtest `RecommendationPortfolioBacktestService` | 依再平衡日期呼叫 replay，data manifest 由 snapshot 產生 factor snapshot/contributions。 | 合成 portfolio case 固定 snapshot 日期與 refs、ordered recommendation、factor 日期與完整 factor manifest；不擴大驗證撮合或成本。 |

R001 證據確認 replay 是獨立 legacy engine boundary，由 R005/R017/R020 承接。R001 將 symbol 標為 `app_module/historical_evidence_replay.py::RecommendationReplayService` 與 `app_module/recommendation_market_data_provider.py::RecommendationDataFrameProvider`；本次 HEAD 的實際定義位置是 `app_module/recommendation_replay_service.py` 與 `app_module/recommendation_dataframe_provider.py`。本報告與測試按 HEAD source 核對，R001 的路徑錨點差異列為追溯缺口，未改其他文件。

## Golden 與 fixtures

- Fixture grain 是每股每日列。日期為數字 `YYYYMMDD`，coverage 為數週；lookback 測試含第 80 與第 81 日邊界，股票上限測試用 201 個代碼 × 20 列。案例均使用測試建立的小型 DataFrame。
- Full snapshot golden 以 fixture `oracle_score` 和 factor 欄位為輸入，由 test-only scorer 複製成 `FinalScore`；預期的 `A=85`、`B=91`、ordered recommendations、factor scores、config/profile/as-of/regime/diagnostics 均逐欄寫成固定常數。future rows 使用極端分數，驗證同 mode full snapshot 仍與固定 expected 相同。
- `price_change_max=10` 的邊界 golden 以 prev close 100 固定 latest close 110（10.00%）剛好通過、110.01（10.01%）超限拒絕；超限股票未交給 scorer，也不在結果中。
- Portfolio manifest golden 直接列出 `technical.total_score=82.35 → 8235 bp` 與 `volume.volume_ratio=70.0 → 7000 bp`、availability 日期、版本、品質、missing policy、metadata 及 contribution counts；expected 未呼叫 production factor builder 生成。
- 例外案例固定 provider 靜默略過失敗股票、snapshot diagnostics 不增加例外項目，factor manifest 只包含成功輸出的股票。

## 已固定與尚未固定

已固定的差異包括 wrapper 的 date/availability/universe policy、provider 的 lookback/max-stocks/min-rows/price 與 volume filters/score-fallback/order/exception policy，以及 portfolio snapshot 的 date/profile/config 與 factor manifest。缺少 `available_date` 欄不產生排除診斷；欄位存在時 missing 與 future availability 都逐列排除，diagnostic 按排除列計數。拒絕最新列不會整股 veto：若前序仍有至少 20 列，provider 仍可用最後一列可用資料產生推薦；測試固定 MISSING/FUTURE 各保留 20 列且輸出前一可用日分數。

以下 contract 目前無法由 scoped fixture 固定，交下游承接：

- `RecommendationPortfolioBacktestResultDTO` 沒有 portfolio/replay result ID 或 parent reference 欄位；本次只能固定 snapshot、日期及 factor manifest references，無法驗不存在的持久化 parent/child refs。R017 建 bridge 時需確認 typed reference owner。
- Annotation 測試只固定 replay wrapper 原樣複製 provider 回傳的 annotation payload。Fixture 不載入歷史持久化結果，也沒有 current-model inference seam，因此不能證明 persisted annotation 與後續重算隔離；歷史讀取/顯示交 R016，重算與 evaluator parity 交 R020。
- Provider 對個股例外沒有 diagnostic contract；測試固定現況為 silent skip，不能辨別失敗原因。R020 如保留此 policy，需保留成功候選及 manifest 不納入失敗股票的結果。
- 一般互動 `RecommendationService` 的完整 policy/result 不在 R005 oracle 範圍；只登錄 owner 差異，不要求跨 mode 結果相等。
- R001 baseline 的 replay/provider source path 與 HEAD symbol 定義位置不同，需後續文件 owner 校正；本 task 不改該 baseline 或其他文件。

## 驗證

R005 專用測試：`.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py -q -o addopts= -p no:cacheprovider`，結果 `13 passed in 0.99s`，exit code 0。

V-REPLAY focused suites：`.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py tests/test_historical_evidence_replay.py tests/test_recommendation_historical_replay.py tests/test_recommendation_portfolio_backtest.py tests/test_backtest_timeline_contract.py -q -o addopts= -p no:cacheprovider`。

結果：`66 passed, 24 warnings in 2.61s`，exit code 0。24 項是 portfolio suite 的 idealized same-day-close `UserWarning`，不是失敗。

語法檢查：`.\.venv\Scripts\python.exe -m py_compile tests/test_recommendation_replay_characterization.py`，exit code 0。

空白檢查：`git diff --check` exit code 0，無 whitespace diagnostic；Git 對五個原有 dirty tracked paths 顯示 LF→CRLF checkout warnings，沒有改動那些檔案。兩個目標檔前後皆為未追蹤檔，因此另以 `git diff --no-index --check` 對照起始副本：測試檔命令為 `$backup = Join-Path $env:TEMP 'r005_luna_rework_20260922'; git diff --no-index --check -- (Join-Path $backup 'test_recommendation_replay_characterization.py') tests/test_recommendation_replay_characterization.py`，報告檔命令將末兩個路徑替換為 `R005_IMPLEMENTATION_REPORT.md` 的備份與 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`。兩命令 exit code 1 是因檔案存在預期 diff；均無 whitespace error。

## R017/R020 handoff

- R017 bridge 保留 replay wrapper 契約：as-of/availability cutoff、universe、snapshot metadata 與 dict recommendations；以固定 ordered snapshot 作 parity oracle。
- R020 evaluator/portfolio replay cutover 保留 DataFrame provider 的獨立 legacy policy 與輸出：lookback 80、max stocks 200、20-row minimum、價量 fast filters、score fallback、stable ties/top-N、例外 silent skip；不得用一般互動 `RecommendationService` 預期替換。
- 日期與 factor handoff 以 `test_portfolio_replay_pins_outer_snapshot_dates_and_factor_manifest` 完整固定結果為 oracle。R017/R020 使用同 mode 比對，不用跨 mode 相等取代。

## 回滾

為只回滾本次 price 上界增補並保留先前 R005 oracle，開始前已將兩個檔案複製到 `%TEMP%\r005_luna_rework_20260922_before_max_boundary`。在 repo 根目錄執行 `$backup = Join-Path $env:TEMP 'r005_luna_rework_20260922_before_max_boundary'`，再執行 `Copy-Item -LiteralPath (Join-Path $backup 'test_recommendation_replay_characterization.py') -Destination 'tests/test_recommendation_replay_characterization.py' -Force` 與 `Copy-Item -LiteralPath (Join-Path $backup 'R005_IMPLEMENTATION_REPORT.md') -Destination 'docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md' -Force`。這只移除本次上界增補；完整回到首次 R005 修改前的副本仍位於 `%TEMP%\r005_luna_rework_20260922`。回滾風險是失去對應版本的 R005 characterization/report 變更；不影響 production data 或其他檔案。

IMPLEMENTATION_STATUS: READY_FOR_REVIEW

## SOL FINAL PRE-REVIEW（完整）

# R005 SOL 最終送審前核對

R005 本輪僅在 `tests/test_recommendation_replay_characterization.py` 與 `R005_IMPLEMENTATION_REPORT.md` 加入價位上界 oracle。SOL 逐讀測試與 `RecommendationDataFrameProvider._passes_fast_filters` 的現行政策：前收 100、末收 110 在 `price_change_max=10` 精確邊界通過；末收 110.01 被拒，scorer 未收到該股。availability cutoff 仍逐列排除未來可得資料，先前有效列達 20 列時該股可照既有語意推薦，不能誤改成整股 veto。

SOL 獨立執行 V-REPLAY 五個 focused suites：`66 passed, 24 warnings in 2.56s`，exit 0；24 個 warning 是既有 same-day-close 研究假設提示。R005 worker 報告單檔 `13 passed`、py_compile exit 0。無 production、正式資料、repository 或 ML 改動。

凍結 SHA-256：

- `tests/test_recommendation_replay_characterization.py`：`F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`
- `REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`：`14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F`

此處僅是 SOL 初審；R005 仍待 Gemini 對實際 repository 獨立審查。Wave 2 不得放行。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

## REQUIRED GEMINI REVIEW RESULT

請回傳可核對的審查報告，逐一列出 findings（若無則明說）、你核對的實際 source／test、SHA、測試結果及證據限制。最後一行必須恰好是以下三者之一：
`REVIEW_STATUS: PASS`
`REVIEW_STATUS: CHANGES_REQUIRED`
`REVIEW_STATUS: BLOCKED`

Do not redesign the architecture. Do not perform unrelated cleanup. Do not silently fix unrelated bugs. Do not begin another R-task. If repository evidence contradicts this task specification in a way that prevents safe review, stop and report BLOCKED with evidence.

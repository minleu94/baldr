# BALDR 每日 Evidence 與 Model Readiness（2026-09-25）

> 查核基準：2026-09-25 Pacific；檔案內的最新採集時鐘跨至 2026-09-26 UTC／台北。這是正式資料及既有 artifacts 的唯讀工程盤點，不是訓練、推論、重播、自然成熟、模型品質或 promotion 驗收。
>
> 本輪沒有執行模型 pickle／joblib 載入、訓練、推論、scheduler、正式資料寫入或 pointer 修改。正式 SQLite 以 `mode=ro`、`PRAGMA query_only=ON`、單次讀取交易後 `ROLLBACK`；personalization index 同樣唯讀。Direct/OOC 維持凍結，R027 維持 INCONCLUSIVE、R028 維持 BLOCKED。

## 目前應先處理的工程斷點

| 優先序 | 目前證據 | 最窄修復 | 不代表 |
|---|---|---|---|
| P1：個股研究 UI 沒接 ML read provider | `ui_qt/main.py:320-325` 建立 `StockResearchReportReadService` 時未傳 `ml_provider`；`app_module/stock_research_report_service.py:1404-1411` 因 provider 為 `None` 固定回 unavailable。既有 9/24 H5 與 bounded 13 檔研究收據未進個股 UI。 | 新增 app-owned、只讀 typed receipt provider，使用各家族既有 receipt contract／hash 驗證；只從已產生 JSON receipt 投影所選股票的整數 bp 輸出、版本、缺失欄位、qualification 與限制。保留 `ml_provider` 作為注入 seam，由 UI composition owner 接線。 | 不在 UI 載入模型、即時 infer/train、把研究輸出當建議、補造 available clock 或 provenance。中央組裝 `ui_qt/main.py` 由既有 owner 處理。 |
| P1：9/25 recommendation calibration learner 的同次 cohort 綁定（歷史失敗；synthetic 修復驗證完成） | 當日 snapshot 有 200 檔 cohort；當次 learner 曾以 `failed_dependency`／`symbol_cohort_preflight_failed:ValueError` 結束。原因是舊 JSON/glob 消費方式未接 typed execution artifact。 | 已改為 pipeline 傳本次 child status 的 `result_id` 與 cohort hash；learner 以唯讀 saved query 讀取明示 result id，驗證 canonical artifact/index、schema/revision、artifact bytes/payload hash、決策日、資料日、clock 與 cohort identity/hash。Synthetic regression 結果見本報告「修復驗證」。 | 未重跑正式 scheduler 或 training；9/25 原始失敗仍是歷史收據。不得改用固定 symbols、掃描／重播舊日或宣稱候選已訓練。 |
| P1：有效的 paper coverage receipt 被 consumer schema 檢查擋下 | 9/22 paper producer status 是 `paper-portfolio-daily-status.v1`，另有 `isolated_scope_schema_version=paper-portfolio-daily-isolated-scope.v1`，其 nested preopen receipt 是 `paper-preopen-coverage.v1` 且 status passed。forward status 因 `paper preopen coverage receipt schema is not governed` 在 shadow_evidence fail-closed，沒有記 observation。 | `app_module/ml_allocation_shadow_evidence.py:1373-1374` 應分別驗 root `schema_version`、`isolated_scope_schema_version` 和 nested coverage schema，保留原有 date/hash/status/safe-flag/decision binding 驗證。 | 不放寬 paper source/custody/credit gate；不把 producer 的 passed 直接當 ML 自然 credit。 |
| P1：daily collector 的自然觀測缺 clock 與必要 context | 9/24 evidence 29 筆全是 contract-blocked；`observation_available_at_missing` 29、`formal_rule_champion_weight_snapshot_missing` 29、`formal_sector_thesis_health_context_missing` 29；自然 credit eligible 0、matured 0，且 `pending_is_normal_wait=false`。 | 修既有 collector/caller：只在真實採集時由 clock 捕獲 `emitted_at`，並接入同次 run 真正存在的 rule/champion 與 sector/thesis context。若來源當次不存在，繼續留 UNKNOWN/blocked；只改善未來記錄。 | 不回填歷史 clock/context、不補 credit、不加新的 formal writer、不更改 maturity/promotion 規則。 |

上述均為能明確指向現有 caller/contract 的工程切片。成熟期、資料品質、模型指標與正式授權分開列在下方，不藉由工程修補自動跨越。

## 每日資料與成熟度讀回

### Natural allocation shadow

最新 daily evidence 是 `D:\Min\Python\Project\FA_Data\output\scheduled\ml_allocation_copilot\natural_shadow_pruning_evidence\daily\2026-09-24\evidence_1ea44683d8fc78c6.json`，41,766 bytes，SHA-256 `2b496282938f786017f4cefc26dfb587e5c209e901139b0e260c92b2ca5b66d0`。它列 29 observations、pending 29、matured 0；H5/H10/H20/H60 的成熟計數全為 0。最新 daily status（`latest_status.json`，13,390 bytes，SHA-256 `7435dde02df685ccfc3eb9b435fec602a7703b0d5927d48668a37ed3f4bb9b0a`）記錄 9/24 cutoff、outcome records 從 763 增至 792（新增 29 個 partial），仍沒有 matured observation，`natural_day_credit_granted=false`。9/25 為非交易日，最新 orchestration status `skipped_non_trading_day`，不計為新的 market-session failure。

Sidecar `D:\Min\Python\Project\FA_Data\output\scheduled\ml_allocation_copilot\shadow_evidence_collector\shadow_evidence.sqlite` 為 53,387,264 bytes，SHA-256 `573c1b5007641c9cbccfb5e9f2523ed18ff1e67f944b4b87633256ce377963b2`。唯讀讀回為 49 observation revisions、29 個決策日（7/31–9/17）、792 outcome revisions。49/49 observation payload 沒有 `emitted_at`、`available_at`、`observation_available_at` 或 `natural_forward_deadline_at`；43/49 明列 `promotion_day_credit_allowed=false`，其餘 6 筆舊列缺此欄位，不能視為 granted。

程式斷點在 `app_module/ml_allocation_shadow_evidence.py:3501-3504,3617-3620`：collector 只有取得 `natural_forward_deadline` 時才捕獲並寫入 `emitted_at`。daily caller `scripts/run_daily_ml_allocation_orchestration.py:2956-3007` 只會在收到可選 `--natural-forward-deadline-at` 時傳值。上述 9/24 artifact 已明列正式 rule/champion snapshot 與 sector/thesis context 欠缺；時鐘修復本身不能解除這兩個 contract blocker。

現 gate 要求每一個 H5/H10/H20/H60 horizon 至少 20 個成熟觀測、20 個自然 shadow 日，並覆蓋兩種 downside class；此輪各項均未達標。29 筆裡另有 29 筆 `natural_day_credit_not_allowed`、29 筆 `completed_horizons_incomplete`，所以「等待 H60」不能解釋全部阻塞。歷史判讀入口：[Natural Shadow Weekly Evidence Audit](NATURAL_SHADOW_WEEKLY_EVIDENCE_AUDIT_2026_09_20.md)；本報告以上述 9/24 原始讀回更新其舊樣本數，不取代 gate 定義。

### Formal calibration

正式 DB `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`（3,827,728,384 bytes）以唯讀方式查詢：Evidence Event 67,699 筆，決策日 7/30–9/24；Evidence Outcome 172 筆、43 個 distinct event IDs。H5 有 10 ready／33 insufficient，H10 有 1 ready／42 insufficient，H20 與 H60 各 43 筆 insufficient。

9/25 `inspect_recommendation_calibration.py --db-path <formal-db> --format json` 輸出 `not_evaluable`：258 included events、172 outcomes、430 excluded、0 observations、0 folds，H5/H20 可評估 horizon counts 都是 0。Diagnostics 為 `missing_outcome_5d:215`、`missing_outcome_20d:215`、`universe_policy_assumed:215`、`universe_policy_mismatch:43`。研究決策是 `retain_current_method_insufficient_matched_oos`。短期工程修補不能用補零、歷史日期重播、或重訓取代缺少 matched OOS 的事實。

門檻依據：[V4.1 Recommendation Calibration Vertical Slice](V4_1_RECOMMENDATION_CALIBRATION_VERTICAL_SLICE_2026_09_10.md) 與 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 的 V4 formal boundary：需要自然 Forward/Paper/Live、P0 source acceptance、PIT/available-time、成本與成交、calibration/downside/regime stability、具名 review 及 rollback；工程完成、research receipt 或 scheduler ready 不足以授予 formal。

## Allocation／bounded 研究 family 與個股 UI

本輪只讀現成 receipts 的原始 JSON bytes，沒有載入它們引用的任何 pickle/joblib。

| 家族／receipt | 原始讀回 | 已有結果與資格原因 |
|---|---|---|
| H5 allocation | `E:\codex_model_repair_20260923\candidate_formal_repair_run01\h5_current_inference\current_shadow\aa0684a06502d2ec56df79de94886ce19496c5b89b4cc38acf2426622f6237c7.json`；79,333 bytes，raw SHA-256 `0ebd28eece19f600ebb54f778100a78be06e10ec76d140221778d419caf2933a`。 | `restated-allocation-current-shadow.v1`，13 檔，feature as-of 9/23、capture 9/24 09:41:34+08；release `restated-repair-4db92a237e3ad10a`，model `baldr-ml-allocation-restated-revision-aware-ridge-logistic-h5-rank-v2`。Signal 有 integer bp 欄位，非必須重算：例如 1101 的 downside 7,593 bp、expected excess −125 bp、expected sector excess `null`。Proposal coverage 8,613 bp，missing families 為 `market_sector_cross_section` 與 `price_liquidity_technical`，missing head 為 `expected_sector_excess_return_bp`；fallback `feature_pack_missing_or_partial_missing_mask`。Target summary 是全現金／neutral meta，`model_learned_allocation=false`，turnover 0。historical PIT、formal OOS、production action 均 false、alpha 0。 |
| Bounded | `E:\codex_model_repair_20260923\candidate_formal_repair_run01\bounded_current_inference\bounded_current_heads\69477a334f3094ee4cfaa56b681942744030c34dd77eaaf24e365855dc679fef.json`；230,388 bytes，raw SHA-256 `e9a7c8ff8ded4210ca39ffdb36fcb92a45af80d95028b0187160dc0f9be35a7d`。 | `bounded-restated-current-heads.v1`，相同 13 檔、feature as-of 9/23、capture 9/24 10:10:33+08；每列 24 experts、四個 horizons，共 312 個 heads。312/312 heads 缺 `expected_sector_excess_return_bp`；`allocation_proposal=null`、`promotion_eligible=false`、historical PIT/formal/production false、alpha 0。它是 prediction readback，不是配置或下單結果。 |

這些 13 檔為 `[1101, 1216, 1256, 1301, 1477, 2002, 2303, 2317, 2330, 2412, 2454, 2881, 6505]`。H5 receipt 沒有獨立的 `available_at`；UI 必須分開顯示 `feature_asof_date=2026-09-23`、`captured_at=2026-09-24` 和 availability `unknown`，不可沿用現行 `_ml_source` 把 `inference_at` 同時當 data-as-of 與 available-at（`app_module/stock_research_report_service.py:1445-1457`）。

**個股 UI 最窄設計提案：**

1. 在 app 層新增 read-only typed provider／read model，僅解析 configured family receipt、驗 receipt/schema/hash、model/dataset/release identity 和 symbol row；對已存在 `StockResearchReportReadService.ml_provider` seam 回傳 DTO。`app_module/restated_allocation_shadow_service.py` 與 `app_module/bounded_restated_shadow_service.py` 是會載入模型並執行 inference、落檔的 producer，不可從 UI 呼叫。
2. DTO 至少分開 `family_id`、`model_id/release_id`、dataset identity、decision date、feature as-of、captured clock、explicit optional available clock、receipt hash、prediction bp、missing family/head、fallback/qualification reasons、formal/PIT/production flags 與 alpha。未知值保留 UNKNOWN；整數 bp 原樣投影，不轉 float、不新算預測。
3. 先只顯示本輪已驗證的 13 檔 research receipt；同頁明示「研究候選／未 promotion／不具 formal 或下單權限」，並同列 missing features、cash-only target 和模型品質限制。超出 receipt coverage 的股票顯示 unavailable + 原因，不搜尋其他目錄或即時推論。
4. H5 OOF QA 顯示三組 feature pack 的 return MAE 模型／baseline 為 488/489、483/489、488/489 bp；downside Brier 為 22,631,852/22,388,860、23,027,452/22,388,860、22,394,066/22,388,860 bp²。三組 Brier 均未勝 baseline，QA 結論未 promotion。Bounded pooled OOF 中兩個算法、四個 horizons 的 return MAE 與 downside Brier 皆高於 baseline。這些品質原因應與「推論已產生」分欄，不能由 receipt status `completed` 隱去。

目前 UI 結構及 seam：[main.py](../../ui_qt/main.py)（320–325）、[read service](../../app_module/stock_research_report_service.py)（100–113、1404–1457）、[DTO](../../app_module/stock_research_report_dtos.py)（212–222）、[view](../../ui_qt/views/stock_research_report_view.py)（1441–1457）。既有模型候選驗收：[Repaired Source Model Candidate QA](REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)；training 與 heldout 限制：[Restated Allocation Repair Training](RESTATED_ALLOCATION_REPAIR_TRAINING_2026_09_23.md)。Direct/OOC 產物與解讀依指令保持凍結，不在這份報告重新分析或拆分。

## Recommendation calibration learner 同日 snapshot 與資料／決策時間

9/25 Shadow snapshot status `D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_snapshot\latest_status.json` 是 57,543 bytes，SHA-256 `07befd6c7960a79a5f98a3b455ca560d819d57e5d1c0e2908aab78816686df05`；status passed、decision date 9/25、result id `rec_d9e6903135ea4fcd8dd7a6520e1842bc`。Cohort hash `sha256:39288495c9496b70937f8b212b7ba55be8cef5b50c7036577ba61a5437b10d31`，200 requested、3 eligible、197 degraded、0 missing。

同日結果已寫進 `D:\Min\Python\Project\FA_Data_Shadow\recommendation\runs\execution_artifacts\1e2c18967937227eff95daf8effdbbec5215fc4a358366734dba3c7cdb3b05b7.json`，1,094,095 bytes，SHA-256 `ce7c5b7a34c3f7363b69d20ce741ed95f4a7b1d182b275439d486046c4c0a880`。Index row 對應 schema `recommendation-execution.v1`、payload hash `sha256:d21227edcac82024efe0fdcbfbf324890827581ec08495ad0b1edf2fcebbcfef`、persisted at `2026-09-25T12:54:34.127251+00:00`。typed context 為 as-of 9/24、available at `2026-09-25T12:54:17.526749Z`、decision at `2026-09-25T12:54:33.745617Z`；warnings `calibration_feature_source_unavailable:ValueError`、`legacy_source_identity_unbound`，quality degraded。

`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\latest_status.json` 為 2,683 bytes、SHA-256 `850c63a1e2f382dc6b79e9281786ad9e2e40a2131f7c81c6852a18829171e905`；`failed_dependency`、reason `symbol_cohort_preflight_failed:ValueError`、candidate/dataset 為 null、natural matured count 0；dataset build、candidate training、same-date comparison、training lineage 均 skipped。pipeline overall status 在 `scheduled/recommendation_calibration_learning/latest_status.json`，9/25，SHA-256 `ad58b6639813effe7a2cebe30ad119bf691eec17fb02c8cc917ae2a58383cb8b`；recommendation_snapshot passed、recommendation_learning failed，另有獨立 data_update_quick failure，不把兩個 stage 合併成一個原因。

9/25 當次 learner 的錯誤路徑是歷史狀態：舊版 `_find_same_day_snapshot` 只掃 `recommendation/runs/*.json` 並讀舊 `config.scheduled_snapshot`／`decision_date`，無法讀取 `execution_artifacts/` 內的 typed `recommendation-execution.v1`。此差異是 producer/consumer artifact contract 不相符，不是 cohort 無資料。

現行 pipeline 從本次 snapshot child stdout 中解析唯一完整的 scheduled-snapshot JSON payload，核對 child task、決策日、typed cohort schema/hash 與 `result_id`，並保留原 stdout bytes 的 SHA-256；不重新讀可被同日其他 run 覆寫的 `latest_status.json` 來決定 snapshot identity。Learner 收到 `result_id`、cohort hash 與 invocation stdout SHA 後，只用 `build_recommendation_execution_queries(...).get(result_id)` 取該筆保存結果，並要求 canonical index/payload 驗證、支援的 schema/revision、原 artifact SHA 與 payload hash、completed typed execution、scheduled config、相符的 decision date、request/context 兩處相符的 `data_as_of_date`、當地決策日相符的 aware `decision_at`，以及 config cohort 與 typed context cohort 完全一致且 hash 等於 child 傳入值。Eligible symbols 另須與保存的 decision rows 一致。完整性或 typed-contract 錯誤會 fail closed；不 fallback 到 legacy JSON、固定 symbols 或 latest snapshot。`--symbols` 仍是受控明示輸入路徑。

Learner 將 `data_as_of_date=2026-09-24` 與 `decision_date=2026-09-25` 分開保留。`available_at` 若存在須帶時區並原樣記錄；若缺失就保留 `None`，不從 context date 或 decision clock 推導。這與 recommendation calibration 來源證據的 clock 要求一致，不會把 personalization 狀態或資料成熟度混入此 cohort resolver。

### 修復驗證

新增 `tests/test_recommendation_calibration_snapshot_resolution.py`，覆蓋同日兩個 run 選擇、cohort/hash 衝突、request/context/decision date 漂移、legacy／typed 完整性 fail-closed、CLI integrity exception terminal status，以及缺少 `available_at` 不補時鐘。Pipeline synthetic test 覆蓋 child handoff 後 `latest_status.json` 被另一 run 覆寫、stdout 缺失／歧義、schema 錯誤與原始 stdout hash。maturity／rollback regression 使用正式唯讀 lease 實作，只替換合成資料查詢。Focused learner suite 與 `py_compile` 結果列於本報告「唯讀 QA 收據」。這些是 synthetic contract 驗證，沒有執行正式 scheduler 或 training；9/25 原始 failed learner artifact 未被回填或重寫。

Recommendation calibration active pointer 目前為 rule-only、active candidate null；learner readback 的 natural matured count 為 0，這是 calibration evidence。Personalization 是不同 family；本輪沒有讀取其專屬 artifact、user action/outcome 或 maturity receipt，因此不推定其樣本數、資格或 V6 adoption 狀態。其 evidence-driven personalization 方向仍依 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 的獨立門檻判讀。

## 其他 family 門檻與狀態分帳

| Family | 9/25 可確認狀態 | 後續分類 |
|---|---|---|
| Calibration | 258 included／172 outcomes／0 evaluable observations／0 folds，`not_evaluable`。 | 先修實際 read/contract blockers；缺少 outcome、自然 maturity 與 matched OOS 是資料及時間門檻，不靠新模型 fit 解決。 |
| Allocation H5 | 13 檔 research inference 已產生；質量指標沒有一致勝 baseline，cash-only target，不具 PIT/formal/production 權限。 | 有界 read-only UI 可顯示；promotion blocked by quality/governance evidence。 |
| Bounded | 13×24=312 個 expert heads 已有 receipt；另有 312 個 sector excess heads missing；現有 pooled OOF 不勝 baseline。24 個 experts 已涵蓋四個 horizons，不應再乘一次 4。 | 可顯示 prediction receipt、缺失與限制；不等同舊 operational family 的修復／替代或 promotion。 |
| Direct/OOC | 本輪依明確指令凍結。 | 不重跑、不拆分、不改行為。 |
| Personalization | 本輪未讀取 personalization 專屬 artifact／user action／maturity evidence；calibration pointer 與 learner 的 matured count 不代表 personalization。 | 維持未確認；需由 personalization 自身 evidence/readback 判定，不借用 calibration cohort 或 maturity。 |

R027 仍 INCONCLUSIVE、R028 仍 BLOCKED。本盤點只辨識 read-only 證據和必要工程切片，不宣告 Daily Evidence、Calibration、模型品質、UI 使用資格或任何 family PASS。

## 唯讀 QA 收據

- 原始正式 DB／natural artifact readback：`C:\Users\archi\AppData\Local\Temp\baldr_daily_evidence_model_readiness_20260925_688766d51ca743e39db96cd7b6ae2c6f\audit_readback.py`（SHA-256 `7f526327257e33a69da42c8208ac6e69f8874d89cc6800caa58e86f8b41a6964`），輸出 `readback.json`（SHA-256 `e10a12f32a2633db4a98daf1040be9910d65f2961d29b10fb9f2746bc5a95877`）。
- Recommendation calibration index／typed artifact 及 H5／bounded receipt readback：`C:\Users\archi\AppData\Local\Temp\baldr_daily_evidence_model_readiness_20260925_688766d51ca743e39db96cd7b6ae2c6f\artifact_readback.py`（SHA-256 `587ef1943e75db631bcd1f78acabd51119d4039f6085ff27847b69d999c16fcf`），輸出 `artifact_readback.json`（SHA-256 `05944bd923e86687d3bae22b622be97b2bb145ed6ae1feac55d9674070e9b502`）。Script 只讀 JSON bytes 和 readonly SQLite index；未讀取 model binary。
- 修復後 synthetic learner 驗證：`.venv\\Scripts\\python.exe -m pytest tests\\test_recommendation_calibration_snapshot_resolution.py tests\\test_daily_recommendation_learning_loop.py tests\\test_recommendation_calibration_contract_guards.py -q -o addopts= -p no:cacheprovider`，**65 passed**。另對 5 個變更 Python 檔執行 `py_compile`，exit 0。沒有跑正式 scheduler、model load、training 或 inference；正式 pointer 與 artifacts 未改寫。獨立 QA 尚待執行。

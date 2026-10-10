# BALDR B13 模型輸入契約 QA（2026-10-06）

> **日期與資格提示（2026-10-10）：** 本收據限定 synthetic／offline 契約；formal、training、production 與 historical PIT 旗標維持 false。它不構成 production composition 或模型訓練授權；文末 rollback／`Remove-Item` 命令是歷史交接，不要直接執行。

## 變更範圍與 API

本批只新增三個檔案：

- `app_module/rule_research_model_input_adapter.py`
- `tests/test_baldr_b13_model_input_adapter.py`
- `docs/06_qa/BALDR_B13_MODEL_INPUT_20261006.md`

主要型別與函式簽名如下；此介面可供 B14 消費契約，`ModelInputRunner` 是注入的有界 Protocol port，adapter 本身不匯入 `ml_module`。這不代表 production composition 已授權：

```python
@dataclass(frozen=True, slots=True)
class ModelInputPolicy: ...
@dataclass(frozen=True, slots=True)
class ModelInputSample: ...
@dataclass(frozen=True, slots=True)
class ModelInputEvidence: ...
@dataclass(frozen=True, slots=True)
class PreparedModelInput: ...
class ModelInputRunner(Protocol):
    def run(self, prepared: PreparedModelInput) -> ModelInputRunnerResult: ...

def prepare_model_input(
    policy: ModelInputPolicy,
    samples: Sequence[ModelInputSample],
    evidence: ModelInputEvidence,
    *,
    fair_denominator: Sequence[ModelInputFairDenominatorRow],
    preprocessing_audit: TrainingPreprocessingAudit | None,
) -> PreparedModelInput: ...

def run_prepared_model_input(
    prepared: PreparedModelInput,
    *,
    runner: ModelInputRunner,
) -> ModelInputRunResult: ...
```

所有 DTO 為 frozen dataclass 並複製巢狀序列為 tuple。錯誤 DTO 型態在建構或函式入口以 `TypeError` 拒絕；正確型態但缺政策/證據回 `waiting`，資料矛盾或不支援的樣本回 `reject_fit`。`PreparedModelInput` 的 seal、重算身份、blockers 與獨立樣本數會在每次呼叫 runner 前重驗。

## 可接受範圍與封鎖條件

本版只實作呼叫端明確聲明的 `endpoint_gross_return_bp`：以首個決策日收盤價至末個 horizon session 收盤價計算 gross bp，採 Decimal 與 `ROUND_HALF_EVEN`。唯一接受的 price basis/version、cost policy、benchmark 與 metric 分別是 `raw_ohlc_no_corporate_action`、`b13-endpoint-gross-v1`、`gross-no-cost:v1`、`none:gross-no-excess`、`gross_return_bp`；net、excess、path extrema 等 target 尚無契約，不會自行換算。所有欄位由 caller 提供，U2 欄位未決時回 `waiting`。

ready 輸入僅能使用固定 `synthetic://offline` 命名空間及合成 evidence pins，代表工程 fixture 可通過驗證，不代表來源資格、自然證據、PIT、正式評估或訓練資格。所有正式、訓練、PIT、自然證據、執行與生產動作資格旗標恆為 `False`。pin 綁定 actual session calendar、custody、path/label、source、artifact bytes 及 training audit 的精確內容 SHA-256；artifact 只 hash bytes，不反序列化。feature registry/schema hash 依既有 HistoricalFeatureBuilder 契約核對。

每個樣本需具完整 caller calendar 中的決策日與 horizon session、可用 OHLC Decimal、明確 availability 與無公司行動聲明；缺價、停牌、來源日曆缺件、可用日穿越決策或未知公司行動皆不會被補值。features 與可用日必須早於決策日。標籤端點必須等於封存路徑首末收盤計算值且已成熟。Train/evaluation 範圍、label maturity、purge、embargo 均依 caller split 及傳入的完整 session calendar 實測；preprocessing audit 必須逐筆列出 training row IDs、最大可用日與 cutoff。

公平分母必須由 caller 明示。每個 method 都需覆蓋同一 `(symbol, decision_date)` 宇集；represented 列只能引用保留樣本，missing/excluded 列需有理由。相同標的與決策日只保留一個獨立樣本，不因方法列重複計數。既有 one-date runner 一次僅收一筆 evaluation row；零筆或多筆會在準備階段拒絕，runner 不會被呼叫。runner 回執需帶有界 immutable JSON bytes、匹配的 identities/hash 及 prediction；輸出 downside probability 限於 0–10000 bp，uncertainty 不可為負。

測試 bridge 只在測試程式中使用既有 `HistoricalFeatureRow`、`HistoricalFeatureBuilder`、`ModelArtifactManifest`、`ShadowModelArtifactLoadResult`、`HistoricalMLShadowRunReport` 及 `OneDateShadowInferenceService` DTO/API。它以 stub predictor 與 memory registry 實際呼叫 `run_one_date`，不載入檔案、不建立 SQLite/真 DB，也不 deserialize artifact、不執行真 fit。

## 驗證紀錄

- B13 自有 suite：使用 repo `.venv` 執行 `python -m pytest tests/test_baldr_b13_model_input_adapter.py -q -o addopts= --basetemp=C:\Users\archi\AppData\Local\Temp\baldr-b13-root-final-2`，root 最終獨立驗證結果 `40 passed in 0.50s`（零 fail／skip）。含空 session 路徑，以及深層／超長整數 JSON 回執的結構化拒絕。
- 固定 base 上既有 forward outcome、label readiness、fair comparison suites 為 `47 passed`，由整合 owner 在本 lane 開工前執行。
- 本 lane root 的 adapter focused mypy（`--follow-imports=silent`）、adapter／test `py_compile`、`quant_guard_linter` 均通過；focused mypy 並不代表全倉型態檢查已通過。
- ML AST shadow guard 現掃描 664 files；本批新增 0 violations，總數仍有 base 已存在的 8 項。此數字是「新違例為零」，不是全倉 guard pass。

## 規格來源與文件權威

本 QA 使用下列規劃文件作為 B13 範圍輸入；列出的 SHA-256 是讀取時的來源檔身份：

| 規劃輸入 | SHA-256 |
|---|---|
| `output/plans/baldr_completion_inventory_astra_20261006.md` | `1b724facbbc1712cc93ca3ddb204ea95f2ebb5efd1bdb18cc1733a3ff005be60` |
| `output/plans/baldr_completion_review_sol_20261006.md` | `8e97eca8f1ae3da4538b441b246fa0b36535f1a97c34c416c488079a253f264e` |
| `output/plans/baldr_product_experience_plan_20261004.md`（唯一原 plan，本 lane root 初讀） | `c4126a56cbe6a1c28b541222f11616af26b18a7149ed29ac8d402a53e729fc85` |

規劃附件提供工作範圍，不能取代 repo 現行 SSOT。依根 `AGENTS.md`：目前狀態以 `docs/00_core/PROJECT_SNAPSHOT.md` 為準；權威入口是 `docs/00_core/DEVELOPMENT_ROADMAP.md`；產品、工程、長期 maturity 與舊工作承接分別以 `PRODUCT_ROADMAP_POST_REFACTOR.md`、`ROADMAP_6M_ENGINEERING.md`、`VERSION_ROADMAP_V2_1_TO_V4_0.md`、`LEGACY_ROADMAP_CARRYOVER.md` 為準。這一 lane 沒有改這些共享文件。B15 整合 owner 應依最後整合後的實際行為，判斷是否同步 `docs/07_guides/APPLICATION_MANUAL.md`、`docs/00_core/PROJECT_SNAPSHOT.md`、架構／路由／`docs/00_core/DOC_COVERAGE_MAP.md` 與唯一原 plan；不得將本工程 fixture 描述成正式資料資格或已授權生產流程。

## 回滾

整合提交後以該 B13 commit 的 hash 回滾；不要在共享分支上直接刪除檔案：

```powershell
git revert <B13commit>
```

若變更仍未提交且只需撤回本 lane 的新增檔案，才於 repository root 執行：

```powershell
Remove-Item -LiteralPath `
  'app_module/rule_research_model_input_adapter.py', `
  'tests/test_baldr_b13_model_input_adapter.py', `
  'docs/06_qa/BALDR_B13_MODEL_INPUT_20261006.md'
```

以上是回滾步驟紀錄，QA 執行期間未執行。

## Frozen API 欄位快照

以下為本次 adapter 的實際 constructor signatures；PreparedModelInput 必須由 prepare_model_input 建立，私有 seal 不供 caller 建構。hash 格式均為 sha256: 加 64 位小寫 hex。

```text
ModelInputTimeSplit(train_start_date: 'str', train_end_date: 'str', evaluation_start_date: 'str', evaluation_end_date: 'str', training_as_of_date: 'str', label_as_of_date: 'str', purge_sessions: 'int', embargo_sessions: 'int') -> None
ModelInputPolicy(primary_target: 'str | None', horizon_sessions: 'int | None', split: 'ModelInputTimeSplit | None', cost_policy_version: 'str | None', benchmark_id: 'str | None', price_basis: 'str | None', price_basis_version: 'str | None', metric: 'str | None') -> None
ModelInputPathBar(trading_date: 'str', open: 'Decimal | None', high: 'Decimal | None', low: 'Decimal | None', close: 'Decimal | None', available_date: 'str | None', state: 'str', corporate_action_status: 'str') -> None
ModelInputSample(row_id: 'str', symbol: 'str', phase: "Literal['training', 'evaluation']", decision_date: 'str', feature_as_of_date: 'str', feature_available_date: 'str', features: 'tuple[tuple[str, int | None], ...]', actual_session_dates: 'tuple[str, ...]', path: 'tuple[ModelInputPathBar, ...]', target_value_bp: 'int | None', horizon_end_date: 'str', label_available_date: 'str') -> None
ModelInputFairDenominatorRow(symbol: 'str', decision_date: 'str', method_id: 'str', status: "Literal['represented', 'missing', 'excluded']", row_id: 'str | None', reason: 'str | None') -> None
TrainingPreprocessingAudit(fitted_row_ids: 'tuple[str, ...]', max_available_date: 'str | None', fit_cutoff_date: 'str | None') -> None
ModelInputSourcePin(role: 'str', namespace: 'str', source_id: 'str', content: 'bytes', content_sha256: 'str', metadata: 'bytes' = b'', metadata_sha256: 'str | None' = None) -> None
ModelInputEvidence(dataset_id: 'str', model_id: 'str', run_id: 'str', source_id: 'str', feature_registry_sha256: 'str', feature_schema_sha256: 'str', feature_schema: 'tuple[tuple[str, str, str], ...]', actual_session_calendar: 'tuple[str, ...]', pins: 'tuple[ModelInputSourcePin, ...]') -> None
PreparedModelInput(status: 'ModelInputStatus', blockers: 'tuple[str, ...]', policy: 'ModelInputPolicy', samples: 'tuple[ModelInputSample, ...]', evidence: 'ModelInputEvidence', fair_denominator: 'tuple[ModelInputFairDenominatorRow, ...]', preprocessing_audit: 'TrainingPreprocessingAudit | None', independent_sample_count: 'int', identity_sha256: 'str', _seal: 'str' = '') -> None
ModelInputRunnerResult(status: "Literal['available', 'unavailable']", prepared_identity_sha256: 'str', dataset_id: 'str', model_id: 'str', run_id: 'str', source_pins_sha256: 'str', result_identity_sha256: 'str', result_payload: 'bytes', blockers: 'tuple[str, ...]' = ()) -> None
ModelInputRunResult(status: 'ModelInputRunStatus', prepared_identity_sha256: 'str', dataset_id: 'str', model_id: 'str', run_id: 'str', source_pins_sha256: 'str', result_identity_sha256: 'str | None', blockers: 'tuple[str, ...]', result_payload: 'bytes | None' = None) -> None
build_synthetic_offline_evidence(policy: 'ModelInputPolicy', samples: 'Sequence[ModelInputSample]', *, fair_denominator: 'Sequence[ModelInputFairDenominatorRow]', preprocessing_audit: 'TrainingPreprocessingAudit', dataset_id: 'str', model_id: 'str', run_id: 'str', source_id: 'str', feature_registry_sha256: 'str', feature_schema_sha256: 'str', feature_schema: 'tuple[tuple[str, str, str], ...]', actual_session_calendar: 'tuple[str, ...]', model_artifact_bytes: 'bytes') -> 'ModelInputEvidence'
```

Runner receipt schema_version 固定 baldr-b13-runner-result.v1，JSON exact keys 為 prepared_identity_sha256、dataset_id、model_id、run_id、source_pins_sha256、sample_row_id、symbol、decision_date、status、prediction、blockers，另含 schema_version。available prediction exact keys 為 prediction_id、symbol、return_prediction_bp、ranking_score_bp、downside_probability_bp、uncertainty_bp；unavailable 時 prediction 為 null 且 blockers 非空。caller 只消費回傳的 result_payload 與對應 hash。

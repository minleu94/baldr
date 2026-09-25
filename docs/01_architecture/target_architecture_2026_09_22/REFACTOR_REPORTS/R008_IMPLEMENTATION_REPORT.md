# R008 實作報告：推薦決策與 execution contracts

## 審查狀態

**READY_FOR_REVIEW**。這是實作交付，不是 R008 gate 的 PASS 宣告。

## 變更範圍

新增 `decision_module/recommendation/contracts.py` 與 `app_module/recommendation/contracts.py`，並建立兩個 recommendation package。依 `R008_SCOPE_ADDENDUM.md`，另將兩個 parent package 的原 public exports 改為窄 lazy exports，讓 leaf contract imports 不載入服務或非程式資源；只調整 `tests/test_update_service_import_contract.py` 的載入時序 oracle，保留原 public export 與 class identity assertions。ML availability 回修在 `app_module/recommendation/__init__.py` 公開新增的 availability record/status/reason。沒有修改 RecommendationService、既有 DTO、演算法、ML schema、UI、codec 或 save 流程，也沒有接上 production consumer。

本次 R008 自有檔案如下：

- 修改：`app_module/__init__.py`、`decision_module/__init__.py`、`tests/test_update_service_import_contract.py`
- 新增：`app_module/recommendation/__init__.py`、`app_module/recommendation/contracts.py`、`decision_module/recommendation/__init__.py`、`decision_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py`、本報告

工作樹中其他既有 dirty/untracked 檔案均保留，未 stage、commit 或 push。

## 欄位歸屬

| Owner | Contract | 欄位／責任 |
|---|---|---|
| decision | `UniverseReference` | `policy_id`、`snapshot_id`、`as_of_date`、`members_hash` |
| decision | `FactorContribution` | `factor_id`、`value`、`unit`、`version`、`source_refs` |
| decision | `RecommendationItem` | `stock_code`、`stock_name`、原規則 `rule_score`、`factor_contributions`、`rank`、`universe_ref`、`reasons`、可選 `confidence`、`score_percentile_bp`、`eligible_universe_size`、`eligible_universe_date`、`ranking_method`、`threshold_mode`、`regime_match` |
| decision | `FilterOutcome` | `filter_id`、`passed`、`reason`、`evidence` |
| decision | `NegativeEvidence` | `evidence_id`、`reason`、`source_refs`、`observed_at`、`details` |
| decision | `LiquidityAssessment` | `acceptable`、`reasons`、`missing_data`、`evidence_refs`、`observations` |
| decision | `CandidateAssessment` | `stock_code`、`eligible`、`filter_outcomes`、`negative_evidence`、`reasons`、`liquidity`、`missing_data` |
| decision | `RegimeStateTransition`、`DecisionBatch` | 前者保存 prior/next state、日期與原因；後者保存有序 `items`、`assessments`、`regime` 與可選 state transition。items 與 assessments 各自要求 stock code 唯一。 |
| app | `VersionReference` | `kind`、`reference_id`、可選 `version`；runtime、replay、portfolio、evidence 與 ML receipt navigation ID 以 typed reference 表示。 |
| app | `Request` | `as_of_date`、config/profile/strategy/policy/universe-policy typed refs；不提供無型別 `options` 擴充字典。 |
| app | `Context` | 可未知的 `as_of_date`、aware `decision_at`、`source_refs`、data-snapshot refs、config/profile/strategy/policy/universe refs、algorithm ref、`input_quality`、`warnings`。歷史未知值保留 `None` 或 unknown 狀態。 |
| app | `QualityReport`、`ExecutionEvent` | 品質 status/warnings/metrics，以及事件 type/message/aware clock/details。 |
| app | `MLAvailability` | `status` 明示 not-requested/unknown/available/unavailable/blocked；缺值或拒絕時保存 typed `reason` 與可選不可變 `reason_detail`。 |
| app | `MLReceiptBinding` | ML_RECEIPT `receipt_ref` navigation ID、`receipt_hash`、`result_id`、`decision_date`、`model_candidate_id`、唯一 `projected_stock_codes` tuple、可未知的 `cost_scenario_hash`。 |
| app | `RecommendationExecution` | `result_id`、`request`、`context`、terminal `status`、唯一的 `decision: DecisionBatch \| None`、quality、獨立 `ml_availability`、events、related refs、ML projection refs 與 typed `MLReceiptBinding` tuple、可選 `failure_reason`。schema version/revision 是固定 class/schema metadata。 |
| app | `SaveReceipt` | `result_id`、payload hash、artifact location、aware `persisted_at`、index status、schema version/revision。 |
| R007 | `SourceRef` | 作為來源 leaf contract 使用，owner 仍為 R007；R008 不修改該型別。 |

`RecommendationExecution.items` 與 `.assessments` 是唯讀 property，直接委派至 `decision`，不是 dataclass fields，也沒有第二份保存空間。`related_references` 只接受 runtime/replay/portfolio/evidence kinds；config、data、universe、ML projection 與 ML receipt 各由其專屬欄位保存。ML 狀態不從 refs 或 terminal status 推算；空 refs 可明確對應 not-requested、unknown、unavailable（需原因）或 blocked（需原因）。unknown 可保留 refs 而不被改判為 available。available 必須有 projection 與完整 typed receipt binding，not-requested 不可帶這兩類 refs。

## 深凍結與拒絕規則

兩側 contract 各自持有封存 helper。helper 僅接受明示 contract whitelist 中的 frozen dataclass、tuple/list、mapping、`str`、`int`、`bool`、`None`、有限 `Decimal`、明示列名的 enum、date 與帶時區 datetime。app enum 只接受 `ReferenceKind`、`ExecutionStatus`、`QualityStatus`、`IndexStatus`、`MLAvailabilityStatus`、`MLAvailabilityReason` 六個 exact 型別；任意外部 Enum（包括帶 mutable attribute 的成員）會拒絕。dataclass 必須是白名單中的 exact class；一般外部 frozen dataclass 或 contract subclass 不會作為逃生擴充口。數值 scalar 使用 exact int/Decimal 檢查，因此 bool 不會混入 int 欄位，也不會把 legacy float 轉成 Decimal 或基點。

list 會遞迴轉為 tuple；只有在 runtime 已確認輸入精確為 tuple/list 後，才以窄 `cast(Sequence[object], ...)` 告知型別檢查器其可迭代形狀。每個 mapping 都先複製成新的 backing dict，遞迴凍結值後再包成 `MappingProxyType`；key 只接受 exact `str`。active-path identity 檢查拒絕循環結構。dataclass 必須是白名單中的 exact class；一般外部 frozen dataclass 或 contract subclass 不會作為逃生擴充口。數值 scalar 使用 exact int/Decimal 檢查，因此 bool 不會混入 int 欄位，也不會把 legacy float 轉成 Decimal 或基點。typed `_freeze_tuple` 只在逐項 exact type runtime 驗證後 cast 回 tuple[T, ...]；沒有使用寬泛 `type: ignore`。naive datetime、非有限 Decimal、float、錯誤 mapping key、未列名 dataclass、一般物件、callback 與 live file handle 均拒絕。輸入的 mapping proxy 也會複製 backing dict，因此後續改動原 dict 或其巢狀 list 不會改變已封存值。

Execution terminal rules 為：`completed` 必須帶 `DecisionBatch`，即使 items 為空，且不得帶 `failure_reason`；`failed` 與 `cancelled` 必須沒有 decision，並必須保存非空白 `failure_reason`，診斷可另留在 events/quality，避免 partial items 經便利 property 被當成已完成推薦發布。結果 ID 驗證沿用 `rec_<uuid>`。schema metadata 固定為 `recommendation-execution.v1` 與 revision `1`；artifact writer 尚未發布。

ML availability 獨立使用 `MLAvailabilityStatus` 與 `MLAvailabilityReason`。not-requested、unknown、available 不接受缺值原因；unavailable 與 blocked 都必須記錄明示原因。typed reason 涵蓋 missing、schema-mismatch、quarantined、source-version-unavailable、cutoff-unproven 與 policy-blocked；reason 保持與 status 分離，不由 reason 猜 status。`reason_detail` 只接受不可變非空字串。這保留缺 projection 與具體原因，不填補 0，也不把 quality、terminal outcome 或 persistence receipt 混成 ML availability。

`MLReceiptBinding` 是 app-owned frozen 純值摘要，只包含既有 `ML_RECEIPT` `VersionReference` navigation ID、小寫 `sha256:<64 hex>` 格式的 receipt hash、符合 `rec_<uuid>` 的 result ID、decision date、非空 model candidate ID、非空、精確且不重複的 projected stock-code tuple，以及可未知的 cost-scenario hash（已知時必須同為小寫 SHA-256 格式）。Execution 核對每個 binding 的 result ID；若 `Context.as_of_date` 已知，必須與 binding date 相同；若有 `DecisionBatch`，投影股票必須屬於其 items 或 assessments stock-code 集合。unknown 可攜帶已局部核對的 refs 但仍維持 unknown；available 至少需要 projection ref 與通過上述本地檢查的 binding。零列 completed execution 合法但不會有 receipt binding：既有 `build_inference_projection_receipt` 明確拒絕空 projection rows（`ml_module/recommendation_inference_provenance.py:795`），因此 binding 拒絕空 tuple/list；零列 execution 測試以空 receipt refs 與 unknown availability 表達，不合成 receipt。

這些是 R008 的本地值形狀與一致性檢查，並非 readback：未讀取 receipt 檔案、未驗實際 receipt body/hash、candidate/symbol 與實際 projection rows、cost-scenario hash 或任何值與 `PreparedMLInput` 的真實一致性，也沒有驗證 publication 時序。未知的 context date 不由 binding 回填；未加入 cutoff/mode/decision_at 摘要或未被證明的 cost lane identity。實際 receipt 與 PreparedMLInput 的完整一致性由 R010 boundary contract 及 R026 production wiring 驗證，R008 不宣稱端到端 ML compatibility。

## 舊 DTO、ML projection 與 wire 欄位

R008 未改 `app_module/dtos/__init__.py`。`RecommendationDTO` 的既有 rule/UI payload 包含 `stock_code`、`stock_name`、`close_price`、`price_change`、`total_score`、`indicator_score`、`pattern_score`、`volume_score`、`recommendation_reasons`、`industry`、`regime_match`。其中 close price 型別為 `float | Decimal`，其餘價格變動與 score 欄為 float。現有 `from_dict` 會用 `Decimal(str(close_price))` 建 close price，並以 `float(...)` 建 price change 與四個 score；`to_dict` 輸出中文 wire key（例如 `證券代號`、`收盤價`、`漲幅%`、`總分`、`推薦理由`、`Regime匹配`），並在 quantile mode 加上百分位顯示欄。R008 保留這套舊行為，沒有做 legacy → canonical 數值轉換，也沒有量化、改精度或改 tie-break。

舊 DTO 的追溯欄 `score_percentile_bp`、`eligible_universe_size`、`eligible_universe_date`、`ranking_method`、`threshold_mode` 對應部分 canonical decision 欄位；舊 DTO 的 `eligible_universe_date` 是 Optional[str]，而 canonical item 使用 Optional[date]，轉換尚未實作。舊 `float` rule score/price 欄的 legacy → canonical 數值轉換（包含精度／單位決策）留給 R009/R011 等明確 adapter task；R008 未驗證或改動轉換。`ranking_score_bp` 與下列 calibration/ML projection 欄位也不放進 `RecommendationItem`：`calibrated_probability_bp/status`、`after_cost_profit_probability_bp/status`、`evidence_confidence`、`sample_size`、`cost_basis_bp`、`calibration_model_version`、`calibration_dataset_version`、`calibration_horizon`、`calibration_status`、`calibration_source`、`calibration_warnings`、`calibration_source_trace`、probability transform/baseline lineage 欄與 `calibration_provenance`。它們留在原 DTO／ML projection 邊界；execution 另持 `MLAvailability` outcome，並保留 typed ML projection refs 與 `MLReceiptBinding`。

`RecommendationResultDTO` 仍是既有 envelope/wire shape：`result_id`、`result_name`、mutable config/recommendations、regime、string timestamp、notes、`excluded_candidates_json`、`screening_matrix_json`、`why_not_payload_json`、`liquidity_gate_payload_json`、exclusion quality/warnings 與 `run_context`。本次沒有將這些 JSON 欄位轉成 canonical assessments，也未驗證 legacy-to-canonical adapters、ML projection ABI/ordered schema 或任何持久化相容性；轉換與 ABI 驗證留待 R009/R011 等明確 task。專用測試確認 legacy DTO 上既有 float 值原樣保留，而 canonical rule score/factor contribution 拒收 float。

## Parent import 調整證據與相容性

調整前兩個 parent `__init__.py` 都直接 eager import 公開 class。初始 import smoke 顯示 `decision_module` 會經 `analysis_module/__init__.py`、`analysis_module/pattern_analysis/__init__.py` 載入 `pattern_analyzer.py`（其頂層匯入 `matplotlib.pyplot`），並載入 pandas；`app_module` 的 eager service/DTO 路徑也載入 pandas，且經 `data_module/prospective_formal_clock.py` 建立 `ZoneInfo("Asia/Taipei")`、觸及非程式 timezone 檔案。這不符合 contract leaf import 不觸發非程式 I/O 的 INV-03 要求。

現在 parent 保留原 `__all__` 名稱與順序，使用窄 `__getattr__` 延遲載入並快取原 class，`__dir__` 保留公開名稱可見性。專用 subprocess tests 對 contract import 安裝 Python audit hook，拒絕非程式檔案 open 與 SQLite connect，並確認 domain import 不反向載入 app、app contract import 不載入 recommendation service/DTO、pandas 或 matplotlib。R008 專用自動 oracle 逐一比對全部 17 個舊 parent export 的來源 class identity，並覆蓋 direct import、star import、`getattr` 與 `__all__`；既有 update-service import contract 也有回歸測試。

明確限制：bare `import app_module` 或 `import decision_module` 後，尚未存取的 lazy export 不會立即出現在 parent module 的 `__dict__`；首次 `getattr`/direct import 才會載入並快取。`dir()` 仍列出 exports，direct/star imports 與 class identity 已驗證。依 R008 規格，此 `__dict__` 觀察時序差異已揭露，不宣稱與 eager import 的所有反射副作用完全一致。

## 回滾清單

執行前由獨立 preflight 記錄三個將修改的既有檔案均為 clean；下列 SHA 為寫入前基線。若需回滾，只能撤回 R008 對這三個檔案的精確 diff hunks 並移除下列 R008 新檔；不得對共享工作樹執行 checkout/reset，也不得覆寫同時存在的其他 dirty/untracked 檔案。

| 既有檔案 | 修改前 SHA-256 | 執行前狀態 |
|---|---|---|
| `app_module/__init__.py` | `8539ACBBB25FD76123EB67B2A344D167A6C0FA0ACD8E79BB914230B36F467375` | clean |
| `decision_module/__init__.py` | `D173D4179317DA314CB98EF1C77035C46938D4F1844075EE6E71767A08BFCF9D` | clean |
| `tests/test_update_service_import_contract.py` | `C8023FB7145AE9C3DAB9101ECB3E1EA000A20E9A2C5A0915596812FE5F85092E` | clean |

### 本輪 ML availability 回修

本輪開始前，下列 R008 檔案均為 untracked；如需回滾，只撤回本輪的精確 contract/test/package-export hunks 與本節報告補充，不刪除或 checkout/reset 整個檔案。

| 檔案 | 本輪修改前 SHA-256 | 修改前狀態 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `C12670CDE79F1CBA9B3DB1EC2B7990CF1D2496B173C5ADC65B341AD5DB35E2C6` | untracked |
| `tests/test_recommendation_contracts.py` | `2975AC35434CA6F5C0A50388653CDFD7114B0451BA00DAD55A898327F92A8270` | untracked |
| `app_module/recommendation/__init__.py` | `F2020F50FACA5BE43F9FCB409F2E6135B07E6B9F78B4A6173EF3F25ACA1DE952` | untracked |
| `R008_IMPLEMENTATION_REPORT.md` | `E0761D092C7CF612CCB94B2F69A6ED806FBCCBE5D3706EABF40ED95AC163AA98` | untracked |

### 本輪 failure reason、Request、enum 與 export identity 回修

本輪開始前只修改下列三個 R008 檔案；均為既有 untracked，沒有改動 package init 或其他工作樹檔。若需回滾，只撤回本輪在此三檔的精確 hunks，保留其他 R008 與 unrelated changes。

| 檔案 | 本輪修改前 SHA-256 | 修改前狀態 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` | untracked |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` | untracked |
| `R008_IMPLEMENTATION_REPORT.md` | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` | untracked |

ML availability 回修階段完成後的檔案 SHA-256（本輪 app 側再回修前）：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` |

前一輪 app 側回修完成後的程式碼與測試 SHA-256（本輪 receipt binding 回修前）：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `7014936A4529AEA11AFA541B2D1BD2B9F6806EC0F127AD1ED6123846C0D50A02` |
| `tests/test_recommendation_contracts.py` | `88FC23A2B958E9E8CAC5CD1A7F3D5D92E2A998EA43BC68CD62810B1790AD67AD` |

### 本輪 ML receipt binding 回修

本輪開始前只修改下列四個授權 R008 檔案；皆為既有 untracked。若需回滾，只撤回本輪在這些檔案的精確 hunks，保留其他 R008 與 unrelated changes。

| 檔案 | 本輪修改前 SHA-256 | 修改前狀態 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `7014936A4529AEA11AFA541B2D1BD2B9F6806EC0F127AD1ED6123846C0D50A02` | untracked |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` | untracked |
| `tests/test_recommendation_contracts.py` | `88FC23A2B958E9E8CAC5CD1A7F3D5D92E2A998EA43BC68CD62810B1790AD67AD` | untracked |
| `R008_IMPLEMENTATION_REPORT.md` | `B8877D1829BE8DF27803DC1AE598D57B5335B4065DEF20B9E6A47C01033885CE` | untracked |

本輪修改後的程式碼、package export 與測試 SHA-256（本報告自身 SHA 於交付訊息列出）：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `12F526A15D7B5B32F3FFB89CF8671C38A07F4898B8B6BE6EBD17C480D260CF20` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `tests/test_recommendation_contracts.py` | `6633A5B9C32B26CDC6237BEDBD63B6E34054E95FB738C4CAD796DA4187E45271` |

### 本輪空 projection receipt 修正

本輪增補開始前四個授權檔皆為 untracked；只撤回本節精確 hunk 即可回到上一輪已完成並驗證的 MLReceiptBinding 狀態。

| 檔案 | 增補前 SHA-256 | 增補前狀態 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `12F526A15D7B5B32F3FFB89CF8671C38A07F4898B8B6BE6EBD17C480D260CF20` | untracked |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` | untracked |
| `tests/test_recommendation_contracts.py` | `6633A5B9C32B26CDC6237BEDBD63B6E34054E95FB738C4CAD796DA4187E45271` | untracked |
| `R008_IMPLEMENTATION_REPORT.md` | `0E746D03F5F27FDFF18C8A605DDE246C83687EAD6DD368553BF485E20196B37A` | untracked |

增補後的 app contract 與測試 SHA-256（本報告自身 SHA 於交付訊息列出）：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `B5F2B11FF362F470974B89D0B7E5881EEAEE9F1076517F43EAEA94EC50851C83` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `tests/test_recommendation_contracts.py` | `DDADE06FBD3F82055FBAE0AC165DC6D71ACF030CA27ABBD9000F5AC8FB4CC08E` |

## 驗證結果

- `PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py -q -o addopts= -p no:cacheprovider`：61 passed，涵蓋 R008、decision 數值/enum、R007、parent import contract 與 V-EXEC characterization；R008 專用測試含 17 項。
- `python -m mypy --explicit-package-bases app_module/__init__.py decision_module/__init__.py app_module/recommendation/contracts.py decision_module/recommendation/contracts.py`：4 files checked，無錯誤。
- 對本輪修改的 recommendation package/contracts 與相關 R008/decision 測試檔執行 `python -m py_compile`：通過。
- `git diff --check`：通過；另對本輪 untracked 的 R008 contracts、package export、tests 與 report 執行 whitespace check：通過。
- 深凍結 alias 測試使用既有 `QualityReport.metrics` 與 `ExecutionEvent.details`，不再由 `Request.options` 建立核心擴充面。
- Binding 拒絕空 tuple/list，依據既有 `build_inference_projection_receipt` 在 `ml_module/recommendation_inference_provenance.py:795` 對空 projection rows 的明確拒絕；zero-item completed execution 仍可完成，但不保存或合成 receipt binding。

## 已知缺口與審查重點

Contracts 尚未接任何 consumer、service 或 writer；legacy DTO 數值/日期欄轉換、ML projection ABI mapping、持久化 codec、artifact writer、資料庫 save、UI 呈現均未在 R008 驗證。MLReceiptBinding 只提供 R008 本地 immutable identity/hash-shape/date/stock membership checks；不代表 receipt 檔案 hash/body、model candidate、cost hash 或 PreparedMLInput 已互相驗證，也不證明 receipt publication ordering。這些端到端檢查留給 R010/R026。未更動推薦分數計算、rounding、tie-break、ML ordered schema/dtype/mask/top-N，也未新增金融 float 計算。請依以上範圍與已測項目進行 review；本報告狀態維持 **READY_FOR_REVIEW**。

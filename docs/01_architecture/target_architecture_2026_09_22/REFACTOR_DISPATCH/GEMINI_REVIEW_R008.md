# GEMINI_REVIEW_R008 — Wave 2 正式獨立審查封包

> 暫停派送：R008 並行稽核找到需回修的深凍結與 contract validation 缺口；下列 SHA 是本次回修前快照。SOL 更新本封包與九檔 SHA 後才能作正式 Gemini 審查。

> 版本保管：先前 Gemini `CHANGES_REQUIRED` 報告核對的是 ML availability 回修前四個舊 SHA，見 `REFACTOR_REPORTS/R008_STALE_GEMINI_REVIEW_INTAKE.md`。本封包以下嵌的 Luna 回修報告與 `R008_SOL_REWORK_REVIEW.md` 九個最新 SHA 為本次審查對象；請勿沿用舊報告的 bytes 或結論。

## ROLE／TASK ID／PURPOSE

你是 Gemini 獨立 reviewer。只審查 Luna Max 的 R008 canonical recommendation／execution contracts 與經 SOL 核准的 parent package 窄 lazy-export 修正。這是正式 implementation review，**唯讀**，不可改任何檔案。最後必須且只能給出一個 `REVIEW_STATUS`。這個封包在 Luna 實作、SOL 初審、跨切片測試與 SHA 凍結後產生；此前的 Wave 2 並行分析不是正式審查，也不替代本次判定。

## CURRENT SYSTEM CONTEXT／COMPLETED DEPENDENCIES

Repository：`C:\Projects\PythonProjects\technical_analysis`。HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`，未 commit。Wave 1 正式 checkpoint `REFACTOR_REPORTS/WAVE1_CHECKPOINT.md` PASS；R002 recommendation semantics、R003 execution state、R007 data leaf contracts 均 PASS，R008 才解鎖。Wave 3 R009/R010 與後續仍 blocked。現有 dirty/untracked worktree 含其他 task；不得 stage、commit、push、revert、清理或覆寫。R008 尚未接 production consumer、codec、writer、UI、ML internals。

## AUTHORITATIVE ARCHITECTURE／ALLOWED SCOPE／OUT OF SCOPE

下方嵌入原始 R008 task 規格、全 18 條架構 invariants、SOL 受控範圍裁決、Luna 完整實作報告與 SOL 初審。另可唯讀參照同目錄 `FINAL_TARGET_ARCHITECTURE.md` §5.1–5.3／§6.1、`FINAL_DATA_FLOW.md` §2／§6。架構已定案；不得重新設計。R008 只允許兩個 contract packages、專用 tests、兩個 parent `__init__.py` 窄 lazy exports、指定既有 import-contract 時序 oracle 與任務報告。不得建 codec、writer、consumer，或改舊 DTO/service、UI、推薦公式／數值、ML schema、正式資料。

## ORIGINAL R008 SPECIFICATION

# R008 — canonical recommendation／execution contracts 與深凍結

## TASK CONTEXT

現有RecommendationDTO混合rule、calibration、wire與UI欄位；RecommendationResultDTO保存多份list。FINAL已定decision item/batch與app execution的ownership。

## WHY THIS TASK EXISTS

R009–R020都依賴同一typed shape；先抽engine再定contract會製造一次性adapter。

## AUTHORITATIVE ARCHITECTURE REFERENCES

- [FINAL_TARGET_ARCHITECTURE §5](../FINAL_TARGET_ARCHITECTURE.md)
- [FINAL_DATA_FLOW §2、§6](../FINAL_DATA_FLOW.md)
- [FINAL_ARCHITECTURE_INVARIANTS INV-07–11](../FINAL_ARCHITECTURE_INVARIANTS.md)

## DEPENDENCIES

R002、R003、R007。

## ALLOWED SCOPE

新增 `decision_module/recommendation/contracts.py`、`app_module/recommendation/contracts.py`、必要的 recommendation package `__init__.py` 及 tests。若一般 import 的實測證明既有 parent package eager imports 觸發非程式 I/O，R008 可**獨占**將 `decision_module/__init__.py` 與 `app_module/__init__.py` 的原公開 exports 改成窄 lazy exports；須保留原名稱、`__all__`、direct/star import 與 class identity，且不得在這兩檔變動任何其他業務邏輯。僅因這項核准的載入時序變更，可將 `tests/test_update_service_import_contract.py` 原 eager-module oracle 改為 lazy-before-access、explicit-access-after-load 的雙時點 oracle；保留原 class identity 與 public exports assertions。這是為滿足既定 INV-03 的受控匯入修正，不授權 consumer migration。

## OUT OF SCOPE

修改RecommendationService/DTO、codec、save、UI、算法、ML contract internals。

## CURRENT BEHAVIOR TO PRESERVE

既有score/precision、stock identity、rank/universe、reasons、screening/negative evidence、regime/context、quality/warnings、result_id與ML receipt references。

## IMPLEMENTATION OBJECTIVE

建立RecommendationItem、CandidateAssessment、DecisionBatch與Request/Context/RecommendationExecution/SaveReceipt。Execution只持`decision: DecisionBatch | None`；便利properties不得重複儲存。

## ARCHITECTURAL INVARIANTS

INV-06–11。completed必有DecisionBatch，items可空；failed/cancelled可無decision。

## ML COMPATIBILITY REQUIREMENTS

Execution只組合現有projection/receipt typed reference或immutable snapshot，不複製ML schema，不改top-N。

## PERSISTENCE COMPATIBILITY REQUIREMENTS

定義 `schema_version="recommendation-execution.v1"` 及 `EXECUTION_SCHEMA_REVISION=1`，尚不寫artifact。

## TEST REQUIREMENTS

nested mutable input/output mutation、MappingProxy backing copy、duplicate stock code、aware clocks、status組合、null/zero、existing numeric types。

若觸及 parent `__init__.py`，另驗一般 contract import 不讀非程式檔／不連資料庫、不引入 domain→app 逆向依賴，並比對原公開 exports 的 direct/star import、`getattr`、`__all__`、class identity 與既有 import-contract tests。對 bare parent import 後立即檢查 module `__dict__` 的既有副作用，如有差異須明列限制，不得偽稱完全相同。

## ACCEPTANCE CRITERIA

contracts可獨立建構且深凍結；無DataFrame/logger/callback/live handle；沒有第二份items/assessments storage。

## EXPECTED DELIVERABLES

兩個contract modules、validation/deep-freeze helpers（owner旁）、tests與field ownership表。

若使用上述受控 import 修正，報告另列 parent eager-import 的實測證據、兩個檔案的逐項 export 相容驗證與額外 diff；不得把它記為 architecture redesign。

## POST-TASK REPORT REQUIREMENTS

列出contract欄、凍結策略、reject cases、哪些舊DTO欄屬ML或legacy wire。

## ROLLBACK / FAILURE CONDITIONS

若必須改舊計算才能建構contract，停止；contract未接production前可整體回滾。

## RELEVANT FINAL ARCHITECTURE INVARIANTS

# 最終架構不變條件

> 設計定案，尚未實作。唯一決策來源：FINAL_TARGET_ARCHITECTURE（開發收據見dev）。以下 18 條是目標系統與後續實作 prompt 的強制規則；現況尚未全部符合。過渡違規只能以 遷移退休帳（開發收據見dev） 的具名 owner／退出條件列管，不允許整包永久豁免。

| ID | 必須遵守 | 驗證方式 |
|---|---|---|
| INV-01 | 原始資料、歷史 artifact、模型與 checkpoint 不因重構改 bytes、ID 或 hash。 | 唯讀基線／hash inventory；寫入只用隔離 root。 |
| INV-02 | data 擁有來源解碼；analysis 擁有技術公式；domain 擁有 factor 語意、策略與規則；app 擁有用例；UI 只呈現。 | 變更 owner 表與 import／call-site 審查。 |
| INV-03 | domain 不依賴 app、Qt、concrete DB/HTTP/file reader、ML trainer 或 scripts；純 leaf contracts 不觸發 I/O。 | 精確 module DAG、無 I/O 的 domain fixture、import smoke。 |
| INV-04 | factor 語意轉譯與公式留同一 domain owner；vendor 欄名／來源 fallback 留 data；app 不複製兩者。 | 同標準輸入跨來源等價、factor unit/missing 測試。 |
| INV-05 | 訊號、特徵、母體、標準化與 benchmark 只用 decision-time 可得資料；unknown availability 不當已知。 | cutoff／PIT／未來資料注入反例。 |
| INV-06 | 新金融核心計算使用 Decimal 或具單位整數；不得在重構中偷改原 precision、rounding、tie-break 或 ML matrix ABI。 | 獨立數值 oracle、精確比較；具名 legacy 例外退休帳。 |
| INV-07 | 每次執行回傳同一完整 execution；result_id 在 ML receipt 前建立；runtime／portfolio／replay ID 只以 reference 連結。 | A/B 交錯、ID conflict、parent/receipt 對照。 |
| INV-08 | worker 返回前遞迴封存所有結果；frozen dataclass＋tuple＋複製後 MappingProxyType，不保留 mutable alias。 | 原輸入與回傳值兩側的巢狀 mutation 測試。 |
| INV-09 | completed/failed/cancelled、quality、ML availability、保存 outcome 分開；零候選可為 completed。 | 零列、取消、部分失敗與 last-good UI 案例。 |
| INV-10 | save／query／UI 不讀 service.last_*、不補算 regime、score 或 ML；真正業務 prior state 必須明示保留。 | 執行後來源變更再保存、regime 多日／cooldown 測試。 |
| INV-11 | canonical typed contract 是唯一新欄位 schema；codec 自動涵蓋支援型別，未知 schema/type 必須拒絕，禁止無型別核心擴充字典。 | 全欄位 roundtrip、null/0、缺 optional、未知 revision 拒絕。 |
| INV-12 | 新保存採 create-only；同 ID/hash 冪等、異 hash 拒絕；metadata 不進 execution hash；SQLite index 可重建。 | 並行保存、中斷後補索引、改名不改 payload hash。 |
| INV-13 | 歷史顯示只讀原結果；歷史重算建立新 result_id 並保留 parent/版本；兩模式 policy 差異不得被共用 engine 偷改。 | 無 live lookup readback、日期/母體/策略差異 fixtures。 |
| INV-14 | ML prepare 明示固定資料／模型版本；build/infer 不暗讀 live source。初輪 frozen reads 僅依列管例外維持，不能假稱已隔離。 | 來源更新 barrier、exact candidate/date/cost/receipt 驗證。 |
| INV-15 | 舊 ML ordered schema、dtype、scale、mask、row/fold refs、transform、source identity、class path 與 safety gate 不自動演進。 | ML 契約（開發收據見dev） 的相容正反例；新 feature 明示 opt-in 新版本。 |
| INV-16 | composition 建立並管理資源；runtime 只排程／治理；UI/CLI 呼叫相同用例。 | 單一實例／生命週期、取消與重試、入口測試。 |
| INV-17 | 過渡 runtime 機制必有 ID、owner、caller、刪除條件；新舊不留雙引擎。永久歷史 decoder／artifact ABI 支援分帳。 | 全 caller inventory、動態/serialized 依賴、退休帳逐項驗收。 |
| INV-18 | 設計完成、測試通過、工程完成與 formal/promoted/production 權限分開；不可用重構通過替代產品 Gate。 | 驗收記錄、權限拒絕測試、Scoped SSOT 核對。 |

每個實作切片至少指出受影響 INV、對應證據與仍存在的具名例外；未驗證項目明記未執行。新介面不能再產生 `last_*` 依賴，即使舊 caller 尚在遷移也一樣。

## SOL R008 SCOPE ADDENDUM

# R008 parent package import 範圍裁決

## 實測與判定

R008 Luna worker 在變更前用獨立 Python import smoke 查出：一般匯入新 `decision_module.recommendation.contracts` 與 `app_module.recommendation.contracts` 時，Python 必先執行各自 parent `__init__.py`。現有 decision parent eager import 經 analysis/pattern → Matplotlib 讀取 `matplotlibrc` 等非程式資源；app parent eager import 還讀取時區資料。SOL 獨立重跑 parent import，`decision_module` 已載入 15 個 decision modules 與 pandas，`app_module` 已載入 42 個 app modules、21 個 decision modules 與 pandas。worker 尚未修改任何檔案即停手。source 核對未見 decision parent 反向載入 app 或 SQLite connect。

這是既有 package 初始化對「新純 leaf contract 匯入不得觸發 I/O」的實作衝突，不是 `FINAL_TARGET_ARCHITECTURE` 中 contract owner/型別無法成立的架構矛盾。SOL 將它判為**可在 R008 原目標內修正的範圍缺漏**，不是正式 `ARCHITECTURE_BLOCKER`。R007 曾就 `data_module/__init__.py` 有同型窄修正與相容審查。

## 受控範圍

僅增列 `decision_module/__init__.py`、`app_module/__init__.py` 兩個 package 入口供 R008 worker 獨占；只允許將原 public exports 改為窄 lazy exports。原名稱、`__all__`、direct/star import、class identity 與被測呼叫路徑必須相容。SOL 獨立重跑 `tests/test_update_service_import_contract.py` 得 1 passed／1 failed；唯一失敗為原測試把「匯入 `app_module.update_service` 就預載七個 service」當成 oracle。此與受控 lazy 修正直接衝突，故允許 R008 **只改該測試的載入時序斷言**：存取 public class 前只載入被指定子模組，逐一明示存取後仍載入原服務且 class identity、`__all__` 不變。不得放寬或移除其他 assertions。不得改 service、DTO、codec、save、UI 或其他 R-task，亦不接任何 production consumer。新增 import smoke 必須證明 contract import 無非程式檔 I/O／DB 連線與 domain→app 逆向依賴；對 bare parent module `__dict__` 時序差異須明列。若不能在此界線通過，就回報具體 blocker 而非擴大修正。

已同步 R008 task spec 與 Wave 2 execution-order 註記。Wave 2 仍只執行 R008，後續正式 Gemini review 需特別審查此兩檔及所有公開 import 相容性。

SCOPE_DECISION: CHANGES_REQUIRED_WITHIN_R008

## SOL R008 ML AVAILABILITY SCOPE DECISION

# R008 SOL 範圍內回修裁決：ML availability

STATUS: CHANGES_REQUIRED_WITHIN_R008

`FINAL_TARGET_ARCHITECTURE.md` §5.2 與 `FINAL_ARCHITECTURE_INVARIANTS.md` INV-09 明定 terminal status、quality、ML availability、persistence outcome 必須分開；`FINAL_ML_COMPATIBILITY_CONTRACT.md` §2 進一步要求缺 projection 時記錄 unavailable／blocked 原因，並能區分 missing、schema mismatch、quarantined 與 source version unavailable 等結果。

目前 `app_module/recommendation/contracts.py` 的 `RecommendationExecution` 有 terminal `status`、`quality` 與 ML projection／receipt reference tuple，`SaveReceipt` 另表達保存結果，卻沒有明示的 ML availability/outcome。兩個空 reference tuple 不能區分未要求、未知、不可用、阻擋或尚未發布；`ExecutionEvent` 可放自由文字，但沒有強制的 ML 維度，不能作為 INV-09 的契約保證。這是 R008 canonical execution contract 的範圍內缺口，不是架構重新設計或 R009+ consumer migration。

請原 R008 worker 僅於 `app_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py` 與 `R008_IMPLEMENTATION_REPORT.md` 補上最小的明示、不可變 ML availability/outcome 表達和缺值原因；區分「未要求／未知」與「不可用／阻擋」，不得從空 refs 或 terminal status 猜測，亦不得把缺 projection 補成 0。維持 projection／receipt refs 的原 owner、既有 schema version/revision、DecisionBatch 欄位與 ML ordered ABI；不接 consumer、不改舊 DTO、ML 模組、writer、UI 或演算法。新驗證要涵蓋零參照下可區分的狀態、原因保存、深凍結、非法組合及原有 import 邊界。由 SOL 重新驗證並更新正式 Gemini review packet 的凍結 SHA 後，才將此輪提交獨立審查。

原先的 Gemini 並行分析僅是實作前風險提示；本裁決來自 SOL 對權威規格與實際 contract 的核對，不宣稱已有 Gemini 正式 `REVIEW_STATUS`。

## LUNA R008 IMPLEMENTATION REPORT

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
| app | `VersionReference` | `kind`、`reference_id`、可選 `version`；runtime、replay、portfolio 與 evidence ID 以 typed reference 表示。 |
| app | `Request` | `as_of_date`、config/profile/strategy/policy/universe-policy refs、不可變 `options`。 |
| app | `Context` | 可未知的 `as_of_date`、aware `decision_at`、`source_refs`、data-snapshot refs、config/profile/strategy/policy/universe refs、algorithm ref、`input_quality`、`warnings`。歷史未知值保留 `None` 或 unknown 狀態。 |
| app | `QualityReport`、`ExecutionEvent` | 品質 status/warnings/metrics，以及事件 type/message/aware clock/details。 |
| app | `MLAvailability` | `status` 明示 not-requested/unknown/available/unavailable/blocked；缺值或拒絕時保存 typed `reason` 與可選不可變 `reason_detail`。 |
| app | `RecommendationExecution` | `result_id`、`request`、`context`、terminal `status`、唯一的 `decision: DecisionBatch \| None`、quality、獨立 `ml_availability`、events、related refs、獨立 ML projection/receipt refs、可選 `failure_reason`。schema version/revision 是固定 class/schema metadata。 |
| app | `SaveReceipt` | `result_id`、payload hash、artifact location、aware `persisted_at`、index status、schema version/revision。 |
| R007 | `SourceRef` | 作為來源 leaf contract 使用，owner 仍為 R007；R008 不修改該型別。 |

`RecommendationExecution.items` 與 `.assessments` 是唯讀 property，直接委派至 `decision`，不是 dataclass fields，也沒有第二份保存空間。`related_references` 只接受 runtime/replay/portfolio/evidence kinds；config、data、universe、ML projection 與 ML receipt 各由其專屬欄位保存。ML 狀態不從 refs 或 terminal status 推算；空 refs 可明確對應 not-requested、unknown、unavailable（需原因）或 blocked（需原因）。unknown 可保留 refs 而不被改判為 available。available 必須有 projection 與 receipt refs，not-requested 不可帶這兩類 refs。

## 深凍結與拒絕規則

兩側 contract 各自持有封存 helper。helper 僅接受明示 contract whitelist 中的 frozen dataclass、tuple/list、mapping、`str`、`int`、`bool`、`None`、有限 `Decimal`、enum、date 與帶時區 datetime。dataclass 必須是白名單中的 exact class；一般外部 frozen dataclass 或 contract subclass 不會作為逃生擴充口。數值 scalar 使用 exact int/Decimal 檢查，因此 bool 不會混入 int 欄位，也不會把 legacy float 轉成 Decimal 或基點。

list 會遞迴轉為 tuple；只有在 runtime 已確認輸入精確為 tuple/list 後，才以窄 `cast(Sequence[object], ...)` 告知型別檢查器其可迭代形狀。每個 mapping 都先複製成新的 backing dict，遞迴凍結值後再包成 `MappingProxyType`；key 只接受 exact `str`。active-path identity 檢查拒絕循環結構。dataclass 必須是白名單中的 exact class；一般外部 frozen dataclass 或 contract subclass 不會作為逃生擴充口。數值 scalar 使用 exact int/Decimal 檢查，因此 bool 不會混入 int 欄位，也不會把 legacy float 轉成 Decimal 或基點。typed `_freeze_tuple` 只在逐項 exact type runtime 驗證後 cast 回 tuple[T, ...]；沒有使用寬泛 `type: ignore`。naive datetime、非有限 Decimal、float、錯誤 mapping key、未列名 dataclass、一般物件、callback 與 live file handle 均拒絕。輸入的 mapping proxy 也會複製 backing dict，因此後續改動原 dict 或其巢狀 list 不會改變已封存值。

Execution terminal rules 為：`completed` 必須帶 `DecisionBatch`，即使 items 為空；`failed` 與 `cancelled` 必須沒有 decision，診斷留在 events/quality，避免 partial items 經便利 property 被當成已完成推薦發布。結果 ID 驗證沿用 `rec_<uuid>`。schema metadata 固定為 `recommendation-execution.v1` 與 revision `1`。

ML availability 獨立使用 `MLAvailabilityStatus` 與 `MLAvailabilityReason`。not-requested、unknown、available 不接受缺值原因；unavailable 與 blocked 都必須記錄明示原因。typed reason 涵蓋 missing、schema-mismatch、quarantined、source-version-unavailable、cutoff-unproven 與 policy-blocked；reason 保持與 status 分離，不由 reason 猜 status。`reason_detail` 只接受不可變非空字串。這保留缺 projection 與具體原因，不填補 0，也不把 quality、terminal outcome 或 persistence receipt 混成 ML availability。

## 舊 DTO、ML projection 與 wire 欄位

R008 未改 `app_module/dtos/__init__.py`。`RecommendationDTO` 的既有 rule/UI payload 包含 `stock_code`、`stock_name`、`close_price`、`price_change`、`total_score`、`indicator_score`、`pattern_score`、`volume_score`、`recommendation_reasons`、`industry`、`regime_match`。其中 close price 型別為 `float | Decimal`，其餘價格變動與 score 欄為 float。現有 `from_dict` 會用 `Decimal(str(close_price))` 建 close price，並以 `float(...)` 建 price change 與四個 score；`to_dict` 輸出中文 wire key（例如 `證券代號`、`收盤價`、`漲幅%`、`總分`、`推薦理由`、`Regime匹配`），並在 quantile mode 加上百分位顯示欄。R008 保留這套舊行為，沒有做 legacy → canonical 數值轉換，也沒有量化、改精度或改 tie-break。

舊 DTO 的追溯欄 `score_percentile_bp`、`eligible_universe_size`、`eligible_universe_date`、`ranking_method`、`threshold_mode` 對應部分 canonical decision 欄位；舊 DTO 的 `eligible_universe_date` 是 Optional[str]，而 canonical item 使用 Optional[date]，轉換尚未實作。`ranking_score_bp` 與下列 calibration/ML projection 欄位也不放進 `RecommendationItem`：`calibrated_probability_bp/status`、`after_cost_profit_probability_bp/status`、`evidence_confidence`、`sample_size`、`cost_basis_bp`、`calibration_model_version`、`calibration_dataset_version`、`calibration_horizon`、`calibration_status`、`calibration_source`、`calibration_warnings`、`calibration_source_trace`、probability transform/baseline lineage 欄與 `calibration_provenance`。它們留在原 DTO／ML projection 邊界；execution 另持 `MLAvailability` outcome，並保留 typed ML projection/receipt references。

`RecommendationResultDTO` 仍是既有 envelope/wire shape：`result_id`、`result_name`、mutable config/recommendations、regime、string timestamp、notes、`excluded_candidates_json`、`screening_matrix_json`、`why_not_payload_json`、`liquidity_gate_payload_json`、exclusion quality/warnings 與 `run_context`。本次沒有將這些 JSON 欄位轉成 canonical assessments，也未驗證 legacy-to-canonical adapters、ML projection ABI/ordered schema 或任何持久化相容性；轉換與 ABI 驗證留待 R009/R011 等明確 task。專用測試確認 legacy DTO 上既有 float 值原樣保留，而 canonical rule score/factor contribution 拒收 float。

## Parent import 調整證據與相容性

調整前兩個 parent `__init__.py` 都直接 eager import 公開 class。初始 import smoke 顯示 `decision_module` 會經 `analysis_module/__init__.py`、`analysis_module/pattern_analysis/__init__.py` 載入 `pattern_analyzer.py`（其頂層匯入 `matplotlib.pyplot`），並載入 pandas；`app_module` 的 eager service/DTO 路徑也載入 pandas，且經 `data_module/prospective_formal_clock.py` 建立 `ZoneInfo("Asia/Taipei")`、觸及非程式 timezone 檔案。這不符合 contract leaf import 不觸發非程式 I/O 的 INV-03 要求。

現在 parent 保留原 `__all__` 名稱與順序，使用窄 `__getattr__` 延遲載入並快取原 class，`__dir__` 保留公開名稱可見性。專用 subprocess tests 對 contract import 安裝 Python audit hook，拒絕非程式檔案 open 與 SQLite connect，並確認 domain import 不反向載入 app、app contract import 不載入 recommendation service/DTO、pandas 或 matplotlib。相容測試覆蓋 `from package import Name`、`from package import *`、`getattr`、class identity、`__all__` 與既有 update-service import contract。

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

本輪實作完成後供 review 凍結的檔案 SHA-256：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` |

## 驗證結果

- `python -m pytest tests/test_recommendation_contracts.py -q -o addopts=`：13 passed；含零 refs 的明示狀態、原因保存、凍結、非法 status/reason/reference 配對與 package export import smoke。
- `python -m pytest tests/test_data_market_contracts.py -q -o addopts=`：8 passed，作為 R007 leaf-contract characterization。
- `python -m pytest tests/test_update_service_import_contract.py -q -o addopts=`：2 passed。
- `python -m mypy --explicit-package-bases app_module/__init__.py decision_module/__init__.py app_module/recommendation/contracts.py decision_module/recommendation/contracts.py`：4 files checked，無錯誤。
- 對兩個 parent package、兩個 recommendation package/contracts 與兩個相關測試檔執行 `python -m py_compile`：通過。
- pytest 顯示既有 `.pytest_cache` 寫入權限警告；測試結果仍通過，未修改 cache 或其他工作樹資料。

## 已知缺口與審查重點

Contracts 尚未接任何 consumer、service 或 writer；legacy DTO 數值/日期欄轉換、ML projection ABI mapping、持久化 codec、artifact writer、資料庫 save、UI 呈現均未在 R008 驗證。未更動推薦分數計算、rounding、tie-break、ML ordered schema/dtype/mask/top-N，也未新增金融 float 計算。請依以上範圍與已測項目進行 review；本報告狀態為 **READY_FOR_REVIEW**。

## CHANGED FILE／DIFF SCOPE、TESTS ALREADY EXECUTED、FROZEN SHA

# R008 ML availability 回修：SOL 獨立驗證與正式 Gemini 審查交接

INTEGRATION_STATUS: READY_FOR_GEMINI_REVIEW

## 判定與範圍

SOL 對照 `R008_SOL_CHANGES_REQUIRED_ML_AVAILABILITY.md`、權威 §5.1–5.3／INV-09 及實際程式碼，確認 Luna 只在核准範圍補入 application-owned `MLAvailability`、`MLAvailabilityStatus`、`MLAvailabilityReason`，以及相應 tests、package exports、實作報告。`RecommendationExecution` 現有獨立 `ml_availability`，可在相同的空 projection/receipt refs 下區分未要求、未知、不可用與阻擋，並對後二者保存 typed reason 及可選不可變 detail。`available` 要求 projection 與 receipt refs，`not_requested` 禁止這些 refs；沒有從 terminal status、quality 或空 refs 猜測可用性，也沒有補零。原 DecisionBatch、schema version/revision、舊 DTO、ML internals、consumer、writer、UI 和數值算法均未改。本判定只表示可交 Gemini 正式審查，**不是 R008 PASS**。

## 凍結檔案 SHA-256

| R008 受審檔案 | SOL 現讀 SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` |
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` |
| `REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` |

三個 tracked 檔的實際 `git diff` 仍只涉及原核准的兩個 parent lazy exports 與一個 import-contract 載入時序測試；其餘 R008 檔為 untracked，SOL 逐檔閱讀而非只看 `git diff`。Git index 為空；沒有 stage、commit、push，其他既有 dirty/untracked 檔未動。

## SOL 獨立測試

- R008 contract、R007 leaf、parent import、R003 execution characterization/coordinator 組合：`38 passed`，exit 0。
- R002 characterization、recommendation run support、task-loop 規則切片：`38 passed, 2 existing pandas warnings`，exit 0。
- 兩個 parent 與兩個 recommendation contract 的定向 mypy：`Success: no issues found in 4 source files`；八個受審 Python 檔 `py_compile` 通過；`git diff --check` exit 0（僅 Git LF/CRLF 訊息）。
- SOL 額外探測把 `tests/test_recommendation_service_calibration_integration.py` 併入第二組後得到 `44 passed, 6 failed`。六個失敗都在該**未修改**測試的 `_natural_receipt` fixture 建立階段，`tests/natural_session_source_fixture.py:130` 拋出 `ValueError("evaluation_day must follow every exact-20 session endpoint")`；測試固定 `evaluation_day="2026-06-22"`，尚未進入 R008 contract 或被測 ML consumer 路徑。此既有 fixture 日期不一致須如實列為擴大測試限制，不能宣稱該 ML integration suite 通過，也不授權 R008 偷改其 fixture 或 production。Gemini 可獨立核對這項分類。

## Gemini 必查

請核對上述九個 SHA 與實際 diff，尤其確認 ML availability 的 status/reason/reference 組合符合 INV-09、FINAL ML compatibility contract，且 `UNKNOWN` 預設不冒稱可用；`available` 對兩種 refs 的要求是否與既有 receipt 發布順序相容；enum reason 是否足以保存必需的缺值／阻擋原因。其餘深凍結、Decimal/bp、terminal、parent lazy export、import 無 I/O、typed refs、schema ownership 與測試充分性依正式審查封包逐項檢查。獨立 review 結尾只允許一個 `REVIEW_STATUS`；SOL 收到後仍需核對工作樹與 gate。

Tracked diff scope 只含 `app_module/__init__.py`、`decision_module/__init__.py`、`tests/test_update_service_import_contract.py`。請實際執行 `git diff -- <三檔>` 並閱讀兩個新 `contracts.py`、兩個 package `__init__.py`、`tests/test_recommendation_contracts.py`；untracked 新檔不會出現在普通 `git diff`，必須逐檔讀。以 SOL 回修驗證表格列出的九個 SHA-256 先核對實際 bytes；任一不符即停止，回報 drift 與是否需重新凍結。不要只相信報告或執行結果敘述。

## REQUIRED INDEPENDENT REVIEW

請逐項檢查：R008 acceptance criteria；deep-freeze 輸入與返回值兩側 nested alias、MappingProxy backing copy、unsupported frozen dataclass/subclass、naive clock、循環結構；completed-empty／failed／cancelled、quality／ML availability／save outcome 分離；duplicate stock code、result_id 與 runtime/replay/portfolio/ML refs 的 identity／ownership；null/zero、Decimal 精度、bp unit 與 legacy float 邊界；score/order/reasons/negative evidence/regime/context 是否保留舊語意；schema_version/revision 是否由 app contract 單一持有；是否產生第二份 items/assessments storage、hidden state、新 reverse dependency；parent lazy exports 的 direct/star/getattr/__all__/class identity 與反射時序限制；import 是否觸發非程式 I/O／SQLite；R008 原有與新增測試是否充分，是否把現況 gap 誤標為目標 PASS。歷史 artifact、replay mode、ML ordered schema/dtype/mask/top-N、receipt/production boundary 不得因 R008 受到改動，也不得由本輪測試冒稱已驗證完整相容。

請只回報 R008 範圍內具體 findings，含檔案、行號、可重現 evidence、違反的 acceptance/invariant 與最小修正方向。對於既有其它 task 的 gap，只記為未驗證／後續 owner，不要要求在 R008 偷改。可以唯讀重跑聚焦測試、mypy、py_compile 和 diff-check；不要跑正式資料寫入或 full-market ML rebuild。不要重寫無關程式碼。

## REQUIRED OUTPUT

請分別列出：SHA／diff custody、acceptance/invariant 審查、數值／persistence／replay／ML 相容邊界、測試充分性、具體 findings（若無請寫「無」）以及仍未由 R008 驗證的項目。最後一行**恰好一個**狀態：

`REVIEW_STATUS: PASS`
`REVIEW_STATUS: CHANGES_REQUIRED`
`REVIEW_STATUS: BLOCKED`

PASS 僅代表本 task 的正式獨立審查通過，不代表 Wave 2 checkpoint、C1–C4、ML promotion 或 production Gate 通過。

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.

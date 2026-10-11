> **時點／狀態導覽（2026-10-11）**：本文是基線 HEAD `391b057c92037ec7a19cab2bf951d6029d29b020` 上、R008 實作前的唯讀風險分析；`ANALYSIS_STATUS: COMPLETE` 只表示檢查表完成，不是實作或 acceptance verdict。R031 current disposition 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；實際實作與後續裁定請看 [R008 implementation report](R008_IMPLEMENTATION_REPORT.md) 與 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。本文的基線觀察與 checklist 保留為歷史分析，不取代現行 contract。

# Wave 2 並行唯讀契約驗收風險分析：R008 規範與審查檢查表

> **任務識別碼**：`WAVE2_PARALLEL_ANALYSIS`（R008 契約驗收風險）  
> **角色**：獨立 Gemini 分析者（Pre-implementation Read-Only Risk Analysis）  
> **基線 HEAD**：`391b057c92037ec7a19cab2bf951d6029d29b020`  
> **工作模式**：唯讀分析（不修改任何程式碼、不變更 repository、不開始其他 R-task；本分析供 SOL 於 Luna 完成後核對使用，非最終 PASS review）

---

## 一、已確認的契約事實（Confirmed Contract Facts）

本分析依據現行程式庫（`app_module/dtos/__init__.py`、`data_module/contracts/market.py`、`app_module/recommendation_service.py`、`app_module/recommendation_save_coordinator.py`）及權威架構文件（[FINAL_TARGET_ARCHITECTURE.md §5](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md#L170)、[FINAL_DATA_FLOW.md §2、§6](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_DATA_FLOW.md)、[FINAL_ARCHITECTURE_INVARIANTS.md](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md)），確認以下不可變更之核心事實：

### 1. 現有 DTO 欄位混合現況與法定歸屬劃分

現行 `RecommendationDTO`（共 33 個欄位）與 `RecommendationResultDTO`（共 14 個欄位）混雜了決策、推論、保存與呈現邏輯。R008 必須依據架構邊界嚴格解耦，明確歸屬：

| 欄位類別 | 現有 DTO 欄位名稱 | 法定歸屬 Module | 目標契約物件與職責 |
|---|---|---|---|
| **核心標的識別** | `stock_code`, `stock_name` | `decision_module` | `RecommendationItem`：標的身分，`stock_code` 在同一 batch 內必須唯一。 |
| **價格與數值基礎** | `close_price`, `price_change` | `decision_module` | `RecommendationItem`：`close_price` 採 `Decimal`（或整數分）；`price_change` 保持原精度，禁止 float 任意轉換。 |
| **領域規則評分** | `total_score`, `indicator_score`, `pattern_score`, `volume_score` | `decision_module` | `RecommendationItem`：保持原計算數值，**嚴禁將原分數偷換/量化為 bp**。 |
| **推薦理由與標籤** | `recommendation_reasons`, `industry`, `regime_match` | `decision_module` | `RecommendationItem`：結構化理由與標籤；`regime_match` 為 bool。 |
| **排名與母體統計** | `score_percentile_bp`, `eligible_universe_size`, `eligible_universe_date`, `ranking_method`, `threshold_mode` | `decision_module` | `RecommendationItem`：決策當下可得之排名資訊（以整數 bp 與整數表示）。 |
| **候選評估與排除** | `excluded_candidates_json`, `screening_matrix_json`, `why_not_payload_json`, `liquidity_gate_payload_json`, `exclusion_quality`, `exclusion_warnings_json` | `decision_module` | `CandidateAssessment` 與 `DecisionBatch`：未入選標的評估、負例與流動性判斷。 |
| **ML 校準與投影** | `ranking_score_bp`, `calibrated_probability_*`, `after_cost_profit_*`, `evidence_confidence`, `sample_size`, `cost_basis_bp`, `calibration_*`, `calibration_provenance` | `app_module` (組合 `ml_module` 引用) | **絕對不得進入 Decision 領域！** 屬於 `app_module` 的 `RecommendationExecution` 之 `ml_projection_receipt_ref` 或外部不可變參照。 |
| **執行與決策脈絡** | `result_id`, `regime`, `config`, `run_context`, `created_at`, `notes` | `app_module` | `RecommendationExecution`、`RecommendationRequest` 與 `RecommendationContext`：App 擁有執行身分與情境。 |
| **舊版 Wire / UI 欄位** | `to_dict()`/`from_dict()` 的中文鍵（`證券代號`、`漲幅%`、`總分`、`Regime匹配='是'`、`百分位`等）、`notes`、`result_name` | `app_module` (Legacy Codec/Presenter) | 屬舊版相容與展示層；**嚴禁直接成為新 Canonical Contract 的屬性**。 |

### 2. 執行身分與複合列鍵（Row Identity）
- 單次 execution 內：`stock_code` 必須唯一（重複即為建構錯誤）。
- 跨 execution 列鍵：法定為 `(result_id, stock_code)`。
- `result_id`：維持 `rec_<uuid>` 格式，由 app 在決策執行與 ML receipt 之前建立。
- ID 隔離性：`result_id`、排程 `run_id`、replay `parent_result_id`、portfolio `evidence_id` 為不同型態與語意，只能以具名欄位關聯，禁止互換或共用。

### 3. Execution 與 Decision 的單向包含關係
- `RecommendationExecution` **僅能持有 `decision: DecisionBatch | None`**。
- `RecommendationExecution.items` 等便利屬性若存在，**只能是唯讀委派 property**（例如 `@property def items(self) -> tuple: return self.decision.items if self.decision else ()`），**嚴禁在 Execution 內部建立第二份 items 或 assessments 儲存欄位**（防止雙重狀態與不一致）。

---

## 二、R008 審查檢查表（SOL 審查專用）

SOL 在審查 Luna 的 R008 diff 時，應逐項核對以下檢查表（任一項違反即應判定 `CHANGES_REQUIRED`）：

### 檢查點 1：領域邊界與檔案範圍（INV-02、INV-03）
- [ ] **檔案路徑限制**：僅新增：
  - `decision_module/recommendation/contracts.py`
  - `app_module/recommendation/contracts.py`
  - 專屬測試檔（如 `tests/test_recommendation_canonical_contracts.py`）
  - 報告與清冊（若有）。
- [ ] **零修改限制**：未修改既有 `RecommendationService`、`RecommendationDTO`、`RecommendationResultDTO`、UI、codec、save、算法或 ML internals。
- [ ] **依賴方向純淨性**：`decision_module/recommendation/contracts.py` 為純領域契約，**嚴禁 import `app_module`、`ui_qt`、`PySide6`、DB/I/O 或 ML trainer**。
- [ ] **ML 欄位隔離**：`RecommendationItem` 與 `DecisionBatch` 完全不含 `calibrated_probability_*` 等 18 個 ML projection 欄位。

### 檢查點 2：深凍結與不可變型別白名單（INV-08）
- [ ] **Dataclass 裝飾器**：所有契約 class 皆使用 `@dataclass(frozen=True, slots=True)`（或 `frozen=True`）。
- [ ] **型別嚴格白名單**：所有屬性型別僅限：
  - `str`, `int`, `bool`, `None`
  - `Decimal`（禁止裸 float 作為精確金融度量）
  - `enum.Enum`
  - `datetime.date`
  - 具備時區之 aware `datetime.datetime`
  - `tuple`（禁止暴露任何 `list` 或 `set`）
  - `types.MappingProxyType`（禁止暴露任何可變 `dict`）
  - 經白名單審核之 frozen dataclass。
- [ ] **禁止侵入之型別**：`DataFrame`、`Series`、`QObject`、`logger`、`callback`、`file/connection handle` 絕不可作為欄位型別。

### 檢查點 3：終端狀態組合（Terminal State Combinations, INV-09）
- [ ] **COMPLETED 契約**：當 `terminal_status == ExecutionTerminalStatus.COMPLETED` 時，`decision` **必不為 None**（即使 `decision.items` 為空 tuple，代表合法零候選完成）。
- [ ] **FAILED / CANCELLED 契約**：當 `terminal_status` 為 `FAILED` 或 `CANCELLED` 時，`decision` 允許為 `None`；若附帶 partial decision，僅作診斷使用。
- [ ] **四維度解耦**：契約設計明確區分：(1) `terminal_status`、(2) `quality`、(3) `ml_availability`、(4) `save_receipt`，不得以空清單暗示取消或失敗。

### 檢查點 4：時鐘、版本與身分驗證（INV-05、INV-07、INV-11）
- [ ] **時鐘感知性**：`RecommendationContext.decision_at` 必須驗證 `tzinfo is not None and utcoffset() is not None`；拒絕 naive datetime。
- [ ] **歷史補值禁止**：歷史 context 中未知之值保留為 `None` 或 `"unknown"`，嚴禁以 `datetime.now()` 偽造決策時間。
- [ ] **版本與 Revision 宣告**：
  - 包含 `schema_version: str = "recommendation-execution.v1"`
  - 包含整數常數 `EXECUTION_SCHEMA_REVISION = 1`
- [ ] **UUID 前綴校驗**：`result_id` 必須符合 `rec_<uuid>` 格式（若非則拋出 ValueError）。

---

## 三、可能的 CHANGES_REQUIRED 風險與具體反例證據

以下列出 Luna 在實作 R008 時最容易犯錯的陷阱、其對應的反例（Negative Case），以及哪種錯誤設計會導致驗證失敗：

### 1. 深度不可變（Deep-Freeze）漏洞反例

#### 反例 A：MappingProxyType 洩漏底層可變 Dict（Shared Backing Dict）
- **錯誤設計**：
  ```python
  # 錯誤實作：直接將傳入的 dict 包裝為 MappingProxyType
  def __init__(self, config: dict):
      object.__setattr__(self, "config", MappingProxyType(config))
  ```
- **為何失敗**：Caller 在建構合約後，依然持有原本的 `config` 參照。當外部調用 `config["threshold"] = 999` 時，合約內的 `self.config["threshold"]` 會隨之被篡改！這直接破壞了 [INV-08](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L14)（不保留 mutable alias）。
- **正確實作要求**：合約建構時必須進行**遞迴防禦性複製（recursive deep copy）**至新建的私有 dict，再包裝為 `MappingProxyType`；且巢狀 dict 亦必須遞迴轉為 `MappingProxyType`。

#### 反例 B：Dataclass 欄位直接接收 List / Set
- **錯誤設計**：
  ```python
  @dataclass(frozen=True)
  class DecisionBatch:
      items: tuple[RecommendationItem, ...]
      diagnostics: list[str]  # 錯誤：使用了 mutable list
  ```
- **為何失敗**：雖然外層是 `frozen=True`，但 `batch.diagnostics.append("leak")` 仍可被外部原地修改。
- **正確實作要求**：建構時強制 `object.__setattr__(self, "diagnostics", tuple(diagnostics))`。

#### 反例 C：接受 Naive Datetime 破壞決策時間戳
- **錯誤設計**：直接接受 `datetime.now()` 或無時區之 `datetime(2026, 9, 22, 10, 0)`。
- **為何失敗**：跨系統、跨時區回測與儲存時產生歧義，違反 PIT availability（[INV-05](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L11)）。
- **拒絕測試**：傳入 `datetime.now()` 必須拋出 `ValueError("decision_at must include a timezone")`。

---

### 2. 業務拒絕測試（Rejection Test Scenarios）

Luna 的測試套件必須包含以下拒絕測試，證明合約具備自我防禦能力：

| 拒絕情境 | 觸發條件 | 預期例外 | 哪種錯誤設計會漏測 |
|---|---|---|---|
| **重複代碼** | `DecisionBatch(items=[item_2330, item_2330])` | `ValueError("duplicate stock_code in DecisionBatch")` | 未在 `DecisionBatch.__post_init__` 檢查 `len(set(codes)) == len(codes)`。 |
| **COMPLETED 缺決策** | `RecommendationExecution(terminal_status=COMPLETED, decision=None)` | `ValueError("completed execution requires a DecisionBatch")` | 未檢查終端狀態與決策對象的依賴一致性（[INV-09](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L15)）。 |
| **非法 result_id** | `RecommendationExecution(result_id="invalid_id_123")` | `ValueError("result_id must start with rec_")` | 未校驗 UUID 命名規則（[INV-07](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L13)）。 |
| **浮點數混充 Decimal** | `RecommendationItem(close_price=105.5)` (若宣告為 Decimal) | `TypeError("close_price must be Decimal")` | 允許 float 隱式傳入，引發二進位浮點精度截斷（[INV-06](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L12)）。 |
| **未知 Schema Revision** | 傳入 `schema_revision=2`（而當前實作為 1） | `ValueError("unsupported schema revision")` | 缺乏版本白名單防禦（[INV-11](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L17)）。 |
| **缺失值與零混淆** | 傳入 `score_percentile_bp=0` vs `None` | 兩者在合約內嚴格不等且不可互換 | 錯誤將 `None` 透過 `or 0` 預設值轉為 0。 |
| **外部別名修改** | 建立合約後修改傳入的 input list/dict | 合約內部值完全不受影響 | 僅做淺層複製或直接引用原始物件（[INV-08](file:///C:/Projects/PythonProjects/technical_analysis/docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md#L14)）。 |

---

## 四、尚待 Luna Diff 才能判定之事項

在 Luna 完成並凍結實作前，以下項目無法提前推斷，必須在正式 Review 時審查其實際 Diff：
1. **模組與符號公開清單**：確認 `decision_module/recommendation/contracts.py` 與 `app_module/recommendation/contracts.py` 的 `__all__` 是否乾淨，無洩漏任何內部 helper 或未授權型別。
2. **便利屬性的委派實作**：確認 `RecommendationExecution.items` 是否為純 property 委派，未在 `__slots__` 或 dataclass fields 中佔用第二份儲存空間。
3. **遞迴封存 Helper 的效能與邊界**：檢視 Luna 實作的 deep-freeze 函式是否能優雅處理多層巢狀結構，且未引入循環引用。
4. **現有測試回歸狀態**：確認新增合約及其測試是否與既有 29 個 Wave 1 characterization 測試完全解耦且全數通過。

---

## 五、已執行的唯讀檢查（Executed Read-Only Checks）

1. **Wave 1 相依測試套件重跑**：
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_refactor_characterization.py tests/test_recommendation_execution_state_characterization.py tests/test_data_market_contracts.py -q -o addopts= -p no:cacheprovider
   ```
   - **結果**：`29 passed in 1.45s`（Exit Code: 0），確認 R002、R003、R007 之契約基線處於 100% 穩定綠燈狀態。
2. **Market 合約典範檢查**：
   唯讀讀取 `data_module/contracts/market.py`，確認其 `@dataclass(frozen=True, slots=True)`、`_require_aware_datetime`、`_require_nonblank` 與 tuple conversion 模式，確認 R008 可參照該成熟模式實作。
3. **Repository 檔案與 Git 狀態檢查**：
   確認工作目錄無任何由本分析引入的修改，保持完全唯讀。

---

## 六、分析狀態回報

本唯讀並行分析已全數完成，明確界定了 R008 的契約事實、欄位歸屬、SOL 審查檢查表、深凍結陷阱與拒絕測試情境。未發現阻止 R008 進行安全實作的架構阻礙（Architecture Blocker）。

ANALYSIS_STATUS: COMPLETE

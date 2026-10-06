# R008 正式唯讀獨立審查報告

> **審查基準**：
> - 審查封包：`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md`
> - 收件參照：`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE2_GEMINI_PARALLEL_ANALYSIS_INTAKE.md`
> - 權威架構與契約：`FINAL_TARGET_ARCHITECTURE.md`、`FINAL_DATA_FLOW.md`、`FINAL_ARCHITECTURE_INVARIANTS.md`、`FINAL_ML_COMPATIBILITY_CONTRACT.md`
> - 審查模式：**唯讀獨立審查**（未修改任何檔案、未 stage/commit、未啟動其他 R-task）

---

## 一、SHA-256 逐檔保管與 Diff 核對

依據 `GEMINI_REVIEW_R008.md` 所列之 9 個凍結檔案，逐一讀取磁碟實際位元組計算 SHA-256，核對結果如下：

| 受審檔案 | 封包指定凍結 SHA-256 | 磁碟實際計算 SHA-256 | 核對結果 |
|---|---|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` | **MATCH** |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` | **MATCH** |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` | **MATCH** |
| `app_module/recommendation/__init__.py` | `F2020F50FACA5BE43F9FCB409F2E6135B07E6B9F78B4A6173EF3F25ACA1DE952` | `F2020F50FACA5BE43F9FCB409F2E6135B07E6B9F78B4A6173EF3F25ACA1DE952` | **MATCH** |
| `app_module/recommendation/contracts.py` | `C12670CDE79F1CBA9B3DB1EC2B7990CF1D2496B173C5ADC65B341AD5DB35E2C6` | `C12670CDE79F1CBA9B3DB1EC2B7990CF1D2496B173C5ADC65B341AD5DB35E2C6` | **MATCH** |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` | **MATCH** |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` | **MATCH** |
| `tests/test_recommendation_contracts.py` | `2975AC35434CA6F5C0A50388653CDFD7114B0451BA00DAD55A898327F92A8270` | `2975AC35434CA6F5C0A50388653CDFD7114B0451BA00DAD55A898327F92A8270` | **MATCH** |
| `docs/01_architecture/.../R008_IMPLEMENTATION_REPORT.md` | `E0761D092C7CF612CCB94B2F69A6ED806FBCCBE5D3706EABF40ED95AC163AA98` | `E0761D092C7CF612CCB94B2F69A6ED806FBCCBE5D3706EABF40ED95AC163AA98` | **MATCH** |

### Git Tracked Diff 範圍核實
檢查 `git diff` 僅限於核准的 3 個既有檔案：
1. app_module/__init__.py（開發參考）：移除頂層 eager 匯入，改以 `_LAZY_EXPORTS` 字典搭配 `__getattr__` 延遲載入並快取至 `globals()`，`__all__` 順序與名稱完全保留，`__dir__` 保留反射可見性。
2. decision_module/__init__.py（開發參考）：同上模式，移除 eager 匯入（避免傳遞載入 analysis/pattern/matplotlib），改為窄 lazy exports。
3. tests/test_update_service_import_contract.py（開發參考）：將原先「僅 import `update_service` 就斷言其餘 7 個服務已被載入」的 eager 依賴 oracle，調整為「存取前不預載未存取模組；存取後驗證 class identity 與 public exports 不變」的雙時點契約測試。

---

## 二、架構不變條件與驗收標準審查

### 1. Parent Package 窄 Lazy-Export 相容性與反射限制
- **載入行為**：實測驗證，在全新直譯器中執行 `from app_module import RecommendationService` 或 `from app_module import *`，均能正常取得目標類別，且 `is` 判斷與原始定義類別完全一致（class identity 保留）。
- **已揭露之時序差異**：在裸匯入 `import app_module` 當下，尚未存取的公開 class 不會立即出現在 `app_module.__dict__` 中，必須透過 `getattr` 或直接存取後才會載入並快取。此差異已在 R008 規格與實作報告中如實記錄，符合「不偽稱完全相同」之受控要求。
- **測試驗證**：test_parent_public_exports_keep_order_direct_star_getattr_and_class_identity（開發參考） 與既有 test_update_service_import_contract.py（開發參考） 均以獨立子程序執行且通過。

### 2. 無 I/O 匯入與模組邊界隔離（INV-03）
- 透過 Python `sys.addaudithook` 稽核：
  - 匯入 decision_module.recommendation.contracts（開發參考） 時，無任何 `sqlite3.connect`，無非 `.py/.pyc` 檔案讀取，且未載入 `app_module`、`pandas` 或 `matplotlib`。
  - 匯入 app_module.recommendation.contracts（開發參考） 時，無任何 `sqlite3.connect`，無非程式檔案讀取，且未預先載入 `recommendation_service`、`dtos`、`scoring_engine`、`pandas` 或 `matplotlib`。
- 完全滿足純 leaf contracts 匯入零 I/O 之規定。

### 3. 深凍結防護與資料封存（INV-08）
- **不可變性**：所有合約類別均宣告 `@dataclass(frozen=True, slots=True)`。
- **防止別名穿透**：
  - decision_module/recommendation/contracts.py（開發參考） 與 app_module/recommendation/contracts.py（開發參考） 各自持有封存 helper。
  - 傳入的 `Mapping` 或 `MappingProxyType` 均會被**複製**為全新的內部 dict，遞迴凍結後再封裝為 `MappingProxyType`，成功杜絕修改外部 backing dict 造成的後續穿透（test_mappingproxy_input_is_copied_before_sealing（開發參考） 驗證通過）。
  - `Sequence` 嚴格轉換為 `tuple`。
- **白名單限制**：`_ALLOWED_FROZEN_RECORD_TYPES` 嚴格限定為合約內明確列出之 exact class，不接受任意外部 frozen dataclass 或合約子類別（逃生口被徹底封堵）。
- **循環參照防護**：`active_path` 追蹤物件識別碼，遭遇循環結構時拋出 `TypeError("偵測到循環參照")`。

### 4. 數值、單位與精度防禦（INV-06）
- **禁止裸 float 滲入**：
  - `RecommendationItem.rule_score`、`FactorContribution.value`、`RecommendationItem.confidence` 嚴格要求 `Decimal | int | None`。
  - 純 scalar 驗證以 `type(val) in (Decimal, int)` 且排除 `bool`（因 `isinstance(True, int)` 為真），並排除非有限 `Decimal('NaN')` 或 `Decimal('Infinity')`。
  - test_legacy_float_values_are_not_quantized_or_moved_into_domain_contract（開發參考） 證實傳入舊 DTO 之 float 分數會明確引發 `TypeError`，未發生偷轉型、偷量化或未經授權的 bp 替代。

### 5. 終端狀態互斥與身分唯一性（INV-07, INV-09）
- **狀態與決策互斥**：
  - `ExecutionStatus.COMPLETED`：必須持有 `DecisionBatch`（允許 items 為空，代表零候選情境正常完成）。
  - `ExecutionStatus.FAILED` 或 `CANCELLED`：`decision` 必須為 `None`，嚴禁夾帶 `DecisionBatch`（防止下游將部分計算當成已完成推薦發布）。
  - `completed` 狀態下嚴禁附帶 `failure_reason`。
- **身分唯一性**：
  - `DecisionBatch.__post_init__` 校驗 `items` 與 `assessments` 集合中的 `stock_code` 唯一性，重複即拋出 `ValueError`。
  - `result_id` 強制符合 `rec_<uuid>` 正則表達式。
- **無多餘儲存**：
  - `RecommendationExecution.items` 與 `assessments` 為唯讀 `@property`，直接委派給 `decision`，未在 execution 上新增第二份儲存欄位。

---

## 三、關鍵疑點審查：ML Availability 與 INV-09 / FINAL ML 契約之符合性

依指示特別查明：**空 ML references 是否能明確表達 ML 未啟用／不可用及原因，是否符合 INV-09 與 FINAL ML 契約？**

### 審查判定：不符合（NON-COMPLIANT）
現有實作中，`RecommendationExecution` 僅定義了：
```python
ml_projection_refs: tuple[VersionReference, ...] = ()
ml_receipt_refs: tuple[VersionReference, ...] = ()
```
當推薦執行完成但 ML 未啟用、或因故不可用時，合約狀態如下：
1. **維度混淆與資訊丟失**：
   - 若 ML 未啟用（使用者未配置／停用）：`ml_projection_refs == ()`。
   - 若 ML 已啟用但無符合候選（No candidates）：`ml_projection_refs == ()`。
   - 若特徵資料缺失或決策時間截止點（cutoff）不一致而被阻擋（Blocked）：`ml_projection_refs == ()`。
   - 若模型檔案遺失、環境函式庫不相容或模型處於隔離狀態（Unavailable / Quarantined）：`ml_projection_refs == ()`。
   **下游 Consumer／UI 僅見空 tuple，完全無法區分上述情境。**
2. **違反 INV-09 明確分離原則**：
   - INV-09 明定：`completed/failed/cancelled`、`quality`、`ML availability`、`保存 outcome` 是四個**各自獨立的維度**。
   - 目前 terminal status 有 `ExecutionStatus`，quality 有 `QualityReport`，保存 outcome 有 `SaveReceipt`，但 **ML availability 缺乏一級 typed 狀態欄位**。
   - 若將 ML 不可用之原因強行塞入 `QualityReport.warnings`，會污染整體輸入資料的品質評等（例如 Rule 推薦的輸入品質原本為 `HEALTHY`，卻因可選 ML 缺件而被標為 `DEGRADED`）；若僅記錄於 `ExecutionEvent`，則事件屬於稽核歷程（Audit trail），下游無法以型別化欄位取得當前狀態快照。
3. **違反 FINAL_ML_COMPATIBILITY_CONTRACT.md §2**：
   - 契約明文要求：「無法證明 cutoff／版本／共用來源一致時，拒絕此次 ML projection，**記錄 unavailable／blocked 原因，保留 Rule outcome**... Execution 封存精確 receipt 的 ID／hash／candidate／date／cost lane，以及 **missing、schema mismatch、quarantined、source version unavailable 等結果**；缺 projection 不補 0。」
   - 現行合約在 `status == COMPLETED` 時禁止填寫 `failure_reason`，導致 Rule 成功而 ML 被阻擋時，無 typed 欄位可承載 ML blocked/unavailable 原因。

---

## 四、具體 Findings、可重現證據與最小修正方向

### [Finding R008-01] (架構不變條件違規 / 嚴重度：中高)
- **檔案與行號**：
  app_module/recommendation/contracts.py:202-215（開發參考）
- **違規條款**：`FINAL_ARCHITECTURE_INVARIANTS.md` INV-09、`FINAL_ML_COMPATIBILITY_CONTRACT.md` §2、`FINAL_TARGET_ARCHITECTURE.md` §5.2。
- **可重現 Evidence**：
  在目前合約下，建構一個 Rule 計算完成但 ML 因特徵 cutoff 不一致被封鎖的案例：
  ```python
  from app_module.recommendation.contracts import ExecutionStatus, RecommendationExecution, Request, Context
  from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem
  from decimal import Decimal
  from datetime import date

  # Rule 成功，但 ML 因來源版本不一致被阻擋
  execution = RecommendationExecution(
      result_id="rec_00000000-0000-0000-0000-000000000001",
      request=Request(as_of_date=date(2026, 9, 21)),
      context=Context(as_of_date=date(2026, 9, 21)),
      status=ExecutionStatus.COMPLETED,
      decision=DecisionBatch(items=(RecommendationItem("2330", rule_score=Decimal("10.0")),)),
      ml_projection_refs=(),
      ml_receipt_refs=(),
  )
  # 斷言：合約無法表達 ML 是「未啟用」還是「被封鎖」，亦無法記錄封鎖原因
  assert execution.ml_projection_refs == ()  # 無法得知 blocked 原因
  # 若嘗試設置 failure_reason="ml_cutoff_mismatch"，會因 L253 觸發 ValueError: "completed execution 不得附帶 failure_reason"
  ```
- **最小修正方向（Minimal Solution，不改動任何 ML 內部 ABI）**：
  在 app_module/recommendation/contracts.py（開發參考） 的純應用合約範圍內增設 ML 狀態列舉與報告結構：
  1. 新增狀態列舉：
     ```python
     class MLAvailabilityStatus(str, Enum):
         NOT_REQUESTED = "not_requested"  # 未啟用／未設定
         AVAILABLE = "available"          # 正常產出 projection
         NO_CANDIDATES = "no_candidates"  # 正常執行但無符合候選
         BLOCKED = "blocked"              # 來源/cutoff 不一致或安全閥拒絕
         UNAVAILABLE = "unavailable"      # 模型缺失或環境不可用
         QUARANTINED = "quarantined"      # 模型處於隔離狀態
     ```
  2. 在 `RecommendationExecution` 增加對應欄位（附帶預設值，完全相容現有簽名）：
     ```python
     ml_availability: MLAvailabilityStatus = MLAvailabilityStatus.NOT_REQUESTED
     ml_availability_reasons: tuple[str, ...] = ()
     ```
     （或封裝為 `ml_availability: QualityReport` / `MLAvailabilityReport`）
  3. 在 `_freeze_execution` 中將 `ml_availability_reasons` 納入 `_freeze_tuple(..., str)`。
  4. 在 tests/test_recommendation_contracts.py（開發參考） 增加測試案例，驗證 `status=COMPLETED` 下，`ml_availability=MLAvailabilityStatus.BLOCKED` 且帶有 reasons 時，能明確與 `NOT_REQUESTED` 區隔，完整滿足 INV-09 的四維度分離。

---

## 五、測試充分性與驗證狀態

1. **現有測試套件重跑結果**：
   - `python -m pytest tests/test_recommendation_contracts.py tests/test_update_service_import_contract.py -v -o addopts=`：**13 passed**。
   - `python -m mypy app_module/__init__.py decision_module/__init__.py app_module/recommendation/contracts.py decision_module/recommendation/contracts.py tests/test_update_service_import_contract.py`：**Success: no issues found in 5 source files**。
   - 專案全域 mypy（646 source files）：**Success: no issues found**。
   - `python -m py_compile`（8 個受影響 Python 檔）：**通過**。
2. **測試覆蓋之有效性**：
   - 深凍結與防穿透測試極為扎實（包含 `MappingProxyType` backing 複製、循環引用檢測、exact whitelist 拒絕外部 dataclass）。
   - Import 隔離測試運用 Python audit hook 驗收無 I/O，具備高度鑑別力。
3. **測試缺口**：
   - 既有測試未涵蓋「ML 缺失／阻擋診斷表達」之負例與狀態組合測試，恰與上述 Finding R008-01 相呼應。

---

## 六、R008 範圍外未驗證項目（留待後續 R-Tasks 列管）

下列項目不在 R008 任務範圍內，本審查確認其未被意外更動，亦不宣稱其已達最終相容：
1. 舊版 `RecommendationDTO` 與 `RecommendationResultDTO` 向 Canonical Contracts 的雙向轉換 Adapter（歸屬 R009/R011）。
2. ML 內部 ordered feature schema、dtype、mask 與 matrix ABI（歸屬 ML 專案與後續任務）。
3. 磁碟持久化 Codec、Create-only Repository 與 SQLite 索引實作（歸屬 R010/R012）。
4. UI 呈現層與實際 Production Consumer 之接線。

---

## 七、正式審查結論

R008 在 Parent lazy-export、無 I/O import 隔離、深凍結防禦、Decimal/int 數值邊界及終端狀態互斥上均達到優異之工程水準，且 9 個檔案之 SHA-256 與 diff 完全受控。然而，**現有合約以空 ML references 代表所有 ML 未產出情況，無法表達 ML 未啟用／不可用及原因，明確違反 INV-09 與 FINAL ML 契約**。此缺失屬於原合約邊界內的必要微調，應在完成上述最小修正後再行通過。

REVIEW_STATUS: CHANGES_REQUIRED
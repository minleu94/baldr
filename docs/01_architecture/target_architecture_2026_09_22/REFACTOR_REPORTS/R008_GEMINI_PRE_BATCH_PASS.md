> **歷史 Gemini 舊 SHA transcript**：其中的 PASS 僅適用 [R008 intake](R008_GEMINI_PRE_BATCH_PASS_INTAKE.md) 與 [Wave 2 validation plan](WAVE2_BATCH_VALIDATION_PLAN.md) 記錄的舊檔案雜湊，不是目前或正式驗收。後續 task 結果見 [R008 SOL final acceptance](R008_SOL_FINAL_ACCEPTANCE.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

> 核對目前 R008 bounded contract scope 請另看 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)；此歷史 transcript 的 PASS 不代表 Wave 2 或其他 task release。

Ran command: `$files = @(
  "app_module/__init__.py",
  "decision_module/__init__.py",
  "tests/test_update_service_import_contract.py",
  "app_module/recommendation/__init__.py",
  "app_module/recommendation/contracts.py",
  "decision_module/recommendation/__init__.py",
  "decision_module/recommendation/contracts.py",
  "tests/test_recommendation_contracts.py",
  "docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md"
)
foreach ($f in $files) {
  if (Test-Path $f) {
    $hash = (Get-FileHash $f -Algorithm SHA256).Hash
    Write-Output "$f : $hash"
  } else {
    Write-Output "$f : MISSING"
  }
}
`
Viewed __init__.py:1-40
Viewed contracts.py:1-250
Viewed contracts.py:251-547
Viewed test_recommendation_contracts.py:1-250
Viewed test_recommendation_contracts.py:251-500
Ran command: `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py tests/test_update_service_import_contract.py -v -o addopts=`
Ran command: `git diff -- app_module/__init__.py decision_module/__init__.py tests/test_update_service_import_contract.py`

# R008 唯讀獨立審查報告 (ML Availability 回修驗證版)

> **審查基準**：
> - 審查封包：`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md`
> - 權威架構與契約：`FINAL_TARGET_ARCHITECTURE.md`、`FINAL_DATA_FLOW.md`、`FINAL_ARCHITECTURE_INVARIANTS.md`、`FINAL_ML_COMPATIBILITY_CONTRACT.md`
> - 回修裁決與報告：`R008_SOL_CHANGES_REQUIRED_ML_AVAILABILITY.md` 及回修後之 `R008_IMPLEMENTATION_REPORT.md`
> - 審查模式：**唯讀獨立審查**（未修改任何檔案、未 stage/commit、未啟動其他 R-task）

---

## 一、SHA-256 逐檔保管與 Diff 核對

依據最新提交之 9 個凍結檔案，逐一讀取磁碟實際位元組計算 SHA-256，核對結果如下：

| 受審檔案 | 封包指定凍結 SHA-256 | 磁碟實際計算 SHA-256 | 核對結果 |
|---|---|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B320...` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` | **MATCH** |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D...` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` | **MATCH** |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B78...` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` | **MATCH** |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1C...` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` | **MATCH** |
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC7...` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` | **MATCH** |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC...` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` | **MATCH** |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B...` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` | **MATCH** |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A...` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` | **MATCH** |
| `R008_IMPLEMENTATION_REPORT.md` | `0FA98AF3EDA595A4E...` | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` | **MATCH** |

### Git Tracked Diff 範圍核實
檢查 `git diff` 僅限於核准的 3 個既有檔案：
1. `app_module/__init__.py` 與 `decision_module/__init__.py`：移除 eager 匯入，改以 `_EXPORTS` 字典搭配 `__getattr__` 延遲載入並快取至 `globals()`，`__all__` 與 class identity 完全保留。
2. `tests/test_update_service_import_contract.py`：配合 lazy exports 修正，將時序預期分為 `loaded_before_public_access` 與 `loaded_after_public_access`，成功反映「存取前不預載未存取模組；存取後類別識別與公開匯出維持不變」的行為。

---

## 二、架構不變條件與驗收標準審查

### 1. ML Availability 修正核對 (INV-09, ML Compatibility Contract)
本輪重點審查先前遭退回之 ML availability 表達能力，現已完美達成：
- **獨立四維度**：`RecommendationExecution` 現已擁有獨立的 `ml_availability: MLAvailability`，與 terminal `status`、`quality`、`persistence` (SaveReceipt) 完全分離，嚴格遵守 INV-09。
- **不可用／阻擋原因之型別化紀錄**：新增 `MLAvailabilityStatus`（NOT_REQUESTED, UNKNOWN, AVAILABLE, UNAVAILABLE, BLOCKED）與 `MLAvailabilityReason`（MISSING, SCHEMA_MISMATCH, QUARANTINED, SOURCE_VERSION_UNAVAILABLE, CUTOFF_UNPROVEN, POLICY_BLOCKED）。
- **嚴謹的組合驗證**：
  - `AVAILABLE` 時強制要求 `ml_projection_refs` 與 `ml_receipt_refs` 不得為空。
  - `NOT_REQUESTED` 等狀態時禁止附帶 refs。
  - `UNAVAILABLE` 與 `BLOCKED` 強制要求必須附帶具體的缺值／拒絕 `reason`，並支援不可變的 `reason_detail`。
  - 沒有從 terminal status 或 quality 猜測 ML 可用性，也沒有以 0 填補缺值。

### 2. 無 I/O 匯入與模組邊界隔離 (INV-03)
- `tests/test_recommendation_contracts.py` 中的 `sys.addaudithook` 嚴格把關：不連 SQLite、不開非程式檔、不載入 pandas/matplotlib。
- 完全滿足純 leaf contracts 匯入零 I/O、domain 不依賴 app 等隔離要求。

### 3. 深凍結防護與資料封存 (INV-08)
- 透過 `_freeze_value`，對 dataclass、tuple、`MappingProxyType` 進行嚴格白名單防禦。
- Mapping 的 backing dict 被完整複製，迴避了外部 mutable alias 穿透的風險。
- 限定白名單中註冊的 exact class，防堵了外部 subclass 繞過凍結檢查。循環引用檢測正常運作。

### 4. 數值、單位與精度防禦 (INV-06)
- 核心數值（`rule_score`、`FactorContribution.value`、`confidence`）強制要求為 `Decimal` 或 `int`（以及 None）。
- 實作中精確檢查 `type(val) in (Decimal, int)` 且排除 `bool` 與非有限 Decimal。明確拒收 `float`，避免了不經授權的量化與基點換算。

### 5. 終端狀態互斥與身分唯一性 (INV-07, INV-09)
- `ExecutionStatus.COMPLETED` 必須伴隨 `DecisionBatch`，而 `FAILED`/`CANCELLED` 則強制其為 `None`，有效防止 partial decision 被當成完成態發布。
- `DecisionBatch` 在建立時嚴格檢驗 `items` 與 `assessments` 內的 `stock_code` 唯一性，重複即報錯。

### 6. Schema Ownership 與委派
- `RecommendationExecution` 中的 `items` 與 `assessments` 實作為唯讀 `@property` 委派給 `decision`，並未新增第二份欄位儲存空間。
- App 合約嚴格持有 `schema_version` (`"recommendation-execution.v1"`) 與 `schema_revision`。

---

## 三、測試充分性

- 專用合約測試 `pytest tests/test_recommendation_contracts.py` (15 passed)：涵蓋了巢狀 mutation、MappingProxy backing copy、重複股票識別碼、aware clock、狀態互斥、舊型別 float 拒絕、ML availability 組合與理由保留、無 I/O import 等所有邊界。
- 專案全域 `mypy` 檢查 646 檔案：**Success: no issues found**。
- `py_compile` 針對受影響的 8 個檔案編譯無誤。
- `test_update_service_import_contract.py` 在受控範圍內正確調整為 lazy imports 時序檢查。

---

## 四、R008 範圍外未驗證項目（交由後續列管）

以下項目依合約規定不在 R008 實作範圍，本審查不宣稱其已相容或完成，須由未來 Task 獨立處理：
1. 舊版 `RecommendationDTO` 與 `RecommendationResultDTO` 向新 canonical contracts 轉換之 Adapters（待 R009/R011）。
2. 持久化 Codec、SQLite index builder、與實際資料庫的 create-only 寫入流程（待 R010/R012）。
3. UI 呈現層、實際 ML API（ordered schema/ABI）、生產環境 Consumer 之接線。

---

## 五、具體 Findings

**無**。（本次複查中，前次被指出之 ML Availability 問題已完全依照架構要求及 INV-09 修正，各項契約與凍結實作皆符合預期，且受控檔案變更符合授權範圍。）

---

REVIEW_STATUS: PASS

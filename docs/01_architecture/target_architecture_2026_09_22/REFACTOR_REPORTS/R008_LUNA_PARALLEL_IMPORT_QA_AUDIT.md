# R008 獨立 import／QA 稽核

> 本 `AUDIT_STATUS: CHANGES_REQUIRED` 記錄舊 frozen inputs 的 findings 與當時 QA；它不是目前 R008 task verdict。請以 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 核對現行 bounded scope，並保留下文 findings 作歷史 audit 證據。

## 範圍與依據

本次只審核 R008 的 contract、兩個 parent package lazy exports、相關 import/deep-freeze 測試，以及指定的 calibration fixture 失敗。依序核對 `REFACTOR_TASKS/R008.md`、`REFACTOR_REPORTS/R008_SCOPE_ADDENDUM.md`、`REFACTOR_REPORTS/R008_SOL_REWORK_REVIEW.md`、`FINAL_ARCHITECTURE_INVARIANTS.md` 的 INV-02/03/08–11 與 `REFACTOR_VALIDATION_MATRIX.md` 的 Wave 2/R008 要求；亦讀取 QA Agent 指定的測試清冊、路由矩陣與相關手冊內容。

未修改 production、test 或既有報告；未 stage、commit、push。本次唯一由我寫入的檔案是本報告。工作樹還有其他 R-task 的 dirty/untracked 檔案，未納入本審查，也未改動。Git index 為空。

## 受審檔案 SHA-256 與實際變更

SHA 為稽核時工作樹原始 bytes 的 SHA-256。三個既有 tracked 檔以 `git diff HEAD -- <path>` 核對；其餘為 untracked，沒有 HEAD 版本可供 Git diff，已逐檔讀取現版原始碼並記錄 SHA。

| 檔案 | 狀態 | 現版 SHA-256 | 實際差異 |
|---|---|---|---|
| `app_module/__init__.py` | modified | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` | 原 11 個 public exports 保持名稱與順序；改為 `_EXPORTS` + `__getattr__` 延遲匯入並快取，新增 `__dir__`；沒有其他業務邏輯。 |
| `decision_module/__init__.py` | modified | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` | 原 6 個 public exports 保持名稱與順序；改為 `_EXPORTS` + `__getattr__` 延遲匯入並快取，新增 `__dir__`。 |
| `tests/test_update_service_import_contract.py` | modified | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` | 將單一 eager-module oracle 拆成 public access 前／後兩個時點；保留完整 `__all__`、UpdateService identity 與七個 service module 的載入對照。 |
| `app_module/recommendation/__init__.py` | untracked | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` | 新增 application contract exports，包含 ML availability 型別。 |
| `app_module/recommendation/contracts.py` | untracked | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` | 新增 request/context、execution、quality、ML availability、save receipt 與 reference contracts；`items`/`assessments` 為委派 property。 |
| `decision_module/recommendation/__init__.py` | untracked | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` | 新增 decision contract exports。 |
| `decision_module/recommendation/contracts.py` | untracked | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` | 新增 decision item、candidate assessment、batch 與遞迴凍結 helper。 |
| `tests/test_recommendation_contracts.py` | untracked | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` | 新增 R008 contract、deep-freeze、terminal/ML availability 組合、import boundary 與 parent export 測試。 |
| `REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | untracked | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` | 新增實作摘要、欄位歸屬、回修、驗證與限制記錄。 |

三個 tracked diff 的 `git diff --numstat` 為 app parent `60/27`、decision parent `42/15`、import test `42/21`（新增/刪除行）。逐段 diff 僅包含上述 lazy export 與載入時序 oracle。實作報告中的修改前 SHA 是 CRLF 工作樹 bytes；以 HEAD blob 轉 CRLF 後三者均可重現報告值，差異來自換行格式，不是基線檔案不一致。

## 匯入與 export 相容性

以 HEAD 中兩個原始 `__init__.py` 的 import 清單建立 17 個 export 對照，逐項驗證 `__all__` 順序、`dir()`、`getattr`、`hasattr`、`from package import Name`、`from package import *`，並以原定義模組的 class object 做 `is` 比對：app 11/11、decision 6/6 全通過。direct/star import 後取得的都是原模組 class identity。

bare `import app_module`／`import decision_module` 後，原 public class 名稱不會立即出現在 parent `__dict__`；首次 getattr/direct import 才載入並快取。`dir()` 仍列出完整 exports，star import 可正常取回。這項反射時序差異是範圍 addendum 明確允許並要求揭露的限制，不算未披露差異。

`test_update_service_import_contract.py` 的 oracle 變更沒有刪除 public names、`__all__`、class module 或 identity assertion；只把預載模組檢查改成載入前後雙時點，並在 public class access 後仍要求原七個 service module 都已載入。沒有發現為求通過而移除既有 assertion 的情形。另有自動測試覆蓋範圍缺口，列於 Finding R008-IQA-02。

## Leaf import 與依賴邊界

在兩個獨立 Python subprocess 安裝 `open` 與 `sqlite3.connect` audit hook，再一般匯入兩個 contract leaf。兩次均沒有非程式檔案 open 或 SQLite connect；決策 leaf 沒有載入 app、sqlite3、pandas、matplotlib；application leaf 沒有載入 recommendation service/DTO、decision scoring engine、sqlite3、pandas、matplotlib。現有 `test_contract_import_is_io_free_and_respects_module_boundaries` 也在定向 suite 通過。

程式依賴方向符合本切片：decision contract 只引用 R007 `SourceRef`；application contract 引用 decision contract；沒有 domain→app 逆向依賴。parent lazy imports 保留在明確核准範圍內，未改其他 parent package。

## 驗證命令與結果

1. 定向 R008/import/V-EXEC/R007 組合：

   ```powershell
   $env:PYTHONDONTWRITEBYTECODE = '1'
   .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py -q -o addopts= -p no:cacheprovider
   ```

   結果：`38 passed in 4.44s`，exit 0。

2. 17 個舊 public exports 的獨立 runtime 相容性檢查：以 `git show HEAD:<package>/__init__.py` 讀原始 import/export 對照，再於目前 interpreter 逐一作 direct/star/getattr/hasattr 與 source object identity 驗證。結果：app 11 個、decision 6 個全部通過，exit 0。

3. 獨立 import audit：兩個 subprocess 均使用 `sys.addaudithook` 拒絕非程式檔案 open 與 SQLite connect，並檢查載入後的 module set。結果：兩個 leaf 均通過，exit 0。

4. 指定 calibration integration 六個失敗案例：

   ```powershell
   $env:PYTHONDONTWRITEBYTECODE = '1'
   .\.venv\Scripts\python.exe -m pytest `
     tests/test_recommendation_service_calibration_integration.py::test_real_consumer_producer_advice_workbench_ui_path `
     tests/test_recommendation_service_calibration_integration.py::test_public_service_real_builder_saves_result_and_reverse_reads_receipt `
     tests/test_recommendation_service_calibration_integration.py::test_active_training_label_contract_missing_or_mismatched_fails_closed `
     tests/test_recommendation_service_calibration_integration.py::test_active_training_label_contract_missing_from_provenance_fails_closed `
     tests/test_recommendation_service_calibration_integration.py::test_real_consumer_rejects_future_research_candidate_context `
     tests/test_recommendation_service_calibration_integration.py::test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation `
     -q -o addopts= -p no:cacheprovider
   ```

   結果：`6 failed in 2.16s`。六例皆固定使用 `evaluation_day="2026-06-22"`；呼叫鏈停在 `test_daily_recommendation_learning_loop.py::_natural_receipt` → `natural_session_source_fixture.py:130`，因 `evaluation_day must follow every exact-20 session endpoint` 拋出 `ValueError`。guard 位於該 fixture 建 SQLite/calendar/source lineage 前；測試程式沒有匯入 R008 contract leaf，且錯誤先於各案例後續 consumer/service 驗證。這六個失敗確定發生在 R008 路徑之前，屬於既有固定日期 fixture 不相容；不可宣稱 calibration integration suite 通過，也不應歸因為 R008 contract 回歸。

5. `git diff --check -- app_module/__init__.py decision_module/__init__.py tests/test_update_service_import_contract.py`：exit 0，無 whitespace error；Git 僅顯示既有 LF/CRLF 提示。`git diff --cached --name-only` 無輸出。

## Findings

### R008-IQA-01 — 任意 Enum 可攜帶 mutable alias 穿透深凍結（P1）

兩個 `_freeze_value` 都以 `isinstance(value, Enum)` 接受任意 enum subclass，僅驗證 `.value` 是 primitive，隨後原樣 `return value`（`decision_module/recommendation/contracts.py:32–38`、`app_module/recommendation/contracts.py:45–51`）。但 `FilterOutcome.evidence` 與 `QualityReport.metrics` 都接受 `Mapping[str, object]`。自訂 Enum 可在 member 上保存 list 等 mutable attribute，導致 contract 建構後仍能修改其內部狀態，違反 INV-08 的「不保留 mutable alias」。

獨立 PoC 建立 `class MutableEnum(Enum)`，在 member 初始化 `payload=[]`，分別放入 `QualityReport(metrics={"enum": MutableEnum.VALUE})` 與 `FilterOutcome("rule", True, evidence={"enum": MutableEnum.VALUE})`；建構後執行 `MutableEnum.VALUE.payload.append(...)`，兩份 contract 讀回的 list 都出現新值。命令結束輸出：`CONFIRMED: both frozen records retain the same mutable Enum member payload; mutation remains visible through both contracts`。現有測試未涵蓋帶 mutable member state 的 enum；需讓非明確支援的 enum 無法穿透，並加入兩個 mapping 邊界的回歸測試，才符合 R008 deep-freeze acceptance。

### R008-IQA-02 — 自動 export oracle 未逐項斷言 class identity（P2）

目前自動測試已核對完整 export 名單、star import 成員存在性，以及部分 class identity；但 `test_parent_public_exports_keep_order_direct_star_getattr_and_class_identity` 對所有 export 的 identity 僅比較 `RecommendationService`、`RecommendationDTO`、`StrategyConfigurator`。另一 import-contract 測試核對七個 service 的 `__module__` 字串並直接比對 `UpdateService`，但沒有對 17 個 exports 全部逐項與來源 class object 做 `is` 比較。獨立 runtime 審查已證明現版 17/17 相容；缺口在持續回歸 oracle，而非本次實際 export 錯誤。R008 要求逐項 export 相容驗證，應把全量 source identity 檢查納入自動測試。

## 判定

Lazy export 的目前 runtime 行為、IO/SQLite 邊界與允許的 bare-parent 反射時序限制符合 R008 範圍；被修改的 eager/lazy 測試 oracle 未有不當放寬。校準 suite 六個失敗是日期 fixture 在 contract/consumer 路徑前拋錯。惟 R008 deep-freeze 的 Enum mutable alias 已可重現，且 export class identity 自動 oracle 不完整，故目前不可判為 PASS。

本報告是獨立 import/QA 稽核，不取代 Gemini 正式審查，也不代表 Wave 3 可開始。

AUDIT_STATUS: CHANGES_REQUIRED

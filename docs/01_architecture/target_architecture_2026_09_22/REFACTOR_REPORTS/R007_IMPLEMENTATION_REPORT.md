> **時點／狀態導覽（2026-10-10）**：本文的 `CHANGES_REQUIRED`、`READY_FOR_REVIEW`、`BLOCKED` 與 Wave／下游 gate 敘述，只代表撰寫當時的 implementer／reviewer／root 裁定，不是目前 disposition；目前 task 狀態看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，現況看 [Project Snapshot](../../../00_core/PROJECT_SNAPSHOT.md)。原審查結論與限制保留。

# R007 實作報告

Task：R007 — 建立 data leaf observation／availability contracts
Wave：1
Dependencies：R001 PASS
日期：2026-09-22

## Scope 與裁定

依整合 review 對 R007 的裁定，新增 `data_module/__init__.py` 作為唯一額外 production edit。Python 載入 `data_module.contracts` 前必然先執行父 package initializer；既有 initializer eager import `data_loader` 與 `data_processor`，會載入 vendor dependencies 並觸發非程式檔讀取。將四個既有頂層匯出改為 PEP 562 lazy exports，使純 contracts import 保持 leaf，同時保留名稱、順序、`__all__`、直接匯入、star import 與 ordinary submodule import。四個舊匯出仍解析到原有 class；未改其他 production 檔。

沒有遷移 providers、consumers 或資料，也沒有建立 wire codec、ML schema、vendor I/O 或 production wiring。

## 公開型別與欄位 owner

依 FINAL §3–§5，來源標準欄位、單位、資料日、可得時間、來源版本及 snapshot/source refs 由 data leaf 表達；來源適配器保留來源事實，domain/app 負責各自的業務解讀與 cutoff 準備。

| 公開型別 | 欄位與 owner |
|---|---|
| `SourceRef` | `source_id`、`revision`、可選 `snapshot_id`；來源識別與版本由 data source adapter 擁有。Revision 保留原有 `str` 或 `int` 型別。 |
| `MeasureUnit` | 原樣保留來源單位 `code`；data 擁有欄位轉換，domain 解讀單位。 |
| `Availability`／`AvailabilityStatus` | `status`、`available_date`、可選 timezone-aware `available_at`；data 保留來源提供的粒度，date-only 不補造 clock。未知 availability 必須沒有日期與時間。 |
| `SourceObservation` | `subject_id`、`fact_id`、`observation_date`、`value`、`unit`、`availability`、`source_ref`；data 擁有標準化來源事實。值僅允許 `Decimal`、`int`、`bool`、`str` 或 `None`。 |
| `MarketSlice` | `as_of_date`、`observations`、完整 `source_refs`、可選 aware `cutoff_at`；data leaf 擁有輸入 record 形狀，app preparation 提供 cutoff/as-of context。 |
| `MarketFactValue`／`SourceRevision` | 上述值與版本欄位的封閉型別別名；不含 `Any` 或任意 payload。 |

## Validation 與封存

所有 record 為 frozen、slotted dataclasses。`MarketSlice` 會把輸入 iterable 複製為 tuple，拒收非對應 record、重複 source refs、未列於 `source_refs` 的 observation source ref、重複 observation identity，以及晚於 `as_of_date` 的 observation。Identity 是 `(subject_id, fact_id, observation_date, source_ref)`。

日期欄位只接受 `date`，不接受 `datetime` 代替；`available_at`、`cutoff_at` 必須含 timezone。Known availability 至少帶日期或時間；Unknown availability 不可帶日期或時間。Finite `Decimal` 原樣保留，`float`、任意 object、非有限 Decimal 與空單位拒收。MarketSlice 無 DataFrame、live connection、latest pointer 或自由擴充 mapping 欄位。

測試確認三種情況維持不同：沒有 observation row、row 存在但 `value=None`、row 存在且值為 `Decimal(0)`。不從舊資料推定缺失 timestamp，也不把 unknown availability 轉為 known。

## 未遷移 consumers

本 task 沒有改接任何 consumer。既有 data providers/adapters、`data_module.data_loader`、`data_module.data_processor`、app replay 的 `RecommendationDataFrameProvider`，以及 analysis／decision／ML callers 均維持 R001 所記錄的現況；後續 consumer migration 仍由各自 R-task 負責。

直接存取四個 legacy top-level exports 時，仍解析到 `data_module.config.TWStockConfig`、`data_module.data_loader.{MarketDateRange, DataLoader}`、`data_module.data_processor.TWMarketDataProcessor` 的原 class。直接匯入與 star import 及 `from data_module import config` 均有測試。

## Import 無 I/O 證據

R007 import smoke 在全新 subprocess 安裝 audit hook：SQLite connect 立即拒絕；`open` 事件只允許 Python module code suffix。測試以 canonical `from data_module.contracts import market` 路徑匯入，成功證明此路徑沒有非程式檔開啟或 SQLite connect，且沒有載入 `data_loader`、`data_processor`、`yfinance`、app、analysis、decision、backtest、portfolio、ML 或 Qt modules。契約模組本身只依賴標準 library 型別與 frozen record 定義。

## 變更檔案

- `data_module/contracts/market.py` — market leaf records 與驗證。
- `data_module/contracts/__init__.py` — 僅窄匯出 market contracts。
- `data_module/__init__.py` — 四個既有 public exports 的 lazy resolution；名稱、順序與 `__all__` 保留。
- `tests/test_data_market_contracts.py` — immutable/date/timezone/unit/revision/unknown/None/zero/identity/import/legacy export 測試。
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R007_IMPLEMENTATION_REPORT.md` — 本報告。

## Validation

- SOL type-check review 後，在 lazy `__getattr__` 分支前明示 `value: object`；僅修正局部型別推斷，runtime 行為未變。
- `.venv\Scripts\python.exe -m pytest tests\test_data_market_contracts.py tests\test_data_module.py -q -o addopts=`：13 passed。pytest 顯示 `.pytest_cache` 寫入權限警告；測試不受影響。
- `.venv\Scripts\python.exe -m py_compile data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py tests\test_data_market_contracts.py`：exit 0。
- `.venv\Scripts\python.exe -m mypy --explicit-package-bases data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py`：Success，3 source files 無問題。
- `git diff --check`：exit 0，無 whitespace error；Git 對既有 LF/CRLF 工作樹檔案顯示 normalization warnings。

## 風險與限制

Bare `import data_module` 現在不會立即把四個舊 class 放進 module globals；讀取對應 attribute、使用 `from data_module import ...` 或 star import 時會載入原 class。若外部 caller 仰賴 bare import 後檢查 `data_module.__dict__`，其觀察結果會改變；`dir(data_module)` 與 `__all__` 仍列出四個名稱。該行為改變是純 contracts leaf import 不觸發 concrete provider import 的必要條件，直接／star 匯入相容性已有測試。

IMPLEMENTATION_STATUS: READY_FOR_REVIEW

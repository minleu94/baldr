> **時點／狀態導覽（2026-10-11）**：本文的初審與 `INTEGRATION_STATUS` 是當時的歷史記錄，不等同 R008 整體現行 disposition。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項。此處僅導覽 task-level 狀態，不重裁本文特定審查範圍或限制；原始判讀與限制保留。

# R008 SOL 初審與 Gemini 正式審查交接

## 初審判定

R008 Luna 實作經兩輪 scope 內修正，已達可交 Gemini 獨立正式審查的凍結狀態；**R008 尚未 PASS，Wave 2 checkpoint 尚未關閉，Wave 3 仍 blocked**。SOL 實際檢查了兩個 parent package 的 tracked diff、兩個新 contract 原始碼、專用測試與實作報告；不只採信 worker 摘要。原先 mypy 的 9 個型別錯誤已在 R008 兩個 contract 檔內修正，沒有放寬 runtime 白名單或用廣泛 type-ignore。

## Scope 與凍結檔

既有檔的改動只包含：`app_module/__init__.py`、`decision_module/__init__.py` 的窄 lazy public exports，以及 `tests/test_update_service_import_contract.py` 的 before/after 載入時序 oracle。此三檔在 worker 接手前 clean，原 SHA 與範圍裁決記於 `R008_SCOPE_ADDENDUM.md`、`R008_IMPLEMENTATION_REPORT.md`。新增檔只包含兩個 recommendation package `__init__.py`、兩個 `contracts.py`、`tests/test_recommendation_contracts.py` 與任務報告。沒有改 RecommendationService、舊 DTO、codec、writer、UI、推薦演算法、ML store 或正式資料；沒有 stage、commit、push。

| 受審檔案 | SOL 現讀 SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `app_module/recommendation/__init__.py` | `F2020F50FACA5BE43F9FCB409F2E6135B07E6B9F78B4A6173EF3F25ACA1DE952` |
| `app_module/recommendation/contracts.py` | `C12670CDE79F1CBA9B3DB1EC2B7990CF1D2496B173C5ADC65B341AD5DB35E2C6` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` |
| `tests/test_recommendation_contracts.py` | `2975AC35434CA6F5C0A50388653CDFD7114B0451BA00DAD55A898327F92A8270` |
| `REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | `E0761D092C7CF612CCB94B2F69A6ED806FBCCBE5D3706EABF40ED95AC163AA98` |

## SOL 獨立驗證

- R008/R007/import/V-EXEC 組合：`67 passed`，exit 0；含 R008 專用 11、既有入口相容與 worker/取消／stale callback 切片。
- V-REC：`64 passed, 2 warnings`，exit 0；警示為既有 pandas dtype FutureWarning。
- V-PERSIST：`33 passed`，exit 0。
- V-REPLAY：`66 passed, 24 warnings`，exit 0；警示為既有同日收盤研究假設。
- 定向 mypy：`Success: no issues found in 4 source files`；八個受影響 Python 檔 `py_compile` 通過；`git diff --check` exit 0，只有既有 LF/CRLF 提示。Git index 無 staged paths。

專用 subprocess import audit 安裝 Python audit hook，對一般 contract import 拒絕非程式檔 open／SQLite connect；確認 decision contract 不導入 app，app contract 不預載舊 service/DTO/pandas/matplotlib。公開 `__all__`、direct/star import、`getattr`、class identity 具測試。裸匯入 parent 後 `__dict__` 不再立即含 public classes，是已明示的時序變更。

## Gemini 必查風險

1. 深凍結是否真正在每個 nested input/output 邊界複製 backing mapping、限制明示 frozen record 類型與 aware clock；是否存在可穿透的 mutable alias、unsupported enum/dataclass/subclass。
2. `completed` 與 `failed/cancelled` 互斥 decision 形狀、零候選合法完成、duplicate stock code、`items/assessments` 只讀委派；diagnostics 不作 completed 發布。
3. rule score、factor contribution 的 Decimal/int 與單位關係，特別是 bp unit 是否可能被任意精度 Decimal 假冒；`None`、0、legacy float 保留及後續轉換責任有無矛盾。R008 尚未接轉換 adapter，不可由本輪測試推論數值 parity。
4. parent lazy-export diff 是否有外部 import／反射副作用風險；既有載入時序測試是否只更新被核准的 eager side-effect oracle，未放寬 public identity。
5. Context/Request/source/result/ML references 是否各有唯一 owner；`related_references` 的 kind 限制是否足夠，沒有 new reverse dependency、live state 或重複 schema/storage。

Gemini 的正式判定須為 `REVIEW_STATUS: PASS`、`REVIEW_STATUS: CHANGES_REQUIRED` 或 `REVIEW_STATUS: BLOCKED` 之一。SOL 收到後仍須核對當時 repository SHA 與實際差異；Gemini PASS 不自動釋出 Wave 3。

INTEGRATION_STATUS: READY_FOR_GEMINI_REVIEW

# R010 Luna 獨立審查

> **狀態時點提示（2026-10-11）：** 本文前段 `INITIAL_REVIEW_STATUS: CHANGES_REQUIRED` 僅適用原凍結 SHA；同文後段對修正 SHA 的最終複審為 `REVIEW_STATUS: PASS`，另由 [SOL integration acceptance](R010_SOL_INTEGRATION_ACCEPTANCE.md) 接受 R010 有界契約範圍。R031 的現行 task disposition 與 R026／R029 後續 supported caller/profile 範圍見 [R031 31-task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)；不代表所有模型／profile 或 promotion 已驗收。原 finding 保留為歷史證據。

## 初版審查（舊凍結 SHA）

INITIAL_REVIEW_STATUS: CHANGES_REQUIRED

R010 的實際改動限於核准的新 ML leaf contract、application Protocol、專用測試及實作報告；基本 immutable/cutoff/import 邊界與既有 20-feature ABI 的未變更狀態有證據支持。但契約尚有兩項原 scope 內可修正的缺口：production 安全狀態可互相矛盾，以及無法保留 R007 已支援的 date-only availability。

## 凍結產物與相依 SHA

本次依指定凍結 worktree `output/agent_worktrees/refactor_r010_20260922` 審查。實作報告 SHA 與派工指定值一致；三個 R010 原始碼／測試檔 SHA 亦與報告一致。

| 檔案 | SHA-256 |
|---|---|
| `ml_module/prepared_input_contract.py` | `97B58559CCD0D77D5A83B17379A39A88A4845C4F05799107D6C16698C46A9255` |
| `app_module/recommendation/ml_adapter.py` | `F7DFB234D6DFE72CFBCA742DB9ED21EF2EA2E6654EB886A182545AD9B9E55C22` |
| `tests/test_prepared_ml_input_contract.py` | `8B7FCB73AD5FDDFA03FBAD74724B1F843F91CD0C641EAE4E4F7E89F5564F5086` |
| `REFACTOR_REPORTS/R010_IMPLEMENTATION_REPORT.md` | `F48853110939003484891209A8EBFCC0D06747B1B07482CFFC1E21020FECCD51` |

依 `WAVE3_DISPATCH_BASELINE.md` 逐項重算 14 個 R006/R007/R008 凍結相依檔，worktree 與 main 的原始 bytes SHA-256 **14/14 一致**，包含 R006 ABI baseline test 及 R007/R008 contract/test。R010 沒有修改這些相依檔，也沒有更動 feature builder、20-feature registry、model、loader、store、provider 或正式資料。

R006/R007/R008 前置 PASS 證據已核對：`R006_SOL_INTEGRATION_REVIEW.md` 為 `TASK_STATUS: PASS`；`R007_LUNA_TZNAME_INDEPENDENT_REVIEW.md` 為 `REVIEW_STATUS: PASS` 且 `R007_SOL_TZNAME_ACCEPTANCE.md` 為 `TASK_STATUS: PASS`；`R008_SOL_RESULT_ID_ACCEPTANCE.md` 與 `WAVE2_RESULT_ID_CHECKPOINT.md` 均為 PASS。這些證據涵蓋 R006 分層 ABI 基線、R007 immutable market/availability record 與 R008 exact result identity，不代表本次發現已解決。

## 實際範圍與驗證

R010 專用實際產物只有上述三個程式／測試檔及 implementation report。Adapter 只定義 `RecommendationMLAdapter` 與 `PreparedMLProjector` Protocol，要求明確 `mode`，未實作 source access、feature building、model loading 或 inference。ML contract 的 AST/subprocess 測試確認沒有 app/data/domain import、DB/file/model I/O import 或對應呼叫；execution/result、候選、rule/ML snapshot、feature/transform、model/release、成本 receipt identity 均有 typed 欄位。候選與 records 使用 tuple/frozen/slotted record，建構時複製 list 輸入；兩 lane 可使用不同 snapshot，但各自受共同 cutoff 與 decision time 限制。

獨立驗證結果：

- 指定五檔 R010＋R006/R007/R008 regression bundle：**88 passed in 4.52s**。
- `py_compile`：三個 R010 Python 檔通過。
- scoped mypy：`ml_module/prepared_input_contract.py`、`app_module/recommendation/ml_adapter.py`，**Success: no issues found in 2 source files**。
- 14 個共用凍結相依 SHA：**14/14 相同**。
- 20-feature ABI：本任務沒有修改 ABI/source 檔；R006 PASS baseline 仍是本次依賴證據。本審查未執行訓練、正式 artifact 載入或 prediction parity，亦不將其宣稱為已驗證。

## 必須修正

1. **[P1] `ModelBinding` 接受自相矛盾的 production 狀態。** 在 `ml_module/prepared_input_contract.py:378` 的檢查只拒絕 `shadow_only=True` 或 `production_eligible=False` 的組合；它沒有要求 quarantine 為 `CLEAR`、permission 為 `GRANTED`。獨立反例以 `quarantine_status=QUARANTINED`、`permission_status=DENIED`、`shadow_only=False`、`production_eligible=True`、`production_action_allowed=True` 建構 `PreparedMLInput`，目前被接受。這會讓明示的隔離／拒絕狀態與 production action authorization 同時為真，無法作為可信安全契約。請在原 R010 scope 加入 fail-closed 一致性驗證，並新增上述反例測試；若狀態未知，也不得宣告 production action allowed。

2. **[P1] `AvailabilityBinding` 遺失 date-only availability 精度。** `ml_module/prepared_input_contract.py:183` 只有 `status` 與 `available_at`，KNOWN 強制必須是 aware `datetime`。R007 的 `data_module/contracts/market.py:138` 明確支援只有 `available_date` 而沒有 timestamp 的 known availability。現契約不能表示該合法來源證據；呼叫端只能把它降成 UNKNOWN，或自行補造時間。前者遺失可得性證據，後者會違反 unknown/time 精度不可推定的規則。請在 R010 原 scope 加入 date-granularity 欄位與驗證：KNOWN 至少提供日期或 aware timestamp；UNKNOWN 不得帶任一值；若有 timestamp，保留 timestamp 並依既定時間規則核對；僅有日期時不補造時分秒，仍以日期 cutoff 驗證。新增 date-only、known date 超過 decision date、UNKNOWN 帶日期等正反例。

## 初版限制與交接

未發現新增逆向 import、I/O 或 R010 scope creep；也未執行 R026 prepare/build/infer、live-source barrier、模型載入、training/prediction、正式 persistence 或 R7 搬移實驗，這些不在 R010 範圍。R010 需依以上兩項修正後，以新 SHA 重新獨立審查；本報告只適用於上述凍結 SHA。

## 修正後獨立複審（目前凍結 SHA）

本次重審凍結版本的 implementation report SHA 為 `CE34EAA983CF0938C92D9D4C4533B95B195B9547BA0FBCB2A3FDA037066A418D`。目前三個 R010 檔案 SHA 與該報告一致：

| 檔案 | SHA-256 |
|---|---|
| `ml_module/prepared_input_contract.py` | `E39EE8ACB37CEDBCABE5276FE85703B2FDBEB98C2DE9702B23184934D6513D03` |
| `app_module/recommendation/ml_adapter.py` | `61ED294BC577A9D68A1887DC73F357C5563F6D7D465F3FC5C97235D1DB300755` |
| `tests/test_prepared_ml_input_contract.py` | `CBF892E0ABFF3583962205E7C3BC41F798D29E8D4087683D15BC3BFC1F142B9A` |
| `REFACTOR_REPORTS/R010_IMPLEMENTATION_REPORT.md` | `CE34EAA983CF0938C92D9D4C4533B95B195B9547BA0FBCB2A3FDA037066A418D` |

### 初版 finding 的修正證據

1. `ModelBinding.__post_init__` 現在只有在 quarantine 為 `CLEAR`、permission 為 `GRANTED`、`shadow_only=False` 且 `production_eligible=True` 時，才接受 `production_action_allowed=True`。我獨立嘗試 QUARANTINED、DENIED 與 UNKNOWN 的狀態組合；均以 `ValueError` 拒絕。反向合法組合可建構。相應 regression test `test_production_action_requires_every_model_safety_gate` 對這些狀態逐一斷言拒絕。

2. `AvailabilityBinding` 現在分別保留 `available_date` 與 aware `available_at`；KNOWN 至少要有其中一者，UNKNOWN 兩者皆不得附帶。`PreparedMLInput` 將 timestamp 與 `decision_at` 比較，並將 date 與 `decision_date` 比較；沒有強迫兩者的曆日相同。獨立反例確認：只有日期的 known 值精確保留；超過決策日的日期及 UNKNOWN 附日期均拒絕；日期 `2026-09-21` 與 timestamp `2026-09-20T09:00:00+00:00` 可以同時保留，且兩者不必相等。

3. 同日 date-only 值仍只保存日期且 `available_at is None`，不會宣稱在該日的 `decision_at` 之前已可得。Protocol 明文要求沒有額外可驗證的日內政策時拒絕 projection；獨立檢查到的 `RecommendationMLAdapter` 與 `PreparedMLProjector` Protocol 仍沒有 I/O 或推論實作。這是交給後續 projector 實作者遵守的 fail-closed contract，不是 R010 已提供 runtime projector 的證據。

### 新凍結版實際範圍與驗證

R010 專用產物仍是 ML leaf contract、application Protocol、R010 tests 與 implementation report。`ml_module/prepared_input_contract.py` 沒有 app/data/domain/provider/DB/model import；adapter 只依賴 app execution contract 與 ML leaf types，未加入 source access、feature building、model loading 或 inference。tests 的 AST/subprocess import audit 與 Protocol no-I/O 檢查均包含在重跑套件中。未發現新增逆向依賴、scope creep 或對既有 20-feature ABI、模型、loader、store、provider、訓練資料及正式資料的修改。這次沒有執行訓練、production model load、prediction parity、ML projection 或 R7 搬移實驗。

- 獨立重跑指定 R010＋R006/R007/R008 五檔 bundle：**92 passed in 4.69s**。
- scoped mypy：**Success，2 source files 無問題**。
- 13 個原 Wave 3 frozen dependency 與 main 的 raw SHA：**13/13 相同**。
- 額外 R009 `app_module/recommendation/contracts.py` dependency 為指定 SHA `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`；相對 main 舊版的實際 diff 只有新增 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)`。該窄 addendum 尚屬獨立 R009 review 範圍，R010 本次審查不替它判 PASS，也不代表 Wave 3 已整合通過。
- R006/R007/R008 前置 PASS 證據仍成立；R006 的 ABI baseline 測試包含於 92 項 bundle。沒有因本次 R010 PASS 宣稱完成歷史模型載入或 prediction 相容驗證。

### 複審限制

本次結論只適用於表列 R010 SHA，以及明確標示的 R009 app contract dependency SHA。R010 獨立審查通過不等同整合驗收；待 R009 addendum 獨立審查與後續 Wave 3 整合驗證完成後，才可判斷 Wave 3 gate。舊版 CHANGES_REQUIRED findings 與其舊 SHA 保留於本報告前半部，作為已修正問題的歷史證據。

REVIEW_STATUS: PASS

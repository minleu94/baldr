# R008 app contract aware datetime 深凍結回修報告

> 本報告記錄 2026-09-22 app-owner 深凍結切片與其 SHA／QA 證據；文末等待跨 owner 統一複核是當時狀態。R008 現行 bounded contract disposition 見 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)；本切片不代表其他 consumer 或 Wave gate 完成。

日期：2026-09-22

## 範圍與結果

本切片只修改 `app_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py`，並新增本報告。沒有修改 decision contract/test、parent package、service、codec、writer、UI 或其他 R-task；沒有 I/O、金融數值計算或業務規則變更。

`_freeze_aware_datetime()` 現在同時驗證並封存直接時間欄位及 `_freeze_value()` 遞迴遇到的 datetime。只有 `tzinfo` 精確型別是 `datetime.timezone`（包括 `timezone.utc` 與固定偏移）或 `zoneinfo.ZoneInfo`，且回傳的 offset 與 tzname 分別是精確內建 `datetime.timedelta` 和 `str` 時，才保留原 datetime。這些標準時區不可變，保留可維持區域時區名稱與跨 DST 日期運算語意。若 offset 是 `timedelta` 子類，則透過 `timedelta` 基底的 `days`、`seconds`、`microseconds` descriptor 讀取底層整數分量，重建精確內建 `timedelta`；若名稱是 `str` 子類，則透過 `str.__str__()` 建立精確內建 `str`。接著以這些快照建立固定 offset 時區，不呼叫子類覆寫屬性，也不保留可變 subclass 別名。其他 tzinfo 也在封存當刻採相同方式快照。

直接欄位涵蓋 `Context.decision_at`、`ExecutionEvent.occurred_at` 與 `SaveReceipt.persisted_at`。遞迴路徑涵蓋 `QualityReport.metrics`、`ExecutionEvent.details`、巢狀 mapping/list，以及 execution 內 `DecisionBatch` 的 `NegativeEvidence.observed_at` 與 details。自訂時區快照保留封存當刻的 wall-clock、microseconds、fold、UTC offset、ISO 格式與 timestamp。

## 相容限制

- `datetime.timezone` 固定偏移、`timezone.utc` 與標準 `ZoneInfo` 在 offset 為精確內建 `timedelta` 時維持原物件及既有語意；ZoneInfo 的 DST 規則、時區名稱與跨日期運算均保留。
- `timedelta` 子類的數值 offset 會正規化成內建 `timedelta`。因此即使輸入包在精確 `datetime.timezone` 中，只要 offset 帶有 subclass payload，也會建立新的固定偏移時區以切斷巢狀別名；若原固定 timezone 有明示名稱，會保留該名稱。
- 標準 timezone／ZoneInfo 的名稱若不是精確內建 `str`，會經 `str.__str__()` 複製文字內容後再封存；原 name subclass 的 mutable attributes 不會傳入合約。名稱文字、offset、ISO、timestamp 與 fold 維持不變。
- 其他 tzinfo 封存後代表封存當刻的固定偏移。這會捨棄其 `tzname()` 文字與封存後跨 DST／日期運算時的動態規則；當刻的 ISO/timestamp 與牆上時間不變。此取捨避免對未知 tzinfo 使用不可靠的 `deepcopy`，並符合契約不保留可變 alias 的要求。
- 沒有新增外部資料存取或時區資料載入；contract import 的既有無 I/O 測試包含在本次 app contract 測試執行中並通過。

## 回歸測試與驗證

新增可變 `tzinfo.hours` 測試，建立後由 0 改為 +9 小時，確認以下已封存時鐘仍保持原 offset 與內容：Context、ExecutionEvent、QualityReport metrics、SaveReceipt，以及 nested source path mapping/list 和 `NegativeEvidence` dataclass path。另確認 UTC 與固定偏移輸入保留原 tzinfo。

R007 獨立複核後新增 mutable `timedelta` subclass payload 測試，同時覆蓋自訂 tzinfo 和帶明示名稱的 `timezone(MutableDelta)` 輸入。子類底層 offset 為 +05:00:17.000231，但覆寫 `days` property 回傳 -1；測試驗證封存值仍保持底層 offset、timestamp、ISO 與 fold。payload 後續修改後，Context、Event、QualityReport metrics 與 SaveReceipt 封存值的 `utcoffset()` 仍是精確內建 `timedelta`，且不再暴露 caller payload；明示時區名稱亦保留。

R008 獨立 final review 發現 exact `timezone` 的名稱可以是帶可變 attributes 的 `str` 子類。新增回歸測試讓名稱子類在封存後修改 `labels`，覆蓋 Context、Event、QualityReport metrics、SaveReceipt 及巢狀 mapping/list 路徑；所有封存值仍回傳精確內建 `str`，文字內容、offset、ISO、timestamp、fold 與 datetime repr 保持穩定。

- `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py -q -o addopts= -p no:cacheprovider`：21 passed。
- `.\.venv\Scripts\python.exe -m mypy --explicit-package-bases --follow-imports=silent app_module/recommendation/contracts.py`：1 source file checked，無錯誤。
- 未加 `--follow-imports=silent` 的 mypy 呼叫另報 4 個匯入相依檔案診斷：`analysis_module/technical_analysis/technical_indicators.py` 3 個參數型別診斷，以及 `app_module/update_service.py` 1 個型別標註診斷；本切片未修改這些檔案。
- `.\.venv\Scripts\python.exe -m py_compile app_module/recommendation/contracts.py tests/test_recommendation_contracts.py`：通過。

本報告只記錄 app owner 切片的驗證。跨 owner 的 R008 focused suite 與最終 diff/review 由 SOL 在所有 owner 完成後統一重跑。

## SHA-256

| 檔案 | 本切片修改前 | 本切片修改後 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `B5F2B11FF362F470974B89D0B7E5881EEAEE9F1076517F43EAEA94EC50851C83` | `8CEFCC9D00B8E35D38488D8603486BFEFBBCA575AC74DE27C4BD8147D087E9C1` |
| `tests/test_recommendation_contracts.py` | `DDADE06FBD3F82055FBAE0AC165DC6D71ACF030CA27ABBD9000F5AC8FB4CC08E` | `83847793C9C5B78FED6AC12FD0A2ED4E793D76D51FA99656E9E84DBE3B7F0D84` |

R007 複核補強的 SHA：

| 檔案 | 補強前 | 補強後 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `BBFBFD0B8F8A18C4A90CAA1E618203EF2738D4E75B0C1ECA32B96E9AAF693684` | `2D8EA808F1CAF245D902F38E8ABBCB36E83C7F0C170079C1DCBE921336A723F7` |
| `tests/test_recommendation_contracts.py` | `2B7CB0DFFA3CC30835087D54D61DF768437B295AAE278B056041DCD8E3D58F9D` | `FAC44205AD94265C3363814233C35D9350F53FD4776AD2A56013C87318F45984` |

複核後 descriptor 修正的 SHA：

| 檔案 | 修正前 | 修正後 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `2D8EA808F1CAF245D902F38E8ABBCB36E83C7F0C170079C1DCBE921336A723F7` | `1C30155F42B7F482DAAF7C8F46D7AB8EEB41569CAC0EC19F2392D484BCBF7AB3` |
| `tests/test_recommendation_contracts.py` | `FAC44205AD94265C3363814233C35D9350F53FD4776AD2A56013C87318F45984` | `A726246D6B62B88032247164A8E93259722CB247F35F572D30540C9B306D64BF` |

TZ name alias 複核修正 SHA：

| 檔案 | 修正前 | 修正後 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `1C30155F42B7F482DAAF7C8F46D7AB8EEB41569CAC0EC19F2392D484BCBF7AB3` | `8CEFCC9D00B8E35D38488D8603486BFEFBBCA575AC74DE27C4BD8147D087E9C1` |
| `tests/test_recommendation_contracts.py` | `A726246D6B62B88032247164A8E93259722CB247F35F572D30540C9B306D64BF` | `83847793C9C5B78FED6AC12FD0A2ED4E793D76D51FA99656E9E84DBE3B7F0D84` |

## 回滾清單

| 檔案 | 變更類型 | 回滾方式 | 回滾風險 |
|---|---|---|---|
| `app_module/recommendation/contracts.py` | 修改 | 僅撤回本報告描述的 `_freeze_aware_datetime`、datetime 遞迴分支及三個直接欄位封存 hunks；該檔本切片前為 untracked，勿用 `git checkout HEAD` 覆蓋。 | 會恢復 mutable tzinfo alias 問題。 |
| `tests/test_recommendation_contracts.py` | 修改 | 僅移除 `MutableHoursTZ`、兩個本切片新增的時區測試。 | 會失去對 mutable tzinfo alias 的回歸保護。 |
| 本報告 | 新增 | `Remove-Item -LiteralPath 'docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R008_APP_DATETIME_FREEZE_REPORT.md'` | 無程式影響。 |

回滾前確認工作樹狀態，只撤回本表列出的切片差異，保留其他 R008 與 unrelated dirty files；本切片未 stage、commit 或 push。

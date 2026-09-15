# Decision → Outcome Journey 唯讀垂直切片 QA（2026-09-14）

## 結論

本輪完成一個獨立的 "decision-outcome-journey.v1" read model：以單一
Recommendation result 為根，將明示 identity 的 Evidence event、Evidence
outcome、Journal、精確 Portfolio ledger event 與 legacy Portfolio trade 分開
投影成可排序的 timeline。它沒有建立新資料庫、沒有修改既有 repository、沒有
執行 recommendation／outcome 計算，也沒有將研究 return 或使用者紀錄宣稱為
實際 broker PnL。

目前可由 Journal／Workbench 之後呼叫：

~~~python
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService

service = DecisionOutcomeJourneyService.from_paths(
    output_root=output_root,
    evidence_db_path=evidence_db_path,
    journal_path=output_root / "portfolio" / "journal_entries.jsonl",
    portfolio_trades_path=output_root / "portfolio" / "trades.jsonl",
    portfolio_ledger_path=existing_ledger_path_or_none,
)
journey = service.build(result_id, query_boundary="2026-09-14")
~~~

## 來源與 identity 契約

| 來源 | 真實讀取位置／欄位 | Journey key 與連結規則 |
| --- | --- | --- |
| Recommendation result | output/recommendation/runs/<result_id>.json；result_id、config.decision_date、run_context.source_id、策略／universe identity | 根 key 是 result_id；candidate key 是 (result_id, stock_code)，代號只取保存的 stock_code／證券代號 |
| Evidence event | evidence_events；event_id／event_hash、source_id、source_snapshot_id、symbol、available_date | 只接受 source_id == result_id、source_snapshot_id == result_id 或 importer 明示的 metadata.source_result_id == result_id；日期／股票只做欄位與 query bound，不形成 join |
| Evidence outcome | evidence_outcomes；(event_id, window_days, return_basis) | 只由 exact event_id 的 parent event 取得；duplicate natural key 若 payload 衝突則保留並標 conflict |
| Journal | output/portfolio/journal_entries.jsonl；journal_id、linked_id／linked_type、source_id、source_snapshot_hash、thesis_id | 只由 result key、精確已連入 ledger event key 或相符的明示 snapshot hash 連入；revision_of／revises_id／reverses_event_id 只保存，不猜 target |
| 精確 Portfolio ledger | 呼叫端提供既有 portfolio_ledger.sqlite，以 PortfolioLedgerRepository.open_read_only() 開啟；event_id、source_namespace、source_id、source_snapshot_hash、thesis_id、reverses_event_id | trade 以 result source identity／snapshot hash 連入；compensation 只有在 reverses_event_id 精確指向已連入 trade 時才補列，仍保持獨立事件 |
| Legacy Portfolio trade | output/portfolio/trades.jsonl；trade_id、source_id、source_snapshot_hash | 與精確 event ledger、Recommendation result 分開；目前舊資料沒有 result source key 時為 unlinked，不用日期／股票補接 |

Recommendation root 會保留原始 JSON 的策略版本、config hash、universe policy／
snapshot identity。若 result 本身沒有 source_snapshot_id 或
source_snapshot_hash，Journey 不用 result_id 或 universe snapshot 代填；
Evidence importer 另行保存的 source_snapshot_id 只留在 Evidence event。

## Fail-closed 與時間規則

- 找不到舊 key、缺少 event／outcome、invalid payload、同 key duplicate 或
  identity 衝突，都保留 source payload 並標示 unknown、unlinked、deferred、
  ambiguous 或 conflict；不生成 surrogate identity。
- Evidence bounded read 使用 max_events + 1 判斷 last_has_more。達上限時輸出
  evidence_read_truncated，若目標不在已讀 page 只能是 unknown／partial，不能
  宣稱「沒有關聯」。
- query_boundary 接受 ISO date 或帶 timezone 的 aware datetime。aware
  datetime 先轉 UTC 比較；date-only 是來源宣告的 calendar-day boundary，與
  timestamp 比較時只比較 calendar date；naive timestamp 或 invalid value 不
  猜 UTC，視為不可用／unknown。
- timeline 保留 source_at、occurred_at、available_at 與 query_boundary，以
  normalized aware time、類別順序與 key 穩定排序；原始字串仍在 original_payload。
- 固定 maturity windows 為 5/10/20/60 trading days。缺少或尚未在 query
  boundary 可見的 outcome 只產生無數值的 maturity row。
- EvidenceOutcomeRecord.is_execution_pnl 只保存來源宣告；正式 recommendation
  evidence 的 False 對外語義為 research_forward_return。Journey 的
  investment_effectiveness_claim 永遠為 False。
- Recommendation、portfolio_trades、精確 portfolio_ledger_events 是不同
  DTO 集合。沒有 actual fill 不會阻擋 recommendation／Evidence tracking；有
  paper／manual／backtest namespace 時也不會自動合併成個人實際持倉。

## 合成 fixture 驗證

測試檔案：tests/test_decision_outcome_journey.py。所有資料明確標為 synthetic，
未使用正式市場資料。

涵蓋：

1. result → candidate → event → (event_id, window) outcome 精確 chain。
2. 相同股票／日期但不同 source_id 不會誤接。
3. Journal revision reference 與 ledger compensation reversal。
4. missing result/key、missing outcome、conflicting identity、conflicting
   duplicate outcome 的 fail-closed 狀態。
5. stable timeline sort、aware offset 同 instant、真正 future、date-only
   當日 boundary、naive／invalid timestamp。
6. 原始 nested payload 的 immutable snapshot 與 to_dict() 還原。
7. bounded Evidence page 的 has_more／partial coverage。
8. read-only adapter 的 result／JSONL／SQLite 檔案 stat 與 bytes 不變。
9. 沒有 fill 時 recommendation tracking 仍可用；legacy float 金額只保留 raw
   payload，不進行金融計算。
10. CLI/projection 同時列出每個 horizon 的 link_status 與 outcome_status；
    linked 但 insufficient_future_data 不會被呈現為已成熟。

## 執行命令與結果

在 repository root C:\Projects\PythonProjects\technical_analysis 執行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_outcome_journey.py -q -o addopts=
~~~

結果：16 passed。pytest 顯示既有環境無法寫入 .pytest_cache 的 warning，沒有
測試失敗，也沒有改寫正式資料。

~~~powershell
.\.venv\Scripts\python.exe -m mypy app_module/decision_outcome_journey.py tests/test_decision_outcome_journey.py scripts/inspect_decision_outcome_journey.py
~~~

結果：Success: no issues found in 3 source files。

~~~powershell
.\.venv\Scripts\python.exe -m py_compile app_module\decision_outcome_journey.py tests\test_decision_outcome_journey.py scripts\inspect_decision_outcome_journey.py
~~~

結果：通過。

## 正式資料 bounded smoke

唯讀腳本：scripts/inspect_decision_outcome_journey.py。正式路徑依
TWStockConfig 的預設位置解析，但腳本不建立 TWStockConfig，避免其
_ensure_directories() 成為讀取副作用；預設讀取：

- data root：D:\Min\Python\Project\FA_Data
- output root：D:\Min\Python\Project\FA_Data\output
- evidence DB：D:\Min\Python\Project\FA_Data\sqlite\twstock.db
- journal：output\portfolio\journal_entries.jsonl
- legacy trades：output\portfolio\trades.jsonl

命令：

~~~powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts\inspect_decision_outcome_journey.py --result-id scheduled_rec_20260914_051003
~~~

結果摘要：

~~~text
READ_ONLY=True
WRITES_ALLOWED=False
IDENTITY_FILLING=False
[official] RESULT=scheduled_rec_20260914_051003
[official] STATUS=linked
[official] DECISION_DATE=2026-09-14 CANDIDATES=1
[official] SOURCE_PROVIDER=DefaultRecommendationMarketDataProvider
[official] EVIDENCE_EVENTS=582 OUTCOMES=4 MATURITY_BY_WINDOW=[
  {'candidate_key': ['scheduled_rec_20260914_051003', '1528'], 'window_days': 5, 'link_status': 'linked', 'outcome_status': 'insufficient_future_data'},
  {'candidate_key': ['scheduled_rec_20260914_051003', '1528'], 'window_days': 10, 'link_status': 'linked', 'outcome_status': 'insufficient_future_data'},
  {'candidate_key': ['scheduled_rec_20260914_051003', '1528'], 'window_days': 20, 'link_status': 'linked', 'outcome_status': 'insufficient_future_data'},
  {'candidate_key': ['scheduled_rec_20260914_051003', '1528'], 'window_days': 60, 'link_status': 'linked', 'outcome_status': 'insufficient_future_data'}
]
[official] JOURNAL=0 PORTFOLIO_LEDGER=0 PORTFOLIO_TRADES=0
[official] COVERAGE evidence_read=1712, evidence_linked=582, evidence_unlinked=1130, ... trade_read=3, trade_linked=0, trade_unlinked=3
[official] PERSONAL_RECORDS_SEPARATE=True EFFECTIVENESS_CLAIM=False
SOURCE_STAT_UNCHANGED=True
~~~

對 4 筆 outcome 的 read-back 另核對為：

~~~text
event_id=evt_75c2573b4c2342138135112a0cfafc0c
windows=5,10,20,60
return_basis=close_to_close_event_date
outcome_status=insufficient_future_data
data_quality=missing
is_execution_pnl=False
performance_semantics=research_forward_return
~~~

這表示目前結果已建立 exact Evidence chain，但 forward outcome 尚未成熟，不能
解讀為正／負 PnL。正式 trades.jsonl 有 3 筆舊 user-recorded trade，均沒有
source_id（所以 3 筆 unlinked）；這不會阻擋上述 recommendation tracking。
Journal 檔目前為空，沒有可列出的 user decision／thesis；本輪也沒有發現可用的
精確 personal portfolio_ledger.sqlite。正式 DB、result JSON、journal 與
trades 的 stat 在 smoke 前後未變。

使用日界線的命令：

~~~powershell
.\.venv\Scripts\python.exe scripts\inspect_decision_outcome_journey.py --result-id scheduled_rec_20260914_051003 --query-boundary 2026-09-14
~~~

結果狀態為 partial，4 個 maturity 為 deferred；這是 query boundary 對後續
outcome availability 的 fail-closed 呈現，不會把未能以明確時間證明可用的資料
回灌決策。這次 smoke 同樣輸出 SOURCE_STAT_UNCHANGED=True。

腳本也支援 --shadow-output-root／--shadow-evidence-db，但本機沒有另行指定的
shadow result path，因此本 QA 不宣稱 shadow chain 已通過。

## 尚未完成的整合

- 本輪未改 UI、Workbench、Decision Desk、Journal editor 或 Manual；下一步需由
  parent 將 DecisionOutcomeJourneyService.build(result_id, query_boundary=...)
  接入既有 read-only view，並決定 UI 如何分組 recommendation、research
  outcome、journal、paper／manual trade。
- 本輪未修改 shared architecture、navigation、snapshot、Manual 或 roadmap
  文件；這份獨立 QA 只記錄契約與待整合點，避免覆蓋其他 agent 的未提交變更。
- 現有獨立 PaperTradeLedger 尚未納入 Journey DTO；它仍
  應沿用其 research_only=True／禁止 broker order 的邊界，不能與 personal
  ledger 合併。
- 沒有新增 scheduler、broker、approval、formal ledger promotion 或全市場
  recompute；這條切片不代表 V5／ultimate journey 完成。

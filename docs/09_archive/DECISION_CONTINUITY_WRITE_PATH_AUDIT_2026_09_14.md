# V5「觀察清單／持倉 → 接受／略過／筆記 → 下次檢視」Decision Identity 保存鏈審查

> **歷史實作前基線（2026-10-10）：** 本審查記錄 Increment A 實作前的 delete/clear 與 tombstone 缺口；同日後續 [Increment A QA](DECISION_CONTINUITY_WRITE_PATH_QA_2026_09_14.md) 已接受 append-only tombstone 的 bounded storage／Journal slice，本文舊結論在該範圍已被後續收據覆蓋。UI Increment B 仍是當時另外的範圍；本文方案與授權脈絡不可當成目前實作許可。現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

**日期：** 2026-09-14
**狀態：** 僅供父層審查；本文件不授權實作 write path
**範圍：** 觀察清單、持倉、交易日記、既有 ledger、研究下鑽與已提交的 `DecisionOutcomeJourney`。
**本輪限制：** 不改 UI／core／既有 Matrix、Manual、roadmap，不執行交易，不寫正式或測試資料，不建立 branch／worktree，不 push。

## 1. 審查結論

目前沒有一條已存在、可供 V5「接受／略過／筆記／下次檢視」直接使用的完整保存鏈。現況是「部分入口偶爾保存 `source_id`，但沒有一致的 `result_id + source_snapshot_id/hash + stock_code` decision identity；刪除與清空又會破壞可回放歷史」。

1. `DecisionOutcomeJourney` 是唯讀研究投影，不是 writer；它要求推薦 root 的 exact `result_id`，candidate key 是 `(result_id, stock_code)`，不以同股、同日、排序位置或文字備註補接。見 `app_module/decision_outcome_journey.py:1-17, 101-174, 530-637, 848-1002, 1259-1299`。
2. 推薦頁「加入觀察清單」在有已保存結果時會把 `current_result_id` 放進 `WatchlistItem.source_id`，並保存 `stock_code`；但 `WatchlistItem` 沒有 `source_snapshot_id/hash`，且以 `stock_code` 去重，後續同股不同結果不能並存。見 `ui_qt/views/recommendation_view.py:2208-2234`、`app_module/watchlist_service.py:18-31, 181-234`。
3. 手動觀察清單、market watch／smart money、universe 載入路徑只送 `stock_code`（加名稱、來源或自由文字備註）；推薦自動保存到 universe 也只是 codes，`result_id` 只出現在 description 文字，不是結構化 key。見 `ui_qt/views/watchlist_view.py:745-824, 1196-1251`、`ui_qt/views/strong_stocks_view.py:360-394`、`ui_qt/views/weak_stocks_view.py:342-376`、`ui_qt/views/smart_money/smart_money_flow_view.py:825-852`、`app_module/recommendation_save_coordinator.py:101-145`、`app_module/universe_service.py:52-99`。
4. 舊 Portfolio／Journal UI 會保存股票代號與時間；交易 UI 可能把策略選擇值送成 `source_id`，但沒有送 `source_snapshot_hash`，而日記 UI 完全沒有送 `linked_id/source_id/source_snapshot_hash`。直接呼叫 service 的 API 雖接受這些欄位，但不能把「API 可接受」誤當成「現有 UI 已保存」。見 `ui_qt/views/portfolio_view.py:287-365, 2156-2198`、`app_module/portfolio_service.py:57-145`、`app_module/journal_service.py:22-57`。
5. 精確 `PortfolioLedgerRepository` 已具備 immutable event、exact source identity 與 `reverses_event_id` compensation；但 `PortfolioService` 只有在 caller 明確注入 repository 時才使用它，桌面 UI 預設仍是 legacy `PortfolioJsonlStore`。見 `ui_qt/main.py:248-253`、`app_module/portfolio_service.py:38-55, 306-413`、`data_module/portfolio_ledger_repository.py:70-177, 223-246, 267-389`。
6. Journal／legacy trade／watchlist 的現行刪除或清空是覆寫／物理刪除，不是 revision 或 tombstone。`DecisionQualityRepository` 的 status history 雖然 append-only，但它描述的是 process-review item 的 reviewed/dismissed，不是 V5 candidate 的 accept/skip。見 `app_module/portfolio_store.py:21-78`、`app_module/journal_service.py:59-86`、`app_module/portfolio_service.py:207-228`、`data_module/watchlist_repository.py:31-51`、`app_module/decision_quality_repository.py:201-324`。

本輪的最小建議是：先由父層審查 identity 與 revision contract；後續只沿既有 store 增加 revision／tombstone／exact compensation，不另造 parallel DB，也不先把 accept 轉成交易。

## 2. 現有保存鏈

```text
Recommendation result (exact result_id)
        │
        ├─ Decision Desk / Workbench：顯示 identity、唯讀下鑽，不保存 V5 action
        │
        ├─ Recommendation → Watchlist：有時 source_id=result_id；snapshot 遺失
        │       └─ Watchlist → Research / Universe：多數只剩 stock_code
        │
        └─ Portfolio / Journal：legacy JSONL；只有 caller 明確傳 key 才能 exact link
                └─ DecisionOutcomeJourney：只讀 exact link；缺 key 不猜
```

### 2.1 Journey 的 identity SSOT 與 fail-closed 行為

| 範圍 | 已凍結的 key／規則 | 證據入口 |
|---|---|---|
| Recommendation root | `result_key = (result_id,)`；payload 缺少或衝突時保留 requested key，狀態 `UNKNOWN/CONFLICT`，不以日期／股票造 key。 | `app_module/decision_outcome_journey.py:101-145, 1004-1114` |
| Candidate | `candidate_key = (result_id, stock_code)`；缺股票代號為 unknown，不取 row 順序或其他候選猜測。 | `app_module/decision_outcome_journey.py:148-174, 1259-1299` |
| Evidence | 只接受 `source_id`、`source_snapshot_id` 或 importer 明示的 `metadata.source_result_id`；日期、股票只作欄位／query boundary。 | `app_module/decision_outcome_journey.py:1301-1465`；`docs/06_qa/DECISION_OUTCOME_JOURNEY_2026_09_14.md:31-32` |
| Journal | 由 exact result key、已連入 ledger event key、或相符的明示 `source_snapshot_hash` 連入；revision/reversal 欄位不會自行找 target。 | `app_module/decision_outcome_journey.py:1756-1805, 2069-2122` |
| Ledger／legacy trade | 精確 ledger 以 `source_id`／snapshot hash 連入；compensation 必須由 exact `reverses_event_id` 指向已連入 trade。沒有 exact source key 的 legacy trade 是 `UNLINKED`，但不阻擋 recommendation tracking。 | `app_module/decision_outcome_journey.py:1625-1754, 2125-2272`；`docs/06_qa/DECISION_OUTCOME_JOURNEY_2026_09_14.md:34-36, 165-166` |

目前 `_identity_link_status()` 在「user row 所有來源欄位都空白」時回傳 `UNLINKED`（`app_module/decision_outcome_journey.py:2541-2565`）；root／maturity 缺 key 則有 `UNKNOWN`。這是既有 read model 的分類，不是未來 write path 可以猜值的理由。新增 continuity revision 應直接保存 `identity_status=unknown`，不把 unknown 升格為 linked。

## 3. 使用者操作逐項盤點

| 使用者操作／入口 | 目前實際保存 | `result_id`／snapshot／stock code 判定 |
|---|---|---|
| 推薦頁選列 → 加入觀察清單 | `stock_code`、`stock_name`、`source='recommendation'`、notes；若有 `current_result_id`，填 `WatchlistItem.source_id`。 | **部分 result_id。** 沒有 `source_snapshot_id/hash`；`source_id` 沒有型別保證；未保存結果時為空。 `ui_qt/views/recommendation_view.py:2208-2234`、`app_module/watchlist_service.py:226-234`。 |
| DataFrame／候選池 → 觀察清單 | `source_id`，若空再取 `result_id`；另存 `stock_code`、名稱、來源。 | **部分 result_id。** snapshot 欄位在 item schema 不存在；`get_stocks()` 也不回傳 snapshot。 `ui_qt/views/watchlist_view.py:1063-1094`、`app_module/watchlist_service.py:18-31, 346-371`。 |
| 手動加入觀察清單 | `stock_code`、名稱、notes、`source='manual'`。 | **只有 stock_code。** UI 沒有 result／snapshot 欄位。 `ui_qt/views/watchlist_view.py:700-788`。 |
| market watch／strong／weak／smart money 加入 | 各入口組出的 dict 只有 code/name，service 另加來源標籤。 | **只有 stock_code。** 來源標籤不是 join key。 `ui_qt/views/strong_stocks_view.py:360-394`、`ui_qt/views/weak_stocks_view.py:342-376`、`ui_qt/views/smart_money/smart_money_flow_view.py:835-852`。 |
| RecommendationSaveCoordinator → universe 清單 | 先保存推薦 root；universe payload 是 `codes`、source、description，description 內含 `result_id` 文字。 | **不是結構化 result_id。** `UniverseService` schema 只保存 codes／描述；從 universe 載回觀察清單時只建 code/name/note。 `app_module/recommendation_save_coordinator.py:101-145`、`app_module/universe_service.py:52-99`、`ui_qt/views/watchlist_view.py:1196-1251`。 |
| 移除／清空／刪除 watchlist | 以 code 過濾後重寫 JSON payload；注入 repository 時更新單一 row，delete 物理刪除。 | **目前 active view 的 identity 消失。** repository 的 `revision` 只做 optimistic concurrency，不是歷史表；無 tombstone。 `app_module/watchlist_service.py:255-328, 429-451`、`data_module/watchlist_repository.py:31-51`。 |
| 觀察清單選取／研究下鑽／回頁 | 可從現有 row 的 `source_id` 建 `ResearchStockContextDTO`；universe 下鑽傳空 source。這是 navigation/read context。 | **不新增保存。** context DTO 有 result/source id，但沒有 source snapshot；`select_stock` 只定位 code（並在持倉頁明確丟棄 result id）。 `app_module/research_session/session_dtos.py:23-82`、`ui_qt/views/watchlist_view.py:848-1028`、`ui_qt/views/portfolio_view.py:2070-2119`。 |
| 持倉頁手動記錄交易 | UI 送 code/name、trade date、策略 combo 的 source id；未送 snapshot。`TradeDTO` 可存 source id/hash。 | **stock_code + trade_date；source_id 可能只是策略／run id。** 沒有可靠的 recommendation identity；不可用同股同日補接。 `ui_qt/views/portfolio_view.py:287-312, 2156-2184`、`app_module/dtos/portfolio_dtos.py:9-50`。 |
| 匯入 Broker CSV 至 legacy Portfolio | `TradeImportService` 以 CSV bytes SHA 建 `source_id`，同值填 `source_snapshot_hash`，另存 code／trade date／row metadata。 | **有 import-file snapshot，不是 recommendation snapshot。** 這是歷史資料匯入來源；不是 broker order，也不表示實際下單授權。 `app_module/trade_import_service.py:238-290`、`ui_qt/views/portfolio_view.py:1648-1714`。 |
| 明確注入的精確 Portfolio ledger API | `PortfolioLedgerEvent` 保存 event id、source namespace/id、source snapshot hash、thesis、code、occurred_at；append-only。 | **可 exact link，但不是目前 UI 預設 writer。** duplicate event id 拒絕；更正用新 compensation event。 `app_module/portfolio_service.py:306-413`、`data_module/portfolio_ledger_repository.py:70-177, 267-389`。 |
| 持倉頁新增 Journal | Dialog 只有 title、body、stock_code；呼叫 `JournalService.add_journal_entry()` 時只傳這三項。 | **只有 stock_code（及 created_at）。** service API 雖接受 `linked_id/source_id/source_snapshot_hash`，現有 UI 沒有提供或傳入。 `ui_qt/views/portfolio_view.py:315-365, 2186-2200`、`app_module/journal_service.py:22-57`。 |
| 直接 Journal service caller | 可保存 `linked_type/linked_id/source_type/source_id/source_snapshot_hash`。 | **只有 caller 明確傳 exact key 才可 link。** Journey 不用 stock/date fallback。 `app_module/journal_service.py:22-57`、`app_module/dtos/portfolio_dtos.py:109-145`。 |
| 刪除／清空 Journal 或 legacy Portfolio | service 讀全部資料後呼叫 `overwrite_journal_entries()`／`overwrite_trades()`；UI 明示「無法還原」。 | **破壞現行檔案中的歷史。** 沒有 revision、tombstone 或 compensation；Journey 之後只能看到刪除後剩下的 rows。 `app_module/journal_service.py:73-86`、`app_module/portfolio_service.py:207-228`、`app_module/portfolio_store.py:42-56`、`ui_qt/views/portfolio_view.py:2254-2308`。 |
| Workbench／Decision Desk／Decision Quality | Workbench 顯示 candidate result/source/snapshot；點選只加入 memory 的 viewed set。Decision Quality 可把 review item 標為 reviewed/dismissed 並寫 status history。 | **不是 V5 candidate action。** 沒有 accept/skip/next-review 的 candidate revision；Decision Quality item 只有 symbol、decision_date、source_id 等 process-review 欄位。 `ui_qt/views/workbench_view.py:1581-1592`、`ui_qt/views/workbench_view.py:1040-1108`、`app_module/decision_quality_dtos.py:84-108`、`app_module/decision_quality_repository.py:201-324`。 |
| Paper fill import | 既有 Paper Trade Ledger 具 explicit fill/source event id，並強制 `research_only=true`、broker／auto-rebalance false。 | **研究用途可分離保存；不是 actual fill。** 不可把它當正式 Portfolio 或 broker fill。 `app_module/paper_trade_ledger.py:1-8, 34-63, 131-145, 207-223`、`ui_qt/views/portfolio_view.py:1549-1616`。 |

## 4. 「同股同日」為何不能回連

以下欄位可以讓人「看起來」找到同一檔股票，但不能精確回到某次推薦：

| 現有欄位／行為 | 可能的誤讀 | 正確判定 |
|---|---|---|
| watchlist `stock_code + added_at` | 以加入日猜推薦決策日 | 沒有正式 decision date，也沒有 result key；只能標示觀察紀錄。 |
| legacy trade `stock_code + trade_date` | 以交易日回找當日推薦 | 同日可有多個 result；`DecisionOutcomeJourney` 明確不做此 join。 |
| journal `stock_code + created_at` | 以筆記時間猜當時訊號 | UI 沒有 linked/source key；只能是未連結筆記。 |
| `source`、notes、universe description | 以自由文字中的「推薦」或 result id 解析 | 不是 schema identity；不得由文字重建 key。 |
| `select_stock(stock_code, result_id)` | 以返回頁的同股列代替原候選 | 持倉頁直接 `del result_id`；只能定位同股，不能證明同一 result。 |

既有測試已鎖定此規則：同股票、同日期但不同 source 不會 join（`tests/test_decision_outcome_journey.py:352-377`）；缺 exact result root 會保留 requested key 並回 `UNKNOWN`（同檔 `:379-390`）；bounded read 未涵蓋 target 也不宣稱無關聯（同檔 `:461-489`）。因此未來 write path 遇到舊資料缺 key 時，應保存 `identity_status=unknown` 與原始 payload，不猜 result、snapshot、candidate 或 thesis。

## 5. Journal delete／overwrite 對不可變歷史的影響

現行程式有「append-only」文字描述，但實作只在新增時 append：

- `PortfolioJsonlStore.append_journal_entry()` 以 append mode 加一行；同一 adapter 的 `overwrite_journal_entries()` 卻以 `open(..., "w")` 重建整個 `journal_entries.jsonl`（`app_module/portfolio_store.py:30-56`）。
- `JournalService.delete_journal_entry()` 先移除指定 `journal_id`，再整檔覆寫；`clear_all_journals()` 直接覆寫空檔（`app_module/journal_service.py:73-86`）。
- `PortfolioService.delete_trade()`／`clear_all_data()` 對 `trades.jsonl` 有同樣問題（`app_module/portfolio_service.py:207-228`）。
- watchlist 的 JSON writer 以 temp replace 更新 active payload；SQLite adapter 只有單一 `watchlists` row，`save()` 是 upsert，`delete()` 是 physical delete（`app_module/watchlist_service.py:107-120`、`data_module/watchlist_repository.py:10-51`）。

所以刪除一篇曾經帶 exact `linked_id/source_id/source_snapshot_hash` 的筆記後，Journey 下次讀取不到該 row，無法區分「從未存在」與「曾存在後被刪除」；覆寫也會使原始 byte history、revision chain 與刪除原因不可重建。`journal_id` 本身不是歷史保存機制。這與精確 Portfolio ledger 的設計不同：ledger 只能用新 event compensation 指向既有 event，不能刪改既有 event（`data_module/portfolio_ledger_repository.py:267-389`；既有 Journey 測試 `tests/test_decision_outcome_journey.py:435-458`）。

## 6. 最小實作方案（本文件只提案，不實作）

### 6.1 共同 revision envelope

新增的邏輯記錄應沿用既有 service/store 邊界，至少具備下列欄位；欄位名稱可由父層最後核定：

```text
continuity_event_id   # retry/idempotency 的穩定 key
revision_id           # 每次 immutable revision 的 key
revision_of           # 修訂或 tombstone 指向的 exact 前一 revision；不能用 code/date
action                # accepted | skipped | note | review_scheduled | removed | cleared
entity_type/id        # watchlist item、journal、或明確的 ledger event
result_id             # 可為空，但空時 identity_status=unknown
stock_code            # candidate identity 的必要明示欄位；不可從鄰近 row 猜
source_snapshot_id    # 有就保存，無就留空
source_snapshot_hash  # 有就保存，無就留空；不可用 result_id／universe hash 代填
decision_date         # 原始決策日期；只作 context，不能取代 result_id
note                  # note action 的正文
next_review_at        # 使用者明確輸入的下次檢視時間，不由日期推導
identity_status       # linked | unknown | conflict | unlinked
created_at / actor    # 寫入時間與操作者
original_payload      # 舊 row 或輸入的保留副本
```

規則：

1. `accepted`／`skipped`／`review_scheduled` 是研究 annotation，不建立 trade，不呼叫 broker，不改正式持倉。
2. `note` 是 Journal 語意；改寫或刪除一篇筆記只能 append 新 revision／tombstone，不能用原 `journal_id` 覆寫或物理刪除。
3. watchlist item 的更新、移除、clear 以 exact `revision_of` 產生新 revision；active list 是最新 revision 的 projection，歷史仍保留。
4. 只有明確的 formal ledger trade correction 才使用既有 `reverses_event_id` compensation；不要把 accept／skip 或 journal delete 偽裝成 ledger compensation。ledger compensation 本身必須遵守既有 repository 的 exact target、scope 與 one-compensation 規則。
5. 同一 `continuity_event_id/revision_id` 重試時，完全相同 payload 應 idempotent；相同 id 但 payload 不同應回 `CONFLICT`，不能產生第二個未知狀態。
6. 缺舊 key 時保存 `identity_status=unknown`、原始 action 與原始 payload；不可由 `stock_code + date`、notes、排序或 latest result 補造 link。若 key 不同但非空，回 `conflict/unlinked` 並保留雙方值。

### 6.2 沿既有 store 的落點

| Domain | 最小落點 | 不應做的事 |
|---|---|---|
| Watchlist | 以既有 `WatchlistRepository` 所在 SQLite 為 canonical store；在**同一 DB** 增加 append-only revision/tombstone records，保留 `watchlists` current projection 與 optimistic revision。既有 JSON 檔只作相容讀取，migration 必須保留原檔，舊 row 沒 key 一律 unknown。 | 不建立 `decision_continuity.sqlite`；不把現有 `revision` 欄位宣稱成歷史表；不再以 code 去重而丟掉後來 result。 |
| Journal | 延伸既有 `PortfolioJsonlStore` 的 `journal_entries.jsonl` record contract，以 discriminated revision/tombstone line 建立 active projection；舊 entry 保持可讀。新 continuity path 禁止呼叫 `overwrite_journal_entries()`。 | 不另造 parallel DB；不在 Journey 內偷偷寫 journal；不從 free-text description 回填 result。 |
| Legacy Portfolio | 新 V5 accept/skip 不寫 legacy trade。若未來有明確 formal manual trade correction，優先走已存在的 precise `PortfolioLedgerRepository` append／compensation；legacy JSONL 舊資料不做猜測式 backfill。 | 不把 `record_trade()` 的策略 combo source id 自動當 recommendation result；不因 accept 自動下單或建立 fill。 |
| Paper fill | 依既有 `PaperTradeLedgerRepository` 的 research-only contract 保存明確 paper fill，與 formal Portfolio／broker 分離。 | 不把 paper fill 宣稱成 actual fill、personal PnL 或 broker confirmation。 |
| Journey | 增加的只是 future read adapter／normalizer，沿用目前 exact-key、unknown、conflict、query-boundary 規則；Journey 本身仍唯讀。 | 不讓 `DecisionOutcomeJourneyService` 變 writer；不由它反向補建缺漏 identity。 |

注意：目前桌面 `MainWindow` 以 `WatchlistService(config)` 與 `PortfolioService(config)` 啟動，沒有注入 `WatchlistRepository` 或 precise ledger（`ui_qt/main.py:248-253`）。因此父層若核准方案，第一個 writer slice 必須先明確決定既有 store 的 canonical writer／相容 migration；在此之前不能宣稱現有 UI 已具備不可變 continuity。

## 7. 現有授權範圍與延後範圍

### 依既有研究授權可做（後續另需父層下實作指令）

- 以 exact `result_id`、`stock_code`、可用的 snapshot id/hash 建立 watchlist research annotation。
- 保存 `accepted`、`skipped`、`note`、明確 `next_review_at`，只做研究／人工覆盤狀態，不代表交易意圖已執行。
- 讀取與展示 `DecisionOutcomeJourney`、source trace、maturity 與 unknown/conflict diagnostics。
- 使用既有 Paper Trade Ledger 做明確 research-only fill evidence；其 `research_only=true`、`broker_order_allowed=false`、`auto_rebalance_allowed=false` 是硬邊界。
- 使用既有 Decision Quality 的 reviewed/dismissed status history 作 process review；不把它映射成 V5 candidate accept/skip。

### 延後，不能由 V5 action 自動觸發

- broker API、下單、取消單、actual fill ingestion、broker confirmation、滑價／流動性歸因。
- accept → formal Portfolio trade promotion、auto rebalance、正式持倉變更。
- 以日期／股票／latest result 回填舊交易、journal 或 watchlist identity。
- 將 Paper fill、research forward return 或 source-declared PnL 解讀成個人實際成交／個人績效。

`PortfolioService.record_precise_trade()` 是明確的 formal ledger write API，不是 broker API；它只有在 caller 明確提供 event/source identity 且注入 repository 時才應另案審查。它不能被 V5 的 accept action 隱式呼叫。

## 8. 建議測試與驗收證據

本輪不新增測試、不寫 fixture、不重跑大套件。下列是父層核准 write path 後的 focused QA：

| 測試面 | 建議案例與必驗斷言 | 建議檔案／入口 |
|---|---|---|
| Identity capture | 推薦 result + candidate 加入 watchlist 後，round-trip 保留 exact `result_id`、`stock_code`、snapshot id/hash；沒有 snapshot 時保持空值／明示 missing，不用 result id 代填。 | 新增 `tests/test_decision_continuity_write_path.py`；回歸 `tests/test_decision_outcome_journey.py:252-325`、`:352-390`。 |
| Unknown／conflict | 缺 result／舊 row 缺 source key → `unknown`；不同 result 同股同日維持兩條獨立 chain；不接受 notes、date、排序猜測；不一致 key → conflict。 | 新測試；回歸 `tests/test_decision_outcome_journey.py:352-377, 425-431, 461-489`。 |
| Revision chain | accept → note → review_scheduled → skip／correct 的每一步都有新 `revision_id` 與 exact `revision_of`；active projection 只有 head，raw history 全在。 | 新測試；Watchlist repository contract 可參考 `tests/test_task_loop_07_contract.py:238-267`。 |
| Tombstone／clear | remove／clear／journal delete 只新增 tombstone；active list 排除 target，但歷史查詢仍看得到原 entry、actor、reason、identity。不得呼叫 `overwrite_*`。 | 新測試；回歸 `tests/test_portfolio_delete.py`、`tests/test_portfolio_jsonl_store_serialization.py`。 |
| Idempotency／concurrency | 相同 event/revision 重試不重複；同 id 不同 payload → conflict；watchlist optimistic revision race fail closed；跨 process 不丟 revision。 | 新測試；`data_module/watchlist_repository.py:31-41`、ledger append duplicate checks。 |
| Journal exact link | UI future action 傳 `linked_id/source_id/source_snapshot_hash` 時 Journey 可 exact link；只傳 stock/date 時為 unknown/unlinked，不回連。 | 新測試；`tests/test_decision_outcome_journey.py:435-458, 597-638`。 |
| Formal ledger boundary | trade event 可 append；補償只能 exact `reverses_event_id` 且不改原 event；Journey 只讀；accept／skip 不產生 ledger event。 | `tests/test_formal_portfolio_ledger.py`、`tests/test_decision_outcome_journey.py:435-458`。 |
| Paper／broker boundary | paper fill round-trip 保持 research-only flags；V5 action 不呼叫 broker／不修改 formal Portfolio。 | `tests/test_paper_trade_ledger.py`、`ui_qt/views/portfolio_view.py:1549-1616` 的 UI boundary tests。 |
| UI round-trip（第二增量後） | 從推薦／觀察清單／持倉返回時保留 result identity；Portfolio 不再丟棄 result id；unknown 狀態可見；next review 不被目前時間覆寫。 | `tests/test_ui_qt_watchlist_layout.py`、`tests/test_ui_qt_portfolio_view.py`、`tests/test_ui_qt_decision_outcome_journey.py`、`tests/test_watchlist_stock_analysis_navigation.py`。 |

## 9. 最多兩個可獨立交付增量與 owner 邊界

### Increment A — Decision continuity storage contract

**Owner：** app/data persistence owner。
**交付：** 核定 identity envelope、unknown/conflict 規則、WatchlistRepository 同 DB revision/tombstone、PortfolioJsonlStore journal append-only revision projection、idempotency／concurrency tests；保留既有資料，無猜測式 backfill。既有 precise ledger 僅沿用 exact append／compensation，不把研究 action 寫成 trade。
**不包含：** Qt widget、按鈕、broker、actual fill、auto rebalance、正式 Portfolio promotion。
**完成 gate：** raw history 可回放；刪除／clear 不再抹除歷史；同股同日不會誤接；缺 key 明確為 unknown；Journey read adapter 的 linked／unknown／conflict regression 全綠。

### Increment B — Thin UI continuity integration

**Owner：** UI／workflow integration owner。
**交付：** 從 Recommendation／ResearchStockContextDTO／Watchlist／Portfolio 將明確 result id、stock code、可用 snapshot 傳入 A 的 API；加入研究用 accept／skip／note／next-review 操作與 unknown/conflict 顯示；返回頁保留 exact context。
**不包含：** 新 DB、core scoring、推薦重算、交易、broker、actual fill 或任何「accept 即下單」語意。
**完成 gate：** UI round-trip 與 A 的 persisted payload 一致；manual／universe 缺 key 不猜；Decision Desk／Workbench 仍唯讀；Portfolio／Journal destructive legacy action 不被 V5 path 誤用。

父層審查前，本文件不執行上述任何 write path。核准後仍應先交付 A，再由 B 接線；broker／actualfill 維持獨立延後 gate。

## 10. 精確檔案入口索引

- Journey contract／read-only adapters：`app_module/decision_outcome_journey.py:1-17, 101-174, 530-637, 670-825, 848-1002, 1259-1299, 1625-1805, 2069-2272, 2356-2565`。
- Existing Journey QA：`docs/06_qa/DECISION_OUTCOME_JOURNEY_2026_09_14.md:31-41, 74, 165-187`。
- Watchlist model/service／mutable operations：`app_module/watchlist_service.py:18-31, 57-120, 160-245, 255-328, 346-371, 429-451`。
- Watchlist SQLite copy／revision limitation：`data_module/watchlist_repository.py:10-51`。
- Recommendation／universe callers：`ui_qt/views/recommendation_view.py:2208-2234`、`ui_qt/views/watchlist_view.py:555-637, 700-824, 848-1028, 1063-1094, 1145-1251`、`app_module/recommendation_save_coordinator.py:101-145`、`app_module/universe_service.py:52-99`。
- Portfolio／Journal service and stores：`app_module/portfolio_service.py:38-145, 207-228, 306-413`、`app_module/journal_service.py:15-86`、`app_module/portfolio_store.py:21-78`、`app_module/dtos/portfolio_dtos.py:9-145`。
- Portfolio UI writers／destructive actions／navigation：`ui_qt/views/portfolio_view.py:287-365, 1549-1714, 1906-2032, 2070-2308`；default wiring `ui_qt/main.py:248-253`。
- Precise and paper ledger boundaries：`data_module/portfolio_ledger_repository.py:70-177, 223-389, 508-535`、`app_module/paper_trade_ledger.py:1-8, 34-63, 131-145, 207-223`。
- Process review distinction：`app_module/decision_quality_dtos.py:84-108`、`app_module/decision_quality_repository.py:41-105, 201-324`、`ui_qt/views/decision_quality_view.py:37-48, 150-260`。
- Focused regression tests：`tests/test_decision_outcome_journey.py`、`tests/test_task_loop_07_contract.py`、`tests/test_portfolio_delete.py`、`tests/test_portfolio_jsonl_store_serialization.py`、`tests/test_formal_portfolio_ledger.py`、`tests/test_paper_trade_ledger.py`、`tests/test_decision_quality_repository.py`、`tests/test_watchlist_stock_analysis_navigation.py`、`tests/test_ui_qt_watchlist_layout.py`、`tests/test_ui_qt_portfolio_view.py`。

**交付聲明：** 本輪只新增本 QA 規劃文件；沒有執行資料寫入、交易、broker 呼叫或實作任何 decision continuity write path。

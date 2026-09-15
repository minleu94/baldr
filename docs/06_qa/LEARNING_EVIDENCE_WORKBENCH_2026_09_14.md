# Learning Evidence Workbench QA 紀錄（2026-09-14）

## 結論

本輪已完成一個可審查的唯讀增量：Workbench／Research Console 會以 typed candidate、active、prediction-capture verifier 的 projection 顯示 learning evidence、成本 lane、日期 freshness、horizon scope、樣本與下一個缺口。工程驗證通過；這不是 promotion、正式推薦或交易授權。

目前實際資料仍未形成可授予 natural evidence credit 的成熟樣本：臺銀 lane 等待後續自然 forward capture，legacy lane 的既有 candidate 則因來源追溯衝突而 blocked。UI 因此保留 pending／blocked／unknown，不以 replay、fixture 或缺 receipt 的 capture 補值。

## 範圍與安全邊界

- 入口：`app_module/recommendation_learning_evidence_projection_service.py`、`app_module/workbench_source_service.py`、`ui_qt/views/workbench_view.py`、`ui_qt/views/research_console_view.py`、`ui_qt/main.py`。
- authority boundary：`ml_module/recommendation_calibration_authority.py` 的 `verify_natural_evidence_read_only` 與 `ml_module/recommendation_calibration_evidence.py` 的 `verify_prediction_capture_read_only`；兩者只讀、只驗證，不寫 receipt／pointer、不 promotion、不改正式 Recommendation／Portfolio、不下 broker order。
- candidate／active／capture 與 cost scenario 必須同 lane、同 candidate／model identity、同決策日及同 source contract；horizon 統計只取單一選定 lane，不能跨 candidate／active 或跨成本情境合併。
- Workbench 的 dashboard decision date 會傳入 Research Console；未明示日期時只接受可信的臺灣官方交易日 resolver。日曆不可用或日期不明時顯示 `unknown`，不以 learning receipt 的最新日期冒充今日。

## Increment B：研究操作、append-only 紀錄、跨頁讀回與自然 evidence

Increment B 的邊界是「把明示的 recommendation／stock／snapshot identity 帶入研究操作，
並能在頁面往返後讀回同一條 continuity」；它不等於 V4 formal maturity，也不把只讀
learning projection 當成 user decision。依目前 A／D 增量，狀態如下：

| 面向 | 目前已完成／可核對增量 | 仍缺的 B gate |
|---|---|---|
| 研究操作 | 個股研究報告已能以 `ResearchStockContextDTO.result_id` 開啟唯讀 Decision → Outcome Journey；Workbench → Research Console 也已綁定明確決策日與成本 lane。畫面沒有 Apply、Trade 或 implicit accept。 | B 的 accept／skip／note／next-review 操作尚未完整接到每個研究入口；不能因畫面可讀就產生 user decision。 |
| append-only 紀錄 | Increment A 已提供 `DecisionIdentity`、候選池 revision／tombstone、研究 journal revision、idempotency／optimistic-concurrency 與 unknown／conflict 契約；歷史資料不靠猜測 backfill。 | B caller 仍需在每個明確操作傳入 exact result／stock／snapshot identity，並將操作寫入 A API；不得以 stock／date／排序補 key，也不得把操作轉成 trade／broker event。 |
| 跨頁讀回 | Journey read model 以 exact result／candidate／event identity 分開讀回 Evidence、outcome、Journal、精確 Portfolio ledger 與 legacy trades；5／10／20／60 horizon 的 linked／maturity 狀態可見，研究 return 與個人交易分離。 | Recommendation → Research → Watchlist／Portfolio → Workbench 的完整 B round-trip、返回後 exact context、review history head 與 UI action result 尚未由同一條 production workflow 全部驗收。 |
| natural evidence | 本輪 typed candidate／active／capture verifier 與 BankTaiwan／legacy projection 已完成；Research Console 會保留 pending／blocked／unknown，真實 BankTaiwan lane 仍無 matching current capture，legacy lane 仍 provenance blocked。 | 自然 forward capture、後續成熟 outcome、同 candidate／同成本／同 source custody 的有效 receipt 仍須由真實時間累積；UI／append-only decision 不會增加 natural sample，也不解除 formal／promotion gate。 |

因此 B 目前是「A persistence contract + D read-only journey + 本輪 learning read model」的
分段完成狀態；尚未宣稱 B 的完整操作 round-trip，更未宣稱 V4 formal／投資有效性完成。

## 實際資料唯讀觀察

| lane | learning root | 最新觀察 | 判讀 |
|---|---|---|---|
| 臺銀公開成本研究（預設） | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning` | candidate `rec-cal-b48b793f35280ce0ff9d5109`；`cost_scenario_id=banktaiwan-electronic-estimate`；`retain_current`／`natural_forward_evidence_receipt_missing`；active pointer 為 none | `pending`；沒有 matching current capture，natural matured sample 為 0。估算成本維持 `estimated_research_only`。 |
| Legacy 固定 50bp（獨立 lane） | `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning` | candidate `rec-cal-29c1b6129396a3885a89d080`；既有 status 含 `cross-capture feature/source conflict: 1528`；`retain_current` | `blocked_provenance`；不與臺銀 lane fallback 或混算。 |

上述路徑、candidate、receipt 與 pointer 均為現有 shadow output 的 query-only readback；本輪沒有執行 producer、pipeline、scheduler 或資料重建。

## QA case map

| case | 覆蓋內容 | 結果 |
|---|---|---|
| authority receipt race | verifier 完成後 receipt bytes 被替換 | 通過；回報 `natural_evidence_receipt_changed_after_verification`，不標記 verified。 |
| cost scope | candidate／active 與選定 lane 的 scenario 不一致 | 通過；`blocked_cost_scope`，不跨 lane fallback。 |
| failure branch | candidate verifier 失敗且仍有 capture | 通過；保留 typed blocked diagnostics，未再觸發 duplicate-keyword failure。 |
| capture provenance | 缺日期、改 rows、historical origin、錯成本、有效 pending capture | 通過；分別維持 blocked／unknown／pending／recorded 語意。 |
| freshness | explicit stale、future、stale capture、週末 official-session contract、resolver unknown | 通過；只使用目標決策日；未知時不推斷 current。 |
| horizon scope | candidate 20 samples／2 dates 與 active 10 samples／10 dates | 通過；不產生合成的 20／10 統計，兩個 lane 各自保留 scope。 |
| UI date binding | Workbench dashboard date → Research Console projection | 通過；Research Console 收到明確的 `2026-09-14`／切換後 `2026-09-01`。 |

聚焦測試指令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_learning_evidence_projection.py tests\test_ui_qt_research_console_view.py tests\test_ui_qt_workbench_view.py tests\test_daily_investment_journey.py tests\test_workbench_source_service.py -q -o addopts=
```

結果：`72 passed, 1 warning`。唯一 warning 是 pytest cache 目錄的既有 permission warning，不是測試失敗。

另外，指定 9 個 changed source files 的 mypy 為 `Success: no issues found`；本輪 changed Python files 的 `py_compile` 通過。依根 AGENTS 強制清單重跑的全域指定 mypy（`ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`）目前為 `Success: no issues found in 611 source files`。

## Qt 實際渲染與 MainWindow smoke

已使用實際 PySide6 widget／production view 組裝，在 offscreen Qt 環境套用 `MIDNIGHT_ANALYST`、`Microsoft JhengHei`，綁定 `decision_date=2026-09-14`，切換臺銀與 legacy selector、滾動至每日學習區塊並目視檢查 PNG。這是「離屏實際 Qt 渲染」，不是 controlled DTO screenshot，也不是 native desktop mouse／screenreader 測試。

manifest：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\learning_projection_qt_20260914\manifest.json`

- manifest `status=passed`、`evidence_kind=offscreen_actual_qt_render`、`read_only=true`、無 Apply／Trade controls。
- 臺銀 PNG 顯示 default lane、`pending`、`not_recorded`、`natural_forward_evidence_receipt_missing` 與尚無 verified natural sample。
- legacy PNG 顯示獨立 `legacy_fixed_bp` lane、`blocked_provenance` 與 cross-capture conflict；沒有把 legacy 結果當臺銀 fallback。
- PNG：`research_console_banktaiwan_default.png`、`research_console_legacy_fixed_bp.png`，位於上述目錄。

另執行實際 `MainWindow` offscreen keyboard／geometry smoke：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\mainwindow_smoke_20260914\summary.json`

結果為 `status=passed`、scale 1.0、1366×768、market/runtime Space navigation、600-row PageDown/Home 與 recommendation／portfolio embedded pages 通過。native CUA surface 在本機不可用，因此 `native_windows_interaction`／screenreader 不宣稱已測。

先前共享工作區曾因 `app_module.portfolio_store`／`app_module.journal_service` in-flight 缺檔
而阻擋 import；A／D public modules 恢復後，該 blocker 已 resolved。最新 MainWindow
offscreen smoke 已重新通過，`summary.json` 為目前可引用的成功 artifact。

## 根 AGENTS 強制驗證補充

- `pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=`：D 線最新驗證 `81 passed`。
- `scripts\qa_validate_update_tab.py`：D 線最新驗證 `25 pass、0 fail、4 skip`。
- MainWindow offscreen validator：本次恢復後重跑 `status=passed`；scale 1.0、1366×768、keyboard navigation、600-row table 與 embedded recommendation／portfolio pages 均通過。
- 全域 mypy：本次實際輸出 `Success: no issues found in 612 source files`。
- 歷史缺檔 blocker 已標記 resolved；本線 learning focused run 仍保留 `72 passed, 1 warning`、Research Console `16 passed, 1 warning` 與最新 learning PNG 的自身邊界證據。

## 尚未解除的產品 Gate

本輪沒有真實 natural matured sample、正式 promotion package、Advice adoption、正式 Recommendation／Portfolio 變更或 broker action。learning 的下一個 gate 只需由既有自然 forward 流程累積同 candidate／同成本／同 source custody 的成熟 receipt；Workbench 在此之前維持研究／等待／阻擋狀態。observed broker fill／slippage 與 formal promotion 是延期中的 execution／formal gate，不是每日 shadow learning 或本輪 UI 驗收的必要前置。

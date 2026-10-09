# 6M Roadmap Gate 3／4 歷史狀態（2026-08-26 至 08-28）

> 本文保存當時的工程觀測與 QA 數字，不代表目前 Gate 狀態或目前優先序；目前狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準，Gate 定義以 [6M Engineering Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md) 為準。

<a id="gate3-20260826"></a>
## Gate 3：2026-08-26 Data Source Control Center read model

2026-08-26 已先落地 `app_module/p0_source_control_center.py` 與 `scripts/inspect_p0_source_control_center.py` 的 13-source 唯讀 composition；它只投影 contract／audit／decision evidence，沒有 auto-accept 或 downstream grant，後續仍需逐來源補齊真實 evidence。

<a id="gate4-20260827-28"></a>
## Gate 4：2026-08-27 至 08-28 Portfolio／Paper 工程觀測

2026-08-27 進度：Portfolio UI 已接上最小唯讀 Scenario & Stress Lab v1、受控手動 Trade Import、Paper Portfolio readiness、Paper weekly evidence read model 與獨立 Paper Trade Ledger v1 contract；另有預覽／明確確認分離的 `append_paper_trade_ledger.py` JSON producer、完整 execution contract 的 `append_paper_trade_csv.py`／UI Paper fills 匯入，以及從 baseline／既有 snapshots／T-1 市場資料建立 frozen-constituent Equal Weight preview 的 `build_paper_equal_weight_benchmark.py`。正式輸出重新檢查到 21 筆 raw paper snapshots，其中最新 `2026-08-28` 超過台北今日 `2026-08-27`；readiness 會將狀態降為 `degraded` 並把 future row 排除於 current projection，weekly evidence 與 Equal Weight builder 遇到 future period／snapshot 則 fail-closed。Equal Weight ledger／Paper Trade Ledger 尚未配置，故 weekly evidence 仍 `not_computable`；固定情境缺價只顯示 partial，輪動失敗／來源中斷維持 `not_computable`。本輪再加入 Stress history v1：明確確認後才可保存 hash-idempotent 研究快照，Portfolio UI 與 `append_portfolio_stress_history.py` 均提供唯讀歷史揭露。這些是可見的工程入口，不代表 Gate 4 的 OOS / forward / paper 成本後 evidence 已完成；producer 的實際來源資料、成本 fill、壓力結果與 forward outcome 關聯及 review 仍待後續輸入。

2026-08-28 進度：Equal Weight builder 已抽至 `app_module/paper_equal_weight_benchmark_builder.py`，CLI 與 Portfolio UI 共用 preview／確認／輸入重驗證／新檔拒絕覆寫流程；Paper readiness／weekly evidence 預設讀取 `<OUTPUT_ROOT>/paper_portfolio/paper_equal_weight_benchmark.sqlite`（仍可由 `PAPER_EQUAL_WEIGHT_BENCHMARK_PATH` 覆寫）。Portfolio UI 新增「預覽／建立 Equal Weight」入口，建立後只補 benchmark observation；Paper Trade Ledger、真實 fill／partial-fill／reject／override、成本與 execution gap 仍不可由 snapshot 或手動交易推導。

- 2026-08-28 進度：新增 `scripts/inspect_paper_trade_reconciliation.py` 的 query-only fills preflight；外部 CSV 先通過完整 execution contract，再以期初／期末 snapshot 逐股票核對 filled quantity delta，並檢查既有 ledger fill-id collision。缺 context 或對帳不符會停在 `needs_review`／`rejected`，只有 `ready` 才能交給既有明確 confirm append；此工具不從 snapshot 猜成交、不建立或修改 ledger。

2026-08-28 台北日期刷新：`taiwan_market_today()` 已進入 `2026-08-28`，上述 raw snapshot 不再是 future row；Paper readiness 目前為 `partial`。已在 QA output 以 3 檔 frozen constituents 產生 21 筆 Equal Weight staging preview（最新 `472302.39`），並於受控確認後建立正式 Paper output ledger `<OUTPUT_ROOT>/paper_portfolio/paper_equal_weight_benchmark.sqlite`；真正缺口縮小為 Paper Trade Ledger 與可計算的成本後週報／forward outcome。future-date guard 仍保留，下一筆超過台北市場日的資料仍必須 fail-closed。

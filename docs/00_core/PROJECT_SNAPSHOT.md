# PROJECT_SNAPSHOT（目前狀態）

> **更新基線：2026-10-12。** 本頁只記目前可支持的整體狀態；局部 PASS 不相加成完整工作包或產品 Gate。最新恢復收據見 [10/12 補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)，先前紀錄見 [BALDR_COMPLETION_PROGRESS_20261011](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md)；原始 receipts／source inventory 依各收據所列路徑與 SHA 追溯。

## 現在有哪些入口

baldr 已有九個本機工作區，主程式是 `ui_qt/main.py`。下表說明可以從哪裡開始研究，並非所有來源、候選版本或投資效果均已驗收。

| 你的需求 | 已有產品入口 | 使用時的限制 |
|---|---|---|
| 整理行情、確認資料日期 | 數據更新與資料狀態檢查 | 使用自己的合法來源；缺庫、缺表、日期落後分開判讀 |
| 了解市場與個股 | 市場探索、個股研究 | 原始排名、來源與品質各自保留，unknown 不能當零 |
| 比較候選與策略 | 推薦分析、策略回測／Research Lab | 歷史研究與 Paper 不代表正式投資有效或可交易 |
| 保存名單與檢查持倉 | 觀察清單、持倉管理 | 真帳、聲明持倉、研究 Paper 帳分開，保存重開依精確來源判讀 |
| 找日常重點或排查系統 | 決策工作台、系統狀態 | 顯示與導航不授自動交易、模型 promotion 或資料 writer 權限 |

第一次使用依[快速開始](../07_guides/QUICK_START.md)；換電腦依[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。新版完整產品包尚有以下工程驗收事項，已交付舊包與當前候選不能混用資格。

## 目前工程狀態與限制

產品補完範圍仍為 P00–P14、M1–M3、F01–F23、UX01–UX24、G0–G4，工作持續中；沒有因單項 QA 通過而宣告整包或 Gate 完成。近期接手背景與資源約束見[2026-10-12 恢復交接](../agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md)。

使用者於本輪接續工作後要求暫停並保存 commit；補完 goal 已 paused，沒有 active QA／subagent。P01 r04 新 origin／fresh 通過，唯一 warm 診斷已自然完成90份取樣；Root獨立完整artifact核對與熱點分析尚待，原三p95FAIL／Main／Qt types／完整Gate不變。接手依[本輪暫停停點](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md#使用者要求暫停與-commit停點)，只有使用者要求恢復才繼續。

| 主題 | 最新可支持的狀態 | 判讀依據 |
|---|---|---|
| P08 保存結果旅程 | 指定凍結候選版完整旅程 5 PASS／native 0。該證據只適用於指定合成來源與候選版本，不授予最新 formal 修補版本、正式來源資格、完整 P08 或產品 Gate 接受。 | [補完進度與最新收據](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md) |
| P01 Main | 單次原生觀測仍為access violation／完整來源守衛終態FAIL，pins／mirror穩定。唯一348,191bytes dump經exact DLL／PDB及136bytes有界unwind，確認捕獲fault在faulthandler watchdog路徑；保存frame參數地址等於False singleton，fault為NULL code欄位讀取。指標形成與初始／次生因果仍未知；不授Main接受。 | [10/12 補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md) |
| P01 矩陣 | M27完整五cold＋一warm已自然返回，90份完整DTO相等；Root重算翻頁327.8650／篩選444.9752／排序934.8569ms，三類皆未達原嚴格低於300ms門檻。不接受P01／Gate。 | 同上 |
| M25／M26／M27 | M26六phase聚焦案例已有同helper證據；M27已經Root完整raw／AST／3497pins／18compile／382closure、純預檢及actual origin核對。完整矩陣完成診斷仍效能FAIL，來源版本明示保留舊SHA，不授最新版formal接受。 | 同上 |
| Health／ML長路徑 | Health11path＋fixture及ML6來源＋helper／test精確採入；r03修正lineage暫存leaf263，新3085來源／17formal origin通過。新版ML159、incremental104、callers329PASS／2SKIP、UI85、governance51、validator與syntax20通過。原長路徑18案例16PASS／2FAIL收據保留；使用者授權一次UAC後，原兩項no-follow另組2PASS／0SKIP，來源及原守衛通過，沒有改永久權限設定。Qt保存raw九份完整欄位相等僅資料診斷，原types守衛FAIL保持；新同版Health正常／freshMain1PASS，P01完整Main與工作包／完整Gate仍待。 | 同上 |

上述工作依賴目前一次一組受控驗證與來源封套規則；未封存、未經審查的候選不能當成可執行驗收來源。產品目前優先事項不換算為 6M Month N，工程 Gate 順序見 [ROADMAP_6M_ENGINEERING](ROADMAP_6M_ENGINEERING.md)。

## 產品與系統入口

- **產品方向與來源優先序**：[PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md)。產品 Gate 定義產品能力與接受證據，不是完成狀態。
- **目前架構**：[system_architecture](../01_architecture/system_architecture.md)及[目前架構分冊](../01_architecture/current/README.md)。
- **目標架構設計**：[FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標實作設計唯一權威，不作 current 完成證明。
- **UI**：主程式為 `ui_qt/main.py`，共有九個頂層工作區；Daily Decision Desk 位於「市場探索 > 市場總覽」。完整操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **正式資料路徑**：由 `data_module/config.py` 的 `TWStockConfig` 管理；`DATA_ROOT` 預設 `D:/Min/Python/Project/FA_Data`，SQLite 主要檔為 `<DATA_ROOT>/sqlite/twstock.db`。不得依 repo 相對目錄推定正式資料位置。

## 重要限制

- 不覆寫或刪除正式 raw data；所有來源候選、PIT、時間戳與 gate 原門檻照原收據判讀。
- 金融核心使用 Decimal 或整數單位；策略、回測、Recommendation、Portfolio 與 Exit 實作須先做 look-ahead 自查。
- Historical replay、readiness、dry-run、shadow、paper 與局部 UI／後端 PASS 不代表 forward／live evidence 或產品接受。
- Investment Advice 不授權 broker execution、自動平倉或自動策略升降級。

歷史快照與逐輪驗收原文已由文件治理封存在 [documentation_productization_20261012/originals](../09_archive/documentation_productization_20261012/originals/)；封存版本只供追溯，不能覆蓋本頁或最新具名 QA 收據。

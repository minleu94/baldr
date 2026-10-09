# 文檔結構與維護規則

> **最後更新**：2026-10-08
> **用途**：定義 `docs/` 內每個資料夾的歸屬、文件生命週期、刪除/歸檔規則。

> **2026-10-06 維護補充**：[全文件目錄歷史快照](../09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md)涵蓋 tracked root／docs／module 說明；[整理 manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md)保存全文封存與原 bytes 恢復。ignored 的 plan／QA 不等同 cache；唯一需求先核 byte backup，失敗 raw 不改寫。資料保留看[資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)，graph 更新看[維護入口](DOCUMENTATION_GRAPH_GUIDE.md)。

---

## 一、權威文件層級

1. **產品願景與原則**
   - `docs/01_architecture/system_vision_specification.md`
   - 定義 North Star、產品原則、Evidence、成功標準與 Non-goals；不保存工程執行狀態。

2. **目前狀態入口**
   - `docs/00_core/PROJECT_SNAPSHOT.md`
   - 定義目前狀態、工作模式、本週優先事項與高風險區。

3. **產品方向**
   - `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`
   - 定義產品問題、產品能力、成熟度與非目標；不保存目前完成度或工程排程。

4. **6 個月工程路線**
   - `docs/00_core/ROADMAP_6M_ENGINEERING.md`
   - 定義相對月份、工程 Gate、依賴、交付物與驗收標準；當前進度以 Snapshot 為準。

5. **Roadmap Hub**
   - `docs/00_core/DEVELOPMENT_ROADMAP.md`
   - 只提供系統定位與權威文件入口，不複製 Next、進度、風險或完整歷史。

6. **長期版本成熟度階梯**
   - `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md`
   - 定義 V2.1-V4.0 的產品成熟度標準；與 6M 工程 Gate 對照能力，不代表一對一的工程順序。

7. **外部參考與歷史版本形狀**
   - `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`
   - 保存外部專案參考、資料源候選、歷史版本形狀與 deferred 技術邊界；不定義目前交付順序。

8. **舊 Roadmap 移交記錄**
   - `docs/00_core/LEGACY_ROADMAP_CARRYOVER.md`
   - 保存舊項目的唯一處置與移交證據；目前月份與工程順序以 6M Roadmap 為準。

9. **目前操作手冊**
   - `docs/07_guides/APPLICATION_MANUAL.md`
   - 保存目前工作區的完整操作、結果判讀、安全限制與排錯方式。

10. **架構權威**
   - `docs/01_architecture/system_architecture.md`
   - 定義目前架構、模組邊界、資料流與高風險技術邊界。

11. **索引與維護規則**
   - `docs/00_core/DOCUMENTATION_INDEX.md`
   - `docs/00_core/DOC_COVERAGE_MAP.md`
   - `docs/00_core/DOCUMENTATION_STRUCTURE.md`

12. **專項文件**
   - 架構、功能、資料、Phase、QA、指南、技術、Agent、策略文件。

13. **Archive**
   - `docs/09_archive/`
   - 僅作歷史追溯，不作目前狀態依據。

---

## 二、資料夾歸屬

| 目錄 | 放什麼 | 不放什麼 |
|---|---|---|
| `00_core/` | Snapshot、產品方向、6 個月工程路線、Roadmap Hub、版本成熟度、外部參考、舊項目移交、索引與文件治理規則 | 完整歷史 Done、單一功能的長篇操作教學 |
| `01_architecture/` | 架構、資料流、依賴邊界、Runtime 規範 | 一次性 QA 記錄 |
| `02_features/` | 使用者可見功能、UI、策略、回測、評分說明 | Phase 規劃草案 |
| `03_data/` | 資料更新、資料流、資料重建、資料故障排除 | 券商分點專屬細節 |
| `04_broker_branch/` | 券商分點資料、分點解析、籌碼資料更新 | 一般每日資料更新 |
| `05_phases/` | 歷史 Phase 設計、Phase 3.5 SOP、Phase 4 設計追溯 | 目前 roadmap、目前完成狀態、日常操作指南 |
| `06_qa/` | QA 問題、總結、驗證、審核報告 | 長期架構設計 |
| `07_guides/` | 快速開始、安裝、腳本、測試操作 | 系統權威狀態 |
| `08_technical/` | 技術優化、環境、參數設計備忘 | 使用者導向流程 |
| `09_archive/` | 歷史總結、已執行提案、舊調查、舊完整 Roadmap | 仍需日常引用的文件 |
| `agents/` | Agent 職責、協作規範、上下文 | 一般使用者指南 |
| `governance/` | 流程治理、決策紀錄、政策文件；目前為預留目錄 | 功能教學或一次性 QA |
| `strategies/` | 策略說明與 Why | 策略程式碼或測試 |
| `superpowers/` | Superpowers specs / plans、設計追溯與 execution artifacts | 目前 roadmap、目前狀態、raw output 或正式 QA closeout |

---

## 三、文件生命週期

### Active

日常使用、開發或決策會引用的文件。Active 文件必須：

- 出現在 `DOCUMENTATION_INDEX.md`
- 相對連結有效
- 狀態描述不與對應 scoped authority 衝突

### Historical

仍有追溯價值，但不應作為目前狀態依據。Historical 文件應放入 `09_archive/`，並在 README 中明確標註。

適合歸檔的內容：

- 舊線性 Phase 的完整 Done 與 Exit Criteria。
- 已執行完畢的 Next Action Plan。
- 舊 Roadmap current section。
- 過期但仍有決策脈絡價值的調查或提案。

### Delete

符合以下所有條件即可刪除：

- 沒有被 Active 文件引用
- 沒有保留歷史脈絡的必要
- 內容已被更新、更完整的文件取代
- 文件本身是一次性 debug log、patch note、單日執行指南或過期草稿

---

## 四、目前已確認的整理決策

- `PROJECT_SNAPSHOT.md`、`PRODUCT_ROADMAP_POST_REFACTOR.md`、`ROADMAP_6M_ENGINEERING.md`、`DEVELOPMENT_ROADMAP.md`、`VERSION_ROADMAP_V2_1_TO_V4_0.md`、`EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`、`LEGACY_ROADMAP_CARRYOVER.md` 與 `DOCUMENTATION_INDEX.md` 保持為核心入口。
- `system_vision_specification.md` 定義產品願景與原則；`PRODUCT_ROADMAP_POST_REFACTOR.md` 定義產品方向；`ROADMAP_6M_ENGINEERING.md` 定義工程順序與驗收；`PROJECT_SNAPSHOT.md` 定義目前狀態。
- `DEVELOPMENT_ROADMAP.md` 是純導覽 Hub，只連結權威文件，不複製 Next、進度或風險摘要，也不保存完整歷史。
- 版本成熟度階梯描述產品能力與證據成熟度，不等同 6M Roadmap 的工程 Gate 順序。
- 舊完整 Roadmap 已歸檔為 `docs/09_archive/DEVELOPMENT_ROADMAP_LEGACY_2026_06.md`。
- `PROJECT_NAVIGATION.md`、`PROJECT_INVENTORY.md` 位於 repo 根目錄，仍屬專案級導航文件；索引需用正確相對路徑指向它們。
- 根目錄 `README.md` 保持使用者導向，說明專案目的、啟動方式與乾淨 `main` 使用方式；Agent / 開發者上下文放在 `AGENT_CONTEXT.md`。
- `ui_qt/README.md` 不屬於 `docs/`，但若 `docs` 索引引用它，需標註它可能落後於 roadmap。
- `09_archive/` 保留歷史文件，但 Active 文件不應依賴 archive 內容判斷目前狀態。
- `output/`、`output/qa/` 與根目錄臨時資料樣本屬於本機執行產物，不應作為 Active 文件或乾淨 `main` 內容；需要保存結論時整理為 `docs/06_qa/` 摘要。
- 一次性 QA debug／patch 收據先做生命週期與引用核對；有追溯價值者歸檔並保留原路徑轉址，不因為是一次性就刪除證據。只有確認屬本機臨時輸出、且不是原始資料或正式 QA 證據的產物，才可清理。
- `docs/05_phases/` 保留歷史目錄 README 與舊路徑轉址；13 份 Phase／SOP 原文已依原層次移至 `docs/09_archive/`，舊引用可經轉址開啟原文。目前核實到的 Active 直接引用只有 `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` 指向 `PHASE2_ARCHITECTURE.md`。歸檔內容中的「下一步」「進行中」「Phase Gate」不代表目前 roadmap。
- `docs/06_qa/` 保存日期化驗證與調查證據；已結束的收據可在核對內容、現況權威與引用後移至 `docs/09_archive/`，原路徑以短轉址維持相容。2026-07 的 21 份 Post-V1 Evidence Pipeline 收據已集中歸檔；當時的 Scheduler SOP／待辦不作為目前操作權威。Gate 7 的 Prospective Formal Restart Direction、Simulated Portfolio Execution Plan 與 Decision-clock Contract 仍是目前方向／執行 SSOT／契約，不因檔名日期而歸檔；狀態仍以 Snapshot 判讀。
- 2026-07-13 Broker Flow dashboard failed gate、後續 semantics scoped pass，以及 2026-07-07 readability polish closeout 已移入 `docs/09_archive/`；原 QA 路徑保留轉址，Broker Flow 的失敗與後續優化需成對閱讀。
- R001 baseline、R006 ML ABI baseline 與 R020 deferred-threshold dated QA 已移至 `docs/09_archive/`；R031 task evidence index 保留為狀態導覽，R006 未知正式資產的未驗邊界仍由 dated addendum 承接，舊 QA 路徑保留轉址。
- 三份 2026-09-08 V4 NEXT Formal／ML／Ops handoff 已移至 Archive；舊 QA 路徑保留轉址，9/30 Formal bootstrap repair 改為直接連到保留原文，其他目前狀態／操作回到 Snapshot／Manual。
- 12 份早期一次性 QA／工程 closeout／治理 audit 已移至 Archive；Evidence Rehearsal Runbook、Full App coverage mapping、External Validation Register 等現行契約入口留在原位，舊路徑轉址承接仍存活的歷史引用。
- 六份 2026-07／08 資料來源、license、owner 與 display refresh receipt 已歸檔；pilot／授權／來源限制照原文保存，現行 P0 handoff 與 Snapshot 留在 QA／core。
- 七份 2026-08-18 至 08-28 的 Prospective Formal clock activation、execution、staging、calendar 與 failure receipts 已歸檔；目前 restart direction 與 decision-clock contract 留在 QA，歷史 staging 不構成重啟／發布授權，8/26 僅為具名一次性例外。
- `PROGRAM_STATUS_REBASELINE_2026_08_29.md` 已改為 Archive 日期快照；目前狀態以 PROJECT_SNAPSHOT 為準，Manual、Gate 7 與 External Validation Register 已解除對 8/29 snapshot 的 current-state 依賴，舊 QA 路徑保留轉址。
- 2026-08-29 ML Release v4 Storage Retention Cleanup 是使用者授權的一次性 custody 收據，已移至 Archive 並保留舊 QA 路徑轉址；目前 immutable publication retention 規則以 system_architecture §11.1 為準，操作以 Application Manual Supplements 為準。
- 三份 2026-08-30 Runtime／Performance、Paper、Formal／ML readiness 詳細快照已移至 Archive；目前狀態以 PROJECT_SNAPSHOT 為準。P0 與 Evidence weekly approval handoff 仍留在 QA 並由 External Validation Register 引用，日期化數字不代表今日 Gate 狀態。
- 兩份 2026-07-12 V2.3 P0 source decision receipts 已移至 Archive；P0 逐來源 Register 留在 QA 作為目前分類入口。V2.2 Phase 5 simulated approval rehearsal 因 Application Manual 仍引用，保留原文於 QA 並標明不構成 approval／scheduler enablement。
- LUNA A／C handoff 與 9/8 integration closeout 已移至 Archive；Luna B handoff、pre-integration review 保留在 QA，因 audit scripts 直接讀取這兩份原文。QA README 導覽明列歸檔與保留理由，舊路徑均有短導引。
- 六份 2026-07 V2.4／V2.5 paper baseline、V3.0 readiness／manual validation 與 V4.0 dated release-freeze receipt 已歸檔；成熟度文件保留 Gate 與決議摘要、移除單日 metrics，舊 QA 路徑仍供 script existence check 與歷史引用相容。
- 三份 2026-09-14／15 decision workbench、next-increment 與 continuity write-path audit 已歸檔；QA 導覽與 PIT industry discovery 改連 Archive 原文，日期化剩餘工作不再混作目前優先序。
- 四份 2026-09-15／16 PIT source discovery、daily source design、probability-learning audit 與 decision/evidence clock QA 已歸檔；後續 reader／caller acceptance QA 與目前狀態入口仍保留，舊 QA 路徑以短導引承接引用。
- Continuity Review pre-R1 gap audit 已由後續 R1 Workbench QA 取代並歸檔；R1 驗收原件與仍未完成 full-source cross-page acceptance 的計畫留在 QA，避免把 pre-R1 gap 或 acceptance checklist 誤標為目前完成狀態。
- 五份 BALDR 2026-09-25／26 整合、scheduler、readiness 與技術修補 closeout 收據及兩份已執行 request／inventory JSON 已歸檔；QA 舊路徑保留導引，本機 ignored inventory／baseline sidecars 留在 QA，並明示乾淨 checkout 不一定包含。
- 三份 V4 2026-09-08 Data freshness、Direct／OOC／Release、Stock Research handoff 已歸檔；當日數字與 next step 不作目前操作或 Gate 狀態，QA 路徑保留轉址，入口改導向 10/03 data closeout、Manual、Snapshot 與近期 H20 QA。
- 2026-09-07 的三份 V4 bounded data／machine／ML QA 亦已歸檔；仍以 Snapshot 與較新的專題收據判讀目前狀態，不將單日 release evidence 當成現行資格結論。
- `FULL_APP_HEALTHCHECK_2026_06_16.md` 已歸檔為早期 UI smoke 快照；現行架構與操作分別看 system architecture 和 Application Manual，舊 QA 路徑保留轉址。
- 若要採用歸檔 Phase SOP 中的操作內容，先依目前程式與 `docs/07_guides/APPLICATION_MANUAL.md` 核對並另行改寫；不要直接把歷史 Phase gate 重新當成目前規範。
- `docs/superpowers/` 是 plan／spec／prompt 歷史追溯區；README 導覽與 165 項 manifest 區分現行 Baldr 計畫、留在原路徑的歷史文件、以及已封存原文／舊路徑轉址。13 份具完成 QA 證據的 Post-V1 plan/spec、1 份 Month 2 結案 plan、4 份 Month 3 Factor Layer 計畫與 1 份設計規格，以及 1 份 Month 4 closure plan、1 份已結案 Safe Refactor continuation plan、8 份 Month 3 Portfolio Replay implementation plans 與 1 份 Month 3 closure audit、3 份已結案 V3 ML／UI polish plans 與 3 份配套 design specs、1 份 TPEX daily-price backfill plan、1 組金融 float boundary plan/spec、1 份文件 Roadmap rebaseline plan、1 組 Legacy Test Governance plan/spec 已封存；Scheduler Approval pair 因測試內容依賴、Healthcheck Batch 3 plan 因原人工 QA 仍留有待重測項目而保留原文。
- `docs/06_qa/UI_QT_DEVELOPMENT_ROADMAP_AUDIT.md` 已因 2026-05-19 舊狀態容易誤導而歸檔為 `docs/09_archive/UI_QT_DEVELOPMENT_ROADMAP_AUDIT_2026_05_19.md`。
- `docs/agents/PATCH_MEMO.md` 已移至 `docs/08_technical/MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md`；MCP / openmarkets patch memo 屬技術環境備忘，不屬 Agent 角色規範。
- `multi_agent_workflow.md` 已移至 `docs/agents/`；Agent 分支、合併與協作協議不屬於系統架構文件。
- `SHIM_LEGACY_REMOVAL_AUDIT_2026-07-12.md` 已移至 `docs/06_qa/`；移除 Gate、驗證結果與回滾證據屬 QA closeout。
- `REFACTORING_MIGRATION_PLAN_2025.md` 與 `SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md` 已移至 `docs/09_archive/`；兩者均已完成，只作歷史遷移、執行證據與 rollback 追溯。

---

## 五、每次整理後必跑檢查

1. Markdown 文件數量與目錄分布。
2. Active 文件是否都有 README 或索引入口。
3. Broken relative links。
4. Snapshot、Product Roadmap、6M Roadmap、版本成熟度、Roadmap Hub、Architecture 與 Index 的職責及連結是否一致；Hub 不複製狀態。
5. 是否有明顯過期的「待開始 / 進行中」描述。

### 避免重複內容重新累積

- README、索引與 Roadmap Hub 只維護閱讀路徑和文件職責；動態驗收數字、完成度與阻塞狀態連到 Snapshot 或原始 QA 證據，不複製整段現況。
- 同主題的設計契約、操作手冊與日期化驗收報告有不同用途；依職責判斷取捨，不能只靠檔名相似或共同關鍵字刪除。不可變收據、固定雜湊與回滾證據須保留。
- 文檔盤點分開統計正式 `docs/` 與 `output/` 工作副本、QA raw output、Graphify 產物；工作副本中的同名文件不是新的文檔權威。
- Obsidian 圖譜可用 Search 的 `path:` 篩選正式文檔與根目錄入口，避免納入 `output/` 和 `graphify-out/`。本機圖譜設定屬 `.obsidian/`，不提交；篩選只調整閱讀範圍，不代表已完成文檔內容整理。
- `APPLICATION_MANUAL.md` 先呈現安裝與工作區主流程；`APPLICATION_MANUAL_SUPPLEMENTS.md` 屬同一手冊的操作附冊，保存較長的維運、研究與操作補充。搬移章節須保留原深連結導向；純更新流水帳放 archive，不再插在操作章節中。

## 六、更新記錄

- 2026-10-08：歸檔 LUNA A／C handoff 與整合 closeout；因 inventory 工具直接讀取原文而保留 LUNA B handoff／Project Consolidation Review，QA 地圖標示兩者界線並直達 Archive 收據。
- 2026-10-08：依目前引用歸檔 Program Status、ML retention custody、8/30 readiness details 與 V2.3 source decisions；QA 導覽保留當前 Gate 7 execution SSOT，並明確區分有效契約、owner handoff 與歷史快照。
- 2026-10-08：補齊 Scoped SSOT 的願景、產品、工程、現況、成熟度與歷史移交分工；將 Roadmap Hub 定義為純導覽，並說明版本成熟度不代表工程 Gate 順序。
- 2026-10-08：依逐檔引用檢查修正 `05_phases/` 保留理由，明列目前唯一核實的 Active 直接引用；歷史文件仍須按引用、證據與追溯價值逐檔判讀。
- 2026-10-08：將 13 份 Phase／SOP 原文按原相對層次歸檔，保留舊路徑轉址與唯一 Active Phase 2 架構引用；目前 Phase 目錄只保留索引與相容入口。
- 2026-10-08：將 21 份 2026-07 Post-V1 Evidence Pipeline QA 原文歸檔，原路徑保留轉址；同步 QA／Archive 導覽與歸檔規則，未改動核心 Index。
- 2026-10-08：歸檔 3 份 2026-09-07 V4 bounded release／data QA，修復歸檔後一條跨目錄相對連結並保留舊路徑轉址。
- 2026-10-08：歸檔 2026-06-16 全 UI healthcheck 快照，保留原文與 QA 舊路徑轉址，現行操作路由至 Architecture／Manual。
- 2026-10-08：將兩份 Broker Flow 效能收據成對歸檔，並歸檔 2026-07-07 readability polish closeout；保留原文 hash、失敗→修正脈絡與 QA 舊路徑轉址。
- 2026-10-08：歸檔 R001、R006、R020 三份已具結案或 dated-snapshot 定位的 QA 原文；以 R031 task evidence index 導覽處置，保留舊 QA 路徑與 R006 unknown-artifact addendum。
- 2026-10-08：歸檔 2026-09-08 V4 NEXT Formal／ML／Ops handoff；將仍引用精確 Formal handoff 章節的 9/30 repair 連結更新至封存原文，其餘歷史引用由舊路徑轉址承接。
- 2026-10-08：將 12 份已完成或日期化的早期 QA／audit 歸檔，修復 Evidence Rehearsal、Full App coverage、External Validation Register 三條原文相對連結，保留現行操作／Gate 狀態入口。
- 2026-10-08：歸檔六份日期化資料／source-owner receipt，保留來源與授權邊界，並從 QA／Archive 導覽指向仍有效的 P0 handoff 與 Snapshot。
- 2026-10-08：歸檔七份 Prospective Formal clock 歷史收據，QA 保留目前 restart direction 與契約；標明 staging／failure 的有限效力及 8/26 一次性具名例外。
- 2026-10-08：歸檔六份 V2/V3/V4 dated readiness 收據並保留 QA 相容導引；收斂版本成熟度正文中的重複單日數字，V4 跨文件連結改為明確指向仍有效的 QA／core 路徑。
- 2026-10-08：歸檔三份 2026-09 decision workbench／continuity audit；將 PIT industry discovery 的歷史 audit 引用改為直達封存原文，並以 QA／Archive 導覽保留查找路徑。
- 2026-10-08：將 2026-09-15／16 PIT source discovery、daily source design、probability-learning audit 與 decision/evidence clock QA 歸檔；保留 QA 舊路徑轉址，後續 acceptance QA 與現況入口仍留在 QA／Snapshot。
- 2026-10-08：以 R1 Workbench QA 對照並歸檔 pre-R1 continuity gap audit；Cross-page Journey acceptance plan 與 V6 personalization detailed contract 仍保留於 QA，README 補上直接入口和未完成邊界。
- 2026-10-08：將 BALDR 9/25–26 已完成的整合／scheduler／evidence readiness／technical QA 收據與已套用 prompt request 歸檔；兩個 ignored local baseline／inventory sidecars 不移動、不提交，歸檔導覽明示其僅在本機可得。
- 2026-10-08：歸檔三份 9/8 V4 Data／Direct／Stock Research owner handoff；保留原 QA 路徑導引，資料、Direct／ML、操作與個股研究導覽改指向目前權威及後續 closeout。
- 2026-10-08：將 13 份已完成 Post-V1 plan/spec 原文依 plans／specs 層次封存；以原路徑短導引、manifest bytes／SHA 與 Q1–Q8 QA links 保留追溯，Scheduler Approval pair 留在來源路徑供內容測試檢查。
- 2026-10-08：封存已結案 Month 2 parameter／run storage plan，修正既有 manifest bytes／SHA 不符原件的列，保留來源路徑導引並明示最終完成證據已取代早期「等待核准」快照。
- 2026-10-08：封存 Month 3 Factor Layer 的兩份實施計畫與配套設計規格；保留原路徑轉址及 plan/spec bytes／SHA，並明示原計畫中的提交核准核取方塊仍未勾選。
- 2026-10-08：另封存兩份具提交及驗證證據的 Month 3 Factor Layer 延伸計畫，以及 Month 4 Decision Desk closure 原文；保留 Month 4 結案摘要與未勾選模板核取方塊的差異。
- 2026-10-08：封存已完成的 Safe Refactor continuation plan；其 Wave 6 核准與 release healthcheck 由專項 QA audit 保留，舊路徑轉址至 Archive。
- 2026-10-08：將 Month 3 closure audit 及八份核取項目全完成的 Portfolio Replay 計畫成組歸檔；weight/exposure 計畫因留有未勾項目而留在來源路徑，README 與 manifest 明確標示。
- 2026-10-08：將 V3 ML readiness 與兩組 UI readability polish 的已結案 plan/spec 配對歸檔；ML 原件明定僅研究／closeout readiness，不代表 production ML。
- 2026-10-08：將 TPEX daily-price backfill plan、金融 float boundary plan/spec 與 Scoped SSOT roadmap rebaseline plan 封存；保留舊路徑導引及原始 hash，分別指向後續 TPEX QA、現行數值治理入口與現行文件權威。
- 2026-07-12：完成全 docs 位置稽核，將 Agent workflow、Shim removal audit 與兩份已完成重構文件分別移至 `agents/`、`06_qa/`、`09_archive/`，並同步所有 Active 引用與目錄 README。
- 2026-07-06：完成 push 前 docs 結構稽核後補上 `superpowers/` folder ownership、歸檔舊 UI Qt roadmap audit，並將 MCP patch memo 移至技術文件。
- 2026-07-06：新增 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 作為 V2.0 之後長期版本階梯 companion，納入核心入口與文件權威層級。
- 2026-07-04：新增 `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 作為外部參考與 V1.5-V2.0 版本形狀 companion，納入核心入口與文件權威層級。
- 2026-07-03：將 `docs/05_phases/` 明確降格為 Historical / Reference 區，保留歷史設計與研究 SOP 脈絡，但不作目前 roadmap、目前完成狀態或日常操作權威。

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
- `docs/06_qa/` 保存日期化驗證與調查證據；已結束的收據可在核對內容、現況權威與引用後移至 `docs/09_archive/`，原路徑以短轉址維持相容。2026-07 的 21 份 Post-V1 Evidence Pipeline 收據已集中歸檔；當時的 Scheduler SOP／待辦不作為目前操作權威。
- 2026-09-07 的三份 V4 bounded data／machine／ML QA 亦已歸檔；仍以 Snapshot 與較新的專題收據判讀目前狀態，不將單日 release evidence 當成現行資格結論。
- `FULL_APP_HEALTHCHECK_2026_06_16.md` 已歸檔為早期 UI smoke 快照；現行架構與操作分別看 system architecture 和 Application Manual，舊 QA 路徑保留轉址。
- 若要採用歸檔 Phase SOP 中的操作內容，先依目前程式與 `docs/07_guides/APPLICATION_MANUAL.md` 核對並另行改寫；不要直接把歷史 Phase gate 重新當成目前規範。
- `docs/superpowers/` 保留為 spec / plan 追溯區；新增 `README.md` 作為資料夾邊界，避免大量 plan / spec 被誤讀成目前 roadmap。
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

- 2026-10-08：補齊 Scoped SSOT 的願景、產品、工程、現況、成熟度與歷史移交分工；將 Roadmap Hub 定義為純導覽，並說明版本成熟度不代表工程 Gate 順序。
- 2026-10-08：依逐檔引用檢查修正 `05_phases/` 保留理由，明列目前唯一核實的 Active 直接引用；歷史文件仍須按引用、證據與追溯價值逐檔判讀。
- 2026-10-08：將 13 份 Phase／SOP 原文按原相對層次歸檔，保留舊路徑轉址與唯一 Active Phase 2 架構引用；目前 Phase 目錄只保留索引與相容入口。
- 2026-10-08：將 21 份 2026-07 Post-V1 Evidence Pipeline QA 原文歸檔，原路徑保留轉址；同步 QA／Archive 導覽與歸檔規則，未改動核心 Index。
- 2026-10-08：歸檔 3 份 2026-09-07 V4 bounded release／data QA，修復歸檔後一條跨目錄相對連結並保留舊路徑轉址。
- 2026-10-08：歸檔 2026-06-16 全 UI healthcheck 快照，保留原文與 QA 舊路徑轉址，現行操作路由至 Architecture／Manual。
- 2026-07-12：完成全 docs 位置稽核，將 Agent workflow、Shim removal audit 與兩份已完成重構文件分別移至 `agents/`、`06_qa/`、`09_archive/`，並同步所有 Active 引用與目錄 README。
- 2026-07-06：完成 push 前 docs 結構稽核後補上 `superpowers/` folder ownership、歸檔舊 UI Qt roadmap audit，並將 MCP patch memo 移至技術文件。
- 2026-07-06：新增 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 作為 V2.0 之後長期版本階梯 companion，納入核心入口與文件權威層級。
- 2026-07-04：新增 `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 作為外部參考與 V1.5-V2.0 版本形狀 companion，納入核心入口與文件權威層級。
- 2026-07-03：將 `docs/05_phases/` 明確降格為 Historical / Reference 區，保留歷史設計與研究 SOP 脈絡，但不作目前 roadmap、目前完成狀態或日常操作權威。

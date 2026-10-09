# 文檔結構與維護規則

> **最後更新**：2026-10-09
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
| `01_architecture/` | 架構、資料流、依賴邊界、Runtime 規範；保留與目標架構任務索引、驗收及回滾直接綁定的實作／審查報告 | 一般一次性 QA 收據（放 `06_qa/`）；`target_architecture_2026_09_22/REFACTOR_REPORTS/` 這類任務關聯報告不批次移出 |
| `02_features/` | 使用者可見功能、UI、策略、回測、評分說明 | Phase 規劃草案 |
| `03_data/` | 資料更新、資料流、資料重建、資料故障排除 | 券商分點專屬細節 |
| `04_broker_branch/` | 券商分點資料、分點解析、籌碼資料更新 | 一般每日資料更新 |
| `05_phases/` | 歷史 Phase 設計、Phase 3.5 SOP、Phase 4 設計追溯 | 目前 roadmap、目前完成狀態、日常操作指南 |
| `06_qa/` | QA 問題、總結、驗證、審核報告 | 長期架構設計 |
| `07_guides/` | 快速開始、安裝、腳本、測試操作 | 系統權威狀態 |
| `08_technical/` | 技術優化、環境、參數設計備忘 | 使用者導向流程 |
| `09_archive/` | 歷史總結、已執行提案、舊調查、舊完整 Roadmap、已結束 QA 快照 | 仍需日常引用的文件 |
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

`DOC_COVERAGE_MAP.md` 維護目前的權威分工、文件同步矩陣與 DoD；逐批搬移／覆蓋記錄集中放在 `docs/09_archive/DOC_COVERAGE_HISTORY_2026.md`，Map 不重複保留歷史批次索引。每次歸檔都要更新 Coverage History 與 Archive README；若權威邊界、目前入口或同步規則改變，再同步 Coverage Map 與受影響的 scoped authority。每筆歷史記錄仍須保留原路徑、目的地、來源證據與目前替代入口。

適合歸檔的內容：

- 舊線性 Phase 的完整 Done 與 Exit Criteria。
- 已執行完畢的 Next Action Plan。
- 舊 Roadmap current section。
- 過期但仍有決策脈絡價值的調查或提案。

### QA evidence retention

`docs/06_qa/` 保存具時間與範圍的驗收證據；日期、完成標籤或文件長度本身不決定歸檔。以下任一情況成立時，原文留在 QA：

- 仍被 Gate、開放問題／重驗、Roadmap、Manual、測試、腳本或固定輸出路徑引用。
- 它是目前有效的 scoped contract、唯一證據入口，或尚未被後續證據取代的最新驗收。

只有在 owner／Gate 已結案、未解事項與替代入口已交代、活躍路徑依賴已解除或保留相容入口後，才把純歷史收據移到 Archive。保留舊路徑短導引；Coverage History 記錄原路徑、封存位置、原件 bytes／hash、當時效力與目前替代入口。若產生器仍會寫入固定 QA 路徑，先處理 writer／consumer 契約，不能直接以 redirect 取代原件。

### Delete

符合以下所有條件即可刪除：

- 沒有被 Active 文件引用
- 沒有保留歷史脈絡的必要
- 內容已被更新、更完整的文件取代
- 文件本身是一次性 debug log、patch note、單日執行指南或過期草稿

---

## 四、目前已確認的整理決策

- 目前狀態、產品方向、工程順序、成熟度與架構權威依第 1 節分工；`DOCUMENTATION_INDEX.md` 與 `DEVELOPMENT_ROADMAP.md` 只負責導覽，不複製狀態或建立第二套計畫。
- 根目錄 `README.md` 面向使用者；`PROJECT_NAVIGATION.md` 與 `PROJECT_INVENTORY.md` 是開發者入口。`AGENT_CONTEXT.md` 僅作快速導覽，Agent 強制規則仍以根目錄 `AGENTS.md` 與 `docs/agents/` 為準。
- `ui_qt/README.md` 不屬於 `docs/`，可能落後於目前功能；判斷操作、架構與成熟度時回到對應的 Manual、Architecture 與 Snapshot。
- `docs/05_phases/` 是歷史參考區，保留目錄入口與相容導引；重用其中 SOP 前先依目前程式及 Application Manual 核對。
- `docs/06_qa/` 的原件依第 3 節 QA retention 規則判斷；主題入口看 QA README，日期或 `Done` 標籤本身不代表可歸檔。
- `docs/superpowers/` 保存設計與執行追溯；目前仍進行中的例外由其 README 指明，其他計畫不代表現行優先序或執行授權，舊路徑與封存位置以 manifest 為準。
- 每次歸檔的原路徑、目的地、原件 bytes／SHA、效力與替代入口記在 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)，分類導航看 [Archive README](../09_archive/README.md)；Archive 不作目前狀態依據。
- 本節原有逐批決策與第 6 節更新流水帳的完整快照保存在 [歷史整理決策與更新記錄](../09_archive/DOCUMENTATION_STRUCTURE_CHANGELOG_20261009_HISTORY.md)，其搬移與尚缺專屬記錄的 legacy Archive 項目由 Coverage History Entry 109 追蹤。

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

- 2026-10-09：收斂本文件為現行權威分工、資料夾歸屬、生命週期與整理檢查規則；逐批歸檔敘述移至 Coverage History，原第 4／6 節快照見 [Archive 歷史記錄](../09_archive/DOCUMENTATION_STRUCTURE_CHANGELOG_20261009_HISTORY.md)及 [Coverage History Entry 109](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-109)。另明確保留與目標架構任務索引、驗收及回滾直接綁定的 `REFACTOR_REPORTS/`；一般一次性 QA 仍歸 `docs/06_qa/`。

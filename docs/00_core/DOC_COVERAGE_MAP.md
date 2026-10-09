# 文檔覆蓋矩陣（Documentation Coverage Map）

> 閱讀順序：先看本頁的權威邊界、文件同步矩陣與 DoD；下方保留歷史批次標題作為相容索引，逐批整理內容移至 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。歷史批次只提供追溯證據，目前狀態依各主題權威文件判讀。

## 可追溯性限制

[2026-10-06 BALDR First Wave QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md) 引用的 Python／exe 截圖目前只存在本機 `output/qa/`；該目錄受 Git ignore 排除，因此乾淨 checkout 無法取得圖片。QA 收據文字與檢查結果仍保留，但圖片本身沒有隨 repository 封存，不能在乾淨 checkout 重新核對視覺截圖。

## 一、文件權威邊界（Scoped SSOT）

本專案不再使用單一文件承擔所有最高權威。當文件描述衝突時，先判斷主題，再依主題對應的權威文件處理。

| 主題 | 權威文件 | 判斷規則 |
|---|---|---|
| 目前狀態、本週優先事項、高風險區 | `docs/00_core/PROJECT_SNAPSHOT.md` | 開場與日常工作先看 Snapshot。 |
| 重構完成後產品方向、投資問題、產品能力演進 | `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` | 定義 bounded advice、Portfolio、Exit、Evidence、Data、ML 與 pruning 產品 Gate；不保存工程 checklist。 |
| 未來 6 個月工程路線 | `docs/00_core/ROADMAP_6M_ENGINEERING.md` | 里程碑、交付物與驗收標準以 6M Roadmap 為準；Month 1–6 是相對順序，進度看 Snapshot。 |
| 外部專案參考、資料源優先序、V1.5-V2.0 版本形狀 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` | 作為 6M Roadmap / Version Roadmap companion；不取代 Vision 或目前狀態權威。 |
| V2.0 之後長期產品成熟度 | `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` | 只維護 V2.1–V4.0 maturity milestone；目前進度看 Snapshot，日期化狀態／工程交接看 `docs/09_archive/`；不取代 Product / 6M Roadmap、Vision。 |
| Roadmap 入口與權威導覽 | `docs/00_core/DEVELOPMENT_ROADMAP.md` | Roadmap Hub 只連結權威文件，不複製 Next、狀態、風險或完整歷史。 |
| 舊 Roadmap 項目處置與移交 | `docs/00_core/LEGACY_ROADMAP_CARRYOVER.md` | 每個 Legacy 項目有唯一處置；移交項目標示新版落點與驗收，舊月份標籤只供歷史追溯。 |
| 系統架構、模組邊界、資料流 | `docs/01_architecture/system_architecture.md` | 架構描述衝突時，以系統架構文件為準。 |
| 理想目標架構與 Current → Target 演進 | `docs/01_architecture/target_system_architecture.md` | Target capability 不代表目前已實作；現況仍回到 system architecture。 |
| North Star、Bounded Advice、Evidence、Success Levels、Non-goals | `docs/01_architecture/system_vision_specification.md` | 不保存詳細 implementation checklist 或完成流水帳。 |
| 目前使用者完整操作流程 | `docs/07_guides/APPLICATION_MANUAL.md` | 9 個頂層工作區、跨工作區流程、安全限制與排錯以本手冊為準；較長的操作補充與受控維運保存在同屬手冊的 `APPLICATION_MANUAL_SUPPLEMENTS.md`，涉及該入口時同步檢查附冊。 |
| 文檔位置與分類 | `docs/00_core/DOCUMENTATION_INDEX.md` | 只作導航，不取代狀態或架構權威。 |
| 文檔生命週期與歸檔規則 | `docs/00_core/DOCUMENTATION_STRUCTURE.md`；QA 收據專項入口見 `docs/06_qa/README.md` | 日期或完成標籤不能單獨作為 QA 歸檔依據；必須核對未解 Gate、引用路徑、固定輸出位置與替代證據。 |
| 歷史 Phase、舊 Done、舊 Roadmap current section | `docs/09_archive/DEVELOPMENT_ROADMAP_LEGACY_2026_06.md` | 只作追溯，不作目前狀態依據。 |

其他專項文件權威：

1. **`PROJECT_NAVIGATION.md`** - 開發者導航權威
   - 三層架構（UI / Service / Domain）的導航說明
   - 功能導航（我要做 X，要去哪裡看？）

2. **`AGENTS.md` / `docs/agents/`** - Codex 與 Agent 指引權威
   - `AGENTS.md` 是 Codex 自動讀取的 repo 指令入口
   - `docs/agents/` 保存完整 Agent 職責、Prompt 與共用上下文

3. **其他專項文檔** - 功能特定權威
   - `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明
   - `docs/07_guides/APPLICATION_MANUAL.md` - 完整使用手冊
   - `docs/02_features/USER_GUIDE.md` - 進階專題教學
   - `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格

**衝突處理規則：**
- 若 Snapshot、Product Roadmap、6M Roadmap、Architecture 之間衝突 → 先判斷主題，依上表權威文件修正。
- 若 Index 路徑與實際檔案不符 → 以實際檔案與文件結構規則修正 Index。
- 若 Active 專項文檔仍引用舊 Phase 或舊 Roadmap current section → 更新為 scoped authority；歷史內容移至 archive 或保留歷史語意。
- 無法判斷主題歸屬時，標示「需要確認」，不要自行建立第二套權威。

## 二、變更類型 → 必須更新的文件對照表

### UI / View / Tab 變更

**變更範圍：**
- `ui_qt/views/*.py` 新增/修改/刪除
- Tab 結構變更（新增 Tab、合併 Tab、Tab 順序變更）
- UI 功能新增/修改/移除

**必須更新（Must）：**
- `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明
- `docs/07_guides/APPLICATION_MANUAL.md` - 新增或改變使用者可操作功能、參數、結果或限制時
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「現在的工作模式」段落（如影響使用流程）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**應該更新（Should）：**
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如有操作流程變更）
- `PROJECT_NAVIGATION.md` - 「功能導航」段落（如新增功能）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大功能變更）

---

### Service / Domain / DTO 變更

**變更範圍：**
- `app_module/*.py` 新增/修改/刪除
- `decision_module/*.py` 新增/修改/刪除
- DTO 結構變更（`app_module/runtime_dtos.py` / `app_module/decision_desk_dtos.py`）

**必須更新（Must）：**
- `PROJECT_NAVIGATION.md` - 「三層架構導航」段落（如架構變更）
- `docs/01_architecture/system_architecture.md` - 系統架構文檔（如架構變更）

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「高風險區」段落（如涉及高風險模組）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）

**可選更新（Nice-to-have）：**
- `PROJECT_INVENTORY.md` - 專案盤點（如為重大模組變更）

---

### 回測 / 推薦核心邏輯變更

**變更範圍：**
- `app_module/backtest_service.py` 修改
- `app_module/recommendation_service.py` 修改
- `backtest_module/*.py` 修改
- `decision_module/scoring_engine.py` 修改
- `decision_module/reason_engine.py` 修改
- Strategy registry / preset / promotion 相關服務變更

**必須更新（Must）：**
- `docs/02_features/BACKTEST_LAB_FEATURES.md` - 回測功能文檔（如回測邏輯變更）
- `docs/07_guides/APPLICATION_MANUAL.md` - 回測模式、參數、結果判讀或 Promote 規則變更
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如操作流程變更）
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「高風險區」段落（這些都是高風險區）

**應該更新（Should）：**
- `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格（如策略邏輯變更）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**可選更新（Nice-to-have）：**
- `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明（如 UI 行為變更）

---

### Agent 文件變更

**變更範圍：**
- `docs/agents/*.md` 新增/修改/刪除
- Agent 職責變更
- Agent Prompt 模板變更

**必須更新（Must）：**
- `AGENTS.md` - 若 Codex 自動讀取入口或強制必讀順序變更
- `docs/agents/README.md` - Agent 總覽（如新增 Agent 或職責變更）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 文檔索引（如新增 Agent 文檔）

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「Tech Lead 的預設任務」段落（如 Tech Lead 變更）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大變更）

---

### 使用流程、目前狀態或 Roadmap 變更

**變更範圍：**
- 目前狀態或產品閉環狀態變更
- 工作流程變更（「現在的工作模式」）
- 優先事項變更
- 系統定位變更
- 未來 6 個月工程路線變更

**必須更新（Must）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 目前狀態、工作模式、優先事項、高風險區
- `docs/00_core/ROADMAP_6M_ENGINEERING.md` - 若影響 6 個月里程碑、交付物或驗收標準
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - 若新增或調整 Roadmap Hub 的權威入口
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若索引內進度文字過期，需更新

**應該更新（Should）：**
- `README.md` - 專案主文檔（如 Phase 狀態變更）
- `PROJECT_NAVIGATION.md` / `PROJECT_INVENTORY.md` - 若影響開發導航或盤點

**可選更新（Nice-to-have）：**
- `PROJECT_INVENTORY.md` - 專案盤點（如為重大狀態變更）

---

### 資料處理 / 資料架構變更

**變更範圍：**
- `data_module/*.py` 修改
- 資料格式變更
- 資料流程變更

**必須更新（Must）：**
- docs/01_architecture/system_architecture.md - 現行系統資料流與資料層架構（架構變更時）
- docs/03_data/DATA_FETCHING_LOGIC.md - 現行來源、欄位與獲取邏輯
- docs/03_data/daily_data_update_guide.md - 使用者更新流程（流程變更時）
- `docs/03_data/DATA_FETCHING_LOGIC.md` - 資料獲取邏輯（如資料獲取邏輯變更）
- `docs/03_data/daily_data_update_guide.md` - 每日資料更新指南（如更新流程變更）

**應該更新（Should）：**
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**可選更新（Nice-to-have）：**
- `docs/02_features/USER_GUIDE.md` - 進階使用者指南（如影響使用者操作）
- `docs/07_guides/APPLICATION_MANUAL.md` - 完整操作手冊（如影響使用流程、參數、結果判讀或安全限制）

---

### 容量 / retention / immutable artifact 清理

**變更範圍：**
- 正式 output、immutable run、模型 publication、checkpoint 或大型 QA artifact 的刪除／搬移
- retention 規則、保留數、current pointer、dependency closure 或 recovery 語意變更
- 容量 blocker 的建立或解除

**必須更新（Must）：**
- `docs/06_qa/<DATED_CLEANUP_AUDIT>.md` - owner 授權、exact scope、before／after bytes、全部刪除／保留 ID、pointer／hash、依賴、不可逆性、recovery 與 post-check
- `docs/00_core/PROJECT_SNAPSHOT.md` - current capacity、readiness 影響、stale status supersession
- `docs/01_architecture/system_architecture.md` - 若改變 retention／pointer／custody／tombstone 邊界
- `docs/00_core/DOCUMENTATION_INDEX.md` - 新增 durable audit 入口

**應該更新（Should）：**
- `docs/07_guides/APPLICATION_MANUAL.md` - 若使用者日後需判讀、執行或排錯 retention／preflight
- `docs/00_core/ROADMAP_6M_ENGINEERING.md` - 若容量影響 Gate／里程碑／production canary
- 既有 readiness／runbook 文件 - 保留歷史 ID，不偷換；artifact 已刪時新增 tombstone／supersession

**固定安全檢查：**
- 不破壞 raw source；不對 broad root／wildcard 做遞迴刪除
- 先做 untruncated inventory、active lock／process、repo reference、pointer 與完整 dependency closure 檢查
- resume deletion 與 complete-run deletion 分開核准；明示只能重算或冷 archive 的 recovery 界線
- read-only inspector 的 `automatic_delete_allowed=false` 不因一次人工授權而變成長期自動刪除權

---

### 策略設計 / 策略規格變更

**變更範圍：**
- `docs/strategies/*.md` 新增/修改/刪除
- 策略邏輯變更
- 策略參數變更

**必須更新（Must）：**
- `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格（如策略規格變更）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增策略文檔，需更新索引

**應該更新（Should）：**
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如影響策略使用）
- `docs/02_features/BACKTEST_LAB_FEATURES.md` - 回測功能文檔（如策略回測變更）

**可選更新（Nice-to-have）：**
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如為重大策略方向或入口變更）

---

### 文檔結構 / 文檔組織變更

**變更範圍：**
- 新增/刪除/重組文檔
- 文檔索引結構變更

**必須更新（Must）：**
- `docs/00_core/DOCUMENTATION_INDEX.md` - 文檔索引（必須反映最新結構）
- `docs/00_core/DOCUMENTATION_STRUCTURE.md` - 若資料夾歸屬、刪除/歸檔規則、文件生命週期有變更

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「指定權威文件」段落（如權威文件變更）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大結構變更）

## 三、Documentation Definition of Done（DoD）

文件更新完成必須滿足以下所有條件：

### 必須條件（Must）

1. **所有 Must 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查
   - 所有標示為 Must 的文件都已更新

2. **Scoped Authority 一致性檢查通過**
   - `PROJECT_SNAPSHOT.md` 的目前狀態與本週優先事項合理反映當前工作。
   - Snapshot 的近期工作能對應 6M Roadmap 中的 Gate 與依賴；未設定計畫起日時，不將相對月份推斷成目前月份。
   - Roadmap Hub 正確連到 Snapshot、Product Roadmap 與 6M Roadmap，不複製任何一份文件的 Next 或狀態。
   - `system_architecture.md` 的架構描述不落後於 Snapshot 的已完成能力。
   - `DOCUMENTATION_INDEX.md` 包含新增、搬移或歸檔的 Markdown。
   - 若發現不一致，必須依主題權威文件修正，而不是一律回寫 Roadmap。

3. **文件結構已更新**
   - 新增/刪除/搬移 Markdown 後，`DOCUMENTATION_INDEX.md` 必須同步
   - 若文件分類或刪除規則改變，`DOCUMENTATION_STRUCTURE.md` 必須同步

4. **相關使用指南已更新**
   - 若變更影響使用者操作流程，`docs/07_guides/APPLICATION_MANUAL.md` 必須更新
   - 若變更影響進階專題教學，`docs/02_features/USER_GUIDE.md` 必須更新
   - 若變更影響 UI 功能，`docs/02_features/UI_FEATURES_DOCUMENTATION.md` 必須更新

5. **Manual 完整性 Gate 已通過**
   - 每個使用者可見工作區都有入口與前置條件。
   - 每個可操作功能都有步驟與參數意義。
   - 結果頁有判讀方式，不只列出功能名稱。
   - 危險操作、不可逆行為與目前限制有明確警告。
   - 至少包含常見失敗與排錯入口。

6. **變更日誌已記錄**
   - 根據 `docs/agents/shared_context.md` 的「更新記錄 / 變更日誌規範」記錄變更
   - 若存在變更日誌文件（如 `docs/UPDATE_LOG_*.md`），需記錄變更

### 應該條件（Should）

1. **所有 Should 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查
   - 所有標示為 Should 的文件都已更新

2. **架構文檔已更新**
   - 若變更影響系統架構，`docs/01_architecture/system_architecture.md` 或 `PROJECT_NAVIGATION.md` 已更新

3. **專案主文檔已更新**
   - 若為重大變更，`README.md` 已更新

### 可選條件（Nice-to-have）

1. **所有 Nice-to-have 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查

2. **專案盤點已更新**
   - 若為重大結構變更，`PROJECT_INVENTORY.md` 已更新

---

## 一致性檢查清單

每次文件更新後，必須檢查以下一致性：

### Snapshot ↔ Roadmap Hub ↔ 6M Roadmap 一致性
- [ ] Snapshot 的近期優先事項可對應到 6M Roadmap 的 Gate／依賴；沒有明確起日就不宣稱當前 Month N。
- [ ] Roadmap Hub 連結正確指向 Snapshot、Product Roadmap 與 6M Roadmap，且不複製 Next 或狀態。
- [ ] Snapshot 的高風險區涵蓋 6M Roadmap 近期任務的高風險模組。
- [ ] Product Roadmap 定義產品問題與 Gate；6M Roadmap 只轉成工程交付、依賴、測試與 Exit Criteria。
- [ ] Vision 只保存 North Star / Policy / Evidence / Success / Non-goals，不複製詳細工程 checklist。
- [ ] Current Architecture 與 Target Architecture 清楚分開；Target-only 模組不得寫成已存在。

### Index ↔ Scoped Authority 一致性
- [ ] Index 的進度描述不與 Snapshot、6M Roadmap 或 Architecture 衝突。
- [ ] 文檔索引完整（所有新文檔已加入索引）

### 專項文檔 ↔ Scoped Authority 一致性
- [ ] UI 功能描述與 Snapshot / UI docs 一致。
- [ ] 完整操作手冊與目前 9 個工作區、按鈕啟用狀態及工作模式一致。
- [ ] 進階使用者指南與完整操作手冊不衝突。
- [ ] 架構文檔與目前模組實際邊界一致。

---

## 容易被忽略但必須更新的文件清單

以下文件在變更時容易被忽略，但根據變更類型，必須檢查：

### 所有變更類型都必須檢查

1. **`docs/00_core/PROJECT_SNAPSHOT.md`**
   - 當變更影響「現在的工作模式」時 → 必須更新
   - 當變更影響 Phase 狀態時 → 必須更新
   - 當變更影響優先事項時 → 必須更新
   - 當變更涉及高風險區時 → 必須更新

2. **`docs/00_core/DOCUMENTATION_INDEX.md`**
   - 當新增/刪除文檔時 → 必須更新索引
   - 當文檔結構變更時 → 必須更新索引
   - 當進度描述過期時 → 必須依 Scoped Authority 更新

3. **`docs/00_core/DOCUMENTATION_STRUCTURE.md`**
   - 當新增/刪除資料夾時 → 必須更新資料夾歸屬
   - 當刪除 Active Markdown 時 → 必須確認符合 Delete 條件
   - 當文件被改為 Historical 時 → 必須確認是否應移入 `09_archive/`

4. **`docs/00_core/DEVELOPMENT_ROADMAP.md`**
   - 當 Roadmap Hub 的權威入口或連結目標變更時 → 必須更新。
   - 不再把完整歷史 Done、長期架構細節或所有風險都塞回本文件。

5. **`docs/00_core/ROADMAP_6M_ENGINEERING.md`**
   - 當 6 個月工程方向、月度里程碑、交付物或驗收標準變更時 → 必須更新。
   - 當只是單日完成小修復，且不影響 6 個月方向時 → 不需要更新。

### 特定變更類型必須檢查

6. **`PROJECT_NAVIGATION.md`**
   - 當架構變更時 → 必須更新「三層架構導航」
   - 當功能變更時 → 必須更新「功能導航」

7. **`README.md`**
   - 當為重大功能變更時 → 應該更新（雖然優先級較低，但容易被忽略）

## 使用說明（給 Documentation Agent）

1. **收到變更請求時**：
   - 根據「變更類型 → 必須更新的文件對照表」識別需要更新的文件
   - **特別檢查「容易被忽略但必須更新的文件清單」**
   - 標示優先級（Must / Should / Nice-to-have）

2. **執行 Coverage Pass 時**：
   - 列出所有需要更新的文件清單（包括容易被忽略的文件）
   - 檢查 Snapshot / Roadmap Hub / 6M Roadmap / Architecture / Index 一致性（使用下方「一致性檢查清單」）
   - 標示需要更新的具體段落

3. **執行 Patch Pass 時**：
   - 僅更新已確認的 Coverage 清單中的文件
   - 確保所有 Must 優先級的文件已更新
   - **特別確保 Snapshot / Roadmap Hub / 6M Roadmap / V2.1-V4.0 Roadmap / Architecture / Index 已更新並一致**

4. **完成後驗證**：
   - 執行「一致性檢查清單」
   - 確認所有 DoD 條件已滿足
   - **確認所有容易被忽略的文件已檢查並更新（如適用）**

---

**最後更新**：2026-10-09

## 更新記錄

- 2026-10-08：校正 Scoped SSOT 的產品、工程、現況、成熟度與歷史移交邊界；將 Hub 定義為純導覽、6M 月份明示為相對順序，並以 6M Gate 連結取代 Product Roadmap 重複維護工程交付清單。未修改當前狀態或 dirty Index。
- 2026-10-09：將 Portfolio Replay weight/exposure 歷史實作計畫原文歸檔，保留舊路徑導引與未勾選的最後 diff／stage 狀態；細節見 [Coverage History Entry 091](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-091)。
- 2026-10-09：將 Personal H20 10/06 dated status receipt 移入架構更新歷史，並把穩定的 artifact／lineage 身分契約抽回 system architecture §11；舊 heading 保留導引。細節見 [Coverage History Entry 092](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-092)。
- 2026-10-09：整理 Architecture 10/06 ML source custody 與 session proof／publisher loader 增量：穩定依賴方向契約移入 §11，guard／測試狀態保留在 QA／Archive，兩個舊標題維持導引。細節見 [Coverage History Entry 093](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-093)。
- 2026-10-09：將七段 UX21／UX08／UX13／UX18／UX19 日期化 research snapshot 增量從 Architecture 前置區移入歷史檔；Immutable source、cohort、method、pinned read、unknown／PIT 與 saved chart 契約濃縮於 §8。細節見 [Coverage History Entry 094](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-094)。
- 2026-10-09：將 10/06 homepage wiring 與 private review dated increments 移入架構更新歷史；首頁 routing 和 personal store／account identity 契約整理至 §§3、11。細節見 [Coverage History Entry 095](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-095)。
- 2026-10-09：將 2026-09-29 排程 operational custody dated slice 歸檔；各 lane source／release pins、同次 terminal receipt 與不可跨 lane 授權規則保留於 Architecture §10。細節見 [Coverage History Entry 096](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-096)。
- 2026-10-09：明確 QA 收據歸檔條件：仍被 Gate、未解問題或工具固定路徑使用的文件留在 QA；純歷史收據只有解除活躍依賴並保留相容導引後才搬移。
- 2026-10-09：將 8/27 Scheduler Health dated output snapshot 與 UX08 pre-integration controller handoff 歸檔；確認 scheduler 報告工具無固定 QA writer、UX08 目前整合收據保留在 QA，並以舊路徑 stub 維持引用。詳見 [Coverage History Entry 099](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-099)。
- 2026-10-09：將 Qt MainWindow shutdown teardown bounded 修復收據歸檔，保留 QA 舊路徑導引並明確區分仍待追查的 Native crash 與 SQLite inspector 問題。詳見 [Coverage History Entry 100](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。
- 2026-10-09：將 Position Health source-provider calendar-cache 測試隔離收據歸檔；保留原 QA 路徑與舊 Catalog 引用，並明示此收據不代表 Position Health 正式 Gate 結案。詳見 [Coverage History Entry 101](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-101)。
- 2026-10-09：將 9/20 ML Formal input readiness event-before snapshot 歸檔；舊 Catalog 引用由 QA 相容導引承接，QA／Archive 導覽明確標示它不是 9/21 實際驗收。詳見 [Coverage History Entry 102](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-102)。
- 2026-10-09：將 9/14 排程與週資料受託審查移入 Archive，舊 QA 路徑保留導引；明示 `reviewed_with_follow_up` 未通過正式採認及 SQLite quick check 的範圍限制。詳見 [Coverage History Entry 103](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-103)。
- 2026-10-09：將 9/30 唯讀服務合作式取消收據歸檔，保留原始 `125 passed／1 failed` 結果、後續 fixture contract 證據與 ignored raw log 限制；歷史連結由 QA 舊路徑承接。詳見 [Coverage History Entry 104](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-104)。
- 2026-10-09：將 V4.2 9/13 每日推薦 learning 部署／bounded run 歷史 QA 移入 Archive；保留 task 尚未執行、shadow-only 與無正式升格資格的界線。詳見 [Coverage History Entry 105](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-105)。
- 2026-10-09：核對 Gemini 提出的 10 份 QA 歸檔候選，只封存 3 份無活躍依賴的歷史紀錄；其餘 7 份因 tracked manifest 固定原 bytes／路徑或仍被現行入口引用而保留。詳見 [Coverage History Entry 097](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-097)。
- 2026-10-09：精簡 V2.1–V4.0 maturity spec 中重複的 7/12、8/30 status notes；歷史判讀仍由既有 Archive 提供，正文保留版本標準並以 Snapshot 表示現況。
- 2026-10-09：修正 R029 active report／R031 index 對 gate 草稿與預檢清冊的引用後，將兩份已 superseded 的 dated preflight 成對歸檔；保留 QA 原路徑導引與 WAVE14 凍結 manifest。細節見 [Coverage History Entry 098](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-098)。
- 2026-08-30：補入 P0／Evidence／Paper／Formal／Runtime／Performance／Data Update refresh 文件，並把 UI 舊 readiness artifact marker、週末 freshness 語意與最新測試 inventory 納入 coverage。
- 2026-09-10：補入 V4.1 A 線推薦機率校準的 QA handoff、Snapshot、Current architecture、Manual 與 Index；確認 20／5 outcome contract、walk-forward split、整數 bp calibration、read-only DB boundary 與自然 forward evidence 尚未成熟的 not-evaluable 狀態。chip／funding、industry、PIT theme 保持 deferred，沒有回填歷史 event。
- 2026-09-12：補入 V4.1 A 線第二輪歷史研究與候選方法包的 QA handoff、Snapshot、Current architecture、Navigation、Manual、Runbook 與 Index；新增逐列 manifest、gap／candidate coverage、自然時間分類與 create-only frozen artifact，確認正式 DB 僅 query-only 讀取且沒有 promotion／formal writer 變更。
- 2026-09-30：新增七項排程修復當日 QA，並將 Paper EOD no-work、queue historical diagnostic proof、Evidence #3 engineering readback／business degraded、Bank #1 failure／#2 Quick barrier、Formal denominator QA、fundamental dry-run、PIT 1,932／1,988 taxonomy mismatch 與 ML forward 9/30 child blocker 同步至 Snapshot、Current architecture、Application Manual、QA README、scheduled README。DOCUMENTATION_INDEX 已有 QA 入口；QA 同時保留 02:12 初始 inventory 及 04:23:28 PDT 最新 21-task native matrix，沒有宣稱自然 Quick 已 terminal 或全鏈通過。
- 2026-08-29：新增容量／retention／immutable artifact 清理的文件 coverage、custody、pointer／dependency、tombstone 與安全檢查要求。
- 2026-07-06：新增 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 的 scoped authority 邊界，定位為 V2.0 之後長期版本階梯 companion。
- 2026-07-11：新增 Post-Refactor Product Roadmap、Target Architecture 與新版 Vision scoped authority；補充 Product / Engineering、Current / Target 一致性 Gate。




## Coverage History 快速索引

詳細的逐批搬移／覆蓋內容、原路徑、archive 目的地及原文 hash 見[完整 Coverage History 清冊](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。

## 2026-10-08 封存 Task Loop 01-07 handoff

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-082)。

## 2026-10-09 歸檔 Portfolio Replay weight/exposure implementation plan

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-091)。

## 2026-10-09 整理 Personal H20 架構 dated increment

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-092)。

## 2026-10-09 整理 ML source custody 與 loader 架構增量

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-093)。

## 2026-10-09 整理 Daily Market Research 架構增量

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-094)。

## 2026-10-09 整理 Homepage 與 personal store 架構增量

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-095)。

## 2026-10-09 歸檔 9/29 排程 operational custody 切片

[完整批次紀錄](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-096)。

## 2026-10-09 覆核 QA 歸檔候選

[完整批次紀錄與逐檔 SHA-256](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-097)。

## 2026-10-09 歸檔 R029 gate 草稿與 preflight 清冊

[成對歸檔紀錄與逐檔 SHA-256](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-098)。

## 2026-10-09 歸檔 scheduler health snapshot 與 UX08 controller handoff

[逐檔來源與封存 SHA-256](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-099)。

## 2026-10-09 歸檔 Qt MainWindow shutdown teardown bounded QA

[原始 QA 與封存原文 SHA-256、引用及未涵蓋問題](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。

## 2026-10-09 歸檔 Position Health calendar-cache 測試隔離 QA

[原始 QA 與封存原文 SHA-256、引用及範圍界線](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-101)。

## 2026-10-09 歸檔 ML allocation Formal input readiness event-before snapshot

[原始 QA 與封存原文 SHA-256、引用及驗收界線](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-102)。

## 2026-10-09 歸檔 9/14 排程與週資料受託審查

[原始 QA 與封存原文 SHA-256、審查結果及引用界線](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-103)。

## 2026-10-09 歸檔唯讀服務合作式取消 QA

[原始 QA 與封存原文 SHA-256、當次 failed case 與 ignored log 限制](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-104)。

## 2026-10-09 歸檔 V4.2 每日推薦學習 9/13 部署 QA

[原始 QA 與封存原文 SHA-256、task 尚未執行與 research／shadow 範圍](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-105)。

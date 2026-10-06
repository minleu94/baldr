# 架構紅隊審查 (ARCHITECTURE RED TEAM REVIEW)

## 執行摘要：核心問題
**六個月後的開發者，能明確知道該在哪裡修改程式碼嗎？**
**不能。** 提案的架構成功解決了「義大利麵條程式碼 (Spaghetti Code)」的問題，但卻引入了「千層麵程式碼 (Lasagna Code)」（過度分層）。雖然技術上分離了責任，但當開發者要實作單一業務功能（例如新增一個 factor 或 confidence score）時，將被迫在 3 到 4 個不同的根目錄（`app_module`、`decision_module`、`data_module`、`ui_qt`）中尋找與修改檔案。此架構以犧牲「修改的局部性 (locality of change)」為代價來達成關注點分離。開發者雖然不需要全庫搜尋來了解「某個檔案在做什麼」，但他們必須全庫搜尋才能找到「實作一個功能需要修改的所有檔案」。

## 提案正確之處 (WHAT THE PROPOSAL GETS RIGHT)
1. **保留執行身分 (Preservation of Execution Identity)**：改用單次執行且被凍結的聚合體 (`RecommendationExecution`) 並賦予唯一的 `result_id`，這對除錯和歷史重播是一大進步。
2. **ML 隔離 (ML Quarantine)**：在一般架構重構期間，拒絕重建 ML 流程是成熟且規避風險的決策。保持 ML 範圍凍結可防止計算身分 (computation identity) 發生災難性的遺失。
3. **資料不可變性 (Data Immutability)**：JSON artifact 的 create-only (僅限新增) 寫入政策，配合 SQLite 作為索引，提供了強健的復原選項，並防止意外覆寫歷史。
4. **明確的 UI API 邊界 (Clear API boundaries for UI)**：UI 被嚴格限制只能使用 read-models (讀取模型) 和 commands (命令)，成功切斷了 Qt 框架與業務邏輯的連結。

---

## 審查發現 (FINDINGS)

### 關鍵 (CRITICAL)

#### 1. 應用層的 Factor 對應破壞了領域內聚性
- **受影響組件**：`app_module/adapters/factors` 與 `decision_module/factors`
- **證據**：目標架構第 2 節 (`app_module/adapters/factors`) 與擴充情境檢驗 F (新增 datasource)。
- **為何重要**：量化分析師若要建立新的 factor，必須在 `decision_module` 定義 factor，卻要在 `app_module` 撰寫從資料到 factor 的 mapping。這在物理上拆散了 factor 的定義，以及它如何從真實市場資料推導出來的過程。
- **真實情境**：開發者更新了 factor 的數學定義，卻忘記更新 `app_module/adapters` 中的資料 mapping，導致無聲的邏輯錯誤。
- **建議修正**：將 factor mapping 移至 `decision_module/factors/adapters` 或 `decision_module/market`。領域 (Domain) 應該擁有「如何將市場資料解釋為自身領域概念」的權利。`app_module` 應該只負責提供 `MarketSlice` 或 raw contracts。

#### 2. 遷移步驟 3 和 4 的順序顛倒
- **受影響組件**：`MIGRATION_STRATEGY.md` (步驟 3 與 4)
- **證據**：步驟 3 將 I/O 與 Decision 分離。步驟 4 統一了欄位 mapping 並建立 canonical schema。
- **為何重要**：如果先拆分引擎（步驟 3）卻還沒有 canonical schema（步驟 4），團隊將被迫在新的分離模組之間，使用「舊的、破碎的 DTO」建立大量暫時性的資料轉換層。
- **真實情境**：團隊花了數週為步驟 3 撰寫 adapter 程式碼，結果在步驟 4 導入新的 `RecommendationItem` 和 codec 時，必須將這些程式碼全部丟棄重寫。這會產生開發疲勞，導致步驟 4 永遠無法完成，系統將永久與暫時性的 DTO 糾纏不清。
- **建議修正**：在分離 execution 與 decision 引擎（步驟 3）**之前**，先定義好 canonical contracts 與 codec（步驟 4）。

### 高風險 (HIGH)

#### 3. 極度分層導致簡單的新增卻需要「散彈槍手術」
- **受影響組件**：`decision_module`、`app_module/adapters`、`ui_qt`
- **證據**：擴充情境檢驗 A (`confidence_score`)。文件宣稱跨層有「3-4 個責任點」。
- **為何重要**：為了一個新欄位，開發者必須修改：`decision_module/.../contracts.py`、`decision_module/.../evaluate.py`、`app_module/.../persistence/codec.py`、`ui_qt/.../view.py`。這正是散彈槍手術 (Shotgun Surgery) 的定義。
- **真實情境**：開發者新增了一個 filter 指標，更新了領域和 UI，但忘記更新 persistence codec。系統在記憶體中運作正常，測試也通過了（如果沒有特別檢查 codec），但該欄位在存檔時無聲無息地遺失了。
- **建議修正**：為非索引的可選屬性（例如在 codec 中加入 `extended_attributes: dict`）實作由 schema 驅動的動態處理機制，讓 persistence 層不需要為每一個新的領域標量 (scalar) 更改程式碼，同時在領域層仍保持強型別。

#### 4. 「深度凍結」的錯覺
- **受影響組件**：`app_module/recommendation/contracts.py` (Execution Aggregate)
- **證據**：目標架構第 4 節 (「immediate deep freeze into complete execution」)。
- **為何重要**：Python 原生並不支援深度不可變性 (deep immutability)。標準的 `@dataclass(frozen=True)` 無法凍結內部的 lists 或 dicts。
- **真實情境**：UI presenter 或下游的 portfolio 程序，在執行完畢後於記憶體中修改了 `RecommendationItem.assessments` 列表。因為它沒有真正被深度凍結，存檔的 JSON artifact 現在包含了執行後的 UI 狀態。
- **建議修正**：在 `ARCHITECTURE_INVARIANTS.md` 中，強制規定 execution aggregate 內的所有集合 (collections) 必須使用 `MappingProxyType`、`tuple`，或專門的不可變函式庫 (如 `immutables` 或 `frozendict`)。

### 中風險 (MEDIUM)

#### 5. ML「影子推論」繞道風險
- **受影響組件**：`app_module/adapters/ml` 與 `ml_module`
- **證據**：ML 相容計畫與資料流圖 (Data Flow Diagram)。
- **為何重要**：ML adapter 是在 domain 執行**之後**被呼叫。如果 ML 流程需要的原始資料沒有被 application 準備在 `MarketSlice` 中，ML adapter 勢必會直接從資料庫抓取資料（繞道）。
- **真實情境**：新的 `UpdateService` 以不同方式協調資料，但凍結的 ML feature builder 仍然直接查詢 SQLite DB，並預期舊的資料表更新時間。這會在 `app_module` 資料準備與 ML 影子資料抓取之間引入隱藏的競爭危害 (race condition)。
- **建議修正**：明確定義 ML 流程是由 `RecommendationExecution` context 餵給資料，還是完全自行負責獲取資料。絕對不能允許 ML 在執行中途默默讀取 DB。

#### 6. `app_module` 變成垃圾場
- **受影響組件**：`app_module`
- **證據**：目標架構在 `app_module` 下列出了 10 個子套件，從 `jobs` 到 `persistence` 再到 `composition`。
- **為何重要**：`app_module` 缺乏內聚的主題，淪為「所有不是純數學或 UI 的東西」的集合地。
- **真實情境**：隨著時間推移，`app_module` 會變成新的義大利麵條核心，因為任何需要與兩個不同領域溝通的程式碼，都會被丟進 `app_module/jobs` 或 `app_module/adapters` 中。
- **建議修正**：將 `app_module` 拆分為 `application_module`（業務使用案例：recommendation, portfolio, reporting）與 `infrastructure_module`（基礎建設：adapters, persistence, composition, jobs）。

### 低風險 (LOW)

#### 7. 「應用組合 (Application Composition)」與「Runtime」職責模糊
- **受影響組件**：`app_module/composition` 與 `runtime/`
- **證據**：目標架構第 2 節。兩者都在處理「接線 (wiring)」與「協調 (orchestration)」。
- **為何重要**：開發者會不知道該在哪裡初始化新的 service。
- **真實情境**：新的資料庫連線池在 `runtime/` 被實例化，卻又在 `app_module/composition` 中被注入，導致重複的初始化程式碼。
- **建議修正**：將 `runtime/` 純粹定義為進入點（CLI/Qt bootstrapper），並將 `composition` 定義為 DI container/factory。

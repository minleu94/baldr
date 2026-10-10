# 必要的架構變更 (ARCHITECTURE REQUIRED CHANGES)

> 本文件是最終架構裁決前的審查輸入，不是目前待辦清單。採納、修改或取消的項目以 [FINAL_TARGET_ARCHITECTURE.md](FINAL_TARGET_ARCHITECTURE.md) §2 及其分冊為準；例如草案中搬移 `app_module/adapters/factors` 的方案已被最終裁決取代。下文「現況」是原審查時點觀察，不應當作目前程式狀態。

## 實作前必須修改 (MUST CHANGE BEFORE IMPLEMENTATION)

1. **重新排序遷移策略 (Reorder Migration Strategy)**
   - **現況**：步驟 3 (分離 Domain/IO) 早於步驟 4 (統一欄位 Mapping/Codec)。
   - **必須變更**：將兩者對調。步驟 3 必須是「統一欄位 Mapping 與 Canonical Schema」，步驟 4 必須是「將 Domain 與 I/O 分離」。如果沒有先建立並測試 canonical 資料封裝 (`RecommendationExecution`)，就不可能乾淨地分離執行邏輯。如果硬是先執行步驟 3，將迫使開發者撰寫大量用完即丟的 adapter 邏輯。

2. **重新定位領域資料 Mapping (Relocate Domain Data Mapping)**
   - **現況**：資料到 factor 的 mapping 位於 `app_module/adapters/factors`。
   - **必須變更**：將 mapping 移入 `decision_module`。領域 (Domain) 必須自己定義如何將外部資料轉譯為自身的業務概念。`app_module` 應該只負責提供標準化的 `MarketSlice` 或 raw contracts。

3. **定義深度凍結機制 (Define Deep Freeze Mechanism)**
   - **現況**：含糊地宣稱「deep freeze into complete execution」，卻沒有強制執行的機制。
   - **必須變更**：在 `ARCHITECTURE_INVARIANTS.md` 中，明確規定必須使用的 Python 結構（例如 `tuple`、`MappingProxyType`，或特定的不可變函式庫）。單靠 dataclass 的 `frozen=True` 是不夠的，它會讓下游的 UI/Portfolio 擁有修改能力，進而污染儲存的 JSON 狀態。

## 應該修改 (SHOULD CHANGE)

4. **拆分 `app_module` (Split `app_module`)**
   - **現況**：`app_module` 包含了 use cases、背景 jobs、資料庫 adapters 以及 DI composition。
   - **必須變更**：將其拆分為 `application_module`（業務使用案例：recommendation, portfolio, reporting）與 `infrastructure_module`（adapters, persistence, composition, jobs）。這能釐清業務協調與純粹 I/O 基礎建設之間的邊界，並阻止 `app_module` 變成通用的垃圾場。

5. **非索引欄位的擴充性 (Extensibility for Non-Indexed Fields)**
   - **現況**：新增一個像 `confidence_score` 這樣簡單的欄位，需要明確修改 persistence codec。
   - **必須變更**：在 canonical item 中允許使用強型別的 `extended_attributes` 字典或類似模式，讓 codec 自動將其序列化至 JSON。簡單的領域標量 (domain scalars) 除非需要 SQL 索引，否則不應該要求修改 persistence 層的程式碼。

## 可選的改善 (OPTIONAL IMPROVEMENT)

6. **釐清 ML 資料抓取邊界 (Clarify ML Data Fetching Boundaries)**
   - 確保 ML Adapter 是直接從應用程式的 execution envelope 接收所有必要的上下文，而不是繞過架構，在推論期間內部自行從 SQLite 抓取。如果它在內部抓取，將會在應用程式的資料準備步驟與 ML 抓取之間，產生隱藏的競爭危害 (race condition)。

## 實驗 / 需要程式碼驗證 (EXPERIMENT / NEEDS CODE VALIDATION)

7. **ML 計算 Hash 驗證 (ML Compute Hash Verification)**
   - 在凍結 ML 流程之前，必須執行嚴格的實驗，以驗證將 `UpdateService.calculate_technical_indicators` 移至 `app_module/jobs`，不會意外改變 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 的 hash，或特徵具體化 (feature materialization) 的時間點。

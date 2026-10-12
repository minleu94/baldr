# 目標領域背景與演進導覽

> 本文件說明產品領域的長期方向，以及目前模組如何逐步靠近目標邊界。它不證明目標能力已實作，也不授權新增 target-only package。Current 狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與[目前系統架構](system_architecture.md)；產品優先序看 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)。

## 產品能力方向

目標是用同一套受治理流程，從市場觀察走到候選 Recommendation、Portfolio 與 Position Health，再以 Evidence Review 決定保留、限制、降權或退休。每一步都要保留決策當下可得資料、來源版本、策略與 policy identity。

Investment Advice 與 broker execution 分開；Guided／Professional 共享決策核心，以 policy 與策略資格區隔；Candidate data、research sandbox、historical replay、ML shadow 與 AI 摘要不能直接改動正式決策。

## 狀態語彙

| 標記 | 含義 |
|---|---|
| `CURRENT` | repo 中已有可識別模組或能力；實際完成度仍以 Snapshot／QA 為準。 |
| `REPOSITION` | 現有責任需要在既有模組內重新釐清或建立明確 adapter。 |
| `TRANSITIONAL` | 先沿用現有 package 逐步補上服務、DTO 或 port；不要求立即搬 package。 |
| `TARGET_ONLY` | 理想邊界尚不存在，不得當成已實作。 |
| `CANDIDATE` | 僅能依其明確資格用於 diagnostics 或 shadow。 |

## Current → Target 導覽

| 領域 | Current | Target 方向與限制 |
|---|---|---|
| UI 與 application | `ui_qt/`、`app_module/` 承載九個工作區、use case、DTO 與 service composition。 | 由 application ports／read models 明確組合流程；UI 不持有領域計算。 |
| 市場與 Recommendation | 市場、Regime、Screening 與推薦分散在 `app_module/`、`decision_module/` 及 `data_module/`。 | 以來源可得日、quality 與決策 policy 維持單一資格鏈；`market_module/` 是 target-only 候選。 |
| Advice 與 Portfolio | Advice projection、Portfolio tracking 與 research-only sizing 由既有 application／portfolio 模組承載。 | 共用可解釋、可拒絕的 Advice 契約；`advice_module/` 是 target-only 候選，Portfolio 建議仍須產品 Gate。 |
| Backtest、Evidence 與 Exit | 現有回測、Research Run、Evidence、Position Health 模組提供分層研究與 read models。 | 以可追溯證據決定是否保留或限制能力；Exit 不自動下單或平倉。 |
| Data 與 Runtime | `data_module/`、`runtime/` 與 `app_module/runtime_services/` 處理來源、保存及營運狀態。 | source identity、PIT／available-at、write mode、保存與 recovery 權限維持可核對且彼此隔離。 |
| ML 與研究工具 | `ml_module/`、`development_module/` 與個人研究路徑已有受限制實作。 | Model／feature／label identity、自然成熟 evidence、校準、promotion 與 rollback 各有獨立 gate。 |

具體模組、責任與資料流見[目前架構分冊](current/README.md)。Target 結構中的 `market_module/`、`advice_module/` 等名稱是方向候選，不能僅因本文件出現就建立 package；實作邊界必須符合唯一目標設計。

## 目標實作設計唯一權威

[FINAL_TARGET_ARCHITECTURE](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是 target package、owner、契約、依賴方向、保存模型與遷移順序的唯一實作設計權威。它的五份 FINAL 分冊與 task specs 是設計／執行契約，不是 current 狀態或產品接受證明。

閱讀順序：先看 Snapshot 確認當前狀態，再看 current architecture 判斷實際模組；只有需要設計目標責任、契約或遷移時才進 FINAL。歷史差距基線與日期化評估見 [Archive README](../09_archive/README.md) 及同批文件治理 manifest。

<a id="1011-ml-shadow-layer"></a>
### ML shadow 的領域位置

Recommendation ML shadow、Portfolio Allocation ML 與 Personal H20 是不同資料和權限路徑。此處只描述長期 boundary；目前哪條路徑已接線及其資格看 Snapshot／QA。產品 Roadmap Gate 7 是條件式 Portfolio Allocation ML shadow gate；FINAL 中的 R7 是 UpdateService identity／時序相容實驗，兩者不相同。

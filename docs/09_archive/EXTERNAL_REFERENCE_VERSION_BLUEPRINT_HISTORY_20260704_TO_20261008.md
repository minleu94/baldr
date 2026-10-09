# External Reference Version Blueprint 歷史摘錄（2026-07-04 至 2026-10-08）

> 本頁保存原核心藍圖 §10 的 2026-07-11 Roadmap 審查與 §11 更新記錄。僅移出日期化歷史；外部專案與資料源研究仍見[現行藍圖](../00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md) §§1–9，並未因此宣告重新查核或完成。

目前狀態與優先序請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[6M Engineering Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md) 與 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)。來源區塊範圍、雜湊與處置紀錄見 [Coverage History Entry 158](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-158)。
## 10. 2026-07-11 對當時 Roadmap 的審查結論（歷史）

> 本節保留當日的方向審查與交付次序建議，不作目前狀態或下一步依據；後續優先序已由 Snapshot 與 6M Roadmap 接管。

### Vision

不建議大幅改寫。Vision 應保持 North Star、Evidence Requirement、Gap Register 與非目標；外部專案清單由本文件承接。

### 6M Roadmap

主線仍合理：Evidence-Driven baldr、資料治理、Factor Layer、Daily Decision、Portfolio Feedback。外部參考校準後不需要改方向；V1.8 portfolio sandbox、V1.9 read-only AI 與 Workbench formal read-only source adapter 已完成 v1，後續維持先補 evidence accumulation / manual smoke / multi-day dry-run，再評估 V2.0 Unified Decision Workbench 主 UI 的順序。

### Version Roadmap

V1.1 至 V1.9 已完成的定位不變。已完成的 portfolio sandbox 不等於自動配置建議，read-only AI 不等於 AI 決策。V2.0 前必須先用實際週期證據驗證哪些 evidence summary / dashboard / action item 真正有用。
V2.0 之後的 V2.1-V4.0 只在 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 中維護 maturity milestone，不由本文件直接承諾外部資料源導入或投資有效性。

### Roadmap Hub

2026-07-11 的審查當時建議 Hub 指向本文件，並用「累積 evidence、用 read-only adapter 補 V2.0 前置驗證、V2.0 主 UI 等 evidence 和使用節奏成熟後再評估」作 Next 摘要。這是歷史建議；目前 Hub 只提供權威文件連結，狀態看 Snapshot，工程順序看 6M Roadmap。

---

## 11. 更新記錄

- 2026-10-08：將 2026-07-11 的 Roadmap Hub Next 建議標為歷史，對齊目前 Hub 僅導覽、Snapshot 管狀態、6M Roadmap 管工程順序的分工。
- 2026-07-11：對齊 Post-Refactor Data Source priority；P0 納入 corporate action、trading restriction、三大法人、信用交易、TDCC 與 PIT fundamentals，P1 / P2 依產品可信度重排；所有來源仍 candidate-first，不直接進 `ScoringEngine`。
- 2026-07-08：補上今晚目標已轉為 `V3.0 engineering candidate closeout/readiness report`；score/source readiness 只作工程候選與人工驗證輸入，不代表正式資料 ingestion、ScoringEngine 接線、scheduler approval、V4 readiness 或投資有效性。
- 2026-07-08：補上 supervised ML 採用邊界；sklearn / XGBoost / LightGBM 只可作 V3.3 shadow-only 候選，必須等 V3 score effectiveness audit 可判讀後才進實驗，不取代 rule engine、不直接改推薦。
- 2026-07-08：補上 Phase 3C source candidate readiness 現況；三大法人、信用交易與 TDCC 只完成 candidate-only dry-run，不代表正式資料 ingestion、ScoringEngine 接線或 scheduler approval。
- 2026-07-06：補上 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 的 scoped authority 對照，明確本文件不直接承諾 V2.1-V4.0 外部資料源導入或投資有效性。
- 2026-07-05：重新整理外部專案採用規則與分級；確認只保留公開可讀且 README / docs 足以理解用途與操作方法的專案；`x-qa/stock-screener-service` 因 404 移出 active reference；`PyPortfolioOpt` 改用目前 canonical `PyPortfolio/PyPortfolioOpt`；`OpenBB agents` 降級為 experimental playground 參考。
- 2026-07-06：標記 Workbench formal read-only source adapter 已完成；V2.0 主 UI 仍等待 Phase 0 weekly history / multi-day dry-run / manual workflow evidence，不因 adapter 或 replay 提前解除 gate。
- 2026-07-06：標記 V1.9 Read-only Agent / MCP Evidence Access v1 已完成；V2.0 前置條件改為 evidence accumulation、manual smoke、multi-day dry-run 與真實 workflow 樣本成熟。
- 2026-07-05：補上 Blueprint 衝突檢查，明確寫入 SQLite 不拆檔、不做 async / split DB 改造、暫不導入 GPU / cuFOLIO、不自動交易、不讓 AI 決策。
- 2026-07-04：新增外部專案參考與 V1.5-V2.0 版本藍圖；確認 Vision 不大幅改寫，外部參考由本 companion 承接。

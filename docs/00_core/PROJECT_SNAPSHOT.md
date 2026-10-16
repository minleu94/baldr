# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-15（使用者時區）。本頁只回答現在能用什麼、下一次交什麼、哪些仍受限制。逐輪過程見[具名 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)；重規劃前全文見[歷史快照](../09_archive/PROJECT_SNAPSHOT_20261015_BEFORE_DELIVERY_REPLAN.md)。

## 現在有哪些入口

**目前可試用的回報修正版是 `0f644faa0d48`**，入口為 `output/trial/Baldr-Feedback-Preview-59/Launch-Baldr.cmd`。它使用獨立試用狀態；原 `9fa4518c2aca`、PF 窄版和使用者原狀態仍保留。這不是目前全部開發成果；交付證據見 [Increment59](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment59試用回報固定候選與同版出口)，實際操作見[推薦與研究手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)。

| 使用流程 | 已知可用範圍 | 還要處理什麼 |
|---|---|---|
| 看市場、查個股 | 使用者在 9fa 版確認市場狀態、四股價格／技術頁可用 | 漲跌多數未提供：已找到試用原件缺方向的情況，但不能推定所有資料皆如此；須顯示具體缺欄與來源日期。 |
| 設條件、選股、保存研究 | 0f 版補查詢版本／來源批次／股票篩選步驟及輸入順序修正 | 推薦長頁仍難懂，尚未完成依「選資料 → 設條件 → 看結果」的整體重排；查詢成功不等於易用性通過。 |
| 觀察清單與持倉回訪 | 使用者確認觀察清單可回訪；0f 版持倉表已前移至四張狀態卡下方 | 該版持倉排版驗證使用隔離空白狀態，不冒稱已驗使用者私人持倉。 |
| 單股回測、保存與歷史 | 0f 版兩個原策略的保存／規則／歷史返回及新程序讀回已有限定證據 | 使用者貼文有 6 組完成配對，卻回報畫面像 0 交易；同一 run 的顯示矛盾仍待定位，不能直接判成無交易或改掉 SOP FAIL。 |

原 V1 四條流程與出口維持[計畫 §0.3](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)。以上是已交付及回報狀態，不是全部 P00–P14 或 G0–G4 接受。

## 目前工程狀態與限制

**最新產品程式碼 checkpoint 為 `d8c7d59f`。** Increment60–64 已補保存策略版本明選、新建版本保護、布林基礎與 W 底研究策略的正常執行／保存／歷史／新程序讀回；尚未納入上述固定試用包，也未取得這批變更的 Native／EXE 接受。詳 [Increment60–64 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment64p07w底正常回測與當次訊號保存)。程式碼完成與使用者拿到成果分開記錄。

本次只完成使用者要求的進度重規劃，產品實作維持暫停。恢復後先依[原計畫 §0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)完成下一份日常研究候選，再接資料與其他完整流程；原先直接轉財報 adapter 的下一葉順序已被該節調整。

| 接續順序 | 使用者會拿到的成果 | 目前位置 |
|---|---|---|
| 1. 日常研究修正版 | 選資料、設條件、看結果、保存回訪連貫；回測交易數說清楚；已完成的保存修正進入固定候選 | 已有局部修正與程式碼基礎；推薦頁重排、同 run 矛盾定位、整合 Native／EXE 出口待做。 |
| 2. 有來源的基本面研究 | 讀得到已接受的財報與前期比較，缺件能說明是哪一段，合格新快照可用於日常研究 | 法人、注意公告有具名限定進展；財報 capture／parser／正常 reader 仍有斷點，Increment65 只有靜態筆記。 |
| 3. 持倉情境、策略比較及後續完整能力 | 先完成同帳本的研究情境，再完成兩策略的獨立結果與比較；後續接其餘方法及成熟結果 | 部分保存／讀回已有證據，完整現金／行情／健康來源、雙策略全期間績效與自然成熟仍各自待驗。 |

外部缺件只隔離受影響用途：TPEx 年度日曆授權不等於 TPEx 法人 OpenAPI 的授權狀態；MOPS 文件 partial／缺 EOF、月營收與 TWSE 舊 GET 額度、單位版本、歷史 PIT 和完整真 N 繼續各自追蹤。首次成功保存後的合格新快照按已決定的台北小時政策供前瞻研究；不得倒填歷史可得性。原 P01 效能 FAIL、原 Native FAIL、Paper／Forward 未成熟與已停用 maintainer 仍保留，詳[原 QA](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)、[資料政策 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)及[排程指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

## 產品與系統入口

- **進度與交付**：[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保留；不以 Increment 或測試數量計算完成率。
- **產品方向與來源優先序**：[Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)；正式 Gate 依賴見[六個月工程路線](ROADMAP_6M_ENGINEERING.md)，不以本輪交付排序改寫 Gate。
- **實際操作**：[APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)；首次設定看[快速開始](../07_guides/QUICK_START.md)，移機看[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。
- **現行與目標架構**：[system_architecture](../01_architecture/system_architecture.md)／[current 分冊](../01_architecture/current/README.md)；[FINAL](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標設計，不作已實作證據。
- **主程式與資料**：`ui_qt/main.py`，九個頂層工作區；資料位置由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `DATA_ROOT=D:/Min/Python/Project/FA_Data`，不能以 repo 相對路徑推定正式資料位置。

## 重要限制

- 正式資料寫入、全量回補、正式 Task／maintainer 變更、push、發布與交易沒有新增授權；私人資產與其他 owner 變更受保護。
- 金融精度、決策當下可得性、來源用途、原 FAIL 與各 Gate 門檻維持；缺值與未知不能補零。
- Historical replay、readiness、dry-run、shadow、Paper、合成資料或測試通過，均不能代替真來源、有效績效、真人接受、自然成熟或 production ML 資格。程式碼／EXE 可啟動也不授上述接受；UI 的既有 mypy ignore 設定不證強型別。
- Root 串行 QA 與資源守衛依[共用規則](../agents/shared_context.md)。本補完 task 已用完新建代理額度 10/10；只在無待寫與無衝突時重用既有 Luna。

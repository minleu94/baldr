# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-15（使用者時區）。本頁只回答現在能用什麼、下一次交什麼、哪些仍受限制。逐輪過程見[具名 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)；重規劃前全文見[歷史快照](../09_archive/PROJECT_SNAPSHOT_20261015_BEFORE_DELIVERY_REPLAN.md)。

## 現在有哪些入口

**目前可試用的日常研究修正版是 `ec5c95733608`**，入口為 `output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd`，步驟、固定身份與限制見同目錄 `TRIAL_GUIDE.md`、`KNOWN_ISSUES.md`、`DELIVERY_RECEIPT.json`。這是獨立隔離狀態；原 `9fa4518c2aca`、`4b530`、`0f644faa0d48` 試用包與使用者原狀態保留。來源與同版 EXE 的 Windows Main／新程序旅程已限定驗證，尚待使用者真人試用；詳 [Increment66](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)。

| 使用流程 | 已知可用範圍 | 還要處理什麼 |
|---|---|---|
| 看市場、查個股 | 使用者在 9fa 版確認市場狀態、四股價格／技術頁可用；新隔離價庫四股末日的漲跌方向經同股同日精確核對後可讀 | 僅四股行情子集，截至 2026-09-23；仍有 977 列缺明確方向，保持未提供。 |
| 設條件、選股、保存研究 | ec5 版把價格選股設為預設子頁；來源摘要在首屏，四股篩選、兩股比較、收藏及新程序回訪已限定驗證 | 只有一份四股技術封存可嚴格核驗，且依賴原本機絕對路徑；真人易用性待回報。 |
| 觀察清單與持倉回訪 | 觀察清單新程序讀回已驗；持倉表位於四張狀態卡下方，兩筆隔離測試持倉可見 | 新試用狀態沒有搬入使用者真帳；私人資料效果仍待真人試用。 |
| 單股回測、保存與歷史 | ec5 版兩個原 `1.0.0` 策略的保存、同 run 歷史、返回及新程序讀回已限定驗證，摘要分列完成配對／成交／明細／期末持股 | 使用者貼文的六配對原 run 未取得；SOP 樣本不足、Baseline FAIL、未做 Walk-forward 均未改判。 |

原 V1 四條流程與出口維持[計畫 §0.3](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)。以上是已交付及回報狀態，不是全部 P00–P14 或 G0–G4 接受。

## 目前工程狀態與限制

**固定產品來源 commit 為 `ec5c9573360891595bb395fa7bbb934077c6d4c0`。** Increment60–64 的保存版本、布林基礎與 W 底程式碼已納入這份來源／EXE；但本次 Native／EXE 驗證只接受指定日常研究和兩個原 `1.0.0` 單股策略，不把其餘家族視為已交付能力。詳 [Increment60–64 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment64p07w底正常回測與當次訊號保存)。

依[原計畫 §0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)，第一列「日常研究修正版」已形成固定可試用候選。受改測試、共同 UI 防線、兩筆隔離持倉、來源與 EXE 的正常 Main／新程序及同版檢查已限定通過；EXE SHA-256 為 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`。交付收據最初記錄 SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2`，目前檔案 SHA-256 為 `16bb4f511e5ecb21dff6667a5a38fa7aa73d298bf951ea69c0ce85b42e128eb1`；原因未裁決，兩者不混稱同一位元原件，詳[Increment67 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment67p08-推薦回放通用比較的金融判讀阻斷)。這只關閉本列工程交付出口，真人試用及完整產品 Gate 仍待。

| 接續順序 | 使用者會拿到的成果 | 目前位置 |
|---|---|---|
| 1. 日常研究修正版 | 選資料、設條件、看結果、保存回訪連貫；回測交易數說清楚 | 固定 `ec5c95733608` 本機候選已交，正常 Main／新程序、兩筆隔離持倉與同版 Native／EXE 限定通過；真人試用與原 Gate 未通過。 |
| 2. 有來源的基本面研究 | 讀得到已接受的財報與前期比較，缺件能說明是哪一段，合格新快照可用於日常研究 | 法人、注意公告有具名限定進展；財報 capture／parser／正常 reader 仍有斷點，Increment65 只有靜態筆記。 |
| 3. 持倉情境、策略比較及後續完整能力 | 先完成同帳本的研究情境，再完成兩策略的獨立結果與比較；後續接其餘方法及成熟結果 | 開發來源已阻擋推薦回放的通用錯誤績效顯示；策略 Paper 帳同日 Health 收據的初次情境已沿正常 Main→新程序完成保存／重開／返回。真私人帳、未持有候選、雙策略全期間績效與自然成熟仍各自待驗。 |

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

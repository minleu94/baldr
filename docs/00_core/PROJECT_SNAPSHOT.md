# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-15（使用者時區）。本頁只回答現在能用什麼、下一次交什麼、哪些仍受限制。逐輪過程見[具名 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)；重規劃前全文見[歷史快照](../09_archive/PROJECT_SNAPSHOT_20261015_BEFORE_DELIVERY_REPLAN.md)。

## 現在有哪些入口

**最新另交的本機試用候選為日常研究 71（`f9b4e7d12149`）**，入口是 `output/trial/Baldr-Daily-Research-71/Launch-Baldr.cmd`。依 [Increment71 原 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正)的 QA456／458，同版 EXE 已限定驗證價格選股、同源比較／收藏、持倉訊號接線至一般個股價量，以及兩個原 `1.0.0` 策略的保存、歷史與新程序返回；真滑鼠雙擊、真私人帳與完整 Gate 仍待。完整身份、操作與限制由[試用版指南](../07_guides/TRIAL_VERSION_GUIDE.md)連到包內原件。

原 `ec5c95733608` 日常研究66、`9fa4518c2aca`、`4b530`、`0f644faa0d48` 與各自狀態仍保留，不接續或覆寫。使用者在66回報的價格單列／收藏、手動持倉下鑽及回測版面問題，是71修正的來源；原66指南 D 把獨立價格研究視窗誤寫成主個股頁，其勘誤仍保留。71的有限工程驗證不代替新版真人接受；後續 Increment72 舊歷史缺件判讀仍只在開發來源，未納入固定71 EXE。

| 使用流程 | 已知可用範圍 | 還要處理什麼 |
|---|---|---|
| 看市場、查個股 | 使用者在 9fa 版確認市場狀態、四股價格／技術頁可用；新隔離價庫四股末日的漲跌方向經同股同日精確核對後可讀 | 僅四股行情子集，截至 2026-09-23；仍有 977 列缺明確方向，保持未提供。 |
| 設條件、選股、保存研究 | 71 候選可在同一已核來源清除篩選、分列處理數／符合數，限定 EXE 旅程已驗四股、兩股比較、單股收藏與回訪 | 66 的真人單列回報與當次 UI 條件未知仍保留；71 新版真人操作及完整 Gate 待驗。 |
| 觀察清單與持倉回訪 | 71 候選加入唯一精確代號／名稱互補；限定 EXE 已驗持倉表訊號至一般個股價量及重新載入 | 真滑鼠雙擊手勢及真帳效果待驗；保存來源持倉仍沿原 exact 守衛，不改來源或帳本。 |
| 單股回測、保存與歷史 | 71 候選限定驗兩個原 `1.0.0` 策略的保存、規則卡、同 run 歷史、返回與 fresh；設定／結果版面及選用查找已調整 | 使用者六配對原 run 未取得；72 舊歷史缺值／空表修正未打入71。原 SOP FAIL／Baseline FAIL／未做 Walk-forward 未改判。 |

原 V1 四條流程與出口維持[計畫 §0.3](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)。以上是已交付及回報狀態，不是全部 P00–P14 或 G0–G4 接受。

## 目前工程狀態與限制


**目前71固定候選來源為 `f9b4e7d1214967f86d9ae90b1e462bde11b73f3f`；後續工作樹不會改變該 EXE。** 原66來源為 `ec5c9573360891595bb395fa7bbb934077c6d4c0`。 Increment60–64 的保存版本、布林基礎與 W 底程式碼已納入這份來源／EXE；但本次 Native／EXE 驗證只接受指定日常研究和兩個原 `1.0.0` 單股策略，不把其餘家族視為已交付能力。詳 [Increment60–64 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment64p07w底正常回測與當次訊號保存)。

原66候選的交付歷史：依[原計畫 §0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)，第一列「日常研究修正版」已形成固定可試用候選。受改測試、共同 UI 防線、兩筆隔離持倉、來源與 EXE 的正常 Main／新程序及同版檢查已限定通過；EXE SHA-256 為 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`。交付收據最初記錄 SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2`，目前檔案 SHA-256 為 `16bb4f511e5ecb21dff6667a5a38fa7aa73d298bf951ea69c0ce85b42e128eb1`；原因未裁決，兩者不混稱同一位元原件，詳[Increment67 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment67p08-推薦回放通用比較的金融判讀阻斷)。這只關閉本列工程交付出口，真人試用及完整產品 Gate 仍待。

| 接續順序 | 使用者會拿到的成果 | 目前位置 |
|---|---|---|
| 1. 日常研究修正版 | 選資料、設條件、看結果、保存回訪連貫；回測交易數說清楚 | 71 固定候選已另交，具名同版 EXE／fresh 的有限工程驗證見 Increment71；新版真人手勢／真帳及完整 Gate 待驗。72 舊歷史判讀修正在開發來源；66 原真人 A／B／C／E 回報與 D 問題保留。 |
| 2. 有來源的基本面研究 | 讀得到已接受的財報與前期比較，缺件能說明是哪一段，合格新快照可用於日常研究 | 法人、注意公告有具名限定進展；財報 capture／parser／正常 reader 仍有斷點，Increment65 只有靜態筆記。 |
| 3. 持倉情境、策略比較及後續完整能力 | 先完成同帳本的研究情境，再完成兩策略的獨立結果與比較；後續接其餘方法及成熟結果 | 開發來源已阻擋推薦回放的通用錯誤績效顯示；策略 Paper 帳同日 Health 收據的初次情境已沿正常 Main→新程序完成保存／重開／返回。兩個基本策略可在隔離來源各自保存後，沿 Registry 只讀對照原指標、開各自明細並返回，且新程序可重開；資格仍不可評。真私人帳、未持有候選、來源／成本權威、歷史 PIT、完整雙策略績效與自然成熟仍各自待驗。 |

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

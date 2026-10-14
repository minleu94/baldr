# 任務上下文與文件治理增量驗收（2026-10-13）

## 範圍與來源

本輪起始 `dev`／`fbbc314b3197a3764e749eb1c7daece5f95394ff`，Git 工作樹與 index 乾淨。只改善導航／Feature Map／既有 document_control；不改產品、正式資料、排程、Snapshot 或他人 WIP。Context 是動態任務視圖，不增加索引資料庫。原件與固定 Manifest、root Graphify 保持。

## 固定五題與驗收方法

五題是 Daily Decision Desk UI 定位、P01 篩選 Bug、Recommendation／ML 接受資格、DecisionDesk DTO 同步影響、目前阻礙與 QA。修改前固定來源摘錄已存於 `output/tasks/doc-governance-context-20261013-01a137c6/root/before.json` 及五份 `before_*.txt`；每份有原始 path／line ranges／source SHA。LF 正規化，字元／UTF-8 bytes 實測；Token 粗估為 ceil(bytes/3)，不是 tokenizer 或人工時間。

修改後由同一 root 腳本使用 `context --domain <領域> --level 3 --format text` 的相同函式與 formatter 回放；UI／Bug／ML／API／現況分別使用 `ui`／`bug`／`ml_model`／`architecture_refactor`／`documentation_qa`。各題的 JSON／文字保留為 `after_<題>.json/txt`，實際 CLI 的 text formatter 另有回歸測試。`after.json` 保存路徑、selector、行號、完整輸出量與未知，`trace.json` 保存程式查證矩陣；兩份治理 metadata 的版本另列，未把完整 JSON 送入模型。

| 固定任務 | 摘錄來源檔數 前→後 | 來源字元 前→後 | 來源 UTF-8 bytes 前→後 | 前粗估 Token→後來源粗估／完整包粗估 | 後完整包 bytes |
|---|---:|---:|---:|---:|---:|
| UI：Daily Decision Desk | 8→10 | 6836→2711 | 8958→4235 | 2986→1412／2884 | 8650 |
| Bug：P01 filter／根因界線 | 4→6 | 5848→4005 | 9284→6069 | 3095→2023／3149 | 9446 |
| Recommendation／ML資格 | 5→12 | 8910→6145 | 12806→8559 | 4269→2853／5131 | 15391 |
| DecisionDesk DTO文件影響 | 9→6 | 16835→3150 | 23667→5002 | 7889→1668／3050 | 9150 |
| 現況阻礙與QA | 5→8 | 11485→6217 | 19117→10761 | 6373→3587／5031 | 15093 |

後測每題還由工具讀取兩份 metadata，實際不同來源總數分別為12／8／14／8／10；上表檔數只計進入模型摘錄的文件／程式／測試，沒有把機械讀取藏成少讀。前測是已保存的固定人工導航摘錄回放，不是使用者歷史 telemetry；後測完整包多含hash／未知／三lane程式與測試候選。來源摘錄均縮小，但含包裝後只有UI／API／現況三題縮小，Bug及ML增加，不宣稱每題Token或時間都改善。

Root已核五題的必要結論：Decision Desk位於市場探索index0且唯讀；P01原385.9978ms及strict300ms失敗保持、原因不推定；ML三lane分開且local／shadow不授promotion；DTO能找到宣告欄位、契約／測試及6份同步核對文件；現況保留Main FAIL與P08a來源過期／等owner交接／重建lineage。五題均定位到正確文件、程式與測試入口，無budget略過或失效selector回退。舊歷史敘述仍按日期讀，QA不當成現況authority。

## Document-to-Code Verification Matrix

以下是本輪AST／來源及文件邊界查證；測試檔存在不等於本輪執行該產品測試。完整source hash／HEAD blob／簽名／tests／evidence在 `root/trace.json`，用 `document_control trace --inspect-file <path> --symbol <symbol>` 可重建。

| 文件／章節 | 程式／symbol | 代表性測試 | 本輪結論與界線 |
|---|---|---|---|
| Manual §8；UI README 頂層工作區 | `ui_qt/main.py` index0接線；`ui_qt/views/decision_desk_view.py::DecisionDeskView.__init__` | `test_ui_qt_decision_desk_main_integration.py`／`test_decision_desk_dto_contract.py` | 接線／名稱／簽名存在；工作台舊映射移回市場探索，跨工作區Main另有shell關聯；未執行UI驗收 |
| Current application/workspaces §入口與分層、工作區責任 | `app_module/decision_desk_dtos.py::DecisionDeskSnapshot` | `tests/test_decision_desk_dto_contract.py` | 欄位宣告可查，時間／quality／warnings／source_lineage存在；文件未逐參數列Schema，未證明序列化行為完全相等 |
| Snapshot P01；completion QA §Root16完整核驗 | `app_module/daily_market_technical_universe_v4_query.py::DailyMarketTechnicalUniverseV4ReadSession.read_page` | `test_daily_market_technical_universe_v4_read_session.py` | 靜態回傳V4Page、query/cancel契約可查；不是當版效能或Main PASS |
| Current decision/research §Evidence與模型權限；6M Gate7 | `ml_module/recommendation_calibration_authority.py::RecommendationPromotionPolicy`、`ml_module/allocation_training_service.py`、`app_module/recommendation/personal_h20_read_session.py::PersonalH20ReadSession` | Recommendation calibration／allocation shadow／H20 read session | 三lane程式入口存在；purge、完整母體、兩cutoff等契約有來源；沒有本輪promotion／natural maturity接受 |
| Current Recommendation與Decision | `app_module/recommendation/contracts.py::RecommendationExecution`、public DTO exports/advice DTO | recommendation contracts／DTO roundtrip | 補public facade文件影響路徑；Target FINAL不作current實作證明 |
| G10 issue resolution；資料架構讀寫契約 | `scripts/scheduled/run_daily_data_update_quick.py::_calendar_for_run`、`scripts/update_phase3c_candidates.py` | scheduled update runner／phase3c backfill runner | 補腳本／測試change patterns；Quick76／CLI40是原10/12收據，不是本輪新跑，自然no-data仍unknown |

Root另讀兩份既有P01原receipt，SHA與正文所引 `f62576aa…`／`a6cae2bb…`相等；僅核保存身份，沒有重跑90份DTO、矩陣、產品import或取得正式Gate。原始receipt與查證結果列在 `root/after.json`。

## 治理改變與狀態責任

擴充原 `document_control.py`，其helper無獨立CLI／DB；保留route／init-task／check／bootstrap與auto_state_sync。新增context／trace／inventory／issues及metadata檢查，task初始化補read_files／inspection_scope。Feature Map增10閱讀領域、精確UI／DTO／ML／腳本測試路徑及shared shell。導航只加AGENTS、PROJECT_NAVIGATION、Index與Coverage指引，README／docs README已有合適入口而保留。流程正文集中於Product Change Workflow。

Snapshot／Product／6M／Current／Target／QA各自責任保持；沒有實質產品狀態改變便不重寫Snapshot。G01–G10沿原ID追蹤resolved scope／external unknown、owner null／來源日期commit／blocking／criteria，G07目前恢復回Snapshot，不引用舊pause覆蓋。G01/02/03/04/05/08/10外部證據界線保持，G06/G07已解，G09非blocker且與排程G9不同。source_commit是觀測來源，不代表接受產品的commit。

`inventory --base fbbc314b3197a3764e749eb1c7daece5f95394ff --details` 可取得現行Git tree/delta；新untracked文件先在工作樹欄列，commit後進HEAD。路徑分類是機械候選，不是全庫語意／EOF審核。本輪保存57份產品化原件＋歷史Manifest＋root graph共59份SHA，全部未變。

## QA、資源與保留失敗

Raw evidence統一在 `output/tasks/doc-governance-context-20261013-01a137c6/root/`，不得stage。Root沿既有8GiB／12程序、suspended assign、kill-on-close、同repo mutex守衛序列執行；成功組自然Job0、handles關閉／mutex釋放、無forced cleanup。

| 檢查 | 結果 | 命令／證據 |
|---|---|---|
| 治理回歸與反例 | PASS，73 passed | `python -m pytest tests/test_document_context.py tests/test_document_control.py tests/test_auto_state_task_json.py -q -o addopts= --basetemp <本任務唯一暫存>`；`root/pytest.stdout.txt` |
| Compile | PASS | `python -m py_compile scripts/document_control.py scripts/document_context.py tests/test_document_context.py` |
| Scoped mypy | PASS，3 files | `python -m mypy scripts/document_control.py scripts/document_context.py tests/test_document_context.py --follow-imports=silent --explicit-package-bases` |
| 12 features／10 domains／10 issues／6個導航來源 | PASS | `document_control check --context-metadata --path <本輪導航文件>`；`root/cli_metadata.stdout.txt` |
| 五題／inventory／trace／保護原件 | PASS | `root/after.json`、`inventory.json`、`trace.json`；全部無新增失效selector／budget略過 |
| Diff whitespace | PASS | `git diff --check`；Git既有CRLF warning保留，不改設定 |
| Graphify當前圖重建／AST再驗 | NOT_RUN | 舊收據固定5eba9bc3、1518docs／1087production Python／8308 unresolved AST；與本輪來源不同，只核範圍和root graph SHA不變，不覆寫圖 |
| UI／完整產品／正式資料／自然排程／promotion | NOT_REQUIRED於本治理變更；未執行 | 無產品邏輯或UI變更，不以73治理測試升格產品資格 |

最後完整QA outer：`root/single_owned_qa_77f1c4ef1049418d851b4d36b20e8aaf/receipt.json`，SHA `1c4f02de4255ef0c92585bb74cd13600826da94876ff6c2defe34b5bef24e588`；命令與tested source pins在 `root/quality.json`。staged交付另外核對Git正規化bytes，不把CRLF換行當成語意漂移。

失敗均保存：初始local guard使用不存在的CREATE_SUSPENDED符號，child未啟動，修local copy literal後通過；sandbox暫存權限造成50pass／1fail／13errors，專屬fixture在原守衛下重跑；root量測helper的import入口與一個失效selector曾拒絕；mypy首次namespace參數不完整、其後兩個缺annotation均修正。原receipt在各 `single_owned_qa_*`，不改寫為PASS。Luna靜態review發現symlink／metadata版本／trace競態／selector拒讀／Windows分隔符缺口，Root修復並增加反例。沒有UAC、放寬斷言或skip失敗case。

## 交付與限制

本輪新建Luna Max兩位，同時最多兩位，無孫代理／worker QA／worker commit；Luna A完成導航／基線及一次重派，Luna B完成映射／issue及兩次重派。Root裁決、修改共同入口與工具、親自讀diff／五題關鍵來源及QA結果。

限定本輪文件與程式查證，不宣稱1,400+全文重讀、全repo links零錯、完整產品或所有API語意已驗。metadata／path分類和AST簽名只能定位；具名receipt須核其source/data/run／環境，不由PASS字樣推定現在版本。owner、自然no-data、host triggers、完整歷史接受及正式ML資格缺證仍待。

安全scoped commit由Root在index與tested bytes一致、link／Coverage／task檢查後建立；本頁不內嵌自身未生成的commit SHA，確切交付SHA見Git log與最終回覆。只納入本輪11檔，未push；raw outputs與歷史原件保留。

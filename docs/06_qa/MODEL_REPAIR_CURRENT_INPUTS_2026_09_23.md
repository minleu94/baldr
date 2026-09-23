# 修訂模型的當日研究輸入

本輪以隔離分支實作當日研究入口；完整模型重訓與驗收完成前，不代表日常模型已切換。

## 實作與回滾範圍

| 路徑 | 變更 | 回滾方式 | 限制 |
|---|---|---|---|
| `ml_module/restated_research_input_contract.py` | 新增不可變的推論來源綁定 | 回退本提交 | 不讀資料、不改訓練 artifact |
| `data_module/ml_restatement_current_inputs.py` | 從封存 Parquet 讀取當日指定股票 | 回退本提交 | 原來源唯讀，只驗證實際消費的分片 |
| `data_module/ml_restatement_current_capture.py`、dataset 的 `build_restated_feature_values` | 在唯讀 transaction 取得新前綴，共用既有 62 欄計算 | 回退本提交；保留封存輸入 | 不改全量 build 正在執行的隔離分支或舊 manifest |
| `app_module/restated_allocation_shadow_service.py`、`scripts/run_ml_allocation_restated_shadow.py` | 當日研究推論與結果封存 | 回退本提交；保留已產出結果 | 不建立排程、不改正式指標或 pointer |
| `app_module/ml_allocation_inference_service.py`、`app_module/allocation_release_adapter.py` | 明確研究入口接受獨立輸入身分 | 回退本提交 | 未提供新綁定時保持原比較與 audit 格式 |

回滾前先核對工作區與其他重構 owner，僅回退此功能提交；不清理來源、模型、資料集或其他 agent 檔案。回滾後驗證 release adapter／inference 回歸測試。新入口的既有研究結果保留作追溯，不回寫舊格式。

## 時點與精度自查

- 只讀明確指定且 hash 相符的完整研究資料集；決策日須等於實際 capture 的臺北日期。
- 股票／市場特徵事件均在當日前；修訂實際觀測時間不可晚於 capture，不追認歷史 PIT。
- 特徵固定 62 欄的順序、尺度、整數值與明確缺值；不讀取 outcome 或配置 targets。
- 新來源身分與 training 身分分別留在 audit；原模型來源／artifact hash 不改寫。
- 只有明示的修訂研究 release 可接受新來源綁定；正常 daily 08:30 路徑仍要求原身分一致。
- 原模型隔離、正式 OOS／alpha／交易限制均保留；研究入口不推導投資配置建議。

## 驗證

隔離 integration 分支執行 current provider／research binding／既有 inference／release adapter 測試，共 **33 passed**（一則既有 joblib 實體核心數查詢警告）。案例涵蓋真零與缺值、指定股票、來源篡改、缺當日列、未到可得時間、輸入準備後變更、來源身分分離與正式／舊 profile 拒絕新綁定。

合入僅供新研究 profile 使用的 fit-row commitment parser 後，lineage／binding／原 inference／adapter focused tests 共 **34 passed**；兩項既有量化靜態 guard 通過。新增四個入口／contract 檔案以 `mypy --follow-imports=silent` 檢查無錯，`py_compile` 通過。上述靜態 guard 不取代實際資料與時點驗證。

真實 v3 六股票樣本的 current provider 已獨立讀取 **1256／1477**，完成 release loader 和模型推論。模型為 `restated-repair-185dd789084a9adb`（2,697 列樣本、帶 fit cap，僅用於接線驗證）；特徵日為 **2026-09-22**，實際 capture 為 **2026-09-23T12:31:54.306367+08:00**。入口只解碼當年分片中的當日指定列，沒有載入完整訓練陣列；該樣本命令含 Python 啟動共 2.45 秒，不能外推全市場效能。

不可變結果位於 integration worktree 的 `output/qa/model_repair_review/current_shadow_v3/current_shadow/73be42807d618ba29a3ff762596c427576d1eebfb1cce4e9407f81b7955f3279.json`，body SHA-256 為 `73be42807d618ba29a3ff762596c427576d1eebfb1cce4e9407f81b7955f3279`。結果仍為 `formal_oos_allowed=false`、`production_blend_alpha_bp=0`；全量資料與最終模型仍在建立，不能由此樣本判定修復完成。

## 新的當日輸入擷取

SQLite 以 `mode=ro`、`query_only` 與單一 read transaction 讀取，不使用會忽略 WAL 的 immutable 模式。只消費實際臺北當日以前的完整股票／市場前綴，對修訂 receipt 涵蓋的指定股票逐欄核對修正後價格。計算使用純函式抽取前的相同公式；新 producer 記錄自己的 code hash，沒有更改已啟動全量 build 的 source 或資料身分。

新輸入保存精確消費的 gzip 原始前綴、Parquet、來源及程式 SHA-256 與真正觀測時間。訓練資料身分與新輸入身分各自驗證；不讀 outcome、不建立新 teacher，配置狀態仍為中性的全部現金研究狀態。這不是使用者實際庫存，也不是歷史 PIT。來源超過七日會拒絕，但此檢查不等於官方交易日曆完整性保證。

實際 run02 snapshot 對 **13 檔**（1101、1216、1256、1301、1477、2002、2303、2317、2330、2412、2454、2881、6505）完成新輸入擷取與既有樣本模型推論。特徵日 2026-09-22，capture 為 **2026-09-23T12:41:11.997312+08:00**；含 Python 啟動共 **5.07 秒**，不外推全市場效能。全部 13 檔都核對本次 5/20 receipt；1256、1477 的 62 個值、缺值 mask 與股票／市場事件日，逐欄對照獨立封存的 v3 樣本完全一致。

- 新資料身分：`sha256:425942d267b09569b744204d2d64b3ca8e454e7cc06edcaeb63d6ec9fb1f9798`。
- 原訓練資料身分：`sha256:94eb3665394b6a0565b97c58c07c55575eb9ff22123d592060e0127f9ac93734`，沒有改寫。
- 結果 body SHA-256：`febb72d88cf0e4b58a06954781005f3f70448f3edbfa15e30c7d72accc4d37f8`；位於 integration worktree 的 `output/qa/model_repair_review/current_capture_run01/current_shadow/`，同一 run 另有 `parity_summary.json`。

current capture／provider／dataset focused tests **15 passed**，涵蓋來源 DB bytes 不變、未來價格不進入前綴與修正遺失時拒絕；加上研究 binding 回歸共 **22 passed**（一則既有 joblib 實體核心數查詢警告）。新增 capture 與 CLI 的 mypy、py_compile、兩項量化靜態 guard 均通過。此 run 仍使用帶 fit cap 的六檔樣本模型，僅證明資料與推論接線；三項正式權限維持 false、alpha 維持 0。

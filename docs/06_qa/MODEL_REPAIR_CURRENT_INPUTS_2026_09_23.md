# 修訂模型的當日研究輸入

本輪以隔離分支實作當日研究入口；股票修訂 v2 兩家族均完成讀回，追加官方市場 v3 目前完成 bounded 的新模型推論，全量 H5 v3 尚待新資料與 fit。品質驗收未通過，日常正式模型沒有切換。下方 v2 與六股票樣本保留為較早的接線紀錄。

## 官方市場 v3 的 bounded 最新輸入

正式 SQLite 僅以新 read transaction 讀取股票前綴，大盤改讀核驗後的官方月報。實際 capture 為 `2026-09-23T16:48:42.586694+08:00`、特徵日 9/22，13 檔 × 24 experts 共 312 組預測成功，neutral fallback=0；所有 experts 的產業超額報酬 head 均保持 missing，沒有補成 0。這項缺值與預測品質限制均保留，不能把有輸出當作可正式投資。

模型 SHA `2a1223e06563098f08c8d57e85ec71c2c61399621987b3f09c9ac1d3b1081ae9`，current receipt file SHA `9355d7683d6fd7bd081eca0b607f94d30a1c0fd0ddbccf8e45abcd913e4429c8`，路徑為 `E:/codex_model_repair_20260923/current_inference/bounded_official_v3_run01/bounded_current_heads/cb6fea7fad1dab2df9261ea640e32d41fadb6b841eafb986810765d332b5019f.json`。輸入 identity 與訓練 identity 分開，正式權限均 false、alpha=0、無配置 proposal。app wrappers 及底層研究 inference 皆驗證官方市場契約，拒絕舊混合來源；新月份可用新封存清冊，原資料與模型不覆寫。完整來源與 hashes 見[大盤來源核對](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)。

## 全量 H5 模型的最新資料讀回

使用完整 release `restated-repair-5a4ece1426e70aa3`，從 run02 唯讀擷取 **13 檔**（1101、1216、1256、1301、1477、2002、2303、2317、2330、2412、2454、2881、6505）。實際 capture 為 **2026-09-23T15:41:55.101579+08:00**，特徵日期 **2026-09-22**；本次 CLI 含 Python 啟動共 **3.52 秒**，不外推全市場效能。

Root 逐項讀回 **39 個 base expert outputs**，無 neutral fallback；sector-excess head 因原標籤缺失保留 missing，其餘八頭有整數輸出，機率與 rank 均在 0–10,000 bp。來源有部分特徵缺失，結果明確保留缺失 family、coverage **8,310 bp** 與原因；沒有把 partial coverage 說成完整來源。Cash-only meta 未學習配置。這只驗證實際推論接線，不代表品質達標，尤其[新發現的大盤來源問題](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)尚待處理。

- 輸出：`E:/codex_model_repair_20260923/current_inference/full_h5_run01/current_shadow/ee61df09009ab235c5538ccf3b5b46feec3a7628759cc7f66f6f936148ccb2ca.json`。
- Body SHA-256：`ee61df09009ab235c5538ccf3b5b46feec3a7628759cc7f66f6f936148ccb2ca`；file SHA-256：`c182370aca354d8c48faddfa5314b65bd7f0e619bff84ee65f8be968368512ed`。
- 新 capture dataset identity：`sha256:bdea335057337adb8d7cb19521f63ac0e77cec56fdf5bdfc5439f8520039253e`；訓練身分仍為 `sha256:5b7c0979da1a3b1a967297deca8e88564217a260306c97f0a964a8e1922de3ea`，兩者獨立綁定。
- Root QA：integration `output/qa/model_repair_review/full_h5_current_heads_readback.json`；正式 OOS／production action／broker order 為 false、alpha=0，原 pointer 未變。

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

### 交叉複核後補正

獨立檢視發現 CLI 原先在擷取後才由 service 檢查 release 輸出目錄；現已提前共用檢查，連 `input_captures/` 或 `current_shadow/` 指向來源內的情況也拒絕。新 current-input provider 另外核對 gzip 原始前綴的 bytes SHA、manifest provenance 和逐列 lineage，讀取完成後再核 SHA；不能只靠 Parquet 仍一致就忽略其原始前綴已變更。

新增來源前綴遭改動與兩種受保護輸出路徑的反例，current capture／provider 共 **12 passed**；四個 current source 檔 mypy 無錯。新 four-horizon ridge/logistic 樣本 release `restated-repair-a119146c1eb75553` 另用新的 **13 檔** current capture 完成實際推論：capture `2026-09-23T12:53:15.238323+08:00`、特徵日 9/22，結果 body SHA-256 `89426715c6c979bd2c7282790172911cfb6f54dd1f7120d6882b949fdc2edde6`，位於 `output/qa/model_repair_review/current_capture_four_horizon_run01/current_shadow/`。這是候選模型接線驗證，仍不代表完整 bounded family 或全市場模型已修復。

Root 另以不匯入 trainer 或模型的本機 QA 腳本，使用 Python 整數與 Decimal 驗算該 release 的 **12 份 heldout Parquet、456 個統計數值**（模型／train-only naive 的 MAE、RMSE、Brier、正例率、門檻正確率，以及 calibrated Brier），全部與封存報告一致。亦核對 receipt SHA、列數、日期、唯一 row key、naive 常數、機率範圍及校準 mapping 單調性；未在此步重播模型、驗算 ECE 分箱或重建 labels。結果 `output/qa/model_repair_review/four_horizon_sample_independent_metrics.json` 綁定 verifier 檔案 SHA；確認數值報告正確並不改變樣本表現弱於基準的結論。

## 完整 v2 與原 bounded 家族的當日入口

v2 reader 使用 merger 匯出的固定身分欄位和 22 檔範圍，核對 lineage、source aliases、原 row count、零新增列、父資料／補算資料／manifest 建立時間。逐列 revision 必須精確對應父資料或 corrected subset；不只檢查早於 capture。新 capture 以 v2 作範本時，清除歷史 merge metadata、封存新前綴並產生 v1 current-only 身分。v2／既有 current provider／capture focused tests **19 passed**，含重新 hash 後的錯誤時鐘、alias、縮減身分欄位與尚未建立來源等反例。

原 bounded 家族使用新 `app_module/bounded_restated_shadow_service.py` 及 CLI。先驗 fit receipt、training manifest、audit、artifact bytes SHA 與原兩演算法／四期間／62 欄，再使用既有純 expert predictor；不改模型 bytes、profile、normal infer gate 或 production pointer。當日資料保留獨立身分，只產生研究 heads；不呼叫 meta 配置，也不將全部現金 targets 宣稱為配置學習。反序列化前仍經既有事故隔離檢查。

登錄表來源轉換有獨立驗證：從完整 original registry 重算 20 個技術欄的 source／table／record hash，其餘定義須完全一致。只重新計算整份 JSON hash、同時偷偷改 dtype／尺度／家族／其他 metadata，不能通過此相容性檢查。訓練及當日兩個 registry hashes 均寫入結果，沒有把不同來源硬改成同一個身分。

bounded focused tests **14 passed**：合成 62 欄資料實際 fit HGB 與 ridge/logistic、四期間三特徵組，再以新的當日輸入執行 24 組 heads；另驗來源更改、過早 capture、資料 hash、受保護路徑及 registry 轉換反例。一則既有 joblib 實體核心數查詢警告；兩個新 service／CLI 檔 mypy 無錯。以下另列真正 22,093 列模型完成後的實際 readback，與合成接線測試分開記錄。

### 真實 bounded 全量模型 readback

原兩演算法、三特徵組及四期間的新模型已完成 22,093 列完整訓練。Root 以修正千分位字串解析後的 current capture，重新唯讀擷取上述 13 檔；真實 capture 為 **2026-09-23T13:44:52.076330+08:00**、特徵日為 **2026-09-22**。每檔 **24 個 expert outputs** 均正常產生，包含 1256、1477；命令含 Python 啟動共 **6.85 秒**，不外推全市場效能。

- 模型位於 `E:/codex_model_repair_20260923/bounded_fullfeature_label_restatement_20260923_v2/training_run01/`；artifact SHA-256 為 `0a9f7a9c399c379d4bed5b98ec124db5661f9358c21d523477dedafe4f04b7e6`，fit receipt 檔案 SHA-256 為 `543f6293da39ad7f1fbaea016dd3b905483c7ea3811714c17cddff6dc43c490f`。
- 輸出位於 `E:/codex_model_repair_20260923/current_inference/bounded_full_run01/bounded_current_heads/dc496e0f87a583ac9b5538c33650c27e5603cf0ecadff66b2093eaecdef1fa55.json`；Root 重新驗算 body SHA 及 13 × 24 組唯一 expert keys。
- Current dataset identity 為 `sha256:c67287c77361da1c4afa0d90de42a15a67bcac534ee7308bcb35392040ae5ef3`，訓練資料 identity 為 `sha256:b46ec56082e52b1d83810c3553cfa89153f4f4406ab752809aac7c26fc40c133`。兩個登錄表各自保留身分，20 欄來源轉換通過完整驗證，62 個數值欄位契約一致。
- 這證明原 bounded 家族的新模型可以使用修正後的當日輸入。它不等於已完成全市場 H5 模型、取得歷史 PIT／正式 OOS 資格，或證明優於基準；沒有產生配置建議，正式混合比例仍為 0。

整合 v2 merger、strict training loader、bounded producer／consumer 及 current reader 後，七個 focused test files 為 **75 passed**。新模型的品質與完整原始資料保留驗證另記於 bounded 修復 QA。

回滾此增量時，僅回退上述新 bounded 入口以及 current reader/capture 的 v2 支援，保留模型、輸入與結果 receipt。沒有排程、正式資料寫入或 frozen ML contract 改動。

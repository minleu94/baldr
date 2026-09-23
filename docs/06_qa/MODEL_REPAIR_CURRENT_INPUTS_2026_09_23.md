# 修訂模型的當日研究輸入

本輪以隔離分支實作當日研究入口；完整模型重訓與驗收完成前，不代表日常模型已切換。

## 實作與回滾範圍

| 路徑 | 變更 | 回滾方式 | 限制 |
|---|---|---|---|
| `ml_module/restated_research_input_contract.py` | 新增不可變的推論來源綁定 | 回退本提交 | 不讀資料、不改訓練 artifact |
| `data_module/ml_restatement_current_inputs.py` | 從封存 Parquet 讀取當日指定股票 | 回退本提交 | 原來源唯讀，只驗證實際消費的分片 |
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

真實 v3 六股票樣本的 current provider 已獨立讀取 1256／1477，確認特徵日為 2026-09-22，capture 使用實際 2026-09-23 時鐘，沒有載入完整訓練陣列。尚待合入新版 fit lineage parser 後執行完整模型載入／推論；全量資料與最終模型仍在建立，不能由此樣本判定修復完成。

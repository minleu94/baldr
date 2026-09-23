# 模型修復：原配置目標的實體資料查核

查核日期：2026-09-23（臺北日期）。本文件記錄原訓練目標的查核結果，不代表模型重訓、評估或日常接線已完成。

## 查核範圍與結果

Root 唯讀檢查既有 Direct numeric run `direct-ooc-505c6adaf3f71a0c8f0a274e` 的全部 13 個年度（2014–2026）、共 **3,353,096 列** `targets.i32`。先逐檔核對年度 manifest 宣告的 SHA-256，再按原 `<i4`、`target_shape` 與 `target_fields` 解讀所有列；沒有載入或反序列化舊模型。

| 原目標欄位 | 全部資料的最小值 | 最大值 | 非零筆數 |
|---|---:|---:|---:|
| `target_weight_bp` | 0 | 0 | 0 |
| `delta_weight_bp` | 0 | 0 | 0 |
| `risk_contribution_bp` | 0 | 0 | 0 |
| `risky_budget_bp` | 0 | 0 | 0 |
| `cash_bp` | 10000 | 10000 | 3353096 |
| `rebalance_worthwhile` | 0 | 0 | 0 |

這批目標只表達保留全部現金的配置限制，不能據此宣稱模型已學會股票配置比例。這個結論只涵蓋上述原目標欄位；報酬、波動、下跌與成交可行性等九個 label 欄位屬另一組資料，不能由目標全常數推斷那些預測模型沒有訓練或不受價格修訂影響。

## 修復決策

- 保留原配置目標語意。重訓報酬與風險模型時，不把事後 H5 報酬改造成新的配置目標，避免將價格修復變成未經要求的策略改版。
- 原列若重用 targets，仍須核對精確 row identity、年度位置、欄位順序、檔案 hash 與原 teacher 的限制；不能僅憑欄位恆定就任意拼接。
- 新增列使用原 teacher 規則重新產生，或明確記錄目標不可用；不能將原列的常數目標無證據延伸到新列。
- 新 release 如沿用現金限制，必須明示其為中性配置政策；不能將固定輸出記為已學會配置，也不能虛報 fit 筆數。
- 2026 年保留資料的評估模型與使用全部成熟資料的最終模型需分開記錄。最終模型對已參與訓練資料的預測，不得計入保留資料表現。

## 可追溯證據

原檔位置：

`D:/Min/Python/Project/FA_Data/output/release_v4/portfolio_ml_direct_numeric_production_v4_v2/runs/direct-ooc-505c6adaf3f71a0c8f0a274e/manifest.json`

原 manifest 實體 SHA-256：

`61d806ef005d0881911201104079c1acc92826a26bd8a331b9bd79156983ffe8`

Root 查核輸出位於獨立整合工作區的 `output/qa/model_repair_review/original_target_values_audit.json`，逐年保存筆數、targets 檔案 hash，以及每欄最小值、最大值與非零筆數；該本機輸出不提交 Git。查核輸出 SHA-256：

`4abe164961842e047cbbb96d2d980eb4241376f28c845253940ed5e79ecc937c`

同一整合基線 `2268a98a` 的模型來源隔離、release adapter 與 inference focused tests 共 `58 passed`，另有 joblib 無法查物理核心數而改用邏輯核心的警告一則。兩個既有量化靜態 guard 通過。這些只證明原隔離／載入檢查在該基線可用，不證明新的資料集、重訓或推論已完成。

## 原模型 recipe 與本輪修復範圍

Root 另以唯讀 JSON 核對 H5 derived release 的 `derived_training_manifest.json` 與 parent `portfolio_ml_direct_ooc_training_production_v4_v5/runs/allocation-ooc-868b7e805f5c03c65dc303e4/manifest.json`。H5 選用三個 feature packs 的 `ridge_logistic`，每個 final base expert 原 fit rows 均為 3,353,096。Parent 的 `ridge_alpha_bp=100` 在 frozen trainer 中轉為 `Decimal(100)/Decimal(10000)`，實際 alpha 為 **0.01**，IRLS iterations 為 **6**；不能將 100 bp 直接當成 alpha 100。H5 derived rank contract 為 `allocation-rank-v2:dense_value_tiebreak`，不能因重訓而退回預設 V1。小樣本 fitting 僅供接線驗證，不等同原規模模型修復。

另一個仍由 daily orchestration 預設入口引用的 `ml_allocation_bounded_v4_operational`，其 `training_manifest_v2.json` 記錄 22,093 rows 與 5／10／20／60 四個 horizons；`training_audit_v3.json` 的 expert fold audits 同時包含 `ridge_logistic` 與 `hist_gradient_boosting`。因此，H5 完成或新四 horizon 線性候選模型完成，都不能直接宣稱原 bounded 雙算法模型已修復。這兩條現行消費路徑必須各自驗收。

`DATA_ROOT/models/` 的兩個 legacy 檔案也只讀取實體 metadata 與 hash，未反序列化或刪除：`_EnsembleModel_model.pkl`（3,030,277 bytes，SHA-256 `2bb8ffd4aee0048409e8e6ec7ddb6da8f836fcba9edcbee0b07ad1b2c285f9e5`）與 `2330_EnsembleModel_model.pkl`（2,715,314 bytes，SHA-256 `064271e3948718300267a51bcb5d9d163d629aea4a3c5c671f30d66e4d971904`）。本輪在目前 runtime Python 中未找到其載入入口；檔案修改時間雖為 2024 年，仍不足以證明訓練資料血緣。保留為未確認的 legacy 產物，不把它們算成已驗證安全或已重訓模型。

# R030 架構邊界與擴充推演 QA

**狀態：** R030 fixture slice 證據已完成；此報告不代表 C2、R029、C3/C4 或整體重構 gate 通過。

本輪只新增有限架構檢查器、synthetic fixtures 與測試，未改 production codec、save/replay、strategy registry 或 historical feature builder。所有測試資料的 `DATA_ROOT`、`OUTPUT_ROOT`、`TEMP` 與 pytest `basetemp` 都指向隔離系統 TEMP；`PROFILE=test`。未使用正式資料，也未開啟互動式 UI。

## 凍結證據

- 凍結 manifest：[R030_EXTENSIBILITY_FIXTURE_QA_MANIFEST_20260925.json](R030_EXTENSIBILITY_FIXTURE_QA_MANIFEST_20260925.json)
- pytest log：`<USER_HOME>\AppData\Local\Temp\r030_luna_final_20260925\r030_pytest.log`
- pytest log SHA-256：`83CD2B39FFF27CB7DEF86BED1A895AA11853F29E18543BCD4B13781B6516867D`
- 結果：**17 passed、0 skipped**；`-rs` 輸出沒有 skip。

可重跑命令與本輪隔離路徑、各 frozen input SHA-256 均記於 manifest。

## 驗證範圍

**架構 guard：** 對有限指定邊界做 AST 檢查：decision 層反向匯入 app、execute/save/replay 手工重建 `RecommendationItem`、persistence/query/presenter 讀取 service `last_*` business state，以及 backtest strategy-ID 分支繞過 registry。負向 fixtures 證明各 guard 會拒絕違規形狀，正向 fixture 證明正常 registry 路徑可通過。`python scripts/check_refactor_architecture_boundary.py` 回報 `R030 architecture boundary: clean`。

**Confidence 欄位推演：** fixture 從 `RecommendationItem` 建立 frozen subclass，加入具 defaults 的 `confidence_score_bp`、`confidence_method_version`、`confidence_status`；透過 monkeypatch 更新 typed aliases、封閉 wire registration、frozen allowlist 和 revision 3。真 `RecommendationReplayService` 先生成 canonical rows，再由 fixture calculator 附上欄位，經原 codec、`RecommendationExecutionPersistence.save`、queries readback 和 presenter 驗證。涵蓋 null、0、10000、越界拒絕、舊 revision 1 fixture 原 bytes 解碼前後一致及未登錄 record 拒絕。新 `__post_init__` 先呼叫原 `RecommendationItem.__post_init__`，舊欄位驗證仍生效。沒有將 confidence 放進 `ExecutionEvent.details`。

**Strategy 擴充推演：** 使用不同於既有 baseline 的 fixture executor，經真 `StrategyRegistry.register/get_executor` 建立，依目前與前一日整數價格輸出訊號。測試比較完整輸入、cutoff prefix 與 cutoff 後價格突變的 prefix，確認前綴訊號相同、cutoff 前不交易；清理 fixture registration 後，舊 registry IDs 與 baseline executor class 維持原值。

**Feature 擴充推演：** 對同一個 synthetic `HistoricalRawSnapshot` 執行 production `HistoricalFeatureBuilder.compute/load`；fixture calculator 只追加 synthetic feature。新舊 schema 比較原有有序 feature IDs、dtype、units、values、missing mask 與 canonical vector bytes，且重新執行後舊 bytes 相同。新增欄位另外驗證 0 與 missing 的區別，以及 cutoff 後極端 raw close 不影響結果。舊 feature projection 以完整有序 tuple（含 `None`）呼叫 production `RunnableRecommendationCalibrationModel.predict`；controlled return/classifier estimators 與 identity calibrator只控制數值輸出，模型既有 `_matrix_from_values` 將 missing 映成 NaN，舊投影 estimator inputs 與 predictions 相同。

模型 parity 是 controlled estimators/calibrator 的 fixture 證據，**不是** safe-loaded 或訓練出的歷史 artifact 證據；artifact loader/class-path 由 C3 既有 route 覆蓋，不在此切片擴張。

## 靜態檢查與限制

- `py_compile`：架構檢查器與兩個 R030 test modules 通過。
- `mypy --follow-imports=silent`：兩個 R030 test modules 無錯誤。
- 一般 import-following mypy 同時讀到正在進行的 R026 NoModel wiring，於 `app_module/recommendation/prepared_runtime_preparation.py:252-253` 回報兩個 `_NoModelProjectionCapability` union-attr errors（缺 `loaded_model_runtime_class`、`model_resolution_evidence`）。此為 cross 正在處理的並行 WIP，非 R030 source；需由後續 R026 broad mypy 收口。
- `git diff --check`：exit 0；Git 只輸出共享工作樹既有檔案的 LF→CRLF notices。

本 slice 的 fixture、測試與檢查器已凍結並列入 manifest。R030 後續 gate 仍依整體任務清單及 C2/C3/C4 驗收裁定；本輪不宣稱已通過那些 gate。

## 獨立相鄰路由複核收據

Root 於 2026-09-25 使用下列 5 個測試檔另跑 fresh TEMP 路由，確認 R030 frozen source／fixture 與相鄰 codec、feature-builder、strategy-owner 回歸相容：

- `tests/test_r030_architecture_guards.py`
- `tests/test_r030_extensibility_acceptance.py`
- `tests/test_recommendation_execution_codec.py`
- `tests/test_ml_historical_feature_builder.py`
- `tests/test_decision_strategy_owner.py`

結果為 **48 passed，1.83 秒**。環境為合成測試、`PROFILE=test`、新系統 TEMP `<USER_HOME>\AppData\Local\Temp\r30r_01c542`；未讀寫正式資料。pytest log 位於 `<USER_HOME>\AppData\Local\Temp\r30r_01c542\pytest.log`，101 bytes，SHA-256 `73495DB39B1F91769C6364181C78A834A5D71070D601414A455B41C8060E877B`。manifest 12 項 frozen source／fixture 加上 3 個相鄰測試的執行前、執行後 SHA 清單完全相同；兩份清單均為 3,486 bytes，SHA-256 `9164C456DE1FB0ED21152602ED41FFD33555F0C4EA48DF2C85664C0A85DC5C02`。完整檔案選擇及 readback receipt 已追加至 JSON manifest。

這是 R030 frozen slice 的 bounded 獨立複核，不代表 C2、R029 cleanup、C3/C4 或整體 refactor gate 通過。

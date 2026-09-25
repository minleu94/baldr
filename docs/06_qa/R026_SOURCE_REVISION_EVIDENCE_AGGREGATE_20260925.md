# R026 四個 Source Revision Namespace 單次聚合切片

日期：2026-09-25
狀態：R027 獨立複核無 P1/P2，root 判為此單次 aggregate 切片 bounded `ACCEPTED_SCOPE`；不代表 R026 或 TMP-ML-01 完成。

## 範圍

新增 `data_module/source_revision_evidence_collector.py` 的
`collect_source_revision_evidence_v1()`。呼叫端必須提供穩定、非路徑的
`scope_id` 與精確 `date` 型別的 `cutoff_date`；入口在任何 collector 執行前，
透過 source-evidence contract 的共同驗證 helper 檢查兩者，不複製 scope regex。
入口不從資料庫路徑、即時檔案或 snapshot 猜測 scope。`symbols` 與
`explicit_path` 僅傳給 direct daily-price receipt collector。

每次呼叫依序各執行一次 market revision、historical session revision、excluded
daily-price revision、direct daily-price repair receipt 的 typed collector。
任一 collector 失敗即傳遞錯誤且不建立 aggregate；四者成功後才建立
`ValidatedSourceEvidenceV1`。舊 `check_daily_price_source_revision()` 不在新入口
呼叫鏈內，避免先跑 legacy composite gate、再重掃四個 namespace。

## 驗證

Fresh TEMP 使用 `PROFILE=test`、隔離 `DATA_ROOT`／`OUTPUT_ROOT`。定向路由包括
新 aggregate 測試、source-evidence contract、market/session/excluded collectors，
以及 direct receipt bytes/link 測試：**86 passed**。

新測試固定了 collector 呼叫順序與每次只呼叫一次、四個失敗位置皆不回傳部分
結果、拒絕非精確 `date` 與路徑型 `scope_id`（兩者都不進入 collector）、digest 綁定 scope/cutoff，
以及一個真實 collector 合成整合案例（三個 namespace 為 EMPTY，direct receipt
為 PRESENT）。舊 legacy gate 未被 aggregate 呼叫。

`py_compile` 通過；scoped mypy 為 3 個 contract/source/test files、0 issues。新測試已登錄
`qa/full_app_healthcheck/test_inventory.py` 的 `service-oracle-recommendation`。

R027 以另一個 fresh TEMP 根獨立重跑上述七檔路由：`C:\Users\archi\AppData\Local\Temp\r026_source_aggregate_review_ad54be1af9a449a782bd39ea7b64fd62`，隔離 `PROFILE=test`、`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP/TMP` 與 pytest basetemp；結果 **90 passed／0 failed**（13.65 秒，exit 0）。路由包含本 aggregate 測試、source-evidence contract、market/session/excluded collectors，以及 direct-receipt same-bytes/link characterization。無 P1/P2。此 verdict 僅接受單次資料層 aggregate 與失敗不回傳部分 aggregate 的行為。

## 限制

此 digest 表示四個 namespace 各自一次檢查的合成結果，不代表跨檔、跨 namespace、
多個 SQLite 查詢或不同呼叫之間具有原子性，也不替代 invocation pre/post 比對。
`scope_id` 的 production 來源政策尚未定案；呼叫端需提供既有、穩定的邏輯來源
識別。此切片沒有做 ML wiring；R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

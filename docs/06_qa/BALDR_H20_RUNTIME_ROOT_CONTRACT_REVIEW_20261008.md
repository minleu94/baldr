# H20 runtime 根目錄契約獨立複驗

狀態：候選路徑解析契約合成驗證通過；原始 H20 完整主視窗旅程與新 EXE 尚未驗收。

本次發現兩項啟動契約錯誤：舊 child 將 output root 再附加 `output/`，與 supervisor 的實際輸出位置不一致；Windows 路徑直接替換進 JSON allowlist 字串造成反斜線跳脫失效。新 QA 候選明示區分 case root 與 output root，JSON 路徑列表使用 Windows 可解析的 `/`。原 frozen 檔案未覆寫。

Root 以 native Python 獨立執行 `output/qa/h20_dual_runtime_contract_20261008_a/runtime_paths_contract_synthetic_selftest.py`，terminal exit 0、21 項通過。收據為同目錄 `runtime_contract_selftest_20261009T001323Z.json`。較早 sandbox 執行的 `Path.resolve` 出現 WinError 5，該失敗保留，未透過移除 containment 檢查處理。

驗證使用候選 child 的實際解析方法，涵蓋 case/output 根目錄一致性、必要 case 欄位、QA containment、effective 兩條 runtime DB 路徑、legacy 三條內層路徑、第三 effective DB 拒絕，以及未支援 placeholder 拒絕。此測試不執行 Main、SQLite 連線、模型、產製器、網路或 EXE。

候選 SHA256：

- child：`ea7daa0055c9ed17aa314a87e391cf71977cb5de72eca69d1971921403ee490e`
- legacy adapter：`98ca79e560497dd423772783da1b3300cb237e00bbef78e1fd1eadc50b7c22f6`
- supervisor：`70d3574bfe9501a1863fc3fefc8a47e59e2997bedf2b1210acac15e48ccaf7e7`

下一個必要驗證是明示型別的 WAL merged market bridge：原市場 main/WAL pins 與合併副本 SHA 必須分別保留，不能冒充既有 `PinnedSQLiteReadSession`。完成橋接、固定來源封套與完整主視窗旅程後，才能製作供真人驗收的新版本。本紀錄不代表 launch 範本核准或正式資料接受。

# F12 穩定保存條件與連續重開：Root 複核

Root 實讀 `output/qa/f12_revenue_source_adapter_20261009_a/adapter_attempt07_recipe_positive_native.log`：真雙來源正向旅程 1 passed、168.11 秒。另直接閱讀目前測試 380–466 行的兩次重開、頁面、來源 inventory 與連線關閉斷言，並重新計算來源 SHA。

- adapter `app_module/daily_market_technical_official_disposition_revenue_source_v1.py`：`33b66b658fb20e2a2c6481fce14e60d607a21b2d8d028a6b0aeeca50afe422d9`。
- 測試 `tests/test_daily_market_technical_official_disposition_revenue_source_v1.py`：`b14ced39efcb330dbbb419b564616f7ee4be580489561f6c30657874611d4157f`。
- Root 另執行方法 ID/version 契約測試：1 passed、0.71 秒；三個相關檔案的 mypy 無問題、py_compile exit 0。

旅程先從真正 exact reader 發行 page 0 recipe，以保存 archive 重新開啟；操作 ID 可更新，原來源、條件、排序與頁面保持。翻至 page 1 後發行新 recipe，identity 隨頁碼改變，再用這份 recipe 重開，確認 page 1 的 facts/counts、條件、排序與來源相同。操作各自使用新的私有 SQLite copy，所有已開連線關閉；原歷史 DB parent/raw origin 暫時移離期間仍可重開，測試 finally 還原，原檔與來源 inventory 起訖不變。

recipe 自身的 JSON/hash 只保存條件與固定參照，不授予資料資格。每次重開仍由真正 archived exact reader 核來源。資料保持 current_only、availability unknown、historical PIT false；沒有把原始時鐘與本次操作時鐘混成同一識別碼。

先前失敗封套保留：operation clock 與原保存 clock 誤混、query 方法 ID 誤用 reference 方法 ID，以及翻頁後錯誤要求 recipe identity 不變，均不當作通過證據。這次接受範圍為 backend 連續重開；尚未證明新 Qt 畫面、完整 Main 收藏按鈕、EXE 或真人操作。下一步以此真 API 建立獨立畫面與保存入口，再依 UI gate 驗證。


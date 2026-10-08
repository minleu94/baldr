# Baldr 讀取 session 中央審核（2026-10-08）

這份記錄涵蓋 P01 的固定來源索引核心，以及 H20 私有 SQLite 副本的設定與 provider 介面。兩者尚未完成 UI 接線、新候選打包或真人接受；不表示完整補完計畫已完成。

## P01 固定來源索引

中央在原生 Windows 的獨立隔離暫存執行 `tests/test_daily_market_technical_universe_v4_read_session.py`，結果 **7 passed / 46.49 秒**，程序 exit 0。四個 owned 檔案的 mypy 通過。原始輸出保留於 ignored `output/qa/p01_root_review_20261008_b.log`。

測試使用真 public producer、repository 與 store 的合成來源：17 股納入、257 股排除，驗證完整索引的 AND／OR、全域排序與分頁、Decimal／同值／空值排序、選股下鑽、空母體／全排除／partial、來源不符、索引預算、取消、child 篡改，以及 fresh 收藏重驗與新程序 strict 還原。這不是 1000+ 股票或真市場 full-N 的效能證據。

session 固定建立時完成核驗的版本；它不宣稱來源後續仍未變動。頁面與個股會精確重開選取的 child artifact；新收藏重新完整核驗來源，跨來源比較仍各自使用 strict reader。64 MiB 是 canonical serialized index 的預算，不是 Python RSS 限制。

中央審核發現 `read_stock_snapshot` 先讀 origin page，再重讀選取的 child artifact。已要求提出保留來源與 origin page 身分驗證的去重方案；目前不能據此宣稱下鑽延遲已解決。

## H20 設定與 provider 介面

中央新測試 `test_personal_h20_sqlite_read_config.py` 與 `test_ml_current_observed_read_copy.py` 共 **10 passed / 1.32 秒**。中央另跑既有 bootstrap、historical provider 與 current-observed capture 回歸，共 **85 passed / 3.89 秒**，程序 exit 0；輸出在 ignored `output/qa/h20_stage1_root_regression_20261008_b.log`。

明示設定 `PERSONAL_H20_SQLITE_READ_ROOT` 為絕對路徑，未設定維持 `None`；設定解析不建立目錄，frozen 模式拒絕程式包內路徑。實際 copy session 負責驗證既有私有根與固定來源的隔離。

provider 的 opt-in session 分支核對原來源路徑與 SHA，重用私有副本既有唯讀交易，保持原 provenance、feature 與 row hash；不另開來源 SQLite 連線、不再雜湊原 DB，也不提交或關閉呼叫端交易。未傳 session 的既有路徑保持相容。測試包含錯誤路徑／SHA、已關閉與取消的 session 拒絕，以及原合成 DB 與 sidecar 起訖 hash／stat 不變。

實際 H20 public verifier、feature replay、entry observation 與 Main 尚待接線。原 4 GB 封存來源的保護、等待提示、2382 下鑽時間、收藏新程序重開與新候選資格均未由這些合成測試證明。

## 真人驗收狀態

使用者回報舊 `0f25b8c6ee51` 名單最終出現，但等待很久且不清楚觸發時機；雙擊 2382 後反應慢，未確認能下鑽。此項仍未通過；不要求使用者重測舊版。下一候選完成原件保護與 Main 自動驗證後，才提供精確啟動檔及分開計時的名單／下鑽驗收步驟。

# R007 aware datetime 深凍結依賴勘誤

DEPENDENCY_STATUS: REOPENED_FOR_TARGETED_ERRATUM

R008 的獨立深凍結審查顯示，aware `datetime` 可保留呼叫者所有的可變 `tzinfo`。SOL 在 R007 的 `Availability.available_at` 與 `MarketSlice.cutoff_at` 重現相同問題：來源 `tzinfo` 偏移由 0 改 9 小時後，已建構 record 的 `utcoffset()` 跟著改變。此項具體違反 FINAL_ARCHITECTURE_INVARIANTS INV-08，也影響 R008 對 R007 leaf contract 的依賴信任。

只在 R007 原 leaf contract 範圍內回修 `data_module/contracts/market.py`、`tests/test_data_market_contracts.py`，另新增專項勘誤報告。目標是在封存時固定當刻時間與 offset，保留已知日期、時間、微秒、fold、ISO/timestamp；不得重新解釋 PIT/availability、改 provider、writer、正式資料或其他 R-task。原 R007 與 Wave 1 的 PASS 保存為舊 SHA 的歷史證據，待本勘誤通過後重驗相關 R007/R008 tests，並在 Wave 2 checkpoint 記錄新依賴 SHA。Wave 3 在此與 R008 均通過前保持 blocked。

回修首版核查另發現相同 INV-08 邊界的兩個 caller-owned alias：`datetime` subclass 可覆寫 `utcoffset()`，即使它持有標準 `timezone.utc`，首版 helper 的 trusted-zone 分支仍原樣保存 subclass；另外 `SourceObservation`、`SourceRef` 的外部 subclass 可用額外 mutable `payload` slot，現有 `isinstance` 驗證會把 subclass 原樣存入 `MarketSlice`。SOL 已分別重現封存後 offset 0→9 小時及 `payload.append()` 改變已封存 graph。R007 owner 在原兩個授權檔內補 builtin datetime snapshot 與 nested record exact-type 驗證測試；不得以一般 frozen decorator 對 subclass 的外殼代替深凍結證據。首版 R007 勘誤報告所列 SHA/PASS 只屬中途快照，須重驗後更新。

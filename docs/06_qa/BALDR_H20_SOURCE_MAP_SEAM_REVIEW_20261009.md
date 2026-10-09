# H20 固定來源清單環境橋接審查

## 範圍與結論

根 agent 已直接審閱 `synthetic_main_20261009_m` 的 child、controller 與測試紀錄。此變更僅處理 Windows 環境變數單一值長度限制：完整 4,161 檔來源 SHA 清單有 493,808 字元，不適合放入 Win32 環境變數。

候選改由固定 manifest 路徑及 SHA 傳遞，驗證完整來源 inventory、檔案身分、總位元組與 22 個依賴 pins 後，僅對精確 legacy 模組的單一環境 key 提供唯讀值。其餘環境讀寫委派真實環境；沒有截斷清單或更換全域 `os.environ`。旅程結束須還原 loader 與模組 `os`，確認該 key 恰好讀取一次並重核 manifest 身分。

## 已核對的證據

- child SHA-256：`DDEBB4068E7A120EE674F2A0DB590042B20934FC042AA854AAB1C1D205DB60E2`。
- controller SHA-256：`B819400F51FD7134F7DCAE34967A85F0351F0566DA2D198927EBAB54CAF592F5`。
- 實際純測試紀錄：7 passed，1.88 秒；測試檔 mypy 通過。
- 測試涵蓋完整 s3 清單、不可變 map、錯誤 manifest pin、來源漂移、額外檔案、環境長度限制、精確模組橋接與還原。
- 純測試沒有啟動 Main 或連接 SQLite。child 整檔仍有與 preimage 相同的 19 類動態 Main／DTO 型別錯誤，不能宣稱整檔型別檢查通過。

## 下一步與驗收界線

已授權 owner 以固定 controller 執行一次全新隔離合成 Main 旅程，保存啟動 argv、來源起訖、三條 DB 路由、2382 下鑽時間與結果、child terminal，以及 Job 關閉後 owned process 為零的證據。失敗不得覆寫或直接重試。

此審查只批准 QA 橋接與下一次執行，尚未證明 Main 旅程、原始 H20 下鑽效能、EXE 或真人操作驗收完成。

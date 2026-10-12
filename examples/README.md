# 示例資料

本repo不內附市場SQLite、私人持倉、模型、憑證或交易日曆。舊main_example.py不存在，不作啟動入口。

`synthetic_price_shape.csv` 是人造資料形狀示例，symbol為DEMO，不是實際股票，price單位為字串Decimal、volume為整數；兩列不足以產生MA／BB或策略訊號。它不是可載入的UI demo，不具PIT、自然結果、訓練、正式或交易資格，不得匯入正式資料庫使缺件變綠。

主入口為 [快速開始](../docs/07_guides/QUICK_START.md)，需要可用行情時依自己的資料來源與使用權取得；不把QA私人物件或有saved outputs的notebook當demo。

移機使用[安裝清冊範例](machine_bootstrap_manifest.example.json)與[Schema](machine_bootstrap_manifest.schema.json)。範例只有待填佔位與停用期望，不能直接執行；依[首次安裝 Prompt](../docs/07_guides/FIRST_INSTALL_PROMPT.md)填入自己的 roots、資產與排程，再產生唯讀計畫。

舊機來源依[盤點格式](machine_bootstrap_inventory.example.json)與[盤點 Schema](machine_bootstrap_inventory.schema.json)正規化，保留原匯出 path／SHA。正規化清冊的 SHA 填入安裝 manifest 的 `source_inventory`；原 XML／Codex 定義與正規化欄位仍需逐項核實。`bootstrap-plan` 核的是正規化檔案 hash 與排程差異，沒有解析 XML 或證明匯出內容一致。

# 示例資料

本repo不內附市場SQLite、私人持倉、模型、憑證或交易日曆。舊main_example.py不存在，不作啟動入口。

`synthetic_price_shape.csv` 是人造資料形狀示例，symbol為DEMO，不是實際股票，price單位為字串Decimal、volume為整數；兩列不足以產生MA／BB或策略訊號。它不是可載入的UI demo，不具PIT、自然結果、訓練、正式或交易資格，不得匯入正式資料庫使缺件變綠。

主入口為 [快速開始](../docs/07_guides/QUICK_START.md)，需要可用行情時依自己的資料來源與使用權取得；不把QA私人物件或有saved outputs的notebook當demo。

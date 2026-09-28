# m11 個人模型與自然結果評估（2026-09-28）

## 驗收範圍

本報告記錄 m11 隔離 Qt widget 個人模型流程及其唯一保存 capture 的 Stage C 自然結果評估。模型採用是 user-declared research-only；不代表 official historical PIT、正式模型 promotion 或整體 WP5 通過。Qt 收據只證明 Qt widget automation，沒有 OS foreground／desktop screenshot 驗證。

## m11 保存結果與隔離來源

- 候選：rec-cal-3f8b2c276ef316e28de3806d，learning tree 為唯讀 pin。
- 第一次啟用後保存的 canonical result：rec_03ae4c2c3e0344a7ae26d8646107c851。canonical payload SHA-256 為 d0804acd55dfa90eb49277fb0685fef416a2dcec893956102a651d0338fc97e8；artifact raw SHA-256 為 51fcfcb9ff9d9f12fff359eaed25e8aad280ff16230bb9c97dba350cacdca2a4。
- 保存 readback 顯示 19/19 個別股列使用該候選的 calibrated probability，皆為 6000 bp。這只描述 m11 保存推薦列，不是效果勝出證據。
- restart／停用／版本回復後，policy revision 4 為 rule_only；global pointer 未觸碰。
- 唯一 capture 為 [ad981904…ac28.json](../../output/qa/personal_daily_product_20261006/personal_research_ui/m11/output/_test/personal_prediction/captures/ad981904a1717affda64c1a787aa95c7602156344a67a6521dd0ff3c23b8ac28.json)，raw SHA-256 9bb49cb8e0f461231710dfd7d8113d15383674094eb208d332315bf43dbf2f46，capture schema recommendation-personal-prediction-capture.v3。
- m11 工作資料庫位於 output/qa/personal_daily_product_20261006/personal_research_ui/m11/data/_test/sqlite/twstock.db；raw SHA-256 c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08，與固定 QA snapshot 位元相同，但工作副本在 m11 隔離路徑。m11 沒有開啟或寫入正式 D 資料庫。

UI journey 收據：[personal_model_acceptance.json](../../output/qa/personal_daily_product_20261006/personal_research_ui/m11/receipts/personal_model_acceptance.json)，SHA-256 dd9f976b41d589def2b13e26d50303882632725510a19b8ca1346cd17423fcf4。該收據標記未驗證 OS 前景畫面；不要將其 Qt widget render 說成真人桌面操作。

## 候選資料與表現限制

候選訓練收據為 [fit-v7-fe4e918b1257.receipt.json](../../output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json)，SHA-256 f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1；細節亦見 [m10 候選與 UI 報告](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)，SHA-256 3ccfef56e6ceffb8f6323d00e4785b9afae31a789c81b212974a9d2bc4119cee。候選使用 8 檔：2308、2317、2327、2330、2344、2408、2454、3037；歷史輸入自 2024-10-24、replay 至 2026-06-26，training_as_of 為 2026-05-25、training_cutoff 為 2026-06-26。512 筆 replay sample 選 64 個決策日（2025-11-28 至 2026-05-28）。20-session label horizon 與 50 bp 固定 round-trip cost 下，有 336 筆 cutoff-eligible training rows，其中 176 筆 OOF calibration、16 筆 untouched holdout。特徵使用決策日前一交易日資料；source available_at 是 user-declared 日粒度契約，非同日盤中可得或官方 publication/PIT 證明。

Holdout Brier 為 2730 bp，50% null baseline 為 2500 bp，差 230 bp；這是表現偏弱的 advisory，不能稱模型勝過基準，也不等於工程採用失敗。兩個舊 legacy candidates 的安全 loader 曾載入成功，但缺 training lineage／來源時間契約且績效未獨立驗證；沒有修改原件，也不把它們說成 loader 失敗或可採用。詳見 [WP5 整合清單的候選限制](WP5_INTEGRATION_CHECKLIST_20260928.md)。

## Stage C 評估

Stage C 僅以明確指定的 m11 canonical output、單一 capture、m11 工作資料庫及 calendar cache 執行。評估時鐘是實際 UTC 2026-09-28T17:13:55Z；命令參數、完整路徑與 pin 收在 [m11_stagec_evaluation_receipt.json](../../output/qa/s11/m11_20260928T1713Z/m11_stagec_evaluation_receipt.json)，Stage C 原始 summary 為 [6fbe8be5…b667.json](../../output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json)。

Stage C CLI exit 0，結果 completed_with_pending：選取 1 個 capture、19 個樣本 pending、0 matured、0 個 outcome artifact。唯一 pending reason 是 personal_outcome_source_or_cost_incomplete。未建立 global natural evidence 或 promotion credit。這表示自然結果目前尚不可評估，並非模型虧損或成功。

使用的 official annual calendar cache raw SHA-256 為 2b145dacedbd267eef4df7f9043e0534eaa8d19a76ed6532c5218397bb5605c1，檔案內 expires_at_utc 為 2026-09-28T23:15:03.981649+00:00，在本次評估時仍有效。它只覆蓋 annual plan；本次沒有提供 temporary-closure cache，因此不聲稱已排除臨時停市。市場資料庫的 Stage C before／after device、inode、size、mtime 一致，工作資料庫 raw hash 也維持不變。

## 可重現 QA 證據

- Stage C summary raw SHA-256：2355562e24d6e9e3398810835e43ac315ce84a61ae89bb55b6652abbea4dbdea；summary 內 payload SHA-256：6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667。
- 專屬 create-only QA receipt raw SHA-256：e738d47070872bc043a775db0e308fa2ddd74401685ff697612c7583c700022c。
- 所有輸入與輸出均位於 repo QA 區或明確 calendar cache；本次沒有執行 scheduler、HTTP、模型訓練、promotion 或交易動作。

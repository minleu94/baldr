# 完整母體查詢消費同次核驗內容

本葉片沿既有完整母體 store 的逐段 verified-parent callback，直接消費同次嚴格核驗的 child snapshots。每段只留下股票代碼、排序值與精確 child artifact 引用；全域排序後只重開頁面涉及的 child，而不再次重開整個256股 parent。不同查詢仍重新核驗來源，沒有跨操作快取、latest fallback 或放寬 hash／來源／取消 guard。

原 query 的来源／時鐘／方法／日期不符仍回傳 `technical_universe_v4_query_source_identity_mismatch`。完整 receipt 核驗成功且計數一致後才回傳頁面；callback 途中失敗不發布部分結果。策略判定沿原保存的五規則結果，排序使用 Decimal／整數等原精確型別，不新增金融 float 或讀未來行情。

## 驗證

- 完整257股測試初次為8 passed／1 failed、490.01秒；唯一失敗為錯來源 pin 的穩定錯誤碼順序。失敗證據保留，沒有列為全綠。
- 修後原257股針對案例 `test_exact_receipt_missing_corrupt_and_rehashed_source_identity_are_rejected`：1 passed、276.40秒、session59565 exit0。
- 真17股16+1 child 小型回歸：1 passed、9.35秒；初次每個 child 只讀一次、頁面 child 再讀一次，非選中 artifact 的 fresh tamper 仍拒絕，錯方法／日期仍回原來源錯誤碼。
- 中央相同固定257股 query identity、pins bytes SHA、計數及頁面結果的單次非剖析量測為8.1980804秒，原單次35.8078331秒。raw receipts 分別為 `output/qa/baldr_completion_m2_20261007/full_v4_query_stream_measurement_20261007.json` 與 `full_v4_query_plain_measurement_20261007.json`，均保留。
- 中央完整 mypy：882 source files、0 error；既有兩則 untyped-body notes 保留。Python語法檢查通過。

## 限制

單次量測同時有其他QA，不是冷暖／30次互動 p95、1000股或真N效能。8.2秒仍不足以授原互動效能 Gate。完整257 UI 回歸與正常初始化 MainWindow 收藏重開另行驗證，不能以本底層葉片宣告 P01／P04／P09 或整份 P00–P14 完成。0f25b8c6真人候選不包含本葉片；未替換原exe、推送或修改main。

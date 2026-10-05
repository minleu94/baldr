# 2026-10-05 每日鏈容量與接線修正

## 授權與範圍

使用者於本聊天明確授權調整容量限制，並一併處理 Decision Evidence、G6/G9/Bank 與 Paper EOD 工程阻塞。沒有刪除原始資料、變更排程、寫正式 DB、交易、stage/commit/push；Weekly 人工審查與 formal credit 不自動核准。來源／訊號／特徵的決策 cutoff 與模型資格保持原契約；僅整數 bytes 容量計算，沒有新增金融浮點計算。

## 修正

1. 中央安全餘量 200 → 20 GiB。本輪正式 raw 仍計 35 GiB 持久＋40 GiB 暫存，共 95 GiB；研究 cycle 採實際 snapshot 上限＋2 GiB 持久＋2 GiB 暫存＋20 GiB。較大顯式餘量保留，未知用量與不足空間仍拒絕。G6 producer 與 G9 reader 使用一致 v2 政策；舊 v1/200 GiB 證明依原帳驗證，不接受混合 reserve。
2. Decision wrapper 持有 canonical OS lock，Popen 後登記 child PID 並交接已驗證 lease；Evidence child 只在 lease 缺席時自行取鎖。偽造 marker 不能繞過，第三 writer 不能進入，父層釋放後新 owner 能取得鎖。
3. G6 snapshot 與 source observation 以实际內容 SHA/bytes 判別 DB/WAL，空 WAL／不存在不當成來源新交易，mtime-only 不拒絕。revision namespace、data_version、journal mode 與非空內容變動仍 fail closed；snapshot_failure.json 保存前後證據，不產生成功 receipt。watchlist/holding 的原 mtime/hash pin 不放寬。
4. Paper 明列的不可重試政策時間拒絕，在 source/candidate/receipt 全部驗證且無 ledger 時作 rejected 終態；queue diagnostics 明列原 receipt/hash，沒有成功或 formal credit。source-less 衍生失敗經完整 candidate/receipt 驗證後不構成 pending identity。原始錯誤仍逐筆驗證，未知 blocker、混合身份錯誤、candidate 異動與真正 pending 過期仍阻擋。

## 驗證

- 核心容量、G6、Decision、Paper、容量資格、raw wrapper、新子程序／snapshot suite：230 passed、2 skipped。
- G9 raw dependency、Bank operational、learning lineage、current-restated context、Evidence service：151 passed、4 skipped。
- 新增舊政策相容與混合 reserve 拒絕後，capacity eligibility 單檔：8 passed。
- 六個變更 source 的 scoped mypy 通過；變更 Python 語法檢查通過。
- Bank 相關測試須用短隔離路徑 `--basetemp=output/hb105`，預設 OS TEMP 的 no-follow ancestor 權限與長路徑不能當產品失敗。Paper fixture 必須位於 OS TEMP；對 Paper 不覆寫 basetemp。初次環境失敗已依正確入口重跑，不改 ACL 或正式檔案。
- 真實 D 槽唯讀容量回查：available=294142603264 bytes；required=102005473280 bytes，within_budget=true。
- 原 Paper 10/2 receipt 完整重新驗證，讀為 rejected；全部原 receipts 載入後 invalid pending 為 0。原始檔案保持不變。
- 詳細回查：`output/qa/heartbeat_chain_repair_20261005/readback.json`。

## 尚未宣稱的結果

本輪是工程與隔離驗證，不是新自然排程或新的正式訓練。10/5 原失敗 run 保留；G9/Bank 要在新 run 取得合格 G6 terminal 才能消費。真實 DB/WAL/revision 在快照期间變動仍需停止，不能把受控測試替代新成功收據。來源資格、歷史 PIT、H5/20 日成熟、Weekly 人工審查均按原 Gate。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| data_module/ml_storage_capacity.py | 修改 | 從 before_files 同路徑還原本輪差異 | 200 GiB 舊門檻恢復 |
| data_module/current_observed_capacity_eligibility.py | 修改 | 從 before_files 同路徑還原本輪差異 | reader 回到舊政策 |
| scripts/scheduled/current_stock_research_cycle.py | 修改 | 從 before_files 同路徑還原本輪差異 | 空 WAL 誤判恢復 |
| scripts/capture_evidence_events.py、scripts/scheduled/run_scheduled_decision_evidence_capture.py | 修改 | 從 before_files 同路徑還原本輪差異 | 父子鎖衝突恢復 |
| data_module/paper_daily_execution_producer.py | 修改 | 從 before_files 同路徑還原本輪差異 | 舊拒絕再堵 queue |
| 三個既有測試與新 tests/test_heartbeat_chain_repairs.py | 修改／新增 | 還原既有測試差異，移除新測試 | 不影響正式資料 |
| Manual、Snapshot 與本報告 | 修改／新增 | 僅還原本輪段落 | 不覆寫其他聊天同期文件變更 |

步驟：先 `git diff -- <指定檔案>` 檢查同期變更；無其他變更的 source 可用 `Copy-Item -LiteralPath output/qa/heartbeat_chain_repair_20261005/before_files/<檔案> -Destination <檔案>`。有同期變更僅按 diff 手動還原本輪行，不整檔覆蓋。重跑上述各範圍測試。原始資料、歷史 receipt、模型與 output 不刪除。

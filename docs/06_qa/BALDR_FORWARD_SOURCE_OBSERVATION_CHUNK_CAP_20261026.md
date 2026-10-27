# Forward 來源觀察 chunk 上限修正（2026-10-26）

唯讀盤點最新 Forward outcomes 執行時，發現來源觀察 recorder 會因 `source_observation_chunk_count_limit` 停止發布；該 run 未產生 Forward outcomes。根因是每個小型 query 至少需要一個 chunk，但 recorder 原本只允許 128 chunks，低於既有 4,096 query 上限，且可能在 run byte／row、chunk 檔案大小及 manifest 大小都仍符合契約時先行失敗。

`app_module/forward_source_observation.py` 現將 `MAX_CHUNKS` 從 128 提升至明確的 4,096。這沒有放寬既有總 query、總 row、單檔 512 KiB、manifest 512 KiB 或 run 64 MiB 上限；超出任一上限仍拒絕。每個 chunk 的 query 身分、row hash、source binding 與 outcome 關聯格式不變。

新增 129 個各含一列的小型 query 的 regression，確認 recorder 可持久化所有 chunk 並逐列讀回，且每份 chunk 保持單檔大小上限內。受控驗證：`tests/test_forward_source_observation.py` **6 passed**；Windows Job readback 為 kill-on-close、8 GiB／12 程序上限，exit 0、剩餘 PID 0、handles closed。

這只修復工程 recorder 過早遇到 chunk-count cap 的路徑。未重跑正式 DATA_ROOT 的自然 Forward producer，未寫正式資料庫／排程狀態，也不改資料來源可得時間、PIT、Formal、績效或 ML 資格；正式自然 run 與其餘 blockers 仍待各自驗證。

執行收據：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\forward-source-observation-fix-20261026\final\receipt.json`，SHA-256 `DB1219FD28BF743FFF516095C7067543FFEBFBBEED42A0D213DCF700C4C2DA2B`。完整終端輸出：同目錄 `stdout.log`。

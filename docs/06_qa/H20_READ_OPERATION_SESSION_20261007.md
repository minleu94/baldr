# H20 單次操作來源核驗與等待提示

真人回報0f25候選的名單很久才出現，雙擊2382仍等待過久並關閉；尚未驗證下鑽成功。原十股公開讀回約93秒，每列重驗同一大型來源庫，不能以等待提示當作效能改善。

## 本輪行為與邊界

新增操作內來源／合約核驗 session，按完整 canonical binding bytes 分組，不能忽略 observed_at 或只用檔案路徑合併。快取回傳獨立副本，不跨操作；各筆 capture 仍沿原 strict reader驗證。完成前各群組 fresh source／contract verifier結果須逐位元組相同，再重讀原 manifest、capture pins及activation/reference，任何終態變動拒絕發布新結果。單股入口將原 manifest和prediction兩段讀回共用同一session，保留expected_reference。取消與phase callback錯誤傳出，不能吞成未知列。此變更不重算預測、不訓練、不啟用模型或改讀最新來源。

Main名單等待提示顯示實際讀取階段與秒數，取消提高generation，晚到phase與結果不得套用。保存個股H20與一般個股product worker接入同操作入口；原報告成功與否不影響保存H20獨立摘要。大檔verifier仍無分塊取消，不宣稱立即取消或特定實際速度。

## 已取得證據

中央 session／cohort UI／推薦版面／更新工作台組合106項通過（11.32秒），全域mypy887檔通過；更新頁validator25通過、0失敗、4保護跳過，runtime修改檔py_compile通過。首輪sandbox 7項fixture activation原子替換WinError5失敗、99項通過，保留原log；獨立原生短TEMP重跑全通過。106項的測試時間不能當成原十股載入時間。

保存下鑽旅程與workspace面板6項通過（9.33秒），包含保存報告、報告失敗仍獨立摘要、來源切換取消及晚到拒絕、明確重試與來源指標變動保留原名單。這套使用MainWindow方法harness，不能代替完整MainWindow constructor驗收。第一輪5通過、1失敗由CapturedWorker欠缺新增progress signal造成，原輸出保留；補齊替身signal與新入口trace名稱後重跑，不放寬產品來源限制。

原始輸出在ignored output/qa/baldr_completion_m2_20261007/h20_session_ui_root_20261007_d.log（sandbox失敗）、h20_session_ui_root_20261007_e.log（106通過）、h20_main_root_20261007_f.log（替身失敗）、h20_main_root_20261007_g.log（6通過）、h20_session_mypy_root_20261007_d.log與h20_update_root_20261007_e.log。各次隔離fixture保留，不清理或覆寫。

## 未完成驗收

完整MainWindow初始化後的名單→2382雙擊→保存摘要→返回／重驗／取消與終態來源變動；原十股唯讀來源時間與來源bytes不變；最新固定候選Python/exe同版與真人閱讀、實際反應速度仍待。0f25候選不包含本輪改動，不能請真人沿舊版重驗本輪成效。H20收藏UI及原P00–P14／M1–M3其他出口也仍未完成。

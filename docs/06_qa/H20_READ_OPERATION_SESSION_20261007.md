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

本輪 runtime/介面與定向證據已保存於 dev d9a115f67d2bda845409e0047311cb7dc92a8a10。僅讀原 ten-capture JSON/manifest metadata、逐檔raw SHA與起訖stat比對，確認完整來源binding為1組、合約binding為1組（h20_binding_groups_20261007_b.json）。沒有SQLite連線、沒有呼source verifier，故此證據只支持可共用群組，不支持實際速度達標。第一個metadata probe使用錯誤pin欄名sha256而KeyError，原script保留；新唯一b使用既有manifest raw_sha256後通過。新candidate從固定d9 commit建置中，未驗證前不交真人。

## d9 固定候選與原來源再驗

固定 runtime commit d9a115f67d2bda845409e0047311cb7dc92a8a10 已建置2026.10.06+d9a115f67d2b，exe SHA f6c0710c57b6e7f7714d5ca15d34e9935ee70fe9e383e947c95df55928159b2e，archive SHA 6ac742e0f87a0ca00c1e4c17c0144eab31414670efbac1afd6df11a8d0e8275c；原exe未替換。BUILD_INFO維持built_not_validated建置快照，資格沿下列獨立QA收據，不覆寫建置原件。

原十股readonly canonical probe output/qa/h20canon_d9_20261007_a/canonical_readonly_receipt.json passed（controller96.843秒）。Python/exe都10/10available，2382仍684bp、決策10/7／來源10/6／特徵10/5，原完整capture身份與單股public product evidence一致。每次名單operation source/contract verifier各2次；另一次stock operation再各2次，不跨操作快取。原manifest/captures/activation/reference/DB/WAL/SHM bytes起訖不變，兩模式各4個SQLite connection均mode=ro/query_only，無predict/fit/SQL寫入/網路。模型載入未量測，不能把未訓練解讀成未載入模型。

單次工程量測：Python名單19.531秒／stock product18.406秒，exe名單23.906秒／stock product18.812秒。舊0f名單約92.7秒；host/page-cache及操作範圍不同，這不是p95、冷暖分布或真正Main雙擊總時間，仍需真人評估等待與階段提示。probe單股讀回是public product，不冒稱原來源Main stock-report完整成功。

一般共同入口same-version另通過output/qa/baldr_same_version_d9a115f67d2b_2ac07260/same_version_receipt.json的隔離呈現fixture。第一eb86ce85在QA終端cp1252中文輸出失敗，原receipt/log保留；明示UTF-8後新attempt通過。該一般fixture不替代canonical原source或完整full-N同pins驗收。

真MainWindow新增journey在中央合成環境2通過、8.82秒；補齊測試型態與實際TaskWorker基底後再驗2通過、8.32秒，6則既有layout_helpers:380 disconnect warnings保留。該測試用完整MainWindow()與QTest真雙擊，覆蓋下鑽摘要／返回／重驗source bytes drift拒絕、關窗取消；source/model verifier為合成邊界。首次QTest缺單擊前置而未發出doubleclick、後續取消測試阻塞GUI pump的失敗attempt均保留，校正測試而不改Main。新test的型態檢查自身通過；擴追舊fixture測試有既有型態錯誤，並非全tests typing綠燈，production全域887檔檢查沿前文。

新ignored啟動檔start_h20_feedback_candidate_d9a115f6.cmd/.ps1已建立（UTF-8 BOM）。Windows PowerShell5以ValidateOnly核candidate SHA、原日曆及研究設定與child env成功，未啟動GUI。真人僅重驗本輪推薦完整閱讀、H20可讀下鑽與返回，不驗尚未接線H20收藏或整份P00–P14完成。

# 測試暫存同盤可還原隔離收尾

量測時間 `2026-10-05T09:43:35.270504+00:00`；產品基線 dev `6691ec784eea6e020d181d8e0aacc485679910a2`。使用者已授權可恢復清理；永久刪除未授權。本批未開代理、Native視窗、producer、訓練或全套測試，未更動正式資料／模型／排程／持倉。未知 `paper_event_source_capture.py` 未讀未動。

## 已完成範圍與占用

限定既有 `output/qa/cleanup_feasibility_20261005/paths.csv` 的1251白名單根，未擴掃C盤。以目前tracked測試函數及pytest fixture編號核對生成用途，重新掃描tracked程式／設定／文件的具名引用，並查核程序命令列。成功項逐一以CreateFileW讀寫分享衝突探針核對所有檔案／目錄、檔案數、reparse與硬連結；失敗保留。此探針不等於全系統handle列舉，也不保證釋放探針到改名之間沒有競態；搬移前再比快照，Windows改名失敗即停止。

- 成功同C盤隔離 **879個根、108054個檔案**，位置 `C:\ta_iso_1005\四位數編號`；逐項原／目的映射在動作前寫入restore manifest。
- 群組：642個可對應測試函數的純pytest fixture、229個空暫存根、8個標準CacheDirTag與結構已核實的mypy快取。
- r015僅 **d/e/f** 已隔離；g/h/i的全部函數來源未對應，保留其中fixture DB。先前進度說六個都完成已更正，不能拿進度估計替代實際映射。
- R020／R026 user Temp有136個空根已隔離；具引用的r20q、r26m、r26p、r26q及raw custody根保留，沒有把整個R20/R26群組視為可清空。
- 隔離檔案AllocationSize：前次census **4,951,450,624 bytes**，本次改名後實測 **4,951,450,624 bytes（4.611 GiB）**，兩者相等；logical bytes為4,845,871,595。全部檔案inode／大小／mtime／attributes在搬移前後一致，最終879項重新核對metadata雜湊通過。
- **未釋放檔案容量**：同盤隔離保留原檔案，不是清空磁碟。C可用容量由237,980,422,144變為237,505,548,288 bytes；volume變化包含其他活動及metadata，未歸因為本批釋空間。不含目錄索引/MFT的檔案AllocationSize不可當精確volume回收量。

## 回收判斷與還原

Microsoft的[操作旗標文件](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags)描述RECYCLEONDELETE與永久刪除警告，但未提供此機超容量／既有回收內容淘汰邊界的已驗證保障。故沒有啟動回收操作；採[MoveFileW同盤目錄改名](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew)，禁止替換目的路徑、跨盤複製後刪除或任何delete fallback。未改權限。

事前回滾清單：`output/qa/reversible_cleanup_20261005/ROLLBACK.md`及`restore_manifest_pre_execution.csv`；成功清單`moves.json`。先核對metadata與原位置未重新出現，再在repo根執行：

```powershell
powershell -NoProfile -File output/qa/reversible_cleanup_20261005/restore.ps1
# 上式只核對／列出；需實際還原時加 -Execute，任何衝突即停止，不 Force。
```

微型改名／還原／衝突拒絕探針通過；又以真正r015 d（7檔案）反向還原到原路徑，核對全部identity後重新隔離通過。原目錄後續若被新的測試重建，還原腳本停止，不覆蓋。保留首次深層目的路徑MAX_PATH失敗證據；第一筆已立即完整還原，才改短路徑重做。沒有資料損失或永久刪除。

## 保留清單與批准界線

**372個根保留**。58個具tracked或歷史引用的根全部保留，含原20個QA引用；正式DB/raw/model/userfile、當前驗收證據不在可移除範圍。獨立QA／來源快照／runtime副本／先前清理備份／混合用途不能只憑暫存名稱清除。每項精確路徑、原因、引用及容量見`retained.csv`與`retained.json`，分群不是已刪除清單。

19個選定候選未通過占用／權限探針：

- `C:\Projects\PythonProjects\technical_analysis\.tmp_audit_ui_20261004_source_service`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_audit_ui_main`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_g4_capture_focused3`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_g9crp7`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_lm_m6_review01`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_ml_a_scale`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_mypy_g6_registry`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_pcap4`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_pcap6`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_pv2`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_r019_c3c2_20260924_a`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_r020_c0_20260924_a`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_r020_c0_20260924_c`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_r027_phase_db3`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_rf27`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_stageb_p2_junction`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_wp2_industry_gate3`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_wp2_wp5_full_test_output`：讀寫占用／權限探針 WinError 32，保留，不改權限。
- `C:\Projects\PythonProjects\technical_analysis\.tmp_wp3_head`：讀寫占用／權限探針 WinError 32，保留，不改權限。

**永久刪除0、回收操作0，必要永久刪除清單為空**。若將來要求真正釋放隔離內容，`permanent_release_approval_candidates.csv`列出879個精確隔離路徑／原路徑／配置量；這是未批准候選，不是本批要求永久刪除，亦未證明另有內容備份。父層須逐路徑取得授權後另批執行，不能以本次可恢復整理授權替代。

## C／D容量與下一步

沿用交接既有C自然ML request需求215,285,235,712 bytes，以及D formal raw 35GiB persist＋40GiB temp＋200GiB reserve共295,279,001,600 bytes；不降低reserve。

| 卷 | 既有需求bytes | 本次free bytes | margin bytes | 結果 |
|---|---:|---:|---:|---|
| C:/ | 215285235712 | 237505548288 | 22220312576 | PASS（點時間） |
| D:/ | 295279001600 | 300638941184 | 5359939584 | PASS（點時間） |

兩卷在本次只讀量測均不阻塞上述既有容量門檻；D本批開始前已高於門檻，未做D盤操作，不能說是本批清理解除。這是點時間容量結果，沒有啟動writer或授模型資格；每次實際writer仍須按當次request重新查核。

## 90秒失敗至4.5秒成功的driver說明

上一批具體修正是：ProgressTaskWorker start前接started/progress/finished/error/cancelled/native_finished；記錄run-enter/exit、generation、實際UI config及timeout時thread flags／phase／stack；等待改為processEvents＋sleep(.02)，沿用90秒上限；modal保留wrapper避免id重用漏記。成功重試的worker實際run約4.375秒，UI完成等待4.5秒，正常新分析設定PE999／volume ratio min1，與原保存PE1結果分開。

離屏qWait探針只證實額外延遲，舊Batch7使用sleep亦曾timeout，**仍無證據將歷史90秒失敗單一歸因qWait、訊號遺漏或產品bug**；原telemetry不足的歷史根因保持未知。新程序讀回的Request.universe誤查改讀sealed config，及截圖加入已讀取／非空表格與有界350ms repaint，是另外兩個讀回driver修正。完整Native鏈已接受，不重開驗收、不因清理重做。

最終收據`output/qa/reversible_cleanup_20261005/final_receipt.json`、allocation_after.json、moves.json、actual_fixture_restore_proof.json、retained.csv、restore_manifest_pre_execution.csv。只同步指定原計畫與交接，本地commit不push。可恢復整理批次結束，交回父層安排原計畫的後續階段；尚留372根並不等於宣告白名單全部清空。

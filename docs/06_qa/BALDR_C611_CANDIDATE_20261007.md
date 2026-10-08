# c611 固定候選：建置及同版驗證

候選來源固定為 c611ed515ca06ae3c2a8d6b8fa56552c5f7c811b，版本 2026.10.06+c611ed515ca0；不納入工作樹其他聊天的 dirty 變更，也不因後續文件提交改稱新版。包含正常保存研究讀取根、H20 收藏保存／重開、個人收藏本地排隊及基本面副本配置；F17 僅是來源 reader，尚未接完整選股。

新候選在 dist/candidate_c611ed515ca0_1cc2db97/baldr/baldr.exe，53,122,929 bytes，SHA256 d37bed44f21be2a1bde646a54c53097cb3f5a2898693e31efa9fd205b8c5e2ef。source archive SHA256 4336ff7be5ddb8581e3e205ede6397ecfae7321b4a02145f19e6171baa9653bb，依賴鎖 b1a3bb4bd03246c025f09bca3658104aff6c676983c878f46d118cec992df743，建置完成於 2026-10-08 02:06:52.986117 UTC。中央逐值核 source metadata／BUILD_INFO／candidate receipt、archive 與 exe hashes；原 exe SHA ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e 不變。

BUILD_INFO 保持 immutable built_not_validated，驗證收據另存，不覆寫建置收據。中央建置核對 output/qa/c611_candidate_build_root_20261007_a.json 不授同版、原 Main H20 或 Native 資格。

| 驗收範圍 | 目前證據 | 邊界 |
|---|---|---|
| 固定版本／archive／exe／依賴／原 exe 保留 | 中央一致，build terminal exit 0 | 未簽章、不替換原 exe |
| 既有同版隔離回歸 | output/qa/baldr_same_version_c611ed515ca0_60600e21/same_version_receipt.json，passed_isolated_fixture，terminal exit 0 | 四用途／收藏與重開／worker取消／配置／呈現 H20 是既有合成 probe；不代替真保存母體或原私人來源 |
| Python launcher、直接 Qt、-m 與 exe 共用設定／版本 | 上述收據逐值一致，invalid DATA_ROOT 拒絕 | resource_root／frozen形態／screenshot路徑為明示必要差異 |
| 257+1正常 Main 同一 sealed store/query/bookmark | 最新7a2c3157兩模式完整通過，中央逐值核對同query／收藏／rows／basket及source/store inventories | 真producer一次、兩模式讀同一sealed store；合成257+1，不代表實際市場／1000／效能或Native |
| 原十股→2382真 Main 載入／雙擊／返回耗時 | 最新2009ff15e64a完成原十股、684bp／三日期／返回與關閉，但source SHM mtime變動及guard拒絕使terminal exit1 | 有單次階段時間，尚未授原件保護／完整旅程／Native或p95；不重設基線掩蓋變動 |
| 真人閱讀／速度／完整四用途／實際市場資源 | 未驗 | 未發新真人啟動檔，完整 P00–P14/M3仍開放 |

同版驗證首次 attempt 9b8cc079 在印中文狀態時因宿主 cp1252 失敗，未執行案例；原 failed receipt 保留。改設 PYTHONUTF8=1／PYTHONIOENCODING=utf-8 後另開 60600e21 全部通過，不重建、不覆寫候選，也不刪除原失敗。這是驗證工具宿主編碼問題，不是候選程式的中文 UI 失敗。

H20 Main 首次完整 attempt `output/qa/h20_main_canonical_design_20261007_a/attempts/20261008T022030Z_27782a316737/controller_receipt.json` terminal exit 1、18.234秒；未到名單或2382，下鑽速度仍沒有新量測。下一輪只允唯一QA case的明示app-local runtime SQLite，原H20 snapshot必須mode=ro／query_only，正式market DB與任何原來源寫入仍拒絕。不能把runtime必要DDL計數冒稱所有SQLite零寫入。

後續本地 `1e0e28ae` 市場歸屬來源提交不在此固定候選，不重建或修改c611的BUILD_INFO；其中央12項與892檔mypy資格另見市場歸屬QA，也未接完整篩選UI。

後續原H20 Main attempt `20261008T022925Z_9cdc4b7c3ea1` 已terminal exit1：Main建構約4.3秒，初讀10列約54秒後遇 `personal_h20_cohort_changed_during_terminal_read`，未到2382雙擊。SQLite紀錄顯示原source連線0、正式market拒絕3次、另10次對同一原快照的拒絕；中央與分工核對確定該快照是storage config active_root內的exact pin，QA ancestry卻誤要求DATA_ROOT，為測試護欄的根誤用。source/archive inventory不變。原54秒含被拒source的處理，不是成功名單或產品速度證據；修正QA根綁定後另開attempt，不放寬產品finalizer、manifest或來源核驗。

完整母體同版 attempt `baldr_fulln_read_root_257_20261007_f759d97f` 真產製與exact讀回封存已成功，但Python Main因私有COW fixture來源位置與真正OUTPUT_ROOT不一致而未完成啟動。已安全中止並保留日誌，不dismiss來源錯誤冒稱通過；fixture-only預檢與新唯一attempt仍待驗。source readonly attribute不是strict resolve失敗原因：普通／readonly檔在sandbox均拒、elevated均成功；保留原readonlyattribute與全部guard。

`9934f8a8` 已另外修正H20跨結果分頁返回的雙重讀排程，相關路由及Main合成回歸通過；此固定c611依然不包含，不以後續dev狀態修改候選身份。

修正QA source ancestry後，唯一原件 Main attempt `20261008T023759Z_2009ff15e64a` 已完成10/10 available名單、真Qt雙擊2382、原預測684bp與三日期首屏、返回同manifest／2382及零worker關閉。單次受guard量測：Main建構6.500秒、初始名單16.734秒、雙擊前置完整名單重讀16.609秒、個股證據worker16.312秒、雙擊至摘要32.937秒、返回16.625秒。這些僅是該次操作觀測，不是p95／Native或產品速度接受。

該attempt仍terminal exit1、不得授原件保護或完整旅程通過：最後命中 `canonical_main_readonly_boundary_violation`，原snapshot `-shm` 的mtime變動（32KiB、SHA不變）；main DB及其餘原件bytes不變，另有mkdir/write guard拒絕待分類。SQLite mode=ro/query_only不能據此宣稱source metadata全不變。已停止再直接SQLite開啟原快照，不將變動後新baseline當作修好；下一步先唯讀檢查WAL依賴並評估受界隔離reader／明示sealed-only方案。不可直接加immutable=1忽略WAL、checkpoint原件或放寬full-stat驗收。

## 最新完整母體同版資格

`output/qa/baldr_fulln_read_root_257_c611_cowfix_7a2c3157/same_version_fulln_report.json` controller terminal exit0、status=passed。中央直接核counts：258 declared／257 included／1 excluded／257 processed／0 pending／1 missing，2 segments；真public producer114.078秒、exact readback/seal4.750秒，只產一次。Python與exe都使用正常TECHNICAL_UNIVERSE_READ_ROOT，沒有browser root override；query SHA同為 `a5786ac29bc4b8774d5a41a4eea3c08bc82e9e690dadb42c93ddf824ec9717a9`。query／完整counts／page rows／selected snapshot／basket／bookmark／reopened bookmark／原source hashes／store pins等12欄相等，兩個私人COW和OUTPUT根互異，每模式真helper只呼一次。

中央另直接核兩mode terminal exit0、source inventory起訖相等、sealed store不變、denial／network／非預期warning/critical均0，各22個產品模組origins落在固定archive或exe runtime root。Python Main88.360秒／controller96.125秒，exe Main89.312秒／controller99.375秒。首次catalog約0.17秒，但strict query約10.5秒、stock drill約15秒、bookmark save約27秒；不符合P01暖查詢300ms之類效能資格，不能因旅程完整就授速度接受。

這補上前文的固定候選精確Main同版缺口；舊failed attempts與Windows權限／COW fixture path根因保留。BUILD_INFO仍為immutable built_not_validated，完整QA資格由獨立收據聲明。原十股保護、原市場N／1000效能、不同PID完整母體重開與完整Native矩陣仍各自驗收，未發新真人啟動檔。

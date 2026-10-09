# PROJECT_SNAPSHOT（必讀｜目前狀態）

2026-10-09 最新補完接續（優先於下方同日歷史）：固定合成四均線 F02 V11 完整父 Main→收藏→正常關閉→新程序 Watchlist 真實單擊／雙擊重開已由 Root 核收據通過，三組條件59／158／97、頁碼／選取／比較籃保留，來源與收藏bytes不變、worker0、Job清理。這不代表新EXE、原來源或H20真人接受。詳見 [MA 完整旅程審核](../06_qa/BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)。

P01 路徑修正已保存本機 dev `f9ead461`／`30812082`，但最新固定千檔六角色矩陣效能未通過：翻頁p95=239.4695ms，篩選1074.3634ms、排序344.7445ms，後兩者超過原300ms門檻。Root獨立重算90原始樣本並核來源／資料／程序清理；正用既有profile與純CPU診斷定位退化，不重跑相同候選。F12營收完整Main候選c與H20 exact cycle-terminal切片仍在施工，沒有新真人操作入口。完整P00–P14／M1–M3／F01–F23範圍維持。詳見 [P01 效能審核](../06_qa/BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md) 與 [補完缺口](../06_qa/BALDR_COMPLETION_GAP_REVIEW_20261008.md)。

同輪終態更新：P01 v6已完成20頁／1000檔公開讀取，Root直接核child passed、returncode0、來源／資料庫／store前後一致與Job清空；尚未通過300ms效能門檻，下一候選保留五個cold程序及換頁／篩選／排序各30次。H8 Main驗證handle4808已exit1，停於BacktestView初始化缺少合成backtest/presets；Main尚未建成，下一fixture精確補盤點所得presets/versions/profiles三目錄，原失敗與收尾次錯保留。F02 G handle26696已exit1，新diagnostic定位str-only parser拒絕code1000。Root更正先前讀錯compact DTO的判斷：真technical_row是ParentV4Row，其evidence ratio為Decimal或None；下一候選恢復正確邊界並保留診斷，原F bareassert仍未定位。下段「已啟動／未重跑」為取得終態之前的歷史；目前無新EXE或真人入口，完整補完範圍維持。

2026-10-09 本輪最新實測：H7 合成接縫與四檔回歸已中央26 passed，118筆檔案pins／77個獨立路徑一致；唯一Main驗證已啟動（owner handle25842），尚無Window／旅程接受結果。P01 v5真正讀到1000檔selection，但QA誤把ReadSelectionPage當可直接序列化的內頁，原失敗保留；v6真DTO中央8 passed，已加入20頁全1000碼與跨段row實讀，來源清冊正恢復測試快取後續驗，未有新效能通過。F02 E已走正常F17 exact-open，後因oracle只接受list而真method contract回tuple失敗；新F僅修QA oracle型別，Decimal與完整22cases/reopen不變，未重跑。長路徑QA修正中央獨立通過；上述皆不是原2382／684bp、新程序收藏或同版EXE真人接受。完整P00–P14／M1–M3／F01–F23、原300ms效能門檻與後續產品整合仍保留；現在無新真人操作入口。

2026-10-09 最新並行續驗（取代下方早期施工狀態）：H20 H6 MainWindow未建，SQLite兩公開alias不一致的原失敗保留；新alias helper 12項單測及fixed guard＋E success／primary-failure合成接縫通過，H7正接完整Main，尚未實測。F02 B provider-only已實際exit0：8個protected roots前後一致、provider1、raw19632筆、唯讀SQL2、producer／bundlewriter／query0、Job清空；C完整22條件案例及canonical reopen正準備實測，不代表全F01–F23。P01三角色parentchain v3 hello實測exit0，venv環境保留、launcher/base/conhost各1、Job零殘留；SystemExit0誤印failure的診斷噪音原樣保留，新v5正接回d12完整1000檔流程。原page/filter/sort p95失敗與300ms門檻仍有效，尚無新效能結果。原2382／684bp、收藏新程序與同版EXE真人驗收仍待；根目錄副本已備份但未移動／刪除。無新EXE或真人入口，完整P00–P14／M1–M3／F01–F23範圍保留，詳Root並行審查。

2026-10-09 續驗終態補記：H20 G2 固定 archive 重建已經中央逐檔核驗4161檔／77,229,228 bytes完全相等，7項static preflight通過；但完整synthetic嘗試在preparer引用未定義output_root時terminal failed，Main未啟動，Job清理完成且origin／artifact保持一致。H先後修正output_root與SHA表示法，H2單獨preparer已中央實核passed／exit0／來源一致／Job清理，同固定版完整synthetic於keeper sibling配置時failed、MainWindow未建；H3正核兩個exact E輔助檔本地複本後接完整流程，尚無真人入口。F03三路暫存協調器已中央重驗並保存`736dc9d0`；多parent固定版已中央完整重驗3passed／497.32秒，含指定RuntimeError cause及首段暫存清空，成果保存`ac5a3d1f`；尚無共同發布資格。F02 F精確mode候選已批准唯一provider-only，但native因scope constructor的generated init caller未納入而failed；G純呼叫鏈契約中央通過，G2已審一行retarget到全新同bytes target並接派唯一provider-only，full query尚未批准；下段G1／e狀態為此補記之前的歷史。

2026-10-09 最新補完核驗（取代下段同日早期施工狀態）：F03 KDJ query 契約已保存本機 dev `a56a5cff`，中央定向 18 passed；F06 bounded unqualified collector 已保存 `6bf71603`，中央 11 passed、正常 scoped mypy／compile 通過。MA、KDJ、volatility 尚未接成共同來源資格與原子發布；新三成員 observer group 的單一真 parent 故障／取消矩陣已有 agent 測試，仍待中央複核與多 parent／發布接線。H20 同一 frozen E 的四個 native 清理案例通過，但均未進 Main；F 完整啟動嘗試因來源樹新增兩個 pyc 而在 Main 前拒絕，G1 固定 archive 重建遇長路徑限制，保留兩次失敗並改準備全新短路徑 G2，尚無新 EXE／真人入口。F02 continuation c、d、e provider-only 均 terminal failed：c 為不存在 local DB URI 解析，d 為 QA provider 使用不存在的 VerifiedState 欄位，e 為 exact store pin／counts 不符且 SQLite 連線計數為 2；完整 query 矩陣尚未執行，正在只讀定位實際契約差異。1,000 檔換頁／篩選／排序 p95 原失敗、原 2382 約20秒及收藏新程序／同版 EXE 驗收仍待，不縮減 P00–P14／F01–F23 補完範圍。

2026-10-09 補完並行工程補記：本機 dev `ff2c0cf5` 已保存 F03 有界、未核資格的 KDJ 收集骨架，Root 重驗 12 passed、兩檔 scoped mypy clean；不含 full-N 資格發行、複合查詢或 UI。H20 clone-scoped installer seam 已核成功，但真 H20-first／市場收尾、完整 Main 與新 EXE 尚待驗。F02 續驗的來源 DB、pointer 與原失敗 receipt 雜湊吻合；尚未執行新 query continuation。F06 Decimal 波動原料 leaf 已於本機 dev `8816644c` 保存，Root 凍結來源重驗 13 passed、兩檔 scoped mypy clean；BB30 母體標準差與 ATR14 簡單平均方法已明示，另於 `4a1ead28` 保存未核資格的波動複合請求／predicate／排序契約，Root 重驗 23 passed、兩檔 scoped mypy clean；尚未完成全母體 reader-issued 複合結果、收縮／突破條件或 UI 整合。現在沒有新的真人驗收啟動入口，不能以小測試替代原 2382 下鑽、效能或同版 EXE 驗收；細節見 [Root 並行審查](../06_qa/BALDR_PARALLEL_ROOT_REVIEW_20261009.md)，完整範圍沿原單一補完計畫。

2026-10-08 排程工程補記：Bank heartbeat mtime、Paper 決策 freeze archive／blocked fills、Decision watchlist 查詢已修正；G9 CMD 總 timeout 改為 14400 秒。四個既有 Task 已實際套用背景 action，XML／ACL／trigger 保留且未手動 Run。主要回歸 262 passed／4 skipped，另 launcher 16 passed；完整 Decision 診斷 dry-run 約 39 秒完成，無自然資格。G6 skipped_locked、Forward 1538 缺價、舊 Allocation source revision 仍 blocked；Scheduler Operational 的 UAC 已取消，尚未啟用。今天自然整鏈尚未通過，證據與限制見 [10/08 QA](../06_qa/BALDR_SCHEDULE_REPAIR_20261008.md)。

## 歷史快照與驗收入口

2026-10-06 至 10-07 的產品補完開工、首波及 M2 逐輪狀態已由較新的 WIP checkpoint／恢復 QA 取代，不作目前狀態依據。保留詳細歷史與證據入口如下；本 Snapshot 不重複保存舊測試數字或逐輪施工日誌。

- [完整快照歷史](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md)：早期狀態、舊 branch／worktree 與當時修正脈絡。
- [產品補完首波 QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md) 與 [M2 工程 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)：保留相應日期的局部驗證與限制。
- [排程修正 QA（2026-10-08）](../06_qa/BALDR_SCHEDULE_REPAIR_20261008.md) 與 [排程修正 QA（2026-10-07）](../06_qa/BALDR_SCHEDULE_REPAIR_20261007.md)：保留各輪範圍及原始結果；目前排程狀態仍以本 Snapshot 的最新狀態為準。
- [中央 cohort／natural／BBUI 整合](../06_qa/BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md)、[Final authorized union](../06_qa/BALDR_FINAL_AUTHORIZED_UNION_20261006.md)、[工程與決策差異](../06_qa/BALDR_ENGINEERING_DECISION_DELTA_20261006.md)：分別保留跨包、授權測試與證據資格界線。

## 工作區與資料保護

2026-10-09 本機 dev checkpoint 為 `a48a86afd4de0fd9a5f85e2dd09cf370ad42281b`；checkpoint 建立時位於 `dev`、工作樹乾淨且未 push。這是 WIP 交接，不代表產品完成；驗收界線與續接事項見 [交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)。42 個舊 checkout 的 refs／extras 恢復備份是 2026-10-07 收據，見 [兩分支恢復 QA](../06_qa/BALDR_TWO_BRANCH_RECOVERY_20261007.md)。main 是受控使用版，不等同 dev 全部開發收據已公開。

市場根由 `TWStockConfig`／`DATA_ROOT` 決定；私人資料、模型／source lineage、原失敗 raw 與 immutable receipts 保留。2026-10-06 repo-temp cleanup terminal 只移除 4 個空 root 共 8 目錄、0 bytes；當日清冊中的 14 DB、三工具 root、2070 Temp root、其餘 354 repo 暫存 root 與未釋放候選 50.6 GiB 是該次盤點／處置範圍，不是 10/09 冷封存後的即時清冊。用途、容量時點與恢復規則見 [資料資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)。

2026-10-09 冷封存終態：第一批 6/6、第二批 28/28，共 34 個根、158,712 個檔案、198,246,544,124 logical bytes（約 184.62 GiB）；終態收據記為完成，34 個 C 槽原路徑均為目標相符的 Junction。兩批執行收據記錄全檔 SHA-256 核驗通過；[終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md)只核對收據及 Junction metadata，沒有重新計算全量 SHA。容量變化與 postflight 數值均是當時快照，不代表目前可用空間；正式 D 槽資料及既有 E 槽舊封存未改。

## 下一步與導航

產品補完已在 2026-10-09 本機 WIP checkpoint 後恢復開發；恢復基線、當輪分工及初步通過／失敗／未驗證界線見 [恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md)。原 checkpoint 交接與未完成驗收仍見 [交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)及各具名 root review。checkpoint、局部測試或文件整理均不關閉 Gate。方向見 [Roadmap Hub](DEVELOPMENT_ROADMAP.md)，邊界見 [目前架構](../01_architecture/system_architecture.md)／[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)，完整文件清單與維護流程見 [文檔索引](DOCUMENTATION_INDEX.md)。

2026-10-06 可攜版交付歷史：當日交付 Windows onedir `dist/baldr/baldr.exe`，需保留整個資料夾、不需 IDE／全域 Python；外部資料、輸出與私人設定分離，未內附 FA_Data 或個人模型。D01 合法警告保留 last success、warning 與 freshness/date 診斷，Runtime 維持 guarded。當日 main 同步及 branch 狀態只代表該次交付，不代表目前分支狀態；首次操作、SHA 與驗收界線見 [可攜指南](../07_guides/PORTABLE_WINDOWS.md) 及 [可攜 QA](../06_qa/BALDR_PORTABLE_WINDOWS_20261006.md)。


2026-10-07 M2、H20 與 v4 候選的逐輪工程摘要、測試數字與未驗限制保留在 [M2 工程 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md) 及相應具名 QA 原件。此處只提供歷史入口；目前通過／失敗／未驗狀態看本頁開頭、[恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md) 與 [交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)。

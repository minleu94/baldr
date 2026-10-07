# 推薦工作區真人回饋處理（2026-10-07）

## 範圍與結論

使用者回報：H20 名單的2382下鑽後摘要無有用資訊、不知道收藏位置、全股票三個預設策略同遇官方日曆錯誤，以及非全螢幕時歷史版本控制項擠壓。本輪修正日曆外部來源接線、推薦失敗說明與窄欄排版；原碼隔離回歸通過，尚未更新候選 exe、尚未完成同版及 Native 驗證。H20 真保存來源整條旅程另在驗證，不能宣稱此回報已全部解決。

## 原因與修正

- 舊 `MarketSessionCadence.for_config` 預設日曆位於程式相對 `output/paper_execution_eod_replay/calendar_cache`；可攜 bundle 不包含該本機產物。共同啟動／TWStockConfig 新增 `OFFICIAL_CALENDAR_CACHE_PATH`，明示外部來源，預設沿外部研究根。這證明接線缺口存在，未證明使用者實際使用的版本或 cache 狀態。沒有放寬官方 cache hash、期限、coverage 或可得時間核驗。
- 推薦 error callback 對共用日曆阻擋提供中文原因，指出換策略／放寬條件無效；原完整錯誤保留 detailedText，舊有效結果與 stale generation guards 保留。其他錯誤仍沿原處理。
- 歷史版本排版原依右側結果寬度，與左側設定欄實際空間不一致。現改依左欄寬度垂直排列版本選擇與兩個按鈕，保留完整工具提示、輔助說明及 Tab 順序。
- H20 正常路由在報告成功後讀回模型原來源、更新五問結論與可見日期／狀態；原 H20 詳細 label 在收合來源區。一般報告失敗時 `reportLoaded` 不發出，H20 reader 不啟動，此控制流程限制仍保留。未讀正式／私人 root 來猜測使用者2382當次原因，亦未用注入 DTO 代替 canonical 整條成功證據。

## 驗證

| 檢查 | 結果與邊界 |
|---|---|
| 窄欄／既有推薦布局、共同設定／日曆來源、H20摘要呈現 | 30 passed；H20仍是既有呈現案例，不是本次真人2382通過 |
| 新日曆來源與實際cache reader | 8 passed：設定優先序、bundle拒絕、frozen外部預設；有效來源可核驗，缺失／過期／竄改／未來取得保持阻擋，cache bytes 不變、無網路fallback |
| 新日曆失敗畫面與推薦execution state | 11 passed：日曆專屬說明、非日曆錯誤不誤分類、stale回呼不開dialog、舊結果保留 |
| mandatory 更新頁 | 85 passed |
| mandatory 更新頁validator | 初次 Windows managed sandbox 21 passed／3 failed／4 skipped，原因為新建隔離Temp strict realpath WinError5；原失敗不抹除。專用Temp重驗25 passed／0 failed／4 skipped，raw `output/qa/baldr_completion_m2_20261007/update_root_4.log` |
| mandatory 全域mypy | 862 source files，0 errors；施工時新technical adapter出現6項型別錯，該leaf修正後再驗通過，原錯誤工具輸出保留 |
| py_compile | 本輪日曆、推薦UI及其測試7檔通過 |

非 Native、人工作業未跑、未觸發正式 Task、未更新原 `dist/baldr/baldr.exe` 或 active delivery、未讀寫正式市場 DB，也未修改模型／預測／交易資格。

## 修正版再驗方式

先核開啟程式的完整版本；H20選2382下鑽後看摘要結論與日期，再返回核原來源／選取。H20收藏目前不列驗收。每日研究收藏另依Manual原入口核對。修正版同一有效官方日曆設定下再跑三預設策略；無有效日曆時必須清楚阻擋，不能記成分析成功。非全螢幕左欄核三控制項全文、可點、Tab順序及版本工具提示。完整入口見[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-07-真人回饋摘要收藏與推薦失敗)，原完整補完範圍沿[單一計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)。

## 同版候選更新（原碼驗證之後）

固定來源 `2b6fda426b6fd69919fd563cc3389293b591f9b1` 已建成 `2026.10.06+2b6fda426b6f`。版本字串沿固定來源 metadata，不能依驗證日期改寫。候選位於 `dist/candidate_2b6fda426b6f_3ed9cb87/baldr/baldr.exe`（52,436,967 bytes），SHA-256 `f18e4fb154d1662b544d5e0c5f5be1cd7ebcfdb744191444de215dde048cffbd`；固定 archive SHA-256 `b2bfd6ffbd14cf4dd3c8ea19c93aac7c807090547cee69a70404ae3ff4b7705a`。

原同版隔離比較通過：`output/qa/baldr_same_version_2b6fda426b6f_5c5f2aa4/same_version_receipt.json`，raw SHA-256 `82d13dcfaf2af82318d9d99f9636aa6c65ffe7e25d3ba622820abea030758d7e`。包含啟動設定／版本、四用途 synthetic旅程、未訓練模型artifact、保存新程序、H20呈現與原異常案例；H20仍非完整保存來源旅程。`BUILD_INFO.json` 保留 built_not_validated 建置時快照，另增 `VALIDATION_INFO.json` 綁定實際驗證收據，沒有事後改寫建置證據。

另以同一外部 synthetic 日曆 bytes及相同共用JSON，在固定 Python 與 exe 沿實際 cache reader／RecommendationInputSession交易日邊界逐值比較通過；同一缺來源時重現使用者的 `official_calendar_unknown:2026-09-16…`，有效來源時通過，bytes未變且無網路。收據 `output/qa/baldr_completion_m2_20261007/calendar_same_version/comparison.json` SHA-256 `2481a4de87b7da2a29eb70c9b69c4e4e08e39592ec2145b6ecb82016550a7296`。這不是三個真實策略執行。初次driver以相對路徑被launcher切換cwd後找不到檔、第二次managed strict realpath WinError5；改絕對路徑與受控隔離執行通過，原失敗工具輸出保留。

2026-10-07T19:00:25Z 唯讀既有官方cache範圍2026-09-16～10-07核驗通過，cache原捕捉／可得時間2026-10-06T00:25:04Z、期限10-13；原bytes SHA-256 `37083f2b35c79d6d0e11ccd7ba2f5583be4b8c09babdb96e9518e4f0107a6157`。原件保留於 `output/paper_execution_eod_replay/calendar_cache`；未開市場DB、未下載／改cache／取得PIT或臨時停市覆蓋資格。

真人啟動helper `output/qa/baldr_completion_m2_20261007/start_feedback_candidate.ps1` 只核候選SHA並給child上述原日曆路徑，其他市場／個人設定沿原配置，**沒有自動執行**。PowerShell語法檢查通過；若來源期限或hash不符仍由程式拒絕。原exe SHA仍 `ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e`，active delivery／Task／私人設定未改。Native及使用者2382／三策略／窄欄仍待實測；全母體UI／producer／technical adapter另在施工，未包含此候選，也未把原完整補完範圍改成完成。

## 真人啟動設定的唯讀核對補記

正常主機環境以純 `resolve_application_settings()`（未apply、未建目錄、未開DB）核對：`C:/Users/archi/AppData/Local/baldr/config.json` 存在、configured=true，行情／輸出仍是原 FA_Data／output，研究根是主機LOCALAPPDATA的baldr/research_state；目前portable設定沒有 `OFFICIAL_CALENDAR_CACHE_PATH`。受限sandbox的LOCALAPPDATA會被虛擬化成獨立空根，該環境的configured=false不能當成真人未設定的證據。原候選啟動helper只向child指定原官方日曆cache，沒有改寫上述JSON或其他私人設定。這仍不證使用者正在開啟的exe版本、2382讀取狀態或三策略的實際執行成功。


## H20 摘要獨立讀取已整合（dev，候選待更新）

前文「一般報告失敗不啟動H20」為修正前狀態；目前activeContextChanged直接對原保存cohort精確pins核驗，不等報告成功。個股研究上方新增「保存的個人 H20 研究預測」，顯gross、預測／來源／特徵日期與實際結果尚無已核驗結果；一般報告錯誤仍保留，H20資訊可獨立讀回。「重新核驗保存預測」明示重讀原來源；pointer變動返回保留原列表／排序／選取並拒絕新版本。H20收藏尚未實作。

中央整合workbench／完整母體／H20旅程96 passed、validator25 passed／4 protected skips、mypy870檔通過；H20公開來源旅程使用真SQLite／保存reader，模型contract為明示未fit合成邊界。原Qt測試pump飢餓失敗已定位並保留，同一fixture改等待方式full route3.78s；未改production reader或放寬guard。完整證據見[M2 QA](BALDR_COMPLETION_M2_20261007.md)。原真人2382、三真策略、窄欄與新candidate／同版仍未驗，目前不用使用者用舊exe重驗。

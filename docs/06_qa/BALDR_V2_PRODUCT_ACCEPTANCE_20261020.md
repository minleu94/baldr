# Baldr V2 產品驗收

本文件記錄依 [V2 Blueprint](../superpowers/specs/BALDR_V2_PRODUCT_UX_BLUEPRINT_CONSOLIDATED_20261020.md) 開發的 Source 分支證據。基線 `9ce92743`，分支 `codex/baldr-v2-product`。目前施工中，尚未交付 V2 Release Candidate；既有固定研究13不包含本輪變更。

## M0 與所有權

有界核對涵蓋 Main／導覽、兩種個股來源、選股、題材、收藏、Journal／Forward、真實手動持倉／Paper、回測／Registry、主題與資料更新／Runtime。重用既有服務及保存契約，未發現需推翻 Blueprint 的安全衝突。Root 擁有 Main、Router、共享契約與整合驗收；Luna 分別完成來源盤點、投資分區、共用元件、定向測試與文件同步，均未自行執行 Python 驗證。

本機可恢復狀態與逐項搬遷表位於 `output/tasks/baldr-v2-product-implementation/`。原補完任務的狀態、固定包、未完成金融資格及正式資料均保留。

## 前期 M1：導覽與投資分區

Source 已接四主頁、齒輪與一層子頁列；原九工作區 key／callback 保留。共用個股詳情保留主頁高亮及原服務的返回核驗；頁內上一／下一不堆疊來源。搜尋須明選，題材結果綁載入版本，變版或忙碌時拒絕舊選單。投資分區以原 widget identity 保留九個舊子頁，手動／Paper／研究紀錄各有帳種說明。

這一階段是 Shell 增量；以下 M2–M4 段補記後續整合。子頁可到達不等於該里程碑已驗收。

| 驗證 | 實際結果 | 原始證據 |
|---|---|---|
| QA001 編譯／定向 | 編譯 PASS；68 PASS、3 SKIP、4 FAIL。四失敗為新增 Qt 測試替身不支援 weak reference，已修 | 本 task `qa001_focused` |
| QA002 導覽／來源擴充回歸 | 編譯 PASS；89 PASS、3 SKIP、1 FAIL。舊同查詢返回測試仍要求重開 session，與 HEAD 已有精確重讀流程不符；修正呼叫假設，保留來源／頁面／選取核驗 | `qa002_integration` |
| QA003 持倉舊路徑 | 69 PASS | `qa003_required/00_stdout.log` |
| QA003 Workbench 強制回歸 | 85 PASS | `qa003_required/01_stdout.log` |
| QA003 validator | 23 PASS、2 FAIL、4 SKIP。QA 的 TEMP 採 C 槽 junction 別名，與 F 槽 resolved data root 不符；改實體 TEMP 重驗，未放寬資料守衛 | `qa003_required/02_stderr.log` |
| QA004 validator | 25 PASS、0 FAIL、4 SKIP；實體 TEMP 解除測試根路徑衝突 | `qa004_integration/01_stderr.log` |
| QA004 指定全範圍 mypy | PASS，1088 source files | `qa004_integration/02_stdout.log` |
| QA004 擴充回歸 | 95 PASS、4 SKIP、1 FAIL。比較返回也沿同查詢重讀；已修正第二處過時 opener 假設，尚未重跑。既有 live-return 測試包含跨查詢重開與原件破損拒絕 | `qa004_integration/03_stdout.log` |
| 正常 Main 原生視窗 | PARTIAL：真正 Main／實際服務、全新隔離根啟動成功，1280×760、實際 DPR 1.5、worker 歸零；已檢視首頁缺件降級。切頁操作前使用者以實體 Escape 停止 Computer Use，本輪不再輸入 | `native005/history.json` 及首頁圖 |
| 五旅程／其他尺寸與 DPI／保存 fresh | NOT_TESTED | 待整合驗證 |

QA001–004 Job 均自然排空，三個 PID 陣列為空，process／Job handles 關閉並釋放同工作區 mutex；8 GiB committed memory、12 程序上限不變。原生 Main 另依既定 240 秒正常關閉，由其 owner wrapper 保存閉鎖收據。原始 FAIL 保留，不以後續 PASS 改寫原收據。

原生首頁發現的全域資料狀態文字擠壓已修，QA013 正常 Main 17 路由寬度皆至少180。原首頁多子頁也已在後續 Source 改為單頁；尚未做原生重驗。

## M2–M4：Source 整合與正常 Main

市場以同一個方向控制切換強弱股／產業，題材只從明確設定或使用者明選的版本目錄載入已完成且到可用時點的原件；歷史 manifest 仍核 exact SHA。綜合選股保留原來源、三態／分母及比較籃，H20 獨立置於 ML 研究；查詢截至不冒稱逐筆資料日。共用個股以章節與動作切換呈現，保存時報告保持獨立 snapshot-only reader。

時間軸沿同一 Journal 與三種 typed note readers 索引原文／修訂，原件回訪先 fresh 逐欄核對；價格再驗原來源，報告只顯示保存副本，題材明選原 manifest。Forward 僅在明載結果身分時連結；500筆是讀取合併後顯示上限，現行 reader 仍全讀，不宣稱來源端有界。策略庫可瀏覽登記及保存版本，只允精確目前版本進入現行回測設定；歷史保存版不偷換成目前版本。

回測保留原引擎、Registry 及拒錯比較，使用平面結果選單；固定假設只讀當次或保存原值，期末／逐日訊號只投影原報告觀測。手動、聲明研究與 Paper 分區保持原帳本，Paper 增加文字及虛線區分。儲存頁只盤點明確位置容量及有界 Trial 大小，引用未核一律保留，沒有刪除操作。首頁重排原 widgets／DTO 為單頁，原證據及進階來源都有明確入口與返回。

| 驗證 | 實際結果與限制 |
|---|---|
| QA006 | 92 PASS／1 SKIP／2 FAIL；既有題材用途文案與原生 thread 終態等待已修；後續定向通過 |
| QA007–009 | 保留新測試語法／Qt fixture／junction根與精確 page placeholder、文案預期等原失敗；QA009為224 PASS／1 SKIP／6 FAIL |
| QA010–011 | task helper pins經junction誤拒後僅允ROOT或本TASK；mypy五項明確型別錯誤已修，原失敗保留 |
| QA012 | compile、mypy（1100 files）、定向測試、Workbench、validator 命令均 return code 0。最後的 offscreen Main 命令 return code 1：市場路由視窗高 821px，超過 760px；此布局失敗後續修正，原收據保留。上一個 mypy 命令成功，不能因最後命令失敗改寫為失敗。 |
| QA013 | compile、market定向5 PASS；正常Main全部17路由在1280×760，另驗1440×900／1920×1080首頁；無modal/errors、workers0。隔離空資料／原服務，沒有替換服務或注入價格；offscreen不代表native |

QA013 closure SHA `bf3f65d99b3ee0450db887746d54b780c7fcc9ae18abe888d1026b447ef04200`。所有本輪 Job 均自然排空，8GiB／12程序上限、handles關閉與mutex釋放保持。正常Main截圖與原始JSON在本task `main013/`；後續個股純自選、來源內比較與一般查股回測預填、新程序保存／回訪正進行 QA014，尚不宣稱通過。

## QA014–020：個股動作、整合回歸與復原

QA014 原收據為 compile PASS、定向測試失敗（`qa014_detail_fresh/02_stdout.log` 保留 105 PASS／2 FAIL）；兩項涉及動作狀態與測試替身 NameError。QA015 原收據為首命令失敗，不能用後續結果改寫原收據。QA016 對個股三項動作的定向測試 PASS（`qa016_detail_debug/receipt.json`），屬局部證據。

QA017 六個 scoped commands 全部 return code 0，包含 Workbench 測試、更新頁測試與 validator、`main_journey.py --phase first/fresh` 及 offscreen Main。`03_stdout.log` 明示一般查股保留價格缺件、報告與判斷保存、fresh 回訪、純自選語意分離、返回時間軸選取及回測只預填；`05_stdout.log` 覆蓋 17 路由於 1280×760、DPR 1.5。兩份 journey 輸出均標 `native_gui_accepted=false`、`financial_qualified=false`。因此可支持旅程1的局部流程與路由狀態，不能替代五條旅程完整 Main、原生 GUI 或真人接受。

QA018 原定向整合收據保留兩個失敗；修正後 QA019 同一測試組因 Windows access violation `3221225477` 中止，兩份原收據均保留。QA020 執行前後各核對 57 個 source pins 相符；後續 source 增量另行驗證。QA020 命令1與2各 30 PASS；命令3綜合選股／官方處置收入組為 11 PASS／1 setup error，發生於 `test_original_view_daily_actor_pages_bookmark_exact_reopen_and_shutdown` setup 的 synthetic capture scope `path_link_rejected`。根因是 fixture 所在 output junction 未 resolve，並不表示應用安全 guard 失敗。spec 後續列出的 Workbench／validator／mypy／journey 命令未出現在此 run receipt，故標為未執行，不推論其通過或失敗。QA020 receipt `full_gate_accepted=false`，整體 V2 尚未接受。外層 owned closure receipt 記錄 Job 已排空、handles 關閉、mutex 釋放且無 forced cleanup。原始收據與輸出仍在 `output/tasks/baldr-v2-product-implementation/qa020_product_integration/` 及 `single_owned_qa_45299e2894ad430c9271eda9b4ed60fd/`。

## QA021–025：修正後證據與仍未完成的出口

| QA | 實際結果 | 原始證據與解讀 |
|---|---|---|
| QA021 | 編譯 PASS；整合測試 12 PASS／1 FAIL／1 ERROR。FAIL 為新測試替身 type 不唯一；ERROR 為舊 fixture 長路徑下 `_tree_signature` extended walk 遇到 `WinError 3`。後續已改用專用測試子類並修正 extended walk，沒有放寬產品 guard；本批沒有重跑 QA021 原測組證明這兩項修正，原收據仍是失敗。 | `qa021_product_integration/00_stdout.log`、`01_stdout.log`；原失敗保留。 |
| QA022 | 編譯 PASS、wrapper 13 PASS、Workbench 85 PASS、validator 25 PASS／0 FAIL／4 SKIP、mypy 1102 files PASS。Main018 first 由 helper 使用不存在的 route key `watchlist` 觸發 `StopIteration`；有效 key 為 `lists`，屬驗收 helper 錯誤，不是產品路由失敗。 | `qa022_required_and_main/01_stdout.log`–`05_stdout.log`；Main 證據 `05_stdout.log`。不把最後一項 helper 失敗回推成前面命令失敗。 |
| QA023 | `main_journey023.py` first/fresh 均 PASS；17 routes 在 1280×760、DPR 1.5、search context 寬度至少 180、worker 0；offscreen Main PASS。該 run 的 R07 journey helper first 因 import audit 拒絕 `NUL` 失敗，原失敗保留，並由 QA024 專用 helper／receipt 接續驗證。 | `qa023_journeys/01_stdout.log`–`04_stdout.log`，`journey023/first_result.json`、`fresh_result.json`、`qa023_journeys/03_stdout.log`（17 routes）。QA023 receipt 有失敗命令，不能稱整個 spec 全 PASS。 |
| QA024 | scoped commands 全部 return code 0：編譯、wrapper 13 PASS、Workbench 85 PASS、validator 25／0／4、mypy 1102 files，以及固定 10/16 三來源副本 Main first/fresh。正常 Main 驗證 25 鏈、90 題材、CoWoS 21/21 個股價量觀測→2330→返回、題材 note revision 保存及新程序 canonical identity 回讀；三來源檔 SHA 前後不變。一般個股行情仍是隔離空資料，故為局部旅程證據，不是金融資格、PIT、native 或真人接受。 | `qa024_theme_and_required/00_stdout.log`–`06_stdout.log`、`main_research_journeys_r07_qa024/{first_result,fresh_result}.json`。closure SHA-256 `384bdf19b4c1438c83d2b6014516134b72665c78b2234cf91d72c9502bba1ee2`，receipt `single_owned_qa_4a83dfced84c4f0aa7adf2a43f276a11/receipt.json`：Job PID 清空、handles 關閉、mutex 釋放、exit 0；`full_product_accepted=false`、未改正式產品。 |
| QA025 | 指定文件／來源測試 82 PASS／4 SKIP；route 與 context 命令 return code 0，輸出未列 Unknown。全域 `document_control.py check --context-metadata` return code 2，回報多筆既有 `output/trial`／`output/tasks` junction 外部連結越界；沒有以此結果改寫文件或宣稱檢查通過。 | `qa025_source_and_documents/01_stdout.log`–`04_stdout.log`。此回合未執行 backend。 |
| QA026 | 原始 UI／日營收流程測試 1 FAIL；由原 view 打開候選時，session 以 `monthly_revenue_yoy_index_v2_source_open_failed:DailyMarketMonthlyRevenueReadSessionV2Error` 失敗。不可把這項產品路徑失敗說成成功。 | `qa026_revenue_flow/00_stdout.log`、`receipt.json`。隔離且唯讀的來源診斷 QA032 後來成功，不改寫此 receipt。 |
| QA027 | 指定 Paper／回測邊界命令的 helper py_compile PASS；`main_paper_boundary_r11.py --phase first` 在 150 秒逾時（return code 124，owner 強制結束程序），未產生可用 journey 證據。隔離資料缺 `twstock.db` 及 benchmark preview 檔亦見於 stderr。 | `qa027_paper_backtest/receipt.json`、`01_stderr.log`。 |
| QA028 | 小型合成 fixture 診斷未完成，尚未取得月營收 session 成功開啟的證據；原失敗保留。後續 QA031 改用既有 QA026 來源唯讀定位原因。 | `qa028_monthly_diagnostic/receipt.json` 及原始診斷輸出。不能外推為產品或來源資格通過。 |
| QA029 | R09 backtest journey helper first 以 1 結束，沒有建立任何已檢核項目。helper 自行加上的預設成交限制停止條件阻止執行；另有隔離 audit 將三次正常 `NUL` 開啟記為 denied write。受限 120 點資料副本及既有 Registry 元件 source SHA 前後相同，沒有 network attempt。 | `qa029_backtest_main/receipt.json`、`01_stdout.log`、`01_stderr.log`。此結果是 helper／audit 未通過，不能當作回測產品功能結果。 |
| QA030 | `document_control check --task ... --path ...` return code 2。輸出列出 17 個 Must 文件未登記，另有 `theme_momentum_filter` source/test 未命中自身 change patterns；結構核對限制亦明示不證明文件語意或產品 Gate。 | `qa030_scoped_document_check/receipt.json`、`00_stdout.log`、`00_stderr.log`。 |
| QA031 | offscreen Main route smoke 17 路由正常、無 messages/errors、worker 0；但月營收 source diagnostic 仍 return code 1（protected root reparse point），R09 backtest first 在 420 秒逾時（return code 124，owner 強制結束）。QA031 未完成保存／fresh journey，不能由路由 smoke 推論通過。 | `qa031_daily_journeys/receipt.json`、`00_stdout.log`–`03_stderr.log`。 |
| QA032 | 使用 QA026 已存在的合成來源檔，以獨立 CASE 唯讀打開月營收 session 成功（`open_succeeded`）；來源 fingerprints 前後相同、無正式資料寫入。這只確認受限 physical diagnostic 能開啟原件，原 QA026 UI 仍失敗，沒有驗證原 Main view 或真人操作。 | `qa032_physical_monthly_diagnostic/receipt.json`、`00_stdout.log`、`.tmp_v2_r12/CASE_qa032_monthly_source_existing/receipt.json`。 |
| QA033 | 七個命令全部 return code 0：helper 編譯、正常 Main Paper 缺件拒絕及手動研究日記 first/fresh、原月營收 view 測試 1 PASS、兩筆正常 Main 回測保存與 fresh Registry 精確讀回、scoped 文件結構檢查。兩策略資料指紋不同，績效比較按原契約拒絕；搬移的舊 run 絕對路徑亦被拒絕。 | `qa033_journeys/receipt.json`、`r09_qa033/{first_result,fresh_result}.json`、`main_paper_boundary_r11_qa033/`。R09 狀態仍為 PARTIAL；未證明相容比較、真 Paper 帳本或金融資格。 |

QA033 closure SHA `1905734286700f7930b731900d2097aaec9a6d70047f40113fe87e448f78944d`；Job 自然排空，handles 關閉、mutex 釋放，無強制收尾。QA032 的診斷 PASS 與 QA033 原 view PASS 分開記錄；QA026 原 FAIL 保留。全域舊 junction 連結檢查仍是局部未解，scoped check 不代表全域通過。

QA034 正常 Main 的真 WorkbenchSourceService 缺件出口通過：沒有每日快照狀態檔時，候選為零、無來源身份、選單及開啟按鈕停用，按鈕不會誤入個股；未生成候選檔。QA035 新增月營收明確個股入口與短期來源回返契約，25 項定向、原 view 真 fixture 1 項、Workbench 85、validator 25/0/4、mypy 1103、17 路由 smoke 及 scoped 文件檢查通過。同輪 R17 first 正常 Main 追加同條件 MA run，真正指紋相同且原兩筆 metadata/Parquet 保持；fresh 因比較讀取器不識單股原存 `equity` 欄失敗，故整輪仍 FAIL，closure `076a8ca931dfd59179744286ed8d6026035c1fc06f3cf5a4c0f32909c0e6bcbb`。

QA036 將明確 `single_backtest` 原曲線在比較副本轉接欄名後，七命令全部 0：編譯、47 項日期／精度／保存／比較測試、正常 Main fresh 同指紋比較、Workbench 85、validator 25/0/4、mypy 1103 及 scoped 文件檢查通過。真正讀回 120 個共同日期、240 列標準化權益，原來源與 QA033 原件不變，未重算原回測或覆寫 QA035 失敗。closure `ef6ef15e4d3f0978eecc338a9b802e5a84c966a65bdc4d6eec0a42fcc53df6f1`；兩輪 Job 均自然排空、handles 閉、mutex 釋放。證據位於本 task `qa034_daily_missing`、`qa035_revenue_route_and_compare`、`qa036_registry_comparison`，R17 各輪結果另名保存。

QA021–025 的範圍、原失敗和修正後輸出分開記錄；後續 PASS 不抹去舊 receipt。QA025 的文件檢查失敗是既有 junction 連結越界，不能外推成產品 backend 結果。QA024 closure 的受控程序自然排空，但不代表整體 V2 gate 接受。

## 五條旅程與金融界線

QA037 固定建置日期參數的編譯、74 項來源／資源／身分測試、單檔 mypy 與 scoped 文件檢查全部通過；closure `049af0e847a6bd5872c480e4462e5936a8a173ab5784d481798b42d60c10a8e1`，自然閉鎖。此證據尚未包含 EXE 建置或同版驗證。

QA038 從固定 `730613e121b3fb5ca349440bf9973acc6a727842` 建立首個隔離 EXE，僅為 built_not_validated。QA039 在固定 archive 的 Python model probe 遇到舊 `workspace_widgets == 9` 假設而失敗，尚未進 EXE 比較，不是同版 PASS。更新驗證工具後，QA040 來源版 model/spawn/fresh/Main 正式 17 路由及全部既有後端入口通過，無 modal、正常關閉；編譯及 scoped 文件檢查亦通過。首包及原失敗保留，需固定新 commit 重新建置後驗證。

狀態只描述目前有界工程證據，產品 Gate 仍未整體接受。`PARTIAL` 不等於完整旅程通過；真人接受另列 `MANUAL_ACCEPTANCE_PENDING`。

| 五條研究旅程 | 狀態 | 已有證據與未覆蓋出口 |
|---|---|---|
| 總覽→線索→個股→保存→返回 | PARTIAL | QA017 覆蓋一般查股、保存、fresh 回訪及返回；沒有覆蓋由總覽線索進入的完整旅程，offscreen 不是原生 GUI。 |
| 市場／題材→成分→個股→返回 | PARTIAL | QA024 固定 10/16 受限快照之正常 Main first/fresh 證明 25 鏈／90 題材、CoWoS 21/21 有價量觀測的明選成分進 2330、保存題材 note revision 並 fresh 回讀原 manifest identity；這是固定題材來源的腳本旅程 PASS。一般個股行情在隔離根仍缺件，完整來源資格、原生 GUI 與真人接受待驗，不能把題材價量當作個股行情。QA013／QA017 另提供路由／布局證據。 |
| 綜合選股→條件→2–5股比較→個股 | PARTIAL | QA056 正常 Main／新程序已完成價格母體兩股條件、比較、個股與原頁返回，屬 scoped PASS；QA033 原月營收 view 的分頁、比較、收藏及精確重開另有局部證據。月營收完整 Main 綁定、EXE 此旅程與 Native／真人仍待。 |
| 個股→人工確認→Paper→Forward→覆盤 | PARTIAL（安全出口） | QA033 正常 Main 缺合法 mark/cash/snapshot 時拒絕建帳，manual/Paper 分開、無 NAV/ledger 寫入；手動研究日記經 UI 保存並 fresh 精確回讀。完整建帳及自然 Forward 成熟未驗。 |
| 策略→回測→保存→比較→返回 | PASS（受限腳本） | QA033 正常 Main 以 2330 真實受限 120 點樣本執行兩策略、保存 Registry 並 fresh 精確讀回；QA035/036 另以同策略原輸入新增合法 run、fresh 比較 120 共同日期/240列權益，原件保持。異指紋與搬移路徑拒錯另有原證據。非績效資格、Native 或真人接受。 |

QA013、QA017 與 QA020 的 scoped 結果均不能升格為 V2 Product Acceptance PASS。真人接受仍為 `MANUAL_ACCEPTANCE_PENDING`。

PIT、全市場資料覆蓋、法人金額／單位、Forward 自然成熟、ML OOS／Promotion 與真 Paper 完整帳本仍依各自原資格。UI 通過不授金融資格；不補零、不造 NAV、不合併手動／Paper，不觸正式交易、排程或正式資料寫入。

## 資源與交付界線

QA041 從固定 `e36919493b70a6be99df43b8e6d420b6d6b6c418` 建置修正候選，版本 `2026.10.21+e36919493b70`。QA042 Python／EXE 同版隔離 fixture 通過，包含固定來源／依賴／資源身份、直接 Qt 入口、保存旅程、模型／spawn／fresh 與 H20 呈現；不代表真實市場或真人接受。QA043 的 CMD 行尾及 QA044 的 PowerShell runtime 模組相容失敗保留；標準 CRLF、固定 Windows 內建 PowerShell 與其模組路徑後，QA045 整包通過：啟動器 prepare/check、錯 SHA 拒絕、原樣本不變，以及真正 frozen Main 17 路由、1280×760／1440×900／1920×1080、DPR 1.5。Main／coordinator／新 origin 均由 `PyiFrozenLoader` 從 `_MEIPASS` 載入，無 modal／錯誤，TaskWorker／thread pool 為零。以上是 offscreen，沒有恢復原生輸入。

本機候選位於 `dist/candidate_e36919493b70_a1df3b90/baldr`，使用同資料夾 `Launch-Baldr.cmd`；指南與 `DELIVERY_RECEIPT.json` 列原樣本、獨立 state、流程限制和原始收據。EXE SHA `1834e107cbe6e93a0f5e684dadba003e6809662f12ceb05cdd5838273b4b6f1f`。QA042 closure `abf2513883a466b21dcf7a97d68be18022dbcf07a7c6db3bdf814ae9c0a45cd3`；QA045 closure `be4531d9421e230d4871b5d5263015604efb7145ef9a95d9f1bc22f508bafe15`，自然排空、handles 關閉、mutex 釋放。原生操作仍受使用者先前 Escape 停止指示，已另請確認是否恢復；無回覆不視為同意。

QA047 補齊 Blueprint §11A 的 **1500×900、DPR 1.5**，沿用同一 e369 EXE 與隔離 state，沒有重建。真正 frozen Main 的 17 路由通過；首頁與選股頁截圖實際為 2250×1350 像素，root 已檢視，無意外 modal／錯誤，TaskWorker／thread pool 為零。啟動器正反 SHA 檢查及包內／state 四個樣本 SHA 保持。原始收據在本 task 的 `qa047_1500_probe/receipt.json` 與 `qa047_1500_probe/r27_exe_main_smoke/result.json`；closure `ee26d03ce16d9bd9843153d950068acd2ca125738a40507dfd30cc9b49507e45` 自然排空、handles 關閉、mutex 釋放。這補足指定尺寸的 offscreen 證據，不改變五條完整旅程的 PARTIAL 或原生／真人待驗狀態。

交付回退只切換啟動對象：先正常關閉此候選，保留完整目錄及獨立 state，再從研究13原入口 `output/trial/Baldr-Theme-Research-13/Launch-Baldr.cmd` 啟動。不要把候選 state 匯入、合併或複製進研究13／正式／私人根；本步驟沒有資料還原、遷移或清理。兩份新 EXE（730 首包與 e369 修正版）及原失敗證據均保留，資源現況依既有 task `RESOURCE_LEDGER.md`，任務 Credits 為 `USAGE_UNOBSERVABLE`。

QA049–055 原失敗均保留。QA052 的舊143來源因保存的 C 槽 output 別名已成 junction 而被 source-clock canonical 檢查拒絕；現有封存恢復工具保留 clock，不能解除這個具名限制。QA054 改用固定 QA233a 真行情副本，經正常 Main 四個 Qt 非原生確認與正式 producer 建立明示兩股母體（2317／2330、資料日 2026-09-23、台北16:00截止），分母／處理各2、缺件0；完成條件、比較及個股開啟後，驗證腳本錯把隱藏個股頁要求清空而逾時，整輪仍是 FAIL，沒有改產品返回邏輯。

QA056 以全新 Main 程序與 CASE，透過正式 `ApplicationSettings` 明選剛產製的保存來源，通過兩股查詢、價格下限1、比較、個股及返回；query／page／row identity 全部保持。原 QA233a／本 CASE 價庫 SHA 與來源 plan／三份 receipt SHA 保持，availability 仍 unknown、歷史 PIT 仍 false。`r44_qa056/journey_receipt.json` 為原始證據，closure `36a15b1a8b374bf1b2b7907742c591d995fa819f93a05ef9b44bd0884ed45782` 自然排空、handles 關閉、mutex 釋放，worker／thread pool 為零。本切片不是月營收綁定、全市場、EXE 此旅程或 Native／真人接受。候選另附已由正式 loader 接受的兩股母體 JSON 範例及 README 步驟，只有研究範圍參數，沒有手寫金融列、clock 或接受紀錄。

本任務新 EXE 建置共 2 份，首包保留但未通過同版；本機修正候選約 976 MB，未替換研究13、`dist/baldr` 或 active delivery。已有包、正式資料、模型及私人資產未刪除。平台可觀測帳戶共用額度與餘額，無精確任務計費歸屬，額外 Credits 實耗為 UNKNOWN；不聲稱能對平台帳單強制數字硬停。

本文件僅記本輪實際範圍，V2 產品驗收尚未完成。

# Baldr UI／UX 原始碼實作收尾（2026-10-23）

本頁記錄 `baldr-opus-ux-implementation` 從排程觸發、M88 初次收尾至 M97 後繼切片的**原始碼工程交接**。基線提交為 `97305c6a500798bcda27eee6a5fe9a07ef15b15f`。具名逐項裁決、原始失敗、測試收據與截圖保留在本機 `output/tasks/baldr-opus-ux-implementation/` 的 `IMPLEMENTATION_MATRIX.md`、`SOL_REVIEW.md`、`QA_RESULTS.md` 與 `NEXT_ACTIONS.md`；`output/` 依 Git 排除規則不進版控。本頁提供可隨原始碼提交查閱的範圍與證據索引，不取代各原件。

## 審查來源與工程處置

依使用者交接，Opus 起始 UI／UX 審查，因用量達限由 Antigravity 接手完成 `output/tasks/baldr-ux-visualization-audit/` 六份報告及視覺設計成果。獨立原件可核的是[先前 Opus 審查](OPUS_BALDR_UI_UX_REVIEW_20261022.md)及 Antigravity 任務 owner；交接經過來自使用者說明，沒有另份交接收據。Sol 核對報告的實際產出、穩定性、程式與畫面依據，並與[先前修正 QA](BALDR_OPUS_UX_REMEDIATION_QA_20261022.md)去重。六份續作報告是 Opus→Antigravity 審查鏈的候選建議，不冒稱完全由 Opus 寫完，也不直接當工程指令。

Sol 依現行 UI、Application DTO、來源及金融契約重排 P0–P3。已完成的方向色與圖卡不重做；來源或資料時鐘不足的圖不創造新數值。M73 保留決策品質股票／最低分數控制的作用範圍裁決；M75 保留逐公司有向供應鏈關係與跨期強弱的來源、日期和用途契約前置。這些未實作提案不能由已完成的靜態分類探索或合成比較升格。

## 從開工到此提交

| 階段 | 已實作或核對的主要結果 | 實作界線 |
|---|---|---|
| M1–M24 | 市場廣度缺值／真零、警示及日期白話；台股方向色；個股首屏及持倉速覽；題材等面積格、原九指標卡與成交額面積圖；Portfolio、Paper、推薦、回測與 Runtime 的首屏／空態／明細分層。 | 原數值、來源身份、明細與導航保留；不補造資料。 |
| M25–M45 | 兩份明選題材版本的 Application 原值 DTO 與 Qt 並列；分類成員探索及原表下鑽；Paper／Evidence／Runtime 狀態；大盤歷史圖、期間切換及載入／錯誤清舊。 | 題材分類不代表公司間供應關係；雙版本原值不代表合格跨期報酬或歷史 PIT。 |
| M46–M66 | Advice `bp` 與 TWD 成本分別標示；回測缺月與不適用值；題材大表、批次回測缺值／真零、保存結果及持倉籌碼監控；決策品質與 Evidence 首屏範圍。 | 既有績效公式、來源資格與私人帳不變。 |
| M67–M88 | 真 ProcessPool 合成指標回傳；個股漲跌與來源日期；決策品質日期／類型／Portfolio ID 精確篩選及標籤；首頁市場比例、大盤單位與背景檢測；最佳化指標可用性；Evidence 與 Legacy 歷史游標分頁、狀態／圖表來源清舊與刷新身份。M86 使覆盤六卡在寬頁單列，1280×760 首屏可見三列表格。 | 已簽績效契約的真零、不可用與舊未驗證結果分開；Legacy 與版本化 Registry 身份及資格不混用。 |

以上 M 編號包含實作、唯讀裁決與 QA 專項，**不代表 88 個獨立功能**。Sol 審查 Luna 切片並退回版面或語義問題後才接受；共同檔案由單一 writer 持有，所有 Python／Qt 驗證由 root 在受控 Windows Job 序列執行。

## 驗證範圍與最後證據

- M88 最終聚焦 **14 passed**；正常 Main 在 1280×760／真 Windows DPI96 以 211 筆隔離合成 SQLite 驗較舊圖表 run 刷新暫留、後續載入不重複，資料庫 SHA 不變。收據：`output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_4d338270e4dc47deae4374ba106fea2d/receipt.json`、`.../single_owned_qa_9963e078b52e45e180fcb677dd822e38/receipt.json`。
- M87 使用隔離 CSV 驗 A 完整、B 缺交易、C 缺曲線及交易的來源切換。最終可讀文字替代顯示 A `100／105／110`、B `200／210／205`，且 B 不殘留 A 原值；WebEngine canvas 線條未由該次截圖確認。收據：`.../single_owned_qa_d678598d81c04a31a8c62910ff25b245/receipt.json`。
- M86 聚焦 **43 passed**；正常 Main 1280×760 的覆盤歷史第 1／2 頁均可見三列，原限制提示、來源路徑與選列詳情仍可達。收據：`.../single_owned_qa_bd132e0263a04d92b9ebfc39174f4e3c/receipt.json`、`.../single_owned_qa_aacc73453e7c44a6b0a5046f665ae0b8/receipt.json`。
- M88 後共同門檻：受改 Python 編譯通過、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,143** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。收據：`.../single_owned_qa_860bdeb3071d49f89c7c957a4c55df19/receipt.json`。文件及 task 結構檢查另見 `.../single_owned_qa_6d30a91e46a9437e89f39127e5c9a9bb/receipt.json`，當時 `check_task` 無錯、`git diff --check` 為 0。

文件的完整連結檢查仍有既存 `output/` junction 連結問題；上述 `check_task` 零錯指任務結構檢查，**不代表全文件連結檢查零錯**。

較早切片的聚焦測試、真 reader／合成來源正常 Main、100%／125%／150% 隔離視窗、原件 SHA 及 before／after PNG 按各 M 列於本機 `QA_RESULTS.md`，**不能將不同輪次的測試數相加作唯一案例總數**。本輪未使用或改寫正式資料、私人 Portfolio、broker order、正式策略績效公式或來源／PIT 資格；未重建固定 EXE，也未推送、合併或部署。

## 交接與未完成 Gate

此提交封存**源碼及合成／隔離 QA 的工程階段**。正式市場／Evidence／Portfolio／Legacy 來源、自然排程、Owner UAT、真 OS 125%／150% DPI 全路徑、Light（如正式支援）、固定新版 EXE 與完整產品 Gate 均須各自驗收；1280×760／DPI96 的正常 Main 證據不能代替這些 Gate。長表大資料量與其他 Evidence 子頁可讀性仍按 `NEXT_ACTIONS.md` 續辦。下一階段若使用正式來源，先取得明確核准的安全唯讀副本與用途契約，不直接讀寫私人正式資料。

## 後續 M89–M90（同日原始碼與畫面證據）

M89 由 Luna 修改 `ui_qt/views/industry_theme_map_view.py` 和對應測試，Sol 審查接受。題材漲跌格及成交金額面積格遇跨鏈同名題材時，顯示最短可辨識鏈名前綴；未重名者維持原標籤。合成雙鏈的同名格保留各自漲跌、成交額、提示和無障礙名稱，點擊仍精確進入原鏈／題材成員；沒有更動 DTO、排序、金融計算或來源資格。根節點在受控 Windows Job 驗證：題材聚焦 **47 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,143** 檔 clean，編譯通過。收據為 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_6300fb6eb4564885bdbca19786e61132/receipt.json`。原生合成題材頁在真 Windows DPI144（150%）的 1280×760 和 900×760 邏輯視窗驗標籤容納與點擊身份，四張截圖及結果位於 `output/tasks/baldr-opus-ux-implementation/root/native_m89_evidence/run_fd02ca2fd6504bfcaf78ccb8de08446f/`，Job 收據為 `.../single_owned_qa_b804e2854859401e8d6430b9f95f6c09/receipt.json`。

M90 是 QA 專項，未修改產品程式。前一輪 M87 的早期截圖未證明 WebEngine canvas 線條可見；本輪用隔離合成 SQLite／CSV 的 A `100／105／110`、B `200／210／205`，等待頁面完成與兩次繪製幀，在正常 Main 1280×760、真 Windows DPI144（150%）截取 canvas 與整窗。A／B 分別有 **4,538／4,761** 個權益線色像素，canvas SHA 不同，切換後整窗顯 B run 身份與可見線條；來源 SHA 前後一致。結果與四張 PNG 位於 `output/tasks/baldr-opus-ux-implementation/root/native_m90_evidence/run_59cc07a00cd842ea94d0b26a1921ca63/`，通過收據為 `.../single_owned_qa_5d5c822f746749f5846d7c0acf778846/receipt.json`。首次 QA harness 因錯把桌面 DPI 固定假設為 96 而失敗，收據 `.../single_owned_qa_c92bbc3edea142438d5f96f8bd71281d/receipt.json`；修正為記錄實際 DPI 後重跑通過，這次失敗不能解讀為產品畫圖缺陷。

上述證據限合成來源、權益曲線及真 OS 150% 的兩個視窗寬度；其他圖種、GPU 路徑、其他 DPI、正式資料、固定 EXE、Owner UAT 與完整產品 Gate 仍待各自驗收。M 編號仍包含實作與 QA 專項，不能作功能數相加。

## 後續 M91–M93（題材查找與圖表刻度）

M91 由 Luna 在題材頁加名稱片段搜尋，只查已載入快照的原題材目錄；跨鏈同名結果分列，明選並按定位才套用原鏈／題材篩選。Sol 審查時修正合成 fixture 多一筆及 PySide6 `QComboBox` 將 tuple 轉成 list 的實際返回型別，保留首兩輪失敗收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_dd7d280cb95b45689e35ccae23616293/receipt.json`、`.../single_owned_qa_82d65c7965104de7b50824426dddf367/receipt.json`。修後題材聚焦 **49 passed**（`.../single_owned_qa_ba1cc99b6648482aba14511093492692/receipt.json`）；合成 90 題材原生 View 在真 Windows DPI144（150%）的 900×760／1280×760 驗搜尋前、同名結果、精確定位及無匹配清舊，來源快照指紋不變。收據 `.../single_owned_qa_213c5ba58a504a20b2991668789e6524/receipt.json`，截圖與結果 `output/tasks/baldr-opus-ux-implementation/root/native_m91_evidence/run_5ef7f056500c44f3bd56c8c25e6344aa/`。

M92 是 QA 專項，未改產品程式。正常 Main 1280×760／真 Windows DPI144，以隔離合成 Legacy A/B 原檔等候各 WebEngine 頁載入並取 canvas：A 回撤、交易報酬、持有天數三圖皆有相應線／柱色；切 B 後回撤圖仍有 B 線，兩張缺交易圖隱藏、無 A 舊色像素且各有缺件文字；SQLite／CSV SHA 不變。收據 `.../single_owned_qa_ebcde30cda5243d39a0377c3d61edd13/receipt.json`，前版截圖與結果 `output/tasks/baldr-opus-ux-implementation/root/native_m92_evidence/run_49a02f69e2f74ee39a8d6d9ad865fc4c/`。Sol 目視 A 回撤圖發現 Y 軸小幅值全被格式化為 `0`／`-0`，進入 M93。

M93 由 Luna 僅改 Fast chart canvas 的 Y 軸顯示：回撤圖依刻度間距保留小數、附 `%` 並正規化顯示精度內的負零；原曲線 payload、圖形範圍、金融計算及權益圖整數刻度路徑不變。Sol 在同一隔離 A/B 正常 Main 重跑，目視 A 真零回撤的刻度從重複 `0`／`-0` 改為 `0.02%／0.01%／0.00%／-0.01%／-0.02%`，B 非零回撤的刻度也可區分，另三圖仍可見／缺件清舊；收據 `.../single_owned_qa_b6d3667e3e9c40beb7169c165097177b/receipt.json`，後版截圖與結果 `output/tasks/baldr-opus-ux-implementation/root/native_m92_evidence/run_9771ebe1acfd4c9e9a0a073b0a75f234/`。Sol 最後補搜尋舊身份失效時清結果與可見提示後，重跑 M91–M93 受改 Python 編譯、聚焦 **71 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,143** source files clean；受控 Job 無殘留或強制清理，最終收據 `.../single_owned_qa_6f1583c8cd9b4e1995906db4c17d6190/receipt.json`。

這些證據仍限合成題材／Legacy 原檔、真 OS 150% 的已測畫面；正式資料、其他 DPI／GPU、固定 EXE、Owner UAT 與完整產品 Gate 未接受。M91–M93 皆未改 DTO、正式回測公式、PIT 或來源資格。

## M94 工作台首屏已知警示文案

Luna `/root/next_theme_slice` 唯讀盤點找到既有合成 DTO 的持倉警示在首頁仍顯整句英文；另一 Luna 盤點 Portfolio／Watchlist 的預設純自選、空態及來源分區，未找到可安全認定的新缺陷，因此沒有為湊切片改動分類。Luna 對 `ui_qt/views/workbench_view.py` 與 `tests/test_ui_qt_workbench_view.py` 實作已知持倉英文文案的呈現層映射。Sol 目視首版原生圖後，連同同一首屏的已知候選句「需人工判讀；未產生買賣建議」一起修正，並調整轉譯順序：候選原句在通用 token 翻譯前保留，首頁顯繁中，tooltip 與 Action／Review 原表格仍可追原文；未知文案原樣。原 DTO、狀態分類、數值、來源身份、導航與金融資格不變。

受控測試最終 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_9f54db344abe4714a56b647ffec1d86b/receipt.json`：受改 Python 編譯、Workbench View 聚焦 **42 passed**、共用 Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,143** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。候選句初加時因原通用 `recommendation` 替換先產生半中半英，聚焦失敗收據 `.../single_owned_qa_96e3a3ae689248e9b9279d3c0c98e788/receipt.json` 與 `.../single_owned_qa_72eb67606a6140f08b4f9c672de685af/receipt.json` 保留；修轉譯順序後重跑通過。真 Windows DPI144（150%）的原生 1280×760 合成 Workbench 畫面，在 `.../native_m94_evidence/run_8bbb3bf19954475d9a590eb9b710d108/` 有已知與未知警示的 PNG／JSON；Job 收據 `.../single_owned_qa_b928055d812540e786c1ffd911c81239/receipt.json`。較早僅持倉句的合成畫面 `.../native_m94_evidence/run_3f0c4f1b476c49408981bff423df17fe/` 可作候選句前版對照。

此收尾限已知句、合成 DTO、單一真 OS DPI 與現行原始碼；未宣稱全部自由文字已翻譯，也未核正式市場／私人 Portfolio、固定新版 EXE、Owner UAT、其他 DPI 或完整產品 Gate。M73 決策品質控制範圍及 M75 題材多期／有向關係仍須原產品與來源契約。

## M95 已保存 Stress 歷史選列卡

Luna `/root/m95_research_audit` 唯讀去重後指出 Portfolio「情境壓力」保存歷史只有九欄寬表，同筆基準／壓力後／變動需跨欄比對；Market／Stock 的另一 Luna 未找到具來源資格的新圖表缺口。Sol 接受原 `PortfolioStressHistoryRecord` 已有三個 `Decimal` TWD 原值、狀態、日期與覆蓋數，限定為單筆選列卡，不推跌幅、損失機率或跨 run 排名。Luna 僅改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`：Stress 區分「目前情境／已保存歷史」子頁，使歷史卡和原表不再受即時持倉長表擠壓；選列卡顯同筆原值，`None` 顯未提供、真零保留，原表與 hash 保留，換列／刷新／空態／讀取失敗清舊。Sol 修合成 ready fixture 的覆蓋語義、將冗長 record ID 留提示，並拒絕舊模型選列重填卡。只改呈現與選列，原 Stress 公式、DTO、保存／唯讀服務、來源與私人帳均未改。

最終受控編譯、Portfolio View 與 Stress 歷史聚焦 **76 passed**、共用 Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,143** source files clean；Job 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_e6363036bd904aa1a2f2866da71daedb/receipt.json` 無殘留或強制清理。正常 Main 1280×760／真 Windows DPI144（150%）的隔離合成 ready 與 partial 兩態、選列與原表可見性已目視；最終收據 `.../single_owned_qa_47af6f166fa24d649b832b2b920362b1/receipt.json`，PNG／JSON 在 `.../native_m95_evidence/run_701f1338298d4785889d6ffd742b3623/`。原生 harness 前兩輪在 Qt 版面穩定前嘗試捲動，卡片可見高度斷言失敗，原收據 `.../single_owned_qa_a164bc8ef342425d909ed2220881fb9f/receipt.json`、`.../single_owned_qa_08b4c9468cd34299bf7b446d593ee4e6/receipt.json` 與第三輪 `.../single_owned_qa_6dc13bae57464354b12bdfaed9a28cd7/receipt.json` 保留；等待版面完成再捲動後通過，不據此宣稱產品曾把卡片隱藏。

題材關聯圖另經 Luna 唯讀盤點：同一 snapshot mapping 足以描述題材／股票的**靜態共用成員**，單題材成員及鏈目錄已由 M29–M30 等實作，重畫全圖會重複；若續做，限「目前明選題材的跨題材共用成員鄰域」，需要新投影 DTO、範圍上限、版本身份與來源標示，且不可稱供應鏈、有向因果或歷史 PIT。M95 沒有實作這張圖。正式／私人來源、其他 DPI、固定新版 EXE、Owner UAT 與完整產品 Gate 仍各待驗；合成 Stress 卡不提升任何金融資格。

## M96 同版題材共用成員鄰域

M95 後的唯讀盤點確認，既有 M29–M30 僅呈現單一題材的分類成員，已載 snapshot 仍可回答「目前題材與哪些其他題材共用同一檔股票」。Luna 做分類資料唯讀審查，並由兩個獨立 writer 修改 `app_module/theme_overlap_presentation.py`、`tests/test_theme_overlap_presentation.py` 與 `ui_qt/views/industry_theme_map_view.py`、`tests/test_ui_qt_industry_theme_map_view.py`；Sol 核來源與 UI 邊界，退回只有文字比值的初版，要求真正的水平重疊條及兩側原分類依據。DTO 限同 manifest、`current_research`、報表與映射交集、同版日期及有效 SHA；拒絕重複分類列。UI 最多八張卡，揭露總鄰居與省略數，點擊沿原鏈／題材身份定位，換題／換版／清除／錯誤清舊；沒有改行情、報酬、PIT、正式來源或私人帳。

首輪受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_8fb9d8273377408a8bdc8b683862cd76/receipt.json` 發現 PySide6 將按鈕 tuple 屬性取回為 list，造成導航被守衛拒絕；mypy 另抓到兩個 DTO 迴圈同名變數型別衝突。Sol 修正後目視正常 Main，發現點卡後落在過低的筆記區，故使新入口回到新題材摘要，並修正合成鄰居的成員覆蓋分母。最終受控 `.../single_owned_qa_e301b2bd3f824c45a5583a7043fd6cb4/receipt.json`：受改 Python 編譯、題材 DTO／View／原分類聚焦 **47 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。真 Windows DPI144（150%）的隔離合成 View 在 1280×760／900×760 驗八張卡、2／2 與 1／2 水平條、長文捲動及省略數；最終收據 `.../single_owned_qa_9d285ce660704930864437d72beb2c20/receipt.json`，PNG／JSON 在 `.../native_m96_evidence/run_a8cfd732cd3d47308feb42f5b46ba699/`。正常 Main 1280×760 另驗市場探索導航、卡片點擊精確進入鄰居題材且新摘要與成員表可見，來源 fixture SHA 不變；最終收據 `.../single_owned_qa_ab291c1225d34b5b936985e4a0dcf7f4/receipt.json`，PNG／JSON 在 `.../native_m96_evidence/main_36e9c5e27a5743c2977ee5adab272269/`。這是合成來源與單一 OS DPI 證據，尚未核正式題材版本、其他 DPI、固定 EXE、Owner UAT 或完整產品 Gate。
## M97 Runtime 階段耗時圖與工程收尾

Luna 唯讀盤點 Recommendation／Research Lab／Backtest 已有的視覺化與資格界線，未找到值得重做的新圖；另一 Luna 指出 Runtime 決策擷取終態的階段耗時僅以長文字呈現，而既有 typed DTO 已提供原順序、狀態、整數毫秒及安全例外類型。Sol 限定只改 `ui_qt/views/runtime_view.py` 與 `tests/test_ui_qt_runtime_view.py`：在既有收合明細內附橫條，最多顯示前 32 個原事件，保留原文字、同名事件各列、零值、截限、無效值及省略數；條長只相對於本次顯示最長階段，不解讀為總耗時、成功率或金融資格。選列、篩選、被動刷新、空結果與缺型別終態清舊。沒有改 reader、排程、資料寫入或金融計算。

Sol 目視首輪真 Windows 圖後發現同名 `failed`／`started` 事件均被原 `unfinished_stages` 名稱標成「未完成」，故移除逐列推定，整體未完成階段仍在原終態文字核對。修後受控 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_6158fd336d2c4483836be6e601fccbc2/receipt.json`：受改 Python 編譯、Runtime 聚焦 **19 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留或強制清理。修前通過但語義被退回的原 QA 收據 `.../single_owned_qa_95a6a432a3e7484fb6432916344659d4/receipt.json` 與原生圖 `.../native_m97_evidence/run_bb0ea4d3ff6a48b1adbd2438fec95c50/` 均保留，不當最終接受。最終原生收據 `.../single_owned_qa_e752b43112444d599780ac9186980ecc/receipt.json`；真 OS DPI144（150%）隔離合成 View 的基線文字／修後橫條、完整正常 Main 1280×760、局部圖與原始碼 SHA 位於 `.../native_m97_evidence/run_7a38356a3d8c421ab0ef265b20d04059/`。Sol 目視確認同名 failed 不再帶錯誤的未完成標記，原清單仍可見。

### 全任務盤點與保留界線

M1–M97 是工程切片序號，包含唯讀裁決與 QA 專項，**不是 97 個獨立功能**。P0 已改善台股方向色、數值單位、日期、未知／真零、關鍵摘要及互動回饋；P1 已交付題材格、成交額圖、同版分類成員與鄰域、搜尋及精確下鑽；P2 已整理市場／個股／推薦／Portfolio／Backtest／Evidence／Runtime 的首屏、原值圖卡、歷史與狀態清舊。各處保留原明細、來源身份與金融限制。P3 的有向供應鏈及跨期強弱仍需要逐邊來源／時鐘與用途契約；既有靜態重疊不得升格。審查來源是 Opus 起始、Antigravity 續作完成六份主要報告，Sol 逐項去重與核現行程式，Luna 分切片、root 複核及執行受控 QA；具名身份以本頁「審查來源與工程處置」為準。

本次收尾是**後繼原始碼與隔離 QA 的工程階段完成**。正式市場／Evidence／Portfolio 資料、自然排程、私人帳、完整 100%／125%／150% DPI／Light（若支援）、固定新版 EXE、Owner UAT 與完整產品 Gate 沒有因此通過；M73 決策品質控制作用範圍與 M75 來源／用途契約仍待產品裁決。下一步只依具名來源與授權取得安全唯讀副本後補正式接受，不以合成 PASS、圖卡外觀或單一截圖取代。

# Baldr UI／UX 原始碼實作收尾（2026-10-23）

本頁後續已更新至 M154；下方早期階段敘述依當時範圍保留，最新切片與收據見文末。

本頁記錄 `baldr-opus-ux-implementation` 從排程觸發、M88 初次收尾至 M154 後繼切片的**原始碼工程交接**。基線提交為 `97305c6a500798bcda27eee6a5fe9a07ef15b15f`。具名逐項裁決、原始失敗、測試收據與截圖保留在本機 `output/tasks/baldr-opus-ux-implementation/` 的 `IMPLEMENTATION_MATRIX.md`、`SOL_REVIEW.md`、`QA_RESULTS.md` 與 `NEXT_ACTIONS.md`；`output/` 依 Git 排除規則不進版控。本頁提供可隨原始碼提交查閱的範圍與證據索引，不取代各原件。

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

M1–M98 是工程切片序號，包含唯讀裁決與 QA 專項，**不是 98 個獨立功能**。P0 已改善台股方向色、數值單位、日期、未知／真零、關鍵摘要及互動回饋；P1 已交付題材格、成交額圖、同版分類成員與鄰域、搜尋及精確下鑽；P2 已整理市場／個股／推薦／Portfolio／Backtest／Evidence／Runtime 的首屏、原值圖卡、歷史與狀態清舊。各處保留原明細、來源身份與金融限制。P3 的有向供應鏈及跨期強弱仍需要逐邊來源／時鐘與用途契約；既有靜態重疊不得升格。審查來源是 Opus 起始、Antigravity 續作完成六份主要報告，Sol 逐項去重與核現行程式，Luna 分切片、root 複核及執行受控 QA；具名身份以本頁「審查來源與工程處置」為準。

本次收尾是**後繼原始碼與隔離 QA 的工程階段完成**。正式市場／Evidence／Portfolio 資料、自然排程、私人帳、完整 100%／125%／150% DPI／Light（若支援）、固定新版 EXE、Owner UAT 與完整產品 Gate 沒有因此通過；M73 決策品質控制作用範圍與 M75 來源／用途契約仍待產品裁決。下一步只依具名來源與授權取得安全唯讀副本後補正式接受，不以合成 PASS、圖卡外觀或單一截圖取代。

## M98 市況廣度比例條與 Stress 長表補驗

Luna 唯讀去重後指出市場總覽的市況廣度已有原家數與來源比率文字，但「完整市場資料」內尚無家數分布的直觀比例；另一路 Luna 建議補 M95 Stress 歷史長表的合成操作證據。`/root/m98_breadth_bar` 單一 writer 修改 `ui_qt/views/decision_desk_view.py` 與其測試；Sol 審查接受以原 `MarketBreadthSummary` 的三個非負整數家數作紅漲／綠跌／平盤中性比例條，只在正總數、可辨識品質及來源日不晚於判斷日時顯示。原家數、來源 `breadth_ratio_bp`、來源日與品質並列；零段為零寬、缺值不補零、刷新／載入／錯誤清舊。條長不解讀為指數報酬或交易訊號，未改 DTO、金融公式、來源資格或私人資料。Sol 補清除舊 Qt 子元件與重繪測試後接受限定呈現層。

最終受控收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_926a209971c24b1ab1fbb33b2861c022/receipt.json`：受改 Python 編譯、決策工作台聚焦 **35 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，Job 無殘留 PID 或強制清理。前兩輪測試用 `isVisible` 判斷未顯示的 parent View，斷言失敗；改驗元件自己的 hidden 狀態後通過，原失敗收據 `.../single_owned_qa_be3bae14387b44e3a19aef421321d59d/receipt.json`、`.../single_owned_qa_81630514e4944475afd97447ae39f308/receipt.json` 保留。真 Windows DPI144（150%）的原 View HEAD 基線、修後局部與整窗、正常 Main 1280×760 隔離合成截圖及 JSON 在 `.../native_m98_breadth_evidence/run_0ea20727ecf6474ba7c5b04809fcf10b/`；Job 收據 `.../single_owned_qa_a51f75e170384066a41c6e3c3545ecf1/receipt.json`。Sol 目視比例、家數、來源與品質可讀。

Stress 長表未改產品程式。隔離正常 Main 1280×760／真 DPI144 注入 40 筆合成保存紀錄，選第 1／21／40 筆時同筆 TWD 原值與 partial 缺值卡片正確，重繪成單筆後清舊；渲染 46.5 ms。證據 `.../native_m98_stress_40_evidence/run_9639ec3fc3c24d1c9d84e7624b88ed3d/`，Job 收據 `.../single_owned_qa_744be3436f6f4ab6a302ae46d1e5de63/receipt.json`。首兩輪腳本過早注入，被 Portfolio 原背景載入覆蓋；原失敗收據 `.../single_owned_qa_1a95f37156774f6985a7d1aa8ae4b866/receipt.json`、`.../single_owned_qa_1dde9569ecc74d34aabd82d775db64be/receipt.json` 保留。40 筆外層長頁選列卡與末列不一定同屏，後續需在正式授權副本和實際操作下再評估表格導覽；本次不據合成腳本稱正式性能或 Owner UAT 通過。

M1–M98 編號含唯讀審查與 QA 專項，不代表 98 個功能。原始碼工程階段已盤點；正式來源／自然排程、其他 OS DPI、Light（若正式支援）、固定新版 EXE、Owner UAT、M73／M75 契約及完整產品 Gate 保留獨立驗收。

## M99／M100 法人流向圖與 Stress 長表版面

Luna `/root/m99_research_cards_audit` 唯讀去重指出三大法人市場淨股數已有同次 typed DTO，但首頁仍為長文字。`/root/m99_institutional_flow_bars` 單一 writer 只改 Decision Desk View 與測試；Sol 複核要求舊 row widget 清除時先解除 parent，並禁止來源日晚於 decision as-of 或日期無效仍畫圖。最終在原 `MetricCard` 內以共用零軸顯外資／投信／自營商原整數股數的正負相對條，真零為中性短標記；原文字、精確股數、來源日、涵蓋檔數、品質與警示仍可核。條長只相對於同次三者最大絕對值，沒有改來源服務、DTO、金融公式、PIT、交易或資格。真 Windows DPI144（150%）的原 View HEAD 基線、後版 1280×760／900×760 與正常 Main 1280×760 已目視，局部可讀圖在 `output/tasks/baldr-opus-ux-implementation/root/native_m99_flow_evidence/run_28cdc2b4dbd84a589b4063e21ebfe50e/`；Job 收據 `.../single_owned_qa_f1b5e8d17c03477ab9976e7a0e6e0e6f/receipt.json`。

Luna `/root/m99_portfolio_longlist_audit` 判定 M98 末列不同屏的原截圖受 harness 外層捲動定位影響，不能單獨判產品 defect；但 Stress 已保存歷史的長表無高度上限，有合理的可讀性改善空間。`/root/m100_stress_history_layout` 單一 writer 只改 Portfolio View 與測試，將表格可見高度封頂約七列，保留內部垂直／水平捲動；讀取錯誤時空模型重算高度。Sol 的首次正常 Main 畫面發現封頂後多餘高度被上方卡片吃掉，導致卡片巨大，雖 Job exit0 仍未接受；原圖及收據 `.../native_m100_stress_evidence/run_35b3fac0b3dd40e6b2185ac99f4318d7/`、`.../single_owned_qa_57067afe29b84b47bf05eb8de1bb1cfc/receipt.json` 保留。Sol 修卡片內容高度與表下 stretch 後，同樣 40 筆合成紀錄的正常 Main 1280×760／真 DPI144 首、中、末選列皆精確顯同筆原 TWD 值，末筆 selected row 與卡片同屏，缺值未補零；最終原生圖／JSON `.../native_m100_stress_evidence/run_cf43287112704c40ac411c05f0e277b3/`，Job 收據 `.../single_owned_qa_dffb9f25c71a4b70816682d7620fb18e/receipt.json`。未改 Stress 公式、reader、保存、私人 Portfolio 或交易。

第一輪受控聚焦 `.../single_owned_qa_052cdb10815746b38a5646890805cda1/receipt.json` 是 **1 fail／110 pass**：測試只選內層歷史 tab，未展開 Portfolio 進階工作區；Workbench85、validator25/0/4、mypy1144、編譯均通過。修測試路徑後 111 focused 通過；Sol 視覺修卡後的最終共同收據 `.../single_owned_qa_b675e08449fa4116b84b3476bea63422/receipt.json` 為編譯、**111 focused**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無剩餘 PID 或強制清理。這些都是隔離合成與單一真 OS DPI 的原始碼證據；正式來源、其他 DPI、固定新版 EXE、Owner UAT 及完整產品 Gate 沒有因此接受。M1–M100 編號含審查與 QA 專項，不代表 100 個獨立功能。

## M101 Stress 研究窗格比例與任務收尾

Luna `/root/m101_portfolio_workspace_audit` 唯讀核 M100 正常 Main 截圖與現行 QSplitter：Stress 右側原約 40%，左側 Paper 健康狀態有實際阻擋資訊，因此應保留而讓研究表格取得較多寬度。另一研究頁盤點沒有足夠的新視覺證據，本輪不改。`/root/m101_stress_pane_focus` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`；Sol 複核只在尚未手動拖曳的寬畫面，Stress 頁籤採左／右約 30／70，其他頁籤仍約 60／40，窄畫面上下分割維持原比例。左側健康狀態、原表、同筆 TWD 卡、缺值、來源身份與既有導航均保留；沒有改 Stress 公式、DTO、reader、保存、私人帳或交易。

受控聚焦及共同 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_4305dc3e805e43909ec8963dcaf72e30/receipt.json`：編譯通過，Portfolio **73 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留 PID 或強制清理。正常 Main 1280×760、真 Windows DPI144（150%）、隔離合成 40 筆 Stress 的首／中／末選列與返回 Paper 皆通過，原生收據 `.../root/single_owned_qa_e69fc3265a4f4410a43cee138145ab5d/receipt.json`、結果及四張 PNG `.../root/native_m101_stress_evidence/run_4e0192c528ab4bbaa23494754f415d5a/`。Stress 右側實測 **69.3%**，Paper 返回後右側 **39.9%**；末筆卡與表列同屏。M100 前版圖 `.../root/native_m100_stress_evidence/run_cf43287112704c40ac411c05f0e277b3/last_partial_1280x760.png` 留作同尺寸視覺基線。這些是原始碼／合成資料／單一真 OS DPI 的有限驗證，不是正式來源、私人帳、固定 EXE 或 Owner UAT 接受。

### 從排程開工至 M101 的盤點

Opus 起始審查、Antigravity 因 Opus 用量耗盡續作六份主要報告；Sol 核對實物、程式依據、重複項與金融限制，再把可做項目切給 Luna，由 root 複核及序列執行受控 QA。上方 M1–M88 表及各後續小節是具名切片原件；補充總覽如下，**M 編號含唯讀裁決與 QA 專項，不是功能數**：

| 階段 | 累積完成的使用者可見工作或證據 |
| --- | --- |
| P0／M1–M88 | 台股紅漲綠跌、單位與日期、未知／真零、首屏摘要、載入／錯誤回饋；市場、個股、推薦、Portfolio、Backtest、Evidence、Runtime 的圖卡／明細層級與來源清舊。 |
| P1／M25–M96 | 題材等面積格、成交額圖、原九指標、同版分類成員、兩版原值並列、名稱搜尋、跨鏈同名辨識、共用成員鄰域及精確下鑽；靜態重疊不稱供應鏈。 |
| M89–M94 | 同名題材標籤、Legacy 權益／回撤／交易結果真 Windows canvas 證據與刻度修正、首頁已知警示繁中化；未知來源文字保留原文。 |
| M95–M101 | Stress 即時／已保存歷史子頁、同筆原值卡、40 筆長表內捲動與同屏、Stress 寬窗格；市場廣度紅／綠／中性比例、三大法人原股數共用零軸條、Runtime 階段耗時條。 |

全部可見改造保留原值、來源、日期與明細；比率或條長只表其明定的同次相對量，不授市場趨勢、投資績效或來源資格。正式資料與自然排程、完整 DPI／Light、固定新版 EXE、Owner UAT、完整產品 Gate，以及 M73 控制作用範圍與 M75 有向關係／跨期來源契約仍分列未驗。本輪只提交受追蹤原始碼、測試與文件；`output/` 原始收據及截圖留本機，未 push、merge 或部署。

## M102 Stress 情境切換清舊與保存身份

Luna `/root/m101_research_layout_audit` 深查後撤回市場完整警示候選：M2 的首屏摘要、預設收合、刷新清舊及 1280×760 原生圖已處理，不為進度重做。另一 Luna 盤點 Backtest／個股／推薦，現有原值圖與首屏表已覆蓋先前提案，未找到可靠的新高價值圖卡。`/root/m101_portfolio_workspace_audit` 則發現可達的 Stress 身份錯配：執行情境 A 後只改選 B，舊 A 結果仍留在摘要／表格並可保存。Sol 核現行 combo、run、save 與手冊，接受此為 P0 操作與狀態回饋缺陷。

同一 Luna 作唯一 writer，僅改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`。換情境即清舊摘要、診斷、表格及 `_stress_result`，提示重新執行，保存按鈕停用；取得新結果後才恢復。執行失敗也清舊。保存函式獨立比對結果與選項的 scenario ID，錯配時在二次確認及 repository append 前拒絕並清除。Sol 複核保留原 `partial`／`not_computable`、缺值、真零、二次確認與已保存歷史語義；Stress service、DTO、金融公式、正式資料及帳本均未改。

受控共同 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_7ffdeafa60e3468585bdf64e9a7076d1/receipt.json`：編譯、Portfolio **75 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。聚焦測試以 `tmp_path` 隔離持倉資料，驗 A→B 清舊且不建歷史、故意注入舊 DTO 仍拒保存、B 重算後保存匹配 scenario、例外清舊。正常 Main 1280×760、真 Windows DPI96（100%）的隔離空帳本三態原生圖與 JSON 在 `.../root/native_m102_scenario_evidence/run_0d795e13fcf14467939c93832a5f333f/`，最終 Job 收據 `.../root/single_owned_qa_cd62b9ab793e4110a36d10808c9b1f5b/receipt.json`；Sol 目視 A 原結果、B 待執行與 B 新結果，三張圖 SHA 不同。首次原生腳本沿用前輪 DPI144 假設而 fail，原收據 `.../root/single_owned_qa_10366b2d78d2484c9abebe85e2da1379/receipt.json`；第二輪雖 Job pass，未捲到 Stress 控制區，三圖相同，不作最終視覺證據，原收據 `.../root/single_owned_qa_15f2c21d3de24117b5dcb19e2bb98af2/receipt.json` 保留。這些是隔離空帳本與單一真 OS DPI 的原始碼證據，正式私人帳、其他 DPI、固定新版 EXE、Owner UAT 與完整產品 Gate 仍未接受。

## M103／M104 決策品質作用範圍與 Stress 來源揭露

Luna `/root/m101_research_layout_audit` 核現行 Decision Quality service：股票代碼只篩項目列，分數卡取所選覆盤範圍最新一筆；最低分數比較該最新分數，未達時清項目列，卡片仍保留原值。M73 尚未裁決正式作用範圍，因此 M103 不改 service、DTO 或分數公式。該 Luna 單一 writer 改 `ui_qt/views/decision_quality_view.py`、`tests/test_ui_qt_evidence_review_dashboards.py`、`tests/test_decision_quality_dashboard_service.py`：左側篩選可內部捲動，刷新鈕固定於左欄底部；提示現行語義，服務測試鎖定跨兩期與不同股票行為。Sol 在正常 Main 1280×760 原生圖發現初版內層捲動受外層長頁撐高，退回要求高度上限與外層長頁測試；修後依 Qt 邏輯螢幕可用高度限制。使用者須先把外層頁面捲到決策品質區，再於左欄捲到最低分數；兩層捲動已原生核對。

Luna `/root/m101_portfolio_workspace_audit` 跨查 Portfolio 呼叫與 Paper 導覽：Stress 使用 `PortfolioService.get_portfolio()` 的交易／手動持倉 DTO，Main 預設 `portfolio_id=default`；Paper 分區只決定畫面位置，不將 Paper snapshot、ledger 或 Health 當 Stress 輸入。M104 單一 writer 只改 `ui_qt/views/portfolio_view.py`、`tests/test_ui_qt_portfolio_view.py`，在目前情境與保存確認顯示來源；切換分區不清空既有 Stress 結果。Sol 核保存仍須情境身份守衛及二次確認；未改 service、DTO、公式、保存 payload、帳本或私人資料。

最終受控 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_d4b7151751334c4abd17e2e1d28e1ca4/receipt.json`：受改 Python 編譯、**125 focused passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留 PID 或強制清理。首輪聚焦 fixture 未限制離屏 Qt 虛擬螢幕高度，第二輪在外層長頁頂端要求下方控制可見，各有一個測試失敗；修 fixture 模擬受限左欄並先捲到決策品質區後通過。失敗收據 `.../root/single_owned_qa_3b29b5a2ee9e440daa394332bcdcb84a/receipt.json`、`.../root/single_owned_qa_1b662bf855b64bdcbe991bcedcc33127/receipt.json` 保留，不列最終通過。

正常 Main 1280×760、真 Windows DPI216（225%）隔離合成 SQLite 原生收據 `.../root/single_owned_qa_8785b81d1fac46cf93583a691e4202c0/receipt.json` exit0、無殘留 PID；三張不同 SHA PNG 與 `result.json` 在 `.../root/native_m103_m104_evidence/run_f60dd1c6fa334205b88e5ea7eaad25c0/`。Sol 目視決策品質左欄最低分數與刷新鈕、右側原卡／項目表，以及 Stress 在 Paper 導覽中的來源提示；來源 DB 前後 SHA 相同。原生初輪腳本固定 DPI 範圍而拒絕當前 225%，後兩輪停在 Evidence 外層頂端，均未作最終圖證；原收據 `.../root/single_owned_qa_e124918abfac42148d45acacac92b88d/receipt.json`、`.../root/single_owned_qa_8a2e066521b84069870d947a87f3917f/receipt.json`、`.../root/single_owned_qa_966d3858dd6748b18714ba4cf8d04bff/receipt.json` 保留。

### 從排程開工至 M104 的階段盤點

M1–M104 是含審查、裁決、QA 的切片序號，**不是 104 個獨立功能**。Opus 起始、Antigravity 接續的六份審查與 mockup／prototype 已定位，Sol 對照現行架構、去重、修正不適用提案。P0 完成台股紅漲綠跌、原數值單位／日期、真零／未知／錯誤、首屏摘要及狀態清舊；P1 完成題材等面積格、限定成交額圖、九指標、同版分類與鄰域、雙版本原值、搜尋及精確下鑽；P2 改善市場、個股、推薦、Portfolio、Backtest、Evidence、Runtime 的摘要／圖卡／明細、長表與研究回訪，M103／M104 補篩選與來源文字。既有圖卡及已驗路徑未為進度重做。P3 公司間有向關係與跨期強弱仍缺逐邊來源、時鐘與用途資格；M73 仍缺決策品質股票與門檻作用範圍正式裁決。

本次完成的是原始碼、隔離合成資料及單一真 OS DPI 的工程驗證。正式市場／Evidence／Portfolio 資料與自然排程、全 DPI／Light（若支援）、固定新版 EXE、Owner UAT 和完整產品 Gate 仍未接受；`output/` 收據與圖留本機，不進版控。沒有自動交易、broker order、正式資料改寫、force push、merge 或部署。

## M105 決策品質篩選欄水平溢位

Luna `/root/m105_decision_filter_layout_audit` 唯讀核 M103 正常 Main 1280×760／真 OS DPI216 原生圖：左篩選欄出現水平捲軸，Portfolio ID 與其他欄位右側被裁；這是可達 UI 缺口，不是縮圖假象。Sol 指定同一 Luna 為 `ui_qt/views/decision_quality_view.py`、`tests/test_ui_qt_evidence_review_dashboards.py` 唯一 writer，於原 `QFormLayout` 設 `WrapLongRows`，窄欄時標籤換至輸入欄上方。Root 加強測試的左界斷言。右側結果表原本的獨立水平捲動仍保留；沒有隱藏左捲軸掩蓋裁切，也沒有改查詢、service、DTO、分數、PIT 或來源資格。

受控 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_ab6c8351196b49be89960bc2304e5067/receipt.json`：受改 Python 編譯、**125 focused passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留 PID 或強制清理。正常 Main 隔離合成 SQLite 原生收據 `.../root/single_owned_qa_6e3581b85afc45219d3a281fc06260bf/receipt.json` exit0；真 OS DPI216（225%）下 1280×760 與 1500×900 的左欄水平捲動最大值皆 0、九個可互動控制左右邊界皆在視口內，最低分數、內層垂直捲動、固定刷新與右側原值仍可見。來源 DB 前後 SHA 相同。兩張 PNG 與數值 JSON 在 `.../root/native_m105_filter_evidence/run_a907ac800dbd43b9a7b0486fb05b21ac/`；M103 前圖 `.../root/native_m103_m104_evidence/run_f60dd1c6fa334205b88e5ea7eaad25c0/decision_quality_filter_bottom_1280x760.png` 保留作同尺寸 before。1920×1080 超過當前螢幕可用邏輯尺寸，腳本明記 `not_run_screen_too_small`；其他真 OS DPI、正式 Evidence DB、固定 EXE、Owner UAT 與完整 Gate 仍未驗。M73 的正式股票／門檻作用範圍仍待產品裁決，M105 只修版面。

## M106 研究落差資料品質分布

Luna `/root/m106_evidence_visual_audit` 盤點 Evidence 後提出多個候選。Sol 核 `LiveResearchGapDashboardResult` 與服務語義，拒絕把三個帶 `bp` 的研究落差欄位直接畫成共用零軸：現行 `gap_vs_benchmark_bp` 的組合與 UI「對大盤落差」標籤尚需契約釐清，不用圖形放大歧義。Watchlist 狀態分布需額外逐列來源身份及讀取契約，本輪延後。Sol 選擇服務已提供的 `quality_counts`，指定 Luna 單一 writer 僅改 `ui_qt/views/live_research_gap_view.py` 與 `tests/test_ui_qt_evidence_review_dashboards.py`。

「證據覆盤 → 資料缺口」在原表上方新增已觀測、降級、缺失、其他代碼四類 2×2 品質分布條與精確計數。僅在服務計數為非負整數且與已載入列及 `positions_seen` 一致時呈現；未知新碼保留原文，成功讀取的空集合顯真 0。診斷、缺計數、矛盾或例外顯未知，刷新先清除舊卡、表、明細與圖條，遲到結果仍按原 request ID 拒絕。條長只描述本次載入資料狀態，不代表投資績效、正式來源資格或交易訊號；服務、DTO、來源、PIT 與金融公式均未改。Sol 首次原生目視發現四行品質條擠壓 1280×760 原表，退回改為 2×2 後才接受。

最終受控 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_872b947a20534e4b9f015c1467371465/receipt.json`：受改 Python 編譯、Evidence／Decision／Portfolio 聚焦 **126 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留 PID 或強制清理。正常 Main 1280×760／1500×900、真 Windows DPI216（225%）的隔離合成 DTO 畫面及來源不可用狀態已目視；1280 首屏可見品質條與原表首列，來源診斷時卡片為「未知」、條計數為「—」，DB SHA 前後一致。原生 Job 收據 `.../root/single_owned_qa_8a7e0401c7814c0d810258f63fc07c8d/receipt.json`，JSON 與三張 PNG 位於 `.../root/native_m106_quality_evidence/run_ca7caeedc70742d48c6cf92c774ac2e4/`。首版四行基線及收據仍留 `.../root/native_m106_quality_evidence/run_5d019310c4cf4e52abf3e8f162ffb2c8/`、`.../root/single_owned_qa_1a76e67170f44046be97748a1c3bcfb4/receipt.json`；它不是最終布局。

M1–M106 是含實作、唯讀裁決與 QA 的序號，不是 106 個獨立功能。正式市場／Evidence／私人 Portfolio、自然排程、其他真 OS DPI、Light（若正式支援）、固定新版 EXE、Owner UAT、M73／M75 來源與用途契約及完整產品 Gate 仍須分別驗收；本輪 1920×1080 超出可用螢幕邏輯尺寸，明記未跑。`output/` 原始證據留本機，不進版控；沒有 push、merge 或部署。

## M107 前瞻結果逐期限成熟分布

Luna `/root/m107_evidence_audit` 唯讀盤點正常 Evidence Review「今日決策 → 排程狀態」：前瞻結果卡只列總待成熟數，各期限 ready／pending／missing 原值藏在長篇明細。Sol 查 `ScheduledEvidenceStatus.forward_health_horizons` 與 `scheduled_forward_outcome_service` producer，確認它是**本次有界選取的 cohort health 摘要**，不是全部歷史、報酬、勝率或來源資格；不將 Portfolio 四摘要卡尚未原生重現的窄窗裁切候選冒充已證實缺陷。指定 Luna 單一 writer 只改 `ui_qt/views/scheduled_evidence_status_view.py`、`tests/test_ui_qt_evidence_review_dashboards.py`，原 producer、read service、DTO、金融公式及正式來源均不改。

新圖在前瞻結果卡下逐期限顯原始 ready／pending／missing 精確筆數及同一期限內比例，數字鍵按數值升序，最多六列，其他原標籤與超出項在原明細保留。三個原欄全為非負整數才可畫條；明示 `0 / 0 / 0` 時以中性空條顯真零，缺欄、布林、負數與錯型別顯未知，不借舊 `_horizon_summary` 的缺 key 預設 0。刷新時清舊，來源未知不殘圖，最後可信內容只在醒目 STALE 標記下保留。圖例明示狀態色非績效／交易訊號，pending 是等待成熟。

Sol 首次同尺寸原生圖發現新增 chart 把原雙欄卡片擠成約 20／80，且清舊只排入 deferred delete，使來源未知截圖仍閃現前次彩條；雖該輪 Job exit0，視覺未接受，原圖與收據留 `output/tasks/baldr-opus-ux-implementation/root/native_m107_evidence/run_ff6b0a2c71024a13ae10e27ac17c5882/`、`.../root/single_owned_qa_1e0af2dab9ba47b197e9697ba2be8c16/receipt.json`。Luna 改雙欄等伸展、縮窄策略與行 widget 立即 hide／detach 後，第二輪正常 Main 的欄寬及未知清舊可見；Sol 再要求期限按數值順序，最終畫面才接受。

最終受控 QA 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_83d7efeeed0f49ddad1cd1062a1f9847/receipt.json`：受改 Python 編譯、Evidence 聚焦 **55 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。真 Windows DPI216（225%）的隔離合成正常 Main 1280×760／1500×900、stale／未知三態及同尺寸元件 before／after 已目視，來源 DB SHA 不變；最終 Job 收據 `.../root/single_owned_qa_d2efb34563264c4788327d0fc837cf7c/receipt.json`，七張 PNG 與 JSON 在 `.../root/native_m107_evidence/run_aa6157541c254375a1f258640e97b1a3/`。1920×1080 超出現有螢幕可用邏輯尺寸，其他真 OS DPI、正式排程／Evidence 來源、固定 EXE、Owner UAT、完整 Gate 未驗。

M1–M107 是含實作、審查與 QA 的序號，非 107 個獨立功能。M73 決策品質控制正式作用範圍與 M75 有向關係／跨期資料用途契約仍分列待裁；本輪未讀寫正式或私人資料，未改其他排程，也未 push、merge 或部署。

## M108 個股研究 ML 估計完整性提示與收尾

Luna `/root/m108_research_visual_audit` 唯讀核對 `StockMLSnapshotDTO.predicted_benchmark_excess_return_bp`、adapter 與個股報告 View：模型鍵未承諾為可比較期限，完整原值表在收合的「資料稽核」，但首屏一般摘要只列前三筆而不提示餘數。Sol 選定只改呈現層，拒絕用不具可比契約的模型鍵畫趨勢條。Portfolio 四卡長缺值文案另以真 Windows DPI216、隔離合成 900×760／1280×760／1500×900 探針核：900 寬文字與可見寬皆 182 logical px，完整可讀，因此未把未證實裁切改版；原探針與收據在 `output/tasks/baldr-opus-ux-implementation/root/native_m108_probe_evidence/run_2e962c7b2f2940c2998433bb3de1bc7f/`、`.../single_owned_qa_82d6d09c888649b986bfd07e9a168ba2/receipt.json`。

Luna 單一 writer 只修改 `ui_qt/views/stock_research_report_view.py` 與 `tests/test_ui_qt_stock_research_report.py`：一般摘要仍最多顯前三筆有效整數估計，多餘時明示「另有 N 項」並指向完整資料稽核；H5 註記優先時明示完整 ML 表的有效總筆數，避免將 H5 誤稱前三筆。保留原 H5／H20 分流、成本與目標定義、資格、研究限定及非機率警語；完整表、DTO、service、金融公式、來源資格及正式資料均未改。Sol 第一輪正常 Main 發現 H5 優先路徑漏提示，退回補上並新增測試；原生失敗收據 `.../single_owned_qa_464e894efc894aeda6706960d539c56a/receipt.json`，後兩次 harness 預期文字未同步新路徑，收據 `.../single_owned_qa_8a43f5e079ef4db5834ac822a926b29d/receipt.json`、`.../single_owned_qa_c7d6eba3307a42219cad12dc30727d74/receipt.json` 保留，不列產品失敗或最終接受。

最終受控 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_1a8541ea913040cd8be810bb08deffd1/receipt.json`：受改 Python 編譯、個股研究 **78 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job exit0、無殘留 PID 或強制清理。正常 Main 真 Windows DPI216（225%）的隔離合成四筆 ML／H5 前後比較，在 1280×760、1500×900 均可見總數提示及原警語；原生收據 `.../single_owned_qa_606c0c28b4554d539abd4a4d5d919d13/receipt.json`，HEAD 原函式重建的 before 與修後四張 PNG、文字及 hash 位於 `.../native_m108_research_evidence/run_6fb22fc937ee48d2bf0eb05b547e28c8/`。這些是合成 DTO 與單一真 OS DPI；1920×1080 因目前可用螢幕尺寸不足未跑，其他 DPI、正式來源、固定新版 EXE、Owner UAT、自然排程及完整產品 Gate 仍未接受。

### 從排程開工至 M108 的盤點

Opus 先做獨立唯讀 UI/UX 審查；額度耗盡後 Antigravity 接續六份主要報告、mockup 與 prototype。Sol 查原實物、程式與產品架構，逐項去重並裁決金融語義；Luna 在單一 writer 檔案邊界實作，root 複核、跑受控 QA、真 Windows 合成畫面及本機逐輪提交。**M1–M108 是含唯讀裁決、測試與實作的序號，不是 108 個獨立功能。**

| 範圍 | 累積已完成的工程工作 |
| --- | --- |
| P0 金融辨識與狀態 | 台股紅漲綠跌、單位／日期、未知與真零、首屏 KPI、載入／錯誤／來源清舊；修正 Stress 情境 A→B 的過期結果與保存身份；M108 補 ML 多筆估計完整性提示。 |
| P1 題材與產業 | 題材摘要及原九指標、限定成交額圖、等面積格、雙端比較、成員下鑽、同版分類／共用成員鄰域、名稱搜尋與跨鏈同名識別；未把靜態分類當有向供應鏈。 |
| P2 研究工作台 | 市場廣度／三法人、個股價格與研究證據、推薦／選股、持倉與 Stress、Backtest、Evidence／覆盤、Runtime 的摘要圖卡、原表及細節、長表導覽與限定前後原生驗證。 |
| P3 限定探索 | 同一版本的題材與股票分類關係可讀；公司間供應／客戶有向邊與跨期強弱仍缺來源、時鐘及用途契約，未假造完整關係圖。 |

完成的是後繼**原始碼工程切片與隔離合成 QA**，不是產品正式驗收。正式市場／Evidence／私人 Portfolio 來源與自然排程、全真 OS 100%／125%／150% DPI 路徑、Light（若正式支援）、固定新版 EXE、Owner UAT、M73 決策品質控制作用範圍、M75 有向關係／跨期用途契約及完整產品 Gate 各自保留。`output/` 原始收據與截圖留本機，不納版控；沒有自動交易、broker order、正式資料改寫、其他排程變更、push、merge 或部署。

## M109／M110 Paper Health 與候選池辨識

Luna `/root/m107_portfolio_audit` 唯讀盤點 Stress 30／70 頁左側 Paper Health 長表；Sol 先用同股不同部位、確認需求不同的三列合成資料，在正常 Main 1280×760 真 Windows DPI216（225%）重現：原表視窗約 302 邏輯像素，需水平捲動約 378 才看見第六欄「需要確認」。指定同一 Luna 單一 writer 僅修改 `ui_qt/models/workbench_table_models.py`、`tests/test_ui_qt_portfolio_view.py`，把原確認欄移到標的旁，並在代號 tooltip 列出該列原 `position_id`、snapshot ID、cohort key；缺件明示未提供。原欄內容、選列詳情、帳本及健康判定不改。修後 1280 窄表同屏可辨「需要／不需要／需要」，同股仍按原列身份選取。原生 before 收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_1f564370b8f645239510bfdcf94af92c/receipt.json`、圖片 `.../root/native_m109_health_probe_evidence/run_d5fe316aa4d94a7faffd515f2ab73f11/`；after 收據 `.../root/single_owned_qa_b303a0302c9f45e7b2f74a3bbd87b4cf/receipt.json`、圖片 `.../root/native_m109_health_after_evidence/run_8c39939b7f8a4113a68a1028b9e92ed9/`。

Luna `/root/m108_research_visual_audit` 唯讀盤點 Watchlist 多來源列後，單一 writer 僅修改 `ui_qt/views/watchlist_view.py`、`tests/test_ui_qt_watchlist_layout.py`。原 `len(stocks)` 是候選列數，不能標成股票檔數；首屏摘要及表下計數改為「N 筆候選列／M 檔不同代號」，保留同股不同來源及逐列原身份。成功空集合才顯 0／0，載入失敗為未知，清選列不把失敗轉成零。正常 Main 1280／1500、真 OS DPI216 合成兩筆 2330 加一筆 2603 目視確認 3／2 且三列可見，原生收據 `.../root/single_owned_qa_fa6a6c83be9d4bf28415da69c7cda0f9/receipt.json`、圖片 `.../root/native_m110_watchlist_evidence/run_28831576d5874620a6ee6849eb06e560/`。首次 native probe 在窗已關閉後讀 QLabel 而失敗，已修測試 harness，失敗收據 `.../root/single_owned_qa_9dce2f72f69943a49a1fdc5b5b19ab33/receipt.json` 保留；不是產品失敗。

Sol 審查兩切片原始碼、同股不同身份測試與兩組原生圖後接受限定 UI 改造。共同 8 GiB／12 程序 Job `.../root/single_owned_qa_917ff17e09fd47f49e2d801af1915998/receipt.json`：受改 Python compile 0、聚焦 **136 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；Job 無殘留 PID 或強制清理。Watchlist 逐列審查狀態分布需同版批次 DTO／讀取契約，避免不同 revision 混畫，本輪延後。M1–M110 是含審查及 QA 的切片序號，非 110 個獨立功能。正式市場／Paper／私人 Watchlist、自然排程、其他真 DPI、1920 可用螢幕、固定新版 EXE、Owner UAT、M73／M75 契約及完整產品 Gate 未驗；沒有 push、merge、部署或正式資料修改。

## M111–M113 最佳化、選股與情境資訊層級

Luna `/root/m107_evidence_audit` 唯讀盤點 Backtest 後，單一 writer 僅改 `ui_qt/views/backtest/result_panel.py`、`ui_qt/views/backtest_view.py` 與新聚焦測試。M111 將原 `OptimizationStabilitySummary.parameters` 的 `top5_concentration_bp`、`top5_present_count`／`top5_total_count` 畫成最多八個參數的有限橫條，保留原 `to_text()` 和最佳化表；不足／未知不畫假值，開始新掃描、空結果與不足摘要清舊。Sol 審查發現空結果原文字與表也可能留舊，退回一併清理後接受。這只描述目前保留且有效 objective 的最多前五筆中有值參數之眾數占比，不是完整參數面、OOS、統計穩健性、績效或資格。正常 Main 1280×760／1500×900、真 OS DPI216 隔離六筆合成結果，圖條、精確 6000 bp（5／5）與原表同屏目視；收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_458b5ee1951f40c8a78b34f4225423b9/receipt.json`、圖 `.../root/native_m111_backtest_evidence/run_86a8aef117c142c88aab8b603cd33657/`。首輪 native harness 被既有完成模態通知阻住，root 中斷該 owned Job、確認該 PID 及 Python 程序已不存在後，改探針攔通知再重跑；該中斷輪沒有正式 receipt，不當作通過。

Luna `/root/m108_research_visual_audit` 唯讀核綜合選股現有 `FunnelMetric` 五態契約，單一 writer 僅改 `ui_qt/views/unified_screener_workspace.py` 與測試。M112 在預設收合的母體漏斗明細畫最多六項五態分布，只有同一條件完整、非負、加總等於其分母且分母大於零才畫比例；明示每項自己的分母、可能重疊，原計數文字及來源／查詢身份保留。零分母保留 0、缺值／矛盾不補值，busy／failed／無結果清舊圖。Sol 目視首版用綠「符合」／紅「不符合」可能混淆台股漲跌，退回改藍／藍灰等類別色後接受。最終正常 Main 1280／1500 真 DPI216 合成同版投影，結果區仍可到達；收據 `.../root/single_owned_qa_789dfb8910a2411bad81b7a9bedf80e4/receipt.json`、圖 `.../root/native_m112_screener_evidence/run_e40b47786bad4f16978126f176becc9f/`。這不是逐步淘汰、跨條件排名、收益或來源資格；正式查詢原件未在本輪驗。

Luna `/root/m107_portfolio_audit` 唯讀排除同股 Paper 舊項與跨次 Stress 比較的不可比來源後，單一 writer 僅改 `ui_qt/views/portfolio_view.py` 與測試。M113 在「情境壓力 → 目前情境」選取前以原 `StressScenarioDefinition` 顯說明、支援與必要輸入；未知定義保留未知，72 邏輯像素高有界可捲。Sol 退回首版在未執行時拼出 `scenario_requires` blocker 的說法，改為原定義能力提示、實際診斷依當次結果；原執行、保存、來源及 A→B 清舊不變。正常 Main 1280／1500 真 DPI216、隔離空帳支持／不支持情境四圖及收據 `.../root/single_owned_qa_1dc9333cac3e4a8580cde97491981c9c/receipt.json`、`.../root/native_m113_stress_preview_evidence/run_bf38d91a8d4642329ae8bef65b0e768a/`。前兩次 native harness 選到保存歷史、又以舊文案斷言，失敗收據 `.../root/single_owned_qa_14eab38b7241473d87041215e4fa781f/receipt.json`、`.../root/single_owned_qa_dc54fa0ed3ae489595fa22907ea3dca2/receipt.json` 保留，修 harness 後通過。

三切片最終共同 8 GiB／12 程序 Job `.../root/single_owned_qa_e0e5ffe4d0fa41be9f086ad7a6860e5b/receipt.json`：受改 Python compile 0、聚焦 **117 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean，無殘留 PID 或強制清理。首輪 `.../root/single_owned_qa_c4f0fc366f884b4aad8408bc36e0abe6/receipt.json` 聚焦 3 個新測試的文案斷言不符（113 passed／3 failed），產品文案較精確，修測試與圖色後最終通過；原失敗未抹除。M1–M113 是含審查、實作與 QA 的切片序號，不是 113 個獨立功能。正式市場／Backtest／私人 Portfolio、自然排程、其他真 DPI、1920 可用螢幕、固定新版 EXE、Owner UAT、M73／M75 契約及完整產品 Gate 未驗；未改金融公式／DTO、正式或私人資料，未 push、merge 或部署。

## M114／M115 市場判斷與營運快照分布

Luna `/root/m108_research_visual_audit` 唯讀核對原市場 Regime detector 的 Trend 結構分由 `close_above_ma60`、`ma20_slope_positive`、`plus_di_above_minus_di` 三條組成，發現「大盤指數」判斷摘要只列前兩條。單一 writer 只改 `ui_qt/views/market_regime_view.py`、`tests/test_ui_qt_market_regime_view.py`；M114 加第三條來源布林的真／假／未知文字，不改 detector、結構分、DTO、技術細節或交易資格。Sol 複核測試與同份合成結果 before／after View 圖，再沿正常 Main 按原「檢測市場狀態」按鈕驗 1280×760／1500×900 真 OS DPI216，第三條可見，左側本次分類與資料日一致。初版 native harness 直接呼叫摘要 render，留下「尚未檢測」與結果同屏的矛盾畫面；該收據 `root/single_owned_qa_90ce9cb026474979978557dbe0957cfa/receipt.json` 不作完整操作證據。修正後 `root/single_owned_qa_33a3d723d6c84060a17eef8ae37d59a7/receipt.json` 與 `root/native_m114_m115_evidence/run_7437edcac24443aaacc9eaabaf71755f/` 通過；同份 before／after `root/single_owned_qa_fd3fed5938c748c29d837e27679a3569/receipt.json`、`root/native_m114_m115_compare_evidence/run_6166ac69de86454c8e0aa849d38188c7/`。

Luna `/root/m107_evidence_audit` 唯讀核對 Runtime `ScheduledOperationsSnapshotDTO.operations` 單一已保存狀態快照後，單一 writer 只改 `ui_qt/views/runtime_view.py`、`tests/test_ui_qt_runtime_view.py`。M115 在核心就緒與原清單間加有限六類分布與精確計數：正常、安全邊界中、需要注意、無法判定、來源未確認、未知狀態。僅 `read_state=observed` 計入已觀測 normalized state；未知新碼不補正常。狀態選單仍只篩清單，全快照圖保持不變；替換／空快照清舊段，原碼與 read state tooltip 可核。條長只表示本次工作項目比例，不是 Windows Scheduler 執行紀錄、工作成功率、核心就緒分母或資料資格。Sol 目視正常 Main 1280／1500 真 DPI216 圖與同資料 View before／after，六段可讀、原清單仍可捲。上述最終 native 與 before／after 收據共用。

共同受控 8 GiB／12 程序 Job 首輪 `root/single_owned_qa_62b56448cebc4fb38b0e711b5e352e1c/receipt.json`：受改 Python compile 0，聚焦 32 passed／1 failed，失敗是新空快照測試把計數行誤當文字結尾，實際還有精確「共 0 項」；Workbench 85、validator 25／0／4、mypy 1,144 clean，原失敗保留。Luna 修正測試斷言後，最終 `root/single_owned_qa_514be759d88c42899e87cbc65d15c143/receipt.json`：compile 0、聚焦 **33 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；無殘留 PID 或強制清理。M1–M115 是含審查、實作與 QA 的切片序號，非 115 個獨立功能。

Portfolio Stress 目前結果雖有 optional `as_of_date`，計算列沒有逐部位報價來源身份；同一代號或同數值快取不足以證明與計算採用的價格同源。此候選轉為先補 UI DTO／Application Adapter 的後續契約工作，本輪不猜日期、不寫入 result。正式市場／營運排程／私人 Portfolio、其他真 OS DPI、1920 真可用螢幕、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未驗；未讀寫正式或私人資料，未 push、merge 或部署。

## M116／M117 月報酬色階與研究母體下鑽

M116 由 Luna `/root/m107_evidence_audit` 單一 writer 修改 `ui_qt/views/backtest/analyst_diagnostics_widget.py` 及聚焦測試。月度矩陣只對整體與月列狀態皆 `available`、`return_bp` 為真正整數的格上色；正值按台股習慣紅、負值綠、真零中性，四色階只相對本次顯示有效月份的最大絕對 bp。重複年月只以最後顯示的列定尺度，未知、缺月和期間外沒有方向色；原 `return_text`、跨度限制及其他診斷表不變。Sol 原生 before／after 發現首版雖有 item BackgroundRole，全站 QSS 使像素未顯色，退回後以月表專用 delegate 繪出背景並保留選列高亮；最終正常 Main 向下捲至月表的 1280×760／1500×900 畫面可辨紅、綠、零與未知。這是同 run 掃讀輔助，不代表跨 run 比較、OOS、未來績效或新金融資格。

M117 由 Luna `/root/m108_research_visual_audit` 單一 writer 修改 `ui_qt/views/daily_market_cohort_view.py`、`ui_qt/main.py` 與聚焦測試。市場探索「研究母體盤勢」新增已發布成員的明選個股入口，僅用同一 `VerifiedDailyMarketSnapshot` 的 typed row 和現有 `context_for_stock`；核股票、manifest ID/hash、cohort、決策日、資料日、固定條件與 snapshot root，缺件停用。返回時先重核原列，來源變更不切頁、不改選同股其他結果。Sol 正常 Main 先發現個股報告重讀 pinned artifact 前會暫清 `data_date`，首版完整 context 相等檢查拒絕合法返回；修正為只在其餘欄位與開啟時原 context 完全相同且日期僅暫空時，用原已釘選日期重核盤勢列。正常 Main 的同列返回及來源失效拒絕均通過；沒有改快照產生、篩選公式、報告計算或來源資格。

最終受控 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_bdda3d1ec3c2489ea69ea65c9aac32dc/receipt.json`：受改 Python 編譯 exit 0、聚焦 **21 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；Job 無殘留 PID 或強制清理。原生合成正常 Main／同資料 baseline before-after 在真 OS DPI216 的 1280／1500 寬度與精確返回已目視，隔離 SQLite SHA 前後一致；Job 收據 `.../root/single_owned_qa_47a7dd77496a45508879b803ec8979fb/receipt.json`，十一張 PNG 及身份／hash JSON 於 `.../root/native_m116_m117_evidence/run_3346344046514cf29c89922184109049/`。初輪 QA 聚焦斷言 21 passed 但 Qt TaskWorker 未自然終態，`.../root/single_owned_qa_02b240da1cbf460ebfd646a45ceb2969/receipt.json` 記 exit 1；修測試關閉等待後重跑通過。原生首輪未先讓來源 View 接受快照的 harness 失敗、以及修前實際返回拒絕，原收據都在本機 `QA_RESULTS.md`，不併作通過證據。

### 從排程開工至 M117 的盤點

Opus 起始唯讀 UI／UX 審查，額度用盡後 Antigravity 接手六報告與設計成果；Sol 核對原件、現行程式、Roadmap、金融／PIT／來源契約並去重，按可實作前置選 P0–P3 切片。Luna 以單一 writer 檔案範圍完成具名變更，root 退回語義或原生畫面缺陷、受控執行 Python／Qt QA、維護本機原始收據與版控摘要。M1–M117 **包含唯讀裁決、QA 專項與實作序號，不是 117 個功能**。

| 範圍 | 累積工程結果 |
| --- | --- |
| P0 金融辨識與資訊層級 | 台股紅漲綠跌、正負／單位／日期、未知與真零、首屏 KPI、載入／錯誤／過期清舊；個股 ML 估計完整性、Stress 情境身份與保存守衛、決策品質精確範圍提示。 |
| P1 產業與題材 | 原九指標卡、限定成交額與漲跌格、雙版本原值、同版本成員分類／共用鄰域、同名辨識與搜尋、成員下鑽；未把靜態分類畫成有向供應鏈。 |
| P2 研究介面 | 市場廣度與原流向、個股證據、推薦／選股五態、Portfolio／Paper、Backtest 月表與最佳化、Evidence／Runtime 的圖卡、表格混合、長清單分頁與來源返回。M116–M117 補月度色階與盤勢成員精確往返。 |
| P3 進階探索 | 同版題材與股票關聯可查；真公司間有向供應／客戶邊、跨期強弱仍待逐邊來源、可得時鐘及用途契約。 |

這次收尾是**後繼原始碼與隔離合成 QA**。正式市場／Evidence／私人 Portfolio 來源、自然排程、其他真 OS DPI、1920 真可用螢幕、Light 若支援、固定新版 EXE、Owner UAT、M73 決策品質控制語義、M75 有向關係／跨期用途契約、Stress 逐列計算報價 provenance 與完整產品 Gate 均未由本輪接受。沒有自動交易、broker order、正式或私人資料改寫、其他自動化修改、push、merge 或部署；`output/` 原始證據不提交。

## M118／M119 題材 L1 組成與資料缺口追溯

M118 由 Luna `/root/m108_research_visual_audit` 單一 writer 修改 `ui_qt/views/industry_theme_map_view.py` 與聚焦測試。現有 `ThemeClassificationPresentation.members` 已含所選題材同版 L1 原始標籤，但先前只能逐位讀 tooltip；新增有界組成卡以分類列總數為分母，精確顯最多八個類別、其餘合併及空白欄位。非空白原值不做合併正規化，字面「未提供」與真正空白分開；過長名稱省略時 tooltip 與原成員表保留原值。卡片明示資料日／mapping 日期及非權重、供應關係、歷史 PIT 的限制。Sol 原生目視發現首版 108 邏輯像素的標籤欄幾乎逐字折行，退回後改有界 190 像素與完整 tooltip；最終正常 Main 1280×760／1500×900、真 OS DPI216 可直接掃讀條與數字。沒有改分類 mapping、DTO、來源資格或金融計算。

M119 由 Luna `/root/m107_evidence_audit` 單一 writer 修改 `ui_qt/views/live_research_gap_view.py` 與聚焦測試，Sol 複核後補表前可選取文字的「所選列追溯 ID」摘要及明細最小高度。該頁原 dashboard row 已含 `research_run_id`、`evidence_event_id`、`evidence_outcome_id`，先前卡片會計缺件，選列卻無法核原 ID；現在同列摘要與可複製明細顯原值，缺件為「未提供」，換列、刷新、空及錯誤清舊。正常 Main 原生畫面在 1280 首屏下半可見三個 ID，明細仍可核原來源與連結信心；ID 本身不證明匹配、有效 Evidence 或來源資格。沒有改 producer、連結判定、正式資料或金融公式。

最終共同 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_799c0acbcd2c48a9abcaf0ec84dc2a4a/receipt.json`：受改 Python compile exit0、聚焦 **91 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；Job 無殘留或強制清理。隔離合成 normal Main、同資料 baseline before／after、真 OS DPI216 的 1280／1500 原生 Job `.../root/single_owned_qa_9184c508482149438ae8af7b35fb1f6c/receipt.json` exit0；11 張 PNG、題材合成 snapshot SHA 前後一致及結果 JSON 位於 `.../root/native_m118_m119_evidence/run_e3f7380605164888a4fa8788ac8690d9/`。首輪聚焦因不可達的測試失敗分支，後一輪因省略標籤仍用舊測試文字而失敗；原收據及修正理由保留在本機 `QA_RESULTS.md`，不當作通過證據。M1–M119 是審查／實作／QA 切片序號，非 119 個功能。

Watchlist 逐列查看狀態的同版分布尚缺公開批次 DTO：現有逐列 `get_review_state()` 每次重讀可能混 revision，故本輪只完成唯讀契約盤點，沒有畫假同版圖。Stress 逐列計算報價來源、M73 控制作用範圍、M75 有向供應鏈／跨期用途仍待各自契約。正式市場／Evidence／私人 Portfolio、其他真 OS DPI、1920 可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT 與完整產品 Gate 未驗；沒有 push、merge、部署或正式／私人資料改寫。

## M120 Watchlist 同版私人查看狀態分布

Luna `/root/m107_portfolio_audit` 單一 writer 補 `app_module/watchlist_review_state.py`、`app_module/watchlist_service.py` 與服務聚焦測試：唯讀 `get_review_snapshot()` 在一次 `_load_watchlist()` 取候選列、原顯示欄位與逐列狀態，共用頂層 revision；原逐列 getter、CAS writer 及私人儲存不變。SQLite revision 保留原整數，legacy JSON 為 `None`；同股不同 item hash 按原位置分開，缺身份、重複身份、schema/hash 損毀為 unknown。原候選 notes 欄仍可顯示，但新 DTO 不增加 review reason 欄或輸出 extension。成功空、清單缺件、讀取失敗各有不同狀態，不能混作零。

Luna `/root/m108_research_visual_audit` 單一 writer 補 `ui_qt/views/watchlist_view.py` 與 UI 聚焦測試：候選表前顯待查看／已確認／稍後／未知四類原列數及比例，表與卡同用快照，不做第二次 `get_stocks()`。若服務沒有 batch 方法，舊相容路徑仍能讀候選表，但分布明示未知；已有 batch 方法而回錯或壞型別則清舊並拒絕第二次讀取。選列另讀若 revision 或列狀態已變，停用私人保存並要求刷新；legacy 無持久 revision 會標另讀可能較新。Sol 退回首版缺清單假 0、快照失敗再讀及分布在長表後的設計；正常 Main 1280 原生圖又見四列條把表完全推離首屏，改為兩欄兩列與精簡說明。最終 1280 首屏可見卡及表首列上緣，1500 可讀更多表內容；卡片只表示私人查看進度，非金融評分。

最終 8 GiB／12 程序受控 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_97899f60942b4138bd94580d6edfe58f/receipt.json`：受改 Python compile exit0、聚焦 **28 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，Job 無殘留或強制清理。首輪新測試替身建構失敗的原收據 `.../root/single_owned_qa_e12427afaab14bd68241d6d56163a19b/receipt.json` 保留，不冒作產品失敗或通過。最終正常 Main 1280×760／1500×900、真 OS DPI216、隔離合成四態／成功空／載入不可用原生 Job `.../root/single_owned_qa_cb00d89c4a3e4f39b8880ef2f35aee01/receipt.json`，PNG 與 JSON 位於 `.../root/native_m120_watchlist_evidence/run_f1affcf68cfd41a490ab15d3e551c467/`；before 可核 M110 的 `.../root/native_m110_watchlist_evidence/run_28831576d5874620a6ee6849eb06e560/`。前兩輪版面 PNG 與收據保留，不能取代最終圖。

M1–M120 為審查、實作與 QA 切片序號，並非 120 個獨立功能。正式私人 Watchlist／市場來源、其他真 OS DPI、1920 可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT、Stress 逐列報價身份、M73／M75 契約及完整產品 Gate 未驗；此提交只收束本輪原始碼與隔離 QA，沒有 push、merge、部署或正式／私人資料改寫。

## M121 Stress 逐列計算輸入可核對性

Luna `/root/m107_portfolio_audit` 唯讀盤點確認：`PositionDTO.current_price` 僅為 scalar；`PortfolioService._position_to_dto()` 的計算取價與 `get_current_price_observation()` 分讀，CSV 重複列時的選擇語義也不同。Stress `evaluate_positions()` 消費前者，`StressPositionResult` 已保留同次結果的 `quantity` 與 `mark_price`，卻不帶 quote date／source identity。Sol 因此只接受同筆結果已具備的計算輸入展示，拒絕由價值相等的其他快取推定逐列報價來源或日期；未改取價、Stress 公式、DTO、保存與私人持倉。

Luna `/root/m108_research_visual_audit` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`。目前情境逐列結果表在名稱旁增加「計算輸入」：原股數 × 每股 TWD mark price；部分計算只列有價持倉，缺價保留原警示。診斷明示此結果沒有逐列報價資料日／來源，切換情境或載入失敗清除舊結果。Sol 檢查 diff、測試與原生畫面後接受；這是可核對性提升，並未授予行情新鮮度、投資有效性或交易資格。

最終 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_5f1255c06c0d49cfa6e83409d92db764/receipt.json`：受改 Python compile exit0、Portfolio **80 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，無殘留或強制清理。正常 Main、隔離合成完整與缺價持倉、真 OS DPI216 的 1280×760／1500×900 圖及結果在 `.../root/native_m121_stress_inputs_evidence/run_5d36e2e4436e4ba4824af336a0add9c6/`；受控 Job `.../root/single_owned_qa_64dab868bbc240cd80b8d8bf6beb9919/receipt.json` exit0。Sol 目視捲至表格後，表頭與兩列輸入在 1280 可讀。前兩輪 harness 捲動位置造成無效表格截圖，原收據 `.../root/single_owned_qa_e0fff916211040549ba25723059e8d99/receipt.json`、`.../root/single_owned_qa_30f71aa602a74ba38bca6c50bdd728aa/receipt.json` 保留，不當作通過證據。

M1–M121 是審查、實作及 QA 切片序號，非 121 個獨立功能。下一步若要顯報價日期與來源，須先讓 `PortfolioService` 在同次取價帶逐部位價格／日期／來源／身份，再沿 Stress 輸入與 result 傳遞，對 CSV 重複列明訂一致選擇語義；不能事後用同價快取配對。正式私人 Portfolio、其他真 OS DPI、1920 可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 仍未驗；沒有 push、merge、部署或正式／私人資料改寫。

## M122 Stress 同次報價來源與資料日

Luna `/root/m107_portfolio_audit` 單一 writer 修改 `app_module/portfolio_service.py`、`app_module/dtos/portfolio_dtos.py` 與 `tests/test_portfolio_quote_freshness.py`：Portfolio 持倉在同一次取價讀取中綁 `current_price`、quote date、source ID、snapshot SHA-256 與 freshness。SQLite 沿原日期排序／LIMIT 單列查詢；即使舊 schema 缺附屬欄，收盤價仍可用。CSV 同檔同代號重複列沿原首列取價，hash 對應同次讀入的整個檔案。原 `get_current_price()` 純價格 API 與 SQLite→CSV 降級、損益 Decimal 投影及私人帳 writer 未改。這個 quote 來源不等於資料可得時鐘或 PIT 資格。

Luna `/root/m108_research_visual_audit` 單一 writer 修改 `app_module/portfolio_stress_lab_service.py` 與 `tests/test_portfolio_stress_lab_service.py`：Stress 直接由每個 input position 複製可選 metadata 到同列 `StressPositionResult`／v1 payload；缺或無效 ISO 日、hash、freshness 保留未知，不按股票代碼回查，也不由多列推整體 `as_of_date`。Luna `/root/m122_stress_ui` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與聚焦測試：目前情境表保留 M121 計算輸入，加入有界報價摘要，明選列可複製完整 hash。Sol 退回首版以原始列號另存詳情導致排序錯列，改成資料列內隱藏明細隨 sort 移動；又修正 DTO 預設 `unverified` 誤抑缺件警示，以及排序後選列重核、超前日期提示。原生目視再收緊少量列高度與表／明細間距；缺價 partial、情境切換及失敗清舊沿原行為。

首輪受控 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_7180cf43f5a34f5594ebe610ee23e686/receipt.json`：compile、聚焦 **117 passed**、Workbench **85 passed**、validator **25／0／4**，mypy 因 `**dict` 類型推斷 1 error，修為具名欄位後最終 `.../root/single_owned_qa_cf1cf9babd2543a2a832fa07c9c0af5b/receipt.json` 全部通過，mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留或強制清理。隔離正常 Main 1280×760／1500×900、真 OS DPI216、兩筆有來源與一筆缺價 partial、另有未知來源畫面，最終 `.../root/single_owned_qa_199813800a8043acaa42bdbe74f325cd/receipt.json` exit0；5 圖／JSON 在 `.../root/native_m122_stress_quote_evidence/run_a947181a6fa544fea7dcb3d325d516c8/`。Sol 目視表格與所選列日期／來源／完整 hash 同屏可讀；前兩輪版面圖留 QA_RESULTS，不作最後版面證據。最後文件及 task 檢查見本機任務紀錄。

M1–M122 是審查、實作及 QA 切片序號，非 122 個獨立功能。新 Stress v1 payload 增可選逐列欄位，舊保存歷史的 canonical payload／hash 原封不動，歷史 UI 尚未提供逐列來源回訪；CSV hash 為整檔而非重複列專屬指紋。正式私人 Portfolio／行情、其他真 OS DPI、1920 真可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未驗；未推送、合併、部署或改寫正式資料。

## M123 已保存 Stress 逐列來源回訪

Luna `/root/m107_portfolio_audit` 單一 writer 修改 `app_module/portfolio_stress_history.py`、`app_module/portfolio_stress_lab_service.py` 與兩份服務測試：保存紀錄的 payload hash 與索引欄必須對同一份 canonical Stress v1 payload 一致，否則 read service 降級；`project_position_rows()` 只由保存 payload 投影，保留逐列原數值文字、列序、同股多列及可選持倉／Portfolio 身份。新 result 的 v1 payload 可選附身份，舊結果不回寫；缺 `positions`、明示空陣列、缺價代號缺欄、舊版逐列來源缺欄及逐列壞型別分別處理。重複持倉 ID 保留兩列並標診斷，不假合併；未查現況、不改 Stress 公式或來源資格。

Luna `/root/m123_history_ui` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與 UI 測試：已保存歷史總表以隱藏 record ID 對回排序後原件；原三額卡下加入預設收合、最多約 190 邏輯像素高的逐列表，明選列可複製原報價來源 SHA-256、日期、來源、freshness 與持倉身份，payload hash 另列。切換紀錄會收合與清舊；刷新、空結果、錯誤亦清除。Sol 複核修正測試對 Decimal 原字串的預期、預設排序假設、不同紀錄切換後收合、錯誤清舊；逐列表固定保存原序，避免字串金額被字典序誤排。原生目視後又隱藏舊版空表、把技術碼移到 tooltip，讓畫面直接說明「未記錄／未知」，並將新明細設純文字。所有原始失敗收據均保留，不充作通過。

最終受控 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_15ee8929fe18423c869f696c09c1d05a/receipt.json`：受改 Python compile 0、Portfolio／Stress 聚焦 **142 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。正常 Main 1280×760／1500×900、真 Windows DPI216 的隔離合成新／partial／legacy、收合／展開與同股多持倉五張最終 PNG、JSON 在 `.../root/native_m123_history_evidence/run_312f2a0e524c4577b74ce8d82c56a8d3/`，Job 收據 `.../root/single_owned_qa_e86d65e8123e488894b0d2b09437abc3/receipt.json` exit0；Sol 目視接受。初版空表與原診斷碼圖在 `.../root/native_m123_history_evidence/run_673e581f233d49cc98d4df0a7c4a5164/`，只作 before。首次用系統 Python 的工具環境缺 PySide6／mypy、後續三輪測試預期或清舊失敗的收據均留 `root/`，最後以 repo `.venv` 及修後收據為準。

### 排程啟動至 M123 的工程盤點

Opus 啟動審查後因額度用盡由 Antigravity 接手完成六份主要報告及設計附件；任務 `task.json` owner 是 Antigravity。Sol 依現行程式、產品架構和金融契約逐項去重與取捨，Luna 依檔案所有權實作，root 逐切片複核並序列執行受控 QA。**M1–M123 是審查、裁決、實作與 QA 的切片序號，不是 123 個功能**。

| 範圍 | 已完成的原始碼與可核證成果 |
| --- | --- |
| P0 金融辨識與狀態 | 台股方向色、正負／單位／日期、真零與未知分離、首屏資訊、載入／錯誤／刷新清舊；M102 情境 A→B 清舊與保存身份守衛，M121–M123 補 Stress 當次輸入、同次報價與保存回訪。 |
| P1 產業題材 | 同版九指標摘要、成交額面積格、原值比較、名稱／股票反查、分類成員與共用成員鄰域、同版 L1 組成及個股精確往返；靜態重疊不稱供應鏈。 |
| P2 全站研究 | 市場廣度／趨勢、個股資料圖卡與 ML 估計提示、推薦／選股漏斗、法人共用零軸、Portfolio／Paper Health／Watchlist、Backtest 月表與穩定性、Evidence 品質／追溯、Runtime 保存狀態與耗時；保留原表及來源。 |
| P3 進階關係 | 已完成同版分類與共用成員的安全探索；公司間有向供應邊、跨期強弱及用途資格因逐邊來源與時間契約不足而未實作。 |

本輪工程收尾限於受追蹤原始碼、隔離合成資料與上述真 Windows DPI216 畫面。正式市場／私人 Portfolio 的授權唯讀副本、其他真 OS DPI 與 1920 可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT、M73 決策品質作用範圍、M75 有向／跨期來源契約及完整產品 Gate 仍須分開驗；`output/` 原始證據留本機，不進版控。沒有實盤、broker order、正式資料改寫、其他排程修改、push、merge 或部署。

## M124／M125 同源警示與行情日期呈現

Luna `/root/m108_research_visual_audit` 單一 writer 修改 `ui_qt/views/live_research_gap_view.py` 與 `tests/test_ui_qt_evidence_review_dashboards.py`。Evidence「資料缺口」用原 `LiveResearchGapDashboardResult.warning_counts` 與本次 `rows[].warnings` 逐字核對，預設收合顯前五種警示文字的次數條與有界其餘類數／次數。總分母是警示出現次數，一列多則分別計入；diagnostics、型別、總數、逐字或列數不符時顯未知並清舊。Sol 複核補收合時摘要真正隱藏及即時清除舊條，避免刷新瞬間仍看見前次警示。原 service、來源資格與逐列文字不變。

Luna `/root/m107_portfolio_audit` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`。手動 Portfolio 持倉表的「目前價格／行情資料日／行情日期狀態」改從同一 `PositionDTO` 列讀取；另讀 `_current_snapshot_for_position()` 仍只供原條件監控等路徑，不把該次觀測的日期貼到不同取價結果。Sol 補無價格或無有效 ISO 日期的 fail closed 呈現；來源自稱 current／stale 而日期未知時保留原狀態並明示無法核日。同股多筆靠 position identity 留列，原價格、估值、公式、來源優先序與私人帳均未改。

首輪受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_28ea01c67e344826a4450a71e716c896/receipt.json` 為新測試監控欄未先選股造成 **4 failed／158 passed**，程式檢查其餘項通過；修正測試操作後，最終 `.../root/single_owned_qa_e245dd0749964e34ad5648f02dae711d/receipt.json`：compile 0、聚焦 **162 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留或強制清理。正常 Main 1280×760／1500×900、真 Windows DPI216 的隔離合成已載入收合／展開、來源不可用及 Portfolio 同股資料日錯配示例共七圖，結果在 `.../root/native_m124_m125_evidence/run_d30847be1d314fae81fbc18f9a87d565/result.json`，Job `.../root/single_owned_qa_a7093cc406094ef3b174b63fbd505496/receipt.json` exit0；Sol 目視 1280 畫面圖卡、表列與未知狀態可讀，隔離 SQLite 前後 SHA 相同。

排程啟動至今的分期範圍沿上表 P0–P3；M124／M125 新增的是 Evidence 警示頻次與 Portfolio 同列報價日期一致性，**M1–M125 仍是切片序號，不是功能數**。正式 Evidence／私人 Portfolio、其他真 OS DPI、1920 可用螢幕、Light 若支援、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受。原始 PNG／receipt 留 ignored `output/`，不進版控；未 push／merge／部署或改正式資料。

## M126／M127 Stress 診斷與 Paper 提案分布

Luna `/root/m107_portfolio_audit` 先唯讀找到 Stress 當前結果把 service blocker／warning 直接顯底線代碼的缺口，再作 M126 單一 writer，只改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`。已知碼（無持倉、缺必要輸入、來源不可用、缺價、部分結果不外推、流動性替代指標非損益）以繁體中文說明並保留原碼，未知碼原樣顯示；換結果、載入失敗清舊。原 scenario、計算、DTO、歷史 payload 與來源資格不動。

Luna `/root/m108_research_visual_audit` 唯讀排除已完成的 Watchlist 同版狀態圖及月營收圖，核 Paper Health reader 在空、封鎖／過期時的來源撤銷語義，再作 M127 單一 writer，同兩檔串行修改。只有 schema、來源及逐列型別可核、非空且無 blocker 的同一 `PositionHealthReadModel` 才畫五種 `proposed_state` 的評估列數；同股不同 position 各列保留。缺席類別可顯真 0/N，資料缺失／來源不可靠／型別或狀態無效顯未知並清舊，不把 blocked/stale 被撤銷成 WATCH 的列當成正常提案。原表、選列詳情與 review_required 分母獨立。Sol 首輪 QA 發現 malformed row 雖被圖卡拒絕，舊摘要仍讀取而例外，於共用呈現入口先驗列型別並清表；再將新增畫面中的內部術語改為使用者可讀語句。兩 Luna 沒有修改金融公式、reader、正式私人帳或排程。

M126 中間共同受控 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_bc4905c2b31d49199e678c359a60d4fd/receipt.json` 為 focused **163 passed**、Workbench **85 passed**、validator **25/0/4**、mypy **1,144** clean；正常 Main 1280／1500 真 OS DPI216 的 partial、liquidity、unsupported 四圖在 `.../root/native_m126_stress_diagnostics_evidence/run_2cdeeacbcfd04afeb1c94a5c921d3946/result.json`，Job `.../root/single_owned_qa_21cfaf2b22a3429e881844c61c4fa28c/receipt.json`。M127 首輪共同 Job `.../root/single_owned_qa_e1e85c4f76dd4090867dd4db7ba85bdc/receipt.json` 是 **165 passed／1 failed**：malformed 列使舊摘要例外，原失敗保留；修後及文案後最終 `.../root/single_owned_qa_62640d926640413c85a930688ff8c4d4/receipt.json`：compile 0、聚焦 **166 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** clean，8 GiB／12 程序 Job 無殘留／強制清理。Paper 健康圖與表首列在隔離正常 Main 1280×760／1500×900、真 OS DPI216 同屏；blocked／empty 清舊圖及 JSON 最終在 `.../root/native_m127_paper_health_evidence/run_e4e63924b2594fbc81403b9287eaec51/`，Job `.../root/single_owned_qa_45189da1717541f69a0a1afaa035040e/receipt.json` exit0，隔離 SQLite SHA 前後相同。Sol 目視接受；初版合成 fixture 的原因文字與 verified 狀態不符，原圖 `.../run_7691e8ae4b774c689f04abf6fc945e2c/` 保留而不作最後視覺證據。

M1–M127 是審查、裁決、實作與 QA 切片序號，非 127 個功能。正式 Paper／私人 Portfolio 來源、其他真 OS DPI／1920 可用螢幕／Light 若支援、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受；本輪證據留 ignored `output/`，不推送、合併、部署或改正式資料。

## M128 題材 L1 圖至成員表導覽

Sol 在 M1–M127 後盤點 Opus 的 P1／P2 候選與目前程式，Luna `/root/m108_research_visual_audit` 唯讀指出既有 L1 組成圖只能看類別列數，無法沿圖找到完整成員；Luna 隨後單一 writer 修改 `ui_qt/views/industry_theme_map_view.py` 與 `tests/test_ui_qt_industry_theme_map_view.py`。M128 令最多八個原始類別、精確省略類別的「其他」及空白欄位各能篩同一份 typed snapshot 的題材成員表；按「全部成員」還原。篩後分頁按符合列數，個股導覽的 `origin_row_index` 仍指原題材完整列序；分類股票鈕或反查若定位篩選外股票，先還原完整表再定位。換題、換版、失敗或收合清舊；不改 DTO、mapping、金融公式或來源資格。Sol 原生目視發現初版點類別只停在圖下說明，1280 視窗看不到表；修為捲到表格頂端，最終點選後同屏見篩選狀態、表頭與符合首列。

受控 QA 首輪 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_80b68d1ef8e741578be8e36a2b71838c/receipt.json` 為 33 passed／2 failed：新測試文案預期與實際分頁句型不符。後續 `.../single_owned_qa_bab7ad4c1c024bb4982fdc7f45fa84f5/`、`.../single_owned_qa_305ba87f83ce474993401239d7f04aab/`、`.../single_owned_qa_1012f4fcbec7406785cf801ec0b82367/`、`.../single_owned_qa_05094fb8024a436eab22f00e6444a98e/`、`.../single_owned_qa_535c0a7ce8484fcfaac706f32b84ceff/` 反映測試從舊 `deleteLater` 圖卡取到 stale 按鈕的定位過程；原失敗保留。改由目前 layout 實際圖卡取按鈕後，最終 `.../single_owned_qa_e8a4d8ee7dfc4a5caf513f1d5ebfbd1c/receipt.json`：compile 0、定向 **35 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** clean；8 GiB／12 程序 Job 無殘留或強制清理。

正常 Main 真 OS DPI216、1280×760／1500×900 隔離合成 13 成員原圖／點選／表格五張最終 PNG 與同一 fixture SHA 見 `output/tasks/baldr-opus-ux-implementation/root/native_m128_evidence/run_42d06b78f0a14081bc152b9a103e5a8a/result.json`，Job `.../single_owned_qa_2b5f8aa092f34575a3606dd3c8f279e7/receipt.json` exit0。Sol 目視 1280 點後直接見 1000／1001 兩列，1500 圖與表亦可讀。原版初步 `.../native_m128_evidence/run_c674fc765eb3443fbb6f5de49c955ed4/` 和中間自動捲動落點 `.../run_c36a7c047f544c5c819363b74c877bf2/` 保留，不當最終版面證據。Light 主題盤點發現全域 QSS、表格模型、圖表與多處局部深色硬碼仍相依；本輪未宣稱支援 Light，未將市場方向色隨主題翻轉。正式市場來源、其他真 DPI／1920 可用螢幕、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 分列未驗；合成 UI QA 不等於正式接受。

## M129 Matplotlib 備援圖 hover 提示

Sol 盤點共用視覺層後，Luna `/root/m108_research_visual_audit` 唯讀確認 Light 需要獨立 AppAppearance 契約與跨頁遷移，現階段不以 QSS 換色宣稱支援；Luna `/root/m107_portfolio_audit` 唯讀找到 Matplotlib 備援權益曲線的 `mplcursors` 買／賣 hover annotation 在深色圖上動態生成白底。後者單一 writer 修改 `ui_qt/widgets/chart_widget.py`、`tests/test_ui_qt_chart_widget_factory.py`，在兩個新增 callback 保留原文字後套用既有圖表文字、底色與邊框 token。Sol 審核範圍只觸及 annotation 呈現；買賣點資料、損益／報酬公式、WebEngine 圖與台股行情方向色沒有改動。

受控 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_6e74c4d1206942acaa96c800018449af/receipt.json`：受改 Python compile 0、聚焦 **8 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留／強制清理。隔離合成 `EquityCurveWidget` 真 Windows DPI216、1280×760／1500×900 的 before 白底／after 買賣深底四圖及 SHA 在 `output/tasks/baldr-opus-ux-implementation/root/native_m129_evidence/run_a4bc1ffa8fc64ed98798d17d521dbb14/result.json`，受控 Job `.../single_owned_qa_4ec273cb58c04ff4976d775eccb85096/receipt.json` exit0；Sol 目視確認文字與曲線對比。此圖以 callback 注入模擬 hover，未沿正常 Main 實際滑鼠旅程，也未驗無 `mplcursors` 路徑；合成 Matplotlib 使用 DejaVu Sans 缺中文字形，圖上中文呈方框。正式回測／私人 Portfolio、正常 Main 全旅程、其他真 DPI／Light／1920 可用螢幕、固定 EXE、Owner UAT 與完整產品 Gate 均未接受。M1–M129 是切片序號，不是功能數；原始圖留 ignored `output/`，不進版控。

## M130 Matplotlib 備援圖繁中字形

M129 的合成圖出現中文方框後，Sol 分派 Luna /root/m107_portfolio_audit 盤點字型生效範圍並作單一 writer，Luna /root/m108_research_visual_audit 獨立唯讀複核：Qt 啟動字型只註冊到 QFontDatabase，Matplotlib 四種備援圖仍用自己的 DejaVu Sans；這是真實可達的產品缺口，但 M129 合成圖本身不足以證明每次正常 Main 都缺字。ui_qt/widgets/chart_widget.py 現按 Matplotlib 可解析的 Microsoft JhengHei／UI、Noto Sans TC 候選局部設定每張圖的標題、軸、offset、刻度、圖中文字、圖例及買賣點動態 annotation；每輪 ax.clear() 後的共用主題入口重套。缺候選保持原字型、不改全域 rcParams、不散布系統字型；僅同檔與 tests/test_ui_qt_chart_widget_factory.py 變更。Sol 原生首輪發現單一 fname=msjh.ttc 缺 Unicode 負號，改採 Microsoft JhengHei＋DejaVu Sans 的 per-artist 字形後備；原 QA 和 warning 保留，不當最終版。

最終受控 Job output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_e6569394dd2d45c3aa585a779fd60c3a/receipt.json：受改 Python compile0、聚焦 **12 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留或強制清理。正常 Main 用隔離合成保存 CSV 強制 Matplotlib 備援，四圖於 1280×760／1500×900 真 OS DPI216 共 8 張 Main 及 8 張完整 canvas 圖、來源 SHA 不變，最終 output/tasks/baldr-opus-ux-implementation/root/native_m130_evidence/run_c709da6dad0d40e682d6743edeaf8863/result.json 與受控 Job root/single_owned_qa_2d38fe23d7df4374a66549d2344c2b0d/receipt.json exit0；圖表缺字警告設為失敗，Sol 目視中文與負號刻度可讀。另以真 Matplotlib annotation、callback 注入的買賣提示保留白底缺字 before 與深底可讀 after 四圖：root/native_m130_hover_evidence/run_044f24cd741147d9a9a22a14d021cd42/result.json，Job root/single_owned_qa_88e790b222fa413b95b77600374cb16a/receipt.json exit0。首輪單一字型的負號 warning root/single_owned_qa_62b3eba8c3f24fae9744ba5564b121e3/、修後 Main 八圖 root/single_owned_qa_4cb6b9170eb1431898d63b1bc2aa3738/ 及 hover harness 把 before 缺字當 after 門檻的失敗 root/single_owned_qa_c0884a21060e45768cf203160cdf5329/ 均保留如實記錄。

M1–M130 仍是審查、裁決、實作與 QA 切片序號，非功能數。正式 Backtest／私人 Portfolio、實際使用者滑鼠 hover、缺候選字型機器、其他真 DPI／1920／Light、固定 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受；原始 PNG 與收據留 ignored output/，未改金融公式、正式資料或其他排程，未 push／merge／部署。

## M131 備援權益圖真實 hover 與無 mplcursors 退路

Luna `/root/m107_portfolio_audit` 唯一寫入 `ui_qt/widgets/chart_widget.py` 與 `tests/test_ui_qt_chart_widget_factory.py`，Sol 複核。M130 後稽核發現 `HAS_MPLCURSORS=False` 僅記錄 basic tooltip 卻未實作，且有套件路徑把 `sel.target.index` 當交易索引；真實 `mplcursors` 的 target 為座標陣列，首次原生 Qt 事件實際揭出 callback `AttributeError`。修為 `sel.index`，採 `HoverMode.Transient`；無套件時由 `PathCollection.contains` 找買賣點並用同一格式器呈現，重疊每側最多兩筆並明示省略量，游標離開或重繪清舊。沒有更動交易 metadata、圖資料、公式、PIT、來源資格或台股行情色義。最初檢查所用假 Selection 與真實 API 不同，已補真 `mplcursors` 加 Agg MouseEvent 回歸；先前失敗診斷保留，不當通過證據。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_637fd8fd8d374749b42741e04a43c333/receipt.json`：compile 0、圖表聚焦 **17 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留。正常 Main 由 Workbench 進回測保存圖表，隔離合成 CSV 與 SQLite SHA 不變；真 Windows DPI216 在 1280×760（無套件）和 1500×900（有套件）以原生 Qt 畫布滑鼠事件驗買點、賣點、移開清除。結果 `.../root/native_m131_result.json`、四張 PNG 與受控 Job `.../root/single_owned_qa_2719fea440f44d63919cb84a8b76dd8d/receipt.json` exit0；Sol 目視繁中理由、提示深底與負號字形可讀。此事件由程式送入，尚非實體滑鼠；兩路徑未在每個尺寸交叉驗。正式回測與私人 Portfolio、其他真 DPI／Light／1920 可用螢幕、固定新版 EXE、Owner UAT、M73／M75 及完整產品 Gate 保持未接受。審查來源是 Opus 起始、額度用盡後由 Antigravity 接手完成；M1–M131 是切片序號，非功能數。

## M132 Backtest 圖表首屏完整可讀

Luna `/root/m132_layout_audit` 先唯讀定位：1280×760 正常 Main 的 Backtest 結果頁在來源列、歷史列及外層研究脈絡之下放 12×8 吋自然尺寸的 Matplotlib 備援圖，外層捲動保留完整資料，但首屏只見上半圖。Luna 單一 writer 只改 `ui_qt/views/backtest/result_panel.py` 與 `tests/test_ui_qt_backtest_layout.py`：Backtest 實例的四張 fallback 圖採較矮自然尺寸，圖表頁預設收合重複的研究脈絡／補充查找，提供鍵盤可操作的還原按鈕；離頁恢復原查找群組勾選。Sol 首輪原生量測發現 10.8×3.8 仍有 152px canvas 超過 viewport，退回改 10.8×3.2 並收合上方控制；後版又發現來源選擇框縮到 82px，將按鈕移到歷史列並把選擇框保留 200px。run ID、歷史載入、四圖、外層 scroll、Portfolio 共用圖和 Fast 路徑不變，沒有改資料或金融公式。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_f62975b2261143cfa1f96663bee4313a/receipt.json`：compile 0、版面聚焦 **15 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，8 GiB／12 程序 Job 無殘留。標準 offscreen 測試中曾在既有長表捲動測試遭 Chromium GPU context loss 而 Qt abort，收據 `.../root/single_owned_qa_5aee9992c5a343199b47a5921f3fe068/receipt.json`；隔離定位後以測試程序軟體渲染重跑通過，沒有改產品圖表路徑。正常 Windows Main 隔離合成保存 CSV，真 OS DPI216 於 1280×760／1500×900 四圖共 16 張整窗／canvas PNG，加兩張研究脈絡展開圖，來源 SHA 不變；最終 `.../root/native_m132_evidence/run_f5bf4f9fc57347428f2546115a0f17f7/result.json`，受控 Job `.../root/single_owned_qa_f1811fa5232c4709a9c4b85cebf1f20e/receipt.json` exit0。1280 頁內可視區高 483，四圖 canvas 下緣 468，選擇框寬 200；Sol 目視座標、圖例、run 身份、控制鈕與完整圖可讀。正式來源、其他真 DPI／Light／1920 可用螢幕、固定新版 EXE、Owner UAT 與完整產品 Gate 未接受。M1–M132 仍為審查／實作／QA 切片序號，不是功能數。

## M133／M134 成交量尺度與 Fast hover 金融單位

Luna `/root/m133_research_audit` 唯一寫入 `ui_qt/views/stock_research_report_view.py` 與 `tests/test_stock_chart_hover_presentation.py`：原個股 K 線成交量子圖按本段最大原值縮放，但未標量級；現在在價格與量柱之間保留尺度空間，標示「成交量刻度（股）：0 至最高原值」，同步至基本提示與無障礙描述。全零只標 0，缺量沿原 `ohlc`／`close` 模式；原逐日表與 DTO 不變。Luna `/root/m133_fast_audit` 唯一寫入 `ui_qt/widgets/fast_chart_widget.py` 與新 `tests/test_ui_qt_fast_chart_widget.py`：Fast Canvas hover 的策略淨值去除無來源貨幣的 `$`，回撤原百分比值補 `%`，其他序列保留原 yLabel；仍以 `textContent` 輸出。Sol 退回一般序列誤失 yLabel 的首稿並複核修正。兩切片沒有改 payload 數值、金融公式、來源資格或私人資料。

最終受控 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_8248347a5e924e10a93530de53f7fdd9/receipt.json`：受改 Python compile 0、聚焦 **23 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144 source files clean**；8 GiB／12 程序 Job 無殘留。個股圖用 HEAD 原碼與修後同筆合成 OHLCV 作 before／after，在真 Windows OS DPI216 畫出四張元件圖；正常 Main 1280×760／1500×900 另存整窗與圖表，Sol 目視量級清楚且不壓價格軸或量柱。最終 `.../root/native_m133_evidence/run_e08562a1a01b487bb90eaef09ef8e8dd/result.json`、Job `.../root/single_owned_qa_ab4bffd47fbb489a95ab707a38b5ec31/receipt.json` exit0。Fast 真 QWebEngine 畫布以程式送入 `End` 鍵事件，before／after 權益與回撤四圖的 DOM 文字、可見 tooltip 及視覺文字已驗；最終 `.../root/native_m134_evidence/run_23134bfed03f401eb638c55e8b7f7dbb/result.json`、Job `.../root/single_owned_qa_74526531fec6421bb153dda00edf2b2c/receipt.json` exit0。第一次 Fast 畫面工具抓到非本任務視窗，其錯圖目錄已移除；後續一輪只等待 compositor 不足，最終加入可見 DOM 狀態和 compositing 等待後以 widget-only 擷取通過，原失敗收據不作通過證據。

這些畫面限隔離合成資料與本機真 DPI216。Fast 只驗程式化鍵盤事件與本機 WebEngine，正式 GPU／固定 EXE、真滑鼠、正式行情與回測來源、其他 DPI／Light、Owner UAT、自然排程及完整產品 Gate 各自未接受。M1–M134 是審查、裁決、實作與 QA 切片序號，非 134 個獨立功能。審查身份仍是 Opus 啟動、額度用盡後由 Antigravity 接手完成；本輪不修改其他排程，不 push／merge／部署。

## M135／M136 載入回饋與市場條件卡

M135 Luna `/root/m133_fast_audit` 唯一寫入 `ui_qt/widgets/fast_chart_widget.py`、`tests/test_ui_qt_fast_chart_widget.py`。Fast Canvas host 現有可見載入、空資料、文件完成、載入失敗與 renderer 終止狀態；失敗後可重試最新 payload。初始化頁與快速換結果期間只排入最新 payload，數值替代立即更新；新 WebEngine view 以 generation 隔離舊頁的延遲訊號。Sol 退回一版不符合真實進行中 load 的 fake failure 測試，補驗 active load 的失敗與遲到完成訊號。`loadFinished(True)` 只足以顯「圖表文件載入完成」，不宣稱畫布或金融資料成功。沒有改 chart payload 值、回測公式或來源資格。

M136 Luna `/root/m133_research_audit` 唯一寫入 `ui_qt/views/market_regime_view.py`、`tests/test_ui_qt_market_regime_view.py`。市場分類判斷摘要以三列中性卡顯原來源布林條件的符合、未符合、未知及原條件文字；缺項不翻成反證。刷新與錯誤清除舊列，原摘要保留供相容診斷。Sol 比對 M114 已補第三條 `+DI > -DI` 的成果，確認本輪只改善逐項辨識，未新增分數、條件、金融公式或交易資格。

最終受控 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_f711a3ea29204b459d9e989e0138df44/receipt.json` exit0：受改 Python compile0、相關聚焦 **52 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144 source files clean**；8 GiB／12 程序 Job 無殘留。測試程序使用 software rendering 避免已知 offscreen Chromium context loss，不代正式 GPU。M136 隔離合成元件 before／after、正常 Main 1280×760／1500×900 真 Windows DPI216 四圖與來源 SHA 見 `.../root/native_m136_evidence/run_0d1e65c3eaae4bdcae694e0ad0813ad7/result.json`，Job `.../single_owned_qa_ec3dfbcc536f47d9a9be48495b3dfdbb/receipt.json` exit0；Sol 目視三列同屏可讀。M135 真 QWebEngine 正常 Main 在同兩尺寸的權益／回撤圖共八圖、最新 synthetic payload 的 JS 點數與 canvas 尺寸、來源 SHA 不變，見 `.../root/native_m135_evidence/run_e0a32b91f0d5467f8e447629253aedb3/result.json`，Job `.../single_owned_qa_3bcdfd38055841a5bf703266982a7338/receipt.json` 的 child exit0、無殘留；包裝器最後因 PowerShell cp1252 輸出中文 log 發生 UnicodeEncodeError 而自身 exit1，不能把包裝器 exit1 寫成全程通過。M135 1280 的 WebEngine 畫布下緣比頁內可視區低 16px，但保留 35px 捲動；1500 完整可見。Sol 目視主窗圖與圖表可讀。

原生錯誤／renderer 終止及重試以 fake signal 聚焦測試驗證，沒有在正式 GPU 環境故意 crash；正式來源、其他真 DPI／Light／1920 可用螢幕、固定新版 EXE、實體滑鼠、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受。M1–M136 是審查、裁決、實作與 QA 切片序號，非功能數；Opus 開始審查、額度用盡後由 Antigravity 接手完成，Sol 核對後實作。只在本機提交，未 push／merge／部署或改其他排程。

## M137／M138 Fast 畫布確認與可比產業圖卡

M137 Luna `/root/m133_fast_audit` 唯一寫入 `ui_qt/widgets/fast_chart_widget.py`、`tests/test_ui_qt_fast_chart_widget.py`。Sol 核對 M135 的 `loadFinished(True)` 只證明文件載入，要求畫布狀態再經 JS 確認。新頁面以當次 token 與 `pending／ready／error` 狀態標記；只有 `draw()` 返回、CSS 與 bitmap canvas 尺寸皆為正，Python 非同步查詢才顯「畫布繪製完成」。三秒未確認顯明確未確認狀態，JS 例外顯繪製失敗；空資料保持中性。最新 payload、延遲 callback、關閉再開及重試均以 generation／load sequence 隔離。Sol 審查後補要求正尺寸與重開視窗的回歸，已納入測試。沒有改金融資料或圖值。

M138 Luna `/root/m133_research_audit` 唯一寫入 `ui_qt/views/decision_desk_view.py`、`tests/test_ui_qt_decision_desk_view.py`。市場總覽從同一份 `IndustryStrengthSummary.rows` 顯示產業相對基準 5／20 日強弱：同一產業層級及市場範圍內兩期共用零軸與最大絕對 bp 尺度，逐列保留精確 bp、覆蓋、日期、品質與基準；真 0 與 Unknown 分開。選取任一產業後，代表股導覽沿同一 snapshot 的既有研究脈絡，不外推歷史 PIT。Sol 原生審查退回過初版收在進階面板、兩期尺度不同、選列重建，以及內層捲動壓成一行、舊代表股按鈕重影；最終圖卡置於首屏市場摘要之後，內層高度有界，選列保留畫面位置，清舊按鈕即時 hide／disable／unparent，繁中主畫面可讀。沒有新增產業公式、基準資格或來源。

最終受控整合 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_472be127580e439d86a05e2cf1ad7500/receipt.json` exit0：compile0、相關聚焦 **84 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144 source files clean**；8 GiB／12 程序 Job 無殘留或強制清理。測試程序 offscreen 使用 software rendering，不能當成正式 GPU 驗收。首輪 `.../single_owned_qa_b2589f0044294d9b992487f70ed17c4b/receipt.json` 的聚焦 **82 passed／1 failed** 是測試把 PySide6 `currentData()` list 當 tuple；修測試後 M138 定向由 41、42 到最後 42 passed，失敗收據保留。

M137 正常 Main 真 QWebEngine、隔離合成資料、Windows OS DPI216 的 1280×760／1500×900 權益與回撤八圖及 JS ready／正 canvas 尺寸在 `.../root/native_m137_evidence/run_a78e352174ba47478f21d5badf24ca68/result.json`，受控 Job `.../single_owned_qa_6c5f6a355b8349939be0903d2b740081/receipt.json` exit0。另以受控 JS throw 驗 error 文案、數值替代及 retry 恢復 ready，兩圖與結果在 `.../root/native_m137_error_evidence/run_f11ecf73a9c7448882803113ee39b32f/result.json`，Job `.../single_owned_qa_3285177d220041a3994dd314648abe8b/receipt.json` exit0。Sol 目視曲線與錯誤狀態；1280 頁面仍需約 16px 捲動才見整個畫布底端。

M138 正常 Main 真 OS DPI216、同一隔離合成產業 snapshot 的 1280×760／1500×900 圖卡 before／after 五圖與精確數值在 `.../root/native_m138_evidence/run_fb7444ab1d494a72a948cb25172c8573/result.json`，Job `.../single_owned_qa_024e70867e9e492ca070b2cb95a1338e/receipt.json` exit0。Sol 目視兩期、真 0／Unknown、覆蓋及選取非領漲產業後單一代表股按鈕可讀。首兩次 Main fixture 被非同步刷新覆蓋的 harness 失敗，以及兩次版面退回紀錄均保留，未用作最後通過證據。正式市場／回測來源、真 GPU renderer crash、固定新版 EXE、其他真 DPI／1920 可用螢幕、Light 若支援、自然排程、Owner UAT、M73／M75 和完整產品 Gate 仍未接受。M1–M138 是切片序號，非功能數；原始 PNG／receipt 留 ignored `output/`，本輪未改正式或私人資料、其他排程，未 push／merge／部署。

## M139／M140 Fast 首屏與產業深列定位

M139 Luna `/root/m133_fast_audit` 唯一寫入 `ui_qt/views/backtest/result_panel.py`。原 1280×760 正常 Main 的 Fast 權益／回撤畫布下緣在 483px 頁面可視區的 499px，雖可捲 35px 但首屏不完整。Sol 接受只移除 Backtest 圖表外層與四個圖頁的預設邊距，退回一個僅重述實作與既有控制測試的新增測試；原有版面測試與原生幾何更能驗證這項可逆修改。最終畫布仍 300px 高，下緣 482px、捲動上限 0；run ID、歷史載入、狀態、「顯示數值」和研究脈絡控制可讀。Portfolio layout、Fast widget 本體、圖值與金融公式均未改。

M140 Luna `/root/m133_research_audit` 唯一寫入 `ui_qt/views/decision_desk_view.py` 與 `tests/test_ui_qt_decision_desk_view.py`。32 類產業清單在 230px 內捲區不易找到深列；現用同一 `SectorRotationSummary` 的來源 20 日領先／落後名稱，只在唯一對上同份產業列且該列有 20 日超額值時啟用定位，必要時切原層級／市場範圍，仍可任選其他列。延後至 Qt 排版完成後把選中列及同源代表股帶進內外兩層可視區；刷新、換群組或手動改選會作廢舊定位。所選群組兩期皆無超額值時顯精簡 Unknown，保留基準、來源日、品質與群組；部分缺值列及真 0 仍分開顯示。不重算排名、不把跨市場列混排，也不改 DTO、服務、來源資格或 PIT。

最終受控整合 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_aa81b86a0ff64d61912f6a884f98c529/receipt.json` exit0：compile0、相關聚焦 **86 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144 source files clean**；8 GiB／12 程序 Job 無殘留或強制清理。offscreen 測試使用 software rendering，不能代正式 GPU。M139 正常 Main 真 QWebEngine、隔離合成來源、Windows OS DPI216 的 1280×760／1500×900 權益與回撤八圖和精確幾何在 `.../root/native_m139_evidence/run_3ec1043af6ee4ca78069ada06eac86ff/result.json`，Job `.../single_owned_qa_0dbedb036aef4eb2a6fbb6e9c06046be/receipt.json` exit0；Sol 目視完整畫布與來源列。第一次 M139 原生 harness 誤用系統 Python、缺 PySide6，收據 `.../single_owned_qa_b12b7f9b07db43998ef2f60a4186daf0/receipt.json` 保留，不是產品失敗。

M140 正常 Main 真 OS DPI216、同份隔離合成 32 列的 1280×760／1500×900 全缺值群組、來源落後深列與代表股九圖，最終 `.../root/native_m140_evidence/run_b6c9aeb49376444e8d5eb60844e99e58/result.json`，Job `.../single_owned_qa_5f5cf46d5a7f40b8a3be416a55f31067/receipt.json` exit0。最終 1280 外頁可視高 596，選中列 top450／height84、代表股 top544／height44，同屏可見；1500 外頁高736，選中列 top590、代表股 top684，亦完整入畫。Sol 目視缺值空態、兩期 bp 與代表股。原生曾揭露按鈕僅換選列而內捲仍 0（`.../single_owned_qa_8140d64a85bd4809886973a67af76cc3/receipt.json`）；延後內捲後又揭露外頁未帶入代表股（`.../single_owned_qa_722b2009654a487c9bac1b18df0e3662/receipt.json`），兩次退回及修正如實保留，初版圖不作最終視覺證據。

這些證據限隔離合成正常 Main、真 Windows DPI216 與本機 WebEngine；正式市場／回測及私人來源、其他真 DPI／Light／1920 可用螢幕、正式 GPU renderer crash、固定新版 EXE、自然排程、Owner UAT、M73／M75 和完整產品 Gate 未接受。M1–M140 仍是審查、裁決、實作與 QA 切片序號，非獨立功能數；原始收據與 PNG 留 ignored `output/`，沒有 push／merge／部署。

## M141／M142 市況廣度首屏與市場失敗診斷

M141 Luna `/root/m133_research_audit` 唯一寫入 `ui_qt/views/decision_desk_view.py` 與 `tests/test_ui_qt_decision_desk_view.py`。既有市場廣度原家數、品質 badge、紅漲／綠跌／平盤家數比例條、精確家數、來源日與品質原先在預設收合的「完整市場資料」。現在同一 widget 位於「總覽」之後、「市場焦點」之前；仍只在原三個非負整數、正總數、合格品質及不晚於判斷日的來源日期成立時畫條，缺值不補零。載入隱藏舊列，新快照或錯誤重顯原狀態。Sol 正常 Main 首輪退回焦點後位置：1280×760 外頁 viewport596，廣度列 top734／height112，仍不在首屏；修正位置後 top383／height112，1500×900 亦完整可見。不新增廣度比率或交易訊號。

M142 Luna `/root/m133_fast_audit` 唯一寫入 `ui_qt/views/market_regime_view.py` 與 `tests/test_ui_qt_market_regime_view.py`。來源或檢測失敗時主要說明固定為「來源或檢測失敗；本次市場分類未知」，原始多行訊息與 HTML-like token 在預設收合的純文字「技術診斷」逐字保留，可用滑鼠／鍵盤選取；不截掉 worker traceback。失敗與 loading 隱藏空的既有技術指標區；新載入與成功清舊診斷，原三個 bool 條件的符合／未符合／未知、Regime DTO、公式、來源與歷史保存行為均不變。

最終受控 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_2e6615e9dcfb455f860111ab6dbe6afc/receipt.json` exit0：compile0、相關聚焦 **70 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144 source files clean**；8 GiB／12 程序 Job 無殘留或強制清理。正常 Main、隔離合成來源、真 Windows OS DPI216 的 1280×760／1500×900 before／after、失敗收合／展開及成功恢復十圖見 `.../root/native_m141_m142_evidence/run_bf66b3f4086b47ada592e706e8c4ff3f/result.json`，Job `.../root/single_owned_qa_177d260a1b7d463da2fc0a49e471b6ca/receipt.json` exit0；Sol 目視文字、色義、首屏與診斷。M141 首輪 native 失敗 `.../root/single_owned_qa_312d9583806b4f47b503a28c6de2a824/receipt.json` 是實際版面缺口，不當最終通過證據。

證據只涵蓋隔離合成、真 OS DPI216 與本機 Qt；正式市場來源、其他 DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受。M1–M142 是審查、裁決、實作及 QA 切片序號，非功能數；raw receipt／PNG 留 ignored `output/`，未 push／merge／部署或修改其他排程。

## M143／M144 系統入口與 Paper 提示

M143 由 Luna `/root/m133_research_audit` 單一 writer 修改 `ui_qt/main_window_coordinator.py`、`ui_qt/v2_shell.py` 及 shell 測試。Sol 核實原「排程與營運」和「環境與來源診斷」均指向同一 `RuntimeView`，其營運、環境與來源內容仍在；系統子導覽因此只留「資料與更新」、「系統狀態與診斷」、「儲存維護」。舊 `diagnostics` 程式呼叫正規化至 `operations`，舊 runtime workspace callback 亦選同一路由；資料及儲存入口獨立。未改 Runtime reader、排程、資料或金融語義。

M144 由 Luna `/root/m133_fast_audit` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與測試。先前原生 Paper QA 圖顯示橫幅開頭 `🧪` 為缺字框；新橫幅以「Paper 模擬｜不會下單。」純文字開頭，原 Paper／手動帳別、非實盤聲明、虛線樣式及分區路由保留。Sol 拒絕另造 Portfolio 風險總卡：目前 M8 手動帳摘要與 M127 Paper Health 分布分屬不同身份，尚無單一合格 concentration／stop distance／exit DTO，不可混帳或自行推算。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_26076e5bd48043a39196e088bc153f09/receipt.json` exit 0：受改 Python 編譯、相關 focused **115 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；8 GiB／12 程序 Job 無殘留 PID 或強制清理。首兩次聚焦各有 114 passed／1 failed，原因是新測試把 Qt 前一路由已排程刪除的按鈕當成目前導覽，改為檢查子導覽當前 `_buttons` 後通過；保留失敗收據，不當產品缺陷或最終 PASS。

隔離正常 Windows Main 在 1280×760 與 1500×900、真 OS DPI216 的系統頁及 Paper 頁共四張 PNG，Sol 目視只見單一 Runtime 入口、原營運資料及 Paper 橫幅無缺字；舊 route、切回手動帳在程序中斷言。證據 `output/tasks/baldr-opus-ux-implementation/root/native_m143_m144_evidence/run_ed71853ee62e4736937f3d860e12dd3e/result.json`，Job `.../single_owned_qa_e9bb2537daf648249f16c1f0698e8379/receipt.json` exit 0。此 GUI 執行關窗時仍在 stderr 出現既有 Portfolio／Position Health 背景 worker 對已刪除 widget 發訊號的 `RuntimeError`；功能畫面及 route 斷言通過，關閉生命週期驗收**未通過**，列後續修復並不得據此聲稱完整 GUI 驗收。未使用正式／私人資料，未驗其他真 DPI、Light、固定新版 EXE、Owner UAT、自然排程或完整產品 Gate。

## M145／M146 Portfolio 關窗晚到回呼

M143／M144 的隔離 Main 關窗曾在 stderr 出現 `PositionHealthSavedPanel` worker 對已刪 relay 發訊號、`PortfolioView` 刷新 worker 對已刪按鈕寫入的 `RuntimeError`。Luna `/root/m145_saved_panel_shutdown` 只修改 `ui_qt/widgets/position_health_saved_panel.py` 及聚焦測試，使 worker relay 不再以 panel 為 QObject parent；panel 銷毀時其 receiver slot 仍由 Qt 解除連接，native thread finished 的 worker `deleteLater` 保留。Luna `/root/m146_portfolio_shutdown` 只修改 `ui_qt/views/portfolio_view.py` 及聚焦測試，refresh worker 釋放後若已關閉即返回，不觸碰按鈕或啟動 pending generation。Sol 修正註解與條件、加強 late-signal 測試斷言 relay 在 panel C++ 刪除後仍有效；無 Reader、保存、來源、帳本或金融計算變更。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_6ea671fabc944b048f11c63ce6bbe876/receipt.json` exit 0：受改 Python compile、focused **101 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；Job 8 GiB／12 程序上限、無殘留或強制清理。隔離正常 Windows Main 1280×760／1500×900、真 OS DPI216，在 Paper 分區主動觸發 Portfolio 刷新與已保存健康評估候選讀取，再各關窗及排空 deferred delete；`sys.excepthook` 收到 **0** 個 callback exception，兩次關窗成功、Job 無殘留。PNG、JSON `output/tasks/baldr-opus-ux-implementation/root/native_m145_m146_evidence/run_b73b5ebaec1749268d6886555e2e7e29/result.json`；Job `.../single_owned_qa_b664caf401e64aae93505c3cd485ed12/receipt.json` exit 0。這修正已重現的限定關閉路徑，不代表正式／私人帳、其他 DPI／Light、固定新版 EXE、Owner UAT 或完整產品 Gate 通過。

Manual coverage：關窗操作入口、參數、取消語義與既有使用者可見提示均未改，本輪僅處理內部 Qt QObject lifetime；`APPLICATION_MANUAL.md` 不需再新增操作步驟。M143／M144 原失敗與警告收據保留作修復前證據，不改寫成當時通過。

## M147 雙版本題材報酬資料覆蓋條

Luna `/root/m147_theme_gap_audit` 唯一寫入 `ui_qt/views/industry_theme_map_view.py` 與 `tests/test_ui_qt_industry_theme_map_view.py`。Sol 先核對 `ThemeReturnVersionObservation` 的 `row_present`、`returns_coverage`、`member_count` 契約，再審查並修正未知狀態的 bar 範圍、格式及輔助描述清理。每版只以自身原覆蓋整數作中性藍條；`0 / M`、部分／完整覆蓋、無報表列未知及零成員不適用分開。取消、換版、載入與錯誤清舊；原平均報酬、日期、映射、來源 ID 與 manifest SHA 保留。沒有重算金融值、跨版相減、授 PIT 或改來源資格。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_712314439a1445a7b2eeaa3b1b26901b/receipt.json` exit 0：受改 Python compile0、相關 focused **58 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；8 GiB／12 程序 Job 無殘留。隔離正常 Windows Main 以合成比較 snapshot 注入 reader 邊界，在真 OS DPI216 的 1280×760／1500×900 驗 `0 / M`、缺報表列及 `1 / 2` 部分覆蓋，共四張 PNG；取消／失效清舊與 `sys.excepthook` callback exception 0，見 `output/tasks/baldr-opus-ux-implementation/root/native_m147_evidence/run_d7c5c206c44249fbb27accc59fb8bef5/result.json`，Job `.../root/single_owned_qa_3862769690034a13b3c112aa3768578e/receipt.json` exit 0。Sol 目視兩欄精確數值與來源文字可讀。此 native 測試沒有走正式 reader 或正式來源；真 OS 100%／125%、Light、1920 可用工作區、固定新版 EXE、Owner UAT、M73／M75 與完整產品 Gate 未接受。

## M148 每日決策開啟原保存推薦

Luna `/root/m148_research_candidate` 單一 writer 修改 `ui_qt/views/decision_desk_view.py`、`ui_qt/main.py` 及兩份對應測試。Sol 核對 `RecommendationDeskSummary` 原結果 ID／日期／品質，以及 Main 既有精確讀取只在排入指定 ID 後切頁的契約；接受不改 DTO、provider、推薦計算或來源資格的訊號接線。原推薦摘要由警示清單移到總覽的可見來源列，原警示計數不再誤把保存結果當警示。有效原 ID 才顯操作，載入、缺件、失敗清舊；已保存推薦不稱今日新建議或交易指令。Sol 程式審查補回既有總覽狀態樣式、固定摘要純文字；首版原生目視發現按鈕獨占一列，修為摘要同列；第二版缺件畫面仍留不明顯停用按鈕，再修為不顯。最終版 1280 首屏保留市場廣度可見。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_5011d249058647749a167130502e6c8f/receipt.json` exit0：受改 Python compile0、相關 focused **60 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；8 GiB／12 程序 Job 無殘留。隔離正常 Windows Main 使用合成快照與保存讀取 callback 替身，在真 OS DPI216 的 1280×760／1500×900 各驗保存摘要、缺件清舊、精確 ID 跨頁路由；before／after 五張 PNG、callback exception 0，見 `output/tasks/baldr-opus-ux-implementation/root/native_m148_evidence/run_9624a68f6222495890a0dc5fd7088673/result.json`，Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_0118b782ad334ad1a39badbf8a8a004c/receipt.json` exit0。初版及中版測試收據保留作版面修正過程，不作最終版 QA。原保存結果 reader 自身、正式／私人來源、其他 DPI／Light／1920 可用工作區、固定新版 EXE、自然排程、Owner UAT、M73／M75 和完整產品 Gate 未由本輪接受。

## M149 原保存推薦精確讀回與返回

Luna `/root/m149_saved_reader_audit`、`/root/m149_return_flow_audit` 先唯讀定位：M148 只驗 callback 路由，推薦頁原精確讀取仍保留上一次分頁，排入前的具體失敗原因留在尚未切入的推薦頁，且來源頁沒有專用返回。`/root/m149_return_flow_audit` 作單一 writer 修改三個 UI 檔與三份 focused tests；Sol 退回首稿把一般 Workbench 也標成「每日決策來源」的問題，拆成來源專用 wrapper。現行只在指定 ID reader 成功排入後切保存結果分頁並回頂端；失敗仍留每日決策並在原摘要旁以純文字顯示原因。由每日決策成功進入才顯「返回每日決策」，回同一個已掛載的 Decision Desk 且不刷新；一般導覽清來源返回。`get(result_id)`、canonical／legacy 身份核對、取消及失敗保留原結果未改，沒有新增金融計算或授來源資格。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_3d8e48909b4e4aabb7ae398c4f672892/receipt.json` exit0：受改 Python compile0、focused **70 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留。隔離正常 Windows Main 在真 OS DPI216 的 1280×760／1500×900，以合成 canonical verified query 真走 `queries.get(result_id)` 與 identity/readback，先驗排入前設定缺件回饋，再驗精確結果、正確分頁、返回同一摘要及一般進入無來源返回。八張 PNG 與 JSON `output/tasks/baldr-opus-ux-implementation/root/native_m149_evidence/run_3fde4d1135174a908ef8a4448b4e47fe/result.json`，Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_3f58d2dfdbc84be288542c7d9da2dedd/receipt.json` exit0、callback exception0；Sol 目視 1280 失敗訊息、推薦返回操作與 1500 原摘要可見。初輪新測試替身 Qt 初始化錯誤及隱藏初態錯誤已修，失敗收據保留。另試既有 `test_actual_mainwindow_cross_page_decision_journey_round_trip` 時在舊側欄 `button_for_key("market_explore")` 便失敗，尚未進本輪 reader，收據 `.../root/single_owned_qa_582d1b9c5b8b49f7bae73cde95cf7822/receipt.json` 保留為測試入口過時，不列最終 PASS。

本輪 native 用隔離合成 verified payload，不是正式保存檔或自然來源；已載入推薦的候選表在 1280 首屏仍較低，保留後續版面量測。正式 reader／正式或私人資料副本、其他真 OS DPI／Light、1920 可用螢幕、固定新版 EXE、自然排程、Owner UAT、M73／M75 及完整產品 Gate 均未由此接受。M1–M149 是審查、裁決、實作與 QA 切片序號，非獨立功能數。Opus 起始審查，額度用盡後由 Antigravity 接手完成；本輪 Sol 核對後實作，未 push／merge／部署或修改其他排程。

## M150／M151 保存結果首屏與跨頁測試修復

M150 先量測 M149 正常 Main 1280×760 原結果可視區：來源選擇在上方、結果狀態約 y645、候選表首列約 y701，未在同屏。Luna `/root/m149_return_flow_audit` 單一 writer 修改 `ui_qt/views/recommendation_view.py` 與精確讀回測試；Sol 修正初版舊格式回呼缺 generation 及 canonical／legacy 身分守衛。公開精確入口只在已驗證的同一 ID、同一讀取 generation、同一可見保存頁且等待期間未變更捲動時，於結果排版完成後聚焦狀態；錯誤、取消、切頁及使用者先捲動都不搶畫面。保留原單筆 get、來源資格、推薦值、表格及風險說明，不自動選股。

M151 為測試維護：Luna `/root/m149_saved_reader_audit` 單一 writer 將既有正常 Main 跨頁旅程改走現行可見主導覽與 ProductShell 子頁，明選「保存策略研究」來源。Sol 修正舊主導覽斷言與來源選擇名稱；測試完整走過市場／個股／推薦保存／觀察清單／Portfolio／Workbench，未修改產品路由。

最終受控 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_be1cd3d82a164397b5fab971a6e3603a/receipt.json` exit0：compile0、精確保存讀回及緊湊版面 **14 passed**、正常 Main 跨頁旅程 **1 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** files clean；8 GiB／12 程序 Job 無殘留。先前 NameError／測試導覽與來源選擇失敗收據保留，不當最終 PASS。

原生 QA `output/tasks/baldr-opus-ux-implementation/root/native_m150_evidence/run_568b81186dc74f419fb4a82e4a32fe5a/result.json`，受控 Job `.../root/single_owned_qa_e35a8e8cbbf444f2b5f222a3986c2c2b/receipt.json` exit0：正常 Windows Main 在真 OS DPI216 的 1280×760／1500×900，隔離合成 canonical verified query 真走 get(ID)。兩尺寸皆核結果狀態與候選第一列可見、原每日決策返回、一般入口無來源返回；失敗與成功共八 PNG、callback exception0。Sol 目視 1280 首列及來源提示可讀。這只接受原始碼與限定 QA；正式保存來源、其他 DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT、M73／M75 和完整產品 Gate 未接受。M1–M151 是審查／裁決／實作／QA 序號，非功能數；沒有 push、merge、部署或修改其他排程。

## M152／M153 風險提示解釋與研究母體三態圖

Sol 對 M1–M151 及現行程式去重後，採兩個獨立、有原 DTO 的 UX 切片。Luna `/root/m152_decision_gap` 單一 writer 修改 `ui_qt/views/decision_desk_view.py`、`tests/test_ui_qt_decision_desk_view.py`：每日決策進階風險提示原只拼嚴重度、代碼、標題及行動，未顯 DTO 的分類、來源與原因；現以純文字分行顯原理由和建議檢查，三種嚴重度白話顯示、已知來源與分類對應既有中文、原碼保留於輔助描述，超過五筆顯精確省略數。原 quality badge 保留，空 observed 僅表示這份來源未列；missing／degraded／estimated、載入與失敗均不冒充沒有風險。Sol 修降級／估算空態文案，原生退回長內容轉缺件時的高空白；Luna 對該列與徽章設自然高度，Sol 再以受控 Qt 幾何探針確認排版需完成事件輪次，修測試等待。沒有改原 prompt 排序、來源、判斷或建議公式。

Luna `/root/m152_research_gap` 單一 writer 修改 `ui_qt/views/daily_market_cohort_view.py`、新增 `tests/test_ui_qt_daily_market_cohort_view.py`：兩項固定方法保留原符合／不符合／未知整數表，另以同一 typed `DailyMarketCohortMethodCount` 的三態整數及固定母體分母畫橫向三段條；未知使用獨立中性色，原整數與母體數可核。無效或零分母不畫比例，換版、錯誤與清空移除舊圖。Sol 原生退回 DPI216 下精確人數標籤被表格列裁切；Luna 改以當前字型行距、圖條最低高度與儲存格邊距計列高，Sol 補 `sizeHint()` 可能無效的檢查後重驗。沒有改既有方法、投影、分母、PIT 或來源資格。

首輪 focused `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_ffa810cc15cc428ab098e5c2c1773387/receipt.json` 為 **68 passed／1 failed**（降級空態文案預期）；修後 `.../single_owned_qa_c0c7832319ee4e2bb82374b4e1a48ddc/receipt.json` **69 passed**。初輪正常 Main 圖 `.../root/native_m152_m153_evidence/run_e9a75726f0f748e4a42d5a319175aa2d/` 雖腳本 exit0，Sol 目視退回圖例裁切及空態高度，不能作最終視覺接受；幾何測試首輪 `.../single_owned_qa_b7233a9509504e1b8b0c25003b0db314/receipt.json` 為 **69 passed／1 failed**，受控探針 `.../single_owned_qa_f977353c3f994ccb9b0862ba8afcd5d7/receipt.json` 說明長短內容排版在事件輪次後可收縮。修後 focused `.../single_owned_qa_0b7d8964d6cd45e7baecc9f9c4bbea32/receipt.json` **70 passed**。

最終共同 QA `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_06609ab5cf014b0eac9cf222db6c0eb6/receipt.json` exit0：受改 Python compile0、focused **70 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留。正常 Main 真 OS DPI216 的 1280×760／1500×900 六張隔離合成圖與 JSON：`.../root/native_m152_m153_evidence/run_4561fc0e821f4c6a91a7bfdb0d4fe911/result.json`；Job `.../root/single_owned_qa_e0b21e9071c54b9c943d700f1fe2b5b3/receipt.json` exit0。Sol 目視原表與完整三態人數同屏、風險逐筆原因可讀、長提示轉缺件後列收縮且品質徽章保留；隔離 SQLite SHA 不變、callback exception0。

這是原始碼及限定合成／原生 QA，不是正式來源接受。正式市場／私人資料、其他真 OS DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 未接受；M1–M153 是審查、裁決、實作與 QA 序號，非 153 個獨立功能。沒有自動交易、正式資料改寫、其他排程修改、push、merge 或部署。

## M154 研究母體成員固定條件可見判讀

Luna 先做兩個獨立唯讀盤點：推薦候選首屏的 M149 缺口已由 M150 精確保存讀回聚焦處理，Sol 不為湊進度重排既有版面；研究母體頁的成員原條件僅在舊 tooltip 嘗試呈現，實際成員重繪還會取代該 tooltip，選列只切換下鑽按鈕。Sol 核對 `DailyMarketCohortMember.conditions` 已有兩個固定方法的原狀態、相對關係、原因及未知原因，且投影與快照資格既有，選為單一 Qt 呈現切片。

Luna `/root/m152_research_gap` 單一 writer 修改 `ui_qt/views/daily_market_cohort_view.py` 與 `tests/test_ui_qt_daily_market_cohort_view.py`：在成員表旁同屏顯明選股票、行情資料日、MA20／MA60 固定條件原三態、關係、原因與非空未知原因；換列、取消選列、重讀來源或失敗清舊，原三態圖、整數表、成員值及個股下鑽保留。Sol 修 `ui_qt/tab_info_config.py` 的舊「支持、反證」描述，改明確三態與非投資建議。沒有新增讀取、重算均線、投資分數、來源資格、PIT 或正式資料寫入。

最終 root-owned 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_f0aa094f105945bb948b0d8c84fd2870/receipt.json` exit0：受改 Python compile0、cohort／投影／Main bridge focused **18 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；無殘留。正常 Main 真 OS DPI216 的 1280×760／1500×900 以隔離合成已驗證快照驗未選、選未知、換另一檔及清除共八 PNG：`output/tasks/baldr-opus-ux-implementation/root/native_m154_evidence/run_d4eecc7bbb7a44839c494de855e419ed/result.json`，Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_3429f1c24b1144068bdd812e2f0a3dc4/receipt.json` exit0。Sol 目視兩尺寸的成員首列、側欄原狀態與原原因同屏可讀；隔離 SQLite SHA 不變、callback exception0。

這是原始碼與隔離合成／原生 QA。正式市場來源、其他真 OS DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 未接受；M1–M154 是審查、裁決、實作與 QA 序號，非 154 個獨立功能。沒有 push、merge、部署或修改其他排程。

## M155 少量保存推薦的表格與來源區

Sol 在 M1–M154 後再盤點原審查與現行程式，未找到可安全新增且有資料契約的市場／題材／個股／回測圖；M73 控制作用範圍及 M75 有向供應鏈、跨期強弱仍須產品與逐邊來源時鐘契約。M150 的正常 Main 證據另顯示兩筆保存候選仍佔五列高，讓來源與理由區偏低。Luna `/root/m152_decision_gap` 單一 writer 修改 `ui_qt/views/recommendation_view.py`、`tests/test_ui_qt_recommendation_exact_saved_entry.py`、`tests/test_ui_qt_saved_recommendation_compact_layout.py`：精確 canonical／唯讀舊格式讀回 1–4 列時按實際列數配置表格，0 列保留一列空框，五列以上及新執行仍維持五列最低高度。只調 Qt 版面，不改候選、分數、原結果、日期、身份核對、來源資格或金融計算。

Sol 首輪原生 `root/native_m155_evidence/run_43091ef3df6844a58e97f2906d4836c9/result.json` 發現只降低 `minimumHeight` 時，QSplitter 實際仍配置約 201px，來源只略上移；未接受為視覺完成。受控探針 `root/native_m155_evidence/run_58a380268f834ba2bbe2ff3d6df50c71/result.json` 確認分割器配置可令表格約 108px，Luna 補實際 `setSizes`，並以測試斷言實際 splitter size。最終正常 Windows Main、真 OS DPI216、隔離合成的 1280×760／1500×900 canonical 2／0 列與舊格式 1 列共六 PNG、callback exception0：`output/tasks/baldr-opus-ux-implementation/root/native_m155_evidence/run_3e45737d299542739e949c9ea536c231/result.json`；Job `.../root/single_owned_qa_4c6ba068ffdd4807a210450b50791151/receipt.json` exit0、無殘留。Sol 目視 1280 兩列與來源／理由同屏；兩列高度由原五列目標 186px 收至實際 116px（1500 為 112px），空表明確標沒有推薦列。

最終共同 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_93d1b6b2d580466b88c7f13753157ca4/receipt.json` exit0：受改 Python compile0、相關 focused **45 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，無殘留或強制清理。這些是隔離合成及原始碼 QA；正式保存來源、其他真 OS DPI／Light／1920 可用工作區、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 未接受。M1–M155 是審查、裁決、實作與 QA 切片序號，不是 155 個獨立功能；原始 PNG／收據留 ignored `output/`，本機提交不 push、merge 或部署。

## 排程啟動至 M162 的盤點

| 範圍 | 已完成的工程與驗證 | 尚未接受的界線 |
| --- | --- | --- |
| 審查與裁決 | Opus 起始審查、額度耗盡後 Antigravity 續作六份主要報告及設計附件；Sol 核實來源、程式與架構，逐項去重。M1–M162 包含唯讀裁決、測試及實作，並非 162 個功能。 | 審查意見不自動授來源／金融契約。 |
| P0 金融辨識 | 台股方向色、原數值／日期／單位、真零與未知、狀態清舊、可見風險提示及首屏摘要；保存推薦按原 ID 讀回、返回與少量列版面；常駐建置身分短版化；選中持倉及回測 Sharpe 短顯與完整原值可核；Workbench Advice 原警告、日期與選列理由可見。 | 正式保存／市場來源與 Owner UAT 未驗。 |
| P1 產業題材 | 原資料範圍內的題材格、成交額與覆蓋圖、九指標、同版成員／鄰域、搜尋、雙版本原值、具名母體三態與成員條件側欄，保留精確下鑽。 | 多期間報酬、逐邊有向關係需合格來源、時鐘及用途契約。 |
| P2 全站研究 | 市場、個股、推薦、Watchlist／Portfolio、Backtest、Evidence／Runtime 的圖卡與明細層級、長表、載入／失敗、導航與回訪；持倉毛損益正／負／零／未知家數分布；修關窗晚到回呼及備援圖互動／字形；共用狀態色與市場方向色分離。 | 正式或私人資料、安全唯讀副本、其他真 DPI／Light／1920、固定新版 EXE、自然排程與完整 Gate 未接受。 |
| P3 產業鏈 | 已有同版重疊、分類與成員探索；Sol 拒絕把共現當有向供應鏈或把資料覆蓋當跨期強弱。 | M75 逐邊證據與跨期 PIT 用途仍缺；M73 決策品質控制作用範圍仍需產品裁決。 |

各切片均由 Luna 依單一 writer 邊界實作或唯讀盤點，Sol 複核、退回必要修正並以 root-owned 受控 Job 做聚焦、共同回歸及隔離原生畫面；原失敗與探針收據保留。此盤點只收束本機原始碼階段，不代表正式產品驗收或可交易資格。

## M156 全域建置身分資訊層級

兩位 Luna 先唯讀對照原 Opus→Antigravity 審查與 M1–M155：產業／題材、個股、推薦、Portfolio、Backtest、Evidence／Runtime 沒有新資料契約下可安全新增且不重複的高價值圖。Sol 在 M155 正常 Main 原生畫面另確認原審查 P0-1 的未完範圍：開發版常駐狀態列與視窗標題仍顯原始 commit 及 dirty，擠壓研究上下文。已驗 release 原本已有短版；此輪只處理 development，並保留未核實版本的明確警示。

Luna `/root/m152_decision_gap` 為唯一 writer 修改 `ui_qt/main.py`、`tests/test_ui_qt_partial_data_startup.py`：已核實 development 在正常標題與常駐列顯日期及「開發版」，不顯原始雜湊／dirty；release 保持日期及「發布版」；未核實來源不偽裝為已核實。Sol 再將未核實的可見工程文字改為「未核實版本｜請檢查程式來源」，重跑驗證。完整版本、commit、dirty、lock SHA 和設定／資料／輸出路徑仍留原 tooltip，可在需要核對時取得；`BuildIdentity` 模型、建置偵測、來源資格、金融值與資料均未改。這是顯示層整理，不授正式發布或資料資格。

初版 root-owned 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_432329567cd54b2f8d14bb6503f1abfe/receipt.json` 通過，Sol 原生目視再縮短未核實警示；最終共同 Job `.../root/single_owned_qa_069d44f9b33a46e4b1470e780e2e95da/receipt.json` exit0：Python compile0、focused **26 passed**（開發版 dirty／clean、release、unverified 及 BuildIdentity）、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean，無殘留或強制清理。最終正常 Windows Main、真 OS DPI216 的 1280×760／1500×900，三種渠道共六張 PNG、callback exception0：`output/tasks/baldr-opus-ux-implementation/root/native_m156_evidence/run_d3592d6b5ef44cb7ae444136fdc32c1d/result.json`；Job `.../root/single_owned_qa_bf4a64128c514a918b53b0711d786572/receipt.json` exit0。Sol 目視開發版狀態列不再佔用 hash／dirty 寬度，未核實版本警示仍可辨。

固定舊 EXE 不含此變更；正式資料、其他真 OS DPI／Light／1920 可用工作區、自然排程、Owner UAT、M73／M75 及完整產品 Gate 未接受。M1–M156 是審查、裁決、實作與 QA 切片序號，不是 156 個獨立功能；本輪未讀寫正式／私人資料，不 push、merge、部署或修改其他排程。

## M157 Portfolio 選中持倉金額顯示

Sol 續核原 Opus→Antigravity P0 缺口：候選池「清空候選池」已有 Yes／No 不可復原確認及收藏來源身分守衛，現行缺新誤觸證據，不重做。Portfolio 選中持倉摘要則可由原程式與畫面確認長 Decimal 直接顯示，平均成本、現價和毛損益會佔用首屏。Luna `/root/m152_research_gap` 單一 writer 修改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`；Sol 複核只改展示：三項 TWD 金額顯兩位小數，捨入標「約」，完整原值保留具名 tooltip／無障礙描述，極小非零仍顯原值；真零、缺件與非法值各按原語義，取消選列清舊提示。原 quantity、日期、來源、Health 身分、持倉 DTO、金融計算與正式資料均未變。

Root-owned 8 GiB／12 程序 Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_f4e41d93507047be9907e5ceb8a55b9f/receipt.json` exit0：受改 Python compile0、Portfolio focused **100 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；無殘留或強制清理。真 Windows OS DPI216 的 1280×760／1500×900 隔離合成 Portfolio 選列兩張 PNG 與 JSON：`output/tasks/baldr-opus-ux-implementation/root/native_m157_evidence/run_2c13cadb2cf049fca7d662145af21072/result.json`，Job `.../root/single_owned_qa_3a625357eebf43719e4bfac2dab1cbfc/receipt.json` exit0。Sol 目視摘要、表列、資料日與來源同屏，長原值不擠佔首層；tooltip／無障礙原值、取消選列清舊與 callback exception0 由腳本核對。

這是原始碼與隔離合成／原生 QA，不是正式／私人資料、其他真 DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT 或完整產品 Gate 接受。M73 控制作用範圍及 M75 逐邊有向供應鏈、跨期強弱的來源與時鐘契約仍待前置，不用合成畫面推金融資格。M1–M157 為審查、裁決、實作及 QA 序號，並非 157 個獨立功能；沒有自動交易、正式資料改寫、修改其他排程、push、merge 或部署。

## M158 Backtest 原報告基準 Sharpe 判讀

Luna `/root/m149_saved_reader_audit` 唯一 writer 修改 `ui_qt/views/backtest/analyst_diagnostics_widget.py` 與 `tests/test_ui_qt_research_lab_mode_driven_ui.py`。Sol 核對原 Opus→Antigravity P0 數值辨識缺口，接受只在原報告基準比較的 Sharpe 三格做呈現精度：有限值顯兩位，有捨入標「約」；極小非零用保留符號的科學記號，真零 `0.00`，無效或缺件顯未知。每格 tooltip 與無障礙描述保留具名原值；缺 delta 的原 benchmark reason 不被覆蓋。Sol 另將原英文群組／欄名改為中文，bp 列及原 DTO、報告來源、金融公式均未改。

最終受控 QA 與 M159 合跑，收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_67be968423bf4fb8a666e1f5fe589eca/receipt.json`：編譯 0、兩頁 focused **131 passed**、Workbench **85 passed**、validator **25 passed／0 failed／4 skipped**、mypy **1,144** source files clean；8 GiB／12 程序 Job 無殘留。真 Windows OS DPI216 的 1280×760／1500×900 隔離合成 Backtest 元件兩圖：`output/tasks/baldr-opus-ux-implementation/root/native_m158_evidence/run_02c48293c50e42b19ef77c4cfcc1dab1/result.json`，Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_16480e776eb5472083835ec6822ac91a/receipt.json` exit0、callback exception0。Sol 目視中文基準列與 Sharpe 可讀。正式回測、其他 DPI／Light／1920、固定 EXE、Owner UAT 與完整產品 Gate 未接受。

## M159 Portfolio 未實現毛損益家數分布

Luna `/root/m152_research_gap` 唯一 writer 修改 `ui_qt/views/portfolio_view.py` 與 `tests/test_ui_qt_portfolio_view.py`。由同一 `PortfolioDTO` 的活躍 `PositionDTO` 等權計數，只有原 `current`、有效 ISO 報價日、有限正現價與有限原未實現毛損益同時成立才列正、負或真零；其餘列未知。台股正值紅、負值綠、零與未知中性，圖條只表示家數占比，不加總金額、不代表資金權重、報酬或風險；0 檔顯精確 0 而不畫比例。載入、失敗、取消清舊；原表與選列上下文保留，沒有重估持倉、改報價來源或帳本。

Sol 原生首版在 1280×760、真 OS DPI216 量到「手動記錄交易」底部 823px，超過 760px 首屏；失敗收據 `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_0d7c91ac83e84cdc90b060a6c3c176ab/receipt.json` 保留，不當通過。Sol 退回要求把圖卡移到整個持倉面板與操作列之後，Luna 修版面及順序測試。最終 1280 同按鈕底部 731px、首列可見，圖卡向下捲可讀；1500 的正／負／零／未知各一檔可讀。四張真 Windows DPI216 隔離合成 PNG 與精確計數／幾何在 `output/tasks/baldr-opus-ux-implementation/root/native_m159_evidence/run_60f239230b9d4220b7cdaadd15d8d375/result.json`，Job `output/tasks/baldr-opus-ux-implementation/root/single_owned_qa_ebdfd30f6df74ef783eba9b3b21d5b70/receipt.json` exit0、callback exception0；最終共同 QA 同 M158。正式／私人帳、其他 DPI／Light／1920、固定 EXE、Owner UAT、自然排程及產品 Gate 未接受。M1–M159 是含審查與 QA 的切片序號，並非功能數。

## M160 Workbench Advice 判讀層級

兩位 Luna 先唯讀盤點：市場／產業／題材已有同源摘要、漲跌格、成交額、分類與下鑽，新增跨期或有向關係仍欠 M75 來源／時鐘契約；Workbench Advice 已有 typed `AdviceDashboardDTO` 的持有期間、進場論點、失效條件、理由與風險，卻藏在長明細，屬可立即完成的資訊層級缺口。Sol 選此切片，指定 Luna `/root/m160_workbench_advice` 唯一 writer，只改 `ui_qt/views/workbench_view.py`、`ui_qt/models/workbench_table_models.py` 與兩個聚焦測試；不改 Advice producer、策略、資格、公式或交易路徑。

正式 Advice、Professional 研究候選及配置先列模式、決策／資料日、列數與原警告；已知動作／品質／可成交性在顯示層轉中文，原碼留 tooltip／無障礙，未知原樣。選列卡顯原理由／論點、適用期間、風險、失效條件，完整長文仍在共用證據明細；空表收起，有列按表頭加最多四列限制可見高度並保留表內捲動。載入／失敗清除舊卡、警告及列，不將缺件當 0 或把 Professional 升成正式 Advice。

Sol 先退回表格 role 覆蓋基類、空態誤把原警告改寫與長卡無界的版本；Luna 修後聚焦通過。首輪原生探針 `root/native_m160_evidence/run_46fff7df352e44a386f0de8ad5ea9635/result.json` exit0，但三表留白、選列卡被推到下方且配置表顯英文原碼，Sol 目視退回；初次 native harness 未展開進階區的 exit1 亦保留為 harness 失敗，不當產品證據。修版在真 Windows OS DPI216 的 1280×760／1500×900 拍摘要、選列與長警告六圖：`output/tasks/baldr-opus-ux-implementation/root/native_m160_evidence/run_0ac41957c8974a9dae9cc3c914ff1245/result.json`，受控 Job `root/single_owned_qa_74ae18d81dd44be99cc70b7fc2a156cc/receipt.json` exit0、callback0；Sol 目視兩表與選列卡可在同段捲動區判讀，長警告保留原文且可續捲。

最終受控整合 `root/single_owned_qa_8a5554e110514109b28dbf9ac1d5b02b/receipt.json` exit0：compile0、Advice contract **6 passed**、Workbench **85 passed**、更新頁 validator **25 passed／0 failed／4 skipped**、mypy **1,144** 個來源檔無問題；8 GiB／12 程序 Job 無殘留。先前誤用系統 Python 的 `root/single_owned_qa_ee658b95ba6243c7ad0879d0af040ca3/receipt.json` exit1（缺 PySide6／mypy）保留，沒有冒充程式失敗或通過。實際正式 Advice／私人配置、其他 OS DPI／Light／1920、固定新版 EXE、自然排程、Owner UAT、M73／M75 與完整產品 Gate 均未接受；M1–M160 是切片序號，不是功能數。

## M161 Main 外殼 Advice 整合驗證

兩位 Luna 唯讀對照 M1–M160 後，市場、產業、題材、Portfolio、Backtest、Evidence／Runtime、Watchlist 及推薦頁，沒有可由現成 typed DTO 安全新增、又不重複的高價值圖卡；Sol 不為湊進度重畫。另發現 M160 僅有獨立 Workbench View 的原生畫面，未核 Main 導覽外殼及扣除側欄後的可視範圍。由 Luna 提出正常 Main 沙箱驗證路由，root 實作 ignored QA harness，僅用 tests/test_workbench_advice_contract.py 的合成 DTO；Main 本身沿空資料根啟動，等待 async worker 閒置再注入，沒有接觸正式／私人資料。

真 Windows OS DPI216 的 1280×760／1500×900 正常 Main 各拍摘要、選列、長警告六圖：output/tasks/baldr-opus-ux-implementation/root/native_m161_main_advice_evidence/run_0ada6fdd00614a8d8169c964c2100763/result.json；受控 Job root/single_owned_qa_7dcaba44f68a43ec960524226349c3d6/receipt.json exit0、callback0、沙箱 DB SHA 未變、worker 關閉後無殘留。Sol 目視主導覽、表格、判讀卡與長警告在兩尺寸可讀。首版 harness 字串換行語法錯誤的 exit1 收據 root/single_owned_qa_f4d247298d124819a527c1b16c6bc976/receipt.json 保留，不算產品失敗或通過。這是正常 Main 組裝＋合成 DTO 的旅程，不證明自然 Advice producer、正式來源／PIT 或產品 Gate。

## M162 共用狀態色與市場方向色隔離

Luna /root/m160_workbench_advice 單一 writer 只改 ui_qt/theme/tokens.py、ui_qt/theme/qss.py、ui_qt/widgets/theme_widgets.py 與 tests/test_ui_qt_theme.py。原 success=#22c55e 與台股 market_down 同色、原 danger 與 market_up 同紅族，易把品質／作業狀態看成市場漲跌。新增 status_success teal #2dd4bf、status_error orchid #e879f9、status_warning amber #f6b44b、status_info blue #77aef5；只套用 QSS statusTone、StatusBadge 與 SemanticChip。observed／manual_observed 用資訊藍，避免暗示已正式接受；estimated／degraded 用警告色，missing／blocked 用錯誤色，unknown／off 中性。原文字、market_*、舊相容 token、行情方向判斷、金融值與資格不動；未引入 US_INTL／Light 或完整 Delegate Suite。Sol 複核後要求 chip 的成功／錯誤底色也離開舊綠／紅底，Luna 修版。

最終受控 root/single_owned_qa_df617b77848c46a2820d838eae8128b4/receipt.json exit0：compile0、主題／方向／Decimal 聚焦 20 passed、Workbench 85 passed、validator 25 passed／0 failed／4 skipped、mypy 1,144 檔 clean，8 GiB／12 程序 Job 無殘留。真 Windows DPI216 的 1280×760／1500×900 狀態徽章、chip、QSS 與紅漲綠跌對照兩圖：root/native_m162_status_palette_evidence/run_a5ca22b7665049cb9d53135a89a03e20/result.json；Job root/single_owned_qa_01a8b6b960ae415c82841f61d03b78d2/receipt.json exit0、callback0，Sol 目視狀態與行情色可區辨。這是共用元件隔離樣本；正式頁面全路徑、其他真 OS DPI、Light／1920、固定新版 EXE、Owner UAT 及完整 Gate 未接受。M1–M162 是審查、QA 與實作切片序號，不是功能數。

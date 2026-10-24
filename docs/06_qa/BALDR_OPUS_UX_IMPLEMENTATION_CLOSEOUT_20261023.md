# Baldr UI／UX 原始碼實作收尾（2026-10-23）

本頁後續已更新至 M107；下方早期階段敘述依當時範圍保留，最新切片與收據見文末。

本頁記錄 `baldr-opus-ux-implementation` 從排程觸發、M88 初次收尾至 M107 後繼切片的**原始碼工程交接**。基線提交為 `97305c6a500798bcda27eee6a5fe9a07ef15b15f`。具名逐項裁決、原始失敗、測試收據與截圖保留在本機 `output/tasks/baldr-opus-ux-implementation/` 的 `IMPLEMENTATION_MATRIX.md`、`SOL_REVIEW.md`、`QA_RESULTS.md` 與 `NEXT_ACTIONS.md`；`output/` 依 Git 排除規則不進版控。本頁提供可隨原始碼提交查閱的範圍與證據索引，不取代各原件。

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

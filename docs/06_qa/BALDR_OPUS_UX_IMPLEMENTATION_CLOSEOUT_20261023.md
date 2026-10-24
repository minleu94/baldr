# Baldr UI／UX 原始碼實作收尾（2026-10-23）

本頁記錄 `baldr-opus-ux-implementation` 從排程觸發至 M88 的**原始碼工程交接**。基線提交為 `97305c6a500798bcda27eee6a5fe9a07ef15b15f`。具名逐項裁決、原始失敗、測試收據與截圖保留在本機 `output/tasks/baldr-opus-ux-implementation/` 的 `IMPLEMENTATION_MATRIX.md`、`SOL_REVIEW.md`、`QA_RESULTS.md` 與 `NEXT_ACTIONS.md`；`output/` 依 Git 排除規則不進版控。本頁提供可隨原始碼提交查閱的範圍與證據索引，不取代各原件。

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

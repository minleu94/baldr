# 個股營收與籌碼視覺整合

狀態：`RESEARCH_VISUAL_UI_VERIFIED_WITH_LIMITS`。本輪承接 `d5bdddfd`，保留已完成 Track A 布局；只新增已載入報告的視覺投影，不代表資料恢復、金融資格或固定 EXE 接受。

## 範圍與完成條件

Root 負責規劃、DTO 展示投影、研究頁接線與驗收；依使用者授權，Luna 獨立完成原值圖卡元件與候選測試，另做唯讀語意複核。Root 採納其三項重要意見：信用流量／餘額不同軸、基本面分市場、單點不畫滿長正規化橫條。Root 另修中性色、缺件與建圖失敗降級；不是獨立完整產品接受。

| 面向 | 實際行為 |
|---|---|
| 既有 UI 修改 | 首頁、題材雙端、選股證據比較及策略結果沿現行 Track A，不重寫已驗證動線；先前證據仍依原 QA 範圍判讀。 |
| 基本面／營收 | 已核期間基礎、已知單位的原觀測依市場、來源版本、指標與基礎分組；缺月不補、缺值不當零；重複期間不擅選修訂。月營收圖優先，原表保持。 |
| 財報比較 | 直接使用已綁定 DTO 當期與前期，不重算同比或混合百分比／百分點。 |
| 法人、信用、集保 | 三個已知法人淨額可同圖；其他指標各自值卡，不把買進與餘額混尺度。級距用原比例基點，1–15級與調整／合計分開。 |
| 分點 | 依同日、來源與交易類型列原順序前12筆及原分母；不累計、不推連買，原表保留。 |
| 可讀性 | 寬窄窗重排，長列表垂直捲動；中性色不代表利多／利空；單點純值卡，日期、可得時間與品質保留。前四組直接呈現，其餘明選展開。 |
| 降級與回訪 | 繪圖初始化失敗保留原表；切股清舊圖；只讀原報告，不另查最新資料。 |

## 已執行證據

本機原件根：`output/tasks/v2-research-visualization-20261022/root/`。所有 Python 檢查由 Root 使用共享鎖、8 GiB committed memory／12 process Job、kill-on-close、啟動前8 GiB可用RAM規則序列執行。

- `targeted05.txt`：82 PASS，包含投影分組、原值、零／缺值、單點、窄窗、級距及報告切換／失敗降級，並涵蓋既有個股報告與V2布局。
- `visual_final_update_regression.txt`：Workbench85 PASS；`visual_final_update_validator.txt`：25 PASS／0 FAIL／4 SKIP。
- `visual_final_mypy.txt`：1135檔通過，兩個既有annotation-unchecked提示保持；`visual_final_compile.txt`：本次Python檔編譯通過。
- 最終程式驗證 Job：`single_owned_qa_5b88d5f213c44173b7d6ba98b07d4581`，exit0、自然排空、handles關閉及鎖釋放。
- 早期82項檢查曾為1 FAIL／81 PASS，因新測試未提供比較所需的當期原件而被既有DTO守衛拒絕；補齊測試原件後通過，未放寬產品守衛。早期渲染檢查器曾呼叫不存在API，原失敗保持。
- 初版100%研究View真Qt渲染六圖已檢視，發現單點正規化誤導及空白過大後修正；因此初版圖片不作最終視覺接受。最終矩陣第一次因可用RAM3.2 GiB低於8 GiB，未啟動子程序、exit125，原收據 `single_owned_qa_f25f9e0b1caf421a8821a1f1eff24d68` 保留，沒有放寬門檻或清除他人程序。
- 記憶體恢復後，`single_owned_qa_a3cbe61330fb471a8cc298149b845672` 在原上限內完成125%／150%、1280×760／900×760／1500×900的兩章節共12張真Qt研究View渲染；邏輯視窗尺寸與要求一致，exit0並自然排空。圖片與收據在 `render_final1.25`／`render_final1.5`。Root已檢視125%營收1280及150%籌碼900實圖，圖卡、原值及原表可讀。這是明示QA示意DTO的保存報告投影，不是真市場來源接受、完整Main或Native旅程重驗。

## 邊界

不修改 application DTO、金融公式、來源資格、正式資料、Quick／Freshness／Evidence 或排程。現在資料不完整或期間／單位未核時，仍可能只有原表及缺件提示；圖卡工程不能替代 P0 或歷史資料取得。本輪不執行 Native、Owner UAT、EXE build、發布或 push。開工時 Release Closeout 為他人空檔變更，本輪未觸碰；交付檢查時它已恢復 HEAD 內容，不納入本輪。

本輪新增7個文件連結及 scoped 文件／task 檢查通過；全庫檢查仍有既存 Junction 越界引用，不能宣稱全庫文件通過，實際數量與原件依本 task 的 `evidence/document_global_check.json` 判讀。

規劃見[實作計畫](../superpowers/plans/BALDR_RESEARCH_VISUALIZATION_20261022.md)，操作見[手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#個股營收與籌碼圖卡)。現有資料若不足以形成月份序列、單位仍未核，畫面會保留缺件；這類資料前置缺口仍屬P0及各資料線，本輪不補造趨勢。

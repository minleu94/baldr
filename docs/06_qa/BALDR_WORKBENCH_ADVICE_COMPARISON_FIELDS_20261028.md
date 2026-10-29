# Workbench Advice 逐股比較資訊

## 範圍

修復 Advice 卡片缺少保存推薦逐股比較資料、共用警告重複出現在卡片風險位置，以及卡片首屏看不到保存逐股支持／反證與資料日的問題。本切片只調整 Advice DTO、Composer、Workbench model/view、focused tests 和相關文件；未修改 Advice eligibility、Gate、PIT、策略計算、交易規則或資料來源。

## 資料語意與傳遞

保存的 Recommendation 已包含 `total_score`、`score_percentile_bp`、`eligible_universe_size`、`industry`、`close_price`、`price_change`；保存列亦提供 eligible-universe 日期。Composer 此前把這些欄位留在內部保存列，未投影至 `RecommendationAdviceDTO`。目前改為同筆列唯讀傳遞，缺值維持 `None`，不計算新分數、不推導信心或勝率。

`score_percentile_bp` 是 eligible universe 中分數小於或等於該列分數之比例，以 basis points 保存；方向是分數較高通常有較高百分位。卡片用中性的「規則分數百分位」，並列 eligible universe 日期與母體大小，不翻成「前 X%」。分數、收盤價及漲跌幅沿用來源數值文字，避免浮點重算或改變保存精度。

新的 Advice DTO 欄位均為 optional；舊 JSON 讀取時預設缺值，新 DTO 序列化會包含新欄位。Recommendation 資料身份和 Advice 的來源綁定契約未改動。

## 呈現

- Advice 區塊集中顯示來源 warnings，並將多筆 Advice 重複出現的原始資格／限制訊息集中顯示一次。每列 DTO 的原始限制仍保留，展開細節與原始來源證據仍可讀。
- 卡片提供規則分數、規則分數百分位及母體、產業、收盤價、漲跌幅；逐股支持與限制沿用列上的理由，並展示保存來源逐股證據摘要。
- 分數標成規則分數，不顯示為 AI 信心或勝率。無逐股風險時顯示「未提供額外逐股風險資料」，並明示不能據此推定沒有風險。
- 資料日期及品質狀態顯示於卡片；空缺欄位明示未提供或未知。

## 驗證

- `py_compile`：7 個變更 Python 檔通過。
- Advice Composer、Workbench Advice contract、Workbench view、Workbench source service、Recommendation execution codec：139 passed。
- Workbench Update UI 回歸：97 passed。
- `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped。
- 4 個變更模組 targeted mypy：無錯誤。
- Repo-wide mypy 未通過：未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有 line-continuation syntax error。
- 附加執行的 `tests/test_recommendation_execution_use_case.py` 有兩項範圍外環境／既有流程失敗：delisting 測試記錄兩次 history preflight 呼叫，且預設 FA_Data log 寫入權限遭拒；receipt binding 測試在 Windows `os.link` 建立暫存 hardlink 時收到 WinError 5。Recommendation codec 與保存來源 service focused tests 通過；上述失敗不在本切片改動路徑，未宣稱其端到端保存／讀回流程通過。
- 未執行原生 GUI smoke 或 Owner UAT；offscreen UI tests 不代表視覺驗收完成。

## 尚未能顯示的資料

若保存 Recommendation 的同筆列沒有對應值，Advice 只能顯示「未提供」。目前無逐股衍生風險欄位可投影，因此以中性缺值文案呈現；本切片沒有從 `decision_desk_snapshots.risk_prompt_json` join 風險資料。Eligible-universe 日期也只沿用保存的來源日期，不以 Advice 顯示日期代填。

## 2026-10-28 圖卡視覺呈現增量

依圖卡檢視將比較資訊拆為規則分數、百分位母體與產業／行情三組，使用較清晰的字級與層級；規則分數旁明示「排序參考・非勝率」，避免被當成信心。信心缺值改為警示樣式並說明來源未提供。理由與限制膠囊提高對比、加長摘要可見字數，並提示需展開卡片才能讀完整判讀；原比較字串保留在輔助說明中供輔助技術讀取。

本次圖卡聚焦測試：4 passed、12 deselected；必要 Workbench Update UI 回歸 98 passed；Update validator 25 passed、0 failed、4 skipped；本次修改模組 targeted mypy 無錯誤，3 個變更 Python 檔 `py_compile` 通過。Repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到既有 line-continuation syntax error，無法完成全域檢查。Scoped document-control link check 因手冊內兩個既有 `output/trial/.../TRIAL_GUIDE.md` 外部引用在受限工作區回傳 WinError 5（output 路徑拒絕存取）而未能通過，不能據此判定其目標內容。Offscreen 截圖用環境缺少中文字型，畫面文字呈方框，故只確認布局與元件分區，不以該截圖宣稱中文視覺驗收；原生 GUI／Owner UAT 未執行。未修改 Advice 人工決定的來源身分串接。

## 2026-10-28 第二輪：閱讀寬度、展開高度與響應性

使用者回報一般視窗三欄令理由和行情摘要過窄，展開判讀受固定高度截斷，卡片打開也會等待人工狀態讀取。一般桌面寬度改用兩欄（寬度達 1700 logical px 才三欄），展開卡仍跨滿整列；理由摘要上限增至 96 字，完整判讀 QLabel 移除 160 px 高度限制並由工作台捲動查看。展開時的同筆 journal 唯讀讀取改由 TaskWorker 背景執行，UI thread 負責核對完成回覆；讀取中暫停決定按鈕，避免與 readback 競態，完成或失敗後可重試。來源身份欄位與 exact identity 判斷未變。

驗證：Advice contract suite 16 passed；必要 Workbench Update UI 98 passed；Update validator 25 passed、0 failed、4 skipped；targeted mypy 2 模組無錯誤；py_compile 3 檔通過。Offscreen 合成卡截圖確認 1540 px 寬度為兩欄、展開卡寬 1445 px、判讀框最大高度不再固定（16777215）；該環境中文仍因缺少字型呈方框，不作原生字體驗收。Repo-wide mypy 仍被未修改的 data_module/mops_t164_pdf_disposition_bridge.py 第 411 行語法錯誤阻擋；document-control link check 仍因兩個既有 output trial 引用 WinError 5 無法核對內容；原生 GUI／Owner UAT 未執行。

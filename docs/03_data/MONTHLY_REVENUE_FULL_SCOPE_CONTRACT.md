# TWSE／TPEx 月營收全用途授權與資料資格

## Owner 決策與邊界

Owner 已以 `FULL_SCOPE_MONTHLY_REVENUE_OWNER_AUTHORIZATION` 正式撤銷「僅限 current-only 月營收研究」的授權限制。具名 TWSE `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` 與 TPEx `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O` 的開發與使用授權涵蓋當期／歷史、趨勢／YoY／MoM／TTM、因子、選股／比較／產業題材、Scoring／Ranking／Portfolio Research、回測、Paper／Forward、ML 訓練／驗證與符合來源契約的後續研究功能。新增研究模組不需再次取得同一用途開發授權。

此決策沒有批准購買其他供應商、其他授權範圍、實盤、正式資金變更、排程變更、解除 Native 停止或取代既有 RC。歷史文件與原 `approval_request.pending.json` 保留當時事實，不能繼續用作當前僅授 current-only 的判斷。

Owner 授權與來源資格分開：來源身分／授權、每批品質、金額單位、可用時間／修訂、各用途 Gate、模型 Promotion 分別成立。本輪只將核實證據轉為相應資格，不一次將所有用途標成 PASS。

## 官方身分、授權與顯名

政府開放資料集 [18420：上市公司每月營業收入彙總表](https://data.gov.tw/dataset/18420) 與 [56510：上櫃公司每月營業收入彙總表](https://data.gov.tw/dataset/56510) 列出相應十四欄、金融監督管理委員會證券期貨局、免費、政府資料開放授權條款第1版，並連結 TWSE OpenAPI 文件。兩者資料資源另指向 MOPS 金融 CSV；這個關聯不能自動授權所有其他歷史 HTML／API。

[政府資料開放授權第1版](https://data.gov.tw/license) 允許不限目的、時間與地域的利用及衍生處理，並要求顯名；不包含商標／專利權，也不表示來源機關推薦或核准產品。資料輸出須保留提供機關、釋出資料集與版本／年份、條款連結及原始 SHA；衍生百分率／因子應明示由 Baldr 處理。不能將來源署名替換為 Baldr，也不能將 OpenData 改稱 MOPS HTML。

建議顯名：`金融監督管理委員會證券期貨局／臺灣證券交易所或證券櫃檯買賣中心，上市／上櫃公司每月營業收入彙總表，來源資料版本及 SHA；依政府資料開放授權條款第1版提供：https://data.gov.tw/license。衍生整理：Baldr。`

## 單位、時間與版本

原 OpenData pipeline 保留實際 HTTP 狀態、headers、EOF、原始 bytes、SHA、回應完成時鐘及精確市場／period。官方百分率欄位名稱含 `%`，可作原公布百分率研究；不得由此推導金額單位。金額未有精確 endpoint／欄位的官方證據與外部固定 proof SHA 時，保存原單位 Decimal，不換算 TWD、不填補未知為零。

`出表日期`、`資料年月`、官方發布時刻、本機捕獲、落盤完成、可供此版本讀取的下界是不同事實。歷史事後取得的值可保存為 retrospective 候選；不能稱當年已知值。`first_observed`／captured-as-of 只能證明當時本機觀測，不能替代既有 `formal-availability.v2` 所需的官方公告原件／版本／parent revision。回測與 ML 逐決策 cutoff 重選版本，不能先選最新值再改日期。

舊歷史表與 availability mapping 的鍵缺少市場，不直接改寫正式資料或默默遷入新雙市場資料。新候選歸檔須以市場、公司、period、來源與修訂識別原件；hash-addressed raw 保留一次、索引 create-only 並由外部 SHA 明選，讀回重核原 bytes／parser／row identity。未知單位亦能保留，無須先取得 TWD 金融資格。相同可見時間的不同內容必須回報衝突，不能依檔名或 hash 排序選勝者。

## 實作與驗收位置

共用用途政策位於 `data_module/monthly_revenue_use_policy.py`：全用途授權只限具名來源；逐用途判讀仍要求實際來源接受、授權原件、批次 SHA、可得時鐘、必要單位／官方 PIT 與下游 Gate。政策只檢查由已核原件投影的事實，不代替 registry、原件 reader 或來源審閱，也不自行簽發用途接受。

版本歸檔、歷史分批擷取與研究入口由 `scripts/monthly_revenue_archive.py` 提供；資格 reader 由 `monthly_revenue_qualification_binding.py` 逐次重讀外部SHA固定的manifest、來源接受revision及支持原件。它只投影既有 `limited/research_shadow` 接受，不生成正式Scoring、Paper或ML資格。已發行本機百分率研究包只覆蓋明選2026-09兩份raw，不更新正式registry或Main設定；工程審閱時間與Owner原始授權分開記錄。官方原頁語義由root審閱，reader的hash／schema驗證不能自稱法律審查。

研究service連接比較、篩選、分市場shadow因子與Portfolio研究；原推薦consumer另經精確source／normalizer／自然鍵／衍生摘要核對接受合格OpenData DTO，不改原MOPS身份。金額、正式評分／排名、回測、Paper／Forward與ML使用各自資格門；完整連續月窗的TTM／三月趨勢工程不會替未知單位簽證。

完成範圍、實際歷史覆蓋及 QA 見[全用途整合驗收](../06_qa/MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)及本任務 `output/tasks/baldr-monthly-revenue-full-scope` 的具名原始收據。操作見[研究管線](../07_guides/MONTHLY_REVENUE_RESEARCH_PIPELINE.md)。既有 RC `d9a2380fcb7e` 不因 Source 增量自動包含新功能。

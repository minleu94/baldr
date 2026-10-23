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

## 2026-10-22 Track B 歷史原件增量

新的隔離 r2 archive 已保存 2026-06 雙市場完整原件：TWSE 995／TPEx 865 列，共 1,860 列，外部 index SHA `9a36e482b106c9e54e2aa45fc9291b32a1490de877cf703c3f4caeb1cec489f1`。它明示 decoder profile `mops-big5-cp950-strict.v1`、effective codec `cp950`、parser v2，source version 亦包含這三項；舊 v1 archive 原件及身份保持，reader另有明示 legacy 相容路徑。兩者是**同一個雙市場歷史報表月份**，不重複計算，不等於全歷史或全公司完整；2026-07／08 的既有不完整捕獲維持失敗，不重試或拼接 prefix。原失敗 report、完整三跳、原 bytes／SHA 與離線修復收據見 [Track B 驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

MOPS 官方 host 宣告 Big5 而包含 CP950 擴充時，先依宣告 strict decode，僅該 codec 失敗且 exact MOPS host 才以 CP950 strict decode；壞 bytes 仍拒絕，原宣告與 raw hash 保持。不將 charset 相容當來源接受。這批歷史 HTML 的 license/use 尚未接受、金額單位仍 `unknown_no_twd_conversion`；available_at 是 2026-10-23 Taipei 的本機事後捕獲觀測，非 2026-06 官方發布時間。歷史 PIT、正式 Scoring／Backtest／ML 與其餘用途資格未因此成立，也未改正式 registry／DB 或既有百分率研究包。

雙市場六月原 HTML 的產業表頭確有 `單位：千元`。另建的 `mops-monthly-revenue-unit-scale-proof.v1` 只為這兩份固定raw保存逐產業／欄位的尺度證據：TWSE 33表／995公司列、TPEx 28表／865公司列；TWSE「存託憑證」只有明示零合計的空表，保留其scope但不計公司列，亦不混入全市場sibling合計表。五個金額欄的scale為1000，三個百分率欄不適用；不換算任何原值。跨列備註不在這份10欄mapping中，不藉此修改既有parser或archive。

Builder、create-only writer及reader都由固定SHA／URL／CP950 profile的真capture重新推導逐表證據；手造proof、自算SHA、原件或scope漂移、連結／讀取期間替換均拒絕。TWSE proof SHA `c5a998b5be056507f452f1b5b70081d033eaf25ac6c5dcee6a4b74fdca1b9336`、TPEx `a89e429422406c02e6beb61381206006f4545d3e39b638c1cb7af7839eeb2e0b`，QA與固定原件見[Track B驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

這是scale-only proof，`currency=unknown`、PIT／金融資格=false，不是貨幣及用途接受齊全的unit proof，不塞入archive既有`unit_proof_sha256`或將`unit_status`改verified。兩個OpenAPI單位仍未知，不以此乘1,000或標TWD；r2 archive、原百分率研究與既有資格不變。

## 2026-10-22 接任原件增量與 R7 獨立複核

2026-07..09雙市場6份完整HTML與六月2份原件，已由獨立受控reader離線重播；四個月archive為10批9423觀測，index `ac526dfb867e4434fbeb95f690d6e7d59c920e0079df7b29448ed24fe57165b5`。不是全歷史、全公司coverage或歷史PIT。印出日期10/23與本機捕獲時間如實保留，不能回填成六月到九月當時可用。

新增任意月份scale-only create-only writer及外部SHA reader，由完整capture重新推導每表/欄位與原件身份。八份原件可證千元尺度1000，currency仍unknown；不改原archive unit_status，不以此接受金額ML。Parity builder會重播OpenAPI transport/raw並核對rows，拒絕手改rows卻沿用rawSHA。

原9月parity：TWSE共同994、相符993，6443當月96562/88430及累計904467/896335差異皆8132，僅未解修訂候選；cross_verified_scale=null。TPEx共同863全部相符，另有OpenAPI-only30及MOPS-only3。不能將863/863稱為全上市櫃對等，也不能擅自排除6443湊PASS。

Scoring投影另外要求單一metric/period/value-kind/unit且股票唯一；正式use gate仍須獨立來源用途接受。原實測formal_scoring_gate_allowed=false，歷史Backtest樣本not_visible_by_cutoff、formal_pit=false。既有合格百分率研究沿原授權；全用途開發授權不等於所有歷史資料已合格。待補官方幣別、原可得時間、修訂公告與更長連續歷史。

獨立原件讀回 `monthly_capture_independent_readback_r7.json` SHA `d279d59ff2d3fbb96c019457498ca5e03091c2cd73e0fdc60b47b01f331b6b3e`，位於本次審查任務；QA與消費界線見[Track B驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

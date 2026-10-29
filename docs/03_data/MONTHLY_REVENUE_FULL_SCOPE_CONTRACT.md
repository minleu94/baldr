# TWSE／TPEx 月營收全用途授權與資料資格

## Owner 決策與邊界

Owner 已以 `FULL_SCOPE_MONTHLY_REVENUE_OWNER_AUTHORIZATION` 正式撤銷「僅限 current-only 月營收研究」的授權限制。具名 TWSE `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` 與 TPEx `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O` 的開發與使用授權涵蓋當期／歷史、趨勢／YoY／MoM／TTM、因子、選股／比較／產業題材、Scoring／Ranking／Portfolio Research、回測、Paper／Forward、ML 訓練／驗證與符合來源契約的後續研究功能。新增研究模組不需再次取得同一用途開發授權。

此決策沒有批准購買其他供應商、其他授權範圍、實盤、正式資金變更、排程變更、解除 Native 停止或取代既有 RC。歷史文件與原 `approval_request.pending.json` 保留當時事實，不能繼續用作當前僅授 current-only 的判斷。

Owner 授權與來源資格分開：來源身分／授權、每批品質、金額單位、可用時間／修訂、各用途 Gate、模型 Promotion 分別成立。本輪只將核實證據轉為相應資格，不一次將所有用途標成 PASS。

### Owner 研究取用指示（2026-10-28）

Owner 明確指示：其個人研究要取得公開可讀的 MOPS／TWSE／TPEx 資料；Owner 表示相關網站條款不適用於其研究，且不打算遵守。後續工程不得再只因端點條款／自動化授權尚未裁定，就停止 Owner 明確要求的公開資料研究取用；條款狀態記為未裁定並照原樣保存，不得再將它當成本項工作的流程阻擋。此處記錄 Owner 的立場與工作指示，不宣稱已獲來源授權，也不是法律適用性的獨立裁定。

此指示涵蓋 Owner 明確要求、透過一般公開頁面或端點可讀取的資料；不得把它擴張為登入、繞過 CAPTCHA／存取控制或其他技術限制的授權。對取得的資料保留請求 URL、擷取時間、原始回應與 SHA、來源及版本；擷取成功只證明原件已取得，不自動成立來源接受、單位／幣別、修訂橋、歷史 PIT、正式 DB 寫入或任何 Consumer Gate。MOPS 頁面顯示的公告日期／時間依 Owner 既有決定作公告 timestamp；仍須保留公告事件與目標數值 `source_version` 的精確對應證據。

## 官方身分、授權與顯名

政府開放資料集 [18420：上市公司每月營業收入彙總表](https://data.gov.tw/dataset/18420) 與 [56510：上櫃公司每月營業收入彙總表](https://data.gov.tw/dataset/56510) 列出相應十四欄、金融監督管理委員會證券期貨局、免費、政府資料開放授權條款第1版，並連結 TWSE OpenAPI 文件。兩者資料資源另指向 MOPS 金融 CSV；這個關聯不能自動授權所有其他歷史 HTML／API。

[政府資料開放授權第1版](https://data.gov.tw/license) 允許不限目的、時間與地域的利用及衍生處理，並要求顯名；不包含商標／專利權，也不表示來源機關推薦或核准產品。資料輸出須保留提供機關、釋出資料集與版本／年份、條款連結及原始 SHA；衍生百分率／因子應明示由 Baldr 處理。不能將來源署名替換為 Baldr，也不能將 OpenData 改稱 MOPS HTML。

建議顯名：`金融監督管理委員會證券期貨局／臺灣證券交易所或證券櫃檯買賣中心，上市／上櫃公司每月營業收入彙總表，來源資料版本及 SHA；依政府資料開放授權條款第1版提供：https://data.gov.tw/license。衍生整理：Baldr。`

## 單位、時間與版本

原 OpenData pipeline 保留實際 HTTP 狀態、headers、EOF、原始 bytes、SHA、回應完成時鐘及精確市場／period。官方百分率欄位名稱含 `%`，可作原公布百分率研究；不得由此推導金額單位。金額未有精確 endpoint／欄位的官方證據與外部固定 proof SHA 時，保存原單位 Decimal，不換算 TWD、不填補未知為零。

`出表日期`、`資料年月`、官方發布時刻、本機捕獲、落盤完成、可供此版本讀取的下界是不同事實。歷史事後取得的值可保存為 retrospective 候選；不能稱當年已知值。`first_observed`／captured-as-of 只能證明當時本機觀測，不能替代既有 `formal-availability.v2` 所需的官方公告原件／版本／parent revision。回測與 ML 逐決策 cutoff 重選版本，不能先選最新值再改日期。

每日 TWSE／TPEx OpenAPI 採集只保存當期 current snapshot；其 `出表日期` 是 report-level 欄位，不能送進歷史 issuer-period 公告 mapping。候選流程應先落地帶 raw SHA、source version 與 capture time 的 normalized research CSV，mapping 可留空並清楚列出缺公告事件證據；這不構成 formal availability 或 PIT。MOPS F22 事件可以提供公告日期／時間，但若對照已於事後擷取的數值快照，必須把公告事件鐘與 snapshot 數值可得鐘分開，`available_date` 不可早於數值實際可讀日；target source version 必須等於正式 SQLite 完整版本字串。

2026-07..09 固定 snapshot 的 narrow retrospective exception 僅接受 target version 前綴 `mops-static-snapshot-monthly-revenue-2026-10-29|snapshot=mops-static-snapshot.v2:` 且 `available_date=2026-10-30` 的 MOPS announcement mapping。這讓晚於一般 45 日窗口的舊期值仍從 snapshot capture boundary 起可見；更換 target prefix 或可得日即恢復一般晚到拒絕。不得將這個精確例外擴大成全來源／全期間的 availability 規則。

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

## 2026-10-23 WP4 TWSE 6443 逐欄差異與修訂判讀收據

針對 2026-09 TWSE 6443（元晶）於 OpenAPI 與 MOPS HTML 兩版本間之數值差異，核對固定 raw、出表時間、來源版本與欄位對照，建立逐欄差異收據如下：

### 1. 來源與原件固化

- **OpenAPI 原件**：
  - 來源 ID：`twse.openapi.t187ap05_L`
  - 請求端點：`https://openapi.twse.com.tw/v1/opendata/t187ap05_L`
  - Raw SHA256：`a58c04b3bdc2b94632027018ca4f09f6ad053848addb7b9580b372626542fc17`
  - 出表日期：民國 1151017（ISO 2026-10-17）
  - 觀測列數：1,088 列
- **MOPS HTML 原件**：
  - 來源 ID：`mops.history.monthly_revenue.twse`
  - 官方網址：`https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_9_0.html`
  - Raw SHA256：`373d75e8d66a0639f74fd2d0cd0a4f3229695a2c79dace2a454f2a6777b18e30`
  - 出表日期：民國 115/10/23（HTML header comment `05:59:53`）
  - 觀測列數：995 列，尺度證明 SHA256 `878916940196119a0579bc96bf526f45c11553a28685352129d4a827de9f8f40`

### 2. 逐欄對照矩陣（6443 元晶）

| 欄位名稱 | OpenAPI 欄位與數值 | MOPS 欄位與數值 | 差異 (OpenAPI - MOPS) | 符合性 |
| :--- | :--- | :--- | :--- | :--- |
| 公司代號 | `公司代號: 6443` | `公司代號: 6443` | 0 | 一致 |
| 公司名稱 | `公司名稱: 元晶` | `公司名稱: 元晶` | 0 | 一致 |
| 當月營收 | `營業收入-當月營收: 96562` | `當月營收: 88,430` | **+8,132 千元** | 不一致 |
| 上月營收 | `營業收入-上月營收: 66546` | `上月營收: 66,546` | 0 | 一致 |
| 去年當月營收 | `營業收入-去年當月營收: 186260` | `去年當月營收: 186,260` | 0 | 一致 |
| 當月累計營收 | `累計營業收入-當月累計營收: 904467` | `當月累計營收: 896,335` | **+8,132 千元** | 不一致 |
| 去年累計營收 | `累計營業收入-去年累計營收: 1452394` | `去年累計營收: 1,452,394` | 0 | 一致 |
| 前期累計 (累計-當月) | `807,905` | `807,905` | 0 | 算術完全一致 |
| 去年同月增減(%) | `營業收入-去年同月增減(%): -48.15` | `去年同月增減(%): -52.52` | +4.37% | 各自符合當月數值 |
| 前期比較增減(%) | `累計營業收入-前期比較增減(%): -37.72` | `前期比較增減(%): -38.28` | +0.56% | 各自符合累計數值 |
| 備註說明 | `本月營業收入較去年同期減少係因客戶需求減少所致` | `月營收相較同期減少，主要受政府綠能政策速度及市場淡旺季影響所致。` | 說明文字相異 | 修訂版本反映 |

### 3. 算術一致性與判讀結論

1. **內部算術完全自洽**：
   - OpenAPI：`904,467 (累計) - 96,562 (當月) = 807,905 千元`
   - MOPS：`896,335 (累計) - 88,430 (當月) = 807,905 千元`
   - 兩者截至 2026-08 之歷史前期累計營收皆為 `807,905 千元`，上月（8月）營收皆為 `66,546 千元`，去年同期數字亦完全相符。差額 +8,132 千元完全且僅集中於 2026-09 單月，並線性遞延至當月累計營收。
2. **修訂時序判讀**：
   - 官方出表日期分別為 1151017（OpenAPI）與 115/10/23（MOPS），數值及備註不同，只能證明兩份捕獲版本有差異。未取得具名官方更正公告或版本沿革前，不能推定已發生更正／重編、實際修訂時間或任一版本較正確。
3. **治理與資格判定**：
   - 目前依契約定性為 `unresolved_revision_candidate`（未解修訂候選）。
   - **雙版本原值完整保留**：工程不得擅自判定何者為「正確」版本，亦不得逕自排除 6443 以湊成 100% 對等。
   - **TWSE 2026-09 跨來源尺度判定**：因 6443 存在 2 欄數值不一致（amount_mismatch_count = 2），TWSE 2026-09 之 `cross_verified_scale_to_base_unit` 維持 `null`，不生成正式金融資格。
   - 完整收據記錄於 `output/tasks/baldr-track-b-six-packages-20261023/wp4_twse_6443_revision_diff.json`。

## 2026-10-23 WP5 月營收歷史 Coverage 與 Availability 具名矩陣清冊

依 2026-06..09 雙市場八份完整 HTML 原件與兩份 2026-09 OpenAPI 原件（四個月 archive 共 10 批、9,423 筆觀測，索引 SHA256 `ac526dfb867e4434fbeb95f690d6e7d59c920e0079df7b29448ed24fe57165b5`），整理具名盤點矩陣如下：

### 1. 批次摘要（尚非逐發行人與來源版本矩陣）

| 批次 | 期別 | 市場 | 來源類型與 ID | 原始 SHA256 (首8碼) / Bytes | 尺度證明 SHA256 (首8碼) | 觀測列數 (發行人家數) | 金額尺度 | 幣別 | 官方出表時間 | 本機觀測時間 | PIT/可得性 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 | 2026-06 | TPEx | `mops.history.monthly_revenue.tpex` | `a2e43407...` / 394,920 B | `a89e4294...` | 865 列 (865 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 1 | 2026-06 | TWSE | `mops.history.monthly_revenue.twse` | `116fa1f6...` / 454,774 B | `c5a998b5...` | 995 列 (995 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 2 | 2026-07 | TPEx | `mops.history.monthly_revenue.tpex` | `2e95ec42...` / 394,928 B | `488d2999...` | 865 列 (865 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 3 | 2026-07 | TWSE | `mops.history.monthly_revenue.twse` | `11150efd...` / 454,778 B | `f3ba5928...` | 995 列 (995 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 4 | 2026-08 | TPEx | `mops.history.monthly_revenue.tpex` | `cad3b21a...` / 395,356 B | `316fd90c...` | 866 列 (866 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 5 | 2026-08 | TWSE | `mops.history.monthly_revenue.twse` | `06593a29...` / 455,420 B | `a950f356...` | 995 列 (995 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 6 | 2026-09 | TPEx | `mops.history.monthly_revenue.tpex` | `f8b339b6...` / 395,392 B | `1e9118de...` | 866 列 (866 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 7 | 2026-09 | TWSE | `mops.history.monthly_revenue.twse` | `373d75e8...` / 455,508 B | `87891694...` | 995 列 (995 家) | 1,000 (表頭明示) | unknown | 115/10/23 | 2026-10-23 | 未證明 (事後觀測) |
| 8 | 2026-09 | TWSE | `twse.openapi.t187ap05_L` | `a58c04b3...` / 607,634 B | `02477fa3...` (parity) | 1,088 列 (1,088 家) | null (6443差異) | unknown | 1151017 | 2026-10-21 | 未證明 (事後觀測) |
| 9 | 2026-09 | TPEx | `tpex.openapi.mopsfin_t187ap05_O` | `a27fea12...` / 496,597 B | `ed4a0293...` (parity) | 893 列 (893 家) | 1,000 (交叉核驗) | unknown | 1151017 | 2026-10-21 | 未證明 (事後觀測) |

**合計**：10 批次、9,423 筆發行人月營收觀測值。原 WP5 JSON 每批只列五筆樣本，未提供逐發行人與完整來源版本矩陣；它是批次摘要，不能作為逐列 coverage 驗收。原批次 available_at 應與捕獲、落盤與 availability_basis 一起保留，不可直接等同官方發布時間。

### 2. 尺度與幣別治理分離

1. **千元尺度（Scale-to-base unit）**：
   - 八份 MOPS HTML 原件已由 `data_module/monthly_revenue_unit_scale_proof.py` 嚴格推導逐產業表頭與欄位，證明 `scale_to_base_unit = 1000`。
   - OpenAPI 原件端點未明示單位；TPEx 的 863 家共同發行人僅在當月及當月累計兩欄金額相符，這份交叉比較不得外推其餘 30 家 OpenAPI-only 公司、其他欄位或全批尺度資格。TWSE 因 6443 差異維持 `scale = null`。
2. **幣別（Currency）**：
   - 所有 10 批次原始資料皆未包含官方貨幣代碼，全數標記為 `currency = unknown`。
   - **禁止擅自換算 TWD**：在取得官方幣別證據前，不得將未知幣別視同新台幣，亦不得將未知填補為零。

### 3. 時間維度與 Point-in-Time (PIT) 嚴格隔離

1. **事後取得時間不得冒充歷史可用時間**：
   - MOPS HTML 出表日期為 `115/10/23`，本機捕獲時間為 `2026-10-22T22:58:11Z`（Taipei 10/23）。
   - OpenAPI 捕獲時間為 `2026-10-21`。
   - 歷史月份（2026-06、07、08）之發布時刻未經官方公告原件證明，全數維持 `historical_pit_eligible = False` 與 `historical_availability_proven = False`。
   - 回測與決策系統不得以事後取得時間回填為歷史當時已知。

### 4. 下游 Consumer 用途資格盤點

| Consumer 用途 | 資格狀態 | 拒絕／限制原因 |
| :--- | :--- | :--- |
| **Formal Scoring** | **未合格 (Not Qualified)** | `formal_scoring_gate_allowed = False`；缺已驗證幣別及官方 PIT 證明。 |
| **Backtest 回測** | **未合格 (Not Qualified)** | 歷史樣本依決策 cutoff 不可見（`not_visible_by_cutoff`）；`formal_pit = False`。 |
| **ML 重訓與驗證** | **未合格 (Not Qualified)** | `currency = unknown`，未建立正式 PIT 與正規化貨幣資格。 |
| **Paper 實盤模擬** | **未合格 (Not Qualified)** | Formal runtime 與真實 Paper 來源尚未經 Owner 批准選定。 |
| **Limited Research Shadow** | **有限合格 (Partially Qualified)** | 既有已發行百分率研究資格只限明選 2026-09 兩份 OpenAPI raw；不能擴及同期 HTML 或所有歷史版本。其餘歷史候選可做授權範圍內的隔離工程與原值審閱，尚未取得 consumer 用途資格。 |

完整收據檔案已固化於 `output/tasks/baldr-track-b-six-packages-20261023/wp5_monthly_revenue_history_inventory.json`。

上述用途開發已有全用途授權；尚未合格的原因是來源／批次／時間與 consumer Gate，不是重新等待 Owner 批准相同開發範圍。原 WP4 JSON 的 `variance_amount_thousand_twd` 欄位誤帶幣別，應讀作原單位數值差額 8,132；目前不能授 TWD 或 OpenAPI 全批尺度。兩份原收據保留原貌，由獨立複核收據記錄更正。

## 2026-10-29 固定 MOPS 快照回填雙時鐘規則

Owner 已授權以逐年抽樣驗證後回填此固定的官方數值快照。數值來源與公告事件分開記錄：`mops-static-snapshot-monthly-revenue-2026-06-16` 的數值 `available_date` 固定為快照 session 規則推得的 **2026-06-18**；F22 的 `announced_date`／`announced_at` 保留事件原值。因數值快照在 2026-06-18 前尚未進入本機來源版本，所有回測、篩選與決策 cutoff 必須以 `available_date` 判斷；不可因公告日期較早而讓這個快照提前可見。

此例外只適用於精確的 target source version `mops-static-snapshot-monthly-revenue-2026-06-16` 及 `available_date=2026-06-18`，不改動一般月營收公告的 45 日檢查。回填前必須由 accepted snapshot 的 `fetched_at` 逐列驗證 snapshot capture 不晚於 mapping available date；所有 2020-01 至 2025-12 的數值還必須與同版正式 SQLite 精確相同。相同 `(stock_code, period, source_version)` 若既有來源或 Decimal 數值不一致，writer 必須中止，不覆蓋；一致時只更新日期／品質欄位並保留原 `created_at`。

2026-10-28/29 年度分層抽樣的 18 筆（2020–2025 每年上市、上櫃各一筆）均與目前 MOPS F22 明細頁的公司、期別、本月數值及新台幣仟元標示相符。另有完整靜態 CSV 到正式 SQLite 的 126,899 列數值精確相等檢查。抽樣是頁面解析與單位 sanity check，不宣稱逐列讀取 126,899 張 F22 頁面，也不把晚期頁面當成公告當時封存版。

2026-10-29 再補 2014–2019 分層樣本：六個年度各抽 SII／OTC 一筆，12/12 官方 F22 明細頁的公司代碼／名稱、期別、仟元單位、本月營收與固定 snapshot 值一致，raw HTML 與 SHA-256 readback 通過。此抽樣確認舊期頁面解析和單位 sanity check，仍不代表全列頁面驗證或公告時點版本證明。

此次 crosswalk 的 126,899 個正式列中，126,518 個鍵找到唯一 F22 事件；排除公告晚於 snapshot capture 的 15 鍵、來源市場標籤不一致的 144 鍵後，126,359 列可寫入正式公告日期／時間 mapping（其中 9 列只有日期，`announced_at` 留空）。另 540 列只證明數值快照自 2026-06-18 可用，採 capture-only baseline，公告日品質仍維持 degraded（381 無事件、144 市場不一致、15 事件晚於快照）。事件日期晚於期末 45 日不代表 snapshot 在公告日可用；本次仍以 2026-06-18 作數值可得日，並保留真實公告日。此回填不授予 snapshot 在原始公告日的 PIT 資格。

### 正式回填結果（2026-10-29）

已透過既有 guarded recovery writer 寫入正式 SQLite 與 `monthly_revenue_availability.csv`。126,899 列全數將數值快照 `available_date` 校正為 2026-06-18；126,359 列有唯一且符合 target source version 的公告 mapping，品質轉為 `observed`；540 列沒有可安全套用的公告 mapping，保留 `degraded`。這次寫入只更新既有相同來源版本的 availability／quality 欄位，交易內逐列要求來源版本與 Decimal 數值完全相同，保留 `created_at`，不改數值。

寫入後限定期間／來源版本的 SQLite 分組讀回為上述 126,359／540；recovery receipt 為 `applied=true`、無衝突。完整 DB 備份由 writer 建立並通過備份 `quick_check`。完整正式 DB 的 post-write `quick_check` 未完成，不能記為已通過。對應收據、候選與備份路徑記於[具名 QA 報告](../06_qa/MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md#2026-10-29-正式回填與讀回)。

### 全歷史 final readback（2026-10-29）

後續將 2014-04..2019-12 與 2026-01..04 分段加入既有固定 snapshot recovery，並以兩個歷史 F22 詳細頁核實 5236／8908 的 market metadata mismatch。全範圍 2014-04..2026-04 共 242,651 列；目前固定 target version 241,925 observed、726 degraded。後者為 689 無已保存事件、36 公告晚於 snapshot available date、1 公告 timestamp 晚於該 row 的 snapshot capture。兩個已核代碼共 290 期完成公告 mapping；未因事件市場標籤 `sii` 與 snapshot market 欄 `tpex` 不同而拒絕精確、唯一的 stock-code／period 事件鍵。剩餘 726 列與 evidence、備份、最終 SQLite 讀回見[最終 MOPS QA](../06_qa/MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md#2026-10-29-市場標籤裁決與最終剩餘缺口)。

來源 timestamp 與 snapshot `available_date=2026-06-18` 仍是不同時鐘；公告晚於該日或晚於逐列 snapshot capture 的事件仍不會被套用至早期數值版本。無事件列仍保留 capture-only baseline 並維持公告品質 degraded；數值欄位可自 snapshot 可得日起讀取。此批回填完成不代表 689 個無事件列已獲公告完整性證據，也不宣稱 snapshot 中每個歷史數值是公告當時版本。

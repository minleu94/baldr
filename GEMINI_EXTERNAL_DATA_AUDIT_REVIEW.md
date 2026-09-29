# Gemini 外部資料缺口審查：Independent Evidence Review

審查日期：2026-09-28（美西；MOPS 頁面觀察時已顯示臺北 115/09/29）。審查對象是根目錄的 [EXTERNAL_DATA_SOURCE_GAP_AUDIT.md](EXTERNAL_DATA_SOURCE_GAP_AUDIT.md)，不是來源接線或正式資料驗收。本輪只讀 repository、既有 QA 收據及官方網站；正式 SQLite、schema、排程、回填、模型與既有 PIT 證據均未修改。

## Executive Verdict

**可採納的部分**：官方 MOPS 公告快易查確有帶秒級畫面時間的營收公告；專案另已有經 bounded 實際 POST/raw 驗證、僅供研究的 F26–F29 財報公告 adapter。月營收／季報數值來源與公告時間來源應分離，歷史產業歸屬、TDCC 舊週資料及真實成本也確有不同程度的缺口。

**必須修正的部分**：Gemini 把顯示時間等同正式 `available_at`、把公告查詢等同完整歷史狀態、把產業變更公告等同全市場產業歸屬，並把「個人研究目前無須購買」寫成「所有歷史 PIT 都可免費補齊」。其 `formal_records=0` 與最新正式庫 QA 相反；Stage C 的 19 筆 pending 也不能歸因為單純時間未到。

**仍未驗證**：Gemini 指定的 `mops.twse.com.tw/mops/web/ajax_quickpgm`、該端點 POST payload/回應、月營收舊公告與更正版本的完整性、產業初始分類及全歷史覆蓋。原 Gemini 文件沒有附出所稱 payload 或 `soup.find_all('tr')` 程式；這段屬 **NOT VERIFIED PARSER**。可以進入隔離可行性原型，不能據此改正式 `available_at` 或宣稱 Formal/OOS gate 已解。

判讀權威：現況以 [PROJECT_SNAPSHOT](docs/00_core/PROJECT_SNAPSHOT.md)、[DOCUMENTATION_INDEX](docs/00_core/DOCUMENTATION_INDEX.md)、[WP5 checkpoint](docs/06_qa/WP5_CHECKPOINT_CURRENT_20260928.md)、[M11 Stage C](docs/06_qa/M11_PERSONAL_RESEARCH_OUTCOME_STAGEC_20260928.md) 與原始 [Stage C summary](output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json) 為準；舊候選與 roadmap 不覆蓋目前裁定。

## Claim-by-Claim Review

`GEMINI_CLAIM_REVIEW`。分類只針對所寫主張的完整範圍，不把一個樣本的成立外推成全量成立。

| Claim | 分類 | Repository evidence | External evidence | Reasoning | Remaining uncertainty |
|---|---|---|---|---|---|
| A. ezSearch 提供所需 publication timestamp | **PARTIALLY_VERIFIED** | [來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)第 36、124–129 行：F26–F29 的 36 個公告事件有秒級 `announcement_at`，限研究；[adapter](data_module/mops_ezsearch_statement_availability.py)讀 `CDATE`/`CTIME`。 | [官方 ezSearch](https://mopsov.twse.com.tw/mops/web/ezsearch)的「營收公告」最新列，本輪瀏覽器可見日期/時分秒、公司、月份連結。 | 有官方畫面時間與 bounded 季報回應，不等於已證明所有項目的法定發布語意或歷史完整性。 | `CDATE`/`CTIME` 對提交、公開、處理或最後更新的精確定義及延遲。 |
| B. 該時間可直接作正式 `available_at` | **CONTRADICTED** | [基本面契約](data_module/fundamental_availability.py)第 23–27、60–92、133–155 行要求獨立可驗公告、hash/revision 並禁止可得日早於公告；[來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)僅准次一曆日的研究 date-only 投影，formal=`none`。 | 官方頁面只顯示公告列時間，沒有證明本系統同秒能取得。 | 公告、來源處理、抓取完成、交易決策時點是不同時鐘；直接賦值會偷換契約。 | 可用時點政策、來源延遲及修訂事件需逐來源決定。 |
| C. ezSearch 歷史足夠重建 fundamental PIT | **UNVERIFIED** | 同一[台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)明載歷史完整 coverage 未證；[V4 recovery](docs/06_qa/V4_DATA_RECOVERY_2026_09_07.md)只保存 bounded 批次。 | [官方查詢頁](https://mopsov.twse.com.tw/mops/web/ezsearch)標「資料區間（自102年起）」。 | 可選起始年是 UI 宣告，不是逐公司、逐市場、逐版本的 completeness 證據；2013 年前亦不在該宣告內。 | 舊資料缺頁、查詢上限、刪改公告、曾有不同 schema。 |
| D. 月營收可藉 ezSearch 重建 historical PIT | **PARTIALLY_VERIFIED** | [月營收契約](docs/06_qa/R023_FUNDAMENTAL_MONTHLY_REVENUE_CONTRACT_MIGRATION_20260923.md)要求 explicit `available_date`、公告與 revision；[來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)仍把 TWSE/TPEx 月營收列為候選。 | [官方 ezSearch](https://mopsov.twse.com.tw/mops/web/ezsearch)最新營收列可見秒級時間與月份，如 115 年 5 月、8 月；其詳情連至 `ajax_t05st10_ifrs`。 | 單列證明可解析月別候選，不證完整舊公告、原值、同一公司更正鏈或與正式月營收列唯一連結。 | 月營收歷史查詢、各市場覆蓋、修正前值及 stable identity。 |
| E. 季報／財報可藉 ezSearch 重建 historical PIT | **PARTIALLY_VERIFIED** | [既有 adapter](data_module/mops_ezsearch_statement_availability.py)限定 F26–F29；[來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)為 `limited` research；[MOPS owner packet](docs/06_qa/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md)另有 t163sb06 數值+t57sb01 listing 的單候選，未正式接受。 | [官方 ezSearch](https://mopsov.twse.com.tw/mops/web/ezsearch)列 F26–F29、E02、M31 等不同項目。 | 已證明 bounded 公告事件 lane；EZSearch 不是財報數值/XBRL 文件、修訂鏈或全期 coverage。M31 混合預告與決議，既有政策排除。 | filing/document identity、重編更正鏈、全市場歷史覆蓋及獨立 numeric lineage。 |
| F. 產業變更公告可完整重建歷史分類 | **OVERCLAIMED** | [PIT 產業 discovery](docs/06_qa/PIT_INDUSTRY_SOURCE_ACCEPTANCE_DISCOVERY_2026_09_15.md)與[caller QA](docs/06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)均未接受完整 historical sidecar；[WP2 current provenance](docs/06_qa/WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md)仍標 current/unknown。 | [TWSE 調整要點](https://twse-regulation.twse.com.tw/tw/law/DOC01_print.aspx?FLCODE=FL007104&FLNO=2)與[2023 年 47 家調整公告](https://twse-regulation.twse.com.tw/TW/int/DAT01_print.aspx?FLCODE=FE369062)證明存在變更及「公告日 ≠ 實施日」的例子。 | 變更事件沒有 initial state、退市/轉板/改名/合併和 taxonomy 版本就不能生成完整每日成員表。 | 各市場初始分類、所有事件類型、全期覆蓋及 effective interval。 |
| G. 不再需要 TEJ 或其他付費 PIT dataset | **OVERCLAIMED** | [產業 discovery](docs/06_qa/PIT_INDUSTRY_SOURCE_ACCEPTANCE_DISCOVERY_2026_09_15.md)列官方付費歷史商品為候選，亦明示 prospective 可獨立前進；[Snapshot](docs/00_core/PROJECT_SNAPSHOT.md)保留 formal PIT 缺口。 | [TWSE 產業對照歷史商品](https://eshop.twse.com.tw/zh/product/detail/000000006e0bbe8d016f18269c59032c)是另一種候選，但商品存在也不等於已購買或可用。 | 個人研究可不購買；完整舊 PIT 能否免費補完尚未證明。亦可選「只有可驗 PIT 之後才訓練」縮小問題。 | 目標歷史窗、可接受漏率、資料條款、付費商品的實際 lineage。 |
| H. TDCC 歷史資料需要 FinMind | **CONTRADICTED** | [FinMind 候選 QA](docs/06_qa/V2_3_FINMIND_CANDIDATE_SOURCE_AUDIT_2026_07_12.md)記載該集保 dataset 對目前帳號未授權；[TDCC QA](docs/06_qa/V4_TDCC_DATA_COMPLETION_20260909.md)已自官方端取得近期候選。 | [TDCC 官方查詢](https://www.tdcc.com.tw/portal/zh/smWeb/qryStock)明示歷史檔自 97/7 建置但保存/查詢期一年；[官方 OpenAPI](https://openapi.tdcc.com.tw/)有 `1-5`。 | 近期歷史可走官方；更舊歷史仍可能缺，但「必須 FinMind」錯誤且目前未授權。 | 一年前各週是否有合法可取得的官方封存或商業交付。 |
| I. 成本／bid-ask 只是 Optional | **OVERCLAIMED** | [WP4 assessment](docs/06_qa/WP4_PERSONAL_MODEL_ASSESSMENT_READBACK_20260928.md)為 after-cost `unavailable/null`；[成本 QA](docs/06_qa/DAILY_BANKTAIWAN_LEARNING_COST_2026_09_14.md)允許明示估算情境但成本不可得時保持 unknown。 | 本題沒有足以證明逐筆 spread/impact 的官方外部資料。 | 逐筆買賣價差對 gross close-to-close 研究可選；對聲稱「真實可成交/嚴格 after-cost」並非可忽略。固定費稅估算不能證明滑價/impact。 | 需要的是哪種成本聲明與可觀測資料粒度。 |

## MOPS ezSearch Technical Verification

已驗的 URL 是 [頁面](https://mopsov.twse.com.tw/mops/web/ezsearch)及現有 [adapter](data_module/mops_ezsearch_statement_availability.py)所用 `https://mopsov.twse.com.tw/mops/web/ezsearch_query`。2026-09-07 [V4 recovery QA](docs/06_qa/V4_DATA_RECOVERY_2026_09_07.md)第 330–332 行記錄三次該 URL 的 F26/F27/F28 **POST HTTP 200** 與 raw SHA-256；2026-07-27 [來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)第 124–129 行記錄 36 個 bounded 事件。Gemini 提出的 `https://mops.twse.com.tw/mops/web/ajax_quickpgm` 在其報告中沒有 request/response 或 payload；本輪官方頁面的可見 URL 和既有已成功路徑都不支持把它宣稱為 ezSearch 使用中的端點。對它只能判 **UNKNOWN / NOT VERIFIED**，不是證明它不存在。命令列唯讀 GET 因本環境 socket 權限被擋；沒有對該 URL 成功的即時 HTTP probe。

| 檢查項 | 審查結果 |
|---|---|
| Request method / payload | `ezsearch_query` 的既有實作與 QA 證實 POST；[build_query_payload](data_module/mops_ezsearch_statement_availability.py)給 `step=00`, `RADIO_CM=1`, `TYPEK`, `CO_MARKET`, `CO_ID`, `PRO_ITEM`, `SUBJECT`, `SDATE`, `EDATE`, `lang=TW`, `AN`，F26–F29 bounded。**Gemini 的 `ajax_quickpgm` payload 未提供，無從驗證。** |
| Cookies、CSRF、session | 現有 adapter 透過可注入 session POST，顯式傳 `Referer` 與 `User-Agent`，沒有顯式 CSRF 欄；歷史成功不能證明所有時段/環境都不需 cookie 或 session。**UNKNOWN**。 |
| Response encoding / schema | 現有 adapter 用 `response.json()`，要求 JSON object、`status` 與 `data` array；原始 HTTP charset/跨年代編碼 **UNKNOWN**。每個可接受財報列需 `CDATE`, `CTIME`, `TYPEK`, `COMPANY_ID`, `COMPANY_NAME`, `AN_CODE`, `AN_NAME`, `SUBJECT`, `HYPERLINK`；舊列可能缺 `CTIME`，會隔離為 invalid event。這是既有 F26–F29 schema，不代表 Gemini URL 的 schema。 |
| Timestamp 欄及語意 | F26–F29 parser 以 `CDATE`+`CTIME` 轉 `Asia/Taipei` `announcement_at`；官方畫面營收列也可見秒級時間。是否精確等於 company submission/publication/MOPS processing/last update，以及來源處理延遲，**UNKNOWN**。首頁的「資料更新時間」另是一個 page clock，不能混用。 |
| Pagination / query cap / date range | [adapter](data_module/mops_ezsearch_statement_availability.py)在單查詢 `>=1000` 列 fail closed；[來源台帳](docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)採 31 日研究查詢。這是專案保守限制，**不是已證的官方最大區間或 paging 規格**。官方頁面標自民國 102 年起；完整回傳/分頁重現舊公告仍 **UNKNOWN**。 |
| Rate / operational | 官方可接受頻率、封鎖閾值、維護窗口、權利條款與站點變更政策未由本輪證明；僅能遵循既有 bounded 人工研究/失敗收據，不宣稱可排程量抓。 |
| Revision / stable ID | 現有 `event_hash` 是以公司、期別、公告時刻、項目與 detail URL **自行計算**，不是官方 stable announcement ID。MOPS 重大訊息 detail URL 可見 `COMPANY_ID`/`SPOKE_DATE`/`SPOKE_TIME`/`SEQ_NO`，但不能外推至營收/財報版本鏈。更正、重編與舊版本是否保留 **UNKNOWN**。 |
| Parser | Gemini 原報告沒有可檢視的 `soup.find_all('tr')`/`cols[i]` 實作、fixture 或欄位定位；標記 **NOT VERIFIED PARSER**。既有 F26–F29 JSON parser 不能替這段 HTML parser 背書。 |

`115/09/28 22:41:06` 至多先存為 `official_announcement_at`（並保留官方原始欄名、raw bytes/hash、來源 URL、抓取完成時間、時區與事件身份）。即使時間真為公開時刻，也尚需決策時鐘、盤後/假日、官方日曆、擷取延遲、公告更正及 numeric 版本配對的 source policy，才可推導某個 `available_at`。現有研究 policy 將 F26–F29 秒級公告映射至**次一曆日**，刻意避免同日盤中前視；它不是正式來源接納。對有較晚修正的同一 period 必須保留舊 revision 在舊 decision cutoff 的可見值，不得以現值覆寫。

## Fundamental PIT Verdict

### MONTHLY_REVENUE_PIT_FEASIBILITY

**可行性：有值得驗證的公告事件候選，完整歷史 PIT 未成立。** 官方頁最新營收列能同時顯示時間、公司與「115 年 N 月營業收入」；既有 [月營收 contract](docs/06_qa/R023_FUNDAMENTAL_MONTHLY_REVENUE_CONTRACT_MIGRATION_20260923.md)已有 `available_date <= decision_date` 和 append-only revision 設計。然而本輪未證明歷年每公司/市場每月公告完整、時間欄涵義、營收值對應哪個原始/更正版本、公司改碼連結與原版保存。對 2013 年前歷史不能由該頁「自 102 年起」推論。

### FINANCIAL_STATEMENT_PIT_FEASIBILITY

**可行性：F26–F29 的 bounded 研究公告事件已驗，完整財報歷史 PIT 未成立。** [MOPS adapter](data_module/mops_ezsearch_statement_availability.py)按標題解析年度/季度並限制項目；[V4 recovery](docs/06_qa/V4_DATA_RECOVERY_2026_09_07.md)另以 t164/XBRL numeric、EZSearch 公告與 t57sb01 listing 分離 lineage，且有無匹配/標題衝突失敗案例。仍需 filing/publication 精確語意、合併/個別報表、XBRL 文件 identity、完整更補正/重編鏈、版本保留及全期 coverage。EZSearch 的「財務報告」類別本身不提供這些證明。

## Historical Industry Classification Verdict

**目前判定：`PARTIAL EVENT-SOURCED RECONSTRUCTION` 候選；`complete historical industry classification` 未成立。** [TWSE 官方調整要點](https://twse-regulation.twse.com.tw/tw/law/DOC01_print.aspx?FLCODE=FL007104&FLNO=2)規定調整會公告；[47 家調整公告](https://twse-regulation.twse.com.tw/TW/int/DAT01_print.aspx?FLCODE=FE369062)於 112/05/22 發文，112/07/03 才實施，已直接否定 announcement date = effective date。此種公告可補某些事件，但不足以證明每家公司上市/上櫃**初始**分類，亦未覆蓋 TPEx→TWSE、下市、改名改碼、合併、個別重分類、33 類前後 taxonomy/定義版本與不同市場的全期變更。沒有 baseline snapshot + 完整事件 + 獨立全市場 denominator，不能算每日 PIT membership。專案 [PIT discovery](docs/06_qa/PIT_INDUSTRY_SOURCE_ACCEPTANCE_DISCOVERY_2026_09_15.md)和[caller QA](docs/06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)的 historical limitation 保持有效；prospective 第一觀測日可以另行累積，不會倒填舊日。

## Paid Data Requirement

### Required now

**個人研究目前無須購買。** 使用者接受的指定 SQLite 與研究來源時間假設，足以維持已明示限制的個人研究；不能把它改稱官方歷史 PIT 或 formal OOS。對全歷史完整回建，本輪也不能說「必須立刻買」：先決定是否真的需要那段歷史。

### Potentially useful later

若產品明確要求長區間、多市場、完整歷史基本面/產業成員與可稽核版本，付費官方或第三方 PIT 商品可作候選，須另驗授權、交付範圍、raw/修訂/時間 lineage；**免費官方來源足以補完全部歷史基本面或分類**均未證明。TDCC 官方 UI 明示歷史保存一年，更舊週資料也需另找合法封存或縮小窗；FinMind 目前帳號對相關 dataset 未授權。

### Not required

若策略選擇「僅讓有可重驗 PIT evidence 之後的觀測進模型」，不需購買舊歷史來**偽裝**先前期間的 PIT；成本是樣本/歷史窗縮小，應明示。即使未購買逐筆 bid-ask，也可以做 gross return 或明示估算成本的研究，不能宣稱真實 after-cost 執行績效。

## CURRENT_GAP_VERDICT

| 類別 | 目前判斷與證據 |
|---|---|
| True external data gap | 若目標為全舊期集保週資料、逐筆 spread/impact、全歷史產業初始狀態，現有已驗免費來源尚不足；這是**目標依賴**的缺口，不等於今天必須購買。 |
| Historical evidence gap | 基本面公告與 numeric revision 對應、產業初始/變更/effective interval、來源時間/完整性；[Snapshot](docs/00_core/PROJECT_SNAPSHOT.md)與[PIT QA](docs/06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)保持 blocked。 |
| Pipeline wiring gap | 部分來源/consumer 接線仍須查；但 Gemini 的「三大法人/信用正式表是空的」與 [2026-09-21 正式庫唯讀 QA](docs/06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)不符：當時 `institutional_flows=229,472`、`credit_transactions=22,163`，最新同為 2026-09-08。這些 count **不證明新鮮或已治理可用**，亦不能由舊 candidate register 的 `formal_records=0` 代表整個正式表。 |
| Governance/admission gap | F26–F29 EZSearch 只 `limited` research；P0 MOPS packet 的 1/13 machine verified、13 deferred/owner-ready 0 不授予正式 source admission；[formal readiness](docs/06_qa/FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md)為 0/3。 |
| Natural maturity | 自然 forward 20-session endpoint 不能加速；但 [M11 原始 summary](output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json)只記 **1 capture、19 pending、0 matured、0 outcome artifact**，單一 `personal_outcome_source_or_cost_incomplete`。摘要未提供 19 筆逐列診斷，故 **CAUSE BREAKDOWN NOT YET PROVEN**；不能說「大部分只是等待」。[producer](ml_module/recommendation_natural_outcome_service.py)此 reason 同時涵蓋來源/成本 pending。 |
| Optional enhancement | Gross-only 研究的逐筆 bid-ask、進階滑價模型可為後續增強；正式 after-cost/可成交主張所需資料與政策並非 optional。[WP4 readback](docs/06_qa/WP4_PERSONAL_MODEL_ASSESSMENT_READBACK_20260928.md)仍為 after-cost `unavailable/null`。 |
| No longer a gap | 正式三大法人/信用表「完全空白」不是目前 QA 事實；近期 TDCC 也已有 [4,047 列官方候選及後續正式覆蓋記錄](docs/06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。這不解除較舊歷史或 source-time 缺口。 |

## Recommended Next Step

**`PROTOTYPE — isolated MOPS feasibility adapter`**。限定於現有受核准的唯讀/研究邊界，優先重用已驗 `mopsov.../ezsearch_query` 及既有 F26–F29 adapter，而非實作 Gemini 未驗的 `ajax_quickpgm`。原型應用少量跨年份/市場/公司樣本保存原始回應、HTTP 完成時間與 hash，逐項量測月營收 F22、財報 F26–F29 的歷史查詢、欄位變化、查詢上限、版本/更正與 numeric/XBRL 對應；失敗要留下可重驗負證據。這是**下一階段建議**，本輪沒有自行開始程式實作、排程或正式資料寫入。原型完成後才決定 source contract/正式 admission 設計；任何未證明項維持 UNKNOWN。

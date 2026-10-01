# Fundamental OpenAPI 來源採用與季度報表目錄 QA（2026-10-01）

## 範圍與結論

本文件前半最初記錄的是 metadata-only catalog／來源採用檢查：當時沒有呼叫季度數值端點。10/1 後續另以受控 standalone collector CLI 實際執行一次 26 GET；collector 已接到 weekly wrapper，但該次不是自然 weekly Task child。完整 rows、readback 與 review items 見[季度 OpenAPI live capture QA](SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)。兩輪都沒有寫正式資料庫或執行 apply；本文件描述的單位與 formal acceptance 缺件仍成立。

目前月營收 OpenAPI 候選可供研究及完整性檢查，不能正式套用：官方公開欄位與 OpenAPI schema 沒有說明一般金額欄位的幣別或倍率；候選的 `source_api_unit_explicit`、`formal_unit_contract_accepted`、`owner_acceptance`、`formal_apply_authorized`、`historical_pit_credit` 與 `auto_apply` 都是 `false`。機械 preview 的 `ready_for_apply=true` 只表示資料列可解析且沒有機械診斷，不代表 source/unit contract 已接受，也不授權正式寫入。

捕獲的兩份季度 Swagger 目錄列出 12 個上市 income/balance routes 與 12 個上櫃 routes，適合設計每週一次全 route 研究採集，留下該週最新可用季度的 prospective snapshot。每週 capture 是觀測頻率，不代表數值屬於當週季度；也不會回填歷史 PIT。這只是 API metadata 證據：本次沒有取得任何季度數值回應，因此實際回傳格式、公司覆蓋、key uniqueness、跨產業重複、空回應語意與金額單位均未驗證。第一輪 scope 不含公開發行／興櫃、現金流量表或權益變動表。

## 月營收來源與單位採用缺口

2026-08 月營收研究候選使用兩個官方 OpenAPI 回應，合併 1,978 列（TWSE 1,086、TPEx 892）。兩個來源皆 HTTP 200：

| Venue | Exact endpoint | Raw bytes／SHA-256 | Response complete（UTC） |
|---|---|---|---|
| TWSE | `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` | 606,355／`83480ff80b337e936821b45e2cef1c2a48ba92f112fb3e31027501810e8bccf5` | `2026-09-30T22:17:45.393277Z` |
| TPEx | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O` | 496,547／`f00e3fdd7060db0db943b79dc53d732df940d038ef208a1b075363e06660bd92` | `2026-09-30T22:17:48.275856Z` |

Candidate completed at `2026-09-30T22:17:48.394676Z`. Its snapshot SHA-256 is `147d1695f0e9241d9ca6a2fc47ca7535a8280671dd16356facf248fb1540ce63`, scope manifest SHA-256 `7b3aadf6eb2d152e4ffc6781415c9a822b0cb106d75bc27438d0878506893605`, and candidate manifest SHA-256 `3db932cbacd6ea3a7c03b1c957cf1cf97c72efca3e536f07491f57ecfadd7a77`. 原始回應、完整 period/scope、availability 與 readback 位於：

`output/fundamental_research_candidates/20260930T221743808050Z-4148c176e04b4b958b305ed9e971b987/`

來源頁可確認資料由主管機關提供、開放資料授權及欄位名稱，但沒有一般營收金額的 TWD／千元／元單位契約：[TWSE 月營收資料集](https://data.gov.tw/dataset/18420)、[TPEx 月營收資料集](https://data.gov.tw/dataset/56510)、[政府資料開放授權條款](https://data.gov.tw/license)。TWSE／TPEx response 是實際保存的 HTTP entity bytes；source row 數值不能反過來證明單位。TWSE 頁列「每1年」更新頻率、TPEx 頁列「每月」；兩者也不應當成逐筆公告時間。

Repository 的 [MOPS HTML 路徑](../../data_module/current_fundamental_snapshots.py#L30) 將來源金額解讀為千元並轉為元，但這是不同來源／格式的既有契約，不能套用到 OpenAPI。正式欄位 `fundamental_monthly_revenues.revenue` 是 `TEXT`，schema 沒有 unit 欄；backfill 正規化直接複製 source revenue 字串，未做尺度轉換。可核對 [monthly_revenue_backfill.py](../../data_module/monthly_revenue_backfill.py#L85) 的 `ready_for_apply` 與 `formal_apply_eligible` 分離、[writer gate](../../data_module/monthly_revenue_backfill.py#L367) 在 backup/database 之前拒絕未接受來源，以及 [schema](../../data_module/fundamental_schema.py#L51)。[負向測試](../../tests/test_monthly_revenue_backfill.py#L856) 證明 research-only OpenAPI candidate 不建立 backup、不開啟 DB，且 DB hash 不變；legacy MOPS route 的相容測試在同測試檔約第 836 行。

獨立 no-write plan preview 有 0 diagnostics、1,978 candidate rows、預計新增 1,978、合併後 3,810、conflict 0，`ready_for_apply=true` 但 `formal_apply_eligible=false`。preview 前後正式資料 mapping hash 均為 `ea6c0c5651e94f605dc10ac8f4cc36803193e8d3aad0db63a7b9f31d72728f7e`；沒有套用。

目前正式採用仍缺以下可由來源端核實並 hash-bind 到候選的證據：

- TWSE 與 TPEx 各營收數值欄的幣別、尺度及有無例外；不得從相近資料、舊 baseline 的數值相同或 MOPS HTML 單位推論。
- 當月營收、去年同月、上月等數值欄的 period／比較定義；百分比欄位是比例或百分點、空字串／破折號／負值的正式語意。
- 可追溯的來源修訂／更正政策與 availability rule；不能用 API 擷取日冒充歷史發布時間。此候選只按實際 capture 與保守 date-only Taipei 次日規則標記 available date `2026-10-02`，不授予 2026-08 的歷史 PIT credit。
- source acceptance artifact 必須綁定 candidate ID 與 raw、snapshot、scope、availability、manifest 各自 hash，列出 endpoint、欄位 mapping、單位／精度、null 規則、來源版本及適用期間。既有可信任審閱／pin 流程應提供明確人類採納證據；JSON 自述 `owner_acceptance=true` 或單獨 `--confirm` 不能替代來源單位證據。

目前沒有安全、可執行的正式 apply command。即使 mechanical plan 顯示 `ready_for_apply=true`，candidate 仍為 `formal_apply_eligible=false`，writer 會在建立 backup 或連接正式 DB 前拒絕。完成上述來源證據及 hash-bound acceptance 後，才可重新產生 no-write exact diff；另行審核後的 apply 應記錄唯一 backup/journal、apply 前後 DB hash、預期新增／衝突筆數與 readback。任何回復以已驗證一致的 backup 還原並比對 DB hash；不得回填無有效 availability 證據的歷史日。

## OpenAPI metadata 收據

只 GET 兩個由官方目錄確認的 Swagger metadata URLs，30 秒 timeout、8 MiB response cap、`Accept-Encoding: identity`，原件與收據 create-only 保存在 ignored QA output。各 URL 首次 sandbox 嘗試均被 Windows 拒絕，已留下完整失敗收據；之後只對同一官方 metadata URL 作一次目的限定的升權重試。失敗收據沒有 HTTP status 或 body，不應寫成來源端 HTTP 403。

| 官方 metadata URL | 結果／原件 | 完成時間（UTC） | Readback |
|---|---|---|---|
| `https://openapi.twse.com.tw/v1/swagger.json` | run01：WinError 10013；run02：HTTP 200，309,960 bytes；SHA-256 `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`；raw 與 receipt 在 `output/qa/twse_openapi_catalog_metadata_20261001_run02/` | run02 start `2026-09-30T22:42:35.027180Z`，complete `2026-09-30T22:42:36.494611Z` | JSON parse 成功，重算 raw SHA 與 receipt 一致；ETag `"6a9a6562-4bac8"` |
| `https://www.tpex.org.tw/openapi/swagger.json` | run01：WinError 10013；run02：HTTP 200，476,923 bytes；SHA-256 `05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e`；raw 與 receipt 在 `output/qa/tpex_openapi_catalog_metadata_20261001_run02/` | run02 start `2026-09-30T22:38:51.226937Z`，complete `2026-09-30T22:38:52.420371Z` | JSON parse 成功，重算 raw SHA 與 receipt 一致；ETag `"6a44c791-746fb"` |

TWSE Swagger 為 2.0，host `openapi.twse.com.tw`、base path `/v1`、143 paths。TPEx OAS 為 3.0.0，server `https://www.tpex.org.tw/openapi/v1`、225 paths／225 component schemas。下表是首輪上市與上櫃的 24 個精確 GET targets；六種業別為 `basi` 金融業、`bd` 證券期貨業、`ci` 一般業、`fh` 金控業、`ins` 保險業、`mim` 異業。

### TWSE 上市：綜合損益表與資產負債表

| 表別 | 業別 | Exact URL |
|---|---|---|
| 綜合損益 | 金融業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_basi` |
| 綜合損益 | 證券期貨業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_bd` |
| 綜合損益 | 一般業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci` |
| 綜合損益 | 金控業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_fh` |
| 綜合損益 | 保險業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ins` |
| 綜合損益 | 異業 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_mim` |
| 資產負債 | 金融業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_basi` |
| 資產負債 | 證券期貨業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_bd` |
| 資產負債 | 一般業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci` |
| 資產負債 | 金控業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_fh` |
| 資產負債 | 保險業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ins` |
| 資產負債 | 異業 | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_mim` |

### TPEx 上櫃：綜合損益表與資產負債表

| 表別 | 業別 | Exact URL |
|---|---|---|
| 綜合損益 | 金融業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_basi` |
| 綜合損益 | 證券期貨業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_bd` |
| 綜合損益 | 一般業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci` |
| 綜合損益 | 金控業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_fh` |
| 綜合損益 | 保險業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ins` |
| 綜合損益 | 異業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_mim` |
| 資產負債 | 金融業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_basi` |
| 資產負債 | 證券期貨業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_bd` |
| 資產負債 | 一般業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_ci` |
| 資產負債 | 金控業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_fh` |
| 資產負債 | 保險業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_ins` |
| 資產負債 | 異業 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_mim` |

## Catalog schema 限制與 research collector 建議

兩份 OpenAPI 對以上回應宣告 object schema；字段為 string、沒有 required fields，也沒有 query parameters。各類 schema property counts 如下；metadata 未證明實際回應是單筆物件或完整公司清單，更未證明每個公司恰有一列或每個業別互斥。

| 業別 | TWSE income | TPEx income | TWSE balance | TPEx balance |
|---|---:|---:|---:|---:|
| basi 金融業 | 25 | 25 | 64 | 64 |
| bd 證券期貨業 | 25 | 25 | 26 | 26 |
| ci 一般業 | 33 | 33 | 26 | 26 |
| fh 金控業 | 25 | 25 | 61 | 61 |
| ins 保險業 | 26 | 26 | 57 | 57* |
| mim 異業 | 21 | 21 | 25 | 25* |

`*` TPEx `/mopsfin_t187ap07_O_ins` 與 `/mopsfin_t187ap07_O_mim` 兩條實際 route 的 response `$ref` 分別指向 `#/components/schemas/mopsfin_t187ap07_O_insA` 與 `#/components/schemas/mopsfin_t187ap07_O_mimA`。這是 schema component reference，不是建議改抓 `/..._insA`、`/..._mimA` route；catalog 有 insA/mimA components、沒有同名非 A component，對應 A schemas 分別有 57 與 25 個欄位。不能靜默當成 endpoint 本身已具備正確 schema。collector 必須將這兩條標成 schema-reference anomaly，按保存的 ref 驗證，並以實際數值 response 確認鍵值；必要時另行查明官方文件，不可自行把 endpoint 改名或換成 A sibling route。

數值收集前不得推定 response array 包裝、period keys、公司覆蓋或空集合代表有效無資料。capture readback 必須以實際 JSON 驗證 schema、key uniqueness、company/market 對應、period、重複與缺漏，並保留完整 HTTP raw bytes、headers、hash、response completion time 與逐 endpoint receipt。

Swagger 對 EPS 明列 `元`，資產負債表中若干股數欄明列 `股`；這些局部標註不能推廣至一般金額欄位。一般營業／損益／資產負債金額的幣別與 scale 未由目錄證實，OpenAPI schema 以 string 保存也沒有補足此缺口。故第一輪只能是 source research，不能升為 formal unit contract。

原始設計提案曾列每個 run 26 GET、numeric raw 192 MiB 加 catalog 16 MiB（合計 208 MiB）。目前已實作的 collector budget 以 [module constants](../../data_module/mops_quarterly_openapi_research_capture.py#L33) 為準：每個 encoded entity 與 decoded body 各 8 MiB、aggregate raw 256 MiB、preview 128 MiB、metadata 16 MiB；這些是分項上限，不能合併誤稱為 208 MiB 實際硬上限。每週一輪先 GET 兩份 catalog，再對 24 個 numeric targets 各 GET 一次，至多 26 GET、0 retry。Connect/read timeout 各 30 秒；60 秒/request 與 900 秒/run elapsed gates 在阻塞 read 返回後檢查，不是硬牆鐘中止。失敗路徑保留狀態並令本輪不完整；只有兩份 catalog 與每個市場×業別×表別均成功，且 key/period/scope 驗證通過，才建立該週完整研究候選；部分成功不得標記 full-market complete。10/1 實際只跑過一次 live candidate，沒有自然 weekly Task 同次 child receipt 驗收，見[季度 OpenAPI live capture QA](SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)。

Captured catalogs 還列出 TWSE 公發 `_X`、TPEx 興櫃 `_U` 財報路徑，未列入上述上市／上櫃 24 routes，也尚未做 scope 核對。TPEx Swagger 還列出六條 `mopsfin_t187ap06_O_*A`「財報資訊」income siblings；因可能有重疊／不同格式，首輪不納入，需先做單獨 schema、key、scope 比較。兩份被保存 catalog 的路徑標題搜尋未找到明稱「現金流量」或「權益變動」的 t187ap report route；這只能說本次所查 catalog 未證實該兩表，不能推斷其他 portal／文件管道不存在。現金流量與權益變動應維持明確 scope gap，不能用 income/balance 完成度代替。

## QA 範圍與未執行事項

- 讀回並 SHA-256 驗證兩份 200 response 原件與 receipt 相符；成功 catalog 可 JSON parse。
- 兩個首次 WinError 10013 失敗 receipt 均保留，沒有把環境拒絕誤報成來源 HTTP status。
- 原 catalog／unit acceptance review 只解析已保存 Swagger JSON、月營收 candidate/manifest 與 repository source/tests，未呼叫 quarterly numeric endpoints；之後的 numeric capture 由獨立 collector route 執行，請見後續 live QA。
- 未執行正式 apply、Task、Quick runner 或 DB writer；未改既有 raw/candidate/DB、未訓練或更動任何 formal pointer。

## 2026-10-01 官方 metadata 頁面補充：欄位與單位尚未形成接受契約

另有限度讀取四個官方政府資料集 metadata 頁面，以確認公開欄名與更新頻率；這不是完整 API unit contract 檢索，也沒有取得 numeric response：

| 資料集 | 官方頁面 | 可直接確認的欄位／頻率 | 不能據此確認 |
|---|---|---|---|
| TWSE 月營收 | [data.gov.tw/dataset/18420](https://data.gov.tw/dataset/18420) | 年月、出表日期與營收相關欄位；頁面標示每年更新 | 一般金額欄的幣別／倍率、出表日期代表首次公告或修訂、每列首次可得時間 |
| TPEx 月營收 | [data.gov.tw/dataset/56510](https://data.gov.tw/dataset/56510) | 年月、出表日期與營收相關欄位；頁面標示每月更新 | 一般金額欄的幣別／倍率、出表日期代表首次公告或修訂、每列首次可得時間 |
| TWSE 季報一般業 metadata | [data.gov.tw/dataset/91998](https://data.gov.tw/dataset/91998) | 年度、季別、公司、EPS（元）；每 3 個月更新 | 一般業 income statement 金額單位、balance-specific 欄位與單位、合併／個別 basis、逐筆首次／更正公告 available-at、更新頻率是否等同每筆公告時間 |
| TPEx 季報一般業 metadata | [data.gov.tw/dataset/94853](https://data.gov.tw/dataset/94853) | 年度、季別、公司、EPS（元）；每 3 個月更新 | 一般業 income statement 金額單位、balance-specific 欄位與單位、合併／個別 basis、逐筆首次／更正公告 available-at、更新頻率是否等同每筆公告時間 |

此處只記錄四個已檢 metadata 頁的證據，不推論所有官方財報來源都缺單位。季度 metadata 查證限一般業 income statement 頁，沒有檢查 balance-specific metadata page；因此 balance 欄、income/balance 的合併／個別 basis 以及一般金額單位仍未證實。更新頻率不等同個別記錄的公開時間；EPS「元」也不能推廣成其他金額欄位的單位。月營收與季報 OpenAPI 的正式 unit acceptance 仍為 false。要接受來源，仍需把實際 endpoint、response header/schema/sample、數值欄位和來源修訂身份綁到候選 hashes，核實單位、basis、精度、缺值語意與可得時間；現階段不能靠一般 metadata 頁或空泛 owner 同意完成該契約。

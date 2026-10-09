# 產業強弱與產業→個股決策旅程 QA 證據（2026-09-14）

## 結論與範圍

本輪完成的是 Daily Decision Desk 的唯讀 current-research 產業強弱讀模型與 UI
下鑽，不是 V5、正式 PIT 產業資料、ML 特徵或投資有效性證明。使用者可在市場總覽、
強勢產業、弱勢產業查看同一份 service DTO，依明確選取的代表股開啟既有個股研究；
不會新增資料庫、修改觀察清單、寫入 watchlist、啟用 Formal publisher／clock 或產生
機率與買賣建議。

## 來源與資料身份

| 層 | 實際來源／身份 | 本輪判讀 |
|---|---|---|
| 公司分類 | `companies.csv`，觀測日 2026-08-11，檔案可得時間 2026-08-11 08:13:44 | current registry；不是歷史 PIT membership |
| 產業指數 | SQLite `industry_indices`，截至請求日前可得列 | 只接受明確白名單的 37 個純產業指數；不把產品型指數冒充產業 |
| 市場基準／session | SQLite `market_indices` 的精確 `TAIEX` | 固定以 TAIEX session 與報酬作比較；找不到 TAIEX 時 fail-closed，不任意換 benchmark |
| 個股價格 | SQLite `daily_prices` | 只讀請求日以前、同一組 TAIEX session；缺價／停牌不補 0 |
| 映射契約 | `INDUSTRY_CATEGORY_TO_INDEX`、`tw-industry-explicit-map.v1` | 類別→指數為顯式 mapping；同層級 ranking，不混排父層 aggregate 與 leaf |

SQLite provider 使用 `mode=ro` 與 `PRAGMA query_only=ON`。日期查詢使用既有
`idx_market_indices_date`、`idx_daily_prices_date`、`idx_industry_indices_date` 可界定的
日期鍵；沒有建立平行 DB 或寫入正式資料。

## 映射、層級與排除規則

- 37 個白名單是目前資料中可辨識的純產業指數。`金融類日報酬兩倍指數`、
  `金融類日報酬反向一倍指數`、`電子類兩倍槓桿指數`、`電子類反向指數`，以及其餘
  產品／策略／總報酬型名稱不進入純產業排名。
- `電子工業類指數`、`化學生技醫療類指數`、`塑膠化工類指數`、`機電類指數`、
  `水泥窯製類指數` 是父層 aggregate；與 leaf 分開標示、分開排名，不宣稱成互斥
  的同級產業。此輪 registry 可明確對齊 `化學生技醫療` aggregate；其餘父層若沒有
  exact current category，保留 `unmapped_index_names` 診斷。
- current `companies.csv` 的 `存託憑證`、`文化創意業`、`農業科技` 沒有這份顯式
  map，保留 `unmapped_industry_categories`；不以模糊字串猜配。
- Ranking scope 是 `within_industry_level`。所有 component coverage 的分母是
  current、unambiguous、TWSE-aligned registry members；TPEX／興櫃不是悄悄混入或
  轉為 0，而是以 `market_scope_excluded_code_count` 與 warning 揭露。
- `mapping_mode=current_research_only`、`historical_pit_eligible=false`。mapping
  的觀測／可得資訊只在其已知 current source date 適用；不把 2026-08-11 registry
  回填或冒充更早日期的 historical membership。

## 計算契約與 look-ahead 自查

1. 請求日先裁切到不晚於請求日的最後 TAIEX session；若請求日不是 session，明示
   `industry_strength_as_of_fallback:<date>`。
2. 5 日與 20 日視窗都取同一份 TAIEX session anchor 的精確端點（當日與往前第
   5／20 個 session），不是用「某產業有資料的日期」延伸視窗。
3. 產業指數與 TAIEX 報酬在 service 邊界以 `Decimal` 計算、輸出整數 basis points；
   `excess_*_bp = industry_return_*_bp - TAIEX_return_*_bp`。日價代表股也只在
   完整可取得的同一窗口計入，缺價／停牌／不足窗口保持缺值並降低 coverage。
4. 決策日、產業指數、TAIEX、個股價格、registry mapping 都以 `<= as_of_date`
   凍結；沒有讀取未來列、沒有用未來 membership／標準化或 benchmark。這是
   current-research presentation，不是回測或正式 ML eligibility。

## 2026-09-14 真實唯讀 smoke

執行 `IndustryStrengthService(TWStockConfig()).build_industry_strength(date(2026, 9, 14))`
的結果：

| 指標 | 結果 |
|---|---:|
| 最後有效資料日 | 2026-09-14 |
| 產業列 | 32（leaf 與可明確對齊的 aggregate 分開） |
| 5 日可排名列 | 32 |
| 20 日可排名列 | 32 |
| current registry rows／unique codes | 2,343／2,343 |
| TWSE current-research 映射 | 1,084 |
| TPEX／興櫃 scope 排除 | 1,208 |
| historical PIT eligible | 0 |
| current unmapped categories | 3 |
| observed pure index count | 37 |
| 個股缺價／停牌或窗口不足（5／20 日） | 11／12 |
| 品質 | `DEGRADED`（有 current／scope／PIT 警告） |

20 日 leaf 排名的可追溯樣本（報酬／相對 TAIEX，單位 bp）包括：

- 領先：金融保險 `1486／1485`、油電燃氣業 `1440／1439`、塑膠工業
  `1402／1401`、光電業 `571／570`、航運業 `390／389`。
- 落後：運動休閒 `-514／-515`、綠能環保 `-519／-520`、電機機械
  `-609／-610`、生技醫療業 `-912／-913`、電子零組件業 `-981／-982`。
- 可明確對齊的 aggregate `化學生技醫療` 為 `-725／-726`；其他父層缺 exact
  current category 時維持 unmapped，不以 leaf 推估。

代表股由同一產業的 current TWSE registry member、可用價格與窗口 coverage
排序產生；例如金融保險首列代表股為 `2883`，油電燃氣業為 `6505`。UI 不固定
隱式開啟第一檔：排序後先選產業，再從代表股下拉選單明確選取任一檔，按按鈕才
建立既有 `ResearchStockContextDTO`。來源、資料日、mapping version 會隨 context
保留，沒有 watchlist write intent。

## 驗證證據

已完成的 focused checks：

- `tests/test_sector_rotation_service.py`：純產業／槓桿反向排除、aggregate 層級、
  固定 5／20 session、strict TAIEX、TWSE coverage、duplicate membership、未來日與
  current mapping 可得日保護（15 passed）。
- `tests/test_decision_desk_snapshot_repository.py`：nested industry strength DTO
  序列化／重載。
- `tests/test_ui_qt_weak_market_views.py`、`tests/test_ui_qt_decision_desk_view.py`：
  排序後選取列與第二檔代表股仍傳遞正確 code／source／date；雙擊只選列、不隱式開
  第一檔；市場總覽代表股按鈕走既有研究 context，且不寫 watchlist（29 passed）。
- `tests/test_ui_qt_research_context_status.py` 與 `tests/test_ui_qt_stock_research_report.py`：
  session store／status strip／個股研究報告保留 source／mapping version（合併研究
  context route 39 passed）。
- 真實 provider smoke：上述 32 rows、coverage、unmapped／scope／PIT diagnostics
  與 top／bottom rows；沒有 DB／watchlist／ML 寫入。
- 正常桌面寬度的實際 Qt render：`1440×860`、預設細分產業 31 rows、11 個主要可見欄、
  首列代表股選取器 3 檔；按鈕明示「近5交易日／近20交易日」，層級可切換「綜合類別」；manifest 與 PNG 位於
  `C:/Users/archi/.codex/visualizations/2026/09/15/01a0a278-54ae-72b3-bae7-ada2025777cb/industry_ui_smoke/`。

## 尚未證明與下一個 Gate

- 尚無授權的 historical PIT industry membership／available-time export，因此不能
  用 current registry 進行歷史回測、正式 ML feature 或 Formal OOS；補齊後需另建
  versioned mapping、effective／available interval 與 backfill isolation 驗收。
- `companies.csv` 的 TPEX／興櫃成分目前不在這個 TAIEX／TWSE comparable scope；若要
  擴大市場範圍，必須先定義對應市場 benchmark、index membership 與 coverage 分母，
  不能在本服務任意 fallback。
- 2026-09-14 的 `DEGRADED` 是資料身份／coverage／PIT 限制，不是產業看空或上漲
  機率；此 view 只供人工研究排序，不授予 Advice、Portfolio、scheduler 或 broker
  權限。

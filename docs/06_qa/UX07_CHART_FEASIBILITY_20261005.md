# UX07 圖表可行性調查（2026-10-05）

基線 `a52ccd276403288553330f4681c4cec7d14ea2bd`；沿唯一原計畫 §7／stage4。這是方案調查與下一批建議，沒有選定產品方案、完成 UX08 圖表整合或正式 JSON 遷移。最多兩位 LunaMax 分別核對官方資料與 repo，Sol 整合。全程背景、唯讀；沒有安裝依賴、接受條款、帳號／付費、外站嵌入、Native、producer、ML 或 push。

## 三方案與可用基線

| 項目 | TradingView 外部連結 | Hosted Widgets | Lightweight Charts＋本機資料 | 保留現有原生圖 |
|---|---|---|---|---|
| 行情／同源 | TradingView 網站；外部參考 | TradingView 託管資料，不能接本機行情 | 自己供資料；庫沒有市場資料或內建指標 | 沿現有本機輸入；不是所有現圖已有研究身份 |
| 台股覆蓋 | 主站表列 TWSE／TPEx；逐商品映射待驗 | 亞太表列 TPEx 延遲、未列 TWSE；逐商品／元件待驗 | 取決於已接受本機來源，庫不保證交易所覆蓋 | 同本機資料來源與現圖能力 |
| 切股／縮放／歷史 cutoff | 網站操作；不能承諾固定本機截止日 | 設定範圍受官方限制；不能作本機歷史證據 | 可做；應用端先限制資料和 markers，切股／回呼另驗 | 現有能力作基線，缺少部分互動契約 |
| 標記／精確表格 | 本機私有事件留本機 | 不傳帳本／備註／收藏；不能取回指標做本地表 | API 可做 markers／十字線；表格及精確值由應用呈現 | 可保留本機數字表；不冒稱已有全部 markers |
| 離線／失敗 | 無網路不可用；回本機 | 無網路不可用；回本機，不換同名商品 | 固定本地 HTML／JS 資產才可離線；renderer 故障回原生 | 無 WebEngine 的現有本機路徑作 fallback |
| 包裝／效能 | 不新增內嵌 browser；外部 browser 成本另計 | 若內嵌須 WebEngine、網路與 renderer；無本機量測 | 官方約45KB是 library 宣傳尺寸，非桌面增量；Qt／資產／子程序另計 | 現況已存在，新增成本可最小；效能仍按同資料測 |
| 授權／署名 | 網站與資料權限沿使用條件；不取得資料再散布 | 保留官方品牌／attribution；桌面散布適用條件未確認 | Apache2.0，鎖版附 LICENSE／NOTICE／歸屬與連結；Qt／Chromium另核對 | 既有依賴沿自身授權；本批未改變 |

官方資料於 **2026-10-05** 查閱：[主站市場覆蓋](https://tw.tradingview.com/data-coverage/)、[Widget 亞太清單](https://www.tradingview.com/widget-docs/markets/asia-pacific/)、[Widget 資料 FAQ](https://www.tradingview.com/widget-docs/faq/data/)、[Widget 一般 FAQ／署名](https://www.tradingview.com/widget-docs/faq/general/)。網站能看不代表 widget 能嵌；TPEx 清單也不代表全商品／全週期可用。個人付費方案不改 Widget 行情資格；本批不承諾即時台股。

Lightweight Charts 無行情、無內建指標，直接接呼叫端資料；官方比較頁的約45KB沒有定義本地 installer 增量。本機效能不能由此推定。[產品比較](https://www.tradingview.com/charting-library-docs/latest/product-comparison/)、[LICENSE](https://github.com/tradingview/lightweight-charts/blob/master/LICENSE)、[NOTICE](https://github.com/tradingview/lightweight-charts/blob/master/NOTICE)、[官方 Repo 的歸屬要求](https://github.com/tradingview/lightweight-charts)。當前公開 API 有 OHLC series、markers、十字線／時間軸與 panes，採用時仍須固定 release／SHA 和其對應 API／授權；本批未下載 bundle。[Series API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi)、[Markers](https://tradingview.github.io/lightweight-charts/tutorials/how_to/series-markers)、[Chart API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi)、[Time Scale API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ITimeScaleApi)。

Advanced Charts 僅後續備選：官方免費 library 的資格不包含個人／興趣／學習／測試用途，不能把個人桌面工具視為已取得授權。[官方 Libraries FAQ](https://www.tradingview.com/free-charting-libraries/)。本批沒有申請或接受其條款。

## Repo 邊界與缺件

已安裝 Python3.11.9、PySide6／Qt6.10.1，WebEngine module spec 存在；沒有啟動 Qt／renderer。匹配 WebEngine 名稱的120個已裝檔合計356,540,252 B（約340.02 MiB，包含 debug pak），這個檔名集合不是全部依賴、installer大小或新增部署量。Qt官方6.10系列文檔目前頁面是6.10.3，與已裝patch分開；封裝還需 helper／resources／plugins 與Qt及Chromium授權，不因LWC的Apache2.0而豁免。[Qt部署](https://doc.qt.io/qt-6.10/qtwebengine-deploying.html)、[Qt／Chromium授權](https://doc.qt.io/qt-6.10/qtwebengine-licensing.html)（2026-10-05）。

tracked repo未找到LWC本地bundle，`ui_qt`無JS檔、requirements未宣告。WebEngine能執行inline HTML／JS，不代表能用不存在的LWC資產；本批不安裝／下載，因此沒有LWC原型或量測結果。原生個股圖接受 `StockPricePointDTO`，OHLC完整才畫K、缺量不補柱、價格座標沿Decimal；目前hover tooltip可用，尚無縮放／平移／指標／事件交易標記。圖和價格頁表格共用 `report.price_points`。

價格服務的唯讀 `daily_prices` 查詢依個股及 `date<=cutoff` 取最近120筆。DTO有data_date／source_id／逐列source_snapshot_hash，但service沒有填available_at，且明示缺可得時間；日期截斷不能授予historical PIT。轉新renderer要保留這個限制，不用更好看的圖假裝當時可得。

| 現有入口（上述基線） | 已有契約／下一批邊界 |
|---|---|
| `ui_qt/widgets/fast_chart_widget.py:25,153,327` | 可選 WebEngine；factory 預設 prefer_fast，缺 WebEngine 回 Matplotlib。內嵌 HTML／Canvas／JS，沒有外部 CDN；用於回測資產曲線、回撤、報酬與持有期分布，並非個股 OHLC 圖。 |
| `ui_qt/widgets/chart_payloads.py:9`；`ui_qt/views/backtest/result_panel.py:107` | pandas／數值集合投影及 lazy 回測圖；沒有 StockPricePointDTO／OHLC 輸入契約。下一批新增個股 adapter，不直接把回測 payload 當價格證據。 |
| `ui_qt/views/stock_research_report_view.py:148,259,281,1918` | 原生 StockPriceChartWidget、OHLC／缺值模式、Decimal 座標及 report.price_points 圖表／表格共用入口。 |
| `ui_qt/views/stock_research_report_view.py:1188,1311` | 切股增加 request identity、取消舊 worker；舊商品／request 結果拒收。Web renderer 需延續相同失效邊界。 |
| `app_module/stock_research_report_dtos.py:104` | frozen StockPricePointDTO：Decimal 價格、整數量、data_date、available_at、source_id／snapshot hash；缺值不填造。 |
| `app_module/stock_research_report_service.py:189,927,998,3688` | 請求截止日、最多120筆查詢、缺 available_at 限制及逐列來源 hash。 |
| `docs/08_technical/UI_QT_CHART_RENDERING.md:12` | 現有 Matplotlib fallback 與渲染分層說明；未記載已整合 LWC。 |

依賴入口為 `requirements-runtime.txt:17` 的 PySide6 與 `requirements-py311-windows.constraints.txt:21` 的6.10.1固定版本。本批只查 module spec／檔案大小，沒有 renderer 首畫、切股或回收量測。

## 下一個小批次建議與待驗點

建議首版沿原計畫stage1–3保留現有原生個股圖與同源表；LWC＋本機資料是stage4主圖候選，外部連結是可選參考，Hosted Widgets待逐商品／桌面條件成立後再決定。這是推薦，沒有切換default。

下一批先做一個合成單商品、純本地、可替換renderer的隔離原型：

1. 父層決定允許核對／vendor官方standalone release，固定version／SHA、LICENSE／NOTICE與UI歸屬；不使用浮動CDN。
2. Application投影同一price／indicator owner：商品／交易所、頻率、幣別／復權、資料日、cutoff、source ID／hash、availability狀態、OHLCV、已有指標與有證據markers。JS只收白名單展示值，精確Decimal／整數原值留表；JS回值不進金融核心。
3. 日K＋量／無OHLC降收盤線／無量留缺值、十字線同步表、期間／縮放與選股；截止後資料與markers先在服務端排除，事後觀察另明示，不重算策略。
4. 只開一個按需詳細圖，切股／清除來源／取消／關閉使舊回呼失效；不給遠端Widget QWebChannel或file／SQL／Python能力。離線禁止遠端requests，renderer失敗保留原生路徑及同源表。
5. 以相同合成500／2000／10000 bars與不同marker密度核對cold/warm首畫、切股、縮放、JS bytes、父／renderer程序RSS與關閉回收；記錄原生基線及打包前後實體bytes。這些是下一批量測設計，沒有預先設合格數字或宣稱LWC比較快。

未知必須逐項關閉：TWSE／TPEx上市普通股、上櫃普通股、ETF、指數、新上市短歷史、停牌／缺交易日商品的**symbol＋指定Widget＋週期＋歷史深度**；名稱映射與失敗／離線fallback；Widget桌面散布條件；本地asset與Qt封裝；cutoff跨非交易日的線／marker錨定；精確表可複製／鍵盤替代；rapid切股與worker／renderer回收。若未授權vendor，仍能先完成無新依賴的DTO／來源／cutoff純契約切片，保留原生default。

## 正式 JSON 套用的獨立批准邊界

目前原 `D:\Min\Python\Project\FA_Data\output\watchlist\default.json` 為1948B，mtime_ns `1782189963018265100`；只查 metadata，沒有讀內容。新 target／marker／canonical 尚不存在。

| 正式步驟將使用／寫入的項目 | 路徑／影響 |
|---|---|
| source（保留） | `D:\Min\Python\Project\FA_Data\output\watchlist\default.json` |
| CLI 指定的新 DB 候選 | `D:\Min\Python\Project\FA_Data\output\watchlist\watchlists.v3-cow.sqlite`，必須不存在 |
| UI 明示升級的新 DB | 同資料夾 `watchlists.v3-cow-default-<唯一ID>.sqlite`，不覆蓋先前 target |
| conversion receipt | `<新DB>.cow-conversion.v1.json` |
| activation marker | `D:\Min\Python\Project\FA_Data\output\watchlist\default.json.cow-active.json` |
| 回復審計 | 同資料夾 `default.json.cow-rollback.<activation_id>.json`；保存模式／指標 metadata，不是另一份內容備份 |
| 短期鎖／stage | `default.json.cow-lock`；`<新DB>.cow-stage-<唯一ID>.sqlite` 及發布暫存，失敗保留交 owner |
| 設定入口 | `data_module/config.py` 的 `OUTPUT_ROOT`，一般 `ui_qt/main.py:336` 用 `TWStockConfig()`；不修改設定檔或 `.env` |
| 不建立的舊 canonical | `D:\Min\Python\Project\FA_Data\output\watchlist\watchlists.db` |

批准前確認實際 output_root／單一來源、writer 可用時段、當下中央容量及 D 槽寫入權限；正式 dry-run 尚未做，不能保證實際內容通過嚴格格式核驗。批准後才依既有 Manual dry-run→convert→preview→activate→新程序讀回。原 JSON bytes 保留，target 是完整 baseline＋之後的新 revision。

rollback 核對 marker／audit／receipt、source pin、target baseline 與容量後只切 marker 回 JSON；新 DB 新內容、雙來源與所有 audit 保留，不自動合併、不刪檔。回復後日常 JSON 保存可改 JSON；target 新內容仍獨立留存。來源或身份被外部改壞時具名拒絕，不強制還原。沒有修改正式 registry、排程、producer 或資料設定。PID39400／41588沒有原 owner 收據，保留未停止，不作 writer 已停止證據。操作與限制沿 [COW QA](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md) 及 [Manual](../07_guides/APPLICATION_MANUAL.md)。

## 驗證與文檔狀態

本批僅背景研究；沒有新 UI 或金融計算，無需重跑113個已接受 COW tests／全套回歸。原計畫只追加並保留原 bytes 前綴，這份調查不等於圖表整合完成。Raw 根 `output/qa/ux07_chart_feasibility_20261005/` 保存 metadata／查閱清單，按 Git 排除留本機；正式套用與 F1 例外仍未批准。

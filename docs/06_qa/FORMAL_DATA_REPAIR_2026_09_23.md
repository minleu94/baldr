# 正式資料修復與驗收（2026-09-23）

## 授權與範圍

使用者要求「把全部的修正都修正好」。本輪處理已確認的正式大盤 OHLC／成交股數／交易日問題、2026-05-20 價格修訂的相依技術指標與快取，以及日常更新／舊來源重新匯入造成的再污染。原始檔、舊模型、原研究資料和其他工作未提交變更保留；不修改 ML 的欄位／schema，不啟用模型或交易。

資料品質驗收與模型有效性分開：完成資料修復不代表模型優於基準。缺少真實歷史證據的值保持缺值，不製造歷史可得時間。

先前 v3 股票快照未包含本輪補回交易日／錯日排除，新的候選資料與模型必須另行建置和驗收，進度見[修復來源候選驗收](REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)。原 v3 版本保留供比較，不覆寫舊結果。

追加唯讀對照發現舊技指表複製的六個數值欄位仍有全表補值殘留：`最後揭示買價`／`買量`、`最後揭示賣價`／`賣量`、`本益比`、`漲跌價差`。run02 日價與技指 5,260,667 個共同 key 中，1,099,011 列至少一欄不同；買量與賣量各有 1,041,382 個來源 NULL 卻被技指複本填值。該範圍是衍生欄位對照，不是新增日價修訂。20 個因果指標 staging 完成後，還須另行核對／同步這六欄；原始日價、已重算指標與其他欄位保持各自來源與驗收邊界。範圍證據為本機 `technical_raw_alias_scope_run02.json`，尚未視為發布完成。

## 執行前回滾清單

| 檔案／資料 | 變更類型 | 預計變更 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `data_module/data_loader.py`、`data_processor.py` 與官方市場解析共用模組 | 修改／新增 | 統一官方 OHLC／成交股數，來源不足拒絕發布 | 對本輪獨立 commit 執行 `git revert <commit>` | 回復舊程式會重新引入錯誤來源；先停止相關更新 |
| 日常價格匯入與技術計算入口及 focused tests | 修改／新增 | 阻止過期 raw 覆蓋修訂價格，固定完整因果前綴 | 對本輪獨立 commit 執行 `git revert <commit>` | 回復可能恢復再污染，須同時停用舊更新入口 |
| `scripts/repair_formal_market_data.py` 與 tests | 新增 | 來源 hash 核對、dry-run、備份、逐列套用／回復 | 使用新工具 `--rollback <receipt-dir> --confirm repair-formal-market-data`；程式以 `git revert <commit>` 回復 | 僅當欄位仍等於 receipt after 值時回復；後續漂移拒絕 |
| 正式 `market_indices` 與 `meta_data/market_index.csv` | 受控修訂 | 以驗證官方月報更新 TAIEX 指定日期，錯誤交易日留存於備份／receipt | 逐列 receipt rollback；不以整庫覆蓋其他後續資料 | SQLite／CSV 跨儲存體須 journal、鎖與中斷恢復 |
| 正式 `technical_indicators`、既有技術／整合快取 | 受控修訂 | 正確價格完整前綴重算 20 指標，不補缺價；逐股 staging、彙總串流 | `scripts/repair_formal_technical_data.py --rollback --receipt-dir <dir> --confirm repair-formal-technical-data` | 僅在完整技指表仍等於本輪 after fingerprint，且日價未變動時回復；CSV before／after hash 逐檔核對；其他表不回復 |
| 正式技指表與技術 CSV 的六個原始欄位複本 | 受控修訂 | 買賣價／量、本益比、漲跌價差依同日權威日價回復原值與 NULL；其餘欄位不變 | `scripts/repair_formal_technical_raw_aliases.py --rollback --receipt-dir <dir> --expected-manifest-hash <hash> --confirm repair-formal-technical-raw-aliases` | 必須先於 20 指標與來源修復回滾；完整檢查來源、備份與全部 CSV 狀態後才修改，後續漂移拒絕 |
| `daily_prices` 九個完全缺漏交易日 | 受控新增 | 以實際封存的 TWSE／TPEx 報表補回既有股票範圍與四碼證券共 14,869 列；保留官方空值、不修改原始日檔 | `scripts/repair_historical_sessions.py --rollback --plan <plan.json> --expected-plan-hash <hash> --receipt-dir <dir> --confirm repair-historical-sessions` | 先回復相依技術指標；完整欄位／來源／備份任一漂移即拒絕 |
| 歷史交易日與市場修訂讀取／重匯 gate | 新增 | 新來源僅以真正取得時鐘記錄；舊檔不能清掉新核驗來源 | 回復來源後才回復本輪程式；保留歷史 receipt | 不將資料修訂冒充原決策當時已知，也不自動晉升模型 |
| 官方無行情的錯日紀錄 | 受控排除 | 三個完整休市日共 2,888 列，以及 5/20 額外 54 個 key；從正式價格／相依技指與衍生 CSV 排除，原值與原始檔保留 | `scripts/repair_excluded_daily_prices.py` 的逐列回復；先回復後續技指／快取發布 | 只依雙市場完整官方回應與已核驗大盤月報判定；非任意刪除缺報價列；後續漂移拒絕回復 |

回滾前先停止本輪更新 writer，檢查 `git status --short` 與 receipt 的來源／before／after hash，再只回復本輪指定欄位或 commit；不清空 working tree。回滾後核對 DB／CSV 與未修改列，重跑相關 focused tests。

## 驗證計畫

1. 唯讀確認 live SQLite schema、價格修訂 receipt、market source custody 與快取範圍。
2. 對官方報表缺失、跨月／跨日、close 不一致、單位錯誤、過期 raw 重匯、技術前綴與空價加回歸測試。
3. dry-run 產生 before／after、來源 hash 與完整回復清單；正式 apply 前再次核對。
4. 寫入後獨立唯讀比較全量本輪目標、未修改列／表和原始檔，驗證再次更新不再污染。
5. 按切片提交程式與可分享驗收文件；不提交 raw output、DB、備份或第三方重構變更。

## 執行狀態

大盤已於 `2026-09-23T21:05:20Z` 完成正式套用：官方 3,106 日期，補入 19 日期、移除查詢表中 2 個非交易日（before 留存備份）。九個週六 `20141227、20160130、20160604、20160910、20170218、20170603、20170930、20180331、20181222` 的全日個股缺漏，於 `2026-09-23T21:06:23Z` 補入雙市場共 14,869 列。379 列含官方缺 OHLC，其中 36 列仍有非零成交統計；這是原始報表的值，不能由成交量推定一定存在開高低收，也未填補缺價。

來源範圍是目前 `daily_prices` 已收錄的證券加四碼證券（含 0050），並非引進全部 ETF、權證等新商品 universe。未知商品保持原範圍，不擅自擴大模型輸入。新來源與回復檔案位於正式資料根目錄 `output/scheduled/`，不提交原始資料與大型備份。本文件後續補入套用與驗收結果。

| 正式 receipt | 計畫 SHA-256 | 狀態 |
|---|---|---|
| `formal_market_repair_receipts/20260923_run01/` | `2c490f8aa336f646e9570f05d2a0c46e68346b3b2ba55d8e2fa2049b3b756d86` | applied |
| `historical_session_repair_receipts/20260923_run01/` | `c97c3f85c42ec2ab14a0fa39473526e033578ea76a7559b9b186a5a06cb1e96c` | applied |
| `excluded_daily_price_repair_receipts/20260923_run01/` | `27a56f4dcec575d7b93c80353b6c0d6430f503013f2aae97e9a8eb0bea47d287` | applied，UTC 22:36:30；兩表各排除 2,942 列 |
| `formal_technical_repair_receipts/20260923_run01/` | immutable source `bb12ff98369415ee25c56e1cb05eaec020c9b2b32f5fffd43144f96473150f76` | 因發現錯日紀錄而停止，未發布 |

上表路徑皆相對於 `DATA_ROOT/output/scheduled/`。來源 captures 分別永久保存於同層 `formal_market_repair_sources/20260923_run01/` 與 `historical_session_repair_sources/20260923_run01/`，回復依賴來源及備份，不能把它們當作臨時 QA output 刪除。任一程序被中斷時只使用相同 receipt 的 `--resume`；不得改 hash 或建立假完成標記。

第一階段 baseline audit：868 檔、77,173 個 2026-05-20 起的既有 key；來源日價 4,340 欄核對正確，個股 CSV 中文 OHLCV 385,865 欄正確。與目前完整因果 kernel 相較，DB 尚有 7,515 個指標欄位、個股 CSV 7,279 個欄位不一致，包含先前修復白名單未含的 ATR，以及後續更新殘留；這些數字是修復前狀態。英文價格副本與 DB 幾乎全空的 alias 不當成新的來源價差。新重算會涵蓋完整前綴與 20 個既有指標，包含 MA／ATR／ADX，暖機 NaN 保留。

技指 run02 已於 `2026-09-24T01:28:12Z` 完成 5,331,231 列、2,210 份 CSV 正式套用，發布後技指 table hash 為 `374d44ba1b3ab82f67deddc74b6d8836166776489c84f1aac0895d5af2dadfc0`。獨立正式讀回通過：全量 20 個指標與已驗收重算相符，沒有缺 key、非目標欄位變更或 CSV hash 差異；SQLite quick_check 正常、排除 key 殘留及日曆 anti-join 皆為零。報告 SHA-256 為 `6841d7cbb4e0d366b653ef44b0d236e536671a4d18c9528321684d5725e19fc5`，封存於該 receipt 的 `validation/publication_readback/`。此為六欄複本追加修復前的完整技指發布版本。

每日快取於 `2026-09-24T01:58:08Z` 完成套用；獨立全量回讀核對 5,331,231 列、17 欄、3,106 日期（2014-01-02 至 2026-09-23），正式 CSV／sidecar bytes 與 staging 完全相同。CSV SHA-256 為 `6e9a4b342d0c0dd34443d11b9cab8f8738838bc248bc690d4e8497f6c494c437`，正式讀回報告為 `0cb50b8d6b474d825107af630415de1e6e10db40e1e88afbce2b8cd31184ad64`，證據保存在 `formal_daily_cache_receipts/20260923_run02/validation/publication_readback/`。

每日快取 prepare 檢查已修正全日與修訂名單的範圍混淆：5/20 的 1,954 列保留完整來源，868 個修訂 keys 仍逐值與完整性核驗，其餘 1,086 列不因不在修訂名單而丟棄。11 項快取 tests 通過，包含合法同日未修訂列與修訂 key 缺漏的正反例。獨立核驗器另以四組 fixture 檢查 staged／published 身分、精確 Decimal、NULL、官方缺報價 `--` 與千分位格式；無效文字不能轉成零或空值後通過。

## 六個原始欄位複本的追加修復

全量來源格式盤點為 5,331,231 列、47,240 個文字儲存格，僅出現在買價與賣價：官方 `--` 各 9,088／24,716 個，合法千分位數字各 5,337／8,099 個；其他四欄沒有文字，非法文字為零。`--` 表示沒有報價，衍生 numeric 欄位應為 NULL；來源日價及每日快取仍保留原始表示。`raw_alias_source_representation_scope_run02.json` 綁定 run02 source SHA，來源掃描前後 bytes 不變。

修復工具只修改六欄，完整核對日期／股票 key、原 20 指標與其他內容；發布前先建立全量可回復 preimage、2,210 份 CSV staging 與 audit。SQLite 六欄在單一交易中更新，CSV 保留逐檔備份／journal，恢復前重驗全部備份與正式檔案；來源、目標或證據漂移時停止。套用與最終讀回結果另於完成後登錄。

日常更新同步補強 DBManager、UpdateService 四個直接 SQL／技指發布入口與舊 CSV 遷移。省略六欄的增量資料只可從同 key 權威日價補齊；提供錯值則在寫入前拒絕。完整重建保留日價已收錄的五、六碼證券，舊版逐股計算器在修改 CSV 前即停止。完整替換及 CSV 遷移的全部 INSERT 共用一個交易，避免中途失敗留下空表或部分列。正常頁面讀取不執行全量驗證，來源查詢使用既有 key 索引與批次處理。

原始六欄／更新服務／發布與 DBManager focused route 為 171 passed；後續針對 CSV 尾欄截斷的 stage／audit 拒絕行為加兩個反例，raw repair／numeric 子集合 52 passed。五、六碼證券 E2E 確認 `1101B`、`2887Z1` 同時保留於個股 CSV、彙總 CSV 與 SQLite，未知代碼不擴張範圍。更新工作台 84 passed，更新頁 validator 25 passed／0 failed／4 skipped，全域 mypy 664 source files 通過；這些程式驗證不代替正式六欄發布後的全量讀回。

## 全市場交易日檢查追加發現

將全庫日價日期與已核驗的 3,106 個官方交易日交叉核對，另找到 `20160211` 894 列、`20241002` 922 列、`20250929` 1,072 列。三日的 TWSE 回應均明確為無符合資料，TPEx 回應的請求日／表內日正確、狀態成功、筆數為零；對應月份 FMTQIK 與 MI_5MINS_HIST 都沒有該交易日。這是可驗證的錯日紀錄，不是 OHLC 缺值的正常列。

5/20 原先沒有 canonical 的 54 列也完成追加核對：新擷取的完整 TWSE `ALL` 31,124 列與 TPEx 1,007 列均不含這些代碼；其 OHLCV 全部等於錯置的 2024-10-02，50 列還與 2017-12-18 完全相同，其餘包含多日重複的零成交列。不以重複值單獨判定刪除，而是以雙市場官方缺席、日期證據和 before rows 鎖定排除範圍。

八組官方 raw／receipt 已另行封存至 `DATA_ROOT/output/scheduled/excluded_daily_price_repair_sources/20260923_run01/`，16 檔共 4,444,826 bytes，另有逐檔移交 hash；保留真正擷取時間。最初技指 `run01` staging 因上述新發現停止，沒有發布至正式技指或 CSV。後續必須以排除完成後的新 source snapshot 重算，不能沿用停止的 staging 宣稱完成。

排除完成後以 SQLite 唯讀 snapshot 與完整 before DB 獨立逐列比對：`daily_prices` 保留的 5,331,231 列、`technical_indicators` 保留的 5,260,667 列，所有欄位皆無差異、無額外新增列；兩表各只減少計畫中的 2,942 列。所有 SQLite schema objects 和大盤資料不變，`quick_check=ok`，日價日期對官方交易日曆 anti-join 為零。此前未有 canonical 的 54 筆已在這輪取得完整官方缺席證據，不再列為待查。

## 防止再次污染與執行成本

一般與舊版每日合併入口共用已驗證的來源修訂：868 筆價格修訂、14,869 筆補回交易日，以及已套用的錯日排除。沒有新原始檔時仍會同步既有整合快取；原始檔不覆寫。一輪合併只載入一次修訂證據，利用受影響日期的 mask 處理資料，避免為約 533 萬列全數建立 Python records。SQLite writer 在發布前另行驗證，不能用舊來源或不完整重建清空已修復列。

完整技指重建逐股計算因果前綴，彙總快取透過 SQLite 暫存及串流輸出控制記憶體；這是本輪離線維護，不在 UI 每次開頁執行。staging 同時綁定排除範圍與 plan／receipt identity，相同 keys 但不同證據版本也拒絕發布。排除只涵蓋核驗的休市日期和 54 個精確 keys；其他無日價來源的舊快取列及非本輪欄位保留。

來源、備份或回復證據 hash 不符時，工具停止且不以手動改 hash 解鎖。永久來源封存是 apply／resume／rollback 的必要依賴，來源損壞時先恢復封存，再進行受控回復。回復順序是六個原始欄位複本 → 每日整合快取 → 全量技指發布 → 錯日排除 → 原價格／歷史交易日／大盤修訂，避免相依層仍使用已回復的來源。

更新頁 validator 為 25 passed／0 failed／4 skipped；相關來源、合併、發布及更新服務回歸 147 passed。程序池／中止恢復／延遲與 canary 測試 23 passed；舊 fixture 中的 7/32–7/35 已改成合法日期，計算器仍拒絕無效日期。本節測試結果不代替後續正式資料全量讀回。

真實來源 overlay 驗收從正式 DB 唯讀取出目標日期 16,823 列：15,737 筆修訂 canonical keys 及 1,086 筆 5/20 未修訂列。在 C 槽隔離資料故意改錯 1256／1477、九個補回日期的價量，放回全部 2,942 個排除 key 與休市日各一個未知代碼。Overlay 修復 20 個欄位、移除 2,945 列，剩下 16,823 列所有欄位逐列等於正式 canonical source，通過既有 import guard；未經 overlay 的排除列、錯誤 5/20 與錯誤補回交易日三種反例皆被拒絕。此驗收沒有寫入正式資料。

錯日工具／writer／staging／publication 的最後 focused route 為 45 passed；併回含另一項重構 dirty changes 的主工作區後，import contract／更新頁／價格保護及 overlay route 為 121 passed（僅 pytest cache 權限 warning）。本輪隔離分支全域 mypy 661 source files 通過，15 個凍結的 ML 契約檔相對 `dcc27a42` 沒有差異。

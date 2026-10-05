# F4 項目 revision 儲存與 20／120／250 實測（2026-10-05）

本包基於 `c99c6427675c4e73304731fe0ddea764677d9f22`，修正 Watchlist 完整 payload 歷史的二次累積。**新隔離 v3 庫的 20／120／250 實測已通過；正式舊庫未遷移，F4 正式部署仍未全閉。** 舊包 v4 的舊格式阻塞、撤回線性預估與原收據保持有效歷史，不能用新格式結果回寫它們。

## 儲存與相容邊界

新／空 SQLite 庫採 schema 3、`watchlist-item-events.v1`。六表為 `watchlists`（單份 current projection）、`watchlist_storage_meta`、`watchlist_item_objects`（不可變內容hash）、`watchlist_revisions_v3`（revision metadata／envelope／完整payload hash／delta hash／chain）、`watchlist_revision_events`（add／replace／remove／必要的order差異）、`watchlist_current_items`（有序refs）。股票代號、來源namespace、source_id、重複出現序號共同識別項目，同股不同來源不合併。

保存新增項目／事件／header與current投影於單一交易，expected revision CAS拒絕併發覆寫，revision ID重試冪等。移除項目與整清單tombstone保留歷史objects/events；測試內的restore逐版重建精確原payload、snapshot／method／rank identity，沒有刪revision／vacuum。未知item/envelope欄位保留於原始儲存。

v1三／四欄與v2 reader、bookmark v1／v2維持相容。既有v1/v2 `initialize=True`拒絕隱性升版，bytes不變；service active writer只接受嚴格v2/v3，v1維持legacy讀取。未知marker/schema、物件hash、delta/current refs、current source hash錯誤均拒絕，普通load/get_current與inventory同守衛；unknown history不靜默變成空清單。

治理只掃unique items，驗schema/hash/refs/header/chain/current投影及歷史所有bookmark source pins，不展開每份完整歷史；`historical_payload_hashes_verified=False`明示這個邊界。`iter_revisions`先有界盤點、一次cache unique items，增量重播，每次交付一份完整payload並驗其hash。本實測另逐版重播全部250版，完整邏輯歷史156,256,625 B沒有當作重複DB讀取或一次保留於記憶體。

## 實際受控留存

同日期3股×120列隔離 fixture，實際learner不在本範圍；每次實際snapshot／rank publisher＋一個不同bookmark，共250個source/hash。120.438秒、exit0、隔離guard violations=[]，新開repository再讀全部250版與20／120／250精確checkpoint。沒有預估替代實測。

| sessions | 總實體留存 B | Watchlist DB B | 聚合 payload B | Watchlist掃描 B | 全治理掃描 B | index staging B | 單份backup B | 暫存觀測峰 B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 781,365 | 372,736 | 208,091 | 235,661 | 502,932 | 32,768 | 32,768 | 62,072 |
| 120 | 3,887,695 | 2,007,040 | 1,248,012 | 1,413,503 | 2,980,764 | 90,112 | 90,112 | 98,832 |
| 250 | 7,912,388 | 4,145,152 | 2,600,012 | 2,944,903 | 6,202,133 | 155,648 | 155,648 | 164,368 |

總留存包含tiny source DB 40,960 B、universe、feature/rank所有immutable檔、Watchlist含SQLite內index、當節點兩代歷史index與一份backup。20／120／250 feature樹分別181,456／1,053,756／2,187,746 B，rank樹85,815／513,505／1,069,484 B，index tree67,274／181,966／313,042 B。較早checkpoint為本次QA額外保存100,042 B（120時）／372,120 B（250時），與whole-run receipts另列於raw receipt，沒有刪掉或隱藏它們。

SQLite integrity_check均ok；Watchlist／index WAL、SHM觀測為0，watchlist使用DELETE journal，journal觀測峰20／120／250為62,072／82,592／111,320 B；publisher原子替換前staging最大5,294 B。暫存峰以SQL execute/precommit/context exit與原子replace邊界採樣，含building DB及同時sidecars；不是OS連續採樣。backup內部瞬時峰未單獨量測，保持既有8MiB暫存硬預算與保守writer預留，不能宣稱所有暫存峰精確測得。

不調高4MiB payload／32MiB DB／64MiB scan／4096 rows上限。250時Watchlist1002 rows（current／meta各1，其餘四表各250）、聚合2,600,012 B，全治理掃描6,202,133 B。中央policy readonly SHA `6e7b018f3bc3c2ba780bc7a428a382626a9b34e470599b54c7055e6ba111e880`、20GiB reserve；251次watchlist容量檢查（初始化＋250保存）均用當下filesystem API，checkpoint preflight均within_budget=true。250節點free 232,666,476,544 B。snapshot/rank producer reserve仍採受控fixture；本容量結果只驗本fixture，未替正式producer、ML、rawPIT或跨volume writer授權。

## 故障、App 與有限驗證

39項統一路由全通過（13新相容／3新治理／11既有治理／12既有storage/bookmark）；最後source_hash corruption新增1案，針對5種corruption＋crash共6項重驗全通過，distinct總40，不把重驗重複加總。覆蓋舊格式唯讀／拒絕隱升級、重複收藏、同項revision、同股不同來源、移除／tombstone／restore、稀疏events、CAS、取消、隔離子程序提交前`os._exit(73)`、capacity False／None無DBwrite、schema/object/ref/sourcehash拒絕。Windows crash case留下49,760 B零magic cold journal；明確close後last-good current／history／inventory穩定，未刪journal，不宣稱已強制產生並復原hot journal。

三個actual offscreen MainWindow子程序 setup/readback/defaults均exit0，明示新空v3庫後跑research v1來源頁收藏／original-rank v2報告收藏與精確返回，新程序同source/report identity讀回；no-arg預設保留兩種書籤且不讀自訂來源。8個發布檔hash在取消／新程序／close後不變，所有窗口合作關閉、worker依原chain assertions結束。首輪App沿用JSON所以3階段通過但未驗v3，保留其log，第二個全新case明示v3而非改掉舊case。

mypy完整8目錄791檔通過；最後單點守衛後mypy該module通過。6個變更Python compile通過，4個production檔同一精度／未來函數AST guard無違規。沒有UI code更動，沿前包Workbench85／validator25／4skip歷史證據，不重跑這些檢查，也不跑全套回歸／F1 perf／ML／Native／Task。

首輪39-route 37P/2F保留：unknown marker普通reader錯誤碼不一致已修；crash case誤要求cold sidecar消失已改實際header與lastgood驗證。最早dry-run把atime當source變更的失敗保留，改比size/mtime/ino與SHA，無source寫入。中途readonly relative-path as_uri probe失敗無DB開啟，改resolve後續成功。producer實測固定production SHA；實測後只補current source_hash守衛，最終版唯讀重驗同一250庫及v3 App庫完整history/governance，DB SHA不變、不重發布；原實測收據的implementation pins不改成最後版。

## 正式部署與 COW 遷移未做

唯讀新版dry-run對舊20-session v2 DB實測1,302,528 B／21rows／20unique items，source SHA／size／mtime不變，migration_apply_authorized=false，沒有目的地DB。既有JSON→獨立新庫copy流程與本v2 SQLite遷移是不同功能，不能稱v2 converter已完成。

**後續工程仍需實作並審核SQLite v1/v2→v3 COW converter與activation切換流程**：固定source SHA/stat、拒絕busy/unknown；新獨立path建副本，保留所有revision ID、metadata、timestamps、完整payload hash及item/order，尤其舊版spaced canonical JSON必須逐版byte/hash oracle核對；量測新副本physical及原庫＋新庫＋backup／staging總峰，逐版reader/hash與治理/容量通過後給父層審核。明確批准才切activation/path；失敗回原path/marker並保留兩庫，不刪歷史。現有code沒有自動apply路徑，也沒有已批准正式切換方案。未知formal inventory／其他並發writer／實際舊庫容量維持failclosed。

F2/F3 A/A不重開；F1 18.62%<20%差1.38pp交父層方向，不重測微調。新Native／3–5位真人／自然資格分列，舊1477在6691ec78已完成，1000×835 outer／125%沿已接受，不加1000×800硬門檻。沒有正式資料寫入、使用者視窗操作、清理或push；其他owner三檔排除，Paper不讀不動。

## 收據與回滾

raw根 `output/qa/f4_item_revision_storage_20261005/`：`actual_retention_receipt.json` SHA `6ca0a2a8c47784bbe5399341de6c04521c1f4d4a176f911bd357481ebce8cea0`；`actual_app_storage_readback_receipt.json` SHA `26ff6f07644511a9c3b44f84b7641309923f305a410ea8234441b27cc1014a78`；`final_guard_readonly_revalidation.json`、`legacy20_readonly_migration_dry_run_v2.json`、focused/guard/mypy logs與來源pins。raw output不提交，唯一原plan只append，原174073bytes前綴SHA `d2fe59c9a48099d2c1c81faaf08ef2ad91e34a3b3b14fc2a1dc3febe91af9323`保留。

回滾僅本包production/test/document hunks，以reviewed反向patch或新local revert commit；不reset/clean、不覆寫owner。若已有新v3庫，舊程式不能讀它，回滾前須保留新庫並回原path/config，而非刪庫。未執行真實遷移／回滾刪除，Git commit/blob/status以最後readback收據及Git為準。


## 2026-10-05 F4 SQLite COW converter 與明示 activation（最新）

SQLite v1/v2→獨立v3 COW converter、CLI dry-run/convert/activation-preview/activate/status/rollback、fresh-service pointer與錯marker拒寫、bounded governance audit接線已實作並完成隔離驗證；取代前批「converter尚待工程」狀態。lexical codec保留逐版raw payload/hash、IDs/metadata/timestamps/source/order，v1缺歷史只標synthetic baseline。原4MiB/32MiB/64MiB/4096上限不變，取消、容量未知/不足、bad rows/schema、concurrent writer及身份錯誤failclosed。

限定路由 70 passed，mypy 793 source files + CLI 1 source file pass，11檔compile及精度/未來函數guard通過。已許可舊20-session fixture副本由CLI新程序完成轉換、啟用讀回、target r21追加、rollback回source r20；target r21、雙DB/audit保留，不自動合併。原fixture及17份已接受immutable pins保持相同；無producer重跑、正式資料套用、Native、清理或push。

本批COW實作工程關閉；正式使用者apply另行核准。預設canonical SQLite不存在、legacy default.json存在，實際store/mode/override仍待父層確認；沒有初始化缺失DB或讀真實JSON。F1差1.38pp交父層方向，F2/F3 A/A不重開；新Native/真人/自然資格分列，不能把部署批准寫成等自然成熟。

[逐項COW驗證、操作與正式部署邊界](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)


### 最終容量守衛收尾（2026-10-05）

啟用與回退發布 audit／marker 前重新核對當下中央 reserve；容量未知／不足具名拒絕並保留原指標、雙庫與內容。最終限定路由72 passed（focused_root_05.log；另有pytest cache唯讀警告），mypy793及CLI1通過，11檔compile／7產品檔精度與未來函數AST守衛0違規。14個獨立程序實際CLI回放全部exit0、隔離guard0違規，17份immutable來源及原20-session fixture SHA不變。最終case為output/qa/f4_cow_converter_activation_20261005/cli-roundtrip/run-615b305783f9；原失敗與中間收據保留，不替換為自然或正式驗收。

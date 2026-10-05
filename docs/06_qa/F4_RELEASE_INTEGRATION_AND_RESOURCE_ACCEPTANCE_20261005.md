# F4 跨頁整合、資源與手動部署終驗

2026-10-05，基線 `337b4ee06787259f2cd7c62cdfb4f40afcf04050`，沿唯一原計畫凍結終點。**接線／隔離流程通過；20-session量測有效；120／250 sessions長保留受既有儲存預算阻擋，不能宣告F4全部關閉或首版完成。** F2／F3的A／A不重開，F1仍18.62%／20%，差1.38pp。

## 逐項結果

| F4終點 | 結果／限制 | 本機收據（raw ignored） |
|---|---|---|
| 公開來源配置、actual MainWindow啟動／查詢／個股 | 通過。snapshot root/cohort成對且非空、rankroot-only拒絕，9工作區實頁 | `integration_agent/f4_actual_app_round_trip_receipt.json` |
| research v1／original-rank v2收藏、精確返回、新程序讀回 | 通過。v1返回源頁再按收藏，v2使用個股原排名收藏按鈕；新程序bookmarks/source/report身份一致 | 同上，`integration_root_review.json` |
| schema／cancel／stale／last-good／queue-cache | 合法收藏v1/v2支持、v3明示bookmark_schema_mismatch；actual reader合作取消與過期callback不改last-good，單一active reader、feature cache4／cohort16上限 | setup child safety；既有F2 shared queue/cache契約沿用，不重新測全套 |
| isolated啟停／配置回滾 | 三個不同PID子程序皆exit0，合作close後無worker／背景依賴；no-arg MainWindow回預設、不讀customsource，原收藏／來源不變 | setup／readback／defaults child receipts |
| 20-session physical／staging／WAL／index／backup | 實測有效，單一tiny DB、20次受控發布與收藏；不是自然20日 | `resource_agent/resource_budget_receipt_v4.json`、`resource_root_review.json` |
| 120／250較長保留 | **blocked**：收藏整份清單revision造成二次payload累積，兩者超4MiB payload／32MiB DB上限；不是等待自然成熟 | v4 watchlist_payload_retention_reforecast |
| 當下policy／unknown容量／retention | 隔離容量20GiB reserve預檢通過；unknown容量與正式inventory不授writer，retention僅dry-run | v4 policy／unknown gate、`root_policy_readonly_check.json` |
| 正式部署模式 | manual/on-demand沿用；未查改Windows Task，未寫正式DB／watchlist／registry | 手動CLI help/parser為只讀查核，不當正式部署實證 |

## 實際App來源與隔離界線

公開 `MainWindow(daily_market_snapshot_root=..., daily_market_snapshot_cohort_id=..., original_stock_ranking_root=...)` 將同一snapshot root傳給Daily service與StockReport service，rank service使用明示rank root，研究名單初始cohort同步。驗證在QObject／service初始化前拒絕partial／空值；配置不自動讀取／發布。無參數沿既有defaults。

最終root獨立核對收據的case `run-841f196fa52a`：setup PID21388／5.532s，readback PID41208／4.578s，defaults PID28556／4.204s，三階段passed、guard違規0、shutdown error0。9工作區是真實MainWindow，不是QMainWindow spy。Main initialized schema與行情seed保持在同一隔離DB，之後才受控capture／rank publish；不改strict reader或hash契約。發布後5個snapshot＋3個rank持久檔，在UI read／bookmark／return／cancel、fresh child、no-arg defaults及各process close後SHA全部一致。原watchlist是case私有JSON／SQLite，沒有使用者收藏變更。

fixture cohort `original-rank-test-universe`、決策日2026-10-05、收藏股2317；parent snapshot SHA `09d4aa7d7e8f677951d3462ecc99d5f8faf4ed265a2262ea18d761f43644a1dc`、identity `acb429eb9a5f40266768a63a4faec435442694718e72789b80b87982e0236bd4`；day/strong rank SHA `078c47f69cf806c70e1b07448c90f6e33bb5e4db911079b8e849be6312158b92`、rank identity `96c95ce801a9c7f7f062552e49f21925bbd94cc19fc1da06acafb2094bbfff9b`，parent相同。v1源頁收藏與v2報告收藏不是同一按鈕，不能用hidden source action冒充報告操作。

fixture重用3股×120行情列與既有publisher；setup容量探針simulated，明示不當正式reserve通過。新程序／no-arg都是actual公開配置，不私換service。Offscreen工程證據不取代Native／真人、自然跨日、availability／historical membership／PIT或ML資格。舊manifest schema拒絕沿既有strict reader／UX09驗證，沒有migration／隱性升級；本包未重跑已接受UX19 fault或舊1477 Native。

## 20-session實體預算

同一3股×120列market DB，20個同日Decimal行情revision，實際保留20 feature manifests、20 rank manifests、20 typed rank bookmarks。

| 留存部分 | bytes |
|---|---:|
| snapshot tree（objects／manifests／pointer） | 184,656 |
| rank tree（objects／manifests／pointer） | 86,435 |
| watchlist SQLite | 1,302,528 |
| index cache（兩代DB65,536＋metadata1,770） | 67,306 |
| 單份index SQLite backup | 32,768 |
| 單一mutable market SQLite | 40,960 |
| **實體留存總和** | **1,714,653** |

market DB更新淨增0；index staging peak32,768另計，不從retained再扣。SQLite journal DELETE，index兩代WAL／SHM absent=0。internal b-tree分拆未知但已包含整檔，不重複計數。Publisher temporary peak未量測，以既有8MiB policy upper bound作保守capacity reserve，明標bound不是observed peak。backup只一份QA小索引，不拷正式DB／20份DB。Index rollback實際恢復第一代active pointer，兩代檔案都保留。

## 長保留的已知阻塞

root以 `mode=ro&immutable=1` 查既有watchlist DB：current payload101,062 bytes、20 revisions合計1,062,690，總payload1,163,752；revision UTF8長度5,207起，每次新增5,045。保存整份清單的模型為：

`total_payload(N) = 162*(N+1) + 5045*(N*(N+1)//2 + N)`

| 情境 | 收藏payload／DB實體下界 | 總留存估算下界（非精確physical） | 現有預算 |
|---|---:|---:|---|
| 120 sessions | 37,251,702 B | 39,474,487 B | 超payload4MiB及DB32MiB，blocked |
| 250 sessions | 159,588,787 B | 164,165,430 B | 同上，payload另超64MiB scan budget，blocked |

未來精確SQLite physical=null；非watchlist部分沿條件整數ceil、兩代index／單一backup與source DB固定假設。不是自然成長證明，也不授writer。原v3線性SQLite預估總9,894,593／20,528,515 bytes **已撤回並在v4標superseded**，不能拿它們稱長保留通過。後续若要支持120／250，需容量／Watchlist owner提出可審核的版本與儲存／掃描預算方案；本批不擅改上限、不清理revision、不遷移收藏。此是明確工程／部署限制，不是自然樣本未成熟。

## 當下政策與fail closed

政策檢查2026-10-05T20:37:11.859543Z，`ml_storage_capacity.py` SHA `6e7b018f3bc3c2ba780bc7a428a382626a9b34e470599b54c7055e6ba111e880`，central reserve20GiB；沒有exported schema/version，implementation SHA＋API輸出固定版本，governance/index v1各列。root在20:39:06 UTC readonly API/hash獨立核對相同；隔離根free約232.71GB、required free21,491,613,696 bytes，within_budget=true。不得沿用前批舊容量點時數字或把本QA授予正式ML／raw PIT writer。

受控 `free_bytes=None` 直接調capacity API，原始結果是 `TypeError: usage.free_bytes must be integer`，沒有preflight返回；外層驗證gate false、writer callback0次，不能偽裝API傳回False或主機容量量測。Formal snapshot/rank/watchlist roots、併行writer、其他producer與跨volume growth未盤點，formal inventory unknown fail closed；這與已量測本fixture分列。

Manual capture parser未confirm為dry-run，confirm才opt-in，confirm＋dry-run仍不寫；CLI help/parser僅只讀，未查改Windows Task／正式writer。Retention候選不授永久刪除，automatic/permanent delete false，cleanup_authorized false。

## 有限驗證與失敗保留

25個不重複受影響案例有通過證據：root bookmark/main-routing/coordinator/rank-flow12＋resource governance11/rollback1共12＋actual三子程序integration1。Root接受agent focused final 1pass／exit0，獨立核對3個child/PID/identity/hash/guard/close收據，不再重跑完整App。Workbench85、validator25／4skip／0fail、mypy790；Main與新增test編譯，同一AST精度／未來函數guard0違規。Main final worktree SHA `0bd51d412eb81065cddcfb197e3d8e9423e54a47fcd251ae78a9baec8fbec392`，required checks後未變；pytest cache權限warning不影響通過。未跑全套／F1效能／自然producer／ML／formal scheduler。

Integration初次test錯用repo.root、cache.max_entries、rank DTO字段，改按實際API；搬fixture DB後source-path mismatch被strict reader拒絕，改為同一已初始化DB產生pins，沒有放寬核驗。第一次hidden reload造成first-open重讀清選，改真切入Daily再操作；草稿清理呼叫在成功執行前review移除，所有QA cases保留，沒有rmtree／Remove-Item。Resource初次import path／Windows help decoding錯誤保留；v1誤多扣staging，v2重核existing檔修正；v3補unknown gate，v4修二次payload模型。v2至v4修訂均有lineage，只重核既有檔案／API，不重跑20publisher；初始harness失敗案例另保留，舊值不能當final。Root initial bookkeeping的UTF8/asdict讀取錯誤沒有資料修改。

Latest resource receipt v4 SHA `1d6cee9ec6f29370bb7a68e9696b6605020663f7f9bd1cf8416d974142715b85`，current QA harness SHA `9ec8eecef0d2398b51dbc1ac40537eb50a0c28c80e8b0b82e5f7179b1f0efbdf`。原measurement與修訂harness的SHA各自保留，不假裝同次原始執行。收據原根 `output/qa/f4_release_integration_20261005/`，不提交output或唯一原plan；本地commit/blob/status以commit_readback.json及Git為準。

## 回滾與交接

回滾僅本包明列Main配置hunks、integration test與文件增補，以reviewed反向patch／新local commit；不reset/clean、不刪immutable源／原資料／QA、不回滾other owner。本包未執行回滾刪除或push。其他對話的容量／Evidence三檔保留、僅允許readonly政策／entrypoint查核，排除stage；根Paper不讀內容、不改。

接線與隔離終驗已完成，**長保留／正式部署仍有上述預算與inventory阻塞，F4不可全關閉**。F1仍18.62<20，父層處理明確例外或後續方向，不做microtweak／重測湊數。新Native／3–5位真人與自然資格各自另驗；舊1477 Native已在6691ec78通過、不重跑。1000×835 outer／125%沿已接受，不加1000×800硬門檻。完成本批後停止，父層安排容量／Watchlist子責任與下一包，不重新開F2／F3或新方法。


## 2026-10-05 F4 項目 revision 儲存與長留存實測（最新）

新／空庫採 schema3 `watchlist-item-events.v1`，不可變item＋稀疏events取代每版完整清單；舊v1/v2與兩種bookmark可讀，禁止初始化隱升級。4MiB payload／32MiB DB／64MiB scan／4096rows不變，容量未知／不足及schema/hash/refs/sourcehash不一致拒絕；歷史完整payload hash由有界增量replay另驗。

受控同日期3股×120列，實際發布／收藏250次，20／120／250總實體留存781,365／3,887,695／7,912,388 B；250時Watchlist DB4,145,152 B、聚合payload2,600,012 B、全治理掃描6,202,133 B。三節點capacity／scan／references及全部250歷史回放通過，actual v3 offscreen MainWindow三程序讀回通過。39項統一路由＋最後新增sourcehash拒絕1案共40 distinct有通過證據；mypy791、最後單點module mypy、6檔compile與精度／未來函數guard通過。

新隔離v3長留存限制已修，舊格式歷史估算不回寫；**正式v1/v2 COW converter／activation切換尚未實作及核准**。本批僅readonly dry-run，原DBbytes不變；不得把正式部署未做寫成等自然成熟，F4不能全關閉。F1差1.38pp交父層、F2/F3 A/A不重開，新Native／真人／自然資格另列；不清理、不push、不改其他owner。

[完整收據與 COW 剩餘工程](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)

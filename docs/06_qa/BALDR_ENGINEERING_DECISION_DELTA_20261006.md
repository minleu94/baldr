# Baldr 當前工程與決策差異（2026-10-06）

## 2026-10-06 R01 acceptance supersedes prior future scope

R01 `2381b1ab→4e51f34a` 已有界審核採入。Registry／legacy lookup沿原64MiB每artifact、256MiB每輪caller預算；Registry load將equity／trades／portfolio-result／replay-lineage全部計入aggregate，64KiB分塊hash、stat/fstat來源核對、同份已核bytes decode與取消。writer／repository／DTO／schema／公式未改，無budget的原非lookup callers相容；lookup缺budget unavailable。原worker101 focused、73 adjacent／1 Windows symlink skip raw與blobs核對，不累加成完整App數量。

新增tests/test_baldr_r01_registry_read_budget.py精確入冊service-oracle-research-backtest，1284／1284，direct12不變，旧1283分類/support/runner API保留。Notes backup GUI／週月與更多indicator不做，非本輪必修。U1第二家族與U2 H20 gross仍等使用者答覆，未採policy；正式Task／migration／Native／fit維持未准。

本次將在已授提交與中央文件完成後固定HEAD，執行一次四用途／Registry／selected Paper／source_id／v2／boundary affected union，mandatory Workbench→Update validator→full-roots mypy。此段只記準備凍結，結果待raw/JUnit；先不宣稱final union通過。原Stage／UX、七finiteclosed、F1/Journey性能例外、未知資格與自然成熟界線保持。證據：output/qa/baldr_r01_read_budget_20261006/receipt.json，最終差異見BALDR_ENGINEERING_DECISION_DELTA_20261006.md。


唯一路線仍是 `output/plans/baldr_product_experience_plan_20261004.md`（Danny Quant）。本表補正舊 closeout 的 source_id 待批准、176 未登錄、Paper producer 未路由、六 ML 違例等歷史描述，不另造 roadmap。

## 已關閉的點名工程缺口

| 項目 | 當前可核結果 | 保留界線 |
|---|---|---|
| ML dependency boundary | H6/H7 exact DTO；M01 H1–3 custody port、M02 H4 data proof adapter、M03 H5 neutral 同 class、M04 H8 explicit loader；678檔／0違例／exit0，原 global assert 通過 | guard／allowlist未改；完整personalization仍有其他既有allowed training imports，不能宣稱整App trainer-free |
| source_id與retry fixture | 原 Journal 保存→readonly adapter→marker／新程序；exact retry/stale及F01 delegate property已修 | 舊缺source/account/clock仍拒絕，不造身分、不migration |
| 測試清冊 | 原156＋P1新1逐檔靜態入冊，P2新1；1283/1283、missing/stale/docdrift0、direct12 | 靜態分類不是156項runtime通過，沒有新增direct bridge |
| Personal Paper selected producer | P1 ledger＋P2 daily/benchmark→B09同帳consumer／新程序，正常及深Unicode閉環、市場hardlink/sidecars/alias拒絕 | 僅synthetic，不代表真root、Task、migration或來源資格已批准 |
| 深路徑與來源保護 | COW JSON/SQLite v1/v2深Unicode/suffix完整鏈、新程序；snapshot深路徑讀回 | 2 Win1314 symlink skips保留；不改ACL，不宣稱敵意並行reparse race的handle-bound防護 |

## 可自主工程剩餘與驗證界線

目前已授的點名有限scope沒有已知未修production blocker；這不等於原24 UX全部完成。下列後續沒有擴鎖或開始實作。

| 工作 | 可自主部分 | 當前定位 |
|---|---|---|
| 最終HEAD完整回歸證據 | 中央指定穩定union驗證窗後，可跑既有mandatory UI、validator、full-roots mypy；不需真fit／正式DB | 本輪按父層要求只跑必要affected subsets；最後完整union仍只證明c9d57fc7，不能冒稱最新HEAD全量通過 |
| Notes backup GUI／圖表更多指標與週月體驗 | 沿既有bounded API、同源投影、unknown語義，按exactownership完成後續增量 | 原後續產品工作，不是已交有限包的失敗；本輪沒新增GUI／公式 |
| Shared Registry讀取鏈容量／並行custody強化 | 先定exact reader範圍與caller容量契約，再實作負例 | B07有限讀取已交；shared鏈未宣稱raceproof，不自訂正式容量政策 |
| 全面冷載入隔離 | 如另有需求，可按exactsymbols拆純契約／ports，保留公式與exception | guard0只證明現行依賴政策；其他allowed training imports已實錄，非本輪全面隔離承諾 |

## 仍需決策、批准或外部證據

| 類型 | 精確未決內容 | 不可用工程通過替代 |
|---|---|---|
| U1規格 | 第二策略家族method／參數／來源與完整compression；原生圖是否正式取代LWC局部原型 | 八族catalog不是八策略；BBANDS30/2/2/SMA upper只是review候選，未自行啟用 |
| U2研究契約 | primary target／horizon／metric、price basis、benchmark／cost版本 | B13只支持caller明示synthetic endpoint-gross介面，不代選真目標或fit |
| 正式啟用 | 真personal root／migration／backup-restore-activation、Task／account／cadence、ACL、正式model stop/resume/promotion/fit | 現行localcode/tests/commit授權不含這些；synthetic dispatcher stop不是真model control |
| 真資料資格 | official calendar完整coverage、actual sessions、source custody／availability／PIT provenance／account及模型來源 | unknown保持unknown；FA_Data/personal與marketdb分離，registry snapshot不是liveWAL |
| 自然成熟與效果 | 真forward累積、成熟labels、OOS效果／公平分母、成本／benchmark證據 | 時間與效果不是工程gate，也不能用synthetic knownclock造證據 |
| Native／真人 | Windows前景、實際字型／布局、3–5位非開發者四用途操作 | offscreen不等於Native或真人；本輪未啟前景Native |
| 性能例外 | F1 18.6219658%（20%門檻）、Journey8.109s（8s門檻） | 原有限決議保留，未產新測值或提高門檻 |

## 本次可核驗證

M01 `47873e1d→5cc54631`、二次source補正 `ff7adffe→a5304f1c` 已採。原saved artifact／index／stdout reader AST除pure cohort validation保留在ML wrapper外相同。缺port／非callable／returned verified flag拒絕，scheduled script注入原App reader；capture、fit receipt、outcome builder、receipt readback與二次source binding傳遞同port。v1、金融公式、時序、custody及false資格不變。

中央M01 53 passed／1 Windows symlink skip／1 真fit deselected（7.13s）；相鄰原v2 batch15 passed（0.76s）；CLI＋原dependency boundary55 passed（13.95s）。6 source mypy、9 files compile通過。各subset不累加成完整App數量。guard678/0 exit0；原global零違例assert未改，只有 `a0abe901` 將過時CLI六歷史違例期望收緊為main0／zero，原負例保留。raw／blobs見 `output/qa/m01_central_acceptance_20261006.json`。

9 Stage仍1 done／8 partial／0 pending，24 UX仍2 done／22 partial／0 pending；七項有限closed UX03/04/05/06/09/15/17保留。partial混合後續增量、規格、外部資格與真人接受，不能全部稱為未修工程。歷史raw／失敗與唯一plan前綴保留；無push/mainmerge、真DBwrite、migration、Task、ACL、Native、fit或清理。

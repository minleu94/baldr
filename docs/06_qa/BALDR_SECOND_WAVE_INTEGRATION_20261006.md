# B03–B14 第二波中央整合收據（2026-10-06）

本文件只保存整合證據；唯一路線仍是 output/plans/baldr_product_experience_plan_20261004.md（Danny Quant），目前狀態依 PROJECT_SNAPSHOT，操作依完整 Manual。固定最初基準 a42b2cb9；第二波 lane base ba4e9e59，B03 Update／B12 base175d9c50。中央 B10 commit05329f94，B12原024e0194／review修740fd64c。所有交付只local，未push/mainmerge。

## 接受範圍與重用證據

| 包 | 原 lane／中央 | 有界接受與證據 |
|---|---|---|
| B03 Update／Runtime | c9ea5787 →11a56284 | 原DTO影響／未知日期／明細收合；36 focused pass、mypy2。Manual就地更新4.1／11／11.1，原callbacks保留。 |
| B04 | d9e60090 →54a72f84（第一提交19294338仍保留） | 保存來源exact identity與私人Watchlist理由／查看狀態CAS／新程序讀回；97pass，4mypy。正式個人啟用未授。 |
| B05 | d9228ae8→20f9b029，a6852cb2→22c7740e（初491fb26b保留） | 原保存紀錄readonlyadapter→原列custodypins→markers→view／新程序；74pass/11deselected，缺account_kind修8pass/20deselected。main reader尚未注入，舊naive writer保持clock_unknown，不造actual。 |
| B06 | d313b2b2→200cc61a | 三帳／同列估值／缺件unknown／配置注入guard；55pass，mypy2。原result-r1 node repo隔離fixture1pass，Temp失敗為no-follow ancestor sandbox診斷，非產品main bug。 |
| B10 core／backup | 175d9c50／204aae05 | 私人review／query-only市場refs／notes backup create-only；core28，notes+review42pass/1權限skip。真私人啟用未授。 |
| B10 composition／history | 05329f94 | 個人Review週報reader／history、readiness config副本、缺table不借市場、source_lineage unknown；28 affected pass36.41s，mypy3/compile5/quant/diffpass。 |
| B12 | f30b7cc9→024e0194，dce2f909→740fd64c | typed calendar/terminal/segments＋isolated subprocess、deepUnicode snapshot I/O；103 unique synthetic原案例。review修新增runtime39與terminal2組分列，不累加重測。mypy6，canonical/schema/hash/cutoff與角色reserve保留。 |

B12 獨立 reviewer 只讀固定HEAD/base/manifest，focused102＋delta9（8 overlap／1新增）＝103 unique，兩XML hashes符合。發現preflight有效JSON＋非零exit仍可execute；原lane修明示exact int非bool/0，成功terminal也去掉缺值default0。修正後adapter blob abffa4108208f193344821a18318c525003a0435與中央相等；中央六檔targeted mypy成功，不重跑103。calendar/terminal原bytes custody由可信caller先核，不能自行填pins／verified取得資格。

B10 XML output/qa/b10_evidence_history_union_20261006.xml SHA256 7c4aed19534a795bed556dca11faf0c0479fb385bf0af6a3fc4bebec3737cb4a。B12原focused SHA532c39bbe7cb8fb1d6b5e3a4c238494ff77087373ac1e3393ed87763b14f63b7、delta af915157535b0e76b37c12098c6a382dfa92da0c6eddc0a3f3a0213bfa8fa809；review preflight cd7597b1fbbd766bbe36c05a25553ad5f303ed8ed6f350dd8f1319192be5d7f0、terminal b9d1f5c94b348a74b0b924f7c292215d98c94a146e18ac36ac737ea26f1b00f7。raw output不stage，具名lane QA保留exact命令／限制。

## 原 plan prefix 保留與剩餘

本輪只append2655bytes：before243012 SHA c4126a56cbe6a1c28b541222f11616af26b18a7149ed29ac8d402a53e729fc85；after245667 SHA05d2e17be8457dc0c38037ed58bdd94402879e25d2f7fe5c093c1065b7e2f1f6。逐byte prefix相等，ignored receipt output/qa/baldr_second_wave_plan_append_20261006.json。原9stage1done/8partial/0pending、24UX2done/22partial/0pending、七有限closed及F1/Journey性能例外保留，不新增整項done。

B07／B13仍lane進行中，B11／B14待定版派工；B09 per-I/O custody依賴採入曾遭automatic approval review拒絕；使用者直接批准仍適用且不過時修正合併，原lane正核對後同完整依賴重試，未確認完成，禁止extract或轉移中央繞過。B05main、B09同帳composition與B15穩定UI mandatory union仍未完成。首波Workbench85／validator25+4skip／mypy823只覆蓋首波固定樹，不能代替這一輪。自然累積不作工程gate，formal/PIT/training/account/clock unknown不造。

## 回滾

本輪文件僅Manual/Snapshot/Architecture/Index/scheduledREADME/QA，回復具名localcommit前核他人dirty；B10程式回復05329f94，保留私人資料與歷史。B12回復740fd64c再024e0194並同步caller；任何原source／segment／partial／receipt均留存。不實際revert、不cleanup、不降低guard。正式DB／私人migration／Task／ACL／交易／foregroundNative／fit均未執行。


## 2026-10-06 B07／B11／B13 後續接受

B07 ce8c8fad→cf0634e0、cb3af436→fe267c1d：固定來源唯讀歷史與原 typed baseline 執行保存；review 補 legacy 單檔／整輪 bytes 預算、同份 raw hash/decode 及真正 parent shutdown。原154、followup54／11為 lane 報告；中央不冒稱已核未保存的 raw 收據。UI caller 明示64MiB單檔、256MiB每輪 serialized讀取預算，僅工程資源上限，不改正式保存容量、Registry共用reader或解壓後容量政策；超限與取消明示缺件。中央 caller 增量驗證另列。

B11 ed37c1a3→c4c8e755：八族能力字典，31 focused pass；原三feature／兩MA method及catalog hashes保持。DTO實列十一欄（校正原QA十二欄誤計），沒有新增version欄。BBANDS30／2／2／SMA只是原analysis候選，保存三band與compression U1缺件保持；第二family未完成。

B13 4f828f1f→9266e7e3：pure Protocol adapter，40 own pass、47未改入口固定base收據重用。production零MLimport／零IO／零fit，原OneDate runner＋memory registry＋stub predictor僅synthetic測試橋；一次一eval＋至少一train，六pins／實際session purge與embargo／label成熟／分母／preprocessing及runner bytes hash逐項核。unsupported／U2缺件waiting，formal/training/PIT/natural/execution/production資格全false。全repo ML boundary664files仍8舊違例exit1，不稱全倉PASS。B14控制port仍獨立lane進行，正式composition尚未授權。

B07 central caller: parent-close/exact original result 5 passed in19.18s; mypy lookup/result_panel2source PASS. XML SHA256 10d2d1e0990186477a296228c69d24dea7a58160e7d5513e34d95827aad149d2; output/qa/b07_central_caller_20261006.xml.


## 2026-10-06 中央 B09／B05 caller 與 B14 port 接受

B09 d11f187a→537ae1bd、0c149aae→6ca9b54a，只採owned提交，不重採fdb3／5441依賴。獨立review逐I/O與domain allowlist、config任一非None／blank拒絕、Paper固定siblings／query-only、Ledger callbacks及Journal subclass相容未找到阻塞；原146pass14.51s raw hash b21058024245d11dfd81fdda4ac63c8a3f20574b8a5ab181241af06d5a8dc91e已核。不重146。先前auto-review依賴採入阻塞已由可信直接批准解除；本次另一個UI確認source_id三檔擴鎖仍被automatic approval review拒絕，父層等人類直接確認，兩件分開記錄。

中央main只在generic store成對明示配置時注入route＋selection.paths：actual／declared沿既有default契約，Paper沿既有paper-main／paper-main-equal常數。未配置保留legacy原constructor；未自造ledger路徑、帳戶或namespace。Paper兩reader exact paths一致，不讀override env；constructor不connect、不建立私人目錄。Journey routed trades與已選notes改guarded readonly wrapper，保留原journal投影／as-of語義，原generic未配置adapter不改。

B05新中央composition從已驗reportLoaded與原request context取source_id／cutoff／全report context；account只取已選route。背景TaskWorker有界讀原JSONL（16MiB／5000列／64KiB chunks，128個selected pins），每次canonical／links／regular單link／selected-domain守衛、stat/fstat前後驗；原bytes先產rowpins，再以同份raw projection呼原marker reader，沒有candidate自己造pin／第二次file讀回替換。完成再核generation／report物件／context／close；activeContextChanged先清空取消。原保存→custody→reader→圖／freshprocess及source bytes不變已驗，wrong source/account/context／取消／超限／post-constructor hardlink拒。

新manual trade只保存既有now_provider的aware原觀測時間；naive override在任何append／load前拒絕。舊records不migration、不補clock或source／account／PIT。標準UI確認source_id目前仍空，該类confirmation不能畫，三檔修補等待可信批准，不借result_id當source ID。這是剩餘工程，未放寬reader。

中央最終19不同caller cases通過5.84s；XML output/qa/central_personal_chart_composition_final19_20261006.xml，hash見交接manifest。targeted mypy3source、compile5與quant guard pass；pytest cache寫入權限warning不影響案例。最早repository內personal fixture被application-package overlap拒絕，改真OS Temp隔離後pass，未放寬guard。最早圖fixture漏source_id、journal roots重疊及錯exception import已修fixture；紅收據保留。

B14 671b9a97→367b4e7f，四新增pure controlport有界review接受。defaultoff／resume拒／獨立caller state witness＋CAS／readback／發布失敗failclosed／提交後cancel返實際state僅synthetic scope；production_action_allowed固定false。47新＋13既有為lane報告，不累加重跑。QA的tail_truncated實測是尾端receipt缺失／corrupt，不是有效JSON bytes尾截短；不宣稱該byte場景已有收據。prediction freeze／maturity／drift composition下一同lane新包進行，正式modelcontrol／Task仍未啟用。

19-case XML SHA256 77be611553e16345982ebea46de75dfd2b454a0694e9dd9118b1d0249806e3c0


## B14 evidence composition 有界接受

bfe356114e3e6a61ecb35f8fb28ff9d12d2990a7→7c23b7c5，只採四新增owned檔；B13/control三dependency blobs與root逐一相等，不重pick依賴。有界獨立review未發現成熟或控制放行缺陷；witness CAS後link失敗會使store不可用而failclosed，QA/Manual明示、不是可自動恢復。

53 focused passed4.88s，JUnit53/0failure/0error/0skip與raw hashes已核；raw05eca617c6a744afdb299193b1de44350e15dcc0f153aa48191f0f857b55c92c、XMLb2448fef5ab4275e3e56242f6dcd11ad23fc1d300eb1ded4ce5f1c2f20330d6b。lane output/qa/baldr-b14-evidence-final/handoff.json含fullHEAD/blobs與原source byte hashes；不重53或舊47/B13 suite求數量。mypy3/compile3/quant/零float與directMLimport收據沿用具名QA。

原sealedsource→真label/fair wrappers positive research_only/comparison(common2)→原unknown availability→waiting/mature0/完整分母，來源receipt bytes與mtime不變。另明示known-clock synthetic→原B13 public replay→freeze持久新程序prepare/newseal→maturity/monitor review_required→原control defaultpreview→真stop/dispatcher spy→freshprocess同rulehash且model未呼，原payload/pins保留。這兩路資格不互換；所有formal/training/PIT/natural/execution false，沒有正式Task、模型或registry寫入。

B15穩定mandatory與四用途增量union尚待source_id三檔直接批准；該三檔仍未修改。metadata清冊只補本輪具名新增檔，範圍外176缺登錄保持failed，directbridge12不變。


## B15 已准固定樹驗收

父層明示不讓未批准source_id三檔停住其餘驗收。固定c9d57fc704fd441a3b25af697065d4d26a8d48ec：四用途64pass34.77s（含B07真執行保存／新程序與private review讀回）、Workbench85pass2.63s、validator25pass/4skip/0fail、full roots mypy839source無錯15.78s、100 changed Python compile與quant guard成功。非Native／真人／全App／全repo boundary PASS；之後三檔批准只重受影響子集，避免重開已過整條gate。

raw receipt：output/qa/b15_four_journey_union_receipt_20261006.json、b15_mandatory_workbench_receipt_20261006.json、b15_update_validator_receipt_20261006.json、b15_full_roots_mypy_receipt_20261006.json、b15_compile_quant_receipt_20261006.json。XML/log hashes與15WP／9Stage／24UX逐項狀態見[BALDR有限移交](BALDR_CLOSEOUT_STATUS_20261006.md)。ML AST676files仍8真違例，精確後續scope與176清冊缺口／Paperproducer路由工程均具名，不自動豁免或當自然等待。


## 2026-10-06 H6/H7 exact label DTO裁決採入

此前676/8是當時歷史收據；worker56ae8d82→中央4cea589d後676/6，guard仍exit1。只guard/CLI tests/QA，exact原caller兩DTO符號；冷import／DTO零data I/O、writer/trainer／其他caller拒絕、原unknown與globalassert／reader／contracts未變。63pass raw/JUnit與三blobs核對，中央affected subset／guard另錄，不重原mandatory union。現在狀態見[BALDR有限移交](BALDR_CLOSEOUT_STATUS_20261006.md)。


## 2026-10-06 source_id 直接批准後最小修補

使用者已直接回答「當然批准」三處 source_id 修補，單次批准重試成功；local commits `7f56558c46346be1b466e0c9e7b6e3047182cb59` → `fcef6580537ecfcaa724a2de894ead58960ccb30`。恰 controls／controller／既有 controls test 三檔；Journal、shared DTO、舊原紀錄與凍結 I156 tests 未改。新保存只傳 context 明示來源，同 request 精確核來源，直接 DecisionIdentity 舊 API default 空值；不猜來源、不 migration。

專屬9 cases／2.97s 通過：原 UI accepted→既有 Journal writer→有界 readonly 原列 custody→marker可見→全新 Qt process 相同 marker hash，unknown-source新紀錄拒畫；取消 reader、同候選換source清除retry、late committed不覆蓋新context、同步 nested context signal 舊來源不回寫、legacy空值與retry conflict。targeted mypy2／compile3／diffcheck成功；未重跑完整 UI union。相鄰 controller 全集為14pass/1fail，唯一 `FlakyJournal.legacy_read_only` 缺屬性在 ae5 固定 controller 副本同 node 重現1fail，是既有 fixture 不相容，未改外scope測試或弱化唯讀guard。pytest cache permission warning 與 assertions 分報。

原8-case raw/XML、最後9-case raw/XML、相鄰失敗與基準重現原始收據／blobs 位於 `output/qa/source_id_approved_handoff_20261006.json`；讀碼／synthetic驗證不授真DB、私人啟用、Task、Native、交易、fit／Formal/PIT。I156四治理仍待四只讀組 evidence 一次合併，ML guard六既有違例仍 FAIL。

## 2026-10-06 I156 中央最終驗收

固定治理提交 `dd33d4efd23e5915fbc2c1d51fdd4b9f7ab396be`：原凍結156項＋已採P1具名1項一次入冊，共157項增量；filesystem／inventory＝1282／1282，missing＝0、stale＝0、documentation_count_drift＝0，metadata audit exit0／passed。執行時明示 skip-pytest-collection，沒有執行156項測試、fit或模型載入。原13項治理契約13 passed／10.07s；registry targeted mypy、compile及diff-check通過。原1125項分類值、support／runner API、direct bridge12與原治理assert保持不變，沒有新增bridge或豁免。

G0／G1／G2／G3／G4完整靜態證據皆核exact paths、來源blob／working SHA與合法分類；G3固定ROOT QA寫入的F4案例裁為write-risk-dry-run-required，原候選推薦留在raw。G4尾段欄位錯位修正後才接受完整49項；G2額外helper偏差中止且未採用。靜態assert數與來源檢查不是runtime pass。完整固定head、四治理blob、來源證據hash與raw／JUnit索引見本機 `output/qa/i156_final_handoff_20261006.json`。

source_id直接批准修補保留：7f56558c→fcef6580的專屬9例通過；384a46c2另以既有中央bounded composition＋原Journal保存／唯讀reader／新程序驗證正向1例通過（3.01s），是重疊增量，不累加為10項獨立案例。unknown source/account/clock仍拒；相鄰FlakyJournal缺legacy_read_only的原fixture1fail已在固定原基準重現，未放寬assert。

剩餘工程阻塞：ML boundary仍676檔／6違例／exit1（H1–H5／H8），P2正式Paper producer接線尚未接受，不宣稱正式私人鏈完成。原9Stage＝1done／8partial／0pending、24UX＝2done／22partial／0pending、七有限closed UX03/04/05/06/09/15/17不變；F1 18.6219658%（門檻20%）與Journey8.109s（門檻8s）原性能例外保留。自然累積不作工程gate，未知來源／PIT／模型資格不造。完整UI union只沿用c9d57fc7已准範圍；本次沒有重跑或提升整Stage／UX。無push／mainmerge／真DBwrite／私人啟用或migration／正式Task／ACL／清理／交易／foregroundNative／訓練。

# PROJECT_SNAPSHOT（必讀｜目前狀態）

## 2026-10-06 個人 H20 真候選接線增量

使用者已接受 U1 有限 BBANDS30 上軌比較與 U2 H20 gross、要求每日個人模型使用；早先「U1/U2 等答覆」為歷史狀態。A02 `7b5f055d→25530d9d` 已採，原 trainer 已有 H20 absolute/no-cost return head，不需新 trainer。中央可信原 fit 收據核 `rec-cal-3f8b2c276ef316e28de3806d`，真 same-bytes artifact 重播原9月28日三請求得到1613／1963／1086bp，等於原保存輸出；全部來源 bytes／mtime 不變。model final-fold 截點與 merged-lineage cutoff 分別綁定，中文 canonical hash 相容已補，中央68 focused passed、rebuild4 passed、mypy4 sources0 error。

每日目前來源尚未接通：候選對原 frozen snapshot proposal_ready，對當前正式 DB training_source_time_training_rows_unbound；live historical preview 受原 revision guard 阻擋得到0樣本。保留 guard、未知 PIT 與 performance 揭露，不拿舊 snapshot 假稱每日目前行情。自然成熟不是個人使用工程 gate；原Stage／UX、七有限closed與性能例外不變。詳見[中央整合 QA](../06_qa/BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)。

## 2026-10-06 final authorized validation / R01 accepted

R01 worker `2381b1abbec87c0015dc8a581816db02e9b54bbb` 採入 `4e51f34a`；測試清冊與中央文件凍結為 **`c5eb5c80884a9b23ad50f40e28c481338a02855d`**。原64四用途精確nodes與整檔Registry／selected Paper／source_id／v2／boundary去重後，一次union收集522項、執行521項；真fit的real_runner明示deselected。

首跑 **512 passed／7 failed／2 skipped，145.83s**。七個失敗因QA basetemp位於repo內，六個trace直接拒絕personal root/package overlap，另一selected CLI因相同配置出口回exit2。保護正確，未改production、guard、assertion或測試。只重驗這七個原node於全新package外Windows Temp，**7 passed／21.13s**；使用QT offscreen及測試所需祖先handle權限，不改ACL或啟前景Native。原紅raw／JUnit保留。

因此當前affected coverage為 **519 passed／2 skipped／1 真fit deselected**，由512原通過＋7同HEAD fixture校正組成，不能寫成單次519全綠。兩skip為WinError1314 synthetic symlink權限不足，未解除保護或隱藏skip。

同凍結HEAD的mandatory：**Workbench85 passed／2.48s；Update validator25 pass／4 skip／0 fail；full-roots mypy841 sources、0 errors**。standalone **ML guard678檔／0違例／exit0**；quant precision/lookahead guard exit0；相對原a42b2cb9基準的 **134 changed Python files compile通過**。所有source pins與HEAD在驗證期間不變。這是指定affected scope與mandatory結果，不是全1284測試檔執行或真資料／正式模型驗收。

新增R01 test已精確登錄research-backtest service oracle：filesystem/inventory **1284/1284**，missing/stale/docdrift0，direct12不變，舊1283分類／support／runner API不改；metadata audit exit0、13 governance tests passed／9.89s。Registry caller原64MiB/artifact、256MiB/round涵蓋equity／trades／portfolio-result／replay-lineage，decode同份bounded verified bytes，取消／來源改變／hash／identity／sidecars負例保留。不改schema／writer／20或200GiB reserve；序列化bytes不代表解碼RAM上限。

QA: docs/06_qa/BALDR_FINAL_AUTHORIZED_UNION_20261006.md


## 2026-10-06 R01 bounded read / final validation window

R01 `2381b1ab→4e51f34a` 已有界審核採入。Registry／legacy lookup沿原64MiB每artifact、256MiB每輪caller預算；Registry load將equity／trades／portfolio-result／replay-lineage全部計入aggregate，64KiB分塊hash、stat/fstat來源核對、同份已核bytes decode與取消。writer／repository／DTO／schema／公式未改，無budget的原非lookup callers相容；lookup缺budget unavailable。原worker101 focused、73 adjacent／1 Windows symlink skip raw與blobs核對，不累加成完整App數量。

新增tests/test_baldr_r01_registry_read_budget.py精確入冊service-oracle-research-backtest，1284／1284，direct12不變，旧1283分類/support/runner API保留。Notes backup GUI／週月與更多indicator不做，非本輪必修。U1第二家族與U2 H20 gross仍等使用者答覆，未採policy；正式Task／migration／Native／fit維持未准。

本次將在已授提交與中央文件完成後固定HEAD，執行一次四用途／Registry／selected Paper／source_id／v2／boundary affected union，mandatory Workbench→Update validator→full-roots mypy。此段只記準備凍結，結果待raw/JUnit；先不宣稱final union通過。原Stage／UX、七finiteclosed、F1/Journey性能例外、未知資格與自然成熟界線保持。證據：output/qa/baldr_r01_read_budget_20261006/receipt.json，最終差異見BALDR_ENGINEERING_DECISION_DELTA_20261006.md。


## 2026-10-06 M01有限接受與當前工程／決策差異

M01 `47873e1d→5cc54631`、二次source補正 `ff7adffe→a5304f1c` 已採。原saved artifact／index／stdout reader AST除pure cohort validation保留在ML wrapper外相同。缺port／非callable／returned verified flag拒絕，scheduled script注入原App reader；capture、fit receipt、outcome builder、receipt readback與二次source binding傳遞同port。v1、金融公式、時序、custody及false資格不變。

中央M01 53 passed／1 Windows symlink skip／1 真fit deselected（7.13s）；相鄰原v2 batch15 passed（0.76s）；CLI＋原dependency boundary55 passed（13.95s）。6 source mypy、9 files compile通過。各subset不累加成完整App數量。guard678/0 exit0；原global零違例assert未改，只有 `a0abe901` 將過時CLI六歷史違例期望收緊為main0／zero，原負例保留。raw／blobs見 `output/qa/m01_central_acceptance_20261006.json`。

9 Stage仍1 done／8 partial／0 pending，24 UX仍2 done／22 partial／0 pending；七項有限closed UX03/04/05/06/09/15/17保留。partial混合後續增量、規格、外部資格與真人接受，不能全部稱為未修工程。歷史raw／失敗與唯一plan前綴保留；無push/mainmerge、真DBwrite、migration、Task、ACL、Native、fit或清理。

`docs/06_qa/BALDR_ENGINEERING_DECISION_DELTA_20261006.md`


## 2026-10-06 M02／M04 目前有限接受

M02/H4 `0a6f7a32→48d2ae5f`、M04/H8 `3d00f624→a941c79c` 已完成有界審核並採入。M02 僅將原 20 official session proof 驗證移至 data adapter，signature、錯誤與原 resolver 語義不變；純 adapter 冷載入零 ML／data I/O。M03 後完整 personalization 冷載入仍觸及 consumer 其他既有 allowed training imports，負例如實保留，不宣稱整個 app 無 trainer。M04 publisher 必須明示注入原 model loader；缺 loader 在來源讀取／lock／mkdir 前拒絕，原 hash／clock／custody／exception 不變。readonly reader 不載模型；scheduled composition 只驗 AST 接線，未實跑完整 scheduled cycle。

兩 lane 的 exact 四檔、固定 commit blobs、raw／JUnit SHA 均核對；沿用 M02 33、M04 56 focused receipts，中央整合關鍵子集 20 passed／5.33s（69 deselected，pytest cache write warning，不是產品失敗），4 source targeted mypy、8 files compile 通過。數量有重疊，不累加為新完整 suite。standalone ML guard 677 檔／3 違例／exit1，僅 H1–H3 留 M01；global FAIL，未變更 allowlist／global assert。1283 inventory／direct12 沿用固定 metadata 收據，無新 test 檔，未重跑 full UI／mypy union。

9 Stage=1 done／8 partial／0 pending、24 UX=2 done／22 partial／0 pending、七項有限 closed UX03/04/05/06/09/15/17 不升格；F1 18.6219658%（20%門檻）、Journey8.109s（8s門檻）例外保留。自然累積不是工程 gate，unknown model／PIT／source／account／clock 資格不造。無 push／main merge／正式 DB write／migration／Task 啟用／ACL／Native／fit／清理。完整證據：`output/qa/m02_m04_central_acceptance_20261006.json`。


## 2026-10-06 P2／M03 目前有限接受

P2 `f16e3ab6→e34e2ed2`、市場alias review補正 `b0ebaeff→0eca90cf` 已採；只關selected daily／benchmark兩producer與原P1接口。原阻擋P2-R1已由同一hardlink probe驗證拒絕：state/status未新增、私人source bytes/mtime不變；市場main/sidecars/祖先link每I/O核對、calendar錯誤不吞custody、exact generated staging／create-only benchmark／atomic status、readonlylegacy與legacy relative相容保留。原108與R1 delta26 immutable raw/JUnit已核，中央R1關鍵18 pass／19.65s，中央普通＋深Unicode/emoji source→P1填單→daily→benchmark→B09新程序readback兩例2 pass／11.30s，重疊數量不累加；沒有重108或全UI union。正式來源/私人啟用/migration/排程仍未授，不把此scope冒稱全Paper正式鏈完成。

P2只另登錄具名新test一項，治理固定 `21c3c226`：filesystem/inventory1283/1283，missing/stale/docdrift0、direct12不變；metadata audit passed/exit0且skip-pytest-collection；原13治理13 pass／14.59s，原1282分類與support/runner API不變。原I156靜態156＋P1具名1收據保留，不重算為runtime通過。

F01 `042a2dac` 只補FlakyJournal唯讀delegate property，原controller7例在immutable提交7 pass／0.90s，原assert與production guard未改，舊baseline fail raw保留；此fixture blocker已解。M03/H5 `365e5fe3→700d1446` 採neutral InvalidCalibrationOutputError，同class identity／training原API reexport／consumer特定except保留；production除import/class移位以外AST相同。worker19 pass/mypy3/compile5/quant及Luna只讀review已核，中央15 class/非法／合法bp/coldimport/fallback pass／2.02s；採入中央root再驗同15例15 pass／1.68s（重疊不累加）。新neutral冷import不載trainer；consumer其餘既有allowed imports本包未重構。中央standalone guard實測677檔／5違例／exit1，僅H5消除，H1–H3／H4／H8仍待M01／M02／M04。原global assert與allowlist未改，不稱全倉PASS。

唯一原plan只append；9Stage＝1done/8partial/0pending、24UX＝2done/22partial/0pending、七有限closed UX03/04/05/06/09/15/17保持，F1 18.6219658%（20%門檻）與Journey8.109s（8s門檻）性能例外保留。自然累積不是工程gate，U1/U2與未知PIT/model/account/source資格不造。可核本機 `output/qa/p2_m03_central_acceptance_20261006.json` 及同批raw/XML；完整操作看Manual，既有c9d57fc7 mandatory union只沿原測試範圍。無push/mainmerge/正式DBwrite/Task/ACL/Native/交易/真fit/清理。

## 2026-10-06 I156 中央最終驗收

固定治理提交 `dd33d4efd23e5915fbc2c1d51fdd4b9f7ab396be`：原凍結156項＋已採P1具名1項一次入冊，共157項增量；filesystem／inventory＝1282／1282，missing＝0、stale＝0、documentation_count_drift＝0，metadata audit exit0／passed。執行時明示 skip-pytest-collection，沒有執行156項測試、fit或模型載入。原13項治理契約13 passed／10.07s；registry targeted mypy、compile及diff-check通過。原1125項分類值、support／runner API、direct bridge12與原治理assert保持不變，沒有新增bridge或豁免。

G0／G1／G2／G3／G4完整靜態證據皆核exact paths、來源blob／working SHA與合法分類；G3固定ROOT QA寫入的F4案例裁為write-risk-dry-run-required，原候選推薦留在raw。G4尾段欄位錯位修正後才接受完整49項；G2額外helper偏差中止且未採用。靜態assert數與來源檢查不是runtime pass。完整固定head、四治理blob、來源證據hash與raw／JUnit索引見本機 `output/qa/i156_final_handoff_20261006.json`。

source_id直接批准修補保留：7f56558c→fcef6580的專屬9例通過；384a46c2另以既有中央bounded composition＋原Journal保存／唯讀reader／新程序驗證正向1例通過（3.01s），是重疊增量，不累加為10項獨立案例。unknown source/account/clock仍拒；相鄰FlakyJournal缺legacy_read_only的原fixture1fail已在固定原基準重現，未放寬assert。

剩餘工程阻塞：ML boundary仍676檔／6違例／exit1（H1–H5／H8），P2正式Paper producer接線尚未接受，不宣稱正式私人鏈完成。原9Stage＝1done／8partial／0pending、24UX＝2done／22partial／0pending、七有限closed UX03/04/05/06/09/15/17不變；F1 18.6219658%（門檻20%）與Journey8.109s（門檻8s）原性能例外保留。自然累積不作工程gate，未知來源／PIT／模型資格不造。完整UI union只沿用c9d57fc7已准範圍；本次沒有重跑或提升整Stage／UX。無push／mainmerge／真DBwrite／私人啟用或migration／正式Task／ACL／清理／交易／foregroundNative／訓練。

## 2026-10-06 中央 caller 增量（先前驗證範圍）

已採B07原保存歷史／同raw有界讀取／parent關閉取消、B09逐I/O custody（537ae1bd／6ca9b54a）、B11八族唯讀能力字典（c4c8e755）、B13pureProtocol模型輸入（9266e7e3）、B14pure controlport（367b4e7f）。原method/catalog hashes保留，第二family未完成；B13ready限synthetic offline，U2未決waiting，所有正式資格false。B14僅synthetic dispatcher／獨立witness/CAS／exactrule，freeze/maturity/drift composition已採7c23b7c5，53 focused raw/JUnit已核：原wrapper unknown→waiting、synthetic knownclock→freeze/newseal replay→monitor→真stop/dispatcher/newprocess分報，來源資格全false。

中央main私人三帳route＋paths、Paper固定query-only readers及Journey原source逐讀guard已接；B05從已驗report/requestcontext背景讀bounded原JSONL、原rowpins→reader→chart、新程序與過期回傳拒絕已驗19case／5.84s。新手動交易保存aware now_provider，naive beforeappend拒；不migration舊紀錄、不補source/account/PIT。[中央收據](../06_qa/BALDR_SECOND_WAVE_INTEGRATION_20261006.md)。

剩餘：標準UI確認source_id三檔已經使用者直接批准，單次重試成功並完成最小來源傳遞／exact retry／stale context守衛（7f56558c→fcef6580）；Journal/DTO/舊紀錄未改，unknown不補造。B15已准固定樹c9d57fc7驗收：四用途64／Workbench85／validator25+4skip／fullmypy839／100 changed compile與quant guard通過；source_id批准後僅重受影響專屬9例通過；相鄰controller的FlakyJournal缺legacy_read_only既有1fail已固定基準重現，完整UI union沿用原範圍。metadata1105/fs1281/docdrift0/stale0，direct bridge12維持；I20後凍結156未登錄＋P1另新增1具名test待登錄，與6boundary仍工程FAIL（H6/H7 exact label DTO已有限裁決，原8→6，676檔guard仍exit1；原DTO／reader／global assert未改），不因原有豁免。B09先前dependency拒絕已依直接批准解除並接受owned scope，與本次source_id批准分開。Formal DB／私人啟用／migration／Task／ACL／Native／交易／fit仍未授。

原9stage1done/8partial/0pending、24UX2done/22partial/0pending、七有限closed及F1/Journey性能例外不變，沒有新增整項done。首波85／25+4skip／mypy823只覆蓋首波樹，lane報告不能代替第二波union。自然成熟不當工程gate，unknown資格不造；下方日期化摘要是當時scope，最新caller狀態依本段。

## 2026-10-06 第二波工程整合（最新摘要）

目前中央 local HEAD 主體已採 B04 exact 保存來源選擇／私人 Watchlist 理由與查看狀態 CAS 保存、B05 原生圖 marker 契約／原保存紀錄 readonly reader 與缺 account_kind 拒絕、B06 三帳摘要與注入防 fallback、B03 Update／Runtime 白話影響／未知日期／明細收合。B10 私人覆盤／notes 備份及週報 composition/history 接線已驗，中央 commit 05329f94：週報私人 Review 與 query-only 市場 refs 分離，歷史不回落市場 writer，28 affected cases、targeted mypy／compile／quant 通過。原來源與未知資格保留。[B10 收據](../06_qa/BALDR_B10_PRIVATE_REVIEW_20261006.md)。

B12 f30b7cc9 與 exit-code 修正 dce2f909 已採為中央 024e0194／740fd64c。typed calendar/terminal pins＋strict request codec→隔離 subprocess owner，default execute=false、缺來源拒絕；preflight／成功 terminal 要求明示 int 非 bool 的零 exit。103 個不同 synthetic 基礎案例與 39 runtime／2 terminal 增量收據分開保留，不累加重測。snapshot producer／repository 只 OS I/O renderer 修正深路徑，canonical identity/schema/SQL/hash/cutoff 不變；snapshot 20GiB／capture 200GiB 原政策下限保留，高 override 不降原值。未註冊正式 Task。[B12 收據](../06_qa/BALDR_B12_DAILY_RUNTIME_20261006.md)。

剩餘工程：B05 主程式原紀錄 reader 注入、B09 per-I/O custody 與同帳服務 composition、B07 保存規則／四來源歷史、B11 八家族有限能力字典、B13 typed model-input 定版與 B14 真正 control port、B15 穩定 UI mandatory union／完整文件。B09 依賴採入曾遭 automatic approval review 拒絕；使用者已直接批准仍適用且不過時的修正合併，原 lane 正按父層逐字證據核對後對同完整依賴重試，結果未確認前仍不宣稱 custody 完成，未轉移 ownership／extract 或繞過。正式 migration／私人啟用／Task／ACL／真來源寫入／Native／fit 仍未授權。

原計畫 9 stage＝1 done／8 partial／0 pending、24 UX＝2 done／22 partial／0 pending，原七項有限 closed 與 F1／Journey 性能例外保留，沒有新增整項 done。首波 Workbench 85／validator 25＋4 skipped／full mypy 823 僅覆蓋首波固定樹；第二波 UI mandatory union 尚未跑，不以 lane focused 數量代替。自然時間累積不當工程 gate，unknown PIT／帳戶／時鐘／模型資格不造。下列較早摘要是歷史接受範圍，不能代替本段目前狀態。

## 2026-10-06 原產品計畫首波整合（目前摘要）

新唯一dev owner已有界接受Astra B01–B15，首波採B01 registry exact-import／V5語意及B03首頁四用途／明示當下搜尋／大盤收合與缺件三態；中央個股摘要補change及區塊sufficiency與ML限制併列。共用personal長路徑IO helper與B02深DB／防護已採納（234pass／2既有symlink權限skip）；B08私人routes契約21pass，不冒充B09/B10 caller接通。ML新3消除但舊8仍違例，不能稱repo boundary pass；capture200GiB政策不擅降20GiB。

原9stage仍1done/8partial/0pending、24UX仍2done/22partial/0pending，七有限closed與性能例外保留。下方日期化收據按原scope讀，不把舊「最新」或舊counts當本波狀態；本波驗證／缺口見[首波QA](../06_qa/BALDR_FIRST_WAVE_INTEGRATION_20261006.md)。自然成熟、模型資格、正式source與啟用另列，不阻止可隔離驗證的工程；沒有新增UX整項done／正式migration／Task／fit／Native／push。

## 2026-10-06 UX23 隔離 shadow 最小工程狀態（最新）

沿59a09f9b，existing fair comparison＋registry lifecycle DTO 匯出→模型／來源／比較收據 pins→規則回退／隔離投影停止→atomic 保存／exact 新程序重讀。白話三軸「工程可執行／資料或效果未合格／未啟用」，不開 registry RW、不載模型／fit、不改正式控制或 Task。未知 availability／0合格樣本及所有資格 false 保留，alpha 0、selection unknown。

UX23 pending→partial，沒有新增 done；9stage=1done/8partial/0pending、24UX=2done/22partial/0pending。自然預測與成熟／漂移／採用／真效果／正式啟用仍未完成；停止收據僅是研究投影，不是實際 disabled 操作。無 UI／Native／效能 gate 變更，其他 owner 三檔及八條既有 ML boundary 違例保留。[QA 與剩餘工程](../06_qa/UX23_SHADOW_ACCEPTANCE_20261006.md)；Manual 已同步。

## 2026-10-06 UX22 同源公平比較工程

沿ae90ba2c，exact sealed labels→既有CORE20特徵loader／整數shadow prediction DTO→同序共同樣本計分→白話CLI／JSON新程序重讀已接線。明示方法、horizon、label／split／cost／benchmark及兩模型target契約，完整母體、方法行、所選目標與流失分母分列；缺baseline／candidate或目標映射不計分。原sealed fixture仍18 labels／12數值、18 availability unknown、0 temporal training candidates；合成日期及模型輸出只驗工程，PIT／training／formal／natural／execution皆false。

UX22／Stage7仍partial，合格真來源／模型lineage／效果證據待補；9stage=1done/8partial/0pending、24UX=2done/21partial/1pending，沒有新增done。ML boundary base八條違例保留、本包新增0，只限定新consumer exact-symbol read-only邊界；不稱全repo通過、不修其他owner。無UI或正式Task／DB／模型發布變更，既有效能gate不重開。[本包驗證與剩餘缺口](../06_qa/UX22_FAIR_COMPARISON_20261006.md)；操作依Manual最新章。

## 2026-10-06 UX21 label→UX22 readiness 有限入口

沿已接受8104d0a，版本化明示endpoint label政策（gross/net/gross_excess/net_excess、H5/10/20子集）→exact sealed parent/outcome→全母體與逐方法對照ledger→固定訓練/評估界線→既有baseline所需輸入缺件readiness已接線。CLI只讀保存來源、輸出研究JSON；不查今天行情、不呼叫fit。成本／benchmark／availability未知不補0，沒有自選唯一目標；label值已知不等於歷史PIT或訓練合格。

本包開始UX22的readiness工程，所以UX22由pending→partial、stage7由pending→partial；完整label/feature映射、同源baseline與候選prediction pins、實際公平比較與資格仍未完成，UX23保持pending。9stage=1done/8partial/0pending；24UX=2done/21partial/1pending，沒有新增done、正式Task／DB／模型／自然成熟授權。已接受七項首版工程與性能例外不重開。[本包QA與剩餘工程](../06_qa/UX22_LABEL_READINESS_20261006.md)。


## 2026-10-06 UX21 明示benchmark整合

沿5b978df2，review10508947／focused35後cherry-pick57934c51，caller具名設定→actual query-only source→同期間Decimal core→版本化保存／重讀→readonly receipt UI已接線。runtime／saved v2保留v1 benchmark=null相容，成本與basis／availability／source／期間pins封存；未知與失配不補0，不提高PIT／ML／正式／交易資格。沒有UX21預設基準，CLI需明示JSON或未設定。

fixture可比gross／net excess與新程序／修訂、缺日、跨source、取消stale驗證；公開D市場TAIEX四日只讀另報，source main/WAL不變、duplicate／newprocess一致，actual公司行動basis／accepted pins未具備，benchmark unknown／excess null。TAIEX只屬QA具名請求，不是使用者預設。UX21整項仍partial／stage7pending，完整label與正式部署／真人／自然成熟未完成；9stage 1done/7partial/1pending、24UX 2done/20partial/2pending不變。[整合收據及完整label最小缺口](../06_qa/UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md)。

## 2026-10-06 UX08 保存圖表有限閉環

沿3ee80ff8，新日研究／隔離parent producer把既存價格及MA20／60歷史以有界versioned chart封入原feature artifact；個股／原排名下鑽只讀exact parent，圖與精確表同源，不以今天補保存來源。原DB改值／不存在、新程序重讀、gap、取消重試返回／stale及舊保存缺件／獨立最新研究已驗。圖表可用不放寬原feature／rank核驗；未知availability／PIT仍false。

251個不同相關案例、Workbench85、validator25／4略過、mypy813、compile／quant通過；actual offscreen圖／表與缺件畫面核對。UX08這個日研究parent有限工程終點done，整項及stage4仍partial：推薦execution writer／舊結果補建、更多指標、markers、縮放平移／期間、圖商選型、Native／真人未完成。原計畫原文raw bytes只追加；9stage 1done/7partial/1pending、24UX 2done/20partial/2pending不變。UX21 benchmark lane10508947僅只讀核對，未整合；source／runtime／store目前仍benchmark=None/null。[UX08收據](../06_qa/UX08_SAVED_CHART_READBACK_20261006.md)。

## 2026-10-06 UX24 第一版 stage 1–3 有限工程封存

沿8a78eac及已接受F1–F4，具名母體close／MA20／MA60與兩固定方法、共享原排名、個股exact context／收藏／返回／歷史讀回的首版有限工程已封存。補驗找到並修正舊mapping缺rank_context被補空字串而遭DTO拒絕；明示錯誤仍拒絕，沒有新增產品功能。UX03／04／05／06／09／15／17限定工程終點完成，整項仍partial；9stage 1done/7partial/1pending、24UX 2done/20partial/2pending不變。

目前版本隔離全App三程序與原250歷史唯讀重播、來源不變、當下容量與取消/stale通過；不重做F1性能例外、F2/F3、舊1477 Native、learner／Library／個人migration。首版manual/on-demand A/A沒有新發現未修工程缺陷；正式apply、Native／3–5真人、自然增長／PIT另列，其他原產品工程未升done。可用範圍與真實限制見[UX24封存收據](../06_qa/UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md)及[Manual](../07_guides/APPLICATION_MANUAL.md)。本地commit/readback後停，UTC07:00停止界線有效。

## 2026-10-06 UX21 實際來源→保存→隔離日報

承接48feaf70：明示 query-only 市場價格＋既存verified TWSE年度計畫 cache→exact parent/children及原決策close指紋→有界endpoint研究成效→atomic sealed保存／hash重讀→同parent所有revision日報／背景Qt畫面已完成。實際D市場1477/2382的9/1事後研究毛報酬及10/6缺當日價格／未成熟兩路完成；duplicate／新程序相同、main/WAL pins不變，來源不存在blocked零發布。未知成本/benchmark保留null，年度計畫／current-observed不授PIT/訓練/正式或交易資格。

UX21整項仍partial：qualified benchmark／完整labels／正式daily部署與官方actual-session/custody、自然成熟／效果、Native／真人仍缺；這些分別是工程／決策／外證。9stage 1done/7partial/1pending、24UX 2done/20partial/2pending不變，UX22/23不開工。逐項partial差距與驗證見[UX21來源保存日報收據](../06_qa/UX21_SOURCE_STORE_DAILY_20261006.md)及[Manual](../07_guides/APPLICATION_MANUAL.md)。既有效能例外不重開gate，沒有正式DB/Task/migration/fit/push/清理/前景Native；本地commit/readback後停，UTC07:00停止約束有效。


## 2026-10-06 UX21 保存母體 forward outcome 有限整合

由90d16858乾淨dev接手，review後採納lane9aeb2655為25eec766；exact parent＋children與明示calendar/prices/benchmark/cost/asof接唯讀consumer，現有母體收據視窗可看H5／H10／H20完整分母、每股毛／net／excess、資料不足與未成熟。成本不補零，方法判定不是交易selected；未捕捉／排除分母保留，PIT／formal／training／natural／execution false。107passed／1skip、Workbench85、validator25／4skip、mypy810與compile／quant guard通過；合作cancel/stale與同收據新程序重讀已驗。詳見[UX21限定收據](../06_qa/UX21_FORWARD_OUTCOME_20261006.md)、[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-06-ux21-保存母體-h5h10h20-研究結果)。

UX21目前partial，UX22/23 pending；九stage done1／partial7／pending1，24UX done2／partial20／pending2。官方calendar／price custody與自然outcome另列；輸入adapter／outcome store／正式daily owner consumer、Native／真人未完。不重做舊learner/Library/personal、不啟正式Task/DB/migration/fit、不重開已接受效能gate。完成包commit/readback後停交父層，UTC07:00安全暫停界線保持。

## 2026-10-06 UX08 原生歷史 MA20／MA60 有限接線

沿d9a4a086，既存MA20／MA60有界唯讀歷史列接到純投影、原生覆蓋線與精確表；同股／來源／日期／hash／cutoff核對，缺列／None斷線，不重算或補末值。保存／daily／rank未具備同版本技術artifact歷史時明示缺件、禁止借live；暖機與availability未知不授PIT。116受影響案例、Workbench85、validator25／4skip、mypy795、6檔compile／quant guard通過，見[UX08最新章](../06_qa/UX08_NATIVE_CHART_CONTRACT_20261005.md)。整項／stage4仍partial，saved歷史、其他指標、markers、期間／縮放／平移、renderer故障與Native／真人未完。

Widget獨立調查核實5個主站身份，但126格嵌入資格全部unknown；桌面條件／歷史深度／實際嵌入未驗，原生default維持，見[UX07補充](../06_qa/UX07_CHART_FEASIBILITY_20261005.md)。Personal path/control_paths另lane進行，未整合或正式啟用。F1接受例外、20%未達的批准邊界維持。

## 2026-10-05 UX08 原生圖同源契約與最新批准邊界

以631d6ad為基線，個股原生價格圖與精確數值表共用純投影、來源身份與 cutoff；已知股號／日期／hash／來源失配拒絕，未來／晚到資料排除，缺件保 unknown。原生圖建構或填值失敗保留已核對表格，單日技術快照不延伸歷史線，身份不足事件不畫交易 marker。限定59案例通過，Workbench85、validator25通過／4略過、mypy795及4檔compile／quant guard通過；詳見[UX08限定收據](../06_qa/UX08_NATIVE_CHART_CONTRACT_20261005.md)。UX08整項／stage4仍partial：互動期間、歷史線／markers、圖商原型選型、paint故障與Native／真人驗收待辦。

父層轉達使用者23:32 UTC同意F1效能例外結案：實測18.621965821542936%，20%目標未達、差15.1294400013285ms保留，不能標benchmark pass；不再微調／重測。此批准不涵蓋正式JSON遷移或前景Native。

使用者新增個人資料必須與可分享市場包分離的約束；既有FA_Data/output/watchlist新DB位置不符合，正式啟用仍阻擋。首選設計為每位使用者LOCALAPPDATA/baldr/personal，專用DB候選C:\Users\archi\AppData\Local\baldr\personal\watchlists\watchlists.v3.sqlite，設定／pointer／receipt／audit／內容備份亦在個人root；尚未選定、建立或接入writer。獨立personal-storage lane負責路徑與匯出隔離工程，本批只留設計與交接，沒有遷移、匯出／分享或改共用config。較早段落保留歷史邊界，最新批准與約束以本段為準。

## 2026-10-05 頁面內操作說明

各頁「i」說明改為操作、欄位與結果判讀的分區內容，補齊決策工作台、個股研究、市場總覽、研究母體盤勢、每日研究條件及 SQLite 檢視入口；資料更新各來源子頁可直接開啟共用說明。說明可捲動與複製文字，回測明列策略分數門檻及最佳化設定位置。內容與操作見 [Manual](../07_guides/APPLICATION_MANUAL.md#頁面的-i-說明按鈕)。本次變更範圍為說明與入口，不涉及研究公式、交易紀錄或正式資料更新。

## 2026-10-05 UX19 儲存與發布復原（最新限定收尾）

原排名缺件指標 CAS 已修正；有界唯讀 hash／manifest／v1-v2 收藏參照診斷與保守 dry-run 完成，沒有永久刪除授權或自動清理。根層95項＋另列8故障案例共103個不同案例通過；mypy784、7檔compile及quant guard通過。真實 MainWindow空隔離資料offscreen九頁啟動／正常關閉通過（最新worker33872／launcher33136均退出、worker0），不替代正式資料／Native／真人驗收。

既有17檔33,714bytes／4v2／8refs只讀診斷通過；未assert正式所有Watchlist，references_complete=false、候選0。growth歷史不足，不造7／30／90日自然推估。永久刪除停用，未知／不完整來源採保留；其他consumer／完整方法字典／正式母體與排程／其他writer生命周期仍是工程待辦，Backtest18.62%／20%未達不變，來源availability／PIT／自然資格與Native分列。

承接a466cced，另一對話39cc1ec的容量／Evidence／Paper與共享文檔已保留，本批不計為自身成果或代改；中央reserve時點20GiB、正式DB與WAL pins保持，SHM僅mtime變動不聲稱全stat一致。詳見[限定收尾收據](../06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。下列較早章節保留其版本邊界。


## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。

受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。 真實既有 D 來源的 2382 四模式，在程序 24368 保存至隔離清單，程序 26516 重開核對來源與返回；兩程序正常退出且 worker=0。17 個 feature/rank 原檔及 DB/WAL/SHM stat、原引擎／母體設定保持不變；未重跑既有真實來源 publisher／learner，未寫正式 DB／registry 或真實收藏。排名來源測試僅用三股小型 fixture DB 與隔離產物。

其他原大盤／強弱 consumer 融合、完整 feature/method dictionary、正式合格母體／排程部署、長期 storage/growth 及其他 lifecycle crash 驗收仍是第一版工程。Backtest 18.62%／20% 未達保留。正式母體權威、official availability／歷史 membership／PIT，以及舊 Top/Bottom 口徑與 numeric score 暴露屬來源／方法版本決策。Native 鍵鼠／縮放／跨頁、完整 App startup 與 3–5 位真人驗收另待桌面時段；不把工程缺件稱為自然成熟。 詳見[本批限定 QA](../06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。原計畫 append-only；本地 commit/blob 核驗後交父層，不 push／清理／操控用戶視窗，未知 capture 與還原映射不動。以下較早紀錄只代表其版本當時狀態。


## 2026-10-05 UX13／18 共用具名母體盤勢投影

承接 f07f298，市場探索新增「研究母體盤勢」，與每日研究名單共享同一 verified snapshot／source／date／方法身分及既有條件結果。盤勢顯示完整 declared cohort 三態人數與各股行情日、原 close／MA 值；partial 缺件計未知分母，名單不偽造缺件上下文。原排名未提供明示未知，只能按既有指標值排序，Decimal 精確且缺值置尾，不新增綜合分數／alpha。

本包限定驗證以 [QA共用投影章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) 的實際收據為準。完整 UX13／18／19 與 stage2／3 仍部分完成；原強弱排名發布、其他盤勢consumer全面融合、完整母體／方法／收藏與長期治理仍待工程。Backtest18.62%／20%未達維持，PIT／自然 ML／真人驗收不假造。

## 2026-10-05 UX18 兩條固定研究方法契約

承接 c50cefcd，兩條既有 close 高於 MA20／MA60 觀察補完整固定方法契約與 manifest 綁定：方法 ID／家族／版本／固定參數／方向／必要欄位、決策日與可判讀資格／unknown 理由。cache 與快照身分保存同一契約，方法身分變更不能沿用舊結果；錯方法／版本／參數／日期／hash 拒絕。舊 schema 只能明確更新重產，唯讀不自動升版或改走 live；原公式、數值與研究用途保持，非 alpha／買賣勝率。

本包限定完成與驗證以 [QA 方法綁定章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) 的實際收據為準。UX18／19、stage2／3 仍部分完成：原排名／強弱、市場共用 consumer、完整方法／母體、收藏與長期容量仍待工程；Backtest18.62%／20% 未達維持，歷史 PIT／自然 ML／真人驗收分列外部證據，不阻擋本研究切片。

## 2026-10-05 UX04／05 日常研究名單接線

以695797ec為基線，Recommendation新增明示cohort的每日研究條件來源，沿既有close／MA三態做AND／OR與why／why-not，個股固定同manifest／stock／as-of／source身分讀回。只有明確更新才bounded producer；預設repo output/research_snapshots/daily_market研究區，不改正式資料根或WindowsTask。來源修訂／缺件保unknown與中文更新提示，session／切股／返回保來源metadata。工程與Native限定結果以[QA最新flow章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)為準。

這是UX04／05／06有限切片，完整UX18／19與stage2／3仍未完成；更多feature／method、原排名／全母體融合、正式排程與長期storage治理待工程，Backtest18.62%／20%與自然PIT／ML限制不改。

## 2026-10-05 UX19 最小研究快照閉環

以 `3a975e3` 為基線，close／MA20／MA60 既有研究特徵新增隔離有界 producer、不可變 manifest／artifact 與 verified reader，個股 `read_report()` 可明示 opt-in 讀回。最多16檔、每股120列，僅失效股重投影；來源缺件停止發布，既有 latest 保留。reader 另可辨識具名 partial，但不把 cohort 完整等同全市場或特徵／PIT資格。實跑與驗證以[限定收據 UX19 新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)為準。

預設 UI／live consumer 不改，沒有正式 DB writer、排程或新公式。整個 UX18／19、其他 consumer／選股融合及長期 storage 治理仍未完成；Backtest18.62%／20%仍未達，歷史 PIT／自然 ML 資格另列，不以成熟等待代替工程待辦。

## 2026-10-05 UX18 既有日特徵研究切片

既有close／MA20／MA60經共用readonly snapshot實際接入個股研究 `read_report()`、研究理由與首屏。穩定identity綁來源內容／日期／scope／版本，instance cache最多4筆；最後連續有效OHLC不足20／60筆或日期／品質不符，條件為unknown，首屏不另作比較。只投影原指標、Decimal比較，不重算／改分數排名或建立writer。必要observed-prefix不授官方日曆／availability／歷史PIT資格。

原計畫第8.7允許具名partial research，本包完成有限consumer工程；第10整體階段依賴維持，Backtest18.62%／20%未達，UX18全feature／方法／其他consumer與UX19有界producer／manifest／原子發布／容量仍待。工程缺件不稱為等自然成熟。操作見[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux18-共用日特徵與個股觀察)，驗證與done／partial／pending見[既有QA收據新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。本包不重跑效能／ML／Native1477，不碰正式DB／未知paper檔／還原映射，不清理或push。

## 2026-10-05 UX16唯讀來源契約與UX02 Native中文

新增current-observed來源契約API／CLI，重用loader opt-in時鐘與strict SQL，保存明示cohort、cutoff、scoped rowset/schema hash及main/WAL/SHM身份；錯日期／來源／scope、晚到／無效時鐘、partial與unknown均具名，原caller預設不變。正式D兩檔3日讀取6列，scope齊全但availability、全市場universe、特徵暖機、歷史產業成員與benchmark未授資格；cutoff-screened0列，PIT／formal training／published snapshot false。Root定向21passed、mypy3files、compile4檔與quant guard通過，9個UI blob不變沿用既有UI gate。

四用途Native代表畫面中文清楚無豆腐字；三頁受控DTO，個股用明示hash的記錄唯讀DTO（2382／10-05／331.0／ML unavailable），非新即時來源或模型資格。四輪8個QA PID均退出，失敗與來源identity各自保留。詳見[UX16／Native限定收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

原plan append-only，stage1 Backtest18.62%／20%門檻仍未全過；本包只交付UX16 preflight，不放行UX18新方法或UX19正式writer。下一包需具版本／單位／暖機的共用feature dictionary及增量等價性、decision manifest／整批完整性／原子發布／容量等依賴。歷史PIT缺件不阻擋具名當期研究；不重做1477／效能／learner／producer／全量回歸／清理／push。未知根檔與C:/ta_iso_1005映射未動。本地commit與blob/status核驗後停止交父層。

## 2026-10-05 UX02 共用狀態有限切片

`ui_qt/status_vocabulary.py` 提供純呈現 `status_label`／`status_detail`，明確區分 data／load／research／qualification／event／validation；未知碼保留，completed 不跨維度授予資格。盤勢、持倉系統健康、選股、個股及 Console 的既有入口共用詞彙；Workbench 將時間等待／休市與具名故障分開，回測保留 PASS／WARN／FAIL 並加白話驗證狀態。原始診斷、來源及日期／身份沿原 DTO 保留，沒有修改策略／producer／模型或拒絕 guards。

本包是 UX02 有限落點，非全頁狀態重構或整個階段1完成。Backtest 初始化18.62%仍未達20%凍結門檻；UX16來源／PIT及UX19 writer／容量依賴另列，不以自然成熟阻擋本包工程。詳見 [UX02驗證收據](../06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md)。未重跑效能／learner／Native1477、未producer／清理／push，未知根檔及C:/ta_iso_1005還原映射未動。完成本地commit／blob核驗後停止交父層。


## 2026-10-05 階段1早期SQL取消小包

基於2acdbe2c，四檔backend補Builder→Breadth／Relative service→provider→shared loader取消callback，獨立SQLite分支亦用連線專屬progress handler；SQL確實中止才轉取消例外，真實DB故障不遮蔽，舊provider／Series.map dtype／Decimal／cutoff／排名不改。47 focused、50 UI/Shutdown整合、mypy766及7檔compile通過。Native早期SELECT中關閉：worker仍running時視窗保留，32.77ms至native-finished、131.31ms至hidden、沒有完成snapshot／殘留worker；取消→同來源按鈕重試21.141s正常產生真實snapshot。3個Native場景6個launcher／Python PID全退出，input guard／來源rowset SHA不變。

最終單跑loaded30首屏9.350s、p95 54.173ms、peakRSS618,389,504 bytes、全程13.421s退出；這是spot check，不替換舊5跑median。五跑凍結gate逐項核對：首屏-14.84%、四筆純啟動RSS-18.19%、loaded30+close峰值-57.00%（含提前取消）、p95 49.65<300ms皆通過；Industry42.56%通過20%，Backtest18.62%未達20%（原凍結是兩段各自20%，已更正文案，不放寬或微調湊數）。上包13.349s是全程序時間而非close latency，PID退出證實不是只藏UI。完整normal retry RSS1,456,594,944 bytes與提前取消分列。

詳見[取消與gate收據](../06_qa/PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)與output/qa/product_stage01_20261005/stage1_sql_verified.json。main／view／原初始化優化／profiler的未變blob已核對，舊數字保持其版本身份。沒有重跑五baseline／訓練／producer／大DBcopy／永久清理／push；未知paper檔與C:/ta_iso_1005映射未動。停止交父層。

下一原plan包是stage1／UX02純呈現共用狀態字典，先接Research Console／Backtest，沿用上下文列與分層元件，保留未知碼、狀態維度及結果身份；本包只盤點，未實作。UX16來源能力、UX19容量／writer依賴與自然ML資格分開，不拿自然成熟阻擋UX17／UX02工程。不宣告整個stage1／UX17或全部gate完成，也不盲跳UX18／新ML。


## 2026-10-05 階段1限定效能修正包

兩位指定Luna Max完成7個產品檔及6個test檔修正，root整合；profiler及main未改。日期解析單次memoize、回測／組合首次圖表lazy與可見錯誤重試、同輪盤勢整批近期價格及合作取消／native-finished關閉已驗。同條件5跑首屏10.148→8.642s（14.84%）、Industry3.206→1.842s（42.56%）、Backtest1.098→0.893s（18.62%），完整rowset SHA不變；四筆只啟動RSS約0.70→0.57GB。Loaded30關閉13.349s且worker0；完整盤勢正常完成另以Native探針驗，peakRSS1.452GB不與提前取消0.675GB混報。30列高亮p95 49.65ms不代表全互動速度。

Market61、root loader9（8項重跑）、整合47、Workbench85、validator25／4skip、mypy766、13檔compile通過；唯一Windows fixture長路徑失敗保留，短新Temp重跑1pass。5＋1 Native場景12個launcher／Python PID觀測均退出。來源與資源邊界、code／summary SHA與原始收據見[限定收據](../06_qa/PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)，commit readback留output。原plan append-only，UX01→UX16/17→UX18/19→UX04/05依賴維持。階段1／UX17仍部分完成：早期breadth／relative SQL僅區段前後取消，來源availability／warm-up／PIT／universe／benchmark與自然ML資格未全部完成；不新增方法或UX18 Gate。

1477既有Native驗收不重開，1000×835／125%接受與1000×800限制維持；沒有writer／訓練／永久刪除／push，未知paper檔及C:/ta_iso_1005映射未動。本地commit/blob/status驗證後停止交父層。


## 2026-10-05 最新：原產品計畫階段 0 首包

沿用唯一原計畫，已交付 UX01 有界基線、UX16 來源子集及 UX17 五次 Native 新程序量測；產品程式未改，階段 1 優化未開始。首屏中位數10.148秒、Workbench首次資料10.126秒；30次真實列選取高亮p95=116.60ms，不能當篩選／圖表驗收。IndustryMapper建構中位數3.206秒、BacktestView1.098秒。首次市場探索另觸發重背景切片，總CPU60.94秒／RSS1.57GB、約90秒合作關閉才退出，是下一包工程問題入口；沒有歸因自然成熟或宣稱已優化。

來源矩陣只核對有界正式D讀取與既有QA identity，全市場、暖機、精確cutoff、benchmark與PIT資格未升格。五跑完整性無未允許差異，僅同bytes/hash的SQLite SHM mtime可變；所有本包QA PID退出。外層runner末尾中文print失敗保留，提交版修輸出／CPU命名而未重跑。分工、同版hash、場景分離、限制及下一包依賴見[效能基線](../06_qa/PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)與[來源矩陣](../06_qa/PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)。本包不訓練／producer／永久刪除／push，交父層覆核。

## 2026-10-05 最新：測試暫存可還原隔離收尾

879白名單測試暫存根已同C盤隔離，4,951,450,624bytes檔案配置量前後一致，不釋放容量；372根保留，58具引用根與19占用／權限未通過項未動，r015僅d/e/f成功，g/h/i保留。真實fixture還原／重新隔離與879項metadata核對通過，未永久刪除、未改權限，還原映射與[完整收據](../06_qa/TEST_TEMP_REVERSIBLE_ISOLATION_20261005.md)已保存。

2026-10-05T09:43:35.270504+00:00只讀free：C 237,505,548,288／既有request需求215,285,235,712；D 300,638,941,184／既有formal raw需求295,279,001,600，均點時間PASS。較早容量缺口保留為歷史，不能將本次餘裕歸因隔離，writer前仍重新核對；未producer、訓練、全量tests或正式資料變更。Native1477已接受，不重開；本批交回父層推進唯一原計畫。

## 2026-10-05 09:23 UTC：1477 Native 操作鏈完成

1477 真實隔離 Native 已完成取消terminal→generation3重試（4.5秒）→新身份→保存→新程序同一execution/hash讀回，以及截止日／artifact日期／result-run／index hash四項拒絕。新來源 `rec_e677f9ba56d84a5cbcd6f18d5778a01c`，決策10/5、行情10/2；實際未入選篩選紀錄只供研究。最終可見讀回與拒絕畫面已核對並保存Library，所有本批QA程序退出、桌面釋放。產品程式未改；修正的是driver觀測、sealed config欄位斷言與畫面刷新等待，原90秒上限未延長。下方較早「Native仍缺／需桌面時段」段落保留為歷史，以本節及[完整驗收](../06_qa/NATIVE_1477_RETRY_READBACK_ACCEPTANCE_20261005.md)為最新狀態。

本筆只完成原Native工程接受範圍，沒有增加自然／正式模型、PIT或交易資格。既有learner／資料／UI測試不重跑，未訓練、未跑producer、未清理暫存或push。容量／外部來源與自然成熟限制仍依各自最新收據；後續安全清理由父層安排，永久刪除仍需逐項批准，原唯一推進計畫保留。

## 2026-10-05 最新有界收尾與呈現修正

checkpoint／ML 接線／首屏已有本地提交 `2ca83c3`、`71d70a7`、`cd90844`；`0831633c` 再完成 180 筆 semantic 樣本的真實小型 learner→候選→receipt 工程驗證（受控來源 verifier，19 passed／1 skipped），不授自然／正式模型資格。三張受控圖已交 Library。本輪最小修正 ML 稽核展開／收合文字，按 DTO scope 區別當前／保存 ML 並顯示日期；品質降級有原因就呈現、無原因就明示。affected tests 14、Workbench 85、validator 25／4 skip、mypy 766 通過，Manual 已同步。真實 2382 唯讀 consumer 的 H5 未成熟原因已呈現，offscreen 圖不替代 Native／持倉驗收。

原生 1477 完整取消→重試→新身份→保存→新程序重開及 date／run／hash 操作負例仍缺；本輪只驗原保存來源 41KB 副本的三項完整性拒絕，原 bytes 不變。因不能保證獨立 QA 視窗／modal 不搶前景，未啟動 Native，需短暫桌面時段。容量 guard／cleanup 本輪未重驗／執行。詳細已驗／待驗、Library ID 與本地 commit 邊界見 [最小續接清單](../06_qa/MINIMAL_CONTINUATION_HANDOFF_20261005.md) 最新追補；下方 Batch9 的「未提交」等敘述保留為歷史，不作目前 Git 狀態。

## 2026-10-05 有限續接驗收（Batch9）

最新邊界見 [最小續接清單](../06_qa/MINIMAL_CONTINUATION_HANDOFF_20261005.md)。G11 修後同版七項工程檢查已通過：120 modules、1892 passed／12 Windows symlink skipped，Workbench 85 passed、validator 25 passed／4 skipped、mypy 766＋38、222 paths compile 與量化 guard。原生同股來源選擇、精確保存重開、錯股／不存在來源拒絕、current-ML 往返及 1000x835 四用途內容已取證；1000x800 未過，完整重試的新 execution 身分／保存重開及錯日期／run/hash 原生驗收仍不足。最後一次 probe 在「取消中」提前返回並停止，沒有啟動重試，不改寫原失敗。自然 ML 容量、DNS／正式歷史 PIT／revision 資格仍有實際阻礙，不能宣稱只剩自然累積。目前只凍結 217 個提交候選；未 stage 或 commit。下列早期批次保留其當時範圍，不能代替最新驗收。

## 2026-10-05 G11 第一批定向驗證

現況法人／信用／集保公開 service 已以 1477、2382 真實資料完成定向讀回；候選／非歷史 PIT、未知可得時間、有效零值及明示歷史隔離維持。既有 TDCC 原件以可追溯副本供預設 reader 使用，沒有新 HTTP 或自然成功宣稱。Quick 的 tier／aggregate 保存上限已對齊實際全市場檔案，手動重播沿用既有入口並與排程身份分離。收據位於本機 `output/qa/g11_sol_batch1_20261005/`；原生六情境、全套同版驗收與 commit 尚未執行。

## 2026-10-05 四用途工程補全（最後驗收進行中）

本輪以 `dev`／`13f7a410c2ad850d981ed552ef09515220718ade` 為基線，六個實際使用 Luna Max 的分工與逐批證據集中於 [Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。目前只剩 G11 現況法人／信用／集保讀取及自然保存接線、修後同版測試與原生驗收、容量讀回、文件／本機提交；不新增功能或重訓。

- **資料、選股與研究**：現況月營收／季報、官方估值、法人修訂及官方下市狀態已接入既有 consumer。G6 真實研究週期與十股公開模型讀回已接受；G9 最後 50 檔於 10/4 23:33–23:41 UTC 完成 16／16／16／2 四批。決策 10/5、行情 10/2，台北 07:40 的 entry 全部 pending，沒有本批 capture／outcome／fit。正式歷史學習仍受來源 revision gate 限制。G11 另發現目前個股報告的信用／集保沒有消費既有候選，正在補 reader；不能把這項缺口稱為自然樣本不足。
- **盤勢與持倉**：預設查詢日採臺北時鐘，明示歷史截止保留；判斷日與實際行情日分列。無來源手動持倉仍顯示來源不足／WATCH，可檢視股數、成本、行情與損益。入口頁首誤用最後交易日、未知盤勢得分顯示 0，以及切換後舊提示短暫重疊均已修正並納入 v15 回歸。
- **Forward**：受控更新 172 筆、新增 0 筆，43 事件不變；dry-run 14 項及獨立讀回 24 項通過。52 ready／118 pending，1538 的 H5 9/17／H10 9/24 缺官方收盤價，保持 null 與 `external_source_missing`。原自然失敗收據不變。
- **最後工程驗收**：G11 修前的 `astra-final-v15` 七項全部通過，114 個測試模組 1,818 passed／10 Windows symlink 權限 skip／1 warning；Workbench 85 passed，validator 25 passed／0 failed／4 真下載／合併 skip，mypy 765＋35 檔、213 paths 編譯及量化 guard 通過。原生 v19 實際內容已檢視，QA 持有被延遲釋放的舊 table 而失敗；工具修正與 G11 新驗收尚待執行，未稱六情境通過。
- **自然排程**：10/5 01:12 UTC 的 21 tasks enabled／Ready、設定相符。新 weekly 自然 RC0，後續 current-fundamentals 真實 applied 83,606 values／1,976 stocks，歷史 PIT false；core 保留 pending_human_review。新 Paper 已追加六持倉快照，quote date 10/2、ledger transitions 0。ML 08:30 因容量 guard 失敗；PIT preopen DNS 失敗、postcutoff 缺 verified denominator 分別保留。設定正確不代表所有自然 runs 成功。兩個既有 operational prompts V6 已磁碟讀回，快取重載 unknown。
- **容量與外部限制**：C 上十五份已結束隔離副本的可逆壓縮共節省 17,339,938,160 bytes，內容 SHA／長度／mtime 不變；兩份原 SHA 不符的副本已排除且未修改。01:56 UTC 直接呼叫原容量 guard，C 可用 211,794,477,056 bytes，距自然 ML 原 200.5 GiB 門檻仍差 3,490,758,656 bytes；D 可用 281,570,017,280 bytes，自然 ML 來源卷通過，但正式 bootstrap 275 GiB 仍差 13,708,984,320 bytes。不降低門檻或重播過期自然 run。歷史公告可得映射／單位 basis／正式 revision 資格仍有缺件，須按功能影響判讀；H5／20 交易日及 Paper／Exit 真實成熟樣本繼續累積。

尚未建立本次 commit。未知根目錄 `paper_event_source_capture.py` 保留並排除；QA 原件、DB、runtime 與私人設定不提交。

## 2026-10-03 Operational 品質與研究來源隔離補驗

最新工程驗收見 [行情發布節奏與 Paper 研究隔離](../06_qa/OPERATIONAL_QUALITY_AND_RESEARCH_ISOLATION_20261003.md)。Market/watchlist 日期差先驗官方日曆與專案截止，真 stale/缺價仍 fail closed。6171 以 hash-bound raw「除息」及實際 quote 證明非可比較排除；38 檔 ranking 排除已有具名原因，8 檔 listing/交易狀態未核實。Paper 改為獨立 research lane，保留普通持倉／風險品質，研究 governance 缺件不形成使用者補虛構交易／thesis 待辦。wrapper/child/summary 分別回讀；整體 freshness 的歷史月營收／季報與 availability map 缺件仍揭露，current research 不授正式 PIT。原始失敗與自然 task LastTaskResult 保留；本次無暫停任務、無資料 producer 重跑。


## 2026-10-03 整合修復目前狀態
current-restated 年度 raw、Outcome Direct、B 數值來源、CORE19 訓練／保存、新 Python process 載入推論，以及原 Legacy Pipeline→Bank 研究 sidecar 已取得第三階段受控接受。最終 research model manifest 位於 `output/ml_research/integration_20261002/current_restated_core19_phase3_20261003T064855260194Z/`，SHA `f4f8b70f2da3515089007698c44497ca32fa7b56258cec8880e62e8aa6fe2e2b`；接受收據 `output/qa/integration_20261002/ml_validation/root_phase3_ml_acceptance_20261003T070413001284Z.json` SHA `007d245a4228d9f260ef3e4fd39373ce3eb4c62dac8129e88e29f33f2f8afc9f`。該接受僅限 current-restated／non-PIT 研究用途，不代表正式校準、teacher、promotion、交易權限或投資效果資格；10/2 當日 H5 尚未成熟，報酬與成本維持 null。正式 raw task 於 07:04:44.515124Z 恢復 Enabled=true／Ready，沒有手動重跑正式 raw。

本次工程版號以 `output/qa/integration_20261002/phase3_native/version_native_20261003T103404928459Z/version_manifest.json` 為準，SHA `c625fb658edf9d012f7dce9805a8bb1609b0ea67556df234951179cc7efb6392`（986 個 code files、22 個 inputs）。同版 12-file cross-page 回歸 51 passed，readback `output/qa/integration_20261002/phase3_native/cross_page_regression_20261003T103459276791Z/readback.json` SHA `f39f3114a8a8aff30913d3cd872f0f0294ff6160833dab6f038e23d8ab82d4bf`。統一工程檢查亦通過：Workbench 85 passed；更新頁 validator 25 passed、0 failed、4 skipped；指定範圍 mypy 751 個檔案通過；4 個 Python 檔案 compile 通過；月營收診斷與研究報告文案 8 focused tests passed。readback `output/qa/integration_20261002/phase3_native/final_ui_validation_20261003T103427832370Z/readback.json` SHA `d06b0abd733be4216c90ecd7f66e42f4c70f9ea2332d27778ad2ae122bd0108c`。這些工程檢查不是原生 UI 完成證據；該檢查 readback 的 `native_ui=false`。

c625 原生 UI 驗收已由 root 於 2026-10-03 10:55:41.987 UTC 接受；收據 `output/qa/integration_20261002/phase3_native/root_native_final_acceptance_20261003T105541987127Z.json` SHA `483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`，986 個 code files、22 個隔離 inputs 穩定，並核對 43 筆具名實際觀測 pins；這不是宣稱 43 項全數通過。兩次正常關閉均 exit 0：baseline PID 8756、DPR 1.0、1282×832；125% 成本情境 PID 49556、DPR 1.25、1602×1030。首頁 Decision Desk 保存分析日為 10/2；兩筆本次 Recommendation 結果（baseline `rec_52fb34e4c098485da4ed36d30f7e58cd`、成本情境 `rec_3e78a92cdfc04edf9f18618747fa0c29`）的 request／context／decision 日期均為 10/3；market source snapshot 資料日為 10/2，Live Market 查詢日為 10/3。這些是不同截點，不能把 breadth 數字視為同日矛盾或都當成新結果。候選為 1235、1414；持倉 2330 為 1,000 股、價格 2,500 元，Health WATCH、曝險 10,000 bp。Exit 顯示 owner 尚未提供單股唯讀 read model，因此不推導賣出；entry decision identity 未知是另一項來源限制。成本情境把平均成本由 2,500 元調為 2,750 元、投入金額由 2,500,000 元調為 2,750,000 元，價格仍 2,500 元時毛損益為 −250,000 元（−9.09%），QA 帳本已記錄手續費 3,563 元、稅 0；保存結果在新 Python process 成功載入，並完成 canonical 四方 198 個 Decimal 值讀回。這些數字是隔離 UI 驗收情境，不是實際成交或投資效果。缺價 9999 顯示「資料不足，需核對：缺少最新可用價格」，舊 2330 內容已清除。月營收 1,855 筆候選因 `fundamental_availability.snapshot_mapping_incomplete` 得到 `normalized=0`、一項診斷，failed summary 提供重試控制，但未按 Apply，也未偽造 mapping。

原生收據簽發時記錄 `whole_goal_complete=false`；整體三階段有限工程結案以[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)中的 root 最後接受為準。c625 baseline／成本視窗分別為 1282×832 DPR 1.0 與 1602×1030 DPR 1.25；本版 1017×768 縮放嘗試未成功，先前 7eb 版本的窄視窗觀察沒有重標為 c625。不據此提高 current-restated ML 的研究用途、正式 PIT、來源 credit 或交易資格。

D1–D4 有限修補及 freshness cutoff 邊界已完成定向回歸；原 UI D0／U1–U7 範圍亦完成 Workbench、validator、mypy、focused tests 與編譯檢查。操作說明已補上資料不足／需核對的個股研究文案及月營收 mapping 診斷，不會因候選存在而視為正式資料。

最新每週受控 wrapper run 於 2026-10-03 09:27:03–09:28:21 UTC exit 0，readback `output/qa/integration_20261002/weekly_actual_20261003T092700852463Z/readback.json` SHA `53364a1c330253e2a7afe57f41602cfa20690ddb4aa31b59123e9f6e5dcfb890`。quarterly OpenAPI child 的 26 個 endpoint 回應產生 3,958 筆 raw numeric rows 與 3,950 筆 preview rows；`available_at` 全部為 null，仍屬 current-observed research data。consumer 驗證 parent-child binding；core 為 `pending_human_review`、MOPS `captured_verified`、quarterly `captured_with_review`，仍需人工 review 且 `formal_credit=false`。正式 D DB SHA `d0c843fdef4c36d94ab2a031f3dcd898f3629f207bbfa93ddef8f51e157792a2` 與 0-byte WAL 前後不變；週度資料不取得正式來源接受、公告可得時間、historical PIT 或交易資格。

月營收 UI 的受控診斷案例中，2026-08 候選有 1,855 筆 raw rows，但 `normalized_record_count=0`、診斷數 1、`ready_for_apply=false`，原因為 `fundamental_availability.snapshot_mapping_incomplete`。抓取完成只代表有數值候選，不代表公告／可得日 mapping 完整。缺件對話框、摘要與 log 保留診斷碼、訊息及下一步；未知診斷不放行。個股研究報告也已把缺價格／來源警訊改成資料不足或需核對文案，規則理由與歷史持倉警示優先保留。以上不改正式 mapping、SQLite、推薦或研究判定門檻。

第一階段的 heartbeat prompt 與 21 項 task 設定已讀回；不能據設定或受控 run 推定 21 項 LastResult 全部成功。信用候選的正式來源資格與 historical PIT credit 仍為 false；Paper seed、信用、基本面、人工 review 與其他來源各依自身權限與證據判讀。詳細歷史、失敗收據與接受範圍以[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)為準；操作入口看[完整手冊](../07_guides/APPLICATION_MANUAL.md)。

## 歷史：2026-10-02 至10/3早期整合修復檢查點

以下段落保留各次驗證當時的待辦與範圍，後續完成狀態以上方目前狀態為準。

UTC 10/3 `03:46:39Z` root 對已凍結的舊研究 Direct／OOC fold與raw CLI摘要完成獨立回歸：45 passed／1環境symlink skip，39個程式／測試pins前後相同。研究fold現按purge後實際distinct訓練日資格計數，不足門檻的窗口不計入至少四個fold；raw摘要只列已發布manifest。另High對純outcome訓練器／CORE19計算器完成31個有限spy／數值檢查，九檔pins相同，沒有真fit或模型保存。Bridge的完整905日組裝、TWD轉minor、模型保存／載入與Legacy／Bank仍待完成；不外推這兩項有限結果為整鏈完成。

UTC 10/3 `03:21:47Z` 新 outcome Direct 真建置完成，`03:23:16Z` public verified loader與獨立原價重算接受1,796股票觀測／49來源特徵／6,709 labels。905個benchmark事件位置保留，8 folds實際train至少179日、test各63、purge60、相鄰embargo5；T+1／H5／10／20／60與gross差額扣80bp全部相符。新來源ref納入source_id，價格本體與因果ATR／ADX派生列皆在custody內，正式PIT／teacher／投資效果資格不變。這是Direct輸入工程完成；CORE19、模型保存／新行程推論及Legacy／Bank仍待完成，raw task尚未恢復。詳細版本與readback依整合修復紀錄。

使用者已授權依序完成排程修復、Gemini ML 獨立驗收與既有產品收尾。第一階段可獨立完成修補已取得對應實跑／讀回，現進入第二階段；不能據較早摘要宣稱整合完成，接手與驗收證據見 [整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。兩個相關 heartbeat prompt 已實際更新並讀回；21 項 task 的 repo WorkingDirectory 已套用、其他既有設定已核對保留。Paper／ML 盤前改為台北 08:25，兩項 task 於 23:39:49Z 恢復啟用。Evidence 第二次受控 dry-run 已產生 report／summary，日期 hash／strict Exit sidecar／canonical consumer 通過，來源 DB 完整 bytes、大小與 mtime 不變；持倉警示／風險提示 readiness 仍受阻，整體 LastResult=2，不以工程修補當成產品全綠。

下方 10/1 ML 的「18 passed／A、B 貫通」為 Gemini 交接宣稱。UTC 10/3 兩份 Sol High 獨立審查已收口：18 tests 確實通過，但沒有 fit／save／load／infer；確證 revision custody、fold、正式根隔離、數值保存／scale、compact 日期與 downstream 接線缺口。root 已完成單一唯讀 transaction 的真實一致 SQLite 備份與來源前後 pins，這只證備份 bytes，不授歷史 PIT／來源資格。B 修後生產 CLI 已真讀回 1,962 筆／7,658 個值，獨立 Decimal 比對與來源 hashes 前後相同；僅數值觀測 ready，Direct/OOC 仍因 context／成熟標籤不足受阻。`01:44:40Z` root 真實原 DB／副本驗證已通過 completed pending 配對、原 34 檔 inventory 及同次讀取的 27 dependency roles（包含 19 個外部來源檔），來源與 snapshot receipt 未改動；仍是 current-restated、historical PIT=false。Direct outcome 已完成真建置與公開讀回（見下方補充）；CORE19、模型與 Legacy／Bank 接線仍在實作；B dependency fixture 已同步，root 在01:48 UTC獨立重跑22 passed。正式 pointer、active V2 模型、formal gates 與 research-only 邊界保留；受控真實訓練與 Legacy／Bank readback 尚未完成。

最新補充：High 在第二次 raw 後驗確認合法千分位價格被誤判 invalid，成交金額 TWD 元值亦被標成 minor；A 已最小修補。`02:48:01Z` 原年度 raw CLI 第三次受控執行 exit0／stderr0，root 再完整讀回四個年度 gzip shards，52 個來源欄位、73,234 筆觀測及 281,699 個數值的 hash、數值格式、masks 與真時鐘相符；invalid quarantine 已為 0，保留一個原 OHLC 真 null 來源及兩次觀測。觀測數包含產業／大盤 context，不是股票訓練 samples，代表 SQL 數值後驗已核對32/32，合法千分位來源的152個OHLC值及TWD單位亦相符。B 的 2317／2330 七欄另與同一一致副本精確匹配 14/14。首次 raw NameError／exit1、QA helper 的 MappingProxy 讀取錯誤與過長 basetemp 的 WinError206 皆保留歷史紀錄；修後 price contract／raw／CLI 三路由獨立回歸 64 passed。此段記錄 raw 完成時的範圍；後續 Direct 接受見下。CORE19、fit／save／新程序 reload／infer 及 Legacy／Bank 實跑尚未完成，raw task 暫停仍須在驗收後恢復。

UTC 10/3 Paper／ML forward 於 `00:25` 自然觸發，真正等到 Taipei 08:30 後均以星期六 `skipped_non_trading_day` 終止；`00:30:21Z` 原生 COM 核對 Ready／LastResult=0，producer／terminal／selection receipts 綁定相符。正式 16 個 pointer／manifest、active V2 全 39 檔及市場 DB bytes 均未變，這不授新交易日 capture／fill／credit。另為修訂匯出程式驗證暫停 `baldr-ml-raw-pit-refresh-daily`（本機 05:05 task），原 Enabled=true 已備份，修後須恢復；它與台北 08:25 的 forward task 不同。完整證據與當前限制依整合修復紀錄。

23:56 UTC 原生完整讀回確認 21 tasks 全部 available、actions／schedules／working directories 相符、configuration_ready=true；部分套用時最後三個空 cwd 曾漏判，已修後逐項讀回。TDCC 23:47 UTC 真實 CSV 擷取取得 10/2 資料 4,078 筆並寫入 candidate，23:52 UTC freshness 手動重跑及 consumer 已讀回 current。信用交易 10/1 stale、正式基本面缺期與 current-observed 覆蓋 partial 仍如實保留；正式 DB 完整 hash／大小／mtime 未變。quote 相容路由 root 47 passed／1 skipped；推薦狀態分類 root 36 passed，真實 canonical 200 檔中顯示可用 15／策略排除 185，保留原 missing=0／degraded=185。研究用途、資料品質與工程執行狀態分開，沒有改 hash／門檻或升格正式 Advice。

## 歷史：2026-10-01 台北時間接手現況

下列為本輪已讀回的 latest／專項 receipt 狀態；較早 9/30 排程 matrix 是當時點的歷史，不因時鐘到達自動更新。程式／測試驗收、受控 probe、自然 Task 與 business qualification 分開判讀。

- **Paper／1418**：使用者已明確說沒有 1418 持倉。已讀的 9/30 Paper snapshot `paper-main-20260930` 中 1418 是機器初始化的 research seed，不是使用者真實持倉；不可要求使用者補其成交、entry 或 thesis，也不可據此推論使用者其他持倉均為空。05:15 Evidence 收據把 identity/thesis 警告列在 Paper Health/source-quality lane；`portfolio_alert_snapshot_quality_not_ready` 和 `risk_prompt_snapshot_quality_not_ready` 是另列的 snapshot-quality blockers，需各自查來源，不能改寫成使用者欠 1418 資料。此 seed 的研究驗收／Health transition／verified 與 Formal gate 仍未解。低階研究 capture 可先持續記錄，不等於補造 Paper 成交或通過上層 gate。
- **Paper／ML 16:15 Pacific runtime**：10/1 Taipei 08:29:16（9/30 PDT 17:29:16、台北 08:30 cutoff 前 44 秒）的 inventory `output/qa/scheduled_task_inventory_20261001T002916Z_940402272834.json` 為 52,144 bytes、SHA-256 `9bbe91e9c6b1cc723222e87cd92a9751e8ff9985de9f3d7f4f76c2946193e374`；21/21 exact root task paths、0 errors。對應 9/30 Pacific 16:15 trigger（10/1 Taipei 07:15）的 Paper portfolio 與 ML forward Task 均 Ready、`LastTaskResult=3221225786`（`0xC000013A`）；runtime 是 `waiting_for_taipei_cutoff`、`terminal=false`，heartbeat stale，latest 仍是前一日。截止點前的清冊與 runtime 尚不足判定後續原因；Paper XML 未明列 ExecutionTimeLimit，ML forward 為 PT2H、兩者未設 delay，operational logging disabled，這些設定也不能證明中止原因。不可用舊 latest 推定通過或失敗；這與 Paper EOD 06:00 no-work receipt 是不同 Task／lane。
- **05:15 Evidence 與 05:25 capture**：9/30 05:15 PDT Evidence latest status 為 `degraded`／exit 0，SHA-256 `6217e7983df9a13bd81aa6c30cf76a411313001fdc4445e3cc8cbda8fbef4c6b`；自然成熟 warning 為 `INSUFFICIENT_SAMPLE`，另列上述 Paper／portfolio snapshot quality warnings。9/30 05:25 PDT 原生 Task 已實際持久化 Decision/Evidence `passed` receipt，run `20260930T122502721503Z-9dd2d94b9b6c`，latest status SHA-256 `a3e3e0eec25471d03b4a156d2525882a406aaebf9bae9e0cea29927e90b455fd`；`capture_mode=eod_research`、`research_only=true`、`natural_authority=false`、`preopen_authority=false`。這是可保存的低階研究事件，不授 Health transition、verified 或 Formal qualification。
- **Freshness**：核准的受控 read-only probe 綁定 Quick run `20260930-32560` 的 status 與唯一 history row；Quick receipt identity 是 `verified`，但此狀態只證明同次 terminal identity。Freshness 仍為 `degraded`、probe exit 0、calendar network fallback 0，保留月營收／季報 expected-period 與 current-observation 4 項 warnings；DB/candidate DB 等 16 項輸入前後一致。這不是下一次自然 Freshness Task 驗收，詳見[Freshness QA](../06_qa/SCHEDULER_FRESHNESS_QUICK_BINDING_20261001.md)。
- **基本面研究候選**：9/30 官方 TWSE+TPEx 月營收 response 建立完整 1,978 檔研究 scope，候選 availability date 保守標為台北 10/2；1,978 筆 availability candidate、3,810 筆 no-apply merge preview、Formal/unit acceptance 仍 false。MOPS 有兩個不同證據：較早 8 月 availability bounded diagnostic 是 15/15 queries、3,150 events，legacy artifact 無成功 HTTP entity custody；另 9/30 最近完整 7 日 capture 為 6 query／36 events 與 36 projection rows，保存 6 份 HTTP entity raw 共 16,506 bytes。其 artifact 本體 57,850 bytes，位於 `output/research/mops_statement_availability/run_20260930T221808809646Z/mops-statement-availability.json`，SHA `7a50834e63d9429ef23b3716c38cd69d75b6881df1309a25a20fd574fa70f57d`；raw capture receipt SHA `49b37a3f4619dcee4f592f53866819a84a78bf93b56f8a1c4b57328d85affbce`。10/1 季報 OpenAPI collector 以受控 standalone CLI 實際跑一次 26 GET（2 catalog + 24 數值 endpoints；尚非自然 weekly Task child），取得 3,960 raw rows、3,952 preview rows；8 列留在 review（6 key review、2 schema review），不是 official no-data。一般金額單位、issuer denominator、合併／個別 basis、歷史 announcement availability 與 Formal/PIT 仍未接受。各自限制見[基本面 bootstrap QA](../06_qa/SCHEDULER_FUNDAMENTAL_BOOTSTRAP_20260930.md)、[MOPS／來源盤點](../06_qa/FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md)與[季度 OpenAPI QA](../06_qa/SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)。
- **PIT taxonomy**：10/1 自然 07:00:29 台北 Task 因 missing capture-attempt path guard 保持 blocked，`network_attempted=false`、`new_attempt_created=false`；這不是新捕捉失敗，也不代表既有 bundle 無效。其後以保存的 config materialize late proof，再對同日已保存 bundle 作隔離 reuse，07:19:48 台北完整 readback 通過，狀態 `machine_verified_candidate`、0 HTTP／0 new attempt、Formal flags false。後續 proof/reuse 不回寫原自然 blocked status；跨日資格未建立，Rule scope mismatch仍是 Formal gate。官方 universe 1,988、Rule candidate 1,932，scope 不相容。詳見[PIT QA](../06_qa/SCHEDULER_FORMAL_BOOTSTRAP_REPAIR_20260930.md)。
- **ML 交接主張已被獨立審查修正**：Gemini 當時新增上述年度／Direct／OOC 與 B adapter 入口，並宣稱 18 passed／5 folds／838 rows／全鏈路補齊。獨立重跑只證 synthetic 建置；沒有修訂 receipt 的 A fixture 不證 revision-aware，B consumer 只保存索引而丟失真數值，亦未 train／save／load／infer。正式根隔離與 receipt 驗證確有缺口，不能以宣告欄位證明正式資產未變。目前修復與真實驗收以本頁頂部及[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)為準；原[單日投影 QA](../06_qa/SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)、[hook QA](../06_qa/SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)保留其各自來源捕捉範圍。

## 2026-09-29 排程完整審視與修復

[21 項排程審視](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260929.md) 已核對 Windows
註冊／wrapper／時間，並修復 query inventory、same-day Evidence result binding、verified
technical receipt reuse、PIT taxonomy 接線／clock／coverage scope 及 ML 等待 heartbeat。
程式修復與唯讀來源 probe 不代表今日舊 failed receipt 已通過；自然排程重驗仍待後續。
容量、錯過的 Paper 凍結批次、machine-only Paper seed 的 thesis／identity、基本面 PIT lineage、Formal 與 ML
custody 的真實缺件仍保留，不刪原始資料、不補造成交或授予 formal／broker credit。

## 歷史：2026-09-30 初始受控排程修復進度（資料截至 Evidence #1）

附件七項排程修復由 `/root` 審核、規劃與驗收判定，三個 Luna/max subagents 實作資料／Quick、第 2–3 項 Recommendation、第 4–5 項 Paper。TWSE 9/16 缺方向／漲跌數值的拒絕收據保留；最小 nullable parser 與日期範圍 marker 修正後，focused regression **92P／1S**、四檔 mypy、七檔 py_compile 與 scoped diff-check 通過。既有 Quick Task 於 9/30 01:49 PDT 人工觸發第三次，10 日窗口 verified no-op 10/10，status=`passed_with_warnings`；技術 publication 9/30 為 1,967 rows，Freshness coverage 1,967/1,967 eligible。既有 Freshness Task 02:08 人工執行、Task exit 0，但 status=`degraded`，原因是正式月營收／季報落後與 current observations 部分覆蓋。Recommendation Task 02:19 exit 0、canonical `rec_49b04a59aa234283a8e47263de718f3a` readback passed，並產生 9/30 Paper frozen source；Evidence Task 02:30 exit 0、同次綁定該 canonical，但 business status=`degraded`，當時列有 fundamental expected-period unavailable、兩個 portfolio/risk snapshot-quality gaps，以及 machine-initialized Paper 1418 seed 的 identity warning。這些都是早於 04:20／05:00／05:10／05:15 的受控執行，不代表自然排程已驗收；1418 不是真實使用者持倉，不要求使用者補該代號成交或 thesis。稍後一次 Paper EOD Task 安全 no-op（LastTaskResult=0、無待執行來源、positions／ledger 前後 hash 不變），未消費 9/30 frozen source、沒有 9/30 成交成功證據；Evidence #2 以 `transition_proposal_persistence_blocked:ValueError` 終止失敗（Task result 2），BankTaiwan #1 以資料依賴失敗終止（Task result 2）。基本面候選與 Formal denominator resolver 有 bounded QA readback，但不代表正式 apply 或 Formal credit。完整後續收據與未解 gate 見[排程修復 QA](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)。

## 歷史：2026-09-30 排程狀態（terminal 證據核至 05:04:20.581929 PDT）

原生 21-task inventory 在 04:53:25 PDT 唯讀核對 21/21 unique tasks 的設定與狀態；較晚執行只按各自 terminal receipt 補充，未將其外推為 21 項全過。自然 Quick `20260930-32560` Ready／LastResult=0、`passed_with_warnings`，technical publication 1,967 rows／rowset SHA `24ecb98a00bd86af6d0a08639b9642b9a3fdf0833dd206a954ad280b4ee574e8`；唯一 warning 是 Phase3C candidate-only margin／credit 子來源缺少 9/30 有效資料、保留 1 項 retry，沒有新增資料列。自然 Freshness 05:00 Task result 0，但 status=`degraded`、4 warnings；正式月營收／季報落後，且 Freshness 未保存 Quick run_id／status hash，只有同日時間關聯。自然 Official events status=`published`、9/30 as_of、28,725 canonical events／1 new，status 回報 `publication_scope=formal_historical`；僅巢狀 `corporate_action_adjustment_custody` 標示 `prospective_only=true`，且 `formal_source_contract_eligible=false`、`historical_pit_eligible=false`，未解除 ML formal／historical source gate。Paper EOD 是一次安全 no-work，沒有 9/30 fill／EOD成功證據。Evidence #3 工程驗收通過（5/5 transition reuse），business status 仍 `degraded`／readiness=`not_ready`，有兩個 portfolio/risk snapshot-quality gaps與 machine-initialized Paper 1418 seed identity warning；這不是使用者真實持倉或待使用者補成交/thesis。BankTaiwan #2 barrier／工程 readback 通過，但 child 因正式 market revision／source contract gate `failed_dependency`、exit 2，沒有 training。ML forward 9/30 child仍被 stale release source revision阻擋；PIT sector sidecar獨立 ready且consumer-compatible，combined taxonomy bundle仍受 Rule 1,932／official denominator 1,988 mismatch阻擋。完整 identity、hash、QA範圍與未解 gate 見[排程修復 QA](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)。

## 2026-09-29 WP5 目前 HEAD 缺口盤點

以 `dev` commit `447202fca5ed453f4c0bb399c1c3156c66cef146` 為稽核基準的 [WP5 缺口與 19 筆 pending 逐筆診斷](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md) 已完成。舊 final scoped route 的 31 個 SHA pin 中，29 個仍與該基準的原始程式／測試 bytes 相同，兩個差異是後續更新文件；受限路由 183P／2S 可引用，但沒有修補後 full-suite 通過證據。舊全套 274F／13E 已按失敗節點分類，三個代表節點在該基準做小範圍重驗；推薦進度測試的過時契約已修補，整檔隔離 **8P**，尚不能外推全套。

m11 的 19 筆仍為 pending／0 matured：Stage C 在決策日 9/29 凌晨 01:13（台北）執行，缺當日 TAIEX 基準收盤及 20-session proof，未進入逐股端點價／成本核驗。18 檔隔離日價最新 9/24；`1441` 只到 9/16，9/17–9/24 計畫開市日無該股列，停牌或來源漏件尚未判明。成本僅固定 50 bp 假設，after-cost unavailable。正常交易日真 child、OS 前景 UI、自然成熟成效與完整測試仍待驗；MOPS prospective 來源保持獨立原型線。

同日後續 WP5 小範圍驗證：Position Health 合成 calendar／DB fixture 修補後整檔隔離 **15P**，精確 source-time blocker 斷言已到達；這只涵蓋 cache 在 `OBSERVED_AT` 當下有效的情境，不驗今日時鐘的回溯快取。路徑分流的 MOPS batch、materializer、calendar raw custody 各 **1P**。Live research gap 舊 **1F** 是修補前結果：`_run_capture` 傳入已含 `_test` 的 roots，`PROFILE=test` 子 CLI 再加一次 `_test`，因而未讀到 seed position、`gap_observations_created=0`；helper 改傳 parent base roots 後，root 在 `%TEMP%\pytest_wp5_gap_root_<uuid>\pytest_basetemp` 所需 OS TEMP 父目錄建立後重跑整檔 **4P，exit 0**。首次因 basetemp 父目錄不存在而收到 WinError 3，屬測試 setup 未完成。WinError 5 三個歷史代表節點在 OS TEMP basetemp **3P**，expert 節點另在 repo-local basetemp **1P**；目前未重現，根因未確證。Hash/readback 舊桶 11 個 R027 節點停在 `_frozen_direct_stable_identity` payload hash assertion（實際 `9e474…`、固定 `0b23…`），未進 gate/readback；目前 HEAD `97231b24` 的三個 OS TEMP 隔離代表 **3P**，相關 tracked inputs 無 diff，歷史差異原因未確證且不外推全套。Runtime API 桶的兩個 `current_execution` 舊 test-double 節點補 execution+verified ID 後，match／empty／mismatch mock gate **3P，exit 0**；真正 canonical readback 另由 m11 驗證。舊 `reader_status` 精確節點 OS TEMP **1P**，路徑症狀仍屬未證實推論。相鄰 `test_task_loop_07_contract.py` 整檔 OS TEMP **18P/2F**（no-follow `WinError 5` 指向 `C:\Users\archi\AppData\Local\Temp`）；兩個失敗節點改 repo `output/qa` basetemp 並設定 `TEMP`／`TMP` 後 **2P**，不證明根因或 full-suite 通過。TWSE 年度表與新年度快取僅能確認 9/30 排定開市，臨時休市覆蓋及同日更新／snapshot／pipeline pair 仍待執行日證明。完整全套 FAIL 裁定不變，細節見同一 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

9/29 收盤後續查：年度表只確認排定開市；正式 SQLite 與既有 QA snapshot 的 `daily_prices`、`technical_indicators`、`market_indices`、`industry_indices` 四表最新均至 9/24，9/29 列數均為 0。後續記憶體內官方 HTTP 回應觀測到 9/29 個股／TPEx 當日列，但原始 bytes 未保存、沒有 durable custody；同日 canonical pair 仍缺，正常日真鏈未通過。首輪正式 DB→新 `output/qa` 的唯讀 online backup 因異常反覆讀取而中止，未產生成功 seed；來源 DB/WAL 的前後大小與時間戳一致，但唯讀 `mode=ro`／`query_only=ON` 監控連線的 `PRAGMA data_version` 曾在短查由 `2→3→4`，後續同連線又由 `3→21`，顯示期間持續有外部提交，未能確認 writer-idle 時段。其後另以固定 QA snapshot 建立 seed root `output/qa/wp5_verified_snapshot_seed_20260929_01`，bootstrap receipt 成功、全檔 readback SHA 相符且 `quick_check=ok`；但 `ready=false`／`preflight=false`，Look-ahead 僅檢查四表所選日期欄，官方 PIT 與正常日鏈仍未成立。bootstrap wrapper exit 1 且未保留子程序 return code，不宣稱 CLI exit 0；沒有 updater、recommendation snapshot 或 learning child receipt。舊正式備份中止目錄保留，沒有第二次正式 DB 備份；細節見 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

初次 9/29 正常日 pipeline preflight 為 **NO-GO**，未執行 quick updater 或 pipeline dry-run。TWSE OpenAPI `FMTQIK`／`MI_5MINS_HIST` 約 12:12 UTC 可讀但最新日期僅 9/24；TAIEX 5 分鐘 HTML 有 9/29 指數列，不能證明個股／TPEx 同日來源可得或臨時休市 gate。初始 no-go 檢查時 quick updater 使用 repo-level 預設 calendar cache，未傳 `temporary_closure_path`；之後新增 explicit calendar flags 與 pipeline 傳遞，但其 closure gate 仍未滿足。candidate DB helper 在 process env 空值時可讀 HKCU，pipeline 繼承環境未清除 PIT／candidate 外部路徑。`PROFILE=test` 又會為指定 roots 加 `_test`；`PROFILE=prod` 加 QA roots 只是未執行候選。後續雖已觀測到官方 endpoint HTTP 回應含 9/29 個股／TPEx 當日列，原始 bytes 未保存，沒有 durable custody 或可核 source-time；仍須隔離外部路徑、補 source-time 與 closure evidence，才可評估 dry-run。全套 FAIL 裁定不變，細節見 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

後續唯讀 preflight（`data_module/wp5_daily_chain_preflight.py`、`scripts/qa_wp5_daily_chain_preflight.py`、`tests/test_wp5_daily_chain_preflight.py`）root **11P**、compile 通過；固定 seed 實查 exit **2**：seed verified、isolation bounded verified、day blocked，缺 annual calendar、closure receipt、source-time receipt。DB 為 ro/query_only、`st_nlink=1`、identity stable、無 sidecar，SHA-256 仍為 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`。CLI 未接 scheduled runner，stdout 未保存成 durable receipt；path／hardlink guard 不防 preflight 與 runner 開檔間的並行 namespace race，因此只屬 seed-only bounded check，不解除真鏈 **NO-GO**。

稍後官方 HTTP 回應在記憶體內觀測到 9/29 TWSE MI_INDEX、STOCK_DAY 2330，以及 TPEx dailyQuotes、tradingStock 6488 當日列；endpoint、capture end、回報的 body size/hash 詳列於 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。原始 bytes 未保存或獨立讀回，metadata 不構成 durable custody 或官方發布時間，也未補 source-time／closure receipt 或同日 canonical pair。下一包須 create-only 保存原始回應並由 validator 驗證；正常日真鏈仍未執行且 **NO-GO**。

Calendar injection 僅屬準備性接線：未指定旗標時保留舊行為；明確 QA override 會關閉隱含 online probe，但事件型 closure sidecar 對一般開市日仍是 `not_captured` 並必然 fail closed，單獨指定年度 cache 也不等於休市 gate 通過。作者 focused **5P**／quick **25P**，root quick **25P**、pipeline 傳遞 **2P**；兩測試檔合跑 **48P／7F**，7 項均回報 snapshot stdout artifact 類症狀，但未逐項完成基準對照。僅一個代表 pipeline same-day-reuse 節點在 patch 前 `fef56b93` 與 patch 後的同長 basetemp 下同訊息失敗，短路徑兩版均過；其餘失敗未逐一等價比對，不能將代表結果外推到全部 7 項，也不能稱兩檔或 full suite 通過。quick updater 主程式在 calendar gate 前仍有 operational writes，未執行真 updater／pipeline；candidate DB／PIT isolation 仍未解，原 preflight **NO-GO** 持續。詳細範圍與獨立審查結論見 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

Candidate update 的 `--skip-candidate-update` 是另一項**準備性**路由：root quick updater 整檔 **26P**、pipeline child invocation **2P**。明確 skip 會在 path resolver 前略過 process env／HKCU lookup，不呼叫 candidate updater；未指定時保留舊路徑。若 capacity 或 calendar gate 提早 return，receipt 可能沒有後段 candidate step，但 skip 仍不解析路徑或呼叫 writer。它不隔離外部 PIT／closure sidecar，也不證明 source-time；真 updater、pipeline、snapshot／learning child 與正常日真鏈均未跑，原 preflight **NO-GO** 不變。細節見 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

9/29 m11 OS 前景隔離嘗試未驗：QA run `output/qa/personal_daily_product_20261006/personal_research_ui/wp5_os_m11_20260929T103544Z/` 保留；manifest SHA-256 `e814cfcc089038f4f281793d87b81428b449b66fa0dcb68684bd2dd646468b49`、working DB SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`、learning tree pin `3b84158f9ab5edb9420fbcbbc427f0d80ea675fa13a5a741a26824fe8d0f1105`。Windows MainWindowTitle 為 `個人研究 QA｜隔離資料工作區` 且 `Responding=True`，但 `@oai/sky` 的 `list_apps()`／`list_windows()` 無唯一可操作 Window；Ctrl+C 後 launcher exit `1`，無 launch／visible receipt、無 OS screenshot（無時間／路徑／hash）或 UI 輸入，所有 model journey 未驗。QA run 保留，Formal 未寫；後續需取得可 target 的互動桌面會話／人工可見操作，再重驗。詳見 [WP5 診斷附記](../06_qa/WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md)。

## 2026-09-28 WP5 最新驗證狀態

三項 test-only 隔離修補後，以單一 31-path source/test/doc freeze manifest 重跑 WP1–WP4、4-node 同程序環境控制與 inventory：**183 passed／2 skipped／0 failed**，audit 為 1058/1058、無 missing/stale 或 documentation drift。Workbench 84 passed、Update QA 25 passed／4 skipped、mypy 735 files 無錯、22 個變更 Python 檔 compile 通過。第一次較長 basetemp 的 WP4 route 保留一個 Windows `os.link` WinError 3；同 node／整個 WP4 及共同最終 route 改用短 basetemp 後均通過，細節與限制見 [WP5 current checkpoint](../06_qa/WP5_CHECKPOINT_CURRENT_20260928.md)。一次 8,682 項 full pytest 在這些修補前自然結束但 **FAIL**：274 failed、8,378 passed、17 skipped、13 errors；修補後未重跑 full suite，Boundary 乾淨 HEAD 抽查亦確認另一個未改測試仍有 test-double API 缺口。這些 bounded 結果不代表 WP5 完成。

正式 D 以唯讀方式做 before／after 比對，DB/WAL/SHM size 與 mtime、大盤及產業 CSV hash 均未改變。正常開市日 WP1 真 child、WP2 下游 capture time／官方 PIT、自然 outcome 成熟及 OS foreground UI 仍未驗；目前 Stage C 是 19 pending／0 matured，after-cost unavailable。上述 scoped route、full-suite FAIL 與待驗範圍不改寫下方既有歷史裁定。

**2026-09-27 R031 attempt6 限定工程驗收已通過；本文件是提交前snapshot，staged review與commit結果以Git history及root最後交付為準。** R031 attempt6的288-path relevant regression及mandatory checks已由root接受。 R027使用者接受的logical-time revision B與R028 scoped migration各自通過獨立gate；原R027 strict仍INCONCLUSIVE，舊oracle、strict receipts與R028 legacy comparator diagnostic FAIL均保留。IndustryMapper明示providers、H5 app初始化前置條件及其受影響路徑已納入current route並通過。attempt6不代表正式資料、native UI、scheduler、未知artifact或model promotion驗收，亦不是 WP5 或 full-suite verdict。

## 2026-09-28 m10 個人模型 Qt widget 驗收更新

較早 checkpoint 所稱「native／個人模型 UI 尚未驗」是當時狀態，現由隔離 m10 旅程更新：使用者明示來源時間的研究候選已經真 MainWindow Qt widget 操作，完成 V2 保存、推薦、canonical result/readback、capture v3、cold restart、停用、fresh-source revision rollback 與最終 `rule_only`。這是 Qt widget 自動化證據，不是 OS 前景視窗或桌面截圖證據。Outcome 對同一 capture 的 Stage C 結果為 `completed_with_pending`，mature 0、pending 19；來源／成本尚不完整，沒有 outcome artifact、publication、global evidence 或 promotion。模型仍是 user-declared research-only，`official_historical_pit_verified=false`；沒有官方 PIT 或成熟績效證明，WP5 仍未整體完成。

細節及 SHA 請見 [m10 Qt widget 個人模型驗收報告](../06_qa/PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)。

## 2026-09-27 audit／bounded slices current checkpoint

### 個人日常產品與個人模型安全狀態（2026-09-27）

個人模型安全預設保持 `rule_only`：inventory 中兩個舊候選都是 `legacy_unproven`，不可啟用。使用者已明確選擇 V2 指定 SQLite 來源時間信任的個人研究流程；這不是外部 authority 回覆，也不構成獨立官方歷史 PIT／publication-availability 證明。現況仍沒有已證明可合法准入的真實 PIT candidate。company-registry sidecar 的 `available_at` 是 HTTP response capture 完成時間，不是官方 publication time；該 bounded provenance 不能替 industry-index、上市櫃或興櫃 coverage 背書。

本輪可引用的 scoped evidence：WP1 Bank snapshot identity/bounded reader 17P／2S（symlink 權限 skips）；WP2 company-registry slice scoped accepted；WP3／WP4 個人 UI/policy/source slices scoped；Stage B／C 31P／1S；Workbench 84P、Update QA 25P／4S。這些不是自然 scheduler、native post-fix UI、真實合格模型或完整 daily→capture→outcome 驗收。StageC outcome.v2 的 model metric 僅含 active rows；fallback 留在 delivered-cohort coverage，不當作模型預測。其標籤是決策日收盤至官方 20-session endpoint 收盤的事後 close-to-close 結果，不是 execution PnL；after-cost 為估算成本，所需成本／流動性資料不全時維持 pending／unknown。

source/PIT admission 最終測試數及 hash 尚未凍結，狀態為「待最終整合收據」；root 將追加最終 relevant regression 與 mandatory check 結果。不得從目前切片推定正式 source trust、自然成熟或個人模型可用。

### 2026-09-28 最終 relevant regression 更新

前段「待最終整合收據」記錄的是 2026-09-27 狀態；root 現已完成 302-path relevant route，收據 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T061833_712310Z/run_receipt.json)，SHA-256 `3a830dd73a2a8a88903c42211149fb4f1a298b9aeea9e4e606bfdf43fe1aee62`，`overall_candidate_pass=true`。302 個測試檔分為 298 repo-short-TEMP 與 4 OS-TEMP，兩組互斥且聯集完整；合計 3,218 passed／9 skipped／36 warnings。Workbench 84P、Update QA 25P／0F／4S、mypy 737 files、332 個 Python compile paths 與 `git diff --check` 均 exit 0；HEAD `e5d75f7cbd3312dac391f52b5c2206d0c745bbc4`、工作樹狀態及 route scope hashes 前後一致。細節見 [個人日常產品交付 QA](../06_qa/PERSONAL_DAILY_PRODUCT_DELIVERY_20261006.md)。

這是隔離的 relevant regression 與靜態／工作台檢查，不是正式資料操作、可見 native post-fix UI、自然 scheduler 或真實合格 PIT candidate 的驗收；預設仍為 `rule_only`，兩個 `legacy_unproven` 候選仍不可啟用，WP0–WP5 不因此宣告整體完成。先前 failed／interrupted route 收據照原狀保留。

### 2026-09-27 個人 V2 使用者明示來源信任更新

本段補充本 checkpoint 較早寫下的「沒有使用者來源信任回覆」狀態：使用者已明確選擇「信任我指定的資料庫」，UI 因此提供 V2 `user_declared_source_time` 個人研究設定。這不是外部 authority 回覆，也不把使用者指定 SQLite、replay 一致或內部 hash 轉成官方歷史 PIT 證明。預設仍為 `rule_only`；inventory 的兩個 `legacy_unproven` 候選不可啟用，現況沒有已證明的真實 PIT candidate。

V2 預覽與執行重驗綁定候選 pins、檔案身分及實際訓練切片（訓練窗資料列、`available_at`、來源契約、成本與 scope）。本次僅在 `coverage.source_contract.technical`、`source_disclosures.source_contract.technical`、`source_disclosures.technical.source_contract` 三處 technical contract 投影中排除 `content_digest`、`content_row_count`、`coverage_end`、`evidence_hash` 四個全庫彙總欄；另不把 replay 結果最外層的 `dataset_id`、`dataset_hash`、`source_fingerprint` 三個由全庫 source fingerprints 衍生的識別欄納入此來源切片比對。上述例外以外，其他來源與欄位仍依原契約比較；候選已保存 manifest/pins 與逐筆樣本仍獨立核對。這項 V2 個人來源切片比對不改原 replay manifest 或 global oracle。訓練窗後的更新在同一檔案身分且該切片完全不變時可保留驗證，檔案替換或訓練切片改變仍 fail closed。使用者須明確指定來源、檢查預覽、確認並保存；重啟後需重新驗證。V2 僅供個人研究，不影響 global pointer／promotion，也不代表官方 PIT 或模型有效性。

本次 UI owner focused route 為 `tests/test_ui_qt_personal_recommendation_choice.py` 28P；`recommendation_view.py` targeted mypy 0 issues、兩個 changed Python 檔 compile 通過。Workbench route 為 84P，Update QA 為 25P／4S；這些是各自 bounded 結果，不等於 native visible 驗收或最終整合 route。V2 UI source freeze／獨立 review與 root final relevant regression 收據尚待完成；真實候選、native post-fix操作及自然 scheduler仍未證。

R024 root 已完成 5-path diff review，9-suite regression 為 67P/0F/0S；`company_registry.py` 與 TPEX backfill 現各自擁有四欄 data diagnostic record/to_dict，移除 data→decision `FactorDiagnostic` imports。原 decision `FactorDiagnostic` classpath、FactorService 與序列化不變；新 data record不再通過 `isinstance(FactorDiagnostic)`，這是有意的 nominal identity移轉。Root 的 registry route 7P只驗route/metadata，不代表新增inventory 122 tests全跑完。R021原bounded scope不變；使用者另已接受IndustryMapper follow-up：data-owned company／industry-index providers由app composition明確建立注入，domain不再暗讀CSV／DB，已知in-repo callers已遷移。Boundary凍結13個changed paths；4個focused route paths共14 distinct inputs（含未修改的 `tests/test_decision_data_providers.py`），manifest SHA-256 `566c0fce31ce063b57c0f53a069e0d6a308b5cce19007fd56026e7d8ae48e602`；focused 18P/0F/0S、0.84秒。attempt6 288-path current route已包含兩個 mapper tests及其影響路徑並自然通過；此結果不外推為domain-wide no-I/O。

REC-02 的 negative-evidence consumer/projection bounded slice已接受（86P/0F/0S；recommendation-tab QA 7P/0F/0S；canonical query及journey callers亦有獨立readback證據）。completed business path由typed DecisionBatch產生current v1 projection；其v1 event僅作wire相容及一致性核對，failed/cancelled partial row/context僅為diagnostics。source search無production RecommendationService.run_recommendation() caller，也無service/body/execute外的app/UI/script last_* business consumer；R016 saved_recommendation_queries.select_latest_saved_recommendation是合法canonical readonly adapter，並非REC-02 Service list/latest-state surface。Root依R029原criteria裁定兩個in-repo業務consumer exit已達，REC-02 status為ACCEPTED_WITH_RETAINED_PERMANENT_COMPATIBILITY：保留公開run_recommendation/list/latest輸出、v1 projection、failed/cancelled diagnostics及rev1/2歷史decoder作必要具名compat；owner為app recommendation compatibility。這不代表所有last_* writer已刪、外部support已終止或存在第二canonical engine。Portfolio navigation-source identity P2另以六-suite54P/0F/1S exit0 bounded接受（1 skip為opt-in official scheduled Qt smoke）；只驗source navigation identity／22個projection欄位，不簽章整個Portfolio顯示內容。Manual §10.2已同步。

REC-05 兩個 DTO 的 owner/import cutover 已由 root bounded accept：19 個 repo 內非序列化用途 imports 已轉到 `app_module.recommendation.legacy_dtos`，舊 `app_module.dtos` public/pickle qualified paths 仍 re-export 同一 class object，module/qualname/signature/annotations/type hints 保持原值。Final freeze manifest SHA-256 `68ce801292fbc744bb4a79f3f18b5db13bafd59368f26f5b4c2606b6b9fab6f0` 覆蓋 21 source paths 與 DTO ABI regression；root 六-suite結果 69P/1S、exit 0，freeze scope pre/post hash一致。舊 synthetic p4/p5/joblib bytes fresh-process load 成功；load→redump 由 2049 bytes 變 2060 bytes，HEAD與candidate結果相同但都不與input byte-identical；新fixture p4/p5/joblib dump仍等於原fixture hashes。這完成的是 repo 內 import/owner migration；必要舊 class path列為永久相容，未宣稱可刪除 public facade，也未推論正式未知 artifact corpus。
ML2 constant-model與Restated research-contract owner／import-direction slice已由root接受bounded review：pure leaf移置與legacy same-object qualified-path aliases維持原class identity、metadata、annotations/type hints及受控p4/p5/joblib bytes；Restated原class AST、hash／market gates與結果語意保持。Pkgutil/pydoc明確載入面有負控；最新guard掃描591 files、0 violations。此guard是靜態直接／symbol-level檢查，不是攔截sys.modules所有間接反射載入的universal sandbox；未改allowlist、PRODUCTION_ROOTS或Direct15。H5 fresh -m及direct-import entry目前經v3→scripts/build→scripts/infer→app的transitive import chain自然註冊，沒有當前fresh-entry break。使用者已接受明示app initialization prerequisite；H5 bounded implementation與獨立review已接受：9 suites／105P／22.09秒，freeze manifest `4c6b89a8f3b0817118478e8b1455a9633684017f01f3711c8e8465d03f9706db`。正常app CLI保留bootstrap，裸ML entry未bootstrap在training/output前fail-closed；保留verifier、source-revision gate、exact output type與class/serialization identity。CLI驗證限`--help`初始化及target-free synthetic parity，不代表完整training/release或正式artifact load/predict。未知正式artifact只保留inventory狀態，不宣稱任意pickle可載入／預測。

TMP-NUM-01 已按原 bounded gate CLOSED。最新14-path NP1／NP2 routes各212P/1S、exit0，覆蓋Decimal half-up、同分排序、真 scheduled／historical rule-only personalization保存讀回，以及真 RecommendationDataFrameProvider.__call__ 將np.float64(91.5)／Decimal(70.0100)投影為exact built-in-float total_score、factor rows與呼叫順序。各profile對自己的native oracle；保留NP1初次parallel collection race與Windows wider-longdouble skip。這不增加自然ML品質、跨NumPy相等、所有平台或所有profile條件。

原strict gate最新 historical post-Qt full8 receipt `r027_post_qt_lifecycle_root_all_20260927.json`（SHA-256 `9a19c3ac9cc28d6c07ecda6506e1f4f35b30a7ffa4cf74cb915f531e414f5ef7`；summary `DF4533DBA4F72523E047DFBD458CED725114DFC35F17203F221E96100921992F`；scope `BED829EC6706671E98CE938C08DCA7674E5639E1A6BDE56D22512943332F0AB1`）仍為8/8 `INCONCLUSIVE`／0 semantic／947 strict differences、runner exit1；scope為1,233 paths，Direct15／pinned5一致。差異為738 event-clock、143 file-mtime/publication、64 SQLite reader lifecycle、2 SQLite transient SHA。這些是原strict歷史，保留raw evidence與9/23 frozen oracle（17,045,681 bytes；SHA-256 `4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616`）。

使用者接受的獨立 logical-time revision現已全8 PASS，source/runtime slice經boundary獨立review；root start decision授權R028實作；Root後續已正式接受scoped R028 production migration，raw receipt SHA `1a3b496973c7053c7d25612754a733cb505765667afa478be453efd2c5a19d82`，decision SHA `cc375897612e705e6c6c268a0ef63aa38c4f998d214a32fdd74d038567f792db`。詳見 [R028 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。Raw receipt `r027_logical_time_root_full8_20260927.json` SHA-256 `5e1f162cc569c49797d0f9fc9fc72b6d7f4fba41734afcec627a6d9684f372c0`，summary SHA-256 `e39f7d2e5ccb3e2a6b8d30be3d595ad2b06a6837ab9a56f9e3689bc221b58980`；8 cases、8 controls全PASS，3,303 source-scope files前後無差異，Direct15、pinned5、HEAD/status stable。新gate與原strict分開，原strict仍INCONCLUSIVE；details見 [R027 versioned acceptance addendum](../06_qa/R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)。此句記錄當時啟動裁決的限制；其後R028 scoped migration及attempt6 relevant regression／mandatory checks已分別由root接受，不改寫原strict verdict或外部驗收範圍。

`r027_post_custody_root_all_20260927.json`（bb68d020…ae0ae91；1,370-path scope、738 raw OS／146 publication mtime／63 SQLite lifecycle）是兩個Qt callback runtime修補前的歷史receipt；`ae0ddb3b…c83658`為含REC-05／ML2但未含TWSE暫存名修補的較早版，`1d457f7f…e161`為REC-05前版本。更早855／1,058 receipts與原848差異均保留為歷史，不覆寫或回填至最新9a19收據；各版的scope及分類不可混用。

另有獨立 DBManager resource slice：未修前真 TEMP API probe 的 25/25 `execute_query` return 後仍有 SQLite handle；`connect()` explicit-close control 離開 context 後為0。Root/boundary review 已接受最窄修正：保留 connect defaults、transaction與pandas read，`finally` close。新增真 connection success/error/rows/dtypes regression，連同相鄰 tests 92P/0F/0S；修後 7 次真 query return 均觀察到0 handles。`db_manager.py` source SHA `0031d1385920667515b8dd34745b807ed97bc21f9089bd1dde53e2ce3d1ab40e` → `dc3df6df6a9a68b79a00319245aa6d24b3b39de50a3ea6b76903103a8099b586`。這是已接受的獨立資源修正，不證明它是 R027 lifecycle 差異的唯一原因，也不能把 DBfix前 full8 重寫為 PASS。

R031 current result是attempt6：288 test paths自然exit 0，2,951P／5S／36W、817.03秒（JUnit 2,956 tests、0 failures／0 errors）；Root裁定`ACCEPTED_CURRENT_RELEVANT_REGRESSION_AND_MANDATORY_CHECKS`。Raw receipt SHA `9ec19361748ac2a0e0de120eee62043241d42375014af3bed60b6c2a02eefd4d`，root assessment SHA `b8d3f224d786f195ce5bbc8133ce95cae12a33320d627ccb27b80a1495e02b27`。Workbench 84P／0S；Update QA 25P／0F／4S；mypy 731 files／0 issues；changed-Python compile 109 files。3,313 source／fixture inputs無drift、scope新增／刪除為空、HEAD/status穩定、Direct15與pinned5 exact。5個pytest skips為4個Windows `WinError 1314` symlink權限與1個`longdouble` mantissa條件；Update QA另有daily／market／industry download及daily merge四項skip，均不計PASS。cleanup觀察60 roots／232 views不證明native page/profile teardown；Workbench沒有載入`ui_qt.main`。attempt1–5的失敗、中斷與成功收據按各自凍結scope保留，attempt6不覆寫歷史。

已接受的 test-owned cleanup 修補只改`tests/test_ui_qt_research_run_save.py`（SHA-256 `CE0A7F9FBF237E38321C4240B22B6C5EC64C9035C664390493B16F22C4E8F922`）：同一節點的 RED 測試本體1P但 conftest close-veto令程序exit1；修補後最小節點1P/exit0、整檔7P/exit0，後者釋放6 roots／36 views。這證明該案例可觸發並修正一條測試清理veto路徑；attempt4沒有root identity observer，不能斷言當時被拒絕的就是該視窗。B shutdown harness僅備妥並經唯讀審查，未執行；attempt5自然結束後不另跑Qt probe。attempt5通過也不證明過往hang的唯一根因。

第二輪263-path run的三個failure分別是Direct/OOC same-case `.expert-*`到`h5-rl` replace WinError 5、`test_program_readiness_projects_performance_owner_packet`回報`performance_owner_packet_invalid`，以及cache-hit custody runner回傳1。Readiness失敗已定位為QA runner basetemp與OS TEMP分離、違反既有TEMP guard；root決定只修runner並以TEMP子樹下basetemp重跑單節點通過。Cache修補對齊seed與runner的`PROFILE=prod`；owner 61-node route為61P/4.89秒，root單節點為1P/1.40秒，兩者均測於F0AC hash，最終6DF版本只翻譯註解，第三輪包含最終版本。Direct/OOC fold-008的WinError 5根因尚未證實；attempt6相關測試自然通過，但Direct15未修改，也不據此聲稱已定位該歷史失敗原因。第二輪receipt與attempt2原件保留於`output/qa/refactor_completion_20260927/final_candidate_eligible_root_receipt.json`及`final_attempt2_workspace_20260927/final_candidate_root_receipt.json`；第三輪另保留 `pytest_interruption_receipt.json`、`pytest_post_summary_native_stacks_2.txt`及integrity receipt於`output/qa/refactor_completion_20260927/final_attempt3_external_20260927/`。首次full-route嘗試因OS TEMP ancestor no-follow anchor檢查失敗而停止、沒有full verdict；早期254-path／2,610 tests collect-only exit0仍只是歷史collection evidence；category groups union只有127，不能替代top-level234 tests。更早兩次broad cross-page UI run由root精確停PID、exec回報exit -1，亦沒有完整suite verdict。

第三輪execution context有明確限制：attempt 3使用外部root exec的require_escalated；attempt 1／2是在workspace QA default sandbox，TEMP位置與execution context同時變動，故QtWebEngine／PySide shutdown stack不能單獨歸因於workspace watcher、antivirus、file lock或Qt根因。之後已修正並接受上述兩個UI頁面的callback lifetime路徑；有效的 bounded four-file observer run（receipt `output/qa/refactor_completion_20260927/qt_webengine_full_route_observer_20260927_02/receipt.json`、JUnit `output/qa/refactor_completion_20260927/qt_webengine_full_route_observer_20260927_02/pytest.xml`）自然結束：57P／0F／0E／0S、61.25秒、return code 0、未timeout或terminate，source_changed=[]。cleanup前後觀測為top-level Qt objects 552→0、QWebEngineView 72→0，72個view wrappers於cleanup後皆invalid。這只限四檔diagnostic；observer使用weak references且不查`QWebEngineProfile.defaultProfile()`，wrapper invalid／collected不能證明native page/profile資源已teardown，也不能定位先前shutdown failure根因。未變更Qt版本、強制退出方式或驗收門檻。

## 2026-09-26 Wave14 candidate revalidation（accepted with named boundary baseline）

Wave14 candidate 於獨立 managed worktree 完成 234-test／237-source full union；最終 short-path route 為 **2,446 passed／2 failed／5 skipped／35 warnings**，653.90 秒、exit 1，526 個 test/source/fixture/policy inputs 前後 hash 相同。Root 比對本輪 CLI captured stdout JSON 與 9/25 C4，584 files、11 occurrences／10 distinct、`shadow_only=true` 和兩個失敗 nodes 完全相同，裁定 `ENGINEERING_SCOPE_COMPLETE_WITH_RETAINED_BLOCKERS`／`ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。不是全綠，也不是整體 refactor unqualified PASS。

保留三輪 route 歷史：首輪 2,404P／44F／5S，起因 42 個 exact-fixture EOL mismatches 和兩個既有 boundary assertions；新增五條既有 `.gitattributes` `-text` 規則、還原五個 pinned fixtures 後，focused route 80P／1S。第二輪 2,431P／17F／5S；15 個 custody tempfile ENOENT 已由 cross 確認為 260 字元 Windows path boundary（parent 186、basename 73），short-path focused 31P／2F 中 15 個受影響 nodes 全通過，沒有改 production code。第三輪剩下的兩個 failures 就是既有 named shadow-boundary assertions。9/25 C4 保持獨立歷史收據；R027 維持 `INCONCLUSIVE`、R028 維持 `BLOCKED`。詳見 [R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 與 [Wave14 candidate manifest](../06_qa/WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json)。



## 2026-09-25 R026／R031 status（當日歷史快照；C4 named boundary baseline）

推薦校準服務在 `RecommendationCalibrationConsumer`、明列 NP1／NP2 runtime profile 與同次 invocation capability 均符合時，預設使用 `PreparedMLRuntimeInputV1`；未知 profile、自訂 consumer 或 capability 無法成立時，保留既有 `project_many()` 相容路徑。NoModel identity 只封存同次 fresh reload 實際回報 `rule_only` 且 `_model is None` 的結果。Rule 與 ML snapshot identity 分開保存；typed projector 不做資料庫、HTTP 或 filesystem I/O。`RecommendationPostCalibrationHandoffV1` 是執行中的 typed facts，不新增 execution serialized schema；receipt／availability／projection／event 由同次 handoff 投影，ML truth 不由通用 R011 capture 回讀。

NP1／NP2 capability 與 prepared-input focused route 各 68 passed；NP1／NP2 service-node 各 1 passed，NP2 default／fallback focused route 26 passed。Root 已接受 R026 exact consumer、明列 NP1／NP2 profile 與同次 capability 的 bounded runtime migration，`TMP-ML-01` 已關閉於此支援集合；custom／unverified profile 與 graph 保留相容路徑，不宣稱所有 profile 支援。C2 current union 為 1,860 passed／5 skipped／34 warnings（141 個測試，102.75 秒，exit 0），229 個 frozen inputs 前後 hash 未變；log `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\pytest.log`，SHA-256 `193EF45EA69B984A356F238CFAD4D00D714AB2B026E01CE89887260E59604687`。C2 裁定為 `ACCEPTED_WITH_NAMED_QA_BASELINE`：其 Update validator teardown `WinError 32` 保留為歷史 QA baseline，Owner 為 Update QA／DB resource lifecycle；後續 C4 Update validator 已另有成功收據，不改寫 C2 當時結果。C2 的 5 個 skip 為 4 個 Windows `WinError 1314` 與 1 個 runtime-specific `longdouble` skip。

C3 首次 union 為 2,443 passed／4 failed／5 skipped／35 warnings，471 個輸入前後 hash 未變；原始失敗收據仍保留。兩個 UI save fixtures 已遷移為 typed execution DTO，指定 UI／R020／presenter focused route 為 22 passed；log `C:\Users\archi\AppData\Local\Temp\c3uifix_0925_b\focused.log`，SHA-256 `97EE3347873ADEC2692D9BEAA3EC3D5692BEA1752E6E01FF6B1AE1E0BFC31494`。R026 shadow guard 兩個新增 exact imports 已修復；584-file scan 回到 11 occurrences／10 distinct diagnostics。相鄰 focused route 為 30 passed／2 failed，兩個失敗僅為既有 repository guard／CLI aggregate assertions；11 項 baseline 由具名 owners 保留，不宣稱全 guard 通過。詳見 [R026 shadow-boundary follow-up](../06_qa/ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)。

C4 full union 為 2,446 passed／2 failed／5 skipped／35 warnings（640.25 秒，exit 1）；root 裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。兩個失敗是既有 shadow-boundary CLI／repository aggregate assertions；584-file scan 的11 occurrences／10 distinct是歷史diagnostics並保留原receipt；current guard 589-file scan為0 violations，aggregate regression 2P已接受，不把舊baseline當目前違規。C4 route 的 471 個 inputs 前後 hash 未變，SHA-256 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`；與 C3 route 對照時只有 3 個 source/test inputs 不同：`ml_module/shadow_boundary_guard.py`、`tests/test_ml_shadow_dependency_boundary.py`、`tests/test_ui_qt_research_run_save.py`，其餘 468 個 inputs hash 相同。pytest log `C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\pytest.log`，SHA-256 `88797C7C2476576D771E88099E0016D49C10A78D29B0494B2A3CE834A8CF29F9`；route SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。C4 mandatory gates亦已驗證：Workbench 84 passed、Update validator 25 passed／0 failed／4 skipped、broad mypy 724 files／0 issues、67 個 changed Python files `py_compile` 通過，`git diff --check` 通過；source fingerprint 為 2,297 files、SHA-256 `A7F674B9551CC98090D6356E7879E1CE13452655C95EA311CDD2D3E859063AFF`。2026-09-25 root依當日C1–C4 evidence裁定當時定義的R031工程範圍以named blockers／owners收口；這是歷史裁定，不是目前R031/全域完成 verdict，也不是正式資料、scheduler、ML promotion或production acceptance。R027 維持 `INCONCLUSIVE`、`AB-ML-01=OPEN`、`TMP-ML-02=ACTIVE`，R028 維持 `BLOCKED`。詳見 [C4 mandatory gate receipt](../06_qa/C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)、[R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)、[R026 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md) 與 [R026 source revision evidence aggregate](../06_qa/R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md)。

## 2026-09-23 R025 strategy owner 搬移（ACCEPTED_SCOPE）

StrategySpec／StrategyMeta／StrategyExecutor／DailySignalFrame 的 canonical owner 已移至 decision_module/strategies；舊 app paths 為 9 個必要薄 public／qualified-name aliases，root 依 R029 接受 PERMANENT_COMPATIBILITY。Final 17-path source/test route 6P/0F/0S exit0，literal identity/wire 與 synthetic old-qualified-path regression 均通過；不宣稱自然舊 executor artifact 存在、未知 artifact 已載入或整個 facade 可刪。

## 2026-09-23 正式行情與相依資料修復完成

正式 SQLite 與大盤 CSV 已套用 3,106 個官方 TAIEX 交易日的 OHLC／成交股數，補入 19 日並保留備份後移除查詢表 2 個非交易日。九個原先完全缺漏的歷史週六已補入上市／上櫃共 14,869 列；三個休市日與 5/20 額外 54 個錯日 keys 共排除 2,942 列，before 值與原始檔保留。全歷史 5,331,231 列的 20 個技指、2,210 份 CSV 及 17 欄每日整合快取均已正式發布並完成獨立全量讀回；買賣價／量、本益比及漲跌價差六個衍生複本也已正式同步並完成獨立全量讀回；來源空值不補零或前值，20 指標、其他欄位、日價、大盤與 schema 保持。這代表本輪已確認的行情與相依快取修復完成，不代表所有基本面 PIT／產業歷史資料已補齊。日常重匯與完整重算防護已提交，保留既有五、六碼證券，缺值不補零／前值。

新來源候選的兩組完整重訓、獨立評估與各 13 檔研究推論已完成：H5 資料 3,498,147 列／全部 3,469,960 成熟列 fit；bounded 21,898 列／422,952 筆 OOF 預測（17,623 個不同測試列）。H5 三組 downside 與 bounded pooled 報酬／downside 均未勝基準，「未正式啟用」包含模型品質限制，不只是程式尚未正式使用。62 欄契約及 15 個凍結 ML 檔不變，rule_only／production pointers 不變。先前 v3 保留原身分，只作舊版本比較；完整結果見[修復來源候選驗收](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)，資料套用、回復與範圍見[正式資料修復](../06_qa/FORMAL_DATA_REPAIR_2026_09_23.md)。

## 2026-09-23 舊 v3 模型重建與研究驗證紀錄

兩個受影響模型家族的修訂研究資料、完整 fit、獨立評估及 13 檔最新資料推論均已完成。官方市場 v3 核驗 153 個月、306 份回應；全市場 3,496,189 列通過欄位／市場值／日期核對，H5 最終 fit 使用全部 3,433,790 個成熟候選列。市場組在相同股票風險 truth 上的誤差由 9,546 降到 353 bp，但基準為 322 bp；三組 downside Brier 仍不如基準。bounded 官方 v3 的 17,285 列、兩算法、四期間也完成 fit，327,816 筆 OOF 已核驗，但 pooled 報酬／downside 未勝基準。因此該研究版本的工程修復完成，**模型品質仍不足以正式啟用**；rule_only、舊模型隔離及 production pointers 保持。當時尚未寫回正式大盤，後續正式修復見本頁上方；配置 targets 與歷史產業 labels 的限制仍在，v3 不自動取得新正式資料版本的驗收。詳見[完整 v3 驗收](../06_qa/FULL_OFFICIAL_MARKET_V3_REPAIR_QA_2026_09_23.md)及[執行紀錄](../06_qa/MODEL_REPAIR_EXECUTION_2026_09_23.md)。

## 2026-09-22 個股研究內嵌工作區

主程式新增固定「個股研究」頁，市場／推薦／觀察清單／持倉的下鑽共用同一頁；切換工作區保留內容，返回來源定位目前研究股票，關閉主程式同時合作式取消報告與決策結果讀取。籌碼頁把法人、信用、集保與事件分區；持股級距改為語意表格，原始資料與可得時間保留在詳情。本次只調整呈現與導覽，不寫正式資料或改策略／交易行為。操作見 Manual 7.3。 本輪隔離整合 pytest 為 152 passed／1 skipped（含 UpdateView 84）；更新頁 validator 為 25 passed／4 skipped，全域 mypy 640 檔、changed Python py_compile 與 diff check 通過。另有跨程序讀回、busy close exit 0、研究旅程 runner 及正式 theme 的 1440／1000px offscreen 視覺檢查；未測 native 前景操作與螢幕閱讀器。


## 2026-09-22 歷史價格受控修復

使用者核准後，2026-05-20 的 868 筆 `daily_prices` 已完成正式修復；1256 close=183、1477 close=213，1538／2321／5906 的 OHLC 保留 NULL。Root 獨立唯讀逐列 readback 為 868／868 相符、同日非目標 fingerprint 不變；54 筆缺 canonical 的資料未修改。Online backup 與逐列 before／after receipt 保存在 DATA_ROOT 的 `output/scheduled/daily_price_repair_receipts/20260520/historical_price_spike_20260921/`。

模型／PIT 修訂保護已通過 55 focused tests；該階段全域 mypy 639 source files 通過。已知 derived h5 與 bounded operational 兩個 artifact hash 在反序列化前保守隔離，原模型與凍結產物保留，沒有重訓或 promotion；calibration pointer 仍為 rule_only。PIT exporter、歷史 snapshot 與 forward label window 自動檢查修訂 marker，pending 缺逐股明細時保守阻擋全部股票，避免晚到修訂冒充歷史已知資料。

相依技術指標已完成受控 apply：範圍為 868 檔、75,442 筆既有技術列，更新 1,277,135 個 DB 欄位；869 份個股／彙總 CSV 快取已同步，原本缺少的日期／欄位不新增。完整來源 prefix hash 與 before values 均已驗證；online backup、逐檔 journal 與 final receipt 保存於 DATA_ROOT 的 `output/scheduled/technical_indicator_repair_receipts/20260520/historical_price_spike_20260921/`。指標／快取修復 fixtures 13 passed，含程序中止恢復；原始 daily CSV 與模型 artifacts 保留。詳見[修復紀錄](../06_qa/HISTORICAL_PRICE_SPIKE_2026_09_21.md)及[模型影響與隔離](../06_qa/PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md)。

## 2026-09-21 歷史價格尖峰稽核

2026-05-20 的 1256／1477 已以完整官方 retrospective response 核對：canonical 分別為 1256 close 183、1477 close 213，formal SQLite／corrupt backup 為另一組錯誤值；5/20 TWSE 差異 868 筆（865 完整差異、1538／2321／5906 缺 OHLC，另 54 筆無 canonical 暫不動）。本輪未修 formal DB；來源核准、可回滾修復與下游重算影響仍分開待定。詳見 [歷史價格尖峰稽核](../06_qa/HISTORICAL_PRICE_SPIKE_2026_09_21.md)。

# 2026-09-21 個股研究資料鏈查核

正式資料只讀查核已完成：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 的 2026-09-21 `daily_prices` 查到 1,968 rows／1,968 codes，`technical_indicators` 查到 1,965 rows／1,965 codes；2382=344.5、3207=38.25、9935=18.2、1418=17.55 的查詢 rows 日期均為 2026-09-21，並完成日期／重複鍵／raw 對照檢查。1418 只是這次資料查詢的股票代號；Paper 裡同代號的 seed 不是使用者持倉。這只證明本輪查詢範圍內的存在性與一致性，不代表官方交易所全域真值或全來源同日 fresh。

2026-09-21 全市場跨日價格稽核進一步比較 2026-09-18→09-21 與 2026-08-25 起的相鄰交易日：9/21 1,968／1,968 rows／codes 的 O/H/L/C invalid 為 0，9/18→9/21 有 7 筆絕對跳幅 ≥10%、≥20% 為 0；這些跳幅與 11 筆成交金額／量隱含價超出 O/H/L 仍待官方公司行動或成交明細核證，不能宣稱所有價格合理。稽核也確認資料契約的具體 consumer bug：`漲跌價差` 是正絕對值而方向在來源欄，9/21 831 筆下跌都有可解析負號；報告 service 已修正方向合併，1256 為 172→170（-2）、1477 為 194→191.5（-2.5）。官方保存 response／日期／hash custody 的代表資料已對照；merged aggregate 最新僅到 2026-07-14，屬 stale，不能替 9/21 作 cross-source 驗證。完整範圍與限制見 [全市場跨日價格稽核](../06_qa/PRICE_JUMP_AUDIT_2026_09_21.md)。

目前高風險資料邊界：formal institutional／credit 最新到 2026-09-08、TDCC 最新到 2026-09-04；月營收／季報 PIT 仍有 expected period 與 announcement／available-time 缺口；broker coverage 依股票不同（2382 到 9/21、3207 到 8/20、9935 到 9/14、1418 代號無 formal broker row）。此為資料覆蓋清單，不表示使用者持有 1418。Paper 中 1418 的 blocked 分類為 machine-seeded research candidate／lineage 缺件，不是 price corruption，也不是使用者待補資料。候選 DB 的 rows 不得替 formal SQLite freshness 認證；`candidate_only=true` receipt 現由 read service 排除。

本輪未寫入 formal data、未重建／回填／重跑 scheduler、未更新 learning 或交易狀態。資料日、可得時間、PIT／current、source coverage 與 candidate-only 限制須在研究報告中分開判讀；缺件不可補 0。完整 evidence、SQL、focused QA 與 freeze 後整合 QA 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。

2026-09-21 候選池提醒呈現修正：首頁與每日決策已共用逐股原因、資料日／品質與查看步驟，缺前次分數不再只顯示籠統人工判讀；首頁一般觸發提醒導向候選池。候選表以可讀的「推薦來源」狀態替代原始識別字典，保留內部 exact identity。此為呈現修正，不改指標觸發、推薦評分、資料或交易權限；操作見 Manual 第 7.1 節。

2026-09-21 觀察清單導覽修正：移除寬版 responsive 殘留的未掛載候選池提示元件；一般進入、切換尺寸或返回只呈現頁內候選池，明確研究報告／頁面說明入口仍保留。此為 UI 呈現修正，不寫入正式資料。

## 2026-09-21 V5 日常操作與可讀性工程狀態

工作台、候選／研究／持倉、推薦／回測與導覽的 bounded presentation slice 已完成 frozen QA evidence：首頁優先顯示每日重點與下一步，日常／進階研究／系統維護分層，研究報告深頁按需繪製，缺 OHLC 可退回 close chart，錯誤保留白話恢復入口。A／B／D 的 final screenshots 已由 root 以正式 theme 審查；before／after 只在 30-row isolated fixture、2 samples、in-process boundary 下成立，不能外推 production dataset。

本輪 mandatory update pytest、QA validator、全域 mypy、changed Python py_compile、frozen manifest 與 isolated after perf 均已保存。精選整合 route 為 `299 passed, 1 warning`；`test_workbench_source_service_reads_real_read_only_sources` 已精準核對 seeded 2330 portfolio alert 的來源、原因、trace、drill-down、action 與 `write_intent=false`，並保留完整 background evidence feed。pytest cache warning 已獨立記錄，不影響測試結果。

最新 UI freeze evidence 以 `output/qa/incident_20260921/ui_readability/freeze_final_v2/summary.json` 為準（`passed`，offscreen）；all-pages focused route 為 122 passed／1 skipped，UpdateView 84，validator 25 passed／4 skipped，mypy 638 source files，changed Python py_compile passed。freeze 後 affected integration route 為 135 passed／1 skipped；全頁 loaded/error／極長真實資料未全部重演，native window／screen-reader 未測試。

版本名稱為「V5日常操作與可讀性工程」。這是工程可用性／導引進度，不是正式 V4／V5 gate、V6 user-level personalization maturity、自然 learning 效果或 production data readiness；原有 formal／natural／cross-page pending 保持不變。

本輪 UI 整合修正已納入工作樹：左側導覽群組與項目左對齊；個股報告換股會清除舊報告，同股 reload 失敗／取消會明示 last-good data 並保留 Journey 原因；來源摘要與完整 source trace 分層呈現；持倉頁分開日常正文、日期／原始 timestamp、Paper health 與模擬／歷史資料，進階正文可捲動並保留可讀 splitter 比例；工作台與說明按鈕把 machine token 轉為白話。這些是呈現與導引修正，不改資料、評分、交易或 writer；portfolio footer pane freeze 後的 mandatory integration QA 已通過。

> **2026-09-17 HEAD 校準**：目前文件基線為已提交 `0219d709`（C P1 bounded
> next-day inference／projection provenance），並承接 `9a9e778b` 的 Qt 關閉修復。已驗收的 bounded slices 包含
> `5a3ed5db`＋`ef594007` Position Health、`a4996cba` `user_declared`、`031e11ab` Continuity
> Review Workbench R1、`89a264f6` PIT reader/caller、`086ba60c`＋`0aaf0dff` BankTaiwan
> root guard／受控 retry，以及 `94d30b51` calendar／inventory audit。`0219d709` 已完成
> training／inference source 與 PIT hash 分離、共享 schema／transform compatibility、immutable
> hash-verified projection receipt、exact result／candidate／date／cost readback、normal UI
> default UUID → save → exact readback 與 identity conflict fail-closed；rule top-N selection
> authority 保留不變。相關 bounded QA 為 75 tests、mypy 9 source files、ML boundary guard
> 509 inspected／0 violations，詳見 [P1 provenance audit](../06_qa/DAILY_PROBABILITY_LEARNING_NEXT_INCREMENT_AUDIT_2026_09_15.md)。
> L 的官方 taxonomy source chain、完整跨頁整合、自然 evidence 與 V4 formal Gate 仍待完成；本工作樹另已
> 接上 C-owned V6 personal capture／read／ACK／明示 action／evaluation bounded slice，但尚未形成正式
> personal sample。下一順序仍是 **L source chain → 整合使用流程 → 以真實 user decision/outcome evidence
> 驗證個人化效果**，不把工程接線、fixture、replay 或 `natural sample=0` 縮寫成 V4／V5／V6 完成。

2026-09-18 core static follow-up 的 12 個 production files compile／mypy clean，float／
look-ahead quant guard clean；global ML shadow boundary re-inspected 518 files，仍保留 4 項
既有跨層 import residual，沒有以本輪 allowlist 掩蓋。這 4 項 residual 不改寫上述
personal／natural／formal readiness 邊界。

## 2026-09-21 晨間排程與資料接線修復

五項晨間／週排程 action 均仍指向 repository canonical CMD wrapper，且 2026-09-21 最終
`LastTaskResult=0`。Evidence dry-run 已修正隔離 Paper status schema／path、Frozen Rule producer
status、Position Health market-lane warning projection、CMD／PowerShell orchestrator parity、唯一 log 與
bounded Exit timeout；Windows task 連續兩次同日實跑皆 exit 0。Position Health proposal 改用
`position_health_transitions_v2.sqlite` 的 semantic identity，同一市場 rows 重跑保持 5 筆且
`persistence=idempotent`；舊 v1 DB 保留 immutable audit，不搬移未核准 proposal。

Phase3C institutional／credit candidate DB 已驗證 2026-09-21 兩市場 source coverage、無 natural-key
duplicate；freshness 改讀明確 candidate DB，不再以正式 DB 舊 candidate tables 誤判。月營收 2026-08
current observations 已受控 apply，但 formal monthly／statement PIT 仍缺 announcement／availability／
revision evidence，因此 freshness 合理維持 fundamental degraded。Evidence 最終為 `degraded` 而非
`failed`：工程 blockers 已清除，當時仍有 machine-initialized Paper research seed 1418 的 identity／Health
診斷，以及自然 outcome maturity；這不是使用者真實持倉，也不要求其補成交、entry 或 thesis。仍不授權
formal credit、production Evidence 寫入或自動交易。
05:30 read-only heartbeat prompt 已同步上述 candidate／formal／Position Health 判讀與 timestamp log
pointer；排程時間、target thread 與「不重跑、不修復、不寫檔」邊界未變。

## 2026-09-28 個人日常系統最終 relevant regression v2

EOF 空白清理後，root 對精確提交候選版本完成 302-path regression：3,218 passed／9 skipped／36 warnings（298 個 repo-short-TEMP 測試及 4 個 OS-TEMP 測試）；Workbench 84 passed、Update QA 25 passed／4 skipped、mypy 737 files、compile 332 paths 與 `git diff --check` 均通過。最終收據 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T064551_034316Z/run_receipt.json) SHA-256=`0ae3ec09a5f2a61c57bd28bc395bd2b3da4979146c7d00add348e396b791888b`；前一版收據仍保留為歷史。這是隔離 regression 證據，不解除 native post-fix、真實合格 PIT candidate、正式資料或自然 scheduler 尚未驗證的限制，也不表示 WP0–WP5 全面完成。

## 持續保留的接受邊界

以下是既有證據的限制，沒有因文檔整理而解除。詳細日期、source identity、hash 與測試結果見[整理前歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_27.md)及原始 QA；舊 receipt 不代表今天仍 fresh。

| 主題 | 保留的限制與接手入口 |
|---|---|
| Refactor | R027原strict維持`INCONCLUSIVE`；使用者接受的新logical-time revision與root接受的scoped R028 migration各有獨立gate。R031 attempt6的288-path relevant regression及mandatory checks已由root接受；此列為提交前snapshot，stage review與commit結果以Git history/root最後交付為準。`TMP-ML-02`原conditional migration已滿足；formal/native/scheduler/unknown-artifact與promotion驗收不在本輪範圍。 |
| Paper／Formal／自然證據 | 必須核對同決策日的 terminal／immutable receipt、calendar availability 和 source／state identity；隔離 fixtures、research capture、source_verified 不授予自然成熟、Formal credit 或成交證據。[跨日證據交接](../06_qa/V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md)。 |
| ML／推薦學習 | 新修復來源模型的工程建置與評估已完成，但品質未勝基準；rule_only 與 production pointers 不因建置成功改變。自然 probability calibration 仍需完整 prediction／policy binding 和成熟樣本，不拿 close-to-close 研究結果冒充可成交收益。 |
| 個人化與持倉 | source custody、候選與 user_declared 持倉不等於 personal delivery、adoption 或 filled entry；缺 lineage 不回填為可信持倉。當次 source／calendar／cost 仍須獨立驗證。 |
| 資料／PIT | 現況補齊不授予歷史可得時間信用；基本面 PIT、歷史產業 labels、未公告資料與既有來源缺漏仍按原始 QA 限制。不要補零、前值或用晚到修訂冒充歷史已知資料。 |
| Scheduler／交易 | 任務註冊、Ready 或 wrapper 工程驗證不等於每次執行成功；舊 host query 不當作 live 狀態。正式寫入、promotion 與 broker execution 按既有權限／Gate 另行接受，不由文檔更新授權。 |
| Direct／容量 | 舊 build／resume 收據只證明當輪範圍；承接未完成年度、OOC／fit／fold 工作前，先重驗 live headroom、200 GiB reserve 與原任務授權，不沿用舊容量數字。 |

## 閱讀與歷史

- [Roadmap Hub](DEVELOPMENT_ROADMAP.md)：產品方向、工程里程碑與版本成熟度各自的權威入口。
- [目前架構](../01_architecture/system_architecture.md)與[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)：設計目標與已落地範圍分開判讀。
- [完整操作手冊](../07_guides/APPLICATION_MANUAL.md)、[QA 主題入口](../06_qa/README.md)、[文檔索引](DOCUMENTATION_INDEX.md)。
- [2026-09-27 整理前快照全文](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_27.md)：保留 9/8–9/26 逐輪觀測與收據連結；舊「待完成」不自動成為目前待辦。
- [2026-09-08 舊快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md)：更早的整合歷史。

本頁維護最新範圍與未解除限制；新的驗收細節保存於專項 QA，不把逐輪流水帳重新貼回本頁。目前狀態見頁首 2026-10-04 區段；9/30 排程 matrix 與下方歷史段落只代表標明的當時觀測。個別自然／受控 receipt 不代表 21 項排程全數通過。


2026-10-03後續驗證：見 `docs/06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md`。current fundamentals 為weekly成功後的獨立writer；current revision與正式PIT分離，decision date使用Asia/Taipei、market cutoff保留獨立日期；Evidence依child stdout/summary/report與來源品質驗收。個股研究提供明確保存來源／指定股票分析及獨立技術觀察，仍守正式ML來源修訂隔離。


Health最後串接已控制實跑：臺北10/4決策對10/2行情，離線官方日曆驗證休市範圍；5個條件、67個Decimal指標及轉換proposal無blocker，Evidence errors0／report存在／degraded。控制衍生輸出隔離於QA，canonical35筆既有proposal保留；原自然Task結果與品質缺件不改寫。詳見上述Final closeout報告。


## 2026-10-05 UX03／06／13 收藏原研究限定閉環

每日研究列可明確收藏至既有觀察清單，保存原快照／方法／日期／query身份；同內容冪等、不同來源同股共存。重開程式、同查詢切股及返回均精確讀原書籤，無效來源拒絕比較；latest另開是明確唯讀操作。JSON／SQLite沿用既有payload，顯式升級具備嚴格semantic去重，不自動遷移使用者清單，也沒有第二份持倉ledger。

相關114項有限測試、Workbench85、validator25／4 skip、mypy778、compile／quant guard與真D已發布兩股來源＋隔離觀察清單Native閉環通過。完整stage1–3／UX、Backtest18.62%／20%未達、PIT／自然ML／正式資格與真人驗收限制未解除。詳見[收藏收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)，真正HEAD以Git與本包commit_readback為準。


## 2026-10-05 UX04／05 固定方法預設與候選摘要

每日研究條件新增五個固定 MA20／60 查詢預設，選取後須明確套用；只篩選已核驗快照。手動條件／原來源回訪不自動覆蓋，切換預設或Decimal指標排序不改來源／日期／方法／研究資格。完整 declared 分母、已發布／缺件、組合三態、顯示／因篩選隱藏與具名原因可見；缺少 artifact 不造可開列，未知不當反證。原強弱排名未提供，選項停用；不造分數或勝率。選取摘要立即刷新，原方法identity保留詳情。

本包 final 43 affected passed、Workbench85、validator25／4skip／0fail、mypy779、compile／quant guard通過；已發布真D2382／1477 readonly offscreen及preset→收藏payload roundtrip→同源開啟／返回身份核對通過。未啟動正式／全量producer，沒有真實清單寫入／遷移、正式DBwrite、訓練、前景Native或鍵鼠；本包新增Native互動仍待下一使用者桌面時段。完整stage1–3未宣告完成，Backtest18.62%／20%未達及PIT／availability／自然ML／真人證據限制保留。詳見既有[UX16 QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)與[Manual](../07_guides/APPLICATION_MANUAL.md)。


### UX16／18 有界母體來源契約延伸（2026-10-05，基線7e11f5a8）

明示母體設定是隔離研究批次來源：ID／版本／截至日／原檔hash、納入／排除與理由、已知或未知設定分母。可選manifest extension納入原不可變identity，讀取與consumer重新核對來源revision／刪除／成員／date；舊無設定cohort保留來源與原始分母未知。清單、母體盤勢及候選摘要共享同一契約，設定不授予PIT或推薦資格，不計算新分數。CLI明示讀included，禁止無設定手動更新默默降格已綁來源。

原排名來源audit：原計畫指StockScreener本日／本週價量強弱排序（原公式不改）。ScreeningResultDTO有period／method／version／eligible count，但即時結果未有不可變run／完整成員排除／hash發布；strong_stocks_view僅記憶體快取。saved recommendation屬另一rank kind不能代用。有限currentDB schema唯讀未找到rank／screen tables，不推論全球不存在。原排名未知且停用；需原引擎不可變結果發布工程，不稱等待自然成熟。

本包無Native前景或使用者視窗操作，無訓練、全市場producer、正式DB／registry或真實書籤寫入；永久清理仍未執行。驗證與commit結果見同章最終收據補記。

最終驗證：104相關tests、WB85、validator25/4skip/0fail、mypy781、compile13及guard通過；真D三股隔離發布／2382讀回／offscreen同源通過。詳見UX16 QA最新最終驗證章；原排名publisher與Native仍pending，未push。


## 2026-10-05 UX18 原排名發布延伸

既有 StockScreener day／week × strong／weak 原生結果新增獨立 immutable ranking publisher／verified reader；Daily 名單、候選與研究母體 Market 共用同一 parent snapshot及排名身份。僅明示≤16股研究母體，不改原公式、feature v2或舊收藏。原 Top／Bottom 標籤不能按一般百分位／勝率解讀，數值 score 未由舊引擎暴露；未知／不相容來源維持不可用。原排名收藏／個股來源版本化、其他consumer、完整方法／母體／正式排程及長期storage仍須工程。詳見[限定QA](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)，新 Native／真人與全App啟動未由本包驗收。

- 2026-10-05 更新：新增原排名有限工程入口及接受邊界。


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](../06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


### 2026-10-05 每日鏈容量與接線修正（受控工程驗證）

使用者授權把中央 ML 執行後餘量由 200 GiB 改為 20 GiB；本輪工作預算與未知用量 fail-closed 不變，正式 raw 預設總需求為 95 GiB。Decision Evidence 採父子 lease；G6 空 WAL／mtime 與真正內容改變分列；Paper 已驗證不可重試政策拒絕作 rejected 終態，歷史失敗保留。G9／Bank 同次來源 Gate 不放寬。驗證與回滾見 `docs/06_qa/HEARTBEAT_CHAIN_REPAIR_20261005.md`；沒有宣稱新自然排程成功、正式 PIT 或 formal credit。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


### UX09 最終限定收據（2026-10-05）

78 個不重複受影響案例、Workbench 85、validator 25／4 略過、mypy 786、8 檔編譯通過。真實單日三檔維持未知（翌日發布且無有效前次比較），17 檔來源雜湊及正式 DB/WAL/SHM 狀態不變；未授予 PIT／自然成熟。完整第一版與 Backtest 18.62%／20% gate 未變，長期歷史索引／分頁、部署／其他 consumer 與 Native 驗收仍待完成；容量工作屬其他 owner。詳細證據與回滾見 UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


## 2026-10-05 F2／F3 原市場頁共享來源與已開能力矩陣（最新）

F2／F3 在已接受的 A／A 研究限定範圍完成：原大盤指數併列具名摘要，強勢個股、弱勢個股可明示切換至每日研究名單同一 immutable 來源；日／周 × 強／弱四模式保留原完整 eligible、Top／Bottom 標籤、實際比較窗及兩種排除。榜外與研究資料缺件分欄，來源變更／清除／過期回應拒絕，切返嚴格唯讀不啟 producer。既有全市場／產業來源、母體與可比較性仍獨立，沒有用三股取代全市場統計。

能力矩陣只登記 close／MA20／MA60、close_above_ma20／close_above_ma60，完整 field／unit／warmup／missing／availability／version／cost／source 與逐股 audit 可查；官方時點及未量測成本維持 unknown。完整只相對 named declared cohort；既有 feature v2／method hash／原引擎與收藏版本不變，沒有新增正式 B 母體或方法版本。

本批驗證：43 個不重複受影響案例有通過證據（根層首9＋相容29＋實際橋接新增1＋F2 focused4；最後11頁面相容重驗為既有案例不加總）、Workbench85、validator25／4skip／0fail、mypy790、12檔編譯及精度／未來函數 guard 通過。受控小型來源驗實際背景 consumer；真實既有三股保存來源驗能力投影與 offscreen 畫面，17 來源 hash 與正式 DB size／mtime 不變、worker 0；後者沒有開正式 DB 重核 current identity，不能宣稱自然跨日證據或 PIT。詳細來源、失敗保留及回滾見本批 QA 收據。

第一版工程剩 F1（18.62%／20%，差 1.38pp；不重測微調）及 F4（整條跨頁整合、部署、長期總容量）。新 Native／3–5 位真人另驗；舊1477 Native已在6691ec78完成，不重列待辦。1000×835 outer／125%沿已接受，不加1000×800硬門檻。工程缺陷不稱等自然成熟；source/capacity／Evidence 屬另一 owner，保留其變更並排除本批提交。沒有清理、正式資料寫入、訓練、前景視窗操作或 push。

[本批詳細收據](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)


## 2026-10-05 F4跨頁整合與資源終驗（最新）

MainWindow明示snapshot root/cohort、original-rank root接線完成；actual9工作區三個不同子程序跑通research v1源頁收藏／original-rank v2報告收藏、精確返回、新程序同source/report identity讀回及no-arg配置回滾。8個發布檔案hash在跨頁／cancel／fresh process／close後不變，schema/cancel/stale last-good與有限cache核對通過；不是Native或自然資格。25個不重複受影響案例有通過證據，Workbench85、validator25/4skip/0fail、mypy790、兩檔compile與Main量化guard通過。

20個同日受控session共用tiny3股×120列DB，實體留存1,714,653 B、index staging32,768 B另計、index WAL0、單份backup32,768 B；當下policy SHA6e7b018f...111e880／20GiB reserve的隔離preflight通過。Formal inventory unknown，不授writer，retention僅dry-run。

**120／250 sessions仍blocked**：Watchlist revision保存整份清單，payload呈二次累積，下界37,251,702／159,588,787 B，均超4MiB payload及32MiB DB上限；精確未來physical未知。原9.9／20.5MB線性預估已撤回，以resource v4為準。不能宣告F4全閉／首版完成，也不能把已知儲存預算限制寫成等自然成熟；後續容量／Watchlist owner需提出可審核方案，本包不擅改policy／migration／清理。

F2／F3 A／A不重開；F1保持18.62%／20%、差1.38pp，由父層處理例外／後續方向，不重測微調。正式WindowsTask未查改，manual/on-demand沿用；其他owner三檔與Paper未納提交，未寫正式資料、未操作使用者視窗、未刪資料、未push。新Native／真人／自然資格另列，舊1477 Native不重跑，1000×835 outer／125%維持、不新增1000×800門檻。

[本批逐項收據／明確阻塞／回滾](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)


## 2026-10-05 F4 項目 revision 儲存與長留存實測（最新）

新／空庫採 schema3 `watchlist-item-events.v1`，不可變item＋稀疏events取代每版完整清單；舊v1/v2與兩種bookmark可讀，禁止初始化隱升級。4MiB payload／32MiB DB／64MiB scan／4096rows不變，容量未知／不足及schema/hash/refs/sourcehash不一致拒絕；歷史完整payload hash由有界增量replay另驗。

受控同日期3股×120列，實際發布／收藏250次，20／120／250總實體留存781,365／3,887,695／7,912,388 B；250時Watchlist DB4,145,152 B、聚合payload2,600,012 B、全治理掃描6,202,133 B。三節點capacity／scan／references及全部250歷史回放通過，actual v3 offscreen MainWindow三程序讀回通過。39項統一路由＋最後新增sourcehash拒絕1案共40 distinct有通過證據；mypy791、最後單點module mypy、6檔compile與精度／未來函數guard通過。

新隔離v3長留存限制已修，舊格式歷史估算不回寫；**正式v1/v2 COW converter／activation切換尚未實作及核准**。本批僅readonly dry-run，原DBbytes不變；不得把正式部署未做寫成等自然成熟，F4不能全關閉。F1差1.38pp交父層、F2/F3 A/A不重開，新Native／真人／自然資格另列；不清理、不push、不改其他owner。

[完整收據與 COW 剩餘工程](../06_qa/F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)


## 2026-10-05 F4 SQLite COW converter 與明示 activation（最新）

SQLite v1/v2→獨立v3 COW converter、CLI dry-run/convert/activation-preview/activate/status/rollback、fresh-service pointer與錯marker拒寫、bounded governance audit接線已實作並完成隔離驗證；取代前批「converter尚待工程」狀態。lexical codec保留逐版raw payload/hash、IDs/metadata/timestamps/source/order，v1缺歷史只標synthetic baseline。原4MiB/32MiB/64MiB/4096上限不變，取消、容量未知/不足、bad rows/schema、concurrent writer及身份錯誤failclosed。

限定路由 70 passed，mypy 793 source files + CLI 1 source file pass，11檔compile及精度/未來函數guard通過。已許可舊20-session fixture副本由CLI新程序完成轉換、啟用讀回、target r21追加、rollback回source r20；target r21、雙DB/audit保留，不自動合併。原fixture及17份已接受immutable pins保持相同；無producer重跑、正式資料套用、Native、清理或push。

本批COW實作工程關閉；正式使用者apply另行核准。預設canonical SQLite不存在、legacy default.json存在，實際store/mode/override仍待父層確認；沒有初始化缺失DB或讀真實JSON。F1差1.38pp交父層方向，F2/F3 A/A不重開；新Native/真人/自然資格分列，不能把部署批准寫成等自然成熟。

[逐項COW驗證、操作與正式部署邊界](../06_qa/F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)


### 最終容量守衛收尾（2026-10-05）

啟用與回退發布 audit／marker 前重新核對當下中央 reserve；容量未知／不足具名拒絕並保留原指標、雙庫與內容。最終限定路由72 passed（focused_root_05.log；另有pytest cache唯讀警告），mypy793及CLI1通過，11檔compile／7產品檔精度與未來函數AST守衛0違規。14個獨立程序實際CLI回放全部exit0、隔離guard0違規，17份immutable來源及原20-session fixture SHA不變。最終case為output/qa/f4_cow_converter_activation_20261005/cli-roundtrip/run-615b305783f9；原失敗與中間收據保留，不替換為自然或正式驗收。


## 2026-10-05 Legacy JSON v1 COW 與明示切換（最新）

實際一般啟動沿 legacy JSON v1；本批補齊單一 JSON→獨立 SQLite v3 converter、原升級按鈕的 convert／核對／activate、新程序 discovery、source-aware writer 與 rollback，不建立缺失 canonical。多份 JSON、已有 canonical 歧義、錯來源／marker、容量／版本／型態／編碼與並發 writer 具名拒絕。來源 raw bytes 與合法未知巢狀欄位保留，opaque history 不臆造 ledger；JSON 無版本鏈只建明示 synthetic baseline。回退回 JSON，保留 target 新 revision、雙來源和 audit，不自動合併。既有 SQLite COW 路徑沿原契約。

限定統一路由 113 passed，Workbench85、validator25／4skip、mypy 794及CLI1、12檔compile與6產品檔精度／未來函數AST守衛0違規。14個隔離新程序完成 JSON CLI轉換／啟用／追加／回退，來源 bytes unchanged、target r2保留、canonical未建立；合成 JSON 起點20／120／250次保存之總留存 181,902／444,060／816,793 B，未冒稱自然來源／全書籤負載增長。17份已接受immutable來源SHA及正式JSONsize／mtime保持，正式資料未套用。

正式來源 `D:/Min/Python/Project/FA_Data/output/watchlist/default.json` 為1948B；候選 `watchlists.v3-cow.sqlite`、marker `default.json.cow-active.json` 與 canonical `watchlists.db` 仍不存在。本批不讀原 JSON 內容／不初始化缺失 DB。真正apply另由父層／使用者確認單來源、writer時段、當下容量與明示批准，再按Manual dry-run→convert→preview→activate→新程序讀回；rollback保留雙來源／新內容。PID39400／41588無原PID/starttime owner收據，保留未停止，不能當writer已停止的證據。

F1 exact18.621965821542936%／20%差15.1294400013285ms（約15.13ms）例外尚未批准；F2／F3 A/A不重開。UX07未啟動，新Native／真人／自然資格另列。原整份計畫階段done1／partial5／pending3、UX done2／partial14／pending8保持，有限工程完成不等於整份產品計畫完成。沒有清理、producer／ML重跑、Native或push；其他對話檔案保留排除。

[JSON路徑逐項驗證與正式批准邊界](../06_qa/F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)

## 2026-10-05 UX07 圖表方案調查（最新）

UX07 官方資料與 repo 可行性調查已交付，修正上段「未啟動」狀態；選型、離線原型與 UX08 整合尚未完成，原整份計畫完成數不因研究交付自動增加。首版建議保留原生個股圖與同源表，stage4 主圖候選為 Lightweight Charts＋本機資料；外部連結可選，Hosted Widgets 的逐台股商品／元件覆蓋與桌面散布條件仍待確認。現有 fast chart 是回測用 inline Canvas，並非個股 OHLC 契約；本地沒有 LWC bundle，本批沒有安裝／下載或原型效能量測。下一批先固定 DTO、來源及 cutoff 契約，再由父層決定鎖版資產與隔離 renderer 原型。

正式 JSON 未套用、F1 例外未批准；無 Native、producer／ML、清理或 push。[UX07 比較、來源入口、待驗項目與遷移路徑](../06_qa/UX07_CHART_FEASIBILITY_20261005.md)。


## 2026-10-06 個人觀察清單 opt-in 整合

獨立 personal lane 兩個 immutable commit 已順序納入 dev：25c3b326→c03bb4a7、5efb3f13→a205275d。App config／selector／CLI／候選池路徑確認接線，未設定沿原模式；個人模式來源只讀，明示啟用才建立個人 DB，private controls／JSON bytes backup／rollback audit 不留市場包。個人 rollback 僅停止 writer並保留 target 新歷史，不恢復來源 writer。其他個人領域未接線；正式 root、真實遷移與 Native 未執行。F1 18.621965821542936% 保留使用者已接受的效能例外，20% 目標未達，不改稱 pass。[操作](../07_guides/APPLICATION_MANUAL.md)／[QA](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)


## UX10 MA 方法重合摘要限定接線（2026-10-06）

獨立lane `340eac2f5729fade53190967d11d2d637a4c85bf` 已納入dev，沿同accepted快照接每日名單與候選摘要，股票／方法／family去重、完整分母三態與各自理由。MA20／60同family，2方法1family；沒有排名入選predicate或新family，跨familyunknown。來源不可比／partial明示，current-observed research不賦PIT或Formal。UX10維持partial：第二合格家族由父層另行提供，Native／真人另驗。[QA](../06_qa/UX10_MULTI_METHOD_LANE_20261006.md)


## 2026-10-06 個人 Journal composition 整合

Journal lane 的 guarded JSONL adapter 已接獨立 notes root／mode；MainWindow writer／controller、Workbench continuity、推薦 Personalization／ACK 與 outcome journey 共用選擇。personal 不混讀舊來源；legacy_read_only 無來源 lock／mkdir且拒寫。已設定模式漏 selector 會 fail-closed；未設定保留舊相容 writer，不宣稱全域禁寫。正式 personal location、真 notes migration／備份 producer／Native 尚待批准；Portfolio／Ledger／Paper 與 Evidence DB 路由未搬移。[QA](../06_qa/PERSONAL_JOURNAL_LANE_20261006.md)

驗證邊界：App16（含2種實際MainWindow offscreen新程序）、COW指定案例及獨立busy-close driver通過；affected去重251pass／1fail／1skip。完整Workbench跨頁readback案例仍在8s前置時report worker running／loading／無error，根因待診斷，不能關閉工程gate或歸因自然成熟。Workbench85、validator25／4skip、mypy799及compile／quant通過。


## 2026-10-06 最新個人儲存位置決策

使用者已選擇 `D:/Min/Python/Project/FA_Data/personal` 獨立子目錄，取代先前 LOCALAPPDATA／FA_Data 外 root 提案。專用 SQLite 不與市場 `twstock.db` 共用。這次只批准位置，真實 migration／activation 仍未批准；尚未搬移／建立正式 personal store。精確 `data_root/personal` 契約已整合；其他市場子樹、ancestor、output 與 links/hardlinks 仍拒絕。必須明示設定 root／source 或獨立 notes root／mode，未設定不會自動啟用。市場分享只能按 explicit allowlist 排除 personal、舊 watchlist JSON 與其他私人來源，不能宣稱整包 FA_Data 可直接分享。


## 2026-10-06 最新功能收尾

Journal跨頁功能gate在單一15000ms有界等待下完整通過（含新process readback與busy-close）；原current8.109／baseline8.141秒未達8秒保留性能觀察，使用者已接受微小差距，不再阻塞。source/date/hash/no-follow/hardlink/personal守衛未改。

UX11 readmodel c7a9ea37整合為a3b63070；回測策略設定新增按需版本化規則說明，使用與既有回測相同StrategySpec設定，尚未連結執行結果。缺entry/exit/cost/benchmark等維持未知／not_evaluable，不新增executor或績效資格。UX11由待辦改partial，stage6仍partial，Native及真資料migration未完成。


2026-10-06：UX11新增Research Registry單筆保存結果→規則卡readback，來源Spec／pin、version／params／window／cost／data身份核對，缺件not_evaluable、不補章／默認。有限source consumer子項已完成，UX11仍partial而無新增人工blocking gate；未接自然forward／完整execution資格。39focused＋6shell、Workbench85、validator25/4skip、mypy802通過，未讀正式DB或改UX20 lane。

### 2026-10-06 UX20 單批 MA 樣本限定整合

既有隔離 MA CLI 明示保存完整 matched/notmatched/unknown/excluded 單批capture＋receipt，再按原pin唯讀核對readiness；既有MA頁只呈現當期完整控制組投影並明示尚未保存。included≤16、超限拒絕；未知availability/calendar/outcomes不補PIT或訓練資格。Stage5／UX20 partial，多批parent／排程與Outcome接線仍是工程待辦。QA：`docs/06_qa/UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md`；操作以Manual同日章節為準。個人儲存／Journal程式已整合，只有正式migration／activation未做。


### 2026-10-06 UX20 多批母體有限整合

具名parent manifest已沿既有query-only source／producer／capture／readiness完成多批保存、新程序讀回、取消／失敗／安全重試；每批included≤16，完整母體最多16批，缺批與途中來源／方法改變不能complete。producer發布狀態與sample捕捉狀態分開，uncaptured另列。UI未改；Stage5／UX20仍partial，固定時鐘／排程留存、Outcome H5/10/20與母體UI瀏覽仍待工程；官方available-at／日曆及自然成熟另待證據。操作依APPLICATION_MANUAL最新多批章；收據：docs/06_qa/UX20_PARENT_CAPTURE_INTEGRATION_20261006.md。


### 2026-10-06 UX20 保存母體收據瀏覽

每日研究條件新增明示選取parent receipt的背景唯讀視窗，沿原writer/readiness核對；首屏列母體／資料日／方法、完整／uncaptured與每批producer/capture結果，技術身份折疊。重複點擊／取消／返回／stale回應不重跑producer或套舊資料；readiness拒絕時保留已驗envelope的發布記錄，母體資格未確認。15 offscreen測試、Workbench85、validator25/4skip、mypy806+final targeted2通過。Stage5／UX20保持partial；固定觀測日policy、漏日／修訂接受與owner容量部署仍待工程，UX21獨立lane未接受。QA：docs/06_qa/UX20_PARENT_RECEIPT_UI_20261006.md；操作依Manual最新章。


### 2026-10-06 UX20 固定觀測日接受限定完成

既有parent receipt→原readiness→child exact資料日→固定cutoff/窗口/expected dates接受policy→共用atomic writer→新程序唯讀日報已接線；隔離CLI預設preview，--accept明示保存。缺目標資料日不能借latest或前日補完整，同日不同revision保舊、相同policy/parent冪等、failure/partial安全重試。23不同案例、targeted mypy2/compile3/quant/diffcheck通過；UI未改不重跑前批gates。Stage5／UX20仍partial；正式daily owner/Task/cadence監控／容量留存部署與官方來源治理仍待工程/決策，UX21三檔獨占未接受。操作依Manual最新章與Supplements，QA：docs/06_qa/UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md。


### 2026-10-06 UX20 隔離daily owner可執行整合

新增明示runtime/target日期的isolated daily runner，直接沿既有producer/parent/observation接受串全鏈，preflight為預設；capacity/quota先檢，有限retry/合作cancel/漏日與revision監控，exact receipt重用。source/日期/配置一致才完成，producer已發布與capture拒絕分列保留；未配置不選生產值。17不同案例＋最後source/config兩例重核、targeted mypy2/compile3/quant通過；UI未改。Stage5/UX20仍partial，正式date-owner/calendar/Task/ACL/留存治理待工程/決策；UX21三檔未整合。QA：docs/06_qa/UX20_DAILY_OWNER_ISOLATED_20261006.md；操作依Manual。


### 2026-10-06 UX22 同源公平比較工程

新增sealed receipt→既有CORE20 feature／整數shadow prediction DTO→共同樣本計分→白話CLI／JSON重讀。明示method/horizon/label/split/cost/benchmark/target contract，流失及不可比較分母不消失；未配置或無candidate不造結果。唯讀匯出、隔離fixture驗工程，不fit或提升PIT／training／formal／natural／execution資格。UX22／Stage7仍partial；9stage=1done/8partial/0pending、24UX=2done/21partial/1pending，真來源／合格模型及效果證據待補。操作依Manual；QA：`docs/06_qa/UX22_FAIR_COMPARISON_20261006.md`。


## 2026-10-06 UX08 推薦保存圖表（後續最新）

沿1454a125：同次prepared行情frame封存價格／既有MA20／60到immutable execution，保存後exact讀取供既有原生圖與精確表；來源result/provider/version/cutoff/完整股票分母核驗、legacy／缺件不借live，scheduled決策日與行情截止日分離。182相關案例、Workbench85、validator25／4skip、mypy819、compile／quant／offscreen核對。UX08推薦writer有限工程終點完成，整項／stage4仍partial；9stage1done8partial0pending、24UX2done22partial0pending不變。viewport e52b27dd及CSV f0e1d8e→8d0a6090仍lane-only，產品控制尚未採納，待下一包；無Native／正式Task／真資料寫入／分享。Manual及[QA](../06_qa/UX08_RECOMMENDATION_SAVED_CHART_20261006.md)同步。


## 2026-10-06 UX08 原生viewport可操作接線（後續最新）

e52b27dd以cd33ddd6採納controller，產品價格頁加入縮放／平移／重設與可見範圍、全量精確表。缺價格槽hover/paint日期一致，價格與MA缺值斷線；完整同身份重讀保範圍，未知或版本/source/cutoff/context變更重設，取消/stale/保存重開驗證。115相關案例、Workbench85、validator25／4skip、mypy820／compile／quant／offscreen；V5另有2個基線既有斷言失敗留證據。UX08／stage4仍partial，9stage1done8partial0pending、24UX2done22partial0pending不變，無Native／真人／正式Task／DB／push。CSV收據rename阻礙另包修，UX23 readonly未整合。[QA](../06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)。


## 2026-10-06 明示市場CSV consumer／CLI採納（後續最新）

f0e1d8e→8d0a6090精確review後以ac0cc19b→ffa6e537採納，consumer與獨立preview/accepted-preview/execute CLI；修正長UTF16路徑receipt錯名及API成功不足以completed，exact canonical/identity/hash發布後再驗。192去重synthetic通過、深CSV/CLI88重複驗、targeted3／fullmypy821／compile4／quant通過；3個初次deep COW普通open長路徑失敗另記，短fixture全套過。無UI／真匯出／分享／migration／Task／Native／push，FA_Data/personal沒有啟用。整體仍9stage1done8partial0pending、24UX2done22partial0pending，UX08／資料分離partial不增done。Manual同步，[QA](../06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。


### 2026-10-06 UX23 registry readonly 整合補記

UX23 readonly metadata adapter 已整合至 shadow acceptance CLI；export declaration／registry snapshot read 分開。WAL／sidecar 拒絕，不改真 DB，所有資格仍 false；UX23 partial。


### 2026-10-06 B01-H6/H7 有限裁決與下一波ownership

worker56ae8d82採入中央4cea589d：僅guard exact caller兩label symbols、CLI tests與QA三檔。63pass immutable source/raw/JUnit收據核對，中央affected CLI與guard另落raw；namespace/writer/trainer/其他caller仍拒絕，unknown／qualifications原樣。H1–H5/H8剩六工程違例，global仍FAIL；不提升Stage/UX/正式來源資格。Paper实际writer最低五production，拆P1兩ledger／P2builder＋雙CLI，I20四治理檔只分類指定20，見[精確派工](../06_qa/BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md)。source_id三檔仍待直接批准，不繞過；本次沒有formal DB／Task／Native／fit。


### 2026-10-06 I20/P1採入，剩清冊一次有限收尾

I20中央95d381a4：20exact entries，原20test/舊分類/direct12不變；metadata1281/1125/missing156/docstale0、exit1。P1中央e1857a31：ledger route/path/account guards與readonly ctor，原金融AST/SQL不變，172lane raw/44central affected通過；builder＋雙CLI P2依此API執行，尚不代表正式writer啟用。P1新test另1，當前預期1282/1125/missing157。原156全scope＋此具名增量可一次由唯一I156owner改四治理檔，其他四群只讀逐檔證據，不bulk猜、不改tests/support/runner，不重union；[完整派工及frozen paths](../06_qa/BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md)。source_id三檔仍未准；Formal/Task/Native/fit與Stage/UX资格保留。

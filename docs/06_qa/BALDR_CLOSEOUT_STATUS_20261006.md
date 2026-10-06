# BALDR 有界收尾狀態與移交（2026-10-06）

## 2026-10-06 I156 中央最終驗收

固定治理提交 `dd33d4efd23e5915fbc2c1d51fdd4b9f7ab396be`：原凍結156項＋已採P1具名1項一次入冊，共157項增量；filesystem／inventory＝1282／1282，missing＝0、stale＝0、documentation_count_drift＝0，metadata audit exit0／passed。執行時明示 skip-pytest-collection，沒有執行156項測試、fit或模型載入。原13項治理契約13 passed／10.07s；registry targeted mypy、compile及diff-check通過。原1125項分類值、support／runner API、direct bridge12與原治理assert保持不變，沒有新增bridge或豁免。

G0／G1／G2／G3／G4完整靜態證據皆核exact paths、來源blob／working SHA與合法分類；G3固定ROOT QA寫入的F4案例裁為write-risk-dry-run-required，原候選推薦留在raw。G4尾段欄位錯位修正後才接受完整49項；G2額外helper偏差中止且未採用。靜態assert數與來源檢查不是runtime pass。完整固定head、四治理blob、來源證據hash與raw／JUnit索引見本機 `output/qa/i156_final_handoff_20261006.json`。

source_id直接批准修補保留：7f56558c→fcef6580的專屬9例通過；384a46c2另以既有中央bounded composition＋原Journal保存／唯讀reader／新程序驗證正向1例通過（3.01s），是重疊增量，不累加為10項獨立案例。unknown source/account/clock仍拒；相鄰FlakyJournal缺legacy_read_only的原fixture1fail已在固定原基準重現，未放寬assert。

剩餘工程阻塞：ML boundary仍676檔／6違例／exit1（H1–H5／H8），P2正式Paper producer接線尚未接受，不宣稱正式私人鏈完成。原9Stage＝1done／8partial／0pending、24UX＝2done／22partial／0pending、七有限closed UX03/04/05/06/09/15/17不變；F1 18.6219658%（門檻20%）與Journey8.109s（門檻8s）原性能例外保留。自然累積不作工程gate，未知來源／PIT／模型資格不造。完整UI union只沿用c9d57fc7已准範圍；本次沒有重跑或提升整Stage／UX。無push／mainmerge／真DBwrite／私人啟用或migration／正式Task／ACL／清理／交易／foregroundNative／訓練。

本文件是本輪結果索引，不是另一份 roadmap。唯一原計畫／Danny Quant 仍為 output/plans/baldr_product_experience_plan_20261004.md，原文僅 append。最初 base a42b2cb9df44b2fd928104ae02992b0e557c2a39；本輪已准固定測試樹 c9d57fc704fd441a3b25af697065d4d26a8d48ec。原9stage＝1 done／8 partial／0 pending、24UX＝2 done／22 partial／0 pending不改；七有限closed（UX03/04/05/06/09/15/17）、F1 18.6219658%(<20%)及Journey8.109s(<8)原性能例外保留。

## 十五包逐包結果

「有限工程完成」只關本包具名範圍，不等於整Stage/UX done，也不把正式source/model/account/PIT/clock unknown轉合格。完整commands與原失敗／跳過均保留於各QA及ignored raw。

| 包 | 本輪裁決／實際交付 | 可核證據與尚缺 |
|---|---|---|
| B01 基線與boundary | 新3 exact readonly symbols／fresh import+DTO零data I/O與拒writer/trainer完成；summary變化／基本面缺件真修補完成 | 原11→8→6；H6/H7 exact DTO裁決已採。676檔仍6且exit1，H1–H5/H8待工程修補，不是全倉PASS |
| B02 Windows COW | JSON／SQLite v1/v2、canonicalDB與suffix深Unicode、convert→activate→append→rollback→新程序有限工程完成 | 同版234 pass／2 Win1314 skip；source bytes/metadata及原receipts不變，target新增revision保留。正式migration未做 |
| B03 盤勢／主導覽／Update／Runtime | 四用途沿既有callbacks、當下搜尋不借保存身份、刷新收合、白話影響／unknown資料日、原source／selection保留，有限工程完成 | lane13新home與24新update-runtime；中央64用途增量／mandatory收據另列。沒有Native／真人證明 |
| B04 選股／觀察 | 已保存exact chooser／cancel/stale、結果內filter保全分母、reason／confirmed／deferred在原ledger CAS與新程序，有限工程完成 | 原97收據與中央增量重驗source/revision/pins；沒有改分數／市場evidence或正式activate |
| B05 圖表首批 | typed保存marker／全量價格MA精確表／鍵盤／十字線／finite外連、原row custody與Main background stale守衛完成 | source_id三檔直接批准後已修（7f56558c→fcef6580），新context來源保存及exact retry/stale守衛專屬9pass；相鄰FlakyJournal既有fixture1fail分列。原有已保存合格source可畫；舊缺source/account/clock仍拒，不migration |
| B06 三帳持倉摘要 | 人工／聲明／Paper exact分帳、估值unknown不冒總值／安全、原DTO摘要與cache、注入guard，有限工程完成 | 中央Main已route+paths注入；原navigation node同版通過。Paper producer私人writer路由屬B09剩餘，不偽裝此UI已替它完成 |
| B07 規則／歷史 | 一條真typed fixed-v1／next_open執行→原保存artifact→新程序完整card；兩legacy＋Registry四類查找／exact返回、有界同raw讀／cancel-parent關閉，有限工程完成 | 舊154/54/11只有worker報告無raw，不作可核收據；中央5與本輪64含真保存／新程序有JUnit。Registry原shared讀取鏈未宣稱敵意raceproof |
| B08 路徑／selector | canonical身份不變的Windows renderer／URI、nofollow/link拒絕、pure frozen域route與generic selector，有限helper工程完成 | 模式/root任一缺或blank beforeIO拒，無personal→legacy fallback。容量不是單一政策：snapshot20GiB，capture等200GiB有效max保留 |
| B09 個人Portfolio consumer | typed consumers／snapshot、每I/O exact allowlist＋paths／sidecars guard、Paper固定ro/query_only、Ledger callbacks、Journal繼承相容，包內完成 | owned146 pass raw核對；Main/B06/Journey同帳已接。Paper cost／benchmark／daily producer尚未路由到選定private root，是可修工程，不以未批准正式啟用替代 |
| B10 私人覆盤／notes／weekly | private Review與唯讀market refs分離、source refs/hash、selected history／weekly CLI、notes create-only backup/restore有界API，包內有限工程完成 | raw42／28等各同版收據不累加。中央64包含private save→新程序；notes尚無新GUIbackup按鈕，正式backup/restore/migration未啟 |
| B11 八家族字典 | exact八族／十一欄immutable字典、舊3features／2MA methods及hash不變，目錄工程完成 | 31 cases；第二家族producer尚未實作，需U1明示method/參數／來源。BBANDS30/2/2/SMA upper候選是可review選項，非完整compression定義 |
| B12 daily runtime | explicit calendar完整coverage／terminal／clock／sourcebinding、defaultoff runner、quota/segment lock/timeout/cancel、深路徑IO，有限offline工程完成 | 103不同cases，exact int非bool zero-exit補件39＋terminal2各負例沿收據；不降200GiB、不啟Task或造official calendar资格 |
| B13 模型輸入 | pure Protocol／原6pins／actual sessions／split/purge/embargo／path label／preproc／分母／seal與原runner bytes回驗，supported synthetic工程完成 | 40新／47未改base收據；真U2未決waiting，ready僅synthetic://offline、endpoint gross介面，全部正式／訓練/PIT資格false |
| B14 shadow evidence/control | 原B13 public replay/newseal、append-only freeze／獨立witness、明示monitorpolicy／完整分母、真正synthetic stop→rule dispatcher→新程序，有限工程閉環完成 | composition53 raw/JUnit已核；原wrapper positive但unknown→waiting與syntheticknownclock positive分報。CAS後I/O failure namespace failclosed；正式model control未接 |
| B15 增量整合／文件 | 已准樹四用途64／Workbench85／validator25+4skip、完整Manual／Snapshot／architecture／index與classification同步 | full roots mypy839source通過；changed Python100檔compile及quant guard通過。inventory1105/fs1281/docdrift0/stale0，176未登錄仍failed；不是全App／全部UX完成 |

## 原九階段對照

| Stage | 原狀態保留 | 本輪對照與剩餘類別 |
|---|---|---|
| 0 接手量測 | done | 固定HEAD／ownership與原prefix沿用；不重開舊量測 |
| 1 效能／語言 | partial | B03–06摘要／unknown／收合增量已採；Native／真人與原性能例外維持 |
| 2 特徵／規則快照 | partial | B11能力字典、B12配置工程；第二家族需U1，source/PIT外部資格不造 |
| 3 融合選股／個股 | partial | B03/04/06與中央64差異已驗；新跨頁Native／真人未授 |
| 4 圖表 | partial | B05 first batch同源表／markers／鍵盤已接；source_id三檔blocked，UX07原生取代原型需U1裁決 |
| 5 自然樣本 | partial | B12/13 isolation工程已採；官方actual sessions/provenance及自然forward成熟另列，不作工程gate |
| 6 規則／全頁 | partial | B07保存卡／歷史與B08–10consumer私人路由已採；Paper producer選定root工程仍缺，正式migration／Native另批 |
| 7 ML／shadow | partial | B13/14 synthetic完整閉環；6boundary工程待修、U2真目標與合格來源待決，不fit/promotion |
| 8 整合交付 | partial | B15已准固定樹checkpoint；Native／3–5非開發者／正式運行／自然效果仍各自接受 |

## 原二十四UX對照

| UX | 原狀態 | 本輪包對照／仍保留界線 |
|---|---|---|
| 01 基線 | done | B01/B15固定樹；不重做 |
| 02 狀態詞彙 | done | B03–06沿原字典，不撤done |
| 03 導覽 | partial | B03/B15；原有限closed保留，Native／真人未授 |
| 04 每日名單 | partial | B04/B12；原有限closed，正式source運行未啟 |
| 05 篩選摘要 | partial | B04/B11；原有限closed，第二家族需U1 |
| 06 個股摘要 | partial | B05/B15；原有限closed，source_id三檔待批准 |
| 07 圖表可行性 | partial | B05原生default＋五核symbol外連；U1原生決議／有限原型取捨，外部授權與支援不冒稱 |
| 08 同源互動圖 | partial | B05原保存／表／marker/Main；source_id接線待批准，更多指標與週月為原後續 |
| 09 生命週期 | partial | B02/B04/B15增量；原有限closed，真長增長另驗 |
| 10 多策略 | partial | B11字典完成；2MA仍1family，第二家族未做 |
| 11 規則卡 | partial | B07真typed保存／新程序完成；source-only不造績效 |
| 12 回測歷史 | partial | B07統一readonly查找／budget／exact返回完成；不遷移來源 |
| 13 市場觀察 | partial | B03刷新／B04原因與狀態完成；真人待驗 |
| 14 持倉工具 | partial | B06/08/09/10consumer與Main完成；Paperproducer私人路由工程與真遷移分開 |
| 15 文件真人 | partial | B15完整Manual增量；原有限closed，3–5真人未驗 |
| 16 資料矩陣 | partial | B11八族欄位／暖機／缺件；正式/PIT權威未知 |
| 17 性能 | partial | 原有限closed、F1/Journey例外保留；只報新增資源界線，不重開舊門檻 |
| 18 特徵規則 | partial | B11字典；第二家族producer需U1規格，未新造scoring |
| 19 快照容量 | partial | B02/12深路徑／segment/quota／200GiB不降；正式root/ACL/真增長另批 |
| 20 自然收集 | partial | B12 typed calendar/terminal/offline；正式Task/account與真決策receipts未授 |
| 21 成熟labels | partial | B13/14原path/clock/pins回驗；U2 target/cost/benchmark與自然成熟另列 |
| 22 ML候選 | partial | B13 synthetic輸入／B14完整共同分母；真合格model／效果／fit未授 |
| 23 shadow | partial | B14synthetic實際dispatcher停止，不是receipt假控制；6boundary仍工程待修，正式control未啟 |
| 24 整鏈 | partial | B15四用途delta checkpoint；七closed與來源不變保留，Native／真人／自然效果不混作工程完成 |

## 仍可修工程與精確後續scope

1. **source_id三檔**：ui_qt/widgets/decision_continuity_controls.py、app_module/decision_continuity_controller.py、tests/test_ui_qt_decision_continuity_controls.py。只保存已驗context原source_id、exact retry command與原Journalwriter傳遞；既有DecisionIdentity或未知欄保持空，不修改Journal/shared DTO，不補舊record。自動審核因先前「先不修改」與擴鎖訊息衝突拒絕；父層直接人類確認pending，當前零修改／不繞過。批准後只跑UI accept→原writer→reader→marker及source/retry/context負例，不重整條mandatory。
2. **六ML boundary仍不是豁免**：B01-H6/H7 exact label契約已採，只准原caller的HistoricalLabelRow/Spec；fresh-process import／DTO零data I/O、namespace/writer/trainer/其他caller拒絕與原unknown資格均有收據。最新676檔guard剩H1–H5/H8六違例、exit1：三條ML反向app imports，personalization的natural proof verifier、calibration training exception、stock provider直接restated loader，仍需精確port/contract修補。未豁免整module或關guard。
3. **176 inventory是可修治理工程**：不是176已知功能bug，也非自動排除。完整paths在 output/qa/b15_inventory_integrated_20261006.json::missing_inventory_paths；包含兩個support helper及UI/ML/CLI等不同類。後續鎖原四個B15檔＋具名subset，按實際imports/assert與write-risk逐檔分類，保direct12，不用全部歸unit/candidate取綠、不修改runner。可分每波≤20具名檔；一次metadata校正，必要collection只在正確環境另跑。當前全部176仍未登錄、audit failed。
4. **Paper producer routing**：消費端ro/custody已完成，writer仍缺選定private root的工程。下一獨立slice可先鎖 app_module/paper_trade_ledger.py、app_module/paper_equal_weight_benchmark_ledger.py、app_module/paper_equal_weight_benchmark_builder.py、scripts/run_paper_portfolio_daily.py＋新增具名synthetic test與QA；沿personal_paper_store_paths/route+paths，before每mkdir/connect/write/sidecar exactguard、legacy readonly拒writer。若還需import/builder/baseline/其他CLI才擴鎖，不能把此四檔稱全producer覆蓋。不改金融公式、無真Task或migration；full syntheticdaily→原保存→readonly consumers新程序證明同account/root及source不變。

### 八條精確依賴與處置

| # | caller → symbol | 工程處置／保持限制 |
|---|---|---|
| H1 | ml_module/current_observed_feature_snapshot_composer.py → app_module.recommendation.queries._read_regular_file_no_follow | 把app查詢留caller orchestration，ML接受有界readonly port；no-follow／source pins不放寬 |
| H2 | 同caller → app_module.saved_recommendation_queries.build_recommendation_execution_queries | query建構移caller，ML不反向import app；完整母體／原query identity保留 |
| H3 | 同caller → app_module.saved_recommendation_queries.execution_result_config | config建構留caller，不造source或fallback |
| H4 | app_module/personalization_read_service.py → ml_module.recommendation_calibration_evidence.verify_natural_maturity_session_proof | bounded verifier port／純契約移置裁決，原session proof/availability/hash exact，不能增natural authority |
| H5 | app_module/recommendation_calibration_consumer.py → ml_module.recommendation_calibration_training.InvalidCalibrationOutputError | 純exception契約分離且保原class/serialization相容，不能白名單training module／fit |
| H6 | app_module/rule_research_label_readiness.py → ml_module.historical_contracts.HistoricalLabelRow | exact純DTO裁決已採；cold import／建構零data I/O，writer／namespace／其他caller仍拒絕 |
| H7 | 同caller → ml_module.historical_contracts.HistoricalLabelSpec | 同H6已採；原label政策／版本／target及unknown不變 |
| H8 | app_module/stock_research_report_provider_adapters.py → ml_module.current_restated_research_bridge.load_current_restated_outcome_model | provider注入已核bounded artifact/source/target port，view/projection不載模型；不是整ML module allow |

H6/H7 worker 56ae8d82 → 中央4cea589d已有限接受；H1–H5/H8仍六項真工程FAIL，不改成waiting-for-time。原global dependency assert／DTO／reader與source_id三檔逐blob未改。

## 下一個有限包：B01-H6/H7純label契約裁決

在目前source_id等待時，可由父層鎖 ml_module/shadow_boundary_guard.py、tests/test_ml_shadow_boundary_cli.py＋新 docs/06_qa/BALDR_ML_LABEL_CONTRACT_BOUNDARY_20261006.md，固定在本批最終中央HEAD。app_module/rule_research_label_readiness.py與ml_module/historical_contracts.py只讀；只裁exact HistoricalLabelRow、HistoricalLabelSpec。當前contracts直接imports只有stdlib dataclass/date/Literal，仍須fresh process module import與DTO construction零data I/O實測後才接受exact symbols，並加整module/wildcard/writer/trainer/其他caller拒絕。若發現transitive I/O則回報，不移共享DTO或增全module allow。驗收new0、總8→6、原label版本／結果／unknown旗標不變；剩6及原global assert失敗保留，不xfail／不刪assert。這是ownership提案，當前尚未實作或授新增allowlist。

## 真正U／敏感啟用／自然與外部證據

- U1：具體第二家族method/參數/來源及完整compression定義；圖表原生決議是否取代LWC局部原型。原生同源／markers已可用；目錄八族不等於八策略已實作。
- U2：primary target/horizon/metric、price basis、benchmark/cost版本；B13支持介面不替使用者選真研究契約，不用synthetic最佳數值選目標。
- 敏感U3/U4：formal calendar/source配置與account/cadence/Task、200GiB/容量例外、ACL、私人真backup/convert/activation/rollback、formalmodel stop/resume/promotion、fit/train、交易；這些沒有本輪授權，必須具體操作包批准。
- 只自然等待：決策後forward/label mature／成熟樣本及長期實際效果的時間累積。這些不阻擋已授隔離工程；不能造known availability或縮短既有合格政策。
- 外部／真人證據：官方actual session與原source可得性／PIT provenance、模型實際OOS品質、外部圖授權／support，以及Native／3–5非開發者readability。unknown有有效終點；缺producer/caller/guard不能躲進這一類。

## 同版驗證收束

四用途64 passed34.77s：output/qa/b15_four_journey_union_20261006.xml SHA9df22daa102af5aaefca1f4309d51c2f3fd44ccb7f96db412f3efceb7598ba67；raw SHA4a8a6f3441a552838300b64424a0317e3bbaaa9d5e312eb470f0953662db3d14。Workbench85 passed2.63s：XML63d7d419a2133259403c3a37df2c0630f22db0aedbe3dccf94b2d341916250c7。Update validator25pass／4skip／0fail，log98e16cca3b2a29f93f320ddbc9b402f015a658b928ab5704e594255b9f09c88f；skip實際下載／merge等保留。完整full-roots mypy839source無錯，exit0／15.78s，log SHA9b116a968124af43e0d34192d94f53105221e7f29f60a50c61e81d383929d60e；兩個untyped body annotation-unchecked提示保留。100個自最初base至固定樹變更Python檔compile與quant precision/look-ahead guard皆exit0；raw commands/hash見 output/qa/b15_compile_quant_receipt_20261006.json。

本批所有變更只local dev commit；無push/mainmerge、正式DBwrite、personal migration/activation、Task、ACL、Native、fit/train或交易。保存來源與其他lane dirty/worktree不清理；原plan完整prefix保留。


### Paper ownership 實際 I/O 核對補正

純 app_module/paper_portfolio_daily_runner.py 不做 I/O，保持唯讀；完整 selected writer／雙 CLI 最低五個 production：兩 ledger、benchmark builder、run_paper_portfolio_daily.py、build_paper_equal_weight_benchmark.py。可平行先派兩 ledger 與 inventory 首20，後派 builder＋雙CLI；精確 API、ownership、依賴、驗收與 prompts 見 [下一波派工收據](BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md)。這是待父層鎖定的派工 proposal，未把未接線 producer 宣稱完成。

## B01-H6/H7 審核整合收據

前節「下一個有限包」是派工時的歷史提案，現由[有限label裁決](BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md)取代待辦狀態。三檔exact scope、全部raw hashes與63pass／0fail／0skip JUnit已核；中央只重CLI affected subset並另跑guard，未重四用途／mandatory union。中央raw見output/qa/b01_h6_h7_central.log／xml與b01_h6_h7_central_guard.log；最終結果在output/qa/baldr_b01_h6_h7_integration_20261006.json。原9stage／24UX仍1/8/0與2/22/0、七有限closed／性能例外保留，未升Stage／UX done。


## I20／P1有限採入與一次清冊收尾

I20 worker2f7c467c→中央95d381a4；四治理檔exact、20來源blobs／舊entries／direct12與raw hashes核對，中央metadata1281／1125／missing156／docstale0，exit1。worker治理10pass/3原global完整性FAIL收據保留，不稱局部分類全完成。P1 workerd4d32fe2→中央e1857a31；兩ledger＋newtest/QA，172pass0skip immutable raw/JUnit核對，中央affected44pass5.66s。routed route＋paths＋exactportfolio、獨立benchmark_id，read_only缺庫不建／writer拒legacyreadonly；原金融AST/SQL與原子交易未變。builder／雙CLI尚由P2接線，正式writer未授。P1另加一具名新test，現預期1282／1125／missing157（原156＋此1），待同一I156owner分類；不假把I20當已含P1。

全部156可本次一次有界分類完成，由一owner寫四治理檔、四readers只讀交逐檔用途／fixture／assert／副作用與分類理由，見[完整範圍及prompts](BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md#i156-一次有界分類收尾i20-採入後)。不是每20循環，不為增registry啟用direct或改tests/support API；來源pin索引classification仍not_yet_reviewed。Stage/UX與六boundaryFAIL及source_id批准未變。

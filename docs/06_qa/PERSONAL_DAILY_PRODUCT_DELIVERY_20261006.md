# 個人日常產品交付工作包與驗收矩陣

> 目標交付日：2026-10-06。此為 2026-09-27 的承接盤點與驗收基線，不宣稱 WP1–WP5 已完成。本文不替代各服務的 domain contract 或正式資料收據。

## 目標與安全界線

交付目標是讓使用者每天能更新資料、查看規則與模型建議、明確選擇是否採用、保存決策、追蹤成熟結果，再決定繼續、停用或回退。依使用者已作的產品決策，樣本少、尚未勝過基準、尚未證明準確屬於需揭露的限制，不是個人使用的自動封鎖條件；資料錯配、look-ahead、損壞或不支援的 artifact／輸入、非有限輸出及無法核對的來源身份仍須阻止該次模型輸出。個人使用不等於正式 promotion，也不授權自動下單。

盤點完成後，依 root 核准的 source 白名單實作 WP2/WP3/WP4 切片並做隔離驗證；不得啟動正式 scheduler、正式資料 writer、full-market rebuild、模型訓練／promotion或券商操作，只允許在明確隔離的 DATA_ROOT／OUTPUT_ROOT 測試。每個切片仍須遵守已核准的路徑 owner、相依 API、rollback 與測試資料邊界。原始資料、既有 active pointer、舊 receipt 與歷史驗收結果均須保留。

狀態用語：**已接受（bounded）**只代表所列來源版本與範圍通過；**部分具備**表示已有 caller／服務但未完成該工作包；**工程待辦**代表缺少可交付 caller／契約／讀回；**外部相依**代表需要官方資料、授權或隔離 Windows 執行環境；**等待自然成熟**只描述結果樣本尚未成熟，不能反向作為個人模型啟用門檻。單元測試、fixture 或 offscreen UI 不冒充 visible native、正式資料或自然 scheduler 驗收。

## 承接版本與 WP0 交付介面

目前唯讀檢查基線是 `dev` HEAD `e5d75f7cbd3312dac391f52b5c2206d0c745bbc4`；檢查當時只有一個主 worktree。WP0 在 `d77ba23fd03a94f55fa9d63a23a3e32c66544082` 已接受，包含 288-path relevant regression（2,951 passed／5 skipped／36 warnings、817.03 秒）、R027 logical-time revision 與 R028 八案例；R028 source/runtime review 已接受。receipt `output/qa/refactor_completion_20260927/final_attempt6_external_20260927/final_candidate_root_receipt.json` SHA-256 `9ec19361748ac2a0e0de120eee62043241d42375014af3bed60b6c2a02eefd4d`，root assessment SHA-256 `b8d3f224d786f195ce5bbc8133ce95cae12a33320d627ccb27b80a1495e02b27`。5 個 skips（4 個 Windows symlink 權限、1 個 longdouble mantissa）以及 Update QA 的下載／merge skips不計為 PASS。WP0 commit 已接受；後續整合由 root 依 final acceptance 負責 stage/commit，子工作 owner 不自行 stage/commit/push。

**此證據固定在 WP0 版本，不等於目前 e5 HEAD 已重新驗收。** `d77ba23..e5d75f7` 之間另有 7 個 commits、28 個 changed paths（含 scheduler、formal input、資料日期與 Phase 3C candidate repair）；不得把 WP0 的 2,951 passed 冒稱覆蓋這些後續變更。WP5 必須以最終整合版本重新建立 route／source custody 並驗收。

可供後續工作包承接的既有介面如下：

| 領域 | 現有 owner／caller 契約 | 已接受範圍與限制 |
|---|---|---|
| technical-indicator publication | `app_module.technical_indicator_job.TechnicalIndicatorJob` 擁有 orchestration；`app_module.update_service.UpdateService.calculate_technical_indicators` 保留 public facade 並 lazy-delegate。 | R028 report 接受 bounded migration；既有 process-pool port維持父程序單一寫入邊界。原 R027 strict receipt仍是歷史 INCONCLUSIVE，不能改稱 PASS。詳見 [R028 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md) 與 [R027 acceptance revision](R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)。 |
| IndustryMapper | `decision_module.industry_mapper.IndustryMapper` 由 application composition 明示注入 company／index providers；`app_module.decision_service_composition` 建立 app provider。 | 已接受的 provider slice 為 bounded source-owner 修復，不涵蓋本輪 registry mapping version、hash-bound sidecar、上市櫃覆蓋或 historical PIT 全面驗收。相關新工作由 WP2 接手。 |
| H5 loader/bootstrap | ML-owned repaired-input contract／verified loader；app CLI 明確初始化；`scripts/build_ml_allocation_post_freeze_feature_repair.py`、`scripts/infer_ml_allocation_copilot.py` 保留既有 compatibility callable。 | H5 bounded slice 的 CLI 證據限 `--help` bootstrap 與 target-free synthetic parity，不等於 formal artifact load/predict、完整 training/release 或個人模式已接線。 |
| saved recommendation identity | `RecommendationView` 以同一 sealed execution 保存；canonical query/readback 驗 `result_id`、payload hash、artifact與 identity。Portfolio 導覽使用精確 saved result，不以同股／latest 猜接。 | 可支援 WP3 的結果身份基礎；不能由已保存結果推論使用者已採納，也不能把 Journey `LINKED` 當摘要內容簽章。 |
| personal action persistence | `PersonalizationDecisionRecorder`／`JournalService` 使用既有 append-only DecisionContinuity/Journal revision 與 typed payload，不建第二 ledger。 | 現有 recorder 要求 delivered linked prediction，適用已有 prediction 的個人 action，不足以涵蓋 rule-only choice；本輪另核准下方 `personal_recommendation_choice` typed payload。 |

## WP0–WP5 逐項驗收矩陣

| 工作包／原完成條件 | 實際 caller／現有介面 | Owner 與版本 | 證據／目前狀態 | 未完成條件 |
|---|---|---|---|---|
| **WP0.1** 穩定、可回復版本供後續開發 | `dev`、R028 facade/job、IndustryMapper composition、H5 bootstrap | root；WP0 accepted at `d77ba23`；目前 HEAD `e5d75f7` | attempt6 receipt／root assessment 與 R028 report 已接受；d77 到 e5 有 7 commits／28 paths。 | 在最終 WP5 route 覆蓋 e5 與 WP1/WP2 新變更前，e5 尚非本產品交付的最終驗收版本。 |
| **WP0.2** 明列其他包可用介面與必要永久相容 | 三條上表介面及 source-owner contracts | root 整合；各 package owner 不得另造 store／writer | IndustryMapper provider、H5 initializer、R028 facade/job 的 bounded source evidence 已存在。 | 新增個人 policy、registry provenance、decision choice 的實際 API 仍待 owner freeze；須追加 interface/change-list 與 hashes。 |
| **WP0.3** 不擴張重構、不冒稱正式／自然驗證 | branch source graph、known aliases、strict R027 history | root | R027 strict 與 revision B、R028 accepted migration 分帳。 | 本輪只沿使用者六包；unknown formal artifacts、native UI及自然 scheduler依各包另驗，不補造證據。 |
| **WP1.1** 正常日期更新並保存有效預測／推薦 | `scripts/scheduled/run_daily_data_update_quick.py`、正式 input／learning wrappers、RecommendationService | `retirement_luna_max`；目前 e5 scheduler/data commits | 已有受控 daily wrappers；attempt6 Update QA 25P/0F/4S只證明當時 validator，不證明自然日排程或正式資料寫入。 | 對最終 config、資料日期、run identity、錯誤終態及結果 readback 建立隔離／授權後的完整證據；本輪未執行 scheduler。 |
| **WP1.2** 休市時正常跳過，依賴失敗不冒充成功 | formal schedule gate、market calendar、closed-day coverage reuse | `retirement_luna_max` | 後續 commits `9f443385`、`660c2b2b`、`ba92f56c` 對齊 trading calendar／closed-day contract；attempt6 Update QA仍有4項skip。 | 在當前 e5 source做精準 route與確定型 offline case；自然排程 readback屬外部／需 root另核准，不因本矩陣啟用 task。 |
| **WP1.3** 同一 run 重跑不重複累積證據 | recommendation snapshot、learning/capture run identity及重試 caller | `retirement_luna_max` | 本輪只確認目前 wrappers與既有 receipts；未重跑最新 e5 routes。 | 用相同 run/request identity 實測 idempotent readback，並核對取消、部分失敗及 retry。 |
| **WP1.4** outcome 成熟後可被 learning consumer 接收 | `run_banktaiwan_recommendation_learning_daily.py`、learning evidence/read model | `retirement_luna_max` | projection/consumer 已存在；WP0 receipt不等於自然成熟 outcome consumer驗收。 | 以同一 producer→capture→consumer lineage證明接受一次且不重複；需自然樣本時標等待成熟，不阻模型個人試用。 |
| **WP1.5** 未成熟樣本正常等待，不被標成工程故障 | maturity statuses／learning read model | `retirement_luna_max` | 產品規則已明確區分等待成熟與工程錯誤；目前未以 native daily flow驗證。 | 顯示明確「等待成熟／下次檢視」與資料缺件分開；不能把未成熟自動當失敗或阻止個人使用。 |
| **WP1.6** 需要正式寫入／scheduler時先有具體執行方案 | Windows Scheduler／正式 writer | root 審核，owner提供 proposal | 本輪未啟動或改動 scheduler。 | 每項正式操作須另給 target、前置備份、rollback與驗收 readback；不包含在本次 read-only 承接。 |
| **WP2.1** 對外分析欄位可追來源、日期、版本與可得時間 | `data_module/company_registry.py`、`scripts/update_company_registry.py`、`data_module/industry_mapper_data_provider.py` | source owner `retirement_luna_max`；RecommendationService mapping consumer由 `boundary_luna_max` | 已列出最窄新 source slice：6-column CSV、hash-bound versioned sidecar/provider attributes；尚未有本輪 freeze/receipt。 | 完成 writer/provider的單一來源契約與 app consumer接線，精確驗每欄 provenance。 |
| **WP2.2** 今日分類可用但不得回填為歷史 membership | industry index／company registry／historical PIT membership | `retirement_luna_max` + consumer `boundary_luna_max` | 舊 IndustryMapper injection bounded slice已驗；不等於新 registry mapping或 historical PIT coverage完整。 | 驗今日 mapping與 historical `available_date`／PIT membership分開；不得用今日 mapping解鎖歷史 decision。 |
| **WP2.3** 缺來源、過期、覆蓋不足可理解降級 | data providers → recommendation/screening caller → UI | `boundary_luna_max`／WP3 UI `validation_luna_max` | 現有 provider/RecommendationService有 diagnostics；本輪尚未用新 provenance payload 驗 UI降級。 | consumer以實際 payload顯示 source/date/coverage/blocker及可操作下一步，並在缺件時阻斷錯配模型輸入。 |
| **WP2.4** UI、推薦、模型使用同一來源契約 | `app_module/recommendation_service.py` 與 WP4 personal inference consumer | `boundary_luna_max`；UI由 `validation_luna_max`呈現 | mapping provenance consumer是已知接線需求，尚無新 slice review evidence。 | source/provider、RecommendationService、模型 caller需同一 version/hash/date identity，差異時 fail closed並測 readback。 |
| **WP2.5** 工程缺口與外部來源／授權分開 | update_company_registry official source與 mapping custody | source owner `retirement_luna_max` | 外部官方資料／授權需分帳，不預設 fetch 或 apply。 | 列出來源可得性／授權與正式更新方案；沒有授權的範圍標外部相依，不偽造 coverage。 |
| **WP3.1** 今日市場→產業→個股→推薦／模型建議可操作 | `ui_qt/main.py` 的9-workspace composition與 `stockResearchRequested` signals；`RecommendationView` | `validation_luna_max`（UI）；boundary（app mode API） | 已有 MainWindow導覽與相同推薦 context；current recommendation mode button是新手／進階配置，不是模型模式。 | 把明確 personal-use mode接在現有 UI，不改成第二套 workflow；按一次完成後核 exact result identity。 |
| **WP3.2** 採用／不採用／覆寫與理由可保存、讀回 | `DecisionContinuityController`、`PersonalizationDecisionRecorder`、`JournalService` | UI owner `validation_luna_max`；root已核准 typed choice介面 | 現有「納入研究／略過」明確是 research status，不是 Advice採用；personal action recorder只接受 linked delivered prediction。 | 新增 `personal_recommendation_choice` payload，schema ID 為 `personal-recommendation-choice.v1`：bind canonical verified execution、result/stock/date；choice為 adopt/reject/override，override必有結構化 reason；model evidence optional但存在時 exact-bind。採用／讀回走既有 append-only Journal，不建第二帳本；舊 ACTION_ACCEPTED/SKIPPED含義及allowlist不變。 |
| **WP3.3** 保存、換頁、重開後維持同一 result/source identity | `RecommendationView` save + canonical readback、Journey、Portfolio exact-result navigation | `validation_luna_max` | offscreen actual MainWindow＋synthetic Service/UI save/readback/restart已有 bounded pass，attempt6 relevant route已接受；Portfolio P2只驗 source navigation identity。 | 完成個人 choice新payload與 mode/policy context的跨程序讀回；不把 Journey `LINKED`當展示內容簽章，也不以同股/latest替代。 |
| **WP3.4** 區分模型建議、規則建議、使用者決策、真實／模擬成交 | Recommendation result/provenance、personal action、Portfolio/Paper views | `validation_luna_max`呈現；`boundary_luna_max`產生應用身份 | UI已有 recommendation/calibration provenance與多條研究/Portfolio lane；沒有明確 personal mode/choice完整串接。 | UI與記錄要用欄位而非文案推斷；choice不得生成 fill、Paper event、formal credit或broker order。 |
| **WP3.5** 真實 UI 完成一次端到端操作驗收 | 可見 Windows `ui_qt/main.py`＋root `@oai/sky`操作 | `validation_luna_max`準備/ Manual；root操作 | 現有 runner與 pytest設 `QT_QPA_PLATFORM=offscreen`，synthetic provider/scorer與自動 dialog；這不是 visible native或真實使用者互動。 | UI完成後，在隔離 `DATA_ROOT`／`OUTPUT_ROOT`以 visible Windows window操作並重啟讀回 exact IDs；不得用fixture冒充官方資料。visible automation也須標為 automation，不稱真人操作或正式scheduler。 |
| **WP3.6** 缺資料時顯示可行下一步 | update/source status → recommendation/research view | `validation_luna_max` + WP1/WP2 owners | 有 blocker/quality fields，但新 source coverage caller尚未驗。 | 對來源缺件、過期、模型無效、尚未成熟提供不同 next step；不得單顯示 disabled或通用技術錯誤。 |
| **WP4.1** 規則／模型輔助／停用模式由個人明確選擇 | `RecommendationView` → `RecommendationService` invocation snapshot | app/API `boundary_luna_max`；shared UI `validation_luna_max` | `RecommendationService`現有 calibration consumer產生 model projection；`ResearchConsoleView`為只讀狀態；目前無 personal-use mode selector。 | 接 `RecommendationPersonalUsePolicyV1`：`rule_only`／`personal_calibrated_probability`；顯示scope/revision/model identity，invocation前取得不可變snapshot，執行中切換不得改變當次run。 |
| **WP4.2** model mode真接日常 recommendation caller並說清影響 | `RecommendationService._apply_recommendation_calibration`與`RecommendationView` | `boundary_luna_max`、`validation_luna_max` | 現行 calibration projection只附加 probability/ranking metadata；rule仍是 symbol/top-N selection authority，`top_n_changed_by_model=False`。 | 畫面明示 model影響的欄位；本次政策只接受個人選擇使用 calibrated probability，不自行改 rule symbol/top-N或 formal promotion。 |
| **WP4.3** 小樣本／未勝基準時可選用並揭露限制 | calibration/evidence projection + policy selector | `boundary_luna_max`與UI owner | 個人決策已接受此產品政策，但目前 shadow/consumer readiness仍不是可選 personal mode。 | 用明確政策覆蓋「只讀 shadow」限制，不把自然勝基準／樣本數作工程必需門檻；狀態仍需顯示樣本、範圍、日期及不確定性。 |
| **WP4.4** 壞輸入／artifact／輸出阻止本次模型輸出並回退 | inference verifier、provenance/source checks、rule selection | `boundary_luna_max` | 現有 loader、exact identity、source-revision與non-finite守門在各自 bounded scope已存在。 | personal mode呼叫同一 guards，輸入不支援／來源不一致／non-finite時撤回 model fields並保留可用 rule result；加入真 caller負例。 |
| **WP4.5** 保存模型/資料/模式/採用政策 identity | saved execution/context/read model/typed choice | `boundary_luna_max` + `validation_luna_max` | 已保存 calibration model/dataset/provenance欄位；個人政策hash/revision尚無。 | saved result與readback綁 policy mode/revision/hash、model/dataset/source identity；policy更換不追改歷史 result。 |
| **WP4.6** 與 rule/population baseline同 scope比較 | recommendation learning/effectiveness read models | `boundary_luna_max`；natural outcome由WP1 | 現有 bounded learning/evaluation projections與多lane identity可讀。 | 新個人模式須同result/candidate/decision date/horizon/cost scope做 read-side比較；不得混合 historical、natural、synthetic或不同 cost/horizon。 |
| **WP4.7** 顯示繼續、建議停用、候選替換、資料不足 | Research Console／personal mode status | `boundary_luna_max`、UI `validation_luna_max` | Console目前只呈現 read-only readiness/status；沒有完整 personal control與個人評估 action。Root於2026-09-27唯讀檢查看到 global active pointer v2 為 `rule_only`；候選 `rec-cal-29c1b6129396a3885a89d080` 的 `training_as_of` 為 `2026-01-28`，但缺 `training_lineage_manifest` 宣告，現有資訊只能標為 `legacy_unproven`，不是可用模型的載入或預測證據。 | 建立能支援判讀但不自動切換的個人狀態；展示候選具體不合法原因及下一步，提供 rule fallback；小樣本是限制提示，不因低績效自行改 global pointer。 |
| **WP4.8** 新候選切換由使用者確認，rollback可操作 | existing version/pointer/readiness infrastructure + personal policy CAS | `boundary_luna_max` | 尚無 personal-use selector。現行 global active pointer 是 `rule_only`；已授權的 shadow/auto 比較仍保留，不得概括成所有 global authority 均已停用。 | 使用明確 local config path與CAS revision；預設 rule-only或使用者已保存的 policy；切回規則/指定版本有歷史readback，不更動 global champion/active pointer。正式 scheduler未執行。 |
| **WP4.9** 冷啟動、模型缺失、失敗回退、版本切換驗證 | app service plus visible recommendation UI | `boundary_luna_max`／`validation_luna_max` | 內部 guard與rule fallback存在；新 personal mode caller未驗。 | 以同一 UI caller驗五條安全路徑及 saved context；結果讀回一致，無模型時清楚顯示 rule-only。 |
| **WP5.1** 固定可回復整合版本 | final git revision、frozen route/source manifest | root | WP0 d77與R031 attempt6 accepted；e5後續7 commits未被該receipt覆蓋。 | 根據所有source owners的final freeze建立新 version/scope與rollback commit list；不得只引用舊2951測試。 |
| **WP5.2** 一份可每天照做的 Manual | `APPLICATION_MANUAL.md` §2、§6、§7、§8、§9、§10 | `validation_luna_max`，於UI/source contract freeze後 | Manual有保存推薦、跨頁追溯、個股研究、持倉/Paper等既有流程；現行頁面沒有新個人模式操作。 | 待 real caller/visible workflow穩定後更新入口、步驟、模式、限制、判讀、停用/回退與排錯；本輪不先改Manual。 |
| **WP5.3** 工程未完／外部相依／等待自然結果分開 | 本矩陣＋root final acceptance | root | 本文建立分類及證據入口。 | 每包source freeze後更新狀態；正式資料/official scheduler/native UI/unknown artifacts不可由synthetic receipts推升為PASS。 |
| **WP5.4** 10/6之後持續收集、比較、改善方式 | existing learning/outcome read models + Manual | root整合 | Roadmap已有較長期 evidence/portfolio方向；本產品交付尚無新增日常流程。 | 在Manual寫明每日保存／檢視與成熟日期後比較，不自動訓練、promotion或下單；效果持續觀察與工程驗收分帳。 |

## WP5 十個操作情境清單

| # | 情境 | 現有 caller／證據 | 狀態及完成條件 |
|---|---|---|---|
| 1 | 正常交易日：資料更新→推薦→保存 | Daily wrappers、RecommendationView save/readback；隔離 journey有 synthetic round-trip | **未完成全流程驗收**；須在最終個人mode/資料契約下保留run identity並核 readback。 |
| 2 | 休市日：明確跳過且不寫假資料 | formal calendar gate與closed-day code；e5後續commits | **工程有入口、自然scheduler未驗**；在 isolated route驗終態與0不必要writer，再另審 scheduler授權。 |
| 3 | 過期／缺漏來源 | provider diagnostics、as-of/PIT guards | **部分具備**；新增 WP2 mapping provenance後要驗跨 source→UI→model，同時給下一步。 |
| 4 | 模型樣本少／未勝基準但使用者選擇使用 | 使用者已接受政策；現有UI沒有 personal mode | **工程待辦**；必須能明確選用並呈現限制，不能以自然績效作啟用前置。 |
| 5 | 模型輸入或artifact無效 | existing verifier/provenance guards及rule projection fallback | **guard bounded具備、personal UI caller未驗**；同一實際 caller負例須撤掉model output並保持rule result。 |
| 6 | 採用／不採用／覆寫理由 | DecisionContinuity、PersonalizationDecisionRecorder與核准的typed choice contract | **已定最窄契約、未實作/驗收**；append與exact readback共用Journal，不用研究 accepted/skipped代替。 |
| 7 | 保存並重新開啟讀回 | offscreen MainWindow+child readback test、canonical query | **synthetic/offscreen bounded pass**；visible Windows操作與新policy/action payload跨程序回讀待驗。 |
| 8 | outcome尚未成熟 | learning/evidence projection statuses | **可表達等待成熟，沒有本次natural sample驗收**；需顯示 horizon／下次檢視，不封鎖個人啟用。 |
| 9 | outcome成熟後評估 | evaluation/learning read models | **工程元件存在、無當前自然成熟個人decision evidence**；同scope baseline比較與lane label需讀回。 |
| 10 | 停用模型／回退版本 | global candidate/shadow console為read-only；未有 personal-use selector | **工程待辦**；明確CAS policy切換與回退讀回，不動 global champion、scheduler或formal promotion。 |

## 已核准的 WP3 choice contract 與最窄 UI owner

Root已核准的 source 白名單為：`app_module/personalization_contract.py`（新 DTO、不改既有 Envelope bytes/schema）、`app_module/personalization_action_recorder.py`（新增 method，不放寬原 linked-prediction gate）、`app_module/journal_service.py`（可選 typed payload keyword）、`app_module/personalization_read_service.py`（exact typed choice read projection）、`ui_qt/views/recommendation_view.py`、`ui_qt/widgets/decision_continuity_controls.py`；新增測試路徑為 `tests/test_personal_recommendation_choice.py` 與 `tests/test_ui_qt_personal_recommendation_choice.py`。既有 related tests若要修改須先列出並經 root確認。

新 payload 的 schema ID 是 `personal-recommendation-choice.v1`，Journal 欄位名是 `personal_recommendation_choice`，外層採既有 `ACTION_NOTE`；不改 `ACTION_ACCEPTED`／`ACTION_SKIPPED` 的「納入研究／略過」意義、不擴 continuity action allowlist。Choice必須 exact-bind canonical verified saved execution、`result_id`、stock、原 decision date及 source identity；`adopt`／`reject`／`override`都需真實 action clock與唯一 retry identity，override須有結構化原因。模型身份可缺席並明示 rule-only；若本次實際用了 model，choice必與已保存 execution讀回的 model/policy/prediction receipt一致。新choice本身不得製造prediction、自然capture、learning row或 evidence credit。

下一個 UI 單一 owner 是 `/root/validation_luna_max`，只管上述兩個 UI paths與其測試；boundary擁有 RecommendationService個人policy API/consumer；retirement擁有每日資料與 scheduler。policy selector需等 boundary給出凍結的 `RecommendationPersonalUsePolicyV1` exact API，再在 `RecommendationView` invocation啟動前取 snapshot；worker執行期間不可透過 mutable setter改變本輪模式。任何跨 owner路徑改動先停止並由 root 重新切 scope。

## visible UI 與重跑方式

既有操作入口是 `\.venv\Scripts\python.exe ui_qt\main.py`。現有 `scripts/qa_validate_research_journey_qt.py`、`scripts/qa_cross_page_mainwindow_readback.py` 與 `tests/test_cross_page_decision_journey_mainwindow.py` 使用 offscreen／synthetic隔離資料；它們可驗服務接線、same-result identity、save/readback、錯誤/conflict，不代表visible Windows UI、官方行情或自然排程。

下一次可見 UI 驗收應由 root 在 UI source穩定後使用 visible Windows session及 `@oai/sky` 操作 `ui_qt/main.py`：先將 `DATA_ROOT` 與 `OUTPUT_ROOT`指向明確隔離TEMP，使用現有 `qa_personalization_mainwindow_save_readback` 類 runner/seed而不造第二套Journey；執行推薦、保存個人 choice、關閉重開並核對同一 `result_id`、candidate與source/mode/policy identity。桌面互動驗收尚未執行，是工程驗證待辦；若實際遇到桌面鎖定或環境限制，再記為外部相依。需由官方來源產生的資料另標正式來源readback，不可用fixture替代。Visible automation不稱真人互動；native UI smoke也不等於Windows scheduler自然run。

## 回復與責任

| 風險範圍 | 隔離與回復方式 |
|---|---|
| UI/policy/choice caller | 每個 owner先輸出 source allowlist與before hashes；若失敗只回復該slice source commit，保留append-only測試事件與QA receipts，不刪原始資料。personal policy CAS預設可回到`rule_only`；不得更改global active/model pointer。 |
| registry／scheduler／market資料 | 先用synthetic或TEMP；不apply company registry、不跑正式更新或正式writer。若需外部/正式操作，另交root審核與備份／rollback計畫，本文件不構成授權。 |
| outcome／模型表現 | 保留原行為及指標；sample不足/表現未證實列為自然觀察，不以改golden、改threshold或回填資料修復。 |
| Git | 不覆寫他人dirty paths；工作包需各自route/manifest及root review。子工作 owner 不自行 stage/commit/push；root 在 final acceptance 後依既有授權整合。 |

## 外部相依與尚未宣稱事項

- **工程待辦**：個人模式policy API與RecommendationView selector；typed personal choice writer/readback；公司registry mapping provenance→RecommendationService同契約；完整caller route及Manual更新。
- **外部相依**：官方來源可得性與授權、任何正式Scheduler task變更；均未在本輪操作。可見 Windows UI 驗收尚待執行，但目前不是已知桌面不可用的外部阻擋。
- **等待自然成熟**：個人決策及預測的實際horizon outcomes、足夠長期比較。它不阻止使用者在工程門檻通過後選用模型，但不得寫成模型有效／獲利證明。
- 未驗證未知正式serialized binaries/class paths的load/predict；未執行正式training、global promotion、formal credit或broker execution；未跑 e5 的最終WP5完整route。

產品整合順序沿用 [Post-Refactor Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 與 [6-month Engineering Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md)：先保來源可追溯及個人Decision/Outcome閉環，再按同一身份累積評估，最後才依明確權限擴充。此交付不創建另一份roadmap，也不改上述SSOT。

## 2026-09-27 最新狀態覆蓋（保留上列承接時點與歷史結果）

本段只更新目前證據，不改寫上表原始完成條件、此前失敗／跳過收據或 WP0 歷史接受。`e5d75f7c` 的後續 source graph 仍須以各切片凍結版本與當前整合回歸分別判定。

| 工作包 | 目前有證據的 bounded 範圍 | 狀態與限制 |
|---|---|---|
| WP0 | `d77ba23` attempt6：288-path route、2,951 passed／5 skipped／36 warnings；R027 accepted logical-time revision 與 R028 scoped migration。 | 已接受於 d77 版本；不覆蓋其後七個 commits 至 e5，也不替代最終 WP5 route。 |
| WP1 | Stage2 candidate-gate binding 39 passed／0 failed／78.07s；root receipt [`root_scoped_acceptance.json`](../../output/qa/personal_daily_product_20261006/stage2_candidate_gate_binding_20260927/root_scoped_acceptance.json)，SHA-256 `5dc8b6b046114d7285d923629c0c5fc8b9c803b0bafe86ae6d0b3b6218661adc`。 | 只接受 retry／metadata／clock／frozen-input binding。真實 daily producer、CLI／完整 retry 旅程、自然 scheduler 與正式讀回仍未由此證明。 |
| WP2 | 凍結 company-registry 六路徑 root rerun 27 passed／0 failed／0.79s，log [`wp2_root_pytest.log`](../../output/qa/personal_daily_product_20261006/wp2_root_pytest.log)，SHA-256 `1abb8f3b7f9146d81a94556812f0c310e0df861a80a453a89b01f0651c53dfac`。 | 僅 provider／registry bounded route；同一來源 provenance 的 UI 保存與讀回、official data、PIT 覆蓋仍待整合驗收。 |
| WP3 | 個人選擇外層 Journal binding、exact saved-result loader、sealed company-source v1/v2 label 為 bounded accepted。Source freeze [`freeze.json`](../../output/qa/personal_daily_product_20261006/personal_choice_source_v2_followup_freeze_20260927/freeze.json)，SHA-256 `dfd9e03d014adb59cba444d3b18d8e3477eae6a47f2e6d924064b6752f41db98`；root scoped acceptance [`root_scoped_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_choice_source_v2_followup_freeze_20260927/root_scoped_acceptance.json)，SHA-256 `95f6b5f1009c78570f15f91455b35b807356147058040940f420dc7fcf7cfc6e`。Focused 51P／0F；Workbench 84P，Update QA 25P／0F／4S，mypy 732 files／0 issues。 | 限上述 frozen hashes 與測試範圍；Workbench 未載入 `ui_qt.main`，Update QA skips 不算 PASS。Root 已啟動合成 rule-only visible MainWindow 操作；讀回收據尚待，不能宣稱 WP3 native／capture／成熟 outcome 閉環完成。 |
| WP4 | 五來源 policy slice root adjacent route 82P；personal live-clock slice 63P；candidate inventory slice 9P，均為各自 bounded acceptance。 | 唯讀正式候選盤點回傳兩個 `legacy_unproven`、沒有可用 pins；未證明模型 load／predict／自然個人推論。rule-only 是目前可驗路徑。 |
| WP5 | 本文件所列 source/test slices 與可見 native 手動 smoke 正在整合。 | 最終整合 route、同一結果的保存／重新開啟／choice readback、真實來源及自然成熟結果仍未全數驗收；不得以切片相加宣稱完成。 |

### 合成 native seed 的判讀界線

Root 操作中的隔離 workspace 是 `output/qa/personal_daily_product_20261006/native_manual_harness_20260927/run_01`。它只含兩筆合成公司、120 筆合成個股行情、兩個合成指數各 60 筆及空的 technical-indicator table；日期是未依官方休市日調整的 weekday 序列，companies CSV 沒有來源 sidecar。正常 MainWindow/provider 路徑讀取及 rule-only UI smoke 不會證明官方來源、freshness、PIT、模型可用、自然推論或成熟 outcome。Native 結果須以 root 的實際 SKY 操作與 readback receipt 記錄；目前尚無完成收據。

目前不執行正式資料更新／合併、scheduler、訓練／promotion、broker 或自動下單；各 skipped route 保留為 skipped，不計 PASS。WP0–WP5 整體狀態仍為 **進行中**。

## 2026-09-27 後續整合狀態附記

本附記追加本文件建立後的 bounded evidence，不覆寫上方各切片的歷史狀態，也不將分散驗收相加宣稱為 WP5 完成。

| 範圍 | 最新已核範圍 | 尚未證明／限制 |
|---|---|---|
| WP1 Bank snapshot reader | 同次排程狀態與 canonical recommendation `result_id` 綁定、精確 query/readback 與 bounded no-follow reader slice 為 17P／2S scoped accepted。 | 2 個 symlink 負例因 Windows 權限略過；自然排程未驗。這不是整條 daily update→recommendation→outcome→learning 的端到端 PASS。 |
| WP2 來源契約 | company-registry provider/sidecar bounded slice scoped accepted；舊 CSV 無有效 sidecar 時只可 current-only／unknown。sidecar 的 `available_at` 是本次 HTTP response capture 完成時間。 | 此契約不證明 official publication time、historical PIT、外部權威，也不證明 industry-index、上市櫃或興櫃完整 coverage。 |
| WP3／WP4 個人操作與 policy | 個人 choice/source-v2、capture、candidate inventory、個人來源/PIT admission 與 full-stack synthetic caller 各自有 scoped evidence。Workbench UI route 84P；Update QA 25P／0F／4S。 | 不是可見 native post-fix 驗收。來源 admission 的最終測試數與 hash 尚未固定，標為「待最終整合收據」。 |
| Stage B／Stage C 個人結果 | Stage B／C 相關 frozen route 31P／1S scoped；StageC `personal-recommendation-natural-outcome.v2` 僅為個人 outcome read model。 | 沒有宣稱自然 matured cohort 或自然 scheduler 通過。v2 只對 active model rows 計算模型結果；fallback rows 另記 coverage，不冒充模型預測。結果是 decision-date close 至官方 20-session endpoint close 的事後 close-to-close 標籤，不是成交／execution PnL。成本是可得手續費／稅費輸入下的估算；缺成本／流動性輸入時 after-cost 保持 pending／unknown。 |
| WP4 模型准入 | 目前安全預設為 `rule_only`。唯讀 inventory 中兩個舊候選均為 `legacy_unproven`，不可啟用。使用者已明確選擇 V2 指定 SQLite 來源時間信任的個人研究流程。 | SQLite 重播與內部 hash 只能核對所指定來源及計算，不能獨立證明官方歷史 PIT／publication availability；尚無外部 authority，也沒有可用的真實 PIT candidate。 |
| WP5／整體 | 尚未有本產品最終整合驗收。 | source/PIT gate 最終測試數與 SHA 尚未固定；root 將補最終 relevant regression route、mandatory checks 與結果收據。自然 scheduler、真實合格模型、native post-fix UI 均未證。 |

StageC 手動入口與參數、安全限制、狀態判讀及排錯見 APPLICATION_MANUAL §9.9.1b 後的「個人推薦模型擷取與自然結果」附記。此附記是操作說明，不是執行授權；不得據此讀寫正式來源、啟用候選或註冊排程。

## 2026-09-27 個人 V2 使用者明示來源信任 UI 附記

本段補充本 checkpoint 較早寫下的「沒有使用者來源信任回覆」狀態：使用者已明確選擇「信任我指定的資料庫」，UI 因此提供 V2 `user_declared_source_time` 個人研究設定。這不是外部 authority 回覆，也不把使用者指定 SQLite、replay 一致或內部 hash 轉成官方歷史 PIT 證明。預設仍為 `rule_only`；inventory 的兩個 `legacy_unproven` 候選不可啟用，現況沒有已證明的真實 PIT candidate。

V2 預覽與執行重驗綁定候選 pins、檔案身分及實際訓練切片（訓練窗資料列、`available_at`、來源契約、成本與 scope）。本次僅在 `coverage.source_contract.technical`、`source_disclosures.source_contract.technical`、`source_disclosures.technical.source_contract` 三處 technical contract 投影中排除 `content_digest`、`content_row_count`、`coverage_end`、`evidence_hash` 四個全庫彙總欄；另不把 replay 結果最外層的 `dataset_id`、`dataset_hash`、`source_fingerprint` 三個由全庫 source fingerprints 衍生的識別欄納入此來源切片比對。上述例外以外，其他來源與欄位仍依原契約比較；候選已保存 manifest/pins 與逐筆樣本仍獨立核對。這項 V2 個人來源切片比對不改原 replay manifest 或 global oracle。訓練窗後的更新在同一檔案身分且該切片完全不變時可保留驗證，檔案替換或訓練切片改變仍 fail closed。使用者須明確指定來源、檢查預覽、確認並保存；重啟後需重新驗證。V2 僅供個人研究，不影響 global pointer／promotion，也不代表官方 PIT 或模型有效性。

本次 UI owner focused route 為 `tests/test_ui_qt_personal_recommendation_choice.py` 28P；`recommendation_view.py` targeted mypy 0 issues、兩個 changed Python 檔 compile 通過。Workbench route 為 84P，Update QA 為 25P／4S；這些是各自 bounded 結果，不等於 native visible 驗收或最終整合 route。V2 UI source freeze／獨立 review與 root final relevant regression 收據尚待完成；真實候選、native post-fix操作及自然 scheduler仍未證。

## 2026-09-28 最終 relevant regression 收據附記

本附記更新前述 2026-09-27「source/PIT admission 最終測試數及 hash 尚未固定」與「root final relevant regression 收據尚待完成」的當時狀態；其歷史記錄及此前失敗／中斷收據均保留，不回填成成功。Root 最終 route 收據為 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T061833_712310Z/run_receipt.json)，SHA-256 `3a830dd73a2a8a88903c42211149fb4f1a298b9aeea9e4e606bfdf43fe1aee62`，狀態 `FINISHED`、`overall_candidate_pass=true`。使用 runner SHA-256 `38dde5ca0e7a99d81501516d81d70893aa905550f576769cd3d30cd13c52db6b` 與 route manifest SHA-256 `9d8555aac521a6d42090b6f02f477933759f829d927e2ecbf98deb98c4b23fc4`。

302 個唯一測試檔由 298 個 repo-short-TEMP 檔與 4 個 OS-TEMP 檔組成，兩組互斥且完整涵蓋 manifest；repo 組 3,141 passed／9 skipped／36 warnings，OS-TEMP 組 77 passed，合計 **3,218 passed／9 skipped／36 warnings**，兩個 pytest 分區均 exit 0。Workbench 為 84 passed；Update QA 為 25 passed／0 failed／4 skipped；mypy 737 source files 無問題；332 個 compile 路徑全數通過；`git diff --check` exit 0。Route scope hashes、HEAD `e5d75f7cbd3312dac391f52b5c2206d0c745bbc4`、git status 前後一致，未追蹤 Python whitespace scan 為 clean。可由收據核對各命令與隔離路徑。

此結果只接受本收據鎖定版本的 relevant regression 與列出的 mandatory checks，不表示 WP0–WP5 全部產品條件完成。路由採隔離測試根，沒有讀寫正式資料、排程註冊、模型 promotion 或 global pointer 更新；自動化測試亦不等於可見 native post-fix UI 或自然 scheduler 驗收。個人模型預設仍是 `rule_only`，兩個 `legacy_unproven` 候選仍不可啟用，仍無真實合格 PIT candidate；自然成熟 outcome 尚未由自然 daily 流程證明。StageC v2 的 active-only close-to-close 事後標籤、非 execution PnL、估算成本及 pending／unknown 限制維持原判讀。先前失敗或環境受限的 attempts 不刪除、不以本次結果改寫其當時 verdict。

## 2026-09-28 最終 relevant regression v2 收據

本次在四個檔案只移除多餘的 EOF 空白行後，root 重新完成同一個 302-path route。新的 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T064551_034316Z/run_receipt.json) SHA-256 為 `0ae3ec09a5f2a61c57bd28bc395bd2b3da4979146c7d00add348e396b791888b`，`overall_candidate_pass=true`；runner SHA-256 為 `80865005e59b2a02ff13371e7f1395bca5665bc31bb2f7118b9bcd20392b5a53`，manifest SHA-256 為 `52db796ab1a72e1972df0d47f277f28e5eef31a031293a7c333d9e71175cc8b0`。前一版收據保留作歷史，不由本次結果改寫。

302 個測試分為互斥且完整的 298 個 repo-short-TEMP 與 4 個 OS-TEMP 測試：repo 組 3,141 passed／9 skipped／36 warnings，OS-TEMP 組 77 passed，合計 3,218 passed／9 skipped／36 warnings。Workbench 84 passed；Update QA 25 passed／0 failed／4 skipped；mypy 737 個 source files 無問題；332 個 compile paths 與 `git diff --check` 均 exit 0。HEAD、git status、scope hashes 均保持不變。

此收據只支持 EOF 清理後的精確提交候選版本及其列明的隔離回歸，不代表產品整體完成；native post-fix UI、真實合格個人模型、正式資料與自然 scheduler 仍未驗。既有 skipped、環境限制與失敗收據保留原狀。

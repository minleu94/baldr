# 個人 Current-observed H20 每日入口：受驗保存與自然接線

日期：2026-10-06。固定 base：`f15ce80425e4bba2e12446da00547a7cc4618679`。

## 目前交付

中央已明示授予四檔擴鎖；原三檔加四檔共七檔由本 lane 排他持有。已實作每日 CLI、原 H20 prediction create-only 保存／public reader、原 no-model capture／natural outcome 的 exact join／public reader。App adapters 只接注入 ports，沒有新增 App→ML 匯入；原 ML／provider／guard／main／config／Task／Manual 均未修改。UI／產品 consumer、正式私人 root／policy、原 Task 接線及測試清冊由中央持有，尚未宣稱啟用完成。

**真模型已保存十筆，成熟自然樣本仍為 0。** 並非 synthetic-only 終點；但也不是自然效果或正式日常 Task 驗收。新程序以原 source／contract ports 重讀十筆、禁止推論的重試全部 idempotent，原預測 bytes／mtime 不變。

真 aware clock 已跨臺北午夜：本輪 decision 是 **2026-10-07**，cycle source 是 **2026-10-06**，feature-as-of 是 **2026-10-05**。三者分域保存，不回填 10/06 decision、不自稱 10/07 最新行情、不把 10/06 no-model entry 轉成 10/07 樣本。未提供相符的 entry capture／20-session receipt 時，public outcome view 明示 pending；錯日期／來源／cycle／symbol／feature values 必須拒絕。這批跨日來源不能取得舊 10/06 capture 的自然 credit；新同日 cycle 的日常接線仍須中央驗證。

| 股票 | 原 H20 預測毛報酬（bp） |
|---|---:|
| 1225 | 2204 |
| 1256 | 365 |
| 1465 | 1673 |
| 1477 | 2557 |
| 1560 | 2135 |
| 1714 | 1931 |
| 1721 | 2093 |
| 2382 | 684 |
| 3207 | 835 |
| 9935 | 1314 |

模型是可信原候選 `rec-cal-3f8b2c276ef316e28de3806d`，沿原 frozen fit／lineage；inference source 獨立沿原 completed current-stock snapshot。沒有 fit、live DB 替換訓練來源、canonical RecommendationResult ID、交易或資格升格。原 holdout Brier 2730 bp 比 null 2500 bp 差 230 bp；這是既有機率頭的效果揭露，不能當 H20 毛報酬自然驗證。After-cost 缺件仍保留；低績效不作個人研究保存 gate。

## 實際 CLI／API 與中央最小接線

CLI 五個 required 參數：`--request-json`、`--request-sha256`、`--receipt-root`、`--gross-fit-receipt`、`--gross-fit-receipt-sha256`。全部路徑須絕對、root 現存且在 package／FA_Data／原 fit／snapshot 範圍之外。沒有自動選「最新」、沒有自建 policy／Task。

request schema 為 `personal-current-observed-h20-daily-request.v1`，欄位為 `data_root`、`source_pins`、排序且不重複的 exact `symbols`（1–50）、`history_start_date`、`expected_feature_as_of_date`；optional `natural_outcome` 明列 `input_capture_path`／`input_capture_sha256`／`outcome_path`／`outcome_sha256`。`source_pins` 必須是原 completed terminal 同 run pins 加 `cycle_id`、`raw_run_id`、`cycle_source_date`、`cycle_terminal_path`／SHA；不得填 `observed_at`、`decision_date`、預測值或 result ID。CLI 使用真 UTC aware clock，臺北日期用於 request；source cycle 不可晚於觀測日，全部股票須等於 terminal cohort。`data_root` 核對 `TWStockConfig`，不鬆綁原 artifact guard。

公開 API：

- `run_personal_current_observed_h20_daily(*, request, receipt_root, gross_fit_receipt, expected_fit_receipt_sha256, cancelled=None)`，位於新 scheduled script。
- `capture_personal_current_observed_h20_prediction(*, root, source_binding, contract_binding, symbol, source_verifier, contract_verifier, predictor, cancelled=None)`。
- `read_personal_current_observed_h20_capture(path, *, root, source_verifier, contract_verifier, expected_sha256=None)`。
- `project_personal_current_observed_h20_outcome(*, prediction_path, prediction_sha256, root, source_verifier, contract_verifier, input_capture_path=None, input_capture_sha256=None, input_capture_verifier=None, outcome_path=None, outcome_sha256=None, outcome_verifier=None, persist=True)`。
- `read_personal_current_observed_h20_outcome(path, *, root, source_verifier, contract_verifier, input_capture_verifier, outcome_verifier, expected_sha256=None)` 是純讀回；重建驗證時 `persist=False`，不新建 join。
- scheduled composition 的 `personal_current_observed_h20_read_ports()` 回原 source／fit／input capture／outcome verifier ports，供中央注入 App readers。

中央最小接線為：原 raw Task **同 run terminal completed** 後組 exact request／raw pin，指定既有可信 fit receipt raw pin `sha256:f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1`、私人根，再呼叫 CLI。產品 consumer 從該 receipt 的原 path／SHA 呼叫 public reader，顯示 symbol、decision／source／feature 日期、原 predicted gross bp、candidate／contract／lineage 與 pending。若已有 canonical result，中央只能使用真正已保存 ID 作外部引用；本 store 不複製 canonical payload、不冒充 result ID。自然部分沿原 builder 產生相符 input／outcome，再以 exact pins 注入 adapter。

## 保存、重試與自然 identity

新 schema `personal-current-observed-h20-prediction.v1` 保存原 A02 `prediction_id`、完整 request／輸出、原 fit raw pin、contract／artifact／lineage、source pins／source fingerprint／feature row hash與真 capture clock。`sample_id` 綁 cycle、terminal、source pin logical hash、candidate、contract、fit pin、symbol、原 decision；模型 target 保持 20-session absolute close-to-close no-cost gross。所有 formal／PIT／promotion／production action flags 為 false。

原始檔 create-only、finite JSON、16 MiB 上限；拒絕 link／reparse／多 hardlink／來源根重疊，核讀取前後 fd／path／祖先 stat，atomic hardlink publication 後讀回。新檔名稱使用不含 decision 日期的 cycle/model/symbol 重試 key：即使隔日重試仍先讀原輸出，保留第一次 clock／prediction；不重算成新自然樣本。相容本輪先前完整 sample-id 檔名只新增原 path／raw pin 的 create-only 引用，不複製或修改原預測。cancel／failure 回傳已保存部分，下一輪仍沿原 identity。

自然 join 另 pin 原 no-model input capture、原 natural outcome receipt及原 prediction raw bytes；三個來源各由原 public ports 核實。必須同 cycle／snapshot／decision／symbol／feature values與原 row ID；取原 `stock_return_bp` 作已實現 gross，整數誤差為原預測減該原值。別列 return 不會移給 pending 股票。已成熟 join 的多份 evaluation receipts 不能當成多個獨立樣本，產品以 `sample_id` 管理原預測身分。原模型輸出的 false natural／formal flags 不被改寫，join 是受驗的個人研究結果，不是 global promotion evidence。

## 驗證證據與限制

raw 根：本 worktree 的 `output/qa/h20-current-daily/`，全部 excluded，不 stage。真預測私人 QA 根：`C:/Users/archi/AppData/Local/Temp/h20-private-current-observed-20261006`；它是本輪隔離接受根，不替中央決定正式私人 root。

- 真 daily receipt：`real-authorized-read.stdout.json`，completed、10 captures／10 pending，file SHA256 `e134f9ac100185678b46345ea220251d26b27a1e0177a2e4b03e9b2bd67b21b6`。
- 新程序：`fresh_real_readback.py` → `fresh-readback.stdout.json`，10 idempotent，predictor forbidden，原 bytes／mtime 不變，file SHA256 `ce9336c6baeae0fb129dda997cf2e35ccc0cc27dc8e616b264a63cbb52e509ad`。重試命名增量另由 `final-real-reference.stdout.json` 核一筆原真輸出；最新 focused／mypy／compile／quant 收據以交付 manifest 為準。
- 初次純 worktree loader 拒 approved-root 外的原 cycle；保留 `real-daily.*`。QA 直接載原主 checkout **同 bytes** public verifier，維持原受准 root，其餘 provider／service 沿固定 base；沒有 patch guard、retarget config或搬來源。
- sandbox 原 provider `data_version` guard 拒絕；`real-original-verifier.*`／`real-retry.*`／`real-source-trace.*` 保留。source.sqlite size `4054339584`、mtime `1791288882203027900` 前後不變。相同原 API／pins 經授權唯讀 `require_escalated` 成功；沒有 reviewer rejection、ACL 變更或來源重建。主 checkout 正常組合不需要 QA origin launcher。
- 最新 focused 為 **33 passed／1.36s**（`final.txt`／`final.xml`）；含跨午夜不重算、舊檔名原 pin 引用、部分取消／失敗後重試、錯來源／日期／symbol／資格與 pending 列不借別列結果。**3 source mypy、0 errors；6 Python compile exit0；quant precision／look-ahead exit0；ML dependency guard 682 sources／0 violations**。以上沒有 full-repo／UI credit。最後一筆真引用相容驗證 exit0，原 prediction bytes／mtime 不變，沒有模型推論。
- 不重全倉／UI suites；三個新 test 檔的 test inventory／Manual／shared state 更新由中央承接。IO 逐列重驗原大型 snapshot，這次十列約數分鐘，不宣稱性能優化或正式 Task 體感驗收。

回滾為對本 lane 提交執行 `git revert <完整提交雜湊>`，只撤新增入口／adapters／tests／QA 文件；**不刪已保存真預測、原來源與自然收據**。剩餘由中央完成產品 consumer／正式私人設定／原 Task action 接線；跨日 source／entry 差異不能以放寬原 same-source join 解除。

## 初次 blocked-scope 交接（實作前歷史，以下不是目前狀態）

狀態：**blocked_scope；未實作每日入口，未新增自然樣本**。本收據不是 synthetic-only 驗收終點。使用者要求模型真正參與日常選股研究；自然成熟用來改善效果，不是等待模型個人使用的工程 gate。

## 排他範圍與回滾

原授權只新增 `scripts/scheduled/run_personal_current_observed_h20_daily.py`、`tests/test_personal_current_observed_h20_daily.py`、本文件。中央 `01a11020-88c2-7506-acc3-d51ecb674032` 保留 shared state、main、config、Task、Manual。本輪僅新增本文件；沒有為交付數量填入不可供自然結果消費的旁路 JSON。

回滾：`git revert <本文件提交完整雜湊>`。只撤銷本文件；不刪原始資料、既有預測、收據或 worktree。風險：失去此次擴鎖交接文字。

## 既有 public API 核實

| API／位置 | 實際契約 | 對本任務的限制 |
|---|---|---|
| `ml_module/recommendation_calibration_evidence.py:2549`，`verify_current_observed_input_capture` | 驗證 no-model v1/v2 input capture；capture ID、source binding、entry pin、aware capture clock、cost contract 都須通過 | `forbidden_fields` 明拒 `predictions`、`candidate_id`、`model_id`；不能把原 H20 輸出塞入 bootstrap capture |
| `ml_module/recommendation_natural_outcome_service.py:580`，`RecommendationNaturalOutcomeService.build_current_observed_outcomes_for_capture` | 接受上述 immutable no-model input capture 與明示後續 current-restated source；建立 current-observed outcome | 不讀 H20 原始預測，不驗其 candidate／fit／contract／prediction 身分；直接呼叫不等於模型自然效果 join 完成 |
| `app_module/recommendation/personal_prediction_capture.py:106`，`capture_personal_saved_result` | 先 `queries.get(result_id)`，核 canonical/index/receipt，create-only 封存已交付結果 | 今日 QA raw snapshot 推論沒有 canonical RecommendationResult；不得自造 result ID |
| 同檔 `read_personal_prediction_capture` | 每次重讀原 canonical execution/receipt 並比較 stable capture identity | 不能以自建 JSON 或今日新政策代替原保存結果 |

唯讀成功重現來源為 repo 主 checkout 的 `output/qa/baldr_real_model_intake_20261006/observe_current_verified_gross.py`。它沿原 `prepare_contract`、`load_current_observed_context_from_pinned_snapshot`、`MLHistoricalSnapshotProvider.load_current_observed`、`HistoricalFeatureBuilder.compute_current_observed`、`PersonalH20GrossInference.predict`，但其 scope 已明示 `QA capture only, no canonical recommendation capture`。本輪閱讀此檔，**沒有重跑十檔真推論**，不把先前成功算成本輪驗收。

## 精確擴鎖要求

保留 ML／provider／guard 原檔全唯讀，請新增下列正式 App adapters 及測試的排他鎖：

1. `app_module/recommendation/personal_current_observed_h20_capture.py`：typed H20 原始 prediction create-only writer／public reader；以原 no-model capture 原始 bytes pin 作來源身分，獨立模型研究 capture，不冒充 canonical RecommendationResult。
2. `tests/test_personal_current_observed_h20_capture.py`：原 pin 負例、同 identity 重試不再推論、partial/cancel、fresh process readback、檔案 custody／衝突。
3. `app_module/recommendation/personal_current_observed_h20_outcome.py`：沿原 no-model capture/outcome verifier 的 App join adapter；核已保存 H20 預測與自然價格結果一對一身分，保持 research-only 與成熟 pending。
4. `tests/test_personal_current_observed_h20_outcome.py`：wrong capture/cycle/source/model/symbol、未成熟／部分成熟、重讀、自然 outcome exact join 負例。

上述新增檔在原三檔之外，**尚未授權，未建立**。不要求改動 `recommendation_calibration_evidence.py` 或 `recommendation_natural_outcome_service.py` 的 no-model gate；舊 bootstrap 與舊個人 canonical capture 語義保持。若中央已有另一受控保存／自然 join 接口，可用其明確 API 取代新增 adapter，但需能獨立 fresh-process 消費，不接受只由每日 script 自行讀取的 JSON。

## Frozen CLI／API 提案與中央接線

以下為待擴鎖後實作的介面提案，**目前不可執行**：

```text
scripts/scheduled/run_personal_current_observed_h20_daily.py
  --request-json <絕對路徑>
  --request-sha256 <sha256:raw-request-digest>
  --gross-fit-receipt <原可信fit收據絕對路徑>
  --gross-fit-receipt-sha256 <獨立核准raw-fit-digest>
  --receipt-root <隔離個人研究保存根>
```

`run_personal_current_observed_h20_daily(*, request, receipt_root, gross_fit_receipt, expected_fit_receipt_sha256, cancelled=None)` 為每日 composition。`read_personal_current_observed_h20_capture(path, *, expected_sha256)` 為正式 fresh-process consumer。自然 adapter 應接明示 prediction capture path/raw pin 與原 outcome path/raw pin，不掃描「最新」，不接受 caller 自填 return／label。

request 明示 `cycle_id`、`cycle_terminal_path`、`cycle_terminal_sha256`、原 source envelope/snapshot pins、原 no-model input capture path/raw SHA、exact symbols、`history_start_date`、`expected_feature_as_of_date`。CLI 不接受 `observed_at` 的回填；使用執行當下 `datetime.now(timezone.utc)`，decision day 取 Asia/Taipei。feature-as-of、來源發布、local observation、真正 prediction observation 必須分開，不能把當下看到的 restated 資料聲稱當年已可得。

中央在原 current-stock raw terminal `completed` 後傳 exact pins；原 fit receipt `f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1` 指向可信候選 `rec-cal-3f8b2c276ef316e28de3806d`。沿原 frozen training source/lineage 建 contract，今日 inference source 獨立驗證；不把 live DB 替換原 V2 frozen fit source。

保存 join identity 至少包含原 input `capture_id`／raw SHA、cycle／terminal SHA、candidate／contract hash／fit receipt raw SHA、symbol／feature row hash／inference source fingerprint、原 H20 request／prediction bytes hash。重試先讀同 source/candidate/day/symbol 身分的已保存列，保留原 clock 與預測 bytes；cancel／failure 已保存部分不得重算或另造自然樣本。必要的輸入／預測／結果保存應有正式 reader 可供 App／自然 adapter 使用。

## 驗證與剩餘

本輪只做 API／原始碼唯讀核實與 graphify query。graph query 命中既有 Recommendation persistence、ResultArtifactStore、snapshot provider，但其圖不作新 H20 保存／自然 join 的證明；上述 blocker 以固定 base 原始碼為準。

未新增 Python，因此 focused pytest／JUnit、targeted mypy、py_compile／quant 變更檢查 **not_run**；不得報為通過。不重全倉測試。待中央擴鎖後才實作並產出 focused raw/JUnit、targeted mypy／compile／quant、完整 commit/blobs；自然成熟保持真實 pending，不以 synthetic 驗證替代每日真模型使用終點。

Git worktree 初次因 sandbox Git ref 寫入權限失敗；相同 authorized `git worktree add` 經 `require_escalated` 成功。沒有 reviewer rejection，沒有修改 ACL，沒有 push、Task 註冊、真資料搬移、交易或清理。

## 已授權正式私人根的真 daily effect

revision1 enabled=true 已發布到 D:/Min/Python/Project/FA_Data/personal/recommendation_h20/activation.json；revision1原bytes歷史備份保留。使用原模型rec-cal-3f8b2c276ef316e28de3806d與原completed raw-cycle，真UTC clock保存10股／10pending，中央公開全scope驗核後發布產品指標。actual_private_h20_effect.json raw SHA256 b676835a7770a48bebe3cfc6ddc781a5635d73ccdf60827f830c23acb1440048；effective_model_run=true，manifest raw pin sha256:a2cad4b3ac8ff978f52ecb28d006da37573cd1313efcee28bfc1d5d632661e76。decision10/07/source10/06/features10/05，不借10/06entry回填，不取得自然credit。

本次是同daily公開ingress的直接驗核，沒有啟動Task或fit；原Task principal/action/trigger/settings和before receipt逐欄相等，state Ready／trigger enabled，既有05:45 action會採已存在私人配置。下次實際scheduled執行與新同日cycle exact natural join仍須觀察，不把本次直接调用當Task已跑。原guard每次重驗4GB frozen source，效能有成本，UI用背景reader，未宣稱全部性能例外解除。

immutable implementation19afc33dfcff5fa6dcc4c1c7bdb962ce32d612e7；固定commit六檔60passed/8.66s，Workbench85，validator25/0/4，fullrootsmypy845零錯；額外兩CLI mypy零錯／11changedPython compile／quant成功，MLboundary684/0。inventory7與bridge9是16個治理案例，與focused/UI分scope不累計成全倉通過。此前stage/UX有限closed與未知資格不變。

產品新程序真readback已成功：actual_product_readback.json raw SHA256 23cc1ff12570ad267d798388c82107cf07d6f2fb5ee5bbcb433e8d4d489c37da。predictor factory明確禁止，原 public reader核1225 candidate／source／raw pins，實際readonly report as_of10/07，原 view label顯示+22.04%（2204bp）及三日期，私人JSON全集bytes與mtime不變。完整state目前15JSON（10prediction、1manifest、config/history與reference/history），成熟outcome尚0；10pending是run receipt及原capture待核狀態，沒有偽造10個自然outcome檔。

原offscreen Qt缺字型，PNG文字方框，不稱視覺驗收。另QA-only msjh.ttc bytes注入重用已驗readback文字檢查layout，不修改product或字型系統設定；仍不是Native／真人證據。剩下新同日raw-cycle／entry exactjoin與自然二十session成熟、後續scheduled真正執行觀察；這些不否定本次模型實際啟用／daily入口／產品同值成功。parent full-universe BB v3 composition仍依另外exact ownership續作，沒有把有限上軌family或整體roadmap改done。

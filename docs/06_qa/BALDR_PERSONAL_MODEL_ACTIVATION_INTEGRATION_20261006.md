# 個人 H20 模型中央接線與真候選核對（2026-10-06）

> **階段時序提示（2026-10-11）：** 下一段「尚未完成每日目前來源啟用」是 10/06 早期階段摘要；本文後段記錄的 10/07 revision 1 已有 `effective_model_run=true` 的實際個人效果收據。該結果只證明有界個人切片，Task 尚未實際執行、自然結果尚未成熟；不代表整體產品完成或取得交易、正式 PIT／global promotion 資格。現況回到 [Snapshot](../00_core/PROJECT_SNAPSHOT.md) 與 [QA 導覽](README.md)。

本次接受原 H20 毛報酬 head 的精確讀取工程，尚未完成每日目前來源啟用。使用者已明示接受有限 BBANDS30 上軌比較與 H20 gross、希望真模型在每日個人研究中實際使用；自然績效成熟度不再作個人使用的工程門檻。原交易、正式 PIT、global promotion 等資格不因此提升。

## Coverage

| 文件 | 優先級 | 範圍 |
|---|---|---|
| 完整 Manual | Must | policy 路徑、preview、參數、結果、安全與排錯 |
| Snapshot | Must | 接受範圍與尚存 daily source 阻塞 |
| 現行 architecture | Must | 原 lineage reader、same-bytes loader、cutoff 分域 |
| Index | Must | 本文件、A02、activation preflight 入口 |
| 唯一原 product experience plan | Must | append-only；保留原文與 Stage／UX／例外 |
| Product／6M／version roadmap | 不修改 | 沒有新增 maturity gate 或競爭路線 |

## 可核交付

A02 原 `7b5f055d506f0f95777edd4dfaae7cd381f3666d` 採入中央 `25530d9d`；只有四新增檔。沿用 worker 固定 commit 64 focused 與 16 adjacent 收據，不累加成完整 App suite。

中央以可信原 fit 收據 `output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json`，raw SHA256 `f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1`，核候選 `rec-cal-3f8b2c276ef316e28de3806d`。三個 scheduled legacy 候選仍缺 lineage，未修改或啟用。

`scripts/qa_prepare_personal_h20_gross_contract.py` 要求 caller 明示原 fit 收據與可信 raw SHA；讀回原 candidate／manifest／lineage 精確 bytes，注入原 `read_recommendation_training_lineage`，輸出 A02 typed contract 與原 blockers。它不讀 model artifact、不 deserialize、不 fit、不保存 policy 或修改 Task。raw hash 與 canonical manifest hash 分別保存，不混用。

中央真候選核對發現兩個 synthetic 未覆蓋缺口，已補：模型 `training_as_of=2026-05-25` 是原 final fold 截點；merged lineage cutoff `2026-06-26` 另以 additive `lineage_training_as_of` 精確綁定，candidate.training_cutoff 同核；晚於決策日拒絕。原 lineage canonical JSON 使用 `ensure_ascii=False`，中文內容不能改成 ASCII escapes 重算 hash。

實際 same-bytes 原 artifact `sha256:8890df64cb66d73af1b34755053d271dad4d38450bdb6e51578681e8684d7310` 載入後，對原 2026-09-28 保存特徵請求重播：2408=`1613 bp`、2454=`1963 bp`、3037=`1086 bp`，逐項等於原 ranking_score_bp。模型／manifest／candidate／lineage／fit 與請求收據 bytes、mtime、size 前後一致。不是新自然預測、不寫回原 capture，不冒稱目前正式 DB 已每日接通。

raw：`output/qa/baldr_real_model_intake_20261006/verified_existing_h20_saved_replay_final.json`；初次 cutoff 與 Unicode 拒絕證據保留。原候選 holdout Brier2730、null2500、落後230bp，after-cost 缺件；這些須揭露，不能用來無限延後已准個人使用。

中央 final A02 68 passed／4.45s（含四個新 cutoff／Unicode cases）；rebuild 工具 4 passed／0.97s；四 sources targeted mypy 0 error。pytest cache 寫入 warning 保留。對 main/config 的既有 mandatory 收據沿用：Workbench85 passed、validator25 pass／4 skip／0 fail、full roots841 sources0 error；此輪 A02 數量不代替將來 A01/A03 union。

## 操作與排錯

`PERSONAL_MODEL_POLICY_PATH` 或 TWStockConfig.personal_model_policy_path 明示絕對路徑；MainWindow explicit policy_config_path 優先，其次 config，最後原 AppConfigLocation 預設。配置欄位不自建 policy、不等於啟用；relative path 在來源 I/O 前拒絕。不要把 FA_Data 或 market DB 當私人 policy 目錄。

```powershell
.\.venv\Scripts\python.exe scripts/qa_prepare_personal_h20_gross_contract.py --fit-receipt <原fit收據絕對路徑> --fit-receipt-sha256 <獨立核准的原rawSHA256>
```

`scripts/scheduled/rebuild_personal_calibration_candidate.py --help` 列出來源、歷史期間、explicit symbols、max decision dates、cost bp、shared heavy-chain lock 與新 output 等必要參數；default preview 只讀，不訓練、不 lock／mkdir／發布。execute 工程保留原 capacity／shared lock／source guard；scratch 僅新 output/temporary，建立失敗也釋放 reservation。這次沒有 execute。

實際正式來源 replay preview 得0樣本：原 revision guard 自2014-01-02拒 historical PIT，diagnostics 原文保留。不得刪 marker、放寬 guard、補造 available-at 或 PIT；也不得把原9月24日 frozen snapshot 當每日目前行情。

可信候選對原 frozen source 的 source-time proposal=`proposal_ready`；對當前正式 DB 則 `training_source_time_training_rows_unbound`。剩下必須完成目前 current-restated observation 與 frozen training source 的明示分域，以及 A03 CLI 的真 lineage reader／contract 接線、自然結果與中央 union。新 gross trainer不是前置需求。

可逆回退：先撤新 policy path override 使用原路徑；原 rule-only／policy CAS 回退契約不變。不要刪原 receipt 假裝未曾推論或重新標記舊模型資格。本次不變更 Task、ACL、交易、真 DB、migration，也未 push／main merge。


## 2026-10-06 中央 A01/A03 與今日真模型讀回

A01 已採入 `32dea52c`，A03 已採入 `ca762901`。中央補齊 v2/v3 個股 consumer 的 manifest 選版、BB opt-in fingerprint、exact manifest 再驗，以及多方法 consensus／capture 第三方法的完整共同分母；v2 原 pins 不變。單批 snapshot CLI 新增 `--include-bbands30-upper`，預設仍 v2；parent-universe 路徑尚未接 v3，明示拒絕該組合。保存容量、200GiB capture reserve、PIT／來源資格與 compression 未決均保留。

A03 CLI 新增成對 `--gross-fit-receipt`／`--gross-fit-receipt-sha256`，由原可信 receipt 重建 A02 contract、注入原 `read_recommendation_training_lineage`；request 必須明示相同 `gross_model_contract_hash`。不重訓、不載模型、不代造 canonical 結果。gross 保存 projection 區分 model final-fold 日期與 merged lineage cutoff，後者不得晚於決策日。worker fixture root 改成當前 repo/output/qa，不再在主 checkout 誤寫 C:/output。

今日真來源推論已實測：原 public current-observed context verifier／provider／feature builder →同 bytes 的既有 H20 return head；10 檔全部 available。decision_date=2026-10-06，observed_at=2026-10-06T15:35:41.658492+00:00，特徵截至 2026-10-05。收據 `output/qa/baldr_real_model_intake_20261006/current_verified_h20_observation_final.json` raw SHA256 `3abb94591d90256afe83e62d5923aeffb9ddd1bc53e3f7a54f6412bcb5c1a46b`。模型 artifact `sha256:8890df64cb66d73af1b34755053d271dad4d38450bdb6e51578681e8684d7310`；completed cycle terminal `sha256:7e552bfeed88527d7bef66c233a5b90d5dae39cccd937dd100730302318c2819`。

十檔 gross bp：1225=2204、1256=365、1465=1673、1477=2557、1560=2135、1714=1931、1721=2093、2382=684、3207=835、9935=1314。這是新觀測的真模型研究預測，已保存 QA receipt；尚不是 canonical RecommendationResult／personal capture，不冒稱每日正式 producer 已啟用。原來源 availability、PIT、訓練與自然成熟資格未提升。原 holdout Brier2730 比 null2500 差230bp，保留揭露；不把自然成熟或績效變成人工工程啟用 gate。

Windows sandbox 對 snapshot SHM 讀取造成 data_version 每次遞增；同一唯讀探針在允許環境保持不變，原 guard／ACL 未改。相鄰 A03 原 no-follow ancestor handles 同理，紅收據保留，隔離合成同版允許重驗 64 passed/1 skip。A01 composition 133 passed/1 skip；第三方法 scope 偽造 delta2 passed；Workbench85、validator25/4skip、full mypy841零錯誤。這些數量不相加宣稱全 App。

剩餘精確 composition：把已成功的 current-observed public 路徑接成可重複每日保存與 outcome 的可信 caller，不能以舊 frozen training DB 偽裝今日來源；原 V2 canonical source-time policy 與目前 daily live DB 尚不相容，不移除 source marker／改時鐘來通過。日常 Task 真啟用、Private root/帳戶正式選擇未執行。parent-universe v3、compression、原 Stage/UX、七有限 closed／性能例外均未擅自升級。


## 2026-10-06 實際 Task／啟用配置準備（未啟用）

唯讀 Task 查核已確認 archi、Interactive、Limited、Pacific Standard Time；raw-pit-refresh-daily 為05:05、snapshot-daily05:10、calibration-learning-daily05:45，均原 repo 工作目錄／cmd action、IgnoreNew。原 calibration pipeline 有10500秒 current-observed 等候與 exact raw-run/terminal pin 接線，不應以05:10未完成來源直接推論。

PERSONAL_* roots/policy env 未配置，AppConfigLocation=C:/Users/archi/AppData/Local/TechnicalAnalysis/TechnicalAnalysis，只有cache。建議新 personal root 為該目錄下 personal_h20；這是唯一待使用者選定的實際保存位置，不需要新帳號／時刻／權限。配置與預測 root 同域，activation.json 不放FA_Data。此建議尚未執行。

新增 typed PersonalH20Activation、read_personal_h20_activation、publish_personal_h20_activation。預設 preview 不mkdir；明示 execute 才CAS寫下一revision。每I/O沿shared personal root／link／hardlink guard；原no-follow讀回、create-only history（revision+bodySHA）、atomic pointer及exact readback。失敗留下不可被當live配置的不可變history/staging，不清理來源。disabled是新revision，不刪模型／預測；回滾不依賴fit/artifact仍存在。預览與配置發佈均 effective_model_run=false，必須由產品consumer實際verified capture及Task閉環證明effect。

已核真候選的具體preview：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_personal_h20_activation.py --market-root D:/Min/Python/Project/FA_Data --personal-root D:/Min/Python/Project/FA_Data/personal/recommendation_h20 --scope-id personal.default --fit-receipt C:/Projects/PythonProjects/technical_analysis/output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json --fit-receipt-sha256 f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1 --expected-revision 0 --enable
```

經root與實際consumer/同-run每日接線審核後，完全相同命令加 --execute 才寫配置。不是註冊或更新Task；原Task如採opt-in同-run hook，principal/trigger/action/settings不必改。真啟用不可用配置發佈成功代替閉環驗證。

具體回滾（假設已發佈revision1）：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_personal_h20_activation.py --market-root D:/Min/Python/Project/FA_Data --personal-root D:/Min/Python/Project/FA_Data/personal/recommendation_h20 --scope-id personal.default --expected-revision 1 --disable --execute
```

若revision已前進，先唯讀readback再明示expected-revision；不自猜、不覆蓋。publication失敗留下同revision不同body的history不阻擋安全disabled發佈，舊pointer保持原真值。配置不授global promotion／交易／after-cost/PIT；較差holdout2730 vs null2500與after-cost unproven繼續揭露，不作個人model啟用gate。

今日原 public no-model capture已唯讀驗核：output/qa/baldr_real_model_intake_20261006/actual_today_input_capture_verified.json；來源10檔cohort與先前QA十檔不同，不混寫。Taipei 10/07後，10/06保存可讀回/replay/自然outcome，不能宣稱今日新觀測。Task/core reader接線仍待leaf exactAPI與中央composition，root尚未寫入，Task/ACL/憑證未動。

## 中央 same-run Task hook（尚未實際啟用）

中央接點固定既有05:45 calibration-learning Task；原 principal archi／Interactive／Limited、trigger、cmd action、工作目錄與settings不變。cmd只在配置檔已存在時傳optional --personal-h20-activation-config；LOCALAPPDATA預設路徑與上節preview一致，可明示env覆寫。未配置沿原行為；disabled在fit/source/model前退出。cmd未實際執行，不執行排程／網路／真訓練。

run_daily_recommendation_learning_pipeline._learning_child_arguments 僅explicit flag多兩argument，其餘原exact raw-cycle pins不變。main在原no-model input entry persist與自然研究之前呼run_personal_h20_for_current_cycle；原global/formal root conflict仍blocked，收據另有personal_h20_daily，不以個人研究成功改全域資格。對缺來源、wrong raw-run/root/hash/contract或runner錯誤明示pending/blocked，不吞成成功。request用leaf凍結六欄及11原publiccontext pins，不接受caller observed_at、prediction或result_id；entry pending不是模型前置，outcome另明示原保存pins後續join。

測試為合成port，沒有真model/fit/Task：tests/test_personal_h20_daily_hook.py＋原tests/test_current_observed_learning_capture.py同版68 passed/3.55s，raw h20_hook_final.log/XML；同WindowsTemp範圍允許no-follow祖先唯讀handle重驗，guard與ACL沒改。首輪7pass/2fail保留h20_hook.log/XML（fixture漏symbols已修；另一fail為sandbox C:/Users/archi祖先handle）。3scripts targeted mypy --explicit-package-bases --follow-imports=silent 0 errors；5Python compile與quant guard成功。新test分類service-oracle-recommendation，1289inventory，direct仍12；原UI mandatory f15收據沿用，本包未改UI。

剩餘是leaf公開store/readback/schema最終固定、中央productconsumer、使用者實際private root選擇與閉環effect核驗；目前沒有實際config/Task啟用，不能用此68或configuration_published冒稱daily complete。新root仍AppConfigLocation/personal_h20最小建議，原holdout較差230bp/after-cost未證明保持揭露。

## 中央 current-observed 產品閉環（2026-10-07 Taipei）

前段 LOCALAPPDATA 候選與尚待選根是歷史階段；最新明示選根為 FA_Data/personal/recommendation_h20，cmd／Qt 預設皆同步此精確根。不再次選位置，不搬移原資料。採入 leaf a6de8c6→07d32b5 為中央34a9b343→f00efc96；中央只允此模型子樹，其他市場／私人領域仍拒。新 public prediction/outcome readers 保留原 verifier，中央 daily manifest 僅保存原 capture pins，產品指標不複製預測。

同版驗證：六檔 focused 59 passed；新增 completed hook 回歸10 passed（與前59重疊9，合計60不同案例）。Workbook85 passed；update validator25通過/0失敗/4跳過；八根 mypy845 source files零錯誤。test inventory1293、recommendation oracle193、UI candidate98、direct12；新三leaf tests是Temp保存／注入ports的 service oracle，不是正式來源或Task驗證。

實際配置已CAS发布revision1 enabled=true，activation immutable history留原bytes；配置不等於日常推論完成。真 effect / source stat / public readback 結果另列本節後續原收據，失敗如實 blocked，不能由配置成功推定自然 credit。回滾命令沿本文件 `--expected-revision 1 --disable --execute`，不需要fit可讀。沒有改Task／ACL／憑證，沒有fit／市場DBwrite／交易。

## 已授權正式私人根的真 daily effect

revision1 enabled=true 已發布到 D:/Min/Python/Project/FA_Data/personal/recommendation_h20/activation.json；revision1原bytes歷史備份保留。使用原模型rec-cal-3f8b2c276ef316e28de3806d與原completed raw-cycle，真UTC clock保存10股／10pending，中央公開全scope驗核後發布產品指標。actual_private_h20_effect.json raw SHA256 b676835a7770a48bebe3cfc6ddc781a5635d73ccdf60827f830c23acb1440048；effective_model_run=true，manifest raw pin sha256:a2cad4b3ac8ff978f52ecb28d006da37573cd1313efcee28bfc1d5d632661e76。decision10/07/source10/06/features10/05，不借10/06entry回填，不取得自然credit。

本次是同daily公開ingress的直接驗核，沒有啟動Task或fit；原Task principal/action/trigger/settings和before receipt逐欄相等，state Ready／trigger enabled，既有05:45 action會採已存在私人配置。下次實際scheduled執行與新同日cycle exact natural join仍須觀察，不把本次直接调用當Task已跑。原guard每次重驗4GB frozen source，效能有成本，UI用背景reader，未宣稱全部性能例外解除。

immutable implementation19afc33dfcff5fa6dcc4c1c7bdb962ce32d612e7；固定commit六檔60passed/8.66s，Workbench85，validator25/0/4，fullrootsmypy845零錯；額外兩CLI mypy零錯／11changedPython compile／quant成功，MLboundary684/0。inventory7與bridge9是16個治理案例，與focused/UI分scope不累計成全倉通過。此前stage/UX有限closed與未知資格不變。

產品新程序真readback已成功：actual_product_readback.json raw SHA256 23cc1ff12570ad267d798388c82107cf07d6f2fb5ee5bbcb433e8d4d489c37da。predictor factory明確禁止，原 public reader核1225 candidate／source／raw pins，實際readonly report as_of10/07，原 view label顯示+22.04%（2204bp）及三日期，私人JSON全集bytes與mtime不變。完整state目前15JSON（10prediction、1manifest、config/history與reference/history），成熟outcome尚0；10pending是run receipt及原capture待核狀態，沒有偽造10個自然outcome檔。

原offscreen Qt缺字型，PNG文字方框，不稱視覺驗收。另QA-only msjh.ttc bytes注入重用已驗readback文字檢查layout，不修改product或字型系統設定；仍不是Native／真人證據。剩下新同日raw-cycle／entry exactjoin與自然二十session成熟、後續scheduled真正執行觀察；這些不否定本次模型實際啟用／daily入口／產品同值成功。parent full-universe BB v3 composition仍依另外exact ownership續作，沒有把有限上軌family或整體roadmap改done。

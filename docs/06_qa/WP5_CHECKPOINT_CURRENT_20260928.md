# WP5 整合檢查點：目前可核證狀態（2026-09-28）

本文件是 [`WP5_INTEGRATION_CHECKLIST_20260928.md`](WP5_INTEGRATION_CHECKLIST_20260928.md) 的新檢查點，不覆寫其中的歷史結論。本次讀取的實際 HEAD 為 `29ff35b4a17fa3fc270aef6168ab70eaf48eeb1b`；原 checklist 所標 HEAD 為 `2a85bc92019798668ef12f50ef87fb587d0dc58c`，不等於目前 HEAD。工作樹並非乾淨：Bank wrapper、RecommendationView/相關 Qt tests、recommendation service/calibration、Manual 與多份 QA 報告有未提交差異；檢查時沒有 staged diff。因此下列結果是按各收據自己的 source/input pin 分帳，不是對目前整棵 dirty worktree 的完整回歸聲明。

一般 MainWindow 來源綁定的 UI P1 三檔已按本次整合路由固定 hash 並通過相鄰回歸；之後 m11 也完成 scoped Qt widget journey，Boundary review 無 P0/P1。m11 證據與限制列於本文末尾附記；它不證 OS 前景畫面或真人操作，也不代表完整 WP5 通過。

## 可核對收據

下列檔案存在，並已在本次 checkpoint 更新前以 SHA-256 讀回核對：

| 範圍 | 收據／報告 | SHA-256 | 能證明的範圍 |
|---|---|---|---|
| WP1 wrapper／terminal contract | [`final_revalidation_receipt.json`](../../output/qa/personal_daily_product_20260928/wp1_child_terminal_contract_01/final_revalidation_receipt.json) | `b29e7d2b1e345ddb545474aab243e48e7c418d9fd3f7ce2dc37eb19237ef31b7` | bounded child stdout／receipt identity、終態、retry 與測試；不是正常日真 child。 |
| WP1 terminal reuse/fingerprint follow-up | [`receipt.json`](../../output/qa/personal_daily_product_20260928/wp1_terminal_reuse_fingerprint_followup_01/receipt.json) | `d236c88ef03d3ac936396fd81ece5c48bc53fd70ea87f790454a861132965244` | receipt bounded readback、fingerprint 及 38P/4S 隔離路由。 |
| 9/28 closed-day dry-run | [`receipt.json`](../../output/qa/personal_daily_product_20260928/wp1_child_terminal_contract_01/closed_day_dryrun_01/receipt.json) | `1b8a7298c9686ba268dda4fb7fa748882498c89e8fd9c878d55655b5fd7b715f` | 官方日曆閉市、dry-run exit 0、child 未執行。 |
| WP2 current-only provider | [`final_receipt.json`](../../output/qa/personal_daily_product_20261006/industry_index_current_provenance_20260928/final_receipt.json) | `bdfcea454d3fbbbb2b743fc75aecc7660b67f1db581ba16b3115173985b072d5` | SQLite-first/CSV fallback 列身份，不是上游 source-time/PIT。 |
| WP2 sealed event follow-up | [`followup_receipt.json`](../../output/qa/personal_daily_product_20261006/wp2_nested_observation_echo_20260928/followup_receipt.json) | `1eb71993bc0b74849d9a0962f0ab993bd7b7f4cbbd3e659c01e6418b99ee477a` | 新 nested observation 欄位的事件封存／讀回負控；不證官方來源時間。 |
| WP3 Qt test log | [`wp3_modules.log`](../../output/qa/personal_daily_product_20261006/wp2_ui_industry_observation_20260928/closeout_01/wp3_modules.log) | `cc84c4d0c2cee5bfe5d52d05da75a9d7c592169681477eb3247ca947921feb5e` | log 內所列的既有 offscreen 模組測試結果；不是目前未凍結的 MainWindow source。 |
| WP4 fail-closed follow-up | [`followup_receipt.json`](../../output/qa/personal_daily_product_20261006/wp4_fail_closed_negative_validation_20260928/fallback_row_assertion_followup_20260928/followup_receipt.json) | `6f8fab317d891292c3d952f46cc9c1d65a0e20af693010ee0e36903d85546b55` | fixture full-stack fallback row 精確斷言；不等於自然來源／效果驗收。 |
| m10 Qt widget journey | [`personal_model_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_acceptance.json) | `74bd1156e64065fa0bad01808c64f34f254aa6971e87aa4802653b71b3c60c65` | m10 隔離 run 的啟用、canonical readback、capture、restart、disable、rollback。 |
| m10 Stage C | [`3c78725f…json`](../../output/qa/stagec_m10_assessments/s10_20260928T151528958Z/personal_natural_outcomes/runs/3c78725f8033b25f35ae21df777fc219bb20861f0bd8af2e55dbc12c140b17e4.json) | `f6184b1d66c25c7ee74f26930394e82ab2554e415dbe1ab2fbfaca4f72bc00da` | 同次 capture 為 19 pending、0 matured、無 outcome artifact、未發布。 |
| m11 MainWindow Qt widget journey | [`personal_model_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m11/receipts/personal_model_acceptance.json) | `dd9f976b41d589def2b13e26d50303882632725510a19b8ca1346cd17423fcf4` | m11 真 MainWindow 控件 journey：推薦 19/19 active 6000 bp、canonical save/readback、capture、restart、disable、fresh-proof rollback，最後 rule-only revision 4；不是 OS screenshot。 |
| m11 Stage C | [`6fbe8be5…json`](../../output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json) | `2355562e24d6e9e3398810835e43ac315ce84a61ae89bb55b6652abbae4dbdea` | 同次 capture 為 19 pending、0 matured、0 published，無 outcome artifact、global evidence 或 promotion credit。 |

報告來源：[`WP1 重驗`](WP1_DAILY_CHAIN_REVALIDATION_20260928.md)（SHA-256 `ccea11ada3fb17cf8ada70b14f2de078e468a69b1d2baaaaf93abe0fece8db3e`）、[`WP1 rehearsal`](WP1_REAL_CHILD_REHEARSAL_20260928.md)（`14c3a5401dadab2c8b62ddf52647ffab7e9cafc55b1691d75daa47ed8d2d46a9`）、[`WP2 provenance`](WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md)（`46cf4499d9fd17628822a9d2561ab0e701de51734578a5ea7c54beb38c4e5151`）、[`WP2 UI observation`](WP2_INDUSTRY_INDEX_UI_OBSERVATION_20260928.md)（`266f16da91d0514e93bfc425605b6c63e76241dd9060127086b54b9ca54a6264`）、[`WP3 Watchlist QA`](WP3_WATCHLIST_QA_20260928.md)（`4a28f75f24770ec4852fdc6cd2689d83622a998da53976cf388cf73de6d16de0`）、[`WP4 fail-closed QA`](WP4_FAIL_CLOSED_VALIDATION_20260928.md)（`4211fb7ec8e1384cbb78bc15d2705fe24eaf7bf8c815f3d1bd305a26a9687625`）及 [`m10 報告`](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)（`3ccfef56e6ceffb8f6323d00e4785b9afae31a789c81b212974a9d2bc4119cee`）。

## 十個整合情境

| # | 情境 | 目前判定 | 證據與界線 |
|---:|---|---|---|
| 1 | 正常開市日：daily update → 同日推薦 snapshot → learning child → canonical result/readback → 同 run retry | **待驗** | WP1 wrapper、terminal receipt 與 fingerprint 的隔離測試通過；9/28 是閉市且 child `not_run`，9/24 pair 因 latest status 日期不一致且 pipeline failed 而 blocked。尚無合法開市日的 fresh 同日 pair／真 child／冪等重跑。 |
| 2 | 休市日 gate | **已驗，僅閉市 dry-run** | 9/28 官方日曆回報 closed，dry-run exit 0，`child_invocation=not_run`。沒有 updater、child 或排程執行，不記成正常日成功。 |
| 3 | stale、缺失或錯配資料 | **已驗部分 fail-closed 行為** | 9/24 historical probe 拒絕不一致的 snapshot/pipeline 身分；WP1 tests 另測失敗 stdout／receipt mismatch／舊 latest status。WP2 industry-index upstream capture time 仍 unknown，不能轉成 PIT。 |
| 4 | 明示個人模型候選後實際影響推薦 | **m11 scoped Qt widget journey 已驗** | m11 真 MainWindow 送出 19 列，19/19 active calibrated probability 為 6000 bp；canonical result `rec_03ae4c2c3e0344a7ae26d8646107c851` 已保存並讀回。候選 `rec-cal-3f8b2c276ef316e28de3806d` 僅屬 user-declared research-only，`official_historical_pit_verified=false`。 |
| 5 | artifact／來源錯配時回退規則並保留 blocker | **backend fixture 已驗；UI 真負控待驗** | WP4 fixture 負控涵蓋非有限輸出、來源 slice 改變、artifact bytes 損壞，要求 rule-only/unavailable readback 且不建立 capture。未以目前一般 MainWindow source hash 完成對應真 UI 注入。 |
| 6 | 個人選擇採用、停用與設定持久化 | **m11 scoped Qt widget journey 已驗** | m11 policy 先 personal，再 rule-only 停用，對 revision 1 做 fresh-proof rollback 並產 revision 3，最後保存 rule-only revision 4；global pointer 未觸碰。 |
| 7 | canonical result 保存、精確 identity 讀回、cold restart | **m11 scoped Qt widget journey 已驗** | m11 exact result ID 保存/readback、capture readback 與 cold restart 均在旅程收據內；執行與 runtime DB 限於 m11 隔離 root。 |
| 8 | Outcome 未成熟 | **m11 Stage C 已驗 pending 語意** | Stage C 為 `completed_with_pending`，19 pending、0 matured、0 published，reason `personal_outcome_source_or_cost_incomplete`；outcome artifact null、global evidence false、promotion credit false。 |
| 9 | Outcome 成熟後逐筆成效判讀 | **未達成／等待自然成熟** | 尚無成熟列或可報告的個人自然績效。不得用 fixture、合成日期或 holdout 分數冒充 Stage C natural outcomes。 |
| 10 | 停用、指定版本回退及 final rule-only | **m11 scoped Qt widget journey 已驗** | m11 經冷啟動、停用、fresh-source proof rollback，最後為 rule-only revision 4。此為個人 policy revision，不是 global champion 或 promotion。 |

## 跨情境限制與下一步

- WP2 observation hash 證明同次 mapper frame 的內容一致，不證明官方 response capture、publication/availability clock 或歷史產業 membership。`industry_index` source-time 與 PIT 仍是來源／工程缺口。
- m10/m11 是 `QWidget.grab()` 等 Qt widget journey 證據，不是 OS foreground、原生桌面截圖或真人操作證據。m11 的候選來源信任仍限使用者明示的 user-declared research-only snapshot；不是官方 PIT 或 formal promotion。
- 16 筆 holdout Brier 2730 bp、固定 50% null 2500 bp；這是應揭露的效果提示。它不阻止使用者選擇個人研究模型，也不支持「勝過基準」結論。After-cost probability 缺失時維持 unavailable/null。
- 下一個正常交易日須重新核官方日曆與同日 canonical snapshot/pipeline pair，然後才可開全新隔離 root 執行真 child、canonical readback 與同 run retry。不能重用 9/24 歷史資料或 9/28 閉市結果。
- 一般 MainWindow source binding P1 的三檔 hash 已記於本次路由收據；另有 m11 scoped journey 收據與 Boundary scoped review。OS 前景操作／真人使用流程仍未驗。
- 目前沒有由此文件宣稱的「WP5 十情境全通過」。本次 212P/4S 是按四組、共 14 個不重複 test modules 的受限 route；HEAD/工作樹仍維持 dirty，正常日真 child、自然成熟成效與 official historical PIT 仍未驗。

**Checkpoint 判定：WP5 尚未整體完成。** 已有受限範圍的 WP1 fail-closed／closed-day、WP2 current-only provenance、WP3 current source regression 與 m11 Qt widget/policy journey、WP4 backend fail-closed，以及 Stage C pending 證據；正常開市日真 child、WP2 官方來源時間/PIT、自然成熟成效及 OS foreground evidence 仍待完成。

## 2026-09-28 整合路由附記

在同一隔離路由收據 [`integration_route_receipt.json`](../../output/qa/personal_daily_product_20260928/integration_route_20260928/integration_route_receipt.json)（SHA-256 `f027608622a60ccf2ca998cbd99b6974a595f8d21581e04263264cf13dad0f75`）中，以 HEAD `29ff35b4a17fa3fc270aef6168ab70eaf48eeb1b` 執行四個互斥 pytest 分組；14 個唯一 test modules 的 stdout、精確 argv、自然 exit code、source/test 前後 SHA 與隔離環境均逐組記錄。總結果為 **212 passed、4 skipped、0 failed**：WP1 55P/4S、WP2 56P、WP3 33P、WP4 68P。每組自然 exit 0，HEAD、相關 source/test hashes 與 `git status` 前後一致。測試環境設定 `PROFILE=test`、QA 子樹內的 `DATA_ROOT`／`OUTPUT_ROOT`／`DB_PATH`、`QT_QPA_PLATFORM=offscreen`，pytest basetemp 使用 repo 根目錄新建短 `.tmp_i*`；沒有由本次路由直接啟動正式 updater、scheduler 或正式 D: 寫入操作。

MainWindow P1 三檔為 `ui_qt/views/recommendation_view.py` SHA-256 `4b43c273e90845e349875483e6833f1b01828c0d79373d2ab737188f06d67064`、`tests/test_cross_page_decision_journey_mainwindow.py` SHA-256 `4f7307a39bfee7acbb5918a6d3b12f5e755226927cb74ac88c629a1b641a430c`、`tests/test_ui_qt_personal_recommendation_choice.py` SHA-256 `02be7c48b6988ab7d610744b18b8daae8a4d252b224cab1f4c04ce8028fd45b7`。固定 bytes 的相鄰 regression 通過；其後 m11 scoped Qt widget journey 亦通過，不代表 OS foreground／真人操作。完整 route command/stdout/log hashes 見該收據及同目錄四份 log。

## 2026-09-28 m11 個人模型 journey 附記

MainWindow Qt 控件 journey 收據 [`personal_model_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m11/receipts/personal_model_acceptance.json) SHA-256 `dd9f976b41d589def2b13e26d50303882632725510a19b8ca1346cd17423fcf4`，狀態 `PASS_QT_WIDGET_PERSONAL_MODEL_JOURNEY`。Boundary scoped review 為 PASS、無 P0/P1。候選 `rec-cal-3f8b2c276ef316e28de3806d` 在 MainWindow 實際送出的 19 列中全部使用 active calibrated probability 6000 bp；canonical result ID 為 `rec_03ae4c2c3e0344a7ae26d8646107c851`，capture ID 為 `sha256:ad981904a1717affda64c1a787aa95c7602156344a67a6521dd0ff3c23b8ac28`，capture SHA-256 `9bb49cb8e0f461231710dfd7d8113d15383674094eb208d332315bf43dbf2f46`。收據覆蓋 canonical save/readback、capture、cold restart、停用、fresh-proof rollback 至 revision 3，最後 rule-only revision 4；`formal_database_written=false`、`global_pointer_touched=false`、`learning_root_unchanged=true`。Widget render 為 `QWidget.grab()`，明確不是 OS screenshot；OS foreground/screen capture 欄位為 false。

同一 capture 的 Stage C 收據 [`6fbe8be5…json`](../../output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json) 原始檔 SHA-256 `2355562e24d6e9e3398810835e43ac315ce84a61ae89bb55b6652abbae4dbdea`，payload SHA-256 為 `sha256:6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667`。結果為 19 pending、0 matured、0 published，沒有 outcome artifact、global natural evidence 或 promotion credit；reason 為 `personal_outcome_source_or_cost_incomplete`。日曆來源收據有效期到 23:15Z，但本次沒有 temporary-closure cache（`calendar_scope_without_temporary_cache=annual_plan_only`），故不宣稱涵蓋臨時休市公告。候選維持 user-declared research-only、非官方 historical PIT。WP1 正常開市日真 child、Stage C 自然成熟績效、官方 PIT 與 OS foreground 操作仍未驗；Validation 的 m11 專屬報告完成後再補連結。

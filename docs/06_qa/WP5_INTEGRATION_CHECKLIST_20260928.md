# WP5 整合驗收清單（2026-09-28）

## 基準與判讀方式

本清單以目前整合基準 **HEAD `2a85bc92019798668ef12f50ef87fb587d0dc58c`** 記錄各包現況。HEAD 是版本錨點，不代表每個工作包或下列十個情境已在此版本完整通過；每個收據只對其 pin 的程式、輸入、caller 與隔離範圍有效。WP0 的 R027/R028 歷史判定照原收據保留，不因本清單重判。

四種狀態如下：

| 狀態 | 用法 |
|---|---|
| **已驗證（限定範圍）** | 有收據證明所列切片；不可外推到未跑的 caller、UI 或資料來源。 |
| **工程未驗** | 仍缺真 caller、失敗／重啟／讀回路徑，或已知工程修補及重驗。 |
| **外部／來源相依** | 需要合法交易日、可用來源或其明示契約；不得靠合成或回填跨過。 |
| **等待自然成熟** | 觀測時間尚未涵蓋標籤 horizon；保留 pending/unknown，不當成失敗或成功。 |

後續表格將 **backend、可見 Qt、來源／自然結果** 分開列。`rule_only`／個人模型選擇是工程模式；「模型效果未驗」、「官方 PIT 未證」與「自然 outcome 尚未成熟」不是同一狀態。個人研究允許在工程輸入、artifact、來源時間綁定有效時明示採用；樣本少或未勝基準是提示，不是採用門檻。錯配、look-ahead、損壞或不支援輸入仍須 fail closed。沒有新增券商自動交易。

## WP0–WP4 工作包現況

| 包 | Owner／真 caller | 版本與已驗證收據 | 未驗項與狀態 |
|---|---|---|---|
| **WP0 重構收尾** | 整合裁決：root；R027/R028 與 IndustryMapper/H5 implementation：Boundary、Validation、Retirement 各自負責其 source slice。App composition 經 `decision_service_composition` 注入 IndustryMapper providers；H5 由 app facade 延遲載入 job。 | R031 closeout 在 `d77ba23fd03a94f55fa9d63a23a3e32c66544082` 接受；final route 收據 [`final_candidate_root_receipt.json`](../../output/qa/refactor_completion_20260927/final_attempt6_external_20260927/final_candidate_root_receipt.json)，SHA-256 `9ec19361748ac2a0e0de120eee62043241d42375014af3bed60b6c2a02eefd4d`；root assessment [`final_attempt6_root_assessment_20260927.json`](../../output/qa/refactor_completion_20260927/final_attempt6_root_assessment_20260927.json)，SHA-256 `b8d3f224d786f195ce5bbc8133ce95cae12a33320d627ccb27b80a1495e02b27`。當時 2,951 passed／5 skipped／36 warnings；R027 revision B 與 R028 八案例 accepted。 | 該 route pin 在 `d77ba23`，不覆蓋之後提交或目前 2a85 HEAD 的所有差異。舊 R027 strict 收據的 INCONCLUSIVE、R028 legacy comparator diagnostic FAIL 仍是歷史狀態；不改寫成 PASS。**已驗證（限定範圍）**；最終產品版仍要以當前 source pins 做整合 route。 |
| **WP1 每日資料與排程** | Daily runner／same-day status：Retirement；隔離真 child rehearsal：Boundary；整合裁決：root。真 caller 是 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py` 對官方日曆、snapshot／pipeline latest status 與 canonical recommendation identity 的 gate；它再接既有 snapshot、learning pipeline 和 RecommendationService。 | [`WP1_REAL_CHILD_REHEARSAL_20260928.md`](WP1_REAL_CHILD_REHEARSAL_20260928.md)；9/28 preflight [`preflight_receipt_2026-09-28_v2.json`](../../output/qa/wp1-real-20260928-01/preflight_receipt_2026-09-28_v2.json)，SHA-256 `c56850d84c684434d18297fb644a18611af8ebf26db78c668038f2b4e12e2fbd`；9/24 唯讀 probe [`historical_probe_receipt_2026-09-24_v2.json`](../../output/qa/wp1-real-20260928-01/historical_probe_receipt_2026-09-24_v2.json)，SHA-256 `b22c9720bbed481d49355aa57df8632aad8c7faefb3566d17194f126e5786cf0`。 | 9/28 官方日曆為休市；dry-run exit 0、正常 skip、`child_invocation=not_run`，**沒有**真 child。9/24 雖有 snapshot log/result id，snapshot latest status 已是 9/27、pipeline latest 是 9/28 且 failed，historical terminal receipt 亦 failed；同日 canonical pair 不成立，故歷史 true-child 重播 blocked。下一個合法交易日仍需真 child、同日冪等重跑、終態與 saved result readback；正式 scheduler/updater 未執行。**外部／來源相依 + 工程未驗**。 |
| **WP2 資料來源與產業鏈** | Provider／writer：Retirement；RecommendationService consumer 與獨立 review：Boundary。真 caller：`IndustryMapperDataProvider` 的 SQLite-first／CSV fallback frame → `IndustryMapper` → `RecommendationService._record_current_industry_mapping_use` → 同次 `company_registry_source_snapshot` event/readback。 | bounded current-only slice 報告 [`WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md`](WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md)；原 provider receipt [`final_receipt.json`](../../output/qa/personal_daily_product_20261006/industry_index_current_provenance_20260928/final_receipt.json)，SHA-256 `bdfcea454d3fbbbb2b743fc75aecc7660b67f1db581ba16b3115173985b072d5`；44 passed。事件封存 follow-up 收據 [`followup_receipt.json`](../../output/qa/personal_daily_product_20261006/wp2_nested_observation_echo_20260928/followup_receipt.json)，SHA-256 `1eb71993bc0b74849d9a0962f0ab993bd7b7f4cbbd3e659c01e6418b99ee477a`；42 passed、mypy／compile／diff-check exit 0。Follow-up pins：`execute.py` `d661d1f982b79f40bb9ad294caef48cc621c726e5cd63623bd0f6d67333d5165`、test `7714fb2319d6d740467996c86ba0ce0420663ab8be1aa3b6ee9125cc1497d4d9`。獨立 review 對 nested-hash mismatch 給 scoped pass；root 尚待合併 route。 | 只記本次 rowset／CSV bytes 身分與本機 `observed_at`；`status=unknown`、`pit_eligible=false`、`available_at/published_at=null`。沒有官方 response receipt 或 publication time，不能作 historical PIT。Follow-up 僅在新 observation 欄位存在時要求完整欄位組、inner self-hash 與 outer echo 一致；為保留舊 v1/v2 context，整組新欄位缺席仍走 legacy 相容路徑，無法據此推斷產生端版本。self-hash 亦非官方簽章。待 root 合併 route 重驗；source-time/PIT 仍外部相依。**已驗證（限定範圍）+ 外部／來源相依**。 |
| **WP3 日常 UI 閉環** | UI／launcher：Validation；隔離 Qt journey：Retirement；整合裁決：root。真 caller 是 `ui_qt.main.MainWindow`／`RecommendationView`；隔離準備器與 journey runner 為 `scripts/qa_personal_research_ui.py` 及 `scripts/qa_native_personal_model_acceptance.py`。 | m10 journey 收據 [`personal_model_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_acceptance.json)，SHA-256 `74bd1156e64065fa0bad01808c64f34f254aa6971e87aa4802653b71b3c60c65`；Qt widget render：啟用畫面 SHA `b8622758e9238c9d0eeb867c3b4342180a975e48793c3cdd8e0dcd6fa437150a`、規則畫面 SHA `b7a97416942e9c4188b0f3c7b2e0cf7405c3702130d5a6806719d30bb3e0e4b5`。 | m10 在隔離 `PROFILE=test` 工作區完成 V2 source recheck、推薦、canonical save/readback、capture v3、cold restart、停用、fresh-source history rollback 與 final `rule_only`。PNG 由 `QWidget.grab()` 產生，**不是 OS 原生桌面截圖／前景視窗證據**。舊 `run_02`／`run_03` 失敗與不完整嘗試保留為歷史。正式 D 未開啟；候選 learning tree 未變。**Qt widget journey 已驗證（限定範圍）**；OS desktop 操作及 WP1 正常日排程仍未驗。 |
| **WP4 模型採用與改善** | App policy／RecommendationService、capture 與 StageB/C：Boundary；inventory／source-time admission 與 UI：Validation；隔離 Qt journey／outcome 周邊：Retirement。真 caller：source-time inventory → `RecommendationCalibrationConsumer` → `RecommendationService._apply_recommendation_calibration` → canonical save/query → personal capture → StageB/C。 | m10 真候選隔離 UI journey收據同 WP3；candidate `rec-cal-3f8b2c276ef316e28de3806d`、result `rec_26fcc0776bff4c0d85c6c54787202ca8`、capture v3 SHA `b1d2f4d2985b198990e8bf6752743a19235433708225b34f24a68ce9c3936b1d`。政策依序 revision 1 personal → 2 rule-only → 3 對 revision 1 做 fresh-proof rollback → 4 final rule-only；global pointer 未變。 | 19/19 delivered rows 的 active calibrated probability 為 6000 bp；after-cost probability unavailable/null，不代表 0。來源信任是 user-declared research-only，`official_historical_pit_verified=false`，不是官方 PIT 或 formal/global promotion。m10 對應 Stage C 收據 [`personal_natural_outcomes` summary](../../output/qa/stagec_m10_assessments/s10_20260928T151528958Z/personal_natural_outcomes/runs/3c78725f8033b25f35ae21df777fc219bb20861f0bd8af2e55dbc12c140b17e4.json)，SHA-256 `f6184b1d66c25c7ee74f26930394e82ab2554e415dbe1ab2fbfaca4f72bc00da`：`completed_with_pending`、mature 0、pending 19、reason `personal_outcome_source_or_cost_incomplete`；outcome artifact null、published 0、global/promotion false。故模型工程路徑及 UI 採用／回退 **已驗證（限定範圍）**，自然成效 **等待成熟**。 |

### WP4 真候選資料與效果界線

Candidate 來源及完整 pins 已由 backend 收據鎖定。8 檔為 2308、2317、2327、2330、2344、2408、2454、3037；歷史輸入從 2024-10-24、replay end 2026-06-26，實採 64 個決策日為 2025-11-28 至 2026-05-28；20-session label horizon、50 bp 固定 round-trip cost。共 336 筆 cutoff-eligible training rows，其中 OOF calibration 176、未碰 holdout 16，其餘屬訓練折。特徵使用決策日前一交易日資料；來源 `available_at` 是明確的日粒度 user-declared contract。正式 D 的資料日期止於 2026-09-24；個人決策日期為 2026-09-28。這些值不是同日盤中可得證明，亦非官方 publication/PIT 證明。

16 筆 holdout Brier 為 2730 bp，50% null baseline 為 2500 bp；候選差 230 bp。這必須呈現為表現偏弱的提示，不能阻擋已被使用者明確選擇的個人研究採用，也不能宣稱模型已勝基準。兩個舊 legacy candidates 的安全 loader 曾載入成功，但欠 training lineage／來源時間 contract，且績效未獨立驗證；保留原件，不補造 lineage，不把它們說成 loader 失敗或可採用。

## WP5 十個情境：backend、Qt、自然結果分列

| # | 情境 | Backend／真 caller | 可見 Qt | 來源／自然結果 | 當前判定／下一步 |
|---:|---|---|---|---|---|
| 1 | 正常開市日 | **工程未驗**：WP4 手動 Service invocation 通過，但 WP1 正常日 scheduler/child 尚未跑。 | **工程未驗**：尚無成功 MainWindow run。 | **外部／來源相依**：等下一個官方交易日與同日 snapshot/pipeline pair。 | 用 fresh QA root 做同日真 child與冪等重跑；資料日期照實標 9/24 或當日實際日期。 |
| 2 | 休市 | **已驗證（限定範圍）**：2026-09-28 dry-run 正常 closed-day skip；`child_invocation=not_run`。 | 不適用；沒有開啟產品旅程。 | 不產生當日新行情／預測。 | 不繞過官方日曆，也不把 dry-run 說成 child PASS。 |
| 3 | 資料過期／缺漏 | **已驗證（限定範圍）**：9/24 historical probe 因 snapshot/latest-status 日期不符而 blocked；9/24 terminal pipeline failed。WP2 industry index 時間狀態仍 unknown。 | 新 source warning 與可行下一步尚未在 MainWindow 驗。 | **外部／來源相依**：無 official publication/available time；不能轉 PIT。 | 顯示資料截止與具體阻擋，不以舊 log 代替當日成功 pair。 |
| 4 | 尚未驗證效果、但使用者選擇模型 | **已驗證（限定範圍）**：V2 source trust、真 consumer／Service 輸出及 canonical readback 通過；m10 19/19 rows 為 6000 bp。 | **已驗證（限定範圍）**：m10 Qt widget journey 完成 V2 保存與推薦；非 OS screenshot。 | User-declared research-only；official PIT false。Brier 弱於 null 230 bp，屬 advisory。 | 可作個人研究採用，不因效果提示自動停用；不得稱官方 PIT 或 promotion。 |
| 5 | 輸入／artifact 不合法時回退規則 | **工程未驗**：已有 focused hard-guard 負例及 rule-only fallback/CAS reload；本次真 E2E 未注入壞 artifact。 | 未驗錯誤訊息與 fallback 可見性。 | 不應生成 model probability/capture，也不以自然樣本替代工程錯誤。 | 加真 caller/source mismatch 或 invalid artifact fallback smoke；保留 rule result並明示 blocker。 |
| 6 | 採用／不採用／覆寫選擇 | **已驗證（契約範圍）**：typed choice/Journaling schema 與真候選 policy CAS 有 bounded readback。 | **已驗證（限定範圍）**：m10 真 MainWindow 控件完成個人模式啟用、停用與回退；widget render 不是 OS screenshot。 | Choice 不等於成交或 natural evidence，不產生 promotion credit。 | 本列限 m10 個人政策與推薦路徑，不外推一般所有選擇理由入口。 |
| 7 | 重啟後讀回同一筆 | **已驗證（限定範圍）**：canonical query fresh readback 驗 `result_id`、payload hash、projection/capture identity。 | **已驗證（限定範圍）**：m10 cold restart 後 fresh source proof、政策讀回及 history rollback 通過。 | 歷史結果不得用今日 policy 補註；需同一 sealed identity。 | m10 working DB 維持固定 snapshot SHA；不要重用或修改已完成 run。 |
| 8 | Outcome 尚未成熟 | **已驗證（限定範圍）**：m10 Stage C exit 0，`completed_with_pending`、19 pending／0 matured，無 outcome artifact。 | 本次驗收未將 Stage C 狀態顯示於 MainWindow。 | **等待自然成熟**：`personal_outcome_source_or_cost_incomplete`；不是虧損或模型失敗。 | 保留 pending／unknown；不得發布績效或 global evidence。 |
| 9 | Outcome 成熟後評估 | **等待自然成熟**：沒有任何合法成熟列；沒有自然個人成績或 global evidence。 | 未驗成熟結果 UI 判讀。 | **等待自然成熟**：需要官方 session、價格／成本完整及同 scope 比較。 | 只用真 capture 到期後讀回；若 10/6 前無合法成熟觀測，該場景維持未完成，不合成或倒填。 |
| 10 | 停用與版本回退 | **已驗證（限定範圍）**：policy rev1 active→rev2 rule-only→rev3 fresh recheck rollback→rev4 final rule-only；候選/trust 清除，global pointer untouched。 | **已驗證（限定範圍）**：m10 透過真 UI controls 完成停用、選歷史版、fresh proposal、rollback 及 final rule-only readback。 | 對自然效果不作即時推斷。 | 限隔離 user-declared 個人研究政策，不觸 global champion/pointer。 |

## 下一個合法交易日的驗收步驟

1. 只在官方交易日快取明確標示開市後，先用 fresh QA run root 做 `run_banktaiwan_recommendation_learning_daily.py` dry-run。若日曆閉市、同日 snapshot/pipeline pair 不一致或 canonical identity 不完整，停止在 dry-run，不呼叫 child。
2. 在 wrapper 預期的同一隔離 output root 準備同日成功 snapshot 與 pipeline status，核對 result id、cohort、decision clock、source cutoff 及讀回 payload。正式 D 只作已授權唯讀來源；child 的 working DB、DATA_ROOT、OUTPUT_ROOT、capture root 與 policy root 全部留在新 QA tree。不執行 updater、Task Scheduler、正式 writer、global pointer 或 broker 操作。
3. 真 child 完成後保存 run/terminal/child receipts；以相同 run identity 冪等重跑，證明不重複記錄。明確比較正式來源 DB/WAL/SHM 前後 identity/hash/mtime，與 QA working copy 分開記錄。
4. 對同一 canonical result 做模型或 rule-only 選擇、保存、fresh query/readback、capture readback、停用及指定 revision rollback。新預測的自然結果只可在官方價格／session/成本證據足夠後轉成熟；否則維持 pending。

截至本清單日期，9/28 已確認休市；9/24 歷史 pair 被拒且 snapshot 來源資料止於 9/24。不得把這兩項包裝成下個交易日 child，也不得宣稱資料於 9/28 更新。WP1 詳情見 [WP1 rehearsal report](WP1_REAL_CHILD_REHEARSAL_20260928.md)。

## 2026-10-06 交付門檻

- 凍結可回復整合版本及完整 path/hash manifest；測試數必須對應該組 source pins。不得將 d77 的 2,951 passed 外推到 2a85 或其後變更。
- WP1 至少有一個合法開市日真 child、terminal receipt、同日 canonical save/readback 與同 identity 冪等重跑；closed-day 與 stale-pair 仍維持正確拒絕／skip。
- WP2 巢狀 observation hash P2 已做窄修並由獨立 review scoped pass；最終 merge route 仍須重驗。畫面標明 current-only、unknown 與 PIT 不可用範圍，沒有 official source receipt 時不升格。
- WP3 的 m10 已在真正 MainWindow widgets 完成個人候選、來源檢查、採用、canonical save/readback、cold restart、停用與 fresh-proof rollback；`QWidget.grab()` 只證 widget render，不是 OS foreground／desktop screenshot。一般 invalid-artifact fallback 與 WP1 自然 scheduler 仍未由此證明；正式 D 仍唯讀。
- WP4 保留已驗 backend 真模型鏈與透明限制：候選 pins、user-declared QA source、輸出、result/capture identity、policy revision、fallback/rollback 都可讀回；不更動 global pointer。official PIT、效果勝基準及自然成熟結果分列，不以其中任何一項冒充另一項。
- 手冊描述實際 UI 入口、每日順序、資料截止、unknown/pending/invalid 分別處理、使用者 choice、停用／回退與安全限制；不新增 broker auto-trading。
- **自然成熟門檻獨立記錄**：WP5 的 matured 情境只在真實 20-session horizon、官方來源與必要成本/benchmark 齊備後通過。若 10/6 前沒有合法到期 capture，交付可以說明工程使用路徑可用且結果仍 pending，但 WP5 十場景總驗收不得標全通過，績效不得推斷。

## 本清單結論

截至 2026-09-28，WP0 有既定版本的 bounded closeout；WP4 已完成真候選隔離 backend 與 m10 Qt widget 採用、canonical 保存／讀回、capture、cold restart、停用及 rollback，但僅 user-declared research-only。WP1 真開市 child 尚未驗；WP2 current-only provenance 不提供官方 PIT；WP3 m10 widget journey 已驗但沒有 OS foreground／desktop screenshot 證據。m10 capture 的 Stage C 為 19 pending、0 matured，沒有 outcome artifact 或 global/promotion publication。故 **WP5 整合驗收尚未通過**；這不否定已完成的 bounded 工程，也不把未成熟結果判成模型失敗。

## 歷史快照結論（m10 前）

以下原結論記錄於 m10 驗收前，現況請以本節的 WP3／WP4 列及 [m10 報告](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md) 為準；保留其失敗收據作歷史，不再將「MainWindow 操作未驗」或「3/3 pending」當成最新狀態。

截至 2026-09-28，WP0 有既定版本的 bounded closeout；WP4 已完成真候選隔離 backend 採用、輸出保存／讀回、capture 及 policy 停用／rollback，但僅 user-declared research-only。WP1 真開市 child 尚未驗；WP2 nested hash P2 已修並經獨立 scoped review，最終 merge route 待重驗，官方來源時間仍未證；WP3 預檢通過但 MainWindow/native 操作失敗或未驗，並有 QA working DB 初啟 hash 變動待查。新個人 capture 的 outcome 是 3/3 pending、0 matured。故 **WP5 整合驗收尚未通過**；這不否定已完成的 bounded backend 工程，也不把尚未成熟的自然結果判成模型失敗。

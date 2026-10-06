# 重構模型分工表

> 狀態：執行期權威分工表。架構與 task scope 仍以六份 `FINAL_*`、[實作 DAG](REFACTOR_IMPLEMENTATION_DAG.md) 及 [R001–R031 規格](REFACTOR_TASKS/README.md) 為準。本表只決定 implementer、reviewer 與 release discipline，不得用來擴張 task scope。

## 1. 分派原則

- `R001–R008` 保留原分派與已完成的 Gemini 工作為歷史記錄；不把既有實作或審查改寫成另一個模型完成。
- `R009–R030` 的實作一律由 `LUNA_MAX` 負責。可由多個 Luna Max worker 平行處理已解鎖且檔案 owner 不衝突的 task；中央檔案仍依 [執行順序](REFACTOR_EXECUTION_ORDER.md) 串行。
- 中、低風險 task 由 `SOL` 直接審查。高／極高風險 task 先交由未參與該次實作的另一個 `LUNA_MAX` 獨立審查，再由 `SOL` 核對實際 diff、報告、驗證與 invariants，並作最終 gate 判定。
- `R031` 由 `SOL_ONLY` 收斂 checkpoint、文件、risk/TMP 與 shared state，另由獨立 `LUNA_MAX` 複核；最終狀態仍由 SOL 決定。
- `R008` 現版採 `SOL + 獨立 LUNA_MAX` 審查與 SOL gate。較早 Gemini `PASS` 只證明當時凍結快照，不是目前版本的審查或 Wave 2 放行證據。
- 後續不再建立 Gemini 實作或 review 派送；已存在的 Gemini 報告、packet、prompt 僅保留為歷史證據，不作為新 task 的必要 gate。
- 只有 [執行順序](REFACTOR_EXECUTION_ORDER.md) 與 DAG 當下解鎖的 wave 可以開始。分派表不自行解鎖 task；每個 wave 必須先通過 checkpoint 才能釋出下一 wave。詳見 [dispatch 流程](REFACTOR_DISPATCH/README.md) 中仍適用的檔案 owner 與凍結流程。

## 2. R001–R031 assignments

| Task | Wave | Implementer | Reviewer | Risk | Dependencies | ML sensitive | Persistence sensitive | Central file exclusive | Assignment reason |
|---|---:|---|---|---|---|---|---|---|---|
| R001 | 0 | LUNA_MAX | SOL | 低 | 無 | 唯讀 inventory | 唯讀 inventory | 否 | 清冊與基線是 bounded、mechanical 且不改 production；SOL 直接核對完整性即可。 |
| R002 | 1 | LUNA_MAX | GEMINI | 中 | R001 | rule／annotation baseline | 否 | 否 | Characterization 適合 Luna；推薦語意與數值 oracle 由 Gemini 獨立檢查可降低共同盲點。 |
| R003 | 1 | GEMINI | SOL | 中 | R001 | receipt timing 唯讀 | 否 | execution／worker state | 取消、stale callback、A/B 交錯與 hidden state 涉及跨模組 subtle behavior，採 Gemini 實作、SOL 驗證。 |
| R004 | 1 | LUNA_MAX | GEMINI | 高 | R001 | receipt refs 唯讀 | 是 | persistence characterization fixtures | 建立保存／故障 golden coverage 屬 bounded testing；由 Gemini review failure-window 完整性。 |
| R005 | 1 | GEMINI | SOL | 高 | R001 | 否 | 歷史 manifest 唯讀 | replay／portfolio characterization | Replay mode、cutoff 與 portfolio 行為跨多模組，需 Gemini 獨立推理，SOL 查實際 oracle。 |
| R006 | 1 | GEMINI | SOL | 高 | R001 | 是 | ML artifact 唯讀 | Direct／artifact identity inventory | ABI、serialized class path、15-path identity 與未知 artifact 分帳屬 compatibility-sensitive analysis。 |
| R007 | 1 | LUNA_MAX | SOL | 中 | R001 | leaf contract | 否 | `data_module/__init__.py`（R007 獨占） | Data leaf contracts 與為達成無 I/O import 所需的窄 lazy package exports 由 Luna 實作；SOL 檢查既有 top-level import 相容性與依賴方向。 |
| R008 | 2 | LUNA_MAX | 歷史：GEMINI（舊快照）；現版：獨立 LUNA_MAX → SOL gate | 高 | R002、R003、R007 | typed refs | contract schema | recommendation／execution contracts；若啟用受控修正則獨占 app/decision parent `__init__.py` | 現版獨立稽核已找出 terminal cause、receipt binding、options、range、deep-freeze 與 export oracle 缺口；依 SOL 裁決在 R008 內修正，再由 SOL 與獨立 Luna 按最新凍結版複核。 |
| R009 | 3 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R004、R008 | projection refs | 是 | codec、legacy DTO seam | 唯一 schema-driven codec 與 legacy decoder 直接影響保存 bytes、revision 和歷史 fixtures；Luna 實作，另一 Luna 核對 roundtrip／revision／舊格式，SOL 作最後 gate。 |
| R010 | 3 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R006、R007、R008 | 是 | refs only | ML boundary contract | `PreparedMLInput` 與 app adapter contract 固定 rule／ML snapshot identity 及 cutoff 邊界；獨立 Luna 核對 frozen provider 呼叫順序、無 ML ABI 漂移與依賴方向，SOL 作最後 gate。 |
| R011 | 4 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R002、R003、R008、R009、R010 | 保留現況 | 否 | `recommendation_service.py`、execute、ports | 完整 execution、invocation capture 與單向舊 list façade 觸及中央 service 和 hidden state；由單一 Luna 擁有排他檔案，獨立 Luna 核對 A/B、result identity、last_* 邊界與 parity，SOL 作最後 gate。 |
| R012 | 5 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R004、R009、R011 | receipt refs | 是 | repository、save coordinator、artifact store | 唯一 create-only writer 涵蓋 identity、durability、orphan recovery 與 legacy readback；獨立 Luna 核對衝突／中斷窗口和不可覆寫語意，SOL 作最後 gate。 |
| R013 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R011、R012 | projection display | save caller | `recommendation_view.py` | Qt worker/view 改傳完整 execution 並使用 read model；獨立 Luna 核對取消、stale callback、result identity 與不得讀 last_*，SOL 作最後 gate。 |
| R014 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R011、R012 | receipt passthrough | 是 | scheduled recommendation wrapper | 排程與 QA caller 遷移須保留 clock、calendar、save-before-forward 和 receipt passthrough；獨立 Luna 核對順序及舊 DTO 移除範圍，SOL 作最後 gate。 |
| R015 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R011、R012、R013、R014 | 是 | 是 | personalization save／ACK seam | 這是最後保存 caller，涉及 candidate/model/receipt/ACK 身分、retry/CAS 與多個 outcome；獨立 Luna 核對 readback 和重試冪等性，SOL 作最後 gate，並確認 TMP-REC-03 closure。 |
| R016 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R011、R012 | stored refs only | read path | saved-result consumers | Evidence、Advice、Decision Desk 等改由唯一 query 讀取 verified execution/read view；獨立 Luna 搜核 live-state lookup、重複 decoder 與 stored-reference 使用，SOL 作最後 gate。 |
| R017 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R005、R009、R011 | 否 | child refs | replay provider／bridge | 建立 typed child execution 與 parent refs，同時保留既有 replay 算法及 mode policy；獨立 Luna 核對同 mode parity 和沒有第二 evaluator，SOL 作最後 gate。 |
| R018 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R007、R011、R013–R017 | frozen branch | 否 | `recommendation_service.py` input preparation | 從中央 service 抽出 source selection、cutoff、PIT/provider 與 fallback，但不動決策算法；獨立 Luna 核對中央檔案 owner、None/empty 語意與 frozen-branch 時序，SOL 作最後 gate。 |
| R019 | 10 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R018、R023、R024 | rule candidate identity | 否 | recommendation evaluator／service | Pure evaluator 收斂 filter、factor、ranking、reason 與 candidate assessment，數值／排序 parity 風險最高；獨立 Luna 用原 oracle 核對精確結果與 domain 無 I/O，SOL 作最後 gate。 |
| R020 | 11 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R017、R019 | 否 | historical refs | replay／policy／portfolio integration | 共用 evaluator 時必須由明示版本化 policy 保留 interactive/replay 的 cutoff、母體與 portfolio 差異；獨立 Luna 核對歷史參照和同模式 parity，SOL 作最後 gate。 |
| R021 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R001、R007 | 否 | read-only data | StockScreener reader／provider | 將 StockScreener concrete I/O 移到 data provider 並維持注入式依賴；獨立 Luna 核對 fallback、None/empty 與 data→decision 方向，SOL 作最後 gate。 |
| R022 | 8 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R003、R012、R015 | regime refs | state file | regime detector／save-time cleanup | Hysteresis、cooldown、多日 prior state 與 save-time re-detect 牽涉狀態轉移和持久化；獨立 Luna 核對 history/並行語意及使用 execution-time regime，SOL 作最後 gate。 |
| R023 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R001、R007 | eligibility frozen | data records | fundamental／monthly factor vertical | 月營收垂直切片需將來源／availability records 留在 data、factor 語意移至 decision；獨立 Luna 核對 PIT、unit、missing 與 reverse edge，SOL 作最後 gate。 |
| R024 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R023 | eligibility frozen | data contracts | statement／valuation factor vertical | 延伸 R023 的 statement／valuation source contract 與 domain mapping；獨立 Luna 核對各來源語意、availability/PIT parity 和剩餘 reverse edges，SOL 作最後 gate。 |
| R025 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 高 | R001、R005 | 否 | strategy spec | strategy registry／executors | 將 strategy contract、registry 與 executors 移至 decision，保留唯一 ID、signal 行為及序列化相容路徑；獨立 Luna 核對 callers、backtest parity 和 class paths，SOL 作最後 gate。 |
| R026 | 11 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R006、R010、R011、R018 | 是 | receipt | ML adapter／calibration seam | 明確 prepare/resolve `PreparedMLInput` 並接既有 receipt，核心風險是 provider race、feature/model/result identity 和 publication 順序；獨立 Luna 核對 ABI/source identity 不變與 race 測例，SOL 作最後 gate。 |
| R027 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R006 | 是 | 隔離 fixture | Direct identity experiment | 這是 production-read-only 的舊／候選 identity 實驗；實作者須使用獨立 oracle、不得共用被抽 helper，另一 Luna 核對 hash、時序、數值與 resume verdict，SOL 作最後 gate。 |
| R028 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R027=PASS | 是 | technical publication | `update_service.py`／technical job | 僅在 R027=`PASS` 後搬移 publication orchestration，並維持 frozen Direct identity、publication 時序與 bytes；獨立 Luna 逐項核對實驗 gate 及原 writer 次序，SOL 作最後 gate。 |
| R029 | 12 | LUNA_MAX | 獨立 LUNA_MAX → SOL gate | 極高 | R013–R016、R020–R026、R027 gate | ABI 保留 | legacy read | service／repository／bridges／re-exports | 僅在 caller 清零後退休 runtime bridges、last_*、舊 engine 與無用 re-export，保留永久 decoder/class alias；獨立 Luna 核對 caller/TMP 清冊、serialized paths 與雙引擎殘留，SOL 作最後 gate。 |
| R030 | 13 | LUNA_MAX | SOL | 中 | R029 | compat fixture | codec locality | architecture guards | 以已知 bad fixture 與 repo 正向驗證建立窄 dependency/schema guards，並檢查 confidence、新 strategy、新 technical feature 的變更局部性；SOL 直接核對 false-positive baseline、FINAL invariants 與不擴成產品功能。 |
| R031 | 14 | SOL_ONLY | 獨立 LUNA_MAX → SOL gate | 中 | R030 | 最終驗證 | 最終驗證 | checkpoint／文件／shared state | SOL 收斂 C1–C4、各 wave evidence、risk/TMP closure 與交接聲明；獨立 Luna 逐項重核所引用的證據與文件狀態，SOL 保留最終 closeout gate，且不宣稱產品 Gate。 |

## 3. Wave release 狀態

| Wave | Status | Released tasks | Blocked by |
|---:|---|---|---|
| 0 | `PASS` | R001 | SOL review PASS；replay/TMP 清冊勘誤已重審 PASS，見 `REFACTOR_REPORTS/R001_SOL_REVIEW.md`、`REFACTOR_REPORTS/R001_SOL_ERRATUM_REVIEW.md` |
| 1 | `PASS` | R001–R007 | R007 時區名稱別名勘誤已依 `R007_LUNA_TZNAME_INDEPENDENT_REVIEW.md`、`R007_SOL_TZNAME_ACCEPTANCE.md` 與 `WAVE1_R007_TZNAME_CHECKPOINT.md` 在最新 SHA 上恢復 PASS。 |
| 2 | `PASS` | R008 | result_id 勘誤原 SHA 已 PASS；R009 schema-range 唯一一行窄變更在新 SHA 經 `R008_SCHEMA_RANGE_DEPENDENCY_RECHECK.md` 重驗 PASS。 |
| 3 | `PASS` | R009、R010 | 兩項獨立 Luna 複核與 SOL 整合驗收 PASS；`WAVE3_CHECKPOINT.md` 在 main 最新整合狀態 PASS。 |
| 4 | `PASS` | R011 | 最終獨立 Luna review 與 SOL 整合驗收 PASS；見 `REFACTOR_REPORTS/R011_SOL_INTEGRATION_ACCEPTANCE.md`、`REFACTOR_REPORTS/WAVE4_CHECKPOINT.md`。 |
| 5 | `PASS` | R012 | 最終獨立 Luna review 與 SOL 整合驗收 PASS；見 `REFACTOR_REPORTS/R012_SOL_INTEGRATION_ACCEPTANCE.md`、`REFACTOR_REPORTS/WAVE5_CHECKPOINT.md`。 |
| 6 | `PASS` | R013、R014、R016、R017 | C1 engineering gate 與 Wave 6 bounded task gates 已通過；依 [Wave 6 最終 gate 報告](REFACTOR_REPORTS/WAVE6_FINAL_GATE_REPORT.md) 釋出 Wave 7。此為工程釋出，不是正式資料、ML promotion 或 production acceptance。 |
| 7 | `CHECKPOINT_RECORDED; BOUNDED TASK ACCEPTANCES ONLY` | R015、R021、R023、R025；R027 實驗結果已記錄 | R015、R021、R023、R025 各自 bounded scope 已接受；R027 為 `INCONCLUSIVE`，`AB-ML-01` OPEN、`TMP-ML-02` ACTIVE，故 R028 保持 BLOCKED。`TMP-REC-03` 已退休；`TMP-STR-01` 仍 ACTIVE。此列不宣稱 Wave 7 full closeout。詳見 [Wave 7–10 至 R020 checkpoint](REFACTOR_REPORTS/WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md)。 |
| 8 | `BOUNDED TASK ACCEPTED; NO WAVE CLOSEOUT` | R022 | R022 已 `ACCEPTED_SCOPE`；`TMP-RGM-01` 仍 ACTIVE，需待 R029 caller inventory／相容入口退出條件完成。此列不宣稱 Wave 8 full closeout。詳見 [Wave 7–10 至 R020 checkpoint](REFACTOR_REPORTS/WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md)。 |
| 9 | `BOUNDED TASK ACCEPTANCES; CONDITIONAL R028 BLOCKED` | R018、R024；R028 未釋出 | R018、R024 已各自 `ACCEPTED_SCOPE`；R027 非 PASS，因此 R028 不啟動。個別 scope acceptance 不解除該條件分支。詳見 [Wave 7–10 至 R020 checkpoint](REFACTOR_REPORTS/WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md)。 |
| 10 | `R019 BOUNDED_ACCEPTED; C2 ACCEPTED_WITH_NAMED_QA_BASELINE` | R019 evaluator core；C2 current union | R019 bounded scope 已接受，`TMP-REC-01` 窄 rule bridge CLOSED。C2 current union 為 141 unique tests／88 sources、1,860P／5S／34W、exit 0，229 個輸入 pre/post 零漂移；Workbench 84P、broad mypy 724 files／0 issues。C2 當時 Update validator 的 WinError 32 TEMP SQLite teardown exit 1 保留為具名 QA baseline；C4 validator 後續成功不改寫 C2 收據。此列不宣稱產品 release。詳見 [R019 implementation report](REFACTOR_REPORTS/R019_IMPLEMENTATION_REPORT.md)、C2 union receipt（開發收據見dev） 與 C2 mandatory gates（開發收據見dev）。 |
| 11 | `R020 ACCEPTED_WITH_RETAINED_COMPATIBILITY; R026 BOUNDED_ACCEPTED` | R020 typed provider handoff／replay／recovery；R026 supported caller/profile preparation／post-calibration handoff | Root 已接受 R020 bounded R005／V-REPLAY 與 5 個 distinct persistent-state hard-exit windows，`TMP-REC-04=CLOSED`；R026 明列 NP1／NP2 profile 與同次 capability 的 supported runtime migration 亦接受，該範圍 `TMP-ML-01=CLOSED`。此處不關閉獨立 `TMP-NUM-01`，也不宣稱所有 caller／平台／profile parity。C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`。詳見 [R020 implementation report](REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md)、[R020 hard-exit QA](../../06_qa/R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)、[R026 implementation report](REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md) 與 C2 receipt（開發收據見dev）。 |
| 12 | `R029 ACCEPTED_WITH_RETAINED_COMPATIBILITY` | R029 retirement ledger | `TMP-REC-04`、`TMP-REC-06` engine-selector 條件及 supported caller/profile `TMP-ML-01` 遷移條件 CLOSED；REC-06 ABI parity test 與歷史 decoder 保留。`TMP-REC-02/05/NUM-01/STR-01/RGM-01/ML-02` 為 `BLOCKED_WITH_OWNER`，不得宣稱所有 compatibility facade 已移除。詳見 [R029 implementation report](REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [FINAL_MIGRATION_SEQUENCE ledger](FINAL_MIGRATION_SEQUENCE.md)。 |
| 13 | `R030 BOUNDED_ACCEPTED` | Synthetic architecture guard／extensibility fixtures | Bounded synthetic slice 為 17P，root 獨立 5-file adjacent route 48P；只證明 architecture guards、confidence/schema extension、strategy registry 與 feature-builder 的局部性，不宣稱新增 production feature 或正式 trained-artifact path。R029 prerequisite 已接受。詳見 [R030 fixture QA](../../06_qa/R030_EXTENSIBILITY_FIXTURE_QA_20260925.md) 與 [R030 manifest](../../06_qa/R030_EXTENSIBILITY_FIXTURE_QA_MANIFEST_20260925.json)。 |
| 14 | `R031 ENGINEERING_SCOPE_COMPLETE_WITH_RETAINED_BLOCKERS` | R031 final relevant regression／文件 closeout | 9/25 C4 union 為 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`，原始 2,446P／2F／5S／35W 收據保留；9/26 candidate revalidation 已啟動，結果以 R031 closeout 後續 receipt 更新。R027／R028 與具名 compatibility owners 仍保留；這不是產品 release、正式資料接受或模型 promotion。詳見 R031 closeout（開發收據見dev） 與 C4 machine receipt（開發收據見dev）。 |

Wave 1 的 R003、R005、R006 原實作均由 Gemini 完成，SOL 審查為 `CHANGES_REQUIRED`。依使用者指示，三項回修改由 Luna Max 在各自原 scope 執行。R003/R005 的[合併 Gemini 正式審查](REFACTOR_REPORTS/WAVE1_R003_R005_GEMINI_REVIEW.md)與各自 [SOL 驗收](REFACTOR_REPORTS/R003_SOL_INTEGRATION_REVIEW.md)、[R005 驗收](REFACTOR_REPORTS/R005_SOL_INTEGRATION_REVIEW.md)均 PASS；R006 的[正式 Gemini review](REFACTOR_REPORTS/R006_GEMINI_REVIEW.md)與[SOL 整合驗收](REFACTOR_REPORTS/R006_SOL_INTEGRATION_REVIEW.md)亦 PASS。SOL V-EXEC 41 passed、V-REPLAY 66 passed（24 個既有警示）。表格保留原始分派與已完成 Gemini 證據；這些是 Wave 1 歷史，不代表後續 task 仍須派 Gemini。

R008 初始 worker 在動檔前發現 parent package eager import 造成新 leaf contract 匯入 I/O。SOL 依[範圍裁決](REFACTOR_REPORTS/R008_SCOPE_ADDENDUM.md)將兩個 parent `__init__.py` 的窄 lazy exports 納入 R008 專屬受控範圍並要求相容測試；此為既定 INV-03 的 implementation conflict 修正，R008 與 Wave 2 已依後續驗收證據 PASS。

R008 初始 parent lazy-export、contract、ML availability、receipt/execution binding 與 result_id 勘誤的歷史報告均保留。`R008_GEMINI_PRE_BATCH_PASS.md` 僅適用舊凍結 SHA；最終 R008 驗收以 `R008_SOL_RESULT_ID_ACCEPTANCE.md`、`WAVE2_RESULT_ID_CHECKPOINT.md` 及後續唯一 schema-range 窄變更的 `R008_SCHEMA_RANGE_DEPENDENCY_RECHECK.md` 為準。R009/R010 已依新 R008 contract SHA 完成各自獨立 Luna review 與 SOL 整合 gate；後續不再派 Gemini。

Wave 2 先前的 [Gemini pre-implementation analysis](REFACTOR_REPORTS/WAVE2_GEMINI_PARALLEL_ANALYSIS.md) 與相應 packet 仍保留為歷史風險分析；`ANALYSIS_STATUS: COMPLETE` 不是凍結後的正式審查，也不改變現版 gate 狀態。

R027 的結果若為 `FAIL` 或 `INCONCLUSIVE`，立即啟動 `AB-ML-01`，R028 保持 blocked；不得改派其他模型繞過。此條不因實作者或審查者模型調整而改變。

## 4. Report 與 review custody

- 每個 implementer 必須建立 `REFACTOR_REPORTS/Rxxx_IMPLEMENTATION_REPORT.md`，列出實際修改、依賴證據、驗證結果與未解風險。
- 高／極高風險 task 的 diff、報告與驗證先凍結，再交給不同於 implementer 的獨立 LUNA_MAX reviewer；reviewer 依同一凍結版提出 findings，不能重用實作者的推論代替獨立檢查。其後 SOL 必須逐檔核對實際 diff、報告、測試與 FINAL invariants，完成最終 gate。中／低風險 task 由 SOL 直接審查；R031 依表格採獨立 LUNA_MAX 複核再由 SOL closeout。
- R008 現版的 review custody 為獨立 Luna review + SOL 驗收；其較早 Gemini PASS 僅保留為舊 snapshot 歷史。R001–R007 已完成的 Gemini 分析／審查及 Wave 1 整合證據同樣保留原貌；不再建立 Gemini implementation/review packet。
- 已存在的 `REFACTOR_DISPATCH/GEMINI_*.md` 與 Gemini report 是歷史輸入，不自行解鎖 task，也不取代目前凍結版的獨立 Luna review 或 SOL gate。
- Task status 只可由 SOL orchestrator 設為 `PASS`、`CHANGES_REQUIRED` 或 `ARCHITECTURE_BLOCKER`；worker 或獨立 reviewer 自報完成、測試通過及舊快照 PASS 均不等於 task PASS 或 wave release。
- Wave 1 執行中發現 Python 會先執行 parent package；為滿足 R007 的無 I/O leaf import，`data_module/__init__.py` 已納入 R007 的窄範圍並由該 worker 獨占，只允許保留原四個 public exports 的 lazy 相容實作。

## 5. 更新記錄

- 2026-09-22：依最新分派決定，保留 R001–R008 的歷史實作／Gemini 證據，改列 R009–R030 由 LUNA_MAX 實作、依風險採獨立 LUNA_MAX 複核及 SOL gate，R031 由 SOL_ONLY 收斂並接受獨立 LUNA_MAX 複核。
- 2026-09-22：R009/R010 與 Wave 3 checkpoint PASS；R008 schema-range 唯一窄變更重驗 PASS。Wave 4 只釋出 R011，後續仍封鎖。
- 2026-09-23：R011 與 Wave 4 checkpoint PASS；已驗證 155 個相關測試及最終獨立 Luna review，六個既有 calibration 日期 fixture 失敗具名分帳。Wave 5 僅釋出 R012，C1 與 Wave 6 仍封鎖。
- 2026-09-23：R012/Wave 5 PASS 後完成 C1。六個 calibration 日期 fixture 失敗以具名測試資料修復，獨立 Luna 複審 PASS；C1 核心 213 passed/3 個 Windows symlink 權限 skip、ML 93 passed、相關 natural fixture 76 passed，靜態檢查 PASS。C1 放行 Wave 6，Wave 7 仍封鎖。
- 2026-09-23：Wave 6 readiness 揭示 R008–R012 canonical execution／query 對既有 scheduled、saved-result、replay consumer 欄位不完整；R014/R016/R017 在改檔前停止。SOL 撤回 C1 原 PASS 放行並重開契約完整性修復，不將測試綠燈誤作 consumer parity。所有後續 wave 保持 blocked。
- 2026-09-23：R023 statement `.quality` regression 曾使 R023 gate 重開；R024 修復後 regression route 152 passed，root 獨立 fresh TEMP R024 20-module route 107 passed並檢查擴充 AST guard，R023 與 R024 均恢復／裁決 `ACCEPTED_SCOPE`。Wave 7–14 仍 `BLOCKED`；個別 bounded scope acceptance 不等於 wave release，正式資料與 ML gates 不變。詳見 R023 QA 報告與 R024 implementation report。
- 2026-09-23：R021 由 root 與獨立 reviewer 裁定 `ACCEPTED_SCOPE`；implementation report 記錄 24 focused、28 affected UI、84 UpdateView、Update QA 22 passed/0 failed/5 skipped 與 broad mypy 680/0。Root 另回報並行 `tmp_path` failure-isolation rerun 通過，但 test node／aggregate 未記錄，僅作補充、不另計 suite。Wave 7–14 仍 `BLOCKED`；個別 R021 acceptance 不構成 wave release。
- 2026-09-24：更新 Wave 6–14 現行 checkpoint 摘要並新增 [Wave 7–10 至 R020 bounded-release checkpoint](REFACTOR_REPORTS/WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md)。只記錄既有 task gate：R027 `INCONCLUSIVE`／`AB-ML-01` OPEN／R028 BLOCKED；Wave 11 僅授權 R020 bounded implementation。未宣告 Wave 7–10 full closeout 或 C2。

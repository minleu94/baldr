# 6M 工程 Roadmap 開頭狀態紀錄

> 日期化狀態、單輪 handoff、Gate 7 狀態、Gate 校正與更新流水帳已從核心入口移出；本文保留原紀錄，不能作為目前狀態或優先順序依據。


> **2026-10-06 文檔判讀補充**：下文 2026-09-17 等 bounded status 為歷史時點，不覆蓋後來已接受的 U1/U2／H20 使用狀態。當前啟用與剩餘驗收看 [Snapshot](../00_core/PROJECT_SNAPSHOT.md)；工程 Roadmap Gate／自然資格／長期 maturity 不因文檔整理升級。必要操作／調度指引仍保留於 [文檔索引](../00_core/DOCUMENTATION_INDEX.md#必要調度與維運)。

> **2026-07-12 engineering package update**：Gate 2–7 的純工程 deliverables 已依獨立 slices 落地並由 `scripts/verify_gate_2_to_7_closeout.py` 驗證；external human/time/license/evidence/ML gates 尚未因此完成。後續執行重心轉為 [Gate 2–7 External Validation Register](../06_qa/GATE_2_TO_7_EXTERNAL_VALIDATION_REGISTER.md)，不得重做工程模擬來折抵真實時間或人工決議。

> **2026-07-14 evidence rehearsal update**：replay / P0 source shadow / ML shadow / lineage 的唯讀工程預演底座狀態為 `engineering_rehearsal_complete`；coverage、quality、missingness 與 blocker 可重跑，但不折抵任何 Gate 2–7 external human/time/license/evidence/ML 需求。詳見 [Evidence Rehearsal Engineering Closeout](../06_qa/EVIDENCE_REHEARSAL_ENGINEERING_CLOSEOUT_2026_07_14.md)。

> **工程終態**：15 capability、canonical lineage 與 operations handoff 已收口為 `V3.3 Engineering Complete`；後續屬 `V4.0 Evidence Accumulation Track`，不是正式 V4.0。見 [V3.3 Engineering Closeout](../06_qa/V3_3_ENGINEERING_CLOSEOUT_2026_07_12.md)。

> **2026-07-13 系統整合校正**：跨流 contracts、唯讀正式資料 smoke、Dashboard／Broker latency 與 pure closeout verifier 已完成工程驗證。Gate 2 真實 forward evidence、Gate 3 source／license acceptance、Gate 7 formal OOS、shadow-day 累積與 promotion review 均仍是 external pending，不能由本次工程測試折抵。
>
> **最後更新**：2026-09-17；本輪基線為已提交 `0219d709`，並承接 Qt 修復 `9a9e778b`，不新增產品版號。
> **定位**：本文件是未來六個月工程執行的 scoped authority，將 [PRODUCT_ROADMAP_POST_REFACTOR.md](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 轉成可交付、可測試、可回滾的 Gate。
> **現況**：目前完成狀態以 [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md) 為準。既有 V3.0 engineering candidate、read-only Workbench、candidate source readiness 或 simulated phase progress 不自動折抵本 Roadmap 的產品 Gate。
> **版本 companion**：產品成熟度版號見 [VERSION_ROADMAP_V2_1_TO_V4_0.md](../00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md)。

> **2026-09-17 ABC bounded status**：A 的 Paper／calendar／Recommendation receipt 已完成
> bounded readback；9/17 Recommendation receipt 的 source、calendar 與 14 candidate file hash
> 已由 root 逐欄核對，calendar capture／availability 為 9/14，早於 9/17 candidate decision。
> 14 筆仍是 candidate-only；`1418` 只有 rejected sell、沒有 filled entry source，維持 unproven。
> Paper completion 仍要求同一 decision date 的 terminal run、latest／immutable phase receipt、
> `calendar.available <= decision` 與 source／state hash；heartbeat 舊 snapshot 不構成完成。
> legacy 05:45 9/17 實跑為 `passed_with_warnings`；BankTaiwan pending 18、matured 0；raw PIT
> invalid 7、unavailable 16,913。official-events 的 `prior canonical raw lineage missing` 已定位並
> 修復為 reader compatibility gap：A lineage path 跨檔 `8 passed`（prior-lineage 單檔含 3 tests），
> isolated next-publication real chain output-only readback（`output/qa/official_event_next_publication_output_only`）
> 為 `40` chain／`28,636` events／`95` raw，coverage gap `0` 且 source bindings 均在 self-contained
> output 內。先前 failed latest receipt 仍保留，正式 job 尚未重跑；不能歸類為 raw 缺件或純 external。
> formal input readiness artifact 的原始 aware clock 為 `training_as_of=2026-09-17T11:19:45.4764372-07:00`、
> `created_at=2026-09-17T11:19:46.502565-07:00`；loader 以 `Asia/Taipei` 轉出 `training_as_of_date=2026-09-18`，
> readiness 為 `0/3`。三個 configured input path 仍為 `clock-20260819`／`prospective_output_not_published`；
> 這只代表 configured input 缺失，不能外推 D 槽沒有其他產物。
>
> B historical context assembly 已以 observed market／stock date union 保留 explicit empty slot，
> 不把上一個 market date 冒充 cutoff，也不壓縮 missing-middle session。bounded report 分開
> row-count、observed-calendar exact join、value completeness 與 horizon completeness；observed
> `market_indices` DISTINCT 日期不是 official complete session calendar，故 horizon／formal／training
> credit 均為 false。報告 `report_hash`=`sha256:06304a44340e3cfad623c2710e6bd84cd1d479950df0c344623ba3a2ad8f1b72` 是排除自身欄位後的
> canonical logical hash；JSON file SHA256=`f6c3d15bb04f93782c1b42a903a3934fdd30109f6039c0d541c3bf14a7fef698`。
>
> C 的 fit producer／persistence／CLI、artifact persistence 與 readback engineering 已 bounded
> accepted：fit runner／CLI／calibration／read service focused suite `41 passed`，wrong-scope
> empty-evaluation exit `2` 且不產生 evaluation／verified binding；五檔 explicit-package-bases mypy
> clean。source fingerprint artifact `c_personalization_fit_acceptance_20260917.json` SHA256=
> `d45033e0ea8a4c418150df685e96d26d7425872a6c633695f0aa752054f0a3d3`。正式 D 的 real scope／delivery／
> human action／natural outcome 仍缺；fixture／replay／`natural sample=0` 不授予 formal／natural credit。
> 9/17 PIT audit 維持 same-day denominator 未驗證、taxonomy publication blocked、security lifecycle 僅
> historical research replay、formal sidecar 不存在；DNS pre-response failure 未進 parser，`5371`／`3718`
> 不 carry-forward，這些是 source／formal gate evidence residual。
> 全局 ABC 仍 `in_progress`；目前 module trees mypy 為 630 source files clean（scripts excluded，
> 僅 2 untyped-body notes）。

## 2026-09-06 Gate 對應歷史紀錄

### 2026-09-06 閉環工程增量的 Gate 對應

八卡依 [Master Goal Playbook](../09_archive/MASTER_GOAL_PLAYBOOK_2026_09_06.md) 的檔案 owner 與隔離雙根執行；[TASK-08 交接](../06_qa/TASK_LOOP_08_HANDOFF.md) 保存中央組裝與整合驗收。整體仍為 `action_required`、V4 Evidence Accumulation，以下工程契約不代表正式 Gate Exit Criteria 已通過。

| 既有 Gate | 本輪可承接的工程能力 | 下一個不可替代的條件 |
|---|---|---|
| Gate 1／3 | 01／02 的日期與品質 DTO、03 推薦設定與輸入指紋、07 同日唯讀聚合 | source-by-source acceptance、精確可得時點、PIT 產業成分及指標版本鏈 |
| Gate 2 | 05 顯式 Registry 恢復、版本隔離、Evidence lineage／人工提案；08 observer 生命週期 | 自然前瞻週期、具名 review 與正式證據信用；不得由 replay／fixture 折抵 |
| Gate 4／6 | 04 下一可交易開盤與精確成本；06 candidate-only append 帳本、補償事件及 07 ledger adapter | 真實 Paper producer fills／cost、thesis、已提交估值、reconciliation 及正式來源切換 Gate |
| 跨 Gate | 八卡專用契約與離線 QA、中央文件／inventory／組裝驗收 | 工程全域結果依當輪紀錄；production canary、scheduler／writer 審核各自保留 |

08-B 已完成本輪隔離工程接線與驗收，後續依正式接受與時間條件推進；`9a9e778b` 已驗收真 MainWindow 的
`DeferredDelete` close lifecycle、busy 單次 close 與實際 OS process exit `0`，但完整截圖 smoke／人工 UI
驗收仍未執行。固定組合仍是 per-stock 研究；舊無版本與 legacy run 不升級為 `next-session-open.v2`，取消／部分結果不作績效混排。現有 JSON／JSONL 正式預設未切換，migration 只驗證指定隔離副本，不以完成候選 schema 宣稱正式帳本完成。


## Gate 7 日期化狀態紀錄

### 2026-08-19 Prospective restart execution lock

- 舊 `clock:prospective:20260819:v1` 已錯過且不得重建、沿用或回填；歷史 `2014–2026` artifacts 不取得 prospective Formal credit。
- 下一個執行 clock 依執行當下的官方 TWSE／TPEX 共同交易日與至少一個完整準備日另建新 identity；選日方法、責任與 DoD 見 [Prospective Formal Restart Direction](../06_qa/PROSPECTIVE_FORMAL_RESTART_DIRECTION_2026_08_19.md)。
- Rule Champion 由 Codex 從現有可重播、版本化、正式 Rule path 提出單一首選；Owner 只對具體 Champion identity 做一次接受，不需要自行設計策略。
- Prospective PIT sector 固定採 TWSE `t187ap03_L` 與 TPEX `t187ap03_O` 官方公司基本資料，保存 source／license／publication／available／hash lineage；不得用 current `companies.csv` 回填歷史。
- 本執行軌持續 `formal_oos_allowed=false`、alpha 0、Broker disabled；strict readiness 不等於 Formal OOS、promotion 或下單授權。

### 2026-08-25 activation-day pre-open status

- `clock:prospective:20260825:v1` 已建立，activation=`2026-08-25`、preparation=`2026-08-24`；官方 TWSE／TPEX source bytes 已在 create-only staging，尚未寫入正式 PIT manifest。
- Rule Champion identity 已接受，但三份 clock-bound formal inputs 仍為 `0/3`，controlled path 缺件與 T-1 `2026-08-24` market rows 使 strict readiness fail-closed；不得 partial start、回填或把 staging／fixture 當成 Formal evidence。
- 本週狀態、source hashes、測試與未通過 gates 見 [Prospective Formal Restart Weekly Update](../06_qa/PROSPECTIVE_FORMAL_RESTART_WEEKLY_UPDATE_2026_08_25.md)；本段不代表 Formal OOS、promotion、broker 或 weekly gate credit。

### 2026-08-28 owner handoff preparation

- Formal candidate inventory 實際解析 `511` 份 manifest、略過 `1` 份並因 bounded 上限保留 `truncated=true`；candidate input counts 為 causal=`3`、PIT sector=`1`、formal Rule=`0`，沒有任何一項可直接消費為正式 input。
- 新增 `scripts/build_formal_input_owner_packet.py` 與 `formal-input-owner-review.v1` 只讀 packet，為三項 expected input 建立具名 owner／reviewer review slot，保留 bounded manifest identity／原因；packet 不選 candidate、不寫 controlled path、不把 research／prospective artifact 改名成 Formal。
- 實際 packet status=`needs_named_owner_reviewer`、formal ready=`0/3`、`formal_oos_allowed=false`、`candidate_only=true`；下一步是 owner-controlled publisher 產出三份 expected schema manifest，再重跑正式 readiness。這是可持續的 handoff 工程化，不折抵 Formal OOS、promotion 或 broker gate。

### 2026-08-30 current Gate rebaseline

- Gate 2 Evidence 已不再只是等待三個自然週期：歷史 working-copy=`1/3`、owner-approved
  UI projection=`3/3`、正式 sidecar pending=`10`、multi-day=`3/3`，但
  `formal_credit_authorized=false`、production scheduler disabled。下一步是具名 review、
  formal credit 與 scheduler approval／recovery，而不是 replay 回填。
- Gate 3 P0 已有 13/13 machine evidence 與 3/3 license page candidate；accepted／limited
  仍為 0、downstream eligibility none。下一步是 publication／coverage denominator／license／
  decision-time PIT 與逐列 owner 決議，不再優先增加同型 parser／contract。
- Gate 4 Paper 已有 21 snapshots 與 21 Equal Weight observations；Trade Ledger missing、
  fills／cost=`0`、weekly=`not_computable_cost_ledger_missing`。工程 contract 已有，真正缺
  Paper execution producer 與真實 fills／partial-fill／override／execution gap。
- Gate 7 Formal 對整個 output 的 `19,942` manifests 做 exact-schema cross-check 後仍為
  `0/3`：causal=`0`、Rule=`0`、PIT=`1` 且唯一 PIT 為 prospective diagnostic-only。
  owner packet 可 review 但 `publication_emitted=false`；shadow-only、alpha 0、broker false 不變。
- performance 的實體容量 blocker 已由使用者授權 retention cleanup 解除；8/30 fresh
  inventory 觀察 D free=`364,003,164,160` bytes（約 338.9 GiB）、PIT／Direct／OOC
  current runs=`8/9/9`，唯讀 inventory=`headroom_ok`。舊 6.56／410.31 GiB status 仍保留為
  歷史觀察；真正剩餘工程 Gate 是 technical production single-writer backup／rollback
  canary，不能為刷新 status 擅自啟動 rebuild。
- 完整 current 判讀見 [Program Status Rebaseline](../06_qa/PROGRAM_STATUS_REBASELINE_2026_08_29.md)，
  cleanup custody／tombstone 見
  [ML Release v4 Storage Retention Cleanup](../06_qa/ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md)。

### 2026-09-13 V4.2 每日推薦 calibration shadow／custody observation

- 既有 recommendation calibration 每日自動學習／受控 shadow path 已留下 bounded runtime
  observation：bounded replay／training、frozen challenger、當日 prediction capture、active
  monitor／rollback、source contract 與 lineage custody 可由既有 receipt／projection 讀回。
  `719cf7a4` 先提交並驗收 C 的 bounded canonical runner／training lineage／cutoff／ML boundary
  階段；`0219d709` 後續完成 C 的 P1 next-day inference／projection provenance bounded
  engineering slice（75 tests、mypy 9 source files、ML guard 509 inspected／0 violations）。
  training／inference source／PIT hash 分離，shared schema／transform compatibility、immutable
  receipt、normal UI UUID→save→exact readback 與 identity conflict fail-closed 均可核對，rule
  selection authority 保留。
- 05:45 learning wrapper 排在 05:40 forward outcomes 之後，週末／官方休市日由
  `OfficialTradingCalendar` skip，不將 historical replay 當 natural evidence；輸出只落隔離
  shadow root。這是已授權的 learning engineering path，不是新的 owner approval request。
- 2026-09-14 父任務以提升權限做 read-only host query，觀察到
  `baldr-forward-outcomes-daily` 與 `baldr-recommendation-calibration-learning-daily`
  均為 TaskPath `\\`、State `Ready`。這是部署狀態觀察，不是本輪重新註冊／重啟，也不
  代表正式 Recommendation／Portfolio promotion、broker execution 或 Formal evidence credit。
- 最新 durable receipt 為 `completed / retain_current`，`decision_reason=
  natural_forward_evidence_receipt_missing`、`natural_matured_sample_count=0`、
  `formal_order_allowed=false`、`shadow_only=true`；因此 learning 沒有調整正式決策。
  完整的市場到個股工作台 requirements／code／gap／acceptance matrix 見
  [終極決策工作台整合缺口矩陣](../06_qa/ULTIMATE_DECISION_WORKBENCH_2026_09_14.md)。
  正式 source acceptance、natural forward evidence、observed cost 與 promotion review
  仍維持 external pending，符合本 Gate 原有「shadow output 不進正式決策層」邊界。

### 2026-09-14 Decision Workbench integration track（V4.1／V4.2 → V5／V6）

本軌與 V4 formal evidence accumulation **並行**；下表是本日 bounded engineering slice
的 scoped 判定，不把工程驗收升格為 V4 formal：

| 增量 | 目前狀態 | 可採認／仍待 |
|---|---|---|
| 每日首屏／content-first | **已驗收**（`0d9d72af`／`cad07762`） | 每日結論與候選／持倉先呈現的唯讀切片可核對；完整資料覆蓋與 formal Advice scope 仍受 evidence Gate 限制。 |
| 市場 → 產業 → 個股 | **工程切片已驗收**（`25544142`） | 真實產業指數強弱與官方 TAIEX 5／20 日基準可讀，並排除槓桿／反向產品型指數；current representative-stock mapping、TPEX／興櫃 coverage 與 historical PIT membership 仍有限。 |
| 每日 evidence／learning view | **P1 provenance bounded engineering 已驗收**（`0219d709`，承接 `421ab844`） | 2026-09-14 臺銀正常 scheduled lane 的 typed candidate／active／capture projection 為 natural sample `0`、`retain_current`；legacy 50bp 是獨立 lane，可能為 `blocked`，不得合併。P1 已分離 training／inference source／PIT hash，核對 shared schema／transform compatibility，保存 immutable receipt，並可由 normal UI UUID→save→exact readback 回查；不把 natural sample `0` 或 receipt 當正式成熟。 |
| C：personalization source／decision evidence | **C-owned bounded wiring 已驗收**（working tree） | `RecommendationService` 實際 clocks／verified label custody → existing save/readback → MainWindow technical ACK；read-only exact projection、cohort／exclusion／late delivery、fixed evaluator、明示 action CLI、fit producer／persistence／CLI 與 real MainWindow process probe 均可核對；fit runner／CLI／calibration／read service `41 passed`，wrong-scope exit `2` fail-closed。正式 D 槽仍無 real scope／delivery／human action／natural outcome；C engineering bounded acceptance 已完成，不把 fixture／replay／`natural sample=0` 當正式樣本。 |
| 成本／排程 | **bounded guard／受控 retry 已驗收**（`086ba60c`／`0aaf0dff`） | 臺銀 `estimated_research_only` 可供研究；首次 05:50 natural run 以 `failed_dependency` 結束，root guard 已修復，受控 retry 為 `completed_waiting_natural_maturity`、natural sample `0`，不等於自然成熟或 observed cost。 |
| Decision → Outcome／Increment A/B/C | **工程驗收**（`53b456a0`／`ffb66c6f`／`5339230f`／`7e029933`／`9a9e778b` + R1 QA） | 唯讀 journey、exact identity、append-only storage、`7e029933` 的跨程序 writer／reader readback、`9a9e778b` 的 `MainWindow DeferredDelete`／busy 單次 close／實際 OS exit `0`、Continuity Review Workbench R1 與 Position Health read model 可核對；完整跨頁一致性及推薦／決策／outcome 追溯整合仍待驗收。 |

#### 2026-09-21 V5 日常操作與可讀性工程 bounded update

工作台、候選／研究／持倉、推薦／回測與主導覽的 content-first／進階分層／錯誤導引已完成 frozen visual review；個股報告的價格 tab 改為按需建立，缺 OHLC 時保留 close fallback。QA 以 30-row isolated fixture、2 repeats、8 個建構 workspace 與 7 次指定切頁保存 before／after；這是工程量測，不外推 production dataset。mandatory UI QA、全域 mypy、py_compile、manifest 與 `299 passed` 精選整合結果已保存，pytest cache permission warning 另列；本 update 仍不關閉 formal Gate、natural evidence、cross-page full integration 或 V6 personalization。

已驗收的內容優先、每日 evidence、typed verifier 與 A storage slice 不必等待 V4 formal
closeout；這些是接下來施工的已驗收基礎：

1. **P0 content-first entry（已驗收 bounded slice）**：每日結論、候選／持倉先出現，三個大型空表折疊；debug state、
   `AdviceDashboardDTO`、完整 hash 收進技術詳情；缺資料轉 `RESEARCH`／`NO_NEW_POSITION`。
2. **P0 daily evidence view（已驗收 bounded slice）**：以既有 `DecisionDeskSnapshot`、Evidence event／outcome、
   forward read model 與最新 shadow receipt，同屏呈現 decision date、maturity、missing／
   pending／retain reason、candidate／champion／rollback identity；不新增 pseudo source。
3. **P0/P1 typed verifier projection（已驗收 read-only slice）**：只有 verifier 已核對的 natural authority receipt
   才能顯示已驗證；`available`、hash、evidence kind 或 shadow label 不能升格。routine daily
   shadow adoption／rollback 依既有已授權 policy 自動執行，不要求每日人工批准。
4. **P0/P1 identity reuse（A/B/C runtime + R1 review loop 已驗收）**：`5339230f` 已保存 append-only
   revision／tombstone 與原始列，並具備 idempotency／optimistic concurrency；`7e029933`
   已補 continuity close／cross-process readback 證據，`9a9e778b` 另補 `MainWindow DeferredDelete`、busy 單次 close、實際 OS process exit `0`；R1 已把同一 identity 接入 Journal reminder
   projection、Workbench exact drilldown 與 shared Journey／controls，不另建平行 decision database。
5. **成本 read model（工程邊界已驗收）**：本輪先消費已提交的臺銀 `estimated_research_only` policy／consumer；
   observed fills、partial fill、broker 對帳與實際滑價是後續 execution-realism／formal Gate。

本輪 2026-09-15 bounded slice 的未完成項（不得視為 V5 closeout）：

- **跨頁一致性及推薦／決策／outcome 追溯整合**：A/B/C 的 continuity runtime close／cross-process writer→reader readback、`5a3ed5db`／`ef594007` Position Health read model 與 `031e11ab` Continuity Review Workbench R1 均已有 bounded acceptance；尚未完成的是把 market→industry→stock→watchlist／portfolio 的同一 identity journey 與推薦／決策／outcome trace 整合驗收，不重做 R1。
- **代表股／歷史產業歸因**：真實產業指數強弱與 TAIEX 5／20 日相對基準已可讀，純產業白名單已排除槓桿／反向產品型指數；current registry 的代表股 mapping、TPEX／興櫃 coverage 與 historical PIT membership／available-time 仍待補齊，因此不能把 current mapping 回填為歷史成分或宣稱完整產業回測。
- **typed 自然驗證權威**：Workbench 只投影既有 learning receipt；若尚未有 verifier 核對的 natural authority receipt，matured sample／active model 不能升格為已驗證或 current champion。2026-09-14 臺銀正常 lane 仍為 sample `0`／`retain_current`，legacy lane 可為 `blocked`；首次 05:50 實際 run 已於 `05:50:03–05:50:05 -07:00` 以 `failed_dependency` 結束，root guard 已由 `086ba60c` 修復，`0aaf0dff` 受控 retry 成功但不等於自然成熟，後續正常排程仍屬觀察線。
- **觀測成交成本**：observed fill、partial fill、broker 對帳與實際滑價仍是後續 execution-realism／formal Gate，刻意不作每日 learning 的前置條件。

V5 是可與 V4 formal 並行的完整決策體驗（每日結論、內容優先 journey、research fallback、
decision／outcome continuity），不是新 Formal version。V6 的 contract、population baseline、
歷史回放、離線 learning／calibration、sample／negative evidence、guardrail 與 rollback 可先
設計；真實 user decision／outcome sample 再決定效果宣稱與 user-level adoption。完整
requirements／code／gap／acceptance 對照見
[終極決策工作台整合缺口矩陣](../06_qa/ULTIMATE_DECISION_WORKBENCH_2026_09_14.md)。

### 2026-09-17 C 線個人化真實來源接線 handoff（working tree）

C-owned bounded slice 已從「尚未接線」更新為可驗收的工程入口：normal
`RecommendationService` producer context 會提供完整 temporal clocks，verified training lineage
會 custody label registry／contract／return basis；`RecommendationSaveRequest`／既有
`RecommendationRepository` 完成 create-only save/readback，MainWindow save 後追加既有 Journal
technical delivery ACK。`PersonalizationReadService`／`PersonalizationProjectionService`、fixed
Decimal/bp evaluator 與明示 `PersonalizationDecisionRecorder` CLI 已可 exact join／診斷，並對
late delivery、missing／pending、cohort denominator 與 legacy action 保持 fail-closed。獨立
real MainWindow process probe 已通過；fit runner／CLI／calibration／read service focused suite `41 passed`，
wrong-scope empty-evaluation exit `2` 且不產生 evaluation／verified binding；source fingerprint artifact
`c_personalization_fit_acceptance_20260917.json` SHA256=`d45033e0ea8a4c418150df685e96d26d7425872a6c633695f0aa752054f0a3d3`。
這些是 C engineering proof，不是正式 personal sample。

目前正式 D 槽仍沒有可驗證的 real scope-linked capture、delivery ACK、human action 或 natural
outcome；fit producer／persistence／CLI 的工程 bounded acceptance 已完成，包含 real-source
shape／scope／lineage／readback fail-closed 驗證。前四項中的
scope／delivery／human action 必須由真實合法使用流程及使用者提供；natural outcome 必須由同一
prediction 的後續官方資料自然成熟；fit artifact 的 formal／natural credit 仍不成立。fixture、
historical replay、Paper、user-declared 與 `natural sample=0` 均不折抵正式效果／adoption Gate。
詳見 [V6 personalization contract plan](../06_qa/V6_PERSONALIZATION_CONTRACT_PLAN_2026_09_15.md)
與 [Personalization read-only source QA](../06_qa/PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)。

### 2026-09-15 Current → Next（基線 `0219d709`）

自然 forward 收集、同 scope calibration 與 05:50 後續正常排程維持獨立觀察線；首次實際 run
已以 `failed_dependency` 結束且 root guard／受控 retry 已處理，`natural_sample_count=0` 仍不
能推導 V4 formal 完工，也不以策略／模型效果逐日單調改善作為驗收條件。
後續工程依序為：

1. **L official taxonomy source chain**：C 的 bounded canonical runner／training lineage／cutoff／
   ML boundary 與 P1 next-day inference／projection provenance 已由 `0219d709` 完成；P1 receipt
   已分離 training／inference source／PIT hash，核對 shared schema／transform compatibility，
   並可由 normal UI UUID→save→exact readback 及 conflict fail-closed 路徑追溯。下一步由 L 補
   官方 taxonomy raw producer／v3／publisher／reader／caller，並完成 PDF／preopen
   completion-time 修正；不以既有 shadow receipt 或 natural sample `0` 折抵自然／正式 Gate。
2. **整合使用流程**：在已驗收的 Position Health、`user_declared`、Continuity Review Workbench
   R1 與 PIT reader／caller bounded slices 上，接通 market→industry→stock→watchlist／portfolio
   的同一 identity read-only journey，完成跨頁一致性及推薦／決策／outcome 追溯的整合驗收；
   不新增平行 DB、不開啟 broker／auto action，也不重做 R1。
3. **V6 evidence-driven personalization**：C-owned contract、population fallback、read-only
   exact projection、fixed evaluator、save／ACK／明示 action、fit producer／persistence／CLI 與
   negative evidence bounded wiring 已可驗收；下一步是累積正式 D 的真實 user decision／natural
   outcome evidence，再決定效果宣稱與 user-level adoption。V6 不保證報酬、
   不自動調倉／下單。

上述順序不重做已驗收的 Advice／calibration／historical replay／daily shadow；任何策略評估結果
只代表該資料與 cohort 下的觀察，不保證每天或每期單調改善。

### Entry Conditions

- Gate 5 對 rule score、bucket、component、label 與 metric 已可判讀。
- Feature / Label / Dataset Registry、purged / embargo split 與 leakage checks 完整。
- Champion baseline、shadow storage、rollback owner 已定義。

### Engineering Deliverables

- Gradient Boosting / learning-to-rank / meta-label / calibration / downside risk 的最小 challenger。
- Model Registry、Calibration Report、Feature Importance、Drift Monitor、Shadow Prediction Store。
- Champion / Challenger comparison 與 Promotion Review package。

### Testing / Evidence

- Purged walk-forward、OOS ranking、calibration、net utility、regime / liquidity stability。
- Feature / label drift、missing feature、model unavailable、rollback to champion。
- Shadow output 不得進 formal Recommendation / Portfolio / lifecycle / scheduler。

### Exit Criteria

- 只能提出「繼續 shadow、拒絕、或建議人工 promotion review」。
- 即使 promotion review 通過，也需另立 formal adapter 計畫與 rollback Gate；不自動上線。


## 2026-07-12 Gate 狀態校正與更新記錄

## Gate 狀態校正（2026-07-12）

- Gate 0 已由 `ae83740` 與歸檔的 `SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md` closeout；後續重構只作 maintenance，不再阻塞產品主線。
- Gate 1 已由 Advice DTO、fail-closed policy、read-only composer 與 Workbench DTO-to-view slice closeout。驗證見 `docs/06_qa/GATE_1_ADVICE_CLOSEOUT_2026_07_12.md`。Gate 1 的完成不折抵 Gate 2 的真實 weekly evidence、Gate 3 的 P0 source acceptance，亦不代表 broker execution 或投資有效性。
- 因此工程順序更新為 Gate 2 → Gate 3 → Gate 4；已完成 Gate 1 的 bounded Advice 仍維持 read-only / paper boundary。


## 更新記錄

- 2026-09-17：C-owned personalization bounded wiring 已在 working tree 完成並驗收：producer
  temporal clocks／verified training label custody、existing Recommendation save/readback、
  MainWindow technical delivery ACK、read-only exact projection、fixed Decimal/bp evaluator、
  明示 action recorder／CLI 與 late／missing／pending negative cases；real MainWindow process probe
  通過。fit runner／CLI／calibration／read service focused suite `41 passed`，wrong-scope empty
  evaluation exit `2` 且無 evaluation／verified binding；五檔 explicit-package-bases mypy clean。
  正式 D 槽仍沒有 real scope／delivery／human action／natural outcome；不把 fixture／replay／
  `natural sample=0` 當正式 evidence，不改 scheduler、broker 或正式 order 邊界。
- 2026-09-15：以已提交 `719cf7a4` 校準：C bounded canonical runner／training lineage／cutoff／
  ML boundary 已驗收（88 tests、508 files guard 0 violations、production-scoped mypy），P1
  next-day inference／projection provenance 與 L official taxonomy source chain 尚待完成；
  Position Health、`user_declared`、Continuity Review Workbench R1、PIT reader／caller 與 BankTaiwan
  受控 retry 已各自有 bounded acceptance。首次 05:50 實際 run 的 `failed_dependency` 已由 root guard
  修復，受控 retry 成功但後續自然排程仍觀察；下一順序收斂為 C＋L → 整合使用流程 → V6 contract／離線設計與 real-user 驗證，不改
  V4 formal、V5／V6 定位或正式交易邊界。
- 2026-09-15（後續校準）：`0219d709` 已完成 C P1 next-day inference／projection provenance
  bounded engineering acceptance；`9a9e778b` 已完成 MainWindow `DeferredDelete` teardown、busy 單次
  close 與實際 OS process exit `0`。L source chain、跨頁整合、自然 evidence 與 V4 formal Gate 仍待驗收。
- 2026-09-14：補上 Decision Workbench 的機率／rank 分離、來源與 evidence status 唯讀詳情，
  交付 V4.1／V4.2 engineering 與 V4 formal／V5／V6 分流的完整缺口矩陣；實機排程只讀觀察
  為兩個 daily task `Ready`，最新 receipt 為 `retain_current`、natural sample `0`，不改
  formal／broker 邊界。
- 2026-09-13：完成 V4.2 每日 recommendation calibration shadow learning／controlled adjustment
  engineering loop、active monitor／rollback、實際 source contract／availability／corporate-action／
  after-cost gates、05:45 wrapper 與 QA；明確保留 formal allocation、broker 與 production evidence
  external gates。
- 2026-09-06：將八卡工程增量映射到既有 Gate，保留真實 fills、來源接受、自然時間、具名 review 及正式遷移邊界。

- 2026-08-29：完成整體 Gate rebaseline 與 owner-authorized ML release_v4 retention cleanup 紀錄；三個主要 root 釋放約 `403.95 GiB`、D free 約 `410.31 GiB`，各保留 6 個完整 PIT／Direct／OOC run 與有效 current pointer。這解除實體 headroom blocker，但不改 Evidence credit、P0 acceptance、Paper fills、Formal 0/3、alpha 0、scheduler／broker 或 technical production canary Gate；cleanup 前的 6.56 GiB 條目保留作歷史。
- 2026-08-28：新增唯讀 `scripts/qa_technical_indicator_latency.py`、full-batch／isolated writer、real calculator staging process-pool、worker crash recovery／queued cancellation、parent single-writer integration staging 與 broker 離線 bounded-fetch acceptance probes；Broker CSV writer 加上 process-local single-writer lock。technical／broker pool 目前只在 protected-root 外 staging 以 bounded in-flight、retry、parent single writer 與 fail-closed checks 證明形狀；technical batch 的 production feature flag／scheduler lifecycle 已接上且預設關閉，真實 broker／Selenium 平行抓取仍未啟用；後續須補 owner-approved backup／rollback、technical canary 與真實 broker canary／rate-limit evidence。
- 2026-08-28：新增 `scripts/build_performance_canary_owner_packet.py`，把 technical preview、worker recovery／single-writer staging、broker real HTTP、Direct/OOC capacity preflight 與 retention inventory 收斂成 `performance-canary-owner-review.v1`。實測 packet status=`needs_named_owner_reviewer`；technical production canary 仍 `confirmation_required`、Direct/OOC free `6.56 GiB < 20 GiB`、broker production fetch pool 維持關閉。此 slice 只建立 TEMP candidate handoff，不啟動 worker／pool、不刪除或搬移 run、不寫正式資料；下一步是 owner capacity／canary／rate-limit review，而非直接提高 thread 數。
- 2026-08-28：`inspect_program_readiness.py` 新增 `--performance-owner-packet`，Data Update／readiness bounded projection 會顯示 owner packet 的 status 與待處理 lane 計數；invalid schema／unsafe flag fail-closed，不把 `needs_named_owner_reviewer` 或 `ready_for_owner_review` 視為 production 授權。
- 2026-08-28：以 host 證據重算含 performance owner packet 的完整 readiness artifact（status=`action_required`、performance=`partial`、owner review 待處理 `3/4`）；此輸出只供 `PROGRAM_READINESS_ARTIFACT` 唯讀顯示，不改任何正式 gate、worker／pool 或資料寫入。
- 2026-08-28：新增 `build_formal_input_owner_packet.py` 唯讀 owner handoff；從 bounded Formal candidate inventory 產生 `formal-input-owner-review.v1`，固定三項 expected input 的 owner／reviewer review slot 與 candidate metadata，輸出只能位於候選根目錄外，且固定 `formal_ready_input_count=0`、`formal_oos_allowed=false`、`candidate_only=true`、`write_performed=false`。這把候選盤點轉成可交接清單，但不選 candidate、不發布正式 manifest、不授予 Formal／promotion／broker credit。
- 2026-08-28：Data Update quick runner 新增 `data-update-status-history.v1` append-only JSONL（`--history-path`，預設與 latest status 同目錄），UpdateView 時間軸新增最近執行歷史表；只保存真實 runner 的 running／terminal status 摘要，既有 latest 不回填，未改資料、Evidence、Formal、scheduler 或 broker 邊界。
- 2026-08-27：新增 `scripts/append_source_acceptance_decision.py` 的 preview／明確確認 append foundation；applying decision 必須綁定 `ready_for_owner_review` intake 與 evidence ids，registry 只能位於 `DATA_ROOT` 之外，且 append 不改變 downstream／formal／scheduler／broker fail-closed 邊界。
- 2026-08-27：Update 大型每日合併與 SQLite CSV 匯出改用 `ProgressTaskWorker` 與批次進度回報；合併回報檔案／讀取批次／整合檔 chunk，匯出先以 query-only count 建立預估筆數並回報已處理筆數。取消仍維持檔案／資料批次安全邊界，不改變原子提交與既有資料保留規則；合併新增單檔內讀取批次取消檢查，仍不做逐列中斷。
- 2026-08-27：Update 增量合併在沒有新 CSV 時改回傳結構化 `no_op=true` 與既有筆數／最新日期，UI 明確顯示「資料已是最新」且不先建立備份，避免把 no-op 誤報成一般重新合併或產生不必要副作用。
- 2026-08-28：Runtime staging write probe 改用正式 `ResearchRunRepository` schema，於非正式暫存 DB 驗證 insert／讀回／rollback／清理並輸出 `registry_transaction_succeeded`；仍禁止指向正式 `DATA_ROOT`／`OUTPUT_ROOT`，不授予 scheduler／formal credit，也不宣稱正式 Registry ACL 已通過。
- 2026-08-28：新增 guarded `scripts/qa_research_registry_production_canary.py`；預設只讀正式 Research Registry，只有 owner approval、無並行 writer acknowledgement 與 explicit confirm 才會對正式 DB 做唯一 canary row 的 insert／read-back／rollback，並用 content hash、row count 與 `quick_check` 驗證無 durable change。backup 僅存 OS TEMP，失敗保留供人工比對；尚未執行 production write，因此 Runtime transaction blocker 仍在。
- 2026-08-28：`inspect_program_readiness.py` 新增唯讀 `--ml-direct-chain-status` 輸入；Direct/OOC `blocked_insufficient_storage`／已觀察的 `No space left on device` 會進入 performance lane 與 execution order，明確提示容量／保留策略，不啟動 worker、不刪除 immutable run。
- 2026-08-28：`inspect_program_readiness.py` 新增唯讀 `--runtime-readiness-json`；可載入允許 host context 產生的 `runtime-environment-readiness.v1`，避免 sandbox token 的正式檔案 handle `PermissionError` 覆蓋已核實的 host readiness；schema 不符即 fail-closed，仍不進行正式 Registry transaction。
- 2026-08-28：新增 `scripts/inspect_ml_storage_retention.py` 唯讀容量／retention inventory；只掃描明確根目錄的 metadata，輸出大目錄、manifest status 與可逆 owner review 候選，固定 `automatic_delete_allowed=false`，不刪除／搬移 immutable run。這讓 Direct/OOC 的 20 GiB headroom blocker 有可審核的容量證據，而不是直接重跑或猜測清理。
- 2026-08-28：Evidence scheduler readiness evaluator 新增 `evidence-production-scheduler-approval.v1` fail-closed gate；即使 source coverage 與 working-copy smoke 通過，仍需具名 owner、有效期限與 source／dry-run／backup／rollback／recovery checks 全部通過的 approval artifact，才可能回報 `operational_production`，避免 read-only readiness 自動放行 production write-mode。
- 2026-08-28：Formal readiness 對缺失的 `formal_prospective/clock-YYYYMMDD` path 新增 configured clock／training cutoff stale hint；只改善 owner handoff 診斷，不掃描或自動改接其他 clock，也不把 prospective bytes 升格成正式 input。
- 2026-08-27：Runtime formal path readiness 補上既有 logger／Research Registry 的不寫入 write-handle probe；`os.access` 與實際開啟權限不一致時，狀態固定降級為 `attention`，保留 formal ACL／鎖定 blocker。
- 2026-08-27：Runtime／MainWindow 窄版 UX 補強：長路徑診斷與 status strip 不再貢獻過大的水平 minimum hint；主視窗明確保留 320px compact 下限，Runtime 小於 720px 改用垂直治理欄並提供內容捲動。此為 presentation／可觀測性改善，不解除任何 formal、scheduler 或資料權限 blocker。
- 2026-08-27：Data Update 窄版 UX 補強：更新工作區加入垂直捲動，來源導覽移到上方，核心狀態卡改雙欄、候選卡單欄、操作按鈕直列；只修正 presentation，不改 update worker、SQLite sync 或資料來源 gate。
- 2026-08-27：Paper Portfolio readiness／weekly evidence／Equal Weight builder 新增台北交易日 future-date look-ahead guard；raw future snapshot 只保留診斷，current projection 改用最後一筆安全 snapshot，週報／benchmark builder 遇到 future period 直接降級或拒絕。Equal Weight builder CLI 也統一 UTF-8 stdout／stderr，Windows CP1252 可正常顯示 `--help` 與拒絕診斷。
- 2026-08-27：修正每日 Paper／Decision Desk 排程的 cutoff 選擇；排程入口改用最近已到達的台北 08:30，Paper writer 對明確未到達的 `--decision-at` 在開啟資料庫前回報 `skipped_future_decision`，避免重複產生 future／look-ahead row。既有正式 raw row 不刪除、不回填，仍需 owner 稽核。
- 2026-08-27：新增 `scripts/inspect_p0_intake_readiness.py` 唯讀 P0 source intake validator 與 13 列候選範本；它驗證 dossier schema／型別／分母／secret-like 欄位／安全旗標，將 `deferred`、`ready_for_owner_review`、`invalid_input` 分開投影，並固定不建立 decision registry、不授予 downstream eligibility。這是外部輸入的可重跑接入口，不是 source acceptance closeout。
- 2026-08-28：新增 `scripts/build_p0_intake_from_audit.py`，將既有 `p0-source-evidence-audit.v1` 的 machine row counts／payload hash／status 安全轉成 13 列 candidate intake，所有 owner／license／publication／PIT 欄位仍 fail-closed 為 `unverified`／`requires_review`；輸出限定 OS TEMP，不建立 registry、不改正式資料，也不授予 downstream eligibility。
- 2026-08-28：P0 source-evidence audit 的 MOPS verified-artifact 分支補上 validated artifact 的 raw／accepted／quarantine／blocked counts，讓 candidate intake 保留真實 coverage／row-conservation denominator（不再把已驗證 artifact 誤顯示為 `0/0`）；此修正不改 source acceptance、license、PIT authority 或 downstream eligibility。
- 2026-08-28：以允許 HTTPS 的 host context 重跑 P0 bounded live probe；12/13 官方路徑實際 observed、13/13 payload hash 存在，raw=`91,127`、accepted=`89,750`、blocked=`1,377`，再轉成 candidate intake／owner packet。這證明替代 acquisition route 可取得 machine evidence；publication timestamp、decision-time、license 與 owner acceptance 仍維持 fail-closed。
- 2026-08-28：MOPS EZSearch 季報 availability candidate 改支援 1–31 天 query window 與最多 3 次 error-only retry，manifest 保留每段 query window／attempt lineage；host context 以 40 個 7 天窗口重抓 2026-05 雙市場 F26–F29，取得 `7,473/7,473` events／projections，validator `accepted=7,473`、diagnostics=`0`。既有 raw 財報仍缺全量 explicit available-date，backfill dry-run `normalized=0`，所以此 evidence 仍只供 research candidate，未寫正式 mapping／SQLite 或解除 P0 source acceptance／Formal gate。
- 2026-08-28：將上述 chunked MOPS candidate 接回 P0 source-evidence audit；13/13 source rows 有 machine evidence，MOPS verified-artifact row conservation=`7,473/7,473`，並產生 13 列 candidate intake 與 Owner packet。validator 維持 `deferred`、owner-review-ready=`0`，所有 artifact 只在 TEMP；此步驟只增加可追溯 machine evidence，不把部分公告 availability 當成全量 raw available-date、source acceptance 或 Formal credit。
- 2026-08-28：補齊既有 performance／runtime／scheduler／freshness artifact 後，以 chunked MOPS audit 重算 unified readiness；新報告仍為 `action_required`，但 performance 不再因漏帶 baseline 而產生假性缺口，準確保留 Direct storage 與 technical production single-writer canary blockers。這是 read-model 更新，不改任何正式資料或 gate。
- 2026-08-28：歷史 MOPS EZSearch `2024-Q1` query 以 40 個 7 天窗口取得 `6,933` valid availability events／projections；8 筆缺 `CTIME` 的歷史列改為逐列 quarantine，artifact 以 `degraded` 保留有效資料與錯誤計數。對現有 raw 財報做 backfill dry-run 得到 `normalized=496`、`missing_available_date=1,645,059`；CLI 改為 bounded diagnostics，完整計數仍保留在 plan，`ready_for_apply=false` 與正式 mapping／SQLite 寫入邊界不變。這讓後續可按歷史窗口繼續擴充 coverage，而非把 schema drift 誤判成整批失敗。
- 2026-08-28：backfill 讀取器新增多份 `--availability-file` 累積能力；相同完整 candidate row 去重，同一 natural key 的不一致 provenance 經 revision validator fail-closed。2024-03／04／05 三份 MOPS candidate 合併唯讀盤點得到 `35,735` normalized rows，剩餘 `1,609,820` rows 缺 explicit available-date；這把「多來源補資料」變成可重跑、可稽核的 bounded path，仍不代表 mapping／SQLite 可直接 apply。
- 2026-08-28：以 retroactive baseline 加三份 MOPS candidate 做 hybrid planner dry-run，raw／normalized=`1,645,555 / 1,645,555`、diagnostics=`0`；records quality 分布為 official MOPS `observed=35,735`、baseline `degraded=1,609,820`。這提供完整 schema coverage 的安全 fallback，但 roadmap 仍要求逐段提高 official announcement／PIT coverage，不能把 baseline rows 升格成 Formal evidence。
- 2026-08-28：backfill plan／CLI 新增 `quality_counts`，讓完整 schema coverage、records quality 與正式 source acceptance 在同一份 dry-run 輸出中分開呈現；`ready_for_apply` 不再被解讀為 PIT／Formal gate 已通過。
- 2026-08-28：MOPS availability candidate 由 2024-Q1 繼續回溯至 2022-Q3（2023-05／08／11、2023-03、2022-11），hybrid planner 的 official observed raw records 提升至 `225,643`，degraded baseline 降至 `1,419,912`。官方 `status=fail` 空回應與 network／parser error 維持分流，未因部分月份成功而宣稱全期間 coverage 或解除 gate。
- 2026-08-28：再加入 2022-Q1／Q2 公告窗口（2022-05／08）；hybrid planner official observed raw records 提升至 `301,489`、degraded baseline 降至 `1,344,066`，全量 normalized／diagnostics=`1,645,555 / 0`。下一段按同一流程回溯 2021-Q4，仍維持 candidate-only 與正式 apply confirmation 邊界。
- 2026-08-28：2022-03 公告窗口（主要對應 2021-Q4）再取得 `5,966` valid events，hybrid planner official observed raw records 提升至 `335,620`、degraded baseline 降至 `1,309,935`；下一段按同一流程回溯 2021-Q3，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2021-11 公告窗口（主要對應 2021-Q3）再取得 `6,461` valid events，hybrid planner official observed raw records 提升至 `373,361`、degraded baseline 降至 `1,272,194`；下一段按同一流程回溯 2021-Q2，仍維持 candidate-only 與正式 apply confirmation 邊界。
- 2026-08-28：2021-08 公告窗口（主要對應 2021-Q2）再取得 `6,929` valid events，hybrid planner official observed raw records 提升至 `412,613`、degraded baseline 降至 `1,232,942`；下一段按同一流程回溯 2021-Q1，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2021-05 公告窗口（主要對應 2021-Q1）再取得 `6,349` valid events，36 個 query 有資料、4 個官方無資料；hybrid planner official observed raw records 提升至 `449,464`、degraded baseline 降至 `1,196,091`；下一段按同一流程回溯 2020-Q4，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2021-03 公告窗口（主要對應 2020-Q4）再取得 `5,989` valid events；hybrid planner official observed raw records 提升至 `484,302`、degraded baseline 降至 `1,161,253`；下一段按同一流程回溯 2020-Q3，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2020-11 公告窗口（主要對應 2020-Q3）再取得 `6,373` valid events；hybrid planner official observed raw records 提升至 `521,411`、degraded baseline 降至 `1,124,144`；下一段按同一流程回溯 2020-Q2，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2020-08 公告窗口（主要對應 2020-Q2）再取得 `6,610` valid events；hybrid planner official observed raw records 提升至 `559,082`、degraded baseline 降至 `1,086,473`；下一段按同一流程回溯 2020-Q1，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2020-05 公告窗口（主要對應 2020-Q1）再取得 `6,094` valid events；hybrid planner official observed raw records 提升至 `594,642`、degraded baseline 降至 `1,050,913`；下一段按同一流程回溯 2019-Q4，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2020-03 公告窗口（主要對應 2019-Q4）再取得 `5,864` valid events；hybrid planner official observed raw records 提升至 `630,985`、degraded baseline 降至 `1,014,570`；下一段按同一流程回溯 2019-Q3，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：2019-11 公告窗口（主要對應 2019-Q3）再取得 `6,444` valid events；hybrid planner official observed raw records 提升至 `670,943`、degraded baseline 降至 `974,612`；先重跑 unified readiness，再決定是否回溯 2019-Q2，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：歷史 MOPS coverage 回溯至 2019-Q3 後，以正確 real process-pool／broker canary baseline 重算 unified readiness；報告仍為 `action_required`，但只保留 P0 外部治理、Evidence pending review、Paper cost/fills、Formal inputs、Direct storage 與正式 technical canary blockers，仍不改正式 mapping／SQLite 或 Formal gate。
- 2026-08-28：Evidence weekly sidecar 新增唯讀 `scripts/build_evidence_weekly_approval_input.py`，把 8 筆 `pending_human_review` collection 轉成獨立 `evidence-weekly-approval-input.v1` owner／reviewer 交接包；packet 會驗證 source path／SHA-256、payload 與錯誤欄位，並固定 candidate-only、無寫入、無 Formal credit。這讓下一步從「找不到資料」收斂成外部具名 owner／reviewer 逐期決策；尚未產生 approved projection，不能直接餵入 Formal 或 scheduler。
- 2026-08-27：Pre-V2 readiness 的 Workbench、`inspect_pre_v2_readiness.py` 與 `inspect_simulated_phase_progress.py` 統一讀取 `WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH`（亦支援明確 projection path）；projection 只供 UI／readiness 揭露，不授予 formal credit，避免不同入口顯示不同 weekly Gate 數字。
- 2026-08-27：Decision Desk／Pre-V2／Workbench／Evidence source coverage 的 current snapshot 查詢加入台灣市場今日上限；future row 只留 raw 診斷並阻擋 current evidence。Evidence source coverage 與 snapshot inspector 改用 query-only 讀取，避免正式唯讀 DB 被 writer repository 初始化 schema。
- 2026-08-27：UpdateView 日期控件統一以台灣市場日期服務初始化；localized `不可用` 狀態改判異常；全域狀態檢查失敗時，六個核心與三個候選來源 inline 摘要同步清除舊內容並保留共同錯誤原因，候選來源分頁也會投影自己的檢查結果。補上 UI regression 與全量 pytest 證據，未改資料更新／SQLite 寫入契約。
- 2026-08-27：Recommendation Explain 補上 PatternScore rolling confirmation evidence；結果列保存 `PatternNames`／`Pattern_Signal`／`PatternAgeDays`，ReasonEngine 只消費已確認資料，無具體名稱時不從分數臆測型態。此為可追溯性修補，不改 score、交易訊號或任何 formal Gate。
- 2026-08-27：Recommendation 與四個策略 executor 移除未使用的全歷史 PatternAnalyzer 預掃描，避免和 ScoringEngine rolling path 重複計算；策略訊號與 score contract 維持不變。
- 2026-08-27：Data Update SQLite sync 修正欄位別名與重複條件處理；日期／股票代號／股票名稱的受治理 aliases 會先在副本上映射至 canonical schema，日期與四碼代號格式一致，raw CSV 不被改寫，缺必要欄位仍 fail-closed。
- 2026-08-26：Gate 3 先完成 13-source P0 Data Source Control Center 唯讀 read model、CLI 與 Evidence/Research Console 可見投影；只收斂 contract／audit／decision evidence，仍維持 auto-accept、downstream eligibility、formal OOS 與 production scheduler 關閉。
- 2026-08-19：新增 Gate 7 prospective restart execution lock；定案新未來 clock、Codex Rule Champion proposal、TWSE／TPEX 官方產業來源與 Broker 關閉邊界。
- 2026-07-12：校正 Gate 0 / Gate 1 closeout；下一工程 Gate 為真實 Evidence Operating Loop，不將 Advice 契約完成誤寫為 evidence、scheduler 或投資有效性完成。
- 2026-07-11：依 Post-Refactor 產品主線重寫為六個月 Gate；納入 Safe Refactor Closeout、Daily Usable Advice、Real Evidence Loop、P0 Data、Portfolio Coach、Signal Pruning、Position Health / Exit 與 conditional ML Shadow。

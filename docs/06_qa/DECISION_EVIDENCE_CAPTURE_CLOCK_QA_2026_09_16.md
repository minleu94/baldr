# Decision Desk／Evidence capture 真實時鐘 QA（2026-09-16）

## 結論

已修正每日 evidence capture 的 caller clock 錯誤。原本 05:25 Pacific 執行的
`baldr-decision-evidence-capture-daily`，會用「最近已到達的台北 08:30 cutoff」
同時充當 `decision_at`；因此台北 20:25 的 EOD capture 被標成 08:30 盤前決策。
現在拆成兩個不同語意：

- `calendar_decision_at`：只作為已到達的台北 08:30 日曆選擇器。
- `decision_at`、`captured_at`：本次實際 aware runtime clock。
- `as_of`：明確的來源日期；不由 capture clock 改寫 source availability。
- 台北 13:30 後的預設模式是 `eod_research`，固定
  `research_only=true`、`preopen_authority=false`、`natural_authority=false`。

既有錯誤 receipt、既有 snapshot/event 與正式資料沒有被回寫、回填或重標為盤前；
後續正常排程只建立帶有正確時間 context 的新 identity，舊紀錄保留供稽核。

## 原始問題與 artifact readback

實際 receipt：

```text
D:\Min\Python\Project\FA_Data\output\scheduled\decision_evidence_capture\latest_status.json
```

唯讀讀回的關鍵值是：

```text
status=passed
checked_at=2026-09-16T20:25:01+08:00
decision_at=2026-09-16T08:30:00+08:00
decision_date=2026-09-16
events_inserted=1714
events_duplicates=0
events_failures=0
```

這證明不是「沒有 capture」，而是 caller 把日曆選擇器誤當成實際決策時鐘；
這筆歷史 receipt 不作為真實盤前 authority。

同一日上游 recommendation artifact 的唯讀來源為：

```text
D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260916_051003.json
created_at=2026-09-16T05:10:03-07:00  # 台北 20:10
```

上游 `source_created_at` 與 DDD 本次約台北 20:25 的 `captured_at` 是不同欄位；
capture clock 不會覆蓋上游來源可用時間。

測試用隔離 DB 的 artifact readback 也已確認：保存後重新讀取的
`capture_context` 通過完整 custody hash，snapshot 的 `hash_payload()` 使用
去除 retry-varying `captured_at` 的 semantic identity；重試只改 `captured_at` 會
duplicate，改 `decision_at`／`as_of` 不會靜默合併。

## 驗證範圍

已追蹤的 call chain：

```text
scripts/scheduled/run_scheduled_decision_evidence_capture.py
  -> scripts/capture_decision_desk_snapshot.py
  -> scripts/capture_evidence_events.py
  -> EvidenceCaptureRequest
  -> EvidenceCaptureService / EvidenceEventService
```

已完成的安全檢查：

- aware `decision_at`／`captured_at` 必須含時區，且 `captured_at >= decision_at`。
- `as_of` 不得晚於 decision availability、`decision_date` 或決策時點的台北自然日。
- `preopen`／`natural` 宣告直接拒絕；`eod_research` 在台北 13:30 前拒絕。
- semantic identity 忽略可合理變動的 retry `captured_at`，但綁定 decision／as-of、
  mode 與 authority flags。
- 完整 context 另以 custody hash 保存；既有 receipt 若 hash 或 semantic identity
  被竄改，重跑 fail closed。
- child 必須回讀相同 temporal receipt 與 persisted context；缺欄、hash 不符或
  identity 不符時，外層停止後續 event capture。
- date-only 舊 caller 保持相容，但明確輸出
  `temporal_precision_unproven`，不補假造 08:30。

## 最新非零／異常 scheduled receipt 分類

範圍是正式 D 槽 scheduled root、repository 的正式 formal／forward scheduled
root，以及 repository `output\scheduled`；排除了 `luna_*`、pytest 暫存與其他測試
fixture。判讀以 receipt 的 nested status、blocker、source/provenance 與 maturity
欄位為準，不只看 exit code。

| Receipt | 讀回狀態與證據 | 分類／嚴重度／信心 | 最小修復方向 |
|---|---|---|---|
| `D:\Min\Python\Project\FA_Data\output\scheduled\data_freshness\latest_status.json` | `status=degraded`；monthly／quarterly expected period 不可用，且 `fundamental.current_monthly_observations`、`current_statement_observations`、`institutional_flows`、`credit_transactions` freshness degraded。 | 外部資料 freshness／來源契約缺口；High／高 | 補齊來源 partition 與 freshness receipt，再重跑 freshness；不以 capture clock 掩蓋缺日。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\evidence_pipeline_dry_run\latest_status.json` | 外層 `status=failed`、`exit_code=2`，但 `pipeline_overall_status=degraded`、`pipeline_exit_code=0`、`pipeline_errors_count=0`；health source 有 `health_baseline_date_mismatch`，且 PIT condition、forward thesis binding、Decimal metrics 與 portfolio/risk quality 未就緒。 | 外部來源／跨 pipeline 契約缺口，屬預期 fail-closed，不是 crash；High／高 | 先補正同日 health baseline 與受控 source receipt／binding；在完整來源前維持 degraded，不寫交易或 Formal authority。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\ml_raw_pit_refresh\latest_status.json` | `status=failed`、`builder_returncode=2`、`error=raw_pit_builder_failed:2`；nested quality `quarantine_required`，candidate `17,857`、invalid price `1,474`、unavailable `15,445`、route missing `16,969`，`repair_performed=false`，source receipt time 未提供。 | 外部／來源完整性與 custody 契約缺口；Critical／高 | 先做 canonical daily CSV 與 SQLite bounded reconciliation、補 source receipt／expected universe；維持 quarantine，不重跑以洗掉 invalid rows。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\official_market_events\latest_status.json` | `status=failed`、`failure_class=official_market_event_backfill_failed`；`TWT49U` event 6949（2025-12-10）為 unlinked revision conflict。已知比對中 1357／1358 經濟欄位相同，差異是名稱 `沛爾生醫-創` → `沛爾生醫*-創`。 | 工程／資料契約邊界；High／中高（僅能外推此 bounded case） | bounded display-name comparator 已完成並通過隔離／實際 raw read-only full-chain；經濟內容或 identity 不全等時仍 blocked；不覆寫 raw／SQLite／last-known-good。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\ml_promotion_evidence\latest_status.json` | `status=blocked`；`formal_ooc_dataset_full_market_not_ready`，缺 causal non-cash ledger、formal rule champion snapshot history、PIT sector membership。 | 外部 formal input／契約缺口；Critical／高 | 形成完整 full-market OOC、ledger、rule history、PIT custody 後再跑 preflight；alpha 與 Formal gate 維持 0。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\ml_direct_chain_maintenance\latest_status.json` | `status=failed`、`returncode=1`、`maintenance_lock_state=missing_or_invalid`；容量 preflight 通過，但 direct log 最新訊息為 `ValueError: direct checkpoint computation dependency snapshot is missing`。 | 工程／provenance blocker；High／高 | 恢復並驗證既有 dependency checkpoint snapshot 與 immutable hash，再做 bounded maintenance；不得以目前 hash 代替遺失 provenance，也不清理重建。 |
| `C:\Projects\PythonProjects\technical_analysis\output\formal_daily_publications\scheduler\latest_status.json` | `status=candidate_only`、`exit_code=2`；20 個 blocker，含 formal ledger／rule history／sector source、common identity readback、independent expected universe、license scope 與 sidecar publication 缺口。 | 外部 formal 契約缺口，混有 candidate custody 尚未被承認；Critical／高 | 依 blocker 清單補齊 source、license acceptance、expected universe 與三 consumer readback；candidate 不得提升為 Formal。 |
| `C:\Projects\PythonProjects\technical_analysis\output\formal_daily_publications\scheduler\pit_sidecar\latest_status.json` | `status=blocked`；`verified PIT denominator is missing for 2026-09-17`，且 `formal_ready=false`、`formal_consumer_compatible=false`。 | 外部 PIT denominator／來源缺口；High／高 | 取得獨立 denominator 並完成 readback；缺件期間只保留 blocked receipt，不重抓同日已保存 archive。 |
| `C:\Projects\PythonProjects\technical_analysis\output\v4_ml_daily_derived_shadow_real_v2\scheduled\ml_allocation_forward\latest_status.json` | **初始 2026-09-16 bounded readback（修復前）**為 `status=blocked_child_exit`、`child_returncode=1`、`child_status=failed_read_only_integrity`；nested maturity 雖 `completed`，但 `pending_is_normal_wait=false`、`matured_observation_count=0`、`partial_outcome_count=1`、`evidence_status=insufficient_evidence`。child 的 `shadow_evidence` 另報 `ValueError: paper ledger weekly turnover is not derivable from snapshots`；隔離 paper ledger 有 2026-09-08、同一 `paper-main` 的 8 筆交易（filled／partial／rejected，含 `turnover_bp`、`source_event_id`、cost）。 | 工程／read-only integrity 與 paper-ledger／snapshot 對帳契約 blocker，不是自然成熟等待；High／高。另兩份 wrapper 顯示 `source.database`／release unchanged=true，但 `paper_state_db` 的 mtime 改變（size 仍 28672），因此需要明確區分合法 preopen writer overlap 與未授權變更。 | 已在 repository-isolated code／fixture 完成 bounded 修復與 readback；正式 scheduled receipt 尚未重跑，不能把它當作本輪 production pass。不可直接相加交易或把 maturity 0 誤算成自然等待。 |
| `C:\Projects\PythonProjects\technical_analysis\output\scheduled\official_market_events\latest_status.json` | `status=failed`、`failure_class=tpex_official_endpoint_unavailable`。 | 外部官方 endpoint 暫時不可用；High／中高 | 依既有 retry／source receipt policy 重試並保留 last-known-good；endpoint 未可驗證前不發布新 official vintage。 |
| `C:\Projects\PythonProjects\technical_analysis\output\scheduled\twse_quote_observation\latest_status.json` | `status=durable_partial`，無非零 child exit，但不是完整 capture。 | 外部來源／部分觀測；Medium／中 | 補齊缺失 session observation 與完整 custody，再由 consumer 判斷是否可用；不把 partial 當完整市場 session。 |

### Official TWT49U 顯示名稱修訂 bounded QA（2026-09-16）

本段只處理 6949（2025-12-10）的受限 display-only case。D: 正式資料全程唯讀，
沒有執行 producer、沒有改 `latest_manifest.json`，也沒有改 SQLite、既有 formal
canonical history 或 last-known-good。實際比對的兩個 raw 是：

```text
D:\Min\Python\Project\FA_Data\output\release_v4\official_market_events\runs\official-market-events-d51d54fa09f8f7e03f9d7fbd\raw\twse.TWT49U.ex_right_dividend_result\year=2025\response.json
D:\Min\Python\Project\FA_Data\output\release_v4\official_market_events\quarantine\failed-1f4796d29efc4e5185b9b22f764fb7d1\raw\twse.TWT49U.ex_right_dividend_result\year=2025\response.json
```

唯讀 raw hash 分別為 `sha256:fb8ad7e07eb7c0b83bb944a5bd7398d7d0f2f1d783dd7589e59234dbc736044b`
與 `sha256:0ec84940f2f22a2de21532ab3d488493ee07efb4b57441f6e1dcaaab24a3d407`；第一個
路徑的正式 manifest／pointer 未變。兩列的 source record 只有 `股票名稱` 差異：
`沛爾生醫-創` → `沛爾生醫*-創`；除價格、日期、代號、結果欄位與 source identity
外，經濟投影 hash 相同。

在隔離 output root 以兩版實際 raw 順序建立同一條 publication chain，readback 結果如下：

| Check | Result |
|---|---|
| 第一版 → 第二版 canonical | `1358 → 1359`，`new_event_count=1` |
| 6949 revision chain | 舊 `sha256:8b4e6154f61ced9a11c94960de30360190d8279af162066a4002845bcfe01e88`，新 `sha256:b45ca41c345e238fa695a08d73ebf2ffdb0b2750d78c78d557bd6e6a92a5f808`；`revision_kind=display_name_only`、`revision_sequence=1`、`supersedes_revision_id`／`display_revision_of` 指向舊版 |
| Economic／availability boundary | `economic_content_hash` 相同；舊 `available_at=2025-12-10T23:59:59+08:00`，新版使用 raw `retrieved_at=2026-09-16T11:50:34+00:00`；兩列 ambiguity flag 均為 false |
| Raw custody | 第二版 `raw_index` 有 2 個 response、`lineage_response_count=1`，舊／新 hash 都可從檔案重算 |
| Adjustment custody | 兩個 source revision 都保留相同 factor／economic hash；`prospective_only=true`、`historical_pit_eligible=false` |
| Portfolio ML historical reader（`training_as_of=2026-01-01`） | canonical／label ledger observed=`1359`／`1359`；6949 只出現舊名稱，eligible effective date 只有 1 個 |
| 第三次 identical replay | `new_event_count=0`、canonical revision 仍為 2、raw response 仍為 2，沒有 chain／lineage 膨脹 |

因此 adjustment sidecar 雖保留每個 vintage 供追溯，既有 reader 的 effective-date
聚合仍只有一個經濟事件；現有 return／label-window consumer 只產生一個 exclusion
效果，且本路徑不直接乘 adjustment factor。新版顯示名稱是 2026-09-16 才觀測到的
prospective observation，不會成為 2025 historical `as_of` 的已知名稱。

39 項 official availability／adjustment focused tests 已通過，包含同名經濟欄位變更、
未連結 revision、raw hash／reader chain、與第三次 identical replay；不支援的 endpoint／
schema、不同價格／日期／代號／source identity、同名經濟變更與 ambiguous predecessor
仍維持 fail closed／quarantine。

### Forward Paper ledger／preopen writer overlap bounded QA（2026-09-16）

本段針對前述初始 Forward child blocker 做 repository-isolated 修復驗證；沒有啟動
正式 scheduler、沒有寫入 D: 正式資料或既有 production output。舊的實際
`paper_trade_ledger.sqlite` 仍是 2026-09-08 的 8 筆歷史 rows（filled／partial／rejected，
gross filled amount 合計 `7457`），沒有可供 consumer 驗證的
`paper_trade_transitions`；因此它仍應被 blocked，不能把 snapshot 事後猜成 transition。
唯讀 state readback 也確認 2026-09-08 → 2026-09-09 的 T+1 數量／現金變化已反映在下一
snapshot；這是對帳證據，不是把舊 ledger 自動升級成新 contract。

本輪 contract 收斂為：

- Paper producer 以 `PaperTradeTransition` 原子保存 fill batch 的 pre/post cash、NAV、
  positions、common prices 與 fill identity；policy turnover 只加總 transition 的
  canonical integer bp，gross fill turnover 只作 audit。
- 每筆 executed fill 的 gross bp 必須用 transition 的
  `pre_total_value` 以 Decimal `ROUND_HALF_UP` 重算；不從事後 EOD snapshot 猜分母，
  也不以 rejected／zero-fill 製造 turnover。
- T-1 reader 以官方 calendar 的完整 bounded date range 對 weekly snapshot，要求每個
  official session 都有 snapshot、最後一筆是 strict T-1 tail，且 cash／quantity delta
  能與 bounded fill interval 對帳；無交易只有在完整 coverage 已證明時才可接受。
- state 與 transaction ledger 都以 SQLite `mode=ro`／`query_only`、hash-before／after
  custody 讀取。isolated preopen producer 另發布
  `paper-preopen-coverage.v1` 與 `paper-state-write-contract.v1`；receipt 的 bytes、
  state head、portfolio／decision date、state／ledger path、snapshot relation 與安全
  scope 都要和 inner reader 讀回一致。
- Outer derived wrapper 對 state DB 的合法 08:30 append 允許明確的
  `expected_preopen_producer_overlap`；只有 inner read view 穩定、ledger 穩定、hash-bound
  preopen receipt 有效且最新 state head 對得上時才授權。empty、inline mismatch、stale、
  scope mismatch、receipt 在 hash/read 間變動或沒有 contract 都維持
  `failed_read_only_integrity`。

聚焦 QA 結果：

| Scope | Result |
|---|---|
| shadow ledger／calendar／transition／overlap | `tests/test_ml_allocation_shadow_evidence.py`：`33 passed` |
| source capture request／response binding | `tests/test_paper_formal_daily_source_chain.py`：`17 passed, 1 skipped` |
| derived wrapper（包含真實 isolated preopen producer → inner T-1 reader → outer wrapper，以及 invalid receipt／scope／race cases） | `tests/test_daily_ml_allocation_derived_shadow.py`：`16 passed` |
| isolated preopen／public daily runner regression | `tests/test_paper_portfolio_isolated_scheduler.py tests/test_run_paper_portfolio_daily.py`：`19 passed` |

上述真實 producer 整合只使用 pytest temporary source／repository scope；production
Forward scheduled receipt 仍須由 owner 在正式時段做 bounded rerun，並重新確認
`source.database`、market／release、state head、ledger hash、child stdout 與 outer
status。直到該 rerun 完成，`formal_oos_allowed=false`、`production_blend_alpha_bp=0`、
`broker_order_allowed=false` 維持不變。

### Direct checkpoint provenance recovery bounded QA（2026-09-16）

本段只做 Direct checkpoint／manifest 的唯讀 provenance 分類；沒有寫入 D 槽、
沒有改 checkpoint、manifest、latest pointer 或正式 SQLite，也沒有啟動 heavy
rebuild。新增入口為：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_ml_direct_checkpoint_provenance.py `
  --store-root D:\Min\Python\Project\FA_Data\output\release_v4\portfolio_ml_direct_numeric_production_v4_v2 `
  --maintenance-output-dir D:\Min\Python\Project\FA_Data\output\release_v4\portfolio_ml_direct_ooc_training_production_v4_v5
```

正式 Direct root 的實際 readback 如下：

| Check | Result |
|---|---|
| run scope | `11` 個 `runs/<run_id>`，checkpoint 全為 `portfolio-ml-direct-checkpoint.v2` |
| checkpoint state | `10` 個 `complete=true`，`1` 個 `complete=false`（`direct-ooc-3cec102bc9f96e2219319560`；6 個 completed years，沒有 top-level manifest） |
| computation provenance | `11/11` checkpoint 都缺 `computation_dependency_hash`、`computation_dependencies`、stable `computation_identity_hash` 與 identity payload |
| classification | `legacy_missing_computation_provenance=11`；`computation_identity_drift=0`（沒有 stored stable identity 可做 drift 比較） |
| full resume | `11/11` `resume_allowed=false`；完整 legacy manifest 只作 audit-only，不能由目前 source 貼 hash 回去 |
| latest pointer | 唯讀 pointer 指向 `direct-ooc-505c6adaf3f71a0c8f0a274e` 的 complete manifest；其 checkpoint／manifest 同樣沒有 computation provenance |
| recovery plan | `status=blocked_legacy_provenance`；2026-09-17 read-only plan hash `sha256:518a48e08bf5fd3e3ca84731a9e8a4d978fd1a80fad6a0ce7535d784a935c559` |

因此這次是「可辨識的 legacy provenance 缺失」，不是已證實的 source drift。
只有 checkpoint 已保存 self-consistent stable identity 時，inspector 才會把目前
stable identity 不同分類為 `computation_identity_drift`；checkpoint 缺欄不能被
推論成 drift，也不能被標成可續跑。stable computation identity 只綁定明確
dependency source bytes／compiled source fingerprint，排除 loaded-module 與
runtime constants；runtime custody 另作同批驗證，不參與 run identity。

安全復原流程固定為：

1. 先保存 inspector 回報的 checkpoint／manifest bytes hash 與 classification，
   原檔保持不動。
2. owner 確認 Direct／OOC／release 無 active process、heavy-chain lock 無 owner，
   並審核容量與目前 source identity；legacy checkpoint 不可使用 `--resume`。
3. 以目前 contract 建立新的 run identity／fresh Direct build；不能在舊 checkpoint
   上補寫目前 hash，也不能以 complete legacy manifest 冒充新的 computation custody。
4. 只在新 checkpoint、manifest、年度 artifact 與 raw source hash 完整 readback 後，
   才交給 OOC；Formal OOS、alpha 與 broker gate 仍維持關閉。

隔離驗證：`tests/test_ml_direct_checkpoint_provenance_recovery.py` 為 `12 passed`，
涵蓋 runtime metadata 不影響 stable identity、legacy complete audit-only、真正
identity drift、dependency corruption、manifest JSON corruption／tamper／identity
mismatch；另含 OOC handoff legacy reject／current identity accept，以及 lock custody
read-only／changed-bytes／gate-enumeration 負例；
`tests/test_ml_direct_computation_dependency_guard.py` 為 `9 passed`，
確認 legacy `_load_checkpoint` fail-closed 且不改變原 bytes。上述結果不等同正式
Direct 恢復；正式 D checkpoint／歷史 receipt 仍待 owner 依具體方案另行核准。

### Direct fresh-run recovery plan（owner approval required；2026-09-17 re-readback；本輪未執行）

為避免「另開新 run」停留在泛用建議，以下固定本次 read-only snapshot 對應的
輸入、identity 與隔離 output。任何 raw／corporate／sector／formal input、capacity
參數或 source dependency 改變，都必須重新執行 inspector／identity preflight，不能
沿用下列 run id。

2026-09-17 的 final source readback 已取代 9/16 及 lock-diagnostic code 加入前的
transient identity snapshots；此前 `sha256:69abb...`／`sha256:3f299...` 對應的
run id 都不得使用，本段只承認下列表格的新 identity。

| Item | Read-only value |
|---|---|
| raw source | `D:\Min\Python\Project\FA_Data\output\release_v4\ml_pit_year_shards\runs\pit-6874d65ee70d4f84cf41f5d1\all_field_enriched\manifest.json`；`manifest_hash=sha256:d55879c6d4bfae7c8fbb095330b0732eb1c5c80ecd2e0a0b5b79ee617b2eddc9`；`training_as_of=2026-09-07T08:30:00+08:00` |
| official corporate-action source | `D:\Min\Python\Project\FA_Data\output\release_v4\official_market_events\runs\official-market-events-189a6e1401c0396ff8cd353a\manifest.json`；file hash `sha256:6052829c4f477c2a902513356d01aa25ac98d324a828144036d9137b492b49b0` |
| current stable computation identity | `sha256:9c368f4a61397d9577ace500c0d45aaf9419dc5b32f04ba3163edfc6349b25f9`；只綁 dependency source bytes／compiled source fingerprint，排除 loaded-module／runtime constants |
| deterministic Direct identity | `direct_identity_hash=sha256:61851419729459f00529b7b9aa207d1b89999ef3eb9ebfc8af8970c26bb7bee0`；`run_id=direct-ooc-61851419729459f00529b7b9` |
| isolated store output | `D:\Min\Python\Project\FA_Data\output\release_v4\recovery_review\direct-store`；預期 run directory `...\runs\direct-ooc-61851419729459f00529b7b9` |
| isolated OOC output | `D:\Min\Python\Project\FA_Data\output\release_v4\recovery_review\ooc-training` |
| old publication boundary | 舊 `...\portfolio_ml_direct_numeric_production_v4_v2\latest_manifest.json` 不在上述 output；fresh build 不得以舊 root 為 `--output-dir` |

這份 snapshot 的現行 contract 是 `minimum_train_dates=252`、`test_date_count=63`、
`purge_trading_days=60`、`embargo_trading_days=5`、`benchmark_entity=TAIEX`、
`batch_size=8192`、`workers=2`、`memory_budget_mb=4096`，以及 persistent `35 GiB`、
temporary `40 GiB`、safety reserve `200 GiB`。目前 controlled environment 指向的
formal portfolio ledger 與 Rule Champion history 檔案不存在，sector sidecar 也沒有
被目前 pointer-bound identity 接受；因此下列命令只代表「current source + raw + official
event」的 bounded research fresh build，不能宣稱 formal readiness。缺少的 formal／sector
輸入若日後補齊，必須以實際驗證後的絕對路徑加參數並重新計算 identity。

owner 核准後，Direct-only 的完整可審查命令如下（本輪不執行）：

```powershell
.\.venv\Scripts\python.exe scripts\build_portfolio_ml_direct_numeric_store.py `
  --raw-manifest D:\Min\Python\Project\FA_Data\output\release_v4\ml_pit_year_shards\runs\pit-6874d65ee70d4f84cf41f5d1\all_field_enriched\manifest.json `
  --output-dir D:\Min\Python\Project\FA_Data\output\release_v4\recovery_review\direct-store `
  --training-as-of 2026-09-07T08:30:00+08:00 `
  --benchmark-entity TAIEX `
  --corporate-action-manifest D:\Min\Python\Project\FA_Data\output\release_v4\official_market_events\runs\official-market-events-189a6e1401c0396ff8cd353a\manifest.json `
  --minimum-train-dates 252 `
  --test-date-count 63 `
  --purge-trading-days 60 `
  --embargo-trading-days 5 `
  --batch-size 8192 `
  --workers 2 `
  --memory-budget-mb 4096 `
  --persistent-storage-budget-bytes 37580963840 `
  --temporary-storage-budget-bytes 42949672960 `
  --safety-reserve-bytes 214748364800 `
  --heavy-lock-path D:\Min\Python\Project\FA_Data\output\release_v4\.ml_heavy_chain.lock `
  --no-resume
```

此命令執行前必須確認 `recovery_review` 是新且空的 staging root；builder 只可在
該 root 建立 `latest_manifest.json`，不得碰舊 Direct root。完成後的 readback gate
是：inspector 顯示該新 run 為 `resumable_under_current_computation_identity`、
`checkpoint_provenance_valid=true`、`manifest_custody_valid=true`、`resume_allowed=true`；
再逐一核對 manifest／checkpoint 的 stable identity、dependency snapshot、raw／year／fold
hash 與容量 readback。任一不符都停在 staging，不進 OOC。

OOC 不是 standalone bypass：正式 downstream handoff 必須由同一 canonical
`D:\Min\Python\Project\FA_Data\output\release_v4\.ml_heavy_chain.lock` 的 maintainer
建立 parent→child custody，再把 `direct-store` 與 `ooc-training` 兩個隔離 root 傳給
chain。OOC 在訓練前現在會再次驗證 Direct manifest 與 checkpoint 的 current stable
identity、dependency snapshot、runtime custody 及兩者一致性；legacy／drift／corruption
一律 blocked。OOC 的 complete training manifest、replay-input status、artifact hashes
及 release readback 都完成前，舊 Direct pointer 不得替換；本次 owner 尚未授權該 chain，
所以沒有執行任何 OOC／release training。

容量與 custody preflight 的實際 readback：D 槽 free `317870940160` bytes（約
`296.04 GiB`），政策最壞需求為 `35+40+200=275 GiB`，理論餘裕約 `21.04 GiB`。
更新後的真正 read-only `rb → advisory-lock → unlock` probe 顯示 canonical lock 與
11 個 handoff gate 都是 `probe_stage=advisory_lock`、`lock_acquired=true`、
`bytes_unchanged=true`；canonical 與 gates 的 point-in-time bytes hash 都是
`sha256:d6b13e71d1ddd1f077144e83546732f8b53ed7b2e081166496683005ff05bb4d`。這只代表
該觀測瞬間未觀察到 holder，不等於 caller 已取得 canonical owner protocol。沒有
`.owner.json` 或可驗證 maintainer process，matching Direct／OOC／release process
掃描為空，maintenance lock 不存在，scheduled status 仍是
`maintenance_lock_state=missing_or_invalid`。因此仍不得刪 lock／gate、跳過 owner
protocol 或自行宣告可啟動；正式執行前必須由 chain owner 原子取得 canonical
reservation、重做容量與 process custody readback，並保留新的 point-in-time hashes。

若任一檔案的 before／after bytes 不一致，aggregate status 會是
`probe_file_changed`；若 handoff gate enumeration 失敗，會是
`handoff_gate_enumeration_incomplete`；兩者都 fail closed，不能降級成
`no_active_lock_observed`。

隔離 small-scope 已由 `tests\test_ml_direct_computation_dependency_guard.py` 的
interrupted builder fixture 走過新 identity checkpoint → complete manifest → inspector
readback；它只寫 pytest temporary directory，不寫 D 槽，也不等同正式 Direct recovery。

### 自然累積（不列為工程故障）

`D:\Min\Python\Project\FA_Data\output\scheduled\forward_outcomes\latest_status.json`
與 `evidence_progress\latest_status.json` 是 exit 0／warning path，核心訊息是
`no_maturity_calendar_observation`；官方日曆 open 並不等於 close price 已觀測，
因此這是正常 natural maturity accumulation。`v4_ml_forward_scheduler` 的
`skipped_non_trading_day` 也是正常 no-op。兩者都不能被改成 failure，也不能用
日曆推定 maturity。

## 後續修復清單

### Evidence pipeline／Position Health／Exit live readback（2026-09-17）

本次對正式 D 槽只做唯讀核對，沒有重跑 scheduler、沒有改寫 source／Paper／Formal。
9/9–9/16 共八份 `exit_effectiveness/YYYYMMDD.json` 均為
`status=degraded`、`transition_count=0`，並帶有
`no_exit_transition_rows`；八份實體 artifact hash 都與各自 child log receipt
的 `artifact_file_sha256` 相符。9/16 的 child return code 為 `0`，因此 Exit
caller 已經在既有排程中實際執行，這不是 caller 尚未接線或 subprocess wiring
失敗。

9/16 outer receipt 的關鍵分層如下：

| 層級 | 實際結果 | 判讀 |
|---|---|---|
| Evidence pipeline child | `pipeline_exit_code=0`、`pipeline_overall_status=degraded`、`pipeline_errors_count=0` | child 沒有 crash；仍有 portfolio／risk source-quality gap。 |
| Paper health refresh | `status=passed`，但選到 `snapshot_date=2026-09-14`，並有 `paper_daily_status_as_of_fallback:2026-09-14` | refresh 沒有把 9/14 快照冒充成 9/16；因此不能作 9/16 source evidence。 |
| Position Health market source | `status=blocked`；`position_health_market_source_unhandled:PositionHealthMarketSourceError:health_baseline_date_mismatch` | 9/14 baseline 與當次 `decision_date=2026-09-16` 不相等，date contract 正確拒絕。 |
| Outer wrapper | `status=failed`、`exit_code=2`、`pipeline_exit_code=0` | wrapper 對 blocked health source fail closed；這個非零是資料安全訊號，不是 Exit child failure。 |
| Position Health transition DB | 5 筆均為 `decision_kind=proposal`、`WATCH→WATCH`、`recorded_state=WATCH`、`auto_action_allowed=0` | 缺 `condition`／`thesis` 時保留 WATCH；沒有 `proposed_state=EXIT_CANDIDATE`。 |
| Exit effectiveness child | 9/16 `status=degraded`、`transition_count=0`、`warning=no_exit_transition_rows`；Paper ledger 8 rows、market price 504 rows | producer 只讀 `EXIT_CANDIDATE` proposals；零 rows 是目前 source state 的正確結果，沒有自然 closed 或人工 approved action 可計算。 |

因此目前的 blocker→owner→safe fix 如下：

| Blocker／缺口 | Owner | Safe fix | 不可採用的捷徑 |
|---|---|---|---|
| `health_baseline_date_mismatch` | Paper／Evidence data source owner + Ops | 等待或產出同一 decision date 的 Paper snapshot、status 與 quick／freshness receipt，再由自然排程重跑 source producer | 不得把 9/14 baseline 改名、改欄位或回填成 9/16。 |
| `thesis_registry_not_configured`、`forward_position_thesis_binding_missing`、`frozen_rule_policy_machine_only` | strategy owner／reviewer／governed policy owner | 提供 stable `position_id`／entry lineage、reviewer-owned `PositionThesisContract`，以及正式接受的 invalidation／horizon／review policy | 不得從 recommendation、model、UI 文案或 machine-only hash 代填 thesis。 |
| `pit_condition_source_missing`、`decimal_metric_source_missing` | market source／data-quality owner | 在同日有效 baseline 通過後，以 verified quick／freshness receipt capture PIT condition 與 Decimal metrics | 不得用目前價格、事後 capture clock 或裸 float 推回決策時點條件。 |
| `no_exit_transition_rows` | 不是 Exit caller wiring blocker；由上游 Health evaluator／reviewer／Paper ledger 共同形成 | 只有真實且可追溯的 `EXIT_CANDIDATE` proposal，及後續 reviewer-approved／Paper execution evidence，才可進入 Exit maturity | 不得手造 transition、人工改 SQLite／JSON，或把 WATCH proposal 當 EXIT。 |

自然累積的輸入是同日可驗的 Paper／market source、後續交易日的 outcome maturity，以及
上游在有效條件下自然產生的 transition。需要人工或治理輸入的是 thesis contract、正式
invalidation policy、reviewer approval 與實際 Paper fill／closed ledger evidence；在這些
輸入出現前，`degraded`／`WATCH`／`no_exit_transition_rows` 都是應保留的證據狀態。

本輪沒有修改 production code 的原因是現行 guard 行為正確：
`run_scheduled_evidence_pipeline_dry_run.py` 對 blocked health source 明確回傳 2，
`position_health_market_source_producer.py` 拒絕跨日 baseline，
`exit_effectiveness_producer.py` 只查詢 `proposed_state='EXIT_CANDIDATE'`。
新增的隔離測試固定了這兩個契約邊界，未觸碰正式 D 資料。

已完成的程式與 QA：

1. runner 傳遞實際 aware `decision_at`／`captured_at`／`as_of`，並新增獨立
   `calendar_decision_at`；after-close 自動標為 `eod_research`。
2. 兩個 capture CLI 與 `EvidenceCaptureRequest` 接上 chronology validator、
   source availability preservation 與舊 date-only honest downgrade。
3. event／snapshot identity 與完整 custody hash 分離；retry capture clock 可冪等，
   decision／as-of 變更不可靜默合併，tamper／child readback mismatch fail closed。
4. 已通過 52 項 clock／capture／service／event focused tests，另通過 27 項相關
   importer／repository／cross-day tests；Python syntax check 亦通過。

仍待外部或其他 owner 的 bounded follow-up：

- 補資料 freshness、PIT denominator、OOC／ledger／license 與 endpoint custody。
- 修復 Direct 缺失 checkpoint provenance；Forward child 的 Paper ledger／preopen
  read-only integrity 已完成 repository-isolated bounded QA，正式 scheduled rerun 仍待
  owner 在合法時間窗執行。
- 後續仍待外部或其他 owner 的 data freshness、PIT denominator、OOC／ledger／license、
  endpoint custody 與 forward Paper read-only integrity follow-up。

本輪沒有執行正式資料庫、raw source、scheduler registration 或歷史 event 的
修改；也沒有把任何舊 receipt 宣告為盤前或自然 authority。

### 後續追查：Paper producer termination 與 forward calendar lineage（2026-09-17）

對 Windows Task Scheduler 與 repository-isolated Paper output 做了唯讀追查，沒有
重跑 task、改 trigger／principal、改 D 槽或建立新的 Paper snapshot。實際 task
`\baldr-paper-portfolio-daily` 的 `Last Run Time` 是 `2026-09-16 16:15:01`，
`Last Result=-1073741510 (0xC000013A)`，action 指向
`scripts/scheduled/run_paper_portfolio_daily.cmd`，task 仍為 Enabled／Ready。
該 wrapper 在寫 status 前會等待真正的 Asia/Taipei 08:30；因此 9/16 這次是已啟動
但在 producer 完成前終止，沒有 9/16 status 或 snapshot。Task Scheduler Operational
log 當時是 disabled，無法由現有證據辨識確切終止者，故不把它歸因於登出、電源、
容量或特定操作者。這是排程執行環境的外部 fragility，不是 Paper reader 選錯 root。

repository Paper SQLite 的最後 snapshot 是 `paper-main-20260914`；
`PositionHealthDailyRefreshService._read_snapshot()` 只取 `decision_date <= requested`
的最新列，所以 9/16 選到 9/14 是正確的 fail-closed fallback，不能把它改標成 9/16。
entry lineage 只控制 machine-policy binding，不能補出缺失的 Paper snapshot。

另一條可修的缺口在 recommendation forward producer：approved policy
`paper-machine-thesis-benchmark-v1_2026-09-08-approved-v1` 仍 immutable，policy file
hash 保持 `sha256:23c3d37f36630b9a9217f41e6d60c50b17ee1bea44b3843edef55c1d904512ee`，
但其 calendar pin 是 9/7 snapshot，已於 `2026-09-14T19:20:27Z` 過期。官方 calendar
refresh receipt 已於 9/14 產生新的 exact cache，9/15／9/16 status 也都選取該檔；
原 recommendation forward receipts 仍回報
`ForwardPositionThesisError:official_calendar_day_unknown`，原因是 caller 沒有把
refresh status 的 current selection 傳給 candidate producer。

本輪修復只在 repository／隔離邊界完成：

1. scheduled recommendation 讀 `official-calendar-refresh-status.v1` 的 latest receipt，
   僅接受 read-only、candidate-only、無 child／credit／production action 的 terminal
   status，使用 receipt 指定的 exact path／file hash，再以官方 cache loader 重驗；不掃描
   directory、不回退到任意舊檔。
2. candidate packet／receipt 保留 policy 的 `calendar_cache_path`／hash 作為 immutable
   historical custody，另外保存 `calendar_observed_path`／`calendar_observed_sha256`。
   binder 重新驗證兩組 bytes，review horizon 使用 current observation；這不改 policy
   identity、也不替 machine observation 生成 human thesis。
3. `entry_binding` 仍維持 `awaiting_paper_fill`；只有同一 recommendation hash、
   policy hash、Paper fill／source event／evidence 與 policy 生效後新
   `natural_entry_verified` entry 才能建立 machine-policy contract，而且仍有
   `human_approval_required=true`、`auto_action_allowed=false`。目前沒有因此回填新
   entry、binding、thesis 或歷史 recommendation candidate。

隔離驗證結果：

```text
pytest tests/test_forward_position_thesis_candidate_producer.py tests/test_scheduled_recommendation_snapshot_wrapper.py -q -o addopts=
21 passed

pytest tests/test_forward_machine_policy_producer.py tests/test_scheduled_forward_calendar_refresh.py tests/test_position_health_source_providers.py -q -o addopts=
29 passed

mypy --explicit-package-bases --follow-imports=silent app_module/forward_position_thesis_candidate_producer.py app_module/position_health_source_providers.py scripts/scheduled/run_scheduled_recommendation_snapshot.py
Success: no issues found in 3 source files
```

以實際 repository refresh receipt 做 read-only selector readback，選到
`output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260914T231502118687Z_e02efc5483b2.json`，
file hash 為 `sha256:e0e0808d909ef82a94406ed99cbec2f53d8cff26413b38b74c995c0ae27514be`，
expiry 為 `2026-09-21T23:15:03.532140Z`。這只證明 producer/status wiring 已能消費
現有 renewed receipt；沒有把該 readback 宣告成 9/15／9/16 的新自然 candidate，亦沒有
觸碰正式 D 資料。

#### Paper lifecycle observability 與 Task Scheduler 證據界線（2026-09-17）

Paper isolated wrapper 已新增獨立於既有 `latest_status.json` 的 run-state：
`output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/run_state/latest.json`，
immutable phase receipts 位於同層 `receipts/`。`starting`、
`waiting_for_taipei_cutoff`、`cutoff_reached`、`producer_starting`、
`producer_completed` 與 `terminal` 都會留下 phase／heartbeat；等待 loop 每次 clock
觀察都更新 heartbeat，單次 sleep 上限 60 秒，超過 180 秒沒有 heartbeat 的非 terminal
前一輪才標成 `stale_nonterminal_run`。`terminator` 固定為 `unknown`，因此 stale
分類不會冒充 Windows actor 證據。收據寫入另保存 `pending`、`persisted`、
`already_present_verified`、`conflict` 或 `incomplete`；bytes mismatch 與建立收據時的
寫入例外會留在 latest run-state 的診斷欄位，不會讓下一輪把半份收據當成成功。此觀測層仍
固定 `candidate_only=true`、`writes_D_source=false`、`writes_market_database=false`、
`formal_credit=false`、`broker_execution=false`，也不回填既有 status／snapshot。

唯讀讀回 `\\baldr-paper-portfolio-daily` 的 Task XML／query facts：
`LogonType=InteractiveToken`、`RunLevel=Limited`、`MultipleInstancesPolicy=IgnoreNew`、
`DisallowStartIfOnBatteries=true`、`StopIfGoingOnBatteries=true`、Idle
`WaitTimeout=PT1H`／`StopOnIdleEnd=true`、`ExecutionTimeLimit=PT72H`、
`StartWhenAvailable=false`，action 為 `cmd.exe /c ...\\run_paper_portfolio_daily.cmd`。
trigger 的 Pacific local time 是 16:15；2026-09-16 16:15 PDT 對應台北次日 07:15，
wrapper 的自然 cutoff guard 會再等到台北 08:30。該次 `LastResult=3221225786`
（`0xC000013A`），且沒有寫出 9/16 terminal status／snapshot；與「作業已啟動、
在 terminal publication 前遭外部終止」一致，但 Scheduler Operational log 為 disabled，
所以目前不能證明 exact phase、terminator、登出、電源、idle 或特定操作者。這些設定
沒有在本輪修改。

若要在 root review 後縮短等待窗口，最小排程選項是依 DST 分季把 trigger 對齊台北
08:30（PDT 約 Pacific 17:30；PST 約 Pacific 16:30），但這仍需另行批准並處理季節性
trigger 變更；本輪不套用。當前已套用且不改 Task registration 的最小工程修補是
wrapper run-state／heartbeat／stale detection。正式查閱時應先看 run-state 判斷是否有
中止或 stale，再看既有 `latest_status.json` 是否真的有 terminal producer result；
heartbeat、old snapshot 或 fallback reader 都不能單獨宣告當日 Paper 完成。

本輪新增的 lifecycle／clock boundary 測試為 Paper isolated scheduler `14 passed`；
forward candidate 與 scheduled caller 的直接 producer／wrapper 定向測試為 `28 passed`。

#### A 線 partial write／fsync retry 與正式運行恢復唯讀盤點（2026-09-17）

本輪只修改 A 線 Paper isolated wrapper 與其定向測試，沒有修改 B／C、shared
Manual／SSOT、Task Scheduler 設定或正式 D 槽資料。`_PaperRunState._write_event()`
現在先把 immutable phase receipt 寫入短名 temporary file，完成 `flush`／`fsync` 後以
create-only hard-link 發布 final path，再讀回 final bytes；temporary cleanup 失敗也不會
刪除或覆寫 final receipt。partial stream 或 fsync 中斷只會留下
`event_write_status=incomplete`，final path 不會出現半份 JSON；相同 payload retry
可以重新發布，既有 bytes 則只接受 `already_present_verified`，竄改或 readback
mismatch 維持 `conflict`。

隔離測試使用真實暫存檔寫入：一個測試在 stream 已寫入半份 bytes 後中斷，另一個在
`fsync` 中斷，兩者都驗證 final／temporary path 沒有 partial 殘留，解除中斷後 retry
成功，第二次 retry 保持 bytes 不變，並保留 tamper conflict。正式 calendar loader E2E
則建立 hash-bound `OfficialTradingCalendar` cache，禁止 network fallback，將實際
`OfficialTradingCalendar` 傳入 `run_isolated()` 與 public Paper runner；positive case
的 cache `available_at` 早於 08:30 decision，結果為 `status=passed`、
`trading_calendar_validated=true`、
`trading_calendar_reason=twse_holiday_schedule_cache_open`。isolated wrapper 現在也
固定把 actual loader 綁到 repository `calendar_cache`，並重驗
`available_at <= decision_at`；late-capture negative case（cache 在 decision 後一分鐘
完成）回傳 `degraded_calendar_unknown`、
`trading_calendar_reason=official_calendar_capture_after_decision_at`，不追加 Paper
snapshot。這證明隔離 wrapper 能消費正式 loader contract 並拒絕用決策後日曆補造
盤前 authority；fixture 仍是 candidate-only QA，不是正式日曆 authority。

另外針對 official-events prior raw lineage 做了實際正式 artifact 的隔離讀取：
`D:\Min\Python\Project\FA_Data\output\release_v4\official_market_events\runs\official-market-events-189a6e1401c0396ff8cd353a\manifest.json`
的 manifest file hash 是
`sha256:6052829c4f477c2a902513356d01aa25ac98d324a828144036d9137b492b49b0`，
canonical events file hash 是
`sha256:07ee170332b220a416080773db2327987c7c4204e9d17651e0bf41c9d4f35fe6`。
現行 raw index 的 52 筆與 canonical 28,636 筆之間原有 43 個 raw hash／13,277
列未在 current index 出現；reader 沿 verified parent manifest chain 逐段核對後，
43 個 hash 的實際 bytes 全部從祖先 immutable raw response 找回，故這是 reader
lineage compatibility gap，不是真實 raw bytes 缺失。實際隔離 positive 為
`events=28636`、current raw `52`、ancestor lineage `43`、canonical raw coverage
缺口 `0`；把一個祖先 response 加 byte 的 negative 仍回傳
`ValueError: prior raw response hash mismatch`。新增 synthetic parent-chain
positive／tamper／broken-chain 測試 `3 passed`，受影響 official backfill tests `8 passed`。
再以該 D artifact 的 2026 四個 raw response 作受控 fetcher，在完整隔離副本建立
下一代 publication `official-market-events-8f81f86a04341d690a2d585f`（parent
manifest hash `sha256:97f4b17377fa91d977016134551a4f96d8f0e67d7824e1cc6392acdf225c168e`）：
`new_events=0`、canonical `28636`、raw `95`（requested `4`、lineage `91`），
canonical raw coverage gap `0`，95 個 response path／bytes 全部重算相符。這是
isolated self-contained publication readback，不是正式 D publication 更新。
同一正式 artifact 的隔離斷 parent negative 刪除
`runs/official-market-events-3f8c49b09c0d2366b7088633/manifest.json` 後回傳
`prior canonical raw lineage missing`；tamper negative 回傳
`prior raw response hash mismatch`。

```text
.\.venv\Scripts\python.exe -m py_compile scripts\scheduled\run_paper_portfolio_daily_isolated.py tests\test_paper_portfolio_isolated_scheduler.py
exit=0

.\.venv\Scripts\python.exe -m pytest tests\test_paper_portfolio_isolated_scheduler.py -q -o addopts=
14 passed

.\.venv\Scripts\python.exe -m pytest tests\test_paper_portfolio_isolated_scheduler.py -q -o addopts= -k "hash_bound_official_calendar_loader or late_official_calendar_capture"
2 passed, 12 deselected
```

正式運行恢復採唯讀讀回。`C:\Windows\System32\Tasks\baldr-paper-portfolio-daily`
XML 顯示 trigger 為每日 16:15、`InteractiveToken`／`LeastPrivilege`、
`MultipleInstancesPolicy=IgnoreNew`、電池時停止、`ExecutionTimeLimit=PT72H`、
`StartWhenAvailable=false`，action 為
`scripts\scheduled\run_paper_portfolio_daily.cmd`；
`Microsoft-Windows-TaskScheduler/Operational` log 是 disabled，
`schtasks /Query` 在目前受限環境無法提供 runtime facts。先前同一份真實 readback 的
9/16 `LastResult=0xC000013A` 與 16:15 啟動事實仍只支持「terminal publication 前被
外部終止」，不能辨識 actor、登出、電源、idle 或 exact phase。本輪沒有重跑 task。

2026-09-17 讀回六個已命名 `latest_status.json`（只讀 JSON 與檔案 metadata，沒有
啟動 job、寫 D 槽或改 scheduler）。目前正式與相鄰 lane 的最新狀態如下；日期以
receipt 內的 decision／as-of clock 為準，括號內是檔案 `mtime_utc`：

| 來源 | 讀回結果 | 工程判讀 |
|---|---|---|
| `D:\Min\Python\Project\FA_Data\output\scheduled\paper_portfolio_daily\latest_status.json` | `status=passed`、`decision_date=2026-09-07`、`snapshot_id=paper-main-20260907`；mtime `2026-09-07T12:28:04Z` | 正式 D Paper 仍是舊 terminal 快照，尚無本輪正式運行驗證；不能冒充 9/17。 |
| `C:\Projects\PythonProjects\technical_analysis\output\paper_execution_eod_replay\scheduled\paper_portfolio_isolated\latest_status.json` | `status=passed`、`decision_date=2026-09-14`、`snapshot_id=paper-main-20260914`；mtime `2026-09-14T00:30:05Z`；wrapper `run_state/latest.json` 仍不存在 | isolated output 仍是舊 terminal status；本輪 code/fixture QA 不等於正式 recovery receipt，仍待合法時段正式重跑。 |
| `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\latest_status.json` | `status=completed_waiting_natural_maturity`、`decision_date=2026-09-17`、`reason=natural_forward_evidence_receipt_missing`；matured `0`、pending `18`、`formal_order_allowed=false` | 自然成熟等待，不是 failure；歷史 replay 不可補成自然 evidence。 |
| `D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_calibration_learning\latest_status.json` | `status=passed_with_warnings`、`decision_date=2026-09-17`；warning `snapshot_cohort_degraded_screening_quality`；coverage degraded `186`、eligible `14`、missing `0`；learning `retain_current`／`natural_forward_evidence_receipt_missing` | 舊 9/16 cost-root failure 已不再是 latest cause；目前是 degraded screening 與自然 forward evidence 尚未成熟，仍 `formal_order_allowed=false`。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\official_market_events\latest_status.json` | `status=failed`、`as_of_date=2026-09-17`、`failure_class=official_market_event_backfill_failed`；receipt cause `prior canonical raw lineage missing`；active SQLite 未寫、formal publication preserved、latest manifest 未更新 | 舊 receipt 記錄的是 current raw index 未聚合 parent lineage 的 reader compatibility gap；A 已以正式 artifact 隔離修正／驗證，failed receipt 與 formal pointer 仍未被回填或重跑，不能宣稱新 backfill 成功。 |
| `D:\Min\Python\Project\FA_Data\output\scheduled\ml_raw_pit_refresh\latest_status.json` | `status=failed`、`2026-09-17 05:05:02–05:08:40 -07:00`、`builder_returncode=2`；`quarantine_required`，candidate `17858`、invalid `7`、unavailable `16913`；SQLite `ro/query_only`、source 不寫入 | 真實 PIT source／custody blocker；quality receipt 的 source receipt time 未提供，維持 quarantine，不修補、零填或重跑洗掉。 |

六路徑 compact readback 與分類另存於
`docs/06_qa/A_OPERATIONS_LATEST_STATUS_REVIEW_2026_09_17.md`，供 review／B 線引用。

可執行但尚需批准的 A recovery 方案是：由 Ops owner 在合法時間窗執行既有
`baldr-paper-portfolio-daily`，保留 Task XML／LastResult／child stdout-stderr，完成後
唯讀讀回 run-state `latest.json`、phase receipts、isolated `latest_status.json`、
state head 與 source bytes hash；若仍無 terminal 或出現 stale，維持 unknown／blocked。
若要把 trigger 從 16:15 Pacific 改成依 DST 對齊台北 08:30，必須另取得 scheduler
變更批准，本輪不套用。BankTaiwan 自然等待、legacy degraded／natural-evidence、
official-events 尚待正式重跑的 receipt 與 raw PIT quarantine 分別由其 owner 處理；A 不替它們製造
candidate、checkpoint、historical availability 或 EXIT。

#### 2026-09-17 morning recommendation／calendar caller 唯讀 readback

9/17 morning report 與 recommendation scheduled receipt 已完成唯讀讀回；沒有重跑
caller、沒有寫 D 槽、沒有改 Paper 或 scheduler。正式 recommendation status
`D:\Min\Python\Project\FA_Data\output\scheduled\recommendation_snapshot\latest_status.json`
為 `status=passed`、`checked_at=2026-09-17T05:10:02-07:00`、
`result_id=scheduled_rec_20260917_051002`、`recommendations_count=14`。其
`forward_position_thesis` 同時為 `status=passed`、`candidate_count=14`、
`blockers=[]`、`candidate_only=true`、`human_approval_required=true`、
`auto_action_allowed=false`，且 `writes_paper_state=false`、
`writes_formal_state=false`、`writes_broker=false`。這是 candidate evidence，不是
正式下單或 Paper completion。

這次 actual caller 的三個 clock／custody 關係如下：

| Clock／來源 | 唯讀值 | 判讀 |
|---|---|---|
| recommendation source | `D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260917_051002.json`；file hash `sha256:3ee58f7588f209ce0e59e9b86401d58aa97835e3d429e99e9340c41d003c4a14`；`available_at=created_at=2026-09-17T05:10:02-07:00` | source bytes 在 candidate decision 前已可用。 |
| candidate decision | `forward_position_thesis.decision_at=2026-09-17T05:10:23.23025-07:00`；sample candidate `candidate_scheduled_rec_20260917_051002_1569.json` file hash `sha256:fe3c7ec4524e78bd83f75d0d562a3fa7d44377de7f1cffdead55ff468ff15b07`，實際 hash 相同 | recommendation source → candidate decision 的順序與 immutable pointer 可驗。 |
| official calendar observation | `C:\Projects\PythonProjects\technical_analysis\output\paper_execution_eod_replay\calendar_cache\twse_holiday_schedule_2026_20260914T231502118687Z_e02efc5483b2.json`；file hash `sha256:e0e0808d909ef82a94406ed99cbec2f53d8cff26413b38b74c995c0ae27514be`；`captured_at=2026-09-14T16:15:03.53214-07:00`；`expires_at=2026-09-21T16:15:03.53214-07:00` | calendar capture 早於 9/17 decision，且 refresh status `cache_valid_for_forward_horizon`；actual loader 的 path／hash selection 已接線。 |

Approved policy 的 calendar pin 仍保留在 candidate 的 invalidation custody：policy path
`C:\Projects\PythonProjects\technical_analysis\output\forward_position_thesis\calendar_snapshots\paper-machine-thesis-benchmark-v1_2026-09-08-approved-v1_74790d36d0cd6639.json`、hash
`sha256:74790d36d0cd66398c37a729bfce243e1a03358f93afd256c523e2549c6d6c93`；current
observation 另綁上述 renewed cache，不覆寫 historical policy identity。

9/17 evidence morning report 的 blocking gaps 是
`portfolio_alert_snapshot_quality_not_ready` 與
`risk_prompt_snapshot_quality_not_ready`。`risk_prompt` 的 warning 是
`risk_prompts:risk_prompt_source_quality:portfolio_alerts:degraded`，因此應判為
portfolio alert quality 的下游結果，不另立成 risk-prompt caller 未接線。Paper
9/14 fallback、`human_thesis_required_before_health_transition_validation` 與
`paper_position_identity_unproven:1418` 仍是實質 residual。

1418 的 read-only join 檢查只能證明持倉存在，不能證明 entry identity：正式 D
`paper_portfolio.sqlite` 的 `paper-main-20260907` snapshot 有 `1418`、3000 股、
mark `17.6`，baseline `baseline_20260712.json` 也有 1418／3000 股；repository
9/14 snapshot 延續 1418／3000 股，但 ledger 對 1418 僅見 9/8 rejected sell、
`filled_quantity=0`，沒有 filled buy／entry fill／source event 可綁定。因此不補造
`position_id`、entry lineage 或 human thesis，保留 unproven／WATCH 與下游 degraded。

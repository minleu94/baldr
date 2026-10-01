# ML revision-aware rebuild 執行方案與缺件分類（2026-10-01）

## 結論

本輪已完成三項分開的工程結果：既有 runner 可在 core freshness proof 後、Formal revision hold 前保存雙市場 prospective source custody；另以既存 2026-09-30 source candidate 完成一次獨立 no-write preflight 與單日 raw-row research projection；每日 projection hook 已接到 runner／`.cmd`，並通過 46 passed／1 skipped focused route、py_compile 與 scoped mypy。Hook route 使用 stub projector，wrapper 行為以短暫複製 wrapper+fake child 驗證三種旗標及原樣傳回 child exit code；沒有執行正式 wrapper 或自然 Task，故 10/1 下一次 05:05 natural projection receipt 仍待驗，受控 CLI projection 不替代 hook 收據。所有結果都不解除 revision cutoff，也沒有 source-unit acceptance、historical PIT、formal OOS 或 formal credit。Projection 的來源、rows、readback、測試與失敗收據見[單日投影 QA](SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)與[hook QA](SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)。

正式年 shard exporter `data_module/ml_pit_year_shard_exporter.py::PITYearShardExporter` 與 CLI `scripts/build_ml_pit_year_shards.py` 已存在；另有固定來源、hash-pinned 的 V3 **research candidate** 命令。缺口不是 exporter 不存在，而是未支援任意新市場 revision 的 revision-aware research mode。既有 Direct/OOC raw-manifest contract 不接受本輪 daily source-row research schema，也沒有隔離 candidate 的 exact-pin 消費與 release revalidation。正式 blocker 因而包含 raw research mode 與 Direct/OOC research adapter/pin engineering；不能描述成僅待 owner 確認或自然成熟。每輪 natural sample、shadow horizons、source acceptance 與正式寫入確認仍是不同 gate。

V3／Direct/OOC command 與 source profile 盤點為唯讀；另外已在受控 CLI 下產生上述單日 research row projection。每日 hook code 與 fake-child wrapper 行為 route 已驗；沒有跑真實 runner、建立歷史 ML dataset、執行 Direct/OOC、訓練或 Task；沒有寫 D、正式 DB 或任何 pointer。

## 分開管理的四項狀態

| 項目 | 已有事實 | Close criteria |
|---|---|---|
| 前瞻 source custody 與單日來源列投影 | `run_ml_raw_pit_refresh.cmd` 預設傳入 `--capture-prospective-daily-price-candidate` 與 `--project-daily-source-rows`；`BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION=0` 單獨停用 projection，既有 `BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE=0` 同時停用 capture 與下游 projection。Python runner 僅在 core freshness proof 後、revision gate 前執行 capture；只接受 same-run `captured`／驗證過的 `already_captured` 與完整 candidate readback/pins 才投影。受控 9/30 candidate projection 為 1,972 rows、9,004,111 bytes、source/revision/DB 11 項指紋零差異；source availability 在原日 cutoff 之後，未評估 PIT。Hook nested status 與候選內 create-only `runner_terminal_verification_receipt.json` 綁定 terminal readback；失敗只新增診斷，不覆寫 core／revision-hold／exit。Hook route 46P/1S、py_compile、scoped mypy 通過；fake-child wrapper test 驗證三種旗標及 child exit propagation，沒有執行真實 wrapper／Task。 | 下一自然 05:05 Task 應 read back 同 run 的 capture `candidate_path`／manifest SHA 與 projection nested terminal receipt path/hash，並核驗 receipt status/content pin/readback clock/observations hash。自然收據到位前不得說日常 hook 生產已驗。受控 projection 無 feature/label、unit claim、PIT、Direct/OOC、Formal eligibility；核心仍守 revision hold。 |
| Revision-aware research raw 與 Direct/OOC pins | 正式 `PITYearShardExporter`／`scripts/build_ml_pit_year_shards.py` 已存在，並非任意市場 revision 的 research builder。V3 candidate 僅支援固定 source profile。Direct/OOC 目前不接受 daily source-row schema；scheduled resolver 只用 `release_v4` latest raw pointer。 | 工程新增明確 revision-aware research raw contract 與隔離的 Direct/OOC research adapter，精確綁定同一 candidate manifest/hash、source/revision/availability/cutoff pins，完成 source quality、output identity/readback 與 release revalidation；正式 pointer 保持不動。 |
| 自然前瞻 maturity | candidate 是 accumulator，不是 mature evidence。gate 為 5／10／20／60 trading-day horizons、至少 20 個 shadow days，且每個 horizon 至少 20 筆已成熟觀測。 | 每筆實際跨過對應 horizon，且再次驗來源可得時間、cutoff 與資料完整性；完成後另行 owner review formal/OOS eligibility。不得用當日事件或行事曆經過天數冒充成熟樣本。 |
| Source acceptance／正式 D rebuild | source owner acceptance 目前是 QA 所列後續 gate，repo 沒有一個可宣稱已接受來源的通用 acceptance object。現存 V3 source profile 是結構與 hashes 驗證，並明確禁止 PIT/OOS/promotion。 | 對指定 sources/market dates 提供可核實單位、availability、venue、source receipts／raw hashes、revision/DB identity及修訂規則；使用既有可信任 review/pin 流程作明確採納。候選 exact diff、資源／鎖／rollback/readback計畫完成後，正式 D 改寫才可另行明確確認。不得用 JSON 自宣或新造簽章代替。 |

9/30 sample 的 `available_at` 是 `2026-09-30T08:07:47Z`／`08:07:51Z`，晚於 9/30 台北 08:30 cutoff（`00:30Z`），因此不能回填 9/30 PIT。候選本身在 `2026-09-30T20:45:36.956214Z` 完成，雖早於下一日 `2026-10-01T00:30Z`，既有 QA 沒有做 10/1 cutoff qualification 或 source-owner acceptance；不能單以時間先後宣告通過。

## 現有 supported commands 與其邊界

### Restatement V3 research candidate

`scripts/build_ml_raw_dataset.py` 在 `scripts/`、`data_module/`、`tests/` 中均不存在。正式 `data_module/ml_pit_year_shard_exporter.py::PITYearShardExporter` 已存在；正式 year-shard CLI 為 `scripts/build_ml_pit_year_shards.py`，可供既有正式 pipeline 建立年 shards，但不提供任意市場修訂的 research-mode manifest。此處缺的是另一種 revision-aware **research** input mode，不是宣稱 repo 沒有 raw exporter。`scripts/build_ml_restatement_research_dataset.py` 只有 legacy wrapper，呼叫 `data_module.ml_restatement_research_dataset.main()`；它不是 revision-aware Formal raw builder。真正的 V3 research CLI 是 `scripts/build_ml_restatement_candidate.py`，輸入需 exact pin：snapshot DB/hash、source manifest/hash、official market manifest/hash，以及 unique `output-dir`／`custody-dir`。其非可執行模板如下；`<...>` 都必須在每次建置前從實際 readback 取得，不可照抄：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_restatement_candidate.py `
  --snapshot-db <verified-snapshot-db> `
  --expected-snapshot-sha256 <readback-snapshot-sha256> `
  --source-manifest <matching-source-manifest> `
  --expected-source-manifest-sha256 <readback-source-manifest-sha256> `
  --official-market-manifest <official-market-capture-manifest> `
  --official-market-hash <readback-market-manifest-sha256> `
  --output-dir <new-isolated-research-output> `
  --custody-dir <new-isolated-custody-output>
```

當前 validator 並非通用：它 pin 固定的 2026-09-23 run02 `source.sqlite`／`source.json`、正式 DB 路徑、market capture 與 validator code hashes（見 [candidate source constants](../../data_module/ml_restatement_research_candidate_source.py#L28)、[exact path/hash checks](../../data_module/ml_restatement_research_candidate_source.py#L442)、[profile flags and pins](../../data_module/ml_restatement_research_candidate_source.py#L526)）。V3 manifest 還要求 `research_only=true`、`formal_historical_PIT=false`、`formal_oos=false`、`promotion_eligible=false`；建置前後都重新驗 source/profile hashes（見 [V3 validator](../../data_module/ml_restatement_research_dataset_v3.py#L84)、[V3 build readback](../../data_module/ml_restatement_research_dataset_v3.py#L243)）。所以這可供目前指定來源的研究 candidate 使用，不是將未來 DB revision 泛化為 Formal 的命令；本輪未執行。

Existing profile 是可信任資料完整性／hash pin evidence，不是 owner 採納：其欄位和固定驗證範圍沒有 source-owner acceptance。它有檢查 DB revision receipts、來源 snapshot、官方 market capture 與 validator bytes，卻明確保留研究限制。

### Direct/OOC 的既有入口

- `scripts/scheduled/run_ml_direct_chain_maintenance.py --preflight-only` 可解析目前 release inputs 與容量，停在 launch／lock 前；但 `_resolve_inputs()` 固定從 `release_v4` 的最新 raw dataset pointer 取 manifest（[resolver](../../scripts/scheduled/run_ml_direct_chain_maintenance.py#L357)）。它是現有 release 的預檢，不會產生 candidate raw dataset，也沒有接收 arbitrary candidate root 的 option。本輪未執行；preflight 會寫 operational status。
- `scripts/maintain_ml_direct_v3_refresh_chain.py` 接受 explicit `--raw-manifest`、store/training/output roots、database 和 `training-as-of`（[parser](../../scripts/maintain_ml_direct_v3_refresh_chain.py#L118)），是 Direct/OOC heavy chain。它消費既有 raw-manifest contract，沒有接受單日 source-row research schema 或 owner source acceptance 的輸入；不是 revision-aware raw builder。
- Standalone `scripts/build_portfolio_ml_direct_numeric_store.py` 與 `scripts/build_portfolio_ml_ooc_from_raw.py` 也接受 `--raw-manifest` 和明確 output path（[Direct CLI](../../scripts/build_portfolio_ml_direct_numeric_store.py#L33)、[OOC CLI](../../scripts/build_portfolio_ml_ooc_from_raw.py#L33)），能做既有 contract 的後續 Direct/OOC stage，但不是底層 revision-aware raw build。新單日 research projection schema 不符合目前這些 consumer 的 raw manifest contract，不可直接接入或宣稱相容；須先建立新的 research manifest／adapter 與明確的 source/revision pins，再做隔離 consumption QA。既有產物 `formal_oos_allowed=false` 的邊界不變。

source revision fail-closed gate 位於 `formal_market_revision.collect_market_revision_evidence()`：驗證真實 revision 狀態並依 decision cutoff 拒絕歷史 PIT；單純讀取／改寫 status、增加 candidate 或直接重跑舊 wrapper 都不解此 guard（[gate](../../data_module/formal_market_revision.py#L324)）。

## 已完成的單日來源列投影與仍缺工程

`data_module/ml_daily_source_row_research_projection.py` 與 `scripts/project_ml_daily_source_rows.py` 只接受經驗證的單日 prospective source candidate，產生來源列 representation，不計算 features、labels、returns 或 unit conversion。受控實際結果及 raw／receipt／manifest／rows hash 見[單日投影 QA](SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)。它不是完整日期範圍／歷史 shards 的 general builder；candidate flags 保持 research-only，`unit_claimed=false`、`market_revision_cutoff_policy_evaluated=false`、`direct_ooc_compatible=false`。每日 hook 已接到 runner／wrapper並通過 focused route；未跑真實 runner或natural Task，不能用單日 CLI 的成功替 hook 日常收據。CLI 預設 no-write，`--write-candidate` 才寫固定 QA 子樹；hook 的 per-run terminal 與 nested status contract 見[hook QA](SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)。

## 建議的最小後續工程範圍

下一批工程先建立 revision-aware research mode，重用既有 exporter 的受支持部分但不改 Formal writer／pointer，也不將單日投影冒充完整歷史 raw：

1. 為 revision-aware research mode 定義明確輸入 contract：snapshot DB identity、`revision.json`／receipt／plan pins、market source custody 與實際 availability、code/schema identity、隔離 output/custody root。不得假設固定 V3 source profile 適用未來來源，也不讓候選自行宣稱 owner acceptance。
2. 在完整 research raw manifest 保存 exact input/output pins 和研究 flags；建置前後重驗來源不可變、raw/partition/source-quality/cutoff/lookahead 與 readback。無 availability、未知 cutoff 或來源不完整即 fail closed；不得回填交易訊號可得日。
3. 現有 Direct/OOC contract 不接受新 daily source-row research schema；先新增明確 research-only adapter/manifest，以小 fixture 驗 schema、identity、hash 與負向分支，再用隔離 candidate 做消費 readback。Direct/OOC per-run manifest/receipt 必須 pin 同一 candidate raw manifest hash、row counts、training-as-of 與 market revision；release `release_v4` pointer 保持不變。
4. 用 source-time 自查：每個決策特徵、標籤、公司篩選、標準化、corporate-action adjustment 與 benchmark 只依決策時點可取得資料；晚到或更正值只進未來時點／candidate revision。完整 revised-history build 需 key-by-key revision diff 與非回歸 comparison，並記錄差異歸因。

建議新增檔案的最小 allowlist 可先限 `data_module/ml_revision_aware_raw_candidate.py`、`scripts/build_ml_revision_aware_raw_candidate.py`、`tests/test_ml_revision_aware_raw_candidate.py`，另視 Direct/OOC 消費 contract 增加隔離 research adapter 與 tests。先用小 fixture 固定 source row input、manifest／receipt pins 與 consumer schema；不要改 Formal D writer、scheduled Direct/OOC release-pointer resolver 或既有 V3 source profile。此限制只界定正式 rebuild／release resolver，不阻礙已接線、仍保持 research-only 的每日 projection hook。此為後續工程建議，不是已核准實作，也沒有預設 source-owner acceptance 物件。

## 執行與 release 驗收次序

1. 只讀校驗來源 owner 提交的 source-contract facts與正式 revision chain。現有截至 2026-09-23 revision參考為 `20260923_run01`，DB 範圍 `2014-01-02..2026-09-23`；revision.json SHA-256 `801375e37a6f3c387d80178c775bfa73a1bf21ec914e73f7a014233078c700d2`，鏈摘要 `7dc35af66b3ca033f47d172ff52cdea9d21b95a1a94c2ed57fb649624a508bc4`。每次真實執行均需重新 readback，這些歷史 hash 不可假設永遠 current。
2. 產生 research-only raw candidate 到全新 repo ignored root；記錄輸入 pins、snapshot revision、source custody、availability、market calendar、code hashes、實際讀寫 bytes、candidate raw manifest hash。source modification、row/key/period/coverage mismatch、cutoff/lookahead violation 都應拒絕 candidate complete。
3. 在 candidate root 對該 hash-pinned manifest 做 Direct/OOC preview／build，驗其來源 identity/readback與 flags；不能讀寫 `release_v4/latest_manifest.json`、Formal source pointer、正式 SQLite 或 D。實際 heavy candidate QA 前，依既有 capacity policy先確保資源可用且與其他 chain 不競爭；不以 preflight 本身宣稱 build pass。
4. 之後才做 release 重新驗證：從 exact candidate/source/revision pins重讀、再驗 source quality、cutoff、Direct/OOC hashes、manifest/partition readback、pointer 更新的預覽 diff、容量與共享 lock。若改版任何來源、時間、schema或build code，舊 QA 必須失效重跑。
5. D 正式重建是另一個明確高影響操作，需 owner/source acceptance 已有來源證據、候選 diff 與 backup/rollback/readback 計畫可審、至少保留 200 GiB、scheduled persistent 上限 35 GiB、temporary peak 40 GiB，持有 `.ml_heavy_chain.lock` 並確定 Direct/OOC 沒有競爭 owner。全部材料 review 完成後，正式 D write 仍需另外明確確認；本輪不可執行。

真正自然成熟仍按 5／10／20／60 horizons 和每 horizon 20 個已成熟觀測計算。這些成熟條件不能取代 revision-aware research builder 或 Direct/OOC adapter；builder readiness 也不能取代 maturity、source acceptance、正式寫入確認或自然 Task 驗收。

# ML revision-aware rebuild 執行方案與缺件分類（2026-10-01）

## 2026-10-03 目前研究工程驗收

年度 raw／Outcome Direct／B 數值來源、CORE19 訓練保存、新 Python process 推論及原 Legacy Pipeline→Bank 研究接續，已由 root 第三階段受控 readback 接受。最新模型 manifest 位於 `output/ml_research/integration_20261002/current_restated_core19_phase3_20261003T064855260194Z/`，SHA `f4f8b70f2da3515089007698c44497ca32fa7b56258cec8880e62e8aa6fe2e2b`；整體 ML acceptance receipt `output/qa/integration_20261002/ml_validation/root_phase3_ml_acceptance_20261003T070413001284Z.json` SHA `007d245a4228d9f260ef3e4fd39373ce3eb4c62dac8129e88e29f33f2f8afc9f`。root 驗證 16 個 code pins、12 項真實 evidence、13 項語意檢查、兩個 cold process、Legacy→Bank sidecar、四筆成熟歷史成本 Decimal 重算與 55 個 protected formal／V2 檔未變。raw task 於 `07:04:44.515124Z` 恢復 Enabled=true／Ready，XML 回到暫停前 SHA；沒有手動重跑正式 raw。

研究模式仍是 current-restated／non-PIT、production alpha 0、allocation teacher blocked；沒有 promotion、正式 pointer 切換、formal credit 或投資效果驗收。第三階段 UI 與 native Windows 操作仍待 root 最終驗收；本文件的現行狀態不代表整個產品驗收完成。受控輸入、時鐘、成本和使用限制見[整合修復紀錄](INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)與[手冊7.0.1](../07_guides/APPLICATION_MANUAL.md)。

## 歷史：2026-10-03 第二階段中間驗收檢查點

以下保存當時的修復順序及待辦，不作最新未完成清單；目前狀態以上方與PROJECT_SNAPSHOT為準。

舊研究 Direct／OOC 的 purge後實際distinct train門檻與raw CLI發布摘要已修正並凍結。Root於`03:45:53Z`→`03:46:39Z`獨立執行原三檔加正式防護／CLI，45 passed／1環境symlink skip，39 pins前後相同；至少四個合格fold不能包含不足request.minimum的五日窗口。High對C的pure fitter／CORE19 projector子集另完成31有限檢查，未真fit或保存。真資料的CORE19→fit／save／新PID reload／infer與Legacy／Bank仍須實跑，不能以這些測試替代。

當時Direct結果：root以新凍結source-id／80bp契約版本真建置與公開讀回，1,796股票rows／49來源features、6,709 labels逐筆通過獨立原價Decimal重算；905個benchmark事件位置、8個實際125以上train／63test／60purge／5embargo folds已核實。受控producer PID3616於`03:21:47Z` exit0，consumer於`03:23:16Z`接受，20 producer pins與16 consumer pins前後相同。此段只記錄當時的Direct checkpoint；後續 CORE19／fit／save／新 PID reload／infer、Legacy／Bank與raw task恢復狀態以上方 2026-10-03 摘要為準，不以舊時間點描述現況。

目前狀態依 [整合修復紀錄](INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。root 已完整讀兩份 Sol High 報告並分派 Luna 修復；原 18 tests 兩次獨立重跑均通過，但沒有模型 fit／save／load／infer。A fixture 沒有修訂 receipt（`source_revision_gate=null`），B consumer 只保存 value_count 索引而丟失實際數值。另已確證 invalid custody 放行、假 fold 標籤跨越 test、Windows 正式根隔離、scale 分母／exponent、compact 日期零列、收據過早與研究續跑接線等 bug。下方原「完整貫通」主張已被修正，不能當現行完成證據。

root 已實際建立真來源的單一 query_only transaction／SQLite backup 一致副本，核對 quick_check、四表 counts、原 DB 與 34 個 namespace 檔案 before／after hashes。`01:44:40Z` 已再以真實原 DB、同一副本與四 namespace strict validator 通過 current-restated context，completed pending／final 配對及 27 個同次實體 dependency roles（19 個外部來源檔）有效。快照觀測為 `00:23:25.887429Z`，完整來源驗證完成為 `01:44:40.304301Z`；後續 raw／fit 必須使用真正較晚的完成／訓練截點，不授 historical PIT／formal source acceptance。Formal 16 個 pointer／manifest 與 active V2 全 39 檔 before pins 已保存，真研究 run 完成後還須 after 校驗。

研究輸出統一收斂到 repo `output/ml_research` 的新隔離目錄，修訂旗標不得放寬 schema/hash/custody/leakage/數學切分／隔離。完整 stack 維持足夠真 fold；三日 projection 無成熟 20 日 label，只能證數值保存／已驗 loader／有足夠歷史上下文的研究推論，不能造 train/test。Legacy／Bank 研究 context、真歷史資料 build/train/save/reload/infer 與相關排程受控驗收仍在本次工作內，不列為已完成或未來建議。

補充時間審查確認現有研究旗標仍可能將目前修訂值的可得時間回填成 event_at。修復必須重用既有 restated 研究型別並保留真實觀測／修訂時鐘，不改一般 PIT row guard。event／歷史 reference、標籤 event maturity、purge 與 embargo 依年代座標驗證；本次資料修訂／觀測則依真實 fit cutoff 驗證。缺原公告時間不得填造。研究分片若依歷史 event 年份選取，仍須保留當前 availability，不能為配合 `--years` 倒填可得時間。有限真來源日期容量已足以安排 2330／2317 的 2023–2025 年代範圍四個以上完整 fold；raw與outcome特徵／標籤已完成後續真建置與讀回（見下方補充），CORE19／模型仍待實跑。

下列截至 10/1 的來源／命令盤點保留其歷史範圍；命令模板須依修後 CLI、真 UTC freeze、實際 bytes pins 與 approved roots 更新後再執行，不能照抄舊日期或來源路徑。

最新 raw 更新：High 後驗發現合法千分位 parser 誤判與 TWD unit 標示問題，A 修後原 CLI 第三次真實隔離執行於 UTC `02:48:01Z` exit0／stderr0；root 完整讀完 2023–2026 四個 gzip shards，核對 73,234 observations／281,699 values 的內容、筆數、hash、int64／exponent／masks 與來源／衍生時鐘，invalid quarantine=0，真 null 價格來源仍保留。price contract／raw／CLI 三路由獨立回歸 64 passed。這是 raw 層完成，包含 context rows，並非股票 samples 或模型訓練；SQL 數值有限後驗32/32、合法千分位與TWD單位已接受。舊單位／coverage 限制及原失敗保留，真實 readback 見整合修復紀錄。Direct outcome store 已完成下述後續實跑；CORE19 與 Legacy／Bank consumer仍須實跑，不以本段raw證據外推整鏈。

UTC 10/3 `01:15:57Z` root 已以生產 B CLI 完成真 10/2 source-row projection → adapter → numeric observations store → immutable loader，1,962 筆／7,658 個值全部通過獨立 Decimal 尺度比對，來源與四個 B production 檔前後 pins 相同。此為數值消費工程驗收，仍 blocked Direct/OOC context／mature labels，未建立 fold／模型。A 原 DB context 的後續真實讀回已通過，見 `output/qa/integration_20261002/ml_validation/real_source_context_20261003T014356344464Z/readback.json`；不刪 marker、不改既有 snapshot receipt、不把新增來源驗證時間當歷史當時可得。Direct、模型／Legacy／Bank worker 仍實作中，真實 fit／save／load／infer 尚待取得；B unit fixture 已同步新 physical dependency inventory，root 於01:48 UTC獨立重跑22 passed。

## 歷史：2026-10-01 初始結論

本輪已完成三項分開的工程結果：既有 runner 可在 core freshness proof 後、Formal revision hold 前保存雙市場 prospective source custody；另以既存 2026-09-30 source candidate 完成一次獨立 no-write preflight 與單日 raw-row research projection；每日 projection hook 已接到 runner／`.cmd`，並通過 46 passed／1 skipped focused route、py_compile 與 scoped mypy。Hook route 使用 stub projector，wrapper 行為以短暫複製 wrapper+fake child 驗證三種旗標及原樣傳回 child exit code；沒有執行正式 wrapper 或自然 Task，故 10/1 下一次 05:05 natural projection receipt 仍待驗，受控 CLI projection 不替代 hook 收據。所有結果都不解除 revision cutoff，也沒有 source-unit acceptance、historical PIT、formal OOS 或 formal credit。Projection 的來源、rows、readback、測試與失敗收據見[單日投影 QA](SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)與[hook QA](SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)。

正式年 shard exporter `data_module/ml_pit_year_shard_exporter.py::PITYearShardExporter` 與 CLI `scripts/build_ml_pit_year_shards.py` 已存在；另有固定來源、hash-pinned 的 V3 **research candidate** 命令。缺口不是 exporter 不存在，而是未支援任意新市場 revision 的 revision-aware research mode。既有 Direct/OOC raw-manifest contract 不接受本輪 daily source-row research schema，也沒有隔離 candidate 的 exact-pin 消費與 release revalidation。正式 blocker 因而包含 raw research mode 與 Direct/OOC research adapter/pin engineering；不能描述成僅待 owner 確認或自然成熟。每輪 natural sample、shadow horizons、source acceptance 與正式寫入確認仍是不同 gate。

V3／Direct/OOC command 與 source profile 盤點為唯讀；另外已在受控 CLI 下產生上述單日 research row projection。每日 hook code 與 fake-child wrapper 行為 route 已驗；沒有跑真實 runner、建立歷史 ML dataset、執行 Direct/OOC、訓練或 Task；沒有寫 D、正式 DB 或任何 pointer。

## 歷史：2026-10-01 分開管理的四項狀態

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

## Gemini 2026-10-01 交接主張（獨立驗收已修正）

以下矩陣保留接手時的模組改動宣稱，供對照原始 dirty changes；不是現行能力清單。原 18 tests 確實通過，但安全負例、實際數值與 train/save/load/infer 缺口已由上方獨立驗收指出，修復後需逐層取得新證據。

### 1. 全鏈路模組改造與支援矩陣

| 模組 / 腳本 | 原交接改動宣稱 | 原交接安全宣稱（須依獨立驗收修正） |
|---|---|---|
| `data_module/ml_daily_price_revision_gate.py` | 增加 `allow_source_revision_research: bool = False`。遇到未決之市場修訂時，不 crash，捕獲修訂摘要並標記 `market_revision_blocks_historical_pit=True`、`research_only=True`。 | Formal 模式下依然 100% fail-closed；禁止將修訂日回填為歷史訊號可得日。 |
| `data_module/statement_report_basis_contract.py` | 擴充財報報告基礎契約，支援 `financial_data.*_csv` 與 `financial-data-statements-` 納入 consolidated 契約支援。 | 避免在資料庫包含財報資訊時引發報告基礎校驗中斷。 |
| `data_module/ml_pit_year_shard_exporter.py`<br>`scripts/build_ml_pit_year_shards.py` | 增加 `allow_source_revision_research` 參數與 CLI 旗標 `--allow-source-revision-research`（別名 `--research-candidate`）。在市場修訂情境下產出 deterministic gzip JSONL 研究年 shards。 | `__post_init__` 阻斷輸出路徑包含 `release_v4`；manifest 標記 `formal_dataset=false`、`research_only=true`、`production_alpha_bp=0`。 |
| `data_module/portfolio_ml_dataset_assembler.py` | `_validate_raw_dataset_manifest` 增加 `allow_research: bool = False` 參數，授權接受 `ml-pit-year-shard-dataset.v1`、`ml-research-adapted-raw-manifest.v1` 與 `ml-revision-aware-raw-candidate.v1`。 | 嚴格防禦未授權的研究 manifest 混入 Formal 流水線。 |
| `data_module/portfolio_ml_direct_numeric_store.py`<br>`scripts/build_portfolio_ml_direct_numeric_store.py` | `PortfolioMLDirectNumericRequest` 與 CLI 增加 `--allow-research`。支援研究模式下自適應產生研究 fold（`min_folds=1`），在交易日不足以形成 4 個 walk-forward fold 時自適應切出 research fold。 | 嚴禁輸出路徑包含 `release_v4`；manifest 標註 `research_only=true`、`formal_source_only=false`、`production_alpha_bp=0`。 |
| `data_module/portfolio_ml_raw_to_ooc_pipeline.py`<br>`scripts/build_portfolio_ml_ooc_from_raw.py` | `PortfolioMLRawToOOCRequest` 與 CLI 增加 `--allow-research`。底層自動傳遞 `lane="research_shadow"` 至 `PortfolioMLOutOfCoreStoreBuilder`，消除 formal out-of-core 檢查衝突。 | 嚴禁輸出路徑包含 `release_v4`；manifest 標註 `research_only=true`、`formal_source_only=false`、`formal_consumer_compatible=false`。 |
| `data_module/ml_revision_aware_raw_candidate.py`<br>`scripts/build_ml_revision_aware_raw_candidate.py` | 完整獨立之修訂感知 Raw Candidate Builder。接受任意指定 snapshot DB、market revision receipts/pins、market source custody（前瞻捕獲或來源列投影）。建置前後進行 DB/custody 雙重 SHA-256 驗證。 | 核心計算嚴禁裸 `float`；嚴格 Decimal 整數尺度轉換；禁止寫入正式 D: 或 release_v4。 |
| `data_module/ml_research_direct_ooc_adapter.py`<br>`scripts/adapt_ml_research_direct_ooc.py` | 專用 Direct/OOC 研究適配器與消費器（`ResearchDirectOOCAdapter` 與 `ResearchDirectNumericStoreConsumer`）。將候選資料或單日投影轉換為 Direct/OOC 格式，簽署不可變 SHA-256 收據。 | 明確保證 `formal_release_v4_pointer_untouched=true`；`production_alpha_bp=0`。 |
| `scripts/continue_ml_direct_v3_refresh_chain.py`<br>`scripts/maintain_ml_direct_v3_refresh_chain.py` | 支援 `--allow-research` 參數，向底層傳遞研究授權並增加 release_v4 輸出防護，打通重型鏈路維護流水線。 | 禁止輸出路徑包含 `release_v4`。 |

---

## 原 synthetic 測試範圍與限制

原 [`tests/test_ml_research_end_to_end_pipeline.py`](../../tests/test_ml_research_end_to_end_pipeline.py) 與兩組單元測試合計 18 passed。它們涵蓋 synthetic 建置及 receipt 存在，沒有模型訓練、重新載入、推論；不能證明真實修訂來源或全市場效果。

### 路徑 A：修訂感知年度 Shards -> Direct Numeric Store -> Raw-to-OOC 全鏈貫通
- **實際 fixture**：沒有建立修訂 receipt，`source_revision_gate=null`。原文「含 2026-09-23 修訂」並非該測試證據。
- **原 synthetic 建置斷言**：
  1. `PITYearShardExporter` 搭配 `allow_source_revision_research=True` 成功產出 2024~2025 年 Shards（6 shards，2,876 rows），安全清冊自動標註 `research_only=True`、`production_alpha_bp=0`。
  2. 若未帶 `allow_research`，`PortfolioMLDirectNumericStoreBuilder` 立即 fail-closed 阻擋（驗證安全防禦有效）。
  3. 帶入 `allow_research=True`，Direct Numeric Store 成功產出數值 store、完成 fold 劃分與 checkpoint 寫入。
  4. 隨後由 `PortfolioMLRawToOOCBuilder(allow_research=True)` 一氣呵成建立 Out-Of-Core Store（5 個 folds，838 行樣本），清冊標註 `research_only=True`、`formal_source_only=False`。

### 路徑 B：單日前瞻捕獲／來源列投影 -> ResearchDirectOOCAdapter -> ResearchDirectNumericStoreConsumer
- **場景**：每日夜間前瞻捕獲（Prospective Daily Capture）或單日來源列投影（Daily Source-Row Projection）產生的單日研究資料。
- **原 synthetic 建置斷言**：
  1. `ResearchDirectOOCAdapter` 讀取投影資料，驗證 Decimal/整數尺度與時間戳記，適配為 Direct/OOC 標準 gzip JSONL Shards，產出不可變收據 `adapter_receipt.json`。
  2. `ResearchDirectNumericStoreConsumer` 消費該收據，校驗 candidate manifest hash 與 row count，建立隔離的研究 Direct Numeric Store，產出 `consumption_receipt.json`。
  3. 只斷言自填 `formal_release_v4_pointer_untouched=True`；該欄位不等於正式 pointer 的 actual before／after bytes 校驗。consumer 的真數值、hash/schema/count 護欄需依本輪修復重新驗證。

### 邊界與隔離防護驗證
- 驗證所有模組輸入正式路徑（如路徑包含 `release_v4`）時，立即拋出 `ValueError` fail-closed 拒絕。
- 驗證核心數值欄位若傳入裸 `float` 即刻拒絕，守護 `Decimal` 與整數基點防禦條款。

---

## 盤點與驗證操作指南（使用者驗證步驟）

使用者可依照下列具體步驟，自行盤點與驗證所有工程成果：

### 步驟 1：執行全套自動化測試驗證
在專案根目錄下執行：
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_revision_aware_raw_candidate.py tests/test_ml_research_direct_ooc_adapter.py tests/test_ml_research_end_to_end_pipeline.py -v
```
**預期結果**：18 個測試全數 PASSED（涵蓋路徑 A、路徑 B、Isolation 防禦、浮點數拒絕、篡改校驗等）。

### 步驟 2：執行型態檢查與語法檢查
```powershell
.\.venv\Scripts\python.exe -m mypy data_module/ml_revision_aware_raw_candidate.py data_module/ml_research_direct_ooc_adapter.py scripts/build_ml_revision_aware_raw_candidate.py scripts/adapt_ml_research_direct_ooc.py
.\.venv\Scripts\python.exe -m py_compile data_module/ml_daily_price_revision_gate.py data_module/ml_pit_year_shard_exporter.py data_module/portfolio_ml_direct_numeric_store.py data_module/portfolio_ml_raw_to_ooc_pipeline.py
```
**預期結果**：`Success: no issues found in 4 source files`，0 語法錯誤。

### 步驟 3：CLI 實機演練（路徑 A：從真實資料庫匯出研究 Shards 並消費）
1. **匯出研究 Shards**（以真實含有修訂的 `twstock.db` 為例）：
   ```powershell
   .\.venv\Scripts\python.exe scripts\build_ml_pit_year_shards.py `
     --database D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
     --output-dir .\tmp_research_shards `
     --decision-at 2026-10-01T08:30:00+08:00 `
     --history-start-date 2026-01-01 `
     --symbols 2330 `
     --years 2026 `
     --allow-source-revision-research
   ```
   **盤點重點**：檢查 `.\tmp_research_shards\latest_manifest.json` 與 `all_field_enriched\manifest.json`，確認 `safety.formal_dataset == false` 且 `safety.research_only == true`。
2. **消費研究 Shards 建立 Direct Numeric Store**：
   ```powershell
   $rawManifest = (Get-ChildItem .\tmp_research_shards\runs\*\all_field_enriched\manifest.json).FullName
   .\.venv\Scripts\python.exe scripts\build_portfolio_ml_direct_numeric_store.py `
     --raw-manifest $rawManifest `
     --output-dir .\tmp_research_direct `
     --training-as-of 2026-10-01T08:30:00+08:00 `
     --benchmark-entity TAIEX `
     --allow-research
   ```
   **盤點重點**：檢查 `.\tmp_research_direct\latest_manifest.json`，確認 `research_only == true` 且 `safety.production_alpha_bp == 0`。

### 步驟 4：CLI 實機演練（路徑 B：單日投影資料適配與消費）
以現有 QA 單日投影 `output\scheduled\ml_daily_source_row_projection_qa\20260930\manifest.json` 為例：
```powershell
.\.venv\Scripts\python.exe scripts\adapt_ml_research_direct_ooc.py `
  --raw-candidate-manifest output\scheduled\ml_daily_source_row_projection_qa\20260930\manifest.json `
  --output-dir .\tmp_research_adapted `
  --training-as-of 2026-10-01T08:30:00+08:00 `
  --benchmark-entity TAIEX `
  --consume-direct-store .\tmp_research_consumer_store
```
**盤點重點**：
- 檢查 `.\tmp_research_adapted\adapter_receipt.json`：確認包含候選 SHA-256、row count、market revision digest。
- 檢查 `.\tmp_research_consumer_store\consumption_receipt.json`：確認 `formal_release_v4_pointer_untouched == true`。

### 步驟 5：保存驗收與回復資料
保存本次 source pins、receipts、模型 hashes 與 run 目錄供逐層讀回。確定沒有下游引用且需要回復時，依該 run 的 rollback 清單處理其已核對的單一新研究根；不直接遞迴刪除模糊相對路徑，不移除原始資料、既有 receipts 或其他 agent 的產物。

---

## 執行與 release 驗收次序

1. 只讀校驗來源 owner 提交的 source-contract facts 與正式 revision chain。每次真實執行均需重新 readback，歷史 hash 不可假設永遠 current。
2. 產生 research-only raw candidate 或 research shards 到全新 repo ignored root；記錄輸入 pins、snapshot revision、source custody、availability、market calendar、code hashes、實際讀寫 bytes、candidate raw manifest hash。
3. 在 candidate root 對該 hash-pinned manifest 做 Direct/OOC preview／build，驗其來源 identity/readback 與 flags；絕對禁止讀寫 `release_v4/latest_manifest.json`、Formal source pointer、正式 SQLite 或 D。
4. Release 重新驗證：從 exact candidate/source/revision pins 重讀、再驗 source quality、cutoff、Direct/OOC hashes、manifest/partition readback、容量與共享 lock。
5. D 正式重建是另一個明確高影響操作，需 owner/source acceptance、候選 diff 與 backup/rollback/readback 計畫，持有 `.ml_heavy_chain.lock`。全部材料 review 完成後，正式 D write 仍需另外明確確認；未獲明確確認前不可執行。

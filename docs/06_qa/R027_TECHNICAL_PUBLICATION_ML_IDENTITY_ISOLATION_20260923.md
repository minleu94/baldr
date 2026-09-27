# R027 technical publication／ML identity 隔離實驗報告

## 2026-09-27 新 logical-time revision 最終狀態

使用者接受的 revision B 已完成 full8 gate與獨立 source/runtime review。結果及 exact scope/hash 記於 [R027 logical-time acceptance revision addendum](R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)。本報告下方 9/23 與 post-Qt strict receipts保持歷史原貌：原 strict仍為 `INCONCLUSIVE`，不回填新版本 PASS。Root其後正式接受scoped R028 production migration；R031 attempt6 current relevant regression及mandatory checks已由root接受；目前為提交前snapshot，staged review與commit結果以Git history及root最後交付為準。R028結果見 [implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。

- 日期：2026-09-23
- 裁定：`INCONCLUSIVE`
- Evidence 狀態：latest completed old-strict result與raw receipt見下方2026-09-27 checkpoint；該次source graph早於新revision owner edits；保留原始9/23、848-difference與各版receipt，不覆寫。
- 架構阻擋：`AB-ML-01`（OPEN）
- 暫時機制：`TMP-ML-02` 保持 ACTIVE
- 後續（原strict裁定）：9/23時R028保持BLOCKED。本報告上方2026-09-27 current status記錄versioned revision full8 PASS與R028 scoped migration其後均已接受；這些bounded裁定不是整體重構完成判定。

## 2026-09-27 使用者接受的新驗收版本（full8 PASS；原strict仍INCONCLUSIVE）

使用者已明確接受新logical-time acceptance revision（proposal B）；root full8及boundary獨立review均PASS。Summary SHA e39f7d2e5ccb3e2a6b8d30be3d595ad2b06a6837ab9a56f9e3689bc221b58980、raw SHA 5e1f162cc569c49797d0f9fc9fc72b6d7f4fba41734afcec627a6d9684f372c0。Root最初decision核准R028實作開始；其後另有正式R028 acceptance，記於下方current addendum。這是與原strict gate分開的版本化驗收，不回溯變更原strict。原9/23 oracle、848差異、raw receipts與原INCONCLUSIVE verdict均保留；latest 9a19 receipt仍是原strict gate的8/8 INCONCLUSIVE、947 differences。

新revision須精確比較source-owned logical phase-call/token count/order、event／publication phase與publication point；真正使用production method中的phase port，不接受observer stamping。此token只表示來源呼叫順序及次數；原產品沒有canonical publication timestamp，production不消費token作artifact時間欄位，也不新增schema。raw wall/perf、mtime、WAL／SHM與reader evidence全數保留，但只依新revision不要求跨process physical values逐值相同。每個原snapshot phase的main DB raw bytes／SHA／size仍exact，且逐phase核對committed visibility、完整rows/schema/key/source identity及fresh reopen readback；commit/rollback、failure、cancel、retry/recovery不得遺失、重複或形成半套狀態。其餘原exact output、Direct15與負控仍保留。baseline與candidate各自收集、不可共用新helper作兩邊oracle；clock negatives須實際改production call site/phase並被拒絕。詳見ignored QA驗收追蹤 `output/qa/refactor_completion_20260927/USER_ACCEPTED_IMPLEMENTATION_TRACK_20260927.md`。Stage 1的clean-case interim evidence列於下方；不是新revision gate PASS。

### 2026-09-27 phase-port／原SQLite快照 bytes interim review

`phase_port_stage1_freeze_v2.json`（SHA-256 `e37cf120589b44e4d1a07aac5f741518f0d829a4c6b067b355ddb85c0cf57f9b`）凍結6個owner source/test inputs及3個read-only dependency hashes；source review核對所有hash與目前working tree一致。既有 `record_phase` 在原 `sqlite_main_db_before_checkpoint` read保存可選raw bytes、原query-only reader close後再讀raw bytes；clean baseline與candidate各return code 0，11個source-issued phase calls/token sequence一致，該phase原snapshot前／reader close後的main DB raw bytes、SHA、size逐項相同。每個worker另以兩個fresh `mode=ro`／`query_only` connections close/reopen讀回80 rows與schema/key/source identity，reader間結果相同且DB bytes未變；final checkpoint前、後讀值分開保存且兩側一致。Focused既有R027 candidate test file為13P/0F/0E、0.878秒，py_compile通過；舊strict comparator仍為`incomparable_clock`／`INCONCLUSIVE`。

此為clean-case interim evidence，root接受其有限證據範圍；不是新revision PASS或R028解鎖。尚無新版gate、production call-site負控、failure/cancel/recovery expected-outcome matrix、全8 cases或完整route；目前receipt沒有驗證新revision的跨worker failure recovery。原strict evidence／raw fields與oracle保持未改。

## 2026-09-27 latest completed old-strict source-graph checkpoint

Latest completed old-strict post-Qt lifecycle runtime full8 receipt `r027_post_qt_lifecycle_root_all_20260927.json`（SHA-256 `9a19c3ac9cc28d6c07ecda6506e1f4f35b30a7ffa4cf74cb915f531e414f5ef7`；summary `DF4533DBA4F72523E047DFBD458CED725114DFC35F17203F221E96100921992F`；scope `BED829EC6706671E98CE938C08DCA7674E5639E1A6BDE56D22512943332F0AB1`）。此run在兩個Qt callback runtime修補後完成，runner自然exit 1代表strict R027 gate未通過，projector exit 0；8/8 `INCONCLUSIVE`／`incomparable_clock`、0 semantic、947 strict differences、R028 unlock=false。各case counts依序為clean81、same-input143、partial67、unchanged79、cancel/resume117、source-change153、failure/recovery137、publication-failure/recovery170。16 workers／16 unique positive PID／rc0、完整ordered case-mode與wrapper/receipt identity、pairwise-isolated roots均成立；6/6 negative controls detected。1,233 selected paths前後相同、changed=[]、HEAD unchanged；Direct15與5 pinned fixtures另有全數hash-match custody。舊855／1,058、bb68與更早版本保留各自歷史，不覆寫。

本輪947個strict differences分類為738 event-clock、143 file-mtime/publication snapshot、64 SQLite snapshot-reader lifecycle及2 SQLite transient snapshot SHA。這兩個transient差異只在`publication_failure_recovery`，精確為`$.timings.final_sqlite_transient_files_before_checkpoint.twstock.db-shm.sha256`與`...twstock.db-wal.sha256`；其他raw OS／publication mtime／WAL／SHM／reader fields仍strict對照。21個`sqlite_main_db`差異均為`mtime_ns`，此namespace沒有SHA／size差異。1,233 selected paths之worker loaded-source inventory為1,488→1,492；所有pre-existing source hashes/fingerprints穩定，另列3個late-loaded repository modules，不與selected scope混同。9/23凍結oracle bytes實核為17,045,681 bytes、SHA-256 `4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616`，路徑為`C:/Users/archi/AppData/Local/Temp/r027-r023-freeze-all-20260923-dd1c0d4c58404dfa8d94a6275de96f2a/r027_comparison.json`；repo舊summary引用的另一歷史位置缺失並標stale。這不證明所有physical bytes相等或差異根因。raw receipts與strict comparator不變。

DBManager.execute_query的unclosed connection是另個已bounded accepted resource fix：未修時25/25 API query返回後仍觀察到OS handle，明確close control為0；修後7/7 handle observations為0，真connection success/error/row/dtype checks及相鄰route共92P。此修正保留原connect defaults、with-connection commit/rollback與materialized query result semantics；它不是R027 947 differences的單一因果證明。原strict仍INCONCLUSIVE，AB-ML-01仍OPEN；versioned revision full8已PASS，R028 scoped migration其後亦已由root接受；attempt6 current 288-path relevant regression及mandatory checks已由root接受；此處保留為提交前snapshot。

## 使用者決策前的具體技術方案（歷史提案；B已接受，未實作）

以下A／B為使用者裁決前的技術方案紀錄。使用者後接受B並另立versioned gate；方案A未採用，不作為目前R028阻擋理由。原strict comparator、848 frozen oracle、raw receipts、negative controls、Direct15與5 pinned paths均不變。方案A當時建議維持UpdateService owner、將conditional R028搬移視為不適用，並在使用者接受整體完成條件變更後結束該conditional work；這不代表R027 PASS。

方案B只能在使用者明確接受新的versioned acceptance revision後採用，不能稱原R027 PASS。將固定logical publication clock、呼叫數、事件順序、phase與publication point作精確比較；額外clock call或publication phase改變仍失敗。raw wall/perf clock、真實mtime與WAL/SHM/reader snapshots原樣保留於receipt，標為獨立OS/lifecycle observations。新revision仍精確要求case/mode覆蓋、publication paths與輸出bytes/hash/size、CSV row/key/order/schema/dtypes、numeric/mask bytes、Direct15與允許的serialized identity evidence相等；SQLite以獨立reopen reader確認committed visibility、rows/schema、rollback/commit邊界、失敗／取消／重試後恢復與readback一致。main DB raw bytes/hash/size繼續exact；若任何WAL/SHM或mtime由gate轉為diagnostic而非equality field，須逐欄列明並由使用者接受此完成條件改變。此方案不放寬資料／模型語意，也不排除可修lifecycle defect；current evidence不自動批准採用。

## 原始 2026-09-23 實驗結果（歷史 baseline）

以下內容保存原始candidate relocation、848-difference oracle與原實驗限制；不替代上方post-REC-05／ML2 current-source full8結果。

8 個合成情境均由舊路徑與候選路徑的獨立子程序完成。每案語意欄位差異為 0；固定輸入下的 publication path、最終輸出檔案 SHA／大小、列與 numeric/mask bytes、warmup、Direct 15-path identity、runtime integrity、resume 正反例及事件順序均相等。4/4 negative controls 均被 comparator 偵測。

R023 freeze 後的新 full TEMP receipt 記錄 candidate extraction source SHA `sha256:df1d04445f23ff07f2eb45eab7b024b819ba511928b8cc2d25ee3bc3c69dae88`，16 個 worker receipt 的 `update_service_method_source_sha256` 均相同；projector 執行時讀取的 `app_module/update_service.py` bytes SHA 亦相同。機讀摘要的 `run.head` 是 projector 執行時讀取的 repository HEAD metadata：`777c06d039a7676475f7f6eecebf9a24bb790692`。Full receipt 沒有記錄 worker 啟動／執行時的 HEAD，因此這個 `run.head` 不能獨立證明 workers 執行時所在的 commit；不能將該 metadata 當作 worker 執行時 commit 的證據。若重新投影時 HEAD 不符預期，或 source bytes 與 candidate extraction SHA 不同，projector 會拒絕輸出；不得沿用不匹配的 projection。

仍不能判 `PASS`：子程序各自使用真實 wall／monotonic clock，且 publication 檔案有各自的 `mtime_ns`。8 案共有 **848 個 exact timing／snapshot 差異**，沒有共用可注入的固定 clock，也沒有 canonical publication timestamp 欄位。依 R027 無容差、全等才可 PASS 的要求，不能把兩條 process 的 timestamp 以容差視為一致。候選也只是由原方法 AST 抽出的 relocation copy，未實作一條獨立、實際不同的 orchestration。因此本證據不能支持正式搬移。

## 範圍與隔離（原始實驗歷史細節）

- 只新增本實驗 harness、合成 fixture、機讀證據摘要與本報告；未修改 `app_module/update_service.py`、Direct/OOC source／registry／15 frozen paths、模型、正式資料、scheduler、checkpoint 或 artifact。
- 16 個 worker（每個 case 的 baseline／candidate 各一個）為獨立子程序，各自使用 `PROFILE=test`、隔離的 TEMP data/output root；未觸及正式資料。每個 worker 合成輸入為 1101、2330 兩檔、各 40 個交易日，來源 hash 為 `sha256:a74becf8f3491474b1db9a14471414967fe55758c5b7b85ee219baccb86ca29b`。來源含缺值與零值；source-change case 只在 TEMP DB 加入兩列合成資料。
- 主要執行環境為 Windows 10 build 26200、repo `.venv` Python 3.11.9、pandas 2.3.3、NumPy 2.3.5。此為合成 fixture 相容證據，未載入模型或執行推論。
- Harness 先驗證 TEMP run root 與 repository／正式 data/output root 不相交。worker 的原始 loaded-file inventory 從 pre-run **1,478** 增至 post-run **1,482**；原有 1,478 entries 的 raw SHA 與 source-code fingerprint 均未改變（`source_inventory_stable` 的語意只表示此事，不表示 path set 不變）。新增 3 個 repo source paths：`data_module/excluded_daily_price_revision.py`、`data_module/formal_technical_raw_alias_repair.py`、`data_module/historical_session_revision.py`；另新增 1 個 third-party runtime path：`.venv/Lib/site-packages/pandas/io/formats/csvs.py`。16 workers 的增量 path set 一致，fingerprints 收於機讀摘要。
- DB/WAL/SHM 的 phase snapshot 只讀取並保存診斷。只有各情境的計算、取消／resume／recovery 全部完成且 worker 關閉後，才對 TEMP DB 執行一次 `PRAGMA wal_checkpoint(TRUNCATE)` 並擷取 final publication；沒有在 partial→resume 或 recovery 中途改寫 DB 狀態。原始 pre-checkpoint main DB、WAL、SHM 的 bytes/hash 與 mtime 診斷保留在 full receipt，未以 checkpoint 後 main DB 一致掩蓋 timing blocker。

## 兩路執行與證據界線

- **Baseline：** 每個 baseline 子程序直接呼叫未修改的 `UpdateService.calculate_technical_indicators`。instrumentation 觀察 production `TechnicalIndicatorCalculator.calculate_and_store_indicators` writer 與 `DBManager.connect` transaction/commit/rollback；沒有替換正式 writer 或改寫 production code。
- **Candidate：** runner 將同一 production method 以 AST source extraction 複製到 run-specific TEMP `CandidateTechnicalIndicatorJob.run`，以 forwarding wrapper 提供該 worker 的 `UpdateService` config/helper，再在獨立 candidate 子程序呼叫。Full receipt 的 candidate extraction source SHA 與 16 個 worker 結束時 receipt 記錄的 method source SHA 均為 `sha256:df1d04445f23ff07f2eb45eab7b024b819ba511928b8cc2d25ee3bc3c69dae88`；projector 當時讀取的 production source SHA 亦相同。`run.head` `777c06d039a7676475f7f6eecebf9a24bb790692` 是 projection-time metadata，receipt 不記錄 worker-time HEAD。method 位於 `app_module/update_service.py:4614–5421`（808 lines），擷取方法 SHA 為 `sha256:7efb02d06b7a76bd273d69693468bfd3e89d3912980019d706d53725fe2767c7`；TEMP candidate module SHA 為 `sha256:6a5a9156170ad3cb0882ebbcf87f6569430206d49ad1b45f4d26c115f861d173`。擷取期間 production source 前後 bytes 相同。
- 比較器在 runner parent process，獨立比較 worker receipts；它不匯入 candidate class，也未以新抽出的 candidate helper 作 oracle。兩路共用的只有 synthetic input／measurement fixture 與原有 production calculator/writer/DB helpers。
- **限制：** candidate method body 與 baseline 完全相同，並透過相同既有 helpers/writer/DB 實作運作；沒有驗證真正抽離後的不同 orchestration、正式 wiring 或實際 ML consumer 的 read/availability/cutoff 競爭。這是 bounded relocation/binding smoke proof，不是獨立實作間的語意等價證明。實驗沒有載入 Direct/OOC 模型、執行 ML inference，亦未觸碰任何正式 checkpoint。

### 最小 clean-run proof

`clean` case 的兩條獨立 worker 都成功執行未修改 production method、指標 writer、SQLite transaction/commit，並發布相同的 4 個最終 paths；baseline/candidate 語意差異 0、事件種類與順序一致。Direct runtime identity 在計算前後穩定。這證明 harness 確實到達 production orchestration/writer/commit 邊界。Clean case 有 71 個 exact clock／mtime 差異（62 event clock、9 file mtime）；沒有固定 clock seam，因此 clean proof 本身已不能 PASS。

## 比較欄位與 R006 identity

比較器對每個 case 的 baseline/candidate receipts exact compare 下列欄位，不使用時間 tolerance：

1. Runner 分別啟動 baseline/candidate process，並在 raw receipt 記錄 mode、PID、worker return code。本次是 8 baseline + 8 candidate、16 個不同 PID、return code 全為 0。`compare_workers` 對任一 nonzero return code 回報 `worker_error`，但 `mode`／PID／return code 不在 `flatten_comparable` 中，不做兩路欄位逐項比較。`flatten_comparable` 會比較 PROFILE、isolated input hash 與 data/output root containment。
2. publication 完整 path set、排序、每檔 SHA256／byte size；final DB 與 CSV 的 parsed row keys、欄位順序、dtype、shape。
3. numeric buffer 的 bytes SHA、shape、dtype；feature mask bytes SHA、shape、dtype；warmup row count、leading ADX null count。
4. event kind/order、各事件 wall time／monotonic time、publication file `mtime_ns`、SQLite main DB/WAL/SHM pre-checkpoint 診斷、transaction／commit／rollback trace。
5. 15 個 Direct frozen source path 的 ordered set、每檔 raw SHA256、source-code fingerprint、loaded code/constants fingerprint 與 match flag、stable computation identity、runtime dependency payload hash、pre/post integrity。
6. same-identity checkpoint resume accept、changed-identity resume reject、拒絕分類，以及每個 scenario phase 的結果／source mutation 狀態。

R006 對照結果：**15/15 non-empty ordered paths 完全一致**；15 個 raw file SHA 全數 match R006。stable identity 為 `sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c`，runtime dependency payload 為 `sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087`，均 match R006。loaded state 為 **14/15**，同 R006；`teacher_input_source_producer.py` 有 disk SHA／source fingerprint，但未 import，沒有將它記作 loaded。此判定不等同完整來源 inventory path set 未變；其 late-loaded files 列於上段及機讀摘要。

兩路每個 worker 的 synthetic checkpoint fixture 均接受同 identity resume，並以 `DirectCheckpointProvenanceError`／`computation_identity_drift` 拒絕 changed identity resume。fixtures 是 TEMP 新建、不同 identity，未混寫 run，也未讀寫正式 checkpoint。

| # | R006 frozen source path | raw SHA256 |
|---:|---|---|
| 1 | `data_module/portfolio_ml_direct_numeric_store.py` | `017ae82cc6dd3466a6a1e3a17eca1edc88a94d114f03783acb4c14f90cc41509` |
| 2 | `data_module/portfolio_ml_dataset_assembler.py` | `f8fd70c43bf18a3e507e0b44325aaf45a856a537829af7d7d0f2a0c7d6cf3b91` |
| 3 | `data_module/portfolio_ml_out_of_core_store.py` | `11ab46b71e81b0d72b6a39ec587454a9d332dc7360e53eb58d745c66ab09225a` |
| 4 | `data_module/ml_storage_capacity.py` | `60202f419c06015a1d283579fd8ce204f6f7218a2348f3d74f4ec3fabdc4bb15` |
| 5 | `data_module/ml_pit_shared_block_resolver.py` | `1ec0b283a5fa8a1eb9c69e87cdca25ccbf04381743944c62a1df6fc8e90e2709` |
| 6 | `data_module/ml_direct_shared_block_resolver.py` | `9972bcd53fdc2a02abea47487f8c62f92b62895afde93e32212bd1661b98a4c4` |
| 7 | `data_module/formal_portfolio_ledger.py` | `1859ba515a4c4a33e61b139bb2a2b72eed93802f6c9ad00d81333bf74967112f` |
| 8 | `data_module/rule_champion_snapshot_service.py` | `99c45420050e0ac78c17341dc4f9cc530435882b78fa0cc9f4a2dd5726b05645` |
| 9 | `data_module/teacher_input_source_producer.py` | `68bca304f7d2505d3f6a394f44a20b0507e99169600e790d119f171a9e11d5ad` |
| 10 | `ml_module/allocation_training_service.py` | `b898d97cbcc7033ff53fe34c4f3ffedf53542942718a257a2db6a733f62881f6` |
| 11 | `ml_module/allocation_contracts.py` | `dd18d81a5409b8aa176e77d89cbcd515da41e8140ae7f9b248c4ca526fc84343` |
| 12 | `ml_module/allocation_teacher.py` | `c34f6ce1023ab1eb8f3899819cbb93701ab198c0f5bfcc20287d8e36f75477f1` |
| 13 | `ml_module/immutable_ml_block_store.py` | `cd14ef0b8da2af8e1953f2f28c299277a779a9ffb1f06fb5f6d86057f7ac3400` |
| 14 | `ml_module/purged_walk_forward.py` | `345edaccddfcc658d63bd1e0a69508594954eb9d72e2c48e1d9944c5e487ff4a` |
| 15 | `data_module/ml_price_availability_contract.py` | `6d503e6c2d77a16b0a49efdddb3770971b774be9d563d9668235a84e0bf6af9b` |

逐檔 source-code／loaded-code/constants fingerprint 與 match flags、各案 publication 檔案 SHA/size、numeric/mask/row hashes 和 warmup 數據，見[機讀合成摘要](R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json)。摘要由 [project_receipt.py](../../scripts/experiments/r027/project_receipt.py) 使用 Python stdlib 從 full receipt 投影產生；它在投影時核對 repository HEAD 與 `--expected-head`、並核對當前 source SHA 與 receipt candidate extraction SHA，漂移時拒絕產出。摘要的 `run.head` 僅表示 projection-time HEAD，不是 full receipt 的 worker-time commit attestation；投影未讀寫 production state。

## 8 個 case 結果

每列的「語意差異」指除 clock／mtime／SQLite transient timing diagnostics 以外的嚴格比較差異；所有 8 案均為 0。baseline/candidate 最終 publication bytes/path set 相等，phase outcome 與 event order 相等。每案 exact timing 差異分類沒有折抵或容差。

| Case | Fixture／phase outcome（baseline 與 candidate 相同） | Final paths | semantic diffs | exact timing／snapshot diffs |
|---|---|---:|---:|---:|
| `clean` | `clean_full_synthetic_publication` 成功 | 4 | 0 | **71**（62 event clock、9 file/mtime snapshot） |
| `same_input_rerun` | 首次發佈與相同輸入再次發佈均成功 | 4 | 0 | **129**（116 event clock、13 file/mtime snapshot） |
| `partial` | `target_stock=1101` 的 targeted publication 成功 | 2 | 0 | **65**（52 event clock、11 file/mtime snapshot、2 final transient hash） |
| `unchanged` | 以 `force_all=false` 執行 `unchanged_source_skip` fixture 成功 | 3 | 0 | **77**（62 event clock、13 file/mtime snapshot、2 final transient hash） |
| `cancel_resume` | cancellation 中止（預期 false）；`cancel_recovery_force_all` 恢復成功 | 4 | 0 | **103**（92 event clock、11 file/mtime snapshot） |
| `source_changed_during_run` | snapshot 後向 TEMP source 加入 2 rows；重新 publication 成功 | 4 | 0 | **139**（126 event clock、13 file/mtime snapshot） |
| `failure_recovery` | 注入 calculator failure（預期 false）；停用故障後恢復成功 | 4 | 0 | **123**（112 event clock、11 file/mtime snapshot） |
| `publication_failure_recovery` | SQLite trigger 注入 publication failure（預期 false、觀察到 rollback）；移除 trigger 後恢復成功 | 4 | 0 | **141**（116 event clock、23 file/mtime snapshot、2 final transient hash） |
| **總計** | **8/8 cases；16/16 worker processes return code 0** | — | **0** | **848**（738 event clock、104 file/mtime/publication snapshot、6 final SQLite transient hash snapshot） |

Final publication paths 逐案比較亦完全相等：`clean`、`same_input_rerun`、`cancel_resume`、`source_changed_during_run`、`failure_recovery`、`publication_failure_recovery` 的完整 set 為 `data/_test/meta_data/all_stocks_data.csv`、`data/_test/sqlite/twstock.db`、`data/_test/technical_analysis/1101_indicators.csv`、`data/_test/technical_analysis/2330_indicators.csv`；`partial` 為 SQLite DB 加 1101 指標 CSV；`unchanged` 為 SQLite DB 加 1101、2330 指標 CSV。逐案兩路每個檔案的 byte size/SHA 和完整 row/numeric/mask hash 均在機讀摘要中。

Synthetic numeric 輸出以 clean/cancel/failure 等同一輸入情境為例，table shape `[80,31]`，numeric buffer `float64 [80,29]`，mask `uint8 [80,29]`；兩檔各 40 rows，leading ADX null 27。source-change 情境為 `[82,31]`，numeric buffer `float64 [82,29]`、mask `uint8 [82,29]`，兩檔各 41 rows、leading ADX null 27。各案 baseline/candidate bytes/hash 相同；完整逐案 row/schema/dtype/hash 以機讀摘要為準。

## Negative controls

Comparator 直接針對 clean baseline receipt 的欄位做單一突變，每項均產生 1 個差異並被偵測：

| Control | Injected change | Detection |
|---|---|---|
| path | 將 `data/_test/meta_data/all_stocks_data.csv` 改名為 `negative-control-renamed/...` | detected，差異欄位 `publication_paths[0]` |
| byte | 將 all-stocks CSV SHA 改為 64 個 `0` | detected，差異欄位該檔案 `.sha256` |
| timing | 第一個 monotonic timestamp 加 `1 ns` | detected，無 tolerance |
| resume | 把 same-identity resume accepted 從 `true` 改為 `false` | detected，差異欄位 `same_identity_resume_accepted` |

**Negative controls：4/4 detected。**

## Timing gate 與無法比較範圍

R027 §7 要求 publication timestamp／時序精確相等。本 harness 沒有在 production method、writer 或 DB helper 加固定 clock seam；baseline/candidate 的 event wall/monotonic clocks 分別由各 process 取值，publication timestamps 以實際檔案 mtime 觀察。receipt 也沒有 canonical publication timestamp 欄位。因此 848 個差異是實際保存的 exact 值差異；不是 comparator 誤差，也不能透過容差改成通過。

`sqlite_transient_snapshot` 6 個差異是 partial、unchanged、publication-failure/recovery 各 2 個 final pre-checkpoint WAL/SHM hash 差異；phase-level WAL/SHM 診斷及 mtime 差異收在 `file_mtime_and_publication_snapshot` 類別（104 個）。main DB/WAL/SHM raw hashes/mtime 保留於 full receipt。每個 scenario 最後才在 worker 關閉後 checkpoint，所以 canonical final DB equality 不會抹除或取代這些診斷。事件種類／次序及 commit/rollback trace 相等，只能支持 semantic trace parity；不能證明 publication timestamp／materialization 時序 exact equality。

另未執行真實 ML model/consumer 的 infer、正式 rule-vs-ML read barrier、來源更新後 availability/cutoff receipt 或正式 checkpoint resume。source-change/cancel/resume 和 identity accept/reject 都限於 TEMP synthetic fixture。因此不能外推至 formal artifact、正式資料或 scheduler。

## 重跑方式與唯一有效 evidence

在 repo root 使用 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m py_compile scripts\experiments\r027\run_experiment.py scripts\experiments\r027\worker.py scripts\experiments\r027\project_receipt.py
$r027RunName = "r027-replay-" + [Guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts\experiments\r027\run_experiment.py --case all --run-name $r027RunName
.\.venv\Scripts\python.exe scripts\experiments\r027\project_receipt.py --receipt "$env:TEMP\$r027RunName\r027_comparison.json" --output docs\06_qa\R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json --expected-head 777c06d039a7676475f7f6eecebf9a24bb790692
```

runner 預設把 run root 與 full JSON receipt 寫到系統 TEMP，並拒絕與 repository 或 `R027_FORMAL_DATA_ROOT`／`R027_FORMAL_OUTPUT_ROOT` 相交。每個新 `run-name` 必須唯一。因 strict verdict 為 `INCONCLUSIVE`，runner 會以 exit code 1 結束；JSON 仍會保存 verdict、workers、比較結果與 negative controls。`--case` 可用 `clean` 做最小 clean proof；完整 gate 用 `all`。命令中的 `--expected-head` 只約束 projector 執行時讀取的 repository HEAD；full receipt 沒有 worker-time HEAD 欄位，此選項不能回溯證明 worker 執行 commit。

**R023 source freeze 後唯一可供 current gate review 的完整 receipt：**

- TEMP root：`C:\Users\archi\AppData\Local\Temp\r027-r023-freeze-all-20260923-dd1c0d4c58404dfa8d94a6275de96f2a`
- Receipt：`r027_comparison.json`，17,045,681 bytes
- SHA256：`sha256:4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616`
- Projection-time `run.head` metadata：`777c06d039a7676475f7f6eecebf9a24bb790692`（full receipt 不記錄 worker-time HEAD）
- Candidate extraction、16 個 worker 結束時 receipt 與 projection-time `update_service.py` SHA：`sha256:df1d04445f23ff07f2eb45eab7b024b819ba511928b8cc2d25ee3bc3c69dae88`
- Durable projection：[R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json](R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json)，97,871 bytes，SHA256 `sha256:8fa79f4b5f4c47a0751b6926f28f948aebd8fc369b6ae7ca81dd9f537bc7b5d5`
- Harness：[run_experiment.py](../../scripts/experiments/r027/run_experiment.py)、[worker.py](../../scripts/experiments/r027/worker.py)、[project_receipt.py](../../scripts/experiments/r027/project_receipt.py)

`run.head` 為 project_receipt 執行期間從 repository 讀取的 HEAD metadata；full TEMP receipt 沒有 worker-time HEAD 欄位，不能由此值推論 worker 執行 commit。此 run 的 source-level provenance 由 candidate extraction SHA、16 個 worker receipt SHA 與 projection-time source bytes SHA 組成；HEAD metadata 限於 projection 時點。

早期錯誤 evidence 仍為 discarded：`r027-clean-proof-20260923`（final comparator/path capture 修正前）、`r027-clean-proof-v2-20260923`（Direct path key／loaded state 錯誤）、`r027-all-cases-20260923`（將 WAL/SHM 誤列 publication artifact）、`r027-all-cases-stable-snapshot-20260923`（中斷且會在多階段情境中途 checkpoint）、`r027-all-cases-final-20260923`（15/15 loaded-state/path key 錯誤）。先前 R006-state receipt `r027-all-cases-final-r006-state-20260923`（`sha256:0b5acd75fb242858db32c76820a03337f9e95b9b4e8788a10be38c4b98bf9de7`）現在標記 **STALE_HISTORICAL**：它使用較早的 `update_service.py` SHA `78986ae0…`，不適用於 current method 的 publication guard/source update。R023 freeze 前 receipt `r027-all-cases-current-20260923-3cf66ab3b22d42c59445767da803e48c`（17,045,607 bytes，`sha256:e452041fa96f99894f046f4ccb33ef8c219d4ffe1cc921f9b30a41deea656359`）使用舊 source SHA `dbf18eaf…`，標記 **STALE_HISTORICAL_R023_PRE_FREEZE**；R023 已更新 source bytes 至 `df1d0444…`。只有本節列出的新完整 receipt 是 freeze 後 source 的 current gate evidence；摘要所附 HEAD 仍只代表 projection-time metadata，不代表 worker-time HEAD。

## AB-ML-01 與 TMP-ML-02 退出條件

`AB-ML-01` 由本次 exact-clock 不可比與 candidate scope 不足立案，狀態 OPEN。R028 不啟動。要重新評估 R027，至少須提供既有 production seam 可支援的共同固定 clock／literal publication timestamp，並讓獨立 candidate orchestration 在隔離 process 內證明 publication/commit timing、path/SHA、loaded integrity、numeric bytes/shape/dtype/mask、warmup、resume 正反例、cancel、failure recovery、source-change/unchanged 及 downstream identity 全部無例外 exact equality。若無法安全控制 live source 或證明 availability／call order，仍維持舊接線及拒絕 projection；不得碰正式資料補證。重新執行若存在任一差異，判 FAIL；比較面仍不可觀測則維持 INCONCLUSIVE。

`TMP-ML-02` 是既有 FINAL_MIGRATION_SEQUENCE 暫時機制登錄，本輪狀態維持 ACTIVE：Direct 15-path frozen exception、assembler/OOC/teacher source-path 限制及 `UpdateService.calculate_technical_indicators` 搬移限制均不退休。其退出條件不變：完成精確 caller/source inventory、隔離 hash/bytes/timing/resume 實驗，證明透明相容，或先明示新 identity/run 與舊 checkpoint 處置計畫；此 R027 結果沒有達成退出條件。

因 `FINAL_MIGRATION_SEQUENCE.md` 正由 R015 freeze，本輪沒有修改該共用文件或 `DOCUMENTATION_INDEX.md`。待 freeze 後供窄幅合併的 ledger status text：

```text
R027 (2026-09-23; source SHA `df1d04445f23ff07f2eb45eab7b024b819ba511928b8cc2d25ee3bc3c69dae88`, matched by candidate extraction, 16 worker-end receipts and projection-time source; projection-time HEAD metadata `777c06d039a7676475f7f6eecebf9a24bb790692`, not worker-time commit provenance): INCONCLUSIVE; AB-ML-01=OPEN; TMP-ML-02=ACTIVE; R028=BLOCKED. Current receipt SHA `4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616` has 8/8 cases, 16/16 worker return_code=0, 15/15 ordered Direct paths, semantic differences=0 and 4/4 negative controls, but 848 exact event-clock/file/mtime/publication-snapshot differences remain because the two processes have no shared fixed publication clock; candidate is an AST relocation copy over existing helpers, not an independent orchestration. Runtime inventory expands from 1478 to 1482 raw loaded files: three new repo paths and one pandas runtime path; all pre-existing entries remain unchanged. Full receipt does not attest worker-time HEAD. Do not unlock R028.
```

## 更新／完成邊界

`py_compile` 對三個 harness/projection scripts 通過。projector 會 fail closed：投影時 current repository HEAD 與 `--expected-head` 不同，或當前 production source SHA 與 receipt candidate extraction source SHA 不同時拒絕輸出。這項檢查證明投影時 repo/source 符合指定值，不回溯證明 worker-time HEAD。報告不把未執行的真實 ML inference、正式來源競爭、模型 artifact／checkpoint 讀取或固定 clock parity 宣稱為通過。沒有 stage 或 commit；repo 中其他既有工作樹變更未納入本任務。

## 2026-09-27 R028 scoped migration accepted

Root正式接受R028 scoped production migration，decision SHA `cc375897612e705e6c6c268a0ef63aa38c4f998d214a32fdd74d038567f792db`，full8 raw SHA `1a3b496973c7053c7d25612754a733cb505765667afa478be453efd2c5a19d82`。20 workers自然exit0，8 cases／8 controls PASS，3,312 source-scope files stable，Direct15／pinned5、HEAD/status stable；source與runtime獨立review無blocker。Production owner為`TechnicalIndicatorJob`，UpdateService facade lazy-delegate，既有process-pool port維持父程序單一寫入邊界。TMP-ML-02原conditional migration scope已滿足；R031 attempt6 288-path relevant regression及mandatory checks已由root接受；staged review／commit結果以Git history與root最後交付為準。原strict 9a19仍INCONCLUSIVE／947 differences，848 frozen oracle與所有strict raw receipts保持不變。詳見 [R028 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。

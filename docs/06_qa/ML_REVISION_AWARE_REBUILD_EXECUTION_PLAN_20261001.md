# ML revision-aware rebuild 執行方案與缺件分類（2026-10-01）

## 結論

本輪已完成的是前瞻 source-custody collector 的程式接線與隔離 preview；這不等於 `run_ml_raw_pit_refresh` 已自然觸發、也不會解除舊 raw builder 的 revision cutoff。候選仍為 research-only，沒有 owner source-contract acceptance、historical PIT、formal OOS 或 formal credit。

目前存在一個固定來源、hash-pinned 的 V3 **research candidate** 建置命令，但沒有能將任意已接受的新市場修訂轉成 revision-aware raw manifest、再供 Direct/OOC 隔離消費並 release revalidate 的通用受支持命令。正式 blocker 不只是等待 owner 或自然成熟：泛用 raw build／manifest 發布接線仍須工程完成。每輪自然 sample、shadow horizons 和 owner/source acceptance 是不同 gate，需分開關閉。

本方案只讀檢查 repo 指令與已保存的 ML QA。沒有建 dataset、Direct/OOC、訓練或 Task；沒有寫 D、正式 DB 或任何 pointer。

## 分開管理的四項狀態

| 項目 | 已有事實 | Close criteria |
|---|---|---|
| 前瞻 source collection | 每日 Quick updater 保存 TWSE／TPEx 原始資料 custody；ML collector 只讀 raw、receipt 與資料列，驗 hash、日期、schema／row completeness／`available_at <= observed_at`，create-only 複製到 isolated candidate。9/30 preview 的 TWSE／TPEx raw rows 為 1,095／877；候選 manifest/receipt hashes 與 flags 見 [ML raw QA](SCHEDULER_ML_RAW_REPAIR_20260930.md)。 | 下一次合法排程自行觸發 `run_ml_raw_pit_refresh` 後，核對同一次 status、自然 source receipts、候選 manifest/readback；不能以手動 preview 取代自然 runner 收據。仍不可提升為 Formal。 |
| General revision-aware raw build 與 Direct/OOC pins | 尚無 `scripts/build_ml_raw_dataset.py`；v3 restatement CLI 是限定來源的 candidate builder。scheduled Direct/OOC wrapper 解析 `release_v4` 現有 latest raw pointer，不接隔離 candidate。 | 建立受支持的 revision-aware raw manifest，含 exact source/revision/cutoff pins；隔離 Direct/OOC 明確吃該 candidate manifest/hash，完整驗 source quality、輸出 identities 與 readback；pointer 仍不更新。 |
| 自然前瞻 maturity | candidate 是 accumulator，不是 mature evidence。gate 為 5／10／20／60 trading-day horizons、至少 20 個 shadow days，且每個 horizon 至少 20 筆已成熟觀測。 | 每筆實際跨過對應 horizon，且再次驗來源可得時間、cutoff 與資料完整性；完成後另行 owner review formal/OOS eligibility。不得用當日事件或行事曆經過天數冒充成熟樣本。 |
| Source acceptance／正式 D rebuild | source owner acceptance 目前是 QA 所列後續 gate，repo 沒有一個可宣稱已接受來源的通用 acceptance object。現存 V3 source profile 是結構與 hashes 驗證，並明確禁止 PIT/OOS/promotion。 | 對指定 sources/market dates 提供可核實單位、availability、venue、source receipts／raw hashes、revision/DB identity及修訂規則；使用既有可信任 review/pin 流程作明確採納。候選 exact diff、資源／鎖／rollback/readback計畫完成後，正式 D 改寫才可另行明確確認。不得用 JSON 自宣或新造簽章代替。 |

9/30 sample 的 `available_at` 是 `2026-09-30T08:07:47Z`／`08:07:51Z`，晚於 9/30 台北 08:30 cutoff（`00:30Z`），因此不能回填 9/30 PIT。候選本身在 `2026-09-30T20:45:36.956214Z` 完成，雖早於下一日 `2026-10-01T00:30Z`，既有 QA 沒有做 10/1 cutoff qualification 或 source-owner acceptance；不能單以時間先後宣告通過。

## 現有 supported commands 與其邊界

### Restatement V3 research candidate

`scripts/build_ml_raw_dataset.py` 在 `scripts/`、`data_module/`、`tests/` 中均不存在。`scripts/build_ml_restatement_research_dataset.py` 只有 legacy wrapper，呼叫 `data_module.ml_restatement_research_dataset.main()`；它不是 revision-aware Formal raw builder。真正的 V3 research CLI 是 `scripts/build_ml_restatement_candidate.py`，輸入需 exact pin：snapshot DB/hash、source manifest/hash、official market manifest/hash，以及 unique `output-dir`／`custody-dir`。其非可執行模板如下；`<...>` 都必須在每次建置前從實際 readback 取得，不可照抄：

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
- `scripts/maintain_ml_direct_v3_refresh_chain.py` 接受 explicit `--raw-manifest`、store/training/output roots、database 和 `training-as-of`（[parser](../../scripts/maintain_ml_direct_v3_refresh_chain.py#L118)），是 Direct/OOC heavy chain。它消費現成 raw manifest，無 owner source-acceptance input；不是 raw revision builder。
- Standalone `scripts/build_portfolio_ml_direct_numeric_store.py` 與 `scripts/build_portfolio_ml_ooc_from_raw.py` 也接受 `--raw-manifest` 和明確 output path（[Direct CLI](../../scripts/build_portfolio_ml_direct_numeric_store.py#L33)、[OOC CLI](../../scripts/build_portfolio_ml_ooc_from_raw.py#L33)），能做後續 Direct/OOC stage，但不是底層 revision-aware raw build；其產物將 `formal_oos_allowed=false`。若接新 isolated raw manifest，先核對它與這兩個 pipeline 的 manifest schema／source identity compatibility，再決定是否可不改程式重用。

source revision fail-closed gate 位於 `formal_market_revision.collect_market_revision_evidence()`：驗證真實 revision 狀態並依 decision cutoff 拒絕歷史 PIT；單純讀取／改寫 status、增加 candidate 或直接重跑舊 wrapper 都不解此 guard（[gate](../../data_module/formal_market_revision.py#L324)）。

## 建議的最小工程範圍

下一批工程先做 isolated research route，不改 D writer／formal pointer：

1. 新增通用的 revision-aware raw candidate builder／CLI，輸入明確的 snapshot DB identity、`revision.json`／receipt／plan pins、market source custody與實際 availability、code/schema identity、隔離 output/custody root。此 route 不能假設一份現有 candidate source profile 對所有未來 source 都適用，也不能讓候選自行宣稱 owner acceptance。
2. 在同一 candidate manifest 內保存 full exact input/output pins 和研究 flags；建置前／後重驗輸入不可變，驗 raw／partition／source-quality／cutoff／lookahead／candidate manifest readback。遇到無 availability、未知 cutoff 或 sources 不完整要 fail closed；不得回填交易訊號可得日。
3. 優先以現有 standalone Direct/OOC CLI 做 isolated consumption proof，但需先證明新 manifest schema 是其支援的 raw-manifest contract，且為各 stage 使用獨立、create-only output。另加 focused QA 確保 Direct/OOC manifest/receipt 精確綁到 candidate raw manifest hash、row counts、training-as-of 與既有 source revision；若 standalone contract 不接受 candidate flags，才提出最小 adapter／CLI 接線，保持 scheduled `release_v4` pointer 不變。
4. 用 source-time 自查：每個決策特徵、標籤、公司篩選、標準化、corporate-action adjustment 與 benchmark 只依決策時點可取得資料；晚到或更正值只進未來時點／候選 revision，不回寫成歷史已知。對 revised-history build 做 key-by-key source revision diff 和非回歸 comparison，並記錄差異歸因。

建議新增檔案最小 allowlist先限 `data_module/ml_revision_aware_raw_candidate.py`、`scripts/build_ml_revision_aware_raw_candidate.py`、`tests/test_ml_revision_aware_raw_candidate.py`。先用測試固定 API/manifest 契約後再確認是否必須改現有 Direct/OOC CLI；不要先改 `run_ml_raw_pit_refresh.cmd`、scheduled Direct/OOC pointer resolver 或既有 V3 profile。這是範圍建議，不是已核准實作，也沒有預設 source-owner acceptance 物件。

## 執行與 release 驗收次序

1. 只讀校驗來源 owner 提交的 source-contract facts與正式 revision chain。現有截至 2026-09-23 revision參考為 `20260923_run01`，DB 範圍 `2014-01-02..2026-09-23`；revision.json SHA-256 `801375e37a6f3c387d80178c775bfa73a1bf21ec914e73f7a014233078c700d2`，鏈摘要 `7dc35af66b3ca033f47d172ff52cdea9d21b95a1a94c2ed57fb649624a508bc4`。每次真實執行均需重新 readback，這些歷史 hash 不可假設永遠 current。
2. 產生 research-only raw candidate 到全新 repo ignored root；記錄輸入 pins、snapshot revision、source custody、availability、market calendar、code hashes、實際讀寫 bytes、candidate raw manifest hash。source modification、row/key/period/coverage mismatch、cutoff/lookahead violation 都應拒絕 candidate complete。
3. 在 candidate root 對該 hash-pinned manifest 做 Direct/OOC preview／build，驗其來源 identity/readback與 flags；不能讀寫 `release_v4/latest_manifest.json`、Formal source pointer、正式 SQLite 或 D。實際 heavy candidate QA 前，依既有 capacity policy先確保資源可用且與其他 chain 不競爭；不以 preflight 本身宣稱 build pass。
4. 之後才做 release 重新驗證：從 exact candidate/source/revision pins重讀、再驗 source quality、cutoff、Direct/OOC hashes、manifest/partition readback、pointer 更新的預覽 diff、容量與共享 lock。若改版任何來源、時間、schema或build code，舊 QA 必須失效重跑。
5. D 正式重建是另一個明確高影響操作，需 owner/source acceptance 已有來源證據、候選 diff 與 backup/rollback/readback 計畫可審、至少保留 200 GiB、scheduled persistent 上限 35 GiB、temporary peak 40 GiB，持有 `.ml_heavy_chain.lock` 並確定 Direct/OOC 沒有競爭 owner。全部材料 review 完成後，正式 D write 仍需另外明確確認；本輪不可執行。

真正自然成熟仍按 5／10／20／60 horizons 和每 horizon 20 個已成熟觀測計算。這些成熟條件不能取代 general revision-aware builder；builder readiness 也不能取代 maturity、source acceptance 或正式寫入確認。

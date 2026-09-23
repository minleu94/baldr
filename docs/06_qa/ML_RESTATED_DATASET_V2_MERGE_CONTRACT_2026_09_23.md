# Restated Research Dataset v2 合併契約（2026-09-23）

## 用途與限制

v2 是研究用途的價格修訂資料集。它以不可變的完整 v1 rowset 為父版，對 22 檔股票的完整歷史與最新 append rows 重新計算 62 個特徵及 H5/H10/H20/H60 標籤，再以 `row_id` 合併回完整父版。這份資料不代表歷史 PIT 可得性，也不屬於正式 OOS 或產品放行資料。

輸出固定放在 `E:\codex_model_repair_20260923\dataset\full_restated_v2`。v1、22 檔 corrected subset 與 v2 是不同版本目錄；合併器拒絕覆寫已存在的 v2 目錄，並在 staging 目錄內完成分區及 manifest 後才改名發布。

## Row 與數值保證

- 22 檔修正名單由 `data_module.ml_restatement_research_dataset_v2_merge.CORRECTED_SYMBOLS` 固定；合併器拒絕不同的 subset 名單。
- 只用 `row_id` 對應。父版每列及原順序保留；未命中的父版資料由原 Arrow batch 寫出。所有 subset rows 必須恰好命中父版一列，否則本版不發布。本次 full v2 的新增 row count 為 0，總 row count 與完整 v1 相同。
- subset 的 37,115 列包含 35,582 個 Direct baseline rows 和相對原 Direct baseline 的 1,533 個 append rows；這 1,533 列已存在於 full v1，不是 v2 新增列。
- 六個 `target_fields` 和 `target_missing_mask` 逐列保留父版原值。原 Direct target audit 有 3,353,096 個 baseline rows；六欄 target 均有 3,353,096 個 observed 值。Append rows 的 targets 維持 missing，不以標籤結果填充。
- 未修正股票的 row fields 保持父版值；修正股票的 row fields 取自同一 `row_id` 的 corrected subset，包括 feature、quality、label、fold、row-level event 和 observation clocks。
- `features_scaled_i64` 固定 62 槽 int64、沿用既有欄位順序與 scale。`feature_missing_mask` 每槽獨立，0 表示 observed、1 表示 missing。四個 horizon 各自保留 labels、mask、`label_end_date_hN` 及 `maturity_at_hN`。
- `decision_at` 是決策日 08:30 Asia/Taipei。決策日收盤不作為當日特徵；股票與市場特徵沿用嚴格 T-1 事件截止。修訂觀測時鐘按列保留：未修正列沿用父版實際時鐘，22 檔列沿用 subset 實際時鐘。它們記錄研究資料實際驗證時間，不宣稱 historical PIT availability。
- TAIEX observed dates 是 research calendar；如無完整官方日曆證據，不標示為完整交易日曆。公司行動側檔為 prospective-only，落在標籤窗內的 horizon labels 保持 masked。

## Manifest identity 與來源

schema 固定為 `portfolio-ml-restated-research-dataset.v2`，`dataset_id` 前綴為 `ml-restated-research-v2-`。`dataset_identity_fields` 必須等於程式常數 `V2_IDENTITY_FIELDS`，reader 不得信任 manifest 自供的其他 field list。Identity payload 為：

```python
{"identity_fields": list(V2_IDENTITY_FIELDS), **{k: manifest[k] for k in V2_IDENTITY_FIELDS}}
```

以 UTF-8、JSON `ensure_ascii=False, sort_keys=True, separators=(",", ":")` 計算 SHA256。`dataset_id`、`dataset_identity_hash`、`manifest_hash` 和 `dataset_identity_fields` 本身不進入 payload。合併器匯出 `build_v2_identity_payload` 與 `compute_v2_identity_hash` 供 reader 使用。

v2 `source_manifest_hashes` 保留原七個來源 alias，並依固定順序追加父版 manifest、corrected subset manifest、grouped numeric parser、v2 row merge、causal kernel implementation 五個來源。`computation_source_hashes` 精確列出 `causal_kernel_facade`、`causal_kernel_impl`、`grouped_numeric_parser`、`corrected_subset_builder`、`v2_row_merge` 的 raw bytes SHA256。外部 source-custody sidecar 不納入 dataset manifest，以免形成循環 hash。

`dataset_lineage.parent_v1` 與 `dataset_lineage.corrected_subset` 都記錄 manifest path、file SHA、identity hash、row count 和各自的 `revision_observed_at`。`patch.verification_summary.new_appended_rows` 僅表示 subset-only row IDs；本次應為 0。`corrected_subset_appended_row_count` 表示 subset 相對 Direct baseline 的 append 數，預期為 1,533。

## 執行與驗證

先確認 parent v1 和 corrected subset manifest 狀態是 `complete_research_build`，並用 manifest inventory 核對每個 Parquet 的 SHA、byte count 和 row count。直接執行 CLI：

```powershell
python scripts\merge_ml_restatement_research_dataset_v2.py `
  --parent-manifest E:\codex_model_repair_20260923\dataset\full_restated_v1\manifest.json `
  --subset-manifest E:\codex_model_repair_20260923\dataset\corrected_22_symbol_subset_v1\manifest.json `
  --output-dir E:\codex_model_repair_20260923\dataset\full_restated_v2 `
  --expected-parent-manifest-sha <sealed-parent-file-sha256> `
  --expected-subset-manifest-sha <sealed-subset-file-sha256> `
  --original-target-audit C:\Projects\PythonProjects\technical_analysis\output\qa\model_repair_integration_20260923\output\qa\model_repair_review\original_target_values_audit.json
```

QA 應同時確認：subset 37,115 個 IDs 各自恰好命中一次；full v2 所有 IDs、順序及 row count 與父版一致；每個父版 target 與 mask 未變；22 檔各列全部欄位與 subset 對應列一致；其他股票所有欄位與父版一致；manifest partition inventory、12 個 aliases、`dataset_identity_hash` 與外部 source-custody sidecar 均可獨立重算。

單元測試：

```powershell
python -m pytest tests\test_ml_restatement_research_dataset_v2_merge.py -q -o addopts=
```


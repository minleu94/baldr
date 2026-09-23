# Derived-h5 run02 研究訓練輸入缺件盤點（2026-09-23）

## 結論與範圍

**結論：NO-GO，不能直接以目前封存資料啟動修訂後的 derived-h5 全量研究重建或 fit。** 本盤點只確認已封存來源、舊 Direct/OOC 與 derived-h5 manifest，以及當前公司行動候選 sidecar 的檔案身分和已記錄 coverage。沒有載入或反序列化模型、沒有 fit、沒有重建資料，也沒有寫入 D 正式資料或模型。這不是永遠不能重訓的結論；它表示目前證據不足以聲稱「完整 corrected-source inputs 已就緒」。

本輪沒有重算整個 11 GB archive，也沒有掃描 3.6 GB SQLite、235 MB cell diff 或完整舊數值 store。大型檔案的 size/SHA 沿用已封存 transfer receipt；run02 的全窗口技術指標 readback 沿用已保存且先前通過的 tracked verifier 結果。本輪另行讀取小型 JSON manifest 並核對其路徑、宣告 hash、coverage 與 identity。下文把「檔案存在」、「manifest 綁定到 run02 identity」和「資料內容已 readback」分開說明；未做內容讀回處均明列未驗證。

## 權威 run02 來源 custody

封存根目錄為 `D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna`。其 transfer receipt：

`D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\transfer_receipt.json`

本輪讀回 receipt 檔案 SHA-256 為 `c0e0cb823d172c052db201351d7db0dc3d170f6b436003d37d4815ce28015fe4`；receipt 記錄 26 個檔案、總計 11,326,481,197 bytes，並限制 `research_only=true`、`non_release=true`、`formal_training_allowed=false`、`historical_pit_allowed=false`、`promotion_eligible=false`、`production_alpha_bp=0`。這是檔案清單與轉移時的 size/hash 證據；本輪沒有對 26 個大檔逐一重算 SHA。

權威 v2 run identity 是 `7e2f19cc5a00f20ba5b3890a`，資料集 ID 為 `research_shadow_daily_price_revision_recovered_source_20260922`。manifest 完整路徑：

`D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\revision_20260922_run02\research_source_dataset\runs\7e2f19cc5a00f20ba5b3890a\manifest.json`

manifest file SHA-256 為 `f9a19b704fab86d0701091073d74353dec51dd1a8d3902fc46a6fb24ec1ba772`。它綁定 run02 SQLite snapshot：

`D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\revision_20260922_run02\inputs\twstock_snapshot_run02.db`

snapshot 為 3,602,477,056 bytes、SHA-256 `38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771`；此 hash 沿用 transfer receipt 與既有 snapshot/verifier 證據，本輪未重讀或重算整個 DB。manifest 綁定的來源列檔完整路徑為 `D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\revision_20260922_run02\research_source_dataset\runs\7e2f19cc5a00f20ba5b3890a\recovered_source_rows.jsonl`，868 rows、2,001,269 bytes、SHA-256 `506f464d92ead313c4fc0d15eaa4eb490b553e86e084701f7d4e93c34e796fb4`；hash/size 沿用 receipt，本輪未重讀完整 rows payload。

此來源 artifact 僅涵蓋 2026-05-20 修訂：868 個 daily-price/technical source rows，其中 865 列 OHLC 完整，1538、2321、5906 共 3 列明列 `missing_ohlc_source`。修訂於 2026-09-22 才觀測，狀態為 `late_obtained`，歷史 `available_at` 為 null，`historical_decision_time_available=false`，原 pending marker 保留並繼續阻擋 formal PIT。manifest 的 `feature_contract_status=not_assessed`、`label_maturity_status=not_materialized`、`labels_materialized=false`、`labels_available_for_fit=false`、`model_training_input_compatible=false`；formal、PIT、promotion 皆 false。

技術修復證據只驗證既有 repair window，不等於模型 feature coverage：修復計畫涵蓋 868 個個股快取、75,442 rows；tracked verifier 先前讀回 1,277,135 個修復後 cells 及 2,117,755 個 untouched cells，均零 mismatch。verifier file 路徑為 `D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\revision_20260922_run02\evidence\technical_snapshot_verification.json`，SHA-256 `1abadf64fdb932fb88d97359c04fa4b61d087b90f3e0083e3e0a226add9fedd9`；其 evidence SHA-256 為 `1e3fc58f984e89126ed6d8e3bce477b06f021bf6a08397ba369648d67dcbc35c`。這裡沿用先前 verifier readback，不把本輪的 manifest inspection 描述為重新驗證完整 SQLite。

## 需求矩陣

| 必需輸入 | 已存在的 artifact 與 identity | 已驗 coverage / content readback | 判定 |
|---|---|---|---|
| 完整 62-feature 值、固定順序、逐欄 scale/normalization | run02 archive 內只有 868-row `recovered_source_rows.jsonl`，包含價格與技術來源，不是 62-feature model matrix；transfer receipt 的 26 檔清單沒有新的 Direct shards、feature matrix 或 62-feature lineage manifest。舊模型採用的 order hash 是 `sha256:a2a3a26f457f9901f90b1f08d3e844defe7abe279a22d722d197f56d3eb19611`，registry hash 是 `sha256:8b0f831a94ecd503591a146d36412b2385397928b98fbd607a33fa6073630f27`。 | 只核對 run02 source rows 數量與 manifest；沒有對 run02 全窗口產生或讀回 62 個 feature values、per-column scale、dtype/mask 或 normalization。 | **缺 run02 綁定的完整 feature inputs / lineage。** 舊 schema hash 只識別舊 contract，不能證明新資料內容相容。 |
| 10 個 quality features | 舊 Direct manifest 的 `data_quality` pack 列有 10 個 feature IDs；其 `derived:feature_quality` source hash 為 `sha256:4ec39f893d42293743db20d9fa340d07d1951bf2e33d4c9980a3f9f761605d09`。 | 舊 store 宣告 3,353,096 rows，quality coverage 為 33,530,960 / 33,530,960（10000 bp）。沒有 run02 identity 的 quality sidecar 或對應 content readback。 | **舊資料有完整宣告 coverage；修訂後資料缺新 identity 的 quality values/lineage。** 不可移植舊 100% coverage。 |
| 全窗口 feature dependency/availability lineage | run02 綁定來源只列 2026-05-20 的 868 個價格與技術來源 rows、repair receipts、recovery receipt、tracked verifier；transfer receipt 沒有 model feature lineage manifest。舊 Direct 的 7 個 source hashes 均是另一個 dataset identity。 | 已有 readback 限於 repair window 的 1,277,135 after cells、2,117,755 untouched cells 與 868 個 source-date rows；本輪未驗證完整歷史每 row/每 feature 的 source dependency、scale、available clock 或 rolling window。 | **缺 full-window corrected feature lineage。** repair-cell verification 不可外推成 62-feature OOC store 驗收。 |
| H=5 label values 與 authoritative `available_at` | run02 manifest 的 `labels_materialized=false`、`label_maturity_status=not_materialized`、`labels_available_for_fit=false`；transfer inventory 沒有新 label rows/lineage manifest。 | 本輪沒有讀回任何 run02-bound label values 或 per-row authoritative availability receipt。行事曆上的 horizon end 不能替代來源 `available_at`。舊 Direct/OOC manifest 列有 h5 label family，舊 derived-h5 manifest 綁定其 parent store；舊 row values 本輪未 readback，且其 source identity 不是 run02。 | **缺新 label values、成熟證據與 authoritative availability。** |
| 公司行動 label exclusion | D 有一份 current prospective-only sidecar。latest pointer `D:\Min\Python\Project\FA_Data\output\release_v4\corporate_action_adjustments\latest_manifest.json` file SHA-256 `e2f26bca285ab85287c7ac5109b35f28d72b1d3507d21bf3d5d05943a5e53d5a`，指向 `D:\Min\Python\Project\FA_Data\output\release_v4\corporate_action_adjustments\runs\corporate-action-adjustments-1f167a302bb6acd17349502f\manifest.json`；該 manifest file SHA-256 `8fda26cdcf5cc399bef5cd3a13e35343f0c68321f13b416f6baaef71497676e9`、canonical manifest hash `8287a04e96ef8d33612491811e190d73ea58121d274b620a1343bd8df2c9d133`。 | sidecar manifest 宣告 12,869 adjustment rows；完整 adjustments 路徑為 `D:\Min\Python\Project\FA_Data\output\release_v4\corporate_action_adjustments\runs\corporate-action-adjustments-1f167a302bb6acd17349502f\adjustments.jsonl`、20,482,432 bytes、manifest-declared hash `sha256:5bdf25449d88333d005b4b604b8daf1547e67945c890037ad0caf4ac2f511d21`；coverage file `D:\Min\Python\Project\FA_Data\output\release_v4\corporate_action_adjustments\runs\corporate-action-adjustments-1f167a302bb6acd17349502f\coverage.json`、916 bytes、manifest-declared hash `sha256:a2544464b39cef2d7c94301c8d315ce008c7d9e23f4afa43750f510e09d08265`，宣告 28,714 canonical events。這兩個資料檔本輪只核路徑/size 與 manifest 宣告 hash，沒有重新計算全檔 SHA 或逐列驗 exclusion。`prospective_only=true`、formal/PIT false。Transfer inventory 不含此 sidecar，也沒有 run02-bound exclusion result/readback。 | **檔案存在，但未綁定 run02 及新 labels。** 可作後續新 candidate 的輸入候選，不能直接宣稱排除已完成。 |
| 新 fold manifest | run02 transfer inventory 沒有 fold manifest 或新的 train/test refs。 | 舊 Direct 有 41 folds，purge=60、embargo=5；test coverage 從 2015-01-13 到 2026-07-14。derived-h5 舊 manifest 將 fold-001–003 用於 meta/calibration，fold-004 作 withheld heldout（2015-11-16 至 2016-02-22，57,666 rows）。這些 refs 全部綁舊 Direct store。 | **缺新 dataset identity 下的 folds/ref/readback。** 舊 heldout/OOS 結果不能作 corrected-source OOS。 |

## 舊 release 與目前 sidecar 的身分界線

舊 Direct/OOC manifest 位於：

`D:\Min\Python\Project\FA_Data\output\release_v4\portfolio_ml_direct_numeric_production_v4_v2\runs\direct-ooc-505c6adaf3f71a0c8f0a274e\manifest.json`

本輪讀回該小型 manifest 的 file SHA-256 為 `61d806ef005d0881911201104079c1acc92826a26bd8a331b9d79156983ffe8`。它標示 dataset ID `all_field_enriched-direct-allocation-3fba3292db22`、identity hash `3fba3292db228577f91fb652d74d4bcfbed124e98e4fb8e48de92eb9554209f8`、3,353,096 rows、62 features、41 folds、training cutoff `2026-09-03T17:30:00-07:00`。它的 source hashes 包含舊 `derived:daily_prices.ohlc=sha256:00550762f031b1389bb74708b7047a0a9a71c0582c3026b91fa3bf76b2cac634`、舊 `derived:feature_quality=sha256:4ec39f893d42293743db20d9fa340d07d1951bf2e33d4c9980a3f9f761605d09`、舊 `sidecar:official_corporate_action_ledger=sha256:97f4b17377fa91d977016134551a4f96d8f0e67d7824e1cc6392acdf225c168e`、舊 `sqlite.daily_prices=sha256:61a6364748172fc07518e2ebc6e29daf9ec1b73fd4ade3e924b5fdcf3d57821d`、舊 `sqlite.technical_indicators=sha256:3f6f910d22a265b44a36a1c6efe18be80dc5f68183cf5ec2b9c7813e02598125`、`sqlite.industry_indices=sha256:2ad1e34a0e2731d54152fc1d145ad8804cecbe5fb2f78dc0d0841a2e90cc4f3e`、`sqlite.market_indices=sha256:93234c84a466619a9f9209b6d2a127a7c7875c99a5d93e518d39b371497d1dc1`。這些與 run02 corrected snapshot identity 不同，因此該 store 雖實際存在，不能直接充當修訂後 inputs。此輪只讀 manifest metadata，沒有讀回全 store shards 或逐列 labels。

每日 shadow derived-h5 release 位於 repo ignored output：

`C:\Projects\PythonProjects\technical_analysis\output\v4_ml_derived_h5_20260907_real_v2\release_manifest.json`

release manifest SHA-256 為 `c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea`，artifact SHA-256 為 `aa152ebb8e8d7913a6a2274a0526620d8b8ce151a5f667d8de446df9724c895c`。其 `derived_training_manifest.json` 完整路徑為 `C:\Projects\PythonProjects\technical_analysis\output\v4_ml_derived_h5_20260907_real_v2\derived_training_manifest.json`，SHA-256 為 `4a51fc41e67c6eac44e503bb683bcefa1def5336022590b912951ab863a32da0`；preprocessor 位於 `C:\Projects\PythonProjects\technical_analysis\output\v4_ml_derived_h5_20260907_real_v2\preprocessor.json`，檔案 SHA-256 `987fdbea4ffdd97004aa5cd824f73d106370d0617bb1dfafcebe897322c95419`，指定舊 order hash `sha256:a2a3a26f457f9901f90b1f08d3e844defe7abe279a22d722d197f56d3eb19611` 與 `train_fold_exact_median_indicator_standard_scale`。它沿用上段舊 Direct parent identity，不是 run02 新產物。本輪沒有載入或反序列化 h5 模型。

D current corporate-action sidecar 雖已存在，其 `manifest_hash=sha256:8287a04e96ef8d33612491811e190d73ea58121d274b620a1343bd8df2c9d133` 及 adjustment file hash `sha256:5bdf25449d88333d005b4b604b8daf1547e67945c890037ad0caf4ac2f511d21` 均不同於 Direct manifest 綁定的舊 `manifest_hash=sha256:97f4b17377fa91d977016134551a4f96d8f0e67d7824e1cc6392acdf225c168e`／manifest file hash `sha256:6052829c4f477c2a902513356d01aa25ac98d324a828144036d9137b492b49b0`。最新 sidecar 可供後續受控研究 builder 考慮，但必須明確與 run02、feature lineage、label rows 一起建立新 identity 並完成 row-level exclusion readback；不能只因檔案存在便視為舊模型或 run02 已消費。

## 安全下一步與限制

最小必要工作包是另立一個 model-family-specific research dataset builder/QA：唯讀綁定 run02 snapshot、修訂 receipts、完整 62-feature frozen registry/order/scale/mask/normalization；重建被影響依賴窗口並產出全窗口 per-feature source lineage；為 H=5 重新產生 label values，逐列連到 authoritative label availability；把公司行動 exclusion sidecar 綁入新 dataset identity；建立新 purge/embargo fold manifest，完成 row/shard readback。只有全部 evidence complete 後，才另行審查研究 candidate fit 的授權與資源。這不應暗塞到 R027/R028，也不應改動 frozen 15 source paths 或正式 PIT gate。

在該工作包完成前，derived-h5 訓練 readiness 維持 pending；不 fit、不 promotion、不改正式 DB/model、不將 5/20 修訂值回稱歷史 PIT，也不把舊 Direct folds、labels、quality coverage 或公司行動排除結果重用為修訂後證據。R027/R028 的既有職責不因本盤點擴張。

## 讀取與驗證範圍

本記錄使用 D transfer receipt 中的 26-file inventory/hash 與既有 tracked technical verifier；未對所有封存內容重算 hash。另行核對的檔案內容只包括 transfer receipt、run02 source manifest、D current corporate-action latest/run manifests、舊 Direct manifest 及 C derived-h5 release/training/preprocessor manifests。未讀入完整 SQLite 或全量 feature/label/store shards；因此未宣稱這些未讀 payload 已在本輪獨立完成 hash/readback。

本輪為 docs-only QA 紀錄，沒有新增程式或測試；不代表資料 builder 已完成或允許模型 fit。

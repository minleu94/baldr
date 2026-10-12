# R026 capability candidate JSON captured-bytes 品質驗證

**狀態：** Root 判定此 experimental invocation capability 候選 JSON captured-bytes 切片為 bounded `ACCEPTED_SCOPE`。接受範圍僅限 capability 路徑的 active/ancestor candidate JSON 同次捕獲與解析；不接 live service/runtime handoff。R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`。

## 範圍與行為

Capability 路徑在解析 active `candidate.json` 前捕獲原始 bytes，並由同一 buffer 解碼及解析；每個 ancestor candidate 也各自以一次 `read_bytes()` 捕獲，再以該 buffer 解析。現有 candidate path recheck 保留，但此路徑要求 recheck 讀到的 bytes 與該節點解析時捕獲的 bytes 完全相同。Active 或任一 ancestor 不符時，整個 capability 失敗，不發布部分 lineage evidence。一般 `reload()`、舊 loader、service、receipt 與 projection 行為未改。

`_CapabilityCandidateJsonBytesLineageV1` 為 capability 暴露有序、frozen 的節點 evidence。每個模型節點分別記錄：

- `raw_bytes_sha256`：實際解析的 candidate JSON 原始序列化 bytes 摘要。
- `canonical_payload_sha256`：使用 `recommendation-candidate-json.v1`（UTF-8、`ensure_ascii=False`、key 排序、緊湊分隔符）計算的解析後 JSON payload 摘要。
- candidate/model ID、相對 pointer 根目錄正規化的 candidate root，以及 manifest/artifact/freeze/dataset identity claims。

Null benchmark 節點不對應 candidate 檔，兩個 JSON digest 欄位皆為 `None`。Raw hash 與 canonical payload hash 是不同證據；後者不代表原始 bytes 相同。

## 測試與驗證

先行 red 路由在未實作行為時為 **5 failed／29 deselected**：missing evidence property、active JSON 替換、相同 payload 不同序列化、transient replace/restore evidence 與 ancestor JSON 替換案例未符合預期。這是 test-first 基線，不作為現行通過證據。

Focused 新增行為測試：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py -k 'captures_ordered_same_bytes_lineage or active_candidate_json or ancestor_candidate_json' -q -o addopts= -p no:cacheprovider
```

fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026cj_37e908ff` 結果 **5 passed／29 deselected**，log SHA-256 `9E67D7AEC95BF9D60B5DAC7CF7A444709A12C10B27F38639061FC2E2D38E7121`。Test-first red run 為 **5 failed／29 deselected**；該短輸出未另存 log。

最終 source/test bytes 的五檔 adjacent 路由命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_r026_model_resolution_facts.py tests/test_r026_model_artifact_same_bytes_loader.py tests/test_ml_model_artifact_loader.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider
```

使用 `PROFILE=test`，並將 `TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT`、pytest `--basetemp` 隔離到各自 fresh TEMP。首次五檔路由為 **67 passed／1 failed**；唯一失敗是 `test_live_calibration_brackets_one_provider_snapshot_with_matching_source_evidence`，斷言兩次 sequential scope ID 不同時觀察到相同值。此失敗 run 使用最終行為實作、但早於最後一個 `_is_prefixed_sha256` 參數型別註記修正；該註記僅收窄 mypy 對 runtime type guard 的誤判，並未改 runtime 判斷。測試單獨 fresh TEMP 重跑通過；之後最終 source/test SHA 下同路由先後兩次均為 **68 passed**，最後一筆 log 為 `C:\Users\archi\AppData\Local\Temp\r026cjf2_1216dfdd\pytest.log`，SHA-256 `AA189E70E3C1060239041513590D3CC2C218297766EB1F77066E8EE21E204CB0`。首次失敗的 log 為 `C:\Users\archi\AppData\Local\Temp\r026cjf_3d27e588\pytest.log`，SHA-256 `8A302E262787AB9771466A95D95E86C74446CC4D626EA12228ED42300363E60B`；scope test 單測重跑 log 為 `C:\Users\archi\AppData\Local\Temp\r026live_59ce92eb\pytest.log`，SHA-256 `353949A8236178D20EF1829924BAA88A4DBCA28C29768E1D1D47C6E1199D3468`。R015 獨立確認首次失敗來自舊斷言索引：每次 invocation 有三次 sidecar collect，共六筆 aggregate call；舊測試誤以 `aggregate_calls[2]` 代表第二次 invocation，該索引實際仍屬第一組。當前 frozen test 改用 `[3]`，並在最終 source/test SHA 下兩次取得 68 passed。首次 **67 passed／1 failed** 仍是失敗收據，不計為通過；修正索引與成功重跑不抹除該失敗紀錄。

測試 runtime：Windows 10 build 26200、Python 3.11.9、NumPy 2.3.5、SciPy 1.16.3、scikit-learn 1.8.0、joblib 1.5.2。

最終 source/test SHA-256：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation_calibration_consumer.py` | `49B9889376DBFBC004DDDE0D15F18BCEDE9F4C6FFB83D261452594189499ED48` |
| `tests/test_r026_invocation_model_capability.py` | `41824B9C3CF8C524C47FB8FE19D87ECA211341D53FA3D42ACE1B09489A6B0589` |

Scoped mypy：`python -B -m mypy app_module/recommendation_calibration_consumer.py --follow-imports=silent`，0 issues。`py_compile` 對 source 與測試通過；`scripts/quant_guard_linter.py` 通過精度與 look-ahead 檢查；`git diff --check` 通過（Git 僅提示既有 LF/CRLF 轉換）。

## Look-ahead 與限制

此切片僅捕獲並比對 candidate identity JSON；不讀取新價格/特徵、不改 scoring、訓練 cutoff 或 decision date，也不做標準化，沒有引入 look-ahead 路徑。

Exact bytes recheck 是前後 path observation，不是跨檔 lease。candidate JSON、manifest、artifact、pointer、lineage 與 receipt 未共同綁定在一個原子快照；檢查後變更與 A→B→A race 仍未解。Raw/canonical JSON digest 不證明 manifest/artifact 是由相同交易讀取，也不構成完整 `ModelBinding`、`PreparedMLRuntimeInputV1` 或 runtime handoff。此 bounded slice 不關閉 R026 或 `TMP-ML-01`。

## 獨立複核與 bounded acceptance

R015 以 fresh short TEMP 對 frozen source/test 執行 68 passed，review log SHA-256 `3C0DC627DFB6EA9858931E7A961CCF25C6D1D59488FBA75A183F4E4592C6C347`；scoped mypy 2/0，未發現 P1/P2。Root 據此接受本文件開頭所述的有限範圍。Owner 最終 frozen source/test SHA 與 68P 路由收據見上文；該路由的最後 log SHA-256 為 `AA189E70E3C1060239041513590D3CC2C218297766EB1F77066E8EE21E204CB0`。

早期 **67 passed／1 failed** 收據仍保留為 FAIL、不計通過。R015 確認該次失敗是舊斷言索引錯誤：每次 invocation 有三次 aggregate collect、總計六筆；舊測試以 `aggregate_calls[2]` 當第二次 invocation，實際仍是第一組第三筆。Frozen 測試改用 `[3]` 後，同一受控路由取得 68 passed；這不抹除早期失敗紀錄。

此 acceptance 不涵蓋跨檔原子性或 ABA 防護、candidate JSON 以外的共同來源綁定、receipt 發布競態，亦不授權 live runtime handoff。R026 與 `TMP-ML-01` 仍開啟。

## 後續 supported handoff 狀態（2026-10-10）

上列 `TMP-ML-01` 狀態是本 experimental candidate-JSON slice 的 2026-09-25 checkpoint。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md) 與 [R031 final closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，正常 `RecommendationService` 的 NP1／NP2 supported caller/profile 遷移條件後續已 `CLOSED`。此狀態更新不表示本 candidate-JSON capability 已接入該 runtime handoff；R026 其他 source-evidence slices 仍未全部完成。

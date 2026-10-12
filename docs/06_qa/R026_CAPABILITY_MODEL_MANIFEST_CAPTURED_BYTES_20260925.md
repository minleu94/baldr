# R026 capability model-manifest 同 bytes 捕獲實作驗證

**狀態：** owner 已完成限定實作並凍結程式／測試 bytes，`READY_FOR_INDEPENDENT_REVIEW`。這不是 bounded acceptance，也不代表 R026 或 `TMP-ML-01` 完成；R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

## 範圍與實作

新增 opt-in `SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1()`，結果版本為 `shadow-model-artifact-manifest-same-bytes.v1`。此 wrapper 在載入階段對每份 `manifest.json` 執行一次 `read_bytes()`，raw SHA-256、UTF-8 decode、JSON parse 與 `ModelArtifactManifest.from_dict()` self-hash 驗證都使用同一 buffer。 `canonical_manifest_payload_sha256` 是從該 buffer 重建且通過 self-hash 驗證的 `manifest_hash`；它和整份原始 JSON bytes 的 SHA 是兩項不同證據。Artifact 仍經既有 same-bytes spool/hash/deserializer 路徑。

普通 `load()`、`load_same_bytes_v1()` 簽章及返回 ABI 保持可用；舊 same-bytes 方法只將 manifest parse 後的既有 artifact 檢查抽成內部 helper。測試保留舊 Path deserializer 與一般 consumer reload/projection 行為。新 API 不改 model manifest schema、artifact hash、candidate、receipt 或 training lineage。

experimental `resolve_invocation_projection_capability()` 只在 fresh consumer 使用新 API，涵蓋 active manifest 與 probability lineage 中依序載入的所有 ancestor manifests。能力新增唯讀 `model_manifest_bytes_lineage`，節點以相同順序保存 candidate/model identity、normalized root、捕獲 raw SHA 與已驗證的 canonical manifest hash。Null benchmark 節點不宣稱有檔案證據。原始 bytes 僅在建立 capability 的 fresh consumer 中暫存；能力返回前逐一重讀所有捕獲 manifest paths，任一 bytes 不同或讀取失敗就不發布 capability，並清除暫存 bytes。

這個 path recheck 是兩次 bytes 觀察，不是 lease；它不能排除 A→B→A、最後一次檢查後的變更或跨 pointer/candidate/manifest/artifact/SQLite 的原子快照。新 API 仍只服務 experimental capability；沒有接入 RecommendationService，也未寫入 decision receipt 或 training lineage。

## 紅綠與相容性案例

新增／調整案例涵蓋：

- loader 捕獲同一份 manifest bytes 一次，raw digest 與 self-hash identity 由該 buffer 取得；
- invalid UTF-8、invalid JSON 與合法 manifest 中錯誤的 self-hash 均 fail closed；
- active 與 ordered ancestor manifests 都出現在 capability 的 immutable evidence lineage；
- active 或 ancestor manifest 在捕獲後被替換成同一 JSON payload、不同原始 bytes 時，返回前 path recheck 拒絕 capability；
- 普通 loader、既有 `load_same_bytes_v1()` 與一般 reload/projection 仍維持既有測試行為。

開發期 red 路由在新 API 未實作時因缺少版本化 result symbol 而於 collection 失敗（33 deselected、1 error）。首輪實作後另有一次 5 passed／1 failed：錯誤 self-hash fixture 同時漏掉必要 shadow flags，先被既有旗標檢查拒絕；測試改為從完整有效 manifest 僅改 self-hash 後重跑。這些開發期失敗均保留，不計入最終通過數。

## 最終 fresh TEMP 驗證

環境使用 `PROFILE=test`；`TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 和 pytest basetemp 均隔離在 `C:\Users\archi\AppData\Local\Temp\r26mfrozen_20260925_07`。沒有讀寫正式資料根目錄。

焦點路由：

```powershell
$qaRoot = 'C:\Users\archi\AppData\Local\Temp\r26mfrozen_20260925_07'
$env:PROFILE = 'test'
$env:TEMP = Join-Path $qaRoot 'tmp'
$env:TMP = $env:TEMP
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'out'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_model_artifact_same_bytes_loader.py `
  tests/test_r026_invocation_model_capability.py `
  tests/test_ml_model_artifact_loader.py `
  tests/test_ml_model_artifact_manifest.py `
  -q -o addopts= -p no:cacheprovider `
  --basetemp (Join-Path $qaRoot 'pytest')
```

結果：**56 passed**，結束碼 0。pytest log SHA-256：`9652284164054B1D6BFDE55E0163FB4C90136A68D29DF805647DBFB2B1F1960F`。

其他檢查：

```powershell
.\.venv\Scripts\python.exe -m mypy ml_module/model_artifact_loader.py app_module/recommendation_calibration_consumer.py --follow-imports=silent
.\.venv\Scripts\python.exe -B -m py_compile ml_module/model_artifact_loader.py app_module/recommendation_calibration_consumer.py tests/test_r026_model_artifact_same_bytes_loader.py tests/test_r026_invocation_model_capability.py
git diff --check -- ml_module/model_artifact_loader.py app_module/recommendation_calibration_consumer.py tests/test_r026_model_artifact_same_bytes_loader.py tests/test_r026_invocation_model_capability.py
```

Mypy 檢查 2 個來源檔、0 項問題；`py_compile` 結束碼 0；`git diff --check` 結束碼 0（只有既有 Windows LF/CRLF 提示）。檢查 log SHA-256：`0937593E934AE15C4D4863C5879DBEDB9C3E48170F85097AA66EF7F5951A044B`。未執行全庫量化精度／未來資料檢查；本切片只新增 bytes/hash/identity 驗證，沒有新增金融數值或特徵計算。

## 凍結來源／測試 SHA-256

| 檔案 | SHA-256 |
|---|---|
| `ml_module/model_artifact_loader.py` | `95D30503215B022888ED2D94E061DE27B4648F1C60A6C56D90F9B68DDB412F08` |
| `app_module/recommendation_calibration_consumer.py` | `1559D1399A36C88883D1CF19AE4F7B96BE962E3F99866015FBFEBE45E9740EF5` |
| `tests/test_r026_model_artifact_same_bytes_loader.py` | `17DC26416471327F11675A620292F3619236BEC5F3DA0BC012E80A0186946CFB` |
| `tests/test_r026_invocation_model_capability.py` | `6AE9276D31A4ED8FD642830F6916A7BB4C2D9337AB559692E3C47AE632B65605` |

以上雜湊識別目前 working copy 的完整檔案，也包含這些共用檔案中先前已存在的 dirty slices；本實作報告不宣稱那些既有 hunk 是此切片新增。本次沒有 stage、commit 或 push。

## R026 最短剩餘依賴

下列是 `R026.md` 與 FINAL 條款仍要求的 runtime 閉合項，按先後列出。此表不擴張本 manifest slice 的實作範圍。

| 依賴 | 明確條款 | 可重用的現有實作 | 尚缺驗收 |
|---|---|---|---|
| 建立並接線版本化 transient runtime input | R026 `IMPLEMENTATION OBJECTIVE`／`ACCEPTANCE CRITERIA`；FINAL_DATA_FLOW §5；INV-14 | `PreparedMLInput.v1` 在 `ml_module/prepared_input_contract.py`；`RecommendationMLAdapter`／`PreparedMLProjector` Protocol 在 `app_module/recommendation/ml_adapter.py`；capability-only resolve 現可取得 invocation-local model/lineage | 尚無 `PreparedMLRuntimeInputV1`，也未接入 app preparation 與 projector 唯一參數。需將 ordered `tuple[int | None, ...]`、schema/hash 及本次 capability 凍結在 runtime input；projector 期間禁止 DB、HTTP、path、pointer、provider 與 loader I/O，並測 alias 隔離。 |
| 將已驗 source/model facts 綁到同次 runtime input | R026 `CURRENT BEHAVIOR TO PRESERVE`／`ML COMPATIBILITY REQUIREMENTS`；FINAL_DATA_FLOW §5；INV-05、INV-14、INV-15 | accepted 的 provider read snapshot transaction、ordered preparation facts、source identity shadow facts、pointer/candidate/artifact/manifest captured-bytes 能力 | 這些目前是分立 evidence，尚未共同進 runtime input。需保留來源 resolve 時點、cutoff、candidate order、cost context、feature bytes/order/dtype/missingness、quarantine/unavailable fallback；測 source-update 與 active-pointer barrier。不得由 sidecar 摘要推定 SQLite generation。 |
| 完成深層 alias、A/B interleave 與新舊 parity gates | R026 `TEST REQUIREMENTS`／`ACCEPTANCE CRITERIA`；Prepared runtime decision addendum 第 1–7 項；INV-08、INV-14、INV-15、INV-18 | 現有 same-bytes loader、capability isolation、legacy preparation baseline、calibration integration 與 receipt tests | 尚須在真正 runtime input/projector 接線上驗證外部／巢狀 mutation 與 A/B invocation 隔離；穩定 pointer 下逐項比對 feature/schema/hash、model identity、projection、annotation、receipt identity/bytes；注入 loader reject、quarantine、source/pointer race 與 receipt failure，驗 fallback 與副作用順序。 |
| 通過後才處理 `TMP-ML-01` 退休 | R026 `IMPLEMENTATION OBJECTIVE`／rollback 條款；FINAL_MIGRATION_SEQUENCE Block 4 與退休帳；INV-17 | 舊 calibration preparation branch 與歷史 decoder／必要 class aliases 仍保留；本 slice 未碰 legacy branch | 前述 runtime、alias、barrier、parity、receipt gates 全通過前保持單一路徑，不能刪舊 branch。永久歷史 decoder/qualified class 支援保留。 |

**資料來源可用性邊界：** 目前 `SnapshotReference.source_revision`、availability、quality、scope 有些仍是 `None`／`UNKNOWN`，詳見 R026 report 的 source identity slices。這些值須原樣表示 unknown，不能以新的 manifest digest 升格為 `KNOWN`。UNKNOWN 應按現行政策拒絕或降級推論；它不要求本輪做全市場資料回填／重建，也不應無限擴張 producer scope。來源完整性／PIT 驗收與 R026 runtime contract 是不同 Gate。

全域狀態維持：C1 工程 Gate `PASS`；R020、R026 `IN_PROGRESS`；C2 未完成；R027 `INCONCLUSIVE`、`AB-ML-01` `OPEN`，R028 `BLOCKED`。

## 後續獨立複核與 supported handoff 狀態（2026-10-10）

本文開頭的 `READY_FOR_INDEPENDENT_REVIEW` 已由 [manifest independent review](R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_INDEPENDENT_REVIEW_20260925.md) 後續收據取代：該切片無 P0／P1／P2，並獲 bounded acceptance。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)，依賴表中「尚無 `PreparedMLRuntimeInputV1`」也是 2026-09-25 的歷史描述；NP1／NP2 supported normal-service route 後續已使用 typed prepared-runtime／post-calibration handoff，`TMP-ML-01` 該遷移條件為 `CLOSED`。這不表示本 experimental manifest-capture slice 本身已接入 service，也不關閉其他 R026 source-evidence slices、profiles 或 production release。

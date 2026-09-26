# R026 capability model-manifest 同 bytes 捕獲獨立覆核（2026-09-25）

## 範圍與凍結確認

覆核對象為 `R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_20260925.md` 所列 frozen manifest slice。
以下四個 working-copy SHA-256 與 owner／root 提供值完全一致；本覆核未修改來源或測試檔：

| 檔案 | SHA-256 | 結果 |
|---|---|---|
| `ml_module/model_artifact_loader.py` | `95D30503215B022888ED2D94E061DE27B4648F1C60A6C56D90F9B68DDB412F08` | 相符 |
| `app_module/recommendation_calibration_consumer.py` | `1559D1399A36C88883D1CF19AE4F7B96BE962E3F99866015FBFEBE45E9740EF5` | 相符 |
| `tests/test_r026_model_artifact_same_bytes_loader.py` | `17DC26416471327F11675A620292F3619236BEC5F3DA0BC012E80A0186946CFB` | 相符 |
| `tests/test_r026_invocation_model_capability.py` | `6AE9276D31A4ED8FD642830F6916A7BB4C2D9337AB559692E3C47AE632B65605` | 相符 |

## 覆核結果

**結論：接受此 manifest slice 進入 C2 freeze；本覆核沒有發現 P0、P1 或 P2。** 此結論只適用
於本次凍結的 manifest bytes capture slice，不代表 R026 或 `TMP-ML-01` 完成，也不擴張至四個
檔案中先前已有的其他 dirty slices。

- `load_same_bytes_with_manifest_v1()` 對 manifest path 執行一次 `read_bytes()`；raw SHA-256、
  UTF-8 decode、JSON parse 與 `ModelArtifactManifest.from_dict()` 都以該 bytes buffer 為輸入。
  已解析且 self-hash 驗證的 manifest 才傳入既有 artifact same-bytes 載入流程。版本化結果會
  驗證 raw digest 等於捕獲 bytes 的 digest、canonical digest 等於 manifest self-hash，並要求
  ready 結果同時具有兩項 digest 與捕獲 bytes。
- capability 使用 fresh consumer。active manifest 與每個 ordered ancestor manifest 都經此
  opt-in same-bytes loader；證據節點依 probability lineage 順序建立，並逐項比對 candidate id、
  canonical manifest hash 與 lineage。null benchmark 節點的 manifest 欄位皆為 `None`，不宣稱
  有檔案證據。
- capability 發布前，consumer 對捕獲過的每個 manifest path 重讀並逐 byte 比較；缺檔、讀取錯誤、
  bytes 不同或 manifest node 數量不一致時不註冊 capability。返回／失敗路徑的 `finally` 會清空
  暫存的 raw-byte capture state，capability 只保留不可變 digest／identity facts。
- 普通 `load()`、舊 `load_same_bytes_v1()` 及一般 consumer reload/projection 的 API 仍沿既有路徑；
  additive manifest API 只在 experimental invocation capability 使用。相容性案例確認 legacy
  projection 在建立 capability 前後一致。
- 負例涵蓋 invalid UTF-8、invalid JSON、self-hash 錯誤、active manifest 被換成同 JSON payload
  的不同原始 bytes，以及 ancestor manifest 的同 payload／不同 bytes 替換；均 fail closed。

已知限制與 owner QA note 一致：能力建立前的 path recheck 是兩次 bytes 觀察，不是 lease，無法排除
A→B→A 或最後一次檢查後的變更；此 slice 不提供 pointer／candidate／artifact／SQLite 的跨資源原子快照，
也未接入 `RecommendationService`、decision receipt 或 training lineage。

## 獨立 fresh TEMP 路由

使用新的合成 TEMP `C:\Users\archi\AppData\Local\Temp\r26mr91d2bcf`；`PROFILE=test`、
`TEMP`／`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 和 pytest basetemp 均隔離於該根目錄。執行命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_model_artifact_same_bytes_loader.py tests/test_r026_invocation_model_capability.py tests/test_ml_model_artifact_loader.py tests/test_ml_model_artifact_manifest.py -q -o addopts= -p no:cacheprovider --basetemp C:\Users\archi\AppData\Local\Temp\r26mr91d2bcf\p
```

結果：**56 passed**，結束碼 0。console log：
`C:\Users\archi\AppData\Local\Temp\r26mr91d2bcf\console.log`；SHA-256：
`D1A8638F34803EB4C4F9EE50507A88488C58CCB09ED1C57DB62BEF55AFBC08A5`。

未執行 scheduled main，未讀寫正式資料根目錄；未 stage、commit 或 push。全域狀態仍依 owner note
維持 R026 `IN_PROGRESS`、`TMP-ML-01` `ACTIVE`、R028 `BLOCKED`。

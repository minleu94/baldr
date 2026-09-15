# BankTaiwan 首次排程學習執行失敗紀錄（2026-09-15）

## 結論

2026-09-15 05:50 的 BankTaiwan recommendation-learning shadow task 不是資料擷取或 candidate 訓練失敗，而是 shared authority root 的成本情境防護被錯誤觸發。舊版 `challenger/current.json` 沒有成本情境欄位，reader 將缺少欄位的 marker 依相容預設解讀成 legacy fixed 50 bp；同一 root 的 `latest_status`、decision receipt 與 candidate 實際屬於 BankTaiwan electronic estimate，因此被判定為跨 lane 衝突。

正式資料、candidate、manifest、artifact 與 receipt 均保留，未刪除、重建或覆寫；本次修復也沒有重跑正式 05:50 任務。

## 實際失敗證據

| 項目 | 證據 |
|---|---|
| 排程 task | `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` |
| 執行時間 | `2026-09-15T05:50:03-07:00` 至 `2026-09-15T05:50:05-07:00` |
| wrapper 結果 | `status=failed_dependency`、`reason=child_exit_code:2`、`recoverable=true` |
| input fingerprint | `sha256:848408b70b641a2738f97eda201790bf5581b6401391338f14218acdc3557501` |
| requested scenario | `banktaiwan-electronic-estimate:sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450` |
| 錯誤分類 | `decision_reason=cost_scenario_root_conflict` |
| 錯誤中既有 root | `legacy-fixed-round-trip-bp:sha256:1e50e15cf30f3bd25f1a142f264d9755fed486fee234c9c794d5534122906d5e` |

原始排程 receipt：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs\2026-09-15-attempt-001-848408b70b64.json`

該檔案大小為 74118 bytes，最後寫入時間為 `2026-09-15 05:50:05.242 -07:00`，檔案 SHA-256 為 `sha256:7f18a633324817fa41d4bad26ef8b2a7dbcd76da9bb0a62eb3cbad5511e7792c`。

## Root authority 讀取比對

| marker | 最後寫入時間 | SHA-256 | 關鍵結果 |
|---|---:|---|---|
| `recommendation_learning/challenger/current.json` | `2026-09-14 19:13:44.727 -07:00` | `sha256:6b8cb4b6ca086e9667b6c61852ba0ef94dbcdc0b17836c93fd6a84b390401f76` | schema `recommendation-calibration-challenger-pointer.v1`；有完整 candidate identity，但沒有 cost scenario 欄位 |
| `recommendation_learning/latest_status.json` | `2026-09-14 19:13:44.772 -07:00` | `sha256:7f474c74972e50b17e70f54eaafdeeae7b5ba1115b0b2cad8b89932b90721956` | top-level BankTaiwan cost scenario，candidate id `rec-cal-b48b793f35280ce0ff9d5109` |
| candidate `candidate.json` | `2026-09-14 19:13:44.704 -07:00` | `sha256:c35bb83e01d9758f8adce815b98923fafe541285737204e527afab5856e6d2ab` | `cost_scenario_hash=sha256:73ad…e450`；candidate freeze hash `sha256:13ac…f85d` |
| candidate `manifest.json` | `2026-09-14 19:13:44.703 -07:00` | `sha256:723b21b42261bd32abe3bc374abcea75d62d79c9ae3eebcea86efff782f19466` | manifest hash `sha256:0fff…32ce`；artifact hash `sha256:90d…a6b7` |

candidate root：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\runs\2026-09-14\scheduled-snapshot-5f4de77ffb404af2-efed573\candidates\rec-cal-b48b793f35280ce0ff9d5109`

同一 candidate 的 dataset hash 為 `sha256:4928f33774d499f24c1560980fc28f867b244144a5b22893a57874b556487d07`。唯讀回驗舊 challenger pointer 的結果為：

```text
STORED_SCENARIO banktaiwan-electronic-estimate sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450
ERROR None
ROOT_CONFLICT None
```

## 根因與修復

### 根因

`_cost_scenario_root_conflict()` 會掃描 shared root 的 active pointer、challenger pointer、latest status 與 decision receipts。舊 challenger pointer 沒有任何 `cost_scenario*` 或 policy/sizing 欄位；原本的 `cost_scenario_from_metadata()` 對這種 legacy shape 會套用 fixed 50 bp 預設，故把 BankTaiwan candidate 誤分類成 legacy root。

### 修復

- `_ensure_challenger_pointer()` 的兩條 writer 路徑現在都寫入完整 `_scenario_cli_metadata(cost_scenario)`，因此新建立的 challenger pointer 自帶 scenario id、version、hash、basis、policy、sizing 與 nested scenario metadata。
- 舊 pointer 仍可相容讀取，但只有在完整 candidate identity anchor 存在時才允許推導 lane：`candidate_id`、`candidate_root`、`candidate_freeze_hash`、`candidate_manifest_hash`、`candidate_artifact_hash`、`dataset_hash` 缺一即 fail-closed。
- 相容 reader 不再只相信 candidate.json 自宣告的 hash：會重算 canonical `ModelArtifactManifest`、實際 artifact bytes SHA-256、candidate freeze hash，並檢查 manifest/artifact/candidate identity、nested/flat cost metadata、cost contract hash 與 label registry hash 的一致性。
- 若 marker 已有完整新 scenario 且也帶完整 candidate anchor，仍會用同一套 candidate verification 比對 candidate scenario；避免只讀 pointer metadata 就解除 root guard。

## 隔離回歸與 QA 結果

執行的驗證均使用 pytest 暫存目錄或 read-only formal root inspection：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_daily_banktaiwan_learning_cost.py -q -o addopts=
14 passed, 1 warning in 4.47s
```

另已通過：

- `py_compile`：`scripts/scheduled/run_daily_recommendation_learning.py`、`tests/test_daily_banktaiwan_learning_cost.py`。
- 真實 BankTaiwan 舊 challenger pointer read-only 回驗：scenario hash 正確且 `_cost_scenario_root_conflict()` 回傳 `None`。
- 新 writer 產出的 valid BankTaiwan pointer：scenario fields 與 candidate hash 一致。
- 舊 pointer 的 candidate cost field 被改動但保留舊 scenario hash：拒絕。
- artifact bytes 被篡改或 artifact 遺失：拒絕。
- candidate_id-only / 不完整 identity pointer：拒絕。
- legacy fixed 50 bp root 與 BankTaiwan lane：仍拒絕跨 root 重用，且既有 legacy state bytes 不變。

針對排程 script 的 mypy 執行被並行工作樹 `data_module/pit_sector_membership_reader.py` 的當時錯誤阻擋（行 2133、2183、2222、2315）；本次沒有修改該檔案。

## 尚未執行事項

本次沒有直接重跑正式 BankTaiwan schedule，也沒有改寫正式 Shadow root。待審核並釋出修復後，由後續排程窗口或受控人工 retry 驗證 wrapper 產生 completed receipt；若仍遇 dependency failure，應保留新 receipt 並依其新的 `decision_reason` 判讀，不覆寫既有 candidate/manifest/artifact。

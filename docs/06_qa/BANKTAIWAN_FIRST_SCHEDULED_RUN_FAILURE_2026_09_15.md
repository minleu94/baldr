# BankTaiwan 首次排程學習執行失敗紀錄（2026-09-15）

## 結論

2026-09-15 05:50 的 BankTaiwan recommendation-learning shadow task 不是資料擷取或 candidate 訓練失敗，而是 shared authority root 的成本情境防護被錯誤觸發。舊版 `challenger/current.json` 沒有成本情境欄位，reader 將缺少欄位的 marker 依相容預設解讀成 legacy fixed 50 bp；同一 root 的 `latest_status`、decision receipt 與 candidate 實際屬於 BankTaiwan electronic estimate，因此被判定為跨 lane 衝突。

正式資料、candidate、manifest、artifact 與 receipt 均保留，未刪除、重建或覆寫；本次未透過 scheduler 重跑正式 05:50 任務，後續受控 shadow retry 已另行完成並保留完整 lineage。

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

## 受控 shadow retry 實績（2026-09-15）

修復 commit `086ba60c0fe48e737b06c2018841b32d730a6410` 後，依主審批准以固定的 2026-09-15 snapshot 與既有 source custody 執行一次 dry-run，再執行一次真實 BankTaiwan 專用 wrapper。沒有啟動 scheduler、重跑正式 producer、改寫 formal DB／Portfolio／broker 或 order。

前置 dry-run 結果為 exit `0`：官方交易日判定 `true`、snapshot `verified`，snapshot hash 仍為 `sha256:8d88147cd56815bce3ac06da12d3231ac2d973dc60a92c1db6902520c07ac4cc`，成本情境為 `banktaiwan-electronic-estimate`／`sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`，且 `shadow_only=true`、`formal_order_allowed=false`。

真實 retry 使用的實際命令如下（wrapper 會將 child 的 `--capture-current` 固定帶入；source audit 仍以既有來源為 read-only input）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts\scheduled\run_banktaiwan_recommendation_learning_daily.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan `
  --snapshot-output-root D:\Min\Python\Project\FA_Data\output `
  --source-artifact-root D:\Min\Python\Project\FA_Data_Shadow `
  --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --decision-date 2026-09-15 `
  --history-start-date 2014-01-01 `
  --max-decision-dates 100 `
  --cost-policy-estimate-date 2026-01-01 `
  --research-order-quantity-shares 1000 `
  --research-order-lot-type full_lot `
  --research-instrument-type ordinary_stock `
  --child-timeout-seconds 7200
```

| 項目 | 實際結果 |
|---|---|
| wrapper/session | 首次真實 retry 的 exec PTY session `85079`；wrapper receipt 未持久化 child PID，故以 session、child command、receipt 與檔案 mtime 作為可追溯 handle |
| 首次真實 retry 時間 | `2026-09-15 06:33:12–06:33:25 -07:00`；外層 exit `0`，child `returncode=0` |
| operational receipt | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs\2026-09-15-attempt-002-848408b70b64.json`；SHA-256 `sha256:3a4e38a0bb0ecfa54f405936814350231536b32cb030f9d806fb9c92eff945cd` |
| retry 結果 | `status=completed_waiting_natural_maturity`、`reason=natural_forward_evidence_receipt_missing`；沒有 `cost_scenario_root_conflict` |
| child receipt | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\runs\2026-09-15\scheduled-snapshot-440e18cdaa2036d1-efed573\run_receipt.json`；SHA-256 `sha256:1363dab6020e9f047f73cb81f244a6337b09f083e30d319d10e383e8f54aae04`；`status=completed`、`decision=retain_current` |
| shadow flags | `broker_action=false`、`shadow_only=true`、`formal_order_allowed=false` |
| natural sample | `natural_matured_sample_count=0`、`natural_training_sample_count=0`、`active_pointer=null`；未形成 natural forward evidence，未 promotion |
| coverage | eligible symbols `1463, 1528`；`eligible_count=2`、`degraded_count=198`、`missing_count=0` |

受控 retry 只在 BankTaiwan shadow lane 產生當日 dataset／decision／capture／child receipt／challenger pointer projection 與 operational receipt。原 attempt-001 保持原檔與 hash：`sha256:7f18a633324817fa41d4bad26ef8b2a7dbcd76da9bb0a62eb3cbad5511e7792c`。既有 immutable candidate、manifest、artifact 亦保持不變：

- candidate `candidate.json`：`sha256:c35bb83e01d9758f8adce815b98923fafe541285737204e527afab5856e6d2ab`
- candidate `manifest.json`：`sha256:723b21b42261bd32abe3bc374abcea75d62d79c9ae3eebcea86efff782f19466`
- `recommendation_calibration.joblib`：`sha256:90d1828c84b53c1f929f1929fd17a29a4b7578ffeb307870ada39ea867f4a6b7`

舊 challenger pointer 的 hash 為 `sha256:6b8cb4b6ca086e9667b6c61852ba0ef94dbcdc0b17836c93fd6a84b390401f76`；retry 後由正常 writer 補齊完整 BankTaiwan scenario metadata，pointer hash 為 `sha256:45e5117f32cc5052a50380dd2c16bb8e419a529cc9901cbb9e7ae17fce719846`，candidate identity、freeze／manifest／artifact／dataset hash 與 scenario hash 均一致。source contract 亦在 BankTaiwan shadow lane 產生當日 immutable contract `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-15\d5f473ecd81ddab0\contract.json`（file SHA-256 `sha256:77a3234562bcb630585901c5b7b34461926cb2b71ae2014a92c34d12edabb013`），再原子更新 mutable `source_contract/latest.json`；這不是正式來源重建。

以 retry 前保存的 14 個 baseline 檔案逐一重算 SHA-256，snapshot、snapshot status、attempt-001、candidate／manifest／artifact、舊 source contract、source DB、官方事件／corporate-action manifest/status、technical publication receipt、TPEx／TWSE source receipt 全部 `MATCH`，`PREPOST_CHECK_BAD_COUNT=0`。其中 source contract 新指向的 2026-09-15 source manifests／receipts，其檔案最後寫入時間均早於本次 retry（最晚 `05:46:35 -07:00`），非本次 retry 寫入。

同一組參數第二次執行作冪等驗收，時間為 `2026-09-15T13:39:06.1961851Z–13:39:08.1062254Z`（`06:39:06.196–06:39:08.106 -07:00`），exit `0`。operational status 回報 `idempotent_replay=true`、`reused_run_id=2026-09-15-attempt-002-848408b70b64`、`reused_receipt_path` 指向同一 receipt；沒有新增 attempt-003，child receipt／candidate／manifest／artifact／pointer 的 mtime/hash 均未改變，只有 shadow operational `latest_status.json` projection 更新（post hash `sha256:10c6708761b8304b48966da59951ef7137308d9c2ea1afa60b953f805a1d5d01`）。

## 尚未執行事項

本次仍沒有直接重跑正式 BankTaiwan scheduler，也沒有觸發自然 forward evidence 或 promotion。`completed_waiting_natural_maturity` 只表示 shadow learning／gate evaluation 已完成；`natural_forward_evidence_receipt_missing`、formal PIT、observed cost、actual execution 與 broker eligibility 仍按原門檻維持 pending／blocked。若後續再次遇到 dependency failure，應保留新 receipt 並依其新的 `decision_reason` 判讀，不覆寫既有 candidate/manifest/artifact。

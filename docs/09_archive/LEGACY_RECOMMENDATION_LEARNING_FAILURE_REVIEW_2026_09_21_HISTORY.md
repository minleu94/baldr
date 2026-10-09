# Legacy recommendation learning：2026-09-21 失敗與 BankTaiwan capture 證據

本文件只記錄 2026-09-21 的 read-only scheduler／artifact review。沒有重跑
production pipeline、沒有改 Task Scheduler、沒有寫入正式 D 槽資料庫，也沒有把
BankTaiwan shadow capture 當成 natural credit 或績效證據。

## Legacy 05:45 failure

已知 task `baldr-recommendation-calibration-learning-daily` 的 action 是以
file path 啟動 `scripts\scheduled\run_recommendation_calibration_learning.cmd`；
2026-09-21 05:45 PDT 的 Task Scheduler result 為 `1`。shadow latest status
位於
`D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_calibration_learning\latest_status.json`，當輪為 `status=running`、沒有 `run_id`／process／steps；同日
pipeline log
`D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_calibration_learning\20260921_pipeline.log`
為 0 bytes。沒有找到仍存活的 child PID。

隔離的 real file-path subprocess 在清除 repo root、`PYTHONPATH` 與
`BALDR_PYTHON` 後，確實進入 `_verify_formal_technical_reuse`，首個錯誤是：

```text
ModuleNotFoundError: No module named 'data_module'
```

同一份 technical reuse 以 package import 執行時可回傳 `reused`，所以已定位為
CLI import path 差異，而非正式 technical receipt 本身的失敗。最小修正是入口先
將 repository root 綁入 `sys.path`，並讓 pipeline 對未預期 `Exception` 產生
bounded、create-only、fsync terminal receipt；`KeyboardInterrupt`／`SystemExit`
仍直接穿透。production 尚未以修正後程式重跑，故本文件不宣稱 scheduler 已驗收。

本輪隔離診斷摘要（ignored，不是正式資料）為：

`output/qa/scheduler_readback_20260921_1909/legacy_last_result1_diagnosis_20260921.json`

其 SHA-256 為
`sha256:38b21b7decb24cd2d57916f7f9665668d7c9b4735693217133b3a21ab47946bf`。

## BankTaiwan capture provenance

以下四份 immutable shadow capture 是 read-only readback 的完整摘要。合計 30 rows、
四個 capture dates（18 rows from 9/15–9/17，新增 12 rows on 9/21）；目前
`matured_sample_count=0`。每個 capture payload 只有 `captured_at` 與
`capture_as_of_date`，沒有 `created_at`／`decision_at`，因此沒有用 snapshot 的
post-hoc projection 補填 capture 時間。

- **2026-09-15／2 rows**：
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\captures\2026-09-15\scheduled-capture-440e18cdaa2036d1-c73ad38fa8a5c\rec-cal-b48b793f35280ce0ff9d5109-9e9974e49adf79dd48ba1bf2.json`；
  `captured_at=2026-09-15T21:33:24+08:00`；
  `capture_id=capture-462f9ff1e1c3cf5368deec63`；
  `capture_hash=sha256:600dbd742d6c512e289161e9cb8a6cca1b5203e1a0896a95600ccd5850380770`；
  file SHA-256 `sha256:3f10ac64956bd5736a7aacd02333265c896bb212663789d14e44627c2b46f39b`；
  source contract
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-15\d5f473ecd81ddab0\contract.json`；
  contract content SHA `sha256:d5f473ecd81ddab0855325eb6be1c78c143c1c2fc18e2497df226f3a146839b1`，
  file SHA `sha256:77a3234562bcb630585901c5b7b34461926cb2b71ae2014a92c34d12edabb013`，
  availability cutoff `2026-09-15T13:33:13+00:00`，checked at
  `2026-09-15T13:33:14.042910+00:00`。

- **2026-09-16／2 rows**：
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\captures\2026-09-16\scheduled-capture-2c3e129587a1710e-c73ad38fa8a5c\rec-cal-b48b793f35280ce0ff9d5109-9679a6a253a99797f8f5315c.json`；
  `captured_at=2026-09-16T20:50:14+08:00`；
  `capture_id=capture-67cd7a5b04071c223cd9aa72`；
  `capture_hash=sha256:01b5a1e017fb8f282f9344543202b1f2f93d913299db64a66005c4773fee78fa`；
  file SHA-256 `sha256:1bcbde40b679e4a6bea3372156041d5c8289a8790a551fb6cb2f31488ff716c3`；
  source contract
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-16\83f856b746a15c24\contract.json`；
  contract content SHA `sha256:83f856b746a15c24147e58f2b5ddd05697776e65e86b6f92886e3983434f8828`，
  file SHA `sha256:15912bc1e875e0de94423a7b242d146543e9cc090c3411998379189ef44fa60c`，
  availability cutoff `2026-09-16T12:50:03+00:00`，checked at
  `2026-09-16T12:50:04.488456+00:00`。

- **2026-09-17／14 rows**：
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\captures\2026-09-17\scheduled-capture-9d0ac58082f00b11-c73ad38fa8a5c\rec-cal-b48b793f35280ce0ff9d5109-91f5a9a82a01cee402804607.json`；
  `captured_at=2026-09-17T20:51:29+08:00`；
  `capture_id=capture-310614fa5e190e6baa56b698`；
  `capture_hash=sha256:c3c11c6444e378b32fa00b936efa30b32dc2b573501120cf6a28148579067b3e`；
  file SHA-256 `sha256:b50a6e3999cb13019e11dd8c34d28694d9940e9421809be16fc73595904b8b0a`；
  source contract
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-17\ada21139ba2e7a20\contract.json`；
  contract content SHA `sha256:ada21139ba2e7a20a061bddac4957f0084cc812a01d04a291be19320afd127b8`，
  file SHA `sha256:7d403bffe8b06f92d84a9c70c8c26624cf5a142cb8e265643dcb001e98667c96`，
  availability cutoff `2026-09-17T12:50:03+00:00`，checked at
  `2026-09-17T12:50:06.414733+00:00`。

- **2026-09-21／12 rows**：
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\captures\2026-09-21\scheduled-capture-0a03de82a19f1006-c73ad38fa8a5c\rec-cal-b48b793f35280ce0ff9d5109-dbaf2dc9da47e09132bc7463.json`；
  `captured_at=2026-09-21T20:51:10+08:00`；
  `capture_id=capture-8074505a65f625cc70d54f17`；
  `capture_hash=sha256:cd6201de2b7b3abcb2b8a1ddabe05b4832b9b2569397acce9e433136d8b4c5fe`；
  file SHA-256 `sha256:7849f9e5fd9f286db9850fe06ef1cacca6a17adc993dc360b4e3550794f69789`；
  source contract
  `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-21\a6cc1474ad2bb0cb\contract.json`；
  contract content SHA `sha256:a6cc1474ad2bb0cb29d8000a64af4cd3b36afa1cfe21c1bb84f239ad7c6bc48d`，
  file SHA `sha256:22b65bfdcd6429335993f191424ad631c9aef1f93f74702f33d08473a95a014b`，
  availability cutoff `2026-09-21T12:50:03+00:00`，checked at
  `2026-09-21T12:50:05.230154+00:00`。

前一輪 **2026-09-20** receipt（`source_date_end=2026-09-18`）的
`available_at=2026-09-20T04:30:44.151755-07:00`，只供歷史參考，不作 9/21 publication：
`D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-18\cfd6ce9b23dd7d5d\receipt.json`，
`run_id=20260920-1460`、file SHA-256
`sha256:1d97d6da0e22ee5a4565bf213d493246867d1eb89f4ab4c393e0e8eb14f81991`。

9/21 contract 實際綁定的 formal publication 是
`D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-21\673cd5cb03e630a1\receipt.json`，
`run_id=20260921-27840`、`source_date_end=2026-09-21`，原始
`available_at=2026-09-21T04:33:17.238788-07:00`
（`2026-09-21T11:33:17.238788Z`），`publication_time_verified=true`；receipt
file SHA-256 為
`sha256:c6a49f41145a013ee1873385f91efa869664f3c051ab39689365a3e0d2d2bf12`，
receipt `content_sha256` 為
`sha256:673cd5cb03e630a12af78668e048f5f1ca2bf8fc7daa1f8d5edd88c1ac6448de`。

Bank capture 所用的完整 source contract 是
`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-21\a6cc1474ad2bb0cb\contract.json`，
`contract_sha256=sha256:a6cc1474ad2bb0cb29d8000a64af4cd3b36afa1cfe21c1bb84f239ad7c6bc48d`，
contract file SHA-256
`sha256:22b65bfdcd6429335993f191424ad631c9aef1f93f74702f33d08473a95a014b`。
該 contract 原字段為 `availability_cutoff_at=2026-09-21T12:50:03+00:00`、
`checked_at=2026-09-21T12:50:05.230154+00:00`、
`technical.publication_available_at=2026-09-21T04:33:17.238788-07:00`、
`technical.publication_time_verified=true`，以及
`technical.prospective_feature_snapshot.captured_at=2026-09-21T12:50:03+00:00`。
因此正確順序是 9/21 formal publication 11:33:17Z → contract cutoff／feature
snapshot 12:50:03Z → checked 12:50:05Z → Bank capture 的
`captured_at=2026-09-21T20:51:10+08:00`（12:51:10Z）。這只證明 technical
publication／contract／capture 的時間順序與 hash custody；不表示歷史 PIT eligible，
也不表示任何 natural outcome 已成熟。

本輪 Bank compact proof（ignored）為
`output/qa/scheduler_readback_20260921_1909/bank_capture_collection_provenance.json`，
SHA-256 `sha256:7dcfe2dfc1f95f14597aa0898d283d65e3426d05b1ee309bd3b9e6e4591091d6`。
其中 `captures_total=30`、日期為 `2026-09-15`、`2026-09-16`、`2026-09-17`、
`2026-09-21`，並保留 `natural_evidence.status=pending`、
`matured_sample_count=0`。

## 邊界與後續驗收

這次修正只處理 Legacy CLI 可載入性與 terminal failure 可見性；不修 Paper
`scope_manifest_v2` migration、不改 source contract、不降低自然成熟／PIT／正式 gate。
安全驗收條件是下一個正常 scheduler run 能在新 CLI path 下產生 terminal receipt，且
technical reuse／child status／原始 log 均能被 read back；在該驗收前，09/21 的
`LastTaskResult=1` 仍是已證實的工程 blocker。

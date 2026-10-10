# A02：私人 H20 毛報酬契約與受控讀模型

> **後續整合範圍（2026-10-10）**：本文保存 A02 的隔離合約與 reader 交付；後續收據記錄 H20 consumer、lineage wiring 及十股真保存讀回。這仍不等於正式來源資格、PIT／自然成熟或產品啟用 Gate 通過；現況看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)與[中央整合收據](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md)。

本包已完成隔離工程：既有 calibration 的 H20 absolute gross return head → 精確 artifact／lineage／runtime pins → 原 same-bytes loader → typed 整數 bp 輸出。最終 focused **64 passed／3.92s**；原 loader 相鄰 **16 passed／0.66s**；三檔 targeted mypy、三檔 compile 與既有 quant guard 通過。僅合成 artifact，沒有載入三個來源未證候選、真 fit、正式 Task 或正式產品啟用。

固定 base：`36dc1baf740007834f385ff0f654c7fe268a36f3`。獨立 branch：`codex/baldr-a02-h20-gross-20261006`；worktree：`output/worktrees/baldr-a02-h20-gross`。本包新增四檔，原 trainer／loader／config／main／consumer／Task／Manual／原 plan 均未修改。

## 既有 API 與目標裁決

- `ml_module/recommendation_calibration_training.py::_fit_return` 以 `row.stock_return_bp` fit return head；成本與 benchmark 不參與此 head。
- `RunnableRecommendationCalibrationModel.predict` 把 return head 的輸出轉為整數 `RecommendationPrediction.ranking_score_bp`；同次的 upside／after_cost 機率維持原 calibration 定義。本包不修改原 target、calibration、H5 excess 或其 artifact。
- 既有 `RECOMMENDATION_HORIZON_TRADING_DAYS=20`、`RECOMMENDATION_RETURN_BASIS=close_to_close_event_date`。新 view 的 target 是 `absolute_forward_stock_return_bp`，cost basis 是 `no_cost_gross`，沒有用費稅抵減值或 benchmark 超額替代毛報酬。
- `SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1` 已有捕獲 manifest 與同份 serialized artifact bytes 的驗證／反序列化路徑。本包的 `PinnedH20GrossArtifactLoader` 繼承該 loader，只在原已捕獲 manifest 進入 decode hook 前核本包精確 pins；原 loader 檔案不改。
- 原 public lineage API 是 `read_recommendation_training_lineage(path, expected_manifest_hash=..., expected_dataset_hash=..., expected_candidate_id=...)`，返回含 `payload`／`manifest_hash` 的 immutable lineage。本包由 composition 明示注入；沒有自動接未知來源或把自稱 verified 的 metadata 當權威。

已有 gross head 時，新 gross 訓練不是既有 calibration 日常使用的前置條件。只有 `gross_head_missing` 才需要另議最小新增訓練 scope；本包不自動 fit。自然樣本數為零或效果未成熟也不是此工程介面的永久載入阻塞；來源與模型資格仍須由中央核定，hash 只證明 bytes 身分。

## A03 凍結介面

`ml_module.personal_h20_gross_model_contract`：

- `H20GrossModelContract`：綁 artifact_root／lineage_path、model_id／model_version／candidate_id／dataset_id／dataset_hash、model_family、精確有序 feature_schema、feature_registry_hash／label_registry_hash、manifest logical/raw hash、artifact hash、candidate raw hash、lineage logical/raw hash、training source/PIT hashes、training_as_of 與完整 runtime versions。target／horizon／price／cost／adapter／contract version 固定於本 v1。
- `contract_hash`：含上述全部 frozen 欄位的 canonical JSON SHA256；runtime mapping 複製後不可寫。`capture_model_version` 唯讀返回 `candidate_id`。
- `H20GrossInferenceRequest`：symbol、decision_date、feature_as_of_date、feature_available_date、feature_schema、feature_values（tuple of int／None）、feature_snapshot_hash、feature_source_hash、model_contract_hash。
- `H20GrossInferenceOutput`：request、status、predicted_gross_return_bp、model_id／model_version、model_contract_hash、artifact_hash、lineage_hash、blockers、固定 target／horizon／price／cost／contract version。`to_dict()` 可 JSON 保存，`prediction_id` 綁原請求；資格旗標固定 false。
- `H20GrossInferencePort.predict(request)` 與 `H20GrossLineageReader` 是中立 typed protocols，冷 import 不引入 trainer 或 App namespace。

`ml_module.personal_h20_gross_inference`：

```python
loader = PinnedH20GrossArtifactLoader(contract, data_root=config.data_root)
service = PersonalH20GrossInference(
    contract,
    lineage_reader=read_recommendation_training_lineage,
    artifact_loader=loader,
)
output = service.predict(request)
```

`status` 僅 `h20_gross_available`／`h20_gross_unavailable`；可用時為整數毛報酬 bp，不可用時 prediction=null 且有 blocker。缺 loader／reader 在來源讀取前拒絕；原未 pin loader 亦拒絕。失配不轉為零，不自動換來源，不授予交易或自然證據資格。

原版本欄位有兩種語義，必須分開核：candidate.json 的 `model_version=self.model.model_id`，canonical capture row 的 `model_version=candidate_id`。因此 A03 原 capture 可把 `ranking_score_bp` additive 投影為 gross，前提是核 `row.model_version == contract.capture_model_version`、candidate metadata 的 `model_version == contract.model_version`，及原 artifact／manifest／dataset／features／lineage/source/PIT pins。不要強迫這兩個同名欄位相等，不從 calibrated_probability／after_cost 推毛報酬，也不需要重推論。

## 時序、安全與驗證邊界

- request 要求 feature_as_of < decision_date、feature_available <= decision_date；模型 training_as_of 不可晚於 decision_date。created_at 必須 aware 且日期不晚於決策日。這是沿既有日粒度決策契約，不新增未給定的 intraday decision timestamp 或官方 trading-calendar 證明。
- candidate 拒錯 target／H5／bool horizon／price basis／exact schema／version／hash／資格旗標，以及 `legacy_unproven`／`training_lineage_missing`。lineage 必須同原已核 payload、exact artifact/dataset/source/PIT pins、decision_time context 與非空 training rows；不把未知 lineage 補造為可信。
- runtime 核 manifest 完整版本與 caller frozen versions，並以當前 process 的 `importlib.metadata.version` 觀測每個 distribution；不只沿原 loader 的 major.minor 相容規則，也不接受 caller 字串替代實際 runtime。
- 原 sidecars 在 lineage verifier 前捕獲、verifier 後／decode 前、loader 後及 prediction 後重核 raw hash。pin loader 在 decode 前核已捕獲的 logical manifest／artifact hash；替換 manifest 的測試證明 deserializer 呼叫數為零。
- sidecar 每檔讀取上限 64 MiB；原 artifact loader 捕獲／decode 行為保留，沒有宣稱增加整個 artifact 或 decode RAM 上限。沒有新增 filesystem ACL／私人 root custody 政策。
- request 的 snapshot/source hashes 是 caller 核定來源 pins，A02 不讀 market/features 資料也不重建 upstream snapshot。A03／中央須核實際 canonical row／snapshot 與 pins 的綁定；typed string 不代表取得 PIT 或來源權威。
- production／formal／natural 資格固定 false，synthetic 成功不授真上線。價格基準只沿原 event close-to-close metadata，不冒稱已核公司行動／歷史調整資格。
- 無新增裸 float；模型本身既有 sklearn 數值邊界保留。新輸入／輸出只接受整數 bp 或明示 None。

## 驗證與 immutable raw

raw／JUnit 位於本 worktree 的 `output/qa/a02_h20_gross_20261006/`，不 stage。測試分類建議 `service-oracle-recommendation`；新增 test 清冊登錄交中央，不擴本 lane 四檔 ownership。

| 驗證 | 結果 | raw |
|---|---|---|
| focused 首跑 | 59 pass／1 fail，4.80s | focused-first.txt／xml |
| pin fallback 修補後 | 63 pass，4.12s | focused-final.txt／xml |
| 實際 runtime 觀測及 readonly protocol 完成後 | **64 pass，3.92s** | focused-runtime-final.txt／xml |
| 原 loader ＋原 same-bytes tests | **16 pass，0.66s** | adjacent.txt／xml |
| targeted mypy（含新 test） | 三 sources／0 errors | mypy-final.txt |
| py_compile | 三新增 Python 檔成功 | compile-final receipt |
| quant_guard_linter | precision／lookahead exit0 | quant-guard.txt |

首跑 failure 是新 predecode-pin fallback 未帶回已驗 manifest，原 wrapper 的 canonical identity invariant 正確拒絕；修補返回 manifest，原 assertion 保留。首次擴至 test 的 mypy 五 errors 是 readonly dataclass 對 writable protocol 欄位不相容與測試 dynamic kwargs 型別；改為 readonly properties 與 typed kwargs 後通過，首跑 raw 保留。各重測結果不累加成總 suite 數，也不代表全倉 gate。

最終 focused 覆蓋：合成序列化 artifact → 原 lineage builder/reader（不 fit）→ 原 same-bytes loader → gross1234bp；零自然樣本可推論；兩個機率 head 不當毛報酬；新程序 JSON readback／原 artifact bytes/mtime 不變；冷 import 無 trainer/App；非法金融數值、缺 ports、錯精確版本／features／target／hash、未來模型／feature、unknown lineage、來源改變／消失與 decode 前替換拒絕。

| raw | SHA256 |
|---|---|
| focused-first.txt | `3fae333303f7e054d35529ed074060b1dce9c0555fd6e97722e5038f09e11a92` |
| focused-first.xml | `02a1d394cac294f95317f5fd6edd55aec6794982b43eb158175bb9f0e5f38aa3` |
| focused-runtime-final.txt | `9390802c1dc513bb3d4e9f689cd0444077be55b2ddeb7dcc3764c213ca475048` |
| focused-runtime-final.xml | `0e174607d0fe6b4f8d7e650a98bebe9ae4b1a309075d98acab3c86c9ee511878` |
| adjacent.txt | `0ca41e9fd1cbf2827c96c082487c730fbfa419dd32fa4f69babb7f329ab85d69` |
| adjacent.xml | `51bf7b2957217ce457e627b524c0920bb4e2054059b08a1b2a183fa38f299603` |
| mypy-final.txt | `281a094c39385b4d7b53e5db635f52158036861433c2a4975b9039e77a627a24` |
| quant-guard.txt | `0b6c600d7337a098cbb9aafe589eb7e1a77625f3325de1b11366195b0b361ec7` |

## 剩餘接線與回滾

中央須重新生成原 target 的可信 lineage 並核定 pins，注入原 reader／新 pinned loader；三個 legacy 未證候選維持拒絕。A03 保存每日 capture 的 additive gross projection、自然結果與日常 consumer 接線由各 owner 完成；config／main／Task／Manual／原 plan 在中央，不由 A02 共寫。自然時間與效果成熟屬結果證據，不能代替或永久阻塞這些工程接線。

回滾新增 contract／inference／tests／本 QA 四檔：採入前不採本 commit；採入後先核 A03／中央依賴，再 `git revert <A02 commit>`。只回滾本包新增內容，無原資料刪除風險；已有下游依賴時會中斷 gross view，須同時由其 owner 調整接線。沒有寫 shared_state／Manual／registry，是本次 exact ownership 限制，交接內容由中央保存。

# 個人 Current-observed H20 每日入口：擴鎖交接

日期：2026-10-06。固定 base：`f15ce80425e4bba2e12446da00547a7cc4618679`。

狀態：**blocked_scope；未實作每日入口，未新增自然樣本**。本收據不是 synthetic-only 驗收終點。使用者要求模型真正參與日常選股研究；自然成熟用來改善效果，不是等待模型個人使用的工程 gate。

## 排他範圍與回滾

原授權只新增 `scripts/scheduled/run_personal_current_observed_h20_daily.py`、`tests/test_personal_current_observed_h20_daily.py`、本文件。中央 `01a11020-88c2-7506-acc3-d51ecb674032` 保留 shared state、main、config、Task、Manual。本輪僅新增本文件；沒有為交付數量填入不可供自然結果消費的旁路 JSON。

回滾：`git revert <本文件提交完整雜湊>`。只撤銷本文件；不刪原始資料、既有預測、收據或 worktree。風險：失去此次擴鎖交接文字。

## 既有 public API 核實

| API／位置 | 實際契約 | 對本任務的限制 |
|---|---|---|
| `ml_module/recommendation_calibration_evidence.py:2549`，`verify_current_observed_input_capture` | 驗證 no-model v1/v2 input capture；capture ID、source binding、entry pin、aware capture clock、cost contract 都須通過 | `forbidden_fields` 明拒 `predictions`、`candidate_id`、`model_id`；不能把原 H20 輸出塞入 bootstrap capture |
| `ml_module/recommendation_natural_outcome_service.py:580`，`RecommendationNaturalOutcomeService.build_current_observed_outcomes_for_capture` | 接受上述 immutable no-model input capture 與明示後續 current-restated source；建立 current-observed outcome | 不讀 H20 原始預測，不驗其 candidate／fit／contract／prediction 身分；直接呼叫不等於模型自然效果 join 完成 |
| `app_module/recommendation/personal_prediction_capture.py:106`，`capture_personal_saved_result` | 先 `queries.get(result_id)`，核 canonical/index/receipt，create-only 封存已交付結果 | 今日 QA raw snapshot 推論沒有 canonical RecommendationResult；不得自造 result ID |
| 同檔 `read_personal_prediction_capture` | 每次重讀原 canonical execution/receipt 並比較 stable capture identity | 不能以自建 JSON 或今日新政策代替原保存結果 |

唯讀成功重現來源為 repo 主 checkout 的 `output/qa/baldr_real_model_intake_20261006/observe_current_verified_gross.py`。它沿原 `prepare_contract`、`load_current_observed_context_from_pinned_snapshot`、`MLHistoricalSnapshotProvider.load_current_observed`、`HistoricalFeatureBuilder.compute_current_observed`、`PersonalH20GrossInference.predict`，但其 scope 已明示 `QA capture only, no canonical recommendation capture`。本輪閱讀此檔，**沒有重跑十檔真推論**，不把先前成功算成本輪驗收。

## 精確擴鎖要求

保留 ML／provider／guard 原檔全唯讀，請新增下列正式 App adapters 及測試的排他鎖：

1. `app_module/recommendation/personal_current_observed_h20_capture.py`：typed H20 原始 prediction create-only writer／public reader；以原 no-model capture 原始 bytes pin 作來源身分，獨立模型研究 capture，不冒充 canonical RecommendationResult。
2. `tests/test_personal_current_observed_h20_capture.py`：原 pin 負例、同 identity 重試不再推論、partial/cancel、fresh process readback、檔案 custody／衝突。
3. `app_module/recommendation/personal_current_observed_h20_outcome.py`：沿原 no-model capture/outcome verifier 的 App join adapter；核已保存 H20 預測與自然價格結果一對一身分，保持 research-only 與成熟 pending。
4. `tests/test_personal_current_observed_h20_outcome.py`：wrong capture/cycle/source/model/symbol、未成熟／部分成熟、重讀、自然 outcome exact join 負例。

上述新增檔在原三檔之外，**尚未授權，未建立**。不要求改動 `recommendation_calibration_evidence.py` 或 `recommendation_natural_outcome_service.py` 的 no-model gate；舊 bootstrap 與舊個人 canonical capture 語義保持。若中央已有另一受控保存／自然 join 接口，可用其明確 API 取代新增 adapter，但需能獨立 fresh-process 消費，不接受只由每日 script 自行讀取的 JSON。

## Frozen CLI／API 提案與中央接線

以下為待擴鎖後實作的介面提案，**目前不可執行**：

```text
scripts/scheduled/run_personal_current_observed_h20_daily.py
  --request-json <絕對路徑>
  --request-sha256 <sha256:raw-request-digest>
  --gross-fit-receipt <原可信fit收據絕對路徑>
  --gross-fit-receipt-sha256 <獨立核准raw-fit-digest>
  --receipt-root <隔離個人研究保存根>
```

`run_personal_current_observed_h20_daily(*, request, receipt_root, gross_fit_receipt, expected_fit_receipt_sha256, cancelled=None)` 為每日 composition。`read_personal_current_observed_h20_capture(path, *, expected_sha256)` 為正式 fresh-process consumer。自然 adapter 應接明示 prediction capture path/raw pin 與原 outcome path/raw pin，不掃描「最新」，不接受 caller 自填 return／label。

request 明示 `cycle_id`、`cycle_terminal_path`、`cycle_terminal_sha256`、原 source envelope/snapshot pins、原 no-model input capture path/raw SHA、exact symbols、`history_start_date`、`expected_feature_as_of_date`。CLI 不接受 `observed_at` 的回填；使用執行當下 `datetime.now(timezone.utc)`，decision day 取 Asia/Taipei。feature-as-of、來源發布、local observation、真正 prediction observation 必須分開，不能把當下看到的 restated 資料聲稱當年已可得。

中央在原 current-stock raw terminal `completed` 後傳 exact pins；原 fit receipt `f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1` 指向可信候選 `rec-cal-3f8b2c276ef316e28de3806d`。沿原 frozen training source/lineage 建 contract，今日 inference source 獨立驗證；不把 live DB 替換原 V2 frozen fit source。

保存 join identity 至少包含原 input `capture_id`／raw SHA、cycle／terminal SHA、candidate／contract hash／fit receipt raw SHA、symbol／feature row hash／inference source fingerprint、原 H20 request／prediction bytes hash。重試先讀同 source/candidate/day/symbol 身分的已保存列，保留原 clock 與預測 bytes；cancel／failure 已保存部分不得重算或另造自然樣本。必要的輸入／預測／結果保存應有正式 reader 可供 App／自然 adapter 使用。

## 驗證與剩餘

本輪只做 API／原始碼唯讀核實與 graphify query。graph query 命中既有 Recommendation persistence、ResultArtifactStore、snapshot provider，但其圖不作新 H20 保存／自然 join 的證明；上述 blocker 以固定 base 原始碼為準。

未新增 Python，因此 focused pytest／JUnit、targeted mypy、py_compile／quant 變更檢查 **not_run**；不得報為通過。不重全倉測試。待中央擴鎖後才實作並產出 focused raw/JUnit、targeted mypy／compile／quant、完整 commit/blobs；自然成熟保持真實 pending，不以 synthetic 驗證替代每日真模型使用終點。

Git worktree 初次因 sandbox Git ref 寫入權限失敗；相同 authorized `git worktree add` 經 `require_escalated` 成功。沒有 reviewer rejection，沒有修改 ACL，沒有 push、Task 註冊、真資料搬移、交易或清理。

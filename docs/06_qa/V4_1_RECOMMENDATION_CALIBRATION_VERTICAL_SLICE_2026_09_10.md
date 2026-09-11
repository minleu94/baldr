# V4.1 A 線：推薦機率校準垂直切片（2026-09-10）

## 結論

本輪完成一個 research-only、可重現的推薦校準最小垂直切片。它把既有
`EvidenceEvent`／`EvidenceOutcome` 組成固定 20 trading-day primary target 與
5 trading-day auxiliary target，按 decision date 做 expanding
train／calibration／untouched-test walk-forward，輸出基準、原始 score、整數 bp
isotonic calibration、機率分箱、樣本與 Wilson 不確定性、Brier／ECE、成本後與
benchmark 比較。

正式推薦行為沒有改變：不改 `ScoringEngine`、推薦權重、threshold、alpha、
production scheduler 或 promotion pointer。歷史 replay／sample 也不折抵自然
forward evidence credit。

## 固定 outcome contract

| 欄位 | 本輪契約 |
|---|---|
| decision time | `EvidenceEvent.decision_date`；`event_date`、`as_of_date`、`available_date` 不得晚於 decision date |
| primary target | 20 個 trading days；`upside = forward_return_bp > 0`；`after_cost_profit = forward_return_bp > fixed_round_trip_cost_bp + observed liquidity_cost_bp` |
| auxiliary target | 5 個 trading days，使用相同兩個 label |
| 報酬 | `EvidenceOutcome.close_to_close_event_date`，label end 使用 `outcome_price_date` |
| benchmark | 直接使用既有 `benchmark_return_bp`／`benchmark_excess_bp`，缺值不補零 |
| 成本 | `fixed_round_trip_cost_bp + EvidenceOutcome.liquidity_cost_bp`；缺 liquidity cost 的 row 不進 after-cost label；未提供的手續費／稅費不假設為零 |
| universe | `event_type=recommendation_included`、`symbol` 非空，使用 event 當時保存的 universe／rank evidence；不讀目前 universe、不回填歷史事件 |
| probability | 所有輸入／輸出為整數 bp（0–10,000）；Brier／ECE 也以整數 bp 保存 |

`ranking_score_bp`、`score_percentile_bp`、`upside_probability_bp`、
`after_cost_profit_probability_bp`、`action_suitability`、`evidence_confidence`
是不同欄位。`action_suitability` 只使用 `research_candidate`、
`research_watch`、`research_review`、`not_evaluable` 研究語意，不能解讀成下單
指令；`evidence_confidence` 是資料完整性／來源品質，不是勝率。

## 已完成項目

- `app_module/recommendation_calibration.py`：建立成熟 outcome dataset、future-dated input fail-closed、固定 universe policy、20／5 horizon、purged expanding split、整數 bp isotonic、baseline prevalence、raw score、calibrated probability、10-bin calibration table、Brier、ECE、Wilson 95% interval、forward／benchmark／cost-adjusted summaries。
- `scripts/inspect_recommendation_calibration.py`：支援 `--sample`、`--db-path`、`--format json|markdown`、`--output`、fixed cost 與 universe policy；來源 DB 以 repository 的 SQLite read-only path 讀取，不建立 schema。
- `RecommendationEvidenceImporter`：未來新匯入的推薦事件另保存既有 DTO 的 `indicator_score_bp`、`pattern_score_bp`、`volume_score_bp`；這是 price／volume ablation 的決策當下欄位，不回填歷史 event。
- `price_volume_v1` 已作為 challenger ablation 接口；係數在 train label 上以整數 bp grid 選擇，再只用 calibration block 校準，不能用 test block 調參。
- report 固定宣告 `production_eligible=false`、`natural_forward_evidence_credit=false`、`recommendation_weights_changed=false`，並保存可重算的 dataset manifest／feature registry／label registry／split policy hash。

## 可重現驗證

使用 repo 已存在的 Python 3.11 virtual environment 執行：

```powershell
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' -m py_compile app_module\recommendation_calibration.py scripts\inspect_recommendation_calibration.py
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' -m pytest tests\test_recommendation_calibration.py tests\test_recommendation_evidence_importer.py tests\test_score_effectiveness_read_model.py -q -o addopts=
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' -m mypy app_module/recommendation_calibration.py scripts/inspect_recommendation_calibration.py
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' scripts\inspect_recommendation_calibration.py --sample --format markdown
```

結果：定向測試 `14 passed`；新增模組與 CLI 的 mypy `Success: no issues found`；
sample 為 `567` events、`1,134` observations、`3` folds，20 日 primary
`score_percentile_v1` calibrated OOS `n=72`、Brier `720 bp`；同一 sample 的
`price_volume_v1` Brier 也是 `720 bp`，所以研究決策為
`retain_current_method_no_oos_improvement`。

另跑完整 pytest 時，collection 在 8 個既有 ML promotion／daily shadow 測試停止，
共同原因是工作樹缺少 `runtime/promotion_authority_secret_store.py`；該檔案在本輪
開始前即不存在，錯誤未觸及本輪新增模組。故本輪採認定向 evidence／recommendation
回歸 `45 passed` 與完整 application-scope mypy `506 source files` 通過；完整 suite
的既有缺件仍需另行修復，不能被本輪結果掩蓋。

## 正式 evidence DB 的實際 read-only 結果

以 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 執行：

```powershell
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' scripts\inspect_recommendation_calibration.py --db-path 'D:\Min\Python\Project\FA_Data\sqlite\twstock.db' --format markdown
```

讀到 `217` recommendation events、`8` outcomes，但 `0` 成熟 observations、
`0` walk-forward folds，狀態為 `not_evaluable`。診斷是：

- `missing_outcome_20d:215`
- `missing_outcome_5d:215`
- `universe_policy_assumed:215`
- `universe_policy_mismatch:2`

這不是負績效，也不是可以用 fixture 補成有效；它表示目前正式 evidence DB
尚未提供可配對且成熟的 20／5 日 outcome。CLI 前後讀取到的正式 DB
`LastWriteTimeUtc` 相同，未做任何 DB 寫入。

## 未完成與下一個 slice

- 自然 forward evidence 尚未累積到可形成正式 OOS；歷史 working-copy replay
  只作研究資料，不替代 scheduler／自然觀測。
- 舊 event 沒有 component score 時保持缺件，不回填；price／volume challenger
  只有在未來 importer 保存欄位後才可得到真實 matched OOS。
- chip／funding、industry、PIT theme 尚未接入此 calibration dataset；下一步須
  先建立各自的 decision-time／available-date／source fingerprint contract，
  再以相同 universe、cost、20／5 horizon 做增量／消融，不能把 current snapshot
  直接當成歷史 PIT feature。
- fixed cost 預設為 `0 bp` 只是明確的「未提供固定成交成本」設定，不代表完整
  手續費、證交稅、turnover 或 execution ledger 已完成。
- 若 challenger 沒有 matched OOS Brier 改善，保留 current score method；本模組
  沒有任何自動 promotion 或正式推薦接線。

## 安全邊界

本文件、sample、歷史 evidence report 都是 research evidence。close-to-close
forward return 不是可執行實盤績效；不產生交易建議、不寫正式資料、不授予
Formal／ML alpha／promotion credit，也不把單次 sample 的結果稱為投資有效性。

# derived-h5 修訂研究雙時鐘契約（2026-09-22）

## 目的與範圍

本契約為 derived-h5 模型家族定義一個隔離的 restated-research row 格式。它只驗證列與資料集證據欄位的結構，不建資料、不 fit、不載入模型，也不替代正式 PIT gate。輸出永遠是 research-only；任何歷史決策、正式 OOS、promotion 或 production 主張都保持關閉。

本次程式只新增：

- `ml_module/derived_h5_restated_research_contract.py`
- `tests/test_derived_h5_restated_research_contract.py`
- 本 QA 文件

`ml_module/allocation_contracts.py`、revision gate、Direct/OOC builder 與 R027/R028 檔案均不修改。R027/R028 處理 publication writer/orchestration，不是修訂資料 acceptance、完整重建或重訓 owner。

## 固定模型家族與 identity

契約只接受既有家族 `baldr-ml-allocation-derived-h5-v4-rank-v2`、H=5、62 個有序 feature IDs、既有 feature order hash `sha256:a2a3a26f457f9901f90b1f08d3e844defe7abe279a22d722d197f56d3eb19611` 與 registry hash `sha256:8b0f831a94ecd503591a146d36412b2385397928b98fbd607a33fa6073630f27`。新 dataset 必須使用 `restated-derived-h5-` identity 前綴，並綁定已封存 run02 snapshot SHA `sha256:38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771`。

62 個 slot 的精確名稱與順序固定在 leaf module。每列使用 `int64` 整數值、正整數 scale、明確布林 mask；缺值必須是 `None` 且 mask 為 false，觀測值必須是整數且 mask 為 true。特徵內容 hash、mask hash、feature order hash 與 registry hash 都要相符。這些驗證不重算來源內容，也不讀取數值 store。

目前 leaf 只要求 scale 是正整數並把它納入 feature content hash；它**不驗證**逐欄 scale 的實際語意、normalization 轉換或 frozen preprocessor 相容性。即使 62 slots 與 hash 結構通過，也不能宣稱模型 input compatible。未來 builder 與獨立 QA 必須逐欄比對 frozen release registry、scale/unit、缺值處理及 normalization。

來源 identity 必須列出 run02 snapshot、price receipt、technical receipt、recovery receipt、technical verifier、corporate-action exclusion manifest、feature lineage manifest、label lineage manifest 與 fold manifest 的 SHA-256。Contract 會驗雜湊格式、必要項目及 dataset identity 的一致性；這些欄位仍是呼叫端申報，不能替代對實際檔案 bytes 的 readback 驗證。

## 雙時鐘與標籤規則

`historical_decision_at` 是原始歷史樣本的決策時間。`revision_observed_at` 是本研究資料集觀測／保全修訂值的時間，不代表來源首次可得時間，也不提供歷史 `available_at`。修訂觀測時間必須晚於原決策時間；`training_as_of` 必須不早於修訂觀測時間。

H=5 標籤要提供 `horizon_end_date`、權威 `authoritative_available_at`、label value hash 與可得時間證據 hash。`horizon_end_date` 是台北交易日；契約會先把有時區的 `authoritative_available_at` 轉成 `Asia/Taipei` 再比較本地日期，避免 UTC 日期邊界造成錯誤拒絕。可得時間不得早於 horizon 結束，且必須不晚於 `training_as_of`。Contract 不會由 horizon 日期推造 label `available_at`。若 corporate-action exclusion manifest 缺失或標籤列被標記為受公司行動影響，該列拒絕進入候選列。

Fold 必須由 fold manifest hash 識別，日期分割不得重疊或倒置；purge 至少 60 個交易日、embargo 至少 5 個交易日。Contract 檢查宣告的範圍與列分配，但不重跑交易日曆、purge 選列或 OOS 驗證；這仍需後續 fold producer 與獨立 QA 證據。

## 接受／拒絕矩陣

| 輸入情況 | 結果 | 可主張內容 |
|---|---|---|
| 9/22 才觀測到修訂值；原決策早於修訂；`training_as_of` 晚於修訂與成熟 label；62 slots、order/registry、values/mask hashes、完整來源 identity、公司行動排除與 fold identity 格式皆有效 | row contract 結構通過 | 僅可視為未來用途的 restated research 候選列；`historical_pit=false`、`formal_oos=false`、`promotion=false`、`production=false` |
| 來源 hash、dataset identity、feature slot/order/registry、values hash、mask hash、dtype/scale 或 fold identity 缺漏／不符 | fail closed | 不接受該列 |
| 缺 label 權威 `available_at` 或其證據 hash、label 尚未成熟、`available_at` 早於 horizon end、或 training clock 倒退 | fail closed | 不接受該列；不得由 horizon end 補時間 |
| 缺 corporate-action exclusion manifest，或 label 列仍受公司行動影響 | fail closed | 不接受該列 |
| row 欄位結構完整，但全資料集缺 62-feature 覆蓋、feature/label 全窗口 lineage、公司行動排除驗收或新 fold 驗證 | dataset evidence 維持 `pending` | 不得宣稱資料集 evidence 完整，更不得進入 fit |
| 呼叫端宣告所有摘要 count/boolean 完整，但沒有實際內容 readback／獨立 verifier | 最多標示 `research_candidate_evidence_declared_complete_unverified` | 只是未驗證的結構宣告，不是資料 acceptance、fit 授權、OOS 結果或 promotion 資格 |

`research_only=true`、`historical_pit=false`、`formal_oos=false`、`promotion=false`、`production=false` 是不可由建構參數覆寫的常數。此 leaf 不暴露 `fit_eligible`，也不會呼叫或修改既有 `PortfolioMLDatasetRow`。

## run02 的實際狀態

目前 868-row custody artifact 只證明修訂價格來源列（865 列 OHLC 完整、3 列缺值）；它沒有完整 62-feature vectors、feature lineage sidecar、物化 label、label availability evidence、與 run02 綁定的 corporate-action exclusion、全窗口 lineage 或新 fold manifest。因此目前真實資料狀態仍是 `pending`。Synthetic positive test 只證明欄位契約的預期語意，不能拿來聲稱真實資料已被接受。

新的雙時鐘 row 格式不轉換成既有 `PortfolioMLDatasetRow`。舊契約仍要求每個特徵 `available_at <= decision_at`；9/22 才觀測的值在歷史決策時不可用，既有 consumer 必須繼續拒絕。這份契約也不繞過正式 `check_daily_price_source_revision` gate。

## 驗證

執行 focused tests：

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -o addopts= -p no:cacheprovider tests/test_derived_h5_restated_research_contract.py
```

測試覆蓋 late revision research row、原 PIT consumer 拒絕 late feature、固定 62-feature order/registry/hash/mask/dtype、缺 source/label/company-action/fold evidence、training clock 逆序、台北交易日跨 UTC 日期邊界、purge/embargo 邊界，以及 dataset 保持 pending／unverified 的語意。

## 回滾清單

本變更只新增上述三個檔案，且在 ignored linked worktree 與 task branch 中完成。回滾方式是只還原該 task branch commit，或刪除這三個新檔；不需要改動主 `dev` 工作樹、正式資料、既有模型或 PIT gate。

# R006 Luna 回修之 SOL 初審完成

## 判定

R006 原有的相容性過度宣稱已改成可追溯的分層清冊。SOL 前兩輪 findings 均已在 R006 原範圍修正；目前可送 Gemini 獨立審查，但不是最終 PASS 或 Wave 1 release。唯一既知 shadow-boundary 測試失敗仍保留為既有 baseline，沒有被 allowlist 或 production 修改掩蓋。

## 實際檔案與證據

- 只變更 `tests/test_refactor_ml_compatibility_baseline.py`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md`、`REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。凍結 SHA-256 依序為 `ee182953773ebbf3e8e4d77632454bba8ee45bd7f9f0124a4e2d2634e9372f0e`、`f3c609ecc79398c5863ec03c2015036ef5b83e41eed34b9b960130c8db90ffd2`、`be26a22c42e6133711d0ebabc869922d17d5848570f8c6155cc7c7eca97df4b7`。HEAD 保持 `391b057c`。
- SOL 對 QA 表 15 條 Direct source 逐檔獨立重算原始 bytes size 與 SHA-256，15/15 與目前工作樹相符。QA 同時列出 source owner、Direct stable identity 與 runtime snapshot 分帳、14/15 loaded-code 觀察限制及 reader/writer 程式責任；這些沒有被宣稱為正式 DATA_ROOT 寫入授權。
- Historical 20 欄順序/dtype/unit/missing、`None→NaN` 與零值區別有新增斷言；受控 joblib fixture 經預設 SafeShadow loader 實際載入。另有 source-declared／controlled-fixture／artifact-readback／unknown 的 ABI→test 對照，明示 imputer/scale、HGB mask、OOC persisted tuple 與正式 class path 的證據界線。
- R001 的 7-manifest source-rebuild 目錄在 QA 中使用完整 `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` 名稱。OOC persisted `(year_ordinal, local_row_index)` 只列 `source-declared`；合成 causal fold 另列 `controlled-fixture verified`。未知 pickle/joblib 沒有反序列化，也沒有補 sidecar、移檔或寫正式 artifact。

## SOL 驗證與限制

SOL 在最終 Python 測試版本重跑 `.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py -q -o addopts= -p no:cacheprovider`，結果 `8 passed in 0.21s`，exit 0；最終兩輪只有 QA／報告文字與測試註解變動，測試斷言語意未變。Luna 對 ABI 對照所指的 affected focused cases 執行 `21 passed, 1 warning in 137.69s`；更早的完整 10 檔 focused suite 真實結果為 `73 passed, 1 failed in 477.36s`，其中唯一 failure 是已知 `test_repository_respects_ml_shadow_dependency_boundary` 四條 production→ML import。不可把本次描述為完整 suite PASS。changed Python 的 `py_compile` 與 `git diff --check` exit 0；格式檢查通過。

## Gemini 獨立審查焦點

請驗收清冊是否足夠供 R010/R026/R027 使用且未把 source/manifest metadata 當模型相容證明；檢查 15-path identity、歷史 20 欄、OOC/Direct refs、safe loader／未知資產分帳、18 個所選資產 hash 保全、權限描述與四條既有 guard failure 的歸屬。對任何超出 R006 scope 的兼容缺口只要求具名記錄，不要求載入未知 binary 或修 production。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

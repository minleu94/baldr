# R005 SOL 最終送審前核對

> **時點／狀態導覽（2026-10-11）：** 本文 `AWAITING_GEMINI_REVIEW` 是 SOL pre-review 當時標籤；後續 Gemini `PASS` 與 SOL integration acceptance 見 [R005 SOL integration review](R005_SOL_INTEGRATION_REVIEW.md)。R031 index 記錄 R005 disposition 為 `ACCEPTED_WITH_R020_BOUNDED_REPLAY`，不外推到所有 profiles 或整體 Wave 完成；詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 與 [R020 implementation report](R020_IMPLEMENTATION_REPORT.md)。原 pre-review 證據保留。

R005 本輪僅在 `tests/test_recommendation_replay_characterization.py` 與 `R005_IMPLEMENTATION_REPORT.md` 加入價位上界 oracle。SOL 逐讀測試與 `RecommendationDataFrameProvider._passes_fast_filters` 的現行政策：前收 100、末收 110 在 `price_change_max=10` 精確邊界通過；末收 110.01 被拒，scorer 未收到該股。availability cutoff 仍逐列排除未來可得資料，先前有效列達 20 列時該股可照既有語意推薦，不能誤改成整股 veto。

SOL 獨立執行 V-REPLAY 五個 focused suites：`66 passed, 24 warnings in 2.56s`，exit 0；24 個 warning 是既有 same-day-close 研究假設提示。R005 worker 報告單檔 `13 passed`、py_compile exit 0。無 production、正式資料、repository 或 ML 改動。

凍結 SHA-256：

- `tests/test_recommendation_replay_characterization.py`：`F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`
- `REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`：`14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F`

此處僅是 SOL 初審；R005 仍待 Gemini 對實際 repository 獨立審查。Wave 2 不得放行。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

> **時點／範圍導覽（2026-10-11）：** `TASK_STATUS: PASS` 記錄的是本文所述 R005 V-REPLAY SOL integration review；R031 index 記錄 R005 disposition 為 `ACCEPTED_WITH_R020_BOUNDED_REPLAY`，不代表所有 profiles 或整體 Wave 均已完成。詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 與 [R020 implementation report](R020_IMPLEMENTATION_REPORT.md)。原 review verdict 與證據保留。

# R005 SOL 整合驗收

## 判定與證據

Gemini 對 Luna 回修的正式唯讀審查判定 R005 `REVIEW_STATUS: PASS`；原文保存在 `WAVE1_R003_R005_GEMINI_REVIEW.md`（SHA-256 `D7012AEAE4AAE3DA9B0B3592197F5D5490D9F522DA8B398F96C3132FC0EF475D`）。SOL 核對實際測試檔與任務報告，兩者 SHA-256 分別為 `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`、`14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F`，與審查凍結版本一致。

實際測試以合成 DataFrame 固定 replay 同 mode snapshot、future append 不變、逐列 availability 截斷、數字 YYYYMMDD、lookback／max-stocks／min-rows、價量邊界、分數回退／排序、個股例外隔離及 portfolio factor manifest。實作報告清楚區分互動推薦、legacy DataFrame provider 與 replay wrapper；不要求跨 mode 結果相等。R001 的舊 source-path 錨點已另行勘誤並通過 SOL review。SOL 重跑 V-REPLAY：`66 passed, 24 warnings`、exit 0；警示為既有同日收盤研究假設。未修改 production policy、回測撮合、保存 writer 或正式資料。

R017/R020 必須以這份同 mode oracle 檢查遷移；未出現的 parent／child ID 與歷史 annotation readback 仍由後續 task 驗證。

TASK_STATUS: PASS

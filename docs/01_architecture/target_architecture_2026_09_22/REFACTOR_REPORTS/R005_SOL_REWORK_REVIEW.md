> **時點／狀態導覽（2026-10-10）**：本文的 `CHANGES_REQUIRED`、`READY_FOR_REVIEW`、`BLOCKED` 與 Wave／下游 gate 敘述，只代表撰寫當時的 implementer／reviewer／root 裁定，不是目前 disposition；目前 task 狀態看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，現況看 [Project Snapshot](../../../00_core/PROJECT_SNAPSHOT.md)。原審查結論與限制保留。

# R005 Luna 回修之 SOL 初審

## 判定

R005 回修已補齊前次 `CHANGES_REQUIRED` 的主要 characterization oracle；SOL 逐讀實際測試及 production replay/provider seam，並獨立重跑 V-REPLAY。此處是送 Gemini 獨立審查前的初審，不是 wave release 或最終 PASS。

## 實際 scope 與 acceptance 證據

- 回修只聲明修改 `tests/test_recommendation_replay_characterization.py` 與 `REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`；兩檔起始 SHA-256 分別為 `4FE16FC67B72FDD4E48FF47BA3A206542C938400F0315539CE7DBB59A6511312`、`DC71C444F19AB8ADA27F72B065AE07B51BED5F8430DA08E0F37E0CB4F2BA06E9`，回修後為 `9a5dd653da2d1bbcdf3e5e8cc15238cdeae830880dc9fc8b55afbe932869684b`、`07b0c0e07154e5648f6cf7dbe81c74873e9af0c702b2251c0d0202a538d30630`。HEAD 仍為 `391b057c`。沒有 production code 改動歸屬於 R005。
- 同 mode full snapshot 對固定 profile/config/date/regime、ordered rows、factor scores、reason、diagnostics 有具名 expected；future append 以極端分數重驗完整 snapshot 不變，scorer 實收截止日也固定。
- availability test 同時檢查 provider 實收 row 數／最新日期、排除列數與最終 recommendations；數字 `YYYYMMDD`、universe、lookback 80、自訂 lookback、max stocks 200、自訂上限、20-row minimum、價量 fast filter、score fallback、stable tie/top-N 及個股例外均有獨立 fixture。
- Portfolio case 固定外層 snapshot 日期、profile/config、ordered recommendation 及完整 factor snapshot/contributions；expected 是測試明列值。DataFrame provider 被正確標為 portfolio/replay legacy evaluator，而非 interactive 入口。
- 無 portfolio parent ID、持久化 annotation readback／重算隔離、per-stock exception reason diagnostics 等目前不能由此 fixture 證明的項目，報告具名列為 gap；未宣稱跨 mode 相等或 downstream 完成。

## SOL 獨立驗證

命令：`.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py tests/test_historical_evidence_replay.py tests/test_recommendation_historical_replay.py tests/test_recommendation_portfolio_backtest.py tests/test_backtest_timeline_contract.py -q -o addopts= -p no:cacheprovider`

結果：`65 passed, 24 warnings in 2.43s`，exit 0。24 個 warning 為既有 portfolio same-day-close 研究假設提示。`py_compile` 對 R005 測試檔 exit 0；`git diff --check` exit 0（只有既有 tracked dirty paths 的 LF/CRLF 提示）。

## Gemini 獨立審查焦點

請核對上述 golden 是否真正能區分同 mode 行為變化、portfolio factor expected 是否與 legacy source 獨立、availability／exception gap 是否如實描述、R001 source-path 差異是否不影響本次 oracle。若有可在原 R005 scope 修正的缺口，明列具體斷言或檔案行號；勿要求在本 task 修改 production。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

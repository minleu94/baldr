# Smart Money 主表欄寬重複量測快取（2026-10-27）

## 變更

Smart Money 主表依目前 `TerminalTableModel` 和字型／DPI 度量快取集中度、語意、badges、診斷欄的內容寬度。同模型重排或視窗 resize 時沿用內容度量；診斷欄最終寬度仍按目前 viewport 重算，保留原欄寬限制及顯示結果。建立新模型或字型／DPI 度量改變時重新量測。沒有改 DTO、顯示值、來源或金融資格。

## 受控量測

在 1,600 列合成 DTO、offscreen Qt 與真實 `SmartMoneyFlowView`／`TerminalTableModel` 下，先完成 layout settle，再重複呼叫欄寬 fit 30 次：

| 指標 | 原本 | 快取後 |
|---|---:|---:|
| 首次 fit | 50.146 ms | 49.886 ms |
| 後續 fit p50 | 47.3499 ms | 0.0107 ms |
| 後續 fit p95 | 52.7499 ms | 0.035 ms |
| 後續 fit 文字／badges 重量測 | 90／30 次 | 0／0 次 |
| 後續 fit 掃描列數 | 192,000 | 0 |
| settle 後五欄寬 | `[54, 66, 220, 156, 190]` | `[54, 66, 220, 156, 190]` |

首輪內容量測仍約 50 ms；改善範圍是同模型後續 resize／layout fit，不能外推為 T0–T4 或整個頁面載入延遲改善。這是合成資料的 offscreen 微基準，不代表真實螢幕繪製或正式資料規模。

機器可讀結果位於工作區的 `output/tasks/smart-money-column-measurement-20261027/evidence/scanner_column_fit_benchmark.json`。原始 settled baseline 與前後受控執行收據位於同任務 evidence 的 `single_owned_qa_bf41836c2ed84a208eddb598a8064448/`、`single_owned_qa_c10d19c6334740e0a33d60e8b87c0610/`。

## 驗證與限制

- Smart Money view／async：26 passed。
- Update tab validator：25 passed、0 failed、4 skipped。
- 修改 Smart Money view targeted mypy：成功；修改 view 與測試檔 `py_compile`：成功。
- 必要 Workbench UI suite：55 passed、2 failed。失敗位於 Advice detail 缺件欄位呈現及 Advice-to-backtest 導航身份測試，涉及本切片範圍外功能；因此 UI regression Gate 尚未清除，不能宣稱這份工作通過完整必要 UI 回歸。
- 未驗真實主視窗、原生繪製、其他 DPI／字型與 Owner UAT。
- Feature map、UI features、QA index 與本次兩份 QA 報告的 scoped document link check 通過。Task-wide document-control check 仍回報 Snapshot 既有四個缺少的錨點，以及其他文件指向被排除的 `output` 儲存 junction；不宣稱 repo-wide document check 全通過。

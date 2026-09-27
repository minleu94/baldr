# 2026-09-26 工作區分批提交驗證紀錄

## 範圍與起始狀態

- 分支：`dev`；起始 HEAD：`bb23a162f3ca3875ddbe5799fbd45d10b92cc3d4`，起始時比 `origin/dev` 超前 257 個提交。
- 起始 `git status --porcelain -uall` 共 10,268 行，沒有已 stage 變更；包含 20 個追蹤檔案修改、59 個根目錄 `.tmp_*`、5 個 `.obsidian` 設定檔、1 個 `Untitled.canvas`、10 個 BALDR QA 文件及測試／fixture。
- `git status` 的 10,268 行主要是未追蹤目錄展開後的路徑列，不是實體檔案總數。暫存目錄未刪除；以 repo 根目錄限定的 `/.tmp_*/` 忽略。
- 本輪未執行 scheduler、正式資料更新、資料重建、SQLite 寫入、ML promotion 或 push。

## Focused 驗證

- A–F 起始聯合路由（11 個測試模組）：206 passed、20 failed。失敗全在推薦校準 E 組；最初以 Windows TEMP 路徑作 pytest basetemp 時，Windows no-follow reader 在開啟 `C:\Users\archi` 目錄 handle 得到 WinError 5。改用 repo 內短 basetemp 後，此路徑障礙消失，並修正 E 組測試 double 以建立本次 invocation stdout artifact；未放寬 missing-artifact 負例。
- Slice E 最終路由：74 passed，66.43 秒，exit 0。
- Slice C 合成 fixture 後路由：63 passed，2.15 秒，exit 0。OS TEMP basetemp 為該路由所需，因一項 PIT 隔離測試明確要求輸出位於系統 TEMP。
- Workbench UI 測試：84 passed，2.18 秒，exit 0。
- `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped，exit 0；報告寫入已忽略的 `output/qa/update_tab/`。
- 廣域 mypy：724 個來源檔案，0 issues。
- 本輪 23 個修改／新增 Python 檔案 `py_compile` 通過；`git diff --check` 通過。Git 顯示既有 LF/CRLF 轉換警告，沒有 whitespace error。

上述 focused 路由不是整個 repository 的完整測試套件，也不構成正式資料或生產接受證據。

## 本機產物處置

- 根目錄 `.tmp_*`、`.obsidian/` 與單一 `/Untitled.canvas` 已加入精確忽略規則；沒有使用全域 `*.canvas`，沒有刪除目錄或草稿。
- Paper preopen 測試 fixture 曾含真實 machine paths、資料庫位置、cash/total value、source ID 與來源雜湊；已轉為結構等價合成收據，保留 canonical/schema/safety flags、日期與 snapshot 關係，並固定合成 bytes 長度 5,416 與 SHA-256 `8084250A3B2F738CD76E811A6636DB40DABD6A606F10F8FAFF1909FC54E5C795`。
- `BALDR_PRODUCT_INTEGRATION_BASELINE_20260925.json`（3.05 MB）與 `BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json`（170 KB）含機器 dirty-path 原始清單與完整 automation prompts/IDs；依本機輸出排除原則保留為未提交檔案。其他八份 BALDR 摘要／QA 文件未發現 credential 欄位或投組金額欄位。

## 限制

- 首輪 20 項 E 失敗源自 Windows TEMP ancestor handle 權限；後續在 repo basetemp 的 Slice E 全部通過。
- 不代表跑過 repository-wide pytest，也沒有執行真實排程或正式資料驗收。

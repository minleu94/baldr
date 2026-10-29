# MOPS 每日月營收候選排程 QA（2026-10-29）

## 範圍

修復每日 Quick 漏接 MOPS 靜態月報候選、更新頁手動抓取可能把單市場半成品發布，以及期別提示在每月 10 日週末切換過早的問題。TWSE／TPEx OpenAPI 現況候選仍是獨立子流程。這輪只新增候選採集與 selector 發布守衛，不改正式 SQLite、availability mapping 或 PIT 資格。

## 變更與契約

- `scripts/scheduled/run_daily_data_update_quick.cmd` 預設啟用獨立 MOPS snapshot 候選旗標；可用 `BALDR_CAPTURE_MONTHLY_REVENUE_MOPS_SNAPSHOT_CANDIDATE=0` 單獨停用。既有 OpenAPI 子流程仍由 `BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE` 獨立控制。
- `scripts/scheduled/run_daily_data_update_quick.py` 只在核心完成狀態／history 發布並釋放 heavy-chain reservation 後才執行 MOPS child。兩個候選 child 依序執行，各自使用 receipt；MOPS 子程序失敗或逾時不改核心狀態與退出碼。核心失敗則不啟動 child。
- `scripts/capture_mops_monthly_revenue_candidate.py` 使用台灣市場日期與共用月份期別函式，抓取一個預期期別的 SII／OTC MOPS 靜態月報，保存 HTML、各市場 SHA／source version、列數、診斷及候選 CSV。雙市場資料、必填值、期別、診斷及原件未完整時不產出 CSV。
- 排程 run 先留下 `scheduled_capture.json`；只有候選 CSV、詳細 receipt 與最後 `capture_complete.json` 都成功後，selector 才會接受該排程候選。未完成發布的 CSV 不會遮蔽既有候選。既有手動 capture 目錄仍相容。
- Update tab 的 MOPS 手動抓取也要求所選市場／期別均有列、無解析診斷、鍵唯一且當月值非空；不完整結果保留診斷／raw，但不寫出可選 CSV。
- 共用期別提示以台灣日期計算每月 10 日申報期限，遇週末順延至週一，期限當日仍使用前兩個月份。此為抓取期別提示，不代表每家公司均已公告。

## QA 結果

- 定向候選、selector、UpdateService、UpdateView、排程整合與另外三個現有 UI 操作稽核檢查：**47 passed，1 skipped，15 deselected**。15 個未選入案例不屬本次 MOPS 路徑；整個 `tests/test_scheduled_data_update_runner.py` 在本環境執行時另有既存案例受 TWSE 臨時休市來源 DNS 失敗／環境狀態影響，故不能宣稱全檔通過。
- 必要 Update workbench UI：**98 passed**。
- `scripts/qa_validate_update_tab.py`：**25 passed／0 failed／4 skipped**；輸出導向 ignored 本機 scratch，所有 fixture 使用隔離雙根。
- 修改及相關 Python 檔 `py_compile`：通過。
- 修改來源 targeted mypy（5 files）：**0 issues**。repo-wide mypy 未通過：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- 執行使用專案既有 Windows owned Job：每次讀回 8 GiB／12 process 限制，available RAM > 8 GiB；各程序自然退出，Job 關閉。

## 尚待自然排程驗證

這輪未手動啟動正式每日核心排程，也未對外重抓 MOPS，因既有 ROTC／PUB 歷史事件採集正在執行。Task Scheduler 已有 daily Quick `.cmd`，因此無須改註冊；需在下一次自然排程後檢查 `latest_status.json` 的 `monthly_revenue_mops_snapshot_capture.result_receipt_path` 及 MOPS child receipt，確認雙市場候選／marker 可由 Update tab selector 讀到。取得排程證據前，只能說修復程式與排程 wiring 已驗，不能宣稱 production schedule 已成功。

目前正式月營收仍為 **251,189 observed／727 degraded**。新候選採集不會解除舊列 degraded、建立公告 mapping 或寫正式 DB；剩餘 degraded 需依歷史事件 harvest 與精確版本／時間證據另行裁決。

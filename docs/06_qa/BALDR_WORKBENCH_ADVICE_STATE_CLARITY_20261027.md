# Workbench Advice 載入狀態易讀性 QA — 2026-10-27

## 變更範圍

Workbench Advice 的「尚未載入」、「本次沒有可顯示的建議」與「無法載入策略建議」各自顯示白話說明及下一步。錯誤狀態會先清除舊建議；原始狀態碼與載入診斷移至可鍵盤操作、可複製且有高度限制的技術診斷區。拒絕新增部位仍維持獨立結論。這只改變文字、診斷展開及無障礙描述，不改策略資格、Advice 生成或資料來源。

## 驗證狀態

- 新增狀態案例與必要 Update Workbench regression：**98 passed**，位於受控執行收據 `output/tasks/workbench-advice-state-clarity-20261027/evidence/single_owned_qa_ec4e8ae881324be684ea1118d543e3a7/stdout.log`；收據 SHA-256 `24686fdda67ee752217cdb73d144c5049e7acf5c0456d2740ae3510d84212350`。其中 Workbench 新狀態案例檢查白話標題、狀態切換時收合診斷、原始代碼／訊息可讀、載入錯誤清警告與三張表清空。
- 完整 Workbench view suite：**55 passed、2 failed**。既有失敗分別為 `test_advice_detail_lists_missing_required_contract_fields_without_filling_them`（期待的提示字串與目前方法輸出不同）及 `test_advice_contract_backtest_navigation_carries_exact_current_candidate_identity`（回測導航按鈕仍隱藏）。兩者涉及本次未修改的契約判讀及導航條件；完整 suite 未標成通過。收據 SHA-256 `b9e8abff3e855ea5b5882c6b0a20ee3ff2e6b7272fe57fe787d0ccc18981cf28`。
- `scripts/qa_validate_update_tab.py`：**25 passed、0 failed、4 skipped**；受控收據為 `single_owned_qa_0551bf43a6f1487c9eb06fed79d7591a/receipt.json`。
- 全目錄 mypy 已執行，但在 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到語法錯誤後停止；定向 `mypy ui_qt/views/workbench_view.py` 通過（1 source file）。較早一次全目錄啟動嘗試時，可用 RAM 為 **3.38 GiB**，受控包裝器在建立子程序前拒絕；之後資源恢復才重跑。
- 兩個修改 Python 檔 `py_compile` 通過，受控收據 SHA-256 `3c5b71fb4122c08e7f71b2206ea8620e32cdea32b0137c0335ca924f2e020b10`；`git diff --check` exit 0。
- `document_control check --task` 的 task route／必要文件檢查沒有錯誤，但整體 exit 2，錯誤僅為 Snapshot 內四個既有 `BALDR_MARKET_SESSION_TEMPORARY_CLOSURE_CADENCE_20261026.md` 舊錨點；收據 SHA-256 `dae29b23bcb9022c04583080dee71ff17b9da122011e1dfc2169c8b10a336dad`。對本次更新的架構、功能、QA、手冊與指南地圖另做定向 check，12 features／6 link sources／0 errors，通過；收據 SHA-256 `1854c7fd492d13e8ad8ca64698bf8d4a840a1a4f1f3cbf79074873ccc5af1bc7`。原生 GUI／Owner UAT 未執行。

所有 Python 驗證都由此任務 evidence 目錄的 root-owned Windows Job wrapper 執行，8 GiB／12 process／kill-on-close 限制讀回成功；成功與失敗的執行在結束時 Job 剩餘程序均為 0。

此項不代表正式來源、Gate、PIT、ML 或 Owner UAT 接受。全目錄 mypy 須等未改檔案的語法錯誤排除後才能完成；兩項 Workbench 失敗及 Snapshot 舊錨點限制保持可見。

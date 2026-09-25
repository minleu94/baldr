# R008 aware datetime 深凍結回修裁決

SCOPE_DECISION: CHANGES_REQUIRED_WITHIN_R008

獨立 Luna 對最新 R008 凍結版發現 `datetime` 雖為不可變外殼，卻可持有呼叫者所有的可變 `tzinfo`。SOL 在 2026-09-22 用 `tzinfo.utcoffset()` 依 mutable `hours` 回傳偏移的最小案例重現：建立 `Context.decision_at`、`NegativeEvidence.observed_at` 與 `QualityReport.metrics["clock"]` 後，將原 `tzinfo.hours` 從 0 改為 9，三個已封存值的 `utcoffset()` 都由 0 變為 9。這是 INV-08 的實際 alias 漏洞，並可能改變既有決策時點的解讀，不能作為單純測試限制接受。

依 R008 原「aware clocks／nested mutable input-output mutation／深凍結」範圍，分兩個互不改同檔的 Luna Max worker 回修：app owner 僅碰 `app_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py` 與其專項報告；decision owner 僅碰 `decision_module/recommendation/contracts.py`、`tests/test_r008_decision_numeric_enum_rework.py` 與其專項報告。目標是在 seal 時對 aware datetime 建立不可再受原 `tzinfo` 修改影響的時間快照；保留當刻 wall-clock、微秒、fold、UTC offset 與 ISO/timestamp，並覆蓋直接欄位及巢狀 mapping/records。不得改舊服務、數值、ML 內部、codec、writer、UI 或 R009/R010。

兩個 worker 完成後，SOL 必須重跑 R008 focused、相鄰 recommendation/exec 測試、mypy、py_compile 與 diff/範圍檢查；因 code SHA 改變，任何先前 PASS 僅是舊快照證據。獨立 Luna 對同一新 SHA 複核，SOL 再決定 R008 與 Wave 2 gate。R009/R010 保持 blocked。

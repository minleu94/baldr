# Wave 1 Gemini 唯讀分析收件與 SOL 對照

- 來源：使用者提供 `<USER_HOME>\.codex\attachments\634621e7-baa4-461d-acbf-43c3ac8379c7\Pasted text.txt`，31667 bytes，內容標記 `WAVE1_PARALLEL_ANALYSIS`。
- 原文存檔：`REFACTOR_REPORTS/WAVE1_GEMINI_PARALLEL_ANALYSIS_REPORT.md`；下表為 SOL 與當前 repository 對照後的處置，不取代原文。
- Gemini 最終狀態：`ANALYSIS_STATUS: COMPLETE`、`NEEDS_FINAL_DIFF_REVIEW: YES`。這不是 R003、R005、R006 任一項的正式 `REVIEW_STATUS: PASS`。
- 對照基線：HEAD `391b057c`，以目前實際測試／production source 為準。分析報告撰寫時 Luna 正在回修，其「缺口」欄多指回修前版本，不直接當作當前 findings。

## SOL 對照與處置

| 任務 | Gemini 有效提醒 | 目前工作樹證據 | SOL 處置 |
|---|---|---|---|
| R003 | 五種 terminal 事件、同 service A/B、stale callback、worker lifecycle、巢狀 alias、progress/receipt 要用可判定 oracle。另提醒執行前取消應有 10% checkpoint，且新的 UI 執行開始會清空舊畫面。 | Luna 回修的 11 個新測試已覆蓋五種事件、同 service A/B、延遲 callback 覆寫、worker registry/destroyed、兩側 alias、執行後取消進度與 test-only receipt marker；SOL V-EXEC 39 passed。`RecommendationExecutionRequest.execute` 另有執行前取消分支；`RecommendationView._execute_recommendation` 在啟動 worker 前清空 table 與 `current_recommendations`，目前 R003 新測試未固定這兩點。 | 只在 R003 專用測試與報告加入執行前取消／新執行清空 last-good 的現況 oracle，記錄為 gap，不改 production。回修後重新凍結 SHA 與 review packet。 |
| R005 | 同 mode snapshot、future append、availability row 排除、`YYYYMMDD`、lookback/max-stocks/min-rows、價量 fast filters、fallback/exception 與 factor manifest 要有獨立 expected。 | Luna 回修的 12 個新測試已覆蓋上述主要政策；SOL V-REPLAY 65 passed。價量測試固定 `price_change_min` 與 volume 下界，但沒有 `price_change_max` 上界。Gemini 提議「未來 available_date 的股票代號完全不出現在結果」不符合目前 provider 對同一股票較早可用列仍可輸出的語意；現有測試逐 row 驗證被拒列沒進 provider／結果。 | 只在 R005 專用測試與報告補 `price_change_max` 邊界正反例；保留較早可用列的現況語意，不改 provider。回修後重新凍結 SHA 與 review packet。 |
| R006 | 15 路徑來源身份、20 欄 ABI、OOC/Direct、safe loader 與未知模型必須按證據等級分帳；既有 shadow-boundary 四條 import 不得 allowlist。 | Luna 回修後 QA 已列 15/15 raw bytes/hash、source owner、stable/runtime identity、20 欄、ABI→test 四級表、受控 joblib fixture 與 unknown class path；SOL 逐檔重算 15/15 hash 相符，R006 新測試 8 passed。完整長測仍為 73 passed、1 個已知 guard failure。 | 分析報告的「DummyModel 冒充正式模型」、「兩欄充當歷史 ABI」、「清冊已宣稱全資產相容」均是回修前問題，現在已修；R006 現有正式 Gemini review packet 仍有效，不因本次 analysis 直接標 PASS。 |

Gemini 分析中提到的 `last_config`／`last_results` 並非目前 `RecommendationService` 此路徑的實際 `last_*` 主欄位；實際 source 以 `last_run_context` 等欄位為準。其測試建議只作驗收提示，不擴張任何 R-task scope。R003/R005 回修完畢之前，既有 `GEMINI_REVIEW_R003.md`／`GEMINI_REVIEW_R005.md` 的凍結 SHA 視為待更新；Wave 2 仍 blocked。

## 補件完成後的狀態

上表保留分析收件當時的對照，不再代表當前待辦。R003 已補執行前取消與新請求清空 last-good 兩個 oracle，SOL V-EXEC 為 41 passed；R005 已補 `price_change_max` 邊界，SOL V-REPLAY 為 66 passed、24 個既有警示。兩份正式 Gemini review packet 已按最終測試／報告 SHA 重新凍結；R006 packet 的三個 SHA 亦已重核。三項仍待 Gemini **正式獨立審查**，本分析不將任何 task 標為 PASS，Wave 2 保持 blocked。

# Decision Desk 日期與保存診斷（2026-10-06）

## 實證與日期語意

本次僅唯讀查核正式資料與既有排程收據，未觸發 Task、補存快照或重建 EXE。稽核證據位於忽略的 `output/qa/baldr_date_semantics_audit_20261006/`。

- 工作台最新有效快照的 `decision_date` / `as_of_date` 為 2026-10-05；保存 ID 為 `dds_f3d93c395a764e89`，來源 `decision_desk_snapshot_v1`。日期是已保存快照的截止日。
- 美西 2026-10-06 晚間對應台北 2026-10-07；市場總覽預設以台北評估日作資料截止上限。正式公開行情最新可讀日期為 2026-10-06，不能把台北評估日當成行情資料日。
- 10/6 排程收據顯示等待重型作業鎖約 70 分鐘後取得鎖；snapshot 子程序執行 120 秒逾時，沒有有效 JSON，保存結果保持未知，後續 evidence 未執行。正式快照表亦沒有 10/6 新列；因此仍顯示 10/5。鎖持有人與逾時內部階段未由當時收據證明。
- 打包模組中的日期與刷新相關函式，與稽核時 source 相符；此現象不是已證明的 EXE 專屬路由錯誤。此次 source 修正尚未重建 EXE。

公開 SQLite 查詢採 `mode=ro`、`query_only=ON`，前後 DB / WAL / SHM 的檔案大小與修改時間相同。未輸出持倉或個人內容；未把推薦保存作業的成功收據當成 Decision Desk 保存成功。

## 修正範圍

工作台分列已保存快照日、行情／指數資料日、台北評估日，以及最近 Decision Desk 保存狀態。保存狀態只讀固定位置、限定大小與欄位的收據；缺件、錯誤格式與未來日期保留未知。歷史快照日期與 identity 不改成今天。

預設市場總覽的刷新重新取台北日期，明確歷史查詢仍保留指定日；沒有快照時的工作台 fallback 亦採注入的台北時鐘。既有 request generation 防止舊請求覆蓋新日期。

snapshot CLI 新增可選階段診斷；排程 snapshot 子程序開啟此診斷。只將固定階段、整數單調耗時與例外型別寫入 stderr，限制事件數，並 flush 以保留逾時前的最後階段；stdout JSON、保存資料、hash、Task 設定、逾時門檻與鎖契約均維持。收據增加診斷摘要，不輸出原始個人 payload 或例外訊息。

同次 Smart Money dashboard 改成載入一次 broker events 並按股票分組；保留日期 cutoff、穩定排序、重複股票順序、Decimal／整數計算與取消語意。上下文在結束時重設，下次摘要重新讀來源，沒有跨次快取。

## 公開資料效能證據與限制

有界公開 provider probe：市場 frame 日期讀取約 750 ms、行情列讀取約 1,594 ms、broker events 冷讀約 18,235 ms。這只能說明當次公開來源的耗時，不能定位原排程 120 秒的完整根因。

同一份唯讀公開 broker events、同一截止日、40 檔公開股票的前後比較：原版來源讀取 40 次、約 1,360 ms；新版讀取一次、約 109 ms；完整 dashboard DTO 相等。此比較隔離原始資料冷讀，因此不能宣稱整次 producer 已降至此耗時或自然排程已恢復。

## 驗證

- Producer／CLI／市場 frame／Smart Money：56 passed（UTF-8 環境）。診斷開關前後 stdout JSON 與 snapshot hash 相同；真子程序逾時保留已 flush 的階段且保存狀態仍為未知。
- 排程與診斷：52 passed。沒有更改 Task、timeout 與 evidence 子程序參數。
- 日期 UI／source／composer 六個 focused 測試檔：105 passed；包含台北午夜前後一秒的預設刷新、歷史日期固定、異常／未來收據與有界行情讀取。
- 必要 Workbench gate：85 passed；更新頁 validator：25 passed、0 failed、4 skipped。validator 僅在記憶體調整輸出路徑至本任務 QA 目錄，原腳本未改。20 個本任務 Python 檔案語法編譯通過。
- Full mypy 通過 849 個 source files；最後複核曾在另一個尚未 freeze 的個股模型成本 lane 發現一個型態錯誤，該 owner 已修正並回報 full mypy 849 檔通過。最終兩個 lane 固定後的 union gate 仍由整合 owner 執行，不把中間態當成本任務回歸。
- 修正後的正式唯讀 helper 回傳 10/6 擷取逾時、保存結果未知、行情／TAIEX 日均為 10/6，約 188 ms；DB／WAL／SHM pins 前後相同。fixture 與此讀回均不代表自然排程成功或正式交易證據。

原始 10/6 逾時需下一次獲授權的保存執行或自然排程收據補足階段證據。此次不透過延長 timeout、改鎖或改寫日期掩蓋問題。

# UX20 保存母體收據 UI 限定整合（2026-10-06）

基底 ae64afc0cc9fd6c970a86f3f350053cb7d851d82。本批完成 parent 保存收據唯讀瀏覽，Stage5／UX20仍partial。UX21獨立lane已由父層啟動（base ae64afc0）；其 app_module/rule_research_forward_outcome.py、tests/test_rule_research_forward_outcome.py 及QA未讀改／未提前整合，UX21保持pending。

## 入口與身份

每日研究條件新增「查看保存母體收據」。同一視窗重複開啟不建立第二視窗或背景工作；使用者選取 parents/<identity>/receipt.json，先由既有 BoundedRuleResearchParentWriter 驗 envelope，再由原 read_saved_parent_rule_sample_readiness 重讀 exact parent、原母體配置、child pins及方法。沒有掃描latest、開市場DB、producer、儲存新包、正式排程或 migration。

首屏為母體名稱／版本／保存資料日、決策截止與觀測時間、完整或未完整、captured/uncaptured分母、MA20／MA60方法版本與符合方法／不符合／未知／排除計數。表格各批producer發布結果與capture保存結果分列；顯示的是該保存收據記錄，重讀不會重跑producer。同一identity去重沿用首次收據，不能從其記錄推定最近CLI執行的狀態。

hash、完整來源／原配置／receipt／各批error及技術診斷預設收合；使用者可展開與選取。缺批為uncaptured，unknown不替負樣本；方法判定不當正式selected/nonselected。來源available-at／官方calendar／outcome maturity未知，不授PIT、ML-fit或交易資格。

若envelope核對成功但child/config/method readiness拒絕，仍展示保存資料日與記錄中的各批producer/capture結果，明示母體資格未確認；不偽造readiness或把producer發布擦掉。envelope本身拒絕則清除上一次分母／表格，詳細理由折疊；錯誤不代表producer未發布。

## 背景工作與下一步

使用既有TaskWorker。明示QueuedConnection＋Qt Slots在GUI thread接結果；generation與sender身份擋晚到callback。重複點擊不追加worker，來源核對在背景；取消／返回／關窗合作式cancel，不terminate、不阻塞GUI，等待native thread結束才恢復重讀／改選。返回不刪收據；晚到成功或error不能改取消後畫面。

重讀／重試核對只讀同一保存包。incomplete的下一步先檢查各批結果；原隔離CLI沿同來源/母體/方法/固定as_of重試，revision/methodchanged需新明示保存，partial store需新隔離capture root且保留舊件。視窗不提供未經批准的正式producer或刪除捷徑。

## 驗證收據

- 新收據UI11案例＋既有每日研究頁4案例＝15 passed，final 8.01s。實際隔離17 included+2 excluded/兩批receipt→背景reader→UI；新Python程序readback、只讀bytes不變、complete/incomplete、child/config readiness拒絕保留producer、bad envelope後清舊/重試、重複點擊、合作cancel/返回/close/stale success/error、picker取消、單視窗入口均覆蓋。
- 初次測試helper使用未安裝qtbot，改為專案QApplication方式；QTest忙等曾飢餓背景Python讀取，改processEvents＋短sleep讓出GIL。同步readback本機量測0.063s；這些是測試driver修正，未把timeout當產品SLA，也未放寬來源守衛。最終無fail／skip，只有pytest cache sandbox警告。
- Workbench85 passed；validator25 passed/0failed/4既有環境skip；full roots mypy806 sources通過，最後slot/sender局部修正targeted2通過；compile3、quant precision/look-ahead、diffcheck通過。
- output/qa/ux20_parent_capture_20261006/ui_focused.xml；parent_receipt_controlled.png已實際看圖，offscreen fixture且測試明示載入中文字型，不是Native／自然資料／真人驗收。未操作使用者視窗，未push／正式DB/EvidenceDB／ML重訓／Task／migration／刪除清理。

## 固定時鐘／漏日／修訂／容量治理：現有接線與最小下一包

| 工程 | 現有接線點 | 仍缺什麼 |
|---|---|---|
| 固定時鐘/cadence | parent produce_parent_rule_samples的decision_cutoff/as_of、CLI capture-as-of；既有child時計驗證 | 每日觀測時刻與時區policy／owner，不能以observed-now取代固定決策時刻 |
| 漏日 | explicit parent decision_date、exact parent receipt/readiness；來源可得時間與calendar仍unknown | 明示預期觀測日與實際收據的缺日報表；未知calendar不宣稱交易日漏失 |
| 同日修訂接受 | query-only transaction＋main/WAL stat/schema pin；_plan和parent identity；fixed as_of去重保留首次包 | 同日新revision與前包關係、接受／拒絕理由、不可覆寫的接受記錄 |
| 容量/留存 | shared writer200GiB reserve、256KiB/包、8MiB/128包；parent各root64MiB/4096 entries與預留budget | 正式data-owner位置／配額／留存／busy/partial處置與部署決策；不自動刪除 |

下一個最小閉合包建議先做**純固定觀測日接受policy＋隔離CLI接線**：明示timezone/每日cutoff/預期觀測日/母體方法版本，輸出待捕捉、已有同pin、同日revision需新包、缺觀測日／calendar未知等狀態；沿既有parent receipt與plan hash，不新增producer/DB/排程框架。隔離fixture驗時區與future拒絕、漏日不補資料、fixed as_of duplicate、同日revision保舊新identity、新程序只讀接受記錄及容量拒絕保留證據。部署／官方calendar／自然outcome另需後續，不在本批執行。

## 原計畫精確狀態與文件覆蓋

9階段：done1（0）；partial7（1/2/3/4/5/6/8）；pending1（7）。24UX：done2（01/02）；partial19（03/04/05/06/07/08/09/10/11/12/13/14/15/16/17/18/19/20/24）；pending3（21/22/23）。多批parent及saved receipt瀏覽有限工程完成，UX20整體未改done。UX21只開始獨立lane，未主線接受，不能提前調partial。

Must同步Manual、Features、Guide、Snapshot、Architecture、Index、Navigation、QA及唯一原計畫；產品方向／6M／長期版號未改。回滾：確認沒有後續依賴後git revert本批commit，保存receipt/fixture不刪除。UTC07:00安全暫停安排不變，由父層安排午夜review。

## 2026-10-11 後續收據核對

原文「UX21只開始獨立 lane，未主線接受」描述的是本收據時間點。後續 `UX21_FORWARD_OUTCOME_20261006.md` 記錄計算器、saved-package reader 與唯讀結果畫面已在 dev 接線；`UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md` 再記錄明示 benchmark source／store／CLI／畫面切片。UX21 因此已有後續整合收據，整項仍為 partial；正式 calendar／custody、自然成熟與正式部署等缺口未由工程收據解除。

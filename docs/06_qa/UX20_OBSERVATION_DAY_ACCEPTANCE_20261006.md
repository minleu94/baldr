# UX20 固定觀測日接受 policy 與隔離 CLI（2026-10-06）

基底71369c9f1fc0de49c5515b367534860c35852894。本批完成固定觀測日接受、缺日報表、同日revision保留與冪等重試的限定工程；Stage5／UX20保持partial。UX21三檔ownership保留，未碰其lane／未提前整合。

## 既有邊界與接受語意

新增rule_research_observation_acceptance只接受既有parent收據，沿BoundedRuleResearchParentWriter→原read_saved_parent_rule_sample_readiness→child capture資料日。接受記錄writer繼承同一BoundedRuleResearchCaptureWriter，只替換decoder/receipt；沒有第二套producer、DB、calendar或排程框架。

policy schema為rule-research-observation-policy.v1，明示policy_id/version、timezone=Asia/Taipei（沿parent既有時區）、每日decision_cutoff_time、observation_start_time/end_time、1–31個sorted unique expected_observation_dates、絕對universe_template_source及research_only=true。時間需HH:MM:SS且cutoff≤start≤end，窗口不跨日；expected dates是明示觀測日，不代表官方交易日。模板沿既有具名parent schema，日期依每個parent核對，其餘全母體成員／排除／版本須一致；來源bytes/hash與方法hash一起綁policy身份。

候選必須沿exact parent receipt、原snapshot/capture roots、母體配置、方法及revision pin核驗；decision date在expected dates中，cutoff精確等於當日配置時刻，原as_of落於當日窗口。parent實際capture observed_at≤接受記錄observed_at≤目前時刻；不能把接受時鐘回填到parent捕捉之前。不重寫as_of、不挑latest、不開市場DB。

測試發現既有parent complete只保證控制組／保存包完整，缺當日資料時仍可保存較早資料日的研究觀測。本包保留該語意，另核每股非excluded child row的data_as_of，缺／未知／較早日列missing_target_data_members與insufficient_or_stale；parent或目標日未完整時只存recorded_incomplete_observation，不能填當日完成。未知MA方法、暖機與來源可得性仍未知，不推成負樣本、正式selected或交易資格。

只有完整parent/source且無缺目標日成員才accepted_research_observation；這只是研究觀測接受，不是PIT／natural／formal／training資格。source stat/schema/WAL pin不是raw-content custody或官方revision承諾。

## 日覆蓋、冪等及失敗

日報明示evaluated_at，不能晚於現在。截止窗口未到為not_due，窗口內缺合格包為awaiting_complete_observation，窗口結束後仍缺完整包為missing_complete_observation。只把parent實際捕捉不晚於evaluated_at的收據列入覆蓋；這是目前保存證據的回顧投影，不授歷史可得性。未知日曆不把缺觀測日稱交易日漏失。

相同policy與exact parent pin冪等，沿用首次接受receipt；不同source_binding_sha256或新parent/as_of保留新包。同日多pin列observed_multiple_revision_pins，無winner/latest自動接受／覆寫。不同policy bytes／方法／模板pin的舊記錄另計other_policy_record_count，不冒充當前policy覆蓋。

重讀逐筆再次核parent及child，source/config/hash失效便saved_verified=false且不計accepted；catalog開始／結束pin不一致或busy/partial拒絕報表。寫入成功但日報拒絕時保留acceptance_saved=true、實際receipt與day_readiness_status=rejected；CLI不能說未寫任何內容。accept途中exception以acceptance_saved=unknown告知核對目錄，保留證據。容量拒絕無partial時可原root重試；原子寫中斷保留partial，同root fail closed，明示fresh隔離root重試，不刪原件。

維持200GiB reserve、256KiB/包、8MiB/128包、隔離output/qa或Temp與links/hardlinks守衛；不允許接受root重疊producer/parent來源、或包含policy/母體來源檔。不放寬容量，不自動清理。既有lstat/fstat與rename邊界仍不宣稱完整敵對Win32 no-follow／crash durability。

## CLI 與驗證

scripts/accept_rule_research_observation.py要求policy-config、acceptance-root、含時區evaluated-at；明示parent-receipt時預設preview，不建目錄／lock，只有--accept寫接受或未完整記錄；省略parent-receipt只讀日報，不開DB。退出0只表示操作完成，不保證所有預期日齊全；應讀missing_observation_dates及各日狀態。候選未完整或day readiness拒絕返回2。

23個不同案例passed（22案例23.96s＋追加future/not-due案例1pass），無skip：實際隔離query-only producer→parent→接受capture/receipt→新Python程序日報、byte只讀、preview無寫／明示accept、相同輸入duplicate、同日兩revision保舊、缺目標資料日不借前日、錯日/cutoff/window/母體/時區、duplicate/32日拒絕、capacity retry、捕捉失敗後same-as_of重試、atomic partial/freshroot、tamper/重hash假資格、later parent／future及早於parent接受clock拒絕、catalog race、別policy不混算、報表失敗保留已寫receipt均驗證。

targeted mypy2、compile3、quant precision/look-ahead、diffcheck通過。UI未改，不重跑前批Workbench/validator/fullmypy；前批UI gate仍85／25+4skip／806sources，本包不重複算入測試數。只有pytest cache sandbox警告。raw XML與controlled readback在ignored output/qa/ux20_parent_capture_20261006；實際當日synthetic fixture的午夜cutoff只供契約測試，不是市場資料已在午夜可得的證明。未正式DB/Task/migration/ML重訓/Native/push/永久刪除。

## 真正部署仍缺的工程與使用者決策

| 尚缺工程（不能稱等自然） | 部署前需使用者決策 |
|---|---|
| 沿既有producer CLI把policy日期/cutoff、保存as_of與parent receipt→accept串成一次有界daily owner；目前仍明示兩步，沒有正式排程 | 每日截止與觀測窗口、expected dates來源、owner/執行帳號 |
| dry-run排程adapter、合作cancel、busy/失敗/錯revision的有限retry與退出碼/JSON監控；漏日報表通知路由 | cadence、retry次數/退避、通知／人工覆核流程；WindowsTask正式啟用另批准 |
| 正式落點／segment roots／配額留存與partial/capacity-stop處置、版本配置保存／新程序恢復；本包不自動rotate/delete | storage落點、可用容量與quota、保留期限／owner，任何永久清理另批准 |
| 官方calendar接既有來源驗證、raw來源可得時間/custody與revision接受治理；目前明示dates＋stat pins | 認可的官方來源/日曆與修訂接受規則；未知維持未知 |
| UX21純Outcome契約主線接受後再接saved來源與consumer；接受policy瀏覽／正式日報consumer尚未加UI | 後續派工與驗收，不因自然樣本未成熟拖延工程 |

下一個最小工程包當時建議隔離 daily owner dry-run／execute-isolated adapter，重用本 policy＋既有 producer/parent/accept API，用明示目標日串兩步與 retry，不選 latest；synthetic 新程序回復、busy/源缺日/partial/capacity 停止與已發布但 accept 失敗收據驗證，再由父層決定正式 Task。後續的 bounded daily-owner 實作與隔離全鏈見[UX20 隔離 daily owner QA](UX20_DAILY_OWNER_ISOLATED_20261006.md)；該收據仍將正式部署列為未完成。官方證據、逐日自然收據、後續交易日與 outcome 準確度是另一類證據依賴。

## 計畫、文件與回滾

9階段done1（0）／partial7（1/2/3/4/5/6/8）／pending1（7）；24UXdone2（01/02）／partial19（03/04/05/06/07/08/09/10/11/12/13/14/15/16/17/18/19/20/24）／pending3（21/22/23）。本有限終點完成，UX20仍partial，UX21獨立lane尚未主線接受。

Must同步QA、Manual＋Supplements、Snapshot、Architecture、Features、Guide、Index、Navigation及唯一原計畫；方向／6M／版號未改。git revert本批commit回復程式／文件，保留原parent與接受收據/partial，無資料搬移或刪除。UTC 07:00 安全暫停是本文件記錄的 2026-10-06 交接安排；本頁不確認它於後續日期仍有效，後續 review 依 parent 目前安排判定。

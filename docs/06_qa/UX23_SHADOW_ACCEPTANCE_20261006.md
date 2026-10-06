# UX23 隔離 shadow 最小工程狀態（2026-10-06）

承接已接受 `59a09f9b787817ba65f62e2c67265e7b7a103e58`。唯一 Luna Max 實作新 leaf／focused cases；root review、CLI、exact 收據重讀、邊界及文件整合。沒有新 shadow 平台、UI、真模型執行／訓練或正式控制。

## 有限工程契約

既有公平比較接 exact parent／outcome 與明示 label／split／comparison／feature-prediction bundle；新 consumer 只附加既有 ModelLifecycleEvent 匯出與轉移規則、candidate metadata pins，以及「工程可執行／資料或效果未合格／未啟用」三軸。缺 candidate、版本不相容、比較失敗或 lifecycle 缺件保留規則路徑；disabled／superseded／rollback_requested／review_required 停止隔離投影。有效空事件只能驗研究工程，不能宣稱已啟用。

既有 registry 的查詢也以 `mode=rw` 開啟 DB，所以本包不呼叫 registry／monitoring service；匯出 DTO 是聲明，沒有驗真 lifecycle custody 或訓練 lineage。明示 stop reason 只形成隔離研究停止收據，不寫 disabled 事件、不切換實際 overlay；沒有正式推薦、排程、部署或自動選模型。

薄 capture 沿 BoundedRuleResearchCaptureWriter 保存 canonical capture＋receipt，同目錄 atomic rename、前後重新開啟來源與身份重驗、duplicate 保留首次 observed_at、exact 指定身份 read。保留 256KiB／128筆／8MiB／200GiB 安全線，不增加 runtime 繞過。取消不發布，殘件保留且下次 fail closed；不清理資料或覆寫舊收據。

## 未來資料與效果邊界

沿公平比較 T-1 feature／availability、原 prediction 來源與 label split 契約，不對評估資料 fit 或標準化。observed_at 是當下 UTC，不回填歷史預測；同一 identity 排除觀測時鐘只為 idempotence，不授自然預測資格。完整母體、方法、selected target 與 common cohort 分母沿原比較固定，matched／notmatched 不是交易 selected。

原 sealed fixture 為 18 labels／12 數值／6 缺值、18 availability unknown、0 temporal training candidates；本包不更改未知與 0 合格。資料／效果軸永遠未合格，所有 training／PIT／formal／natural／execution／shadow enabled false、alpha 0、selection unknown。保留研究計分不等於模型勝出；endpoint-only 不評估期間 MFE／最大不利 excursion／停牌。

## 驗證紀錄

最終 47 個不同案例通過，0 失敗／0 略過（新 leaf／CLI／scoped boundary 與既有 fair comparison 回歸44，加 adapter執行例外／容量拒絕／殘件保留3）。完整 mypy：`Success: no issues found in 818 source files`；CLI／guard targeted mypy、7 檔 py_compile、量化精度／未來函數檢查通過。程式 hash 在整包最終檢查前後一致；後補3個安全案例只新增測試，另存XML／hash／compile，未改runtime或擴大gate。無 UI 改動，不重跑 Native／已接受效能 gate。

actual 重用 UX22 原 sealed fixtures：受控 baseline／candidate predictor 再執行各 3 次，artifact source hash 與原輸出相同，不改 prediction DTO 或聲稱新增歷史 forecast。完整母體 3／included 2、兩方法 6 行、selected target 3、common 2；18 labels／12 值／6 缺值、18 unknown／0 temporal training candidates。相同 exact 輸入→隔離發布→duplicate→新程序重讀、明示 stop 收據新程序重讀、不同 artifact version／缺 candidate 安全回退均驗。

工程收據 `c930c41580542d74ac5ec11012f4deaf0e89651e4c5d6eaef2c81ba31d28ade9`；停止收據 `2fc045d99678d3aad8de32bbdac5c0d5f204155e13b7371e112d2f07ab3e2260`。兩者始終未啟用，read 不調用 live fair comparison；原 sealed JSON、來源 DB、policy 與 prediction bundle before／after SHA 相同。保存 fixture 的 free-space probe 明示受控 10^12 bytes，只驗 writer 分支，runtime 200GiB 安全線與拒絕路徑沒有繞過選項。

ML boundary 從 immutable base59a09 guard／source tree 核對：既有八條相同、本包新增 0；新 consumer 僅明列 ModelLifecycleEvent／既有轉移常數，registry／monitoring writer import 拒絕。不能宣稱全 repo boundary 通過。其他 owner 三檔相對90d16858完全不變。

raw（不 stage）保留在 `output/qa/ux23_shadow_acceptance_20261006/validation_receipt.json`、`fixture_actual_readback.json`、`boundary_readback.json`、`preview_report.json`、`stopped_report.json`、focused XML／各檢查 logs 與隔離 store。原計畫前 231416 bytes（SHA `2aba923e94eabdc1760a78e5bcea31131192edafa7d6dcf5f9e7f62898927e0b`）原文完整保留，只追加本包進度。

早期 CLI 子程序的 Windows cp1252 中文輸出失敗已改為明示 UTF-8；agent 初版回報保留於 `agent_observations.md`，未重建假原始 log。修正後 agent24及root47案例通過；root關閉pytest cache plugin，不需寫入既有唯讀cache。沒有把初版失敗或尚未整合版當成最後通過證據。

## 進度與剩餘缺口

UX23 pending→partial，Stage7 仍 partial，沒有新增 done。原計畫 9stage=1done/8partial/0pending、24UX=2done/22partial/0pending；原文 bytes 保留，只追加本包真實結果。

剩餘工程：自然預測的當日封存、成熟讀回、漂移監控、具名採用／回退條件、真模型效果與 qualified provenance、正式啟用／控制整合。剩餘外證：官方 actual session／時點與 custody、自然成熟期間、真人驗收；目前隔離受控預測與匯出 DTO 無法代替。全 repo 既有八條 ML boundary 違例保留且另報，不自行修其他 owner。

操作入口、參數、判讀、保存／exact 重讀／停止及排錯已同步 [Manual](../07_guides/APPLICATION_MANUAL.md)。完成本地 commit／收據後停工，06:40 UTC 未完成則保留 dirty 與證據，不強行 commit；07:00 UTC 截止與午夜 review 約束有效。無 push、正式 Task／DB／personal migration、清理、前景 Native 或已接受效能 gate 重開。

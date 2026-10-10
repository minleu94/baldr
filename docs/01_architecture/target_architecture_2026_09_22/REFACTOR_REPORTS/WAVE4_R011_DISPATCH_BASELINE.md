> **歷史派工基線（勿依此重新派工）**：owner、HEAD、檔案雜湊、路徑與狀態只代表該次交接快照，不代表目前負責人或執行授權。現況與優先順序看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 及最新具名 QA；目標設計以 [FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md) 為準。

# Wave 4 R011 中央 execution 派工基線

CURRENT_STATUS: R011_IN_PROGRESS

`WAVE3_CHECKPOINT.md` 為 PASS，故依 `REFACTOR_EXECUTION_ORDER.md` 只釋出 R011。派工時 main HEAD 為 `5e2d2efcfdc91c5e29810eb823b1c582199a44cc`，`app_module/recommendation_service.py` clean，原始 bytes SHA-256 `7578D7EE6E1EF6128E895092E44C0416CB98B3E00558C880B551445F30B756D3`。R008 app contract SHA `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`、R009 codec SHA `A1BC97DE557C58FCAA039D06DAE909123A3E405B5E2DD7776B94F9A80ED653BE`、R010 ML leaf SHA `E39EE8ACB37CEDBCABE5276FE85703B2FDBEB98C2DE9702B23184934D6513D03`。

R011 採主工作目錄嚴格串行，由單一 Luna Max 擁有 `recommendation_service.py`、新增 `app_module/recommendation/execute.py`、R011 專用 tests 與 implementation report。沒有其他 R-task 可修改中央檔案。R011 必須保留舊 list API、result/receipt identity、numerical/ML 時序，並用 invocation-scoped capture 組成完整 execution；不得開始 writer、save caller、provider/evaluator 或 consumer migration。另有唯讀 Luna parity 稽核供實作者與 SOL 參考，不具實作 ownership。

main 已存在的 Wave 0–3 與無關未提交檔保持原樣；不 stage、commit、push、reset 或 clean。若另一獨立任務推進 main HEAD，R011 整合驗收須重新核對中央檔、相依 SHA 與實際 diff。R012 及所有後續 wave 在 R011 獨立 review、SOL 驗收與 Wave 4 checkpoint PASS 前保持 blocked。

派工後另一獨立模型修復任務將 main HEAD 推進至 `eaf3ad24ffee0f289bdf876fb9033845b1bb2632`。SOL 核對 `5e2d2efc..eaf3ad24` 的 changed paths 只在 research ML/current capture、對應 script/test/QA/Manual，不含 R011 中央 service、R008–R010 契約／codec／DTO seam 或本次 task 專用 tests；service 原始 SHA 仍為 `7578D7EE6E1EF6128E895092E44C0416CB98B3E00558C880B551445F30B756D3`。R011 worker 保持原派工 scope，整合時仍以最新 main 重新查證。

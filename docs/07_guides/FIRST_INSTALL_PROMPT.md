# baldr 首次安裝／完整移機 Prompt

在新電腦將以下內容交給 Codex。第一次使用選 fresh；復原原有環境選 owner-migration。依執行範圍持續完成環境、設定與排程，而 bootstrap-plan 本身維持唯讀核對。

## 可直接複製

```text
請依AGENTS.md、README與docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md，完成baldr首次安裝或完整移機。

模式：fresh / owner-migration
執行範圍：plan-only / configure / restore-and-enable
新機Repository：<絕對路徑>
GUI Runtime：source / portable-gui
新機Windows時區：<識別名稱，例如Pacific Standard Time>
DATA_ROOT：<自己的市場根>
OUTPUT_ROOT：<自己的報告及狀態根>
舊機清冊（移機必填）：<baldr-machine-inventory.v1檔案絕對路徑與SHA-256>
核准復原的備份與資產：<來源、目的、owner、完整性／lineage資料，不含秘密>
新機既存排程觀測：<Windows及Codex清冊；缺觀測填unknown>
舊機移交writer已停止：true / false
適用與明確排除排程：<原狀態、時區、wrapper、trigger、帳戶、理由>
排程source runtime已核對：true / false

授權界線：plan-only只產生可審查計畫；configure允許在上述新機目的地建立runtime與設定、從核准且一致備份復原資產、建立停用排程；restore-and-enable另允許啟用原本已啟用且前提已成立的任務，原停用的保持停用。範圍未選或清冊未明時，先完成獨立盤點，把確認留在具體變更前一次。

先唯讀核既存狀態、來源身份、roots、模型lineage與新舊排程差異。依baldr-bootstrap.v1範例／schema及scripts/document_control.py bootstrap-plan檢查；不要以plan無error當runtime、來源資格或自然run通過。使用init-task建立獨立task ID，不碰其他任務singleton。

依既有具體授權，持續完成新venv／依賴或可攜整包、兩個roots與私人設定、核准資產／模型復原、GUI啟動及資料狀態檢查。不得修改或重建原始資料、不將活躍SQLite主檔複製當完整備份，不搬credentials、DPAPI私鑰、Codex auth／session DB。需要使用者登入或機器authority重建時，明示該步，繼續其餘獨立工作。

排程從現行稽核器清冊及專用註冊路徑逐項復原；aggregate不涵蓋全部，不可只執行aggregate便結案。保存before定義，核principal、argv、cwd、trigger／DST／Taipei cutoff、timeout／power／retry、上游及原enabled／通知／模型。新舊writer不可雙寫。configure保持停用；restore-and-enable只啟用前提成立且原已啟用的任務，重新讀回真正設定和NextRun。

自然驗收等待真時鐘觸發，再核同次terminal、run/date/hash與consumer。材料未齊、權限／平台限制或尚未到觀測窗口，保留pending與安全接手點，不用人工trigger、fixture、舊latest或放寬gate替代。

交付已完成安裝／設定、逐Task before/after及讀回、資產身份、自然驗收、未完成原因與回滾。已授權清冊範圍內不逐Task重問；只有scope外變更或證據不能裁決的高風險差異才確認。記錄真命令／結果，設定完成、自然運行與產品Gate分開。
```

## 清冊與工具

公開[範例](../../examples/machine_bootstrap_manifest.example.json)及[JSON Schema](../../examples/machine_bootstrap_manifest.schema.json)使用 baldr-bootstrap.v1。私人值放ignored output並另作安全備份。

| 欄位 | 要求 |
|---|---|
| mode／runtime／repo_root／timezone | 明示fresh或owner-migration、GUI及實際新機位置／時區 |
| roots | DATA_ROOT及OUTPUT_ROOT分別指定；不猜他人私人根 |
| source_inventory | owner-migration的正規化舊清冊path＋SHA；保持原匯出／觀測來源 |
| assets | id、path、required及可選SHA；模型需完整lineage，不只權重 |
| schedules／observed_schedules | 分開記desired與observed；id/platform/desired_enabled/timezone/trigger及平台所需wrapper／argv／cwd／principal／model／通知 |
| excluded_schedules | 明確ID、platform、reason；不默默漏Windows或Codex任務 |
| old_machine_writer_stopped | 移機啟用前真證據，不能只填true |
| source_scheduler_runtime_verified | 可攜GUI不能替代source排程runtime核對 |

```powershell
.\.venv\Scripts\python.exe scripts\document_control.py bootstrap-plan --manifest output\tasks\<task_id>\bootstrap.json
```

bootstrap-plan只讀清冊、來源常數及明示資產存在／hash，計畫輸出到stdout；不安装、搬資料、註冊、啟用、觸發或建立task record。真正設定依上方授權與[詳細Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)，缺件則記錄可接續狀態。

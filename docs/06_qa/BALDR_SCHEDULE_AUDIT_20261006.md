# 2026-10-06 全排程模型盤點與 Windows 唯讀稽核

本輪使用者授權範圍是所有本機使用者 Codex 排程的 Astra→`gpt-6.1-sol`、5.6 Luna→`gpt-6-luna`，保留 effort／fast／時間／通知／停用狀態；Windows 僅檢查。沒有啟動或改 Windows Task，沒有改 target thread／running turn，沒有執行資料更新、fit、promotion、資料遷移或 exe 切換。

開場已核本 repo dev `7b9b300753280ddd3cdf5033a449c528cdb5adec`、main `ba164d500cd73c98da84fa6442dd7c0f4f5dfac1`；未建立 branch／worktree。exe 啟動修復由另一 owner 持有，本輪不修改其 launcher、spec、Manual、Snapshot、索引或其他 dirty 檔。

## Codex 實際結果

本機合法 automation 目錄共 **49** 份 TOML，跨 technical_analysis 與 Risk Lab，不只本專案；**46 PAUSED／3 ACTIVE**。cron 43 個的 execution model 是 **40 個 gpt-5.6-terra、3 個 gpt-5.6-sol**，不符合本輪指定替換，因此均不動。6 個 heartbeat 沒有獨立 model／effort 欄位，另外只讀其指定 target 的模型 metadata，未讀私聊內容或 session 檔案。

| heartbeat | 狀態 | target metadata model／effort | 指定目標與本輪結果 |
|---|---|---|---|
| 9-18-tpex | PAUSED | gpt-6-astra／medium | execution 替換未完成；未來子代理 prompt 的 5.6 Luna/max→6 Luna/max 已完成 |
| paper | ACTIVE | gpt-6-astra／medium | 應換 gpt-6.1-sol／medium；未完成 |
| risk-lab-luna | PAUSED | gpt-6-astra／high | 應換 gpt-6.1-sol／high；未完成 |
| moomoo-200-risk-lab | ACTIVE | gpt-5.6-luna／max | 應換 gpt-6-luna／max；未完成 |
| baldr-scheduled-evidence-morning-report | ACTIVE | gpt-6-luna／max | 已是目標世代，不動 |
| wp5 | PAUSED | gpt-6.1-sol／high | 已是目標，不動 |

前三項 Astra heartbeat 中，9-18-tpex 與 paper 共用同一 target；四個待換排程涉及三個 target。metadata 說明當前保存模型，未證明 server 下一輪實際 execution model。

實際 **execution model 修改 0 個、49 個執行設定未改；prompt 最小校正 1 個、48 個 TOML bytes 完全相同**。校正是明示未來執行指令，非歷史引述：`所有查找、下載、程式修改、測試與補入均交由 gpt-5.6-luna、reasoning_effort=max 的 subagent` 的唯一 model token 改為 `gpt-6-luna`。保留 PAUSED、target、原 prompt 其他 bytes、trigger、timestamps 與全部其他欄位；沒有用 prompt 冒充 execution model 已遷移。

本機 models_cache catalog 確认精確 slugs `gpt-6.1-sol`／`gpt-6-luna`，Sol 支援 low／medium／high／xhigh／max／ultra，Luna 支援 low／medium／high／xhigh／max；待換項原 effort 均支援。Catalog 是本機觀測，不是其他帳戶可用性保證。

**阻塞：** purpose-built automation API view 回覆 `Automations are only supported for local threads.`；本 delegated 執行環境無本機 automation API。可見 heartbeat schema 沒有 model／effort 欄位，沒有合法方法在保持 target／running turn 不變的條件下於此環境完成這四個 execution 替換。不直接加未證實生效的 TOML model、不修改 threads DB、不喚醒任務。需由具本機 supported 設定入口的 owner 接手，先確認是僅未來排程 override，還是 target chat 模型變更；後者不得打斷 running turn。此未完成事項不可標成「全排程已更新」。

父層另外回報 cloud 使用者排程沒有 enabled user task、connector 未提供 model 欄；停用提醒保持停用。本輪未自行查 cloud 帳戶，因此 cloud 結果是父層證據，不能與本機 49 筆混加或假稱跨層去重已完成。

## Windows 設定吻合與執行結果

查詢時間 `2026-10-06T14:17:00-07:00`，主機 `Pacific Standard Time`／DST。全部目錄 **223** 項；按名稱與 action／arguments／WorkingDirectory 的專案引用篩選，相關 **21** 項。Microsoft／第三方系統工作只看目錄與匹配 metadata，不修改。初次 restricted 查詢 Access denied，後以獲准 require_escalated 唯讀查詢完成，沒有改權限或 credential。

- 21 項均 Enabled／Ready、action 是 cmd.exe→目前 repo canonical wrapper，WorkingDirectory 都是目前 repo；沒有舊 temp／worktree action。21 wrapper 與引用的 repo 腳本存在，venv 存在。Paper EOD wrapper 使用另一種自行 cd 的寫法，同樣回到 repo。
- principal 均原互動使用者／Interactive／Limited；具體帳號只保存在私有清冊。無人登入時不能假設會執行。全部 IgnoreNew、StartWhenAvailable=false、RestartCount=0、WakeToRun=false、Network gate=false；timeout 是 16 個 PT72H、3 個 PT1H、1 個 PT2H、1 個 PT5H，逐項以本輪 XML／清冊核對。
- 個人 calibration-learning 與 BankTaiwan 不因電池停止；其餘 19 項為「電池不啟動、轉電池停止」。因此新筆電的漏跑政策需重新確認，不能把 Ready 當保證自然執行。
- calibration-learning 下一原 run **2026-10-07 12:45 UTC／05:45 PDT**，本輪未手動 trigger、改時刻、換 interpreter 或切 exe，保留自然觀測。
- Paper／ML forward XML 的當前 StartBoundary 帶 `-07:00`（當次美西 17:25）；其他 task 通常無 offset、美西本地鐘點。搬機與 DST 要保留各自語義，不能全部改當地相同時間。
- 白名單 process／User／Machine roots／private／model 環境未見明示值；這不是 Task 登入當時 env 的完整回溯。wrapper defaults 與外部可攜 JSON 仍是不同設定入口。現有市場、Paper DB／ledger、release bundle、日期 config root、thesis policy／PIT source config 與 H20 activation 路徑均存在；未讀 DB／重訓或做全模型 bytes 驗證。H20 descriptor 原 enabled=true、revision=1 未變。
- 後驗 21 份 XML **21/21 完全相同**。最近 Scheduler LastResult：**12 個 0、2 個 1、7 個 2**，不能宣稱全部健康。
- ML forward 原 release_manifest.json 的實際 SHA-256 與 wrapper pin `c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea` 完全相符；只驗 manifest file bytes，不代表整個 model bundle 或 promotion 資格已驗。

每 Task 用途、入口、依賴、驗收輸出與搬機契約見 [運維指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。最近 receipt 判讀如下；這是原件唯讀，不改 gate 或回授資格。

| 狀態群組 | 最新已讀證據與限制 | 最小可逆處理建議（未執行） |
|---|---|---|
| Quick／freshness／snapshot／evidence | Quick 10/6 04:20 run passed_with_warnings，freshness degraded，snapshot passed，dry-run degraded | 保留 warnings、來源日期與子收據，不因 exit 0 消警告；按原來源 cadence 驗下一同次 receipt |
| decision／outcome | decision receipt degraded，Task result1；outcome blocked／outcome_price_missing，Task result2 | 核同一 decision／due date可見價格與terminal；不要以新來源重寫原 frozen outcome |
| raw PIT／promotion／maintainer | raw blocked_source_revision，promotion evidence corporate-action custody stale，authority skipped_evidence_unavailable，copilot passed_rule_only，maintainer skipped_locked | source revision／manifest custody各自列有界修復提案；維持原資格，不解鎖強跑或產生授權 |
| PIT／formal／forward | PIT denominator／DNS缺件；sidecar blocked，formal candidate_only，forward blocked_child_exit | 先核 official denominator、same-date raw、calendar／Paper／manifest pin與子程序terminal；只使用既有原bounded retry，重建需另授權 |
| learning／BankTaiwan | 10/6 learning failed（historical PIT source revision guard），BankTaiwan failed_dependency | 保留原失敗與自然run窗口；上游修復由來源／模型owner另review，不手動 fit或重跑 |
| Paper | Paper valuation最新10/6 passed；EOD latest pointer hash 正確，10/6 gate ready_with_warnings，但 Task result2 | 不把9/25舊 gate failure當10/6結果；gate ready不是adapter成功，需追同次retry／adapter terminal，仍列未完成驗收 |
| weekly | latest locator→10/5 UTC terminal hash matches，core verified／pending_human_review，monthly captured_research、quarterly completed_with_review_items | 不引用9/20舊report當最新；子terminal摘要不是formal接受，維持human_review與formal_pit_eligible=false |

設定沒有已證實必須立即更換的舊路徑；運行來源／資格阻塞與既有排程策略需要 owner 判斷。最小搬機補件是：新帳戶／登入模式、missed-start／battery／retry政策逐項決定，明示必要環境、固定來源契約與模型 assets，保持專用 forward／Paper註冊，不盲目aggregate RegisterAll。19 個 wrapper 有全域 Python fallback 的靜態路徑，新機先驗 venv，若要移除 fallback另提受控修補，不在本輪動穩定入口。

## 私有收據、回滾與交接

本機 ignored `output/qa/baldr_schedule_migration_20261006/` 包含：

- `codex_inventory_before.json`／`codex_inventory_after.json`：全部49份含原prompt、status、target、cwd、SHA。
- `model_catalog.json`、`heartbeat_target_metadata.json`：只讀精確模型能力與六個target選定metadata；沒有sessions／auth內容。
- `9-18-tpex.before.toml`／`expected-after.toml`／`readback.toml`、`prompt.diff`、`migration_result.json`：唯一prompt更正、備份、精確bytes後驗。
- `windows_directory.json`、`windows_details.json`、21份原XML、`windows_settings_readback.json`：全部目錄／相關Task完整設定／LastResult／NextRun與設定不變證據。
- `wrapper_audit.json`、選定環境清冊、`required_paths.json`、`producer_receipt_readbacks.json`、`current_pointer_readbacks.json`：明示依賴、入口與收據hash。舊9/25／9/20檔案只作歷史，不混為最新。
- `LOCAL_PRIVATE_INVENTORY.md`、`verification.json`：完整本機清單、前後欄位與48份不變檢查。ignored 清冊應由使用者安全另備份，不隨Git搬移。

回滾唯一prompt更正前，先核目前 TOML SHA 是本輪 after pin `cc9b9f9316666d05590854bb5affd5b941aba65708f52adc01fc909ca826f0c2`，再使用supported入口或原子恢復本輪備份；原 before SHA `41f2e216c32fba37ce4bf0e1d48a3a9adf8b2362999ddb4a830f2e5a8ae43af6`。若設定已被他人更新，只撤回該model token，不整檔覆蓋。回退不喚醒PAUSED任務。Windows無本輪變更，不需回滾。

文檔Coverage：本輪獨立新增本報告與運維指南；原共享入口owner修exe期間未修改Manual／索引或stage。owner釋出窗口後，僅在Documentation Index新增本指南／稽核連結並於本機dev提交這三份文檔；Manual與guides index未改。Roadmap、architecture與產品資格不變，不新增全庫graph／fullgate，不提交私有清冊、不push或main merge。

## 後續 blocked 交接補充

2026-10-06T21:24:31.658980+00:00 再次只讀精確四份TOML與三個target模型metadata，狀態／模型仍與上表一致。四個heartbeat沒有獨立model／effort欄位，target metadata有保存模型；尚未驗scheduler完整繼承契約，不能把metadata當下一自然run模型證明。

目前工具catalog沒有「僅改既有target模型設定而不啟動turn」專用setter。send_message_to_thread的model override會送follow-up prompt，因此本輪沒有用它替代設定操作。父層另回報對停用Risk Lab target的cloud入口嘗試為CloudThreadNotFound，本機target不是該cloud task；不是成功模型替換。這是父層回報，非本輪新toolcall。

原使用者模型替換授權已充分。API回覆local-thread環境限制，不是owner／授權拒絕，也沒有實際model欄位驗證拒絕；公開heartbeat schema未明列model override，尾端unknown union不代表支援。重新詢問同一授權不能補工具能力。官方只有一般Scheduled模型選擇說明，未取得既有heartbeat專用model-only UI控制證據，不猜手動步驟。精確target映射、原錯誤、工具schema與最新readback只保存在ignored BLOCKED_HANDOFF.md等檔；execution模型仍0個完成、4個待換，停用狀態不恢復。

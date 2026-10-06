# B14 獨立 shadow control port 工程收據

日期：2026-10-06。主 owner：`01a11020-88c2-7506-acc3-d51ecb674032`。

## 固定範圍與交接

- Base：`670b4e8b04348eb0bb13b0966fa756b4b07bab40`。
- Branch：`lane/baldr-b14-shadow-control-20261006`。
- Worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b14-shadow-control`。
- 僅新增 `app_module/rule_research_shadow_control.py`、`app_module/rule_research_shadow_control_store.py`、`tests/test_baldr_b14_shadow_control.py` 及本文件。
- 沿原 plan、Astra B14 與 Sol 有界 review：UX23／Stage7 仍 partial；本收據只完成先行獨立 control port，不將整項 B14 或資格改成 done。
- Execution 為實作角色，Testing/QA 為驗證角色；本包 medium、僅 synthetic IO。中央持有 shared state、Manual、Snapshot、原 plan／架構權威與 UI union，不擴寫四檔以外的共享檔。
- 既有 shadow acceptance／CLI、ML monitoring／lifecycle／guard、ModelInput、shared DTO、main 全部唯讀。未引用 B13 mutable 檔，沒有重新建立 ModelInput／PredictionDTO。

## API 與核准邊界

`ShadowControlIdentity(model_id, model_revision)` 指向 exact 模型 revision；`RuleRoute(rule_id, rule_revision, artifact_sha256)` 指向 caller 指定的已核最後規則 artifact。沒有搜尋 latest／last-approved，也沒有閾值選擇。

`ControlSourcePin(role, source_id, content, custody_sha256)` 保留原始 bytes；每 pin ≤64 KiB、≤16 roles、總量≤256 KiB，roles 唯一，`last_rule` pin 必須等於 route artifact hash。bytes／pins 防禦複製。hash 只表示完整性，不能表示核准。

`ShadowControlCommand(command_id, action, identity, expected_revision, last_rule, issued_at, deadline, source_pins)` 為 frozen typed command；action 支援控制 `stop_restore_rule`，`resume` 明示拒絕。revision 必須是非負整數且拒 bool；時鐘必須 aware，UTC 正規化，期限必須晚於 issued_at。

`ControlApprovalProof(custody_id, command_sha256, source_pins_sha256, approved_at, expires_at)` 綁定 exact command／pins；`ControlApprovalVerifier.verify(command, proof)` 由 caller 注入，必須核對獨立持有的核准記錄。未注入 verifier、缺 proof、自算 hash／未知 custody、不符 command／source pins／clock 均拒絕。測試的 caller 核准清單與控制 receipts 分 root；這是 synthetic 工程核准 fixture，沒有正式 authority／資格效力。

verifier 必須逐欄核對完整 proof，包含兩個時間欄位；proof 的 `identity_sha256` 提供完整內容身份，不提供核准權。測試獨立記錄含此身份，篡改原過期時間以延長核准會拒絕。

`ControlPort.readback(identity)` 與 `stop_and_restore_rule(command, proof, context)` 是唯一控制邊界。port 必須 CAS 停 exact revision、切至明示 route、在原子提交前再核 deadline／cancel，並讀回 exact namespace／identity／revision／status／rule hash／command hash／source pins hash。

`ShadowControlService(port=None, verifier=None, clock=...)`；`apply(command, proof=None, execute=False, cancel=None)`：缺 port 為 unavailable；預覽不寫入；execute 非 bool 拒絕；完成必須同時通過 port 回傳與獨立 readback 核對。錯誤／假 stopped receipt 不回 completed。`production_action_allowed` 固定 false。

## 隔離保存與真正 dispatcher 控制

`SyntheticShadowControlPort.create(root=..., namespace=..., command=..., proof=..., verifier=..., context=...)` 只接受明示、尚不存在的絕對 root，父目錄須已存在；root 限於 OS temp 或該 worktree 的 output 子樹，namespace 限 `synthetic://<明示名稱>`。無預設路徑、不接 config、不碰正式／私人 DB。既存 root 用 constructor 讀回，不能用 create 覆蓋。

bootstrap revision 0 僅供 synthetic model callback 測試，保存 caller 已核 route／原 pins／proof；stop 原子追加 revision 1，status=`stopped_rule`。本包不提供模型 resume／重新啟用 transition。最多256 receipts、每 receipt≤1 MiB；實際允許的狀態鏈僅0→1。

每 receipt 保存原 command／proof／base64 原 bytes、canonical payload hash、前一原始 receipt hash。每次讀回重驗完整連續鏈與 caller custody，不因自有 hash 正確就接受。原 receipt 不覆寫；CAS duplicate／stale、錯模型、錯 route、未知欄位／檔、缺 revision、壞資料／links／hardlinks 均 fail closed。

synthetic port 還要求 `ControlStateCustody`：caller 在控制 root 外獨立持久保存 `current_revision(namespace, identity) -> (revision, command_sha256)`，以 `reserve_stop_revision(namespace, command, proof)` 原子 CAS 0→1。bootstrap 要求獨立 witness=(0,None)；停止發布前先單調保留(1,exact command hash)。讀回必須與 witness 完全相同，因此合法 tail 被截斷也不能回到模型。fresh-process fixture 將完整核准與 witness 保存至另一 caller 檔；reader 不更新該檔。

writer 使用 exclusive OS lock，先寫自有 staging 並 fsync，再核取消／deadline，以 exclusive hard-link publication 原子發布新 receipt，最後移除自有 staging link。已保存 receipt 最終單 link。crash 殘留 staging／多 link／lock 時拒讀或拒寫，不猜測恢復、不清理他人檔；需 caller 保留失敗目錄並另行診斷。建立 root 後若 bootstrap 失敗，可留下不可讀的隔離目錄，不將其當成功 store。

witness reservation 與 receipt publication 跨兩個 caller 資源，不宣稱跨資源 transaction：reservation 後 IO／取消／逾時失敗，保留單調 witness，讀回不符即拒全部 runners，不撤銷 witness、不恢復模型、不稱 completed。獨立 custody 的持久性／CAS 是 injected port 合約的一部分，不能以程式內可變計數器充當正式保存。

`dispatch(identity, request: bytes, model_runner=..., rule_runner=...)` 沿同一控制鎖：revision0 才呼 synthetic model callback；revision1 僅呼指定 route／已保存 rule artifact callback。讀回失敗完全不呼任何 runner。stop 與 inference 互斥；inflight 時 stop 回 unavailable，不產生等待後晚到的控制工作。這是 caller dispatcher 的實際 gate，與 registry append／lifecycle simulation 無關。

期限／取消為合作式 port 契約；service 無背景執行緒，合格 port 在提交點重核。publication 為線性化點：提交後才到達的取消／期限不冒充未執行，service 繼續取得 exact readback；已確認 stopped state 回 completed，讀回失配／不可讀不回 completed。任意外部 port 的提交時鐘／強制取消遵約性須由其 caller 驗證，此包沒有強制終止任意第三方 callback 的能力。

## 驗收證據與操作素材

正向 `test_actual_dispatch_stop_rule_and_fresh_process`：caller 已核隔離 rule bytes → revision0 呼模型 spy 一次 → service stop/CAS → revision1 呼指定 rule spy → fresh interpreter 注入原獨立 custody，模型 callback 設為 AssertionError，dispatcher 仍只走同 rule hash。原來源 rule／prediction bytes 與 mtime 不變；receipt0 bytes 不變。

負向覆蓋：預覽／缺 port、不符 proof／自算核准／延長過期核准、resume、錯 model ID／revision、未知 last rule／hash、stale CAS／duplicate、future／late／expired clock、cancel／timeout（包括 verifier 或 fsync 延遲）、假控制及七項 readback binding 失配、inflight、損壞／gap／unknown／尾端 receipt 缺失／損壞、撤銷 custody、reservation 後發布失敗仍拒模型、提交後取消正確讀回、hardlink、nested pins 防禦複製、新 root／namespace／aware clock 限制。

程序入口為上述 Python API，沒有本包 CLI／UI。caller 操作順序：先持有 exact rule artifact／source pins／獨立核准 → 構造 command／proof → 明示新隔離 root／namespace 建 synthetic port → default preview → 明示 execute → exact readback → dispatcher 使用同一 port → 新程序重新注入同 custody／root／namespace 讀回。參數錯誤保留 blocker，不自行選規則或補 proof。

排錯：`control_port_missing` 補 caller port；`caller_custody_rejected`／`persisted_caller_custody_rejected` 核原核准記錄；`readback_*_mismatch`／`cas_*` 核 exact model/revision/route；`timeout`／`cancelled` 不重用晚到 command；`control_store_inventory_invalid`／`control_revision_gap` 保留保存目錄診斷，不能刪壞 receipt 讓模型重新可用。port failure 不表示已停止，必須讀回。

## 驗證命令

在指定 worktree，Python 為主 checkout 共用 `.venv/Scripts/python.exe`：

```powershell
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_baldr_b14_shadow_control.py -q -o addopts= -p no:cacheprovider
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_rule_research_shadow_acceptance.py -q -o addopts= -p no:cacheprovider
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B -m mypy app_module/rule_research_shadow_control.py app_module/rule_research_shadow_control_store.py tests/test_baldr_b14_shadow_control.py
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B -m py_compile app_module/rule_research_shadow_control.py app_module/rule_research_shadow_control_store.py tests/test_baldr_b14_shadow_control.py
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B scripts/quant_guard_linter.py
git diff --check
```

本包新增 focused：47 passed。相鄰 shadow acceptance：13 passed（先前同一 union 52 passed=39本包+13既有；其後本包新增8案，去重後60不同案例，不累加重跑）。targeted mypy：3 source files，0 errors。compile／quant guard 通過；最後固定樹核對見交接 full commit／blob hashes。

一次 Luna Max 唯讀 review 已完成，三項實質問題（提交後取消回報、完整 proof clock、尾端 receipt 缺失／損壞）均已修正並加入負控；review 不重跑測試。最後指出的 bootstrap mkdir 後取消會留下空 root，屬已明示的 fail-closed 部分初始化限制：新增測試核空目錄不可 constructor 讀回、無 receipt、witness不變；不清理或覆蓋該root，同路徑不得重試。

無裸 float／金融公式／資料標準化／訊號／labels／benchmark／價格或績效計算；本包只控制 opaque 原 bytes route，沒有引入未來資料。Quant guard 為既有白名單靜態檢查，不作為完整金融正確性證明。

## 剩餘與回退

B13 final commit 採納後，prediction freezing／maturity／drift adapter 是下一包，需中央再鎖 ownership；現在不接未提交 API、不新增 ML writer imports、不改 B01 allowlist。正式 model、Task、registry writer、訓練、交易、私人 migration、ACL、Native、push／dev cherry-pick 均未執行；不授 training／PIT／natural／formal／production 資格。

中央已通知 B13 採納 commit `9266e7e3`，原 lane `4f828f1f3698788c6726c9c3471e2f4763898f89`、adapter blob `490d9fdf8a7a6a1af08f8d74e04ed0e8b23c9a8a`；本包 base／scope 不變，composition 仍須下一包 exact ownership。

完整 Manual／Snapshot／architecture／shared state／測試路由由中央整合本收據素材；重 UI mandatory union 只在中央穩定窗口一次執行，本包 focused 不能代替該驗收。

程式回退為中央整合後 revert 本包 commit；不刪除來源或已保存控制 receipts。模型恢復必須獨立明示核准與新 adapter，本包不能用 revert／receipt 清理假冒 resume。

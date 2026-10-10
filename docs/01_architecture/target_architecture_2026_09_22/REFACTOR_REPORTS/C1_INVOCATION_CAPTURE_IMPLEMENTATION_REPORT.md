> **C1 子階段歷史狀態**：本文的未通過／blocked 描述只代表 U3 invocation capture 切片當時狀態；後續 [C1 checkpoint](C1_CHECKPOINT.md) 記錄 C1 Engineering PASS、Wave 6 released。R014 真正 wrapper parity 仍未完成；本文 U3 的窄範圍結果保留，不構成產品或生產授權。

# C1 U3 Invocation Capture Implementation Report

- **狀態：** `U3_ACCEPTED_FOR_U4`
- **切片：** C1 U3 invocation capture；不代表 C1 PASS 或 Wave 6 解鎖。
- **Implementer：** Luna Max
- **起始／結束 HEAD：** `dcc27a42a37c2f69ad83fecee6c245177a457e01`（未提交）
- **工作樹基線：** 起始時已包含本 refactor 的 dirty／untracked paths，包含 U1/U2、R011 及其他並行工作的檔案；本切片只在授權檔案內工作，未覆寫其他路徑，未 stage、commit 或 push。
- **狀態約束：** U1/U2/U3 已依序接受進入下一切片；U4/U5 與 C1/Wave 6 仍維持 `BLOCKED`。未修改或啟動 scheduled wrapper，真 scheduled wrapper parity 與 R014 接線仍未完成。
- **複審結論：** 第一輪獨立 review 重現的 P1 scheduled marker downgrade 與 P2 caller clock provenance 已修復；獨立 Luna Max 複審結論為 **`Accept U3 only`**，沒有剩餘 P0/P1/P2。此結論不代表 U4/U5 或 C1/Wave 6 通過。

## 已讀 authority 與 dependency

- 根目錄 `AGENTS.md` 指定必讀文件及量化數值護欄。
- `docs/agents/README.md`、`shared_context.md`、`git_exclusions.md`、`skills_registry.md`、`execution_agent.md`。
- Project snapshot、roadmap、產品／工程方向、system／target architecture、quant defense 文件。
- `C1_UPSTREAM_REPAIR_SCOPE_RULING.md`、C1 consumer readiness matrix、C1 finding、`FINAL_DATA_FLOW.md`。
- U1 contract repair report 與 U2 codec repair report（狀態分別為 `U1_ACCEPTED_FOR_U2`、`U2_ACCEPTED_FOR_U3`）。
- `REFACTOR_TASKS/R011.md`、`R014.md`，以及 R011 implementation／review／acceptance 材料。
- 現行 execute/service、recommendation contracts、DTO、R011 use-case tests、U1 contract tests、U2 codec tests。

## 實作與範圍

### Invocation capture 與 direct execution seam

- `execute_recommendation()` 接受分離的 `runtime_config` 與原 caller `RecommendationConfigSnapshot`，並將呼叫時的 `max_stocks`／`top_n` 寫入 `Request`。舊 `run_recommendation()` list ABI 保留無 callback 路徑；runtime 或 caller snapshot 明示 scheduled 時，module use case 拒絕無 callback 的執行。
- `RecommendationService.execute_recommendation()` 新增供 R014 後續接線使用的 direct execution seam。原始 snapshot 與同步 `postprocess_callback` 是必填 keyword-only 參數，並在執行前拒絕非 callable callback；因此即使 service 呼叫前的 runtime config 沒有 `scheduled_snapshot` marker，漏傳 callback 也不能執行或回傳不完整 completed result。
- R011 `copy(service)` invocation-local view 的 transient fields 在 body 返回後立即 deep-copy 到本次 private capture。callback 收到的是該 capture 投影出的同次 Request、DTO 列、screening matrix、runtime config 與 Context；不收到 service，也不讀共享 `service.last_*`。完整 execution 在 callback 完成並通過 U1 typed contract 驗證後才建立及返回。
- callback 產生具名 `RecommendationPostprocessFacts`，包含 typed cohort、evidence identity、result config snapshot/hash 與 optional aware `created_at`。`RecommendationResultConfigSnapshot` 驗證完整 config canonical hash；Context／Execution constructors 交叉驗證 scheduled required owners、identity/evidence/cohort overlap、Request snapshot/limits 以及 clocks。callback/body 例外不會返回可保存的 partial execution；對 callback-free 舊路徑仍保留原有 status/error 處理。
- callback facts 返回後再次比對 input 與 result marker：caller/runtime 已標記 scheduled 時，callback 不能把 result marker 降為 false；反向由 pre-run 非 scheduled 變成 scheduled 仍允許，以符合 wrapper 後生成 marker 的時序。
- `_invocation_context.created_at` 只保存明示的 caller/wrapper clock，不再以 service `run_started_at` 回填。scheduled result 必須有明示 caller `created_at`；non-scheduled callback 可將缺值明確保存為 `None`。service `run_started_at`、`available_at` 與實際 `decision_at` 分別保留；不要求 caller time 與 service start 相等，Context contract 保持 `available_at <= decision_at`，不強制 `decision_date == as_of_date`。

### Row capture 與 fail-closed

- `RecommendationItem.rule_score` 唯一對應 DTO `total_score`，沒有另存第二份 `total_score`；DTO 數值轉換使用 `Decimal(str(value))`。scheduled result config 下，`rule_score`、close price、price change、indicator/pattern/volume scores 缺漏或不是有限數值時拒絕封存；industry 與 reason text 也必須有值。非 scheduled 的舊 ABI 保留 optional/unknown `None` 語意。
- 沒有在 callback 或 capture 中重新評分、推論或 live-read。合成 fixture 的 recommendation generator 回傳固定合成分數，cohort 以既有 `_build_snapshot_cohort` 建立，result config hash 以 producer `_sha256_json` 作 oracle。

### Changed files

- `app_module/recommendation/execute.py` — 同步 callback、invocation-local capture 投影、Request 原快照／limits、clock event、typed facts 驗證、scheduled marker/created_at provenance 與 row completeness 檢查及 callback 路徑 fail-closed。
- `app_module/recommendation_service.py` — 新增 callback 與原始 config snapshot 必填的 direct execution delegation；既有 list facade 未改 public ABI。此檔在起始 dirty baseline 已含其他 R011 工作，本報告只涵蓋本 slice 加入的 direct method，不重述或認領其他變更。
- `tests/test_c1_invocation_capture.py` — 新增隔離 synthetic capture、full config/hash、clock、numeric/reason row、missing callback/hash/owner/error、A/B interleave 與來源更新測試。
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/C1_INVOCATION_CAPTURE_IMPLEMENTATION_REPORT.md` — 本報告。

未修改 contracts、codec、persistence、queries、scheduled scripts、ML、forward producer、R014 wrapper 或其他非授權路徑。未執行 scheduled main、未讀寫正式 `DATA_ROOT`，未新增持久 component。

## 行為與相容性證據

- 舊 DTO list 路徑由 R011 use-case tests 驗證，沒有觀察到 list ABI regression；舊路徑不要求 callback。
- 新 direct seam 對漏傳 callback（即使 runtime/request config 都未設 scheduled marker）在 body 啟動前拒絕；caller config snapshot、numeric strings、limits 與 runtime floats 分別保留。
- A/B 同 service instance 並行執行，在 callback 暫停期間更新 provider 來源；兩份 execution 仍各自保存正確輸入、row、cohort、strategy/universe identity 與 clocks，service shared last state 維持原值。
- wrapper `created_at` 早於 service `run_started_at` 的 fixture 通過；二者分別可在 Context 與 capture event 追溯。available/decision clocks 使用同次來源且符合 U1 ordering contract。
- review P1 repro 現在因 pre-run scheduled marker 與 callback result marker 矛盾而在 row sealing 前拒絕；reverse upgrade path 仍由其他 scheduled callback fixtures 覆蓋。
- review P2 repro 現在因 scheduled result 缺原 caller clock 而拒絕；non-scheduled callback 缺 caller clock 時 `Context.created_at` 保持 `None`，clock event 仍分別記 service run start。
- missing required numeric/text row、non-finite score、缺 result config owner、錯 config hash、錯 `created_at`、callback error 與 body error 均 fail closed，沒有產生公開 partial execution。
- persistence/query、replay 與 ML 行為未改；本 slice 沒有保存 artifact 或呼叫 producer/ML inference。U1/U2 contract/codec suites 維持通過。

## 驗收項目

| U3 項目 | 結果 | 證據／限制 |
|---|---|---|
| Request 保存 caller 原始 config snapshot 與 limits，與 runtime config 分離 | **通過** | 合成 Request/runtime numeric string-vs-float assertion |
| 同步 callback 只能讀同次 private capture，並在 execute 返回前封存 | **通過** | C1 callback fixture、A/B interleave；沒有 service/共享 state 參數 |
| callback/full config hash、typed owners、clocks 與 identity 交叉驗證 | **通過** | producer `_sha256_json` oracle、U1 constructors 與錯 hash/owner/clock 負例 |
| scheduled required row 數值／文字缺失或無效時 fail closed | **通過** | DTO `None`、`Infinity`、必填文字負例；Rule score 唯一 |
| caller scheduled marker 不可被 callback result marker 降級 | **通過** | P1 regression fixture 斷言 row builder 未執行；獨立 review `Accept U3 only` |
| scheduled result 缺 caller `created_at` 時拒絕，non-scheduled unknown 仍為 `None` | **通過** | P2 regression fixture + non-scheduled unknown clock fixture；獨立 review `Accept U3 only` |
| 非 scheduled legacy list ABI 無 callback 保持相容 | **通過** | `tests/test_recommendation_execution_use_case.py` |
| 真 scheduled wrapper parity 與 R014 caller 接線 | **未執行／保留** | C1 裁決禁止本 slice 改動或啟動 wrapper；需 C1 完整 gate 後另行接線驗證 |
| C1 / Wave 6 release | **仍 BLOCKED** | U3 僅 `Accept U3 only`；U4/U5、R014 接線與完整 C1 gate 尚未完成，不宣稱 C1 PASS |

## 獨立複審結論

Luna Max 獨立複審：**`Accept U3 only`**，沒有剩餘 P0/P1/P2。複審涵蓋 P1 marker downgrade 與 P2 caller-clock provenance 修復，以及 U3/R011 26 passed、U1/U2 contract+codec 88 passed、`py_compile` 與 scoped mypy 通過結果。U4/U5 尚未執行；真 scheduled wrapper parity 與 R014 接線仍未完成。C1/Wave 6 維持 `BLOCKED`。

## 驗證

| 完整命令 | 結果 |
|---|---|
| `\.venv\Scripts\python.exe -m pytest tests/test_c1_invocation_capture.py tests/test_recommendation_execution_use_case.py -q -o addopts=` | **26 passed** |
| `\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py tests/test_recommendation_execution_codec.py -q -o addopts=` | **88 passed** |
| `\.venv\Scripts\python.exe -m py_compile app_module\recommendation\execute.py app_module\recommendation_service.py tests\test_c1_invocation_capture.py tests\test_recommendation_execution_use_case.py` | **通過** |
| `\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation\execute.py app_module\recommendation_service.py` | **Success: no issues found in 2 source files** |

未執行 scheduled wrapper、production data、persistence/query 與 consumer readiness tests；這些不屬 U3，真 scheduled parity 明確留待 R014。

## 暫存元件、風險與 rollback

- 未建立需要獨立移除的 temporary component；新增 direct seam 是後續 R014 可接線的 execution API，不包含 wrapper 接線。
- 未 stage／commit/push；HEAD 仍是 `dcc27a42a37c2f69ad83fecee6c245177a457e01`。工作樹內含其他 slice 的 dirty/untracked 檔案，不可用 HEAD checkout 或整目錄刪除作 rollback。
- 若獨立 review 要求回退 U3，應只撤回本報告列出的 direct method 與 U3 capture/callback/row capture 變更，以及本 slice 新增的 capture tests/report；需保留 R011 `execute.py` 與舊 DTO list delegation 所需程式。不要刪除共享的 `app_module/recommendation/` 目錄或重置其他 dirty paths。
- 限制：synthetic fixture 證明同次 capture 與現行 builder/hash oracle 的一致性；沒有實際呼叫 R014 wrapper，因此不能據此宣稱真 scheduled config parity、saved readback 或 C1 PASS。

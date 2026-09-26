# 重構風險登錄表

> Risk owner 是負責產生證據與停止條件的 task，不代表可自行變更架構。任何風險觸發 rollback／blocker時，先保留差異，再由 program manager決定下一task。

| ID | 風險／觸發訊號 | 影響 tasks | 預防與偵測 | 停止／回滾條件 | Owner |
|---|---|---|---|---|---|
| RK-01 | 推薦計算、filter、ranking、order語意漂移 | R002,R011,R018,R019,R020 | 固定輸入golden/手算、同mode exact parity、stable sort/tie-break | 任一未核准差異即停止該slice | R002基線；各實作task |
| RK-02 | Decimal quantum、legacy float、null/zero或rounding改變 | R002,R008,R009,R019,R029 | Decimal字串、不經float中轉；TMP-NUM-01；極值/unknown tests | bytes/value/order差異未解釋即rollback | R002/R009/R019 |
| RK-03 | execution仍依賴共享last_*，A/B run互相污染 | R003,R011,R013-R015,R029 | A→B→save A、invocation capture、nested mutation、repo search | execution無法獨立重讀或跨run混合 | R003/R011 |
| RK-04 | schema-driven codec漏欄、舊reader截斷新revision | R009,R012,R030 | fields-based codec、revision dispatch、unknown reject、all-field test | 新artifact可被少欄reader回存或hash不穩 | R009 |
| RK-05 | JSON artifact／SQLite index不一致或舊replace覆寫 | R004,R012,R014,R015 | exclusive create、same-hash idempotency、orphan recovery、index rebuild | 同ID異hash可覆寫或失敗後重算 | R012 |
| RK-06 | 歷史artifact／DTO／中文keys無法讀 | R004,R009,R012,R016,R029 | 永久decoder、old bytes fixtures、先驗hash | unknown bytes遭修改/刪除或read view重寫原檔 | R009/R012 |
| RK-07 | replay被「共用」後偷偷採interactive政策 | R005,R017,R020 | 各mode獨立oracle、versioned policy、future-row/date tests | replay score/candidate/lookback差異未核准 | R020 |
| RK-08 | temporary dual architecture永久存在 | R001,R011,R017,R025,R029 | 每個TMP有creator/remover/caller/exit；Wave 9搜尋 | 無deletion owner、兩engine都可寫正式結果 | R001/R029 |
| RK-09 | dependency cycle或廣泛re-export在import時觸發I/O | R007-R010,R021-R025,R030 | leaf import smoke、module DAG、窄re-export支援期 | 新data↔decision/app cycle或import side effect | R030；各boundary task |
| RK-10 | factor source解碼與domain語意分離後值／quality漂移 | R023,R024,R019 | 同標準facts→原FactorRecord、unit/date/missing tests | factor值/diagnostic/source custody差異 | R023/R024 |
| RK-11 | Regime I/O抽離消失confirmation/cooldown或保存時重查 | R022,R012,R013 | 多日/same-day/historical tests、execution-time snapshot | state transition或run A保存結果改變 | R022 |
| RK-12 | Strategy relocation 在 repo 範圍產生雙 registry、import break或不同 signal | R025,R029 | ID/meta/signal exact tests、唯一 registry／alias identity、repo caller inventory | repo 內出現第二 registry、alias identity 或 signal parity 失敗 | R025 |
| RK-13 | UI顯示／保存不是同一execution，stale callback覆蓋 | R003,R013,R031 | request correlation、last-good、cancel/save tests | cancelled/old run顯示或保存成新run | R013 |
| RK-14 | Scheduled clock/calendar/candidate publication順序改變 | R014 | wrapper/calendar custody tests、save-before-forward assertion | clock/source custody或side-effect順序改變 | R014 |
| RK-15 | Personalization result/receipt/ACK identity不一致 | R015,R026 | exact readback、candidate/model hash、CAS/retry tests | ACK掩蓋save、retry重算或降級舊personal result | R015 |
| RK-16 | ML feature order/dtype/scale/mask/transform失效 | R006,R010,R026,R030 | ABI inventory、loader/feature tests、new feature opt-in | 舊model input或prediction parity改變 | R006/R026 |
| RK-17 | ML provider在infer中暗讀更新中的DB造成race | R010,R026 | PreparedMLInput、update barrier、snapshot/source identity | 無法證明cutoff/version一致時拒絕projection | R026 |
| RK-18 | Direct source bytes/path或runtime constants使checkpoint identity失效 | R006,R027,R028 | 15-path inventory、stable/runtime分層、resume正反例 | 任一hash/timing/bytes差異→AB-ML-01 | R027 |
| RK-19 | joblib/pickle qualified class path被當無caller刪除 | R001,R006,R025,R029 | artifact inventory＋load fixture，不只rg imports | 支援artifact仍引用舊path | R006/R029 |
| RK-20 | 大型central files的多人diff互相覆寫 | R011,R012,R018,R019,R026,R029 | execution waves、exclusive owner、small merge order | active tasks碰相同central region | Program manager |
| RK-21 | Data contract抽取需要正式資料重寫 | R007,R023,R024 | additive contract/adapters、tmp fixtures、no data migration | task要求修改/回填正式data才能通過 | Boundary task owner |
| RK-22 | Architecture guard靠廣泛allowlist變綠 | R030,R031 | bad-fixture positive/negative tests、exact symbol baseline | 新allowlist未列owner/expiry或掩蓋4項既有違規 | R030 |
| RK-23 | 「full regression」範圍過大導致無法定位，或過小漏跨流 | R012,R020,R029,R031 | C1-C4分層checkpoints、focused first/full relevant later | checkpoint缺category或只跑單元測試 | R031 |
| RK-24 | 工程完成被誤報為formal/production/promotion | 全部，尤其R031 | INV-18、Scoped SSOT與closeout措辭審查 | 文件或UI宣稱未獲准權限 | R031 |
| RK-25 | 未檢入的外部 caller／deployment extension 或未知支援期，使 facade 移除成 migration dead end | R001,R014,R025,R029 | 依 R025／R029 preflight 保存有限 repo caller 與 literal-path inventory；目前已知 direct strategy callers 已遷移，literal-path 命中為相容 alias fixture，有限檢查未找到 generic loader 中的舊 facade 字串。未檢入 deployment/plugin caller 與 external support period 仍須具名保留；未決前保留相容 facade | 發現不可遷移外部 caller，或支援期／deprecation 未決而試圖移除 facade | R001/R029；各 compatibility owner |
| RK-26 | 既有 opaque result_id 直接作檔名造成路徑逃逸、保留名稱或大小寫碰撞 | R008,R009,R012,R016 | 保留 exact identity；R012 writer採安全檔名映射、target containment／symlink 檢查與 readback exact ID；隔離fixture測 traversal／separator／Windows保留名／case collision | 任一 ID 可寫出預期 artifact root、同名不同 ID 碰撞或讀回身份不符即停止保存切片 | R012；R008 僅維持 typed ID／binding |

## 2026-09-25 R026／C2–C4 current checkpoint（C4 accepted with named boundary baseline）

R026 exact consumer、明列 NP1／NP2 profile 與同次 capability 的 bounded runtime migration，以及 typed post-calibration handoff 已由 root 接受；`TMP-ML-01` 對此支援集合已關閉。R020 bounded replay criteria 已接受，`TMP-REC-04` 已關閉；兩者均不代表所有 profile／model graph、全部 replay caller 或 numeric boundary 都完成。Unsupported/custom caller 保留相容路徑。C2 current union 為 1,860 passed／5 skipped／34 warnings、exit 0，root 裁定 `ACCEPTED_WITH_NAMED_QA_BASELINE`；該次 Update validator 的 synthetic SQLite teardown `WinError 32` 仍為具名歷史例外，Owner 為 Update QA／DB resource lifecycle。後續 C4 Update validator 為 25 passed／0 failed／4 skipped，不改寫 C2 原始結果。

C3 首次 union 為 2,443 passed／4 failed／5 skipped／35 warnings，471 個 frozen inputs 前後 hash 一致，原始 fail receipt 保留。其後 UI save fixtures 以 typed DTO 表示 live execution，指定 UI／R020／presenter focused route 為 22 passed。R026 兩個 exact app→ML imports 已限定到 source/symbol allowlist；584-file scan 回到 11 occurrences／10 distinct diagnostics。含 guard／CLI／R030 files 的 focused route 為 30 passed／2 failed，兩項失敗只觸及既有 repository guard／CLI aggregate assertions；11 項依賴／guard baseline 有具名 owner，不宣稱全 guard clean。詳見 [R026 shadow-boundary follow-up](../../06_qa/ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)。

C4 mandatory gates 已驗證：Workbench 84 passed、Update validator 25 passed／0 failed／4 skipped、broad mypy 724 files／0 issues、67 個 changed Python files `py_compile` 通過，`git diff --check` 通過。C4 full union 為 2,446 passed／2 failed／5 skipped／35 warnings（640.25 秒，exit 1）；root 裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。兩個失敗為既有 shadow-boundary CLI／repository aggregate assertions；584-file scan 為 11 occurrences／10 distinct diagnostics，仍由具名 owners 追蹤。471 個 route inputs 前後 hash 未變，SHA-256 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`；pytest log `C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\pytest.log` SHA-256 `88797C7C2476576D771E88099E0016D49C10A78D29B0494B2A3CE834A8CF29F9`；route SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。依 root-reviewed disposition map，以下列出 26 個 RK：19 項 CLOSED、4 項 ACCEPTED WITH OWNER、3 項 BLOCKED；有限工程 scope 完成但不是全綠。詳見 [R031 closeout record](../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。

| ID | Disposition | Owner | Evidence 與範圍／殘餘 |
|---|---|---|---|
| RK-01 | **CLOSED（bounded）** | R002／R020 | Recommendation characterization 與 R020 fixed-vector/replay evidence；不擴大為未驗 profile 或策略有效性。 |
| RK-02 | **ACCEPTED WITH OWNER** | Decision recommendation／app codec | `TMP-NUM-01` 仍需獨立處理 precision、rounding、tie-break、Decimal string 與剩餘 caller parity；R020 bounded numeric evidence 不代替該 gate。 |
| RK-03 | **CLOSED（execution truth）** | R003／R019／R026 | 同次 execution capture、A/B isolation 與 typed post-calibration handoff；剩餘 legacy ports／sidecar consumers 歸 RK-08／RK-25。 |
| RK-04 | **CLOSED（known codecs）** | R009 | Schema/revision codec 與 complete-field、old-bytes、unknown-revision fixtures；unknown serialized class paths 歸 RK-19。 |
| RK-05 | **CLOSED（bounded persistence）** | R012 | Create-only、same-ID conflict、orphan/recovery 與 exact readback evidence。 |
| RK-06 | **CLOSED（known old bytes）** | R009／R012 | 已知歷史 bytes／decoder 維持可讀且不被重寫；未知 artifact/class paths 獨立列 RK-19。 |
| RK-07 | **CLOSED（mode policy）** | R020 | R005 mode-specific oracle、cutoff/date vectors 與 R020 fixed-vector evidence；不推論其它未列 modes。 |
| RK-08 | **ACCEPTED WITH OWNER** | R029 compatibility owners | 保留 TMP：`TMP-REC-02/05`、`TMP-STR-01`、`TMP-RGM-01` 等具名 compatibility surface；不得把保留 ABI 或外部支援期改寫為已移除。 |
| RK-09 | **ACCEPTED WITH OWNER** | R030 dependency-boundary owners | 既有依賴方向 residuals 分列並交由具名 Restated/allocation owners；不以 broad allowlist 放行，也不與 R030 Direct、`FactorDiagnostic` 或 `DBManager` 問題混算。 |
| RK-10 | **CLOSED** | R023／R024 | Factor contract/adapters、來源 custody、unit/date/missing 與 quality regression evidence。 |
| RK-11 | **CLOSED（bounded state flow）** | R022 | Regime state／policy、multi-day、source-failure、save-after-source-change 與 UI routes；legacy compatibility surface 仍列 RK-08。 |
| RK-12 | **CLOSED（repo scope）** | R025 | 唯一 strategy registry、alias identity、signal parity 及有限 repo caller inventory；外部 caller/support period 另列 RK-25。 |
| RK-13 | **CLOSED** | R013 | Request correlation、stale/cancelled callback 與 save-after-current-execution regression。 |
| RK-14 | **CLOSED（synthetic schedule custody）** | R014 | 合成 clock/calendar/publication-order 與 save-before-forward tests；未執行正式 scheduler，亦未宣稱正式營運驗收。 |
| RK-15 | **CLOSED（bounded persistence/ACK）** | R015 | Exact artifact readback、retry/CAS acknowledgement、receipt identity 與 C2 current route evidence。 |
| RK-16 | **CLOSED（R026 supported profiles）** | R026 | NP1／NP2 exact-profile ABI、same-bytes、candidate/input 與 supported service routes；custom／unknown artifacts 不在此結論內。 |
| RK-17 | **CLOSED（source binding scope）** | R026 | 同次 prepared input、decision clock、source-contract evidence、snapshot/cutoff alignment 與 no-I/O projector evidence。 |
| RK-18 | **BLOCKED** | R027／R028 data numeric store／ML identity owners | R027 `INCONCLUSIVE`、`AB-ML-01=OPEN`、`TMP-ML-02=ACTIVE`，848 exact timing/snapshot differences；R028 依 prerequisite `BLOCKED`。 |
| RK-19 | **BLOCKED** | R006 artifact／ML custodian | 未知 formal binaries 與 serialized class paths 未載入、未推定安全；保留歷史 readers、必要 aliases 與 rejection policy。 |
| RK-20 | **CLOSED（this wave）** | Program manager／slice owners | Wave ownership、central-file change coordination、C2/C3 frozen-input receipts；不表示永久免除未來變更的 owner discipline。 |
| RK-21 | **CLOSED（no formal rewrite）** | Data boundary owners | Additive contracts/adapters 與 synthetic fixtures 證明此 wave 無需正式資料 rewrite；不授權未來 data repair。 |
| RK-22 | **ACCEPTED WITH OWNER（guard baseline）** | R030 Restated/allocation guard owners | C4 584-file scan 有 11 diagnostic occurrences／10 distinct；R026 edges 已精確修復。Focused 30P／2F 與 C4 union 的兩項 failure 均為既有 repository／CLI aggregate assertions；baseline 收據見 [R026 shadow-boundary follow-up](../../06_qa/ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md) 及 [R031 closeout record](../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。 |
| RK-23 | **CLOSED（full relevant coverage scope）** | R031 QA owner | C1–C4 validation matrix 涵蓋定義的 full relevant coverage categories；C4 union 已完成並獲 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`，兩個既有 guard／CLI aggregate assertion failures 與 named shadow baseline 留在 RK-22。Coverage scope 已驗證；本列不把 retained baseline 宣稱為零失敗。 |
| RK-24 | **CLOSED（after documentation review）** | R031 documentation owner | Current／target architecture、Snapshot、Index 與 risk dispositions 依 scoped SSOT 同步並做 link/fence/diff review；formal、promotion、production 等權限仍明確排除。 |
| RK-25 | **BLOCKED** | R001／R029 compatibility owners | 有限 repo inventory 已完成；未發現 generic-loader 中舊 facade 字串，但未檢入 deployment/plugin callers 與 external support period 無法由 repo bytes 證明。保留 compatibility facade。 |
| RK-26 | **CLOSED（safe ID mapping）** | R008／R012 | Exact identity、safe filename mapping、containment/symlink/readback 與 traversal、reserved-name、collision fixtures。 |

C2 的 Update validator teardown failure 仍以 `ACCEPTED WITH OWNER` 保留為 QA resource-lifecycle 歷史例外；C4 Update validator 成功不回寫 C2。RK-09 dependency-direction residual、RK-22 11-occurrence guard baseline 與 R030 四項 Direct／`FactorDiagnostic`／`DBManager` issues 是不同帳目。R027/R028 與 unknown serialized artifacts 不因 R026 supported-profile acceptance 而解除。

## 風險 review 節點

- **C1/R012**：RK-01–06、15–17、26。
- **C2/R020**：RK-01–08、13–17。
- **R027 decision gate**：RK-18；失敗即 `AB-ML-01`。
- **C3/R029**：全部temporary／serialized／external caller風險。
- **C4/R031**：26 個 RK 已有 root-reviewed disposition，分類為 19 CLOSED／4 ACCEPTED WITH OWNER／3 BLOCKED。C4 union 已獲 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`；R031 有限工程 scope 完成，仍保留 RK-08／09／22 owners 與 RK-18／19／25 blockers，不得總結為全綠。

## 不以本計畫處理的風險

- 投資策略有效性、自然時間證據、正式資料來源接受、ML promotion、broker execution權限仍由既有產品／工程Gate管理。
- 未經另案授權，不進行正式資料修復、回填、全市場ML重建、scheduler實跑或模型切換。
- 發現既有產品bug時另建behavior-change task；除FINAL已明確要求的execution-time snapshot/create-only一致性修正外，不混入結構task。

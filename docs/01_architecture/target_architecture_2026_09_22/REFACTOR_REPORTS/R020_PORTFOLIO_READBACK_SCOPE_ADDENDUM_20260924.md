# R020 portfolio result readback scope addendum

> 日期：2026-09-24
> 狀態：架構裁決；Stage A codec、Stage B1 repository CAS、Stage B2 Registry publish、Stage C strict DTO／child readback 與 Stage D Registry UI／Manual 各自 bounded `ACCEPTED_SCOPE`。R020 整體仍 `IN_PROGRESS`，不代表 V-REPLAY／C2 完成。
> 範圍：R020 新增 Registry portfolio result 的完整 DTO 保存與讀回窄幅整合範圍。

## 裁決摘要

依 Root 2026-09-24 架構裁決，本 addendum 明確新增 R020 的 Registry portfolio integration 授權：版本化 portfolio-result sidecar、Registry repository 的 guarded staging-only manifest／payload-hash finalize、strict DTO reader、Registry 專屬 UI 入口及操作手冊同步。sidecar descriptor 對一般 Registry 格式是可選 extension；每筆新建的 portfolio result 則必須明示 sidecar 為必備。這是窄幅 scope addendum，不是實作完成或 parity 驗收紀錄；不改寫 R020 原 task／實作報告或其他 acceptance gates，也不代表 C2、`TMP-REC-04` 或 R020 已完成。

## 實作進度與 gate（2026-09-24）

- Stage A portfolio-result codec 已由 R027 frozen SHA 獨立複審並取得 bounded `ACCEPTED_SCOPE`：`app_module/recommendation_portfolio_result_artifact.py` SHA-256 `559EAEFD1CAF3D4193D3499BCC6F64B66AF64733C93769F9DCB30DE97C5B4736`；`tests/test_r020_portfolio_result_artifact.py` SHA-256 `C7975D1A39888B46011BC4B12B1148431816112A5781017D15DECF0E28D529CC`。fresh TEMP route `42 passed`、`24` 個既有 warnings，無剩餘 P1／P2。
- Stage B1 repository guarded finalize CAS 已 bounded `ACCEPTED_SCOPE`；`tests/test_research_run_portfolio_finalize.py` SHA-256 `15297F1E205F0FA396FAD3D55D8D944195A287881730E71D0599DBF07A8DC89C`。此 gate 驗證 staging/pending、expected base `payload_hash`、portfolio run type、原 manifest 保留及不可變狀態；此處不重報未凍結於本 receipt 的 pass 數。
- Stage B2 先前 source receipt（service SHA-256 `18CE2A329A1F8092EAC4BD280E536D24E08060476B04CBE57D03BEE67D91E7B8`、repository SHA-256 `8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`、tests SHA-256 `BDFA08912679D2053F14187C889866A77BB0B61B4B7BC1CE2AF723BFBA0D8827`；fresh TEMP `103 passed, 1 skipped`）保留為歷史 bounded acceptance。該 receipt 為 guard 變更前歷史 bytes；最新 B2 acceptance 見下一列。
- **最新 B2 gate update（取代本節較早的 pending-review 句）**：lineage-status guard 的新 B2 bytes 已由 R015 獨立 bounded `ACCEPTED_SCOPE`：service `DC47816C62D1249629B2CE6303608B52503E3735882EAD74A68C75AF7D7B00CF`、repository `8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`、tests `CA18D12AF9F483C8302BF3C146D915B272BE42E79AED4A81C88AE9BE46B6D1C1`；R015 fresh TEMP non-UI route `70 passed`，mypy 0／compile 通過。B2 guard 只保護 Registry writes；BacktestView 先 create-only 寫 R012 children，再呼叫 B2，若後續 Registry metadata validation 失敗，child 可能保留並須依同 ID／同 bytes 重試。此 residual 不代表跨 store rollback。
- Stage C strict DTO materialization／child-integrated readback 已由 R023 frozen-source 獨立 bounded `ACCEPTED_SCOPE`：reader SHA-256 `812ED626377812F53650EBDEA0E587A036AC6BED80E060CF532B085E18ADFACB`、tests SHA-256 `1C5E68904A4956C9416EE99B2986EABD78C36752A9C7C4C193462832EA02D124`；專項 fresh TEMP route `14 passed`，交叉 route `79 passed／1 skipped`。完整 DTO 只有在 Registry artifacts／manifest 與所有 declared R012 child bytes 驗證成功後回傳；舊 markerless run 為 typed unavailable，marked corruption fail closed。
- Stage D BacktestView Registry 專屬 UI／Manual 已由 R023 獨立 bounded `ACCEPTED_SCOPE`：同次完整 DTO 才可保存並傳入 `portfolio_result`；零 snapshots 時跳過 R012 child persistence、寫 parent-bound `unavailable` 且不發布空 sidecar；Registry 單選開啟不混入 legacy dropdown；strict reader unavailable／corruption、stale request、legacy-history save guard 與 empty/no-child UI 判讀均有測試；Registry readback 不抓目前 benchmark overlay。R023 獨立 7-file fresh TEMP route `95 passed`、Workbench `84 passed`、broad mypy `712 source files／0 issues`、compile／diff-check 通過。Update QA 分別記錄：R027 `25／0／4` exit 0；R023 `25／1／4` 的單一失敗為 WinError32 TEMP SQLite teardown，非功能 assertion，不計 reviewer pass。Stage D bounded acceptance 不代表 R020 整體完成。
- `reconcile_incomplete_saves` 是顯式操作，應只在確認 writers quiescent 後執行；若與 live staging writer 競賽，reconcile 可能 fail closed 將該 row 標為 failed。此路徑沒有 lease／自動 writer 協調保證。
- 跨 R012／Registry 的 process-crash／missing-child recovery 目前只有 bounded evidence：R015 test `tests/test_r020_process_crash_recovery.py` frozen SHA-256 `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63`；R027 獨立 fresh TEMP 7-file route `142 passed, 3 skipped`，scoped mypy `7 source files／0 issues`、py_compile 通過。它涵蓋 **3 個 `spawn`／`os._exit` 真正 crash 點**（R012 child artifact 發布後／index 前、所有 child 完成後／Registry save 前、Registry `files_ready` CAS 後／artifact publish 前）及 **1 個 committed child 缺檔情境**；缺檔 case 是 fail-closed 負向／修復情境，不是第四個 hard-exit。修復須明確重發同 hash 原 `RecommendationExecution`；同 ID／同 bytes retry 可恢復，異 bytes 不可覆寫。
- 上述不是完整 recovery gate：未涵蓋所有 partial-publish crash windows、R012 與 Registry 間的共同原子交易／補償 rollback，也不會自動重建原 execution。full process-crash／child-missing recovery gate 仍未關閉；reconciliation 僅能在確認 writers quiescent 後明確執行。
- **最新 `TMP-NUM-01` runtime evidence（取代下列歷史的 Windows NumPy 1 collection blocker）**：R015 對 provider `app_module/recommendation_dataframe_provider.py` SHA-256 `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630` 與 differential/C1b/provider adapter tests 的 frozen bytes 給 `ACCEPTED_SCOPE`，無 P1/P2。修補前 NumPy 1.26.4 沒有 `np.exceptions.RankWarning`，但有 `np.RankWarning`；provider 在 scorer try 中直接讀缺失屬性，將 AttributeError 當 scorer exception 並略過候選。修補後 resolver 優先讀新 API，缺席時才 lazy 讀舊 alias，只忽略 RankWarning；兩種 API-shape tests 與真實 no-filter scorer/row/disposition 測試已通過。NumPy 1.26.4／Pandas 2.3.3 與 NumPy 2.3.5／Pandas 2.3.3 的同一 15-file R005/R020 route 各 `216 passed, 1 skipped`；獨立 4-file route（`test_r020_numeric_runtime_differential.py`、`test_r020_c1b_numeric_dtype_legacy.py`、`test_r020_provider_staged_prefilter_adapter.py`、`test_r020_provider_scorer_handoff.py`）各 `58 passed, 1 skipped`。差異測試 SHA `D792F2B4AED996474FA4086C20F8C7C4CD63891C9606B639C297262AF1B01157`、C1b SHA `F6954D4E19607304F4F8D5C4A4C9CAF923686A387A431D5171795B61A48739AF`、provider adapter SHA `568E73E4C6DF26959F3A331C668DECF630A85EF4C3ADEA9AEC510D05896908C2`。4-file receipts：NP1 log SHA `CC719394E8C6B96818802B92C32F0EAEB532E0B792891CBBB0E26B91E318CB9D`，NP2 log SHA `7C479D5862F5C130539DB06D98DE3AEDB2110E5DA9590262005D811E17D63074`。TEMP fastdtw 0.3.4 fallback 僅為 NumPy 1 test environment：從 repo `.venv` 複製前逐項驗證 installed RECORD hashes，provenance JSON SHA `D5006DEE131E0552CA479AA66A4AC625A80B426D7A8C5DD27C17D29FA054EC74`，沒有改依賴宣告。兩 profile 分別符合其同 runtime native-operator oracle；不要求兩版本相等。Windows `longdouble` 是 `<f8` alias，Linux/wider longdouble、其他 NumPy 1.x 版本及其他平台仍未驗。詳細 hashes、full-route log 與限制見 [R020 implementation report](R020_IMPLEMENTATION_REPORT.md)。因此 `TMP-NUM-01`、`TMP-REC-04` 仍 `ACTIVE`，R020 為 `IN_PROGRESS`、C2 未放行、R028 `BLOCKED`。
- R020 維持 `IN_PROGRESS`；`TMP-REC-04` 與 `TMP-NUM-01` 維持 `ACTIVE`，C2／full V-REPLAY parity 尚未通過，R028 維持 `BLOCKED`。Stage A/B 的 bounded receipts 不改變其他 gate。

既有 Research Run Registry 的 metadata、equity、trades 與 replay-lineage sidecar 仍保留原責任。新 sidecar 保存 DTO 重建目前缺少的原始結果欄位，包括各日期 snapshot 及 v1 recommendations、holdings、cash／contributions、diagnostics、improvement hints、details 與其餘 DTO 欄位。保存與讀回須把此 sidecar、Registry run identity 及該 run 的 metadata／equity／trades artifact descriptors 綁定；驗證原始 bytes SHA-256 及 canonical payload hash。sidecar 依 Registry 現有 staging、commit、readback 與 reconciliation 流程發布。

## 相容性與 fail-closed 契約

- 舊 `RecommendationPortfolioRunRepository` JSON bytes、schema、decoder 及 legacy history dropdown 原樣保留。不得雙寫到舊 repository，也不得以重新執行 replay／portfolio 計算代替讀回。
- 新 Registry portfolio run 使用 Registry 專屬的保存與讀取入口；不能把 Registry `run_id` 當成 portfolio replay parent 或舊 repository run ID，也不能將新 Registry run 塞入 legacy dropdown。
- 每筆新 Registry portfolio result 必須明示完整 portfolio-result sidecar 為必備；一般 Registry run 不需新增此欄位。新 portfolio result 的必備標記存在但 sidecar 缺失、schema 未知、run／parent／artifact identity 不符、raw SHA 或 canonical hash 不符時，完整 DTO reader 一律 fail closed，不回傳部分或重算 DTO。
- 舊 Registry run 若沒有新 sidecar contract marker，仍可經既有入口讀取 metadata／equity／trades；其完整 portfolio DTO 狀態明示為 unavailable，不推測或重建遺失欄位。
- 若 sidecar 聲明 canonical replay lineage，完整 DTO＋lineage reader 必須驗證該批所有 R012 child 實際 bytes、hash、日期與 parent/reference identity。任一 child 缺失或損毀時整份 strict readback fail closed，且不得將未驗證或部分驗證的 child 附回 snapshot。若保存時已明示 `lineage unavailable`，DTO 可按已保存的 v1 result data 讀回，但不得合成 child。
- Registry sidecar 與 R012 child artifact 是兩個儲存邊界。依 Registry staging／commit／reconcile 管理 Registry 內的一致性；不得宣稱 Registry 與 R012 間存在原子交易。跨 store recovery 仍須獨立測試與 gate。

## 依據與 R020 邊界

R020 原 `ALLOWED SCOPE` 明列 Replay/DataFrame provider、replay policy/input adapter、Snapshot projection 及 portfolio integration tests，但未明列 Registry repository sidecar、metadata finalize、完整 DTO reader、Registry 專屬 UI 入口或操作手冊；本 addendum 明確新增以上窄幅整合範圍，不把它說成原 task 已隱含授權。R020 其他原 scope、compatibility requirements 與 parity gates 均保留。新重算使用新的 identity/version；舊歷史仍走 legacy 保存路徑。新 Registry run 使用獨立讀取入口，不更改 legacy JSON 或既有 history dropdown。

本設計遵循 FINAL_TARGET_ARCHITECTURE 的版本化 artifact、明示 schema revision、未知版本拒絕完整 decode、保留原始 bytes/hash 與目前 extension/manifest 邊界；並遵循 FINAL_DATA_FLOW 的 create-only、同 ID 同內容可重試、不同內容拒絕及 crash reconciliation。Registry metadata hash／manifest descriptor 的發布採下列 guarded staging-only finalize：

1. 先以既有流程建立 `staging/pending` Registry row，並寫出 equity、trades 與 portfolio-result sidecar 的 staging bytes；從 Parquet temp bytes 計算 raw SHA-256，由 sidecar codec 提供 sidecar 的 canonical payload hash 與 raw SHA-256。
2. Parquet temp bytes 與 hash 已備妥後，repository 以單一 transaction 做 compare-and-set：只有 row 仍為 `staging/pending` 且現有舊 `payload_hash` 等於本次預期值時，才一次固定 `data_manifest_json`、finalized metadata `payload_hash` 及 sidecar descriptor。舊 hash 或 state 不符、transaction 影響列數非一時必須拒絕，不得部分更新。
3. 上述 finalize transaction 成功後，才允許轉入 `files_ready`、發布檔案並走現有 commit／reconciliation 流程。`committed` 後 descriptor、manifest 及 payload identity 不可再改。
4. 若在 finalize 前後仍處於 `staging/pending` 時崩潰，只有在確認沒有 live writer 後才執行 reconciliation，並將該 run 標為 failed；完整 DTO reader 不提供該 run 的完整結果。`reconcile_incomplete_saves` 是顯式操作，不能與 active writer 併行：競賽時 live staging row 可能被 fail closed，系統沒有 lease／writer liveness coordination。不得從記憶體重算 manifest 或用尚未發布資料補成完整讀回。

此順序以已寫出的 artifact bytes 為 hash 依據。沒有證據支持先在記憶體預先組完最終 metadata/hash 後才寫 Parquet，故不採此作法；也不改用 DataFrame canonical digest 取代實際 Parquet／sidecar bytes hash，該 hash 契約未驗證。新增 sidecar 是 Registry integration contract，並非擴張純 evaluator 的職責。

## 分階段 owner、檔案與測試 gates

以下是實作分派建議；實際檔案所有權須在每階段開始前確認，不能覆蓋其他 owner 的 shared hunks。所有 QA 僅用 synthetic fixture、fresh TEMP 與 `PROFILE=test`，不讀寫正式資料。

| 階段 | Owner | 預期範圍／候選檔案 | 必過測試 gate |
|---|---|---|---|
| A. DTO sidecar contract／codec | R020 application artifact owner | 新增獨立 codec／contract，例如 `app_module/recommendation_portfolio_result_artifact.py`；以 `app_module/recommendation_portfolio_dtos.py` 的現有 DTO 欄位作來源。除非另行裁決，不改 legacy `to_dict`／`from_dict` bytes 或語意。 | 對完整欄位、空 portfolio、多 snapshot、v1 row 順序、holdings、cash、contributions、diagnostics、hints、details 做 roundtrip；canonical UTF-8 bytes/hash 穩定；未知 schema、缺欄／錯型別、重複或矛盾 identity、byte tamper 與 canonical-hash tamper 均拒絕。 |
| B. Registry 保存與發布（B1/B2 bounded `ACCEPTED_SCOPE`；非完整 DTO reader） | Research Run Registry persistence owner | `app_module/research_run_service.py`、`app_module/research_run_repository.py` 及必要的 Registry artifact/manifest adapter；sidecar descriptor 綁定 Registry run／portfolio identity、schema/revision、相對路徑、sidecar 實際 temp bytes raw SHA 與 canonical payload hash，並驗既有 metadata/equity/trades artifacts。Repository 有獨立 guarded staging-only finalize command。 | 已接受明示 `portfolio_result` 的 opt-in marked path：先寫 Parquet／sidecar temp bytes 並計其 hashes；row 仍為 `staging/pending` 時，以單一 transaction 比對 expected old `payload_hash`，並一次寫入 `data_manifest_json`、finalized metadata `payload_hash`、sidecar descriptor；成功後才 guarded 轉 `files_ready`、發布並驗證。B1/B2 已 bounded accepted，不等於完整 DTO materialization／child 附回。reconciliation 僅可在 writers quiescent 後執行；Stage C reader／Stage D UI 與 Manual 現均已 bounded `ACCEPTED_SCOPE`，完整 cross-store process-crash／child-missing recovery 仍未完成。舊無 marker run 維持舊 metadata 行為。 |
| C. Registry 專屬 strict reader／重啟讀回 | 新 Registry portfolio read-service owner；R020 persistence owner 配合 | 新增 Registry portfolio-result reader（可獨立 app service），從 Registry metadata、equity、trades、portfolio-result sidecar 直接建 DTO；呼叫既有 lineage verifier 驗 R012 child。不得呼叫 replay provider、portfolio calculation 或現況資料來源。 | 以全新 service/repository instance 讀回；逐欄與保存 DTO 精確比對及欄位順序比對；在 provider/replay/service 被設為「若呼叫即 fail」時仍成功；新 run marker 下缺 sidecar、未知 schema、錯 hash、artifact cross-binding mismatch fail closed；舊無 marker 只回既有 metadata view／DTO unavailable；declared child 全批驗證成功才附回，單一 child 損毀時全份 strict DTO＋lineage readback 失敗且零 child 附回。 |
| D. Registry 專屬 UI 入口與 Manual | Qt Backtest／Registry UI owner；Documentation owner | `ui_qt/views/backtest_view.py` 或專屬 Registry result view，以及 `docs/07_guides/APPLICATION_MANUAL.md`；新增 Registry run 選擇／開啟入口，不重用或擴張 legacy portfolio history combo。 | 新 Registry run 由專屬入口重啟後讀回完整 DTO；Manual 說明入口、保存／讀回限制與 unavailable／fail-closed 狀態；legacy dropdown 僅顯示舊 repository records；舊 JSON bytes/readback 不變；Registry save 不雙寫 legacy repository、不誤設 legacy current run ID。 |
| E. 獨立高風險 review 與整合 gate | 非實作者的另一位 Luna reviewer；root 作最終 gate | 對 frozen source/test SHA 的 codec、Registry staging/readback、strict child verification 及 UI route 做唯讀 review。 | 完整 v1/R005 同 mode golden；snapshot order、holdings、cash、contributions、equity、trades、summary、diagnostics/hints/details；empty/error dates；future/cutoff/PIT；factor-manifest consumer；sidecar與child tamper／missing／reconcile；legacy decoder/dropdown regression；restart readback及跨 store failure recovery。只有每項證據通過後才由 root 決定是否擴大 R020 gate。 |

實作者不可同時充當此高風險 sidecar/readback gate 的獨立 reviewer。任何階段若 DTO 欄位來源、canonicalization、identity binding 或跨 store failure semantics 無法由既有合約證實，先回報架構差異並停在該階段，不得臆造舊資料或放寬驗證。

## 非目標與狀態限制

- 此 addendum 不驗收 C2、full V-REPLAY、R005 exact parity、完整多 runtime numeric parity 或 `TMP-REC-04` retirement。
- 不改 replay/filter/scoring/portfolio trading、cost、holdings 計算，不修改 R012 child schema，不改舊 portfolio JSON serializer、decoder 或 dropdown。
- 本段只記錄 Registry portfolio bounded gates，不代表 R020、V-REPLAY parity、完整 cross-store recovery 或正式資料遷移已完成。Stage C DTO reader/materialization 與 declared R012 child readback、Stage D BacktestView 專屬 UI／Manual 均已 bounded accepted。只有明示 `portfolio_result` 的呼叫建立 marked run；既有 markerless Registry runs 不補算、不回填。
- R020 整體狀態仍以 [R020_IMPLEMENTATION_REPORT](R020_IMPLEMENTATION_REPORT.md) 為準；本 addendum 只記錄核准的 scope 與實作 gate，不改其 `IN_PROGRESS`、`TMP-REC-04 ACTIVE` 或 `TMP-NUM-01 ACTIVE` 狀態。

## 參考

- [R020 task](../REFACTOR_TASKS/R020.md)
- [FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md)
- [FINAL_DATA_FLOW](../FINAL_DATA_FLOW.md)
- [R020 implementation progress](R020_IMPLEMENTATION_REPORT.md)

## 更新記錄

- 2026-09-24：先記錄 Stage A、Stage B1 與舊版 B2 bounded receipts（當時 Stage C/D 尚未完成；BacktestView 仍走 markerless caller）。此為當時狀態，不代表最新 B2 bytes 或目前 UI 狀態。
- 2026-09-24：依 root 架構裁決，明確增補 R020 Registry sidecar／guarded staging-only manifest finalize／strict reader／Registry UI 與 Manual scope；固定 staged bytes/hash、staging/pending guarded transaction、files_ready 與 committed 不可變順序，並排除未驗證的 memory precompute／DataFrame digest 方案。未修改程式、測試或既有 R020 task／報告。
- 2026-09-24 現況：Stage C、Stage D 均為 bounded `ACCEPTED_SCOPE`。Stage D R023 獨立 7-file fresh TEMP route `95P`、Workbench `84P`、broad mypy `712/0`、compile／diff-check 通過；Update QA 分列 R027 `25P/0F/4S` exit 0 與 R023 `25P/1F/4S`（WinError32 TEMP SQLite teardown，非功能 assertion，不計 reviewer pass）。零 snapshots 保存採 parent-bound `unavailable`、不寫空 lineage sidecar，重啟後保留空 DTO 並標明沒有 recommendation snapshots／canonical child 不可用。B2 lineage-status guard 已由 R015 獨立 bounded `ACCEPTED_SCOPE`，其 SHA／70P 證據見上方最新 B2 gate update；Stage A/B1/C receipts 不因後續 bytes 而改變。跨 store process-crash／missing-child 已有 R015 frozen test `07C2A71B…` 的 bounded evidence：3 個真 `spawn`／`os._exit` crash 點及 1 個 committed child 缺檔／同 hash 原 execution 明確重發情境，R027 獨立 7-file route `142P/3S`、mypy `7/0`、compile。這不是四個 hard-exit，也不等於完整 recovery gate；所有 partial-publish windows、跨 store atomicity／補償及原 execution 自動重建仍未覆蓋，reconcile 僅在 writers quiescent 後執行。`TMP-NUM-01` 新增 bounded runtime evidence 但 full provider/runtime parity 未驗收，具體 receipt 與 Windows NumPy 1／wider `longdouble` 環境限制見上方。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 為 `ACTIVE`，C2 未放行，R028 為 `BLOCKED`。

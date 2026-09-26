# C3／C4 relevant suite 預檢草稿（2026-09-25）

## 狀態

這是 C3／C4 的 suite 與輸入路徑規劃，不是 freeze、執行收據、R029 acceptance 或 C3 pass。本輪沒有執行 pytest、Workbench、Update validator、mypy、py_compile 或 R027/R028 fixture。Root 發出 source stable/freeze 通知前，不可把這份目前工作樹 snapshot 當正式 route。

可重跑 manifest builder：`C:\Users\archi\AppData\Local\Temp\c3c4_draft_luna_20260925_76de31a7\build_draft_manifest.py`。在 repo root 執行：

```powershell
.\.venv\Scripts\python.exe C:\Users\archi\AppData\Local\Temp\c3c4_draft_luna_20260925_76de31a7\build_draft_manifest.py
```

Builder 只重算目前工作樹的輸入 SHA，輸出至 [C3／C4 relevant suite draft manifest](C3_C4_RELEVANT_SUITE_DRAFT_MANIFEST_20260925.json)。它驗證既有 C2 manifest SHA，並在輸入缺檔或 AST parse error 時列出／停止；不執行任何測試。

## C2 base 與目前 drift

基礎是 root 已接受的 C2 manifest：`C:\Users\archi\AppData\Local\Temp\c2_luna_union_20260925_be52bcaa\manifest.json`，SHA-256 `64D7EB0FD2A7E7ED9E775562650B58E6D8B51EE5E99722785CD9EB113CDF0291`，記錄 136 tests、78 sources、HEAD `bec423eef1d9e9d4a32410dac96cd233304489aa`。本 draft 在同一 HEAD 的目前工作樹 bytes 上另記錄 230 unique tests、232 unique Python sources；比 C2 base 多 94 個去重測試路徑與 154 個 AST direct-import source paths。

Draft manifest 建立當下已有 6 個 C2 base inputs 與其原凍結 bytes 不同：

| 類別 | 路徑 | C2 SHA-256 | Draft 當下 SHA-256 |
|---|---|---|---|
| Test | `tests/test_r020_process_crash_recovery.py` | `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63` | `AEE58FA99D089DDA40D368062299871333D4BD104C477BA1B1256611BFB3A998` |
| Test | `tests/test_recommendation_service_calibration_integration.py` | `075B980B7BDC75AF9E25DAC239C1BB12167EAA10F61B25B1CDF896DF02EFA3F6` | `1D2D3CF7D289144B693D91FBE09ABB72CDF5A6650F8FECE498A6EA9CD5A24D9F` |
| Source | `app_module/recommendation/execute.py` | `A2C7FE5529AA6CC5BC72E149B503BE196EA2D99E2AC8E325DF789A7B3A05FD46` | `7B1781D1FDBFF46280494FF8705DCF4B4C1E154979DA21B4205CA757A09B3802` |
| Source | `app_module/recommendation/ml_adapter.py` | `61ED294BC577A9D68A1887DC73F357C5563F6D7D465F3FC5C97235D1DB300755` | `34B90885A0607050A788240CF202548276BC95ACEE81DF2F35E639F13D77B156` |
| Source | `app_module/recommendation_calibration_consumer.py` | `1559D1399A36C88883D1CF19AE4F7B96BE962E3F99866015FBFEBE45E9740EF5` | `6A8EC0D62103639AF36504F0EA74623B36B2C397C84B6DF63A1AFBD131E6E766` |
| Source | `app_module/recommendation_service.py` | `947BE55EA2F9A5B7B9325B6D544CD81AD97E9FDA39A9C6DC1F07932090DC8EF6` | `8F74AC2A49A371F3DA3A0A21E69C815B547F338D478EA3638390AA93301C2CA2` |

因此 C2 accepted receipt 僅代表原始 route snapshot；本 draft 的 SHA 是 planning snapshot，freeze 時必須重新讀取，不可沿用舊 C2 數字或 SHA 當作新 route 證據。94 個新增測試路徑目前全存在，分組 AST import 盤點無 parse error。各測試完整相對 POSIX 路徑、當前 bytes/SHA、bundle owner、各 bundle direct-import sources 都在 JSON manifest。

## C3 suite 與 owner 清單

分組有交集；各列 `總測試數／超出 C2 的測試數` 不可相加作為 union 總數。Draft manifest 已按 POSIX path 去重。

| Bundle | Task/source owner | 測試數／新增數 | Direct-import source 數 | Scope |
|---|---|---:|---:|---|
| `V-SCREENER` | R021；Decision stock screener、data SQLite reader/provider、受影響 Decision Desk UI | 12／12 | 24 | SQLite reader／first／provider、task-loop-02、decision providers/composition/import guard，以及 R021 affected UI batch。 |
| `V-REGIME` | R022；RegimeService、market regime provider、walkforward、regime presentation | 19／13 | 71 | kernels/detector/provider、多日/cooldown state、walkforward history/source changes、R019 regime parity 與 focused UI。 |
| `V-FACTOR` | R023/R024；factor contracts/adapters/registry/gate、fundamental/revenue/statement/valuation | 44／44 | 48 | R023 monthly-revenue regression、R024 20-module statement/valuation route、factor registry/gate/cross-sectional packs 與相應 CLI/guards。 |
| `V-STRATEGY` | R025；decision strategy registry、Backtest/optimizer/walkforward、strategy-list UI | 16／16 | 42 | spec/params roundtrip、strategy lifecycle/screening、threshold modes、Backtest/parallel、optimizer/walkforward 及 affected UI。 |
| `V-BOUNDARY` | R030；narrow import/schema/state/mapping guards；新 R030 fixtures 尚未交付 | 10／10 | 10 | ML shadow/direct、indicator registry、screening、fundamental dependency 與 workbench read-only boundary。R030 三項 synthetic extensibility fixtures 後續再加。 |
| `V-OLD-ARTIFACT-CLASSPATH` | R006/R026；historical ABI、controlled artifact loader、manifest、Direct checkpoint provenance | 13／6 | 20 | Controlled fixture 的 historical feature/class-path、old loader/manifest 與 Direct checkpoint/recovery。不能以它宣稱正式未知模型相容。 |
| `R026-NEW-TESTS` | R026；prepared runtime、snapshot custody、revision evidence、capability、prospective row evidence | 19／3 | 30 | 現有全部 `test_r026_*.py` 加 `test_prepared_runtime_input.py`；C2 已含其中 16 個。R026 仍為 `IN_PROGRESS`。 |

新增測試按路徑去重共 94 個，與 136 個 C2 base 合成 230 個。除 base 原 78 個來源外，JSON 額外擷取上述新／擴大 suites 中測試 AST 直接 import 的 154 個 source paths；232 個 sources 的逐檔 SHA 與 bundle owner 均列於 manifest。此直接 import 清單供 freeze 前核對，不宣稱完整 runtime dependency closure。R015 已退休的 `tests/test_recommendation_save_coordinator.py` 不重加；C2 已包含 R019 scheduled cutoff 與 UI run registry compare，R020 40-test route 也已在 C2 136-test base 中。

## Boundary baseline 分帳

R006 歷史記錄的四個 app→ML import failure 與本次 shadow guard residual 必須分開。前者目前已由 exact `module:symbol` guard entries 覆蓋，不再計入現在的 11 個 diagnostics：

1. `app_module/personalization_projection.py` → `ml_module.recommendation_inference_provenance:read_inference_projection_receipt`
2. `app_module/personalization_save_adapter.py` → `ml_module.recommendation_inference_provenance:read_inference_projection_receipt`
3. `app_module/recommendation_calibration_consumer.py` → `ml_module.recommendation_calibration_training:RECOMMENDATION_RETURN_BASIS`
4. `app_module/recommendation_calibration_consumer.py` → `ml_module.recommendation_calibration_training:recommendation_label_contract_id`

目前 `MLShadowBoundaryGuard.inspect()` 的獨立靜態輸出是 **11 occurrences／10 distinct diagnostics／583 files**，內容及各 import site owner 見 [R026 exact allowlist QA](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)。`tests/test_ml_shadow_dependency_boundary.py` 的 fixture 正／負例 12 passed；repository-wide assertion 仍因該 11 個既有 Restated/allocation occurrences 失敗。這些 current shadow residual 不代表 R006 的前四條又失敗，也不能將 repository-wide test 記為 green。

R030 task 所述四項 Direct baseline 亦保持獨立分類，不與上述 11 個 shadow diagnostics 合併。V-ML-DIRECT／old-artifact class-path tests 只用 synthetic/controlled fixtures；R006 選定的 OOC head 與兩個 sidecarless legacy pickle class paths 仍為 unknown，不讀取或反序列化未知正式 bytes。C3/C4 只報告此限制與既有 custody，不把 unknown artifact 轉成新測試預設或 pass。

## C4 收口次序與禁止擴張

收到 root source-stable 通知後，先以 builder 重新生成 manifest，再由 root review exact test/source paths 與 hashes；確認 frozen inputs 後才跑 full C3 route，保留 `pytest -rs` 的 skip 原因及每個 runtime 的 TEMP、log、manifest pre/post hash。C4 按矩陣重跑 C3 relevant suite，並另做 changed-Python `py_compile`、repo 指定 Workbench、`scripts/qa_validate_update_tab.py`、broad mypy（`ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`）、`V-SOURCE` 與 `git diff --check`。C2 過往 UI/mypy receipts 只能作未變更 bytes 的 continuity baseline，不能取代穩定後 mandatory gates。

R027/R028 僅依已核准隔離 fixture 範圍重跑；不執行 scheduler、正式資料、full-market ML rebuild、模型 promotion 或互動式 UI 操作。未知 serialized class paths 不載入；不將 R030 尚未交付的 fixtures 預先列為可通過測項。

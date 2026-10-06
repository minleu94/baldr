# R009 Luna 獨立審查

## 初版凍結審查

初版凍結基線為 worktree `output/agent_worktrees/refactor_r009_20260922`，HEAD `166ad745710914312ee8e2e698f230577bfb41a4`。實作者交付報告狀態為 `READY_FOR_REVIEW`。下列是我實際檢查的初版 SHA-256：

| R009 交付檔 | SHA-256 |
|---|---|
| `app_module/recommendation/codec.py` | `BC56ADC8FC4967B727A99FE61C955F46D7DD09F7592660BD750B0349D3A701D0` |
| `app_module/dtos/__init__.py` | `FAF14BF53E005F82ED2A8B97697549C74FDA2D2CD695E97F934CBA5FC0BE365B` |
| `tests/test_recommendation_execution_codec.py` | `406D409D139F2AB03B87D3B00FF39F20997CF4D883EB9C5A601739B2F6AFF5DF` |
| `REFACTOR_REPORTS/R009_IMPLEMENTATION_REPORT.md` | `E3363B00D19D018028F4625C90551C3CEE4254907D851EA0FB2325FF4DE84125` |

### 凍結依賴 SHA

下列 13 個共用依賴及額外的 R004 characterization 測試均與 `WAVE3_DISPATCH_BASELINE.md` 一致。

| 凍結依賴檔 | SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `data_module/__init__.py` | `D05D5275D2A4453FC4CF86B8F2D99FE611AEC98F610C58A8D63BA289A8825537` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `data_module/contracts/__init__.py` | `C36C0AAB8805F98B9FCEABCF48BABDF68587704D0AB261CE1E2A9580E2860FE6` |
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `app_module/recommendation/contracts.py` | `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63` |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |
| `tests/test_recommendation_contracts.py` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA` |
| `tests/test_r008_decision_numeric_enum_rework.py` | `74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `tests/test_r004_recommendation_persistence_characterization.py` | `F7F9F5E34CB9653511E4B2BC4A7280CFCCECD0F9A54BB3F54D153972F4A1E321` |

### 實際變更範圍

- 新增唯一 schema-driven codec、歷史 decoder 與 focused tests。
- `app_module/dtos/__init__.py` 僅將 `RecommendationDTO.to_dict/from_dict` 改為延遲委派至具名 legacy codec 函式；舊英文／中文輸入欄位、中文輸出鍵、校準資料和 subclass 呼叫路徑有對應測試。
- 沒有加入 repository、SQL、save caller、ML producer、UI 或 writer 變更。
- 四個 R009 檔案均核對上述 SHA；13 個共用依賴及 R004 characterization test 均符合凍結基線。worktree 的 staged index 為空。DTO 整合必須套用方法範圍窄 patch，保留主工作樹換行格式。

### 獨立驗證

在 R009 worktree 以主 repository 的虛擬環境執行：

```text
python -m pytest tests/test_recommendation_execution_codec.py tests/test_r004_recommendation_persistence_characterization.py tests/test_recommendation_dto_roundtrip.py tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py -q -o addopts= -p no:cacheprovider
```

結果為 **96 passed**。兩個 R009 source files 的 focused mypy 通過；三個變更 Python files 的 `py_compile` 通過；tracked diff `git diff --check` 及新增 codec/test 的 trailing-whitespace 檢查通過。

### 必須回修的發現

**R009-F1 — 目前版本 guard 拒絕同 major 的舊 additive revision。** `app_module/recommendation/codec.py:586` 在先前 revision 已通過 `_SUPPORTED_SCHEMA_REVISIONS` 範圍檢查後，仍要求 `revision == EXECUTION_SCHEMA_REVISION`。我以唯讀 monkeypatch 模擬 root revision 從 1 增至 2，建立 revision 1 artifact，移除具 default factory 的 optional `events` 欄位並重算該 artifact 的 canonical hash。decoder 在該 guard 回報「reader revision 與目前 contract revision 不相容」，沒有使用 default factory 解碼。

這與 `FINAL_TARGET_ARCHITECTURE.md` §6.1 的同 major 舊 artifact 缺少新 optional 欄位時使用 contract default 的規則不符，也違反 R009 對 revision dispatch 與 additive optional field 的驗收條件。初版測試僅在目前 revision 為 1 時拒絕 revision 2，未模擬「目前 revision 為 2、輸入 revision 1」的相容路徑。實作報告稱接受 1 至 current revision，但此 guard 實際上只接受 current revision。

要求回修：讓 decoder 依明確支援的同 major revisions 接受舊 revision，並對缺少的 optional 欄使用契約 default；增加目前 revision 2 讀取 revision 1 缺欄 artifact 的回歸測試，同時保留未知／不支援 revision 的拒絕測試。不得放寬未知 schema 或未列支援 revision。

初版已修正的 metadata 與 legacy raw-hash 順序問題不列為 finding：本次凍結 SHA 已移除 artifact 內可變 metadata，bytes-level legacy dispatcher 也要求先提供並驗證 raw SHA。

初版狀態：`CHANGES_REQUIRED`。實作者已回修 R009-F1，以下記錄 v2 獨立複核；v2 尚有新的落點 finding，故仍不得把初版或 v2 標為 PASS。

## v2 回修版獨立複核

v2 worktree HEAD 仍為 `166ad745710914312ee8e2e698f230577bfb41a4`。重新核對的 SHA-256：

| R009 v2 交付檔 | SHA-256 |
|---|---|
| `app_module/recommendation/codec.py` | `83FADAC5A76A90709FF374A3E35ADCFE3E2B5AEEF4BCE08D8F2404DF047F0E33` |
| `app_module/dtos/__init__.py` | `FAF14BF53E005F82ED2A8B97697549C74FDA2D2CD695E97F934CBA5FC0BE365B` |
| `tests/test_recommendation_execution_codec.py` | `C1EEEE21AF9E7EA332453D0A89E20C8025D145E742ABD4CC3B334B674B734917` |
| `REFACTOR_REPORTS/R009_IMPLEMENTATION_REPORT.md` | `4CAFAE4742C70B0318E3247039A8C276F37C42AB84E1DDB6E3302EEB69062799` |

R009-F1 的 current-only guard 已移除。新增測試在隔離的 monkeypatch 中將 current revision 設為 2，並確認 revision 1 缺少 optional `events` 欄時會以契約 default 還原；未知 revision 測試仍拒絕在 current=1 時出現的 revision 2。獨立重跑同一 7 檔 focused bundle，結果 **97 passed**。Focused mypy 2 files、三個變更 Python files `py_compile`、`git diff --check` 與新增檔 trailing-whitespace 檢查皆通過。13 個 common dependencies 和 R004 characterization test 的 SHA 再次與 Wave 3 baseline 相符。

### 仍需處理的發現

**R009-F2 — supported revision 範圍未放在權威 contract。** `FINAL_TARGET_ARCHITECTURE.md` §6.1 明確要求 `EXECUTION_SCHEMA_REVISION` 與支援 revision 範圍固定定義於 `app_module/recommendation/contracts.py`。v2 僅在 `codec.py` 定義 `_SUPPORTED_SCHEMA_REVISIONS = range(1, EXECUTION_SCHEMA_REVISION + 1)`；`contracts.py` 目前只有 `EXECUTION_SCHEMA_REVISION = 1`，沒有明示支援集合。雖然此衍生範圍可通過 v2 additive-revision 測試，仍未符合架構指定的 schema ownership 落點，也讓格式相容政策不由 root contract 明確擁有。

依 SOL 架構裁決，最小回修是在 app recommendation contract 加明示的 supported revision tuple（目前 `(1,)`），codec 匯入並使用該 tuple；不改 schema fields、contract validator、wire shape 或既有 R008 行為。該變更會改變 R008 dependency SHA，整合前須重驗 R008 contract 範圍並同步 R010 dependency。

v2 狀態：`CHANGES_REQUIRED`，等待窄 scope addendum 與新版凍結 SHA；新版需重新驗證 contract、codec、測試、依賴與結果。

## v3 窄範圍 addendum 最終獨立複核

實作者通知 v3 已凍結；本次只讀取 worktree `output/agent_worktrees/refactor_r009_20260922`，HEAD `166ad745710914312ee8e2e698f230577bfb41a4`。我重新計算以下交付檔 SHA-256，均與實作者通知相符：

| 凍結交付檔 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81` |
| `app_module/recommendation/codec.py` | `A1BC97DE557C58FCAA039D06DAE909123A3E405B5E2DD7776B94F9A80ED653BE` |
| `app_module/dtos/__init__.py` | `FAF14BF53E005F82ED2A8B97697549C74FDA2D2CD695E97F934CBA5FC0BE365B` |
| `tests/test_recommendation_execution_codec.py` | `3E6BDE7EF1594E55F2F4FC5A5F0BB9AF781BBC645EF6C666DAB686C217D4E9BF` |
| `REFACTOR_REPORTS/R009_IMPLEMENTATION_REPORT.md` | `F8C1F2A1C11F0B7DFC5CAA00E8EEBDBF38BA68A01C466DEBC9A0A55AF84D087F` |

### 依賴 SHA 與 addendum 範圍

我逐檔重算了 13 個 Wave 3 common dependencies 與額外的 R004 characterization test。12 個未變更 common dependencies 和 R004 測試都符合 `WAVE3_DISPATCH_BASELINE.md`：

| 未變更凍結依賴 | SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `data_module/__init__.py` | `D05D5275D2A4453FC4CF86B8F2D99FE611AEC98F610C58A8D63BA289A8825537` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `data_module/contracts/__init__.py` | `C36C0AAB8805F98B9FCEABCF48BABDF68587704D0AB261CE1E2A9580E2860FE6` |
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |
| `tests/test_recommendation_contracts.py` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA` |
| `tests/test_r008_decision_numeric_enum_rework.py` | `74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `tests/test_r004_recommendation_persistence_characterization.py` | `F7F9F5E34CB9653511E4B2BC4A7280CFCCECD0F9A54BB3F54D153972F4A1E321` |

`app_module/recommendation/contracts.py` 在 Wave 3 baseline 的 SHA 為 `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63`，本次 SHA 為 `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。與 baseline 的行尾正規化 diff 只有 addendum 明許的一行：`SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)`。codec 從 owner contract 匯入並使用該 tuple；schema fields、R008 validators、parent exports、既有 R008 golden/test contract 均未改。R008 contract/import 與 decision tests 已納入獨立 focused suite 並通過。

### 回修確認與獨立驗證

- R009-F1 已修正：codec 不再強制輸入 revision 等於目前 revision。回歸測試模擬 current revision 2、支援 `(1, 2)`，並確認舊 revision 1 缺少 optional `events` 時由 contract default 還原；未知 revision 仍被拒絕。
- R009-F2 已依核准的窄 scope addendum 修正：supported revision tuple 現由 `app_module/recommendation/contracts.py` 明示擁有，codec 僅消費此契約設定。
- 我按 R009/R004/R008/R007 派工組合獨立重跑 codec、R004 persistence characterization、R008 contract/decision/import、R007 market/data module 測試：**101 passed**。
- 額外加入 `tests/test_recommendation_dto_roundtrip.py` 的擴充套件也通過：**104 passed**。
- 對 codec、recommendation contracts、DTO 三個 source files 執行 focused mypy：`Success: no issues found in 3 source files`。
- 對四個變更 Python files 以 `compile(..., 'exec')` 做不落地語法編譯：通過；`git diff --check` 無 whitespace error。

我檢查了新格式遞迴欄位 schema、Decimal/date/aware datetime/enum/tuple/mapping 編解碼、canonical bytes/hash、未知 schema/type 拒絕、舊中英文 DTO 相容、legacy bytes 先驗 raw SHA 的順序及 DTO 延遲委派範圍。metadata 不在 immutable artifact bytes 中；此任務沒有新增 writer、repository、SQL、ML producer、UI 或 numerical projection 變更。沒有發現未解的 R009 acceptance finding；R008 shared contract 的唯一差異受 addendum 明確授權，且相關測試通過。

最終凍結版狀態：**PASS**。

REVIEW_STATUS: PASS

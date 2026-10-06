# PIT 產業來源與 caller 驗收 QA（2026-09-15）

## 驗收目的

本輪驗證的是「已通過 custody gate 的 prospective PIT membership，能否被真實 Industry／Recommendation／Decision Desk caller 消費」。`prospective accepted` 只代表指定 cutoff 的可重驗來源可用，不代表 historical backfill、formal OOS、promotion 或 real-money eligibility。

本輪沒有啟動正式 pipeline、scheduler、下載來源或寫入 production SQLite；既有使用者未提交變更保持原狀。

## 實作邊界

- 新增唯讀 `data_module/pit_sector_membership_reader.py`：驗證 sidecar envelope、rows/canonical hash、官方 raw bytes、source registry、clock manifest、score-bearing universe identity、taxonomy source bytes、effective／available cutoff、市場 scope 與同日衝突。
- `PITMembershipReadResult.usable` 與 `industry_filter_usable` 分離。membership 可讀不等於產業 filter 已具備可證明 taxonomy；Industry／Recommendation 只有在 `industry_filter_usable=True` 時才可用產業分類。
- current daily taxonomy 使用 `pit-industry-taxonomy-identity.v3` + `pit-industry-taxonomy-source.v2`，並由 raw manifest 綁定 classification/security component bytes。TWSE target definition 可由 `official_twse_b1212_composite_rederived` 的 B12.00 base、2023 change notice、B12.13 bounded history 與 current-regulation cross-check 重算，safe boundary 為 `2026-05-01`；B12.13 的 `115/12` 只作 history-only future evidence。identity 的 `source_hash` 必須等於 reader 重新計算的 source file bytes hash，`schema_version`、market-scoped classification/security source id/version、`available_at` 與 `effective_from` 都獨立驗證；PDF classification 的 `effective_from` 還必須有 `effective_date_basis`／`effective_date_evidence`，不能把 HTTP／頁面更新日當適用日；事後產生的 taxonomy 不可回填成 cutoff 當時已知。既有 v2/v1 fixture 結果仍保留作 compatibility evidence，current source／applicability QA 以 [PIT taxonomy daily source QA](./PIT_TAXONOMY_DAILY_SOURCE_QA_2026_09_15.md) 為準；目前完整 research chain 仍因 `5371` exact company join blocked，沒有 accepted full sidecar。
- `TWStockConfig` 提供 opt-in path／env entry points；composition root 只建立一個 reader，並注入 IndustryStrengthService、RecommendationService 與 non-UI Decision Desk factory。
- `formal_rule_source_producer` 將既有已計算的 integer `scores_bp` 與實際 hash input 的 `universe_hash_symbols` 一併保存到新產生的 universe identity，使後續 reader 能重建 score-bound universe hash；未修改既有正式 artifact。

## Evidence 與 custody 邊界

### 既有 D 槽 artifact 的唯讀 smoke

只針對 `TWStockConfig` 預設 data root 下的候選 output 做了讀取與 hash 檢查。既有 prospective sidecar 的兩個官方 raw bytes 以 `Get-FileHash -Algorithm SHA256` 核對，並與 final manifest registry 一致：

- `tpex_t187ap03_O.raw.json`：`sha256:4f055c3c035d84c75b299211f36ef2dbe01b700c58c2115aeb6630c7628ce835`
- `twse_t187ap03_L.raw.json`：`sha256:9e6f88f30420552e435951193dc44094d726412c8d917d8a975581d8ae083c97`

reader 對該既有 artifact 的結果是 `status=unavailable`、`universe_verified=false`、`taxonomy_verified=false`，原因包含既有 universe identity 沒有 `scores_bp`，且沒有可驗證 taxonomy source。這是 fail-closed 結果，不把 self-declared identity 當作 custody 證明，也不把目前公司 registry 當歷史分類。

### 隔離 positive artifact

測試 fixture 以既有 `build_official_first_seen_capture` 產生 official raw／source registry，再以既有 `capture_prospective_pit_sector_membership` 產生 sidecar；clock、score-bearing universe identity、taxonomy identity/source 則明確放在同一個隔離 bundle，並由 reader 重新驗證。

taxonomy source 使用 `fixture:*` source id，代表測試 custody contract，不宣稱 TPEx/TWSE 官方 taxonomy、正式授權或歷史回填。它的用途是證明 caller wiring 與 hash／時間／分母 gate；正式環境仍須提供可追溯且具授權的 taxonomy source file。

## 驗收矩陣

| 面向 | 驗收情境 | 預期／實際結果 |
|---|---|---|
| cutoff | `00:30Z` 與 `08:30+08:00` 同一 instant | normalize 後結果一致；as-of 晚於台北決策日 fail-closed |
| raw custody | raw bytes hash、official canonical rows hash、symbol/sector 對應 | 通過才可進 accepted |
| clock | `clock_id`、manifest hash、universe hash 綁定，並重新載入 clock manifest | mismatch／無法驗證即 unavailable |
| universe | symbols、candidate count、score vector、score-bound hash、rows coverage | 缺 scores、symbols tamper、scores tamper、空 identity、錯 schema 均不可 accepted |
| taxonomy | source bytes hash、source schema value、classification/security provenance、available cutoff、effective date | 假 source hash、錯 source schema、future available_at、未知 code、部分 denominator 均不可 `industry_filter_usable` |
| scope/conflict | TWSE／TPEx 不重疊市場分開選取；同 market 同日不同內容 | 前者可依 requested scope 消費；後者 fail-closed，不被 candidate 或其他 market 遮蔽 |
| candidate | machine publication 保持 candidate-only | 不會升格成 accepted |
| Industry caller | current companies registry 故意反置，PIT taxonomy 指向 2330 | semiconductor 成分只含 2330，分母為 `accepted_pit_membership_rows` |
| Recommendation caller | 透過 `TWStockConfig → build_decision_service_composition → RecommendationService`，cutoff 產業 filter | 真實推薦服務的 PIT 篩選路徑只把 2330 送入隔離的 strategy output stub；未驗證 taxonomy 不回退 current mapper，直接記錄 missing evidence |
| Decision Desk | Sector rotation 使用 IndustryStrengthService | `source_lineage.sector_rotation.metadata.pit_membership` 保留 accepted／taxonomy lineage，`historical_pit_eligible` 仍為 false |

## 已執行 QA

```text
.\.venv\Scripts\python.exe -m pytest tests/test_pit_sector_membership_reader.py -q -o addopts=
9 passed

.\.venv\Scripts\python.exe -m pytest tests/test_pit_industry_callers.py -q -o addopts=
7 passed

.\.venv\Scripts\python.exe -m pytest tests/test_pit_sector_membership_machine.py tests/test_pit_sector_machine_publisher.py tests/test_formal_machine_consumer_integration.py -q -o addopts=
16 passed

.\.venv\Scripts\python.exe -m pytest tests/test_prospective_official_pit_source.py tests/test_prospective_pit_sector_membership.py tests/test_formal_rule_source_producer.py tests/test_decision_service_composition.py tests/test_decision_desk_builder_factory.py tests/test_sector_rotation_service.py tests/test_recommendation_ranking_service.py -q -o addopts=
66 passed

.\.venv\Scripts\python.exe -m py_compile data_module/pit_sector_membership_reader.py data_module/config.py data_module/formal_rule_source_producer.py app_module/industry_strength_service.py app_module/recommendation_service.py app_module/decision_service_composition.py app_module/decision_desk_composition.py app_module/decision_desk_builder_factory.py tests/pit_test_support.py tests/test_pit_sector_membership_reader.py tests/test_pit_industry_callers.py

.\.venv\Scripts\python.exe -m mypy data_module/pit_sector_membership_reader.py data_module/config.py data_module/formal_rule_source_producer.py app_module/industry_strength_service.py app_module/recommendation_service.py app_module/decision_service_composition.py app_module/decision_desk_composition.py app_module/decision_desk_builder_factory.py --show-error-codes
Success: no issues found in 8 source files

.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime --show-error-codes
Success: no issues found in 619 source files
```

pytest 僅出現既有 `.pytest_cache` 權限 warning，未造成測試失敗；repository 全域 mypy 亦已通過。下一階段若要把 caller 連到正式日常資料，必須先提供正式 taxonomy source 的產製／授權／availability contract，並另行完成 historical／formal gate；本輪不宣稱已完成。

## Config entry points

`TWStockConfig` 可用 constructor kw-only fields 或對應環境變數設定：

`PIT_SECTOR_MEMBERSHIP_PATH`、`PIT_SECTOR_MEMBERSHIP_RAW_ROOT`、`PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH`、`PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH`、`PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH`、`PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH`、`PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION`、`PIT_MARKET_SCOPE`。

未設定 artifact path 時不掃描資料根目錄，也不會因組合服務而自動建立 PIT reader。

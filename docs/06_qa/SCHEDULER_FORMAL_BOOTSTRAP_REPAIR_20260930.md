# 排程正式輸入 bootstrap 修復：PIT taxonomy 分母綁定

日期：2026-10-01（本文件保留 9/30 基線與 10/1 更新）
範圍：Rule candidate 與官方完整 PIT 證券母體分開綁定；已實際產生 10/1 research candidate，不啟用 Formal consumer。

## 結論

Rule universe 與官方完整證券分母是兩種不同集合。驗證已保存的 2026-09-30 輸入後，Rule candidate 為 1,932 檔，官方分母為 1,988 檔，交集 1,931 檔；官方分母獨有 57 檔，Rule candidate 獨有 `5371`。因此兩者不是單向少數，而是雙向不相等；取交集會隱去 `5371`，也會丟棄 57 檔官方母體資料，不能作為修復。

新的 opt-in v2 契約保留完整官方分母與全部 Rule candidate／score 順序，並把兩方向差異、來源 bytes、日期、clock、availability 及 hash 一起綁定。官方獨有股票可取得分類／證券型別 coverage，但沒有 Rule 分數；Rule-only `5371` 保留為 diagnostics，令 `rule_scope_compatible=false`。此 v2 目前是 research candidate：publisher 不宣告正式相容，reader 拒絕正式可用，assembler 即使 sidecar 自行宣稱相容也 fail closed。

## 已保存來源的唯讀重驗

以下資料均為 repository 內既有的 2026-09-30 immutable 輸入；本輪只重讀 bytes、呼叫既有 denominator validator，並在記憶體重算 binding／set diff，沒有建立 taxonomy bundle、sidecar 或排程 receipt：

- 官方分母：[denominator.json](../../output/formal_daily_publications/pit_denominator/2026-09-30-run-e641fcac1df04d1e/denominator.json)，1,988 個 symbols，`symbols_hash=sha256:54f9836d564f996deef42410629f192361f847cf20a9ca421fba5da2c68df1b6`。
- Rule parent：[universe_identity.json](../../output/formal_daily_publications/rule_source/clock-20260930-machine-v2-6414e448ccfb-85d50c270d9a/metadata/universe_identity.json)，1,932 個 candidate，`universe_hash=sha256:2760b4cc29bb78d24287e01adc68611125999e7e82d26ec62638191d94809411`；原始完整 candidate list：[universe_symbols.json](../../output/formal_daily_publications/rule_source/clock-20260930-machine-v2-6414e448ccfb-85d50c270d9a/metadata/universe_symbols.json)，raw file hash `sha256:fe47608d0d404106f464391eb85d84a47da8268e332a5f97bdbae29fe0a87181`。
- 重算結果：交集 1,931；官方獨有 57，set hash `sha256:fda2d8682e8fdf583d0998ecf345acf70aedc3529acd5dbf57a7a5afa2136385`；Rule 獨有 1，內容為 `5371`，set hash `sha256:3978d98f1d7585399304c98cc2c583c9e8d6b176a3ef7fc56332c38705650b55`。`taxonomy_coverage_complete=true`，`rule_scope_compatible=false`。

此段是實際 capture 前的 9/30 唯讀基線。其分母與 Rule 集合差異與 10/1 新 capture 重算相符；不再代表最新 capture 狀態，也不等於正式來源接受或 clock acceptance。

## Repo 變更與相容性

- `data_module/pit_taxonomy_source_producer.py` 新增 bundle `pit-industry-taxonomy-daily-bundle.v2`、source v3、identity v4 與明示 scope binding。預設仍走原 v1，full-equality 與舊 `to_dict()` 欄位形狀不變。split binding 只接受 allowlist 欄位；空 mapping、保留欄位注入會在輸出前拒絕。驗證會重讀 denominator／Rule 原始檔案、驗證 custody/hash/date/cutoff、重算 identity/clock/source-window 與雙向差異；reference path 限定於 publication root 並拒絕 traversal／非一般檔案。
- `scripts/scheduled/run_pit_sector_membership_preopen_capture.py` 加入 `--split-denominator-contract`，預設不變。v2 taxonomy 輸出使用獨立的 `pit_taxonomy_preopen_split_v2/YYYY-MM-DD` 新目錄；Rule score/hash 順序保持來源原值。`scripts/scheduled/run_pit_sector_membership_preopen_capture.cmd` 的既有 Python 呼叫已依核准追加此 opt-in；Rule 子程序、失敗 exit code 與呼叫端環境變數優先序不變。
- `data_module/pit_sector_membership_reader.py` 保留舊 reader 語意，新增 v2 source binding 驗證，並將 taxonomy coverage 完整與 Rule scope 相容分開回報。
- `data_module/formal_pit_sector_publisher.py` 對 split v2 只在 v2 candidate root create-only 寫入 sidecar／receipt；receipt 把 coverage 與 Rule compatibility 分開回報，formal readiness／consumer compatibility 保持 false。舊 v1 receipt 不增加新欄位。
- `data_module/portfolio_ml_dataset_assembler.py` 新增 source-binding gate，並明確拒絕尚未 owner-accepted 的 split v2 preview；僅把 sidecar 的 `formal_consumer_compatible` 改成 true、`research_only` 改成 false 並重算 sidecar hash，不足以讓它通過。

舊 accepted clock、immutable archives、Task Scheduler 定義、Formal consumer pins 均未修改。沒有新增 5371 的假分數、沒有將官方 universe 塞進 ranking，也沒有把 57 檔丟掉。

## 驗證

Focused 路由：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pit_taxonomy_daily_source.py tests\test_pit_taxonomy_split_contract.py tests\test_pit_sector_membership_reader.py tests\test_formal_pit_sector_publisher.py tests\test_portfolio_ml_dataset_assembler.py -q -o addopts=
```

9/30 基線結果：92 passed。包含 v1 roundtrip／mismatch 拒絕、split allowlist／empty binding、來源缺失與 raw mutation、Rule hash／availability timestamp 缺件、wrong clock、path traversal、`5371` 雙向差異保留、reader／publisher candidate-only，以及 assembler 對偽造 formal flags 和重算 hash 仍拒絕。

10/1 最終 PIT focused route（完成實際 capture 後的 bounded saved-path hardening）如下：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pit_preopen_schedule.py tests\test_pit_taxonomy_daily_source.py tests\test_pit_taxonomy_split_contract.py tests\test_pit_sector_membership_reader.py tests\test_formal_pit_sector_publisher.py tests\test_pit_inactive_security_termination_evidence.py tests\test_portfolio_ml_dataset_assembler.py tests\test_scheduled_cmd_scripts_no_confirm.py -q -o addopts= -p no:cacheprovider
```

結果：**160 passed、2 skipped**。兩個 skip 都是 Windows token 無建立 symlink 權限：`test_split_scope_binding_rejects_linked_proof_path` 與 `test_split_saved_active_source_rejects_linked_path_before_resolving`；相應拒絕邏輯在可建立連結的環境有負控。Joblib physical-core discovery 有一項 warning，測試改用 logical-core 數繼續。六個 PIT source 的 scoped mypy 0 issues；該批所有變更 Python source／tests `py_compile` 通過；`git diff --check` exit 0。

## 2026-10-01 真實時鐘 capture：歷史失敗與最新成功

本節更新本文件先前的失敗收據。第一個官方 HTTP 嘗試在預設 sandbox 遭 Windows `WinError 10013`；核准的 PIT-only route 後續保留同一 Rule parent、既有 company archive 與 denominator，沒有重跑 Rule 或重抓這三份輸入。較早的 taxonomy attempt 因 8183 無 exact ISIN/CFI security row 而 fail closed，該失敗 status/archive 仍保留為歷史 evidence，不能被新候選說成成功。另一個經核准的 TPEx 公告 GET 已由 8183 證據 lane 獨立保存；本次新 taxonomy attempt 是重用其 raw bytes/metadata，不宣稱其為原 ISIN query response，也沒有再次 GET 公告。

本輪在實際台北時間 2026-10-01 06:08:03.7020572 啟動，06:11:44.577834 完成，早於 08:30 cutoff，未注入 clock。只對該 PowerShell process 設定環境變數，使用 repository publication root；run exit 0，status=`machine_verified_candidate`。CLI 使用 `--split-denominator-contract`、`--publication-root output/formal_daily_publications` 及唯一 `--status-root output/formal_daily_publications/scheduler/pit_preopen_capture_validation/79bf791f00bb4ded87097e1f96cc4efb`。正式排程預設 status 仍寫 `status_root/latest_status.json`；本次 isolated root 沒有覆寫 operational `latest_status.json`。

新輸入和 readback：

- 新 taxonomy：[bundle_manifest.json](../../output/formal_daily_publications/pit_taxonomy_preopen_split_v2/2026-10-01/bundle_manifest.json)，schema=`pit-industry-taxonomy-daily-bundle.v2`，bundle hash `sha256:b6fae3b2d808ae99398bb7c8c1153e8a106be05c7dbc815d696ea983eb98f4b5`。完整 1,988 rows／official denominator，其中 eligible 1,977、excluded 11、unknown 0；taxonomy coverage complete=true。
- Rule source 保留全 tuple：[universe_identity.json](../../output/formal_daily_publications/rule_source/clock-20261001-machine-v2-7e325256a5b1-85d50c270d9a/metadata/universe_identity.json)，1,932 candidates、universe hash `sha256:ab92ccecfefb4e0c38c2939d261bafbc29e3df83e9f11f02c743bc3875e343c7`。Diff 為 intersection 1,931、official denominator-only 57、Rule-only 1 個 `5371`；沒有取交集或補造分數，故 `rule_scope_compatible=false`、industry filter unusable。
- Company archive：[archive_manifest.json](../../output/formal_daily_publications/pit_candidate_archive/2026-10-01/03cd1f8a77efafe8-2730badccde8e2f9/archive_manifest.json)，1,988 rows，publication content hash `sha256:03cd1f8a77efafe8342ad8f5e3ece17429bfecd6b5d18492bffff88c2ef5b627`，manifest file SHA `sha256:36d8ca933ef5f44299a7a18381c1b9b847c4f0616400fe68655ef43f5ad73393`。本次 reuse 並未抓取或修改該 archive。
- Official denominator：[denominator.json](../../output/formal_daily_publications/pit_denominator/2026-10-01-run-b9e0e9b022b44637/denominator.json)，1,988 symbols，symbols hash `sha256:54f9836d564f996deef42410629f192361f847cf20a9ca421fba5da2c68df1b6`、content hash `sha256:a74675249df76e86ebf4c072263cbd2cdf277da4c22594e7d71cc5f5f9714e50`、file SHA `sha256:c39f22b3047e2daf8aa0294324a64ba7e2ce3b60c86a00e504c3144a9b435dc3`。本次 reuse 並未重新抓取或修改。
- 本次唯一的網路清單是來源 config 的六個 GET：TPEx classification spec、TWSE listed base definition、change notice、revision history、current regulation，以及 TWSE ISIN security list；六個皆 HTTP 200、requested/final URL 均精確符合 config URL。公司 archive、denominator、Rule source、8183 公告均 0 GET。attempt result 包含 8 個 component：上述 6 個 fetched components，另 2 個為 8183 已保存 raw 公告及 capture metadata；aggregate raw 39,167,825 bytes。attempt ID=`0207f93a9db94bb0be4e4c7e371339a7`、descriptor SHA `sha256:c670b2957510b2f52ec44d0beaff00c731b4be3e3cbeb218ed4fee5d58a3f715`、receipt SHA `sha256:df763967d79f0b10e2cb8d3ca5506f970d9750713034bc7d84e2f98b807d28d4`。完整 attempt/raw/metadata hash readback 與 v2 bundle validator 均通過。
- 8183 overlay 保留官方公告 raw：[announcement.html](../../output/qa/pit_8183_tpex_termination_diagnostic_20261001/attempt_20260930T212353756235Z_authorized_retry_7c96e318/announcement.html)，HTTP 200、21,378 bytes、SHA `sha256:735e9596680ca64cf5dc5d4b77e9784493da22375bf7e2911ffae750c0e01d47`；proof capture=`2026-09-30T21:23:55.086807Z`，在 cutoff 前。只證明 `8183` 是 TPEx 已終止普通股：`eligible=false`、`research_only=true`、`formal_credit=false`、`historical_pit=false`、`active_security_record=false`，ISIN/CFI 均為 null；沒有建立或冒充 active `OfficialSecurityRecord`。
- 本次輸出仍是 candidate-only：`formal_consumer_compatible=false`、`formal_ready=false`、`formal_oos_allowed=false`、`promotion_eligible=false`、`training_started=false`、`writes_formal_controlled_paths=false`、`writes_source_database=false`。未改舊 accepted clock、legacy latest/status、正式 pins、Task Scheduler、D: market/source DB，亦未修改 immutable archive/denominator/Rule inputs。

Invocation／clock readback 與產物 hash 已 create-only 存於 ignored QA 子目錄：[invocation_and_clock.json](../../output/qa/scheduler_formal_bootstrap_20261001/split_v2_candidate_0207f93a9db94bb0be4e4c7e371339a7/invocation_and_clock.json)，SHA `sha256:c7abe04d9e5b1a1d5f996dad913f0b7f9a2bb82cfe68f287c1e1d0a3544b98b6`；[capture_readback.json](../../output/qa/scheduler_formal_bootstrap_20261001/split_v2_candidate_0207f93a9db94bb0be4e4c7e371339a7/capture_readback.json)，SHA `sha256:fa85978534ecf40a78d2e45c119564e0ab9a1de2a3f39049ef58a8ae16df2c32`。此候選的 custody descriptor 綁 canonical parsed config hash `sha256:f0875b47006ad6f140b780869914af26c2d72e5033c549f4d2f432594b672717`，但沒有把 source-config 原始檔 bytes 納入 attempt component；QA 另記錄該檔 raw SHA `sha256:9757c31a5b7275d810933b6671f0582150ca468b5485e69c56faad3a8056cc63` 並逐筆驗證六個實際 requested URL。這項 provenance 限制保留為 candidate research-only，不提升 Formal compatibility。

## 本輪修正、最小後續步驟與正式啟用界線

split v2 現已能以同一 cutoff 同時綁定官方完整 taxonomy/security denominator 與 Rule score-bearing candidate parent，完整保留雙向差異；denominator-only 的 57 檔只獲 taxonomy coverage，不產生 Rule score。Rule-only `5371` 留在 diagnostics 並使 scope incompatible；不能用 intersection 隱去任何一邊，也不能把官方全表塞進排名。v1 reader/schema/full-equality 行為與輸出 ABI 維持；v2 需明確 opt-in。

本輪 failed-attempt custody 限制已實作：split opt-in 下每個 planned source GET 前檢查 component 數量上限；取得 response 後、parse/coverage 前 create-only 寫 raw 與 metadata；descriptor、每個 component、terminal result、success/failure receipt 均重驗 byte/hash pins。最多 16 components、aggregate 128 MiB、每來源 64 MiB、最低 free reserve 16 MiB、每來源 timeout 30 秒。非成功/partial attempt 不作完整 proof；超限 body 不假稱完整 raw。新 `inactive_security` overlay 只接受經 raw/cutoff/readback 驗證的 termination proof，其他 active/unknown/security mapping 仍 exact-map fail closed。

新 candidate 之後可供 research-side taxonomy coverage diagnostics；不能自行改舊 accepted clock、已消費 cutoff、immutable archive、consumer pin 或可變 current-latest。若要正式 consumer 接受分離母體契約，仍需 owner 明示接受 source/license/scope，並建立新 versioned consumer acceptance/pin/clock；本輪沒有授予這些資格，也未把 candidate 當成 publisher／Formal runtime 通過。config raw-byte custody 亦需在後續 candidate schema 中明確綁定及重驗，才能關閉此 provenance gap。

# 排程正式輸入 bootstrap 修復：PIT taxonomy 分母綁定

日期：2026-10-01（本文件保留 9/30 基線與 10/1 更新）
範圍：Rule candidate 與官方完整 PIT 證券母體分開綁定；已實際產生 10/1 research candidate，並完成同日唯讀重用驗證；不啟用 Formal consumer。

## 最新狀態（2026-10-01 台北時間 07:19）

自然排程於 07:00:29 讀取既有 split candidate 時，因 late source-config proof 尚不存在而保留 `blocked` 收據；該次沒有網路請求或新 attempt。07:12:56–07:13:19 以原 saved config bytes 建立獨立、hash-addressed late proof；07:19:23–07:19:49 再以真實時鐘執行同日 research-only reuse，完整驗證既有 archive、denominator、Rule tuple、taxonomy bundle、capture attempt/raw custody 與 config proof。重用狀態為 `machine_verified_candidate`，但 `formal_consumer_compatible=false`、`formal_credit=false`、`rule_scope_compatible=false`；此結果是獨立人工 CLI receipt，不回寫或改稱 07:00 自然排程成功。

同日重用只允許同一台北自然日、真實時間早於 08:30 cutoff 且完整來源驗證通過；跨日不得拿舊 candidate 冒充新日資料。`same_candidate_reuse_prohibited=true` 的 rolling-contract 語意是禁止跨日替代新日 candidate；同日唯讀 research 重驗不修改該旗標，也不授予 Formal consumer 資格。此邊界依據 [`_rolling_contract`](../../scripts/build_formal_9_9_candidate_runtime_config.py) 與 [V4 next-formal handoff，第 216–220 行](../09_archive/V4_NEXT_FORMAL_HANDOFF_2026_09_08_HISTORY.md)。

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

新 candidate 之後可供 research-side taxonomy coverage diagnostics；不能自行改舊 accepted clock、已消費 cutoff、immutable archive、consumer pin 或可變 current-latest。若要正式 consumer 接受分離母體契約，仍需 owner 明示接受 source/license/scope，並建立新 versioned consumer acceptance/pin/clock；本輪沒有授予這些資格，也未把 candidate 當成 publisher／Formal runtime 通過。原始 06:08 attempt 建立時未將原始 source-config 檔案 bytes 作為該 attempt component，這仍是該次擷取的歷史 provenance 限制。07:12–07:13 的獨立 late proof 以 saved config 原始 bytes、canonical hash、舊 attempt descriptor／bundle／receipt linkage 與本次 materialization 時間建立 create-only cache，並在 07:19 重驗 bytes、hash 及當前 tracked config 的 source 語意；它足以支持本次同日 research-only reuse，但不回填原 attempt、不改寫 capture 時間，也不聲稱 06:08 已有原始 config-file custody。本批對新 split attempt 已加入 canonical config snapshot hash pin；該規格化設定綁定與原始設定檔 bytes／metadata custody 是不同層次。

## Late config proof 與同日唯讀重用收據

### 07:00 自然排程：保留 blocked 歷史

只讀查詢 `baldr-pit-sector-membership-preopen-capture-daily` 的 Windows Task Scheduler 狀態：工作已啟用且為 `Ready`；最後執行時間為 Windows 本機時間 `2026-09-30 16:00:01`（台北 `2026-10-01 07:00:01`），`LastTaskResult=2`；下一次排程為 Windows 本機時間 `2026-10-01 16:00:00`（台北 `2026-10-02 07:00:00`）。本輪只讀取 `Get-ScheduledTask` 與 `Get-ScheduledTaskInfo`，沒有觸發或修改 Task。

自然排程 operational receipt 位於 [latest_status.json](../../output/formal_daily_publications/scheduler/pit_preopen_capture/latest_status.json)，SHA-256=`fc92466c69171039cd3c8817e309e6642d881257dfc43710263df875fc438bb9`；`observed_at=2026-09-30T23:00:29.445303Z`（台北 07:00:29）、`status=blocked`，阻擋原文為 `existing_split_candidate_reuse_rejected:PITTaxonomySourceError:capture attempt path is missing`。該次 `network_attempted=false`、`new_attempt_created=false`。這是 late proof 缺件時的舊收據，不因後續成功而覆寫或追認為 pass。

### 07:12–07:13 late proof：create-only materialization

只使用既存 `source_config_saved_notice.json`，未發 HTTP GET。CLI 命令：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_pit_sector_membership_preopen_capture.py --publication-root C:\Projects\PythonProjects\technical_analysis\output\formal_daily_publications --materialize-existing-split-config-proof --source-config-proof-source C:\Projects\PythonProjects\technical_analysis\output\qa\pit_taxonomy_split_candidate_20261001\source_config_saved_notice.json
```

實際開始 `2026-10-01T07:12:56.1174221+08:00`，完成 `07:13:19.6220314+08:00`，CLI return code `0`。Proof root 是 `output/qa/pit_cfg_proofs/ec16e65a3bc87fbd3a27ce0a948013a9275852185c1aa4accb45db6d71401165`，僅有三個 create-only 檔案：

- `source_config.json`：3,902 bytes，SHA-256 `9757c31a5b7275d810933b6671f0582150ca468b5485e69c56faad3a8056cc63`，與原 saved config bytes 相同；canonical hash 為 `sha256:f0875b47006ad6f140b780869914af26c2d72e5033c549f4d2f432594b672717`。
- `config_proof.json`：1,783 bytes，SHA-256 `ed83281dcbd0550bad5d07d82b8af0a9eb6a77acc8e67996ee0af0e8350f70a5`；proof hash 為 `sha256:fb7a46ba3dac7e2ba306107b4d90b7b3002b545d4e2fb2fea2d60c466f009cfb`。
- `completion_receipt.json`：788 bytes，SHA-256 `36a4dc05b8e4fda511766c0d1ba5bdff33bdbf79bdc2d6dd4f988be812ff6a0a`。

Proof 明確標記歷史可得性與 historical PIT eligibility 均為 false，`research_only=true`、`candidate_only=true`、Formal flags 均為 false。Materialization run receipt：[materialization_run.json](../../output/qa/pit_late_config_proof_materialization/20260930T231256109Z_24b3231a94c349b597b3a1a6799673eb/materialization_run.json)，SHA-256=`2782e5b6e9a86fb7a3d9e31234a64dbf6cb787ebd36f7dd244c961cabe701282`；保存命令輸出的 `command_output.txt` SHA-256=`93298f00eb7d64ab8497d0553cec1692829a0ef85d201413d83c5b370544b296`。run receipt 確認 tracked/immutable 輸入無變更、attempt ID 前後同為 `0207f93a9db94bb0be4e4c7e371339a7`、attempt count 未變、未呼叫 source capture。

外層 PowerShell 驗收包裝器曾因 `-join` 與比較運算子的優先序將原值清單誤判為有差異而回傳 2；這是包裝器檢查式的 false alarm，不是 proof CLI 失敗。CLI run receipt 的 return code 是 0，三個 proof 檔在寫入後完成 bounded readback、hash 與 linkage 驗證，且 receipt 的 `changed_tracked_paths=[]`、`attempt_count_unchanged=true`；不得將外層包裝器回碼改寫成 CLI 回碼。

### 07:19 同日 reuse：isolated status、零網路、Formal false

CLI 以實際 process clock 執行，caller environment 在 finally 區塊恢復原值；publication root 使用 repo `output/formal_daily_publications`，status 使用唯一隔離目錄 `scheduler/pit_preopen_reuse_validation/e3d78970ed9b43cca69bdb8e81a7f39f`。命令為：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_pit_sector_membership_preopen_capture.py --publication-root <repo>\output\formal_daily_publications --status-root <repo>\output\formal_daily_publications\scheduler\pit_preopen_reuse_validation\e3d78970ed9b43cca69bdb8e81a7f39f --split-denominator-contract
```

實際開始 `2026-10-01T07:19:23.0491991+08:00`，taxonomy 完整驗證完成 `07:19:48.967855+08:00`，CLI 完成 `07:19:49.0972984+08:00`，return code `0`。隔離 [latest_status.json](../../output/formal_daily_publications/scheduler/pit_preopen_reuse_validation/e3d78970ed9b43cca69bdb8e81a7f39f/latest_status.json) SHA-256=`3e6209675e7ebad43f3c5d832ac2371e0197a11de69201a4bb624e27bd0324a4`；`status=machine_verified_candidate`、`capture_mode=reused_existing_split_candidate`、taxonomy status=`verified_reused_existing_split_candidate`。Reuse run receipt：[reuse_run.json](../../output/qa/pit_same_day_reuse_validation/20260930T231923020Z_3ebaaa7d63eb4bc980c465009404208d/reuse_run.json)，SHA-256=`172d17fd6464c41273abd5a78b66da268ab828d3ce8ccf2ae8e8fe5f448e476a`；保存 CLI stdout 的 `command_output.txt` SHA-256=`fc33522ac52f4016d153e35b1a8c0cb3c981c9ce769ae7506888e01008592b93`。

此為完整 existing-candidate validator 的實際 readback：既有 taxonomy bundle hash 維持 `sha256:b6fae3b2d808ae99398bb7c8c1153e8a106be05c7dbc815d696ea983eb98f4b5`，原 attempt 仍只有 `0207f93a9db94bb0be4e4c7e371339a7`；Rule full tuple、official 1,988 分母、1,988 company archive、source plan/六個 URL、原始 components 與 late config proof 都重新比對通過。實際集合仍為 Rule 1,932、official 1,988、交集 1,931、official-only 57、Rule-only `5371`；`taxonomy_coverage_complete=true` 且 `rule_scope_compatible=false`。reuse 是零 GET、零新 attempt、零 Rule/archive/denominator refresh；原 operational status SHA 前後均為 `fc92466c69171039cd3c8817e309e6642d881257dfc43710263df875fc438bb9`，immutable inputs 與 attempt count 前後未變。`formal_consumer_compatible=false`、`formal_credit=false`、`formal_ready=false`、`formal_oos_allowed=false`、`promotion_eligible=false`、`training_started=false`。

## 同日重用 glue 回歸測試與本批最終驗證

新增 focused route：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pit_same_day_reuse.py tests\test_pit_taxonomy_source_config_proof.py tests\test_pit_preopen_schedule.py tests\test_pit_taxonomy_split_contract.py tests\test_pit_inactive_security_termination_evidence.py tests\test_portfolio_ml_dataset_assembler.py -q -o addopts=
```

結果：**97 passed、1 skipped**。同日 runner positive 是窄編排/stub 測試，驗證 0 network、0 new attempt、Formal false、並且不重抓 archive/denominator；它不是端到端 validator 的替代，端到端 existing-candidate validator 已由前述實際 07:19 reuse/readback 補足。負向測試覆蓋 Rule/denominator tuple drift、跨自然日、驗證跨 cutoff、source URL/source plan mismatch，以及 proof 缺件／partial／raw mutation／canonical semantic hash mismatch 等 fail-closed 情況。唯一 skip 為 `test_split_scope_binding_rejects_linked_proof_path`；Windows 建立 symlink 回報 `WinError 1314 A required privilege is not held by the client`，所以該連結拒絕分支在此環境未執行。

`py_compile` 對 `data_module/pit_taxonomy_source_producer.py` 與 `scripts/scheduled/run_pit_sector_membership_preopen_capture.py` 通過；六檔 scoped mypy（另含 reader、publisher、assembler、inactive termination evidence）為 0 issues；`git diff --check` exit 0。pytest 顯示 Joblib physical-core 查詢無法取得硬體核心數而改用 logical-core 數，另有 `.pytest_cache` 因 Windows 權限無法寫入 nodeids 的 warning，均未影響測試結果。這些局部檢查不代表整個專案測試全綠。CLI 曾提示無權寫 `D:\Min\Python\Project\FA_Data\logs\config.log`，改走 console-only logger；本輪沒有寫入 D:。

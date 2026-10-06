# H20N01 完整 cohort 自然結果 caller

固定 base：`d222ba0dbd3e87991ba5404fec29470646af2c68`。本包僅新增 dispatch 指定的 App caller、scheduled CLI、兩份 focused tests 與本文件。原 outcome/capture/provider/hook/learning CLI/main/config/DTO/Manual/原 plan 皆唯讀。未改正式 Task、ACL、資料庫或原始資料；未執行真寫入、推論、訓練、交易、push、整合或清理。

## Frozen API 與 consumer

`run_personal_h20_natural_outcome_batch(*, manifest_path, manifest_sha256, root, input_capture_path=None, input_capture_sha256=None, outcome_path=None, outcome_sha256=None, prediction_reader, source_verifier, contract_verifier, input_capture_verifier, outcome_verifier, cancelled=None) -> Mapping` 保持 dispatch 原 signature。

App 零 ML imports。先沿 `read_personal_h20_daily_manifest` 完整 public reader 驗原 manifest raw SHA/canonical filename、1..50 完整 symbols、candidate/contract/cycle/date、sample/prediction pins；不使用 selected_stock 跳列。額外原 pinned reader 拒重複 JSON keys。每列呼原 `project_personal_current_observed_h20_outcome`，保留原 cycle/terminal/snapshot/symbol/decision/features/capture_row_id 配對及官方二十 session verifier。

所有列先 `persist=False` 核驗，整體通過且 manifest 重核才逐列交原 projector/publisher；成熟沿原 create-only join 保存與 readback，不另保存 prediction 或 batch JSON。caller 返回完整 scope、原 rows、processed/remaining symbols 與 pending/matured counts。無 entry 或無成熟 outcome 時全員仍在 cohort 且 pending；不捏造結果。缺原 prediction、錯 hash/scope/source/日期/verifier 拒絕為 exception、CLI exit 2。

取消在初始讀回前／中以 InterruptedError 結束，CLI exit 130；進入逐列投影後取消返回 status=cancelled 與原完整 symbols、已發布 rows、remaining_symbols。非整批 atomic transaction；已完成 create-only joins 保留，重試沿原 sample_id + outcome SHA 重用，不產新 credit。bp/error 為原整數式，不轉勝率，不建立 canonical result_id、policy 或 label。

## Request codec / CLI 與 Manual 素材

入口：`scripts/scheduled/run_personal_h20_natural_outcome_batch.py --request-json <絕對JSON路徑> --request-sha256 sha256:<raw64hex>`。僅以上兩個 CLI 參數；request 使用 nofollow regular-file reader，64KiB 上限，同份受驗 bytes hash/decode，拒 duplicate keys、NaN、未知欄位、模糊路徑、相對路徑或 caller observed_at。

request schema：`personal-h20-natural-outcome-batch-request.v1`。必填 `schema_version/manifest_path/manifest_sha256/root`；可選 `input_capture_path/input_capture_sha256/outcome_path/outcome_sha256`，每組 path/pin 必須成對，outcome 需要 entry。SHA 統一 `sha256:` + lowercase 64 hex。root 為原 personal 根且必須在 package 外；不得用 latest/glob 找配對。

CLI 注入原 `personal_current_observed_h20_read_ports()` 四 ports 與原 public prediction reader partial；不接受 caller predictions、不載模型重新推論。stdout JSON 的 completed 只表示 cohort 處理完成，不表示成熟、模型優於基準或交易授權；pending/matured counts 及每列 reason 是結果判讀入口。錯配先核 exact manifest、entry、outcome 的原 pins 和決策日；來源缺件保留 pending/unknown，不回填來源或時鐘。H20 gross 為二十交易日未扣成本報酬，與機率分開；合成成熟不授自然信用。

## 中央最小剩餘接線

中央持有正式日常 consumer 與 Manual，不在本包修改。固定 base 的 `scripts/scheduled/run_daily_recommendation_learning.py:1902` 呼原 `run_personal_h20_for_current_cycle`，其 completed 結果已有 `receipt_path/receipt_sha256`（`personal_h20_daily_hook.py` 原 manifest 保存後回傳）。中央在原 no-model entry 保存成功取得 `capture_path/capture_sha256` 後，可明示以上 pins 呼本 caller；缺件也可只傳 manifest 回完整 pending。

自然重核最小位置為原 learning CLI `outcome_refs.append`（固定 base 約4973行）已核 receipt_path/outcome_file_sha/capture_sha256 之後，沿原 exact entry 對應到其保存 manifest 呼 caller。caller 自行核 decision/cycle/source/features；10/07 prediction 不接 10/06 entry。過往 cohort 必須由原保存 exact pin 清冊提供，禁止新增 latest/glob。中央需接入原日常結果收據與公開 consumer／UI，登錄兩個新 test 檔及同步 Manual/Scoped SSOT；本包 CLI/API 已可消費原 artifacts，但尚未啟用正式自動排程或完成全模型選股。

## 驗證與限制

所有 fixture 在 package 外的獨立 Windows Temp，僅 synthetic QA。最終同輪本包32項＋原 outcome10項，**42 passed / 4.03s**；targeted mypy **2 source files / 0 errors**；4個新增 Python compile exit0；quant precision/lookahead guard exit0。未重跑全倉 gate、UI mandatory 或真模型／真自然成熟。

raw 路徑：`output/qa/h20n01_20261007/`。最終 `final2.txt` SHA256=`d58b0aa85b684a43b14260ce5693aa37760767508d0a547bec548a9e1efff536`；JUnit `final2.xml` SHA256=`92b5975d5cfde1e4d0c973d3e3ffb2cb227a0a0c6c9f3988083e5b620388cb25`；mypy `mypy-final2.txt` SHA256=`0c37c4158c91ef55c724ba017bf6465f26018199badb08e3ff13f98acdf056c2`；quant `quant.txt` SHA256=`87be6a99ac7beb04aa3fa6497b13b81b3bf6d4371887b667e6dc8c2a99681e3a`。完整 source/blob/commit/raw pins 另交本機 `handoff.json`，raw 不提交。

原 sandbox 首輪 **9 passed/17 failed** 全卡 public Windows nofollow ancestor handle 權限；未改 guard/ACL，依授權同工具升權 synthetic QA 得26 passed/3.14s。增量首輪 **40 passed/2 failed**，一例 fixture 原 capture reader 偵測 ancestor source_changed，另一例新測試錯用 budget exception type；修正該 owned test 為原 ExecutionArtifactIntegrityError，再跑同42項全通過。紅 raw/XML 全保留，數量有重疊不累加。未宣稱正式資料不變之實測，只證明 synthetic source bytes/mtime 與 create-only retry。

Look-ahead 自查：沒有新增 signal/feature/benchmark/價格計算；使用原保存 decision、嚴格早於決策的 feature 與原二十 session outcome；不補時鐘、不借前日 entry。人工檢查 owned App/CLI 無裸 float/ML imports/推論/造 canonical ID。原 quant AST gate 為 scoped whitelist，綠燈不代表全部策略正確性。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| app_module/recommendation/personal_h20_natural_outcome_batch.py | 新增 | 撤回本包 commit | 需先撤下游 caller 接線 |
| scripts/scheduled/run_personal_h20_natural_outcome_batch.py | 新增 | 撤回本包 commit | 需先撤明示 CLI consumer |
| tests/test_personal_h20_natural_outcome_batch.py | 新增 | 撤回本包 commit | 無正式資料影響 |
| tests/test_personal_h20_natural_outcome_batch_cli.py | 新增 | 撤回本包 commit | 無正式資料影響 |
| docs/06_qa/BALDR_H20_NATURAL_BATCH_20261007.md | 新增 | 撤回本包 commit | 中央索引若接入需同步 |

依序核未提交與下游依賴、撤本包 commit、重驗 focused 與中央 consumer。不得刪原 joins、prediction 或正式資料以回滾。

更新：2026-10-07，H20N01 排他 caller 工程交付；中央日常接線／Manual 尚待。

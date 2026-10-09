# P01 同次 Session Metadata 重用：1,000 檔效能候選

本文記錄候選 runtime 的 static-input preflight、六角色 exact-read 與效能矩陣。三類效能 p95 均未達 300 ms；不代表 P01 效能門檻通過、EXE 資格或 F17 bundle 資格。既有 query 與 reader-issued metadata 摘要仍使用完整來源與 artifact 驗證。

## 本次程式與回歸

本次 query 變更只在同一 exact read session 重用已核的 plan、receipt、cohort 與 segment 摘要。摘要綁定原 state、root、plan/receipt body、source pins、候選與 artifact-reference tuples、unknown-code tuple、index bytes 及 read-session identity。跨 session、替換物件或來源 bytes/pins 改變時不能沿用摘要。

每次頁面 materialization 仍重新讀取該頁 child artifact，檢查 artifact bytes/SHA、layout/path、row/source identity，並保留取消檢查。沒有快取 child snapshot，沒有 QA decoder cache，也沒有跳過 fresh filesystem integrity checks。未改計算公式、特徵值、決策日期、source clock、availability、查詢語義、排序或頁面內容；沒有讀取決策 cutoff 之後的資料。

共享 cancellation regression 原先攔截 `DailyMarketTechnicalSnapshotV4Repository.read_exact`，但 reader-issued semantic proof 實際走 `query_module._read_session_child_snapshots`，使測試沒有觸發取消。只修正該單一測試攔截實際 child materialization；child 讀取恰好一次後取消，API 回具名取消錯誤而沒有頁面結果。query 原始碼 SHA 保持不變。

定向 native regression 在全新 `C:\t\session_metadata_cancel_fix_20261009_a` 執行：六個既有 reader 節點加上 18 個同次摘要測試，共 `24 passed in 47.00s`。原先 `5 passed, 1 failed` 的輸出保留於 `output/qa/session_metadata_native_20261009/existing_session_regression.log`；修正後輸出是 `combined_regression_cancel_fix_attempt01.log`。其餘驗證為 `py_compile` exit 0、query 模組 scoped mypy 無錯、`git diff --check` exit 0。

檔案 SHA-256：

- 固定 query：`166355640a95b7d7a39c62d5d4b0cf1013e81bf7859381d1132191457f5164fe`。
- 修正後共享 reader 測試：`3833954a778b31f5d7c967f64924d9c8ba8afa30ff68696fdd13403eac8e1b5e`。完整前像在 `output/qa/session_metadata_native_20261009/test_preimage_shared/test_daily_market_technical_universe_v4_read_session.py.preimage`，SHA-256 `de496a5d8d534b30bd7c2f35b59693b07f0d35312f484eb5e5e0528d4c1e4627`。
- 同次摘要測試：`39380514a8d9224d0a46a2af0f490971fb909b1fc1978b0c3b133efe303a1a41`。
- 回歸輸出：`f82e51a10246d00320cbb533727ca9f98f47cb95e626166d511ad7a15b9f734c`。

## 待測 runtime 與保存來源 pins

下一候選是固定 d12 runtime archive 加一個明確檔案 overlay，不是另一次 commit，也不能被稱作舊 acd18 benchmark runtime。base archive 是 `output/qa/p01_1000_current_source_20261009_a/source_HEAD_d12f3e32.zip`，SHA-256 `1d797701fb0e4574e2c57081caf3129b92b8715935942058b7f76924998525da`；base commit `d12f3e32672d90addc4c0e7ac0a478f2171bcfeb`、tree `36508847da0002492296ad2d31e74851d1e2905a`、content inventory `3c872f327b80ec3c7da5625a781abde0f43f12648f583dc1c1bd569c0f6b7df7`。

唯一 overlay 是 `app_module/daily_market_technical_universe_v4_query.py`：base archive 版本 SHA-256 `75e036c229a7eec50877e5300ad97a3d411a0929eb791a31ebb9354ec74d0e72`（133,817 bytes）；候選版本 SHA-256 `166355640a95b7d7a39c62d5d4b0cf1013e81bf7859381d1132191457f5164fe`（143,700 bytes）。精確 overlay bytes 在 `output/qa/p01_1000_session_metadata_candidate_20261009_a/runtime_overlay/app_module/daily_market_technical_universe_v4_query.py`，patch SHA-256 `ca74d321c18d48a61d1129ab330ade4d6a5a926a67e9618aa2eb5a4e4ca9cdd3`。base preimage 與目前 overlay 的正規化 diff SHA 為 `323ed231ba27e4f0ae38ccd296305fb55a37187e81fd0b6c0ce6556b92d551b8`；base archive query 與 query 工作樹 preimage 僅有 CRLF/LF 差異。候選完整 source tree 已建於 `C:\t\p01_smeta16635564_a\technical_analysis`，overlay 套用後重新掃描得到 4,465 files、112 directories、0 `.pyc`、80,191,895 bytes，inventory `fe9b2a0e0c2f81d6a1d45c0ec27e06666d9d5478f8ec90790fa8c6b86959099a`。獨立 post-build inventory receipt `candidate_tree_postbuild_inventory_receipt_v1.json` SHA-256 `8a4b539244f841e1add69a4d0a3b83eee1b5aedd0be71e5cf115b60b25c2b0f8` 再次確認此清冊；verifier 未載入產品模組、未開 SQLite、未呼叫 exact reader、producer、network 或矩陣。

初始 overlay 清冊由 `build_overlay_manifest.py` 計算；實際候選樹則由 `build_candidate_runtime_tree.py` 從已核 SHA 的 archive bytes 解壓，僅替換一檔後全樹重算。`runtime_source_manifest_overlay_v1.json` SHA-256 `e8c414eabf75845c8b06f70795199ee01d94010d18eb0f542448dac787d158bc`，tree build receipt SHA-256 `059114a425a31a74007e68cbe4daf59e54da5e7e8a3bab5a3783d76b30a7c14b`。收據標記 `sqlite_opened=false`、`exact_reader_called=false`、`producer_started=false`、`network_attempted=false`、`product_modules_imported=false`、`performance_matrix_started=false`。候選樹 build stdout 保存在 `output/qa/p01_1000_session_metadata_candidate_20261009_a/build_candidate_runtime_tree_native.log`。原始 overlay 計算 manifest `session_metadata_overlay_manifest_v1.json` SHA-256 `19d0673a0bf2e226b3eeadc4ef562c94226bc653e18267fb13c3eec3ced94640`，candidate manifest identity `da73abb6a08e244cc7a05f4397022db7c1eb5b09246563300fdb85ef700940a4` 仍保留作前置候選證據。

資料來源仍是已封存的既有 1,000 股票 store，不重新產製：

- 實際 sealed store root：`C:\t\p01_b3mrz9_8`；舊 benchmark attempt `C:\t\p01_mc6g40xn` 僅是 provenance，不是 store root。
- Source database SHA-256：`54ad8d6cdd018cecfc449062edd8ced56ba682b3fde8c86c1bce25d311674f27`；database inventory SHA-256：`e87a96c7cbabaac8f208b64bb8de57ef383f3d6100fccee3660862fd5ca4593d`。
- Sealed store tree SHA-256：`a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9`；method contracts SHA-256：`d3254c71badda536fa91856e5aef53b56d71f4138430a0386b55e60fb367c0da`；舊 readback receipt SHA-256：`8be6157e281c037e2d0e67717d9e25560f861bb0db8bf14b339d992e80ebc326`。
- 固定分母是 declared 1,001、excluded 1、included/processed 1,000、pending 0、missing data 1。Producer origin commit `2897f269d6b5ee6618698f191ad117adb73c0672` 與 runtime 身分分開記錄。舊 acd18 runtime/readback 證據不可直接替代 overlay runtime 的 exact read。

## Runner 最小差異與完整量測範圍

沿用 source-only `output/qa/p01_1000_current_runtime_matrix_20261009_a/current_runtime_matrix_controller_v1.py` 的量測與 guard 協定，已建立此候選專屬 controller、aggregator 與 manifest，不修改舊 controller、舊 report 或 d12 固定 source tree。舊 controller 將 source manifest 與 `SOURCE_ROOT` 固定到原 d12 extracted tree，故不可只換 CLI manifest 執行；專用 controller 位於 `output/qa/p01_1000_session_metadata_candidate_20261009_a/session_metadata_matrix_controller_v1.py`，候選 manifest 為 `session_metadata_matrix_candidate_manifest_v1.json`。最小差異只限：

1. 從 pinned d12 archive 建立新的短路徑候選 tree，先核對完整 base inventory，僅以 overlay 檔替換 query，再重算全部 4,465 檔 inventory；建樹與 inventory 已通過，沒有從工作目錄或其他 runtime tree fallback。
2. 新 controller/manifest 固定 base archive SHA、overlay 原件與 patch SHA、候選 source inventory、實際 runtime root、overlay source manifest bytes SHA、tree build receipt、aggregator bytes SHA，以及既有 DB/store/method/readback pins；執行時 module origin 必須全在該新 candidate root。
3. 不匯入或啟用 `reader_issued_decode_cache_candidate_v1.py`。warm worker 不預熱；每次操作都用正式 query/page API 與原本 fresh verification。cache prototype 僅做歷史對照，不能混入本次結果。
4. 其他行為及界線完全保留：五 cold process、一 warm process；每個 role 完整 1,000-selection、page 0 及 20 頁 × 50 rows，順序摘要與跨 segment `S00256`；warm `page_flip`、`filter_select_and_page`、`global_sort_select_and_page` 各 30 個真 API 樣本。保留 natural-zero typed page 與 explicit-empty wrapper 的分辨。
5. 每類使用 nearest-rank p95，仍要求嚴格小於 300,000,000 ns。計時仍包含公開 API 的完整 query/selection/page materialization；cProfile 只在 90 筆 wall samples 後各操作類額外執行一次，排除於 p95。cold 的 launch/open/page0 計時分開記錄，完整 20-page walk 不混入 page0。
6. 保留六個 fresh process、Windows Job 三具名角色與原 600 秒 operation deadline、10 秒 cleanup、來源與 store 前後 inventory、SQL/network/producers guards。任一角色失敗即停，不重跑、不更換 store、不放寬門檻。

五 cold 加一 warm，按原 600 秒 operation deadline 粗上限約 3,660 秒（61 分鐘），另計 static preflight 與純 aggregator。這是 deadline 上限估算，不是 ETA。此候選的 native 矩陣已完成；結果與效能未通過結論見下節。

目前 controller SHA-256 為 `f29a4281452bd08966aad9aee1368bad77d0c3037dbef020b12fb60ced296dbb`，candidate manifest SHA-256 為 `6b457d306a1b80840f69b531fe9f94c6d51a8ee80e044d3fb0395a01c2e8daa6`，aggregator SHA-256 為 `488b0f67fb365a2b21e0b49ebda4ecaf1611f1d83313b538f03726a2ce632504`。正規化 controller diff 在 `session_metadata_controller_overlay.diff`，SHA-256 `978876d7de1ef80fee2d9a7a2aae1da61919219b8692e86aed8ee8286ce250d5`；aggregator diff 只改 QA output directory，SHA-256 `c0bdfe656cda5b958b37ab21ded28e9db24168e669df25fe6ebcc1c0d49b87ae`。

純 guard/manifest contract 測試命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -I -B -X utf8 -m pytest `
  output/qa/p01_1000_session_metadata_candidate_20261009_a/test_candidate_build_guards.py `
  output/qa/p01_1000_session_metadata_candidate_20261009_a/test_candidate_matrix_manifest_contract.py `
  -q -p no:cacheprovider -o addopts=
```

結果為 28 passed / 3.72 秒，stdout 保存在 `pure_guard_contract_tests_final.log`。七個 builder/controller/aggregator/test 檔 `compile()` 檢查成功。Static-input preflight 已執行一次，exit 0、耗時 9.36 秒；收據 `static_preflight_b2ea6c2b963a.json` SHA-256 `96e0067736ce1cd69a00c6b0c8ea60f96a5ec4e70d2a954f7facb295a779393b`，stdout `static_preflight_native.log` SHA-256 `5f2646f1c694932eee2ab34ccc762d75c98f68e3f9af35dbc7b52f23c997de6d`。`failures=[]`，source/DB/Store 起訖一致；SQLite/network/subprocess 計數為零，public opener、worker、producer 均未啟動。實際 static preflight 命令如下：

```powershell
$python = '.\.venv\Scripts\python.exe'
$controller = 'output\qa\p01_1000_session_metadata_candidate_20261009_a\session_metadata_matrix_controller_v1.py'
$manifestSha = '6b457d306a1b80840f69b531fe9f94c6d51a8ee80e044d3fb0395a01c2e8daa6'

& $python -I -B -X utf8 $controller --preflight-reviewed-static-inputs --expected-manifest-sha256 $manifestSha --private-parent C:\t
```

五個 cold 與一個 warm 角色已依序完成；六份 child/supervisor 收據與完整效能結果見下節。

## 六角色 exact-read 與效能矩陣結果

依序完成五個 cold process 與一個 warm process；六者均使用同一候選 manifest/controller 與固定來源/Store。每個 child 對 1,000 個 included 股票完成 20 頁 × 50 列，完整 ordered-code 摘要一致（`6613555ad6e1f45dd7c199f20724282962d48b1a01c199e35e9053df04797b86`），跨 segment 股票 `S00256` 位於 page 5 offset 6。六份來源與 Store 起訖檢查均 unchanged，guard 計數為零，Job 清空且 cleanup completed。

| 角色 | Attempt root | public exact-open 耗時 | page 0 materialize | 20 頁讀取 | child 總耗時 |
|---|---|---:|---:|---:|---:|
| cold_01 | `C:\t\p01cur_rd_8d7e3e73cc` | 14.934 s | 548.622 ms | 12.418 s | 41.904 s |
| cold_02 | `C:\t\p01cur_rd_9d50a83f05` | 14.694 s | 514.340 ms | 12.454 s | 31.429 s |
| cold_03 | `C:\t\p01cur_rd_f1e0c05aa3` | 15.376 s | 544.909 ms | 11.643 s | 31.442 s |
| cold_04 | `C:\t\p01cur_rd_40c5471671` | 14.883 s | 573.378 ms | 11.571 s | 30.774 s |
| cold_05 | `C:\t\p01cur_rd_998d21ee37` | 14.731 s | 516.537 ms | 11.704 s | 30.755 s |
| warm_01 | `C:\t\p01cur_rd_aba26c9143` | 15.856 s | 552.697 ms | 12.135 s | 101.680 s |

Frozen aggregator 輸出 `session_metadata_matrix_aggregate_v1.json` SHA-256 `51893d53eb3a6d19ab3946c777507d302dc0373937534c0e819204fd42113cc1`，彙總 stdout `matrix_aggregate_native.log` SHA-256 `4d58e554813d9b01bcd9d2945b7aa994bcaa6387033c9ccce026afec75ad559d`。warm 90 個 timed API 樣本三類各 30 筆、failed sample 為零；nearest-rank p95 如下，均未達嚴格 `< 300,000,000 ns`：

- page flip：`604,960,700 ns`（不通過）。
- filter + full selection + page：`1,541,028,500 ns`（不通過）。
- global sort + full selection + page：`1,533,123,000 ns`（不通過）。

三份 cProfile 診斷在 90 筆 wall samples 之後執行，未計入 p95。aggregate 狀態為 `complete_diagnostic_candidate_requires_review`；本候選效能 gate **未通過**，exact-read 六角色完成不改變此結論。

## 歷史效能資料與接受界線

舊 source-only d12/original query 矩陣的 warm p95 是 page flip 998.0999 ms、filter+select+page 1,820.7275 ms、global sort+select+page 1,189.4934 ms，三類均未達門檻。後來 QA cache prototype 的 p95 是 757.2949 ms、905.318 ms、403.1362 ms，仍全部超過 300 ms。這些是不同 source/runtime/cache 條件的歷史診斷，僅供比較，不能代替新 session-metadata overlay 的 90 樣本結果。

本文件記錄 targeted reader regression、static-input preflight 及六角色 exact-read/效能診斷。1,000 檔候選已完成 exact-read，但三類 p95 均未通過；不得稱作效能接受。

## 後續正式優化候選（唯讀設計，尚未實作）

warm child 的三份 cProfile 是插樁診斷，時間不納入 90 個 p95 樣本。它們顯示不同操作有不同成本來源：

| 操作 | 插樁總時間 | 主要累積成本 |
|---|---:|---|
| 換頁 | 1,297.6 ms | `read_selected_exact` 1,288.6 ms；50 個 `_decode_and_validate_snapshot` 1,061.7 ms，其中 `_validate_snapshot_payload` 937.9 ms、`_verify_saved_rule_semantics` 346.7 ms。 |
| 條件篩選 | 2,113.7 ms | 26 次 `read_selected_exact` 2,079.0 ms；路徑檢查包含 10,556 次 `lstat`（1,114.6 ms）、442 次有界檔案讀取（1,108.1 ms）、494 次祖先／reparse 檢查（911.7 ms）；30 個 snapshot decode 為 700.2 ms。 |
| 全域排序 | 1,293.8 ms | 4 次 `read_selected_exact` 1,275.2 ms；50 個 snapshot decode 1,041.6 ms，其中 payload 驗證 920.1 ms、規則語義重建 339.4 ms。 |

這些是 cProfile 插樁時間，不是實際樣本延遲，也不可拿來直接推算 p95。條件篩選的路徑檢查和換頁／排序的 snapshot decode 都是值得分開驗證的熱點；任何候選仍須保留現有完整來源核驗。

本輪 query overlay 已包含同一 read session 的 `_ReadSessionSourceMetadata`：它以 owner token、state/session 身分、原始 plan/receipt 物件與 body、pins、cohort、segment 與 index tuple 綁定，再供 `_state_metadata` 等路徑使用。這個候選路徑已在六角色 runtime 中執行；不過收據沒有 metadata hit 計數，也沒有同一 runtime 的停用對照，所以無法由本輪 cProfile 定量分離它帶來的改善。結果仍是三項 p95 全未通過。

較適合先評估的下一項，是讓 repository 以「同一 reader-issued semantic proof＋本次重新讀到且 SHA 完全相同的 artifact bytes」授權私有 typed rehydration。現有 `_VerifiedBatchSemanticProofV4` 由 repository 的 `read_exact` 在全批 artifact 解碼、語義驗證與 layout 驗證後才簽發，帶有 manifest 內容身分、封印及 issued-proof registry；它目前不保留 snapshot。P01 的 `_ChildArtifactReference` 保存此 proof，read session 的 `_ReadSessionSourceMetadata` 另綁定 exact read session owner。`read_selected_exact` 仍會每次重讀並驗 manifest、完整 batch 每個 artifact 的大小與 SHA、選取列的語義及最終 layout；這些 fresh 驗證不可省略。

候選切片可在此 proof 與 session 私有邊界內，只省略同一已驗證 bytes 上重複執行的昂貴 semantic/fingerprint 重建，再由私有 decoder 重建 immutable typed DTO。必須保留 duplicate-key 與非有限 JSON token 拒絕、禁止 float、schema/欄位型別轉換（含 Decimal、日期與布林）、頂層 code/identity 與 artifact reference 綁定，以及原有 cancellation poll。原本公開 `from_json` 和一般 `read_selected_exact` 路徑仍走完整 strict validator；不得加入可由任意 caller 或自我雜湊取得的 bypass。能力需同時綁定 proof object、manifest/ref、repository root、P01 read-session token 與 method/schema identity；clone、跨 store、跨 session、改 pin 或 bytes 不符皆拒絕。取消、close、失敗時不留部分結果或跨 session cache。

兩種設計的差異如下：

| 方案 | 好處 | 代價與限制 |
|---|---|---|
| session-scoped bounded DTO LRU | 相同股票與 artifact bytes 再被選取時可直接重用 parsed snapshot，連 JSON 重建也能省略。 | 會保留含 raw history 的完整 snapshot；先前 prototype 的 150 筆工作集約 22.3 MB、5,960 列原料，且舊 cache 矩陣三類 p95 仍為 757.3／905.3／403.1 ms，全部超過門檻。容量會受完整 20 頁巡覽與 filter/sort 選集影響，且需要 session-close 清理。 |
| proof-gated private rehydration（建議先驗） | 不保留 batch 或 snapshot 歷史；每次仍重讀所有 refs 並 fresh hash，僅避免已由同一 proof 覆蓋的重複語義重建，額外記憶體接近固定 proof/reference 大小。 | 仍要 parse JSON 並建 typed DTO，實際收益未知；必須證明 validator 省略範圍嚴格受同一 reader-issued proof 與相同 bytes 限定。 |

建議先在隔離測試以 strict 路徑作逐值 oracle，量測 decode/semantic call count，不改現行 p95 矩陣或門檻。驗收需包含：同 bytes 的 DTO `to_dict()` 和 selection identity 完全相等；selected 與 unselected artifact 改 bytes（保留 mtime）均被 fresh SHA 拒絕；manifest/reference、proof clone、跨 root/session/store、method/schema pin 不符均拒絕快速路徑；取消在讀取前、中、末端都不發布部分頁面；close 後 proof/cache reference 歸零。普通 `from_json` 仍需獨立證明嚴格路徑不變。

filter profile 的高比例路徑檢查是另一個候選，不應與 semantic reuse 混成同一變更。若要減少同一 `read_selected_exact` 內重複祖先路徑解析，必須先證明不會跨 operation 使用 stat-only cache，並保留每個 leaf 的 reparse/hardlink/regular-file、大小、bytes/SHA、讀取前後檔案身分、全 layout 與 cancellation 核對。任何 ancestor reuse 都須有同次呼叫內明確的 directory handle/identity 邊界，不能只記錄一個先前 `lstat` 結果。這項尚未實作，也沒有安全或效能接受結果。

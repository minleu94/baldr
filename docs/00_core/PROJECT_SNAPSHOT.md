# PROJECT_SNAPSHOT（必讀｜目前狀態）

**工程驗收已通過；本文件是提交前snapshot，staged review與commit結果以Git history及root最後交付為準。** R031 attempt6的288-path relevant regression及mandatory checks已由root接受。 R027使用者接受的logical-time revision B與R028 scoped migration各自通過獨立gate；原R027 strict仍INCONCLUSIVE，舊oracle、strict receipts與R028 legacy comparator diagnostic FAIL均保留。IndustryMapper明示providers、H5 app初始化前置條件及其受影響路徑已納入current route並通過。attempt6不代表正式資料、native UI、scheduler、未知artifact或model promotion驗收。

## 2026-09-27 audit／bounded slices current checkpoint

### 個人日常產品與個人模型安全狀態（2026-09-27）

個人模型安全預設保持 `rule_only`：inventory 中兩個舊候選都是 `legacy_unproven`，不可啟用。使用者已明確選擇 V2 指定 SQLite 來源時間信任的個人研究流程；這不是外部 authority 回覆，也不構成獨立官方歷史 PIT／publication-availability 證明。現況仍沒有已證明可合法准入的真實 PIT candidate。company-registry sidecar 的 `available_at` 是 HTTP response capture 完成時間，不是官方 publication time；該 bounded provenance 不能替 industry-index、上市櫃或興櫃 coverage 背書。

本輪可引用的 scoped evidence：WP1 Bank snapshot identity/bounded reader 17P／2S（symlink 權限 skips）；WP2 company-registry slice scoped accepted；WP3／WP4 個人 UI/policy/source slices scoped；Stage B／C 31P／1S；Workbench 84P、Update QA 25P／4S。這些不是自然 scheduler、native post-fix UI、真實合格模型或完整 daily→capture→outcome 驗收。StageC outcome.v2 的 model metric 僅含 active rows；fallback 留在 delivered-cohort coverage，不當作模型預測。其標籤是決策日收盤至官方 20-session endpoint 收盤的事後 close-to-close 結果，不是 execution PnL；after-cost 為估算成本，所需成本／流動性資料不全時維持 pending／unknown。

source/PIT admission 最終測試數及 hash 尚未凍結，狀態為「待最終整合收據」；root 將追加最終 relevant regression 與 mandatory check 結果。不得從目前切片推定正式 source trust、自然成熟或個人模型可用。

### 2026-09-28 最終 relevant regression 更新

前段「待最終整合收據」記錄的是 2026-09-27 狀態；root 現已完成 302-path relevant route，收據 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T061833_712310Z/run_receipt.json)，SHA-256 `3a830dd73a2a8a88903c42211149fb4f1a298b9aeea9e4e606bfdf43fe1aee62`，`overall_candidate_pass=true`。302 個測試檔分為 298 repo-short-TEMP 與 4 OS-TEMP，兩組互斥且聯集完整；合計 3,218 passed／9 skipped／36 warnings。Workbench 84P、Update QA 25P／0F／4S、mypy 737 files、332 個 Python compile paths 與 `git diff --check` 均 exit 0；HEAD `e5d75f7cbd3312dac391f52b5c2206d0c745bbc4`、工作樹狀態及 route scope hashes 前後一致。細節見 [個人日常產品交付 QA](../06_qa/PERSONAL_DAILY_PRODUCT_DELIVERY_20261006.md)。

這是隔離的 relevant regression 與靜態／工作台檢查，不是正式資料操作、可見 native post-fix UI、自然 scheduler 或真實合格 PIT candidate 的驗收；預設仍為 `rule_only`，兩個 `legacy_unproven` 候選仍不可啟用，WP0–WP5 不因此宣告整體完成。先前 failed／interrupted route 收據照原狀保留。

### 2026-09-27 個人 V2 使用者明示來源信任更新

本段補充本 checkpoint 較早寫下的「沒有使用者來源信任回覆」狀態：使用者已明確選擇「信任我指定的資料庫」，UI 因此提供 V2 `user_declared_source_time` 個人研究設定。這不是外部 authority 回覆，也不把使用者指定 SQLite、replay 一致或內部 hash 轉成官方歷史 PIT 證明。預設仍為 `rule_only`；inventory 的兩個 `legacy_unproven` 候選不可啟用，現況沒有已證明的真實 PIT candidate。

V2 預覽與執行重驗綁定候選 pins、檔案身分及實際訓練切片（訓練窗資料列、`available_at`、來源契約、成本與 scope）。本次僅在 `coverage.source_contract.technical`、`source_disclosures.source_contract.technical`、`source_disclosures.technical.source_contract` 三處 technical contract 投影中排除 `content_digest`、`content_row_count`、`coverage_end`、`evidence_hash` 四個全庫彙總欄；另不把 replay 結果最外層的 `dataset_id`、`dataset_hash`、`source_fingerprint` 三個由全庫 source fingerprints 衍生的識別欄納入此來源切片比對。上述例外以外，其他來源與欄位仍依原契約比較；候選已保存 manifest/pins 與逐筆樣本仍獨立核對。這項 V2 個人來源切片比對不改原 replay manifest 或 global oracle。訓練窗後的更新在同一檔案身分且該切片完全不變時可保留驗證，檔案替換或訓練切片改變仍 fail closed。使用者須明確指定來源、檢查預覽、確認並保存；重啟後需重新驗證。V2 僅供個人研究，不影響 global pointer／promotion，也不代表官方 PIT 或模型有效性。

本次 UI owner focused route 為 `tests/test_ui_qt_personal_recommendation_choice.py` 28P；`recommendation_view.py` targeted mypy 0 issues、兩個 changed Python 檔 compile 通過。Workbench route 為 84P，Update QA 為 25P／4S；這些是各自 bounded 結果，不等於 native visible 驗收或最終整合 route。V2 UI source freeze／獨立 review與 root final relevant regression 收據尚待完成；真實候選、native post-fix操作及自然 scheduler仍未證。

R024 root 已完成 5-path diff review，9-suite regression 為 67P/0F/0S；`company_registry.py` 與 TPEX backfill 現各自擁有四欄 data diagnostic record/to_dict，移除 data→decision `FactorDiagnostic` imports。原 decision `FactorDiagnostic` classpath、FactorService 與序列化不變；新 data record不再通過 `isinstance(FactorDiagnostic)`，這是有意的 nominal identity移轉。Root 的 registry route 7P只驗route/metadata，不代表新增inventory 122 tests全跑完。R021原bounded scope不變；使用者另已接受IndustryMapper follow-up：data-owned company／industry-index providers由app composition明確建立注入，domain不再暗讀CSV／DB，已知in-repo callers已遷移。Boundary凍結13個changed paths；4個focused route paths共14 distinct inputs（含未修改的 `tests/test_decision_data_providers.py`），manifest SHA-256 `566c0fce31ce063b57c0f53a069e0d6a308b5cce19007fd56026e7d8ae48e602`；focused 18P/0F/0S、0.84秒。attempt6 288-path current route已包含兩個 mapper tests及其影響路徑並自然通過；此結果不外推為domain-wide no-I/O。

REC-02 的 negative-evidence consumer/projection bounded slice已接受（86P/0F/0S；recommendation-tab QA 7P/0F/0S；canonical query及journey callers亦有獨立readback證據）。completed business path由typed DecisionBatch產生current v1 projection；其v1 event僅作wire相容及一致性核對，failed/cancelled partial row/context僅為diagnostics。source search無production RecommendationService.run_recommendation() caller，也無service/body/execute外的app/UI/script last_* business consumer；R016 saved_recommendation_queries.select_latest_saved_recommendation是合法canonical readonly adapter，並非REC-02 Service list/latest-state surface。Root依R029原criteria裁定兩個in-repo業務consumer exit已達，REC-02 status為ACCEPTED_WITH_RETAINED_PERMANENT_COMPATIBILITY：保留公開run_recommendation/list/latest輸出、v1 projection、failed/cancelled diagnostics及rev1/2歷史decoder作必要具名compat；owner為app recommendation compatibility。這不代表所有last_* writer已刪、外部support已終止或存在第二canonical engine。Portfolio navigation-source identity P2另以六-suite54P/0F/1S exit0 bounded接受（1 skip為opt-in official scheduled Qt smoke）；只驗source navigation identity／22個projection欄位，不簽章整個Portfolio顯示內容。Manual §10.2已同步。

REC-05 兩個 DTO 的 owner/import cutover 已由 root bounded accept：19 個 repo 內非序列化用途 imports 已轉到 `app_module.recommendation.legacy_dtos`，舊 `app_module.dtos` public/pickle qualified paths 仍 re-export 同一 class object，module/qualname/signature/annotations/type hints 保持原值。Final freeze manifest SHA-256 `68ce801292fbc744bb4a79f3f18b5db13bafd59368f26f5b4c2606b6b9fab6f0` 覆蓋 21 source paths 與 DTO ABI regression；root 六-suite結果 69P/1S、exit 0，freeze scope pre/post hash一致。舊 synthetic p4/p5/joblib bytes fresh-process load 成功；load→redump 由 2049 bytes 變 2060 bytes，HEAD與candidate結果相同但都不與input byte-identical；新fixture p4/p5/joblib dump仍等於原fixture hashes。這完成的是 repo 內 import/owner migration；必要舊 class path列為永久相容，未宣稱可刪除 public facade，也未推論正式未知 artifact corpus。
ML2 constant-model與Restated research-contract owner／import-direction slice已由root接受bounded review：pure leaf移置與legacy same-object qualified-path aliases維持原class identity、metadata、annotations/type hints及受控p4/p5/joblib bytes；Restated原class AST、hash／market gates與結果語意保持。Pkgutil/pydoc明確載入面有負控；最新guard掃描591 files、0 violations。此guard是靜態直接／symbol-level檢查，不是攔截sys.modules所有間接反射載入的universal sandbox；未改allowlist、PRODUCTION_ROOTS或Direct15。H5 fresh -m及direct-import entry目前經v3→scripts/build→scripts/infer→app的transitive import chain自然註冊，沒有當前fresh-entry break。使用者已接受明示app initialization prerequisite；H5 bounded implementation與獨立review已接受：9 suites／105P／22.09秒，freeze manifest `4c6b89a8f3b0817118478e8b1455a9633684017f01f3711c8e8465d03f9706db`。正常app CLI保留bootstrap，裸ML entry未bootstrap在training/output前fail-closed；保留verifier、source-revision gate、exact output type與class/serialization identity。CLI驗證限`--help`初始化及target-free synthetic parity，不代表完整training/release或正式artifact load/predict。未知正式artifact只保留inventory狀態，不宣稱任意pickle可載入／預測。

TMP-NUM-01 已按原 bounded gate CLOSED。最新14-path NP1／NP2 routes各212P/1S、exit0，覆蓋Decimal half-up、同分排序、真 scheduled／historical rule-only personalization保存讀回，以及真 RecommendationDataFrameProvider.__call__ 將np.float64(91.5)／Decimal(70.0100)投影為exact built-in-float total_score、factor rows與呼叫順序。各profile對自己的native oracle；保留NP1初次parallel collection race與Windows wider-longdouble skip。這不增加自然ML品質、跨NumPy相等、所有平台或所有profile條件。

原strict gate最新 historical post-Qt full8 receipt `r027_post_qt_lifecycle_root_all_20260927.json`（SHA-256 `9a19c3ac9cc28d6c07ecda6506e1f4f35b30a7ffa4cf74cb915f531e414f5ef7`；summary `DF4533DBA4F72523E047DFBD458CED725114DFC35F17203F221E96100921992F`；scope `BED829EC6706671E98CE938C08DCA7674E5639E1A6BDE56D22512943332F0AB1`）仍為8/8 `INCONCLUSIVE`／0 semantic／947 strict differences、runner exit1；scope為1,233 paths，Direct15／pinned5一致。差異為738 event-clock、143 file-mtime/publication、64 SQLite reader lifecycle、2 SQLite transient SHA。這些是原strict歷史，保留raw evidence與9/23 frozen oracle（17,045,681 bytes；SHA-256 `4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616`）。

使用者接受的獨立 logical-time revision現已全8 PASS，source/runtime slice經boundary獨立review；root start decision授權R028實作；Root後續已正式接受scoped R028 production migration，raw receipt SHA `1a3b496973c7053c7d25612754a733cb505765667afa478be453efd2c5a19d82`，decision SHA `cc375897612e705e6c6c268a0ef63aa38c4f998d214a32fdd74d038567f792db`。詳見 [R028 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。Raw receipt `r027_logical_time_root_full8_20260927.json` SHA-256 `5e1f162cc569c49797d0f9fc9fc72b6d7f4fba41734afcec627a6d9684f372c0`，summary SHA-256 `e39f7d2e5ccb3e2a6b8d30be3d595ad2b06a6837ab9a56f9e3689bc221b58980`；8 cases、8 controls全PASS，3,303 source-scope files前後無差異，Direct15、pinned5、HEAD/status stable。新gate與原strict分開，原strict仍INCONCLUSIVE；details見 [R027 versioned acceptance addendum](../06_qa/R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)。此句記錄當時啟動裁決的限制；其後R028 scoped migration及attempt6 relevant regression／mandatory checks已分別由root接受，不改寫原strict verdict或外部驗收範圍。

`r027_post_custody_root_all_20260927.json`（bb68d020…ae0ae91；1,370-path scope、738 raw OS／146 publication mtime／63 SQLite lifecycle）是兩個Qt callback runtime修補前的歷史receipt；`ae0ddb3b…c83658`為含REC-05／ML2但未含TWSE暫存名修補的較早版，`1d457f7f…e161`為REC-05前版本。更早855／1,058 receipts與原848差異均保留為歷史，不覆寫或回填至最新9a19收據；各版的scope及分類不可混用。

另有獨立 DBManager resource slice：未修前真 TEMP API probe 的 25/25 `execute_query` return 後仍有 SQLite handle；`connect()` explicit-close control 離開 context 後為0。Root/boundary review 已接受最窄修正：保留 connect defaults、transaction與pandas read，`finally` close。新增真 connection success/error/rows/dtypes regression，連同相鄰 tests 92P/0F/0S；修後 7 次真 query return 均觀察到0 handles。`db_manager.py` source SHA `0031d1385920667515b8dd34745b807ed97bc21f9089bd1dde53e2ce3d1ab40e` → `dc3df6df6a9a68b79a00319245aa6d24b3b39de50a3ea6b76903103a8099b586`。這是已接受的獨立資源修正，不證明它是 R027 lifecycle 差異的唯一原因，也不能把 DBfix前 full8 重寫為 PASS。

R031 current result是attempt6：288 test paths自然exit 0，2,951P／5S／36W、817.03秒（JUnit 2,956 tests、0 failures／0 errors）；Root裁定`ACCEPTED_CURRENT_RELEVANT_REGRESSION_AND_MANDATORY_CHECKS`。Raw receipt SHA `9ec19361748ac2a0e0de120eee62043241d42375014af3bed60b6c2a02eefd4d`，root assessment SHA `b8d3f224d786f195ce5bbc8133ce95cae12a33320d627ccb27b80a1495e02b27`。Workbench 84P／0S；Update QA 25P／0F／4S；mypy 731 files／0 issues；changed-Python compile 109 files。3,313 source／fixture inputs無drift、scope新增／刪除為空、HEAD/status穩定、Direct15與pinned5 exact。5個pytest skips為4個Windows `WinError 1314` symlink權限與1個`longdouble` mantissa條件；Update QA另有daily／market／industry download及daily merge四項skip，均不計PASS。cleanup觀察60 roots／232 views不證明native page/profile teardown；Workbench沒有載入`ui_qt.main`。attempt1–5的失敗、中斷與成功收據按各自凍結scope保留，attempt6不覆寫歷史。

已接受的 test-owned cleanup 修補只改`tests/test_ui_qt_research_run_save.py`（SHA-256 `CE0A7F9FBF237E38321C4240B22B6C5EC64C9035C664390493B16F22C4E8F922`）：同一節點的 RED 測試本體1P但 conftest close-veto令程序exit1；修補後最小節點1P/exit0、整檔7P/exit0，後者釋放6 roots／36 views。這證明該案例可觸發並修正一條測試清理veto路徑；attempt4沒有root identity observer，不能斷言當時被拒絕的就是該視窗。B shutdown harness僅備妥並經唯讀審查，未執行；attempt5自然結束後不另跑Qt probe。attempt5通過也不證明過往hang的唯一根因。

第二輪263-path run的三個failure分別是Direct/OOC same-case `.expert-*`到`h5-rl` replace WinError 5、`test_program_readiness_projects_performance_owner_packet`回報`performance_owner_packet_invalid`，以及cache-hit custody runner回傳1。Readiness失敗已定位為QA runner basetemp與OS TEMP分離、違反既有TEMP guard；root決定只修runner並以TEMP子樹下basetemp重跑單節點通過。Cache修補對齊seed與runner的`PROFILE=prod`；owner 61-node route為61P/4.89秒，root單節點為1P/1.40秒，兩者均測於F0AC hash，最終6DF版本只翻譯註解，第三輪包含最終版本。Direct/OOC fold-008的WinError 5根因尚未證實；attempt6相關測試自然通過，但Direct15未修改，也不據此聲稱已定位該歷史失敗原因。第二輪receipt與attempt2原件保留於`output/qa/refactor_completion_20260927/final_candidate_eligible_root_receipt.json`及`final_attempt2_workspace_20260927/final_candidate_root_receipt.json`；第三輪另保留 `pytest_interruption_receipt.json`、`pytest_post_summary_native_stacks_2.txt`及integrity receipt於`output/qa/refactor_completion_20260927/final_attempt3_external_20260927/`。首次full-route嘗試因OS TEMP ancestor no-follow anchor檢查失敗而停止、沒有full verdict；早期254-path／2,610 tests collect-only exit0仍只是歷史collection evidence；category groups union只有127，不能替代top-level234 tests。更早兩次broad cross-page UI run由root精確停PID、exec回報exit -1，亦沒有完整suite verdict。

第三輪execution context有明確限制：attempt 3使用外部root exec的require_escalated；attempt 1／2是在workspace QA default sandbox，TEMP位置與execution context同時變動，故QtWebEngine／PySide shutdown stack不能單獨歸因於workspace watcher、antivirus、file lock或Qt根因。之後已修正並接受上述兩個UI頁面的callback lifetime路徑；有效的 bounded four-file observer run（receipt `output/qa/refactor_completion_20260927/qt_webengine_full_route_observer_20260927_02/receipt.json`、JUnit `output/qa/refactor_completion_20260927/qt_webengine_full_route_observer_20260927_02/pytest.xml`）自然結束：57P／0F／0E／0S、61.25秒、return code 0、未timeout或terminate，source_changed=[]。cleanup前後觀測為top-level Qt objects 552→0、QWebEngineView 72→0，72個view wrappers於cleanup後皆invalid。這只限四檔diagnostic；observer使用weak references且不查`QWebEngineProfile.defaultProfile()`，wrapper invalid／collected不能證明native page/profile資源已teardown，也不能定位先前shutdown failure根因。未變更Qt版本、強制退出方式或驗收門檻。

## 2026-09-26 Wave14 candidate revalidation（accepted with named boundary baseline）

Wave14 candidate 於獨立 managed worktree 完成 234-test／237-source full union；最終 short-path route 為 **2,446 passed／2 failed／5 skipped／35 warnings**，653.90 秒、exit 1，526 個 test/source/fixture/policy inputs 前後 hash 相同。Root 比對本輪 CLI captured stdout JSON 與 9/25 C4，584 files、11 occurrences／10 distinct、`shadow_only=true` 和兩個失敗 nodes 完全相同，裁定 `ENGINEERING_SCOPE_COMPLETE_WITH_RETAINED_BLOCKERS`／`ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。不是全綠，也不是整體 refactor unqualified PASS。

保留三輪 route 歷史：首輪 2,404P／44F／5S，起因 42 個 exact-fixture EOL mismatches 和兩個既有 boundary assertions；新增五條既有 `.gitattributes` `-text` 規則、還原五個 pinned fixtures 後，focused route 80P／1S。第二輪 2,431P／17F／5S；15 個 custody tempfile ENOENT 已由 cross 確認為 260 字元 Windows path boundary（parent 186、basename 73），short-path focused 31P／2F 中 15 個受影響 nodes 全通過，沒有改 production code。第三輪剩下的兩個 failures 就是既有 named shadow-boundary assertions。9/25 C4 保持獨立歷史收據；R027 維持 `INCONCLUSIVE`、R028 維持 `BLOCKED`。詳見 [R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 與 [Wave14 candidate manifest](../06_qa/WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json)。



## 2026-09-25 R026／R031 status（當日歷史快照；C4 named boundary baseline）

推薦校準服務在 `RecommendationCalibrationConsumer`、明列 NP1／NP2 runtime profile 與同次 invocation capability 均符合時，預設使用 `PreparedMLRuntimeInputV1`；未知 profile、自訂 consumer 或 capability 無法成立時，保留既有 `project_many()` 相容路徑。NoModel identity 只封存同次 fresh reload 實際回報 `rule_only` 且 `_model is None` 的結果。Rule 與 ML snapshot identity 分開保存；typed projector 不做資料庫、HTTP 或 filesystem I/O。`RecommendationPostCalibrationHandoffV1` 是執行中的 typed facts，不新增 execution serialized schema；receipt／availability／projection／event 由同次 handoff 投影，ML truth 不由通用 R011 capture 回讀。

NP1／NP2 capability 與 prepared-input focused route 各 68 passed；NP1／NP2 service-node 各 1 passed，NP2 default／fallback focused route 26 passed。Root 已接受 R026 exact consumer、明列 NP1／NP2 profile 與同次 capability 的 bounded runtime migration，`TMP-ML-01` 已關閉於此支援集合；custom／unverified profile 與 graph 保留相容路徑，不宣稱所有 profile 支援。C2 current union 為 1,860 passed／5 skipped／34 warnings（141 個測試，102.75 秒，exit 0），229 個 frozen inputs 前後 hash 未變；log `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\pytest.log`，SHA-256 `193EF45EA69B984A356F238CFAD4D00D714AB2B026E01CE89887260E59604687`。C2 裁定為 `ACCEPTED_WITH_NAMED_QA_BASELINE`：其 Update validator teardown `WinError 32` 保留為歷史 QA baseline，Owner 為 Update QA／DB resource lifecycle；後續 C4 Update validator 已另有成功收據，不改寫 C2 當時結果。C2 的 5 個 skip 為 4 個 Windows `WinError 1314` 與 1 個 runtime-specific `longdouble` skip。

C3 首次 union 為 2,443 passed／4 failed／5 skipped／35 warnings，471 個輸入前後 hash 未變；原始失敗收據仍保留。兩個 UI save fixtures 已遷移為 typed execution DTO，指定 UI／R020／presenter focused route 為 22 passed；log `C:\Users\archi\AppData\Local\Temp\c3uifix_0925_b\focused.log`，SHA-256 `97EE3347873ADEC2692D9BEAA3EC3D5692BEA1752E6E01FF6B1AE1E0BFC31494`。R026 shadow guard 兩個新增 exact imports 已修復；584-file scan 回到 11 occurrences／10 distinct diagnostics。相鄰 focused route 為 30 passed／2 failed，兩個失敗僅為既有 repository guard／CLI aggregate assertions；11 項 baseline 由具名 owners 保留，不宣稱全 guard 通過。詳見 [R026 shadow-boundary follow-up](../06_qa/ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)。

C4 full union 為 2,446 passed／2 failed／5 skipped／35 warnings（640.25 秒，exit 1）；root 裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。兩個失敗是既有 shadow-boundary CLI／repository aggregate assertions；584-file scan 的11 occurrences／10 distinct是歷史diagnostics並保留原receipt；current guard 589-file scan為0 violations，aggregate regression 2P已接受，不把舊baseline當目前違規。C4 route 的 471 個 inputs 前後 hash 未變，SHA-256 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`；與 C3 route 對照時只有 3 個 source/test inputs 不同：`ml_module/shadow_boundary_guard.py`、`tests/test_ml_shadow_dependency_boundary.py`、`tests/test_ui_qt_research_run_save.py`，其餘 468 個 inputs hash 相同。pytest log `C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\pytest.log`，SHA-256 `88797C7C2476576D771E88099E0016D49C10A78D29B0494B2A3CE834A8CF29F9`；route SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。C4 mandatory gates亦已驗證：Workbench 84 passed、Update validator 25 passed／0 failed／4 skipped、broad mypy 724 files／0 issues、67 個 changed Python files `py_compile` 通過，`git diff --check` 通過；source fingerprint 為 2,297 files、SHA-256 `A7F674B9551CC98090D6356E7879E1CE13452655C95EA311CDD2D3E859063AFF`。2026-09-25 root依當日C1–C4 evidence裁定當時定義的R031工程範圍以named blockers／owners收口；這是歷史裁定，不是目前R031/全域完成 verdict，也不是正式資料、scheduler、ML promotion或production acceptance。R027 維持 `INCONCLUSIVE`、`AB-ML-01=OPEN`、`TMP-ML-02=ACTIVE`，R028 維持 `BLOCKED`。詳見 [C4 mandatory gate receipt](../06_qa/C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)、[R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)、[R026 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md) 與 [R026 source revision evidence aggregate](../06_qa/R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md)。

## 2026-09-23 R025 strategy owner 搬移（ACCEPTED_SCOPE）

StrategySpec／StrategyMeta／StrategyExecutor／DailySignalFrame 的 canonical owner 已移至 decision_module/strategies；舊 app paths 為 9 個必要薄 public／qualified-name aliases，root 依 R029 接受 PERMANENT_COMPATIBILITY。Final 17-path source/test route 6P/0F/0S exit0，literal identity/wire 與 synthetic old-qualified-path regression 均通過；不宣稱自然舊 executor artifact 存在、未知 artifact 已載入或整個 facade 可刪。

## 2026-09-23 正式行情與相依資料修復完成

正式 SQLite 與大盤 CSV 已套用 3,106 個官方 TAIEX 交易日的 OHLC／成交股數，補入 19 日並保留備份後移除查詢表 2 個非交易日。九個原先完全缺漏的歷史週六已補入上市／上櫃共 14,869 列；三個休市日與 5/20 額外 54 個錯日 keys 共排除 2,942 列，before 值與原始檔保留。全歷史 5,331,231 列的 20 個技指、2,210 份 CSV 及 17 欄每日整合快取均已正式發布並完成獨立全量讀回；買賣價／量、本益比及漲跌價差六個衍生複本也已正式同步並完成獨立全量讀回；來源空值不補零或前值，20 指標、其他欄位、日價、大盤與 schema 保持。這代表本輪已確認的行情與相依快取修復完成，不代表所有基本面 PIT／產業歷史資料已補齊。日常重匯與完整重算防護已提交，保留既有五、六碼證券，缺值不補零／前值。

新來源候選的兩組完整重訓、獨立評估與各 13 檔研究推論已完成：H5 資料 3,498,147 列／全部 3,469,960 成熟列 fit；bounded 21,898 列／422,952 筆 OOF 預測（17,623 個不同測試列）。H5 三組 downside 與 bounded pooled 報酬／downside 均未勝基準，「未正式啟用」包含模型品質限制，不只是程式尚未正式使用。62 欄契約及 15 個凍結 ML 檔不變，rule_only／production pointers 不變。先前 v3 保留原身分，只作舊版本比較；完整結果見[修復來源候選驗收](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)，資料套用、回復與範圍見[正式資料修復](../06_qa/FORMAL_DATA_REPAIR_2026_09_23.md)。

## 2026-09-23 舊 v3 模型重建與研究驗證紀錄

兩個受影響模型家族的修訂研究資料、完整 fit、獨立評估及 13 檔最新資料推論均已完成。官方市場 v3 核驗 153 個月、306 份回應；全市場 3,496,189 列通過欄位／市場值／日期核對，H5 最終 fit 使用全部 3,433,790 個成熟候選列。市場組在相同股票風險 truth 上的誤差由 9,546 降到 353 bp，但基準為 322 bp；三組 downside Brier 仍不如基準。bounded 官方 v3 的 17,285 列、兩算法、四期間也完成 fit，327,816 筆 OOF 已核驗，但 pooled 報酬／downside 未勝基準。因此該研究版本的工程修復完成，**模型品質仍不足以正式啟用**；rule_only、舊模型隔離及 production pointers 保持。當時尚未寫回正式大盤，後續正式修復見本頁上方；配置 targets 與歷史產業 labels 的限制仍在，v3 不自動取得新正式資料版本的驗收。詳見[完整 v3 驗收](../06_qa/FULL_OFFICIAL_MARKET_V3_REPAIR_QA_2026_09_23.md)及[執行紀錄](../06_qa/MODEL_REPAIR_EXECUTION_2026_09_23.md)。

## 2026-09-22 個股研究內嵌工作區

主程式新增固定「個股研究」頁，市場／推薦／觀察清單／持倉的下鑽共用同一頁；切換工作區保留內容，返回來源定位目前研究股票，關閉主程式同時合作式取消報告與決策結果讀取。籌碼頁把法人、信用、集保與事件分區；持股級距改為語意表格，原始資料與可得時間保留在詳情。本次只調整呈現與導覽，不寫正式資料或改策略／交易行為。操作見 Manual 7.3。 本輪隔離整合 pytest 為 152 passed／1 skipped（含 UpdateView 84）；更新頁 validator 為 25 passed／4 skipped，全域 mypy 640 檔、changed Python py_compile 與 diff check 通過。另有跨程序讀回、busy close exit 0、研究旅程 runner 及正式 theme 的 1440／1000px offscreen 視覺檢查；未測 native 前景操作與螢幕閱讀器。


## 2026-09-22 歷史價格受控修復

使用者核准後，2026-05-20 的 868 筆 `daily_prices` 已完成正式修復；1256 close=183、1477 close=213，1538／2321／5906 的 OHLC 保留 NULL。Root 獨立唯讀逐列 readback 為 868／868 相符、同日非目標 fingerprint 不變；54 筆缺 canonical 的資料未修改。Online backup 與逐列 before／after receipt 保存在 DATA_ROOT 的 `output/scheduled/daily_price_repair_receipts/20260520/historical_price_spike_20260921/`。

模型／PIT 修訂保護已通過 55 focused tests；該階段全域 mypy 639 source files 通過。已知 derived h5 與 bounded operational 兩個 artifact hash 在反序列化前保守隔離，原模型與凍結產物保留，沒有重訓或 promotion；calibration pointer 仍為 rule_only。PIT exporter、歷史 snapshot 與 forward label window 自動檢查修訂 marker，pending 缺逐股明細時保守阻擋全部股票，避免晚到修訂冒充歷史已知資料。

相依技術指標已完成受控 apply：範圍為 868 檔、75,442 筆既有技術列，更新 1,277,135 個 DB 欄位；869 份個股／彙總 CSV 快取已同步，原本缺少的日期／欄位不新增。完整來源 prefix hash 與 before values 均已驗證；online backup、逐檔 journal 與 final receipt 保存於 DATA_ROOT 的 `output/scheduled/technical_indicator_repair_receipts/20260520/historical_price_spike_20260921/`。指標／快取修復 fixtures 13 passed，含程序中止恢復；原始 daily CSV 與模型 artifacts 保留。詳見[修復紀錄](../06_qa/HISTORICAL_PRICE_SPIKE_2026_09_21.md)及[模型影響與隔離](../06_qa/PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md)。

## 2026-09-21 歷史價格尖峰稽核

2026-05-20 的 1256／1477 已以完整官方 retrospective response 核對：canonical 分別為 1256 close 183、1477 close 213，formal SQLite／corrupt backup 為另一組錯誤值；5/20 TWSE 差異 868 筆（865 完整差異、1538／2321／5906 缺 OHLC，另 54 筆無 canonical 暫不動）。本輪未修 formal DB；來源核准、可回滾修復與下游重算影響仍分開待定。詳見 [歷史價格尖峰稽核](../06_qa/HISTORICAL_PRICE_SPIKE_2026_09_21.md)。

# 2026-09-21 個股研究資料鏈查核

正式資料只讀查核已完成：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 的 2026-09-21 `daily_prices` 查到 1,968 rows／1,968 codes，`technical_indicators` 查到 1,965 rows／1,965 codes；2382=344.5、3207=38.25、9935=18.2、1418=17.55 的查詢 rows 日期均為 2026-09-21，並完成日期／重複鍵／raw 對照檢查。這只證明本輪查詢範圍內的存在性與一致性，不代表官方交易所全域真值或全來源同日 fresh。

2026-09-21 全市場跨日價格稽核進一步比較 2026-09-18→09-21 與 2026-08-25 起的相鄰交易日：9/21 1,968／1,968 rows／codes 的 O/H/L/C invalid 為 0，9/18→9/21 有 7 筆絕對跳幅 ≥10%、≥20% 為 0；這些跳幅與 11 筆成交金額／量隱含價超出 O/H/L 仍待官方公司行動或成交明細核證，不能宣稱所有價格合理。稽核也確認資料契約的具體 consumer bug：`漲跌價差` 是正絕對值而方向在來源欄，9/21 831 筆下跌都有可解析負號；報告 service 已修正方向合併，1256 為 172→170（-2）、1477 為 194→191.5（-2.5）。官方保存 response／日期／hash custody 的代表資料已對照；merged aggregate 最新僅到 2026-07-14，屬 stale，不能替 9/21 作 cross-source 驗證。完整範圍與限制見 [全市場跨日價格稽核](../06_qa/PRICE_JUMP_AUDIT_2026_09_21.md)。

目前高風險資料邊界：formal institutional／credit 最新到 2026-09-08、TDCC 最新到 2026-09-04；月營收／季報 PIT 仍有 expected period 與 announcement／available-time 缺口；broker coverage 依股票不同（2382 到 9/21、3207 到 8/20、9935 到 9/14、1418 無 formal broker row）。1418 Paper blocked 分類為 candidate／lineage 缺件，不是 price corruption。候選 DB 的 rows 不得替 formal SQLite freshness 認證；`candidate_only=true` receipt 現由 read service 排除。

本輪未寫入 formal data、未重建／回填／重跑 scheduler、未更新 learning 或交易狀態。資料日、可得時間、PIT／current、source coverage 與 candidate-only 限制須在研究報告中分開判讀；缺件不可補 0。完整 evidence、SQL、focused QA 與 freeze 後整合 QA 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。

2026-09-21 候選池提醒呈現修正：首頁與每日決策已共用逐股原因、資料日／品質與查看步驟，缺前次分數不再只顯示籠統人工判讀；首頁一般觸發提醒導向候選池。候選表以可讀的「推薦來源」狀態替代原始識別字典，保留內部 exact identity。此為呈現修正，不改指標觸發、推薦評分、資料或交易權限；操作見 Manual 第 7.1 節。

2026-09-21 觀察清單導覽修正：移除寬版 responsive 殘留的未掛載候選池提示元件；一般進入、切換尺寸或返回只呈現頁內候選池，明確研究報告／頁面說明入口仍保留。此為 UI 呈現修正，不寫入正式資料。

## 2026-09-21 V5 日常操作與可讀性工程狀態

工作台、候選／研究／持倉、推薦／回測與導覽的 bounded presentation slice 已完成 frozen QA evidence：首頁優先顯示每日重點與下一步，日常／進階研究／系統維護分層，研究報告深頁按需繪製，缺 OHLC 可退回 close chart，錯誤保留白話恢復入口。A／B／D 的 final screenshots 已由 root 以正式 theme 審查；before／after 只在 30-row isolated fixture、2 samples、in-process boundary 下成立，不能外推 production dataset。

本輪 mandatory update pytest、QA validator、全域 mypy、changed Python py_compile、frozen manifest 與 isolated after perf 均已保存。精選整合 route 為 `299 passed, 1 warning`；`test_workbench_source_service_reads_real_read_only_sources` 已精準核對 seeded 2330 portfolio alert 的來源、原因、trace、drill-down、action 與 `write_intent=false`，並保留完整 background evidence feed。pytest cache warning 已獨立記錄，不影響測試結果。

最新 UI freeze evidence 以 `output/qa/incident_20260921/ui_readability/freeze_final_v2/summary.json` 為準（`passed`，offscreen）；all-pages focused route 為 122 passed／1 skipped，UpdateView 84，validator 25 passed／4 skipped，mypy 638 source files，changed Python py_compile passed。freeze 後 affected integration route 為 135 passed／1 skipped；全頁 loaded/error／極長真實資料未全部重演，native window／screen-reader 未測試。

版本名稱為「V5日常操作與可讀性工程」。這是工程可用性／導引進度，不是正式 V4／V5 gate、V6 user-level personalization maturity、自然 learning 效果或 production data readiness；原有 formal／natural／cross-page pending 保持不變。

本輪 UI 整合修正已納入工作樹：左側導覽群組與項目左對齊；個股報告換股會清除舊報告，同股 reload 失敗／取消會明示 last-good data 並保留 Journey 原因；來源摘要與完整 source trace 分層呈現；持倉頁分開日常正文、日期／原始 timestamp、Paper health 與模擬／歷史資料，進階正文可捲動並保留可讀 splitter 比例；工作台與說明按鈕把 machine token 轉為白話。這些是呈現與導引修正，不改資料、評分、交易或 writer；portfolio footer pane freeze 後的 mandatory integration QA 已通過。

> **2026-09-17 HEAD 校準**：目前文件基線為已提交 `0219d709`（C P1 bounded
> next-day inference／projection provenance），並承接 `9a9e778b` 的 Qt 關閉修復。已驗收的 bounded slices 包含
> `5a3ed5db`＋`ef594007` Position Health、`a4996cba` `user_declared`、`031e11ab` Continuity
> Review Workbench R1、`89a264f6` PIT reader/caller、`086ba60c`＋`0aaf0dff` BankTaiwan
> root guard／受控 retry，以及 `94d30b51` calendar／inventory audit。`0219d709` 已完成
> training／inference source 與 PIT hash 分離、共享 schema／transform compatibility、immutable
> hash-verified projection receipt、exact result／candidate／date／cost readback、normal UI
> default UUID → save → exact readback 與 identity conflict fail-closed；rule top-N selection
> authority 保留不變。相關 bounded QA 為 75 tests、mypy 9 source files、ML boundary guard
> 509 inspected／0 violations，詳見 [P1 provenance audit](../06_qa/DAILY_PROBABILITY_LEARNING_NEXT_INCREMENT_AUDIT_2026_09_15.md)。
> L 的官方 taxonomy source chain、完整跨頁整合、自然 evidence 與 V4 formal Gate 仍待完成；本工作樹另已
> 接上 C-owned V6 personal capture／read／ACK／明示 action／evaluation bounded slice，但尚未形成正式
> personal sample。下一順序仍是 **L source chain → 整合使用流程 → 以真實 user decision/outcome evidence
> 驗證個人化效果**，不把工程接線、fixture、replay 或 `natural sample=0` 縮寫成 V4／V5／V6 完成。

2026-09-18 core static follow-up 的 12 個 production files compile／mypy clean，float／
look-ahead quant guard clean；global ML shadow boundary re-inspected 518 files，仍保留 4 項
既有跨層 import residual，沒有以本輪 allowlist 掩蓋。這 4 項 residual 不改寫上述
personal／natural／formal readiness 邊界。

## 2026-09-21 晨間排程與資料接線修復

五項晨間／週排程 action 均仍指向 repository canonical CMD wrapper，且 2026-09-21 最終
`LastTaskResult=0`。Evidence dry-run 已修正隔離 Paper status schema／path、Frozen Rule producer
status、Position Health market-lane warning projection、CMD／PowerShell orchestrator parity、唯一 log 與
bounded Exit timeout；Windows task 連續兩次同日實跑皆 exit 0。Position Health proposal 改用
`position_health_transitions_v2.sqlite` 的 semantic identity，同一市場 rows 重跑保持 5 筆且
`persistence=idempotent`；舊 v1 DB 保留 immutable audit，不搬移未核准 proposal。

Phase3C institutional／credit candidate DB 已驗證 2026-09-21 兩市場 source coverage、無 natural-key
duplicate；freshness 改讀明確 candidate DB，不再以正式 DB 舊 candidate tables 誤判。月營收 2026-08
current observations 已受控 apply，但 formal monthly／statement PIT 仍缺 announcement／availability／
revision evidence，因此 freshness 合理維持 fundamental degraded。Evidence 最終為 `degraded` 而非
`failed`：工程 blockers 已清除，剩餘是 1418 position lineage 與既有持倉 thesis 人工欄位、以及
自然 outcome maturity；仍不授權 formal credit、production Evidence 寫入或自動交易。
05:30 read-only heartbeat prompt 已同步上述 candidate／formal／Position Health 判讀與 timestamp log
pointer；排程時間、target thread 與「不重跑、不修復、不寫檔」邊界未變。

## 2026-09-28 個人日常系統最終 relevant regression v2

EOF 空白清理後，root 對精確提交候選版本完成 302-path regression：3,218 passed／9 skipped／36 warnings（298 個 repo-short-TEMP 測試及 4 個 OS-TEMP 測試）；Workbench 84 passed、Update QA 25 passed／4 skipped、mypy 737 files、compile 332 paths 與 `git diff --check` 均通過。最終收據 [`run_receipt.json`](../../output/qa/personal_daily_product_20261006/final_root_route_20260927/run_20260928T064551_034316Z/run_receipt.json) SHA-256=`0ae3ec09a5f2a61c57bd28bc395bd2b3da4979146c7d00add348e396b791888b`；前一版收據仍保留為歷史。這是隔離 regression 證據，不解除 native post-fix、真實合格 PIT candidate、正式資料或自然 scheduler 尚未驗證的限制，也不表示 WP0–WP5 全面完成。

## 持續保留的接受邊界

以下是既有證據的限制，沒有因文檔整理而解除。詳細日期、source identity、hash 與測試結果見[整理前歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_27.md)及原始 QA；舊 receipt 不代表今天仍 fresh。

| 主題 | 保留的限制與接手入口 |
|---|---|
| Refactor | R027原strict維持`INCONCLUSIVE`；使用者接受的新logical-time revision與root接受的scoped R028 migration各有獨立gate。R031 attempt6的288-path relevant regression及mandatory checks已由root接受；此列為提交前snapshot，stage review與commit結果以Git history/root最後交付為準。`TMP-ML-02`原conditional migration已滿足；formal/native/scheduler/unknown-artifact與promotion驗收不在本輪範圍。 |
| Paper／Formal／自然證據 | 必須核對同決策日的 terminal／immutable receipt、calendar availability 和 source／state identity；隔離 fixtures、research capture、source_verified 不授予自然成熟、Formal credit 或成交證據。[跨日證據交接](../06_qa/V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md)。 |
| ML／推薦學習 | 新修復來源模型的工程建置與評估已完成，但品質未勝基準；rule_only 與 production pointers 不因建置成功改變。自然 probability calibration 仍需完整 prediction／policy binding 和成熟樣本，不拿 close-to-close 研究結果冒充可成交收益。 |
| 個人化與持倉 | source custody、候選與 user_declared 持倉不等於 personal delivery、adoption 或 filled entry；缺 lineage 不回填為可信持倉。當次 source／calendar／cost 仍須獨立驗證。 |
| 資料／PIT | 現況補齊不授予歷史可得時間信用；基本面 PIT、歷史產業 labels、未公告資料與既有來源缺漏仍按原始 QA 限制。不要補零、前值或用晚到修訂冒充歷史已知資料。 |
| Scheduler／交易 | 任務註冊、Ready 或 wrapper 工程驗證不等於每次執行成功；舊 host query 不當作 live 狀態。正式寫入、promotion 與 broker execution 按既有權限／Gate 另行接受，不由文檔更新授權。 |
| Direct／容量 | 舊 build／resume 收據只證明當輪範圍；承接未完成年度、OOC／fit／fold 工作前，先重驗 live headroom、200 GiB reserve 與原任務授權，不沿用舊容量數字。 |

## 閱讀與歷史

- [Roadmap Hub](DEVELOPMENT_ROADMAP.md)：產品方向、工程里程碑與版本成熟度各自的權威入口。
- [目前架構](../01_architecture/system_architecture.md)與[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)：設計目標與已落地範圍分開判讀。
- [完整操作手冊](../07_guides/APPLICATION_MANUAL.md)、[QA 主題入口](../06_qa/README.md)、[文檔索引](DOCUMENTATION_INDEX.md)。
- [2026-09-27 整理前快照全文](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_27.md)：保留 9/8–9/26 逐輪觀測與收據連結；舊「待完成」不自動成為目前待辦。
- [2026-09-08 舊快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md)：更早的整合歷史。

本頁維護最新範圍與未解除限制；新的驗收細節保存於專項 QA，不把逐輪流水帳重新貼回本頁。

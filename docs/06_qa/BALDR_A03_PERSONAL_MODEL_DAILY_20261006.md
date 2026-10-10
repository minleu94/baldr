# A03 個人模型每日保存與自然結果

> **後續整合範圍（2026-10-10）**：本文的中央 CLI／App caller 接線待辦屬 A03 lane 當時狀態；後續收據記錄自然 caller 與消費端整合。本文命令仍是該隔離 lane 的證據，不授予目前排程或正式資料操作授權。自然效果與資格限制仍以 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)和[中央整合收據](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md)為準。

本 lane 固定 base `36dc1baf740007834f385ff0f654c7fe268a36f3`，只交付五個 owned 檔案。每日工程鏈已提供：既有 personal recommendation producer → canonical exact-ID 讀回 → immutable 個人 prediction capture → 官方 H20 sessions resolver → 個人 natural outcome。自然效果尚未成熟不阻擋保存新的已交付預測；缺官方交易日／價格／資格仍保持 unknown，不補平日或零值。

本次只使用隔離合成 fixture；未執行真來源、Task 註冊、ACL、交易、push、migration 或新 fit。中央保有 config／main／consumer composition／Task／Manual／原 plan，本 lane 未改這些檔案。repo `.agents/skills` 本機不存在，已讀 `docs/agents/skills_registry.md` 與 `docs/agents/skills/team.md`、`quant_defense_guard.md`；Graphify 舊圖只作定位，當前程式為準。

## 凍結入口與來源

CLI：

```powershell
python scripts/scheduled/run_personal_model_daily.py --request-json <absolute-request.json> --request-sha256 sha256:<raw-request-bytes-hash> --receipt-root <absolute-isolated-receipts>
```

`--help` 不載入執行服務，不寫任何輸出。request 限一般檔案、1 MiB，驗原始 bytes SHA-256；CLI exit 0 為 completed／completed_with_pending，2 為 failed／completed_with_unknown，130 為 cancelled。pending 不是模型效果通過。

App API：

```python
run_personal_model_daily(
    request=request, receipt_root=receipt_root, cancelled=None,
    gross_contract=None, lineage_reader=None,
)
capture_personal_daily_results(result_ids_tuple, queries, personal_root)
project_personal_capture_h20_gross(
    capture_path, queries, personal_root,
    contract=a02_contract, lineage_reader=controlled_original_reader,
)
```

request schema 為 `personal-model-daily-request.v1`，拒未知欄位：

| 欄位 | 契約 |
|---|---|
| `canonical_recommendation_output_root` | 絕對路徑，內含原 `recommendation/runs/recommendation_runs.db` 與 execution_artifacts；不是新建空庫入口 |
| `personal_capture_root` | 絕對路徑，原 create-only `captures/`；與 canonical root 分離 |
| `isolated_outcome_root` | 絕對路徑，與 canonical／capture／行情 DB／calendar 路徑樹分離 |
| `market_source_db` | 精確絕對路徑、原始 bytes pin；只讀 |
| `calendar_cache_path` | 明示官方 cache 路徑；存在的全部 cache 檔均須 pin；缺 cache 允許收集預測，outcome 保留 unknown |
| `evaluation_at` | 含時區 ISO datetime；固定本次自然結果評估時間，不改原 decision／feature cutoff |
| `result_ids` | 明示、不重複、最多 500 個 IDs；可空 |
| `capture_paths` | 明示、不重複、最多 500 個 captures 直屬 JSON；可空；與 result_ids 至少一項非空 |
| `source_pins` | 1–1000 個 `{path, sha256}`，hash 為原始 bytes，包含行情 DB／完整 calendar inventory；讀前、producer 後、outcome 後重驗 |
| `generation_argv` | 可省略；明示原 `scripts.run_personalization_recommendation` argv，沒有 shell 或任意 command port |
| `timeout_seconds` | 可省略，預設 300；僅接受 int 1–3600，拒 bool |
| `temporary_closure_cache_path` | 可省略；明示官方臨時休市來源，沒有時沿原 annual_plan_only 語意 |
| `gross_model_contract_hash` | 可省略；注入 A02 contract 時必須匹配其 contract_hash，固定同次 gross 解讀 identity |

generation 必須沿 prod、非 historical-research、同 output root、明列 result_id；config-json 須 raw pin。data-root 的行情路由必須與 `TWStockConfig` 原 `data_root/sqlite/twstock.db` 一致；current-fundamental-source-root 與獨立 journal JSONL 都須明示，不能借環境猜來源。本入口只啟動原 producer；既有來源／政策／loader 資格限制不變，失敗不冒成功。

## 保存、重試與取消

`receipt_root/runs/<request-logical-sha256>.json` 是 create-only terminal 收據；`attempts/<request-sha256>-<nonce>.json` 記本次 runtime failure／cancel。每份 schema 為 `personal-model-daily-receipt.v1`，含 request hash、首次 process PID／aware 開始時間／nonce、producer 收據、原 prediction pins、outcome summary／paths 與 artifact raw SHA。`global_natural_evidence_created`、`promotion_credit_created`、`auto_fit_performed`、`formal_order_allowed` 均 false。

收據根必須與全部輸入／capture／outcome roots 分離。單 writer EXCL lock 保持到收據發布完成；busy 不移除另一個 writer 的 lock。只清本程序的協調 lock／暫存，不清原資料。成功重試重驗 pins、原 canonical captures、artifact raw bytes，保留第一次收據 bytes／PID；回傳 `idempotent=true`，另附當前 `readback_process_identity`，不把重試造為新自然預測。

失敗／取消可能留下已保存 canonical 結果、captures 或部分 outcome，attempt 收據如實記錄，沒有 rollback／自動刪除。runtime failure 不建立 terminal，可在來源 pins 不變時明示重試。preflight request／unsafe root／pin 錯誤在寫入前拒絕，以 CLI JSON 診斷返回，不能安全確認根時不強行寫 failure 檔。producer timeout／取消只終止本次 child；stdout 限 2 MiB、stderr 64 KiB。outcome preparation／publication 階段合作取消；publish 完成後以真實結果回報。

既有 capture schema v1/v2/v3、baseline probability、cost／after-cost 與 canonical source／decision／inference／feature pins 保持相容。H20 維持官方實際 session proof＋原來源 endpoint，unknown／缺價／未成熟不發布成熟 outcome；不得以週末扣除、當日最新資料或合成價格補足。原 natural outcome API 僅 additive cancelled keyword，預設行為不變。

## A02 gross additive port

A02 固定 commit `7b5f055d506f0f95777edd4dfaae7cd381f3666d` 提供 `H20GrossModelContract` 與 pinned same-bytes inference；中央可注入此 contract 及原 `read_recommendation_training_lineage`。A03 不載新模型、不重算舊推論：從原已核 canonical receipt 的 `ranking_score_bp` 解讀原 return head，目標為 `absolute_forward_stock_return_bp`、20 trading sessions、`close_to_close_event_date`、`no_cost_gross`。

解讀前核 contract、candidate／manifest／artifact／dataset pins、raw manifest／candidate／lineage、原 verified training provenance source／PIT／as-of、exact feature schema／registry／runtime。原 receipt row `model_version=contract.candidate_id`，candidate metadata `model_version=contract.model_version`；兩者不重標、不強行相等。rule-only row、缺 lineage、缺 contract、pin 不合均 unavailable／null；絕不從 calibrated_probability 或 after_cost head 推 gross。gross view 是新 daily 收據的 additive 欄位，不改舊 capture artifact。

此 view 不新增 formal／natural／production qualification。中央仍須完成 A02 contract／原 lineage reader 的受控 composition 注入，以及 CLI 與 App 日常 caller 的具體接線；Task／cadence／正式 root/account/source 啟用留中央。本 lane 先交可注入 port，不把合成驗證冒充真上線。

## 驗證與交付

最終三檔 focused union 為 **61 passed／1 Windows symlink skipped，10.91s**：本 lane 36 例＋既有 capture／outcome 25 例；數量不再與先前 27／34 例或相鄰 25 例累加。targeted mypy 三個 production 檔通過；四個 Python 檔 py_compile 通過，diff-check 通過；量化守衛 exit 0。未重跑全倉、Workbench、UI 或完整 roots mypy，本 lane 沒有 UI 變更。

raw／JUnit 位於 lane `output/qa/a03/`，不 stage：`a03-owned-union.log`、`a03-owned-union.xml`、`mypy-delivery.log`、`compile-delivery.log`、`diff-delivery.log` 與 `quant.log`。其他每輪 final／delta 檔保留，不冒稱全 App gate。首輪 focused 的 full raw 曾被後續 run 覆寫；仍保留 `a03-personal-model-daily-retry.raw.txt` 的原 launcher PID 失敗，後續改獨立 stderr runtime PID probe 後通過，沒有放寬原保存 bytes／writer identity 斷言。

Windows venv `python.exe` 是 launcher，PID 與實際 runtime 可不同。producer 改用原 `sys._base_executable` 加 `__PYVENV_LAUNCHER__` 保持同一 venv；隔離實際子程序核 prefix／PID／成功 JSON，取消及 timeout 後核 actual child 已停止，未執行模型或 fit。gross 正向案例是明示 structural adapter oracle，canonical 原保存 ingress 由相鄰 capture tests 驗證；此處不冒稱真 A02→日常 producer→gross 完整上線測試。

Look-ahead 自查：每日 producer 沿原同次決策 cutoff；捕獲與 gross view 僅讀原封存 inference，不重新取今日 features；自然 outcome 在 evaluation_at 只接受原 resolver 已核官方 20 sessions 及來源 prices。新程式不新增裸 float；gross 保持整數 bp。靜態量化工具只是白名單檢查，不宣稱完整時序證明。

回滾先核 working tree／owned 範圍，中央可不採此 lane commit，或只 revert 本 lane 五檔改動。兩個原 app 檔回復固定 base；新增 CLI／tests／QA 文件停止採用。已保存 captures／outcomes／原資料保留，不使用整根 cleanup。中央同步 Manual、Snapshot／Index／原 plan、具名 test inventory 的 exact API 與剩餘資格；本 lane 不共寫。完整自然結果累積、效果改善與正式 cadence 持續驗證，不當永久工程阻塞，也不宣稱已達效果資格。

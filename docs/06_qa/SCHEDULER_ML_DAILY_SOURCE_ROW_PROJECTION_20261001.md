# ML 每日原始來源列隔離投影 QA（2026-10-01）

## 結論

已對 2026-09-30 的既有雙市場 prospective source candidate 完成一次 no-write preflight 與一次經核准的 repo-local candidate 寫入。最終 candidate 有 1,972 列、9,004,111 bytes；兩市場 raw、receipt、revision evidence 與 D SQLite metadata 在投影前後一致。此結果只證明這個單日來源列研究投影可保存、可讀回，沒有宣稱 source unit、決策 cutoff、PIT、Formal、Direct/OOC 或模型資格。

既有 source candidate 的 TWSE／TPEx eligible rows 分別為 1,095／877；source raw table rows 分別為 35,794／1,013。TPEx 8440「漲跌」原 token「除息」保留為 `source_annotation`，數值與 scale 為 null，沒有解作零、報酬或股利數字。未列入精確 annotation allowlist 的非數字 token 仍 fail closed。

## 實際來源與 candidate

輸入 manifest：

`output/qa/ml_prospective_daily_price_candidates/2026-09-30/089c28f7c037af83c41e99e28bc6c5ccb85ecf215cb52cb65ae7fd7c889f5d81/manifest.json`

- input manifest SHA-256：`226f222c7ed32ed3df75f5918f449874354c60d3d8cb400e2d2126c275ff9b49`
- TWSE raw SHA-256：`5f4bb47a32d90d7f6ded896bac70174bb3267148f53f5bb016f72d1ebd393689`；receipt SHA-256：`6e9a78840b83629647d69809842e0d7791f8001764643d7209aa5feddb6bdffb`
- TPEx raw SHA-256：`ee80854bd773c12237953e3a700fc762b4b88c52de09f9ffa6027ee67a16a311`；receipt SHA-256：`26c83bfce114f65b188be5405c1fde22115b8b7c1a432d802dda13209c5b3c57`
- 原始來源可得時間：TWSE `2026-09-30T08:07:47.132399Z`；TPEx `2026-09-30T08:07:51.311757Z`。

隔離投影 candidate：

`output/qa/ml_daily_source_row_research_projections/2026-09-30/95bde70a6e533158200541d6ee48b50136f3593162d877bb5f52b340096d3366/`

- CLI 狀態／exit：`completed_research_only`／0。
- candidate manifest SHA-256：`54658a2a9219e55a7ae49e8df8519d9299a258d38ae4aac0da2b4d6892e24ed1`。
- `observations.jsonl`：1,972 rows，3,848,832 bytes，SHA-256 `31e985f25103b32732be41b69c2fa27e14044659f23ed1f22ce52890449658eb`。
- CLI `verification_completed_at` 與 `candidate_available_at`：`2026-09-30T23:58:17.174641Z`；外層逐檔 readback verifier 完成於 `2026-09-30T23:58:17.537818Z`。
- `completion_receipt.json` 的 `awaiting_terminal_revision_validation` 是中間狀態。它不能單獨用來宣稱成功；CLI 最終結果是在 copied inputs、manifest、rows readback 與最後 revision equality 驗證完成後回傳。
- manifest／CLI 明確保持 `research_only=true`、`candidate_only=true`；`formal_credit`、`formal_oos_allowed`、`formal_source_contract_eligible`、`historical_pit_eligible`、`direct_ooc_compatible`、`features_included`、`labels_included`、`model_use_claimed`、`market_revision_cutoff_policy_evaluated` 均為 false。`unit_claimed=false`，不宣稱數字的計量單位。

外層 actual-write receipt：

`output/qa/ml_daily_source_row_projection_20261001/actual_write_run01.json`，38,795 bytes，SHA-256 `4ecd0d8efd3aeefe92e537865545ab4bc7a17792aaedd688c5d41d71847c61de`。receipt 保存 CLI argv/stdout/stderr/native exit、候選 manifest/receipt/rows readback、scope counts 與來源前後指紋。11 項 source/revision/database 指紋比對為零差異；SQLite 只比對 size/mtime metadata，沒有宣稱其完整內容 hash 已驗證。candidate 根目錄寫入前不存在，且來源／資料庫未被寫入。

## 預檢失敗與修正紀錄

所有下列輸出均留在 ignored `output/qa/ml_daily_source_row_projection_20261001/`，沒有覆寫原 raw candidate：

- `preflight_stdout.json`（SHA-256 `892b3dc04b0599dc391906360fafce5befe11c60ed2d7f2685427a2422a841f0`）：第一次 no-write preflight 拒絕 35,794 筆 TWSE raw table rows，因舊上限錯把 raw table population 與 1,095 筆 eligible 四碼列混為一談。上限改為 50,000；新增 35,794 raw rows／1,095 eligible rows 壓力 fixture。
- `preflight_run02.json`（SHA-256 `ebb7408fa8b7b66e4572d2509e696bd865723d5bb13a67e6d8cc27bb1d222196`）：第二次 no-write preflight 發現 TPEx 8440「漲跌」token「除息」。新增只對 TPEx `漲跌` 欄接受此確切 annotation 的分支；保留 token，`value_int`、`scale` 為 null；未知文字仍拒絕。
- `tpex_change_annotation_diagnostic.json`（SHA-256 `8534a45123f721bd0243c0f06ed63bbf28913ea241b48d295cae3f0c1e03b0fe`）：保存 annotation 欄位與原來源 raw／receipt 身分，沒有另行 HTTP 抓取。
- `preflight_run03.json`（SHA-256 `333c40821e53a115d5f7bf48bf9dee94a5163555b00267b952f919eef574d2f6`）：第三次 no-write preflight exit 0、1,972 rows、估計 10,046,827 bytes，且正式 candidate output root 不存在。外層 helper 曾因比較 JSON 型別方式錯誤，保留原 `inputs_revision_and_database_metadata_unchanged=false` 字串，不回寫掩蓋。
- `preflight_run03_readback_addendum_67d29043aa144a569f07cd7db655032c.json`（SHA-256 `0a5c6f5bd67e30b1cf500110925f68fcae90bb759bdf5dc3a9e9d8020cff6ea7`）：按 11 條明確路徑重新比較，size、UTC mtime ticks 與有提供的 SHA 全數相同；SQLite 為 metadata-only。根據此項獨立核對，source/revision/database 的 11 項比對零差異。
- `actual_write_guard_abort.json`（SHA-256 `4a94bd524fc9619062c2c912bc565c8fca22fb39fabd99d28c0ff234e7196cda`）：第一次 outer guard 在啟動 Python 前中止，記錄 CLI `not_started`、零寫入及 helper comparator 的原因；相同結構 control 中故意改動 size/hash 均被拒絕。它不是 Python CLI exit code，也沒有 candidate side effect。

## 驗證

- Focused tests：`19 passed`；測試包含合法 raw-table 大小與 eligible scope 分離、decimal／annotation 行為、未知 token fail-closed、重複 JSON keys／非有限數值拒絕、bounded coefficient／scale、不可變來源與 create-only/readback。
- 命令：`.\.venv\Scripts\python.exe -m pytest tests\test_ml_daily_source_row_research_projection.py -q -o addopts= --basetemp .tmp_ml_projection_acceptance_20261001`
- Syntax：`.\.venv\Scripts\python.exe -m py_compile data_module\ml_daily_source_row_research_projection.py scripts\project_ml_daily_source_rows.py tests\test_ml_daily_source_row_research_projection.py`
- Scoped type checks：`.\.venv\Scripts\python.exe -m mypy scripts\project_ml_daily_source_rows.py` 及 `.\.venv\Scripts\python.exe -m mypy data_module\ml_daily_source_row_research_projection.py tests\test_ml_daily_source_row_research_projection.py` 均通過。
- `git diff --check` 通過。pytest 顯示 sandbox 無法寫 repo `.pytest_cache` 的警告；以 basetemp 隔離測試輸出，未影響測試結果。

## 限制與後續

> **階段狀態更新：** 本節記錄投影撰寫時尚待實作的排程 hook。後續接線結果見 [scheduler hook QA](SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)；自然 Task 驗收仍待完成。

這是對已保存 2026-09-30 source candidate 的單日 research projection，不是 general revision-aware raw build，不包含歷史 partitions、features、labels、Direct/OOC consumption 或 source unit acceptance。9/30 原始 source receipt 時間在當日 cutoff 之後，且本投影沒有評估 cutoff policy，故不能回填 PIT 或歷史可得性。

下一步若接入每日排程，必須在同一次 runner 內僅於 prospective capture 返回 `captured` 或已驗證 `already_captured` 後，使用該回傳的 exact manifest path/hash 啟動投影；capture 失敗不得啟動。投影 child 失敗不得改寫 core collection／Formal revision hold 的狀態或 exit。需另建每次 run 的 create-only terminal receipt，並由 runner 對輸出 readback 和 exact pins 完成驗證；不能以 mutable latest 或 `awaiting_terminal_revision_validation` 中間 receipt 宣稱完成。此排程 hook 尚待實作與自然 Task 驗收。

# Git 排除與不應提交清單

> 給 Codex / Agent 接手時判斷 working tree 用。看到這些項目時，不要因為它們出現在 `git status` 就順手 stage。

## 已由 `.gitignore` 排除

這些是本機快取、工具暫存或 agent 工作目錄，不應提交：

- `.superpowers/`：Superpowers plugin 的本機工作狀態。
- `/meta_data/`：repo 根目錄下的背景任務狀態與 runtime log；正式資料根目錄 `{DATA_ROOT}/meta_data/` 不在 repo 內，不受此規則影響。
- `**/.tmp.driveupload/`：文件或工具在任意工作目錄建立的雲端上傳暫存目錄。
- `/.tmp_*/`：repo 根目錄下以 `.tmp_` 開頭的隔離測試／pytest `--basetemp` 輸出；只排除根目錄此命名模式，不涵蓋其他目錄中的同名資料。
- `/.tf_*/`、`/.tc1/`、`/.tc2/`：2026-09-27 R031 QA runner 產生的根目錄短 TEMP／C1 隔離輸出；這些精確前綴與目錄只供該次 QA 暫存，不涵蓋其他根目錄來源或一般新建 source files。
- `/.t/`：repo 根目錄下的本機 QA 暫存（例如 capture、full-stack、OS temp 與 replay diagnostics）。只忽略此根目錄，不要刪除或提交其內容；來源不明時先保留並查明 owner。
- `/.obsidian/`、`/Untitled.canvas`：本機 Obsidian 設定與目前這份根目錄草稿白板；不使用全域 `*.canvas` 規則，以免排除其他可能屬於專案的白板。
- `docs/agents/shared_state/active_task.yaml`：Agent 本機任務交接狀態；各工作階段可自行更新，不應提交。
- `docs/agents/shared_state/handoff_log.md`：本機跨 Agent 交接紀錄；可能包含進行中工作資訊，不應提交。
- `.pytest_cache/`、`.coverage`、`htmlcov/`、`.tox/`、`.cache/`：測試與 coverage 輸出。
- `*.log`、`logs/`：執行日誌。
- `venv/`、`env/`、`ENV/`：本機虛擬環境。
- `.env*`：本機環境變數與密鑰設定；`.env.example` 例外，可提交。
- `*.db`、`*.sqlite*`：本機資料庫輸出。
- `output/`：QA、驗證、報告匯出與本機執行輸出；2026-06-30 起不應再追蹤於乾淨 `main`。
- `/qa-cache*/`：隔離 QA runner 的本機 cache（例如 SQLite WAL、XML、JSON receipt）；只保留本機，不應 stage 或提交。
- `**/graphify-out/`：Graphify 產生的本機知識圖譜、HTML、JSON、報告與快取；可由原始碼重新建立，不應 stage 或提交。
- `/test.parquet`：根目錄臨時資料樣本 / 測試產物，不應提交。
- `downloads/`、`temp_downloads/`、`tmp/`、`temp/`：下載與暫存檔。

## 已從乾淨 main 移出的易變輸出

以下檔案類型曾經被 Git 追蹤，但屬於本機驗證輸出；2026-06-30 清理後，乾淨 `main` 不應再包含這些產物。若它們在本機重新生成，應維持 ignored，不要 stage：

- `output/**`
- `output/qa/**`
- `test.parquet`

若任務需要保存可分享的 QA 結論，請寫入 `docs/06_qa/` 的摘要 / audit / issue 文件，而不是提交 `output/` 底下的 raw output。

## Agent 操作規則

- Stage 前一定先跑 `git status --short`，確認只包含本次任務檔案。
- 不要 revert、刪除或清理你沒有產生的 dirty files。
- 若遇到不在本文件中的新暫存/輸出目錄，先判斷來源並更新本文件，再決定是否加入 `.gitignore`。
- 若是正式資料根目錄 `DATA_ROOT` / `OUTPUT_ROOT` 內的資料，遵守 `docs/agents/shared_context.md` 的資料完整性規則，不做破壞性操作。

## 2026-10-09 本機交接排除

本機 .git/info/exclude 保留並排除已識別 .h20pytest_tmp_20261007、.h20snapshot_tmp_20261008_*、.qa_f17_*、.qa_temp_technical_*、兩個 .rptv4-* 與 .t-ouxfxe6t 暫存；根目錄六個殘留來源及 scripts/maintenance 一次性本機封存工具不提交、不刪除。精確範圍與接手審查見 docs/06_qa/BALDR_COMPLETION_HANDOFF_20261009.md。此規則不是對新正式來源的通用忽略。

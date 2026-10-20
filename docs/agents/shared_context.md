# 共同安全與工程規範

> 本文件是所有平台、角色與任務共用硬規則的唯一權威。其他 Agent 文件、平台適配與提示只引用本頁，不複製或改寫規則。產品狀態與領域事實仍依各自 Scoped SSOT。

## 工作邊界與資料保護

- 使用繁體中文回覆與更新文件；新增程式註解也使用繁體中文。只在使用者授權的範圍內工作，不自行擴張功能、資料、清理或發布範圍。
- 不覆寫、revert、刪除或清理使用者或其他 Agent 留下的未提交變更。先辨認工作目錄、HEAD 與 dirty tree；只整合本任務成果。
- 不得刪除、覆寫、重建或破壞正式資料根目錄內的原始／每日資料。位置由 `data_module/config.py` 的 `TWStockConfig` 決定，預設 `F:/Min/Python/Project/FA_Data`，可由 `DATA_ROOT` 覆蓋。資料審計預設唯讀；任何寫入、migration、backfill 或重建都必須有明確授權與精確範圍。repo 的大型 `output`、`dist`、`.t` 經 junction 存於 `F:/Min/Python/Project/BaldrStorage`。
- 不確定資料所有權、現行產品事實或操作影響時，先查對應 Scoped SSOT 和證據；無法裁決時標示需要確認，不猜測現況。
- 刪除、清理、正式資料寫入／重建、migration、分支或工作樹清理，以及其他不可逆操作，只能在明確授權和完成影響／恢復性檢查後進行。不得使用寬泛 wildcard 或清理不明目標。

## 量化精度與時間安全

- 策略、回測、推薦、篩選、資金、倉位、風控、交易成本、滑價、績效與風險指標等核心計算，嚴禁新增裸 `float` 計算。使用 `Decimal`、整數分／股／基點／萬分點或明確定義的量化格式。第三方套件、資料轉換與圖表所需浮點數必須留在隔離的分析或展示邊界，不得回流策略決策。
- 實作或修改策略、回測、推薦、篩選、績效或 benchmark 邏輯前，先做 Look-ahead bias 自查。訊號日期、特徵窗口、標準化樣本、排序與篩選 universe、停損停利、benchmark 對齊、交易價格與持倉更新只能使用決策當下可取得的資料；月營收、估值等 PIT 資料需滿足 `available_date <= decision_date`。
- 無法證明資料時間可得性或精度符合要求時，停止該部分工作並明確記錄阻塞點。
- 台股 `日期` 可能是數字型 `YYYYMMDD`；Recommendation replay／Portfolio backtest 必須使用共用 `parse_stock_dates()` 或明確格式，不能裸用 `pd.to_datetime(series)` 造成 1970 epoch 誤判。歷史 replay 保留 candidate limit／prefilter，回歸點位不足或 x 退化時安全跳過。

## 變更、驗證與文件交付

- 依既有架構、介面與驗收方式增量修改；破壞契約時需先提出明確遷移與相容路徑。
- 已授權的實作任務包含完成必要的影響檢查、QA 與文件同步；不可因角色分工或「只照字面執行」停在半成品。驗證失敗須保留失敗並處理或交接，不得降低測試強度或宣稱未執行的項目通過。
- UI 改動完成後必須執行：`.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=`、`.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py`，以及 `.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`。修改 Python 檔後執行 `.\.venv\Scripts\python.exe -m py_compile <changed-python-files>`；量化核心檢查依任務適用的防線執行。
- 文件同步依 `docs/00_core/DOC_COVERAGE_MAP.md`、`docs/00_core/FEATURE_DOCUMENT_MAP.json` 與 `docs/00_core/PRODUCT_CHANGE_WORKFLOW.md`。使用者可見操作變更必須同步 `docs/07_guides/APPLICATION_MANUAL.md` 的入口、步驟、參數、結果判讀、安全限制與排錯。
- Root 對任務範圍、風險複核、驗證狀態與最終交付負責。依任務路由加入相應角色，不將 QA、資料或架構複核責任留在模糊的「之後再看」。
- QA 收據、原始輸出與未驗證界線須依原貌記錄；有限測試結果不得外推為整體產品或 Gate 接受。

## Python 驗證程序與資源

- 同一任務一次只執行一組 Python 重型驗證；在授權的多 Agent 任務中，subagent 只做靜態閱讀與候選編輯，pytest、mypy、compile、產品 import 與 QA 子程序由 root 序列執行。
- Windows 驗證使用可讀回上限的 Job、kill-on-close 與同工作區執行鎖。受控補完預設全 Job committed memory 上限 8 GiB、最多 12 個程序，啟動前至少保留 8 GiB 可用 RAM；不得默默放寬資源上限或原驗收門檻。
- 工具等待逾時或輸出中斷時，追蹤同一 session／Job，不另開同一驗證。開始下一輪前確認前一輪 terminal、Job 剩餘程序為 0、process／Job handles 關閉及執行鎖釋放。
- 異常與取消時回收該次 Job 的整棵 owned process tree。以 PID、建立時間、來源、父系與 Job membership 判定所有權；PID 可能重用，不得全機終止 Python 或清除其他專案、IDE、MCP 服務。只有確認屬於本任務的殘留程序才可回收。正常 QA 若依賴強制清除才排空，不算成功。

## Git、分支與工作樹

- Stage 或 commit 前先讀 [`git_exclusions.md`](git_exclusions.md)，並核對 `git status --short`；只納入本任務檔案。本機暫存、工具輸出、正式資料與非本任務 QA raw output 不得順手提交。
- `dev` 是開發整合主線，`main` 是穩定版本；整合到 `dev` 不代表取得修改或推送 `main` 的授權。分支命名與工作樹生命週期見 [`multi_agent_workflow.md`](multi_agent_workflow.md)。
- 新增工作樹前先找可重用的工作樹；清理前確認沒有其他聊天或程序使用且可還原。不得為了整潔而破壞未提交內容。

## 任務狀態與並行所有權

- 多階段、需恢復或需交接的任務使用 `output/tasks/<task_id>/task.json`；由 `scripts/document_control.py init-task` 建立，命令與欄位契約以該工具和 `docs/agents/shared_state/README.md` 為準。
- `task.json` 是被忽略的本機協作狀態，不是產品狀態或領域 SSOT。每個 task ID 由單一 root／task owner 負責更新；並行協作者回報給 owner，不同 task 不共寫同一檔案。
- 現有 `docs/agents/shared_state/active_task.yaml`、`handoff_log.md` 與 resume prompt 是既有 singleton／交接資產；不得自動搬移、覆寫、追加或刪除。它們與新 task JSON 可並存；若需遷移，必須由其現有 owner 明確處理並保留原件。

## 權威與更新

- 目前狀態看 `docs/00_core/PROJECT_SNAPSHOT.md`；產品方向看 `PRODUCT_ROADMAP_POST_REFACTOR.md`；工程順序看 `ROADMAP_6M_ENGINEERING.md`；長期成熟度看 `VERSION_ROADMAP_V2_1_TO_V4_0.md`；現行架構看 `docs/01_architecture/system_architecture.md`；目標設計看 `target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md`；操作看 `docs/07_guides/APPLICATION_MANUAL.md`；外部候選研究看 `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`；舊工作承接看 `LEGACY_ROADMAP_CARRYOVER.md`。`DEVELOPMENT_ROADMAP.md` 與 `DOCUMENTATION_INDEX.md` 是導覽，不取代主題權威。
- 新增、移動或歸檔文件時更新適當領域 README／主題索引，中央 Index 僅在主要入口或權威邊界改變時更新。歷史或日期化文件不得覆蓋現況權威。

## 更新記錄

- 2026-10-12：收斂共用安全、精度、程序、Git、交付與任務狀態規範；角色與平台文件改為引用本頁。

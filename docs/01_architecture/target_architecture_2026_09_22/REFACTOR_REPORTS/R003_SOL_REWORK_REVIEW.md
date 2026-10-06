# R003 Luna 回修之 SOL 初審

## 判定

R003 回修已提供可判定的 terminal、A/B hidden-state、stale UI、worker lifecycle、progress／receipt marker 與 nested alias characterization。這是送 Gemini 獨立審查前的初審，不是最終 PASS 或 Wave 1 release；所有證明現況不符合最終架構的案例均如實列為 gap，沒有在 R003 偷改 production。

## 實際 scope 與 acceptance 證據

- 只聲明修改 `tests/test_recommendation_execution_state_characterization.py` 與 `REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`。起始 SHA-256 分別為 `58570C03BBCE9EFE4FE3DEB6298184C48DCF0674D6573FC1F8A98E83D3452E10`、`36E6F55896854BB1A05EA229D0D9289B7DB9437949108D517E81881C3B7C12C0`；回修後為 `ec89cda7b861b6467681fb21f3956a89c8b8335f03eaee74ceba68bae22cc020`、`07a81eae69166ad22bdd89ed239e77e30434ce01115d5a58984558ed6aea7054`。HEAD 仍為 `391b057c`。
- completed-nonempty、completed-empty、validation rejection、raised failure、cooperative cancellation 分別由 service call、worker signal 與實際 view callback 觀察；沒有把 `[]` 當唯一 terminal 判據。
- 使用 barrier 使 A 完成後 B 在同一 service 開始，再延後 A 的實際 view callback；測試明確顯示 A callback 覆寫 last-good，且共用 `last_*` 指向 B。另以實際 `RecommendationService` 空資料 invocation 驗證延後讀 A context 只能取得 B state。
- 巢狀 input mutation 及回傳後 caller/service 兩端 mutation 都有 alias 斷言；這是 INV-08 的現況缺口。native thread completion、managed registry cleanup 與 QObject destroyed signal 有可觀察 oracle。
- progress shape/order 與測試用 receipt marker 在 cancel/failure terminal 之前的可見次序均有斷言；報告明確聲明未用正式 ML writer 或模型，不能外推正式 receipt durability。

## SOL 獨立驗證

V-EXEC focused suites：`.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py tests/test_ui_qt_task_worker.py tests/test_ui_qt_shutdown_coordinator.py "tests/test_ui_qt_portfolio_view.py::test_portfolio_stale_worker_callback_cannot_replace_new_generation" -q -o addopts= -p no:cacheprovider`

結果：`39 passed in 1.69s`，exit 0。因測試使用多個 QThread/barrier，SOL 另將 R003 新測試獨立重跑五次，每次 `11 passed`、exit 0；changed Python 的 `py_compile` exit 0。

## Gemini 獨立審查焦點

請檢查 A/B barrier 和 view probe 是否確實避免 timing 假陽性、receipt marker 的證明範圍有沒有被報告擴張、各 terminal event 是否與實際 worker/view 行為一致、worker teardown 是否可穩定重跑，以及任何未列出的 nested alias 或 last-good gap。只提 R003 原 scope 內的精確 findings。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

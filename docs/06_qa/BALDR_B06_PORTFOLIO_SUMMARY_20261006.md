# B06 持倉分帳與估值摘要交接

> **日期與狀態提示（2026-10-10）：** 本文件結尾「待中央」是早期交接狀態；後續 MainWindow route／paths 注入與 P2／M03 有界 readback 見[架構補記](../01_architecture/system_architecture.md)及[BALDR 第二波 integration receipt](BALDR_SECOND_WAVE_INTEGRATION_20261006.md)。這只更新 bounded caller wiring 狀態，不代表 Paper producers、正式資料啟用、migration、產品資格或真人／Native 驗收已完成。

日期：2026-10-06。狀態：限定 presenter／注入接口完成，待中央整合；不宣稱 UX14 或私人 Paper 全鏈完成。

## 範圍與基線

- Base：`ba4e9e59da7946aa66fd5eac3729e091dfe5cced`。
- Branch：`lane/baldr-b06-portfolio-summary-20261006`。
- Worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b06-portfolio-summary`。
- 唯一 dev 整合 owner：`01a11020-88c2-7506-acc3-d51ecb674032`。
- 只改 `portfolio_view.py`、`user_declared_holding_research_widget.py`、兩份原有指定 UI tests、新 B06 tests 與本 QA 文件。
- 原主 plan、inventory／review、Manual、main、config、shared DTO／codec、金融 core／storage 都未修改。B09 新 route API 未 cherry-pick；本包沿 base 原 DTO／service 編譯及測試。
- 未使用正式資料、migration、Task、ACL、Native、fit、交易或 push，沒有重開七個有限 closed 或性能例外。

## 可見行為

頁首「分帳查看」能選真實／手動登錄帳、使用者聲明研究帳或 Paper 模擬帳。手動登錄未核券商成交；選聲明或 Paper 時隱藏手動帳金額卡及持倉表，開原有該帳工作區，不合併總值。選回手動帳恢復原資料與日常摘要，沒有重新計算或轉移資料。

手動帳投入與已實現損益沿原毛額，已記錄交易費稅沿既有 `recorded_trade_costs`，未知不補零。未讀取卡片保持未知。估值日期取同一 position_id／stock_code 快取報價，且價格須與原 DTO 相同；`source_summary` 的日期或 `last_trade_date` 不構成報價證據。缺價／缺日期、異日、價格失配、其他股票快取及未來日期不顯示完整市值。原同日齊全值沿既有 Decimal 市值公式，沒有新增金融公式。

持倉表先建立同列快取，摘要與金額卡再消費該份資料，不新增查價。舊報價日期明列，不代表目前估值；前值／滑價／換手率／部位集中度沒有已提供值時列未知。不把缺 health、Paper 狀態或空列判為人工帳安全。下一步沿原「個股研究」及 selected row exact source；原結果未驗證就保留空 result_id／unlinked。

聲明表新增估值日期；明細並列評估日、使用者聲明單價與費稅／滑價／換手率／集中度缺件。Decimal 使用固定小數字串呈現，不經 float 或額外四捨五入。帳面變化不代表已實現績效；原 CRUD、CAS revision、取消／stale gate 保留。

## 中央注入接口

`PortfolioView.__init__` 新增 keyword-only：

```python
user_declared_store: UserDeclaredHoldingResearchStore | None = None
user_declared_portfolio_id: str = "default"
paper_readiness_service: PaperPortfolioReadinessService | None = None
paper_weekly_evidence_service: PaperPortfolioWeeklyEvidenceService | None = None
```

原 `user_declared_research_service` 注入保留；與 `user_declared_store` 同時提供則拒絕。只注入 store 時用原 service 建構子，不另選路由。`user_declared_portfolio_id` 必須非空，傳到聲明 widget 的 `portfolio_id`；中央須傳該 route 的 `identity.key`。

入口 guard 在任何 legacy service 建構前檢查：config 任一 `personal_store_root` 或 `personal_store_mode` 已配置，就必須注入聲明 store／service 及完整 Paper service pair；缺件 `ValueError`，不回退舊服務。完全無配置時維持既有 defaults。私人 notes 與 generic store 未混用。

同一 constructor 對 Paper pair 精確核對 `portfolio_id`、`benchmark_id`、`state_db_path`、`benchmark_db_path`、`cost_ledger_db_path`；缺半組或任一失配即拒絕。注入實例原樣保存，不再自行 resolve。focused 負例逐欄驗失配，也驗 root-only、personal、legacy_read_only 缺注入。此核驗不提升 producer writer／正式 Paper 資格。

中央 main 最小接線位置為原 `PortfolioView(...)` composition，傳入已由 B08／B09 建構的聲明 store、身份與同 route 的兩個 Paper service；不在 view 選路由。本包不包含 main patch，中央已有 route／mode owner自行接線。

## Exact-result 原 fail 的判讀

保留原 node：`tests/test_ui_qt_stock_research_navigation.py::test_mainwindow_portfolio_return_requires_current_exact_result_identity`，原 `result-r1` assertion 及 R1→R2 stale rejection 都未改。

OS Temp 第一輪另見 Portfolio sorted-row exact-result fail：canonical query 開 legacy namespace 的 no-follow 祖先 handle 時，`CreateFileW C:/Users/archi` 得 `Errno 5`，轉 `ExecutionArtifactIntegrityError`；view 正確 fail-closed 成空 result_id。repo 合成 basetemp 原導航 node `1 passed`，兩個原指定 UI 檔 `39 passed`。這不是長路徑產品驗證；沒有縮短正式來源、放寬 no-follow、改 assertion 或補 guessed result_id。

main 現有 `_return_to_research_source` 已傳 `context.result_id or None`，且 Portfolio exact 失配已有通知；在 repo fixture 不存在待修 main 產品 defect。中央可用 repo 下新隔離 `--basetemp` 跑該 node，避免 sandbox 對 home 祖先 handle 的限制；B02 真長路徑驗證保持其原 scope。

## 驗證與 raw 證據

使用 repo 根原 `.venv/Scripts/python.exe`，workdir 為本 lane worktree：

```text
python -X utf8 -m pytest tests/test_baldr_b06_portfolio_summary.py tests/test_ui_qt_portfolio_view.py tests/test_ui_qt_user_declared_holding_research.py tests/test_ui_qt_stock_research_navigation.py::test_mainwindow_portfolio_return_requires_current_exact_result_identity tests/test_ui_qt_v5_research_views.py::test_portfolio_summary_uses_plain_terms_and_marks_last_good_data -q -o addopts= --basetemp=.tmp_b06_handoff_20261006 --junitxml=output/qa/baldr_b06_20261006/focused_handoff.xml
python -X utf8 -m mypy ui_qt/views/portfolio_view.py ui_qt/widgets/user_declared_holding_research_widget.py --follow-imports=silent
python -X utf8 -m py_compile ui_qt/views/portfolio_view.py ui_qt/widgets/user_declared_holding_research_widget.py tests/test_baldr_b06_portfolio_summary.py tests/test_ui_qt_portfolio_view.py tests/test_ui_qt_user_declared_holding_research.py
```

Focused `55 passed`；targeted mypy 兩檔通過；五份 Python 語法及 diff whitespace 通過。完整 mypy／Workbench／update validator 按使用者要求留中央穩定 union 跑一次，本 lane 未重跑。

Raw 位於本 worktree `output/qa/baldr_b06_20261006/`，不提交：final JUnit、三帳 `*_handoff.png`、`offscreen_receipt.json`（圖像 SHA-256 與兩個 UI source SHA-256）。offscreen 1000×800 三帳切換及捲動區已核對；初始系統字型因 sandbox 原生讀取呈方框，QA 以同機 `msjh.ttc` bytes 載入解決，沒有改產品字型／主視窗。Native／縮放／真人待中央另驗，offscreen 不冒充 Native。

Final JUnit SHA-256：`5f2aa5128d99012bd43f4294196fbcfccd732d79d8c5183fd246638f9572f8eb`；offscreen receipt SHA-256：`bde1a1a01cc01b412d367d641b6b169bb3de227df3ab7a39f045167b4367a3e8`。完整 commit 與 Git blobs 由交接訊息回傳，避免本文件自我 hash 循環。

## Manual 精確同步提案（僅中央套用）

在持倉操作章補下列文字，涵蓋入口、步驟、參數、結果、安全與排錯：

> 在持倉頁「分帳查看」選手動登錄、聲明研究或 Paper。三帳各用自己的資料與總值；手動登錄未核券商成交，聲明成本只供研究，Paper 非實盤績效。切聲明／Paper 時不顯示手動帳金額卡，沿原分頁核對資料。手動帳成本／已實現損益為毛額，已記錄費稅另列；估值日依同列原報價，資料更新時鐘不等於估值日。缺價格、日期未知／異日／未來、或價格與同列來源失配，市值顯示未知；前值、滑價、換手率與集中度缺件不補零。選持倉後按「個股研究」沿同股原來源，未驗原結果維持未連結，不能借今天結果補舊身份。聲明列可看估值日，明細顯示評估日與聲明成本；過期、缺件或沒有精確健康資料時不能判安全。刷新取消／失敗保留上次資料並明示未確認最新。私人 root／mode 已配置但中央服務未注入，頁面拒絕初始化；檢查主程式同帳服務 composition，不回退舊資料，不做自動 migration。

## 回滾與剩餘事項

| 檔案 | 類型 | 回滾 | 風險 |
|---|---|---|---|
| 兩個指定 UI 檔 | 修改 | 中央整合前放棄本 lane commit；整合後僅 revert 本包 | 失去新呈現／注入接口，須同時調整中央 caller |
| 兩個原 UI tests | 修改 | 隨本包還原 | 金額日期未知及聲明明細驗證消失 |
| 新 B06 tests／本 QA 文件 | 新增 | 隨本包還原 | 交付證據消失，原資料無影響 |

回滾前確認 dirty／owner，僅對本包範圍操作，之後跑相同 focused；本 lane 不清理或實際回滾。資料／Look-ahead 自查：只讀現成值與同列已存在快取，不回填較新行情、無核心金融公式或裸 float 新增。

剩餘：中央 main 注入 B09 route services、Manual／Scoped SSOT 同步與穩定 union；B09 私人 route／新程序完整 backend 另包驗收；正式 migration／producer writer／Native／真人均未授權。本包只 local commit/readback 後等待整合，不 cherry-pick dev、不 push。

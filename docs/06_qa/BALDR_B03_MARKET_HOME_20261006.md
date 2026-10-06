# B03 首頁與市場判讀限定收據（2026-10-06）

主整合 owner：thread `01a11020-88c2-7506-acc3-d51ecb674032`。本 lane 為 `lane/baldr-b03-market-home-20261006`；base `a42b2cb9df44b2fd928104ae02992b0e557c2a39`，工作樹 `output/worktrees/baldr-b03-market-home`。本地 commit 的完整 HEAD 與 receipt hash 由同目錄 `output/qa/baldr_b03_20261006/handoff.json` 及交接訊息提供，避免文件嵌入自身 commit hash。

沿唯一原計畫第 4 節三層閱讀、第 5 節搜尋／返回、第 6.1 節首頁及 Astra B03；未另建 dashboard、搜尋引擎或研究計算。原 plan 唯讀 SHA256：`9730be99e060ea467827a532abb24a2342db1a3ecc2e5f756d0a979ee2a28543`。既有七項有限工程接受不重開，整項 UX03／13 及 Native／真人未因此升 done。

## 完成行為與 API

- 原 guided home 新增「看盤勢／持倉健康／選股研究／個股研究」，使用原 market／portfolio／recommendation／stock research callbacks。市場及持倉重點按鈕直接導覽，完整來源仍可由原收合面板查看。
- 股號搜尋為明示 4–6 位數字代號；Enter 或「開啟當下研究」沿 `ResearchStockContextDTO` 到既有個股頁。`source_kind=explicit_latest_stock_research`、`source_workspace=workbench`，不填候選的 decision/data/result/source 身份，來源可用性由原個股頁核對；無 callback 停用。沒有名稱搜尋或 autocomplete。
- 原候選 `_open_daily_candidate_research` 保留保存結果／股號／決策日／資料日／source_id。原 generic 返回工作區 API 沿用；主 owner 接受，不新增主路由。完整個股六頁與股票下鑽未修改。
- 首層技術詞翻譯為白話，原文保留 tooltip 與原完整來源；歷史時點資格不足等限制仍可見。
- 大盤檢測與連續刷新保留技術細節 checked 選擇，預設收合。摘要只讀來源明示 bool；缺欄位保未知，不補 false。來源 `error` 走失敗狀態，不展示服務相容用的預設 Trend。風險／下一步首層可見，不將匹配度當勝率。

Look-ahead 自查：本包只翻譯已傳入 DTO 與導覽，不查新日期、篩選、排名、重算或新增金融公式。明示當下搜尋不改原保存身份。沒有新增核心 float 計算。

## 驗證

使用母 repo `.venv/Scripts/python.exe`，cwd 為本 lane 工作樹，`QT_QPA_PLATFORM=offscreen`。

```powershell
$py = 'C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe'
& $py -m pytest tests/test_baldr_b03_market_home.py tests/test_ui_qt_v5_workbench_guided.py tests/test_ui_qt_workbench_view.py tests/test_shared_market_research_consumers.py tests/test_ui_qt_market_regime_view.py -q -o addopts= -k 'not test_market_regime_detection_shows_technical_details' --basetemp=C:/Users/archi/AppData/Local/Temp/baldr-b03-final-20261006 --junitxml=output/qa/baldr_b03_20261006/focused.xml
& $py -m mypy ui_qt/views/workbench_view.py ui_qt/views/market_regime_view.py --follow-imports=silent
& $py -m py_compile ui_qt/views/workbench_view.py ui_qt/views/market_regime_view.py tests/test_baldr_b03_market_home.py
git diff --check
```

結果：63 passed／1 deselected，9.00 秒，程序 exit 0；targeted mypy 2 檔成功，三檔 compile／diff check 成功。含 13 個 B03 新案例：預設收合／手動展開各連續刷新兩次、未知條件、來源 error／例外、四用途、原保存身份與當下搜尋隔離、無效股號、未接線停用、技術原文保留；既有案例驗證取消／stale、切來源、原路由與最後可信內容。

額外命令：`pytest tests/test_ui_qt_stock_research_navigation.py tests/test_ui_qt_daily_market_research_main_routing.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/baldr-b03-routes-20261006`，結果 5 passed／1 failed。失敗為 `test_mainwindow_portfolio_return_requires_current_exact_result_identity`，Portfolio 傳出的 result_id 空字串而非 result-r1；在未套 B03 的母 repo base 重跑同 node 同樣失敗。此實際 caller 缺口留 B06/B09 待修，不能當 baseline pass。未修改其來源檔或測試。

## 中央接手與驗收限制

中央已鎖 `tests/test_ui_qt_market_regime_view.py`，並承接舊 `test_market_regime_detection_shows_technical_details` 的最小改動：先 `view.layer3_group.setChecked(True)` 再檢測，保留原指標 assertions。本 lane base 上該舊斷言仍要求 auto-expand，因此明示 deselect；新預設收合行為由 B03 兩次刷新案例驗證。不恢復 auto-expand。

強制 Workbench／update validator／全 roots mypy 由中央穩定候選序列跑一次，本 lane targeted mypy 不替代全 roots gate。未跑 Native／真人、正式資料、Task、ACL、migration 或模型訓練。1000×835 offscreen 截圖只核面板結構；本環境 Qt 缺 CJK 字型，中文字呈方框，不能宣稱文字視覺／縮放接受。raw PNG／JUnit 保留工作樹 ignored output，不提交。

Manual 由中央就地同步：首頁四用途、代號搜尋的明示當下身份與原候選分流、Enter 操作、未接線停用／無效代號排錯、大盤刷新保持收合、未知條件不當反證、匹配度不是勝率。主 `main.py` market callback 維持既有市場總覽，不擴改；update／runtime 影響摘要在其 owner scope。

## 回滾

未整合時不採納本 lane commit。整合後先確認其他 dirty，僅 revert 本包 commit；兩 view 回到 base，專屬測試與本 QA 摘要撤回。無資料回滾或 migration 風險，UI 四用途／搜尋會撤回。不得清理他人 branch／worktree／dirty。未 push 或整合 dev。

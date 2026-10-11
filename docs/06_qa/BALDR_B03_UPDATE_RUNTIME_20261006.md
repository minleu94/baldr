# B03 Update／Runtime 餘項限定交付

> **後續狀態導覽（2026-10-11）：** 本文只記錄 2026-10-06 的 B03 兩頁呈現餘項，不代表全 B03 或正式運行接受。後續中央整合已同步 Manual §4.1、§11、§11.1；Native、Windows Task 與真資料更新仍未驗收。細節見[第二波中央整合收據](BALDR_SECOND_WAVE_INTEGRATION_20261006.md)。

日期：2026-10-06。這是原產品體驗計畫 B03 的兩頁呈現餘項，不是全 B03、全部 UX 或正式運行接受。

## 固定來源與所有權

- base：`175d9c502985165e3b591af71f138ce4f3b9de6d`。
- branch：`lane/baldr-b03-update-runtime-20261006`。
- worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b03-update-runtime`。
- 中央 owner：`01a11020-88c2-7506-acc3-d51ecb674032`。
- 原計畫、Astra inventory、Sol review 均僅讀取；原計畫讀取時 SHA-256：`c4126a56cbe6a1c28b541222f11616af26b18a7149ed29ac8d402a53e729fc85`。不改其 prefix 或狀態矩陣。
- graphify 2026-09-29 舊圖只定位 `UpdateView`／`RuntimeView`，實作判斷回查固定 base 原碼；不把舊圖當目前接線證據。
- managed worktree API 回報需要 local／SSH／WSL task；依使用者既有授權以 Git 建立上述獨立工作樹。未重用或清理其他 lane。

## 行為與服務邊界

Update「全部資料」先顯示資料影響、最後成功完成、股價／技術指標各自資料日及下一步。成功完成取既有時間軸 `last_success_at`，資料日取同次來源 `latest_date`；不以目標資料日、現在日期或手動更新成功推造資料日。缺欄位、部分 payload 或狀態檢查錯誤均清除舊摘要日期、明示未知；錯誤原文仍留在既有卡片、明細與日誌。

「更新時間軸與執行歷史」、「候選資料（不代表正式可用）」、「官方來源候選與接受條件」、「使用資格與完整阻擋原因」預設收合。展開後仍是原時間軸、候選卡片、P0 表、readiness 表；沒有移除 blocker、授予資格或改變更新／取消 callback。刷新保留目前資料頁與收合狀態，表格按步驟／來源／lane 身分及歷史 Run 保留仍存在的選擇，不能沿用舊列號挑錯結果。

Runtime 首層改為「運作狀態與下一步」，分開說明日常工作、資料與保存位置、治理任務。現有 DTO **沒有最後成功完成日期或行情資料日期**，因此固定明示未知；每列原 `updated_at` 另標「觀測時間」，不升格為成功日期。頁面維持純 DTO 渲染、無直接檔案 IO。

Runtime 路徑、排程原始診斷、治理上下文／完整事件流可收合；保存結果每列先顯示中文狀態，raw status、job／lane、讀取狀態、時間來源、來源路徑與完整 diagnostic 保留在可展開的唯讀文字及 tooltip。重新整理按 job ID／path key 保留選擇，收合狀態不被 callback 改寫。未知 token、unavailable、未確認讀來源不能顯示正常；current scope 搭配無法讀取／降級事件檔亦不能在治理明細顯示綠色健康。歷史、未來時間、無法解析的事件仍採既有非 current 呈現。

不新增服務 API、worker 或 DTO。`main`、config、backend、runtime package、共用 DTO、Manual、原計畫及 Workbench 測試均未修改。不啟動真正更新、Task、ACL、migration、清理、模型訓練或 Native 操作。

量化／未來函數自查：只投影已回傳狀態與日期，不新增訊號、特徵、排序、基準、成本、績效、交易價或持倉計算；沒有新增裸 float 計算。既有治理拒絕率只用於其原監控呈現，不轉為金融決策。

## 限定驗證

共用 Python：`C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe`。cwd 為上述 worktree，`QT_QPA_PLATFORM=offscreen`。

| 命令／檢查 | 結果與範圍 |
|---|---|
| `python -m pytest tests/test_ui_qt_runtime_view.py tests/test_baldr_b03_update_runtime.py -q -o addopts= --basetemp output/qa/b03-temp-final` | **36 passed，2.25s**；既有 Runtime 12＋新增 B03 24，參數化案例去重，不累加重跑 |
| `python -m mypy --follow-imports=silent ui_qt/views/update_view.py ui_qt/views/runtime_view.py` | **2 source files clean**；不是 full roots mypy |
| `python -m py_compile ui_qt/views/update_view.py ui_qt/views/runtime_view.py tests/test_ui_qt_runtime_view.py tests/test_baldr_b03_update_runtime.py` | exit 0 |
| `python scripts/quant_guard_linter.py` | 精度與 look-ahead 白名單 gate 均通過；非完整量化正確性證明 |
| `git diff --check` | exit 0 |
| 980×835、390×835 的兩頁 offscreen 渲染 | 摘要可換行、內容可捲動；只是離屏 layout，不是 Native／真人接受 |

首個 pytest 呼叫因尚未建立 `output/qa` 父目錄而在 fixture setup 報 35 errors；建立隔離輸出父目錄後通過。此為執行環境設定失敗，未藉修改產品或刪 assertion 消除。Qt teardown 提示 `ui_qt.main` 尚未載入；本 lane 不匯入完整 App 或啟動其正式工作。

離屏初始字型清冊為空；渲染檢查另載入 `C:/Windows/Fonts/msjh.ttc`、`msjhbd.ttc`、`segoeui.ttf`，僅在 QA process 套用微軟正黑體，未改產品字型或環境設定。截圖保存在 ignored `output/qa/b03-render-fixture/`。

本 lane 未執行重型 Workbench／Update validator／全 roots mypy；依使用者指定由中央穩定 union 一次執行。Native、Windows Task 及真資料更新均未驗，不以離屏結果折抵。

## 本機證據與 blobs

以下 raw 輸出位於 worktree 的 ignored `output/qa/`，不提交。

| Raw 檔 | SHA-256 |
|---|---|
| `b03-focused-final.txt` | `2c17e63636030b9b3603d3469c349886f68a5d7036173ce1db8bb6c3dd8e77ef` |
| `b03-mypy-final.txt` | `0c37c4158c91ef55c724ba017bf6465f26018199badb08e3ff13f98acdf056c2` |
| `b03-quant-final.txt` | `87be6a99ac7beb04aa3fa6497b13b81b3bf6d4371887b667e6dc8c2a99681e3a` |

Git 正規化 blob：

| 檔案 | Blob |
|---|---|
| `ui_qt/views/update_view.py` | `fd2aeb496318a1e0cc6fdb58679a4469a5db6143` |
| `ui_qt/views/runtime_view.py` | `6b971f0b8a2c8fd1fa795a9d143d241c88923eb3` |
| `tests/test_ui_qt_runtime_view.py` | `c8dc40bb91659bfe83498c8254682113bff37c27` |
| `tests/test_baldr_b03_update_runtime.py` | `1f9150236e011b4cfa5b83ca5e9d6314df3d413a` |

## Manual 精確補文交中央

只提供下列補文，沒有直接寫 Manual。中央整合兩頁後就地更新，避免只在尾端追加造成現行章互相矛盾。

### 4.1「全部資料看板」替換現行排版段

替換以「一般桌面寬度的『全部資料』頁」開頭的整段為：

> 「全部資料」頁先顯示資料影響與下一步，分開列出最後成功完成、股價資料日及技術指標資料日，再提供「立即操作」與本次手動更新摘要。最後成功完成來自已保存更新時間軸；資料日來自同次各來源狀態，不以目標日或成功操作代填。未知、過期、部分完成與檢查失敗不能解讀成資料齊全；本輪缺欄位時不沿用舊日期。按「檢查數據狀態」後先核對各來源卡片，再依原因選擇個別更新。核心卡寬版採三欄、窄版採雙欄；整頁可捲動。

緊接新增：

> 更新時間軸與執行歷史、候選資料、官方來源候選與接受條件、使用資格與完整阻擋原因預設收合，按對應「展開／收合」可查看原完整明細。候選有資料不表示正式來源已接受；收合不解除阻擋或改變寫入權限。刷新保留資料頁、展開選擇，以及仍存在的步驟／來源／lane／Run 選擇。檢查失敗時先展開明細核對錯誤與來源，再重新檢查；原快速／安全更新、取消、SQLite 同步及人工確認規則不變。

### 11 開頭補入首層判讀

置於「這是唯讀觀測頁，不是選股工具」之前：

> 此頁標題為「運作狀態與下一步」。先看日常工作、資料與保存位置、治理任務各自的影響，再依提示到「數據更新」檢查資料。當前來源沒有提供最後成功完成與行情資料日期，兩者明示「未知」；每個工作列的「觀測時間」不能當成成功完成、行情資料日或 Windows 排程執行證據。未讀取、未知、來源無法讀取及歷史治理事件均不能解讀成正常。

接在兩條觀測平面清單之後新增：

> 「路徑與讀寫診斷」、「排程來源與原始診斷」、「治理任務、上下文與完整事件明細」預設收合；按「展開／收合」查看完整上下文、原始狀態、來源路徑及錯誤原因。刷新保留收合選擇與仍存在的工作／路徑選擇；不會啟動更新、訓練或修復。無法讀取／部分無法解析的事件檔即使標為目前觀測，也不能顯示為健康；先核對來源與診斷，再按既有排錯流程處理。

### 11.1 現行入口文字替換

將「Runtime 頁面最上方的『正式路徑環境（唯讀診斷）』」改為「首層摘要下的『資料與保存位置（唯讀診斷）』；展開『路徑與讀寫診斷』後」。保留原四位置、os.access／handle probe、唯讀／確認邊界、CLI、ACL 與 Registry 限制全文；不用此交付重寫正式操作。

## 回滾與接手

| 路徑 | 類型 | 摘要 | 回滾 | 風險 |
|---|---|---|---|---|
| `ui_qt/views/update_view.py` | 修改 | 白話影響、日期分開、明細收合、選擇保留 | 回退本 lane commit | 呈現回退，無資料遺失 |
| `ui_qt/views/runtime_view.py` | 修改 | 白話狀態、未知日期、技術收合與讀來源防誤判 | 回退本 lane commit | 呈現回退，無資料遺失 |
| `tests/test_ui_qt_runtime_view.py` | 修改 | 原 raw token 改驗 tooltip／折疊入口 | 回退本 lane commit | 無正式資料風險 |
| `tests/test_baldr_b03_update_runtime.py` | 新增 | focused 日期／未知／刷新負例 | 回退本 lane commit | 無正式資料風險 |
| 本 QA 文件 | 新增 | 證據、補文與剩餘界線 | 回退本 lane commit | 無正式資料風險 |

回滾順序：先 `git status --short` 確認沒有需保留的後續改動；整合前保留或不採納此獨立 commit；整合後在整合分支 `git revert <本 lane commit>`，再跑上述 focused 路由。不得用 reset／清理覆寫別人工作。

交付本地 commit 後停止等待中央整合；不在 dev cherry-pick、不 push、不清理工作樹。中央仍須接 Manual 補文及穩定 union 重型鏈；本 lane 只結案 Update／Runtime 呈現餘項。

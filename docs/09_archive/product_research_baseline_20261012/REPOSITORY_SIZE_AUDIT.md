# baldr 程式規模與維護負擔：唯讀盤點

> 2026-10-12 研究的歸檔閱讀版。下文的現況、執行與未執行描述固定於原研究時點；本次只整理導航與保存，不重跑研究或改變原結論。來源 SHA／修訂範圍見 [清冊](ARCHIVE_MANIFEST.json)，後續沿用方式見 [基線入口](README.md)。

日期：2026-10-12。baldr HEAD：`54f1e04d51f4057b04c9288b3ff6a733d6946a01`；兩份既有未提交文件保持原狀。關鍵數值、大型檔案／函式及重複候選摘要見 [BASELINE_METRICS.json](BASELINE_METRICS.json)，量測方法原文見 [CENSUS_METHOD.py.txt](CENSUS_METHOD.py.txt)。完整逐檔 raw census 仍保留在原本 ignored 任務目錄，來源與 hash 見清冊；未移入文件庫。

結論：體積來自較廣的產品／研究與資料治理範圍、大量測試／QA／工具，以及需要進一步收斂的責任集中和歷史研究支援成本。現有證據不支持以「功能比較多」充分解釋全部行數；也沒有證明大量重複執行計算是主因。程式大小、目錄整潔、可維護性與執行速度是不同問題。

## 測量口徑

- 只盤點 Git 追蹤路徑的工作樹內容，沒有掃描 `.venv`、ignored cache／output 或正式資料根目錄。
- 行數為實體行數，含空白、註解及 docstring；不是邏輯 SLOC、功能數、執行時間或已驗收功能量。
- 所有 baldr 4,817 個追蹤檔案均取得 inventory；程式／文件文字依列出的副檔名計行，二進位資產只記容量，不把圖片等當程式行數。未跳過追蹤檔案。
- 產品／研究來源是依路徑分類，不代表逐檔確認實際 runtime 可達、formal 資格或可清理狀態。
- DSA 的 Git `-C` 讀取在子程序失敗，因此由指定工作目錄取得 936 個追蹤路徑與 HEAD manifest，再唯讀統計檔案；沒有把失敗當成零檔案或 clean 狀態。baldr 已完成的 AST 結果沒有因這次失敗重跑。
- DSA 是本機 2026-06-24 HEAD 副本，KittenCN 是先前凍結的 `d463cde` 副本；比較不能外推為目前全部上游版本。

## Python 體積

| 項目 | baldr | 本機 DSA | KittenCN stock_prediction |
|---|---:|---:|---:|
| 產品／研究 Python | 724,456 | 122,461 | 8,358 |
| 測試／QA Python | 542,499 | 92,187 | 1,014 |
| 腳本／範例 Python | 216,087 | 3,060 | 588 |
| 其餘 Python（含舊版等） | 164 | 536 | 3,165 |
| 全部追蹤 Python | 1,483,206 | 218,244 | 13,125 |
| Python 檔案 | 3,079 | 461 | 70 |

baldr 的 Python 約 48.8% 是產品／研究來源、36.6% 是測試／QA、14.6% 是腳本／範例。產品 Python 去掉空白後仍有 664,757 行；此數字仍包含註解與字串，不能稱為純演算法行數。

DSA 的產品來源另有 JS／TS／CSS／HTML 等，共計 194,530 實體行；baldr 的 Qt UI 已計在 Python 產品來源內。因此只拿 Python 比例說「功能多幾倍」並不公平。DSA 本身也有約 21.8 萬行 Python，首頁乾淨不等於整個專案很小。KittenCN 以預測實驗為主，和 baldr 的資料治理、研究、證據、持倉與 UI 範圍不同。

另外，baldr 的 Markdown／RST 共 200,593 行，與上述 Python 分開計算。

## 產品程式主要用在哪裡

| 目錄 | Python 實體行數 |
|---|---:|
| app_module | 307,601 |
| data_module | 203,480 |
| ui_qt | 93,049 |
| ml_module | 83,375 |
| decision_module | 18,955 |
| analysis_module | 5,618 |
| backtest_module | 2,153 |
| 其他產品／研究來源 | 10,225 |

Decision／Analysis／Backtest 合計 26,726 行，約占產品 Python 的 3.7%；這只是這些目錄的大小，不能推定其他目錄沒有核心計算。但數字足以說明：大部分行數在 application、資料管線、ML 與 UI，並非全是新股票指標或策略公式。

具名來源例子：`data_module/formal_daily_input_producer.py` 的責任包括來源交接、candidate/formal 邊界、immutable publication、receipt、clock、custody 等。這些有工程目的，但不直接等同使用者新增一項功能。Qlib／vn.py／OpenBB 的框架範圍也很大；vn.py 有獨立 app／gateway repo，OpenBB 公開資料平台與 Workspace UI 分開，單看一個 repo 根目錄不能比較完整產品體積。

## 維護壓力的具體訊號

產品／研究 Python 有 216 個檔案至少 1,000 行、37 個至少 3,000 行、12 個至少 5,000 行。前 20 大檔案共 107,289 行。產品及腳本直接函式／類別方法共分析 25,140 個，其中 545 個至少 200 行；不包含測試函式與函式內部的巢狀函式。

| 來源 | 行數／責任訊號 |
|---|---|
| [recommendation_view.py](../../../ui_qt/views/recommendation_view.py#L783) | 8,755 行；同檔包含畫面、個人使用 policy、來源綁定／檔案 identity、候選 inventory、非同步任務、結果與回訪等多種職責。 |
| [RecommendationService._run_recommendation_body_result](../../../app_module/recommendation_service.py#L2384) | 單函式 1,890 行，含 invocation、cutoff／clock、universe 與推薦流程 orchestration。 |
| [formal_daily_input_producer.py](../../../data_module/formal_daily_input_producer.py#L1) | 7,229 行；來源和不同 publication／formal 時間邊界交接。 |
| [portfolio_ml_direct_numeric_store.py](../../../data_module/portfolio_ml_direct_numeric_store.py#L351) | 6,049 行；其中 build 方法 1,229 行。 |

這些是優先檢查責任切分與共用契約的候選，不是只依行數判定有 bug 或可以刪除。先弄清楚資料、權限、時間和恢復契約，才能安全抽出可共用部分。

## 重複程度：這次能證明什麼

本次對產品、腳本與明示舊版 Python 做保守 AST 比對：保持參數、變數、型別、常數、decorator 等，只忽略函式名稱、首段 docstring 與位置資訊；至少 30 個非空白行，且出現在不同檔案，才列入候選。AST 解析失敗為 0。

- 全部發現 69 組精確 AST 重複候選，多出實體行數共 6,745。
- 僅看產品／研究來源內部，有 3 組，多出實體行數 226；分別是三個策略 executor 的訊號生成、兩個 executor 的包裝函式，以及強／弱勢股 view 的加入觀察清單。
- 較大的重複多數涉及腳本／凍結基線，例如 `TechnicalIndicatorJob.run` 與 r027 candidate，或 UpdateService 與 r028 frozen baseline。保留基線有研究／回歸目的，不能直接當成正在重複計算或可刪除程式。
- 此方法不捕捉改名變數、改變常數／契約的近似重複，也不捕捉短 helper／template；226 行不是完整 duplication rate，也不能用它證明架構已充分共用。

同一函式被存成兩份，與同一使用者操作重複跑兩次是不同證據。是否有重複 SQL、指標計算、磁碟／hash／schema read、模型推理或 UI 轉換，須在明確使用者操作下做 caller tracing／profiling；本次未執行效能或產品 QA，不以靜態行數下效能結論。

## 為什麼本機看起來比 GitHub 更雜

baldr 本機根目錄有 205 個項目、163 個目錄；154 個根項目沒有 Git 追蹤的子項。DSA 對應為 38 個根項目，其中 9 個沒有追蹤內容。baldr 中可見許多 QA／暫存／快取／output 類目錄，GitHub 首頁只呈現被追蹤的部分，因此視覺上並非相同口徑。

「沒有被 Git 追蹤」不表示沒有 owner、可以重建、沒有引用或可以刪除。本次未作資料／程序／依賴清理判定。

## 建議的處理順序

1. 先清楚標示現行產品入口、research/candidate、凍結基線、工具與歷史記錄的責任和來源；不要用減少檔案數取代用途盤點。
2. 先檢查大 view、長 orchestration 函式及 producer 是否同時承擔 UI、資料、安全、流程與保存等責任；按同一契約抽出共用服務，保持原驗收與不同身份／clock 邊界。
3. 對實際慢的操作做有界 caller／profile，才決定 batch、cache、增量計算或消除重算。不得重跑既有被禁止重跑的 frozen QA 矩陣。
4. 將研究／腳本中的相似工具列成具名收斂候選；先查引用與恢復／回歸用途，尚未核清者保持 unresolved。
5. 測試保留風險覆蓋，檢查 fixture/helper 是否可共用；不能為了行數好看刪掉失敗反例或放寬 Gate。

本頁是純查詢產物，不改產品／資料／文件權威。沒有刪除、搬移、重構、stage 或 commit。完整依賴／可達性審查、近似 clone 分析與 runtime 重算判斷留作具名後續工作，不列為本次已完成驗證。

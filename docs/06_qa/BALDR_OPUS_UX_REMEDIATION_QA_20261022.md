# Opus UI／UX 修正與 root 複核

任務 `opus-ux-remediation-20261022-01a161de`，基線 `20a121af7f74d7d3e22f7e68985d674d9bbe86ac`。依[處置計畫](../superpowers/plans/BALDR_OPUS_UX_REMEDIATION_20261022.md)，三位 `gpt-6-luna` 分別實作圖表、個股、首頁／殼層；root 審閱差異、退回問題、序列執行 QA 並同步文件。使用者日期 10/22，部分收據 UTC／台北已是 10/23。

## 本輪交付與邊界

| 使用路徑 | 本輪結果 | 保留限制 |
|---|---|---|
| 今日總覽 | 上方市場卡三個原家數數字位；最多五個逐股候選入口。缺值、缺名、缺個別理由明示。個別理由依明確代號前綴配對，不能將過濾後的理由按位置配股。 | 沒有原指數／成交額就不造值；可核公司名及分型支持／反證須另補 DTO／來源。 |
| 個股首屏 | 搜尋預設收合可切換；原價格、漲跌、行情日提升；主圖與短五問並列，風險及不足常顯、全文可展開；營收／法人／信用／集保摘要直接可見。 | 不新算報酬百分比或獲利機率；版本核對失敗仍拒絕顯示其他價格。 |
| 營收／財報 | 月份柱圖保留缺月間隔；財報當期／前期配對柱；正值軸不浪費負半軸；單點值卡。精確原值／來源可明選展開。 | 不回推 YoY／MoM，不補月份、不升級 PIT 或金額單位。 |
| 籌碼 | 四個固定面向摘要取代全頁前四組；法人三家淨額、信用兩餘額、集保原比例優先；分點原順序與分母保持。全部已載入原欄位可展開。 | 沒有序列不做連買、餘額增減、大戶變化；不統一除以1000、不新增主力排名。 |
| 方向與狀態 | 價格、漲跌、法人淨額採獨立紅正／綠負／零中性 token，保留符號；一般量值中性；成功／失敗狀態獨立。 | 本輪未新增顏色偏好設定。 |
| 選股與比較 | 結果漏斗短摘要，完整原計數可展開；比較未知弱化但保留原因。 | 原來源、母體分母、查詢、收藏與資格守衛保持。 |
| 回測與殼層 | Matplotlib 局部深色；研究限定白話；緊湊原來源返回與 Ctrl+K；設定 SVG；release 顯示短版本，完整身份提示保留。 | 開發身份仍可見；固定 EXE 沒有重建或替換。 |

產品變更只在 `ui_qt/`；測試新增完整合成研究 DTO，沒有修改 application DTO、reader、計算、正式資料、Quick／Freshness／Evidence、Windows 排程或私人帳。本輪沒有執行下載、migration、正式 writer、原生桌面、交易或外部發布。

## root 實際退回與修正

root 沒有只採信元件存在：曾退回候選理由位置配對、柱圖重複橫條、單柱不可見、比較來源明細遺失、整段隱藏五問風險、不存在的 DTO `source_version` 讀取、摘要取錯最新月份與法人欄位、市場 KPI 放在首頁下方、返回按鈕裁切、窄柱首尾／頂部標籤裁切，以及籌碼摘要被級距 JSON 誤判成整面未知。Luna 修正後重驗，原失敗留存。

正常 Main 在 1280×760 的價格區頂端為 **166 邏輯 px**，四個摘要按鈕完整位於可視範圍；900 寬為199、1500寬為166。125%／150%均核對三尺寸，沒有強制擴大視窗。圖卡子樹沒有內層 `QScrollArea`，長原表仍沿原明細及頁面捲動閱讀，不能推論所有產品表格都已移除自身捲動。

## 驗證與原件

本機證據根為 `output/tasks/opus-ux-remediation-20261022-01a161de/`，下列相對路徑均以此為根。raw／PNG 被 Git 排除，不在乾淨 checkout；可提交的合成 fixture 為 `tests/opus_ux_review_fixture.py`，不是正式金融資料。

| 驗證 | 實際結果 | 原件 |
|---|---|---|
| 定向第四輪 | 281 PASS | `root/targeted04.txt`；收據 `single_owned_qa_a52769ac6e2940f3bdb2ccc39daf11cb`，SHA `397bdc6261bfc08afabe78c6d9f5be3add56e9be3de571d2535fd4bd5bb7bb66` |
| 125% Main first／fresh | PASS，正常保存、原件回訪、原 query／page／row 返回；新程序讀回不改 Journal | `main_remediation125_04/{first,fresh}_result.json`；收據 SHA `626180feb35c142a95f18c88ef70cfc3ba07795bf9ea3b0277ae8aee00a962c4`／`14f752a4da34ca9637feec6102d8df87cd40048cd7c06a311fe0d8c5910cd963` |
| 150% Main first／fresh | PASS，同樣驗原報告、題材選列、Registry 原結果及兩策略對照返回 | `main_remediation150_04/{first,fresh}_result.json`；收據 SHA `2fa86bcd3725c5f3120d352cc34a52bcf2761d39cd3f39ea05f9b7bafd358739`／`b9104ee56ab66ceb5babebd3ba10c7099d1ba6d6dd80321c63d0fe1e43eeb91b` |

最終 footer 白話增量及原保存／全域查找／題材導航補驗：**315 PASS**，`root/targeted05.txt`，收據 `single_owned_qa_2e02a14656d745d0b9914926f91dded4`，SHA `8b64d918a2744bc51e6a75d072421533ad3394de8c7f86691b3955d8aee8e058`。強制檢查第一輪：變更Python編譯0、Workbench85 PASS、validator25 PASS／0 FAIL／4 SKIP、mypy1138檔通過，收據 `single_owned_qa_56f988d483cb43e6a169e5ca3dbbd554`，SHA `f3243b07dd21a233e2de882e0c05522f125606d53c6b61b8bf19d2dfa8f93270`。回測WebEngine宿主白底另於實圖審查發現，後續修正與最終重驗另列，不能用這輪結果取代後續變更的驗證。

Main 的可讀行情是既有候選價庫的獨立副本，來源／副本 SHA 均為 `eeea9a1a4bbf119bda97465d87e7a9e3b0c1268ffec2f1f9fd9a03248125ddc4`，不是正式根新行情。原價點與圖值相等；實際筆記 UI 保存、canonical／Journal／新程序回訪、技術與價格比較、題材原三檔 SHA、原策略 executor／broker 的隔離 run／Registry 讀回均在原 harness 核對。其他來源缺表仍按實際缺件顯示；不能因隔離價庫缺大盤／分點宣稱正式資料故障。

完整研究 gallery 是明示合成 DTO：9法人欄、6信用欄、3個集保摘要與17級距 JSON、15分點、缺月營收及財報比較。其保存 canonical SHA `b0645f46810468b71a781b09dd8a6807bc563295a1d892ac961e238940e7fe10`，展示前後不變且不寫 Journal。此 fixture 的價格上下文沒有匹配原服務來源，所以摘要圖仍拒絕；正向同源 K 線另由上述候選價庫旅程驗證，不能為美化 fixture 放鬆守衛。

所有 Python 使用同工作區共享鎖及 Windows Job：8GiB、12程序、kill-on-close、啟動可用 RAM≥8GiB；成功輪皆 worker／Job程序0、自然排空、handles關閉及鎖釋放，不靠強殺算成功。

### 最後畫布修正與重驗

root 在 `_04/backtest_equity_first.png` 抓到實際 Main 走的是 `fast_chart_widget.py` 的 QtWebEngine，本來只改 Matplotlib 不足。Luna 補了宿主／頁面初始與每次 `setHtml` 前的局部深色背景，沒有改 inline payload 或全域 rcParams。`main_remediation150_05/` 的實際頁面背景色斷言、first全旅程、三尺寸完整圖卡及17路由通過，worker0；收據 `single_owned_qa_8485ebfc181842c3bfb192b37080f2f9`，SHA `91e5d9926da833e35ce61c5e57b6e3864f87559af277e75abf1df3f828d2b635`。root 已看 `backtest_equity_first.png` 的深色空畫布、`state_first_open_1280.png` 與白話市場 footer。這張圖驗的是未選詳細結果的宿主空態，不冒稱新曲線資料或所有 JavaScript 互動已驗；同原件權益預覽仍由上述旅程另驗。

最終新增路徑／payload／同源圖表回歸 **29 PASS**（`root/final_chart.txt`），收據 `single_owned_qa_a746ac64fe604f0ea672516fe7a30780`，SHA `643a1bd0daba1d30e82355bece7df839a4231ad7564be70f7094459e991dd6bf`。變更後強制檢查再次通過：編譯0、Workbench85、validator25／0／4、mypy1138；`root/mandatory02_{compile,workbench,validator,mypy}.txt`，收據 `single_owned_qa_a6beeed5ee8c41ce82e460b23f8cd3c9`，SHA `ba05c62c58609fa80473957faaca8f443443cff23cb193f8876712136eb084d4`。29項與先前315項部分重疊，不加總成不重複測試數。Workbench cleanup 提示未 import Main 而不額外 import，Job仍自然排空；mypy兩項 untyped body note非錯誤，validator四項skip保留。

本輪進行期間其他 owner 提交了 Track C `c97685da`，不是本次 UI 修改；保留其成果，不從基線差異誤納資料／清理程式。最新 Main 截圖的開發版本因此會顯示該HEAD；本輪仍是 dirty source QA，尚未構建固定EXE。

### 文件 Coverage

本次實際變更命中 workbench／market_explore／recommendation／backtest／stock_research／bootstrap／application_shell 七個feature；bootstrap是可攜指南同步帶出的檢閱範圍，不是本輪改安裝或排程。Manual及兩分冊、UI功能、題材方向語意、可攜版說明、Snapshot、QA索引／計畫已同步。架構、來源／儲存／金融契約、導航、觀察／帳本及首次安裝／移機／排程指南逐項記錄 not_required 理由於 task.json，未改對應行為。

`root/document_check02.json` 比較同一 `c97685da` HEAD 正文與本輪文件：基線1項／目前1項／新增0。保留市場手冊原有 `../../../output/tasks/baldr-post-completion-execution/TPEX_20261019_GUIDE.md` 連結越界，**全檢查不冒稱零錯誤**；本輪新增文件及連結未引入錯誤，task結構核對無錯。收據 `single_owned_qa_cf07646b457b485fab90a2b419370322`，SHA `82500f37681a1fc1c9d93c4c3d1937b59b7b86562164c7b0aac1bf989d86a52c`。首個文件QA腳本因漏列FIRST_INSTALL覆蓋理由而KeyError，改腳本後重驗，原收據 `single_owned_qa_c727f72050a04ce0b52977fd3aceb8bd` 仍保留；不是產品或文件連結新增失敗。

## 實圖與尚待改善

125%／150% 的 `main_remediation{125,150}_04/` 各有 `full_{summary,fundamental,flows,position}_{900,1280,1500}.png`、`full_financial_pair_1280.png`、展開籌碼、讀取失敗保留上次資料，以及17路由 gallery。root 已檢視首屏、窄營收／配對柱、固定四面向、市場、空持倉、Paper、ML、資料／營運／診斷、負損益及讀取失敗畫面；不是只列出檔名當接受。

| 新補評區域 | 實圖發現與下一步 |
|---|---|
| 市場分析 | 缺件模式仍有密集紅色診斷及內部欄位名；應另做白話摘要＋詳細診斷分層。資料恢復不會自動解決這個版面問題。 |
| 持倉／下跌 | 空帳有金額卡；負損益 fixture 可讀原值，但個股持倉章仍以長表／Health／Exit為主，未有完成的一眼風險圖卡。這不是已完成的持倉 UX 接受。 |
| Paper | 空狀態與帳別界線存在，仍有英文身份詞、大片空表及一處舊符號缺字；另排文字／空狀態整理，不改帳本或證據資格。 |
| ML | 研究限定、缺安全副本及明確讀取入口可見，完整有資料狀態仍需原件；未接受預測準確或金融用途。 |
| 系統 | 資料頁初始未檢查、營運來源未知可見；營運與診斷沿用同頁內容，仍需減少重複入口和長診斷。未按更新、修復或排程按鈕。 |
| 首次／失敗 | 首頁來源缺件、查股入口及同股重載失敗保留舊資料已補圖；全新使用者首次安裝／簽章阻擋／自然每日更新仍未做真人驗收。 |

本輪是具體批評的修正及未評頁面補證，**不是全平台已符合美觀與直覺的宣告**。下一步由 Opus 依同一截圖任務複審；真人十秒／三十秒測試、原生桌面、固定新版 EXE、正式來源／金融 Gate 仍未執行。D1–D9序列、單位換算、名稱／分型理由、分點排序等依賴保留於原計畫，與 Daily Operations Recovery 分開交接。

## 原失敗保留

`qa_chart01` 共享鎖忙，exit125且未啟動子程序，非記憶體不足；targeted01為182 PASS／11 FAIL、targeted02為273 PASS／5 FAIL、targeted03為279 PASS／1 FAIL。包含 DTO 缺欄、原斷言需展開明細／來源保留與 CSS content高度不等於物理外框的問題，修後重驗，未刪除失敗。

`main_remediation125` 因 harness 仍在收合摘要找完整漏斗而失敗，後續明確展開原明細核對；`main_remediation125_03` 找到 Qt 尚待 deferred delete 的已隱藏舊按鈕，後續核對唯一可見按鈕及完整 visibleRegion，沒有取消首屏門檻。`main_remediation125_02` 是通過的中間版，尚未含最後柱圖及籌碼摘要修正。這些歷史 case 均保留，不與 `_04` 最終證據混用。

# Baldr 並行工作 Root 審查補記

本次審查延續原補完計畫，未縮減全母體、H20、實際 UI 與同版啟動驗收的範圍。

## F03 收集模組

Root 實讀 `daily_market_technical_universe_kdj_alignment_query_v1.py` 的來源要求、builder 綁定、parent 收集、有界 entry 與 projection group。新模組明示未核資格，尚不能據此宣稱 full-N 查詢、資格發行或 UI 完成。

Root 執行：`.\.venv\Scripts\python.exe -m pytest tests/test_daily_market_technical_universe_kdj_alignment_query_v1.py -q -o addopts=`，結果 `9 passed in 0.67s`。此結果只涵蓋當時的九項合約測試。

待 owner 補證：公開來源要求建立時立即執行 byte budget；任何來源、順序或取消失敗後的終態行為；取消回呼後續回傳 False 時仍不得續收集。Group 在 try 區塊外執行的取消與前置核驗也須納入失敗終態，不得把部分收集重新包成完整資格。

後續 owner 加入建構時大小檢查與公開操作失敗終態。Root 再實讀 wrapper、group `_poison` 及取消恢復負例，重跑同命令得 `10 passed in 0.59s`。目前 group 失敗會使 KDJ member 拒絕讀取未核 entries，但 MA member 仍可被取得；未來完整來源資格發行必須檢查 group 終態、禁止任一 member 獨立發行部分結果，並有實際 full-N 負例。本次純合約通過不代表該原子發行邊界已完成。

Root 後續逐段閱讀 compact entry 與 consume 的日期、snapshot object 身份、source clock、method、parent row 對照及 Decimal leaf 投影。凍結 SHA 已核一致：module `c0c3bb9fd17d9c25ce5476a4a4bfaececf976d1affff79a51ef5f3c215b275c2`、test `9a398c3d8b10d3c61e91d1d216116f92bb43e1cfeb93ab71ee0197b81e9ceaeb`、plan `b0300581719683656151172ed919bf9491578808a20dce9e9755c72da4a3c0a4`。兩檔 scoped mypy 無問題。

尚有公開建構界限缺口：request/entry 的建構檢查只計 body bytes，實際 `to_dict` 還會附 identity 欄位；collector 雖再次檢完整 entry，公開 DTO 本身仍可超過宣告上限。已要求 owner 保存此凍結版本，再按最終 canonical payload 的大小統一檢查，新增 body 未超限但完整 payload 超限的負例。上述 SHA 是本次審查版本，不能冒稱後續修正版本。

大小修正已完成並經 Root 實讀：SourceRequest 檢含 identity 的完整 16 KiB payload；CompactEntry 建構與序列化均檢完整 payload，collector 繼續按完整 bytes 累計。兩個新增反例分別使用真 request 邊界與縮小的 entry 測試 budget。Root fresh 結果 `12 passed in 0.63s`、兩檔 scoped mypy clean。新 SHA：source `3afb98f39a7b2a66a43f1796edd8255c155940a08b24c11effdddc14e9b9e9a0`、test `054b975a51779e4cd9ad9f01efd6cdf5039609c90f0d139877f467c9f73ee367`、plan `4d0f3b1827398f5361ece9ea612b03220e5fa103deab87e2ca7692408253ec89`。接受的範圍僅為 bounded unqualified skeleton，原全母體發行與查詢 gate 仍待完成。

## H20 隔離測試接線

Root 拒絕僅以 finally 還原共享 `_case_root` 作為並行安全證明：其他來源或 archive 核驗呼叫仍可在暫改期間讀到 QA root。

已允許 owner 製作 cloned globals 的隔離小測試候選。原模組 globals 必須不變，clone code 使用凍結原函式，globals 差異逐項明示。此為受控 runtime 差異，不代表原 runtime 完全相同；若既有資格核驗要求原 globals 身份，應保留失敗，不得繞過。

完整 Main 尚未因此獲准執行。須先有真凍結 guard 正例、主失敗保留、假根與來源拒絕，以及並行原 helper 仍使用原 case root 的證據，再由 Root 審查 diff、pins 與啟動封套。

Root 已實讀 E 候選的 clone 實作：原模組 globals 不改，私有字典的差異為 `_case_root`、`_plain_runtime_sqlite`、`_install_sqlite_allowlist` 三槽，helper/installer 沿原 code object 執行。仍需補 runtime 持續核驗：固定所有非差異 globals 的 object 身份及 keyset，並核安裝後 `sqlite3.connect` 的 exact wrapper 身份與 scoped globals；只在 receipt 記錄布林不足以拒絕 resolver 替換。已交 owner 增加具名拒絕與相應負例，未授權 Main 啟動。

clone 首次 native 小測試保存在 E 候選內 `attempts/clone_globals_selftest_20261008T235435_6ec5afea/`。Root 實讀 receipt/stderr 與 adapter：`legacy_scoped_guarded_connect_identity_invalid` 來自安裝階段錯要求兩個 SQLite alias 同為 scoped wrapper。凍結 legacy SHA `98ca79e560497dd423772783da1b3300cb237e00bbef78e1fd1eadc50b7c22f6` 的 installer 只替換 `sqlite3.connect`，保留 `dbapi2.connect`。錯誤存在 QA adapter 本身，也不只是測試期待。已允許按原契約修正並保存前像；安裝階段應核 dbapi alias 未變，外層 router 收尾階段另核雙 alias 回到 scoped wrapper。小測試人為模擬 router 收尾不能證明真 Main 的 finally 已執行。

v2 小測試 `clone_globals_selftest_v2_20261008T235712_06e027ba` 的 receipt/stdout 已由 Root 實讀且核兩個 log SHA，terminal exit 0、20 checks 成立。兩個真 thread 同時核原 helper 保持 case root 與 scoped runtime 六次連線；source connect attempts 0、frozen guard SQLite connections 0，不能說所有 SQLite 連線為零。原來源拒絕、resolver/alias/root 替換及實際 junction 拒絕均包含。接受範圍僅 installer seam；Main 尚未執行。

後續發現整體收尾的 verifier 在最終 connector restore 後仍期待 scoped wrapper，會誤拒真 child。已允許調整為 readers/worker 終態及 router detach 後核 scoped wrapper，再最終 restore 後另核 base guard 的雙 alias。必須沿真正 H20-first 正例／主失敗收尾實跑並保留主要錯誤，不以 installer seam 取代完整收尾證據。

`clone_globals_router_order_20261008T235924_751bb725` 已由 Root 實讀 receipt、pytest stdout 與 test：compile exit 0、`1 passed in 0.72s`。實際覆蓋 installer selftest 與尚未經 router 時拒絕 cleanup stage，沒有執行 H20/market dual operation 或真正 router 收尾。其目錄名稱不能作為完整順序驗收證明；後續仍須真 dual seam 的 H20-first 正例與注入主要失敗。

## F06 實作前的來源語義核對

Root 已審閱具體方法提案，允許獨立 BB30 population ±2σ 與 ATR14 rolling-SMA 原料切片，保留兩個方法版本及舊 Wilder 路徑。尚未接受收斂或突破規則。Decimal context 應沿現有精度 34、ROUND_HALF_EVEN、Emin -6143／Emax 6144，全部 traps 明示。

Root 另實讀 `daily_market_technical_source.py::_calculate_sessions`：原始 rows 完整保存，sessions 僅使用最新連續 OHLC 有效尾段；無效列會重設暖機，不跳過。`observed_prefix_contiguous` 不證交易所日曆完整。Snapshot raw validator 核驗 token 解析值、validity、原因與 fingerprint，因此合法缺值或 invalid OHLC 可保存並由新 leaf 回 unknown；transport 篡改則拒絕。已要求測方法窗口外早期 invalid 不污染有效尾段、BB30 內但 ATR15 外 invalid 時兩方法獨立狀態、以及成交量缺值不單獨使不使用量的波動原料未知。

Root 已初讀新增但尚未凍結的 `daily_market_technical_volatility_evidence_v1.py`：兩個方法各選自己的窗口並分別建立原料 evidence，context 沿精度 34／Emin -6143／Emax 6144。仍待確認計算前輸入 Decimal token、coefficient、exponent／adjusted exponent 上限，與方法提案的原料界限一致且納入 method identity；輸出 token 限制不能替代計算前的資源界限。已要求 owner 補相應極端精度／指數反例，尚未接受此候選。

Root 後續實讀新輸入界限檢查與九項測試，並在全新 native 合成目錄 `C:/t/f06_root_20261009_82a3` 執行完整 leaf suite：`9 passed in 1.14s`、terminal exit 0，JUnit `output/qa/f06_root_20261009_82a3.xml`。包括合法來源在 cutoff 後追加列、重新保存 snapshot 後截點前 measurements 不變，以及 raw tamper 拒絕。仍待公開 Measure 的自洽負例：observed 不得容許空窗口、每方法窗口上限應分別 30／15，window digest 必須與日期/fingerprint/方法一致。未核資格 DTO 的內容自洽檢查不代表來源發行資格。

新增 Measure 窗口檢查後，Root 實讀缺失窗口／逆序日期負例與 window digest 重核，於新 native 目錄 `C:/t/f06_root_20261009_b62d` 重驗 `10 passed in 1.23s`；JUnit `output/qa/f06_root_20261009_b62d.xml`，scoped mypy 兩檔 clean。尚待補直接 fingerprint/digest 混搭與未知窗口超過方法上限的負例；候選未凍結，不能用本次十項結果涵蓋後續改動。

後續加入窗口混搭、方法上限及 ATR 上下跳空向量。Root 實讀跳空向量的前收距離 11／當日範圍 2 與獨立 14-TR 總和 37 oracle，再於 `C:/t/f06_root_20261009_c731` 得 `13 passed in 1.28s`，兩檔 scoped mypy clean，JUnit `output/qa/f06_root_20261009_c731.xml`。測試期間 source SHA `d72e8ac0d4ea3e38777592da6adbff5bc3601439ee3643f104e36e6b1788fa98` 不變，但 test SHA 有變，故這是施工期間回歸，尚非固定 test 版本最終接受；owner 凍結後再核精確版本。

owner 明確凍結後，Root 以 `C:/t/f06_root_frozen_20261009_f18b` 做固定版本驗收：`13 passed in 1.19s`、terminal exit 0，JUnit `output/qa/f06_root_frozen_20261009_f18b.xml`；scoped mypy 兩檔 clean、py_compile exit 0。source SHA 前後仍為 `d72e8ac0d4ea3e38777592da6adbff5bc3601439ee3643f104e36e6b1788fa98`，test 為 `e656ea5d1bba0900ac2155c232596668d99fc5047b2c28eafa761345563b3f81`。Root 亦實讀 owner 原始 `C:/t/f06_volatility_evidence_20261009_e/pytest.log` 的 13 passed／1.33s。接受範圍為純 Decimal 原料 leaf，仍非 full-N 資格、收斂／突破、UI 或 F06 完成。

## F02 續驗輸入核對

Root 實讀 v2 manifest，SHA 為 `84da626532cb7132f1ede72409793c0f511139568be6b61cf58f25318fe2bc3a`，明列獨立 segments 根及 94 directories／300 files／27,963,544 bytes。Root 另以檔案雜湊直接核 source database、兩組 pointer 與原失敗 receipt，均吻合 manifest。此步沒有連線 SQLite、沒有產製或開啟 reader；也沒有重新核完所有 segment files，不算完整來源資格或 continuation 執行通過。候選 target 尚待 owner 凍結後審查。

## 分工與真人驗收

三條子任務持續獨立推進：H20 接線、F02 查詢續驗、F03 KDJ 收集與整合準備。Root 負責交叉審查。尚未產生通過整合驗收的新啟動版本，因此本次沒有新增真人重測要求；後續交付應提供實際啟動位置及同版本驗收步驟。

Root 已再核目前推薦 view 與 layout test SHA，分別仍為 `5F0FAA96F246C62C7693E1771D538D88B72AE95A6544208D74B14650ED16EDD5`、`61E4ECAF7F4E339798C73950808D5CB17B4F03B9A23B8C1B73DF48C33C340701`，與先前 11 項 layout suite 的受測版本一致，因此沒有無理由重跑此套測試。此一致性仍不證 EXE 同版驗收。

Root 補驗 H20 未知列的兩個現有案例：`pytest tests/test_ui_qt_personal_h20_research_widget.py -k unknown -q -o addopts=`。首次 sandbox 執行在合成 capture 的 `os.link` 遇 WinError 5，兩項均尚未進入 UI 斷言，不視為產品結論。改用新的 native 隔離目錄 `C:/t/h20_unknown_root_20261009_7c41`，同兩項測試 `2 passed, 11 deselected in 2.13s`，terminal exit 0；JUnit 保存於 `output/qa/h20_unknown_root_20261009_7c41.xml`。覆蓋未知列禁止下鑽、完整可複製來源原因與恢復原 pin 的前置條件；不覆蓋原 2382 的來源修復、效能、Main 或 EXE。

真人草稿入口名稱亦已對照目前原碼：「研究選取股票」、「摘要」、「返回來源清單」、「收藏此原排名研究」、「個人 H20 原保存研究收藏」、「重新整理收藏」、「重開所選 H20 研究」均有實際控制項。H20 表格的可下鑽狀態是「可核原預測」；「未知」列會顯示可複製核驗原因且停用研究按鈕。未來啟動候選應先由工程驗證原 2382 列可核，不能把未知列停用交由真人反覆點擊排錯。


### F06 複合查詢首次排序契約審查

Root 已直接閱讀新查詢 DTO 的硬資格、三群 truth 與全域排序 helper；硬資格失敗會產生 not_evaluated 並拒絕 predicate match，不能由 OR 或 unknown include 升格。null 值在升冪／降冪皆置尾端，穩定排序以股票代碼升冪作最終同分依據。這是尚未凍結來源的靜態審查，不代表 reader-issued 結果或 full-N 驗收。

已要求 owner 補查三項：排序欄位須綁定允許型別，避免數值欄全部字串而以字典序排序；100,000 列乘 33 欄與每值 256 bytes 的局部界限仍容許大量中間投影，須提供總位元組預算；超長整數轉字串的拒絕須回傳穩定領域錯誤。F03 KDJ 尚未納入此三群 DTO，完整 MA／KDJ／波動整合責任保留，不能宣稱原選股器範圍完成。


### H20-first 第五次前置失敗的 API 證據

Root 已直接閱讀 `C:/t/h20dual_h20first_20261009_success_74a2dd39/output/router_cleanup_seam_receipt.json`，其 failure 為 `market_operation_source_group_not_exact_keeper_pin`，並保存 `wal_keeper_close_deferred_without_terminal_router_proof` 次要清理錯誤；此 case 不能算完整收尾通過。固定 neutral helper 的 `CopiedWalGroup.__init__` 實際保存 `source_start`，原 child 卻讀取不存在的 `source_pins`，造成 None 與預期 tuple 比對失敗。Root 已核 helper 原始碼欄位，這項證據支持 API 名稱不匹配；尚不能由此宣稱原來源曾異動或型別載入不一致。

Owner 下一步須保存事件時點的實際 canonical pins、修正為固定 helper 現有 API，並驗半安裝故障的 partial abort；不能偽造 Main shutdown flag，也不能以程序退出替代 reader／permit／private copy／keeper 清理證據。完整 Main 與新 EXE 仍未驗，沒有新增真人入口。


### F06 複合查詢凍結來源 Root 重驗

新 request/predicate/unqualified sort 切片已完成上述排序型別、64 MiB 投影預算及超長整數穩定拒絕補強。Root 使用凍結來源獨立重驗配對測試，結果 23 passed／0.82 秒；兩檔 scoped mypy clean。來源 SHA `5D99A71C789523A04AF6EA5B9AF44EF3FDACB47FE4B0F9F7D9FD0A7E9A9637A8`、測試 SHA `F0DA1B257CF03FEB809186FF1EE54C7BCE07EB3F6FC7F345FDA8AD89CC365970`、契約 SHA `1376C0408D874E9D0AFF835949A81E4ADC3A5F82EFB321E2D1C1CE25AF7B1B98` 均與 owner 凍結值吻合。Root 本次 pytest 命令指定的封套位置為 `output/qa/f06_root_query_20261009_r1.xml`；Root 已另讀該 JUnit 封套，確認 tests=23、errors=0、failures=0、skipped=0；py_compile 亦 exit 0。

這些證據只核純請求／判斷／排序契約，不包含 reader qualification、全母體 sealed result/page、F03 KDJ、UI 或 EXE。代理已接續 F03 KDJ 查詢契約，完整原計畫與真人驗收仍未完成。


### P03 正常更新到 F17 bundle 的來源入口核對

Root 實讀正常官方來源 wrapper `scripts/scheduled/run_official_market_status_bundle.py:650`，其 current child 呼叫 `scripts/refresh_current_market_status_observation.py`，輸出根為 `release_v4/current_market_status`。capture_sources 保存每次原始本文、SHA、captured_at、HTTP／parse 狀態；source_specs 同時包含上市／上櫃／興櫃 roster 與 TWSE／TPEx disposition。不能只由 wrapper 成功推論 F17 bundle 已建立。

`CurrentMarketAssignmentReader.from_pointer` 要求指定 current_market_status_pointer.json，先核 schema、current_only／PIT false、發布時間不晚於 cutoff、run 相對路徑及 snapshot／manifest SHA，再由 exact payload 建立來源 pin。BundleWriter.create_from_pins 另要求 technical store generation／plan／receipt 三個 exact identity 與 byte SHA，加上市場及處置 typed source pins，先核來源與 output 不重疊，再建立新 attempt；其 API 明示不讀 latest pointer。

下一正常更新 adapter 必須把同次 capture 的確切 pointer／run 與兩種 typed pins 留在封套，再連同 technical exact pins 送入 writer；不得於後段重新尋 latest 或從 current capture 借 historical PIT 資格。當前僅完成呼叫與契約核對，尚未有 updater→bundle→收藏新程序的完整執行證據；正式排程未修改或啟動。


### H20 收尾失敗分支的順序風險審查

Root 實讀 child.finish：H20 session 未終態或其 finish 拋錯時，原流程記錄錯誤後仍往 market detach／finish 前進。Bridge 自身只檢查市場連線 _active／_opening，不能代表 H20 session 或 permit 已釋放；helper inventory 最後拒絕亦不能作正常延後機制。Bridge.abort 在 finally 標 finished，即使保留未知 artifact，故不能以先 abort 再重試作可靠收尾。已要求 owner 在市場 detach／finish／abort 前核 H20 reader／permit 與真正 worker 狀態，以純合成故障案例證明保持資源與可恢復狀態。這是靜態風險與待驗項，不宣稱已在 Main 重現或修復。


### P03 同次擷取、兩種 typed reader 的真合成接縫

Root 新增隔離探針，以真 capture_sources 保存五個合成 roster／disposition 回應，再呼叫兩個公開 from_pointer 及 from_exact。Native b attempt exit 0，八個檢查全部通過：五個合成來源、相同 run／snapshot SHA／manifest SHA／pointer SHA、2382 assigned_twse、市場 exact reopen、處置 exact reopen。receipt 位於 `output/qa/p03_same_capture_readers_20261009_b/receipt.json`，SHA `820199ac987b4f6049d8c0ba0db4c49f13053b96ccbf1df33687828007114fcc`。

Sandbox a attempt 在 strict realpath WinError 5 失敗，原 captures／script 保留；不把該環境失敗當成來源壞損。這個接縫不接網路／SQLite／producer／正式排程，合成2382不是原H20研究。尚未涵蓋 pointer 競態拒絕、bundle writer、全母體結果、收藏新程序、Main／EXE；原P03正常更新完整閉環未因此完成。


### P03 pointer 前進後仍重開原來源

Root native d 合成案例再擷取第二次來源，使 pointer 前進並把新市場名錄改為1101；舊 typed pins 以原 cutoff 重開仍保存2382與原兩種pin identity，新 pointer readers 則一致讀到新run／1101。12項檢查全部通過，receipt SHA `ec771b9db0586e4e73c18793483133f7bf7ea30cd7bb4811a91abdcdc4e5e09b`，位於 `output/qa/p03_same_capture_readers_20261009_d/receipt.json`。

原 c 案例錯以 advanced cutoff 重開舊市場 pin，被 `market_assignment_exact_cutoff_mismatch` 正確拒絕；該失敗與來源保留，修正的是 QA 呼叫，不是放寬 reader。這證明保存 recipe 需要保留原 cutoff，不能僅保存 bundle或來源SHA。尚未測 pointer在兩reader取得pin中途前進的原子拒絕，亦未包含完整writer／UI／EXE。


### P03 同次擷取 adapter 的競態契約證據

Root native e 探針確認：pointer 更新前取得的市場 reader 與更新後取得的處置 reader，各自都通過公開 reader 驗證，但 run／snapshot 不相同。15項探針檢查通過，包含此混版情境被辨識，並非產品 adapter 已拒絕；receipt SHA `a2f15646bfb6882714d70972af4b43d7531c1610fd90f9b5441c99be3667dfd4`，位於 `output/qa/p03_same_capture_readers_20261009_e/receipt.json`。

因此正常更新的「同次 capture」adapter 必須核兩pin對指定run／snapshot／manifest／pointer身份再發布，或從已固定的原run建立exact兩pin。不能只檢查兩reader各自有效就聲稱同次來源。這是該adapter的同次擷取契約，不改通用BundleWriter可接受明示獨立市場／處置來源的設計；F02原固定來源可來自不同root/run，仍按各來源pins與cutoff獨立核驗。正式流程尚未接線。


### KDJ 新 DTO 首次語義驗證審查

Root 實讀尚未凍結的 KDJ query：完整 canonical payload byte budget 已含最終 identity，typed predicate 綁 stock／snapshot／clock／cutoff，排序先核64 MiB投影再配置索引。另指出直接 dataclass 構造或 replace 後自洽重雜湊可能避開 from_dict 的語義驗證；to_dict/to_json 只核 hash／bytes，不足以保證 states／combine／source pair／sort fields 合法，而 predicate/sort目前僅呼 to_json。已要求 owner 建立無遞迴的共用語義核驗並補自洽 malformed request 負例；未核資格請求同樣不能接受非法語義。這是mutable來源的靜態缺口，不代表已接受最終來源。


### F02 continuation b 啟動前拒絕：未定義名稱

Root 重算 b supervisor `694c2d3046ccf1f73724013b92cc12e16bf05032dee8b68e8d8a3b30196d16eb`、target `ca8663ad43dc3c83e4132ec740ca6d7fad84c38197dfa65a4763c31eda3f485b`、manifest及diff雜湊吻合。完整讀新增inventory段後發現 `_capture_continuation_inputs` 回傳使用 `original_receipt_pin`，該名稱只在另一函式的local內定義。Root對生成候選本身跑mypy，L494確實報[name-defined]；log保存在b/root_mypy_review.log，整檔173 errors不屬產品gate通過。首次錯用mypy disable-error-code=all的命令亦未完成檢查，後續正常命令已確認此缺陷。

b尚未執行，Root未授權run；要求owner保留b immutable，另立c讓capture自行取得並驗原failedreceipt pin，對生成來源而非僅derivation腳本核name-defined／compile。原target oracle bytes／AST與原失敗收據均保留。這是具體啟動阻礙，不要求真人操作。


### F02 b 其餘 provider／唯讀差異續審

Root 完成 provider/create_from_pins 及RO guard新增段閱讀：exact來源DB以固定SHA／size／single-link／無sidecar核驗，connect要求完整固定mode=ro URI、uri=True與timeout=5.0；原SQLite audit必經wrapper／threadlocal target身份，不能直接繞過connect wrapper。Provider經真StoreReader exact核complete counts 259/258/1/258/0與missing1257，再核固定市場／處置pins對原bundle來源，經真BundleWriter建立新sidecar。來源起訖inventory與每個protected tree起訖保留；原oracle／targetbytes／AST未改，producer deny與receipt continuation-only保留。

此部分未發現須縮母體或改產品writer的理由；b仍因L494未定義名稱而拒絕run。下一c以窄修正及對生成來源name-defined核驗後，Root再核b→c immutable diff與fresh target／outer roots才放行一次native完整矩陣。不能由本次靜態閱讀宣稱完整query或來源資格已通過。


### H20 Windows path 修正與正例仍失敗

Root 已讀9c41b8原failure receipt，H20 permit release以type(path) is Path錯拒WindowsPath；現child改核type(Path())的本平台具體類別，並保留parent、lexists、guard removal delta與permit身份核驗。Root搜尋current候選未見其餘同類判斷，preimages保留原錯誤。

後續bf7a21原failure receipt仍為failed，原因synthetic_guard_denial_counter_nonzero，另有keeper close deferred；該receipt未保存各counter值，不能由此宣稱guard放寬或來源寫入。已要求owner在失敗封套保存有界counter／first-deny並定位原因，不能清零或略過gate。fallback keeper close另須接受已核no-Main proof且所有reader／permit零活躍與市場真正finish binding，不能以proof字典本身算終態。尚未有完整H20-first正例或Main通過。


### F02 c 窄修正核對與一次執行授權

Root 已完整讀 b→c 1833-byte diff：只有新target／input manifest路徑及capture local receipt pin賦值／SHA／size核驗。Root重新compile生成supervisor、跑generated mypy，未有name-defined（整檔172其他錯仍保留，不稱mypy clean）；c target目錄僅原84,223-byte target且與b逐位元組相同。12個direct product module SHA全部吻合原manifest，sqlite_read_only helper f608de...86ae吻合。

c supervisor SHA `70d1b25a85c3ffbb74ddadd687a937d836e7998ba52eb10d5a1ca9487a06b9a9`、manifest `5d29a1a95c3bce5486ee16f4206bd4eb118c68b92ee15fa02d31b727a437d9e0`、v2 input `84da626532cb7132f1ede72409793c0f511139568be6b61cf58f25318fe2bc3a`、diff `9ecbb1fe4a7330b6acd698c934e0bb007e041464fb892d3340346ad6ee011539`、plan `b3e7f03dd08652a7f8bbbc03ee303d64c4d502587b1ceddf8d50ad1b6b300c8c` 均由Root實算。

Root已授權owner一次native完整query_continuation_only執行，仍須最後pin／fresh root核對並回報live handle，owner自行poll／保存stdout/stderr／來源起訖／Job終態。此授權紀錄不是已啟動或通過證據；不得restart或改凍結runtime，失敗封套保留，producer／原資料／正式排程不啟動。


### H20 counter 契約：缺欄位與真拒絕分辨

Root實讀004004完整診斷及固定canonical guard來源：guard未定義source_write_denied專用counter，故原gate因None而fail；實際catch-all write_attempts_denied／sqlite_write_sql_denied及其他必填counter為0，events空、overflow0，legacy source_write_denied0。原failure保留，不能說原gate通過。fallback keeper已在該封套實際close，status passed／committed marker與rollback證據保存。

Root允許owner新增限定已pin guard版本／SHA的counter contract：未提供專用欄位時必須catch-all0、相關deny事件不存在、overflow0及legacy專用counter0；有專用欄位則strict int0。缺其他必填欄、bool、catch-all非零／專用非零／event或overflow皆拒絕。需合成正負例再進完整seam，不改guard、不清counter，不接受任意缺key fallback。Main尚未驗。


### F03 KDJ query 凍結來源 Root 接受

Root 獨立重驗18 passed／0.97秒，實讀JUnit tests18/errors0/failures0；兩檔scoped mypy clean、py_compile exit0。來源SHA `2DA8E37359F85FD7D278330C80C30559DC1AE3E9319AC03CB2D32AD24F00F11A`、測試 `1986E6E68ABA4B429214795D3C6E3C9030306E1854A67EF400D0F545A497F3D7`、契約 `B54EEA93CC2EE3DF6CEDA53117626F6D9D6933160B2FB3E433DC4400327AC05F`皆吻合。直接constructor／replace後自洽重hash的非法語義負例已補。

只接受request/predicate/unqualified sort/page contract，沒有full-N reader發行或UI／收藏。Owner接續F06有界collector骨架與同次MA/KDJ/volatility四群publication方案；full-N共享接線待F02實證，整份原計畫仍未完成。另Root重算c最新補齊文件manifest `26f0fad86dada228a786eadb2c78102e1480ae21652ca14ebcaa3037bba180b4`及plan `d0bf3e4c0fdfb9d519312b260d029db7bfc21ab1640083944407ee5df092352b`吻合owner補記，runtime source不變；準備中不能當live handle。


### H20-first 真雙來源純合成正例收據核對

Root實讀004225完整receipt，SHA `ff6405437777675a0e8ebc6bdfb319646009150b09e53391672ff6150d8bd822`。事件依序H20 cleanup begin→session finish begin/complete→permit release→H20 end→market finish begin/complete；H20清理時兩alias仍outer router，市場finish前切runtime guard，結束還原baseguard。3/3 private directories、permit1/1、private root empty、legacy scope passed、keeper close passed；市場/H20來源operation pins起訖相同、市場應用source SQL=0、keeper active pins不變及rollback均經Root逐值核對。

合成H20值1234 bp、三筆合成市場價格，不是原684 bp。main_entered=false，零worker是未建Main，不提供真正Main shutdown資格。接受此正例封套事實；故障／retry／partial abort仍待，不能放行新Main或EXE。


### H20 故障重試與主要錯誤封套 Root 核對

Root實讀retry_v3_004428 receipt SHA `38dc7fe6c94e0438278bdc501a8578bdc2ca7dd9be4471432270c7e4d2c884ab`：失敗快照保留同一注入exception物件、H20 active／permit1、outer router兩alias、market attached且未finished，第二輪真finish後3/3目錄與permit1/1釋放。注入事件已明示為QA marker，不是Main生命週期事件。primary_failure_004441 receipt SHA `5d199e2615ad83cfd2da7ec289bfd0c7b18bf54652d5c456c997598fa4b2d1b1`亦保存主要錯誤、次要清理錯誤並完整收尾。

partial_install_004441仍failed（partial_install_abort_contract_failed），不能由copy已刪除和alias已還原當作整例pass；owner接續同版counter契約，原封套保留。Root另直接執行counter-contract-selftest，12/12正負檢查exit0；這是current QA runner的純記憶體檢查，不代frozen Main或原來源。

F02 c outer receipt經Root實讀：worker_returncode1、continuation_input_unchanged true、job_closed true／empty_before_close／zero_owned_processes_proven true／cleanup_budget_exhausted false。原query仍未執行通過；d只有生成與純合成guard正負授權，尚未放行新完整run。


### H20 同版凍結四情境 Root 獨立重驗

Root使用同一runner A840D2D7...51FBF3及child F6CD9750...D8645E，在四個新native roots 獨立執行success／primary-failure／partial-install-failure／h20-finish-failure-retry，皆exit0；runner起訖SHA相同。完整stdout/stderr與逐receipt SHA核對保存在output/qa/h20_root_frozen_seams_20261009_a/root_receipt_review.json。Root逐例另核no Main、private root empty與keeper passed；三個完整共存案例3/3目錄、permit1/1、兩來源起訖pins一致，partial案例counter／alias／原install error亦通過。

四例清理接縫現可接受，owner接續同版frozen依賴manifest與完整合成Main啟動計畫，仍需root預審才run；原684bp／十股／效能／EXE未因此接受。

### F06 collector 初次 root 原始碼審查（2026-10-09）

審查候選 SHA `A5923BD173FE81B01A3B6D57B9CD1E1A9AAE503A22E727DC9DA3150628F526B9`，未接受為整合完成。讀取完整 collector 與合成測試後，要求 owner 修正三項：consume/end 的 segment index 必須拒絕 bool；custom index byte budget 必須檢查加入 identity 的最終 payload；直接建立或一致重算 hash 的 index 仍須逐 entry 核對 request 的 clock/date/cutoff，不能只驗排序與數量。owner 的 8 個測試通過僅代表原 bounded skeleton；root 尚未批准該候選。修正由既有 subagent 負責，不改其他線 frozen runtime。完整四路同次 observer／原子發布仍待後續整合。

### F02 continuation d root 審查與一次續跑授權（2026-10-09）

Root 讀取 c→d scoped diff、guard selftest 的實際 stdout 與 terminal，重算 supervisor `8fd863d5211c51b212c7b13a38b2ea255acff30b7504129c5aae551ff5d9c2a4`、diff `301c4fa03909f32405670f2af02598a272fa4ea2250123aeef3ec2e5bf1bd041`、stdout `df89f78cec5403238ba2697d74403b5b9c4d76f5eccd86febb895080c05b40d1` 均一致。原 c 不變。d 僅將 continuation 固定 source URI 與 local URI 解析分支分開，仍保留 source SHA/size/single-link/WAL-SHM absent、exact kwargs、query_only 與 ATTACH/DETACH deny。實際 guard-only exit0、唯讀正例1、負例13、source pins unchanged、local DB absent；不代表 query continuation 通過。已授權 owner 在來源及產品 pins actual preflight 一致後，對同 frozen d 執行唯一一次 native continuation；原 deadline、Job 與隔離規範不變。owner 管理其 live handle；完整驗收與 terminal receipt 仍待回讀。

### H20 Main 收尾接線追加審查（2026-10-09）

Root 讀取 E `synthetic_main_child.py` 的 `_journey` finally：Main 關閉後輪詢 visible/running/native_finished，無 shutdown error 才設定 router 的 Main terminal flag；E router.finish 會先要求 owner terminal proof，再關 H20，H20/permit 未終態即保持 market router 並延後清理。已要求 F controller 候選核查 journey 前失敗及已刪除 Qt worker wrapper 的例外保存，避免 primary 被清理例外遮蔽，並區分尚未進 Main 的明示 no-Main proof 與已進 Main但worker未知的 deferred 狀態。這是實際原始碼審查，不授予 Main runtime 通過。

### F06 修正版 collector root 獨立驗證（2026-10-09）

模組 `61E3E4D0993C0F405006ADEFE496004C67F7EBEEBD950241F0BDD573FA069E9E`、測試 `A1A02B15E88330FADA5450B86CB9A435B66C33C332DA7DE345AC6071087B1F69` 已由 root native 新隔離根 `C:/t/f06-volatility-root-review-20261009-a` 執行：11 passed／1.29 秒，JUnit `output/qa/f06_volatility_root_collector_20261009_a.xml` 實讀 tests11/errors0/failures0/skipped0，起訖 hash 一致。正常 scoped mypy 兩檔 clean、py_compile exit0；另 follow-imports=skip 模式產生18個跨模組型別 attr 錯誤，不以該模式宣稱乾淨。三項審查缺口已補 strict bool 拒絕、final identity bytes 自訂上限、一致 rehash 後仍逐 entry 核 request 日期/cutoff/clock。接受 bounded unqualified collector 切片；尚不代表四路原子發行、full-N、F06收斂突破或 UI 完成。

### 四路同次觀察與原子發布邊界核查（2026-10-09）

Root 實讀 P01 `bind_verified_projection` 與 `consume_verified_parent`：只有單一 observer slot，原 snapshot→parent row 迴圈可逐列呼叫，同 segment begin/end 都在原來源核驗路徑。F17 `_publish_session` 目前先 finalize MA、建立 session、最後檢查取消。因此新四路整合不能僅依次呼叫每個 member 的現有 finalize；必須先備妥全部不可變候選、驗來源與完整分母、最後取消檢查後由單一 publication authority 發行，任一 member 失敗時全部保持不可讀／永久 poison。builder 對 callback 的 catch 範圍亦不能當作任意異常已毒化的證據。已將此實際接點與失敗要求交 owner 的下一片方案，保持舊 MA-only 路徑成本與功能；未修改 shared reader／builder。

已接受 F06 三檔切片保存於本機 dev `6bf71603`，不推送，不包含其他未提交內容。

### F02 d 原生續驗終態（2026-10-09）

Root 實讀 workspace terminal：d唯一續跑exit1，supervisor／target／input SHA 起訖一致；原owner handle77580已由owner確認terminal。outer `C:/t/f02_ma_composite_257_v4_76b046c19786` supervisor receipt status failed、worker_returncode1、continuation_input_unchanged true。實際 acceptance `d_target/attempt_0db15db4fdab4a49/acceptance_receipt.json` 顯示 fixture_creation 8390ms，原料唯讀19632 rows與真 StoreReader.read_exact 一次成功，producer/bundle writer為0，之後因 QA provider 讀取不存在的 VerifiedState.generation_identity_sha256 失敗。Root對照真DTO欄位確認generation必須沿plan取值；要求owner全面核plan/receipt API，另建e provider-only核驗後再審新完整run。原d不得重跑或修改收據，這不是產品full-N矩陣通過。

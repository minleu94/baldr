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

### P03 現有同版來源轉接器再核（2026-10-09）

Root 實讀 `app_module/selection_current_source_pair.py`（既有提交 `05ebabd6`）：normal coordinator 在真正 producer 前固定 market/disposal pair，下游 writer 沿原 plan cutoff/exact pins，非 complete 不發 bundle。pair 明示核 run/pointer/snapshot/manifest 同版，兩 reader datetime 格式以aware datetime 比對。不能沿用早期「缺 adapter」診斷；剩餘是完整 Main／EXE／正常來源閉環驗收。Root 新隔離根 `C:/t/p03-sourcepair-root-20261009-f` 重驗既有兩個實際 capture 測試，2 passed／0.50秒，證明 pointer 前進後已取 pair 保持原版、兩 reader 之間前進造成混版會拒絕。JUnit `output/qa/p03_sourcepair_root_20261009_f.xml`；18項未在此重跑，不授完整20項或UI/producer資格。

### H20 F 子程序收尾與下一程序啟動條件（2026-10-09）

Root 實讀新 F runner 已將 Job 的 terminate/wait_empty/close 移入 finally，分開保存 primary/cleanup errors，最終 passed gate 也要求 cleanup_complete。另發現 fixture→Main 分支只依 prepare exit0 與 manifest存在，未核prepare收尾完整；已要求只有prepare tree_empty／cleanup_complete、無primary/cleanup error、無timeout才啟Main。最後拒絕passed不足以代替失敗後不得啟下一程序。原 static preflight marker錯誤 receipt 已保留獨立 `_01_failed.json`；這仍不是完整 Main 執行證據。

### P03 正常來源 coordinator 中央完整定向回歸（2026-10-09）

為核實目前已存在的 normal adapter，Root 在新隔離根 `C:/t/p03-sourcepair-root-20261009-g` 執行整檔 `tests/test_selection_current_source_pair.py`：20 passed／5.52秒，JUnit實讀 tests20/errors0/failures0/skipped0。測試包括來源先固定再產製、pointer更新混版拒絕、晚於cutoff拒絕、cancel/non-bool拒絕與incomplete無發布。Root另實讀最後案例，確實呼叫真合成producer、真BundleWriter與BundleReader.read_exact，保存一股1101 processed且來源 DB／capture hash保持不變；不是以mock writer替代這個正例。當前source SHA `14D41AF43240915084CB493AB42E2060B34973972260DEE44B96FCBA18D44314`、test SHA `3F35FD8E56AFCCD13D739C109DD8F5BBB69C4C787A2657EAE43759762DAB3BA8`。接受此backend定向範圍；沒有全市場、完整Main／EXE、收藏新程序或自然排程資格。

### H20 F 凍結候選一次完整 Main 授權（2026-10-09）

Root 已讀 F 主要完整 diff／最終 manifest，actual三runtime SHA與清單完全一致：controller `4e356485f782a149ac11272a775c2c50e5ff309ac9b1be2b3e9b18c6d103ba12`、child `67911f64ab2943373baf917b4112d45af8ae3fb395021dce1e7e2ff8e5a7e115`、preparer `3b7b139366ed8c035df44fc0cf1ba8ccf0e7a0d9086f8f151fe5be3372c481d4`。Manifest `be4c68abdc08958fda1c2e947da256175f6934e67caf11e3028afb8a051cb191`、7個static checks通過；Root實算6個E固定依賴全部吻合、unique C:/t root不存在。已授權owner凍結後再核pins/root，唯一一次controller native Main；120秒fixture／300秒Main／20秒Job清理不變。fixture cleanup不合格不得啟Main；Main worker關閉證據／Job empty／來源起訖／H20-first清理為接受門檻。此授權不代表已啟動或通過，不授原十股/684bp、新程序收藏或EXE資格；此片bookmark是同Main新typed讀取，已改正名稱。原source BUILD_INFO approved_for_launch=false仍保留；本片是明示合成worktree QA，不當作原artifact正式launch接受。

### H20 F 實測終態與重建來源下一步（2026-10-09）

owner native handle56186 terminal exit1，未進fixture/Main；controller在full s3 tree核驗拒絕。Root另獨立以manifest檔名集合對照：expected4161、actual4163、missing0，extras為 `data_module/__pycache__/__init__.cpython-311.pyc` 與 `pinned_sqlite_read_session.cpython-311.pyc`。owner完整hash對照changed0；其來源診斷封套待中央回讀。Root未刪除、忽略或修改extras。F unique QA root已建立但case空，沒有資料庫／Main接受。下一G先評估從原已pin archive重建新隔離read tree，逐4161 size/SHA及22pin核對，保留原manifest/build/archive bytes；明示origin與reconstructed root，不能修改原snapshot_root或宣稱s3 unchanged。先審QA path adapter與純契約，未放行G Main。此拒絕是full tree新增cache，不是required22pin漂移；原source BUILD_INFO與F失敗保持不變。

## F03 三路暫存協調器中央複核

2026-10-09：Root 在全新 `C:/t/f03-group-root-20261009-a` 執行真 synthetic parent 定向測試，terminal exit 0，1 passed／13.63 秒；JUnit `output/qa/f03_group_root_20261009_a.xml` 為 1 test、0 failures／errors／skipped。正常 scoped mypy 兩檔 clean，py_compile exit 0。前後三檔 SHA 均吻合：source `0B0864D9017FAC0EFBC2E26F450EFA2C7A82C17D53AC1674B8B881D240B11AA2`、test `CEA9DE7218D61EF113E1C6F18A54ECC5B6E1948DFEF784036799AB0C7943EB5E`、QA `B52EC63CDEF22979B502C83B5D49B56E02756E3D01DC7D16AEA57C205C7C83D1`。

已讀實際測試及故障矩陣：MA／KDJ／volatility 各 begin／consume／end 失敗及 callback 後取消均清空整組並永久失效；同一真 typed parent／snapshot／row 引用供三路處理。Root 要求修正無效 DTO finalize 呼叫的證據表述：其一般拒絕不能證明單一 finished 分支；finished、issued session 為 None 及 partial buffers 清空由獨立結構斷言支持。

接受範圍僅為未核資格的單 parent 暫存 fan-out，不包含多 parent、完整母體、共同 prepare／seal、qualified index/query、UI 或 EXE。下一片須保留唯一 reader authority，完成全部 parent 與 counts 核驗後再共同發布，不能先發布 MA 後讓其他 member 失敗。

## F02 e 實際 DTO 差異與下一片分工

Root 已實讀 e `attempt_ef50a7bddb184cee/acceptance_receipt.json` 與 native terminal：exit 1；stdout SHA `fe2f79438c9d1d1037ce1cda607eafa1b28f0806f10f605b9ec0d7c68d9c8b6c`。真 StoreReader counts 為 declared_count／included_count／excluded_count／processed_count／pending_count／missing_data_count／missing_data_pending_count，值依序259／258／1／258／0／1／0；QA provider 卻比縮寫鍵，因而拒絕。Producer、bundle writer 與兩個 pointer reader 皆0，完整 query 尚未進入。第二 SQLite connection 仍須實際 call path 解釋，不能直接放寬 expected 次數。

Root 已讀 `BALDR_F03_MULTI_PARENT_GROUP_PUBLICATION_PLAN_20261009.md`，接受完整 parent ledger、prepare 與共同私有 issuer 方向；先釋出新增測試／QA 的真多 parent 切片，不改 F02 仍依賴的共享產品 pins。MA／KDJ／F06／F17 shared publication 實作待固定來源驗證收尾後再分派，原全母體 query、UI、收藏 scope 保留。

## 真人檢查草稿與隔離多 parent 前提

Root 再核推薦 view SHA `5F0FAA96F246C62C7693E1771D538D88B72AE95A6544208D74B14650ED16EDD5`、layout test SHA `61E4ECAF7F4E339798C73950808D5CB17B4F03B9A23B8C1B73DF48C33C340701` 與先前完整11pass證據一致，沒有無故重跑。真人草稿補上理由文字焦點內 PageDown／End，以及正常關閉後使用同一已提供啟動檔重開 H20 收藏；仍明示現在沒有新入口，不要求使用者先驗。

Root 已實讀 `synthetic_full_store` fixture：真 SQLite／兩個真 parent、257 included／1 excluded，segment 為256+1，包含 cancelled→resume→complete receipt chain。該 fixture用 tempfile而非pytest tmp_path，下一 native測試須明設全新短TEMP/TMP、保留外部封套；fixture自己的合成DB刪除不作用正式來源，source讀回能力由已保存capture證明。這片不替代1000檔p95或共同seal。

## H20 G2 固定 archive 重建中央逐檔核驗

Root 以 native唯讀命令逐檔計算 `C:/t/h20gsrc_20261009_b/artifact/source` 的size／SHA，對照原 s3 manifest：expected4161／actual4161、77,229,228 bytes、missing0／extra0／changed0，完全相等，terminal exit0。另已讀 G2 archive reconstruction run receipt：synthetic ZIP tests exit0、fixed reconstruction exit0、Main／SQLite／original data皆未啟動。此核驗僅接受重建來源內容，不授 Main 或 EXE 驗收。

同時實讀 G2 第一次 static receipt，`candidate_and_fixed_dependencies` 為 FileNotFoundError，其餘來源22pins／E清理證據通過。仍須新 immutable candidate manifest／diff及修正後前置檢查，再由中央審核完整 Main；原 static失敗及G1長路徑失敗保留。

## 多 parent 故障注入的中央審查修正

Root 實讀新 multiparent test 與 group consume順序。第二parent的 volatility callback前，MA及KDJ已各增加S0256，因此當下應是MA/KDJ257、volatility256，group已完成數仍256／1parent。原測試在預定RuntimeError前assert三路均256，會先出AssertionError而未命中預定故障。已要求owner沿既有live handle77015觀察到終態、不修改live source，再修正注入前提並以新attempt驗證；須確認真指定RuntimeError原因及全部首段256筆暫存清空。這是測試前提缺陷，尚未據此認定產品功能失敗或多parent通過。

## H20 G2 完整 synthetic Main 單次核准

Root 已審G2候選差異，並另比F→G2 controller，確認僅明示origin metadata與重建physical read root、完整內容／來源封套before-after；child維持`67911f64ab2943373baf917b4112d45af8ae3fb395021dce1e7e2ff8e5a7e115`、preparer維持`3b7b139366ed8c035df44fc0cf1ba8ccf0e7a0d9086f8f151fe5be3372c481d4`。中央實核四候選檔SHA均與manifest相符，manifest `de29a7a280a37a1bc4fba621fb018a81a5aad46d4f80b61d380dcab1bd6827db`、diff `9e806b4b71c8ec980308d6693407137b62839173c95377236a162b3cf5ebd819`、static02 receipt `363ee967df547fa31e544e83b57d3026ffbe4eb0ddff1f6be777f2cb9de087d8`。Static status passed、Main/preparer false，新`C:/t/h20dual_main_integration_candidate_20261009_g2`不存在。

結合中央完整4161逐檔相等證據，釋出一次frozen G2完整synthetic Main run，限新scope、原timeout／Jobcleanup與Ekeeperguard保留，owner追唯一handle到terminal。不授原H20/EXE/真人launch資格；synthetic1234bp與same-process fresh read仍分開判讀。尚未取得本次run結果。

## F02 F 候選 WIP 連線上界審查

Root 讀F候選 WIP，counts已改真七個*_count鍵，但role validator暫為raw==1／scope>=1，guard的expected_connections預設None時亦接受source>=2。已要求各模式明示精確role counts與固定callsite上界；provider-only須raw1+scope1，第三次或同role2次不可通過marker或terminal。若fullrun真bundlewriter另作scope檢核，須先給實際callpath及mode-specific精確數量，不用無界最低數取代。候選尚未凍結或核准native/fullrun。

多parent attempt b實際terminal1，2passed／1failed／176.36秒。Root讀log確認injection={}，未打到預定故障，符合先前review；原輸出保留，新修正只改測試前提，不改producer或產品。

## H20 G2 完整嘗試終態中央核實

Root 實讀controller_receipt／launcher_exit與fixture stderr：launcher terminal1；preparer在601行guard_existing_directories列舉使用未定義output_root，NameError，exit1。fixture Job cleanup complete=true／tree empty=true／cleanup errors=[]，Main launch gate=false、child_pid=null、result不存在。controller的child_exit_code=1是未啟動失敗狀態，不能解讀為已跑Main。source artifact／origin before-after均true。已交派新H副本先做四支script undefined-name完整核查及standalone preparer驗證；不改G2、s3或重用已建立scope。

## 多 parent c 針對性重驗的證據界線

Root 已實讀c log：1passed／2deselected／132.12秒，owner確認handle61040terminal。該版測試SHA `53E3AEA041AE4880AE82343BBFE12525E013F4D06D587B1BF0E4CC3AB5B34630` 已核第二parent當下partial counts=(257,257,256)、首段完成數256／1parent與全組清空；但只有callback_failed一般碼，尚未assert原cause型別／訊息。Root要求補明原cause為RuntimeError及指定injected_second_parent_volatility_failure後凍結，中央再跑完整3項。c不冒稱新增cause assertion或整套驗收通過。

## 固定版多 parent 中央全套啟動

Root核測試SHA `BDB0453BF24199A4685A41A6B3CB5434006B4928F0A3F3E27D82A9834796CF74`包含精確RuntimeError cause斷言後，以全新TEMP/TMP `C:/t/f03-multiparent-root-20261009-a-temp`、basetemp `C:/t/f03-multiparent-root-20261009-a-pytest` 啟動完整3項native測試，JUnit預定`output/qa/f03_multiparent_root_20261009_a.xml`。唯一root handle34772，第一次poll仍live，尚無結果。不重啟或重用scope。

空出的subagent已接派獨立QA效能profiler候選：先讀原1000檔frozen controller/recovery pins、保留完整page/filter/global-sort操作，不改產品／來源／store、不重產1000。靜態候選經中央審核後才執行profile；原300ms gate與未完成EXE/真人驗收保持不變。

## F候選精確模式成功出口複核（尚未凍結）

Root再讀F WIP：role validator現在要求明示expected_attempts，各role attempts/allowed/opened皆相等且精確等於預期；worker provider-only與parent terminal validator已分別傳入provider-only或full模式固定callsite counts，舊expected_connections預設無界路徑已移除。仍需凍結diff、純負向契約與native provider-only證據才核准完整query；不能因WIP閱讀視為驗收通過。

## F02 F 凍結純契約中央重驗

Root實核supervisor SHA `3c8552b84422ec47abcc14cd81108a5f25ac5676b64196092ef937c6c6f0777b`，獨立執行`--self-test-continuation-sqlite-callsite-contract` terminal0。兩模式精確raw1/scope1與raw1/scope5通過；8個次數／登記負例、12個真public count DTO schema正負例全true，產品module未import／SQLite0／producer0；DTO source SHA `16cac8d2640f34f0ffe0de667573025d5f95438d8c1ed941709fb49831d52c2d`符合固定pin。接受純契約，不等同native provider或完整query通過。下一步凍結diff/manifest審核後單次provider-onlynative，不重複已通過純自測。

## F02 F 單次 provider-only native 核准

Root已審F manifest及diff（含DTO真鍵、精確caller route、來源pin、URI selftest正例在guard外／unknown caller在guard內拒絕），manifest `4172eb73b0f971bf16966f6511150d1bb9928a695a7e648cbdc33fab5029337e`、diff `bd3aec55de3c46d9169bb6819f4f6bd05acc431971a42982ba04765273d4ef48`中央實核相符。Candidate／preimage／固定target／inputmanifest／四產品source pins逐一實核match；F_target只有固定target檔，尚無attempt。

結合root純contract terminal0，釋出一次frozen F provider-only native：新scope、raw1+scope1、producer/bundlewriter/query0、sentinel與wrapper還原、六root inputs before-after與Job空樹。owner追唯一handle到terminal，不重啟；完整query matrix仍待native證據中央審核後另行釋出。

## F02 F provider-only 失敗定位與 G 候選分工

Owner 回報唯一 native preflight terminal exit1：外層 `C:/t/f02_ma_composite_257_v4_097d4faa5c08`、target `attempt_9cde26d6219d4cc3`。raw role 1、scope role 0、unknown caller 拒絕1；未通過，不釋出 full query。依固定來源呼叫順序定位 scope constructor 的 dataclass generated `__init__` frame 未納入精確鏈；收據未保存 stack，不能稱為直接 traceback 證明。Root 接派全新 G 候選註冊並重驗 init function/code/globals/class 身分，補純正負契約；沒有核准重跑 native 或放寬原來源守衛。

## 原 1,000 檔三操作 profiler 純契約中央重驗

Root 獨立執行 `profile_candidate_selftest.py` terminal0，child `38df4564dd0fcd6f5c12c63617f538c2b0ae815aa65397e8365e21e5a58a5237`、supervisor `8f3fefef8fc39f2ddfdb486111aff39d4a1f04ec9ca5d9e5810dcea3938926a2`。固定 runtime acd18a1e 與 producer 2897 分開；page／完整 filter selection+page／完整 sort selection+page 三操作均列入，原 failed p95 保留。未啟 runtime、DB、store 或 producer；純契約通過不代表實際剖析或效能改善，native 仍待完整差異與隔離流程審核。
## H20 H 前置產製及 1,000 檔診斷單次接派

Root 實讀 H static05 receipt passed／execution exit0，四檔 SHA 與 manifest `7f9ff3bce7741edfe0f31a61faf015f3b2d59131054e5ee657e29313087276f1` 相符。審過 strict preparer-only branch：Main pid／exit保持None、無result，需完整fixture路徑／來源檔pin／來源樹前後一致與Job cleanup。已釋出一次新短root preparer-only native，E guard／keeper未安裝不得計為驗過；尚未釋出完整Main或真人入口。

Root 實核 profiler manifest `41ac6a08d7202f874772246cf49e88cddd6baf7ad121382293c76416f4f585a8`、child diff `24fe4191e5d5f789d489c9e3fa5bff3855cfe835b05f5101119b54dc04272aa3`、supervisor diff `905aaf18342c5dd613ead256355743274f4a6dd30d3b4c058e68903b325a5e55`。三操作包含完整selection+page，原guard／source pins／Job deadline保持；接派固定child38df4564與supervisor8f3fefef唯一native診斷，新private root、600秒／10秒清理，不重跑producer或benchmark。等待實際結果，單筆cProfile不得取代原30樣本p95失敗。
## 原 1,000 檔 native 診斷已啟動

Owner唯一session `28999`；root透過唯讀native CIM實見Python程序 `22232 → 56184`，對應新 full_operation_profile 候選。stdout安靜不作terminal判定，owner持續輪詢同一handle，沒有重啟。結果仍未核為passed，原p95失敗保持。
## H20 H preparer-only 實際終態中央初讀

唯一owner handle57455 terminal exit1，未重跑。Root實讀controller：fixture_prepare_exit_code=0、cleanup_complete=true、tree_empty=true、primary_error=null，來源artifact前後一致；Main pid=null。失敗由新validator回報 `preparer_only_source_sha_field_mismatch:manifest_path`。Root實讀required_source_pins把保存的manifest_sha256與raw file SHA直接比較，接派owner核其原保存契約是否canonical identity；不得改fixture值迎合validator。前置產製程序成功不等於整體驗收通過，保留failed狀態待精確修正。
## H20 H 表示法錯誤定位及 H2 接派

Owner定位保存manifest_sha256/capture_sha256為 `sha256:<64位hex>`，raw file pin為無prefix的64位hex；preparer既有 `_unpadded_sha256` 明確驗此格式後比檔案SHA，root實讀該helper確認。H新增controller直接比較兩種表示法而failed，不是來源漂移或preparer缺資料。接派全新H2僅做嚴格canonicalizer及純正負例，保持保存來源欄位、file identity、source group及全部hash守衛。尚未批准新native重跑。
## 1,000 檔剖析已進實際 runtime

Root唯讀native CIM與 `C:/t/p01_7mgftjof/phase_times.jsonl` 實核：固定acd18 source import完成，source pin365cd8吻合；1000檔selection與page0 baseline已ready（50列、20頁，setup27.9128313秒）。child 56928→40800仍live；這是setup階段實證，不是三操作cProfile結果或原延遲gate通過。Owner沿唯一handle28999追蹤，不重啟。
## F02 G 純 stack oracle 修正

Root實讀generated-init角色判斷及純合成鏈：精確post_init→registered_init→make_bundle保留；owner007診斷六個frame identity全true、helper分類research_scope_validation。純測試卻把dataclass init的None回傳值當role，造成假失敗。接派僅修oracle：從當次helper記錄取實際role，另assert init回傳None；不改classifier或allowlist，native未釋出。
## F02 G 中央純契約通過及唯一 provider-only 接派

Root實讀F→G runtime diff並獨立執行purecontract terminal0；固定supervisor `cb5f92b6312ef9f32bb82a1e157467f153439cbe573430b4845f4cdb636f696b`，新增generated init identity registration／live recheck與精確六段chain，raw與bundle validate路徑保留。三路正例、init/code/globals/module/qualname替換、wrongparent、unknowncaller、額外次數負例全true，產品import／SQLite／producer0。接派唯一新G provider-only native，須先核target/productpins、raw1+scope1、完整輸入前後一致／Jobempty；未釋出fullquery。

H2修正版root實核manifest063701／diff0866／controller09b2全部吻合，只有嚴格sha256表示法比較helper與純測試新增；已接派唯一新preparer-only，owner handle72261 live，沒有Main啟動資格。
## H2 前置產製中央接受，接完整 synthetic Main

Root實讀raw receipt `d045b824ac9e0671d2f532532c975f9ff7290727076d7fe1cd5a9672b2ad8e2c`，status passed_synthetic_preparer_only、exit0、Job cleanup/treeempty true、sourceartifact及fixed_e_runtime_dependencies前後一致，runner09b2固定。Eguard/keeperfalse、Mainfalse，故只接受preparer。接派同固定四檔唯一新shortroot full synthetic Main，owner追同handle到terminal；不提供EXE或真人入口。

G native未啟動：原TARGET_PATH仍Ftarget且已有failed attempt，守衛正確拒絕。接派新G2僅複製同ca866固定target到全新sibling root並retarget，保留原attempt；不得放寬無舊attempt限制，待新diff/hash核對後再執行。
## 效能剖析原始資料中央初讀與 Current 對照

Root實讀raw child：三操作profilewall page3.0905377s／filter2.0716593s（6matches）／sort3.9429145s；inclusive耗時集中read_selection_page、_materialize_page、_read_session_child_snapshots、read_selected_exact，exclusive包含遞迴float-tree／isinstance／canonical JSON。整體supervisor因launcherPID56928身分NoSuchProcess而failed，保留failed，不拿childpass替代。這些有cProfile負擔的單樣本不是p95改善證據。

Root比對current與acd18 frozen：current feature float-tree已有exact-type fastpath，git log來源7254bd8f；另有dd99fa5b單次解析、31f1fed4重複驗證修正。已接派owner先對照這些既有成果及query分支，再提current下一個熱點修正，避免重複實作已落地優化。尚未改產品source pins或重跑性能矩陣。

Root實核G2 supervisor f0a6263d／diff ae629ce3／target ca8663ad，one-line retarget與新target僅腳本無attempt；接派唯一provider-only，不改守衛、不釋出fullquery。


H2 full synthetic唯一handle65802 terminal1，root實讀child stderr首錯synthetic_market_wal_keeper_not_attempt_sibling（L1752），位於keeper啟動／MainWindow建構之前；controller main_started只表childlaunch。fixture成功、child清理空樹／來源保持一致；接派窄幅新候選核固定keeper sibling layout，不刪守衛、不重跑。G2 provider唯一handle7015也terminal1，owner正核首錯，fullquery未釋出。

## 最新失敗邊界精確定位

Root解析G2原worker.stderr：error為 `continuation_source_pin_value_mismatch:market:pointer_sha256`，兩次預期來源SQLite均已allowed/opened；因此generated-init守衛已跨過，失敗在typed pointer DTO與QA固定值的比對。接派核canonical prefix／file hash契約，不改固定source或產品；Jobempty/inputunchanged不替代provider pass。

H2完整run仍未建MainWindow：root實讀controller env keeper指fixed E原件，child先_load_exact再核parent==ATTEMPT，故pre-Main拒絕。核准H3窄幅準備固定6e0b keeper完整bytes sibling，controller仍核Eorigin並另核新sibling、childparentguard保留；靜態先核keeper內部路徑限制，避免可預見缺件。尚未核准新Mainrun。

Root初讀H3 WIP local dependency核驗：兩個固定E sibling皆plainfile/nlink1/SHA及fileidentity記錄、原Esource核驗；runtime前後完整列表相等列入兩modegate。尚待frozendiff/hash與必要static結果，不把WIP視為Main接受。

## F02 typed pointer 格式完整定位

Owner核市場raw pointer SHA9cb685及處置be6ee3與固定inventory一致，兩typed reader的pointer_sha256皆為 `sha256:<raw>`；QA兩expected常數漏prefix，snapshot／manifest既有expected則已prefixed。兩邊run_id/scope/current_only/historical=false亦吻合。接派新H僅兩常數補prefix＋新同bytes targetroot，保持strict equality，不剝除prefix或改source；尚未釋出native。現版1,000檔source archive開始於獨立QA目錄，未視為性能結果。

Root實核H3 keeper6e0b/helper22d08兩個sibling bytes SHA與E固定值吻合；初讀localcopy negative覆蓋tamper/missing/hardlink與env parentguard。Root初讀F02 H兩expectedcanonical pointer與purepincontract正負結果，待finaldiff/hash交付再釋出native，不重做完整guard自測。


Root獨立執行F02 H purepincontract terminal0，supervisor69f0a37f，兩canonical pointer正例及八欄位負例均通過，無productimport/SQLite/producer；待frozendiff/targetinventory。Root初讀current source preparer發現helper import後才驗SHA，接派改為先驗固定bytes再載入，archive固定HEAD及新runtime qualification區別維持。


Root實核F02 H 三行diff（兩canonical pointer＋新target）及supervisor69f0／diffcf349／manifest33a5／targetca866全部吻合，新target僅單檔無attempt。結合root purepin terminal0接派唯一H provider-only native，raw1scope1／source六root保持／Jobempty；fullquery未釋出。


Root實讀H3 native focused stdout：5passed／0skip／0.58s及manifest9c566／diff707f相符，接派唯一H3fullsyntheticMain，新run-copy七檔及兩localfixedbytes保持，尚待實際handle/終態。Current source attempt04檔案映射在declaredroot上層造成拒絕，失敗保存；接派執行前純prefixmapping與Windows長路徑檢查，使用短root避免已知限制。


H3 full唯一handle89123 terminal1，root實讀keeper schema必需10表／preparer只有9表，缺industry_indices，MainWindow未建。source/E/localdependency前後一致、Jobempty不等於Mainpass。接派H4僅補synthetic schema並一次核keeper後續fixture欄位SQL；keeper/guard不改，原資料不碰。F02 H唯一74484 terminal1，root實讀segmentroots_mismatch；raw1scope1已成功、source六root保持，完整query仍未執行。


Root獨立核current d12 archive SHA與manifest一致、4465檔／80182012 bytes；manifest SHA2ee9807。Repository rawSHA archivecc3e66與原frozen85a8ce不同但gitdiffnone，接派核LF/CRLF及全部critical actualbytes pins，不把semantic相同稱raw相同。H4盤點keeper後續所有fixturechecks完畢，industry_indices六欄PK/index空表為必要最窄補件，不造資料或資格。


Root獨立bytecompare確認d12 archive repository與原frozen差異僅CRLF（新1363行CRLF／原0），LFnormalized bytes完全相等；actualrawSHA仍各自固定不能互換。Root初讀H4 industry_indices六欄／複合PK／日期index空表及query_only schema讀回、rowcount0/DBbeforeafterpins核驗，未新增金融計算或產業資料；待必要測試與frozenhash。


H4 root獨立schema native1passed0.53s（sandboxWin5failed保留），manifest2a7f49／diffef2e7e與八檔actualSHA全match，接派唯一fullMain，未新EXE。Current d12 exactread設計root接受三身份／完整1000counts／actualarchivepins，已接派實作QA controller+有界Job，不以靜態相容或P01opener冒稱F17資格。

## 2026-10-09 H4 實際啟動與根目錄盤點續記

H4 owner 已回報唯一 controller session 56165，argv 指向凍結 run-copy 的 snapshot_and_run.py；prelaunch SHA 為 9df79fbfc732dddcb24a71fff898dbe3c9d4acfb7487074c8ebb203bd36cc9e8。Root 實讀 prelaunch 列出的 manifest／diff 與檔案 pins，並確認 C:/t/h20dual_h4_main_run_20261009_a 已建立隔離 case/output、watchlist COW 暫存。這些檔案只證明流程已開始，不證明 MainWindow、下鑽、收藏重開或完整測試通過；由 owner 輪詢既有 handle，禁止觀察超時就重啟。兩次 launcher 前置誤呼叫未執行 controller，其失敗記錄保留。

使用者詢問根目錄副本。Root 實查六個未追蹤檔案 presenter.py、reason_engine.py、recommendation_service.py、supervise_f02_ma_composite_257.py、test_r019_reason_regime_parity.py、test_recommendation_view_presenter.py，已把逐檔大小、建立／修改時間及 SHA 保存到 output/qa/root_file_inventory_20261009_a/inventory.json。兩個指定服務副本與正式模組 SHA 不同，未查到產品 Python 的直接根目錄 import；來源尚未證實，不據時間推定作者，不移動、不刪除、不覆蓋正式版本。待來源／使用狀況及可回復清單確認後再整理。

F02 I supervisor 已落地但尚未凍結，沒有原生測試授權；P01 d12 controller 仍在實作。P01 不以 case_root 字串代替實際 sealed-store inventory，舊 producer、舊 runtime qualification 與新 d12 runtime 身份須分開保存。

H4 終端覆核：owner session 56165 已 exit 1；root 實讀 controller_receipt.json 並獨立核 SHA 4fae03520d7c062f10e78d57e455f1c51cda581d61f545f3775675a58a535298。preparer exit 0、child exit 1、兩 Job cleanup/tree-empty true，original_data_opened false、固定 E／artifact／snapshot inventory unchanged。Root 實讀 child stderr 及固定 E operation L165–214，確認 operation 本身仍從 E origin 載入，而 H20_SYNTHETIC_ATTEMPT_ROOT 指向 H4 run-copy，觸發 synthetic_market_bridge_origin_mismatch；尚未完成 verifier／guard／keeper／MainWindow，不以隔離 watchlist 暫存推論主視窗已啟動。另 source-map restore RuntimeError 必須保留主錯誤並修復。

已接派 H5 僅候選實作／純 contract 驗證：operation、legacy bridge 及其完整 sibling 依賴以原字節 plain copy 納入新 run-copy，僅精確已 pin loader 路徑映射至同 SHA copy；不更改或放寬固定 guard 的 origin／SHA／hardlink／reparse 檢查。必須一次盤點 dependency/module-cache origins 與 restore branches；尚未授權 H5 完整 Main。

根目錄來源續核：root 用 git show a8c81bf5:<正式模組路徑> 與根目錄 bytes 比較，獨立結果保存 history_comparison.json。reason_engine.py、recommendation_service.py 及兩個指定測試檔與 a8c81bf5 歷史版在 LF 正規化後完全相同；recommendation_service.py 的原字節 Git object 770d5fe6cf7c39e7fefc363810de15a113ee7b5f 亦可在歷史正式 app_module 路徑找到，396c08e8 已修改其正式版。因此可確認這四檔是歷史內容副本，但尚無證據證明由哪個操作落到根目錄。presenter.py 不等於同版本正式 presenter，supervisor QA 用途需另查；不據其檔名自動移入正式模組或覆蓋現行內容。

Root 實讀 F02 pinned complete receipt4：segment_reference 為 null，last_parent_reference 才等於 receipt3 的 parent_reference。已指示 I oracle 對 complete receipt 保持 sequence4／previous ID+SHA／counts／last parent 精確檢核，同時要求 segment_reference is None 並加入非 null 造假負例；不得把 partial receipt 的 segment_reference 形狀套到 complete receipt。

P01 owner 實證 b3 是 recovery/source/store 根，mc6 僅 benchmark attempt；root 接受此角色區分，要求新候選保存獨立 correction receipt，不改 manifest08、不搜尋 fallback 路徑。Root 初讀 WIP controller 仍見 mc6 固定 input paths，已要求修正且所有整數 counts 必須排除 bool；尚未凍結或啟動新 runtime exact read。

F02 I root 獨立純驗證通過：候選 SHA bad3a219ec0e92fc7dc4cfb5a3df75c6fc2d241f062e3bf10466f9334afc6be7，執行前後一致，output/qa/f02_i_root_parent_contract_20261009_a/exit_code.txt 為 0；stdout status passed_pure_readonly_contract_only，所有 predicates true／15 mutation negatives rejected，輸入六根前後相等。Root 查 H→I diff 刪除的是錯誤 generation container root 判定；新 provider protected_sources 使用收據推導的精確 segment roots，不改 product guard。此結果僅證明 pure receipt oracle，不代表 provider／SQLite／query／Main／性能通過；待 frozen manifest 與 DTO audit 才核准唯一 provider。

根目錄六檔已複製到 output/qa/root_file_inventory_20261009_a/preserved_originals，backup_receipt.json 核每檔 copy SHA 等於原檔且原檔前後 SHA 相等；尚未移動或刪除原檔。

P01 current archive root 全清冊獨立驗證：root 未載入產品，逐一讀取 extracted d12 tree 的每個 regular file，拒絕 reparse，核相對路徑、原字節 SHA、size、missing/extra；4465 files／80182012 bytes／0 pyc、errors 空。結果 output/qa/p01_current_root_inventory_20261009_a.json；manifest08 actual SHA 123dbbbe27a02a922bea2e08345c34cbedb2b45af53ecbaceb3e65fec7f74149。這證明目前封存 source bytes 清冊相符，仍不證明 runtime exact-read 相容或任何效能 gate。

F02 I 進入唯一 provider-only 續驗：root 已獨立核 supervisor BAD3A219…AFC6BE7、target CA8663…3F485B、輸入 manifest84da、RO/capture/store/repository/bundlewriter actual pins 相符；讀 DTO audit 後要求修正兩個 provider 函式歸屬為 supervisor（不是 fixed target）與 README 繁體。已授權 owner 在保存 freeze manifest 且 prelaunch 全 pins／全新 attempt 核驗通過後，唯一執行 I provider-only：兩個精確唯讀 caller、有界 Job／原期限、前後六根與產品 pins、producer/bundle/query 0。任何核心 pins 改變／preflight 拒絕均停止，不自行重跑；full query 仍未授權，尚未收到實際 handle。

F02 I freeze 最終 root 獨立核：manifest SHA 08532148d6e044fa73267ad2c1cb8289cb4a4e2a01e1f3e367607f13e93376a5，其 24 個 path/SHA/size file pins 全部吻合；output/qa/f02_i_root_freeze_pins_20261009_a.json 保存逐檔結果。已通知 owner 沿唯一 provider-only 授權執行，仍未收到 live handle。

P01 path correction root 實讀固定原 report 與 receipt，兩 raw bytes SHA 皆與 correction receipt 相符：report.case_root=b3、receipt.sealed_store_case_root=b3，而 receipt.case_root=bo 是獨立 readback-run 根；report source_root 是原 acd18 extracted source。mc6 不得作 source/store 路徑，新 d12 runtime 不得取代原 producer/readback provenance。

F02 I 唯一 provider-only session37617 terminal1：root實讀 C:/t/f02_ma_composite_257_v4_7865e8cd59c8/supervisor_receipt.json，SHA ec718c3c99f363d7aaedd356bbbad4c323e8e14168a62e48bfb66330f8c3c5d3；worker1、輸入六根unchanged、Jobclosed且zero_owned_processes_proven true。錯誤 canonical generation path299 UTF16 units普通exists false，extendedexists true且plan/receipts存在；root診斷保存 f02_i_root_failure_longpath_20261009_a.json，不把WinError3判成來源遺失。固定 QA tree_signature 對短根render後直接lstat長descendant，與錯誤路徑/階段一致但原stack未保存；J僅QA等價逐descendant渲染與隔離重現/負例實作授權，未native、不移來源、不改產品pins。

P01 v2 root獨立static preflight exit0：controller e21216b098778c6019ca963a94ecc1cb2e81195dfff882efc3e4628a716b1b3b／manifest4606d20bba3281035b1337c1c4cea3823d2854f24bc573a6910c78bf0ebc3743，root log p01_current_root_static_20261009_a.log、收據 static_preflight_4387b581c021.json；來源/store before-after一致、product/network/SQLite/subprocess0。已授權 owner 唯一fresh native P01 exact-open/full1000selection/page0，600s有界Job，不重產、不profile；尚未收到handle，效能矩陣未授權。

P01 v2 唯一 native prelaunch session結果 failed，attempt C:/t/p01cur_rd_8d3a751d47；root實讀 supervisor_result.json rawSHA403e843930d6f41a82249473fdff14b03974b9921386d96459a96600501261de。child_launch_count0、parent subprocess attempts1／approved0、Job空／cleanupcompleted；source_and_store_before/after皆null，不能聲稱此次native有來源前後驗證。完整traceback指出audit1769拒絕Windows Popen payload。Root讀本機CPython Windows _execute_child確認argv已list2cmdline成string；既有OR判定已足以因非list拒絕，不能推論default executable當時非None。已接派v3保存四欄actual audit probe（audit hook在CreateProcess前sentinel中止／無OSchild），固定單一精確exe/cmd/cwd/env/single-use契約、純負例與新版本封套，不改v2失敗。另要求before inventory及failure後postflight/未完成狀態保存完整；尚未授v3native。

H5 root 靜態續審（未凍結、未執行）：restore 已分開 verification_reasons 與 restoration_errors，legacy 尚未載入以 not_activated_module_not_loaded、partial import 移除以 partial_import_removed 記錄；已要求 operation 中途 import／helper cache 錯 origin／legacy 未載入／wrapper 被替換／setter 還原失敗負例，成功仍須完整 verification。新的控制器/純案例尚在實作，不以此靜態審核聲稱 Main 通過。

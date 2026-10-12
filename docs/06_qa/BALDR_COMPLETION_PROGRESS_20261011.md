# Baldr 補完接續（2026-10-11，進行中）

> 最新：使用者為文件治理要求暫停；Root QA Python0、subagent已停。Health Main1PASS；P01 M25未封存、Main native crash未解；P08完整旅程待天然時間。接手prompt見末節，完整Gate仍待。

> 前次紀錄：P01唯一warm profiling90樣本完成且Job自然0；P39 40/2，V2首次建庫後日曆回讀與unit fixture仍待。Health joint v3正常957檔mypy零錯誤。完整Gate未接受。
> 前次紀錄：日曆50PASS、legacy17PASS/1SKIP與Health saved-log來源回放均通過。P08 fixture5原41仍40/1，已定位首次benchmark writer錯用reader的missing-DB前置條件；新產品修正待審查，完整Gate未接受。

> 前次紀錄：日曆public selector原50項與actual來源守衛通過；Health保存log來源回放通過但新normal types待跑。Legacy v2終態見末節；P08原41仍40/1停V2 benchmark，fixture5 writer時鐘修正待QA，完整Gate未接受。

> 前次紀錄：固定P38＋fixture2正常型態6／14來源與projection15通過；績效40/1停在V2首個intent的日曆因果守衛，完整Gate未接受。詳見本頁末節與具名收據。

## 最新接續：程序資源限制與 Health v6 真 Worker 驗證

使用者於 2026-10-11 恢復補完，要求禁止 subagent 留存／反覆增加 Python 造成 RAM 耗盡。本輪限制已寫入 shared context；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 scope 仍有效。沒有新增完整工作包或 Gate 接受。

### 程序資源與收尾

Root 的 `run_one_owned_qa_root02.py` SHA `89e3886b740010926bbb03ea1c409583b09f21bb348f8ade23c3df0f3e09fd1c` 用同工作區 named mutex 阻止重複 QA，父程序 suspended assign Job 後才 resume；讀回 kill-on-close、12 個程序及 8 GiB 全 Job committed-memory 上限，啟動前要求至少 8 GiB 可用 RAM。Orphan probe 收據 `single_owned_qa_dc04c364e4974270be1a2bdb38efcf23/receipt.json` SHA `1109fc11c2b81c905000ababea787aafcb16873aa6f0c19b8064c06df2de79f5` 證明父退出後剩餘子程序被同 Job 回收，終態0。正常驗證若需要強制回收，仍以125拒絕成功。未宣稱 mutex 競爭負例或記憶體分配壓力測試已執行。

本輪所有已結束 Job 都排空、handle 關閉、mutex 釋放；只有一位 Luna Max 做 P01 靜態候選，禁止 Python／import／compile／QA。Host 盤點有其他專案程序；20:32 UTC 新一批 Python 的父系實際屬於 Antigravity IDE 的兩個 language server 與 formatter，與本 QA Job 不同，沒有終止它們。PID 可能重用，判斷必須含建立時間、實際來源與父系；不能以舊 PID 或整台 Python 數量推論洩漏。

### Health 來源清冊與傳遞

原 617 pins 的正式父程序補充先重建為875，explicit F12 synthetic root 未設定的 setup failure保留；納入 scripts 後為887。Root 再由全部31候選入口、遞迴 AST 匯入及15個可解析內嵌 child 字串重建764模組／891 pins；收據 `health_complete_overlay_closure_16e77edb706a474cba81ac9ee6e54be5/receipt.json` SHA `a356d7216765683671f560fcd02b04f8a1814d4b76dcc0c160f280cc8bdf6707`。這是靜態允許清冊；每個真 PID 仍檢查實際 exec／sys.modules 路徑與 SHA。

17 個原合成來源與月營收 DB／CSV／raw HTML 起訖固定，SQLite 三種 sidecar 保持不存在；最長290字元來源只在 OS syscall 用 extended path，不改 canonical identity。Qt 的相對虛擬 `signature_bootstrap.py`／`shibokensupport/*` 僅在沒有對應 repo 檔案、shiboken6 載入路徑與三個檔案 SHA固定時另記第三方 embedded source；其他未知 repo source照樣拒絕。不宣稱全 Qt binary 核驗。長 child `-c` 程式用 create-only 私人檔案傳遞，完整 bytes／SHA、原指令與改送指令均保存；child核 SHA 後以原 `<string>` 執行，argv／原 supervisor／期限不變。

舊原始失敗均保留：root03 長路徑讀取、root04 scripts 漏列、root05 工具自身字串轉換 SyntaxError（未跑 pytest）、root06 Qt 虛擬來源錯判及 WinError206、root07 Health baseline 依賴漏列。這些不算產品通過，沒有放寬原 candidate assertion 或修改 v6 freeze。

### 真程序結果

固定 v6 manifest SHA `5adf6bcf2c9166e9f5e18d0f2247ee96f3ce5c0178fe0af5b588dd9c1f37099e`；root08 runner SHA `d1f0b3bddd7fdc0d615e3be410f04f1c5f94c1cf0cb8d89108c76dc601cb3f35`。

- 聚焦：**3 PASS／2 deselected／14.56秒／native0**。成功選擇保存、保存失敗保留舊選擇、真 TaskWorker 五代 A→B→A、stale不保存、cancel與close owner保留直到matching native finish／registry排空。四個 actual PID、完整第一方 origin clean、pins起訖相同、pycache空。收據 `health_v6_focused_9428a9b8899c4f63a2a9962529a17a44/receipt.json` SHA `5def740b6d83e442cf36f01abb0ea41037ebe72339a2778d5002203ffb4a811d`；外 Job SHA `a152b6605d85c0dd810f6ada269745d3580be5582dcfcd1b11a2c24668377356`，剩餘0、未強制回收。
- 全組：**4 PASS／1 FAIL／23.65秒／native1**。另取得 panel lifecycle 通過；writer 階段被 F12 canonical SQLite URI guard 拒絕，daily-refresh blocked／PermissionError。尚未進入完整 Main返回與fresh PID reopen。六個 actual PID、origin clean、pins相同、pycache空；收據 `health_v6_full_a1cd730557e04663a4e5be2e184ca61a/receipt.json` SHA `caaaa76ac0ddcb178dd9ecac533635685deab5c1b5e98b78ab2dbac8283411db`；外 Job SHA `d4c4870b27282f6060c07595d6e3f8fd0fe36c5b1022269c6c9463726ca51a83`，剩餘0、未強制回收。

兩輪都有 F12 helper 預先導入而無法 pytest assertion rewrite 的 warning；原 child assertion照常執行，沒有隱藏 warning。結果不相加。接續先診斷 writer URI 原始值、canonical reconstruction 與 callsite，保留護欄；再完成 Main、fresh PID及正式 UI／型態驗收。P01 v11 靜態續辦；P08 v30 目錄內 manifest／README 仍指 v29，暫停前未完成封裝，不可當成已交付候選執行。

### 保存與回滾

五份共用文件前像、20組原始收據／日誌、parent/child origin、傳遞程式與工具先保存到本輪 `resume_resource_focus_handoff_*` packet。Rollback只在 after bytes相同時逐檔還原保存前像；若後續有人改動，人工合併本輪新增段落，不用整檔 git restore。只有 QA 工具及文件異動；正式產品、Manual 操作與架構不變。

## 最新接續：Health v6 靜態通過與父程序閉包拒絕；P01 v10 預檢原文比較失敗

上一輪為狀態查詢，分類 no progress。本輪取得原方法、完整差異與真程序拒絕證據，改變接續動作，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 仍保留，沒有新增完整工作包或 Gate 接受。

### Health v6：正常選擇提交與 bootstrap

Root 先前以 v5 原函式 AST 建構 bootstrap 重現 `NameError: _health_json`：六處外層 f-string 插值引用只有子程序字串內才定義的 alias。原證據 `health_v5_bootstrap_probe_3e6a550c865743209077b716cd7f03b3/receipt.json` SHA `74f1e1d6229785948bfd32acc540dac6448f69e8d6e5eb5ecc74d4e9bc1dd423` 保留；host 只構字串，未啟動 child／Qt／產品。

v6 manifest SHA `5adf6bcf2c9166e9f5e18d0f2247ee96f3ce5c0178fe0af5b588dd9c1f37099e`。Root **617 unique pins／716 checks**、31候選／25正式前像、10 target 含4新檔的 full patch 與僅 panel／candidate test 兩 target 的 v5→v6 delta 全 hunk 重建。58個原 outer AST assert 保留，新增16個 outer assert；既有測試函式（含原 child scripts）AST相同，僅 bootstrap 六處 json.dumps 與 stage prefix 的兩新鍵窄改。原 `_on_finished` AST 五案證明 current open_candidate 先解包再保存與呈現、open_saved 不再保存、stale／closing 不保存、保存失敗不覆寫原選擇。bootstrap 19440字元成功建構與 AST parse；未執行 child 字串。靜態收據 `health_v6_static_aedda8c0ca0a4115b53dd4de4ca30cb3/receipt.json` SHA `4526c557627fd37e545f4f782d7b5949e2db7adb76278fd0ef6bcf89c80e3cc3`。

Root 新增完整第一方 Python audit exec／sys.modules 來源核驗後啟動聚焦候選，actual parent PID55588，native1、來源起訖相同。parent 導入正式 F12 test helper 時，其 `app_module.personal_watchlist_service.py` 不在候選509靜態閉包內，guard 拒絕；沒有進入三項 test body、沒有取得成功 UI 或真 TaskWorker 證據。原始 stdout／stderr／parent-origins 與收據 `health_v6_focused_19cf99d628424edf8c7617d73f3d0200/receipt.json` SHA `0cd62c7b27a9449a36797fe9f75893ae79125899a7f0b0977d59b3992b01e1b6` 保留；不能推論產品缺陷。Owner 另建 parent pytest/F12 helper 全遞迴 AST closure artifact，v6不動；不逐檔猜補、不放寬 guard。這次 guard 範圍是所有實際第一方 repository Python，未宣稱外部 Qt binary 完整核驗。

### P01 v10：sidecar 已修，預檢自身的片語守衛仍錯

Root核 **594 pins／1057 checks／78 indexed files／380 closure**；8段 full diff 全 hunk 重建，git文字差異明示 CRLF→LF、raw bytes另由SHA固定。query／完整query test／bridge byte與AST沿v9；80 formal sources、原 fixed inputs／protocol／semantic oracle 完全相等。預檢與supervisor sidecar常數指向實際 `.json.sha256`。靜態收據 `p01_v10_static_a2ba79927efa4c4c8c0f091363da04c3/receipt.json` SHA `b22a77016c1028c08716f89816ee4384064c505e73dcf967ec22710b72ce5b04`。

真正 pure preflight actual PID7712／native1／來源起訖相同，line144要求 literal `full DTO` 存在於 `semantic_oracle.all_pages`，但原各版都使用 `each role uses real View next-button TaskWorker path for all 20 pages and compares each complete DTO to serial fallback before warm samples`；`full nested equality` 是另一 equality欄。這是預檢比較原文錯置，不是已證明的 protocol drift。收據 `p01_v10_preflight_682f8f7d129248aabf8a4aa0d29c3616/receipt.json` SHA `1d57b5c710f520d10c3189dc137eed1d3539d2a8690f06cbaa0ccf72cd125b52`。保留v10，v11窄修精確 metadata 驗證並先逐行審核剩餘preflight／supervisor／probe；origin與matrix未釋。原5 cold＋1 warm、1000列／20頁、每操作30樣本／600秒與strict<300ms全部保持；最後有效filter446.3604ms仍未達標。

### 接續、Coverage 與保存

P08 owner 靜態發現 observation projection 仍遞迴剔除 nested同名欄位，另建 sibling 做已核 envelope 淺層剔除並保留 nested負例；尚未由root驗收。不改來源 expiry／available/captured／cache SHA/path／date/status 守衛。

Raw與四文件前像先保存 `output/qa/baldr_completion_20261011/root/health_v6_p01_v10_handoff_59a3b850029a4fbba2e795509000c965`。本輪正式產品、原資料、Manual操作及架構未改，Coverage只需Snapshot、具名QA、shared state與handoff四檔；rollback僅在本輪after bytes相同時還原保存前像，不覆寫後續他人變更。所有root程序terminal，完整goal仍active。

## 最新接續：公開日曆同源雜湊差異核實；Health v5 正常開啟阻擋

本輪完成公開日曆runtime核實與Health全文patch/原AST診斷，取得改變下一步的證據，分類progress。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4保留；沒有完整工作包或產品Gate接受。

### P08 Calendar v5 觀測封套

Root以fixture05保存的calendar/cache與DB原件為唯讀來源，先複製到新私人根，再沿真正 `OfficialTradingCalendar.read_operation(allow_online_probe=False).evidence_for(2026-10-07)` 做兩次live讀取，socket連線／DNS audit拒絕；未改歷史clock或正式source。兩次來源cache/path/hash/available_at/captured_at/expires_at/status/date完整相同，原candidate `_stable_calendar_projection` 已去validated_at，但仍含不同 `calendar_observation.effective_at`，因此原hash不同；僅去該觀測封套後完整dict相等。

診斷收據 `p08_calendar_observation_probe_deed93205e704f5a8c5071ba46b75478/receipt.json` SHA `0c0a18a949a4d1ca48799c5f7dd1fc5da619d319e586ad04dbde2f04fcc57167`，native0／actual PID 28752／source guard clean／502pins相同。原fixture與兩私人副本起訖bytes相同、fresh pycache空。這是公開reader與原helper的根因證據，不是修正接受或策略生命週期驗收。原owner v28需區分不可變source hash與operation observation，保留expiry、來源時鐘、cache SHA/path、日期/status及因果守衛；projection語意變更須明示版本與舊版拒絕/decoder，不能靜默重解釋原v3 artifact。

### Health v5 全文與正常開啟拒絕

Manifest SHA `54e13cd530b07682cae2f5815dcd2c68289dc6ceb64cef04011aee778ec66e61`。Root **609 unique pins／707 checks／592 role entries**，31候選與25current正式前像相同；964022-byte full patch **10targets含4new** 及v4→v5 **2targets** 所有hunk逐行重建。其餘候選bytes沿v4，不把既有風險導覽或靜態清冊當runtime證明。

`PositionHealthSavedPanel._on_finished` 第243行對open_candidate在解包 `opened,record=value` 之前呼叫 `selection_store.save(record)`，record尚未賦值。Root僅抽原函式AST執行最小store/label，實際saved_calls=0，捕獲UnboundLocalError後return；因此正常選擇不能保存/呈現。收據 `health_v5_static_rejected_03c368846b50443888dc08fe5d0d0585/receipt.json` SHA `ead6b82565149d4ba146219d6210fe921f84c80ae73586138dfdbde9e07f730a`。未匯入Qt/專案、未跑Main/完整candidate QA，產品v5拒絕。原owner另建v6 narrow sibling先解包再UI thread commit，維持generation、stale/取消不落盤、open_saved不另保存、原exact bundle及真TaskWorker斷言，並加保存失敗保留原選擇案例。

P01 v9 sidecar缺件拒絕仍有效，v10新sibling待審；原strict<300ms與446.3604ms缺口保持。Raw/helpers/四文件前像先保存 `output/qa/baldr_completion_20261011/root/calendar_probe_health_v5_handoff_6715e63b151b44a3b1b803c7c0679608`；root QA皆terminal，正式產品與原資料未變，完整goal保持active。

## 最新接續：P08 fixture05 日曆一致性失敗；P01 v9 預檢缺件拒絕

上一goal turn主要回答產品狀態，分類no progress。本輪獨立核P01新候選及保存P08新全組終態，證據改變接續動作，分類progress。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4維持，沒有完整工作包或產品Gate接受。

### P08 同版八檔原回歸

Fixture05 manifest SHA `da00bdcbf84f2aa73e24941d8d8a72200fc093aa0d6002a1d2a52bcdcf6b734b`。Root靜態完整重建delta、核14產品namespace正規化bytes仍同v27/04、393原assert完整保留；新public exact reader回讀增加7個DTO／eligibility=false斷言。Static `p08_fixture05_static_38bbbd94ea754525ab3b054a88a420a8/receipt.json` SHA `ba35d6f086af6f56ec00a31d123121ded5f0d56a80d92b129b8ba8060f73e950`。真14origins native0／505pins相同／來源守衛clean；收據SHA `6b88ee37711099743753b3437a04d800c64320d63cb157637a93e28b35df5904`。

八檔全組 **60 PASS／2 FAIL／1 skip／70.63秒／native1**，506pins相同、source guard clean、3 actual PIDs。Suite `p08_fixture05_suite_0c5348c1cb4e48648eb33e8cd2da900e/receipt.json` SHA `1528001babf5190e4d3d8d492c31d55e5fa670de22f1a628d33568161dd01a4d`；stdout/JUnit/actual origins全部保存。兩個失敗是完整MA旅程與public-v5 availability案例，都於intent preflight/current日曆核驗報 `p08_intent_calendar_changed_during_preparation`，未到新增公開reader斷言。不能將此版視為通過，也不能與較早其他版本的通過數相加。

Root靜態定位 `_stable_calendar_projection` 只移除validated_at，Calendar v5 source_evidence新增的calendar_observation內即時clock仍參與hash；KD亦復用此helper。已交原owner新v28 sibling核同operation clock與不可變source projection，來源available/captured/expires/cache SHA/path/status/date及因果檢查保持。另新public fixture的 `_TARGET_READ_CUTOFF` 無定義，這是未執行到的靜態缺口，須用既有checkpoint時鐘補正並保留7斷言。績效草稿的版本契約／有界讀取、完整benchmark及正常UI仍待。

### P01 v9 靜態來源與啟動拒絕

Root核 **512pins／552checks**，75個封套檔案SHA/size一致；380-module closure只重綁五個正式已套依賴。原query/test/bridge bytes與AST相同，外層source/runtime、sealed inputs、normal protocol及完整DTO oracle相同，五cold／一warm、1000×20、三類各30樣本、600秒及strict<300ms門檻保持。

預檢第18行與supervisor第33行精確sidecar常數都指向不存在的 `...20261011.sha256`，實際freeze只保存 `...20261011.json.sha256`。Root在執行前拒絕；static `p01_overlay_v9_static_rejected_492024a2ca364caa9f8712f61f3b8824/receipt.json` SHA `9d5b16e9dc55fbfacdddc4622bc04293ce7706d83624100608a525199c549009`。這輪未跑v9 preflight/origin/matrix，未讀sealed store，也未宣稱全文diff重建。原件保留，原owner另建v10 narrow sibling修正精確檔名與self pins。最新有效filter p95仍446.3604ms，不授P01／300ms Gate。

Health v5 owner自查完整diff漏四個candidate-only new files，原freeze保留，另建完整diff sibling待root審。原正式caller同版322PASS及954檔mypy證據維持；這輪沒有套正式產品或改正式資料。四文件前像、來源收據與helpers先保存於 `output/qa/baldr_completion_20261011/root/p08_fixture05_p01_v9_handoff_e45d69a21ff0447ab89f9143b1e16b50`，完整goal維持active。

## 最新接續：正常持倉日曆預設 clock 修正及同版驗證完成

上一 goal turn 回答狀態，分類 no progress；本輪完成八模組型態來源核驗與原回歸接續，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包或產品 Gate 結案。

### 正式 caller 與原斷言

Root已完整審caller四檔diff與所有原測試AST。`PortfolioService`保留ledger預設now provider，但cadence只收到caller明示provider；widget沒有明示clock時以live日曆核驗，不從service.now猜歷史模式。明示historical clock仍要求aware／不晚於現在，不授PIT；custom cadence identity優先。原金融函式未改、沒有新增裸float，日曆只核決策時可得觀測。Apply收據SHA `021d60e457a046540cd7316ce2604cd1a7a1c77221a572b0ab64b22967375783`及四前像保留。

首輪23檔320 PASS／2 FAIL／2 skip：兩個新widget fixture缺output_root，未到clock斷言。Root只補新fixture路徑，所有原斷言AST相同；產品未為fixture放寬。首輪、fixture apply與第二輪raw均保存。

正式23檔 **322 PASS／0 FAIL／2環境skip**；兩skip仍是無symlink權限，未宣稱平台負例已驗。原工作台 **85 PASS**、原validator **25 PASS／4 skip**、私人 **13檔語法通過**。第二輪收據 `calendar_callers_formal_60c43a88e2fd4d088193ab40835f81e1/receipt.json` SHA `4ce3cffc674ca8ad6fd3c374be1fa02227fe9c5fd0aeec6836ea963fad12ef3c`，各上述stage actual origins clean、起訖1453pins相同。第二輪總native125是型態stage來源守衛拒絕，不能改寫為總native0。

### 型態與Qt來源證據

正常原mypy.ini／follow-imports／explicit-package-bases／no-fast-exit之八模組 **954檔0 issues**。舊守衛的Qt原生內嵌signature_bootstrap raw marshal雜湊在完整code欄位讀取前後不同；舊政策與兩次來源拒絕保留，不以不存在的repo檔案補白名單。新獨立reference政策核相同七原生runtime SHA、26精確虛擬名稱及13 ZIP成員；九函式所有執行／traceback code欄位、巢狀code與typed constants逐值保存。另在同一型態PID起訖要求相同module／loader／importer class／九函式與不可變code物件。初末完整欄位相同，任何未知／缺失來源仍拒絕。

獨立types-only收據 `calendar_callers_types_fields_f3830bddc3884274b0476b9c101e5f0e/receipt.json` SHA `88a0ffb81fd54412c742f8d4a0f66a2e33fde2ace11297180b6cdc74bf9d718f`：actual PID 11672、native0、來源守衛clean、1456pins相同、fresh pycache空。此收據未重跑23檔；與第二輪來源hash逐項同版比對後接受本切片的回歸／UI強制命令／型態與語法，不累加舊測試，不授全部巢狀PID或程序樹資源接受。

### 仍開放

Health正常Main封存選取、真TaskWorker取消／重選／close與exact bundle反例由既有owner準備v5；P08 fixture04實際raw helper並非public reader已核實，05另加7公開DTO／qualification斷言待root全組；績效03草稿以未接受04為基準並明示9條unresolved import，未授來源或績效接受。P01 v9重綁五已整合依賴，完整矩陣待審；最後有效filter p95仍446.3604ms，原strict<300ms門檻不變。

Raw、helpers、正式來源副本及七文件前像先保存。同步入口、clock語意、限制與排錯；原始行情、Task、模型、交易、main/push/release未變。完整goal保持active。

## 最新接續：日曆正式整合廣回歸通過；P08 八檔仍有兩個 fixture 失敗

上一 goal turn 僅回答狀態，分類 no progress；本輪完成正式日曆／Health 二十檔原回歸與正常型態／語法，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包或產品 Gate 接受。

### 日曆 v5：已套正式來源並完成同版廣回歸

Root 先核十一個目前 formal preimages 與 v5 bytes、原候選四階段收據，再套五產品與五測試；另一 cadence 測試相同未改。全部正式前像與 candidate manifest/full/delta 已保存。Apply `root/calendar_v5_formal_apply_9b7f2f1d971348e5856d021376c6f3fd/receipt.json` SHA `5c5f409de527c282912494e1d773c8e8970b5d7e25d63859b99b600047492d15`；其 `formal_QA_executed=false` 是套用當時事實，不改原收據，由本輪新 QA 證明後續狀態。

首個 formal runner 原二十檔 **264 PASS／25 FAIL／1 skip／29.15秒／native1**：25失敗全是 QA write guard，包含 Windows `\\?\` extended path 的同一私人路徑與原 `workspace_qa_tmp` 新 UUID fixture 被誤拒絕；另265 actual origins未列，包含真 Main 來源及26 Qt 內嵌虛擬來源。九來源正常 mypy／十四檔語法通過，902pins起訖相同。原收據 `root/calendar_health_formal_f82fcde9391b4a0aadb6d18fe4f0242d/receipt.json` SHA `a5861400247aa9dada0114dc1eee0d5280676ebb8dd066b9e56b573b9a5d3fab` 保留，不能授產品失敗或通過。Root02／03各於 QA 前發現 signature_bootstrap 虛擬路徑而停止，未改原件或產品。

Root04 從二十檔、正常 conftest/plugins、Main 靜態 import 與首輪 actual來源重建825 source／3271邊。只允原 fixture 當次新建且不存在的八個 `pytest_health_<32hex>` 子根；extended path 先解為真路徑再核私人根。Qt26虛擬名稱另以七原生 runtime pins、13實際 embedded ZIP 成員 SHA、loader identity與bootstrap code hashes核驗，不跳過未知或缺失 repo 檔。四個直接 QA 子程序實際載入來源均通過，1206pins相同、fresh pycache根空。

正式來源廣回歸 **288 PASS／0 FAIL／2 skip／34.17秒／native0**；JUnit290案例、time34.127秒，兩skip均為環境無法建立symlink，不宣稱已驗兩個平台負例。正常原mypy.ini／正常follow-imports／explicit-package-bases／no-fast-exit：**0 issues／9 sources／native0**；私人目的地 **14檔語法通過**。Actual Python PID依序57332(origin)、9344(pytest)、59704(types)、34736(syntax)，不以venv wrapper PID代替。Receipt `root/calendar_health_formal_3c6c2c0967904ad6bf73e00b503b1d26/receipt.json` SHA `0558cf220553d198102580ed917e02cd64d5c296b06543fc019cae5977e3c934`。這是正式日曆及既有 Health 同版廣回歸；不與先前候選96或Health214累加，不授巢狀PID／完整Windows程序樹／整體UI接受。

日曆 API 明示 `live_now` 與 `historical_as_of`；同一read operation一次capture，跨日／年度與expiry共用相同觀測。歷史clock不授PIT或目前freshness。最新 caller audit發現 `PortfolioService` 將預設 now lambda無條件傳cadence.clock，聲明持倉widget同樣傳預設service.now，會錯標historical；交原P01 owner新scratch修正，尚未套正式。正常Health封存選取UI、策略EOD adapter與完整P06／M3仍待。

### P08 composition02：重新審觀測版本後八檔取得失敗證據

原交付manifest `f2c8c11d…` 在交付後被owner改寫，未保留原bytes，root拒絕以原freeze宣稱只改README。Owner停止寫02後，root完整重審實際觀測manifest `28a01b0f31c2a378a0031ac11ebd2f251b6355cc887cd8b01cd4c220e497007e`，另封存全部observed files／provenance gap。完整46069-byte delta重建、1468pins／419modules／393asserts／19target cases核驗；14產品只對v27重綁namespace，六fixture改用public cash seed／daily checkpoint／typed prior，原負例與exact error equality保留。Static `root/p08_prior_composition02_static_a42ef158abf24e43b521820e5a21bc46/receipt.json` SHA `26c4aed044e1e39470e068b4aa5c39f85b7087acf50d67ba954b0f659b34f590`；不能補回原f2c freeze缺失證明。

十四actual origins通過；八檔 **60 PASS／2 FAIL／1 skip／52.83秒／native1**，1476pins起訖相同、4 actual PIDs source guard clean。Receipt `root/p08_p08_type_candidate_20261011_v27_prior_fixture_02_suite_3dab2f18cbc44d50ad2ccff7e09dba6a/receipt.json` SHA `a37c4ab00e19b91b38088ce2267843617341234d4ae32603da89541067457752`。一案舊positive receipt helper不符合v5完整fields；另一案tampered fill只有source_type，太早被symbol格式守衛拒絕，未到原fill-hash錯誤。交原owner另建public v5 writer/readback fixture並從真fill改有效欄位；保持原assert／hash qualification拒絕。03又有source-base metadata誤指direct parent，未QA；新04 fixture-only已交root待審，另以接受後同版接performance，不授02／03或完整P08／M3接受。

### Coverage、保存與接續

Root正式QA全部terminal，session66367／50002均已消費。保存formal apply／首輪與通過QA／P08 static與suite全raw、Qt embedded來源、正式QA來源副本及六文件before；同步Snapshot、本QA、架構、Manual與本機shared state／handoff。方向與入口不改，完整原計畫保持；原始行情、main／push／release／Task／模型／交易未改。三個既有Luna Max續推default caller修正、Health新formal freeze、P08 fixtures及績效；P01 v8來源probe／cold-warm矩陣待root審查，篩選446.3604ms／strict<300ms缺口不變。

## 最新接續：日曆 v5 全組與型態通過，P01 query 來源證明仍待

上一 goal turn 只回覆產品進度，分類 no progress。本輪接續已凍結候選完成日曆正常型態驗證，重核上輪 query／日曆終態並保存原收據；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包接受。

日曆 v5 manifest `8d5ce5a038f9bb5088926988d229c99043cce3e621ed2f923403878d4b7653c5`；root 靜態核623 pins／509 modules／592祖先／1736import邊，87427-byte full.diff及42219-byte v4增量全文重建，279原assert AST保留。產品只補六slot型態與LockType，移除annotations後與v4 runtime AST相等；三fixture保持原日期及count，沿真public writer補parent與跨年cache。Static receipt SHA `a327b06b53155961b84744710c98c7ef334ca73221835f872b3939b288a345ed`。

Fresh origin五產品 native0／actual PID54684／629pins相同，收據SHA `8efc5af478c8a7b3bcad128f38ede46bb91918d93c9d3dc20e360866374facd8`。六檔 **96 PASS／0 FAIL／0 skip／6.34秒／native0**，actual PID26268／635pins相同，收據 `root/calendar_v5_calendar_fa0e377779654df5a8c40775e425ccca/receipt.json` SHA `923addc50062e707aa819ae6864004bb9f14a7c838bddb1b73cc3e1a62ca1ed3`。正常mypy原mypy.ini／explicit-package-bases／正常follow-imports，**0 issues／5 sources／native0／13.938秒**，actual PID54692／635pins相同，收據 `root/calendar_v5_types_6bad79186a1748b887e775252a4aeaa4/receipt.json` SHA `6d06abf14e19d016574bfed077511920ea55434e1783ed7133b8a2bf49cf3a17`。三階段actual source guard clean、fresh bytecode根空；接受此同版來源／日曆回歸及型態切片，正式整合、正常UI與完整P06／M3仍待。Popen封套不授完整程序樹接受。

P01 v7完整query **25 PASS／573.37秒**，但child／launcher／root **native1**：`p01_child_fresh_subprocess_candidate_import_not_observed`，不能接受完整query來源證明。Root receipt `root/p01_rolling_v7_query_a2931ab7e7b84226bd2ea10b9c0d12e7/receipt.json` SHA `158f9d3e0139d665087c6e2a1cbd9fd8f7ac90f70585de41392e65501c41f816`；2185pins相同。原fresh-reopen測試的文字結果通過，但缺新PID候選載入事件；已交原owner新sibling查bootstrap，保留原assert及跨PID/hash拒絕守衛。原query未失敗不蓋掉來源核驗失敗；完整cold/warm與原篩選446.3604ms／strict<300ms仍待。

P08 prior composition01因整檔替換遺失v27 availability負例拒絕：root69pins、原389→392assert不能證原負例保留，收據SHA `0fa531d47af26c450b997e7b63c3dcda163edbfbdd7d51ded982fcaf98cfe669`。新composition02以v27為基底，只移植六指定prior測試與必要helper，待root全審／QA。另root AST核兩份legacy v2公開provenance reader：18個SQL metadata位置只核前16個，payload index16未預檢且上限錯套index14；3pins／2觀察收據SHA `79071b9381de4c48375f2348e644d94e28d966be47ff76d5f095e8023438d22a`。此為靜態缺口，沒有runtime race結論；新同版績效候選補reader與鎖內writer預檢，v2/v3版本及原證據保持。

所有root QA已terminal，session98502已消費exit0。四文件before及raw先保存；本輪只同步Snapshot／本QA／本機shared state／handoff。產品操作、Manual／架構／Roadmap／Index入口與原始資料未變，未套正式日曆。Health UI v2由原owner做逐函式三方整合；P01真新程序／矩陣與P08同版prior／績效持續推進。


## 最新接續：P01 v7 真程序與來源十四契約通過

本輪接續P08 v27後完成P01 v7獨立審查、唯讀預檢與真Win32 Job契約；全部root QA自然terminal。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4保持，沒有完整P01或產品Gate接受。

Manifest `54b66e91665f975a56a1803cf38eaaefb6e50df6213dd91c1fe65fa655a3ebbb`。Root **2181pins／4277checks／380repo modules／1666external files（1675 module names／140681548bytes）**，49825-byte complete diff及三support deltas全文重建相符。原query／test bytes、runtime來源、閉包、五cold／一warm、1000×20、三類各30樣本、600秒及strict<300ms門檻保持；八程序案例原88assert AST相同，六origin負例bytes不變。Static `root/p01_rolling_v7_static_0dad268288e341e88a4837e0d85d0bea/receipt.json` SHA `ccc01e98ca287f8f7908d888644dff10567ba96535825b1bb86822b003edaf59`。

Host preflight **native0／2183pins相同／source_store_access false**；`root/p01_rolling_v7_preflight_1271d020dacc43f0aab8fbcdd96bfb14/receipt.json` SHA `8c4a1968f7aac1661e651af0e5f9e6693ae48da7d3a9cf61fafec3ca88aec8ad`。十四原契約 **14 PASS／6.89秒／native0**，2184pins相同；`root/p01_rolling_v7_contracts_89a0feaff00c41de8bf547c635ce3ae1/receipt.json` SHA `1e51a10973d4bd2caf85bcbeb30ec1d5a02c3d69688b996fa70af01798e1c251`。

Root另唯讀核七個_run_child完整結果及retained stdout/stderr的SHA／bytes。短命descendant自然排空；長命descendant在自然期限後保留 `job_child_processes_remained_after_natural_drain` 原failure，再由同一Job終止，conhost／base Python／venv Python三個member實際signal／exited125、query handles closed、Job0／PID[]。既有parent return0不蓋掉residual-child failure。原v6 state running失敗保留；v7以保留handle的共享monotonic deadline實際等待，不由Job空推定exited。

以上接受此十四定向契約；原query全檔與完整cold/warm矩陣未跑，無新p95。原篩選446.3604ms／strict<300ms缺口仍在，不能以監督器修正或十四PASS授效能／正式整合接受。七完整raw與index、三root封套、manifest／diff／helpers及四docs前像先保存；只追加Snapshot／本QA及本機shared state／handoff。正常UI、正式產品／原始資料、Manual／Roadmap／架構未變。

接續：v27 true-prior同版composition已交root待審，performance正在完整同版重綁；P01 owner續做Calendar v5三fixture／14slot typing修正，Health UI v2仍施工。root下一步完整組合審查與原query回歸；所有目標保持進行中。


## 最新接續：P08 typed v27 同版正常型態與完整 MA／KD 旅程通過

本輪在日曆 v4 終態後串行核 v27，所有 root QA 已自然 terminal，session89967與4933均已消費native0；沒有 live root handle。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

Owner manifest `7b254c9f6c63be7a9ec9c06fe8512945f4e4d9000a8ecb681c3a5d26c0953b3f`。Root獨立 **1389pins／2095checks／418modules／22mapping／389原assert**，全文full/type/incremental三diff重建。原v26到v27只有MA與KD allocation local由quantity改constructed_quantity；逐完整module AST只還原該Name後與v26相等，原金融計算、None／exact-int／股數／整張與target寫入守衛保持。首個root重建器把incremental header／順序設錯而停止，保留root03，root04按實際header／順序重建相同；沒有修改候選bytes。Static `root/p08_type_v27_static_5d925710822749f8ae38882f54fb9d25/receipt.json` SHA `6442a58cc4a6ef38bda9e598ee85e006f5d48c7a893db7ac8b5384e678b64072`。

Fresh origin **14產品／native0**，1396pins相同、1 actual PID、guard clean；`root/p08_p08_type_candidate_20261011_v27_01_origin_7530c1b41cde4623b888d7cb42d829f1/receipt.json` SHA `43f02dc2b16b3b981acc0e3205ffe1bd078afc79e75b2df21ede38d2685879d1`。正常mypy原mypy.ini、explicit-package-bases、正常follow-imports：**0 issues／14 source files／native0**，1397pins相同、actual guard clean、fresh bytecode根空；`root/p08_p08_type_candidate_20261011_v27_01_types_cef1da74f03a41daacb6a4aa18284c68/receipt.json` SHA `128881a207d407608337dcbeb8a9d0e21ab39cfeb7f3e4a9acbf4762bafbc78f`。

同版原完整MA／KD節點 **1 PASS／0 FAIL／74.22秒／native0**，1397pins相同，7 actual PIDs來源乾淨。涵蓋真public source→intent→共享金融引擎→daily/checkpoint、已消費seed／歷史prior、新PID讀回、兩家族進場與賣出、blocked／UNKNOWN零成交及空倉日；行情與訊號仍是具名合成fixture，不授真市場PIT、官方event或交易／績效資格。`root/p08_p08_type_candidate_20261011_v27_01_integration_ccf746eb283c4092bb51a87304f1b931/receipt.json` SHA `6a38710418e94f4c375e547961f1d61960f84838dec51e1ac950d0a614a90f0c`。

接受本v27的十四來源正常型態與這條原完整旅程；不是八檔全組或完整P08／M3接受。另一owner已接v27同版public-prior fixture composition，再將performance修正完整同版重綁；MA/KD與舊receipt原exact assertions保持。績效、benchmark、正常UI、原來源、同版EXE／Native／真人及完整交付Gate仍待；原v26／所有失敗封套保留，未套正式來源。

本輪只追加Snapshot／本QA及本機shared state／handoff，四文件before與全部raw先保存。Manual／Roadmap／架構契約未變，正式產品及原始資料未改；Popen封套不授完整Windows程序樹資源驗收。後續依同版本完整組合與原驗收門檻推進。


## 最新接續：日曆 v4 真來源通過，六檔回歸與正常型態缺口已定位

上一 goal turn 只回覆補完進度，分類 no progress。本輪完成靜態閉包與真來源核驗、六檔完整回歸及五來源正常 mypy，取得可改變下一版動作的原始證據，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持；沒有新增完整工作包接受。

Calendar v4 manifest SHA `c58af21bff2531fcf9d40648ac708d1859919b4e7c9ad82f73202db17784bbce`。Root 獨立核 **574 pins／509 modules／592祖先 initializer／1736具名import邊**；原十一份 candidate／preimage bytes、488列舊閉包不變，新增21來源。86757-byte full.diff與37535-byte v3→v4增量全文重建相符，bridge完整讀核。Static receipt `root/calendar_v4_static_review_a6abc008483749418baf58cf081f3b98/receipt.json` SHA `8bb16466bd41ac5da6c3309c84c6243629e7fe52d3a3f8df31c73701be8332d8`。

Fresh host origin **native0／2.141秒**，五個candidate產品皆來自exact v4來源；576pins相同、actual PID2448、guard clean、fresh bytecode根空。Receipt `root/calendar_v4_origin_d150f6a95a1f4d7b9874092c0209dcaf/receipt.json` SHA `fa82e2e706fabe6ec47dfdd7cdd832fded1c51e91c2625c4357bc95c49b1f502`。不以wrapper PID6500代替actual Python PID。

Root runner前兩次QA終態因 Windows nul裝置被root外根寫入守衛誤判；分別native3／native1，兩份未完成JUnit保存，不當產品測試結果。Root03明示私人pytest log，只辨識exact `os.devnull` Windows裝置；candidate產品／測試及外根檔案限制未放寬。六檔96項回歸 **93 PASS／3 FAIL／0 skip／JUnit5.459秒**；controller8.578秒、native1、583pins相同、actual PID40400、guard clean。Receipt `root/calendar_v4_calendar_961a12fef2bb48d7a08abdb6dccdbdaf/receipt.json` SHA `4e4d9b805d969ea04ae1a13152796b69a0aa5c898d85ebac1c0bc9d2ef09760f`。

三失敗都位於新增calendar cache fixtures：兩temporary-closure案例在public writer前沒有建立要求存在的parent；單clock五日查詢從2026-01-05跨到2025-12-31，但只有2026annual cache，因此原unknown守衛拒絕。已交原owner另建v5：補私人parent（missing-negative案保留先讀missing順序），保留原reference/count與全部assert，真public builder/writer補2025年度並沿同directory定位；不mock整個calendar或把未知當開市。

正常mypy沿原mypy.ini、explicit-package-bases及正常follow-imports，五來源 **14 errors／1 file／native1／14.141秒**；587pins相同、actual PID33456、guard clean、fresh bytecode根空。全數為CalendarObservation六private slot欄位經object.__setattr__建構卻缺型態宣告；v5補明確str／datetime／bool／真LockType annotations，保留slots、不可變守衛、issuance與單次claim，不新增ignore／Any／cast。Receipt `root/calendar_v4_types_d572041fdb6940be8750a40e95cb2327/receipt.json` SHA `ea0e0f8591b5783b990abada264b14c3dadae2a552352d772720f82d472b82cc`。

Root全部QA terminal，原session97370已消費exit1。原件／stdout／stderr／JUnit／actual origins／pins與helpers先保存，再追加Snapshot、本QA及本機shared state／handoff。正式產品／原始資料未改；Manual、Roadmap、架構政策未變。日曆完整回歸／型態與正式整合未接受；P01 v7、typed v27、Health UI v2及同版prior／performance接續。此Popen封套不授Windows完整程序樹資源接受。


## 最新接續：績效來源定位器的公開 publisher 契約拒絕

Root全文讀33972-byte price locator並核目前正式publisher：公開descriptor的SHA為 `sha256:`＋64hex，content-addressed路徑是2hex shard＋64hex filename。候選 `_HASH_RE` 卻僅認裸64hex，並用於prefixed SHA及2hex shard；exact reader甚至同時要求shard64hex與等於filename前2字，條件互斥。

原publisher line886路徑expression與候選初始guard AST四案核實：合法prefixed SHA先回 `price_locator_pinned_descriptor_identity_invalid`，去掉prefix後同一合法path仍回 `price_locator_pinned_descriptor_path_invalid`；`_find_candidates`／`_enumerate_publications` 的原prefix.name guard皆拒絕2hex目錄。14pins相同；原收據 `output/qa/baldr_completion_20261011/root/p08_locator_contract_d78478a401ff48558a0fdd0de3cf7734/receipt.json` SHA `79f79dceabd60169fae5c5c687b84ba3ab31b797ca9f92f69df3152478746b95`。只隔離原初始守衛並stub request validation，沒有完整writer／locator、產品imports或市場／帳本讀取；不授完整price／benchmark接受。

已交原P08 owner新performance sibling，分開prefixed contenthash／裸64hex filename／2hex shard三個明示patterns，完整保留root／containment／shard／filename／內容hash、公開row reader與雙projection hashes；不跑已知失敗v6或放寬來源。等typed v27時先獨立準備weekend／bounded writer／locator修正初稿，再完整同版重綁；fixture組合優先。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍待；正式產品、原始資料、Manual、Roadmap與架構未改。


## 最新接續：績效 v6 週末日曆分支核實

完整scope保持。本輪續讀完整EOD series reader與metrics producer／reader，並讀benchmark v3的prefix writer／reader、baseline／calendar／close policy／manifest／persist核心；不宣稱136269-byte整份v3或完整benchmark／ResearchRun接受。

Root在兩份凍結benchmark的 `_read_calendar_window` 核到：weekend convention證據沒有official clock/hash，卻沿相同官方來源驗證降為unknown。抽取原AST函式、以合成工作日完整clock/hash作分支輸入，2026-10-10週末兩份均回 `calendar_evidence_clock_or_source_hash_missing`；v3 2026-09-05至10-06窗口工作日皆open、週末皆unknown，`_v3_baseline_date`精確回 `benchmark_v3_baseline_calendar_unknown`。這是原純函式分支證據，沒有產品imports／市場／帳本讀取或完整性能QA。13pins起訖相同；原收據 `output/qa/baldr_completion_20261011/root/p08_performance_weekend_ad9743f80f2e4b1bbacfd858a7b5869f/receipt.json` SHA `613b62dbd5103ee0b081abf7c8125543c19c99038c67346999504ae733a7a72c`。

Owner已授新performance sibling：週末closed慣例與工作日official evidence分開，不虛造週末clock/hash；缺工作日來源仍unknown、baseline只取真open，補真public calendar cache案例。另靜態讀到v3writer在BEGIN IMMEDIATE內SELECT既有provenance_json／manifest_json／clock無SQL type/byte預檢，先前readonly有界預檢不能證跨交易窗口不變；未runtime重現race，鎖內有界讀取需補。原v6及v2/v3日期／路由／資格界線保持，不改金融計算或放寬因果守衛。

本輪原始證據與四文件前像create-only保存；coverage只追加Snapshot／本QA／local shared state與handoff，正式產品、Manual、Roadmap、架構及原始資料未改。Typed v27待freeze；fixture同版組合與performance修正由原owner續行，沒有live root QA handle或完整Gate接受。


## 最新接續：P01 v6 真契約與 P08 v26 正常型態終態

上一 goal turn 只回覆剩餘範圍，分類 no progress；本輪取得新實際來源與真程序契約／正常型態結果，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保留，沒有新增完整工作包或 Gate 接受。

### P01 v6：來源與預檢通過，程序最終狀態仍失敗

Manifest SHA `b084e7d6ef00591e9e94da27bb771be5519d465b9a7d7c771e9d5d3b26d9cf3e`。Root 2130 pins／2551 checks、380 repo modules與1666外部檔（1675 module names／140681548 bytes）核對相同；四個先前真repo漏列已補，原376項不變。67075-byte完整產品／三support diff全文重建；query及原tests逐byte等同v5，五cold／一warm、1000列20頁、每類30samples、600秒、strict p95<300ms未變。Static `output/qa/baldr_completion_20261011/root/p01_rolling_v6_static_05e093b1415747689f8eae1604a83e37/receipt.json`，SHA `d97332d32f62c545b63987ce4eb0a9ad4c07b9829f6953064cc00ec1e4e0ed88`。

Host唯讀預檢 native0／2132 pins，source/store access=false。十四契約 **13 PASS／1 FAIL／6.81秒／native1**，2133 pins起訖相同。長命descendant的Job active0、PID清單空、owned handles closed及獨立process signaled檢查均通過，但保存member state仍running，原line305拒絕；不能憑Job accounting空推定retained process handle已signaled。收據 `output/qa/baldr_completion_20261011/root/p01_rolling_v6_contracts_d92a45395c6c4978990264827ce9edaa/receipt.json`，SHA `09e4f7c5496cd8259c6e87a9ad81d2da3bdaecb6e6fccb920a00b529e24d982b`。完整query／matrix未釋出；owner保留v6，另v7使用共同有界deadline等member handles、讀實際exit code並保存raw result；不改原assert或吞cleanup失敗。原篩選446.3604ms／300ms門檻保持。

### P08 typed v26：實際匯入通過，型態剩兩個局部名稱衝突

Manifest SHA `b7cde9efae57205c6ed56f30e6f45a46bf12edd4b480fe5f6f6012a03569b810`。Root1311pins／1856checks、22source/test mappings、418module closure／389原assert相同；完整差異與v24→v26 type diff重建。V25→v26只補兩DTO imports及daily local union annotation，runtime guards與金融邏輯不改。第一個root generic工具錯用v25 type-diff header，QA前assert停止；保留原helper，root02按實際v26 header全文重建，不改candidate。Static `output/qa/baldr_completion_20261011/root/p08_type_v26_static_8afc187ef9a44603b7ce2d737ea7aa70/receipt.json`，SHA `9ab30b42de7d08e6fe1b9ce65c2bf48be691351705b86ccb81e426cea2f30ebc`。

Fresh interpreter **14 candidate origins／native0**、1318pins相同、一actual PID source guard clean。正常mypy（explicit-package-bases、正常follow-imports、無ignore／Any／cast）**2 errors／2 files／14targets／native1**，1319pins相同、一actual PID clean；較前v24的23errors減少，但未通過。MA executor line615與KD executor line693都把 int|None executable_shares 指派給先前held loop已推int的quantity。收據 `output/qa/baldr_completion_20261011/root/p08_p08_type_candidate_20261011_v26_01_types_08c021622e6040ff889948d04d2ee3af/receipt.json`，SHA `9d6eb0bda1849bcf37af3710cea8aae004de33b12c64ece626d9cd79942edecc`。Owner另v27只拆local名稱，保留guard與assert；真prior fixture等同版v27再compose。沒有跑v26完整旅程／八檔全組或套正式，不累加不同版成功。

### Health UI 與真 prior fixture：先前靜態發現已交修正

Health UI v1 root113pins、九product差異全文重建；new QA test混合newline只能邏輯hunk重建，另raw SHA pin，不宣稱raw全文相等。Panel舊worker native_finished即使不是current仍無條件消費_pending，可能在新worker上啟動另一讀取；已授v2綁worker identity／generation／pending並保持slot至native finish、補stale callback／取消／新選取／close負例。Preference保存與取消一致性續審；主畫面內部hash／receipt英文key改可讀中文並提供展開diagnostics。`output/qa/baldr_completion_20261011/root/health_ui_v1_static_eba1ffe3da124672b19080294a8036a6/receipt.json`，SHA `d650c30a1d3dd58d9351569215e1f56c9a54a3e23bb64a8852f7dbd3de1e98d7`；未QA或套正式。

Prior fixture v25 root1024pins、34309-byte四段patch重建，六target案例19金融assert保持，真public cash seed／daily checkpoint／typed exact prior取代手工字典。MA先前10/01 decision早於10/03 prior availability改10/04，KD仍10/09，保留500000／8 policy與原金融值；fixture仍合成price/signals，不授正式PIT／execution／績效。Root抓到新pytest.raises的未錨定regex弱於舊exact str(error)==，next composition需保留原exact equality。`output/qa/baldr_completion_20261011/root/p08_prior_fixture_v25_static_0358cea2ebfb40f4b875ec39d4763e45/receipt.json`，SHA `25e0ecd1ad7c5d6711c1cb278bccc2d2f66a8a8469d7690a692d16c7a3054634`。

### 保存、Coverage 與接續

本輪root QA全部terminal；保存原始stdout／stderr／JUnit／origin／清冊／diff及四文檔前像。只追加Snapshot／本QA及本機shared state／handoff；正常產品API／UI／Manual／Roadmap／架構未變，原始資料未動。三位原Luna Max續做P01 v7與Calendar v4、typed v27與Health UI v2、真正prior fixture同版組合；績效reader／benchmark／正常UI與全部交付範圍仍待。


## 最新接續：日曆 v3 實際匯入拒絕

前一純狀態回覆分類 no progress；本輪重新核目前 HEAD／來源及原始日曆終態，保存會改變下一版閉包修正的證據。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持開放。

Calendar v3 origin **native1／2.016秒**，527 pins 起訖相同；wrapper PID49584、actual Python PID28912。五產品尚未全部安裝完成，source guard false；38 個已載入來源可核，另有四個真正 repo initializer 未列：app_module/recommendation/__init__.py、data_module/contracts/__init__.py、decision_module/__init__.py、decision_module/recommendation/__init__.py。第三方分類修正尚未完成整個 import closure，不能以 v3 靜態 488 module 清冊授予實際匯入接受。

原收據 `output/qa/baldr_completion_20261011/root/calendar_v3_origin_b3c38f7010be4a928336bcb8bd9922d8/receipt.json` SHA `7ca2a37f1bf92f90d9b4629a261e5f1f817108a3aade841d33db3cd464e67283`；stderr／actual origins／pins／manifest／完整差異／runner 原件已先備份。v3 失敗保存且不重跑；原 owner 另建 v4，補完整 package initializer 與 actual import closure 後重新審查。Focused 五檔 QA、型態與正式整合仍未釋出；沒有 live root QA handle。

本輪 Coverage 只追加 Snapshot、此 QA 與本機 shared state／handoff；正常 API、UI、Manual、Roadmap 及架構契約未變。正式來源／原始資料／main／push／release未改。


## 最新接續：P01 真程序契約／P08 型態同版旅程／日曆審查

上一純狀態回覆為 no progress；本輪完成真子程序與完整旅程驗證，取得改變修正動作的失敗證據，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包或 Gate 接受。

### P01 rolling v5：測試通過、封套失敗，效能仍待

Manifest `94d8960f192ba9952005664639ee4fa26c0676ff67fbe03c15ce7bb3e9fdae91`。Root 核418 pins／429 checks、376 module closure、21626-byte產品diff及v4→v5 launcher全文delta；改用原生CreateProcessW保留hProcess/hThread，先Assign Job再Resume，初始suspend count必須1。只讀預檢native0／420 pins，七個真子程序案例 **7 PASS／1.21秒／native0**、421 pins不變，覆蓋真暫停、Create／Assign／Resume失敗、錯suspend count、逾時及後代回收。收據 `root/p01_rolling_v5_contracts_ad02e2204319479ab02c21d266dde8ad/receipt.json` SHA `9f34c696a9a224b5c997212d658aced8ee40f960d1d7a2062594f5a9276a4d1b`。

同版query全檔 **25 PASS／433.34秒**，但child origin後檢失敗、native1。1679個unlisted origins中1675個是venv第三方，真正repo缺四個：decision_module/__init__.py、decision_module/factors/__init__.py、utils/__init__.py、utils/io_utils.py。不能只跳過venv而漏真閉包。Parent PID37800終止時Job仍有PID8904；未證其是redirector短暫收尾或真正殘留。Job最後Terminate排空0、三handles皆closed、沒有逾時，但cleanup error保留，不能授完整程序資源接受。Root收據 `root/p01_rolling_v5_query_216320d79c204032bcf8b613766028af/receipt.json` SHA `51b74b0c16048787de4ead768a84b494034a4f2eb7f465094d37d1d4d69d7796`，422 pins不變。新v6先修exact第三方分類／完整初始化及動態閉包、記Job member PID/exe/exit與有界自然排空；原v5封套留存，不重跑已知失敗或釋放matrix。原篩選p95=446.3604ms及strict<300ms要求不變。

### P08 typed v24：完整旅程通過，正常型態仍有23項

Owner manifest `eca13853bfaad76d31183a5b96083b9211f43bb3b79f5770568c376edf0174c1`。Root核1164 pins／2237 checks，71534-byte產品diff的23段全文重建、389個原assert AST相同，八原tests只重綁namespace；adapter由本版AST重建418 modules／edges，保留v24 card文字與七個prior-clock keys。實際14候選origin native0／1168 pins。首個完整旅程因root封套只設PERSONAL_DATA_ROOT而缺配對來源，被既有TWStockConfig拒絕，原 **1 FAIL／9.57秒** 保存；移除不完整個人儲存override後，同candidate與原assert **1 PASS／82.56秒／native0**，1172 pins不變、7 actual PIDs source guard clean。收據 `root/p08_type_v24_integration_b597258025d844b29a5fa9a176e75f77/receipt.json` SHA `fb65c13d26ad6899bd5af322a1c4bcd1f7426a9d1938fb8e5416a7de150ecf3f`。

首次正常mypy因namespace package被辨識兩個名字，native2；依本機mypy原碼加explicit-package-bases，關閉hard exit以保存atexit來源紀錄，不改正常follow-imports或typing規則。第二次 **23 errors／6 files（14 targets）／native1**，1172 pins起訖相同、source guard clean；收據 `root/p08_type_v24_types_956498645883401394036f48bd74579f/receipt.json` SHA `99975ca7c6b8d48c43788fe415a0ec71e73448f82fa70e3cfdfccae78b8a8d97`。缺口為完整TypedDict keys、nullable欄位、prior locator／decision/card unions及JSON narrowing；不能用ignore／Any／cast或放寬validator掩蓋。原owner另建typed v25，另一owner以真正public seed/checkpoint writer→exact typed prior修六target fixture及一舊receipt。未跑本版八檔全組、不與不同版通過數相加，未套正式source。

### 日曆與績效候選

Calendar v2 origin native1：bridge把venv urllib3.exceptions錯判為unlisted repo，來源pins不變，五候選載入未完成；未跑focused QA。靜態追線另核兩個DecisionDesk入口仍用cadence.clock，而v2移除該公開屬性。原失敗 `root/calendar_v2_origin_df57417213cd422590db691015ec1f8c/receipt.json` 保留。新v3恢復clock callable、保留assess明示observation policy，新增兩個真入口clock傳遞回歸；第三方只排除runtime/sys.prefix/sysconfig所固定的purelib/platlib根。Root只核525 pins、488 closure及86757-byte全文diff重建；manifest `2bba498dfffd5406b7ed33e46f31a1094761545e4e41c116f9c19655d4197dd3`，尚待完整bridge語義／origin／定向QA／型態，不授正式整合。

P08 performance v6仍是review候選。Root第二份清冊盤點56 pins／56 checks、11 Python AST可解析、無顯式float constants/calls；已讀整分／獨立Decimal context核心，完整series reader／benchmark／ResearchRun及新程序語義仍待。原首份清冊34 pins未走進帶path/sha的上層內嵌source mapping，保留並以第二份核全部22 upstream mappings；不把首份當完整來源核對。v2舊public series與v3新metrics route各自binding及日期語義分開，v3名義13:30不是官方收盤事件證明，所有qualification保留false。完整同版performance組合待typed修正後接續。

### 保存與Coverage

本輪所有root QA handles皆已消費終態；三位既有Luna Max續做P01封套、P08型態及真fixture。只追加Snapshot／本QA／本機shared state／handoff；正常UI／正式API／Manual／Roadmap及架構政策未改，既有QA入口仍可到達。原始資料、正式產品、main／push／release均未改。Raw與四文件preimages已先保存；不能由本輪局部通過宣稱產品完成。

目前 HEAD `3f7690e02e48d63ed57e128763a6871b3ffb7946`，Health保存後另有其他工作提交兩個排程scripts與兩個tests；不是本root修改或驗收。Root重新核本輪四個QA receipt所有來源pins，與這四條外部source變更沒有交集，原驗證來源仍相同。不能再把HEAD至Health之間稱為只有docs變更。


## 最新接續：P08 真候選接線與完整生命週期重驗

本輪讀回 dev HEAD `ef5edd675abcd7cf211ed609874e5b20ec8b43b2`；Health 正式後端提交為 `f163e6fde33c7c64b0f39a7bd5a931c9e677c25f`，兩者間只新增文件變更，產品來源仍與 QA pins 相同。Health 後端最終十五檔 **214 PASS／2 skip** 已保存，不代表正常 Health UI 完成。本輪 P08 產品變更全部在不可變 scratch sibling，沒有套用正式模組或改原始資料。

Root 由 seed/clock v2＋v3 組合候選逐輪核驗，保留失敗與原測試預期。已修正：seed canonical receipt 記錄、producer stock grammar 缺件、daily 參考價格提前使用未初始化變數、官方 calendar cache hash 格式、quote receipt 綁 SQLite row hash、exact reader 區域 receipt 名稱。CSV projection 與 SQLite projection 的雜湊分別綁各自實際型別序列化，依公開 publication 契約逐一重核，不要求兩者字面相等；SQLite REAL 僅在 reader 序列化邊界轉成有限 Decimal，沒有新增金融 float 算式。Checkpoint DTO 明示 execution/performance eligibility 均為 False，true／1／None／文字假值八負例保留。

v8 的共享批次引擎→daily 帳本→已消費 seed→歷史 seed／新 PID 讀回節點 **1 PASS**，同輪另一完整旅程 **1 FAIL／25.88秒／native1**，667 pins 不變；收據 `root/p08_seed_clock_integration_de2ec154d3e34c9d8b2264104db7c921/receipt.json` SHA `926523ce8cb14da3f944bca0ad3d26e194e684a5b303f045ce1eaee9c91eb738`。這是有限真 API 合成來源旅程，不是正式行情／交易／績效資格。

Root 在 v10 將公開行情 scalar DTO 延遲匯入本版 daily，MA／KD forward source DTO 及三個 executor/intent 的 exception 也改成本版 candidate。v10 起從全 415 封存 Python 來源 AST 重建 import edges；22 source/test hashes 與原斷言 AST 核驗，改動不使用 formal 舊 DTO 代替候選。v10 首次 sandbox **1 FAIL／13.72秒**，精確暫存路徑 stat 相同、resolve 在 sandbox WinError5／host 成功；同 freeze host 再驗 **1 FAIL／16.30秒**，已走過 MA 成交、公 reader、新 PID seed，停於兩個負例 SQLite connection 未設 Row factory。v11 只補兩 fixture 的 Row factory，**1 FAIL／19.79秒**，超限負例到原預期錯誤，之後三個舊 DTO `.marker` 屬性斷言待修。v12 只沿公 checkpoint `ledger_operation` 直接讀 zero_fill，三原 False/True 值不變，金融／來源／時鐘判斷不變。

v24 manifest SHA `44ab7fe12ea82e60ae187f5912655a13c4de3c92308de22ad0f1902f6056c42e`。v12 整體1 FAIL／16.53秒，KD forward 公 reader 的 isinstance 因測試替換 datetime 被誤判；v13只修隔離 clock double 的 instance 判讀，沿標準庫 datetime 判別型別，原 naive／future guards 不變。v13 整體1 FAIL／17.15秒，實際 KD source consumer 錯要求二欄訊號，公開 DTO 嚴格提供五欄。v14 改核精確五欄，新增逐股 snapshot／source-window／raw-window 三個 pin 與 exact parent 快照重核；不省訊號、來源或時鐘 guard。v14 整體1 FAIL／18.27秒，KD intent 成功後 daily 把指標窗口日期當作收盤價日期。v15 價格日改綁同份 exact capture.decision_date（strict date），MA/KD public source 已證 close 只取該日唯一有效 OHLC；仍核官方 T−1、public close/value/row hash 與 cutoff。指標缺暖機保留 unknown，不新增金融 float。v15 整體1 FAIL／16.39秒，KD SourceCaptureView adapter 遺漏原已核 source 的 decision_date；v16 只補 date 欄位與 _make_read 的同值委派，source projection 原已有 source_decision_date，artifact/hash/clock/qualification 未改。v16 整體1 FAIL／15.81秒，shared engine caller 仍讀 MA 專用 strategy_decision.source_decision_date；v17 改用同函式前方 strict date 已核 capture.decision_date，兩家族來源／官方參考日核驗保留。v17 整體1 FAIL／18.88秒，測試時鐘替身繼承 fromisoformat 回傳 datetime 子類，被共享引擎的 exact datetime 守衛拒絕；v18 僅改 QA helper 的解析回標準庫 datetime，不改原 ISO 值／naive/future 檢查、產品 guards 或 assert。v17 wrapper 印含繁中文字串另遇 cp1252 UnicodeEncodeError，child 原始終態 native1、pins/guard 與完整 raw receipt 已在列印前保存；v18 以 -X utf8 啟動 wrapper，不修改舊 runner。v18 整體1 FAIL／19.69秒，首次 KD seed 尚無成本帳本，policy 的 readonly open 正確拒絕；MA fixture 手工初始化曾隱藏此缺口。v19 daily 只在 exact typed、unconsumed seed 使用已選帳戶 route 的 public ledger writer 建空 schema，移除 MA 手工 bootstrap，讓兩家族都走真首次 writer。既有 checkpoint／consumed seed 不建立缺失帳本，政策／交易鎖／CAS與資金計算不變。v19 整體1 FAIL／27.06秒，MA/KD首次進場、兩家族 consumed seed／新PID讀回及原斷言已走過，10/15 KD blocked intent 被10/06+預設7日cache的到期守衛拒絕。v20只在跨10/06–10/23的fixture明示公 builder合法31日max_age，實際receipt/hash/expiry重算；捕捉日期、future／expired守衛與原assert不變。v20 整體1 FAIL／39.44秒，blocked intent已通過，下一daily prior validator只接受v1卻遇本版writer發布v2 receipt。v21只准原v1及唯一具名P08 v2，完整canonical bytes/hash/account/snapshot/qualification守衛不變；隨後public availability _verify_base_checkpoint逐schema核operation配對、ledger、來源／clock與p08 engine receipt，未知版本仍拒絕。v21 整體1 FAIL／39.94秒，KD blocked daily及exit writer已走過，KD讀回cutoff07:15但observer仍07:10，被未來cutoff守衛拒絕。v22只在該讀回前將mock observer設為既有SECOND_CHECKPOINT_READ_CLOCK，如原MA讀回；所有原cutoff、價格、成交與assert不變。v22 整體1 FAIL／104.45秒，MA/KD 首次進場、KD UNKNOWN／超限零成交、雙家族賣出與空倉日、KD新PID公 reader已返回；fixture仍把nested snapshot JSON取為flat欄位，於snapshot_id KeyError停止。v23只改九個斷言左側 API取用，snapshot_id/cash沿snapshot取值、positions投影原stock_code/quantity/market_value三欄；原所有右側值、比較運算與產品函式均不變。v23 原八檔終態52 PASS／10 FAIL／1 skip／110.42秒，1209 pins相同、9 actual PIDs clean；完整MA/KD節點通過，剩餘6個typed prior fixture、1個舊v1 executionreceipt、2個KD最小clock先決schema及1個card token。v24補KD七prior clock keys，負例仍要求原database identity拒絕；card只將15_percent與of_current_NAV間空白改底線，建構15% entry budget及policy 15% NAV皆不變。原三節點3 PASS／5.23秒／native0，1244 pins起訖相同，收據root/p08_seed_clock_integration_69b5422c66fa4976905f2248b537ac0a/receipt.json；不能與v23不同版結果相加或宣稱全組已通過。Card hash自然重算後另驗完整MA/KD節點。Fresh origin 實際匯入14候選／native0；完整 host 節點 **1 PASS／0 FAIL／native0**，1252 pins 起訖相同、source guard clean、7 個實際 PID 有載入來源證據。完整 MA／KD 同來源旅程通過。原始收據 `output/qa/baldr_completion_20261011/root/p08_seed_clock_integration_252e151b5c5c4da89c16ba13cfd76038/receipt.json` SHA `1716db0ffd4f282ca13b109d8eafffaebaeb340c5d746c1eae5b023c3b9023e1`；stdout／JUnit／actual origins 全部保存，不授完整 Windows Job／資源清理或全部測試接受。

v9 十四來源型態診斷 **54 errors／10 files**，收據 `root/p08_types_eebba157537444788e43df1ea3fa1e88/receipt.json` SHA `a0282b05669732a0802c7f5a0322ba64a67b3f403eb89c3fc20f087913334113`。此為 follow-imports=skip 診斷，尚非型態接受；需修 TypeAlias、JSON narrowing 與 typed fixtures，不可廣泛 ignore／Any 或放寬 runtime guards。

接續依據：完整同版八檔回歸、typed fixtures／型態、績效／benchmark及正常 UI。P01 rolling scheduler／QA bridge、Calendar immutable live/historical clock 及 P08 performance v6 繼續準備；Health Main/Portfolio／新 PID 候選 freeze SHA 32bd32853d39283afc8bd0d0d7d7ad2deaac865fc8090905d5de53dbf6c440c5 已交 root 待審，未授 QA。原 Health Luna Max 接 P08 型態候選、performance owner 後接 public-prior 真 fixture；無新正式套用。所有 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持開放。

本輪 Coverage 限 Snapshot／本 QA／本機 shared state；正常 UI、正式 API、架構、Manual、Roadmap 方向及門檻未變，既有入口可到達。文檔／raw 前像封套 `output/qa/baldr_completion_20261011/root/p08_composition_handoff_d4e92d91012948409e439e4928439bb8`；上一純狀態輪為 no progress，本輪有候選接線修正與改變接續動作的真 QA 證據，分類 progress。

本輪完整節點 JUnit 用時 **66.26秒**，controller 用時 **67.72秒**，兩者分列。

Calendar v2 靜態核 **517 pins／485 module closure／83,246-byte 全文 diff** 重建一致；bridge 實際 SHA `3c09fef50eb50cac23e5611b323a5aaaa24684f55c1fcae34195ee8ec62d105f` 與 manifest 相符，owner 交接字串 e270… 已校正，不判為來源漂移。收據 `root/calendar_v2_static_review_0b49b0c112784fa6aac86fb55143e860/receipt.json` SHA `86e3d3489905d13e02be51b4cffc42e769b31a90b5fe13bb3fbce885d51dccde`；尚未完成整體語義審查、origin 或 QA。

### P01 v4 靜態拒絕與 benchmark 版本裁決

Root 重核 P01 rolling v4 manifest SHA `10f84f7e99e86a5dfdcf44fffde176abb0b8cbca994e2bf828390be3907f2fec`、403 unique pins、376 AST module closure 與完整21,626-byte diff。演算法保留最多8 unfinished futures／16 submitted unconsumed groups、順序 DTO／error、取消能力與 reader 守衛；沒有執行測試或新效能矩陣。Launcher 卻在 CREATE_SUSPENDED 的 Popen 後要求 `_thread`。實際 `C:/Program Files/Python311/Lib/subprocess.py` 中 Popen 的 AST 無 `_thread`，`_execute_child` 只保存 process handle 並 CloseHandle(ht)，因此新版一定在 Resume 前因 thread handle missing 失敗；QA 前拒絕。收據 `root/p01_rolling_v4_review_42f791a8baf44421bba6f205cf2aad73/receipt.json` SHA `7dd0494019b1d970caac39234346443522f15c0b8999c12224eadd443e8bb746`，實際stdlib／launcher原件與diff已保存。Owner先完成Calendar immutable clock v2，再另建v5保留真thread handle→Assign Job→Resume及錯誤收尾；原446.3604ms篩選與300ms門檻不變。

P08 performance v6 尚未freeze/QA。新版名義台北13:30政策採獨立 `p08-source-cohort-equal-weight-eod-clock-v2-1`／2.1.0 與新版schema，舊 `p08-source-cohort-equal-weight`／2.0.0 reader 委派舊契約，不重解舊rows。正式binding依id/version/hash與account route固定；public ledger API驗兩ID不碰撞，各版本用合法獨立binding/route驗寫讀，不造雙binding共用route。舊ResearchRun prefix於later append後fresh PID不變、真writer與typed fixtures仍待驗。13:30明示為名義政策，不代表已取得官方close event或正式績效資格。

## 最新接續：P08 真候選接線與完整生命週期重驗

本輪讀回 dev HEAD `ef5edd675abcd7cf211ed609874e5b20ec8b43b2`；Health 正式後端提交為 `f163e6fde33c7c64b0f39a7bd5a931c9e677c25f`，兩者間只新增文件變更，產品來源仍與 QA pins 相同。Health 後端最終十五檔 **214 PASS／2 skip** 已保存，不代表正常 Health UI 完成。本輪 P08 產品變更全部在不可變 scratch sibling，沒有套用正式模組或改原始資料。

Root 由 seed/clock v2＋v3 組合候選逐輪核驗，保留失敗與原測試預期。已修正：seed canonical receipt 記錄、producer stock grammar 缺件、daily 參考價格提前使用未初始化變數、官方 calendar cache hash 格式、quote receipt 綁 SQLite row hash、exact reader 區域 receipt 名稱。CSV projection 與 SQLite projection 的雜湊分別綁各自實際型別序列化，依公開 publication 契約逐一重核，不要求兩者字面相等；SQLite REAL 僅在 reader 序列化邊界轉成有限 Decimal，沒有新增金融 float 算式。Checkpoint DTO 明示 execution/performance eligibility 均為 False，true／1／None／文字假值八負例保留。

v8 的共享批次引擎→daily 帳本→已消費 seed→歷史 seed／新 PID 讀回節點 **1 PASS**，同輪另一完整旅程 **1 FAIL／25.88秒／native1**，667 pins 不變；收據 `root/p08_seed_clock_integration_de2ec154d3e34c9d8b2264104db7c921/receipt.json` SHA `926523ce8cb14da3f944bca0ad3d26e194e684a5b303f045ce1eaee9c91eb738`。這是有限真 API 合成來源旅程，不是正式行情／交易／績效資格。

Root 在 v10 將公開行情 scalar DTO 延遲匯入本版 daily，MA／KD forward source DTO 及三個 executor/intent 的 exception 也改成本版 candidate。v10 起從全 415 封存 Python 來源 AST 重建 import edges；22 source/test hashes 與原斷言 AST 核驗，改動不使用 formal 舊 DTO 代替候選。v10 首次 sandbox **1 FAIL／13.72秒**，精確暫存路徑 stat 相同、resolve 在 sandbox WinError5／host 成功；同 freeze host 再驗 **1 FAIL／16.30秒**，已走過 MA 成交、公 reader、新 PID seed，停於兩個負例 SQLite connection 未設 Row factory。v11 只補兩 fixture 的 Row factory，**1 FAIL／19.79秒**，超限負例到原預期錯誤，之後三個舊 DTO `.marker` 屬性斷言待修。v12 只沿公 checkpoint `ledger_operation` 直接讀 zero_fill，三原 False/True 值不變，金融／來源／時鐘判斷不變。

v23 manifest SHA `cccfd7a981466bb80b3929499d50a87c9b56d7d49bca64967d9c265da2c8be91`。v12 整體1 FAIL／16.53秒，KD forward 公 reader 的 isinstance 因測試替換 datetime 被誤判；v13只修隔離 clock double 的 instance 判讀，沿標準庫 datetime 判別型別，原 naive／future guards 不變。v13 整體1 FAIL／17.15秒，實際 KD source consumer 錯要求二欄訊號，公開 DTO 嚴格提供五欄。v14 改核精確五欄，新增逐股 snapshot／source-window／raw-window 三個 pin 與 exact parent 快照重核；不省訊號、來源或時鐘 guard。v14 整體1 FAIL／18.27秒，KD intent 成功後 daily 把指標窗口日期當作收盤價日期。v15 價格日改綁同份 exact capture.decision_date（strict date），MA/KD public source 已證 close 只取該日唯一有效 OHLC；仍核官方 T−1、public close/value/row hash 與 cutoff。指標缺暖機保留 unknown，不新增金融 float。v15 整體1 FAIL／16.39秒，KD SourceCaptureView adapter 遺漏原已核 source 的 decision_date；v16 只補 date 欄位與 _make_read 的同值委派，source projection 原已有 source_decision_date，artifact/hash/clock/qualification 未改。v16 整體1 FAIL／15.81秒，shared engine caller 仍讀 MA 專用 strategy_decision.source_decision_date；v17 改用同函式前方 strict date 已核 capture.decision_date，兩家族來源／官方參考日核驗保留。v17 整體1 FAIL／18.88秒，測試時鐘替身繼承 fromisoformat 回傳 datetime 子類，被共享引擎的 exact datetime 守衛拒絕；v18 僅改 QA helper 的解析回標準庫 datetime，不改原 ISO 值／naive/future 檢查、產品 guards 或 assert。v17 wrapper 印含繁中文字串另遇 cp1252 UnicodeEncodeError，child 原始終態 native1、pins/guard 與完整 raw receipt 已在列印前保存；v18 以 -X utf8 啟動 wrapper，不修改舊 runner。v18 整體1 FAIL／19.69秒，首次 KD seed 尚無成本帳本，policy 的 readonly open 正確拒絕；MA fixture 手工初始化曾隱藏此缺口。v19 daily 只在 exact typed、unconsumed seed 使用已選帳戶 route 的 public ledger writer 建空 schema，移除 MA 手工 bootstrap，讓兩家族都走真首次 writer。既有 checkpoint／consumed seed 不建立缺失帳本，政策／交易鎖／CAS與資金計算不變。v19 整體1 FAIL／27.06秒，MA/KD首次進場、兩家族 consumed seed／新PID讀回及原斷言已走過，10/15 KD blocked intent 被10/06+預設7日cache的到期守衛拒絕。v20只在跨10/06–10/23的fixture明示公 builder合法31日max_age，實際receipt/hash/expiry重算；捕捉日期、future／expired守衛與原assert不變。v20 整體1 FAIL／39.44秒，blocked intent已通過，下一daily prior validator只接受v1卻遇本版writer發布v2 receipt。v21只准原v1及唯一具名P08 v2，完整canonical bytes/hash/account/snapshot/qualification守衛不變；隨後public availability _verify_base_checkpoint逐schema核operation配對、ledger、來源／clock與p08 engine receipt，未知版本仍拒絕。v21 整體1 FAIL／39.94秒，KD blocked daily及exit writer已走過，KD讀回cutoff07:15但observer仍07:10，被未來cutoff守衛拒絕。v22只在該讀回前將mock observer設為既有SECOND_CHECKPOINT_READ_CLOCK，如原MA讀回；所有原cutoff、價格、成交與assert不變。v22 整體1 FAIL／104.45秒，MA/KD 首次進場、KD UNKNOWN／超限零成交、雙家族賣出與空倉日、KD新PID公 reader已返回；fixture仍把nested snapshot JSON取為flat欄位，於snapshot_id KeyError停止。v23只改九個斷言左側 API取用，snapshot_id/cash沿snapshot取值、positions投影原stock_code/quantity/market_value三欄；原所有右側值、比較運算與產品函式均不變。Fresh origin 實際匯入14候選／native0；完整 host 節點 **1 PASS／0 FAIL／native0**，1195 pins 起訖相同、source guard clean、7 個實際 PID 有載入來源證據。完整 MA／KD 同來源旅程通過。原始收據 `output/qa/baldr_completion_20261011/root/p08_seed_clock_integration_e423e5d81cc14f30a84d8a0df5e82eb2/receipt.json` SHA `0e16af3882157d7111d5ffc1a6b6b287a72aac58d985e26b380b23347a8b62fe`；stdout／JUnit／actual origins 全部保存，不授完整 Windows Job／資源清理或全部測試接受。

v9 十四來源型態診斷 **54 errors／10 files**，收據 `root/p08_types_eebba157537444788e43df1ea3fa1e88/receipt.json` SHA `a0282b05669732a0802c7f5a0322ba64a67b3f403eb89c3fc20f087913334113`。此為 follow-imports=skip 診斷，尚非型態接受；需修 TypeAlias、JSON narrowing 與 typed fixtures，不可廣泛 ignore／Any 或放寬 runtime guards。

接續依據：完整同版八檔回歸、typed fixtures／型態、績效／benchmark及正常 UI。P01 rolling scheduler／QA bridge、Calendar immutable live/historical clock 及 P08 performance v6 繼續準備；Health Main/Portfolio／新 PID 候選 freeze SHA 32bd32853d39283afc8bd0d0d7d7ad2deaac865fc8090905d5de53dbf6c440c5 已交 root 待審，未授 QA。原 Health Luna Max 接 P08 型態候選、performance owner 後接 public-prior 真 fixture；無新正式套用。所有 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持開放。

本輪 Coverage 限 Snapshot／本 QA／本機 shared state；正常 UI、正式 API、架構、Manual、Roadmap 方向及門檻未變，既有入口可到達。文檔／raw 前像封套 `output/qa/baldr_completion_20261011/root/p08_composition_handoff_12162713d1044b74a1353ce3b4251d1f`；上一純狀態輪為 no progress，本輪有候選接線修正與改變接續動作的真 QA 證據，分類 progress。

本輪完整節點 JUnit 用時 **89.53秒**，controller 用時 **98.69秒**，兩者分列。

### 同一 v23 八檔回歸終態

Root 使用同一 manifest 與原八個完整測試檔，不改 selection/node/預期；**52 PASS／10 FAIL／1 skip／110.42秒／native1**。1209 pins 起訖相同、source guard clean、9 個實際 PID；原收據 `output/qa/baldr_completion_20261011/root/p08_seed_clock_integration_9f0ef88f3d95454b934fb95a61faf2c7/receipt.json` SHA `ac7242f5a16f1f4e9ab582e334fbe0f685e7717e7e50876b24d826a30ac3df00`。此回歸與前述完整節點不累加，金融／型態／績效與正常 UI 接受仍依各自證據。

保留未通過節點：`test_kd_lifecycle_freezes_unknown_hold_and_caps_new_entries_per_entry_budget`；`test_unknown_and_held_quantities_stay_frozen_while_entry_uses_shared_builder`；`test_low_cash_does_not_rebalance_unknown_position_or_create_zero_share_order`；`test_death_cross_only_target_can_be_empty_without_recreating_cash_allocations`；`test_held_and_unknown_quantities_stay_frozen_after_price_move_and_zero_bp_value`；`test_entry_cap_is_fifteen_percent_of_entry_budget_with_multiple_new_symbols`；`test_strategy_card_states_entry_budget_cap_base_explicitly`；`test_availability_reader_accepts_only_hash_bound_nonqualified_p08_engine_receipt`；`test_kd_exact_intent_reader_rejects_database_not_used_at_write_time[recorded_file_id]`；`test_kd_exact_intent_reader_rejects_database_not_used_at_write_time[alternate_database]`。下一步核原始 traceback 與 fixture/產品契約，再另建 sibling，不能以單一旅程通過抵消全組失敗。

Calendar v2 靜態核 **517 pins／485 module closure／83,246-byte 全文 diff** 重建一致；bridge 實際 SHA `3c09fef50eb50cac23e5611b323a5aaaa24684f55c1fcae34195ee8ec62d105f` 與 manifest 相符，owner 交接字串 e270… 已校正，不判為來源漂移。收據 `root/calendar_v2_static_review_0b49b0c112784fa6aac86fb55143e860/receipt.json` SHA `86e3d3489905d13e02be51b4cffc42e769b31a90b5fe13bb3fbce885d51dccde`；尚未完成整體語義審查、origin 或 QA。

### P01 v4 靜態拒絕與 benchmark 版本裁決

Root 重核 P01 rolling v4 manifest SHA `10f84f7e99e86a5dfdcf44fffde176abb0b8cbca994e2bf828390be3907f2fec`、403 unique pins、376 AST module closure 與完整21,626-byte diff。演算法保留最多8 unfinished futures／16 submitted unconsumed groups、順序 DTO／error、取消能力與 reader 守衛；沒有執行測試或新效能矩陣。Launcher 卻在 CREATE_SUSPENDED 的 Popen 後要求 `_thread`。實際 `C:/Program Files/Python311/Lib/subprocess.py` 中 Popen 的 AST 無 `_thread`，`_execute_child` 只保存 process handle 並 CloseHandle(ht)，因此新版一定在 Resume 前因 thread handle missing 失敗；QA 前拒絕。收據 `root/p01_rolling_v4_review_42f791a8baf44421bba6f205cf2aad73/receipt.json` SHA `7dd0494019b1d970caac39234346443522f15c0b8999c12224eadd443e8bb746`，實際stdlib／launcher原件與diff已保存。Owner先完成Calendar immutable clock v2，再另建v5保留真thread handle→Assign Job→Resume及錯誤收尾；原446.3604ms篩選與300ms門檻不變。

P08 performance v6 尚未freeze/QA。新版名義台北13:30政策採獨立 `p08-source-cohort-equal-weight-eod-clock-v2-1`／2.1.0 與新版schema，舊 `p08-source-cohort-equal-weight`／2.0.0 reader 委派舊契約，不重解舊rows。正式binding依id/version/hash與account route固定；public ledger API驗兩ID不碰撞，各版本用合法獨立binding/route驗寫讀，不造雙binding共用route。舊ResearchRun prefix於later append後fresh PID不變、真writer與typed fixtures仍待驗。13:30明示為名義政策，不代表已取得官方close event或正式績效資格。

## 最新整合：Health 廣回歸通過與 P08 clock guard

Root 核三檔 fixture 候選 manifest `2fd1467d2a2fb6ca3ad2e7ba1c8d6ba21d0d26f90a1cd3da6f14835e6837044b`、6940-byte full.diff、原 host 失敗收據及 JUnit；完整 diff 逐檔重建，所有原函式斷言 AST 相同。移除 degraded 正例的假 rows hash，另保留具名 malformed-hash 拒絕；scheduled double 明示其原預期 manual action；calendar fixture 只固定模組局部觀測時間，新增 future／expired 負例，不改正式 cache freshness、來源 hash 或決策 cutoff。保存三檔原始 bytes 與變更前回滾清單後套用，apply 收據 `root/health_fixture_apply_0818ce2a2dce4750ac324d693ea34d09/receipt.json` SHA `c3dd4f49c44188b5e1bed2567ab86a6e2b165711d546acdf2497039c1bd55693`。原五失敗收據保留。

| 同源正式驗證 | 終態與收據（相對本次 root QA 根） |
|---|---|
| 原十一檔 regression | **125 PASS／1 skip／21.41秒／native0**；`health_formal_v2_regression_b12ff680e22e4291871fa47a7ffc42b5/receipt.json` SHA `a666c5fa296d5c5dba6ab083fc62237e59790fb68073adc466b16f164d1c8991`。 |
| 原四檔 focused | **89 PASS／1 skip／7.34秒／native0**；`health_formal_v2_focused_6fa44230bf2e461bbf85349e8459ee20/receipt.json` SHA `95379302e45e8afef2c01795be989ea4e2159b63ac753ec1de51d6ce63655318`。不與 regression 累加為產品測試總數。 |
| 型態與語法 | 六正式產品 mypy、十三檔語法均 **native0**；`health_formal_v2_types_03f758140fe144d6b200ec4e579240e9/receipt.json` SHA `7d5a61a725479d4eb9f7fe0878df78bf39e4cd6545296f7e1e68e1447da1fd06`。 |

各輪 fresh child 都實際匯入六正式來源與 54 個本機依賴；625 pins 起訖相同、fresh bytecode 根空。兩組 skip 都是 reparse 環境能力，不能授原生 link／完整 G3／G4。六產品、四原 focused tests 與三 fixture tests 的後端增量可保存；正常 Health Portfolio／Main 介面、策略 EOD adapter 與完整 P06／M3 尚未接受。Calendar 的雙時鐘是獨立產品缺口，fixture 固定時鐘沒有修正它；live／historical operation clock 候選持續實作。

提交前 `git diff --cached --check` 抓到新封存測試檔 EOF 多餘空行；第一個提交 helper 在 commit 前停止，未建立提交。Root 保存原件及回滾清單，僅移除末尾空行並核 AST 完全相同，after SHA `10d1e522ab3a69d1891998cc05ecf645ecac4cdc0c438bebc42ea60eec9210db`。最終 bytes 的原四 focused＋十一 regression 合併為十五個不同檔案，**214 PASS／2 skip／27.52秒／native0**，六來源 mypy／十三檔語法通過；626 pins 起訖相同、fresh bytecode 根空。這是獨立最終執行，不與先前 125／89 累加。收據 `root/health_formal_v3_all_eceb523cd91141168fc835a972d63b92/receipt.json` SHA `08326fdec6d3ac2b0fb4520e2a5af84e1821f1a7fa417161f83121ed965cedc5`；EOF 修正收據 `root/health_eof_normalization_41c7a7ff1347413f9d634860df6fdba8/receipt.json` SHA `f6584ecc5d6a93c590d9acc1ecc4345d763ce6c4827e218024fe6727d11f9bc0`。所有程序已自然終態。

P08 clock guard v3 靜態核 151 次／130 pins、完整 patch 與同 BEGIN 的 type／byte 預檢順序後，僅釋出四個 SQLite guard tests；**4 PASS／6.68秒／native0**、130 pins 相同、bytecode 根空。Oversized 8193 bytes、BLOB、duplicate 在 full receipt SELECT 前拒絕，8192-byte TEXT 邊界允許取值。收據 `root/p08_clock_v3_guards_8a8ee097caf745aea61cb3b982ebf10d/receipt.json` SHA `4c1c5085febbf4de276032108047b08064cc04551d4532018911ae23cc36f16f`；不授 canonical receipt、完整 reader／writer race、兩策略生命週期或績效資格。

P08 v6 財務候選靜態審查已修正最大回撤以比例比較、次分拒絕及零 prior NAV 的未定義日報酬；新有界 series reader 仍需 type／byte 預檢、完整 prior SHA／ledger rowset 鏈及結尾 exact 重驗，已交 owner 補齊。候選尚未 frozen／QA／套正式，benchmark／ResearchRun v2／正常 UI 的完整交付持續推進。原範圍與全部 Gate 保持開放。

## 最新終態：P01 v4 完整千檔矩陣

原五 cold／一 warm、每角色 600 秒、三類各 30 samples 與嚴格小於 300 ms 門檻均保留。Session 86056／supervisor PID 42504 已自然 native0；不是效能 Gate 通過。Root 直接讀取原 90 筆耗時並按 nearest-rank 獨立重算：翻頁 p95 **207.0988 ms**、全域排序 **251.5675 ms**、篩選 **446.3604 ms**；三類完整 DTO 全部相等，篩選仍未達標。五冷啟動至首頁 p95 **31.9190474 秒**，與操作耗時分列。1464 pins 起訖相同，各角色完成後 Job 清理無殘留；原失敗封套保留。這是固定合成來源診斷矩陣，不授正式全市場、正常產品旅程、新 EXE 或真人接受。

Root 收據：`output/qa/baldr_completion_20261011/root/p01_v4_matrix_8095af1b05a24c17ad252c3af7a02e8c/receipt.json`，SHA `2e5591e209368a7831615c112dea51113ca810e06a0f50c8006e314a303b6c50`。Supervisor 收據：`output/qa/p01r_1011/ers_v4/candidate/supervised_matrix_attempts/attempt_20261011T154146Z_101430b2f974/supervisor_receipt.json`，SHA `12d389df0170223947c02f5c3241735be0e2683e5ae5432dea4a6bfa4c2a47b2`。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 仍持續推進。

完整需求仍依 [原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)，保留 P00–P14、M1–M3、F01–F23 與 G0–G4。本文只記錄本次實作與驗證，不取代 Snapshot 或 Manual。起點為 `dev`／`04b35387`；原九份文件 dirty 保留。

## 排他分工

| Owner | 可寫範圍 | 出口 |
|---|---|---|
| p01_perf（Luna Max） | `personal_data_paths.py`、其測試；root 審查後另釋出 v4 query／測試的單一時段；隔離 QA | 先取 current-source 真 API profile，再依證據改善；原 300ms 不變；Main freeze 期間不可改既有來源 |
| f12_journey（Luna Max） | 新營收 Main 旅程測試與隔離 QA | 精確只讀 SQL 角色、真確認／收藏／關閉／新程序重開 |
| p08_daily（Luna Max） | 新 `strategy_paper_account_daily.py`／測試；既有 `paper_trade_ledger.py`／測試 | 同交易 CAS、有序 fills、零成交與跨 DB 重試；正式 quote clock 缺口保留 |
| root | 配置 DTO／service、新持倉情境 service／測試、共用 UI／文件 | 純規則入口沿既有金融計算，已選帳本研究情境保存、讀回及 UI |

## Root 實作前檢查

- 量化 guard 已執行，兩項靜態檢查通過；其白名單不等同新情境因果性證明。
- 情境只接受決策前已知的完整帳本狀態與行情；同日／未來狀態不授執行提案；未知持倉不得補零。
- 等權與明示目標沿既有整數 bp／Decimal 引擎。純規則入口不得建立假 model／dataset 身分，也不授 broker 或 rebalance 權限。

## 回滾清單

### 變更檔案清單

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `app_module/portfolio_allocation_dtos.py` | 修改 | 新增純規則請求／數值投影契約 | 保存當前差異並核對 owner，只還原本輪 diff／preimage | 移除後新情境入口無法 import |
| `app_module/portfolio_allocation_service.py` | 修改 | 現有計算共用於 Rule/ML 與純規則入口 | 同上；不還原其他 lane 檔案 | 須重驗既有 ML 配置回歸 |
| 新 `app_module/portfolio_research_scenario_service.py` | 新增 | 已選帳本研究情境 | 核對 postimage 和依賴後只移除本新增檔 | consumer 需同步解除 |
| 新 `tests/test_baldr_completion_p06_scenarios.py` | 新增 | 真限制／身份／因果性案例 | 同上，只移除本新增檔 | 移除會失去本輪回歸覆蓋 |
| 本文件 | 新增 | 排他 scope、證據及限制 | 核對 owner 後只移除本新增檔 | 交接證據遺失 |
| `docs/01_architecture/system_architecture.md`／`docs/00_core/PROJECT_SNAPSHOT.md` | 修改 | 新 API 的責任及未完成接線 | 只逆向移除本輪新增段／列，保留其他 writer 增量 | 交接狀態不同步 |
| `app_module/personal_store_routes.py`／`tests/test_personal_store_routes.py` | 修改 | 新情境 archive domain 與派生私人路徑 | 核對本輪 preimage／diff，只回滾新 enum／分支／案例 | 新 repository 會失去路由 |
| 新 `app_module/portfolio_research_scenario_artifact.py`／`app_module/portfolio_research_scenario_repository.py`／`tests/test_portfolio_research_scenario_repository.py` | 新增 | immutable 情境編解碼、明示保存及公開 exact reader | 保存 postimage，確認 consumer 解除後只移除本新增檔 | 跨程序研究讀回不可用 |
| `app_module/portfolio_research_scenario_service.py` | 修改 | 保存完整 input 以核 input hash | 只回滾本輪新增 input 契約／驗證 | 原 artifact reader 需保留相應 decoder |

### 回滾步驟

1. 比對當前 diff 與 `output/qa/baldr_completion_20261011/root/preimages/`，保存其他 writer 增量。
2. 僅逆向套用 root 差異；新增檔先核 postimage 及 consumer，禁止整個工作樹 reset。
3. 重驗配置與情境定向案例，不回滾任何市場／私人 DB。

## 驗收狀態

本輪尚未關閉任何完整工作包。單元測試、隔離合成旅程、原來源、同版 EXE、Native 與真人接受需分別登記；daily clock 缺口不能以合成成交補足。

### P06 純規則與情境計算增量

- 新增 `PortfolioRuleAllocationRequestV1`／`PortfolioRuleAllocationResultV1`。原 `project()` 保持 Rule/ML metadata 與 authorization 路徑；`project_rule_only()` 與它共用 `_project_weights()`，不建立 ML 提案或模型身分。
- `PortfolioResearchScenarioService.compare()` 只經 `read_exact(account_kind, portfolio_id, snapshot_id)` 讀一次完整帳本狀態，產生維持、等權及明示目標比較。候選排序固定，等權沿既有 Construction，所有風控與成本沿既有 Allocation。
- 純規則 result 綁實際配置 policy hash；comparison input hash 綁帳本、原來源 hash、aware cutoff、全部 context 事實、候選及目標。Health 未知、晚到資料、同日／未來帳本、跨帳本 context、缺持倉、錯股數／權重及缺候選價格均拒絕；不推定健康或空倉。
- 目前只完成計算 API 與 reader protocol。正常帳本 adapter、情境 artifact 保存／公開讀回、Portfolio／個股 UI、返回／新程序及 G3／G4 **尚未完成**，不得將此項列為 P06 或 M3 完成。

| 驗證 | 結果／範圍 |
|---|---|
| allocation service、新 P06 情境、Construction sandbox、Paper policy 四組定向 pytest | **56 PASS**；新情境 23 項、既有 allocation 20 項、Construction／Policy 13 項。Windows 沙箱對 `Path.resolve(strict=True)` 拒絕，改以核准的 elevated process 在工作區 isolated `pytest03` fixture 執行；未碰正式 DB。 |
| 3 個變更 source 的定向 mypy `--follow-imports=silent` | 通過；不宣稱 full repo mypy |
| 3 個變更 source＋新測試 `py_compile` | 通過 |
| `scripts/quant_guard_linter.py` 修改前／後 | 兩項靜態檢查通過；未納白名單的新檔另以 Decimal／因果性測試檢查 |

首輪 19 PASS／1 fixture PermissionError、次輪 40 PASS／3 failures 是本輪過程。次輪兩項新測試修正既有 diagnostic 名稱與缺少的 test ML proposal `coverage_bp`，沒有放寬產品門檻或刪除 assertion。最終 56 PASS 是同組定向回歸終態，不與前輪數字相加。

成功命令：`.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_allocation_service.py tests/test_baldr_completion_p06_scenarios.py tests/test_portfolio_construction_sandbox.py tests/test_paper_portfolio_policy.py -q -o addopts= --basetemp=output/qa/baldr_completion_20261011/root/pytest03`。

### 接續依賴

1. P06 接完整、受治理的帳本／Health reader adapter；缺原 clock 的帳本不能自行填 availability。
2. 設計情境 artifact 的明示私人保存路由與版本 decoder，再接正常 UI；session store 只是記憶體上下文，不能冒稱持久化。
3. P01 現源單次 cProfile 為 641.909ms（插樁診斷，非 p95）。主要成本是 lstat、bounded reads 與路徑檢查；已釋出 narrow absolute builtin Path 候選，不把單次診斷當原 300ms Gate 通過。
4. P08 CAS 葉片的 11 PASS 是 owner 聚焦結果；root 審查要求 `rowset_hash()` 固定同一 read transaction 並補測。daily companion、UI 與正式 clock 尚待，不先收完整葉片。

### P06 情境封存與公開 exact reader 增量

- 新增 `PORTFOLIO_RESEARCH` route，派生 `{personal_root}/portfolio/research_scenarios.sqlite`；constructor／空庫讀取不建立資料、不 fallback legacy。明示 append 才建立私人 schema；writer 僅限 PERSONAL，兩種 legacy 模式均拒絕 append。
- `portfolio_research_scenario_artifact.py` 封存完整 account、request、contexts、三種原計算結果與 policy／source hash。編解碼只接受 canonical JSON、有限 Decimal 字串、整數與已知版本；重複 key、JSON float／NaN、缺欄／多欄、執行旗標、錯帳本／時鐘／input hash／row contract 都拒絕。單一 payload 上限 2 MiB。
- `PortfolioResearchScenarioComparison` 核 row universe、current／requested／target／executable 權重、gap、行情價格／名稱、成本合計、等權分配與 causal state。讀回不呼叫現行 Allocation／Construction 重算原研究。
- repository 在 `BEGIN IMMEDIATE` 內核 schema、append／冪等回傳；content-addressed ID 不覆寫舊情境，重試保留首次 saved_at。保存時間統一 UTC，帳本 kind／id 隔離。公開 reader 沿 custody、SQLite `mode=ro`／query-only，在同一 read transaction 核大小、內容 hash 與索引，再回 typed artifact；查詢索引最多 200 IDs，選取時仍需 exact read 核內容。
- 新程序回歸以另一個 Python PID、實體私人 SQLite 與正式公開 reader 讀回同份 input／result。前後 DB SHA 相同；這是隔離合成帳本，**尚非正常 Main、正式帳本／Health adapter、原來源、同版 EXE 或真人接受證據**。P06／M3／G2–G4 仍未完整完成。

| 驗證 | 結果／範圍 |
|---|---|
| 新封存、P06、Allocation、私人 route、Construction、Paper policy 六組定向 pytest | **132 PASS／6.29 秒**；新封存 53 項、P06 23 項、Allocation 20 項、route 23 項、Construction／Policy 13 項。核准 elevated process；fixture 只在工作區 `output/qa/baldr_completion_20261011/root/archive04`。 |
| scenario service／artifact／repository 的定向 mypy `--follow-imports=silent` | 通過，3 個 source；不外推 full repo |
| 同三個 source＋新測試 py_compile | 通過 |

首輪封存回歸為 61 PASS／3 failures：保存 API 回傳未正規化的候選 tuple 順序，與 canonical decoder 回傳不同。已修正 writer 回傳為實際封存 payload 的 typed decode；原金融結果／hash 未重算。次輪 107 PASS；最終加入單一 read transaction／query-only、超大 BLOB 在 decoder 前拒絕、未知 schema 不修復等案例後為 123 PASS，不累加各輪。

成功命令：`.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_research_scenario_repository.py tests/test_baldr_completion_p06_scenarios.py tests/test_portfolio_allocation_service.py tests/test_personal_store_routes.py tests/test_portfolio_construction_sandbox.py tests/test_paper_portfolio_policy.py -q -o addopts= --basetemp=output/qa/baldr_completion_20261011/root/archive04`。

Subagent 唯讀審查另找出三項契約缺口，root 已修正後取得 132 PASS：限制私人 writer；拒絕 target／executable 中不在原 rows 的隱藏 0／正 bp 股票；schema 強制 covering index 的欄位及升降方向。新增拒絕負例、query plan 不使用暫存排序及兩個 writer 同時首次 append 的原子／冪等回歸。沒有定義自動刪除／保留配額；完整歷史可持續增長，現階段只證明單 payload、索引 read 與返回 ID 數的界線。實作前的 raw fixture／code SHA 保留，不作現行 schema 等價宣稱。

下一步仍是正常帳本／Health reader 的 exact source 與可得時鐘、Portfolio／個股 UI 接線、保存理由／返回／Main 新程序，以及完整 G3／G4。沒有以 caller 填的 SHA／時間推定真實來源；content hash 只證明封存完整性，不授資料資格。

另有既有金融契約限制：`CausalPortfolioState.v1` 與本 AccountState 要求正 bp 持倉；股數為正但整數權重為 0bp 的微小持倉不能完整表達。adapter 不得省略此持倉後產生情境，須明示來源與 blocker；完整 P06 仍需處理此情況。本輪沒有放寬既有 Rule/ML kernel 的 causal universe。

### P06 同帳本快照身分修正

Context 原僅核帳本 kind／id、股數與 bp；同帳本不同快照若持倉相同仍能混入。修正將 context 的 `snapshot_id` 納入必要輸入與 hash，並與 exact account／request 快照一併核對。比較 payload 與 input schema 升為 v2；舊 v1 缺快照耦合，公開 decoder 拒絕而不猜補身分、不改寫舊 DB。保存 store schema 維持 v1，因 SQL 欄位及索引未變。

回滾面僅限 scenario service、artifact codec 與兩個 scenario／repository 測試檔；preimage 保存在本機排除的 `output/qa/baldr_completion_20261011/root/context_snapshot_preimages/`。回滾前保存 postimage 並確認 consumers；只逆向本次增量，不回滾其他 writer 或市場資料。此修正不改金融計算或可得時鐘：所有 context 仍須在 cutoff 前已知，未知 Health 仍拒絕。根據因果自查，不以快照日期冒充保存／可得時間。

六組定向回歸本次 **140 PASS／6.75 秒／native exit 0**，比上一版本多 8 項負例／身分回歸：同帳本不同快照且持倉相同仍拒絕；完整更換快照身分會改 input hash；空白／非 canonical 身分拒絕；decoder 拒絕 v1、缺身分與錯快照；public reader 對 v1 payload 拒絕並保持 DB bytes 不變。另一個 Python PID 讀回的 fixture 亦隨新 payload 重驗。3 個 source 定向 mypy、4 檔 py_compile、修改前後量化靜態 guard 通過。命令沿前述六組測試，basetemp 改為 `output/qa/baldr_completion_20261011/root/context_snapshot01`；不累加前輪 132 PASS。此 backend 修正尚未接正常 UI、真帳本／Health 或完整 P06／M3 Gate。

### P06 精確估值契約

現有配置引擎從 NAV × cash bp 重建現金，而 bp 僅有萬分之一精度；真帳本的 Decimal 現金不能由此還原。新增 `portfolio_research_valuation.py` 與對應測試，保存完整股數、價格、市值、現金及 NAV，核 NAV = 現金 + 全持倉市值，保留正股數但顯示 0bp 的持倉。bp 只作明示確定性的近似顯示，不授資金、帳本可得時鐘或成交能力；後續須沿同一 Allocation 引擎接 exact monetary state。

| 檔案 | 類型／回滾 | 風險 |
|---|---|---|
| `app_module/portfolio_research_valuation.py` | 新增；保存 postimage 並確認 consumer 後僅移除此檔 | exact 估值 consumer 失去契約 |
| `tests/test_portfolio_research_valuation.py` | 新增；同上只移除此新增測試 | 失去資金守恆／微小持倉回歸 |

新增檔不改 Main 凍結來源；沒有修改正式帳本或捨棄持倉。金融自查：只核 caller 已取得的同份 snapshot 事實，不取未來行情；此 value object 不替來源 clock 或 Health 核驗背書。回滾須先解除 consumer，再核本次 postimage，不還原其他 writer。

估值契約定向案例 **32 PASS**；與已審閱的初版取消能力 7 項合跑為 **39 PASS／1.26 秒／native exit 0**，不與之前各輪相加。32 項涵蓋 exact 現金、NAV／全持倉守恆、同 bp 不同分金額的 hash 差異、微小 0bp 持倉、確定性最大餘數顯示、低 Decimal precision／Emax、未知列、股票 bp 損壞、重複持倉、數值／股數／列數界線。金融核心輸入拒絕 float／非有限 Decimal／分以下金額；乘法沿既有 `quantize_money` 並使用獨立 Decimal context，顯示 bp 沿整數分計算。2 個 source 定向 mypy、4 檔 py_compile 與量化靜態 guard 通過。

`PortfolioResearchValuation.from_snapshot()` 現可核正式 snapshot DTO 的完整估值，但不自行開 DB、不把收到 DTO 視為來源認證。尚未接替現有 Allocation 的 bp 還原金額路徑；現有情境 AccountState／causal v1 的微小持倉 blocker 仍有效。下一步須新增完整 monetary causal contract、沿同一引擎接精確金額，以及受治理的 exact source／availability reader，不能用新 value object 單測代替真帳本閉環。

### P06 精確金額接入（後端增量，完整接線仍待）

Root 單一 writer 接 Causal state 的版本化 monetary payload、同一 Allocation 引擎的 exact 現金／股數／市值及實際風控核對，並將 P06 AccountState 明示完整估值。舊無 monetary state 的 Rule/ML 請求維持原路徑；完整新情境不從顯示 bp 還原資金。新的比較／input payload 需升版，缺真現金的歷史 payload 不猜補。

回滾清單：Allocation DTO／service、scenario service／codec 與兩個 P06／archive 測試只逆向本輪 diff；新 exact-money 測試在核 postimage／consumer 後移除。六檔 preimage 保存於 `output/qa/baldr_completion_20261011/root/exact_money_preimages/`。回滾風險為新 monetary consumer 失去契約，須先解除 consumers，並重驗既有 ML／Rule 與情境；不覆寫其他 writer、不碰 DB 或市場來源。實作前後量化 guard 與因果負例必須通過，已知資料仍受 exact snapshot／aware cutoff／T−1 限制。

本節更新前述「尚未接 Allocation」的歷史狀態：`CausalPortfolioState.v2` 現綁完整估值；新 AccountState 必須保存實際現金、NAV、所有股數／mark price／市值。無 monetary state 的 v1 Rule／ML 請求沿既有計算；valued 請求沿同一 Allocation 引擎使用實際資金、整手／流動性／成本，並以成本後 NAV 核現金下限、實際單股／產業曝險、正股數持倉數與 hard exit。計算使用獨立 Decimal context，bp 仍作目標與既有再平衡政策單位，不能反推現金或忽略微小持倉。

比較／input schema 升為 v3；舊 v1／v2 缺完整金額證據，decoder 拒絕而不猜補或自動改寫舊 DB。政策 hash payload 升為 `portfolio-allocation-policy.v2`，明示 weight-derived／exact-money-post-cost-NAV 計算版本及原政策／成本／成交限制；不沿用舊 hash 冒稱新算法相同。封存讀回另外核完整 final valuation／顯示權重、按股數變化的現金守恆及此 v3 固定買 25／賣 55bp 成本，不重新執行當下 Allocation 或讀 live 行情。超過 10,000 列的估值先拒絕再建 DTO。

子代理唯讀審查發現零 bp hard exit 的 Advice 分類原先按 bp 遺漏，現按實際股數回 EXIT_CANDIDATE，完整可執行欄位仍在退出未完成時拒絕。非硬退出的小額持倉仍受既有再平衡 band／minimum trade；cash-only target 不代表強制清倉。保留的 0bp 持倉須在 executable contract、股數／市值、HOLD 與具名 retention diagnostic 中完整表達，不能顯示成已無持倉。

過程：首輪新金融案例 **79 PASS／1 failure**，原因是測試行情成交量上限先把目標增量截回 0bp；改為具名高流動性 fixture 以隔離真現金邊界後 **80 PASS**。八組回歸 `exact_money02`／`exact_money03` 均 **203 PASS**，最後一次 7.78 秒／native exit 0。接著增加 caller Decimal context 與小額 retention 兩例，三組定向 **82 PASS**；八組最終 **205 PASS／7.94 秒／native exit 0**。各輪數字不相加。

最終包含 frozen 金額損壞、成本後 cap、cash floor、買賣成本／守恆、同日／未來拒絕、caller context 獨立性及新 Python PID exact reader。收據 `output/qa/baldr_completion_20261011/root/exact_money_final01/receipt.json` SHA-256 `23c5584ce567a44c1db8557d054c172f44c2e264c96ff5aacff47c044983ce4d`：15 個來源／測試 byte pins 起訖相同，fresh reader PID 50928，隔離 DB SHA 前後均為 `9688541136c189d944110edcf365157a99647a35a65c50784af121646dde503e`，保存 clock 字串保持 UTC。六個 source scoped mypy、九檔語法、量化 guard 與 root scope diff check 全部 native0。全工作樹 diff check 另指出其他文件整理 owner 的 Archive EOF 空行，保留而未覆寫；不冒稱全樹 clean。Full UI／Main／原來源／新 EXE／真人與正常帳本／Health adapter 仍未完成。

### P08 審查接續（尚未接受增量）

Root 已讀 daily writer 全文與 ledger CAS 主流程。Owner 的 ledger 14／daily 9／cash seed 17 PASS 仍是 owner 聚焦結果；尚未 root 完整收取。審查要求先證明／補足以下缺口，不以 `performance_eligible=False` 取代金融核心核驗：

1. Caller fills 的費用、滑價與數量須核 exact binding policy／成本模型；目前只保存 hash 並做現金／股數 replay，不足以證明計算符合政策。
2. Quote event／cutoff 須與台北 execution／snapshot 日期及下一官方 session 契約一致；self-hashed sidecar 不能授正式行情時鐘。
3. Prior seed 的 `seed_created_at` 必須在決策 cutoff 前；daily prior 需實際 writer 保存／可得 clock，不能以 caller `mark_cutoff` 代替。
4. 後續 target→fill 若以開盤成交模擬，不能使用事後才完整的當日成交量。正式前向與明示 EOD replay 必須遵守各自因果邊界。

上述審查階段先由 owner 只讀盤點負例／既有 public API／最小修正範圍；沒有因此啟動正式 writer、Task 或 collector。

接續只讀負例已重現三項缺口：1,000 股非零買進而佣金／稅為零仍 append；quote event 的台北日期早於 execution date 仍 append；seed 保存時間晚於 decision cutoff 仍作 prior。root 已釋出新 daily／測試與可新增的 availability companion 範圍，先修時計並準備共享 producer engine 的精確 patch；既有 producer／seed writer／ledger／Main pin 暫不擴寫。成本模型、官方 event／calendar 與完整策略 persisted signal 的資格仍需補足，不把研究 replay 或 caller hash 當正式績效。所有正式 writer／Task／collector 保持未啟動。

### F12 聚焦 Main 旅程的本次終態

原 session `83137` 經同 handle 收取為 **exit 1／1 failed／1214.47 秒**，不冒稱 PASS 或測試 deadline timeout。Main 初始化最終完成，但 COW 按鈕不啟用；來源選擇回報 `personal_watchlist_source_unavailable`，尚未進 COW／catalog／query／fresh child。此前子代理工作區路由逾時不是程序終態；root 在 08:19:38 UTC 的 elevated CIM 確認 observer 可見且 exact runner tree（32848→52112→39552）已不存在，後由 owner 收取 pytest 終態。原來源 guard 保持。

根因仍需核 fixture：PROFILE=test 會使 output_root 加 `/_test`，而 test source 預建於未加後綴的路徑。先做小型配置／resolver 探針，再修自身 fixture；另加初始化階段 log、faulthandler 與明示 deadline，避免無界初始化觀察。未因 poll 逾時重啟、不用失敗 fixture 宣稱正式產品缺陷；新 Main candidate 須重新凍結來源再驗。

### P01 正式取消能力接線與整合驗證

前一 goal turn 僅回覆使用者進度，分類為 no progress；本輪核對當前 dev 後，root 審閱並套用六檔 Event qualification 候選，保留完整補完範圍。正式 TaskWorker／v4 View／query 與三個回歸檔在套用前逐檔核 base SHA，前版本及回滾表保存於 `output/qa/baldr_completion_20261011/root/p01_apply_2f16e38ff9ad4d1dbcbd6987b43a1a36/`；包含原 query／測試未提交增量，不以 HEAD 還原覆寫它們。

候選 patch SHA 為 `a44d8bcb3284ddb40dcfdbdd0ac5a993954e0b91c7b73f5c52283660bedc8abf`。`git apply --check` 通過；套用後 raw SHA 差異來自 newline，root 先斷言六檔 normalize 後文字與 pinned candidate 完全相等，再寫回原 candidate bytes，使六個 raw pins 與 manifest 相符。純 Python 能力模組與測試保持原候選版本。

TaskWorker 只在明確 opt-in、exact worker／原 method／Event 身分與未被 caller 提供的 callback 下發行能力；Event 方法不合格仍用原 callback 執行，不將 helper TypeError 當成任務失敗。v4 View 的選版／查詢／換頁／返回將同一 callback 與一次能力傳至 public reader。多 artifact 有界讀取保留 fresh I/O、原結果／錯誤順序、獨立 path memo 及 worker 自然排空；自訂回呼仍走序列路徑。沒有修改金融計算或來源資格。

| Root 驗證 | 結果及界線 |
|---|---|
| 純能力＋真 TaskWorker | 50 PASS；收據版重驗 1.82 秒／native0，八個 source／test raw pins 起訖一致。包含 positional callback、不以 kwargs 自動 opt-in、worker／Event override fallback。 |
| 更新工作台強制回歸 | 85 PASS／4.06 秒／native0；原測試未刪。 |
| 更新頁 validator | 25 通過／0 失敗／4 跳過／native0；合成 Temp 資料，不代表真下載或正式資料更新。 |
| 全範圍 mypy | 首輪 950 檔僅 P08 候選 daily JSON None 型別錯誤；交 owner 收窄後第二輪 950 檔通過／native0。保留首輪失敗；此結果不授 P08 金融／來源接受。 |
| 八個變更 Python 語法 | native0。 |
| 正式 query＋v4 View 全組 | session79511／pytest PID24644 執行中；尚未取得終態，不授整合通過。 |

Root raw 收據由 `output/qa/baldr_completion_20261011/root/run_p01_review.py` 保存 command、UTC 起訖、child PID、八個 raw source／test SHA 及檔案 log。stdout／stderr 直接寫專屬 regular file，沒有未排空 PIPE。觀察期限若到期會記 live_after_observation_timeout，不推定程序死亡；需沿原 handle／exact PID 核程序樹，不盲目重跑。

Manual §6.7 已同步背景讀取、取消後保留已核結果、晚到結果隔離與安全收尾；架構記錄程序內能力及序列 fallback 邊界。原千檔 filter p95 超過 300 ms 仍有效；完整 matrix、正常 Main／原來源／EXE／真人與完整 P01 Gate 尚待。P01 owner 接續 scratch 追加開始後取消、九個以上 artifact outstanding 上限與正常 TaskWorker matrix，未授權先跑重型 matrix。

### P08 Decimal context 審查負例

Root 在 availability source SHA `7429d5d047636fb9c4d7553f51fd98255ac0f2016594b13b960252ebcec2948d` 上只呼叫純 helper：同一合法 `500000.00`，caller Decimal precision 28 接受，precision 3 卻回 `root_cash_precision_invalid`。收據 `output/qa/baldr_completion_20261011/root/p08_decimal_context_probe01.json`；未開 DB。完整 snapshot 加總／估值／bp 核驗也仍使用 caller context，已交唯一 owner 補獨立、有界 Decimal 核驗及低精度正負例。Owner 前版 30 PASS 不涵蓋此缺口；新版金融資格尚未 root 接受，成本與 account-aware producer 候選仍續辦。

### F12 supervisor 聚焦更新

Owner 配置探針已確認 PROFILE=test 的來源需位於解析後 `output_root/_test/watchlist/default.json`；不合格舊路徑保持拒絕。小型 supervisor fixtures 為 2 PASS／2.26 秒：create-only regular log 寫入 3,145,945 bytes 且沒有 PIPE，專屬 suspended Windows Job 在 deadline 後清理其五個成員 PID。這些是 owner 小型證據，不是完整 Main／query／保存與 fresh child。舊失敗封套保留；root 審讀另要求 fresh child 改為 bounded log 與相同 owned tree 管理、明示 startup 隔離環境及新的來源 freeze。完整 Main 仍未釋跑，不關閉 F12 Gate。

### P01 query／View 終態與精確修正

Root 沿原 session79511 收取 terminal native exit1：**30 PASS／1 failure／609.08 秒**；八個 source／test raw pins 起訖相同。唯一失敗在 `test_p01_parallel_child_read_round_is_bounded_equivalent_and_keeps_fallbacks`：測試在 strict_page 賦值前比較 DTO，traceback 明示 UnboundLocalError，不能當成產品 reader 通過或功能缺陷。

已保存兩檔 preimage 與回滾表於 `p01_apply_2f16e38ff9ad4d1dbcbd6987b43a1a36/terminal_fix`。Root 只將 capability／strict DTO 完整比較移到 strict_page 賦值後，未刪除 assertion；另將 Worker 新增三行註解改為繁體中文，沒有 runtime 變更。精確失敗 node 重驗 **1 PASS／6.09 秒／native0**，收據 `output/qa/baldr_completion_20261011/root/p01_exact_fix01_9ca2bb8ec2e24cba8033bb28e0e63e38/receipt.json`，八 pins 不變。原全組的其餘 30 項不重複累加，這兩次證據合計覆蓋原 31 個獨立節點；不宣稱同一次全組全部綠燈。

註解修正後純能力＋真 Worker 重驗 **50 PASS／1.34 秒／native0**，收據 `p01_worker03_bf5e91f557a340f48d291351c4095434/receipt.json`；八檔語法 `p01_compile02_28fe736a237743d5b1f3f1317224a76e` native0。量化靜態 guard 兩項通過；它不代替新金融來源的因果與精度核驗。P01 owner 正準備執行中取消與超過八個 artifact 的 outstanding 上限回歸；兩測試尚未 root 接受，完整冷暖矩陣及原300ms Gate仍未閉合。

上一 goal turn 新收取特定 session79511 的終態與完整 failure trace，證據確認下一修正動作，分類為 progress；本輪已修正式測試順序並精確重驗。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持，沒有完整包結案。

### P06 完整封存成本核驗的 caller context 修正

Root 對已提交情境 codec 追加完整 encode／decode 回歸，caller precision 分別為1／3／28，Emax=1、Emin=-1並啟用 Inexact trap。修正前同份合法 frozen payload三例均於 Comparison 成本列加總拋 Decimal Overflow；另純記憶體 precision1探針重現成本比較 ValueError。原205項主要覆蓋 Allocation／估值的獨立 context，未覆蓋這段 Comparison 加總，保留原成功範圍與此次反例。

Root 只將封存成本加總包在 `localcontext(Context(prec=60))`，既有完整結果比較、成本／現金守恆、身份／clock／hash／政策均保留。未讀行情或重跑當下 engine，payload v3格式與算法政策未變；同一封存的 bytes/hash不變。修改前preimage與標準回滾表在 `output/qa/baldr_completion_20261011/root/scenario_context01/`。

精確三例重驗 **3 PASS／0.75秒／native0**；接續八組完整定向回歸 **208 PASS／10.66秒／native0**，不與前輪205或本輪3累加。收據 `output/qa/baldr_completion_20261011/root/scenario_context_final01_a09be89bd3b7459aa10722fbb47c648a/receipt.json` 保存command／UTC／child PID11144、15個source／test起訖SHA，pins一致。兩檔compile與source定向mypy通過，量化guard兩項通過。正常帳本／Health可得時鐘、UI／Main／原來源／EXE／真人及完整P06／M3／G2–G4仍待。

### 產品剩餘範圍與 P01 追加終態核對

Root 收取原 session80658 終態：執行中取消排空與超過八個 artifact 的未完成工作上限兩測試 **2 PASS／21 deselected／130.56秒／native0**，八個 source／test raw pins 起訖一致。收據 `output/qa/baldr_completion_20261011/root/p01_additional_tests01_f19220a90fe2426abc6d657150d8f23a/receipt.json`，child PID32044。正式 query 測試追加後語法檢查 native0；前輪全範圍 mypy 950檔 native0 的12個受核 pins 一致，收據 `completion_mypy01_360becf725a746d1ae57bfc0570ffd34/receipt.json`。這補足前節兩測試待接受狀態，仍不代表正常千檔冷暖矩陣或原300ms門檻通過。

P08 owner 回報 daily／availability 新版38 PASS／223.73秒／session19119 native0；此為 owner 證據，公開 exact checkpoint reader、共用 producer 與 root 完整審查仍續辦，尚未授完整P08／M3。F12完整 Main／fresh child 仍待候選凍結與 root 釋跑。

依原計畫與現況，剩餘工作可整理為六類：完整母體效能及共用查詢；其他資料域與策略定義；正常 UI／收藏／返回／重開；持倉情境與策略獨立帳本／績效；自然結果與維運終態；同版 EXE、Native 與3–5位真人接受。P00–P14全部仍有完整驗收缺口；M1／M2已有有限旅程，M3剩餘實作最多。此分類只供狀態說明，不重定義原工作包、條件或Gate，也沒有可核完整完成率或日曆工期。

### Root 保存與正常讀回審查接續

已核定的15個P01取消／有界讀取、P06完整codec精度檔案與五份操作／架構／狀態文件保存於本機dev `7dba5f82`。Stage前重核兩份final receipt共23個source／test pins全部相符，cached範圍精確且diff check native0；其他owner dirty候選保留，main／push未動。本提交不關閉任何完整工作包。

P08公開checkpoint reader靜態審查發現：用marker的歷史rowset_after比對當下完整rowset，後續合法成交後會拒絕原checkpoint；多次ledger public calls亦各用獨立連線，尚未證明同份read snapshot。已交owner先收session92496終態，之後補真兩日writer歷史重開與same-BEGIN exact ledger候選；新40節點結果即使綠燈，也不涵蓋這兩項尚未補入的契約。

F12候選freeze `96b184032190863d8aeaa97be0539a41a55028a5aa10e06ec3076c8b839c0607` 的58 formal＋5 harness pins由root重核全部相符。新startup audit對任何file URI無條件拒絕；root隔離probe在QA普通DB建立後，以其合法mode=ro URI讀取，取得 `F12 write guard 拒絕未解析 SQLite URI`。receipt位於 `output/qa/baldr_completion_20261011/root/f12_uri_probe_58357112669d401caadff4b9b5c6bc41/receipt.json`，harness raw SHA `7799cca2ae3a29e098cdca1d4781a6f74dedb336a6953d8a551b1a7605c56d1f` 起訖相同。Probe最後stdout受cp1252輸出限制拋UnicodeEncodeError／native1，receipt已先寫入；這是拒絕實證，不稱PASS。已要求owner補精確私人／受核合成唯讀URI及外部／歧義拒絕案例，重新freeze後才釋完整Main；未碰正式SQLite或舊失敗來源。

### P06 策略 Paper 完整帳戶 adapter 候選

新增 `portfolio_research_account_reader.py`，從使用者明示strategy/version/namespace/operation/snapshot與本次aware cutoff讀公開checkpoint。公開reader核完整帳本／clock後才建立AccountState；source hash綁binding、snapshot、base receipt、availability與ledger operation，未收caller hash、不推Health、不猜latest或現金。錯kind／portfolio／snapshot拒絕，晚到availability不能用於舊決策。因果自查及回滾清單於 `root/account_reader_preimages_01/`：沿原exact source及完整Decimal valuation，沒有新行情、公式或writer。

Root首兩輪各為2 FAIL／5 PASS（13.01秒與11.55秒），原因依序為測試引用writer結果不存在的snapshot欄位、valuation不存在的cash欄位。修正為獨立完整現金／NAV／股數／mark／市值與writer available_at數值oracle；原失敗不抹除，未減assertion。第一輪受控runner又在test helper建過長Windows路徑前失敗6 FAIL／1 PASS／0.80秒，17pins一致，收據 `account_reader_final01_ed9847dabcb8435abd6145176a0bf79a`；不是產品來源拒絕。改用既有短隔離QA basetemp後，完整七節點 **7 PASS／10.08秒／native0**，收據 `output/qa/baldr_completion_20261011/root/account_reader_final02_4b1fc7526aa34554a3c1d87d92ea3fb1/receipt.json`，child50644，17 source/test pins起訖一致。隔離state/ledger DB bytes讀取前後相同；source定向mypy、兩檔compile及量化guard兩項native0。

此候選只支援策略Paper source，依賴P08未提交reader；Health、manual/user_declared source、正常UI/Main、原來源、同版EXE、真人與完整P06/M3仍待，不以七測試關閉工作包。

### F12 URI修正的root小型證據

新版startup guard允精確QA/run/synthetic的mode=ro URI並強制query_only，private mode=rw限制QA/run；外部、歧義與未明示uri=True拒絕。Root同款隔離URI probe native0，收據 `root/f12_uri_probe_2049ed31edb6497c94ee25b8f061f268/receipt.json`，harness SHA `29231ffd60a4daab1d7757c01fc33c0849e4b6dc78c3f5a4a618e937f14daf76` 起訖相同，補足前輪誤拒反例。

Root小型六節點native0／6 PASS／2.79秒，但執行中journey test source變更，63 pins核驗不一致，runner因此拒絕接受該freeze。原收據 `root/f12_guard_supervisor01_abdbe981539a4c418149dac0d80d9201/receipt.json` 保留；不稱同一凍結候選PASS。Owner完成修改後重新freeze，root再核及精確重驗；Main仍未釋跑，原deadline及來源限制不變。

### F12 固定來源與最終小型回歸接續

Root 最終小型回歸收據 `root/f12_guard_supervisor02_9e04fba9f9354cff97d2eb86416afa93/receipt.json` 為 **10 PASS／2 deselected／3.01 秒／native0**，63 個來源／測試 pins 起訖相同，涵蓋 URI、環境、Job 清理及查詢期限服從總期限。這補足前輪執行中來源變更的拒絕；完整 Main 與原 resolver 節點不在這十項範圍內。

Owner 的來源重驗曾將 sandbox／長路徑讀取失敗判為三個 bundle 檔案缺失，原診斷保留。Root 改以核准的唯讀程序及 Windows extended path 直接核 bytes：原 `synthetic_main_42f484b9f27b47328b7d268a866cc755` **17／17 檔案 SHA 與大小相符、20／20 目錄存在**；收據 `root/f12_inventory_readonly_c6b32e82ac9a43c39713ae29aba23062.json`，沒有來源寫入。另由正式 catalog 在相同原根執行 native0 預檢：scan complete、唯一一筆可 exact-read、declared count 258。無須修復或重建原來源；已停止替代來源重建，部分 QA 根與失敗日誌保留。此證據解除來源缺檔誤判，仍須最終 freeze 與一次有界 Main→保存→正常關閉→新程序精確重開驗證，尚不授完整 F12 Gate。

本次 goal turn 接續前一輪的來源核驗進展；P08 公開 ledger reader 候選審查另發現 operation payload hash 必須由 repository 自行重算、transition fill order 與 foreign portfolio prefix 必須明確核對。候選尚未套用，不把暫時跨模組私有 schema 讀取當成正式架構完成。

### F12 固定來源 Main v3 終態與診斷缺口

Root 重核 v3 的63個候選 pins，另加入實際載入的 task_cancellation 依賴，共64個；原42f來源17檔與月營收14個來源／sidecar觀測均納入前後守衛。釋跑一次有界正常 Main，收據 `root/f12_main_v3_01_f43c9ac6902e4761b7442febc946a8d9/receipt.json` 記錄 terminal native1；外層測試1 FAIL／11.02秒，內層1 FAIL／6.98秒。Main 初始化完成5.469秒，收藏啟用按鈕 enabled，但點擊後仍為 personal_source_readonly，尚未進入查詢／保存／新程序。所有64個source pins及來源觀測前後一致。

專屬 supervisor 收據 `output/qa/f12_resume_20261011/main_candidate_c29656ee9ab140c0a9f1b6db4066adc7/supervisor-receipt.json` 記錄 owned Job 程序樹已關閉、最後active count為0、沒有逾時終止。這是失敗後程序清理證據，不是完整正常關閉旅程通過。舊log未保存 handler 捕獲例外所在的status_label，因此不能宣稱已定位錯誤；正式COW流程沒有mode=rwc，不放寬guard。接續先補正常頁面導航、可見按鈕滑鼠操作及有界標籤診斷，再以正式元件小型探針追因；不原樣重跑完整Main。

### P08 公開 exact reader 的原始列格式反例

Root 對候選reader以獨立合成帳本實際append成交／transition；只把fill的schema_version改為wrong-fill-schema，重算raw rowset_after及marker hash，沒有變動operation payload。候選read_exact_daily_operation仍接受，DTO重新顯示paper-trade-ledger.v1。探針native0，兩候選source／test pins前後一致；收據 `root/p08_schema_probe_0eb89b8b10d547819d68eb8001156246.json`。這證明目前22項owner候選測試尚未覆蓋原始fill schema的拒絕，不將其當完整reader接受。

已交唯一owner在解碼前明確核對schema，並審查原始SQLite整數／flags／文字是否被轉型掩蓋；新增重封schema負例後再交不可變base/post manifest及patch。正式ledger未套本候選。Owner daily／availability首次47節點回歸在過長basetemp建檔時取得44 FAIL／3 PASS、session78437已native1終態；改短隔離QA路徑後才重驗，不改產品來源掩蓋路徑問題。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍進行中。

### P08 公開歷史 reader 正式套用與 raw schema 精確重驗

Root以同一獨立合成反例重驗新版候選，wrong-fill-schema已被ValueError明確拒絕；native0、兩candidate pins起訖一致，收據 `root/p08_schema_probe_4fb78cb5f2094ec3b52a5d5d1f3c56db.json`。此結果補足前節誤接受，不抹除原反例。

完整審查候選原始schema／SQLite primitive、獨立Context、canonical JSON、既有v1串流prefix、foreign portfolio、operation重算、transition fill order及有界讀取後，root保存working preimage與回滾清單，精確套用兩檔。Packet `root/p08_exact_apply_0d984d2399694dca92b53bcd9a45da49/`；patch SHA `7c639e44b415caa0b74a7aa2045a9aa067bac1e9fe72ff010f2c036c6a8db6dc`，raw post source `b4a9244cf692c038f00b978f752cf5c7996585a8350fc0f8aa03ca0ba86aa07c`／test `aba7f3a7f1e663aa617bab6d7867a050447dc18e1be2ecdd2b10d6f7026dfcd3`，完全等於隔離套用候選。前置與後置量化靜態guard兩項通過；沒有正式資料或既有SQLite寫入。

Root正式import全套ledger取得 **27 PASS／1.33秒／native0**，收據 `root/p08_exact_ledger01_120ba6037854473d822055c11e013a51/receipt.json`，child PID2716、28個source／test pins起訖一致。包括後續成交後歷史買賣／零成交重開、單BEGIN與WAL同snapshot、caller prec=1／Emax=1／Emin=-1／Inexact trap、重封raw schema／REAL股數與bp／錯flag、marker／fill／transition／rowset／foreign prefix及cap拒絕。Ledger定向mypy、兩檔compile與diff check通過；不能與owner同27項重複累加。

Owner短basetemp重驗原daily／availability取得47 PASS／325.16秒／session1897 native0；仍是暫時private ledger reader證據。現已釋availability唯一owner改用公開API，移除重複schema／rowset算法，保留clock／base／source operation拒絕；完成freeze後再由root跑正式ledger＋daily／availability＋P06帳戶reader完整定向回歸。正常producer／成本政策／日曆／benchmark／績效／UI與完整M3尚未完成。

F12小型owner探針取得真可見按鈕／QTest click／Yes確認各一次，仍readonly；標籤為path_preflight_failed，cause為PermissionError errno13／WinError5。Session28079／nested PID34588已native1終態、Job清理後remaining PID為空；來源未變。此與既有sandbox strict resolve誤拒須分開判讀，root待新診斷freeze後用核准的隔離小型probe核原因，不弱化正式custody。P01候選後置guard錯誤原會只寫failed而native0，已交owner修非零退出及純fixture；矩陣未釋跑。完整目標維持active，本輪已有正式code套用及原生回歸進展。

### P08 公開 API 接線與四組 root 整合終態

上一 goal turn 僅回覆剩餘範圍，分類為 no progress。本輪重新讀目前工作樹與 availability raw freeze：source `f9d3e7aceb343dd0d00e5f03fb755f8a7863bdd87a039c0324d884d2f6dafc8f`、test `074cb8d04d26284e66f192f04aceff621d05243d6e08afe878217b8aff9b539f`；owner preimages 在 `output/qa/p08_resume_20261011/availability_preimage/`。Root全讀pre/post差異：移除跨模組私有ledger schema／prefix／row decoders，只呼叫一次公開 `read_exact_daily_operation()`，核 typed bundle、marker、state operation、ordered fills／transition與上層clock。Public integrity errors保留cause並轉為availability拒絕碼；沒有取消state／來源核驗。

Root正式import四組 **81 PASS／246.73秒／native0**，包含ledger27、daily23、availability24、P06帳戶reader7；不與前輪或owner重複累加。收據 `output/qa/baldr_completion_20261011/root/p08_public_integration01_cf99f14a663f4ac7b4fc92dfb0632164/receipt.json`，child PID42924，28個source／test raw pins起訖一致。包含真writer空倉／買賣、零成交checkpoint、跨庫失敗恢復／冪等、後續append後歷史讀回、raw schema與payload篡改拒絕、同BEGIN及一次公開bundle並行寫入後仍讀原結果／下次拒絕、低Decimal context與錯帳戶／cutoff拒絕。

四來源定向mypy native0，收據 `root/p08_public_mypy01_9c596ba956904145b07117ecff3fd69c/receipt.json`；八個Python語法native0，`root/p08_public_compile01_3f659df612424133b88afe1843822468/receipt.json`；兩項白名單量化靜態guard native0，`root/p08_public_quant02_f2ba6a4371414924aeafbe68e9c2e723/receipt.json`，皆28 pins一致。首輪quant wrapper在child已結束／receipt已保存後，打印emoji被cp1252拒絕；原 `p08_public_quant01_ea6f15b338d34c6dbeb862242b29f68d` 保留，重驗明示UTF-8，不將wrapper例外寫成檢查PASS。

驗證期間另一工作保存本機dev `3da61351`，含本輪八個金融source／test與F12 harness；root未執行這個commit。提交存在不授F12新候選或整體驗收。Daily仍為逐庫恢復，saved recommendation execution只核目前canonical config／clock，不授完整P07訊號；quote／成本policy／官方日曆、正常account-aware producer、benchmark／績效與UI／M3仍開放。P08 owner只在scratch盤點公開P07 signal、T−1 preopen volume與原policy／fill引擎契約，不接受caller target/hash代替策略權威。

### P01 final freeze 純核驗與失敗傳播負例

Root明示final manifest path與SHA `4c3691192e6b0bb8c207c52ceef20e842312d23935626fad4dd988992eaa339f`，sidecar一致；純preflight兩次核80個source/runtime file pins、51個實際產品module及594個runtime package/DLL檔案一致，native0／8.56秒。收據 `root/p01_pure_preflight_20c06f0359f64f9b82c51e5736f4a4ef.json`；沒有store讀取或矩陣啟動。

本輪root三個純負例 **3 PASS／6.21秒／native0**，80 raw pins起訖一致，收據 `root/p01_pure_guard01_1ddbe1afdae947dd82c236c64e2f45f2/receipt.json`，child PID9068。實際runner保存post-guard失敗並native1；未列入freeze的金融產品module及放在output的產品module alias皆拒絕。該module負例沿owner已凍結的versioned fixture，沒有拿latest正式來源資格。Supervisor `c6d730f89471ba02f2c7993a4bcdc4a39c1f2f9a1c35cecec73b0f6d65222d6e` 靜態審查尚缺失敗role的PID／Job清理／logs收據、失敗後postguard及supervisor自身漂移拒絕；已交唯一owner補正負例。正常六角色矩陣未釋跑，原300ms Gate保持。

### F12 root 小型 WatchlistView 的下一失敗定位

Root核小型candidate main SHA `cd03151036b5102c224fe522237ca588d9b58260ea29cdf107be1d707dc14de3`／child SHA `32456ac7c5c526c927a9a9c744676f07bdd050d08006562a08012f07200bf2bb`，只替換原64-pin release的兩harness；其他來源及data觀測沿原42f不替代。新release `root/f12_small_probe_root_release_20261011.json` 僅授單一小型node，Main未釋跑。

核准隔離probe收據 `root/f12_small_watchlist01_91de1ff0e9c64e97a4570da3869d5b02/receipt.json` 為native1／外層1FAIL／5.64秒；64 source pins及data前後一致。內層 `output/qa/f12_resume_20261011/watchlist_view_probe_fdc167fa972f45449f7df9de893235b6/` 保存真可見click／Yes各1，status label是 `personal_watchlist_convert_blocked: source_backup_write_failed`；preflight causes為空，已越過前輪path預檢。目標DB未建立、原source SHA不變；view正常close、worker0，專屬Job／root handles已關閉，remaining PIDs空。

測試停在information＋warning必須1的assertion，但正式handler捕獲exception只設標籤並return，兩modal為0符合該分支；不視為modal產品缺陷。Source backup真路徑是os.open→os.fdopen，QA audit目前將integer descriptor當路徑拒絕的假設待小型實證。已交owner補backup cause observer與分支modal oracle；若修fd守門，須以OS實際handle path核private containment，外部／合成readonly source／closed或reuse fd／非檔案拒絕，不能一概放行integer。未改正式COW或放寬資料防護，完整F12旅程仍待。

Owner其後交純descriptor child的具名收據 `output/qa/f12_resume_20261011/fdopen_guard_probe_f7280b3f45954bd6b7ffedeeaa3e1f4c/fdopen-guard-role-receipt.json`。Root直接核收據及supervisor：private regular file的os.open成功但fdopen被PermissionError拒絕，private file仍空；同數字重用、closed fd、pipe、外部及readonly synthetic source皆拒絕，source SHA不變。Supervisor child PID29524／native0、owned Job關閉後remaining PIDs空。此為owner基線反例，補足前節假設的特定guard行為，沒有證明修正或完整COW成功；精確OS handle候選仍待freeze／root review。

### P01 啟動器 v2／v3／v4 的獨立驗證與真啟動失敗

上一goal turn只答產品剩餘範圍，分類為no progress；本輪重核目前檔案並推進凍結候選。Root v2測試7 PASS／1.89秒／native0／82 pins一致，receipt `root/p01_supervisor_v2_01_8c69d089e207449796ad3cc433eaaa62/receipt.json`。一次v2 matrix在首role spawn前拒絕，原因是`sys.implementation.name`的cpython和manifest的CPython表示不一致；packet `root/p01_normal_matrix_v2_01_1450223121824f72827ad21dedba4bdb`保留，沒有效能樣本。

V3改用與manifest/runner一致的`platform.python_implementation()`，追加真正guard正例及錯implementation負例。Root9 PASS／1.84秒／native0／84 pins一致，receipt `root/p01_supervisor_v3_01_176d17d9c762442aa98e9289af06645d/receipt.json`。一次v3 matrix第一role native1，standalone runner無repository root搜尋路徑，import app_module失敗；packet `root/p01_normal_matrix_v3_01_1461e11a0be44a9e9b9222ccd2c9680a`及stderr保留。Job已排空、postguard通過，沒有store內容或p95樣本。

V4僅令child PYTHONPATH固定repository root，不繼承caller；final manifest `4c3691192e6b0bb8c207c52ceef20e842312d23935626fad4dd988992eaa339f`及runner `055669702e0d217957df5380d49532fba90bfd7a2c0f73ed51fb1a67fb466bca`原bytes保持。Root全讀delta及新增測試，以受污染caller環境跑真suspended Windows Job standalone runner --help，再核bootstrap全部51產品origin、80file pins、594package/DLL及四版本；零store內容存取，Main及QApplication未啟動。Root獨立 **10 PASS／6.07秒／native0／86 pins一致**，receipt `root/p01_supervisor_v4_01_a9ddf2c44c314a698052301a57f29b5c/receipt.json`。V4 supervisor SHA `f52a1602e6bc835c9a991e4b84d0849bae591688b04b623dc97bdfb2b4031f26`，test SHA `5d1674a0a4c03e4c819382cd06dc71d58445ebd8b67ca0e6565dd7c71692cbb8`。

Root確認沒有本任務QA競爭程序後啟動一次五cold／一warm矩陣；packet `root/p01_normal_matrix_v4_01_369bed5846674873ab31bacd52562ae5` native1／86 pins一致。Inner `supervised_matrix_attempts/attempt_20261011T104818Z_58b6e6a8b4a4` cold01在`_fixed_store_snapshot`的sealed inventory `os.lstat`碰到長路徑WinError3，cold_metrics及matrix皆空，不能寫成效能不合格或通過。Role supervisor PID50568／runner PID2864；owned Job closed、remaining PIDs空、cleanup errors空，80／51／594及supervisor自身postguard通過。Runner來源樹前／後核驗均停在同路徑，不能由code pins推整份store已核一致。

Root唯讀metadata確認報錯目錄普通path不存在、延伸路徑存在且為directory；這僅支持長路徑存取診斷，沒有證明全store hash。Owner接續new versioned runner／manifest長路徑候選及真sealed store全量預檢，禁止移動、重建、縮母體或略過子樹。原每role600秒、各類30樣本、嚴格p95<300ms、1000母體／20頁及完整DTO序列oracle保持，Main／EXE／真人與完整P01未完成。

### F12 Win32 實際 handle 診斷與截斷防護審查

同一API probe腳本SHA `42456040c15944797edcd5a686723996464490da7665742cb9be7b1a1e6216d5`在sandbox的DOS/GUID GetFinalPath失敗WinError5、NT/NONE成功；root核准隔離新QA根執行相同bytes後，三access modes的八種valid flags全成功。Root receipt `root/f12_handle_api_4465164d84004ff2907a3c22c9e6f330/win32-handle-api-receipt.json`，PID43804／native0，DISK／fstat／Winfileinfo的volume、inode與nlink1一致，descriptor全部關閉。此證據支持保留NORMALIZED DOS(0)精確guard，不採NT fallback；尚非私人副本／Main旅程成功。

候選guard逐次核真正handle path及identity、單連結與private containment。Root另發現write-capable os.open若先O_TRUNC後查hardlink，拒絕前已可能破壞外部別名；已交owner補pre-open／audit existing file link count及os.open／builtin open兩種截斷負例，外部bytes須保持。完整Main仍未釋跑。

### P08 前向觀察候選審查（未套用）

Owner scratch沿真v4 source session／child／parent writer及公開exact reader投影五predicate之一，保留完整included cohort合法UNKNOWN與source availability unknown／historical PIT false。Root全讀候選，要求讀回時source cutoff、parent completed clock逐值綁真public package，重核capture不早於真parent並補重封hash負例；讀檔改有界且各層reparse／hardlink驗證，不先read_bytes全量再核上限。保存時鐘語意亦須精確，不能以preparation clock稱已保存。候選不授完整StrategySpec、帳戶producer或績效；正式P07／P08／M3及完整產品scope保持。

### P01 v5 原 sealed 清冊與凍結後漂移

Root全讀v5 runner相對原runner差異：僅將lstat／scandir／檔案I/O轉為Windows extended path，canonical root、relative payload、排序、identity、reparse與hardlink拒絕均保持。原80 source、51產品module、594runtime及fixed inputs的manifest值相同。Root在manifest `9509fb22782f1bec5a72f54aca0f6a2882010f9de1cc558359aa285f4a4dc7cb`凍結時獨立 **2 PASS／2.84秒／native0／89 pins一致**，receipt `root/p01_extended_v5_01_d3ec4b112ba34af4860330c11c4fa311/receipt.json`。真sealed source共1457 entries（1150 files／307 directories），tree SHA `a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9`、source DB SHA `54ad8d6cdd018cecfc449062edd8ced56ba682b3fde8c86c1bce25d311674f27`與原封套一致；無來源重建、移動或縮母體。

Owner其後同path新增bridge欄位造成9509 manifest變成e4；root要求保留e4新檔並恢復exact9509。Owner依已記錄欄位重建，computed SHA精確等於9509，root目前Get-FileHash已核實；e4另存preimage。新bridge manifest為 `772f77b8d9f7aa479f4e826dbb0456469d66d7578859c1a360215a0f43c8e45a`，但root獨立啟動時發現attempt30 freeze的preflight SHA `88f138ff0c6e68dfbe1fe9a63d33ad649fd30e1baca3d5680c01d88962b92be7`與現檔 `b6bc82f926874ccf6393f60c9a43817c4aa671dec32298571d9588249621dbae`不同，於產品／store前停止。該停止沒有pytest／matrix樣本；已要求唯一owner新filename與新freeze，不能把已凍結候選原地改寫。原300ms、五cold／一warm、每類30samples及完整DTO oracle不改。

### F12 descriptor 私人正例與 alias 夾具失敗

Root審查pre-open nlink1／private containment及每次真DOS0 handle、Winfileinfo／fstat identity候選；freeze `be682af87e765785e46a44270789648fa5c09b0e5b8d6733eea7685d600279d5`，harness source `5f8ae9f30c84f39d3d2acf1d5552d6a7767b19767d709014674ca47a78327005`、child保持 `32456ac7c5c526c927a9a9c744676f07bdd050d08006562a08012f07200bf2bb`。首root attempt忘明示F12_SYNTHETIC_ROOT，在child前1FAIL／0.91秒；收據完整保留。第二attempt明示原42f來源，receipt `root/f12_descriptor_preopen_02_cc9ec1499f5a476ea989c533a21157a9/receipt.json`為 **1FAIL／3.60秒／native1**；64source pins與17檔／14sidecar觀測起訖相同。

Inner `output/qa/f12_resume_20261011/fdopen_guard_probe_73ecba9a56d44ff297c81efaee38f6d6/`真private writer成功且bytes一致；外部／readonly source／closed／同fd數字reuse／pipe皆拒絕。預先開啟的hardlink handle、os.open O_TRUNC與builtin open wb都拒絕，外部檔bytes與SHA不變。唯一失敗是os.symlink缺權限WinError1314，未真正建立alias，不能宣稱reparse負例通過。Launcher PID46396已native1終態，owned Job／root handles閉合、remaining PIDs空。下一候選改新私人目錄junction，不skip、不移除alias斷言；小型COW與完整Main尚未驗。Guard-only release需明示未授Main，舊base繼承的true旗標不能當新授權。

### P08 前向觀察來源鏈的 root 獨立驗證

上一goal turn只答進度，分類no progress；本輪root重核現工作樹、完整讀凍結候選與八項測試，manifest SHA `a9634ca5815ef73dca5f570ce0a587ed2d0c9eb3485d1c4027b1ddac492f5c7e`。候選source `c9d67dd6ad5c28c0595a9bd6c51a7072bac7eeb253b623c059968e44554a600d`、test `e53aba44b8e19f8a6a78034218dfebcd6682f1fadae29245b1a01849a109e47d`。Root guard保留前輪28財務／UI pins，再加入候選及19正式技術source/test依賴，所有raw pins起訖一致。

Root01沙箱在.t.resolve(strict=True)被WinError5拒絕，8個setup errors／2.54秒／native1，未進來源；receipt `root/p08_forward_root01_3b1771175930482a871e2a6f544cbd8e/receipt.json`保留。核准相同bytes的工作區隔離測試Root02取得 **8 PASS／0 skip／8.99秒／native0**，receipt `root/p08_forward_root02_87ba28556269405e811dda66b0a46e6f/receipt.json`，launcher PID41036終態。包含真v4 read session→child／parent writer→公開exact reader→新觀察保存→fresh reader、完整included UNKNOWN、重封訊號／重複成員／cutoff與parent completed clock、naive／晚到／foreign universe、caller score禁止、junction／hardlink／2MiB超限拒絕與hostile Decimal context。

新程序收據 `output/qa/p08_resume_20261011/forward_signal_candidate/fresh_source_reader_receipt_32124_27568.json`記PID27568／exit0，保存與重開signals相等（2330 unknown、2382 match）；來源SQLite SHA before=after=`c1a7c08dcbd925e64d84875470a06da399a8b2116f95bf3b4e1798b8fd12bc05`。此為隔離synthetic source經真正式來源API的證據，非正式市場來源或交易績效資格；source availability unknown／historical PIT false保留。候選尚未套正式module。下一包須有完整版本卡、entry／hold／exit／unknown政策及typed executor、exact account daily route與原金融引擎；完整P07／P08／M3與所有產品Gate維持未完成。

本輪文檔coverage／preimages／回滾packet為 `root/forward_and_descriptor_docs_944bd7b90d8b4fa29482d88c6c8cb39c/`；沒有產品UI／架構行為變更，Manual／Roadmap／Index無需新增流程。原資料、失敗QA、其他writer及main／push／發布邊界保留。

### P01 v5 新 final 獨立通過與唯一矩陣啟動

Owner保留88 preimage、新名b6 preflight，另發final freeze `7d31f9434a63f4a478aff510f10c1bbed8a6acf4d27f80e47f96fa37b5f90736`；root全讀delta僅新增parent product-path map與fixed-input equality核驗。Supervisor v4→v5僅變manifest／runner／自身檔名與fixed identity，Job、deadline與operation protocol不變。Root獨立 **12 PASS／10.95秒／native0／99 raw pins一致**，receipt `root/p01_v5_final_root01_dbf6e3641549425db911a82a675e10ed/receipt.json`，PID50580 terminal；包含full sealed store、真standalone help／bootstrap、assignment／resume／timeout／postguard收據及精確runtime。不是原10項與新增2項的重複累加。

新名preflight獨立native0，receipt `root/p01_v5_final_preflight01_a75db7c34364465aa420f6d66c93af38/receipt.json`，PID42160 terminal；80 source/file、51 product origins、594 runtime/DLL及四版本相同，store內容存取0，99 pins一致。Root通知兩owner停止QA，已收到無QA／新subprocess確認；host唯讀盤點只有其他專案risk-lab Python程序，未停止或修改它們，因此不宣稱整台機器完全無其他負載。

Root釋出並啟動唯一一次完整矩陣，session49268／launcherPID1180，packet `root/p01_normal_matrix_v5_root01_18aa1514b6b248d099032a933a97d6fb/`；inner `supervised_matrix_attempts/attempt_20261011T110425Z_a2cdc0776321/`。本段記錄時仍execute_role:cold_01，外層handle已實際poll確認live，尚無native終態或p95。五cold／一warm、每role600秒、1000母體／20頁、各操作30samples、strict<300ms及完整DTO serial oracle保持。後續依同一handle收終態，不因觀察逾時另起矩陣。

F12新freeze `5e78321c1a7a060498feafea029b7e1d42e33c40b33d29d0100572bcc0669ebd`（main513745c6、child32456ac7）已靜態審查與64-pin核對；root純guard release `f12_junction_guard_root_release_20261011.json` SHA `24c30fa4ab210fce34ebae329ba80c9724ae2c5863270fdb59489d53ec4e17b8`明示released_for_one_Main_attempt=false。尚未跑descriptor、COW或Main；待矩陣terminal再按相同freeze接續。P08 owner於scratch做完整策略卡／executor／daily route，保持已凍結依賴不變。

### P01 v5 完整矩陣終態：cold01 到達原期限

上一goal turn已poll同一session49268並確認live，分類為verified wait。本輪再次poll同一handle後取得native1終態，沒有重啟矩陣。Root packet `root/p01_normal_matrix_v5_root01_18aa1514b6b248d099032a933a97d6fb/receipt.json` 保存99 raw pins起訖一致；inner `supervised_matrix_attempts/attempt_20261011T110425Z_a2cdc0776321/supervisor_receipt.json` 在cold01達600秒，由專屬Job終止owned tree。

Role rootPID3844、截止前Job成員3844／28700／29812；Job與root handles已閉合，remaining PIDs及cleanup errors皆空。80 source/file、51 product origins、594 runtime/DLL與supervisor postguard通過。兩個role log為0 bytes、沒有result.json／oracle檔或p95；不能由空log判斷停在open、selection或page讀取，也不能由三個PID推為artifact reader程序。既有sealed store全清冊是啟動前證據，本次強制終止沒有runner來源post-inventory，不能由程式pins代替來源全樹證明。下一版增加原子phase與有限stack觀察，保留1000母體／20頁／完整serial DTO oracle、五cold一warm、600秒與strict<300ms，不直接提高期限或縮小範圍。

### 正式前向規則來源 API 整合

Root先保存Coverage／回滾與候選raw preimages於 `root/forward_formal_adoption_ecb2e49e834a4992a1bcfa101d514355/`，以create-only新增 `app_module/strategy_rule_forward_observation.py` 及 `tests/test_strategy_rule_forward_observation.py`。沿原candidate c9d67dd6／test e53aba44，只有繁中說明、正式import、型別驗證明確分支及非空bool、fresh reader60秒精確kill／wait與receipt搬到ignored QA根；原candidate與19正式技術依賴保持不變。型態檢查首輪23 errors、第二輪5 errors完整保留；在前次測試native terminal後才修改正式source，沒有凍結期間覆寫。

最終source SHA `9c02bce9b80797eab62433f1468a1db0e908950a6e758fac9f3d3e46af4420a7`、test SHA `b641e8e2083926f237cf76dbf65b4e31ad00c1871207740b6046f43354001bdb`。Root正式匯入 **8 PASS／7.84秒／0 skip／native0**，receipt `root/forward_formal_v3_root01_68efbce9b940415b8a6bf86607f7c368/receipt.json`，launcherPID37036終態，53 raw pins起訖一致。不與原候選八項、前兩次正式測試重複累加。新程序收據 `output/qa/strategy_rule_forward_observation/fresh_source_reader_receipt_18744_31532.json` 記childPID31532／exit0、2330 unknown／2382 match與保存相同，來源SQLite before=after=`c1a7c08dcbd925e64d84875470a06da399a8b2116f95bf3b4e1798b8fd12bc05`。

最終mypy native0 `root/forward_formal_v3_mypy01_6b00b18f9cb74266a2281afd5d524087/receipt.json`；兩檔語法native0 `root/forward_formal_v3_compile01_f7ce87ab0b66461cac72a1cd58ab207f/receipt.json`；兩項白名單量化guard native0 `root/forward_formal_v3_quant01_6912ca0a78704c90bb8582673a541658/receipt.json`，均53 pins一致。白名單guard沒有涵蓋新module，來源時鐘／未來資料拒絕依完整八項與root review判讀。

追加既有v4八組來源回歸首輪 **91 PASS／20 FAIL／40.43秒／native1**，receipt `root/forward_source_regression01_49d88191a5ec48d88e671d5764e703fd/receipt.json`，53 pins一致；失敗集中在runner將basetemp放`.t`，無research_scope的舊測試producer依既有允許根契約拒絕`technical_snapshot_v4_isolated_output_required`。原失敗保留，僅以新wrapper改到既有允許的output/qa重驗，正式producer／既有測試沒有修改。

此正式API只授前向研究觀察、完整UNKNOWN、exact來源重讀，source availability unknown／historical PIT false／execution及performance false保持。完整版本卡、entry／hold／exit政策、typed executor、原金融引擎normal daily route、官方日曆／成本／benchmark／績效與正常UI仍待；P07／P08／M3及完整產品Gate未完成。

### F12 junction fixture 第二輪審查

Root按freeze5e78321c與main513745c6執行三個guard／branch節點，receipt `root/f12_junction_root01_ffbaefcc1a644b5a9ef586d655e18877/receipt.json` 為 **1 FAIL／2 PASS／3.71秒／native1**，64 pins及原17檔／14sidecar觀測起訖不變。Inner `fdopen_guard_probe_e0b216ccc52a4bf8940c3d0206505cc8` launcher2196自然native1，ownedJob／handles閉合、remaining PIDs空；junction流程之後仍引用已移除的private_sha_before_reparse，NameError使role receipt未完成，不宣稱junction通過。

Owner保持513745preimage並修新main9fe5dac0；freeze9778fa22的test_files已更新，但pin_inventory仍引用513745／舊size，root新prepare在pytest前拒絕兩份清冊不一致。沒有guard、COW或Main新樣本；已要求保留9778原bytes、另建一致的新freeze，不略過inventory equality。完整COW、Main保存／關閉／fresh reader仍待。

### 本輪來源回歸與 F12 私人副本獨立通過

相同八組來源測試僅改basetemp到producer既有允許的output/qa，取得 **110 PASS／1 skip／51.76秒／native0**，receipt `root/forward_source_regression02_f9f67d0f18374548bffd1ad5b9c67aac/receipt.json`，launcherPID33812終態，53 pins起訖一致。具名skip原因補查 `root/forward_source_symlink_reason01_6edfce9eda544245804bc8cfa2bc0d56/receipt.json`：原artifact symlink fixture因WinError1314無權建立而跳過，不視為該拒絕案例通過。正式新觀察API自己的八項維持0 skip，兩者覆蓋不互相替代。

F12 owner新freeze `14e3d64317aa542819b90f14c30976e665b35bf5a8399057d6e2fac034499b45` 保持main9fe5dac0／child32456ac7，64-pin aggregate `a747590f769ec24036697b38d096fb10df74acafcc00b5be93730f525aa6cc69`；root重新逐列比原base＋本輪Main差異，完整inventory與test_files相等後建立新guard release `e381a25bf040dee0e39f59206aec5166feeda7f2921a8a2da5ef7060d60c92a5`，仍未授Main。Root獨立 **3 PASS／3.52秒／native0**，receipt `root/f12_junction_pinrefresh_root01_364dd270767f4c58859a7abe8a903dbb/receipt.json`，64 pins及原來源觀測前後一致。

Inner `fdopen_guard_probe_a87335dd431e4c14a9f52a841f3fdb22/fdopen-guard-role-receipt.json` 全部assertions為true：private DOS handle writer及exact bytes、external／readonly source／closed／reuse／pipe拒絕、兩種hardlink截斷pre-open拒絕且外部bytes不變。實際junction創建成功、alias寫入被拒，target SHA在before／after-attempt／after-cleanup皆 `fc1c6f1bdd46318f9ed5e7b0d65bed6f56bc2b8d99dc53efdda0b8319891f952`；alias已非遞迴移除而target存在。Create／remove各自owned Job的PID31736／50900均native0、handles閉合、remaining PIDs空。

按同freeze釋單一小型COW release `fd971d4dc7e3a9fa07b562737d698f6f9c2cb321f1b75d268a4fea50a8ae99cf`，Root **1 PASS／8.37秒／native0**，receipt `root/f12_small_cow_junction_root01_39caa64443a64a939a419182484a04d0/receipt.json`，64 pins及來源觀測不變。Inner `watchlist_view_probe_154961274ee04880898444a5ed0bb3c0` 真可見WatchlistView按鈕QTest click1／Yes確認1／information1／warning0，service repository active；新私人target在run root、SQLite v3 ready、query_only true／write_blocked true、active reader成功，原source SHA未變。Worker34208 native0、registry排空及owned Job／handles關閉、remaining PIDs空。這是私人副本啟用證據，完整營收query與收藏fresh reader仍另驗。

Root核上述COW三份inner receipt、當前64pins後，建立唯一一次完整Main release `f0aef1f2238bc3112f88bf2380091b031171f444ad09e8b3a2e0662aaa2f7a48`。Session15138／launcherPID47352，packet `root/f12_full_main_after_cow_root01_23779aee1cb14e11b4a1fac9967fc4a6/` 已啟動，記錄時尚live／沒有終態。原42f來源與258完整cohort不換，worker2400／Main init600／fresh subprocess600／fresh init540／query min480remaining為防失控上限，不當產品效能門檻。後續poll同handle收結果，無新EXE／真人或完整Gate驗收。

完整Main同一session15138後續poll取得 **1 FAIL／25.97秒／native1**，receipt `root/f12_full_main_after_cow_root01_23779aee1cb14e11b4a1fac9967fc4a6/receipt.json`，64 pins及來源觀測起訖一致。Inner `main_candidate_6f6597e4d85e422d8e707e90739e0b84` launcher17792、active count0／tree closed／root handles closed，未逾時。Main QApplication／theme／真正MainWindow全部初始化完成，私人副本啟用後，在「核驗雙來源並執行全母體查詢」停止：`monthly_revenue_yoy_index_v1_source_archived_open_failed:PermissionError:fdopen_must_transfer_descriptor_ownership`。

Root靜態沿真source archived路徑核 `data_module/fundamental_read_snapshot.py` 的2445／2903：private封存writer使用os.fdopen(..., wb, closefd=False)，以caller保留fd供flush／fsync／close；現QA guard在write mode強制closefd=True。此是guard與正式writer生命週期契約的下一停點，不據此宣稱產品讀取缺陷。Owner接續exact actualhandle／private regular nlink1／descriptor ownership候選與closefalse正負矩陣，不放行外部／hardlink／reparse／closed／reuse／pipe，也不改正式fundamental reader、縮母體或略過保存／fresh child。完整F12旅程未通過；root現無live QA，後續新freeze審後重驗。

### P01 v6 停點觀察工具獨立審查與故障紅測

上一goal turn只回報補完狀態，分類no progress。本輪重新核工作樹與葉片狀態後，完整讀v6 observer及正式reader簽名。Manifest SHA `9c83dce562acea8b60b213a6868b579f96cd761974d9d071d194a75be4136701`，helper `f1d90c40dc57492917c97781564ea9d3fa395f9e099400182cc30b977a95bee1`、runner `a1fcac9c4141ccd19c632ecab33317c10cbe6d3baa8de5f0e4e7d6170e6ebe62`均保留；沒有啟動runner、Qt／Main或讀sealed store。

Root獨立純工具 **3 PASS／2.06秒／native0**，receipt `root/p01_phase_v6_pure_root01_b8d659944a584343a990026db8bf8b38/receipt.json`、launcher46232終態。完整15個候選／正式依賴raw pins起訖一致；只證有界history、短stack與正常watchdog停止，不授真reader wrappers或全矩陣資格。

Root新增兩個QA-only故障紅測，實際得到 **2 FAIL／1.89秒／native1**，receipt `root/p01_phase_v6_red_root01_fb64ce22db4d4cb5bcdb611f8c55ea33/receipt.json`、launcher35544終態、同15 pins一致。第一例注入snapshot writer RuntimeError，背景執行緒停止而operation仍完成；第二例先真停止watchdog再注入stop=False，operation仍完成。兩例都因呼叫端沒有收到應有RuntimeError而失敗；未建立失控執行緒或讀取產品資料。Root test SHA `fe43b476e3eb97ef724542577965121cdb219ca7f98930cf120f16e01a17f237`，wrapper SHA `50a701adc5414d40b3bb68c5d764177a3643d9ce3914316698998e8c3e38b9c1`。

已要求另建v7，保留v6全部bytes：故障必須傳遞且排空失敗具名，補最長有界context／多stack與真小型writer→reader的baseline／instrumented完整DTO、issued能力、UNKNOWN、fresh來源拒絕及異常還原。v6收據對v5誤稱sealed-input postguard通過，亦須在新版本更正；v5沒有runner store postinventory，正式source／runtime postguard不能替代它。原1000母體、20頁、五cold一warm、30samples／類、600秒與strict<300ms保持，尚未放行下一完整矩陣。

F12 safe-dup候選與P08完整策略路由仍在owner scratch，未凍結、未執行QA。Root審查要求F12 constructor若已閉dup再重用其數字，cleanup須核當前handle身分，不能誤關新descriptor；P08 hold_unknown須在target construction中保留原quantity，不能由等權再平衡間接成交。這是待驗要求，不宣稱候選修正或產品完成。

本輪coverage／preimages／回滾packet為 `root/phase_v6_root_review_20261011/`。產品UI／Manual、架構、Roadmap方向與Index入口未變；完整補完範圍保持。兩輪root QA均terminal，沒有root live runner。

Root隨後以原v5 frozen wrapper／測試執行一次 `test_full_sealed_store_preflight_matches_all_frozen_hashes`，取得 **1 PASS／6.78秒／native0**，receipt `root/p01_sealed_after_timeout_root01_2c75a649318f44a288e0fdc3de2975a4/receipt.json`、launcher46096終態，99 raw pins一致。重新唯讀核全部1457 entries、sealed tree SHA `a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9`與原DB／inventory hash相同。這是逾時之後的新時點核驗，不能改寫原v5不存在runner postinventory的事實；沒有新matrix／p95或Qt旅程。

### P01 v7 草稿靜態審查：後檢與 helper 載入界線

上一goal turn已有root故障紅測與全清冊核驗，分類progress。Root本輪讀v7草稿與正式reader簽名、保存三份raw preimages並做AST比對，packet `root/p01_v7_static_d07cb9a2b4204f5695accc207a36f0c9/receipt.json`。當次v7 source SHA `a04f3e37307a16ccbc7d5188cd2a4a3be3c486cae850c8236e56566c38ebf53b`，不是最終freeze。兩個計時函式 `_click_and_measure`／`_configure_and_click_and_measure` 與七個矩陣常數在v5/v6/v7 AST相同；不外推成全runner等價或新p95。

當次草稿helper先在21行匯入，28行之後才查origin/hash，且hash仍為placeholder；還原失敗在1686行直接raise、1688行才定義postguard，會跳過來源／runtime／store後檢與result持久化。已要求新版以canonical sibling核raw bytes後compile/exec，拒絕wrong-origin／wrong-SHA前不能有sentinel副作用；cleanup逐項嘗試restorers、postguards與保存收據，最後具名回報，保留primary exception。Initial observer的restore亦須按replacement identity核對且不因單項conflict漏還原其餘項。Owner已接受並接續補純loader／restoreconflict測試；此時尚無新freeze、QA或完整矩陣放行。

靜態腳本首輪只在console輸出繁中JSON時因cp1252 UnicodeEncodeError停止，當次raw/receipt已保存於 `root/p01_v7_static_5cf64bdb0bc846639e1ed00f841617f1/`；UTF-8輸出重驗相同分析取得native0並保存上述新packet。兩次都只parse AST，沒有執行candidate或匯入產品／讀store。F12仍在owner完成safe-dup lease／cleanup與新freeze；P08仍在修hold/UNKNOWN固定quantity、來源日曆可得時鐘及正常多策略daily route。完整產品與M3 Gate未完成。

Root續讀F12尚未freeze的lease helper，發現constructor例外事件引用不存在的duplicate_record.path_role，會以KeyError覆蓋原TypeError；已要求在凍結前修為核驗後的record或實際duplicate_role，原未凍結source preimage及review JSON保存於上述packet。尚未據此執行guard／COW／Main，也未改正式fundamental reader。

### F12 owned duplicate 凍結候選的事件範圍審查

上一goal turn為進度回答，分類no progress。本輪root完整讀9fe5→86ec候選diff，新freeze SHA `15b25ea8cabc324b47f31922b6cb8cbf765667ecba4745507c6eff46f9f489c5`，Main test SHA `86ec737352a2dc205a1c7b2cbb1c17a6b4b3984e433e924024ce1e09cf31d944`。原constructor事件已改讀validated record，lease／fresh DOS handle／Win file identity核驗的cleanup保留caller及重用descriptor。

Root另發現測試在全部案例結束後從constructor_event_start往後反向取最後cleanup，會取到後來descriptor重用案例，而不是原constructor失敗事件；早期正確事件其實已存入closefd_false_constructor_result。已交owner改用該封存事件並綁每案例事件範圍，保留原freeze／失敗證據、不改正式reader。此候選未放行pytest、COW或Main。

獨立raw SHA／size／AST審查收據 `root/f12_owned_dup_static86ec_root02_4d6d5a84e8964b36a876fdfd12c3aaf4/receipt.json` 為 `static_rejected_cleanup_event_cross_case`：64 pins及10個source snapshot／preimage／diff／來源清冊artifact均核相符；只有Main test pin改變，其餘63不變。原17檔來源與14筆monthly觀測去重後23個路徑起訖期待一致；此為唯讀靜態核驗，不是執行旅程證據。Root審查腳本首輪因candidate多了size metadata而整份monthly row相等斷言失敗；核實只有8列新增size後，改為逐項比較原path／SHA／present並另核所有新增size，沒有放寬來源契約。

Coverage及回滾清單在 `root/f12_dup_review_20261011/COVERAGE_AND_ROLLBACK.md`；QA與Snapshot preimages在上述收據packet。Snapshot仍正確記完整F12待驗，產品行為／Manual／架構／Roadmap與Index未變。P01 v7與P08完整策略路由仍由原owner續辦，完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4保持。

新版event-window freeze SHA `7b9630e3bb1d87c7781c8de95a5f4e75eb5fae38867a3056838659ce70d2fdae`、Main test `87a4852bbe83821bc32921ae79be6ae0996d1a3bd6129faa232558d8aa863628`；Root獨立核64 raw SHA／size、aggregate `f34d7e2c5b782887494132234870f892a9b0d8bbda2c46b54ae1444b6f39fcaa`及11個artifact pins，原17檔／14筆來源觀測仍一致。AST除write guard／收藏觀察event projection／descriptor fixture三個頂層函式外，其餘42個頂層函式與9fe5完全相同。`root/f12_owned_dup_event87a4_root01_54519c01f2ba426684cc21751035e7a1/receipt.json`保存來源／文件preimages及純guard release；未授COW／Main。

Root第一次同版三節點為 **1 FAIL／2 PASS／8.57秒／native1**，packet `root/f12_owned_dup_guard_root01_5ea4846f7f1746ca9b5da9911c270208/receipt.json`、launcher45176終態，64 pins及23個去重來源觀測起訖一致。Sandbox hardlink setup遭WinError5拒絕，未進descriptor cases；inner launcher37164原生1、Job排空／handles閉合，不能稱已驗hardlink負例。

同freeze改由host執行隔離案例，實際取得 **1 FAIL／2 PASS／3.73秒／native1**，packet `root/f12_owned_dup_guard_host_root02_ace771f4fb3247b5aaa87431ec1c360d/receipt.json`、launcher29464終態，64 pins及來源仍一致。Inner `fdopen_guard_probe_7cd156b08895496193d4e4f123144acf` launcher19368在60秒原期限內自然1、active count0／remaining PIDs空／Job及handles閉合；測試在4423行 `len(descriptor_records)` 發生NameError，因dict是guard installer的local而fixture不可見。當次沒有完整role receipt，不授descriptor矩陣／COW／Main成功。

已交owner保留7b963原freeze，改以持鎖、僅回傳整數的QA-only唯讀record count getter，禁止曝光／移交descriptor dict或handle權限，並靜態核新closure引用。P01 v7另外補runner diagnostic writer故障不得遮蔽primary及loader測試OUT宣告；P08需由真normal producer的ledger fills證明hold／UNKNOWN原quantity保留、多strategy namespace隔離。此輪不是重跑逾時程序，兩次root QA皆已取得終態；完整Gate仍待。

### P01 v7 同版真 reader、程序管理及新完整矩陣終態

上一 goal turn 核得當次新矩陣五 cold role 的具名收據，分類 progress；本輪取得原 session30083 的 terminal/native1，沒有因觀察逾時重啟。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍維持。

固定 v7 manifest SHA `75a6db87bca478d8c03b5bc945278978aff39cdea60205a3a6755339ab6c80c2`，runner `39483ae750618f5858a0fe149964a0b3a539e6fc8b1f2f35b056db5639f3994e`、helper `f6d8a4c961013631da97c38302b5f52605f0ad20c85d67680afacb012cce6ca8`。Root 靜態讀 loader、restore／後檢／failure writer、真 reader 整合案例及 preflight／supervisor 增量，保存於 `root/p01_v7_frozen_review_f0fef364885b4c8cac62aa96e9daa406/receipt.json`；104 pins 核相符。兩個 timer 函式與七個矩陣常數仍與 v5 AST 相同，不能據此宣稱新效能通過。

| 同版 root 實際驗證 | 結果與界線 |
|---|---|
| v7 候選測試 | sandbox 12 PASS／1 ERROR／4.37秒，私人 fixture 的 strict resolve 遭 WinError5；host 新封套 **13 PASS／8.90秒／native0**、104 pins 不變。`root/p01_v7_candidate_tests_host_root02_21660be06d1642919cf7dd76e69f60dd/receipt.json`。包含真 writer→public reader 完整 DTO、兩 artifact 併行、真 issued cancellation capability、coordinator callback 與 raw source 損壞拒絕；不累加 sandbox 重複案例。 |
| 純 preflight | **native0**、80 source／51 product modules／594 runtime package files、Python3.11.9／PySide6 6.10.1、`store_access_attempt_count=0`；104 pins 不變。`root/p01_v7_pure_preflight_root01_e37476b39b204266b883c82fbb0afe7f/receipt.json`。 |
| v7 真 Windows Job／失敗收據 | root 從原 v5 failure tests 派生 v7 精確 supervisor 路徑；首輪9 PASS／1 FAIL／5.93秒為沿用 v5 bootstrap hash。獨立 AST 展開 v7 bootstrap 原文核新 SHA `30048173174b33a000179e19a522ead338e798f304c3cf5afb336d92efd20965`，只改派生測試該期待 hash；新封套 **10 PASS／10.41秒／native0**、107 pins 不變，`root/p01_v7_owned_supervisor_v2_root02_fd1f294d724840dd8fe3f3ec3da506b9/receipt.json`。保留 timeout、assign／ack／resume failure、primary failure 與 cleanup assertions。 |
| 原規格六角色完整矩陣 | attempt `attempt_20261011T121108Z_5e9bae30c9ac`：**五 cold 全通過；warm_01 自然 native1／46.724425秒**，非600秒逾時。暖操作第一個 sample 的 `record→_assert_capability_claim` 發生 `read_page_capability_claim_count_mismatch`，matrix為空 dict，**沒有有效暖操作樣本或 p95**。各 role 來源／store／程式後檢與 observer restore、shutdown 通過，Job 排空；outer native1、110 pins 起訖相同。 |

Root 對六份 result／role receipt及 supervisor／outer原文另存獨立封套 `root/p01_v7_terminal_review_04cb319835774434992a13c5dcd3c327/receipt.json`，SHA `53c8dd08f5e8f8d0c67bd27137beb65f0f6660a55aeff0973a6419aad824f141`。五 cold 皆完成20頁及完整序列 DTO核對；程序啟動到首頁 nearest-rank p95 為 **21.0448914秒**，與暖操作300ms Gate分開。暖 failure role 沒有 supervisor result_sha256 欄位，root只保存與自行核 raw hash，不冒稱該欄存在。收據整理工具初輪 deep-copy路徑 Win206、以及 cold status／failure schema期待不符的停止保留；僅修 root 讀取與封存工具，未重跑矩陣或修改產品。

v5 600秒失敗無 phase／stack／result，精確停點仍未知；新 v7 的 cold 通過不能倒推 v5原因。Owner 新 v8 scratch僅重用page0重複oracle，未採納、未跑QA；當前優先診斷新暖操作claim次數，不放寬能力核驗、N=1000／20頁／五cold一warm／每類30 samples／600秒role或strict p95<300ms。完整P01／EXE／Native／真人仍待。

### F12 唯讀 count getter 的實際通過與完整 Main 新失敗

新 freeze SHA `ba3f1beba403d8d96404c37c9cd5d14b45e7e520c4ada779f8a1ac142f072fd3`、Main harness `5c739885de4acf481f91e992960c86a6858bbd4aa508a15251c6ae952819bb5a`，child仍為 `32456ac7c5c526c927a9a9c744676f07bdd050d08006562a08012f07200bf2bb`。新增持鎖的唯讀 integer count getter，fixture不再引用 installer區域dict；64 pins／23個去重來源路徑及候選artifact核相符。Root static收據 `root/f12_count5c73_root01_f08c990824e84b6ea82ef2f9127badec/receipt.json` 的 unchanged函式count顯示43包含新增getter；精確判讀為原基線 **42個頂層函式未變，加1個新getter**，不是43個舊函式未變。

依同版 guard→小型COW→完整Main順序，各階段使用新release：

- guard三節點 **3 PASS／3.26秒／native0**；`root/f12_count5c73_guard_host_root01_04300a98cf9d4682a0f82e756946e08d/receipt.json`，inner37 assertions全True、descriptor records0、Job排空／handles閉合。
- 小型真WatchlistView click／Yes私人COW **1 PASS／8.55秒／native0**；`root/f12_count5c73_cow_host_root01_dfe78b7190084e45aba8857d0c3925ef/receipt.json`，click1／Yes1、private schema3、query_only及write-blocked、active service讀回、source不變、worker0及Job排空。
- 完整Main **1 FAIL／27.31秒／native1**；`root/f12_count5c73_full_main_host_root01_37f7fbab3a4e4aa8ad7997b5999e43f7/receipt.json`，inner `main_candidate_372fdbe0fe074fb7861c5f6505e82869` 的child29652自然1、未逾時、Job排空／handles閉合。Main各初始化與私人COW完成，query在5427行因 `monthly_revenue_yoy_index_v1_source_archived_open_failed:PermissionError:[Errno13]F12writeguardblocked:outside_allowed_private_root` 失敗；完整收藏／下鑽／新程序未完成。

上述三階段64 pins與23來源路徑前後均相同；原closefd=False及getter NameError失敗亦保留。現有收據不足以指出 query期間是哪個audit event／path拒絕；正在另建query事件window及finally create-only診斷候選，不擴writable roots、不修改正式reader／原來源／child。完整F12 Gate未閉合。

### P08 v2 凍結候選的 root 靜態拒絕

Root 獨立核 manifest `d5795a909c60d90ec32c59fb263fd25eec36cccf5d946d07dc12785c330dfb41`及dependency manifest `f5ef35df38e80f51e41d197fa49952705a6ce216c53aa04870a27ca83028ac87`，43個去重raw pins全部相符；只讀候選、正式construction公式及AST，**未匯入／執行候選或跑QA**。封套 `root/p08_v2_static_root_533bab710cef4665835908ce4b99c2b7/receipt.json`，SHA `d51b481b39c60efcd83a0f2edb6b4cf18072ca4efacf729e3fcc4477b3fe7f73` 保存五份來源preimage。

拒絕點：producer第4779行使用未匯入／定義的Context/localcontext；daily候選接正式availability而新增execution receipt欄位的候選接線未完成；空倉且無新entry日因空source evidence被拒絕，未有合法零成交checkpoint；完整batch Decimal context隔離與真policy／fills下hold／UNKNOWN quantity保留未證明。另multi-entry純target test的15%公式錯誤：124000入場預算每檔上限18600，price8／lot1000應各2000股、兩檔純target residual268000；原9300／1000股／284000期待與正式construction公式不符。

Owner在獨立p08_v3修正，v2及正式檔維持；第二個不同家族KD策略、完整normal producer／雙namespace／真ledger、benchmark／績效／UI仍待。Coverage與回滾依 `root/p01_v7_review_coverage_20261011.md`：只同步QA／Snapshot，正式行為與Manual／架構／Roadmap／Index入口未變；保留所有原資料及其他writer dirty內容。

### F12 query 診斷候選的 root 審查與實際終態

上一 goal turn 核對並回報剩餘範圍，未改 authoritative state 或執行驗證，分類為 no progress。本輪接續已凍結 query 候選，未重跑已消耗的舊 release。Freeze SHA `c77b0f7be4689badd1537086a778a4f5bd25a2468146e4fd5ceb7f2bc9df7a3d`、Main harness SHA `628494edb44f5aa1ff7eb1912983394cdf74bcabcf222e7e01473988fe5e7134`，child不變。Root全讀28,851-byte patch，獨立核64 pins、23個去重來源路徑及artifact；相對5c73只新增六個頂層定義、修改installer與Main兩個定義。搬移前後原守衛判斷body、其餘nested guard、write roots與Main query成功後所有旅程assertions的AST相同。收據 `root/f12_query6284_root01_a995aa4cfab048c5b207df214a9cf174/receipt.json`。

凍結前靜態審查已要求修正ContextVar區域import造成先用後定義，以及診斷捕捉失敗遮蔽原PermissionError；事件範圍改固定start:end。兩個新增helper測試只覆蓋安全事件投影與writer失敗保留primary，不自行證明actual guard或Main finally。Root reviewer初輪對外部runtime pin位置、次輪對搬移docstring的AST期待停止；只修root讀取核驗工具，未改候選／產品或測試門檻。

| 新同版實際驗證 | 結果與界線 |
|---|---|
| Guard與兩個helper，五節點 | **5 PASS／4.13秒／native0**；`root/f12_query6284_guard_host_root01_2d322a8ea11f4c4d85917d5855b0fb75/receipt.json`。原descriptor角色37 assertions及records0成立；inner `fdopen_guard_probe_34abe4a6ed0f4efaabcfb226592adedd`，Job排空／handles閉合。 |
| 小型真WatchlistView／Yes／私人COW | **1 PASS／8.13秒／native0**；`root/f12_query6284_cow_host_root01_3f964940027147f8928441e28ee462a5/receipt.json`。inner `watchlist_view_probe_946713e4dc2149d0a4e8a99aa5871942`；真按鈕與確認各1次、private schema3、readonly query_only／write_blocked、active service讀回、worker0及Job排空。 |
| 完整Main | **1 FAIL／27.79秒／native1**；`root/f12_query6284_full_main_host_root01_6a439d00222648eba6301ebf21482242/receipt.json`。inner `main_candidate_955c9a30ede740f8a607bce6962e52a8`、launcher52340自然1、非逾時；Job active0／tree與handles閉合。初始化與COW完成，query在5770行仍因source_archived_open_failed／outside_allowed_private_root失敗；完整收藏／新程序未完成。 |

三階段64 pins與23來源均起訖不變。Actual create-only `monthly-revenue-query-guard-diagnostics.json` SHA `bb5f6fe48a7d0e74ddfdd5a776d46d5b3558a5655b28baab1a2616294174ddb9` 已保存：query window10:320共310 events，其中fdopen_rejected283、os_open_registered11、os_close11、owned duplicate2、write_path_rejected **3次**；三次皆audit `open`／observedTrue／thread45620／outside_manifest_roots／relative null。這只證明拒絕事件與時段，尚未識別目標或callsite，不能由283個canonical失敗推定產品根因。接續先靜態trace archived pipeline與operation root，再補有限callsite／診斷角色；不得授更多write roots或改來源。

### P01 v9b 窄順序修正的真 View／TaskWorker 驗證

Owner初版v9只移動call開頭的草稿未採納；另凍結v9b，manifest SHA `622594a3f7250a4d5d264b1ab8ed86a93ea36d6108852ee6c362b7e9b55e3d90`、runner `020cdfde50cc0769f91767e081b9e099ac17e3760c1b58011e71659b98a4d689`、focused test `a78f7148aa0d32296bcb6986492cf05e625f1476a0c6bb4aeb72054d55935d6c`。Root全讀runner單一hunk與223-line focused test，獨立核8 formal／51 product／80 runtime／594 package與candidate artifacts，共708去重raw pins；AST只交換record中完整claim assertion與完整DTO oracle兩statement，其餘runner完全相同，不納入v8 page0最佳化。Static receipt `root/p01_v9b_static_root01_fab095c41999463eabe5ec4db1b36428/receipt.json`。

Root新隔離host **1 PASS／9.04秒／native0**，708 pins起訖相同；`root/p01_v9b_focused_host_root01_f2da921b2ec44e5f8b58d45ba5595241/receipt.json`。真writer產製17股／兩artifact，正常View load與兩次Apply經真TaskWorker／公開reader。先serial oracle再claim明確重現原count mismatch；修正後先claim再完整DTO，兩次均通過。Fixture只有1頁，這是再次Apply page0，**不是跨頁next導航**，後者仍待千檔矩陣。

JUnit `root/p01_v9b_focused_host_root01.junit.xml`實際保存六次sanitized observer：3個真Worker callback／issued+claimed probe，執行緒5496／24856／11008；3個無能力serial callback在coordinator25084，交替順序正確。未序列化能力物件。Pytest另有record_property與xunit2相容性warning，但property實際存在並由root解析；不隱藏warning。原v7 actual暖失敗未保存精確claim count，本輪小型重現不能倒推其數值，也不授p95／完整P01。

Root將上述四份host收據／logs、F12 actual診斷／supervisor／worker log、P01 JUnit共16份raw另存 `root/query6284_v9b_terminal_root_0cf4078f781b4d848d4a5159bbc778c4/receipt.json`，SHA `c9c46b87e356f589b7adebcd1e4b6e498a559b362b6360fbe693a284ed616ebb`，獨立核自然終態、pins、三次拒絕與六次observer。P01正在準備v9b專用preflight／supervisor與真Job失敗案例，未釋完整矩陣；P08 v3真金融整合仍待。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4維持進行中。

### F12 呼叫位置診斷實測與 P01 v9b 監督封套接續

上一 goal turn 只回答產品進度，分類為 no progress；本輪完成候選審查、三階段 F12 實測及 P01 預檢／真 Job 驗證，取得改變下一步的原始證據。未縮減原工作包或驗收條件。

F12 原 `5a8c9d` freeze 的 `test_files`／artifacts 仍指前版，與候選 `eefdbd` 不一致，root 在執行前拒絕；原 freeze 保存於 `root/f12_callsite_freeze_rejected_952ae69424ec47dbb328c2b735c9dce7/receipt.json`，SHA `69cec59de079308931a1f6773a727a45cb063bfe5a8ad29704f1d59b0a0be1e7`。Owner 另建 final freeze SHA `eb8fd4667e6bf20fc6905332bc8a99ee1d297329e03d4461658364720410ead2`，沒有覆寫原件。Root 核64 current pins／63非Main不變、23來源、兩份test snapshot及628494 preimage；AST只新增三個診斷helper、四個診斷／測試function差異及stack上限12，其餘整個module相同，guard installer／Main行為及寫入根不變。`formal_source_pins` 是原release的歷史清冊，current pins 由 `pin_inventory` 給出；root初次validator誤要求二者相等後修正歷史對照，未改候選。Static收據 `root/f12_callsite_eef_root01_1385f4aa52524de3a1dc2dd3429723db/receipt.json`。

| 同版 F12 實際階段 | 結果 |
|---|---|
| 五個 guard／診斷節點 | **5 PASS／4.27秒／native0**；host `f12_callsite_eef_guard_host_root01_504f5fdb98714d89afdcead5aaa0bf23`。原descriptor 37 assertions、records0及Job收尾通過。 |
| 真 Watchlist 按鈕／Yes／私人COW | **1 PASS／12.26秒／native0**；host `f12_callsite_eef_cow_host_root01_4514cfccb6854299baa34777bc026185`。schema3、query_only／write_blocked、active service讀回與worker0通過。 |
| 完整 Main | **1 FAIL／34.01秒／自然native1**；host `f12_callsite_eef_main_host_root01_7a9b0a8e19ad4dcb953b114631fc5081`、inner `main_candidate_342bec40d6394a9eabb13562a07bc90d`。Main初始化及COW後，query仍被outside_allowed_private_root拒絕；launcher33984、無逾時或強制終止原因、程序樹及handles閉合、Job active0。 |

三階段64 pins／23來源起訖一致。實際query診斷 SHA `04352bdff2a294a8887e1c3cabc14c48e3a4dedf0f136251bfc17f2c84506477`，window10:320共310 events；三次write_path_rejected的原guard role仍為outside_manifest_roots，但新增診斷明確分類private_run_write_root，relative都是 `revenue-operations/f12-revenue-4043c815291346e3a1932a182d3ed792/monthly_snapshot_operations/ebdbbfc487e54e1b9f348c61cb796eea/` 下 `.attempt_status.json`／`.snapshot_capture.json` 的隨機tmp。最多12個stack frames目前都是QA guard wrappers，沒有正式writer caller；不能聲稱已取得完整caller。此證據將下一步收斂至guard與診斷的路徑表示／canonical比較，owner準備真extended-path正例與外根／alias／reparse／hardlink等負例候選；尚未接受修正或放寬寫根，完整F12仍待。

P01 v9b supervision v1 supplement SHA `81496c4e` 在執行前被root拒絕：preflight及supervisor要求artifact key `full_diff`，清冊卻只有`v9b_full_diff`及`supervision_full_diff`；四份原件保存於 `root/p01_v9b_supplement_rejected_dd7c272945b44a339a5ee6674e2438b5/`。Owner另建獨立v2 supplement SHA `5649f7f87a9b1ea7929552b45c722b8fe42271d0c7584cdc86f74a576d36dc88`，alias指同一v9b patch。Root核717 raw pins及v1→v2 AST metadata差異，原8 formal／51 product／80 runtime／594 package與sealed store／5cold+1warm／600秒／三類各30樣本／strict p95<300ms／1000列20頁完整DTO協議不變。

v2純preflight **native0／store access attempts0**、80／51／594及匯入origin核對通過；host `p01_v9b2_pure_preflight_root01_00d66952850f471987567eaab1e7c869`。真Job全組 **9 PASS／1 FAIL／5.12秒／native1**；host `p01_v9b2_job_tests_root01_e1fe125233cd47b5b90952bd42a47266`，717pins起訖相同。失敗節點是standalone bootstrap exact hash仍期待舊v7 bytes的`6d23a8`，v9b path／manifest插值後實際為`daf849adfaaa2a1e44db43dd047414d0f7a174403487a7bd02ea7ab064dce29d`。Owner另建v3並先核完整插值內容；不能只從失敗抄hash改期待。完整矩陣未釋出，沒有新p95。

上述五份host receipt／stdout／stderr及F12 inner診斷／supervisor／worker log共18份raw另存 `root/callsite_eef_v9b2_terminal_c4bcdf58a8874cb8a4b2e1dd512a9926/receipt.json`，SHA `9ce88bd9eb430817dcc37deaf2d48f34dcbc0c084efe7e179234fd72a9cfbf36`；獨立核自然終態、來源不變及三個relative target。Root sessions53189／25369均terminal，無live root QA。

P06前置核查確認現行Health reader只讀可變latest_status／latest指標；evaluator沒有不可變歷史receipt及保存後可得時鐘。Root接續補writer-owned封存／public exact reader，未實作前不授歷史情境資格。P08另發現seed_created_at是append前準備clock，首個intent不能直接消費現行daily-only checkpoint reader；owner獨立scratch新增seed prior／首次讀回clock候選，尚未凍結／執行。Root要求區分歷史seed讀回與新執行CAS，避免首日daily完成後讓原seed／intent無法重開；真金融batch→ledger→checkpoint、MA／KD正常接線、benchmark／績效與UI仍待。

本輪coverage僅QA／Snapshot與隔離QA核驗工具；無正式功能或入口變更，Manual／架構／Roadmap／Index不改。回滾只移除此兩文件本節／新增列，依root封存preimage保留其他writer與raw資料；不得reset整樹或清舊失敗。各定向／Main程序已terminal，root無live QA handle。

### P01 v9b3 六角色終態與 F12 extended-path 守門接續

上一 goal turn 為產品狀態回覆，分類為 no progress；本輪重新輪詢原 session47255，確認它已自然終態，未因觀察期限重新啟動矩陣。本節保留原 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍。

P01 supervision v3 supplement SHA `6d772e092444191fe48cc5c6390795fdfbf0fa5f530ef99ef5ad43d1cb6e9ae1`，root 獨立核完整差異、717 raw pins 與原協議。Standalone probe 的 JoinedStr AST 與 v5 相同；root 僅重算已審插值，舊版本 `6d23a8` 與新版本 `daf849adfaaa2a1e44db43dd047414d0f7a174403487a7bd02ea7ab064dce29d` 的差異來自 runner／manifest 路徑與 hash，沒有執行 probe 來推導期待值。v3 純 preflight native0、store access0，真 Job 失敗與收尾全組 **10 PASS／8.10秒／native0**；717 pins 起訖相同。Host 分別為 `p01_v9b3_pure_preflight_root01_7f60ad3f95ec4c55b73332669f2ab6f7` 與 `p01_v9b3_job_tests_root01_f675e8e8b7194f6d94a3d6e92a8fc712`。

原 1000 列／20 頁、五 cold＋一 warm、每 role600秒、三類各30樣本與 strict p95<300ms 協議實際執行；host `p01_v9b3_full_matrix_host_root01_1946c3bf43e64464862bbcc9b0e2f53b`，inner `attempt_20261011T125444Z_06eb0335ca4b`。

| P01 實際結果 | 判讀 |
|---|---|
| 五次 cold | 五 role 均 native0；完整20頁與 DTO 相等，啟動至首頁 nearest-rank p95 **33.9451527秒**。不能把此值當暖查詢 p95。 |
| warm | **65.6722947秒／自然native1**，非600秒逾時。完成20頁與第一筆翻頁樣本 **196.3811ms**，完整DTO相等且真TaskWorker能力已claimed；下一次導航前，phase helper 的 `os.replace(temporary_path, self.path)` 遭 **WinError5**。 |
| 樣本與資源 | 暖翻頁只有1筆，篩選／排序0筆，matrix空；沒有有效暖p95或效能接受。717 pins起訖一致，每role postguard／observer restore／shutdown通過、Job排空及handles閉合。 |

Root另存17份原始收據／logs／phase證據於 `root/p01_v9b3_terminal_review_33aeffedf22843c89aa4cb0e1279513f/receipt.json`，SHA `203d0b346cfd696b85387124c7a71b789663418afa3d0cfaf3e0e97747ec6638`。新失敗已越過前輪claim-count停點，但不能由單筆樣本授300ms或完整P01。Supervisor原碼在role執行期間沒有讀phase JSON；實際WinError5的佔用來源尚未證明，不能直接歸因監督器輪讀。QA-only phase封套候選另交代理準備，原v9b3與失敗封套不改。

F12 extended候選以eefdbdb為preimage，Main test `5c007ea42717f21a4a2f1dbcedb87a92e504b7b1c3e298158b50645cbfc01db5`。原freeze `46e9d018` 的 prior inventory派生metadata過時，owner另建只修該欄位的immutable sibling，SHA `6c313768cd9a7653710b3ab217c2bff66961cb77efdf29c230aeb3f16f5d07a6`；root核其餘全部欄位相同。Root核64 current pins／63非Main不變、23來源、patch精確由preimage重算。整個module AST只允三個top-level functions改動；guard installer只新增DOS prefix驗證helper，替換guarded_path及lexical helper兩處呼叫，其他內容包括完整Main／產品assertions均相同。本輪 `formal_source_pins` 已是current清冊，root初次validator誤要求歷史清冊後修正對照，未改候選。Static收據 `root/f12_extended_static_root01_933b6885a7ca4e86930359c8f6f6accf/receipt.json`。

同版五節點guard實測 **4 PASS／1 FAIL／5.97秒／native1**，host `f12_extended_guard_host_root01_92929b50181e4a1fb57e67c08e31ee22`，inner `fdopen_guard_probe_a5883ed2f3324590bdeb3f23649a3df4`。47 assertions唯一false是private payload精確bytes；本機extended target已成功接受、handle／volume-file／nlink=1驗證成立，七個outside／dot alias／reparse／hardlink／唯讀source／UNC／未知namespace負例皆拒絕且原件bytes不變。Root精確讀回探針payload為 `extended DOS private write allowed\r\n`，而期待LF；Windows os.open文字模式造成CRLF，下一候選只補正例O_BINARY旗標。records0、64pins／23來源不變，專屬Job自然退出並排空。本階段未通過，不釋COW或完整Main。

七份raw另存 `root/f12_extended_guard_failed_terminal_e0bf57f23d2d432bbd7dacce484c412c/receipt.json`，SHA `d7cc56d540cb23fe680a19aeb4600f65f941fc11ff9a5bb463db8444b28c1e86`。Health不可變receipt／public exact reader由原P01代理在scratch實作，正式套用與後續情境/UI由root審核；P08仍補真batch→ledger→daily checkpoint、歷史seed與兩策略正常authority。候選與定向測試不授完整P06／P08／M3。

### F12 O_BINARY 探針通過與完整 Main 保存契約失敗

上一 goal turn 只回覆使用者補完狀態，分類 no progress；本輪重核工作樹與三代理 ownership，保存既有 guard／COW／Main 的 terminal 原收據，不重啟 consumed release。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

O_BINARY sibling freeze `6f2c95360c023e233779828df1af22187a466f016f80da9a0032114d3dcda718`；Main test SHA `2b1e225f53c3fdebb22575d03798e78a91fe331bb9de5876af15795030554c4d`，child 仍 `32456ac7` 前序版本。Root 逐 byte 核整個 module 只把私人正例 os.open 旗標增加 `getattr(os, "O_BINARY", 0)`；其餘 guard、七類負例及產品旅程斷言全部不變，64 pins／23來源核驗通過。Static收據 `root/f12_binary_static_root01_0d1ac6b1107b44faa8cd761eb2eccdd2/receipt.json`。

| 階段 | 同版 root 實測與界線 |
|---|---|
| guard | **5 PASS／4.42秒／native0**，host `f12_binary_guard_host_root01_324df7c0d6924ece8421c444c62bd795`。47 assertions全true、descriptor records0，專屬Job／root handles閉合、remaining PID空。 |
| 真私人 COW | **1 PASS／11.00秒／native0**，host `f12_binary_cow_host_root01_e7f155fcc1254803b14e7e473a21150b`。真按鈕／Yes各一次、schema3、公開reader query_only且寫入拒絕、active service可讀、worker registry0、Job排空。 |
| 完整 Main | **1 FAIL／38.94秒／outer native1**，host `f12_binary_main_host_root01_73c2d2cbb4584b759fbf91230ac175e9`。Main初始化、私人COW及完整母體查詢成功，已操作列／下鑽／返回及準備收藏；尚未等待保存完成、核持久化收藏或新程序重開。 |

Main inner `main_candidate_852151c96b3148d2844012244d0353f0` worker pytest為1 FAIL／31.57秒，首個錯誤在 `tests/test_ui_qt_revenue_main_journey.py:6483`：`bookmark.saved_recipe.f17_query.bundle_identity_sha256`。正式 `DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1` 提供 `f17_query_json`，沒有 `f17_query` 屬性。代理正核整個 Main／freshchild 後續欄位與正式decoder契約，另建 QA sibling，不能以刪除身分核驗或增加產品相容屬性掩蓋測試錯誤。

內層 supervisor記 **exit3221226505**、termination_reason null、active_process_count0、process_tree_closed true、owned_tree_closed＋owned_root_handles_closed。這不是自然native1成功收尾；native異常原因未證實，原初始化600／旅程2400秒期限未觸發。Query診斷明示 settled／success true／write_authority_unchanged true，window10:710共700事件：676個 `fdopen_rejected/canonical_handle_path_unavailable`、11個os_open_registered、11個descriptor_closed_via_os_close、2個owned-duplicate授權；不能稱Main guard零事件，也不能將這些已被query處理的事件當query失敗。三階段64pins／23來源路徑前後不變。

Root唯讀另存 **23份raw** 於 `root/f12_binary_terminal_review_9cb232226d0e4970b62a63bfae6ea04a/receipt.json`，SHA `3425e77a9647b581f393555cfa5888e3e14853ccb827f53c6852a517c1a54e48`。保存工具初輪錯假設每個成功事件都含reason key，KeyError停止；保留該未完成封套，僅修root讀取工具為保留「欄位不存在」，沒有修改原收據或重跑產品。

Health候選仍在scratch：dated baseline缺portfolio_id與observed_at，不能以mutable latest_status補歷史資格；缺完整witness保持degraded。P08正補兩策略exact intent、分開T−1決策來源與execution／close來源及公開日曆clock；尚未QA。此輪coverage／回滾見 `root/binary_terminal_coverage_20261011.md`，正式來源、Manual行為、架構與Roadmap Gate未改；完整F12／P06／P08／M3仍待。

Root另全讀 F12 QA-only saved-recipe patch `256706bb953db5053bbcebfebab5b249e4cb854739fe0c711cfd2761d0e49231`：兩個測試均用正式F17 decoder解析保存JSON，保留bundle斷言並新增完整canonical JSON等價。原full-freeze `9e098de2` 的 verification仍含舊patch hash、錯prior inventory、舊Main preimage與63非Main計數；root尚未套用或釋跑，已交owner建立只修派生metadata的不可變 sibling。62個非test依賴與 guard不改，舊freeze原件保留。

### F12 真收藏保存與新 PID 重開接續

Metadata-only sibling SHA `391167320fd4c054bc67ca7c04115186049af64d57c63f0f9207fb5015a34670` 保留原candidate／patch／62非測試依賴；root獨立核只有created_at／scope／verification／pin_inventory派生metadata變更。逐檔核current preimage、候選snapshot、完整diff與64pins，AST只變Main旅程函式及child.main；guard及其他top-level內容不變，斷言數增加。兩QA測試已套，preimages／rollback在 `root/f12_recipe_static_apply_root01_c0d3b99c654e462d8001fa363796c624`；64pin aggregate為 `dad1ec6b7ccf783a0ca71c46e6e6228762273d71a623e6aadaa936976c6675a7`。不是正式產品修改。

首輪sandbox guard **4 PASS／1 FAIL／14.08秒／native1**，host `f12_recipe_guard_host_root01_e989f909b42441769f05adbf9ef298c7`。內層在guard安裝前os.link合成hardlink setup遭WinError5，尚非守門拒絕證據；Job自然退出、handles閉合、來源與pins相同。Root保存原raw於 `root/f12_recipe_sandbox_guard_terminal_root01`，另發同候選host權限release，不改test或來源。釋出工具曾因placeholder proof hash先行assert停止、未寫release；核實際hash後才釋出，不修改原proof。

同候選guard **5 PASS／4.65秒／native0**，host `f12_recipe_guard_host_root02_f0712aa2ac444e37afc85199f65fd344`、inner `fdopen_guard_probe_c22ce1f41a964cee8d3e2144690a9dd0`，完整47斷言／records0及Job排空由stage release核驗。真COW **1 PASS／10.48秒／native0**，host `f12_recipe_cow_host_root01_0dc77a03e398465dad13cdda53cf17a1`、inner `watchlist_view_probe_cdabf1502e3a4c298527c941944c23b9`；真click／Yes／schema3／readonly reader／worker0／Job閉合均核。

同版Main **1 FAIL／77.32秒／outer native1**，host `f12_recipe_main_host_root01_f3b9cbaacf0d4d67be9a6befd267f48f`；inner `main_candidate_1231a414304b4587a94ed42479baf92d` worker **1 FAIL／72.34秒／native1**，init600／total2400秒未觸發，Jobclosed／active0。這次已核真bookmark writer完成、service完整to_dict讀回相等、原JSON不變、私人DB hash改變、父Main關閉與shutdown requested，再啟動另一PID。

Fresh child PID53448已正常Main初始化、公開bookmark讀回、雙來源exact重開，outcome成功，bundle與canonical F17一致、完整recipe JSON相等。停在child line234：要求重開 `current_query.query_identity_sha256 == expected_query_identity`。child自然native1、600秒期限未觸發、Job排空及root handles閉合；尚未完成後續page/request、收據與正常child關閉斷言，不授完整F12。Root已核正式bookmark.verify_exact_row沿穩定recipe／facts及當次query-page互綁，而原selected query／request保存歷史操作身分；具名SavedRecipe QA亦明示操作ID可更新。已交owner只讀核所有後續父子query／request斷言，先確認差異成因，不能只刪身分核驗。

Root另存 **22份raw** 於 `root/f12_recipe_terminal_review_f3f0f20241d5454bbcdb87874307ed38/receipt.json`，SHA `772124f084655ddbc8dfa7167171a862b44eefa23120e7284b0f08229fed23af`。三階段64pins／23來源前後不變，session54535已terminal，全部本輪release已consumed，無live root QA。Coverage／回滾見 `root/f12_recipe_coverage_and_rollback.md`；本輪前序終態文件已存本機dev `e7d3f78e`，沒有main／push／release。

Health v1 archive候選已freeze（manifest `fe1c3f05af35635927dcd93f3b98faf2838b64ac59954aa961ac69825f264484`），root靜態讀到witness只parse source observed clock，缺與evaluation／archive／cutoff的完整時序核驗；另授同owner新sibling增加refresh不可變source witness、exact portfolio／shares與分欄clock，舊baseline不回填。P08新增reference／execution具名publication選版，公開reader逐角色核clock，完整日volume不得進開盤sizing；仍在scratch，無QA或完整P06／P08／M3接受。

Readonly契約稽核已完成：正式RevenueQuery的hash body含monthly reader／index／operation clock，重開會新發；原source測試458、472–478行明確要求query／read-session／index身分更新。Bookmark原selected query/request是收藏當下的歷史識別；正式verify_exact_row要求stable recipe／facts及重開當次query／page／request互綁。Root已獨立讀上述程式及原測試，授新QA sibling保留原selected ID／完整saved request核驗，另核fresh當次query/page/request及全部recipe條件與stable fact context；父子receipt分列selected／reopened身分，不以刪斷言換通過。新候選未套、未QA，原失敗保留。

### F12 固定合成來源完整 Main／保存／新程序旅程通過

上一 goal turn 只回覆進度，分類為 no progress。本輪獨立審查、套用兩份 QA 測試並完成三階段實測，完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

新 identity 候選 full-freeze SHA `df4bef434bba22255c3d4516184c4106dcfecd9cafe2e3195ff62de51c55355b`，patch SHA `deb15c4755a38e8b380645b11281adf970388854744c410b67a9bb7f88ac7593`。原 freeze `2fee9a4d` 保留；metadata sibling 只修 verification.preimage_directory，另增加 correction／superseded metadata 及核驗工具 artifacts。Root逐檔核全部artifact／64pins、62非test依賴不變、23來源，並從ace399／e92c preimages重算完整diff。整個module AST只有Main旅程函式與child.main改動，斷言數增加；正式程式、guard、來源與期限未改。Main候選 `953dd450900f3160734ea76bdf0316924eee4fd15ca99d505efda68a373286b3`，child `ccc5862a6bb005867d969ca9a0bf21df6b7088445993475b7766f28cbbd9ea28` 已套；preimage封套 `root/f12_reopen_identity_static_apply_root01_3e08ccda0cc74b80856a92166fe47cb5`。

| 同版階段 | Root實測 |
|---|---|
| 五個guard節點 | **5 PASS／3.98秒／native0**，host `f12_reopen_identity_guard_host_root01_656b32fcb74b41b082e1214cfa8e06df`。完整47斷言與descriptor records0、Job／handles收尾通過。 |
| 真Watchlist按鈕／Yes／私人COW | **1 PASS／12.24秒／native0**，host `f12_reopen_identity_cow_host_root01_e3a0659347064af89ab08e3726169f4f`。schema3、公開reader query_only／write_blocked、active service及worker registry0通過。 |
| 完整Main旅程 | **1 PASS／80.19秒／native0**，host `f12_reopen_identity_main_host_root01_ff80d566dc7a4585a9b09d4e79097aa1`，inner `main_candidate_b405fa27564f4bec8471bca282159731`。內層pytest **1 PASS／76.39秒／native0**；父／child均自然0、非逾時，專屬Job active0、程序樹與handles閉合。 |

完整旅程核258檔declared／visible count、同來源列選取／下鑽／返回、真bookmark writer完成與公開service全文讀回、私人DB保存後hash變化、原JSON不變、父Main關閉，再啟動新PID17708（父Main PID27280，child supervisor33036）。Child exact雙來源重開、完整recipe與F17 canonical JSON相等，selected原query/request保留，當次reopened query/page/request互綁且身份更新；頁面0／100、AND／unknown include／stock_code asc及保存條件完整核對。Child正常close後自然exit0，Job remaining PID空；privateDB讀回前後相等。這次保存／重開條件是ma_states及minimum_yoy均null，不能外推其他條件組合。

Query仍明示current_only／availability unknown／historical_pit_eligible false。三階段64pins與23來源觀測起訖一致；成功query的guard診斷仍有fdopen被拒事件，不把query成功寫成guard零事件。Root獨立解析journey與child標記收據，重核新舊身分、stable recipe／F17、PID、source／DB hash及Job終態，另保存 **23份raw** 於 `root/f12_reopen_identity_terminal_review_519eaa3819424fb5a76c0bcc98ca8910/receipt.json`，SHA `5d09ff63aa9eb08b0458466ee708275de6bcd2a21fd7513b45134eee010709c5`。Session26437已terminal；本輪release均consumed，不重用。

接受固定42f合成來源的此完整Main旅程；原來源、其他條件、同版EXE／Native／真人與完整F12／P09／M2仍待。Coverage及精確回滾見 `root/f12_reopen_identity_coverage_and_rollback.md`；本輪只同步QA／Snapshot，不新增Manual操作或架構／Roadmap政策。

F12 owner已回P01 phase QA-only候選，保留原WinError5及缺暖p95。Health v2仍在scratch，完整clock順序及真refresh→identity→evaluator→archive→新PID測試待freeze；只支援paper-main盤前邊界，策略EOD adapter仍缺。P08 v3另補empty selector不得藏非空target、execution open／volume／close同列row identity及精確symbol universe，以及行情與intent/calendar同受控DB核驗；真金融batch／兩namespace／績效與UI未授完成。

### P01 phase 原子替換定向通過與 Health v2 相容性審查

上一 goal turn 只回覆產品進度，分類 no progress。本輪重核工作樹與三個 live 代理 ownership，保存既有測試終態並完成 Health 新版 baseline 的正式 consumer 相容性稽核；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

P01 phase QA-only freeze SHA `6a2dc96d31618c8bc110322fce1f979e6a837c2e41575354f87ce051f40c47ff`，新 helper SHA `d717e79601b80decde99ae1ea7de228cf23c4e1a5d2e3267a2a127a6c8604ece`。Root全讀diff及三個tests，以AST核原helper全部函式只有 `_write_locked` 的一次replace呼叫改接新helper；只對Windows PermissionError／WinError5或32最多四次、100ms重試預算，其他錯誤原樣raise。原xb／flush／fsync／atomic publication／temp cleanup與大小上限保持。

Root原命令 `python -X utf8 -B output/qa/baldr_completion_20261011/root/run_p01_phase_replace_root01_review.py p01_phase_replace_tests_root01 -m pytest output/qa/p01_phase_replace_candidate_20261011/candidate/test_p01_phase_evidence_replace_candidate_20261011.py -q -p no:cacheprovider -o addopts=` 取得 **3 PASS／1.66秒／native0**、child PID14008，host `root/p01_phase_replace_tests_root01_fa0f02c37718435bb4c54e927e36854f`。正例用獨立子程序真正持有不分享DELETE的Win32讀取handle，實際replace遭5／32後釋放、成功保存完整JSON；負例核WinError3只一次、持續WinError5四次、原exception／舊bytes與temp清理。734 pins起訖相同，本輪獨立逐檔重核；release SHA `3ec1bf4dd29ad7fb3614009b1811a19d814f45ed931bf3518403c757e87f0efd` 只授這三測，不授完整矩陣。原Windows占用者未知，不能由此正例判定原故障原因。

Health v2_01 manifest SHA `7f1008d7bb67888e53e0b55865e0c8be02e92cd225fbf5d2908a29bbae8d216b`，四候選source、兩tests、四formal preimages／targets、11直接deps、full.diff／rollback與v1 manifest均逐檔重核。本輪補讀 archive writer、exact reader、receipt/result/source全身分、完整時序、position／shares與有界regular-file讀寫；missing／unqualified撤銷正向Health，invalid阻擋。這是靜態審查，沒有候選pytest或正式套用。

兩個具體接續缺口已交同owner：`forward_position_thesis_candidate_producer.py:1397` 僅接受daily-refresh.v1，新v2會拒絕；`position_health_market_source_producer.py:421` 僅v1走完整snapshot/as-of／source邊界，新v2會落legacy分支。另發現candidate app_module缺initializer時，Python會選正式regular package；v2_02須提供test-only overlay、fresh-cache／actual-origin核驗與child環境pins。原v2_01保留，新compat sibling須保留v1行為、具名v2來源與日期檢查，加入真refresh至兩producer回歸後再審；策略EOD adapter未完成。

Root另存 **10份raw** 至 `root/phase_health_review_f2d813c1fb9b452281f7e33c8778f50d/receipt.json`，SHA `8b43186e55e4afb558aa3264f4b5efad8169aed9b557b8d73d6a367ce286753c`；其中29個Health靜態pins不是完整runtime closure。Coverage／回滾見 `root/phase_health_coverage_20261011.md`。P01 owner正準備全新六角色sibling，原五cold＋一warm、1000列20頁、三類各30樣本、600秒與strict300ms保持，尚未釋跑。P08仍補MA／KD intent首次寫入同一physical DB身份與完整金融daily整合，未QA；正式Health、完整P01／P06／P08／M3仍未完成。

本節兩份文件已精確存本機dev `031d9ae6`；暫存期間另一文件owner保存其成果，root使用 `commit --only` 僅提交本輪兩檔，不重設其他人的index。後續root讀v2_02 frozen overlay，核到initializer把 `parents[1]` 的test_bootstrap目錄誤當freeze根，使candidate path不存在、只能fallback正式；缺actual module origin斷言亦已交owner補v2_03。Owner另發現static closure只涵蓋app_module，其他repo roots須補全；v2_02保持原樣、未QA。P08 owner回報scratch KD intent將canonical字串直接傳sha256的TypeError已修為UTF-8 bytes，尚無QA證據。

### P01 新封套預檢通過與 Health fresh origin 拒絕證據

上一 goal turn 是產品進度回覆，分類 no progress。本輪重新核工作樹與三位 live 代理，完成獨立靜態審查及預檢；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持。正式產品來源、原資料、main／push／發布未由本輪變更。

P01 第一份 phase matrix sibling 的 focused path 多了 `test_`，且 runner 的未使用 expected-relative 常數仍指舊 v7 檔名；保留原 freeze `ca3eb9b4`，另建 v2。新 freeze SHA `357d9eaf9bd5076a43aa18adf3428715a0e51b4524f75897fb5d7efaadee1e99`；runner `7600f42a`、manifest `ed27f247`、supplement `5249200e`、完整24784-byte patch `9ce840d4`。Root全讀patch、從五份原 preimage 與新 test 重建全文diff，核 runner AST僅身份metadata改動；正式source／runtime／fixed-input／protocol maps與原v9b完全一致。完整 JoinedStr 由六項實際插值獨立重算 UTF-8 SHA `385232ce4701d02b0b6d0d170ae2ffd50c9784813d3cadc52ea5f1f1b9ea33a5`，與 assertion／supplement一致；887個raw pins逐檔核相同。

新 pure preflight host `root/p01_pm2_preflight_root01_9b6f92c5a31f4f19ad7a131f8a3bb24f` 為 **native0／store access0**；80 source files／51產品／594套件核驗通過。新真 Job failure-test host `root/p01_pm2_failures_root01_c14df2ff836b4dddb5385be35c461f3e` 為 **10 PASS／10.37秒／native0**，兩階段887pins起訖相同；helper三測沿先前相同bytes證據，不重複累加。

另釋新一次性 full release SHA `5172ffc3ac5a25c4df16a72aa87e5e124299c47ebcfe2ee975ffbd68e029042f`，893pins；wrapper SHA `eb55aaa1cb04c1b3f8dcfa3e8127b3d4a14285c644b42bca274626a25211361b`。原五cold＋一warm、1000列20頁／50列、三類各30樣本、600秒與strict300ms保持。**目前執行中**：session3127、supervisor PID49176，host `root/p01_pm2_full_matrix_root01_cf1eef2c39434322a250b97b17526f9d`；candidate attempt `attempt_20261011T140252Z_c583b095d40a` 的 cold01 childPID5964，phase seq25為 `strict_read_session_open_failed`／`technical_parent_v4_child_path_invalid`。此前source／1457-entry store核驗通過；尚未取得首頁或操作樣本。原deadline與監督器保持，不因觀察逾時重啟，不推定終態或新p95。Owner正唯讀核精確路徑與例外成因。

Health v2_03 manifest SHA `7aa88777092df7a2dc22a3cf9999e5ec5943b38703a7afece7ac3bfe48f567cf`；Root核422pins、四正式preimages與新目標不存在，從六檔重建163302-byte完整diff，四product AST與已審v2_01相同。新origin probe host `root/health_v203_origin_b6b144a94df240f19ea81fca5a47920e`、PID12512自然 **native1**：四候選origin檢查後，已載入本機module清冊核驗發現 `data_module/contracts/__init__.py` 未列pin；422起訖pins相同，未跑候選pytest。Readonly枚舉原321modules還核到其他逐層父package initializer缺漏，已交owner保留v2_03另補閉包。

Health v2_04新manifest SHA `78772aaaf394e9da6692e9c069afde48175531f6699dd3e40323724584862113`；355 repo modules（含22 initializer）、1 namespace、68 stdlib與20 external，未解析local為0。Root獨立460pins／原版本保全／完整diff重建與四source AST再核相同；這是靜態證據，fresh origin／pytest待P01矩陣終態後串行。兩consumer相容sibling已續授；paper-main preopen之外的策略EOD adapter、正常P06／完整P08／M3仍缺。

Root保存 **22份已終態raw** 至 `root/p01_health_v203_review_7b703e0090f845ec9a96af5c4882c838/receipt.json`，SHA `f3f93b4ab2a8eacadad05a70e0f028fb4a3ecaf407c146f8d3f83a404a9ab1fa`；其中full matrix欄明列live、不是終態接受。本輪新增的root工具／receipts／preimages只在ignored QA根。P08 owner已寫真v4→forward observation→MA intent→公開行情→daily→ledger→fresh reader候選測試，未freeze／未QA；KD與兩namespace完整交易／成本及績效／UI驗收保留。

### P01 矩陣終態、strict resolve 身分對照與 Health 五項具體缺口

上一 goal turn 已以精確 session3127 handle 核 live，分類 verified wait；本輪繼續同 handle 至 terminal，再完成 Health 真載入、兩次定向測試及唯讀 cause 核對，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有新的完整工作包接受。

#### P01 原矩陣停止與程序收尾

原 session3127 於 `2026-10-11T14:12:57.035253+00:00` 終態 **exit1**，不再以 live 判讀。Host `root/p01_pm2_full_matrix_root01_cf1eef2c39434322a250b97b17526f9d/receipt.json` 的893個pre/post raw pins相同。原 supervisor attempt `attempt_20261011T140252Z_c583b095d40a` 總elapsed **604.0349435秒**；cold01真角色600秒期限用盡後，primary為TimeoutExpired，外層OwnedCommandFailure。Role收據的native1是Job收尾後的exit，不稱自然成功。

原Job before-cleanup為5964／49308／52052，after-cleanup與after-root-exit均空、closed=true、cleanup_errors空；80 runtime file／51產品origin／594套件postguards通過。只有cold01啟動，其他四cold與warm沒有執行；result.json不存在，phase seq25最後為 `strict_read_session_open_failed`／`technical_parent_v4_child_path_invalid`。原1457-entry store初核通過；沒有首頁或暖操作採樣、新p95或300ms接受。原role stderr僅font cache warning，沒有保存底層OSError。

Root使用同一唯讀探針對固定sealed segment0第一個child的205字元repository root與437字元manifest核對：manifest SHA `580c2a7710546b343e651393715b9556e53605390965575e5f5d7e087c3958c6` 起訖相同，lstat的dev／ino／size／mtime／nlink／attributes保持。Sandbox兩路徑皆strict realpath PermissionError／errno13／WinError5；經自動審查允許的host兩路徑皆成功，去extended prefix後與原canonical identity完全相等。原收據為 `root/strict_resolve_p01_pm2_sandbox.json`、`root/strict_resolve_p01_pm2_host.json`。這證明這兩個精確路徑有執行環境存取差異；不能冒稱已取得原live underlying cause、全部sealed路徑已驗或完整矩陣通過。原來源與守衛不改，owner另建QA-only exception chain／真正error callback早收尾候選。

#### Health v2_04 真載入與 sandbox／host 重驗

同一manifest `78772aaaf394e9da6692e9c069afde48175531f6699dd3e40323724584862113`、root release `20d3c13d841eff6189d282bba8f7c50363aafb095f6f5f3ada98a9e52f496287` 保持。Fresh origin host `root/health_v204_origin_feff383b32de42d3b5eced4aa856dc56` 為 **native0**：四個candidate實際`__file__`／SHA成立，39個已載入本機模組皆在manifest expected pins中，另保存725個實際runtime檔案觀測；後者不是725項外部runtime全部已預先pin的宣稱。460 pre/post pins相同，新formal targets仍不存在。

Origin wrapper啟動venv PID47524，probe實際base Python PID48552；root初次額外解析錯誤假設兩者相等，AssertionError後直接讀原JSON核到此區別，沒有改candidate或把它當origin失敗。後續以四origin、39本機module與460pins的原assertions判讀。

| 固定候選階段 | 終態與範圍 |
|---|---|
| Sandbox兩測試檔 | `root/health_v204_focused_tests_81c1a39628f049efa3b423e28c5ab4b5`：**15 PASS／23 FAIL／10.38秒／native1**，460pins相同。23FAIL均在archive `root_abs.resolve(strict=True)` PermissionError／WinError5，未到完整新程序旅程。 |
| 同script唯讀路徑對照 | `strict_resolve_health_v204_sandbox.json`／`strict_resolve_health_v204_host.json`：同四個既存路徑、兩種strict API共八檢；sandbox八拒絕、host八成功，所有metadata／source hash相同。未修改產品守衛。 |
| Host兩測試檔 | 自動審查允許後，沿同候選／460pins、全新私人`.t`根重驗；`root/health_v204_focused_tests_1897f1bc8d1244eebf15e8c1a260660b`：**32 PASS／5 FAIL／1 skip／3.09秒／native1**，460pins相同、formal新檔仍不存在。原sandbox失敗完整保留，不累加兩次passes。 |

Host五項失敗已逐項核，不再統稱環境問題：

1. 真refresh→PaperPositionIdentityProvider→baseline/witness→evaluator/archive成功，但exact read為blocked。Root用同public reader唯讀重開原結果，唯一blocker是 `position_health_source_future_dated:provenance.position_identity_source.observed_at`：10/11觀察被用於10/08決策。因果守衛正確；新版fixture須用明示受控盤前時鐘，保留晚觀察拒絕，不放寬reader。
2. 原structural-only baseline無來源witness，exact model為degraded／unqualified；source_observed_at與baseline_saved_available_at都為None，測試卻fromisoformat('None')。缺時鐘須保持未知，不借archive時鐘補值。
3. Raw shares `100.0` 的負例在archive嚴格JSON parser被 `saved_health_result_floating_json_number_rejected` 拒絕。須對齊真正拒絕契約，不授浮點股數或改鬆parser。
4. Extra-universe負例保存receipt時，plain `os.open` 的長temporary path得到FileNotFoundError／WinError2。
5. Wrong-source負例在另一個長receipt temporary path發生同類plain I/O失敗；需沿既有internal I/O path邊界，保留canonical identity與create-only publication。

Root唯讀重開兩原結果的證據在 `root/health_v204_existing_saved_models_root01.json`；460pins及原health目錄全部bytes保持。Skip尚未提供reparse setup成功證據。五項缺口已交owner另建v2_05，原v2_04保持；兩consumer相容候選先獨立freeze，不把盤前Health授成策略EOD或完整P06。

Root獨立核終態、Job、pins、原路徑對照與兩模型後，create-only保存 **34份raw** 至 `root/p01_health_v204_terminal_review_51fbab12675c46c398491c198d4cee69/receipt.json`，SHA `d86ae0fce0dc3cf6d6827586a841d46759e21c50675b3459c472f60ff0147fd5`；兩份正式文件preimages亦保留。Coverage／回滾是 `root/health_v204_terminal_scope_and_rollback.md`，僅追加Snapshot與本QA，不新增Manual功能或更改Roadmap／架構契約。

P08 v3新freeze SHA `a7123366b679e44677aca2ef6a5bc1fc643a9578b840a1d9ec9500d5f7009282` 已交root，尚未QA或正式套用。Owner明列正式seed writer未保存availability、MA首intent依scratch reader、KD僅接受既有daily checkpoint、daily首seed gate只核準備時鐘等生命週期缺口；另建v4補真seed→MA/KD首intent→daily／checkpoint，不能用setup-only bootstrap結案。完整策略、績效、UI、M3與全部產品交付Gate繼續。

### Health consumer v5 獨立清冊審查：前版 sidecar 檔案雜湊不符

上一 goal turn 為產品進度回覆，分類 no progress。本輪依目前工作樹繼續獨立靜態審查，產生可改變後續動作的拒絕證據，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

Compat freeze_v5 manifest SHA `5a99b878bdc42420d84150fb89003616233e85a3d7918df1bdcdcafa2d311993`，full.diff SHA `360b34068fc7eefa88bc7a922bb639d502812b268e2752d315f0c44249983756`、59123 bytes。Root全讀兩個product差異、既有consumer呼叫與兩份新增測試／overlay／look-ahead及回滾，核對具名v1／v2分支、paper-main preopen、來源與identity clock、entry日及缺identity保持awaiting／degraded；未把本候選授成P08 EOD、正常Main或完整Health。

Root審查工具從四份saved preimage逐行重建全文diff，與原full.diff bytes完全相同；四formal targets仍等於各preimage SHA。修正後獨立檔案檢查共475次、462個unique paths，包含candidate／formal／依賴／runtime／stdlib／前版metadata。唯一真正mismatch是 `prior_compat_freeze_pin.sidecar_sha256`：宣告 `86337ea37dca461746b80dc4f1e95667d63189f2d3dc10fb517c6f70367d2bee` 是v4 manifest hash；111-byte sidecar檔本身實際hash為 `9ed4b9d77642d4d4bd043dcdf89aeb8303672a79e14dfcc514f8be26cd1666ba`。Sidecar第一token與manifest相同不等於sidecar file SHA相同，故v5仍為static_rejected，未執行candidate origin／pytest或套正式。

Root初版工具誤將stdlib-relative paths當repo-relative，曾報一批缺件；原工具與第一收據保留。讀dependency builder及manifest後沿sysconfig stdlib根修正，再核其餘檔案全部一致，不能把root的路徑解讀錯誤算為candidate缺件。最終收據 `root/health_compat_v5_static_review_0fbf15e99b2b4ae8b47a1f09992dd1b3/receipt.json`，AST核四個目標只增加具名validator／consumer接線與候選測試。這是靜態差異證據，不是實際runtime／金融／UI通過。

Root create-only保存10份raw／兩formal文件前像於 `root/health_compat_v5_review_packet_5efd92a63d8948f0898979f47dd5339b/receipt.json`，SHA `ec2fe602772e3030f115b8f33f62894a6161dc6de10d9cc1518c36f6f5db4386`。Scope／回滾見 `root/health_compat_v5_scope_root01.md`；僅追加本QA與Snapshot，不新增Manual操作或更改Roadmap／架構。

Owner已接續Health v2_05五項原失敗修正，之後另建metadata-only compat v6，保留v5原件並精確pin v4 sidecar及v5 predecessor；兩者仍須root審查。P01 owner續補原error chain與真error callback收尾，P08 owner續補真seed／availability及MA／KD lifecycle。完整效能、帳本、績效、UI、同版EXE、自然排程與真人接受保持開放。

### P01 錯誤收據定向通過與 Health v2_05 真來源 fixture 擋點

上一 goal turn 只回覆產品進度，分類 no progress。本輪獨立審查新候選並執行已授權驗證，取得可改變下一步的證據，分類 progress；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持。

#### P01 QA-only 錯誤診斷與等待

Error-receipt freeze SHA `8dfde1f0ca3475bb507b836256bd2ec7ecd3d960a8855c93d62204274551f5d8`，runner SHA `ebea7622bb09690a1fdb805937db6d61ccf90e3e256a5e1e87ccd9caa77a02c3`、95419 bytes。Root全讀runner增量與五測，獨立核994次檔案hash／774個unique paths，從v2 runner preimage逐byte重建24648-byte diff相同；source_freeze／runtime_file_sha256／runtime_environment／fixed_inputs／normal_view_protocol／semantic_oracle六maps與原manifest完全相等。Static收據為 `root/p01_error_receipt_static_review_c12dabc7b51c47f3aaf94b8f9406f20b/receipt.json`。

候選保留例外cause/context拓樸、qualified type、errno／winerror與有界traceback；只保存遮蔽絕對路徑的message／repr／frames，不保存locals或source lines。初次load在exact TaskWorker.start owner接額外error observer，仍執行原start與正式View error receiver。只有worker已release且保存error／strict-open failure時，等待才走typed失敗；原成功result type／query／page identity assertions與600秒預設期限保留。

Root在host fresh interpreter執行 `candidate/test_p01_taskworker_error_receipt_candidate_20261011.py` 全五測，**5 PASS／1.98秒／native0**，outer2.703秒，stderr空，774pins起訖相同。含真TaskWorker錯誤及成功signals、正式View錯誤receiver、native finished後release，以及synthetic cause/context／cycle／成功identity。成功wait測試仍是小型fake DTO，因此不授千檔完整DTO／p95或整體P01。Focused收據 `root/p01_error_receipt_focused_4f09c3836beb49a8b49443df99128597/receipt.json`，SHA `ae5879e3f02767daf4d60e69e64690d2a930026bed1d07da3d27e0a7d843c35b`；JUnit與stdout同目錄，完整矩陣未啟動。

前輪cold01的底層cause仍未知，不能用synthetic error倒推原WinError5或逾時原因。原600秒矩陣、sealed store／source guards、1000列20頁、五cold一warm、三類各30筆與strict p95<300ms仍有效；owner另建supervisor／preflight／bootstrap重綁候選，須root核驗後才執行。

#### Health v2_05 完整增量與實際失敗

新manifest SHA `62bd436cf22e811d03ed2ff5b07741d150814e8eeac04a88ac29b4872dbea9e2`。Root核476個unique pins、四formal preimages與兩new targets仍absent，逐byte重建formal→candidate完整168742-byte diff及v2_04→v2_05 delta；兩reader／evaluator AST不變，產品差異只在refresh私有UTC clock seam與archive OS I/O邊界（新增import及五函式），canonical／strict resolve／reparse／single-link／stable-read／create-only契約保留。Repo dependency仍355 modules／68 stdlib／20 external／unresolved0。Review／release工具只寫ignored QA根。

Fresh origin host **native0**，四candidate product origins、39個載入local modules與725個actual runtime files已保存，476pins不變，formal new targets仍absent。Receipt在 `root/health_v205_origin_43eb75d7124646e9b291e0457b10e980/`；這不是完整UI／金融接受。

Host兩檔定向pytest：**36 PASS／2 FAIL／1 skip／3.64秒／native1**；不與前版32 PASS相加，476pins及formal absence保持。收據與stdout在 `root/health_v205_focused_tests_9fe5026b2ff84fa6ae89ad17f8aeaa85/`。v2_04原五失敗與所有freeze原件保留；新負例及長路徑停點解除後的既有負例仍有fixture缺口：

1. 新late-source負例使用 `_scope()` 的synthetic預設POSITION_ID，真writer保存的是另一個entry lineage，所以先被 `saved_health_scope_position_identity_mismatch` 擋下，未抵達日期守衛。Root用原baseline保存的真position id／code／shares建立typed scope，對相同已保存receipt唯讀重開，唯一blocker確為 `position_health_source_future_dated:provenance.position_identity_source.observed_at`；不用換expected assertion遮過。
2. Extra-universe測試修改baseline多加一列後，對新content SHA所定位的 `saved_baseline_witnesses/<SHA>.json` 不存在。Receipt已保存 `health_baseline_witness_unavailable:saved_health_artifact_missing`，public reader因此先回 `saved_health_source_witness_invalid`。下一候選須建立與新完整baseline相符的有效witness，再測request scope少一持倉時的完整universe拒絕；錯witness另保留負例。

Root公開reader唯讀對照在 `root/health_v205_saved_failures_root01.json`；23個原fixture檔及476source pins前後相同，沒有更新fixture／writer／reader或正式帳本。已授原owner另建v2_06 test／sourcefixture sibling；不放寬因果或身分守衛。Skip仍無成功reparse setup證據，保持未驗。v2_05未套正式；paper-main preopen之外的P08 EOD／正常P06 UI與M3仍待。

#### P08 績效接續的公開比較器證據

Root以實際 `ResearchRunComparisonService.evaluate_comparability` 與記憶體DTO做四例唯讀probe：兩筆缺status／身分／fingerprint／metrics，以及兩筆無資格legacy零metrics，均回Comparable；明示cancelled與不同fingerprint則各回Incompatible。DTO預設status回退completed及空fingerprint相等不自行授績效資格。因此P08新read service消費既有公開ResearchRunService／ComparisonService前，須逐run核完整資格與metric validity，缺件保持未知，不把零值當有效歷史績效或排名。原metrics／broker／ResearchRunService／ComparisonService維持既有復用邊界，本輪未改程式或計算金融指標。

Probe收據 `root/performance_comparison_probe_31353601236348a79d5c21ac0354df9e/receipt.json`，SHA `02dd096bf30740541fcc9697040f00a14fee8b3edc452a4981b064376a78d6d5`；兩formal module origins及hash起訖相等、無DB／UI或正式資料。這是新consumer設計的必要前置證據，不是完整P08接受。P08 owner目前仍補真seed writer／availability→MA與KD首intent→daily CAS／checkpoint，績效與UI尚未完成。

Root create-only保存28份raw及兩formal文檔前像於 `root/error_health205_review_packet_f4e885be1bb340e28b093f7d1a6c63ee/receipt.json`，SHA `6d700a46a626bda058d5c84c49ac531512a2ba3604e65856ee0860cd8590746c`。Coverage／回滾見 `root/p01_error_receipt_review_scope_root01.md`及候選Health rollback；本輪只追加Snapshot／本QA，Manual、Roadmap、架構政策與main／push／發布未改。Compat metadata-only v6已由owner交root，但尚未獨立核驗／QA，不取代v5原拒絕。

### Health v2_06 定向通過、相容測試終態與 P01 預檢差異拒絕

上一 goal turn 為進度回覆，分類 no progress；本輪取得新實際來源／測試終態及可改變下一步的靜態拒絕，分類 progress。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包接受。

#### Health v2_06 真來源與完整兩檔測試

Manifest SHA `c2fac8383c3645b106eda6ff8e3bc4556135b087aa7cdd37d8044be16242782c`。Root核515個raw pins、正式四前像／兩新檔缺席、172479-byte full.diff及5478-byte v2_05→v2_06 delta全文重建。四個產品來源bytes與v2_05完全相同；唯一變更為saved archive測試：晚到負例使用真refresh writer產生的position id，extra-universe負例重封完整合成baseline witness並先核structurally_valid，以抵達原scope universe守衛。這份合成witness不取得正式資料資格。

第一個root origin探針已載入新四檔，但其繼承依賴清冊仍指v2_05路徑，故以來源清冊assertion停止；515 pins及空bytecode根保持。保留原失敗，另建v2探針逐一核四對equal bytes、移除舊依賴路徑並精確綁新v2_06路徑。Fresh child **native0**，四candidate／39 local／725 observed runtime來源核驗通過；`root/health_v206_v2_origin_d1015e94b577464b95c5bf1da8634096/receipt.json` SHA `d57bbe0ac4719765010c9e40387138b3a4f97569e97db6a783f6400e7c90b640`。沒有把此root探針錯誤當成產品故障。

Host完整 `test_position_health_daily_refresh_service.py` 與 `test_position_health_saved_archive.py` 為 **38 PASS／1 skip／5.58秒／native0**；515 pins起訖相同，正式兩新檔仍缺席，fresh `PYTHONPYCACHEPREFIX` 起訖為空並使用 `-B`，未載入候選保存的舊相鄰bytecode。收據 `root/health_v206_v2_focused_tests_9d96082d6f714cac9b53a732569eeedd/receipt.json` SHA `5efc2fc74fd2f7d9c8dc266bfa35ed66464a9675075c4e7480049c0d13eb04b6`；JUnit同目錄。候選四來源mypy為0 issues、六檔語法通過／兩命令native0，515pins相同；`root/health_v206_types_dc4849c8b6644e21b8196434991477c6/receipt.json` SHA `912e5356dacfdb0c95c1f6ee931ad443544b47f87685554d4bfb68ae646f26f1`。Skip仍未有成功reparse setup證據，完整Health／正常P06 UI／策略EOD／P08／M3未授接受；本版未套正式。

#### Compat v6 實際測試與下一版範圍

V6為保留v5來源bytes的metadata-only sibling，manifest SHA `f34e3dd868a8f28e1b2bdc7d814d0870377aa61c470083b5cff5d82f3cadcd2e`。Root500 checks／469 unique pins、原四formal前像及59123-byte全文diff／metadata delta重建通過。四Health依賴仍是v2_04，不是v2_06。Fresh origin native0、六candidate／54 local／830 observed runtime；完整兩producer測試 **47 PASS／4 FAIL／3.04秒／native1**，469pins起訖相同。原收據在 `root/health_compat_v6_origin_9e43ef31d2dc4cee84706a1403d062ce/`及 `root/health_compat_v6_focused_tests_2bb2b94225884d33b53113c1b8e7cf39/`。

Root確認兩個新測例把不回傳值的 `_write_json` helper當作Path，導致Path(None)而未抵達目標validator；approved-machine-policy fixture的v1 baseline缺decision_date，producer回 `health_baseline_decision_date_invalid`；weekend fixture為 `market_date_not_latest_verified_session`。Owner唯讀triage指出共用calendar cache的captured=09/08、31日expiry=10/09已早於10/11 host QA日期，另建有效且完整hash-bound測試cache；不改producer日期或因果守衛。已授v7完整fixture修正、typed blocker assertions及四Health依賴的實際origin／closure精確重綁v2_06，原v5／v6保留；v7尚未執行或接受。

#### P01 新監督器 v2：QA 前靜態拒絕

Freeze SHA `315ee11ccd6177a1cf5b5738fac39b88c027b0112a0ea22f5b8993999081f194`。Root1664 checks／837 unique paths一致，145567-byte完整patch由原三harness preimages、已審error runner diff、standalone bootstrap及builder全文重建相同；原Job／程序控制核心AST不變，九項原failure tests不變，只有第十項改為新standalone bootstrap。原manifest保留error-receipt bytes及其歷史writer_scope，不把focused五測授成full matrix。

Root靜態核到preflight line183 `_exact_artifact(..., "full_diff", V9B_DIFF_PATH)`，其常數仍指normal_view候選的舊v7 patch，但supplement列新v2完整delta；必定回 `v7_candidate_artifact_path_mismatch:full_diff`。**未跑preflight／pytest／Qt或完整矩陣**。拒絕收據 `root/p01_error_supervision_v2_static_a29db55f58af4a6d8fe0cc8d54f4cd16/receipt.json` SHA `011a3a3f9fcb7d905210626ee538f09c60b9636c630e85f6c2448ac442d646fa`。已授原owner保留v2、另建v3並逐項靜態比較expected path與被讀manifest row，分開新版完整delta及原phase-evidence diff。原千檔20頁／full DTO、五cold一warm、三類各30samples、600秒及strict300ms不變。

#### P08 候選清冊與完整終態保持

V4 seed lifecycle manifest SHA `df09831050ea15850b73253dd65a3cdef1c30d01460ae85e614e26d9a968dd81`。Root只核清冊／正式兩target提案patch：79 checks／75 unique pins、26凍結檔、37正式source及8focused tests，66104-byte patch從原seed writer前像及新typed-prior檔全文重建一致，新formal target仍absent／imports沒有scratch來源。收據 `root/p08_v4_inventory_2e2359b7c1c54abca60abca886a7a21f/receipt.json` SHA `74e91ff88629c093c0996b37884307867c519d625ad4f82b2219e98beb56bad3`。**完整生命週期邏輯未接受、未QA或套正式**，不能單獨套seed patch取代daily v2整合。

原owner接續scratch績效reader／兩卡widget及public ResearchRun讀回。已盤點原DTO允許空status／fingerprint、legacy metrics無schema及benchmark缺exact source／clock。新consumer逐run驗資格、缺件保持未知；另要求提供root可實作的版本化metrics／benchmark producer接點及可計算研究績效契約，不以永久unknown卡完成P08。兩策略成本後研究績效、歷史比較、正常UI與新程序仍是完整終態要求。

Coverage及回滾見 `root/health_v206_scope_root01.md`與候選README。Root create-only保存51份raw及兩formal文檔前像於 `root/health206_compat_p01_review_packet_e2cc74f5508147d88230e2a05e3d6920/receipt.json`，SHA `9f39b6737279a9fff156050f819ebd6c505a837be36206a53c0c1098628d765d`；第一份長檔名packet在第48份遇Windows長路徑限制，其47份已複製原件保留，新packet以短檔名及完整source metadata完成。Root本輪QA全部終態，只追加Snapshot／本QA；Manual、Roadmap、架構政策、正式產品來源、原資料、main／push／發布未改。

### Health compat v7 靜態拒絕與 P08 seed 守衛核實

上一 goal turn 回報進度並核實 P08 的兩個原函式分支，取得可改變修正動作的證據，分類 progress。本輪續核 Health v7 與 P08 交易／整合案例；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包接受。

#### Health v7：產品內容與閉包核對通過，清冊 live pin 拒絕

Manifest SHA `e621d12905c9366cda131fb12698110b788c9e21446e90719aa4e3c5da7a6451`。Root 核969 checks／499 unique paths、四份formal preimages與65756-byte全文diff重建；兩個產品來源與v6所指v5 bytes相同。四個Health依賴均指v2_06實際candidate，root逐項核其355 repository modules由v7的360項覆蓋，僅五個compat-only modules；套件initializer／overlay與forward candidate另核精確重綁。已讀兩份產品validator及測試差異，fixture改動保留日期與typed blocker守衛。

唯一不符為 `prior_compat_freeze_pin.sidecar_sha256`：path指v4的111-byte `.sha256`原檔，但expected值`86337ea3…67d2bee`是檔內manifest token；actual raw file SHA為`9ed4b9d77642d4d4bd043dcdf89aeb8303672a79e14dfcc514f8be26cd1666ba`。此欄由v5繼承，未沿v6修正，故**QA前拒絕，沒有執行origin／pytest／Qt**。原拒絕收據 `root/health_compat_v7_static_review_b254b5259ac2434db5c7b0512cfc721c/receipt.json` SHA `c2a8bd1b38c88ae49dae92dff2c60a6e7f4d55f394d5222f48197a29ca6fa4de`。已交原owner另建metadata-only v8，保留v7原件與產品／測試／overlay／closure的原bytes及paths。另核v7說明誤寫v6有3 skip，原stdout終態實為47 PASS／4 FAIL／3.04秒、沒有skip；新版說明需據原件修正，舊說明保留追溯。

#### P08 v4：兩個消費狀態分支實際核實與交易窗口

Root只抽取凍結原AST的 `_require_columns`、`_require_primary_key`、`_seed_consumption_status`，在純記憶體SQLite執行；未跑完整reader／writer或金融計算。存在同帳戶later snapshot時，daily兩表缺席及兩表存在但皆空，**兩案實際均回unconsumed**。沒有可驗daily證據的later snapshot應回unknown，歷史seed仍可讀但首次clock／恢復寫入應拒絕；不可憑缺證據推定未消費。

另靜態核 `_record_seed_clock` line1025在BEGIN IMMEDIATE（1068）前讀exact seed，鎖內至commit（1102）沒有base／hash／consumption重驗，存在並行consumer先提交的窗口；**未重現runtime race**。測試line228仍期待clock_unknown，但新writer已自動寫clock；pending daily測試line437建表即結束、無assert，receipt／operation片段誤放line463的later-snapshot測試並引用未定義connection。已交owner保留v4與績效v5 WIP、另建seed lifecycle v2修正版：鎖內核同份base／身份／消費狀態、真companion failure與resume、正確分離測試scope並保留真daily consumed整合。

75 pins起訖相同；收據 `root/p08_v4_seed_guards_057fcc07bc444cacb96111cb56c51968/receipt.json` SHA `86b7e187f2178f44ef9de5816980ef90b37e770f35e108eacf184bfeb54e26f1`。Root診斷工具前兩次僅因自己的常數擷取不足停止，未產生成功收據；修為只取數值budget後完成上述原函式核實，沒有改候選產品。續讀整合案例確認MA／KD各自seed／intent／ledger、buy成本、blocked zero-fill hold、death-cross exit與fresh PID讀回有具體assertions；這是測試內容審查，**未執行或接受完整生命週期、績效、正常UI／M3**。

#### 保存與接續

P01 v3首次create-only組裝遇歷史預像深層路徑限制，partial原件保留；原owner以短名稱唯一sibling及history_v1／history_v2映射續行，未跑preflight或matrix。三位原代理均confirmed running。Root保存10份raw與兩文件前像至 `root/compat7_seed_review_a46ca13b7af143959f9c31ff236c184f/receipt.json`，SHA `deb249e775b5cf92498bf80e0a17cd105fcc266e4bbdea099ac6832ac2d0ee69`。Coverage限定Snapshot最新狀態與本QA追加；產品入口／Manual／Roadmap／架構與Index未變，保留其他owner dirty內容。正式產品與原始資料未動，完整目標active。

### Health 正式十檔整合與廣回歸缺口／P08 seed v2 原函式核驗

上一 goal turn 回覆產品剩餘狀態，分類 no progress。本輪重新核工作樹與三位原代理，完成正式 Health 套用及回歸，取得可改變接續動作的失敗證據；完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保持，沒有完整工作包接受。

#### 前序候選與 P01 終態補記

Health compat v8 manifest SHA `c894f72c1c8c5bd261e43911de84e0fafec479b410de86031c20941e0fde9069`：root 核991 checks／504 unique pins、實際六來源，兩檔 **51 PASS／4.29秒／native0**，起訖 pins 不變、fresh bytecode 根空；metadata-only 修正保留 v7 產品與測試原件。Focused 收據 `root/health_compat_v8_focused_tests_7311445cb8db4166afe4fdeecbf24b8a/receipt.json` SHA `e9184c47c35731da61be6b625edf5faa0f77b866373eb5a22fdb82665947dd00`。Health v2_06＋compat v8 六來源 mypy、十檔語法通過，577 個 union pins 不變；收據 `root/health_pair_types_193424d3d90b423493214ae71a695f81/receipt.json` SHA `4985a04dc2e9d9c8ff1cd713158527de48e26acb9e460bd6a51006a3c5a5c115`。

P01 supervision v3f manifest SHA `214405d0ef0a821930260062434a4b65e2ab59102291d6c4ae45c41111a65d62`：root 核2327 checks／1107 pins、20 bridges與全文 delta，pure preflight native0／store access0、80 formal／51 product／594 runtime。完整十個 Job failure tests **8 PASS／2 FAIL／1.72秒／native1**；兩 fail 均在 supervisor line230 把 supplement 的 path／SHA／size row 與原 manifest 的 path／SHA row 作整個 dict 相等比較。實際 path／SHA 相同，153015-byte size 只在 supplement，故不得宣稱 preflight 通過代表 standalone 已可跑。收據 `root/p01_v3f_jobs_9b2585ed01614c9ea7e212557f011dd4/receipt.json` SHA `650a7343a8cf9b504dbd818c135daa89a8b7ae0dc414d6ab1f06cedf412ee065`；1107 pins 不變，完整矩陣未釋出。Owner 新 v4 freeze `ed111070c0767a9eda93eebc05098ebda4129d43b258e78af5c1714dbdc0004f` 已回，root 尚未審查／執行；原五 cold／一 warm、1000列20頁／完整DTO、三類各30樣本、600秒與strict300ms保持。

#### 正式 Health 套用與逐函式轉換審查

十目標提案 `output/qa/health_formal_1011/freeze_v1/`，manifest SHA `c5ba9311661c8994c06def2cf9bdce9c00b8675269dbf0f082cc4d952b37c56f`。Root 核596 pins，從八份現有正式原檔及兩個 absent target 重建224941-byte全文diff。六個 product sources 與 v2_06／v8 已驗候選逐 byte 相同；四份 test 的所有原函式 AST 保持，只有兩個 archive 新程序函式移除 child origin scaffolding 並改正式 cwd／env，root 逐語句核其餘內容與 assertion 相同。新 helper 只清除 PYTHONPATH 並要求 PYTHONNOUSERSITE；沒有刪新程序旅程或負例。

Static 收據 `root/health_formal_static_a25960a3e2384205b4717080b5068699/receipt.json` SHA `2e7811d3d7034c66460e28cc0346ab4f4e8f5cec7fccf5b3c4289ddebd3943eb`。Root 保存八份 preimages 後套入六產品及四測試，新增 `app_module/position_health_saved_archive.py`／`tests/test_position_health_saved_archive.py`；apply 收據 `root/health_formal_apply_64415fb690f34c34a6518e27b1fde5ae/receipt.json` SHA `73f1bf9a7d7c2eee03c2fbabb60b76a374a5d180e59669e1a811457177d6d228`。這些正式檔目前是未提交 WIP，廣回歸失敗未解，不授整合完成。

| 正式匯入階段 | 原始終態與界線 |
|---|---|
| 六來源 origin | Fresh interpreter 真正式 app_module 六來源／54 loaded local 核驗通過；不載入 scratch overlay，fresh bytecode 根空。 |
| 四檔 focused sandbox | **39 PASS／51 FAIL／21.45秒**。私人 temp 的 os.replace／strict resolve 遭 WinError5；原失敗完整保存，不能寫成產品全部通過。 |
| 同源四檔 focused host | **89 PASS／1 skip／9.64秒／native0**，610 pins 起訖相同。收據 `root/health_formal_focused_babce770647a4b0faf1021fc2069626a/receipt.json` SHA `3302b3dc89e0927e200e83a6e0b0b5c50bab74247c4d056528238dece677208b`；skip 為 reparse 環境能力，未授 G3／G4。 |
| 六來源 mypy／十檔語法 | **兩命令 native0**，610 pins 相同、fresh cache空。收據 `root/health_formal_types_a6b72637c80a4735b15a1a67b7dc2560/receipt.json` SHA `926f1933b529bd37680eab873e0ab98c32c8787e8366dcf30133e8a78bca4913`。 |
| 十一檔既有回歸 sandbox | **100 PASS／22 FAIL／1 skip／53.45秒**。來源不變；含私人 strict resolve WinError5，完整 failure list 保留。 |
| 同源十一檔回歸 host | **117 PASS／5 FAIL／1 skip／29.81秒／native1**，610 pins 相同。收據 `root/health_formal_regression_03252c1e43f84723a2bc69738b05a507/receipt.json` SHA `6c542b5325292a52e7dede9d449393701f3cdee321df89357941a9c527b3c451`。 |

Host 的五項缺口：舊 baseline bridge fixture 的 `sha256:rows` 被 archive receipt hash validator 拒絕；scheduled integration 預期 manual_action_required=true、實際 false（本輪未改 scheduler）；三個 source-provider 案例的9/8 captured＋31日 calendar fixture 在目前日期已失效。Root 已讀 JUnit 原 assertion 與 SQL／calendar 入口，交 owner 分辨既有 fixture／契約與產品回歸，不先刪 assertion 或放寬 validator。正常 Portfolio／Main exact receipt 操作與策略 EOD adapter 仍待。

Root QA 工具先因 Windows path 分類、命令列過長而在 child 啟動前停止；改用 manifest 檔輸入後，第一個 origin 把 .venv 誤判 repository source，native1 原件保留。修成與原 origin probe 相同的 repository／.venv 分類後才進入 pytest；沒有修改產品或把工具錯誤當產品 defect。Static 工具先因 CRLF 與 receipt exit-code 欄位差異停止，修正 raw decode／具名欄位後完成全文核對。

#### P08 seed v2：原分支修正通過，完整候選待 QA

Manifest SHA `5f222a3fd38f40d6a59d588fe4e707929a05ce58eb7203305c8eca8927b8eb51`。Root 176 checks／118 pins，核21 base＋21 candidate＋18 dependencies及v4原件；九檔 patch逐 hunk 套原文重建全部新內容，prior module AST只變 consumption及clock writer兩函式，其餘變更限定scratch import或明示測試。純記憶體SQLite執行原三helper：沒有later時 absent／empty 均unconsumed，有later時兩案均unknown。Writer 的 exact binding／base／hash／consumption讀回已在 BEGIN IMMEDIATE與commit之間；真writer failure／resume與真daily consumed交錯測試內容已核，未執行完整reader／writer或runtime race。

收據 `root/p08_seed_v2_review_2b5469a59c1c4a62ac7b8ed210ef611b/receipt.json` SHA `dbfdb4d88d3a7f5dcf32b071373fe49585755307619445e5931aaa1a61f1d215`。Root另核新existing-clock分支在SQL byte/type預檢前materialize receipt_json，交owner補有界讀取；窄v3 sibling freeze SHA `857476db66da8f3d4bc6b6f13c74feb472cd36388bcc205aeadf481b2d851920` 已回，待root審查。V2與v4保持原件；完整MA／KD生命週期、績效／benchmark、正常UI與M3仍未接受。

#### 保存、文件與接續

Root保存79份raw及Snapshot／本QA／目前架構／Manual四份前像至 `root/health_formal_seed_review_128321c02af048b683d4dfdfd932fb5e/receipt.json` SHA `b175dd7459fd03f540ad385a6236ef99e2084f3cd2d836fc3833a87078980503`。Coverage限定四份文件的本輪增量，Roadmap方向／驗收標準、target architecture、中央Index入口與UI來源未改。UI強制命令未因backend變更重跑；已執行Portfolio既有UI回歸，不能代完整Main。原始資料、main／push／發布未改；本輪所有root QA已終態，三代理續行Health五缺口／正常UI、P01 v4／完整效能、P08有界clock與績效。正式產品改動留WIP，完整目標active。

## Health v6 URI 診斷接續

原 full 4 PASS／1 FAIL 收據保留；root11 只補記拒絕 URI及callsite，固定 candidate、original guard、assertion與期限，結果仍為4 PASS／1 FAIL／25.07秒／native1，六actual PID origin clean、來源起訖相同。收據 `health_v6_full_8642e90e97b74e6f966c8eec08ce8774/receipt.json` SHA `26a06bdcaa4341d7c4818453198684568885b280e0975ea556ecb71a27e02ae7`；外 Job `single_owned_qa_af57ebb2c32d49bf80fc44376e73c9d3/receipt.json` SHA `fa9a6bbcd2447042c4a1698c1ba79c1c5db850065f3650adb7409ab4288b4b4b`、剩餘0、未強制清除。不能把這輪與原全組的通過數相加。

診斷證據確認 callsite 為 `PositionHealthDailyRefreshService._read_snapshot` → candidate `ReadOnlySQLiteManager.connect/_uri`。原 URI `file:C:/Projects/.../paper_portfolio.sqlite?mode=ro` 的 scheme=file、netloc空、mode=ro、decoded絕對路徑正確；護欄允許的 Path.as_uri canonical 為 `file:///C:/Projects/.../paper_portfolio.sqlite?mode=ro`，project serializer canonical 則是 `file:C:%5CProjects%5C...?...mode=ro`。拒絕是共用 manager URI 拼法與 existing canonical contract不一致，沒有證據顯示要存取私人根以外資料。新候選應讓 manager沿既有 `connect_read_only_sqlite` 使用 `resolve().as_uri()`，query-only／原immutable suffix／cancel handler與輸入日期內容不變；不放寬F12 guard、不覆寫v6 freeze、尚未修改正式helper。

診斷工具 root03 的child字串與 root04的prefix字串 SyntaxError 原始結果各自保留；它們沒有成功UI body，不能推翻已取得原v6 panel／TaskWorker定向證據。root05診斷driver與root11 runner在啟動child之前解析完整工具與child程式AST，取得上述真URI診斷。

新的canonical reader候選尚待封裝、root審查、reader原回歸與full Main/fresh PID原旅程。所有本輪Job terminal／剩餘0；唯一Luna Max葉片只做P01 v11靜態封裝。完整scope及Gate開放狀態不變。

## P01 v11 獨立核對與來源清冊 shape 缺口

Root 審查 v11 manifest `28459b99cd5845ca1216966dbc2d7f12657045acc6fbedf9d46dec992b8b401c`：641 raw pins／884 checks、125 index files、30 v10 原像與八段 full diff 全文重建一致。完整原 normal_view_protocol／fixed_inputs／semantic_oracle／candidate_query_overlay／source_freeze／runtime_environment 相同；七份活動 Python AST 僅接受已審閱的 exact metadata 比較及路徑／SHA／診斷版本識別。原 query/test/bridge/380 closure 保持。收據 `root/p01_v11_static_5098873408544b9f89fd641a2aee2180/receipt.json` SHA `70108fde562f26137cbdf0218ec4b0fa21d5390c9afd2222816e014da04d4b2f`。Root 前三次工具拒絕為自身 AST 版本映射／full diff hunk 後空白分隔處理不足，原結果保留；沒有把工具錯誤當產品回歸或改動候選。

Sandbox pure preflight native1，在 `Path(__file__).resolve(strict=True)` 遭 WinError5，尚未進入 store；收據 `root/p01_v11_preflight_6ef6dc7dbee94bbf91574d6ea76bfeba/receipt.json` SHA `98523bdf471e3455cfb3164bd4ee7ef2d36e015e938763e22d5ff1ff4a6b8e53`。同一固定候選／私人環境／Job 上限在 host 重驗，原路徑可解析；pure preflight native1 精確拒絕 `p01_v11_formal_query_preimage_not_preserved`，收據 `root/p01_v11_preflight_f6d5161bf4d44941a97bb316b53be644/receipt.json` SHA `948fb37c67852c9397b210d25f0a43e79ba8b9e3563c9ecd00402d88b9b8404a`。兩輪來源 pins 相同，沒有 origin probe 或完整矩陣，也沒有新 p95。

確定根因：原 `runtime_product_module_paths_sha256` 是 repository relative PATH→SHA 清冊，但 preflight／supervisor／runner 以 MODULE 名查該表後與 PATH 相比。正式 query 的 module→SHA、relative path→SHA、實體 raw bytes 與 overlay replaced_formal_query 都一致；錯誤在三個新增 query-overlay 查核入口的表形狀假設。v12 新 sibling 同步修三處，以 exact relative path查原 path→SHA、另保留 module→SHA 與 overlay exact path／SHA；原清冊、51 modules、380 closure、query/test/bridge與所有門檻不變。原有效篩選 p95 446.3604 ms 仍未達 strict <300 ms，不以預檢修正授效能接受。

所有本段 root Job 都 terminal、remaining0、未依賴強制回收，process／Job handles 關閉、mutex 釋放；讀回12程序與8 GiB記憶體限制。Host 唯讀盤點當時可用 RAM約23.87 GiB、22 Python共約1.15 GiB RSS，沒有命中本任務QA腳本；完整建立時間／父系／來源清冊省略所有 command line。此盤點不能代替 Job membership 作為所有權判斷。Sandbox CIM 拒絕所生成的 null欄位盤點不作證據，採 host fail-closed有效盤點 SHA `34dccc2e6feb1a48f19978ab0d6826aae777a0ccf7d462dbb5f0bb6bb4ee9c52`。

Health v7 的 canonical readonly URI候選與P01 v12僅由兩位Luna Max靜態葉片續辦；葉片無Python／pytest／mypy／compile／import／背景程序。完整scope P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4保持開放。本段只新增 ignored raw／helper與四份狀態文件增量；Manual／Roadmap／架構／Index入口無行為變更。回滾限本次新增段落並參考packet內逐檔前像，不覆寫其他owner修改。

## P01 v12 預檢通過與長路徑阻礙／Health v7 完整差異拒絕

P01 v12 三個 QA 入口已改為 exact relative PATH→SHA 查核，module→SHA 與 overlay path／SHA 另行保留。Root 獨立核對 704 pins／1,022 checks／185 index files／45 v11 原像與八段完整差異；七份活動 Python 除精確三處清冊形狀修正、版本與路徑／SHA 身分外 AST 相同。原 protocol、fixed inputs、semantic oracle、source freeze、runtime environment、query／test／bridge 保持。靜態收據 `root/p01_v12_static_391cc4c68bd44edcaa3d70f62186ecea/receipt.json` SHA `02d5fbb040252c824019ded2cd52cec528c004080d6d3fef8825b8f426b05959`。Root 工具自身普通長路徑讀檔與過廣的 30→45 替換失敗原件保留；有效重建器只修 inventory 比較，不改原暖樣本30。

同版 host pure preflight **native0**，8 formal／51 product／80 runtime／594 package／380 nested closure 核對通過；704 pins 起訖相同、pycache 空、store access0。收據 `root/p01_v12_preflight_b13ef2f1981641fcbbb490d84ddb962b/receipt.json` SHA `86807fbf4f848c197821e0fa7fcb9ebb9036a791abb25f79384748087377edbd`。fresh origin 階段 **native1**，在 `_execute_query_overlay_origin_preflight` 的 role directory mkdir 遭 WinError206，尚未啟動該 probe；實際目錄255字元。收據 `root/p01_v12_origin_27af544506804226a2d9d764f5903db2/receipt.json` SHA `48f69b9bb569ad57681d1e5cdff1a503268f0059940e9843579b96b888edd847`；inner SHA `4c4e18fb444d73a1b40f69b92181a1407f485d69ca91a4e0834bacb8d6d48944`。來源相同、無新完整矩陣／p95。短 sibling m13 正補 canonical QA output 與 private root aliases，原 role 識別、全部守衛及600秒期限維持；不修改 host 長路徑設定。

Health v7 manifest SHA `ac736735948881f49ebb06850c31ffb72e2f6f241e31bfcb5278bc3a538b00dd` 靜態候選已凍結。Root 在完整 formal patch 重建時拒絕：journey 新增 module pin 四行後2520行，但 full patch 仍為 v6 的2516行。候選 URI／journey pins 兩檔 delta 不代表 full formal patch 相符；本輪未匯入產品／未執行 Qt。原失敗 Job 收據 `root/single_owned_qa_09d5b1aee23b4c75a10b7973b1714a6c/receipt.json` SHA `94c08ac66ec1f1d063b2427a82615f87189cb54267bdcddcf9403aa2e23e1ca6`。v7 保持原件，新短 sibling hv8 沿相同31候選 bytes 重建完整11-target diff及清冊；reader取消／URI／full Main與fresh PID旅程尚待。

本段所有 root QA 使用單一 Job／mutex、8 GiB committed memory／12程序、啟動前至少8 GiB可用RAM；皆 terminal／剩餘0／無強制清除，process與Job handles關閉、mutex釋放。葉片只做靜態來源與候選封裝。原有效篩選p95 446.3604 ms仍未達 strict <300 ms；P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4完整scope保留，沒有完整工作包或Gate新接受。

Coverage Pass：本段只新增 ignored raw/helper 與 Snapshot／接續QA／active task／handoff 四文件增量；正式產品、操作入口、Manual、Roadmap、Architecture及Index無行為改變。回滾只移除本次段落與Snapshot新列，使用 packet 的逐檔前像比較，不覆寫其他owner dirty內容。

## P08 v31 原像／完整差異／原回歸與日曆 projection 終態

v31 manifest SHA `a6b45b955969c2e9913db6bf95d6ebc63613bf6377d980ba8f92ffc983a9d93a`，276-entry fixed chain SHA `1e986ab8fc326ab5b12260bfe1f7902b9918c64c827b286665789ae7bf531d2a`。Root 獨立核對915 pins／418 AST closure／28活動來源、14 product＋2 package、33 formal pins，v29原98檔與v30原131檔及保存副本吻合；25活動 product／tests／fixture 除完整 namespace與projection檔名重綁外逐檔等同v30。完整formal-target proposal／fixture05全文16段、v30actual一段、v29rebound兩段均重建一致。原fixture05的393＋7 assertions AST完整保留，沒有刪除或鬆斷言。收據 `root/p08_v31_static_c4cd553ceb6e49689467c6bcd1d3c318/receipt.json` SHA `596cb3a27c6e23841dba262f2f553c2e7c0a2dafebb454e78d22b4aa0d5f3834`；root01自身未處理rebound舊測試檔名的失敗原件保留，root02只修正既定rebound身分映射。

Host fresh origin **native0**，實際14 product sources符合固定path／SHA，922pins起訖相同、sourceguardclean；收據 `root/p08_v31_origin_4fb10e02155b41188ce718e7a13cd7ea/receipt.json` SHA `95b0ac232034c9769c868b1d632c7dd63370093d552e04ab1be618adca432082`。同版正常mypy **14 sources／0 issues／native0**，923pins與來源守衛正常；收據 `root/p08_v31_types_ab87b78d03a741f2bbbb0aa4cb66e490/receipt.json` SHA `fca80efe6d2a2549f7a8df9238f1185814871f367d3fd5cac9edf0afe0a61006`。

新增projection＋原candidate-origin測試 **11 PASS／4 FAIL／5.71秒／native1**，923pins不變、origin clean，收據 `root/p08_v31_projection_72daf03b161949459bdd1308fdd68958/receipt.json` SHA `e3735f90dc8bb1ff72a4cdc6f41a52d7892467945991906f66db8ed2c20216b2`。兩案把Path傳給明訂exactstr的locator；一案只突變outer status而未同步source evidence，正確遭source_projection_mismatch；origin測試要求原exact v1五欄位，candidate metadata改v2而被判malformed。Hash-only的live mode搭cache shape與complete_year=false也僅證明序列化敏感性，不是合法producer eligibility；限制已在候選README與mode_shape_review明記。原負例與product guard保持。

原八檔全組 **57 PASS／5 FAIL／1 skip／106.16秒／native1**，923pins起訖相同、9 actual PID origin clean、pycache空。收據 `root/p08_v31_suite_aa9538cf506146ca8dcc3042065e7a08/receipt.json` SHA `ef4c2831ca320419e4b19ba2032f671e394b95ad29c438c05843590a89eb7b4d`。JUnit確認真MA source→intent→共用engine→daily→fresh public read旅程通過（60.752秒）、KD lifecycle UNKNOWN／hold／entry-budget cap案例通過；真batch→daily writer→消費後seed-prior reopen與fresh public seed prior讀回也通過。五FAIL均為manual minimal MA／KD identity gate fixture缺schema4新增clock欄位而先拒絕，未達原確切database_identity_mismatch／replaced負例檢查入口；不能改expected error來當通過。短p32只補QA封套、exactstr輸入、合法內外一致hash vector與原v1 origin metadata；14product邏輯不變，原393＋7及所有負例assertions保持。p32仍待完整同版QA。

本段所有Python均root序列執行，單一owned Job／mutex、8GiB committed memory／12程序、啟動前至少8GiB可用RAM；所有Job自然terminal／remaining0／無強制清除，handles關閉、mutex釋放。原失敗、fixture與私有診斷輸出完整保留；subagent無Python／pytest／mypy／compile／import／背景程序。沒有正式套用P08候選、沒有授P08／M3或其他完整Gate接受。

Coverage Pass：只增加ignored raw/helper與Snapshot／接續QA／active task／handoff四文件增量。Manual／Roadmap／Architecture／Index沒有正式行為變更需同步；回滾限本次段落與Snapshot列，packet保存逐檔前像，不覆寫其他owner dirty內容。

## Health hv8 與 P01 m13：精確失敗位置、資源終態與接續修正

Health hv8 manifest `7402101d8269e1420acaedeba0662ca67d7a6485fd1a1145e748fc1d6b69cb95`，root 698pins／1355checks／11完整targets／2delta重建通過，保留原74assertions及process deadline。SQL僅改canonical `resolve().as_uri()`，另29檔與v6相同。完整閉包再納原conftest及其literal pytest_plugins，最終988pins／779modules／16embedded AST。首次reader因未列conftest被守衛拒絕，原件保留；完整閉包後原readonly＋URI測例 **10 PASS／1 FAIL／1.54秒**。六URI cases均通過；原TaskWorker取消真recursive SQL案例沒有cancelled訊號，屬SQLite取消例外與既有BacktestCancelledError接線缺口，不能把真SQL錯誤一律當cancel。收據SHA `fe8203b33b0a092fd9f26a0a50b3b5ba89d106e941087f0ee5386dd232031374`。

同版原Health五旅程 **5 FAIL／17.96秒**，六actual PID、來源起訖相同、guard clean。全部停在helper載入後的blanket changed-module assertion：candidate app package已安裝，F12 helper正當載入新增SQLite candidate也遭拒絕，未進Main旅程。收據 `root/health_v8_full_ccdda60876814cad98400e5aa974f9dc/receipt.json` SHA `c8236ae8410c80c3cc440cd5ea4a9c5752140ecdf311670f17c1f7304970c12e`。hv9只補專用取消例外繼承與SQLITE_INTERRUPT＋callback明確確認，保留真錯誤；helper後改逐一exact canonical path／SHA核對已載入模組，overlay前禁載仍保留。hv9尚未runtime驗證，沒有正式套用或授Health完整接受。

P01 m13 manifest `c55d3f80db8190d3118ef902736ebf229516854f46a56bc4668b6bfcc18b3af4`，root743pins／1065checks、17直接v12前像＋185歷史引用、八全文差異逐行重建＋raw source SHA，所有原protocol／inputs／oracle／query overlay七組核心欄位一致。463展開路徑最大199字元，僅允許具名來源身分與短run目錄、token／role檢查、path_length_inventory核對等精確AST改動；剩餘AST差異0。Root初版把特殊全文差異視為git-new-file格式，後續解析錯誤屬審查器問題；原失敗Job收據保留，不當產品FAIL。靜態收據 `root/p01_m13_static_59ab22185fd6451b8fcd58bca4ec108a/receipt.json` SHA `1edb917d78e9b41c7e056ad4107f75b378ccce2f4c28fe4199b262c4943bcfa0`。

Host pure preflight **native0**、743來源pins不變、store讀取0、pycache空；origin已越過長路徑並啟動真probe，fresh PID37620 import event核candidate query與formal parent exact path／SHA，但fresh child **exit101**，原capture_output stderr尚未進失敗收據，不能推斷原因或聲稱origin通過。Root收據 `root/p01_m13_origin_8ce4b0a26166490186223a91ac8b3a90/receipt.json` SHA `bf9838e5f0806490e3aa75611afc62bc8611aea5e9138a5833542f1d97a1835a`。m14僅補具名fresh child失敗stdout／stderr／PID／原exit證據，m13封存不改；原sealed1457／1000rows20pages／5cold＋1warm／每操作30samples／600秒role／strict p95<300ms保持。此段尚未重跑全六角色矩陣，原446.3604ms FAIL仍有效。

上述各QA皆root序列Job、8GiB committed memory／最多12程序、至少8GiB可用RAM才啟動；均自然terminal、remaining0、無強制清理，handles關閉與mutex釋放。Subagent只做靜態候選。Coverage Pass僅Snapshot／接續QA／active task／handoff四文件增量，沒有正式產品變更需更新Manual／Roadmap／Architecture／Index；整體P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍WIP。回滾只限新增段落與Snapshot列，逐檔前像與raw證據保存在具名ignored packet。

## P08 v32 原始斷言、15 projection 與完整八檔結果

v32 manifest `167630265d730dd3ae04a5061e8a20955899718a145d79642927dcbf66cf9b58`，42-entry chain `3be74b19d09fdf01609d67240ed3f661e45bbd7bc0bdc3f1380872b207cdac84`。Root961pins／418closure、16份v31→v32完整delta重建一致，原393＋7 assertions AST完整保留；14產品除namespace外逐bytes等同v31，原primary測試只改兩個minimal identity gate helper，其餘AST相同。靜態收據 `root/p08_v32_static_c39c3233afb24543b104d68aeab4abf0/receipt.json` SHA `c58f6c7c9711a0035c052044f58ecf14e03439dbd6f782927472f8ebc66fb4b1`。

第一輪projection14PASS／1FAIL，原origin測試明列candidate.__init__載入同一固定initializer，root02守衛只接受canonical package name而拒絕。Root03由兩項固定package_files產生精確alias map，要求同路徑、同SHA、canonical＋.__init__且限定同candidate namespace；其他產品模組仍exact name/path/SHA。原失敗收據SHA `13fd6695a376d4051b1e6363300dd757be37436de6039624ad8000e3d24008b6`保留。

同版新origin native0、14真產品、968pins起訖相同；projection＋原origin測例 **15 PASS／4.71秒／native0**，969pins不變、guard clean，收據SHA `955bf5dc6fa6702fd29e20ae1291e81a1cd8593506b86c86b880c677e28c7426`。原八檔 **60 PASS／2 FAIL／1 skip／104.69秒／native1**，9 actual PIDs、969pins不變、guard clean；收據 `root/p08_v32_suite_450c1f78ba4b45348c8e4df6823fbe13/receipt.json` SHA `1d1076b04a1a9406914af7b408171c9d761f6c15b2be7258b6de18a4767ecb66`。三MA identity mismatch／replaced負例已到原指定gate並通過；兩KD helper仍把saved_at／available_at datetime直接交canonical JSON而TypeError，未到DB gate。短p33僅補isoformat與namespace重綁，root先定點核兩KD＋三MA，再原全組／15projection／14mypy同版。正常mypy本版 **14 sources／0 issues／native0**，收據SHA `eb4476e557bcd52926caddb271eff990359723c3c3aed6d679a412a321698ec4`。

上述Job均root序列、8GiB committed-memory／12程序、至少8GiB available RAM才啟動，自然terminal／remaining0／無強制清理、handles關閉／mutex釋放；沒有subagent啟Python。完整P08／M3與全產品Gate仍待。Coverage只增加四份狀態文件增量與ignored raw/helper，沒有正式產品變更需同步Manual／Roadmap／Architecture／Index。逐檔前像與原失敗原件保存，回滾僅本段與Snapshot列，不覆寫其他owner內容。

### Health hv9 未完成封裝，不進 runtime

Leaf停止後只讀核對：hv9/candidate-freeze-v9.json仍為hv8 manifest bytes，SHA `7402101d8269e1420acaedeba0662ca67d7a6485fd1a1145e748fc1d6b69cb95`，sidecar/schema/freeze_id/root仍指hv8；full patch早於callback ContextVar變更，不是有效hv9 freeze。Root未執行hv9。接續新hv10以已審hv8為權威基線，最後才產生同版manifest與全文patch；原callback進度處理器的瞬態throw後回True須保存first exception與SQLcause，不能誤分類cancel。hv9原像保留不修改。Root目前所有已報QA均Job0／handles關閉／mutex釋放，subagents只做靜態工作；完整產品／Gate仍WIP。

## P08 p33 同版原八檔通過（仍未接受完整 P08／M3）

候選 `output/qa/p33_calendar_projection/` manifest SHA `c64747ab0914369daf1e5904510b2edeeca702e47dbf0fc10ceb347ada8b83a6`；root static 收據 `root/p33_static_ab6a027fe0934803adc6ab459b1645ad/receipt.json` SHA `b008fb2c1adc954b7de0f172be08806e9879d4938b9d3023dccef2216ba81c17`。1004 pins／418 closure、15 段 delta 精確重建，原393＋7 assertions保留；14產品除namespace完全等同v32，唯一fixture payload差異是KD helper三處ISO時間序列化。第一版root reviewer錯把AST unparse末項沒有逗號當成missing field；原失敗保留，改用精確三項AST轉換後通過。

真14產品 origin、五項原identity gate均通過。原八檔 **62 PASS／1環境skip／0 FAIL／105.65秒**，9 actual PIDs、1012 pins起訖相同、source guard clean；收據 `root/p33_suite_bb122be1bb2a48c19fb4f9f6a9ae3416/receipt.json` SHA `e3c1282ff7a080f47fe7c117dfab87627e32cddf22b93e98351c9161f08fcd8b`。skip仍為Windows建立reparse alias缺權限WinError1314，不能算產品pass。Projection **15 PASS／4.67秒**、正常mypy **14 source files／0 issues**，同版來源與斷言不變，各收據固定於本次handoff索引。

本次報告的P08 Job均自然terminal／remaining0／無強制清理，handles關閉及mutex釋放；單一Job、8GiB／12程序、至少8GiB可用RAM才啟動。Health或後續Job之即時狀態另依具名收據，不以本段推定全部程序已結束。未修改正式產品或資料；完整P08尚缺正常多策略績效、benchmark、歷史比較與正常UI之同版驗收，M3／所有全產品Gate保持open。

文檔Coverage：僅Snapshot／具名QA／active_task／handoff四檔狀態增量，沒有新使用者可見行為；Manual／Roadmap／Architecture無行為同步需求。回滾：保存四檔前像，只撤本段及Snapshot新增列，不覆寫其他owner變更；不可變候選、原失敗與raw不刪除。原收據不遞迴複製，以SHA固定引用。

## Health hv10 取消通過、真 writer 缺口與 P01 m15 預檢終態

hv10 manifest SHA `a4c56ac83f650fd54f3530617e09a7823c5cfaf7ca1e14c7ba6fcbf08faea0e7`。Root獨立754 pins／1446 checks／11全文＋2delta重建，29原候選bytes相同、原74 assertions與所有旅程／期限保留。URI取消案例依新專用例外增加原SQLITE_INTERRUPT cause查核，其餘URI原方法保持；SQL只改取消類型、精確interrupt翻譯、第一callback錯誤與ContextVar reset。原TaskWorker與readonly加URI負例 **66 PASS／2.14秒**；包含短暫callback拋錯後回True、巢狀範圍不外漏，原TaskWorker genuine error仍error。Static SHA `28878f29024883162bbcb108992ab996d42014561d9bbca8383fa06f1d2f7ce9`，reader SHA `8bbe9d045f0e5aa6b2444bb796bc7b199b9a1596536a784fde29339bc2f8e11d`。完整closure1046 pins／781 modules／16 embedded AST，含原conftest/plugins及兩份Task取消回歸。

原五旅程依序跑三次，每次 **4 PASS／1 FAIL／六actual PID origins clean／pins起訖相同**：

1. 22.28秒，writer witness路徑275字元，`os.open`報FileNotFoundError；父目錄存在。純stdlib create-only私有probe證258/259字元成功、260/275字元Errno2，SHA `5eeb34f30e0a1e9d4cbc7aa5712dac7f376be4d46271dcdf2b0b4de3447ce612`。
2. 24.57秒，root私人目錄縮至h＋3hex／pytest p，witness通過，archive臨時檔用extended syscall開啟後，F12 canonical普通lstat在285字元誤判缺檔；原guard拒絕保留。
3. 23.09秒，root driver僅以標準TmpPathFactory.mktemp('t')產生每test獨立短目錄，原候選／原旅程／F12守衛bytes不變。Witness及archive publish通過，真public reader才暴露 `position_health_saved_archive.py:391` `_required_text`多傳第二參數，helper只接受一參數，TypeError。收據 `root/health_hv10_full_eb67ba1f72214628abcae49440fa183c/receipt.json` SHA `72d2a8ee6212830179f8aa6d63a6cf8759dc6551d0e54b28b6b8240a21cb65ee`。hv11僅修八處caller arity及來源pin；正常Main／回訪與新PID仍未接受。

長路徑是現存產品witness syscall／測試guard IO邊界缺口；短QA路徑只允許驗證後續流程，不能算長路徑已修。所有原失敗保留。

P01 m14差異拒絕：preflight段hunk宣稱15行實際13，原source未改。m15新actual Git差異四段重建、796 pins、原m13→m14診斷argv/cwd/env/成功斷言及核心七項協定獨立核對；m14差異未追認。Root處理Git缺末尾newline標記的兩次自有parser錯誤保留，最終static SHA `8e3df1bf9e3044963fb668f44a6d1507c44ec2fec15a580e465ca22eddf677d0`。Host preflight native1、pins不變、未碰store：manifest status被改而入口嚴格要求原v13 status。收據SHA `55098508283e3cfee0b49d3b160c9dc6046ed6a006c20172f21077fde3765c65`，m16恢復原schema/status並靜態核所有入口metadata讀取。尚無fresh stderr／新矩陣／p95；原446.3604ms FAIL與strict<300ms保留。

以上所有已執行Job自然terminal／remaining0／無forced cleanup／handles關閉／mutex釋放；root目前沒有活躍QA session，subagent僅靜態。單一root Job、8GiB／12程序、至少8GiB可用RAM政策維持，未全域kill其他Python。沒有正式產品／資料變更，未stage／commit。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍open；各綠燈只是具名窄範圍，沒有完整包或Gate接受。

文件Coverage僅四份狀態增量；無使用者可見行為故Manual／Roadmap／架構無本輪行為同步。回滾只撤本段與Snapshot新列，四檔前像於具名handoff；候選、原失敗raw、原資料不刪除、不覆寫他人未提交改動。原raw以SHA固定引用，不遞迴複製歷史樹。

### Health helper arity 與 P08 績效前像核對補記

Root唯讀AST核對hv10 archive：40個頂層helper、181處直接同檔呼叫、0處star展開間接呼叫；唯一八處錯誤皆為_required_text多傳第二參數，其他173處arity符合。收據 `root/health_archive_arity_9df8cb2aea85487e82ee3f93f6385f6e/receipt.json` SHA `21aa167132a056191e98a62b460421b216030a1bcff22eea606d998af0e5efda`；owned收據SHA `ce40f2b1bd65df9da252d285f7da0e2316d3995c9244d0e17b6a8e7748354984`，自然Job0、無強制清理。hv11仍待封存／原旅程驗證，不以static核對宣稱功能通過。

P08績效靜態盤點已封存：`output/qa/p33_perf_static_audit_20261011/audit_manifest.json` SHA `5c6c10e667368b05823bf73a01362998f6efe5be1e8dec745671dce0d65a73bd`；README SHA `ab1beaf9032ec8a0d962a2c9efb8a3b5eae775e85d005c1a883ecf1e9e328037`，root實際讀取並核SHA。最新perf03仍是未接受fixture04核心，不能覆蓋已通過p33；p34以p33核心另接六個績效模組與六份原focused tests，14-core origin契約仍固定，145個既有績效assert與400個core assert均須保留。帳戶獨立損益、benchmark、歷史比較與正常UI之完整P08／M3仍open。

本補記僅四份狀態文件增量與先前root新增段的繁體用詞修正；四檔前像另存，回滾只撤本增量。未修改正式產品／原始資料、未stage或commit；root沒有活躍QA session，葉片靜態工作仍在進行。

## P01 m16 真 launcher 根因與 Health hv11 真公開讀取

P01 m16 manifest SHA `c10383a7e3371afb3ab2f17dbea6b7e382fa322f3824a6e3620fdbdda0170cd0`，index SHA `96d82c954a76d07af33693c9761bb9ac80997920a2f37f9711baaf4716e81d80`。Root824 pins／21封裝檔／六直接前像／四段完整差異、原七core與matrix_state及schema/status、必要artifact path/SHA相符。Root最初三次自有reviewer讀取旧欄位／未解析Git帶引號Windows header，原失敗保留；最終adapter按實際schema與Git quote解析，未改候選。預檢 **native0／pins不變／store內容0／pycache空**，SHA `cbfdf6f931ecea46460ee89a625c954f3f6b76eda2e19ab1590e8fc9f19ebd3f`。

真正origin仍native1；此版首次保存fresh launcher原始stdout/stderr/PID/argv/exit，fresh childPID43840、probe CPython18408、exit101，stderr為venv redirector「Unable to create process using ...」，不是Python guard traceback。固定raw `m16/runs/o_a3abcc653dc6/roles/o/fresh_child_failure.json` SHA `8ff526b2f9ab0e333da92104fd05fd2bd3cdb99cd5938521953d9ea1e4050ad7`；root origin SHA `fadee81981ec2e08159ec8f02ef532a4e31451d0b1ead72d5db42643baf5582e`。

Root純stdlib、無產品import、有界nested Job診斷證：內層cap3時第二venv chain的base Python無法建立而exit101；cap5時nested native0。兩案先assign suspended、自然排空0、handles關閉、無強制清理；收據 `root/nested_venv_job_limit_2dc1d418c9414d479f57dcb2d02f27fd/receipt.json` SHA `6d9337c571a2bb4a9de0893f8c9df80f1561ec479957485676a54b44250aac51`。普通matrix的Qt/ThreadPool reader為執行緒，非另一組OS程序；六角色仍序列。m17只調內層當前QA Job cap3→5（兩層venv/base共4＋console保留1），root外層12程序／8GiB與至少8GiB可用RAM才啟動不變。原1457 entries／1000 rows／20 pages／5 cold＋1 warm／30 samples／600sec／strict<300ms不變；原446.3604ms FAIL仍有效，完整matrix未啟動。

Health hv11 manifest SHA `7be494bf40abac638944c3b32c0ec7ebe3b00f30cd9853d50925c2d24c72d073`。Root811 pins／1503 checks／11全文＋2delta、八caller精確AST轉換通過；其他29 candidate bytes相同、74原外層assert与URI方法保留。Delta最後payload行缺傳輸LF，root只對固定archive-pin末行补一個LF解析，原raw SHA不改、各hunk和完整source逐行相符、source raw SHA另行核驗；不宣稱原delta可直接自動apply。完整closure1103 pins／781 modules／16 embedded AST。原readonly／TaskWorker／URI回歸 **66 PASS／2.16秒／native0**，SHA `688909c39b267f51f7a578d60fb0221ec998f1d46f94b2e77f04ec273480fdbc`。

原五旅程 **4 PASS／1 FAIL／23.38秒／六actual PID origins clean／pins不變**，SHA `cdb7589272e850ada0ffaf05bbe71178e164e8957d5f0d094445356b4be18766`。真writer已越過公開reader、snapshot／locator／hardlink負例，reparse reader也按原指定code拒絕；終於卡在負例finally的 `os.rmdir(junction)`，F12寫入守衛拒絕alias清理。hv12只把自建junction保留為QA證據，finally改三項唯讀檢查（reparse attribute／exact target／原receipt SHA），不繞過或放寬F12、不改產品。正常Main／返回／新PID完整旅程仍待。長路徑產品及F12 canonical-stat gap仍open。

所有上述Job均自然terminal／remaining0／無forced cleanup、handles關閉／mutex釋放；root目前沒有活躍QA session，三葉片只做靜態封裝。所有source失敗與root自有adapter失敗保持原始不可變收據，原件不覆寫。P34依已封存績效盤點繼續；六績效模組不授qualified性能，來源event clock／官方session／共享fill cost policy三個eligibility blockers仍有待完整P08實作。

Coverage僅Snapshot／具名QA／active_task／handoff四份狀態增量；無正式產品／原始資料變更，未stage／commit，無使用者可見變更需同步Manual／Roadmap／架構。四檔前像已保存，回滾只撤本段與Snapshot新列，不撤他人變更或刪除QA原件。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4維持原scope；沒有完整包或Gate接受。

## P01 m17 真 fresh-child 環境問題與 P08 p34 首次績效執行

P01 m17 manifest `d939acb90b52bf46918b99dfe1f1c039071fb2e4b9c6af54e7c6c9af856214a8`，root 靜態 843 pins、14 封裝檔、四完整 delta 通過；唯一執行限制變更為內層 Job cap3→5。預檢 native0、store內容0、pins不變。Origin已越過原 launcher101，但 native1：fresh child 啟動期 sitecustomize 拒絕 `PYSIDE6_OPTION_PYTHON_ENUM,QT_QPA_PLATFORM`；runner在import期明確設定Qt offscreen，probe import runner後使用 `os.environ.copy()` 傳給fresh child。Shiboken DLL含另一變數token，native setter尚未證明。m18僅在import runner前保存已通過 exact allowlist 的啟動環境快照，明確傳給helper；不放寬bridge/allowlist。原1457 entries、1000rows、20pages、5cold+1warm、30samples、600秒與strict<300ms保留；原446.3604ms FAIL仍有效，完整matrix未執行。

Health hv12 manifest `976c3d064b48c99ac02ac50aad1fdc3613a697b0473cbb4317063dedf641a806` 已封存，但root拒絕其delta：context行缺 unified-diff marker前導空格。全文11target已重建；尚未完成候選後續審查，未執行hv12。新hv13只修封裝格式、31候選bytes維持hv12，不得改guard或測試意義。原hv11 reader66PASS/full4PASS1FAIL與長路徑gap仍有效。

P08 p34 manifest `b6573fae4e6b5788a7273cbb71856cf926263361578d7347d2f3e8e34afb99e3`：root1092pins／447遞迴閉包／52完整新增patch逐行重建；p33核心14模組與原測試及六績效模組/測試均僅namespace替換。核心現有401assert與p33相同，原400保留；六focused原像143assert精確保留。root早期adapter誤把400/145當成目前count，兩次自身assert失敗原件保留；以固定原像實際count校正，未刪或弱化候選assert。核心v1 origin維持五鍵/2init/14，績效另六module-map。

20實際候選模組origin native0，1099pins不變、guardclean。首次六focused＋獨立origin測試 **28 PASS／13 FAIL／10.30秒／native1**，1100pins不變、guardclean；raw收據 `p34_performance_9ed1bfeea0804871b4886cbc60954473` SHA `7a2d97db655c32f9c727be7904baedfb53f9d7c6460d0a5efad20ecec9871a5f`。錯誤包括四個tuple欄位fixture ValueError、三個writer回傳None當Path、manifest schema/canonical JSON及benchmark route identity；需先分辨fixture與產品契約，不改expected錯誤碼掩蓋。尚未跑p34核心全suite/projection/mypy；P08雙帳戶、資格、歷史比較、正常UI、返回與新程序仍未接受。

上述九組root Python全部自然Job0、handles關閉、mutex釋放；沒有強制清理或並行Python。subagent只做靜態工作。最後p34性能組終態available memory為18,358,956,032 bytes（取自收據，非即時RAM）。外層12程序/8GiB及啟動至少8GiB RAM限制維持。

四份狀態文件增量已保留前像及固定raw收據；無正式產品或原始資料變更、未stage/commit。無使用者可見變更需同步Manual/架構/Roadmap。完整P00–P14/M1–M3/F01–F23/UX01–UX24/G0–G4 scope保留，沒有完整包或Gate完成。

## Health hv13 進入正常 Main 與 P08 p34 真正常型態檢查

hv13 manifest `0a2a48b3e2dae86e48dfd44ad5a75e46c35906595d32f038b2baf26d4ebfa7b6`。root867pins／1561checks／11full+1delta逐行重建，30候選與hv11相同，旅程唯一刪除自建junction改三個唯讀檢查；74原外層assert及URI方法保留。Delta原raw有正確marker與末尾LF，沒有做transport修補。完整閉包1159pins／781modules／16embedded AST。原讀取／取消／URI回歸 **66 PASS／2.31秒／native0**。

原五旅程 **4 PASS／1 FAIL／30.48秒／native1／七actual PID origins clean／pins不變**。writer已通過全部保存／locator／hardlink／reparse原負例，Main parent此次確實開始；現在 `_health_assert_candidate_loaded` 在 `from ui_qt.main import MainWindow` 後、建立Main並點Portfolio正常lazy載入之前就要求八個尚未載入模組，提前拒絕。需先核正常UI時序，再將完整required-set來源檢查放到正常Main/Portfolio載入後；禁止預先硬import冒充旅程、刪弱來源guard或原UI斷言。正常返回及fresh PID仍未接受。長路徑產品及F12 canonical-stat gap仍open；新候選的normal typing需canonical overlay以避免formal fallback混入，尚未執行。

P34另一次root自有stage路由錯誤：原命名performance_types的raw收據實際command為pytest projection，**15 PASS／5.34秒**；不能算mypy。錯誤runner/raw保留，新root02精確修stage路由。真正正常mypy command核六績效來源、**32 errors／5 files／native1**，來源pins不變、guardclean；收據SHA `008b784e2535b2f1fa1137dbd767b362e506d7d505cab4a0a50af6cee3053e4e`。包含locator helper回None被當Path、兩個 `_parse_aware` 少field參數、Decimal exponent未做型別收窄、route使用object及JSON欄位窄化不足。不得以Any/cast/ignore/suppress或降低政策替代修復。P34原28PASS13FAIL仍有效，核心全suite與核心mypy尚未執行。

所有本節六組root Python自然Job0、handles關閉、mutex釋放、無forced cleanup。目前沒有本節QA session在跑。機器唯讀盤點仍有IDE/MCP背景Python及graphify pair；本節未啟動這些程序，未有充分所有權證據前不整批終止。盤點時約17.8GiB可用RAM，非持續即時數值。Python QA仍由root序列執行、外層12程序/8GiB及啟動至少8GiB可用RAM，葉片無Python。

四份狀態文件增量保存前像及固定raw收據；無正式產品或原始資料變更、未stage/commit。完整P00–P14/M1–M3/F01–F23/UX01–UX24/G0–G4 scope保留，完整包/Gate均未接受。

## P01 m18 真 fresh-child 通過與原矩陣完整失敗證據

Manifest `86486be4b84cc9362400bd7f5d632f1b367a76d0c9c9d75da1b5d11c31328f0f`。Root864pins／14封裝檔／六直接前像／五完整差異及原probe AST guard、fresh-child code保留通過。第一版root reviewer漏正規化更新probe SHA，原自身失敗保留，第二版補必要對照後通過；候選未改。預檢native0/store0/pins不變；真fresh-child origin native0、probePID35688／fresh CPython44604，startup bridge/query/formal父initializer實際path+SHA皆通過、sealed store內容存取0。origin root收據SHA `9a86cd7447ba271176f7aed0cea6c226ff6d3400d47cb854bdcaf426edaef766`。

同版原六角色完整矩陣 **五cold passed/native0/cleanup errors0；warm_01第一筆page_flip失敗／native1**。warm完整DTO serial oracle及來源pin檢查先通過，後 `_assert_capability_claim` 拒絕 `read_page_capability_claim_count_mismatch`；postguard及finalization passed/source/store stable。這是取消能力觀察次數，未產出完整p95；1000rows/20pages/1457entries/5cold+1warm/每類30samples/600秒/strict<300ms與446.3604ms原FAIL保留。矩陣root收據SHA `53ebd6c407a439b41e5521b02ff264ad15c5c72095501d3306e7328a3d1e411e`，warm result SHA `751a29af2c2c8033c268a835c6e54e8872882d0df81943bf22c4123cdf63de6b`。

Root與葉片唯讀交叉定位：warm record先 `_compare_full_dto`，其serial oracle一般callback也會claim並被observer保留，然後才查剛才一個TaskWorker的claim，使oracle的None-capability紀錄混入。Initial/page_walk先claim驗證再oracle。m19只把原完整claim assertion block搬至source-pins後、oracle前，不刪或弱化len/index/TaskWorker callback/owner thread/capability要求，不丟observer紀錄、不改產品query/cache/oracle/測時邊界。新同版完整六角色仍需重跑，不能拼m18cold及m19warm宣稱全部通過。

全部上述五組root Python自然terminal/Job剩餘0、handles關閉、mutex釋放、無forced cleanup；matrix exec78150已terminal並關閉。root live-document helper觀察到矩陣已終態即安全拒絕，沒有發布過期live狀態。Health hv14僅移正常Portfolio載入後兩個完整source assertion；P35僅精準helper/type/canonical/header/fixture修正。葉片無Python，正式產品/原始資料均未變，無stage/commit。完整P00–P14/M1–M3/F01–F23/UX01–UX24/G0–G4原scope保留，完整P01/M2/包/Gate均未接受。

## P01 m19 600秒終態、Health正常Main旅程與P36同版回歸

P01 m19獨立靜態886pins、14封裝檔及原assert／oracle精確兩statement搬移通過；預檢與真fresh-child origin均native0、store0、來源不變。同版原矩陣cold01/cold02通過，cold03停在seq38 `strict_full_population_selection_started`，原600秒deadline到達。內層Job在清理前有3個owned PID、清理後0且handle關閉；外層自然native1／Job0。watchdog只有Python主線與自身堆疊，無Qt原生QThread堆疊，不能據此判定worker已死亡或已發出error。沒有新p95，原1000rows／1457entries／20pages／5cold+1warm／每類30samples／strict<300ms及446.3604ms FAIL仍保留；m20僅診斷訊號記錄候選待審，不重跑m19拼接成功。

Health hv14獨立靜態922pins／1620checks、完整11targets及delta1target／四hunks通過；閉包1214pins／781modules／16embedded AST，66 PASS／1.71秒。原五旅程4 PASS／1 FAIL／34.17秒、7個actual-origin PID clean，正常Main的Portfolio開啟→Watchlist→Portfolio返回已產出成功收據；outer比較因writer QA收據漏列 `health_observed_at` KeyError失敗，尚未進fresh reader。hv15只加既有DTO映射 `opened.read_model.observed_at or opened.source.observed_at`，30其他candidate bytes完全相同。Root970pins／1677checks、完整11targets／delta1hunk、74outer原assert與所有內嵌assert／deadlines、URI方法保持；閉包1262pins／781modules，66 PASS／2.32秒。同版原五旅程結果見下方具名收據。長路徑product與F12 canonical-stat缺口仍未解，完整Health/P06/M3/Gate未接受。

P35靜態發現兩個比較RHS漏 `_parse_aware` 必填field，未執行已知錯誤版本。P36補兩處RHS；root1215pins／447closure，實際p34→p35與p35→p36差異重建各39變更target／92及81hunks，所有刪除只在patch語義中核對、實際原包保存。40個活動Python完整授權差異、401core／143focused原assert保持、v2/v3全部10+15 helper calls arity通過；Decimal／PIT／qualification／reader guards未弱化。20個actual candidate modules origin通過。原績效41case為34 PASS／7 FAIL／12.09秒；同版core原八檔62 PASS／1 Windows privilege skip／104.85秒、9actual PIDs clean，projection15 PASS／5.07秒，六perf與十四core來源正常mypy均0 issues。全部來源pins起訖一致。仍缺完整績效、實際正常策略UI、comparison fail-closed與完整P08/M3。

七個績效失敗已定位：日曆可解析但identity drift落generic碼；real_metrics fixture未建立observation root父目錄；Windows `DirEntry.stat().st_nlink`恆0被誤判alias；四SQL guard錯誤碼大小寫與原契約不符。Root純stdlib三案證普通檔DirEntry nlink0／Path.lstat1、真正hardlink pair為DirEntry0／Path.lstat2，首次sandbox WinError5原失敗保留，host受限Job通過。官方依據：[Python 3.11 DirEntry.stat](https://docs.python.org/3.11/library/os.html#os.DirEntry.stat)。P37只允許錯誤分類、fixture前置目錄、可靠metadata及兩個error字串窄修；保持nlink==1與原type/reparse/SQL順序，STATIC候選待審。

Root審查器自身的README非Python列、Health predecessor重綁、delta/URI metadata形狀及scope review文字差異拒絕已保留raw failures；沒有為通過刪除產品guard或原測試assert。外層所有已完成Job自然remaining0、process/Job handles關閉、mutex釋放；P01 cold03內層確實使用deadline清理，不聲稱該角色自然成功。subagent只做靜態候選，沒有Python程序。正式產品與原始資料本增量未變、無stage/commit；完整P00–P14/M1–M3/F01–F23/UX01–UX24/G0–G4保持未接受。
Health hv15同版原五旅程 **5 PASS／0 FAIL**；actual-origin PID數 8，來源守衛clean／pins不變；具名root收據 `C:\Projects\PythonProjects\technical_analysis\output\qa\baldr_completion_20261011\root\health_hv15_full_ec8294e1835943969cecdec769f7648a\receipt.json`，SHA `bd054e7fef36be30592f521e8a51422eff64566a0296c8c6a2e9ae277690db74`。這是具名正常UI返回與fresh PID旅程通過，不授完整產品/Gate。


## P01 m20 同版完整矩陣與 P37 績效增量

P01 m20 原六角色已跑完：五次冷啟動與一次暖操作均自然退出，所有初始 DTO／20頁與90筆完整壓縮 DTO oracle逐一一致，來源與 capability 守衛保持。Root按原 nearest-rank公式獨立重算各30筆 p95：翻頁 **356.6717 ms FAIL**、篩選 **382.4615 ms FAIL**、全域排序 **210.1654 ms PASS**；原 strict <300 ms Gate 未通過，冷啟動 p95 24.4537864秒。Supervisor native0只代表診斷矩陣完成，不能作為產品Gate通過。m19 cold03的600秒失敗保留；m20沒有重現該timeout，未證明根因已修復。後續需對實際正常Qt路徑定位效能；不能重跑同版、改門檻或縮母體湊成功。Main UI實際產製1000檔、real-N、超過256歷史版本selector、EXE及原完整P01驗收仍開放。

P37修正四個既有失敗原因後，原41筆績效測試為 **40 PASS／1 FAIL／16.27秒**；四SQL guard後續斷言也通過，20 actual candidate modules origin乾淨，六績效來源正常mypy零問題，來源pins保持。剩餘失敗是fixture把seed reader clock固定在10/6後，10/7及10/9 cutoff被正確未來資料守衛拒絕；P38只允許fixture的clock context恢復及各階段clock綁定。P36 core62 PASS／1 Windows privilege skip、projection15 PASS及十四來源mypy是歷史同版證據，不冒充P37重跑。正式績效UI、兩帳戶正常產製／保存／新PID讀回、comparison qualification與完整P08/M3仍未接受。

程序管理：root一次只執行一組Python，CREATE_SUSPENDED後加入Windows Job才resume；8 GiB committed、12程序上限、至少8 GiB可用RAM及執行鎖保持。以上已完成外層Job均自然排空，process／Job handles關閉、mutex釋放。subagent只做靜態候選，下一組不得在前組未退出時啟動。正式產品與原始資料本增量未改；未stage／commit。P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4整體仍未驗收。

Health 八模組正常 mypy 的 v1 helper 在 preflight 讀取不存在的 metadata key 而 native1；root因缺 result 收據退出125。未建立 mirror、未執行 mypy，不能計為產品型態失敗。原失敗保存；v2僅修正 reader key，954來源 guard及清冊bytes保持。

修正後同一 Health candidate 的正常八根 mypy已實際執行：native 1、mypy exit 1、module path proof fail，完整 mirror 3079 檔、核對 firstparty modules 1042；來源 pins 不變。原 mypy.ini 的 UI ignore_errors=True 保留，此結果不代表嚴格 UI 型態驗收。詳細原 stdout/stderr及mapped paths保存於具名收據。 原正常型態輸出為3 errors／3 files：SQLite read-only的exception型態、Health personal_paths參數型態、既有calendar private helper缺operation；需核對第三項未提交變更歸屬。module proof另有packaging外部套件名稱與本機同名目錄誤判、BuildSource根紀錄漏讀；均保持失敗，待精確靜態診斷，不能把path proof失敗忽略為通過。


## P38 固定產品與 fixture2 同版回歸

Root獨立核P38 1341 pins／447 closure，完整patch重建、401 core及143 performance assertions保持，產品僅namespace重綁。首次root審查器假設control path為package-relative而拒絕；新審查器依實際repo-relative path核對，前代patch的移除另由固定predecessor manifest與完整patch刪除語義確認，沒有實刪p37原包。20個actual candidate modules origin通過。原41績效為40 PASS／1 FAIL／10.19秒：seed writer建立seed時已自動保存可得時鐘，p38只包後續explicit record的context太晚，原時間assert正確拒絕。

Fixture2僅把兩個既有context擴充至包含create_cash_seed及explicit record；P38全部產品bytes／namespace保持，沒有再重綁全包。Root1349pins獨立逆向兩個assignment移動後，完整測試module AST與原檔完全相同；143原assert／expectations保持。QA guard僅新增一個具名test path、兩個精確pytest/canonical module aliases，仍必須命中closure SHA；candidate module identity、全部舊scratch拒絕保持。新封套20actual modules origin通過，原41績效40 PASS／1 FAIL／12.00秒，兩個seed可得時鐘assert通過後，停在**V2第一個intent**的 `p08_intent_calendar_clock_not_causal`（fixture605→helper275→reader1356）。沒有完成metrics/save、later session或fresh PID；先前root口頭位置判讀過後已更正。

同一固定P38產品／fixture2 QA封套，六個績效來源與十四個核心來源正常mypy均零問題，projection15 PASS／4.51秒。核心原八檔摘要見下方具名收據。來源pins起訖一致、實際origin守衛clean。本增量沒有正式產品或原始資料修改；未stage/commit。所有已完成外層Job均自然remaining0，process/Job handles關閉、mutex釋放；root序列、8GiB／12程序與8GiB可用RAM保留，subagent無Python。

P01 legacy selector候選v1已封存，但root靜態查到第2頁返回第1頁使用cursor=None而漏校既有inventory，來源變更後可能誤換新first page；不執行已知缺口版本。V2候選只補expected_inventory_sha256與UI每次續頁固定inventory、兩個stale-return regressions，來源resolver/readback、tuple相容與既有上限保持。Health兩個型態修正及精確BuildSource／三個packaging module path/hash proof候選亦未正式套用；日曆dirty API ownership衝突保持開放。P01原翻頁356.6717／篩選382.4615ms FAIL、Main／realN／EXE；P08完整績效UI／qualification／comparison／M3；Health完整Gate等原要求均未接受。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 scope不縮減。

P38 fixture2原八檔core：**62 passed, 1 skipped in 100.85s (0:01:40)**，native 0，actual origin PID數 9；root收據 `C:/Projects/PythonProjects/technical_analysis/output/qa/baldr_completion_20261011/root/p38_fixture2_suite_7aa0bae5da4342bba4a8b0a443eac330/receipt.json`，SHA `ccf9310b0d9f4d5da095a564706aa31a87c195befce12ec06e5367c38f4cb668`。


## 日曆公共快取 API、Health 來源回放與 legacy selector v2 增量

日曆 public `load_latest_verified_twse_calendar_cache_for_year` 候選保留原 validator、future/expiry/source/hash/schema 與離線契約；Phase3C CLI 每次擷取一個 aware UTC observation，跨年度共用，不依賴 dirty CalendarObservationClock。Root 3094 pins 獨立重建四個完整 patch targets，確認原 calendar 函式 AST、其餘 CLI 函式 AST、全部原斷言保持。完整 3076-source canonical mirror 的四個實際候選模組 origin 通過，原 Phase3C＋新增十個 selector cases **50 PASS／1.96 秒**；實際來源守衛 clean、mirror/pins 起訖一致。第一版 namespace 守衛遇 Windows .venv/Scripts 同名路徑拒絕，後以 mirror-only 第一方根修正；首輪 native50PASS 仍因三個精確 pytest plainmodule aliases 拒絕，不能當完整驗收。新的精確 aliases 與 canonical path/SHA 核對已通過，拒絕原始收據仍保留。

Health typefix 的兩產品及一 QA pin-only 檔可完整逆向回 hv15；其他28候選 bytes、原 tests/deadlines 保持。首次完整 reconstruction 攔下 runner delta 漏列三處 symlink 硬化；control-only successor 保留原31檔與 runner bytes、不再複製 candidate tree，只重封完整 runner diff。Root3590 pins／完整11target／3delta／runner全diff重建通過。保存的 V2 mypy raw log 回放核3079鏡像、原myPy config、1042第一方/1176外部/957 BuildSource modules，path errors0，`source_path_proof_mapped`；原 mypy exit1與三個型態錯誤保留。**回放未執行myPy或產品，也不證明新型態通過**。Health31與Calendar4交集0；聯合 normal-only 八根型態候選規劃為35 overlay、25 products/10tests、fullmirror3080，原八根957/config不變，尚待封裝與root QA。

P01 legacy selector v2 的原 resolver/readback AST與十二個原測試 AST保持；完整 v1兩產品 patch及v2五檔八hunks重建、3122 pins通過。`expected_inventory_sha256` 在cursor=None也先核對，UI下一頁/上一頁均綁定當頁inventory，明示refresh才重建。3077-source mirror 與四個實際候選模組 origin 通過；Qt虛擬檔案以既有精確ZIP/loader/bootstrap code hashes與七個runtime pins判讀，未廣泛豁免。API/Qt/257來源/取消/stale-return與原相容性終態見下方；僅widget/API切片，不代表正常Main、realN、EXE或整個P01通過。

P08 fixture3只調公共日曆 observer及intent reader分階段時鐘，完整module bytes/AST可逆；原41為40PASS／1FAIL／15.30秒，已越過首個intent但停V2首個daily的execution close/EOD guard。fixture4只把V2 execution publication captured/written改成06:00Z/07:05Z，保留Oct5 pre-close baseline、所有原assert與P38產品bytes。原41仍40PASS／1FAIL／16.55秒，已完成V2首個daily和exact fill=1斷言，停V2 benchmark `benchmark_baseline_not_available_at_strategy_source`；尚未到V3 metrics/save/later/freshPID。精確根因是UpdateService自動publisher用live writer clock，再由測試explicit publisher用歷史clock雙寫；locator正確選live較晚副本。兩原JSON除writer clock與派生content hash外canonical完全相等，fixture5 scoped writer clock可使兩筆同body/hash/path而create-only冪等、不放寬tie guard，封裝及QA待完成。

完整P08計畫仍缺canonical performance readmodel、每策略Paper/歷史兩卡、正常兩帳交易/保存重開比較。正式Registry committed/valid只證storage integrity；舊Comparator缺status預設completed與缺qualification/version等契約仍開放，原Comparator與既有測試保持唯讀。P01原翻頁356.6717／篩選382.4615ms FAIL仍保留；單warm thread-aware CPU profiling只作診斷，不能當Gate evidence。全部P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4原scope維持，沒有任何完整產品/Gate接受。本增量只改本節四份狀態文檔與隔離QA artifacts；未正式套用產品、未改原始資料、未stage/commit。root序列Python，8GiB/12程序Job與至少8GiB可用RAM保留；subagent STATIC ONLY。所有列入的Job自然remaining0、handles關閉、mutex釋放。

Legacy v2終態：**17 passed, 1 skipped in 33.48s**；native 0、來源守衛clean=True、pins一致=True。root收據 `legacy_selector_v2_suite_7ffb1911a90f490ca336ca50d1a9a638/receipt.json`，SHA `2673ea24dd414359c0f05d6d3d31919915bb97069f370d3892a064e88af1f09e`。


## P08 fixture5 實際終態與首次 benchmark writer 初始化缺陷

Fixture5僅新增public publication alias及capture內scoped writer clock；root1384pins獨立逆向後原fixture4整個module bytes/AST相等，P38全部產品bytes/namespace、兩個publisher、全部143原assert保持。固定兩筆publication的writer clock後，它們生成同canonical body/hash/path並走既有create-only冪等；未放寬locator tie或來源cutoff。20個actual candidate modules origin通過。

原41績效終態為**40 PASS／1 FAIL／18.08秒**，native1、1390pins起訖一致、actual來源守衛clean。V2 baseline可得時鐘拒絕已越過；最新失敗在V2 benchmark持久化 `_ensure_routed_entries_persisted`→`_account_store` 的 `benchmark_route_database_missing`（V2 candidate1681；V3 adapter283轉譯）。沒有到V3 metrics/save/later/freshPID。

精確根因已靜態證明：cash-seed只建state snapshot，daily只寫state及cost ledger；它們不建立benchmark DB。候選 `_account_store` 先無條件要求benchmark DB存在，但真正能在合法exact route/custody下建立schema的正式 `EqualWeightBenchmarkLedger(read_only=False)` 在此檢查之後才初始化。這是writer共用reader前置條件的產品缺陷；下一步只允許合法首次writer進public ledger建庫，reader預設缺DB/schema拒絕、route/custody/sqlite alias/journal guards、金融計算、PIT/qualification與原assert保持。不得手建dummy DB/entry或改fixture繞過產品bug。

本次root兩個型態回放與兩候選套件回歸的其他結果維持前節；legacy v2為17 PASS／1 SKIP／33.48秒且來源clean，日曆50 PASS／1.96秒。所有fixture5外層Job自然remaining0、handles關閉、mutex釋放，未累積Python。P01 profiling與Health＋Calendar35來源normal-only型態封套仍STATIC ONLY；P08 readmodel/UI/comparison完整流程未接受，P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 scope維持。沒有正式產品或原始資料修改、未stage/commit。

## 兩個新 control 封套的前置 schema 守衛

Health＋Calendar聯合control root3635pins、35個來源完全等於已審查Health31＋Calendar4、forward/inverse各18hunks、原來源parser/classifier整段bytes相等。受控執行在 `expected_inputs` line178 即因 `formal_source_inventory` KeyError拒絕：manifest artifacts用實體JSON檔名作key，helper查logical欄名。native1、pins一致；**未建立mirror、未執行myPy、沒有型態結果**。新的control-only v2只修三個artifact key映射，35個來源／3080mirror／957八根／原config與runner保存。

P01單warm profiling封套root931pins、完整七段四十hunks重建通過；原timer、liveness、source/capability與Job函式AST保持。`normal_view_protocol`只有兩項明示profiler輸出與排除Gate的描述變動，實際protocol保持；首次root審查誤要求描述也不變的失敗保留。pure preflight native1，在line162 `p01_thread_profile_diagnostic_contract_changed` 拒絕：consumer查 `elapsed_is_gate_evidence`／`p95_gate_ns`，manifest生成 `profiled_elapsed_is_gate_evidence`／`original_p95_gate_ns`。**尚未origin、warm profile或重跑矩陣**。新control v2統一欄名和明確False/300000000，不以default繞檢查、不提高600秒或加第二warm；cProfile function stats是wall time，thread_time_ns另記CPU總量，必須明示且不作Gate證據。

兩個前置失敗均自然Job remaining0、handles關閉、mutex釋放。P08下一P39 STATIC候選只修兩個benchmark產品：合法首次writer由正式public ledger初始化base schema；metadata/persistence、reader與readback保留缺DB預設拒絕；V3生效writer在companion/bundle讀取之前初始化base。原P38全部產品／401core／143perf assertions、fixture5 clocks及namespace重綁可逆；增加獨立回歸，不能手造dummy DB/entry，尚未宣稱P39通過。其餘actual回歸與完整scope維持前節，沒有正式產品／原始資料改動、未stage/commit，完整產品或Gate未接受。

## P01 唯一 warm profiling 完成；P39 首次建庫後的回讀缺口

P01 profile control v2 root961pins、完整5segments/7hunks重建；runner/supervisor/preflight僅身份與pin重綁，helper/probe/phase bytes完全沿v1，body review完成。純前置與fresh child actualquery/store0都通過。唯一warm診斷native0、90samples（三類各30）、591prof、UI/TaskWorker/querypool實際執行緒來源、原完整DTO oracle/capability/source/store/postguard均通過；內層600秒未逾時，外層209秒左右自然Job0、handles關閉、mutex釋放。沒有重跑五cold或第二warm。新profiling p95只作診斷：翻頁478.6875ms、篩選862.0179ms、排序394.8965ms；**原m20未加profiler的356.6717／382.4615／210.1654ms與strict<300ms FAIL保持**。

唯讀分析90筆metadata/591prof核起訖SHA。querypool `nt.lstat` 254358calls/self wall88.0602秒為最大函式耗時；路徑 `633 artifact reads→repository _read_selected_exact_impl→10641 bounded reads→11907 link-component checks`。篩選artifact groups為1/4/6/26/27，各六樣本；翻頁固定四group。Querypool各類實際thread CPU總量約9.94／17.72／11.19秒。cProfile函式時間是wall elapsed，含排程/I/O等待；跨函式inclusive與跨執行緒wall不能相加當CPU或整體耗時。這是修正方向證據，尚無新效能接受。最初analysis工具錯把正常收據缺席的可選 `forced_descendant_cleanup` 當必有False欄；原失敗保留，依原wrapper schema檢查失敗欄位缺席後只讀分析成功，未重跑產品。

P39 root538pins、65檔hash鏈/42 active sources、全patch27targets53hunks與另fixture5/兩product delta重建；兩product AST除三個writer-only require_existing=False與V3正式ledger初始化外，整份逆回P38。其他reader/persistence預設存在性保持，fixture5原module僅namespace重綁。20actual product origin通過。原41＋新unit合組**40 PASS／2 FAIL／19.56秒**，546pins起訖相同、actual sourceguard clean。原旅程通過V2合法首次建庫/持久化後，在V2 public reader line404報 `benchmark_calendar_source_changed_during_read`；尚未到V3、metrics保存、later append或fresh PID。新unit把readback替換為無欄位object，writer原hash check329因此AttributeError；這是fixture缺陷，不能宣稱public provenance roundtrip。

P08靜態根因：V2與V3日曆來源hash混入外層 `calendar_observation` 每次live observer時鐘。不能在原2.0.0／2.1.0 schema下刪欄後重解舊hash，也不能覆寫immutable row。接續先以限V2 writer+緊接reader的同時刻fixture scope核legacy相容性（不折抵later/fresh），新版本另明示benchmark identity、contract/manifest schema與source-observation投影規則，保留raw hash、來源captured/available/expiry/status/date/PIT與reader拒絕。Unit fixture保持原writerhash assertions並誠實標示mock範圍。

Health＋Calendar control v2 root3662pins/23artifacts/20index、原runner與35source不變；actual再次在建立mirror/mypy前被 `verify_origin_lineage` safe_relative_path拒絕：15個upstream references中11個path為Windows反斜線。**沒有新型態結果**，原v1 KeyError也保留。control-only v3僅轉同一11個引用的POSIX字串與描述身份/相應pins，runner/產品來源保持；全前置契約走查後另審執行。


v3實際續驗：root3698pins核11個upstream path的POSIX化後source-origin整份dict相等、35來源及runner bytes不變；歷史失敗lineage與limitations新增說明已逐項核對，兩次root誤要求這些描述也完全不變的static失敗保留。正常八根mypy **native0／957來源no issues**，完整mirror3080、Health31＋Calendar4、source proof1042 firstparty／1176 external／0unknown path errors、status mapped。起訖formal/candidate/config pins一致，原mypy.ini保留ui_qt ignore_errors及既有script ignores，不能稱strictUItyping。收據health_calendar_v3_normal_types_febf5a4ecdab4b0f8cc50548774cb827 SHA e6c7c85da9d8b634dbdede1a39271f0623a47bff9a253c4c04aaf82da8c2d9f9；result SHA dda1897475599cb5eaa56dcc79dc4c63dd201032cd26ef20e3ea0db303486d9f，外Job自然0。

本節所有owned Job自然terminal0；host最後唯讀盤點owned QA Python0、可用RAM15.58GiB，沒有終止其他服務。subagent只做靜態候選；正常Main full-N三個缺fixture的接線正在準備，尚未執行／接受。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍進行中，正式產品／原資料未改，完整工作包或Gate未接受。

## Health 同版 runtime、P01 共用 SQLite 相容性與 P08 DTO 修正增量

Health typefix 的31個來源與聯合正常型態957來源使用同版 bytes。Root3594pins重新封完整runtime閉包；reader組 **66 PASS／2.11秒**，完整Main返回／fresh PID等五案 **5 PASS／43.34秒**，分別1與8個actual來源PID、guard clean、pins一致，原deadline與assertions保持。reader收據 `health_typefix_reader_6657357c19654d1685e0bfc9349dafcb/receipt.json` SHA `e1f684949a66de6c8668f744edaf9dee55d70b0c6dba4db4b52cd645fdc16966`；full收據 `health_typefix_full_221a4f5065c940e78b1031d98009d82f/receipt.json` SHA `dbacc5ca143775cf7674d87b5837ba24dd942ab8ebf684cf6ef38fb7bba13832`。不是完整P06/M3、長路徑或F12接受。

P01 v10 query與原query test整份bytes不變，僅共享SQLite reader改映Health typed來源；root4152pins、3075 canonical來源映像、Qt精確虛擬policy及來源守衛保持。三個actual模組origin通過，完整query組 **25 PASS／330.05秒**，actual來源2PID、pins/mirror一致。收據 `p01_sqlite_rebase_suite_eefb2d46f165464d9e2206f08c8d1825/receipt.json` SHA `cb6940d442a547895100d09da200326fd671cd05880cdd6ecac08d935b2383d7`；外Job `single_owned_qa_86482a4f008a499f8afd732866a385d4/receipt.json` SHA `0e08557cdac776c7d69b92a147347a19f66548809395c2422452fc6d4ecdeef2`，自然退出0。此為相容性驗證，沒有重跑p95；原翻頁356.6717／篩選382.4615ms FAIL保持。Directory lease與正常Main full-N harness另做static候選，未宣稱效能或整個P01通過。

P39 fixture6僅V2 writer＋緊接reader共用一次live observer及修復unit mock欄位，root555pins／完整兩個module AST inverse核對，所有P39產品bytes保持。原41＋unit **40 PASS／2 FAIL／19.20秒**；已越過V2 calendar pair，停在V2 public reader `clock['schema_version']` KeyError。unit另因raw Path長度260無法觀察已由public writer建立的12288-byte DB；不是缺DB。未到V3、metrics保存、later或fresh。

Clock DTO候選唯一產品delta是既有exact八欄／唯一列／型別長度守衛後增加固定in-memory schema marker；persisted SQL、rows、receipt SHA與原2.0.0身份不變。Root正逆patch及整份產品AST逆向相等，exact logical module仍是P39 V2、physical source只替換單檔、原physical檔拒絕。獨立decoder **5 PASS／1 deselected／6.71秒**；被deselect的是完整public tamper旅程，稍後全組仍執行，不能當已接受。第一次全48於sandbox有 **39 PASS／9 FAIL／11.66秒**，實際WinError5來自canonical path與atomic rename；原失敗保存。正式sourceguard與產品防線未放寬。

後續私有QA outside-sandbox仍使用相同owned Job上限及完整來源守衛。原import-origin test整份bytes保持，控制清冊僅一個module path/SHA與source-manifest hash重綁，所有原來源hash assertions照常執行；short tmp_path adapter只是root `tmp_path_factory.mktemp('t')`，沒有改test source或手造DB。20actual模組origin通過，完整48 **46 PASS／2 FAIL／57.28秒**，586pins一致、actual來源守衛clean。V2 public writer/readback、receipt tamper拒絕、unit首次建庫與原import-origin通過；兩FAIL均到 `metrics_v2.write...` 的V3publicreader2120：decoded day payload沒有 `provenance_sha256`，卻取該key。收據 `p39_clock_dto_performance_0735939b005d4e16b61df993057fb381/receipt.json` SHA `276e7f841c1fd13ea76afd11b8b1a00eebf1bd502d4108ec32c1aac8050baf4b`。尚未完成metrics保存、later append或fresh PID。下一窄修保留已驗證raw day row的hash供manifest核對，不把hash塞進canonical payload；V4/2.2.0另有明示來源投影及read-observation契約，不重解舊V2/V3hash。

root補強具名Job child launcher：只開既有Job、核parent/native child/venv redirector後actual Python均屬同一Job，suspended→membership→resume；readback仍8GiB committed／12程序、無nested Job。原root03動態字串SyntaxError在建立Job前拒絕；root04只修換行escaping。第一child probe在sandbox canonical path拒絕；outside-sandbox首次證明venv Popen PID與actual script PID不同而原probe拒絕。root02 launcher以SHA-bound bootstrap在candidate前核actualPID exact Job並保留native_launch_pid，正常probe0／bad pin啟動前拒絕／所有handles關閉；收據 `named_child_probe_dbd50ce97c9143d8baddabe93f60f1df/receipt.json` SHA `4728a1b6e9fec169b25495f9d0cd85e5e7a77f937c114f16ca70087019f90d94`。獨立timeout probe預期native124並已終止整個owned Job，自然剩餘0、外handle/鎖釋放；不是產品成功。外收據 `single_owned_qa_8eede188c39747519fc49337f4107cf7/receipt.json` SHA `848d961b2147673c3895ae7054dfac062ee9902bce678161d2ab69819f8b01f9`。

最新唯讀host盤點：owned QA Python0、可用RAM17.19GiB；未終止其他服務。subagent全程STATIC ONLY，root每次確認前Job終態／remaining0／handles閉合／mutex釋放才開下一組。本增量仍未正式套用產品、未改原始資料、未stage/commit。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4維持，沒有新增完整產品包或Gate接受。所有原始收據、stdout/stderr、來源與失敗保留，結果不相加為整體接受。
## V3 raw day hash 綁定實際續驗；P01 靜態接線缺口

V3 public reader原先把canonical decoded day payload當作含SQL `provenance_sha256` 的row。新單模組 sibling僅在decoder核hash、canonical、identity及missing-day守衛後，以raw day row的hash比較manifest；不把hash加進payload、不改persisted SQL/schema/bytes/舊source projection。Root601pins、正逆各一target兩hunks、整份AST除新增窄helper與reader單一binding外逆回P39，兩個focused正／negative regression隨全組執行；原401core／143perf assertions來源保持。Import-origin原test bytes保持，控制清冊追加第二個exact module path/SHA，原V2 overlay與fixture6保持；20actual modules originPASS。

合組原41＋unit＋clock六案＋V3兩案 **48 PASS／2 FAIL／47.47秒**，native1、609pins一致、actual來源1PID／guard clean。收據 `p39_v3_reader_hash_performance_13a15014bace48f684cf9410d69be3dc/receipt.json` SHA `74b346fa69ca31d0b39fea6469b9f1744c47d76add74e6e9f477017280f13905`。V3 hash KeyError已越過；兩FAIL均在initial metrics writer內，V3 exact public reader2171報 `benchmark_v3_calendar_source_changed`，由metrics167轉譯 `p08_metrics_exact_source_read_failed`。V2 public receipt tamper守衛已越過，但該獨立tamper案仍因重用整個旅程而FAIL，不能把它單獨算完整接受。尚未保存initial metrics、later append或fresh PID。已知舊calendar source projection混live observer時鐘，不再重跑相同未修完整旅程；接續明示V4/2.2.0 identity/schema/source projection/read-observation實作，不在舊V2/V3schema下重hash或覆寫immutable資料。

P01 Main full-N harness封存manifest `4b1e11584d9154eeb5174e558e4db38a5f9479f8f35e7984d499265e88c4129f`，尚未runtime。Root靜態查到共用 `_click_result_stock` 仍讀Qt/QTest globals，但兩者已移至test local import；要求小sibling只在helper延後import，原assert/body與600秒保持，不由runner暗注入globals。Root另明示Main canonical mirror／actualROOT cwd／Qt exact virtual policy、typedSQLite與v10 query三個已驗overlay的composition，草案及新來源freeze待封裝。

P01 lease封存manifest `b280a894690eec15609580f9868dbb00f2683cd8e6e0c26164d20caa51717c01`，candidate-root `7dbc4616b3ad73c233e276f62be4325182d6393eaab99a24bf304a807148ea9c`；是STATIC ONLY，未執行原strict、新lease或p95。Root靜態查到同lease重用FD未seek會在第二次讀取遇EOF，且native volume/file-index還未直接與fstat pair綁定。要求新窄sibling每次read前seek0、native identity不可證明時拒絕、首次及重用核fstat pair，新增同lease重複fresh bytes/SHA與zero/mismatch negatives。它仍每次讀fresh bytes、核原manifest/CAS/DTO/layout／取消，沒有byte/hash cache；原封包與v10/test bytes不改。修正封存後才執行QA，不用已知缺陷版本消耗重型驗證。

本增量上述三個owned Job均終態、remaining0、handles關閉、mutex釋放；原資源上限8GiB／12程序與啟動前8GiB可用RAM保持。subagent只做靜態候選。沒有正式產品或原始資料修改、未stage/commit，沒有新增完整工作包或Gate接受；P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4全scope維持。
## P01 strict／正常 Main 與 Health 可攜候選接續

使用者恢復補完並再次要求避免 Python 吃滿 RAM。Root 維持一次一組 Python、named mutex、suspended assign 後 resume、全 Job 8 GiB／12程序、啟動前至少8 GiB可用RAM；subagent只做靜態檢查。所有本節已結束的引用Job均remaining0、process／Job handles關閉、mutex釋放。Main新增同pytest PID的60秒stack診斷與具名owned Job journal，沒有另開診斷Python。主機於04:01 UTC仍有約16.7 GiB可用RAM；這是觀測值，不是壓力測試。

P01新版repository be8858fc：原strict25案 **25 PASS／337.59秒**，2actual PID來源guard clean、pins與mirror一致；收據 p01_lease_identity_strict_05e26e4b6e7a413cb60d22bf38371be0/receipt.json SHA 0445508ca08252a41059dd80b3bde7f84325edffc05f2febcfe943d6c0e59a90。前一版24PASS／1FAIL為mock不接受directory_lease=None keyword；新候選只在None分支恢復原兩位置呼叫，正逆兩hunk與整份AST逆還原已核。不改原mock、strict查核或新lease分支。

Lease13案首輪 **6 PASS／6 FAIL／1 SKIP／57.08秒**，actual source與產品pins一致。成功案已含native identity/fstat綁定、DTO與取消；6FAIL的原始trace指向測試自身未渲染的長路徑read/stat/write/open/utime，hardlink也因此SKIP。新test-only封套manifest ad21b8c0cfae5449e37a8aaef2395925b60d98c9d8ce0ec2db876fb7a885ab52只在OS邊界使用既有to_internal_io_path，保留canonical路徑及原fixture。新版 lease test I/O boundary **13 PASS／0 FAIL／0 SKIP／55.61秒**，收據 SHA 0a3cd87a176a90a8dc5aeba1b88d6f0801b7eff7e7f237aa417e54a0614fda4a；actual來源guard clean、pins與mirror一致，原hardlink案實際通過。Root4248pins、正逆patch及僅逆轉OS邊界後整份AST相等，28原assert與12函式保留；strict映射未變、lease只更新test row。fixture provider預先import而無pytest rewrite的一項warning保留。 M20完整矩陣與原strict p95<300ms仍未接受；舊page356.6717／filter382.4615 FAIL保留。

Main原完整旅程先在producer click不可見而等待600秒，再在Watchlist UserRole錯讀bookmark_identity_sha256而等待600秒。新測試封套只修真click可達性、讀bookmark_id與實際Watchlist導航／stateReady路由事件，原107個assert保留並增至121；Root4229pins、四patch正逆與17→18 QTest click核對。最新：Main旅程原assert1PASS，fresh-only別名與來源續驗通過（合成fixture；原guard99保留）。收據 p01_main_harness_suite_edf9a94e936346b69591f47a4c8738b4/receipt.json SHA e2e755458a0eb3bd4ea76a76a2752e37d05f1bd285eb3319eb6e7c57cd86818b。單次fresh-only續驗通過：Root核stdlib multiprocessing既有__mp_main__ alias assignment，只對同一腳本path/SHA新增精確alias；新actual PID來源guard clean、同Job attestation成立，完整fresh result除了runtime parent/child PID與前次相等、DB/settings/watchlist來源不變。收據 SHA 07795f7609f89ec0e0e82e8e9c2210b734c31134b9124712a77563ff075fce2a。原整個Main收據的guard false／99保持，不回寫成clean，也沒有重新跑producer1000；結果只合成fixture。第一次fresh-only因固定private checkpoint路徑拒絕保留；新版先在同私人根目錄保存前輪三個QA檔，再以原固定新檔路徑執行，未移動raw source／store／watchlist。 沒有實際Real-N／EXE／人工產品接受；原始失敗原件保留。

Health正式提升候選10產品＋4操作/架構文件正逆重建、3079canonical source mapping已完成；origin通過。Portable panel **3 PASS／1.93秒**，來源guard clean、pins與mirror一致；第一次pytest importlib別名不在精確清冊的Root拒絕保留，成功版只改成正常test module aliases，不放寬unknown namespace。收據 health_formal_candidate_panel_f7dd0fa5bb4d4cb1a406e1ee501aff00/receipt.json SHA 550272eb46231b11be8e049865da61523290d770f5fd8afbdf5c3f823e58bfa2。這三案使用受控scope factory；新的public writer／Main返回／fresh PID候選仍待API、可達性與runtime審查，不能借用panel通過授全旅程接受。Portable候選把舊891pins closure描述為3075的metadata錯誤已辨識；Root沿正式提升候選3079映射，不採該數字。尚未正式套用10產品。

P08另有distinct V4／2.2.0候選：stored calendar receipt/write observation與本次read receipt/read observation分開，公開execution/ranking資格保持false，fresh child改用root-owned launcher；獨立靜態核18artifact／18chain／34source／13baseline一致。完整patch、AST／runtime仍待。績效工作台候選尚缺trusted qualification來源與完整正常UI旅程，不能由storage valid／completed推成qualified，不能拼接Paper與Historical曲線。

正式產品及原始資料本輪未改，未stage/commit，沒有新增完整工作包或Gate接受；完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4範圍維持，goal active。四份SSOT以已核前像CAS附加，保存前像與引用收據/SHA到root handoff packet；rollback只在after SHA相同時還原本輪前像。
## Health可攜Main與V4期限／矩陣來源守衛接續

Health正式提升候選原六檔 **110 PASS／2 SKIP／13.23秒**，3actual來源PID、guard clean、pins/mirror一致；兩skip是Windows測試symlink建立權限，未轉成PASS。收據 health_formal_candidate_reader_ca22363667714088b47237414a8f44fe/receipt.json SHA993ddfcfa554a48e5e6b99b12d3ff99252346b575a6c035be406ab172201444a。Qt session cleanup的未載入Main提示保留；與先前portable panel3及舊typefix66的不同組合不相加。

普通Main新source fixture經formal Paper snapshot/ledger writer、PositionHealthDailyRefreshService與evaluator/archive writer產生兩快照與一筆research-only fill，再用正常Main exact receipt selector/open/table保存position、Watchlist返回及fresh Main重開。Root供exact17-key私人環境、空ML根及正式schema的私人ML設定；未借F12私有adapter或正式資料根。Status JSON是synthetic contract input，market observations缺少時degraded／unknown、available_at維持null；不宣稱實際排程producer、日曆驗收、真實broker事件或可交易資格。

本輪保留所有失敗：Root控制工具source變數碰撞（未跑pytest）、私人explicit ML config缺席（1FAIL9.12秒）、popup logical row507px／viewport440px的新增整列guard（1FAIL12.82秒）、fresh table整體捲動不能保證選列在外viewport（1FAIL28.95秒）。對後兩項修正只驗實際可見命中點與以cell content座標再次ensureVisible；父test/conftest不改、完整內外viewport predicate不變。Root3211pins、正逆兩hunk、整份fresh AST移除新增scroll並還原診斷文字後與前像相等；原38祖先assert／120秒wait與600秒child期限保留。

最後actual Main：native 1，完整Main旅程尚未通過；原始junit/stdout/stderr保留。收據 SHA 21b1f14d61749aad59c57905e727abbcf83d6b535f4f8a5183e1dd5cb665e5a9。此次27.22秒FAIL的fresh PID診斷為visible_cell QRect(61,701,99,29)、Portfolio viewport QRect(0,0,700,729)：列底729超出viewport底728一個像素。原完整contains仍拒絕；接續只將ensureVisible半格邊距向上取整，不重跑未修候選。來源guard/pins/mirror與實際PID attestation仍以本收據原值為準；所有本節引用的owned Job自然終態0、process/Job handles關閉、mutex釋放，沒有同時開第二組Python，沒有subagent執行Python。主機恢復時唯讀盤點本任務QA Python零殘留、可用RAM約14.61GiB；其他MCP、IDE與risk lab程序保持。正式10產品與4操作/架構文件仍未套用；完整P06/M3／EXE／人工接受與後续正式UI QA未授通過。

P08 V4產品正逆完整7段與V3完整module差異已由Root重建。8個財務／因果helper（含_build_entries、Decimal邊界、盤後出版與baseline/mark clock）僅版本名稱正規化後AST相同；review-fix僅四個既有定義變更，stored write receipt與本次read receipt分開，公開historical PIT／official event／execution／ranking均false。靜態收據 p08_v4_product_static_f04d13e81ddf418f869fb5044dee8ebe SHA5529f5a0cef78800feaf4ebc4f3798d7dd9f63a805666b8c533ae494be6eb430，不是runtime接受。Root另發現舊review漏標fresh60→600秒放寬；新deadline60封套manifest e73fa74f9d1a21d6345c4112a887ba311c757e07665e4b9a9023cd8f35f94335，只恢復timeout與錯誤文字兩個literal，raw逆回字節相等、child4347字節不變；caller context須固定60。Runtime composition／origin／完整public writer-reader/fresh及績效UI仍待。

P01 M20/M21 lease矩陣封套已靜態封存，querya1f／repositorybe885／SQLite1280／lease test571與已實跑13案一致。獨立review在執行前發現supervisor的overlay manifest/sidecar/closure三個固定SHA過期，因此沒有啟動origin或重型矩陣。Runnable successor需明列三SHA修正、必要namespace/path及其SHA重綁，原六角色／20頁／30 samples／600秒與strict p95<300ms不變；sealed predecessor保留。

Root為六角色600秒加前置/後置守衛，新增aggregate controller總批次cap3600→7200秒；與單角色／fresh接受期限分開，不默默放寬原測量。Root05 SHA267a881619cc3f6e7c062bc09edd1e888d446bfa1fc69c110c61aba8cd8c8d59，Root03 launcher SHA03d6ee383ae210ab55af3a0f976c7d928eda16906ffe3634879c647bd8ee169b僅改wrapper pin；Root AST/raw核證8GiB全Job／12程序、最低8GiB可用RAM、named mutex、suspended assign、kill-on-close與終態0規則保持。新controller/launcher尚未runtime；舊Root04/Root02原封。Original矩陣／p95 FAIL仍保持，沒有新完整Gate接受。

本輪未改正式產品／原始資料，未stage/commit。P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4全scope與active goal維持；保存四文件CAS前像與具名raw收據，不把合成片段或不同版本PASS相加成完整包。

## Health 完整可攜 Main 通過；P01 矩陣縮排前置拒絕

Health 最新 full Main **1 PASS／25.47秒／native0**：public Paper snapshot/ledger、DailyRefresh與evaluator/archive writer在私人根產生來源，再以正常Main exact receipt selector/open、完整列可見QTest click、Watchlist返回、關閉及新PID正常Main重開。完整selection／clock／snapshot／typed rows／baseline／witness／result／receipt／來源DB與status／selection-store SHA核對保留。2actual來源PID guard clean、3226起訖pins與3079來源映像不變；fresh PID41588與root-owned launcher attestation一致，原600秒期限、正常關閉及native TaskWorker registry排空成立。收據 health_main_portable_suite_306c064413f94a6b84d41c3304e4feb7/receipt.json SHA42bafecd598e849ea2f2db2d45bdfb98b0fe79d5a6cff697cecc683784d3f09a；外Job SHA55040e68a52f353a998f391ec3711248db2eac39703586d4d28cc818a5a2219f，自然剩餘0、handles閉合、mutex釋放。

測試接線新leaf只把ensureVisible的width/height半格margin向上取整；Root正逆patch與整份fresh AST僅逆回兩個margin後完全相等，parent/conftest bytes、inner/outer完整contains與原身份、120秒wait／600秒child期限均不變。Manifest99b42476b9ceabe05b97e5f930f330e1ba7ce8c20dd6aa052f7cf9bcf4a67ee2；靜態收據 d8508cb8e87ddf6d71d0ec8110a1610fb523d58d3597baa09c2f2d21bee6e1f5；origin收據 fd4bb33685dd3cf687e8cbfc8b32f23369edfcc2c708cb674bed1a79ba131fae。原27.22秒一像素裁切FAIL保留，不改contains或UI尺寸。

接受範圍是同版私人synthetic contract input＋正式public writer/read與正常Main旅程；market資料缺席時degraded/unknown/available_at null仍成立。沒有實際排程producer、official calendar／broker事件／execution/ranking資格、Real-N／EXE／人工或整個P06/M3 Gate接受。正式10產品與4操作/架構文件尚未套用；正常正式UI85案、validator、八根mypy與compile仍待序列執行，不把reader110／2skip或panel3與本旅程相加。

P01 M20 pinfix sibling的79封裝檔／17外部pins／97 hash-chain先由Root核對，Python AST在原runner343報IndentationError：source_module_hashes的overlay guard多8個空格；sealed前像有同一錯誤。收據 single_owned_qa_ccd9f34bf8944455aae435fc3913284c/receipt.json SHA08da1b41b8cfc2edfa911439421f91412d1506875881a4a5c3223292ad2a9053。沒有啟動origin或任一矩陣角色。另準備只修縮排及必要namespace/SHA重綁的sibling，六角色各600秒／20頁／30 samples／strict p95<300ms保持。Root05此靜態批次已實際讀回8GiB／12程序並自然Job0；Root03 launcher整合仍待runtime。

所有本節Python由Root序列執行，subagent僅靜態編輯，沒有同時啟動第二組。正式產品／原始資料未改、未stage/commit；完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍進行中。四SSOT保存CAS前像與收據/SHA；不覆寫封存失敗或其他未提交變更。


## P08 V4 首次公開回讀與 M23 程序契約增量

P08 V4 Root3180pins，正式3075＋26個exact執行來源＋2個regular initializer組成3103 canonical mapping；28個選定output.qa來源實際compile。唯一正式override是typed SQLite1280；P39 V2/V3保持原5a92／98a，不沿舊adapter的4749／72b3。Source composition收據2a20aafe4c1c8a64add4f6cb4bae7109a9736f060f40a45ac5d33beea356448b。Root plugin只橋接兩fixture並用pytest factory短tmp_path，未改候選或手造DB。

首輪來源collect在implicit namespace動態重算後帶入host output.qa而被精確目錄守衛拒絕：native2／guard99，產品pins與mirror未變，原收據367f8d0d5f849fbd3b5932c541ebcedd79bb9cb6ade3c7cea677a32400224a77保留。新Root02只把清冊10個namespace的ModuleSpec search_locations固定為各自唯一mirror目錄；不存在initializer必須成立，unknown namespace與來源SHA照常拒絕，不略過namespace。四個actual module及五項test collect **native0／guard clean**，收據d0e6b12912068938d61c452ba812170d3f24e122bd303a06ff669293d7d12e6d。

完整選定組 **4 PASS／1 FAIL／17.26秒**，1actual PID、source guard clean、pins與mirror一致；收據 p08_v4_public_suite_56b36382cc9c498fad424994c318ec0f/receipt.json SHAd7e170175f6fb6b6ff54b7a6a95219006a5b3da6d8ee25d61c41ed8afa64f353。四calendar guard通過；旅程已越過V4首次public write/read、stored write observation對本次read observation各自hash與read receipts變化、V2/V3拒絕V4資料。後續checkpoint在PaperExecutionProducerError拒絕「paper policy execution date is not an official trading day:2026-10-09」。這是原V4 fixture選錯交易日，不能強制calendar open或放寬產品規則。下一test-only sibling先按實際fixture/calendar API核next trading date及publication／intent／checkpoint／PIT時鐘。尚未完成later append／old-prefix reopen／fresh PID；沒有child，原child4347與60秒期限保持，不能宣告整旅程或P08接受。

P01 M23 Root135pins、96package／18external／115chain與正逆raw完整重建、16個執行檔compile通過；原runner縮排的修正明示，其他AST只逆回namespace/derived SHA即相等。六角色600秒／20頁／30samples／strict p95<300ms與完整DTO/oracle保持。靜態收據53d7fd06b3a3752938d436a5c598e3b0a92808c816d11d2693412d7dfa0e1f66。Root05/Root03 plan實際native0、actual supervisor PID26088同named Job、suspended membership→resume與8GiB12 readback成立，child/process/Job handles閉合、自然剩餘0；收據af63dc0b012074f2856e87e8588d20502fc46266dcc1997292adc03f7ae4c780。

M23 origin在任何role前由pre/post guard拒絕candidate_query_overlay_bridge_manifest_hash_mismatch：nested manifest的bridge row仍9d6/11449bytes，actual bridge與outer manifest/supervisor已4cc/12274bytes。Root收據9397089d25bba85375a8c4e88cb773d2b2e6b2187a6fcc4f03419ccbb80a8eee，source pins不變。新bridgepin sibling限nested row與相依SHA及namespace重綁；全399個candidate/closure/outer pin靜態對照只見該一row不一致，禁止改bridge本體／guard／產品／角色期限或p95。未啟動來源role或矩陣，不能由plan通過授矩陣接受。

本節所有owned Job自然terminal、remaining0、handles閉合與mutex釋放；沒有同時第二組Python，subagent只做靜態。最新host唯讀盤點本任務QA Python零殘留、可用RAM約14.64GiB；其他專案／IDE／MCP保持。Health同版完整Main1PASS已保存，正式10產品與4文件尚未套用。未改正式產品／原始資料、未stage/commit；P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4全scope、active goal及完整Gate未接受保持。


## M24 來源實證、Main lease 組合與 P08 天然時間界線

M24 新封套只修 nested bridge row 與相依 SHA，Root 537 pins、16個檔案 compile、完整正逆重建及 nested382來源閉包核對通過（收據40661f7eb6703bfa991eb07b691d02dff6bbf41a54bf296f3c91c4dfd19b2797）。Actual origin native0，actual fresh PID35660 的 query a1f／repository be885／SQLite1280 路徑與 SHA一致，51 first-party／80 runtime／594 venv pins 與前後守衛一致，無 store access；收據c08c0901c8900cd83fac79e9dc617c0b608cb397da5d3034e4b196b0eb166ab7。

M24 完整矩陣第一次 cold01 約9.10秒失敗，尚無 initial page 或 p95。TaskWorker error payload 明示 phase helper 在 seq23 strict_read_session_open_started 寫診斷檔的 os.replace 遭 WinError5，目標result.phase.json；並非已證明產品query讀取故障。後續同檔寫到seq43成功，現有檔案Archive且非唯讀，target157／temp177字元；無證據能指認具體 handle持有者。完整矩陣收據f12653058a2b2fbb4d939b91d5eb6d6927a32e34614fdfbfc1809d150a4a88bd，所有inner/outer Job自然0，無 timeout／cleanup error。新control-only successor限Windows replace的5／32／33錯誤最多5次，2／4／8／16ms退避；永久錯誤仍拋出，延遲算入原latency，600秒／角色／sample／p95／assert不變，待Root完整審查與回歸，不能重跑未修原包並當作接受。

P01 Main lease composition Root4255pins通過，3075來源只替換query61c→a1f與repository正式1e49→be885，SQLite1280及其他3072列未變。Raw inverse逐byte還原962369bytes原mapping；原Main journey／conftest／fresh c3 bytes及600秒期限不變。清冊aggregate57e0按原PowerShell zh-TW排序精確重建；原metadata未聲明collation，Root核對實際七列順序，並未宣稱其為ordinal排序。Root靜態收據88c0d26b10f036a2224c7f300b0a01546334bbdb1e771d1c5879d467ecf7a973。精確same-path/SHA __main__＋__mp_main__ alias加入Root runner，actual origin native0／guard clean／pins及mirror一致（93025ac1076bd6f87e2d96b062221eb3bb650ad9159aa24dcd3d40c062d8c8ed）。同組合完整Main旅程已啟動一個Root owned Job，結果待回收；不以舊61c的1PASS644秒替代本次a1f實證。

P08 新test-only交易日fixture將後段execution及四個clock對齊2026-10-12，私有calendar增加1151009閉市列與明示fixture ETag；Root3198pins／3103 mapping／完整正逆patch及整個AST逆回核對通過（28bc58936b598b7fc9bada25e787420346fc8353bb4e967d189d42c69c8df126）。原39 assert、fresh4347 bytes、10參數與60秒期限不變。兩個calendar authority已分清：intent fixture cache與producer calendar=None的正式日曆。獨立annual cache只是佐證，未宣稱suite讀取它；其-07偏移換算capture為Oct6 00:25Z、expires為Oct13 00:25Z。

PIT靜態核對指出live EOD reader會拒future checkpoint，V4 write/read也檢查live available_at及required clocks；fixture envelope沒有替這些reader設時鐘。最新checkpoint為Oct12 07:10Z，整旅程最早須等實際UTC過此時間並再核其他required clocks。舊prefix及fresh只讀Oct7，但旅程須先完成latest append；目前不啟動這項suite、不修改future guards。正式產品／原始資料未變；Health同版完整Main1PASS仍已保存，正式提升及全scope Gate未接受。

上述已terminal收據都確認Job0、process/Job handle關閉與mutex釋放。當前僅一個P01 Main Python群組，所有subagent STATIC ONLY；最新啟動前host可用RAM13.13GiB、owned QA0，其他MCP／IDE／risk-lab保留。


## Main lease 完整旅程原生崩潰（原收據保留）

同來源組合Main suite在producer期間遭Windows native access violation，native exit3221225477；收據f6f0d749530fbeb16a9e352801e17eb2e5c8c8ab26acf09bf819acc008f1f34d。Fatal stack的worker在snapshot repository read／rule JSON驗證，Main在原wait_for processEvents；不能由堆疊頂端推定JSON為根因。Pins與3075 mirror前後不變，但程序崩潰未產生atexit origin收據，source_guard_clean=false；未到fresh child，沒有Main接受。外Job自然0／handles關閉／mutex釋放、forced_cleanup=false（2422c79c7514821a13e0755012f6b953566d9f708056f1bb71afe96aed94cd78），不算OOM上限或timeout，靜態agent唯讀檢查Qt worker lifetime與lease差異，禁止盲重跑。

後續host唯讀確認owned QA0、可用12.70GiB，其他程序保留。P08新Root03有latest checkpoint UTC07:10天然啟動gate；此刻只執行import/collect origin，未啟動future fixture旅程。正式產品／資料不變，完整工作包／Gate仍未接受。


## P08 新交易日來源核對完成與 Main native 事件對應

新Root03 origin只import及collect五項，native0／source guard clean／3198pins及3103 mirror不變，收據b3ee6e416969a41ab569f4cc1e82f7787b39911d56d80b007360893f4163e2eb；外Job自然0（5118b247ab8e16a1a5c06cc48d089f12187ef2372ba375d28f4833401fe5ff27）。尚未執行fixture旅程，Root suite入口已明確拒絕UTC07:10前啟動，產品future guards不變。

Main native Windows事件1000／1001已保存XML：91546 SHA54079b57002c9f78fe0b6f3a37a864d631d150dc30149253503dd3119aff1965；91547 SHA4253b04ddff6e548008fe625262e5f22e2d2f43745a91f13afa24cb76953e117。fault PID0xAEC8=44744在外Job observed集合，時間22:45:06-07:00亦在22:44:03→22:45:19窗口；module python311.dll、exceptionc0000005、offset0x1aaaeb，未能由此認定根因。stacks.log的60秒是faulthandler觀測時點，並非600秒QA期限。兩位static agent分別核Qt lifetime與Win32 ABI，phase successor由第三位靜態封裝；所有Root Python當前terminal0。正式產品／資料與完整Gate判讀保持。


## 使用者暫停：先進行文件治理（2026-10-12 06:00 UTC）

使用者明確要求暫停補完工作並保存接手prompt。所有subagent已完成或中斷；所有Root Python Job terminal／自然0，process及Job handles關閉、mutex釋放。最後host唯讀盤點owned QA Python0、可用RAM14.96GiB。Goal應設paused，只有使用者授權才恢復。

接手入口：[完整停點與新對話Prompt](../agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md)。Snapshot／shared_state中的相對路徑請依本文件實際目錄及現行導航定位該同名檔案。完整範圍仍P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4，沒有新增完整工作包或Gate接受。

最新界線：Health完整Main1PASS已保存但正式提升未做；P01 M24 origin已通過、矩陣在QA phase replace失敗且無p95，M25重試successor封裝途中被中斷，完整檔案SHA inventory另存暫停封包，不能直接執行未封存候選。Main lease producer期間native access violation仍未確定根因；靜態Qt／ABI沒有找到具體錯誤。舊644秒Main的實際conftest／test／fresh bytes與本次相同，先前agent誤讀predecessor pins的說法已撤回，但舊query／repository及guard99不替代新lease接受。P08新origin collect5guard clean，完整latest append仍待天然UTC07:10及required clocks，原60秒期限保持。

官方PDB純資料的GUID／age與DLL相符，沒有安裝或更換Python；DbgHelp exact lookup126、純PDB parser未找到fault RVA procedure，最後工具失敗／Job自然0，仍未定位原生函式，不可把它當根因實證。交接入口記明來源檔案及所有診斷停點。正式產品／原始資料未變，未stage／commit；文件治理後應依最新權威與路徑接手，保留其他未提交變更。

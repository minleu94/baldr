# Baldr 補完工作暫停交接（2026-10-12）

> 使用者為進行文件治理，於 2026-10-12 06:00 UTC 要求暫停。這是接手導覽；目前狀態仍以最新 PROJECT_SNAPSHOT 與具名 QA 收據為準。後續文件治理可能更動路徑，請先查現行入口，勿用本交接覆寫新狀態。

## 工作範圍與停點

- 原目標：推進整個 `docs/superpowers/plans/baldr_product_completion_plan_20261006.md`，完整範圍 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4。局部成功不代表完整工作包或 Gate 接受。
- 所有 Root Python Job 已終止且自然剩餘0，沒有待輪詢的 exec session；所有 subagent 已完成或中斷。最後唯讀盤點 owned QA Python0，可用 RAM14.96GiB。其他 IDE／MCP／risk-lab 程序保持原狀。
- 本次新增 QA 工具、候選、收據與文件紀錄；正式產品及原始資料未變，未 stage／commit。倉庫已有其他未提交變更，接手不得覆寫。

## 已取得的實證

### Health

完整可攜 Main 旅程 **1 PASS／25.47秒**；normal Main 公開 writer、Health 更新／保存／選擇、實際點擊與返回、close／fresh Main 重開皆通過。同版來源守衛、pins、mirror一致，fresh child及所有 Job自然0。

- 收據：`output/qa/baldr_completion_20261011/root/health_main_portable_suite_306c064413f94a6b84d41c3304e4feb7/receipt.json`
- SHA256：`42bafecd598e849ea2f2db2d45bdfb98b0fe79d5a6cff697cecc683784d3f09a`
- 正式提升候選：`output/qa/health_formal_promotion_candidate_20261011/manifest.json`，SHA `5b4c495d9306fc0ed772ed7c0c4f4156f07cf61b9dedde05dd26ce39ad3dec94`。10個產品來源及4文件仍未套用。提升前須處理 canonical baseline lineage／rebase；正式 UI85／validator／8 root mypy／compile須由 Root串行驗證。
- 屬於私有合成契約資料旅程，不折抵真來源、自然 producer、真N、同版exe或真人驗收；不授整體P06／M3完成。

### P01 lease、矩陣與 Main

- 舊 strict25 PASS 使用 query61c／repository be885／SQLite1280；lease13 PASS無skip使用 a1f／be885／1280。不可宣稱 strict25驗過a1f。
- M24封套：`output/qa/p01_lease_matrix_bridgepin_candidate_20261011`。Root537pins／完整正逆重建通過；actual origin及fresh PID35660來源守衛通過，收據 `p01_lease_matrix_origin_cfc66f7e83b64de69863bcaaaf89e08c/receipt.json`，SHA `c08c0901c8900cd83fac79e9dc617c0b608cb397da5d3034e4b196b0eb166ab7`。
- M24 matrix第一次cold01約9.10秒失敗，phase helper `os.replace(temp,result.phase.json)` 在seq23遇WinError5，尚未進入initial page，**沒有p95**。後續同檔可成功寫到seq43；具體handle持有者未明。收據 `p01_lease_matrix_matrix_f508cac49d414d698cd54c08bc9ceeb7/receipt.json`，SHA `f12653058a2b2fbb4d939b91d5eb6d6927a32e34614fdfbfc1809d150a4a88bd`。所有inner／outer Job自然0，無timeout／強制回收。
- M25 successor `output/qa/p01_lease_matrix_phase_replace_retry_candidate_20261011` 在封裝途中中斷。**未封存完成、未經Root審查、未執行**；現有freeze index可能是複製的舊版，缺少完整新hash chain，不可直接執行或宣稱凍結。暫停封包保存該目錄當時完整檔案SHA inventory。
- 已批准的M25邊界：只在Windows replace的winerror5／32／33做最多5次、2／4／8／16ms退避；其他錯誤立即拋出，永久拒絕仍失敗；延遲納入原量測。600秒、六角色、20頁、30samples、p95<300ms、schema／鎖／序號／原assert保持。新增聚焦回歸來源尚未執行，接手須檢查永久錯誤與暫存寫入失敗等反例是否完整。
- Main新組合Root4255pins、3075mapping只替換query與repository兩列，其餘3073列含SQLite不變。靜態收據 `p01_main_lease_composition_static_311736789d33417982cc6094fd100354/receipt.json`，SHA `88c0d26b10f036a2224c7f300b0a01546334bbdb1e771d1c5879d467ecf7a973`；actual origin clean SHA `93025ac1076bd6f87e2d96b062221eb3bb650ad9159aa24dcd3d40c062d8c8ed`。
- 完整 Main lease旅程在producer期間 **native3221225477／access violation**，尚未到fresh。Pins及mirror不變，但native crash沒有atexit origins，source_guard_clean=false，不授接受。收據 `p01_main_harness_suite_b769aceda56b48a18775210c5f44c24c/receipt.json`，SHA `f6f0d749530fbeb16a9e352801e17eb2e5c8c8ab26acf09bf819acc008f1f34d`；外Job自然0，收據SHA `2422c79c7514821a13e0755012f6b953566d9f708056f1bb71afe96aed94cd78`。
- Windows事件對上owned PID44744，module python311.dll／c0000005／offset0x1aaaeb，XML位於 `output/qa/baldr_completion_20261011/root/Main_native_event_a1d9af6d32f943248eb332a3dffc55da/`。WER僅有Report.wer，沒有dump。兩位靜態審查未找到ABI或worker提前釋放錯誤；active `read_exact` 沒有走新lease。不能認定JSON／Qt為根因。60秒stack是faulthandler觀測，不是600秒期限失敗。
- 舊644.02秒Main PASS的實際conftest6075367／journey0c29b9／freshc3b453與本次三檔bytes相同；靜態agent先前誤讀predecessor pins的說法已撤回。舊版query61c／正式repo不同且guard99，不可拿來替代本次a1f／be885接受。

### P08 V4

- 先前實際組4 PASS／1 FAIL17.26秒：四calendar guard通過、首次V4公開write/read通過；後段fixture誤選2026-10-09非交易日而拒絕。尚未到later append／old-prefix／fresh，不授P08完成。
- 新test-only交易日封套 `output/qa/p08_benchmark_v4_tradingday_fixture_candidate_20261011` 已凍結，manifest SHA `a2bc33953b65bf891f83e31959a2a567d76428e33d8967f457a00dae5abaed98`。後段改10/12，私有calendar增加Oct9閉市列／fixture ETag；Root3198pins／3103mapping／完整forward/inverse與AST核對通過，39 assert／fresh4347bytes／10參數／60秒期限不變。
- Root靜態收據 `p08_v4_tradingday_fixture_static_1ae366d649a045c3904c81d5dbeafb5a/receipt.json`，SHA `28bc58936b598b7fc9bada25e787420346fc8353bb4e967d189d42c69c8df126`。
- 新origin只import／collect5，native0、guard clean、pins及mirror不變；收據 `p08_v4_public_origin_acb87e5b56e8466bb17b3c5e4685b378/receipt.json`，SHA `b3ee6e416969a41ab569f4cc1e82f7787b39911d56d80b007360893f4163e2eb`，外Job自然0。
- `run_p08_v4_public_root03_tradingday.py` suite入口有天然時間gate **2026-10-12 07:10 UTC**。接手時仍先核對實際UTC及所有required source clocks；保留live future guards。Fixture的clock envelope沒有凍結EOD/V4 live reader。尚未執行完整新版suite，60秒期限不准拉長。

## 原生符號診斷停點（可選）

只下載官方Python3.11.9的`core_pdb.msi`資料包並讀取CAB／PDB，沒有安裝或更換Python。DLL CodeView GUID與PDB stream1 GUID、age1精確相同。檔案位於 `output/qa/baldr_completion_20261011/root/python311_native_symbols_20261012/`。

- MSI SHA `37c68a397a363d251163c9f447ed4c9aa0db062a563aa47d3e586d5075e448d5`。
- 真正PDB資料在 `symbols_f7e5275193f34461b67c34b287f06c1c/cab1.cab.cab`，檔名是expand產生，但內容為MSF7，SHA `35dcb6ed31887cf87e6c0349f686c6e8455cb6e433977b14628f071b67a2734a`。
- DLL SHA `0817a2a657a24c0d5fbb60df56960f42fc66b3039d522ec952dab83e2d869364`；raw GUID `597C45FC7D1FC04C9AC2DB42401CE2C7`。
- DbgHelp exact lookup仍WinError126；純PDB parser已讀278modules／8927procedure，但沒有找到涵蓋fault RVA的record，故仍**未定位函式／未確定根因**。可能需要驗證PDB section／OMAP，不能直接把無matching record當作PDB不符。
- 最後工具 `read_python311_PDB_function_root01.py` 失敗，outer `single_owned_qa_416b4798326e4c988a9531b819a376f5/receipt.json` SHA `43dd1da7f9329aca8829f2cb1e59abd9e438e469b80c24721ee1dddf3f79772d`，自然0。所有更早工具失敗紀錄保留；不要原樣無限重跑。

## 接手順序與資源限制

1. 依現行AGENTS.md完成必讀，再讀最新Snapshot、QA進度、active_task及handoff；文件治理後的權威／路徑優先於本交接舊副本。盤點git diff和未提交內容，不stage／commit未知檔。
2. 核對本機QA檔案及SHA仍在，先封裝／審查未完成M25，不執行未封存封套；完整正逆重建、all pins／closure、原協議／門檻均要核對，再聚焦回歸、actual origin、matrix。
3. 診斷Main native crash：單次有界的observation-only事件或process-scoped native dump，保留N1000、QTest、600秒及排程；勿盲重跑、disable GC或據stack猜修正。實證clean才授本次Main成功。
4. 天然時間到後才串行執行P08新版suite；先確認origin來源仍不變。完成later append／old-prefix／fresh後再判讀。
5. 刻意處理Health正式提升的source lineage／baseline rebase，做同版正式QA及文件同步；再依全補完計畫處理其餘工作包、真來源／同版exe／真人Gate，勿把局部QA當整計畫完成。

Root是唯一可啟動Python／import／pytest／mypy／compile／subprocess的執行者；subagent只能靜態讀／寫，不啟動背景程式或再分agent。一次只允許一個本任務Python Job，啟動前至少8GiB可用RAM；named workspace mutex、suspended assign Job後resume、全組8GiB／12程序，真正terminal／Job0／process與Job handles關閉／mutex釋放後才下一組。正常成功須natural0，不以強制回收當成功。不要終止其他專案、IDE或MCP程序。不得刪除原始資料；金融核心不得新增裸float；策略／績效先做look-ahead自查；期限、source guards及assert保持。

## 可貼到新對話的 Prompt

```text
請接手 C:\Projects\PythonProjects\technical_analysis 的 Baldr 產品補完工作。
先依目前 AGENTS.md 讀完必讀文件，再讀 docs/agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md，以及文件治理後最新的 PROJECT_SNAPSHOT、BALDR_COMPLETION_PROGRESS、active_task、handoff_log。若治理後改名，先循現行索引找到；不要覆寫新文件或其他未提交變更。
原工作因我做文件治理而暫停，現在授權恢復。請負責審查與整合，完整範圍仍是補完計畫 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4。核對本機收據/SHA及未完成封套後，按交接順序繼續M25 phase控制修正、P01 Main native crash、P08 V4完整旅程與Health正式整合；不要把局部PASS當完整工作包/Gate完成。
資源限制務必遵守：subagent只做靜態工作；Python/pytest/mypy/compile/子程序只由Root串行執行。一個Windows Job總上限8GiB/12程序，啟動前至少8GiB可用RAM；前一組真正terminal、Job0、所有handles關閉及mutex釋放後才下一組。不要一直開Python或盲重跑，不要終止其他IDE/MCP/專案程序。保留原assert、來源守衛、PIT及期限；未凍結M25不可直接執行。
請先簡短回報接手現況與下一步，再持續推進；使用繁體中文。
```

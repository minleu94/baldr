# Baldr 補完交接：Increment18 已驗證／Increment19 未驗證候選

使用者於台北小時政策與P03封存來源施工後，要求本對話停止推進新功能，先將自己的工作提交並交由新對話接手。文件日期按使用者時區 America/Los_Angeles 的2026-10-14；收尾已跨UTC 2026-10-15。這是進度保存，不是完整產品接受，也不是另一份總計畫。

## 接手先讀與所有權

1. 現行 `AGENTS.md`、共同安全規則及原[補完計畫§9.5](../superpowers/plans/baldr_product_completion_plan_20261006.md#95-資料阻塞分流與下一批交付2026-10-14-調整)。仍以原P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4為範圍。
2. 本交接、[Snapshot](../00_core/PROJECT_SNAPSHOT.md)與[每日資料政策實作QA](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。[原10/14 checkpoint](BALDR_COMPLETION_CHECKPOINT_20261014.md)及其舊FAIL原樣保留；它是更早的歷史基線，不能覆蓋本交接的新進度。
3. 本機唯一owner task：`output/tasks/baldr-completion-policy-20261014-01a1390b/task.json`。同目錄的 `increment18_safe_resume.json`、`increment19_static_candidate_qa00.json`、`handoff_commit.json`及具名收據提供精確接手點。`output/`被忽略，未隨Git提交；同機接手必須保留，不可清理。
4. `docs/agents/shared_state/active_task.yaml`與`handoff_log.md`是其他owner的singleton，只讀核對、不追加或取代。所有進度寫自己的task；角色與Context按現行索引漸進讀取，不重讀全庫。

提交前HEAD為`5cedd65710db21d9d1863695dcfa4ee0edb872ec`（其他owner的Direct排程文件提交），Root起始基線為`10eb154af9c553354c73e57fcb2fafa724b82b8a`。本交接checkpoint實際commit由Git log及本機 `handoff_commit.json`核實。提交保存本任務實作與WIP，沒有push／發布／交易或正式資料寫入。

工作樹唯一outside-own檔案是 `docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md`，未知owner，Root不改、不stage；交接前bytes11387，SHA256 `9526e061ff877b0f5340a2bbef7a4aac7b7f779a3e1c019dc0ecae3de9097abe`。shared active_task SHA `7bda6289355767dbf32412f70708e475de6e92b5795d143d42ce4c879fcfa7c9`，handoff_log SHA `ad98d6c0059c825207d4e63bd2b27417d67bcc1780013035d4b7de97b172321f`；仍維持原件。

## 已驗證到哪裡

小時可用性與不可覆寫每日版本快照已沿P00／P03契約、consumer、固定cohort／series binding及正常組裝推進；它不接受錯來源、單位、歷史PIT或未成熟paper結果。較早P02、P08 Decimal capture／Registry、Paper卡及各次FAIL依實作QA原分段證據追溯，不能加總成完整Gate。

最新Increment18接通原F17正常頁面、單一owner-thread actor、Source3／Recipe3／Bookmark3、Main typed saver與Watchlist「個股分析」路由。保留四個外部SHA：原Reference3、原Artifact3 descriptor、ArchiveReference2及Artifact4 descriptor。完整來源／正式根與operation根先檢核，再建立三個sibling研究目錄；binding metadata提供roots，不讀mutable series pointer。舊V1／V2收藏維持strict-live，不自動轉封存。

| 當時具名驗證 | 結果及限制 |
|---|---|
| Bookmark3／storage3／Watchlist3 | 分別9 PASS、27 PASS／1 protected-reparse SKIP、5 PASS，不是單次合併suite。 |
| 原archived UI | 1 PASS／44.49秒，full258、原1000 YoY22.006875、分頁／比較籃／收藏、DB/raw漂移且原snapshot/reference移開後exact重開。 |
| 正常Main／新程序 | actual父54640→fresh32420；保存1128／頁1，26固定來源、四錨點與origin Recipe3相同，原320 F17資產不變。父關閉後改私有DB/raw、移開舊snapshot/reference、改壞series pointer，fresh仍精確重開。原120秒每phase／270秒driver保留。 |
| 受影響舊路由 | V2 UI1、V1 UI6、錯收藏路由2 PASS；Workbench85 PASS，validator25 PASS／0 FAIL／4 protected skips，金融float守衛PASS。 |
| 型別與治理 | 八roots mypy1003 PASS，但既有ui_qt.* ignore_errors=True不證UI強型別。文件治理12features／37link sources、errors=[]及來源audit PASS。 |

Main原生旅程是合成保存來源、Python socket attempts0，OS network audit未執行；不是完整Recommendation、正式來源用途接受、PIT、真N或Native／EXE資格。Increment19已改public portfolio reader，故Increment18收據仍只代表當時source pins，不得直接聲稱現在整份新候選已全部重驗。

重要本機證據如下；所有SHA均為SHA-256：

| 路徑或身分 | SHA／內容 |
|---|---|
| `source_readback_increment18.json`（task同目錄） | `fbc29b980ac8e647d692352e786b65cce7ff749140bd478b1ab39b84c056bdcc`；154own／155dirty／52保護資產，唯一outside-own如上。 |
| `outer_job_inventory_increment25.json` | `b398f8561dc9b6650f0e97da51116c6a1c74dd50f1d128b87a589222c59c8fbc`；141收據＝140native＋1歷史低RAM未起child125。 |
| `outer_job_inventory_increment26_handoff.json` | `da8542099ddb349be9cec6c17a22bcaf2cdc69119b651cfcd1b45449054cca3c`；前141＋P08唯讀Context＝142收據／141native／1低RAM未起child。 |
| 最後完整產品批治理outer `eeba77683a334a1fbb47d76aedfc5d5f` | `6032a53d6c2d5a9f0660acc5e7755b7fc969418e5e081bff99e944fa1040f666`；0、三PID陣列空、process／Job handles closed、mutex released。 |
| P08 Context-only outer `8f8ed3d0cf0546319f9c6d64ffe14512` | `8e2a365c23db27e135360a216f2a737d14b42f1c3994ab2e6c739830e570883c`；同樣完整閉鎖；L2僅3文件3768字元，不是產品QA。 |
| F17 saved fixture `revenue_saved_f17_fixture_qa03.json` | `6e414d0f643e0b6a3dd8cf6d99cf6476698197e884c79adde81f0256d96d8ca7`；320固定資產／full258，不重跑原producer。 |
| 正常Main parent／fresh | `C:/Users/archi/AppData/Local/Temp/bv3ui18a/fixture/parent.json`：`960e1ea04c719afca56ef4a580d38cf191cc40ea58d9cf4aca2996841b089c7e`；fresh.json：`a126fed641ed15584a48a97de74a107b12445b2e381ca11ee779793c4abfb1f3`。 |

所有歷史FAIL／timeout／SKIP均保存，包含Increment18兩份治理FAIL。最新治理PASS只修正具體錨點／audit分類，不抹除失敗。P01 p95 `385.9978ms > 300ms`原FAIL保留；使用者只暫緩它作為其他包前置，不是P01接受。

提交前tracked scoped diff check為0；stage後首次涵蓋所有新增檔案的git diff --cached --check回2：17個new blank line at EOF及1個SourceActor註解尾空白。它們是已保存候選的既有bytes，不影響本次checkpoint保存，也沒有當成PASS；未為排版重寫已驗證來源／SHA。原輸出保留於本機handoff_staged_diff_check.log。

## Increment19：已保存但完全未QA的P08候選

新增三組葉片：日曆raw-evidence純DTO／codec、create-only單檔artifact及public exact reader、雙明示Registry run的full-period只讀配對；各有新增測試。另增量修改public `RecommendationPortfolioResultReader.read`：可選外部metadata SHA及64MiB／128MiB預算，舊default呼叫形狀保留。

日曆封套內嵌完整raw/base64、原URL／年月／hash／metadata與重算兩市session dates；維持既有93 calendar-days／單原件4MiB／最多8responses限制。artifact外部whole-file SHA與DTO body evidence SHA是不同錨點。仍是candidate，不授official clock／PIT／performance資格。較長期間的有界分段組合尚未完成，不能宣稱支援任意完整歷史期間。

配對不選latest、不重跑回測、不從float摘要造PnL；保留兩邊原producer Decimal capture，分別列expected／actual／missing／unexpected sessions。loop complete不代表coverage完整。現行V2原件缺source／currency／calendar／execution／cost權威，因此即使日期齊全也應blocked、metrics=None，不能捏造可比較盈虧。Root在靜態複核後補上artifact／precision策略id-version與metadata交叉綁定，以及initial capital的精確Decimal不一致原因；策略修正在pair模組143–146及156–157行（下表SHA）；本批修正尚未測試。

| 未驗證來源 | SHA256 |
|---|---|
| `app_module/recommendation/portfolio_result_reader.py` | `f31b667e79114db29b7aa1281b21b8c9ddb1e278de2861da6d35d9240b1a4c7f` |
| `app_module/recommendation_portfolio_calendar_evidence_v1.py` | `bd4de8a1b53fa31d15ae040d02fe3d5009c6727023a0c4de05e2ae3c48405849` |
| `app_module/recommendation_portfolio_calendar_artifact_v1.py` | `e4847552485cd6a9a0e25eefd2ccda8862c291ece8c8090b44e62da57afd3e9f` |
| `app_module/recommendation_portfolio_full_period_pair_v1.py` | `de970e06c62071a6789cb8298aefe3fbc68bafcf8e84ffda20c5eca3b7210817` |
| `tests/test_recommendation_portfolio_calendar_evidence_v1.py` | `f11d7360eac9ad0be4ce2c2c1eac01d71060d1279b7b0486f8e26f61e0968c35` |
| `tests/test_recommendation_portfolio_calendar_artifact_v1.py` | `98c58cc66a9108944a5804d1da73699f578dcc49201ab075d2d24a1781001073` |
| `tests/test_recommendation_portfolio_full_period_pair_v1.py` | `8dbeb705d0b91ac01fd9b5802a241d8b4ba6c7d13f1a03a07bdd670f05059327` |

本機 `increment19_static_candidate_qa00.json` SHA `74faf7a2f2cf57a520271054d02a9b423aafe5dc055aa1ee6ff279798718439c`；明示STATIC／NOT_QA_ACCEPTED。已準備但從未啟動的 `p08_calendar_typing_contracts_qa02_spec.json` SHA `471bbfcea0c2bd304fe78f3d3e741059b03596b9e5ffb7a02ab071e658113f4f`：compile7檔30秒、八roots mypy180秒、calendar codec120秒、artifact120秒、pair180秒。QA01只是更早未執行規格，不能當FAIL或PASS。新Root要重新核pins與HEAD，建立自己的task並引用舊封套；QA02只作命令模板，將runner TASK、spec／env／result directory另存至新owner的task並重綁SHA，不直接寫舊task或覆寫原spec／收據。

RAM preflight曾約6–7GiB，低於至少8GiB可用RAM，故本批compile／mypy／pytest全部未執行，沒有背景Python或待輪詢session。最後交接文件與新增Feature Map紀錄的Python治理亦未執行；commit只是保存，不能因此標PASS。正式資料、Windows Task及原件沒有為騰RAM而改動，也沒有終止其他owner程序。

## 下一批執行順序與並行加速

1. 核對本commit／worktree／外部owner、上述sealed與static SHA、142閉鎖收據及原52保護資產；讀最新Snapshot／原計畫。不要重新接手舊singleton或把更早checkpoint當目前完整進度。
2. Root先做全新RAM preflight、核前Job三清冊空／handles closed／mutex released。RAM未達8GiB不得起Python；不放寬8GiB committed／12程序／原case期限，不全機kill Python。不要把等待資源寫成QA失敗或通過。
3. 資源達標後Root依QA02固定命令串行compile、mypy、三組新測試；首次失敗保留收據，辨明斷言／產品／fixture／typing原因，只重受影響部分。再驗受改public Reader的既有Registry／artifact消費者，例如 `tests/test_recommendation_portfolio_precision_registry_v2.py`、`tests/test_recommendation_portfolio_result_artifact_v2.py`；按實際dependency選，不盲全庫。
4. 同時最多三個Luna Max僅靜態：A複核日曆raw/schema／版本／93日邊界；B複核Registry策略／parent／metadata與source/currency/cost交叉綁定及接public ports；C定位原Backtest歷史頁的兩個exact run選取／正常保存→重開→比較→返回。各人最小檔案清單及單寫owner，Root保留金融判斷、shared ports、整合、QA與文件單寫。先複核既有葉片，不重寫或按資料夾分agent。
5. QA後再沿原P08把日曆、真正提供history的typed source/currency/clock evidence、版本化artifact／Registry descriptor、pair reader及正常UI接齊。現V2 wire不可偷偷填猜測權威；新evidence需additive schema或明示sidecar。缺真來源時繼續獨立功能工程，不能把unknown卡片或本批calendar候選當完整P08交付。
6. 同步原計畫、Snapshot、契約、Feature Map及必要手冊，執行文件治理及來源重新綁定。UI若再改，Root須做Workbench85／validator25/0/4及適用回歸；mypy的UI既有ignore限制仍明示。最後才重封candidate及native／fresh；原件320不重產。

本舊session只新建3個Luna Max，全部已完成、無pending writes。其名稱是 `completion_static_review`、`hour_snapshot_contract`、`scrapling_static`，只是歷史識別，不代表新對話可跨session直接重用。同一補完task跨對話累計已新建3／10，不得因換對話重置額度。新對話先查可重用性；平台不支援或context膨脹時，可先新建最多3名Luna Max，使累計至多6／10，後續亦不得超過10；同時最多3名。禁止子代理再建子代理、Python／QA／network由worker執行或同時掃同一全庫文件集合。

## 保留的資料阻塞與授權

使用者已決定：每日固定成功抓取後保存不可覆寫版本；對應官方timestamp以台北時區作可用時間基礎，小時向上取整（14:45→15:00），實際使用不得早於成功批次完成。只有基準日期時用成功批次小時並明示basis；保留原件、官方時間原文、批次時間、hash/version，更正另存。從首次成功保存建立前瞻可用性，歷史用途仍按真版本證據；不要再詢問小時精度，也不把舊FAIL改PASS。

Scrapling已作P03隔離工具選項及限縮實測，沒有全面取代既有官方API。MOPS財報清單／timestamp／文件鏈仍缺完整PDF EOF；EZSearch／月營收／TWSE舊timeout及partial都保持FAIL。月營收及TWSE既有GET scope已耗完，不得盲重抓；財報scope先核原attempt帳本，不能重置額度。TWSE保存原件的exact單位／版本品質與正式publisher、source/use一次性接受、歷史PIT、完整Recommendation／雙策略盈虧、真N、Native／EXE及paper/forward自然成熟仍待。

依原A工具／B時間／C重複驗證／D品質、歷史、執行與自然成熟分流；來源用途一次性接受與每日自動validator分開，失敗隔離具體原因。Scrapling全面完成不是其餘包前置。正式資料寫入、全量回補、正式Task變更仍依已有精確授權；Direct maintainer已由另一owner依精確授權停用，不自動啟用／重觸發。本任務沒有push、發布或交易授權；工期未知，不編造估算。

## 可直接貼到新對話的Prompt

```text
/goal 請恢復 C:\Projects\PythonProjects\technical_analysis 的 Baldr 產品補完工作，沿原計畫推進，不另建競爭總計畫。

先遵守現行 AGENTS.md，讀取：
- docs/06_qa/BALDR_COMPLETION_HANDOFF_20261014_INCREMENT19.md（最新交接，優先於更早的歷史待辦）。
- docs/00_core/PROJECT_SNAPSHOT.md。
- docs/06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md 的最新 Increment18／19。
- docs/superpowers/plans/baldr_product_completion_plan_20261006.md，特別是§9.5。
- docs/06_qa/BALDR_COMPLETION_CHECKPOINT_20261014.md 作歷史參照；active_task／handoff_log只讀核對，不覆寫其他owner singleton。若路徑變更循現行索引。
- output/tasks/baldr-completion-policy-20261014-01a1390b/task.json、handoff_commit.json、increment18_safe_resume.json、increment19_static_candidate_qa00.json及交接列出的具名收據。

先簡短回報HEAD、工作樹、收據SHA、pending候選與資源，再工作。不要把commit、靜態guard、局部PASS或案例加總當完整Gate。

目前狀態：Increment18的P03正常F17 archived Source3／Recipe3／Bookmark3／Main／Watchlist及新程序54640→32420已限定驗證，full258、26固定來源與320 F17原資產相同；原V1/V2回歸、Workbench85及validator25/0/4通過。Increment19三個P08新模組、三份測試及public portfolio reader增量已提交為WIP，但完全未compile／mypy／pytest；最後因RAM低於8GiB未啟動QA。策略metadata/artifact/precision交叉綁定已在pair層靜態補入，仍待驗。mypy既有ui_qt.* ignore_errors=True不證UI強型別。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未接受。

新Root建立自己的task並引用舊task／sealed證據，保留舊task及output原件。QA02 spec只作待執行命令模板：先核七來源pins與本次HEAD，再將runner TASK、spec、隔離env及result directory另存到自己owner的task，重新綁SHA，不直接寫舊owner task或覆寫原spec。首組期限沿原compile30秒、mypy180秒、calendar codec120秒、artifact120秒、pair180秒；失敗保存原收據，只修／重驗受影響部分。通過後補受改public Reader的Registry/artifact原回歸，再接正常Backtest雙exact run保存／重開／比較／返回及新程序。

Root：Sol；workers：Luna Max。可立即安排三路靜態工作以加速：
A. 日曆raw custody、schema／版本、兩市場缺日與93日邊界。
B. Registry兩策略、parent、metadata、source／currency／cost交叉綁定及public ports。
C. 原Backtest歷史頁的雙exact run選取、保存／重開／返回接線定位；Root凍結API後才改其分配葉片。
每路只給必要檔案與明確單寫ownership；Root保留金融判斷、共用ports、整合、QA與文件單寫。

嚴格資源規則：同時最多3名Luna；同一補完task跨交接累計已新建3/10，不因新對話重置。優先重用同session、已完成、無pending writes、context適當且無ownership衝突的代理；平台不能重用或context過大時，新對話可先再建最多3名（累計最多6/10），總新建永不超10。禁止子代理再產生子代理、按資料夾逐一建agent、多代理重複讀全庫。Worker只做靜態工作，禁止Python/import/compile/QA/network；全部Python與QA由Root串行。一個Windows Job最多8GiB committed／12程序、kill-on-close、同workspace mutex；啟動前至少8GiB可用RAM。前組三PID陣列真正空、process／Job handles關閉、mutex釋放後才起下一組。等待逾時追同一session，不盲重跑、不kill其他owner程序；保留斷言、PIT、來源守衛與原期限。

已決定的時間政策直接落實，不再詢問：每日固定成功抓取後保存不可覆寫版本；對應官方發布／更新timestamp統一台北時區，小時向上取整（14:45→15:00），使用不得早於成功批次完成。僅有基準日期時用成功批次小時並明示basis；保留原件、官方時間原文、批次時間、hash／version，更正另存。從首次成功保存建立前瞻可用性；歷史用途仍按實際版本證據，不永久阻擋已驗證新快照的日常研究，也不消除舊FAIL／造歷史PIT／提前成熟paper或forward。

Scrapling沿P03限縮工具選項（https://github.com/d4vinci/Scrapling），既有官方API沿用；僅在browser/session/動態來源需要時使用，不全面重寫或假設突破WAF。先核既有attempt帳本：月營收／TWSE舊GET scope已耗完、MOPS文件仍partial／缺EOF，不能重置額度盲重抓。優先功能必要的法人、月營收、財報／前期比較、注意／處置；信用／TDCC先核功能依賴，不擴成全市場全歷史。沿抓取→原件版本→解析品質→保存→public reader→正常UI→新程序。

依A工具／B時間／C重複驗證／D品質、歷史缺件、執行與自然成熟分流，來源用途一次性接受與每日批次validator分開；失敗隔離具體原因。必要變更沿P00/P03同步P07/P12及P13/P14。其他包與資料靜態工作可並行，Scrapling不是全計畫前置。完整PDF鏈、TWSE單位版本、官方用途接受、歷史PIT、真N、完整雙策略績效、Native/EXE及自然成熟仍獨立處理；unknown卡片不算功能補完。

保護docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md的其他owner未提交變更、所有原候選／FAIL／收據與320 F17原件；不重跑已保存的producer。正式資料寫入、全量回補、正式Task變更仍限既有精確授權，不自動啟用／重觸發已停用maintainer。不授權push、發布或交易；工期未知不估造。使用繁體中文，完成必要核對後直接推進，不停在建議。
```

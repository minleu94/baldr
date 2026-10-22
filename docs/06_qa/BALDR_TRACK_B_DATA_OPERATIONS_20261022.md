# Track B 金融資料與營運補完（2026-10-22）

裁決：`TRACK_B_ENGINEERING_IN_PROGRESS`。不宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`。Quick custody、Formal／Paper新終態、BankTaiwan有界控制面、Forward實際來源觀測、校準official invocation綁定及月營收decoder版本已有定向工程證據；仍有 **88筆legacy recommendation的原件custody未成立、mixed query維持拒絕**，以及修復後自然鏈尚未驗實。固定 V2 RC、275 項歷史驗證與 Track A/C 開發均不重開；不 push。

本機證據根：`output/tasks/baldr-track-b-data-operations-20261022/`。來源 HEAD `4dd820139148089ec09635ac5b0818409aa915df`；繼承恢復 `32d37e1295a1`。Release Closeout、UI 與儲存治理的他人變更保持。

## 自然排程與差異

本輪 COM 唯讀查詢 21/21，XML delta=0、20 enabled／Direct disabled，沒有手動觸發或更改 Task。`windows_observation.json` SHA `1b69b384ed3aea9230058b7df9de7baf178e516710a2144a5129f74748c09b61`；時點為 10/22 Pacific 日間。COM 的 LastRun 為本機無 offset 值，解讀沿該主機 Pacific；producer 各自的 aware clock 另核，不由字串補成跨時區接受。

51份Codex automation TOML與原after baseline逐檔SHA delta=0；廣義Baldr／repo／FA_Data相關48份，其中ACTIVE2份為 `baldr-scheduled-evidence-morning-report`（05:30）與 `paper`（06:20），其餘相關46份paused。兩份完整config SHA分別 `6072aa41d85b1079e988c933663d330448001fb7fbd9f5d367380d454ad9adc1`、`21bb4db1939e68ed625071c3fb94937c78611b907f80cfd6d6ec213fe172e9b3`；native view亦成功顯示，但沒有新的automation執行收據或用量證據，不能將ACTIVE當自然彙報已成功。未新建、恢復或修改任何automation。

`natural_receipt_index.json` 固定當前 21 條原件的 copy hash；`natural_receipts_v2/` 保留 bytes。新的 Freshness／Evidence immutable terminal 外部 SHA 已與 locator 一致，不改原件、不將失敗改成成功。

| 自然 lane | 本輪事實（Pacific） | 判定 |
|---|---|---|
| Quick | 10/22 04:20，run `20261022-29800`、result 1；TWSE 1,096／TPEx 868 原行情捕獲，SQLite sync 拒絕 excluded revision 的 D/F DB 身份失配 | 新工程失敗；DB 最新仍 10/20 |
| Freshness | 05:00，run `freshness-20261022T050002254164-59ed1b2cc320447c9235a39a30abc7a7`，degraded／result0；terminal SHA `5faaee3500f12355a61482305d5b1c8d72a8f06c02903d55ae528158f49326ae` | 新終態持久化已自然驗實；來源未恢復 |
| Evidence dry-run | 05:15，run `evidence-20261022T051502868661-39498d16fb9b4272802ff9efe5277452`，result2／recommendation not ready；terminal SHA `57153a4c64fb92eca77b8b21dc67c30f89c12f85cae409ae2c006753fb3e91d5` | 依賴拒絕且 child 未啟動；終態觀測已恢復 |
| ML Raw PIT | 05:05，run `raw-pit-20261022T120503240335Z-15760-6ec75109b13844ffb5a452365c86fc38`、result0，`blocked_upstream_not_ready`／Quick failed | 原不可觀測分支已有當日原因；不是 Raw PIT archive成功 |
| Calibration | 05:45，run `20261022-20261022T124502979715Z-7d72de3c680e`，result1／pinned raw terminal not eligible | 等同次合格 Raw PIT；沒有繞過來源拒絕 |
| BankTaiwan | 05:50，run `2026-10-22-attempt-001-a6f7ac66771e`，result2／failed_dependency／child exit2 | 新自然終態存在，金融與模型資格未接受 |
| Paper EOD | 06:00，gate `dependency_gate_20261022T130002973294Z_attempt1`、result2、1,970 blockers；SHA `bbf38f96d3b439559f151836e55c4648946d704ef755dabc84065a280c2a47fb` | Quick／SQLite stale；無當日 ledger消費成功 |
| Forward outcomes | 05:40，run `20261022T124003133789Z`、result2／outcome_price_missing；172 updated、21 missing price、56 pending，215 incomplete identities skipped | 真自然研究更新；不能稱完整成熟或訓練資料就緒 |

## 七維具名矩陣

工程、自然執行、來源資格、coverage、PIT、consumer 與外部條件各自判定。PARTIAL／UNKNOWN 不等於 PASS；金融 fail-closed 與工程缺陷分列。

| 線路 | Engineering | Natural execution | Source qualification | Coverage | PIT | Consumer | External dependencies |
|---|---|---|---|---|---|---|---|
| Quick→SQLite→技指 | custody／guard讀回PASS，待自然 | FAIL（10/22原run） | 原用途守衛保持 | raw當日／DB10/20 | 原歷史修訂拒絕保持 | 下游hold | 新自然run |
| Freshness | 終態工程自然驗實 | PASS（執行／degraded） | 不由probe授予 | 當日缺SQLite | UNKNOWN | 來源警告／hold | Quick |
| Evidence dry-run | 終態工程自然驗實 | BLOCKED_DEPENDENCY | UNKNOWN | recommendation缺件 | UNKNOWN | child未啟動 | Quick／Recommendation |
| ML Raw PIT | 診斷自然可觀測 | BLOCKED_UPSTREAM | UNKNOWN | 本次builder未啟動 | 當日archive未成立 | calibration拒絕 | Quick |
| Recommendation snapshot | gate拒絕保持；不重播writer | 10/22 result2／blocked | 非正式接受 | requested200／eligible1／degraded198／missing1 | 不外推 | paper frozen export `eligible_date_mismatch` | 同日合格來源／Paper契約 |
| Formal input | 新immutable終態定向PASS，待自然 | 10/21 21:25 result2（Taipei10/22）；10/22晚尚未到 | 未接受 | ready/compatible=0 | 未成立 | 拒絕 | 有效runtime／Owner來源包 |
| PIT preopen／sidecar | QA014有效binding讀回；三角色均09/09runtime過期 | 10/21 16:00／18:00 result2（Taipei10/22） | candidate-only | target10/22無capture | 不能用10/20 archive代替 | formal/OOS=false | 有效配置／cutoff前自然capture |
| Paper EOD／Portfolio | EOD新immutable終態與精確reader定向PASS，待自然；Portfolio待新run | EOD blocked；Portfolio上一run10/21 17:25 result2 | 真帳戶／cash／mark未接受 | 舊snapshot非當日 | 缺同日合法輸入 | 無ledger成功讀回 | Owner帳戶策略資金包／Quick |
| Forward outcomes | 實際fetch觀測／持久化前置guard定向PASS，待自然 | 真自然研究更新但blocked | research-only | 缺價與pending分列 | availability未知／非跨讀快照 | 不授ML／績效 | 官方價源／自然horizon |
| Calibration／BankTaiwan | 有界同次child控制面定向PASS，待自然；原依賴拒絕保持 | result1／2 | shadow-only | 合格samples未建立 | 不借舊source clock | 未就緒 | Raw PIT／snapshot |
| 月營收 | strict CP950相容、真歷史capture／隔離archive讀回PASS | 非獨立每日正式Task成功證據 | 原OpenData限定資格保持；新歷史HTML用途未接受／金額unit unknown | 原current1,981列；新增六月雙市場1,860列／1歷史月 | 歷史發布／修訂證據0 | 原YoY限定研究；新歷史候選與正式用途blocked | 官方unit proof／連續歷史／PIT／歷史來源用途 |
| Official market events | wrapper→historical child→manifest／canonical讀回相符 | 10/22 result0／published | corporate-action custody formal=false | 28,799事件；4 ambiguity | historical PIT=false；current-only另列 | 下游是否使用此版本不可由執行順序推定 | child資格／精確consumer版本 |
| Decision evidence | 同次兩child／stdout完整；新增有界integrity reason | result0／passed | research_only／natural_authority=false | 1,096 events；1,093 degraded／3 estimated | verified clock不等於歷史PIT | snapshot19warnings含recommendation integrity failure | 來源資格／legacy custody |
| Recommendation execution mixed query | 當前唯讀重現FAIL；不建通用D/F alias | 非新增自然run | 88 legacy原件equivalence未證 | canonical index33／legacy88；不回傳部分列表 | 不升格 | legacy data_path超出runs；fail-closed | 原legacy bytes／逐檔SHA及後續精確locator接線 |
| Copilot | 規則lane | result0／passed_rule_only | 模型資格未成立 | 不外推 | 不外推 | inference未跑 | 合格ML資料／模型 |
| ML allocation forward | 既有config producer拒絕保持 | 10/21 17:25 result2／blocked_config_producer | candidate-only | 沒有Taipei08:30前合格PIT archive | 當日cutoff未成立 | 不啟動正式forward | cutoff前自然PIT／有效Formal來源 |
| Promotion evidence→authority | fail-closed | result0／blocked→skipped | 未授promotion | evidence不足 | 未成立 | authority未啟動 | 合格同次evidence |
| Weekly collection | 既有人工review待處理 | 10/18 result1；本週尚未到 | child partial | 未全核 | 未外推 | 未接受 | monthly_statement review |
| Direct maintainer | 預期停用 | NOT_APPLICABLE | 不作模型成功證據 | 不外推 | 不外推 | 不啟動 | 不擅自開啟 |
| Windows／Codex | 定義無差異；timeout budget另列 | 21項按各run；heartbeat非producer | 不授金融資格 | 本機設定覆蓋 | 不適用 | 彙報契約 | DST實際讀回／設定可觀測性 |

## 工程修復與驗證

三份原修訂不在既有逐檔搬遷 SHA PASS 清冊；本輪依原 hash 鏈與正式DB受保護值／排除key的新唯讀稽核建立 custody-only pins，不改原 receipts／DB，不授歷史PIT。Profile SHA `5e3a31d9e867a5b7eb51979b7bbce41e34a74d75731d6475d5bc5c47626def1b`；14份修訂JSON、18份來源的精確路徑／原SHA固定，既存plain validation目錄只按固定名稱保留，不用其內容授金融資格。

| QA | 實際結果與界線 |
|---|---|
| QA001 | init-task／context child exit0、Job自然排空；外層cp1252顯示例外保留，後續明示UTF-8，未冒稱整個shell成功 |
| QA002／003／004／005 | 本機audit對migration scope／market optional欄位／session無journal／實際表名的假設先後拒絕，原FAIL保存；未放寬產品守衛 |
| QA007 | 唯讀語義核驗 **SCOPE_MATCHED／0 mismatch**：daily/technical各2,942排除key及3休市日；14,869 session rows×8欄，3,106 market rows×6欄；原hash鏈相符，DB身份／主檔狀態穩定，沒有正式資料寫入 |
| QA008／009 | 發現真reader未容許既存validation目錄與archive的D定位閉包；已用精確pins修復。另有mypy縮窄與本機pytest basetemp配置失敗，原FAIL保存 |
| QA010 | source pins在候選編輯期間變更，precheck拒絕、未跑測試；不是產品失敗原因 |
| QA011 | **真來源reader／writer guard讀回PASS**，Daily revision、Excluded、Session、Market均可讀；歷史PIT仍拒絕、formal training=false。整輪因新fixture缺nested exit與OS TEMP限制有2 FAIL，原件保留 |
| QA012 | 最終6檔compile、**89 passed／3 skipped**、**mypy6檔PASS**；skip為本機建立link權限，未宣稱該能力測到。修復沒有放寬原精度、時間或金融門檻 |
| QA013 | 測試3檔compile及真21項CLI成功；整輪full文件check仍FAIL，既有／他人文件output junction連結等96錯誤另作同checker增量核對，不能寫full PASS |
| QA014 | 三角色有效runtime唯讀probe與文件增量check通過；Formal／PIT preopen／sidecar均 `runtime_config_expired:2026-09-09:2026-10-23`；原binding SHA未變。文件current1／baseline1／new0、metadata0，不宣稱full check通過 |
| QA015／016 | 六月新雙市場offline plan成功；單次capture取得完整EOF/raw SHA/Content-Length，因MOPS宣告Big5與CP950擴充不相容而strict decode失敗，原FAIL及raw hops保存，未重抓 |
| QA017／018 | 新測試fixture鍵名／重複固定clock與實際控制reader缺import先後失敗，原FAIL保存；真20 MB日誌投影6,002 bytes、分類前後一致、金融flags不升格；無producer replay |
| QA019 | Forward／monthly codec **128 passed**；4檔mypy因兩處新增註記失敗，原件保留後修正 |
| QA020 | 最終8檔compile、**123 passed／4 skipped**、**mypy5檔PASS**；skip為link權限。完整六月capture離線重建、原hash／三跳／parser及reader通過：TWSE995、TPEx865；不接受歷史可用時間、單位或用途 |
| QA021 | 經既有import接口追加全新隔離archive並讀回，1,860列／1歷史月，index SHA `2bf763d1bf0a03ec84b3712a02642d1466b3894b26c4f562cbb39a18d5343048`；license not accepted、unit unknown、PIT=false。原capture及FAIL不動 |
| QA022 | EOD reader 4檔compile、**34 passed**、**mypy2檔PASS**；固定原自然manifest重讀，application=BLOCKED_SOURCE、overall仍EXECUTION_FAILED、financial／observability仍UNKNOWN；原1,970 blockers只計數，不作逐條驗證或producer run身份主張 |
| QA023 | decoder profile／舊格式相容 **94 passed**、mypy2檔PASS；整輪因本機r2 helper仍引用既有report名而拒絕，沒有覆寫舊件，原FAIL保存 |
| QA024 | source綁定首輪90 passed／9 FAIL，主機OUTPUT_ROOT污染fixture routing；另16個新增optional型別問題，原件保留。r2 capture重建成功，明示CP950 profile／parser v2且raw bytes不變 |
| QA025 | 新Paper終態72 passed／1 fixture FAIL（誤期待純adapter驗真合法形狀SHA），mypy4檔PASS；舊EOD再讀與r2 archive追加／重開成功。r2 index SHA `9a36e482b106c9e54e2aa45fc9291b32a1490de877cf703c3f4caeb1cec489f1`；舊r1保留、不重算月份數 |
| QA026 | 只在QA child明示unset DATA_ROOT／OUTPUT_ROOT／CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT後，**102 passed**、mypy3檔PASS；不改主機／產品環境或原測試門檻 |
| QA027／028 | 精確aggregate path與新Paper adapter／原SHA否決、Bank相容 **169 passed／4 skipped**；整輪因1處型別收窄FAIL保留。最後compile、**54 passed**、**mypy7檔PASS**；gate ref明示shape_only_producer_asserted，finance仍UNKNOWN |
| QA029／030 | importer診斷與archive **18 passed**、mypy2檔PASS；當前唯讀query重現拒絕、DB stat穩定。QA029本機archive helper相對root被拒，原FAIL保存；QA030改為canonical absolute任務根後，舊v1／新v2 archive均重開1,860列成功，88筆legacy catalog唯讀核驗完成 |
| QA031 | 47檔scope／coverage更新；同checker文件current1／baseline1／new0、metadata0。兩份r2交付契約各12份引用SHA全數相符，未授training／OOS／金融資格；全庫文件check仍不宣稱PASS |

所有Python由root串行使用Windows Job：8 GiB committed／12 processes／kill-on-close／workspace mutex；鎖忙時不啟動child，原拒絕保存；正常完成的Job均自然剩餘0、handles關閉／mutex釋放。其他Track曾推進HEAD，版本precheck拒絕另保留，重取當前HEAD與pins後才執行。

自然CLI manifest SHA `1d6c84b522b4d9af0670a7225e2f79b80c327f25c8e78dc9111898887268c939`，原CLI輸出 `natural_audit_cli_stdout.json`：HEALTHY2／DEGRADED2／EXECUTION_FAILED13／UNKNOWN4。Freshness application=DEGRADED／observability=HEALTHY，Evidence application=BLOCKED_SOURCE／observability=HEALTHY，ML raw observability=HEALTHY但來源blocked。原Paper EOD的receipt_blockers_invalid保持於原CLI輸出；新reader在512KiB／原SHA／exact schema、來源stale／write=false及五分鐘scheduler時間關聯下，只投影明示的BLOCKED_SOURCE與1,970計數，不逐條驗證超128清單、不補producer run ID。新輸出 `natural_audit_after_eod_reader.json` 仍保持overall EXECUTION_FAILED及financial／observability UNKNOWN，兩份判讀均保留。

### 尚存工程與下一步

- BankTaiwan本run的child stdout為20,312,574 bytes，超既有16,777,216上限，`child_payload_source=child_stdout_artifact_size_limit_exceeded`、terminal readback失敗。新控制面以固定lane路徑、nonce、同parent run／日期／cost／DB／snapshot及外部SHA驗證512 KiB內typed receipt，再核原child run receipt；保留大型完整日誌及原cap。定向PASS不替原child exit2改判，也不證明下一自然run已恢復。
- Forward本run172筆為95 ready／56 pending／21 missing price。新工程在實際fetch保存query／params／rows／cache reuse與outcome對應，create-only持久化及讀回先於upsert；同recorder與同run ID重用均拒絕。availability仍unknown、PIT／training=false、跨query一致性未保證；不事後替舊172筆補來源，不以動態DB hash冒充PIT。
- **尚未完成的來源工程：Forward逐筆價格版本／可得時間映射。** 靜態複核未找到現成合格resolver；`daily_prices`沒有source version／revision ID／available_at，同鍵更新不保留舊版本，revision gate只核全域cutoff。須先具備逐筆row至已接受不可變官方payload／revision／SHA及可信發布／本機可得時間的權威映射，再實作consumer讀回；不能由同值比對或全域gate推定來源。新fetch觀測工程PASS只限實際讀取與持久化，並非完整金融lineage工程PASS；不改正式DB或回填舊outcomes補造資格。
- Formal／PIT當前實際binding三角色同樣拒絕09/09過期runtime，不再以舊path mismatch作當前根因。有效資料用途批准仍不可代理；新的Formal終態只影響下一run，不補舊收據。
- **尚未完成的工程：legacy recommendation custody reconciliation／精確reader接線。** 當前query以強制SQLite `ro/query_only`重現 `legacy data_path 超出 runs 目錄範圍`；canonical index33筆、legacy88筆，88個data_path均仍指D，原D檔均不存在，F counterpart均存在。逐一查原target SHA receipt，88份全部沒有逐檔entry／原SHA PASS；當前F hash僅是新觀測，不足證明原件同一性。不得改DB路徑、建立通用D/F alias、跳過legacy回傳部分結果或口頭接受來源。取得原bytes／外部固定原SHA與custody後，才可實作有限locator、全88讀回及負向回歸；目前具名缺件保留。
- 這次current query probe不是舊Decision run的事後完整根因。原自然child只保存泛化error，沒有cause path／SHA；新importer保留原訊息與拒絕行為，僅將exception type／240字內reason放入diagnostic metadata，讓下一自然run可定位。沒有偽造舊metadata或重建snapshot。
- Task設定未有差異；16項沿既有PT72H與IgnoreNew，Bank upstream wait＋child＋flush恰為5h，是timeout政策檢視點，未觀測到本run因該limit而timeout，不在此改設定或默默放寬期限。

官方來源新有界查詢仍未建立API金額unit proof。[政府資料集18420](https://data.gov.tw/dataset/18420)有14欄、來源與OGL資訊，未提供可綁定此API金額的單位；另找到的[舊TWSE申報說明](https://www.twse.com.tw/staticFiles/news/event/event_download_201501141045_02.pdf)是申報系統文件，並非這兩個OpenAPI endpoint／parser／field mapping的外部固定unit artifact。未存原bytes／typed proof，也未升格單位或重抓已耗盡的歷史入口。

## 可用範圍、自然等待與 Owner 最小決策

可安全交付：原件／新自然終態的唯讀診斷，以及已通既有契約的限定研究範圍。月營收1,975列YoY與6 unknown沿原百分率研究reader；金額單位未知，不標TWD。六月隔離archive新增的是1個雙市場歷史報表月份、1,860列，不是全市場完整或連續TTM；其raw SHA為TWSE `116fa1f6b8a78e8b145b39c1b5048618a92a6df4399698a0d5669ed5c58a5c52`、TPEx `a2e4340708c27b0c208b195a1f4f6829903f72b294d8f16337a0b5c2fd3a19e9`。取得時鐘為2026-10-23 Taipei 03:21:34／03:21:42，不是六月官方發布時間；歷史HTML用途／license未接受。無正式Scoring／Backtest／Paper／Forward／ML資格升格。歷史SQLite已有2014起月營收值與部分舊PIT日期，與本次具名archive範圍不同，不能混算。

待自然累積：修復後Quick與下游同次收據、PIT cutoff前新capture、Forward官方交易日horizon及合格樣本；不能手動執行冒稱自然恢復。

Owner不可代理決策最小包：

1. **正式runtime與來源用途版本**：選定有效日期／版本及其外部接受reference／SHA，具名 clock／universe／owner acceptance、Source／Revision／Custody與consumer用途。當前binding固定09/09候選配置、仍帶D來源根，不能直接延長日期或沿用批准授新來源。
2. **Paper正式輸入**：選定真帳戶、策略policy及其版本、合法cash／mark與官方日曆／Ledger來源。研究500,000 TWD或9/7舊cash不是正式來源。
3. **Weekly monthly_statement**：對原具名partial child作人工review或提供合格替代版本；不重試已耗盡入口冒稱成功。

官方金額單位、完整歷史報表及當時發布／修訂證據是外部資料條件，不可由Owner口頭接受替代。已授全用途開發範圍不再重批。

Track C 的 ML Data Readiness 與 Track A 的唯讀研究展示見 [共用交付契約](../03_data/BALDR_TRACK_B_DATA_READINESS_CONTRACT.md)。

機器可讀交付位於本任務 `ml_data_readiness_contract_r2.json`（SHA `f2b68daa108933156de87ec243a9a48f45d45f33eb15a8378c04a564515fe204`）與 `readonly_research_display_contract_r2.json`（SHA `8f650d909b88e4a9cc5e87bc53a75f5706c87a810c2b4c93341a71aa568614db`）。兩份均固定原證據引用，明示不是已合格訓練資料集／新增金融接受；training／validation／OOS／promotion=false，UI不使用不完整fallback或將研究cash當真資金。Legacy custody原件屬不可替代外部證據，不由Owner口頭批准代替。

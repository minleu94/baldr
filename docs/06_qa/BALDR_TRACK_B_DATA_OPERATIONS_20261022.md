# Track B 金融資料與營運補完（2026-10-22）

裁決：`TRACK_B_ENGINEERING_IN_PROGRESS`。不宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`。Quick custody、Formal／Paper新終態、BankTaiwan有界控制面、Forward實際來源觀測與同次fetched row來源身份、校準official invocation綁定、TPEx同次逐列來源證據及月營收decoder版本已有定向工程證據；仍有 **88筆legacy recommendation的原件custody未成立、mixed query維持拒絕**、Forward可信可得時間／用途與歷史修訂的合格resolver未接通，以及修復後自然鏈尚未驗實。QA024正式metadata污染與人工cache修復另有原貌／SHA記錄，不納入自然執行。固定 V2 RC、275 項歷史驗證與 Track A/C 開發均不重開；不 push。

本機證據根：`output/tasks/baldr-track-b-data-operations-20261022/`。來源 HEAD `4dd820139148089ec09635ac5b0818409aa915df`；繼承恢復 `32d37e1295a1`。Release Closeout、UI 與儲存治理的他人變更保持。

## 自然排程與差異

本輪 COM 唯讀查詢 21/21，XML delta=0、20 enabled／Direct disabled，沒有手動觸發或更改 Task。`windows_observation.json` SHA `1b69b384ed3aea9230058b7df9de7baf178e516710a2144a5129f74748c09b61`；時點為 10/22 Pacific 日間。COM 的 LastRun 為本機無 offset 值，解讀沿該主機 Pacific；producer 各自的 aware clock 另核，不由字串補成跨時區接受。

51份Codex automation TOML與原after baseline逐檔SHA delta=0；廣義Baldr／repo／FA_Data相關48份，其中ACTIVE2份為 `baldr-scheduled-evidence-morning-report`（05:30）與 `paper`（06:20），其餘相關46份paused。兩份完整config SHA分別 `6072aa41d85b1079e988c933663d330448001fb7fbd9f5d367380d454ad9adc1`、`21bb4db1939e68ed625071c3fb94937c78611b907f80cfd6d6ec213fe172e9b3`；後續由native目標聊天讀回兩份10/22 heartbeat completed終態，詳下節。這證明監測執行，不授producer成功／金融資格，也沒有準時性或模型／用量證據。未新建、恢復或修改任何automation。

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
| TPEx日價逐列來源 | raw→重解析17欄→CSV→merged→readonly SQLite定向PASS | 新接口尚無自然收據 | candidate-only；URL／參數固定 | 僅本次捕獲無歧義列 | published／available未知，false | 獨立tpex_row_evidence；不授Forward／ML | 新自然捕獲／來源接受／可信可得時間 |
| Freshness | 終態工程自然驗實 | PASS（執行／degraded） | 不由probe授予 | 當日缺SQLite | UNKNOWN | 來源警告／hold | Quick |
| Evidence dry-run | 終態工程自然驗實 | BLOCKED_DEPENDENCY | UNKNOWN | recommendation缺件 | UNKNOWN | child未啟動 | Quick／Recommendation |
| ML Raw PIT | 診斷自然可觀測 | BLOCKED_UPSTREAM | UNKNOWN | 本次builder未啟動 | 當日archive未成立 | calibration拒絕 | Quick |
| Recommendation snapshot | gate拒絕保持；不重播writer | 10/22 result2／blocked | 非正式接受 | requested200／eligible1／degraded198／missing1 | 不外推 | paper frozen export `eligible_date_mismatch` | 同日合格來源／Paper契約 |
| Formal input | 新immutable終態定向PASS，待自然 | 10/21 21:25 result2（Taipei10/22）；10/22晚尚未到 | 未接受 | ready/compatible=0 | 未成立 | 拒絕 | 有效runtime／Owner來源包 |
| PIT preopen／sidecar | QA014有效binding讀回；三角色均09/09runtime過期 | 10/21 16:00／18:00 result2（Taipei10/22） | candidate-only | target10/22無capture | 不能用10/20 archive代替 | formal/OOS=false | 有效配置／cutoff前自然capture |
| Paper EOD／Portfolio | EOD新immutable終態與精確reader定向PASS，待自然；Portfolio待新run | EOD blocked；Portfolio上一run10/21 17:25 result2 | 真帳戶／cash／mark未接受 | 舊snapshot非當日 | 缺同日合法輸入 | 無ledger成功讀回 | Owner帳戶策略資金包／Quick |
| Forward outcomes | 實際fetch觀測／持久化前置guard及Quick bundle→同次完整列身份綁定定向PASS，待自然 | 真自然研究更新但blocked；新接口未自然驗實 | identity bound仍非用途接受／research-only | 缺價與pending分列；新production bindings未觀測 | availability未知／非跨讀快照 | 不授ML／績效 | 可信時點／用途／歷史修訂、自然horizon |
| Calibration／BankTaiwan | 有界同次child控制面定向PASS，待自然；原依賴拒絕保持 | result1／2 | shadow-only | 合格samples未建立 | 不借舊source clock | 未就緒 | Raw PIT／snapshot |
| 月營收 | strict CP950、隔離archive與真原件scale-only proof讀回PASS | 非獨立每日正式Task成功證據 | 原OpenData限定資格保持；六月HTML千元尺度已綁，幣別／用途未接受 | 原current1,981列；新增六月雙市場1,860列／1歷史月 | 歷史發布／修訂證據0 | 原YoY限定研究；新歷史候選與正式用途blocked | 幣別／完整unit用途證據、連續歷史／PIT／歷史來源用途 |
| Official market events | wrapper→historical child→manifest／canonical讀回相符 | 10/22 result0／published | corporate-action custody formal=false | 28,799事件；4 ambiguity | historical PIT=false；current-only另列 | 下游是否使用此版本不可由執行順序推定 | child資格／精確consumer版本 |
| Decision evidence | 同次兩child／stdout完整；新增有界integrity reason | result0／passed | research_only／natural_authority=false | 1,096 events；1,093 degraded／3 estimated | verified clock不等於歷史PIT | snapshot19warnings含recommendation integrity failure | 來源資格／legacy custody |
| Recommendation execution mixed query | 當前唯讀重現FAIL；不建通用D/F alias | 非新增自然run | 88 legacy原件equivalence未證 | canonical index33／legacy88；不回傳部分列表 | 不升格 | legacy data_path超出runs；fail-closed | 原legacy bytes／逐檔SHA及後續精確locator接線 |
| Copilot | 規則lane | result0／passed_rule_only | 模型資格未成立 | 不外推 | 不外推 | inference未跑 | 合格ML資料／模型 |
| ML allocation forward | 既有config producer拒絕保持 | 10/21 17:25 result2／blocked_config_producer | candidate-only | 沒有Taipei08:30前合格PIT archive | 當日cutoff未成立 | 不啟動正式forward | cutoff前自然PIT／有效Formal來源 |
| Promotion evidence→authority | fail-closed | result0／blocked→skipped | 未授promotion | evidence不足 | 未成立 | authority未啟動 | 合格同次evidence |
| Weekly collection | 既有人工review待處理 | 10/18 result1；本週尚未到 | child partial | 未全核 | 未外推 | 未接受 | monthly_statement review |
| Direct maintainer | 預期停用 | NOT_APPLICABLE | 不作模型成功證據 | 不外推 | 不外推 | 不啟動 | 不擅自開啟 |
| Windows／Codex | 定義無差異；timeout budget另列 | 21項按各run；兩個10/22 heartbeat completed已讀回，非producer成功 | 不授金融資格 | 21 Tasks／51設定／兩個具名目標turn | 不適用 | 監測回報有執行；準時性未授PASS | dispatch原因／模型／用量未暴露 |

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
| QA032／033 | Forward剩餘契約文件增量current1／baseline1／new0、metadata0；後續fixture自行隔離主機roots的75項通過，canary未建立、正式Quick三份metadata SHA未再變；原QA024污染另外保存並修復cache，不抹去history／log |
| QA034／035／036 | TPEx候選先10 FAIL／74 passed及2個型別錯誤，再4 FAIL／80 passed及mypy5 PASS；原件保存。CSV空欄／pandas文字欄NaN與readback修正後84 passed、mypy5 PASS；不接受缺值為零 |
| QA037 | scale-only proof合成12 passed／1 link權限skip、mypy1 PASS；真六月原件因巢狀wrapper／跨列表頭尚不相容而FAIL，未產生合格proof；此FAIL保留，後續另驗 |
| QA038 | 獨立review指出原請求URL被final URL取代，已分開保存、核官方端點及日期／重複參數；非官方redirect在CSV前拒絕。最終compile、87 passed、mypy5 PASS；先前鎖忙125無child另存，不冒稱驗證失敗後重啟活程序 |
| QA039／040／041 | 真HTML跨列表頭修正後合成16 passed／1 skip、mypy1 PASS，但遇存託憑證空表仍FAIL保留。QA040唯讀形狀診斷確認其唯一零合計空表；精確支援後21 passed／1 link權限skip、mypy1 PASS，真雙市場proof create-only及讀回PASS，995／865公司列與33／28表數不變 |
| QA042 | fingerprint改為不受Decimal context精度影響的字串正規化，避免不同來源值在低精度下合併；有界數字編碼拒絕極端指數。最終compile、89 passed、mypy5 PASS，沒有新增金融值計算或資格 |

所有Python由root串行使用Windows Job：8 GiB committed／12 processes／kill-on-close／workspace mutex；鎖忙時不啟動child，原拒絕保存；正常完成的Job均自然剩餘0、handles關閉／mutex釋放。其他Track曾推進HEAD，版本precheck拒絕另保留，重取當前HEAD與pins後才執行。

自然CLI manifest SHA `1d6c84b522b4d9af0670a7225e2f79b80c327f25c8e78dc9111898887268c939`，原CLI輸出 `natural_audit_cli_stdout.json`：HEALTHY2／DEGRADED2／EXECUTION_FAILED13／UNKNOWN4。Freshness application=DEGRADED／observability=HEALTHY，Evidence application=BLOCKED_SOURCE／observability=HEALTHY，ML raw observability=HEALTHY但來源blocked。原Paper EOD的receipt_blockers_invalid保持於原CLI輸出；新reader在512KiB／原SHA／exact schema、來源stale／write=false及五分鐘scheduler時間關聯下，只投影明示的BLOCKED_SOURCE與1,970計數，不逐條驗證超128清單、不補producer run ID。新輸出 `natural_audit_after_eod_reader.json` 仍保持overall EXECUTION_FAILED及financial／observability UNKNOWN，兩份判讀均保留。

## 後續核對與尚存工程

### 13:20 後續唯讀核對與 QA 隔離修復

2026-10-22 Pacific 13:20 重新讀回21項Task，XML差異0、新自然執行0，Direct仍停用；不是等待中程序或新自然成功。首份觀測器把PowerShell反序列化的DateTime與字串比較，誤列run_changed，原件保留；r2按ticks重核，SHA `d406e8bda4f114878e474cb18e52c8870e118871ff302927f1adaf0585fb4314`，以此分類為準。

新核對查出Quick可變`latest_status.json`在12:42變成52 bytes的`passed` fixture，SHA `d180875e35ddbfd489ac98cb14c6b882da518bf32dc92f065b87cd84885e3447`。實際日誌指向本任務QA024：臨時data root的測試繼承正式OUTPUT_ROOT，意外執行Quick入口並寫入正式metadata。history新增的`20261022-4252`、`20261022-31128`、`20261022-58464`皆為測試窗口2026-09-20的非自然嘗試，不得納入自然恢復。這是QA隔離失誤，不是排程成功；先前QA024只記routing污染的描述不足，於此補正。

污染的status／log／history原貌及SHA另存本task，不刪除或重寫log/history。已確認無同名producer活程序、Task仍04:20／result1且cache SHA未變後，只原子恢復可變status cache為先前固定SHA `9b238cf57c16cc807697b1b53ae6d1d0a490edbed5c3c00f3060449a6a5c89f1`的真自然失敗原bytes；另存`quick_status_cache_restoration.json`，明示人工cache修復、非新自然執行，未修改金融資料。正式DB未受此metadata修復觸碰；不由此聲稱全正式根在QA024期間逐檔無變動。

51份automation設定於13:39前後再核SHA仍無差異，無新增ID；`automation_revalidation_20261022T2040Z.json` SHA `7fc0729680284211a3a32db863aff8e08e94cef2bd8dc36f23dd1f63b514c6ef`。沒有runtime執行收據核驗，不將設定不變當彙報自然成功。

兩個會啟動pipeline／寫child fixture的測試模組已自行清除DATA_ROOT、OUTPUT_ROOT及CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT，不再僅依外層runner。QA033注入task內canary root後75項通過，canary未建立，三份正式Quick metadata均與保存的污染快照SHA相同，證明該輪未再寫入；它不抹去QA024既有影響。原失敗與人工修復收據均保留。

### 仍需接續的工程與外部條件

- BankTaiwan本run的child stdout為20,312,574 bytes，超既有16,777,216上限，`child_payload_source=child_stdout_artifact_size_limit_exceeded`、terminal readback失敗。新控制面以固定lane路徑、nonce、同parent run／日期／cost／DB／snapshot及外部SHA驗證512 KiB內typed receipt，再核原child run receipt；保留大型完整日誌及原cap。定向PASS不替原child exit2改判，也不證明下一自然run已恢復。
- Forward本run172筆為95 ready／56 pending／21 missing price。新工程在實際fetch保存query／params／rows／cache reuse與outcome對應，create-only持久化及讀回先於upsert；同recorder與同run ID重用均拒絕。availability仍unknown、PIT／training=false、跨query一致性未保證；不事後替舊172筆補來源，不以動態DB hash冒充PIT。
- TPEx上游前瞻來源工程已補：原raw序號／hash經既有官方parser與normalizer重建17欄，CSV與合併frame／readonly SQLite逐鍵核對後發immutable publication；Quick只傳本次descriptor，不掃舊CSV補證。QA038已含真UpdateService接線、同鍵歧義、source artifact漂移、重算manifest／CSV自身hash仍不能改raw投影、SQLite改值／缺列及非官方URL／錯日期拒絕。這使前瞻列證據更完整，但沒有來源用途接受或可信官方availability，尚未接成Forward合格resolver；不回填10/22舊outcomes或寫正式DB。
- **尚未完成的來源工程：Forward逐筆價格版本／可得時間映射。** 靜態複核未找到現成合格resolver；`daily_prices`沒有source version／revision ID／available_at，同鍵更新不保留舊版本，revision gate只核全域cutoff。須先具備逐筆row至已接受不可變官方payload／revision／SHA及可信發布／本機可得時間的權威映射，再實作consumer讀回；不能由同值比對或全域gate推定來源。新fetch觀測工程PASS只限實際讀取與持久化，並非完整金融lineage工程PASS；不改正式DB或回填舊outcomes補造資格。
- Formal／PIT當前實際binding三角色同樣拒絕09/09過期runtime，不再以舊path mismatch作當前根因。有效資料用途批准仍不可代理；新的Formal終態只影響下一run，不補舊收據。
- **尚未完成的工程：legacy recommendation custody reconciliation／精確reader接線。** 當前query以強制SQLite `ro/query_only`重現 `legacy data_path 超出 runs 目錄範圍`；canonical index33筆、legacy88筆，88個data_path均仍指D，原D檔均不存在，F counterpart均存在。逐一查原target SHA receipt，88份全部沒有逐檔entry／原SHA PASS；當前F hash僅是新觀測，不足證明原件同一性。不得改DB路徑、建立通用D/F alias、跳過legacy回傳部分結果或口頭接受來源。取得原bytes／外部固定原SHA與custody後，才可實作有限locator、全88讀回及負向回歸；目前具名缺件保留。
- 這次current query probe不是舊Decision run的事後完整根因。原自然child只保存泛化error，沒有cause path／SHA；新importer保留原訊息與拒絕行為，僅將exception type／240字內reason放入diagnostic metadata，讓下一自然run可定位。沒有偽造舊metadata或重建snapshot。
- Task設定未有差異；16項沿既有PT72H與IgnoreNew，Bank upstream wait＋child＋flush恰為5h，是timeout政策檢視點，未觀測到本run因該limit而timeout，不在此改設定或默默放寬期限。

官方來源新有界查詢仍未建立API金額unit proof。[政府資料集18420](https://data.gov.tw/dataset/18420)有14欄、來源與OGL資訊，未提供可綁定此API金額的單位；另找到的[舊TWSE申報說明](https://www.twse.com.tw/staticFiles/news/event/event_download_201501141045_02.pdf)是申報系統文件，並非這兩個OpenAPI endpoint／parser／field mapping的外部固定unit artifact。未存原bytes／typed proof，也未升格單位或重抓已耗盡的歷史入口。

## 可用範圍、自然等待與 Owner 最小決策

可安全交付：原件／新自然終態的唯讀診斷，以及已通既有契約的限定研究範圍。月營收1,975列YoY與6 unknown沿原百分率研究reader；金額單位未知，不標TWD。六月隔離archive新增的是1個雙市場歷史報表月份、1,860列，不是全市場完整或連續TTM；其raw SHA為TWSE `116fa1f6b8a78e8b145b39c1b5048618a92a6df4399698a0d5669ed5c58a5c52`、TPEx `a2e4340708c27b0c208b195a1f4f6829903f72b294d8f16337a0b5c2fd3a19e9`。取得時鐘為2026-10-23 Taipei 03:21:34／03:21:42，不是六月官方發布時間；歷史HTML用途／license未接受。無正式Scoring／Backtest／Paper／Forward／ML資格升格。歷史SQLite已有2014起月營收值與部分舊PIT日期，與本次具名archive範圍不同，不能混算。

待自然累積：修復後Quick與下游同次收據、PIT cutoff前新capture、Forward官方交易日horizon及合格樣本；不能手動執行冒稱自然恢復。

六月HTML新增的單位尺度工程已由原capture重建驗真：五個金額欄明示千元尺度，三個百分率欄不乘1000。TWSE proof SHA `c5a998b5be056507f452f1b5b70081d033eaf25ac6c5dcee6a4b74fdca1b9336`、TPEx `a89e429422406c02e6beb61381206006f4545d3e39b638c1cb7af7839eeb2e0b`。這是逐表scale-only proof，不是幣別／用途齊全的unit proof，不覆寫r2 archive或unit_status，不外推OpenAPI、TWD、歷史可得時間或正式金融資格。

Owner不可代理決策最小包：

本輪Owner已直接回覆Formal有效runtime／來源用途包與真實Paper帳戶、策略、cash／mark／Ledger來源「尚未選定」。此為明確外部條件，不由程式選候選、延長日期或使用研究預設；以下第3項Weekly review不由這個回覆代替。

1. **正式runtime與來源用途版本**：選定有效日期／版本及其外部接受reference／SHA，具名 clock／universe／owner acceptance、Source／Revision／Custody與consumer用途。當前binding固定09/09候選配置、仍帶D來源根，不能直接延長日期或沿用批准授新來源。
2. **Paper正式輸入**：選定真帳戶、策略policy及其版本、合法cash／mark與官方日曆／Ledger來源。研究500,000 TWD或9/7舊cash不是正式來源。
3. **Weekly monthly_statement**：對原具名partial child作人工review或提供合格替代版本；不重試已耗盡入口冒稱成功。

官方金額單位、完整歷史報表及當時發布／修訂證據是外部資料條件，不可由Owner口頭接受替代。已授全用途開發範圍不再重批。

Track C 的 ML Data Readiness 與 Track A 的唯讀研究展示見 [共用交付契約](../03_data/BALDR_TRACK_B_DATA_READINESS_CONTRACT.md)。

機器可讀交付位於本任務 `ml_data_readiness_contract_r2.json`（SHA `f2b68daa108933156de87ec243a9a48f45d45f33eb15a8378c04a564515fe204`）與 `readonly_research_display_contract_r2.json`（SHA `8f650d909b88e4a9cc5e87bc53a75f5706c87a810c2b4c93341a71aa568614db`）。兩份均固定原證據引用，明示不是已合格訓練資料集／新增金融接受；training／validation／OOS／promotion=false，UI不使用不完整fallback或將研究cash當真資金。Legacy custody原件屬不可替代外部證據，不由Owner口頭批准代替。

後續r3交付為`ml_data_readiness_contract_r3.json`及`readonly_research_display_contract_r3.json`，保留r2，另附新自然／automation再核、QA024污染與cache修復、TPEx最終定向QA及六月scale-only proof引用；外部SHA與逐件引用核驗見`delivery_contract_r3_verification.json`。它們仍是readiness觀測／唯讀展示要求，不是訓練資料集或已接入新UI的聲明，亦不解除legacy或Forward缺件。

## 後續來源身份接線（同日 QA044–045）

13:52:55 PDT 再核21 Tasks：新LastRun=0、XML變更=0、21原收據SHA變更=0；`natural_revalidation_20261022T2053Z.json` SHA `7b1c0fc37c59810fb2583aeb1302c3e40214044289024369ae1637e693dbeda5`。這是唯讀再核，沒有重播producer。QA後Quick可變status仍為原失敗SHA `9b238cf57c16cc807697b1b53ae6d1d0a490edbed5c3c00f3060449a6a5c89f1`。

Quick新`daily-price-source-bundle.v1`只收同輪唯一SQLite sync step回傳的captured TWSE／TPEx descriptors，hash-addressed create-only run加精確locator；讀取前後核DB relative path與dev/ino。Quick passed只表示執行結果，bundle固定`natural_success=false`。Forward使用config來源根，與artifact output root分離；同一次SELECT取得完整17欄及既存方向別名，binder不另讀SQLite，兩family純verifier重建raw／parser／custody、逐列核完整內容；單一來源吻合才標`source_identity_bound`。DB在load／binding期間被替換、雙family歧義、來源缺件或同close但非價格欄漂移均拒綁。

原TWSE檔案讀取在新路徑改為bounded/no-follow、前後路徑chain身份檢查與strict JSON；TPEx補chain／累積budget。單輪已驗證來源cache最多4項，key含root／DB身份與descriptor pins，命中仍核每列內容，不依close推來源。新觀測v2把逐列binding與實際rows對齊chunk，另存binding SHA，原大小及保留上限不放寬；v1無binder caller保持。

QA044：14檔compile通過，123 passed／12 failed、4 mypy errors，原輸出保留。失敗包含新測試run ID不符固定格式、TWSE雙方向欄的null placeholder、TPEx負向誤用了同值42.50及cache分支型別；修正案例／實作，未放寬金融守衛。QA045：**138 passed、14檔compile通過、8來源檔mypy通過**，包括真合成TWSE下載→sync publication→bundle→Forward同次fetch→綁定、DB替換／cache／chunk與舊reader相容性。兩輪Job均自然terminal、remaining PIDs=0、handles關閉、mutex釋放、forced_cleanup=false。限定工程QA不是自然排程或整體金融Gate。

剩餘工程具名：來源用途接受與可信availability/cutoff接線、歷史被替換版本的custody／精確consumer讀回；88 legacy recommendation仍缺原件或獨立原SHA；有效Formal runtime及真Paper輸入仍待具名Owner來源包。新身份接線不補10/22舊172筆、不修改正式表schema、不授ML/OOS或交易權限。

月營收官方單位查詢另核政府18420／56510、TWSE OpenAPI與2013 IFRS申報說明；只找到來源／欄位及仟元申報尺度，未找到可精確綁本次兩OpenAPI與六月HTML幣別的證據。未借發行人其他報表授整市場TWD、未改原unit_status；既存scale-only proof及百分率研究範圍保持。

後續r4機器交付（保留r1–r3）：`ml_data_readiness_contract_r4.json` SHA `d52a6b5e24ab3266df01e3b1fe493ce3fd66ba310fb419a97192621f5669f28f`；`readonly_research_display_contract_r4.json` SHA `96a8a9299011e17bac28dc457aa8b2652a2cbe58bab3a82e51e44f84cb27da8c`。每份25個證據引用均按外部SHA讀回；格式與同次列身份接口已交付，PIT／training／OOS／promotion與交易資格不升格，production bindings仍未觀測。

## 後續有限完成審計：自然收據、日期守衛與 heartbeat

14:17:19 PDT 再核仍為21 Tasks、XML／LastRun及21 receipt SHA均零變更；Direct保持停用，沒有live producer等待或新自然成功。`natural_revalidation_20261022T2118Z.json` SHA `99ba4f6302059c2e42616d29f9666463edee695abc428013b9b209d9f383c1d5`。初次sandbox COM拒絕後，以核准elevated唯讀COM重查；不改ACL／Task、不重播producer。

Recommendation自然保存result `rec_49453d47e7304e2cb34613df311bb1db`的原artifact SHA `5769c262d8c935b666646480495fd5c40b65697ad8d6ee0afcc3d3e87d744b72`未變：context as-of及唯一入選列eligible date均為10/20，decision date為10/22；原quality含`natural_market_data_session_insufficient:stale:expected=2026-10-22:observed=2026-10-20`。因此Paper frozen日期拒絕是過時來源的預期fail-closed，不是已證實的日期adapter缺陷。`recommendation_frozen_date_cause_readback.json`保存精確crossbind／SHA與限制，不更改eligible date或重播writer。

Native目標聊天的兩個具名heartbeat已核：晨報thread `01a08626-6d14-7350-8502-61ba8fc3aa30`／turn `01a164cd-911a-7ec0-ab1a-cabfca99729e`，Paper thread `01a0b393-181a-7ef3-9ad7-2af05bc09f8b`／turn `01a164cd-9334-7911-a00f-b353917607d0`；兩輪started為10/22 18:09:16 UTC，分別completed 18:18:20／18:19:31，status completed、error=null且原heartbeat automation ID相符。讀取摘要`automation_runtime_observation_20261022T2122Z.json` SHA `614ac67f2fbc99db9c7e1b35227f8534cb447f9bc23635f12a4285bfc6adfb21`。這補上監測執行證據；不把名義05:30／06:20 Pacific與實際dispatch混為準時證明，dispatch原因／模型／用量未暴露。晨報內scheduler查詢UNKNOWN與Paper查到21項屬各自查核能力，本任務COM再核仍以本次原件為準。沒有發訊至目標聊天、修改prompt／cadence或新增automation。

獨立靜態複核重新區分了舊自然失敗與現行修復：Quick的04:20 excluded marker mismatch已由原hash鏈＋保護狀態的精確D/F custody及QA007／reader readback覆蓋，current profile／三個marker pins沒有新差異；不再因舊log重開相同修復。Formal三角色當前拒絕09/09過期配置，不以舊path mismatch作現因；尚未找到已批准的新runtime。Monthly既有capture/import/archive介面已能保存後續具名OpenData版本，但endpoint沒有期別回補參數；六月MOPS候選與金額／PIT接受界線保持，沒有可直接接用的新歷史或幣別原件。

現在的可執行恢復條件具名維持：下一個真正Quick／下游與Formal/PIT自然run；Owner明確選定Formal與Paper來源包；88 legacy原件custody；Forward已接受用途、可信availability/cutoff及歷史revision後的精確consumer接線；官方金額單位／幣別、連續歷史與公告／修訂證據；Weekly具名partial review。不能以stub、空資格resolver或研究現金宣稱剩餘工程已完成。

後續r5交付保留r1–r4：`ml_data_readiness_contract_r5.json` SHA `b6582cca898ab970e1c64a169c4184b3b24113065a39bef1fdfd6cc653f4c592`；`readonly_research_display_contract_r5.json` SHA `038ed16af88440f780aa15da629d82ae05006ebe805153e26d0a6fa2c6745c86`。每份28個證據引用驗真；兩個heartbeat完成僅授監測執行觀測，不授準時性或producer成功。Owner已回覆Formal/Paper來源尚未選定；所有金融、PIT、ML及交易資格保持。

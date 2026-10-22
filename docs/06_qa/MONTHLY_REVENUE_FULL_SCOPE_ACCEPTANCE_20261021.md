# 月營收全用途研究工程與資格矩陣

本輪從 `fd0e7302` 接續，沒有重啟 V2 或重建候選；獨立任務為 `output/tasks/baldr-monthly-revenue-full-scope`。Owner 全用途授權已確認，[權威契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)分開定義開發授權與逐用途資料資格。交付為Source研究管線與逐用途安全入口；不宣稱全部金融功能已合格或全部正式consumer已啟用。

## 已取得的實際證據

| 項目 | 結果與範圍 |
|---|---|
| Owner 授權 | 已確認，current-only 授權限制已撤銷；不需逐模組重批。正式資金、其他付費來源、Native 停止、實盤及發布限制保持。 |
| 官方身分／授權 | QA010 對政府資料集18420、56510及OGL第1版各一次有界GET，三份HTTP200／完整EOF／原HTML保存。授權不限目的但須顯名，不推定其他歷史HTML同授權。 |
| 精確API schema | QA011保存TWSE官方Swagger 309,960 bytes，SHA `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`；精確`/opendata/t187ap05_L`十四欄description未標金額單位，百分率欄標`%`。 |
| 金額單位 | 仍Unknown。沒有精確API欄位官方unit proof；未換算TWD。一般月營收簡報不能代替本API mapping。 |
| Current原件品質 | QA006重新驗上一輪官方捕獲原件SHA及parser，TWSE1,088列、TPEx893列、資料年月2026-09，共1,981列；保存為新不可變raw歸檔，不寫正式資料。 |
| 缺值 | TWSE MoM未知3、YoY未知1；TPEx MoM未知3、YoY未知5、累計YoY未知2。保留None／原因，不填零；完整期間／公司涵蓋未由列數推定。 |
| 原件版本歸檔 | QA006新index SHA `d24972f617277c25eb92dbf7ba0a7a1559505f1c8f73f3f1c517c9fa637be608`；市場＋公司＋期別隔離、原bytes/hash、修訂parent、同鐘異內容拒絕、晚歸檔不能倒填可見性。無mutable head，外部明選immutable parent可分支，並非跨程序CAS。 |
| Historical實際取得 | QA007四次direct GET失敗。QA020發現讀取底層chunk framing的工程錯誤，已修高層entity reader並保留原FAIL。QA024明選修正後官方鏈，兩市場2026-08各三跳：POST及popup完整成功，最終HTML HTTP200但期限內只觀測122,880／455,242與262,144／395,224 bytes，EOF=false，完整SHA=null。合格歷史月份版本仍0，未放寬期限、未把prefix拼成完整原件、未繼續重試。 |
| PIT | 官方歷史發布／當時版本／修訂證據0。captured-as-of與正式PIT分欄；舊daily series的PIT=false保持，沒有以當前snapshot補當年已知資料。 |

QA006 archive原件位置為本任務`current_archive`，外部hash及逐市場資料品質見`current_archive_report.json`。原TWSE SHA `a58c04b3bdc2b94632027018ca4f09f6ad053848addb7b9580b372626542fc17`、TPEx SHA `a27fea120daa8ef4543bcbf6e31426cad2e0201111ee8d97916fbb5fce2727a6`保持；這是既有原件重驗，不稱本輪又做新current GET。官方metadata三份原HTML及收據位於`official_metadata_qa010`，Swagger位於`official_swagger_qa011`。

## 工程與自動驗收

QA002初版用途政策22項通過。QA003／004／005分別暴露嵌套transport時區、測試helper結構與archive重開parent型別／索引取值等缺陷；原始FAIL保留。修正後QA006編譯及55項歷史capture／archive／用途policy／CLI測試通過，並實際歸檔上述兩市場原件。QA007驗的是有界取得流程與自然回收，資料結果仍是失敗，不能把runner完成改寫為歷史下載成功。

研究service新增原百分率、明選比較／條件篩選、分市場shadow排名、產業題材／Portfolio研究、完整月窗TTM／三月趨勢，以及回測／ML逐cutoff與Paper／Forward月營收feature的獨立用途入口。原推薦consumer另接精確OpenData source profile；共用identity抽至無IO的utils，保留原MOPS／normalizer／hash／comparator守衛。QA008–014逐輪FAIL包含語法、fixture、容器比較、型別及架構依賴問題，均保存原件；QA015後191項回歸與mypy11來源檔通過。QA016再加入檔案完整性守衛，編譯／192項／mypy11通過，但全輪因四個既有浮點邊界而FAIL；QA017以HEAD函式AST證明四處所屬函式完全未改，本輪新增／修改函式的精度與look-ahead靜態違規0。沒有改原checker或補marker使全檔綠燈。

只有外部固定SHA的資格reader核過來源接受revision及原件，研究服務才能放行；一般用途字串與reference不空不是capability。QA018第一份工程包因不符既有嚴格document schema被拒；原包保留，未放寬reader。QA019於全新`reviewed_percentage_shadow_r2`建立真原件limited／research_shadow包：以真Owner全用途授權與root原頁審閱為依據，審閱者明記AI、非Owner UAT；decision時鐘是工程審閱時間，並非偽造人類批准時間。官方metadata、capture與QA收據均有獨立預先固定SHA。未寫正式registry、Main設定或生產資料。

QA019真CLI從兩份原件重驗1,981列：YoY合格1,975、Unknown6；TWSE shadow1,087、TPEx shadow888。明選QA條件`YoY >= 0`命中1,408，Unknown6，資格拒絕0；該門檻僅驗證篩選，不是建議策略。fresh resolver重開通過、早於batch可得時間拒絕；全部14用途的TWD金額均拒絕。七個research用途的政策可放行原百分率，七個正式用途仍缺來源／下游Gate；政策PASS不能外推為歷史月份已存在或正式引擎已啟用。正式Scoring權重、撮合、cash／mark、ML Promotion與既有RC保持各自資格。

QA021晚歸檔與entity reader整合後227 PASS／1 fixture FAIL，原件保留；修正高層read1測試替身後，QA022編譯、228項、mypy11來源檔、量化增量與真raw／archive整合通過。真archive的批次可用時間是`2026-10-22T00:00:00Z`，實際落盤約`02:06:21Z`／`02:06:22Z`，archive可見下界為`03:00:00Z`；兩時鐘分列，不改opaque qualification evidence。QA022驗歸檔前拒絕及下界後研究讀取，後者cutoff當時仍在未來，明記`later_cutoff_simulated=true`，不稱自然時間已到或正式PIT。QA023再對精確官方query allowlist、不同period比較拒絕與歷史capture歸檔CLI執行72項及mypy3檔通過。

QA026最後離線補驗標準HTTP parser的完整／短Content-Length、chunked entity與socket deadline，40項及mypy1通過；完整framing後可無socket空讀確認EOF，未完或提前關閉仍拒絕，不再發HTTP。QA025對全部15份修改文件檢查仍有29個既有output junction越界引用；逐引用所在完整行與HEAD相同，原FAIL保留。新增文件／其他修改文件與Feature Map結構分別核對，不能將有限增量通過稱全庫連結全綠。原checker與舊引用未改。

所有本輪Python均由root序列於8GiB／12程序、kill-on-close及工作區mutex的owned Job執行；收據記錄正常結束、remaining_job_pids=[]、forced_cleanup=false。GUI未改控制項，Native仍`USER_STOPPED_ESCAPE`，Owner UAT仍`OWNER_UAT_NOT_PERFORMED`，沒有重建RC、push、排程或正式資料／資金寫入。

## 各用途目前判讀

| 用途 | 狀態 | 尚待證據或工程 |
|---|---|---|
| Current研究 | PASS（限定） | 明選2026-09兩raw的原百分率、品質及CLI真資料驗證；金額、全部公司完整性及Main TWD binding不在此PASS內。 |
| Historical研究／修訂 | PARTIAL | 分批計畫、原件版本與晚歸檔契約已驗；2026-09 current原件可按真實觀測時間回看，尚無長期月份或正式PIT覆蓋。 |
| YoY／MoM／基本面因子 | PASS（限定） | 原公布百分率研究；精確OpenData DTO可沿既有推薦投影到evaluator。金額衍生因子仍缺單位。 |
| 選股 | PASS（限定） | 真raw YoY及明選條件篩選；沒有更改預設策略或正式評分權重。 |
| 比較 | PASS（限定） | 同metric／unit／period、Decimal精確差值及資格拒絕有契約測試；caller明選股票，未產生投資建議。 |
| 產業／題材研究 | PARTIAL | 分市場shadow因子已真資料驗證；產業／題材歸屬仍由原合格成員來源提供，不以營收資料自造分類。 |
| 正式Scoring | BLOCKED_WITH_REASON | shadow工程通過；正式來源用途及Scoring Gate未成立，未改權重或啟用正式consumer。 |
| 正式Ranking | BLOCKED_WITH_REASON | 分市場shadow研究排名通過；不把shadow當正式Ranking接受。 |
| Portfolio Research | PASS（限定） | 明選權重、同metric／period、未知保留與Decimal基點契約通過；未指定真帳戶配置、未建持倉或預設本金。 |
| 回測／歷史績效 | BLOCKED_WITH_REASON | 逐歷史版本／官方可用時間、來源用途及回測Gate缺件；逐cutoff projector安全拒絕。 |
| Paper | BLOCKED_WITH_REASON | 月營收feature Gate已驗；營收不作cash／mark，來源用途及帳戶／策略／現金／行情守衛獨立，沒有正式建帳。 |
| Forward | BLOCKED_WITH_REASON | 月營收feature Gate已驗；來源用途、正式運行及自然成熟證據未成立。 |
| ML訓練 | BLOCKED_WITH_REASON | 逐cutoff projector已驗；官方PIT、來源用途及訓練Gate缺件，不以當前snapshot回填。 |
| ML驗證 | BLOCKED_WITH_REASON | 同上；研究工程驗證不構成模型Promotion。 |
| TTM／金額三月趨勢 | BLOCKED_WITH_REASON（資料） | 連續唯一月窗與精度工程已驗；實際完整月份、逐版精確單位及來源用途未具備。回溯研究不額外要求全部正式PIT。 |

## 具名補證方案

需要精確API欄位的官方schema／下載說明或來源機關確認，證明金額單位及對應市場／欄位，再固定官方URL、版本、原bytes SHA與mapping；未取得前保留unknown。歷史另需在既定資源範圍取得完整官方報表原件、確認該HTML授權適用範圍，再核當時發布／修訂證據。可先明選同範圍在有穩定網路的受控環境捕獲完整artifact，經外部SHA匯入候選歸檔；本輪不延長原期限或購買替代來源。沒有既有當時版本時，僅自真實觀測時間起累積，不推造更早PIT。這些是資料資格要求，不再要求Owner重批「是否可開發歷史／其他模組」。

本輪可安全交付的Source工程已完成；保留的PARTIAL／BLOCKED_WITH_REASON屬以上具名外部資料或獨立正式用途Gate，不作全部金融功能完成裁決。證據集中於本任務`evidence/`逐檔SHA清冊；原失敗、原件及舊候選保持，累計額外Credits授權上限12,500不重置，任務實際用量仍`USAGE_UNOBSERVABLE`。

# Track B 金融資料與營運補完（2026-10-22）

裁決：`TRACK_B_ENGINEERING_IN_PROGRESS`。不宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`；共同上游 Quick 的新自然失敗已完成精確 custody 定位並完成真來源guard讀回，Formal新終態完成定向驗證；BankTaiwan大輸出控制面與Forward價源lineage仍在處理。固定 V2 RC、275 項歷史驗證與 Track A/C 開發均不重開；不 push。

本機證據根：`output/tasks/baldr-track-b-data-operations-20261022/`。來源 HEAD `4dd820139148089ec09635ac5b0818409aa915df`；繼承恢復 `32d37e1295a1`。Release Closeout、UI 與儲存治理的他人變更保持。

## 自然排程與差異

本輪 COM 唯讀查詢 21/21，XML delta=0、20 enabled／Direct disabled，沒有手動觸發或更改 Task。`windows_observation.json` SHA `1b69b384ed3aea9230058b7df9de7baf178e516710a2144a5129f74748c09b61`；時點為 10/22 Pacific 日間。COM 的 LastRun 為本機無 offset 值，解讀沿該主機 Pacific；producer 各自的 aware clock 另核，不由字串補成跨時區接受。

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
| Formal input | 新immutable終態定向PASS，待自然 | 10/21 21:25 result2（Taipei10/22）；10/22晚尚未到 | 未接受 | ready/compatible=0 | 未成立 | 拒絕 | 有效runtime／Owner來源包 |
| PIT preopen／sidecar | config binding拒絕，根因待精確runtime比較 | 10/21 16:00／18:00 result2（Taipei10/22） | candidate-only | target10/22無capture | 不能用10/20 archive代替 | formal/OOS=false | config／cutoff前自然capture |
| Paper EOD／Portfolio | EOD gate已觀測；Portfolio待新run | EOD blocked；Portfolio上一run10/21 17:25 result2 | 真帳戶／cash／mark未接受 | 舊snapshot非當日 | 缺同日合法輸入 | 無ledger成功讀回 | Owner帳戶策略資金包／Quick |
| Forward outcomes | 價源lineage尚需精確交付 | 真自然研究更新但blocked | research-only | 缺價與pending分列 | 成熟與可得性未全證 | 不授ML／績效 | 官方價源／自然horizon |
| Calibration／BankTaiwan | 已核新依賴拒絕；child細因待核 | result1／2 | shadow-only | 合格samples未建立 | 不借舊source clock | 未就緒 | Raw PIT／snapshot |
| 月營收 | 既有研究工程保持；單位契約歧義收斂 | 非獨立每日正式Task成功證據 | 官方來源／OGL已核；金額單位unknown | 本批1,981列；完整歷史月0 | 歷史發布／修訂證據0 | YoY限定研究；正式用途blocked | 官方unit proof／完整歷史／PIT |
| Official market events | 待同次children／consumer核驗 | 10/22 result0，新wrapper原件已存 | 各child獨立 | 未外推 | 未外推 | 待精確讀回 | child資格 |
| Decision evidence | 10/22具名receipt已存 | result0／passed | 不由capture授予 | 該receipt scope | 未外推 | 待exact consumer | 來源資格 |
| Copilot | 規則lane | result0／passed_rule_only | 模型資格未成立 | 不外推 | 不外推 | inference未跑 | 合格ML資料／模型 |
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

所有Python由root串行使用Windows Job：8 GiB committed／12 processes／kill-on-close／workspace mutex；鎖忙時不啟動child，原拒絕保存；正常完成的Job均自然剩餘0、handles關閉／mutex釋放。其他Track曾推進HEAD，版本precheck拒絕另保留，重取當前HEAD與pins後才執行。

自然CLI manifest SHA `1d6c84b522b4d9af0670a7225e2f79b80c327f25c8e78dc9111898887268c939`，原CLI輸出 `natural_audit_cli_stdout.json`：HEALTHY2／DEGRADED2／EXECUTION_FAILED13／UNKNOWN4。Freshness application=DEGRADED／observability=HEALTHY，Evidence application=BLOCKED_SOURCE／observability=HEALTHY，ML raw observability=HEALTHY但來源blocked。Paper EOD原1,970 blockers仍超既有128上限，保留receipt_blockers_invalid，不截短原件或放寬reader；人工語義觀測與六軌CLI結果分開。

### 尚存工程與下一步

- BankTaiwan本run的child stdout為20,312,574 bytes，超既有16,777,216上限，`child_payload_source=child_stdout_artifact_size_limit_exceeded`、terminal readback失敗；不能把child exit2一概當金融缺件。需要有界、同invocation、typed immutable控制面，保留原大型診斷，不提高上限。
- Forward本run172筆為95 ready／56 pending／21 missing price。既有metadata有event lineage、cutoff與calendar hash，沒有實際使用價格／benchmark列的revision／custody／hash；工程須在實際讀取邊界保存來源觀測，再交consumer qualification。不能事後替本run補來源或以動態DB hash冒充PIT。
- Formal／PIT的舊配置、實際wrapper binding與新自然結果須分開；當前有效資料用途批准仍不可代理。新的Formal終態只影響下一run，不補舊收據。
- Task設定未有差異；16項沿既有PT72H與IgnoreNew，Bank upstream wait＋child＋flush恰為5h，是timeout政策檢視點，未觀測到本run因該limit而timeout，不在此改設定或默默放寬期限。

官方來源新有界查詢仍未建立API金額unit proof。[政府資料集18420](https://data.gov.tw/dataset/18420)有14欄、來源與OGL資訊，未提供可綁定此API金額的單位；另找到的[舊TWSE申報說明](https://www.twse.com.tw/staticFiles/news/event/event_download_201501141045_02.pdf)是申報系統文件，並非這兩個OpenAPI endpoint／parser／field mapping的外部固定unit artifact。未存原bytes／typed proof，也未升格單位或重抓已耗盡的歷史入口。

## 可用範圍、自然等待與 Owner 最小決策

可安全交付：原件／新自然終態的唯讀診斷，以及已通既有契約的限定研究範圍。月營收1,975列YoY與6 unknown沿原百分率研究reader；金額單位未知，不標TWD。無正式Scoring／Backtest／Paper／Forward／ML資格升格。歷史SQLite已有2014起月營收值與部分舊PIT日期，與本次全用途archive的完整歷史月份0是不同來源／證據範圍，不能混算。

待自然累積：修復後Quick與下游同次收據、PIT cutoff前新capture、Forward官方交易日horizon及合格樣本；不能手動執行冒稱自然恢復。

Owner不可代理決策最小包：

1. **正式runtime與來源用途版本**：選定有效日期／版本及其外部接受reference／SHA，具名 clock／universe／owner acceptance、Source／Revision／Custody與consumer用途。當前binding固定09/09候選配置、仍帶D來源根，不能直接延長日期或沿用批准授新來源。
2. **Paper正式輸入**：選定真帳戶、策略policy及其版本、合法cash／mark與官方日曆／Ledger來源。研究500,000 TWD或9/7舊cash不是正式來源。
3. **Weekly monthly_statement**：對原具名partial child作人工review或提供合格替代版本；不重試已耗盡入口冒稱成功。

官方金額單位、完整歷史報表及當時發布／修訂證據是外部資料條件，不可由Owner口頭接受替代。已授全用途開發範圍不再重批。

Track C 的 ML Data Readiness 與 Track A 的唯讀研究展示見 [共用交付契約](../03_data/BALDR_TRACK_B_DATA_READINESS_CONTRACT.md)。

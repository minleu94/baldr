# 下一次Task唯讀驗收與原24UX已知工程差異（2026-10-07）

此份是對原plan最新已知差異的有界追加；沿用B01–B15、M/P/R及A01–A03收據，不全面重audit、不重跑已接受底座、不塞Notes新GUI／週月／更多indicator／外部renderer選配。固定base d89fad0f8057ec7ccf8af15d74a7d16986754ad5，tracked clean。9Stage仍1done/8partial、24UX仍2done/22partial；七有限closed UX03/04/05/06/09/15/17、F1 18.6219658%及Journey8.109s原例外不改。

## Task確切時間、現有hook與真值界線

原 baldr-recommendation-calibration-learning-daily 下次NextRunTime＝2026-10-07T05:45:00-07:00，Windows Pacific Standard Time（目前DST offset−07；UI顯示−08是時區通用label，不是本次offset），UTC＝2026-10-07T12:45:00Z，台北＝2026-10-07T20:45:00+08:00。trigger enabled、state Ready；last_run是10/06 05:45:01、last_result1，屬此次enable之前的舊run，不冒稱新model失败或下次成功。NextRunTime不是完成時間，須等原run terminal；10500秒source wait與原pipeline timeouts不改。

configuration：D:/Min/Python/Project/FA_Data/personal/recommendation_h20/activation.json，revision1 enabled=true scope personal.default，raw SHA256 769a40ba527c0c6d845349ef4f1002f9845ff6f68f5c3695800aee863c62ad3f。model/candidate rec-cal-3f8b2c276ef316e28de3806d；contract sha256:185a2378794a01c4f627d64b158e2fd50c6f41700af0ccbb3e31cfc60aa17053，fit raw sha256:f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1。

原cmd在該檔exists時傳 --personal-h20-activation-config；pipeline._learning_child_arguments沿原same-run pins傳learning child；learning main:1897–1907在entry capture／natural fit之前呼hook。來源root與所有原guard保留。Process/User/Machine五項根路徑env override全None（DATA_ROOT/OUTPUT_ROOT/RECOMMENDATION_LEARNING_OUTPUT_ROOT/CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT/PERSONAL_H20_ACTIVATION_CONFIG，原值只讀落地）；原Task使用archi/Interactive/Limited、action、cwd、trigger/settings已逐欄比before相同。没有啟Task／重跑raw鏈／新automation。

重要：hook仍在原pipeline的recommendation_learning child，child前若technical/snapshot或exact current-cycle dependency blocked，模型hook也可能未到達；配置enabled不是保證下次producer已成功。原global/formal root-conflict可令Task最後return1/2，即使personal H20 success也不把全Task變綠。readonly驗收须分別報Task整鏈、personal model effect與natural资格。

## 下次run只讀驗收路徑／identity

1. 發現入口（只能用來找到新run，不直接作成功證據）：
   - D:/Min/Python/Project/FA_Data_Shadow/scheduled/recommendation_calibration_learning/latest_status.json
   - 同root的20261007_pipeline.log（原stdout/stderr追加，找到對應newrun，不把tail/舊JSON當exact收據）
   - latest.status的run_id及terminal_receipt_path→同root/runs/<exact-run-id>/receipt.json；核原terminal raw SHA與run_id、decision_date、同一steps/current_observed_source_cycle_wait。
   - 原source raw status D:/Min/Python/Project/FA_Data/output/scheduled/ml_raw_pit_refresh/latest_status.json及selected cycle terminal只是發現；沿terminal path/SHA核exact completed cycle，不拿10/06舊completed當10/07成功。
2. personal保存入口：同已選root/h20_product_reference.json→h20_daily_receipts/<rawSHA>.json→h20_predictions/<retry-key>.json。使用public read_personal_h20_product_for_stock、read_personal_h20_daily_receipt／read_personal_h20_prediction；predicate factory禁止predictor，新程序只讀，不fit／不重跑source。ref/current config revision必一致；manifest原bytes SHA、candidate/contract、full symbols/count／每列sample_id/prediction_id/source_row_sha與raw pin都核。
3. 應核new identity：本次scheduledrun真正選取的raw_run_id／cycle_id、cycle_terminal path/rawSHA/source_date、snapshot DB/receipt rawSHA、source_context envelope rawSHA、Task run_id與原source dependency對應。適用交易日需新同日source_date與decisiondate，expected feature期依原source verifier／calendar而非自猜；缺新cycle就是pending，不重放原10/06。
4. modeldecision／aware observed_at必屬該次真觀測；manifest cohort等於exact raw terminal全部current_symbols（目前原cohort／API1–50，不是全市場）。config可保持revision1，source/capture必须新，不以同配置或旧pointer a2cad4b3...當新run。Model artifact/fit仍原pins，不重訓；原prediction bytes保留，重試不增加同cycle/model/stock樣本。
5. outcomes：新同日input capture／outcome availability/decision/cycle/source/features exactjoin成功才形成自然樣本；20session未成熟pending不是失敗。原十笔decision10/07/source10/06/features10/05仍pending，不可接10/06entry补成熟。personal private成功與formal/global blocked可同時為真。
6. readonly命令：Get-ScheduledTaskInfo -TaskName 'baldr-recommendation-calibration-learning-daily' 只核LastRunTime/LastTaskResult；再讀上述immutable anchors。不要Start-ScheduledTask／cmd重跑／改registry/clock/source/guard，不設automation。父層到時讀結果即可。

## H20實際用途與剩餘接線

目前已真：daily public ingress→原H20 gross head→10原預測create-only保存→fullscope manifest pin／productref→個股摘要背景公開讀回。新程序predictor禁止，1225原2204bp／三日期確實顯示。這是已啟用的研究推論，不是只畫合成值。

目前未做：把此H20 candidate接到RecommendationService原推薦的生成／排名／機率。檢索全app/ui/scheduled references，consumer只在個股summary與daily保存；RecommendationService仍用原calibration_consumer的概率／排名契約，H20不在此條路。原 canonical RecommendationResult排序／勝率／after-cost沒有被換成gross。

日常選股的必要增量：
- 提供已驗daily manifest完整cohort的H20 research row/readmodel，保存original sample/prediction/raw source pins；依gross整數bp排序，unknown不當0、tie固定股碼、全分母／來源clock与scope可見，1–50原scope不得冒称全市場。
- 在既有推薦／研究工作區提供明示H20研究來源列表（保持九workspace IDs及原saved canonical列表），列表→同stock／原prediction identity下鑽→返回同列表，current／saved/source-change/stale回呼／取消有負例。不把H20值寫回 canonical probability或改舊rank；若要整合原名單必须先有完整同source/date/cohort binding，不依單股碼/date猜merge。
- Daily entry／outcome原public verifier已经有H20 adapter，但当前hook六欄request未注入natural_outcome，Task未自動把新entry/outcome原pins餵給该adapter。這是caller工程缺口，與自然成熟時間分開；接線後缺exactmatching或未成熟继續pending，不能借別cycle樣本優化／訓練。

尚需分配具體列表/consumer ownership才實作；本次只界定必要增量，不擅改RecommendationService公式／sharedDTO。真正drift/adoption或fit-control仍按原port／policy權限，不把B14 synthetic stop當此personal真model controller。configuration disabled CAS是已驗有限回滾，沒有即時殺訓練程序宣稱。

## 原24UX的目前已知非自然工程差異（有限核對）

| 原UX | 本次已知必要工程／保持原接受 |
|---|---|
| 01 基線 | done保留，無新已知實作缺口；更新本固定base。 |
| 02 狀態語言 | done保留；新增gross列表要明示毛報酬、不是勝率。 |
| 03 導覽 | 七有限closed保留；新增H20列表→原prediction下鑽／返回是新scope。 |
| 04 每日名單 | 原named名單closed保留；H20尚無完整cohort列表與日常排序。 |
| 05 篩選摘要 | 原兩MAclosed保留；BBv3新增第三條件filter／理由/反證/缺件與H20列表分域尚缺。 |
| 06 個股摘要 | 原closed保留；H20原值增量卡已真用；H20列表選股所需exact context尚未接。 |
| 07 圖表可行性 | 原native default／有限外連沿用，沒有本次已知必修；不塞LWC prototype選配。 |
| 08 同源互動圖 | B05／原保存marker/键盘/精確表已受驗；無新增必修，不展週月/更多指標。 |
| 09 訊號歷史 | 原finiteclosed索引／分頁／版本讀回保留，未發現新缺陷，不再重audit。 |
| 10 多策略家族 | BB上軌v3 single-batch已存，parent全宣告母體三方法／列表family正確label尚缺；compression不假done。 |
| 11 規則結果卡 | B07 typed保存→freshprocess、R01 bounded legacy/Registry接受沿用，無新必修。 |
| 12 統一歷史 | R01完整64/256MiB同份bytes/cancel/identity接受沿用，無新必修。 |
| 13 市場觀察 | B03/B04市場/理由提醒已受驗，無本次新必修；不擴未知真提醒部署。 |
| 14 三帳／工具 | B06/B08–10/P2 selected producer與personal caller原scope接受保留，真migration不是工程缺陷。 |
| 15 文件／真人 | 本增量Task/用途/剩餘必要接線文件同步；Native/3–5真人分開不假過。 |
| 16 資料能力 | 八族catalog／A01字段契约接受；v3 parent/日接受consumer還需同version完整母體；未開家族不擴。 |
| 17 性能 | F1/Journey原例外保留；新H20/BB列表新增query/cancel/resource按UX24做增量驗收，不全重profiling。 |
| 18 共用特徵方法 | A01有限上軌源→snapshot已真；parent及UI third-selector/labels仍硬綁兩MA，為必要接線。 |
| 19 快照／容量 | 原A01atomic/immutability接受；parent/daily runtime/acceptance policy版號傳遞待接，保20/200GiB與原上限。 |
| 20 全母體自然收集 | BBP01完整具名母體v3；中央owner/runtime/policy明示版，不能截斷。下一Task只讀驗真新cohort，不造自然clock。 |
| 21 label／自然結果 | existing H20 public outcome adapter已存在；Task的新原entry/outcome pins→adapter自動caller未接。20session本身是自然待驗不是工程gate。 |
| 22 ML候選 | A02原H20可信artifact/lineage實際predict已用；到日常選股仍缺research list/ranking reader/UI，不需新trainer。 |
| 23 shadow/回退 | 原B14纯port/synthetic工程接受保留；个人daily啟用/保存/讀回及disabled CAS已真；原模型自然反馈caller尚缺，不冒真drift/control閉環。 |
| 24 新增整鏈 | 原B15稳定519P/2S与新H20 60/WB85/mypy845原收據重用；BBparent/UI/日接受与H20列表新增完成後只驗其diff旅程/容量/资源。 |

## BBP01立刻派工／中央保留

四檔派工full prompt及base/blob：output/plans/baldr_bbp01_parent_v3_dispatch_20261007.md、output/qa/baldr_real_model_intake_20261006/bbp01_dispatch_pins.json。父層即可新Sol lane，初期最多1Luna。中央本次只讀四檔，不共編。

已查明後續日接受exact central檔：rule_research_daily_owner.py（strict runtime parser及254producer caller）、rule_research_daily_runtime_adapter.py（segment/request傳版）、rule_research_observation_acceptance.py（82固定v2 method SHA）。BBP01 parent四檔不含此三檔，第一包无需等日接受才交；中央收到 frozen API後沿同descriptor接，旧v2 config/hash不變。

BB列表後續最小UI範圍可另鎖 daily_market_research_view.py＋新BB UI tests/QA。已知精確點：two-MA controls260/265，restore allowlist1205，方法summary1649非MA20一律標MA60；按savedmanifest版顯示BB checkbox/label及why-not/返回，v2不顯BB，不能只改文字當第三方法可用。

本次沒有production/tests修改或runtime重測，僅讀碼／Task/config readonly及文件。原未知资格／自然結果／七有限closed/性能例外／正式資料限制不變。

# B03–B12 第二波中央整合收據（2026-10-06）

本文件只保存整合證據；唯一路線仍是 output/plans/baldr_product_experience_plan_20261004.md（Danny Quant），目前狀態依 PROJECT_SNAPSHOT，操作依完整 Manual。固定最初基準 a42b2cb9；第二波 lane base ba4e9e59，B03 Update／B12 base175d9c50。中央 B10 commit05329f94，B12原024e0194／review修740fd64c。所有交付只local，未push/mainmerge。

## 接受範圍與重用證據

| 包 | 原 lane／中央 | 有界接受與證據 |
|---|---|---|
| B03 Update／Runtime | c9ea5787 →11a56284 | 原DTO影響／未知日期／明細收合；36 focused pass、mypy2。Manual就地更新4.1／11／11.1，原callbacks保留。 |
| B04 | d9e60090 →54a72f84（第一提交19294338仍保留） | 保存來源exact identity與私人Watchlist理由／查看狀態CAS／新程序讀回；97pass，4mypy。正式個人啟用未授。 |
| B05 | d9228ae8→20f9b029，a6852cb2→22c7740e（初491fb26b保留） | 原保存紀錄readonlyadapter→原列custodypins→markers→view／新程序；74pass/11deselected，缺account_kind修8pass/20deselected。main reader尚未注入，舊naive writer保持clock_unknown，不造actual。 |
| B06 | d313b2b2→200cc61a | 三帳／同列估值／缺件unknown／配置注入guard；55pass，mypy2。原result-r1 node repo隔離fixture1pass，Temp失敗為no-follow ancestor sandbox診斷，非產品main bug。 |
| B10 core／backup | 175d9c50／204aae05 | 私人review／query-only市場refs／notes backup create-only；core28，notes+review42pass/1權限skip。真私人啟用未授。 |
| B10 composition／history | 05329f94 | 個人Review週報reader／history、readiness config副本、缺table不借市場、source_lineage unknown；28 affected pass36.41s，mypy3/compile5/quant/diffpass。 |
| B12 | f30b7cc9→024e0194，dce2f909→740fd64c | typed calendar/terminal/segments＋isolated subprocess、deepUnicode snapshot I/O；103 unique synthetic原案例。review修新增runtime39與terminal2組分列，不累加重測。mypy6，canonical/schema/hash/cutoff與角色reserve保留。 |

B12 獨立 reviewer 只讀固定HEAD/base/manifest，focused102＋delta9（8 overlap／1新增）＝103 unique，兩XML hashes符合。發現preflight有效JSON＋非零exit仍可execute；原lane修明示exact int非bool/0，成功terminal也去掉缺值default0。修正後adapter blob abffa4108208f193344821a18318c525003a0435與中央相等；中央六檔targeted mypy成功，不重跑103。calendar/terminal原bytes custody由可信caller先核，不能自行填pins／verified取得資格。

B10 XML output/qa/b10_evidence_history_union_20261006.xml SHA256 7c4aed19534a795bed556dca11faf0c0479fb385bf0af6a3fc4bebec3737cb4a。B12原focused SHA532c39bbe7cb8fb1d6b5e3a4c238494ff77087373ac1e3393ed87763b14f63b7、delta af915157535b0e76b37c12098c6a382dfa92da0c6eddc0a3f3a0213bfa8fa809；review preflight cd7597b1fbbd766bbe36c05a25553ad5f303ed8ed6f350dd8f1319192be5d7f0、terminal b9d1f5c94b348a74b0b924f7c292215d98c94a146e18ac36ac737ea26f1b00f7。raw output不stage，具名lane QA保留exact命令／限制。

## 原 plan prefix 保留與剩餘

本輪只append2655bytes：before243012 SHA c4126a56cbe6a1c28b541222f11616af26b18a7149ed29ac8d402a53e729fc85；after245667 SHA05d2e17be8457dc0c38037ed58bdd94402879e25d2f7fe5c093c1065b7e2f1f6。逐byte prefix相等，ignored receipt output/qa/baldr_second_wave_plan_append_20261006.json。原9stage1done/8partial/0pending、24UX2done/22partial/0pending、七有限closed及F1/Journey性能例外保留，不新增整項done。

B07／B13仍lane進行中，B11／B14待定版派工；B09 per-I/O custody依賴採入曾遭automatic approval review拒絕；使用者直接批准仍適用且不過時修正合併，原lane正核對後同完整依賴重試，未確認完成，禁止extract或轉移中央繞過。B05main、B09同帳composition與B15穩定UI mandatory union仍未完成。首波Workbench85／validator25+4skip／mypy823只覆蓋首波固定樹，不能代替這一輪。自然累積不作工程gate，formal/PIT/training/account/clock unknown不造。

## 回滾

本輪文件僅Manual/Snapshot/Architecture/Index/scheduledREADME/QA，回復具名localcommit前核他人dirty；B10程式回復05329f94，保留私人資料與歷史。B12回復740fd64c再024e0194並同步caller；任何原source／segment／partial／receipt均留存。不實際revert、不cleanup、不降低guard。正式DB／私人migration／Task／ACL／交易／foregroundNative／fit均未執行。

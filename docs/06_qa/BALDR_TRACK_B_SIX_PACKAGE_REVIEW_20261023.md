# Track B 六包交付獨立複核（2026-10-23 Taipei／10-22 Pacific）

基線 `ecd69465`，承接原R7 `78193d89`。本次只核查與補修六個工作包，不授Formal/Paper來源、不重跑producer或自然排程、不push。原Gemini收據與R7證據保持。

## 狀態與實質發現

WP1新增09/06原Git證據可接受第七筆，但原交接文字寫錯SHA，真正原件SHA為 `101d9593767e895c338358cb3349bf6674e85de3e159eb0c02581daaa46fe1b1`；剩81筆仍缺證。補有效custody tier與caller拒絕集合，不以pin越過明示限制。

WP2的固定10/19原件確有遷移證據；原例外卻可由新收據借用，且沒有驗D/F完整bytes/SHA並永久快取路徑可信。修正為固定run/terminal、封閉mapping、逐條原件/當前版本重驗；5/6 partial維持。

WP3原實作把任意metadata時間當證據、結果價可能沿用baseline，reader會從自帶cutoff重建政策。修正以原capture context研究時鐘、事件canonical hash及本輪上限核對，實際建立的每事件政策登記供讀回；不由payload自授cutoff。Capture context仍research_only，並不授natural/preopen或全金融PIT。

WP4的8132差異不能標thousand_twd；不同出表日期不能證明曾官方更正。WP5原件只有十批摘要與樣本，需真reader重建9423逐issuer/sourceversion矩陣；時間及百分率授權不得跨來源外推。

## 精確 repository output 導航登記權威範圍

本表是既有output掛載點中的精確檔案導航，並非冷封存批次，不授金融資格或內容驗真。原37個連結出現位置對應35個唯一文件/目標pair；原重複連結保持。不全面豁免output：未列文件、其他來源文件、掛載漂移、子層link或缺件均拒絕。固定掛載目標為 `F:/Min/Python/Project/BaldrStorage/repo-output`。

| 精確來源檔案 | 引用文件 | 類型 |
|---|---|---|
| `output/tasks/baldr-post-completion-execution/TPEX_20261019_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-143/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-02/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-02/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-03/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-05/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-05/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-07/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-08/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-08/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-08/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-09/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-09/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-09/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-10/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-10/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-10/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-11/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-11/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-11/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-12/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-12/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-12/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-13/KNOWN_ISSUES.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-13/Launch-Baldr.cmd` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-13/TRIAL_GUIDE.md` | `docs/00_core/PROJECT_SNAPSHOT.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-117/TRIAL_GUIDE.md` | `docs/07_guides/APPLICATION_MANUAL.md` | metadata-only historical navigation |
| `output/trial/Baldr-Theme-Research-03/TRIAL_GUIDE.md` | `docs/07_guides/APPLICATION_MANUAL.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-117/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-120/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-121/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-82/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-90/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-94/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |
| `output/trial/Baldr-Daily-Research-95/TRIAL_GUIDE.md` | `docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md` | metadata-only historical navigation |

## 驗證與交接

QA005：236 passed、3 skipped；7個受改production module mypy通過、15檔編譯通過，9份範圍文件檢查通過。Job `single_owned_qa_7a779e91cc2d449cbeeac6be82a9fa5f`，receipt SHA `86fe265d1b681beb667300ec067971ce63bc91faf633cd8a4348ebb1387673b3`，exit0、remaining0、無forced cleanup。保留QA001..003失敗原貌；QA004修正整合測試建構後5passed。3個skip為環境／truthcase條件，不當PASS。全庫文件檢查仍有本範圍外既存錯誤，不宣稱全庫通過。所有未提交UI文件保持；不宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`。

本次證據根 `output/tasks/baldr-track-b-six-package-review-20261023/`，下列SHA是實際file bytes，不是來源資格簽章。

| 原件 | SHA256 | 範圍 |
|---|---|---|
| monthly_revenue_issuer_version_matrix_r8.json | `027665b3e349180e68fe0c51a1f7a1314c06fc02c3a727cf30df9d4ada678fa6` | 10批、9423列；五類時鐘、逐列來源與revision；不授歷史PIT |
| twse_6443_revision_independent_review_r8.json | `3b29e3be97324aae6b6a3c6c8708ba2392c0a76d3573a48d9e445c9c1b8db416` | 8132差異，currency unknown、修訂順序未解 |
| legacy_weekly_navigation_independent_readback_r8.json | `82f63d960b23df31102e95014fe1430aecf729b3b2626df23f1e0697133658ec` | 真88筆讀回：7有效、81拒絕，DB未變；Weekly partial；37處/35pair導航 |

## 七維判定與剩餘工作

| 線路 | Engineering | Natural execution | Source qualification | Coverage | PIT | Consumer | External dependencies |
|---|---|---|---|---|---|---|---|
| Legacy | 本次限制集合與effective tier修復已驗 | 不適用 | 7筆custody成立 | 7/88 qualified custody，81缺 | 未授 | 7筆限定唯讀，81拒絕 | 獨立原件／原hash pins |
| Weekly | 固定遷移範圍修復已驗 | 本輪未重跑 | fixed core核驗，monthly partial | monthly 5/6 | 未授 | human review required | sii F26完整原件與審核 |
| Forward | 每事件政策、角色、讀回修復已驗 | 修復後待自然run | 仍需真用途接受及availability | 不由fixture推全歷史 | 條件未滿拒絕 | research context限定；training false | 合格來源與自然horizon |
| 月營收 | reader重播與逐列矩陣已驗 | 本次離線核對 | HTML尺度成立，currency unknown | 四月雙市場8HTML；另2OpenAPI | historical false | 既有09百分率研究授權不外推 | 幣別、公告時點、6443修訂 |
| 文件導航 | 37處精確登記與拒絕案例已驗 | 不適用 | metadata only | 35來源文件／目標pair | 不適用 | scoped check通過 | 其餘整庫連結另列 |
| Formal/Paper | 本次未啟用候選 | 未證完整自然成功 | Owner尚未選定 | 未選定 | 不接受 | fail closed | runtime/source-purpose、真帳戶及cash/mark/Ledger |

可交給後繼工程者的取證工作：逐筆尋找81份Legacy獨立原件；取得sii F26完整原件並沿原controller規則驗證；找6443官方更正公告及幣別欄位定義；擴充官方歷史公告時間清冊。以上可直接做唯讀搜尋與候選接線，取得官方證據也不能偽造歷史可用時間。Formal/Paper可準備帶路徑、SHA、用途與差異的最小批准包，Owner尚未選定時不能自行指定正式身份。自然排程及horizon另待真實產生，不能人工重播冒充。

Track A/C機器契約位於本次證據根的`readonly_research_display_contract_r8.json`與`ml_data_readiness_contract_r8.json`；只交付可驗欄位及拒絕界線，不啟動訓練或改UI。

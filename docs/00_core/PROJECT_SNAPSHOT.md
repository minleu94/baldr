# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-17（使用者時區）。本頁只回答現在能用什麼、下一次交什麼、哪些仍受限制。逐輪過程見[具名 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)；重規劃前全文見[歷史快照](../09_archive/PROJECT_SNAPSHOT_20261015_BEFORE_DELIVERY_REPLAN.md)。

## 現在有哪些入口

**目前指定本機試用候選為日常研究119（`332ff9292543`）**，入口是 [Launch-Baldr.cmd](../../output/trial/Baldr-Daily-Research-119/Launch-Baldr.cmd)。先看[試用版指南](../07_guides/TRIAL_VERSION_GUIDE.md)，版本、原件與限制由包內收據固定。119沿118日常流程，新增原P07第二階段「四均線多頭排列（研究）」正常單股執行→保存→原規則／結果→返回→新程序；來源／EXE同輸入訊號、撮合及金融輸出一致。這不擴大V1或授策略有效性，詳[119 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment119-ma-alignment)。118同源個股修正及8933／2506原Windows Qt證據仍見[118 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment118-price-stock-workspace)，未改旅程不全數重跑。

115、112、109、71、66及更早候選與各自狀態保留，不自動匯入個人內容。66原回報及指南D勘誤沿原身分保留；後續修復不冒充新版真人接受。116沒有重跑未改的四條全部旅程：單股雙策略保存／比較沿用112具名證據，價格選股、收藏與舊推薦回訪按109及相應原QA判讀。

| 使用流程 | 已知可用範圍 | 還要處理什麼 |
|---|---|---|
| 看市場、查個股 | 市場狀態與四股一般價格／技術研究；四股末日漲跌方向另有同股同日核對 | 一般個股仍是四股隔離價庫，截至2026-09-23；舊列缺方向維持未提供。 |
| 設條件、選股、保存研究 | 另一份2026-10-16來源宣告1,989、處理1,951、排除38；可依MA條件選股、主個股頁看原價量、同源比較、收藏及重開 | 5筆價格UNKNOWN、名錄用途與來源clock未接受；不能稱正式真N或歷史PIT。 |
| 觀察清單與持倉回訪 | 持倉位於四卡下方；唯一精確代號／名稱互補，未綁來源部位可回一般個股價量重載 | 真私人帳與真人手勢待驗；保存來源部位沿原exact守衛，Paper外部根未在試用配置。 |
| 單股回測、保存與歷史 | 兩個原1.0.0基本策略可保存、核原規則、對照條件、開明細返回；窄視窗以按鈕切換設定／結果並捲動 | 原六配對run尚未定位；SOP／Baseline FAIL及未做Walk-forward不改判。批次原列可回訪，116拒絕未具資格的通用績效比較。 |

原 V1 四條流程與出口維持[計畫 §0.3](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)。以上是已交付及回報狀態，不是全部 P00–P14 或 G0–G4 接受。

## 目前工程狀態與限制

**Increment120施工中，未替換119。** 已重現原baseline／穩健／暴衝計分策略用未來指標回填過去分數／訊號的缺陷；舊版本與保存件保留，不供因果策略結論。1.1.0另立保留未知的方法，正驗正常保存／重開及同版出口，未完成項不記PASS。2317原隔離行情2025-07-30四價全缺、量0，原因未核定；不補價、不稱停牌，其他有效區段應能繼續研究。證據見[120 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment120-causal-score-input)。

119固定來源`332ff92925433baee5f6ea9f7c4dc76a206c9d64`，EXE SHA-256 `272f07ed847a74da24645a904f3091236983f5d6ed4fa48e2fdbbf3f0b7189a6`，交付SHA `f83cc8d528f1b33c4713966b00045b4f48a62f45cbea4363826971d2ca6d11a5`。新四均線用2317／2025-01-02至2026-09-23驗419列、8個進場意圖、6組完成配對；來源Main38416→2744、固定EXE6808→34096精確讀回。320項受改／共同回歸、取消與打包缺件、compile、validator25/0/4、mypy1050與精度守衛有具名結果；歷史測試失敗保留。它只交正常單股研究，其他模式／歷史PIT／來源／成本權威／有效績效／Native／真人仍待。三個原研究策略與完整P07不能按數量合計完成。

118固定來源`1444b5d298d676cedd0147ac342eaf77ff141a18`，EXE SHA-256 `1ee22609eb6beeefce56e977adaf1ad101d4365dfb07b35a13ac9fa2278298df`，交付SHA `71e127853fd7731ba9f5f40f55224c4f5399932321b8169b74b8fb9d50417d51`。來源Main及固定EXE的同源個股、原頁返回、收藏及fresh均有定向收據；112項受改／共同UI防線通過。Windows Qt功能不授Native／真人／完整Gate；沿117的五項基本面與116保存修正，不重驗未改旅程。

115已納入跨視窗TabOrder、Qt model自有連線清理及pandas相容性修復；原受影響回歸、共同UI防線與13個隔離MainWindow旅程見[啟動警告修復QA](../06_qa/BALDR_STARTUP_WARNINGS_FIX_20261015.md)。115該次同版EXE父／新程序未收到Qt警告；公司名冊缺來源憑證的提示仍保留。

116已修舊回測因Decimal附註而降級CSV、讀回再失精度的缺陷；33個受影響測試、compile、mypy／精度守衛與正常Python Main四筆保存→新程序通過，同輪固定EXE另驗高精度原值新保存及重開。原producer的float DTO按原位元身分核，不授完整精度；舊CSV／SQLite摘要不遷移。前段來源階段、失敗與補證原樣見[Increment116 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment116-legacy-parquet-precision)。

**116固定來源為 `1cf80e32b4c229177152d364fce06ec4e63ec948`，EXE SHA-256為 `ba38c46e72a880b7c1016210c748c826c026a18ffec8631c7a1cb14223830ca1`。** 後續工作樹不改該EXE。18份固定狀態由109核SHA另複製，詳[交付收據](../../output/trial/Baldr-Daily-Research-116/DELIVERY_RECEIPT.json)；程式碼包含某家族不表示其金融或完整產品資格已接受。

原66候選的交付歷史：依[原計畫 §0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)，第一列「日常研究修正版」已形成固定可試用候選。受改測試、共同 UI 防線、兩筆隔離持倉、來源與 EXE 的正常 Main／新程序及同版檢查已限定通過；EXE SHA-256 為 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`。交付收據最初記錄 SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2`，目前檔案 SHA-256 為 `16bb4f511e5ecb21dff6667a5a38fa7aa73d298bf951ea69c0ce85b42e128eb1`；原因未裁決，兩者不混稱同一位元原件，詳[Increment67 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment67p08-推薦回放通用比較的金融判讀阻斷)。這只關閉本列工程交付出口，真人試用及完整產品 Gate 仍待。

| 接續順序 | 使用者會拿到的成果 | 目前位置 |
|---|---|---|
| 1. 日常研究修正版 | 四流程及受改缺陷的固定候選 | 118已交同源個股／返回／收藏／fresh修正；真人與不同DPI待試，不重跑未改流程。 |
| 2. 有來源的基本面研究 | 正常個股頁的當期／前期與保存重開 | [117基本面預覽](../../output/trial/Baldr-Daily-Research-117/TRIAL_GUIDE.md)已交固定`8109709a0721`；2330／2026-H1五欄限定目前研究接受，來源版與EXE的Qt Main／fresh通過。原生螢幕命中FAIL、其他公司、前期及歷史PIT仍保留。 |
| 3. 持倉與研究情境 | 同帳本現金／行情／Health的初次情境、保存及返回 | 隔離合成來源已有定向證據；缺真人策略Paper帳與同日原件，不以手動成本造NAV。 |
| 4. 可比較策略研究 | 原規則、獨立結果、保存／比較／明細返回 | 119另交四均線正常單股研究；116原列回訪、精度及拒錯沿原QA。來源、幣別、成本權威、歷史PIT及完整雙策略績效仍各自待。 |
| 5. 結果追蹤與其餘範圍 | 到期、品質與執行原因分列 | 舊推薦5／10／20日受限結果可回訪，60日待成熟；P12自然原件仍研究用途，正式時序與來源修訂限制未解除。 |

外部缺件只隔離受影響用途：TPEx 年度日曆授權不等於 TPEx 法人 OpenAPI 的授權狀態；MOPS 文件 partial／缺 EOF、月營收與 TWSE 舊 GET 額度、單位版本、歷史 PIT 和完整真 N 繼續各自追蹤。首次成功保存後的合格新快照按已決定的台北小時政策供前瞻研究；不得倒填歷史可得性。原 P01 效能 FAIL、原 Native FAIL、Paper／Forward 未成熟與已停用 maintainer 仍保留，詳[原 QA](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)、[資料政策 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)及[排程指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

## 產品與系統入口

- **進度與交付**：[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保留；不以 Increment 或測試數量計算完成率。
- **產品方向與來源優先序**：[Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)；正式 Gate 依賴見[六個月工程路線](ROADMAP_6M_ENGINEERING.md)，不以本輪交付排序改寫 Gate。
- **實際操作**：[APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)；首次設定看[快速開始](../07_guides/QUICK_START.md)，移機看[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。
- **現行與目標架構**：[system_architecture](../01_architecture/system_architecture.md)／[current 分冊](../01_architecture/current/README.md)；[FINAL](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標設計，不作已實作證據。
- **主程式與資料**：`ui_qt/main.py`，九個頂層工作區；資料位置由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `DATA_ROOT=D:/Min/Python/Project/FA_Data`，不能以 repo 相對路徑推定正式資料位置。
- **L2 產業鏈與題材萃取對應（獨立模組）**：[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 提供季度／手動之 25 條產業鏈、L2 題材與股票對應三檔建置（未介入既有選股／UI 流程）；規格與檔案欄位見[設計文件](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)，驗證收據見[QA](../06_qa/INDUSTRY_THEME_MAP_STANDALONE_QA_20261016.md)。

## 重要限制

- 正式資料寫入、全量回補、正式 Task／maintainer 變更、push、發布與交易沒有新增授權；私人資產與其他 owner 變更受保護。
- 金融精度、決策當下可得性、來源用途、原 FAIL 與各 Gate 門檻維持；缺值與未知不能補零。
- Historical replay、readiness、dry-run、shadow、Paper、合成資料或測試通過，均不能代替真來源、有效績效、真人接受、自然成熟或 production ML 資格。程式碼／EXE 可啟動也不授上述接受；UI 的既有 mypy ignore 設定不證強型別。
- Root 串行 QA 與資源守衛依[共用規則](../agents/shared_context.md)。本補完 task 已用完新建代理額度 10/10；只在無待寫與無衝突時重用既有 Luna。

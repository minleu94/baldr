# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-17（使用者時區）。本頁只回答現在能用什麼、下一次交什麼、哪些仍受限制。逐輪過程見[具名 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)；重規劃前全文見[歷史快照](../09_archive/PROJECT_SNAPSHOT_20261015_BEFORE_DELIVERY_REPLAN.md)。

## 現在有哪些入口

**目前指定本機試用候選為日常研究125（`147e80d35fa2`）**，入口是 [Launch-Baldr.cmd](../../output/trial/Baldr-Daily-Research-125/Launch-Baldr.cmd)。先看[試用版指南](../07_guides/TRIAL_VERSION_GUIDE.md)，版本與限制由包內收據固定。125在原個股頁提供2317／2330／2454的2026-H1五欄目前研究，來源與固定EXE正常Main／fresh、返回／重載及原值比對通過；2382文件缺件隔離。未改的價格研究、清單／持倉與回測沿124及原收據，不全數重跑或擴V1，詳[125 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment125-reviewed-fundamentals)。

115、112、109、71、66及更早候選與各自狀態保留，不自動匯入個人內容。66原回報及指南D勘誤沿原身分保留；後續修復不冒充新版真人接受。116沒有重跑未改的四條全部旅程：單股雙策略保存／比較沿用112具名證據，價格選股、收藏與舊推薦回訪按109及相應原QA判讀。

| 使用流程 | 已知可用範圍 | 還要處理什麼 |
|---|---|---|
| 看市場、查個股 | 市場狀態與四股一般價格／技術研究；2317／2330／2454有H1五欄基本面 | 一般個股仍是四股隔離價庫，截至2026-09-23；舊列缺方向維持未提供。 |
| 設條件、選股、保存研究 | 另一份2026-10-16來源宣告1,989、處理1,951、排除38；可依MA條件選股、主個股頁看原價量、同源比較、收藏及重開 | 5筆價格UNKNOWN、名錄用途與來源clock未接受；不能稱正式真N或歷史PIT。 |
| 觀察清單與持倉回訪 | 持倉位於四卡下方；唯一精確代號／名稱互補，未綁來源部位可回一般個股價量重載 | 真私人帳與真人手勢待驗；保存來源部位沿原exact守衛，Paper外部根未在試用配置。 |
| 單股回測、保存與歷史 | 124含三段收縮正常保存與新程序，並修合法千分位；三計分1.1.0及同版對照沿原鏈，受改輸入已核。窄視窗切換設定／結果並捲動 | 舊候選／run不重寫；0配對不等於無訊號。舊計分回填限制、原六配對run、SOP／Baseline FAIL、Walk-forward及完整績效仍保留。 |

原 V1 四條流程與出口維持[計畫 §0.3](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)。以上是已交付及回報狀態，不是全部 P00–P14 或 G0–G4 接受。

## 目前工程狀態與限制

原P14另完成保存研究的新副本工具：三種研究store逐bytes複製，僅重綁新索引路徑，原金融值／來源manifest不改。來源Main與既存125 EXE已從新根開原規則／結果、返回及fresh，並禁止原根I/O與重算；125候選本身不替換。操作見[Runbook](../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#保存研究的新副本來源工具)，證據見[126 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment126-research-output-copy)。行情、technical v4、一般推薦／收藏、私人帳及其他主機的完整搬移仍待，不把此步當全環境可攜。

第二列已交具名三公司固定版本：原CSV的2317／2454經完整官方半年報勾稽，沿2330原reader保留7件，新外層共9件；真保存台北19:00後才讀值。來源Main46452→35928、EXE19012→34276的五欄、版本、時間及顯示一致，四股價格／返回／重載可用，2382驗證頁缺件隔離。116項受改／Workbench、validator25/0/4、mypy1060及精度守衛通過；不授歷史PIT、前期或策略輸入。交付SHA `670e489253748b0bd3e2513413f6fbc1bcd6a55d6ff8ce8467a8af983d0f55b4`，詳[125 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment125-reviewed-fundamentals)。

124已把原P07三段轉折收縮1.0.0接入原單股Backtest／Broker／Registry與規則卡，完成來源及EXE正常保存、返回及新程序讀回。整合同時修SQLite合法千分位被轉成NaN，新run保存`historical-price-numeric-text.v1`，不改原資料或舊結果。2330／2025-01-02至2026-09-23、千萬元核對例為419已知列、1意圖／1配對；EXE9988→38812與來源一致。EXE SHA `a8b840d383b6d6a9918c074bf27ab462da3145d6f5dcd16d3b37fcf111fbeb12`，交付SHA `a012cfcfce0a49717b97db19135a4e7aa65d9c646223caf3c4826e935d792963`。百萬元同窗2330布林／W底仍0配對但有18／4意圖，不能叫無訊號；原完整計分配置的2317仍8／9／2配對。以上不是有效策略、完整雙策略績效或歷史PIT接受，詳[Increment124 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment124-vcp-integration)。基本面前期用途缺件仍維持不可用。

124另包含保存回訪的錯根拒讀：Research Registry索引複製後不再沿舊絕對路徑讀原根，也拒其他run檔名及根內連結替換。原件不改寫、121交付SHA保持；此防錯修復不是完整搬移，詳[Increment122 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment122-registry-root-binding)。

121固定來源`c62a3eca221b3a360f812973bf558061004a3315`，EXE SHA `c9bc1e3025ecd283711cd623613b18a3a97d7f300b070bc384adadf93dbcc9f7`，交付SHA `628be1285d682e3d295751ef5813ccec3ec50e88a22e54ec7b3c71bfeb08bf02`。來源Main28164→32412、EXE35832→48656皆驗2317同窗419列／2進場意圖／2完成配對及保存回訪，金融輸出一致；62項／public66項／UI91項等定向證據不加總為Gate。原大整數成交量／前列串接紅測及其他FAIL保留。完整Native、真人、F06全功能、家族與有效績效仍待；P14完整資料搬移仍受保存絕對引用限制。詳[121 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment121-bollinger-squeeze)。

120固定來源`aad10ca40a374f3d4e7406981580ce3d8c2efc1b`，EXE SHA-256 `43c0d50bdabc966e784b435a2b99a6166b4076a461d5a282ae93c76818749491`，交付SHA `0462b9748721e8463795b9c440a9c864200621597132ff8e79191b3edcfb4472`。來源Main35632→48176、EXE51132→23412，各三策略419列／332已知分數／87未知日，baseline／穩健／暴衝8／9／2配對。89項定向因果／保存測試、前輪268PASS、失敗修正後38＋17PASS及必要防線分開記錄，不加總成Gate。原2317在2025-07-30四價全缺、量0，原因未核，不補價或稱停牌；保留未知後有效區段可繼續。舊版本、119固定包及歷史FAIL保留，見[120 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment120-causal-score-input)。

交付後另以同一120 EXE原生滑鼠／鍵盤驗2330基本面五值、價格圖、觀察清單切頁返回及重載，父52368→fresh32196各8次原生點擊的曝光／命中／裁切守衛通過；13輸入與交付原SHA不變。這只補該目前研究旅程的限定Native證據，沒有重建或改舊FAIL；其他尺寸／DPI、真人及策略回測Native仍待，詳[原生補證](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#post120-native-stock-fundamental)。

119固定來源`332ff92925433baee5f6ea9f7c4dc76a206c9d64`，EXE SHA-256 `272f07ed847a74da24645a904f3091236983f5d6ed4fa48e2fdbbf3f0b7189a6`，交付SHA `f83cc8d528f1b33c4713966b00045b4f48a62f45cbea4363826971d2ca6d11a5`。新四均線用2317／2025-01-02至2026-09-23驗419列、8個進場意圖、6組完成配對；來源Main38416→2744、固定EXE6808→34096精確讀回。320項受改／共同回歸、取消與打包缺件、compile、validator25/0/4、mypy1050與精度守衛有具名結果；歷史測試失敗保留。它只交正常單股研究，其他模式／歷史PIT／來源／成本權威／有效績效／Native／真人仍待。三個原研究策略與完整P07不能按數量合計完成。

118固定來源`1444b5d298d676cedd0147ac342eaf77ff141a18`，EXE SHA-256 `1ee22609eb6beeefce56e977adaf1ad101d4365dfb07b35a13ac9fa2278298df`，交付SHA `71e127853fd7731ba9f5f40f55224c4f5399932321b8169b74b8fb9d50417d51`。來源Main及固定EXE的同源個股、原頁返回、收藏及fresh均有定向收據；112項受改／共同UI防線通過。Windows Qt功能不授Native／真人／完整Gate；沿117的五項基本面與116保存修正，不重驗未改旅程。

115已納入跨視窗TabOrder、Qt model自有連線清理及pandas相容性修復；原受影響回歸、共同UI防線與13個隔離MainWindow旅程見[啟動警告修復QA](../06_qa/BALDR_STARTUP_WARNINGS_FIX_20261015.md)。115該次同版EXE父／新程序未收到Qt警告；公司名冊缺來源憑證的提示仍保留。

116已修舊回測因Decimal附註而降級CSV、讀回再失精度的缺陷；33個受影響測試、compile、mypy／精度守衛與正常Python Main四筆保存→新程序通過，同輪固定EXE另驗高精度原值新保存及重開。原producer的float DTO按原位元身分核，不授完整精度；舊CSV／SQLite摘要不遷移。前段來源階段、失敗與補證原樣見[Increment116 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment116-legacy-parquet-precision)。

**116固定來源為 `1cf80e32b4c229177152d364fce06ec4e63ec948`，EXE SHA-256為 `ba38c46e72a880b7c1016210c748c826c026a18ffec8631c7a1cb14223830ca1`。** 後續工作樹不改該EXE。18份固定狀態由109核SHA另複製，詳[交付收據](../../output/trial/Baldr-Daily-Research-116/DELIVERY_RECEIPT.json)；程式碼包含某家族不表示其金融或完整產品資格已接受。

原66候選的交付歷史：依[原計畫 §0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)，第一列「日常研究修正版」已形成固定可試用候選。受改測試、共同 UI 防線、兩筆隔離持倉、來源與 EXE 的正常 Main／新程序及同版檢查已限定通過；EXE SHA-256 為 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`。交付收據最初記錄 SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2`，目前檔案 SHA-256 為 `16bb4f511e5ecb21dff6667a5a38fa7aa73d298bf951ea69c0ce85b42e128eb1`；原因未裁決，兩者不混稱同一位元原件，詳[Increment67 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment67p08-推薦回放通用比較的金融判讀阻斷)。這只關閉本列工程交付出口，真人試用及完整產品 Gate 仍待。

| 接續順序 | 使用者會拿到的成果 | 目前位置 |
|---|---|---|
| 1. 日常研究修正版 | 四流程及受改缺陷的固定候選 | 118已交同源個股／返回／收藏／fresh修正；真人與不同DPI待試，不重跑未改流程。 |
| 2. 有來源的基本面研究 | 正常個股頁的當期／前期與保存重開 | [125固定候選](../../output/trial/Baldr-Daily-Research-125/TRIAL_GUIDE.md)已交三公司2026-H1五欄及來源／EXE正常Main／fresh。2382、前期、其他公司、歷史PIT及完整Native仍待；原117命中FAIL保留。 |
| 3. 持倉與研究情境 | 同帳本現金／行情／Health的初次情境、保存及返回 | 隔離合成來源已有定向證據；缺真人策略Paper帳與同日原件，不以手動成本造NAV。 |
| 4. 可比較策略研究 | 原規則、獨立結果、保存／比較／明細返回 | 120交三計分1.1.0因果缺值與同版研究對照，沿119四均線；來源、幣別、成本權威、歷史PIT及完整雙策略績效仍各自待。 |
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

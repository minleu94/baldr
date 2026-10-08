# 1,000 檔合成保存研究產製與獨立讀回

最新單次診斷 session6599（`C:/t/p01_ou8p3n_6`）終態 exit1，完整 report 身分與八項來源 pins 通過後，strict-open 的合法唯讀 `fdopen` 被 QA 守衛拒絕；尚無 pstats／效能樣本。來源前後一致且 Job 已證明零 owned 殘留。下一步修正診斷工具的精確唯讀 descriptor 契約，詳見本文末段；既有完整矩陣的三項效能失敗仍有效。先前 session45903 的 report 映射失敗封套保留，不能覆寫為通過。

## 固定 acd 讀取器完整矩陣（2026-10-08，效能未通過）

新 attempt `C:/t/p01_mc6g40xn` 僅沿固定 `acd18a1efcc045951defc00b79167035b6ec6f2d` archive 讀取原封存合成來源，未重跑 producer。中央直接讀 `benchmark_result.json`，SHA256 `5d0beaf0480c14b1cf009e67fdd54cb3c6c64f4714f5db999545187423554c74`；完整五冷／一暖／五類各 30 次樣本完成，整體 status failed、controller exit 1。下列為原嚴格 `<300ms` 的來源引擎 p95，不是 GUI 或 EXE 延遲。

| 暖操作 | p95（毫秒） | 原門檻 |
|---|---:|---|
| 翻頁 | 813.5101 | 未通過 |
| 篩選、全域選取及首頁 | 1208.0899 | 未通過 |
| 全域排序、選取及首頁 | 879.3598 | 未通過 |
| 單股 materializer | 73.0590 | 通過 |
| 16 股跨段 materializer | 290.0902 | 通過 |

中央另直接核五份 cold result：五個不同 PID 均處理完整 1,000 檔，首頁 50 股，query／page identities 相同。分母 declared 1001／included 1000／excluded 1／processed 1000／pending 0／missing 1；缺件仍保留。Cold launch-to-page p95 為 93.3948601 秒，不能當成暖操作或真人頁面 p95。來源 archive、DB、store、controller／helper／qualifier／receipt／原 report 的起訖 pins 相同；六個 audited worker launches 精確符合白名單，SQLite／網路為零，Main／EXE／producer 未啟動。

中央讀 warm resource summary：worker exit 0、sampler valid／closed、3058 samples、無 sampler errors；Job closed、剩餘 owned PID 為空。舊完整矩陣及本次失敗封套都保留。相較舊矩陣的四類失敗，本次跨段 materializer 達標，但仍有三類效能缺口；不能授整體效能、正式市場 N 或 M2 完成。接續以同份來源的單次翻頁函式 profile 定位成本，不能略過 source hash／proof、縮母體或更改門檻來換通過。

依使用者明確授權，在全新隔離目錄建立合成股票資料、執行產製器並保存測試封套。正式資料與正式排程不在此測試範圍。

## 有限接受結果

固定來源為 Git archive `2897f269d6b5ee6618698f191ad117adb73c0672`，不是目前候選執行檔。隔離 case `C:/t/p01_b3mrz9_8` 的產製器收據為 complete：四個分段完成、納入1,000檔全部處理、待處理0。原始代碼1,002筆，去重後1,001檔；其中1檔明示排除。納入列另有1檔缺資料，保持缺件，不改為成功資料或待處理。

中央獨立 public `StoreReader.read_exact` 核驗同一 generation／plan／receipt 與各 bytes SHA，session82282 terminal0，收據 status verified。來源 archive／tree、合成 SQLite 及 sidecars、整份保存來源、原失敗封套／phase／manifest 前後身分一致。補驗未載入 producer 或 ML，SQLite、網路、子程序、被拒寫入計數均0。

新證據位於 `output/qa/p01_b3mrz9_8_readback_qualification_20261008_b/readback_qualification.json`，SHA256 `f1a69b9d2e2f729cf49cd5610e8ca4acd8c0f2298f99601853d254db1368b3bf`；helper SHA256 `82a26815d4e4b30cb1e1d9b2f595e7cabff3ab38d9141f3edd1efca31906d037`。helper只建立新的獨立證據，不覆寫原failed結果。

## 身分與完整性

| 項目 | 已核值 |
|---|---|
| Generation | `34066dc3d86cf4bc70bcac84b543290cb6b047bd0df295d13b8c2e4c6a2a0c02` |
| Plan identity | `08b757c0b9e86e82394d52dca8a0ebb6033665e282211ef56caed353e9224d17` |
| Receipt identity | `b278e93058fc537dc87af98117c17a8e5d8771653464aaed3e496401778f28ff` |
| Receipt bytes SHA | `1f357f468150e595c3af33797a0b5e94afb4adcf13a38cd8cf15f79ea25ce1f2` |
| Source clock identity | `9606c2267746cf621f314235c5e7464cad5ebaab7b89955268ab572242714286` |
| Method contracts SHA | `d3254c71badda536fa91856e5aef53b56d71f4138430a0386b55e60fb367c0da` |
| Calculation identity | `3ae700370a0043f9a85cc8f694575075d60b5985bcc927a16860fa6ff0f40f10` |
| 合成 SQLite bytes SHA | `e87a96c7cbabaac8f208b64bb8de57ef383f3d6100fccee3660862fd5ca4593d` |
| 封存來源 tree SHA | `a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9` |

保存寫入事件1,070筆逐筆核對固定writer、精確暫存／目的路徑、原生descriptor身分與容量；拒絕0、未關閉追蹤descriptor0，事件計數對帳。原產製封套未保存逐筆SQL連線清單或精確總數；只能依固定控制器在失敗前已通過的檢查，確認至少一筆連線且限制為該合成source.sqlite的ro模式。獨立補驗沒有SQL連線。Store writer原事件的容量參數為null，另依固定來源的plan／receipt容量常數核對，不捏造原記錄內容。

## 原失敗與尚未授予資格

原產製控制器C63在產製完成後誤用不存在的receipt.counts，原結果仍為failed／checks空。第一補驗最後輸出因Windows audit預設O_NOINHERIT旗標被誤拒；窄修後第二補驗保存failed，錯誤為報告使用不存在的Plan日期／方法屬性。新helper改由已驗證的Plan.to_dict取值，先通過純型別／API自檢，再完成本次完整讀回。所有舊失敗保留，沒有重跑producer或改判舊結果。

本結果只接受固定來源的合成產物與獨立讀回，不授予原控制器整體成功、正式來源／歷史PIT、實際市場N、效能、MainWindow、Native／exe或真人資格。冷5／暖30效能與正常資料產製仍須分別完成，完整P00–P14／M1–M3目標不變。

## Source-only benchmark 守衛中央補驗（2026-10-08）

root 獨立執行 parent／worker 組合自測，exit 0；新 case `C:/t/p01_hgz9tl64`，log `output/qa/p01_b3mrz9_8_source_benchmark_20261008_a/root_guard_composition_20261008_a.log`。固定 controller SHA256 `79f402906920754e5a5f97c4691d34a20983f0b260a3639dd2d958929c9955dc`，selftest SHA256 `784cf2ffc51f7c4f05c94272e29b8c3c426c3dc605a581d9fb939c088ce6a510`；C63 helper 未變。

六個合成 worker 成功，六個錯誤啟動反例拒絕；network／SQLite 都為 0。實際 parent guard 的拒絕被 fake worker 吞下並回傳 passed 後，after-worker gate 仍拒絕；下一次 before-launch gate 不呼叫 launch，failure envelope 保留有界 denial snapshot。來源與 protected sentinel 前後 SHA 一致，沒有產品 API、模型、產製器或 benchmark 執行。

本項只接受 QA 守衛組合與立即停跑契約，不授予正式 worker 或冷暖效能接受。中央 F17 回歸仍執行中，完整冷 5／暖 30 矩陣須等其他重測停止後單獨執行；原失敗 attempts 不覆寫。

## 首個真 worker 與 parent 收據失敗（2026-10-08）

root session 16749 terminal exit 1；新 attempt `C:/t/p01_yyuuqth0`，controller SHA 79f402906920754e5a5f97c4691d34a20983f0b260a3639dd2d958929c9955dc。cold_01 真 worker completed／passed，原結果與 events 留存：declared 1001、included／processed 1000、excluded 1、pending 0、missing 1；第一頁 50 列、matching 1000。worker 的 source archive／合成 DB／sealed store 前後一致，network／SQL／子程序皆無。

該單次 cold 的引擎 strict-open 15.7664812 秒、query／selection 0.1004507 秒、首頁 materialize 0.7595453 秒，合計 16.6285502 秒；controller launch-to-page 68.419395 秒另含啟動等成本。這是一筆 cold 樣本，不是完整矩陣或 p95，不授予 300ms 接受。

parent 在 `_run_child` 寫 resource summary 時仍呼叫原 C63 `_write_json_new`，該 helper 先呼叫 case root `mkdir(exist_ok=True)`，被新 parent guard 拒絕。完整 traceback 留在 cold_01.controller_failure.json；after-worker gate 即刻停跑，沒有 cold_02／warm。outer failure 未保留 local Job 清理狀態，因此 cleanup 為 unknown，不能聲稱零殘留；原 resource samples 與 worker passed 結果不覆寫。修正僅限 parent 寫入改走 exact exclusive wrapper，並補實際 `_run_child` 合成旅程及 metadata 失敗清理證據。root 有界診斷另存 `output/qa/p01_b3mrz9_8_source_benchmark_20261008_a/root_yyuuqth0_diagnosis.json`。

## Parent 最終保存錯誤中央補驗

root 獨立 selftest exit0，case `C:/t/p01_ucayb301`，log `output/qa/p01_b3mrz9_8_source_benchmark_20261008_a/root_guard_finalization_20261008_b.log`。controller固定 SHA256 `38b4ea08f362908b84f9ab49799d728a646b38bec8f6eb9c9833e9e5792551ec`；真 `_run_child_preserving_failure` 在 worker passed result已保存後注入 resource-summary 錯誤，仍保留已驗 bootstrap/PID/create-time、7筆samples的path/hash/size/count與實際Job closed／零ownedprocess證據；原workerresult bytes不變，parentfailed且停止矩陣。沒有把未知樣本偽造為零，未重複嵌樣本明細。固定C63helper未改，network／SQL／producer／model／benchmark都沒有執行。

這授予 QA finalization 契約有限接受，不能改寫原 `p01_yyuuqth0` cleanup unknown。root另啟新的完整1000檔source-only矩陣 session63774，目前執行中；其他代理測試／build／Native已暫停，原始資料及正式排程不在本矩陣範圍。結果未到前不授完整p95接受。

## 完整冷暖矩陣終態（效能未通過）

session63774 已 terminal exit1，新 case `C:/t/p01_yyz7kyi8`。固定 controller38b4、來源2897及既有合成store不變；五個獨立cold worker與一個warm worker均完成，parent guard拒絕數0。完整included／processed1000、declared1001、excluded1、pending0、missing1；來源archive、合成DB、sealed store前後一致，SQLite連線0，未啟動MainWindow／EXE／producer。這是固定來源引擎測試，不是2382或實際全市場UI驗收。

冷啟動到首頁五筆68.385–69.021秒，最近秩p95為69.021087秒，含啟動及證據封裝成本。暖操作每類30筆的引擎p95如下：換頁0.8270295秒；篩選／selection／首頁5.1925273秒；全域排序／selection／首頁1.471302秒；單股materializer0.2235914秒；16股跨段materializer0.4444089秒。只有單股類達300ms門檻，其餘四類明確失敗，不刪慢樣本或放寬門檻。

完整結果與逐筆資料保存於該case的benchmark_result.json與各worker檔；大檔只能解析必要欄位，不能整檔輸出。中央另獨立核sample／nearest-rank／Job清理證據，該補審結論尚待。效能失敗已解除重測互斥，價格query的真257跨段功能回歸可接續；不以本矩陣授Native或正式版接受。

補審完成：事件檔150筆（每類30）重算的最近秩p95與controller一致，冷5 PID各自不同；六個worker sampler有效／無錯誤／已關閉，Job清理均驗零殘留。controller／recovery report前後一致；原result SHA256 `fcb10a761c73cd6551f624d27c449b8a37966b174bee825ec73f0f5b6c8efaaa`，有界review SHA256 `e343d3c392cff5700a18f41ae01250aa7669e4b7997fb05ebc17ac66b0e21ff9`，保存在原QA目錄root_matrix_yyz7kyi8_review.json。完整矩陣的資料核驗與效能未達標均已確認，沒有重跑或改寫原樣本。

## acd18a1e 翻頁剖析首次啟動失敗（2026-10-08）

中央啟動單次診斷，session11338 終態 exit1；新隔離 attempt `C:/t/p01_uhaqbi84`，收據 SHA256 `d806a816327d2dced7047cd69f6a074cd24d3606ae77c8cb3aa4e03ab73f7c0b`。supervisor SHA `c9eb3e303ffb7cb694d6eb03756ed8a35376f257a94e5d212ecdd1e61aa94091`、profile SHA `705b2f1f3137a36e70d0b99c9bbfec0533fc1186e0c76a59e46ead6864f3a3d9`；固定 controller/helper 未改。Popen 在建立 stdin pipe 的 `io.open(3, 'wb')` 被 parent metadata guard 拒絕，尚未取得 child PID／Job／profile result；cleanup 證據為 unknown，不能授零殘留或真 Job 驗證。source 起訖與全部固定輸入 pins 一致，保留拒絕計數1與失敗封套。

此結果未產生效能樣本，不能替代最新 acd18a1e 完整矩陣的三項暖操作失敗。下一步只修 QA supervisor 的精確 pipe 初始化契約並補自測，不修改固定 controller/helper，不放行任意數字 descriptor 寫入，也不重跑整個冷暖矩陣。

標準輸入改為 `stdin=None` 後，中央獨立 guard-only 自測 exit0（`C:/t/p01_tfj5381x`）；readonly numeric pipe audit 事件通過，write 事件仍拒絕，沒有放行 descriptor 寫入。supervisor 新 SHA `11e0c13f9f7456bf040bf13e732a53fb6db9e87806351531511ef36aba87da0c`，profile/controller/helper 不變。

新單次診斷 session74526 終態 exit1（`C:/t/p01_6zm2rnit`），收據 SHA `01b61eb6e07f68f5a4e83714624fa07611debb378a82a14ec144f848f4602311`。parent exact-launch 與 metadata guards 通過，拒絕數0；Job 觀察到三個 PID，超過 QA sampler 的兩個上限而停止。Job 已終止／關閉，實際證明零 owned 殘留，來源與全部固定 pins 起訖一致；尚無 profile 結果。接續核對 venv launcher 鏈的三個 process identity／image／commandline，再修正 QA sampler；不能僅放寬數量或把本次診斷當效能接受。

中央於 2026-10-08 獨立審查並執行修正版 supervisor 的 guard-only 自測，attempt `C:/t/p01_gn8il8w8`、exit0；supervisor SHA `7e02a68c72915cb21201e63ba786cc9fc03b6c11670094e8a1bdac9a4a863e5f`，profile SHA 仍為 `705b2f1f3137a36e70d0b99c9bbfec0533fc1186e0c76a59e46ead6864f3a3d9`。合法三程序鏈合成正例通過；錯映像、SHA、父程序、原生 argv0、角色互換、第四個程序與非正規 conhost 路徑負例均拒絕。自測實際啟動子程序0、SQLite連線0、產品模組載入0；不是實際 profile 或效能接受。固定 conhost 起訖身份／SHA 一致，保留其系統硬連結數2的精確例外。base Python 原生命令核對固定 base image，venv `sys.executable`／prefix 契約另行核對，未放寬為任意 Python。下一次單次 profile 等 MA 定向測試終態後執行，避免重型測試互相干擾。
## 翻頁診斷的唯讀 descriptor 守衛衝突（2026-10-08）

中央單次診斷 session6599 終態 exit1，隔離 attempt `C:/t/p01_ou8p3n_6`；parent 收據 SHA256 `086eac8081ce7584798ea31a218bcd60568e2a7a90f3f20ea17a8b0a52af8f4a`。修正後 report 身分與完整八項來源 pins 已通過，child runtime PID24708 及三程序 Job 身分已核驗。來源前後一致、Job 清理零 owned 殘留，沒有 SQLite／網路／巢狀子程序操作。

child 在 strict-open 的 canonical file 讀取路徑失敗：固定 reader 先以唯讀旗標 `os.open`，再以 `os.fdopen(descriptor, "rb")` 包裝；profile 套用的 parent metadata guard 對 `fdopen` 全面拒絕，因此尚未產生 pstats 或效能樣本。完整 traceback 保存在 `warm_01.result.json`。這證明 QA 守衛與合法唯讀路徑衝突，不能當作產品效能結果或來源讀取通過。

後續修正範圍限定 profile 的精確唯讀 descriptor 契約與自測：核固定 reader caller、精確來源路徑、唯讀 open 旗標、原生 handle 身分及單次 token；其他 descriptor、寫入與 dup 仍拒絕。固定 controller、helper、archive、report、sealed store 與來源核驗條件保持固定。修正後先由中央審查 guard-only 自測，再排程單次診斷，不重跑完整矩陣以取代既有失敗樣本。

# Baldr 本機資料品質唯讀盤點（2026-10-25）

<a id="2026-10-26-mops-q2-announcement-event-pit-projection"></a>

### 2026-10-26 MOPS Q2 公告事件到季報候選 PIT 日期投影

依 Owner 已確認可把 MOPS 顯示的公告日期／時間作為該公告 timestamp，新增隔離候選橋接：以同公司、同期間及 F26/F27/F28 報表類型精確配對 MOPS EZSearch 事件與 T164 數值列，保留原始 numeric capture timestamp／date，另將 date-only `available_date` 投影為台北公告日的次一日並標示 `mops_announcement_next_taipei_calendar_date`。候選 adapter 會驗證 MOPS source/version、event hash 格式與報表類型對應，拒絕仍沿用較晚 numeric capture date 的候選；無公告事件的舊候選仍以 numeric capture 的次一日為可得日。

受控 focused QA：公告事件 date-only cutoff、新舊日期差異、舊 numeric capture date 拒絕、既有 capture date cutoff，以及 bridge 的三表精確事件配對、原始 T164 bytes 防竄改與錯期間拒絕 **6 passed／19 deselected**；四個 Python 檔 `py_compile` 通過。Focused receipt SHA-256 `7f9c0df9664596053818fce9e3c1d9ce5cb48021873531e34b0382cce02cf6a0`，8 GiB／12-process／kill-on-close 限制讀回、剩餘 PID 0、無強制清理。另以原始 2330／2026-Q2 172 列輸入重新生成隔離候選：172 列均為 `available_date=2026-08-15`、`numeric_available_date=2026-09-08`；candidate SHA-256 `abb1b6ba2d496600d6155b70cf9aba99ccd8d50eafe957de72a8ad42535f19f9`。真實候選經 adapter／provider 隔離 sidecar 讀回：2026-08-14 可見 0、08-15 可見 172，品質仍全為 degraded；readback receipt SHA-256 `d770114bff9f423cebdd148ca41b9c8f5aa2c47c984da9af110c8056dfe90f8f`，Job 自然歸零。完整 adapter／bridge 兩檔 suite 在 sandbox 外的受控 Windows Job **24 passed／1 skipped**；略過項是此 Windows 環境無法建立 symlink 的案例。完整 suite receipt SHA-256 `ce8547715365db029f378fb402010feef9340c7caa35ff75d3f671871b42c817`，8 GiB／12-process／kill-on-close 限制讀回、剩餘 PID 0、無強制清理。先前 sandbox 內 9 個 CLI `Path.resolve(strict=True)` 失敗由 sandbox temp-path 權限造成，sandbox 外同套測試已通過。此投影仍只存在研究候選／隔離 sidecar，沒有寫正式 DB、沒有把品質從 degraded 改 observed，也沒有接受版本、PIT、Gate 3 或 ML credit。官方 PDF bytes／列語義／單一正式 source-version 唯一橋及 4 個 unresolved 列仍待處理。

<a id="2026-10-26-monthly-revenue-quality-verification-details"></a>

### 2026-10-26 月營收公告日缺漏／報表日期核對明細

Research Console 的月營收品質明細現在同時列出 `announced_date` 空白列與來源為 `mops.monthly_revenue_static_report`／`mops.monthly_revenue_static_snapshot` 且日期非空的報表層級列，並排顯示公司、來源、版本、SQLite 現存日期、MOPS 公告日期及核對狀態。頁面分頁上限 100；SQLite 以 `mode=ro`、`query_only=ON` 讀取，不回傳營收值、不寫正式資料。摘要只在 `(stock_code, period, source_version)` 精確對應且 mapping 日期等於 SQLite 現存日期時，才從報表日期待核實數扣除；只有版本 mapping 但日期不同會保留待核實。

以正式資料庫與正式 availability mapping 做逐頁唯讀回讀：

| 資料月份 | 正式列 | 缺公告日 | 報表日期待核實 | 品質明細列 | 精確日期相符 | 無精確版本 mapping | 2330 對照 |
|---|---:|---:|---:|---:|---:|---:|---|
| 2026-04 | 1,848 | 1,847 | 0 | 1,848 | 1 | 1,847 | `mops-static-snapshot-monthly-revenue-2026-06-16`，正式日期／mapping 均為 2026-05-08 |
| 2026-05 | 1,848 | 0 | 1,847 | 1,848 | 1 | 1,847 | `mops-static-snapshot-monthly-revenue-2026-07-14`，兩日期均為 2026-06-10 |
| 2026-06 | 1,832 | 0 | 1,831 | 1,832 | 1 | 1,831 | `mops-static-snapshot-monthly-revenue-2026-08-15`，兩日期均為 2026-07-13 |

三期各有一列精確日期相符；其餘列沒有精確公司／月份／版本 mapping，仍待官方證據。2026-04 的 1,847 筆公告日缺漏沒有因此解除；2026-05／06 各剩 1,847／1,831 筆報表日期待核實。這次只改明細與摘要判斷並增加日期一致性條件，正式資料寫入 **0 列**、品質／degraded 解除 **0 列**，Gate／PIT／ML 資格不變。頁面測試覆蓋按待核實月份啟用、精確相符、日期不一致、無 mapping、unknown 及 unavailable；Owner 原生 GUI UAT 未執行。

QA：monthly reader／Research Console service／view **103 passed**；必要 Update Workbench UI **97 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；全域 mypy **1,157 source files、無 issues**；3 個修改 Python 檔 `py_compile` 通過。正式資料逐頁讀回與上述測試在受控 Windows Job 下自然結束，limit 8 GiB／12 processes、剩餘 PID 0、無強制清理。Focused receipt SHA-256 `82941f948db1735dfc81fe76f839c47063ebbece1fb7de8f2459e9927ce8424e`；正式資料唯讀回讀 receipt SHA-256 `92312a32cc987ac4146a4157fbd0bb3e9b1dc5ed3ac9dbfeaa9933180a164653`；合併驗證 receipt SHA-256 `030848ce7d713ff5d90bdd14f2ddd88fe744a59fa31e1e3167b591fc6052d5f7`。Feature Map／UI Features／本 QA inventory 的 scoped document-control **12 features／3 link sources／0 errors**。包含 Snapshot 與 Manual 的廣域檢查因既有 `output/` junction 對 29 個舊 trial/task links 回報 `WinError 5`；未修改該 junction，也不記為通過。

<a id="2026-10-27-mops-f22-2330-q2-monthly-exact-version-backfill"></a>

### 2026-10-27 MOPS F22 2330／2026-05、2026-06 精確版本回填

依 Owner 已授權的公告時間語義，對 2330 的 F22 2026-05、2026-06 各自保存 MOPS EZSearch 與官方明細原件，逐一核對公司、月份、單位及營收值，再綁定 SQLite 的精確來源版本。2026-05 公告時間為 2026-06-10 14:36:51（台北），金額新台幣仟元 416,975,163；EZSearch SHA-256 `f23f73cb73d059df681c5b0bc9615ef20578727e62826831e7482bdb06079fea`、明細 SHA-256 `4904f8b57a20f58e731f3300dea990cf5e7fad0def78ea7009a13ee6ad97fc80e`。2026-06 公告時間為 2026-07-13 14:29:56，金額 442,679,969；EZSearch SHA-256 `f1219831bbe92b2532c4d2896f290ac371d63e378f703643559e3f7e36fc506a`、明細 SHA-256 `07d89502f8a48951958cd9341fcae0c113b4c5410174868f69e9fef3817efced`。兩份 EZSearch 查詢都小於 1,000 列上限，且各只有一筆精確匹配。

正式 availability mapping 新增 2 列、保留 1 列既有紀錄，衝突／診斷皆 0；2026-06 保留原 TWSE revision 1，新增 MOPS revision 2 並以 `parent_revision=1` 延續歷史。兩筆 `formal-availability.v2` mapping 分別綁定 `mops-static-snapshot-monthly-revenue-2026-07-14` 與 `mops-static-snapshot-monthly-revenue-2026-08-15`，hash 對應 EZSearch 原件；正式 mapping SHA-256 `287A443526D7299915C85C2B607E6AC23F19E00CB2A11BEE2EDB89D210D12076`。正式 SQLite 備份 4,111,114,240 bytes；複製前後來源大小、mtime 相同，WAL／journal 為空，備份 SHA-256 `f33b05b9c66183f08331614305f40083ae3b226e9e2582b2a1e44c4d0ff153e2`，更新前後 `quick_check=ok`。

以公司、期間、as-of date、營收值、原 source/source_version、舊 announced/available date 及 `observed` 品質作條件，正式庫精確更新 **2 列**：5 月 `2026-06-16 → 2026-06-10`、available `2026-06-17 → 2026-06-11`；6 月 `2026-07-14 → 2026-07-13`、available `2026-07-15 → 2026-07-14`。營收值、品質、來源、數值版本、as-of date 及 created_at 保留。回查確認兩筆值與版本無誤，availability loader 診斷 0；由於兩列原本已是 `observed`，本次 degraded／missing 正式解除 **0 列**，Gate／ML 資格不變。

研究台摘要已接上正式月營收 availability mapping：只有 `mops.monthly_revenue_announcement`、`formal-availability.v2`、官方公告證據 hash 完整，且 stock／period／announced_date／target source version 全相符的列，才會自靜態日期待核實計數扣除。唯讀摘要回讀 2026-05 為 1,848 列、公告日缺漏 0、待核實 1,847；2026-06 為 1,832 列、公告日缺漏 0、待核實 1,831。其餘列仍明確待核實，沒有擴大套用。此修改只改研究台摘要判讀，不授予 Gate／ML 資格。bounded Job 讀回 payload 成功、剩餘 PID 0；三個修改 Python 檔 `py_compile` 通過，未執行測試套件，也未做 Owner 原生 GUI UAT。

富邦 API 的前一輪缺值核對也無候選可補：Gate 2 OHLC 為 0/16 精確命中，Forward 19 筆為 0/19；富邦不提供 MOPS 公告時間或季報數值版本橋。此次不呼叫帳務、持倉、委託或交易端點。

### 2026-10-26 MOPS F22 2330／2026-04 單列正式回補

依 Owner 已授權的 MOPS 公告時間語義，對 2330 的 F22／2026-04 做單筆官方查詢並保存原件。EZSearch 回應 HTTP 200、241,086 bytes、SHA-256 `d7570f52177dab08192d58e79a84f478ca706b1268fc5ec7d6a39532bbae82a0`；唯一對應列為 `115年4月營業收入`、公告時間 2026-05-08 14:40:12（台北）。官方明細 HTTP 200、6,444 bytes、SHA-256 `e064e4d2fb662078e9b198a7ca4c951370421f4bee0057fb67cb2cada19b6f3a`，列示民國115年04月、單位新台幣仟元、本月營收 410,725,118。正式 SQLite 唯一同公司／期間列的營收完全相同，source version 為 `mops-static-snapshot-monthly-revenue-2026-06-16`；mapping 明確綁定這個 target version。

正式 mapping 以 `formal-availability.v2` 保存公告日期 `2026-05-08`、timestamp `2026-05-08T14:40:12+08:00` 和公告原件 hash。revision 1 保留，revision 2 將錯標的擷取日期標籤改成穩定事件識別 `mops-ezsearch-f22-2330-2026-04`；候選 merge 無診斷、無衝突，新增 1 列。正式 DB 在已驗證的 4.11 GB SQLite backup 後，依公司、期間、as-of date、舊值、來源、target source version 與 `degraded` 狀態完整條件精確更新 1 列：`announced_date=NULL → 2026-05-08`、`available_date=2026-06-17 → 2026-05-09`、`quality=degraded → observed`。營收值、原始來源、target source version、as-of date、created_at 均保留。更新 available date 是依公告日翌日回補的歷史 PIT 校正；未把 6/17 靜態快照抓取日誤當公司可知日。

正式 provider 讀回結果：2026-05-08 決策日不載入此列；2026-05-09 起載入 2026-04、410,725,118、`observed`，source version 精確為上述 target。正式資料 aggregate 為 246,331 列，`observed` 3,681、缺公告日／degraded 242,650；2026-04 缺公告日由 1,848 降至 1,847（其中 1 列仍是報表層級日期待核實），本次正式解除 **1 列**。正式 DB `quick_check=ok`；mapping loader diagnostics 為 0。回補後正式 DB SHA-256 `f33b05b9c66183f08331614305f40083ae3b226e9e2582b2a1e44c4d0ff153e2`，正式 mapping SHA-256 `0d2d9622e066dea928a214a8ff5837a0f3a781f0a520ca24e7fb788c3f7113e3`。DB backup 位於隔離工作區 `owned-validation/mops-f22-2330-202604-20261027/formal-db-backup.sqlite`，4,111,114,240 bytes，SHA-256 `5e9b987d9b0ae8f72e66bb7dba388affaf1d16b9f9e1059ac1d38629e3de2e04`；首次 mapping 備份 SHA-256 `ea6c0c5651e94f605dc10ac8f4cc36803193e8d3aad0db63a7b9f31d72728f7e`，revision 2 前 mapping 備份 SHA-256 `c126a156d42db0f0ad16ee69a88b976e19e6c88125a191ab9239d606dce9b4a0`。單筆 receipts、候選及明細原件同在該隔離目錄。

這是具體單列的公司、期間、F22 報表及 target source version 對應；不外推至其他公司／月份、不啟動批次抓取，也不表示 MOPS 批次採集條款已完成審查。這筆 row 現可由正式 date-only PIT provider 按 5/9 起使用；不代表其他來源、季報、Gate 或 ML 資格通過。原先本節所述「沒有 F22 原件、解除 0 列」是回補前狀態，已由本段新證據取代。

### 2026-10-26 月營收 availability mapping 保留公告 timestamp

月營收候選 mapping 新增可選 `announced_at` 欄，接收已驗證事件原件提供的 ISO-8601 時區時間；投影器要求其台北日期與 `announced_date` 一致，loader 拒絕無時區或日期不符的值。merge fingerprint／serializer 會保留此欄，舊 date-only CSV 仍可讀；沒有事件 timestamp 的來源保持空白。這只保存與核驗公告時間證據，正式 fundamental runtime 和策略 PIT 仍以日精度 `announced_date`／`available_date` 判斷，不能宣稱具盤中 PIT。

該次 timestamp contract review 當時沒有 F22 公司／月份原始事件可提供 `announced_at`，正式月營收解除仍為 **0 列**；靜態報表 `出表日期` 繼續被拒絕作公告時間。受控 Windows Job 驗證涵蓋 timestamp 保留、台北日期一致、時區缺失、同 revision 時間變更衝突及舊 CSV 相容：五組來源／history／merge／builder／fundamental 測試 **58 passed**，4 個來源模組 mypy clean，7 個修改 Python 檔 `py_compile` 通過。Job啟動前可用 RAM 28,391,813,120 bytes；上限 8 GiB／12 processes，累計 9 個程序、剩餘 0、handles closed、無強制清理；receipt SHA-256 `d9e95302bcbb51b6910ebb547702146350d78ad34bc3321bcbd3b7424ff2de00`，log 位於隔離工作區 `owned-validation/monthly-timestamp-contract-final-20261026/stdout.log`。pytest 暫存目錄使用 repo 內受控臨時路徑，結束後已移除。scoped document-control **12 features／4 link sources／0 errors**，receipt SHA-256 `eb0b1b755a9dfda5d398e4bce681d635f2571e3e18db6355ec4daa0cbd30a0e3`；包含 Snapshot 的廣域檢查受既有 `output/` junction `WinError 5` 阻擋，未記為通過。該次紀錄時正式 DB 未改寫；後續單列結果見本文件上方 MOPS F22 回補段。

### 2026-10-26 MOPS F22 monthly version binding and Q2 probe

月營收 availability mapping 增加可選 `target_source_version`；新的 `mops.monthly_revenue_announcement` mapping 必須明填它，formal provider 只會把日期套用到 SQLite `source_version` 完全相同的月營收列。merge fingerprint／serializer 保留目標版，舊 CSV 與既有非 MOPS mapping 可讀。這修正「只憑公司＋月份＋日期就套版」的程式缺口，但不會自行證明公告事件與數值快照是同一報表版本，也不會改動正式資料。

以官方 MOPS EZSearch 頁面人工唯讀查得 2330 的 2026-Q2 三筆 F22 公告，結果列時間與月營收明細如下；MOPS 明細的表頭單位為新台幣仟元。這是瀏覽器頁面檢視，沒有保存 EZSearch HTTP response bytes／header 或建立正式 availability candidate。

| 月份 | EZSearch 公告時間（台北） | MOPS 明細本月數值 | 正式庫列 | MOPS 明細 |
|---|---|---:|---|---|
| 2026-04 | 2026-05-08 14:40:12 | 410,725,118 | 數值相同；`announced_date=NULL`、`degraded`、`available_date=2026-06-17`、source version `mops-static-snapshot-monthly-revenue-2026-06-16` | [2330／115 年 4 月](https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs?encodeURIComponent=1&step=1&firstin=1&off=1&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id&inpuType=co_id&TYPEK=all&isnew=false&co_id=2330&year=115&month=04) |
| 2026-05 | 2026-06-10 14:36:51 | 416,975,163 | 數值相同；目前 `observed`，公告日為靜態快照日期 2026-06-16 | [2330／115 年 5 月](https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs?encodeURIComponent=1&step=1&firstin=1&off=1&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id&inpuType=co_id&TYPEK=all&isnew=false&co_id=2330&year=115&month=05) |
| 2026-06 | 2026-07-13 14:29:56 | 442,679,969 | 數值相同；目前 `observed`，公告日為靜態快照日期 2026-07-14 | [2330／115 年 6 月](https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs?encodeURIComponent=1&step=1&firstin=1&off=1&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id&inpuType=co_id&TYPEK=all&isnew=false&co_id=2330&year=115&month=06) |

因此 3/3 個月份的公司、期間與單一營收數字相符；只有 4 月是目前缺公告日的 degraded 目標。其 SQLite `source_version` 是後來的靜態快照版，事件頁也尚無不可變 response hash／修訂識別碼可證明 event→snapshot version bridge；5、6 月則是公告日來源校正候選，不能當作缺值解除。這三列目前正式解除仍為 **0**，available date、quality、DB／mapping 都未改寫。MOPS EZSearch 自動擷取的端點用途條款在既有審查中仍未裁定，因此本次只做單案頁面核對，沒有擴大自動下載。

目標版本護欄受控 Windows Job QA：`py_compile` 5 個修改 Python 檔、三組 availability source／SQLite provider／merge tests **59 passed**、3 個 production modules scoped mypy clean。首輪 pytest 暫存位置造成 sandbox rename 權限失敗；第二輪 basetemp 路徑過長；改用 repo 內短隔離路徑後相同測試通過，未放寬斷言。最終 Job：開始前可用 RAM 23,926,648,832 bytes、8 GiB／12 process limits 讀回成功、kill-on-close Job 已附加、child exit 0 且關閉後 PID 不存在。Raw log `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\mops-monthly-target-source-version-20261026\stdout.log` SHA-256 `6b372c23384c283357aba05d98f1f0e9a2784557c549adc135a4b70bcfd19555`；QA receipt `receipt.json` SHA-256 `30eb0b6ae23597947690d3fda481ca5ad94f8d4454fd3c1d6dd5e54e685cbb10`。

## 目的與範圍

釐清受控 Evidence replay 顯示的 fundamental source qualification gaps：本機正式資料庫是否完全沒有相關資料，或是資料存在但品質／來源資格尚不足。這是一次唯讀盤點，不改資料、不接受來源、不提供 Gate credit，也不代表完整市場覆蓋。

來源為 `F:/Min/Python/Project/FA_Data/sqlite/twstock.db`。以 SQLite `mode=ro`、`PRAGMA query_only=ON` 開啟；在 Windows Job Object 中執行，8 GiB 記憶體上限、12 個 process 上限、單一驗證 lock。資料庫大小約 4.11 GB。此次盤點只輸出 schema、列數、日期範圍、quality/source/version 分布，沒有匯出公司資料列。

## 發現

### 2026-10-26 MOPS 季報公告時間的數值來源版本綁定

季度 availability mapping 新增可選 `target_source_version`；舊 CSV／非 MOPS mapping 可不提供，但 MOPS EZSearch 公告映射必須明確填入數值財報的 `source_version`。MOPS 公告 evidence 的 `source_version` 仍保留原有語義，不充當數值版；同一公司／報表／期間的 MOPS 修訂若綁到不同數值版，loader 拒絕猜測。Parser 僅在 target 與當次數值輸入 `source_version` 完全相等時才套用日期，否則輸出可定位的版本診斷並阻止 backfill apply。這是防止自然鍵誤貼時間的程式護欄，不證明 target 本身的 row-level filing identity，也不填造 MOPS event→財報內容 hash 橋。

受控 Windows Job 驗證：`py_compile` 四個修改後季報 Python 模組通過；`tests/test_fundamental_statement_availability_sources.py`、`tests/test_fundamental_statement_data.py`、`tests/test_fundamental_statement_backfill.py`、`tests/test_fundamental_statement_availability_entrypoint.py` 共 **29 passed**。啟動前可用 RAM 28,814,909,440 bytes；Job 上限 8 GiB／12 processes、kill-on-close；7 個累計程序自然退出、Job active processes 0、exit 0，無強制回收。pytest basetemp 使用本任務隔離可寫路徑，沒有改測試斷言。完整 pytest console log 保存在隔離工作目錄 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\statement_tests.log`。首輪 temp-root 被 sandbox 拒絕的單一 rename 失敗以指定可寫 basetemp 重跑後消除；測試本身未放寬。

對 2330／2026-Q2，正式 `fundamental_statement_items` 仍為 0 個目標列；公告事件、官方 PDF 與本機 numeric snapshot 的內容 hash custody 尚未唯一橋接，因此本次不產生可解除列數、不改正式 DB、不授予 Gate／PIT 資格。版本字串相等只驗明確綁定契約，不能取代 row-level filing identity／內容 hash 對照。

| Table | Rows | 日期範圍／最新值 | Quality 與來源摘要 |
|---|---:|---|---|
| `fundamental_monthly_revenues` | 246,331 | available date 2026-06-17 至 2026-07-15；as-of date 最晚 2026-06-30 | `degraded` 242,651（98.5%）、`observed` 3,680；單一來源 `mops.monthly_revenue_static_snapshot`；3 個 source versions。degraded 242,651 列全都缺 `announced_date`，集中在 2026-06-16 snapshot；3,680 個 observed 列都有公告日。 |
| `fundamental_statement_items` | 1,645,555 | available date 僅 2026-06-17；as-of date 最晚 2024-03-31 | 1,645,555 全為 `degraded`，公告日全缺；3 個 CSV source families；單一 source version `financial-data-statements-2026-06-17` |
| `fundamental_current_observations` | 319,893 | as-of date 最晚 2026-06-30；觀測時間最晚 2026-10-04 | 多個 MOPS／TWSE／TPEx endpoint 及靜態快照來源；`aggregate_feature_eligible=1` 為 0 列。`basis_verified=1` 有 140,300 列、其餘 179,593 列未驗證；此表沒有 `quality` 欄，不能由 row count 推定 qualified。 |
| `fundamental_valuation_metrics` | 1,671 | available/as-of date 最晚 2026-08-06 | 1,671 筆均為 `observed`，來源為 `daily_prices.pe`；僅此欄位概況不能證明授權、覆蓋或 PIT 合格 |
| `decision_desk_snapshots` | 58 | 2026-07-30 至 2026-10-23 | 有近期保存的 Decision Desk snapshots；本次未解讀 snapshot 內容或對其品質重新評分 |

資料庫內本次篩選到 5 張表，沒有名稱符合 `%watchlist%` 的表。`meta_data/fundamental_statement_availability.csv` 不存在。這只表示這個 SQLite 與指定路徑沒有該表／檔案；Watchlist 可能由獨立個人資料庫供應，不能據此宣稱產品 Watchlist 為空。

根因已能由程式與資料交叉核對：月營收與季報的舊 quality projector 都只在 `announced_date` 存在時標 `observed`，缺失就標 `degraded`。本機月營收可用日檔只有 1,832 個 key，與 242,651 個 degraded 月營收 key 沒有重疊；它只覆蓋已有公告日的新版本。舊財報 CSV 最後修改在 2024-04-17 UTC，季報 availability 對照檔不存在。不能用 period end、batch date 或 current `available_date` 偽造公告日。

另以當前 Decision Desk snapshot 的品質／狀態分組，只讀讀回 active snapshots：49 個 `degraded`、7 個 `estimated`（日期截至 2026-10-23）；這佐證資料資格缺漏已影響每日結果呈現。此項只讀 group count，未重算 snapshot 的 underlying inputs。

## 判讀與下一步

實際原始資料量不為零；目前真正問題是大量資料被標記為 `degraded`、可核對的來源可用日期偏舊，且來源接受所需的授權、來源契約、PIT 語義與市場／期間 coverage 證據尚未完成。Evidence Review 顯示「qualification gap」並不等於資料表空白；反過來，資料表有列也不等於來源可以進入策略或 Gate。

Decision Desk 的季報列現可把公告日缺漏筆數直接列出；月營收來源列也會顯示公告日缺漏數。這是根因揭露，不是把日期補成 observed。`fundamental_current_observations` 現有 319,893 列也全部未標 aggregate eligible，代表「目前有觀測值」與「已可進入 aggregate factors」是兩件事。

建議依序完成：

1. 對每個 source version 追查 `degraded` 的原始原因與其建立流程，先找出可安全重建的欄位／批次；不要批次改標成 `observed`。
2. 補上來源、授權／使用條款、可用日與 PIT、coverage 的可核驗原件，分來源、分用途接受。
3. 對更新後的資料重算 freshness、缺漏、唯一鍵衝突及各市場／期間 coverage；本次盤點未做完整鍵衝突或覆蓋分析。
4. 從產品目前實際使用的 Watchlist store 獨立盤點 pool 與欄位品質，並確認 Risk Prompt 各輸入的品質來源。
5. 在 Evidence Review 產品卡上分清「無原始資料」「資料存在但 degraded／stale」「資格證據未齊」三種狀態，再讓真人 reviewer 依 gate policy 判斷。

### 限制

- 日期與列數是 2026-10-25 當次本機資料庫的觀察，不保證此後未變。
- 未驗證來源授權、原始公告／價格原件、逐市場 universe coverage、資料數值正確性或每個下游用途的 eligibility。
- 本次沒有做完整 duplicate/key-collision、欄位缺漏與跨表 join 分析；schema 的 primary key 宣告不等於資料事實已獨立檢核。
- 伴隨的 notebook `baldr_data_quality_inventory_20261025.ipynb` 保存在本機 visualization 工作區；因專案 `.venv` 沒有 `nbconvert`／`nbclient`／`nbformat`，notebook 尚未由 Jupyter 執行。上表來自同一唯讀資料源、以受限 runner 執行的 SQL profile，查詢記錄保存在本機 scratch；notebook JSON 已讀回，但不視為已執行 notebook。

## Follow-up：決策台季財報可見性

Decision Desk 現有的唯讀市場資料可見性列新增 `fundamental_statement_items` 摘要：以 `available_date <= as_of_date` 且 `as_of_date <= as_of_date` 的資料列做 SQL aggregate，顯示列數、股票數、最新期間與最新可用日，並依原列 `quality` 標成 OBSERVED／DEGRADED。資格固定仍是 `research_only`，PIT 顯示未驗證，並明示 license／coverage／PIT 未由這個摘要驗收。此查詢不載入 164 萬列的數值 payload、不回填資料、不改下游決策。

- Market Data Visibility service 與 Decision Desk offscreen UI focused tests：公告日缺漏顯示切片 **61 passed**（3.69 秒），受 bounded Windows Job Object 執行。
- QA runner 啟動前可用記憶體 29.63 GiB；child 使用 8 GiB Job memory cap、12 process cap，正常退出，未強制清理。
- 正式本機 DB 的季報 SQL aggregate 讀回 1,645,555 列／1,567 檔、判為 `DEGRADED`／`research_only`，查詢耗時 0.607 秒；整個既有資料可見性 service 的當次 read 耗時 6.33 秒，沒有舊版基準，故不能把全部耗時歸因於這次新增查詢。
- 正式設定初始化因 sandbox 不允許建立 `output/application_state/logs/config.log`，退回 console-only；資料庫本身以唯讀方式成功開啟。
- 原生 GUI／正式資料庫互動耗時／Owner UAT：尚未執行。

### 2026-10-26 來源缺口呈現易讀性

Decision Desk「完整市場資料 → 資料可見性與擴充因子」改為每個來源分層顯示品質與列數、觀測／可得日期、PIT 可得時間狀態、資格，以及來源 warnings。已知 `historical_pit_unverified`、`observation_date_only`、`missing` 與 `research_only` 轉成繁體中文白話；未知狀態仍保留原值。下一步提示明列逐來源核對缺漏、可得時間、授權及覆蓋，並說明未核清前不拿來做歷史回測或 ML。呈現只讀既有 DTO，不新增資料或改 eligibility。

- `tests/test_ui_qt_decision_desk_view.py`：**53 passed**（3.54 秒）。
- `tests/test_ui_qt_update_view_workbench.py`：**93 passed**（3.87 秒）。
- `scripts/qa_validate_update_tab.py`：**25 passed／0 failed／4 skipped**；第一次預設輸出至 `output/qa/update_tab/RUN_LOG.txt` 被 Windows sandbox 拒絕，使用既有 `BALDR_UPDATE_TAB_QA_LOG_DIR` 改寫到隔離 scratch 後正常完成。跳過項目仍不計為通過。
- 修改的 view／test `py_compile` 通過；全域 mypy **1,145 個來源檔無錯**。pytest、validator、mypy 與 py_compile 均以 Windows Job 執行，readback 為 kill-on-close、8 GiB memory cap、12 process cap，執行後正常退出。
- `git diff --check` 通過。原生 GUI 目視與 Owner UAT 尚未執行；因此只確認 offscreen 回歸和程式靜態檢查，不能宣稱正常桌面視窗尺寸或真人操作已接受。
- Feature Map `change_patterns` 與 targeted document-control check（Feature Map、Snapshot、Operations index、output navigation registry／scope doc）通過，12 個功能入口映射無錯，目標文件 0 錨點／連結錯誤。舊 Snapshot 的精確 QA_RESULTS output 導航已加到既有 registry；只驗目標存在及路徑 metadata，未讀原件內容。其他文件的 output link 與全域 check 尚未清完。

## Official announcement evidence capture attempt

以既有唯讀 MOPS announcement collector 查詢 2026-Q2 TWSE／TPEx F26–F28 公告，分別保留原始成功 response custody 與 mapping，所有產物都在使用者 visualization scratch；沒有寫正式資料庫、沒有來源接受或 Gate credit。

- 初次 sandbox 擷取因 DNS `NameResolutionError` 產生 `unavailable` 收據；單一 31 天查詢則碰到 MOPS 1,000 列上限，因此不採用該次結果。
- 2026-07-01..31 以 7 天窗口擷取，24 個成功查詢、6 個官方明確無資料，產生 288 筆公告事件／projection row；0 failed、0 invalid，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_jul_candidate_20261025`。
- 2026-08-01..31 以 7 天窗口、一次 retry 重跑後 30/30 查詢成功，產生 5,724 筆公告事件／projection row；0 failed、0 invalid、0 duplicate，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_retry1_20261025`。
- 2026-09-01..30 同樣以 7 天窗口擷取，27 個成功查詢、3 個官方明確無資料，取得 123 筆事件／projection row；0 failed、0 invalid，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_sep_candidate_20261025`。
- 2026-10-01..05 六個查詢均為官方明確無資料，沒有公告事件；工具依來源狀態輸出 `unavailable` 候選，不能解讀為查詢失敗或缺漏資料。候選目錄：`mops_statement_availability_q2_2026_oct_candidate_20261025`。

以上仍是隔離研究候選：`formal_oos_allowed=false`、`formal_credit_authorized=false`、`production_blend_alpha_bp=0`。公告候選不能單獨證明舊報表內容正確、完整 coverage 或授權，也未執行正式回填。將 8、9 月 mapping 按 response hash 回連 query manifest 的市場，再按市場／股票／報表種類對照本機 `fundamental_current_observations` 的 2026-Q2 current statement keys，唯讀結果如下：

| Market | Statement type | Current keys | Candidate keys | Matched | Current without event | Candidate without current row |
|---|---|---:|---:|---:|---:|---:|
| TWSE | balance sheet / income / cash flows（各類相同） | 1,084 | 1,096 | 1,084 | 0 | 12 |
| TPEx | balance sheet / income / cash flows（各類相同） | 891 | 888 | 885 | 6 | 3 |

合計 1,975 個 MOPS current HTML 子集股票身份中，1,969 檔有 7–9 月候選公告，仍有 6 檔 TPEx 股票未命中；TWSE 1,084 檔全數命中。另有 15 個候選股票代碼（TWSE 12、TPEx 3）沒有該子集的本機 Q2 對應列。差異對三種報表類型一致。這個比對只涵蓋 2026-07-01..09-30 公告查詢窗及 2026-06-30 的 MOPS current HTML 子集，不代表 MOPS 全市場／其他期間完整 coverage，也未驗證報表值、授權、歷史 PIT 或正式 `fundamental_statement_items` 的逐列正確性。這些結果應留在研究／Gate 3 人工審查，不得因公告匹配就批次補回正式資料。

### 來源授權邊界與後續採集路徑

2026-10-25 重新查核官方條款後，現有 MOPS EZSearch 自動採集路徑的授權範圍仍未證實。證交所網站使用條款第 6 節限制未經同意的自動化下載，第 8 節將已授權政府資料開放平台提供的資料列為例外；條款文字是否適用到獨立的 `mopsov.twse.com.tw` EZSearch 端點，現有證據不能裁定。因此：

- 當時的處置是先不擴大自動擷取，直到取得明確授權或官方文件。此「條款未裁定即停止研究取用」的工程阻擋，已由 2026-10-28 Owner 指示覆寫；不得再將授權未核單獨作為停止其明確要求之公開資料研究取用的理由。歷史決策保留作為當時狀態，不改寫其時序。
- 政府資料開放平台逐一列出的資料集具有自己的授權與下載資源。2026-10-25 查到下列四個一般業季度資料集皆列政府資料開放授權條款第 1 版、免費，並從各自的「資料資源下載網址」核出明列 CSV URL：

| 市場／報表 | 開放資料集 | 目錄列出的 CSV 資源 |
|---|---|---|
| TWSE 資產負債表 | [94831](https://data.gov.tw/dataset/94831) | `https://mopsfin.twse.com.tw/opendata/t187ap07_L_ci.csv` |
| TWSE 綜合損益表 | [91998](https://data.gov.tw/dataset/91998) | `https://mopsfin.twse.com.tw/opendata/t187ap06_L_ci.csv` |
| TPEx 資產負債表 | [91967](https://data.gov.tw/dataset/91967) | `https://mopsfin.twse.com.tw/opendata/t187ap07_O_ci.csv` |
| TPEx 綜合損益表 | [94853](https://data.gov.tw/dataset/94853) | `https://mopsfin.twse.com.tw/opendata/t187ap06_O_ci.csv` |

這項明列授權只支援以上資料集及其目錄資源的評估／採集，不能推廣成所有 MOPS／OpenAPI 端點的通用授權。這四份資源只代表一般業，不能代表其他產業或全市場財報；欄位雖有「出表日期」，官方目錄沒有說明它等同逐筆首次公告或可得時間，一般金額單位亦未確認。因此下一步可從這四個明列 CSV 做隔離候選並保留原始 bytes／hash／response metadata，再逐項核 schema、更新時點、單位、coverage 和修訂語意；它們仍不得自動進正式 DB、PIT 或 Gate。
- 既有季度 OpenAPI collector 曾完成 24 個數值 endpoint 的隔離研究擷取，原始回應與 review items 已有 2026-10-01 QA 紀錄。該批資料標記一般金額 `unit_unknown`、`available_at=null`，含 8 個未納入 preview 的 key/schema review 列，且不含現金流量表／權益變動表；不能因此視為完整季度來源或正式可用。不得將 OpenAPI 端點改名或合併成 MOPS EZSearch。

本節記錄目前可核驗的來源範圍與工程採集守則，不作法律裁定。官方依據：[TWSE 使用條款](https://wwwc.twse.com.tw/zh/terms/use.html)；[data.gov.tw 18420](https://data.gov.tw/dataset/18420)。

### 2026-10-28 Owner 覆寫研究取用阻擋

Owner 指示為個人研究取得公開可讀資料，並表示網站條款不適用於其研究且不打算遵守。自本日期起，條款／自動化授權未裁定不得單獨阻止 Owner 明確要求的公開 MOPS／TWSE／TPEx 資料研究取用；過去「待取得端點授權才可擴大擷取」的工程停止條件已覆寫。這是 Owner 的立場與執行指示，不是法律適用性的獨立結論，也不把來源狀態標為已接受。

後續取得仍需由正常公開頁面／端點存取，保存 URL、時間、原始 response／bytes／SHA 與來源版本；不繞過登入、CAPTCHA 或技術存取控制。MOPS 顯示的公告日期／時間依 Owner 既有決定可作公告 timestamp，但事件仍須與目標數值版本精確連結。擷取不等於正式 DB 回填、單位／幣別核實、修訂橋、歷史 PIT 或 Gate 資格。此紀錄本身不執行擷取；既有 2026-10-27 唯讀盤點的數字及收據維持原貌。

### 2026-10-26 開放資料季報 CSV 候選與 coverage 對照

使用政府開放平台各資料集頁面明列的 CSV 資源 URL，對四個一般業季報資源各執行一次 GET。四個回應均 HTTP 200，原始 bytes 寫入隔離 scratch 並逐檔 SHA-256 readback；CSV 可解析，沒有正式 DB 寫入、source acceptance 或 Gate credit。原始候選、manifest 與內容稽核位於：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-quarterly-csv-candidate-20261026retry1/`

| 市場／報表 | data.gov.tw dataset | 列數／唯一代碼 | 期別 | 出表日期 | 原始 bytes | SHA-256 |
|---|---|---:|---|---|---:|---|
| TWSE 資產負債表 | [94831](https://data.gov.tw/dataset/94831) | 1,051 | 115-Q2 | 1151026 | 257,355 | `96cd65e1c5ad1251772bbcf3fae3491c0ce1a60e29a8f2e63f989fd9b99196eb` |
| TWSE 綜合損益表 | [91998](https://data.gov.tw/dataset/91998) | 1,051 | 115-Q2 | 1151026 | 287,750 | `c89fc3db5db5850af8867b81ef12fb53c905facdf0d98d2e7fe51176492c1233` |
| TPEx 資產負債表 | [91967](https://data.gov.tw/dataset/91967) | 888 | 115-Q2 | 1151026 | 207,730 | `94e23dfa43d8accf62dea0d339f924d484d0ee93db9146e3d521dcb53aa7280c` |
| TPEx 綜合損益表 | [94853](https://data.gov.tw/dataset/94853) | 888 | 115-Q2 | 1151026 | 231,938 | `690ee762106602db2b0e3a1d431ba836ed0cea4c039ebdda1f65413843d0fb62` |

四檔 CSV 的公司代碼及 `(公司代號, 年度, 季別)` 都沒有重複；同市場資產負債表與綜損的代碼集合相同。每列欄位數與 header 相符，沒有額外欄或短列。欄位中有大量空字串，但沒有 `-`／`--`／`N/A` 等字面 placeholder；空值究竟代表不適用、未揭露或資料缺漏，官方語意仍未知，不將它轉成 0。四檔都有 `出表日期`，該欄逐列為 1151026；它只證明這次輸出所標的日期，不證明逐筆首次公告／可得時間或修訂歷史。一般金額單位、財報 basis 與歷史 PIT 仍未核定。

另以政府開放平台列出的上市／上櫃公司基本資料資源建立近時點目錄候選：TWSE [18419](https://data.gov.tw/dataset/18419) 有 1,097 個唯一代碼，TPEx [25036](https://data.gov.tw/dataset/25036) 有 894 個唯一代碼，兩檔出表日期皆為 1151025；bytes/hash 及 readback 收據在：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-company-directory-candidate-20261026/`

目錄比一般業 CSV 晚／早一日的觀測差，故不是完全同日分母。以目錄 `產業別` 欄做集合對照：TWSE 有 46 個目錄代碼不在一般業 CSV（其中產業碼 17 有 31、91 有 10，其他碼合計 5），一般業 CSV 代碼全都在目錄中；TPEx 有 8 個目錄代碼不在一般業 CSV（產業碼 17 有 7、26 有 1），另有兩個 CSV 代碼 `6898`、`6938` 不在前一日目錄。這些差異尚未按全部產業的季報資源及歷史上市狀態裁定，不能宣稱已完整覆蓋或視為來源錯誤。

再與本機 `fundamental_current_observations` 的 2026-Q2、`as_of_date=2026-06-30` MOPS current-HTML 子集唯讀對照：TWSE 子集 1,084 檔中 1,049 檔命中一般業 CSV（35 檔不在一般業集合）；TPEx 子集 891 檔中 883 檔命中（8 檔不在一般業集合）。反向有 2 檔 TWSE、5 檔 TPEx 一般業 CSV 公司代碼沒有該本機子集列。此子集不是正式 issuer denominator，且其觀測時間早於兩份新候選；結果只用來定位差異，不用來判定缺漏、接受來源或補正式資料。

### 2026-10-26 全產業季度 CSV 候選補採與 issuer 對照

依政府資料開放平台各資料集頁面所列資源 URL，追加擷取 19 個非一般業季度 CSV；每項均單次 GET、禁止自動跟隨 redirect、每個 response 上限 32 MiB，原始 body 寫入 scratch 並逐檔 hash/readback。19/19 回 HTTP 200 且原始 bytes 與 readback SHA-256 一致；沒有正式 DB 寫入、來源接受或 Gate credit。完整 manifest、原始檔與集合對照：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-industry-quarterly-candidate-20261026/`

TWSE 共採資產負債表／綜合損益表各五個產業資源；TPEx 採目錄列出的資產負債表四個及綜合損益表五個產業資源。各市場同一產業的兩種報表有效代碼集合相符：

| 市場／產業 | 季報目錄資產負債表／損益表 dataset | 各表有效代碼 | 觀察 |
|---|---|---:|---|
| TWSE 銀行業 | [94829](https://data.gov.tw/dataset/94829)／[91995](https://data.gov.tw/dataset/91995) | 10 | 115-Q2，出表日 1151026 |
| TWSE 證券期貨業 | [94830](https://data.gov.tw/dataset/94830)／[91996](https://data.gov.tw/dataset/91996) | 3 | 115-Q2，出表日 1151026 |
| TWSE 金控業 | [94832](https://data.gov.tw/dataset/94832)／[91999](https://data.gov.tw/dataset/91999) | 13 | 115-Q2，出表日 1151026 |
| TWSE 保險業 | [94833](https://data.gov.tw/dataset/94833)／[92000](https://data.gov.tw/dataset/92000) | 5 | 115-Q2，出表日 1151026 |
| TWSE 異業 | [94834](https://data.gov.tw/dataset/94834)／[92001](https://data.gov.tw/dataset/92001) | 4 | 115-Q2，出表日 1151026 |
| TPEx 銀行業 | [91965](https://data.gov.tw/dataset/91965)／[94850](https://data.gov.tw/dataset/94850) | 0 | HTTP 200，但沒有有效代碼／年度／季別列 |
| TPEx 證券期貨業 | [91966](https://data.gov.tw/dataset/91966)／[94852](https://data.gov.tw/dataset/94852) | 7 | 115-Q2，出表日 1151026 |
| TPEx 金控業 | [91968](https://data.gov.tw/dataset/91968)／[94854](https://data.gov.tw/dataset/94854) | 0 | HTTP 200，回應僅 78 bytes 表頭／空列 |
| TPEx 保險業 | 無另列資產負債表資源（[94867](https://data.gov.tw/dataset/94867) 保險資料集欄位只見損益項目）／[94855](https://data.gov.tw/dataset/94855) | 0 | 損益資源列為不定期更新；本次沒有有效代碼／年度／季別列 |
| TPEx 異業 | [91970](https://data.gov.tw/dataset/91970)／[94856](https://data.gov.tw/dataset/94856) | 0 | HTTP 200，回應僅 78 bytes 表頭／空列 |

所有非空產業表均只有 115-Q2、出表日 1151026；各檔有效 issuer 代碼無重複。TPEx 空回應只證明本次 response 沒有有效季報列，不能推論產業「沒有公司」或來源已完整。保險業損益目錄頁標示不定期更新；其餘新增目錄頁列政府資料開放授權條款第 1 版／免費與每三月更新。資料集主要欄位清單列出欄名，未提供財報金額單位或合併／個別 basis 說明；例如[一般業](https://data.gov.tw/dataset/94831)與[金融業](https://data.gov.tw/dataset/94829)頁只在股數欄明列「單位：股」，金額單位仍不能由數值推斷。以上授權只支持這些明列資源的研究採集。

對四個一般業與 19 個產業資源再做結構剖析：16 個檔案有有效財報列，合計 3,962 個「報表 × 公司」列；`(公司代號, 年度, 季別)` 重複鍵為 0，觀察欄位的空白值為 31,077／97,708（31.8%），檢查的 `-`、`--`、`N/A`、`NA`、`null`、`NULL` 文字 placeholder 為 0。3,962 是跨報表列數，不是唯一公司數；31.8% 空白可能是格式／適用性／缺漏，官方語意未明，不補零。欄位數在不同報表／產業間從 5 到 64 欄不等，需建立逐報表欄位與單位映射，不能直接拼成一張同質資料表。稽核結果在同一候選目錄 `content_audit_all_quarterly.json`；原始 response、readback hash 與逐來源資料集 ID 在 `capture_manifest.json`。

以 1151025 的 TWSE／TPEx 公司目錄作近時點分母，將四份一般業資源和本次有效產業列去重後：

- TWSE：季報資源聯集 1,086 代碼；目錄 1,097 代碼中 11 個不在該聯集。普通產業代碼 `1589` 的缺列已由官方交易所公告解釋為未依限申報 115 年第一、二季財報；此為官方非申報，不是抓取失敗，也不是資料完整，必須保留缺件／降級狀態。另十個未命中代碼均為目錄產業別 91，原因仍待查。不能因剩餘差異看似小就接受完整 coverage。
- TPEx：季報資源聯集 895 代碼；目錄 894 代碼中 `3718` 不在季報聯集，季報候選另有 `6898`、`6938` 不在前一日目錄。官方公告說明 `3718` 是由 `5371` 中強光電轉換成立的新控股公司，轉換生效日為 2026-09-03，`5371` 自 2026-08-24 停止上櫃交易；因此 `3718` 不是 2026-Q2 季末 issuer。候選 Q2 CSV 也未含 `3718` 或 `5371`。此差異要求以歷史 issuer universe／公司沿革對照並查核前身的 Q2 申報狀態，不能把當前目錄直接當作 Q2 分母，也不能判成 `3718` 漏報。
- 目錄與季度 CSV 的出表日相差一天；這是近時點對照，不是相同觀測時點的正式 denominator。公司目錄也不提供歷史上市狀態或季度財報義務判斷。完整差異代碼與每個檔案 hash 在上述 scratch `scope_reconciliation.json` 與 `capture_manifest.json`。

此補採縮小了「一般業以外都未核對」的未知範圍，但仍未完成來源契約：`出表日期` 不等於逐筆首次公告／available-at；單位、合併／個別 basis、空值語意、修訂歷史、歷史 PIT、產業母體與其餘目錄差異都未解決。候選不得匯入正式 DB，不授予 Gate 3／來源接受或 ML 訓練資格。

### 2026-10-26 issuer 例外查核

- `1589`：TWSE 官方[公告](https://accessibility.twse.com.tw/zh/announcement/announcement/detail.html?id=C4DFB886C2F211F19A80005056BE3760)指出永冠-KY未依限申報 115 年第一、二季財務報告，並公告其上市有價證券預計於 115-11-18 終止上市。該公告足以解釋本次 Q2 CSV 未見該代碼；資料缺件仍須呈現為非申報／降級，不能推估、補零或把來源宣稱為完整。
- `3718`／`5371`：TPEx 官方[公司轉換公告](https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html)記載 `5371` 轉換為新設控股公司 `3718`，於 2026-09-03 生效，`5371` 自 2026-08-24 停止上櫃交易。當前公司目錄含 `3718` 不代表其應出現在 2026-Q2 季末母體；目前 Q2 CSV 候選兩碼皆無，仍需按歷史 issuer 身分核實 `5371` 的 Q2 財報及來源歷史涵蓋。這不是來源接受或 coverage 通過證據。

本次官方查核只把兩個代碼差異分類得更準確；TWSE 其餘十個目錄代碼、TPEx `6898`／`6938` 的時間／母體差異，以及 issuer 沿革完整交叉表仍未解決。沒有正式資料寫入、Gate credit 或 ML 資格變更。

### 2026-10-26 官方目錄欄位契約查核

抽查 TWSE 一般業及金融業資產負債表[資料集 94831](https://data.gov.tw/dataset/94831)、[資料集 94829](https://data.gov.tw/dataset/94829)：目錄列有年度、季別、公司代號與財報欄位，標示每三月更新、免費及政府資料開放授權條款第 1 版；股數欄有標明「單位：股」，但目錄沒有說明財報金額單位，也沒有清楚宣告合併／個別 basis。94831 詮釋資料更新時間為 2023-07-25，94829 為 2026-06-30，這些是目錄 metadata 時間，不能當成逐列可得時間。

目前隔離候選每檔的有效列都只有同一個 `出表日期=1151026`；原件 HTTP `Last-Modified` 是整份 CSV 的 response metadata。兩者都不能證明每家公司每個欄位的首次公告時間或後續修訂時序。這一批只有單次 current snapshot，沒有歷史版本可比較，因此無法由候選自身產生 row-level available-at、修訂鏈或 point-in-time 歷史。這些是來源契約缺口，不以 `出表日期`、HTTP `Last-Modified` 或當前值推定；若找不到有授權的歷史原件／公告時間來源，該來源仍不得拿來作歷史回測或 ML 特徵。

### 2026-10-27 2330／2026-Q2 資產負債表 13 列精確交叉核對

為縮小 T164／PDF／官方開放資料之間的數值差異，以隔離 T164 v2 candidate（SHA-256 `bab76dfa071973209d0d99d2713165287d63a9426b3d18da209392daad948699`）、TWSE 一般業季報 CSV 資料集 [94831](https://data.gov.tw/dataset/94831)（原始檔 SHA-256 `96cd65e1c5ad1251772bbcf3fae3491c0ce1a60e29a8f2e63f989fd9b99196eb`）及 T57 列示的台積電 2026-Q2 合併財報進行唯讀比對。對 2330／民國 115 年第 2 季，依明確財報列碼與 OpenData 欄名對照 13 個合併資產負債表總額／權益項目，逐列以 Decimal 精確比較 **13/13 相同、0 不同**。另目視核對同一官方 PDF 位元組之第 4 頁：12 列列碼直接相符，候選列碼 3100 對應 PDF 列碼 3110；期末欄與新台幣仟元單位相符。PDF SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`；隔離頁面圖與逐列候選 row SHA、欄名及比對狀態索引保存在 `owned-validation/q2-statement-pages-20261027/q2_2330_balance_sheet_13_row_bridge.json`。

後續已完成 172 列候選對同一官方 PDF 的內容分類，但此 13 列交叉核對本身仍不是 XBRL／正式 source-version 身分證明。94831 只保存 `出表日期=1151026`，沒有公告時分、歷史修訂或候選 numeric source version；其單次 current snapshot 不證明 PIT 歷史。正式 `fundamental_statement_items` 仍無 2026-Q2 列，`fundamental_current_observations` 的多個 source versions 仍未唯一認領。現未寫正式 DB、未接受來源或授 Gate／ML credit；因此正式品質解除仍 **0 列**。172 列分類摘要及剩餘列語義問題見下方整合對照。

<a id="2026-10-27-2330-2026-q2-損益表-37-列-pdf-內容對照"></a>

### 2026-10-27 2330／2026-Q2 損益表 37 列 PDF 內容對照

以同一 T164 v2 候選 `gate3-event-numeric-bridge-final/candidate.json`（SHA-256 `bab76dfa071973209d0d99d2713165287d63a9426b3d18da209392daad948699`；source version `mops-t164-consolidated-statements-with-t57sb01-xbrl-row-codes.v2`）逐列比對相同 bytes 核實的台積電官方 2026-Q2 合併財報 PDF 第 5–6 頁（PDF SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`）。影像列有 2026-04-01 至 06-30 單季欄、比較期間欄與年初至今累計欄，單位標示為新台幣仟元（EPS 為元）。逐列結果為：**37 列中 33 列的列碼、標籤與單季數值可直接目視相符**；1 列（候選 7010）與 PDF 列碼 7190 的標籤／數值相符但列碼不同；1 列（候選 7020）與 PDF 7020、7230 兩列合計相符，屬明細粒度差異；1 列（候選 8317）候選為零、PDF 以破折號呈現；1 列（候選 5900）在 PDF 沒有獨立列，與 5950 重複同一毛利金額。因此此 37 列沒有未能調節的金額差異，但後四類不能標成直接逐列 exact match。隔離狀態表為 `owned-validation/q2-statement-pages-20261027/q2_2330_income_statement_37_row_pdf_bridge.json`，記錄候選、PDF、頁面影像及 TWSE income CSV hashes，未輸出財務數值。

TWSE 開放資料 dataset 91998 的 `2330／115／Q2` current snapshot 有 1 列，但沒有同檔 Q1 基準列；資料集也未定義這些金額欄的單位或 Q2 是單季／累計。故沒有用 Q2−Q1 推導候選單季值，也沒有將 OpenData 當作 37 列的獨立數值核對。另以 SQLite `mode=ro`、`PRAGMA query_only=ON` 即時讀回正式 `fundamental_current_observations` 的 2330／2026-Q2 身分欄（未選取財務數值）：161 列分屬 11 個 `source_version`，來源／statement／unit／basis 展開為 23 組；所有組的 `aggregate_feature_eligible=0`。查詢前後 DB／WAL／SHM 大小與 mtime 完全相同。故 PDF 的內容佐證改善了 T164 candidate 的 filing 內容確認，但仍不能把它唯一橋接至 11 個正式版本；正式 `fundamental_statement_items` 仍 0 列。只讀查詢 bounded receipt 在 `owned-validation/q2-formal-version-readonly-20261027/receipt.json`。未寫正式 DB、未接受來源、未解除品質缺漏或授 Gate 3／PIT／ML credit；正式解除仍 **0 列**。完整 37 列狀態清單在上述隔離 JSON，原始影像 `statement-05.png`／`statement-06.png` 亦在同目錄。

<a id="2026-10-27-2330-2026-q2-現金流量表-78-列-pdf-對照"></a>

### 2026-10-27 2330／2026-Q2 現金流量表 78 列 PDF 對照

T164 v2 consolidated candidate 的 78 列全是 2026-01-01 至 06-30 `year_to_date`，與同位元組核實的官方 PDF 第 8–10 頁當期 YTD 欄一致；PDF 明示新台幣仟元。以候選列名／金額對三頁逐列檢視後，64 列直接相符；B07600 一列候選合併 PDF 兩列股利、A23700／B01500 兩列候選零值在 PDF 顯示破折號、A00010 加五個調整項／資產負債變動小計（A20010、A31000、A32000、A30000、A20000）及 E00210 共 7 列沒有獨立對應列。A32230、A32990、B09900 三列仍無法確認一對一 mapping。C01200 候選金額等於 PDF 分列列示的公司債發行總額扣除發行成本；算術可調節，但候選與 PDF 對成本的會計呈現語義尚未證實，因此仍列未解，不能稱為直接相符或四捨五入。全 78 列狀態和候選／PDF／頁面 SHA-256 在 `owned-validation/q2-statement-pages-20261027/q2_2330_cashflow_78_row_pdf_bridge.json`，沒有輸出財務數值。

這是內容核對，不足以認領正式數值版本：formal observations 的三個現金流 source versions 均各有 7 個 YTD summary row，與候選同標籤列作 TWD／scale 1,000 Decimal 對照後各為 7/7 exact，但三個版本都相同，故無法據此選出唯一 `source_version`。正式表列 `period_basis=unknown`、`aggregate_feature_eligible=0`；C01200 的 gross/net presentation semantics 仍未解。`fundamental_statement_items` 仍 0 列，未寫正式 DB、未接受來源、Gate 3／PIT／ML 未升格；本次正式品質解除 **0 列**。只讀 Decimal 比對輸出及 bounded receipt 位於 `owned-validation/q2-formal-content-bridge-readonly-retry1-20261027/`。

<a id="2026-10-27-2330-2026-q2-t164-v2-172-row-pdf-classification"></a>

### 2026-10-27 2330／2026-Q2 T164 v2 全 172 列 PDF 內容分類

以同一 T164 v2 candidate（SHA-256 `bab76dfa071973209d0d99d2713165287d63a9426b3d18da209392daad948699`）和官方 PDF（SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`）合併三張報表的逐列橋，172 列均已有明確內容分類：**147 列直接相符、2 列列碼別名、5 列 PDF 多行合計、4 列候選零值／PDF 破折號、10 列 PDF 無獨立列、4 列仍未解**。資產負債表 57 列為 50 直接、1 別名、3 合計、1 零／破折號、2 無獨立列；損益表 37 列為 33 直接、1 別名、1 合計、1 零／破折號、1 無獨立列；現金流量表 78 列為 64 直接、1 合計、2 零／破折號、7 無獨立列、4 未解。

四個未解代碼為現金流量表 A32230、A32990、B09900、C01200。MOPS T164 XBRL 原件（SHA-256 `0a4924d8260707efc363b14bae7ff94d8d98fcae6b32431b18caaa69c0d632ab`）確認前三列概念分別為「其他流動負債增減調整」、「其他營業負債增減」及「其他投資活動現金流入／流出」；但 PDF 第 8 頁的「應付費用及其他流動負債」是合併標題，無證據可分配 A32230／A32990；第 9 頁沒有獨立「其他投資活動」列，也沒有來源提供列碼到 PDF 呈現的橋。C01200 算術上等於 PDF 公司債發行總額扣除分列發行成本，但 gross/net 呈現語義未核實。以上三列不得按金額猜分或自動合併。分類狀態總表位於隔離檔 `owned-validation/q2-statement-pages-20261027/q2_2330_t164_v2_172_row_pdf_bridge_summary.json`，SHA-256 `629cb98965a791e4f56d2161508e6d6f35e085eddae95bf6ccf9ce52155e755e`；其中不含財務儲存格數值。此結果完成候選對 PDF 的內容分類，**不代表 172 列正式 source-version bridge 已完成**：正式 observations 仍有多個來源版本且無唯一認領，`fundamental_statement_items` 仍 0 列，來源接受／正式資料寫入／quality 解除／Gate 3／PIT／ML credit 仍為 0。

現有 `scripts/backfill_fundamental_statement_items.py` writer 只接受 legacy raw CSV 與 availability CSV；其正式表 schema 不保存 T164 candidate 的 unit／scale、period basis、XBRL 概念／row hash 或逐列 PDF 對照狀態，品質 projector 只要有 announced date 即會標為 observed。因此不可直接將這份 JSON 送入 legacy backfill，也不可把公告時間有值當作 172 列均可放行。要正式 materialize，需有保留 source lineage／列級 disposition 的專用資料契約與 writer，並把 MOPS 數值版本綁到正式 availability artifact；再補 per-use P0 source dossier 所需的 license、coverage、missing policy 與影子驗收證據。Owner 已授權的公告 timestamp 語義只解決 event timestamp 欄位，不會生成上述缺少的外部證據。

另查官方[MOPS 財務資訊服務使用說明](https://mopsfin.twse.com.tw/terms)：該頁描述 IFRS 財務資料範圍及每日更新、與 MOPS 申報資料約一日時間差，並說明來源為 MOPS；但它是財務資訊服務說明，頁面沒有列出可直接套用到 EZSearch／T164 endpoint 的重製、儲存或再散布授權條款。因此只用來佐證服務範圍與延遲，不把公開可瀏覽或此頁當作本候選的 license acceptance 證據。

#### 2026-10-28 PDF disposition bundle 完整性重驗

新增 `scripts/validate_mops_t164_pdf_disposition.py`，用候選 JSON、四份列級 bridge、整合摘要及官方 PDF bytes 驗證候選／PDF hash、既有 MOPS consumer adapter 的單位／期間／時間語意、報表 identity、172 個唯一 item code 的逐列完整覆蓋，以及 statement／分類計數與未解代碼。對原 bridge 中 4 個少一字元的 PDF hash 引用，驗證器不改原檔；它讀取保存的 issuer PDF bytes，算得 SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`，再將舊引用記為 `single_character_omission`。第 5 份 13 列 Open Data bridge 的 PDF hash 已與實際 bytes 完全一致。候選、PDF、bridge 與摘要原件保持不變。

逐列 accounting 驗證 **172／172**，分類計數與原摘要一致：147 direct、2 code alias、5 aggregate、4 zero vs dash、10 no independent PDF row、4 unresolved；未解仍是 A32230、A32990、B09900、C01200。隔離 integrity report 位於 `owned-validation/q2-statement-pages-20261027/q2_2330_t164_v2_pdf_disposition_integrity_verified_v2.json`，SHA-256 `7fdba99ce950a19e2af37c7fb5b1cc78ecf5adb046737355cb386fc6de21f264`；bounded receipt 位於 `owned-validation/mops-t164-disposition-live-contract-final-20261028/receipt.json`，SHA-256 `0e1d883091d2a841308cfa72e1c50e1050b9a141042f5672260e6ebe22fbe898`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 自然歸零且 handles 關閉。新增 bridge validator 的測試 **5 passed**，兩個新 Python 檔 `py_compile` 通過、針對兩檔 mypy clean。

這項重驗證明 hash binding 與候選 row accounting 完整；它沒有重新讀取 PDF 頁面內容，也沒有逐列 source row hash／財務值欄位可供 PDF JSON bridge 對照的 159 列。它不會自動修正原始 bridge、不產生來源接受或正式版本認領；正式 statement rows、正式品質解除、Gate 3／PIT／ML credit 仍 **0**。CLI report 只能寫新建 research output，會拒絕覆寫輸入或正式 DATA_ROOT。

下一步需要同一 filing 的正式列碼／概念到 PDF 展示對照、期間基礎／單位確認及正式來源版本唯一性證據，不將內容分類當作 Gate 通過。

### 2026-10-26 P0 季報逐資源／逐欄位唯讀稽核接線

P0「研究證據 → P0 Data Source Control Center」新增使用者明選候選目錄後的離線 CSV 稽核。一次只讀一個目錄；一般業與產業資源分別選取，不合併根目錄或資源。稽核支援目前兩種 capture manifest schema，核對 manifest 安全旗標、逐筆 HTTP／readback 收據、檔案 SHA-256、資源路徑與 CSV 結構，再按市場／報表／產業／資料集逐項呈現有效列、重複業務鍵、欄位空白／非空及精確已知 placeholder 計數。表格不輸出財務儲存格值；目錄選擇只在本次執行有效，啟動預設可由 `P0_QUARTERLY_CANDIDATE_ROOT` 設定。未連網、不匯入、不建立 DB／schema，也不把讀取結果保存成產品資料。

以現有封存的兩個 scratch 根目錄做唯讀重算：一般業 4/4 CSV 可解析，產業資源 12/19 可解析、7/19 是空回應，23 項中缺檔 0、驗證無效 0；可解析列共 3,962 個「報表 × 公司」財報列，`(公司代號, 年度, 季別)` 重複鍵 0。逐欄彙總 31,077 空白、66,631 非空（placeholder 已包含在非空內），檢查的 `-`、`--`、`N/A`、`NA`、`null`、`NULL` token 為 0。這些與前節原內容稽核結果一致；行數不是唯一公司總數或全市場 coverage，跨報表欄位合計也不是統一 schema。空白語意、未申報與不適用仍未知；`available` 在 UI 只譯為「候選檔可解析」，不表示資料源可用或接受。

在 P0 Source Control Center 的 PIT quarterly row 可查看稽核摘要；選資源可看原始財務欄位計數及實檔 SHA 完整提示。欄位表的 placeholder 是非空值子集，不應與非空相加。壞目錄會顯示明確 invalid 原因並維持 candidate-only 邊界。無論計數結果如何，`source_acceptance=false`、`gate_credit=false`、`downstream_eligibility=none`。最終驗證為稽核／來源中心／Research Console focused 105 passed、強制 Workbench 93 passed、Update validator 25 passed／0 failed／4 skipped、全域 mypy 1,148 檔 clean、8 個修改 Python 檔 `py_compile` 通過；Feature Map／code path 與 QA／架構文件 check 通過。Snapshot／Manual link check 仍被既有 `output` junction 的 WinError 5 阻擋，列出的都是舊 trial／task 輸出連結，沒有新稽核章節錯誤。原生桌面 Owner UAT 未執行；沒有改變來源接受、Gate 3、正式回測或 ML 狀態。兩個候選目錄 parser 完整 readback 摘要在 task scratch `quarterly-audit-qa/real-candidate-readback-v3.log`。

2026-10-26 增加逐公司／期別空白剖面、欄位空白率橫條及逐資源下一步指引：選取資源後可依公司代碼、名稱或期別篩選，按空白格數排序，並查看原始空白欄名、出表日期與 placeholder token 計數；公司名稱衝突會明示，不任選名稱。profile 只序列化鍵與計數、不含財務值，每資源最多輸出 5,000 個 key，另提供掃描數及截斷／完整旗標。欄位空白率按空白／(空白+非空) 計算並以無品質門檻色義的橫條展示；placeholder 留在非空分母中，無有效列時顯示 N/A。逐資源指引按可解析／空回應／缺檔／無效提供相應核查路徑；明確提示空回應不等於市場無申報，缺檔／無效修復需另建候選並保留原件。兩個原始候選重讀共輸出／掃描 3,962 個資源內 issuer-period profile（一般業 3,878、產業 84），沒有觸及上限或名稱衝突；profile 計數仍合計 31,077 空白、66,631 非空，與逐欄總數一致。這是資源內有完整 issuer／年度／季別鍵的 CSV 觀測，不是全市場分母；空白／placeholder 語意仍未定。最後驗證：focused suite 115 passed、WorkBench 93 passed、Update validator 25 passed／0 failed／4 skipped、全域 mypy 1,148 檔 clean、3 個修改 Python 檔 `py_compile` 通過、5 條相關程式／測試／QA／架構路徑文件檢查通過。原生 GUI／Owner UAT 與 Gate／ML 資格仍未完成。

### 2026-10-26 季報候選與公司名錄差異可見性

Research Evidence 的 P0 Source Control Center 新增獨立公司名錄候選選取器，呼叫端明選根目錄後，離線核對名錄 capture manifest 的 candidate-only 安全旗標、TWSE 18419／TPEx 25036 來源分母、GET／HTTP 200／未跟隨 redirect／readback 收據、檔案 bytes／SHA、CSV 代號／名稱／產業／出表日期欄及逐市場列數與唯一代號。名錄讀取沒有網路、DB、資料保存或自動套用；路徑只在當次 UI state 有效，`P0_ISSUER_DIRECTORY_CANDIDATE_ROOT` 可作啟動預設。

當季度 CSV 與名錄候選都通過驗證時，服務逐市場 union 目前已完整輸出的 issuer profile 與目錄代號，顯示兩邊都有、名錄有而目前候選未見、目前候選有而名錄未見；表格預設只看差異，可切換全部並依代號／名稱／產業碼篩選。對照明確限定於目前選取的季報根目錄；空回應、缺檔、無效、profile 截斷等會標示結果不完整。`rows` 與摘要只描述兩份明選候選在各自出表時點的觀測，不把目錄當歷史分母，不將「未見」推成漏抓、未申報或應申報。

隔離回歸以 temp CSV／manifest 核 hash 改動與 source-acceptance 邊界拒絕，並以合成季度資料確認差異計數、表格預設差異篩選及全表切換。第一次 focused run 為 51 passed／1 failed；唯一失敗是測試預期值的市場排序與實際排序不同，修正測試排序後結果 **52 passed**；最後納入日期摘要與啟動環境隔離更新後再跑，結果 **54 passed**。強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；14 個修改 Python 檔 `py_compile` 通過。最終收據位於工作區 scratch `quarterly-coverage-qa/focused3.log`、`workbench3.log`、`validator3.log`、`mypy3.log`、`py_compile3.log`；Python 命令由 bounded QA runner 在 8 GiB／12 process 上限下執行並自然排空。

此增量不修改或重新擷取名錄／財報原件；沒有把既有官方 issuer 例外映射成自動狀態，也沒有接受來源、改 Gate 3、正式資料、回測或 ML。名錄與財報快照日期不一致；目前季報選擇仍一次只比一個根目錄。已完成 offscreen GUI 自動化，原生桌面畫面及 Owner UAT 尚未完成。document-control 對架構段、QA 清單與 QA 索引的 scoped check 通過；涵蓋 Snapshot／Manual 的較廣檢查仍被既有 `output` junction WinError 5 阻擋，錯誤只涉及舊 trial／task 引用，沒有指向本次新增章節。

### 2026-10-25 MOPS 公告時間 crosswalk 與 Q2 實際解除數

Owner 已授權把 MOPS 顯示的公告日期與時間直接作為對應公告時間戳。本輪更新候選 crosswalk，保留 MOPS 原始 `announcement_at` 的台北時區、事件 SHA 與來源回應 SHA；候選鍵按市場、公司、報表種類及期間比對，不只沿用日級 projection。這項授權已用於時間候選，不等於 MOPS EZSearch 自動採集授權或正式資料寫入許可。

對 2026-Q2 四份一般業 Open Data CSV 的 **3,878** 個公司／報表 profile，對照 2026-07-01 至 2026-09-30 的三組已封存 MOPS 窗口，**3,864** 筆有唯一時間戳候選、**0** 筆有多個公告版本候選、**14** 筆在所選窗口未觀測。未觀測不表示未申報。候選根目錄和 JSON／CSV SHA 留存於本機 `open-data-quarterly-csv-candidate-20261026retry1` 與 `mops_statement_availability_q2_2026_*_20261025`；crosswalk 明確為 candidate-only，`formal_db_write=false`、`source_acceptance=false`、`gate_credit=false`。

將其接回正式資料時，實際結果是 **0 列品質解除**：

- `fundamental_statement_items` 有 1,645,555 列且公告日全缺，但資料期間僅到 2024-Q1，沒有 2026-Q2 目標列。這批公告候選無法回填至不存在的 Q2 財報列。
- `fundamental_current_observations` 有 Q2 資料，但 MOPS current statement HTML 在 TWSE 1,084 家、TPEx 891 家公司與三種報表中，每個公司／報表鍵各有 3 個 `source_version`，合計 5,925 個公司／報表鍵、306,067 列。精查現有候選契約：公告 event hash 綁公告時間、報表項目、detail URL、期間與代碼；`source_sha256` 綁 MOPS 公告查詢 response，不是 filing／財報 HTML bytes。現況 `source_version` 則綁 current statement HTML bytes SHA 及 `captured_at`，`source_available_at` 是擷取時間；公告事件沒有 filing content hash／不可變文件 ID，也沒有寫進現況表的 `announcement_at` 欄。因此 event 到 `source_version` 沒有精確橋。僅以公司、期間、報表類型 join 會把同一時間套到多個報表快照版本；來源擷取時間或相同數值也不能證明它就是公告版。該表全體 `aggregate_feature_eligible=0`，unit／basis 等其他門檻也不會因公告時間而自動解除。因此沒有修改任何一列 Q2 觀測，正式可解除仍為 **0**。
- `fundamental_monthly_revenues` 有 242,651 列缺公告日；現有 1,832 個月營收 availability key 與缺公告日正式 DB key 的精確公司／月份交集為 **0**。沒有各舊月份對應公告時，不拿 2026-Q2 或其他月份時間代填；實際解除 **0 列**。

以上正式 DB 均以唯讀方式檢查，本輪未寫入或重算正式資料。公告匹配候選不能視為 quality projector 已接受的事件映射；要安全解除品質，仍需取得具報表內容版本關聯的公告證據，或 source acceptance 審核建立該連結。MOPS EZSearch endpoint 使用授權、季度 CSV 金額單位／basis、歷史 PIT、舊月營收逐月公告以及其他缺值仍未解。原始 crosswalk 摘要、候選 hash 與唯讀查詢值由 bounded QA runner 產生，詳[本輪公告時間及圖卡 QA](BALDR_INDUSTRY_LEADER_CARDS_20261025.md)。

### 2026-10-26 Research Console 公告候選正式資料影響讀回

Research Console 已把公告候選與正式季報資料的影響摘要接在同一公告對照區。Reader 以唯讀 SQLite 開啟設定資料庫，只查 `fundamental_statement_items` 的公司／報表／期間聚合：版本數、項目列數與缺公告日列數；不選取財務值、不寫 DB。正式表沒有 market 欄，因此 overlap 僅為 identity-only；MOPS 候選事件亦沒有正式 `source_version`／內容 hash 橋接，精確版本連結與公告對照可解除列數不會由身份相同推算。

以已封存 2026-Q2 一般業季報候選及 2026-07-01 至 2026-09-30 三組 MOPS 候選，在本機正式 DB 做實際 reader readback：狀態 `observed`、公告候選唯一鍵 **3,864**；正式 identity overlap **0**、overlap 範圍正式版本 **0**、項目列 **0**、缺公告日項目列 **0**、精確版本連結 **0**、本次可解除 **0**。缺公告日列為 0 是因為這個期間／候選 identity 沒有對應的正式 `fundamental_statement_items` 列，不代表資料庫其他期間已補齊。Reader blockers 為 `formal_table_has_no_market_column_identity_only_overlap` 與 `candidate_event_to_content_version_bridge_missing`。這與前節實際解除 0 列的結果一致，並讓操作頁可直接呈現原因；沒有回填正式資料或改動來源、Gate、PIT、ML 資格。

QA：公告 reader／crosswalk／P0 Source Control Center／Research Console focused suite **125 passed**；必要 Workbench 回歸 **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,151 source files clean**；9 個變更 Python 檔 `py_compile` 通過。實際資料讀回由 8 GiB／12 process 有界 Windows Job 執行，正常退出、Job 無殘留程序。document-control 對 inventory、QA 索引與 README 的 scoped check **12 features／4 link sources／0 errors**。含 PROJECT_SNAPSHOT／APPLICATION_MANUAL 的較廣檢查仍受既有 `output` junction WinError 5 影響，故不能將它記成通過；兩文件新增內容已同步，本輪未跑原生桌面 GUI 或 Owner UAT。

### 2026-10-26 MOPS 季報候選事件 hash 讀回驗證

Root 對封存 EZSearch raw event 重新計算公告擷取器定義的 canonical SHA-256，欄位固定為台北時區 `announcement_at`、F-code、官方明細 URL、期別與公司代碼；只有 `https://mopsov.twse.com.tw` 官方 host 可通過。舊版 crosswalk 曾只驗 hash 字串格式，現在遇到時間或 URL 沿用舊 hash、HTTP 或仿冒 host 即 fail closed。核驗通過的明細 URL 與 event SHA 保留在 candidate crosswalk；Research Console 公告時間欄提示可回查該官方 URL，並與查詢 response SHA 分開呈現。

此修正強化候選事件自身的防竄改與可回查性，不代表公告事件已連到 filing bytes 或唯一財報 `source_version`。仍有 126 個 2330/Q2 observations basis unknown／未驗證／不具 aggregate eligibility，正式 Q2 `fundamental_statement_items` 目標列為 0，公告時間缺漏解除仍為 **0 列**；沒有正式 DB 寫入、重算、source acceptance、PIT、Gate 或 ML 資格變更。

### 季報公告 crosswalk 增加按財報期別摘要

Research Console 的季報公告候選對照，現在對每個選取 CSV 資源按財報所屬期別分列 `profile_resource_rows` 數，以及唯一候選、多筆歧義、查詢窗口內未觀測、查詢窗口不完整與身份缺漏。統計單位明確是資源列／profile；同一公司在不同資源或期別可能重複，因此不代表唯一公司數。查詢窗口內未觀測只表示所選窗口沒有找到對照候選，不等於未申報。

本切片只聚合已選取的離線候選 crosswalk，不新增公告採集、正式資料讀取或寫入，也不改來源接受、Gate、PIT 或 ML 資格。本輪以合成案例驗證期別排序、狀態分桶、缺期身份及跨資源分開計數，沒有重新讀回實際封存候選，因此這份 QA 不提供本機實際候選的期別分布或新的正式資料解除筆數。

QA：crosswalk 與 Research Console focused tests **55 passed**；必要 Workbench 回歸 **93 passed**；全域 mypy **1,151 source files clean**；修改的 2 個 Python 檔 `py_compile` 通過。`scripts/qa_validate_update_tab.py` 因既有 `output/qa/update_tab/RUN_LOG.txt` junction 權限錯誤未能執行完成；bounded Windows Job 正常退出、無殘留程序。offscreen 合成 UI 測試通過；原生桌面 UI／Owner UAT 及實際封存候選 readback 未執行。

### 正式月營收缺公告日按月份唯讀讀回

Research Console 新增正式月營收按期別的公告日欄位品質摘要。Reader 以 SQLite `mode=ro` 和 `PRAGMA query_only=ON` 讀 `fundamental_monthly_revenues`，只按 `period` 聚合列數、缺公告日列、distinct stock code 與 source version；不取營收欄位，也不載入 availability mapping。

本機正式 DB 讀回 147 個月份，期間為 **2014-04 至 2026-06**，共 **246,331 列**、其中 **242,651 列缺公告日**。145 個月份（**2014-04 至 2026-04**）各月所有正式列都缺公告日；2026-05 的 1,848 列與 2026-06 的 1,832 列均有公告日。資料根期間與 mapping coverage 不應混為一談：先前讀回的 availability 檔只覆蓋 2026-06 的 1,832 個 key，與缺公告日正式列精確 overlap 仍為 0。這次沒有回填／重算正式資料；未將公告日完整解讀成單位、口徑、來源接受或 Gate 完整。

實際只讀讀回由 bounded Windows Job 執行，8 GiB memory／12 process 上限 readback 通過，正常退出且無殘留 PID。Receipt：`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_086af2ad67e64b7b995edf2e3adf92f3/receipt.json`，SHA-256 `0ab887fec479114c9440697efc4cde7bea33894b2354c1224276e3634092716`。本切片 reader、P0 DTO/service、crosswalk 與 offscreen UI 整合 focused 執行共 **138 passed**；另有兩個既有 MOPS freshness 測試在 pytest 暫存目錄 `os.replace` 遇到 Windows `WinError 5`，不屬於本次新增資料 reader 路徑。必要 Workbench 回歸 **93 passed**、全域 mypy **1,152 source files clean**、本次修改的 5 個 Python 檔 `py_compile` 通過。Update validator 無法寫入既有 `output/qa/update_tab/RUN_LOG.txt` junction，未完成。額外 shell focused 執行受該 shell Python 缺 PySide6／pytest 套件影響，故不取代 bounded runner 結果。Bounded runner 正常退出且無殘留程序；原生 GUI／Owner UAT 未執行。

### 2026-10-26 月營收缺公告日公司識別明細

正式月營收品質摘要可明選月份分頁讀取缺公告日列的識別明細。Reader 只查所選 `period` 且 `announced_date` 為空值的列，以 `stock_code`／`source_version` 穩定排序；SQLite 使用 `mode=ro` 與 `PRAGMA query_only=ON`，不查營收值、不回寫或重算正式資料。每頁固定 100 列；reader 限制單頁不超過 200 列、offset 不超過 1,000,000。Detail schema v1 分開記錄 mapping 狀態與列狀態：只有無 loader 診斷的正式 mapping，且 `mops.monthly_revenue_announcement`、`formal_v2`、官方公告 hash、公司、月份及 target source version 鍵完整相符，才顯示精確 mapping 日期；已完整讀取但無精確鍵時明示「目前 mapping 無精確版本」，不代表公司未公告。mapping 未配置、不可讀或有診斷時，列狀態保持 unknown。合法的資料庫/schema unavailable 回應也以不可用原因呈現，不誤報成 DTO 格式錯誤。期間摘要與明細共用 `(stock_code, period, target_source_version)` 精確鍵，已匹配 mapping 會從報表日期待核實數扣除；正式公告日缺漏列數另行保留。

實際正式 DB／availability CSV 唯讀讀回：2026-04 有 1,848 列、缺公告日 1,847；第一頁 100 列的 mapping 狀態為 verified，但 100 列均無 exact mapping。2026-05 的 1,848 列公告日缺漏 0、報表日期待核實 1,847；2026-06 的 1,832 列缺漏 0、待核實 1,831，精確 MOPS mapping 各自只核實一個 target version。此明細只列缺公告日列，不會把已填報表日期改寫，也不計為品質解除或 Gate／PIT／ML 通過。

受控驗證：reader／service／detail UI 聚焦 **19 passed**（reader 13、service 3、UI 3）；必要 Workbench UI **97 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,157 source files clean**；3 個修改 Python 檔 compile 通過。正式資料唯讀讀回與測試在同一 bounded Windows Job 執行，8 GiB memory／12 process／kill-on-close 限制 readback 成功，exit 0、remaining PID 0、無強制回收。最終 receipt：`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_32e3c956dfde442e9301f5340b7c32f6/receipt.json`，SHA-256 `8945a47698cbde5735c1506450c19905c05d49c993332b44a3d41b08ef374b96`；route／scoped document-control **12 features／2 link sources／0 errors**，最終 receipt `C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_e2ce28d4dee44481b7c56a7351e83ee9/receipt.json`，SHA-256 `63bab6349efc6b80f660344deb268692709d69c5dc404475f697c942aefba28d`。短路徑 scratch logs／正式資料摘要在 `C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/monthly_mapping_detail_final/`。第一次 pytest basetemp 位於巢狀 scratch，Windows SQLite 無法建立 DB；改用短隔離路徑後通過。期間摘要 exact mapping regression 先抓到 3-key dict 與 4-key tuple 不相容，已改用相同三欄身份鍵並由回歸鎖定。廣域文件連結檢查對 Manual 既有 `output/` Junction 回 WinError 5，因此未記為通過；本輪只核功能地圖與 QA 連結。正式 DB 未寫入；degraded／missing 解除 **0 列**，Gate／PIT／ML 資格不變；原生 GUI／Owner UAT 未執行。

### 2026-10-26 靜態月報日期被誤當公司公告日的現況盤點

唯讀正式 DB 聚合發現 2026-05 的 **1,848** 列與 2026-06 的 **1,832** 列 `fundamental_monthly_revenues`，來源皆為 `mops.monthly_revenue_static_snapshot`，目前 `quality=observed`。前者儲存公告日 `2026-06-16`、可用日 `2026-06-17`；後者公告日 `2026-07-14`、可用日 `2026-07-15`。這些日期來自報表層級快照日期，不能證明各公司原始公告時間。兩期共 **3,680 列**需逐公司、逐月份、逐版本重新核對；未執行正式 DB 更新或重算。

正式 availability CSV 唯讀抽查：2026-05 無 mapping；2026-06 有 1,832 個舊 TWSE OpenAPI mapping。provider 以正式 mapping 對應 SQLite 列後，2026-05 靜態 snapshot 不會被讀出；策略讀取器已排除舊 `legacy_official_compatibility` mapping，避免相同報表日期讓 2026-06 靜態 snapshot 列進入策略。它們的正式列身分與公告事件版本仍無證據橋，不能視為 MOPS 公司別公告已重新核實。另一個 242,651 列缺公告日仍未解除。

本次 `monthly_revenue_availability_history` 修正禁止將 TWSE／TPEx OpenAPI 的報表出表日、MOPS 靜態報表／靜態快照日期轉成 `official_announcement` 候選；即使提供擷取時間也不提升證據。只有具公司、月份與 source version 的 MOPS 公告事件才可建立候選；未有事件原件的月份保持 missing。SQLite provider 也不再讓舊 `legacy_official_compatibility` OpenAPI mapping 替靜態快照通過策略讀取，但保留任何後續有效 v2 事件 mapping 的歷史匹配能力。

Research Console 月營收摘要契約升至 v2，新增報表層級日期來源待核實列數，頁面說明「讀回成功」不等於公司公告時間已逐筆核實。本機正式 DB 唯讀讀回 147 個月份：2026-05 的 1,848 列公告日欄非空，但 1,848 列均為報表日期來源待核實；2026-06 的 1,832 列同樣全數待核實；其餘 242,651 列仍缺公告日。這是依來源 ID 的品質警示，不是逐列 MOPS event/source-version match，也沒有改 DB `quality` 欄或解除正式列。

focused reader／P0 schema／Research Console service/UI **139 passed**；必要 Workbench UI **96 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,154 source files clean**；3 個修改 Python 檔 `py_compile` 通過。受控 Windows Job 正常退出、無殘留程序、8 GiB／12 process 上限 readback 通過；正式 DB 實讀 receipt SHA-256 `a589611afc3def096e9c7e766405a1c7b0adc9624b9825704e9fc33e0fa0b40c`。文件控制 task 檢查仍有既有 `output` junction 越界連結，未列為通過；原生 GUI／Owner UAT 未執行。正式資料未寫入，品質解除 **0 列**。

### 2026-10-26 MOPS 靜態月報日期語義與月營收公告 mapping 防線

Owner 已授權把 MOPS 顯示的「公告日期／時間」當作相符公告事件 timestamp；它不把整份歷史靜態月報頁首的「出表日期」改成公司別公告時間。本次讀取官方 MOPS 2026-04 月報頁：TWSE 頁顯示「出表日期：115/10/25」，TPEx 頁顯示「出表日期：115/10/24」；這是報表層級的回溯日期，不是每家公司 2026-04 的原始公告時間。來源：[TWSE 2026-04 靜態月報](https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_4_0.html)、[TPEx 2026-04 靜態月報](https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_115_4_0.html)。

因此，`monthly_revenue_availability_history` 載入靜態 MOPS 報表時改標為 `mops.monthly_revenue_static_report`／`retrospective_static_report_date`；候選 mapping builder 只記一次該市場／月份的診斷，不把此日期建立成 `announced_date` 或 `available_date`。正式月營收仍保持缺公告日，直到取得公司＋月份＋原公告時間的逐筆事件證據；報表靜態日期、available_date 或當前擷取日期不能替代它。

### 2026-10-26 MOPS 2330／2026-Q2 公告至財報 custody 單筆追查

已封存 EZSearch candidate 含 2330／F27／2026-Q2 唯一事件：公告時間 `2026-08-14T13:46:30+08:00`、event hash `42a2b7d7e07d8c4986de69fb98d8d7f9a11a4a89a368095ed70ee71abdf46610`、公告查詢 response SHA `ad8b8a5f33a401347f4fa0a3c36c5f100cd81990c4aa040a03c44d0d643b4286`；事件原件 JSON SHA-256 `30c80bc6d34d69a6d1652a1779e254b7cda053a50a2ee5978899a82f9e26e466`，位於隔離候選 `mops_statement_availability_q2_2026_retry1_20261025`。

後續透過官方[TWSE 電子資料查詢頁](https://doc.twse.com.tw/server-java/t57sb01?co_id=2330&colorchg=1&mtype=A&step=1&year=115)讀到 2330／民國 115 年第二季／IFRSs 合併財報列檔：`202602_2330_AI1.pdf`，9,323,383 bytes，上傳時間 `2026-08-14 13:59:44`，更補正狀態「無」；英文版另列 `202602_2330_AIA.pdf`，1,911,452 bytes，上傳時間 `14:00:15`，更補正狀態亦為「無」。台積電[官方中文版 Q2 財報](https://investor.tsmc.com/sites/ir/financial-report/2026/TSMC%202026Q2%20Consolidated%20Financial%20Statements_C.pdf)封面同為 2330／115 及 114 年第二季合併財報，附註二記載 115-08-11 董事會核准並通過發布。MOPS 公告事件時間比 TWSE 電子檔上傳早 13 分 14 秒；兩個 timestamp 分別表示公告事件與檔案上傳，不合併替代。隔離 PDF `mops-t57-2330-2026q2/202602_2330_AI1.pdf` 本機大小及檔名與官方 listing 相符，SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`；但 10/25 的本機 T57 listing capture receipt 因 DNS 失敗，沒有封存 listing HTML／response bytes。故目前新證據確認了同公司、期間、合併報表種類、申報檔名、刊載大小／時間與未更正狀態，仍未證明本機 PDF 與官方 listing 所指 bytes 完全相同，也未完成 PDF 對 `fundamental_current_observations` 單一 `source_version` 的內容/hash 比對。

正式 `fundamental_statement_items` 對此 2026-Q2 identity 仍為 0 列；正式資料沒有可重算或解除 announcement-only degraded 的目標列。現有 3,864 個 Q2 公告候選與 3 個 current snapshot versions 不因這筆單案身份核對而取得正式版本橋接。未寫正式 DB，正式解除仍為 **0**。下一步需在可取得官方 bytes 的環境保存 T57 listing／PDF 原件和 hash，再把財報完整項目、單位／口徑及某一快照 `source_version` 做唯一比對；不得用自然鍵或同日期外推其餘事件。

### 2026-10-26 2330／2026-Q2 財報內容候選交叉核對

另以台積電[官方 2026-Q2 合併財報](https://investor.tsmc.com/sites/ir/financial-report/2026/TSMC%202026Q2%20Consolidated%20Financial%20Statements_E_2.pdf)交叉核對本機 `fundamental_current_observations`。該報表涵蓋截至 2026-06-30 的六個月，財務報表金額單位為新台幣千元，董事會核准日為 2026-08-11。依同報表的 13 個資產負債表、19 個綜合損益表及 7 個現金流量表數值逐項比對，乘以 1,000 換算成資料列的 TWD 後，39 個數值完全相符。公告時間仍採相符 MOPS 事件 `2026-08-14T13:46:30+08:00`；董事會核准日及 TWSE 電子檔上傳時間都不是該公告 timestamp。

唯讀讀回共見 126 筆 observation，分屬三張報表各三個 raw snapshot version group。每張報表的三組 canonical item-code／numeric-value／unit manifest 相同，但 raw bytes hash 不同；此可支持數值一致性，不能單獨證明哪一組是該 MOPS filing 的唯一 `source_version`。另 3 個欄位尚未由報表逐項核實：兩個股數列為 0，以及衍生的「每股參考淨值」248.05。全部 126 列目前 `period_basis=unknown`、`basis_verified=0`、`aggregate_feature_eligible=0`；正式 `fundamental_statement_items` 的 2026-Q2 目標列仍是 0。MOPS／TWSE listing 原始 response custody 也仍不完整（本機 T57 listing 擷取曾 DNS 失敗；已知官方 PDF 連結現回 404），因此這是內容匹配候選，不是來源接受或正式資料版本橋。

#### 2026-10-26 三個剩餘欄位的官方交叉核對補充

以 `mode=ro`／`PRAGMA query_only=ON` 精確讀回正式 DB 中 2330／2026-Q2 的候選觀察：庫藏股股數與「預收股款（權益項下）之約當發行股數」各為 `0 shares`，兩者均出現在三個 MOPS balance snapshot versions；TWSE 官方 OpenAPI 候選亦各回 `0.00 shares`。這證明多份現有候選記錄的值一致，但不能代替 T57 原件逐項核驗，也不能證明各 snapshot 的 bytes 身分或它們中的任一個就是該公告版本。

「每股參考淨值」`248.05 TWD/share` 亦可由台積電[官方 2026-Q2 精簡財報](https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/2026-07/114aaca0fea2050e96b91fffbab9ed04ba09cd92/FS.pdf)交叉重算：2026-06-30 歸屬母公司股東權益新台幣 6,432,518 百萬元，股本新台幣 259,324 百萬元；以每股面額新台幣 10 元推得約 25,932.4 百萬股，權益除以此股數約為新台幣 248.05 元。這使候選衍生值可重現，但屬跨報表數值計算核對，不是完整 T57 的直接列報值；分子、分母、日期及計算規則仍需納入明確欄位契約。

因此「248.05 尚未核實」現應精確解讀為「衍生算法可交叉重現，正式口徑與版本未接受」；兩個股數 0 則仍只有多份候選來源一致，沒有完整 T57 逐欄佐證。這項補充沒有改動 126 筆 observation：basis／來源版本橋仍未完成、`aggregate_feature_eligible=0`，正式目標列仍 0；未寫 DB、未重算或解除公告時間品質，Gate／PIT／ML 資格不變。

未寫正式 DB、未重算或改標 quality；公告時間缺漏的正式品質解除 **0 列**，source／PIT／Gate／ML 資格均無變更。只有在 filing bytes／不可變身份、statement basis 與單一 `source_version` 唯一橋接並具備正式目標列後，才可按 Owner 已授權的公告 timestamp 重算；其他單位、口徑、版本或實際缺值仍須分項保留。官方公司報表只能佐證內容，不能替代 MOPS event 或官方 listing 的原始 custody。


### 2026-10-19 最新季度 OpenAPI 候選 readback

截至 2026-10-26，repo 已有季度 OpenAPI 最新候選為 `quarterly-openapi-20261019T010111865027Z-19cecc8bee1f483493329969f441c91b`（2026-10-19 UTC 擷取），位於 `output/mops_quarterly_openapi_research/`。終端狀態為 `completed_with_review_items`；唯讀 terminal readback 驗證 26 份 request receipt、3,962 筆數值原始列與 3,954 筆 preview 列。24 個 endpoint 中，16 個為 `observed_row_array`、6 個為 `key_review_required`、2 個為 `schema_review_required`；8 筆待審列未進 preview。16 個可解析 endpoint 的報表期別均為 2026-Q2。preview 的欄位空值計數合計 31,001（欄位值缺漏數，不是公司列數）；這是候選觀測，不代表正式品質清除或全市場 coverage。

該 run 將 `available_at` 留空、`formal_pit_eligible=false`、`issuer_coverage_complete=false`；endpoint 的 `Date`／`出表日期` 不被視為逐列公告時間。官方 OpenAPI catalog 與 Open Data 季報頁提供路由、欄位與季度期別資訊，但不足以確認一般金額單位、合併／個別報表 basis、逐列首次可得時間或修訂版本歷史。相關證據與限制見[季度 OpenAPI 擷取 QA](SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)及[來源採用與季度目錄 QA](FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md)；官方來源包括 [TWSE OpenAPI catalog](https://openapi.twse.com.tw/v1/swagger.json)、[TPEx OpenAPI catalog](https://www.tpex.org.tw/openapi/swagger.json)、[TWSE 季報資料集 94831](https://data.gov.tw/dataset/94831)與[TPEx 季報資料集 91967](https://data.gov.tw/dataset/91967)。因此該批資料仍為隔離研究候選，沒有正式 DB 寫入、source acceptance、Gate credit 或 ML 資格變更。

### 2026-10-26 F22 與富邦 API 來源可用性盤點

為確認能否補到正式月營收公告日，查核 [MOPS 官方公告快易查](https://mopsov.twse.com.tw/mops/web/ezsearch)：頁面列有 F22「月營業收入」，並標示資料區間自民國 102 年起；這個頁面資訊表示歷史範圍可能涵蓋正式資料庫 2014-04 起的缺公告日月份，但尚未證實其查詢 API 回應如何標示公司、月別與時間，也未建立可用候選。既有 `mops_ezsearch_statement_availability` adapter 只接受季度財報 F26–F29。依上方「來源授權邊界」，EZSearch 自動擷取授權未被證實，不得以這項功能列表擴大自動採集。

本次僅作一次無登入、單一公司（2330）、單一日期的 F22 查詢探測；本機 DNS 無法解析 `mopsov.twse.com.tw`，HTTP request 未建立，沒有 response body、receipt 或資料候選。沒有因此建立正式公告日期 mapping。

<a id="mops-f22-2330-2026-05-08-single-day-retry"></a>

### 2026-10-26 F22／2330 單日公告查詢重試

2026-10-26 重新限縮到 2330／F22／2026-05-08 的單日唯讀查詢（POST `ezsearch_query`，最多 8 秒、回應上限 8 MiB，無登入）。請求仍在 DNS 階段失敗，沒有 HTTP status、response body、公告列或正式候選；因此這次也沒有重算／解除。Bounded Job 使用 8 GiB／12 process／kill-on-close，exit 2 表示單筆 probe 未取得資料，Job active processes 0、handles closed、無殘留程序。receipt SHA-256 `c1c73cee4925651e2e5110b6edf36770c0929d16ac31bd22264e1809bf215742`，stdout SHA-256 `bd2e83fcfc6f20b038b5c3caf588a89d5e43fcd6aba0c17e815b29bdaA373e3c`，收據位於隔離 visualization scratch `owned-validation/f22-2330-20260508-20261026/`。瀏覽器可開啟 EZSearch 首頁只證明查詢表單可顯示，沒有提交後的 F22 結果，不作公告或版本證據。

#### 官方開放資料替代來源核對

另核對 TWSE 在政府資料開放平台的[上市公司每月營業收入彙總表（dataset 18420）](https://data.gov.tw/dataset/18420)與[公開發行公司每月營業收入 OpenAPI](https://openapi.twse.com.tw/)。這兩個官方路徑可提供月營收彙總資料；dataset 18420 標示政府資料開放授權條款第 1 版，欄位包含「出表日期」、「資料年月」、「公司代號」及營收數值，但未提供逐公司 F22 公告事件及其原始公告時分。依既有月營收契約及靜態出表日判讀，不能把 dataset 的「出表日期」推定為每家公司的公告時間；它可供數值／當期彙總交叉核對，不能解除 `announced_date` 缺漏。F22 逐筆事件證據目前仍無候選，正式月營收公告日解除 **0 列**。

另查核[富邦歷史 K 線文件](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/historical/candles/)：其市場行情 API 文件列出上市櫃日線最遠可回溯至 2010 年，單次查詢小於一年。它可能提供缺漏日的行情候選，但不是 MOPS 公告時間、公司財報月份或 filing version 的證據。工作區安裝 `fubon-neo` **2.2.8**；不帶任何憑證初始化 `FubonSDK()` 時收到 `ValueError: No such host is known (os error 11001)`，無登入、無歷史 candles endpoint 回應。當時的 2330／2026-10-23 查詢尚未送出，且自動審查曾拒絕讀取 Windows Credential Manager 並登入券商 API。此段記錄的是初次試查前狀態；後續依 Owner 要求完成的兩筆行情查詢見下節，該節為較新結果。

結論：F22 與富邦文件各自提供候選路徑；F22 仍受 EZSearch 自動採集授權與 DNS 限制。富邦歷史 K 線後續已完成單筆試查，但沒有解除正式資料；2.4.0 盤後籌碼端點則尚未實測。正式資料、Gate／PIT／ML 資格不變。

### 2026-10-26 富邦唯讀歷史 K 線單筆試查

依 Owner 要求，只在程式外用既有唯讀行情憑證做兩筆歷史 K 線查詢；沒有讀取或呼叫帳戶、持倉、委託或交易 API，也沒有把券商 API 接入 Baldr。正式 DB、daily CSV、Gate 與 ML 均未寫入或改變。

- 目標查詢 2330／2026-10-23／日 K：API 回 **HTTP 404 Resource Not Found**，沒有行情 payload。既有[TWSE 10/23 單股重核](BALDR_LIVE_MARKET_FRESHNESS_RECHECK_20261024.md#2026-10-26-twse-1023-單股來源重核)也記錄 2330 查詢無資料、月成交頁最新列為 10/22；兩個來源都沒有提供 10/23 行情，尚無證據把它判成可補的交易日缺列。錯誤原始 response body 未留存。
- 控制查詢 2330／2026-10-22／日 K：成功取得一列，`open=2435`、`high=2435`、`low=2385`、`close=2385`、`volume=29,796,590`、`turnover=71,536,783,195`、`change=-35`。富邦文件說明一般上市櫃日 K 的 volume 單位是股，turnover 單位是元；此控制列只證明 API 對該日期有回應，未與正式 DB 或 TWSE 逐欄對帳。
- 隔離候選檔：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\fubon_2330_20261022_control.json`；canonical payload SHA-256 `1a7718812a6aa5612738ebf03511662300247dfff1d06259edc361226a432a99`。10/23 404 沒有被改造成資料列，也沒有保存為原始 response artifact。
- Fubon 歷史行情 endpoint 因 10/22 控制查詢成功而確認可連線；對 10/23 查詢回 404，正式解除筆數 **0**。後續核對到官方 TWSE 臨時休市公告及已驗證 calendar cache：2026-10-23 因薔琵颱風休市，故這不是應有行情列的交易日缺值，富邦 404 不構成資料源缺漏或可補資料。10/22 控制列仍未與正式 DB／TWSE 逐欄對帳。富邦行情可作 OHLCV／turnover 候選來源，不能填月營收或季報 `announced_date`、公告時間、申報版本、PIT 或授權證據；上述 fundamental 缺口與 Gate／ML 資格不變。休市證據見[TWSE 臨時休市公告與資料日重判](BALDR_PROGRAM_READINESS_LIVE_UI_20261025.md#2026-10-25-twse-臨時休市公告接線與資料日重判)。

### 2026-10-26 富邦 2.4.0 盤後籌碼端點能力盤點（未實測）

補查富邦[三大法人買賣超](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/ownership/institutional-trades/)、[集保戶股權分散](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/ownership/tdcc-distribution/)及[董監持股](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/ownership/director-holdings/)官方 API 文件：這些端點分別提供個股日法人買賣、每週（早期每月）集保級距分布、每月董監持股；文件列出的歷史起點分別為 2013 年、2013-07、2017-01，資料來源為 TWSE／TPEx、TDCC 或 MOPS 公開資訊整理。它們不是月營收或財報數值 API。**這些也不是 Baldr 的新 transport 缺口**：repo 已有 TWSE T86／TPEx 三大法人及 TDCC CSV／OpenAPI 路由，另有正式來源 parser／candidate capture（[`p0_source_acquisition_routes.py`](../../data_module/p0_source_acquisition_routes.py)、[`capture_tdcc_shareholding_candidate.py`](../../scripts/capture_tdcc_shareholding_candidate.py)）。Gate blocker 在 available-date／PIT provenance、license／用途、coverage 與 source acceptance，不是沒有下載端點。富邦文件標註上述盤後籌碼方法自 SDK **2.4.0** 起提供；本工作區版本為 **2.2.8**，套件原始檔內沒有這三個方法；官方範例要求登入取得行情權限，故本輪沒有為重複來源升級／登入。

這次沒有升級套件、讀取券商憑證或登入呼叫新端點，遵守 Owner 指定產品不連真實券商帳戶的邊界；因此這只是文件能力盤點，未取得任何新 response／候選列，正式解除仍為 **0 列**。即使未來取得回應，法人 `date` 是交易日、TDCC `date` 是公布基準日、董監 `date` 是資料年月，文件沒有逐列首次公告 timestamp；因此仍須另外核對捕獲／可得時間與正式欄位契約，不能直接消除歷史 PIT、Gate 或 ML blocker。既有 2330／10-23 candles 404 與 10-22 控制查詢結果維持前節記錄。

### 2026-10-27 富邦唯讀行情連線重試

依 Owner 要求，以既有隔離的 `scripts/test_fubon_readonly_marketdata.py` 執行一次 bounded probe。使用專供行情讀取的 API Key／憑證登入，僅呼叫 OTC quote snapshot；連線成功並收到 `dict` response。探測程式只記錄 response type，未保存或檢查 payload 列數／欄位，因此這是 transport 成功證據，不是資料內容完整性或正式來源接受證據。未呼叫帳戶、持倉、委託或交易 API；未升級 SDK、寫正式 DB、回填行情或改 Gate／PIT／ML 資格。執行 receipt SHA-256：`E1DD1B719E406869BC7700CA5A525A35E5370E98AA19BD00FF7C4D85BAA5810F`（本機 owned-validation receipt；原始憑證未寫入輸出）。

富邦官方行情文件列有歷史 K 線、公司行動及盤後籌碼 API，但沒有 MOPS F22 月營收公告事件、F26–F29 季報 filing identity 或報表版本橋。此前已成功的 2330／2026-10-22 歷史 K 線仍只屬未與正式 DB／TWSE 逐欄核對的行情候選；2026-10-23 404 對應官方休市，不是缺列。此連線重試沒有新增可套用到缺值的行情列，正式缺口解除仍 **0 列**；19 筆 Forward 的公司行動／交易限制 source warnings、13 筆待收盤項目，以及 MOPS 公告／版本缺口均未改變。

### 2026-10-27 富邦公司行動對 Forward 19 筆 warning 的唯讀候選比對

依 Owner 要求，使用現有唯讀行情憑證呼叫富邦 market-data API，僅取 2330 當前 ticker／quote 及 2026-08-01 至 2026-10-26 的 dividends、capital-changes 候選；未呼叫帳戶、持倉、委託或交易端點。隔離投影共有 703 observations，其中 702 筆公司行動列、1 筆 2330 漲停狀態觀測；另有 1 列公司行動因必要日期欄不合投影契約而拒收。投影會保留逐列 payload hash，但不保留完整 API response bytes；診斷仍標示 `research_only_not_official_announcement` 及沒有完整交付指標。

以正式 `latest_status.json` 的 run `20261026T175624162476Z` 所列精確 19 個 event IDs，唯讀讀取各事件股票、Forward window-20 的 event/outcome 價格日期及警告，再按股票代碼與 `(event_price_date, outcome_price_date]` 比對富邦公司行動候選。**19 筆均無代碼及日期區間同時命中的候選，來源警告解除 0 筆。** 無命中不能證明歷史期間沒有事件；富邦 intraday ticker 是當前狀態，沒有足以回建歷史交易限制有效期間的端點。19 筆仍為 `ready`／`degraded`，每筆保留企業行動與交易限制兩項來源警告，共 38 項；未改正式 DB、Forward 結果、Gate／PIT／ML 資格。

隔離輸出 `owned-validation/fubon-outcome-gap-probe-20261027/candidate.json` SHA-256 `325407DC68EFBF2CFBAB803E3D69A933A36FBD957895CD1C5EFD416342E3D3EC`；exact-19 比對 `exact19_match_audit.json` SHA-256 `D6503D86C06213FEB2D975B296A037C2C441223F8D9A539AEBC4A5ABE3C2205B`。官方端點範圍見[富邦除權息](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/corporate-actions/dividends/)、[資本變動](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/corporate-actions/captital-changes/)及[個股即時 ticker](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/intraday/ticker/)；上述候選沒有公告／首次可得時間或足以接受為完整歷史事件來源的證據。

### 2026-10-26 EZSearch 季報事件候選與數值重播限制

重新讀回 2026-10-26 的 2330／2026-Q2 EZSearch F26–F28 原始回應，三份 HTTP response hash 均與 capture evidence 一致：F26 `257663262d452f05dc8b27d446b770cee12abae6b0e388c1e01d7b56272788b7`、F27 `c11f94270d2a19a3a55e2155918f46899724bf04b0fe5e69f8441a0eea844785`、F28 `1b74777fe725a09cf2669822fb98373f9725fe3d85d6a91d8375e13921e6fd20`；per-company evidence SHA-256 `9c7356686c3c298833aefdb953a07b4fbb6963641be03cb57683363554648f1b`。F27 列指向同公司、同期間的官方 `ajax_t164sb04` detail URL，公告 timestamp 為 `2026-08-14T13:46:30+08:00`。原 7/31–8/29 查詢三項各回 **1,000 列**，因此仍不能由該批次宣稱搜尋範圍完整或唯一。後續把查詢縮至 8/14 單日重抓，擷取器在 TEMP 產生的 manifest `raw_files` 為空，沒有保存到任何 response body；唯一性與未截斷仍未驗證。受控 Job 收據 SHA-256：`f9191fe2e72b7bdab84989248ff31d79c570e7b5cd0acfebb7aecb185342e285`。

以 broad-window EZSearch evidence 搭配 r8 保存的 MOPS T164／XBRL raw 重播，官方 candidate builder 的證據驗證通過並產生 172 列隔離候選；輸出位於本機 visualization 工作區 `mops_2330_q2_ezsearch_candidates_20261026/mops-ezsearch-2330-q2-v2-20261026/`，candidate SHA-256 `7d9627b11f091ab554c1806fdd67de6236943dbad72d33c95a4869f1b1710e46`、run manifest SHA-256 `c6988d829331c1aacc16f7231876404ecaeee676e6b444987edd38debedaf8cf`，Job receipt SHA-256 `d315f2bddab050e38527441afea5e21fcb073f0767c922b446d5813c633e5be5`。與 r8 原候選對照，172 列的整數值、單位、scale 及數值來源列 hash 全相同；但 172 列的 candidate `content_hash` 全部改變，其中 45 列 `xbrl_reported_value` 符號改變，source version 從 `...t57sb01...v2` 變為 `...ezsearch...v3`，`numeric_available_at` 也從 2026-09-07 重設成 2026-10-26。故這份重播候選不能當作只補公告時間的回填，也不能把新的 parser/version 當成既有數值版本。

另一個唯讀核對找到原 candidate 所引用的 canonical manifest／dataset，hash 均符合 batch manifest：manifest `0a9f0a4890b04ff573cf264346e98790065e955a3437c2be7076743870ddb726`、dataset `6afe51a64abc50626cfd411b84e57d8637dec9a50a35985d2724413764ab9777`；該 dataset 自身標記 `research_only_degraded`、`formal_oos_allowed=false`、`zero_formal_write=true`，只作 lineage 錨定，不代表財報版本證據。F22／2330／2026-06（查詢窗 7/1–7/31）的單次無登入探測則在 DNS 階段失敗，沒有 response body 或 F22 evidence；Job receipt SHA-256 `e2db57e255c961fc2b36e347d2b59d2a0290beafa00346fa9077b4da22c71300`。

目前只能確認 MOPS 公告事件與 r8 數值候選有相同自然鍵及 detail endpoint；尚缺未截斷的事件查詢原件，以及公告 filing bytes／唯一版本識別碼到 r8 數值列的內容橋。季報正式表的 2026-Q2 目標仍為 0 列，月營收逐公司／月份 F22 事件仍無候選；本輪未寫正式 DB、未重算或解除列數 **0**，Gate／PIT／ML 資格不變。下一步先取得成功的窄窗 F26–F28 原件，再以同一 filing 的原始 bytes 或可核驗版本識別，逐列比對 numeric source version；未完成前維持 candidate-only。

### 2026-10-26 T57 清單 custody 更正與 PDF 身分探測

更正前述「T57 listing 原始 response custody 不完整」的概括描述：r8 原始候選其實已封存 2026-09-07 的官方 T57 清單 response，路徑 `output/v4_data_recovery_2026-09-07/quarterly/v4-quarterly-statement-2026q2-twse-2330-r8/raw/mops_t57sb01_2330_115.html`，5,058 bytes，SHA-256 `dc8d533ea747f62164aa452d4009cfe1477783145ec2db63d38672b7b8e77daa`，且與 r8 `run-manifest.json` 引用 hash 相符。清單原件列出 2330／民國 115 年第二季／IFRSs 合併、`202602_2330_AI1.pdf`、9,323,383 bytes、上傳 `115/08/14 13:59:44`、更正狀態「無」。因此 listing 原件 custody 完整；先前 10/25 再擷取失敗只表示沒有第二份較新 listing response，不會抹除 r8 原件。

為補上 listing 到 PDF bytes 的精確橋，於 2026-10-26 14:03:57 UTC 按原表單 `step=9`、`kind=A`、`co_id=2330`、`filename=202602_2330_AI1.pdf` 對官方 T57 endpoint 發出一次無登入、唯讀、無 redirect 的單檔 POST，response 上限 11,000,000 bytes。請求在 DNS 階段失敗（`doc.twse.com.tw` WinError 11001），故沒有 response body／PDF hash。受控 Windows Job exit 0、8 GiB／12 process 限制讀回通過、剩餘 PID 0、無強制清理；Job receipt SHA-256 `26780cbfe12aace1b3270ebc447ecf1ece7aeb07d89c0fd3dcc7361fdcacd22b`。此狀態更新 receipt 位於隔離 visualization scratch，正式資料未動。

scratch 中候選 PDF 仍為 9,323,383 bytes、SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`；檔名／大小與 r8 T57 清單一致，但 DNS 失敗使官方 bytes 比對未完成。39 個官方財報數值核對仍僅證明內容交叉比對結果，不足以證明 PDF byte identity 或唯一對應三個 current snapshot source versions。正式 Q2 statement target 仍 0 列，正式品質解除 **0**，未寫 DB、未重算，Gate／PIT／ML 資格不變。安全下一步是當官方 T57 DNS 可用時重試這一個精確 listing row 的單檔下載並比對 SHA；若相符，再核完 item／basis／source-version 唯一橋，不擴成批次回填。

### 2026-10-26 T57 單檔下載 sandbox 外重試

為排除 sandbox 網路限制，Root 又在有界 Windows Job 中對同一官方 T57 `step=9` 表單、同一檔名與相同上限做一次 sandbox 外無登入唯讀 POST；請求仍在 DNS 階段失敗（`doc.twse.com.tw` WinError 11001），沒有 response body 或 PDF hash。Job receipt SHA-256 `4cff2ad51d63265a98d78c6bf4060109ce005587a7329ff9b1fb213d43122874`；exit 0、剩餘 PID 0，kill-on-close／8 GiB／12 程序限制讀回成功，無強制清理。正式資料及 r8 原件不變；PDF bytes identity、唯一數值版本橋與正式資料品質解除仍未完成，維持 **0 列**。此後不再盲目重試相同 DNS 請求；等官方主機解析恢復或可用的官方 bytes 路徑再續。

### 2026-10-27 台積電官方 IR PDF 與 T57 候選 bytes 比對

沿用同一 2330／2026-Q2 精確文件，改從[台積電投資人關係官方財報 PDF](https://investor.tsmc.com/sites/ir/financial-report/2026/TSMC%202026Q2%20Consolidated%20Financial%20Statements_C.pdf)唯讀 GET；HTTP 200、`application/pdf`、9,323,383 bytes。隔離保存後 readback SHA-256 `a9c56c17cba6ebd9aaaa0579c1e73eea53a14623e62916bbf26a1080107b78a3`，與既有 `202602_2330_AI1.pdf` 候選 bytes **完全相同**；T57 官方清單原件列出的檔名與大小亦一致。這為候選文件提供了官方 issuer bytes 的來源佐證，但沒有把候選 JSON 的 `document_bytes_verification` 改成已直接下載 T57，也不代表 172 筆 T164 數值已與該 PDF 完成逐列版本橋。

正式 Q2 `fundamental_statement_items` 仍為 0 列；`fundamental_current_observations` 有 161 列、11 個 source versions，無法唯一認領 172 列 research candidate。公告 timestamp 雖已由 MOPS 事件核對，仍須完成數值內容／版本唯一性及來源接受證據；正式資料寫入與品質解除 **0 列**，Gate／PIT／ML 不變。隔離 PDF 與 manifest 位於 `owned-validation/issuer-q2-pdf-version-check-20261027/`；manifest SHA-256 `DF0D8A15D6E68581FF74ECE91F016E347EF05A78E92BF576219A6B259F7C6B3B`，bounded receipt SHA-256 `219384F1EE81D67CD37BFB0297CDDA21D67DB7ACC22BE362FBCCB4F43B46CD2D`；Job exit 0、8 GiB／12-process／kill-on-close 限制讀回、程序歸零且 handles 關閉。粗略 PDF text label／數字掃描未能建立完整列級 mapping，summary SHA-256 `E5D352744DFF58285DF105E8A96B261548073967794203E7417B020AA6878869`，故不作為版本比對或回填依據。

<a id="2026-10-26-q2-formal-observation-version-crosswalk"></a>

### 2026-10-26 Q2 正式觀察列直接版本鍵比對

對正式 `fundamental_current_observations` 以 `mode=ro`／`query_only=ON` 重做直接鍵比對：2330／2026-Q2 有 161 列、11 個 source versions；對 172 列 T164 候選逐版本比較後，**11 個版本的 exact `item_code` overlap 均為 0**，exact item-name／value／unit match 亦均為 0。正式列 basis 混有 unknown、period-end 與 year-to-date-cumulative；不能用同公司／期間或裸數值相似性挑一個版本。這只排除直接鍵相等，並未判定不同碼名之間是否存在可審核語義映射；建立 mapping 仍須逐列保存別名、單位、period basis 與 PDF/XBRL lineage 證據。唯讀 audit bounded receipt SHA-256 `8f785c6d5bcb3c71c2f08e170ca11cd4a8937b1c1be21a79643a2d61d0caa413`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、正式 DB 未寫入、Job 自然歸零。正式來源版本橋、quality release、Gate 3／PIT／ML credit 仍為 0。

<a id="monthly-2330-2026-04-readonly-audit"></a>

### 2026-10-26 2330／2026-04 正式月營收列唯讀核對

用正式 DB `mode=ro`、`PRAGMA query_only=1` 僅查 `stock_code=2330`、`period=2026-04` 的身份與可用日期欄位（未讀營收數值）：唯一一列為 `source=mops.monthly_revenue_static_snapshot`、`source_version=mops-static-snapshot-monthly-revenue-2026-06-16`、`as_of_date=2026-04-30`、`announced_date=NULL`、`available_date=2026-06-17`、`quality=degraded`。這確認了最窄候選列及其精確數值來源版本，未寫正式 DB。

台積電官方[2026 年 4 月營收報告](https://pr.tsmc.com/chinese/news/3305)及[營運報告行事曆](https://investor.tsmc.com/chinese/financial-calendar)均支持報告於 2026-05-08 發布；issuer release 只提供日期，沒有本次核到的 MOPS 公告時分與原始公告 response。因 Owner 授權指定使用 MOPS 顯示的公告日期／時間，不能以 issuer 頁面或當前靜態快照日期假作 MOPS event timestamp，也不能只憑相同公司與月份將事件綁至 2026-06-16 數值版。正式公告 mapping、品質重算及解除仍 **0 列**；該列目前是精確追查候選，不是已解缺口。

唯讀查核輸出 SHA-256 `ad5d1c62176c1c7ffc5e0b51db7312bf7d8bf2c2096fde3aa16475fc99b14847`；bounded Job receipt SHA-256 `d7176288abc69805f5489694382c3d5a337dc1d2d76a04aec756f47d44e74ae3`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 自然歸零及 handles 關閉。輸出保留於 visualization scratch `owned-validation/monthly-2330-202604-audit/`。

<a id="2026-10-27-fubon-historical-candles-for-weekly-ohlc-gaps"></a>

### 2026-10-27 富邦歷史 K 線對週報 OHLC 缺值做精確候選比對

針對 Gate 2 週 collection `ewc_58409a20689d74be` 已經同日 TWSE custody 原件核實為 `--` 的 16 筆 OHLC 缺值，使用行情唯讀 API 逐股票查詢 2026-10-19 至 2026-10-22 日 K，共 11 檔、11 次歷史行情請求。富邦回傳 28 根 K 線；與 16 個缺值 row 的股票代碼及日期做精確比對後 **0/16 命中**。1538 在該區間沒有 K 線；其餘回應日期也未對上各自缺值日。故本次沒有可供替代核對的候選行情，官方 `--` 仍是已核實的來源事實，正式 OHLC、degraded 狀態、週 collection 與 Gate credit 均未變，解除 **0 列**。

此 probe 僅使用既有行情唯讀 API 身分及歷史 K 線端點，未呼叫帳務、持倉、委託或交易 API，未寫正式 DB／CSV／sidecar。候選摘要位於隔離 visualization scratch `owned-validation/fubon-weekly-ohcl-probe-20261026/candidate.json`，SHA-256 `6B577868570210899725EC8E576E6F1E703CE32FCC6C7E90D1D467432F8DF0C6`；bounded Job receipt SHA-256 `273D3BB4B6CBDBE2B1DC709D400C1E3E3A8BA7609B9414C24A87B40E87FFDEF9`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 自然歸零及 handles 關閉。回應 hash 是 SDK 正規化物件的 canonical JSON hash，不是原始 HTTP bytes；本候選僅用來記錄精確查詢與結果，沒有任何正式資料套用。

### 2026-10-26 2330／2026-Q2 MOPS 公告時間與 T57 季報候選接線

修正 `build_mops_quarterly_pit_artifact.py` 將 T57 上傳時間誤寫成公告時間的問題。builder 現在必須提供同公司、同期間的 MOPS F26–F29 公告 artifact，確認匹配事件時間一致後，才會輸出；`announcement_date` 保留 MOPS 公告 timestamp，`available_date`／`t57_upload_at` 保留 T57 文件上傳 timestamp。另支援由 source manifest 補入存檔 HTML 未嵌入的 T57 查詢 URL，並按主 PDF 檔名選取多季頁面中的唯一列。輸出明確標示本機 PDF bytes 尚未驗證，不代表已核准來源版本。

使用既有 2330／2026-Q2 T57 清單與 MOPS availability artifact 產生隔離候選：公告時間 `2026-08-14T13:46:30+08:00`、T57 上傳／可得時間 `2026-08-14T13:59:44+08:00`，候選列 1 筆。schema validator 通過；P0 candidate audit 將此列列為 `observed_candidate`，剩餘 blocker 為 `research_only_not_source_accepted`／license、Owner written acceptance 與正式升格。PDF bytes 狀態仍 `unverified`，既有多個數值來源版本歧義及單位／口徑等缺項也未解除；正式 DB 寫入、品質解除、Gate 3 與 ML credit 均為 0。

候選 artifact SHA-256 `E33F9B489259AF8701ED21BB9D49E2AAAA7AC1A9CEAAE276B40B8CC4CCA7BDCC`；normalized validator output SHA-256 `16C88F4F9F118BEDA8CC81EDEB772A6D5D1FEDC4C870E2B8A463A886688177C7`；P0 audit SHA-256 `55A622770B0E345139BB464FEDAEFCC482C3DF92CBCCBFCAB046DD8FF11A3BA6`。產物在隔離 visualization scratch `gate3-mops-q2-candidate-verified/` 與 `gate3-mops-q2-p0-audit/`。builder／validator tests 9 passed；三個 bounded Jobs 均讀回 8 GiB／12-process／kill-on-close 限制，Job 自然歸零且 handles 關閉。這只確認候選欄位與 artifact schema 可用，未確認 PDF 官方 bytes 或數值來源 version bridge。

同日再建立 candidate-only numeric bridge：F26／F27／F28 分別接到 r8 保存的 T164 balance sheet／income statement／cash flow，逐一重驗 run-manifest artifact SHA、5 個 raw response SHA、T57 availability row SHA、MOPS event hash、公司／季別／期末日及 endpoint。唯一 r8 numeric candidate version `mops-t164-consolidated-statements-with-t57sb01-xbrl-row-codes.v2` 共 172 列（57／37／78），每列保留原 numeric source row SHA；衍生副本將 `announcement_date`／`publication_timestamp`／event timestamp 改用 MOPS `2026-08-14T13:46:30+08:00`，`numeric_available_at` 與 `available_date` 保持原捕獲時間語義。P0 audit 讀回 172／172 candidate rows，`timestamp_evidence=official_mops_announcement_timestamp`，仍為 `observed_candidate` 且 blocker `research_only_not_source_accepted`。T57 PDF bytes 未驗證，PDF 與 T164 數值是否同一報表版本、原始公告時的數值 response body、正式 observations 的三個 source_version 分組均未解；正式 DB 寫入／品質解除／Gate 3／ML credit 仍 0。

bridge SHA-256 `BA553522C514FE5049414B4A94A05CF60D84650C9CCF09DC44D5883C309A4629`；linked candidate SHA-256 `BAB76DFA071973209D0D99D2713165287D63A9426B3D18DA209392DAAD948699`；重新 validator 後的 P0 audit SHA-256 `20878DC7B173D53AED135657C89D92F7AB11982011B45CE2C3587A2AAC788165`。輸出位於隔離 scratch `gate3-event-numeric-bridge-final/` 與 `gate3-event-numeric-bridge-final-audit/`。bridge、原季度 builder、artifact validator 及 P0 audit 聚焦 **40 passed**；原始 r8 run 與正式 DB 未改動。

### 2026-10-26 富邦唯讀 API live probe：即時候選可取、既有缺口未解除

使用既有唯讀憑證，對 2330、1538、2881 取得 intraday ticker／quote，並查詢 2026-10-01 至 2026-10-26 公司行動。bounded Job exit 0，8 GiB／12-process／kill-on-close 限制讀回，Job 歸零且 handles 關閉。候選投影共 135 列：公司行動 133 列、`microstructure.limit_lock` 2 列（2330、2881）；沒有 disposition、分盤或停牌觀測。兩筆 quote 的 ticker `observation_date` 都是 2026-10-22，比 2026-10-26 capture 早 4 個日曆日，不能當作當日即時狀態。公司行動列沒有 `action_type`／公告時間，另有 1 列因欄位不合 contract 被拒；diagnostics 同時指出富邦沒有 documented full-delivery indicator，部分 quote 不足以產生 limit-lock。

所有候選均標為 `quality=degraded`、`availability_evidence_kind=first_observed_only`、`publication_at=null`、`downstream_eligibility=none`。因此這次確認富邦端點確能回傳研究候選，但沒有任何候選可以當作官方發布／歷史 PIT 證據；週報 16 筆 OHLC 缺值仍為先前精確比對 0/16，Forward 19 筆歷史事件警告仍為先前精確比對 0/19。MOPS 月營收公告時間、季報 PDF／T164 版本一致性、正式 source acceptance 與 Gate／ML 資格也不屬於這些 API 回應可解除的問題。正式資料解除 **0 列**，未寫正式 DB／CSV／sidecar，沒有提升 Gate 或 ML credit。

隔離候選 JSON SHA-256 `E144E0229997D59E068655A40B619168FF0DA89D0E921BAD1DCEF51C8D086539`；bounded Job receipt SHA-256 `C6D211896E836281A778D6FDCE7238D76E4D82249E69A37E78275E63A954B0E5`。輸出位於 visualization scratch `fubon-gap-probe-20261026-elevated/`；回應只保存正規化 candidate，不是原始 HTTP bytes，亦不構成 source acceptance。

<a id="2026-10-27-forward-official-market-event-source-audit"></a>

### 2026-10-27 Forward 企業行動／交易限制官方來源查核

依正式 `latest_status.json` 的 run `20261026T175624162476Z` 唯讀對回 19 個成熟 event/outcome：2026-09-18 的 7 檔（1103、1436、1437、1438、1529、1560、1569；目標行情日 10-21），以及 2026-09-21 的 12 檔（1314、1338、1528、1529、1560、1568、1569、1598、1611、1617、1709、1721；目標行情日 10-22）。19/19 outcome 均為 `ready`，但仍各有 `corporate_action_source_not_ingested` 與 `trading_restriction_source_not_ingested`，共 38 個來源警告。

現有官方 immutable sidecar 的涵蓋止於目標區間之前：manifest 觀測日 2026-09-14；TWSE TWT49U 最晚 09-14、TWTAUU 最晚 09-07、TWSE 暫停／復牌最晚 08-14、TPEx 暫停／復牌最晚 08-03。因此不能用這批 sidecar 證明 09-18 至 10-22 期間沒有企業行動或交易限制。先前富邦公司行動候選與 19 筆 event 的代碼／日期窗精確比對為 0/19；無命中不代表期間無事件，且候選沒有足以供下游使用的公告時間或完整類型。

官方可查路徑包括[TWSE OpenAPI](https://openapi.twse.com.tw/)（含 `TWTAWU` 暫停交易、`TWT85U` 變更交易、`TWT48U_ALL` 除權息預告）及[TPEx OpenAPI](https://www.tpex.org.tw/openapi/)；不過本批候選為上市股票，TPEx 資料不能代替 TWSE。對 TWSE 的 `TWTAWU`、`TWT85U`、`TWT48U_ALL` 以 2026-09-18、09-21、10-21、10-22 做 12 次唯讀日期查詢，全部在 DNS `getaddrinfo failed` 階段終止，沒有 HTTP response，也沒有可計算的命中數。故匹配狀態是**未知**，不是 0 命中；正式資料與現有 sidecar 未變。

TWSE 官方歷史 TWT85U 另有自 2017-08-11 起的每日檔，但資料商店標示內部使用 NT$500/月並限制僅供訂購者內部使用，須先核清實際用途／授權；本次沒有購買或訂閱。[TWSE TWT85U 資料商店說明](https://eshop.twse.com.tw/zh/product/detail/036982f02fbb4d1a805024d5e72d7e17)。解除警告仍須取得可用且授權明確、涵蓋完整期間的官方來源，逐一核對股票與有效日期；本次新增候選 0、來源警告解除 0、正式 DB 寫入 0、Gate／PIT／ML 資格不變。探查收據位於隔離 visualization scratch `owned-validation/restriction-source-audit-20261027/`，有界 Job 自然歸零、8 GiB／12-process 限制讀回且 handles 關閉。

### 2026-10-26 Recommendation 兩筆 score missing 追查與指標重算邊界

讀回同日 200 筆推薦 screening cohort 後，`1516` 與 `1541` 是僅有的 2 筆 `quality=missing`、`stage=strategy_evaluation`、`reason=total_score_missing_or_nonfinite`；另外 194 筆 Why Not 為流動性政策排除或策略無訊號，不能當成缺資料。策略快照啟用 RSI、MACD、ADX 與 MA5/10/20/60。

修正 `decision_module.indicator_reuse` 的重用判定：一般推薦只有在每個預設指標欄位的最新列都存在且為有限數值時才重用；若最新列缺值，保持計算器啟用，讓其依輸入 OHLC 重算。`causal-score-input.v1` 保留原有未知值政策，不因後續資料是否出現而選擇重用。新增尾列 NaN 與 Infinity 的回歸案例；`tests/test_indicator_reuse.py` 為 11 passed，兩個變更 Python 檔 `py_compile` 通過。此修補不填值，也不會把重算後仍缺的指標改成中性分數。

唯讀、記憶體內重播同一策略參數與截至 2026-10-22 的行情後，`1516` 最近一列為 2026-10-14，因 TWSE 公告舊股交易於 2026-10-15 至 2026-10-23 停止、2026-10-27 新股恢復交易，故 10/22 無行情是停牌期間預期結果；參見 [TWSE 停止舊股交易公告](https://www.twse.com.tw/en/announcement/announcement/list.html) 及 [減資參考價／恢復交易日期](https://www.twse.com.tw/en/announcement/reduction/twtauu.html)。其截至 10/14 的 60 列窗口只有 59 列 OHLC 完整，最近連續有效段 38 列；當時仍不能算 MA60，不應補造停牌日價格。

`1541` 於 2026-07-28 至 10-22 的 60 列輸入有 2 列全 OHLC 缺值（9/16、9/24），最近連續有效段只有 17 列。重算仍得到 MA5、MA10、RSI，但 MA20、MA60、MACD、ADX 仍為空，因此總分仍缺。修補後的 read-only 診斷未寫正式 DB／推薦紀錄，兩筆缺分實際解除仍為 **0**。後續逐日來源追查與富邦歷史日線結果見下節。

#### 2026-10-27 富邦歷史 K 線精確日期重查

依富邦官方 Historical Candles 文件定義的 `from`／`to` 參數，重查 1541 的 2026-09-15 至 09-17 日 K：回傳 2 根（09-15、09-17），仍無 09-16。第一次探測使用 SDK 不識別的 `from_date`／`to_date`，API 回傳預設近期區間，該回應已作廢、不納入缺值判定；修正參數後才得到上述精確範圍結果。更正後候選摘要 SHA-256 `719D09A892434AD13F643204505C6BB0D45FB8DA5C40B199772BC8CB96169A22`；payload canonical SHA-256 `23315ada5739de60ee278fdfa5ab60d3e77660aa52e4997e239b9c2a38305dce`；bounded receipt 位於 `owned-validation/fubon-gap-recheck-20261027/job-corrected/receipt.json`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 歸零且 handles 關閉。這次未讀帳戶／持倉／委託、未呼叫交易 API，亦未寫正式資料。1541 9/16 OHLC 缺值仍無候選可補；此前週報 16 筆精確比對 0/16、Forward 19 筆事件候選比對 0/19 的結論不變，正式品質解除 0 列，Gate／PIT／ML 不變。

### 2026-10-26 1541 缺 OHLC 日確認與富邦歷史 Candles 探測

唯讀檢查 1541 `daily_prices` 的兩個全 OHLC 空列：2026-09-16 `成交筆數=1`、`成交股數=8,000`，這是有成交但 OHLC 缺值的實際資料品質缺口；2026-09-24 `成交筆數=0`、`成交股數=0`，是無成交列，不應當成 OHLC 漏採。這兩列最近窗口因此仍只有 17 根連續有效 OHLC bar。

更正前一節對富邦能力的概括：富邦官方 [Historical Candles 文件](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/historical/candles/) 確實提供上市／上櫃日線歷史行情；前次 API probe 沒有查詢這個歷史 endpoint。此次以已授權唯讀行情連線查 1541／2026-09-15 至 09-17，取得 09/15 與 09/17 bar，但回應沒有 09/16 bar，故無法補回本地的 8,000 股成交列。SDK 回應 canonical SHA-256 `03ce0a133e75b9b46485e3cf801d3d3a1bf73128bb7cdc822eeb5d2b2cee7306`；bounded receipt 位於 visualization scratch `owned-validation/fubon-historical-1541-elevated-retry2-20261026/receipt.json`，8 GiB／12-process 限制讀回、Job 自然歸零、handles 關閉。未要求帳務資料，未呼叫下單 API。

唯讀查詢 TWSE 官方 `MI_INDEX` 2026-09-16 JSON 成功：HTTP 200、`stat=OK`，1541 官方列為成交股數 8,000、成交筆數 1、成交金額 166,000，但開盤、最高、最低、收盤均為 `--`。原始回應 244,822 bytes，SHA-256 `afbe5d3c9220a4e14c08105e3f0d5843b7dff86385c75f1091e4f7cd752f8e29`，保存於隔離 scratch `owned-validation/twse_1541_20260916_response.json`。因此已確認官方行情本身沒有提供這日 OHLC；不能把成交金額除以股數自行推成四種 OHLC，也沒有可安全回填的官方價格。9/16 應保留 missing；本地不是漏掉一筆官方有提供的 OHLC。沒有正式 DB／CSV／sidecar 寫入或 score missing 解決。

### 2026-10-26 富邦行情 API 對財報與歷史警示缺口的可用範圍

依[富邦行情 API 官方功能清單](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/getting-started/)，Web API 範圍為日內、快照、歷史、技術指標、公司行動與盤後籌碼；清單沒有財務報表申報、MOPS F26/F27/F28、T164/XBRL 或報表修訂版本端點。這是依官方端點清單作的範圍判讀，不代表其他資料服務不存在。故富邦行情 API 不能為 Gate 3 補財報內容、MOPS 公告 timestamp 或歷史 PIT／版本橋。[Historical Candles](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/historical/candles/) 可提供歷史 OHLCV，但 1541／2026-09-16 的精確查詢沒有該日 bar，且 TWSE 原件四個 OHLC 皆為 `--`，不能補造價格。

富邦有[依日期查詢的除權息端點](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/corporate-actions/dividends/)及資本變更類端點，故不概括為「完全沒有歷史公司行動」；但這些端點欄位描述的是除權息日期／股務資訊，不能直接替代目前未命中的暫停交易、變更交易與歷史處置警示公告。`intraday/ticker` 提供 `isAttention`、`isDisposition`、`securityStatus` 等股票狀態欄位，官方契約未提供這些狀態的逐日公告時間線，僅能做帶擷取時間的當前觀測。[Intraday Ticker 欄位](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/intraday/ticker/) 富邦 API 此輪未解除 OHLC、Forward 警告或財報缺件；無正式資料寫入，Gate／PIT／ML 不變。

<a id="2026-10-26-recommendation-缺分原因呈現"></a>

### 2026-10-26 Recommendation 缺分原因呈現

為免使用者只看到泛用 `total_score_missing_or_nonfinite`，`ScoringEngine` 現共用計分所需欄位定義診斷最新列缺少的已啟用輸入；Recommendation 將結果以 `score_input_missing:<欄位>` 寫入既有 typed warnings，若不能精確辨識則用 `score_inputs_not_identified`。UI 在篩選列「備註」將已知指標轉成中文，未知欄位／警告照原文保留。狀態仍 `missing`、原原因碼不變，不補值、不放行；沒有改 negative-evidence schema 或正式資料。

驗證：`tests/test_indicator_reuse.py`＋缺分警告 UI regression **13 passed**；必要 Update Workbench UI **97 passed**；全域 mypy **1,159 source files clean**；6 個變更 Python 檔 `py_compile` 通過。較大的 Recommendation regression **28 passed／31 failed**：候選多數在本工作樹現有的 valuation gate 以 `valuation_pe_missing` 提前結束，另 3 個保存測試在 sandbox temporary path rename 得 `WinError 3`，因此 service 分數分支的完整回歸尚未通過。`scripts/qa_validate_update_tab.py` 因 sandbox 拒絕寫入 `output/qa/update_tab/RUN_LOG.txt`（PermissionError）未能執行。上述結果均以 scratch 的受限 Windows Job 執行，Job 自然歸零、handles 關閉。

### 2026-10-26 富邦 v2.4 盤後籌碼端點唯讀實測

依 Owner 要求，使用富邦既有行情唯讀憑證，對 2330 查詢官方文件列出的三大法人買賣超與集保戶股權分散端點，期間 2026-10-01 至 2026-10-26。第一輪只帶 API Key 直接呼叫收到 HTTP 401；改用既有文件化流程 `apikey_login` → `init_realtime` 取得 SDK 行情權限後，兩個端點均成功回應。三大法人回傳 15 個交易日列（2026-10-01 至 10-22），欄位為 `date/foreign/trust/dealer/total`；集保回傳 4 期（2026-10-02 至 10-22），欄位為 `date/distributions`。這證實富邦可供應這兩類最新歷史觀測，不能推論全市場或完整歷史覆蓋。

本機行情 SDK 是 `fubon-neo` 2.2.8 與 `fugle-marketdata` 2.4.1；盤後籌碼路徑經通用唯讀 REST request 呼叫，舊包沒有對應的便利方法。回應摘要與 SDK 正規化 payload SHA-256 位於隔離 scratch `owned-validation/fubon-v24-ownership-probe-20261026/result.json`（檔案 SHA-256 `2DA2FD069FCE84092DCDB39BABE7908AF1D68F7503E3A465E66E206D9F53D58C`）；bounded Job receipt SHA-256 `6BE57423FAE1EF335328B4E35344B510E037E4907B99D6FD1B7576125369119F`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、Job 自然歸零且 handles 關閉。只保存列數、日期範圍、欄位與 hash，未保存完整 response body；未讀帳戶／持倉／委託，未呼叫交易 API，未寫正式 DB／CSV／sidecar。

這是新增盤後籌碼的**資料可達性證據**，不是既有缺口解除。端點的歷史列提供資料日期，但本次回應未證明每列首次可得時間；因此不能把資料日期當 `available_date`／公告時間，也不能用現在回傳的歷史內容回填過去決策時點。P0 登錄仍要求明確可得時間、來源條款與用途審查、覆蓋量測及 Owner 接受；目前 Formal downstream eligibility 仍為 `none`，可作隔離 candidate/shadow 審查，正式品質解除 0 列、Gate／PIT／ML credit 仍為 0。富邦仍無 MOPS 公告 timestamp、財報數值／報表版本橋或官方交易日曆端點，故這次不能解除上述缺口或 `market_breadth_cadence:unverified`。

<a id="2026-10-27-正式月營收與-2330-2026-q2-季報精確版本重盤"></a>

### 2026-10-27 正式月營收與 2330／2026-Q2 季報精確版本重盤

在 Windows Job 中以正式 SQLite `mode=ro`、`PRAGMA query_only=ON` 及唯讀 availability loader 重查現況。正式 mapping 載入 1,834 筆且 diagnostics 為 0；SQLite 有 242,650 筆 `quality=degraded` 且 `announced_date` 為空的月營收列。以 MOPS 正式公告證據、公司／期間、`as_of_date` 與 `target_source_version` 精確連接後，這批缺公告日列目前 **0 筆**有可套用的精確 mapping；資料庫與 mapping CSV 的大小及 mtime 前後一致。另唯讀確認先前修復的 2330／2026-04 列仍為 `announced_date=2026-05-08`、`available_date=2026-05-09`、`quality=observed`、source version `mops-static-snapshot-monthly-revenue-2026-06-16`。因此本次重盤後累計可確認的正式解除為 **1 列**，沒有其他可安全解除的精確月營收列；不能擴用相近日期、公司或 snapshot 版本。

同次唯讀核對 2330／2026-Q2：正式 `fundamental_statement_items` **0 列**；`fundamental_current_observations` 有 **161 列、11 個 source_version**，aggregate feature eligibility **161/161 為 0**。因此雖已有 MOPS 公告 timestamp 與 172 列 T164／PDF 候選內容分類，目前沒有正式季報列可因補公告時間而重算。數值版本橋、單位／period basis、來源條款與 4 個未解列仍未完成，不能把公告事件時間當成財報內容版本或授予 Gate 3／PIT 資格。

兩項受控讀回的 receipts／原始輸出位於 scratch `owned-validation/mops-monthly-current-audit-20261027/` 與 `owned-validation/mops-q2-formal-current-audit-20261027/`；Jobs 讀回 8 GiB／12 process／kill-on-close，剩餘程序 0。兩次都沒有正式資料寫入。本次盤點把下一步鎖定為取得精確的數值版本認領證據；不再重試不能提供公告或財報版本橋的富邦行情 API。

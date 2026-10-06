# UX24 第一版 stage 1–3 有限工程封存

基線 `8a78eac313f8544eb01657da3510fb15af3c179b`。本包沿用原計畫 F1–F4 已接受範圍，關閉有限工程終點；完整 UX、Native、真人、正式啟用及自然資格沒有因此完成。原計畫只追加，未另建產品計畫。

## 可用版本與實際修補

第一版提供具名完整研究母體的 close／MA20／MA60、兩條固定 close-above-MA 方法、AND／OR 與 why／why-not，市場原日／周強弱排名共享 immutable 來源；個股可保留來源身份、收藏、精確返回與新程序原來源讀回。歷史有界索引／分頁與版本拒絕已具備。完整指 declared cohort，不是官方全市場；方法符合不等於交易入選，未知價格時點、成本、分數與資格不補造。

既有當下個股、保存推薦、觀察清單、聲明持倉用途各自保留 context；本包沿用已接受的用途證據，補驗其返回及錯源拒絕契約，不重做舊四用途 Native／1477／learner／Library／個人 migration。新增的實際全 App 三程序測的是每日研究 v1／原排名 v2 收藏鏈，不能冒充四用途全部重新原生驗收。

找到一個產品缺陷：`MainWindow._coerce_stock_research_context()` 將舊 mapping 缺少的 optional `rank_context` 補成空字串，DTO 因而拒絕。只改為缺少時 `None`；明示空字串或錯誤格式仍拒絕，不以同股來源或最新結果代替，失敗不替換 session。原失敗 XML 保留；回歸涵蓋真實 MainWindow 路由。另修本輪 QA 包裝器的測試 import 路徑與 Windows 終端 UTF-8，並非產品故障。

## 有限工程終點表

| 原 UX | 本包認定工程終點完成的範圍 | 整項狀態與剩餘界線 |
|---|---|---|
| UX03 | exact bookmark／來源／股碼返回，拒絕錯身份；取消不替換 last-good | partial；全產品跨頁與 Native／真人另驗 |
| UX04 | named full-cohort 名單、同源個股下鑽與缺件分母 | partial；正式 B 母體／部署、新方法擴充不在首版 |
| UX05 | 已開兩方法 AND／OR、理由與原排名保留 | partial；其他方法另立契約，Native／真人另驗 |
| UX06 | 現況／保存用途摘要與 exact context 回讀 | partial；完整互動圖表／全用途產品驗收另列 |
| UX09 | 有界歷史索引／分頁、schema 支持／拒絕、新程序重讀 | partial；Native、自然歷史增長與全產品驗收另列 |
| UX15 | 本版入口／操作／參數／判讀／限制／排錯文件同步 | partial；3–5 位非開發者可理解性驗收另列 |
| UX17 | 本版 F1 已接受性能例外、F4 有界長保留與當下容量預檢 | partial；新擴充資源、正式根目錄與自然增長不外推 |

七項都是「限定工程終點完成」，不是把七項整體改成 done。9 stages 仍 1 done／7 partial／1 pending；24 UX 仍 2 done／20 partial／2 pending。

## 收據與驗證

新增 `scripts/qa_validate_first_version_release.py`，輸出只能在 repo `output/qa/` 的新目錄。重用既有 F4 actual MainWindow child；子程序另拒絕 FA_Data 讀取，沿用案例外寫入／SQLite、網路及子程序拒絕。明示隔離 DATA_ROOT／OUTPUT_ROOT／PROFILE／Qt offscreen，建立全九工作區而非畫面 spy。setup → fresh readback → no-arg defaults 三個不同 PID exit 0，來源八檔 inventory／收藏／rank parent hash 相同；合法 v1/v2、schema 拒絕、cancel／stale last-good、合作 close 都驗到。不涉及正式 source 或個人資料。

- 修後 23 個 context／來源復原／ML scope／bookmark bridge／持倉與清單返回案例通過；修前 21 pass／1 fail 保留於 `context.xml`。
- Workbench 85 passed；update validator 25 passed／4 skipped／0 failed；完整 mypy 812 檔無錯。QA 工具單檔 mypy 使用 `--follow-imports=silent`：不將既有未納入 production mypy 的測試 helper 34 個型別錯誤算成本包錯誤或宣稱已修。
- F1 性能 18.6219658% 的既定例外沿用；[F2／F3](F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md) 已接受 A／A 不重跑，不新增官方母體、排名或方法。
- 原 [F4 20/120/250 保存](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md) 收據沿用，沒有重跑 250 次 producer。當下只讀原 DB 重播 250 revisions、驗 500 refs／250 feature manifests／250 rank manifests；1,005 原檔 hash 與完整檔集合不變，中央 policy 20 GiB 保留不改。治理 scan 完整、unknown entries 0、validation 6,202,133 bytes，當下 free 與 headroom 見 raw receipt。不把 logical retained bytes 3,257,230 當總實體容量；實體、staging／WAL／index／backup 量測沿原收據。

Raw：`output/qa/ux24_first_version_20261006/run04/receipt.json`、三 child receipts／logs、`context_fixed.xml`、`workbench.xml`、`update_validator.txt`、`mypy.txt`、compile／quant／commit readback 與原計畫前綴證明。run01 import 失敗、run02 中文 print exit 1（內部 receipt 通過）與修前 context XML 全部保留。run03 是產品修前封存，run04 才是修後權威收據。

run04 SHA256 `d411bf16300cc13042e31a3fd92439386125e4caacaa06fa2a69a32847671a6e`；setup／readback／defaults PID 28116／29544／31364，各 6.829／5.719／5.187 秒。這些是本輪觀測時間，不另設性能門檻；三次皆無 shutdown error，來源／實作 pins 前後一致。原計畫 220,624 bytes 前綴 SHA256 `0f72a8d31668979bf9bfa74a0702aa74dadcb1f41c18bba8d44acbbdcb85a24f` 完整保留，追加後 224,602 bytes SHA256 `fc5164cca1d6ece10bd3a1e0c7ef53b46f73fd38369e502bea821fb90562ad5b`。

## 真正剩餘工作與外部接受

本次首版固定 A／A、manual/on-demand 範圍沒有再發現未修工程缺陷。正式庫 apply 是尚未批准的部署動作，既有 COW 工程收據不重開；Native 索引／排名跨頁鍵鼠、3–5 位非開發者驗收另列。舊 1477 與已接受 1000×835／125%、性能例外不重開。

較大產品仍有工程：UX07 圖表 prototype、UX08 更完整圖表、UX10 第二合格方法、UX11 typed 規則執行、UX14 其他 owner notes／ledger、UX16／18 更多 feature／consumer、UX19 正式部署與維運、UX20 日主部署邊界、UX21 qualified benchmark adapter／完整 labels／正式部署，以及 UX24 全產品端到端驗收。UX12／13 大範圍也未有全工程完成證據。這些不能用「等自然成熟」掩蓋，也不屬本包授權。

官方 availability／membership／calendar custody、自然跨日與 H5/10/20 成熟、ML OOS／投資效果是外部證據／自然資格；成本、benchmark、target policy 與正式啟用則需要明確產品／部署決策。不能因工程封存授予 PIT／training／trading flags。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| `ui_qt/main.py`／context test | 修改 | review 本包 commit 後 `git revert <本包commit>` | 舊 mapping 缺件的錯誤會復現 |
| QA tool／本收據 | 新增 | 同上，保留 raw 案例與所有資料 | 失去本批封存入口，產品無依賴 |
| Manual／Snapshot／索引／routing／coverage | 修改 | 同上 | 本版狀態入口回到較早內容 |
| 原計畫 | 僅追加 | 先核對 `plan_before.bin` 前綴與 SHA，再只反向本批附錄 | 不得覆蓋其後他人追加 |

先核對工作樹／commit 範圍與前綴，反向限定提交後重跑受影響路由；不刪資料、不 reset／clean，不碰其他 owner 的容量／capture／排程檔。完成本機 commit＋readback 即停，無 push／Task／migration／重訓／清理／Native。
